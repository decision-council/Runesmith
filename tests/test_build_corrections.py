import json

import pytest

from runesmith.app.build_corrections import (MAX_CORRECTIONS,
                                              correct_rejected_answer,
                                              correction_candidates)
from runesmith.app.planner import PlannerUnavailable, milestone_contract, source_context
from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from test_studio import scripted


def rejected_answer(tmp_path):
    ws=Workspace(tmp_path)
    ws.set_brief('Improve this local fixture.')
    plan=ws.save_plan({'summary':'Fixture','milestones':[{'title':'Change both files','done_when':'public behavior passes'}]})
    milestone=plan['milestones'][0]
    (tmp_path/'tool.py').write_text('value = 1\n')
    (tmp_path/'test_tool.py').write_text('expected = 2\n')
    snapshot=collect_snapshot(ws);freeze_snapshot(ws,snapshot);context=source_context(ws,snapshot=snapshot)
    contract=milestone_contract(ws,milestone)
    answer={
        'author':'fixture-author','contract':contract,'context_digest':context['digest'],
        'snapshot_digest':snapshot['digest'],
        'answer':{'title':'First answer','why':'fixture','files':[
            {'path':'tool.py','purpose':'change value','edits':[{'old_text':'value = 1','new_text':'value = 2'}]},
            {'path':'test_tool.py','purpose':'bad representation','edits':[{'old_text':'missing = 1','new_text':'expected = 2'}]},
        ]},
    }
    answer_path=ws.home/'draft-answers'/'answer.json';_write_json(answer_path,answer)
    attempt_id='a'*32
    _write_json(ws.home/'build-attempts'/(attempt_id+'.json'),{
        'state':'failed','utc':'2026-09-26T00:00:00Z','finished':'2026-09-26T00:00:01Z',
        'contract':contract,'context_digest':context['digest'],'snapshot_digest':snapshot['digest'],
        'error':'Exact edit refused for test_tool.py',
        'feedback':{'path':'test_tool.py','admitted_paths':['tool.py'],'answer_receipt':'draft-answers/answer.json'},
    })
    return ws,attempt_id


def test_correction_retains_unreturned_operations_and_binds_source(tmp_path):
    ws,attempt_id=rejected_answer(tmp_path)
    scripted(ws,[{'title':'Correct test operation','why':'exact current source','files':[
        {'path':'test_tool.py','purpose':'valid replacement','content':'expected = 2\nchecked = True\n'},
    ]}],roles=('plan',))
    draft=correct_rejected_answer(ws,ws.router(),attempt_id)
    files={row['path']:row for row in draft['files']}
    assert files['tool.py']['content']=='value = 2\n'
    assert files['test_tool.py']['content']=='expected = 2\nchecked = True\n'
    assert draft['retained_paths']==['tool.py']
    assert draft['correction_of']==attempt_id
    candidate=correction_candidates(ws)[0]
    assert candidate['corrections']==1 and candidate['remaining']==1


def test_correction_cannot_add_a_path(tmp_path):
    ws,attempt_id=rejected_answer(tmp_path)
    scripted(ws,[{'title':'Broaden','why':'bad','files':[
        {'path':'other.py','purpose':'outside original answer','content':'x=1\n'},
    ]}],roles=('plan',))
    with pytest.raises(PlannerUnavailable,match='path set'):
        correct_rejected_answer(ws,ws.router(),attempt_id)
    assert not (tmp_path/'other.py').exists()


def test_correction_refuses_stale_source_before_call(tmp_path):
    ws,attempt_id=rejected_answer(tmp_path)
    (tmp_path/'tool.py').write_text('value = 9\n')
    assert correction_candidates(ws)==[]        # J2-F21: an answer for an earlier source gets no card
    _write_json(ws.home/'build-corrections'/'c0late.json',{'id':'c0late','attempt':attempt_id,'state':'uncertain',
                                                           'utc':'2026-09-26T00:00:02Z'})
    assert correction_candidates(ws)==[]        # not even with a late correction: it could never be used
    (ws.home/'build-corrections'/'c0late.json').unlink()
    scripted(ws,[{'title':'Unused','why':'unused','files':[
        {'path':'test_tool.py','purpose':'unused','content':'expected=2\n'},
    ]}],roles=('plan',))
    before=sum(row['calls'] for row in ws.call_stats().values())
    with pytest.raises(WorkspaceError,match='stale'):
        correct_rejected_answer(ws,ws.router(),attempt_id)
    assert sum(row['calls'] for row in ws.call_stats().values())==before


