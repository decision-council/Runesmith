"""A one more try cut short by a restart must never block its milestone for good, nor silently.

The sequence found in a long unattended run: three ordinary tries failed, the one more try (another model) was started,
the Studio was restarted while it worked, and from then on every build of that milestone ended "Unresolved author
allowance receipt ...; reconcile it before another call" while the Overview's "Needs you" stayed empty. The receipt was
written "started", the model job was retrieved after the restart, but nothing tied the retrieved answer to the receipt, so
nothing ever settled it.
"""
import json
from types import SimpleNamespace

import pytest

from runesmith.app import building, runesmith_md, stuck
from runesmith.app.author_allowance import ordinary_allowance
from runesmith.app.author_recovery import (INTERRUPTED, close_interrupted_escalation, close_interrupted_escalations,
                                           pending_authors, read_packet, resume_author, settle_escalation)
from runesmith.app.planner import PlannerUnavailable, draft_files, milestone_contract, source_context
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.instruments import Router
from test_author_allowance import failed_author
from test_author_recovery import Gateway, instrument
from test_build_steps import enable, setup


class Died(BaseException):
    """The process is gone (power cut, killed, restarted): no `except Exception` in the code under test sees it."""


class DyingGateway(Gateway):
    def __init__(self, dies_on):
        super().__init__()
        self.dies_on = dies_on

    def __call__(self, method, *args):
        if method == self.dies_on:
            raise Died()
        return super().__call__(method, *args)


def home(tmp_path, gateway, monkeypatch):
    """A folder with a milestone, its three ordinary tries used up, and a router that goes through a model gateway."""
    ws = setup(tmp_path)
    enable(ws)
    ws.save_instrument('model', {'kind': 'milliner', 'model': 'free:worker', 'base_url': 'http://localhost:8765'},
                       key_value='unused', roles=['plan'])
    inst = instrument(ws.home, gateway)
    router = Router({'m': inst}, {'plan': ['m']}, backoff_s=(), on_call=ws.record_call)
    with monkeypatch.context() as spend:
        spend.setattr(building, 'draft_files', failed_author)
        for _ in range(3):
            with pytest.raises(WorkspaceError, match='Fixture author'):
                building.build_step(ws, None, author_only=True)
    monkeypatch.setattr('runesmith.config.build_instrument', lambda *args, **kwargs: inst)
    return ws, router


def receipts(ws):
    return {p.stem: _read_json(p, {}) for p in (ws.home / 'build-escalations').glob('*.json')}


def only_receipt(ws):
    [(key, receipt)] = receipts(ws).items()
    return key, receipt


def cut_short(ws, router, *, at):
    """The one more try is started and the process dies in it (`at`: the gateway call it dies in)."""
    with pytest.raises(Died):
        building.escalate_build(ws, router)
    key, receipt = only_receipt(ws)
    assert receipt['state'] == 'started'
    return key


def used_up(result):
    return result.get('replan_needed') and not result.get('allowance_blocked') and 'Unresolved' not in result['summary']


# ---- the sequence from the run -----------------------------------------------------------------------------------------

def test_a_started_receipt_with_no_saved_call_is_settled_by_the_restart_and_the_build_goes_on(tmp_path, monkeypatch):
    ws, router = home(tmp_path, DyingGateway('POST'), monkeypatch)
    key = cut_short(ws, router, at='POST')
    with pytest.raises(WorkspaceError, match='Unresolved author allowance receipt'):
        contract = milestone_contract(ws, ws.plan()['milestones'][0])
        ordinary_allowance(ws, contract, source_context(ws)['snapshot_digest'])
    worker = Worker(ws, EventBus())
    worker._recover()                                                    # the restart
    receipt = receipts(ws)[key]
    assert receipt['state'] == 'failed' and receipt['error'] == INTERRUPTED == 'interrupted by a restart'
    assert receipt['prior_state'] == 'started' and receipt['reconciled_by'] == 'Runesmith (restart)'
    assert any('cut short' in line['text'] and 'nothing was sent again' in line['text'] for line in worker.lines)
    assert not pending_authors(ws)                                       # the saved request it left no longer holds the milestone
    result = building.build_step(ws, None)                               # no model may be asked
    assert used_up(result), result


def test_a_build_settles_a_started_receipt_itself_when_no_restart_did(tmp_path, monkeypatch):
    ws, router = home(tmp_path, DyingGateway('POST'), monkeypatch)
    key = cut_short(ws, router, at='POST')
    result = building.build_step(ws, None)
    assert used_up(result), result
    assert receipts(ws)[key]['state'] == 'failed' and receipts(ws)[key]['error'] == INTERRUPTED
    assert list(ws.ledger.events('build.escalation_reconciled'))
    with pytest.raises(WorkspaceError, match='No one-shot'):             # the interrupted call used its one more try
        building.escalate_build(ws, router)


