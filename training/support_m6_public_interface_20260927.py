"""Prospective contract clarification, one instrument supplement, one new-candidate check.

The external trainer supplies public interface intent and bounded orchestration,
never Hat implementation. Each phase is explicit; interrupted phases are consumed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectations, expectation_digest, publish_expectations
from runesmith.app.author_recovery import pending_authors
from runesmith.app import building
from runesmith.app.inference_routes import route_view, save_route
from runesmith.app.planner import milestone_contract
from runesmith.app.revision_context import inspect_revision, save_selection, candidate_identity
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _read_json, _write_json, _now
from runesmith.config import build_router

ROOT = Path(__file__).resolve().parent / 'SupportHat'
HOME = ROOT / '.runesmith'
RECORD = HOME / 'trainer-trials/public-interface-m6-20260927.json'
PRIOR = 'd20260926170845e812'
SOURCE = '6ee90ff4e46a8d253c3e4e6fe2a3865db00e751a9d4fe5b9ade533dc2a5fbd6b'
OLD_PUBLIC = 'f977b0770ac0ca16803921e9ef8e5462f90fab1bc9b43f4812894ae7f8dd2d65'
ROUTES = ['gemini:gemini-3.1-flash-lite-preview', 'gemini3:gemini-3.1-flash-lite', 'gemini2:gemini-3.1-flash-lite']
INTERFACE = {'id':'record-handoff-response','invocation':'python -m supporthat --json record-handoff CASE_ID',
    'description':'On success, return a single JSON object for the requested case after the persisted increment. '
                  'Other response fields may remain. A missing case must still fail without a partial write.',
    'criterion_ids':['metrics.handoffs','metrics.local_only'],'response_type':'object','fields':[
        {'name':'case_id','type':'integer','required':True,'nullable':False,'unit':'',
         'description':'The requested existing case identifier.'},
        {'name':'handoffs','type':'integer','required':True,'nullable':False,'unit':'handoffs',
         'description':'Persisted cumulative handoff count for this case after the successful increment; not the global total.'}]}
TASK = ('A prospective public-contract clarification now declares the record-handoff JSON response. '
        'Revise the retained candidate to conform to that declaration and add a regression in the selected project tests. '
        'Keep existing metric behavior, status/error handling, local-only boundaries and unrelated candidate bytes. '
        'Read the displayed metrics implementation and the selected command before editing. '
        'Return exact edits only to displayed candidate units. This is a newly clarified interface, not evidence '
        'that the original author ignored a previously stated field. No private fixture source or examples are provided.')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def public_packet(prompt):
    # draft_prompt deliberately appends readable operator notes after its JSON.
    packet, _ = json.JSONDecoder().raw_decode(prompt.lstrip())
    if not isinstance(packet, dict): raise RuntimeError('Draft packet must begin with a JSON object')
    return packet


def audit(ws):
    return {'source':collect_snapshot(ws)['digest'],'resident':bool(_existing(ws.home)),
            'current':(ws.home/'STUDIO_CURRENT.json').exists(),'pending':len(pending_authors(ws)),
            'manual':ws.manual_waiting(),'auto_work':ws.settings()['auto_work'],'kaizen':ws.settings()['kaizen']}


def checkpoint(ws, record):
    state = audit(ws)
    if state != {'source':SOURCE,'resident':False,'current':False,'pending':0,'manual':0,'auto_work':False,'kaizen':False}:
        raise RuntimeError('Home no longer matches the bounded single-writer state: '+str(state))
    if any(not Path(p).is_file() or sha(Path(p))!=value for p,value in record['protected_sha256'].items()):
        raise RuntimeError('Protected source-of-record changed')
    if expectation_digest(ws,'m6') != record['public_digest']:
        raise RuntimeError('Public contract changed')
    if sha(HOME/'runesmith.json') != record['config_sha256']:
        raise RuntimeError('Configured instrument changed')
    if sha(HOME/'PLAN.json') != record['plan_sha256']:
        raise RuntimeError('Plan changed')
    if not building.status(ws)['enabled']:
        raise RuntimeError('Build checks are no longer authorized')


def prepare(ws):
    if RECORD.exists(): raise RuntimeError('Preparation already recorded; inspect, never recreate')
    prior = ws._draft(PRIOR)
    if audit(ws) != {'source':SOURCE,'resident':False,'current':False,'pending':0,'manual':0,'auto_work':False,'kaizen':False}:
        raise RuntimeError('Home has changed or unresolved work')
    if prior['state']!='needs_revision' or prior.get('verification',{}).get('status')!='failed':
        raise RuntimeError('Prior failed result changed')
    old = expectations(ws,'m6')
    if old['digest']!=OLD_PUBLIC or building.supplement_status(ws,prior)['used']:
        raise RuntimeError('Old contract or one-supplement eligibility changed')
    protected = [p for p in (HOME/'acceptance').rglob('*') if p.is_file()]
    for folder in ('build-attempts','build-check-resumes','build-check-allocations','build-check-reconciliations'):
        protected.extend((HOME/folder).glob('*.json'))
    protected.extend((HOME/'build-runs').glob('*/v-*/VERIFICATION.json'))
    protected.extend([HOME/'acceptance-contracts/history/m6/1.json',HOME/'BUILD_GRANT.json',HOME/'drafts'/f'{PRIOR}.json'])
    record = {'state':'preparing','utc':_now(),'prior_draft':PRIOR,'prior_public_digest':OLD_PUBLIC,
        'source_digest':SOURCE,'prior_candidate_digest':candidate_identity(prior),
        'gateway_job_limit':1,'router_retry':False,'paid_fallback':False,'max_output_tokens':4000,
        'prompt_ceiling_bytes':66000,'new_candidate_check_limit':1,'project_timeout_s':360,'owner_timeout_s':240,
        'resource_reason':'New candidate, not a retry of the spent replacement. Preserve the prior 360/240s ceilings; '
                          'the prior complete phases used163.027/48.818s. No adaptive extension or automatic apply.',
        'trainer_assistance':'Trainer versions the missing public output requirement, selects existing candidate units '
                             'and commissions one instrument correction. No trainer-authored Hat implementation or test.',
        'scope':'Operational development, not scientific confirmation or autonomous target selection.',
        'stop_rule':'One returned/refused/unresolved author result. At most one separately invoked full check of its admitted candidate; '
                    'stop on any failure, uncertainty or timeout. Apply is a separate guarded action after review.',
        'protected_sha256':{str(p):sha(p) for p in protected if p.is_file()},
        'plan_sha256':sha(HOME/'PLAN.json')}
    _write_json(RECORD,record)
    public = publish_expectations(ws,'m6',old['criteria'],
        'Prospective response-interface clarification after the retained candidate failed on an output member not '
        'specified in contractv1. Preserve the original FAIL and private fixture bytes. No behavioral relaxation.',
        by='external-trainer',interfaces=[INTERFACE],expected_digest=OLD_PUBLIC)
    view = route_view(ws,'free-author')
    save_route(ws,'free-author',revision=view['revision'],model=ROUTES[0],fallback_models=ROUTES[1:],
        reason='One narrowly scoped clarified-interface revision using known configured Gemini routes only; no paid or credit-backed fallback.')
    info = inspect_revision(ws,PRIOR)
    if info['blockers']: raise RuntimeError(str(info['blockers']))
    command = next(u for u in info['units'] if u['path']=='supporthat/cli.py' and u['label']=='cmd_record_handoff')
    selected = save_selection(ws,PRIOR,version=info['version'],selections=[
        {'path':'supporthat/cli.py','unit':command['unit']},
        {'path':'supporthat/metrics.py','unit':'*'},
        {'path':'tests/test_metrics.py','unit':'*'}],reason='Show the command, its actual count implementation and candidate project tests; preserve all other bytes.')
    note = ws.add_note('draft',PRIOR,TASK,'m6 public JSON response clarification')
    info = inspect_revision(ws,PRIOR);prompt=info['preview']['prompt']
    if info['blockers'] or TASK not in prompt or len(prompt.encode())>record['prompt_ceiling_bytes']:
        raise RuntimeError('Complete bounded task was not delivered in the preview')
    record.update(state='prepared',public_digest=public['digest'],public_version=public['version'],note=note['id'],
        config_sha256=sha(HOME/'runesmith.json'),configured_routes=ROUTES,selection=selected['view']['selections'],
        preview_bytes=len(prompt.encode()),preview_sha256=hashlib.sha256(prompt.encode()).hexdigest())
    checkpoint(ws,record);_write_json(RECORD,record)
    ws.ledger.append('trainer.public_interface_prepared',{k:v for k,v in record.items() if k!='protected_sha256'})


def author(ws, record):
    if record['state']!='prepared': raise RuntimeError('Author allocation already consumed or not prepared')
    checkpoint(ws,record)
    preview = inspect_revision(ws, PRIOR)
    prompt = (preview.get('preview') or {}).get('prompt') or ''
    if (preview['blockers'] or TASK not in prompt or len(prompt.encode())>66000
            or public_packet(prompt)['public_acceptance']['interfaces'] != [INTERFACE]):
        raise RuntimeError('Validate the complete prospective packet before reserving any author allocation')
    spec=ws.config()['instruments']['free-author']
    if [spec['model']]+spec.get('fallback_models',[])!=ROUTES: raise RuntimeError('Routes changed')
    calls=[]
    router=build_router({'instruments':{'free-author':spec},'roles':{'plan':['free-author']}},
        home=HOME,on_call=lambda event:(calls.append(event),ws.record_call(event)),backoff_s=())
    class Once:
        used=False
        def call(self,role,**kwargs):
            prompt=kwargs['prompt'];packet=public_packet(prompt)
            if self.used or TASK not in prompt or len(prompt.encode())>66000 or kwargs['max_tokens']>4000:
                raise RuntimeError('Actual prompt or call bound exceeded')
            if packet['public_acceptance']['interfaces'] != [INTERFACE]: raise RuntimeError('Interface not delivered')
            self.used=True
            record.update(state='submitted',request_key=kwargs['key'],prompt_bytes_actual=len(prompt.encode()),
                actual_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),complete_task_delivered=True)
            _write_json(RECORD,record)
            print(json.dumps({'state':'submitted','prompt_bytes':record['prompt_bytes_actual'],'paid_fallback':False}),flush=True)
            return router.call(role,**kwargs)
    record.update(state='author_started',author_started=_now());_write_json(RECORD,record)
    try:
        result=building.supplement_build(ws,Once(),PRIOR,
            'One external-trainer-authorized instrument correction to prospectively clarified response contractv2. '
            'Old FAIL/budgets remain; save for review only.',author_only=True,checkpoint=lambda:checkpoint(ws,record))
        draft=ws._draft(result['draft']);old=ws._draft(PRIOR)
        changed=[f['path'] for f in draft['files'] if f['content']!=next(o['content'] for o in old['files'] if o['path']==f['path'])]
        record.update(state='admitted',draft=draft['id'],authored_by=draft.get('drafted_by'),changed_files=changed,
            candidate_digest=candidate_identity(draft))
    except Exception as error:
        record.update(state='refused_or_unresolved',error=type(error).__name__+': '+str(error)[:500],
                      remote_receipt=getattr(error,'remote_receipt',{}))
    record.update(author_finished=_now(),calls=calls,source_unchanged=collect_snapshot(ws)['digest']==SOURCE,
        protected_unchanged=all(Path(p).is_file() and sha(Path(p))==v for p,v in record['protected_sha256'].items()))
    _write_json(RECORD,record);ws.ledger.append('trainer.public_interface_author',{k:v for k,v in record.items() if k!='protected_sha256'})


def check(ws,record,*,record_path=RECORD):
    if record['state']!='admitted': raise RuntimeError('Check allocation unavailable/consumed')
    checkpoint(ws,record);draft=ws._draft(record['draft'])
    if candidate_identity(draft)!=record['candidate_digest'] or draft.get('verification'):
        raise RuntimeError('Candidate changed or already checked')
    record.update(state='check_started',check_started=_now());_write_json(record_path,record)
    ws.ledger.append('trainer.public_interface_check_reserved',{'draft':draft['id'],'project_limit_s':360,'owner_limit_s':240,'apply':False})
    milestone=next(m for m in ws.plan()['milestones'] if m['id']=='m6')
    result=building._check_and_record(ws,draft,milestone,milestone_contract(ws,milestone),
        checkpoint=lambda:checkpoint(ws,record),phase_checkpoint=lambda:checkpoint(ws,record),
        allow_apply=False,project_timeout_s=360,owner_timeout_s=240)
    record.update(state='checked',check_finished=_now(),check_result=result)
    checkpoint(ws,record);_write_json(record_path,record)


def apply(ws,record,*,record_path=RECORD):
    if record['state']!='checked' or record['check_result']['verification']['status']!='acceptance_passed':
        raise RuntimeError('No checked passing candidate available for application')
    checkpoint(ws,record);draft=ws._draft(record['draft'])
    if candidate_identity(draft)!=record['candidate_digest']: raise RuntimeError('Candidate changed')
    milestone=next(m for m in ws.plan()['milestones'] if m['id']=='m6')
    record.update(state='apply_started',apply_started=_now());_write_json(record_path,record)
    result={'advanced':False,'summary':'Existing grant did not permit application.'}
    with ws._lock:
        building._apply_if_current(ws,draft,milestone,milestone_contract(ws,milestone),building.status(ws),
            record['check_result']['verification'],result)
    record.update(state='applied' if result.get('advanced') else 'apply_refused',apply_result=result,finished=_now(),
        resulting_source_digest=collect_snapshot(ws)['digest'],
        protected_unchanged=all(Path(p).is_file() and sha(Path(p))==v for p,v in record['protected_sha256'].items()))
    _write_json(record_path,record);ws.ledger.append('trainer.public_interface_apply',{'draft':draft['id'],**result})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','prepare','author','check','apply'],default='inspect',nargs='?')
    args=parser.parse_args()
    if _existing(HOME): raise RuntimeError('Use the resident Studio API, not a direct writer')
    lock=InstanceLock(HOME)
    if not lock.acquire(): raise RuntimeError('Another writer owns this home')
    try:
        if args.action=='inspect':
            ws=object.__new__(Workspace);ws.root,ws.home=ROOT,HOME
            print(json.dumps({'audit':audit(ws),'record':_read_json(RECORD,{})},ensure_ascii=True));return
        ws=Workspace(ROOT,HOME)
        if args.action=='prepare':prepare(ws)
        else:globals()[args.action](ws,_read_json(RECORD,{}))
        record=_read_json(RECORD,{})
        print(json.dumps({k:v for k,v in record.items() if k not in ('protected_sha256','check_result')},ensure_ascii=True),flush=True)
        if record.get('check_result'):
            v=record['check_result']['verification']
            print(json.dumps({'status':v['status'],'evidence_dir':v.get('evidence_dir'),
                'phases':{n:{k:(v.get(n)or{}).get(k) for k in ('status','ran','errors','failures','elapsed_s','limit_s')}
                          for n in ('project_checks','acceptance')}}),flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
