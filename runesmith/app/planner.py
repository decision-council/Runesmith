"""The planner: from the owner's brief and the map to a plan, and from a milestone to first files.

This is how Runesmith starts work in a folder that has no failing tests to repair:
an empty folder with an idea, a folder of documents, a half-built project. The
planner asks the model in the ``plan`` role (or, if none is set, the role that
has instruments) for:

* a **plan**: a summary, milestones on named tracks, first steps and the questions
  only the owner can answer; the owner edits it freely; and
* a **draft**: the first files for one milestone, written as a proposal. Drafts are
  labelled as unverified: no test has judged them. They are applied only by the
  owner, never over an existing file without a second confirmation, and can be undone.

Everything the model sees is listed in the prompt: the map, the brief, the
blueprints the owner picked, the goals and the owner's open notes. Nothing else.
"""

from __future__ import annotations

import json
import time
from typing import Any

from runesmith.instruments import TransportCensored

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "tracks": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "purpose": {"type": "string"}}, "required": ["name"]}},
        "milestones": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "detail": {"type": "string"}, "track": {"type": "string"},
            "done_when": {"type": "string"}}, "required": ["title"]}},
        "first_steps": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "milestones"],
}
DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "why": {"type": "string"},
        "files": {"type": "array", "items": {"type": "object", "properties": {
            "path": {"type": "string"}, "purpose": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}},
    },
    "required": ["title", "files"],
}
PLAN_SYSTEM = ("You are the planning instrument of Runesmith, a careful development runtime. You write practical, "
               "honest plans for the owner of a folder. Reply with one JSON object only.")
DRAFT_SYSTEM = ("You are the drafting instrument of Runesmith. You write the first files for one milestone of the "
                "owner's plan: small, complete, runnable where it applies, with no placeholders you could fill in "
                "yourself. Reply with one JSON object only.")


class PlannerUnavailable(RuntimeError):
    """No model is set up for planning, or it did not answer."""


class SkippedByOwner(RuntimeError):
    """The owner skipped the chat-relay request: nothing is saved, and the plan and the drafts stay as they were."""


def _workspace_summary(ws) -> dict[str, Any]:
    env_map = ws.environment_map() or {}
    facts = env_map.get("workspace_facts") or {}
    objects = []
    for o in env_map.get("objects", []):
        row = {"name": o["name"], "kind": o["kind"], "next_rung": o.get("next_rung"),
               "ladder": {r["rung"]: r["status"] for r in o.get("ladder", [])}}
        f = o.get("facts") or {}
        for key in ("source_files", "test_files", "markdown_files", "documents", "files", "broken_links", "top_extensions",
                    "package_name", "test_script", "pages", "stylesheets", "scripts", "broken_references",
                    "pages_with_viewport", "pages_with_title"):
            if f.get(key) not in (None, [], ""):
                row[key] = f[key]
        objects.append(row)
    return {"folder": ws.settings()["workspace_name"], "empty": facts.get("empty"),
            "top_level_entries": [e["name"] + ("/" if e["type"] == "dir" else "") for e in facts.get("entries", [])][:60],
            "file_count": facts.get("files"), "kinds_of_files": facts.get("top_extensions"), "objects": objects}


def plan_prompt(ws) -> str:
    brief = ws.brief()
    packet = {
        "task": ("Draft a development plan for this folder. Use the owner's brief and blueprints as the source of "
                 "intent; use the map for what exists now. Milestones must be concrete and checkable, ordered, and "
                 "grouped into a few named tracks (for example: Foundation, Features, Quality, Docs). Keep it to what "
                 "the brief supports; ask instead of inventing requirements."),
        "folder_map": _workspace_summary(ws),
        "owner_goals": [g["text"] for g in ws.goals() if g["status"] == "active"],
        "owner_brief": brief.get("text") or "(no brief written yet)",
        "current_plan": ws.plan(),
        "output": {"summary": "3-6 sentences: what will be built and the approach",
                   "tracks": "2-5 tracks, each {name, purpose}",
                   "milestones": "4-12 milestones, each {title, detail, track, done_when}",
                   "first_steps": "up to 5 concrete next actions",
                   "questions": "up to 5 decisions only the owner can make"},
    }
    text = json.dumps(packet, ensure_ascii=False, indent=1)
    blueprints = ws.blueprint_text()
    if blueprints:
        text += "\n\n=== BLUEPRINT DOCUMENTS (chosen by the owner) ===\n" + blueprints
    notes = ws.notes_for_plan()
    if notes:
        text += "\n\n" + notes
    return text


