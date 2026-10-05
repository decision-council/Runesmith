"""Try what was built: run the project's own Python program from the Studio (gap G2, out-of-box journey R1).

Journey R1 found that a non-technical owner could not use the program Runesmith had built without a terminal. Here
the owner picks one of the commands the project documents (its README, then its milestones), edits it, and runs it.

- It runs on a practice copy of the folder unless the owner chooses the real folder. The practice copy lasts between
  runs, so "add" and then "list" behave as they would for real, until the owner starts it again.
- Only the project's own Python program runs (``python -m <package in this folder>`` or ``python <file in this
  folder>.py``): never a shell and never another program.
- Input is closed, output is capped, the run stops after a time limit, and every run is recorded in the ledger.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from runesmith.app.snapshots import SnapshotUnsupported, collect_snapshot
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

TIMEOUT_S = 30
MAX_OUTPUT = 20000
MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
DOCUMENTED = re.compile(r"(?:python3?|py)\s+(?:-m\s+[A-Za-z_][\w.]*|[\w./\\-]+\.py)[^`\n]*")
QUOTED = re.compile(r"(['`])((?:python3?|py)\s+(?:-m\s+[A-Za-z_][\w.]*|[\w./\\-]+\.py)(?:(?!\1)[^\n])*)\1")
PLACEHOLDER = re.compile(r"\b[A-Z]{2,}\b|YYYY|<[^>]*>|\.\.\.|…")
README_NAMES = ("README.md", "README.txt", "README.rst", "README")


def _folder(ws) -> Path:
    return ws.home / "try"


def parse(ws, command: str) -> list[str]:
    """The argument list to run, or a WorkspaceError in plain words. Never a shell."""
    if not isinstance(command, str) or not command.strip() or len(command) > 2000:
        raise WorkspaceError("Type the command to try, for example: python -m yourprogram --help")
    try:
        words = shlex.split(command.strip(), posix=True)
    except ValueError as error:
        raise WorkspaceError(f"The command could not be read ({error}). Check its quotes.") from None
    if len(words) < 2 or words[0].lower() not in ("python", "python3", "py"):
        raise WorkspaceError("Only this project's own Python program can be tried here: "
                             "start with “python -m …” or “python something.py”.")
    root = ws.root.resolve()
    if words[1] == "-m":
        if len(words) < 3 or not MODULE.fullmatch(words[2]):
            raise WorkspaceError("After “python -m”, name the program's package, for example: python -m yourprogram")
        top = words[2].split(".")[0]
        package = root / top
        if not ((package.is_dir() and ((package / "__init__.py").is_file() or (package / "__main__.py").is_file()))
                or (root / (top + ".py")).is_file()):
            raise WorkspaceError(f"“{words[2]}” is not a program in this folder.")
        return [sys.executable, "-m", *words[2:]]
    script = (root / words[1]).resolve()
    if (script.suffix != ".py" or not script.is_file() or not script.is_relative_to(root)
            or script.is_relative_to(ws.home.resolve())):
        raise WorkspaceError(f"“{words[1]}” is not a Python file in this folder.")
    return [sys.executable, script.relative_to(root).as_posix(), *words[2:]]


def _applied_draft_texts(ws, limit=8) -> list[tuple[str, str]]:
    """What the newest applied drafts say about running what they wrote: their `why` (the author is asked to put the run
    instructions there) and each file's purpose, newest first. Read straight from the saved drafts, never a diff."""
    rows = []
    for path in (ws.home / "drafts").glob("*/DRAFT.json"):
        draft = _read_json(path, None)
        if isinstance(draft, dict) and draft.get("state") == "applied":
            rows.append((str(draft.get("applied_utc") or draft.get("utc") or draft.get("created") or ""), draft))
    found = []
    for _, draft in sorted(rows, key=lambda r: r[0], reverse=True)[:limit]:
        purposes = [str(f.get("purpose") or "") for f in draft.get("files", []) if isinstance(f, dict)]
        found.append((draft.get("title") or "a draft", "\n".join([str(draft.get("why") or ""), *purposes])))
    return found


def _entry_points(ws) -> list[str]:
    """The commands the program's own files offer when nothing documents one: ``python -m package`` for a package with a
    ``__main__``, ``python file.py`` for a top-level file that runs when started (never a test file)."""
    root, found = ws.root, []
    for child in sorted(root.iterdir()) if root.is_dir() else []:
        if child.name.startswith((".", "_", "test")) or child.name == "tests":
            continue
        if child.is_dir() and (child / "__main__.py").is_file() and (child / "__init__.py").is_file():
            found.append(f"python -m {child.name}")
        elif child.is_file() and child.suffix == ".py":
            try:
                source = child.read_text(encoding="utf-8", errors="replace")[:200000]
            except OSError:
                continue
            if re.search(r"""if\s+__name__\s*==\s*['"]__main__['"]""", source):
                found.append(f"python {child.name}" + (" --help" if re.search(r"argparse|sys\.argv|click|typer", source) else ""))
    return found[:6]


