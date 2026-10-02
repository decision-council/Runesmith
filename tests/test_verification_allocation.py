"""Prospective resource grants preserve earlier outcomes and every check gate."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runesmith.app import building
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.verification_allocation import allocate_verification, allocation_status
from runesmith.app.verification_resume import resume_verification
from runesmith.app.workspace import Workspace, WorkspaceError, _read_json, _write_json
from test_verification_resume import pending


def ready(tmp_path, monkeypatch):
    ws, did = pending(tmp_path, monkeypatch)
    with monkeypatch.context() as local:
        local.setattr(building, '_run_checks', lambda *a, **kw:
            {'ok': False, 'status': 'timeout', 'elapsed_s': 240, 'limit_s': 240})
        assert resume_verification(ws, did, 'Original separate continuation')['verification']['status'] == 'inconclusive'
    snapshot = collect_snapshot(ws)
    folder = ws.home / 'source-baseline-runs' / snapshot['digest']
    # Synthetic measurement fixture, not an actually measured performance claim.
    baseline = {'state': 'completed', 'outcome': 'measured', 'snapshot_digest': snapshot['digest'],
        'source_still_current': True, 'stage_inputs_changed': [],
        'project_checks': {'status': 'passed', 'ok': True, 'ran': 50, 'skipped': 0, 'elapsed_s': 133.91},
        'inventory': {'complete': True, 'count': 50},
        'runner_sha256': hashlib.sha256(building.RUNNER.encode()).hexdigest(),
        'evidence_dir': folder.relative_to(ws.home).as_posix()}
    _write_json(folder / 'BASELINE.json', baseline)
    return ws, did, folder / 'BASELINE.json'


def quote(ws, did):
    status = allocation_status(ws, ws._draft(did))
    assert status['eligible'], status
    return status['quote']


def test_real_full_candidate_and_owner_checks_use_distinct_reserved_limits_once(tmp_path, monkeypatch):
    ws, did, _ = ready(tmp_path, monkeypatch)
    q = quote(ws, did)
    assert (q['project_timeout_s'], q['owner_timeout_s'], q['maximum_check_s']) == (360, 240, 600)
    assert q['host_variation_allowance_s'] == q['baseline_elapsed_s'] == 133.91
    original = ws.home / 'build-check-resumes' / (did + '.json')
    original_bytes = original.read_bytes()
    prior_history = list(ws._draft(did)['verification_history'])
    author_attempts = {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')}
    def forbidden(*a, **k):
        raise AssertionError('No inference')
    monkeypatch.setattr(ws, 'router', forbidden)
    real = building._run_checks
    calls = []
    def check(stage, kind, logs, **kwargs):
        reservation = _read_json(ws.home / 'build-check-allocations' / (did + '.json'), {})
        assert reservation['state'] == 'started'
        calls.append((kind, kwargs['timeout_s']))
        return real(stage, kind, logs, **kwargs)
    monkeypatch.setattr(building, '_run_checks', check)
    result = allocate_verification(ws, did, q['id'], 'Separate fixed resource allowance')
    assert result['advanced'] and result['verification']['status'] == 'acceptance_passed'
    assert calls[0] == ('project', 360) and calls[1][1] == 240 and calls[1][0].startswith('[')
    assert result['verification']['project_checks']['ran'] == result['verification']['acceptance']['ran'] == 1
    assert original.read_bytes() == original_bytes
    assert ws._draft(did)['verification_history'][:len(prior_history)] == prior_history
    assert {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')} == author_attempts
    receipt = allocation_status(ws, ws._draft(did))['receipt']
    assert receipt['state'] == 'completed' and receipt['author_budget_reset'] is False
    assert receipt['baseline_receipt_digest'] == q['baseline_receipt_digest']
    monkeypatch.setattr(building, '_run_checks', forbidden)
    assert allocate_verification(Workspace(tmp_path), did, q['id'], 'Duplicate after restart')['already_used']


@pytest.mark.parametrize('changed', ['source', 'candidate', 'acceptance', 'baseline', 'grant'])
def test_quote_cannot_be_used_after_frozen_inputs_or_authority_change(tmp_path, monkeypatch, changed):
    ws, did, baseline_path = ready(tmp_path, monkeypatch)
    q = quote(ws, did)
    if changed == 'source':
        (tmp_path / 'new.py').write_text('x=1\n')
    elif changed == 'candidate':
        draft = ws._draft(did); draft['files'][0]['content'] = 'changed=1\n'
        ws._save_draft_state(draft, 'waiting')
    elif changed == 'acceptance':
        (ws.home / 'acceptance/m1.py').write_text('changed=1\n')
    elif changed == 'baseline':
        baseline = _read_json(baseline_path, {}); baseline['project_checks']['elapsed_s'] = 140
        _write_json(baseline_path, baseline)
    else:
        ws.update_settings({'build_apply': False})
    with pytest.raises(WorkspaceError, match='stale'):
        allocate_verification(ws, did, q['id'], 'Old quote must not execute')
    assert not (ws.home / 'build-check-allocations').exists()


@pytest.mark.parametrize('condition', ['missing', 'timeout', 'inventory', 'old_runner', 'unresolved', 'unfinished_resume'])
def test_inadequate_or_unresolved_baseline_is_not_a_basis_for_new_allowance(tmp_path, monkeypatch, condition):
    ws, did, path = ready(tmp_path, monkeypatch)
    baseline = _read_json(path, {})
    if condition == 'missing':
        path.unlink()
    elif condition == 'unresolved':
        _write_json(ws.home / 'SOURCE_BASELINE_PENDING.json', {'state': 'interrupted'})
    elif condition == 'unfinished_resume':
        _write_json(ws.home / 'build-check-resumes' / (did + '.json'), {'state': 'started'})
    else:
        if condition == 'timeout':baseline['outcome'] = 'inconclusive'
        if condition == 'inventory':baseline['inventory']['count'] = 49
        if condition == 'old_runner':baseline['runner_sha256'] = '0' * 64
        _write_json(path, baseline)
    assert not allocation_status(ws, ws._draft(did))['eligible']


@pytest.mark.parametrize('elapsed', [True, float('inf'), -1, 241], ids=['boolean', 'infinity', 'negative', 'outside_baseline_ceiling'])
def test_bad_elapsed_cannot_produce_an_unbounded_quote(tmp_path, monkeypatch, elapsed):
    ws, did, path = ready(tmp_path, monkeypatch)
    baseline = _read_json(path, {}); baseline['project_checks']['elapsed_s'] = elapsed
    _write_json(path, baseline)
    assert not allocation_status(ws, ws._draft(did))['eligible']


def test_second_timeout_is_retained_and_allocation_stays_spent(tmp_path, monkeypatch):
    ws, did, _ = ready(tmp_path, monkeypatch)
    q = quote(ws, did)
    monkeypatch.setattr(building, '_run_checks', lambda *a, **kw:
        {'status': 'timeout', 'ok': False, 'elapsed_s': 360, 'limit_s': 360})
    result = allocate_verification(ws, did, q['id'], 'One new allowance only')
    assert result['verification']['status'] == 'inconclusive' and not result.get('advanced')
    assert allocate_verification(ws, did, q['id'], 'No automatic repeat')['already_used']


def test_interruption_reservation_blocks_replay_even_with_another_quote_id(tmp_path, monkeypatch):
    ws, did, _ = ready(tmp_path, monkeypatch)
    q = quote(ws, did)
    def interrupted(*args, **kwargs):raise RuntimeError('Host stopped')
    monkeypatch.setattr(building, '_run_checks', interrupted)
    with pytest.raises(RuntimeError, match='Host stopped'):
        allocate_verification(ws, did, q['id'], 'Reserve before execution')
    assert allocation_status(ws, ws._draft(did))['receipt']['state'] == 'interrupted'
    assert allocate_verification(Workspace(tmp_path), did, 'changed', 'No repeat')['already_used']


@pytest.mark.parametrize('raw', ['', '{', '{}', 'null', '[]', '{"id":"partial"}'],
                         ids=['empty', 'truncated', 'empty_object', 'null', 'array', 'partial'])
def test_damaged_reservation_is_unknown_not_permission_to_replay(tmp_path, monkeypatch, raw):
    ws, did, _ = ready(tmp_path, monkeypatch)
    q = quote(ws, did)
    path = ws.home / 'build-check-allocations' / (did + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding='utf-8')
    before = path.read_bytes()
    def forbidden(*args, **kwargs):raise AssertionError('Damaged reservation must not execute')
    monkeypatch.setattr(building, '_run_checks', forbidden)
    status = allocation_status(ws, ws._draft(did))
    assert status['used'] and not status['eligible']
    assert status['receipt']['state'] == 'unresolved'
    assert allocate_verification(ws, did, q['id'], 'No silent replay')['already_used']
    assert path.read_bytes() == before


def test_checks_without_apply_grant_and_with_disabled_checks(tmp_path, monkeypatch):
    ws, did, _ = ready(tmp_path, monkeypatch)
    ws.update_settings({'build_apply': False})
    q = quote(ws, did)
    result = allocate_verification(ws, did, q['id'], 'Checks only')
    assert result['verification']['status'] == 'acceptance_passed' and not result.get('advanced')
    assert not (tmp_path / 'app.py').exists()


def test_api_worker_cannot_accept_arbitrary_deadlines(tmp_path, monkeypatch):
    from runesmith.app.server import api_worker_run
    from runesmith.app.worker import EventBus, Worker
    ws, did, _ = ready(tmp_path, monkeypatch)
    worker = Worker(ws, EventBus()); calls = []
    def allocate(workspace, draft_id, quote_id, reason, **kwargs):
        calls.append((workspace, draft_id, quote_id, reason)); return {'summary': 'Checked'}
    monkeypatch.setattr('runesmith.app.verification_allocation.allocate_verification', allocate)
    job = api_worker_run(SimpleNamespace(worker=worker), {}, {'job': 'allocate_check',
        'params': {'draft_id': did, 'quote_id': 'quoted', 'reason': 'Explicit', 'owner_timeout_s': 999999}})
    assert 'owner_timeout_s' not in job['params']
    worker._execute(job)
    assert calls == [(ws, did, 'quoted', 'Explicit')]
    ui = (Path(__file__).parents[1] / 'runesmith/app/static/js/views/work.js').read_text(encoding='utf-8')
    assert 'Reserve a separate verification budget' in ui and "job: 'allocate_check'" in ui


def test_a_large_owner_bundle_gets_its_scaled_limit_in_the_quote(tmp_path, monkeypatch):
    # Review of J11-B17: the quote fixed the owner phase at 240 s, less than an ordinary build gives a large bundle.
    from test_build_steps import setup, enable
    big = 'import unittest\nfrom app import answer\n\n\nclass Acceptance(unittest.TestCase):\n' + ''.join(
        f'    def test_c{i}(self):\n        self.assertEqual(answer(), 42)\n' for i in range(200))
    ws = setup(tmp_path, acceptance=True)
    enable(ws)
    (ws.home / 'acceptance' / 'm1.py').write_text(big, encoding='utf-8', newline='\n')
    with monkeypatch.context() as local:
        local.setattr(building, '_run_checks', lambda *a, **kw:
            {'status': 'timeout', 'ok': False, 'elapsed_s': 120, 'limit_s': 120, 'output': 'unfinished'})
        did = building.build_step(ws, ws.router())['draft']
    with monkeypatch.context() as local:
        local.setattr(building, '_run_checks', lambda *a, **kw:
            {'ok': False, 'status': 'timeout', 'elapsed_s': 240, 'limit_s': 240})
        assert resume_verification(ws, did, 'Original separate continuation')['verification']['status'] == 'inconclusive'
    snapshot = collect_snapshot(ws)
    folder = ws.home / 'source-baseline-runs' / snapshot['digest']
    _write_json(folder / 'BASELINE.json', {'state': 'completed', 'outcome': 'measured', 'snapshot_digest': snapshot['digest'],
        'source_still_current': True, 'stage_inputs_changed': [],
        'project_checks': {'status': 'passed', 'ok': True, 'ran': 50, 'skipped': 0, 'elapsed_s': 133.91},
        'inventory': {'complete': True, 'count': 50}, 'runner_sha256': hashlib.sha256(building.RUNNER.encode()).hexdigest(),
        'evidence_dir': folder.relative_to(ws.home).as_posix()})
    q = quote(ws, did)
    assert (q['project_timeout_s'], q['owner_timeout_s'], q['maximum_check_s']) == (360, 460, 820)
    seen = []
    monkeypatch.setattr(building, '_run_checks', lambda stage, kind, logs, **kw:
        seen.append(kw['timeout_s']) or {'ok': True, 'status': 'passed', 'ran': 1, 'elapsed_s': 1, 'limit_s': kw['timeout_s']})
    allocate_verification(ws, did, q['id'], 'Separate resource allowance')
    assert seen == [360, 460]
