"""One new free-author allocation after the prior parked, partial correction.

The trainer supplies observed failure feedback, not Hat implementation code.
No automatic verification, application or resetting of prior allocations.
"""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files
from runesmith.app.revision_context import inspect_revision, save_selection
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from revise_growth_m5_focused_units_20260926 import ROUTES


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio exists; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Home is owned by another writer')
    try:
        path = home / 'trainer-trials/gemini-m5-serializer-20260927.json'
        if path.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(path, {}).get('state')})); return
        ws = Workspace(root, home)
        if pending_authors(ws) or ws.manual_waiting() or _read_json(home / 'STUDIO_CURRENT.json', None):
            raise RuntimeError('Reconcile interrupted or pending work first')
        assessment = _read_json(home / 'trainer-trials/gemini-m5-focused-units-assessment-20260926.json', {})
        predecessor = _read_json(home / 'trainer-trials/gemini-m5-focused-units-20260926.json', {})
        if assessment.get('decision') != 'park_one_call_allocation_with_partial_progress':
            raise RuntimeError('The prior allocation has not been parked')
        prior = ws._draft('d202609262105221010')
        if prior['state'] != 'needs_revision' or prior.get('verification'):
            raise RuntimeError('Candidate state changed')
        snapshot = collect_snapshot(ws)
        if snapshot['digest'] != predecessor['source_digest'] or expectation_digest(ws, 'm5') != predecessor['public_acceptance_digest']:
            raise RuntimeError('Source or criteria changed')
        hashes = predecessor['protected_sha256']
        def protected_ok():
            return all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in hashes.items())
        if not protected_ok(): raise RuntimeError('Historical check/acceptance bytes changed')
        spec = ws.config()['instruments']['author']
        if ws.config()['roles']['plan'] != ['author'] or [spec['model']] + spec.get('fallback_models', []) != ROUTES:
            raise RuntimeError('Configured free-only author routes changed')
        record = {'state': 'preparing', 'utc': _now(), 'prior_draft': prior['id'], 'milestone': 'm5',
                  'previous_allocation': 'parked; never reset', 'gateway_job_limit': 1, 'router_retry': False,
                  'configured_routes': ROUTES, 'paid_fallback': False, 'prompt_ceiling_bytes': 48000,
                  'max_output_tokens': 4000, 'source_digest': snapshot['digest'],
                  'public_acceptance_digest': predecessor['public_acceptance_digest'], 'protected_sha256': hashes,
                  'project_checks': False, 'owner_checks': False, 'apply': False,
                  'stop_rule': 'One author result, then review. No silent retry, checks or application.',
                  'trainer_assistance': 'Preserve the two prior probe gains. Supply observed serialization-failure feedback and require discriminating project regressions. Select the complete affected function and test file. Instrument authors all Hat code.',
                  'authorization': 'Owner requested continuing configured-author work alongside reusable Runesmith development; this is a separately journaled bounded allocation, not a replay of a spent one.'}
        _write_json(path, record)
        calls = []
        try:
            note = ws.notes.add(target_type='draft', target_id=prior['id'], target_label=prior['title'], author='external-trainer',
                text='New bounded development allocation, 2026-09-27: retain the two successful original probes. '
                     'The inherited serializer-error path still fails: when json.dump raises after fdopen, '
                     'the context closes the descriptor, then the exception handler calls close again before unlink. '
                     'The controlled probe observed OSError and a leftover destination. Correct this resource-lifetime '
                     'path without losing exclusive creation or deleting a competitor-owned destination. '
                     'Also author discriminating CLI regression tests for a competitor appearing at actual open, '
                     'export-data failure, and serialization failure; merely checking an already-existing file is '
                     'not a regression for the race. Preserve unrelated candidate files, public criteria and private '
                     'owner checks. No trainer implementation code supplied. Return exact edits to both the '
                     'displayed function and the displayed project test file; no test result may be invented.')
            record['review_note'] = note['id']
            before = inspect_revision(ws, prior['id'])
            if before['blockers']: raise RuntimeError(str(before['blockers']))
            chosen = [u for u in before['units'] if
                      (u['path'] == 'growthhat/cli.py' and u['label'] == 'cmd_export_recommendations') or
                      (u['path'] == 'tests/test_recommendation_cli.py' and u['unit'] == '*')]
            if len(chosen) != 2: raise RuntimeError('Expected bounded units unavailable')
            saved = save_selection(ws, prior['id'], version=before['version'],
                selections=[{k:u[k] for k in ('path','unit')} for u in chosen],
                reason='New one-call allocation after parked partial progress; narrow to export cleanup and its missing regressions.')
            record.update(prompt_bytes_preview=saved['preview']['focused_prompt_bytes'],
                          selections=saved['view']['selections'], state='prepared')
            _write_json(path, record)
            router = ws.router(on_call=lambda event: (calls.append(event), ws.record_call(event)), backoff_s=())
            class OneCall:
                count = 0
                def call(self, role, **kwargs):
                    size = len(kwargs['prompt'].encode('utf-8'))
                    if self.count or size > record['prompt_ceiling_bytes'] or kwargs['max_tokens'] > 4000:
                        raise RuntimeError('New allocation call/prompt/output bound exceeded')
                    self.count += 1
                    record.update(state='submitted', prompt_bytes_actual=size, request_key=kwargs['key'])
                    _write_json(path, record)
                    print(json.dumps({'state':'submitted','prompt_bytes':size,'calls_allowed':1,'routes':ROUTES}), flush=True)
                    return router.call(role, **kwargs)
            draft = draft_files(ws, OneCall(), 'm5', revision=prior)
            record.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'),
                          paths=[f['path'] for f in draft['files']])
        except Exception as error:
            record.update(state='refused_or_unresolved', error=type(error).__name__+': '+str(error)[:500],
                          remote_receipt=getattr(error, 'remote_receipt', {}))
        record.update(finished=_now(), calls=calls, source_unchanged=collect_snapshot(ws)['digest'] == snapshot['digest'],
                      protected_unchanged=protected_ok())
        _write_json(path, record)
        ws.ledger.append('trainer.serializer_revision', {k:v for k,v in record.items() if k!='protected_sha256'})
        print(json.dumps({k:v for k,v in record.items() if k!='protected_sha256'}), flush=True)
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__': main()
