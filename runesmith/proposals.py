"""Judge-accepted fixes as reviewable patches: Runesmith proposes, a human decides.

The run loop never edits an object. Each repair that the held-out judge accepted is
kept in the experience store. This module turns those repairs into unified diffs
against the source as it was when the opportunity was served, with ``a/`` and
``b/`` prefixes, so ``git apply`` can take them from the repository root. If the
repository has changed since, ``git apply`` refuses, which is the safe outcome.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from runesmith.loop import ExperienceStore


def _diff(parent: dict[str, str], fix: dict[str, str]) -> str:
    chunks = []
    for path in sorted(fix):
        before, after = parent.get(path, ""), fix[path]
        lines = list(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{path}", f"b/{path}"))
        for i, line in enumerate(lines):
            if not line.endswith("\n"):                    # last line of a file without a final newline
                lines[i] = line + "\n\\ No newline at end of file\n"
        chunks.append("".join(lines))
    return "".join(chunks)


def proposal_states(home: Path) -> dict[str, dict[str, Any]]:
    """What the owner did with each proposal in the Studio (applied, undone, rejected), keyed by proposal."""
    try:
        states = json.loads((Path(home) / "PROPOSALS_STATE.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return states if isinstance(states, dict) else {}


def list_proposals(home: Path) -> list[dict[str, Any]]:
    store = ExperienceStore(Path(home) / "experience")
    states = proposal_states(home)
    out = []
    for task in store.tasks():
        fix = store.verified_fix(task["key"])
        if not fix:
            continue
        done = states.get(task["key"]) or {}
        out.append({"key": task["key"], "repo": task["repo"], "failing_tests": task["failing_tests"],
                    "files": sorted(fix), "diff": _diff(store.parent_src(task["key"]), fix),
                    "state": done.get("state", "waiting"), "state_utc": done.get("utc")})
    return out


def write_proposals(home: Path, into: Path) -> list[Path]:
    """Save each proposal still waiting as a patch; one already applied, undone or rejected is not handed out again."""
    into = Path(into)
    into.mkdir(parents=True, exist_ok=True)
    written = []
    for proposal in list_proposals(home):
        if proposal["state"] != "waiting":
            continue
        path = into / f"{proposal['key']}.patch"
        header = (f"# Runesmith proposal {proposal['key']}\n# repository: {proposal['repo']}\n"
                  f"# fixes: {', '.join(proposal['failing_tests'])}\n"
                  "# accepted by the held-out judge; review before applying (git apply <this file>)\n")
        path.write_text(header + proposal["diff"], encoding="utf-8")
        written.append(path)
    return written
