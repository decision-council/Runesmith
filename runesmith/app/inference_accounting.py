"""Read-only, bounded accounting projection. Recovery never adds a second job.

Historical gateway identities remain in scope, even after an instrument/route
is changed or removed. This does not add legacy host totals to gateway totals.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from runesmith.canon import digest
from runesmith.inference_usage import qualify_usage

MAX_RECEIPTS = 100
MAX_RECEIPT_BYTES = 3_000_000
TERMINAL = ('terminal', 'refused')
STATES = (*TERMINAL, 'submitting', 'pending', 'remote_outcome_unknown', 'binding_mismatch')


def _linked(path):
    return any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
               for p in (path, *path.parents))


def _valid(record):
    if not isinstance(record, dict):
        return False
    if (not isinstance(record.get('key'), str) or
            hashlib.sha256(record['key'].encode()).hexdigest() != record.get('id')):
        return False
    for field in ('origin', 'caller', 'instrument'):
        if not isinstance(record.get(field), str) or not 0 < len(record[field]) <= 1000:
            return False
    if (record.get('state') not in STATES or not isinstance(record.get('body'), dict)
            or digest(record['body']) != record.get('body_digest')):
        return False
    job = record.get('job_id')
    if job is not None and (not isinstance(job, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', job)):
        return False
    if record['state'] in TERMINAL:
        payload = record.get('payload')
        if not isinstance(payload, dict) or digest(payload) != record.get('payload_digest'):
            return False
        if record['state'] == 'terminal':
            if (not job or payload.get('job_id') != job or not isinstance(record.get('authenticated_agent'), str)
                    or not 0 < len(record['authenticated_agent']) <= 1000
                    or payload.get('agent') != record['authenticated_agent']
                    or payload.get('state') not in ('succeeded', 'failed', 'cancelled', 'rejected', 'expired')):
                return False
    return True


def accounting_view(home):
    home = Path(home)
    coverage = {'scanned': 0, 'valid': 0, 'invalid': 0, 'omitted': 0, 'duplicates': 0}
    paths, observed, groups = [], [], {}
    directory = home / 'inference-requests'
    try:
        if _linked(directory):
            raise ValueError('Linked receipt directory')
        for path in directory.glob('*.json'):
            try:
                if _linked(path):
                    raise ValueError('Linked receipt')
                stat = path.stat()
                paths.append((stat.st_mtime_ns, path.name, path))
            except (OSError, ValueError):
                coverage['invalid'] += 1
    except (OSError, ValueError):
        coverage['invalid'] += 1
    paths.sort(reverse=True)
    coverage['omitted'] = max(0, len(paths) - MAX_RECEIPTS)
    for _, _, path in paths[:MAX_RECEIPTS]:
        coverage['scanned'] += 1
        try:
            with path.open('rb') as stream:
                raw = stream.read(MAX_RECEIPT_BYTES + 1)
            if len(raw) > MAX_RECEIPT_BYTES:
                raise ValueError('Oversized receipt')
            record = json.loads(raw)
            if not _valid(record):
                raise ValueError('Invalid receipt')
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            coverage['invalid'] += 1
            continue
        coverage['valid'] += 1
        observed.append(record)
    # Union only exact request-ID and bound-ticket aliases in one gateway/caller
    # namespace. A pre-ticket copy of this request is not a second unknown POST.
    # Equal prompt/body bytes alone never establish an alias.
    parents = {}
    def root(node):
        parents.setdefault(node, node)
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node
    def request_node(record):
        return (record['origin'], record['caller'], 'request', record['id'])
    for record in observed:
        request = root(request_node(record))
        if record.get('job_id'):
            ticket = root((record['origin'], record['caller'], 'ticket', record['job_id']))
            parents[max(request, ticket)] = min(request, ticket)
    for record in observed:
        groups.setdefault(root(request_node(record)), []).append(record)
    rows = []
    for identity, records in groups.items():
        coverage['duplicates'] += len(records) - 1
        terminal = [r for r in records if r['state'] in TERMINAL]
        tickets = sorted({r['job_id'] for r in records if r.get('job_id')})
        conflict = (len(tickets) > 1 or len({(r['body_digest'], r['instrument']) for r in records}) != 1
            or len({r.get('authenticated_agent') for r in records if isinstance(r.get('authenticated_agent'), str)}) > 1
            or any(r['state'] == 'binding_mismatch' for r in records)
            or len({r['payload_digest'] for r in terminal}) > 1)
        record = terminal[0] if terminal else records[0]
        state = 'conflicting' if conflict else record['state']
        payload = record.get('payload', {})
        usage = qualify_usage(payload.get('meta')) if state in TERMINAL else qualify_usage(None)
        rows.append({'id': digest(identity), 'instrument': record['instrument'],
            'job_id': tickets[0] if len(tickets) == 1 else None, 'job_ids': tickets, 'state': state,
            'outcome': payload.get('state') if state == 'terminal' else None,
            'usage': usage})
    costs = [r['usage']['est_usd'] for r in rows if r['usage']['est_usd'] is not None]
    summary = {'requests': len(rows), 'terminal': sum(r['state'] in TERMINAL for r in rows),
        'unresolved': sum(r['state'] not in TERMINAL for r in rows),
        'costed_requests': len(costs), 'estimated_usd': sum(costs) if costs else None,
        'attempt_reconciled_requests': sum(r['usage']['cost_status'] == 'reported_attempt_reconciled' for r in rows),
        'aggregate_only_requests': sum(r['usage']['cost_status'] == 'reported_aggregate_only' for r in rows),
        'token_complete_requests': sum(r['usage']['tokens_in'] is not None and
            r['usage']['tokens_out'] is not None for r in rows)}
    return {'summary': summary, 'coverage': coverage, 'requests': rows, 'inference_calls': 0,
        'scope': 'Retained gateway receipts in this home, including historical routes. Each bound ticket is counted once. Refresh reads files only; it does not retrieve tickets or call a model.',
        'caution': 'Subtotal of included reported estimates, not a bill, remaining credit or complete spend. Attempt-reconciled means aggregate tokens match retained attempts; aggregate-only lacks that cross-check. Missing, inconsistent, unresolved and omitted costs stay unknown. Cached metadata is not assigned as fresh usage/cost. Never add this subtotal to legacy host-call estimates. No current prices are applied retrospectively.'}
