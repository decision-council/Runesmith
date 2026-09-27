"""User-selected paid Opus author through Milliner; one journaled request."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from runesmith.config import build_instrument
from runesmith.instruments import Router


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home):raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        path = home / 'trainer-trials/opus-m5-20260926.json'
        if path.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(path, {}).get('state', 'unknown')})); return
        if pending_authors(ws):raise RuntimeError('Reconcile pending author first')
        prior = _read_json(home / 'trainer-trials/opencode-cli-longcat-m5-20260926.json', {})
        if (prior.get('exit_code') != 1 or prior.get('timed_out') is not False or
                not any((e.get('data') or {}).get('statusCode') == 403 for e in prior.get('cli_errors', []))):
            raise RuntimeError('CLI predecessor not the reviewed terminal refusal')
        before = source_context(ws)['snapshot_digest']
        public = expectation_digest(ws, 'm5')
        if before != prior['source_digest'] or public != prior['public_acceptance_digest']:
            raise RuntimeError('Source or acceptance changed')
        if any(d.get('milestone') == 'm5' and d.get('state') in ('waiting', 'applied') for d in ws.drafts()):
            raise RuntimeError('m5 already has a candidate')
        old = ws.config()['instruments']['author']
        original = build_instrument('author', old, home)
        name = 'paid-opus45'
        ws.save_instrument(name, {'kind': 'milliner', 'preset': 'milliner',
            'model': 'openrouter:anthropic/claude-opus-4.5', 'base_url': old['base_url'],
            'timeout_s': 300, 'fallback_models': [], 'budget_tag': 'runesmith-field-training',
            'caller_tag': 'runesmith/trainer/growth-m5-opus',
            'note': 'User chose paid Opus while credit remains. One bounded author trial, no silent retry; primary roles unchanged.'},
            key_value=original._token(), roles=[])
        instrument = build_instrument(name, ws.config()['instruments'][name], home)
        receipt = {'state': 'started', 'utc': _now(), 'milestone': 'm5', 'requested_model': instrument.model,
            'source_digest': before, 'public_acceptance_digest': public, 'author_limit': 1,
            'automatic_retry': False, 'fallback': False, 'predecessor': 'OpenCode genuine CLI terminal403',
            'observed_shared_credit_before_usd': 0.908075842,
            'credit_note': 'Read from provider credit API before this run; shared balance, not an isolated project budget.',
            'reason': 'Latest user instruction: use paid Opus while credit is available. Same frozen m5 task and criteria.'}
        _write_json(path, receipt)
        events = []
        def record(event):events.append(event); ws.record_call(event)
        router = Router({name: instrument}, {'plan': [name]}, backoff_s=(), on_call=record)
        print(json.dumps({'state': 'starting_paid_author', 'model': instrument.model, 'max_requests': 1}), flush=True)
        try:
            draft = draft_files(ws, router, 'm5')
            receipt.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'),
                paths=[f['path'] for f in draft['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved', error=type(error).__name__ + ': ' + str(error)[:500],
                remote_receipt=getattr(error, 'remote_receipt', {}))
        receipt.update(finished=_now(), calls=events, source_unchanged=source_context(ws)['snapshot_digest'] == before)
        _write_json(path, receipt)
        ws.ledger.append('trainer.author_trial', receipt)
        print(json.dumps(receipt, ensure_ascii=True))
    finally:
        if lock.handle:lock.handle.close()


if __name__ == '__main__':main()
