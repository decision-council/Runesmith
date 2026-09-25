"""Code objects: a repository whose behaviour is observed through its tests.

The kernel owns the *public signal* of a code object: it applies a candidate's
file overrides to a private work copy, runs the named tests, and returns
pass/fail, sanitized ``FAILED``/``E`` lines, and optionally the source lines the
tests executed. Organs never see the work copy's path, test source, or any
held-out judge; they see only this signal.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PLUGIN_NAME = "runesmith_trace_plugin"
PLUGIN_FILE = Path(__file__).with_name("trace_plugin.py")
COPY_IGNORE = (".git", ".hg", ".venv", "venv", "node_modules", ".tox", ".mypy_cache", ".pytest_cache", ".runesmith")


def is_link(path: Path) -> bool:
    """A symbolic link or a Windows junction. Runesmith never follows one: it can lead out of the folder (into
    someone's documents, or a whole disk) or round in a circle. Python's own walkers follow junctions."""
    try:
        if Path(path).is_symlink():
            return True
        isjunction = getattr(os.path, "isjunction", None)            # Python 3.12+
        return bool(isjunction and isjunction(path))
    except OSError:
        return False


def _copy_ignore(*patterns: str):
    """``shutil.ignore_patterns`` that also leaves out links and junctions: a copy holds the object's own files."""
    by_name = shutil.ignore_patterns(*patterns)
    return lambda directory, names: set(by_name(directory, names)) | {n for n in names if is_link(Path(directory) / n)}


@contextmanager
def throwaway_copy(repo: Path, scratch: Path | None = None) -> Iterator[Path]:
    """A temporary copy of an object, so running its tests never writes into the object itself."""
    if scratch is not None:
        Path(scratch).mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="rs-copy-", dir=str(scratch) if scratch is not None else None))
    try:
        target = base / Path(repo).name
        shutil.copytree(Path(repo), target, ignore=_copy_ignore(*COPY_IGNORE, "__pycache__"))
        yield target
    finally:
        shutil.rmtree(base, ignore_errors=True)


def sanitize(output: str, workdir: Path, src_dir: str = "src") -> list[str]:
    """Keep only FAILED/E lines, strip local paths, and drop lines that quote source files."""
    text = output.replace(str(workdir), "").replace(str(workdir).replace("\\", "/"), "")
    keep = [line for line in text.splitlines() if line.strip().startswith("FAILED ") or line.startswith("E ")]
    marker, marker_win = f"{src_dir}/", f"{src_dir}\\"
    return [line[:300] for line in keep if marker not in line and marker_win not in line][:20]


BOM = b"\xef\xbb\xbf"


def read_src_files(src_root: Path, prefix: str = "src") -> dict[str, str]:
    """Source files as text. A UTF-8 byte-order mark is not text (``ast.parse`` rejects it), so it is dropped here
    and restored by :func:`encode_like` when a fix is written back."""
    found = []
    for current, dirs, names in os.walk(src_root):              # never through a link or junction (see is_link)
        here = Path(current)
        dirs[:] = [d for d in dirs if d != "__pycache__" and not is_link(here / d)]
        found.extend(here / n for n in names if not is_link(here / n))
    files = {}
    for path in sorted(found):                                  # the same order as a sorted rglob of the files
        if not path.is_file():
            continue
        try:
            files[f"{prefix}/" + path.relative_to(src_root).as_posix()] = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
    return files


def encode_like(text: str, current: bytes | None) -> bytes:
    """``text`` as bytes in the style of the file it replaces: that file's byte-order mark and line endings."""
    crlf = current is not None and b"\r\n" in current
    data = (text.replace("\r\n", "\n").replace("\n", "\r\n") if crlf else text).encode("utf-8")
    if current is not None and current.startswith(BOM) and not data.startswith(BOM):
        data = BOM + data
    return data


