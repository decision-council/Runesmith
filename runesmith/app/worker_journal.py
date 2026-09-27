"""Small, fail-closed control records for the single-writer Studio worker.

These records preserve intent across process restarts; they are not an exactly-once
guarantee for external services. A current marker always precedes dispatch.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path

from runesmith.app.workspace import WorkspaceError

MAX_BYTES = 2_000_000
MAX_JOBS = 100


def _safe_file(path):
    # Never follow a redirected control record, including Windows junctions.
    for item in (path, path.parent):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise WorkspaceError(f'{path.name} is redirected; inspect recovery records before continuing.')
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise WorkspaceError(f'{path.name} is not a regular control file.')


def _read(path):
    _safe_file(path)
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None, None
    if len(raw) > MAX_BYTES:
        raise WorkspaceError(f'{path.name} exceeds the recovery record limit; nothing discarded.')
    try:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate control key')
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique_pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        if value is None:
            raise ValueError('null is not an absent control record')
    except (ValueError, UnicodeError) as error:
        raise WorkspaceError(f'{path.name} is unreadable; inspect it before recovery.') from error
    return value, hashlib.sha256(raw).hexdigest()


def atomic_write(path, value):
    """Flush a complete replacement before rename; no in-place truncation."""
    path = Path(path)
    _safe_file(path)
    data = (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=1) + '\n').encode('utf-8')
    if len(data) > MAX_BYTES:
        raise WorkspaceError(f'{path.name} exceeds the recovery record limit.')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class Record:
    """Fingerprint checks supplement (not replace) the home's OS writer lock."""
    def __init__(self, path):
        self.path = Path(path)
        self.value, self.digest = _read(self.path)

    def check(self):
        _value, digest = _read(self.path)
        if digest != self.digest:
            raise WorkspaceError(f'{self.path.name} changed outside this worker; reload and review recovery.')

    def write(self, value):
        self.check()
        atomic_write(self.path, value)
        self.value, self.digest = _read(self.path)

    def remove(self):
        self.check()
        self.path.unlink(missing_ok=True)
        self.value, self.digest = None, None


def validate_job(job):
    if not isinstance(job, dict) or not isinstance(job.get('id'), str) or not job['id'] or len(job['id']) > 128:
        raise WorkspaceError('Invalid saved job identity; inspect recovery records.')
    kind, params = job.get('kind'), job.get('params', {})
    if not isinstance(kind, str) or not isinstance(params, dict):
        raise WorkspaceError('Invalid saved job parameters; inspect recovery records.')
    from runesmith.app.build_jobs import BuildJob, PARAMETERS
    if kind in PARAMETERS:
        BuildJob(kind, params)
    else:
        allowed = {'map': {'probe'}, 'round': set(), 'plan': set(), 'goalposts': set(), 'health': set(),
                   'draft': {'milestone'}, 'breakdown': {'milestone'}, 'mode': {'mode'}, 'measure': {'measurement'}}
        if kind not in allowed or set(params) - allowed[kind]:
            raise WorkspaceError('Invalid saved job kind or parameters; inspect recovery records.')
        for name, value in params.items():
            if name == 'probe':
                valid = value is None or type(value) is bool
            else:
                valid = value is None and kind == 'draft' or isinstance(value, str) and 0 < len(value) <= 128
            if not valid:
                raise WorkspaceError('Invalid saved job parameter value; inspect recovery records.')
        if kind in {'breakdown', 'mode', 'measure'} and set(params) != allowed[kind]:
            raise WorkspaceError('Missing saved job parameter; inspect recovery records.')
    return job


def validate_queue(value, root):
    if value is None:
        return [], None
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('root') != str(root)):
        raise WorkspaceError('STUDIO_QUEUE.json has an unknown format or workspace binding; nothing replayed.')
    jobs, recovery = value.get('jobs'), value.get('recovery')
    if not isinstance(jobs, list) or len(jobs) > MAX_JOBS:
        raise WorkspaceError('STUDIO_QUEUE.json has an invalid queue; nothing discarded.')
    for job in jobs:
        validate_job(job)
    if len({job['id'] for job in jobs}) != len(jobs):
        raise WorkspaceError('STUDIO_QUEUE.json repeats a job identity; nothing replayed.')
    if recovery is not None and (not isinstance(recovery, dict) or
            not isinstance(recovery.get('revision'), str) or len(recovery['revision']) != 32 or
            any(c not in '0123456789abcdef' for c in recovery['revision']) or
            not isinstance(recovery.get('reasons'), list) or
            not all(isinstance(reason, str) for reason in recovery['reasons'])):
        raise WorkspaceError('STUDIO_QUEUE.json has an invalid recovery hold.')
    return jobs, recovery
