import json
from pathlib import Path
import pytest

from runesmith.app.building import (build_step, recheck_draft, status, verify_draft, build_escalation_status,
                                    escalate_build, review_current_files, current_file_reviews,
                                    readmit_escalation_answer)
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
    limits={}
    def checks(stage,kind,logs,**options):
        limits[kind=='project']=options.get('timeout_s')
        if (kind=='project') == (timeout_phase=='project'):
            return {'status':'timeout','ok':False,'elapsed_s':120,'limit_s':120,'output':'unfinished'}
        return {'status':'passed','ok':True,'ran':1,'elapsed_s':1,'limit_s':120}
    monkeypatch.setattr('runesmith.app.building._run_checks',checks)
    first=build_step(ws,ws.router())
    assert first['verification']['status']=='inconclusive'
    # The owner run's limit comes from its number of checks (journey J11-B17); the project run keeps the default.
    assert limits[True] is None
    if timeout_phase=='acceptance':
        from runesmith.app.building import CHECK_TIMEOUT_S
        assert limits[False]==CHECK_TIMEOUT_S             # one small file: the 120 s floor
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
    assert again['unchanged'] and again['draft']==first['draft'] and 'waits for you' in again['summary']
    assert first['draft'] not in again['summary'] and '“Answer”' in again['summary']      # J2-F26: titles, not ids
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
    assert any(line['text'].startswith('Building the next step did not finish: ') for line in worker.lines)   # J2-F9
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


def test_a_draft_left_for_a_milestone_another_draft_finished_no_longer_waits(tmp_path):
    # Journey J2-F1: R1's first, never-checked m4 draft kept the Overview saying "1 draft waits for your review"
    # hours after a second m4 draft had passed its checks, been written and finished the milestone.
    ws = setup(tmp_path)
    early = draft_files(ws, ws.router(), 'm1')
    scripted(ws, [{'title': 'Second try', 'files': [{'path': 'app.py', 'content': 'def answer():\n    return 42\n'}]}],
             roles=('plan',))
    (tmp_path / 'app.py').write_text('def answer():\n    return 0\n')          # the source changed in between, as in R1
    later = draft_files(ws, ws.router(), 'm1')
    assert ws.state()['drafts'] == {'waiting': 2}
    ws.apply_draft(later['id'])
    ws.update_milestone('m1', {'status': 'done'})
    assert ws.state()['drafts'] == {'superseded': 1, 'applied': 1}
    listed = {d['id']: d for d in ws.work()['drafts']}
    assert listed[early['id']]['superseded_by'] == later['id'] and listed[later['id']]['superseded_by'] is None
    assert ws.work()['draft_counts'] == {'superseded': 1, 'applied': 1}
    assert ws._draft(early['id'])['state'] == 'waiting'          # the stored record is unchanged


def test_a_corrected_draft_does_not_trip_the_ordinary_lineage_guard(tmp_path):
    # Journey J2-B7: after a correction's draft failed its checks, the next scheduled round ended "Invalid author
    # request key": the lineage guard assumed every draft needing revision came from an ordinary attempt.
    ws = setup(tmp_path, acceptance=True); enable(ws)
    corrected = draft_files(ws, ws.router(), 'm1')
    ws._save_draft_state(dict(corrected, author_request_key=None, correction_of='a' * 32), 'needs_revision')
    result = build_step(ws, ws.router())
    assert 'Invalid author request key' not in result.get('summary', '')



