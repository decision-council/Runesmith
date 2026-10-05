"""The living map's builders (docs/MAP_LOGIC.md): structure graph, test-run evidence, ladders, lineage, plan graph.

Every case is built on a fixture folder and a fixture home; nothing runs a model, and the only test run that is real is
the one probe case at the end of the evidence tests.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from runesmith import generations
from runesmith.app import living_map
from runesmith.app.workspace import Workspace, _write_json
from runesmith.kaizen.trial import Trial


def utc(offset: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


def write(root: Path, rel: str, text: str = "x = 1\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def shop(tmp_path: Path) -> tuple[Workspace, Path]:
    """A Python project in the src layout: cart and prices are tested, checkout is tested by a failing test, lonely is not
    tested at all, and a README and a pyproject sit at the top."""
    root = tmp_path / "shop"
    write(root, "src/shop/__init__.py", "from .cart import Cart\n")
    write(root, "src/shop/cart.py", "from shop import prices\n\n\nclass Cart:\n    pass\n")
    write(root, "src/shop/prices.py", "def price():\n    return 1\n")
    write(root, "src/shop/checkout.py", "from shop.prices import price\n")
    write(root, "src/shop/lonely.py", "VALUE = 1\n")
    write(root, "tests/test_cart.py", "from shop.cart import Cart\n\n\ndef test_cart():\n    assert Cart\n")
    write(root, "tests/test_prices.py", "from shop import prices\n\n\ndef test_price():\n    assert prices.price()\n")
    write(root, "tests/test_checkout.py", "from shop.checkout import price\n\n\ndef test_checkout():\n    assert price\n")
    write(root, "README.md", "# shop\n")
    write(root, "pyproject.toml", '[project]\nname = "shop"\n')
    ws = Workspace(root, tmp_path / "home")
    ws.map_environment(probe=False)
    return ws, root


def age(root: Path, seconds: float = 7200) -> None:
    """Make every file of the fixture older than the run the test is about to record."""
    old = time.time() - seconds
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))


def round_record(ws: Workspace, status: str, *, when_utc: str | None = None, failing: list[str] | None = None) -> None:
    name = next(o["name"] for o in ws.environment_map()["objects"])
    _write_json(ws.home / "WORK.json", {
        "utc": when_utc or utc(60), "outcome": "worked", "objects": {name: status}, "details": {}, "summary": {},
        "opportunities": [{"id": "o1", "object": name, "failing_tests": failing or [], "issue": "x"}] if failing else []})


def nodes(view: dict) -> dict[str, dict]:
    return {n["id"]: n for n in view["nodes"]}


# ------------------------------------------------------------------------------------------- the structure --

def test_structure_has_kinds_groups_edges_and_how_each_edge_was_found(tmp_path):
    ws, _ = shop(tmp_path)
    view = living_map.structure_view(ws)
    by = nodes(view)
    assert {k: v["kind"] for k, v in by.items()} == {
        "README.md": "doc", "pyproject.toml": "config", "src/shop/__init__.py": "module", "src/shop/cart.py": "module",
        "src/shop/checkout.py": "module", "src/shop/lonely.py": "module", "src/shop/prices.py": "module",
        "tests/test_cart.py": "test", "tests/test_checkout.py": "test", "tests/test_prices.py": "test"}
    assert [g["id"] for g in view["groups"]] == ["", "src/shop", "tests"]
    assert by["src/shop/cart.py"]["lines"] == 5 and by["src/shop/cart.py"]["group"] == "src/shop"
    edges = {(e["from"], e["to"], e["type"]): e["how"] for e in view["edges"]}
    assert edges[("src/shop/cart.py", "src/shop/prices.py", "imports")] == ["python ast: from shop import prices (line 1)"]
    assert edges[("src/shop/__init__.py", "src/shop/cart.py", "imports")] == ["python ast: from .cart import Cart (line 1)"]
    # a test file reaches a module by importing it, or by its name, and says which
    assert any("the test imports it" in how for how in edges[("tests/test_cart.py", "src/shop/cart.py", "tests")])
    assert any(how.startswith("named for it") for how in edges[("tests/test_cart.py", "src/shop/cart.py", "tests")])
    assert ("tests/test_checkout.py", "src/shop/checkout.py", "tests") in edges
    assert not [e for e in view["edges"] if e["to"] == "README.md" or e["from"] == "README.md"]
    for n in view["nodes"]:                                   # every fact names its source
        assert n["evidence"] and all(row["source"] for row in n["evidence"]), n["id"]
    assert view["counts"]["files"] == 10 and view["counts"]["edges"] == len(view["edges"])


def test_a_module_with_no_test_is_minimal_and_no_run_makes_the_rest_unknown(tmp_path):
    ws, _ = shop(tmp_path)
    by = nodes(living_map.structure_view(ws))
    assert by["src/shop/lonely.py"]["state"]["band"] == "minimal"
    assert "nothing here tests it" in by["src/shop/lonely.py"]["state"]["reason"]
    assert by["src/shop/cart.py"]["state"]["band"] == "unknown"
    assert by["src/shop/cart.py"]["state"]["reason"] == "No test run is recorded for this project."
    assert by["tests/test_cart.py"]["test"]["result"] == "not_run"
    assert by["README.md"]["state"]["band"] == "unknown"                     # a document is not measured


def test_a_whole_suite_green_run_makes_tested_modules_optimal_with_the_run_named(tmp_path):
    ws, _ = shop(tmp_path)
    round_record(ws, "green", when_utc=utc(60))
    view = living_map.structure_view(ws)
    by = nodes(view)
    for name in ("cart", "prices", "checkout"):
        state = by[f"src/shop/{name}.py"]["state"]
        assert state["band"] == "optimal" and "every test passed" in state["reason"]
        assert "during a repair round" in state["reason"]
    assert by["src/shop/lonely.py"]["state"]["band"] == "minimal"           # untested stays untested
    assert by["tests/test_cart.py"]["test"]["result"] == "passed"
    assert view["run"]["source"] == "round" and view["run"]["scope"] == "whole"


def test_a_failing_run_names_the_files_it_names_and_leaves_the_rest_unknown(tmp_path):
    ws, _ = shop(tmp_path)
    round_record(ws, "failing", failing=["tests/test_checkout.py::test_checkout"])
    by = nodes(living_map.structure_view(ws))
    bad = by["src/shop/checkout.py"]["state"]
    assert bad["band"] == "bad" and "tests/test_checkout.py failed" in bad["reason"]
    assert by["tests/test_checkout.py"]["test"]["result"] == "failed"
    assert by["tests/test_checkout.py"]["state"]["band"] == "bad"
    assert any(b["kind"] == "failing" for b in by["tests/test_checkout.py"]["badges"])
    # the round lists only the files it served: another test file's pass is not recorded, so never Optimal
    for name in ("cart", "prices"):
        unknown = by[f"src/shop/{name}.py"]["state"]
        assert unknown["band"] == "unknown" and "not the other test files' results" in unknown["reason"]
    assert by["tests/test_cart.py"]["test"]["result"] == "unknown"


def test_a_module_changed_after_the_run_is_unknown_not_a_stale_color(tmp_path):
    ws, root = shop(tmp_path)
    age(root)
    round_record(ws, "green", when_utc=utc(-3600))                          # the round finished an hour ago
    write(root, "src/shop/checkout.py", "from shop.prices import price\n\nVALUE = 2\n")   # changed now, after it
    by = nodes(living_map.structure_view(ws))
    assert by["src/shop/checkout.py"]["state"]["band"] == "unknown"
    assert by["src/shop/checkout.py"]["state"]["reason"].startswith("Changed since the last test run: src/shop/checkout.py")
    assert by["src/shop/cart.py"]["state"]["band"] == "optimal"             # cart did not change, nor did its test, nor what it imports
    assert by["src/shop/prices.py"]["state"]["band"] == "optimal"           # checkout imports prices, not the other way round
    # a test file changed after the run makes the modules it reaches unknown too
    round_record(ws, "green", when_utc=utc(60))
    assert nodes(living_map.structure_view(ws))["src/shop/cart.py"]["state"]["band"] == "optimal"
    round_record(ws, "green", when_utc=utc(-3600))
    age(root)
    write(root, "tests/test_cart.py", "from shop.cart import Cart\n\n\ndef test_cart():\n    assert Cart is not None\n")
    stale = nodes(living_map.structure_view(ws))
    assert stale["src/shop/cart.py"]["state"]["band"] == "unknown" and "tests/test_cart.py changed" in stale["src/shop/cart.py"]["state"]["reason"]
    assert stale["tests/test_cart.py"]["test"]["words"] == "changed since the last test run"


def test_a_unittest_subset_never_earns_optimal(tmp_path):
    ws, _ = shop(tmp_path)
    env = ws.environment_map()
    obj = env["objects"][0]
    obj["probe"] = {"runner": "unittest", "collected": 3, "passed": 3, "failed": 0, "errors": 0, "exit_code": 0, "suite_seconds": 0.1}
    obj["measured_utc"] = utc(60)
    _write_json(ws.home / "ENVIRONMENT.json", env)
    view = living_map.structure_view(ws)
    by = nodes(view)
    assert view["run"]["scope"] == "subset" and view["run"]["outcome"] == "passed"
    assert by["src/shop/cart.py"]["state"]["band"] == "unknown" and "unittest subset" in by["src/shop/cart.py"]["state"]["reason"]
    assert not [n for n in view["nodes"] if n["state"]["band"] == "optimal"]


def test_a_failing_probe_records_counts_not_names_so_no_file_is_blamed(tmp_path):
    ws, _ = shop(tmp_path)
    env = ws.environment_map()
    env["objects"][0]["probe"] = {"runner": "pytest", "collected": 3, "passed": 2, "failed": 1, "errors": 0, "exit_code": 1}
    env["objects"][0]["measured_utc"] = utc(60)
    _write_json(ws.home / "ENVIRONMENT.json", env)
    view = living_map.structure_view(ws)
    assert view["run"]["source"] == "probe" and view["run"]["outcome"] == "failed"
    cart = nodes(view)["src/shop/cart.py"]["state"]
    assert cart["band"] == "unknown" and "did not record which test files failed" in cart["reason"]
    assert not [n for n in view["nodes"] if n["state"]["band"] in ("bad", "optimal")]


def test_an_applied_fix_after_the_round_makes_the_tests_unknown(tmp_path):
    ws, root = shop(tmp_path)
    age(root)
    round_record(ws, "failing", when_utc=utc(-120), failing=["tests/test_checkout.py::test_checkout"])
    # a proposal applied after the round, as the Studio records it
    (ws.home / "experience" / "k1").mkdir(parents=True)
    import gzip
    with gzip.open(ws.home / "experience" / "k1" / "verified_fix.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"src/shop/checkout.py": "from shop.prices import price\n"}, stream)
    with gzip.open(ws.home / "experience" / "k1" / "parent_src.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"src/shop/checkout.py": ""}, stream)
    (ws.home / "experience" / "k1" / "TASK.json").write_text(json.dumps({
        "key": "k1", "repo": str(ws.root), "failing_tests": ["tests/test_checkout.py::test_checkout"], "issue": "x"}), encoding="utf-8")
    _write_json(ws.home / "PROPOSALS_STATE.json", {"k1": {"state": "applied", "utc": utc(-60)}})
    view = living_map.structure_view(ws)
    assert view["run"]["superseded"] and view["run"]["status"] == "fix_applied"
    by = nodes(view)
    assert by["src/shop/cart.py"]["state"]["band"] == "unknown"
    assert "fix was applied after this run" in by["src/shop/cart.py"]["state"]["reason"]
    assert by["src/shop/checkout.py"]["state"]["band"] == "unknown"           # never Bad over a run a fix has outdated
    obj = ws.environment_map()["objects"][0]
    overlay = living_map.ladder_overlay(ws, obj)
    assert overlay["tests_pass"]["status"] == "unknown" and overlay["tests_collect"]["status"] == "unknown"
    # the badge: Runesmith's fix is the last change, with its time
    assert any(row["label"] == "Last change" and "a fix was applied by you" in row["value"]
               for row in by["src/shop/checkout.py"]["evidence"])


def test_a_real_probe_of_a_passing_project_makes_modules_optimal(tmp_path):
    pytest.importorskip("pytest")
    ws, _ = shop(tmp_path)
    ws.map_environment(probe=True)                                               # runs pytest on a throwaway copy
    view = living_map.structure_view(ws)
    run = view["run"]
    if run["outcome"] != "passed":                                              # a machine without these paths: nothing to claim
        pytest.skip("the fixture project's tests did not run green here: " + run["words"])
    assert run["source"] == "probe" and run["scope"] == "whole"
    assert nodes(view)["src/shop/cart.py"]["state"]["band"] == "optimal"


# -------------------------------------------------------------------------------- other kinds of folders --

def test_a_javascript_project_has_import_edges_and_no_test_results(tmp_path):
    root = tmp_path / "web"
    write(root, "package.json", '{"name": "web", "scripts": {"test": "node --test"}}')
    write(root, "src/app.js", "import { draw } from './draw.js';\nconst util = require('./lib/util');\n")
    write(root, "src/draw.js", "export function draw() {}\n")
    write(root, "src/lib/util.js", "module.exports = {};\n")
    write(root, "src/lib/index.ts", "export * from './util';\n")
    write(root, "src/pages.js", "import('./lib').then(() => 1);\nimport React from 'react';\n")
    write(root, "src/draw.test.js", "import { draw } from './draw.js';\n")
    ws = Workspace(root, tmp_path / "home")
    ws.map_environment(probe=False)
    view = living_map.structure_view(ws)
    by = nodes(view)
    edges = {(e["from"], e["to"], e["type"]) for e in view["edges"]}
    assert ("src/app.js", "src/draw.js", "imports") in edges and ("src/app.js", "src/lib/util.js", "imports") in edges
    assert ("src/pages.js", "src/lib/index.ts", "imports") in edges                   # a folder import finds its index
    assert ("src/lib/index.ts", "src/lib/util.js", "imports") in edges
    assert ("src/draw.test.js", "src/draw.js", "tests") in edges                      # imported, and named for it
    assert not [e for e in edges if "react" in e[1]]                                   # a package is not a project file
    assert "pattern" in next(e for e in view["edges"] if e["type"] == "imports")["how"][0]
    assert by["src/draw.js"]["state"]["band"] == "unknown" and "does not run" in by["src/draw.js"]["state"]["reason"]
    assert by["src/pages.js"]["state"]["band"] == "minimal"
    assert view["run"]["recorded"] is False and "npm test" in view["run"]["words"]


def test_a_docs_folder_groups_documents_and_has_no_edges(tmp_path):
    root = tmp_path / "docs"
    for name in ("a", "b", "c"):
        write(root, f"guide/{name}.md", "# " + name + "\n")
    write(root, "index.md", "# index\n")
    ws = Workspace(root, tmp_path / "home")
    ws.map_environment(probe=False)
    view = living_map.structure_view(ws, "guide")                           # the sub-folder is an object of its own
    assert view["edges"] == [] and {n["kind"] for n in view["nodes"]} == {"doc"}
    assert [g["id"] for g in view["groups"]] == [""] and len(view["nodes"]) == 3
    assert "no code to link" in view["sentence"] and "no edges" in view["sentence"]
    top = next(o["name"] for o in ws.environment_map()["objects"] if o["root"])
    assert [n["id"] for n in living_map.structure_view(ws, top)["nodes"]] == ["index.md"]


def test_a_folder_with_no_files_says_so_in_a_plain_sentence(tmp_path):
    root = tmp_path / "root"
    (root / "empty").mkdir(parents=True)
    write(root, "readme.md", "hi\n")
    ws = Workspace(root, tmp_path / "home")
    ws.map_environment(probe=False)
    view = living_map.structure_view(ws, "empty")
    assert view["empty"] is True and view["nodes"] == [] and "no files here yet" in view["sentence"]


def test_a_container_workspace_reads_only_its_own_loose_files(tmp_path):
    root = tmp_path / "root"
    write(root, "notes.md", "n\n")
    write(root, "sub/project/a.py", "x = 1\n")
    write(root, "sub/project/test_a.py", "import a\n")
    ws = Workspace(root, tmp_path / "home")
    ws.map_environment(probe=False)
    top = next(o for o in ws.environment_map()["objects"] if o["root"])
    assert [n["id"] for n in living_map.structure_view(ws, top["name"])["nodes"]] == ["notes.md"]


# ------------------------------------------------------------------------------------------------- scale --

def test_two_hundred_files_are_capped_grouped_stable_and_expandable(tmp_path):
    root = tmp_path / "big"
    for folder in range(8):
        for i in range(25):
            write(root, f"pkg{folder}/m{i:02d}.py", "VALUE = %d\n" % i + "x = 1\n" * (i % 7))
    write(root, "pkg0/test_m00.py", "import m00\n")
    write(root, "pyproject.toml", '[project]\nname = "big"\n')
    ws = Workspace(root, tmp_path / "home")
    ws.map_environment(probe=False)
    one = living_map.structure_view(ws)
    two = living_map.structure_view(ws)
    assert one["counts"]["files"] == 202 and one["counts"]["drawn"] <= 60 + len(one["groups"])
    assert [n["id"] for n in one["nodes"]] == [n["id"] for n in two["nodes"]]                 # the same drawing twice
    assert [(n["id"], n["drawn"]) for n in one["nodes"]] == [(n["id"], n["drawn"]) for n in two["nodes"]]
    assert [n["id"] for n in one["nodes"]] == sorted(n["id"] for n in one["nodes"])             # folder, then name
    shown = {g["id"]: g for g in one["groups"]}
    assert all(g["drawn"] + g["more"] == g["files"] for g in one["groups"])
    assert sum(g["more"] for g in one["groups"]) > 0 and shown["pkg1"]["more"] > 0
    expanded = living_map.structure_view(ws, expand=("pkg1",))
    assert {g["id"]: g for g in expanded["groups"]}["pkg1"]["more"] == 0 and {g["id"]: g for g in expanded["groups"]}["pkg1"]["expanded"]
    assert len(one["nodes"]) == 202                                                           # the list view holds every file


def test_more_than_twelve_folders_share_one_group(tmp_path):
    root = tmp_path / "wide"
    for folder in range(16):
        for i in range(3):
            write(root, f"f{folder:02d}/m{i}.py")
    write(root, "pyproject.toml", '[project]\nname = "wide"\n')
    ws = Workspace(root, tmp_path / "home")
    ws.map_environment(probe=False)
    view = living_map.structure_view(ws)
    assert len(view["groups"]) == living_map.GROUP_CAP + 1
    assert "(other folders)" in {g["id"] for g in view["groups"]}


def test_an_excluded_object_is_never_read(tmp_path):
    root = tmp_path / "root"
    write(root, "secret/key.py", "TOKEN = 1\n")
    write(root, "open/a.py", "x = 1\n")
    ws = Workspace(root, tmp_path / "home")
    ws.update_settings({"exclude": ["secret"]})
    ws.map_environment(probe=False)
    view = living_map.structure_view(ws, "secret")
    assert view["empty"] and view["nodes"] == [] and "never-touch" in view["sentence"]


# --------------------------------------------------------------------------------------------- the ladder --

def test_the_ladder_uses_the_latest_run_whatever_ran_it_and_names_it(tmp_path):
    ws, _ = shop(tmp_path)
    obj = ws.environment_map()["objects"][0]
    assert living_map.ladder_overlay(ws, obj) is None                        # no run: the map's own ladder stays
    round_record(ws, "green", when_utc="2026-10-05T13:11:00Z")
    overlay = living_map.ladder_overlay(ws, obj)
    assert overlay["tests_collect"]["status"] == "achieved" and overlay["tests_pass"]["status"] == "achieved"
    assert overlay["tests_pass"]["source_words"] == "latest test run 13:11Z, during a repair round"
    assert overlay["fast_suite"]["status"] == "unknown"
    round_record(ws, "failing", when_utc="2026-10-05T13:12:00Z", failing=["tests/test_checkout.py::test_checkout"])
    overlay = living_map.ladder_overlay(ws, obj)
    assert overlay["tests_collect"]["status"] == "achieved" and overlay["tests_pass"]["status"] == "not_achieved"
    round_record(ws, "error_without_failures", when_utc="2026-10-05T13:13:00Z")
    overlay = living_map.ladder_overlay(ws, obj)
    assert overlay["tests_collect"]["status"] == "unknown" and overlay["tests_pass"]["status"] == "unknown"


def test_a_newer_probe_wins_over_an_older_round_and_a_newer_round_over_a_probe(tmp_path):
    ws, _ = shop(tmp_path)
    env = ws.environment_map()
    env["objects"][0]["probe"] = {"runner": "pytest", "collected": 3, "passed": 3, "failed": 0, "errors": 0, "exit_code": 0, "suite_seconds": 2.0}
    env["objects"][0]["measured_utc"] = "2026-10-05T14:00:00Z"
    _write_json(ws.home / "ENVIRONMENT.json", env)
    round_record(ws, "failing", when_utc="2026-10-05T13:00:00Z", failing=["tests/test_checkout.py::test_checkout"])
    obj = ws.environment_map()["objects"][0]
    assert living_map.latest_run(ws, obj)["source"] == "probe"
    round_record(ws, "failing", when_utc="2026-10-05T15:00:00Z", failing=["tests/test_checkout.py::test_checkout"])
    run = living_map.latest_run(ws, obj)
    assert run["source"] == "round" and run["outcome"] == "failed"


def test_the_measuring_round_with_unittest_names_failing_tests_and_stays_a_subset(tmp_path):
    ws, _ = shop(tmp_path)
    obj = ws.environment_map()["objects"][0]
    round_record(ws, "measured: 1 of 3 tests fail", when_utc=utc(60))
    folder = ws.home / "fix-tests"
    folder.mkdir(parents=True)
    _write_json(folder / "MEASURED.json", {obj["path"]: {"object": obj["name"], "path": obj["path"], "status": "failed", "ran": 3,
                                                          "failures": 1, "errors": 0, "failing": ["tests.test_checkout.TestCheckout.test_checkout"],
                                                          "utc": utc(30)}})
    view = living_map.structure_view(ws)
    assert view["run"]["source"] == "measure" and view["run"]["scope"] == "subset"
    by = nodes(view)
    assert by["src/shop/checkout.py"]["state"]["band"] == "bad"
    assert by["src/shop/cart.py"]["state"]["band"] == "unknown"
    overlay = living_map.ladder_overlay(ws, obj)
    assert overlay["tests_pass"]["status"] == "not_achieved" and overlay["tests_collect"]["status"] == "achieved"     # unittest found and ran 3 tests
    assert "as a subset it does not show that every test file collects" in overlay["tests_collect"]["note"]
    stages = {s["id"]: s for s in living_map.stages_view(ws)}
    assert stages["discover"]["count"] == 1 and "failing: shop" in stages["discover"]["extra"]          # a measuring round found work too


# ------------------------------------------------------------------------------------------------ badges --

def test_badges_come_from_the_drafts_the_plan_and_the_ledger(tmp_path):
    ws, root = shop(tmp_path)
    milestone = ws.add_milestone("Cheaper carts", "make src/shop/cart.py faster", "Speed", "carts are fast")
    ws.save_draft(title="A faster cart", why="because", files=[{"path": "src/shop/cart.py", "content": "class Cart:\n    pass\n"}],
                  drafted_by="gemini-test", milestone=milestone["id"])
    applied = ws.save_draft(title="Prices", why="because", files=[{"path": "src/shop/prices.py", "content": "def price():\n    return 3\n"}],
                            drafted_by="gemini-test")
    ws.apply_draft(applied["id"], overwrite=True)
    by = nodes(living_map.structure_view(ws))
    kinds = {b["kind"] for b in by["src/shop/cart.py"]["badges"]}
    assert {"draft_waiting", "milestone"} <= kinds
    assert "changed" in {b["kind"] for b in by["src/shop/prices.py"]["badges"]}
    labels = {row["label"]: row for row in by["src/shop/prices.py"]["evidence"]}
    assert "applied from a draft by you" in labels["Last change"]["value"] and "gemini-test" in labels["Last change"]["value"]
    assert labels["Last change"]["source"].startswith("ledger and draft record")
    open_work = {row["label"]: row for row in by["src/shop/cart.py"]["evidence"]}["Open work"]
    assert any("A faster cart" in item for item in open_work["items"])


# ---------------------------------------------------------------------------------------------- lineage --

def candidate(ws: Workspace, parent: str, tag: str, **provenance) -> dict:
    """A frozen generation whose organ differs by a comment, so its id is its own."""
    source = ws.home / "generations" / parent / "organs"
    target = ws.home / "scratch" / f"organs-{tag}"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target)
    repair = target / "repair.py"
    repair.write_bytes(repair.read_bytes() + f"\n# {tag}\n".encode())
    return generations.freeze(target, ws.home, label=f"kaizen-loop {tag}", parent=parent, provenance=provenance or {"target": {"family": "x"}})


def test_the_lineage_is_in_parent_to_child_order_with_trial_states_and_ticks_only_where_earned(tmp_path):
    ws, _ = shop(tmp_path)
    g0 = generations.active(ws.home)
    # ids are digests: build children until the child's id sorts before its parent's, the order the old track got wrong
    child = None
    for tag in "abcdefgh":
        child = candidate(ws, g0, tag)
        if child["id"] < g0:
            break
    grandchild = candidate(ws, child["id"], "grand")
    sibling = candidate(ws, g0, "sibling")
    trial = Trial(incumbent=g0, candidate=grandchild["id"], seed="s", min_per_arm=10, look_every=10, max_per_arm=40)
    trial.counts = {"incumbent": [3, 8], "candidate": [5, 9]}
    trial.save(ws.home / "TRIAL.json")
    # a rejected candidate and one won
    lost = Trial(incumbent=g0, candidate=sibling["id"], seed="s", decision="reject", counts={"incumbent": [8, 10], "candidate": [2, 10]})
    lost.save(ws.home / f"TRIAL-{sibling['id']}-reject.json")
    view = living_map.lineage_view(ws)
    ids = [s["id"] for s in view["stations"]]
    assert ids.index(g0) < ids.index(child["id"]) < ids.index(grandchild["id"])               # parent before child
    by = {s["id"]: s for s in view["stations"]}
    assert by[g0]["state"] == "active" and by[g0]["tick"] and by[g0]["depth"] == 0
    assert by[grandchild["id"]]["state"] == "on_trial" and not by[grandchild["id"]]["tick"]
    assert "candidate repaired 5 of 9" in by[grandchild["id"]]["state_words"] and "next look" in by[grandchild["id"]]["state_words"]
    assert by[grandchild["id"]]["trial"]["next_look_at"] == 10 and by[grandchild["id"]]["trial"]["looks"] == 0
    assert by[sibling["id"]]["state"] == "rejected" and not by[sibling["id"]]["tick"]
    assert by[child["id"]]["state"] == "frozen" and not by[child["id"]]["tick"]
    assert sum(1 for s in view["stations"] if s["tick"]) == 1                                  # only the active one


def test_a_generation_that_won_its_trial_is_ticked_and_an_owner_rollback_is_named(tmp_path):
    ws, _ = shop(tmp_path)
    g0 = generations.active(ws.home)
    winner = candidate(ws, g0, "winner")
    Trial(incumbent=g0, candidate=winner["id"], seed="s", decision="activate",
          counts={"incumbent": [2, 12], "candidate": [9, 12]}).save(ws.home / f"TRIAL-{winner['id']}-activate.json")
    ws.ledger.append("generation.activated", {"id": winner["id"], "previous": g0, "evidence": "online trial"})
    generations.activate(ws.home, winner["id"], expected=g0)
    by = {s["id"]: s for s in living_map.lineage_view(ws)["stations"]}
    assert by[winner["id"]]["state"] == "active" and by[winner["id"]]["tick"]
    assert by[g0]["state"] == "superseded" and not by[g0]["tick"] and "online trial" in by[g0]["state_words"]
    # the owner rolls back: the winner is left, rolled back, and still ticked because it won
    assert ws.activate_generation(g0)["ok"]
    by = {s["id"]: s for s in living_map.lineage_view(ws)["stations"]}
    assert by[g0]["state"] == "active"
    assert by[winner["id"]]["state"] == "rolled_back" and by[winner["id"]]["tick"] and "Rolled back" in by[winner["id"]]["state_words"]


# ----------------------------------------------------------------------------------------------- the plan --

def test_the_plan_graph_has_prerequisite_edges_states_origins_and_needs_you(tmp_path):
    ws, _ = shop(tmp_path)
    first = ws.add_milestone("Lay the base", "base", "Core", "the base exists")
    second = ws.add_milestone("Build on it", "more", "Core", "built", depends_on=[first["id"]])
    third = ws.add_milestone("Polish", "shine", "Extras", "polished", depends_on=[second["id"]])
    done = ws.add_milestone("Earlier work", "x", "Core", "x")
    ws.update_milestone(done["id"], {"status": "done"})
    ws.update_milestone(first["id"], {"status": "doing"})
    dropped = ws.add_milestone("Never mind", "x", "Extras", "x")
    ws.update_milestone(dropped["id"], {"status": "dropped"})
    ws.save_draft(title="First files", why="w", files=[{"path": "src/shop/base.py", "content": "x = 1\n"}], drafted_by="gemini-test",
                  milestone=first["id"])
    graph = living_map.plan_graph(ws)
    by = {n["id"]: n for n in graph["nodes"]}
    assert {(e["from"], e["to"]) for e in graph["edges"]} == {(first["id"], second["id"]), (second["id"], third["id"])}
    assert by[first["id"]]["state"] == "needs_you" and by[first["id"]]["needs"][0]["kind"] == "draft"      # a draft waits
    assert by[second["id"]]["state"] == "waiting" and by[second["id"]]["unmet"] == [first["id"]]
    assert by[third["id"]]["state"] == "waiting" and by[done["id"]]["state"] == "done" and by[dropped["id"]]["state"] == "dropped"
    assert by[second["id"]]["level"] == 1 and by[third["id"]]["level"] == 2 and by[first["id"]]["level"] == 0
    assert by[first["id"]]["origin"]["kind"] == "owner" and by[first["id"]]["origin"]["source"] == "ledger: milestone.added"
    assert by[first["id"]]["drafts"] == {"count": 1, "waiting": 1, "last_author": "gemini-test", "last_utc": by[first["id"]]["drafts"]["last_utc"]}
    history = {row["label"]: row for row in by[done["id"]]["evidence"]}["Status history"]
    assert history["items"] and history["items"][0].endswith(": done")
    assert all(row["source"] for n in graph["nodes"] for row in n["evidence"])
    assert {t["name"] for t in graph["tracks"]} == {"Core", "Extras"}


def test_a_ready_milestone_and_a_plan_larger_than_the_cap_are_capped_by_what_matters(tmp_path):
    ws, _ = shop(tmp_path)
    ids = [ws.add_milestone(f"Step {i}", "d", "Long", "done") ["id"] for i in range(80)]
    for i in ids[:50]:
        ws.update_milestone(i, {"status": "done"})
    graph = living_map.plan_graph(ws)
    assert graph["counts"]["total"] == 80 and graph["counts"]["drawn"] == living_map.NODE_CAP
    ready = [n for n in graph["nodes"] if n["state"] == "ready"]
    assert ready and all(n["drawn"] for n in ready)                         # what can be worked on is always shown
    assert graph["tracks"][0]["more"] == 80 - living_map.NODE_CAP
    again = living_map.plan_graph(ws)
    assert [n["drawn"] for n in again["nodes"]] == [n["drawn"] for n in graph["nodes"]]


def test_the_origin_of_a_step_split_by_the_stuck_policy_and_one_the_owner_adopted(tmp_path):
    ws, _ = shop(tmp_path)
    parent = ws.add_milestone("Big thing", "d", "Core", "done")
    plan = ws.plan()
    plan["milestones"].insert(0, {"id": "bk1-s1", "title": "Small step", "detail": "d", "track": "Core", "done_when": "x", "status": "open",
                                  "parent_id": parent["id"], "breakdown_id": "bk1", "depends_on": []})
    plan["milestones"].insert(1, {"id": "bk2-s1", "title": "Other step", "detail": "d", "track": "Core", "done_when": "x", "status": "open",
                                  "parent_id": parent["id"], "breakdown_id": "bk2", "depends_on": []})
    _write_json(ws.home / "PLAN.json", plan)
    ws.ledger.append("breakdown.adopted", {"id": "bk1", "children": ["bk1-s1"], "by": "owner", "author": "m"})
    ws.ledger.append("breakdown.adopted", {"id": "bk2", "children": ["bk2-s1"], "by": "Runesmith (your setting)", "author": "m"})
    by = {n["id"]: n for n in living_map.plan_graph(ws)["nodes"]}
    assert by["bk1-s1"]["origin"]["kind"] == "breakdown" and by["bk1-s1"]["origin"]["text"] == "a breakdown you adopted"
    assert by["bk2-s1"]["origin"]["kind"] == "stuck_split" and "stuck-milestone setting" in by["bk2-s1"]["origin"]["text"]


# ------------------------------------------------------------------------------- stages and metrics --

def test_the_stage_counters_say_what_they_count_and_since_when(tmp_path):
    ws, _ = shop(tmp_path)
    round_record(ws, "failing", failing=["tests/test_checkout.py::test_checkout"])
    stages = {s["id"]: s for s in living_map.stages_view(ws)}
    assert list(stages) == ["map", "discover", "repair", "judge", "propose", "apply"]
    assert stages["map"]["count"] == 1 and stages["map"]["source"] == "ENVIRONMENT.json"
    assert stages["discover"]["count"] == 1 and "failing: shop" in stages["discover"]["extra"]
    assert all(s["definition"] and s["window"] and s["source"] for s in stages.values())
    assert stages["repair"]["count"] == 0 and stages["propose"]["window"] == "now"


def test_metrics_carry_their_sample_and_say_few_sessions_under_ten(tmp_path):
    ws, _ = shop(tmp_path)
    (ws.home / "sessions").mkdir(exist_ok=True)
    for i in range(12):
        _write_json(ws.home / "sessions" / f"s{i:02d}.json", {"key": f"s{i:02d}", "status": "public_pass", "strict_success": i % 2 == 0,
                                                              "cycle_seconds": 10, "calls": [{}] * 2, "utc_start": f"2026-10-05T09:{i:02d}:00Z"})
    metrics = living_map.metrics_view(ws)
    row = metrics["metrics"]["repair_yield"]
    assert row["n"] == 12 and not row["few"] and row["since"] == "2026-10-05T09:00:00Z" and row["value"] == 0.5
    assert row["source"] == "12 judged sessions in sessions/ since 09:00Z"
    for i in range(12):
        (ws.home / "sessions" / f"s{i:02d}.json").unlink()
    ws.__dict__.pop("_session_cache", None)
    assert living_map.metrics_view(ws)["metrics"]["repair_yield"]["few"] is True


# ------------------------------------------------------------------------- what the adversarial review found --

def mapped(tmp_path: Path, files: dict[str, str], name: str = "proj", *, python: bool = True) -> tuple[Workspace, Path]:
    """A project made of exactly these files (and a pyproject.toml, unless ``python`` is off), mapped."""
    root = tmp_path / name
    files = ({"pyproject.toml": '[project]\nname = "proj"\n'} if python else {}) | files
    for rel, text in files.items():
        write(root, rel, text)
    ws = Workspace(root, tmp_path / (name + "-home"))
    ws.map_environment(probe=False)
    return ws, root


def test_a_milestone_that_names_a_url_a_network_path_or_a_drive_path_gets_no_badge_and_touches_no_disk(tmp_path, monkeypatch):
    ws, root = shop(tmp_path)
    for name in ("guide.md", "notes.md", "todo.md"):
        write(root, name, "# " + name + "\n")
    ws.add_milestone("Follow the guide", "See https://example.com/guide.md, \\\\fileserver\\share\\notes.md and C:\\work\\todo.md "
                     "for the format; then fix src/shop/cart.py and (README.md).", "Plan", "done when it matches")
    asked: list[str] = []
    real = Path.resolve

    def spy(self, *args, **kwargs):
        if any(word in str(self) for word in ("example.com", "fileserver", "todo.md")):
            asked.append(str(self))
            raise AssertionError("resolve() was handed text taken from a milestone: " + str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", spy)
    by = nodes(living_map.structure_view(ws))
    assert not asked
    for name in ("guide.md", "notes.md", "todo.md"):                        # the last word of a URL or a network path is not a file here
        assert not [b for b in by[name]["badges"] if b["kind"] == "milestone"], name
    for name in ("src/shop/cart.py", "README.md"):                          # a plain relative name still is
        assert [b for b in by[name]["badges"] if b["kind"] == "milestone"], name


def test_the_path_helper_is_lexical_and_refuses_what_leaves_the_folder(tmp_path, monkeypatch):
    calls: list[str] = []
    real = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: calls.append(str(self)) or real(self, *a, **k))
    root, under = tmp_path / "proj", living_map._under
    assert under(root, root, "src/a.py") == "src/a.py"
    assert under(root, root, "src\\a.py") == "src/a.py"
    assert under(root, root, "./src/a.py") == "src/a.py"
    assert under(root, root / "sub", "x.py") == "sub/x.py"
    for bad in ("../x.py", "src/../../x.py", "/etc/x.py", "\\\\host\\share\\x.py", "//host/share/x.py", "C:\\x.py", "C:x.py", "", ".", "a\x00b.py"):
        assert under(root, root, bad) is None, bad
    assert under(root / "sub", root, "x.py") is None                        # outside the object's folder
    if os.name == "nt":                                                      # a drive's case is not a different folder
        assert under(root, Path(str(root).upper()), "src/a.py") == "src/a.py"
    assert not calls                                                         # nothing here asked the disk or the network


def test_imports_are_read_for_the_test_files_first_so_the_cap_never_hides_a_test(tmp_path, monkeypatch):
    files = {f"src/pkg/m{i}.py": "X = 1\n" for i in range(6)}
    files |= {"src/pkg/__init__.py": "", "tests/test_one.py": "from pkg.m0 import X\n"}
    ws, _ = mapped(tmp_path, files)
    monkeypatch.setattr(living_map, "PARSE_CAP", 2)
    view = living_map.structure_view(ws)
    by, edges = nodes(view), {(e["from"], e["to"], e["type"]) for e in view["edges"]}
    assert ("tests/test_one.py", "src/pkg/m0.py", "tests") in edges           # the test sorts last, and is read first
    assert view["imports_not_read"] == 6 and "6 code files" in view["sentence"] and "past the first 2" in view["sentence"]
    assert by["src/pkg/m1.py"]["state"]["band"] == "minimal"                 # every test file was read: none reaches it


def test_a_test_file_that_cannot_be_read_makes_untested_modules_unknown_not_minimal(tmp_path):
    ws, root = shop(tmp_path)
    write(root, "tests/test_values.py", "from shop.lonely import VALUE\nprint 'a syntax error in Python 3'\n")
    view = living_map.structure_view(ws)
    by = nodes(view)
    lonely = by["src/shop/lonely.py"]["state"]
    assert lonely["band"] == "unknown"
    assert "Some test files could not be read, so it cannot say that no test reaches this module." in lonely["reason"]
    assert "tests/test_values.py" in lonely["reason"] and "could not parse" in lonely["reason"]
    assert view["parse_errors"] == ["tests/test_values.py"] and view["imports_not_read"] == 1
    assert "1 with a syntax error" in view["sentence"]
    imports = {row["label"]: row for row in by["tests/test_values.py"]["evidence"]}["Imports"]
    assert imports["value"].startswith("not read") and not imports["items"]    # never "no project file" for a file that was not read
    assert by["src/shop/cart.py"]["state"]["band"] == "unknown" and "No test run is recorded" in by["src/shop/cart.py"]["state"]["reason"]


def test_test_files_past_the_cap_or_too_large_also_make_untested_modules_unknown(tmp_path, monkeypatch):
    ws, root = shop(tmp_path)
    monkeypatch.setattr(living_map, "PARSE_CAP", 2)                          # three test files: the last in order is not read
    view = living_map.structure_view(ws)
    state = nodes(view)["src/shop/lonely.py"]["state"]
    assert state["band"] == "unknown" and "tests/test_prices.py (past the first 2 code files read)" in state["reason"]
    monkeypatch.setattr(living_map, "PARSE_CAP", 2500)
    write(root, "tests/test_big.py", "from shop.lonely import VALUE\n" + "# padding\n" * 150_000)      # a little over 1.5 MB
    view = living_map.structure_view(ws)
    state = nodes(view)["src/shop/lonely.py"]["state"]
    assert state["band"] == "unknown" and "larger than 1.5 MB" in state["reason"] and "tests/test_big.py" in state["reason"]
    assert view["imports_not_read"] >= 1


def test_a_test_named_for_a_module_links_to_the_nearest_module_of_that_name_or_to_none(tmp_path):
    files = {"pkg_a/models.py": "A = 1\n", "pkg_b/models.py": "B = 1\n", "pkg_a/utils.py": "U = 1\n", "pkg_b/utils.py": "V = 1\n",
             "pkg_c/core.py": "C = 1\n", "other/core.py": "O = 1\n", "pkg_d/flow.py": "F = 1\n", "pkg_e/flow.py": "G = 1\n",
             "tests/pkg_a/test_models.py": "def test_a():\n    pass\n",            # mirrors pkg_a
             "tests/test_utils.py": "from pkg_a.utils import U\n\n\ndef test_u():\n    assert U\n",   # the name fits two, the import says one
             "pkg_c/tests/test_core.py": "def test_c():\n    pass\n",              # inside the package
             "pkg_d/test_flow.py": "def test_f():\n    pass\n"}                   # next to the module
    ws, root = mapped(tmp_path, files)
    age(root)
    round_record(ws, "green", when_utc=utc(60))
    view = living_map.structure_view(ws)
    reach = {(e["from"], e["to"]): e["how"] for e in view["edges"] if e["type"] == "tests"}
    assert set(reach) == {("tests/pkg_a/test_models.py", "pkg_a/models.py"), ("tests/test_utils.py", "pkg_a/utils.py"),
                          ("pkg_c/tests/test_core.py", "pkg_c/core.py"), ("pkg_d/test_flow.py", "pkg_d/flow.py")}
    assert all(h.startswith("named for it") for h in reach[("tests/pkg_a/test_models.py", "pkg_a/models.py")])
    assert not any(h.startswith("named for it") for h in reach[("tests/test_utils.py", "pkg_a/utils.py")])   # the name was ambiguous: dropped
    by = nodes(view)
    assert by["pkg_a/models.py"]["state"]["band"] == "optimal"
    assert by["pkg_b/models.py"]["state"]["band"] == "minimal"               # a test of another package's models does not bless this one


def test_a_module_is_stale_when_anything_it_imports_changed_after_the_run(tmp_path):
    ws, root = shop(tmp_path)
    write(root, "src/shop/summary.py", "from shop import cart\n")             # summary imports cart, which imports prices
    write(root, "tests/test_summary.py", "from shop.summary import cart\n")
    age(root)
    round_record(ws, "green", when_utc=utc(-3600))
    assert nodes(living_map.structure_view(ws))["src/shop/summary.py"]["state"]["band"] == "optimal"
    write(root, "src/shop/prices.py", "def price():\n    return 2\n")
    by = nodes(living_map.structure_view(ws))
    own = by["src/shop/prices.py"]["state"]
    assert own["band"] == "unknown" and own["reason"].startswith("Changed since the last test run: src/shop/prices.py changed at")
    for name in ("cart", "checkout", "summary"):                              # cart and checkout import it; summary does so through cart
        state = by[f"src/shop/{name}.py"]["state"]
        assert state["band"] == "unknown", name
        assert "src/shop/prices.py changed at" in state["reason"] and f"src/shop/{name}.py imports it, directly or through other files" in state["reason"]
    assert by["src/shop/lonely.py"]["state"]["band"] == "minimal"             # nothing tests it, run or no run
    words = by["tests/test_cart.py"]["test"]["words"]                         # its result was of the old prices.py too
    assert by["tests/test_cart.py"]["test"]["result"] == "unknown" and "src/shop/prices.py changed since the last test run" in words


SHARED = [("tests/conftest.py", "import pytest\n"), ("pytest.ini", "[pytest]\naddopts = -q\n"),
          ("pyproject.toml", '[project]\nname = "shop"\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'),
          ("setup.cfg", "[tool:pytest]\naddopts = -q\n"), ("tox.ini", "[pytest]\naddopts = -q\n")]


@pytest.mark.parametrize("rel,text", SHARED, ids=[row[0] for row in SHARED])
def test_a_changed_or_new_conftest_or_pytest_configuration_makes_every_tested_module_unknown(tmp_path, rel, text):
    ws, root = shop(tmp_path)
    age(root)
    round_record(ws, "green", when_utc=utc(-3600))
    assert nodes(living_map.structure_view(ws))["src/shop/cart.py"]["state"]["band"] == "optimal"
    write(root, rel, text)
    by = nodes(living_map.structure_view(ws))
    for name in ("cart", "prices", "checkout"):                               # none of them imports the changed file
        state = by[f"src/shop/{name}.py"]["state"]
        assert state["band"] == "unknown", (rel, name)
        assert f"{rel} changed at" in state["reason"]
        assert "a conftest or pytest configuration changed after the run" in state["reason"]
    assert by["src/shop/lonely.py"]["state"]["band"] == "minimal"
    assert by["tests/test_cart.py"]["test"]["result"] == "unknown"            # a configuration or a conftest touches every test's result


@pytest.mark.parametrize("rel,text,reached", [
    ("tests/test_cart.py", "from shop.cart import Cart\n\n\ndef test_cart():\n    assert Cart is not None\n", {"cart"}),                 # changed
    ("tests/test_extra.py", "from shop import prices\n\n\ndef test_extra():\n    assert prices.price()\n", {"prices"})],         # new
    ids=["a changed test file", "a new test file"])
def test_a_changed_or_new_test_file_makes_unknown_only_the_modules_it_reaches(tmp_path, rel, text, reached):
    ws, root = shop(tmp_path)
    age(root)
    round_record(ws, "green", when_utc=utc(-3600))
    write(root, rel, text)
    by = nodes(living_map.structure_view(ws))
    for name in ("cart", "prices", "checkout"):
        state = by[f"src/shop/{name}.py"]["state"]
        if name in reached:
            assert state["band"] == "unknown" and f"{rel} changed at" in state["reason"], name
        else:
            assert state["band"] == "optimal", (rel, name)                    # no test that reaches it changed
    assert by["tests/test_checkout.py"]["test"]["result"] == "passed"         # another test file's result stands
    assert by[rel]["test"]["result"] == "unknown"


def test_a_change_to_a_file_that_is_neither_a_test_nor_pytest_configuration_keeps_the_results(tmp_path):
    ws, root = shop(tmp_path)
    age(root)
    round_record(ws, "green", when_utc=utc(-3600))
    write(root, "pyproject.toml", '[project]\nname = "shop"\nversion = "2"\n')   # no pytest section
    write(root, "README.md", "# shop, again\n")
    write(root, "src/shop/lonely.py", "VALUE = 2\n")
    by = nodes(living_map.structure_view(ws))
    for name in ("cart", "prices", "checkout"):
        assert by[f"src/shop/{name}.py"]["state"]["band"] == "optimal", name
    assert by["tests/test_cart.py"]["test"]["result"] == "passed"


def test_the_list_cut_keeps_what_is_drawn_and_what_matters_most_and_stays_in_id_order(tmp_path, monkeypatch):
    monkeypatch.setattr(living_map, "NODE_CAP", 12)
    monkeypatch.setattr(living_map, "LIST_CAP", 30)
    files = {f"pkg/m{i:02d}.py": "X = 1\n" * (1 + i % 5) for i in range(60)}
    files |= {"zz/last.py": "VALUE = 1\n", "tests/test_zlast.py": "from zz.last import VALUE\n\n\ndef test_x():\n    assert VALUE == 2\n"}
    ws, root = mapped(tmp_path, files)
    age(root)
    round_record(ws, "failing", failing=["tests/test_zlast.py::test_x"])
    view = living_map.structure_view(ws)
    ids = [n["id"] for n in view["nodes"]]
    assert len(ids) == 30 and ids == sorted(ids) and view["counts"]["listed"] == 30 and view["counts"]["files"] == 63
    by = nodes(view)
    assert by["tests/test_zlast.py"]["state"]["band"] == "bad" and by["zz/last.py"]["state"]["band"] == "bad"
    assert by["tests/test_zlast.py"]["drawn"] and by["zz/last.py"]["drawn"]  # failing parts sort last by name, and are listed all the same
    assert view["counts"]["drawn"] == sum(g["drawn"] for g in view["groups"])  # everything a folder says it draws is in the list
    listed = set(ids)
    assert all(i in listed for g in view["groups"] for i in g["more_ids"])    # no folder points at a part the list does not carry


def test_evidence_is_built_for_the_listed_nodes_only_and_the_folder_is_scanned_once(tmp_path, monkeypatch):
    files = {"src/pkg/__init__.py": "", "src/pkg/core.py": "def f():\n    return 1\n"}
    for i in range(70):
        files[f"src/pkg/m{i:02d}.py"] = "from pkg import core\n"
        files[f"tests/test_m{i:02d}.py"] = f"from pkg.m{i:02d} import core\n"
    ws, _ = mapped(tmp_path, files)
    monkeypatch.setattr(living_map, "LIST_CAP", 40)
    built: list[str] = []
    scans: list[str] = []
    real_evidence, real_scan = living_map._evidence, living_map._scan
    monkeypatch.setattr(living_map, "_evidence", lambda ws_, node, *a, **k: built.append(node["id"]) or real_evidence(ws_, node, *a, **k))
    monkeypatch.setattr(living_map, "_scan", lambda root: scans.append(str(root)) or real_scan(root))
    started = time.perf_counter()
    view = living_map.structure_view(ws)
    took = time.perf_counter() - started
    assert len(view["nodes"]) == 40 and view["counts"]["files"] == 143
    assert sorted(built) == sorted(n["id"] for n in view["nodes"])            # no part nobody can open has its facts built
    assert all(n["evidence"] for n in view["nodes"])
    assert len(scans) == 1                                                    # the folder is read from disk once
    assert took < 30


def test_a_long_adversarial_javascript_file_parses_fast_and_real_imports_still_resolve(tmp_path):
    names = ", ".join(f"name{i}" for i in range(80))                         # a list of names longer than 300 characters
    text = f"import {{ {names} }} from './util.js';\nexport * from './more';\nimport './side';\nconst a = require('./req');\n"
    text += ("import " * 4000) + ("export " * 4000) + ("import\n" * 4000)       # words with no path after them, for the rest of the file
    started = time.perf_counter()
    specs = living_map._js_specs(text)
    took = time.perf_counter() - started
    assert took < 1.0, took
    assert specs == [("./util.js", 1), ("./more", 2), ("./side", 3), ("./req", 4)]
    ws, _ = mapped(tmp_path, {"package.json": '{"name": "w"}', "src/util.js": "export const x = 1;\n", "src/main.js": text}, python=False)
    edges = {(e["from"], e["to"]) for e in living_map.structure_view(ws)["edges"]}
    assert ("src/main.js", "src/util.js") in edges


def test_a_probe_and_a_round_with_the_same_second_follow_the_rule_the_ring_uses(tmp_path):
    ws, root = shop(tmp_path)
    age(root)
    stamp = utc(-300)
    round_record(ws, "failing", when_utc=stamp, failing=["tests/test_checkout.py::test_checkout"])

    def probe(measured: str = stamp, **fields) -> dict:
        env = ws.environment_map()
        env["objects"][0]["probe"], env["objects"][0]["measured_utc"] = fields, measured
        _write_json(ws.home / "ENVIRONMENT.json", env)
        return ws.environment_map()["objects"][0]

    obj = probe(runner="pytest", collected=3, passed=3, failed=0, errors=0, exit_code=0)
    assert ws.object_statuses()[obj["name"]] == "failing"                    # at a tie a green probe never overrides the round
    run = living_map.latest_run(ws, obj)
    assert run["source"] == "round" and run["outcome"] == "failed" and run["status"] == "failing"
    assert nodes(living_map.structure_view(ws))["src/shop/checkout.py"]["state"]["band"] == "bad"
    obj = probe(runner="pytest", collected=3, passed=2, failed=1, errors=0, exit_code=1)       # a failing probe does win a tie
    assert ws.object_statuses()[obj["name"]] == "failing" and living_map.latest_run(ws, obj)["source"] == "probe"
    obj = probe(runner="unittest", collected=3, passed=3, failed=0, errors=0, exit_code=0)     # so does a unittest probe
    assert living_map.latest_run(ws, obj)["source"] == "probe" and living_map.latest_run(ws, obj)["scope"] == "subset"
    obj = probe(runner="pytest", error="timed out after 60 s")                                  # and one that could not finish
    assert ws.object_statuses()[obj["name"]] == "timed_out" and living_map.latest_run(ws, obj)["source"] == "probe"
    obj = probe(utc(-100), runner="pytest", collected=3, passed=3, failed=0, errors=0, exit_code=0)   # a green probe a later second wins
    run = living_map.latest_run(ws, obj)
    assert ws.object_statuses()[obj["name"]] == "green" and run["source"] == "probe" and run["outcome"] == "passed"


def test_discover_says_a_failing_probe_was_found_by_the_probe_not_in_a_round(tmp_path):
    ws, _ = shop(tmp_path)
    env = ws.environment_map()
    env["objects"][0]["probe"] = {"runner": "pytest", "collected": 3, "passed": 2, "failed": 1, "errors": 0, "exit_code": 1}
    env["objects"][0]["measured_utc"] = "2026-10-05T13:11:00Z"
    _write_json(ws.home / "ENVIRONMENT.json", env)
    assert not (ws.home / "WORK.json").exists()
    stage = {s["id"]: s for s in living_map.stages_view(ws)}["discover"]
    assert stage["count"] == 1 and stage["unit"] == "objects with failing tests"
    assert "latest round" not in stage["window"] and stage["window"] == "the map's test probe, 2026-10-05 13:11Z; no round has run yet"
    assert stage["source"].startswith("ENVIRONMENT.json") and "WORK.json" not in stage["source"] and stage["utc"] == "2026-10-05T13:11:00Z"
    assert stage["extra"] == "failing: shop (found by the map's test probe)"
    assert "map's own test probe" in stage["definition"]
    # a round that found the same object keeps the older words
    round_record(ws, "failing", when_utc="2026-10-05T13:00:00Z", failing=["tests/test_checkout.py::test_checkout"])
    newer = {s["id"]: s for s in living_map.stages_view(ws)}["discover"]      # the probe is the newer evidence, and says so
    assert newer["count"] == 1 and newer["window"] == "the map's test probe, 2026-10-05 13:11Z, newer than the latest round (13:00Z)"
    assert newer["source"] == "ENVIRONMENT.json (the map's test probe)"
    round_record(ws, "failing", when_utc="2026-10-05T14:00:00Z", failing=["tests/test_checkout.py::test_checkout"])
    only_round = {s["id"]: s for s in living_map.stages_view(ws)}["discover"]
    assert only_round["window"] == "the latest round, 2026-10-05 14:00Z" and only_round["extra"] == "failing: shop"
    assert only_round["definition"].startswith("objects whose tests failed in the latest round") and only_round["unit"] == "objects with work found"


def test_an_object_put_on_the_never_touch_list_is_not_read_even_before_the_next_map(tmp_path, monkeypatch):
    ws, _ = shop(tmp_path)
    name = ws.environment_map()["objects"][0]["name"]
    assert living_map.structure_view(ws, name)["counts"]["files"] == 10
    ws.update_settings({"exclude": [name]})
    assert ws.environment_map()["objects"][0]["kind"] != "excluded"          # the map file still lists it as mapped
    monkeypatch.setattr(living_map, "_scan", lambda root: (_ for _ in ()).throw(AssertionError("an excluded object was read")))
    for ask in (name, None):
        view = living_map.structure_view(ws, ask)
        assert view["empty"] and view["nodes"] == [] and "never-touch" in view["sentence"]


def test_the_never_touch_list_matches_an_object_by_its_name_its_folder_or_the_folder_above_it(tmp_path):
    files = {}
    for project in ("billing", "web"):
        files |= {f"services/{project}/src/{project}/core.py": "X = 1\n", f"services/{project}/tests/test_core.py": "def test_x():\n    pass\n",
                  f"services/{project}/pyproject.toml": '[project]\nname = "x"\n'}
    ws, _ = mapped(tmp_path, files, "park", python=False)
    names = sorted(o["name"] for o in ws.environment_map()["objects"])
    assert names == ["services/billing", "services/web"], names
    assert living_map.structure_view(ws, "services/billing")["counts"]["files"] == 3
    ws.update_settings({"exclude": ["billing"]})                              # the folder's own name, as the mapper matches it
    assert living_map.structure_view(ws, "services/billing")["empty"] and living_map.structure_view(ws, "services/web")["counts"]["files"] == 3
    assert living_map.structure_view(ws)["counts"]["files"] == 3              # one object left that is not on the list: it is the one
    ws.update_settings({"exclude": ["services"]})                             # or a folder above it
    assert living_map.structure_view(ws, "services/web")["empty"]


def test_metrics_show_no_band_under_ten_sessions_and_the_trial_arms_name_their_window(tmp_path):
    ws, _ = shop(tmp_path)
    (ws.home / "sessions").mkdir(exist_ok=True)
    for i in range(3):
        _write_json(ws.home / "sessions" / f"s{i}.json", {"key": f"s{i}", "status": "public_pass", "strict_success": True, "cycle_seconds": 10,
                                                          "calls": [{}] * 2, "utc_start": f"2026-10-05T09:0{i}:00Z"})
    row = living_map.metrics_view(ws)["metrics"]["repair_yield"]
    assert row["few"] and row["value"] == 1.0 and row["band"] == "unknown"   # three sessions colour nothing
    ws.__dict__.pop("_session_cache", None)
    g0 = generations.active(ws.home)
    child = candidate(ws, g0, "arm")
    Trial(incumbent=g0, candidate=child["id"], seed="s", opened_utc="2026-10-05T08:00:00Z").save(ws.home / "TRIAL.json")
    for i, arm in enumerate(("incumbent", "candidate")):
        _write_json(ws.home / "sessions" / f"a{i}.json", {"key": f"a{i}", "status": "public_pass", "strict_success": True, "cycle_seconds": 10,
                                                          "calls": [{}] * 2, "utc_start": f"2026-10-05T10:0{i}:00Z", "trial_arm": arm})
    ws.__dict__.pop("_session_cache", None)
    arms = living_map.metrics_view(ws)["metrics"]["repair_yield"]["arms"]
    assert arms["candidate"]["since"] == "2026-10-05T08:00:00Z" and arms["candidate"]["n"] == 1 and arms["candidate"]["few"]
    assert arms["candidate"]["window"] == "1 judged session since 2026-10-05 08:00Z"


def test_made_active_shows_the_latest_activation_of_a_generation(tmp_path, monkeypatch):
    ws, _ = shop(tmp_path)
    g0 = generations.active(ws.home)
    events = [{"kind": "generation.activated", "utc": "2026-10-01T10:00:00Z", "data": {"id": g0, "previous": None}},
              {"kind": "generation.activated", "utc": "2026-10-03T11:30:00Z", "data": {"id": g0, "previous": "someone", "evidence": "owner's choice"}}]
    monkeypatch.setattr(living_map, "ledger_events", lambda ws_, *kinds: events)
    station = next(s for s in living_map.lineage_view(ws)["stations"] if s["id"] == g0)
    assert station["activated_utc"] == "2026-10-03T11:30:00Z"


def test_a_hub_module_carries_capped_lists_and_the_true_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(living_map, "DETAIL_CAP", 3)
    files = {"core.py": "def f():\n    return 1\n", "README.md": "# hub\n"}
    for i in range(8):
        files[f"m{i}.py"] = "from core import f\n"
        files[f"tests/test_hub{i}.py"] = "from core import f\n"
    ws, _ = mapped(tmp_path, files)
    by = nodes(living_map.structure_view(ws))
    hub = by["core.py"]
    assert hub["imported_by"] == [f"m{i}.py" for i in range(3)] and hub["imported_by_count"] == 8
    assert [t["id"] for t in hub["tests"]] == [f"tests/test_hub{i}.py" for i in range(3)] and hub["tests_count"] == 8
    rows = {row["label"]: row for row in hub["evidence"]}
    assert rows["Imported by"]["items"] == [f"m{i}.py" for i in range(3)] + ["… and 5 more"]
    assert rows["Tests that reach it"]["items"][-1] == "… and 5 more" and len(rows["Tests that reach it"]["items"]) == 4
    assert not any("more" in x for x in hub["imported_by"] + [t["id"] for t in hub["tests"]])      # the id lists hold ids only
    small = by["m0.py"]
    assert small["imports"] == ["core.py"] and small["imports_count"] == 1 and small["imported_by_count"] == 0 and small["tests_count"] == 0
    assert "reaches_count" not in small and "tests_count" not in by["tests/test_hub0.py"]
    test = by["tests/test_hub0.py"]
    assert test["reaches"] == ["core.py"] and test["reaches_count"] == 1 and test["imports_count"] == 0
    assert by["README.md"]["imports_count"] == 0 and by["README.md"]["imported_by_count"] == 0


# ----------------------------------------------------------------------------------------------- endpoints --

@pytest.fixture()
def studio_with_shop(tmp_path):
    import threading
    from test_studio import call
    from runesmith.app.server import Studio, bind
    _, root = shop(tmp_path / "area")
    studio = Studio(root)
    httpd = bind(studio, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    studio.ws.map_environment(probe=False)
    yield studio, call
    studio.closing = True
    studio.close()
    httpd.shutdown()
    httpd.server_close()


def test_endpoints_serve_the_builders_and_keep_the_old_fields_when_one_fails(studio_with_shop, monkeypatch):
    studio, call = studio_with_shop
    status, body, _ = call(studio, "GET", "/api/map/structure")
    assert status == 200 and body["schema"] == "runesmith.map.structure.v1" and body["counts"]["files"] == 10
    assert call(studio, "GET", "/api/map/structure?object=nothing")[0] == 404
    status, env, _ = call(studio, "GET", "/api/map/environment")
    assert status == 200 and env["map"]["objects"] and env["living_problems"] == []
    status, dev, _ = call(studio, "GET", "/api/map/development")
    assert status == 200 and dev["graph"]["nodes"] == [] and dev["lineage_ordered"]["stations"] and dev["lineage"]
    status, self_view, _ = call(studio, "GET", "/api/map/self")
    assert status == 200 and self_view["lineage_ordered"]["stations"] and set(self_view["metrics"]["metrics"]) == set(living_map.METRIC_DEFINITIONS)
    status, ops, _ = call(studio, "GET", "/api/map/operations")
    assert status == 200 and [s["id"] for s in ops["stages"]] == ["map", "discover", "repair", "judge", "propose", "apply"] and ops["pipeline"]
    # a builder that fails leaves the older fields and says what it could not read
    monkeypatch.setattr(living_map, "plan_graph", lambda ws: (_ for _ in ()).throw(RuntimeError("damaged PLAN.json")))
    monkeypatch.setattr(living_map, "lineage_view", lambda ws: (_ for _ in ()).throw(RuntimeError("damaged manifest")))
    status, dev, _ = call(studio, "GET", "/api/map/development")
    assert status == 200 and dev["graph"] is None and dev["lineage_ordered"] is None and dev["objects"] is not None and dev["lineage"]
    assert any("damaged PLAN.json" in line for line in dev["living_problems"]) and any("the plan graph" in line for line in dev["living_problems"])


def test_the_map_endpoints_read_and_write_nothing(studio_with_shop):
    studio, call = studio_with_shop
    before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in studio.ws.home.rglob("*") if p.is_file()}
    for path in ("/api/map/environment", "/api/map/structure", "/api/map/self", "/api/map/development", "/api/map/operations"):
        assert call(studio, "GET", path)[0] == 200
    after = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in studio.ws.home.rglob("*") if p.is_file()}
    changed = {p.relative_to(studio.ws.home).as_posix() for p in set(before) | set(after) if before.get(p) != after.get(p)}
    # the Studio's own bookkeeping may move (its lock and its session files); records, maps and the ledger may not
    assert not [c for c in changed if c in ("ledger.jsonl", "WORK.json", "PLAN.json", "ENVIRONMENT.json", "runesmith.json")
                or c.startswith(("drafts/", "experience/", "generations/"))], changed


# ----------------------------------------------------------------------- the browser fixture, the doc and the words --

VIEWS = Path(__file__).resolve().parents[1] / "runesmith" / "app" / "static" / "js" / "views"
DOC = Path(__file__).resolve().parents[1] / "docs" / "MAP_LOGIC.md"


def _keys(rows: list[dict]) -> set[str]:
    return set().union(*(set(r) for r in rows)) if rows else set()


def test_the_browser_fixture_has_the_shape_the_builders_produce(tmp_path):
    """The loops (B28 to B31) serve tests/fixtures/living_map.json for the map's endpoints. If a builder gains or loses a field,
    regenerate it with ``python tests/living_map_fixture.py``; until then this fails."""
    import living_map_fixture
    committed = json.loads((Path(__file__).parent / "fixtures" / "living_map.json").read_text(encoding="utf-8"))
    fresh = living_map_fixture.build(tmp_path)
    s_old, s_new = committed["structure"], fresh["structure"]
    assert set(s_old) == set(s_new)
    for part in ("nodes", "groups", "edges"):
        assert _keys(s_old[part]) == _keys(s_new[part]), part
    assert set(s_old["run"]) == set(s_new["run"]) and set(s_old["counts"]) == set(s_new["counts"])
    g_old, g_new = committed["development"]["graph"], fresh["development"]["graph"]
    assert set(g_old) == set(g_new)
    for part in ("nodes", "edges", "tracks"):
        assert _keys(g_old[part]) == _keys(g_new[part]), part
    assert _keys(committed["development"]["lineage_ordered"]["stations"]) == _keys(fresh["development"]["lineage_ordered"]["stations"])
    old_rungs = {rung for ladder in committed["development"]["ladders"].values() for rung in ladder}
    new_rungs = {rung for ladder in fresh["development"]["ladders"].values() for rung in ladder}
    assert old_rungs == new_rungs
    assert set(committed["environment"]) == set(fresh["environment"]) and set(committed["operations"]) == set(fresh["operations"])
    assert set(committed["self"]) == set(fresh["self"]) and set(committed["self"]["metrics"]) == set(fresh["self"]["metrics"])
    assert _keys(committed["operations"]["stages"]) == _keys(fresh["operations"]["stages"])
    assert committed["development"]["living_problems"] == [] and fresh["development"]["living_problems"] == []


def _table_rows() -> list[dict[str, str]]:
    text = DOC.read_text(encoding="utf-8")
    block = text[text.index("## 7. The Automate mapping"):text.index("## 8.")]
    rows = []
    for line in block.splitlines():
        if line.startswith("| ") and not line.startswith("| ---") and not line.startswith("| Part"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(dict(zip(("part", "ids", "request", "site", "confirmation"), cells)))
    return rows


def test_the_automate_table_matches_the_code():
    """MAP_LOGIC.md section 7: every control in the table exists in map-parts.js and the other way round; every setting it names is
    a real setting; every endpoint it names is a real route; and the places it says send the same request still contain it."""
    import re
    from runesmith.app import server
    from runesmith.app.workspace import SETTING_TYPES
    rows = _table_rows()
    assert len(rows) >= 25
    parts = (VIEWS / "map-parts.js").read_text(encoding="utf-8")
    registry = parts[parts.index("const REG = {"):parts.index("const NEEDS")]
    in_code = set(re.findall(r"^  (\w+): \(S, ctx", registry, re.M)) - {"none"}
    in_doc = set()
    for row in rows:
        in_doc |= {i.strip("` ") for i in row["ids"].split(",") if i.strip("` ") and i.strip("` ") != "(none)"}
    assert in_doc == in_code, (in_doc ^ in_code)
    routes = [(verb, pattern) for verb, pattern, _ in server.ROUTES]
    sites = {name: (VIEWS / name).read_text(encoding="utf-8") for name in ("settings.js", "home.js", "goals.js", "improve.js", "map.js")}
    body_keys = set(SETTING_TYPES) | {"title", "detail", "track", "done_when", "allow_apply"}
    for row in rows:
        for method, path in re.findall(r"(GET|POST) (/api/[\w/\-{}]+)", row["request"]):
            probe = re.sub(r"\{[^}]*\}", "x1", path)
            assert any(verb == method and pattern.fullmatch(probe) for verb, pattern in routes), (row["ids"], method, path)
            literal = path.split("{")[0]
            named = re.findall(r"([\w-]+\.js)", row["site"])
            if named:
                assert any(literal in sites[name] for name in named if name in sites), (row["ids"], literal, named)
        for body in re.findall(r"\{([a-z_, ]+)\}", row["request"]):
            for key in (k.strip() for k in body.split(",")):
                assert key in body_keys or key in ("generation", "incumbent", "milestone"), (row["ids"], key)
    assert not [r for r in rows if not r["confirmation"]]


def test_the_confirmations_the_map_repeats_are_the_owners_own_words():
    """A control the owner already confirms elsewhere asks with the same words here (docs/MAP_LOGIC.md, section 7)."""
    parts = (VIEWS / "map-parts.js").read_text(encoding="utf-8")
    sources = {name: (VIEWS / name).read_text(encoding="utf-8") for name in ("goals.js", "improve.js", "home.js", "settings.js")}
    pairs = [
        ("goals.js", "Apply checked drafts automatically in this folder?"),
        ("goals.js", "It writes only when a draft passes both its own tests and your acceptance checks for the milestone. You can turn this off here at any time; backups and Undo stay available."),
        ("goals.js", "Allow automatic apply"),
        ("goals.js", "Let Runesmith approve checks itself?"),
        ("goals.js", "Runesmith then asks for acceptance checks for ready milestones and approves them only when they pass every test: tried on your project, no problems it found itself, and a second model working out the same expected values. Otherwise it turns them down with the reason and asks again, twice at most, then leaves them for you. Checks you approved are never replaced by it. You can read and replace any of its checks."),
        ("goals.js", "Turn on the check autopilot"),
        ("goals.js", "Name the files or folders Runesmith may write first, for example: src, tests. A . means the whole folder."),
        ("improve.js", "is checked (digests, allowed imports, a confined smoke test), frozen next to your active generation, and put on trial against it. It becomes active only if it wins on your own work."),
        ("improve.js", "Adopt and start the trial"),
        ("improve.js", "This is your choice, recorded as such in the ledger. It skips the trial, so use it to roll back to an earlier generation rather than to promote an untested one. An open trial is closed by it."),
        ("improve.js", "Stop this trial?"),
        ("improve.js", "stays active and"),
        ("improve.js", "is not used. The counts so far are kept, and the trial is recorded as closed by your choice."),
        ("improve.js", "Trial stopped; what runs is unchanged."),
        ("home.js", "Fix the failing tests?"),
        ("home.js", "Runesmith adds a milestone, “Make the failing tests pass”. Your"),
        ("home.js", "test file(s) are frozen as they are now and decide when it is done."),
        ("home.js", "You review the fix and apply it yourself."),
        ("home.js", "Fixing the failing tests: follow it in Goals & plan and Activity."),
        ("settings.js", "This executes the project’s own code, on a throwaway copy of the folder, so nothing is written into it. Only for projects you trust: the copy is not a security boundary."),
    ]
    for source, fragment in pairs:
        assert fragment in sources[source], (source, fragment)
        assert fragment in parts, ("the map's own copy", fragment)


def test_the_map_files_never_print_null_or_read_a_button_after_waiting():
    """Two browser slips tests/test_static_js_hygiene.py already guards, named here for the new files."""
    from test_static_js_hygiene import null_appends, target_after_await
    for name in ("map.js", "map-parts.js", "map-layout.js", "map-structure.js", "map-self.js", "map-plan.js", "map-ops.js"):
        text = (VIEWS / name).read_text(encoding="utf-8")
        assert not null_appends(text) and not target_after_await(text), name
