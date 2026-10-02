"""What Runesmith decided by an owner's setting, kept where the owner reads it (journey J11-G42, G43).

A project that runs to the end of its plan without its owner makes choices the owner would otherwise make: keeping the
queue after an interrupted job, one more try for a milestone whose tries are used up, smaller steps for one that
failed that too. Each is allowed by a setting that is off by default, and each is said in plain words on the Overview
and written to the ledger, as "Runesmith (your setting)". This module only records and reads; it decides nothing.
"""
from __future__ import annotations

from typing import Any

from runesmith.app.workspace import _now, _read_json, _write_json

BY = 'Runesmith (your setting)'
FILE = 'AUTOMATIC.json'
KEPT = 30


def record(ws, what: str, *, kind: str, **data: Any) -> dict[str, Any]:
    """Note one decision in plain words (`what`), with its kind and the facts that name it."""
    row = {'utc': _now(), 'kind': kind, 'what': what[:400], 'by': BY, **data}
    with ws._lock:
        rows = _read_json(ws.home / FILE, [])
        rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        _write_json(ws.home / FILE, (rows + [row])[-KEPT:])
    ws.ledger.append('automatic.decision', row)
    return row


def recent(ws, limit: int = 5) -> list[dict[str, Any]]:
    """The newest decisions, newest first (what the Overview shows)."""
    rows = _read_json(ws.home / FILE, [])
    rows = [r for r in rows if isinstance(r, dict) and isinstance(r.get('what'), str)] if isinstance(rows, list) else []
    return rows[::-1][:limit]
