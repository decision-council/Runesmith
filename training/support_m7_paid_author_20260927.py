"""One separately journaled ordinary m7 attempt; never repeat a consumed call."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app import building
from runesmith.app.author_recovery import pending_authors
from runesmith.app.build_jobs import BuildJob, run_synchronous_build_job
from runesmith.app.inference_routes import route_view, save_route
from runesmith.app.planner import draft_prompt, source_context
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import _read_json, _write_json, _now
from support_m7_json_input_20260927 import HOME, ROOT, SOURCE, RECORD as COMMISSION, locked, check_idle, sha

RECORD = HOME/'trainer-trials/json-input-m7-paid-author-20260927.json'
MODEL = 'openrouter:deepseek/deepseek-v4-flash-0731'
SCOPE = '7146086fd5a7082699b459a9818013a340d80c81e7114b819cee7a113f0de7c7'
OBSERVED = '2026-09-27T02:55:49.834760+00:00'


def reserve(ws):
    if RECORD.exists():
        raise RuntimeError('This allocation already exists. Inspect its ticket; never resubmit.')
    check_idle(ws)
    old = _read_json(COMMISSION, {})
    if old.get('state') != 'finished' or not old.get('plan_role_restored'):
        raise RuntimeError('Prior author allocation is not reconciled')
    if any(not Path(p).is_file() or sha(Path(p)) != d for p, d in old['protected_sha256'].items()):
        raise RuntimeError('Protected commissioning inputs changed')
    if sha(HOME/'acceptance/m7.py') != old['owner_fixture_sha256']:
        raise RuntimeError('Owner acceptance changed')
    from runesmith.app.acceptance_contracts import expectation_digest
    if expectation_digest(ws, 'm7') != old['public_digest']:
        raise RuntimeError('Public contract changed')
    budget = building.build_escalation_status(ws)
    if budget['scope'] != SCOPE or budget['attempts'] != 1 or budget['used']:
        raise RuntimeError('Ordinary attempt lineage changed')
    if any(d.get('milestone') == 'm7' for d in ws.drafts()):
        raise RuntimeError('An m7 candidate already exists')
    config = ws.config()
    if config['roles'].get('plan') != ['author']:
        raise RuntimeError('Plan role changed')
    context = source_context(ws)
    milestone = next(m for m in ws.plan()['milestones'] if m['id'] == 'm7')
    prompt = draft_prompt(ws, milestone, context)
    packet, _ = json.JSONDecoder().raw_decode(prompt)
    if context.get('focus_errors') or len(prompt.encode()) > 90000 or len(packet['public_acceptance']['criteria']) != 5:
        raise RuntimeError('Author packet failed the reviewed input bound')
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(OBSERVED)).total_seconds()
    # Catalog-based conservative allowance: at most one input token per byte,
    # plus 2,000 tokens for schema/system, and the ordinary 12,000 output cap.
    estimate = (len(prompt.encode())+2000)*0.021/1_000_000 + 12000*0.32/1_000_000
    if age > 900 or estimate > 0.02 or 0.11996584199999916 < 0.02:
        raise RuntimeError('Refresh the balance/catalog review; no generation permitted')
    route = route_view(ws, 'paid-deepseek')
    if route['blockers']:
        raise RuntimeError('Selected route is not reconciled')
    protected = dict(old['protected_sha256'])
    for path in (HOME/'build-attempts').glob('*.json'):
        protected[str(path)] = sha(path)
    record = {'state':'reserved', 'utc':_now(), 'scope':SCOPE, 'source':SOURCE,
        'model':MODEL, 'instrument':'paid-deepseek', 'ordinary_attempt_number':2,
        'prior_config':config, 'prior_route':route,
        'protected_sha256':protected,
        'before_requests':[p.name for p in (HOME/'inference-requests').glob('*.json')],
        'public_digest':old['public_digest'], 'owner_fixture_sha256':old['owner_fixture_sha256'],
        'preview_bytes':len(prompt.encode()), 'preview_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
        'balance_observed_utc':OBSERVED, 'balance_usd':0.11996584199999916,
        'catalog_input_usd_per_m':0.021, 'catalog_output_usd_per_m':0.32,
        'conservative_catalog_allowance_usd':estimate,
        'estimate_limitations':'Catalog estimate, not a hard provider charge guarantee or account-wide reservation.',
        'limit':'One ordinary author-only dispatch. No host retry, explicit fallback, check, apply or follow-on. No attempt/contract/notes reset.',
        'trainer_assistance':'External trainer selected a currently affordable paid route; public task/focus/acceptance are unchanged. Instrument authors Hat implementation.'}
    _write_json(RECORD, record)
    save_route(ws, 'paid-deepseek', revision=route['revision'], model=MODEL, fallback_models=[],
        reason='One m7 attempt after recorded Gemini capacity failure. $0.119965842 fresh balance; no expensive fallback. Restore terminal route afterward.')
    config = ws.config(); config['roles']['plan'] = ['paid-deepseek']; ws.save_config(config)
    record.update(state='dispatch_reserved', config_sha256=sha(HOME/'runesmith.json'))
    _write_json(RECORD, record)
    ws.ledger.append('trainer.m7_paid_author_reserved', {k:record[k] for k in ('utc','scope','model','instrument','balance_usd','conservative_catalog_allowance_usd','limit')})
    return record


def finish(ws, record, result):
    requests = [_read_json(p,{}) for p in (HOME/'inference-requests').glob('*.json') if p.name not in record['before_requests']]
    summaries = []
    for request in requests:
        payload = request.get('payload') or {}; meta = payload.get('meta') or {}
        body = request.get('body') or {}
        summaries.append({k:request.get(k) for k in ('id','state','job_id','instrument')} | {
            'gateway_state':payload.get('state'), 'model':meta.get('model'), 'provider':meta.get('provider'),
            'estimated_usd':meta.get('est_usd'), 'tokens_in':meta.get('tokens_in'), 'tokens_out':meta.get('tokens_out'),
            'attempts':meta.get('attempts'), 'error_code':payload.get('error_code'),
            'prompt_sha256':hashlib.sha256(body.get('prompt','').encode()).hexdigest()})
    record.update(state='finished', finished=_now(), job=result, requests=summaries)
    terminal = all(r.get('state') in ('terminal','refused') for r in requests)
    if terminal and not pending_authors(ws) and sha(HOME/'runesmith.json') == record['config_sha256']:
        previous = record['prior_route']; now = route_view(ws,'paid-deepseek')
        save_route(ws,'paid-deepseek',revision=now['revision'],model=previous['model'],fallback_models=previous['fallback_models'],
            reason='Terminal one-shot m7 attempt completed; restore prior route. No generation.')
        config = ws.config(); config['roles']['plan'] = record['prior_config']['roles']['plan']; ws.save_config(config)
        record['configuration_restored'] = ws.config() == record['prior_config']
    else:
        record['configuration_restored'] = False
    record['source_unchanged'] = collect_snapshot(ws)['digest'] == SOURCE
    record['protected_unchanged'] = all(Path(p).is_file() and sha(Path(p)) == d for p,d in record['protected_sha256'].items())
    _write_json(RECORD,record)
    print(json.dumps({k:v for k,v in record.items() if k not in ('prior_config','protected_sha256','before_requests','prior_route')}), flush=True)


if __name__ == '__main__':
    record = locked(reserve)
    result = run_synchronous_build_job(ROOT, BuildJob('build', {'author_only':True}), home=HOME)
    locked(lambda ws:finish(ws,record,result))
