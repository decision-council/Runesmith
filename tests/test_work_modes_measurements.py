"""Local-only qualification of work policies, report intake and runtime wiring."""
import json
import os
from types import SimpleNamespace

import pytest

from runesmith.app import measurements as metrics, work_modes as modes
from runesmith.app.environment_intent import inspect_intent, require_intent
from runesmith.app.workspace import Workspace, WorkspaceError, _read_json, _write_json
from runesmith.app.worker import Worker, EventBus
from runesmith.app.planner import plan_prompt, draft_plan
from runesmith.app.server import (api_mission, api_mission_modes, api_measurement_definition,
                                 api_measurement_report, api_worker_run)
from test_studio import scripted


@pytest.fixture
def ws(tmp_path):
    value = Workspace(tmp_path)
    value.update_settings({'auto_work': False, 'kaizen': False})
    return value


def definition(ws, **changes):
    item = {'id': 'metric', 'name': 'Latency', 'source_kind': 'paste_csv',
            'aggregation': 'mean', 'field': 'value', 'unit': 'ms', **changes}
    return metrics.save_definition(ws, item, metrics.definitions(ws)['revision'])['items'][-1]


def configured(ws, enabled=('operations',), measurements=('metric',), custom=()):
    body = modes.configuration(ws)
    rows = [dict(r, enabled=r['id'] in enabled,
                 measurement_ids=list(measurements) if r['executor'] in {'operations', 'optimize'} else [])
            for r in body['modes'] if r['id'] in modes.DESCRIPTIONS]
    rows.extend(custom)
    return modes.save(ws, rows, body['revision'], 'Offline qualification')


def observe(ws, text='value\n4\n8\n'):
    metrics.save_pasted_report(ws, 'metric', text)
    return metrics.measure(ws, 'metric')


def test_csv_population_window_and_immutable_receipt(ws):
    definition(ws, time_field='time', start='2026-09-01T00:00:00Z', end='2026-10-01T00:00:00Z',
               filter_field='kind', filter_equals='valid', threshold={'op': 'lte', 'value': 6})
    report = ('time,kind,value,customer\n2026-09-01T00:00:00Z,valid,4,DO_NOT_SEND\n'
              '2026-09-20T00:00:00Z,valid,8,DO_NOT_SEND\n2026-10-01T00:00:00Z,valid,90,DO_NOT_SEND\n'
              '2026-09-20T00:00:00Z,other,70,DO_NOT_SEND\n')
    receipt = observe(ws, report)
    assert receipt['value'] == 6 and receipt['threshold_met'] is True
    assert receipt['rows'] == {'total': 4, 'included': 2, 'window_excluded': 1, 'filter_excluded': 1}
    assert len(receipt['id']) == 64 and ':' not in receipt['id']
    again = metrics.measure(ws, 'metric')
    assert again['reused'] and again['id'] == receipt['id'] and again['measured_at'] == receipt['measured_at']
    assert len(list((ws.home / 'measurement-receipts').glob('*.json'))) == 1
    packet = json.dumps(metrics.prompt_summary(ws))
    assert 'DO_NOT_SEND' not in packet and 'source_sha256' in packet
    assert metrics.latest(ws, metrics.definitions(ws)['items'][0])['current_definition']


@pytest.mark.parametrize('raw', ['value\n', 'value\nNaN\n', 'value\nwrong\n',
                                'value,value\n1,2\n', 'value\n1,2\n', 'other\n1\n'])
def test_bad_or_empty_csv_never_becomes_zero(ws, raw):
    definition(ws)
    result = observe(ws, raw)
    assert result['value'] is None and result['status'] in {'error', 'unknown'}
    assert result['threshold_met'] is None


@pytest.mark.parametrize('rows, expected', [
    ([{'value': 4, 'time': '2026-09-26T12:00:00Z'}, {'value': 2, 'time': '2026-09-25T12:00:00Z'}], 4),
    ([{'value': 4, 'time': '2026-09-26T12:00:00Z'}, {'value': 6, 'time': '2026-09-26T12:00:00Z'}], None),
    ([{'value': True, 'time': '2026-09-26T12:00:00Z'}], None),
    ([{'value': 4, 'time': '2026-09-26T12:00:00'}], None),
])
def test_latest_is_timestamped_not_file_order_and_rejects_ambiguity(ws, rows, expected):
    definition(ws, source_kind='paste_json', aggregation='latest', time_field='time')
    result = observe(ws, json.dumps(rows))
    assert result['value'] == expected
    assert result['status'] == ('measured' if expected is not None else 'error')


