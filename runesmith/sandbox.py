"""Host side of confined organ execution.

:func:`run_organ` stages an organ directory, starts ``organ_child.py`` in an
isolated interpreter with a secret-free environment, and serves the organ's
requests through ``handlers`` — the affordances the kernel grants for this
opportunity. The host enforces the wall-clock limit by killing the child.
A handler may raise :class:`HostHalt` to end the opportunity (for example on
transport censoring); the exception propagates to the caller after cleanup.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from runesmith.oslimits import DEFAULT_MEMORY_BYTES, close_job, posix_preexec, windows_job

CHILD_FILE = Path(__file__).with_name("organ_child.py")
MAX_LINE_BYTES = 8_000_000
MAX_STDERR_BYTES = 16_000_000


class HostHalt(Exception):
    """Raised by a handler to terminate the organ; re-raised to the caller."""


class RequestRefused(Exception):
    """Raised by a handler to refuse one request; the organ sees a CockpitError."""


def _minimal_env() -> dict[str, str]:
    env = {"PYTHONIOENCODING": "utf-8"}
    for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def run_organ(organ_dir: Path, module: str, view: dict, handlers: dict[str, Callable[[dict], Any]], *,
              wall_s: float, scratch: Path, entry: str = "run", python: str = sys.executable,
              max_stderr_bytes: int = MAX_STDERR_BYTES, memory_bytes: int = DEFAULT_MEMORY_BYTES) -> dict:
    """Run one organ entry point to completion, serving its cockpit requests.

    Returns ``{"ok": True, "result": ...}`` or ``{"ok": False, "error_type": ..., "error": ...}``.
    """
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="rs-organ-", dir=scratch))
    staged = stage / "organ"
    shutil.copytree(Path(organ_dir), staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    stderr_path = stage / "stderr.txt"
    started = time.monotonic()
    with open(stderr_path, "wb") as stderr:
        proc = subprocess.Popen([python, "-I", "-B", str(CHILD_FILE)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=stderr, cwd=str(staged), env=_minimal_env(),
                                preexec_fn=posix_preexec(memory_bytes, max_stderr_bytes))
    # OS limits under the audit hook: no child processes and a memory cap. The child waits for the init line
    # before running any organ code, so it is inside the job before the organ can act.
    job = windows_job(proc, memory_bytes)
    os_limits = "job" if job else ("rlimit" if os.name != "nt" else "unavailable")
    lines: "queue.Queue[bytes | None]" = queue.Queue()

    def pump() -> None:
        # Bounded reads: an organ that never sends a newline cannot make the host buffer without limit.
        assert proc.stdout is not None
        while True:
            raw = proc.stdout.readline(MAX_LINE_BYTES + 1)
            if not raw:
                break
            lines.put(raw)
            if len(raw) > MAX_LINE_BYTES:
                break
        lines.put(None)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()

    def send(message: dict) -> None:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(message, ensure_ascii=True) + "\n").encode("ascii"))
        proc.stdin.flush()

    def flooded() -> bool:
        # At the cap, not only over it: on POSIX, RLIMIT_FSIZE stops the file exactly at the cap.
        return stderr_path.exists() and stderr_path.stat().st_size >= max_stderr_bytes

    flood = {"ok": False, "error_type": "OutputFlood", "error": f"organ wrote {max_stderr_bytes} bytes or more to stderr"}
    outcome: dict[str, Any]
    try:
        send({"organ_dir": str(staged), "module": module, "entry": entry, "view": view,
              "grants": sorted(handlers)})
        while True:
            remaining = wall_s - (time.monotonic() - started)
            if remaining <= 0:
                outcome = {"ok": False, "error_type": "Timeout", "error": f"organ exceeded {wall_s:.0f}s"}
                break
            try:
                raw = lines.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                raw = b""
            if flooded():
                outcome = flood
                break
            if raw == b"":
                continue
            if raw is None:
                outcome = {"ok": False, "error_type": "ChildExited", "error": f"exit code {proc.poll()}"}
                break
            if len(raw) > MAX_LINE_BYTES:
                outcome = {"ok": False, "error_type": "OutputTooLarge", "error": "protocol line over 8 MB"}
                break
            try:
                message = json.loads(raw.decode("ascii"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                outcome = {"ok": False, "error_type": "ProtocolError", "error": raw[:200].decode("ascii", "replace")}
                break
            if "final" in message:
                outcome = {"ok": True, "result": message["final"]}
                break
            if "fatal" in message:
                fatal = message["fatal"] if isinstance(message["fatal"], dict) else {}
                outcome = {"ok": False, "error_type": str(fatal.get("type", "OrganError")),
                           "error": str(fatal.get("error", ""))[:1000], "trace": str(fatal.get("trace", ""))[-2000:]}
                break
            name, request_id = message.get("rpc"), message.get("id")
            handler = handlers.get(name) if isinstance(name, str) else None
            if handler is None:
                send({"id": request_id, "error": f"affordance {name!r} is not granted"})
                continue
            try:
                result = handler(message.get("args") or {})
            except RequestRefused as refusal:
                send({"id": request_id, "error": str(refusal)[:1000]})
                continue
            send({"id": request_id, "result": result})
        if not outcome["ok"] and outcome["error_type"] != "Timeout" and flooded():
            outcome = flood     # on POSIX the organ dies of EFBIG at the cap before the next poll: same verdict everywhere
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        for stream in (proc.stdin, proc.stdout):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass
        close_job(job)
        stderr_tail = stderr_path.read_bytes()[-3000:].decode("utf-8", "replace") if stderr_path.exists() else ""
        shutil.rmtree(stage, ignore_errors=True)
    outcome["elapsed_s"] = round(time.monotonic() - started, 3)
    outcome["os_limits"] = os_limits
    if stderr_tail:
        outcome["stderr_tail"] = stderr_tail
    return outcome
