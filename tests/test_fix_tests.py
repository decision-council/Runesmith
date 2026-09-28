"""Fix the failing tests (journey J3): the project's own tests, frozen, decide; builders change only the code."""
import json
import shutil

import pytest

from runesmith.app import building
from runesmith.app.fix_tests import code_paths, offer, project_test_files, start
from runesmith.app.workspace import Workspace, WorkspaceError
from test_studio import scripted

BROKEN = "def total(a, b):\n    return a - b\n"
FIXED = "def total(a, b):\n    return a + b\n"
TESTS = ("import unittest\nfrom shop import total\n\n\nclass Totals(unittest.TestCase):\n"
         "    def test_adds(self):\n        self.assertEqual(total(2, 3), 5)\n\n"
         "    def test_zero(self):\n        self.assertEqual(total(0, 0), 0)\n")


def project(tmp_path):
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "__init__.py").write_text(BROKEN, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_shop.py").write_text(TESTS, encoding="utf-8")
    (tmp_path / "README.md").write_text("# shop\n", encoding="utf-8")
    return Workspace(tmp_path)


def acceptance_on(ws, milestone, stage):
    checks = ws.home / "acceptance" / f"{milestone}.py"
    return building._run_checks(stage, json.dumps([str(checks)]), stage.parent / "log.txt", timeout_s=60)


def copy_of(ws, tmp_path, name):
    stage = tmp_path.parent / f"{tmp_path.name}-{name}" / "project"
    shutil.copytree(ws.root, stage, ignore=shutil.ignore_patterns(".runesmith"))
    return stage


def test_the_frozen_tests_decide_and_changing_the_tests_cannot_pass_them(tmp_path):
    ws = project(tmp_path)
    assert project_test_files(tmp_path) == ["tests/__init__.py", "tests/test_shop.py"] and code_paths(tmp_path) == ["shop"]
    started = start(ws)
    milestone = started["milestone"]
    assert started["frozen_files"] == 2 and next(m for m in ws.plan()["milestones"] if m["id"] == milestone)
    today = copy_of(ws, tmp_path, "today")
    result = acceptance_on(ws, milestone, today)
    assert not result["ok"] and result["ran"] == 2 and result["failures"] == 1
    cheated = copy_of(ws, tmp_path, "cheat")                          # rewrite the tests instead of the code
    (cheated / "tests" / "test_shop.py").write_text("import unittest\n\n\nclass T(unittest.TestCase):\n"
                                                    "    def test_nothing(self):\n        pass\n", encoding="utf-8")
    assert not acceptance_on(ws, milestone, cheated)["ok"]
    fixed = copy_of(ws, tmp_path, "fixed")
    (fixed / "shop" / "__init__.py").write_text(FIXED, encoding="utf-8")
    assert acceptance_on(ws, milestone, fixed)["ok"]
    failure = next(d for d in result["failure_details"])
    assert failure["criteria"] == ["tests.all"]                        # reported by its sentence, not its assertion


def test_automatic_apply_is_limited_to_the_code_only_when_the_owner_allows_it(tmp_path):
    ws = project(tmp_path)
    start(ws)
    assert not ws.settings()["build_apply"]
    start(ws, allow_apply=True)
    settings = ws.settings()
    assert settings["build_steps"] and settings["build_apply"] and settings["build_paths"] == ["shop"]
    with pytest.raises(WorkspaceError, match="automatically"):
        start(ws, allow_apply="yes")


def test_a_build_fixes_the_code_and_is_applied_when_the_frozen_tests_pass(tmp_path):
    ws = project(tmp_path)
    scripted(ws, [{"title": "Fix", "files": [{"path": "shop/__init__.py", "content": FIXED}]}], roles=("plan",))
    start(ws, allow_apply=True)
    result = building.build_step(ws, ws.router())
    assert result.get("advanced") is True, result["summary"]
    assert (tmp_path / "shop" / "__init__.py").read_text(encoding="utf-8") == FIXED
    assert (tmp_path / "tests" / "test_shop.py").read_text(encoding="utf-8") == TESTS


def test_the_overview_offers_it_when_the_map_shows_failing_tests(tmp_path):
    ws = project(tmp_path)
    assert offer(ws) is None                                            # nothing mapped yet
    ws.map_environment(probe=True)
    shown = offer(ws)
    assert shown["object"] == tmp_path.name and shown["code_paths"] == ["shop"] and shown["tests_green"] == 0.5


def test_no_tests_no_offer_to_freeze(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="No test files"):
        start(ws)


def test_the_studio_route_allows_automatic_apply_only_with_an_explicit_true(tmp_path):
    from types import SimpleNamespace
    from runesmith.app.server import api_fix_tests, api_fix_tests_start
    from runesmith.app.worker import EventBus
    ws = project(tmp_path)
    studio = SimpleNamespace(ws=ws, bus=EventBus())
    assert api_fix_tests(studio, {}, None) == {"offer": None}
    assert api_fix_tests_start(studio, {}, {"allow_apply": "yes"})["allow_apply"] is False
    assert not ws.settings()["build_apply"]


def test_a_round_measures_a_project_the_repair_organ_cannot_serve_and_the_fix_is_offered(tmp_path):
    # J3: a flat layout (no src/), or no pytest installed. With test runs allowed, the round runs the project's tests
    # with Python's own unittest and says how many fail; the Overview then offers Fix the failing tests.
    from runesmith.app.worker import EventBus, Worker
    ws = project(tmp_path)
    scripted(ws, [], roles=("repair",))
    ws.update_settings({"onboarded": True, "probe_tests": False})
    worker = Worker(ws, EventBus())
    worker._job_round()
    assert offer(ws) is None                                            # not allowed to run the tests: no claim
    assert any("has not run" in line["text"] for line in worker.snapshot()["lines"])
    ws.update_settings({"probe_tests": True})
    worker._job_round()
    shown = offer(ws)
    assert shown and shown["tests_green"] == 0.5 and shown["code_paths"] == ["shop"]
    lines = [line["text"] for line in worker.snapshot()["lines"]]
    assert any("1 of 2 tests fail" in text and "keeps its code at the top" in text for text in lines)
    assert "Nothing new to work on this round." not in lines[-3:]                   # J3-F6: no contradiction
    assert list(ws.ledger.events("studio.round"))[-1]["data"]["outcome"] == "tests fail: fix offered"


def test_a_milliner_gateway_on_this_computer_is_not_called_a_local_model(tmp_path):
    # J3-F4: the gateway's address is local, the models behind it are not.
    ws = Workspace(tmp_path)
    ws.save_instrument("gate", {"kind": "milliner", "model": "gemini:x", "base_url": "http://127.0.0.1:8765"},
                       key_value="token-not-shown", roles=["plan"])
    assert next(i for i in ws.inference()["instruments"] if i["name"] == "gate")["local"] is False
