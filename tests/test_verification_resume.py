import json
from types import SimpleNamespace

import pytest

from runesmith.app import building
from runesmith.app.workspace import Workspace, WorkspaceError
from runesmith.app.verification_resume import resume_verification, resume_status
from test_build_steps import setup, enable


def pending(tmp_path,monkeypatch):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    with monkeypatch.context() as local:
        local.setattr(building,'_run_checks',lambda *args,**kwargs:
                      {'status':'timeout','ok':False,'elapsed_s':120,'limit_s':120,'output':'unfinished'})
        result=building.build_step(ws,ws.router())
    assert result['verification']['status']=='inconclusive'
    return ws,result['draft']


def test_extended_check_uses_real_saved_candidate_once_and_no_model(tmp_path,monkeypatch):
    ws,did=pending(tmp_path,monkeypatch)
    attempts={p.name:p.read_bytes() for p in (ws.home/'build-attempts').glob('*.json')}
    def forbidden(*args,**kwargs):raise AssertionError('No inference for verification continuation')
    monkeypatch.setattr(ws,'router',forbidden)
    result=resume_verification(ws,did,'One explicit check-time allowance')
    assert result['advanced'] and (tmp_path/'app.py').exists()
    assert result['verification']['project_checks']['limit_s']==240
    assert result['verification']['acceptance']['limit_s']==240
    receipt=resume_status(ws,ws._draft(did))['receipt']
    assert receipt['state']=='completed' and receipt['outcome']=='acceptance_passed'
    assert receipt['inference_calls']==0 and receipt['author_budget_reset'] is False
    assert receipt['candidate_digest']==result['verification']['candidate_digest']
    assert attempts=={p.name:p.read_bytes() for p in (ws.home/'build-attempts').glob('*.json')}
    monkeypatch.setattr(building,'_run_checks',forbidden)
    # Durable idempotence survives a fresh Workspace, not only worker queue dedupe.
    again=resume_verification(Workspace(tmp_path),did,'Duplicate click or process restart')
    assert again['already_used'] and again['resume']==result['resume']


def test_second_timeout_cannot_receive_another_extension(tmp_path,monkeypatch):
    ws,did=pending(tmp_path,monkeypatch)
    monkeypatch.setattr(building,'_run_checks',lambda *args,**kwargs:
        {'status':'timeout','ok':False,'elapsed_s':240,'limit_s':kwargs['timeout_s']})
    result=resume_verification(ws,did,'One extra allowance')
    assert result['verification']['status']=='inconclusive'
    assert not (tmp_path/'app.py').exists()
    assert resume_verification(ws,did,'No recursive extensions')['already_used']
    assert building.build_step(ws,None)['verification_required']


@pytest.mark.parametrize('change',['source','candidate','acceptance','goal','author_context'])
def test_stale_evidence_refuses_before_spending_extension(tmp_path,monkeypatch,change):
    ws,did=pending(tmp_path,monkeypatch)
    if change=='source':(tmp_path/'unrelated.py').write_text('changed=1\n')
    elif change=='candidate':
        draft=ws._draft(did);draft['files'][0]['content']='def answer(): return 100\n'
        ws._save_draft_state(draft,draft['state'])
    elif change=='acceptance':
        path=ws.home/'acceptance/m1.py';path.write_text(path.read_text()+'\n# revised expectation\n')
    elif change=='author_context':
        draft=ws._draft(did);draft['context_digest']='0'*64
        ws._save_draft_state(draft,draft['state'])
    else:ws.update_milestone('m1',{'done_when':'A different goal'})
    with pytest.raises(WorkspaceError,match='changed'):
        resume_verification(ws,did,'Must not continue stale evidence')
    assert not list((ws.home/'build-check-resumes').glob('*.json'))


