"""Read-only accounting across ordinary builds and focused author revisions.

Legacy note-derived scopes are aliases only when their stored contract/source
prove the same boundary. No receipts are migrated, counters reset or missing
lineage reconstructed. Callers still own the home lock and dispatch gates.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from contextlib import contextmanager

from runesmith.app.workspace import WorkspaceError

LIMIT = 3

# A one more try's receipt is settled in one of these; 'transport_failed' and 'context_gap' used nothing up (below).
ESCALATION_SETTLED = frozenset({'answered', 'failed', 'recovered'})
NOTHING_USED = frozenset({'transport_failed', 'context_gap'})


class UnresolvedAllowance(WorkspaceError):
    """A receipt of the milestone's own that no one settled: a call that started and left no outcome. `folder` and `name`
    say which receipt, so the caller can tell a one more try (reconciled by `close_interrupted_escalations`) from an
    ordinary try. Raised with the same words as ever."""

    def __init__(self, folder, name, state=None):
        super().__init__(f'Unresolved author allowance receipt {folder}/{name}; reconcile it before another call.')
        self.folder, self.name, self.receipt_state = folder, name, state


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate key')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('Nonfinite number')


def _float(value):
    number = float(value)
    if not math.isfinite(number): raise ValueError('Nonfinite number')
    return number


_SHARED = threading.local()


@contextmanager
def shared_reads():
    """Everything evaluated inside reads each receipt folder once. A scheduling decision judges every ready milestone, and
    each judgement re-read and re-parsed every receipt: 6,500 reads for 29 ready milestones and 223 attempts on J11's
    home, 13 to 39 s of a worker that holds its lock meanwhile (review of batch EE). Only for a decision that writes
    nothing; per thread."""
    outer = getattr(_SHARED, 'folders', None)
    if outer is None:
        _SHARED.folders = {}
    try:
        yield
    finally:
        if outer is None:
            _SHARED.folders = None


def _load(ws, folder):
    """Every receipt of a folder, parsed and checked for damage (the contract-independent part of `_records`)."""
    shared = getattr(_SHARED, 'folders', None)
    key = str(ws.home / folder)
    if shared is not None and key in shared:
        value = shared[key]
        if isinstance(value, WorkspaceError):
            raise WorkspaceError(str(value)) from None
        return value
    try:
        value = _read_folder(ws, folder)
    except WorkspaceError as error:
        if shared is not None:
            shared[key] = error
        raise
    if shared is not None:
        shared[key] = value
    return value


def _read_folder(ws, folder):
    directory = ws.home / folder
    try:
        directory.lstat()
    except FileNotFoundError:
        return []
    except OSError:
        raise WorkspaceError('Author allowance directory is unreadable; reconcile it first.') from None
    if directory.resolve() != directory.absolute() or (directory.exists() and not directory.is_dir()):
        raise WorkspaceError('Author allowance directory is redirected or damaged; reconcile it first.')
    try:
        # Path.glob may suppress directory I/O errors. Unreadable is not empty.
        paths = sorted(path for path in directory.iterdir() if path.suffix.lower() == '.json')
    except OSError:
        raise WorkspaceError('Author allowance directory is unreadable; reconcile it first.') from None
    result = []
    for path in paths:
        try:
            if path.is_symlink() or path.resolve().parent != directory.resolve() or path.stat().st_size > 2_000_000:
                raise ValueError('Unsafe or oversized receipt')
            row = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique, parse_constant=_nonfinite, parse_float=_float)
            if not isinstance(row, dict) or not _hash(row.get('contract')) or not _hash(row.get('scope')):
                raise ValueError('Missing allocation identity')
        except (OSError, ValueError, RecursionError):
            raise WorkspaceError(f'Damaged author allowance receipt {folder}/{path.name}; reconcile it first.') from None
        result.append((path.name, row))
    return result


def _records(ws, folder, contract=None):
    result = []
    for name, row in _load(ws, folder):
        if row.get('state') in NOTHING_USED:
            # No model answered (J2-B9), or it answered for a file it was never shown (J11-B15): nothing used up.
            continue
        states = ESCALATION_SETTLED if folder == 'build-escalations' else {'answered', 'failed'}
        if row.get('state') not in states:
            # An unresolved call blocks its own milestone's allowance, not every milestone's (journey J11-B6). It is
            # still listed, so the scope checks below see it; damaged receipts above still block everything.
            if contract is None or row.get('contract') == contract:
                raise UnresolvedAllowance(folder, name, row.get('state'))
        result.append((name, row))
    return result


def unresolved_escalations(ws, contract=None):
    """The one more try receipts that were started and never settled, as (file name, receipt) pairs: of this milestone
    contract only when one is given. An unreadable folder raises, as everywhere here."""
    return [(name, row) for name, row in _load(ws, 'build-escalations')
            if row.get('state') not in NOTHING_USED and row.get('state') not in ESCALATION_SETTLED
            and (contract is None or row.get('contract') == contract)]


def ordinary_allowance(ws, contract, snapshot):
    """Count all proven aliases; refuse ambiguous/damaged/unresolved evidence."""
    if not _hash(contract) or not _hash(snapshot):
        raise WorkspaceError('Author allowance needs a valid frozen source and milestone contract.')
    scope = _digest({'kind': 'ordinary-author-v2', 'contract': contract, 'snapshot_digest': snapshot})
    boundary = (contract, snapshot)
    bindings = {scope: boundary}; attempts = []
    records = _records(ws, 'build-attempts', contract=contract)
    for name, row in records:
        source = row.get('snapshot_digest')
        if not _hash(source):
            if row['contract'] == contract or row['scope'] == scope:
                raise WorkspaceError('Legacy ordinary attempt has no proven source snapshot; no new budget granted.')
            continue  # Settled, different contract: cannot belong to this boundary.
        pair = (row['contract'], source)
        if row['scope'] in bindings and bindings[row['scope']] != pair:
            raise WorkspaceError('Conflicting ordinary allowance scope evidence; reconcile it first.')
        bindings[row['scope']] = pair
        if pair == boundary:
            attempts.append({'id': name, 'state': row['state'], 'digest': _digest(row)})
    aliases = sorted(key for key, pair in bindings.items() if pair == boundary)
    if any(row['scope'] in aliases and row['contract'] != contract for _, row in records):
        raise WorkspaceError('Conflicting ordinary allowance scope evidence; reconcile it first.')
    escalations = []
    for name, row in _records(ws, 'build-escalations', contract=contract):
        pair = (row['contract'], row.get('snapshot_digest')) if _hash(row.get('snapshot_digest')) else bindings.get(row['scope'])
        if pair and (pair[0] != row['contract'] or (row['scope'] in bindings and bindings[row['scope']] != pair)):
            raise WorkspaceError('Conflicting alternate-author source evidence; reconcile it first.')
        if pair is None and row['contract'] == contract:
            raise WorkspaceError('Legacy alternate-author receipt has no proven source snapshot; no new call granted.')
        if pair == boundary:
            escalations.append({'id': row.get('id') or name[:-5], 'state': row['state'], 'digest': _digest(row)})
    return {'scope': scope, 'scope_aliases': aliases, 'contract': contract, 'snapshot_digest': snapshot,
            'limit': LIMIT, 'used': len(attempts), 'remaining': max(0, LIMIT - len(attempts)),
            'attempts': attempts, 'escalations': escalations}
