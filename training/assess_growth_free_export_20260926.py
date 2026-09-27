"""Durably retain the bounded free-revision assessment; no project modifications."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace,_write_json,_read_json,_now
from runesmith.app.author_recovery import pending_authors
from runesmith.app.snapshots import collect_snapshot
from diagnose_growth_export_review_20260926 import probe


def main():
    root=Path(__file__).resolve().parent/'GrowthHat';home=root/'.runesmith'
    if _existing(home):raise RuntimeError('Use resident Studio queue')
    lock=InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns the home')
    try:
        ws=Workspace(root,home);path=home/'trainer-trials/gemini-m5-export-assessment-20260926.json'
        if path.exists():print(json.dumps({'existing':_read_json(path,{})}));return
        if pending_authors(ws):raise RuntimeError('Pending author needs reconciliation')
        snapshot=collect_snapshot(ws)
        if snapshot['digest']!='4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5':raise RuntimeError('Source changed')
        retained=['d202609261957066ca2','d202609262025386e60','d20260926203439dbeb']
        receipt={'state':'started','utc':_now(),'source_digest':snapshot['digest'],'inference_calls':0,
            'scope':'Trainer-only unchanged-function controlled namespace; not full application, project or owner tests',
            'script_sha256':hashlib.sha256((Path(__file__).parent/'diagnose_growth_export_review_20260926.py').read_bytes()).hexdigest()}
        _write_json(path,receipt)
        rows=[]
        for did in retained:
            draft=ws._draft(did)
            rows.append({'draft':did,'race':probe(draft,'race'),'export_error':probe(draft,'export_error')})
        latest=rows[-1]
        clears=(latest['race'].get('return_code')==1 and latest['race']['competitor_preserved']
                and not latest['export_error']['destination_exists'] and latest['export_error']['open_descriptors_after']==0)
        receipt.update(state='finished',finished=_now(),rows=rows,known_review_gate_passed=clears,
            decision='park_bounded_allocation' if not clears else 'ready_for_discriminating_test_and_full_gates',
            project_checks_run=False,owner_checks_run=False,applied=False)
        draft=ws._draft(retained[-1])
        if not clears:
            note=ws.notes.add(target_type='draft',target_id=draft['id'],target_label=draft['title'],author='external-trainer',
                text='Bounded free revision assessment: export-data exception still leaves1 descriptor and an empty output. '
                'The new test still precreates its competitor before main, so it does not discriminate against the '
                'old overwrite-race implementation. Atomic no-clobber probe passes; resource-lifetime probe fails. '
                'No full suite or owner checks were run for this candidate, and no apply. One-revision allocation '
                'is now parked; do not repeat calls or reuse a prior passing receipt. Next work needs a separately '
                'reasoned bounded approach, potentially a smaller focused revision packet. The fixed owner '
                'criteria and historical87/25pass remain untouched.')
            ws._save_draft_state(draft,'needs_revision',review_requested_by='external-trainer',review_note=note['id'],
                review_reason='Known export resource-lifetime defect remains after bounded free revision')
            receipt['review_note']=note['id']
        _write_json(path,receipt);ws.ledger.append('trainer.bounded_semantic_assessment',receipt)
        print(json.dumps(receipt),flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
