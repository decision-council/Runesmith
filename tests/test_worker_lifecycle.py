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
    said = [line['text'] for line in worker.lines if 'Studio closed during this job' in line['text']]
    assert said and said[0].startswith('The Studio closed during this job: Building the next step.')   # not "build marker" (J2-F5)
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


def test_a_skipped_chat_request_is_reported_as_skipped_in_plain_words(tmp_path, monkeypatch):
    # Journey J1-F3, F4: the log said "Propose_acceptance skipped: …" and "(skipped by the owner) (acceptance) answered".
    from runesmith.app.planner import SkippedByOwner
    worker = Worker(workspace(tmp_path), EventBus())
    worker._on_call({"answered_by": "(skipped by the owner)", "role": "acceptance", "ok": True, "latency_s": 38.0})

    def skipped(**params):
        raise SkippedByOwner("you skipped the request, so nothing changed")

    monkeypatch.setattr(worker, "_job_propose_acceptance", skipped)
    worker._execute({"id": "j1", "kind": "propose_acceptance", "params": {"milestone": "m1"}, "by": "owner"},
                    schedule_next=False)
    texts = [line["text"] for line in worker.lines]
    assert "You skipped the chat-window request (acceptance)." in texts
    assert "Proposing acceptance checks: you skipped the request, so nothing changed." in texts
    assert not any("answered" in t or "Propose_acceptance" in t for t in texts)


def test_a_new_request_that_replaces_an_answered_one_is_announced(tmp_path):
    # Journey J2-B4: the Checker's answer was refused and its revision request written within one poll. The count
    # stayed at 1, so the page was never told, and the owner saw "nothing waiting" while the job waited.
    ws = workspace(tmp_path)
    folder = ws.home / 'manual'
    folder.mkdir(parents=True, exist_ok=True)

    def request(rid, utc):
        (folder / f'{rid}.request.json').write_text(json.dumps({'id': rid, 'created_utc': utc}), encoding='utf-8')
        (folder / f'{rid}.prompt.md').write_text('a request', encoding='utf-8')

    bus = EventBus()
    worker = Worker(ws, bus)
    events = bus.subscribe()
    request('acceptance-first', '2026-09-28T06:54:45Z')
    worker._check_manual()
    (folder / 'acceptance-first.answer.md').write_text('the answer', encoding='utf-8')
    request('acceptance-first-retry', '2026-09-28T06:55:20Z')                       # answered and replaced before the next poll
    worker._check_manual()
    manual = [events.get_nowait() for _ in range(events.qsize())]
    manual = [e['data'] for e in manual if e['kind'] == 'manual']
    assert manual == [{'waiting': 1, 'new': 1}, {'waiting': 1, 'new': 1}]   # two announcements, one per request
    said = [line['text'] for line in worker.lines if line['text'].startswith('A request is waiting')]
    assert len(said) == 2
    worker._check_manual()                                        # nothing new: no repeat
    assert events.qsize() == 0 or all(e['kind'] != 'manual' for e in [events.get_nowait() for _ in range(events.qsize())])


def test_a_proposal_summary_gives_the_trial_counts(tmp_path, monkeypatch):
    # Journey J2-F10: the summary said "They fail on today's project" when 1 of 2 failed.
    ws = workspace(tmp_path)
    monkeypatch.setattr('runesmith.app.acceptance_proposals.propose', lambda *a, **k: {
        'id': 'p1', 'checks': [{}, {}], 'dry_run': {'verdict': 'fails_now', 'ran': 2, 'failures': 1, 'errors': 0}})
    summary = Worker(ws, EventBus())._job_propose_acceptance('m9')['summary']
    assert '1 of 2 fail on today’s project, as expected' in summary
    # Journey J11-F10: a check on a file nothing creates fails on a correct build too; that is not "as expected".
    monkeypatch.setattr('runesmith.app.acceptance_proposals.propose', lambda *a, **k: {
        'id': 'p2', 'checks': [{}, {'missing_input': ['position.motion.json']}],
        'dry_run': {'verdict': 'fails_now', 'ran': 2, 'failures': 1, 'errors': 0}})
    summary = Worker(ws, EventBus())._job_propose_acceptance('m9')['summary']
    assert 'as expected' not in summary and '1 of the checks use a file nothing creates' in summary, summary