def test_a_kept_answer_an_older_runesmith_refused_can_be_checked_again_without_a_model(tmp_path, monkeypatch):
    # Journey J2-G1/F23: the one more try at m8 (a free model, 200 s) sent 8 exact edits; Runesmith allowed 6 and refused
    # the whole answer. A newer Runesmith accepts it, and the owner can check the kept answer again with no model call.
    from runesmith.app import planner
    ws=setup(tmp_path,acceptance=True);enable(ws)
    lines=''.join(f'A{n} = {n}\n' for n in range(1,8))
    wrong={'title':'wrong','files':[{'path':'app.py','content':lines+'def answer():\n    return 0\n'},
        {'path':'tests/__init__.py','content':''},
        {'path':'tests/test_app.py','content':'import unittest\nfrom app import answer\nclass Tests(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(),42)\n'}]}
    scripted(ws,[wrong]*3,roles=('plan',))
    for _ in range(3):
        try:build_step(ws,ws.router())
        except Exception:pass
    assert any(d.get('state')=='needs_revision' for d in ws.drafts())
    eight={'title':'eight edits','why':'fix','files':[{'path':'app.py','edits':
        [{'old_text':f'A{n} = {n}','new_text':f'B{n} = {n}'} for n in range(1,8)]+[{'old_text':'return 0','new_text':'return 42'}]}]}
    monkeypatch.setattr(planner,'MAX_EDITS',6)                          # the Runesmith that refused it
    scripted(ws,[eight],roles=('plan',))
    with pytest.raises(Exception,match='1-6 exact edits'):
        escalate_build(ws,ws.router())
    kept=build_escalation_status(ws)['kept_answer']
    assert kept and '1-6 exact edits' in kept['error'] and kept['last_recheck'] is None
    with pytest.raises(Exception,match='1-6 exact edits'):             # checked again, still refused
        readmit_escalation_answer(ws,kept['id'])
    kept=build_escalation_status(ws)['kept_answer']                    # J2-F24: when, and why it still does not fit
    assert kept['last_recheck']['utc'] and '1-6 exact edits' in kept['last_recheck']['error']
    monkeypatch.setattr(planner,'MAX_EDITS',12)                         # the updated one
    before=sum(row['calls'] for row in ws.call_stats().values())
    worker=Worker(ws,EventBus())
    done=worker._execute({'id':'j1','kind':'readmit','params':{'escalation':kept['id']},'by':'owner'},schedule_next=False)
    assert done['result']=='done' and done['outcome'].get('advanced'), done
    assert 'return 42' in (tmp_path/'app.py').read_text() and 'B7 = 7' in (tmp_path/'app.py').read_text()
    assert sum(row['calls'] for row in ws.call_stats().values())==before              # no model was asked



def test_the_whole_folder_can_be_allowed_for_a_new_project(tmp_path):
    # Journey J11-B1: the owner of a new project typed "." for the files Runesmith may write; saving failed with "not
    # found: tuple index out of range". "." now means the whole folder; Runesmith's own records stay out of reach.
    from runesmith.app.building import _within_scope
    from runesmith.app.workspace import WorkspaceError
    ws=setup(tmp_path,acceptance=True)
    assert ws._safe_rel('.') is None and ws._safe_rel('./') is None
    ws.update_settings({'build_steps':True,'build_apply':True,'build_paths':['./']})
    assert ws.settings()['build_paths']==['.']
    assert _within_scope('app.py',['.']) and _within_scope('tests/test_app.py',['.']) and not _within_scope('app.py',['src'])
    with pytest.raises(WorkspaceError,match='Use . for the whole folder'):
        ws.update_settings({'build_paths':['../elsewhere']})
    result=build_step(ws,ws.router())
    assert result['advanced'] and (tmp_path/'app.py').is_file() and (tmp_path/'tests'/'test_app.py').is_file()



@pytest.mark.parametrize('spent', [0, 40])
def test_a_try_no_model_answered_uses_up_nothing(tmp_path, spent):
    # Journey J2-B9: with every free route at capacity ("nvidia capacity reached"), each round's call failed with zero
    # tokens, yet counted as one of the three tries, and the one more try was burned the same way.
    from runesmith.instruments import TransportCensored
    ws = setup(tmp_path, acceptance=True); enable(ws)

    class AtCapacity:
        def __init__(self, used=spent):
            self.used = used

        def call(self, *args, **kwargs):
            raise TransportCensored('nvidia capacity reached; no alternative route available',
                                    receipt={'unresolved': False, 'tokens_in': 0, 'tokens_out': self.used, 'job_id': 'mj_x'})
    for _ in range(3):
        with pytest.raises(Exception):
            build_step(ws, AtCapacity())
    states = sorted(json.loads(p.read_text())['state'] for p in (ws.home / 'build-attempts').glob('*.json'))
    if spent:                                              # a model generated: those tries count
        assert states == ['failed'] * 3 and build_escalation_status(ws)['eligible']
        with pytest.raises(Exception):
            escalate_build(ws, AtCapacity(used=0))           # no model answered: the one more try is still there
        assert build_escalation_status(ws)['eligible']
        with pytest.raises(Exception):
            escalate_build(ws, AtCapacity())
        assert not build_escalation_status(ws)['eligible']
    else:
        assert states == ['transport_failed'] * 3
        state = build_escalation_status(ws)
        assert not state['eligible'] and state['allowance']['remaining'] == 3        # all three tries are still there