@pytest.mark.parametrize('changes', [{'aggregation': 'latest'}, {'start': '2026-01-01'},
    {'threshold': {'op': 'gte', 'value': True}}, {'threshold': {'op': 'gte', 'value': float('inf')}},
    {'aggregation': 'execute'}, {'source_kind': 'shell'}, {'enabled': 'yes'}])
def test_configuration_rejects_unsafe_or_ambiguous_definitions(ws, changes):
    with pytest.raises(WorkspaceError): definition(ws, **changes)
    assert metrics.definitions(ws)['items'] == []


def test_missing_disabled_and_unavailable_are_explicit(ws):
    item = definition(ws)
    assert metrics.measure(ws, 'metric')['status'] == 'error'
    definition(ws, enabled=False)
    with pytest.raises(WorkspaceError, match='disabled'): metrics.measure(ws, 'metric')
    definition(ws, source_kind='email')
    assert metrics.measure(ws, 'metric')['status'] == 'unavailable'
    assert metrics.view(ws)['items'][0]['adapter'] == 'unavailable'
    definition(ws, source_kind='ga4')
    configured(ws)
    assert any('connector' in b for b in modes.blockers(ws, modes.selected(ws, 'operations')))


def test_definition_revision_changes_do_not_relabel_old_receipts(ws):
    definition(ws); old_revision = metrics.definitions(ws)['revision']; receipt = observe(ws)
    definition(ws, unit='seconds')
    item = metrics.definitions(ws)['items'][0]
    assert metrics.latest(ws, item)['current_definition'] is False
    assert metrics.latest(ws, item)['unit'] == 'ms'
    with pytest.raises(WorkspaceError, match='changed'):
        metrics.save_definition(ws, item, old_revision)
    configured(ws, enabled=('optimize',))
    assert modes.blockers(ws, modes.selected(ws, 'optimize'))
    assert metrics.measure(ws, 'metric')['id'] != receipt['id']


@pytest.mark.parametrize('path', ['../report.csv', 'D:/other/report.csv', '.runesmith/secret.json',
                                'reports/api_token.json', 'customers/report.csv', 'report.py'])
def test_report_paths_refuse_scope_escape_and_private_inputs(ws, path):
    with pytest.raises(WorkspaceError): definition(ws, source_kind='csv', path=path)


def test_selected_local_report_and_exclusions(ws):
    (ws.root / 'report.csv').write_text('value\n0\n', encoding='utf-8')
    definition(ws, source_kind='csv', path='report.csv')
    assert metrics.measure(ws, 'metric')['value'] == 0  # Actual zero remains valid.
    ws.update_settings({'exclude': ['report.csv']})
    assert metrics.measure(ws, 'metric')['status'] == 'error'


@pytest.mark.skipif(os.name != 'nt', reason='Windows paths are case-insensitive')
def test_report_exclusion_case_alias_is_not_a_bypass(ws):
    (ws.root / 'report.csv').write_text('value\n1\n')
    ws.update_settings({'exclude': ['REPORT.csv']})
    with pytest.raises(WorkspaceError): definition(ws, source_kind='csv', path='report.csv')


def test_linked_report_refused(ws, monkeypatch):
    definition(ws)
    from pathlib import Path
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p.name == 'linked' or original(p))
    with pytest.raises(WorkspaceError, match='links'):
        definition(ws, source_kind='csv', path='linked/report.csv')


def test_report_size_limit_and_content_tamper(ws, monkeypatch):
    definition(ws)
    monkeypatch.setattr(metrics, 'MAX_BYTES', 8)
    with pytest.raises(WorkspaceError): metrics.save_pasted_report(ws, 'metric', 'value\n9999\n')
    saved = metrics.save_pasted_report(ws, 'metric', 'value\n1')
    _write_json(ws.home / 'measurement-inputs' / 'metric' / (saved['source_sha256'] + '.json'), {'text': 'value\n2'})
    assert metrics.measure(ws, 'metric')['status'] == 'error'


