"""The living map's builders (docs/MAP_LOGIC.md): facts only, each with its source and time.

Everything here reads files on disk, Runesmith's own records (ledger, state files, session records) or a recorded test
run. No model is asked, nothing is executed, and nothing is written. What the records do not say is ``unknown``.

The Studio serves these through ``/api/map/*`` next to the older fields; a builder that fails is caught there, and the
map shows the older view and says what it could not read (MAP_LOGIC.md, principle 6).
"""
from __future__ import annotations

import ast
import calendar
import math
import os
import posixpath
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from runesmith.envmap import _scan

# ----------------------------------------------------------------------------------------------- shared helpers --

NODE_CAP = 60                 # nodes drawn at most (a group beyond it shows "+N more"; the list view holds the rest)
LIST_CAP = 500                # nodes carried at all; a folder of 20,000 files is not a drawing, and says so
GROUP_CAP = 12                # folders drawn as groups; the smaller ones share one "other folders" group
PARSE_CAP = 2500              # code files whose imports are read; the rest are counted, never guessed
LINES_CAP = 4000              # files whose lines are counted
READ_CAP = 1_500_000          # bytes read from one file
TOP = ""                      # the group of files that sit at the top of the project


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def epoch(utc: str | None) -> float | None:
    """Seconds since 1970 of a ``2026-10-05T13:11:00Z`` stamp, or None when it is not one."""
    try:
        return float(calendar.timegm(time.strptime(str(utc), "%Y-%m-%dT%H:%M:%SZ")))
    except (ValueError, TypeError):
        return None


def stamp(seconds: float | None) -> str | None:
    return None if seconds is None else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def hhmm(utc: str | None) -> str:
    """``13:11Z`` for a stamp (the map shows times as the ledger keeps them: UTC)."""
    return f"{str(utc)[11:16]}Z" if utc and len(str(utc)) >= 16 else "an unknown time"


def when(utc: str | None) -> str:
    return f"{str(utc)[:10]} {hhmm(utc)}" if utc else "an unknown time"


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _read_json(path: Path, default: Any) -> Any:
    from runesmith.app.workspace import _read_json as read
    return read(path, default)


# ------------------------------------------------------------------------------------------------- the files --

CODE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".c", ".h", ".cc",
                 ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".sh", ".ps1", ".bat", ".cmd", ".lua", ".sql", ".html",
                 ".htm", ".css", ".scss", ".vue", ".svelte"}
JS_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")
DOC_SUFFIXES = {".md", ".markdown", ".rst", ".txt", ".adoc", ".org"}
CONFIG_SUFFIXES = {".toml", ".cfg", ".ini", ".json", ".yaml", ".yml", ".xml", ".lock", ".properties", ".env"}
CONFIG_NAMES = {"makefile", "dockerfile", "requirements.txt", "pipfile", "tox.ini", "package.json", "license", "notice"}
TEST_DIRS = {"tests", "test", "__tests__"}
LANGUAGE = {".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
            ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
            ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".hpp": "C++", ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
            ".swift": "Swift", ".sh": "shell", ".ps1": "PowerShell", ".bat": "batch", ".cmd": "batch", ".lua": "Lua",
            ".sql": "SQL", ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "CSS", ".vue": "Vue", ".svelte": "Svelte"}
KIND_WORDS = {"module": "source file", "test": "test file", "doc": "document", "config": "configuration file",
              "data": "data or other file"}


def classify(rel: str) -> str:
    """module, test, doc, config or data, from the file's name and place alone."""
    path = PurePosix(rel)
    name, suffix = path.name.lower(), path.suffix.lower()
    parts = [p.lower() for p in path.parts[:-1]]
    if suffix in CODE_SUFFIXES:
        stem = name[:-len(suffix)]
        if (stem.startswith("test_") or stem.endswith("_test") or stem == "conftest" or ".test" in name or ".spec" in name
                or any(p in TEST_DIRS for p in parts)):
            return "test"
        return "module"
    if name in CONFIG_NAMES or suffix in CONFIG_SUFFIXES or name.startswith("requirements"):
        return "config"
    if suffix in DOC_SUFFIXES:
        return "doc"
    return "data"


class PurePosix:
    """The little of ``PurePosixPath`` the map needs, on a string that is already a relative posix path."""

    def __init__(self, rel: str) -> None:
        self.parts = tuple(p for p in rel.split("/") if p)
        self.name = self.parts[-1] if self.parts else ""
        self.suffix = os.path.splitext(self.name)[1]


def named_test_target(rel: str) -> str | None:
    """The module a test file is named for: ``test_foo.py`` and ``foo_test.py`` and ``foo.test.js`` all say ``foo``."""
    name = rel.rsplit("/", 1)[-1]
    stem = os.path.splitext(name)[0]
    for marker in (".test", ".spec"):
        if stem.lower().endswith(marker):
            stem = stem[:-len(marker)]
            break
    low = stem.lower()
    if low.startswith("test_") and len(stem) > 5:
        return stem[5:]
    if low.endswith("_test") and len(stem) > 5:
        return stem[:-5]
    if stem != os.path.splitext(name)[0]:
        return stem
    return None


# per file: lines and the imports it makes, kept while the file's size and time stay the same
_FILE_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}

_JS_IMPORT = re.compile(r"""(?:^|[\s;])(?:import|export)\s+(?:[^'"`;]*?\s+from\s+)?['"]([^'"\n]+)['"]""")
_JS_REQUIRE = re.compile(r"""\brequire\(\s*['"]([^'"\n]+)['"]\s*\)""")
_JS_DYNAMIC = re.compile(r"""\bimport\(\s*['"]([^'"\n]+)['"]\s*\)""")