class CodeTask:
    """One reusable private work copy of a repository and its failing tests."""

    def __init__(self, template: Path, failing_tests: list[str], *, scratch: Path,
                 interpreter: str = sys.executable, src_dir: str = "src",
                 src_override_dir: Path | None = None, timeout_s: int = 90) -> None:
        scratch = Path(scratch).resolve()
        scratch.mkdir(parents=True, exist_ok=True)
        self.work = scratch / f"rs-work-{uuid.uuid4().hex[:12]}"
        shutil.copytree(Path(template), self.work, ignore=_copy_ignore(*COPY_IGNORE))
        self.src_dir = src_dir
        if src_override_dir is not None:
            shutil.rmtree(self.work / src_dir, ignore_errors=True)
            shutil.copytree(Path(src_override_dir), self.work / src_dir, ignore=_copy_ignore())
        self.failing_tests = list(failing_tests)
        self.interpreter = interpreter
        self.timeout_s = timeout_s
        self.plugin_dir = self.work / ".runesmith-plugin"
        self.plugin_dir.mkdir()
        shutil.copyfile(PLUGIN_FILE, self.plugin_dir / f"{PLUGIN_NAME}.py")
        self.original = read_src_files(self.work / src_dir, src_dir)
        self._applied: dict[str, str] = {}
        self.runs = 0

    # -- file state ---------------------------------------------------------
    def src_files(self) -> dict[str, str]:
        return dict(self.original)

    def apply(self, overrides: dict[str, str]) -> None:
        """Make the work copy equal to original + ``overrides`` (paths are ``src/...``)."""
        for path in set(self._applied) - set(overrides):
            self._write(path, self.original[path])
        for path, text in overrides.items():
            if path not in self.original:
                raise ValueError(f"override outside the object's source files: {path!r}")
            if self._applied.get(path) != text:
                self._write(path, text)
        self._applied = {p: t for p, t in overrides.items() if t != self.original[p]}

    def applied(self) -> dict[str, str]:
        """The overrides currently in the work copy (only files that differ from the original)."""
        return dict(self._applied)

    def _write(self, rel: str, text: str) -> None:
        (self.work / rel).write_text(text, encoding="utf-8")

    def current_src_dir(self) -> Path:
        return self.work / self.src_dir

    # -- the public signal --------------------------------------------------
    def run(self, overrides: dict[str, str] | None = None, *, trace: bool = False) -> dict:
        if overrides is not None:
            self.apply(overrides)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(self.work / self.src_dir), str(self.work), str(self.plugin_dir)])
        args = [self.interpreter, "-m", "pytest", *self.failing_tests, "-q", "-p", "no:cacheprovider", "-x"]
        trace_out = None
        if trace:
            trace_out = self.work / f".rs-trace-{uuid.uuid4().hex[:8]}.json"
            env["RUNESMITH_TRACE_ROOT"] = str(self.work / self.src_dir)
            env["RUNESMITH_TRACE_OUT"] = str(trace_out)
            args += ["-p", PLUGIN_NAME]
        started = time.monotonic()
        try:
            proc = subprocess.run(args, cwd=str(self.work), env=env, capture_output=True, text=True,
                                  timeout=self.timeout_s, errors="replace")
            code, out, timed_out = proc.returncode, (proc.stdout or "") + (proc.stderr or ""), False
        except subprocess.TimeoutExpired as exc:
            code, timed_out = None, True
            out = exc.stdout if isinstance(exc.stdout, str) else ""
        self.runs += 1
        result = {"passed": code == 0 and not timed_out, "exit_code": code, "timed_out": timed_out,
                  "duration_s": round(time.monotonic() - started, 3),
                  "signal_lines": sanitize(out, self.work, self.src_dir)}
        if trace_out is not None:
            executed: dict[str, list[int]] = {}
            if trace_out.exists():
                raw = json.loads(trace_out.read_text(encoding="utf-8"))
                executed = {f"{self.src_dir}/" + rel: lines for rel, lines in raw.items() if not rel.startswith("..")}
                trace_out.unlink()
            result["executed_src_lines"] = executed
        return result

    def close(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)
