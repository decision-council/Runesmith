"""A draft whose checks did not finish, and what the owner's setting does about it (journey J11-G44).

A draft whose checks ran out of time waits for the owner's "Resume timed-out check once": one more run with a longer
limit, no model call. In a project that runs without its owner the milestone stalled there: J11's Scatter revision timed
out at 255.2 s against its 254 s limit while a test run loaded the computer (the same checks take about 30 s unloaded),
and nobody was there to press the button. The setting "When a draft's checks did not finish" says what Runesmith may do:
"wait for me" (the default) or "recheck once". The recheck is exactly what the owner's button does (same receipt, same
limits, same refusals), once for each draft, and is said as "Runesmith (your setting)".
"""
from __future__ import annotations

from typing import Any

from runesmith.app import building
from runesmith.app.planner import milestone_contract, milestone_ready
from runesmith.app.verification_resume import resume_status
from runesmith.app.workspace import _now, _read_json, _write_json

POLICY = 'recheck'
KIND = 'resume_check'                                    # the step this module asks the schedule for
MARKS = 'RECHECKS.json'                                  # {draft id: when Runesmith asked for it by the setting}: once each
REASON = ('Runesmith (your setting): the checks of this draft did not finish, so they run once more with a longer limit '
          'and no model call.')


def _marks(ws) -> dict[str, Any]:
    value = _read_json(ws.home / MARKS, {})
    return value if isinstance(value, dict) else {}


def mark(ws, draft_id: str) -> str:
    """Record that the setting asked for this draft's recheck (before it runs, so a refusal or a crash is not asked
    again), and return the title of its milestone for the words said about it."""
    with ws._lock:
        _write_json(ws.home / MARKS, {**_marks(ws), draft_id: _now()})
    draft = ws._draft(draft_id)
    milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == draft.get('milestone')), {})
    return milestone.get('title') or draft.get('milestone') or draft_id


def next_draft(ws) -> dict[str, Any] | None:
    """The draft the setting rechecks now, or None. Only the newest draft of a ready milestone, still waiting, whose
    checks did not finish on today's contract, that the owner's own button could resume (the extension is unused and
    longer than the limit that ran out), and that the setting has not asked for before."""
    if not building.status(ws)['enabled']:
        return None                                      # nothing runs executable checks here: the owner's to decide
    plan, marks, seen = ws.plan() or {}, _marks(ws), set()
    milestones = {m['id']: m for m in plan.get('milestones', [])}
    for draft in ws.drafts():                            # newest first
        milestone_id = draft.get('milestone')
        if milestone_id in seen:
            continue
        seen.add(milestone_id)
        milestone = milestones.get(milestone_id)
        if (milestone is None or draft['id'] in marks or draft.get('state') not in ('waiting', 'needs_revision')
                or not building.verification_inconclusive(draft.get('verification'))
                or not milestone_ready(plan, milestone) or draft.get('contract') != milestone_contract(ws, milestone)):
            continue
        if resume_status(ws, draft)['eligible']:
            return draft
    return None
