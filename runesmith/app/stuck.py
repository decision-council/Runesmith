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
from runesmith.app.author_allowance import _load, ordinary_allowance, shared_reads
from runesmith.app.breakdowns import adopt_breakdown, can_break_down, propose_breakdown, room_for_breakdown
from runesmith.app.building import build_escalation_status
from runesmith.app.planner import PlannerUnavailable, milestone_contract, milestone_ready, ready_milestones, source_context
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

POLICIES = ('retry', 'retry_split')
SPLITS = 'STUCK_SPLITS.json'          # {milestone id: when Runesmith broke it down by the setting}: once each
TURN_KINDS = ('escalate', 'split')    # the steps this module asks the schedule for


def stuck_milestones(ws, context=None) -> list[dict[str, Any]]:
    """The ready milestones whose ordinary tries are used up on today's source, each with whether its one more try is
    too ({'milestone', 'escalated'}). A draft that waits for checks or the owner, or is applied, is no stuck milestone."""
    context = context or source_context(ws)
    rows, drafts = [], None
    with shared_reads():                  # every receipt once, not once per ready milestone (review of batch EE)
        for milestone in ready_milestones(ws.plan()):
            contract = milestone_contract(ws, milestone)
            try:
                allowance = ordinary_allowance(ws, contract, context['snapshot_digest'])
            except WorkspaceError:
                continue                  # unreadable or unresolved evidence: the owner's to reconcile, not a setting's
            if allowance['remaining']:
                continue
            if drafts is None:
                drafts = ws.drafts()
            if any(d.get('state') in ('waiting', 'applied') for d in drafts if d.get('contract') == contract):
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
    if not room_for_breakdown(plan):      # an answer that could not be adopted is not paid for (review of batch EE)
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


def gap_waits(ws, milestone) -> str | None:
    """The file the milestone's latest one more try could not change because the model was not shown it, while it still
    is not shown; else None. The owner's button stays open (he can show the file), but the setting does not pay for the
    same refusal every other step (review of batch EE: the call is not counted as used, so it came again and again)."""
    contract = milestone_contract(ws, milestone)
    rows = []
    try:
        for name, row in _load(ws, 'build-escalations'):
            if row.get('contract') == contract:
                rows.append((str(row.get('utc') or ''), name, row))
    except WorkspaceError:
        return None
    if not rows:
        return None
    latest = max(rows, key=lambda r: r[:2])[2]
    not_shown = (latest.get('feedback') or {}).get('not_shown') if isinstance(latest.get('feedback'), dict) else None
    if latest.get('state') != 'context_gap' or not isinstance(not_shown, str):
        return None
    context = source_context(ws, milestone=milestone)
    return None if not_shown in context['files'] or not_shown in (context.get('excerpts') or {}) else not_shown


def stuck_work(ws, policy) -> tuple[str, dict[str, Any]] | None:
    """What the schedule runs for the setting now, or None: ('escalate', {'milestone_id': id}) for the one more try the
    owner's button would give that milestone, or ('split', {'milestone': id}) for a milestone whose one more try did not
    help (policy retry_split). The milestone is the first the one more try can be given to now: one that waits on a
    draft, a check or an answer, or on a file no model is shown, no longer holds back the others (review of batch EE)."""
    if policy not in POLICIES or ws.settings()['autonomy'] == 'observe' or not ws.settings()['build_steps']:
        return None
    with shared_reads():
        return _judge(ws, policy, stuck_milestones(ws))[0]


