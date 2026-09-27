"""No model calls: synthetic legacy receipts exercise the linked recovery boundary."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import threading

import pytest

from runesmith.app import building
from runesmith.app.verification_allocation import allocate_verification
from runesmith.app.verification_reconciliation import (LEGACY_REFUSAL, reconcile_verification,
                                                       reconciliation_status)
from runesmith.app.workspace import Workspace, WorkspaceError, _read_json, _write_json
from test_verification_allocation import ready, quote


def preflight_refused(tmp_path, monkeypatch):
    ws, did, _ = ready(tmp_path, monkeypatch)
    q = quote(ws, did)
    with monkeypatch.context() as local:
        local.setattr(building, 'verify_draft', lambda *a, **k: dict(LEGACY_REFUSAL))
        result = allocate_verification(ws, did, q['id'], 'Synthetic legacy preflight failure')
        assert result['verification'] == LEGACY_REFUSAL
    status = reconciliation_status(ws, ws._draft(did))
    assert status['eligible'], status
    return ws, did, status['quote']


def replacement_path(ws, q):
    return ws.home / 'build-check-reconciliations' / (q['parent_allocation'] + '.json')


def test_real_recheck_preserves_receipts_and_never_applies_or_calls_model(tmp_path, monkeypatch):
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    parent_path = ws.home / 'build-check-allocations' / (did + '.json')
    parent_bytes = parent_path.read_bytes()
    prior = list(ws._draft(did)['verification_history'])
    protected = {p: p.read_bytes() for p in (ws.home / 'acceptance').glob('*') if p.is_file()}
    protected.update({ws.home / rel / 'VERIFICATION.json': (ws.home / rel / 'VERIFICATION.json').read_bytes() for rel in prior})
    author_attempts = {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')}
    def forbidden(*a, **k): raise AssertionError('No inference or apply')
    monkeypatch.setattr(ws, 'router', forbidden)
    monkeypatch.setattr(ws, 'apply_draft', forbidden)
    calls = []
    real = building._run_checks
    def check(stage, kind, logs, **kwargs):
        assert _read_json(replacement_path(ws, q), {})['state'] == 'started'
        calls.append((kind, kwargs['timeout_s']))
        return real(stage, kind, logs, **kwargs)
    monkeypatch.setattr(building, '_run_checks', check)
    result = reconcile_verification(ws, did, q['id'], 'Adjudicate exact synthetic legacy evidence; recheck only')
    assert result['verification']['status'] == 'acceptance_passed' and not result.get('advanced')
    assert len(calls) == 2 and calls[0] == ('project', 360) and calls[1][1] == 240
    assert not (tmp_path / 'app.py').exists()
    assert ws.plan()['milestones'][0]['status'] != 'done'
    assert parent_path.read_bytes() == parent_bytes
    assert all(p.read_bytes() == data for p, data in protected.items())
    assert ws._draft(did)['verification_history'][:len(prior)] == prior
    assert author_attempts == {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')}
    assert reconciliation_status(ws, ws._draft(did))['used']
    assert reconcile_verification(Workspace(tmp_path), did, q['id'], 'Repeated click after restart')['already_used']


@pytest.mark.parametrize('change', ['source', 'candidate', 'criteria', 'checks', 'observe', 'grant', 'mode',
                                  'author', 'worker', 'baseline_pending', 'baseline', 'history', 'runner'])
def test_queued_drift_cannot_start_checks(tmp_path, monkeypatch, change):
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    if change == 'source': (tmp_path / 'unseen.py').write_text('x=1\n')
    elif change == 'candidate':
        draft = ws._draft(did); draft['files'][0]['content'] = 'changed=1\n'; ws._save_draft_state(draft, 'waiting')
    elif change == 'criteria': (ws.home / 'acceptance/m1.py').write_text('# changed\n')
    elif change == 'checks': ws.update_settings({'build_steps': False})
    elif change == 'observe': ws.update_settings({'autonomy': 'observe'})
    elif change == 'grant': ws.update_settings({'build_apply': False})
    elif change == 'mode':
        from runesmith.app.work_modes import configuration, save
        policy = configuration(ws)
        modes = [dict(m, enabled=False) for m in policy['modes']]
        save(ws, modes, policy['revision'], 'Disable all modes', infer_purpose=False)
    elif change == 'author': _write_json(ws.home / 'build-attempts/unknown.json', {'state': 'uncertain'})
    elif change == 'worker': _write_json(ws.home / 'STUDIO_CURRENT.json', {'id': 'another', 'kind': 'build'})
    elif change == 'baseline_pending': _write_json(ws.home / 'SOURCE_BASELINE_PENDING.json', {'state': 'started'})
    elif change == 'baseline':
        path = ws.home / 'source-baseline-runs' / q['bindings']['snapshot_digest'] / 'BASELINE.json'
        value = _read_json(path, {}); value['state'] = 'unknown'; _write_json(path, value)
    elif change == 'history':
        draft = ws._draft(did); ws._save_draft_state(draft, 'waiting', verification_history=[])
    else: monkeypatch.setattr(building, 'RUNNER', building.RUNNER + '\n# changed')
    def forbidden(*a, **k): raise AssertionError('No phase may start')
    monkeypatch.setattr(building, '_run_checks', forbidden)
    with pytest.raises(WorkspaceError, match='stale'):
        reconcile_verification(ws, did, q['id'], 'Old queued quote')
    assert not replacement_path(ws, q).exists()


@pytest.mark.parametrize('change', ['parent', 'ledger', 'result', 'extra_run', 'phase', 'later_check'])
def test_zero_elapsed_or_missing_evidence_alone_never_authorizes_replacement(tmp_path, monkeypatch, change):
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    if change == 'parent':
        path = ws.home / 'build-check-allocations' / (did + '.json')
        value = _read_json(path, {}); value['state'] = 'interrupted'; _write_json(path, value)
    elif change == 'ledger':
        path = ws.home / 'ledger.jsonl'; path.write_text(path.read_text().replace('build.check_allocation_completed', 'build.check_allocation_uncertain'))
    elif change == 'extra_run': (ws.home / 'build-runs' / did / 'v-abcdef012345').mkdir()
    elif change == 'later_check': ws.ledger.append('build.checked', {'draft': did, 'status': 'stale'})
    else:
        draft = ws._draft(did)
        value = dict(LEGACY_REFUSAL)
        value.update({'detail': 'Unrelated early error'} if change == 'result' else {'project_checks': {'status': 'started'}})
        ws._save_draft_state(draft, 'waiting', verification=value)
    assert not reconciliation_status(ws, ws._draft(did))['eligible']


@pytest.mark.parametrize('raw', ['', '{', '{}', 'null', '[]', '{"state":"started"}'])
def test_corrupt_replacement_is_consumed_without_overwrite(tmp_path, monkeypatch, raw):
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    path = replacement_path(ws, q); path.parent.mkdir(parents=True); path.write_text(raw)
    before = path.read_bytes()
    state = reconciliation_status(ws, ws._draft(did))
    assert state['used'] and not state['eligible'] and state['receipt']['outcome'] == 'unknown'
    assert reconcile_verification(ws, did, q['id'], 'No repeat')['already_used']
    assert path.read_bytes() == before


def test_timeout_consumes_replacement_without_reconciliation_chains(tmp_path, monkeypatch):
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    monkeypatch.setattr(building, '_run_checks', lambda *a, **k:
                        {'ok': False, 'status': 'timeout', 'elapsed_s': 360, 'limit_s': 360})
    result = reconcile_verification(ws, did, q['id'], 'One bounded recheck')
    assert result['verification']['status'] == 'inconclusive'
    assert reconcile_verification(ws, did, q['id'], 'No extension')['already_used']


@pytest.mark.parametrize('change', ['pause', 'disable', 'source'])
def test_revocation_between_phases_prevents_owner_execution_and_consumes_slot(tmp_path, monkeypatch, change):
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    calls = []
    def check(stage, kind, logs, **kwargs):
        calls.append(kind)
        if change == 'disable': ws.update_settings({'build_steps': False})
        if change == 'source': (tmp_path / 'new.py').write_text('new=1\n')
        return {'ok': True, 'status': 'passed', 'ran': 1, 'elapsed_s': 1}
    def checkpoint():
        if calls and change == 'pause': raise RuntimeError('Paused between phases')
    monkeypatch.setattr(building, '_run_checks', check)
    with pytest.raises((WorkspaceError, RuntimeError)):
        reconcile_verification(ws, did, q['id'], 'Revocation stays responsive', checkpoint=checkpoint)
    assert calls == ['project']
    assert _read_json(replacement_path(ws, q), {})['state'] == 'interrupted'
    assert reconcile_verification(Workspace(tmp_path), did, q['id'], 'No restart replay')['already_used']


def test_concurrent_requests_execute_at_most_once(tmp_path, monkeypatch):
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    started, release = threading.Event(), threading.Event()
    def check(*a, **k):
        started.set(); assert release.wait(10)
        return {'ok': False, 'status': 'timeout', 'elapsed_s': 360, 'limit_s': 360}
    monkeypatch.setattr(building, '_run_checks', check)
    second_ws = Workspace(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(reconcile_verification, ws, did, q['id'], 'First explicit request')
        assert started.wait(10)
        try:
            assert reconcile_verification(second_ws, did, q['id'], 'Duplicate request')['already_used']
        finally:
            release.set()
        assert first.result()['verification']['status'] == 'inconclusive'


def test_api_dispatch_uses_only_quoted_limits_and_current_worker_identity(tmp_path, monkeypatch):
    from runesmith.app.server import api_worker_run
    from runesmith.app.worker import EventBus, Worker
    ws, did, q = preflight_refused(tmp_path, monkeypatch)
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(building, '_run_checks', lambda *a, **k:
                        {'ok': False, 'status': 'timeout', 'elapsed_s': 360, 'limit_s': k['timeout_s']})
    job = api_worker_run(SimpleNamespace(worker=worker), {}, {'job': 'reconcile_check', 'params':
        {'draft_id': did, 'quote_id': q['id'], 'reason': 'Explicit', 'project_timeout_s': 999999, 'apply': True}})
    assert set(job['params']) == {'draft_id', 'quote_id', 'reason'}
    worker._execute(job)
    receipt = _read_json(replacement_path(ws, q), {})
    assert receipt['state'] == 'completed' and receipt['project_timeout_s'] == 360
    assert receipt['apply_permitted'] is False and not receipt['advanced']
