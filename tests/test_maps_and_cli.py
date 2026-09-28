"""Self-map, environment map, memory, configuration and command-line tests."""

from __future__ import annotations

import json
from pathlib import Path

from runesmith import cli
import pytest

from runesmith.envmap import build_environment_map, classify_object
from runesmith.memory import Memory
from runesmith.selfmap import CAPABILITY_LADDERS, band, build_self_map

from test_kernel import make_repo


def test_band_uses_owner_vocabulary():
    ladder = CAPABILITY_LADDERS["repair_yield"]
    assert band(None, ladder) == "unknown"
    assert band(0.1, ladder) == "bad"
    assert band(0.4, ladder) == "minimal"
    assert band(0.7, ladder) == "optimal"
    lower = CAPABILITY_LADDERS["seconds_per_repair"]
    assert band(90.0, lower) == "optimal" and band(900.0, lower) == "bad"


def test_self_map_knows_its_regions_and_admits_unknowns():
    self_map = build_self_map()
    regions = {c["path"]: c["region"] for c in self_map["components"]}
    assert regions["organs/repair.py"] == "organ (mutable)"
    assert regions["ledger.py"] == "kernel (fixed)"
    assert self_map["capabilities"]["repair_yield"]["band"] == "unknown"
    assert any("no opportunity telemetry" in u for u in self_map["unknowns"])
    records = [{"status": "public_pass", "strict_success": True, "cycle_seconds": 60, "calls": [{}, {}]},
               {"status": "budget_exhausted", "strict_success": False, "cycle_seconds": 90, "calls": [{}] * 5}]
    measured = build_self_map(records=records)["capabilities"]
    assert measured["repair_yield"]["value"] == 0.5 and measured["repair_yield"]["band"] == "minimal"
    assert measured["calls_per_repair"]["value"] == 7.0


