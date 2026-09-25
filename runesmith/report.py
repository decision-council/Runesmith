"""A human-readable dashboard of one Runesmith home (REPORT.md).

Everything here is a projection of the home's own records: the ledger, the
generations, the session records, the trial files and the self-map. Rebuilding
the report from the same home gives the same content, so it can be shared as
evidence of how this Runesmith has been doing and improving.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from runesmith import __version__, generations
from runesmith.kaizen.affordances import audit as audit_affordances
from runesmith.kaizen.attention import SHARE_BP, Attention
from runesmith.kaizen.diagnose import diagnose
from runesmith.kaizen.trial import Trial
from runesmith.ledger import Ledger
from runesmith.selfmap import capabilities

BAND_MARK = {"world_class": "world-class", "optimal": "optimal", "minimal": "minimal", "bad": "bad", "unknown": "unknown"}


def _sessions(home: Path) -> list[dict[str, Any]]:
    root = home / "sessions"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*.json"))] if root.exists() else []


def by_model(sessions: list[dict[str, Any]]) -> list[str]:
    """How each model that answered has done: what Runesmith knows about its own instruments."""
    stats: dict[str, dict[str, Any]] = {}
    for s in sessions:
        seen = set()
        for call in s.get("calls", []):
            name = call.get("model") or call.get("instrument") or "unknown"
            row = stats.setdefault(name, {"calls": 0, "unusable": 0, "sessions": 0, "repairs": 0, "tokens_out": 0})
            row["calls"] += 1
            row["unusable"] += 1 if call.get("error_kind") == "output" else 0
            row["tokens_out"] += int(call.get("tokens_out") or 0)
            seen.add(name)
        for name in seen:
            stats[name]["sessions"] += 1
            stats[name]["repairs"] += 1 if s.get("strict_success") else 0
    if not stats:
        return []
    lines = ["### By model (who answered, and how usable the answers were)", "",
             "| Model | Calls | Unusable answers | Opportunities | Strict repairs | Output tokens per call |",
             "|---|---|---|---|---|---|"]
    for name, row in sorted(stats.items(), key=lambda kv: -kv[1]["calls"]):
        lines.append(f"| {name} | {row['calls']} | {row['unusable'] / row['calls']:.0%} | {row['sessions']} | "
                     f"{row['repairs']} | {row['tokens_out'] / row['calls']:.0f} |")
    lines.append("")
    return lines


def build_report(home: Path, *, recent: int = 10) -> str:
    home = Path(home)
    sessions = _sessions(home)
    active = generations.active(home)
    lineage = generations.list_generations(home)
    ledger = Ledger(home / "ledger.jsonl").verify()
    lines = [f"# Runesmith report — {home.name}", "",
             f"Runesmith {__version__}. Active generation **{active or 'none'}**. "
             f"Ledger: {'intact' if ledger.get('ok') else 'BROKEN: ' + str(ledger.get('error'))}, "
             f"{ledger.get('records', 0)} records.", ""]

    lines += ["## Generations", "", "| Generation | Parent | Label | Frozen |", "|---|---|---|---|"]
    for g in lineage:
        marker = " (active)" if g["id"] == active else ""
        lines.append(f"| {g['id']}{marker} | {g.get('parent') or '—'} | {g.get('label')} | {g.get('frozen_utc')} |")
    lines.append("")

    lines += ["## Capabilities (measured, in bands)", ""]
    if sessions:
        lines += ["| Capability | Value | Band | Minimal | Optimal |", "|---|---|---|---|---|"]
        for name, cap in capabilities(sessions).items():
            if isinstance(cap, dict):
                lines.append(f"| {name} | {cap['value'] if cap['value'] is not None else '—'} | "
                             f"{BAND_MARK.get(cap['band'], cap['band'])} | {cap['minimal']} | {cap['optimal']} |")
        lines.append("")
        by_generation: dict[str, list[dict]] = {}
        for s in sessions:
            by_generation.setdefault(s.get("generation") or "?", []).append(s)
        lines += ["### By generation", "", "| Generation | Opportunities | Strict repairs | Yield | Median cycle (s) |",
                  "|---|---|---|---|---|"]
        for gen, rows in by_generation.items():
            judged = [r for r in rows if r.get("strict_success") is not None]
            wins = sum(1 for r in judged if r.get("strict_success"))
            yield_text = f"{wins / len(judged):.2f}" if judged else "—"
            cycle = f"{median(float(r.get('cycle_seconds') or 0) for r in judged):.1f}" if judged else "—"
            lines.append(f"| {gen} | {len(rows)} | {wins} | {yield_text} | {cycle} |")
        lines.append("")
        lines += by_model(sessions)
    else:
        lines += ["No opportunities recorded yet. Every capability is unknown.", ""]

    lines += ["## Attention (how much of its time goes to improving itself, and why)", ""]
    attention = Attention.load(home / "ATTENTION.json")
    if attention is None:
        lines.append("No attention state yet (it is created by `run` or `steward`).")
    else:
        drift = attention.snapshot()["drift"]
        lines.append(f"- Mode **{attention.mode}**: {SHARE_BP[attention.mode] / 100:.0f}% of steps go to Kaizen.")
        if attention.blocking_signature:
            lines.append(f"- Blocking signal: `{attention.blocking_signature}`.")
        if attention.transitions:
            last = attention.transitions[-1]
            lines.append(f"- Last change: {last['from']} → {last['to']} ({last['reason']}).")
        if drift["baseline_yield"] is None:
            lines.append(f"- Drift chart: collecting its baseline ({drift['baseline_outcomes']}/{attention.drift_baseline_n} outcomes).")
        else:
            lines.append(f"- Drift chart: baseline yield ≥ {drift['baseline_yield']:.2f} (conservative bound); "
                         f"CUSUM {drift['cusum']} of {drift['threshold']} (alarm at the threshold).")
    lines.append("")

    lines += ["## Where it struggles (open Kaizen targets)", ""]
    targets = diagnose(sessions)["targets"] if sessions else []
    if targets:
        for t in targets[:5]:
            what = t.get("family") or f"stage: {t.get('stage')}"
            lines.append(f"{t['rank']}. **{what}** — share {t['share']} ({t['type']})")
    else:
        lines.append("No targets yet.")
    lines.append("")

    lines += ["## What it could try next (affordances the active organs leave unused)", ""]
    organs = home / "generations" / active / "organs" if active else None
    listed = False
    for organ in sorted(organs.glob("*.py")) if organs and organs.exists() else []:
        unused = audit_affordances(organ.read_text(encoding="utf-8"))["unused"]
        if unused:
            listed = True
            lines.append(f"- **{organ.stem}**: " + "; ".join(f"`{u['affordance']}` ({u['offers']})" for u in unused))
    if not listed:
        lines.append("None found.")
    lines.append("")

    lines += ["## Trials (how candidates earn activation)", ""]
    open_trial = Trial.load(home / "TRIAL.json")
    closed = sorted(home.glob("TRIAL-*.json"))
    if open_trial:
        lines.append(f"- **Open:** {open_trial.candidate} vs {open_trial.incumbent}, counts {open_trial.counts}, "
                     f"{len(open_trial.looks)} look(s), level per look {open_trial.level:.4f}")
    for path in closed:
        t = Trial.load(path)
        lines.append(f"- **{t.decision}:** {t.candidate} vs {t.incumbent}, counts {t.counts}, {len(t.looks)} look(s)")
    if not open_trial and not closed:
        lines.append("No trials yet.")
    lines.append("")

    lines += [f"## Recent opportunities (last {recent})", "", "| Session | Status | Strict | Calls | Cycle (s) | Generation |",
              "|---|---|---|---|---|---|"]
    for s in sessions[-recent:]:
        lines.append(f"| {s.get('key')} | {s.get('status')} | {s.get('strict_success')} | {s.get('model_calls')} | "
                     f"{s.get('cycle_seconds')} | {s.get('generation') or '—'} |")
    statuses = Counter(s.get("status") for s in sessions)
    lines += ["", f"All statuses: {dict(statuses)}" if statuses else "", ""]
    return "\n".join(lines)


def write_report(home: Path) -> Path:
    path = Path(home) / "REPORT.md"
    path.write_text(build_report(home), encoding="utf-8")
    return path
