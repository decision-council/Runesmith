"""One synchronous build-job entry point for the Studio worker and trainers.

Callers own the per-home instance lock (or use the resident Studio queue). This
dispatcher never starts a server, resets an allocation or adds a retry policy.
Each existing operation retains its own routing, receipts, limits and guards.
Rendered model prompts stay opaque; this interface accepts job parameters, not
JSON extracted from a prompt with appended documents or operator notes.
"""
from __future__ import annotations

from dataclasses import dataclass
from inspect import iscoroutinefunction, signature
from types import MappingProxyType
from typing import Any, Callable, Mapping

from runesmith.app.workspace import WorkspaceError


# Parameter names are also used by queue admission. None means an optional ID.
PARAMETERS = {
    'build': {'draft_id': None, 'author_only': False, 'milestone_id': None},
    'supplement': {'draft_id': str, 'reason': str, 'instrument': str, 'author_only': False},
    'revise': {'draft_id': str, 'quote_id': str, 'instrument': str, 'operation_id': str, 'reason': str},
    'correct': {'attempt': str},
    'readmit': {'escalation': str},
    'readmit_answer': {'attempt': str},
    'escalate': {'milestone_id': None},
    'review_current': {'milestone': str},
    'resume_check': {'draft_id': str, 'reason': str},
    'allocate_check': {'draft_id': str, 'quote_id': str, 'reason': str},
    'reconcile_check': {'draft_id': str, 'quote_id': str, 'reason': str},
    'resume_author': {'request_id': str},
    'source_baseline': {'reason': str},
}
AUTHOR_JOBS = frozenset({'build', 'supplement', 'correct', 'escalate', 'revise'})


def validate_checkpoint(callback: Callable[[], None], name='checkpoint') -> None:
    """Reject bad hook signatures before a job can consume a durable allocation."""
    try:
        if not callable(callback) or iscoroutinefunction(callback) or iscoroutinefunction(getattr(callback, '__call__', None)):
            raise TypeError()
        signature(callback).bind()
    except (TypeError, ValueError):
        raise WorkspaceError(f'{name} must be a synchronous callable accepting no arguments.') from None


@dataclass(frozen=True)
class BuildJob:
    kind: str
    params: Mapping[str, Any]

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in PARAMETERS or not isinstance(self.params, Mapping):
            raise WorkspaceError('Unknown build job or invalid parameters.')
        schema = PARAMETERS[self.kind]
        if set(self.params) - set(schema):
            raise WorkspaceError('Unexpected build-job parameters; use the declared interface.')
        clean = {}
        for name, rule in schema.items():
            value = self.params.get(name, rule if rule is not str else None)
            if name == 'author_only':
                if type(value) is not bool:
                    raise WorkspaceError('Author-only selection must be boolean.')
            elif value is None and rule is None:
                pass
            elif not isinstance(value, str) or not value.strip():
                raise WorkspaceError(f'{name} must be nonempty text.')
            elif name == 'reason':
                if len(value) > 2000:
                    raise WorkspaceError('A build-job reason must be at most 2000 characters.')
            elif value in {'.', '..'} or len(value) > 128 or any(not (c.isascii() and (c.isalnum() or c in '._-')) for c in value):
                raise WorkspaceError(f'{name} is not a valid local identifier.')
            clean[name] = value
        if self.kind == 'build' and clean['author_only'] and clean['draft_id'] is not None:
            raise WorkspaceError('Choose author-only acquisition or a saved-candidate check, not both.')
        if self.kind == 'build' and clean['milestone_id'] is not None and clean['draft_id'] is not None:
            raise WorkspaceError('Choose a milestone to build or a saved candidate to check, not both.')
        object.__setattr__(self, 'params', MappingProxyType(clean))


