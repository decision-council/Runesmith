"""One explicit check of the retained model-authored draft; no inference/apply."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.author_recovery import pending_authors
from runesmith.app.building import recheck_draft
from runesmith.app.planner import source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home):raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        path = home / 'trainer-trials/opus-m5-first-check-20260926.json'
        if path.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(path, {}).get('state', 'unknown')})); return
        if pending_authors(ws):raise RuntimeError('Reconcile pending author first')
        did = 'd20260926192554fa1a'
        draft = ws._draft(did)
        if draft.get('verification') or draft['state'] != 'waiting':raise RuntimeError('Draft already checked or changed')
        source = source_context(ws)['snapshot_digest']
        if source != draft['snapshot_digest']:raise RuntimeError('Source changed')
        if any(not f['path'].startswith(('growthhat/', 'tests/')) for f in draft['files']):
            raise RuntimeError('Candidate exceeds implementation/test scope')
        seals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (home / 'acceptance').glob('*.py')}
        receipt = {'state': 'started', 'utc': _now(), 'draft': did, 'source_digest': source,
                   'author': draft['drafted_by'], 'inference_calls': 0, 'allow_apply': False,
                   'project_timeout_s': 120, 'owner_timeout_s': 120}
        _write_json(path, receipt)
        result = recheck_draft(ws, did)
        v = result.get('verification') or {}
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (home / 'acceptance').glob('*.py')}
        receipt.update(state='completed', finished=_now(), status=v.get('status'),
            evidence_dir=v.get('evidence_dir'), source_unchanged=source_context(ws)['snapshot_digest'] == source,
            acceptance_unchanged=seals == after, advanced=bool(result.get('advanced')),
            phases={name: {k: (v.get(name) or {}).get(k) for k in ('status','ran','elapsed_s','limit_s','ok')}
                    for name in ('project_checks','acceptance')})
        _write_json(path, receipt)
        ws.ledger.append('trainer.candidate_check', receipt)
        print(json.dumps(receipt), flush=True)
        if not receipt['source_unchanged'] or not receipt['acceptance_unchanged'] or receipt['advanced']:
            raise RuntimeError('Unexpected source/acceptance/apply mutation; investigate')
    finally:
        if lock.handle:lock.handle.close()


if __name__ == '__main__':main()
