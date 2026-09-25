"""Confined organ process (runs as ``python -I -B organ_child.py``).

Standard library only: it must not import the kernel. The host sends one init
line, then this process loads the organ module from its staged directory,
installs an audit hook, and calls the organ's entry point with a ``Cockpit``.
Every effect the organ wants — a model call, a test run, a log line — travels
back to the host as a typed request; the host decides, charges the budget, and
answers. Reads outside the staged organ and the Python installation, all writes,
network, subprocesses and native code are refused.

Protocol: newline-delimited ASCII JSON on the original stdout/stdin. The organ's
own ``print`` goes to stderr so it cannot forge protocol messages.
"""

import importlib.util
import json
import os
import sys
import traceback

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_DENY_EXACT = {
    "subprocess.Popen", "os.system", "os.startfile", "os.fork", "os.forkpty", "os.kill", "os.killpg",
    "os.remove", "os.unlink", "os.rename", "os.replace", "os.rmdir", "os.mkdir", "os.makedirs",
    "os.chmod", "os.chown", "os.link", "os.symlink", "os.truncate", "os.utime", "os.putenv",
    "os.unsetenv", "os.chdir", "shutil.rmtree", "shutil.copyfile", "shutil.copytree", "shutil.move",
    "shutil.chown", "shutil.make_archive", "shutil.unpack_archive", "_winapi.CreateProcess",
    "_winapi.CreateFile", "_winapi.CreateNamedPipe", "urllib.Request", "http.client.connect",
    "webbrowser.open", "ftplib.connect", "smtplib.connect", "poplib.connect", "imaplib.open",
    "nntplib.connect", "telnetlib.Telnet.open", "msvcrt.open_osfhandle", "mmap.__new__",
    "sys.remote_exec", "os.add_dll_directory",
    # Introspection and code-construction routes that could tamper with this guard or craft bytecode:
    "code.__new__", "sys.addaudithook", "sys.settrace", "sys.setprofile", "pickle.find_class",
    "os.chflags", "os.lchflags", "os.lchmod", "os.mkfifo", "os.mknod", "os.chroot",
}
_DENY_PREFIX = ("socket.", "os.exec", "os.spawn", "os.posix_spawn", "ctypes.", "winreg.", "_ssl.",
                "sqlite3.", "resource.",
                "_winapi.",     # OpenProcess/TerminateProcess would let an organ kill other processes
                "gc.",          # gc.get_objects/get_referrers could reach and widen this guard's allow-list
                "signal.")     # not "marshal.": the import system itself uses marshal.loads for cached bytecode
# Python-level audit hooks are per interpreter: a sub-interpreter would run without this guard at all.
_DENY_IMPORTS = {"_interpreters", "_xxsubinterpreters", "_xxinterpchannels", "_interpchannels", "_interpqueues",
                 "concurrent.interpreters", "_testcapi", "_testinternalcapi", "_ctypes", "ctypes"}
_LISTING = {"os.listdir", "os.scandir", "glob.glob", "os.walk", "pathlib.Path.glob", "pathlib.Path.rglob"}


def _norm(path):
    if isinstance(path, bytes):
        path = path.decode("utf-8", "replace")
    return os.path.normcase(os.path.abspath(str(path)))


def install_guard(allowed_roots):
    roots = [_norm(root) for root in allowed_roots]

    def inside(path):
        target = _norm(path)
        return any(target == root or target.startswith(root + os.sep) for root in roots)

    def hook(event, args):
        if event == "open":
            path, mode, flags = (list(args) + [None, None, None])[:3]
            if isinstance(path, int):
                return
            writing = (isinstance(mode, str) and any(ch in mode for ch in "wax+")) or (
                isinstance(flags, int) and flags & _WRITE_FLAGS)
            if writing:
                raise PermissionError(f"organ may not write files ({path!r})")
            if not inside(path):
                raise PermissionError(f"organ may not read outside its staged directory ({path!r})")
        elif event == "import":
            name = args[0] if args else ""
            if isinstance(name, str) and (name in _DENY_IMPORTS or name.split(".")[0] in _DENY_IMPORTS):
                raise PermissionError(f"organ may not import {name}")
        elif event in _LISTING:
            path = args[0] if args else "."
            if path is None or not inside(path):
                raise PermissionError(f"organ may not list {path!r}")
        elif event in _DENY_EXACT or event.startswith(_DENY_PREFIX):
            raise PermissionError(f"organ may not perform {event}")

    sys.addaudithook(hook)


class CockpitError(RuntimeError):
    """The host refused or failed a request (budget exhausted, invalid arguments ...)."""


class Cockpit:
    """The organ's only handle on the world. Method names are the granted affordances."""

    def __init__(self, reader, writer, grants):
        self._reader, self._writer, self._n = reader, writer, 0
        self.grants = tuple(grants)

    def _send(self, message):
        self._writer.write((json.dumps(message, ensure_ascii=True) + "\n").encode("ascii"))
        self._writer.flush()

    def call(self, name, **args):
        self._n += 1
        self._send({"rpc": name, "id": self._n, "args": args})
        line = self._reader.readline()
        if not line:
            raise CockpitError("host closed the cockpit")
        reply = json.loads(line.decode("ascii"))
        if reply.get("error") is not None:
            raise CockpitError(str(reply["error"]))
        return reply.get("result")

    # Named affordances (the host must grant each one).
    def ask(self, packet, schema, purpose, system=None):
        """One model call through the kernel's router. Returns {ok, data, error_kind, error, latency_s}.

        ``packet`` is a dict (sent as sorted JSON) or a string; ``system`` optionally
        replaces the default system instruction.
        """
        return self.call("ask", packet=packet, schema=schema, purpose=purpose, system=system)

    def run_signal(self, files=None, trace=False):
        """Run the object's public signal with ``files`` (path -> full text) overriding the original."""
        return self.call("run_signal", files=files, trace=trace)

    def budget(self):
        """Remaining calls, signal runs and seconds for this opportunity."""
        return self.call("budget")

    def log(self, stage, **data):
        """Record a telemetry mark (a stage boundary or observation) in the kernel ledger."""
        return self.call("log", stage=stage, data=data)

    def recall(self, query, k=5):
        """Retrieve up to ``k`` relevant memories (if the host grants memory)."""
        return self.call("recall", query=query, k=k)


def main():
    reader = sys.stdin.buffer
    writer = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    sys.stdout = sys.stderr                     # organ prints cannot reach the protocol
    sys.stdin = open(os.devnull, "r")
    init = json.loads(reader.readline().decode("ascii"))
    organ_dir = os.path.abspath(init["organ_dir"])
    stdlib_roots = {sys.base_prefix, sys.prefix, sys.exec_prefix}
    install_guard([organ_dir, *stdlib_roots])
    cockpit = Cockpit(reader, writer, init.get("grants", ()))
    try:
        spec = importlib.util.spec_from_file_location(init["module"], os.path.join(organ_dir, init["module"] + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[init["module"]] = module
        spec.loader.exec_module(module)
        result = getattr(module, init.get("entry", "run"))(init["view"], cockpit)
        cockpit._send({"final": result})
    except BaseException as error:  # the host must learn every failure mode
        cockpit._send({"fatal": {"type": type(error).__name__, "error": str(error)[:1000],
                                 "trace": traceback.format_exc()[-2000:]}})


if __name__ == "__main__":
    main()