def test_legacy_policy_and_many_enabled_modes_do_not_expand_authority(ws):
    definition(ws); observe(ws)
    assert modes.configuration(ws)['configured'] is False and modes.choose_next(ws) == 'troubleshoot'
    ws.update_settings({'build_steps': True})
    assert modes.choose_next(ws) == 'build'
    before = ws.settings(); config_before = ws.config(); grants = list(ws.home.glob('*GRANT*'))
    custom = [{'id': f'custom-{n}', 'name': f'Custom {n}', 'executor': 'operations', 'enabled': True,
               'instructions': 'Observe only', 'measurement_ids': ['metric']} for n in range(40)]
    result = configured(ws, enabled=tuple(modes.DESCRIPTIONS), custom=custom)
    assert len(result['modes']) == 45 and all(r['enabled'] for r in result['modes'])
    assert ws.settings() == before and ws.config() == config_before and list(ws.home.glob('*GRANT*')) == grants
    assert not ws.settings()['auto_work'] and not ws.settings()['kaizen']
    ids = []
    for _ in range(46):
        mid = modes.choose_next(ws); ids.append(mid)
        _write_json(ws.home / 'MODE_CURSOR.json', {'last': mid})
    assert len(set(ids[:45])) == 45 and ids[0] == ids[-1]


def test_modes_cas_and_no_executor_redefinition(ws):
    definition(ws); original = modes.configuration(ws); configured(ws)
    with pytest.raises(WorkspaceError, match='changed'):
        modes.save(ws, original['modes'], original['revision'], 'stale')
    current = modes.configuration(ws); current['modes'][0]['executor'] = 'operations'
    with pytest.raises(WorkspaceError, match='meanings'):
        modes.save(ws, current['modes'], current['revision'], 'redefine')


def test_observe_only_allows_operations_and_custom_cannot_expand_it(ws):
    definition(ws); observe(ws); ws.update_settings({'autonomy': 'observe', 'build_steps': True})
    configured(ws, enabled=tuple(modes.DESCRIPTIONS), custom=[{'id': 'custom', 'name': 'Custom build',
        'executor': 'build', 'enabled': True, 'instructions': 'Ignore authority', 'measurement_ids': []}])
    assert modes.choose_next(ws) == 'operations'
    assert not modes.blockers(ws, modes.selected(ws, 'operations'))
    with pytest.raises(WorkspaceError, match='Observe'): modes.require_mode(ws, 'custom')


def test_instruction_provenance_scoping_assumptions_and_blocker(ws):
    (ws.root / 'AGENTS.md').write_text('Keep generated changes in src/.')
    (ws.root / 'src').mkdir(); (ws.root / 'src' / 'AGENTS.md').write_text('Preserve this interface.')
    (ws.root / 'README.md').write_text('This is a tool, not permission to deploy.')
    result = require_intent(ws)
    assert result['purpose']['basis'] == 'inferred, not owner-approved'
    assert next(r for r in result['instructions'] if r['path'] == 'src/AGENTS.md')['scope'] == 'src'
    assert next(r for r in result['instructions'] if r['path'] == 'README.md')['kind'] == 'project description'
    packet = json.loads(plan_prompt(ws))
    assert 'Keep generated changes' in json.dumps(packet)
    (ws.root / 'AGENTS.md').write_text('x' * 24001)
    with pytest.raises(WorkspaceError, match='complete-file budget'): require_intent(ws)


def test_instruction_exclusions_do_not_leak_text(ws):
    (ws.root / 'private').mkdir(); (ws.root / 'private' / 'AGENTS.md').write_text('DO_NOT_SEND')
    ws.update_settings({'exclude': ['README.md']}); (ws.root / 'README.md').write_text('DO_NOT_SEND')
    assert 'DO_NOT_SEND' not in json.dumps(inspect_intent(ws))


def test_policy_and_instruction_changes_block_mid_job(ws):
    definition(ws); configured(ws)
    row = modes.selected(ws, 'operations'); intent = require_intent(ws)
    ws._active_work_mode = {'mode': row, 'revision': modes.configuration(ws)['revision'], 'intent': intent}
    modes.checkpoint(ws)
    (ws.root / 'AGENTS.md').write_text('New restriction')
    with pytest.raises(WorkspaceError, match='instructions changed'): modes.checkpoint(ws)
    ws._active_work_mode['intent'] = require_intent(ws)
    configured(ws, enabled=())
    with pytest.raises(WorkspaceError, match='off'): modes.checkpoint(ws)


