"""Bounded, read-only projection of retained gateway evidence, never a probe.

A configured key, a past success and an elapsed cooldown are not availability
guarantees. Do not return prompts, replies, raw errors, credentials or endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
import time

from runesmith.canon import digest
from runesmith.app.workspace import WorkspaceError, _read_json

MAX_RECEIPTS = 100
MAX_RECEIPT_BYTES = 3_000_000


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _stamp(value):
    try:
        if isinstance(value, str):
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None:
                return None
            value = date.timestamp()
        if _number(value) and 0 <= value <= 253402300799:
            return float(value)
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def availability_view(ws, name, *, now=None):
    spec = ws.config()['instruments'].get(name)
    if not spec:
        raise KeyError(name)
    if spec.get('kind') != 'milliner':
        raise WorkspaceError('Recorded gateway availability is for Milliner instruments.')
    now = time.time() if now is None else now
    names = list(dict.fromkeys([spec.get('model', ''), *(spec.get('fallback_models') or [])]))
    rows = {model:{'model':model, 'status':'unknown', 'detail':'No matching retained outcome in the scanned receipts.'} for model in names}
    # Bound reads and response size; mtime selects the window, not the latest
    # outcome. Outcome time comes from the retained terminal gateway payload.
    paths = []
    unreadable = 0
    for path in (ws.home/'inference-requests').glob('*.json'):
        try:
            if path.is_symlink():
                unreadable += 1
                continue
            stat = path.stat()
            paths.append((stat.st_mtime_ns, path.name, stat.st_size, path))
        except OSError:
            unreadable += 1
    paths.sort(reverse=True)
    scanned = paths[:MAX_RECEIPTS]
    matched = 0
    unresolved = 0
    latest = {}
    for _, _, size, path in scanned:
        if size > MAX_RECEIPT_BYTES:
            unreadable += 1
            continue
        record = _read_json(path, None)
        if not isinstance(record, dict):
            unreadable += 1
            continue
        if (record.get('instrument') != name or record.get('origin') != spec.get('base_url', '').rstrip('/')
                or record.get('caller') != spec.get('caller_tag', 'runesmith')):
            continue
        matched += 1
        if record.get('state') not in ('terminal', 'refused'):
            unresolved += 1
            continue
        payload = record.get('payload')
        body = record.get('body')
        try:
            consistent = (isinstance(payload, dict) and isinstance(body, dict)
                          and digest(payload) == record.get('payload_digest') and digest(body) == record.get('body_digest'))
        except (TypeError, ValueError):
            consistent = False
        if not consistent:
            unreadable += 1
            continue
        observed = _stamp(payload.get('finished_at'))
        if observed is None:
            observed = _stamp(record.get('updated')) or _stamp(record.get('created'))
        if observed is None or observed > now:
            unreadable += 1
            continue
        meta = payload.get('meta')
        attempts = meta.get('attempts', []) if isinstance(meta, dict) else []
        if not isinstance(attempts, list):
            unreadable += 1
            continue
        for attempt in attempts[:32]:
            if not isinstance(attempt, dict):
                continue
            model = str(attempt.get('provider', '')) + ':' + str(attempt.get('model', ''))
            if model not in rows or observed < latest.get(model, -1):
                continue
            latest[model] = observed
            outcome = attempt.get('outcome')
            retry = attempt.get('retry_after_s')
            deadline = observed + retry if _number(retry) and 0 < retry <= 31_536_000 else None
            if outcome == 'ok':
                status, detail = 'past_success', 'This route answered then; current capacity and author quality are unverified.'
                deadline = None
            elif outcome in ('rate_limited', 'overloaded'):
                if deadline and deadline > now:
                    status, detail = 'cooldown_recorded', 'A retained gateway attempt reports a wait. Do not blindly retry.'
                elif deadline:
                    status, detail = 'cooldown_elapsed', 'The reported wait has elapsed; availability has not been rechecked.'
                else:
                    status, detail = 'capacity_failure', 'Capacity failed then; no usable retry time was reported.'
            elif outcome in ('no_credits', 'auth_failed', 'model_not_found'):
                status, detail = 'route_refused', 'The retained attempt reported a credit, authentication or model-access problem; no automatic retry is implied.'
                deadline = None
            else:
                status, detail = 'past_failure', 'A retained attempt failed; this alone does not establish a capacity limit.'
                deadline = None
            job_id = record.get('job_id')
            rows[model] = {'model':model, 'status':status, 'detail':detail, 'observed_at':_iso(observed),
                'outcome':outcome if outcome in ('ok','rate_limited','overloaded','timeout','auth_failed','no_credits','model_not_found','bad_request','truncated','schema_failed','transport','unknown') else 'other',
                'gateway_attempts':len(attempts),
                'retry_at':_iso(deadline) if deadline else None,
                'remaining_s':max(0, round(deadline-now)) if deadline else None,
                'job_id':job_id if isinstance(job_id,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',job_id) else None}
    return {'name':name, 'observed_at':_iso(now), 'routes':list(rows.values()),
        'unresolved_requests':unresolved,
        'coverage':{'scanned':len(scanned), 'matching':matched, 'omitted':max(0,len(paths)-len(scanned)), 'unreadable':unreadable},
        'scope':'Retained receipts only, for this instrument and gateway identity. No live status, credit check, probe, retry or route change.',
        'caution':'Configured is not available. A past success or elapsed wait does not promise quota, free pricing or author quality. Reconcile unresolved tickets before further calls. A gateway job can contain multiple provider/format attempts; this is not a spend ledger.',
        'inference_calls':0}
