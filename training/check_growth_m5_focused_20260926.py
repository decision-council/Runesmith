"""One first check of the retained instrument revision, with no apply or inference."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app import build_memory  # Bind this process before trainer memory edits.
from runesmith.app.author_recovery import pending_authors
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.building import _check_and_record, _candidate_files, status
from runesmith.app.planner import milestone_contract
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot, digest_files
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        path = home / 'trainer-trials/opus-m5-focused-first-check-20260926.json'
        if path.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(path, {}).get('state', 'unknown')})); return
        if pending_authors(ws): raise RuntimeError('Reconcile pending author first')
        draft = ws._draft('d202609261957066ca2')
        if draft['state'] != 'waiting' or draft.get('verification'):
            raise RuntimeError('Candidate is not the unverified retained revision')
        if any(not f['path'].startswith(('growthhat/', 'tests/')) for f in draft['files']):
            raise RuntimeError('Candidate exceeds reviewed code/test scope')
        snapshot = collect_snapshot(ws)
        if snapshot['digest'] != '4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5':
            raise RuntimeError('Source changed')
        if expectation_digest(ws, 'm5') != '5cd2c483da619a4cc34cc720209a91affdef20429b66372d43d1c28209e79cb3':
            raise RuntimeError('Public criteria changed')
        candidate = digest_files(_candidate_files(snapshot, draft), snapshot['policy'].get('declared_documents', []))['digest']
        if candidate != 'dd8d253658b5739fd4387da71fdf8d1f69b7ad8512e883398071719febd76e93':
            raise RuntimeError('Retained candidate changed')
        grant = status(ws)
        if not grant['enabled'] or grant['grant'] != '26cdda8190bd4d55aaf5631bd4837335':
            raise RuntimeError('Executable-check authority changed')
        milestone = next(m for m in ws.plan()['milestones'] if m['id'] == 'm5')
        contract = milestone_contract(ws, milestone)
        if contract != draft.get('contract'): raise RuntimeError('Milestone contract changed')
        originals = list((home / 'acceptance').glob('*.py')) + list((home / 'build-runs/d20260926192554fa1a').glob('*/VERIFICATION.json'))
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
        receipt = {'state': 'started', 'utc': _now(), 'draft': draft['id'], 'contract': contract,
            'snapshot_digest': snapshot['digest'], 'candidate_digest': candidate,
            'project_timeout_s': 240, 'owner_timeout_s': 240, 'allow_apply': False, 'inference_calls': 0,
            'reason': 'External trainer sets the first check allowance prospectively from predecessor timings '
                      '(149.749s project, 85.639s owner). One run, unchanged tests and source; no reset of '
                      'the predecessor continuation. Check only: semantic review remains separate.',
            'preserved_sha256': hashes}
        _write_json(path, receipt); ws.ledger.append('trainer.focused_check_started', receipt)
        print(json.dumps({k: receipt[k] for k in ('state','utc','draft','project_timeout_s','owner_timeout_s','inference_calls')}), flush=True)
        result = _check_and_record(ws, draft, milestone, contract, checkpoint=lambda: None,
                                  allow_apply=False, project_timeout_s=240, owner_timeout_s=240)
        v = result.get('verification') or {}
        unchanged = all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in originals)
        receipt.update(state='finished', finished=_now(), summary=result['summary'], status=v.get('status'),
            evidence_dir=v.get('evidence_dir'), advanced=bool(result.get('advanced')),
            source_unchanged=collect_snapshot(ws)['digest'] == snapshot['digest'], originals_unchanged=unchanged,
            phases={name: {k: (v.get(name) or {}).get(k) for k in ('status','ran','failures','errors','elapsed_s','limit_s','ok')}
                    for name in ('project_checks','acceptance')})
        _write_json(path, receipt); ws.ledger.append('trainer.focused_check_finished', receipt)
        print(json.dumps({k: value for k, value in receipt.items() if k != 'preserved_sha256'}), flush=True)
        if not unchanged: raise RuntimeError('Original evidence changed')
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__': main()
