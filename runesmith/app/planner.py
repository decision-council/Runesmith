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

import copy
import json
import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any

from runesmith.instruments import LenientSchema, TransportCensored

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
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "milestones"],
}
# Code travels inside these strings, so the schema is lenient: Milliner gets it as text, not as a forced schema.
# Forced structured output on free routes lost every backslash escape (journey J2: a whole file arrived as one
# line, "def greet(name):n    return ", with no quotes), while the same request as text came back intact.
# Exact edits per file. Each must match exactly once, so more of them are no less safe; weak models do not count
# well, and a free model's 8 correct edits were refused whole at 6 (journey J2-F23).
MAX_EDITS = 12

DRAFT_SCHEMA = LenientSchema({
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "why": {"type": "string"},
        # Alternative object shapes must be disjoint. Milliner's strict
        # transformation requires every property: listing both representations
        # in one object would require the contradictory dual-field response.
        "files": {"type": "array", "items": {"anyOf": [
            {"type":"object", "properties":{
                "path":{"type":"string"}, "purpose":{"type":"string"}, "content":{"type":"string"}},
             "required":["path","content"], "additionalProperties":False},
            {"type":"object", "properties":{
                "path":{"type":"string"}, "purpose":{"type":"string"},
                "edits":{"type":"array", "minItems":1, "maxItems":12, "items":{   # MAX_EDITS
                    "type":"object", "properties":{"old_text":{"type":"string"},"new_text":{"type":"string"}},
                    "required":["old_text","new_text"], "additionalProperties":False}}},
             "required":["path","edits"], "additionalProperties":False}]}},
    },
    "required": ["title", "files"],
})
PLAN_SYSTEM = ("You are the planning instrument of Runesmith, a careful development runtime. You write practical, "
               "honest plans for the owner of a folder. Reply with one JSON object only.")
DRAFT_SYSTEM = ("You are the building instrument of Runesmith. Implement one bounded milestone change while "
                "preserving existing functionality. Prefer exact edits for existing files, complete content for "
                "new files. No skeletons or placeholder implementations. Reply with one JSON object only.")


class PlannerUnavailable(RuntimeError):
    """No model is set up for planning, or it did not answer."""


class SkippedByOwner(RuntimeError):
    """The owner skipped the chat-relay request: nothing is saved, and the plan and the drafts stay as they were."""


def source_context(ws, limit: int = 48000, *, snapshot=None) -> dict[str, Any]:
    """Bounded, deterministic source bytes, not just filenames. Never follow links.

    Kept outside the model response so that the host, not the author, binds edits
    to the exact version inspected before the call.
    """
    from runesmith.app.snapshots import collect_snapshot
    snapshot = snapshot if snapshot is not None else collect_snapshot(ws)
    from runesmith.app.source_focus import select_context
    return select_context(ws, snapshot, limit)


def milestone_contract(ws, milestone: dict) -> str:
    plan=ws.plan() or {}
    material={"version":plan.get('version'),
              "milestone":{k:milestone.get(k) for k in ('id','title','detail','track','done_when')}}
    if milestone.get('parent_id'):
        parent=next((m for m in plan.get('milestones',[]) if m['id']==milestone['parent_id']),{})
        material['parent']={k:parent.get(k) for k in ('id','title','detail','done_when')}
        material['depends_on']=milestone.get('depends_on',[])
    return hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest()


# A prerequisite the owner dropped no longer blocks: it is not needed any more, and the goal's own checks still judge
# the result. Dropping one used to leave its goal "Waiting for" it forever (journey J2-B8).
SETTLED = ('done', 'dropped')


def milestone_ready(plan, milestone):
    states={m['id']:m.get('status') for m in (plan or {}).get('milestones',[])}
    return milestone.get('status') in ('open','doing') and all(
        states.get(key) in SETTLED for key in milestone.get('depends_on',[]))


def plan_readiness(plan):
    milestones = (plan or {}).get('milestones', [])
    by_id = {m['id']: m for m in milestones}
    return {m['id']: {'ready': milestone_ready(plan, m),
            'unmet': [{'id': key, 'title': by_id.get(key, {}).get('title', 'Missing prerequisite'),
                       'status': by_id.get(key, {}).get('status', 'missing')}
                      for key in m.get('depends_on', []) if by_id.get(key, {}).get('status') not in SETTLED]}
            for m in milestones}


def ready_milestones(plan):
    """Every milestone that can be worked on now, in the builder's order: in progress first, then open."""
    return [m for state in ('doing','open') for m in (plan or {}).get('milestones',[])
            if m.get('status')==state and milestone_ready(plan,m)]


def next_milestone(plan):
    return next(iter(ready_milestones(plan)),None)


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
                    "pages_with_viewport", "pages_with_title", "broken_examples", "orphan_pages", "orphan_examples",
                    "todo_notes", "todo_examples"):
            if f.get(key) not in (None, [], ""):
                row[key] = f[key]
        objects.append(row)
    return {"folder": ws.settings()["workspace_name"], "empty": facts.get("empty"),
            "top_level_entries": [e["name"] + ("/" if e["type"] == "dir" else "") for e in facts.get("entries", [])][:60],
            "file_count": facts.get("files"), "kinds_of_files": facts.get("top_extensions"), "objects": objects}


