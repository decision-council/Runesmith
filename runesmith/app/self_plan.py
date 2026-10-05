"""Runesmith's plan for improving itself: a map, a scored plan, the owner's share, and a gate for every change.

Runesmith keeps a map of itself (SELF_MAP.json: what it is made of, what it does well, where its own work struggles) and
a plan (SELF_PLAN.json): the improvements it sees it could make, each with a score and a reason in plain words. When it
is Runesmith's turn to improve itself, it takes the first item of the plan, unless the project it is working on is
struggling right now: then it takes the best-scored improvement that is linked to that struggle, because that is what
might help it finish the work in front of it.

**Nothing changes without its gate.** The one gate that exists is the repair organ's: a Kaizen campaign replays
held-out work, freezes a candidate, and an online trial on the owner's own work decides whether it is switched on.
Everything else is only *planned*: the item is recorded as "planned: needs a gate", visible to the owner (and ready to
be shared), and Runesmith's code is left exactly as it is.

The scoring rule (declared; the same records always give the same plan, and nothing here reads the clock)
-------------------------------------------------------------------------------------------------------------
``score = benefit + recency + gate``, whole numbers, ties broken by the item's id. The plan lists the items that answer a
milestone that is struggling now first (the owner's priority), then the others; each group in score order.

* **benefit** (0 to 60) from the counts. An option that answers struggles: 10 points for each doubling of the number of
  failures it would have prevented (a failure counts twice while its milestone is still struggling), at most 60.
  A repair-organ target: its share of the lost repairs in percent, at most 60 (a cycle-time target: half its share of
  the time, at most 30). Affordances an organ leaves unused: 3 each, at most 12.
* **recency** (0 to 20): how long before the newest record the item's evidence was last seen: within 6 hours 20, within
  a day 14, within 3 days 8, within a week 4, older 0 (none when the evidence has no time).
* **gate** (0 or 20): 20 when a trial gate exists for the kind of change (the repair organ's), else 0.

**Whose turn.** The owner's setting ``self_improvement_share`` (10 to 90 percent, in steps of ten, default 20) says how
many of every 10 work turns are self-improvement turns, spread evenly (at 20 percent the 5th and the 10th). A work turn
is one repair opportunity served by the run loop, or one scheduled step of the Studio's build work. A counter in the home
(SELF_TURNS.json) keeps the position exact across restarts. This replaces the automatic attention share as the baseline;
the attention module is kept for its health signals (it still watches outcomes, and a repair failure that keeps
recurring is a struggle here too).

**At a self-improvement turn**, in order: the candidates are the plan's items in score order (only those linked to a
current struggle, when a milestone struggles now); the first one that can be acted on is taken. An item with a gate that
can run now starts its campaign. An item without a gate is recorded as planned (once) and the turn goes back to the
project's work at once. An item whose gate cannot run now (no Improver, a trial open, too little experience) is passed
over. When nothing is left, the turn is the project's: Runesmith never idles for a self-improvement turn.
"""
from __future__ import annotations

import calendar
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from runesmith.app import runesmith_md
from runesmith.app.workspace import _now, _read_json, _write_json

SCHEMA = "runesmith.self_plan.v1"
PLAN_FILE, TURNS_FILE = "SELF_PLAN.json", "SELF_TURNS.json"
DEFAULT_SHARE = 20
SHARES = tuple(range(10, 100, 10))
BLOCK = 10                                   # the owner's share is counted in blocks of ten work turns
KEPT_ITEMS, SHOWN_ITEMS, KEPT_HISTORY = 40, 10, 20

# -- the scoring constants (see the module docstring) ---------------------------------------------------------------
BENEFIT_CAP, BENEFIT_PER_DOUBLING = 60, 10
YIELD_CAP, CYCLE_CAP, CYCLE_FACTOR, AFFORDANCE_EACH, AFFORDANCE_CAP = 60, 30, 50, 3, 12
RECENCY_STEPS = ((6, 20), (24, 14), (72, 8), (168, 4))        # (hours before the newest record, points)
GATE_POINTS = 20
CURRENT_WINDOW_H = 48                         # a struggle is current while its last failure is this near the newest record
LARGE_FILE_CHARS = 20_000                     # a file at least this long is "large" for a draft (the context-only cap)
REPEAT_MIN = 2                                # failures of one kind on one milestone before it counts as a struggle
STUCK_SIGNATURES = frozenset({"tries_used_up", "file_not_shown", "split_refused"})     # the stuck policy's own records

