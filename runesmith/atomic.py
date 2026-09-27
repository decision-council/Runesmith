"""Atomic file replacement that survives a reader on Windows.

Runesmith saves state by writing a temporary file and replacing the target with it. On Windows the replacement fails
with a sharing violation (PermissionError, WinError 5 or 32) while another thread or process has the target open, for
example the Studio page reading a draft at the moment a build saves it. Readers hold these files only briefly, so a
short retry is enough. Elsewhere, and after the last try, the error is raised unchanged.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

ATTEMPTS = 40
STEP_S = 0.025
MAX_WAIT_S = 0.25


def replace(src: str | Path, dst: str | Path, *, attempts: int = ATTEMPTS) -> None:
    """``os.replace(src, dst)``, retried for a few seconds on a Windows sharing violation."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if os.name != "nt" or attempt == attempts - 1:
                raise
            time.sleep(min(STEP_S * (attempt + 1), MAX_WAIT_S))
