"""One paid instrument revision after a definite check failure and context repair."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.source_focus import save_focus
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from runesmith.config import build_instrument
from runesmith.instruments import Router


def main():
    credit = float(sys.argv[1])
    if credit < 0.5:raise RuntimeError('Insufficient observed credit for this paid attempt; use an authorized free route separately')
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home):raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home); path = home / 'trainer-trials/opus-m5-focused-revision-20260926.json'
        if path.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(path, {}).get('state', 'unknown')})); return
        if pending_authors(ws):raise RuntimeError('Reconcile pending author first')
        old = ws._draft('d20260926192554fa1a')
        if old['state'] != 'needs_revision' or old['verification']['status'] != 'failed':
            raise RuntimeError('Predecessor is not the observed failed candidate')
        if any(d['id'] != old['id'] and d.get('milestone') == 'm5' and d.get('state') in ('waiting','applied') for d in ws.drafts()):
            raise RuntimeError('Another m5 candidate already exists')
        snapshot = collect_snapshot(ws)
        if snapshot['digest'] != '4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5':
            raise RuntimeError('Source changed')
        if expectation_digest(ws, 'm5') != '5cd2c483da619a4cc34cc720209a91affdef20429b66372d43d1c28209e79cb3':
            raise RuntimeError('Acceptance changed')
        preview = save_focus(ws, ['growthhat/cli.py'], snapshot['digest'],
            'External trainer prioritizes the existing public CLI after77 project checks passed and '
            'one of25 cumulative owner checks failed on missing recommendation command. '
            'The20554byte implementation had been excluded by the20000byte default file cap. '
            'Use the same48000character source budget; preserve original candidate and all acceptance.')
        context = source_context(ws)
        if 'growthhat/cli.py' not in context['files']:raise RuntimeError('Required context still absent')
        name = 'paid-opus45'; instrument = build_instrument(name, ws.config()['instruments'][name], home)
        receipt = {'state': 'started', 'utc': _now(), 'milestone': 'm5', 'prior_draft': old['id'],
            'requested_model': instrument.model, 'inference_limit': 1, 'automatic_retry': False, 'fallback': False,
            'observed_shared_credit_before_usd': credit, 'credit_observation_utc': sys.argv[2],
            'source_digest': snapshot['digest'], 'public_acceptance_digest': expectation_digest(ws, 'm5'),
            'focus_paths': preview['focus']['paths'], 'source_chars': context['selection']['used_chars'],
            'source_budget_chars': context['selection']['budget_chars'], 'context_digest': context['digest'],
            'trainer_assistance': 'Select missing source and enable bounded context path; model authors implementation.'}
        _write_json(path, receipt)
        events = []
        def record(event):events.append(event); ws.record_call(event)
        router = Router({name: instrument}, {'plan': [name]}, backoff_s=(), on_call=record)
        print(json.dumps({'state': 'starting_focused_revision', 'model': instrument.model,
                          'source_chars': receipt['source_chars'], 'source_budget_chars': receipt['source_budget_chars']}), flush=True)
        try:
            draft = draft_files(ws, router, 'm5')
            receipt.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'),
                           paths=[f['path'] for f in draft['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved', error=type(error).__name__ + ': ' + str(error)[:500],
                           remote_receipt=getattr(error, 'remote_receipt', {}))
        receipt.update(finished=_now(), calls=events, source_unchanged=collect_snapshot(ws)['digest'] == snapshot['digest'])
        _write_json(path, receipt); ws.ledger.append('trainer.focused_revision', receipt)
        print(json.dumps(receipt), flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__ == '__main__':main()