RULE = {
    "score": "benefit + recency + gate; whole numbers; ties by id",
    "benefit": f"struggle option: {BENEFIT_PER_DOUBLING} points per doubling of its failure count (twice while its milestone "
               f"struggles), at most {BENEFIT_CAP}; repair-organ target: its percent of lost repairs, at most {YIELD_CAP}; "
               f"unused affordances: {AFFORDANCE_EACH} each, at most {AFFORDANCE_CAP}",
    "recency": "20 within 6 hours of the newest record, 14 within a day, 8 within 3 days, 4 within a week, else 0",
    "gate": f"{GATE_POINTS} when a trial gate exists for this kind of change (the repair organ's), else 0",
    "turns": "the owner's share of every 10 work turns, spread evenly; the counter is kept in the home",
    "priority": "when a milestone struggles now, only options linked to a struggle are considered",
    "order": "the plan lists the items that answer a struggling milestone first, then every other item; each group by score, "
             "ties by id, so its first item is what a self-improvement turn takes",
}

# -- what a struggle is called, in plain words -----------------------------------------------------------------------
WORDS = {
    "draft_checks_failed_large_file": "drafts that rewrite a large file keep failing their checks",
    "file_too_large_to_show": "a file it must change is too large to show a model",
    "module_system_errors": "drafts keep failing on JavaScript module errors",
    "draft_checks_failed": "drafts keep failing their checks",
    "no_author_allowance": "no author try is left to fund the next attempt",
    "split_refused": "smaller steps could not be made or adopted",
    "tries_used_up": "its tries are used up and nothing more is left to try by itself",
    "file_not_shown": "the one more try could not change a file no model is shown",
    "exact_edit_refused": "the author's exact edits do not match the file",
    "answer_truncated": "the author's answers are cut off",
    "checks_time_out": "its checks run out of time",
    "late_answer": "the author's answer does not arrive",
    "acceptance_checks_refused": "the proposed acceptance checks are refused",
}

STAGE_WORDS = {"model": "model calls", "signal": "running the tests", "other": "the organ's own work between them"}

# The job outcomes that tell of a struggle: the first pattern that matches names it (declared, ordered).
JOB_PATTERNS = (
    ("file_too_large_to_show", re.compile(r"too large to show a model", re.I)),
    ("no_author_allowance", re.compile(r"No unambiguous ordinary author allowance|No new budget granted|"
                                       r"Ordinary author allowance exhausted|author allowance receipt", re.I)),
    ("exact_edit_refused", re.compile(r"Exact edit refused|did not match exactly once", re.I)),
    ("answer_truncated", re.compile(r"\btruncated\b|ran out of room before finishing", re.I)),
    ("checks_time_out", re.compile(r"checks? (?:timed out|did not finish)|time limit", re.I)),
    ("late_answer", re.compile(r"answer has not arrived|late answer|Remote outcome unresolved", re.I)),
    ("split_refused", re.compile(r"candidate failures are not current-source failures|prerequisite names an absent file", re.I)),
    ("draft_checks_failed", re.compile(r"checks failed", re.I)),
)
MODULE_ERRORS = re.compile(r"Cannot use import statement outside a module|ERR_REQUIRE_ESM|require is not defined|"
                           r"ERR_MODULE_NOT_FOUND|does not provide an export named|Unexpected token 'export'|"
                           r"exports is not defined|ERR_UNKNOWN_FILE_EXTENSION|ERR_UNSUPPORTED_DIR_IMPORT", re.I)

