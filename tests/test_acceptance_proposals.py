"""Acceptance checks a non-programmer can approve (gap G1 from out-of-box journey R1)."""

from __future__ import annotations

import json
import pytest

from runesmith.app.acceptance_proposals import acceptance_file, approve, discard, dry_run, propose, status, validate
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import Workspace, WorkspaceError

GOOD = '''import os, subprocess, sys, tempfile, unittest

class AddBook(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "readinglog", *args], cwd=os.getcwd(), capture_output=True, text=True)

    def test_a_book_can_be_added(self):
        with tempfile.TemporaryDirectory() as folder:
            data = os.path.join(folder, "log.json")
            self.assertEqual(self.run_cli("--file", data, "add", "--title", "T", "--author", "A", "--finished", "2026-01-01").returncode, 0)

    def test_an_impossible_date_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            data = os.path.join(folder, "log.json")
            result = self.run_cli("--file", data, "add", "--title", "T", "--author", "A", "--finished", "2026-02-30")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(os.path.exists(data))
'''
ANSWER = {"checks": [{"test": "test_a_book_can_be_added", "says": "You can add a book with its title, author and date."},
                     {"test": "test_an_impossible_date_is_refused", "says": "A date that does not exist is refused and nothing is saved."}],
          "assumes": ["The command is run as python -m readinglog with --file for the saved data."], "code": GOOD}


def workspace(tmp_path, answers=()):
    ws = Workspace(tmp_path)
    ws.save_plan({"summary": "Reading log", "milestones": [
        {"title": "Add a book", "detail": "python -m readinglog add --title T --author A --finished YYYY-MM-DD",
         "done_when": "A valid book is stored; an impossible date is refused.", "status": "open"}]})
    config = ws.config()
    config["instruments"]["offline"] = {"kind": "scripted", "answers": list(answers)}
    config["roles"]["plan"] = ["offline"]
    ws.save_config(config)
    return ws


def test_validation_refuses_what_an_owner_should_not_have_to_catch():
    assert validate(ANSWER)["checks"][1]["says"].startswith("A date that does not exist")
    for broken, why in [
        (dict(ANSWER, code=GOOD.replace("import os,", "import socket, os,")), "network"),
        (dict(ANSWER, code="import pytest\n\ndef test_x():\n    assert True\n"), "unittest"),
        (dict(ANSWER, code=GOOD + "\n    def test_unexplained(self):\n        pass\n"), "plain sentence"),
        (dict(ANSWER, checks=ANSWER["checks"] + [{"test": "test_missing", "says": "x"}]), "not a test"),
        (dict(ANSWER, code="import unittest\nclass A(unittest.TestCase):\n    def test_a(self)\n        pass\n"), "not valid Python"),
        (dict(ANSWER, assumes=["x" * 301]), "assumptions"),
        (dict(ANSWER, assumes="the output format"), "assumptions"),
    ]:
        with pytest.raises(WorkspaceError, match=why):
            validate(broken)


def test_a_proposal_is_approved_in_plain_words_and_frozen_with_its_provenance(tmp_path):
    ws = workspace(tmp_path, [ANSWER])
    proposal = propose(ws, ws.router(), "m1")
    assert [c["test"] for c in proposal["checks"]] == ["test_a_book_can_be_added", "test_an_impossible_date_is_refused"]
    assert not acceptance_file(ws, "m1").exists()                      # nothing is used before the owner approves
    assert status(ws)["m1"]["proposal"]["id"] == proposal["id"]
    assert propose(ws, ws.router(), "m1")["id"] == proposal["id"]      # an unchanged request reuses the waiting answer
    approve(ws, "m1", proposal["id"])
    text = acceptance_file(ws, "m1").read_text(encoding="utf-8")
    assert text.startswith("# Owner acceptance for milestone m1. Proposed by ") and "approved by the owner" in text
    assert GOOD.strip() in text
    approved = status(ws)["m1"]["approved"]
    assert approved["provenance"] == "model-proposed, owner-approved" and len(approved["checks"]) == 2
    with pytest.raises(WorkspaceError, match="not waiting"):
        approve(ws, "m1", proposal["id"])
    assert list(ws.ledger.events("acceptance.proposed")) and list(ws.ledger.events("acceptance.approved"))
    assert ws.ledger.verify()["ok"]


