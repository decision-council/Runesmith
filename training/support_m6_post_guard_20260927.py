"""One separately authorized field allocation after a proven local no-dispatch error.

Does not reopen the failed supplement or add a product retry entitlement.
Hat edits remain instrument-authored, with unchanged normal admission/evaluation.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import support_m6_public_interface_20260927 as base
from runesmith.app.planner import draft_files
from runesmith.app.revision_context import inspect_revision, candidate_identity
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _read_json, _write_json, _now
from runesmith.config import build_router

RECORD = base.HOME/'trainer-trials/public-interface-m6-postguard-20260927.json'
CHECK_RECORD = base.HOME/'trainer-trials/public-interface-m6-hookfix-check-20260927.json'
FAILED_SUPPLEMENT = base.HOME/'build-supplements/scc1d47957233.json'
UNSENT_KEY = 'draft-m6-1790468640185935800'


def validate_no_dispatch(old, supplement, requests):
    if (old.get('state')!='refused_or_unresolved' or old.get('calls') != [] or old.get('request_key')
            or old.get('remote_receipt') or not old.get('error','').startswith('JSONDecodeError: Extra data:')):
        raise RuntimeError('Old allocation is not the reviewed local pre-submission failure')
    if (supplement.get('state')!='failed' or supplement.get('id')!='scc1d47957233'
            or supplement.get('error')!='Extra data: line 531 column 1 (char 41558)'):
        raise RuntimeError('Original supplement evidence changed')
    # The Milliner journal persists before POST. Any matching journal, even a
    # refused/uncertain one, defeats this narrow no-dispatch adjudication.
    if any(not isinstance(r,dict) or r.get('body',{}).get('idempotency_key')==UNSENT_KEY for r in requests):
        raise RuntimeError('A matching or damaged transport receipt requires reconciliation, not a new call')


def author(ws):
    if RECORD.exists(): raise RuntimeError('This external allocation already exists; do not repeat it')
    old=_read_json(base.RECORD,{})
    requests=[_read_json(p,None) for p in (base.HOME/'inference-requests').glob('*.json')]
    validate_no_dispatch(old,_read_json(FAILED_SUPPLEMENT,{}),requests)
    base.checkpoint(ws,old)
    prior=ws._draft(base.PRIOR)
    if candidate_identity(prior)!=old['prior_candidate_digest'] or prior['state']!='needs_revision':
        raise RuntimeError('Retained candidate changed')
    info=inspect_revision(ws,base.PRIOR);prompt=(info.get('preview')or{}).get('prompt') or ''
    if (info['blockers'] or base.TASK not in prompt or len(prompt.encode())>66000
            or base.public_packet(prompt)['public_acceptance']['interfaces']!=[base.INTERFACE]
            or info['view']['selections']!=old['selection']):
        raise RuntimeError('Prospective packet is not the reviewed bounded task')
    spec=ws.config()['instruments']['free-author']
    if [spec['model']]+spec.get('fallback_models',[])!=base.ROUTES: raise RuntimeError('Free-only route changed')
    record={k:copy.deepcopy(old[k]) for k in ('prior_draft','prior_public_digest','source_digest',
        'prior_candidate_digest','public_digest','public_version','note','config_sha256','plan_sha256',
        'selection','protected_sha256','gateway_job_limit','router_retry','paid_fallback','max_output_tokens',
        'prompt_ceiling_bytes','new_candidate_check_limit','project_timeout_s','owner_timeout_s','resource_reason')}
    record['protected_sha256'].update({str(p):base.sha(p) for p in (base.RECORD,FAILED_SUPPLEMENT,
        base.HOME/'trainer-trials/public-interface-m6-preflight-assessment-20260927.json')})
    record.update(state='author_reserved',utc=_now(),allocation_kind='external_trainer_postguard',
        prior_allocation=str(base.RECORD),failed_supplement='scc1d47957233',prior_dispatches=0,
        authorization='2026-09-27T00:32:52Z heartbeat continues authorized field work. External trainer explicitly '
                      'commissions one new free-only correction after reviewing the proven local no-dispatch exception. '
                      'The product supplement stays consumed; no old receipt, predicate or grant is reset.',
        trainer_assistance=old['trainer_assistance']+' Trainer also corrected and qualified the failed prompt preflight guard.',
        configured_routes=base.ROUTES,preview_bytes=len(prompt.encode()),
        stop_rule='One outer router call without retry. Save then review; at most one separately invoked 360/240s check. '
                  'Stop on failure, timeout or uncertainty. Guarded application is a separate action.',
        scope='Operational development; no autonomous targeting or scientific confirmation claim.')
    _write_json(RECORD,record);ws.ledger.append('trainer.postguard_author_authorized',{k:v for k,v in record.items() if k!='protected_sha256'})
    calls=[]
    router=build_router({'instruments':{'free-author':spec},'roles':{'plan':['free-author']}},home=base.HOME,
        on_call=lambda event:(calls.append(event),ws.record_call(event)),backoff_s=())
    class Once:
        used=False
        def call(self,role,**kwargs):
            sent=kwargs['prompt'];packet=base.public_packet(sent)
            if (self.used or base.TASK not in sent or len(sent.encode())>66000 or kwargs['max_tokens']>4000
                    or packet['public_acceptance']['interfaces']!=[base.INTERFACE]):
                raise RuntimeError('Actual dispatch guard failed')
            self.used=True
            record.update(state='submitted',submitted=_now(),request_key=kwargs['key'],prompt_bytes_actual=len(sent.encode()))
            _write_json(RECORD,record)
            print(json.dumps({'state':'submitted','request_key':kwargs['key'],'prompt_bytes':len(sent.encode()),'paid_fallback':False}),flush=True)
            return router.call(role,**kwargs)
    try:
        draft=draft_files(ws,Once(),'m6',revision=prior)
        changed=[f['path'] for f in draft['files'] if f['content']!=next(o['content'] for o in prior['files'] if o['path']==f['path'])]
        record.update(state='admitted',draft=draft['id'],authored_by=draft.get('drafted_by'),changed_files=changed,
                      candidate_digest=candidate_identity(draft))
    except Exception as error:
        record.update(state='refused_or_unresolved',error=type(error).__name__+': '+str(error)[:500],remote_receipt=getattr(error,'remote_receipt',{}))
    record.update(author_finished=_now(),calls=calls,source_unchanged=collect_snapshot(ws)['digest']==base.SOURCE,
        protected_unchanged=all(Path(p).is_file() and base.sha(Path(p))==s for p,s in record['protected_sha256'].items()))
    _write_json(RECORD,record);ws.ledger.append('trainer.postguard_author_result',{k:v for k,v in record.items() if k!='protected_sha256'})


def check_after_hook_fix(ws):
    if CHECK_RECORD.exists(): raise RuntimeError('Linked external check allocation is consumed; never replay it')
    old=_read_json(RECORD,{})
    if (old.get('state')!='check_started' or old.get('draft')!='d202609270035308828'
            or old.get('check_started')!='2026-09-27T00:36:00Z'):
        raise RuntimeError('Not the specifically observed trainer callback failure')
    base.checkpoint(ws,old)
    draft=ws._draft(old['draft'])
    if draft.get('verification') or candidate_identity(draft)!=old['candidate_digest']:
        raise RuntimeError('Candidate changed or already evaluated')
    folder=base.HOME/'build-runs'/draft['id']
    runs=sorted(folder.iterdir())
    if len(runs)!=1 or runs[0].name!='v-33028c786de9' or any(runs[0].iterdir()):
        raise RuntimeError('Observed pre-phase run inventory changed; no new allocation')
    # This is a trainer attestation based on the observed traceback and reproduced
    # call path BEFORE _run_checks, not an inference from an empty directory alone.
    record=copy.deepcopy(old)
    record.update(state='admitted',utc=_now(),allocation_kind='external_trainer_check_after_local_hook_fix',
        parent_check_allocation=str(RECORD),parent_check_sha256=base.sha(RECORD),
        observed_local_error="TypeError: check.<locals>.<lambda>() missing 1 required positional argument: 'phase'",
        attestation='Observed00:36 traceback entered the zero-argument phase_checkpoint() before _run_checks. '
                    'A new isolated end-to-end wrapper test reproduced that exact error. After fixing the signature, '
                    'the test passed real tiny project/owner phases and separate guarded apply. The empty prior '
                    'run directory supports, but does not alone establish, non-execution.',
        authorization='External trainer explicitly allocates one new evaluation of the unchanged admitted candidate '
                      'after its own local pre-phase failure. Same360/240s ceilings. Original check-started journal '
                      'and failure evidence stay immutable; this is not an automatic entitlement or a scientific trial.',
        calls=[],inherited_author_calls=old['calls'],new_inference_calls=0,
        stop_rule='One check only, no inference, no automatic apply, no further callback-recovery chain.')
    record.pop('check_started')
    record['protected_sha256'].update({str(RECORD):base.sha(RECORD),
        str(base.HOME/'drafts'/base.PRIOR/'DRAFT.json'):base.sha(base.HOME/'drafts'/base.PRIOR/'DRAFT.json')})
    _write_json(CHECK_RECORD,record)
    ws.ledger.append('trainer.callback_failure_check_authorized',{k:v for k,v in record.items() if k not in ('protected_sha256','inherited_author_calls')})
    base.check(ws,record,record_path=CHECK_RECORD)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['author','check','check-after-hook-fix','apply']);args=parser.parse_args()
    if _existing(base.HOME): raise RuntimeError('Use the resident Studio queue')
    lock=InstanceLock(base.HOME)
    if not lock.acquire(): raise RuntimeError('Another writer owns this home')
    try:
        ws=Workspace(base.ROOT,base.HOME)
        path=CHECK_RECORD if args.action=='check-after-hook-fix' or (args.action=='apply' and CHECK_RECORD.exists()) else RECORD
        if args.action=='author': author(ws)
        elif args.action=='check-after-hook-fix':check_after_hook_fix(ws)
        else: getattr(base,args.action)(ws,_read_json(path,{}),record_path=path)
        record=_read_json(path,{})
        print(json.dumps({k:v for k,v in record.items() if k not in ('protected_sha256','check_result')},ensure_ascii=True),flush=True)
        if record.get('check_result'):
            v=record['check_result']['verification']
            print(json.dumps({'status':v['status'],'evidence_dir':v.get('evidence_dir'),
                'phases':{n:{k:(v.get(n)or{}).get(k) for k in ('status','ran','errors','failures','elapsed_s','limit_s')}
                          for n in ('project_checks','acceptance')}}),flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
