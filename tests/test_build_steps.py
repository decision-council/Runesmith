import json
from pathlib import Path
import pytest

from runesmith.app.building import (build_step, recheck_draft, status, verify_draft, build_escalation_status,
                                    escalate_build, review_current_files, current_file_reviews)
from runesmith.app.planner import draft_files
from runesmith.app.planner import PlannerUnavailable
from runesmith.app.workspace import Workspace
from runesmith.app.worker import EventBus, Worker
from test_studio import scripted


def setup(tmp_path, *, acceptance=False):
    ws = Workspace(tmp_path)
    ws.save_plan({'summary':'Tiny calculation service', 'milestones':[{'title':'Answer', 'done_when':'answer() returns 42'}]})
    answer = {'title':'Implementation', 'files':[
        {'path':'app.py','content':'def answer():\n    return 42\n'},
        {'path':'tests/__init__.py','content':''},
        {'path':'tests/test_app.py','content':'import unittest\nfrom app import answer\nclass Tests(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(),42)\n'}]}
    scripted(ws, [answer], roles=('plan',))
    if acceptance:
        path=ws.home/'acceptance'/'m1.py'
        path.parent.mkdir(parents=True)
        path.write_text('import unittest\nfrom app import answer\nclass Acceptance(unittest.TestCase):\n    def test_contract(self): self.assertEqual(answer(),42)\n')
    return ws


def enable(ws):
    ws.update_settings({'build_steps':True,'build_apply':True,'build_paths':['app.py','tests']})


def test_current_file_review_checks_without_model_source_write_or_completion(tmp_path,monkeypatch):
    ws=setup(tmp_path,acceptance=True); enable(ws)
    assert build_step(ws,ws.router())['advanced']
    ws.update_milestone('m1',{'status':'doing'})
    before={p.relative_to(tmp_path):p.read_bytes() for p in
            (tmp_path/'app.py',tmp_path/'tests/test_app.py')}
    drafts_before=ws.drafts()
    def forbidden(*args,**kwargs):
        raise AssertionError('Current-file review must not request inference')
    monkeypatch.setattr(ws,'router',forbidden)
    result=review_current_files(ws,'m1')
    assert result['verification']['status']=='acceptance_passed'
    assert result['inference_calls']==result['source_writes']==0
    assert ws.plan()['milestones'][0]['status']=='doing'
    assert ws.drafts()==drafts_before
    assert all((tmp_path/path).read_bytes()==data for path,data in before.items())
    assert current_file_reviews(ws)==[result]
    assert (ws.home/result['verification']['evidence_dir']/'VERIFICATION.json').is_file()
    from types import SimpleNamespace
    from runesmith.app.server import api_plan
    assert api_plan(SimpleNamespace(ws=ws),{},None)['current_checks']==[result]


@pytest.mark.parametrize('settings',[{'build_steps':False},{'autonomy':'observe'}])
def test_current_file_review_respects_execution_controls(tmp_path,monkeypatch,settings):
    ws=setup(tmp_path);enable(ws);ws.update_settings(settings)
    def forbidden(*args,**kwargs):
        raise AssertionError('Disabled current-file review must not execute checks')
    monkeypatch.setattr('runesmith.app.building.verify_draft',forbidden)
    assert 'off' in review_current_files(ws,'m1')['summary']
    assert current_file_reviews(ws)==[]


def test_current_file_review_requires_ready_milestone(tmp_path):
    from runesmith.app.workspace import WorkspaceError, _write_json
    ws=setup(tmp_path);enable(ws)
    ws.save_plan({'summary':'Prerequisites','milestones':[
        {'id':'m1','title':'First','done_when':'first'},
        {'id':'m2','title':'Later','done_when':'later'}]})
    # Dependency metadata is installed by breakdown adoption, not save_plan.
    plan=ws.plan();plan['milestones'][1]['depends_on']=['m1']
    _write_json(ws.home/'PLAN.json',plan)
    with pytest.raises(WorkspaceError,match='ready'):
        review_current_files(ws,'m2')
    assert current_file_reviews(ws)==[]


