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