def test_replacing_approved_checks_needs_a_reason_and_keeps_the_old_file(tmp_path):
    second = dict(ANSWER, checks=ANSWER["checks"][:1],
                  code=GOOD.split("    def test_an_impossible_date_is_refused")[0])
    ws = workspace(tmp_path, [ANSWER, second])
    router = ws.router()                                                # scripted answers replay per router
    first = propose(ws, router, "m1")
    approve(ws, "m1", first["id"])
    ws.update_settings({"read_notes": False})                           # a changed packet asks again
    ws.set_brief(text="# Reading log\n\nAlso keep it simple.\n")
    newer = propose(ws, router, "m1")
    with pytest.raises(WorkspaceError, match="already has acceptance checks"):
        approve(ws, "m1", newer["id"])
    with pytest.raises(WorkspaceError, match="Say why"):
        approve(ws, "m1", newer["id"], replace=True)
    approve(ws, "m1", newer["id"], replace=True, reason="the date check moves to its own milestone")
    assert len(status(ws)["m1"]["approved"]["checks"]) == 1
    assert list((ws.home / "acceptance").glob("m1.replaced-*.py.txt"))
    record = json.loads((ws.home / "acceptance-proposals" / "m1.json").read_text(encoding="utf-8"))
    assert [p["state"] for p in record["proposals"]] == ["replaced", "approved"]   # the record says which file decides


def test_discarded_proposals_are_kept_but_never_used(tmp_path):
    ws = workspace(tmp_path, [ANSWER])
    proposal = propose(ws, ws.router(), "m1")
    discard(ws, "m1", proposal["id"], reason="checks the wrong command")
    assert "m1" not in status(ws) and not acceptance_file(ws, "m1").exists()


def test_the_worker_accepts_the_job(tmp_path):
    ws = workspace(tmp_path)
    worker = Worker(ws, EventBus())
    assert worker.enqueue("propose_acceptance", milestone="m1")["kind"] == "propose_acceptance"


def test_the_owner_sees_what_the_checks_assume_and_how_they_fare_on_todays_project(tmp_path):
    ws = workspace(tmp_path, [ANSWER])
    assert dry_run(ws, GOOD)["verdict"] == "not_run"                    # executing project code stays the owner's switch
    ws.update_settings({"build_steps": True})
    proposal = propose(ws, ws.router(), "m1")
    assert proposal["assumes"] == ANSWER["assumes"]
    assert proposal["dry_run"]["verdict"] == "fails_now"                # nothing is built yet, so a check fails
    assert status(ws)["m1"]["proposal"]["dry_run"]["verdict"] == "fails_now"
    (tmp_path / "readinglog.py").write_text(                            # a project that already does what is checked
        "import sys\nsys.exit(2 if '2026-02-30' in sys.argv else 0)\n", encoding="utf-8")
    assert dry_run(ws, GOOD)["verdict"] == "passes_now"
    assert dry_run(ws, GOOD.replace("def test_", "def helper_"))["verdict"] == "broken"   # no test ran
    assert not list((ws.home / "acceptance-proposals" / "dry-runs").iterdir())           # trial copies are removed


REVISED = {"checks": [{"test": "test_months_are_counted", "says": "The months command lists 2026-01 for a book finished in January 2026."}],
           "assumes": [], "code": '''import os, subprocess, sys, tempfile, unittest

class Months(unittest.TestCase):
    def test_months_are_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            data = os.path.join(folder, "log.json")
            subprocess.run([sys.executable, "-m", "readinglog", "--file", data, "add", "--title", "T", "--author", "A",
                            "--finished", "2026-01-05"], cwd=os.getcwd())
            result = subprocess.run([sys.executable, "-m", "readinglog", "--file", data, "months"], cwd=os.getcwd(),
                                    capture_output=True, text=True)
            self.assertIn("2026-01", result.stdout)
'''}


def built_already(tmp_path, answers):
    ws = workspace(tmp_path, answers)
    ws.update_settings({"build_steps": True})
    (tmp_path / "readinglog.py").write_text("import sys\nsys.exit(2 if '2026-02-30' in sys.argv else 0)\n", encoding="utf-8")
    return ws


def test_checks_that_already_pass_are_revised_once_with_what_the_trial_found(tmp_path):
    ws = built_already(tmp_path, [ANSWER, REVISED])
    proposal = propose(ws, ws.router(), "m1")
    assert [c["test"] for c in proposal["checks"]] == ["test_months_are_counted"]
    assert proposal["dry_run"]["verdict"] == "fails_now"
    assert proposal["revision"]["after"] == "passes_now" and len(proposal["revision"]["first_checks"]) == 2


