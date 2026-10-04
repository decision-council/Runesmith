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

from runesmith.app.runesmith_md import is_own
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
                "new files. A file shown only in parts (source_context.excerpts) may be changed only with exact "
                "edits whose old_text is copied from one of its excerpts. No skeletons or placeholder "
                "implementations: never leave code out with a comment such as '// ...'. Reply with one JSON object only.")


class PlannerUnavailable(RuntimeError):
    """No model is set up for planning, or it did not answer."""


class SkippedByOwner(RuntimeError):
    """The owner skipped the chat-relay request: nothing is saved, and the plan and the drafts stay as they were."""


def source_context(ws, limit: int = 48000, *, snapshot=None, milestone=None, feedback=True, parts_share=1.0,
                   parts_reserve=0, parts=True) -> dict[str, Any]:
    """Bounded, deterministic source bytes, not just filenames. Never follow links.

    Kept outside the model response so that the host, not the author, binds edits
    to the exact version inspected before the call. A file too large to show whole is shown in parts; with a
    `milestone` its excerpts are chosen by that milestone's words (and, with `feedback`, by what the last refused
    answers tried to change), so the same milestone and feedback give the same packet (journey J11-B15, B16).
    """
    from runesmith.app.snapshots import collect_snapshot
    snapshot = snapshot if snapshot is not None else collect_snapshot(ws)
    from runesmith.app.source_focus import select_context
    terms = milestone_terms(ws, milestone, feedback=feedback) if milestone else None
    return select_context(ws, snapshot, limit, terms=terms, parts_share=parts_share, parts_reserve=parts_reserve,
                          parts=parts)


