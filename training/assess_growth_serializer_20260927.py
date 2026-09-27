"""Preserve the free-author result and the existing trainer probes, then park it."""
from pathlib import Path
import hashlib
import json
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnose_growth_export_review_20260926 import probe
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home): raise RuntimeError('Use resident Studio queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Home has another writer')
    try:
        ws = Workspace(root, home); path = home / 'trainer-trials/gemini-m5-serializer-assessment-20260927.json'
        if path.exists(): print(json.dumps({'already_assessed': True})); return
        if pending_authors(ws) or _read_json(home/'STUDIO_CURRENT.json',None): raise RuntimeError('Pending/interrupted work')
        author = _read_json(home / 'trainer-trials/gemini-m5-serializer-20260927.json', {})
        if author.get('state') != 'admitted': raise RuntimeError('No admitted new candidate')
        draft = ws._draft(author['draft']); prior = ws._draft(author['prior_draft'])
        if draft['state'] != 'waiting' or draft.get('verification'): raise RuntimeError('Candidate state changed')
        if collect_snapshot(ws)['digest'] != author['source_digest'] or expectation_digest(ws,'m5') != author['public_acceptance_digest']:
            raise RuntimeError('Source or criteria changed')
        receipt = {'state':'started','utc':_now(),'draft':draft['id'],'prior':prior['id'],'inference_calls':0,
            'scope':'Trainer controlled-function probes and candidate comparison only; not project, owner or production verification.',
            'original_checks':['race','export_error'],'previously_disclosed_exploratory_check':'serialization_error',
            'probe_script_sha256':hashlib.sha256((Path(__file__).parent/'diagnose_growth_export_review_20260926.py').read_bytes()).hexdigest()}
        _write_json(path,receipt)
        race, export = probe(draft,'race'), probe(draft,'export_error')
        with patch('json.dump',side_effect=TypeError('synthetic serialization failure')) as injected:
            serializer = probe(draft,'serialization_error'); injected_count = injected.call_count
        changed = [f['path'] for f in draft['files'] if f['content'] != next(o['content'] for o in prior['files'] if o['path']==f['path'])]
        passed = (race.get('return_code')==1 and race.get('competitor_preserved') and race.get('open_descriptors_after')==0
                  and export.get('return_code')==1 and not export.get('destination_exists') and export.get('open_descriptors_after')==0)
        serializer_pass = serializer.get('return_code')==1 and not serializer.get('destination_exists') and serializer.get('open_descriptors_after')==0
        if not serializer_pass or 'tests/test_recommendation_cli.py' not in changed:
            note = ws.notes.add(target_type='draft',target_id=draft['id'],target_label=draft['title'],author='external-trainer',
                text='Post-allocation trainer review: original race/export-data probes remain green, but the known '
                     'serialization-failure probe still raises OSError and leaves the destination. The model changed '
                     'only the CLI function; the requested project regression file remains unchanged. This is not '
                     'completion. No full project/owner checks or apply were run, and no owner criteria were changed. '
                     'The new one-call free allocation is finished and parked. Further work should change task '
                     'decomposition or author selection rather than silently repeat this allocation.')
            ws._save_draft_state(draft,'needs_revision',review_requested_by='external-trainer',review_note=note['id'])
            receipt['review_note']=note['id']
        receipt.update(state='finished',finished=_now(),race=race,export_error=export,original_probes_passed=bool(passed),
            serialization_error=serializer,serializer_injections=injected_count,serialization_probe_passed=bool(serializer_pass),
            changed_files=changed,regression_file_changed='tests/test_recommendation_cli.py' in changed,
            decision='park_bounded_allocation',project_checks_run=False,owner_checks_run=False,applied=False,
            source_unchanged=collect_snapshot(ws)['digest']==author['source_digest'],
            protected_unchanged=all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in author['protected_sha256'].items()))
        _write_json(path,receipt);ws.ledger.append('trainer.serializer_assessment',receipt);print(json.dumps(receipt))
    finally:
        if lock.handle: lock.handle.close()


if __name__=='__main__': main()
