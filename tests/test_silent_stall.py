"""A failed one-more-try draft must never leave the schedule building nothing and telling nobody.

The sequence found in a long unattended run: three ordinary tries fail, the one more try (another author) drafts files whose
checks fail, and from then on every scheduled build ended at once with "No unambiguous ordinary author allowance for this
lineage" (the guard looked for an ordinary try behind the one-more-try draft, which has none), the stuck setting's
break-down was refused (a repair step named a file its milestone creates) and spent, and the worker idled for good with
the owner told nothing.
"""
import json

import pytest

from runesmith.app import author_revisions, stuck
from runesmith.app.acceptance_contracts import publish_expectations
from runesmith.app.building import build_escalation_status, build_step, escalate_build, supplement_build
from runesmith.app.planner import PlannerUnavailable
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import WorkspaceError, _read_json, _write_json
from test_build_steps import enable, setup
from test_studio import scripted

WRONG = {'title': 'wrong', 'why': 'not 42', 'files': [
    {'path': 'app.py', 'content': 'def answer():\n    return 0\n'},
    {'path': 'tests/__init__.py', 'content': ''},
    {'path': 'tests/test_app.py', 'content': 'import unittest\nfrom app import answer\n'
                                              'class Tests(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(),42)\n'}]}
RIGHT = {'title': 'right', 'why': '42', 'files': [dict(WRONG['files'][0], content='def answer():\n    return 42\n')] + WRONG['files'][1:]}


def after_a_failed_one_more_try(tmp_path, **settings):
    """Three tries used up, then the one more try's draft, whose checks failed (the state that stalled the run)."""
    ws = setup(tmp_path, acceptance=True)
    enable(ws)
    ws.update_settings({'auto_work': True, 'policy_chosen': True, **settings})
    scripted(ws, [WRONG] * 3, roles=('plan',))
    for _ in range(3):
        build_step(ws, ws.router())
    assert build_escalation_status(ws)['eligible']
    scripted(ws, [WRONG], roles=('plan',))
    escalate_build(ws, ws.router())
    [receipt] = [r for r in (_read_json(p, {}) for p in (ws.home / 'build-escalations').glob('*.json'))]
    draft = ws._draft(receipt['draft'])
    assert draft['state'] == 'needs_revision'
    return ws, draft


def breakdown_answer(*kinds_and_paths):
    return {'diagnosis': 'Not proven; smaller steps may help.', 'coverage': 'The steps feed the original criterion.',
            'evidence_refs': ['parent', 'source_context'],
            'steps': [{'kind': kind, 'title': f'Step {n}', 'detail': 'Do the step.', 'done_when': 'It works.',
                       'suggested_paths': paths} for n, (kind, paths) in enumerate(kinds_and_paths, 1)]}


# ---- the build after a failed one more try -------------------------------------------------------------------------------

def test_a_failed_one_more_try_draft_has_no_ordinary_try_and_no_longer_blocks_the_build(tmp_path):
    ws, draft = after_a_failed_one_more_try(tmp_path)
    assert author_revisions.unfunded_origin(ws, draft) == 'escalation'
    result = build_step(ws, None)                       # no model may be asked: nothing is left to ask
    assert not result.get('allowance_blocked'), result
    assert result.get('replan_needed') and result['milestone'] == 'm1'
    assert 'No unambiguous' not in result['summary']


def test_a_revision_of_a_one_more_try_draft_is_refused_in_words_that_say_what_to_do(tmp_path):
    ws, draft = after_a_failed_one_more_try(tmp_path)
    with pytest.raises(WorkspaceError) as refused:
        author_revisions._lineage(ws, draft)
    text = str(refused.value)
    assert 'one more try' in text and 'smaller steps' in text and 'edit the milestone' in text and 'No new budget' in text


def test_another_ready_milestone_builds_while_one_waits_with_a_failed_one_more_try(tmp_path):
    ws, _ = after_a_failed_one_more_try(tmp_path)
    plan = ws.plan()
    plan['milestones'].append({'id': 'm2', 'title': 'Second', 'done_when': 'second() returns 7', 'status': 'open', 'depends_on': []})
    _write_json(ws.home / 'PLAN.json', plan)
    ws.update_settings({'build_paths': ['app.py', 'tests', 'second.py']})
    scripted(ws, [{'title': 'second', 'why': '7', 'files': [
        {'path': 'second.py', 'content': 'def second():\n    return 7\n'},
        {'path': 'tests/test_second.py', 'content': 'import unittest\nfrom second import second\n'
                                                    'class Tests(unittest.TestCase):\n    def test_second(self): self.assertEqual(second(),7)\n'}]}],
             roles=('plan',))
    result = build_step(ws, ws.router())
    assert result['milestone'] == 'm2' and result.get('draft'), result