def test_worker_accepts_current_file_review_without_starting_a_server(tmp_path,monkeypatch):
    ws=setup(tmp_path);enable(ws)
    calls=[]
    def review(workspace,milestone,**kwargs):
        calls.append((workspace,milestone));return {'summary':'Reviewed current files'}
    monkeypatch.setattr('runesmith.app.building.review_current_files',review)
    worker=Worker(ws,EventBus())
    worker._execute({'id':'current-test','kind':'review_current','params':{'milestone':'m1'},'by':'owner'})
    assert calls==[(ws,'m1')]
    assert worker.history[-1]['result']=='done'


def test_current_file_review_api_queues_only_declared_parameters(tmp_path):
    from types import SimpleNamespace
    from runesmith.app.server import api_worker_run
    ws=setup(tmp_path);worker=Worker(ws,EventBus())
    api_worker_run(SimpleNamespace(worker=worker),{},
                   {'job':'review_current','params':{'milestone':'m1','unexpected':'ignored'}})
    assert len(worker._jobs)==1
    assert worker._jobs[0]['kind']=='review_current'
    assert worker._jobs[0]['params']=={'milestone':'m1'}


def test_current_file_review_stopped_before_snapshot_leaves_no_receipt(tmp_path):
    ws=setup(tmp_path);enable(ws)
    def stopped():
        raise RuntimeError('Stopped by owner')
    with pytest.raises(RuntimeError,match='Stopped by owner'):
        review_current_files(ws,'m1',checkpoint=stopped)
    assert current_file_reviews(ws)==[]
    assert ws.plan()['milestones'][0]['status']=='open'


def test_default_build_only_proposes(tmp_path):
    ws=setup(tmp_path)
    result=build_step(ws,ws.router())
    assert 'review' in result['summary']
    assert not (tmp_path/'app.py').exists()
    assert not status(ws)['apply']


@pytest.mark.parametrize('timeout_phase',['project','acceptance'])
def test_timed_out_verification_is_inconclusive_and_does_not_reauthor(tmp_path,monkeypatch,timeout_phase):
    from runesmith.app.building import recheck_draft
    ws=setup(tmp_path,acceptance=True);enable(ws)
    def checks(stage,kind,logs):
        if (kind=='project') == (timeout_phase=='project'):
            return {'status':'timeout','ok':False,'elapsed_s':120,'limit_s':120,'output':'unfinished'}
        return {'status':'passed','ok':True,'ran':1,'elapsed_s':1,'limit_s':120}
    monkeypatch.setattr('runesmith.app.building._run_checks',checks)
    first=build_step(ws,ws.router())
    assert first['verification']['status']=='inconclusive'
    assert ws._draft(first['draft'])['state']=='waiting'
    attempts={p.name:p.read_bytes() for p in (ws.home/'build-attempts').glob('*.json')}
    class NoCall:
        def call(self,*args,**kwargs):raise AssertionError('No replacement author for an incomplete check')
    def forbidden(*args,**kwargs):raise AssertionError('No automatic executable retry either')
    monkeypatch.setattr('runesmith.app.building._run_checks',forbidden)
    second=build_step(ws,NoCall())
    assert second['verification_required'] and second['draft']==first['draft']
    assert attempts=={p.name:p.read_bytes() for p in (ws.home/'build-attempts').glob('*.json')}
    # An explicit no-model recheck still uses the same candidate and predicates.
    monkeypatch.setattr('runesmith.app.building._run_checks',lambda *args,**kwargs:
                        {'status':'passed','ok':True,'ran':1,'elapsed_s':1,'limit_s':120})
    assert recheck_draft(ws,first['draft'])['verification']['status']=='acceptance_passed'
    assert not (tmp_path/'app.py').exists()  # recheck alone cannot promote


def test_legacy_timeout_is_recognized_without_relaxing_actual_failures():
    from runesmith.app.building import verification_inconclusive
    assert verification_inconclusive({'status':'failed','project_checks':{'status':'timeout'}})
    assert not verification_inconclusive({'status':'failed','project_checks':{'status':'failed'}})
    assert not verification_inconclusive({'status':'failed','detail':'Project tests changed candidate files',
                                         'project_checks':{'status':'timeout'}})


