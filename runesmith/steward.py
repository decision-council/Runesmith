"""``runesmith steward``: lowered into a workspace, it keeps finding work and keeps improving.

One round:

1. map the workspace (objects, kinds, objectives, the next rung);
2. discover repair opportunities in every Python object, on throwaway copies;
3. keep only opportunities not served before *for the same source state*: an object
   whose ``src`` has not changed is not re-served for the same failing tests;
4. serve them through the run loop, which interleaves Kaizen steps and online trials;
5. write REPORT.md and count the proposals waiting for review.

Rounds repeat every ``interval_s`` seconds. The steward never edits an object: fixes
become proposals (``runesmith proposals``), and objects named in the config's
``steward.exclude`` list are never probed at all.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from runesmith.canon import digest, digest_tree
from runesmith.discover import discover
from runesmith.envmap import build_environment_map
from runesmith.ledger import Ledger
from runesmith.loop import run_loop
from runesmith.proposals import list_proposals
from runesmith.report import write_report


def opportunity_id(opportunity: dict[str, Any]) -> str:
    """Identity of an opportunity: the object, its failing tests and the exact source they fail on."""
    repo = Path(opportunity["repo"])
    return digest({"repo": repo.name, "failing_tests": sorted(opportunity["failing_tests"]),
                   "src": digest_tree(repo / "src") if (repo / "src").is_dir() else None})[7:23]


def steward_round(*, home: Path, workspace: Path, router, seed: str, exclude: set[str] = frozenset(),
                  max_objects: int = 50, loop_settings: dict | None = None,
                  out: Callable[[str], None] = print) -> dict[str, Any]:
    home = Path(home)
    ledger = Ledger(home / "ledger.jsonl")
    env_map = build_environment_map(Path(workspace), probe=False, max_objects=max_objects)
    objects = [o for o in env_map["objects"] if o["kind"] == "python_repository"]
    skipped = sorted(o["name"] for o in objects if o["name"] in exclude)
    served_path = home / "served_opportunities.json"
    served: dict[str, str] = json.loads(served_path.read_text(encoding="utf-8")) if served_path.exists() else {}
    fresh: list[dict[str, Any]] = []
    statuses: dict[str, str] = {}
    for obj in objects:
        if obj["name"] in exclude:
            continue
        if not (Path(obj["path"]) / "src").is_dir():
            statuses[obj["name"]] = "skipped: not a src-layout repository (the shipped repair organ needs src/)"
            continue
        found = discover(Path(obj["path"]), scratch=home / "scratch")
        statuses[obj["name"]] = found["status"]
        for opportunity in found["opportunities"]:
            oid = opportunity_id(opportunity)
            if oid not in served:
                fresh.append(dict(opportunity, id=oid))
    out(f"mapped {len(objects)} Python object(s); excluded {skipped or 'none'}; "
        f"{len(fresh)} new opportunity(ies)")
    for name, status in sorted(statuses.items()):
        out(f"  {name:30} {status}")
    summary = run_loop(home=home, opportunities=fresh, seed=seed, router=router, **(loop_settings or {})) if fresh else {}
    for opportunity in fresh:
        served[opportunity["id"]] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    served_path.write_text(json.dumps(served, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    report = write_report(home)
    waiting = len(list_proposals(home))
    result = {"objects": len(objects), "excluded": skipped, "statuses": statuses, "new_opportunities": len(fresh),
              "strict_successes": summary.get("strict_successes", 0), "subject_steps": summary.get("subject_steps", 0),
              "skipped_environment": summary.get("skipped_environment", 0),
              "proposals_waiting": waiting, "report": str(report)}
    ledger.append("steward.round", {k: v for k, v in result.items() if k != "report"})
    out(f"served {len(fresh)}: {result['strict_successes']} judge-accepted, {result['subject_steps']} Kaizen step(s); "
        f"{waiting} proposal(s) waiting for review; report: {report}")
    return result


def steward(*, home: Path, workspace: Path, router, seed: str, rounds: int = 1, interval_s: float = 3600.0,
            exclude: set[str] = frozenset(), max_objects: int = 50, loop_settings: dict | None = None,
            out: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep) -> list[dict[str, Any]]:
    # One seed for every round: it fixes the experience/validation split, so a task the Kaizen author was
    # scored on can never later show up among the author's examples.
    results = []
    for index in range(rounds):
        out(f"== steward round {index + 1}/{rounds} ==")
        results.append(steward_round(home=home, workspace=workspace, router=router, seed=seed,
                                     exclude=exclude, max_objects=max_objects, loop_settings=loop_settings, out=out))
        if index + 1 < rounds:
            sleep(interval_s)
    return results