def test_a_supplement_draft_does_not_block_a_fresh_ordinary_try_and_its_successor_has_a_lineage(tmp_path):
    ws = setup(tmp_path, acceptance=True)
    enable(ws)
    scripted(ws, [WRONG], roles=('plan',))
    build_step(ws, ws.router())                                          # one ordinary try, two left
    [first] = [d for d in ws.drafts() if d['state'] == 'needs_revision']
    publish_expectations(ws, 'm1', [{'id': 'answer.value', 'description': 'The public answer function returns the required value.'}],
                         'Make the expected output public')
    scripted(ws, [WRONG], roles=('plan',))
    supplement_build(ws, ws.router(), first['id'], 'The owner clarified the expected output')
    [supplement] = [d for d in ws.drafts() if d.get('supplement_of')]
    assert supplement['state'] == 'needs_revision' and author_revisions.unfunded_origin(ws, supplement) == 'supplement'
    scripted(ws, [WRONG], roles=('plan',))
    result = build_step(ws, ws.router())                                 # a fresh ordinary try, on top of the supplement draft
    assert not result.get('allowance_blocked') and result.get('draft'), result
    newest = ws._draft(result['draft'])
    budget = author_revisions._lineage(ws, newest)                       # its lineage stops at the supplement and holds
    assert budget['remaining'] == 1 and len(budget['lineage']) == 1


# ---- the break-down the setting asks for -----------------------------------------------------------------------------------

def test_a_repair_step_that_names_a_file_the_milestone_creates_is_recorded_as_a_build_not_refused(tmp_path):
    ws, _ = after_a_failed_one_more_try(tmp_path, stuck_policy='retry_split')
    ws.update_settings({'build_paths': ['app.py', 'tests', 'engine.py']})
    scripted(ws, [breakdown_answer(('build', ['engine.py']), ('repair', ['app.py', 'engine.py']))], roles=('plan',))
    result = stuck.split(ws, ws.router(), 'm1')
    plan = ws.plan()
    children = [m for m in plan['milestones'] if m.get('parent_id') == 'm1']
    assert [c['kind'] for c in children] == ['build', 'build'], 'a step naming files that do not exist yet is a build'
    [proposal] = [r for r in (_read_json(p, {}) for p in (ws.home / 'breakdowns').glob('*.json'))]
    assert len(proposal['corrections']) == 1 and 'engine.py' in proposal['corrections'][0] and 'build' in proposal['corrections'][0]
    assert 'broke it down into 2 smaller steps' in result['summary']


def test_a_refused_break_down_is_kept_in_plain_words_and_the_owner_is_told(tmp_path):
    ws, _ = after_a_failed_one_more_try(tmp_path, stuck_policy='retry_split')
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ('split', {'milestone': 'm1'})
    scripted(ws, [breakdown_answer(('build', ['app.py']))], roles=('plan',))            # one step: the answer cannot be used
    with pytest.raises(WorkspaceError, match='2-4'):
        stuck.split(ws, ws.router(), 'm1')
    refused = _read_json(ws.home / stuck.REFUSED, {})['m1']
    assert refused['answered'] is True and '2-4' in refused['why']
    assert worker.scheduled_job() == ('build', {})                       # the setting has nothing left to try ...
    [row] = stuck.owner_needed(ws)                                       # ... and says so
    assert row['milestone'] == 'm1' and row['kind'] == 'spent' and row['code'] == 'refused'
    assert 'its one more try are used up' in row['what'] and 'could not be used' in row['what'] and '2-4' in row['what']
    assert [c['id'] for c in row['choices']] == ['breakdown', 'edit', 'set_aside']
    assert row['choices'][0]['label'] == 'Ask for smaller steps again'
    log = (tmp_path / 'RUNESMITH.md').read_text(encoding='utf-8')
    assert log.count('needs you') == 1 and 'set it aside' in log