def two_milestones(tmp_path):
    ws = Workspace(tmp_path)
    ws.save_plan({'summary':'Two independent parts', 'milestones':[{'title':'Answer', 'done_when':'answer() returns 42'},
                                                                   {'title':'Greeting', 'done_when':'greet() says hello'}]})
    enable(ws)
    ws.update_settings({'build_paths':['app.py','greet.py','tests']})
    return ws


GREETING = {'title':'Greeting', 'why':'the second milestone', 'files':[{'path':'greet.py','content':'def greet():\n    return "hello"\n'}]}


def test_a_milestone_whose_tries_are_used_up_no_longer_holds_back_an_independent_one(tmp_path):
    # Journey J11-B6: s1's used-up tries left five independent ready milestones idle for 1 h 39 min, because every
    # round picked the first ready milestone again and reported "allowance exhausted".
    ws = two_milestones(tmp_path)
    scripted(ws, [{'title':'bad', 'files':[]}]*3 + [GREETING], roles=('plan',))
    router = ws.router()
    for _ in range(3):
        with pytest.raises(Exception): build_step(ws, router)
    result = build_step(ws, router)
    assert ws._draft(result['draft'])['milestone'] == 'm2' and 'exhausted' not in result['summary'], result
    assert len(list((ws.home/'build-attempts').glob('*.json'))) == 4          # exactly one call, for m2


def test_when_every_ready_milestone_needs_the_owner_the_round_names_each_and_makes_no_call(tmp_path):
    ws = two_milestones(tmp_path)
    scripted(ws, [{'title':'bad', 'files':[]}]*6, roles=('plan',))
    router = ws.router()
    for _ in range(6):
        with pytest.raises(Exception): build_step(ws, router)
    result = build_step(ws, router)
    assert result['all_blocked'] and result['milestones_blocked'] == ['m1', 'm2'], result
    assert result['summary'].startswith('All 2 ready milestones need you or a late answer.')
    assert '“Answer”: its three tries are used up' in result['summary'] and '“Greeting”: its three tries are used up' in result['summary']
    assert result['replan_needed'] and result['milestone'] == 'm1'           # the smaller-steps proposal, as before
    assert len(list((ws.home/'build-attempts').glob('*.json'))) == 6
    assert build_escalation_status(ws)['milestone'] == 'm1'


def test_the_one_more_try_belongs_to_the_milestone_whose_tries_are_used_up(tmp_path):
    ws = two_milestones(tmp_path)
    ws.update_milestone('m2', {'status': 'doing'})       # m2 first in the builder's order (the Studio's status control)
    scripted(ws, [{'title':'bad', 'files':[]}]*3, roles=('plan',))
    for _ in range(3):
        with pytest.raises(Exception): build_step(ws, ws.router())
    state = build_escalation_status(ws)
    assert state['milestone'] == 'm2' and state['eligible'], state
    ws.update_milestone('m2', {'status': 'open'})        # m1 first again; m2's tries are still used up
    assert build_escalation_status(ws)['milestone'] == 'm2'


def test_the_owner_can_build_a_chosen_milestone(tmp_path):
    ws = two_milestones(tmp_path)
    scripted(ws, [GREETING], roles=('plan',))
    result = build_step(ws, ws.router(), milestone_id='m2')
    assert ws._draft(result['draft'])['milestone'] == 'm2'
    assert 'cannot be built now' in build_step(ws, ws.router(), milestone_id='m9')['summary']


