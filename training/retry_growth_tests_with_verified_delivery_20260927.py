"""New one-call allocation after fixing undelivered feedback, never replay old job."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files
from runesmith.app.revision_context import inspect_revision
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _read_json, _write_json, _now
from revise_growth_m5_focused_units_20260926 import ROUTES


def main():
    root=Path(__file__).resolve().parent/'GrowthHat';home=root/'.runesmith'
    if _existing(home):raise RuntimeError('Use the resident Studio queue')
    lock=InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Home has another writer')
    try:
        out=home/'trainer-trials/gemini-m5-tests-delivered-20260927.json'
        if out.exists():
            print(json.dumps({'already_started':True,'state':_read_json(out,{}).get('state')}));return
        prior_log=_read_json(home/'trainer-trials/gemini-m5-tests-only-20260927.json',{})
        if len(prior_log.get('calls',[]))!=1 or prior_log['calls'][0].get('remote_state')!='terminal':
            raise RuntimeError('Old request not proven terminal; do not buy another')
        ws=Workspace(root,home)
        if pending_authors(ws) or ws.manual_waiting() or (home/'STUDIO_CURRENT.json').exists():
            raise RuntimeError('Reconcile unresolved work first')
        prior=ws._draft(prior_log['prior_draft'])
        if prior['state']!='needs_revision' or prior.get('verification'):raise RuntimeError('Candidate changed')
        note=next(n for n in ws.notes.all() if n['id']==prior_log['review_note'])
        if note['resolved']:raise RuntimeError('Task note resolved; do not replay obsolete guidance')
        source=collect_snapshot(ws)['digest'];public=expectation_digest(ws,'m5')
        if source!=prior_log['source_digest'] or public!=prior_log['public_acceptance_digest']:
            raise RuntimeError('Source or acceptance changed')
        protected=prior_log['protected_sha256']
        def intact():return all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in protected.items())
        if not intact():raise RuntimeError('Historical or acceptance evidence changed')
        config=ws.config();spec=config['instruments']['author']
        if config['roles']['plan']!=['author'] or [spec['model']]+spec.get('fallback_models',[])!=ROUTES:
            raise RuntimeError('Free-only routing changed')
        original=_read_json(home/'inference-requests'/f"{prior_log['calls'][0]['request_id']}.json",{})
        original_prompt=original.get('body',{}).get('prompt','')
        if note['text'] in original_prompt:raise RuntimeError('Diagnosis changed: original task was delivered')
        info=inspect_revision(ws,prior['id'])
        if info['blockers'] or not info['preview'] or not info['view']:raise RuntimeError(str(info['blockers']))
        prompt=info['preview']['prompt']
        if note['text'] not in prompt or info['view']['selections']!=prior_log['selections']:
            raise RuntimeError('Complete fresh task or tests-only selection not delivered')
        record={'state':'prepared','utc':_now(),'prior_allocation':str(prior_log['request_key']),
            'prior_draft':prior['id'],'note':note['id'],'old_job':prior_log['calls'][0]['job_id'],
            'old_prompt_contained_complete_task':False,'new_preview_contains_complete_task':True,
            'task_note_sha256':hashlib.sha256(note['text'].encode()).hexdigest(),
            'preview_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'preview_bytes':len(prompt.encode()),
            'feedback_delivery':info['feedback'],'source_digest':source,'public_acceptance_digest':public,
            'gateway_job_limit':1,'router_retry':False,'paid_fallback':False,'configured_routes':ROUTES,
            'reason':'A new bounded task after a verified reusable feedback-delivery fix. Old terminal request is preserved, not resumed or reset.',
            'trainer_assistance':'Runtime note-selection fix and exact packet inspection. No trainer-authored Hat test or implementation.',
            'project_checks':False,'owner_checks':False,'apply':False,'stop_rule':'One answer then park; no automatic correction or test retry.'}
        _write_json(out,record);calls=[]
        router=ws.router(on_call=lambda e:(calls.append(e),ws.record_call(e)),backoff_s=())
        class Once:
            count=0
            def call(self,role,**kwargs):
                sent=kwargs['prompt'];size=len(sent.encode())
                if self.count or size>54000 or kwargs['max_tokens']>4000 or note['text'] not in sent:
                    raise RuntimeError('Call bound or actual task-delivery guard failed')
                self.count+=1
                record.update(state='submitted',prompt_bytes_actual=size,request_key=kwargs['key'],
                    actual_prompt_contains_complete_task=True,actual_prompt_sha256=hashlib.sha256(sent.encode()).hexdigest())
                _write_json(out,record)
                print(json.dumps({'state':'submitted','complete_task_delivered':True,'prompt_bytes':size,'free_only':True}),flush=True)
                return router.call(role,**kwargs)
        try:
            draft=draft_files(ws,Once(),'m5',revision=prior)
            changed=[f['path'] for f in draft['files'] if f['content']!=next(p['content'] for p in prior['files'] if p['path']==f['path'])]
            record.update(state='admitted',draft=draft['id'],authored_by=draft.get('drafted_by'),changed_files=changed)
            ws._save_draft_state(draft,'needs_revision',review_requested_by='external-trainer',
                                review_note=note['id'],diagnostic_test_candidate=True)
            record['decision']='park_for_discrimination_review; no verification/application'
        except Exception as error:
            record.update(state='refused_or_unresolved',error=type(error).__name__+': '+str(error)[:500],remote_receipt=getattr(error,'remote_receipt',{}))
        record.update(finished=_now(),calls=calls,source_unchanged=collect_snapshot(ws)['digest']==source,protected_unchanged=intact())
        _write_json(out,record)
        ws.ledger.append('trainer.task_delivery_author',{k:v for k,v in record.items() if k!='feedback_delivery'})
        print(json.dumps({k:v for k,v in record.items() if k!='feedback_delivery'}),flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
