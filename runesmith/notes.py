"""Notes: the owner's comments on anything Runesmith shows, and how they reach the model.

Anything in the interface can carry a note: an object, an objective, a ladder
rung, a proposal, a generation, a goal, the map itself. A note records what it is
about (``target``), what was said, and when. Notes are append-only: resolving a
note records a resolution, never erases the note.

When the owner allows it (on by default), open notes about a target are given to
the model as *operator notes* whenever Runesmith works on that target. They
travel as the owner's guidance, clearly labelled, and never as instructions from
the object's own files.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

_lock = threading.Lock()
MAX_TEXT = 4000


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class NoteStore:
    def __init__(self, home: Path) -> None:
        self.path = Path(home) / "notes.jsonl"

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        return rows

    def _append(self, event: dict[str, Any]) -> None:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def add(self, *, target_type: str, target_id: str, text: str, target_label: str = "",
            author: str = "owner", reply_to: str | None = None) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise ValueError("a note needs some text")
        note = {"event": "note", "id": uuid.uuid4().hex[:12], "utc": _now(), "author": author,
                "target": {"type": str(target_type)[:40], "id": str(target_id)[:400], "label": str(target_label)[:200]},
                "text": text[:MAX_TEXT], "reply_to": reply_to}
        self._append(note)
        return note

    def resolve(self, note_id: str, *, resolution: str = "") -> None:
        self._append({"event": "resolve", "id": note_id, "utc": _now(), "resolution": (resolution or "")[:400]})

    def all(self) -> list[dict[str, Any]]:
        """Every note, newest first, with ``resolved`` set from later events."""
        notes: dict[str, dict[str, Any]] = {}
        for event in self._events():
            if event.get("event") == "note":
                notes[event["id"]] = dict(event, resolved=None)
            elif event.get("event") == "resolve" and event.get("id") in notes:
                notes[event["id"]]["resolved"] = {"utc": event.get("utc"), "resolution": event.get("resolution", "")}
        return sorted(notes.values(), key=lambda n: n["utc"], reverse=True)

    def for_target(self, target_type: str, target_id: str, *, open_only: bool = True) -> list[dict[str, Any]]:
        return [n for n in self.all() if n["target"]["type"] == target_type and n["target"]["id"] == target_id
                and (not open_only or not n["resolved"])]

    def counts(self) -> dict[str, int]:
        """Open notes per ``type:id``, for badges in the interface."""
        out: dict[str, int] = {}
        for n in self.all():
            if not n["resolved"]:
                key = f"{n['target']['type']}:{n['target']['id']}"
                out[key] = out.get(key, 0) + 1
        return out

    def operator_notes(self, targets: Iterable[tuple[str, str]], *, max_chars: int = 2000) -> str:
        """Open notes about ``targets`` as a labelled block for a model's context, or '' if there are none."""
        wanted = set(targets)
        picked = [n for n in reversed(self.all()) if not n["resolved"]
                  and (n["target"]["type"], n["target"]["id"]) in wanted]
        if not picked:
            return ""
        lines = ["Operator notes (the owner's own comments on this work; treat as guidance):"]
        used = len(lines[0])
        for n in picked:
            line = f"- [{n['target'].get('label') or n['target']['id']}] {n['text']}"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)