def test_self_tests_are_not_owner_acceptance(tmp_path):
    ws=setup(tmp_path); enable(ws)
    result=build_step(ws,ws.router())
    assert result['verification']['status']=='self_checks_passed'
    assert not (tmp_path/'app.py').exists()
    assert ws.plan()['milestones'][0]['status']=='open'


def test_an_unchanged_waiting_draft_is_not_checked_again_until_its_inputs_change(tmp_path,monkeypatch):
    # F14: scheduled rounds used to recheck the same waiting draft every interval, forever.
    import runesmith.app.building as building
    ws=setup(tmp_path); enable(ws); router=ws.router()
    first=build_step(ws,router)
    assert first['verification']['status']=='self_checks_passed'
    def forbidden(*args,**kwargs):
        raise AssertionError('An unchanged draft must not be checked again')
    monkeypatch.setattr(building,'verify_draft',forbidden)
    again=build_step(ws,router)
    assert again['unchanged'] and again['draft']==first['draft'] and 'waiting for you' in again['summary']
    monkeypatch.undo()
    path=ws.home/'acceptance'/'m1.py'; path.parent.mkdir(parents=True)
    path.write_text('import unittest\nfrom app import answer\nclass Acceptance(unittest.TestCase):\n    def test_contract(self): self.assertEqual(answer(),42)\n')
    after=build_step(ws,router)                       # the owner's new checks mean checking again, then applying
    assert after['draft']==first['draft'] and after.get('advanced') is True


def test_scoped_build_applies_advances_and_undo_reopens(tmp_path):
    ws=setup(tmp_path,acceptance=True); enable(ws)
    result=build_step(ws,ws.router())
    assert result.get('advanced') is True
    assert (tmp_path/'app.py').is_file()
    assert ws.plan()['milestones'][0]['status']=='done'
    assert ws.drafts()[0]['applied_by']=='delegated_build'
    assert ws.undo_draft(result['draft'])['ok']
    assert ws.plan()['milestones'][0]['status']=='doing'


def test_changed_milestone_makes_draft_stale(tmp_path):
    ws=setup(tmp_path)
    draft=draft_files(ws,ws.router())
    ws.update_milestone('m1',{'done_when':'Return 43 now'})
    assert verify_draft(ws,draft)['status']=='stale'


def test_revoke_while_checks_run_prevents_apply(tmp_path):
    ws=setup(tmp_path,acceptance=True); enable(ws)
    count=[0]
    def checkpoint():
        count[0]+=1
        if count[0]==3: ws.update_settings({'build_apply':False})
    result=build_step(ws,ws.router(),checkpoint=checkpoint)
    assert result['verification']['status']=='acceptance_passed'
    assert not (tmp_path/'app.py').exists()


def test_grant_is_bound_to_root_and_paths(tmp_path):
    ws=setup(tmp_path,acceptance=True); enable(ws)
    ws.update_settings({'build_paths':['tests']})
    result=build_step(ws,ws.router())
    assert result['verification']['status']=='acceptance_passed'
    assert not (tmp_path/'app.py').exists()
    path=ws.home/'BUILD_GRANT.json'; data=json.loads(path.read_text())
    data['root']=str(tmp_path/'other');path.write_text(json.dumps(data))
    assert not status(ws)['apply']


def test_partial_write_rolls_back_without_losing_existing_files(tmp_path,monkeypatch):
    ws=Workspace(tmp_path)
    for name in ('a.py','b.py'): (tmp_path/name).write_text('old')
    draft=ws.save_draft(title='batch',why='',drafted_by='test',files=[
        {'path':name,'base':'old','content':'new'} for name in ('a.py','b.py')])
    original=Path.replace
    def fail(self,target):
        if Path(target)==tmp_path/'b.py': raise OSError('simulated second write failure')
        return original(self,target)
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(OSError): ws.apply_draft(draft['id'])
    assert (tmp_path/'a.py').read_text()=='old'
    assert (tmp_path/'b.py').read_text()=='old'
    [journal]=list((ws.home/'backups').glob('*/TRANSACTION.json'))
    assert json.loads(journal.read_text())['state']=='rolled_back'


