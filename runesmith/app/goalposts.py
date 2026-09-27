"""Model-proposed performance targets, separate from owner intent and measured passes."""
from __future__ import annotations

import hashlib
import json
import uuid

from runesmith.app.planner import PlannerUnavailable, _workspace_summary
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.instruments import TransportCensored

TIERS = ("minimum", "good", "frontier")
SCHEMA = {"type": "object", "properties": {
    "summary": {"type": "string"},
    "goalposts": {"type": "array", "minItems": 1, "maxItems": 12, "items": {
        "type": "object", "properties": {
            **{key: {"type": "string"} for key in
               ("title", "measurement", "target", "why", "next_check", "scenario", "window")},
            "tier": {"type": "string", "enum": list(TIERS)},
            "milestone_ids": {"type": "array", "items": {"type": "string"}},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        }, "required": ["title", "tier", "measurement", "target", "why", "next_check", "scenario", "window",
                          "milestone_ids", "evidence_refs"]}},
}, "required": ["summary", "goalposts"]}


def input_packet(ws):
    last = _read_json(ws.home / "BUILD_LAST.json", {})
    verification = last.get("verification") or {}
    return {
        "task": ("Define 3-9 useful, measurable goalposts for this project from the supplied evidence. "
                 "Cover minimum usable behavior, good operation, and ambitious frontier hypotheses where meaningful. "
                 "You choose the targets; do not just count tests. Distinguish functional quality, operational "
                 "performance and eventual real-world value. State the denominator/window or concrete scenario "
                 "in each measurement. Give a feasible next check, including edge cases and negative outcomes. "
                 "A target is a proposal, never an already-achieved result. Do not invent measurements or "
                 "interpret a missing observation as zero. Use only existing milestone IDs, or [] for a future "
                 "direction. Evidence refs name input fields such as plan, notes or latest_build. Existing "
                 "owner constraints and read-only permissions remain in force. Do not change the plan."),
        "tier_definitions": {
            "minimum": "Fundamental correctness and usable behavior, including valid citations, persistence and traceability.",
            "good": "Measurably reliable, efficient operation on a stated workload with edge cases.",
            "frontier": "An ambitious further capability or outcome beyond correctness, explicitly a hypothesis, not a world-class claim."},
        "measurement_rules": [
            "Every goal specifies a concrete scenario (fixture/workload/population) and window (one local run or a fixed observation period).",
            "Explain why the threshold is useful; any invented numerical target is a proposed assumption, not a measured baseline.",
            "Do not substitute output counts or passing tests for outcome quality. Negative results and unknowns remain visible.",
            "Propose non-destructive checks on isolated synthetic fixtures. Never wipe live data or operate a read-only service.",
            "evidence_refs must contain only supplied top-level field names, not document paths. Use blueprints for evidence in documents."],
        "brief": ws.brief().get("text", ""),
        "owner_goals": [g["text"] for g in ws.goals() if g["status"] == "active"],
        "map": _workspace_summary(ws),
        "plan": ws.plan(),
        "blueprints": ws.blueprint_text(),
        "notes": ws.notes_for_plan(),
        "latest_build": {"draft": last.get("draft"), "milestone": last.get("milestone"),
                         "status": verification.get("status"), "utc": last.get("utc"),
                         "evidence_dir": verification.get("evidence_dir"),
                         "project_checks": {k: v for k, v in (verification.get("project_checks") or {}).items()
                                            if k in ("ran", "ok", "status", "elapsed_s")},
                         "acceptance": {k: v for k, v in (verification.get("acceptance") or {}).items()
                                        if k in ("ran", "ok", "status", "elapsed_s")}},
        "existing_goalposts": ws.goalposts(),
    }


