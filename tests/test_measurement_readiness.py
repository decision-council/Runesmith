"""Time/source-qualified report evidence; no live sources or model calls."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runesmith.app import measurements as metrics, work_modes as modes, dashboards
from runesmith.app.worker import Worker, EventBus
from runesmith.app.workspace import WorkspaceError, _read_json, _write_json
from runesmith.canon import digest
from test_work_modes_measurements import ws, definition, configured, observe


def clock(monkeypatch, value):
    monkeypatch.setattr(metrics, '_now', lambda: value)


def report(ws, when='2026-09-27T04:00:00Z', value=4):
    return observe(ws, f'time,value\n{when},{value}\n')


def test_expired_data_is_not_freshened_by_measuring_it_now(ws, monkeypatch):
    clock(monkeypatch, '2026-09-27T06:00:00Z')
    definition(ws, time_field='time', max_age_hours=1, threshold={'op': 'lte', 'value': 6})
    receipt = report(ws)
    configured(ws, enabled=('optimize',))
    assert any('age' in r.lower() for r in modes.blockers(ws, modes.selected(ws, 'optimize')))
    assert receipt['status'] == 'measured' and receipt['threshold_met'] is True


def test_new_paste_blocks_old_result_before_any_new_measurement(ws):
    definition(ws); first = observe(ws); configured(ws, enabled=('optimize',))
    metrics.save_pasted_report(ws, 'metric', 'value\n900\n')
    assert any('report' in r.lower() for r in modes.blockers(ws, modes.selected(ws, 'optimize')))
    old = metrics.latest(ws, metrics.definitions(ws)['items'][0])
    assert old['id'] == first['id'] and old['value'] == first['value']


@pytest.mark.parametrize('limit', [0, -1, True, '24', float('inf')])
def test_age_limit_is_explicit_finite_and_positive(ws, limit):
    with pytest.raises(WorkspaceError, match='age'):
        definition(ws, time_field='time', max_age_hours=limit)


def test_age_limit_requires_a_data_timestamp_not_receipt_time(ws):
    with pytest.raises(WorkspaceError, match='timestamp'):
        definition(ws, max_age_hours=24)


def test_future_data_cannot_satisfy_age_rule(ws, monkeypatch):
    clock(monkeypatch, '2026-09-27T06:00:00Z')
    definition(ws, time_field='time', max_age_hours=24)
    report(ws, '2026-09-27T07:00:00Z'); configured(ws, enabled=('optimize',))
    assert any('future' in r.lower() for r in modes.blockers(ws, modes.selected(ws, 'optimize')))


def test_json_duplicate_keys_do_not_silently_change_a_measurement(ws):
    definition(ws, source_kind='paste_json')
    receipt = observe(ws, '[{"value":4,"value":900}]')
    assert receipt['status'] == 'error' and receipt['value'] is None


def test_data_changed_during_model_call_holds_answer_without_promotion(ws, monkeypatch):
    definition(ws); observe(ws); configured(ws, enabled=('optimize',))
    calls = []
    def answer(*_args):
        calls.append(1)
        observe(ws, 'value\n9\n')  # New, already measured evidence while author responds.
        return {k: 'A retained hypothesis' for k in ('hypothesis', 'expected_effect', 'evaluation', 'limitations')}, 'fixture-author'
    monkeypatch.setattr('runesmith.app.planner._call', answer)
    with pytest.raises(WorkspaceError, match='evidence'):
        modes.run(Worker(ws, EventBus()), 'optimize')
    saved = [_read_json(p, {}) for p in (ws.home / 'optimization-proposals').glob('*.json')]
    assert len(calls) == len(saved) == 1
    assert saved[0]['state'] == 'held' and saved[0]['answer']['hypothesis'] == 'A retained hypothesis'


def test_age_projection_expires_without_rewriting_receipt(ws, monkeypatch):
    clock(monkeypatch, '2026-09-27T04:30:00Z')
    item = definition(ws, time_field='time', max_age_hours=1, threshold={'op': 'lte', 'value': 6})
    receipt = report(ws)
    path = ws.home / 'measurement-receipts' / (receipt['id'] + '.json'); saved = path.read_bytes()
    fresh = metrics.latest(ws, item)['assessment']
    assert fresh['age_status'] == 'within_limit' and fresh['qualified_threshold_met'] is True
    clock(monkeypatch, '2026-09-27T05:00:00Z')
    assert metrics.latest(ws, item)['assessment']['age_status'] == 'within_limit'
    clock(monkeypatch, '2026-09-27T05:00:01Z')
    stale = metrics.latest(ws, item)
    assert stale['assessment']['age_status'] == 'expired'
    assert not stale['assessment']['usable'] and stale['assessment']['qualified_threshold_met'] is None
    assert stale['threshold_met'] is True and path.read_bytes() == saved


def test_without_age_policy_history_is_usable_but_not_claimed_current(ws):
    item = definition(ws, threshold={'op': 'gte', 'value': 0}); observe(ws)
    assessment = metrics.latest(ws, item)['assessment']
    assert assessment['age_status'] == 'not_configured' and assessment['usable']
    assert assessment['qualified_threshold_met'] is None


def test_dashboard_and_current_workspace_share_projection_without_raw_report_reads(ws, monkeypatch):
    clock(monkeypatch, '2026-09-27T06:00:00Z')
    item = definition(ws, time_field='time', max_age_hours=1); report(ws)
    monkeypatch.setattr(metrics, '_raw_report', lambda *_: pytest.fail('Viewing must not re-read a report'))
    last = metrics.latest(ws, item)
    row = dashboards.view(ws)['projects'][0]['measurements'][0]
    assert row['assessment'] == last['assessment'] and row['assessment']['age_status'] == 'expired'


def test_clock_views_and_identical_imports_do_not_purchase_another_hypothesis(ws, monkeypatch):
    clock(monkeypatch, '2026-09-27T04:10:00Z')
    definition(ws, time_field='time', max_age_hours=1); first = report(ws)
    configured(ws, enabled=('optimize',)); calls = []
    def answer(*_args):
        calls.append(1)
        return {k: 'Fixture hypothesis' for k in ('hypothesis', 'expected_effect', 'evaluation', 'limitations')}, 'fixture'
    monkeypatch.setattr('runesmith.app.planner._call', answer)
    worker = Worker(ws, EventBus()); one = modes.run(worker, 'optimize')
    clock(monkeypatch, '2026-09-27T04:55:00Z')
    assert report(ws)['id'] == first['id']  # Explicit same-payload import/remeasure.
    metrics.view(ws); dashboards.view(ws)
    two = modes.run(worker, 'optimize')
    assert two['proposal'] == one['proposal'] and len(calls) == 1
    clock(monkeypatch, '2026-09-27T05:01:00Z')
    with pytest.raises(WorkspaceError, match='age'):
        modes.run(worker, 'optimize')
    assert len(calls) == 1


@pytest.mark.parametrize('broken', [False, True])
def test_legacy_or_damaged_attempt_never_silently_retries(ws, monkeypatch, broken):
    definition(ws); observe(ws); configured(ws, enabled=('optimize',))
    def lost(*_args): raise RuntimeError('response lost')
    monkeypatch.setattr('runesmith.app.planner._call', lost)
    worker = Worker(ws, EventBus())
    with pytest.raises(RuntimeError): modes.run(worker, 'optimize')
    path, = (ws.home / 'optimization-proposals').glob('*.json')
    retained = _read_json(path, {}); legacy = copy.deepcopy(retained['packet'])
    for metric in legacy['context']['measurements']: metric['last'].pop('assessment', None)
    assert digest(legacy).split(':')[-1] == path.stem
    retained.pop('evidence_digest'); retained['packet'] = legacy
    if broken: path.write_text('{broken', encoding='utf-8')
    else: _write_json(path, retained)
    monkeypatch.setattr('runesmith.app.planner._call', lambda *_: pytest.fail('No new paid call'))
    if broken:
        with pytest.raises(WorkspaceError, match='unreadable'): modes.run(worker, 'optimize')
    else:
        assert 'unresolved' in modes.run(worker, 'optimize')['summary']


@pytest.mark.parametrize('relative', ['measurement-latest/metric.json', 'measurement-inputs/metric.json', 'receipt'])
def test_corrupt_saved_evidence_is_visible_and_blocks_without_repair(ws, relative):
    item = definition(ws); receipt = observe(ws); configured(ws, enabled=('optimize',))
    path = ws.home / (f'measurement-receipts/{receipt["id"]}.json' if relative == 'receipt' else relative)
    path.write_text('{"bad":1,"bad":2}', encoding='utf-8'); before = path.read_bytes()
    assert not metrics.latest(ws, item)['assessment']['usable']
    assert modes.blockers(ws, modes.selected(ws, 'optimize'))
    assert not dashboards.view(ws)['projects'][0]['measurements'][0]['assessment']['usable']
    assert path.read_bytes() == before


def test_historical_units_do_not_change_with_definition(ws):
    definition(ws); observe(ws); definition(ws, unit='seconds')
    row = dashboards.view(ws)['projects'][0]['measurements'][0]
    assert row['unit'] == 'ms' and row['current_definition'] is False


def test_edited_cached_receipt_is_not_reused_or_overwritten(ws):
    definition(ws); receipt = observe(ws)
    path = ws.home / 'measurement-receipts' / (receipt['id'] + '.json')
    _write_json(path, dict(receipt, value=900)); saved = path.read_bytes()
    with pytest.raises(WorkspaceError, match='conflicts'): metrics.measure(ws, 'metric')
    assert path.read_bytes() == saved


def test_new_paste_then_measure_restores_readiness_without_deleting_history(ws):
    item = definition(ws); first = observe(ws)
    path = ws.home / 'measurement-receipts' / (first['id'] + '.json'); before = path.read_bytes()
    metrics.save_pasted_report(ws, 'metric', 'value\n900\n')
    assert metrics.latest(ws, item)['assessment']['source_status'] == 'superseded'
    metrics.measure(ws, 'metric')
    assert metrics.latest(ws, item)['assessment']['usable']
    assert metrics.latest(ws, item)['value'] == 900 and path.read_bytes() == before


def test_local_file_is_explicitly_not_rechecked_by_refresh(ws, monkeypatch):
    path = ws.root / 'report.csv'; path.write_text('value\n4\n', encoding='utf-8')
    item = definition(ws, source_kind='csv', path='report.csv'); metrics.measure(ws, 'metric')
    path.write_text('value\n900\n', encoding='utf-8')
    monkeypatch.setattr(metrics, '_raw_report', lambda *_: pytest.fail('No raw report read'))
    row = metrics.latest(ws, item)
    assert row['value'] == 4 and row['assessment']['source_status'] == 'not_rechecked'
    assert 'Measure now' in row['assessment']['detail']


def test_expiring_evidence_holds_valid_returned_answer(ws, monkeypatch):
    clock(monkeypatch, '2026-09-27T04:55:00Z')
    definition(ws, time_field='time', max_age_hours=1); report(ws)
    configured(ws, enabled=('optimize',))
    def answer(*_args):
        clock(monkeypatch, '2026-09-27T05:01:00Z')
        return {k: 'Kept for review' for k in ('hypothesis', 'expected_effect', 'evaluation', 'limitations')}, 'fixture'
    monkeypatch.setattr('runesmith.app.planner._call', answer)
    with pytest.raises(WorkspaceError, match='age'): modes.run(Worker(ws, EventBus()), 'optimize')
    path, = (ws.home / 'optimization-proposals').glob('*.json')
    assert _read_json(path, {})['state'] == 'held'
    assert _read_json(path, {})['answer']['evaluation'] == 'Kept for review'


def test_receiving_report_notifies_open_pages_without_dispatch_or_payload_event(ws):
    from runesmith.app.server import api_measurement_report
    item = definition(ws); observe(ws)
    worker = Worker(ws, EventBus()); studio = SimpleNamespace(ws=ws, worker=worker, bus=worker.bus)
    api_measurement_report(studio, {}, {'text': 'value,private\n900,DO_NOT_BROADCAST\n'}, 'metric')
    event = worker.bus.recent[-1]
    assert event['kind'] == 'mission' and event['data'] == {'measurement': 'metric', 'report_received': True}
    assert not worker._jobs
    assert metrics.latest(ws, item)['assessment']['source_status'] == 'superseded'


@pytest.mark.parametrize('state', ['unresolved', 'started'])
def test_literal_pre_b16_attempt_keeps_original_key_and_makes_zero_calls(ws, monkeypatch, state):
    fixture = json.loads((Path(__file__).parent / 'fixtures' / 'pre_b16_optimization.json').read_text(encoding='utf-8'))
    attempt = json.loads(fixture['attempt_json']); receipt = json.loads(fixture['receipt_json'])
    assert attempt['id'] == 'c6527d18c97cc6bdeebe4a3825af0c44d13e39fae227a9d42bd4e53fdf08805e'
    assert digest(attempt['packet']).split(':')[-1] == attempt['id']
    assert receipt['parser'] == 'local-reports-v1' and 'assessment' not in attempt['packet']['context']['measurements'][0]['last']
    for rel, value in [('WORK_MODES.json', fixture['modes']), ('MEASUREMENTS.json', fixture['definitions']),
                       ('measurement-latest/metric.json', fixture['pointer']),
                       ('measurement-inputs/metric.json', fixture['input_pointer']),
                       (f'measurement-receipts/{receipt["id"]}.json', receipt)]:
        _write_json(ws.home / rel, value)
    attempt['state'] = state  # State is not part of the original packet identity.
    path = ws.home / 'optimization-proposals' / (attempt['id'] + '.json'); _write_json(path, attempt)
    original = path.read_bytes()
    # Project facts/name come from the original fixture; measurement projections
    # and memo identity use today's real code, not reconstructed "legacy" helpers.
    monkeypatch.setattr(modes, 'require_intent', lambda *_: copy.deepcopy(attempt['packet']['context']['intent']))
    monkeypatch.setattr('runesmith.app.planner._workspace_summary', lambda *_: copy.deepcopy(attempt['packet']['map']))
    monkeypatch.setattr('runesmith.app.planner._call', lambda *_: pytest.fail('Retained legacy attempt must prevent a new call'))
    answer = modes.run(Worker(ws, EventBus()), 'optimize')
    assert answer['proposal'] == attempt['id'] and state in answer['summary']
    assert path.read_bytes() == original


def test_recent_row_does_not_claim_whole_aggregate_is_recent(ws, monkeypatch):
    clock(monkeypatch, '2026-09-27T05:00:00Z')
    item = definition(ws, time_field='time', max_age_hours=1)
    old = '2025-01-01T00:00:00Z,100\n' * 10
    receipt = observe(ws, 'time,value\n' + old + '2026-09-27T04:30:00Z,1\n')
    assessment = metrics.latest(ws, item)['assessment']
    assert receipt['rows']['included'] == 11 and receipt['value'] == 91
    assert assessment['age_status'] == 'within_limit'
    assert 'newest selected data' in assessment['detail']
    assert 'does not prove completeness' in assessment['scope']