def test_a_failed_revision_keeps_the_first_proposal_and_its_warning(tmp_path):
    ws = built_already(tmp_path, [ANSWER, {"checks": [], "code": "not python ("}])
    proposal = propose(ws, ws.router(), "m1")
    assert proposal["dry_run"]["verdict"] == "passes_now" and proposal["checks"] == ANSWER["checks"]
    assert "not valid Python" in proposal["revision"]["error"]


def test_approval_publishes_the_sentences_and_maps_failures_to_them(tmp_path):
    from runesmith.app.acceptance_contracts import expectations, publish_expectations
    ws = workspace(tmp_path, [ANSWER, REVISED])
    publish_expectations(ws, "m1", [{"id": "quick", "description": "Adding a book takes under a second."}], "owner")
    router = ws.router()
    approve(ws, "m1", propose(ws, router, "m1")["id"])
    ids = [c["id"] for c in expectations(ws, "m1")["criteria"]]
    assert ids == ["quick", "check.test_a_book_can_be_added", "check.test_an_impossible_date_is_refused", "assumes.1"]
    namespace = {"__name__": "owner_acceptance_0"}
    exec(acceptance_file(ws, "m1").read_text(encoding="utf-8"), namespace)
    assert namespace["AddBook"].PUBLIC_CRITERIA["test_a_book_can_be_added"] == ["check.test_a_book_can_be_added"]
    ws.set_brief(text="# Reading log\n\nMonths too.\n")                  # a changed packet asks again
    approve(ws, "m1", propose(ws, router, "m1")["id"], replace=True, reason="months replace the add checks")
    assert [c["id"] for c in expectations(ws, "m1")["criteria"]] == ["quick", "check.test_months_are_counted"]


HIDDEN = {"checks": [{"test": "test_counts", "says": "The months command shows how many books were finished each month."},
                     {"test": "test_empty", "says": "With no books, the months command says “No books yet”."}],
          "assumes": [], "code": '''import os, subprocess, sys, tempfile, unittest

class Months(unittest.TestCase):
    def run_cli(self, data, *args):
        return subprocess.run([sys.executable, "-m", "readinglog", "--file", data, *args], capture_output=True, text=True)

    def test_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            data = os.path.join(folder, "log.json")
            self.run_cli(data, "add", "--title", "Dune", "--author", "Herbert", "--finished", "2025-01-05")
            out = self.run_cli(data, "months").stdout
            self.assertIn("Dune", self.run_cli(data, "list").stdout, "the book was not stored")
            self.assertTrue(out.splitlines()[0].startswith("2025-01"))
            self.assertIn("2025-01: 1", out, "missing month line")

    def test_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn("No books yet", self.run_cli(os.path.join(folder, "log.json"), "months").stdout)
'''}


def test_exact_text_a_check_requires_but_its_sentence_does_not_say_is_found():
    checks = validate(HIDDEN)["checks"]
    assert checks[0]["unstated"] == ["2025-01: 1"]                     # not the input data, not the failure message
    assert "unstated" not in checks[1]                                  # stated in its sentence


def test_unstated_text_asks_for_one_revision_and_is_published_if_it_stays(tmp_path):
    from runesmith.app.acceptance_contracts import expectations
    ws = workspace(tmp_path, [HIDDEN, HIDDEN])
    proposal = propose(ws, ws.router(), "m1")                          # checking is off: no trial, yet text is found
    assert proposal["dry_run"]["verdict"] == "not_run" and proposal["revision"]["after"] == "unstated_text"
    assert status(ws)["m1"]["proposal"]["checks"][0]["unstated"] == ["2025-01: 1"]
    approve(ws, "m1", proposal["id"])
    counts = next(c for c in expectations(ws, "m1")["criteria"] if c["id"] == "check.test_counts")
    assert counts["description"].endswith("It requires the exact text: “2025-01: 1”.")


def test_the_checker_role_can_use_its_own_model_and_otherwise_borrows_the_planners(tmp_path):
    ws = workspace(tmp_path, [])                                       # the planner has no answers to give
    config = ws.config()
    config["instruments"]["checker"] = {"kind": "scripted", "answers": [ANSWER]}
    config["roles"]["acceptance"] = ["checker"]
    ws.save_config(config)
    assert ws.ready()["acceptance"] and propose(ws, ws.router(), "m1")["checks"] == ANSWER["checks"]
    config["roles"]["acceptance"] = []
    ws.save_config(config)
    assert ws.ready()["acceptance"] and ws.router().roles["acceptance"] == ws.router().roles["plan"]
