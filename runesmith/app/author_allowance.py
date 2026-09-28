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

from runesmith.app.workspace import WorkspaceError

LIMIT = 3


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


def _records(ws, folder):
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
        if row.get('state') == 'transport_failed':
            continue                    # no model answered: nothing used up, nothing to reconcile (J2-B9)
        states = {'answered', 'failed', 'recovered'} if folder == 'build-escalations' else {'answered', 'failed'}
        if row.get('state') not in states:
            raise WorkspaceError(f'Unresolved author allowance receipt {folder}/{path.name}; reconcile it before another call.')
        result.append((path.name, row))
    return result


def ordinary_allowance(ws, contract, snapshot):
    """Count all proven aliases; refuse ambiguous/damaged/unresolved evidence."""
    if not _hash(contract) or not _hash(snapshot):
        raise WorkspaceError('Author allowance needs a valid frozen source and milestone contract.')
    scope = _digest({'kind': 'ordinary-author-v2', 'contract': contract, 'snapshot_digest': snapshot})
    boundary = (contract, snapshot)
    bindings = {scope: boundary}; attempts = []
    records = _records(ws, 'build-attempts')
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
    for name, row in _records(ws, 'build-escalations'):
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
