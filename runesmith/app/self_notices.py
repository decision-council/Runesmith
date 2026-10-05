"""Things Runesmith tells the owner once about its own self-improvement, and keeps quiet about until they change.

Self-improvement is switched on, but no Improver model is set up: a campaign cannot start. Runesmith says so once, in
plain words, on the Overview (where what it decided by the owner's settings is shown) and in RUNESMITH.md, and goes on
repairing. It says it again only after an Improver has been there and gone, so the note is never repeated every round.
"""
from __future__ import annotations

from runesmith.app import automatic, runesmith_md
from runesmith.app.workspace import _now, _read_json, _write_json

FILE = "SELF_NOTICES.json"
NO_IMPROVER = ("Self-improvement is on, but no Improver model is set up, so Runesmith cannot try to improve itself yet. "
               "Repair work goes on as before. Choose an Improver under Thinking power to let it start.")


def improver_check(ws, *, kaizen_on: bool, improver_ready: bool) -> str | None:
    """Keep the one-time note about a missing Improver. Returns the sentence when it was said now, else None."""
    state = _read_json(ws.home / FILE, {})
    state = state if isinstance(state, dict) else {}
    if not kaizen_on or improver_ready:
        if "no_improver" in state:                       # it is there again (or the owner switched it off): say it afresh next time
            _write_json(ws.home / FILE, {k: v for k, v in state.items() if k != "no_improver"})
        return None
    if state.get("no_improver"):
        return None
    with ws._lock:
        _write_json(ws.home / FILE, dict(state, no_improver=_now()))
    automatic.record(ws, NO_IMPROVER, kind="no_improver")
    runesmith_md.no_improver(ws)
    return NO_IMPROVER