def test_two_correction_receipts_exhaust_budget(tmp_path):
    ws,attempt_id=rejected_answer(tmp_path)
    for index in range(MAX_CORRECTIONS):
        _write_json(ws.home/'build-corrections'/(f'c{index}.json'),{
            'id':f'c{index}','attempt':attempt_id,'state':'refused','utc':f'2026-09-26T00:00:0{index}Z'})
    scripted(ws,[{'title':'Unused','why':'unused','files':[]}],roles=('plan',))
    before=sum(row['calls'] for row in ws.call_stats().values())
    with pytest.raises(PlannerUnavailable,match='Two correction'):
        correct_rejected_answer(ws,ws.router(),attempt_id)
    assert sum(row['calls'] for row in ws.call_stats().values())==before


@pytest.mark.parametrize('unresolved', [False, True])
def test_a_correction_no_route_accepted_spends_nothing_and_blocks_nothing(tmp_path, unresolved):
    # Journey J2-F17: every Gemini route was overloaded or at its free limit; the correction was recorded "uncertain",
    # which blocked the next correction until someone reconciled a call that never produced an answer.
    from runesmith.instruments import TransportCensored
    ws, attempt_id = rejected_answer(tmp_path)

    class Refusing:
        def call(self, *args, **kwargs):
            raise TransportCensored('every route failed - gemini:flash overloaded; gemini:flash rate_limited',
                                    receipt={'unresolved': unresolved})
    with pytest.raises(PlannerUnavailable) as failure:
        correct_rejected_answer(ws, Refusing(), attempt_id)
    [row] = [json.loads(p.read_text()) for p in (ws.home / 'build-corrections').glob('*.json')]
    candidate = next(c for c in correction_candidates(ws) if c['attempt'] == attempt_id)
    if unresolved:                                     # an answer may exist remotely: reconcile before another call
        assert row['state'] == 'uncertain' and 'did not arrive' in str(failure.value) and candidate['remaining'] == MAX_CORRECTIONS - 1
        # J2-F18: the page offered "Correct retained answer", which could only fail; now it offers to set it aside.
        assert not candidate['eligible'] and candidate['late_correction'] == row['id']
        from types import SimpleNamespace
        from runesmith.app.server import api_set_aside_correction
        from runesmith.app.worker import EventBus
        studio = SimpleNamespace(ws=ws, bus=EventBus(), worker=SimpleNamespace(current={'kind': 'correct'}))
        with pytest.raises(WorkspaceError, match='running now'):
            api_set_aside_correction(studio, {}, {'reason': 'waited'}, row['id'])
        studio.worker.current = None
        with pytest.raises(WorkspaceError, match='Record the evidence'):
            api_set_aside_correction(studio, {}, {'reason': ' '}, row['id'])
        assert api_set_aside_correction(studio, {}, {'reason': 'waited an hour'}, row['id'])['state'] == 'abandoned'
        candidate = next(c for c in correction_candidates(ws) if c['attempt'] == attempt_id)
        assert candidate['eligible'] and candidate['late_correction'] is None and candidate['remaining'] == MAX_CORRECTIONS - 1
    else:
        assert row['state'] == 'transport_failed' and 'Nothing was used up' in str(failure.value)
        assert candidate['remaining'] == MAX_CORRECTIONS and candidate['eligible']
        scripted(ws, [{'title': 'Corrected', 'why': 'exact current source', 'files': [
            {'path': 'test_tool.py', 'purpose': 'valid replacement', 'content': 'expected = 2\n'}]}], roles=('plan',))
        assert correct_rejected_answer(ws, ws.router(), attempt_id)['id']           # the next correction is allowed


