"""Durable Milliner tickets. A lost response is not permission to submit again.

The owning Workspace/CLI must serialize writers to its home. No credentials are
stored here; request bodies contain only the already-approved model packet.
"""
from __future__ import annotations

import hashlib
import re
import time

from runesmith.canon import digest


def _io():
    # Lazy: config -> instruments -> this module must not import Workspace early.
    from runesmith.app.workspace import _read_json, _write_json, _now
    return _read_json, _write_json, _now


def read_request(directory, request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{64}', request_id):
        raise ValueError('Invalid inference request ID')
    read, _, _ = _io()
    record = read(directory / (request_id + '.json'), None)
    if not record or digest(record['body']) != record['body_digest']:
        raise ValueError('Missing or changed inference request')
    if hashlib.sha256(record['key'].encode()).hexdigest() != request_id:
        raise ValueError('Inference request key does not match its ID')
    return record


# The outcomes Milliner gives a route that turned the job away before generating anything.
REFUSED = {'rate_limited', 'overloaded', 'busy', 'unavailable', 'daily_exhausted', 'capacity', 'circuit_open'}


def no_route_accepted(payload):
    """True when every route refused the job before generating (Milliner's own attempts say so, and no token was
    used): nothing ran and nothing was charged, as with a refusal at submission (journey J11-F2)."""
    attempts = ((payload or {}).get('meta') or {}).get('attempts') or []
    return ((payload or {}).get('state') == 'failed' and bool(attempts)
            and all(isinstance(a, dict) and a.get('outcome') in REFUSED and not a.get('tokens_in') and not a.get('tokens_out')
                    for a in attempts))


def _outcome(instrument, record, started):
    from runesmith.instruments import CallOutcome
    unresolved = record['state'] not in ('terminal', 'refused')
    # A refusal at submission never became a job: nothing ran and nothing was charged (``not_admitted``).
    extra = {'request_id': record['id'], 'job_id': record.get('job_id'),
             'remote_state': record['state'], 'unresolved': unresolved, 'no_retry': True,
             'not_admitted': record['state'] == 'refused' and not record.get('job_id')}
    if unresolved:
        return CallOutcome(False, error_kind='transport',
            error='Remote outcome unresolved; retrieve the saved job, do not resubmit.',
            latency_s=time.monotonic()-started, receipt=extra)
    payload = record['payload']
    if digest(payload) != record['payload_digest']:
        raise ValueError('Retained gateway answer changed')
    result = instrument._response(record.get('http_status', 200), payload, time.monotonic()-started)
    result.receipt.update(extra, no_route_accepted=no_route_accepted(payload))
    return result


def poll(instrument, record, headers, *, wait_s):
    _, write, now = _io()
    path = instrument.request_dir / (record['id'] + '.json')
    started = time.monotonic()
    if (record['origin'] != instrument.base_url or record['caller'] != instrument.caller_tag
            or record['instrument'] != instrument.name):
        raise ValueError('Configured gateway/caller no longer matches this request')
    if record['state'] in ('terminal', 'refused'):
        return _outcome(instrument, record, started)
    if not record.get('job_id'):
        # POST may have reached the gateway. Never guess from timing or rePOST.
        return _outcome(instrument, record, started)
    deadline = started + max(0.1, wait_s)
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            status, payload = instrument._transport('GET',
                f"{record['origin']}/v1/jobs/{record['job_id']}?wait_s={min(15, remaining):.3f}",
                headers, None, min(20, max(1, remaining+2)))
        except (OSError, TimeoutError) as error:
            record.update(state='pending', last_poll_error=type(error).__name__, updated=now())
            write(path, record)
            break
        if status != 200:
            record.update(state='pending', last_poll_http_status=status, updated=now())
            write(path, record)
            break
        if (not record.get('authenticated_agent') or payload.get('job_id') != record['job_id']
                or payload.get('agent') != record['authenticated_agent']):
            record.update(state='binding_mismatch', updated=now())
            write(path, record)
            break
        if payload.get('state') in ('succeeded', 'failed', 'cancelled', 'rejected', 'expired'):
            record.update(state='terminal', payload=payload, payload_digest=digest(payload), updated=now())
            write(path, record)
            break
        record.update(state='pending', updated=now())
        write(path, record)
        time.sleep(min(0.05, max(0, deadline-time.monotonic())))
    return _outcome(instrument, record, started)


def submit(instrument, body, headers):
    read, write, now = _io()
    key = body['idempotency_key']
    request_id = hashlib.sha256(key.encode()).hexdigest()
    path = instrument.request_dir / (request_id + '.json')
    body = dict(body, wait=False, metadata={'caller_ref': key})
    existing = read(path, None)
    if existing:
        record = read_request(instrument.request_dir, request_id)
        if record['body_digest'] != digest(body):
            raise ValueError('An existing request key cannot be used for different bytes')
        return poll(instrument, record, headers, wait_s=instrument.timeout_s)
    record = {'id':request_id, 'key':key, 'origin':instrument.base_url, 'caller':instrument.caller_tag,
              'instrument':instrument.name, 'body':body, 'body_digest':digest(body),
              'state':'submitting', 'created':now(), 'allowance_reserved':True}
    write(path, record)  # durable intent BEFORE crossing the gateway boundary
    started = time.monotonic()
    try:
        status, payload = instrument._transport('POST', f'{instrument.base_url}/v1/complete',
                                                 headers, body, min(30, instrument.timeout_s))
    except (OSError, TimeoutError) as error:
        record.update(state='remote_outcome_unknown', last_error=type(error).__name__, updated=now())
        write(path, record)
        return _outcome(instrument, record, started)
    job_id = payload.get('job_id')
    if status in (200, 202, 429, 502) and isinstance(job_id, str) and re.fullmatch(r'[A-Za-z0-9_-]+', job_id):
        agent=payload.get('agent')
        # Milliner narrows the authenticated token identity with the caller tag.
        # Bind the exact directly-returned identity, never infer one from timing.
        valid_agent=isinstance(agent,str) and (agent==instrument.caller_tag
                    or agent.endswith('/'+instrument.caller_tag))
        record.update(state='pending' if valid_agent else 'binding_mismatch', job_id=job_id,
                      authenticated_agent=agent if valid_agent else None, binding='direct_ticket', updated=now())
        write(path, record)  # persist the directly returned ticket before polling
        if not valid_agent:return _outcome(instrument, record, started)
        return poll(instrument, record, headers, wait_s=max(0.1,instrument.timeout_s-(time.monotonic()-started)))
    if status in (400, 401, 403, 404, 422, 429) or (not job_id and status in (502,503)
            and payload.get('error') in ('all_routes_exhausted','kill_switch')
            and 'permanent' in payload and 'retry_after_s' in payload):
        record.update(state='refused', payload=payload, payload_digest=digest(payload), http_status=status)
    else:
        record.update(state='remote_outcome_unknown', last_http_status=status)
    write(path, record)
    return _outcome(instrument, record, started)