def test_environment_map_finds_objects_ladders_and_unknowns(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    make_repo(workspace)                                  # workspace/repo: src/ + tests/
    (workspace / "notes").mkdir()
    (workspace / "notes" / "README.md").write_text("# notes\n", encoding="utf-8")
    assert classify_object(workspace / "repo") == "python_repository"
    static = build_environment_map(workspace)
    by_name = {o["name"]: o for o in static["objects"]}
    assert by_name["repo"]["next_rung"] == "tests_collect"
    assert by_name["notes"]["kind"] == "document_collection"
    assert any("not probed" in u for u in static["unknowns"])
    probed = build_environment_map(workspace, probe=True)
    repo = {o["name"]: o for o in probed["objects"]}["repo"]
    rungs = {r["rung"]: r["status"] for r in repo["ladder"]}
    assert rungs["tests_collect"] == "achieved" and rungs["tests_pass"] == "not_achieved"
    green = {o["id"]: o for o in repo["objectives"]}["tests_green"]
    assert green["value"] == 0.0 and green["band"] == "bad"


def test_memory_recall_is_lexical_deterministic_and_retirable(tmp_path):
    memory = Memory(tmp_path / "memory.jsonl")
    a = memory.add("episode", "fixed inverted comparison in scheduler window check", tags=["public_pass"])
    memory.add("negative", "renaming the cache key did not fix the stale session bug")
    hits = memory.recall("scheduler comparison inverted", 3)
    assert hits[0]["id"] == a
    memory.retire(a, "superseded")
    assert all(hit["id"] != a for hit in memory.recall("scheduler comparison inverted", 3))


def test_discover_turns_failing_tests_into_opportunities(tmp_path, capsys):
    from runesmith.discover import discover
    repo = make_repo(tmp_path)
    found = discover(repo)
    assert found["status"] == "failing"
    [opportunity] = found["opportunities"]
    assert opportunity["judge_tests"] == ["tests/test_ops.py"]
    assert set(opportunity["failing_tests"]) == {"tests/test_ops.py::test_add", "tests/test_ops.py::test_double"}
    assert "Failing tests (2)" in opportunity["issue"] and "src/" not in opportunity["issue"].split("Make the")[0]
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    config = json.loads((home / "runesmith.json").read_text(encoding="utf-8"))
    config["instruments"] = {"offline": {"kind": "scripted", "answers": [
        {"reads": [{"path": "src/calc/ops.py", "symbols": ["add"]}]},
        {"edits": [{"path": "src/calc/ops.py", "old_text": "return a - b", "new_text": "return a + b"}]}]}}
    config["roles"] = {"repair": ["offline"], "kaizen": ["offline"]}
    (home / "runesmith.json").write_text(json.dumps(config), encoding="utf-8")
    cli.main(["--home", str(home), "discover", str(repo)])
    assert "1 repair opportunities" in capsys.readouterr().out
    cli.main(["--home", str(home), "repair", "--opportunity", "0"])
    assert '"strict_success": true' in capsys.readouterr().out


def test_cli_init_repair_and_ledger_offline(tmp_path, capsys):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    config = json.loads((home / "runesmith.json").read_text(encoding="utf-8"))
    config["instruments"] = {"offline": {"kind": "scripted", "answers": [
        {"reads": [{"path": "src/calc/ops.py", "symbols": ["add"]}]},
        {"edits": [{"path": "src/calc/ops.py", "old_text": "return a - b", "new_text": "return a + b"}]}]}}
    config["roles"] = {"repair": ["offline"], "kaizen": ["offline"]}
    (home / "runesmith.json").write_text(json.dumps(config), encoding="utf-8")
    repo = make_repo(tmp_path)
    cli.main(["--home", str(home), "repair", "--repo", str(repo), "--test", "tests/test_ops.py::test_add",
              "--judge-test", "tests/test_ops.py", "--issue", "add() is wrong", "--apply"])
    out = capsys.readouterr().out
    assert '"strict_success": true' in out and "+    return a + b" in out
    assert "return a + b" in (repo / "src" / "calc" / "ops.py").read_text(encoding="utf-8")
    cli.main(["--home", str(home), "ledger"])
    assert '"ok": true' in capsys.readouterr().out
    cli.main(["--home", str(home), "selfmap"])
    assert '"repair_yield"' in capsys.readouterr().out
    assert len(Memory(home / "memory.jsonl").active()) == 1


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_discover_and_probe_never_write_into_the_object(tmp_path):
    from runesmith.discover import discover
    repo = make_repo(tmp_path)
    before = _tree(repo)
    found = discover(repo, scratch=tmp_path / "scratch")
    assert found["status"] == "failing" and found["opportunities"]
    assert found["opportunities"][0]["repo"] == str(repo.resolve())
    assert "rs-copy-" not in found["opportunities"][0]["issue"]           # the copy's path never leaks
    env_map = build_environment_map(repo, probe=True, scratch=tmp_path / "scratch")
    assert env_map["objects"][0]["objectives"][0]["value"] == 0.0         # double() calls the broken add()
    assert _tree(repo) == before                                          # no __pycache__, no new files
    assert not any((tmp_path / "scratch").iterdir())                      # throwaway copies are removed


def test_document_collections_get_link_integrity_in_bands(tmp_path):
    from runesmith.envmap import document_object
    docs = tmp_path / "docs"
    (docs / "guide").mkdir(parents=True)
    (docs / "guide" / "setup.md").write_text("# Setup\nBack to [the index](../README.md#top); "
                                             "see [line 1](../README.md:1) and [lines](../README.md:1-3).\n",
                                             encoding="utf-8")
    (docs / "README.md").write_text(
        "# Docs\n"
        "- [setup](guide/setup.md) and [same, with anchor](guide/setup.md#install)\n"
        "- [missing page](guide/missing.md)\n"
        "- [external](https://example.org/x) and [mail](mailto:a@b.c) and [in-page](#docs)\n"
        "- [spaced](guide/set%20up.md)\n"
        "[ref]: guide/setup.md\n"
        "```\n[not a link](inside/code.md)\n```\n", encoding="utf-8")
    result = document_object(docs)
    facts = result["facts"]
    assert facts["markdown_files"] == 2 and facts["index"] == "README.md"
    assert facts["internal_links"] == 8                                   # 5 in README (code fence ignored) + 3 in setup
    assert facts["broken_links"] == 2                                     # missing.md and "set up.md"
    assert {b["target"] for b in facts["broken_examples"]} == {"guide/missing.md", "guide/set%20up.md"}
    objective = result["objectives"][0]
    assert objective["value"] == round(6 / 8, 4) and objective["band"] == "bad"   # file:line references resolve
    assert result["next_rung"] == "links_resolve"
    (docs / "guide" / "missing.md").write_text("# now here\n", encoding="utf-8")
    (docs / "guide" / "set up.md").write_text("# spaced\n", encoding="utf-8")
    fixed = document_object(docs)
    assert fixed["objectives"][0]["band"] == "optimal" and fixed["next_rung"] is None
    env_map = build_environment_map(tmp_path)                             # a container holding the collection
    assert any(o["kind"] == "document_collection" and o["objectives"] for o in env_map["objects"])


def test_triage_marks_environment_failures_and_the_loop_spends_nothing_on_them(tmp_path):
    from runesmith.discover import opportunities_from_output, triage_reason
    from runesmith.instruments import Router
    from runesmith.kaizen.improve import FixtureInstrument
    from runesmith.ledger import Ledger
    from runesmith.loop import run_loop
    repo = make_repo(tmp_path)
    assert triage_reason("ModuleNotFoundError: No module named 'requests'", repo)["kind"] == "environment"
    assert triage_reason("ModuleNotFoundError: No module named 'calc.missing'", repo) is None   # calc is in src/
    assert triage_reason("requests.exceptions.ConnectionError: HTTPSConnectionPool(...)", repo)["kind"] == "environment"
    assert triage_reason("assert -1 == 5", repo) is None
    output = ("FAILED tests/test_net.py::test_fetch - requests.exceptions.ConnectionError: boom\n"
              "FAILED tests/test_ops.py::test_add - assert -1 == 5\n")
    found = {o["judge_tests"][0]: o for o in opportunities_from_output(output, repo)}
    assert found["tests/test_net.py"]["triage"]["kind"] == "environment"
    assert "triage" not in found["tests/test_ops.py"]
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    router = Router({"y": FixtureInstrument({"reads": [], "edits": []})}, {"repair": "y"}, backoff_s=(0,),
                    sleep=lambda s: None)
    summary = run_loop(home=home, opportunities=[found["tests/test_net.py"]], seed="triage", router=router,
                       min_experience=99)
    assert summary["skipped_environment"] == 1 and summary["object_steps"] == 0
    assert not (home / "sessions").exists()                               # no session, no model call
    assert any(e["kind"] == "opportunity.skipped" for e in Ledger(home / "ledger.jsonl"))


def test_discover_triages_a_real_missing_dependency_end_to_end(tmp_path):
    from runesmith.discover import discover
    repo = make_repo(tmp_path)
    (repo / "tests" / "test_net.py").write_text(
        "def test_uses_a_missing_dependency():\n"
        "    import a_third_party_package_that_is_not_installed_anywhere\n", encoding="utf-8")
    found = discover(repo, scratch=tmp_path / "scratch")
    by_file = {o["judge_tests"][0]: o for o in found["opportunities"]}
    assert by_file["tests/test_net.py"]["triage"]["kind"] == "environment"
    assert "a_third_party_package_that_is_not_installed_anywhere" in by_file["tests/test_net.py"]["triage"]["reason"]
    assert "triage" not in by_file["tests/test_ops.py"]                  # a real source defect stays repairable


@pytest.mark.parametrize("layout,kind", [
    ({"shop/__init__.py": "", "tests/test_shop.py": "", "README.md": "# shop"}, "python_repository"),   # J3-B1
    ({"tool.py": "", "test_tool.py": "", "README.md": "# tool"}, "python_repository"),
    ({"requirements.txt": "", "app.py": ""}, "python_repository"),
    ({"README.md": "# notes", "guide.md": "text"}, "document_collection"),
    ({"tests/test_orphan.py": "", "README.md": "# only tests"}, "document_collection"),
])
def test_small_python_projects_are_recognised_without_packaging_files(tmp_path, layout, kind):
    for rel, text in layout.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert classify_object(tmp_path) == kind


def test_a_flat_project_with_failing_tests_is_probed_and_its_failures_found(tmp_path):
    # J3: a package, its tests and a README; one test fails. Mapping with probing must run the tests.
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "__init__.py").write_text("def total(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_shop.py").write_text(
        "import unittest\nfrom shop import total\n\n\nclass T(unittest.TestCase):\n"
        "    def test_total(self):\n        self.assertEqual(total(2, 3), 5)\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# shop\n", encoding="utf-8")
    probed = build_environment_map(tmp_path, probe=True)
    root = next(o for o in probed["objects"] if o["root"])
    assert root["kind"] == "python_repository"
    rungs = {r["rung"]: r["status"] for r in root["ladder"]}
    assert rungs["tests_collect"] == "achieved" and rungs["tests_pass"] == "not_achieved"


