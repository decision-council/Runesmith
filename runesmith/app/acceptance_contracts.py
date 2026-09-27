"""Public acceptance expectations, separate from private executable fixtures.

Revisions invalidate verification, not the stable milestone's spent attempts.
The caller owns the Workspace instance lock, as with other Studio mutations.
"""
from __future__ import annotations

import hashlib
import json
import re

from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json


def expectations(ws, milestone_id):
    if not isinstance(milestone_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', milestone_id):
        raise WorkspaceError('Invalid milestone ID.')
    return _read_json(ws.home/'acceptance-contracts'/(milestone_id+'.json'), None)


_UNSET = object()


def publish_expectations(ws, milestone_id, criteria, reason, *, by='owner', interfaces=None, expected_digest=_UNSET):
    if milestone_id not in {m['id'] for m in (ws.plan() or {}).get('milestones', [])}:
        raise WorkspaceError('Unknown milestone.')
    if not isinstance(reason, str) or not reason.strip():
        raise WorkspaceError('A public requirement revision needs a reason.')
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 20:
        raise WorkspaceError('Provide 1–20 public acceptance criteria.')
    clean, seen = [], set()
    for row in criteria:
        if not isinstance(row, dict):
            raise WorkspaceError('Each criterion needs an ID and public description.')
        key, description = row.get('id'), row.get('description')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', key) or key in seen:
            raise WorkspaceError('Criterion IDs must be unique.')
        if not isinstance(description, str) or not description.strip() or len(description) > 1200:
            raise WorkspaceError('Each public description must contain 1–1200 characters.')
        seen.add(key); clean.append({'id': key, 'description': description.strip()})
    with ws._lock:
        old = expectations(ws, milestone_id)
        if expected_digest is not _UNSET and expected_digest != (old or {}).get('digest'):
            raise WorkspaceError('Public expectations changed; reload before publishing. Nothing overwritten.')
        from runesmith.app.public_interfaces import clean_interfaces
        declared = clean_interfaces(interfaces if interfaces is not None else (old or {}).get('interfaces', []), seen)
        row = {'milestone': milestone_id, 'version': (old or {}).get('version', 0)+1,
               'criteria': clean, 'reason': reason.strip()[:2000], 'by': by, 'utc': _now()}
        if declared or interfaces is not None or (old or {}).get('interfaces') is not None:
            row['interfaces'] = declared
        row['digest'] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
        _write_json(ws.home/'acceptance-contracts'/'history'/milestone_id/(str(row['version'])+'.json'), row)
        _write_json(ws.home/'acceptance-contracts'/(milestone_id+'.json'), row)
        ws.ledger.append('acceptance.expectations_published', row)
    return row


def expectation_digest(ws, milestone_id):
    return (expectations(ws, milestone_id) or {}).get('digest')


def public_check_feedback(check, contracts=()):
    """Map host-captured criterion IDs, never guess from fixture strings."""
    if not isinstance(check, dict):
        return {'status': 'not_run'}
    result = {k: check[k] for k in ('status', 'ran', 'skipped', 'failures', 'errors') if k in check}
    descriptions = {c['id']: c['description'] for contract in contracts if contract
                    for c in contract.get('criteria', [])}
    failures = []
    for row in check.get('failure_details', []):
        mapped = [key for key in row.get('criteria', []) if key in descriptions]
        failures.append({'criteria': mapped,
                         'expectations': [descriptions[key] for key in mapped],
                         'diagnosis': ('One or more named expectations failed; the assertion remains private.'
                                       if mapped else 'Failure not localized to a public criterion. Owner clarification needed.')})
    result['public_failures'] = failures
    return result


def owner_feedback(ws, verification):
    contracts = verification.get('public_contracts') or []
    # An old fixture has no criterion mapping. Do not invent one from its text.
    return public_check_feedback(verification.get('acceptance'), contracts)