def _judge(ws, policy, rows) -> tuple[tuple[str, dict[str, Any]] | None, dict[str, dict[str, Any]]]:
    """(the step the setting takes now or None, the stuck milestones it can do nothing more for). One judgement, so what the
    schedule runs and what the owner is told cannot disagree: a milestone waits for the owner exactly when the setting has
    no step left for it (the default 'wait for me'; a one more try that is used up or cannot change a file no model is shown;
    no break-down left to ask for)."""
    escalate = split = None
    waiting: dict[str, dict[str, Any]] = {}
    offered = None          # the milestone the owner's "one more try" button would give it to (the default setting offers it)
    if policy not in POLICIES and any(not row['escalated'] for row in rows):
        state = build_escalation_status(ws)          # once, for the button's own choice: each call builds the source context
        offered = state['milestone'] if state and state['eligible'] else None
    for row in rows:
        milestone = row['milestone']
        note = {'milestone': milestone, 'escalated': row['escalated'], 'retry': offered == milestone['id']}
        if policy not in POLICIES:
            waiting[milestone['id']] = dict(note, kind='wait')
        elif not row['escalated']:
            if gap_waits(ws, milestone) is not None:
                waiting[milestone['id']] = dict(note, kind='gap')
                continue
            if escalate is None:
                state = build_escalation_status(ws, milestone['id'])
                if state and state['eligible']:
                    escalate = ('escalate', {'milestone_id': milestone['id']})
        elif policy == 'retry_split' and may_split(ws, milestone):
            split = split or ('split', {'milestone': milestone['id']})
        else:
            waiting[milestone['id']] = dict(note, kind='spent')
    return escalate or split, waiting


def stuck_turn(ws, policy) -> tuple[str, dict[str, Any]] | None:
    """`stuck_work`, and the owner told about every stuck milestone the setting has nothing left to do for (a failed
    one-more-try draft and a refused break-down once left the worker idle with nobody told). The schedule calls this."""
    if ws.settings()['autonomy'] == 'observe' or not ws.settings()['build_steps']:
        return None
    with shared_reads():
        turn, waiting = _judge(ws, policy, stuck_milestones(ws))
        sync_notices(ws, policy, waiting)
    return turn


def refresh_notices(ws) -> None:
    """Tell the owner at once when a step the setting just took (a one more try, a break-down) left a milestone with nothing
    more to try, instead of at the schedule's next judgement. Never breaks the job it follows."""
    try:
        stuck_turn(ws, ws.settings().get('stuck_policy'))
    except Exception:
        pass


# ---- telling the owner ------------------------------------------------------------------------------------------------

NOTICES = 'STUCK_NOTICES.json'   # {milestone id: {'utc', 'kind', 'contract', 'escalated', 'retry'}}: stuck, nothing left to do by itself
REFUSED = 'STUCK_REFUSED.json'   # {milestone id: {'utc', 'why', 'answered'}}: the break-down the setting asked for, and why it came to nothing


def _notices(ws) -> dict[str, Any]:
    value = _read_json(ws.home / NOTICES, {})
    return value if isinstance(value, dict) else {}


def sync_notices(ws, policy, waiting) -> list[str]:
    """Keep the stuck milestones that wait for the owner (`waiting`) and drop the rest. A milestone is said once, when it
    first waits (to the ledger and to RUNESMITH.md in the project folder), not at every step. Returns those newly said."""
    from runesmith.app import runesmith_md
    contracts = {milestone_id: milestone_contract(ws, row['milestone']) for milestone_id, row in waiting.items()}
    said = []
    with ws._lock:
        before = _notices(ws)
        after = {}
        for milestone_id, row in waiting.items():
            old = before.get(milestone_id)
            facts = {'kind': row['kind'], 'contract': contracts[milestone_id], 'escalated': row['escalated'], 'retry': row['retry']}
            if isinstance(old, dict) and old.get('kind') == row['kind'] and old.get('contract') == contracts[milestone_id]:
                after[milestone_id] = dict(old, **facts)          # said already; the facts that only change what is offered refresh
                continue
            after[milestone_id] = dict(facts, utc=_now(), policy=policy or 'wait')
            said.append(milestone_id)
        if after != before:
            _write_json(ws.home / NOTICES, after)
    for milestone_id in said:
        ws.ledger.append('stuck.needs_owner', {'milestone': milestone_id, 'kind': after[milestone_id]['kind'],
                                               'policy': after[milestone_id]['policy']})
        runesmith_md.stuck_needs_owner(ws, milestone_id, after[milestone_id]['kind'])
    return said