def test_every_milestone_s_late_answer_is_fetched_and_one_that_arrived_is_checked(tmp_path, monkeypatch):
    # Review of J11-B6: with two late answers outstanding, each round fetched only the first; a second that had
    # arrived was never fetched, and both milestones waited for good. Fetching is no model call.
    from runesmith.app import author_recovery, building as built
    ws = two_milestones(tmp_path)
    arrived = ws.save_draft(title='Greeting', why='a late answer', files=[{'path':'greet.py','content':'def greet():\n    return "hello"\n'}],
                            drafted_by='late', milestone='m2')
    rows = [{'id':'r1','key':'draft-m1-1','state':'pending','milestone':'m1','can_resume':True},
            {'id':'r2','key':'draft-m2-1','state':'pending','milestone':'m2','can_resume':True}]
    fetched = []

    def pending(ws, milestone=None):
        return [row for row in rows if milestone is None or row['milestone'] in (milestone, None)]

    def resume(ws, request_id, checkpoint=None):
        fetched.append(request_id)
        if request_id == 'r2':
            rows[:] = [row for row in rows if row['id'] != 'r2']
            return {'summary':'fetched', 'draft':arrived['id']}
        return {'summary':'The late answer has not arrived yet; Runesmith waits for it and does not ask twice.'}
    monkeypatch.setattr(author_recovery, 'pending_authors', pending)
    monkeypatch.setattr(author_recovery, 'resume_author', resume)
    monkeypatch.setattr(built, '_check_and_record', lambda ws, draft, milestone, contract, checkpoint: {'checked':draft['id'], 'milestone':milestone['id']})
    assert build_step(ws, ws.router()) == {'checked':arrived['id'], 'milestone':'m2'}
    assert fetched == ['r1', 'r2']                                # both fetched in one round, no model asked
    fetched.clear()
    rows[:] = [dict(rows[0], milestone=None)]                     # an answer whose milestone is unknown holds all
    assert 'has not arrived yet' in build_step(ws, ws.router())['summary'] and fetched == ['r1']


def test_a_build_every_model_refused_before_answering_uses_no_try(tmp_path):
    # Review of J11-G17: a build request too large for a directly called model counted as one of the three tries.
    from runesmith.instruments import CallOutcome
    ws = setup(tmp_path, acceptance=True); enable(ws)

    class TooLarge:
        def call(self, *args, **kwargs):
            return CallOutcome(False, error_kind="config", receipt={"refused_before_answer": "too_large"},
                               error="This request needs about 20000 tokens, more than this service accepts at once.")
    for _ in range(3):
        with pytest.raises(Exception):
            build_step(ws, TooLarge())
    states = sorted(json.loads(p.read_text())['state'] for p in (ws.home / 'build-attempts').glob('*.json'))
    assert states == ['transport_failed'] * 3
    assert build_escalation_status(ws)['allowance']['remaining'] == 3


def test_the_one_more_try_goes_to_a_milestone_that_has_not_used_its_own(tmp_path, monkeypatch):
    # Journey J2-F34: m8's one more try was spent; m9's tries were used up too, but only m8's card was ever shown.
    from runesmith.app import building
    ws = setup(tmp_path, acceptance=True); enable(ws)
    ready = building.ready_milestones(ws.plan())
    assert len(ready) >= 1
    first = ready[0]
    second = dict(first, id='m-second', title='Second')
    monkeypatch.setattr(building, 'ready_milestones', lambda plan: [first, second])
    contracts = {first['id']: 'c-first', 'm-second': 'c-second'}
    monkeypatch.setattr(building, 'milestone_contract', lambda ws, m: contracts[m['id']])
    spent = {'c-first': [{'id': 'e1'}], 'c-second': []}

    def allowance(ws, contract, snapshot):
        return {'remaining': 0, 'used': 3, 'limit': 3, 'escalations': spent[contract], 'scope': contract, 'attempts': [], 'known': True,
                'can_draft': False, 'blockers': [], 'snapshot_digest': snapshot, 'reuse_draft': None}
    monkeypatch.setattr(building, 'ordinary_allowance', allowance)
    assert building.build_escalation_status(ws)['milestone'] == 'm-second'
    spent['c-second'] = [{'id': 'e2'}]
    assert building.build_escalation_status(ws)['milestone'] == first['id']     # both used: the first, as before


