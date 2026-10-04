import copy
import json

import pytest

from runesmith.app.breakdowns import (propose_breakdown, adopt_breakdown, reject_breakdown, input_packet,
                                      abandon_uncertain_breakdown)
from runesmith.app.planner import draft_files, next_milestone, milestone_contract, PlannerUnavailable
from runesmith.app.workspace import Workspace, WorkspaceError
from runesmith.app.acceptance_contracts import publish_expectations
from runesmith.app.worker import EventBus,Worker
from runesmith.instruments import CallOutcome,TransportCensored
from test_studio import scripted


def setup(tmp_path):
    ws=Workspace(tmp_path)
    ws.update_settings({'build_paths':['src','tests']})
    ws.save_plan({'summary':'Service', 'milestones':[
        {'title':'Existing behavior','status':'done','done_when':'Legacy use works'},
        {'title':'Large feature','detail':'Add two functions','done_when':'Both functions work together','status':'doing'}]})
    (tmp_path/'src').mkdir();(tmp_path/'src/tool.py').write_text('value=1\n')
    acceptance=ws.home/'acceptance'/'m2.py';acceptance.parent.mkdir();acceptance.write_text('# fixed owner contract\n')
    return ws


def answer():
    return {'diagnosis':'The feature spans two functions; a narrower first change may help. Not a proven cause.',
            'coverage':'The two prerequisites feed the original combined criterion.',
            'evidence_refs':['parent','source_context'],
            'steps':[{'kind':'build','title':name,'detail':f'Add {name} without removing old behavior.',
                      'done_when':f'{name} returns the specified value.',
                      'suggested_paths':['src/tool.py','tests/test_tool.py']} for name in ('First function','Second function')]}


def proposal(ws):
    scripted(ws,[answer()],roles=('plan',))
    return propose_breakdown(ws,ws.router(),'m2')


def test_proposal_retains_exact_input_and_does_not_mutate_plan_or_acceptance(tmp_path):
    ws=setup(tmp_path);before=copy.deepcopy(ws.plan());a=(ws.home/'acceptance/m2.py').read_bytes()
    result=proposal(ws)
    assert result['state']=='proposed' and result['drafted_by']=='scripted'
    assert ws.plan()==before and (ws.home/'acceptance/m2.py').read_bytes()==a
    receipt=json.loads((ws.home/result['packet_receipt']).read_text())
    assert receipt['packet']['plan']==before and receipt['answer']==answer()
    # Same evidence reuses the existing proposed work, with no second call.
    assert propose_breakdown(ws,ws.router(),'m2')['id']==result['id']
    assert len(list((ws.home/'breakdown-attempts').glob('*.json')))==1


def test_breakdown_receives_public_criteria_not_private_fixtures(tmp_path):
    ws=setup(tmp_path)
    (ws.home/'acceptance/m2.py').write_text('# PRIVATE_FIXTURE_7291\n')
    public=publish_expectations(ws,'m2',[
        {'id':'result.unknown','description':'An unknown result remains distinct from a negative result.'}
    ],'Specify observable semantics')
    b=proposal(ws)
    receipt=json.loads((ws.home/b['packet_receipt']).read_text())
    assert receipt['packet']['public_acceptance']==public
    assert 'PRIVATE_FIXTURE_7291' not in json.dumps(receipt['packet'])
    assert b['public_acceptance_digest']==public['digest']


def test_changed_public_criteria_block_stale_breakdown_adoption(tmp_path):
    ws=setup(tmp_path);b=proposal(ws);before=copy.deepcopy(ws.plan())
    publish_expectations(ws,'m2',[
        {'id':'result.complete','description':'Display the complete result.'}
    ],'Clarified public behavior after the proposal')
    with pytest.raises(WorkspaceError,match='Public acceptance changed'):
        adopt_breakdown(ws,b['id'])
    assert ws.plan()==before


def test_adoption_preserves_original_goal_and_completed_work_and_is_idempotent(tmp_path):
    ws=setup(tmp_path);before=copy.deepcopy(ws.plan());b=proposal(ws)
    result=adopt_breakdown(ws,b['id'],by='external_trainer')
    plan=ws.plan();parent=next(m for m in plan['milestones'] if m['id']=='m2')
    assert {k:parent[k] for k in before['milestones'][1]}==before['milestones'][1]
    assert plan['milestones'][0]==before['milestones'][0]
    assert parent['depends_on']==result['children']
    assert next_milestone(plan)['id']==result['children'][0]  # not the doing parent
    assert (ws.home/'acceptance/m2.py').read_text()=='# fixed owner contract\n'
    assert json.loads((ws.home/'plans/PLAN-v1.json').read_text())==before
    assert adopt_breakdown(ws,b['id'])['already_adopted'] is True
    assert len(ws.plan()['milestones'])==4