def kept_milestones(ws, plan=None) -> list[dict[str, Any]]:
    """The milestones a redraft keeps exactly as they are (journey J2-B2).

    A model answers with titles only. Saving that answer as the whole plan reopened finished milestones, and gave
    ids by position, so the owner's approved checks, drafts and public expectations (all keyed by milestone id)
    would have attached to other milestones. Kept: anything finished, under way or dropped, anything with drafts,
    checks, proposals, public expectations or a breakdown, and whatever a kept milestone depends on.
    """
    from runesmith.app.acceptance_contracts import expectation_digest
    milestones = ((ws.plan() if plan is None else plan) or {}).get("milestones", [])
    drafted = {d.get("milestone") for d in ws.drafts()}
    proposed = {p.stem for p in (ws.home / "acceptance-proposals").glob("*.json")}

    def linked(m):
        return (m.get("status") != "open" or m["id"] in drafted or m["id"] in proposed
                or m.get("breakdown_id") or m.get("parent_id") or m.get("decomposed_by")
                or (ws.home / "acceptance" / (m["id"] + ".py")).exists() or expectation_digest(ws, m["id"]))
    keep = {m["id"] for m in milestones if linked(m)}
    grew = True
    while grew:
        grew = False
        for m in milestones:
            for prerequisite in m.get("depends_on", []) if m["id"] in keep else []:
                if prerequisite not in keep:
                    keep.add(prerequisite)
                    grew = True
    return [m for m in milestones if m["id"] in keep]


def _fresh_ids(ws, plan, count: int) -> list[str]:
    """New milestone ids that were never used here: not in the plan, a draft or a checks file."""
    used = {m.get("id") for m in (plan or {}).get("milestones", [])} | {d.get("milestone") for d in ws.drafts()}
    used |= {p.stem for p in (ws.home / "acceptance").glob("*.py")} | {p.stem for p in (ws.home / "acceptance-proposals").glob("*.json")}
    n = max((int(i[1:]) for i in used if isinstance(i, str) and re.fullmatch(r"m\d+", i)), default=0)
    ids = []
    while len(ids) < count:
        n += 1
        if f"m{n}" not in used:
            ids.append(f"m{n}")
    return ids


def plan_prompt(ws) -> str:
    from runesmith.app.work_modes import prompt_context, configuration
    brief = ws.brief()
    kept = kept_milestones(ws)
    packet = {
        "task": ("Draft a development plan for this folder. Use the owner's brief and blueprints as the source of "
                 "intent; use the map for what exists now. Milestones must be concrete and checkable, ordered, and "
                 "grouped into a few named tracks (for example: Foundation, Features, Quality, Docs). Keep it to what "
                 "the owner's explicit brief, goals and selected blueprints support. "
                 + ("If those inputs are absent, you may propose a likely useful purpose from the map and source; label "
                    "it and its goals as assumptions, not owner requirements. " if configuration(ws)['infer_purpose'] else
                    "Purpose inference is OFF: do not invent a purpose, audience or goals absent from explicit owner inputs. "
                    "Historical inferred suggestions remain proposals, not newly approved owner intent. ") +
                 "Ask only for material authority or "
                 "high-impact choices that cannot safely be inferred. Do not assume permission for live operations."),
        "work_policy": prompt_context(ws),
        "folder_map": _workspace_summary(ws),
        "owner_goals": [g["text"] for g in ws.goals() if g["status"] == "active"],
        "owner_brief": brief.get("text") or "(no brief written yet)",
        "current_plan": ws.plan(),
        "proposed_goalposts": ws.goalposts(),
        "output": {"summary": "3-6 sentences: what will be built and the approach",
                   "tracks": "2-5 tracks, each {name, purpose}",
                   "milestones": ("1-12 further milestones, each {title, detail, track, done_when}: only work that is "
                                  "still to do, never one of kept_milestones again" if kept else
                                  "4-12 milestones, each {title, detail, track, done_when}"),
                   "first_steps": "up to 5 concrete next actions",
                   "questions": "up to 5 decisions only the owner can make",
                   "assumptions": "explicit inferred purpose/goals and uncertainties; never evidence of achievement"},
    }
    if kept:
        packet["kept_milestones"] = [{"title": m["title"], "status": m.get("status"), "done_when": m.get("done_when", "")}
                                     for m in kept]
        packet["task"] += (" Some milestones are finished, under way or carry the owner's checks (kept_milestones): "
                           "they stay exactly as they are and are not yours to repeat, reword or reopen. Plan only what "
                           "is still to do, including anything new in the owner's goals.")
    text = json.dumps(packet, ensure_ascii=False, indent=1)
    blueprints = ws.blueprint_text()
    if blueprints:
        text += "\n\n=== BLUEPRINT DOCUMENTS (chosen by the owner) ===\n" + blueprints
    notes = ws.notes_for_plan()
    if notes:
        text += "\n\n" + notes
    return text


