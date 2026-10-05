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


def test_commands_quoted_inside_a_milestone_sentence_are_found(tmp_path):
    # Journey J1-G1: a plan wrote its commands in single quotes mid-sentence, and Try it offered nothing at all.
    ws = project(tmp_path)
    ws.save_plan({"summary": "Stock", "milestones": [{"title": "Record a delivery",
        "detail": "A command 'python -m shelf add NAME' adds the book, and 'python -m shelf list' shows every book.",
        "done_when": "After 'python -m shelf add \"The Hobbit\"', 'python -m shelf list' shows The Hobbit."}]})
    rows = {s["command"]: s for s in try_it.suggestions(ws)}
    assert {"python -m shelf add NAME", "python -m shelf list", 'python -m shelf add "The Hobbit"'} <= set(rows)
    assert rows["python -m shelf add NAME"]["placeholders"] and not rows['python -m shelf add "The Hobbit"']["placeholders"]
    assert not any("adds the book" in c or "shows" in c for c in rows)


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


# ---- the newcomer path: the card is shown for a program written down anywhere, and never promised when absent ----

def reading_log(tmp_path):
    """What the drafted app looked like: a program file and its test in the folder, no README, no command in the milestone."""
    (tmp_path / "readinglog.py").write_text(
        "import argparse\nparser = argparse.ArgumentParser()\nparser.add_argument('command')\n"
        "if __name__ == '__main__':\n    print('books:', parser.parse_args().command)\n", encoding="utf-8")
    (tmp_path / "test_readinglog.py").write_text("import unittest\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    ws.save_plan({"summary": "Reading log", "milestones": [{"title": "Add and list books", "detail": "Keep books in a file.",
                                                            "done_when": "A book can be added and listed."}]})
    return ws


def applied_draft(ws, **fields):
    folder = ws.home / "drafts" / "d1"
    folder.mkdir(parents=True)
    (folder / "DRAFT.json").write_text(json.dumps(dict({"id": "d1", "state": "applied", "milestone": "m1", "title": "First files",
                                                          "files": []}, **fields)), encoding="utf-8")


def test_a_command_in_the_brief_shows_the_card(tmp_path):
    ws = reading_log(tmp_path)
    ws.set_brief("A reading log. I run it with 'python readinglog.py list' and add books with python readinglog.py add TITLE.")
    rows = {s["command"]: s for s in try_it.suggestions(ws)}
    assert "python readinglog.py list" in rows and rows["python readinglog.py list"]["source"] == "Your brief"


def test_the_run_instructions_in_the_applied_drafts_why_show_the_card(tmp_path):
    ws = reading_log(tmp_path)
    applied_draft(ws, why="A command line reading log. Run it with: python readinglog.py list. It keeps the books in a file.",
                  files=[{"path": "readinglog.py", "purpose": "The program: `python readinglog.py add TITLE` adds a book"}])
    commands = [s["command"] for s in try_it.suggestions(ws)]
    assert "python readinglog.py list" in commands and "python readinglog.py add TITLE" in commands
    assert [s["placeholders"] for s in try_it.suggestions(ws) if s["command"].endswith("add TITLE")] == [True]


def test_an_unapplied_draft_is_not_a_source(tmp_path):
    ws = reading_log(tmp_path)
    applied_draft(ws, state="proposed", why="Run it with: python readinglog.py list")
    assert [s["command"] for s in try_it.suggestions(ws)] == ["python readinglog.py --help"]      # only the entry point


def test_with_nothing_written_down_the_programs_own_entry_point_is_offered(tmp_path):
    ws = reading_log(tmp_path)
    rows = try_it.suggestions(ws)
    assert [s["command"] for s in rows] == ["python readinglog.py --help"] and rows[0]["source"] == "the program itself"
    assert "usage: readinglog.py" in try_it.run(ws, rows[0]["command"])["stdout"]
    # A test file is never offered, and neither is a folder with no program in it.
    (tmp_path / "empty").mkdir()
    assert try_it.suggestions(Workspace(tmp_path / "empty")) == []


def test_the_overview_promises_the_card_only_when_it_is_there(tmp_path):
    from types import SimpleNamespace
    from runesmith.app.server import api_state
    studio = SimpleNamespace(ws=reading_log(tmp_path), worker=SimpleNamespace(snapshot=lambda: {}),
                             bus=SimpleNamespace(recent=[]))
    assert api_state(studio, {}, None)["try_ready"] is True
    (tmp_path / "bare").mkdir()
    bare = Workspace(tmp_path / "bare")
    bare.save_plan({"summary": "x", "milestones": [{"title": "Plan only", "done_when": "later"}]})
    studio.ws = bare
    assert api_state(studio, {}, None)["try_ready"] is False


# ---- J0-F20: files written to the project reach the practice copy before the next Try ----

LOG_BEGIN = '''import argparse, json
from pathlib import Path
data = Path("books.json")
books = json.loads(data.read_text()) if data.exists() else []
parser = argparse.ArgumentParser(prog="readinglog.py")
commands = parser.add_subparsers(dest="command", required=True)
commands.add_parser("list")
commands.add_parser("add").add_argument("title")
'''
LOG_DELETE = LOG_BEGIN + '''commands.add_parser("delete").add_argument("number", type=int)
'''
LOG_RUN = '''args = parser.parse_args()
if args.command == "add":
    books.append(args.title); data.write_text(json.dumps(books)); print("added", args.title)
elif args.command == "delete":
    if not 1 <= args.number <= len(books):
        raise SystemExit("Error: Book number %d does not exist." % args.number)
    print("deleted", books.pop(args.number - 1)); data.write_text(json.dumps(books))
else:
    print("\\n".join(f"{i}. {b}" for i, b in enumerate(books, 1)) or "No books yet")
'''
READING_LOG_V1, READING_LOG_V2 = LOG_BEGIN + LOG_RUN, LOG_DELETE + LOG_RUN