def test_the_index_is_named_as_it_is_on_disk(tmp_path):
    # J4-F3: on a case-insensitive disk "INDEX.md" exists when index.md does; the map shows the real name.
    (tmp_path / "index.md").write_text("# Recipes" + chr(10), encoding="utf-8")
    (tmp_path / "rye.md").write_text("# Rye" + chr(10), encoding="utf-8")
    doc = next(o for o in build_environment_map(tmp_path)["objects"] if o["root"])
    assert doc["facts"]["index"] == "index.md"


def test_pages_nothing_links_to_and_notes_still_to_do_are_found(tmp_path):
    # J4: a handbook with a page no reader can reach by following links, and notes left to do.
    (tmp_path / "recipes").mkdir()
    (tmp_path / "index.md").write_text("# Handbook\n\n[Rye](recipes/rye.md)\n", encoding="utf-8")
    (tmp_path / "recipes" / "rye.md").write_text(
        "# Rye\n\nTODO: add the baking time.\n\n```\n# TODO inside a code example is not a note\n```\n\n[Back](../index.md)\n",
        encoding="utf-8")
    (tmp_path / "recipes" / "seeded-loaf.md").write_text("# Seeded loaf\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("Order flour.\nFIXME: the oven timer\n", encoding="utf-8")
    objects = {o["name"]: o["facts"] for o in build_environment_map(tmp_path)["objects"]}
    # recipes/ is an object of its own; rye.md is linked from the folder's index, so only the seeded loaf is an orphan.
    assert objects["recipes"]["orphan_examples"] == ["seeded-loaf.md"]
    assert sum(f["orphan_pages"] for f in objects.values()) == 1
    notes = sorted((name, t["document"], t["line"]) for name, f in objects.items() for t in f["todo_examples"])
    assert notes == [("recipes", "rye.md", 3), (tmp_path.name, "notes.txt", 2)]


def test_generations_verify_without_an_id_checks_every_generation(tmp_path, capsys):
    # Journey J10-B1: `runesmith generations verify` crashed with a traceback when no id was given.
    home = tmp_path / ".runesmith"
    cli.main(["--home", str(home), "init"])
    capsys.readouterr()
    cli.main(["--home", str(home), "generations", "verify"])
    verified = json.loads(capsys.readouterr().out)
    assert len(verified) == 1 and all(v["ok"] for v in verified.values())      # g0, the shipped organs
    with pytest.raises(SystemExit, match="needs a generation id"):
        cli.main(["--home", str(home), "generations", "activate"])


def test_an_unexpected_error_at_the_terminal_is_one_plain_line(tmp_path):
    # Journey J10: a person at a terminal gets what went wrong and where to look, not a Python traceback.
    import os
    import subprocess
    import sys
    home = tmp_path / ".runesmith"
    cli.main(["--home", str(home), "init"])
    (home / "runesmith.json").write_text("{ this is not json", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "RUNESMITH_DEBUG"}
    env["PYTHONPATH"] = str(root)
    done = subprocess.run([sys.executable, "-m", "runesmith", "--home", str(home), "status"], cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and "Traceback" not in done.stderr, done.stderr
    assert done.stderr.startswith("Runesmith stopped:") and "runesmith doctor" in done.stderr
    env["RUNESMITH_DEBUG"] = "1"
    debug = subprocess.run([sys.executable, "-m", "runesmith", "--home", str(home), "status"], cwd=str(tmp_path), env=env,
                           capture_output=True, text=True, timeout=60)
    assert "Traceback" in debug.stderr


def test_the_terminal_says_plainly_when_setup_is_missing(tmp_path, monkeypatch, capsys):
    # Journey J10-F2, B2, F1: status before init printed a default setup; the demo silently showed "0 of 0 repairs"
    # without pytest; discover said "error_without_failures".
    import importlib.util
    home = tmp_path / ".runesmith"
    with pytest.raises(SystemExit, match="No Runesmith home here yet"):
        cli.main(["--home", str(home), "status"])
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "pytest" else real(name, *a))
    with pytest.raises(SystemExit, match="python -m pip install pytest"):
        cli.main(["--home", str(home), "demo"])
    assert not home.exists()                                  # nothing was set up for a demo that cannot run
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_x.py").write_text("import unittest\n", encoding="utf-8")
    cli.main(["--home", str(home), "discover", str(project)])
    out = capsys.readouterr().out
    assert "the tests could not run" in out and "Why: pytest is not installed" in out and "error_without_failures" not in out