def draft_prompt(ws, milestone: dict[str, Any], context: dict | None = None, *, memories=None, revision=None,
                 revision_view=None, ignored_attempt_ids=()) -> str:
    from runesmith.app.work_modes import prompt_context
    from runesmith.app.acceptance_contracts import expectations, owner_feedback
    from runesmith.app.workspace import _read_json
    from runesmith.app.build_memory import _check_summary, recall_for_milestone
    memories = recall_for_milestone(ws, milestone) if memories is None else memories
    plan = ws.plan() or {}
    failed = [_read_json(p,{}) for p in (ws.home/'build-attempts').glob('*.json') if p.name not in ignored_attempt_ids]
    failed = sorted((a for a in failed if a.get('contract') == milestone_contract(ws,milestone) and a.get('error')),
                    key=lambda a:a.get('utc',''), reverse=True)[:3]
    revisions = [d for d in ws.drafts() if d.get('contract') == milestone_contract(ws,milestone)
                 and d.get('state') == 'needs_revision']
    if revision is not None:
        revisions = [revision]
    candidate = None
    if revisions:
        previous = revisions[0]
        candidate = {'id':previous['id'], 'status':'not applied; proposed bytes to revise', 'files':[], 'omitted':[]}
        verification = previous.get('verification') or {}
        candidate['verification'] = {
            'status': verification.get('status', 'unknown'),
            'detail': str(verification.get('detail') or '')[:400],
            'project_checks': _check_summary(verification.get('project_checks')),
            'owner_acceptance': owner_feedback(ws, verification),
            'instruction': ('Resolve every listed owner-acceptance failure while preserving passing behavior. '
                            'The candidate is unapplied; revise it against the supplied current source.'),
        }
        used = 0
        for f in previous['files']:
            if used + len(f['content']) <= 40000:
                candidate['files'].append({'path':f['path'],'content':f['content']})
                used += len(f['content'])
            else:
                candidate['omitted'].append(f['path'])
    packet = {
        "task": ("Implement the next small complete step of this milestone, inside the owner's folder. Paths are relative to the folder "
                 "root and use forward slashes. Keep it small: at most 8 files. Use small exact edits for existing files "
                 "when practical; only new files require complete content. Prefer the conventions "
                 "the folder already uses. When documentation already exists, do not emit changes to it. "
                 "Describe run instructions in the draft's why field instead."),
        "milestone": milestone,
        "work_policy": prompt_context(ws),
        "public_acceptance": expectations(ws, milestone['id']),
        "revision_scope": ({'instruction':'Revise this selected candidate with a small exact edit to satisfy the public acceptance expectations. Retain its other working behavior and files.',
                            'candidate':revision['id'],'paths':[f['path'] for f in revision['files']]}
                           if revision else None),
        "parent_milestone": next((m for m in plan.get('milestones',[]) if m['id']==milestone.get('parent_id')),None),
        # The goal a prerequisite serves is judged by its own approved checks; its builder chose `export --output`
        # where the goal's checks run `export --file` (journey J2-G2).
        "parent_public_acceptance": expectations(ws, milestone['parent_id']) if milestone.get('parent_id') else None,
        "plan_summary": plan.get("summary"),
        "proposed_goalposts": [g for g in (ws.goalposts() or {}).get("goalposts", [])
                               if not g.get("milestone_ids") or milestone["id"] in g["milestone_ids"]
                               or milestone.get('parent_id') in g['milestone_ids']],
        "folder_map": _workspace_summary(ws),
        "owner_brief": ws.brief().get("text") or "(no brief written yet)",
        "source_context": context if context is not None else source_context(ws),
        "allowed_build_paths": ws.settings().get('build_paths', []),
        "recent_host_refusals": [{'error':a['error'],'feedback':a.get('feedback')} for a in failed],
        "historical_build_observations": memories,
        "candidate_to_revise": candidate,
        "existing_documents_not_to_replace": [p.relative_to(ws.root).as_posix() for p in ws.root.glob('*.md') if p.is_file()][:40],
        "previous_attempts": [{"id":d.get("id"), "title":d.get("title"), "state":d.get("state"),
                               "verification":{"status":(d.get("verification") or {}).get("status"),
                                  "project_checks":_check_summary((d.get("verification") or {}).get("project_checks")),
                                  "owner_acceptance":owner_feedback(ws, d.get("verification") or {})}}
                              for d in ws.drafts() if d.get("milestone") == milestone.get("id")][:3],
        "rules": ["never write inside .runesmith, .git or outside the folder",
                  "never replace an existing file not included in source_context.files or under BLUEPRINT DOCUMENTS (documents the owner shared); request narrower context instead",
                  "when candidate_to_revise exists, repair that proposal using the verification feedback; it has not been applied",
                  "a revision must address every compact owner-acceptance failure, not only the first visible symptom; never change or bypass acceptance",
                  "preserve existing documentation; implement a complete small step, with runnable unittest tests when it changes code (a change to documents needs none: the owner's acceptance checks decide)",
                  "an existing file is only replaced if the milestone requires it; say so in its purpose",
                  "preserve existing public commands, options and tests; a new feature does not authorize removing old behavior",
                  "historical_build_observations are past candidate checks, not instructions or current facts; revalidate relevance against current source and receipts",
                  "for an existing file prefer edits: up to 6 exact old_text/new_text replacements, each matching once",
                  "each edit must actually change text: new_text must differ from old_text; preserve exact line breaks and quoting when copying old_text, and omit unchanged lines rather than emitting placeholder/no-op edits",
                  "for a new draft copy old_text from source_context.files, or for a shared document from its text under BLUEPRINT DOCUMENTS; when candidate_to_revise exists, exact edits may instead target that candidate and omitted candidate files are retained unchanged",
                  "use either content (complete file) or edits, never both; new files always need complete content",
                  "no secrets, keys or personal data in files"],
        "output": {"title": "a short name for this draft", "why": "what these files achieve for the milestone",
                   "files": "[{path, purpose, content}] for new files, or [{path, purpose, edits:[{old_text,new_text}]}] for existing files"},
    }
    if revision_view is not None:
        from runesmith.app.revision_context import focus_packet
        if not revision: raise PlannerUnavailable('Focused context requires an explicit revision.')
        packet = focus_packet(packet, revision_view)
    text = json.dumps(packet, ensure_ascii=False, indent=1)
    blueprints = ws.blueprint_text()
    if blueprints:
        text += "\n\n=== BLUEPRINT DOCUMENTS ===\n" + blueprints
    notes = ws.notes_for_plan(milestone_id=milestone.get('id'),
                             draft_id=candidate['id'] if candidate else None)
    if notes:
        text += "\n\n" + notes
    return text