def test_the_saved_answer_of_an_interrupted_call_is_retrieved_and_settles_its_receipt(tmp_path, monkeypatch):
    gateway = DyingGateway('GET')
    ws, router = home(tmp_path, gateway, monkeypatch)
    key = cut_short(ws, router, at='GET')                                # sent, its job saved, the process died waiting
    assert read_packet(ws, pending_authors(ws)[0]['key'])['escalation_id'] == key
    Worker(ws, EventBus())._recover()                                    # the restart leaves it: its answer can be fetched
    assert receipts(ws)[key]['state'] == 'started' and pending_authors(ws)[0]['can_resume']
    gateway.dies_on = None
    gateway.fail_poll = False
    result = building.build_step(ws, Router({}, {}))                     # fetched, no new call, checked like any other
    receipt = receipts(ws)[key]
    assert receipt['state'] == 'answered' and receipt['draft'] and receipt['author'] == 'free:worker'
    assert result.get('verification') and ws._draft(receipt['draft'])['milestone'] == 'm1'
    assert [m for m, _ in gateway.requests].count('POST') == 1
    assert not pending_authors(ws)
    assert resume_author(ws, next(p.stem for p in (ws.home / 'author-recoveries').glob('*.json')))['already_used']
    assert receipts(ws)[key]['state'] == 'answered'                      # idempotent


def test_the_saved_job_that_failed_settles_its_receipt_and_the_milestone_is_used_up(tmp_path, monkeypatch):
    gateway = DyingGateway('GET')
    ws, router = home(tmp_path, gateway, monkeypatch)
    key = cut_short(ws, router, at='GET')
    gateway.dies_on = None
    gateway.fail_poll = False
    gateway.state = 'failed'
    first = building.build_step(ws, Router({}, {}))
    assert 'never came' in first['summary']
    receipt = receipts(ws)[key]
    assert receipt['state'] == 'failed' and 'truncated' in receipt['error']
    assert used_up(building.build_step(ws, Router({}, {}))), 'the milestone is stuck in the plain way, not refused'


def test_a_started_receipt_whose_saved_call_has_no_job_to_fetch_is_closed_with_that_call(tmp_path, monkeypatch):
    gateway = DyingGateway('POST')                                       # the process died while sending: nothing can be fetched
    ws, router = home(tmp_path, gateway, monkeypatch)
    key = cut_short(ws, router, at='POST')
    [row] = pending_authors(ws)
    assert not row['can_resume']
    assert building.build_step(ws, Router({}, {}))['summary'].startswith('Ordinary author allowance exhausted')
    assert receipts(ws)[key]['state'] == 'failed' and not pending_authors(ws)
    assert [m for m, _ in gateway.requests] == []                        # nothing was sent, then or since


def test_the_receipt_as_the_run_left_it_a_packet_with_no_link_and_a_job_that_already_failed(tmp_path, monkeypatch):
    # The run's records: a packet without `escalation_id` (older Runesmith), the request retrieved after the restart and
    # recorded as a failed remote job, and the receipt still "started". Retrieval has nothing to point at, so the next
    # build settles the receipt itself.
    gateway = Gateway()
    ws, router = home(tmp_path, gateway, monkeypatch)
    with pytest.raises(PlannerUnavailable):
        draft_files(ws, router, 'm1')                                    # the call of the one more try, as it was made then
    state = building.build_escalation_status(ws)
    key = 'e355ea61a7ec2'
    contract = milestone_contract(ws, ws.plan()['milestones'][0])
    _write_json(ws.home / 'build-escalations' / (key + '.json'),
                {'id': key, 'state': 'started', 'utc': _now(), 'scope': state['scope'], 'milestone': 'm1', 'contract': contract,
                 'snapshot_digest': state['snapshot_digest'], 'ordinary_attempts': 3})
    [row] = pending_authors(ws)
    assert 'escalation_id' not in read_packet(ws, row['key'])
    gateway.fail_poll = False
    gateway.state = 'failed'
    assert 'never came' in building.build_step(ws, Router({}, {}))['summary']      # retrieved: the job failed
    assert receipts(ws)[key]['state'] == 'started'                                 # nothing links the two
    result = building.build_step(ws, Router({}, {}))                               # used to end "Unresolved ..." for ever
    assert used_up(result), result
    assert receipts(ws)[key]['state'] == 'failed' and receipts(ws)[key]['error'] == INTERRUPTED


