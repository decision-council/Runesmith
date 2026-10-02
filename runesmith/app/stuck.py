"""A milestone whose tries are used up, and what the owner's setting does about it (journey J11-G43).

Three tries, then the owner's button gives one more with another model, then nothing: a project loaded with a whole
plan stopped at the first milestone that no model could build, and waited for an owner who was not there. The setting
"When a milestone's tries are used up" says what Runesmith may do about it: "wait for me" (the default), "one more
try", or "one more try, then break it down". The one more try is exactly what the owner's button does (same receipts,
same limits); the breakdown is proposed and adopted as the owner's adoption does, children replacing the milestone.
Each happens once per milestone, never for a smaller step of a breakdown (no recursion), never over a decision the
owner made meanwhile, and is said as "Runesmith (your setting)". Everything else keeps building meanwhile: the
schedule hands this one step in turn, not all of them.
"""
from __future__ import annotations

from typing import Any

from runesmith.app import automatic
from runesmith.app.author_allowance import ordinary_allowance
from runesmith.app.breakdowns import adopt_breakdown, can_break_down, propose_breakdown
from runesmith.app.building import build_escalation_status
from runesmith.app.planner import milestone_contract, ready_milestones, source_context
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

POLICIES = ('retry', 'retry_split')
SPLITS = 'STUCK_SPLITS.json'          # {milestone id: when Runesmith broke it down by the setting}: once each
TURN_KINDS = ('escalate', 'split')    # the steps this module asks the schedule for


def stuck_milestones(ws, context=None) -> list[dict[str, Any]]:
    """The ready milestones whose ordinary tries are used up on today's source, each with whether its one more try is
    too ({'milestone', 'escalated'}). A draft that waits for checks or the owner, or is applied, is no stuck milestone."""
    context = context or source_context(ws)
    rows = []
    for milestone in ready_milestones(ws.plan()):
        contract = milestone_contract(ws, milestone)
        try:
            allowance = ordinary_allowance(ws, contract, context['snapshot_digest'])
        except WorkspaceError:
            continue                      # unreadable or unresolved evidence: the owner's to reconcile, not a setting's
        if allowance['remaining']:
            continue
        if any(d.get('state') in ('waiting', 'applied') for d in ws.drafts() if d.get('contract') == contract):
            continue
        rows.append({'milestone': milestone, 'escalated': bool(allowance['escalations'])})
    return rows


def _splits(ws) -> dict[str, Any]:
    value = _read_json(ws.home / SPLITS, {})
    return value if isinstance(value, dict) else {}


def may_split(ws, milestone) -> bool:
    """Whether the setting may break this milestone down: once, never a smaller step, never over the owner's own
    proposal or decision about it, and not while a breakdown call is unresolved."""
    plan = ws.plan() or {}
    if not isinstance(milestone, dict) or milestone.get('parent_id') or not can_break_down(plan, milestone['id']):
        return False
    if not ws.settings().get('build_paths') or milestone['id'] in _splits(ws):
        return False
    for folder in ('breakdowns', 'breakdown-attempts'):
        for path in (ws.home / folder).glob('*.json'):
            row = _read_json(path, {})
            if folder == 'breakdowns' and row.get('milestone') == milestone['id']:
                return False                  # proposed, rejected or adopted: the owner's, or already done
            if folder == 'breakdown-attempts' and row.get('state') in ('started', 'uncertain'):
                return False
    return True


def stuck_work(ws, policy) -> tuple[str, dict[str, Any]] | None:
    """What the schedule runs for the setting now, or None: ('escalate', {}) for the one more try the owner's button
    would give, or ('split', {'milestone': id}) for a milestone whose one more try did not help (policy retry_split)."""
    if policy not in POLICIES or ws.settings()['autonomy'] == 'observe' or not ws.settings()['build_steps']:
        return None
    rows = stuck_milestones(ws)
    if not rows:
        return None
    state = build_escalation_status(ws)
    if state and state['eligible'] and any(r['milestone']['id'] == state['milestone'] and not r['escalated'] for r in rows):
        return 'escalate', {}
    if policy == 'retry_split':
        for row in rows:
            if row['escalated'] and may_split(ws, row['milestone']):
                return 'split', {'milestone': row['milestone']['id']}
    return None


def defers_breakdown(ws, milestone_id, policy) -> bool:
    """Whether the proposal of smaller steps the schedule used to make at once waits: for "retry_split" the setting makes
    and adopts it itself, and for "retry" the one more try comes first."""
    if policy == 'retry_split':
        return True
    if policy != 'retry':
        return False
    return not any(r['escalated'] for r in stuck_milestones(ws) if r['milestone']['id'] == milestone_id)


def next_escalation(ws) -> dict[str, Any] | None:
    """The milestone the one more try would be for (to say whose it was)."""
    state = build_escalation_status(ws)
    if not state or not state.get('milestone'):
        return None
    return next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == state['milestone']), None)


def split(ws, router, milestone_id, *, checkpoint=lambda: None) -> dict[str, Any]:
    """Break a stuck milestone down by the setting: propose, then adopt as the owner's adoption does."""
    milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == milestone_id), None)
    if not may_split(ws, milestone):
        raise WorkspaceError('This milestone is not one to break down by your setting now; nothing was asked.')
    with ws._lock:                           # once, whatever the call does: the owner's own proposal is not undone
        _write_json(ws.home / SPLITS, {**_splits(ws), milestone_id: _now()})
    title = milestone['title']
    proposal = propose_breakdown(ws, router, milestone_id, checkpoint=checkpoint)
    try:
        adopted = adopt_breakdown(ws, proposal['id'], by=automatic.BY)
    except WorkspaceError as error:
        # The plan, the source or the checks changed since the proposal: it waits under Goals & plan for the owner.
        said = f'“{title}” had used up its tries. Runesmith proposed smaller steps by your setting, but could not adopt them ({error}); they wait for you.'
        automatic.record(ws, said, kind='split', milestone=milestone_id, adopted=False, breakdown=proposal['id'])
        return {'summary': said, 'milestone': milestone_id}
    said = (f'“{title}” had used up its tries and its one more try. By your setting, Runesmith broke it down into '
            f'{len(adopted["children"])} smaller steps, which now come first; the goal itself is unchanged.')
    automatic.record(ws, said, kind='split', milestone=milestone_id, adopted=True, breakdown=proposal['id'],
                     children=adopted['children'])
    return {'summary': said, 'milestone': milestone_id}
