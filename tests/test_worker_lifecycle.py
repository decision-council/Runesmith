import json
import threading

from runesmith.app.worker import EventBus, Worker, StopRequested
from runesmith.app.workspace import Workspace, _write_json
import pytest


def workspace(tmp_path):
    (tmp_path / 'project').mkdir()
    ws = Workspace(tmp_path / 'project')
    ws.update_settings({'auto_work': False, 'kaizen': False})
    return ws


def test_pause_persists_and_queue_waits_until_explicit_resume(tmp_path, monkeypatch):
    ws = workspace(tmp_path)
    original = Worker(ws, EventBus()); original.pause()
    worker = Worker(ws, EventBus())
    assert worker.paused and worker.snapshot()['status'] == 'paused'
    executed = threading.Event()
    monkeypatch.setattr(worker, '_job_health', lambda: (executed.set() or {'summary': 'Local fixture only'}))
    first = worker.enqueue('health')
    assert worker.enqueue('health')['id'] == first['id']  # exact duplicate is not a second job
    worker.start()
    try:
        assert not executed.wait(0.15)
        assert len(worker.snapshot()['queue']) == 1
        worker.resume()
        assert executed.wait(3)
    finally:
        worker.close(); worker._thread.join(3); worker._watch.join(3)
    assert not worker._thread.is_alive()
    assert len(worker.history) == 1 and worker.history[0]['result'] == 'done'
    assert not Worker(ws, EventBus()).paused


def test_interruption_preserves_remote_and_spent_receipts_without_replay(tmp_path):
    ws = workspace(tmp_path)
    remote = ws.home / 'inference-requests/uncertain.json'
    spent = ws.home / 'build-check-allocations/spent.json'
    _write_json(remote, {'state': 'submitted', 'job_id': 'existing-job', 'instrument': 'author'})
    _write_json(spent, {'state': 'started', 'id': 'spent-allocation'})
    protected = {p: p.read_bytes() for p in (remote, spent)}
    _write_json(ws.home / 'STUDIO_CURRENT.json', {'id': 'interrupted', 'kind': 'build', 'params': {}})
    worker = Worker(ws, EventBus()); worker.pause(); worker._recover()
    assert worker.paused and not worker._jobs
    assert worker.snapshot()['recovery']['interrupted'] == 'build'     # named in the owner's plain summary (J4-F11)
    assert all(p.read_bytes() == content for p, content in protected.items())
    assert not (ws.home / 'STUDIO_CURRENT.json').exists()
    job = worker.snapshot()['history'][0]
    assert job['id'] == 'interrupted' and job['result'] == 'interrupted'
    assert 'retrieve its saved response' in job['outcome']['summary']
    assert 'Spent check allocations remain spent' in job['outcome']['summary']
    assert 'run it again' not in json.dumps(worker.snapshot()).lower()
    worker._recover()
    assert len(worker.history) == 1  # restart recovery cannot duplicate history


def test_write_conflict_pauses_and_manual_orphans_are_set_aside(tmp_path, monkeypatch):
    ws = workspace(tmp_path); worker = Worker(ws, EventBus())
    monkeypatch.setattr(ws, 'recover_writes', lambda: [{'key': 'conflict', 'state': 'conflict'}])
    monkeypatch.setattr(ws, 'set_aside_orphaned_requests', lambda: 2)
    worker._recover()
    assert worker.paused and Worker(ws, EventBus()).paused
    assert any('2 chat-relay request(s)' in row['text'] for row in worker.lines)
    assert not worker._jobs


def test_pause_and_stop_finish_at_existing_step_boundary(tmp_path):
    worker = Worker(workspace(tmp_path), EventBus())
    worker.pause()
    with pytest.raises(StopRequested): worker._work_checkpoint()
    worker.resume(); worker.stop_current()
    with pytest.raises(StopRequested): worker._work_checkpoint()
    assert worker.snapshot()['queue'] == []


def test_stop_ends_current_job_but_does_not_pause_or_overlap_queued_job(tmp_path, monkeypatch):
    worker = Worker(workspace(tmp_path), EventBus())
    entered = threading.Event(); release = threading.Event(); second = threading.Event()
    order = []
    def first():
        order.append('first-start'); entered.set()
        assert release.wait(3)
        order.append('first-end')
        worker._work_checkpoint()
        pytest.fail('Stop should be observed at this boundary')
    def next_job(probe=False):
        order.append('second-start'); second.set()
        return {'summary': 'Second queued fixture completed; no model or project work.'}
    monkeypatch.setattr(worker, '_job_health', first)
    monkeypatch.setattr(worker, '_job_map', next_job)
    worker.enqueue('health'); worker.enqueue('map', probe=False); worker.start()
    try:
        assert entered.wait(3) and not second.wait(0.1)
        worker.stop_current()
        assert worker.snapshot()['stop_requested'] and not worker.paused
        release.set(); assert second.wait(3)
    finally:
        release.set(); worker.close(); worker._thread.join(3); worker._watch.join(3)
    assert order == ['first-start', 'first-end', 'second-start']
    assert [r['result'] for r in worker.history] == ['stopped', 'done']
    assert not worker.snapshot()['stop_requested']


def test_the_queue_records_who_asked_for_each_job(tmp_path):
    # F16 (out-of-box journey R1): builds the schedule chains after an applied milestone were recorded as the owner's.
    from runesmith.app.worker import EventBus, Worker
    from runesmith.app.workspace import Workspace
    worker = Worker(Workspace(tmp_path), EventBus())
    assert worker.enqueue("map")["by"] == "owner"
    assert worker.enqueue("round", by="schedule")["by"] == "schedule"
    with pytest.raises(ValueError, match="requester"):
        worker.enqueue("health", by="somebody")
    import inspect
    source = inspect.getsource(Worker._execute)
    assert "self.enqueue('build', by='schedule')" in source and "self.enqueue('breakdown', by='schedule'" in source
