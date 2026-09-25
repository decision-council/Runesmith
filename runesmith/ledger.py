"""Append-only, hash-chained event ledger (JSON Lines).

Every record binds the digest of its predecessor, so any edit, deletion or
reordering of history is detectable by :meth:`Ledger.verify`. The ledger is the
authoritative record; maps, summaries and dashboards are rebuildable
projections over it. Missing, censored and zero stay distinct because the
ledger stores what happened, not a score.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from runesmith.canon import canonical, digest

GENESIS = "sha256:" + "0" * 64
_PATH_LOCKS: dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(str(Path(path).resolve()))
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.Lock())


@contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    """Hold an OS-level lock on ``<ledger>.lock``, so separate processes append one at a time.

    The operating system releases the lock if the holder dies, so a crash never leaves it stuck.
    """
    with open(str(path) + ".lock", "a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.01)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class LedgerCorrupt(RuntimeError):
    """The chain does not verify; history must not be extended silently."""


class Ledger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq, self._head = self._load_tail()

    def _load_tail(self) -> tuple[int, str]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return 0, GENESIS
        last = None
        with open(self.path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            block = min(size, 1 << 16)
            while True:
                stream.seek(size - block)
                lines = stream.read(block).splitlines()
                complete = [line for line in lines if line.strip()]
                if len(complete) >= 2 or block == size:
                    last = complete[-1] if complete else None
                    break
                block = min(size, block * 2)
        if last is None:
            return 0, GENESIS
        try:
            record = json.loads(last)
        except json.JSONDecodeError as error:
            raise LedgerCorrupt(f"last ledger line is not JSON: {error}") from error
        return int(record["seq"]), str(record["hash"])

    @property
    def head(self) -> str:
        return self._head

    def append(self, kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if not kind or not isinstance(kind, str):
            raise ValueError("event kind must be a non-empty string")
        # Several Ledger objects (threads, the loop and its callers, other processes) may share one file, so
        # every append chains onto the file's real tail under a per-path and an OS-level lock, never onto a
        # tail cached when this object was made.
        with self._lock, _path_lock(self.path), _exclusive(self.path):
            self._seq, self._head = self._load_tail()
            body = {"seq": self._seq + 1, "utc": utc_now(), "kind": kind,
                    "data": data or {}, "prev": self._head}
            record = dict(body, hash=digest(body))
            line = canonical(record) + "\n"
            with open(self.path, "a", encoding="ascii", newline="\n") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            self._seq, self._head = body["seq"], record["hash"]
            return record

    def __iter__(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="ascii") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)

    def events(self, *kinds: str) -> Iterator[dict[str, Any]]:
        wanted = set(kinds)
        for record in self:
            if not wanted or record["kind"] in wanted or any(
                    record["kind"].startswith(k[:-1]) for k in wanted if k.endswith("*")):
                yield record

    def verify(self) -> dict[str, Any]:
        """Recompute every link. Returns a report; never repairs anything."""
        prev, count = GENESIS, 0
        for count, record in enumerate(self, start=1):
            body = {key: record[key] for key in ("seq", "utc", "kind", "data", "prev")}
            if record["seq"] != count:
                return {"ok": False, "records": count, "error": f"sequence gap at record {count}"}
            if record["prev"] != prev:
                return {"ok": False, "records": count, "error": f"broken link at seq {count}"}
            if digest(body) != record["hash"]:
                return {"ok": False, "records": count, "error": f"content changed at seq {count}"}
            prev = record["hash"]
        return {"ok": True, "records": count, "head": prev}
