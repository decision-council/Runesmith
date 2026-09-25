"""The steward: finds work across a workspace, never re-serves unchanged work, never touches excluded objects."""

from __future__ import annotations

import shutil

from runesmith import cli
from runesmith.demo import DemoStandIn, write_workspace
from runesmith.instruments import Router
from runesmith.proposals import list_proposals
from runesmith.steward import opportunity_id, steward

from test_kernel import make_repo


def test_steward_serves_new_work_once_and_respects_exclusions(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    workspace = tmp_path / "ws"
    shop = write_workspace(tmp_path / "demo")                       # three slips
    shutil.copytree(shop, workspace / "shop")
    green = make_repo(tmp_path / "g")
    (green / "src" / "calc" / "ops.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef double(x):\n    return add(x, x)\n", encoding="utf-8")
    shutil.copytree(green, workspace / "calc")
    shutil.copytree(make_repo(tmp_path / "x"), workspace / "precious")   # failing, but excluded
    before = sorted(p.relative_to(workspace / "precious").as_posix() for p in (workspace / "precious").rglob("*"))

    router = Router({"stand-in": DemoStandIn()}, {"repair": "stand-in"}, backoff_s=(0,), sleep=lambda s: None)
    lines: list[str] = []
    first, second = steward(home=home, workspace=workspace, router=router, seed="steward-test", rounds=2,
                            interval_s=0, exclude={"precious"}, loop_settings={"min_experience": 99},
                            out=lines.append, sleep=lambda s: None)
    assert first["objects"] == 3 and first["excluded"] == ["precious"]
    assert first["statuses"] == {"calc": "green", "shop": "failing"}
    assert first["new_opportunities"] == 3 and first["strict_successes"] == 3
    assert first["proposals_waiting"] == 3
    assert second["new_opportunities"] == 0                           # same sources: nothing is re-served
    assert "return sum(prices[1:])" in (workspace / "shop" / "src" / "shop" / "pricing.py").read_text(encoding="utf-8")
    after = sorted(p.relative_to(workspace / "precious").as_posix() for p in (workspace / "precious").rglob("*"))
    assert after == before                                            # excluded: never probed
    assert len(list_proposals(home)) == 3
    from runesmith.ledger import Ledger
    assert Ledger(home / "ledger.jsonl").verify()["ok"]              # the steward and the loop share one chain


def test_opportunity_identity_follows_the_source_state(tmp_path):
    repo = make_repo(tmp_path)
    opportunity = {"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"]}
    same = opportunity_id(opportunity)
    assert opportunity_id(dict(opportunity)) == same
    (repo / "src" / "calc" / "ops.py").write_text("def add(a, b):\n    return a * b\n", encoding="utf-8")
    assert opportunity_id(opportunity) != same                        # the object changed: new work


def test_steward_skips_flat_layout_repositories_instead_of_crashing(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    flat = tmp_path / "ws" / "flat"
    (flat / "tests").mkdir(parents=True)
    (flat / "pyproject.toml").write_text("[project]\nname = 'flat'\n", encoding="utf-8")
    (flat / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (flat / "tests" / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                                                  encoding="utf-8")
    router = Router({"stand-in": DemoStandIn()}, {"repair": "stand-in"}, backoff_s=(0,), sleep=lambda s: None)
    [result] = steward(home=home, workspace=tmp_path / "ws", router=router, seed="flat", out=lambda line: None)
    assert result["statuses"]["flat"].startswith("skipped: not a src-layout repository")
    assert result["new_opportunities"] == 0
