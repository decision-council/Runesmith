"""One explicit development allocation using a preserved model-authored regression.

Uses Runesmith's existing focused-revision API, not a new retry entitlement.
The shared build runner is used separately for checks; it has no explicit
author-only revision job yet. No Hat implementation is authored by this script.
"""
from pathlib import Path
import ast
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.environment_intent import require_intent
from runesmith.app.planner import draft_files
from runesmith.app.revision_context import inspect_revision, save_selection
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.work_modes import guard_job, checkpoint
from runesmith.app.workspace import Workspace, _read_json, _write_json, _now
from revise_growth_m5_focused_units_20260926 import ROUTES


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'
    home = root / '.runesmith'
    out = home / 'trainer-trials/gemini-m5-regression-driven-fix-20260927.json'
    lock = InstanceLock(home)
    if not lock.acquire():
        raise RuntimeError('Another home writer exists; use its queue.')
    try:
        if out.exists():
            print(json.dumps({'already_started': True, 'state': _read_json(out, {}).get('state')})); return
        if _existing(home) or (home / 'STUDIO_CURRENT.json').exists():
            raise RuntimeError('Resident/current/interrupted work must be reconciled first.')
        if _read_json(home / 'STUDIO_STATE.json', {}).get('paused'):
            raise RuntimeError('Queue is paused.')
        ws = Workspace(root, home)
        if pending_authors(ws) or ws.manual_waiting():
            raise RuntimeError('Saved remote/manual work must be reconciled first.')
        guard_job(ws, 'build'); checkpoint(ws); require_intent(ws)
        if ws.settings()['autonomy'] == 'observe':
            raise RuntimeError('Observe mode does not authorize authoring.')
        diagnosis = _read_json(home / 'trainer-trials/gemini-m5-tests-delivered-assessment-20260927.json', {})
        delivered = _read_json(home / 'trainer-trials/gemini-m5-tests-delivered-20260927.json', {})
        old = _read_json(home / 'trainer-trials/gemini-m5-tests-only-20260927.json', {})
        prior = ws._draft('d20260926232339d644')
        if (diagnosis.get('state') != 'completed' or not diagnosis.get('detected_known_defect')
                or diagnosis.get('draft') != prior['id'] or prior['state'] != 'needs_revision'
                or prior.get('verification') or delivered.get('state') != 'admitted'
                or len(delivered.get('calls', [])) != 1
                or delivered['calls'][0].get('remote_state') != 'terminal'):
            raise RuntimeError('The preserved, terminal author result and red regression are required.')
        source = collect_snapshot(ws)['digest']
        public = expectation_digest(ws, 'm5')
        if source != delivered['source_digest'] or public != delivered['public_acceptance_digest']:
            raise RuntimeError('Source or public acceptance changed.')
        protected = dict(old['protected_sha256'])
        for folder in ('drafts', 'build-attempts', 'build-corrections', 'build-escalations',
                       'build-supplements', 'build-check-resumes', 'build-check-allocations'):
            for p in (home / folder).rglob('*.json'):
                protected[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (home / 'BUILD_GRANT.json', home / 'PLAN.json'):
            if p.is_file(): protected[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        def intact():
            return all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
                       for p, sha in protected.items())
        if not intact(): raise RuntimeError('Historical or acceptance evidence changed.')
        config = ws.config(); spec = config['instruments']['author']
        if config['roles']['plan'] != ['author'] or [spec['model']] + spec.get('fallback_models', []) != ROUTES:
            raise RuntimeError('The reviewed free-only routes changed.')
        code = next(f['content'] for f in prior['files'] if f['path'] == 'tests/test_recommendation_cli.py')
        node = next(n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.FunctionDef)
                    and n.name == 'test_export_serialization_error_cleanup')
        task = (
            'NEW IMPLEMENTATION-ONLY DEVELOPMENT TASK: the previous tests-only task is complete. '
            'Keep every test and all other candidate files byte-for-byte unchanged. Correct only the '
            'displayed cmd_export_recommendations function so the preserved model-authored regression '
            'below passes. Its actual recorded run currently raises Bad file descriptor after JSON '
            'serialization fails, and leaves the new destination. Required behavior: return 1 without '
            'escaping exceptions, close resources without double-close or leaks, and remove a destination '
            'created by this failed export. Preserve atomic no-clobber behavior: an existing or racing '
            'competitor file must remain unchanged, and export-data failure must create no destination. '
            'No test weakening, edits outside the displayed function, or invented test result. The test '
            'below is read-only observed project evidence, not private owner acceptance:\n\n'
            + ast.get_source_segment(code, node))
        record = {'state': 'preparing', 'utc': _now(), 'prior_draft': prior['id'], 'milestone': 'm5',
            'source_digest': source, 'public_acceptance_digest': public, 'protected_sha256': protected,
            'gateway_job_limit': 1, 'router_retry': False, 'paid_fallback': False, 'configured_routes': ROUTES,
            'prompt_ceiling_bytes': 48000, 'max_output_tokens': 4000, 'project_checks': False,
            'owner_checks': False, 'apply': False,
            'authorization': 'Continuing owner-authorized field training: one separately journaled implementation-only allocation after the admitted regression demonstrated a defect. No old counter or receipt reset.',
            'trainer_assistance': 'Select exact function, supply observed failure and read-only instrument-authored test. Instrument authors all Hat code.',
            'runtime_path': 'Existing explicit draft_files revision API under home lock; no shared author-only revision job is available. Subsequent checks use shared one-shot runner.',
            'stop_rule': 'One terminal/refused/uncertain author outcome, then separate review; no automatic retry, checks or application.'}
        _write_json(out, record); calls = []
        try:
            note = ws.notes.add(target_type='draft', target_id=prior['id'], target_label=prior['title'],
                                author='external-trainer', text=task)
            record['review_note'] = note['id']
            info = inspect_revision(ws, prior['id'])
            if info['blockers']: raise RuntimeError(str(info['blockers']))
            units = [u for u in info['units'] if u['path'] == 'growthhat/cli.py'
                     and u['label'] == 'cmd_export_recommendations']
            if len(units) != 1: raise RuntimeError('Exact function is unavailable.')
            info = save_selection(ws, prior['id'], version=info['version'],
                selections=[{k: units[0][k] for k in ('path', 'unit')}],
                reason='Implementation-only correction driven by the preserved free-authored failing regression; no test edits.')
            prompt = info['preview']['prompt']
            if task not in prompt or len(prompt.encode()) > record['prompt_ceiling_bytes']:
                raise RuntimeError('Complete task delivery or packet ceiling failed before submission.')
            record.update(state='prepared', preview_bytes=len(prompt.encode()),
                          selections=info['view']['selections'], feedback_delivery=info['feedback'])
            _write_json(out, record)
            router = ws.router(on_call=lambda event: (calls.append(event), ws.record_call(event)), backoff_s=())
            class Once:
                count = 0
                def call(self, role, **kwargs):
                    guard_job(ws, 'build'); checkpoint(ws)
                    sent = kwargs['prompt']
                    if (self.count or task not in sent or len(sent.encode()) > record['prompt_ceiling_bytes']
                            or kwargs['max_tokens'] > 4000 or not intact()):
                        raise RuntimeError('One-call/task/custody bound failed before dispatch.')
                    self.count += 1
                    record.update(state='submitted', request_key=kwargs['key'], actual_prompt_bytes=len(sent.encode()),
                                  actual_prompt_sha256=hashlib.sha256(sent.encode()).hexdigest(), complete_task_delivered=True)
                    _write_json(out, record)
                    print(json.dumps({'state': 'submitted', 'prompt_bytes': len(sent.encode()), 'free_only': True}), flush=True)
                    return router.call(role, **kwargs)
            draft = draft_files(ws, Once(), 'm5', revision=prior)
            changed = [f['path'] for f in draft['files']
                       if f['content'] != next(p['content'] for p in prior['files'] if p['path'] == f['path'])]
            record.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'), changed_files=changed)
        except Exception as error:
            record.update(state='refused_or_unresolved', error=type(error).__name__ + ': ' + str(error)[:500],
                          remote_receipt=getattr(error, 'remote_receipt', {}))
        record.update(finished=_now(), calls=calls, source_unchanged=collect_snapshot(ws)['digest'] == source,
                      protected_unchanged=intact())
        _write_json(out, record)
        ws.ledger.append('trainer.regression_driven_author', {k: v for k, v in record.items()
                         if k not in ('protected_sha256', 'feedback_delivery')})
        print(json.dumps({k: v for k, v in record.items() if k not in ('protected_sha256', 'feedback_delivery')}), flush=True)
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__':
    main()