def draft_prompt(ws, milestone: dict[str, Any]) -> str:
    plan = ws.plan() or {}
    packet = {
        "task": ("Write the first files for this milestone, inside the owner's folder. Paths are relative to the folder "
                 "root and use forward slashes. Keep it small: at most 8 files, each complete. Prefer the conventions "
                 "the folder already uses. Include a short README section or file when it helps the owner run it."),
        "milestone": milestone,
        "plan_summary": plan.get("summary"),
        "folder_map": _workspace_summary(ws),
        "owner_brief": ws.brief().get("text") or "(no brief written yet)",
        "rules": ["never write inside .runesmith, .git or outside the folder",
                  "an existing file is only replaced if the milestone requires it; say so in its purpose",
                  "no secrets, keys or personal data in files"],
        "output": {"title": "a short name for this draft", "why": "what these files achieve for the milestone",
                   "files": "[{path, purpose, content}]"},
    }
    text = json.dumps(packet, ensure_ascii=False, indent=1)
    notes = ws.notes_for_plan()
    if notes:
        text += "\n\n" + notes
    return text


def _call(ws, router, prompt: str, system: str, schema: dict, key: str, max_tokens: int):
    try:
        outcome = router.call("plan", prompt=prompt, system=system, schema=schema, max_tokens=max_tokens, key=key)
    except KeyError as error:
        raise PlannerUnavailable("no model is set up for planning: add one under Inference") from error
    except TransportCensored as error:
        raise PlannerUnavailable(f"the model did not answer: {str(error)[:200]}") from error
    if isinstance(outcome.data, dict) and outcome.data.get("skipped_by_owner"):
        raise SkippedByOwner("you skipped the request, so nothing changed")
    if not outcome.ok or not isinstance(outcome.data, dict):
        raise PlannerUnavailable(f"the model's answer was not usable: {(outcome.error or 'no JSON')[:200]}")
    missing = [k for k in schema.get("required", []) if k not in outcome.data]
    if missing:                                     # never save half an answer over a plan the owner has
        raise PlannerUnavailable(f"the model's answer has no {' or '.join(missing)}, so nothing was saved")
    by = outcome.receipt.get("answered_by") or outcome.receipt.get("model")
    return outcome.data, by


def draft_plan(ws, router) -> dict[str, Any]:
    data, by = _call(ws, router, plan_prompt(ws), PLAN_SYSTEM, PLAN_SCHEMA,
                     f"plan-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}", 6000)
    data["drafted_by"] = by
    return ws.save_plan(data)


def draft_files(ws, router, milestone_id: str | None = None) -> dict[str, Any]:
    plan = ws.plan() or {}
    milestones = plan.get("milestones") or []
    milestone = next((m for m in milestones if m["id"] == milestone_id), None) if milestone_id else \
        next((m for m in milestones if m.get("status") in ("open", "doing")), None)
    if milestone is None:
        raise PlannerUnavailable("there is no open milestone to draft for: draft a plan first")
    data, by = _call(ws, router, draft_prompt(ws, milestone), DRAFT_SYSTEM, DRAFT_SCHEMA,
                     f"draft-{milestone['id']}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}", 12000)
    files = [f for f in (data.get("files") or []) if isinstance(f, dict)]
    return ws.save_draft(title=str(data.get("title") or milestone["title"]), why=str(data.get("why") or ""),
                         files=files, drafted_by=by, milestone=milestone["id"])
