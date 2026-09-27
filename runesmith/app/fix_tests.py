"""Fix the failing tests (journey J3): a build milestone whose acceptance is the project's own tests, frozen now.

Runesmith's repair organ (the measured g0/C7 path) works on projects with a src/ folder. For every layout, and as the
plain owner path "my tests fail, fix them", the failing tests become a build milestone:

- the project's current test files are embedded, frozen, in the milestone's acceptance file, a single self-contained
  file whose fingerprint covers them, and they decide when it is done;
- builders may change only the code, never the tests: automatic apply, when the owner allows it, is limited to the
  code folders;
- the ordinary build, check and apply loop does the rest, unattended if the owner allows automatic apply.

The caller owns the Workspace instance lock, as with other Studio mutations.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from runesmith import atomic
from runesmith.app.acceptance_contracts import publish_expectations
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

TEST_DIRS = ("tests", "test")
SKIP = {"__pycache__", ".git", ".runesmith", ".venv", "venv", "node_modules"}
MAX_FROZEN_BYTES = 400_000

ACCEPTANCE = '''# Owner acceptance for milestone {mid}: the project's own tests, frozen {utc} ("Fix the failing tests").
# Builds of this milestone are judged by these tests as they were; builders may change the code, never the tests.
import os
import sys
import types
import unittest

FROZEN = {files!r}


def load_tests(loader, standard, pattern):
    root = os.getcwd()                                   # the candidate project being checked
    for folder in (os.path.join(root, "src"), root):
        if folder not in sys.path:
            sys.path.insert(0, folder)
    suite = unittest.TestSuite()
    for index, (path, source) in enumerate(sorted(FROZEN.items())):
        if not os.path.basename(path).startswith("test"):
            continue
        module = types.ModuleType("owner_frozen_test_%d" % index)
        module.__file__ = os.path.join(root, path)
        module.__package__ = os.path.dirname(path).replace("/", ".") or None
        sys.modules[module.__name__] = module
        exec(compile(source, path, "exec"), module.__dict__)
        for value in list(module.__dict__.values()):
            if isinstance(value, type) and issubclass(value, unittest.TestCase) and value.__module__ == module.__name__:
                value.PUBLIC_CRITERIA = {{name: ["tests.all"] for name in dir(value) if name.startswith("test")}}
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
'''


def _visible(path: Path) -> bool:
    return not any(part in SKIP or part.startswith(".") for part in path.parts)


def project_test_files(root: Path) -> list[str]:
    """The project's test files: everything under tests/ or test/, and test_*.py at the top."""
    found = []
    for folder in TEST_DIRS:
        base = root / folder
        if base.is_dir():
            found += [p.relative_to(root).as_posix() for p in sorted(base.rglob("*.py"))
                      if _visible(p.relative_to(root))]
    found += [p.name for p in sorted(root.glob("test_*.py"))]
    return found


def code_paths(root: Path) -> list[str]:
    """Where a fix may write: src/, the packages and modules at the top, never the tests."""
    paths = []
    if (root / "src").is_dir():
        paths.append("src")
    for p in sorted(root.iterdir()):
        if p.name in TEST_DIRS or p.name in SKIP or p.name.startswith(".") or p.name == "src":
            continue
        if p.is_dir() and ((p / "__init__.py").is_file() or (p / "__main__.py").is_file()):
            paths.append(p.name)
        elif p.is_file() and p.suffix == ".py" and not p.name.startswith("test"):
            paths.append(p.name)
    return paths