# The declared catalogue: which improvement answers which struggle. An entry with no struggle behind it is not planned.
CATALOGUE = (
    {"id": "targeted_edits_large_files", "title": "Targeted edits for large files",
     "signatures": ("draft_checks_failed_large_file", "file_too_large_to_show"),
     "what": "Ask the author for exact edits to a large file instead of the whole file rewritten, and show it the parts "
             "it must change."},
    {"id": "es_module_guidance", "title": "Author guidance for ES modules", "signatures": ("module_system_errors",),
     "what": "Tell the author, before it writes, how the project's JavaScript modules import and export, so a draft "
             "does not mix module styles."},
    {"id": "failed_check_feedback", "title": "Feed failed checks back in the author's own terms",
     "signatures": ("draft_checks_failed",),
     "what": "Show the author which checks failed and what each one expected, so the next try changes the right thing."},
    {"id": "fresh_try_after_one_more_try", "title": "A fresh ordinary try after the one more try fails",
     "signatures": ("no_author_allowance",),
     "what": "Fund a new ordinary attempt when a one-more-try draft fails, instead of stopping at an allowance question."},
    {"id": "valid_smaller_steps", "title": "Smaller steps that only name files that exist or that they create",
     "signatures": ("split_refused",),
     "what": "Check a proposed breakdown against the files before asking for it, so it is not refused afterwards."},
    {"id": "plan_smaller_steps", "title": "Break a large milestone down before its first try",
     "signatures": ("tries_used_up",),
     "what": "Propose smaller steps for a milestone that looks too large before its tries are spent on it."},
    {"id": "show_needed_files", "title": "Show the author the files a step must change",
     "signatures": ("file_not_shown",),
     "what": "Find the files a step must change from its checks and show them, so the one more try can change them."},
    {"id": "exact_edit_anchoring", "title": "Exact edits that match the current file",
     "signatures": ("exact_edit_refused",),
     "what": "Anchor an exact edit on text taken from the file as it is now, and refuse an anchor that is not unique."},
    {"id": "bounded_author_answers", "title": "Answers that fit the model's output limit",
     "signatures": ("answer_truncated",),
     "what": "Split a large answer into parts, or ask for edits, so no answer is cut off at the model's limit."},
    {"id": "checks_inside_limits", "title": "Checks that finish inside their time limit",
     "signatures": ("checks_time_out",),
     "what": "Run a draft's checks in smaller groups, so none of them runs out of time."},
    {"id": "answer_routes_in_time", "title": "Choose routes whose answers arrive",
     "signatures": ("late_answer",),
     "what": "Remember which model routes answered lately and ask those first."},
    {"id": "acceptance_check_quality", "title": "Acceptance checks that pass validation the first time",
     "signatures": ("acceptance_checks_refused",),
     "what": "Give the Checker the validator's rules in its request, so its proposals are not refused afterwards."},
)


