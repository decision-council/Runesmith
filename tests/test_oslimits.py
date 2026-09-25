"""OS-level limits under the audit hook: they hold even for code that the hook never sees."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from runesmith.oslimits import close_job, windows_job
from runesmith.sandbox import run_organ

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Objects")


def _run_limited(code: str, memory_bytes: int) -> subprocess.CompletedProcess:
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    job = windows_job(proc, memory_bytes)
    try:
        out, err = proc.communicate(timeout=60)
    finally:
        close_job(job)
    assert job is not None
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


@windows_only
def test_job_forbids_child_processes():
    # The sleep lets the job be assigned first, as run_organ does before sending the init line.
    done = _run_limited("import time, subprocess, sys; time.sleep(1.5); "
                        "subprocess.run([sys.executable, '-c', 'pass']); print('SPAWNED')", 256 * 1024 ** 2)
    assert "SPAWNED" not in done.stdout and done.returncode != 0


@windows_only
def test_job_caps_memory():
    done = _run_limited("import time; time.sleep(1.5); b = bytearray(600 * 1024 ** 2); print('ALLOCATED')",
                        200 * 1024 ** 2)
    assert "ALLOCATED" not in done.stdout and "MemoryError" in done.stderr


def test_sandboxed_organ_cannot_exhaust_memory(tmp_path):
    organ_dir = tmp_path / "organ"
    organ_dir.mkdir()
    (organ_dir / "probe.py").write_text(textwrap.dedent('''
        def run(view, cockpit):
            hoard = bytearray(700 * 1024 * 1024)
            return {"status": "hoarded", "size": len(hoard)}
    '''), encoding="utf-8")
    outcome = run_organ(organ_dir, "probe", {}, {}, wall_s=60, scratch=tmp_path / "scratch",
                        memory_bytes=250 * 1024 ** 2)
    assert outcome["ok"] is False and outcome["error_type"] == "MemoryError", outcome
    if sys.platform == "win32":
        assert outcome["os_limits"] == "job"
