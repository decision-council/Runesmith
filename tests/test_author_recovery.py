import json
from types import SimpleNamespace

import pytest

from runesmith.instruments import MillinerInstrument, Router, TransportCensored
from runesmith.app.author_recovery import pending_authors, resume_author
from runesmith.app.planner import PlannerUnavailable, draft_files
from runesmith.app.workspace import WorkspaceError
from runesmith.app import building
from test_build_steps import setup, enable


class Gateway:
    def __init__(self):
        self.requests=[];self.fail_poll=True;self.agent='test';self.state='succeeded'
        self.answer={'title':'Implementation','files':[{'path':'app.py','content':'def answer():\n    return 42\n'}]}

    def __call__(self,method,url,headers,body,timeout):
        self.requests.append((method,body))
        if method=='POST':return 202,{'job_id':'mj_test','state':'queued','agent':'test'}
        if self.fail_poll:raise TimeoutError('still running')
        return 200,{'job_id':'mj_test','agent':self.agent,'state':self.state,'parsed':self.answer,
                    'error':'truncated' if self.state=='failed' else None,
                    'meta':{'model':'worker','provider':'free','est_usd':0.001,'tokens_out':30}}


def instrument(tmp_path,gateway):
    return MillinerInstrument('model','free:worker',base_url='http://localhost:8765',
        token=lambda:'not-for-receipts',caller_tag='test',timeout_s=2,
        request_dir=tmp_path/'inference-requests',transport=gateway)


def test_timeout_restart_recovers_one_ticket_without_reposting(tmp_path):
    gateway=Gateway();inst=instrument(tmp_path,gateway);events=[]
    router=Router({'m':inst},{'plan':['m']},backoff_s=(1,1),sleep=lambda _:None,on_call=events.append)
    with pytest.raises(TransportCensored) as failure:
        router.call('plan',prompt='p',system='s',schema=None,max_tokens=10,key='once')
    assert failure.value.receipt['unresolved'] and len(events)==1
    assert [m for m,_ in gateway.requests]==['POST','GET']
    sent=gateway.requests[0][1]
    assert sent['wait'] is False and sent['metadata']['caller_ref']=='once-a0'
    receipt=next((tmp_path/'inference-requests').glob('*.json'))
    assert 'not-for-receipts' not in receipt.read_text()
    assert json.loads(receipt.read_text())['body']==sent
    gateway.fail_poll=False
    result=instrument(tmp_path,gateway).resume_request(receipt.stem)
    assert result.ok and result.receipt['est_usd'] is None  # fixture omits input usage
    assert result.receipt['accounting']['reported_est_usd']==0.001
    assert result.receipt['tokens_out']==30
    assert [m for m,_ in gateway.requests].count('POST')==1
    count=len(gateway.requests)
    assert inst.resume_request(receipt.stem).ok and len(gateway.requests)==count


def test_lost_post_response_does_not_guess_or_repost(tmp_path):
    calls=[]
    def lost(method,*args):
        calls.append(method);raise TimeoutError('ticket lost')
    inst=instrument(tmp_path,lost)
    args=dict(prompt='p',system='s',schema=None,max_tokens=10,key='lost')
    first=inst.complete(**args);again=inst.complete(**args)
    assert first.receipt['unresolved'] and again.receipt['unresolved']
    assert calls==['POST'] and not first.receipt.get('job_id')
    with pytest.raises(ValueError,match='different bytes'):
        inst.complete(**dict(args,prompt='different'))
    assert calls==['POST']


def test_authenticated_subtag_is_bound_from_direct_ticket(tmp_path):
    gateway=Gateway();gateway.fail_poll=False;gateway.agent='operator/test'
    def prefixed(*args):
        status,payload=gateway(*args)
        if args[0]=='POST':payload['agent']='operator/test'
        return status,payload
    result=instrument(tmp_path,prefixed).complete(prompt='p',system='s',schema=None,max_tokens=10,key='subtag')
    assert result.ok
    record=json.loads(next((tmp_path/'inference-requests').glob('*.json')).read_text())
    assert record['authenticated_agent']=='operator/test'


def test_terminal_failure_keeps_unqualified_charge_and_does_not_retry(tmp_path):
    gateway=Gateway();gateway.fail_poll=False;gateway.state='failed'
    inst=instrument(tmp_path,gateway)
    result=Router({'m':inst},{'plan':['m']},backoff_s=(1,1),sleep=lambda _:None).call(
        'plan',prompt='p',system='s',schema=None,max_tokens=10,key='bad-json')
    assert not result.ok and result.error_kind=='output'
    assert result.receipt['est_usd'] is None and result.receipt['tokens_out']==30
    assert result.receipt['accounting']['reported_est_usd']==0.001
    assert result.receipt['accounting']['cost_status']=='tokens_incomplete'
    assert [m for m,_ in gateway.requests].count('POST')==1


