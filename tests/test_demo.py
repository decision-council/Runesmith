"""`runesmith demo` shows the whole loop offline and never touches directories it did not create."""

from __future__ import annotations

import pytest

from runesmith import cli
from runesmith.demo import MARKER, run_demo, write_workspace
from runesmith.ledger import Ledger


def test_offline_demo_moves_the_band_and_records_everything(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    lines: list[str] = []
    summary = run_demo(home, out=lines.append)
    assert summary["opportunities"] == 3 and summary["served"] == 3 and summary["repaired"] == 3
    assert summary["before"]["band"] == "bad" and summary["before"]["value"] == 0.25
    assert summary["after"]["band"] == "optimal" and summary["after"]["value"] == 1.0
    assert any("scripted stand-in" in line for line in lines)          # offline is labelled as such
    assert (home / "REPORT.md").exists()
    assert Ledger(home / "ledger.jsonl").verify()["ok"]
    assert (home / "demo-workspace" / MARKER).exists()


def test_demo_refuses_to_overwrite_a_directory_it_did_not_create(tmp_path):
    foreign = tmp_path / "demo-workspace"
    foreign.mkdir()
    (foreign / "precious.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(SystemExit):
        write_workspace(foreign)
    assert (foreign / "precious.txt").read_text(encoding="utf-8") == "keep me"


def test_kaizen_demo_replays_sr5_self_improvement_end_to_end(tmp_path):
    """Struggle -> diagnosis -> SR5's model-authored change -> held-out qualification -> trial -> activation."""
    import json
    from runesmith import generations
    from runesmith.demo_kaizen import B_ANSWER, run_kaizen_demo
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    g0 = generations.active(home)
    lines: list[str] = []
    result = run_kaizen_demo(home, out=lines.append)
    assert result["first"] == {"strict_successes": 0, "served": 16}          # g0 gives up after bad navigation
    assert result["kaizen"]["decision"] == "frozen_candidate"
    assert result["kaizen"]["target"]["family"] == "navigation_output_failure"
    assert result["trial"]["decision"] == "activate"
    assert result["active"] == result["candidate"] != g0
    organ = (home / "generations" / result["candidate"] / "organs" / "repair.py").read_text(encoding="utf-8")
    assert organ == json.loads(B_ANSWER.read_text(encoding="utf-8"))["module_source"]   # exactly SR5's B
    assert Ledger(home / "ledger.jsonl").verify()["ok"]
    assert any("generation.activated" == e["kind"] for e in Ledger(home / "ledger.jsonl"))
