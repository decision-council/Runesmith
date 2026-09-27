import copy
import json

import pytest

from runesmith.app.goalposts import draft_goalposts, save_goalposts
from runesmith.app.planner import PlannerUnavailable, draft_prompt
from runesmith.app.worker import EventBus, StopRequested, Worker
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from runesmith.instruments import CallOutcome, TransportCensored
from test_studio import call, scripted, studio


def answer():
    return {'summary':'Useful local support', 'goalposts':[{
        'title':'No lost cases', 'tier':'minimum', 'measurement':'Cases recovered after reopening the database / cases written',
        'target':'100% of a mixed 20-case fixture', 'why':'Persistence is fundamental.',
        'scenario':'20 synthetic cases including legacy statuses', 'window':'One local restart check',
        'next_check':'Include legacy statuses and an empty queue.', 'milestone_ids':['m1'], 'evidence_refs':['plan'],
        'status':'achieved'}]}


def workspace(tmp_path):
    ws=Workspace(tmp_path)
    ws.save_plan({'milestones':[{'title':'Persistence', 'status':'done'}]})
    ws.add_goal('Make support useful.')
    return ws


def test_goalposts_are_model_authored_proposals_not_plan_edits(tmp_path):
    ws=workspace(tmp_path)
    plan=copy.deepcopy(ws.plan());goals=copy.deepcopy(ws.goals())
    scripted(ws,[answer()],roles=('plan',))
    result=draft_goalposts(ws,ws.router())
    assert result['drafted_by']=='scripted'
    assert result['goalposts'][0]['status']=='proposed'
    assert ws.plan()==plan and ws.goals()==goals
    assert ws.goalposts()==result
    assert 'No lost cases' in draft_prompt(ws,ws.plan()['milestones'][0])
    receipts=list((ws.home/'goalpost-attempts').glob('*.json'))
    assert json.loads(receipts[0].read_text())['answer']['summary']=='Useful local support'


@pytest.mark.parametrize('field,value',[('milestone_ids',['made-up']),('evidence_refs',['imaginary logs']),('tier','proven'),('measurement','')])
def test_invalid_targets_never_replace_existing(tmp_path,field,value):
    ws=workspace(tmp_path)
    old=save_goalposts(ws,answer(),author='test',packet_digest='one',evidence_keys=['plan'])
    bad=answer();bad['goalposts'][0][field]=value
    with pytest.raises(WorkspaceError):
        save_goalposts(ws,bad,author='test',packet_digest='two',evidence_keys=['plan'])
    assert ws.goalposts()==old


def test_each_goalpost_revision_is_preserved(tmp_path):
    ws=workspace(tmp_path)
    first=save_goalposts(ws,answer(),author='A',packet_digest='one',evidence_keys=['plan'])
    second=save_goalposts(ws,answer(),author='B',packet_digest='two',evidence_keys=['plan'])
    assert second['version']==2 and second['drafted_by']=='B'
    assert json.loads((ws.home/'goalposts/v1.json').read_text())==first


def test_changed_inputs_preserve_answer_without_installing(tmp_path):
    ws=workspace(tmp_path)
    class Changed:
        def call(self,*args,**kwargs):
            ws.update_milestone('m1',{'status':'open'})
            return CallOutcome(True,data=answer(),receipt={'model':'free-model'})
    with pytest.raises(PlannerUnavailable,match='changed'):
        draft_goalposts(ws,Changed())
    assert ws.goalposts() is None
    assert json.loads(next((ws.home/'goalpost-attempts').glob('*.json')).read_text())['state']=='answered'


def test_transport_uncertainty_blocks_silent_repeat(tmp_path):
    ws=workspace(tmp_path)
    class Lost:
        calls=0
        def call(self,*args,**kwargs):
            self.calls+=1
            raise TransportCensored('lost connection')
    router=Lost()
    with pytest.raises(PlannerUnavailable,match='uncertain'):draft_goalposts(ws,router)
    with pytest.raises(PlannerUnavailable,match='reconciliation'):draft_goalposts(ws,router)
    assert router.calls==1


def test_worker_job_and_pause(tmp_path):
    ws=workspace(tmp_path);scripted(ws,[answer()],roles=('plan',))
    worker=Worker(ws,EventBus())
    assert worker.enqueue('goalposts')['kind']=='goalposts'
    worker.paused=True
    with pytest.raises(StopRequested):worker._job_goalposts()
    worker.paused=False
    assert 'model-proposed' in worker._job_goalposts()['summary']
    assert ws.goalposts()['version']==1


def test_goalposts_http_read_and_queue(studio):
    assert call(studio,'GET','/api/goalposts')[1]['goalposts'] is None
    assert call(studio,'POST','/api/worker/run',{'job':'goalposts'})[0]==200
