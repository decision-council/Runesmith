"""One prospectively quoted re-verification, retaining all earlier outcomes."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.verification_allocation import allocate_verification, allocation_status
from runesmith.app.workspace import Workspace, _read_json


def main():
    root = Path(__file__).resolve().parent / 'SupportHat'
    home = root / '.runesmith'
    did = 'd20260926170845e812'
    if _existing(home):
        raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():
        raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        if pending_authors(ws):
            raise RuntimeError('Reconcile pending author first')
        draft = ws._draft(did)
        status = allocation_status(ws, draft)
        if status['used']:
            print(json.dumps({'already_used': True, 'state': status['receipt'].get('state'),
                              'outcome': status['receipt'].get('outcome'), 'no_checks_repeated': True}))
            return
        if source_context(ws)['snapshot_digest'] != '6ee90ff4e46a8d253c3e4e6fe2a3865db00e751a9d4fe5b9ade533dc2a5fbd6b':
            raise RuntimeError('Source changed; review before allocating')
        if draft['state'] != 'waiting' or draft['verification']['status'] != 'inconclusive':
            raise RuntimeError('Retained draft changed; review first')
        if any(not f['path'].startswith(('supporthat/', 'tests/')) for f in draft['files']):
            raise RuntimeError('Candidate goes beyond the reviewed implementation/test files')
        q = status.get('quote') or {}
        if not status['eligible'] or (q.get('project_timeout_s'), q.get('owner_timeout_s'), q.get('maximum_check_s')) != (360, 240, 600):
            raise RuntimeError('The prospective reviewed allocation no longer matches')
        if q.get('grant') != '0adcfda7ed6d418f9d9994596b12b1ef':
            raise RuntimeError('Executable grant changed; review before this run')
        protected = [home / 'build-check-resumes' / (did + '.json')]
        protected.extend(home / e / 'VERIFICATION.json' for e in q['prior_history'])
        protected.extend(home / 'acceptance' / name for name in q['acceptance_bundle'])
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        print(json.dumps({'state': 'about_to_reserve', 'draft': did, 'quote': q['id'],
            'project_limit_s': 360, 'owner_limit_s': 240, 'maximum_check_s': 600,
            'inference_calls': 0, 'author': draft.get('drafted_by')}), flush=True)
        result = allocate_verification(ws, did, q['id'],
            'External trainer chooses one separate operational allocation prospectively, after the accepted-source '
            'baseline passed50 tests in133.910s. Project ceiling360s = baseline plus equal host-variation allowance '
            'plus90s for unmeasured additions, rounded up30s; owner ceiling240s is a declared unmeasured allowance. '
            'All61 candidate project tests and the entire unchanged owner bundle must run anew. '
            'Prior120/240s results and budgets remain unchanged. No new inference, criterion edit, '
            'partial-test reuse or automatic repetition. Apply only through existing unchanged grant and CAS gates.')
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        if before != after:
            raise RuntimeError('Original receipt or sealed acceptance changed; investigate')
        v = result.get('verification') or {}
        phases = {name: {k: (v.get(name) or {}).get(k) for k in ('status', 'ran', 'elapsed_s', 'limit_s', 'ok')}
                  for name in ('project_checks', 'acceptance')}
        print(json.dumps({'summary': result['summary'], 'allocation': result.get('allocation'),
            'status': v.get('status'), 'advanced': result.get('advanced', False), 'phases': phases,
            'evidence_dir': v.get('evidence_dir'), 'old_receipts_acceptance_unchanged': before == after,
            'inference_calls': 0, 'author': draft.get('drafted_by'),
            'current_source_digest': source_context(ws)['snapshot_digest']}, ensure_ascii=True))
    finally:
        if lock.handle:
            lock.handle.close()


if __name__ == '__main__':
    main()
