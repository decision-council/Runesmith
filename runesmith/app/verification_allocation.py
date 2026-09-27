"""A prospective, baseline-informed resource quote; never an automatic extension.

One additional reservation per retained draft, after its original continuation
completed inconclusively. All candidate and owner checks still run from scratch.
The normal Studio worker / per-home instance lock owns execution.
"""
from __future__ import annotations

import hashlib
import json
import math

from runesmith.app import building
from runesmith.app.acceptance_contracts import expectations, expectation_digest
from runesmith.app.planner import milestone_contract, milestone_ready
from runesmith.app.snapshots import collect_snapshot, digest_files, SnapshotUnsupported
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def allocation_status(ws, draft):
    path = ws.home / 'build-check-allocations' / (draft['id'] + '.json')
    used = path.exists()
    receipt = _read_json(path, None)
    if used and (not isinstance(receipt, dict) or not receipt.get('id') or not receipt.get('state')):
        # A corrupt/interrupted reservation is not an unused budget. Preserve
        # its bytes for reconciliation; do not silently grant another attempt.
        receipt = {'id': 'unresolved-' + draft['id'], 'state': 'unresolved', 'outcome': 'unknown',
                   'detail': 'The existing allocation receipt cannot be validated. No automatic replay.'}
    result = {'eligible': False, 'used': used, 'receipt': receipt, 'quote': None}
    if used:
        return result
    if ws.settings()['autonomy'] == 'observe' or not building.status(ws)['enabled']:
        return result
    prior = draft.get('verification') or {}
    if (draft.get('state') != 'waiting' or prior.get('status') != 'inconclusive' or
            (prior.get('project_checks') or {}).get('status') != 'timeout' or prior.get('acceptance')):
        return result
    resumed = _read_json(ws.home / 'build-check-resumes' / (draft['id'] + '.json'), {})
    if resumed.get('state') != 'completed' or resumed.get('outcome') != 'inconclusive':
        return result | {'detail': 'Use or reconcile the original check continuation first.'}
    if (ws.home / 'SOURCE_BASELINE_PENDING.json').exists():
        return result | {'detail': 'The source measurement is still active or unresolved.'}
    try:
        snapshot = collect_snapshot(ws)
        baseline_path = ws.home / 'source-baseline-runs' / snapshot['digest'] / 'BASELINE.json'
        baseline = _read_json(baseline_path, {})
        measured = baseline.get('project_checks') or {}
        inventory = baseline.get('inventory') or {}
        elapsed = measured.get('elapsed_s')
        if (baseline.get('state') != 'completed' or baseline.get('outcome') != 'measured' or
                baseline.get('snapshot_digest') != snapshot['digest'] or not baseline.get('source_still_current') or
                baseline.get('stage_inputs_changed') or not measured.get('ok') or measured.get('status') != 'passed' or
                not inventory.get('complete') or type(measured.get('ran')) is not int or
                measured['ran'] <= measured.get('skipped', 0) or inventory.get('count') != measured['ran'] or
                baseline.get('runner_sha256') != hashlib.sha256(building.RUNNER.encode()).hexdigest() or
                type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 < elapsed <= 240):
            return result | {'detail': 'Measure the unchanged current-source suite successfully before quoting a budget.'}
        plan = ws.plan() or {}
        milestone = next((m for m in plan.get('milestones', []) if m['id'] == draft.get('milestone')), None)
        if not milestone or not milestone_ready(plan, milestone):
            return result | {'detail': 'The candidate milestone is not ready.'}
        contract = milestone_contract(ws, milestone)
        author_context = building.author_context_status(ws, draft, snapshot)
        if not author_context['ok']:
            return result | {'detail': 'The retained author view is stale; reconcile it before reserving resources.'}
        candidate_digest = digest_files(building._candidate_files(snapshot, draft),
                                       snapshot['policy'].get('declared_documents', []))['digest']
        bundle, public = {}, {}
        for item in plan['milestones']:
            path = ws.home / 'acceptance' / (item['id'] + '.py')
            if (item['id'] == milestone['id'] or item.get('status') == 'done') and path.is_file():
                bundle[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                value = expectations(ws, item['id'])
                if value:public[item['id']] = value['digest']
        unchanged = (snapshot['digest'] == draft.get('snapshot_digest') and
            contract == draft.get('contract') and candidate_digest == prior.get('candidate_digest') and
            expectation_digest(ws, milestone['id']) == draft.get('public_acceptance_digest') and
            public == {c['milestone']: c['digest'] for c in prior.get('public_contracts', [])} and
            bundle == prior.get('acceptance_bundle') and milestone['id'] + '.py' in bundle)
        if not unchanged:
            return result | {'detail': 'Candidate, source, milestone or owner acceptance changed; review before allocation.'}
        project_s = max(300, math.ceil((2 * elapsed + 90) / 30) * 30)
        if project_s > 600:
            return result | {'detail': 'The proposed project budget exceeds the supported ceiling.'}
        grant = building.status(ws)
        quote = {'schema': 1, 'policy': 'baseline_resource_quote_v1', 'draft': draft['id'],
            'milestone': milestone['id'], 'snapshot_digest': snapshot['digest'],
            'candidate_digest': candidate_digest, 'contract': contract,
            'author_context': author_context,
            'public_acceptance_digest': draft.get('public_acceptance_digest'),
            'acceptance_bundle': bundle, 'public_contracts': public,
            'baseline_evidence': baseline['evidence_dir'], 'baseline_receipt_digest': _digest(baseline),
            'prior_evidence': prior.get('evidence_dir'), 'prior_history': draft.get('verification_history', []),
            'spent_continuation_digest': _digest(resumed), 'project_timeout_s': project_s,
            'owner_timeout_s': 240, 'maximum_check_s': project_s + 240, 'max_phases': 2,
            'baseline_elapsed_s': elapsed, 'host_variation_allowance_s': elapsed,
            'unmeasured_candidate_allowance_s': 90, 'round_up_s': 30, 'minimum_project_s': 300,
            'owner_basis': 'Fixed 240s allowance for unmeasured cumulative owner phase; not a runtime estimate.',
            'grant': grant.get('grant'), 'apply_permitted': bool(grant['apply'] and ws.settings()['autonomy'] == 'propose'),
            'inference_calls': 0, 'author_budget_reset': False,
            'scope': 'Prospective operational resource allowance, not a statistical estimate or changed assertion. '
                     'Run all candidate project tests and the complete owner bundle anew. No partial-test reuse.'}
        quote['id'] = _digest(quote)
        return result | {'eligible': True, 'quote': quote}
    except (SnapshotUnsupported, OSError, KeyError, ValueError, TypeError):
        return result | {'detail': 'The source/acceptance/baseline evidence could not be validated.'}


def allocate_verification(ws, draft_id, quote_id, reason, *, checkpoint=lambda: None):
    if not isinstance(reason, str) or not reason.strip():
        raise WorkspaceError('Explain the separate verification resource allocation.')
    with ws._lock:
        draft = ws._draft(draft_id)
        status = allocation_status(ws, draft)
        if status['used']:
            return {'summary': 'This draft already has a reserved allocation. Nothing rerun.',
                    'draft': draft_id, 'allocation': status['receipt']['id'], 'already_used': True}
        quote = status.get('quote')
        if not status['eligible'] or not quote or quote.get('id') != quote_id:
            raise WorkspaceError('Resource quote is unavailable or stale; review the current evidence first.')
        milestone = next(m for m in ws.plan()['milestones'] if m['id'] == quote['milestone'])
        checkpoint()
        receipt = dict(quote, state='started', started=_now(), reason=reason.strip()[:2000])
        path = ws.home / 'build-check-allocations' / (draft_id + '.json')
        _write_json(path, receipt)
        ws.ledger.append('build.check_allocation_started', receipt)
    try:
        result = building._check_and_record(ws, draft, milestone, quote['contract'], checkpoint=checkpoint,
            project_timeout_s=quote['project_timeout_s'], owner_timeout_s=quote['owner_timeout_s'])
    except BaseException as error:
        receipt.update(state='interrupted', finished=_now(), outcome='unknown', error=type(error).__name__)
        _write_json(path, receipt)
        ws.ledger.append('build.check_allocation_interrupted', {'id': receipt['id'], 'error': type(error).__name__})
        raise
    verification = result.get('verification') or {}
    receipt.update(state='completed', finished=_now(), outcome=verification.get('status', 'not_run'),
        evidence_dir=verification.get('evidence_dir'), advanced=bool(result.get('advanced')),
        elapsed_check_s=sum((verification.get(k) or {}).get('elapsed_s', 0) for k in ('project_checks', 'acceptance')))
    _write_json(path, receipt)
    ws.ledger.append('build.check_allocation_completed', receipt)
    result['allocation'] = receipt['id']
    return result
