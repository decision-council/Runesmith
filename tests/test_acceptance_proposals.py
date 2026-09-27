"""Acceptance checks a non-programmer can approve (gap G1 from out-of-box journey R1)."""

from __future__ import annotations

import pytest

from runesmith.app.acceptance_proposals import acceptance_file, approve, discard, propose, status, validate
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
          "code": GOOD}


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


def test_discarded_proposals_are_kept_but_never_used(tmp_path):
    ws = workspace(tmp_path, [ANSWER])
    proposal = propose(ws, ws.router(), "m1")
    discard(ws, "m1", proposal["id"], reason="checks the wrong command")
    assert "m1" not in status(ws) and not acceptance_file(ws, "m1").exists()


def test_the_worker_accepts_the_job(tmp_path):
    ws = workspace(tmp_path)
    worker = Worker(ws, EventBus())
    assert worker.enqueue("propose_acceptance", milestone="m1")["kind"] == "propose_acceptance"