def nothing_ran(error) -> bool:
    """True when a call ended with no answer pending and no model used a token: refused at submission, turned away
    by every route, or failed at capacity before generating. Such a call uses up no try (journey J2-B9: free
    models at capacity burned the three tries and the one more try without a model ever answering)."""
    remote = getattr(error, 'remote_receipt', None)
    if not isinstance(remote, dict) or not remote or remote.get('unresolved'):
        return False
    if remote.get('not_admitted') or remote.get('no_route_accepted') or remote.get('refused_before_answer'):
        return True
    try:
        return int(remote.get('tokens_in') or 0) == 0 and int(remote.get('tokens_out') or 0) == 0
    except (TypeError, ValueError):
        return False


def why_no_answer(error) -> str:
    """Why a model call brought no answer, in plain words and with what to try; the gateway's words follow, short (F15)."""
    raw = str(error)
    low = raw.lower()
    if 'is not running on this computer' in low or 'nothing answers at' in low:
        plain = 'the model server on this computer is not running: start it, then try again'
    elif 'unresolved' in low:
        plain = 'the answer has not arrived yet; Runesmith kept the request and will not send it twice'
    elif 'timeout' in low or 'timed out' in low:
        plain = ('the model did not answer in time (a free service may be busy): try again later, '
                 'or put another model first under Thinking power')
    elif any(word in low for word in ('capacity', 'rate_limited', 'overloaded', 'daily_request_cap', '429')):
        plain = ('the model is busy or at its free limit right now: try again later, '
                 'or put another model first under Thinking power')
    elif any(word in low for word in ('auth_failed', 'token unavailable', '401', '403')):
        plain = 'the model service refused the key or token: check it under Thinking power'
    else:
        plain = 'the model did not answer'
    return f'{plain} ({raw[:160]})'


def _call(ws, router, prompt: str, system: str, schema: dict, key: str, max_tokens: int):
    try:
        outcome = router.call("plan", prompt=prompt, system=system, schema=schema, max_tokens=max_tokens, key=key)
    except KeyError as error:
        raise PlannerUnavailable("no model is set up for planning: add one under Thinking power") from error
    except TransportCensored as error:
        failure=PlannerUnavailable(why_no_answer(error))
        failure.remote_receipt=error.receipt
        raise failure from error
    if isinstance(outcome.data, dict) and outcome.data.get("skipped_by_owner"):
        raise SkippedByOwner("you skipped the request, so nothing changed")
    if not outcome.ok and outcome.error_kind == "config":
        failure = PlannerUnavailable(outcome.error or "the model service refused this request")
        if (outcome.receipt or {}).get("refused_before_answer"):
            failure.remote_receipt = dict(outcome.receipt)    # refused before answering: no try is used (J2-B9)
        raise failure
    if not outcome.ok or not isinstance(outcome.data, dict):
        raise PlannerUnavailable(f"the model's answer was not usable: {(outcome.error or 'no JSON')[:200]}")
    missing = [k for k in schema.get("required", []) if k not in outcome.data]
    if missing:                                     # never save half an answer over a plan the owner has
        raise PlannerUnavailable(f"the model's answer has no {' or '.join(missing)}, so nothing was saved")
    by = outcome.receipt.get("answered_by") or outcome.receipt.get("model")
    return outcome.data, by