def test_interruption_preserves_reservation_without_silent_retry(tmp_path,monkeypatch):
    ws,did=pending(tmp_path,monkeypatch);calls=[]
    def checkpoint():
        calls.append(1)
        if len(calls)==2:raise RuntimeError('Owner stopped')
    with pytest.raises(RuntimeError,match='Owner stopped'):
        resume_verification(ws,did,'One allowance',checkpoint=checkpoint)
    assert resume_status(ws,ws._draft(did))['receipt']['state']=='interrupted'
    assert resume_verification(ws,did,'Cannot retry unknown/interrupted work')['already_used']


def test_newly_eligible_acceptance_is_not_the_same_check_bundle(tmp_path,monkeypatch):
    from runesmith.app.workspace import _write_json
    ws,did=pending(tmp_path,monkeypatch)
    plan=ws.plan()
    plan['milestones'].append({'id':'m2','title':'Another completed feature',
                               'done_when':'Established behavior','status':'done'})
    _write_json(ws.home/'PLAN.json',plan)
    (ws.home/'acceptance/m2.py').write_text('# Additional acceptance, not previously checked\n')
    with pytest.raises(WorkspaceError,match='changed'):
        resume_verification(ws,did,'This is now a different bundle')
    assert not list((ws.home/'build-check-resumes').glob('*.json'))


def test_extension_respects_observe_and_apply_controls(tmp_path,monkeypatch):
    ws,did=pending(tmp_path,monkeypatch)
    ws.update_settings({'autonomy':'observe'})
    assert 'off' in resume_verification(ws,did,'No execution')['summary']
    assert not resume_status(ws,ws._draft(did))['used']
    ws.update_settings({'autonomy':'propose','build_apply':False})
    result=resume_verification(ws,did,'Checks only; grant does not allow application')
    assert result['verification']['status']=='acceptance_passed'
    assert not result.get('advanced') and not (tmp_path/'app.py').exists()


def test_extension_requires_an_explicit_reason(tmp_path,monkeypatch):
    ws,did=pending(tmp_path,monkeypatch)
    with pytest.raises(WorkspaceError,match='Explain'):
        resume_verification(ws,did,' ')


def test_api_and_worker_expose_resume_without_arbitrary_budget(tmp_path,monkeypatch):
    from runesmith.app.server import api_worker_run
    from runesmith.app.worker import Worker,EventBus
    ws=setup(tmp_path);worker=Worker(ws,EventBus());calls=[]
    def resume(workspace,draft_id,reason,**kwargs):
        calls.append((workspace,draft_id,reason));return {'summary':'Checked once'}
    monkeypatch.setattr('runesmith.app.verification_resume.resume_verification',resume)
    job=api_worker_run(SimpleNamespace(worker=worker),{},
        {'job':'resume_check','params':{'draft_id':'sample','reason':'Explicit','timeout_s':99999}})
    assert job['params']=={'draft_id':'sample','reason':'Explicit'}
    worker._execute(job)
    assert calls==[(ws,'sample','Explicit')]
    assert worker.history[-1]['result']=='done'


@pytest.mark.parametrize('limit',[0,-1,601,True,'240'])
def test_check_deadline_cannot_be_unbounded_or_implicitly_coerced(tmp_path,limit):
    with pytest.raises(WorkspaceError,match='deadline'):
        building._run_checks(tmp_path,'project',tmp_path/'log.txt',timeout_s=limit)


@pytest.mark.parametrize('data',[b'',b'{',b'null',b'[]',b'{}',b'{"id":"partial"}'],
                         ids=['empty','truncated','null','array','empty-object','partial'])
def test_damaged_continuation_remains_used_and_is_never_overwritten(tmp_path,monkeypatch,data):
    ws,did=pending(tmp_path,monkeypatch)
    path=ws.home/'build-check-resumes'/(did+'.json')
    path.parent.mkdir(exist_ok=True);path.write_bytes(data)
    state=resume_status(ws,ws._draft(did))
    assert state['used'] and not state['eligible'] and state['receipt']['state']=='unresolved'
    def forbidden(*args,**kwargs):raise AssertionError('A damaged receipt must not restart checks')
    monkeypatch.setattr(building,'_run_checks',forbidden)
    assert resume_verification(ws,did,'Do not replay unknown execution')['already_used']
    assert path.read_bytes()==data
