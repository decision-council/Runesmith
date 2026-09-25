"""Kaizen, step 1: see where the work goes and where it fails.

The diagnosis reads only Runesmith's own opportunity records — its telemetry —
plus, for opened tasks, the matured reference outcome (reality's answer, which
arrives after the opportunity closes). It produces:

* a **value stream**: how cycle time splits between model calls, public-signal
  runs and the organ's own computation;
* **failure families**: terminal statuses, refined into signatures when the
  organ's marks say which files it read and the matured reference says where the
  fix was; and
* a **ranked target list** under a fixed, declared rule (``rank_targets``).

Nothing here is a model judgement. The same records always give the same
diagnosis, so the target Runesmith chooses for itself can be audited.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any, Iterable

from runesmith.opportunity import stage_profile

SUCCESS = "strict_success"
CENSORED_STATUSES = {"censored_transport"}
KERNEL_STATUSES = {"censored_transport", "organ_timeout", "organ_error"}
YIELD_TARGET_MIN_SHARE = 0.10


def reads_of(record: dict) -> list[str] | None:
    """Files the organ reported reading (from its telemetry marks), if it reported any."""
    reads = None
    for mark in record.get("marks", []):
        if isinstance(mark.get("reads"), list):
            reads = [r for r in mark["reads"] if isinstance(r, str)]
    return reads


def signature(record: dict) -> str:
    """Outcome family of one opportunity, refined by the reference location when known."""
    if record.get("status") in CENSORED_STATUSES:
        return "censored"
    if record.get("strict_success"):
        return SUCCESS
    family = str(record.get("status") or "unknown")
    if record.get("status") == "public_pass":
        family = "public_pass_but_strict_fail"
    reference = record.get("reference") or {}
    reads = reads_of(record)
    if reference.get("path") and reads is not None:
        family += "|reference_read" if reference["path"] in reads else "|reference_not_read"
    return family


def diagnose(records: Iterable[dict]) -> dict[str, Any]:
    records = list(records)
    uncensored = [r for r in records if r.get("status") not in CENSORED_STATUSES]
    n = len(uncensored)
    signatures = Counter(signature(r) for r in uncensored)
    by_family: dict[str, list[dict]] = defaultdict(list)
    for record in uncensored:
        by_family[signature(record)].append(record)
    families = []
    for family, count in signatures.most_common():
        members = by_family[family]
        families.append({"family": family, "count": count, "share": round(count / n, 4) if n else None,
                         "median_cycle_s": round(median(float(r.get("cycle_seconds") or 0) for r in members), 2),
                         "examples": [r.get("task_id") or r.get("key") for r in members[:6]]})
    profiles = [stage_profile(r) for r in uncensored]
    totals = {k: round(sum(p[k] for p in profiles), 2) for k in ("cycle_s", "model_s", "signal_s", "other_s")}
    shares = {k[:-2]: (round(totals[k] / totals["cycle_s"], 4) if totals["cycle_s"] else None)
              for k in ("model_s", "signal_s", "other_s")}
    purposes: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "output_failures": 0, "seconds": 0.0})
    for record in uncensored:
        for call in record.get("calls", []):
            slot = purposes[str(call.get("purpose") or "")]
            slot["calls"] += 1
            slot["output_failures"] += 1 if call.get("error_kind") == "output" else 0
            start = float(call.get("t_start") or 0.0)
            slot["seconds"] += max(0.0, float(call.get("t_end") or start) - start)
    successes = [r for r in uncensored if r.get("strict_success")]
    return {
        "schema": "runesmith.kaizen.diagnosis.v1",
        "opportunities": len(records), "censored": len(records) - n, "uncensored": n,
        "strict_successes": len(successes),
        "yield": round(len(successes) / n, 4) if n else None,
        "median_cycle_s": round(median(float(r.get("cycle_seconds") or 0) for r in uncensored), 2) if n else None,
        "median_success_cycle_s": (round(median(float(r.get("cycle_seconds") or 0) for r in successes), 2)
                                   if successes else None),
        "seconds_per_success": (round(totals["cycle_s"] / len(successes), 2) if successes else None),
        "calls_per_opportunity": round(sum(len(r.get("calls", [])) for r in uncensored) / n, 3) if n else None,
        "value_stream": {"totals_s": totals, "shares": shares,
                         "by_call_purpose": {k: dict(v, seconds=round(v["seconds"], 2)) for k, v in sorted(purposes.items())}},
        "families": families,
        "false_promotions": sum(1 for r in uncensored if r.get("status") == "public_pass" and r.get("strict_success") is False),
        "targets": rank_targets(families, shares),
    }


def rank_targets(families: list[dict], shares: dict[str, float | None]) -> list[dict]:
    """The declared Kaizen ranking rule.

    1. Lost opportunities first: every non-success, non-censored failure family
       holding at least 10% of uncensored opportunities, largest share first.
       Families caused by the kernel (timeouts, organ crashes) are admissible
       because the organ that produced them is mutable; transport censoring is
       not, because it belongs to the environment.
    2. Then cycle time: the largest stage of the value stream.
    Ties break on the family name so the ranking is deterministic.
    """
    targets = []
    lost = [f for f in families if f["family"] not in (SUCCESS, "censored") and (f["share"] or 0) >= YIELD_TARGET_MIN_SHARE]
    for family in sorted(lost, key=lambda f: (-f["share"], f["family"])):
        targets.append({"type": "yield", "family": family["family"], "share": family["share"],
                        "count": family["count"], "examples": family["examples"],
                        "predicted_metric": "strict successes per opportunity"})
    stages = [(k, v) for k, v in shares.items() if v is not None]
    if stages:
        stage, share = sorted(stages, key=lambda kv: (-kv[1], kv[0]))[0]
        targets.append({"type": "cycle_time", "stage": stage, "share": share,
                        "predicted_metric": "cycle seconds per opportunity at equal or better yield"})
    for rank, target in enumerate(targets, start=1):
        target["rank"] = rank
    return targets