def measure(ws, path: Path, name: str) -> dict[str, Any]:
    """Run a project's tests once with Python's own unittest, on a throwaway copy: no pytest needed (J3-G2).

    Rounds use it for projects the repair organ cannot serve (no src/ folder, or no pytest installed), and only when
    the owner allows running the project's tests.
    """
    from runesmith.app.building import _run_checks
    folder = ws.home / "fix-tests"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="measure-", dir=folder, ignore_cleanup_errors=True) as directory:
        stage = Path(directory) / "project"
        shutil.copytree(path, stage, ignore=shutil.ignore_patterns(*SKIP, "*.pyc"))
        result = _run_checks(stage, "project", Path(directory) / "tests.txt", timeout_s=300)
    record = {"object": name, "path": str(path), "status": result.get("status"), "ran": result.get("ran") or 0,
              "failures": result.get("failures") or 0, "errors": result.get("errors") or 0,
              "failing": [d.get("test") for d in result.get("failure_details") or []], "utc": _now()}
    measured = _read_json(folder / "MEASURED.json", {})
    measured[str(path)] = record
    _write_json(folder / "MEASURED.json", measured)
    return record


def offer(ws) -> dict[str, Any] | None:
    """What the Overview offers: a Python project whose tests do not all pass, from a round's measurement or the map."""
    measured = _read_json(ws.home / "fix-tests" / "MEASURED.json", {})
    for obj in (ws.environment_map() or {}).get("objects", []):
        if obj.get("kind") != "python_repository":
            continue
        record = measured.get(obj.get("path"))
        if record and record["ran"] and record["failures"] + record["errors"]:
            return {"object": obj.get("name"), "path": obj.get("path"),
                    "tests_green": round(1 - (record["failures"] + record["errors"]) / record["ran"], 3),
                    "code_paths": code_paths(Path(obj["path"])), "test_files": len(project_test_files(Path(obj["path"]))),
                    "measured_utc": record["utc"]}
        rungs = {r.get("rung"): r.get("status") for r in obj.get("ladder") or []}
        if rungs.get("tests_pass") == "not_achieved":
            green = next((o.get("value") for o in obj.get("objectives") or [] if o.get("id") == "tests_green"), None)
            return {"object": obj.get("name"), "path": obj.get("path"), "tests_green": green,
                    "code_paths": code_paths(Path(obj["path"])), "test_files": len(project_test_files(Path(obj["path"])))}
    return None


def start(ws, *, allow_apply: bool = False) -> dict[str, Any]:
    """Add the milestone, freeze the tests into its acceptance file, and publish what builders are told."""
    if type(allow_apply) is not bool:
        raise WorkspaceError("Say whether the fix may be applied automatically.")
    root = ws.root
    files = project_test_files(root)
    if not files:
        raise WorkspaceError("No test files were found here (a tests/ folder, or test_*.py files at the top).")
    frozen, size = {}, 0
    for rel in files:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        size += len(text)
        frozen[rel] = text
    if size > MAX_FROZEN_BYTES:
        raise WorkspaceError("The test files are too large to freeze into one acceptance file.")
    paths = code_paths(root)
    if not paths:
        raise WorkspaceError("No code folder or module was found next to the tests.")
    utc = _now()
    milestone = ws.add_milestone(
        "Make the failing tests pass",
        detail=("Some of this project's tests fail. Change the code, not the tests, so that every test passes. "
                "Run them with: python -m unittest discover -s tests"), track="Fix")
    ws.update_milestone(milestone["id"], {"done_when": "Every test in the project's own test files passes, as they "
                                                       f"were on {utc[:10]}; the test files are not changed."})
    target = ws.home / "acceptance" / f"{milestone['id']}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(ACCEPTANCE.format(mid=milestone["id"], utc=utc, files=frozen), encoding="utf-8")
    atomic.replace(temporary, target)
    publish_expectations(ws, milestone["id"], [
        {"id": "tests.all", "description": "Every test in the project's own test files passes, as they were when this "
                                           "fix was asked for. Change the code only; the tests are not to be changed."}],
        "Fix the failing tests: the owner's own tests decide.", by="owner (fix the failing tests)")
    if allow_apply:
        ws.update_settings({"build_steps": True, "build_apply": True, "build_paths": paths})
    ws.ledger.append("fix_tests.started", {"milestone": milestone["id"], "frozen_files": len(frozen),
                                           "code_paths": paths, "allow_apply": allow_apply})
    return {"milestone": milestone["id"], "frozen_files": len(frozen), "code_paths": paths, "allow_apply": allow_apply}
