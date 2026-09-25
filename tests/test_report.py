"""The REPORT.md dashboard is a faithful, reproducible projection of the home's records."""

from __future__ import annotations

from runesmith import cli, generations
from runesmith.instruments import Router
from runesmith.kaizen.improve import FixtureInstrument
from runesmith.loop import run_loop
from runesmith.report import build_report, write_report

from test_kernel import make_repo
from test_loop import HINTS


def test_report_on_a_fresh_home_says_unknown(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    text = build_report(home)
    assert "Active generation **gen-" in text
    assert "Ledger: intact" in text
    assert "No opportunities recorded yet" in text
    assert "No trials yet." in text
    assert "No attention state yet" in text


def test_report_reflects_work_and_is_reproducible(tmp_path, capsys):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    repo = make_repo(tmp_path)
    opportunity = {"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"],
                   "judge_tests": ["tests/test_ops.py"], "issue": "add() returns a wrong value"}
    router = Router({"y": FixtureInstrument(HINTS)}, {"repair": "y"}, backoff_s=(0,), sleep=lambda s: None)
    run_loop(home=home, opportunities=[opportunity] * 3, seed="report-test", router=router, min_experience=99)
    active = generations.active(home)
    text = build_report(home)
    assert f"| {active} (active) |" in text
    assert "| repair_yield | 1.0 | optimal |" in text          # no world-class bar is set for yield
    assert f"| {active} | 3 | 3 | 1.00 |" in text
    assert "All statuses: {" in text
    assert "### By model" in text and "| fixture |" in text
    assert "Mode **HEALTHY**: 15% of steps go to Kaizen." in text
    assert "Drift chart: collecting its baseline (3/30 outcomes)." in text
    assert build_report(home) == text                 # same records, same report
    path = write_report(home)
    assert path.read_text(encoding="utf-8") == text
    cli.main(["--home", str(home), "report"])
    assert "Runesmith report" in capsys.readouterr().out