def program_excerpts(ws, milestone: dict, limit: int = 6000) -> dict[str, str]:
    """The parts of the program the Checker is shown (acceptance_proposals.packet), chosen the same way for a smaller
    budget: file -> a short outline and the best-matching excerpts (journey J11-B16: the second model recomputed values
    from the milestone's words without seeing the code that reads them)."""
    from runesmith.app.snapshots import SnapshotUnsupported, collect_snapshot
    from runesmith.app.source_parts import build_parts
    from runesmith.app.workspace import WorkspaceError
    shown, left = {}, limit
    try:
        snapshot = collect_snapshot(ws)
        context = source_context(ws, limit=16000, snapshot=snapshot, milestone=milestone, feedback=False,
                                 parts_share=0.6, parts_reserve=6000)
        terms = milestone_terms(ws, milestone, feedback=False)
        for rel in context.get('excerpts') or {}:
            part = build_parts(rel, snapshot['files'][rel].decode('utf-8-sig').replace('\r\n', '\n'), terms, left,
                               outline_cap=min(1200, left // 4))
            if part:
                shown[rel] = part['text']
                left -= part['chars']
    except (WorkspaceError, SnapshotUnsupported, OSError):
        return {}                       # the cross-check goes on without the excerpts, as before
    return shown


def milestone_view(ws, observed: dict, snapshot: dict, milestone: dict) -> dict[str, Any]:
    """The source an observation was made of, as this milestone's own words show it: the same files and prioritized
    paths, the parts of large files chosen by the milestone (journey J11-B15). A round reads the folder once and decides
    every milestone from that reading, so this never reads it again."""
    from runesmith.app.source_focus import select_context
    return select_context(ws, snapshot, focus_paths=observed.get('focus_paths'), terms=milestone_terms(ws, milestone))


def _sentences(value):
    """Every text in a nested answer (a check's feedback), in order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _sentences(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _sentences(item)]
    return []


_DRAFT_HEADS: dict = {}


def _light_drafts(ws) -> list[dict[str, Any]]:
    """What the words of a milestone's excerpts need of each saved draft, read from its record only when it changed:
    a draft holds whole files, and a round asks for every ready milestone's words (journey J11-B15)."""
    from runesmith.app.workspace import _read_json
    rows, seen = [], set()
    for path in (ws.home / 'drafts').glob('*/DRAFT.json'):
        try:
            stat = path.stat()
        except OSError:
            continue
        key = str(path)
        seen.add(key)
        known = _DRAFT_HEADS.get(key)
        if known is None or known[0] != (stat.st_mtime_ns, stat.st_size):
            draft = _read_json(path, None)
            known = ((stat.st_mtime_ns, stat.st_size),
                     {k: draft.get(k) for k in ('id', 'milestone', 'contract', 'state', 'utc', 'public_acceptance_digest',
                                                'verification')} if isinstance(draft, dict) else {})
            _DRAFT_HEADS[key] = known
        if known[1]:
            rows.append(known[1])
    for key in [key for key in list(_DRAFT_HEADS) if key.startswith(str(ws.home / 'drafts')) and key not in seen]:
        _DRAFT_HEADS.pop(key, None)
    return rows


def milestone_terms(ws, milestone: dict, *, feedback: bool = True) -> dict[str, Any]:
    """The words a milestone's excerpts of a large file are chosen by (journey J11-B15, B16): identifiers and quoted
    strings of its title, what it should do and done when, and, for a build, of the newest failing checks' sentences
    and, as whole lines, the old_text of the newest refused answers (what the model tried to change: its next call
    is shown those lines). The same milestone and feedback always give the same words."""
    from runesmith.app.acceptance_contracts import draft_owner_feedback
    from runesmith.app.source_parts import extract_terms
    from runesmith.app.workspace import _read_json
    texts = [str(milestone.get(k) or '') for k in ('title', 'detail', 'done_when')]
    anchors: list[str] = []
    wanted: set[str] = set()
    if feedback and milestone.get('id'):
        contract = milestone_contract(ws, milestone)
        refused = []
        for path in (ws.home / 'build-attempts').glob('*.json'):
            row = _read_json(path, {})
            note = row.get('feedback') if isinstance(row, dict) else None
            if not isinstance(note, dict) or row.get('contract') != contract:
                continue
            # A file the last answer could not change because the model was not shown it: this call shows it (the gap
            # closes itself, with no try and no owner), after the prioritized files (review of the merged batch).
            if row.get('state') == 'context_gap' and isinstance(note.get('not_shown'), str):
                wanted.add(note['not_shown'])
            if isinstance(note.get('requested_old_text'), str):
                try:
                    written = path.stat().st_mtime_ns
                except OSError:
                    written = 0
                refused.append((str(row.get('utc') or ''), written, note['requested_old_text']))
        for _, _, old in sorted(refused, key=lambda r: (r[0], r[1]), reverse=True)[:3]:
            anchors += [line.strip() for line in old.splitlines() if len(line.strip()) > 5][:12]
        failing = []
        for draft in _light_drafts(ws):
            if (draft.get('milestone') == milestone['id'] and draft.get('contract') == contract
                    and draft.get('state') == 'needs_revision'):
                failing.append((str(draft.get('utc') or ''), draft))
        for _, draft in sorted(failing, key=lambda r: r[0], reverse=True)[:3]:
            texts.append(' '.join(_sentences(draft_owner_feedback(ws, draft)))[:3000])
    terms = extract_terms(*texts, anchors=anchors)
    return dict(terms, text=' '.join(texts[:3]), wanted=sorted(wanted))


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


def revisable_candidates(ws, drafts, milestone, snapshot_digest) -> list[dict[str, Any]]:
    """The saved drafts a new author call revises, newest rule in one place: a candidate of this milestone's present
    wording, kept for revision, made on today's source and checked by the expectations now in force. The prompt shows
    it, the packet retains its files and the lineage guard counts it by this one rule: a candidate hidden from the
    prompt was still merged into the next draft when each side chose its own (review of J11-G37)."""
    from runesmith.app.acceptance_contracts import expectation_digest
    contract, public = milestone_contract(ws, milestone), expectation_digest(ws, milestone['id'])
    return [d for d in drafts if d.get('contract') == contract and d.get('state') == 'needs_revision'
            and d.get('snapshot_digest') == snapshot_digest and d.get('public_acceptance_digest') == public]


CANDIDATE_CHARS = 40000


def _full_text(ws, context, rel):
    """The whole current text of a file shown in parts, line ends as LF: from the live file when its bytes are the ones
    the parts were made from, else from the frozen snapshot of that source; None when neither is (journey J11-B15)."""
    want = ((context.get('excerpts') or {}).get(rel) or {}).get('sha256')
    if not want:
        return None
    from runesmith.app.snapshots import SnapshotUnsupported, load_snapshot
    found = []
    try:
        found.append((ws.root / rel).read_bytes())
    except OSError:
        pass
    for data in found:
        if hashlib.sha256(data).hexdigest() == want:
            return data.decode('utf-8-sig').replace('\r\n', '\n')
    try:
        data = load_snapshot(ws, context['snapshot_digest'])['files'].get(rel)
    except (SnapshotUnsupported, OSError, KeyError, TypeError, ValueError):
        return None
    if data is not None and hashlib.sha256(data).hexdigest() == want:
        return data.decode('utf-8-sig').replace('\r\n', '\n')
    return None


def candidate_shown(ws, revision, context, milestone):
    """What a revision candidate shows a model, file by file (journey J11-B15): whole while the files fit together, a
    file that does not fit in parts, around the lines the candidate changed and the milestone's words, or, with no room
    for that, not at all. Returns (files, parts, omitted, view): `view` is what the packet records, so a later check
    knows which lines of each candidate file its author saw."""
    from runesmith.app.source_parts import MIN_PART_CHARS, build_parts, changed_blocks
    files, parts, omitted, view, used, terms = [], {}, [], {}, 0, None
    for f in revision['files']:
        path, text = f['path'], f['content']
        if used + len(text) <= CANDIDATE_CHARS:
            files.append({'path': path, 'content': text})
            used += len(text)
            view[path] = {'shown': 'full'}
            continue
        part = None
        if CANDIDATE_CHARS - used >= MIN_PART_CHARS:
            terms = milestone_terms(ws, milestone) if terms is None else terms
            now = context['files'].get(path)
            now = _full_text(ws, context, path) if now is None else now
            part = build_parts(path, text, terms, CANDIDATE_CHARS - used,
                               must=changed_blocks(now, text) if isinstance(now, str) else ())
        if part is None:
            omitted.append(path)
            view[path] = {'shown': 'omitted'}
            continue
        sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        parts[path] = dict(part, sha256=sha)
        used += part['chars']
        view[path] = {'shown': 'parts', 'ranges': part['ranges'], 'lines': part['lines'], 'sha256': sha}
    return files, parts, omitted, view


def draft_prompt(ws, milestone: dict[str, Any], context: dict | None = None, *, memories=None, revision=None,
                 revision_view=None, ignored_attempt_ids=()) -> str:
    from runesmith.app.work_modes import prompt_context
    from runesmith.app.acceptance_contracts import draft_owner_feedback, expectations
    from runesmith.app.workspace import _read_json
    from runesmith.app.build_memory import _check_summary, recall_for_milestone
    memories = recall_for_milestone(ws, milestone) if memories is None else memories
    context = source_context(ws, milestone=milestone) if context is None else context
    plan = ws.plan() or {}
    failed = [_read_json(p,{}) for p in (ws.home/'build-attempts').glob('*.json') if p.name not in ignored_attempt_ids]
    failed = sorted((a for a in failed if a.get('contract') == milestone_contract(ws,milestone) and a.get('error')),
                    key=lambda a:a.get('utc',''), reverse=True)[:3]
    # Only a candidate made on today's source is offered for revision: only then are its edits admitted against it
    # (journey J11-G33: shown a candidate from older source, the model edited that candidate's code, and every answer
    # was refused against the current file, seven times). An older one stays in previous_attempts with its feedback.
    today = context.get('snapshot_digest')
    # Nor one checked by expectations the owner has since withdrawn or replaced: its feedback quotes their sentences
    # (journey J11-G37).
    revisions = revisable_candidates(ws, ws.drafts(), milestone, today)
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
            'owner_acceptance': draft_owner_feedback(ws, previous),     # a supplement's draft too (J11-G37 review)
            'instruction': ('Resolve every listed owner-acceptance failure while preserving passing behavior. '
                            'The candidate is unapplied; revise it against the supplied current source.'),
        }
        # A candidate file too large to show whole is shown in parts too (J11-B15): the lines it changed and the
        # milestone's words, so the next try can repair the code it wrote.
        candidate['files'], parts, candidate['omitted'], _ = candidate_shown(ws, previous, context, milestone)
        if parts:
            candidate['excerpts'] = parts
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
        "source_context": context,
        "allowed_build_paths": ws.settings().get('build_paths', []),
        "recent_host_refusals": [{'error':a['error'],'feedback':a.get('feedback')} for a in failed],
        "historical_build_observations": memories,
        "candidate_to_revise": candidate,
        "existing_documents_not_to_replace": [p.relative_to(ws.root).as_posix() for p in ws.root.glob('*.md')
                                              if p.is_file() and not is_own(p.name)][:40],
        "previous_attempts": [{"id":d.get("id"), "title":d.get("title"), "state":d.get("state"),
                               "verification":{"status":(d.get("verification") or {}).get("status"),
                                  "project_checks":_check_summary((d.get("verification") or {}).get("project_checks")),
                                  "owner_acceptance":draft_owner_feedback(ws, d)}}
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
                  # J11-B15: a file over its cap is shown in parts, and may be changed only where it was shown.
                  "a file listed under source_context.excerpts is shown only in parts: an outline of its declarations, then exact excerpts, each labelled with its lines. Change it only with exact edits whose old_text is copied from ONE excerpt, never from the outline, and never by writing the whole file; an old_text outside the shown lines is refused. A candidate file listed under candidate_to_revise.excerpts is shown the same way",
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


def settled_state(error, otherwise='failed') -> str:
    """The state a refused author call is recorded in: `context_gap` when the model was not shown a file its answer
    changed and the owner can show it, or no model was asked because prioritized files cannot be shown, which uses up
    no try (journey J11-B15), else `otherwise`."""
    return 'context_gap' if getattr(error, 'context_gap', None) else otherwise


def _provider_hint(raw: str) -> str | None:
    from runesmith.app.providers import model_hint
    return model_hint(raw)


def _with_hint(text: str) -> str:
    """A refusal's words, with the replacement the provider named for a retired model (it becomes a button under Thinking power)."""
    from runesmith.app.providers import with_model_hint
    return with_model_hint(text)


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
    elif _provider_hint(raw):
        plain = (f'the service no longer offers this model and suggests {_provider_hint(raw)}: under Thinking power, '
                 'press Test on that model and then the button that offers the switch')
    else:
        plain = 'the model did not answer'
    return f'{plain} ({raw[:160]})'


ANSWER_RECEIPT = re.compile(r'draft-answers/[A-Za-z0-9_.-]+\.json')


def _repeating_authors(ws, contract) -> list[dict[str, str]] | None:
    """Who sent the last two refused answers for this milestone, when both were refused with the same exact edit;
    each as {'instrument', 'model'} (the instrument when the answer's receipt kept it); or None.

    Journey J11-G31: shown each refusal, the file's real lines and a hint, Gemini Flash Lite sent Surfaces the same
    edit quoting the program's output six times (08:14-10:49Z), because every fresh try went to it first again.
    Only refused answers count: a transport failure between two refusals does not hide them (review).
    """
    from runesmith.app.workspace import _read_json
    rows = []
    for path in (ws.home / 'build-attempts').glob('*.json'):
        row = _read_json(path, {})
        feedback = row.get('feedback') if isinstance(row, dict) else None
        if (isinstance(row, dict) and row.get('contract') == contract and isinstance(feedback, dict)
                and isinstance(feedback.get('requested_old_text'), str) and feedback['requested_old_text']):
            try:
                written = path.stat().st_mtime_ns          # records of the same second, in the order written (review)
            except OSError:
                written = 0
            rows.append((str(row.get('utc') or ''), written, feedback))
    last = [feedback for _, _, feedback in sorted(rows, key=lambda r: (r[0], r[1]), reverse=True)[:2]]
    if len(last) < 2 or last[0]['requested_old_text'] != last[1]['requested_old_text']:
        return None
    authors = []
    for feedback in last:
        receipt = feedback.get('answer_receipt')
        answer = _read_json(ws.home / receipt, {}) if isinstance(receipt, str) and ANSWER_RECEIPT.fullmatch(receipt) else {}
        answer = answer if isinstance(answer, dict) else {}
        kept = answer.get('receipt') if isinstance(answer.get('receipt'), dict) else {}
        who = {'instrument': kept.get('instrument') if isinstance(kept.get('instrument'), str) else '',
               'model': answer.get('author') if isinstance(answer.get('author'), str) else ''}
        if not (who['instrument'] or who['model']):
            return None
        authors.append(who)
    return authors


def _rotate_repeating_author(ws, router, contract) -> list[str] | None:
    """Ask the Planner role's other instruments first when one keeps sending the same refused edit (J11-G31). It stays
    last, so a role with one instrument is unchanged; two routes of one instrument count as one. Returns the
    instruments moved last, or None."""
    authors = _repeating_authors(ws, contract)
    roles = getattr(router, 'roles', None)
    names = roles.get('plan') if authors and isinstance(roles, dict) else None
    if not names or len(names) < 2:
        return None
    specs = ws.config().get('instruments') or {}

    def serves(name, who):
        if who['instrument']:
            return who['instrument'] == name
        # An older answer without its instrument: its model string may carry the provider in front ("provider:model",
        # for an OpenAI-compatible instrument its base URL), so it ends with the configured model (review).
        spec = specs.get(name) or {}
        return any(isinstance(m, str) and m and (who['model'] == m or who['model'].endswith(':' + m))
                   for m in [spec.get('model')] + list(spec.get('fallback_models') or []))
    stuck = [name for name in names if all(serves(name, who) for who in authors)]
    if not stuck or len(stuck) == len(names):
        return None
    roles['plan'] = [name for name in names if name not in stuck] + stuck
    ws.ledger.append('build.author_rotated', {'contract': contract, 'models': [who['model'] for who in authors],
                                              'instruments': [who['instrument'] for who in authors], 'asked_last': stuck})
    return stuck


def _call(ws, router, prompt: str, system: str, schema: dict, key: str, max_tokens: int, receipt_out: dict | None = None):
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
        failure = PlannerUnavailable(_with_hint(outcome.error or "the model service refused this request"))
        if (outcome.receipt or {}).get("refused_before_answer"):
            failure.remote_receipt = dict(outcome.receipt)    # refused before answering: no try is used (J2-B9)
        raise failure
    if not outcome.ok or not isinstance(outcome.data, dict):
        raise PlannerUnavailable(f"the model's answer was not usable: {(outcome.error or 'no JSON')[:200]}")
    missing = [k for k in schema.get("required", []) if k not in outcome.data]
    if missing:                                     # never save half an answer over a plan the owner has
        raise PlannerUnavailable(f"the model's answer has no {' or '.join(missing)}, so nothing was saved")
    by = outcome.receipt.get("answered_by") or outcome.receipt.get("model")
    if receipt_out is not None:                     # which instrument answered (review of J11-G31)
        receipt_out.update({k: v for k, v in (outcome.receipt or {}).items() if isinstance(k, str)})
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


def _owner_can_show(ws, wanted):
    """Whether prioritizing these files, beside the ones already prioritized, would show models all of them: what
    Author context accepts (at most 12 files, each within the size limit, together within the source budget)."""
    from runesmith.app.snapshots import SnapshotUnsupported, collect_snapshot
    from runesmith.app.source_focus import MAX_FOCUS_PATHS, focus_settings, select_context
    from runesmith.app.workspace import WorkspaceError
    try:
        paths = list(dict.fromkeys(list(focus_settings(ws)['paths']) + list(wanted)))
        if len(paths) > MAX_FOCUS_PATHS:
            return False
        return not select_context(ws, collect_snapshot(ws), focus_paths=paths)['focus_errors']
    except (WorkspaceError, SnapshotUnsupported):
        return True                     # cannot judge: the owner sees the same error under Author context


def focus_missing(context):
    """Prioritized paths that are gone or hidden. A file that is there but too large, not text or crowded out is an
    omitted file like any other (journey J11-B15 review: a prioritized file passed 40,000 bytes and blocked every
    milestone, also those that never touch it): a milestone that edits it is refused by `_not_shown`."""
    return sorted(path for path, reason in (context.get('focus_errors') or {}).items() if reason == 'not_model_visible')


def focus_problem(context):
    """Plain words for prioritized paths that are no longer files, or None: no call is made while the owner's own
    selection names them, and that uses up no try."""
    missing = focus_missing(context)
    if not missing:
        return None
    return (', '.join(missing) + (' is' if len(missing) == 1 else ' are') + ' prioritized under Author context but is not a '
            'file models can be shown (gone, or hidden). Remove it from the prioritized files under Goals & plan, Author '
            'context. No model was asked, so this used up no try.')


def _prioritized(ws, context, rel):
    """Whether the owner prioritized this file under Author context (a retained selection has no focus of its own)."""
    from runesmith.app.source_focus import focus_settings
    from runesmith.app.workspace import WorkspaceError
    if rel in (context.get('focus_errors') or {}):
        return True
    try:
        return ws is not None and rel in focus_settings(ws)['paths']
    except WorkspaceError:
        return False


def _not_shown(rel, context, ws=None, needed=()):
    """The refusal for an answer that edits or replaces a file the model was not shown (journey J11-B15).

    When the source budget alone kept the file out and the owner can show it (prioritize it, beside the other files
    this change needs), the gap is Runesmith's: the refusal uses up no try, and the milestone waits (`context_gap`).
    A file over the size limit or not UTF-8 can never be shown, and files that cannot be shown together are no gap
    the owner can close: waiting would leave the milestone stuck, so those stay an ordinary failed try, and the words
    say what to change.
    """
    reasons = context.get('omission_reasons') or {}
    reason = reasons.get(rel) or 'packet_budget'
    seen = set(context.get('files') or ()) | set(context.get('omitted') or ())
    # Another file this change needs that can never be shown is the real obstacle, whichever file is met first (review).
    hard = next((p for p in needed if p != rel and reasons.get(p) in ('file_limit', 'not_utf8')), None)
    if reason == 'packet_budget' and hard:
        rel, reason = hard, reasons[hard]
    if (reason == 'packet_budget' and ws is not None
            and not _owner_can_show(ws, [rel] + [p for p in needed if p != rel and p in seen])):
        reason = 'budget_together'
    if reason == 'budget_together':
        words = (f"{rel}, the other files this change needs and the files already prioritized do not fit the source "
                 "budget together, so no model can be shown them all and a change to them cannot be checked. Remove "
                 "prioritized files this step does not need, or split this step into smaller ones.")
    elif reason == 'file_limit':
        # A file over the limit is shown in parts (J11-B15); this is one that cannot be, even then: no line of it is short
        # enough to quote.
        from runesmith.app.workspace import MAX_DRAFT_FILE_BYTES
        try:
            size = (ws.root / rel).stat().st_size if ws is not None else 0
        except OSError:
            size = 0
        if size > MAX_DRAFT_FILE_BYTES:
            words = (f"{rel} is too large to draft ({MAX_DRAFT_FILE_BYTES:,} bytes at most), so a change to it could not be "
                     "kept. Split it into smaller files.")
        else:
            words = (f"{rel} is too large to show a model, even in parts (its lines are too long to quote), so a change to it "
                     "cannot be checked against it. Split it into smaller files.")
        if _prioritized(ws, context, rel):
            words += " It is prioritized under Author context, which cannot show it either: take it out of the list once it is split."
    elif reason == 'not_utf8':
        words = (f"{rel} is not UTF-8 text, so it cannot be shown to a model, and a change to it cannot be checked "
                 "against it. Save it as UTF-8 text, or keep it out of this milestone.")
        if _prioritized(ws, context, rel):
            words += " It is prioritized under Author context, which cannot show it either: take it out of the list."
    else:
        words = (f"{rel} was not shown to the model (the other files filled the source budget), so its change cannot be "
                 f"checked against it. Prioritize {rel} under Goals & plan, Author context, so models see it (the next "
                 "round also shows it by itself); this used up no try.")
    failure = PlannerUnavailable(words)
    # No "path": that names a refusal a correction can repair, and no correction can show the model a file.
    failure.feedback = {'not_shown': rel, 'reason': reason}
    if reason == 'packet_budget':
        failure.context_gap = {'path': rel, 'reason': reason}
    return failure


class _OutsideShown(ValueError):
    """An exact edit whose old text lies on lines of a file the model was shown only in parts, outside every part
    (journey J11-B15). `shown` is the ranges the model was shown."""

    def __init__(self, first, last, count):
        super().__init__(f'old_text is on lines {first}-{last} of {count}, which were not shown')
        self.first, self.last, self.count, self.shown = first, last, count, []


def _inside_shown(before, after, edit, ranges):
    """The shown ranges after an edit that lies inside one of them; _OutsideShown when its old text does not. An exact
    old_text is placed where it occurs; one a forgiving match repaired (indentation, quotes) by the lines it changed."""
    from runesmith.app.source_parts import changed_lines, holding_range, line_span, shifted_ranges, split_lines
    old = edit.get('old_text') if isinstance(edit, dict) else None
    exact, moved = line_span(before, old), changed_lines(before, after)
    # Both: an old text ending in a newline on the last shown line, with a new text that does not end in one, changes the
    # next line too, which was not shown (review of the merged batch).
    span = moved if exact is None else (min(exact[0], moved[0]), max(exact[1], moved[1]))
    index = holding_range(ranges, *span)
    if index is None:
        raise _OutsideShown(span[0], span[1], len(split_lines(before)))
    return shifted_ranges(ranges, index, span[1], len(split_lines(after)) - len(split_lines(before)))


def _replace_every_inside(value, key, given, ranges):
    """_replace_every for a file shown in parts: every place the same edit replaces must lie inside a shown range."""
    from runesmith.app.source_parts import holding_range, split_lines
    text = _replace_every(value, key, given)
    spans, at = [], 0
    while (found := value.find(key[0], at)) != -1:
        spans.append((value.count('\n', 0, found) + 1, value.count('\n', 0, found + len(key[0]) - 1) + 1))
        at = found + len(key[0])
    for first, last in spans:
        if holding_range(ranges, first, last) is None:
            raise _OutsideShown(first, last, len(split_lines(value)))
    each = key[1].count('\n') - key[0].count('\n')
    moved = [[a + each * sum(1 for _, last in spans if last < a), b + each * sum(1 for first, _ in spans if first <= b)]
             for a, b in ranges]
    return text, [pair for pair in moved if pair[1] >= pair[0]]


def _candidate_ranges(candidate_view, rel, candidate, current_in_parts):
    """How a revision candidate's file was shown, as a base for edits: None (whole), the ranges it was shown in, or
    False (not shown, so no edit may quote it). A candidate this call recorded nothing about is trusted as before, unless
    the current file was shown only in parts: then it must have been shown too."""
    view = (candidate_view or {}).get(rel) or {}
    if view.get('shown') == 'parts':
        same = view.get('sha256') == hashlib.sha256(candidate.encode('utf-8')).hexdigest()
        return view.get('ranges') if same and isinstance(view.get('ranges'), list) else False
    if current_in_parts and view.get('shown') != 'full':
        return False
    return None


# Code an answer leaves out (journey J11-G39: renderer.mjs was written as "// ... (renderer logic from motion.mjs)" and
# record.html stopped at "// Recording logic including MediaStreamAudioDestinationNode...", and both passed): a comment
# that stands in for the code. An ordinary comment that ends in "..." is not one.
_LEFT_OUT = (re.compile(r'^(?:\.\.\.|…)'),
             re.compile(r'\bfor brevity\b', re.I),
             re.compile(r'\brest of (?:the )?(?:code|file|function|logic|implementation)\b', re.I),
             re.compile(r'\b(?:code|logic|implementation)\s+(?:is\s+|was\s+)?omitted\b', re.I),
             re.compile(r'\bgoes here\b', re.I),
             re.compile(r'\b(?:code|logic|implementation|handling)\b.*(?:\.\.\.|…)$', re.I))
DOCUMENT_FILES = ('.md', '.markdown', '.txt', '.rst')


def _comment_words(line):
    """The words of a comment line (//, #, /*, * or <!--), or None when the line is not a comment. Python's bare ... is
    a statement, not a comment."""
    text = line.strip()
    for opener in ('<!--', '/*', '//', '#', '*'):
        if text.startswith(opener):
            text = text[len(opener):].strip()
            for closer in ('-->', '*/'):
                if text.endswith(closer):
                    text = text[:-len(closer)].strip()
            return text
    return None


def _refuse_left_out(rel, content, base):
    """Refuse a line the answer ADDS (it is not a line of the base: every line of a new file, the new text of an edit)
    that is a comment standing in for code. An elision already in the base, left untouched, stays."""
    if not isinstance(content, str) or rel.lower().endswith(DOCUMENT_FILES):
        return
    known = {line.strip() for line in base.splitlines()}
    for number, line in enumerate(content.splitlines(), 1):
        words = _comment_words(line)
        if words and line.strip() not in known and any(pattern.search(words) for pattern in _LEFT_OUT):
            failure = PlannerUnavailable(f'{rel} line {number} leaves code out (“{line.strip()[:100]}”): write the '
                                         'code in full; never abbreviate.')
            failure.feedback = {'path': rel, 'elided_line': number}
            raise failure


def admit_answer_files(ws, context: dict[str, Any], raw_files, *, allowed_paths: set[str] | None = None,
                       revision_files: dict[str, dict] | None = None, candidate_view: dict | None = None,
                       materialized=()):
    """Turn one immutable model answer into host-bound candidate bytes.

    Exact edits are replayed against the frozen current source.  During an
    explicit revision, an edit may instead match the prior unapplied candidate
    exactly; the host then materializes full candidate bytes bound to the
    unchanged real source.  Neither path gets fuzzy matching or extra paths.

    A file the model was shown only in parts (context['excerpts']) may be changed only by exact edits whose old text
    occurs once in the whole file and lies inside one shown part, never by a whole-file replacement; `materialized`
    names the paths whose content the host itself built from a focused revision (journey J11-B15).
    """
    from runesmith.app.source_parts import format_ranges
    context = _with_shared_documents(ws, context)
    parts = context.get('excerpts') or {}
    files = copy.deepcopy([f for f in (raw_files or []) if isinstance(f, dict)])
    touched = [r for r in dict.fromkeys(ws._safe_rel(str(f.get("path") or "")) for f in files) if r and (ws.root / r).exists()]
    admitted = []
    for f in files:
        rel = ws._safe_rel(str(f.get("path") or ""))
        if not rel:
            raise PlannerUnavailable("the draft included an invalid path")
        if allowed_paths is not None and rel not in allowed_paths:
            raise PlannerUnavailable(f"the corrected answer broadened its path set: {rel}")
        part = parts.get(rel)
        base_used = ''
        if 'edits' in f:
            candidate=(revision_files or {}).get(rel,{}).get('content')
            if rel not in context['files'] and part is None and not isinstance(candidate,str) and rel in (context.get('omitted') or []):
                raise _not_shown(rel, context, ws, touched)
            if 'content' in f or (rel not in context['files'] and part is None and not isinstance(candidate,str)):
                raise PlannerUnavailable('Exact edits require a fully shown current or candidate file and no content field.')
            edit_index = None
            try:
                if not isinstance(f['edits'],list) or not 1<=len(f['edits'])<=MAX_EDITS:
                    raise ValueError(f'Provide 1-{MAX_EDITS} exact edits.')
                bases=[('current',context['files'][rel],None)] if rel in context['files'] else []
                if part is not None and not bases:
                    whole=_full_text(ws,context,rel)
                    if whole is None:
                        raise PlannerUnavailable(f'{rel} has changed since it was shown in parts, so an edit to it cannot be '
                                                 'checked against what the model saw.')
                    bases.append(('current',whole,part['ranges']))
                if revision_files and rel in revision_files:
                    if isinstance(candidate,str) and candidate!=context['files'].get(rel):
                        # Revisions preserve the selected candidate's other changes.
                        # Fall back to live source only if exact candidate edits fail.
                        # A candidate shown in parts is edited only where it was shown (J11-B15).
                        shown_as=_candidate_ranges(candidate_view,rel,candidate,part is not None)
                        if shown_as is not False:
                            bases.insert(0, ('candidate',candidate,shown_as))
                def replay(base_text,base_ranges):
                    nonlocal edit_index
                    value=base_text;repeated,done=_repeated(f['edits']),set()
                    shown=None if base_ranges is None else [list(r) for r in base_ranges]
                    for edit_index,edit in enumerate(f['edits']):
                        key=_edit_key(edit)
                        if key in repeated:
                            if key not in done:
                                if shown is None:value=_replace_every(value,key,repeated[key])
                                else:value,shown=_replace_every_inside(value,key,repeated[key],shown)
                                done.add(key)
                            continue
                        before=value
                        value=_apply_one_edit(value,edit,rel)
                        if shown is not None:shown=_inside_shown(before,value,edit,shown)
                    return value
                errors=[];proposed=None
                for base_name,base_text,base_ranges in bases:
                    try:
                        proposed=replay(base_text,base_ranges);f['revision_base']=base_name;base_used=base_text;break
                    except (ValueError,TypeError,KeyError) as candidate_error:
                        if isinstance(candidate_error,_OutsideShown):candidate_error.shown=base_ranges
                        errors.append(candidate_error)
                if proposed is None:
                    raise errors[-1]
                if (f.get('revision_base')=='current' and bases[0][0]=='candidate' and bases[0][2] is not None
                        and any(isinstance(error,_OutsideShown) for error in errors)):
                    # The edit lies in the lines of the current file the model was shown, but not in the candidate's shown
                    # lines: the text is the model's own copy, so it is applied to the candidate, and the candidate's other
                    # changes are kept, as for any revision. Only when it does not apply there is the current file edited
                    # (review of the merged batch: the candidate's work was dropped without a word).
                    try:
                        again=replay(bases[0][1],None)
                    except (ValueError,TypeError,KeyError):
                        pass
                    else:
                        proposed=again;f['revision_base']='candidate';base_used=bases[0][1]
                f['content']=proposed
            except (ValueError, TypeError, KeyError) as error:
                feedback={'path':rel,'scope':'Unapplied candidate; source excerpt is from the actual current file.',
                          'admitted_paths':list(admitted)}
                if edit_index is not None:
                    edit=f['edits'][edit_index]
                    old=edit.get('old_text','') if isinstance(edit,dict) else ''
                    old=old if isinstance(old,str) else ''
                    candidate_text=(revision_files or {}).get(rel,{}).get('content','')
                    # A file shown in parts has no excerpt of lines the model was not shown (J11-B15): its next call is
                    # shown them instead, through the old_text this feedback keeps.
                    searchable='' if part is not None else context['files'].get(rel,'')+'\n'+candidate_text
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
                words=f'Exact edit refused for {rel}: {error}'
                if isinstance(error,_OutsideShown):
                    # Plain words, naming the lines that were shown; the model's error, with what a correction can use.
                    words=(f'Exact edit refused for {rel}: its old_text is on lines {error.first}–{error.last} of '
                           f'{error.count}, which the model was not shown. It was shown lines {format_ranges(error.shown)} '
                           f'of {rel}: copy old_text from one of those parts (never from the outline), or leave the '
                           'change out.')
                    feedback.update(shown_ranges=[list(r) for r in error.shown],lines=[error.first,error.last])
                failure=PlannerUnavailable(words)
                failure.feedback=feedback
                raise failure from error
        if rel in context["files"]:
            f["base"] = context["files"][rel]
            f["expected_sha256"] = context['file_hashes'][rel]
        elif part is not None:
            if 'edits' not in f and rel not in materialized:
                failure = PlannerUnavailable(
                    f"refused a whole-file replacement of {rel}: the model was shown it only in parts (lines "
                    f"{format_ranges(part['ranges'])} of {part['lines']}). Change it with exact edits whose old_text is "
                    "copied from one shown part; never write the whole file.")
                failure.feedback = {'path': rel, 'shown_ranges': [list(r) for r in part['ranges']], 'whole_file': True}
                raise failure
            whole = _full_text(ws, context, rel)
            if whole is None:
                raise PlannerUnavailable(f'{rel} has changed since it was shown in parts, so a change to it cannot be '
                                         'checked against what the model saw.')
            f["base"] = whole
            f["expected_sha256"] = part['sha256']
        elif (ws.root / rel).exists():
            if rel in (context.get('omitted') or []):
                raise _not_shown(rel, context, ws, touched)
            raise PlannerUnavailable(f"refused an unseen replacement: {rel}; narrow the milestone or source packet")
        else:
            f.pop("base", None)
            f.pop("expected_sha256", None)
            f["expected_absent"] = True
        _refuse_left_out(rel, f.get('content'), base_used if 'edits' in f else f.get('base') or '')
        admitted.append(rel)
    return files


def admit_revision_answer(ws,context,raw_files,revision=None,*,allowed_paths=None,candidate_view=None,materialized=()):
    """Admit an answer and carry forward untouched bytes from its candidate."""
    context=_with_shared_documents(ws,context)
    revision_files={f['path']:f for f in revision.get('files',[])} if revision else {}
    files=admit_answer_files(ws,context,raw_files,allowed_paths=allowed_paths,
                            revision_files=revision_files,candidate_view=candidate_view,materialized=materialized)
    returned={f['path'] for f in files}
    for rel,prior in revision_files.items():
        if rel in returned:continue
        if allowed_paths is not None and rel not in allowed_paths:
            raise PlannerUnavailable(f'the revision broadened its retained path set: {rel}')
        if rel in context['files']:
            retained=copy.deepcopy(prior);retained['base']=context['files'][rel]
            retained['expected_sha256']=context['file_hashes'][rel]
            retained.pop('expected_absent',None)
        elif rel in (context.get('excerpts') or {}):
            whole=_full_text(ws,context,rel)
            if whole is None:
                raise PlannerUnavailable(f'{rel} has changed since it was shown in parts, so the retained candidate cannot be '
                                         'bound to it.')
            retained=copy.deepcopy(prior);retained['base']=whole
            retained['expected_sha256']=context['excerpts'][rel]['sha256']
            retained.pop('expected_absent',None)
        elif not (ws.root/rel).exists():
            retained=copy.deepcopy(prior);retained.pop('base',None);retained.pop('expected_sha256',None)
            retained['expected_absent']=True
        else:
            if rel in (context.get('omitted') or []):       # as an edit to it is: no try, and the remedy named (J11-B15)
                raise _not_shown(rel, context, ws, [p for p in dict.fromkeys([*returned, *revision_files]) if (ws.root/p).exists()])
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
    context = source_context(ws, snapshot=snapshot, milestone=milestone)
    if focus_missing(context):
        # No model is asked: this uses up no try (journey J11-B15 review: a prioritized file went away and every build
        # used up a try with no call made).
        failure = PlannerUnavailable('Selected author source cannot fit or is unavailable: ' + focus_problem(context))
        failure.context_gap = {'reason': 'focus_errors', 'paths': focus_missing(context)}
        raise failure
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
    revision=revision or next(iter(revisable_candidates(ws,ws.drafts(),milestone,snapshot['digest'])),None)
    packet=prepare_packet(ws,request_key,milestone=milestone,context=context,contract=contract,
        public_digest=public_digest,exposure=exposure_path.relative_to(ws.home).as_posix(),
        revision=revision,explicit_revision=explicit_revision,attempt_id=attempt_id,revision_view=revision_view,
        revision_operation=revision_operation,
        candidate_view=candidate_shown(ws,revision,context,milestone)[3] if revision and revision_view is None else None)
    if not explicit_revision:
        _rotate_repeating_author(ws, router, contract)
    answered: dict[str, Any] = {}
    data, by = _call(ws, router, prompt, DRAFT_SYSTEM, DRAFT_SCHEMA, request_key, 4000 if explicit_revision else 12000,
                     receipt_out=answered)
    _write_json(exposure_path, dict(exposure, state='answer_received', author=by))
    try:
        return admit_packet(ws,packet,data,by,receipt=answered or None,admission_guard=admission_guard)
    except PlannerUnavailable as error:
        _write_json(ws.home/'author-admissions'/(request_key+'.json'),
                    {'state':'rejected','error':str(error)[:500],'feedback':getattr(error,'feedback',None)})
        raise