def test_worker_build_failure_has_cooldown_and_history(tmp_path):
    ws=Workspace(tmp_path);ws.update_settings({'build_steps':True,'onboarded':True})
    worker=Worker(ws,EventBus())
    worker._execute({'id':'test','kind':'build','params':{},'by':'owner'})
    assert worker.history[-1]['result']=='failed'
    assert worker._due()>0


def test_dropping_milestone_during_checks_prevents_apply(tmp_path):
    ws=setup(tmp_path,acceptance=True); enable(ws)
    count=[0]
    def checkpoint():
        count[0]+=1
        if count[0]==3: ws.update_milestone('m1',{'status':'dropped'})
    result=build_step(ws,ws.router(),checkpoint=checkpoint)
    assert not result.get('advanced')
    assert not (tmp_path/'app.py').exists()
    assert ws.plan()['milestones'][0]['status']=='dropped'


def test_unusable_author_answers_exhaust_build_attempt_budget(tmp_path):
    ws=setup(tmp_path);enable(ws)
    scripted(ws, [{'title':'bad', 'files':[]}]*4, roles=('plan',))
    router=ws.router()
    for _ in range(3):
        with pytest.raises(Exception): build_step(ws,router)
    result=build_step(ws,router)
    assert 'Ordinary author allowance exhausted' in result['summary']
    assert len(list((ws.home/'build-attempts').glob('*.json')))==3