def _epoch(text: Any) -> int | None:
    try:
        return calendar.timegm(time.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def _title(text: Any, limit: int = 70) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _when(utc: Any) -> str:
    return str(utc or "")[:16].replace("T", " ") + "Z" if utc else "an unknown time"


# ----------------------------------------------------------------------------------------------------- struggles --

def _draft_flags(ws, draft_id: str) -> dict[str, bool]:
    """Whether a failed draft rewrote a large file, and whether its checks failed on a module error. Only drafts that a
    job names are read, each once (a draft is a few hundred kilobytes; a home has hundreds)."""
    cache = ws.__dict__.setdefault("_self_plan_drafts", {})
    path = ws.home / "drafts" / str(draft_id) / "DRAFT.json"
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return {"large": False, "module": False}
    hit = cache.get(draft_id)
    if hit and hit[0] == stamp:
        return hit[1]
    draft = _read_json(path, {})
    draft = draft if isinstance(draft, dict) else {}
    large = any(max(len(str(f.get("content") or "")), len(str(f.get("base") or ""))) >= LARGE_FILE_CHARS
                for f in draft.get("files") or [] if isinstance(f, dict))
    verification = draft.get("verification") if isinstance(draft.get("verification"), dict) else {}
    texts = []
    for part in ("project_checks", "acceptance"):
        block = verification.get(part)
        if isinstance(block, dict):
            texts.append(str(block.get("output") or ""))
            texts.extend(str(d) for d in (block.get("failure_details") or [])[:20])
    flags = {"large": large, "module": bool(MODULE_ERRORS.search("\n".join(texts)))}
    cache[draft_id] = (stamp, flags)
    return flags


def _job_events(ws, jobs: list[Any]) -> list[dict[str, Any]]:
    events = []
    for row in jobs:
        if not isinstance(row, dict) or row.get("result") not in ("failed", "done"):
            continue
        outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
        params = row.get("params") if isinstance(row.get("params"), dict) else {}
        kind = row.get("kind")
        text = str(outcome.get("error") or outcome.get("summary") or "")
        signature = None
        if kind == "split" and row.get("result") == "failed":
            signature = "split_refused"
        elif kind == "propose_acceptance" and row.get("result") == "failed":
            signature = "acceptance_checks_refused"
        else:
            signature = next((name for name, pattern in JOB_PATTERNS if pattern.search(text)), None)
        if signature == "draft_checks_failed" and outcome.get("draft"):
            flags = _draft_flags(ws, str(outcome["draft"]))
            signature = ("module_system_errors" if flags["module"] else
                         "draft_checks_failed_large_file" if flags["large"] else signature)
        if signature is None:
            continue
        events.append({"signature": signature, "milestone": outcome.get("milestone") or params.get("milestone_id")
                       or params.get("milestone"), "n": int(row.get("repeats") or 1),
                       "since": row.get("first_finished") or row.get("finished"), "last": row.get("finished"),
                       "source": "jobs"})
    return events


def _record_events(ws) -> list[dict[str, Any]]:
    """The stuck policy's own records: a milestone that nothing more is tried for by itself, and a break-down refused."""
    events = []
    notices = _read_json(ws.home / "STUCK_NOTICES.json", {})
    for milestone, note in (notices.items() if isinstance(notices, dict) else []):
        if isinstance(note, dict):
            events.append({"signature": "file_not_shown" if note.get("kind") == "gap" else "tries_used_up",
                           "milestone": milestone, "n": 1, "since": note.get("utc"), "last": note.get("utc"),
                           "source": "stuck notice"})
    refused = _read_json(ws.home / "STUCK_REFUSED.json", {})
    for milestone, row in (refused.items() if isinstance(refused, dict) else []):
        if isinstance(row, dict):
            events.append({"signature": "split_refused", "milestone": milestone, "n": 1, "since": row.get("utc"),
                           "last": row.get("utc"), "source": "refused break-down"})
    return events


def collect_struggles(ws) -> list[dict[str, Any]]:
    """Every milestone that is stuck or fails again and again, with what keeps failing, how often and since when.

    From cheap records only: the worker's job history, the stuck policy's notes, the plan, and the attention module's
    verdict on the repairs (and the few drafts a job names). Deterministic: the same records give the same list, and
    "current" is judged against the newest record, never the clock.
    """
    plan = ws.plan() or {}
    milestones = {m.get("id"): m for m in plan.get("milestones", []) if isinstance(m, dict)}
    jobs = _read_json(ws.home / "STUDIO_JOBS.json", [])
    events = _job_events(ws, jobs if isinstance(jobs, list) else []) + _record_events(ws)
    stamps = [t for t in (_epoch(e.get("last")) for e in events) if t is not None]
    newest = max(stamps) if stamps else None
    groups: dict[tuple, dict[str, Any]] = {}
    for event in events:
        key = (event["milestone"], event["signature"])
        group = groups.setdefault(key, {"counts": {}, "since": None, "last": None})
        group["counts"][event["source"]] = group["counts"].get(event["source"], 0) + event["n"]     # one source counted once
        for field, pick in (("since", min), ("last", max)):
            value = event.get(field)
            if value:
                group[field] = value if group[field] is None else pick(value, group[field])
    out = []
    for (milestone_id, signature), group in groups.items():
        count = max(group["counts"].values())
        if count < REPEAT_MIN and signature not in STUCK_SIGNATURES:
            continue
        milestone = milestones.get(milestone_id) if milestone_id else None
        last_epoch = _epoch(group["last"])
        open_now = bool(milestone) and milestone.get("status") in ("open", "doing")
        current = bool(open_now and last_epoch is not None and newest is not None
                       and newest - last_epoch <= CURRENT_WINDOW_H * 3600)
        out.append({"id": f"{milestone_id or 'project'}|{signature}", "scope": "milestone" if milestone_id else "project",
                    "milestone": milestone_id, "milestone_title": _title(milestone.get("title")) if milestone else None,
                    "signature": signature, "words": WORDS.get(signature, signature.replace("_", " ")),
                    "count": count, "since": group["since"], "last": group["last"], "current": current,
                    "sources": sorted(group["counts"])})
    attention = _attention_struggle(ws)
    if attention:
        out.append(attention)
    return sorted(out, key=lambda s: (not s["current"], -s["count"], s["id"]))


def _attention_struggle(ws) -> dict[str, Any] | None:
    """The repairs' own struggle: a failure that keeps recurring in the repair organ's outcomes (attention's verdict)."""
    from runesmith.kaizen.attention import BLOCKED, SUSPECTED, Attention
    attention = Attention.load(ws.home / "ATTENTION.json")
    if not attention or attention.mode not in (SUSPECTED, BLOCKED) or not attention.blocking_signature:
        return None
    signature = str(attention.blocking_signature)
    count = sum(1 for s in attention.recent if s == signature)
    return {"id": f"repairs|{signature}", "scope": "repairs", "milestone": None, "milestone_title": None,
            "signature": signature, "words": "the repair organ keeps failing the same way (" + signature.replace("_", " ").replace("|", ", ") + ")",
            "count": count or 1, "since": None, "last": None, "current": True, "sources": ["attention"]}


# ---------------------------------------------------------------------------------------------------------- plan --

def _recency(last: Any, newest: int | None) -> int:
    epoch = _epoch(last)
    if epoch is None or newest is None:
        return 0
    hours = (newest - epoch) / 3600
    return next((points for limit, points in RECENCY_STEPS if hours <= limit), 0)


def _benefit(weighted_failures: int) -> int:
    return min(BENEFIT_CAP, BENEFIT_PER_DOUBLING * int(weighted_failures).bit_length())


def _family_words(family: str) -> str:
    return family.replace("|", ", ").replace("_", " ")


def build_plan(self_map: dict[str, Any]) -> dict[str, Any]:
    """The scored plan from the self map alone (its struggles, its ranked Kaizen targets and its unused affordances) and
    the declared catalogue. Pure and deterministic: no clock, no file."""
    struggles = [s for s in self_map.get("struggles") or [] if isinstance(s, dict)]
    stamps = [t for t in (_epoch(s.get("last")) for s in struggles) if t is not None]
    newest = max(stamps) if stamps else None
    items: list[dict[str, Any]] = []
    for entry in CATALOGUE:
        linked = [s for s in struggles if s["signature"] in entry["signatures"] and s.get("scope") != "repairs"]
        if not linked:
            continue
        weighted = sum(s["count"] * (2 if s["current"] else 1) for s in linked)
        lasts = [s["last"] for s in linked if s.get("last")]
        recency = _recency(max(lasts), newest) if lasts else 0
        worst = max(linked, key=lambda s: (s["current"], s["count"], s["id"]))
        where = f"on “{worst['milestone_title']}”" if worst.get("milestone_title") else "in the project"
        reason = (f"{worst['words'][:1].upper() + worst['words'][1:]} {where}: {worst['count']} time(s)"
                  + (f", since {_when(worst['since'])}" if worst.get("since") else "")
                  + (", and it is still struggling" if worst["current"] else "")
                  + (f" (and {len(linked) - 1} more of the same kind)" if len(linked) > 1 else "")
                  + ". No trial gate exists for this kind of change yet, so it stays a plan.")
        items.append({"id": entry["id"], "title": entry["title"], "kind": "struggle", "what": entry["what"],
                      "score": _score(_benefit(weighted), recency, 0), "reason": reason, "gate": None,
                      "struggles": sorted(s["id"] for s in linked)})
    targets = [t for t in self_map.get("open_targets") or [] if isinstance(t, dict)]
    repair_struggles = [s for s in struggles if s.get("scope") == "repairs"]
    for target in targets:
        share = float(target.get("share") or 0)
        if target.get("type") == "yield":
            family = str(target.get("family"))
            benefit = min(YIELD_CAP, int(share * 100 + 0.5))
            title = f"Repair organ: fewer “{_family_words(family)}” failures"
            reason = (f"{round(share * 100)}% of the repairs it could not make ended as “{_family_words(family)}” "
                      f"({target.get('count')} of them). A Kaizen campaign can try a change to the repair organ; "
                      "an online trial on your own work decides whether it is used.")
            linked = [s for s in repair_struggles if s["signature"] == family
                      or (s["signature"] == "yield_drift" and target.get("rank") == 1)]
        else:
            benefit = min(CYCLE_CAP, int(share * CYCLE_FACTOR + 0.5))
            stage = STAGE_WORDS.get(str(target.get("stage")), str(target.get("stage")).replace("_", " "))
            title = f"Repair organ: less time in {stage}"
            reason = (f"{round(share * 100)}% of the repair time goes to {stage}. "
                      "A Kaizen campaign can try a change to the repair organ; an online trial decides.")
            linked = []
        if linked:
            reason += " The repair organ's own outcomes show this failure recurring now."
        items.append({"id": f"kaizen:{target.get('type')}:{target.get('family') or target.get('stage')}", "title": title,
                      "kind": "kaizen_target", "what": "A Kaizen campaign: the Improver proposes a change to the repair organ, "
                      "it is replayed on held-out work, and an online trial on your work decides.",
                      "score": _score(benefit, 0, GATE_POINTS), "reason": reason,
                      "gate": "online trial of the repair organ", "rank": target.get("rank"),
                      "struggles": sorted(s["id"] for s in linked)})
    for organ, option in sorted((self_map.get("improvement_options") or {}).items()):
        unused = [str(u.get("affordance") if isinstance(u, dict) else u) for u in (option or {}).get("unused_affordances") or []]
        if unused and not organ.startswith("_"):
            items.append({"id": f"affordance:{organ}", "title": f"Use what the {organ} organ leaves unused",
                          "kind": "self_map", "what": f"The {organ} organ never asks for: {', '.join(unused)}.",
                          "score": _score(min(AFFORDANCE_CAP, AFFORDANCE_EACH * len(unused)), 0, 0),
                          "reason": f"The self map lists {len(unused)} affordance(s) the {organ} organ never uses. "
                                    "No trial gate takes this kind of change yet, so it stays a plan.",
                          "gate": None, "struggles": []})
    current = {s["id"] for s in struggles if s.get("current")}
    for item in items:
        item["priority"] = bool(current & set(item["struggles"]))          # it answers a milestone that struggles now
    items.sort(key=lambda i: (not i["priority"], -i["score"]["total"], i["id"]))
    for rank, item in enumerate(items, start=1):
        item["position"] = rank
    body = {"schema": SCHEMA, "rule": RULE, "map_digest": self_map.get("map_digest"), "items": items[:KEPT_ITEMS]}
    from runesmith.canon import digest
    body["plan_digest"] = digest({"items": body["items"], "rule": RULE})
    return body


def _score(benefit: int, recency: int, gate: int) -> dict[str, int]:
    return {"total": benefit + recency + gate, "benefit": benefit, "recency": recency, "gate": gate}


# ---------------------------------------------------------------------------------------------------- the turn --

def share_of(settings: dict[str, Any]) -> int:
    value = settings.get("self_improvement_share", DEFAULT_SHARE)
    return value if value in SHARES else DEFAULT_SHARE


def sentence(share: int) -> str:
    k = share // 10
    return f"{k} of every 10 work turns {'goes' if k == 1 else 'go'} to improving Runesmith itself"


def is_self_turn(turn: int, share: int) -> bool:
    """Whether the ``turn``-th work turn (counting from 1) is a self-improvement turn: in each block of ten, ``share/10``
    of them, spread evenly (at 20 percent the 5th and the 10th)."""
    k, p = share // 10, (turn - 1) % BLOCK + 1
    return (p * k) // BLOCK > ((p - 1) * k) // BLOCK


def next_self_turn_in(turns_done: int, share: int) -> int:
    """How many work turns from now the next self-improvement turn is (1 means the very next one)."""
    return next(step for step in range(1, BLOCK + 1) if is_self_turn(turns_done + step, share))


def _turns(ws) -> int:
    value = _read_json(ws.home / TURNS_FILE, {})
    turns = value.get("turns") if isinstance(value, dict) else 0
    return turns if type(turns) is int and turns >= 0 else 0


def choose(plan: dict[str, Any], struggles: list[dict[str, Any]], activity: dict[str, Any], *,
           campaign_ready: bool) -> dict[str, Any]:
    """What a self-improvement turn does now. Pure: ``action`` is ``campaign`` (start the campaign for ``item``), ``plan``
    (record ``item`` as planned: it has no gate) or ``none`` (nothing can run: the turn is the project's)."""
    items = plan.get("items") or []
    current = [s for s in struggles if s.get("current")]
    linked_ids = {s["id"] for s in current}
    pool = [i for i in items if linked_ids & set(i.get("struggles") or [])] if current else items
    mode = "struggle" if current and pool else "top"
    if current and not pool:
        pool = items                                  # nothing answers it in the catalogue: the plan's own order
    passed = []
    for item in pool:
        link = next((s for s in current if s["id"] in set(item.get("struggles") or [])), None) if mode == "struggle" else None
        chosen = {"item": item["id"], "title": item["title"], "mode": mode, "struggle": link["id"] if link else None,
                  "passed": passed}
        if item["gate"]:
            if campaign_ready and item.get("rank") == 1:      # a campaign takes the top-ranked target itself
                return dict(chosen, action="campaign", why=_why(item, mode, link, "campaign"))
            passed.append(item["id"])
            continue
        if str((activity.get(item["id"]) or {}).get("status", "")).startswith("planned"):
            continue
        return dict(chosen, action="plan", why=_why(item, mode, link, "plan"))
    return {"action": "none", "item": None, "title": None, "mode": mode, "struggle": None, "passed": passed,
            "why": ("Nothing can run now: every item is already planned or waits for its gate. "
                    "The turn goes back to the project's work.")}


def _why(item: dict[str, Any], mode: str, link: dict[str, Any] | None, action: str) -> str:
    score = f"score {item['score']['total']}"
    if mode == "struggle" and link:
        where = f"“{link['milestone_title']}”" if link.get("milestone_title") else "the project"
        lead = (f"{where} is struggling now ({link['words']}; {link['count']} time(s)"
                + (f", since {_when(link['since'])}" if link.get("since") else "")
                + f"), so the best-scored improvement linked to it comes first: {item['title']} ({score}).")
    else:
        lead = f"Nothing is struggling now, so the plan's first item comes first: {item['title']} ({score})."
    end = (" It has a gate: a campaign starts." if action == "campaign" else
           " It has no gate yet, so it is recorded as planned: needs a gate, and nothing about Runesmith changes.")
    return lead + end


def _blockers(ws, settings: dict[str, Any], ready: dict[str, Any]) -> list[str]:
    """Why a campaign cannot start now, in plain words (empty: it can). Cheap: counts files, reads two small ones."""
    from runesmith.kaizen.trial import Trial
    from runesmith.loop import load_campaign_state
    out = []
    if not settings.get("kaizen"):
        out.append("self-improvement is off in Settings")
    if settings.get("autonomy") == "observe":
        out.append("Runesmith is in Observe mode")
    if not ready.get("kaizen"):
        out.append("no Improver model is set up")
    trial = Trial.load(ws.home / "TRIAL.json")
    if trial is not None and trial.decision is None:
        out.append("a trial is open")
    stored = len(list((ws.home / "experience").glob("*/TASK.json")))
    need = int(settings.get("min_experience") or 0)
    if stored < need:
        out.append(f"{need - stored} more stored repair attempt(s) are needed")
    else:
        last = load_campaign_state(ws.home)
        gap = int(settings.get("kaizen_every") or 1) - (stored - last) if last is not None else 0
        if gap > 0:
            out.append(f"{gap} more new attempt(s) are needed since the last campaign")
    return out


def refresh(ws) -> dict[str, Any] | None:
    """Rebuild the map (with the struggles), the scored plan and the preview of the next self-improvement turn, and keep
    them in SELF_MAP.json and SELF_PLAN.json (written only when they changed). No model is asked. Never raises."""
    try:
        return _refresh(ws)
    except Exception:
        return None


def _refresh(ws) -> dict[str, Any]:
    settings = ws.settings()
    ready = ws.ready()
    self_map = ws.self_map(refresh=True)
    plan = build_plan(self_map)
    old = _read_json(ws.home / PLAN_FILE, {})
    old = old if isinstance(old, dict) else {}
    ids = {i["id"] for i in plan["items"]}
    activity = {k: v for k, v in (old.get("activity") or {}).items() if k in ids and isinstance(v, dict)}
    struggles = list(self_map.get("struggles") or [])
    blockers = _blockers(ws, settings, ready)
    preview = choose(plan, struggles, activity, campaign_ready=not blockers)
    top = plan["items"][0] if plan["items"] else None
    state = {"schema": SCHEMA, "utc": old.get("utc") or _now(), "plan": plan, "next": preview, "blockers": blockers,
             "activity": activity, "top_id": top["id"] if top else None, "history": list(old.get("history") or [])}
    comparable = lambda s: {k: v for k, v in s.items() if k != "utc"}          # noqa: E731
    if comparable(state) != comparable(old):
        state["utc"] = _now()
        _write_json(ws.home / PLAN_FILE, state)
    if top and top["id"] != old.get("top_id") and settings["kaizen"]:
        ws.ledger.append("self_plan.first_changed", {"first": top["id"], "score": top["score"]["total"], "previous": old.get("top_id")})
        runesmith_md.self_plan_first(ws, top["title"], top["score"]["total"])
    return state


def turn(ws, *, campaign_ready: bool = False, say: Callable[..., None] | None = None) -> str:
    """One work turn. Counts it (kept in the home before anything else happens) and, when it is a self-improvement turn,
    acts on the plan. Returns ``"subject"`` only when a campaign should start now, else ``"object"``: the project's work.
    Never raises, and never changes Runesmith itself: the only change it can start is a gated campaign."""
    try:
        return _turn(ws, campaign_ready, say or (lambda *a, **k: None))
    except Exception:
        return "object"


def _turn(ws, campaign_ready: bool, say: Callable[..., None]) -> str:
    settings = ws.settings()
    count = _turns(ws) + 1
    with ws._lock:
        _write_json(ws.home / TURNS_FILE, {"turns": count, "utc": _now()})
    if not settings["kaizen"] or settings["autonomy"] == "observe" or not is_self_turn(count, share_of(settings)):
        return "object"
    state = _refresh(ws) or {}
    plan = state["plan"]
    struggles = list(ws.self_map().get("struggles") or [])
    activity = dict(state.get("activity") or {})
    decision = choose(plan, struggles, activity, campaign_ready=campaign_ready)
    row = {"utc": _now(), "turn": count, "action": decision["action"], "item": decision["item"],
           "struggle": decision["struggle"], "text": decision["why"]}
    if decision["action"] == "plan":
        activity[decision["item"]] = {"status": "planned: needs a gate", "utc": row["utc"], "turn": count}
        ws.ledger.append("self_plan.planned", {"item": decision["item"], "turn": count, "struggle": decision["struggle"]})
        say(f"Self-improvement turn: “{decision['title']}” is planned and needs a gate before anything can change. "
            "Nothing about Runesmith was changed; back to your work.")
    elif decision["action"] == "campaign":
        activity[decision["item"]] = {"status": "campaign running", "utc": row["utc"], "turn": count}
        ws.ledger.append("self_plan.campaign_started", {"item": decision["item"], "turn": count, "struggle": decision["struggle"]})
        runesmith_md.self_campaign_started(ws, decision["title"])
        say(f"Self-improvement turn: starting a Kaizen campaign: {decision['title']}.")
    state["activity"] = activity
    state["history"] = (state.get("history") or [])[-(KEPT_HISTORY - 1):] + [row]
    state["utc"] = _now()
    _write_json(ws.home / PLAN_FILE, state)
    return "subject" if decision["action"] == "campaign" else "object"


def campaign_finished(ws, step: dict[str, Any]) -> None:
    """Record how the campaign that a self-improvement turn started ended (the run loop's step)."""
    try:
        state = _read_json(ws.home / PLAN_FILE, {})
        activity = state.get("activity") or {}
        running = [k for k, v in activity.items() if isinstance(v, dict) and v.get("status") == "campaign running"]
        words = str(step.get("decision") or "ended").replace("_", " ")
        for key in running:
            activity[key] = {"status": f"campaign: {words}", "utc": _now(), "turn": activity[key].get("turn")}
        state["activity"] = activity
        state["utc"] = _now()
        _write_json(ws.home / PLAN_FILE, state)
    except Exception:
        return


# -------------------------------------------------------------------------------------------------- the page --

def view(ws) -> dict[str, Any]:
    """What the Self-improvement page shows. Reads SELF_PLAN.json; the plan is built once when there is none yet."""
    settings = ws.settings()
    state = _read_json(ws.home / PLAN_FILE, None)
    if not isinstance(state, dict) or not state.get("plan"):
        state = refresh(ws) or {"plan": {"items": []}, "next": None, "activity": {}, "blockers": [], "history": []}
    self_map = _read_json(ws.home / "SELF_MAP.json", {})
    share = share_of(settings)
    turns = _turns(ws)
    activity = state.get("activity") or {}
    blockers = state.get("blockers") or []
    first_target = next((i["id"] for i in state["plan"].get("items", []) if i.get("rank") == 1), None)
    items = []
    for item in state["plan"].get("items", [])[:SHOWN_ITEMS]:
        status = (activity.get(item["id"]) or {}).get("status")
        if not status:
            if item["gate"]:
                status = ("a campaign can start at the next self-improvement turn" if not blockers and item["id"] == first_target
                          else "waits: " + ("; ".join(blockers) if blockers else "the first target goes first"))
            else:
                status = "not yet planned: needs a gate"
        items.append(dict(item, status=status))
    struggles = list(self_map.get("struggles") or [])
    capabilities = self_map.get("capabilities") or {}
    return {
        "kaizen_on": bool(settings["kaizen"]), "share": share, "sentence": sentence(share),
        "turns": turns, "next_self_turn_in": next_self_turn_in(turns, share),
        "map": {"version": (self_map.get("identity") or {}).get("version"),
                "generation": (self_map.get("identity") or {}).get("active_generation"),
                "components": len(self_map.get("components") or []),
                "bands": {k: v.get("band") for k, v in capabilities.items() if isinstance(v, dict) and "band" in v},
                "targets": len(self_map.get("open_targets") or []), "struggles": len(struggles),
                "current_struggles": sum(1 for s in struggles if s.get("current")),
                "unknowns": len(self_map.get("unknowns") or [])},
        "struggles": struggles[:SHOWN_ITEMS], "items": items, "next": state.get("next"), "blockers": blockers,
        "history": (state.get("history") or [])[-5:], "rule": state["plan"].get("rule") or RULE}
