"""The self-map: Runesmith's evidence-bound description of itself (SELF_MAP.json).

Runesmith should not rediscover itself on every cycle. The self-map records,
from its own bytes and its own telemetry:

* **identity** — version, kernel digest, active generation and lineage;
* **components** — every kernel module and organ, with its purpose, public
  symbols and digest, split into the fixed kernel and the mutable surface;
* **affordances** — what an organ may ask of the kernel, and the envelope;
* **capabilities** — measured performance placed in bands (bad / minimal /
  optimal / world-class), where missing evidence is ``unknown``, never a
  guess; and
* **open targets** — the ranked Kaizen targets from the latest diagnosis; and
* **struggles** — the milestones the work is stuck on or fails again and again, each with what keeps failing, how
  often and since when (derived by the Studio from the object-side records it keeps; empty without them).

It is a projection: rebuilding it from the same bytes and records gives the
same map. Facts are ``observed``; purposes read from docstrings are
``declared``; anything unmeasured is listed under ``unknowns``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from runesmith import __version__, generations
from runesmith.canon import digest, digest_file
from runesmith.kaizen.affordances import audit as audit_affordances
from runesmith.kaizen.diagnose import diagnose
from runesmith.opportunity import Envelope

PACKAGE_ROOT = Path(__file__).resolve().parent

# Declared capability ladders. Bands follow the owner's vocabulary:
#   bad < minimal <= value < optimal <= value < world_class
# "optimal" is a strong owner-chosen target, not a proven optimum; "world_class"
# needs external comparison evidence, so it starts unknown (None).
CAPABILITY_LADDERS: dict[str, dict[str, Any]] = {
    "repair_yield": {"unit": "strict repairs per uncensored opportunity", "higher_is_better": True,
                     "minimal": 0.30, "optimal": 0.60, "world_class": None},
    "seconds_per_repair": {"unit": "cycle seconds per strict repair", "higher_is_better": False,
                           "minimal": 600.0, "optimal": 120.0, "world_class": None},
    "calls_per_repair": {"unit": "model calls per strict repair", "higher_is_better": False,
                         "minimal": 10.0, "optimal": 3.0, "world_class": None},
    "false_promotion_rate": {"unit": "public passes that fail the held-out judge, per opportunity",
                             "higher_is_better": False, "minimal": 0.10, "optimal": 0.02, "world_class": None},
}
BAND_KEYS = ("unit", "minimal", "optimal", "world_class", "higher_is_better")


def _module_facts(path: Path, root: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return {"path": path.relative_to(root).as_posix(), "parse_error": str(error)}
    doc = ast.get_docstring(tree) or ""
    public = [node.name for node in tree.body
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_")]
    return {"path": path.relative_to(root).as_posix(), "digest": digest_file(path),
            "purpose": doc.strip().splitlines()[0] if doc.strip() else None,
            "public_symbols": public, "lines": text.count("\n") + 1}


_FACTS: dict[tuple, dict[str, Any]] = {}      # (path, size, mtime) -> the module's facts: parsing every module took a second


def components(root: Path = PACKAGE_ROOT) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        stat = path.stat()
        stamp = (str(path), stat.st_size, stat.st_mtime_ns)       # a changed file is read again; an unchanged one is not
        facts = _FACTS.get(stamp)
        if facts is None:
            facts = _module_facts(path, root)
            facts["region"] = ("organ (mutable)" if facts["path"].startswith("organs/") else
                               "studio (interface)" if facts["path"].startswith("app/") else "kernel (fixed)")
            _FACTS[stamp] = facts
        rows.append(dict(facts))
    return rows


def band(value: float | None, ladder: dict[str, Any]) -> str:
    """``bad`` / ``minimal`` / ``optimal`` / ``world_class``, or ``unknown`` without evidence."""
    if value is None:
        return "unknown"
    better = (lambda a, b: a >= b) if ladder["higher_is_better"] else (lambda a, b: a <= b)
    if ladder.get("world_class") is not None and better(value, ladder["world_class"]):
        return "world_class"
    if ladder.get("optimal") is not None and better(value, ladder["optimal"]):
        return "optimal"
    if ladder.get("minimal") is not None and better(value, ladder["minimal"]):
        return "minimal"
    return "bad"


def capabilities(records: list[dict]) -> dict[str, Any]:
    uncensored = [r for r in records if r.get("status") != "censored_transport"]
    judged = [r for r in uncensored if r.get("strict_success") is not None]
    wins = [r for r in judged if r.get("strict_success")]
    measured = {
        "repair_yield": (len(wins) / len(judged)) if judged else None,
        "seconds_per_repair": (sum(float(r.get("cycle_seconds") or 0) for r in judged) / len(wins)) if wins else None,
        "calls_per_repair": (sum(len(r.get("calls", [])) for r in judged) / len(wins)) if wins else None,
        "false_promotion_rate": (sum(1 for r in judged if r.get("status") == "public_pass" and not r.get("strict_success"))
                                 / len(judged)) if judged else None,
    }
    out = {}
    for name, ladder in CAPABILITY_LADDERS.items():
        value = measured[name]
        out[name] = {"value": round(value, 4) if value is not None else None, "band": band(value, ladder),
                     "evidence": {"opportunities": len(judged)} if value is not None else "unknown",
                     **{k: ladder[k] for k in BAND_KEYS}}
    if judged:
        out["median_cycle_s"] = round(median(float(r.get("cycle_seconds") or 0) for r in judged), 2)
    return out


def build_self_map(*, home: Path | None = None, records: Iterable[dict] | None = None,
                   struggles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = list(records or [])
    rows = components()
    lineage = []
    active_id = None
    if home is not None:
        active_id = generations.active(home)
        lineage = [{k: g.get(k) for k in ("id", "label", "parent", "organ_digest", "frozen_utc", "provenance")}
                   for g in generations.list_generations(home)]
    unknowns = []
    if not records:
        unknowns.append("no opportunity telemetry supplied: every capability is unknown")
    unknowns.append("frontier bands need external comparison evidence and are unknown by default")
    diagnosis = diagnose(records) if records else None
    options = {}
    if home is not None and active_id:
        for organ in sorted((Path(home) / "generations" / active_id / "organs").glob("*.py")):
            unused = audit_affordances(organ.read_text(encoding="utf-8"))["unused"]
            if unused:
                options[organ.stem] = {"unused_affordances": unused}
    body = {
        "schema": "runesmith.self_map.v1",
        "identity": {"version": __version__, "kernel_digest": generations.kernel_digest(), "active_generation": active_id},
        "regions": {"kernel": "fixed: identity, ledger, router, envelope, public signals, confinement, generations",
                    "organs": "mutable: policies the Kaizen engine may rewrite; frozen per generation",
                    "studio": "interface: the local app that shows the maps and relays the owner's decisions; runs no organ"},
        "components": rows,
        "affordances": {"ask": "one model call through the kernel router (charged)",
                        "run_signal": "the object's public tests with file overrides; optional executed-line trace",
                        "budget": "remaining calls, signal runs and seconds", "log": "telemetry mark",
                        "recall": "memory retrieval, when the host grants memory"},
        "default_envelope": {k: v for k, v in Envelope().__dict__.items()},
        "capabilities": capabilities(records) if records else
        {name: {"value": None, "band": "unknown", **ladder} for name, ladder in CAPABILITY_LADDERS.items()},
        "open_targets": diagnosis["targets"] if diagnosis else [],
        "improvement_options": options,
        # Where the work Runesmith does for others struggles: each milestone that is stuck or fails again and again, with
        # what keeps failing, how often and since when (the Studio derives them from its own records; none elsewhere).
        "struggles": list(struggles or []),
        "lineage": lineage,
        "unknowns": unknowns,
    }
    body["map_digest"] = digest({k: v for k, v in body.items() if k != "map_digest"})
    return body


def write_self_map(path: Path, **kwargs) -> dict[str, Any]:
    self_map = build_self_map(**kwargs)
    text = (json.dumps(self_map, indent=1, default=str) + "\n").encode("utf-8")       # LF on every platform
    try:
        if Path(path).read_bytes() == text:                  # unchanged (the map has no clock): not written again
            return self_map
    except OSError:
        pass
    Path(path).write_bytes(text)
    return self_map