def save_goalposts(ws, data, *, author, packet_digest, evidence_keys):
    """Validate proposed targets. A model cannot mark its own target achieved."""
    if not isinstance(data, dict) or not isinstance(data.get("goalposts"), list) or not 1 <= len(data["goalposts"]) <= 12:
        raise WorkspaceError("goalposts must contain 1-12 proposed targets")
    with ws._lock:
        plan = ws.plan() or {}
        known = {m["id"] for m in plan.get("milestones", [])}
        rows = []
        for index, raw in enumerate(data["goalposts"]):
            if not isinstance(raw, dict) or raw.get("tier") not in TIERS:
                raise WorkspaceError("a goalpost needs a minimum, good or frontier tier")
            row = {"id": f"g{index+1}", "tier": raw["tier"], "status": "proposed"}
            for key, limit in (("title", 200), ("measurement", 800), ("target", 400), ("why", 800),
                               ("next_check", 800), ("scenario", 800), ("window", 400)):
                value = raw.get(key)
                if not isinstance(value, str) or not value.strip() or len(value) > limit:
                    raise WorkspaceError(f"goalpost {key} needs nonempty text, at most {limit} characters")
                row[key] = value.strip()
            for key, allowed in (("milestone_ids", known), ("evidence_refs", set(evidence_keys))):
                values = raw.get(key)
                if not isinstance(values, list) or any(not isinstance(v, str) or v not in allowed for v in values):
                    raise WorkspaceError(f"goalpost {key} contains an unknown reference")
                row[key] = list(dict.fromkeys(values))
            rows.append(row)
        previous = ws.goalposts()
        record = {"schema": "runesmith.goalposts.v1", "version": (previous or {}).get("version", 0)+1,
                  "utc": _now(), "drafted_by": author, "plan_version": plan.get("version"),
                  "input_sha256": packet_digest, "summary": str(data.get("summary") or "")[:3000],
                  "goalposts": rows, "scope": "Model-proposed targets; not measured achievement or owner acceptance."}
        if previous:
            _write_json(ws.home / "goalposts" / f"v{previous['version']}.json", previous)
        _write_json(ws.home / "GOALPOSTS.json", record)
    ws.ledger.append("goalposts.proposed", {"version": record["version"], "count": len(rows), "author": author})
    return record


def draft_goalposts(ws, router, *, checkpoint=lambda: None):
    from runesmith.app.work_modes import require_planning
    binding = require_planning(ws)
    packet = input_packet(ws)
    text = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    attempts = [_read_json(p, {}) for p in (ws.home / "goalpost-attempts").glob("*.json")]
    if any(a.get("state") in ("started", "uncertain") for a in attempts):
        raise PlannerUnavailable("An interrupted goalpost request needs reconciliation before another call.")
    if sum(a.get("input_sha256") == digest for a in attempts) >= 3:
        raise PlannerUnavailable("Three goalpost attempts on unchanged evidence; review the recorded failures first.")
    checkpoint()
    attempt_id = uuid.uuid4().hex
    path = ws.home / "goalpost-attempts" / (attempt_id + ".json")
    receipt = {"id": attempt_id, "state": "started", "utc": _now(), "input_sha256": digest,
               "packet": packet}
    _write_json(path, receipt)
    schema = json.loads(json.dumps(SCHEMA))
    item = schema['properties']['goalposts']['items']['properties']
    evidence_keys = [k for k in packet if k not in ('task', 'tier_definitions', 'measurement_rules')]
    item['evidence_refs']['items']['enum'] = evidence_keys
    known_ids = [m['id'] for m in (packet.get('plan') or {}).get('milestones', [])]
    if known_ids:
        item['milestone_ids']['items']['enum'] = known_ids
    else:
        item['milestone_ids']['maxItems'] = 0
    try:
        outcome = router.call("plan", prompt=text,
            system="You are Runesmith's planning instrument. Return the requested JSON object, not implementation code.",
            schema=schema, max_tokens=5000, key="goalposts-"+attempt_id)
    except (TransportCensored, OSError) as error:
        _write_json(path, dict(receipt, state="uncertain", error=str(error)[:300]))
        raise PlannerUnavailable("Goalpost transport uncertain; inspect the saved attempt before retrying.") from error
    receipt.update(state="answered", finished=_now(), answer=outcome.data,
                   instrument={k: outcome.receipt.get(k) for k in
                               ("model", "requested_model", "answered_by", "job_id", "est_usd")})
    _write_json(path, receipt)
    if not outcome.ok:
        raise PlannerUnavailable(f"Goalpost answer unusable: {(outcome.error or 'no JSON')[:200]}")
    checkpoint()
    # Preserve the completed answer, but never overwrite a plan/evidence update made during the call.
    if require_planning(ws) != binding or input_packet(ws) != packet:
        raise PlannerUnavailable("Goalpost inputs changed during authoring; saved answer awaits review.")
    author = outcome.receipt.get("answered_by") or outcome.receipt.get("model")
    try:
        return save_goalposts(ws, outcome.data, author=author, packet_digest=digest, evidence_keys=evidence_keys)
    except WorkspaceError as error:
        _write_json(path, dict(receipt, validation_error=str(error)))
        raise