def draft_plan(ws, router, *, checkpoint=lambda: None, automatic=False) -> dict[str, Any]:
    from runesmith.app.work_modes import require_planning, planning_direction
    from runesmith.app.workspace import WorkspaceError, _write_json, _now
    from runesmith.canon import digest
    checkpoint()
    binding = require_planning(ws, automatic=automatic)
    explicit = planning_direction(ws)['explicit']
    data, by = _call(ws, router, plan_prompt(ws), PLAN_SYSTEM, PLAN_SCHEMA,
                     f"plan-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}", 6000)
    data["drafted_by"] = by
    data['purpose_origin'] = {'kind': 'owner-directed' if explicit else 'inferred',
                              'policy_revision': binding['policy_revision'],
                              'direction_digest': binding['direction_digest']}
    try:
        with ws._lock:
            checkpoint()
            if require_planning(ws, automatic=automatic) != binding:
                raise WorkspaceError('Planning inputs or switches changed during authoring.')
            current = ws.plan()
            kept = kept_milestones(ws, current)
            # Kept milestones stay first, as they were; the answer adds only new work, under ids never used here.
            titles = {m["title"].strip().casefold() for m in kept}
            further = [m for m in data.get("milestones") or []
                       if isinstance(m, dict) and str(m.get("title") or "").strip()
                       and str(m["title"]).strip().casefold() not in titles]
            ids = _fresh_ids(ws, current, len(further)) if kept else [f"m{i + 1}" for i in range(len(further))]
            for m, new_id in zip(further, ids):
                m.pop("status", None)                  # a model never marks work done, nor picks an id
                m["id"] = new_id
            return ws.save_plan(dict(data, milestones=further), kept=kept)
    except Exception as error:
        # Retain a paid/manual answer without installing stale intent or silently
        # retrying it through the automatic empty-folder build path.
        key = digest({'binding': binding, 'answer': data}).split(':', 1)[-1]
        _write_json(ws.home / 'held-plans' / (key + '.json'), {
            'id': key, 'state': 'held', 'utc': _now(), 'author': by, 'binding': binding,
            'answer': data, 'reason': type(error).__name__ + ': ' + str(error)[:500]})
        ws.ledger.append('plan.held', {'id': key, 'author': by, 'reason': str(error)[:300]})
        raise


def _with_shared_documents(ws, context: dict[str, Any]) -> dict[str, Any]:
    """The author's view: shown source files, plus each document the owner shared whose whole text it was shown.

    Documents are never in source_context; a ticked document reaches the author in full under BLUEPRINT DOCUMENTS
    (unless the 12,000-character bound cut it). An edit to it is bound to that text and its bytes, exactly like an
    edit to a shown source file; verification later refuses it if the file changed (journey J4-G3).
    """
    shown = ws.blueprint_text()
    files, hashes = dict(context.get('files') or {}), dict(context.get('file_hashes') or {})
    for entry in ws.brief().get('blueprints', []):
        rel = entry.get('path') if isinstance(entry, dict) else None
        if not rel or rel in files or not ws._safe_rel(rel, allow_missing=False):
            continue
        path = ws.root / rel
        try:
            text, data = path.read_text(encoding='utf-8', errors='replace'), path.read_bytes()
        except OSError:
            continue
        if f"--- {rel} ---\n{text}" in shown:
            files[rel], hashes[rel] = text, hashlib.sha256(data).hexdigest()
    return dict(context, files=files, file_hashes=hashes)


def _apply_one_edit(text: str, edit, rel: str) -> str:
    """One exact edit. If its old text occurs nowhere exactly, the same lines at a uniformly different indentation
    are accepted when they occur exactly once, and the new text is shifted by the same amount.

    Journey J2: a free model's edit wrote 8 spaces where the file has 4, and the whole answer was refused. Only a
    uniform shift of spaces is forgiven; everything else is refused as before, and the checks judge the result.
    The repair organ's own exact edits are unchanged.
    """
    from runesmith.organs.repair import apply_edits
    # Only the old and new text make an edit. A free model labelled each edit with its "purpose", and the whole
    # answer was refused as an invalid edit schema (journey J11-G13, the SVG milestone's first try).
    if isinstance(edit, dict):
        edit = {key: edit[key] for key in ('old_text', 'new_text') if key in edit}
    try:
        return apply_edits({rel: text}, [dict(edit, path=rel)], {rel})[rel]
    except ValueError as error:
        if "did not match exactly once" not in str(error):
            raise
        shifted = _reindented(text, edit.get("old_text"), edit.get("new_text"))
        if shifted is None:
            shifted = _quotes_unescaped(text, edit.get("old_text"), edit.get("new_text"), rel)
        if shifted is None:
            shifted = _first_line_unindented(text, edit.get("old_text"), edit.get("new_text"), rel)
        if shifted is None:
            raise
        return shifted


