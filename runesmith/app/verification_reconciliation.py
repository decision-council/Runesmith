"""One linked, recheck-only exception for a positively identified preflight refusal.

This is not a timeout extension or a budget reset. Legacy evidence is explicitly
labelled as an adjudication of the old rejection path, not phase instrumentation.
The Studio worker (or an operator holding its per-home OS lock) owns execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from runesmith.app import building
from runesmith.app.acceptance_contracts import expectation_digest, expectations
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import milestone_contract, milestone_ready
from runesmith.app.snapshots import collect_snapshot, digest_files, SnapshotUnsupported
from runesmith.app.verification_allocation import _digest
from runesmith.app.work_modes import configuration, guard_job
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.ledger import Ledger

LEGACY_REFUSAL = {'status': 'stale', 'detail': 'Source changed since the author read it.'}


def _require(condition, message):
    if not condition:
        raise WorkspaceError(message)


def _parent(ws, draft):
    value = _read_json(ws.home / 'build-check-allocations' / (draft['id'] + '.json'), {})
    _require(isinstance(value, dict) and re.fullmatch('[a-f0-9]{64}', str(value.get('id', ''))),
             'The original allocation is missing or unreadable; no replacement is available.')
    return value


def _path(ws, parent):
    return ws.home / 'build-check-reconciliations' / (parent['id'] + '.json')


def _runtime_binding():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(building.__file__))}


def _bindings(ws, draft, parent, *, active_job=None):
    settings = ws.settings()
    grant = building.status(ws)
    _require(settings['autonomy'] != 'observe' and grant['enabled'], 'Executable checks are off.')
    guard_job(ws, 'reconcile_check')
    current_path = ws.home / 'STUDIO_CURRENT.json'
    current = _read_json(current_path, None)
    _require(not current_path.exists() or (active_job and isinstance(current, dict) and
             current.get('id') == active_job and current.get('kind') == 'reconcile_check' and
             current.get('params', {}).get('draft_id') == draft['id']),
             'Another or interrupted worker needs reconciliation first.')
    _require(not (ws.home / 'SOURCE_BASELINE_PENDING.json').exists() and
             not pending_authors(ws) and not ws.manual_waiting(),
             'An unresolved author, relay or source measurement needs attention first.')
    for path in (ws.home / 'build-attempts').glob('*.json'):
        row = _read_json(path, None)
        _require(isinstance(row, dict) and row.get('state') not in ('started', 'uncertain'),
                 'An interrupted or unreadable author attempt needs attention first.')
    plan = ws.plan() or {}
    milestone = next((m for m in plan.get('milestones', []) if m['id'] == draft.get('milestone')), None)
    _require(milestone and milestone_ready(plan, milestone), 'The retained milestone is no longer ready.')
    snapshot = collect_snapshot(ws)
    author = building.author_context_status(ws, draft, snapshot)
    candidate = digest_files(building._candidate_files(snapshot, draft),
                             snapshot['policy'].get('declared_documents', []))['digest']
    contract = milestone_contract(ws, milestone)
    bundle, public = {}, {}
    for item in plan['milestones']:
        path = ws.home / 'acceptance' / (item['id'] + '.py')
        if (item['id'] == milestone['id'] or item.get('status') == 'done') and path.is_file():
            bundle[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            value = expectations(ws, item['id'])
            if value:
                public[item['id']] = value['digest']
    _require(author['ok'] and snapshot['digest'] == draft.get('snapshot_digest') == parent['snapshot_digest'] and
             candidate == parent['candidate_digest'] and contract == draft.get('contract') == parent['contract'] and
             expectation_digest(ws, milestone['id']) == draft.get('public_acceptance_digest') == parent['public_acceptance_digest'] and
             bundle == parent['acceptance_bundle'] and public == parent['public_contracts'] and
             milestone['id'] + '.py' in bundle,
             'Source, candidate, original author view, criteria or owner bundle changed.')
    return {'snapshot_digest': snapshot['digest'], 'candidate_digest': candidate,
            'contract': contract, 'milestone': milestone['id'], 'author_context': author,
            'acceptance_bundle': bundle, 'public_contracts': public,
            'authority': {'autonomy': settings['autonomy'], 'checks_enabled': grant['enabled'],
                          'grant': grant['grant'], 'paths': grant['paths'], 'apply_grant': grant['apply'],
                          'mode_revision': configuration(ws)['revision']},
            'runtime_binding': _runtime_binding()}


def _legacy_evidence(ws, draft, parent):
    _require(parent.get('policy') == 'baseline_resource_quote_v1' and
             parent.get('draft') == draft['id'] and parent.get('state') == 'completed' and
             parent.get('outcome') == 'stale' and parent.get('elapsed_check_s') == 0 and
             parent.get('advanced') is False and parent.get('evidence_dir') is None and
             draft.get('state') == 'waiting' and draft.get('verification') == LEGACY_REFUSAL,
             'Only the specifically identified pre-execution author-view refusal is eligible; zero time alone is insufficient.')
    _require(all(type(parent.get(k)) is int for k in ('project_timeout_s', 'owner_timeout_s', 'maximum_check_s')) and
             1 <= parent['project_timeout_s'] <= 600 and 1 <= parent['owner_timeout_s'] <= building.OWNER_LIMIT_S and
             parent['maximum_check_s'] == parent['project_timeout_s'] + parent['owner_timeout_s'] and
             parent.get('max_phases') == 2 and parent.get('author_budget_reset') is False,
             'The original resource limits are not valid.')
    ledger = object.__new__(Ledger)
    ledger.path = ws.home / 'ledger.jsonl'
    _require(ledger.verify()['ok'], 'Ledger integrity is unavailable.')
    records = list(ledger)
    starts = [r for r in records if r['kind'] == 'build.check_allocation_started' and r['data'].get('id') == parent['id']]
    ends = [r for r in records if r['kind'] == 'build.check_allocation_completed' and r['data'].get('id') == parent['id']]
    _require(len(starts) == len(ends) == 1 and ends[0]['data'] == parent and starts[0]['seq'] < ends[0]['seq'],
             'Original started/completed allocation receipts do not agree with the ledger.')
    start, end = starts[0], ends[0]
    original_quote = {k: v for k, v in start['data'].items() if k not in ('id', 'state', 'started', 'reason')}
    _require(_digest(original_quote) == parent['id'] and all(parent.get(k) == v for k, v in original_quote.items()),
             'The original allocation quote was modified.')
    middle = [r for r in records if start['seq'] < r['seq'] < end['seq']]
    _require(len(middle) == 2 and middle[0]['kind'] == 'build.checked' and
             middle[0]['data'].get('draft') == draft['id'] and middle[0]['data'].get('status') == 'stale' and
             middle[1]['kind'] == 'build.remembered' and middle[1]['data'].get('draft') == draft['id'],
             'The old interval includes unknown or conflicting execution evidence.')
    _require(not any(r['seq'] > end['seq'] and r['data'].get('draft') == draft['id'] and
                     r['kind'] in ('build.checked', 'build.advanced') for r in records),
             'A later check or application supersedes the old preflight failure.')
    history = draft.get('verification_history', [])
    _require(history and history == parent.get('prior_history') and parent.get('prior_evidence') == history[-1],
             'Retained verification history changed.')
    runs = ws.home / 'build-runs' / draft['id']
    _require({p.relative_to(ws.home).as_posix() for p in runs.iterdir()} == set(history),
             'An unaccounted verification run exists; its outcome must be reconciled first.')
    receipts = {}
    for rel in history:
        _require(re.fullmatch(r'build-runs/' + re.escape(draft['id']) + r'/v-[a-f0-9]{12}', rel), 'Invalid prior evidence path.')
        path = ws.home / rel / 'VERIFICATION.json'
        prior = _read_json(path, {})
        _require(prior.get('status') == 'inconclusive' and prior.get('snapshot_digest') == parent['snapshot_digest'] and
                 prior.get('candidate_digest') == parent['candidate_digest'] and
                 (prior.get('project_checks') or {}).get('status') == 'timeout' and not prior.get('acceptance'),
                 'Prior outcomes do not match the retained timeouts.')
        receipts[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    resumed = _read_json(ws.home / 'build-check-resumes' / (draft['id'] + '.json'), {})
    baseline = _read_json(ws.home / 'source-baseline-runs' / parent['snapshot_digest'] / 'BASELINE.json', {})
    _require(_digest(resumed) == parent['spent_continuation_digest'] and
             _digest(baseline) == parent['baseline_receipt_digest'] and
             baseline.get('runner_sha256') == hashlib.sha256(building.RUNNER.encode()).hexdigest(),
             'Original continuation, baseline or runner changed.')
    return {'basis': 'legacy_rejection_path_adjudication', 'phase_instrumentation': False,
            'detail': 'Specific legacy author-view refusal, ledger-confirmed completion, unchanged run inventory and prior inputs; not inferred from zero elapsed time alone.',
            'ledger_start': start['hash'], 'ledger_end': end['hash'], 'prior_receipt_sha256': receipts,
            'baseline_digest': _digest(baseline), 'continuation_digest': _digest(resumed),
            'old_verification': draft['verification']}


def reconciliation_status(ws, draft, *, active_job=None):
    result = {'eligible': False, 'used': False, 'receipt': None, 'quote': None}
    try:
        parent = _parent(ws, draft)
        path = _path(ws, parent)
        if path.exists():
            value = _read_json(path, None)
            if not isinstance(value, dict) or not value.get('id') or value.get('parent_allocation') != parent['id'] or not value.get('state'):
                value = {'state': 'unresolved', 'outcome': 'unknown', 'detail': 'Unreadable replacement receipt; never replay it.'}
            return result | {'used': True, 'receipt': value}
        evidence = _legacy_evidence(ws, draft, parent)
        bindings = _bindings(ws, draft, parent, active_job=active_job)
        quote = {'schema': 1, 'policy': 'preflight_reconciliation_v1', 'draft': draft['id'],
                 'parent_allocation': parent['id'], 'parent_receipt_digest': _digest(parent),
                 'parent_receipt_sha256': hashlib.sha256((ws.home / 'build-check-allocations' / (draft['id'] + '.json')).read_bytes()).hexdigest(),
                 'bindings': bindings, 'evidence': evidence,
                 'project_timeout_s': parent['project_timeout_s'], 'owner_timeout_s': parent['owner_timeout_s'],
                 'maximum_check_s': parent['maximum_check_s'], 'max_phases': 2,
                 'inference_calls': 0, 'author_budget_reset': False, 'apply_permitted': False,
                 'scope': 'One explicit linked recheck only. All phases run anew. No automatic apply, replay or further reconciliation.'}
        quote['id'] = _digest(quote)
        return result | {'eligible': True, 'quote': quote}
    except (WorkspaceError, SnapshotUnsupported, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        return result | {'detail': str(error)[:400]}


def reconcile_verification(ws, draft_id, quote_id, reason, *, checkpoint=lambda: None, active_job=None):
    _require(isinstance(reason, str) and reason.strip(), 'Explain the linked preflight reconciliation.')
    with ws._lock:
        checkpoint()
        draft = ws._draft(draft_id)
        status = reconciliation_status(ws, draft, active_job=active_job)
        if status['used']:
            return {'summary': 'The linked replacement is already reserved. Nothing rerun.', 'draft': draft_id,
                    'already_used': True, 'reconciliation': status['receipt'].get('id')}
        quote = status.get('quote')
        _require(status['eligible'] and quote and quote['id'] == quote_id,
                 'Reconciliation quote is unavailable or stale; no checks started. ' + status.get('detail', ''))
        parent = _parent(ws, draft)
        path = _path(ws, parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt = dict(quote, state='started', started=_now(), reason=reason.strip()[:2000])
        try:
            # Exclusive claim prevents even distinct Workspace objects dispatching twice.
            with path.open('x', encoding='utf-8') as stream:
                json.dump(receipt, stream, ensure_ascii=True, indent=1)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            return {'summary': 'Another request reserved the replacement. Nothing rerun.', 'draft': draft_id, 'already_used': True}
        ws.ledger.append('build.check_reconciliation_started', receipt)
    def phase_checkpoint():
        checkpoint()
        with ws._lock:
            _require(_parent(ws, draft) == parent, 'Original allocation changed during the recheck.')
            _require(_bindings(ws, ws._draft(draft_id), parent, active_job=active_job) == quote['bindings'],
                     'Verification inputs or authority changed; no subsequent phase will start.')
    try:
        milestone = next(m for m in ws.plan()['milestones'] if m['id'] == quote['bindings']['milestone'])
        result = building._check_and_record(ws, draft, milestone, quote['bindings']['contract'],
            checkpoint=phase_checkpoint, allow_apply=False,
            project_timeout_s=quote['project_timeout_s'], owner_timeout_s=quote['owner_timeout_s'],
            phase_checkpoint=phase_checkpoint)
    except BaseException as error:
        receipt.update(state='interrupted', finished=_now(), outcome='unknown', error=type(error).__name__)
        _write_json(path, receipt)
        ws.ledger.append('build.check_reconciliation_interrupted', {'id': receipt['id'], 'error': type(error).__name__})
        raise
    verification = result.get('verification') or {}
    receipt.update(state='completed', finished=_now(), outcome=verification.get('status', 'not_run'),
                   evidence_dir=verification.get('evidence_dir'), advanced=False,
                   elapsed_check_s=sum((verification.get(k) or {}).get('elapsed_s', 0) for k in ('project_checks', 'acceptance')))
    _write_json(path, receipt)
    ws.ledger.append('build.check_reconciliation_completed', receipt)
    result['reconciliation'] = receipt['id']
    return result
