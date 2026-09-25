"""Proposals: judge-accepted fixes become patches that apply cleanly to the untouched repository."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from runesmith import cli
from runesmith.instruments import Router
from runesmith.kaizen.improve import FixtureInstrument
from runesmith.loop import run_loop
from runesmith.proposals import list_proposals, write_proposals

from test_kernel import make_repo
from test_loop import HINTS


def _served_home(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    repo = make_repo(tmp_path)
    opportunity = {"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"],
                   "judge_tests": ["tests/test_ops.py"], "issue": "add() returns a wrong value"}
    router = Router({"y": FixtureInstrument(HINTS)}, {"repair": "y"}, backoff_s=(0,), sleep=lambda s: None)
    run_loop(home=home, opportunities=[opportunity], seed="proposals-test", router=router, min_experience=99)
    return home, repo


def test_proposals_list_the_verified_fix_as_a_diff(tmp_path, capsys):
    home, repo = _served_home(tmp_path)
    found = list_proposals(home)
    assert len(found) == 1
    assert found[0]["files"] == ["src/calc/ops.py"]
    assert "-    return a - b" in found[0]["diff"] and "+    return a + b" in found[0]["diff"]
    assert "return a - b" in (repo / "src" / "calc" / "ops.py").read_text(encoding="utf-8")   # never applied by itself
    cli.main(["--home", str(home), "proposals"])
    assert "1 judge-accepted proposal(s)" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_written_patch_applies_with_git(tmp_path):
    home, repo = _served_home(tmp_path)
    [patch] = write_proposals(home, tmp_path / "patches")
    check = subprocess.run(["git", "apply", "--check", str(patch)], cwd=repo, capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    subprocess.run(["git", "apply", str(patch)], cwd=repo, check=True)
    assert "return a + b" in (repo / "src" / "calc" / "ops.py").read_text(encoding="utf-8")