def _first_line_unindented(text, old, new, rel=''):
    """The edit, when its old text occurs nowhere as written but, without its first line's extra leading whitespace,
    exactly once at the start of a line (journey J11-G26: Gemini indented only the first line of '  if (data.project.
    style === "runes") {', which the file has flush left). The new text loses the same extra indentation. Anything else
    is refused as before, and the checks judge the result."""
    if (not isinstance(old, str) or not isinstance(new, str) or '\n' not in old or text.count(old) != 0
            or not str(rel).lower().endswith(QUOTE_ESCAPE_FILES)):
        return None
    first, rest = old.split('\n', 1)
    indent = first[:len(first) - len(first.lstrip(' \t'))]
    if not indent or not first.strip() or not new.startswith(indent):
        return None
    body = first[len(indent):] + '\n' + rest
    # Whole lines only, in code files only (review: a match ending mid-line rewrote a string literal's contents, and a
    # README's code fence was reindented).
    starts = [m.start() for m in re.finditer(re.escape(body), text)
              if not text[text.rfind('\n', 0, m.start()) + 1:m.start()].strip(' \t')
              and (body.endswith('\n') or text[m.end():m.end() + 1] in ('', '\n'))]
    if len(starts) != 1:
        return None
    return text[:starts[0]] + new[len(indent):] + text[starts[0] + len(body):]


QUOTE_ESCAPE_FILES = ('.js', '.mjs', '.cjs', '.py')


def _quotes_unescaped(text, old, new, rel=''):
    """The edit, when its old text occurs nowhere as written but, without a backslash before each quote, exactly once:
    the model escaped the quotes of the code it quoted (journey J11-G22: Nemotron wrote '<svg width=\"' for the file's
    '<svg width="'). The new text is read the same way. Only in JS and Python files, where the model quotes code;
    anything else is refused as before (review: a correct but repeated old text was redirected into a comment, and a
    README got a stray backslash), and the checks judge the result."""
    if (not isinstance(old, str) or not isinstance(new, str) or '\\' not in old
            or not str(rel).lower().endswith(QUOTE_ESCAPE_FILES) or text.count(old) != 0):
        return None
    plain = re.sub(r'\\(["\'])', r'\1', old)
    if plain == old or text.count(plain) != 1:
        return None
    return text.replace(plain, re.sub(r'\\(["\'])', r'\1', new), 1)


def _edit_key(edit) -> tuple[str, str] | None:
    if (isinstance(edit, dict) and isinstance(edit.get('old_text'), str) and isinstance(edit.get('new_text'), str)
            and edit['old_text'] and edit['old_text'] != edit['new_text']):
        return edit['old_text'], edit['new_text']
    return None


def _repeated(edits) -> dict[tuple[str, str], int]:
    """The same exact edit given more than once, and how often (journey J2-G3).

    For m8 a free model gave `books = load_books(path)` -> `books = load_books(Path(args.storage_file))` four times,
    once for each place it occurs, and the whole answer was refused because that text is not unique. When the same
    edit is given exactly as often as its old text occurs, every place is replaced (see _replace_every); any other
    count is refused.
    """
    counts: dict[tuple[str, str], int] = {}
    for edit in edits:
        if (key := _edit_key(edit)) is not None:
            counts[key] = counts.get(key, 0) + 1
    return {key: n for key, n in counts.items() if n > 1}


def _replace_every(text: str, key: tuple[str, str], given: int) -> str:
    found = text.count(key[0])
    if found != given:
        raise ValueError(f'the same edit was given {given} times, but its old_text occurs {found} times in the current '
                         'file')
    return text.replace(key[0], key[1])


def _reindented(text: str, old, new) -> str | None:
    if not isinstance(old, str) or not isinstance(new, str) or not old.strip() or "\t" in old + new + text or "\r" in text:
        return None
    old_lines, new_lines, lines = old.rstrip("\n").split("\n"), new.rstrip("\n").split("\n"), text.split("\n")

    def indent(line):
        return len(line) - len(line.lstrip(" "))

    found = []
    for start in range(len(lines) - len(old_lines) + 1):
        block = lines[start:start + len(old_lines)]
        shifts = {indent(have) - indent(want) for have, want in zip(block, old_lines) if want.strip()}
        if (len(shifts) == 1 and all(have.strip() == want.strip() for have, want in zip(block, old_lines))
                and all(not have.strip() for have, want in zip(block, old_lines) if not want.strip())):
            found.append((start, shifts.pop()))
    if len(found) != 1 or found[0][1] == 0:
        return None
    start, shift = found[0]
    moved = []
    for line in new_lines:
        if not line.strip():
            moved.append(line)
        elif shift > 0:
            moved.append(" " * shift + line)
        elif indent(line) >= -shift:
            moved.append(line[-shift:])
        else:
            return None
    lines[start:start + len(old_lines)] = moved                # whole lines: line ends are kept as they were
    return "\n".join(lines)