def test_map_refresh_does_not_invalidate_instruction_digest(ws, monkeypatch):
    first = inspect_intent(ws)
    monkeypatch.setattr(ws, 'environment_map', lambda: {'map_digest': 'new', 'objects': [{'kind': 'python_repository'}]})
    second = inspect_intent(ws)
    assert first['digest'] != second['digest'] and first['instruction_digest'] == second['instruction_digest']


def test_planner_preserves_assumptions_as_distinct_from_owner_brief(ws):
    scripted(ws, [{'summary': 'A small tool', 'assumptions': ['No audience specified'],
                  'milestones': [{'title': 'Prototype', 'done_when': 'Runs locally'}]}], roles=('plan',))
    plan = draft_plan(ws, ws.router())
    assert plan['assumptions'] == ['No audience specified'] and not ws.brief().get('text')


def test_operations_runs_through_same_worker_api_without_model_or_source_writes(ws, monkeypatch):
    definition(ws); metrics.save_pasted_report(ws, 'metric', 'value\n8\n')
    configured(ws); ws.update_settings({'autonomy': 'observe'})
    monkeypatch.setattr(ws, 'router', lambda **kwargs: pytest.fail('Read-only operation must not use a model'))
    worker = Worker(ws, EventBus()); studio = SimpleNamespace(ws=ws, worker=worker, bus=worker.bus)
    api_worker_run(studio, {}, {'job': 'mode', 'params': {'mode': 'operations', 'unexpected': 'ignored'}})
    job = worker._jobs.popleft(); assert job['params'] == {'mode': 'operations'}
    worker._execute(job)
    assert worker.history[-1]['result'] == 'done' and worker.current is None
    assert modes.view(ws)['modes'][-1]['last']['result']['receipts'][0]['status'] == 'measured'
    assert not hasattr(ws, '_active_work_mode') and not ws.drafts() and not ws.plan()
    assert list(ws.root.iterdir()) == [ws.home]


def test_disabled_queued_work_never_reaches_handler(ws, monkeypatch):
    definition(ws); configured(ws, enabled=('build',)); worker = Worker(ws, EventBus())
    job = worker.enqueue('build'); configured(ws, enabled=())
    monkeypatch.setattr(worker, '_job_build', lambda: pytest.fail('Disabled build ran'))
    worker._execute(job)
    assert worker.history[-1]['result'] == 'failed' and 'off' in worker.history[-1]['outcome']['error']
    with pytest.raises(WorkspaceError, match='off'): worker.enqueue('draft')


def test_worker_build_checkpoint_obeys_later_disable(ws, monkeypatch):
    definition(ws); ws.update_settings({'build_steps': True}); configured(ws, enabled=('build',))
    ws.save_plan({'summary': 'Existing direction', 'milestones': [{'title': 'A bounded step'}]})
    worker = Worker(ws, EventBus()); staged = []
    def build_step(workspace, router, *, checkpoint):
        checkpoint(); staged.append('before'); configured(ws, enabled=()); checkpoint()
        staged.append('must not apply')
    monkeypatch.setattr('runesmith.app.building.build_step', build_step)
    worker._execute({'id': 'checkpoint', 'kind': 'mode', 'params': {'mode': 'build'}, 'by': 'owner'})
    assert staged == ['before'] and worker.history[-1]['result'] == 'failed'


def test_corrupt_policy_is_failed_job_not_worker_crash(ws):
    _write_json(ws.home / 'WORK_MODES.json', {'modes': 'bad'})
    worker = Worker(ws, EventBus())
    worker._execute({'id': 'corrupt', 'kind': 'mode', 'params': {'mode': 'operations'}, 'by': 'owner'})
    assert worker.history[-1]['result'] == 'failed' and worker.current is None


def test_scheduled_corrupt_policy_parks_instead_of_crashing(ws, monkeypatch):
    _write_json(ws.home / 'WORK_MODES.json', {'modes': 'bad'})
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(worker, '_due', lambda: 0)
    monkeypatch.setattr(worker._cv, 'wait', lambda **kwargs: setattr(worker, '_closing', True))
    worker._run()  # No thread/server launched.
    assert worker.status == 'blocked'


