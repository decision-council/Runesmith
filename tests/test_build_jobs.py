"""Exact-path qualification without any live provider or training-home writes."""
import json

import pytest

from runesmith.app import building
from runesmith.app.build_jobs import BuildJob, execute_build_job, validate_checkpoint
from runesmith.app.planner import draft_files
from runesmith.app.worker import EventBus, Worker, StopRequested
from runesmith.app.workspace import WorkspaceError
from test_build_steps import setup, enable


@pytest.mark.parametrize('kind,params', [
    ('unknown', {}), ('supplement', {}), ('build', {'draft_id': 1}),
    ('build', {'author_only': 'true'}), ('build', {'author_only': 1}),
    ('build', {'draft_id': 'd1', 'author_only': True}),
    ('build', {'draft_id': '../candidate'}), ('build', {'draft_id': '..'}), ('build', {'project_timeout_s': 600}),
    ('supplement', {'draft_id': 'd1', 'reason': 'Reason', 'instrument': 'author', 'author_only': 'false'}),
    ('resume_check', {'draft_id': 'd1', 'reason': ' '}),
    ('resume_check', {'draft_id': 'd1', 'reason': 'x' * 2001}),
    ('allocate_check', {'draft_id': 'd1', 'quote_id': None, 'reason': 'Reason'}),
])
def test_invalid_request_does_not_reach_queue_or_create_allocations(tmp_path, kind, params):
    ws = setup(tmp_path); worker = Worker(ws, EventBus())
    before = {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    with pytest.raises((WorkspaceError, ValueError)):
        worker.enqueue(kind, **params)
    assert not worker._jobs and worker.current is None
    assert before == {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}


def test_request_copies_inputs_and_is_immutable():
    params = {'draft_id': 'd1'}; job = BuildJob('build', params)
    params['draft_id'] = 'changed'
    assert job.params['draft_id'] == 'd1'
    with pytest.raises(TypeError): job.params['draft_id'] = 'other'


def test_author_only_uses_ordinary_receipt_and_reuses_waiting_draft(tmp_path, monkeypatch):
    ws = setup(tmp_path, acceptance=True); enable(ws)
    settings = ws.settings(); original = ws.router; backoffs = []
    def router(**kwargs):
        backoffs.append(kwargs['backoff_s']); return original(**kwargs)
    monkeypatch.setattr(ws, 'router', router)
    monkeypatch.setattr(building, '_check_and_record', lambda *a, **kw: pytest.fail('No executable checks'))
    first = execute_build_job(ws, BuildJob('build', {'author_only': True}))
    second = execute_build_job(ws, BuildJob('build', {'author_only': True}))
    assert first['draft'] == second['draft'] and first['author_only']
    assert backoffs == [(), ()]
    attempts = list((ws.home / 'build-attempts').glob('*.json'))
    assert len(attempts) == 1
    receipt = json.loads(attempts[0].read_text())
    assert receipt['state'] == 'answered' and receipt['draft'] == first['draft']
    assert not ws._draft(first['draft']).get('verification')
    assert ws.plan()['milestones'][0]['status'] == 'open'
    assert ws.settings() == settings and not (tmp_path / 'app.py').exists()


@pytest.mark.parametrize('spent', [1, 3])
def test_waiting_draft_with_different_context_cannot_hide_new_attempt(tmp_path, monkeypatch, spent):
    from runesmith.app.workspace import _write_json
    ws = setup(tmp_path); enable(ws)
    first = execute_build_job(ws, BuildJob('build', {'author_only':True}))
    original = ws._draft(first['draft'])
    # A waiting draft may bind an older selected packet on the same full source.
    ws._save_draft_state(original, 'waiting', context_digest='f'*64)
    receipt = json.loads(next((ws.home/'build-attempts').glob('*.json')).read_text())
    for i in range(spent-1): _write_json(ws.home/'build-attempts'/f'consumed{i}.json', dict(receipt,state='failed'))
    if spent == 3:
        monkeypatch.setattr(building,'draft_files',lambda *a,**kw:pytest.fail('Exhausted scope cannot author through a non-reusable waiting draft'))
    result = execute_build_job(ws, BuildJob('build', {'author_only':True}))
    if spent == 3:
        assert result['replan_needed']
        assert len(list((ws.home/'build-attempts').glob('*.json'))) == 3
    else:
        assert result['draft'] != first['draft']
        attempts = [json.loads(p.read_text()) for p in (ws.home/'build-attempts').glob('*.json')]
        assert len(attempts) == 2
        assert any(a.get('draft') == result['draft'] and a['state']=='answered' for a in attempts)


def test_author_only_exhaustion_cannot_schedule_breakdown(tmp_path, monkeypatch):
    from runesmith.app.workspace import _write_json
    ws = setup(tmp_path); enable(ws); ws.update_settings({'auto_work': True})
    result = execute_build_job(ws, BuildJob('build', {'author_only': True}))
    draft = ws._draft(result['draft']); ws._save_draft_state(draft, 'needs_revision')
    attempt = json.loads(next((ws.home/'build-attempts').glob('*.json')).read_text())
    for i in range(2): _write_json(ws.home/'build-attempts'/f'consumed{i}.json', dict(attempt, state='failed'))
    monkeypatch.setattr(building, 'draft_files', lambda *a, **kw: pytest.fail('No fourth attempt'))
    monkeypatch.setattr(Worker, 'enqueue', lambda *a, **kw: pytest.fail('No follow-on job'))
    worker = Worker(ws, EventBus())
    job = worker._execute({'id':'bounded','kind':'build','params':{'author_only':True}})
    assert job['outcome']['replan_needed']
    assert len(list((ws.home/'build-attempts').glob('*.json'))) == 3


@pytest.mark.parametrize('spent', [1, 3])
@pytest.mark.parametrize('change', ['focus', 'source'])
def test_matched_draft_is_reused_without_a_second_author_entry(tmp_path, monkeypatch, spent, change):
    from runesmith.app.workspace import _write_json
    from runesmith.app.source_focus import save_focus
    from runesmith.app.snapshots import collect_snapshot
    ws = setup(tmp_path); enable(ws)
    for name in ('a.py','b.py','c.py'): (tmp_path/name).write_text('# '+name+'\n'+'# comment\n'*1800)
    first = execute_build_job(ws, BuildJob('build', {'author_only':True}))
    original = ws._draft(first['draft']); snapshot = original['snapshot_digest']
    receipt = json.loads(next((ws.home/'build-attempts').glob('*.json')).read_text())
    for i in range(spent-1): _write_json(ws.home/'build-attempts'/f'consumed{i}.json', dict(receipt,state='failed'))
    source_context = building.source_context
    def boundary(workspace):
        context = source_context(workspace)
        if change == 'focus':
            save_focus(ws,['c.py'],context['snapshot_digest'],'Change the selected input after initial observation')
            assert source_context(ws)['digest'] != context['digest']
        else:
            (tmp_path/'a.py').write_text('# external edit\n')
        return context
    monkeypatch.setattr(building,'source_context',boundary)
    monkeypatch.setattr(building,'draft_files',lambda *a,**kw:pytest.fail('Matched draft must never re-enter authoring'))
    monkeypatch.setattr(building,'_check_and_record',lambda *a,**kw:pytest.fail('Author-only cannot check or apply'))
    result = execute_build_job(ws, BuildJob('build', {'author_only':True}))
    assert result['draft'] == first['draft']
    assert ws._draft(first['draft'])['snapshot_digest'] == snapshot
    assert len(list((ws.home/'build-attempts').glob('*.json'))) == spent
    assert not (tmp_path/'app.py').exists()
    if change == 'source': assert collect_snapshot(ws)['digest'] != snapshot


@pytest.mark.parametrize('stale', [False, True])
def test_ordinary_cached_build_still_checks_and_never_authors(tmp_path, monkeypatch, stale):
    ws = setup(tmp_path,acceptance=True); enable(ws)
    first = execute_build_job(ws,BuildJob('build',{'author_only':True}))
    source_context = building.source_context
    def boundary(workspace, **kwargs):
        context=source_context(workspace, **kwargs)
        if stale: (tmp_path/'external.py').write_text('# concurrent external edit\n')
        return context
    monkeypatch.setattr(building,'source_context',boundary)
    monkeypatch.setattr(building,'draft_files',lambda *a,**kw:pytest.fail('Cached path must not author'))
    result=execute_build_job(ws,BuildJob('build',{}))
    assert result['draft']==first['draft']
    assert len(list((ws.home/'build-attempts').glob('*.json'))) == 1
    if stale:
        assert not result.get('advanced') and not (tmp_path/'app.py').exists()
        assert not ws._draft(first['draft']).get('verified')
    else:
        assert result['verification']['status']=='acceptance_passed' and result['advanced']


def test_cache_miss_reserves_attempt_before_author_entry(tmp_path,monkeypatch):
    ws=setup(tmp_path);enable(ws);original=building.draft_files;seen=[]
    def observed(workspace,router,milestone_id,**kwargs):
        attempt=kwargs['attempt_id'];record=json.loads((ws.home/'build-attempts'/attempt).read_text())
        assert record['state']=='started';seen.append(attempt)
        return original(workspace,router,milestone_id,**kwargs)
    monkeypatch.setattr(building,'draft_files',observed)
    result=execute_build_job(ws,BuildJob('build',{'author_only':True}))
    assert len(seen)==1
    assert json.loads((ws.home/'build-attempts'/seen[0]).read_text())['draft']==result['draft']


def test_author_only_synchronous_path_preserves_enabled_grants(tmp_path, monkeypatch):
    from runesmith.app.build_jobs import run_synchronous_build_job
    ws = setup(tmp_path, acceptance=True); enable(ws)
    before = (ws.home/'BUILD_GRANT.json').read_bytes()
    monkeypatch.setattr(building, '_check_and_record', lambda *a, **kw: pytest.fail('No checks/apply'))
    job = run_synchronous_build_job(ws.root, BuildJob('build', {'author_only':True}), home=ws.home)
    assert job['result'] == 'done' and job['outcome']['author_only']
    assert (ws.home/'BUILD_GRANT.json').read_bytes() == before
    assert not (ws.home/'STUDIO_CURRENT.json').exists()


def test_author_only_without_plan_does_not_invent_planning_call(tmp_path, monkeypatch):
    ws = setup(tmp_path); (ws.home/'PLAN.json').unlink()
    monkeypatch.setattr(building, 'draft_plan', lambda *a, **kw: pytest.fail('No implicit planning'))
    with pytest.raises(WorkspaceError, match='Save a plan'):
        building.build_step(ws, ws.router(), author_only=True)


def test_studio_api_preserves_author_only_and_checks_its_type(tmp_path):
    from types import SimpleNamespace
    from runesmith.app.server import api_worker_run
    ws = setup(tmp_path); worker = Worker(ws, EventBus()); studio = SimpleNamespace(worker=worker)
    job = api_worker_run(studio, {}, {'job':'build','params':{'author_only':True}})
    assert job['params'] == {'author_only':True}
    assert dict(BuildJob('build', job['params']).params) == {'draft_id':None,'author_only':True}
    with pytest.raises(WorkspaceError):
        api_worker_run(studio, {}, {'job':'build','params':{'author_only':'false'}})
    assert len(worker._jobs) == 1


async def async_hook(): pass


@pytest.mark.parametrize('hook', [lambda phase: None, async_hook, None, 'not a callback'])
def test_bad_callback_refused_before_model_or_domain_allocation(tmp_path, monkeypatch, hook):
    ws = setup(tmp_path); enable(ws)
    before = {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    monkeypatch.setattr(ws, 'router', lambda **kwargs: pytest.fail('Must not construct a router'))
    with pytest.raises(WorkspaceError, match='no arguments'):
        execute_build_job(ws, BuildJob('build', {}), checkpoint=hook)
    assert before == {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}


def test_bad_phase_hook_refused_before_stage_directory(tmp_path):
    ws = setup(tmp_path, acceptance=True); enable(ws)
    draft = draft_files(ws, ws.router())
    with pytest.raises(WorkspaceError, match='phase_checkpoint'):
        building.verify_draft(ws, draft, phase_checkpoint=lambda phase: None)
    assert not (ws.home / 'build-runs').exists()


@pytest.mark.parametrize('via_worker', [False, True])
def test_real_project_owner_checks_and_guarded_apply_share_entry(tmp_path, monkeypatch, via_worker):
    ws = setup(tmp_path, acceptance=True); enable(ws)
    ws.update_settings({'auto_work': False, 'kaizen': False})
    calls = []
    if via_worker:
        import runesmith.app.build_jobs as jobs
        original = jobs.execute_build_job
        def observed(workspace, request, **kwargs):
            calls.append(request.kind)
            return original(workspace, request, **kwargs)
        monkeypatch.setattr(jobs, 'execute_build_job', observed)
        worker = Worker(ws, EventBus())
        worker._execute({'id': 'fixture', 'kind': 'build', 'params': {}, 'by': 'owner'})
        assert worker.history[-1]['result'] == 'done' and calls == ['build']
        assert worker.history[-1]['outcome']['advanced']
    else:
        result = execute_build_job(ws, BuildJob('build', {}), checkpoint=lambda: calls.append('checkpoint'))
        assert result['advanced'] and len(calls) >= 5
    draft = ws.drafts()[0]; receipt = draft['verification']
    assert draft['state'] == 'applied' and receipt['status'] == 'acceptance_passed'
    assert receipt['project_checks']['ran'] == receipt['acceptance']['ran'] == 1
    assert ws.plan()['milestones'][0]['status'] == 'done'


def test_saved_candidate_checks_never_construct_router_or_apply(tmp_path, monkeypatch):
    ws = setup(tmp_path, acceptance=True); enable(ws)
    draft = draft_files(ws, ws.router())
    monkeypatch.setattr(ws, 'router', lambda **kw: pytest.fail('Check-only job called a model'))
    result = execute_build_job(ws, BuildJob('build', {'draft_id': draft['id']}))
    assert result['verification']['status'] == 'acceptance_passed'
    assert not result.get('advanced') and not (tmp_path / 'app.py').exists()
    assert ws.plan()['milestones'][0]['status'] == 'open'


@pytest.mark.parametrize('control', ['stop', 'pause', 'disable'])
def test_phase_boundary_preserves_completed_project_evidence_without_owner_run(tmp_path, monkeypatch, control):
    ws = setup(tmp_path, acceptance=True); enable(ws)
    draft = draft_files(ws, ws.router()); worker = Worker(ws, EventBus())
    original = building._run_checks; phases = []
    def checked(stage, kind, logs, **kwargs):
        phases.append(kind)
        result = original(stage, kind, logs, **kwargs)
        if control == 'stop': worker.stop_current()
        elif control == 'pause': worker.pause()
        else: ws.update_settings({'build_steps': False})
        return result
    monkeypatch.setattr(building, '_run_checks', checked)
    with pytest.raises((StopRequested, WorkspaceError)):
        worker._job_build(draft_id=draft['id'])
    assert phases == ['project'] and not (tmp_path / 'app.py').exists()
    saved = ws._draft(draft['id']); receipt = saved['verification']
    assert receipt['status'] == 'inconclusive' and receipt['interrupted_before'] == 'owner acceptance'
    assert receipt['project_checks']['ran'] == 1 and receipt['project_checks']['ok']
    assert receipt['acceptance'] is None and not saved['verified']
    assert json.loads((ws.home / receipt['evidence_dir'] / 'VERIFICATION.json').read_text()) == receipt
    ws.update_settings({'build_steps': True})
    # A later ordinary build may not erase uncertainty by reauthoring/rechecking.
    monkeypatch.setattr(building, '_run_checks', lambda *a, **kw: pytest.fail('No automatic check replay'))
    result = execute_build_job(ws, BuildJob('build', {}))
    assert result['verification_required'] and result['draft'] == draft['id']


def test_failed_call_recorder_rejected_before_build(tmp_path):
    ws = setup(tmp_path)
    with pytest.raises(WorkspaceError, match='call recorder'):
        execute_build_job(ws, BuildJob('build', {}), on_call=lambda: None)
    assert not (ws.home / 'build-attempts').exists()


def test_queue_and_execute_both_enforce_changed_mode(tmp_path, monkeypatch):
    from runesmith.app.work_modes import configuration, save
    ws = setup(tmp_path); enable(ws); worker = Worker(ws, EventBus())
    job = worker.enqueue('build')
    policy = configuration(ws)
    modes = [dict(row, enabled=False) if row['executor'] == 'build' else row for row in policy['modes']]
    save(ws, modes, policy['revision'], 'Disable build before executing the queued job.')
    monkeypatch.setattr(ws, 'router', lambda **kw: pytest.fail('Disabled mode dispatched'))
    with pytest.raises(WorkspaceError, match='off'): execute_build_job(ws, BuildJob('build', {}))
    worker._execute(job)
    assert worker.history[-1]['result'] == 'failed' and not (ws.home / 'build-attempts').exists()


def test_synchronous_runner_uses_worker_history_and_never_schedules_followup(tmp_path, monkeypatch):
    from runesmith.app.build_jobs import run_synchronous_build_job
    ws = setup(tmp_path, acceptance=True); enable(ws)
    ws.update_settings({'auto_work': True})
    monkeypatch.setattr(Worker, 'start', lambda *a: pytest.fail('No resident/background worker permitted'))
    monkeypatch.setattr(Worker, 'enqueue', lambda *a, **kw: pytest.fail('One job only; no follow-up queue'))
    job = run_synchronous_build_job(ws.root, BuildJob('build', {}), home=ws.home)
    assert job['result'] == 'done' and job['outcome']['advanced']
    assert job['outcome']['verification']['acceptance']['ran'] == 1
    assert len(Worker(ws, EventBus()).history) == 1
    assert not (ws.home / 'STUDIO_CURRENT.json').exists()
    assert ws.settings()['auto_work']  # The one-shot limit does not alter owner settings.


@pytest.mark.parametrize('obstacle', ['locked', 'current', 'paused', 'resident'])
def test_synchronous_runner_refuses_conflicts_and_preserves_unknown_work(tmp_path, monkeypatch, obstacle):
    from runesmith.app.build_jobs import run_synchronous_build_job
    from runesmith.app.server import InstanceLock
    from runesmith.app.workspace import _write_json
    ws = setup(tmp_path); lock = None
    if obstacle == 'locked':
        lock = InstanceLock(ws.home); assert lock.acquire()
    elif obstacle == 'current':
        _write_json(ws.home / 'STUDIO_CURRENT.json', {'id': 'unknown', 'kind': 'supplement'})
    elif obstacle == 'paused':
        Worker(ws, EventBus()).pause()
    else:
        monkeypatch.setattr('runesmith.app.server._existing', lambda home: 'resident-studio')
    remote = ws.home / 'inference-requests/uncertain.json'
    _write_json(remote, {'state': 'submitted', 'job_id': 'do-not-resubmit'})
    saved = remote.read_bytes()
    monkeypatch.setattr(Worker, '_execute', lambda *a, **kw: pytest.fail('Blocked caller executed a job'))
    try:
        with pytest.raises(WorkspaceError): run_synchronous_build_job(ws.root, BuildJob('build', {}), home=ws.home)
        assert remote.read_bytes() == saved
        if obstacle == 'current': assert json.loads((ws.home / 'STUDIO_CURRENT.json').read_text())['id'] == 'unknown'
    finally:
        if lock and lock.handle: lock.handle.close()


def test_synchronous_runner_does_not_abandon_waiting_manual_request(tmp_path, monkeypatch):
    from runesmith.app.build_jobs import run_synchronous_build_job
    from runesmith.app.workspace import Workspace
    ws = setup(tmp_path)
    monkeypatch.setattr(Workspace, 'manual_waiting', lambda self: 1)
    monkeypatch.setattr(Worker, '_execute', lambda *a, **kw: pytest.fail('Waiting manual request was ignored'))
    with pytest.raises(WorkspaceError, match='manual model request'):
        run_synchronous_build_job(ws.root, BuildJob('build', {}), home=ws.home)
    assert not (ws.home / 'STUDIO_CURRENT.json').exists()
