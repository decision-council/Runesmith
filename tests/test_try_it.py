"""Try what was built (G2, out-of-box journey R1): the owner runs the project's own program from the Studio."""
import json

import pytest

from runesmith.app import try_it
from runesmith.app.workspace import Workspace, WorkspaceError

PROGRAM = '''import json, sys, time
from pathlib import Path
data = Path("data.json")
books = json.loads(data.read_text()) if data.exists() else []
command = sys.argv[1] if len(sys.argv) > 1 else "help"
if command == "add":
    books.append(sys.argv[2]); data.write_text(json.dumps(books)); print("added", sys.argv[2])
elif command == "list":
    print("\\n".join(books) or "No books yet")
elif command == "sleep":
    time.sleep(60)
elif command == "ask":
    print("name?", input())
else:
    print("usage: python -m shelf add TITLE | list")
'''
README = """# Shelf

Add a book:

    python -m shelf add Dune

In general: `python -m shelf add TITLE`. See them with `python -m shelf list`.
Never suggested: `python -m json.tool` and `cmd /c dir`.
"""


def project(tmp_path):
    (tmp_path / "shelf").mkdir()
    (tmp_path / "shelf" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "shelf" / "__main__.py").write_text(PROGRAM, encoding="utf-8")
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(["Emma"]), encoding="utf-8")
    return Workspace(tmp_path)


def test_only_the_projects_own_python_program_can_be_tried(tmp_path):
    ws = project(tmp_path)
    (tmp_path / "tool.py").write_text("print('ok')\n", encoding="utf-8")
    assert try_it.parse(ws, "python -m shelf list")[1:] == ["-m", "shelf", "list"]
    assert try_it.parse(ws, 'python tool.py "a b"')[1:] == ["tool.py", "a b"]
    for command, why in [("cmd /c dir", "own Python program"), ("python -c 'print(1)'", "not a Python file"),
                         ("python -m json.tool", "not a program in this folder"), ("python ../outside.py", "not a Python file"),
                         ("python -m shelf 'unclosed", "could not be read"), ("", "Type the command")]:
        with pytest.raises(WorkspaceError, match=why):
            try_it.parse(ws, command)
    (ws.home / "inside.py").write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="not a Python file"):
        try_it.parse(ws, "python .runesmith/inside.py")


def test_documented_commands_are_suggested_and_placeholders_marked(tmp_path):
    rows = {s["command"]: s for s in try_it.suggestions(project(tmp_path))}
    assert list(rows) == ["python -m shelf add Dune", "python -m shelf add TITLE", "python -m shelf list"]
    assert rows["python -m shelf add TITLE"]["placeholders"] and not rows["python -m shelf add Dune"]["placeholders"]


def test_practice_runs_keep_the_real_folder_untouched_until_the_owner_chooses_it(tmp_path):
    ws = project(tmp_path)
    assert try_it.run(ws, "python -m shelf add Dune")["stdout"].strip() == "added Dune"
    listed = try_it.run(ws, "python -m shelf list")                    # the practice copy lasts between runs
    assert listed["stdout"].split() == ["Emma", "Dune"] and listed["exit_code"] == 0 and not listed["real"]
    assert json.loads((tmp_path / "data.json").read_text(encoding="utf-8")) == ["Emma"]
    try_it.reset_practice(ws)
    assert try_it.run(ws, "python -m shelf list")["stdout"].split() == ["Emma"]
    assert try_it.run(ws, "python -m shelf add Ulysses", real=True)["real"]
    assert json.loads((tmp_path / "data.json").read_text(encoding="utf-8")) == ["Emma", "Ulysses"]
    assert [e["data"]["real"] for e in ws.ledger.events("try.ran")] == [False, False, False, True]


def test_a_run_never_waits_for_input_or_runs_forever(tmp_path, monkeypatch):
    ws = project(tmp_path)
    asked = try_it.run(ws, "python -m shelf ask")
    assert asked["exit_code"] != 0 and "EOFError" in asked["stderr"]
    monkeypatch.setattr(try_it, "TIMEOUT_S", 1)
    slow = try_it.run(ws, "python -m shelf sleep")
    assert slow["timed_out"] and slow["exit_code"] is None and slow["seconds"] < 10


def test_the_studio_routes_run_on_the_practice_copy_unless_real_is_exactly_true(tmp_path):
    from types import SimpleNamespace
    from runesmith.app.server import api_try, api_try_reset, api_try_run
    ws = project(tmp_path)
    studio = SimpleNamespace(ws=ws)
    assert [s["command"] for s in api_try(studio, {}, None)["suggestions"]][0] == "python -m shelf add Dune"
    assert not api_try_run(studio, {}, {"command": "python -m shelf add X", "real": "yes"})["real"]
    assert json.loads((tmp_path / "data.json").read_text(encoding="utf-8")) == ["Emma"]
    assert api_try_reset(studio, {}, {})["files"] >= 2
    assert api_try_run(studio, {}, {"command": "python -m shelf add X", "real": True})["real"]
