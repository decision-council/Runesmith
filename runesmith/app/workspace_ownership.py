"""Cooperating Studio/one-shot writers in one user profile, not a sandbox.

Shared ancestor leases plus an exclusive root lease exclude parent/child roots
without serializing siblings. The OS owns lease lifetime; lock files are never
deleted. Bindings are durable safety records, independent of optional recents.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from runesmith.app.workspace import WorkspaceError
from runesmith.app.worker_journal import Record, _safe_file


def canonical(path):
    return Path(path).expanduser().resolve()


def key(path):
    return os.path.normcase(str(canonical(path)))


def safe_control(path):
    # Include all ancestors: redirecting the coordination directory must not
    # silently split the population of cooperating writers.
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise WorkspaceError('Workspace ownership control path is redirected; inspect it before continuing.')
    _safe_file(path)


class FileLease:
    """Nonblocking shared/exclusive byte lease, including on Windows."""
    def __init__(self, path, *, exclusive=True):
        self.path, self.exclusive, self.handle = Path(path), exclusive, None
        self._overlapped = None

    def acquire(self):
        if self.handle is not None:
            raise WorkspaceError('Ownership lease is already held.')
        safe_control(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                import msvcrt
                class Overlapped(ctypes.Structure):
                    _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                                ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                                ('hEvent', wintypes.HANDLE)]
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                             wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
                kernel.LockFileEx.restype = wintypes.BOOL
                overlap = Overlapped()
                if not kernel.LockFileEx(msvcrt.get_osfhandle(handle.fileno()),
                                         1 | (2 if self.exclusive else 0), 0, 1, 0, ctypes.byref(overlap)):
                    error = ctypes.get_last_error()
                    if error == 33:  # ERROR_LOCK_VIOLATION; other failures are not contention.
                        handle.close()
                        return False
                    raise ctypes.WinError(error)
                self._overlapped = overlap
            else:
                import fcntl
                try:
                    fcntl.flock(handle.fileno(), (fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    return False
        except BaseException:
            handle.close()
            raise
        self.handle = handle
        return True

    def close(self):
        if self.handle is not None:
            # Closing releases all ranges held by this handle, also on failure
            # paths. No unlink: another process may already have this file open.
            self.handle.close()
            self.handle = None
            self._overlapped = None


class RootLease:
    def __init__(self, root, profile, *, home=None):
        self.root, self.profile, self.leases = canonical(root), Path(profile), []
        # A separate home is writable state too. Coalesce nested scopes so a
        # normal root/.runesmith home does not conflict with its own root lease.
        scopes = {self.root, canonical(home)} if home is not None else {self.root}
        self.scopes = {p for p in scopes if not any(q != p and q in p.parents for q in scopes)}

    def acquire(self):
        if self.leases:
            raise WorkspaceError('Source root lease is already held.')
        try:
            parts = {p for scope in self.scopes for p in (*scope.parents, scope)}
            for part in sorted(parts, key=lambda p: (len(p.parts), key(p))):
                name = hashlib.sha256(key(part).encode('utf-8')).hexdigest() + '.lock'
                lease = FileLease(self.profile / 'root-locks' / name, exclusive=part in self.scopes)
                if not lease.acquire():
                    self.close()
                    return False
                self.leases.append(lease)
            return True
        except BaseException:
            self.close()
            raise

    def close(self):
        for lease in reversed(self.leases):
            lease.close()
        self.leases.clear()


class Bindings:
    def __init__(self, profile):
        self.profile = Path(profile)
        self.path = self.profile / 'workspace-bindings.json'

    def _read(self):
        safe_control(self.path)
        record = Record(self.path)
        if record.value is None:
            return record, []
        data = record.value
        if (not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1
                or not isinstance(data.get('bindings'), list) or len(data['bindings']) > 1000):
            raise WorkspaceError('Invalid workspace bindings; no default home will be substituted.')
        roots, homes = set(), set()
        for row in data['bindings']:
            if not isinstance(row, dict) or set(row) != {'root', 'home'}:
                raise WorkspaceError('Invalid workspace binding; inspect the saved record.')
            for field in ('root', 'home'):
                value = row[field]
                if (not isinstance(value, str) or not value.strip() or not Path(value).is_absolute()
                        or str(canonical(value)) != value):
                    raise WorkspaceError('Invalid or redirected workspace binding; inspect the saved record.')
            r, h = key(row['root']), key(row['home'])
            if r in roots or h in homes:
                raise WorkspaceError('Conflicting workspace bindings; inspect the saved record.')
            roots.add(r); homes.add(h)
        return record, data['bindings']

    def resolve(self, root, home=None):
        root = canonical(root)
        _record, rows = self._read()
        saved = next((row for row in rows if key(row['root']) == key(root)), None)
        if saved:
            destination = Path(saved['home'])
            if home is not None and key(home) != key(destination):
                raise WorkspaceError('This root is bound to a different home; automatic rebinding is not allowed.')
            if not destination.is_dir():
                raise WorkspaceError('The registered home is missing or unavailable; restore it before opening this root.')
        else:
            destination = canonical(home) if home is not None else root / '.runesmith'
        if any(key(row['home']) == key(destination) and key(row['root']) != key(root) for row in rows):
            raise WorkspaceError('This home is already bound to a different source root.')
        return {'path': str(root), 'home': str(destination),
                'basis': 'registered' if saved else ('explicit' if home is not None else 'default'),
                'registered': bool(saved)}

    def remember(self, root, home):
        """Called under both root and home leases, before Workspace mutates."""
        lock = FileLease(self.profile / 'workspace-bindings.lock')
        if not lock.acquire():
            raise WorkspaceError('Workspace bindings are being updated; no workspace was initialized. Review and try again.')
        try:
            pair = self.resolve(root, home)  # Recheck after acquiring the registry lock.
            record, rows = self._read()
            if not pair['registered']:
                if len(rows) >= 1000:
                    raise WorkspaceError('Workspace binding limit reached; no records were discarded.')
                record.write({'version': 1, 'bindings': rows + [{'root': pair['path'], 'home': pair['home']}]})
        finally:
            lock.close()
