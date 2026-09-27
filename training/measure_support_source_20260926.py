"""Single accepted-source measurement, not another m6 candidate verification."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.source_baseline import measure_current_source
from runesmith.app.workspace import Workspace


def main():
    root = Path(__file__).resolve().parent / 'SupportHat'
    home = root / '.runesmith'
    if _existing(home):
        raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():
        raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        if pending_authors(ws):
            raise RuntimeError('Reconcile pending author first')
        current = source_context(ws)['snapshot_digest']
        if current != '6ee90ff4e46a8d253c3e4e6fe2a3865db00e751a9d4fe5b9ade533dc2a5fbd6b':
            raise RuntimeError('Accepted source changed; review before this measurement')
        draft = ws._draft('d20260926170845e812')
        if draft['state'] != 'waiting' or draft['verification']['status'] != 'inconclusive':
            raise RuntimeError('The retained m6 candidate changed; review first')
        frozen = [home / 'drafts/d20260926170845e812/DRAFT.json', home / 'PLAN.json', home / 'BUILD_LAST.json',
                  home / 'build-check-resumes/d20260926170845e812.json', home / 'acceptance/m6.py']
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen}
        result = measure_current_source(ws,
            'Trainer-authorized source_baseline_diagnostic after 18:25+ read-only advisor consultation. '
            'Measure accepted m5 complete project suite (expected50), once at240s on the current host. '
            'No m6 override, owner test, inference, apply, budget reset or automatic follow-up. '
            'No concurrent heavy verification started by this trainer; other host workload unknown.')
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen}
        if before != after:
            raise RuntimeError('Protected candidate/acceptance/plan changed during diagnostic; investigate')
        receipt = result.get('baseline') or {}
        checks = receipt.get('project_checks') or {}
        print(json.dumps({'summary': result['summary'], 'already_used': result.get('already_used', False),
            'state': receipt.get('state'), 'outcome': receipt.get('outcome'),
            'project_checks': {k: checks.get(k) for k in ('status', 'ran', 'elapsed_s', 'limit_s', 'progress')},
            'inventory': receipt.get('inventory'), 'evidence_dir': receipt.get('evidence_dir'),
            'candidate_plan_acceptance_unchanged': before == after, 'inference_calls': 0}, ensure_ascii=True))
    finally:
        if lock.handle:
            lock.handle.close()


if __name__ == '__main__':
    main()