def test_identical_failed_scheduled_rounds_are_one_row_with_a_count():
    # Review of batch E: a refused key uses no try, so every scheduled round failed the same way; each added a row.
    from runesmith.app.worker import _same_waiting_round
    failed = {'by': 'schedule', 'kind': 'build', 'result': 'failed', 'outcome': {'error': 'the key was refused'}}
    assert _same_waiting_round(failed, dict(failed))
    assert not _same_waiting_round(failed, dict(failed, outcome={'error': 'something else'}))
    assert not _same_waiting_round(dict(failed, by='owner'), dict(failed, by='owner'))


def test_a_draft_nothing_can_check_does_not_hold_the_next_milestone(tmp_path, monkeypatch):
    # Journey J11-B11: Styles' draft had no checks and nothing to run, so its verification was "unchecked"; every build
    # checked it again and stopped there, and Runes light, whose checks were approved, never ran.
    from runesmith.app import building
    ws = setup(tmp_path, acceptance=True); enable(ws)
    first = building.ready_milestones(ws.plan())[0]
    second = dict(first, id='m-next', title='Next')
    monkeypatch.setattr(building, 'ready_milestones', lambda plan: [first, second])
    calls = []

    def fake_build(ws_, router, milestone, context, *, checkpoint, author_only):
        calls.append(milestone['id'])
        if milestone['id'] == first['id']:
            return {'summary': 'Draft “Styles” waits for you', 'milestone': first['id']}, 'a draft waits for you'
        return {'summary': 'Built', 'milestone': second['id'], 'advanced': True}, None
    monkeypatch.setattr(building, '_build_milestone', fake_build)
    assert building.build_step(ws, object())['milestone'] == second['id'] and calls == [first['id'], second['id']]


def test_an_unchecked_draft_that_has_not_changed_is_not_checked_again(tmp_path):
    from runesmith.app import building
    ws = setup(tmp_path, acceptance=True)
    milestone = building.ready_milestones(ws.plan())[0]
    context = building.source_context(ws)
    draft = {'id': 'd1', 'title': 'Styles', 'verification': {'status': 'unchecked', 'snapshot_digest': context['snapshot_digest'],
             'acceptance_bundle': {n: __import__('hashlib').sha256(d).hexdigest()
                                   for n, d in building._acceptance_files(ws, milestone['id']).items()}}}
    result = building._unchanged_verdict(ws, draft, milestone, 'c', context, lambda: None)
    assert result and result['unchanged'] and 'nothing can check it' in result['summary']


def test_a_saved_draft_whose_checks_now_fail_is_still_reported(tmp_path, monkeypatch):
    # Review of batch J: moving on past every non-advancing recheck hid a draft whose checks had just failed.
    from runesmith.app import building
    ws = setup(tmp_path, acceptance=True); enable(ws)
    milestone = building.ready_milestones(ws.plan())[0]
    context = building.source_context(ws)
    contract = building.milestone_contract(ws, milestone)
    pending = {'id': 'd1', 'state': 'waiting', 'contract': contract, 'snapshot_digest': context['snapshot_digest'],
               'context_digest': context['digest'], 'public_acceptance_digest': building.expectation_digest(ws, milestone['id'])}
    monkeypatch.setattr(ws, 'drafts', lambda: [pending])
    monkeypatch.setattr(building, '_unchanged_verdict', lambda *a, **k: None)
    for status, reason in (('failed', None), ('unchecked', 'a draft waits for you'), ('self_checks_passed', 'a draft waits for you')):
        monkeypatch.setattr(building, '_check_and_record', lambda *a, status=status, **k: {
            'draft': 'd1', 'milestone': milestone['id'], 'verification': {'status': status}, 'summary': status})
        _, got = building._build_milestone(ws, object(), milestone, context, checkpoint=lambda: None, author_only=False)
        assert got == reason, (status, got)


