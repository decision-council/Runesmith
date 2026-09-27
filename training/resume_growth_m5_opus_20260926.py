"""Exercise the existing one-time check continuation, no new author request."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.verification_resume import resume_verification, resume_status
from runesmith.app.workspace import Workspace, _read_json


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home):raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        if pending_authors(ws):raise RuntimeError('Reconcile pending author first')
        did = 'd20260926192554fa1a'; draft = ws._draft(did)
        state = resume_status(ws, draft)
        if state['used']:
            print(json.dumps({'already_used': True, 'receipt': state['receipt']})); return
        if not state['eligible']:raise RuntimeError('Saved candidate is not eligible')
        if any(not f['path'].startswith(('growthhat/', 'tests/')) for f in draft['files']):
            raise RuntimeError('Candidate exceeds reviewed code/test scope')
        original = home / 'build-runs/d20260926192554fa1a/v-70fb902f5e39/VERIFICATION.json'
        paths = [original, *(home / 'acceptance').glob('*.py')]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        if source_context(ws)['snapshot_digest'] != draft['snapshot_digest']:
            raise RuntimeError('Source changed')
        print(json.dumps({'draft': did, 'starting': 'one240s-per-phase continuation', 'inference_calls': 0}), flush=True)
        result = resume_verification(ws, did,
            'External trainer chooses the one existing 240s-per-phase continuation after the original120s '
            'project phase completed43 checks with no reported failure before timeout. No criterion, '
            'candidate, source or author budget changes; run the full candidate and owner bundle anew. '
            'Apply only through the existing unchanged grant and CAS gates. No automatic repetition.')
        v = result.get('verification') or {}
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        print(json.dumps({'draft': did, 'summary': result['summary'], 'status': v.get('status'),
            'evidence_dir': v.get('evidence_dir'), 'advanced': bool(result.get('advanced')),
            'original_evidence_and_acceptance_unchanged': before == after,
            'phases': {name: {k: (v.get(name) or {}).get(k) for k in ('status','ran','elapsed_s','limit_s','ok')}
                       for name in ('project_checks','acceptance')}, 'inference_calls': 0}), flush=True)
        if before != after:raise RuntimeError('Original evidence changed')
    finally:
        if lock.handle:lock.handle.close()


if __name__ == '__main__':main()