def log_project(tmp_path):
    (tmp_path / "readinglog.py").write_bytes(READING_LOG_V1.encode("utf-8"))
    (tmp_path / "books.json").write_text(json.dumps(["Emma"]), encoding="utf-8")
    return Workspace(tmp_path)


def write_delete_command(ws, by):
    """A draft that adds the delete command, written to the project the way the owner or an automatic apply does."""
    draft = ws.save_draft(title="Delete a book by its number", why="Adds delete", drafted_by="test",
                          files=[{"path": "readinglog.py", "content": READING_LOG_V2, "base": READING_LOG_V1}])
    assert ws.apply_draft(draft["id"], by=by)["ok"]
    return draft


@pytest.mark.parametrize("by", ["owner", "build"])
def test_a_draft_written_to_the_project_is_in_the_practice_copy_at_the_next_try(tmp_path, by):
    ws = log_project(tmp_path)
    made = try_it.run(ws, "python readinglog.py add Dune")                  # the practice copy: made now from the folder
    assert made["practice"]["state"] == "made" and made["exit_code"] == 0
    kept = try_it.run(ws, "python readinglog.py list")                      # nothing changed: the copy lasts, Dune is still there
    assert kept["practice"] == {"created_utc": made["practice"]["created_utc"], "state": "kept"}
    assert kept["stdout"].split() == ["1.", "Emma", "2.", "Dune"] and try_it.status(ws)["stale"] is False
    write_delete_command(ws, by)
    status = try_it.status(ws)
    assert status["stale"] is True and status["practice"]["created_utc"] == made["practice"]["created_utc"]   # the card can say so
    tried = try_it.run(ws, "python readinglog.py delete 1")                 # J0: "invalid choice: 'delete'" on the old copy
    assert tried["exit_code"] == 0 and tried["stdout"].strip() == "deleted Emma", tried["stderr"]
    assert tried["practice"]["state"] == "refreshed" and tried["practice"]["created_utc"] >= made["practice"]["created_utc"]
    assert try_it.run(ws, "python readinglog.py list")["stdout"].strip() == "No books yet"       # Dune (the old practice) is gone
    assert try_it.status(ws)["stale"] is False and try_it.status(ws)["practice"]["created_utc"] == tried["practice"]["created_utc"]
    assert json.loads((tmp_path / "books.json").read_text(encoding="utf-8")) == ["Emma"]                # the real folder untouched
    assert [e["data"].get("practice") for e in ws.ledger.events("try.ran")] == ["made", "kept", "refreshed", "kept"]


def test_a_draft_undone_or_a_file_changed_by_hand_also_refreshes_the_copy(tmp_path):
    ws = log_project(tmp_path)
    assert try_it.run(ws, "python readinglog.py list")["practice"]["state"] == "made"
    draft = write_delete_command(ws, "owner")
    assert try_it.run(ws, "python readinglog.py delete 1")["practice"]["state"] == "refreshed"
    assert ws.undo_draft(draft["id"])["ok"]
    after = try_it.run(ws, "python readinglog.py delete 1")
    assert after["practice"]["state"] == "refreshed" and after["exit_code"] != 0 and "invalid choice" in after["stderr"]
    (tmp_path / "readinglog.py").write_bytes(READING_LOG_V2.encode("utf-8"))         # the owner's own editor
    assert try_it.run(ws, "python readinglog.py delete 1")["exit_code"] == 0
    # A run in the real folder is not a practice run: it says nothing of the copy and the copy is not touched by it.
    real = try_it.run(ws, "python readinglog.py list", real=True)
    assert real["practice"] is None and real["exit_code"] == 0


def test_a_practice_copy_made_before_the_folder_was_recorded_is_made_again_once(tmp_path):
    ws = log_project(tmp_path)
    try_it.reset_practice(ws)
    record = json.loads((ws.home / "try" / "PRACTICE.json").read_text(encoding="utf-8"))
    record.pop("files_digest")                                              # a copy of an earlier build
    (ws.home / "try" / "PRACTICE.json").write_text(json.dumps(record), encoding="utf-8")
    assert try_it.status(ws)["stale"] is True
    assert try_it.run(ws, "python readinglog.py list")["practice"]["state"] == "refreshed"
    assert try_it.run(ws, "python readinglog.py list")["practice"]["state"] == "kept"


def test_a_folder_that_cannot_be_read_as_a_snapshot_leaves_the_copy_as_it_is(tmp_path, monkeypatch):
    ws = log_project(tmp_path)
    assert try_it.run(ws, "python readinglog.py add Dune")["practice"]["state"] == "made"

    def refuse(_ws):
        raise try_it.SnapshotUnsupported("too large")
    monkeypatch.setattr(try_it, "collect_snapshot", refuse)
    assert try_it.status(ws)["stale"] is False
    kept = try_it.run(ws, "python readinglog.py list")
    assert kept["practice"]["state"] == "kept" and "Dune" in kept["stdout"]


def test_the_route_tells_the_card_when_the_copy_was_made_and_that_the_folder_changed(tmp_path):
    from types import SimpleNamespace
    from runesmith.app.server import api_try, api_try_run
    ws = log_project(tmp_path)
    studio = SimpleNamespace(ws=ws)
    assert api_try(studio, {}, None)["practice"] is None and api_try(studio, {}, None)["stale"] is False
    ran = api_try_run(studio, {}, {"command": "python readinglog.py list", "real": False})
    assert api_try(studio, {}, None)["practice"]["created_utc"] == ran["practice"]["created_utc"]
    write_delete_command(ws, "owner")
    assert api_try(studio, {}, None)["stale"] is True

