"""A limited fallback is evidence about the tests it ran, not the whole suite."""
import subprocess

import pytest

from runesmith import envmap
from runesmith.app.workspace import Workspace


@pytest.mark.parametrize("stderr", [
    "C:\\Python\\python.exe: No module named pytest\n",
    "/usr/bin/python: No module named 'pytest'\n",
])
def test_missing_pytest_has_explicit_fallback_scope(tmp_path, monkeypatch, stderr):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return subprocess.CompletedProcess(args, 1, "", stderr)
        return subprocess.CompletedProcess(args, 0, "", "Ran 1 test in 0.01s\n\nOK\n")

    monkeypatch.setattr(envmap.subprocess, "run", run)
    probe = envmap.probe_pytest(tmp_path, in_place=True, python=stderr.split(": No module named")[0])
    assert len(calls) == 2 and calls[1][1:3] == ["-m", "unittest"]
    assert probe["runner"] == "unittest" and probe["passed"] == 1
    assert probe["pytest_available"] is False
    assert probe["suite_scope"] == "unittest_discovery_only"


@pytest.mark.parametrize("stdout,stderr", [
    ("", "ModuleNotFoundError: No module named pytest_plugin\n"),
    ("", "ModuleNotFoundError: No module named pytest\n"),
    ("", "Traceback (most recent call last):\npython: No module named pytest\n"),
    ("1 error during collection", "python: No module named pytest\n"),
])
def test_collection_failure_is_not_a_missing_runner(tmp_path, monkeypatch, stdout, stderr):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 2, stdout, stderr)

    monkeypatch.setattr(envmap.subprocess, "run", run)
    probe = envmap.probe_pytest(tmp_path, in_place=True)
    assert all(args[1:3] == ["-m", "pytest"] for args in calls)
    assert probe["runner"] == "pytest" and probe["exit_code"] == 2


