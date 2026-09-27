"""One tests-only free-author development allocation, never an implementation retry."""
from pathlib import Path
import ast
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
    if _existing(home): raise RuntimeError('Use the resident Studio queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Home has another writer')
    try:
        path = home / 'trainer-trials/gemini-m5-tests-only-20260927.json'
        if path.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(path, {}).get('state')})); return
        ws = Workspace(root, home)
        if pending_authors(ws) or ws.manual_waiting() or _read_json(home/'STUDIO_CURRENT.json', None):
            raise RuntimeError('Reconcile pending/interrupted work first')
        prior_run = _read_json(home/'trainer-trials/gemini-m5-serializer-20260927.json', {})
        assessment = _read_json(home/'trainer-trials/gemini-m5-serializer-assessment-20260927.json', {})
        if assessment.get('decision') != 'park_bounded_allocation': raise RuntimeError('Prior allocation not parked')
        prior = ws._draft(prior_run['draft'])
        if prior['state'] != 'needs_revision' or prior.get('verification'): raise RuntimeError('Candidate state changed')
        source = collect_snapshot(ws)['digest']; public = expectation_digest(ws, 'm5')
        if source != prior_run['source_digest'] or public != prior_run['public_acceptance_digest']:
            raise RuntimeError('Source or criteria changed')
        protected = prior_run['protected_sha256']
        def protected_ok():
            return all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in protected.items())
        if not protected_ok(): raise RuntimeError('Protected history or criteria changed')
        config = ws.config(); spec = config['instruments']['author']
        if config['roles']['plan'] != ['author'] or [spec['model']] + spec.get('fallback_models', []) != ROUTES:
            raise RuntimeError('Configured free-only author routes changed')
        code = next(f['content'] for f in prior['files'] if f['path'] == 'growthhat/cli.py')
        function = next(n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef) and n.name == 'cmd_export_recommendations')
        function_text = ast.get_source_segment(code, function)
        record = {'state': 'preparing', 'utc': _now(), 'prior_draft': prior['id'], 'milestone': 'm5',
            'task': 'Author a discriminating project regression only; implementation is deliberately retained faulty.',
            'gateway_job_limit': 1, 'router_retry': False, 'configured_routes': ROUTES, 'paid_fallback': False,
            'prompt_ceiling_bytes': 54000, 'max_output_tokens': 4000, 'source_digest': source,
            'public_acceptance_digest': public, 'protected_sha256': protected, 'project_checks': False,
            'owner_checks': False, 'apply': False, 'previous_allocation': 'parked, never reset',
            'readonly_candidate_function_sha256': hashlib.sha256(function_text.encode()).hexdigest(),
            'trainer_assistance': 'Select the complete existing project test file; supply verbatim read-only candidate function and public cleanup behavior. No trainer-authored Hat test or implementation.',
            'stop_rule': 'One result, then assess whether it discriminates. No silent retry or implementation correction.',
            'authorization': 'Owner continuation and 22:36 read-only advisor recommendation; separately scoped tests-only allocation.'}
        _write_json(path, record); calls = []
        try:
            note = ws.notes.add(target_type='draft', target_id=prior['id'], target_label=prior['title'], author='external-trainer',
                text='NEW TESTS-ONLY DEVELOPMENT TASK, superseding the previous combined correction requests for this call. '
                     'Do not change implementation. Author one discriminating project CLI regression for JSON serialization failure '
                     'after exclusive destination creation. The expected public behavior is graceful failure (return code 1), '
                     'no newly created destination remaining, and no leaked descriptor. Keep unrelated tests. Trigger the actual '
                     'serializer inside the command; a pre-existing destination or export-data failure does not exercise it. '
                     'The retained candidate is KNOWN FAULTY: the context closes its descriptor and the exception handler '
                     'double-closes it, raising OSError and leaving the destination. Your new regression should FAIL on '
                     'that candidate; do not assert the broken behavior as success, weaken assertions, repair the function, '
                     'or invent a passing result. Only exact edits to the displayed complete test file are authorized. '
                     'The following verbatim candidate function is READ-ONLY reference, not an editable unit:\n\n' + function_text)
            record['review_note'] = note['id']
            view = inspect_revision(ws, prior['id'])
            if view['blockers']: raise RuntimeError(str(view['blockers']))
            selected = [u for u in view['units'] if u['path'] == 'tests/test_recommendation_cli.py' and u['unit'] == '*']
            if len(selected) != 1: raise RuntimeError('Complete project test unit missing')
            saved = save_selection(ws, prior['id'], version=view['version'],
                selections=[{k: u[k] for k in ('path', 'unit')} for u in selected],
                reason='New tests-only allocation; implementation is read-only and prior correction allocation remains parked.')
            record.update(state='prepared', selections=saved['view']['selections'], prompt_bytes_preview=saved['preview']['focused_prompt_bytes'])
            _write_json(path, record)
            router = ws.router(on_call=lambda event: (calls.append(event), ws.record_call(event)), backoff_s=())
            class OneCall:
                count = 0
                def call(self, role, **kwargs):
                    size = len(kwargs['prompt'].encode())
                    if self.count or size > record['prompt_ceiling_bytes'] or kwargs['max_tokens'] > 4000:
                        raise RuntimeError('Tests-only call/prompt/output bound exceeded')
                    self.count += 1
                    record.update(state='submitted', prompt_bytes_actual=size, request_key=kwargs['key'])
                    _write_json(path, record)
                    print(json.dumps({'state':'submitted','prompt_bytes':size,'calls_allowed':1,'tests_only':True}), flush=True)
                    return router.call(role, **kwargs)
            draft = draft_files(ws, OneCall(), 'm5', revision=prior)
            changed = [f['path'] for f in draft['files'] if f['content'] != next(o['content'] for o in prior['files'] if o['path']==f['path'])]
            record.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'), changed_files=changed,
                          tests_only_scope=changed == ['tests/test_recommendation_cli.py'])
            ws._save_draft_state(draft, 'needs_revision', review_requested_by='external-trainer',
                review_note=note['id'], diagnostic_test_candidate=True)
            record['decision'] = 'park_for_discrimination_review; no full verification or application'
        except Exception as error:
            record.update(state='refused_or_unresolved', error=type(error).__name__+': '+str(error)[:500],
                          remote_receipt=getattr(error,'remote_receipt',{}))
        record.update(finished=_now(), calls=calls, source_unchanged=collect_snapshot(ws)['digest']==source,
                      protected_unchanged=protected_ok())
        _write_json(path, record)
        ws.ledger.append('trainer.tests_only_author', {k:v for k,v in record.items() if k!='protected_sha256'})
        print(json.dumps({k:v for k,v in record.items() if k!='protected_sha256'}), flush=True)
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__': main()