def _facet(ws, milestone) -> tuple[str, str]:
    """Why no break-down is under way for this stuck milestone, as (code, plain words); code 'open' when none stands in the
    way."""
    plan = ws.plan() or {}
    proposals = [_read_json(path, {}) for path in (ws.home / 'breakdowns').glob('*.json')]
    proposals = [row for row in proposals if row.get('milestone') == milestone['id']]
    if any(row.get('state') == 'proposed' for row in proposals):
        return 'proposed', 'Smaller steps are proposed for it and wait for your review under Goals & plan.'
    if any(row.get('state') == 'rejected' for row in proposals):
        return 'rejected', 'You turned down the smaller steps proposed for it.'
    if milestone.get('parent_id'):
        return 'step', 'It is already one of the smaller steps of a bigger milestone, and a smaller step is not broken down again by itself.'
    if any(m.get('parent_id') == milestone['id'] for m in plan.get('milestones', [])):
        return 'children', 'It already has smaller steps under Goals & plan.'
    if not room_for_breakdown(plan):
        return 'full', 'The plan has no room for more steps. Finish or drop some first.'
    if not ws.settings().get('build_paths'):
        return 'paths', 'No folders are chosen for building, so smaller steps cannot be asked for yet.'
    refused = _read_json(ws.home / REFUSED, {}).get(milestone['id'])
    if isinstance(refused, dict) and refused.get('why'):
        why = str(refused['why']).strip().rstrip('.')[:240]
        if refused.get('answered'):
            return 'refused', f'Runesmith asked a model for smaller steps by your setting, but its answer could not be used ({why}).'
        return 'refused', f'Runesmith tried to ask for smaller steps by your setting, but could not ({why}).'
    if milestone['id'] in _splits(ws):
        return 'asked', 'Runesmith already asked for smaller steps by your setting, and no usable proposal came of it.'
    return 'open', ''


def owner_needed(ws) -> list[dict[str, Any]]:
    """The stuck milestones that wait for the owner, for the Overview: what is stuck, why nothing more happens by itself, and
    what he can do (each choice is something he can already do elsewhere; none grants more tries). Cheap: it reads the notes
    the schedule kept and checks them against the plan, so a milestone he edited, finished or set aside is gone."""
    notes = _notices(ws)
    if not notes:
        return []
    plan = ws.plan() or {}
    out = []
    for milestone in plan.get('milestones', []):
        note = notes.get(milestone.get('id'))
        if not isinstance(note, dict) or milestone.get('status') not in ('open', 'doing') or not milestone_ready(plan, milestone):
            continue                                          # adopted smaller steps make it wait for them: no longer stuck
        try:
            if note.get('contract') != milestone_contract(ws, milestone):
                continue                                          # edited since: new wording, new tries
        except WorkspaceError:
            continue
        out.append(_describe(ws, plan, milestone, note))
    return out