def test_real_mixed_suite_never_claims_all_tests_pass_without_pytest(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("answer = 42\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "test_mixed.py").write_text(
        "import unittest\nfrom app import answer\n"
        "class Unit(unittest.TestCase):\n"
        "    def test_answer(self): self.assertEqual(answer, 42)\n"
        "def test_pytest_only():\n    assert False, 'must not be called a passing test'\n",
        encoding="utf-8")
    real_run = subprocess.run

    def no_pytest(args, **kwargs):
        if args[1:3] == ["-m", "pytest"]:
            return subprocess.CompletedProcess(args, 1, "", f"{args[0]}: No module named pytest\n")
        return real_run(args, **kwargs)

    monkeypatch.setattr(envmap.subprocess, "run", no_pytest)
    result = envmap.python_object(tmp_path, probe=True, scratch=tmp_path.parent / "scratch")
    assert result["probe"]["passed"] == 1 and result["probe"]["exit_code"] == 0
    rungs = {row["rung"]: row["status"] for row in result["ladder"]}
    assert rungs["tests_collect"] == rungs["tests_pass"] == rungs["fast_suite"] == "unknown"
    for row in result["objectives"]:
        if row["metric"] in ("test_pass_rate", "test_suite_seconds"):
            assert row["value"] is None and row["evidence"] == "unknown"


@pytest.mark.parametrize("probe,measured,expected", [
    ({"unavailable": "no runner"}, "2026-10-02T01:00:01Z", "probe_unavailable"),
    ({"unavailable": "no runner"}, "2026-10-02T01:00:00Z", "probe_unavailable"),
    ({"unavailable": "no runner"}, "2026-10-02T00:59:59Z", "green"),
    ({"runner": "unittest", "exit_code": 0}, "2026-10-02T01:00:01Z", "unittest_passed"),
    ({"runner": "unittest", "exit_code": 0}, "2026-10-02T01:00:00Z", "unittest_passed"),
    ({"runner": "unittest", "exit_code": 1}, "2026-10-02T01:00:01Z", "failing"),
    ({"runner": "pytest", "exit_code": 0}, "2026-10-02T01:00:01Z", "green"),
    ({"error": "test run timed out"}, "2026-10-02T01:00:01Z", "timed_out"),
    ({"error": "unittest discovery could not run", "exit_code": 1}, "2026-10-02T01:00:01Z", "error_without_failures"),
])
def test_latest_probe_does_not_inherit_a_stale_green(tmp_path, monkeypatch, probe, measured, expected):
    ws = object.__new__(Workspace)
    ws.home = tmp_path
    monkeypatch.setattr(ws, "proposal_state", lambda: {})
    monkeypatch.setattr("runesmith.proposals.list_proposals", lambda _: [])
    work = {"utc": "2026-10-02T01:00:00Z", "objects": {"repo": "green"}}
    mapped = {"objects": [{"name": "repo", "measured_utc": measured, "probe": probe}]}
    assert ws.object_statuses(work, mapped)["repo"] == expected


def test_newer_application_is_not_overridden_by_old_probe(tmp_path, monkeypatch):
    ws = object.__new__(Workspace)
    ws.home, ws.root = tmp_path, tmp_path
    monkeypatch.setattr(ws, "proposal_state", lambda: {"fix": {"state": "applied", "utc": "2026-10-02T01:00:02Z"}})
    monkeypatch.setattr("runesmith.proposals.list_proposals", lambda _: [{"key": "fix", "repo": str(tmp_path / "repo")}])
    work = {"utc": "2026-10-02T01:00:00Z", "objects": {"repo": "green"}}
    mapped = {"objects": [{"name": "repo", "measured_utc": "2026-10-02T01:00:01Z", "probe": {"unavailable": "no tests"}}]}
    assert ws.object_statuses(work, mapped)["repo"] == "fix_applied"


def test_equal_timestamp_pytest_success_does_not_promote_a_round_failure(tmp_path, monkeypatch):
    ws = object.__new__(Workspace)
    ws.home = tmp_path
    monkeypatch.setattr(ws, "proposal_state", lambda: {})
    monkeypatch.setattr("runesmith.proposals.list_proposals", lambda _: [])
    work = {"utc": "2026-10-02T01:00:00Z", "objects": {"repo": "failing"}}
    mapped = {"objects": [{"name": "repo", "measured_utc": work["utc"], "probe": {"exit_code": 0}}]}
    assert ws.object_statuses(work, mapped)["repo"] == "failing"


@pytest.mark.parametrize("code,output,key", [
    (0, "Ran 0 tests in 0.00s\nOK", "unavailable"),
    (5, "Ran 0 tests in 0.00s\nNO TESTS RAN", "unavailable"),
    (0, "Unexpected runner output", "unavailable"),
    (1, "ImportError: Start directory is not importable", "error"),
])
def test_fallback_absence_and_discovery_errors_keep_scope(tmp_path, monkeypatch, code, output, key):
    monkeypatch.setattr(envmap.subprocess, "run", lambda args, **kw:
                        subprocess.CompletedProcess(args, code, "", output))
    result = envmap._probe_unittest(tmp_path, {}, timeout_s=1, python="python")
    assert result["runner"] == "unittest" and result["suite_scope"] == "unittest_discovery_only"
    assert result["pytest_available"] is False and result[key]
    if key == "error":
        assert result["exit_code"] == 1 and result["diagnostic"] == output
        assert "unavailable" not in result


def test_fallback_timeout_keeps_scope(tmp_path, monkeypatch):
    def timeout(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 1)
    monkeypatch.setattr(envmap.subprocess, "run", timeout)
    result = envmap._probe_unittest(tmp_path, {}, timeout_s=1, python="python")
    assert result["runner"] == "unittest" and result["suite_scope"] == "unittest_discovery_only"
    assert result["error"] == "test run timed out" and "exit_code" not in result


def test_cached_fallback_is_rescoped_without_reprobing_or_mutating_prior_map(tmp_path, monkeypatch):
    import copy
    (tmp_path / "app.py").write_text("answer = 42\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text("", encoding="utf-8")
    before = envmap.build_environment_map(tmp_path)
    obj = before["objects"][0]
    obj["probe"] = {"runner": "unittest", "collected": 1, "passed": 1, "exit_code": 0, "suite_seconds": .1}
    obj["measured_utc"] = "2026-10-02T01:00:00Z"
    for rung in obj["ladder"]:
        if rung["rung"] in ("tests_collect", "tests_pass", "fast_suite"):
            rung["status"] = "achieved"
    for row in obj["objectives"]:
        if row["metric"] in ("test_pass_rate", "test_suite_seconds"):
            row.update(value=1, evidence="observed", band="optimal")
    original = copy.deepcopy(before)
    monkeypatch.setattr(envmap, "probe_pytest", lambda *a, **kw: pytest.fail("Must not re-run a retained probe"))
    mapped = envmap.build_environment_map(tmp_path, previous=before)
    assert before == original
    retained = mapped["objects"][0]
    assert retained["probe"] == obj["probe"] and retained["measured_utc"] == obj["measured_utc"]
    assert {r["status"] for r in retained["ladder"] if r["rung"] in
            ("tests_collect", "tests_pass", "fast_suite")} == {"unknown"}
    assert all(row["value"] is None for row in retained["objectives"]
               if row["metric"] in ("test_pass_rate", "test_suite_seconds"))
