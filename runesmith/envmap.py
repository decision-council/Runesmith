"""The environment map: what Runesmith learns when lowered into a workspace (ENVIRONMENT.json).

Given only a directory, Runesmith inventories the **objects** it finds, proposes
**objectives** for each, places every measured metric in performance **bands**
(bad / minimal / optimal / world-class), and lays out a **build ladder** —
ordered rungs from "source present" to "mutation-tested" — marking each rung
achieved, not achieved, or unknown.

Epistemic discipline: a fact read from disk is ``observed``; an objective
Runesmith proposes for an object is ``proposed`` until an owner accepts or
replaces it; anything unmeasured is ``unknown``, never assumed. Probing (running
an object's tests) is opt-in because it executes the object's code.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from runesmith.canon import digest
from runesmith.objects.code import is_link, throwaway_copy
from runesmith.selfmap import band

SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", "node_modules", ".tox", ".mypy_cache",
             ".pytest_cache", "build", "dist", ".idea", ".vscode"}
MAX_FILES_SCANNED = 20_000

# Objective templates per object kind, in the owner's band vocabulary. Proposed, not accepted.
PYTHON_OBJECTIVES = [
    {"id": "tests_green", "metric": "test_pass_rate", "unit": "passing / collected tests", "higher_is_better": True,
     "minimal": 0.90, "optimal": 1.0, "world_class": None,
     "why": "a repository whose own tests fail cannot be improved safely"},
    {"id": "fast_feedback", "metric": "test_suite_seconds", "unit": "seconds for the full suite", "higher_is_better": False,
     "minimal": 600.0, "optimal": 60.0, "world_class": None,
     "why": "the suite is the object's public signal; slow signals slow every improvement cycle"},
    {"id": "tested_surface", "metric": "test_files_per_source_file", "unit": "ratio", "higher_is_better": True,
     "minimal": 0.2, "optimal": 0.8, "world_class": None,
     "why": "untested modules have no signal to improve against"},
]
PYTHON_LADDER = ["source_present", "tests_present", "tests_collect", "tests_pass", "fast_suite",
                 "coverage_measured", "mutation_tested"]


def walk_files(root: Path) -> list[Path]:
    """The files of a folder that belong to it: no version-control or tool folders, nothing hidden, and never
    through a link or junction. At most MAX_FILES_SCANNED."""
    return _walk(root)


def _entry_is_link(entry: os.DirEntry) -> bool:
    """From the directory listing itself, with no extra system call: a symbolic link or a junction."""
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)                  # Python 3.12+
    return bool(is_junction and is_junction())


def _scan(root: Path) -> list[tuple[Path, int, int]]:
    """(file, size, modification time in ns) for the files that belong to ``root``, in os.walk's top-down order with
    sorted names; never through a link or junction; at most MAX_FILES_SCANNED. On Windows the sizes and times come
    with the listing, so a large folder costs one pass and no per-file calls."""
    out: list[tuple[Path, int, int]] = []
    stack = [Path(root)]
    while stack:
        here = stack.pop()
        try:
            with os.scandir(here) as listing:
                entries = list(listing)
        except OSError:
            continue
        dirs, files = [], []
        for entry in entries:
            try:
                if _entry_is_link(entry):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRS and not entry.name.startswith("."):
                        dirs.append(entry.name)
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry)
            except OSError:
                continue
        for entry in sorted(files, key=lambda e: e.name):
            try:
                st = entry.stat(follow_symlinks=False)
                out.append((here / entry.name, st.st_size, st.st_mtime_ns))
            except OSError:
                out.append((here / entry.name, 0, 0))
            if len(out) >= MAX_FILES_SCANNED:
                return out
        stack.extend(here / d for d in sorted(dirs, reverse=True))      # popped in sorted order: depth first
    return out


def _walk(root: Path) -> list[Path]:
    return [path for path, _, _ in _scan(root)]


PYTHON_MARKERS = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "tox.ini"}


def _python_at_top(path: Path, names: set[str]) -> bool:
    """A module, or a package folder (with __init__.py or __main__.py), directly in ``path``."""
    return any(n.endswith(".py") for n in names) or any(
        (path / n).is_dir() and ((path / n / "__init__.py").is_file() or (path / n / "__main__.py").is_file())
        for n in names)


def _python_tests(path: Path, names: set[str]) -> bool:
    return (any(n.startswith("test_") and n.endswith(".py") for n in names)
            or any((path / d).is_dir() and next((path / d).glob("test*.py"), None) is not None for d in ("tests", "test")))


DATA_SUFFIXES = (".csv", ".tsv", ".xlsx", ".xls")


def _reports_folder(path: Path, names: set[str]) -> bool:
    """Mostly report files: exports from a till, a spreadsheet or a web shop. A bakery's weekly CSV exports used to be
    a plain folder whose next step was "readme present" (journey J5-F2)."""
    files = [n for n in names if not n.startswith(".") and (path / n).is_file()]
    data = [n for n in files if n.lower().endswith(DATA_SUFFIXES)]
    return bool(data) and len(data) * 2 >= len(files)


def classify_object(path: Path) -> str:
    names = {p.name for p in path.iterdir()} if path.is_dir() else set()
    if names & PYTHON_MARKERS:
        return "python_repository"
    if "package.json" in names:
        return "node_repository"
    if (path / "src").is_dir() and (path / "tests").is_dir() and next((path / "src").rglob("*.py"), None):
        return "python_repository"
    # The flat layout of many small projects: a package or module and its tests, with no packaging files (J3-B1:
    # its README used to make it a "document collection", so its failing tests were never run).
    if _python_at_top(path, names) and _python_tests(path, names):
        return "python_repository"
    if path.is_dir() and any(n.lower().endswith((".html", ".htm")) for n in names):
        return "website"
    if path.is_dir() and _reports_folder(path, names):
        return "data_reports"
    if path.is_dir() and any(n.lower().endswith((".md", ".rst", ".txt")) for n in names):
        return "document_collection"
    return "unknown"


def python_facts(path: Path) -> dict[str, Any]:
    scanned = _scan(path)
    files = [f for f, _, _ in scanned]
    py = [f for f in files if f.suffix == ".py"]
    tests = [f for f in py if f.name.startswith("test_") or f.name.endswith("_test.py")]
    sources = [f for f in py if f not in tests and "tests" not in f.relative_to(path).parts]
    lines = 0
    for f in sources[:5000]:
        try:
            lines += f.read_text(encoding="utf-8", errors="replace").count("\n")
        except OSError:
            continue
    pyproject = path / "pyproject.toml"
    pytest_config = (path / "pytest.ini").exists() or (path / "tox.ini").exists() or (
        pyproject.exists() and "[tool.pytest" in pyproject.read_text(encoding="utf-8", errors="replace"))
    return {"files": len(files), "python_files": len(py), "source_files": len(sources), "test_files": len(tests),
            "source_lines": lines, "src_layout": (path / "src").is_dir(), "pytest_config": pytest_config,
            "version_control": (path / ".git").exists(), "truncated_scan": len(files) >= MAX_FILES_SCANNED,
            "fingerprint": _fingerprint_scanned(path, [s for s in scanned if s[0].suffix in (".py", ".toml", ".cfg", ".ini", ".txt")])}


def fingerprint(root: Path, files: list[Path]) -> str:
    """Names, sizes and modification times of the files that decide a measurement: equal means unchanged."""
    scanned = []
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        scanned.append((f, st.st_size, st.st_mtime_ns))
    return _fingerprint_scanned(root, scanned)


def _fingerprint_scanned(root: Path, scanned: list[tuple[Path, int, int]]) -> str:
    signature = hashlib.sha256()
    for f, size, mtime_ns in sorted(scanned):
        signature.update(f"{f.relative_to(root).as_posix()}|{size}|{mtime_ns}\n".encode("utf-8", "replace"))
    return signature.hexdigest()[:16]


def probe_pytest(path: Path, *, timeout_s: int = 900, python: str = sys.executable, in_place: bool = False,
                 scratch: Path | None = None) -> dict[str, Any]:
    """Run the object's own tests once (opt-in): collect, then execute, with a time cap.

    The tests run on a throwaway copy unless ``in_place``, so probing never writes into the object.
    """
    if not in_place:
        with throwaway_copy(path, scratch) as copy:
            return probe_pytest(copy, timeout_s=timeout_s, python=python, in_place=True)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    src = path / "src"
    env["PYTHONPATH"] = os.pathsep.join(p for p in [str(src) if src.is_dir() else "", str(path)] if p)
    out: dict[str, Any] = {}
    started = time.monotonic()
    try:
        collect = subprocess.run([python, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                                 cwd=str(path), env=env, capture_output=True, text=True, timeout=timeout_s, errors="replace")
        if "No module named pytest" in collect.stderr:
            # Journey J2-B3: without pytest this read as "tests do not collect or pass" for 16 passing tests.
            return _probe_unittest(path, env, timeout_s=timeout_s, python=python)
        match = re.search(r"(\d+) tests? collected", collect.stdout + collect.stderr)
        out["collected"] = int(match.group(1)) if match else None
        out["collect_exit"] = collect.returncode
    except subprocess.TimeoutExpired:
        return {"collected": None, "error": "collection timed out"}
    remaining = max(30, timeout_s - int(time.monotonic() - started))
    run_started = time.monotonic()
    try:
        run = subprocess.run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=str(path), env=env,
                             capture_output=True, text=True, timeout=remaining, errors="replace")
    except subprocess.TimeoutExpired:
        out.update(error="test run timed out", suite_seconds=None)
        return out
    text = run.stdout + run.stderr
    counts = {kind: int(n) for n, kind in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", text)}
    out.update(suite_seconds=round(time.monotonic() - run_started, 2), exit_code=run.returncode,
               passed=counts.get("passed", 0), failed=counts.get("failed", 0),
               errors=counts.get("error", 0) + counts.get("errors", 0), skipped=counts.get("skipped", 0))
    return out


def _probe_unittest(path: Path, env: dict[str, str], *, timeout_s: int, python: str) -> dict[str, Any]:
    """Run the tests with Python's own unittest, as the build checks do when pytest is not installed.

    If unittest finds no tests (pytest-style test functions, say), nothing is known: the probe says so instead of
    reporting tests that do not collect.
    """
    where = ["-s", "tests", "-t", "."] if (path / "tests").is_dir() else ["-s", ".", "-t", "."]
    started = time.monotonic()
    try:
        run = subprocess.run([python, "-m", "unittest", "discover", *where], cwd=str(path), env=env,
                             capture_output=True, text=True, timeout=timeout_s, errors="replace")
    except subprocess.TimeoutExpired:
        return {"collected": None, "runner": "unittest", "error": "test run timed out", "suite_seconds": None}
    text = run.stdout + run.stderr
    ran = re.search(r"Ran (\d+) tests?", text)
    if not ran or int(ran.group(1)) == 0:
        return {"collected": None, "runner": None,
                "unavailable": "pytest is not installed in this Python, and unittest found no tests to run"}
    counts = {kind: int(n) for kind, n in re.findall(r"(failures|errors|skipped)=(\d+)", text)}
    total = int(ran.group(1))
    failed, errors, skipped = counts.get("failures", 0), counts.get("errors", 0), counts.get("skipped", 0)
    return {"collected": total, "collect_exit": 0, "runner": "unittest",
            "suite_seconds": round(time.monotonic() - started, 2), "exit_code": run.returncode,
            "passed": total - failed - errors - skipped, "failed": failed, "errors": errors, "skipped": skipped}


def python_object(path: Path, *, probe: bool, scratch: Path | None = None) -> dict[str, Any]:
    facts = python_facts(path)
    measured: dict[str, float | None] = {
        "test_files_per_source_file": (facts["test_files"] / facts["source_files"]) if facts["source_files"] else None,
        "test_pass_rate": None, "test_suite_seconds": None}
    probe_result = probe_pytest(path, scratch=scratch) if probe else None
    if probe_result and probe_result.get("collected"):
        executed = probe_result.get("passed", 0) + probe_result.get("failed", 0) + probe_result.get("errors", 0)
        measured["test_pass_rate"] = (probe_result.get("passed", 0) / executed) if executed else None
        measured["test_suite_seconds"] = probe_result.get("suite_seconds")
    objectives = []
    for template in PYTHON_OBJECTIVES:
        value = measured.get(template["metric"])
        objectives.append(dict(template, status="proposed", value=round(value, 4) if value is not None else None,
                               band=band(value, template), evidence="observed" if value is not None else "unknown"))
    ran = None if not probe_result or probe_result.get("unavailable") else probe_result   # nothing ran: unknown
    rungs = {
        "source_present": facts["source_files"] > 0,
        "tests_present": facts["test_files"] > 0,
        "tests_collect": (ran.get("collected", 0) or 0) > 0 if ran else None,
        "tests_pass": (ran.get("exit_code") == 0) if ran and "exit_code" in ran else None,
        "fast_suite": ((ran.get("suite_seconds") or 1e9) <= 60) if ran and ran.get("suite_seconds") else None,
        "coverage_measured": None,
        "mutation_tested": None,
    }
    ladder = [{"rung": name, "status": {True: "achieved", False: "not_achieved", None: "unknown"}[rungs[name]]}
              for name in PYTHON_LADDER]
    next_rung = next((r["rung"] for r in ladder if r["status"] != "achieved"), None)
    return {"kind": "python_repository", "facts": facts, "probe": probe_result, "objectives": objectives,
            "ladder": ladder, "next_rung": next_rung}


NODE_LADDER = ["package_manifest", "source_present", "tests_present", "test_script_declared", "tests_pass",
               "lockfile_present", "typecheck_declared"]
NODE_OBJECTIVES = [
    {"id": "tests_green", "metric": "npm_test_passes", "unit": "1 if `npm test` exits 0", "higher_is_better": True,
     "minimal": 1.0, "optimal": 1.0, "world_class": None, "why": "the package's own test script is its public signal"},
    {"id": "tested_surface", "metric": "test_files_per_source_file", "unit": "ratio", "higher_is_better": True,
     "minimal": 0.2, "optimal": 0.8, "world_class": None, "why": "untested modules have no signal to improve against"},
]
NODE_SOURCE_SUFFIXES = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")


def node_object(path: Path) -> dict[str, Any]:
    """Static facts for a Node package. Probing (running npm) is not implemented yet and stays unknown."""
    files = _walk(path)
    code = [f for f in files if f.suffix in NODE_SOURCE_SUFFIXES and "node_modules" not in f.parts]
    tests = [f for f in code if ".test." in f.name or ".spec." in f.name or "test" in f.relative_to(path).parts[:1]
             or "tests" in f.relative_to(path).parts[:1] or "__tests__" in f.parts]
    sources = [f for f in code if f not in tests]
    try:
        manifest = json.loads((path / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    scripts = manifest.get("scripts") if isinstance(manifest.get("scripts"), dict) else {}
    test_script = scripts.get("test", "")
    declared_test = bool(test_script) and "no test specified" not in test_script
    facts = {"files": len(files), "source_files": len(sources), "test_files": len(tests),
             "package_name": manifest.get("name"), "test_script": test_script or None,
             "typecheck_script": next((k for k in scripts if "type" in k.lower() or k == "tsc"), None),
             "lockfile": next((n for n in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock") if (path / n).exists()), None),
             "version_control": (path / ".git").exists(), "truncated_scan": len(files) >= MAX_FILES_SCANNED}
    ratio = (len(tests) / len(sources)) if sources else None
    objectives = []
    for template in NODE_OBJECTIVES:
        value = ratio if template["metric"] == "test_files_per_source_file" else None
        objectives.append(dict(template, status="proposed", value=round(value, 4) if value is not None else None,
                               band=band(value, template), evidence="observed" if value is not None else "unknown"))
    rungs = {"package_manifest": bool(manifest), "source_present": bool(sources), "tests_present": bool(tests),
             "test_script_declared": declared_test, "tests_pass": None, "lockfile_present": bool(facts["lockfile"]),
             "typecheck_declared": bool(facts["typecheck_script"])}
    ladder = [{"rung": name, "status": {True: "achieved", False: "not_achieved", None: "unknown"}[rungs[name]]}
              for name in NODE_LADDER]
    next_rung = next((r["rung"] for r in ladder if r["status"] != "achieved"), None)
    return {"kind": "node_repository", "facts": facts, "probe": None, "objectives": objectives, "ladder": ladder,
            "next_rung": next_rung}


DOCUMENT_LADDER = ["documents_present", "index_present", "links_resolve"]
DOCUMENT_OBJECTIVES = [
    {"id": "links_resolve", "metric": "internal_link_integrity", "unit": "resolving / internal Markdown links",
     "higher_is_better": True, "minimal": 0.9, "optimal": 1.0, "world_class": None,
     "why": "a broken internal link is a dead end for every reader, human or model"},
]
MAX_DOCUMENTS = 2000
DOCUMENT_SUFFIXES = (".md", ".markdown", ".rst", ".txt", ".adoc", ".org")
_FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
_INLINE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+\"[^\"]*\")?\s*$", re.M)
_EXTERNAL = ("http://", "https://", "mailto:", "ftp://", "data:", "tel:", "file:")
_LINE_SUFFIX = re.compile(r"^(.+?):\d+(?:[:-]\d+)?$")
_TODO = re.compile(r"\b(TODO|FIXME|XXX)\b")
# Raised whenever a map starts to record something new, so a map from an earlier version is known to be incomplete.
# 2: pages nothing links to, notes still to do, the index's real name (journey J4).
# 3: tests run with unittest when pytest is missing, and a probe that ran nothing is unknown (journey J2-B3).
MAPPER_REVISION = 4


def exists_exactly(path: Path, _listing: dict[str, set[str]] | None = None) -> bool:
    """Does ``path`` exist with exactly this spelling? On a case-insensitive disk, ``faq.md`` finds ``FAQ.md``,
    but the same link breaks on a web server or on Linux, so the case of every part must match."""
    path = Path(os.path.normpath(path))
    if not path.exists():
        return False
    cache = _listing if _listing is not None else {}
    parts = path.parts
    current = Path(parts[0])
    for part in parts[1:]:
        key = str(current)
        if key not in cache:
            try:
                cache[key] = set(os.listdir(current))
            except OSError:
                return True                      # cannot list (permissions): trust the file system's answer
        if part not in cache[key] and part not in (".", ".."):
            return False
        current = current / part
    return True


def _internal_targets(text: str) -> list[str]:
    text = _FENCE.sub("", text)                                   # code examples are not links
    targets = _INLINE.findall(text) + _REFERENCE.findall(text)
    return [t for t in targets if not t.lower().startswith(_EXTERNAL) and not t.startswith("#")]


def _index_name(path: Path) -> str | None:
    present = {p.name for p in path.iterdir()} if path.is_dir() else set()
    by_lower = {n.lower(): n for n in present}                   # the name as it is on disk, on any file system
    return next((by_lower[n.lower()] for n in ("README.md", "INDEX.md", "index.md", "readme.md", "README.rst",
                                               "README.txt", "README") if n.lower() in by_lower), None)


def _linked_pages(scope: Path) -> set[str]:
    """Every file that some Markdown page under ``scope`` links to (other than itself), as normalised paths."""
    from urllib.parse import unquote
    linked = set()
    for doc in [f for f in _walk(scope) if f.suffix.lower() in (".md", ".markdown")][:MAX_DOCUMENTS]:
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for target in _internal_targets(text):
            rel = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = ((scope / rel.lstrip("/")) if rel.startswith("/") else (doc.parent / rel)) if rel else None
            if resolved is not None and resolved.exists() and resolved.resolve() != doc.resolve():
                linked.add(os.path.normcase(str(resolved.resolve())))
    return linked


def document_object(path: Path, *, recursive: bool = True, scope: Path | None = None,
                    linked: set[str] | None = None) -> dict[str, Any]:
    """Static facts for a document collection: Markdown files, an index, and whether internal links resolve.

    Links are counted across ``scope`` (the whole mapped folder), so a page linked from another object's index is
    not an orphan. Nothing is executed or fetched. External links are not checked (that would contact the network).
    """
    from urllib.parse import unquote
    scope = scope or path
    linked = _linked_pages(scope) if linked is None else linked
    candidates = _walk(path) if recursive else sorted(p for p in path.iterdir() if p.is_file() and not is_link(p))
    texts = [f for f in candidates if f.suffix.lower() in DOCUMENT_SUFFIXES]
    documents = [f for f in candidates if f.suffix.lower() in (".md", ".markdown")][:MAX_DOCUMENTS]
    checked, broken, todos = 0, [], []
    listing: dict[str, set[str]] = {}
    for doc in texts[:MAX_DOCUMENTS]:
        if doc.suffix.lower() in (".md", ".markdown"):
            continue
        try:
            lines = doc.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        todos += [{"document": doc.relative_to(path).as_posix(), "line": n, "text": line.strip()[:100]}
                  for n, line in enumerate(lines, 1) if _TODO.search(line)]
    for doc in documents:
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        prose = _FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)     # a TODO in a code example is not a note
        todos += [{"document": doc.relative_to(path).as_posix(), "line": n, "text": line.strip()[:100]}
                  for n, line in enumerate(prose.splitlines(), 1) if _TODO.search(line)]
        for target in _internal_targets(text):
            rel = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not rel:
                continue
            resolved = (path / rel.lstrip("/")) if rel.startswith("/") else (doc.parent / rel)
            checked += 1
            line_ref = _LINE_SUFFIX.match(rel)                    # the `file.py:258` code-reference convention
            if not resolved.exists() and line_ref:
                base = line_ref.group(1)
                resolved = (path / base.lstrip("/")) if base.startswith("/") else (doc.parent / base)
            if not exists_exactly(resolved, listing):
                broken.append({"document": doc.relative_to(path).as_posix(), "target": target,
                               **({"case": True} if resolved.exists() else {})})
    integrity = ((checked - len(broken)) / checked) if checked else None
    index = _index_name(path)
    # Pages no other page links to: a reader following links never finds them. An index (this collection's or the
    # whole folder's) is the way in, so it counts as linked; a lone page cannot be an orphan.
    entries = {os.path.normcase(str((folder / name).resolve())) for folder in (path, scope)
               if (name := _index_name(folder))}
    orphans = [d.relative_to(path).as_posix() for d in documents
               if len(documents) + len(linked) > 1 and os.path.normcase(str(d.resolve())) not in linked | entries]
    facts = {"documents": len(texts), "markdown_files": len(documents), "internal_links": checked,
             "broken_links": len(broken), "broken_examples": broken[:10], "index": index, "recursive": recursive,
             "orphan_pages": len(orphans), "orphan_examples": orphans[:10],
             "todo_notes": len(todos), "todo_examples": todos[:10],
             "truncated_scan": len(documents) >= MAX_DOCUMENTS}
    objectives = [dict(t, status="proposed", value=round(integrity, 4) if integrity is not None else None,
                       band=band(integrity, t), evidence="observed" if integrity is not None else "unknown")
                  for t in DOCUMENT_OBJECTIVES]
    rungs = {"documents_present": bool(texts), "index_present": bool(index),
             "links_resolve": None if integrity is None else integrity >= 1.0}
    ladder = [{"rung": name, "status": {True: "achieved", False: "not_achieved", None: "unknown"}[rungs[name]]}
              for name in DOCUMENT_LADDER]
    next_rung = next((r["rung"] for r in ladder if r["status"] != "achieved"), None)
    return {"kind": "document_collection", "facts": facts, "probe": None, "objectives": objectives, "ladder": ladder,
            "next_rung": next_rung}


FOLDER_LADDER = ["contents_present", "readme_present", "version_control"]
README_NAMES = ("README.md", "README.rst", "README.txt", "README", "readme.md", "Readme.md", "INDEX.md", "index.md")


def _visible_files(path: Path, recursive: bool) -> list[Path]:
    return [p for p, _, _ in _visible_scan(path, recursive)]


def _visible_scan(path: Path, recursive: bool) -> list[tuple[Path, int, int]]:
    if recursive:
        return _scan(path)
    out = []
    for p in sorted(p for p in path.iterdir() if p.is_file() and not p.name.startswith(".") and not is_link(p)):
        try:
            st = p.stat()
            out.append((p, st.st_size, st.st_mtime_ns))
        except OSError:
            continue
    return out


def folder_facts(path: Path, *, recursive: bool = True) -> dict[str, Any]:
    """What any folder holds, whatever it is: file count, size, the kinds of files, a readme, version control."""
    scanned = _visible_scan(path, recursive)
    files = [f for f, _, _ in scanned]
    size = sum(s for _, s, _ in scanned)
    kinds = Counter(f.suffix.lower() or "(none)" for f in files)
    return {"files": len(files), "bytes": size, "top_extensions": kinds.most_common(8),
            "readme": next((n for n in README_NAMES if (path / n).is_file()), None),
            "version_control": (path / ".git").exists(), "recursive": recursive,
            "truncated_scan": len(files) >= MAX_FILES_SCANNED}


def folder_object(path: Path, *, recursive: bool = True) -> dict[str, Any]:
    """A folder Runesmith has no richer template for: mapped by its contents, with a small generic ladder."""
    facts = folder_facts(path, recursive=recursive)
    rungs = {"contents_present": facts["files"] > 0, "readme_present": bool(facts["readme"]),
             "version_control": facts["version_control"]}
    ladder = [{"rung": name, "status": "achieved" if rungs[name] else "not_achieved"} for name in FOLDER_LADDER]
    next_rung = next((r["rung"] for r in ladder if r["status"] != "achieved"), None)
    return {"kind": "folder", "facts": facts, "probe": None, "objectives": [], "ladder": ladder, "next_rung": next_rung}


def _natural(name: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def data_object(path: Path, *, recursive: bool = True) -> dict[str, Any]:
    """Report files the owner can watch a number in: how many, the newest (by name, as week-10 after week-9), and
    its columns, which a measurement names (journey J5-F2)."""
    facts = folder_facts(path, recursive=recursive)
    reports = sorted((f for f, _, _ in _visible_scan(path, recursive) if f.suffix.lower() in DATA_SUFFIXES),
                     key=lambda f: _natural(f.relative_to(path).as_posix()))
    newest = reports[-1] if reports else None
    columns: list[str] = []
    if newest is not None and newest.suffix.lower() in (".csv", ".tsv"):
        try:
            with open(newest, encoding="utf-8-sig", errors="replace", newline="") as handle:
                first = handle.readline()
            columns = [c.strip() for c in next(csv.reader([first], delimiter="\t" if newest.suffix.lower() == ".tsv" else ","), [])][:20]
        except (OSError, csv.Error):
            columns = []
    facts.update(report_files=len(reports), columns=columns,
                 newest_report=newest.relative_to(path).as_posix() if newest is not None else None)
    ladder = [{"rung": "reports_present", "status": "achieved" if reports else "not_achieved"}]
    return {"kind": "data_reports", "facts": facts, "probe": None, "objectives": [], "ladder": ladder,
            "next_rung": None}


def workspace_facts(workspace: Path, *, max_entries: int = 80) -> dict[str, Any]:
    """The workspace as a whole: its top-level entries and what it holds, so even an empty folder has a map."""
    entries = []
    for p in sorted(workspace.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if p.name.startswith("."):
            continue
        try:
            if is_link(p):
                entries.append({"name": p.name, "type": "link", "size": None})
                continue
            entries.append({"name": p.name, "type": "dir" if p.is_dir() else "file",
                            "size": None if p.is_dir() else p.stat().st_size})
        except OSError:
            continue
    facts = folder_facts(workspace)
    facts.update(entries=entries[:max_entries], entries_total=len(entries), empty=not entries,
                 directories=sum(1 for e in entries if e["type"] == "dir"),
                 loose_files=sum(1 for e in entries if e["type"] == "file"))
    return facts


WEBSITE_LADDER = ["pages_present", "index_present", "styles_present", "mobile_ready", "titles_present", "links_resolve"]
WEBSITE_OBJECTIVES = [
    {"id": "links_resolve", "metric": "internal_link_integrity", "unit": "resolving / internal href and src references",
     "higher_is_better": True, "minimal": 0.9, "optimal": 1.0, "world_class": None,
     "why": "a broken link or missing image is the first thing a visitor meets"},
    {"id": "mobile_ready", "metric": "pages_with_viewport", "unit": "pages with a mobile viewport tag / pages",
     "higher_is_better": True, "minimal": 0.5, "optimal": 1.0, "world_class": None,
     "why": "most visitors arrive on a phone"},
]
_REFS = re.compile(r"""(?:href|src)\s*=\s*["']([^"'#?]+)""", re.I)


def website_object(path: Path, *, recursive: bool = True) -> dict[str, Any]:
    """Static facts for a website: pages, styles, whether internal links and images resolve, phone readiness.

    Nothing is executed or fetched; external references are not checked.
    """
    from urllib.parse import unquote
    files = _walk(path) if recursive else sorted(p for p in path.iterdir() if p.is_file() and not is_link(p))
    pages = [f for f in files if f.suffix.lower() in (".html", ".htm")][:MAX_DOCUMENTS]
    styles = [f for f in files if f.suffix.lower() == ".css"]
    scripts = [f for f in files if f.suffix.lower() in (".js", ".mjs")]
    checked, broken, viewport, titled = 0, [], 0, 0
    listing: dict[str, set[str]] = {}
    for page in pages:
        try:
            html = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        low = html.lower()
        viewport += 'name="viewport"' in low or "name='viewport'" in low
        titled += bool(re.search(r"<title>\s*\S", low))
        for ref in _REFS.findall(html):
            ref = ref.strip()
            if not ref or ref.lower().startswith(_EXTERNAL + ("//", "javascript:")):
                continue
            rel = unquote(ref)
            target = (path / rel.lstrip("/")) if rel.startswith("/") else (page.parent / rel)
            checked += 1
            if not exists_exactly(target, listing):
                broken.append({"page": page.relative_to(path).as_posix(), "target": ref,
                               **({"case": True} if target.exists() else {})})
    integrity = ((checked - len(broken)) / checked) if checked else None
    ready = (viewport / len(pages)) if pages else None
    measured = {"internal_link_integrity": integrity, "pages_with_viewport": ready}
    objectives = [dict(t, status="proposed", value=round(measured[t["metric"]], 4) if measured[t["metric"]] is not None else None,
                       band=band(measured[t["metric"]], t),
                       evidence="observed" if measured[t["metric"]] is not None else "unknown") for t in WEBSITE_OBJECTIVES]
    index = next((n for n in ("index.html", "index.htm") if (path / n).is_file()), None)
    facts = {"pages": len(pages), "stylesheets": len(styles), "scripts": len(scripts), "index": index,
             "internal_references": checked, "broken_references": len(broken), "broken_examples": broken[:10],
             "pages_with_viewport": viewport, "pages_with_title": titled, "recursive": recursive}
    rungs = {"pages_present": bool(pages), "index_present": bool(index), "styles_present": bool(styles),
             "mobile_ready": bool(pages) and viewport == len(pages), "titles_present": bool(pages) and titled == len(pages),
             "links_resolve": None if integrity is None else integrity >= 1.0}
    ladder = [{"rung": name, "status": {True: "achieved", False: "not_achieved", None: "unknown"}[rungs[name]]}
              for name in WEBSITE_LADDER]
    next_rung = next((r["rung"] for r in ladder if r["status"] != "achieved"), None)
    return {"kind": "website", "facts": facts, "probe": None, "objectives": objectives, "ladder": ladder,
            "next_rung": next_rung}


def environment_facts() -> dict[str, Any]:
    usage = shutil.disk_usage(Path.cwd().anchor or "/")
    return {"os": platform.platform(), "python": sys.version.split()[0], "cpus": os.cpu_count(),
            "disk_free_gb": round(usage.free / 1e9, 1)}


def build_environment_map(workspace: Path, *, probe: bool = False, max_objects: int = 200,
                          scratch: Path | None = None, exclude: Iterable[str] = (),
                          previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map ``workspace``. Objects named in ``exclude`` are listed as excluded and never read or probed.

    Without ``probe``, a code object whose files are unchanged since a ``previous`` map measured it keeps that
    measurement, marked with the time it was taken; a changed object is unknown again until the next probe.
    """
    workspace = Path(workspace).resolve()
    exclude = set(exclude)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    earlier = {o.get("path"): o for o in (previous or {}).get("objects", [])}
    kept = 0
    root_kind = classify_object(workspace)
    loose = any(p.is_file() and not p.name.startswith(".") and not is_link(p) for p in workspace.iterdir())
    links = sorted(p for p in workspace.iterdir() if not p.name.startswith(".") and p.is_dir() and is_link(p))
    if root_kind in ("python_repository", "node_repository", "website"):
        candidates = [workspace]                      # the workspace is itself one object
    else:                                             # a container: each subdirectory is a candidate object
        candidates = []
        for p in sorted(p for p in workspace.iterdir()
                        if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".") and not is_link(p)):
            # A plain folder that holds projects (services/billing, apps/web) is mapped as those projects.
            nested = [] if p.name in exclude or classify_object(p) != "unknown" else [
                c for c in sorted(p.iterdir()) if c.is_dir() and c.name not in SKIP_DIRS and not c.name.startswith(".")
                and not is_link(c) and classify_object(c) in ("python_repository", "node_repository", "website")]
            candidates.extend(nested or [p])
        if root_kind == "document_collection" or loose:
            candidates.insert(0, workspace)           # its own loose files are an object too
    objects, unknowns, site_links = [], [], None
    for path in candidates[:max_objects]:
        name = path.name if path == workspace else path.relative_to(workspace).as_posix()
        if name in exclude or path.name in exclude:
            objects.append({"name": name, "path": str(path), "kind": "excluded", "objectives": [], "ladder": [],
                            "next_rung": None, "root": path == workspace})
            continue
        kind = classify_object(path)
        entry: dict[str, Any] = {"name": name, "path": str(path), "kind": kind, "root": path == workspace}
        if kind == "python_repository":
            measured = python_object(path, probe=probe, scratch=scratch)
            before = earlier.get(str(path)) or {}
            if probe:
                measured["measured_utc"] = now
            elif (before.get("kind") == kind and before.get("probe") and before.get("measured_utc")
                  and (before.get("facts") or {}).get("fingerprint") == measured["facts"]["fingerprint"]):
                measured = {k: before[k] for k in ("facts", "probe", "objectives", "ladder", "next_rung", "measured_utc")}
                kept += 1
            entry.update(measured)
        elif kind == "node_repository":
            entry.update(node_object(path))
            if probe:
                unknowns.append(f"{name}: Node probing (npm test) is not implemented; tests_pass stays unknown")
        elif kind == "document_collection":
            # The workspace root's own documents only; its subdirectories are mapped as objects of their own.
            if site_links is None:
                site_links = _linked_pages(workspace)             # once per map: links count across the whole folder
            entry.update(document_object(path, recursive=path != workspace, scope=workspace, linked=site_links))
            unknowns.append(f"{name}: external links are not checked (that would contact the network)")
        elif kind == "data_reports":
            entry.update(data_object(path, recursive=path != workspace))
        elif kind == "website":
            entry.update(website_object(path, recursive=path != workspace or root_kind == "website"))
            unknowns.append(f"{name}: external links and how the pages look are not checked")
        else:
            entry.update(folder_object(path, recursive=path != workspace))
            unknowns.append(f"{name}: a plain folder; mapped by its contents, no objective template yet")
        objects.append(entry)
    for p in links:                                   # shown, so nobody wonders where it went, but never followed
        objects.append({"name": p.name, "path": str(p), "kind": "excluded", "reason": "link", "objectives": [],
                        "ladder": [], "next_rung": None, "root": False})
        unknowns.append(f"{p.name}: a link to another place; Runesmith does not follow links out of the folder")
    if len(candidates) > max_objects:
        unknowns.append(f"only the first {max_objects} of {len(candidates)} directories were mapped")
    ws_facts = workspace_facts(workspace)
    capped = [o["name"] for o in objects if (o.get("facts") or {}).get("truncated_scan")]
    if ws_facts.get("truncated_scan"):
        capped.append("the folder as a whole")
    if capped:                                                         # a count that stopped is not the count
        unknowns.append(f"{MAX_FILES_SCANNED} files or more in {', '.join(capped)}: file counts and checks stop "
                        f"at {MAX_FILES_SCANNED}")
    if kept:
        unknowns.append(f"{kept} code object(s) keep the test measurements of an earlier map: their files have not "
                        "changed since (see measured_utc)")
    if not probe and any(o["kind"] == "python_repository" and not o.get("probe") for o in objects):
        unknowns.append("objects were not probed: pass rates, suite times and collect/pass rungs are unknown")
    body = {"schema": "runesmith.environment_map.v1", "mapper_revision": MAPPER_REVISION, "workspace": str(workspace),
            "environment": environment_facts(),
            "band_vocabulary": "bad < minimal <= value < optimal <= value < world_class; world_class needs external evidence",
            "workspace_facts": ws_facts, "objects": objects, "unknowns": unknowns}
    body["map_digest"] = digest({k: v for k, v in body.items() if k not in ("map_digest", "environment")})
    body["utc"] = now
    return body


def write_environment_map(path: Path, workspace: Path, **kwargs) -> dict[str, Any]:
    env_map = build_environment_map(workspace, **kwargs)
    Path(path).write_bytes((json.dumps(env_map, indent=1, default=str) + "\n").encode("utf-8"))
    return env_map