def test_parent_and_later_steps_cannot_be_drafted_before_dependencies(tmp_path):
    ws=setup(tmp_path);b=proposal(ws);children=adopt_breakdown(ws,b['id'])['children']
    for mid in ('m2',children[1]):
        with pytest.raises(PlannerUnavailable,match='prerequisites'):draft_files(ws,ws.router(),mid)
    ws.update_milestone(children[0],{'status':'done'})
    assert next_milestone(ws.plan())['id']==children[1]
    ws.update_milestone(children[1],{'status':'done'})
    assert next_milestone(ws.plan())['id']=='m2'
    assert next_milestone(ws.plan())['status']=='doing'  # prerequisites do not auto-complete parent


def test_child_contract_binds_original_parent_criterion(tmp_path):
    ws=setup(tmp_path);b=proposal(ws);adopt_breakdown(ws,b['id'])
    child=next_milestone(ws.plan());before=milestone_contract(ws,child)
    ws.update_milestone('m2',{'done_when':'Changed owner requirement'})
    assert milestone_contract(ws,child)!=before


@pytest.mark.parametrize('change',['plan','source'])
def test_stale_proposal_is_not_adopted(tmp_path,change):
    ws=setup(tmp_path);b=proposal(ws)
    if change=='plan':ws.update_milestone('m2',{'title':'New direction'})
    else:(tmp_path/'src/tool.py').write_text('value=2\n')
    with pytest.raises(WorkspaceError,match='changed'):adopt_breakdown(ws,b['id'])
    assert len(ws.plan()['milestones'])==2


@pytest.mark.parametrize('path',['../escape.py','.runesmith/config.json','README.md','outside.py'])
def test_bad_scope_is_rejected_without_plan_change(tmp_path,path):
    ws=setup(tmp_path);data=answer();data['steps'][0]['suggested_paths']=[path]
    scripted(ws,[data],roles=('plan',))
    with pytest.raises(WorkspaceError):propose_breakdown(ws,ws.router(),'m2')
    assert len(ws.plan()['milestones'])==2
    record=json.loads(next((ws.home/'breakdown-attempts').glob('*.json')).read_text())
    assert record['answer']==data and record['validation_error']


def test_interrupted_call_blocks_blind_repeat(tmp_path):
    ws=setup(tmp_path)
    class Lost:
        calls=0
        def call(self,*args,**kwargs):
            self.calls+=1;raise TransportCensored('response lost')
    router=Lost()
    with pytest.raises(PlannerUnavailable,match='uncertain'):propose_breakdown(ws,router,'m2')
    with pytest.raises(PlannerUnavailable,match='reconciliation'):propose_breakdown(ws,router,'m2')
    assert router.calls==1


def test_uncertain_call_needs_explicit_evidence_before_replanning(tmp_path):
    ws=setup(tmp_path)
    class Lost:
        def call(self,*args,**kwargs):raise TransportCensored('all routes rejected before a job was created')
    with pytest.raises(PlannerUnavailable):propose_breakdown(ws,Lost(),'m2')
    attempt=json.loads(next((ws.home/'breakdown-attempts').glob('*.json')).read_text())
    with pytest.raises(WorkspaceError,match='evidence'):
        abandon_uncertain_breakdown(ws,attempt['id'],'')
    assert abandon_uncertain_breakdown(ws,attempt['id'],'Provider ledger has no job ID and records a pre-job overload.',
                                         by='external_trainer')['state']=='abandoned'
    scripted(ws,[answer()],roles=('plan',))
    assert propose_breakdown(ws,ws.router(),'m2')['state']=='proposed'


def test_changed_evidence_during_call_preserves_answer_but_not_proposal(tmp_path):
    ws=setup(tmp_path)
    class Changed:
        def call(self,*args,**kwargs):
            ws.update_milestone('m2',{'done_when':'Different criterion'})
            return CallOutcome(True,data=answer(),receipt={'model':'example'})
    with pytest.raises(WorkspaceError,match='changed'):propose_breakdown(ws,Changed(),'m2')
    assert not list((ws.home/'breakdowns').glob('*.json'))
    assert json.loads(next((ws.home/'breakdown-attempts').glob('*.json')).read_text())['state']=='answered'


def test_build_attempts_survive_and_one_nested_breakdown_is_bounded(tmp_path):
    ws=setup(tmp_path);folder=ws.home/'build-attempts';folder.mkdir()
    record={'contract':milestone_contract(ws,ws.plan()['milestones'][1]),'state':'failed','error':'old_text missing'}
    path=folder/'earlier.json';path.write_text(json.dumps(record))
    b=proposal(ws);children=adopt_breakdown(ws,b['id'])['children']
    assert json.loads(path.read_text())==record
    with pytest.raises(WorkspaceError,match='already has prerequisite'):input_packet(ws,'m2')

    # A first-level prerequisite may be split once without losing its
    # provenance or weakening either ancestor's acceptance criterion.
    scripted(ws,[answer()],roles=('plan',))
    nested=propose_breakdown(ws,ws.router(),children[0])
    grandchildren=adopt_breakdown(ws,nested['id'])['children']
    child=next(m for m in ws.plan()['milestones'] if m['id']==children[0])
    assert child['breakdown_id']==b['id']
    assert child['decomposed_by']==nested['id']
    assert child['depends_on']==grandchildren
    with pytest.raises(WorkspaceError,match='maximum breakdown depth'):input_packet(ws,grandchildren[0])