def execute_build_job(ws, job: BuildJob, *, checkpoint=lambda: None, on_call=None, active_job=None):
    """Run one validated operation, with no implicit new retries or grants.

    `checkpoint` is always zero-argument, including between test phases. Model
    call accounting uses the same callback as Studio; synchronous callers default
    to the workspace ledger. Check-only jobs never even construct a model router.
    """
    if not isinstance(job, BuildJob):
        raise WorkspaceError('Use a validated BuildJob request.')
    validate_checkpoint(checkpoint)
    if on_call is not None:
        try:
            if not callable(on_call) or iscoroutinefunction(on_call) or iscoroutinefunction(getattr(on_call, '__call__', None)):
                raise TypeError()
            signature(on_call).bind({})
        except (TypeError, ValueError):
            raise WorkspaceError('The call recorder must accept one event synchronously.') from None
    from runesmith.app import building
    from runesmith.app.work_modes import guard_job, checkpoint as mode_checkpoint

    def guarded():
        checkpoint()
        guard_job(ws, job.kind)
        mode_checkpoint(ws)

    guarded()
    if job.kind in AUTHOR_JOBS:
        from runesmith.app.environment_intent import require_intent
        require_intent(ws)
    p = dict(job.params)
    call_recorder = on_call if on_call is not None else ws.record_call
    if job.kind == 'build':
        if p['draft_id'] is not None:
            return building.recheck_draft(ws, p['draft_id'], checkpoint=guarded)
        options = {'author_only': True} if p['author_only'] else {}
        if p['milestone_id'] is not None:
            options['milestone_id'] = p['milestone_id']
        return building.build_step(ws, ws.router(on_call=call_recorder, backoff_s=() if p['author_only'] else (5, 20)),
                                   checkpoint=guarded, **options)
    if job.kind == 'supplement':
        from runesmith.config import build_router
        instrument = p.pop('instrument')
        spec = ws.config().get('instruments', {}).get(instrument)
        if not spec:
            raise WorkspaceError('Select a configured author instrument.')
        router = build_router({'instruments': {instrument: spec}, 'roles': {'plan': [instrument]}},
                              home=ws.home, on_call=call_recorder, backoff_s=())
        return building.supplement_build(ws, router, **p, checkpoint=guarded)
    if job.kind == 'revise':
        from runesmith.app.author_revisions import revise_author_only
        return revise_author_only(ws, **p, checkpoint=guarded, on_call=call_recorder, active_job=active_job)
    if job.kind == 'correct':
        return building.correct_refusal(ws, ws.router(on_call=call_recorder, backoff_s=(5, 20)),
                                        p['attempt'], checkpoint=guarded)
    if job.kind == 'readmit_answer':
        return building.readmit_refused_answer(ws, p['attempt'], checkpoint=guarded)
    if job.kind == 'readmit':
        return building.readmit_escalation_answer(ws, p['escalation'], checkpoint=guarded)
    if job.kind == 'escalate':
        return building.escalate_build(ws, ws.router(on_call=call_recorder, backoff_s=(5, 20)), checkpoint=guarded,
                                       milestone_id=p['milestone_id'])
    if job.kind == 'review_current':
        return building.review_current_files(ws, p['milestone'], checkpoint=guarded)
    if job.kind == 'resume_check':
        from runesmith.app.verification_resume import resume_verification
        return resume_verification(ws, p['draft_id'], p['reason'], checkpoint=guarded)
    if job.kind == 'allocate_check':
        from runesmith.app.verification_allocation import allocate_verification
        return allocate_verification(ws, p['draft_id'], p['quote_id'], p['reason'], checkpoint=guarded)
    if job.kind == 'reconcile_check':
        from runesmith.app.verification_reconciliation import reconcile_verification
        return reconcile_verification(ws, p['draft_id'], p['quote_id'], p['reason'],
                                      checkpoint=guarded, active_job=active_job)
    if job.kind == 'resume_author':
        from runesmith.app.author_recovery import resume_author
        return resume_author(ws, p['request_id'], checkpoint=guarded)
    if job.kind == 'source_baseline':
        from runesmith.app.source_baseline import measure_current_source
        return measure_current_source(ws, p['reason'], checkpoint=guarded)
    raise WorkspaceError('Unsupported build job.')


def run_synchronous_build_job(root, job: BuildJob, *, home=None):
    """Execute exactly one normal Worker job without starting a server/thread.

    This is the supported trainer path when no resident Studio owns the home.
    It takes the OS instance lock before Workspace initialization, preserves the
    normal job history and call ledger, honors pause, and never schedules the
    next milestone. A current/interrupted job must be reconciled, not replaced.
    """
    from pathlib import Path
    import uuid
    from runesmith.app.server import InstanceLock, _existing, STUDIO_DIR
    from runesmith.app.workspace_ownership import Bindings
    from runesmith.app.worker import Worker, EventBus
    from runesmith.app.workspace import Workspace, _now, _read_json
    if not isinstance(job, BuildJob):
        raise WorkspaceError('Use a validated BuildJob request.')
    root = Path(root).resolve()
    home = Path(Bindings(STUDIO_DIR).resolve(root, home)['home'])
    if not home.is_dir():
        raise WorkspaceError('Initialize and configure this workspace before running a synchronous build job.')
    lock = InstanceLock(home, root=root)
    if not lock.acquire():
        raise WorkspaceError('This home has another writer. Use its Studio API/job queue.')
    try:
        if _existing(home):
            raise WorkspaceError('A resident Studio owns this home. Use its API/job queue.')
        if (home / 'STUDIO_CURRENT.json').exists():
            raise WorkspaceError('A current or interrupted job requires reconciliation; nothing replayed.')
        from runesmith.app.worker_journal import Record, validate_queue
        state = Record(home / 'STUDIO_STATE.json').value
        if state is not None and (not isinstance(state, dict) or
                                 ('paused' in state and type(state['paused']) is not bool)):
            raise WorkspaceError('Invalid Studio control state; recovery review is required.')
        if state and state.get('paused'):
            raise WorkspaceError('The workspace queue is paused. Resume it explicitly before running a job.')
        queued, recovery = validate_queue(Record(home / 'STUDIO_QUEUE.json').value, root)
        if queued or recovery:
            raise WorkspaceError('Retained queue or recovery state needs Studio review; no synchronous job started.')
        Bindings(STUDIO_DIR).remember(root, home)
        ws = Workspace(root, home)
        worker = Worker(ws, EventBus())
        if worker.paused or worker.snapshot()['recovery'] or worker.snapshot()['queue']:
            raise WorkspaceError('Retained queue or recovery state needs Studio review; no synchronous job started.')
        if ws.manual_waiting():
            raise WorkspaceError('A manual model request needs review before starting another synchronous job.')
        return worker._execute({'id': uuid.uuid4().hex[:8], 'kind': job.kind, 'params': dict(job.params),
                                'queued': _now(), 'by': 'synchronous_caller'}, schedule_next=False)
    finally:
        lock.close()
