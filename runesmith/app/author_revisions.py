"""Explicit author-only revisions charged to an established ordinary allowance.

No requirement changes, fresh per-candidate budget, automatic retry, checks or
application. The normal home instance lock/Studio queue owns execution.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from runesmith.app.workspace import WorkspaceError, _read_json, _write_json, _now


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def _lineage(ws, draft):
    from runesmith.app.author_recovery import read_packet
    from runesmith.app.revision_context import candidate_identity
    scopes, seen, origins = set(), set(), []
    node = draft
    while node is not None:
        if node['id'] in seen or len(seen) >= 64:
            raise WorkspaceError('Author allowance lineage is cyclic or too deep; reconcile it first.')
        seen.add(node['id'])
        packet = read_packet(ws, node.get('author_request_key'))
        attempt_id = packet.get('attempt_id')
        if not isinstance(attempt_id, str) or not re.fullmatch(r'[0-9a-f]{32}\.json', attempt_id):
            raise WorkspaceError('No unambiguous ordinary author allowance for this lineage. No new budget granted.')
        attempt = _read_json(ws.home / 'build-attempts' / attempt_id, {})
        if (attempt.get('state') != 'answered' or attempt.get('draft') != node['id']
                or attempt.get('contract') != draft.get('contract')
                or attempt.get('snapshot_digest') != draft.get('snapshot_digest')
                or packet.get('contract') != draft.get('contract')
                or packet.get('snapshot_digest') != draft.get('snapshot_digest')
                or not isinstance(attempt.get('scope'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', attempt['scope'])):
            raise WorkspaceError('Ordinary author allowance evidence is missing, changed or unresolved.')
        scopes.add(attempt['scope']); origins.append(attempt_id)
        previous = packet.get('revision')
        if previous is None: break
        node = ws._draft(previous.get('id'))
        if candidate_identity(node) != candidate_identity(previous):
            raise WorkspaceError('An ancestor candidate changed; allowance lineage needs review.')
    from runesmith.app.author_allowance import ordinary_allowance
    budget = ordinary_allowance(ws, draft['contract'], draft['snapshot_digest'])
    if not scopes.issubset(budget['scope_aliases']):
        raise WorkspaceError('Author allowance lineage has ambiguous scopes; feedback cannot create a new allowance.')
    return dict(budget, lineage=origins)


def _inputs(ws, draft_id, instrument, *, active_job=None, own_request_key=None, recovery=False):
    from runesmith.app.acceptance_contracts import expectation_digest
    from runesmith.app.author_recovery import acceptance_identity, pending_authors
    from runesmith.app.environment_intent import require_intent
    from runesmith.app.planner import draft_prompt, milestone_contract, milestone_ready, source_context, DRAFT_SYSTEM, DRAFT_SCHEMA
    from runesmith.app.revision_context import candidate_identity, selected_view
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.work_modes import guard_job, configuration
    guard_job(ws, 'revise')
    if ws.settings()['autonomy'] == 'observe': raise WorkspaceError('Observe mode does not authorize revisions.')
    if _read_json(ws.home / 'STUDIO_STATE.json', {}).get('paused'):
        raise WorkspaceError('The workspace queue is paused.')
    marker_path = ws.home / 'STUDIO_CURRENT.json'; marker = _read_json(marker_path, None)
    if marker_path.exists() and (not isinstance(marker, dict) or not active_job
            or marker.get('id') != active_job or marker.get('kind') not in ({'revise', 'resume_author'} if recovery else {'revise'})):
        raise WorkspaceError('Finish or reconcile current/interrupted work first.')
    if any(row['key'] != own_request_key for row in pending_authors(ws)) or ws.manual_waiting():
        raise WorkspaceError('Recover the saved author/manual request before another revision.')
    parent = ws._draft(draft_id)
    if parent.get('state') != 'needs_revision': raise WorkspaceError('Select a draft that needs revision.')
    milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == parent.get('milestone')), None)
    if not milestone or not milestone_ready(ws.plan(), milestone): raise WorkspaceError('The selected milestone is not ready.')
    snapshot = collect_snapshot(ws)
    if (parent.get('snapshot_digest') != snapshot['digest']
            or parent.get('contract') != milestone_contract(ws, milestone)
            or parent.get('public_acceptance_digest') != expectation_digest(ws, milestone['id'])):
        raise WorkspaceError('Source, milestone or public requirements changed; ordinary revision is unavailable.')
    spec = ws.config().get('instruments', {}).get(instrument)
    if not isinstance(spec, dict): raise WorkspaceError('Select a configured author instrument.')
    if not isinstance(instrument, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', instrument):
        raise WorkspaceError('Instrument name is not supported by the typed job interface.')
    view = selected_view(ws, parent)
    if not view: raise WorkspaceError('Save an explicit focused revision packet first.')
    feedback = ws.planning_note_selection(milestone_id=milestone['id'], draft_id=draft_id)
    if feedback['blockers']: raise WorkspaceError('; '.join(feedback['blockers']))
    if not any(n.get('target', {}).get('type') == 'draft' and n['target'].get('id') == draft_id for n in feedback['included']):
        raise WorkspaceError('Add a draft note describing the defect and retained behavior; it must be included in the packet.')
    intent = require_intent(ws); context = source_context(ws, snapshot=snapshot, milestone=milestone)
    if context.get('focus_errors'): raise WorkspaceError('Selected source context is unavailable.')
    ignored = ()
    if own_request_key:
        from runesmith.app.author_recovery import read_packet
        # The current call's timeout receipt did not exist in its input. Keep
        # all earlier failures in the reconstructed prompt, but not itself.
        ignored = (read_packet(ws, own_request_key).get('attempt_id'),)
    prompt = draft_prompt(ws, milestone, context, revision=parent, revision_view=view, ignored_attempt_ids=ignored)
    binding = {'schema': 1, 'parent': draft_id, 'candidate': candidate_identity(parent), 'parent_metadata': _hash(parent),
        'source': snapshot['digest'], 'context': context['digest'], 'contract': parent['contract'],
        'public_acceptance': parent['public_acceptance_digest'], 'owner_bundle': acceptance_identity(ws, milestone['id']),
        'focus': _hash(view), 'feedback': _hash(feedback), 'prompt': hashlib.sha256(prompt.encode()).hexdigest(),
        'instrument': instrument, 'routing': _hash(spec), 'settings': _hash(ws.settings()),
        'modes': _hash(configuration(ws)), 'instructions': intent['instruction_digest'],
        'system': hashlib.sha256(DRAFT_SYSTEM.encode()).hexdigest(), 'answer_schema': _hash(DRAFT_SCHEMA),
        'prompt_bytes': len(prompt.encode()), 'max_output_tokens': 4000,
        'host_dispatches': 1, 'host_retries': 0, 'checks': False, 'apply': False}
    return parent, binding, view, feedback, spec


def _unresolved(ws):
    settled = {'build-attempts': {'answered', 'failed'},
               'build-corrections': {'answered', 'refused', 'candidate', 'abandoned'},
               'build-escalations': {'answered', 'failed', 'recovered'},
               'build-supplements': {'answered', 'failed'}}
    unanswered = {'transport_failed', 'context_gap'}      # no model answered, or for a file it was never shown (J11-B15)
    for folder, states in settled.items():
        for path in (ws.home / folder).glob('*.json'):
            row = _read_json(path, None)
            if not isinstance(row, dict) or row.get('state') not in states | unanswered:
                raise WorkspaceError('Reconcile unfinished or damaged author allocations first.')
    for path in (ws.home / 'build-revisions').glob('*.json'):
        row = _read_json(path, None)
        if not isinstance(row, dict) or row.get('state') not in {'reserved', 'submitted', 'uncertain', 'admitted', 'failed',
                                                                  'context_gap'}:
            raise WorkspaceError('A revision reservation is damaged; no automatic replay.')
        attempt_id = row.get('attempt_id')
        if not isinstance(attempt_id, str) or not re.fullmatch(r'[0-9a-f]{32}\.json', attempt_id):
            raise WorkspaceError('A revision attempt reference is damaged; no automatic replay.')
        attempt = _read_json(ws.home / 'build-attempts' / attempt_id, {})
        if (row.get('state') in ('reserved', 'submitted', 'uncertain')
                and attempt.get('state') not in ('answered', 'failed', 'context_gap')):
            raise WorkspaceError('A revision reservation is unresolved; recover its original receipt.')


def revision_status(ws, draft_id, instrument=None, *, active_job=None):
    instruments = [{'name': name, 'kind': spec.get('kind'), 'model': spec.get('model'),
                    'fallback_models': spec.get('fallback_models', []), 'timeout_s': spec.get('timeout_s')}
                   for name, spec in ws.config().get('instruments', {}).items() if isinstance(spec, dict)
                   and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', name)]
    planned = ws.config().get('roles', {}).get('plan', [])
    selected = instrument or (planned[0] if isinstance(planned, list) and planned else None)
    result = {'eligible': False, 'quote': None, 'blockers': [], 'instruments': instruments, 'instrument': selected,
              'scope': 'One author-only revision from the existing ordinary allowance. No new allowance, checks, apply or automatic continuation. Gateway-internal provider attempts may differ from the one host dispatch.'}
    try:
        _unresolved(ws)
        parent, binding, view, feedback, spec = _inputs(ws, draft_id, selected, active_job=active_job)
        budget = _lineage(ws, parent)
        result['allowance'] = budget
        if not budget['remaining']: raise WorkspaceError('Ordinary author allowance exhausted; no new revision budget granted.')
        quote = {'binding': binding, 'allowance': budget}
        quote['id'] = _hash(quote)
        result.update(eligible=True, quote=quote, parent=parent['id'],
            review_reason=parent.get('review_reason'),
            selections=view['selections'], feedback_included=feedback['included'], feedback_omitted=feedback['omitted'],
            prompt_bytes=binding['prompt_bytes'], limits={'host_dispatches': 1, 'host_retries': 0, 'max_output_tokens': 4000,
                                      'timeout_s': spec.get('timeout_s'), 'gateway_fallbacks': spec.get('fallback_models', [])})
    except (WorkspaceError, KeyError, ValueError, TypeError, OSError) as error:
        result['blockers'].append(str(error) or 'Revision context could not be validated.')
    return result


def validate_admission(ws, packet):
    """Apply the same revision binding to immediate and saved-ticket admission."""
    attempt_id = packet.get('attempt_id')
    if not attempt_id and not packet.get('revision_operation'): return
    if not isinstance(attempt_id, str) or not re.fullmatch(r'[0-9a-f]{32}\.json', attempt_id):
        raise WorkspaceError('Invalid author attempt reference.')
    attempt = _read_json(ws.home / 'build-attempts' / attempt_id, {})
    operation = packet.get('revision_operation') or attempt.get('revision_operation')
    if not operation: return  # Other author paths retain their existing contracts.
    if not isinstance(operation, str) or not re.fullmatch(r'[0-9a-f]{32}', operation):
        raise WorkspaceError('Invalid revision reservation reference.')
    saved = _read_json(ws.home / 'build-revisions' / (operation + '.json'), {})
    quote = saved.get('quote') or {}; binding = quote.get('binding') or {}
    if (attempt.get('revision_operation') != operation
            or saved.get('attempt_id') != attempt_id or saved.get('request_key') != packet['request_key']
            or quote.get('id') != _hash({k: v for k, v in quote.items() if k != 'id'})
            or attempt.get('scope') != (quote.get('allowance') or {}).get('scope')
            or (packet.get('revision') or {}).get('id') != binding.get('parent')):
        raise WorkspaceError('Revision reservation no longer matches the author packet.')
    marker = _read_json(ws.home / 'STUDIO_CURRENT.json', {})
    _, current, _, _, _ = _inputs(ws, binding['parent'], binding['instrument'],
        active_job=marker.get('id'), own_request_key=packet['request_key'], recovery=True)
    if current != binding:
        raise WorkspaceError('Revision inputs changed during inference; the answer is retained but not admitted.')


def _existing_operation(ws, path, signature):
    saved = _read_json(path, None)
    if not isinstance(saved, dict) or saved.get('signature') != signature:
        raise WorkspaceError('Operation ID is already bound to different or damaged revision evidence.')
    attempt_id = saved.get('attempt_id')
    if not isinstance(attempt_id, str) or not re.fullmatch(r'[0-9a-f]{32}\.json', attempt_id):
        raise WorkspaceError('Revision reservation is damaged; nothing resubmitted.')
    attempt = _read_json(ws.home / 'build-attempts' / attempt_id, {})
    state = attempt.get('state', saved.get('state', 'unknown'))
    return {'summary': 'Revision operation already recorded. Nothing resubmitted, checked or applied.',
            'already_used': True, 'operation_id': path.stem, 'state': state, 'draft': attempt.get('draft'),
            'request_key': saved.get('request_key'), 'author_only': True}


def revise_author_only(ws, draft_id, quote_id, instrument, operation_id, reason, *, checkpoint=lambda: None,
                       on_call=None, active_job=None):
    from runesmith.app.build_jobs import validate_checkpoint
    from runesmith.app.planner import draft_files
    from runesmith.config import build_router
    validate_checkpoint(checkpoint)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise WorkspaceError('Give an explicit revision authorization reason of 1–2000 characters.')
    if not isinstance(operation_id, str) or not re.fullmatch(r'[0-9a-f]{32}', operation_id):
        raise WorkspaceError('A revision operation needs a 32-character hexadecimal ID.')
    path = ws.home / 'build-revisions' / (operation_id + '.json')
    signature = _hash({'draft_id': draft_id, 'quote_id': quote_id, 'instrument': instrument, 'reason': reason})
    with ws._lock:
        if path.exists(): return _existing_operation(ws, path, signature)
        state = revision_status(ws, draft_id, instrument, active_job=active_job)
        quote = state.get('quote')
        if not state['eligible'] or not quote or quote['id'] != quote_id:
            raise WorkspaceError('Revision quote unavailable or stale. ' + '; '.join(state['blockers']))
        parent, binding, _, _, spec = _inputs(ws, draft_id, instrument, active_job=active_job)
        if binding != quote['binding']:
            raise WorkspaceError('Revision inputs changed while validating the quote; no allocation or call made.')
        router = build_router({'instruments': {instrument: spec}, 'roles': {'plan': [instrument]}},
                              home=ws.home, on_call=on_call or ws.record_call, backoff_s=())
        checkpoint()
        attempt_id = uuid.uuid4().hex + '.json'; attempt_path = ws.home / 'build-attempts' / attempt_id
        record = {'operation_id': operation_id, 'signature': signature, 'state': 'reserved', 'utc': _now(),
                  'attempt_id': attempt_id, 'quote': quote, 'parent': draft_id, 'reason': reason, 'author_only': True}
        attempt = {'scope': quote['allowance']['scope'], 'contract': binding['contract'],
                   'snapshot_digest': binding['source'], 'context_digest': binding['context'], 'state': 'started',
                   'utc': _now(), 'revision_operation': operation_id, 'parent': draft_id, 'author_only': True}
        _write_json(path, record)  # Durable intent first; a crash cannot appear as an unused operation.
        _write_json(attempt_path, attempt)
        ws.ledger.append('build.revision_reserved', {'operation': operation_id, 'attempt': attempt_id,
                         'parent': draft_id, 'scope': attempt['scope'], 'reason': reason})
    class Once:
        dispatched = False
        returned = False
        def call(self, role, **kwargs):
            checkpoint()
            if self.dispatched: raise WorkspaceError('Only one host dispatch is authorized.')
            _, current, _, _, _ = _inputs(ws, draft_id, instrument, active_job=active_job)
            if (current != binding or role != 'plan' or kwargs.get('max_tokens') != binding['max_output_tokens']
                    or hashlib.sha256(kwargs['system'].encode()).hexdigest() != binding['system']
                    or _hash(kwargs.get('schema')) != binding['answer_schema']
                    or hashlib.sha256(kwargs['prompt'].encode()).hexdigest() != binding['prompt']):
                raise WorkspaceError('Revision inputs changed before dispatch; no call sent.')
            self.dispatched = True
            record.update(state='submitted', request_key=kwargs['key'])
            attempt['request_key'] = kwargs['key']
            _write_json(path, record); _write_json(attempt_path, attempt)
            outcome = router.call(role, **kwargs)
            self.returned = True
            return outcome
    once = Once()
    try:
        revised = draft_files(ws, once, parent['milestone'], revision=parent, attempt_id=attempt_id,
                              admission_guard=checkpoint, revision_operation=operation_id)
    except BaseException as error:
        remote = getattr(error, 'remote_receipt', {})
        from runesmith.app.author_recovery import pending_authors
        uncertain = (bool(remote.get('unresolved')) or (once.dispatched and not once.returned)
                     or any(row['key'] == record.get('request_key') for row in pending_authors(ws)))
        from runesmith.app.planner import settled_state
        attempt.update(state='uncertain' if uncertain else settled_state(error), finished=_now(),
                       error=type(error).__name__ + ': ' + str(error)[:400], remote_receipt=remote)
        record.update(state=attempt['state'], finished=_now(), error=attempt['error'], remote_receipt=remote)
        _write_json(attempt_path, attempt); _write_json(path, record)
        ws.ledger.append('build.revision_ended', {'operation': operation_id, 'state': record['state'], 'error': attempt['error']})
        raise
    attempt.update(state='answered', draft=revised['id'], finished=_now())
    record.update(state='admitted', draft=revised['id'], finished=_now())
    _write_json(attempt_path, attempt); _write_json(path, record)
    ws.ledger.append('build.revision_ended', {'operation': operation_id, 'state': 'admitted', 'draft': revised['id']})
    return {'summary': f"Revision {revised['id']} saved unverified. No checks, apply, milestone advance or automatic continuation.",
            'draft': revised['id'], 'milestone': parent['milestone'], 'operation_id': operation_id,
            'parent': draft_id, 'author_only': True, 'advanced': False}