# ---- what stays for the owner --------------------------------------------------------------------------------------------

def an_unclear_receipt(ws, **changes):
    """A receipt in a state nothing here knows: Runesmith cannot tell how that call ended, so it never guesses."""
    state = building.build_escalation_status(ws)
    key = 'e0123456789ab'
    contract = milestone_contract(ws, ws.plan()['milestones'][0])
    _write_json(ws.home / 'build-escalations' / (key + '.json'),
                dict({'id': key, 'state': 'uncertain', 'utc': _now(), 'scope': state['scope'], 'milestone': 'm1',
                      'contract': contract, 'snapshot_digest': state['snapshot_digest'], 'ordinary_attempts': 3}, **changes))
    return key


def test_what_cannot_be_settled_shows_under_needs_you_with_a_choice_that_closes_it(tmp_path, monkeypatch):
    ws, router = home(tmp_path, Gateway(), monkeypatch)
    key = an_unclear_receipt(ws)
    assert building.build_step(ws, None)['allowance_blocked']            # still refused: it is the owner's to settle
    assert close_interrupted_escalations(ws) == [] and receipts(ws)[key]['state'] == 'uncertain'
    assert stuck.stuck_turn(ws, 'wait') is None                          # the schedule judges; the owner is told
    [row] = stuck.owner_needed(ws)
    assert row['milestone'] == 'm1' and row['kind'] == 'interrupted' and row['receipt'] == key
    assert [c['id'] for c in row['choices']][0] == 'close_interrupted'
    assert row['choices'][0]['label'] == 'Close the interrupted call'
    assert 'interrupted' in row['what'] and 'Nothing is sent again by itself' in row['what']
    log = (ws.root / 'RUNESMITH.md').read_text(encoding='utf-8')
    assert log.count('one more try was interrupted') == 1               # one line, not one per step
    stuck.stuck_turn(ws, 'wait')
    assert (ws.root / 'RUNESMITH.md').read_text(encoding='utf-8').count('one more try was interrupted') == 1
    # the one click
    from runesmith.app.server import api_close_interrupted_escalation
    studio = SimpleNamespace(ws=ws, worker=SimpleNamespace(current=None), bus=EventBus())
    result = api_close_interrupted_escalation(studio, {}, {}, key)
    assert result['state'] == 'failed' and receipts(ws)[key]['state'] == 'failed'
    assert 'closed by the owner' in receipts(ws)[key]['error'] and receipts(ws)[key]['reconciled_by'] == 'owner'
    assert 'closed the interrupted one more try' in (ws.root / 'RUNESMITH.md').read_text(encoding='utf-8')
    assert stuck.owner_needed(ws) == []                                  # the card goes at once
    assert used_up(building.build_step(ws, None))
    with pytest.raises(WorkspaceError, match='already settled'):
        api_close_interrupted_escalation(studio, {}, {}, key)


def test_the_close_choice_is_refused_while_a_one_more_try_is_running(tmp_path, monkeypatch):
    ws, router = home(tmp_path, Gateway(), monkeypatch)
    key = an_unclear_receipt(ws)
    from runesmith.app.server import api_close_interrupted_escalation
    studio = SimpleNamespace(ws=ws, worker=SimpleNamespace(current={'kind': 'escalate'}), bus=EventBus())
    with pytest.raises(WorkspaceError, match='running'):
        api_close_interrupted_escalation(studio, {}, {}, key)
    assert receipts(ws)[key]['state'] == 'uncertain'


def test_a_call_whose_saved_job_can_still_be_fetched_is_not_told_to_the_owner_as_an_interruption(tmp_path, monkeypatch):
    ws, router = home(tmp_path, DyingGateway('GET'), monkeypatch)
    key = cut_short(ws, router, at='GET')
    assert stuck.stuck_turn(ws, 'wait') is None and stuck.owner_needed(ws) == []
    assert receipts(ws)[key]['state'] == 'started'                       # the next build fetches it


def test_a_running_one_more_try_is_not_reported_to_the_owner(tmp_path, monkeypatch):
    ws, router = home(tmp_path, Gateway(), monkeypatch)
    an_unclear_receipt(ws, state='started')                             # as a live call's receipt is, while the worker waits on a model
    _write_json(ws.home / 'STUDIO_CURRENT.json', {'id': 'j', 'kind': 'escalate', 'params': {}, 'started': _now()})
    stuck.stuck_turn(ws, 'wait')
    assert stuck.owner_needed(ws) == []
    (ws.home / 'STUDIO_CURRENT.json').unlink()
    stuck.stuck_turn(ws, 'wait')                                         # no job runs: now it is an interruption nothing settled
    assert [r['kind'] for r in stuck.owner_needed(ws)] == ['interrupted']