def test_the_scheduled_step_after_a_failed_one_more_try_and_split_is_never_a_silent_no_op(tmp_path):
    """The whole sequence through the worker: one more try fails, the split is refused, the builds that follow end in the
    used-up verdict, and the owner is told once (the Overview's Needs you and RUNESMITH.md), not at every step."""
    ws, _ = after_a_failed_one_more_try(tmp_path, stuck_policy='retry_split')
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ('split', {'milestone': 'm1'})
    scripted(ws, [breakdown_answer(('build', ['app.py']))], roles=('plan',))
    done = worker._execute({'id': 'j1', 'kind': 'split', 'params': {'milestone': 'm1'}, 'by': 'schedule'}, schedule_next=False)
    assert done['result'] == 'failed'
    assert [r['milestone'] for r in stuck.owner_needed(ws)] == ['m1']                  # told at once, by the job that ended it
    for n in range(3):                                                                  # three scheduled steps in a row
        kind, params = worker.scheduled_job()
        assert kind == 'build'
        step = worker._execute({'id': f'b{n}', 'kind': kind, 'params': params, 'by': 'schedule'}, schedule_next=False)
        assert step['result'] == 'done' and step['outcome'].get('summary', '').startswith('Ordinary author allowance exhausted')
        assert 'No unambiguous' not in step['outcome']['summary']
    assert (tmp_path / 'RUNESMITH.md').read_text(encoding='utf-8').count('needs you') == 1
    assert len([r for r in ws.ledger if r['kind'] == 'stuck.needs_owner']) == 1
    from runesmith.app.server import api_state
    from types import SimpleNamespace
    state = api_state(SimpleNamespace(ws=ws, worker=worker, bus=EventBus(), started=0), {}, None)
    assert [r['milestone'] for r in state['needs_you']] == ['m1']


def test_the_setting_that_only_retries_tells_the_owner_after_the_one_more_try_and_the_default_does_too(tmp_path):
    ws, _ = after_a_failed_one_more_try(tmp_path, stuck_policy='retry')
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ('build', {})
    [row] = stuck.owner_needed(ws)
    assert row['kind'] == 'spent' and row['code'] == 'open' and 'Nothing more is left that your setting may try' in row['what']
    other = tmp_path / 'default'
    other.mkdir()
    ws2, _ = after_a_failed_one_more_try(other, stuck_policy='wait')
    Worker(ws2, EventBus()).scheduled_job()
    [row] = stuck.owner_needed(ws2)
    assert row['kind'] == 'wait' and 'wait for you' in row['what']


def test_the_default_offers_the_one_more_try_before_it_has_been_used(tmp_path):
    ws = setup(tmp_path, acceptance=True)
    enable(ws)
    ws.update_settings({'auto_work': True, 'policy_chosen': True})
    scripted(ws, [WRONG] * 3, roles=('plan',))
    for _ in range(3):
        build_step(ws, ws.router())
    Worker(ws, EventBus()).scheduled_job()
    [row] = stuck.owner_needed(ws)
    assert row['kind'] == 'wait' and [c['id'] for c in row['choices']][:2] == ['escalate', 'breakdown']


def test_the_notice_goes_when_the_owner_edits_sets_aside_or_the_proposal_waits(tmp_path):
    ws, _ = after_a_failed_one_more_try(tmp_path, stuck_policy='retry')
    Worker(ws, EventBus()).scheduled_job()
    assert [r['milestone'] for r in stuck.owner_needed(ws)] == ['m1']
    # smaller steps proposed (the owner pressed the button): the choice becomes reviewing them
    scripted(ws, [breakdown_answer(('build', ['app.py']), ('build', ['tests/test_app.py']))], roles=('plan',))
    from runesmith.app.breakdowns import propose_breakdown
    propose_breakdown(ws, ws.router(), 'm1')
    [row] = stuck.owner_needed(ws)
    assert row['code'] == 'proposed' and row['choices'][0]['id'] == 'review'
    ws.update_milestone('m1', {'detail': 'Make answer() return 42 from a function in app.py.'})        # new wording, new tries
    assert stuck.owner_needed(ws) == []
    ws.update_milestone('m1', {'detail': ''})
    ws.update_milestone('m1', {'status': 'dropped'})
    assert stuck.owner_needed(ws) == []


def test_a_notice_for_a_milestone_that_is_no_longer_stuck_is_dropped_at_the_next_judgement(tmp_path):
    ws, _ = after_a_failed_one_more_try(tmp_path, stuck_policy='retry')
    Worker(ws, EventBus()).scheduled_job()
    assert _read_json(ws.home / stuck.NOTICES, {})
    ws.update_milestone('m1', {'status': 'dropped'})
    stuck.refresh_notices(ws)
    assert _read_json(ws.home / stuck.NOTICES, {}) == {}


def test_a_split_that_no_model_answered_is_not_told_as_refused(tmp_path, monkeypatch):
    ws, _ = after_a_failed_one_more_try(tmp_path, stuck_policy='retry_split')

    def nobody(*args, **kwargs):
        error = PlannerUnavailable('Breakdown call did not reach a model; nothing was used up, ask again later.')
        error.nothing_ran = True
        raise error
    monkeypatch.setattr(stuck, 'propose_breakdown', nobody)
    with pytest.raises(PlannerUnavailable):
        stuck.split(ws, ws.router(), 'm1')
    assert not (ws.home / stuck.REFUSED).exists()
    assert Worker(ws, EventBus()).scheduled_job() == ('split', {'milestone': 'm1'})     # nothing was asked: it is still to come
    assert stuck.owner_needed(ws) == []