def suggestions(ws) -> list[dict[str, Any]]:
    """Commands the project documents, marked when they still hold placeholders such as TITLE. Read, in this order, from
    the README, the brief, the plan's milestones and the newest applied drafts (journey J0-F5: the program was described
    in none of the first two, and the card stayed hidden); with none written down, the program's own entry points."""
    texts = []
    readme = next((ws.root / name for name in README_NAMES if (ws.root / name).is_file()), None)
    if readme:
        texts.append(("README", readme.read_text(encoding="utf-8", errors="replace")[:200000]))
    try:
        brief = str((ws.brief() or {}).get("text") or "")
    except Exception:                                                  # a brief that cannot be read is no source
        brief = ""
    if brief:
        texts.append(("Your brief", brief[:200000]))
    for milestone in (ws.plan() or {}).get("milestones", []):
        texts.append((milestone.get("title") or milestone.get("id") or "plan",
                      " ".join(str(milestone.get(k) or "") for k in ("detail", "done_when"))))
    texts.extend(_applied_draft_texts(ws))
    found, seen = [], set()

    def collect(source, text):
        # A command written inside quotes in a sentence ('python -m stockbook list' shows every item) ends at its
        # closing quote; without this the match ran on to the end of the line and was dropped (journey J1-G1).
        quoted = [(m.start(), m.group(2).strip()) for m in QUOTED.finditer(text)]
        rest = QUOTED.sub(lambda m: " " * len(m.group(0)), text)          # same length: positions keep their order
        loose = [(m.start(), m.group(0).strip().strip("'\"`").rstrip(".,;:'\"`")) for m in DOCUMENTED.finditer(rest)]
        for _, command in sorted(quoted + loose):
            # A sentence ("Run it with: python app.py list. It keeps books.") ends at its full stop.
            sentence = re.split(r"(?<=\S)\.\s", command)[0].rstrip(".,;:'\"`")
            if sentence != command:
                try:
                    shlex.split(sentence, posix=True)
                    command = sentence
                except ValueError:
                    pass
            if command in seen:
                continue
            try:
                argv = parse(ws, command)
            except WorkspaceError:
                continue
            seen.add(command)
            arguments = argv[3:] if argv[1] == "-m" else argv[2:]
            found.append({"command": command, "source": source,
                          "placeholders": any(PLACEHOLDER.search(a) for a in arguments)})
    for source, text in texts:
        collect(source, text)
    if not found:
        for command in _entry_points(ws):
            collect("the program itself", command)
    return found[:24]


def status(ws) -> dict[str, Any]:
    practice = _read_json(_folder(ws) / "PRACTICE.json", None)
    return {"suggestions": suggestions(ws), "practice": practice if (_folder(ws) / "practice").is_dir() else None,
            "timeout_s": TIMEOUT_S}


def reset_practice(ws) -> dict[str, Any]:
    """Make the practice copy again from the real folder (its source, settings and data files)."""
    try:
        snapshot = collect_snapshot(ws)
    except SnapshotUnsupported as error:
        raise WorkspaceError(f"A practice copy of this folder is not possible: {error}") from None
    target = _folder(ws) / "practice"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    for rel, data in snapshot["files"].items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    record = {"created_utc": _now(), "files": len(snapshot["files"]), "snapshot_digest": snapshot["digest"]}
    _write_json(_folder(ws) / "PRACTICE.json", record)
    return record


def run(ws, command: str, *, real: bool = False) -> dict[str, Any]:
    """Run one documented command, on the practice copy unless ``real``; the owner started it."""
    if type(real) is not bool:
        raise WorkspaceError("Choose the practice copy or your real folder.")
    argv = parse(ws, command)
    if real:
        folder = ws.root
    else:
        folder = _folder(ws) / "practice"
        if not folder.is_dir():
            reset_practice(ws)
    scratch = _folder(ws) / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC"}}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(scratch), TMP=str(scratch))
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(argv, cwd=folder, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                   timeout=TIMEOUT_S, check=False)
        stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as expired:
        timed_out, code = True, None
        stdout, stderr = expired.stdout or b"", expired.stderr or b""
    seconds = round(time.monotonic() - started, 2)
    text = lambda data: data.decode("utf-8", errors="replace")[:MAX_OUTPUT]  # noqa: E731
    result = {"command": command, "real": real, "exit_code": code, "timed_out": timed_out, "seconds": seconds,
              "stdout": text(stdout), "stderr": text(stderr), "utc": _now()}
    ws.ledger.append("try.ran", {"command": command, "real": real, "exit_code": code, "timed_out": timed_out,
                                 "seconds": seconds})
    return result
