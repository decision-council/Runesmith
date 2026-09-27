"""One free-route author job, prompted by recorded semantic review, never trainer Hat code."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.inference_routes import route_view, save_route
from runesmith.app.planner import draft_files, draft_prompt, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json


def main():
    root=Path(__file__).resolve().parent/'GrowthHat';home=root/'.runesmith'
    if _existing(home):raise RuntimeError('Resident Studio found; use its queue')
    lock=InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns this home')
    try:
        ws=Workspace(root,home);path=home/'trainer-trials/gemini-m5-export-lifetime-revision-20260926.json'
        if path.exists():
            print(json.dumps({'already_started':True,'state':_read_json(path,{}).get('state','unknown')}));return
        if pending_authors(ws):raise RuntimeError('Reconcile pending author first')
        prior=ws._draft('d202609262025386e60')
        if prior['state']!='waiting' or prior.get('verification'):raise RuntimeError('Retained candidate changed')
        snapshot=collect_snapshot(ws)
        if snapshot['digest']!='4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5':raise RuntimeError('Source changed')
        if expectation_digest(ws,'m5')!='5cd2c483da619a4cc34cc720209a91affdef20429b66372d43d1c28209e79cb3':raise RuntimeError('Criteria changed')
        protected=list((home/'acceptance').glob('*.py'))+list((home/'build-runs').glob('*/v-*/VERIFICATION.json'))
        hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        note=ws.notes.add(target_type='draft',target_id=prior['id'],target_label=prior['title'],author='external-trainer',
            text='Trainer review 2026-09-26: export resource lifetime. The newest retained Opus candidate fixes '
            'the no-clobber race (trainer controlled-function probe confirms return1 and competitor bytes preserved). '
            'However export_recommendations(repo) can raise after os.open and before fdopen/try, leaving an open '
            'descriptor and empty destination. The probe observed1 leaked descriptor. Correct resource lifetime '
            'without losing atomic no-clobber semantics or deleting another process\'s destination on cleanup. '
            'Keep the change narrow and retain other files. The newly added race test precreates a file before '
            'calling main; it also passes the old buggy implementation. Replace it with a discriminating test '
            'that creates a competitor immediately before the actual file-open operation; also cover export-data '
            'failure with no leaked descriptor/empty destination. These are project regressions, not edits to '
            'the fixed private owner checks. No source has been applied. Do not change public criteria or docs.')
        ws.ledger.append('trainer.semantic_review',{'draft':prior['id'],'note':note['id'],
            'scope':'controlled unchanged-function probe; not full acceptance', 'inference_calls':0})
        before=route_view(ws,'author')
        route=save_route(ws,'author',revision=before['revision'],model='gemini3:gemini-3.1-flash-lite',
            fallback_models=['gemini2:gemini-3.1-flash-lite','gemini:gemini-3.1-flash-lite-preview'],
            reason='External trainer switches Growth author to the three user-authorized Gemini free-catalog routes. '
                   'Shared OpenRouter credit observed$0.119965842at20:33:11 is below the preceding$0.206825 '
                   'same-sized request. Catalog GETs returned200; author quality/quota not inferred. '
                   'Paid-opus45 instrument retained; no other home, role, key, endpoint or budget tag changes.')
        ws._save_draft_state(prior,'needs_revision',review_requested_by='external-trainer',review_note=note['id'],
                            review_reason='Export-data failure leaves a descriptor and empty destination')
        prior=ws._draft(prior['id']); milestone=next(m for m in ws.plan()['milestones'] if m['id']=='m5')
        prompt=draft_prompt(ws,milestone,source_context(ws),revision=prior)
        if 'Trainer review 2026-09-26: export resource lifetime' not in prompt:raise RuntimeError('Latest review absent from prompt')
        receipt={'state':'started','utc':_now(),'prior_draft':prior['id'],'milestone':'m5','review_note':note['id'],
            'model':route['model'],'fallback_models':route['fallback_models'],'gateway_job_limit':1,
            'router_retry':False,'gateway_fallback_limit':2,'max_output_tokens':4000,'apply':False,
            'route_before':{k:before[k] for k in ('revision','model','fallback_models')},'route_after':route,
            'source_digest':snapshot['digest'],'public_acceptance_digest':expectation_digest(ws,'m5'),
            'protected_sha256':hashes,'prompt_bytes_preflight':len(prompt.encode()),
            'trainer_assistance':'Fault injection, semantic feedback and explicit free-route selection; instrument authors all code.'}
        _write_json(path,receipt)
        events=[]
        def record(event):events.append(event);ws.record_call(event)
        router=ws.router(on_call=record,backoff_s=())
        print(json.dumps({'state':'starting','model':route['model'],'gateway_job_limit':1,'prompt_bytes':receipt['prompt_bytes_preflight']}),flush=True)
        try:
            draft=draft_files(ws,router,'m5',revision=prior)
            receipt.update(state='admitted',draft=draft['id'],authored_by=draft.get('drafted_by'),paths=[f['path'] for f in draft['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved',error=type(error).__name__+': '+str(error)[:500],remote_receipt=getattr(error,'remote_receipt',{}))
        receipt.update(finished=_now(),calls=events,source_unchanged=collect_snapshot(ws)['digest']==snapshot['digest'],
            protected_unchanged=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p)] for p in protected))
        _write_json(path,receipt);ws.ledger.append('trainer.free_semantic_revision',receipt)
        print(json.dumps({k:v for k,v in receipt.items() if k!='protected_sha256'}),flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