@pytest.mark.parametrize('status,code',[(502,'all_routes_exhausted'),(503,'kill_switch')])
def test_explicit_pre_submission_gateway_refusal_is_not_unknown(tmp_path,status,code):
    def refusal(*args):
        return status,{'error':code,'message':'Refused at submit','retry_after_s':None,'permanent':False}
    result=instrument(tmp_path,refusal).complete(prompt='p',system='s',schema=None,max_tokens=10,key='refusal')
    assert not result.ok and not result.receipt['unresolved']
    assert result.receipt['remote_state']=='refused'


@pytest.mark.parametrize('agent',['other',None])
def test_wrong_or_missing_caller_is_not_automatically_adopted(tmp_path,agent):
    gateway=Gateway();gateway.fail_poll=False;gateway.agent=agent
    outcome=instrument(tmp_path,gateway).complete(prompt='p',system='s',schema=None,max_tokens=10,key='wrong')
    assert not outcome.ok and outcome.receipt['remote_state']=='binding_mismatch'


def interrupted_build(tmp_path,monkeypatch):
    ws=setup(tmp_path);enable(ws)
    ws.save_instrument('model',{'kind':'milliner','model':'free:worker','base_url':'http://localhost:8765'},
                       key_value='unused',roles=['plan'])
    gateway=Gateway();inst=instrument(ws.home,gateway)
    router=Router({'m':inst},{'plan':['m']},backoff_s=(),on_call=ws.record_call)
    with pytest.raises(PlannerUnavailable):building.build_step(ws,router)
    monkeypatch.setattr('runesmith.config.build_instrument',lambda *args,**kwargs:inst)
    row=pending_authors(ws)[0]
    attempt=next((ws.home/'build-attempts').glob('*.json'))
    assert json.loads(attempt.read_text())['state']=='uncertain'
    return ws,gateway,inst,row,attempt


def test_workspace_resume_is_idempotent_and_never_applies_or_refunds(tmp_path,monkeypatch):
    ws,gateway,inst,row,attempt=interrupted_build(tmp_path,monkeypatch)
    with pytest.raises(PlannerUnavailable,match='unresolved'):
        draft_files(ws,Router({},{}))
    assert 'has not arrived yet' in building.build_step(ws,Router({},{}))['summary']      # plain words (J11-F8)
    gateway.fail_poll=False
    result=resume_author(ws,row['id'])
    assert result['draft'] and not (ws.root/'app.py').exists()
    assert len(ws.drafts())==1 and ws.drafts()[0]['drafted_by']=='free:worker'
    assert not ws.drafts()[0].get('verification')
    assert json.loads(attempt.read_text())['prior_receipt']['state']=='uncertain'
    assert len(list((ws.home/'build-attempts').glob('*.json')))==1
    assert sum(v['calls'] for v in ws.call_stats().values())==1
    assert not pending_authors(ws)
    assert resume_author(ws,row['id'])['already_used']
    assert len(ws.drafts())==1 and [m for m,_ in gateway.requests].count('POST')==1


@pytest.mark.parametrize('change',['source','goal','public','acceptance'])
def test_stale_packet_retains_answer_but_refuses_admission(tmp_path,monkeypatch,change):
    ws,gateway,inst,row,attempt=interrupted_build(tmp_path,monkeypatch)
    if change=='source':(ws.root/'new.py').write_text('x=1')
    if change=='goal':ws.update_milestone('m1',{'done_when':'Different goal'})
    if change=='public':
        from runesmith.app.acceptance_contracts import publish_expectations
        publish_expectations(ws,'m1',[{'id':'new','description':'Different public goal'}],'Test changed criteria')
    if change=='acceptance':
        folder=ws.home/'acceptance';folder.mkdir(exist_ok=True)
        (folder/'m1.py').write_text('different check')
    gateway.fail_poll=False
    with pytest.raises(WorkspaceError,match='changed'):
        resume_author(ws,row['id'])
    assert not ws.drafts() and not (ws.root/'app.py').exists()
    assert list((ws.home/'draft-answers').glob('*.json'))
    assert [m for m,_ in gateway.requests].count('POST')==1


def test_resume_obeys_observe_and_worker_stop(tmp_path,monkeypatch):
    ws,gateway,inst,row,_=interrupted_build(tmp_path,monkeypatch)
    ws.update_settings({'autonomy':'observe'})
    before=len(gateway.requests)
    assert 'Observe' in resume_author(ws,row['id'])['summary']
    assert len(gateway.requests)==before
    ws.update_settings({'autonomy':'propose'})
    from runesmith.app.worker import Worker,EventBus,StopRequested
    worker=Worker(ws,EventBus());worker._stop_after_step=True
    with pytest.raises(StopRequested):worker._job_resume_author(row['id'])
    assert len(gateway.requests)==before


def test_api_limits_resume_to_saved_id(tmp_path,monkeypatch):
    from runesmith.app.server import api_worker_run
    from runesmith.app.worker import Worker,EventBus
    ws=setup(tmp_path);worker=Worker(ws,EventBus());calls=[]
    monkeypatch.setattr('runesmith.app.author_recovery.resume_author',
        lambda workspace,request_id,**kw:calls.append(request_id) or {'summary':'Recovered'})
    job=api_worker_run(SimpleNamespace(worker=worker),{},
        {'job':'resume_author','params':{'request_id':'saved','url':'https://elsewhere','max_calls':10}})
    assert job['params']=={'request_id':'saved'}
    worker._execute(job)
    assert calls==['saved'] and worker.history[-1]['result']=='done'


