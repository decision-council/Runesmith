"""Source measurements do not become draft checks, acceptance or retries."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runesmith.app import building
from runesmith.app.source_baseline import baseline_status, measure_current_source, _inventory
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json


def setup(tmp_path):
    ws = Workspace(tmp_path)
    ws.update_settings({'autonomy': 'propose', 'build_steps': True})
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / '__init__.py').write_text('')
    (tests / 'test_current.py').write_text(
        'import unittest\nclass Current(unittest.TestCase):\n'
        ' def test_one(self): self.assertEqual(2+2,4)\n'
        ' def test_two(self): self.assertTrue(True)\n')
    (ws.home / 'acceptance').mkdir(exist_ok=True)
    (ws.home / 'acceptance/m1.py').write_text('raise AssertionError("Owner tests must not run")\n')
    _write_json(ws.home / 'BUILD_LAST.json', {'candidate': 'retained', 'status': 'inconclusive'})
    (ws.home / 'build-check-resumes').mkdir()
    _write_json(ws.home / 'build-check-resumes/candidate.json', {'state': 'completed', 'spent': True})
    return ws


def test_real_complete_baseline_has_inventory_but_no_candidate_or_acceptance_credit(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    before = {p.relative_to(ws.home).as_posix(): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    def forbidden(*args, **kwargs):
        raise AssertionError('No inference or apply permitted')
    monkeypatch.setattr(ws, 'router', forbidden)
    monkeypatch.setattr(ws, 'apply_draft', forbidden)
    result = measure_current_source(ws, 'Diagnose current source only')
    receipt = result['baseline']
    assert receipt['outcome'] == 'measured' and receipt['project_checks']['ran'] == 2
    assert receipt['project_checks']['limit_s'] == 240
    assert receipt['inventory']['complete'] and receipt['inventory']['count'] == 2
    assert all('test_current.Current.test_' in name for name in receipt['inventory']['ids'])
    assert len(receipt['inventory']['sha256']) == 64
    assert receipt['source_still_current'] and not receipt['stage_inputs_changed']
    assert not receipt['candidate_applied'] and not receipt['milestone_advanced']
    assert receipt['inference_calls'] == 0 and receipt['author_budget_reset'] is False
    assert 'owner acceptance were not evaluated' in receipt['coverage']
    for rel in ('BUILD_LAST.json', 'build-check-resumes/candidate.json', 'acceptance/m1.py'):
        assert (ws.home / rel).read_bytes() == before[rel]
    assert not baseline_status(ws)['pending']
    monkeypatch.setattr(building, '_run_checks', forbidden)
    duplicate = measure_current_source(Workspace(tmp_path), 'After restart')
    assert duplicate['already_used']
    assert not list((ws.home / receipt['evidence_dir']).glob('source-stage-*'))


@pytest.mark.parametrize('check,outcome', [
    ({'ok': False, 'status': 'timeout', 'elapsed_s': 240, 'limit_s': 240}, 'inconclusive'),
    ({'ok': False, 'status': 'failed', 'ran': 2, 'failures': 1}, 'baseline_discrepancy')])
def test_timeout_and_completed_failure_are_distinct_and_cannot_rerun(tmp_path, monkeypatch, check, outcome):
    ws = setup(tmp_path)
    monkeypatch.setattr(building, '_run_checks', lambda *args, **kwargs: check)
    receipt = measure_current_source(ws, 'Known ceiling')['baseline']
    assert receipt['state'] == 'completed' and receipt['outcome'] == outcome
    assert not receipt['inventory']['available']
    assert measure_current_source(ws, 'No automatic extension')['already_used']


def test_reservation_precedes_execution_and_interruption_blocks_new_snapshot(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    def stop(stage, kind, logs, **kwargs):
        assert kind == 'project' and kwargs['timeout_s'] == 240
        assert baseline_status(ws)['pending']['state'] == 'started'
        assert (logs.parent / 'BASELINE.json').is_file()
        raise RuntimeError('Interrupted host')
    monkeypatch.setattr(building, '_run_checks', stop)
    with pytest.raises(RuntimeError, match='Interrupted host'):
        measure_current_source(ws, 'One bounded run')
    assert baseline_status(ws)['last']['state'] == 'interrupted'
    (tmp_path / 'new_source.py').write_text('new=1\n')
    with pytest.raises(WorkspaceError, match='active or unresolved'):
        measure_current_source(Workspace(tmp_path), 'Do not evade an unknown run with new source')


def test_current_source_drift_is_not_hidden(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    def changed(stage, kind, logs, **kwargs):
        (tmp_path / 'changed.py').write_text('changed=1\n')
        return {'ok': True, 'status': 'passed', 'ran': 2}
    monkeypatch.setattr(building, '_run_checks', changed)
    receipt = measure_current_source(ws, 'Measure one frozen source')['baseline']
    assert receipt['source_still_current'] is False
    assert not receipt['candidate_applied']


def test_project_mutating_disposable_source_is_discrepancy_not_success(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    def changed(stage, kind, logs, **kwargs):
        (stage / 'tests/test_current.py').write_text('rewritten=1\n')
        return {'ok': True, 'status': 'passed', 'ran': 2}
    monkeypatch.setattr(building, '_run_checks', changed)
    receipt = measure_current_source(ws, 'Diagnose')['baseline']
    assert receipt['outcome'] == 'baseline_discrepancy'
    assert receipt['stage_inputs_changed'] == ['tests/test_current.py']
    assert 'unittest' in (tmp_path / 'tests/test_current.py').read_text()


@pytest.mark.parametrize('setting,value', [('autonomy', 'observe'), ('build_steps', False)])
def test_execution_requires_existing_project_check_authority(tmp_path, setting, value):
    ws = setup(tmp_path)
    ws.update_settings({setting: value})
    assert 'off' in measure_current_source(ws, 'Not allowed')['summary']
    assert not (ws.home / 'source-baseline-runs').exists()


def test_reason_required_and_cancel_before_start_spends_nothing(tmp_path):
    ws = setup(tmp_path)
    with pytest.raises(WorkspaceError, match='Explain'):
        measure_current_source(ws, ' ')
    def cancel():
        raise RuntimeError('Cancelled')
    with pytest.raises(RuntimeError, match='Cancelled'):
        measure_current_source(ws, 'Cancelled before execution', checkpoint=cancel)
    assert not baseline_status(ws)['pending']


def test_studio_worker_path_has_no_timeout_or_candidate_override(tmp_path, monkeypatch):
    from runesmith.app.server import api_worker_run
    from runesmith.app.worker import EventBus, Worker
    ws = setup(tmp_path)
    worker = Worker(ws, EventBus())
    calls = []
    def measure(workspace, reason, **kwargs):
        calls.append((workspace, reason)); return {'summary': 'Source only'}
    monkeypatch.setattr('runesmith.app.source_baseline.measure_current_source', measure)
    job = api_worker_run(SimpleNamespace(worker=worker), {}, {'job': 'source_baseline',
        'params': {'reason': 'One source measurement', 'timeout_s': 99999, 'draft_id': 'ignored', 'apply': True}})
    assert job['params'] == {'reason': 'One source measurement'}
    worker._execute(job)
    assert calls == [(ws, 'One source measurement')]
    ui = (Path(__file__).parents[1] / 'runesmith/app/static/js/views/work.js').read_text(encoding='utf-8')
    assert 'Measure current source' in ui and "job: 'source_baseline'" in ui
    assert 'Current-source timing diagnostic' in ui


@pytest.mark.parametrize('data', ['not json', '{}', 'x' * 262145], ids=['malformed', 'missing_fields', 'oversized'])
def test_malformed_or_large_inventory_is_unknown(tmp_path, data):
    path = tmp_path / 'inventory.json'
    path.write_text(data)
    assert not _inventory(path)['available']


def test_a_baseline_measured_by_an_earlier_runner_is_measured_once_more(tmp_path):
    # Review of J11-B17: the runner changed, allocations refuse a baseline of another runner, and the snapshot could
    # never be measured again ("already has a reserved measurement"): one new measurement, the old one kept beside it.
    ws = setup(tmp_path)
    first = measure_current_source(ws, 'Measure the current source')['baseline']
    path = ws.home / first['evidence_dir'] / 'BASELINE.json'
    _write_json(path, dict(first, runner_sha256='e' * 64))                       # as an earlier runner left it
    again = measure_current_source(ws, 'The runner changed')
    assert 'already_used' not in again and again['baseline']['runner_sha256'] != 'e' * 64
    assert again['baseline']['outcome'] == 'measured'
    assert (ws.home / first['evidence_dir'] / 'BASELINE.runner-eeeeeeee.json').is_file()
    assert measure_current_source(ws, 'And again')['already_used']               # once: now measured by this runner
