"""Saved keys: API keys and tokens kept on this machine, never in the configuration.

Keys live in ``<home>/secrets.json``. On POSIX the file is readable by its owner
only; on Windows it inherits the user profile's permissions, and the home ignores
itself for version control. A key is written once and read only by the instrument
that needs it, at call time. Nothing here returns a key to a caller that asked for
a listing: ``names()`` and ``describe()`` say which keys exist, never what they are.

The configuration refers to a saved key by name::

    {"kind": "openai", "base_url": "https://openrouter.ai/api/v1", "model": "...",
     "api_key_secret": "openrouter"}
"""

from __future__ import annotations

import json
import os
import re
import stat
import threading
import time
from pathlib import Path
from typing import Callable
from runesmith import atomic

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_lock = threading.Lock()


class KeyStore:
    def __init__(self, home: Path) -> None:
        self.path = Path(home) / "secrets.json"

    def _read(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_bytes((json.dumps(data, indent=1, sort_keys=True) + "\n").encode("utf-8"))
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:                                    # Windows: owner-only is the profile's default
            pass
        atomic.replace(tmp, self.path)

    def set(self, name: str, value: str) -> None:
        if not _NAME.match(name or ""):
            raise ValueError("a key name uses letters, digits, '.', '_' or '-' (at most 64)")
        value = (value or "").strip()
        if not value:
            raise ValueError("an empty key cannot be saved")
        with _lock:
            data = self._read()
            data[name] = {"value": value, "saved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            self._write(data)

    def delete(self, name: str) -> bool:
        with _lock:
            data = self._read()
            if name not in data:
                return False
            del data[name]
            self._write(data)
            return True

    def has(self, name: str) -> bool:
        return name in self._read()

    def names(self) -> list[str]:
        return sorted(self._read())

    def describe(self) -> list[dict[str, str]]:
        """What the interface may show: names and when they were saved. Never the values."""
        return [{"name": n, "saved_utc": row.get("saved_utc", "")} for n, row in sorted(self._read().items())]

    def supplier(self, name: str) -> Callable[[], str]:
        """A callable that reads the key at the moment it is needed (so a later change takes effect)."""
        def supply() -> str:
            return str(self._read().get(name, {}).get("value") or "")
        return supply