def test_plan_commit_reconciles_an_interrupted_adoption_receipt(tmp_path):
    ws=setup(tmp_path);b=proposal(ws);first=adopt_breakdown(ws,b['id'])
    path=ws.home/'breakdowns'/(b['id']+'.json');path.write_text(json.dumps(b))
    second=adopt_breakdown(Workspace(tmp_path),b['id'])
    assert second['already_adopted'] and second['children']==first['children']
    assert json.loads(path.read_text())['state']=='adopted'


def test_worker_can_queue_breakdown_without_executing_it(tmp_path):
    ws=setup(tmp_path);worker=Worker(ws,EventBus())
    job=worker.enqueue('breakdown',milestone='m2')
    assert job['params']=={'milestone':'m2'}
    assert worker.enqueue('breakdown',milestone='m2')['id']==job['id']


def test_build_cap_can_queue_replanning_but_not_adoption(tmp_path,monkeypatch):
    ws=setup(tmp_path);worker=Worker(ws,EventBus())
    monkeypatch.setattr(worker,'_job_build',lambda:{'summary':'Needs a smaller step','replan_needed':True,'milestone':'m2'})
    worker._execute({'id':'cap-off','kind':'build','params':{},'by':'owner'})
    assert list(worker._jobs)==[]                # scheduled work is off in a new home: no follow-up is queued
    ws.update_settings({'auto_work':True,'policy_chosen':True})
    worker._execute({'id':'cap-test','kind':'build','params':{},'by':'owner'})
    assert [j['kind'] for j in worker._jobs]==['breakdown']
    assert len(ws.plan()['milestones'])==2


def test_workspace_api_forwards_breakdown_milestone():
    from types import SimpleNamespace
    from runesmith.app.server import api_worker_run
    captured={}
    class Queue:
        def enqueue(self,kind,**params):
            captured.update(kind=kind,params=params);return captured
    result=api_worker_run(SimpleNamespace(worker=Queue()),{},
                         {'job':'breakdown','params':{'milestone':'m2','apply':True}})
    assert result=={'kind':'breakdown','params':{'milestone':'m2'}}


def test_missing_candidate_file_is_not_a_current_repair_target(tmp_path):
    # A repair is for files that exist now. A step the model labelled a repair that names a file which does not exist yet is
    # a build of that file: recorded so, with a note, instead of refusing the whole answer (which, under the owner's
    # stuck setting, spent the one break-down and left the milestone with nothing to try; journey J11-B28).
    ws=setup(tmp_path);data=answer();data['steps'][0]['kind']='repair'
    scripted(ws,[data],roles=('plan',))
    record=propose_breakdown(ws,ws.router(),'m2')
    assert [s['kind'] for s in record['steps']]==['build','build']
    assert len(record['corrections'])==1 and 'tests/test_tool.py' in record['corrections'][0] and 'src/tool.py' not in record['corrections'][0]
    assert len(ws.plan()['milestones'])==2                       # proposing adopts nothing


def test_a_repair_step_that_names_only_existing_files_stays_a_repair(tmp_path):
    ws=setup(tmp_path);data=answer();data['steps'][0].update(kind='repair',suggested_paths=['src/tool.py'])
    scripted(ws,[data],roles=('plan',))
    record=propose_breakdown(ws,ws.router(),'m2')
    assert [s['kind'] for s in record['steps']]==['repair','build'] and 'corrections' not in record


def test_rejection_is_retained_and_enters_new_proposal_context(tmp_path):
    ws=setup(tmp_path);b=proposal(ws);before=copy.deepcopy(ws.plan())
    reject_breakdown(ws,b['id'],'The failed candidate was not installed.',by='external_trainer')
    packet=input_packet(ws,'m2')
    assert packet['review_feedback'][0]['reason']=='The failed candidate was not installed.'
    assert ws.plan()==before
    with pytest.raises(WorkspaceError):adopt_breakdown(ws,b['id'])


def test_a_dropped_prerequisite_no_longer_blocks_its_goal():
    # Journey J2-B8: the owner dropped the "Add integration tests for export" step (the goal's own approved checks
    # already test that); its goal then said "Waiting for: Add integration tests for export (dropped)" forever.
    from runesmith.app.planner import milestone_ready, plan_readiness
    plan = {'milestones': [{'id': 's1', 'status': 'done'}, {'id': 's3', 'title': 'Integration tests', 'status': 'dropped'},
                           {'id': 's4', 'title': 'Another step', 'status': 'open'},
                           {'id': 'm8', 'status': 'open', 'depends_on': ['s1', 's3']},
                           {'id': 'm9', 'status': 'open', 'depends_on': ['s3', 's4']}]}
    goal, other = plan['milestones'][3], plan['milestones'][4]
    assert milestone_ready(plan, goal) and plan_readiness(plan)['m8']['unmet'] == []
    assert not milestone_ready(plan, other) and [u['id'] for u in plan_readiness(plan)['m9']['unmet']] == ['s4']
