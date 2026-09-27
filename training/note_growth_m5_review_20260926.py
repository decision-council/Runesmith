"""Record trainer review via the existing draft-note channel; no Hat code edits."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.author_recovery import pending_authors


def main():
    root = Path(__file__).resolve().parent/'GrowthHat'; home = root/'.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home); draft = ws._draft('d202609261957066ca2')
        if pending_authors(ws): raise RuntimeError('Pending author needs reconciliation')
        if draft['state'] != 'waiting' or draft.get('verification', {}).get('status') != 'acceptance_passed':
            raise RuntimeError('Review does not match retained candidate state')
        if collect_snapshot(ws)['digest'] != draft['snapshot_digest']:
            raise RuntimeError('Source changed')
        marker = 'Trainer review 2026-09-26: export no-clobber race'
        existing = next((n for n in ws.notes.for_target('draft', draft['id']) if n['text'].startswith(marker)), None)
        if existing:
            print(json.dumps({'existing_note': existing['id']})); return
        note = ws.notes.add(target_type='draft', target_id=draft['id'], target_label=draft['title'],
            author='external-trainer', text=marker + '. The saved Opus4.5 candidate passed87 project tests '
            'and25 owner checks (v-238e248c4d71), but was deliberately not applied. In cmd_export_recommendations, '
            'exists() followed by open(output_path, "w") can overwrite a destination created in between. '
            'The existing-file test does not establish atomic no-clobber behavior. Request one narrow '
            'instrument-authored correction with an adversarial project regression for that race; keep the '
            'same public requirements, private owner checks and other candidate files. The trainer has not '
            'implemented that correction or changed the scientific evidence. This is a review note, not an '
            'automatic runtime apply guard; auto_work remainsfalse and no apply is authorized by this note.')
        ws.ledger.append('trainer.draft_review', {'note':note['id'], 'draft':draft['id'],
            'decision':'retain_unapplied_pending_narrow_instrument_revision',
            'candidate_digest':draft['verification']['candidate_digest'], 'inference_calls':0})
        print(json.dumps({'note': note['id'], 'draft':draft['id'], 'source_unchanged':True, 'inference_calls':0}))
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__': main()