def admit_answer_files(ws, context: dict[str, Any], raw_files, *, allowed_paths: set[str] | None = None,
                       revision_files: dict[str, dict] | None = None):
    """Turn one immutable model answer into host-bound candidate bytes.

    Exact edits are replayed against the frozen current source.  During an
    explicit revision, an edit may instead match the prior unapplied candidate
    exactly; the host then materializes full candidate bytes bound to the
    unchanged real source.  Neither path gets fuzzy matching or extra paths.
    """
    context = _with_shared_documents(ws, context)
    files = copy.deepcopy([f for f in (raw_files or []) if isinstance(f, dict)])
    admitted = []
    for f in files:
        rel = ws._safe_rel(str(f.get("path") or ""))
        if not rel:
            raise PlannerUnavailable("the draft included an invalid path")
        if allowed_paths is not None and rel not in allowed_paths:
            raise PlannerUnavailable(f"the corrected answer broadened its path set: {rel}")
        if 'edits' in f:
            candidate=(revision_files or {}).get(rel,{}).get('content')
            if 'content' in f or (rel not in context['files'] and not isinstance(candidate,str)):
                raise PlannerUnavailable('Exact edits require a fully shown current or candidate file and no content field.')
            edit_index = None
            try:
                if not isinstance(f['edits'],list) or not 1<=len(f['edits'])<=MAX_EDITS:
                    raise ValueError(f'Provide 1-{MAX_EDITS} exact edits.')
                bases=[('current',context['files'][rel])] if rel in context['files'] else []
                if revision_files and rel in revision_files:
                    if isinstance(candidate,str) and candidate!=context['files'].get(rel):
                        # Revisions preserve the selected candidate's other changes.
                        # Fall back to live source only if exact candidate edits fail.
                        bases.insert(0, ('candidate',candidate))
                errors=[];proposed=None
                for base_name,base_text in bases:
                    try:
                        value=base_text;repeated,done=_repeated(f['edits']),set()
                        for edit_index,edit in enumerate(f['edits']):
                            key=_edit_key(edit)
                            if key in repeated:
                                if key not in done:
                                    value=_replace_every(value,key,repeated[key]);done.add(key)
                                continue
                            value=_apply_one_edit(value,edit,rel)
                        proposed=value;f['revision_base']=base_name;break
                    except (ValueError,TypeError,KeyError) as candidate_error:
                        errors.append(candidate_error)
                if proposed is None:
                    raise errors[-1]
                f['content']=proposed
            except (ValueError, TypeError, KeyError) as error:
                feedback={'path':rel,'scope':'Unapplied candidate; source excerpt is from the actual current file.',
                          'admitted_paths':list(admitted)}
                if edit_index is not None:
                    edit=f['edits'][edit_index]
                    old=edit.get('old_text','') if isinstance(edit,dict) else ''
                    old=old if isinstance(old,str) else ''
                    candidate_text=(revision_files or {}).get(rel,{}).get('content','')
                    searchable=context['files'].get(rel,'')+'\n'+candidate_text
                    lines=searchable.splitlines()
                    anchors=[line.strip() for line in old.splitlines() if len(line.strip())>5]
                    start=next((n for anchor in anchors for n,line in enumerate(lines) if line.strip()==anchor),None)
                    # A quoted line found only inside a longer line: the model quoted what the program writes, not its
                    # code (journey J11-G28: the excerpt was empty, and Surfaces' model repeated it four times).
                    inside=None if start is not None else next((n for anchor in anchors for n,line in enumerate(lines)
                                                                 if anchor in line),None)
                    start=start if start is not None else inside
                    excerpt='' if start is None else '\n'.join(f'{n+1}: {lines[n]}' for n in range(max(0,start-1),min(len(lines),start+len(old.splitlines())+4)))
                    feedback.update(edit_index=edit_index+1,requested_old_text=old[:800],source_excerpt=excerpt[:1600],
                                    candidate_base_available=bool(candidate_text))
                    # Only when every quoted line sits in a string literal (right after a quote): stale code such as
                    # "x = 10" against "x = 100" is not output (verifier of J11-G28).
                    quoted=lambda anchor,line:(anchor in line and line[:line.find(anchor)].rstrip()[-1:] in ('"',"'",'`'))
                    if inside is not None and all(any(quoted(anchor,line) for line in lines) for anchor in anchors):
                        feedback['hint']=(f'Each line of this old_text appears in {rel} only inside a longer line, for example '
                                          f'line {inside+1}: {lines[inside].strip()[:200]} . old_text must quote the file\'s own '
                                          'lines exactly as they are (its code), not the text the program writes.')
                failure=PlannerUnavailable(f'Exact edit refused for {rel}: {error}')
                failure.feedback=feedback
                raise failure from error
        if rel in context["files"]:
            f["base"] = context["files"][rel]
            f["expected_sha256"] = context['file_hashes'][rel]
        elif (ws.root / rel).exists():
            raise PlannerUnavailable(f"refused an unseen replacement: {rel}; narrow the milestone or source packet")
        else:
            f.pop("base", None)
            f.pop("expected_sha256", None)
            f["expected_absent"] = True
        admitted.append(rel)
    return files


def admit_revision_answer(ws,context,raw_files,revision=None,*,allowed_paths=None):
    """Admit an answer and carry forward untouched bytes from its candidate."""
    context=_with_shared_documents(ws,context)
    revision_files={f['path']:f for f in revision.get('files',[])} if revision else {}
    files=admit_answer_files(ws,context,raw_files,allowed_paths=allowed_paths,
                            revision_files=revision_files)
    returned={f['path'] for f in files}
    for rel,prior in revision_files.items():
        if rel in returned:continue
        if allowed_paths is not None and rel not in allowed_paths:
            raise PlannerUnavailable(f'the revision broadened its retained path set: {rel}')
        if rel in context['files']:
            retained=copy.deepcopy(prior);retained['base']=context['files'][rel]
            retained['expected_sha256']=context['file_hashes'][rel]
            retained.pop('expected_absent',None)
        elif not (ws.root/rel).exists():
            retained=copy.deepcopy(prior);retained.pop('base',None);retained.pop('expected_sha256',None)
            retained['expected_absent']=True
        else:
            raise PlannerUnavailable(f'refused an unseen retained candidate path: {rel}')
        retained['retained_from']=revision['id'];files.append(retained)
    return files


