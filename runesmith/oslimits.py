"""Operating-system limits for organ processes: a second barrier under the audit hook.

The audit hook in ``organ_child.py`` is defense in depth, not a hardened boundary (PEP 578).
These limits are enforced by the operating system, so they hold even if hostile code
bypasses the hook:

* **Windows.** The organ process is placed in a Job Object that allows exactly one active
  process (no children) and caps its memory; closing the job kills the process.
* **POSIX.** Before ``exec``, ``setrlimit`` caps the address space, forbids new processes
  (``RLIMIT_NPROC`` 0) and caps the size of any file the process writes (its stderr log).

File reads and network access are still governed by the audit hook alone. An OS sandbox
(a container, a VM, AppContainer or seccomp) is the right tool for code you do not trust.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Callable

DEFAULT_MEMORY_BYTES = 2 * 1024 ** 3


def posix_preexec(memory_bytes: int, max_file_bytes: int) -> Callable[[], None] | None:
    """A ``preexec_fn`` that applies rlimits in the child, or None where they do not exist."""
    if os.name == "nt":
        return None
    import resource

    def apply() -> None:
        for limit, value in ((resource.RLIMIT_AS, memory_bytes), (resource.RLIMIT_FSIZE, max_file_bytes),
                             (getattr(resource, "RLIMIT_NPROC", None), 0)):
            if limit is None:
                continue
            try:
                resource.setrlimit(limit, (value, value))
            except (ValueError, OSError):
                pass
    return apply


def windows_job(proc: subprocess.Popen, memory_bytes: int) -> Any:
    """Assign ``proc`` to a new Job Object with a memory cap and no child processes.

    Returns the job handle; keep it alive for the life of the process and pass it to
    :func:`close_job` afterwards. Returns None if the job could not be created or assigned.
    """
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    active_process, process_memory, die_on_exception, kill_on_close = 0x8, 0x100, 0x400, 0x2000
    extended_limit_information = 9
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = active_process | process_memory | die_on_exception | kill_on_close
    info.BasicLimitInformation.ActiveProcessLimit = 1
    info.ProcessMemoryLimit = memory_bytes
    ok = kernel32.SetInformationJobObject(job, extended_limit_information, ctypes.byref(info), ctypes.sizeof(info))
    ok = ok and kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle)))
    if not ok:
        kernel32.CloseHandle(job)
        return None
    return job


def close_job(job: Any) -> None:
    if job is None or os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle(job)
