"""One explicitly commissioned instrument revision after trainer semantic review."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, draft_prompt, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from runesmith.config import build_instrument
from runesmith.instruments import Router


def main():
    credit = float(sys.argv[1])
    if credit < 0.30: raise RuntimeError('Insufficient observed credit for this bounded paid revision')
    root = Path(__file__).resolve().parent/'GrowthHat'; home = root/'.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home); path = home/'trainer-trials/opus-m5-export-race-revision-20260926.json'
        if path.exists():
            print(json.dumps({'already_started':True,'state':_read_json(path,{}).get('state','unknown')})); return
        if pending_authors(ws): raise RuntimeError('Reconcile pending author first')
        draft = ws._draft('d202609261957066ca2')
        if draft['state'] != 'waiting' or draft.get('verification',{}).get('status') != 'acceptance_passed':
            raise RuntimeError('Reviewed passing candidate changed')
        snapshot = collect_snapshot(ws)
        if snapshot['digest'] != '4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5':
            raise RuntimeError('Source changed')
        if expectation_digest(ws,'m5') != '5cd2c483da619a4cc34cc720209a91affdef20429b66372d43d1c28209e79cb3':
            raise RuntimeError('Public criteria changed')
        milestone = next(m for m in ws.plan()['milestones'] if m['id']=='m5')
        context = source_context(ws)
        prompt = draft_prompt(ws,milestone,context,revision=draft)
        if 'Trainer review 2026-09-26: export no-clobber race' not in prompt:
            raise RuntimeError('Review note is missing from the actual author context')
        protected = [home/draft['verification']['evidence_dir']/'VERIFICATION.json', *(home/'acceptance').glob('*.py')]
        hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        name='paid-opus45'; instrument=build_instrument(name,ws.config()['instruments'][name],home)
        receipt={'state':'started','utc':_now(),'prior_draft':draft['id'],'milestone':'m5',
            'review_note':'23360000e8d4','requested_model':instrument.model,'inference_limit':1,
            'max_output_tokens':4000,'automatic_retry':False,'fallback':False,'apply':False,
            'observed_shared_credit_before_usd':credit,'credit_observation_utc':sys.argv[2],
            'source_digest':snapshot['digest'],'public_acceptance_digest':expectation_digest(ws,'m5'),
            'protected_sha256':hashes,'prompt_bytes_preflight':len(prompt.encode()),
            'trainer_assistance':'Identified export race; explicitly requested a narrow model-authored revision. '
                                 'Passing check verdict and earlier attempt budgets remain intact.'}
        _write_json(path,receipt)
        ws._save_draft_state(draft,'needs_revision',review_requested_by='external-trainer',
                            review_note='23360000e8d4',review_reason='Atomic no-clobber semantics not covered by ordinary existing-file check')
        ws.ledger.append('trainer.semantic_revision_requested',{'draft':draft['id'],'note':'23360000e8d4',
            'verification_preserved':draft['verification']['evidence_dir'],'one_call':True})
        draft=ws._draft(draft['id'])
        events=[]
        def record(event):events.append(event);ws.record_call(event)
        router=Router({name:instrument},{'plan':[name]},backoff_s=(),on_call=record)
        print(json.dumps({'state':'starting','model':instrument.model,'max_output_tokens':4000,'prompt_bytes':receipt['prompt_bytes_preflight']}),flush=True)
        try:
            new=draft_files(ws,router,'m5',revision=draft)
            receipt.update(state='admitted',draft=new['id'],authored_by=new.get('drafted_by'),
                           paths=[f['path'] for f in new['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved',error=type(error).__name__+': '+str(error)[:500],
                           remote_receipt=getattr(error,'remote_receipt',{}))
        receipt.update(finished=_now(),calls=events,source_unchanged=collect_snapshot(ws)['digest']==snapshot['digest'],
            protected_unchanged=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p)] for p in protected))
        _write_json(path,receipt);ws.ledger.append('trainer.semantic_revision_result',receipt)
        print(json.dumps({k:v for k,v in receipt.items() if k!='protected_sha256'}),flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