def _describe(ws, plan, milestone, note) -> dict[str, Any]:
    title = str(milestone.get('title') or milestone['id'])
    kind = note.get('kind')
    used = 'its three tries and its one more try are' if note.get('escalated') else 'its three tries are'
    head = f'“{title}” cannot go on by itself: {used} used up on the files as they are now.'
    code, why = _facet(ws, milestone)
    if kind == 'gap':
        try:
            shown = gap_waits(ws, milestone)
        except WorkspaceError:
            shown = None
        why = (f'Its one more try could not change {shown}, because no model is shown that file. ' if shown else
               'Its one more try could not change a file no model is shown. ') + why
    elif kind == 'wait':
        why = 'Your setting is to wait for you when tries are used up. ' + why
    elif code == 'open':
        why = 'Nothing more is left that your setting may try by itself.'
    choices = []
    if note.get('retry'):
        choices.append({'id': 'escalate', 'label': 'Try once more with another model',
                        'detail': 'The one more try: another model, one call, the same checks.'})
    if code == 'proposed':
        choices.append({'id': 'review', 'label': 'Review the proposed steps',
                        'detail': 'Goals & plan shows them; adopting them lets the build go on.'})
    elif (code in ('open', 'refused', 'asked', 'rejected', 'step') and room_for_breakdown(plan)
          and ws.settings().get('build_paths') and can_break_down(plan, milestone['id'])):
        choices.append({'id': 'breakdown', 'label': 'Ask for smaller steps' + ('' if code == 'open' else ' again'),
                        'detail': 'One request to a model; you review the steps before they are adopted.'})
    if kind == 'gap':
        choices.append({'id': 'show_file', 'label': 'Show the file to the models', 'detail': 'Goals & plan, Author context.'})
    choices.append({'id': 'edit', 'label': 'Edit the milestone', 'detail': 'New wording gives it fresh tries. Goals & plan.'})
    choices.append({'id': 'set_aside', 'label': 'Set it aside', 'detail': 'The plan goes on without it; you can reopen it later.'})
    return {'milestone': milestone['id'], 'title': title, 'utc': note.get('utc'), 'kind': kind, 'code': code,
            'what': (head + ' ' + why).strip(), 'choices': choices}


def defers_breakdown(ws, milestone_id, policy) -> bool:
    """Whether the proposal of smaller steps the schedule used to make at once waits, because the setting will act on this
    milestone itself: for "retry" its one more try comes first, for "retry_split" that and then its own breakdown. When
    the setting cannot act (no longer stuck in its way, a smaller step, already broken down, no room in the plan), the
    proposal the owner used to get is not held back (review of batch EE)."""
    if policy not in POLICIES:
        return False
    row = next((r for r in stuck_milestones(ws) if r['milestone']['id'] == milestone_id), None)
    if row is None:
        return False
    if not row['escalated']:
        return True
    return policy == 'retry_split' and may_split(ws, row['milestone'])


def next_escalation(ws) -> dict[str, Any] | None:
    """The milestone the one more try would be for (to say whose it was)."""
    state = build_escalation_status(ws)
    if not state or not state.get('milestone'):
        return None
    return next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == state['milestone']), None)


def _remember_refusal(ws, milestone_id, error) -> None:
    """Keep, in plain words, why the break-down the setting asked for came to nothing (what the owner is shown later)."""
    with ws._lock:
        rows = _read_json(ws.home / REFUSED, {})
        rows = rows if isinstance(rows, dict) else {}
        _write_json(ws.home / REFUSED, {**rows, milestone_id: {'utc': _now(), 'why': str(error)[:300],
                                                                'answered': bool(getattr(error, 'answered', False))}})


def split(ws, router, milestone_id, *, checkpoint=lambda: None) -> dict[str, Any]:
    """Break a stuck milestone down by the setting: propose, then adopt as the owner's adoption does."""
    milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == milestone_id), None)
    if not may_split(ws, milestone):
        raise WorkspaceError('This milestone is not one to break down by your setting now; nothing was asked.')
    with ws._lock:                           # once, whatever the call does: the owner's own proposal is not undone
        _write_json(ws.home / SPLITS, {**_splits(ws), milestone_id: _now()})
    title = milestone['title']
    try:
        proposal = propose_breakdown(ws, router, milestone_id, checkpoint=checkpoint)
    except PlannerUnavailable as error:
        if getattr(error, 'nothing_ran', False):      # every route turned it away: nothing was asked, so it is not spent
            with ws._lock:
                _write_json(ws.home / SPLITS, {k: v for k, v in _splits(ws).items() if k != milestone_id})
        else:
            _remember_refusal(ws, milestone_id, error)
        raise
    except WorkspaceError as error:                   # spent, and the owner is told why nothing came of it (J11-B28)
        _remember_refusal(ws, milestone_id, error)
        raise
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
