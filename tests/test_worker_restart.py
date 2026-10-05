import json
import threading

import pytest

from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json


def workspace(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    ws = Workspace(root)
    ws.update_settings({'auto_work': False, 'kaizen': False})
    return ws


def test_waiting_intents_survive_restart_but_need_review_then_separate_resume(tmp_path, monkeypatch):
    ws = workspace(tmp_path)
    first = Worker(ws, EventBus()).enqueue('health')
    worker = Worker(ws, EventBus())
    worker._recover()
    state = worker.snapshot()
    assert state['paused'] and state['queue'] == [first]
    assert state['recovery']['required']
    with pytest.raises(WorkspaceError, match='review'):
        worker.resume()
    with pytest.raises(WorkspaceError, match='review'):
        worker.enqueue('map', probe=False)
    worker.review_recovery(revision=state['recovery']['revision'], decision='keep', reviewed=True)
    assert worker.paused and worker.snapshot()['recovery'] is None
    assert worker.snapshot()['queue'] == [first]
    ran = threading.Event()
    monkeypatch.setattr(worker, '_job_health', lambda: (ran.set() or {}))
    worker.start()
    try:
        assert not ran.wait(0.1)
        worker.resume()
        assert ran.wait(3)
    finally:
        worker.close(); worker._thread.join(3); worker._watch.join(3)
    assert json.loads((ws.home / 'STUDIO_QUEUE.json').read_text())['jobs'] == []
    assert worker.history[-1]['id'] == first['id']


def test_interrupted_job_holds_schedule_and_is_never_left_in_waiting_queue(tmp_path):
    ws = workspace(tmp_path)
    original = Worker(ws, EventBus())
    claimed = original.enqueue('health')
    waiting = original.enqueue('map', probe=False)
    _write_json(ws.home / 'STUDIO_CURRENT.json', dict(claimed, started='2026-09-27T03:00:00Z'))
    worker = Worker(ws, EventBus()); worker._recover()
    assert worker.paused and worker._next_round_utc({'auto_work': True, 'onboarded': True}) is None
    assert worker.snapshot()['queue'] == [waiting]
    assert worker.history[-1]['result'] == 'interrupted'
    assert worker.history[-1]['id'] == claimed['id']
    worker._recover()
    assert len(worker.history) == 1
    again = Worker(ws, EventBus()); again._recover()
    assert again.paused and again.snapshot()['recovery']['required']
    assert again.snapshot()['queue'] == [waiting]


def test_completed_current_marker_is_not_relabeled_as_interrupted(tmp_path):
    ws = workspace(tmp_path)
    job = Worker(ws, EventBus()).enqueue('health')
    _write_json(ws.home / 'STUDIO_CURRENT.json', dict(job, started='2026-09-27T03:00:00Z'))
    _write_json(ws.home / 'STUDIO_JOBS.json', [dict(job, result='done', outcome={'summary': 'Completed fixture'})])
    worker = Worker(ws, EventBus()); worker._recover()
    assert len(worker.history) == 1 and worker.history[0]['result'] == 'done'
    assert not worker.snapshot()['queue'] and worker.paused


def test_set_aside_preserves_intentions_in_receipt_and_never_resumes(tmp_path):
    ws = workspace(tmp_path)
    job = Worker(ws, EventBus()).enqueue('map', probe=False)
    worker = Worker(ws, EventBus()); worker._recover()
    revision = worker.snapshot()['recovery']['revision']
    for kwargs in ({'reviewed': False, 'decision': 'park'}, {'reviewed': True, 'decision': 'retry'}):
        with pytest.raises(WorkspaceError): worker.review_recovery(revision=revision, **kwargs)
    with pytest.raises(WorkspaceError):
        worker.review_recovery(revision='stale', decision='park', reviewed=True)
    worker.review_recovery(revision=revision, decision='park', reviewed=True)
    assert worker.paused and not worker.snapshot()['queue'] and worker.snapshot()['recovery'] is None
    receipts = list((ws.home / 'studio-recovery').glob('*.json'))
    assert len(receipts) == 1
    record = json.loads(receipts[0].read_text())
    assert record['decision'] == 'park' and record['jobs'] == [job]
    assert worker.history[-1]['result'] == 'not_started'
    with pytest.raises(WorkspaceError):
        worker.review_recovery(revision=revision, decision='park', reviewed=True)


@pytest.mark.parametrize('filename', ['STUDIO_QUEUE.json', 'STUDIO_STATE.json', 'STUDIO_CURRENT.json', 'STUDIO_JOBS.json'])
def test_malformed_control_records_fail_closed_without_overwriting_evidence(tmp_path, filename):
    ws = workspace(tmp_path)
    record = ws.home / filename
    record.write_text('{broken', encoding='utf-8')
    worker = Worker(ws, EventBus()); worker._recover()
    assert worker.paused and worker.snapshot()['recovery']['blocked']
    with pytest.raises(WorkspaceError): worker.resume()
    with pytest.raises(WorkspaceError): worker.pause()
    with pytest.raises(WorkspaceError): worker.enqueue('health')
    with pytest.raises(WorkspaceError):
        worker.review_recovery(revision=worker.snapshot()['recovery']['revision'], decision='park', reviewed=True)
    assert record.read_text() == '{broken'


def test_enqueue_only_acknowledges_durable_intent_and_refuses_external_change(tmp_path, monkeypatch):
    ws = workspace(tmp_path); worker = Worker(ws, EventBus())
    import runesmith.app.worker_journal as journal
    real_write = journal.atomic_write
    monkeypatch.setattr(journal, 'atomic_write', lambda *a: (_ for _ in ()).throw(OSError('disk full fixture')))
    with pytest.raises((OSError, WorkspaceError)): worker.enqueue('health')
    assert not worker.snapshot()['queue']
    monkeypatch.setattr(journal, 'atomic_write', real_write)
    worker = Worker(ws, EventBus())
    worker.enqueue('health')
    path = ws.home / 'STUDIO_QUEUE.json'
    value = json.loads(path.read_text()); value['external'] = 'another writer'
    _write_json(path, value)
    saved = path.read_bytes()
    with pytest.raises(WorkspaceError): worker.enqueue('map', probe=False)
    assert path.read_bytes() == saved and len(worker.snapshot()['queue']) == 1


def test_current_marker_precedes_queue_removal_and_no_handler_on_write_failure(tmp_path, monkeypatch):
    ws = workspace(tmp_path); worker = Worker(ws, EventBus())
    job = worker.enqueue('health')
    import runesmith.app.worker_journal as journal
    real_write = journal.atomic_write
    def fail_queue(path, value):
        if path.name == 'STUDIO_QUEUE.json':
            assert (ws.home / 'STUDIO_CURRENT.json').exists()
            raise OSError('claim queue write failed')
        return real_write(path, value)
    monkeypatch.setattr(journal, 'atomic_write', fail_queue)
    monkeypatch.setattr(worker, '_job_health', lambda: pytest.fail('Unjournaled claim must not execute'))
    with pytest.raises((OSError, WorkspaceError)): worker._execute(job)
    assert json.loads((ws.home / 'STUDIO_QUEUE.json').read_text())['jobs'] == [job]
    monkeypatch.setattr(journal, 'atomic_write', real_write)
    recovered = Worker(ws, EventBus()); recovered._recover()
    assert recovered.paused and not recovered.snapshot()['queue']
    assert recovered.history[-1]['result'] == 'interrupted'  # uncertainty, not a fabricated failure or retry


def test_synchronous_runner_must_not_jump_over_retained_intentions(tmp_path, monkeypatch):
    from runesmith.app.build_jobs import BuildJob, run_synchronous_build_job
    ws = workspace(tmp_path)
    Worker(ws, EventBus()).enqueue('health')
    monkeypatch.setattr(Worker, '_execute', lambda *a, **kw: pytest.fail('Queue was bypassed'))
    with pytest.raises(WorkspaceError, match='queue|recovery'):
        run_synchronous_build_job(ws.root, BuildJob('build', {}), home=ws.home)


@pytest.mark.parametrize('raw', ['null', '{"paused":false,"paused":true}', 'NaN', '"wrong shape"'])
def test_invalid_state_shapes_and_duplicate_fields_are_not_silently_defaulted(tmp_path, raw):
    ws = workspace(tmp_path)
    path = ws.home / 'STUDIO_STATE.json'; path.write_text(raw, encoding='utf-8')
    worker = Worker(ws, EventBus()); worker._recover()
    assert worker.paused and worker.snapshot()['recovery']['blocked']
    assert path.read_text() == raw


@pytest.mark.parametrize('mutation', ['root', 'identity', 'parameters', 'kind', 'version'])
def test_queue_is_bound_to_workspace_with_unique_valid_intentions(tmp_path, mutation):
    ws = workspace(tmp_path)
    Worker(ws, EventBus()).enqueue('health')
    path = ws.home / 'STUDIO_QUEUE.json'; saved = json.loads(path.read_text())
    if mutation == 'root': saved['root'] = 'D:/another-project'
    elif mutation == 'identity': saved['jobs'] *= 2
    elif mutation == 'parameters': saved['jobs'][0]['params'] = {'unexpected': True}
    elif mutation == 'kind': saved['jobs'][0]['kind'] = []
    elif mutation == 'version': saved['version'] = True
    _write_json(path, saved); original = path.read_bytes()
    worker = Worker(ws, EventBus()); worker._recover()
    assert worker.paused and worker.snapshot()['recovery']['blocked']
    assert path.read_bytes() == original


def test_pause_between_selection_and_claim_leaves_waiting_intent_untouched(tmp_path, monkeypatch):
    from runesmith.app.worker import StopRequested
    ws = workspace(tmp_path); worker = Worker(ws, EventBus())
    job = worker.enqueue('health'); worker.pause()
    monkeypatch.setattr(worker, '_job_health', lambda: pytest.fail('Paused claim ran'))
    with pytest.raises(StopRequested): worker._execute(job)
    assert worker.snapshot()['queue'] == [job] and not (ws.home / 'STUDIO_CURRENT.json').exists()
    assert worker.snapshot()['recovery'] is None  # ordinary pause is not storage corruption


def test_finish_record_failure_does_not_redispatch_and_thread_remains_held(tmp_path, monkeypatch):
    import time
    import runesmith.app.worker_journal as journal
    ws = workspace(tmp_path); worker = Worker(ws, EventBus())
    first = worker.enqueue('health'); waiting = worker.enqueue('map', probe=False)
    ran = []
    monkeypatch.setattr(worker, '_job_health', lambda: (ran.append('health') or {}))
    monkeypatch.setattr(worker, '_job_map', lambda **kw: pytest.fail('Following job escaped failed history write'))
    real_write = journal.atomic_write
    def fail_history(path, value):
        if path.name == 'STUDIO_JOBS.json': raise OSError('history disk failure fixture')
        return real_write(path, value)
    monkeypatch.setattr(journal, 'atomic_write', fail_history)
    worker.start()
    try:
        end = time.monotonic() + 3
        while not worker.snapshot()['recovery'] and time.monotonic() < end:
            time.sleep(0.01)
        assert worker._thread.is_alive() and worker.paused and worker.snapshot()['recovery']['blocked']
        assert ran == ['health'] and worker.snapshot()['queue'] == [waiting]
        assert json.loads((ws.home / 'STUDIO_CURRENT.json').read_text())['id'] == first['id']
    finally:
        worker.close(); worker._thread.join(3); worker._watch.join(3)


def test_stale_review_cannot_overwrite_external_queue_or_receipts(tmp_path):
    ws = workspace(tmp_path); Worker(ws, EventBus()).enqueue('health')
    worker = Worker(ws, EventBus()); worker._recover()
    revision = worker.snapshot()['recovery']['revision']
    path = ws.home / 'STUDIO_QUEUE.json'; value = json.loads(path.read_text())
    value['jobs'][0]['by'] = 'another controller'; _write_json(path, value)
    before = path.read_bytes()
    with pytest.raises(WorkspaceError, match='changed'):
        worker.review_recovery(revision=revision, decision='park', reviewed=True)
    assert path.read_bytes() == before and worker.paused
    assert not (ws.home / 'studio-recovery').exists()


def test_the_owner_s_review_of_an_interrupted_job_has_a_ledger_event_of_its_own(tmp_path, monkeypatch):
    # Starvation-integrity study (SI, T11): the review wrote RUNESMITH.md and its receipt file, and no ledger event.
    import runesmith.app.worker_journal as journal
    ws = workspace(tmp_path); original = Worker(ws, EventBus())
    original.enqueue('health'); original.enqueue('map', probe=False)
    worker = Worker(ws, EventBus()); worker._recover()
    revision = worker.snapshot()['recovery']['revision']
    real_write = journal.atomic_write
    def fail_queue(path, value):
        if path.name == 'STUDIO_QUEUE.json' and value['recovery'] is None:
            raise OSError('decision persisted but final queue commit interrupted')
        return real_write(path, value)
    monkeypatch.setattr(journal, 'atomic_write', fail_queue)
    with pytest.raises(OSError): worker.review_recovery(revision=revision, decision='keep', reviewed=True)
    assert not list(ws.ledger.events('studio.recovery_reviewed'))        # the decision was not carried out: not recorded
    monkeypatch.setattr(journal, 'atomic_write', real_write)
    again = Worker(ws, EventBus()); again._recover()
    again.review_recovery(revision=again.snapshot()['recovery']['revision'], decision='keep', reviewed=True)
    assert [e['data'] for e in ws.ledger.events('studio.recovery_reviewed')] == [
        {'revision': revision, 'decision': 'keep', 'reviewed_by': 'owner', 'jobs': 2}]


def test_enqueue_and_snapshot_return_detached_intentions(tmp_path):
    ws = workspace(tmp_path); worker = Worker(ws, EventBus())
    job = worker.enqueue('map', probe=False); job['params']['probe'] = True
    view = worker.snapshot(); view['queue'][0]['params']['probe'] = True
    assert worker.snapshot()['queue'][0]['params'] == {'probe': False}
    assert json.loads((ws.home / 'STUDIO_QUEUE.json').read_text())['jobs'][0]['params'] == {'probe': False}


def test_recovery_api_requires_acknowledgement_and_does_not_run_or_grant(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from runesmith.app.server import api_worker_recovery
    ws = workspace(tmp_path); Worker(ws, EventBus()).enqueue('health')
    remote = ws.home / 'inference-requests/protected.json'
    spent = ws.home / 'build-check-allocations/protected.json'
    _write_json(remote, {'state': 'submitted', 'job_id': 'do-not-replay'})
    _write_json(spent, {'state': 'started', 'id': 'do-not-replenish'})
    protected = {p: p.read_bytes() for p in (remote, spent)}
    worker = Worker(ws, EventBus()); worker._recover()
    monkeypatch.setattr(worker, '_execute', lambda *a, **k: pytest.fail('Review ran work'))
    app = SimpleNamespace(worker=worker)
    with pytest.raises(WorkspaceError): api_worker_recovery(app, {}, {})
    reply = api_worker_recovery(app, {}, {'revision': worker.snapshot()['recovery']['revision'], 'decision': 'park', 'reviewed': True})
    assert reply['paused'] and not reply['queue'] and reply['recovery'] is None
    assert all(p.read_bytes() == content for p, content in protected.items())


def test_interrupted_park_keeps_every_intention_archived_even_beyond_history_window(tmp_path, monkeypatch):
    import runesmith.app.worker_journal as journal
    ws = workspace(tmp_path); original = Worker(ws, EventBus())
    for number in range(35): original.enqueue('draft', milestone=f'm{number}')
    worker = Worker(ws, EventBus()); worker._recover()
    revision = worker.snapshot()['recovery']['revision']
    real_write = journal.atomic_write
    def fail_queue(path, value):
        if path.name == 'STUDIO_QUEUE.json' and value['recovery'] is None:
            raise OSError('park decision persisted but final queue commit interrupted')
        return real_write(path, value)
    monkeypatch.setattr(journal, 'atomic_write', fail_queue)
    with pytest.raises(OSError): worker.review_recovery(revision=revision, decision='park', reviewed=True)
    monkeypatch.setattr(journal, 'atomic_write', real_write)
    again = Worker(ws, EventBus()); again._recover()
    assert again.paused and not again.snapshot()['queue'] and again.snapshot()['recovery']
    assert not again.snapshot()['recovery']['blocked']
    assert len(json.loads((ws.home / 'studio-recovery' / f'{revision}.json').read_text())['jobs']) == 35
    for _ in range(2):
        again = Worker(ws, EventBus()); again._recover()
        assert not again.snapshot()['queue'] and again.paused


def test_conflicting_current_identity_does_not_discard_waiting_intention(tmp_path):
    ws = workspace(tmp_path)
    job = Worker(ws, EventBus()).enqueue('map', probe=False)
    _write_json(ws.home / 'STUDIO_CURRENT.json', dict(job, params={'probe': True}))
    marker = (ws.home / 'STUDIO_CURRENT.json').read_bytes()
    queued = (ws.home / 'STUDIO_QUEUE.json').read_bytes()
    worker = Worker(ws, EventBus()); worker._recover()
    assert worker.snapshot()['recovery']['blocked'] and worker.snapshot()['queue'] == [job]
    assert (ws.home / 'STUDIO_CURRENT.json').read_bytes() == marker
    assert (ws.home / 'STUDIO_QUEUE.json').read_bytes() == queued


def test_record_path_redirection_is_refused_without_touching_target(tmp_path, monkeypatch):
    from pathlib import Path
    ws = workspace(tmp_path)
    path = ws.home / 'STUDIO_QUEUE.json'
    _write_json(path, {'retained': True})
    before = path.read_bytes()
    real = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == path or real(p))
    worker = Worker(ws, EventBus()); worker._recover()
    assert worker.paused and worker.snapshot()['recovery']['blocked']
    assert path.read_bytes() == before


@pytest.mark.parametrize('crash_point,exit_code,expected_result', [('claim', 73, 'interrupted'), ('finish', 74, 'done')])
def test_real_process_exit_preserves_claim_boundary_and_completed_outcome(tmp_path, crash_point, exit_code, expected_result):
    import subprocess
    import sys
    ws = workspace(tmp_path)
    queued = Worker(ws, EventBus()).enqueue('health')
    # No server, gateway or model: terminate a disposable interpreter at the
    # actual disk boundary, not just a second object in the same interpreter.
    script = '''
import json, os, sys
from pathlib import Path
from runesmith.app.workspace import Workspace
from runesmith.app.worker import Worker, EventBus
from runesmith.app import worker_journal as journal
w = Worker(Workspace(Path(sys.argv[1])), EventBus())
w._recover()
assert w.paused and w.snapshot()['recovery']
w.review_recovery(revision=w.snapshot()['recovery']['revision'], decision='keep', reviewed=True)
w.resume()
def fixture_only():
    if sys.argv[2] == 'claim': os._exit(99)
    return {'summary': 'Local fixture handler finished; no model or project work.'}
w._job_health = fixture_only
real_write, real_remove = journal.atomic_write, journal.Record.remove
def crash_write(path, value):
    if sys.argv[2] == 'claim' and path.name == 'STUDIO_QUEUE.json' and value['jobs'] == []:
        os._exit(73)
    return real_write(path, value)
def crash_remove(self):
    if sys.argv[2] == 'finish' and self.path.name == 'STUDIO_CURRENT.json': os._exit(74)
    return real_remove(self)
journal.atomic_write, journal.Record.remove = crash_write, crash_remove
w._execute(w.snapshot()['queue'][0])
os._exit(98)
'''
    child = subprocess.run([sys.executable, '-c', script, str(ws.root), crash_point],
                           capture_output=True, text=True, timeout=30)
    assert child.returncode == exit_code, child.stderr
    assert (ws.home / 'STUDIO_CURRENT.json').exists()
    recovered = Worker(ws, EventBus()); recovered._recover()
    assert recovered.paused and recovered.snapshot()['recovery'] and not recovered.snapshot()['queue']
    assert len(recovered.history) == 1
    assert recovered.history[0]['id'] == queued['id'] and recovered.history[0]['result'] == expected_result