def _py_imports(text: str) -> list[tuple[str, str, list[str], int, int]]:
    """(``import`` | ``from``, module, names, relative level, line) of every import statement, by Python's own parser."""
    tree = ast.parse(text)
    rows = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            rows += [("import", a.name, [], 0, node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            rows.append(("from", node.module or "", [a.name for a in node.names], node.level or 0, node.lineno))
    return sorted(rows, key=lambda r: (r[4], r[1]))


def _js_specs(text: str) -> list[tuple[str, int]]:
    found: dict[tuple[str, int], None] = {}
    for pattern in (_JS_IMPORT, _JS_REQUIRE, _JS_DYNAMIC):
        for m in pattern.finditer(text):
            found[(m.group(1), text.count("\n", 0, m.start(1)) + 1)] = None
    return sorted(found, key=lambda r: (r[1], r[0]))


def _file_facts(path: Path, rel: str, size: int, mtime_ns: int, *, count_lines: bool, parse: bool) -> dict[str, Any]:
    key = (str(path), size, mtime_ns)
    known = _FILE_CACHE.get(key)
    if known and (known["parsed"] or not parse) and (known["counted"] or not count_lines):
        return known
    out: dict[str, Any] = {"lines": None, "py": None, "js": None, "parsed": False, "counted": False, "parse_error": None}
    suffix = os.path.splitext(rel)[1].lower()
    textual = suffix in CODE_SUFFIXES or suffix in DOC_SUFFIXES or suffix in CONFIG_SUFFIXES or suffix in (".csv", ".tsv")
    if (count_lines or parse) and textual and size <= READ_CAP:
        try:
            data = path.read_bytes()
        except OSError:
            data = None
        if data is not None:
            if count_lines:
                out["lines"] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
                out["counted"] = True
            if parse and suffix == ".py":
                try:
                    out["py"] = _py_imports(data.decode("utf-8-sig", "replace"))
                except (SyntaxError, ValueError, RecursionError, MemoryError) as error:
                    out["parse_error"] = type(error).__name__
                out["parsed"] = True
            elif parse and suffix in JS_SUFFIXES:
                out["js"] = _js_specs(data.decode("utf-8-sig", "replace"))
                out["parsed"] = True
    elif count_lines or parse:
        out["counted"] = out["parsed"] = True
    if len(_FILE_CACHE) > 60_000:
        _FILE_CACHE.clear()
    _FILE_CACHE[key] = out
    return out


# --------------------------------------------------------------------------------------------- import edges --

def _python_index(py_files: list[str]) -> dict[str, str]:
    """Dotted module name -> file, for the ways the project's own code names its files: from the top of the project, from
    ``src``, and (inside a package) from the folder above the package. The first file in sorted order wins a clash, so
    it never depends on the order the disk listed things in."""
    have = set(py_files)
    index: dict[str, str] = {}
    for rel in sorted(py_files):
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        top, in_package = folder, False
        while top and f"{top}/__init__.py" in have:             # climb to the folder above the outermost package
            top, in_package = (top.rsplit("/", 1)[0] if "/" in top else ""), True
        bases = ["", "src" if rel.startswith("src/") else None, top if in_package else None]
        for base in dict.fromkeys(b for b in bases if b is not None):
            if base and not rel.startswith(base + "/"):
                continue
            inside = rel[len(base) + 1:] if base else rel
            dotted = inside[:-3].replace("/", ".")
            if dotted == "__init__":
                continue
            if dotted.endswith(".__init__"):
                dotted = dotted[:-9]
            index.setdefault(dotted, rel)
    return index


def _own_names(index: dict[str, str]) -> dict[str, str]:
    """File -> the shortest dotted name it answers to (what a relative import counts from)."""
    own: dict[str, str] = {}
    for dotted, rel in sorted(index.items()):
        if rel not in own or len(dotted.split(".")) < len(own[rel].split(".")):
            own[rel] = dotted
    return own


def _package_of(rel: str, own: dict[str, str]) -> str:
    dotted = own.get(rel, "")
    if rel.endswith("/__init__.py") or rel == "__init__.py":
        return dotted
    return dotted.rsplit(".", 1)[0] if "." in dotted else ""


def _locate(dotted: str, folder: str, index: dict[str, str], have: set[str]) -> str | None:
    """The project file a dotted name means: by the project's own names, else next to the file that imports it (how a
    script imports its neighbour when no package says otherwise)."""
    if dotted in index:
        return index[dotted]
    path = (folder + "/" if folder else "") + dotted.replace(".", "/")
    for candidate in (path + ".py", path + "/__init__.py"):
        if candidate in have:
            return candidate
    return None


def _resolve_python(rel: str, rows: list[tuple[str, str, list[str], int, int]], index: dict[str, str],
                    own: dict[str, str], have: set[str]) -> list[tuple[str, int, str]]:
    """(target file, line, how it was found) for each project file a Python file imports."""
    out: list[tuple[str, int, str]] = []
    package = _package_of(rel, own)
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    for kind, module, names, level, line in rows:
        if level:
            parts = package.split(".") if package else []
            if level - 1 > len(parts):
                continue
            base = ".".join(parts[:len(parts) - (level - 1)] + ([module] if module else []))
            text = f"from {'.' * level}{module} import {', '.join(names[:3])}"
        else:
            base = module
            text = f"import {module}" if kind == "import" else f"from {module} import {', '.join(names[:3])}"
        if len(names) > 3:
            text += ", …"
        how = f"python ast: {text} (line {line})"
        if kind == "import" and not level:
            parts = base.split(".")
            for n in range(len(parts), 0, -1):                  # the longest name that is a project file
                target = _locate(".".join(parts[:n]), folder, index, have)
                if target:
                    out.append((target, line, how))
                    break
            continue
        target = _locate(base, folder, index, have) if base else None
        if target:
            out.append((target, line, how))
        for name in names:
            sub = _locate(f"{base}.{name}" if base else name, "" if level else folder, index, have)
            if sub:
                out.append((sub, line, how))
    return out


def _resolve_js(rel: str, specs: list[tuple[str, int]], have: set[str]) -> list[tuple[str, int, str]]:
    out = []
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    for spec, line in specs:
        if not spec.startswith("."):
            continue                                            # a package or an alias: not a file of this project
        base = posixpath.normpath(posixpath.join(folder, spec))
        if base.startswith(".."):
            continue
        tries = [base] + [base + s for s in JS_SUFFIXES] + [base + "/index" + s for s in JS_SUFFIXES]
        if base.endswith(".js"):
            tries += [base[:-3] + ".ts", base[:-3] + ".tsx"]
        target = next((t for t in tries if t in have), None)
        if target:
            out.append((target, line, f"javascript import, found by pattern, not by a parser: '{spec}' (line {line})"))
    return out


# ---------------------------------------------------------------------------------------- test-run evidence --

SOURCE_WORDS = {"probe": "by the map's test probe", "round": "during a repair round",
                "measure": "while measuring with Python's own unittest, in a repair round"}


def _node_ids_to_files(ids: list[str], test_files: list[str], dotted: dict[str, str]) -> dict[str, list[str]]:
    """Failing test ids -> {test file: its failing ids}. A pytest id names its file (``tests/test_a.py::Case::test_x``); a
    unittest id names a module (``tests.test_a.Case.test_x``). An id that names no file of this project is dropped, never
    guessed at."""
    have = set(test_files)
    out: dict[str, list[str]] = defaultdict(list)
    for raw in ids:
        text = str(raw or "").strip().replace("\\", "/")
        if "::" in text:
            file = text.split("::", 1)[0]
            match = file if file in have else next((t for t in sorted(have) if t.endswith("/" + file)), None)
        else:
            parts = re.split(r"[.\s(]", text.split(" ")[0])
            parts = [p for p in parts if p]
            match = None
            for n in range(len(parts), 0, -1):
                match = dotted.get(".".join(parts[:n]))
                if match in have:
                    break
                match = None
        if match:
            out[match].append(str(raw)[:160])
    return dict(out)


def latest_run(ws, obj: dict[str, Any], *, work: dict[str, Any] | None = None, env_map: dict[str, Any] | None = None,
               statuses: dict[str, str] | None = None) -> dict[str, Any] | None:
    """The latest recorded test run of a code object, whatever ran it, or None when no run is recorded.

    It follows the same precedence as ``Workspace.object_statuses`` (a probe newer than the round, a fix applied after
    it), so the node, the ring and the ladder cannot disagree. A run is one of:

    * the map's probe (``ENVIRONMENT.json``): pytest runs the whole suite; the unittest fallback is a subset. It records
      counts, never which files failed.
    * a repair round's discovery run (``WORK.json``), always pytest and the whole suite. ``utc`` is when the round
      finished. The round keeps the failing test files it *served* (a file served in an earlier round is not listed
      again), so a failing run names some failing files and says nothing about the others.
    * a repair round's measurement with Python's own unittest (``fix-tests/MEASURED.json``): a subset; it names the
      failing tests.
    """
    if obj.get("kind") != "python_repository":
        return None
    name = obj["name"]
    work = work if work is not None else _read_json(ws.home / "WORK.json", {})
    env_map = env_map if env_map is not None else (ws.environment_map() or {})
    statuses = statuses if statuses is not None else ws.object_statuses(work, env_map)
    status = statuses.get(name)
    if not status:
        return None
    probe, measured_utc = obj.get("probe") or {}, obj.get("measured_utc") or ""
    round_utc = work.get("utc") or ""
    run: dict[str, Any] = {"status": status, "scope": "unknown", "outcome": "unknown", "failing": {}, "attributed": False,
                           "counts": None, "detail": None, "superseded": None}

    def from_probe() -> None:
        runner = probe.get("runner")
        run.update(source="probe", utc=measured_utc, scope="subset" if runner == "unittest" else "whole",
                   runner=runner or "pytest")
        if "exit_code" in probe and not probe.get("error") and not probe.get("unavailable"):
            run["outcome"] = "passed" if probe["exit_code"] == 0 else "failed"
            run["counts"] = {k: probe.get(k) for k in ("collected", "passed", "failed", "errors") if probe.get(k) is not None}
        else:
            run["detail"] = probe.get("error") or probe.get("unavailable")

    if status == "fix_applied":
        # The fix changed files after the run; the underlying record is the round's. Nothing is known of the files now.
        run.update(source="round", utc=round_utc, scope="whole", runner="pytest", outcome="unknown",
                   superseded="a fix was applied after this run; measure the tests again to confirm")
        run["underlying"] = (work.get("objects") or {}).get(name)
        return run
    probe_terminal = "exit_code" in probe or probe.get("error") or probe.get("unavailable")
    if probe_terminal and measured_utc and measured_utc >= round_utc and status in (
            "green", "failing", "unittest_passed", "timed_out", "error_without_failures", "probe_unavailable"):
        from_probe()
        return run
    if status.startswith("measured:") or status.startswith("not measured"):
        record = _read_json(ws.home / "fix-tests" / "MEASURED.json", {}).get(obj.get("path"))
        if status.startswith("not measured") or not isinstance(record, dict):
            return None
        run.update(source="measure", utc=record.get("utc") or round_utc, scope="subset", runner="unittest",
                   outcome="failed" if (record.get("failures", 0) or 0) + (record.get("errors", 0) or 0) else
                   ("passed" if record.get("ran") else "unknown"),
                   counts={"ran": record.get("ran"), "failures": record.get("failures"), "errors": record.get("errors")},
                   named_ids=list(record.get("failing") or []))
        return run
    run.update(source="round", utc=round_utc, scope="whole", runner="pytest")
    if status == "green":
        run["outcome"] = "passed"
    elif status == "failing":
        run["outcome"] = "failed"
        run["named_ids"] = [t for o in work.get("opportunities") or [] if o.get("object") == name
                            for t in o.get("failing_tests") or []]
    elif status == "unittest_passed":
        run.update(scope="subset", outcome="passed", runner="unittest")
    else:                                                       # timed_out, error_without_failures, anything else
        run["detail"] = ((work.get("details") or {}).get(name) or {}).get("detail")
    return run


def run_words(run: dict[str, Any]) -> str:
    """``latest test run 13:11Z, during a repair round`` (the station and the detail panel say it the same way)."""
    return f"latest test run {hhmm(run.get('utc'))}, {SOURCE_WORDS.get(run.get('source'), 'by an unknown source')}"


def run_phrase(run: dict[str, Any]) -> str:
    """``the latest test run (13:11Z, during a repair round)``, for the middle of a sentence."""
    return f"the latest test run ({hhmm(run.get('utc'))}, {SOURCE_WORDS.get(run.get('source'), 'by an unknown source')})"


def run_outcome_words(run: dict[str, Any]) -> str:
    out, scope = run.get("outcome"), run.get("scope")
    if run.get("superseded"):
        return run["superseded"]
    if out == "passed":
        return "every test passed" if scope == "whole" else "the tests it ran passed (a unittest subset, not the whole suite)"
    if out == "failed":
        c = run.get("counts") or {}
        n = (c.get("failed") or 0) + (c.get("errors") or 0) or (c.get("failures") or 0) + (c.get("errors") or 0)
        of = c.get("collected") or c.get("ran")
        return f"{n} of {of} tests failed" if n and of else (f"{n} tests failed" if n else "tests failed")
    return run.get("detail") or "the run did not establish a result"


def ladder_overlay(ws, obj: dict[str, Any], *, run: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any] | None:
    """The three test rungs of a code object's ladder from its latest recorded run: ``{rung: {status, source, utc,
    note}}`` for tests_collect, tests_pass and fast_suite; None when no run is recorded (the map's own ladder stays)."""
    run = run if run is not None else latest_run(ws, obj, **kw)
    if run is None:
        return None
    words = run_words(run)
    base = {"source": run.get("source"), "utc": run.get("utc"), "source_words": words}
    whole = run.get("scope") == "whole"
    superseded = run.get("superseded")
    out = outcome = run.get("outcome")
    collect = "unknown"
    if not superseded and whole and out in ("passed", "failed"):
        collect = "achieved"                                    # a whole-suite run that ran tests collected them
    elif not superseded and run.get("source") == "measure" and ((run.get("counts") or {}).get("ran") or 0) > 0:
        # A repair round that measured with Python's own unittest is Runesmith's own runner for a project its organ cannot
        # serve (no pytest, or no src folder): it found and ran tests. That shows they are found; it is a subset, so
        # "tests pass" below still never reads achieved from it.
        collect = "achieved"
    if run.get("source") == "probe" and whole and "collected" in (run.get("counts") or {}) and not run["counts"]["collected"]:
        collect = "not_achieved"
    pass_ = "unknown"
    if not superseded and out == "failed":
        pass_ = "not_achieved"                                  # a failed test is a failed suite, subset or not
    elif not superseded and out == "passed" and whole:
        pass_ = "achieved"
    ran_note = (f"{words}: unittest found and ran {(run.get('counts') or {}).get('ran')} tests, so tests are found; as a subset it "
                "does not show that every test file collects.")
    notes = {"tests_collect": {"achieved": f"{words}: it ran tests, so they collect." if whole else ran_note,
                               "not_achieved": f"{words}: no tests were collected.",
                               "unknown": f"{words}: {run_outcome_words(run)}; that does not show the tests collect."},
             "tests_pass": {"achieved": f"{words}: {run_outcome_words(run)}.",
                            "not_achieved": f"{words}: {run_outcome_words(run)}.",
                            "unknown": f"{words}: {run_outcome_words(run)}; that does not show every test passes."}}
    rungs = {"tests_collect": dict(base, status=collect, note=notes["tests_collect"][collect]),
             "tests_pass": dict(base, status=pass_, note=notes["tests_pass"][pass_])}
    if run.get("source") == "probe":                            # only a probe times the suite
        rungs["fast_suite"] = None
    else:
        rungs["fast_suite"] = dict(base, status="unknown", note=f"{words}: the run did not time the suite, so its speed is unknown.")
    return rungs


# --------------------------------------------------------------------------------------------- the structure --

def _object_entry(ws, name: str | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    env_map = ws.environment_map() or {}
    objects = [o for o in env_map.get("objects", []) if o.get("kind") != "excluded"]
    if name:
        found = next((o for o in env_map.get("objects", []) if o["name"] == name), None)
    else:
        found = objects[0] if len(objects) == 1 else None
    return found, env_map


def _recursive(obj: dict[str, Any]) -> bool:
    """Whether the object holds its subfolders, as the mapper reads it: a workspace that is a container reads only its own
    loose files (its subfolders are objects of their own)."""
    return (not obj.get("root")) or obj.get("kind") in ("python_repository", "node_repository", "website")


def _group_of(rel: str, direct: dict[str, int]) -> str:
    """The folder a file is drawn in: its own, or the nearest one above it that holds more than one file."""
    folder = rel.rsplit("/", 1)[0] if "/" in rel else TOP
    while folder:
        if direct.get(folder, 0) > 1:
            return folder
        folder = folder.rsplit("/", 1)[0] if "/" in folder else TOP
    return TOP


def structure_view(ws, name: str | None = None, expand: tuple[str, ...] = ()) -> dict[str, Any]:
    """The structure graph of one mapped object (docs/MAP_LOGIC.md section 1)."""
    obj, env_map = _object_entry(ws, name)
    if obj is None:
        raise KeyError(name or "no single object")
    base = {"schema": "runesmith.map.structure.v1", "object": {k: obj.get(k) for k in ("name", "path", "kind", "root")},
            "built_utc": _now(), "nodes": [], "edges": [], "groups": [], "list_cap": LIST_CAP, "run": None}
    if obj.get("kind") == "excluded":
        return dict(base, empty=True, sentence=f"{obj['name']} is on your never-touch list, so Runesmith has not read it.")
    root = Path(obj["path"])
    if not root.is_dir():
        return dict(base, empty=True, sentence="This folder is not on disk now. Map again to refresh.")
    scanned = [(p, s, m) for p, s, m in _scan(root) if not p.name.startswith(".")]
    if not _recursive(obj):
        scanned = [(p, s, m) for p, s, m in scanned if p.parent == root]
    scanned.sort(key=lambda row: row[0].relative_to(root).as_posix())
    truncated = len(scanned) >= 20_000
    rels = [p.relative_to(root).as_posix() for p, _, _ in scanned]
    if not rels:
        return dict(base, empty=True, truncated_scan=False, counts={"files": 0},
                    sentence="There are no files here yet. When there are, they appear around the folder, each with what is "
                             "known about it.")
    kinds = {rel: classify(rel) for rel in rels}
    info = {rel: (size, mtime) for rel, (_, size, mtime) in zip(rels, scanned)}
    code_rels = [r for r in rels if os.path.splitext(r)[1].lower() in CODE_SUFFIXES]
    parse_set = set([r for r in code_rels if os.path.splitext(r)[1].lower() == ".py" or os.path.splitext(r)[1].lower() in JS_SUFFIXES][:PARSE_CAP])
    facts: dict[str, dict[str, Any]] = {}
    for index, (path, size, mtime) in enumerate(scanned):
        rel = rels[index]
        facts[rel] = _file_facts(path, rel, size, mtime, count_lines=index < LINES_CAP, parse=rel in parse_set)
    py_files = [r for r in rels if r.endswith(".py")]
    pindex = _python_index(py_files)
    own_name = _own_names(pindex)
    have = set(rels)
    found: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_edge(src: str, dst: str, etype: str, how: str) -> None:
        if src == dst:
            return
        edge = found.setdefault((src, dst, etype), {"from": src, "to": dst, "type": etype, "how": []})
        if how not in edge["how"] and len(edge["how"]) < 3:
            edge["how"].append(how)

    for rel in rels:
        rows = facts[rel]
        links = []
        if rows["py"]:
            links = _resolve_python(rel, rows["py"], pindex, own_name, have)
        elif rows["js"]:
            links = _resolve_js(rel, rows["js"], have)
        for target, _line, how in links:
            if kinds.get(target) not in ("module", "test"):
                continue
            if kinds[rel] == "test" and kinds[target] == "module":
                add_edge(rel, target, "tests", how.replace("python ast:", "the test imports it, python ast:")
                         if how.startswith("python ast:") else "the test imports it; " + how)
            elif kinds[rel] == "test" or kinds[rel] == "module":
                add_edge(rel, target, "imports", how)
    stems: dict[str, list[str]] = defaultdict(list)
    for rel in rels:
        if kinds[rel] == "module":
            stem = os.path.splitext(rel.rsplit("/", 1)[-1])[0]
            stems[stem.lower()].append(rel)
    for rel in rels:
        if kinds[rel] == "test":
            wanted = named_test_target(rel)
            for target in stems.get(wanted.lower(), []) if wanted else []:
                if target not in ("__init__.py",):
                    add_edge(rel, target, "tests", f"named for it: {rel.rsplit('/', 1)[-1]} says {target.rsplit('/', 1)[-1]}")
    edges = sorted(found.values(), key=lambda e: (e["type"], e["from"], e["to"]))
    imports_of: dict[str, list[str]] = defaultdict(list)
    imported_by: dict[str, list[str]] = defaultdict(list)
    reaches: dict[str, list[str]] = defaultdict(list)           # module -> tests that reach it
    reached: dict[str, list[str]] = defaultdict(list)           # test -> modules it reaches
    for e in edges:
        if e["type"] == "imports":
            imports_of[e["from"]].append(e["to"])
            imported_by[e["to"]].append(e["from"])
        else:
            reaches[e["to"]].append(e["from"])
            reached[e["from"]].append(e["to"])

    run = latest_run(ws, obj, env_map=env_map) if obj.get("kind") == "python_repository" else None
    test_files = [r for r in rels if kinds[r] == "test"]
    dotted_tests = {}
    for dotted, rel in pindex.items():
        if rel in set(test_files):
            dotted_tests.setdefault(dotted, rel)
    if run and run.get("named_ids"):
        run["failing"] = _node_ids_to_files(run["named_ids"], test_files, dotted_tests)
    run_epoch = epoch(run.get("utc")) if run else None
    work_badges = file_badges(ws, root)
    ledger_changes = last_changes(ws, root)
    direct: dict[str, int] = defaultdict(int)
    for rel in rels:
        direct[rel.rsplit("/", 1)[0] if "/" in rel else TOP] += 1

    def mtime_utc(rel: str) -> str:
        return stamp(info[rel][1] / 1e9) or ""

    def stale(rel: str) -> bool:
        return run_epoch is not None and info[rel][1] / 1e9 > run_epoch + 1

    nodes: list[dict[str, Any]] = []
    for rel in rels:
        kind = kinds[rel]
        size, mtime = info[rel]
        f = facts[rel]
        node: dict[str, Any] = {"id": rel, "name": rel.rsplit("/", 1)[-1], "kind": kind, "group": _group_of(rel, direct),
                                "lines": f["lines"], "bytes": size, "mtime_utc": mtime_utc(rel),
                                "language": LANGUAGE.get(os.path.splitext(rel)[1].lower()),
                                "badges": work_badges.get(rel, [])}
        change = ledger_changes.get(rel)
        if change:                                                # Runesmith's own record: what it changed here, and when
            node["badges"] = node["badges"] + [{"kind": "changed", "text": f"last changed by Runesmith, {when(change['utc'])}",
                                                "source": change["source"]}]
        node["state"] = _state(rel, kind, run, reaches.get(rel, []), info, stale, obj)
        if kind == "test":
            node["test"] = _test_result(rel, run, stale, run_epoch)
            node["state"] = _test_state(node["test"])
            if node["test"].get("failing"):
                node["badges"] = node["badges"] + [{"kind": "failing", "text": plural(len(node["test"]["failing"]), "failing test"),
                                                     "source": f"{run_words(run)}"}]
        node["evidence"] = _evidence(ws, node, f, imports_of, imported_by, reaches, reached, run, ledger_changes, obj, scanned_at=base["built_utc"])
        nodes.append(node)
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:                                             # what the detail panel lists, as names with their results
        n["imports"] = sorted(imports_of.get(n["id"], []))
        n["imported_by"] = sorted(imported_by.get(n["id"], []))
        if n["kind"] == "module":
            n["tests"] = [{"id": t, "result": by_id[t]["test"]["words"], "band": by_id[t]["state"]["band"]}
                          for t in sorted(reaches.get(n["id"], [])) if t in by_id]
        if n["kind"] == "test":
            n["reaches"] = sorted(reached.get(n["id"], []))

    drawn_ids, groups = _select_drawn(nodes, expand)
    for n in nodes:
        n["drawn"] = n["id"] in drawn_ids
    listed = nodes[:LIST_CAP]
    listed_ids = {n["id"] for n in listed}
    counts = {"files": len(rels), "modules": sum(1 for r in rels if kinds[r] == "module"), "tests": len(test_files),
              "docs": sum(1 for r in rels if kinds[r] == "doc"), "config": sum(1 for r in rels if kinds[r] == "config"),
              "data": sum(1 for r in rels if kinds[r] == "data"), "edges": len(edges),
              "drawn": sum(1 for n in listed if n["drawn"]), "listed": len(listed)}
    languages = sorted({n["language"] for n in nodes if n["language"]})
    unread = sum(1 for r in code_rels if os.path.splitext(r)[1].lower() in (".py",) + JS_SUFFIXES and r not in parse_set)
    base.update(
        empty=False, counts=counts, truncated_scan=truncated, imports_not_read=unread, languages=languages,
        sentence=_sentence(obj, counts, languages, edges),
        groups=groups, nodes=listed, edges=[e for e in edges if e["from"] in listed_ids and e["to"] in listed_ids],
        run=_run_summary(run, obj), parse_errors=sorted(r for r in rels if facts[r].get("parse_error")))
    return base


def _sentence(obj: dict[str, Any], counts: dict[str, int], languages: list[str], edges: list[dict[str, Any]]) -> str:
    parts = [plural(counts["files"], "file")]
    kinds = [(counts["modules"], "source file"), (counts["tests"], "test file"), (counts["docs"], "document"),
             (counts["config"], "configuration file"), (counts["data"], "other file")]
    shown = [plural(n, one) for n, one in kinds if n]
    text = f"{parts[0]}: {', '.join(shown)}."
    if edges:
        text += f" {plural(len(edges), 'link')} between them were found in the code itself."
    elif counts["modules"] + counts["tests"]:
        text += (" No links between them were found: Runesmith reads imports in Python and in JavaScript or TypeScript, "
                 "and nothing for other languages.")
    else:
        text += " There is no code to link, so there are no edges."
    return text


def _run_summary(run: dict[str, Any] | None, obj: dict[str, Any]) -> dict[str, Any] | None:
    if run is None:
        if obj.get("kind") == "python_repository":
            return {"recorded": False, "words": "No test run is recorded for this project, so no part can show a test result."}
        if obj.get("kind") == "node_repository":
            return {"recorded": False, "words": "Runesmith does not run npm test, so no test run is recorded for this project."}
        return None
    return {"recorded": True, "source": run.get("source"), "utc": run.get("utc"), "scope": run.get("scope"),
            "outcome": run.get("outcome"), "status": run.get("status"), "superseded": run.get("superseded"), "words": f"{run_words(run)}: {run_outcome_words(run)}",
            "attributed": sorted((run.get("failing") or {}).keys())}


def _state(rel: str, kind: str, run: dict[str, Any] | None, reaching: list[str], info: dict[str, tuple[int, int]], stale,
           obj: dict[str, Any]) -> dict[str, Any]:
    """A node's band, and why. Bad, Optimal, Minimal and Unknown only: nothing here earns World-class."""
    if kind != "module":
        return {"band": "unknown", "reason": ("Not measured: tests are about code, and nothing is recorded for a "
                                              f"{KIND_WORDS.get(kind, 'file')}."),
                "source": "file name and place, read from disk"}
    if not reaching:
        return {"band": "minimal", "reason": "No test file imports this module or is named for it, so nothing here tests it.",
                "source": "imports and file names, read from disk"}
    if obj.get("kind") != "python_repository":
        return {"band": "unknown", "reason": "Runesmith does not run this kind of project's tests, so no result is recorded.",
                "source": "no test run is recorded for this kind of project"}
    if run is None:
        return {"band": "unknown", "reason": "No test run is recorded for this project.", "source": "no recorded run"}
    where, ph = run_words(run), run_phrase(run)
    changed = [r for r in [rel] + sorted(reaching) if stale(r)]
    if changed:
        return {"band": "unknown", "source": where,
                "reason": f"Changed since the last test run: {changed[0]} changed at {hhmm(stamp(info[changed[0]][1] / 1e9))}, "
                          f"after {ph}."}
    if run.get("superseded"):
        return {"band": "unknown", "reason": run["superseded"].capitalize() + ".", "source": where}
    failing = [t for t in sorted(reaching) if t in (run.get("failing") or {})]
    if failing:
        ids = run["failing"][failing[0]]
        return {"band": "bad", "source": where,
                "reason": f"{failing[0]} failed in {ph}; {plural(len(ids), 'test')} named: {', '.join(ids[:2])}"
                          f"{', …' if len(ids) > 2 else ''}. It reaches this module."}
    if run.get("outcome") == "passed" and run.get("scope") == "whole":
        return {"band": "optimal", "source": where,
                "reason": f"{plural(len(reaching), 'test file')} {'reaches' if len(reaching) == 1 else 'reach'} it, and every test passed in {ph}."}
    if run.get("outcome") == "passed":
        return {"band": "unknown", "source": where,
                "reason": f"{ph[0].upper() + ph[1:]} was a unittest subset, which cannot show that every test that reaches this module passed."}
    if run.get("outcome") == "failed":
        c = run.get("counts") or {}
        n = (c.get("failed") or 0) + (c.get("errors") or 0) or (c.get("failures") or 0) + (c.get("errors") or 0)
        named = sorted(run.get("failing") or {})
        return {"band": "unknown", "source": where,
                "reason": f"In {ph}, {plural(n, 'test') + ' failed' if n else 'some tests failed'}, "
                          + (f"naming {', '.join(named[:2])}{', …' if len(named) > 2 else ''} and not the other test files' results"
                             if named else "but did not record which test files failed")
                          + ", so it cannot say whether the tests that reach this module passed."}
    return {"band": "unknown", "source": where, "reason": f"{ph[0].upper() + ph[1:]} did not establish a result: {run_outcome_words(run)}."}


def _test_result(rel: str, run: dict[str, Any] | None, stale, run_epoch: float | None) -> dict[str, Any]:
    if run is None:
        return {"result": "not_run", "words": "not run: no test run is recorded", "failing": []}
    where, ph = run_words(run), run_phrase(run)
    if stale(rel):
        return {"result": "unknown", "words": "changed since the last test run", "failing": [], "source": where}
    if run.get("superseded"):
        return {"result": "unknown", "words": "unknown: a fix was applied after the last run", "failing": [], "source": where}
    failing = (run.get("failing") or {}).get(rel) or []
    if failing:
        return {"result": "failed", "words": f"failed: {plural(len(failing), 'failing test')} named in {ph}",
                "failing": failing, "source": where}
    if run.get("outcome") == "passed" and run.get("scope") == "whole":
        return {"result": "passed", "words": f"passed in {ph}", "failing": [], "source": where}
    if run.get("outcome") == "passed":
        return {"result": "unknown", "words": "no result of its own: the last run was a unittest subset", "failing": [], "source": where}
    return {"result": "unknown", "words": "no result of its own is recorded in " + ph, "failing": [], "source": where}


def _test_state(test: dict[str, Any]) -> dict[str, Any]:
    band = {"failed": "bad", "passed": "optimal"}.get(test["result"], "unknown")
    return {"band": band, "reason": test["words"][:1].upper() + test["words"][1:] + ".", "source": test.get("source") or "no recorded run"}


def _select_drawn(nodes: list[dict[str, Any]], expand: tuple[str, ...]) -> tuple[set[str], list[dict[str, Any]]]:
    """Which nodes are drawn: all of them up to NODE_CAP; beyond it, the ones that matter most in each folder (a failing
    test, work waiting, then the largest), and one "+N more" per folder. A folder in ``expand`` shows all it holds (up to
    NODE_CAP). The same project always gives the same drawing."""
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        by_group[n["group"]].append(n)
    ids = sorted(by_group)
    # the smallest folders beyond GROUP_CAP share one group
    ranked = sorted(ids, key=lambda g: (-len(by_group[g]), g))
    merged = ranked[GROUP_CAP:]
    if merged:
        for g in merged:
            for n in by_group.pop(g):
                n["group"] = "(other folders)"
                by_group["(other folders)"].append(n)
        ids = sorted(by_group)
    drawn: set[str] = set()
    expanded = {g for g in ids if g in expand}
    total = len(nodes)

    def weight(n: dict[str, Any]) -> tuple:
        bad = n["state"]["band"] == "bad"
        return (0 if bad else 1, 0 if n["badges"] else 1, -(n["lines"] or 0), n["id"])

    budget = NODE_CAP - sum(min(len(by_group[g]), NODE_CAP) for g in expanded)
    rest = [g for g in ids if g not in expanded]
    groups = []
    if total <= NODE_CAP:
        quota = {g: len(by_group[g]) for g in ids}
    else:
        quota = {}
        remaining = max(len(rest), budget)
        sizes = {g: len(by_group[g]) for g in rest}
        pool = sum(sizes.values()) or 1
        for g in rest:                                          # a share of the budget by size, at least 2, room for "+N more"
            quota[g] = min(sizes[g], max(2, int(remaining * sizes[g] / pool) - 1))
        for g in expanded:
            quota[g] = min(len(by_group[g]), NODE_CAP)
    for g in ids:
        members = sorted(by_group[g], key=weight)
        keep = members[:quota[g]]
        drawn.update(n["id"] for n in keep)
        label = g if g not in (TOP,) else "(top of the project)"
        groups.append({"id": g, "label": label, "files": len(members), "drawn": len(keep), "more": len(members) - len(keep),
                       "expanded": g in expanded, "more_ids": sorted(n["id"] for n in members[quota[g]:])[:LIST_CAP]})
    return drawn, groups


# ------------------------------------------------------------------------------------------------ the detail --

def _evidence(ws, node: dict[str, Any], f: dict[str, Any], imports_of, imported_by, reaches, reached, run, changes,
              obj: dict[str, Any], *, scanned_at: str) -> list[dict[str, Any]]:
    rel, kind = node["id"], node["kind"]
    disk = f"read from disk at {hhmm(scanned_at)}"
    rows: list[dict[str, Any]] = [{"label": "Path", "value": rel, "source": disk},
                                  {"label": "Kind", "value": KIND_WORDS.get(kind, kind) + (f" ({node['language']})" if node["language"] else ""),
                                   "source": "decided from the file's name and place, " + disk}]
    rows.append({"label": "Lines", "value": f"{node['lines']:,}" if node["lines"] is not None else "not counted (binary, very large, or past the first "
                 f"{LINES_CAP:,} files)", "source": disk})
    if kind in ("module", "test"):
        imps = sorted(imports_of.get(rel, []))
        rows.append({"label": "Imports", "items": imps or None, "value": None if imps else "no project file",
                     "source": f"imports read from the code ({'python ast' if rel.endswith('.py') else 'a pattern match for JavaScript and TypeScript'}), {disk}"
                               if os.path.splitext(rel)[1].lower() in (".py",) + JS_SUFFIXES
                               else "Runesmith reads imports in Python, JavaScript and TypeScript only: nothing is read here"})
        by = sorted(imported_by.get(rel, []))
        rows.append({"label": "Imported by", "items": by or None, "value": None if by else "no project file", "source": disk})
    if kind == "module":
        tests = sorted(reaches.get(rel, []))
        rows.append({"label": "Tests that reach it", "items": [f"{t}: {_result_of(t, run)}" for t in tests] or None,
                     "value": None if tests else "none", "source": "test files that import it or are named for it, " + disk})
    if kind == "test":
        rs = sorted(reached.get(rel, []))
        rows.append({"label": "Reaches", "items": rs or None, "value": None if rs else "no module found", "source": disk})
        t = node.get("test")
        rows.append({"label": "Last result", "value": (t or {}).get("words") or "not run", "source": (t or {}).get("source") or "no recorded run"})
        if (t or {}).get("failing"):
            rows.append({"label": "Failing tests", "items": t["failing"][:12], "source": (t or {}).get("source")})
    change = changes.get(rel)
    on_disk = epoch(node["mtime_utc"])
    if change and (on_disk is None or on_disk <= (epoch(change["utc"]) or 0) + 10):
        rows.append({"label": "Last change", "value": f"{change['what']} {when(change['utc'])}" + (f" ({change['by']})" if change.get("by") else ""),
                     "source": change["source"], "utc": change["utc"]})
    elif change:                                                # the file changed again after Runesmith's change
        rows.append({"label": "Last change", "value": f"changed on disk {when(node['mtime_utc'])}, after Runesmith's change at "
                     f"{when(change['utc'])} ({change['what'].rstrip(',')}); who changed it is not recorded",
                     "source": f"file time, {disk}, and {change['source']}", "utc": node["mtime_utc"]})
    else:
        rows.append({"label": "Last change", "value": f"{when(node['mtime_utc'])}; Runesmith's records do not say who", "source": "file time, " + disk,
                     "utc": node["mtime_utc"]})
    work = [b for b in node["badges"] if b["kind"] in ("fix_waiting", "draft_waiting", "milestone")]
    rows.append({"label": "Open work", "items": [b["text"] for b in work] or None, "value": None if work else "none",
                 "source": "Work & proposals, the drafts and the plan, as recorded now"})
    state = node["state"]
    rows.append({"label": f"State: {state['band'].replace('_', ' ')}", "value": state["reason"], "source": state.get("source")})
    return rows


def _result_of(test: str, run: dict[str, Any] | None) -> str:
    if run is None:
        return "not run"
    if test in (run.get("failing") or {}):
        return "failed"
    return "passed" if run.get("outcome") == "passed" and run.get("scope") == "whole" else "no result of its own"


# ----------------------------------------------------------------------- badges from what Runesmith already keeps --

def _under(root: Path, base: Path, rel: str) -> str | None:
    """``rel`` (relative to ``base``) as a path relative to ``root``, or None when it is outside it."""
    try:
        return (Path(base) / rel).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _drafts_light(ws) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((ws.home / "drafts").glob("*/DRAFT.json")):
        draft = _read_json(path, None)
        if isinstance(draft, dict):
            rows.append(draft)
    return rows


def _proposal_rows(ws) -> list[dict[str, Any]]:
    """Each judge-accepted fix: its key, repo, files (as paths under the repo), state and the model that made it."""
    import gzip
    import json
    state = _read_json(ws.home / "PROPOSALS_STATE.json", {})
    sessions = {s.get("key"): s for s in ws.sessions()}
    rows = []
    for folder in sorted((ws.home / "experience").glob("*")):
        fix_file, task_file = folder / "verified_fix.json.gz", folder / "TASK.json"
        if not (fix_file.is_file() and task_file.is_file()):
            continue
        try:
            with gzip.open(fix_file, "rt", encoding="utf-8") as stream:
                files = sorted(json.load(stream))
            task = json.loads(task_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        done = state.get(folder.name) or {}
        calls = (sessions.get(folder.name) or {}).get("calls") or []
        model = next((c.get("model") for c in reversed(calls) if c.get("model")), None)
        rows.append({"key": folder.name, "repo": task.get("repo"), "files": files, "state": done.get("state", "waiting"),
                     "utc": done.get("utc"), "model": model})
    return rows


def file_badges(ws, root: Path) -> dict[str, list[dict[str, Any]]]:
    """What waits for the owner or touches a file, from the proposals, the drafts and the plan: ``{path: [badge]}``.
    Read from the records; nothing is written."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in _proposal_rows(ws):
        if p["state"] != "waiting" or not p["repo"]:
            continue
        try:
            outdated = bool(ws._fix_outdated(p["key"]))
        except Exception:
            outdated = False
        for rel in p["files"]:
            under = _under(root, Path(p["repo"]), rel)
            if under:
                out[under].append({"kind": "fix_waiting", "key": p["key"],
                                   "text": f"a fix {'(out of date) ' if outdated else ''}waits for you in Work & proposals",
                                   "source": "Work & proposals, proposal " + p["key"]})
    plan = ws.plan() or {}
    open_milestones = {m["id"]: m for m in plan.get("milestones", []) if m.get("status") in ("open", "doing")}
    for d in _drafts_light(ws):
        files = [f.get("path") for f in d.get("files", []) if isinstance(f, dict) and f.get("path")]
        if d.get("state") in ("waiting", "needs_revision"):
            for rel in files:
                under = _under(root, ws.root, rel)
                if under:
                    out[under].append({"kind": "draft_waiting", "id": d.get("id"),
                                       "text": f"a draft waits for you: {str(d.get('title') or d.get('id'))[:80]}",
                                       "source": f"Work & proposals, draft {d.get('id')}, {when(d.get('utc'))}"})
        milestone = open_milestones.get(d.get("milestone"))
        if milestone and d.get("state") not in ("rejected", "undone"):
            for rel in files:
                under = _under(root, ws.root, rel)
                if under:
                    out[under].append({"kind": "milestone", "id": milestone["id"],
                                       "text": f"in the open milestone “{str(milestone.get('title'))[:70]}”",
                                       "source": f"draft {d.get('id')} for that milestone touches it"})
    for mid, m in sorted(open_milestones.items()):             # a milestone that names the file itself
        text = " ".join(str(m.get(k) or "") for k in ("title", "detail", "done_when"))
        for rel in {b for b in re.findall(r"[\w./-]+\.\w{1,5}", text)}:
            under = _under(root, ws.root, rel)
            if under and (root / under).is_file() and not any(b["kind"] == "milestone" and b["id"] == mid for b in out[under]):
                out[under].append({"kind": "milestone", "id": mid, "text": f"in the open milestone “{str(m.get('title'))[:70]}”",
                                   "source": "the milestone's own words name this file"})
    return {k: v for k, v in out.items()}


def last_changes(ws, root: Path) -> dict[str, dict[str, Any]]:
    """The latest change Runesmith's records know of for each file: a draft applied (by you, or automatically by a checked
    build) or a fix applied. ``{path: {utc, what, by, source}}``."""
    best: dict[str, dict[str, Any]] = {}

    def keep(under: str | None, row: dict[str, Any]) -> None:
        if under and (under not in best or str(row["utc"] or "") > str(best[under]["utc"] or "")):
            best[under] = row

    for d in _drafts_light(ws):
        if d.get("state") != "applied":
            continue
        automatic = d.get("applied_by") == "delegated_build"
        for rel in d.get("applied_files") or [f.get("path") for f in d.get("files", []) if isinstance(f, dict)]:
            keep(_under(root, ws.root, str(rel)), {
                "utc": d.get("state_utc"), "what": "applied from a draft by a checked build, automatically" if automatic
                else "applied from a draft by you,", "by": f"drafted by {d.get('drafted_by') or 'an unknown author'}",
                "source": f"ledger and draft record: draft {d.get('id')}"})
    for p in _proposal_rows(ws):
        if p["state"] != "applied" or not p["repo"]:
            continue
        for rel in p["files"]:
            keep(_under(root, Path(p["repo"]), rel), {
                "utc": p["utc"], "what": "a fix was applied by you,", "by": "repaired by " + (p["model"] or "Runesmith's repair organ"),
                "source": f"ledger and proposal record: proposal {p['key']}"})
    return best


# ------------------------------------------------------------------------------------------- the ledger, read once --

_LEDGER_KINDS = {"generation.activated", "generation.imported", "generation.requalified", "trial.opened", "trial.rejected",
                 "trial.closed_by_owner", "milestone.added", "breakdown.adopted", "plan.saved", "fix_tests.started",
                 "stuck.needs_owner", "milestone.updated", "acceptance.approved", "acceptance.autopilot"}
_LEDGER_KIND_BYTES = tuple(kind.encode("ascii") for kind in sorted(_LEDGER_KINDS))
_LEDGER_CACHE: dict[str, dict[str, Any]] = {}


def ledger_events(ws, *kinds: str) -> list[dict[str, Any]]:
    """The ledger's events of these kinds, oldest first. The file is read once and then only what was appended since, so
    a long ledger costs nothing on a refresh. A line that is not complete JSON is left until the next read."""
    import json
    import threading
    path = Path(ws.ledger.path)
    entry = _LEDGER_CACHE.setdefault(str(path), {"offset": 0, "rows": [], "lock": threading.Lock()})
    with entry["lock"]:
        try:
            size = path.stat().st_size
        except OSError:
            return []
        if size < entry["offset"]:
            entry["offset"], entry["rows"] = 0, []
        if size > entry["offset"]:
            with open(path, "rb") as stream:
                stream.seek(entry["offset"])
                chunk = stream.read(size - entry["offset"])
            cut = chunk.rfind(b"\n") + 1
            for line in chunk[:cut].splitlines():
                if not any(kind in line for kind in _LEDGER_KIND_BYTES):
                    continue                                    # a cheap check before parsing: most events are other kinds
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("kind") in _LEDGER_KINDS:
                    entry["rows"].append(row)
            entry["offset"] += cut
        wanted = set(kinds)
        return [r for r in entry["rows"] if not wanted or r["kind"] in wanted]


# ------------------------------------------------------------------------------------------- Self: the lineage --

def _closed_trials(home: Path) -> dict[str, dict[str, Any]]:
    from runesmith.kaizen.trial import Trial
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(home.glob("TRIAL-*.json")):
        try:
            trial = Trial.load(path)
        except (OSError, ValueError, TypeError):
            continue
        if trial is not None:
            out[trial.candidate] = dict(trial.summary(), file=path.name, looks_detail=trial.looks, opened_utc=trial.opened_utc,
                                        incumbent=trial.incumbent)
    return out


def lineage_view(ws) -> dict[str, Any]:
    """Runesmith's generations in lineage order, parent before child (never by name or digest), each station with its state
    in plain words from the generation's manifest, its trial records and the ledger. A tick (``tick``) is drawn only on the
    active generation and on a generation that won its trial."""
    from runesmith import generations
    from runesmith.kaizen.trial import Trial
    home = ws.home
    gens = generations.list_generations(home)
    active = generations.active(home)
    by_id = {g["id"]: g for g in gens}
    ordered = sorted(gens, key=lambda g: (g.get("frozen_utc") or "", g["id"]))
    children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for g in ordered:
        parent = g.get("parent")
        children[parent if parent in by_id and parent != g["id"] else None].append(g)
    sequence: list[tuple[dict[str, Any], int]] = []
    seen: set[str] = set()

    def walk(g: dict[str, Any], depth: int) -> None:
        if g["id"] in seen:
            return
        seen.add(g["id"])
        sequence.append((g, depth))
        for child in children.get(g["id"], []):
            walk(child, depth + 1)

    for root in children.get(None, []):
        walk(root, 0)
    for g in ordered:                                           # a cycle in the manifests would hide stations: show them
        walk(g, 0)
    open_trial = None
    try:
        trial = Trial.load(home / "TRIAL.json")
        if trial is not None and trial.decision is None:
            open_trial = trial
    except (OSError, ValueError, TypeError):
        open_trial = None
    closed = _closed_trials(home)
    events = ledger_events(ws, "generation.activated")
    left_by_owner: dict[str, dict[str, Any]] = {}
    replaced_by: dict[str, dict[str, Any]] = {}
    activated_utc: dict[str, str] = {}
    for e in events:
        d = e.get("data") or {}
        activated_utc.setdefault(str(d.get("id")), e["utc"])
        previous = d.get("previous")
        if previous and previous != d.get("id"):
            if d.get("evidence") == "owner's choice":
                left_by_owner[previous] = {"to": d.get("id"), "utc": e["utc"]}
            else:
                replaced_by[previous] = {"to": d.get("id"), "utc": e["utc"], "evidence": d.get("evidence")}
    kaizen = {path.parent.name: _read_json(path, {}) for path in sorted((home / "kaizen").glob("*/KAIZEN_RESULT.json"))}
    stations = []
    for g, depth in sequence:
        gid = g["id"]
        prov = g.get("provenance") or {}
        name = ws.generation_name(gid)
        origin = ("imported" if prov.get("imported_from") else "requalified" if prov.get("requalified_from")
                  else "kaizen" if prov.get("target") or str(g.get("label") or "").startswith("kaizen") else "shipped")
        trial_info = None
        if open_trial is not None and open_trial.candidate == gid:
            counts = open_trial.counts
            nxt = max(open_trial.min_per_arm, (len(open_trial.looks) + 1) * open_trial.look_every)
            trial_info = {"state": "open", "incumbent": open_trial.incumbent, "counts": counts, "looks": len(open_trial.looks),
                          "min_per_arm": open_trial.min_per_arm, "look_every": open_trial.look_every,
                          "max_per_arm": open_trial.max_per_arm, "next_look_at": nxt,
                          "opened_utc": open_trial.opened_utc, "alpha": open_trial.alpha, "level_per_look": open_trial.level,
                          "source": "TRIAL.json"}
        elif gid in closed:
            c = closed[gid]
            trial_info = {"state": "closed", "decision": c["decision"], "incumbent": c["incumbent"], "counts": c["counts"],
                          "looks": c["looks"], "opened_utc": c["opened_utc"], "source": c["file"]}
        won = bool(trial_info and trial_info.get("decision") == "activate")
        state, words = "frozen", "Frozen: a candidate that was not adopted."
        if gid == active:
            state, words = "active", "Active: this is the generation that runs now."
        elif trial_info and trial_info["state"] == "open":
            c = trial_info["counts"]
            state = "on_trial"
            words = (f"On trial against {ws.generation_name(trial_info['incumbent'])}: the candidate repaired {c['candidate'][0]} of "
                     f"{c['candidate'][1]}, the incumbent {c['incumbent'][0]} of {c['incumbent'][1]}; {plural(trial_info['looks'], 'look')} "
                     f"done; the next look comes when each arm has {trial_info['next_look_at']} finished.")
        elif gid in left_by_owner:
            state = "rolled_back"
            words = (f"Rolled back: you made {ws.generation_name(left_by_owner[gid]['to'])} active on "
                     f"{when(left_by_owner[gid]['utc'])}.")
        elif trial_info and trial_info.get("decision") == "reject":
            c = trial_info["counts"]
            state = "rejected"
            words = (f"Rejected: it lost its trial (candidate {c['candidate'][0]} of {c['candidate'][1]}, incumbent "
                     f"{c['incumbent'][0]} of {c['incumbent'][1]}).")
        elif won:
            state = "won"
            later = replaced_by.get(gid)
            words = "Won its trial" + (f", then {ws.generation_name(later['to'])} replaced it on {when(later['utc'])}." if later else ".")
        elif trial_info and trial_info.get("decision") == "closed_by_owner":
            state, words = "trial_stopped", "Its trial was stopped by you; it was not adopted."
        elif gid in replaced_by:
            state = "superseded"
            words = (f"Replaced by {ws.generation_name(replaced_by[gid]['to'])} on {when(replaced_by[gid]['utc'])} "
                     f"({replaced_by[gid]['evidence'] or 'a recorded change'}).")
        elif origin == "imported":
            state, words = "imported", "Imported: frozen next to the active generation, not on trial."
        label = str(g.get("label") or "")
        campaign = label.split("kaizen-loop ", 1)[1] if "kaizen-loop " in label else None
        author = None
        if campaign and campaign in kaizen:
            attempts = kaizen[campaign].get("attempts") or []
            best = kaizen[campaign].get("best_iteration")
            row = next((a for a in attempts if a.get("iteration") == best), None) or (attempts[-1] if attempts else None)
            author = (row or {}).get("author")
        target = prov.get("target") or {}
        validation = prov.get("validation") if isinstance(prov.get("validation"), dict) else {}
        incumbent_validation = prov.get("incumbent_validation") if isinstance(prov.get("incumbent_validation"), dict) else {}
        stations.append({
            "id": gid, "name": name, "label": g.get("label"), "parent": g.get("parent"), "depth": depth, "origin": origin,
            "state": state, "state_words": words, "tick": gid == active or won, "active": gid == active,
            "created_utc": g.get("frozen_utc"), "organ_digest": g.get("organ_digest"), "kernel_digest": g.get("kernel_digest"),
            "campaign": campaign, "target": target.get("family") or target.get("stage") or target.get("kind"),
            "author_model": author, "imported_from": prov.get("imported_from"), "trial": trial_info,
            "validation": validation.get("strict_successes"), "incumbent_validation": incumbent_validation.get("strict_successes"),
            "activated_utc": activated_utc.get(gid), "source": "generations/" + gid + "/MANIFEST.json, trial records, the ledger"})
    return {"active": active, "stations": stations, "built_utc": _now()}


# ----------------------------------------------------------------------------------- Development: the plan graph --

STATE_WORDS = {"done": "Done", "ready": "Ready: nothing it needs first is still open", "waiting": "Waiting for a prerequisite",
               "doing": "In progress", "needs_you": "Needs you", "dropped": "Dropped (set aside)"}
_PRIORITY = {"needs_you": 0, "doing": 1, "ready": 2, "waiting": 3, "done": 4, "dropped": 5}


def _safe(label: str, notes: list[str], fn, default):
    """One source of the plan graph failing must not hide the rest: it is named, and its facts are unknown."""
    try:
        return fn()
    except Exception as error:                                   # noqa: BLE001 - any reader may fail on a damaged record
        notes.append(f"{label} could not be read ({type(error).__name__})")
        return default


def plan_graph(ws) -> dict[str, Any]:
    """The plan as a dependency graph (docs/MAP_LOGIC.md section 3): milestones, prerequisites as edges, each milestone's
    state from the plan and the work waiting on it, its origin from the ledger. Reads only; asks no model."""
    from runesmith.app import automatic
    from runesmith.app.planner import SETTLED, milestone_ready
    from runesmith.app.workspace import superseded_drafts
    plan = ws.plan() or {}
    milestones = [m for m in plan.get("milestones", []) if isinstance(m, dict) and m.get("id")]
    notes: list[str] = []
    if not milestones:
        return {"nodes": [], "edges": [], "tracks": [], "counts": {}, "notes": notes, "built_utc": _now(),
                "plan": {"version": plan.get("version"), "utc": plan.get("utc"), "drafted_by": plan.get("drafted_by")}}
    by_id = {m["id"]: m for m in milestones}
    drafts = _safe("the drafts", notes, ws.drafts, [])
    superseded = _safe("the drafts", [], lambda: superseded_drafts(drafts, plan), {})
    from runesmith.app import stuck as stuck_module
    stuck = {row["milestone"]: row for row in _safe("what waits for you", notes, lambda: stuck_module.owner_needed(ws), [])
             if isinstance(row, dict)}
    from runesmith.app import acceptance_proposals
    checks = _safe("the acceptance checks", notes, lambda: acceptance_proposals.status(ws), {})
    from runesmith.app import breakdowns
    proposed = {r.get("milestone"): r for r in _safe("the breakdowns", notes, lambda: breakdowns.proposals(ws), [])
                if r.get("state") == "proposed"}
    events = _safe("the ledger", notes, lambda: ledger_events(ws), [])
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    added: dict[str, dict[str, Any]] = {}
    split_by: dict[str, dict[str, Any]] = {}
    fixed: dict[str, dict[str, Any]] = {}
    for e in events:
        d = e.get("data") or {}
        if e["kind"] == "milestone.updated":
            history[str(d.get("id"))].append({"utc": e["utc"], "status": d.get("status")})
        elif e["kind"] == "milestone.added":
            added[str(d.get("id"))] = e
        elif e["kind"] == "breakdown.adopted":
            split_by[str(d.get("id"))] = e
        elif e["kind"] == "fix_tests.started":
            fixed[str(d.get("milestone"))] = e
    by_milestone: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in drafts:
        if d.get("milestone"):
            by_milestone[d["milestone"]].append(d)
    nodes, edges, level = [], [], {}

    def depth(mid: str, trail: tuple[str, ...] = ()) -> int:
        if mid in level:
            return level[mid]
        if mid in trail:
            return 0
        needs = [k for k in by_id[mid].get("depends_on", []) if k in by_id]
        level[mid] = (1 + max(depth(k, trail + (mid,)) for k in needs)) if needs else 0
        return level[mid]

    for m in milestones:
        mid = m["id"]
        status = m.get("status", "open")
        needs = []
        if status in ("open", "doing"):
            if mid in stuck:
                needs.append({"kind": "tries", "text": "its tries are used up, so it waits for you",
                              "source": f"the schedule's note, {when(stuck[mid].get('utc'))}"})
            waiting = [d for d in by_milestone.get(mid, []) if d.get("state") == "waiting" and d["id"] not in superseded]
            if waiting:
                needs.append({"kind": "draft", "text": f"{plural(len(waiting), 'draft')} waiting for your review",
                              "source": "Work & proposals, the drafts' own records"})
            if (checks.get(mid) or {}).get("proposal"):
                needs.append({"kind": "checks", "text": "proposed acceptance checks wait for your approval",
                              "source": "acceptance proposals, " + when(checks[mid]["proposal"].get("utc"))})
            if mid in proposed:
                needs.append({"kind": "breakdown", "text": "proposed smaller steps wait for your decision",
                              "source": "breakdown proposal " + str(proposed[mid].get("id"))})
        ready = milestone_ready(plan, m)
        if status == "done":
            state = "done"
        elif status == "dropped":
            state = "dropped"
        elif needs:
            state = "needs_you"
        elif status == "doing":
            state = "doing"
        elif ready:
            state = "ready"
        else:
            state = "waiting"
        unmet = [k for k in m.get("depends_on", []) if by_id.get(k, {}).get("status") not in SETTLED]
        for k in m.get("depends_on", []):
            if k in by_id:
                edges.append({"from": k, "to": mid, "type": "needs", "met": by_id[k].get("status") in SETTLED})
        # where it came from
        plan_when = plan.get("utc")
        if mid in fixed:
            origin = {"kind": "fix_tests", "text": "created by “Fix the failing tests”", "utc": fixed[mid]["utc"], "source": "ledger: fix_tests.started"}
        elif m.get("breakdown_id") and m["breakdown_id"] in split_by:
            e = split_by[m["breakdown_id"]]
            by = (e.get("data") or {}).get("by")
            origin = ({"kind": "stuck_split", "text": "a step split off by your stuck-milestone setting"} if by == automatic.BY
                      else {"kind": "breakdown", "text": "a breakdown you adopted"}) | {"utc": e["utc"], "source": "ledger: breakdown.adopted"}
        elif mid in added:
            origin = {"kind": "owner", "text": "added by you", "utc": added[mid]["utc"], "source": "ledger: milestone.added"}
        elif plan.get("drafted_by") and plan.get("drafted_by") != "owner":
            origin = {"kind": "plan", "text": f"in the plan drafted by {plan['drafted_by']} (version {plan.get('version')})",
                      "utc": plan_when, "source": "PLAN.json"}
        else:
            origin = {"kind": "unknown", "text": "unknown: the ledger does not say where it came from", "utc": None, "source": "the ledger"}
        mine = sorted(by_milestone.get(mid, []), key=lambda d: d.get("utc") or "")
        last = mine[-1] if mine else None
        approved = (checks.get(mid) or {}).get("approved")
        node = {"id": mid, "title": str(m.get("title") or mid), "track": str(m.get("track") or "Plan"), "status": status, "state": state,
                "state_words": STATE_WORDS[state], "depends_on": list(m.get("depends_on", [])), "unmet": unmet,
                "detail": m.get("detail") or "", "done_when": m.get("done_when") or "", "parent_id": m.get("parent_id"),
                "origin": origin, "needs": needs, "level": 0,
                "drafts": {"count": len(mine), "waiting": sum(1 for d in mine if d.get("state") == "waiting" and d["id"] not in superseded),
                           "last_author": (last or {}).get("drafted_by"), "last_utc": (last or {}).get("utc")},
                "checks": ({"approved": True, "provenance": approved.get("provenance"), "utc": approved.get("approved_utc"),
                            "proposed_by": approved.get("proposed_by")} if approved else {"approved": False}),
                "history": sorted(history.get(mid, []), key=lambda r: r["utc"])}
        nodes.append(node)
    for node in nodes:
        node["level"] = depth(node["id"])
    for node in nodes:
        node["evidence"] = _plan_evidence(node, by_id)
    tracks, seen = [], set()
    for t in [t for t in plan.get("tracks", []) if isinstance(t, dict) and t.get("name")] + [{"name": n["track"]} for n in nodes]:
        if t["name"] not in seen:
            seen.add(t["name"])
            mine = [n for n in nodes if n["track"] == t["name"]]
            tracks.append({"name": t["name"], "purpose": t.get("purpose") or "", "total": len(mine),
                           "counts": {s: sum(1 for n in mine if n["state"] == s) for s in STATE_WORDS}})
    tracks = [t for t in tracks if t["total"]]
    drawn = _plan_drawn(nodes)
    for n in nodes:
        n["drawn"] = n["id"] in drawn
    for t in tracks:
        t["more"] = sum(1 for n in nodes if n["track"] == t["name"] and not n["drawn"])
        t["more_ids"] = [n["id"] for n in nodes if n["track"] == t["name"] and not n["drawn"]]
    return {"nodes": nodes, "edges": edges, "tracks": tracks, "notes": notes, "built_utc": _now(),
            "counts": {s: sum(1 for n in nodes if n["state"] == s) for s in STATE_WORDS} | {"total": len(nodes), "drawn": len(drawn)},
            "plan": {"version": plan.get("version"), "utc": plan.get("utc"), "drafted_by": plan.get("drafted_by")}}


def _plan_drawn(nodes: list[dict[str, Any]]) -> set[str]:
    """At most NODE_CAP milestones are drawn: what needs you, what is in progress, what is ready, then the rest; finished
    and dropped ones last. Within a kind, the plan's own order."""
    if len(nodes) <= NODE_CAP:
        return {n["id"] for n in nodes}
    order = {n["id"]: i for i, n in enumerate(nodes)}
    ranked = sorted(nodes, key=lambda n: (_PRIORITY[n["state"]], order[n["id"]]))
    return {n["id"] for n in ranked[:NODE_CAP]}


def _plan_evidence(node: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    plan_src = "PLAN.json"
    rows: list[dict[str, Any]] = [
        {"label": "Title", "value": node["title"], "source": plan_src},
        {"label": "Done when", "value": node["done_when"] or "not written", "source": plan_src},
        {"label": "Status", "value": f"{node['status']} ({node['state_words'].lower()})", "source": plan_src},
        {"label": "Status history", "items": [f"{when(h['utc'])}: {h['status']}" for h in node["history"]] or None,
         "value": None if node["history"] else "no change recorded", "source": "ledger: milestone.updated"},
        {"label": "Origin", "value": node["origin"]["text"], "source": node["origin"]["source"], "utc": node["origin"].get("utc")}]
    needs = [by_id[k].get("title", k) + f" ({by_id[k].get('status', 'missing')})" if k in by_id else f"{k} (missing)" for k in node["depends_on"]]
    rows.append({"label": "Needs first", "items": needs or None, "value": None if needs else "nothing", "source": plan_src})
    if node["needs"]:
        rows.append({"label": "Needs you", "items": [n["text"] + " (" + n["source"] + ")" for n in node["needs"]],
                     "source": "the records named in each line"})
    d = node["drafts"]
    rows.append({"label": "Drafts", "value": (f"{plural(d['count'], 'draft')}, {d['waiting']} waiting; the last by {d['last_author'] or 'an unknown author'}"
                                              f" at {when(d['last_utc'])}") if d["count"] else "none",
                 "source": "the drafts' own records"})
    c = node["checks"]
    rows.append({"label": "Acceptance checks", "value": (f"approved ({c.get('provenance')}), {when(c.get('utc'))}" if c.get("approved")
                                                          else "none approved yet"), "source": "acceptance proposals"})
    return rows


def milestone_tries(ws, milestone_id: str) -> dict[str, Any]:
    """The tries a milestone has used on today's source, read on a click (it reads the project once to bind them to its
    files as they are now). Unknown, with the reason, when that cannot be established."""
    from runesmith.app.author_allowance import ordinary_allowance
    from runesmith.app.planner import milestone_contract, source_context
    milestone = next((m for m in (ws.plan() or {}).get("milestones", []) if m.get("id") == milestone_id), None)
    if milestone is None:
        raise KeyError(milestone_id)
    try:
        allowance = ordinary_allowance(ws, milestone_contract(ws, milestone), source_context(ws)["snapshot_digest"])
    except Exception as error:                                   # noqa: BLE001 - the reason is the answer
        return {"known": False, "reason": str(error)[:300] or type(error).__name__, "source": "the build attempts' own records"}
    return {"known": True, "used": allowance["used"], "remaining": allowance["remaining"], "limit": allowance["limit"],
            "one_more_try_used": bool(allowance["escalations"]), "source": "the build attempts' own records, counted against the files as they are now",
            "utc": _now()}


# --------------------------------------------------------------------------- Self: the metrics with their samples --

METRIC_DEFINITIONS = {
    "repair_yield": "the share of judged repair attempts that the held-out judge accepted",
    "seconds_per_repair": "seconds spent on judged attempts, divided by the repairs the judge accepted",
    "calls_per_repair": "model calls made in judged attempts, divided by the repairs the judge accepted",
    "false_promotion_rate": "the share of judged attempts that passed the public tests and failed the judge",
}
FEW = 10


def metrics_view(ws) -> dict[str, Any]:
    """Each self-knowledge metric with its sample size and window, and, during a trial, per arm (docs/MAP_LOGIC.md section 2)."""
    from runesmith.kaizen.trial import Trial
    from runesmith.selfmap import capabilities
    sessions = ws.sessions()
    judged = [r for r in sessions if r.get("status") != "censored_transport" and r.get("strict_success") is not None]
    stamps = sorted(str(r.get("utc_start")) for r in judged if r.get("utc_start"))
    since = stamps[0] if stamps else None
    caps = capabilities(sessions) if sessions else {}
    out: dict[str, Any] = {"metrics": {}, "built_utc": _now()}
    trial = None
    try:
        trial = Trial.load(ws.home / "TRIAL.json")
        trial = trial if trial is not None and trial.decision is None else None
    except (OSError, ValueError, TypeError):
        trial = None
    arms: dict[str, Any] = {}
    if trial is not None:
        for arm in ("incumbent", "candidate"):
            mine = [r for r in sessions if r.get("trial_arm") == arm and str(r.get("utc_start") or "") >= trial.opened_utc]
            arms[arm] = {"sessions": len([r for r in mine if r.get("strict_success") is not None]), "caps": capabilities(mine) if mine else {}}
    for name, definition in METRIC_DEFINITIONS.items():
        cap = caps.get(name) or {}
        row = {"value": cap.get("value"), "band": cap.get("band", "unknown"), "n": len(judged), "since": since,
               "few": len(judged) < FEW, "definition": definition,
               "source": f"{len(judged)} judged sessions in sessions/ since {hhmm(since) if since else 'this home was created'}"}
        if arms:
            row["arms"] = {arm: {"n": a["sessions"], "value": (a["caps"].get(name) or {}).get("value"), "few": a["sessions"] < FEW}
                           for arm, a in arms.items()}
        out["metrics"][name] = row
    out["sessions"] = len(judged)
    out["window"] = (f"{len(judged)} judged sessions since {when(since)}" if since else "no judged session yet")
    return out


# ----------------------------------------------------------------------- Operations: the loop, counted and defined --

def _found_work(status: str) -> bool:
    """Whether a round's status for an object says its tests failed: pytest discovery ("failing"), or the unittest
    measurement a round makes where the repair organ cannot serve the project ("measured: 2 of 14 tests fail")."""
    if status == "failing":
        return True
    match = re.match(r"measured: (\d+) of \d+ tests? fail", str(status))
    return bool(match and int(match.group(1)) > 0)


def stages_view(ws) -> list[dict[str, Any]]:
    """The work loop's stages, each counter with what it counts and since when (docs/MAP_LOGIC.md section 4)."""
    env_map = ws.environment_map() or {"objects": []}
    work = _read_json(ws.home / "WORK.json", {})
    statuses = ws.object_statuses(work, env_map)
    sessions = ws.sessions()
    judged = [r for r in sessions if r.get("strict_success") is not None]
    first = min((str(r.get("utc_start")) for r in judged if r.get("utc_start")), default=None)
    created = next(iter(ledger_events(ws, "generation.activated")), None)
    home_since = (created or {}).get("utc")
    proposals = ws.proposal_counts()
    drafts = ws.drafts()
    waiting_drafts = sum(1 for d in drafts if d.get("state") == "waiting")
    auto_applied = sum(1 for d in drafts if d.get("state") == "applied" and d.get("applied_by") == "delegated_build")
    owner_applied = sum(1 for d in drafts if d.get("state") == "applied" and d.get("applied_by") != "delegated_build")
    mapped = [o for o in env_map.get("objects", [])]
    code = [o for o in mapped if o.get("kind") == "python_repository"]
    failing = [n for n, s in statuses.items() if _found_work(s)]
    since_words = f"since {when(first or home_since)}" if (first or home_since) else "since this home was created"
    return [
        {"id": "map", "label": "Map", "count": len(mapped), "unit": "objects mapped",
         "definition": "objects the latest map lists, including any you excluded (listed, never read)",
         "window": f"as of the latest map, {when(env_map.get('utc'))}" if env_map.get("utc") else "no map yet",
         "source": "ENVIRONMENT.json", "utc": env_map.get("utc"),
         "extra": f"{len(code)} are Python projects whose tests Runesmith can run"},
        {"id": "discover", "label": "Discover", "count": len(failing), "unit": "objects with work found",
         "definition": "objects whose tests failed in the latest round (found by pytest discovery, or by a unittest measurement): the failures a repair can work on",
         "window": f"the latest round, {when(work.get('utc'))}" if work.get("utc") else "no round has run yet",
         "source": "WORK.json", "utc": work.get("utc"),
         "extra": ("failing: " + ", ".join(sorted(failing))) if failing else "none failing in that round"},
        {"id": "repair", "label": "Repair", "count": len(judged), "unit": "attempts judged",
         "definition": "repair attempts that got the held-out judge's verdict (attempts censored by a transport failure are not counted)",
         "window": since_words, "source": "sessions/, one record per attempt",
         "utc": None, "extra": None},
        {"id": "judge", "label": "Judge", "count": sum(1 for r in judged if r.get("strict_success")), "unit": "accepted",
         "definition": "judged attempts the judge accepted: the fix passed tests the repair never saw",
         "window": since_words, "source": "sessions/, one record per attempt", "utc": None, "extra": None},
        {"id": "propose", "label": "Propose", "count": proposals.get("waiting", 0), "unit": "fixes waiting for you",
         "definition": "accepted fixes you have not yet applied or rejected, right now (drafts are counted apart)",
         "window": "now", "source": "PROPOSALS_STATE.json and the experience store", "utc": None,
         "extra": f"{plural(waiting_drafts, 'draft')} also wait for your review"},
        {"id": "apply", "label": "Apply", "count": proposals.get("applied", 0) + owner_applied + auto_applied, "unit": "applied",
         "definition": "fixes you applied, drafts you applied, and drafts a checked build applied automatically",
         "window": since_words, "source": "PROPOSALS_STATE.json and the drafts' own records", "utc": None,
         "extra": f"{proposals.get('applied', 0)} fixes and {owner_applied} drafts by you; {auto_applied} drafts automatically"},
    ]


def roles_evidence(ws, stats: dict[str, Any]) -> dict[str, Any]:
    """Per model route: calls, errors and whether every call failed, from the call counters (OPERATIONS.json)."""
    out = {}
    for name, row in (stats or {}).items():
        calls, errors = int(row.get("calls") or 0), int(row.get("errors") or 0)
        out[name] = {"calls": calls, "errors": errors, "failing_every_call": calls > 0 and errors >= calls,
                     "last_utc": row.get("last_utc"), "last_error": row.get("last_error"),
                     "source": "OPERATIONS.json: every call counted since this home was created"}
    return out
