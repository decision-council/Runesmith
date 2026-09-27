"""One prospectively bounded free author attempt with a qualified focused packet."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, draft_prompt, source_context
from runesmith.app.revision_context import selected_view
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json

ROUTES = ['gemini3:gemini-3.1-flash-lite', 'gemini2:gemini-3.1-flash-lite', 'gemini:gemini-3.1-flash-lite-preview']


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        path = home / 'trainer-trials/gemini-m5-focused-units-20260926.json'
        if path.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(path, {}).get('state')})); return
        if pending_authors(ws): raise RuntimeError('Reconcile pending author first')
        old = _read_json(home / 'trainer-trials/gemini-m5-export-assessment-20260926.json', {})
        focus_receipt = _read_json(home / 'trainer-trials/focused-revision-context-20260926.json', {})
        if old.get('decision') != 'park_bounded_allocation' or focus_receipt.get('state') != 'selected':
            raise RuntimeError('Prior stop or new focus receipt is missing')
        prior = ws._draft('d20260926203439dbeb')
        if prior['state'] != 'needs_revision' or prior.get('verification'): raise RuntimeError('Candidate state changed')
        snapshot = collect_snapshot(ws)
        if snapshot['digest'] != '4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5':
            raise RuntimeError('Source changed')
        if expectation_digest(ws, 'm5') != '5cd2c483da619a4cc34cc720209a91affdef20429b66372d43d1c28209e79cb3':
            raise RuntimeError('Criteria changed')
        config = ws.config(); spec = config['instruments']['author']
        if config['roles']['plan'] != ['author'] or [spec['model']] + spec.get('fallback_models', []) != ROUTES:
            raise RuntimeError('Expected free-only author route changed; no paid fallback authorized')
        view = selected_view(ws, prior)
        if not view or view['candidate_digest'] != focus_receipt['candidate_digest']: raise RuntimeError('Focus changed')
        milestone = next(m for m in ws.plan()['milestones'] if m['id'] == 'm5')
        prompt = draft_prompt(ws, milestone, source_context(ws), revision=prior, revision_view=view)
        if len(prompt.encode()) > 40000: raise RuntimeError('Focused prompt exceeded the prospective 40000-byte ceiling')
        protected = list((home / 'acceptance').glob('*.py')) + list((home / 'build-runs').glob('*/v-*/VERIFICATION.json'))
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        receipt = {'state': 'started', 'utc': _now(), 'prior_draft': prior['id'], 'milestone': 'm5',
            'prior_allocation': 'parked; not reset', 'gateway_job_limit': 1, 'router_retry': False,
            'configured_routes': ROUTES, 'paid_fallback': False, 'max_output_tokens': 4000,
            'prompt_bytes': len(prompt.encode()), 'prompt_ceiling_bytes': 40000,
            'focus_selections': view['selections'], 'candidate_digest': view['candidate_digest'],
            'source_digest': snapshot['digest'], 'public_acceptance_digest': expectation_digest(ws, 'm5'),
            'protected_sha256': hashes, 'apply': False, 'project_checks': False, 'owner_checks': False,
            'stop_rule': 'One returned/refused/unresolved author result, then trainer review. No automatic retry, checks or apply. '
                         'The two existing semantic probes must pass before considering the unchanged full gates.',
            'trainer_assistance': 'Implemented candidate-unit packet/admission guard and chose the export function plus complete CLI tests. '
                                  'No new corrective Hat code or new review hint was supplied. This is a development observation, not an A/B test.'}
        _write_json(path, receipt)
        events = []
        def record(event): events.append(event); ws.record_call(event)
        router = ws.router(on_call=record, backoff_s=())
        print(json.dumps({'state': 'starting', 'gateway_job_limit': 1, 'prompt_bytes': receipt['prompt_bytes']}), flush=True)
        try:
            draft = draft_files(ws, router, 'm5', revision=prior)
            receipt.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'),
                           paths=[f['path'] for f in draft['files']], revision_view_recorded=bool(draft.get('revision_view')))
        except Exception as error:
            receipt.update(state='refused_or_unresolved', error=type(error).__name__ + ': ' + str(error)[:500],
                           remote_receipt=getattr(error, 'remote_receipt', {}))
        receipt.update(finished=_now(), calls=events, source_unchanged=collect_snapshot(ws)['digest'] == snapshot['digest'],
            protected_unchanged=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in protected))
        _write_json(path, receipt)
        ws.ledger.append('trainer.focused_unit_revision', {k: v for k, v in receipt.items() if k != 'protected_sha256'})
        print(json.dumps({k: v for k, v in receipt.items() if k != 'protected_sha256'}), flush=True)
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__': main()