def test_resumed_draft_still_needs_checks_and_grants_before_apply(tmp_path,monkeypatch):
    ws,gateway,inst,row,_=interrupted_build(tmp_path,monkeypatch)
    gateway.answer['files'] += [
        {'path':'tests/__init__.py','content':''},
        {'path':'tests/test_app.py','content':'import unittest\nfrom app import answer\nclass Test(unittest.TestCase):\n def test_answer(self): self.assertEqual(answer(),42)\n'}]
    # Establish the owner check in a fresh setup before acquisition, not afterward.
    # Here self-checks alone must NEVER authorize automatic application.
    gateway.fail_poll=False;result=resume_author(ws,row['id'])
    checked=building.build_step(ws,Router({},{}))
    assert checked['verification']['status']=='self_checks_passed'
    assert not checked.get('advanced') and not (ws.root/'app.py').exists()
    assert [m for m,_ in gateway.requests].count('POST')==1


def test_recovery_finishes_attempt_reconciliation_after_interruption(tmp_path,monkeypatch):
    ws,gateway,inst,row,attempt=interrupted_build(tmp_path,monkeypatch)
    gateway.fail_poll=False
    import runesmith.app.author_recovery as recovery
    original=recovery._settle_attempt
    def interrupted(*args,**kwargs):raise OSError('simulated local interruption')
    monkeypatch.setattr(recovery,'_settle_attempt',interrupted)
    with pytest.raises(OSError):resume_author(ws,row['id'])
    assert len(ws.drafts())==1 and json.loads(attempt.read_text())['state']=='uncertain'
    monkeypatch.setattr(recovery,'_settle_attempt',original)
    assert resume_author(ws,row['id'])['already_used']
    assert json.loads(attempt.read_text())['state']=='answered'
    assert len(ws.drafts())==1 and [m for m,_ in gateway.requests].count('POST')==1


def test_an_unattended_round_fetches_a_late_answer_and_checks_it_without_a_new_call(tmp_path,monkeypatch):
    # Journey J2-F12: an answer that arrived after the 300 s wait stopped every scheduled round ("requires recovery
    # before another build") until the owner came back. Fetching it is no new call, so the round does it.
    ws,gateway,inst,row,attempt=interrupted_build(tmp_path,monkeypatch)
    gateway.answer['files'] += [
        {'path':'tests/__init__.py','content':''},
        {'path':'tests/test_app.py','content':'import unittest\nfrom app import answer\nclass Test(unittest.TestCase):\n def test_answer(self): self.assertEqual(answer(),42)\n'}]
    still=building.build_step(ws,Router({},{}))                  # still running remotely: nothing to fetch yet
    assert 'has not arrived yet' in still['summary'] and 'does not ask twice' in still['summary'] and not ws.drafts()
    gateway.fail_poll=False
    checked=building.build_step(ws,Router({},{}))                # a router with no model at all: no new call possible
    assert checked['verification']['status']=='self_checks_passed' and len(ws.drafts())==1
    assert not checked.get('advanced') and not (ws.root/'app.py').exists()   # self-checks alone never apply
    assert json.loads(attempt.read_text())['state']=='answered' and not pending_authors(ws)
    assert [m for m,_ in gateway.requests].count('POST')==1


def test_a_late_answer_holds_back_only_its_own_milestone(tmp_path,monkeypatch):
    # Journey J11-B6: one milestone's late answer stopped every milestone's build until it arrived.
    from runesmith.instruments import ScriptedInstrument
    ws,gateway,inst,row,attempt=interrupted_build(tmp_path,monkeypatch)
    assert row['milestone']=='m1' and pending_authors(ws,milestone='m1') and not pending_authors(ws,milestone='m2')
    plan=ws.plan();plan['milestones'].append({'title':'Greeting','done_when':'greet() says hello'});ws.save_plan(plan)
    ws.update_settings({'build_paths':['app.py','greet.py','tests']})
    greeting={'title':'Greeting','why':'the second milestone','files':[{'path':'greet.py','content':'def greet():\n    return "hello"\n'}]}
    router=Router({'s':ScriptedInstrument('s',[greeting])},{'plan':['s']},backoff_s=())
    result=building.build_step(ws,router)                       # m1's answer has not arrived: fetched, then m2 built
    assert ws._draft(result['draft'])['milestone']=='m2', result
    assert [m for m,_ in gateway.requests].count('POST')==1      # m1's request was never sent twice
    assert json.loads(attempt.read_text())['state']=='uncertain' and pending_authors(ws,milestone='m1')
    only_m1=building.build_step(ws,Router({},{}),milestone_id='m1')
    assert 'has not arrived yet' in only_m1['summary']           # its own milestone still waits for it
