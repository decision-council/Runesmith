"""Running one repair opportunity on a local repository (shared by the CLI and the run loop)."""

from __future__ import annotations

import difflib
from pathlib import Path

from runesmith.config import build_router, envelope_from, load_config
from runesmith.memory import Memory
from runesmith.objects.code import CodeTask
from runesmith.opportunity import run_opportunity


def run_local_task(*, home: Path, organ_dir: Path, repo: Path, failing_tests: list[str], issue: str,
                   judge_tests: list[str] | None, key: str, src_override_dir: Path | None = None,
                   router=None, remember: bool = True) -> tuple[dict, dict, dict]:
    """One opportunity; returns (session record, final changed files, parent source files).

    The judge runs ``judge_tests`` (default: the failing tests) on the organ's final
    state, in the kernel's work copy, after the organ has finished.
    """
    config = load_config(home)
    if not (Path(repo) / "src").is_dir():
        raise SystemExit(f"{repo}: the shipped repair organ (g0) supports src-layout repositories; "
                         "other layouts are a Kaizen target for a later generation")
    task = CodeTask(Path(repo), failing_tests, scratch=Path(home) / "scratch", src_override_dir=src_override_dir)
    memory = Memory(Path(home) / "memory.jsonl")
    try:
        parent = task.src_files()
        record = run_opportunity(task=task, issue=issue, organ_dir=organ_dir, router=router or build_router(config, home=Path(home)),
                                 envelope=envelope_from(config), key=key, scratch=Path(home) / "scratch",
                                 recall=lambda query, k: memory.recall(query, k))
        final = task.applied()
        if record["status"] != "censored_transport":
            task.failing_tests = list(judge_tests or failing_tests)
            judged = task.run()
            record["strict_success"] = bool(judged["passed"])
            record["judge"] = {"tests": task.failing_tests, "passed": judged["passed"]}
        else:
            record["strict_success"] = None
    finally:
        task.close()
    record.update(issue=issue, repo=str(repo))
    if remember and record["status"] != "censored_transport":
        # An attempt cut off by a transport failure was never judged and says nothing of its approach: not remembered, or
        # recall would warn against an approach that was never tried (it stays in the ledger and the sessions).
        verdict = {True: "judge accepted", False: "judge rejected", None: "not judged"}[record.get("strict_success")]
        memory.add("episode" if record.get("strict_success") else "negative",
                   f"{issue}\nstatus: {record['status']} ({verdict})\nchanged: {', '.join(sorted(final))}\n"
                   + change_summary(parent, final),
                   tags=[record["status"]], source={"session": key})
    return record, final, parent


def change_summary(parent: dict[str, str], final: dict[str, str], *, max_chars: int = 1200) -> str:
    """The changed lines of an attempt, bounded, so memory recalls what was tried and not only where."""
    out = []
    for path in sorted(final):
        before = parent.get(path, "").splitlines()
        after = final[path].splitlines()
        for line in difflib.unified_diff(before, after, f"a/{path}", f"b/{path}", n=0, lineterm=""):
            if not line.startswith(("---", "+++")):
                out.append(line)
    text = "\n".join(out)
    return text if len(text) <= max_chars else text[:max_chars] + "\n..."