def test_a_waiting_breakdown_is_not_proposed_again_every_round(tmp_path):
    # Journey J2-F16: with the tries used up, every scheduled round queued another breakdown that only returned the
    # proposal already waiting for the owner.
    ws = workspace(tmp_path)
    worker = Worker(ws, EventBus())
    assert not worker._breakdown_waiting('m7')
    _write_json(ws.home / 'breakdowns' / 'b1.json', {'id': 'b1', 'milestone': 'm7', 'state': 'proposed'})
    assert worker._breakdown_waiting('m7') and not worker._breakdown_waiting('m8')
    _write_json(ws.home / 'breakdowns' / 'b1.json', {'id': 'b1', 'milestone': 'm7', 'state': 'adopted'})
    assert not worker._breakdown_waiting('m7')


def test_rounds_that_find_nothing_new_are_one_counted_row(tmp_path, monkeypatch):
    # Journey J2-F20: with every try for m8 used up, a scheduled round every 5 minutes added a "done" row saying the
    # same thing; the history keeps 30 rows, so within hours the real attempts had been pushed out of Activity.
    worker = Worker(workspace(tmp_path), EventBus())
    monkeypatch.setattr('runesmith.app.work_modes.guard_job', lambda *a: None)
    monkeypatch.setattr('runesmith.app.environment_intent.require_intent', lambda *a: None)
    waiting = {'summary': 'Ordinary author allowance exhausted.', 'replan_needed': True, 'milestone': 'm8'}
    answers = iter([waiting, waiting, waiting, RuntimeError('boom'), waiting, waiting])

    def build(**params):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(worker, '_job_build', build)
    for n in range(6):
        worker._execute({'id': f'j{n}', 'kind': 'build', 'params': {}, 'queued': '2026-09-28T12:00:00Z',
                         'by': 'schedule'}, schedule_next=False)
    rows = list(worker.history)
    assert [(r['result'], r.get('repeats')) for r in rows] == [('done', 3), ('failed', None), ('done', 2)]
    assert rows[0]['first_finished'] <= rows[0]['finished']
    assert json.loads((worker.ws.home / 'STUDIO_JOBS.json').read_text(encoding='utf-8'))[0]['repeats'] == 3
    from runesmith.app.worker import _same_waiting_round
    owners = dict(rows[-1], by='owner')                           # what the owner asked for is always its own row
    assert not _same_waiting_round(rows[-1], owners) and not _same_waiting_round(owners, dict(owners))
    advanced = dict(rows[-1], outcome={'summary': 'Applied m8.', 'advanced': True})
    assert not _same_waiting_round(advanced, dict(advanced))
    # J2-F20 follow-up: the same draft still waiting for checks is the same waiting state; a new draft is not
    waits = dict(rows[-1], outcome={'summary': 'Draft “Export” waits for you.', 'draft': 'd1', 'milestone': 'm8'})
    assert _same_waiting_round(waits, dict(waits))
    assert not _same_waiting_round(waits, dict(waits, outcome=dict(waits['outcome'], draft='d2')))



def test_no_scheduled_breakdown_for_a_milestone_that_already_has_smaller_steps(tmp_path):
    # Journey J2-F31: with m8's tries used up again, every round queued a breakdown that failed at once, "This milestone
    # already has prerequisite steps".
    ws = workspace(tmp_path)
    ws.save_plan({"summary": "Log", "milestones": [{"title": "Export", "done_when": "exported"}]})
    worker = Worker(ws, EventBus())
    goal = ws.plan()["milestones"][0]["id"]
    assert not worker._breakdown_waiting(goal)
    plan = ws.plan()
    plan["milestones"].insert(0, {"id": "s1", "title": "A smaller step", "status": "done", "parent_id": goal})
    _write_json(ws.home / "PLAN.json", plan)
    assert worker._breakdown_waiting(goal)


def test_run_now_does_what_the_schedule_does(tmp_path):
    # Journey J11-F11: "Run now" always queued a repair round, which never builds, and told the owner to draft a
    # plan that already had ten milestones.
    from types import SimpleNamespace
    from runesmith.app.server import api_worker_run
    ws = workspace(tmp_path)
    worker = Worker(ws, EventBus())
    ws.update_settings({'build_steps': False})
    assert worker.scheduled_job() == ('round', {})
    ws.update_settings({'build_steps': True})
    assert worker.scheduled_job() == ('build', {})
    job = api_worker_run(SimpleNamespace(worker=worker), {}, {'job': 'next'})
    assert job['kind'] == 'build'
