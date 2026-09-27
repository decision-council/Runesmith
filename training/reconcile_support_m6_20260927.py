"""Explicit one-time field reconciliation; default is a read-only eligibility report.

Run with --execute and the exact freshly reviewed --quote ID only after runtime
qualification. This is re-verification of instrument-authored bytes, not new
project implementation, scientific confirmation or permission to apply.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.verification_reconciliation import reconcile_verification, reconciliation_status
from runesmith.app.workspace import Workspace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--quote')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / 'SupportHat'
    home = root / '.runesmith'
    did = 'd20260926170845e812'
    if _existing(home):
        raise RuntimeError('Resident Studio found; use its queue, not this direct writer.')
    lock = InstanceLock(home)
    if not lock.acquire():
        raise RuntimeError('Another writer owns this home.')
    try:
        # Read-only preview must not initialize/requalify a home.
        ws = object.__new__(Workspace)
        ws.root, ws.home = root, home
        draft = ws._draft(did)
        status = reconciliation_status(ws, draft)
        if not status['eligible']:
            print(json.dumps(status, ensure_ascii=True))
            return
        q = status['quote']
        print(json.dumps({'state': 'eligible_not_executed', 'quote': q,
                          'author': draft.get('drafted_by'), 'inference_calls': 0}), flush=True)
        if not args.execute:
            return
        if args.quote != q['id']:
            raise RuntimeError('An exact reviewed current quote is required; no checks started.')
        if (q['project_timeout_s'], q['owner_timeout_s'], q['maximum_check_s']) != (360, 240, 600):
            raise RuntimeError('Limits differ from the reviewed field allocation.')
        if q['bindings']['snapshot_digest'] != '6ee90ff4e46a8d253c3e4e6fe2a3865db00e751a9d4fe5b9ade533dc2a5fbd6b':
            raise RuntimeError('Source changed; review again.')
        protected = [home / 'build-check-allocations' / (did + '.json'),
                     home / 'build-check-resumes' / (did + '.json')]
        protected.extend(home / rel / 'VERIFICATION.json' for rel in draft['verification_history'])
        protected.extend(p for p in (home / 'acceptance').rglob('*') if p.is_file())
        protected.extend(p for p in (home / 'build-attempts').glob('*.json'))
        protected.extend(home / name for name in ('runesmith.json', 'PLAN.json', 'BUILD_GRANT.json') if (home / name).exists())
        before = {str(p.relative_to(home)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        ws = Workspace(root, home)
        result = reconcile_verification(ws, did, q['id'],
            'External trainer adjudicates the specific legacy preflight rejection using the unchanged '
            'allocation and hash-chain start/completion, the exact source-change refusal, no additional '
            'run directory, the original two timeout receipts, and the now-matching original14-file view. '
            'This is legacy-path evidence, not historical phase instrumentation. One linked recheck only '
            'at the original360s project/240s owner ceilings; run every check anew. Preserve old outcomes '
            'and budgets. No inference, model-authored-byte edits, assertion changes, automatic apply, '
            'extra extension or retry. Qualification:32new backend tests plus broad suite/B4 browser loops.')
        after = {str(p.relative_to(home)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        if before != after:
            raise RuntimeError('A protected input or earlier receipt changed; investigate before further work.')
        v = result.get('verification') or {}
        print(json.dumps({'summary': result['summary'], 'reconciliation': result.get('reconciliation'),
            'status': v.get('status'), 'advanced': result.get('advanced', False),
            'phases': {name: {k: (v.get(name) or {}).get(k) for k in ('status', 'ran', 'elapsed_s', 'limit_s', 'ok', 'errors', 'failures')}
                       for name in ('project_checks', 'acceptance')},
            'evidence_dir': v.get('evidence_dir'), 'protected_files': len(before),
            'protected_unchanged': before == after, 'source_digest': collect_snapshot(ws)['digest'],
            'author': draft.get('drafted_by'), 'new_inference_calls': 0, 'incremental_model_spend_estimate_usd': 0,
            'cost_scope': 'No new model call; local compute and trainer effort not costed.'}, ensure_ascii=True), flush=True)
    finally:
        if lock.handle:
            lock.handle.close()


if __name__ == '__main__':
    main()
