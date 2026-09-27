"""No provider calls: accounting is a projection of retained gateway evidence."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from runesmith.app.workspace import Workspace, _write_json
from runesmith.canon import digest
from runesmith.instruments import MillinerInstrument
from runesmith.inference_usage import qualify_usage


def failed_payload():
    return {'job_id': 'mj_failed', 'agent': 'operator/field', 'state': 'failed',
        'meta': {'tokens_in': 0, 'tokens_out': 0, 'est_usd': 0.0, 'attempts': [
            {'provider': 'openrouter', 'model': 'example', 'outcome': 'truncated',
             'tokens_in': n, 'tokens_out': 12000} for n in (20608, 20911, 20911)]}}


def save(home, name='one', *, payload=None, state='terminal', **overrides):
    key = 'request-' + name
    body = {'prompt': 'PRIVATE-PROMPT'}
    payload = failed_payload() if payload is None else payload
    record = {'id': hashlib.sha256(key.encode()).hexdigest(), 'key': key,
        'instrument': 'paid-author', 'origin': 'http://gateway.test', 'caller': 'field',
        'authenticated_agent': 'operator/field', 'job_id': payload.get('job_id'),
        'state': state, 'body': body, 'body_digest': digest(body),
        'payload': payload, 'payload_digest': digest(payload), 'updated': '2026-09-27T03:11:32Z'}
    record.update(overrides)
    path = home / 'inference-requests' / (name + '.json')
    _write_json(path, record)
    return path, record


@pytest.mark.parametrize('status', [200, 500])
def test_failed_gateway_usage_is_not_free_or_zero_in_host_event(status):
    inst = MillinerInstrument('paid-author', 'openrouter:example', base_url='http://gateway.test', token=lambda: '')
    result = inst._response(status, failed_payload(), 1)
    assert not result.ok
    assert result.receipt.get('tokens_in') == 62430
    assert result.receipt.get('tokens_out') == 36000
    assert result.receipt.get('est_usd') is None
    assert result.receipt['accounting']['cost_status'] == 'aggregate_mismatch'


def test_new_host_stats_do_not_admit_false_zero_cost(tmp_path):
    ws = Workspace(tmp_path)
    inst = MillinerInstrument('paid-author', 'openrouter:example', base_url='http://gateway.test', token=lambda: '')
    result = inst._response(200, failed_payload(), 1)
    ws.record_call(dict(result.receipt, instrument='paid-author', ok=False, latency_s=1))
    stats = ws.call_stats()['paid-author']
    assert stats['tokens_out'] == 36000
    assert stats.get('costed_calls', 0) == 0
    assert 'aggregate_mismatch' in (ws.home / 'ledger.jsonl').read_text()


def test_terminal_recovery_projection_counts_once_without_rewriting_host_stats(tmp_path):
    from runesmith.app.inference_accounting import accounting_view
    ws = Workspace(tmp_path)
    _write_json(ws.home / 'OPERATIONS.json', {'instruments': {'paid-author': {'calls': 1, 'errors': 1}}})
    path, record = save(ws.home, state='pending')
    first = accounting_view(ws.home)
    assert first['summary']['requests'] == 1 and first['summary']['unresolved'] == 1
    assert first['requests'][0]['usage']['attempts'] is None
    assert first['requests'][0]['usage']['token_basis'] == 'unknown'
    record['state'] = 'terminal'; _write_json(path, record)
    before = {p: p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    result = accounting_view(ws.home)
    assert result == accounting_view(ws.home)
    assert result['summary']['requests'] == 1 and result['summary']['unresolved'] == 0
    row = result['requests'][0]
    assert row['usage']['tokens_in'] == 62430 and row['usage']['tokens_out'] == 36000
    assert row['usage']['est_usd'] is None
    assert result['summary']['costed_requests'] == 0
    assert result['summary']['estimated_usd'] is None
    assert before == {p: p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    assert all(s not in json.dumps(result) for s in ('PRIVATE', 'gateway.test', 'operator/field'))


def test_repeated_ticket_dedup_and_conflicting_terminal_fail_closed(tmp_path):
    from runesmith.app.inference_accounting import accounting_view
    home = tmp_path
    _, record = save(home)
    _write_json(home / 'inference-requests/copy.json', record)
    result = accounting_view(home)
    assert result['summary']['requests'] == 1 and result['coverage']['duplicates'] == 1
    record = copy.deepcopy(record)
    record['payload']['meta']['tokens_out'] = 1
    record['payload_digest'] = digest(record['payload'])
    _write_json(home / 'inference-requests/copy.json', record)
    result = accounting_view(home)
    assert result['summary']['requests'] == 1
    assert result['requests'][0]['state'] == 'conflicting'
    assert result['summary']['costed_requests'] == 0


@pytest.mark.parametrize('field', ['body', 'payload', 'authenticated_agent', 'id'])
def test_damaged_identity_or_digests_are_unknown_not_free(tmp_path, field):
    from runesmith.app.inference_accounting import accounting_view
    path, record = save(tmp_path)
    if field in ('body', 'payload'): record[field]['changed'] = True
    else: record[field] = 'changed'
    _write_json(path, record)
    report = accounting_view(tmp_path)
    assert report['coverage']['invalid'] == 1
    assert report['summary']['estimated_usd'] is None


def test_api_and_dashboard_share_projection_without_initializing_other_homes(tmp_path, monkeypatch):
    from runesmith.app.inference_accounting import accounting_view
    from runesmith.app.server import api_inference_accounting
    from runesmith.app.dashboards import snapshot
    ws = Workspace(tmp_path); save(ws.home)
    monkeypatch.setattr(Workspace, '__init__', lambda *a, **k: pytest.fail('No initialization'))
    expected = accounting_view(ws.home)
    assert api_inference_accounting(SimpleNamespace(ws=ws), {}, {}) == expected
    assert snapshot({'root': str(ws.root), 'home': str(ws.home)})['gateway_accounting'] == expected


@pytest.mark.parametrize('value', [None, True, -1, '2', 1.5, float('nan'), float('inf'), 10**1000])
def test_missing_or_invalid_attempt_tokens_never_imply_complete_zero(value):
    meta = failed_payload()['meta']
    meta['attempts'][1]['tokens_out'] = value
    result = qualify_usage(meta)
    assert result['tokens_in'] == 62430 and result['tokens_out'] is None
    assert result['observed_tokens_out'] == 24000
    assert result['token_complete_attempts'] == 2 and result['est_usd'] is None


@pytest.mark.parametrize('amount', [None, True, -0.01, '0', float('nan'), float('inf'), 10**1000])
def test_invalid_price_is_never_a_costed_request(amount):
    assert qualify_usage({'tokens_in': 1, 'tokens_out': 2, 'est_usd': amount})['est_usd'] is None


@pytest.mark.parametrize('attempts', [None, {}, [None], [True], [{}] * 257])
def test_invalid_attempt_structure_is_not_masked_by_valid_aggregate(attempts):
    result = qualify_usage({'tokens_in': 0, 'tokens_out': 0, 'est_usd': 0, 'attempts': attempts})
    assert result['est_usd'] is None and result['tokens_in'] is None


def test_successful_fallback_aggregate_must_include_failed_attempts():
    meta = {'tokens_in': 10, 'tokens_out': 5, 'est_usd': 0.1,
        'attempts': [{'tokens_in': 4, 'tokens_out': 3}, {'tokens_in': 10, 'tokens_out': 5}]}
    result = qualify_usage(meta)
    assert result['tokens_in'] == 14 and result['est_usd'] is None
    meta.update(tokens_in=14, tokens_out=8)
    result = qualify_usage(meta)
    assert result['est_usd'] == 0.1 and result['cost_status'] == 'reported_attempt_reconciled'


def test_reported_free_and_no_generation_are_distinct_from_unknown():
    result = qualify_usage({'tokens_in': 0, 'tokens_out': 0, 'est_usd': 0,
        'attempts': [{'tokens_in': 0, 'tokens_out': 0}] * 3})
    assert result['est_usd'] == 0 and result['attempts'] == 3
    result = qualify_usage({'tokens_in': 10, 'tokens_out': 20, 'est_usd': 0})
    assert result['est_usd'] == 0 and result['token_basis'] == 'aggregate_only'
    assert qualify_usage({})['est_usd'] is None


def test_cached_counters_are_not_assumed_to_be_fresh_billed_usage():
    result = qualify_usage({'tokens_in': 10, 'tokens_out': 20, 'est_usd': .02, 'cached': True})
    assert result['tokens_in'] is None and result['est_usd'] is None
    assert result['cost_status'] == 'cached_unverified'


def test_pending_copy_and_recovered_ticket_share_one_identity(tmp_path):
    from runesmith.app.inference_accounting import accounting_view
    _, record = save(tmp_path, state='pending')
    record['state'] = 'terminal'
    _write_json(tmp_path / 'inference-requests/recovered.json', record)
    result = accounting_view(tmp_path)
    assert result['summary']['requests'] == 1
    assert result['summary']['unresolved'] == 0
    assert result['coverage']['duplicates'] == 1
    assert result['requests'][0]['usage']['tokens_out'] == 36000


def test_distinct_gateway_identities_and_unknown_posts_are_not_collapsed(tmp_path):
    from runesmith.app.inference_accounting import accounting_view
    save(tmp_path)
    save(tmp_path, 'other', origin='http://other.test')
    save(tmp_path, 'unknown1', job_id=None, state='remote_outcome_unknown')
    save(tmp_path, 'unknown2', job_id=None, state='submitting')
    result = accounting_view(tmp_path)
    assert result['summary']['requests'] == 4 and result['summary']['unresolved'] == 2


def test_partial_subtotal_and_scan_coverage_do_not_claim_whole_spend(tmp_path, monkeypatch):
    import os
    from runesmith.app import inference_accounting as module
    monkeypatch.setattr(module, 'MAX_RECEIPTS', 3)
    monkeypatch.setattr(module, 'MAX_RECEIPT_BYTES', 3000)
    for i in range(4):
        payload = failed_payload(); payload['job_id'] = 'mj_' + str(i)
        if i == 2: payload['meta'] = {'tokens_in': 2, 'tokens_out': 3, 'est_usd': .02}
        path, _ = save(tmp_path, str(i), payload=payload)
        os.utime(path, (100 + i, 100 + i))
    path.write_text(' ' * 3001); os.utime(path, (103, 103))
    result = module.accounting_view(tmp_path)
    assert result['coverage'] == {'scanned': 3, 'valid': 2, 'invalid': 1, 'duplicates': 0, 'omitted': 1}
    assert result['summary']['costed_requests'] == 1
    assert result['summary']['estimated_usd'] == .02
    assert result['summary']['requests'] == 2


@pytest.mark.parametrize('relative', ['inference-requests', 'inference-requests/one.json'])
def test_links_and_junctions_not_followed_even_without_windows_link_privilege(tmp_path, monkeypatch, relative):
    from pathlib import Path
    from runesmith.app.inference_accounting import accounting_view
    save(tmp_path)
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == tmp_path / relative or original(p))
    result = accounting_view(tmp_path)
    assert result['coverage']['invalid'] == 1 and result['summary']['requests'] == 0


def test_actual_durable_timeout_get_recovery_and_repeated_inspection_no_double_count(tmp_path):
    from runesmith.app.inference_accounting import accounting_view
    from test_author_recovery import Gateway, instrument
    gateway = Gateway()
    inst = instrument(tmp_path, gateway)
    result = inst.complete(prompt='p', system='s', schema=None, max_tokens=10, key='one')
    assert not result.ok
    assert accounting_view(tmp_path)['summary']['unresolved'] == 1
    gateway.fail_poll = False
    result = inst.resume_request(result.receipt['request_id'])
    assert result.ok
    report = accounting_view(tmp_path)
    assert report['summary']['requests'] == 1 and report['summary']['unresolved'] == 0
    assert report['requests'][0]['usage']['tokens_out'] == 30
    assert report['summary']['estimated_usd'] is None  # fixture lacks input tokens
    before = len(gateway.requests)
    assert inst.resume_request(result.receipt['request_id']).ok
    assert accounting_view(tmp_path) == report
    assert len(gateway.requests) == before
    assert [method for method, _ in gateway.requests].count('POST') == 1


@pytest.mark.parametrize('mutation', ['body', 'instrument', 'binding'])
def test_duplicate_identity_with_conflicting_custody_is_never_costed(tmp_path, mutation):
    from runesmith.app.inference_accounting import accounting_view
    _, record = save(tmp_path)
    if mutation == 'body':
        record['body']['prompt'] = 'OTHER-PRIVATE'; record['body_digest'] = digest(record['body'])
    elif mutation == 'instrument': record['instrument'] = 'other'
    else: record['state'] = 'binding_mismatch'
    _write_json(tmp_path / 'inference-requests/duplicate.json', record)
    row = accounting_view(tmp_path)['requests'][0]
    assert row['state'] == 'conflicting' and row['usage']['est_usd'] is None


def test_pre_ticket_copy_is_aliased_only_by_exact_request_identity(tmp_path):
    from runesmith.app.inference_accounting import accounting_view
    payload = failed_payload()
    payload['meta'] = {'tokens_in': 1, 'tokens_out': 2, 'est_usd': .03}
    _, record = save(tmp_path, payload=payload)
    record.update(job_id=None, state='remote_outcome_unknown', authenticated_agent=None)
    _write_json(tmp_path / 'inference-requests/pre-ticket-copy.json', record)
    result = accounting_view(tmp_path)
    assert result['summary']['requests'] == 1 and result['summary']['unresolved'] == 0
    assert result['summary']['estimated_usd'] == .03
    assert result['coverage']['duplicates'] == 1


def test_same_request_bound_to_conflicting_tickets_is_one_conflicting_component(tmp_path):
    from runesmith.app.inference_accounting import accounting_view
    _, record = save(tmp_path)
    record['job_id'] = record['payload']['job_id'] = 'mj_other'
    record['payload_digest'] = digest(record['payload'])
    _write_json(tmp_path / 'inference-requests/other-ticket.json', record)
    result = accounting_view(tmp_path)
    assert result['summary']['requests'] == 1
    assert result['requests'][0]['state'] == 'conflicting'
    assert result['requests'][0]['job_ids'] == ['mj_failed', 'mj_other']
    assert result['summary']['estimated_usd'] is None


@pytest.mark.parametrize('history,count,status', [
    ('absent', None, 'reported_aggregate_only'),
    ([], 0, 'reported_aggregate_only'),
    ([{'tokens_in': 1, 'tokens_out': 2}], 1, 'reported_attempt_reconciled')])
def test_reported_estimate_strength_and_absent_attempt_history_are_explicit(history, count, status):
    meta = {'tokens_in': 1, 'tokens_out': 2, 'est_usd': .02}
    if history != 'absent': meta['attempts'] = history
    result = qualify_usage(meta)
    assert result['est_usd'] == .02 and result['attempts'] == count
    assert result['cost_status'] == status