def test_one_alternate_author_can_continue_after_ordinary_cap(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    scripted(ws,[{'title':'bad','files':[]}]*3,roles=('plan',))
    for _ in range(3):
        with pytest.raises(Exception):build_step(ws,ws.router())
    state=build_escalation_status(ws)
    assert state['eligible'] and state['attempts']==3 and not state['used']
    scripted(ws,[{'title':'alternate author','why':'bounded escalation','files':[
        {'path':'app.py','content':'def answer():\n    return 42\n'},
        {'path':'tests/__init__.py','content':''},
        {'path':'tests/test_app.py','content':'import unittest\nfrom app import answer\nclass Tests(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(),42)\n'}]}],roles=('plan',))
    result=escalate_build(ws,ws.router())
    assert result['advanced'] and (tmp_path/'app.py').is_file()
    assert build_escalation_status(ws) is None  # no unfinished milestone remains
    [receipt]=list((ws.home/'build-escalations').glob('*.json'))
    assert json.loads(receipt.read_text())['state']=='answered'


def test_project_test_side_effects_cannot_make_acceptance_pass(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    scripted(ws,[{'title':'Depends on test side effect','files':[
        {'path':'app.py','content':'from pathlib import Path\ndef answer(): return 42 if Path("runtime.flag").exists() else 0\n'},
        {'path':'tests/__init__.py','content':''},
        {'path':'tests/test_app.py','content':'import unittest\nfrom pathlib import Path\nclass Tests(unittest.TestCase):\n    def test_setup(self): Path("runtime.flag").write_text("yes"); self.assertTrue(True)\n'}]}],roles=('plan',))
    result=build_step(ws,ws.router())
    assert result['verification']['project_checks']['ok']
    assert result['verification']['status']=='failed'
    assert not (tmp_path/'app.py').exists()


def test_completed_milestone_acceptance_is_a_regression_gate(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    assert build_step(ws,ws.router())['advanced']
    m2=ws.add_milestone('Another capability')
    (ws.home/'acceptance'/(m2['id']+'.py')).write_text('import unittest\nfrom app import extra\nclass NewContract(unittest.TestCase):\n    def test_new(self): self.assertEqual(extra(),7)\n')
    scripted(ws,[{'title':'Regresses previous capability','files':[
        {'path':'app.py','content':'def answer(): return 99\ndef extra(): return 7\n'},
        {'path':'tests/test_app.py','content':'import unittest\nfrom app import answer\nclass Tests(unittest.TestCase):\n    def test_new_answer(self): self.assertEqual(answer(),99)\n'}]}],roles=('plan',))
    result=build_step(ws,ws.router())
    assert result['verification']['project_checks']['ok']
    assert result['verification']['acceptance']['ran']==2
    assert result['verification']['status']=='failed'
    assert (tmp_path/'app.py').read_text()=='def answer():\n    return 42\n'


def test_each_verification_keeps_its_own_receipt(tmp_path):
    ws=setup(tmp_path);enable(ws)
    first=build_step(ws,ws.router())
    first_path=ws.home/first['verification']['evidence_dir']/'VERIFICATION.json'
    original=first_path.read_bytes()
    # An explicit recheck reuses the saved draft; no second model response is needed.
    # (A scheduled build of the unchanged draft keeps its verdict instead: F14.)
    second=recheck_draft(ws,first['draft'])
    second_path=ws.home/second['verification']['evidence_dir']/'VERIFICATION.json'
    assert first_path != second_path and second_path.is_file()
    assert first_path.read_bytes()==original
    assert len(ws.drafts()[0]['verification_history'])==2


def test_check_timeout_preserves_partial_output_and_deadline(tmp_path, monkeypatch):
    import subprocess
    from runesmith.app import building

    def interrupted(command, **kwargs):
        assert kwargs['timeout'] == building.CHECK_TIMEOUT_S
        kwargs['stdout'].write(b'test_kept (Tests) ... ok\ntest_unfinished (Tests) ... ')
        kwargs['stdout'].flush()
        raise subprocess.TimeoutExpired(command, kwargs['timeout'])

    monkeypatch.setattr(building.subprocess, 'run', interrupted)
    result = building._run_checks(tmp_path, 'project', tmp_path/'checks.txt')
    assert result['status'] == 'timeout' and result['ok'] is False
    assert 'test_kept' in result['output'] and 'test_unfinished' in result['output']
    assert result['limit_s'] == building.CHECK_TIMEOUT_S
    assert result['elapsed_s'] >= 0
    assert 'ran' not in result  # A missing final summary is unknown, not zero tests.


def test_recheck_uses_saved_candidate_without_inference_or_apply(tmp_path, monkeypatch):
    from runesmith.app.building import recheck_draft
    from runesmith.app.server import api_worker_run
    from types import SimpleNamespace
    ws=setup(tmp_path,acceptance=True)
    draft=draft_files(ws,ws.router())
    enable(ws)
    def forbidden(*args, **kwargs):
        raise AssertionError('A recheck must not ask any model to author again')
    monkeypatch.setattr(ws,'router',forbidden)
    worker=Worker(ws,EventBus())
    job=api_worker_run(SimpleNamespace(worker=worker), {},
                       {'job':'build','params':{'draft_id':draft['id'],'probe':True}})
    assert job['params']=={'draft_id':draft['id']}
    result=worker._job_build(**job['params'])
    assert result['verification']['status']=='acceptance_passed'
    assert not result.get('advanced') and not (tmp_path/'app.py').exists()
    assert not list((ws.home/'build-attempts').glob('*.json'))
    assert ws.plan()['milestones'][0]['status']=='open'
    from runesmith.app.workspace import WorkspaceError
    with pytest.raises(WorkspaceError, match='draft_id must be nonempty'):
        worker._job_build(draft_id='')
    ws.update_milestone('m1',{'status':'dropped'})
    assert 'no longer active' in recheck_draft(ws,draft['id'])['summary']


@pytest.mark.parametrize('checking', [True, False])
def test_a_fresh_draft_is_checked_at_once_only_when_checking_is_on(tmp_path, checking):
    # Journey J1-F7: with checking on, "Draft first files" left the draft unverified until Recheck.
    ws = setup(tmp_path, acceptance=True)
    if checking: enable(ws)
    worker = Worker(ws, EventBus())
    worker._execute({'id': 'first-files', 'kind': 'draft', 'params': {'milestone': 'm1'}, 'by': 'owner'})
    done = worker.history[-1]
    assert done['result'] == 'done', done
    draft = ws._draft(done['outcome']['draft'])
    if checking:
        assert draft['verification']['status'] == 'acceptance_passed' and draft['state'] == 'waiting'
        assert 'passed' in done['outcome']['summary'] and 'Nothing was written' in done['outcome']['summary']
    else:
        assert not draft.get('verification') and done['outcome']['summary'] == draft['title']
    assert not (tmp_path / 'app.py').exists()          # checked or not, a fresh draft is never applied here
