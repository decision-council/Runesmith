"""Object-target discovery: turn an object's failing tests into repair opportunities.

Runesmith does not wait to be told what is broken. Probing a code object runs
its own test suite once (this executes the object's code, so it is opt-in) on a
throwaway copy, so nothing is written into the object itself. It groups failing
tests by test file and writes one repair opportunity per file:

* ``failing_tests`` — the public signal the repair organ may run;
* ``judge_tests`` — the whole test file, a stricter held-out check the organ
  never sees; and
* ``issue`` — the sanitized failure excerpt, phrased like a CI report.

The opportunity is a proposal. Whether a failing test is a defect in the
source, in the test, or in the environment is exactly what the repair
attempt and its judge have to settle.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

from runesmith.objects.code import sanitize, throwaway_copy

FAILED_LINE = re.compile(r"^(?:FAILED|ERROR) (\S+?::\S+)(?: - (.*))?$")
MISSING_MODULE = re.compile(r"(?:ModuleNotFoundError|ImportError): No module named '([\w.]+)'")
NETWORK = re.compile(r"ConnectionError|ConnectTimeout|ConnectionRefusedError|gaierror|URLError|getaddrinfo failed|"
                     r"Name or service not known|Temporary failure in name resolution|NewConnectionError")


def triage_reason(reason: str, repo: Path) -> dict[str, str] | None:
    """Classify a failure the source cannot fix: a missing third-party module, or a network dependency.

    Conservative: a missing module that exists in the object's own ``src/`` (or top level) is a source
    defect, such as a renamed module, and stays repairable. Anything unrecognised is left to the repair attempt.
    """
    missing = MISSING_MODULE.search(reason or "")
    if missing:
        top = missing.group(1).split(".")[0]
        internal = any((base / top).is_dir() or (base / f"{top}.py").is_file() for base in (repo / "src", repo))
        if not internal:
            return {"kind": "environment", "reason": f"missing third-party module {top!r}: install it; no source edit helps"}
    if NETWORK.search(reason or ""):
        return {"kind": "environment", "reason": "the test needs network access; no source edit helps"}
    return None


def run_suite(repo: Path, *, python: str = sys.executable, timeout_s: int = 900) -> tuple[int | None, str]:
    env = os.environ.copy()
    src = repo / "src"
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(src) if src.is_dir() else "", str(repo)) if p)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["COLUMNS"] = "400"                                # untruncated summary lines, so triage sees the whole reason
    try:
        proc = subprocess.run([python, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider"], cwd=str(repo),
                              env=env, capture_output=True, text=True, timeout=timeout_s, errors="replace")
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return None, ""


def opportunities_from_output(output: str, repo: Path, *, max_per_file: int = 5,
                              workdir: Path | None = None) -> list[dict[str, Any]]:
    by_file: "OrderedDict[str, list[str]]" = OrderedDict()
    reasons: dict[str, str] = {}
    for line in output.splitlines():
        match = FAILED_LINE.match(line.strip())
        if match:
            node = match.group(1).replace("\\", "/")      # Windows pytest prints backslashes in node ids
            by_file.setdefault(node.split("::", 1)[0], [])
            if node not in by_file[node.split("::", 1)[0]]:
                by_file[node.split("::", 1)[0]].append(node)
            if match.group(2):
                reasons[node] = match.group(2)
    lines = sanitize(output, workdir or repo)
    opportunities = []
    for test_file, nodes in by_file.items():
        chosen = nodes[:max_per_file]
        excerpt = [l for l in lines if any(n in l for n in chosen) or l.startswith("E ")][:12]
        issue = ("CI reports a regression in this repository.\n"
                 f"Failing tests ({len(chosen)}):\n" + "".join(f"- {n}\n" for n in chosen)
                 + "Failure output (excerpt):\n" + "\n".join(excerpt)
                 + "\nMake the smallest source change under src/ that restores the intended behavior. "
                   "The test files are not visible to you.")
        opportunity = {"repo": str(repo), "failing_tests": chosen, "judge_tests": [test_file], "issue": issue}
        verdicts = [triage_reason(reasons.get(node, ""), repo) for node in chosen]
        if verdicts and all(verdicts):                    # every failing test here is an environment problem
            opportunity["triage"] = verdicts[0]
        opportunities.append(opportunity)
    return opportunities


def discover(repo: Path, *, python: str = sys.executable, timeout_s: int = 900, in_place: bool = False,
             scratch: Path | None = None) -> dict[str, Any]:
    """Run the suite once (on a throwaway copy unless ``in_place``) and return repair opportunities."""
    repo = Path(repo).resolve()
    if in_place:
        workdir = repo
        code, output = run_suite(repo, python=python, timeout_s=timeout_s)
    else:
        with throwaway_copy(repo, scratch) as workdir:
            code, output = run_suite(workdir, python=python, timeout_s=timeout_s)
    if code is None:
        return {"repo": str(repo), "status": "timed_out", "opportunities": []}
    if code == 0:
        return {"repo": str(repo), "status": "green", "opportunities": []}
    opportunities = opportunities_from_output(output, repo, workdir=workdir)
    result = {"repo": str(repo), "status": "failing" if opportunities else "error_without_failures",
              "exit_code": code, "opportunities": opportunities}
    if not opportunities:                          # the tests could not even run: say why, if pytest said
        result["detail"] = first_error(output, workdir)
        result["triage"] = triage_reason(result["detail"] or "", repo)
    return result


ERROR_LINE = re.compile(r"\b[A-Z]\w*(?:Error|Exception)\b: .+|no tests ran|collected 0 items|file or directory not found")


def first_error(output: str, workdir: Path) -> str | None:
    """The first error message in a test run's output, with local paths removed."""
    text = output.replace(str(workdir), "").replace(str(workdir).replace("\\", "/"), "")
    for line in text.splitlines():
        match = ERROR_LINE.search(line)
        if match:
            return match.group(0).strip()[:240]
    return None