def test_a_refused_answer_is_checked_again_with_no_model_call(tmp_path):
    # Journey J11: every edit carried a "purpose" and the answer was refused as an invalid edit schema (fixed in G13).
    # The kept answer is checked again without asking any model; no try and no correction is used.
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    answer_path=ws.home/'draft-answers'/'answer.json'
    saved=json.loads(answer_path.read_text(encoding='utf-8'))
    saved['answer']['files'][1]['edits']=[{'old_text':'expected = 2','new_text':'expected = 2\nchecked = True','purpose':'say it is checked'}]
    _write_json(answer_path,saved)
    assert correction_candidates(ws)[0]['can_check_again']
    draft=readmit_kept_answer(ws,attempt_id)
    files={row['path']:row for row in draft['files']}
    assert files['tool.py']['content']=='value = 2\n' and files['test_tool.py']['content']=='expected = 2\nchecked = True\n'
    candidate=correction_candidates(ws)[0]
    assert candidate['corrections']==0 and candidate['remaining']==2 and not candidate['can_check_again']
    assert not list((ws.home/'build-corrections').glob('*.json'))            # no correction receipt: nothing used


def test_a_kept_answer_that_still_does_not_fit_says_so_and_uses_nothing(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    with pytest.raises(PlannerUnavailable,match='Checked again with no model call; it still does not fit'):
        readmit_kept_answer(ws,attempt_id)
    candidate=correction_candidates(ws)[0]
    assert candidate['can_check_again'] and candidate['remaining']==2
    assert 'did not match' in candidate['last_recheck']['error']


def test_a_kept_answer_is_not_checked_again_after_its_files_changed(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    (tmp_path/'tool.py').write_text('value = 3\n')
    with pytest.raises(WorkspaceError,match='files changed'):
        readmit_kept_answer(ws,attempt_id)


def refused_correction(ws, attempt_id, files, *, state='refused', draft=None):
    key = 'c' + str(len(list((ws.home/'build-corrections').glob('*.json')))).zfill(12)
    row = {'id':key,'attempt':attempt_id,'state':state,'utc':'2026-09-29T00:01:00Z','number':1,
           'answer':{'title':'Correction','why':'kept','files':files}}
    if draft: row['draft'] = draft
    _write_json(ws.home/'build-corrections'/(key+'.json'),row)
    return key


def test_a_refused_correction_is_replayed_with_the_files_it_left_alone(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    refused_correction(ws,attempt_id,[{'path':'test_tool.py','edits':[{'old_text':'expected = 2','new_text':'expected = 2\nchecked = True','purpose':'label'}]}])
    draft=readmit_kept_answer(ws,attempt_id)
    files={row['path']:row['content'] for row in draft['files']}
    assert files=={'tool.py':'value = 2\n','test_tool.py':'expected = 2\nchecked = True\n'}


def test_a_refused_correction_that_leaves_out_a_needed_file_is_not_replayed(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    refused_correction(ws,attempt_id,[{'path':'tool.py','edits':[{'old_text':'value = 1','new_text':'value = 3'}]}])
    with pytest.raises(WorkspaceError,match='leaves out a file'):
        readmit_kept_answer(ws,attempt_id)


def test_once_a_correction_became_a_draft_the_kept_answer_is_not_offered_again(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    refused_correction(ws,attempt_id,[{'path':'test_tool.py','content':'expected = 2\n'}],state='candidate',draft='d-earlier')
    assert not correction_candidates(ws)[0]['can_check_again']
    with pytest.raises(WorkspaceError,match='already became a draft'):
        readmit_kept_answer(ws,attempt_id)


def test_a_kept_correction_that_names_a_file_twice_is_not_replayed(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    twice=[{'path':'test_tool.py','content':'expected = 2\nfirst = True\n'},{'path':'test_tool.py','content':'expected = 2\nsecond = True\n'}]
    refused_correction(ws,attempt_id,twice)
    with pytest.raises(WorkspaceError,match='names a file twice'):
        readmit_kept_answer(ws,attempt_id)


def test_a_kept_answer_becomes_a_draft_once_and_a_later_correction_builds_on_it(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    answer_path=ws.home/'draft-answers'/'answer.json'
    saved=json.loads(answer_path.read_text(encoding='utf-8'))
    saved['answer']['files'][1]['edits']=[{'old_text':'expected = 2','new_text':'expected = 2\nchecked = True','purpose':'label'}]
    _write_json(answer_path,saved)
    first=readmit_kept_answer(ws,attempt_id)
    with pytest.raises(WorkspaceError,match='already checked again'):
        readmit_kept_answer(ws,attempt_id)                             # no second free draft from the same answer
    scripted(ws,[{'title':'Correct','why':'build on the replayed draft','files':[
        {'path':'test_tool.py','edits':[{'old_text':'checked = True','new_text':'checked = False'}]}]}],roles=('plan',))
    draft=correct_rejected_answer(ws,ws.router(),attempt_id)          # its old text exists only in the replayed draft
    files={row['path']:row['content'] for row in draft['files']}
    assert files['test_tool.py']=='expected = 2\nchecked = False\n' and files['tool.py']=='value = 2\n', (first['id'], files)


def test_a_replayed_correction_credits_who_answered_it(tmp_path):
    from runesmith.app.build_corrections import readmit_kept_answer
    ws,attempt_id=rejected_answer(tmp_path)
    key=refused_correction(ws,attempt_id,[{'path':'test_tool.py','content':'expected = 2\n'}])
    receipt=ws.home/'build-corrections'/(key+'.json')
    row=json.loads(receipt.read_text(encoding='utf-8'))
    row['instrument']={'model':'manual','answered_by':'the model the owner asked'}
    row['answer']['title']=''
    _write_json(receipt,row)
    draft=readmit_kept_answer(ws,attempt_id)
    assert draft['drafted_by']=='the model the owner asked' and draft['title']=='First answer'


def test_a_correction_every_model_refused_before_answering_uses_nothing(tmp_path):
    # Review of J11-G17: a correction too large for a directly called model was recorded "refused" and used one of
    # the two corrections, although no model answered.
    from runesmith.instruments import CallOutcome
    ws, attempt_id = rejected_answer(tmp_path)

    class TooLarge:
        def call(self, *args, **kwargs):
            return CallOutcome(False, error_kind="config", receipt={"refused_before_answer": "too_large"},
                               error="This request needs about 20000 tokens, more than this service accepts at once.")
    with pytest.raises(PlannerUnavailable) as failure:
        correct_rejected_answer(ws, TooLarge(), attempt_id)
    [row] = [json.loads(p.read_text()) for p in (ws.home / 'build-corrections').glob('*.json')]
    candidate = next(c for c in correction_candidates(ws) if c['attempt'] == attempt_id)
    assert row['state'] == 'transport_failed' and 'Nothing was used up' in str(failure.value)
    assert candidate['remaining'] == MAX_CORRECTIONS and candidate['eligible']


def test_a_set_aside_late_correction_leaves_the_earlier_refused_answer_to_check_again(tmp_path):
    # Journey J2-F33: the last correction's answer never arrived; once set aside, the earlier refused correction's
    # answer is the newest kept answer, and checking it again must not be refused as "no answer".
    from runesmith.app import build_corrections as corrections
    ws, attempt_id = rejected_answer(tmp_path)
    folder = ws.home / 'build-corrections'
    folder.mkdir(parents=True, exist_ok=True)
    base = {'attempt': attempt_id, 'utc': '2026-09-28T20:45:43Z'}
    (folder / 'c000000000001.json').write_text(json.dumps(dict(base, id='c000000000001', state='refused', number=1,
        answer={'title': 't', 'why': 'w', 'files': [{'path': 'test_tool.py', 'content': 'expected = 2\n'}]},
        error='old_text did not match')), encoding='utf-8')
    (folder / 'c000000000002.json').write_text(json.dumps(dict(base, id='c000000000002', state='abandoned', number=2,
        utc='2026-09-28T21:29:55Z')), encoding='utf-8')
    history = corrections._corrections(ws, attempt_id)
    assert [row['state'] for row in history] == ['refused', 'abandoned']
    candidate = next(c for c in correction_candidates(ws) if c['attempt'] == attempt_id)
    assert candidate['can_check_again'] and candidate['late_correction'] is None
    try:
        corrections.readmit_kept_answer(ws, attempt_id)
    except WorkspaceError as error:
        assert 'left no answer' not in str(error), error
    except PlannerUnavailable:
        pass