def test_failed_rounds_with_other_parameters_are_not_merged():
    from runesmith.app.worker import _same_waiting_round
    failed = {'by': 'schedule', 'kind': 'propose_acceptance', 'result': 'failed', 'params': {'milestone': 'm1'},
              'outcome': {'error': 'every model is busy'}}
    assert _same_waiting_round(failed, dict(failed))
    assert not _same_waiting_round(failed, dict(failed, params={'milestone': 'm2'}))


def test_an_edit_whose_old_text_only_escapes_its_quotes_is_matched():
    # Journey J11-G22: Nemotron wrote '<svg width=\"' for the file's '<svg width="', and the build was refused.
    import pytest
    from runesmith.app.planner import _apply_one_edit
    text = "let s = '<svg width=\"' + w + '\">';\nlet t = 1;\n"
    old = "let s = '<svg width=\\\"' + w + '\\\">';"
    new = "let s = '<svg class=\\\"rs\\\"';"
    assert '\\"' in old
    assert _apply_one_edit(text, {'old_text': old, 'new_text': new}, 'motion.mjs') == "let s = '<svg class=\"rs\"';\nlet t = 1;\n"
    with pytest.raises(ValueError):                  # not in a document (review: a README got a stray backslash)
        _apply_one_edit(text, {'old_text': old, 'new_text': new}, 'README.md')
    with pytest.raises(ValueError):                  # anything else still does not match
        _apply_one_edit(text, {'old_text': "let s = '<svg height=\\\"'", 'new_text': 'x'}, 'motion.mjs')
    # Review: a correctly quoted old text that occurs twice was redirected to the one place its unescaped form occurs.
    twice = "x = 'a=\\\"1\\\"'\nx = 'a=\\\"1\\\"'\n# a=\"1\"\n"
    with pytest.raises(ValueError):
        _apply_one_edit(twice, {'old_text': 'a=\\"1\\"', 'new_text': 'b'}, 'm.py')


def test_an_edit_whose_first_line_alone_is_indented_is_matched():
    # Journey J11-G26: Gemini indented only the first line of an old text whose first line the file has flush left.
    import pytest
    from runesmith.app.planner import _apply_one_edit
    text = "let s = 1;\nif (style === 'runes') {\n  s += 2;\n}\n"
    old = "  if (style === 'runes') {\n  s += 2;"
    new = "  if (style === 'runes') {\n  s += 3;"
    assert _apply_one_edit(text, {'old_text': old, 'new_text': new}, 'motion.mjs') == "let s = 1;\nif (style === 'runes') {\n  s += 3;\n}\n"
    with pytest.raises(ValueError):                  # a later line with other content still does not match
        _apply_one_edit(text, {'old_text': "  if (style === 'runes') {\n  s += 5;", 'new_text': new}, 'motion.mjs')
    with pytest.raises(ValueError):                  # not in a document (review)
        _apply_one_edit(text, {'old_text': old, 'new_text': new}, 'README.md')
    literal = 'HELP = """\nif (style === \'runes\') {\n  s += 2; keep"""\n'
    with pytest.raises(ValueError):                  # whole lines only: never a match ending mid-line (review)
        _apply_one_edit(literal, {'old_text': old, 'new_text': new}, 'help.py')
    twice = "if (a) {\n  b();\n}\n  if (a) {\n  b();\n}\n"
    with pytest.raises(ValueError):                  # two places: never a guess
        _apply_one_edit(twice + "x", {'old_text': "    if (a) {\n  b();", 'new_text': "    if (a) {\n  c();"}, 'm.js')


# The project's own tests are found where the draft put them (the newcomer path: an empty-folder draft kept its test in
# the folder root, and every check ended in "Start directory is not importable: 'tests'").
ROOT_TEST = 'import unittest\nfrom app import answer\nclass Tests(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(),42)\n'


def draft_with(tmp_path, files, *, acceptance=False):
    ws = Workspace(tmp_path)
    ws.save_plan({'summary':'Tiny calculation service', 'milestones':[{'title':'Answer', 'done_when':'answer() returns 42'}]})
    scripted(ws, [{'title':'Implementation', 'files':files}], roles=('plan',))
    if acceptance:
        path=ws.home/'acceptance'/'m1.py'
        path.parent.mkdir(parents=True)
        path.write_text('import unittest\nfrom app import answer\nclass Acceptance(unittest.TestCase):\n    def test_contract(self): self.assertEqual(answer(),42)\n')
    enable(ws)
    return ws