# ---- the rules the settling keeps -----------------------------------------------------------------------------------------

def test_a_settled_receipt_is_never_rewritten_and_an_answer_after_the_owner_closed_it_changes_nothing(tmp_path, monkeypatch):
    ws, router = home(tmp_path, DyingGateway('GET'), monkeypatch)
    key = cut_short(ws, router, at='GET')
    result = close_interrupted_escalation(ws, key)                      # the owner closes it, though its job can still be fetched
    assert result['state'] == 'failed' and not pending_authors(ws)      # and its answer, if one comes, is not waited for
    before = (ws.home / 'build-escalations' / (key + '.json')).read_bytes()
    assert settle_escalation(ws, key, 'answered', by='x', draft='d1')['state'] == 'failed'
    assert (ws.home / 'build-escalations' / (key + '.json')).read_bytes() == before


def test_settling_one_milestones_receipt_leaves_the_others_alone(tmp_path, monkeypatch):
    ws, router = home(tmp_path, Gateway(), monkeypatch)
    key = an_unclear_receipt(ws, state='started', contract='f' * 64, milestone='m9')   # another milestone's
    assert close_interrupted_escalations(ws, contract=milestone_contract(ws, ws.plan()['milestones'][0])) == []
    assert receipts(ws)[key]['state'] == 'started'
    assert [c['id'] for c in close_interrupted_escalations(ws)] == [key]


def test_an_answered_call_after_a_crash_between_the_answer_and_the_receipt_is_recorded_as_answered(tmp_path, monkeypatch):
    gateway = DyingGateway('GET')
    ws, router = home(tmp_path, gateway, monkeypatch)
    key = cut_short(ws, router, at='GET')
    gateway.dies_on = None
    gateway.fail_poll = False
    import runesmith.app.author_recovery as recovery
    original = recovery._settle_escalation
    monkeypatch.setattr(recovery, '_settle_escalation', lambda *a, **k: (_ for _ in ()).throw(OSError('simulated power cut')))
    with pytest.raises(OSError):
        building.build_step(ws, Router({}, {}))                          # the draft was saved, the receipt not yet
    assert receipts(ws)[key]['state'] == 'started' and len(ws.drafts()) == 1
    monkeypatch.setattr(recovery, '_settle_escalation', original)
    closed = close_interrupted_escalations(ws)                           # the restart settles it from what was kept
    assert [(c['id'], c['state']) for c in closed] == [(key, 'answered')]
    assert receipts(ws)[key]['draft'] == ws.drafts()[0]['id'] and not pending_authors(ws)
    assert [m for m, _ in gateway.requests].count('POST') == 1


def test_the_restart_with_the_dead_jobs_marker_and_the_keep_setting_settles_the_receipt_and_hides_nothing(tmp_path, monkeypatch):
    # The run's restart: the setting "keep", and the one more try's job marker still on disk from the process that died.
    ws, router = home(tmp_path, DyingGateway('POST'), monkeypatch)
    key = cut_short(ws, router, at='POST')
    ws.update_settings({'recovery_policy': 'keep', 'auto_work': False})
    _write_json(ws.home / 'STUDIO_CURRENT.json', {'id': 'j1', 'kind': 'escalate', 'params': {}, 'queued': _now(), 'started': _now()})
    worker = Worker(ws, EventBus())
    worker._recover()
    assert receipts(ws)[key]['state'] == 'failed' and receipts(ws)[key]['error'] == INTERRUPTED
    assert not (ws.home / 'STUDIO_CURRENT.json').exists()               # the dead job's marker is gone: it can hide nothing
    assert worker.history[-1]['kind'] == 'escalate' and worker.history[-1]['result'] == 'interrupted'
    stuck.stuck_turn(ws, 'wait')
    assert [(r['milestone'], r['kind']) for r in stuck.owner_needed(ws)] == [('m1', 'wait')]    # told in the plain way (the setting is to wait)
    assert used_up(building.build_step(ws, None))
    # and when the marker is still there and the receipt cannot be settled, the card is shown (a dead job is not a running one)
    key2 = an_unclear_receipt(ws)
    _write_json(ws.home / 'STUDIO_CURRENT.json', {'id': 'j2', 'kind': 'build', 'params': {}, 'queued': _now(), 'started': _now()})
    stuck.stuck_turn(ws, 'wait')
    assert 'interrupted' in [r['kind'] for r in stuck.owner_needed(ws)] and receipts(ws)[key2] is not None
