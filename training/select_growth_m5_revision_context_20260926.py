"""Save the qualified candidate-only context profile; never grants a model call."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.revision_context import inspect_revision, save_selection
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'
    home = root / '.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        journal = home / 'trainer-trials/focused-revision-context-20260926.json'
        if journal.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(journal, {}).get('state')})); return
        if pending_authors(ws): raise RuntimeError('Reconcile pending authors')
        previous = _read_json(home / 'trainer-trials/gemini-m5-export-assessment-20260926.json', {})
        if previous.get('decision') != 'park_bounded_allocation': raise RuntimeError('Earlier allocation is not parked')
        draft_id = 'd20260926203439dbeb'
        snapshot = collect_snapshot(ws)
        if snapshot['digest'] != '4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5':
            raise RuntimeError('Source changed')
        public_digest = expectation_digest(ws, 'm5')
        if public_digest != '5cd2c483da619a4cc34cc720209a91affdef20429b66372d43d1c28209e79cb3':
            raise RuntimeError('Public criteria changed')
        protected = list((home / 'acceptance').glob('*.py')) + list((home / 'build-runs').glob('*/v-*/VERIFICATION.json'))
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        before = inspect_revision(ws, draft_id)
        if before['blockers']: raise RuntimeError(str(before['blockers']))
        chosen = [u for u in before['units'] if
                  (u['path'] == 'growthhat/cli.py' and u['label'] == 'cmd_export_recommendations') or
                  (u['path'] == 'tests/test_recommendation_cli.py' and u['unit'] == '*')]
        if len(chosen) != 2: raise RuntimeError('Expected function and complete CLI test file unavailable')
        selections = [{k: u[k] for k in ('path', 'unit')} for u in chosen]
        receipt = {'state': 'started', 'utc': _now(), 'draft': draft_id, 'inference_calls': 0,
                   'source_digest': snapshot['digest'], 'public_acceptance_digest': public_digest,
                   'protected_sha256': hashes, 'prior_allocation': 'parked; not reset', 'selections': selections,
                   'trainer_assistance': 'Selected a known faulty function and complete model-authored CLI test file; no Hat code edits.'}
        _write_json(journal, receipt)
        after = save_selection(ws, draft_id, version=before['version'], selections=selections,
            reason='External trainer: narrow a local export resource-lifetime revision to its complete function '
                   'and the complete CLI test file. Retain all other candidate bytes and full source/acceptance bindings. '
                   'Prior free allocation stays parked; this selection grants no new model call or verification budget.')
        preview = after['preview']
        receipt.update(state='selected', finished=_now(), candidate_digest=after['view']['candidate_digest'],
            code_chars=after['view']['code_chars'], broad_prompt_bytes=preview['broad_prompt_bytes'],
            focused_prompt_bytes=preview['focused_prompt_bytes'],
            reduction_fraction=1 - preview['focused_prompt_bytes'] / preview['broad_prompt_bytes'],
            focused_prompt_sha256=hashlib.sha256(preview['prompt'].encode()).hexdigest(),
            source_unchanged=collect_snapshot(ws)['digest'] == snapshot['digest'],
            protected_unchanged=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in protected))
        _write_json(journal, receipt)
        ws.ledger.append('trainer.revision_context_selected', {k: v for k, v in receipt.items() if k != 'protected_sha256'})
        print(json.dumps({k: v for k, v in receipt.items() if k != 'protected_sha256'}))
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__': main()