def draft_files(ws, router, milestone_id: str | None = None, *, revision=None, attempt_id=None, admission_guard=None,
                revision_operation=None) -> dict[str, Any]:
    from runesmith.app.author_recovery import pending_authors, prepare_packet, admit_packet
    from runesmith.app.acceptance_contracts import expectation_digest
    plan = ws.plan() or {}
    milestones = plan.get("milestones") or []
    milestone = next((m for m in milestones if m["id"] == milestone_id), None) if milestone_id else next_milestone(plan)
    # Only this milestone's own late answer holds it back; another milestone's does not (journey J11-B6).
    if pending_authors(ws, milestone=milestone['id'] if milestone else None):
        raise PlannerUnavailable('A saved remote author request is unresolved; recover it before another call.')
    if milestone is None or not milestone_ready(plan,milestone):
        raise PlannerUnavailable("there is no ready open milestone to draft for; prerequisites must be done first")
    from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
    snapshot = collect_snapshot(ws)
    context = source_context(ws, snapshot=snapshot)
    if context.get('focus_errors'):
        raise PlannerUnavailable('Selected author source cannot fit or is unavailable; inspect Author context before another call.')
    contract = milestone_contract(ws, milestone)
    public_digest = expectation_digest(ws, milestone['id'])
    if attempt_id is not None:
        # The planner reads source again after Build reserves the call. Do not
        # charge a newly changed source/contract to the old allowance.
        import re
        from runesmith.app.workspace import _read_json
        if not isinstance(attempt_id,str) or not re.fullmatch(r'[0-9a-f]{32}\.json',attempt_id):
            raise PlannerUnavailable('Invalid ordinary author reservation.')
        reserved=_read_json(ws.home/'build-attempts'/attempt_id,None)
        if (not isinstance(reserved,dict) or reserved.get('state')!='started'
                or reserved.get('contract')!=contract or reserved.get('snapshot_digest')!=snapshot['digest']):
            raise PlannerUnavailable('Ordinary author reservation no longer matches the source or milestone; no call sent.')
    explicit_revision = revision is not None
    if explicit_revision and (revision.get('contract') != contract
                              or revision.get('snapshot_digest') != snapshot['digest']
                              or revision.get('state') != 'needs_revision'):
        raise PlannerUnavailable('Selected revision does not match the active milestone and frozen source.')
    from runesmith.app.revision_context import selected_view
    revision_view = selected_view(ws, revision) if explicit_revision else None
    for previous in ws.drafts():
        if (revision is None and previous.get("state") == "waiting" and previous.get("contract") == contract
                and previous.get("context_digest") == context["digest"]
                and previous.get('public_acceptance_digest') == public_digest
                and previous.get('snapshot_digest') == snapshot['digest']):
            return previous
    freeze_snapshot(ws, snapshot)
    from runesmith.app.build_memory import recall_for_milestone
    from runesmith.app.workspace import _write_json
    memories = recall_for_milestone(ws, milestone)
    prompt = draft_prompt(ws, milestone, context, memories=memories, revision=revision, revision_view=revision_view)
    request_key = f"draft-{milestone['id']}-{time.time_ns()}"
    exposure = {'request_key':request_key, 'state':'prepared', 'memory_ids':[m['id'] for m in memories],
                'observations':memories, 'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                'snapshot_digest':snapshot['digest']}
    exposure_path = ws.home / 'build-memory-exposures' / (request_key + '.json')
    _write_json(exposure_path, exposure)
    ws.ledger.append('build.memory_packet_prepared', {k:v for k,v in exposure.items() if k!='observations'})
    revision=revision or next((d for d in ws.drafts() if d.get('contract')==contract and d.get('state')=='needs_revision'
                   and d.get('snapshot_digest')==snapshot['digest']),None)
    packet=prepare_packet(ws,request_key,milestone=milestone,context=context,contract=contract,
        public_digest=public_digest,exposure=exposure_path.relative_to(ws.home).as_posix(),
        revision=revision,explicit_revision=explicit_revision,attempt_id=attempt_id,revision_view=revision_view,
        revision_operation=revision_operation)
    data, by = _call(ws, router, prompt, DRAFT_SYSTEM, DRAFT_SCHEMA, request_key, 4000 if explicit_revision else 12000)
    _write_json(exposure_path, dict(exposure, state='answer_received', author=by))
    try:
        return admit_packet(ws,packet,data,by,admission_guard=admission_guard)
    except PlannerUnavailable as error:
        _write_json(ws.home/'author-admissions'/(request_key+'.json'),
                    {'state':'rejected','error':str(error)[:500],'feedback':getattr(error,'feedback',None)})
        raise