APP = {'path':'app.py','content':'def answer():\n    return 42\n'}


@pytest.mark.parametrize('layout,ran', [
    ([APP, {'path':'test_app.py','content':ROOT_TEST}], 1),
    ([APP, {'path':'tests/test_app.py','content':ROOT_TEST}], 1),
    ([APP, {'path':'tests/__init__.py','content':''}, {'path':'tests/test_app.py','content':ROOT_TEST}], 1),
    # tests/ is empty of tests: the top folder's test is found
    ([APP, {'path':'tests/__init__.py','content':''}, {'path':'test_app.py','content':ROOT_TEST}], 1)],
    ids=['root', 'tests-without-init', 'tests-with-init', 'empty-tests-folder'])
def test_project_tests_are_found_where_the_draft_put_them(tmp_path, layout, ran):
    ws = draft_with(tmp_path, layout, acceptance=True)
    result = build_step(ws, ws.router())
    checks = result['verification']['project_checks']
    assert checks['ok'] and checks['ran'] == ran, checks['output']
    assert 'not importable' not in checks['output']
    # The owner's acceptance runs behind the project checks, instead of never starting.
    assert result['verification']['status'] == 'acceptance_passed'
    assert result['verification']['acceptance']['ran'] == 1


def test_a_project_with_a_tests_folder_runs_what_it_always_ran_not_its_top_folder_scripts(tmp_path):
    # An existing project's top folder may hold a script named test_something.py that is not a unittest (it raises or
    # hangs when imported): its checks keep passing, as before the runner also looked in the top folder.
    ws = draft_with(tmp_path, [APP, {'path':'tests/__init__.py','content':''}, {'path':'tests/test_app.py','content':ROOT_TEST},
                               {'path':'test_connection.py','content':'raise RuntimeError("a script, not a test")\n'}], acceptance=True)
    result = build_step(ws, ws.router())
    checks = result['verification']['project_checks']
    assert checks['ok'] and checks['ran'] == 1 and 'a script, not a test' not in checks['output']
    assert result['verification']['status'] == 'acceptance_passed'


def test_a_failing_test_in_the_folder_root_is_reported_not_hidden(tmp_path):
    ws = draft_with(tmp_path, [{'path':'app.py','content':'def answer():\n    return 41\n'},
                               {'path':'test_app.py','content':ROOT_TEST}])
    checks = build_step(ws, ws.router())['verification']['project_checks']
    assert not checks['ok'] and checks['failures'] == 1 and checks['ran'] == 1


def test_a_root_test_that_cannot_be_imported_fails_its_check(tmp_path):
    ws = draft_with(tmp_path, [{'path':'app.py','content':'def answer():\n    return 42\n'},
                               {'path':'test_app.py','content':'import unittest\nfrom nothing_here import x\n'}])
    checks = build_step(ws, ws.router())['verification']['project_checks']
    assert not checks['ok'] and 'nothing_here' in checks['output']


def test_code_without_any_test_says_where_tests_belong(tmp_path):
    ws = draft_with(tmp_path, [{'path':'app.py','content':'def answer():\n    return 42\n'}])
    checks = build_step(ws, ws.router())['verification']['project_checks']
    assert not checks['ok'] and checks['ran'] == 0
    assert 'tests folder' in checks['output'] and 'test_*.py' in checks['output']


def test_the_author_is_told_where_the_tests_belong(tmp_path):
    from runesmith.app.planner import draft_prompt, source_context
    ws = draft_with(tmp_path, [APP])
    milestone = ws.plan()['milestones'][0]
    prompt = json.loads(draft_prompt(ws, milestone, source_context(ws, milestone=milestone)))
    rule = next(r for r in prompt['rules'] if 'unittest tests' in r)
    assert 'tests/ folder' in rule and 'tests/__init__.py' in rule and 'test_*.py' in rule
