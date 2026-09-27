"""One explicit alternate free author, after Pixel's terminal transport timeout."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from runesmith.config import build_instrument
from runesmith.instruments import Router


def main():
    root=Path(__file__).resolve().parent/'GrowthHat';home=root/'.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio found; use its queue')
    lock=InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Another writer owns the home')
    try:
        ws=Workspace(root,home)
        path=home/'trainer-trials/cline-gemini-m5-20260926.json'
        if path.exists():
            print(json.dumps({'existing_trial':_read_json(path,{}),'no_inference':True}));return
        previous=_read_json(home/'trainer-trials/cline-pixel-m5-20260926.json',{})
        remote=previous.get('remote_receipt') or {}
        if previous.get('state')!='refused_or_unresolved' or remote.get('remote_state')!='terminal':
            raise RuntimeError('Previous author is not terminal; do not create another call')
        if pending_authors(ws): raise RuntimeError('Pending author requires reconciliation')
        before=source_context(ws)['snapshot_digest']
        if before!=previous['source_digest'] or expectation_digest(ws,'m5')!=previous['public_acceptance_digest']:
            raise RuntimeError('Source or public criteria changed; review before continuing')
        if any(d.get('milestone')=='m5' and d.get('state') in ('waiting','applied') for d in ws.drafts()):
            raise RuntimeError('m5 already has a candidate')
        old=ws.config()['instruments']['author'];original=build_instrument('author',old,home)
        name='free-cline-gemini'
        ws.save_instrument(name,{'kind':'milliner','preset':'milliner',
            'model':'cline:cline-free/gemini-3.8-flash','base_url':old['base_url'],
            'timeout_s':300,'fallback_models':[],'budget_tag':'runesmith-field-training',
            'caller_tag':'runesmith/trainer/growth-m5-cline-gemini',
            'note':'Explicit alternative after terminal Pixel timeout; no paid fallback or primary role change.'},
            key_value=original._token(),roles=[])
        instrument=build_instrument(name,ws.config()['instruments'][name],home)
        events=[]
        def record(event): events.append(event);ws.record_call(event)
        router=Router({name:instrument},{'plan':[name]},backoff_s=(),on_call=record)
        receipt={'state':'started','utc':_now(),'milestone':'m5','requested_model':instrument.model,
            'source_digest':before,'public_acceptance_digest':expectation_digest(ws,'m5'),
            'author_limit':1,'paid_fallback':False,'predecessor_job':remote.get('job_id'),
            'reason':'Explicit alternate free instrument after terminal transport failure; unchanged task/criteria.'}
        _write_json(path,receipt)
        try:
            draft=draft_files(ws,router,'m5')
            receipt.update(state='admitted',draft=draft['id'],authored_by=draft.get('drafted_by'),
                paths=[f['path'] for f in draft['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved',error=type(error).__name__+': '+str(error)[:500],
                remote_receipt=getattr(error,'remote_receipt',{}))
        receipt.update(finished=_now(),calls=events,source_unchanged=source_context(ws)['snapshot_digest']==before)
        _write_json(path,receipt);ws.ledger.append('trainer.author_trial',receipt)
        print(json.dumps(receipt,ensure_ascii=True))
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