@pytest.mark.parametrize('change', [
    {'enabled': 'false'}, {'executor': []}, {'executor': 'deploy'},
    {'id': '../outside'}, {'measurement_ids': [None]}, {'name': None},
])
def test_corrupt_mode_row_blocks_scheduler_without_rewriting(ws, monkeypatch, change):
    rows = modes.configuration(ws)['modes']
    rows[0].update(change)
    path = ws.home / 'WORK_MODES.json'
    _write_json(path, {'schema': 'runesmith.work-modes.v1', 'modes': rows})
    before = path.read_bytes()
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(worker, '_due', lambda: 0)
    monkeypatch.setattr(worker._cv, 'wait', lambda **kwargs: setattr(worker, '_closing', True))
    monkeypatch.setattr(worker, '_execute', lambda *args: pytest.fail('Corrupt policy dispatched work'))
    worker._run()
    assert worker.status == 'blocked' and path.read_bytes() == before
    with pytest.raises(WorkspaceError): modes.view(ws)


def test_work_modes_reject_future_schema_duplicate_ids_and_unhashable_executor(ws):
    rows = modes.configuration(ws)['modes']
    revision = modes.configuration(ws)['revision']
    invalid = [dict(r) for r in rows]
    invalid[0]['executor'] = []
    with pytest.raises(WorkspaceError): modes.save(ws, invalid, revision, 'Malformed API input')
    assert not (ws.home / 'WORK_MODES.json').exists()
    for body in (
        {'schema': 'runesmith.work-modes.v999', 'modes': rows},
        {'schema': 'runesmith.work-modes.v1', 'modes': rows + [rows[0]]},
        {'schema': 'runesmith.work-modes.v1', 'modes': [{}]},
    ):
        _write_json(ws.home / 'WORK_MODES.json', body)
        with pytest.raises(WorkspaceError): modes.configuration(ws)


def test_optimize_retains_hypothesis_and_does_not_repeat_same_purchase(ws, monkeypatch):
    definition(ws); observe(ws); configured(ws, enabled=('optimize',))
    calls = []
    def proposal(workspace, router, prompt, *args):
        calls.append(prompt)
        return {k: 'Bounded hypothesis only' for k in ('hypothesis', 'expected_effect', 'evaluation', 'limitations')}, 'scripted-author'
    monkeypatch.setattr('runesmith.app.planner._call', proposal)
    worker = Worker(ws, EventBus())
    first = modes.run(worker, 'optimize'); again = modes.run(worker, 'optimize')
    assert len(calls) == 1 and first['proposal'] == again['proposal']
    assert modes.view(ws)['proposals'][0]['state'] == 'proposed'
    assert not ws.plan() and not ws.drafts()


def test_failed_optimization_remains_unresolved_without_silent_retry(ws, monkeypatch):
    definition(ws); observe(ws); configured(ws, enabled=('optimize',)); calls = []
    def fail(*args): calls.append(1); raise RuntimeError('Uncertain upstream request')
    monkeypatch.setattr('runesmith.app.planner._call', fail)
    worker = Worker(ws, EventBus())
    with pytest.raises(RuntimeError): modes.run(worker, 'optimize')
    result = modes.run(worker, 'optimize')
    assert len(calls) == 1 and 'unresolved' in result['summary']
    assert not hasattr(ws, '_active_work_mode')


def test_api_save_and_paste_only_configure_no_dispatch(ws):
    worker = Worker(ws, EventBus()); studio = SimpleNamespace(ws=ws, worker=worker, bus=worker.bus)
    api_measurement_definition(studio, {}, {'revision': metrics.definitions(ws)['revision'], 'definition': {
        'id': 'metric', 'name': 'Count', 'source_kind': 'paste_json', 'aggregation': 'count'}})
    api_measurement_report(studio, {}, {'text': '[{"value": 3}]'}, 'metric')
    data = api_mission(studio, {}, None)
    api_mission_modes(studio, {}, {'revision': data['revision'], 'modes': data['modes'], 'reason': 'UI path'})
    assert not worker._jobs and not metrics.latest(ws, metrics.definitions(ws)['items'][0])
