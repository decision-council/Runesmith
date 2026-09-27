"""User-requested direct OpenCode trial; one POST, no fallback or auto-replay.

Project authoring still uses the ordinary Runesmith packet/admission path. This
is not a Milliner job; a separate request/response journal records its custody.
"""
from pathlib import Path
import hashlib
import json
import sys
import time
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from runesmith.config import build_instrument
from runesmith.instruments import Router, secret_from

MODEL = 'longcat-2.5-preview-free'
BASE = 'https://opencode.ai/zen/v1'


def direct_http(method, url, headers, body, timeout_s):
    # Honest default python-httpx client identity, as used by Milliner. No
    # product/browser identity headers, redirects, transport retries or SDK.
    with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
        response = client.request(method, url, headers=headers, **({'json': body} if body is not None else {}))
    try:
        payload = response.json()
    except ValueError:
        payload = {'error': response.text[:500]}
    return response.status_code, payload


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'
    home = root / '.runesmith'
    if _existing(home):raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        path = home / 'trainer-trials/opencode-direct-longcat-m5-20260926.json'
        if path.exists():
            previous = _read_json(path, {})
            print(json.dumps({'already_used': True, 'state': previous.get('state', 'unknown'),
                              'no_inference': True}))
            return
        if not _now().startswith('2026-09-26'):
            raise RuntimeError('Free-price review is dated; recheck before a later trial')
        if pending_authors(ws):raise RuntimeError('Reconcile pending author first')
        if (home / 'trainer-trials/opencode-longcat-m5-20260926.json').exists():
            raise RuntimeError('Gateway trial exists; reconcile it before direct authoring')
        if any(d.get('milestone') == 'm5' and d.get('state') in ('waiting', 'applied') for d in ws.drafts()):
            raise RuntimeError('m5 already has a candidate')
        previous = _read_json(home / 'trainer-trials/cline-gemini-m5-20260926.json', {})
        if (previous.get('remote_receipt') or {}).get('remote_state') != 'terminal':
            raise RuntimeError('Previous attempt not terminal')
        before = source_context(ws)['snapshot_digest']
        public = expectation_digest(ws, 'm5')
        if before != '4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5' or public != '5cd2c483da619a4cc34cc720209a91affdef20429b66372d43d1c28209e79cb3':
            raise RuntimeError('Source or public acceptance changed')
        status, catalog = direct_http('GET', BASE + '/models', {}, None, 20)
        if status != 200 or MODEL not in {m.get('id') for m in catalog.get('data', [])}:
            raise RuntimeError('Documented free model no longer listed; no generation')
        token = secret_from(env_var='MILLINER_OPENCODE_API_KEY',
            env_file='C:/dev/Milliner/.env', key='MILLINER_OPENCODE_API_KEY')()
        if not token:raise RuntimeError('OpenCode credential unavailable; no generation')
        name = 'direct-opencode-longcat'
        roles_before = ws.config()['roles']
        ws.save_instrument(name, {'kind': 'openai', 'preset': 'custom', 'model': MODEL,
            'base_url': BASE, 'json_mode': 'none', 'timeout_s': 240,
            'label': 'OpenCode LongCat — direct trial',
            'note': 'Direct HTTPX trainer trial; not a Milliner job. Default UI transport has not been qualified. No role change.'},
            key_value=token, roles=[])
        instrument = build_instrument(name, ws.config()['instruments'][name], home)
        receipt = {'state': 'prepared', 'utc': _now(), 'model': MODEL, 'provider': 'opencode',
            'route': 'direct_api', 'gateway_job_id': None, 'source_digest': before,
            'public_acceptance_digest': public, 'timeout_s': 240, 'max_output_tokens': 12000,
            'api_calls': 0, 'paid_fallback': False, 'automatic_retry': False,
            'estimated_cost_usd': 0.0, 'estimate_basis': 'Official Zen free input/output pricing reviewed 2026-09-26',
            'price_source': 'https://opencode.ai/docs/en/zen/', 'billing_verified': False,
            'trainer_assistance': 'User-requested direct route; existing trainer public contract and hidden synthetic acceptance.'}
        _write_json(path, receipt)
        journal = home / 'trainer-trials/opencode-direct-longcat-m5-20260926'
        def transport(method, url, headers, body, timeout_s):
            if receipt['api_calls'] or method != 'POST' or url != BASE + '/chat/completions' or body.get('model') != MODEL or body.get('max_tokens', 0) > 12000:
                raise RuntimeError('Direct trial boundary refused a changed or repeated request')
            # Never store Authorization or copy the provider credential into a packet.
            if token in json.dumps(body):raise RuntimeError('Credential unexpectedly present in author packet')
            _write_json(journal / 'REQUEST.json', {'utc': _now(), 'method': method, 'url': url, 'body': body})
            receipt.update(state='request_started', api_calls=1,
                body_sha256=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest())
            _write_json(path, receipt)
            started = time.monotonic()
            try:
                code, payload = direct_http(method, url, headers, body, timeout_s)
            except BaseException:
                receipt.update(state='transport_unknown', latency_s=round(time.monotonic() - started, 3))
                _write_json(path, receipt)
                raise
            payload = json.loads(json.dumps(payload).replace(token, '[redacted]'))
            _write_json(journal / 'RESPONSE.json', {'utc': _now(), 'http_status': code, 'payload': payload})
            receipt.update(state='response_received', http_status=code, response_id=payload.get('id'),
                answered_model=payload.get('model'), usage=payload.get('usage'),
                latency_s=round(time.monotonic() - started, 3))
            _write_json(path, receipt)
            return code, payload
        instrument._transport = transport
        events = []
        def record(event):
            events.append(event)
            ws.record_call(event)
        router = Router({name: instrument}, {'plan': [name]}, backoff_s=(), on_call=record)
        print(json.dumps({'state': 'starting_direct_author', 'model': MODEL, 'max_api_calls': 1,
            'timeout_s': 240, 'estimated_cost_usd': 0.0, 'gateway_job_id': None}), flush=True)
        try:
            draft = draft_files(ws, router, 'm5')
            receipt.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'),
                paths=[f['path'] for f in draft['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved',
                error=(type(error).__name__ + ': ' + str(error)).replace(token, '[redacted]')[:600])
        receipt.update(finished=_now(), calls=events,
            source_unchanged=source_context(ws)['snapshot_digest'] == before,
            roles_unchanged=ws.config()['roles'] == roles_before)
        _write_json(path, receipt)
        ws.ledger.append('trainer.direct_author_trial', receipt)
        print(json.dumps(receipt, ensure_ascii=True))
    finally:
        if lock.handle:lock.handle.close()


if __name__ == '__main__':main()
