"""Where the Living map puts every part (docs/MAP_LOGIC.md, "Layout"): geometry checks on fixture projects, with no browser.

The layout is pure arithmetic in ``runesmith/app/static/js/views/map-layout.js``. Each case here is built by the real Python builders
(``structure_view``, ``plan_graph``) on a fixture folder, handed to ``tests/map_layout_dump.mjs`` (Node runs the same file the page
loads) and checked as plain numbers: no two names overlap, the same drawing twice and for any order of the lists, the fixed order of
the sectors, tests next to the source they reach, links that keep out of the hub, a plan that reads left to right.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from runesmith.app import living_map
from runesmith.app.workspace import Workspace, _write_json

ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "tests" / "map_layout_dump.mjs"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed: the layout is checked by running map-layout.js")
TAU = 2 * math.pi


def write(root: Path, rel: str, text: str = "x = 1\n", pad: int = 0) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "# padding\n" * pad, encoding="utf-8", newline="\n")


def age(root: Path, seconds: float = 7200) -> None:
    old = time.time() - seconds
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))


def project(tmp_path: Path, name: str, files: dict[str, tuple[str, int]]) -> Workspace:
    root = tmp_path / name
    for rel, (text, pad) in files.items():
        write(root, rel, text, pad)
    age(root)
    ws = Workspace(root, tmp_path / f"{name}-home")
    ws.map_environment(probe=False)
    return ws


def fail_round(ws: Workspace, failing: list[str]) -> None:
    obj = next(o["name"] for o in ws.environment_map()["objects"])
    _write_json(ws.home / "WORK.json", {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600)), "outcome": "worked", "objects": {obj: "failing"},
        "details": {}, "summary": {}, "opportunities": [{"id": "o1", "object": obj, "failing_tests": failing, "issue": "x"}]})


# ------------------------------------------------------------------------------------------------ the fixtures --

def bakery(tmp_path: Path) -> Workspace:
    """Two source packages (the bigger with a sub-folder), tests that reach the bigger one most (with a sub-folder of their own), a
    script that imports across the hub, documents, configuration and data, a loose README, and a test file that fails."""
    files = {
        "README.md": ("# bakery\n", 0), "pyproject.toml": ('[project]\nname = "bakery"\n', 0),
        "src/bakery/__init__.py": ("from .orders import Order\n", 0),
        "src/bakery/models.py": ("class Model:\n    pass\n", 12),
        "src/bakery/orders.py": ("from bakery.models import Model\nfrom bakery.prices import price_of\n", 60),
        "src/bakery/prices.py": ("from bakery.models import Model\n\n\ndef price_of(item):\n    return 1\n", 25),
        "src/bakery/inventory.py": ("from bakery.models import Model\n", 120),
        "src/bakery/reports.py": ("from bakery.orders import Order\nfrom bakery.inventory import take\nfrom bakery.models import Model\n", 400),
        "src/bakery/cli.py": ("from bakery.reports import daily\n", 5),
        "src/bakery/util.py": ("VALUE = 1\n", 3),
        "src/bakery/a_rather_long_module_name_for_inventory_reports.py": ("from bakery.inventory import take\n", 40),
        "src/bakery/ui/__init__.py": ("", 0),
        "src/bakery/ui/app.py": ("from bakery.orders import Order\nfrom bakery.reports import daily\n", 90),
        "src/bakery/ui/widgets.py": ("from bakery.ui import app\n", 40),
        "src/shop_tools/__init__.py": ("", 0),
        "src/shop_tools/labels.py": ("from bakery.prices import price_of\n", 35),
        "src/shop_tools/export.py": ("from bakery.reports import daily\n", 55),
        "scripts/seed.py": ("from bakery import orders\n", 4), "scripts/export.py": ("import csv\n", 2),
        "tests/test_orders.py": ("from bakery.orders import Order\n", 3), "tests/test_prices.py": ("from bakery.prices import price_of\n", 3),
        "tests/test_inventory.py": ("from bakery.inventory import take\n", 3), "tests/test_reports.py": ("from bakery.reports import daily\n", 3),
        "tests/test_models.py": ("from bakery.models import Model\n", 3), "tests/test_labels.py": ("from shop_tools.labels import price_of\n", 3),
        "tests/integration/test_flow.py": ("from bakery.orders import Order\nfrom bakery.reports import daily\n", 3),
        "tests/integration/test_a_rather_long_end_to_end_name.py": ("from bakery.ui.app import Order\n", 3),
        "docs/GUIDE.md": ("# guide\n", 0), "docs/API.md": ("# api\n", 0), "docs/NOTES.md": ("# notes\n", 0),
        "config/settings.toml": ("[x]\n", 0), "config/logging.yaml": ("a: 1\n", 0),
        "data/prices.csv": ("a,b\n1,2\n", 0), "data/orders.csv": ("a,b\n1,2\n", 0),
    }
    ws = project(tmp_path, "bakery", files)
    fail_round(ws, ["tests/test_reports.py::test_daily"])
    return ws


def second_home(tmp_path: Path) -> Workspace:
    """Tests that mostly reach the SMALLER source package: their sector must sit beside that one."""
    files = {"pyproject.toml": ('[project]\nname = "second"\n', 0), "src/big/__init__.py": ("", 0), **{f"src/big/m{i}.py": ("x = 1\n", i) for i in range(8)},
             "src/small/__init__.py": ("", 0), **{f"src/small/s{i}.py": ("x = 1\n", i) for i in range(3)},
             **{f"tests/test_s{i}.py": (f"from small.s{i} import x\n", 1) for i in range(3)}, "tests/test_m0.py": ("from big.m0 import x\n", 1),
             "docs/a.md": ("a\n", 0), "docs/b.md": ("b\n", 0)}
    return project(tmp_path, "second", files)


def flat(tmp_path: Path) -> Workspace:
    return project(tmp_path, "flat", {"pyproject.toml": ('[project]\nname = "flat"\n', 0), "main.py": ("import util\n", 10), "util.py": ("X = 1\n", 3), "other.py": ("import util\n", 2),
                                      "test_main.py": ("import main\n", 2), "test_util.py": ("import util\n", 2), "README.md": ("# x\n", 0)})


def big(tmp_path: Path) -> Workspace:
    files = {f"pkg{f}/m{i:02d}.py": ("VALUE = %d\n" % i, i % 7) for f in range(8) for i in range(25)}
    files["pkg0/test_m00.py"] = ("import m00\n", 0)
    files["pyproject.toml"] = ('[project]\nname = "big"\n', 0)
    return project(tmp_path, "big", files)


def wide(tmp_path: Path) -> Workspace:
    files = {f"f{f:02d}/m{i}.py": ("x = 1\n", f) for f in range(16) for i in range(3)}
    files["pyproject.toml"] = ('[project]\nname = "wide"\n', 0)
    return project(tmp_path, "wide", files)


def docs_only(tmp_path: Path) -> Workspace:
    return project(tmp_path, "docs", {"pyproject.toml": ('[project]\nname = "docs"\n', 0), "README.md": ("# r\n", 0), "guide/a.md": ("a\n", 0), "guide/b.md": ("b\n", 0), "guide/c.md": ("c\n", 0),
                                      "api/x.md": ("x\n", 0), "api/y.md": ("y\n", 0)})


def planned(tmp_path: Path) -> Workspace:
    ws = project(tmp_path, "planned", {"pyproject.toml": ('[project]\nname = "planned"\n', 0), "a.py": ("x = 1\n", 0)})
    core = [ws.add_milestone("Take orders", "d", "Core", "w"), ]
    core.append(ws.add_milestone("Price list", "d", "Core", "w", depends_on=[core[0]["id"]]))
    core.append(ws.add_milestone("Oven API", "d", "Core", "w", depends_on=[core[1]["id"]]))
    core.append(ws.add_milestone("Standalone core step", "d", "Core", "w"))
    rep = [ws.add_milestone("Daily report", "d", "Reports", "w", depends_on=[core[1]["id"]])]
    rep.append(ws.add_milestone("Export labels", "d", "Reports", "w", depends_on=[rep[0]["id"], core[0]["id"]]))
    rep.append(ws.add_milestone("Oven timings", "d", "Reports", "w"))
    rel = [ws.add_milestone("Docs pass", "d", "Release", "w")]
    rel.append(ws.add_milestone("A milestone with a rather long title that must be shortened", "d", "Release", "w", depends_on=[rel[0]["id"]]))
    rel.append(ws.add_milestone("Ship version one", "d", "Release", "w", depends_on=[core[0]["id"], rep[1]["id"]]))   # skips columns
    ws.update_milestone(core[0]["id"], {"status": "done"})
    ws.update_milestone(core[1]["id"], {"status": "doing"})
    ws.save_draft(title="Report first files", why="w", files=[{"path": "a.py", "content": "x = 2\n"}], drafted_by="m", milestone=rep[0]["id"])
    return ws


@pytest.fixture(scope="module")
def laid(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("layout")
    builders = {"bakery": bakery, "second": second_home, "flat": flat, "big": big, "wide": wide, "docs": docs_only}
    spaces = {name: build(tmp) for name, build in builders.items()}
    views = {name: living_map.structure_view(ws) for name, ws in spaces.items()}
    views["big_expanded"] = living_map.structure_view(spaces["big"], expand=("pkg1",))
    views["bakery_again"] = living_map.structure_view(Workspace(tmp / "bakery", tmp / "bakery-home"))
    cases: dict[str, dict] = {name: {"structure": view} for name, view in views.items()}
    graph = living_map.plan_graph(planned(tmp))
    cases["plan"] = {"plan": graph}
    source = tmp / "in.json"
    source.write_text(json.dumps(cases), encoding="utf-8")
    out = tmp / "out.json"
    result = subprocess.run([NODE, str(DUMP), str(out), str(source)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return {"dump": json.loads(out.read_text(encoding="utf-8")), "views": views, "graph": graph}


STRUCTURES = ["bakery", "second", "flat", "big", "wide", "docs", "big_expanded"]


def hit(a: dict, b: dict, gap: float = 0.0) -> bool:
    return a["x0"] < b["x1"] + gap and b["x0"] < a["x1"] + gap and a["y0"] < b["y1"] + gap and b["y0"] < a["y1"] + gap


# --------------------------------------------------------------------------------------------- names and sizes --

@pytest.mark.parametrize("name", STRUCTURES)
def test_no_two_names_or_parts_overlap(laid, name):
    lay = laid["dump"][name]["layout"]
    boxes = [("part " + b["id"], b) for b in lay["boxes"]] + [("folder " + lb["gid"], lb["box"]) for lb in lay["labels"]]
    hub = {"x0": -88, "x1": 88, "y0": -88, "y1": 88}                       # the hub with its halo
    assert len(boxes) >= len(lay["points"])
    for i, (a_name, a) in enumerate(boxes):
        assert not hit(a, hub), (a_name, "sits on the hub")
        for b_name, b in boxes[i + 1:]:
            assert not hit(a, b), (a_name, b_name)


def test_a_long_name_is_cut_in_the_middle_and_keeps_its_end(laid):
    points = {p["id"]: p for p in laid["dump"]["bakery"]["layout"]["points"]}
    long_one = points["src/bakery/a_rather_long_module_name_for_inventory_reports.py"]["label"]
    assert "…" in long_one and long_one.endswith(".py") and len(long_one) <= 16 and long_one.startswith("a_rather")
    other = points["tests/integration/test_a_rather_long_end_to_end_name.py"]["label"]
    assert "…" in other and other.endswith("_name.py") or other.endswith(".py")
    short = points["src/bakery/cli.py"]["label"]
    assert short == "cli.py"                                    # a short name is never changed
    assert all(len(p["label"]) <= 16 for p in laid["dump"]["bakery"]["layout"]["points"])


def test_a_part_grows_with_its_lines_on_a_log_scale_and_is_clamped(laid):
    radii = {int(k): v for k, v in laid["dump"]["bakery"]["layout"]["radii"].items()}
    ordered = [radii[k] for k in sorted(radii)]
    assert ordered == sorted(ordered)                           # more lines never means a smaller part
    assert min(ordered) == 8 and max(ordered) == 24             # the clamp
    assert radii[0] == 8 and radii[1_000_000] == 24 and radii[3162] == 24
    assert 8 < radii[10] < radii[1000] < 24
    for name in STRUCTURES:
        for p in laid["dump"][name]["layout"]["points"]:
            assert 8 <= p["r"] <= 24, (name, p["id"])


# --------------------------------------------------------------------------------------------- determinism --

@pytest.mark.parametrize("name", STRUCTURES + ["plan"])
def test_the_same_drawing_twice_and_whatever_order_the_lists_come_in(laid, name):
    entry = laid["dump"][name]
    assert entry["layout"] == entry["again"]
    if entry["kind"] == "structure":
        assert entry["layout"] == entry["shuffled"]             # no position depends on the order of nodes, groups or edges
    else:
        key = lambda n: n["id"]  # noqa: E731
        assert sorted(entry["layout"]["nodes"], key=key) == sorted(entry["shuffled"]["nodes"], key=key)
        edge_key = lambda e: (e["from"], e["to"])  # noqa: E731
        assert sorted(entry["layout"]["edges"], key=edge_key) == sorted(entry["shuffled"]["edges"], key=edge_key)


def test_two_builds_of_the_same_folder_give_the_same_positions(laid):
    assert laid["dump"]["bakery"]["layout"]["points"] == laid["dump"]["bakery_again"]["layout"]["points"]
    assert laid["dump"]["bakery"]["layout"]["labels"] == laid["dump"]["bakery_again"]["layout"]["labels"]


# ------------------------------------------------------------------------------------------------ the sectors --

def test_sectors_run_clockwise_from_twelve_in_the_fixed_order(laid):
    lay = laid["dump"]["bakery"]["layout"]
    # source packages (the largest first), then the tests beside the package they reach most, documents, configuration, data
    assert lay["order"] == ["src/bakery", "tests", "src/shop_tools", "scripts", "docs", "", "config", "data"]
    sectors = {s["id"]: s for s in lay["sectors"]}
    assert sectors["src/bakery"]["a0"] == pytest.approx(-math.pi / 2, abs=1e-3)        # 12 o'clock
    previous = -math.inf
    for sector_id in lay["order"]:
        s = sectors[sector_id]
        assert s["a0"] > previous and s["a1"] > s["a0"], sector_id                    # clockwise, none over another
        previous = s["a1"]
    assert previous < 3 * math.pi / 2 + 1e-3
    assert {k: sectors[k]["cat"] for k in sectors} == {"src/bakery": "source", "tests": "tests", "src/shop_tools": "source", "scripts": "source",
                                                         "docs": "docs", "": "docs", "config": "config", "data": "data"}


def test_the_tests_sit_beside_the_source_they_reach_most(laid):
    lay = laid["dump"]["bakery"]["layout"]
    sectors = {s["id"]: s for s in lay["sectors"]}
    assert sectors["tests"]["home"] == "src/bakery"
    assert lay["order"].index("tests") == lay["order"].index("src/bakery") + 1          # they share a boundary
    second = laid["dump"]["second"]["layout"]
    assert {s["id"]: s for s in second["sectors"]}["tests"]["home"] == "src/small"       # most of its tests reach the smaller package
    assert second["order"].index("tests") == second["order"].index("src/small") + 1
    assert second["order"].index("src/big") < second["order"].index("src/small")        # the larger package still comes first


def test_each_test_file_keeps_the_order_of_the_module_it_reaches_counted_from_the_shared_edge(laid):
    lay = laid["dump"]["bakery"]["layout"]
    points = {p["id"]: p for p in lay["points"]}
    sectors = {s["id"]: s for s in lay["sectors"]}
    tests = [p for p in lay["points"] if p["sector"] == "tests"]
    assert len(tests) == 8
    views = {n["id"]: n for n in laid["views"]["bakery"]["nodes"]}
    start = sectors["tests"]["a0"]
    located = []
    for t in tests:
        reached = views[t["id"]]["reaches"]
        named = [m for m in reached if m.rsplit("/", 1)[-1] == t["id"].rsplit("/", 1)[-1].replace("test_", "")]
        target = (named or reached)[0]
        located.append((t["group"], t["angle"], (start - points[target]["angle"]) % TAU, t["id"], target))
    for group in {row[0] for row in located}:                                          # inside each folder of tests ...
        mine = sorted(row for row in located if row[0] == group)
        mirrored = [row[2] for row in sorted(mine, key=lambda row: row[1])]
        assert mirrored == sorted(mirrored), mine                                      # ... the order follows the modules' mirrored order
    one = next(p for p in lay["points"] if p["id"] == "tests/test_models.py")
    assert one["sector"] == "tests"


def test_a_folder_inside_a_folder_is_drawn_inside_its_parents_sector(laid):
    lay = laid["dump"]["bakery"]["layout"]
    sectors = {s["id"]: s for s in lay["sectors"]}
    assert "src/bakery/ui" not in sectors and "tests/integration" not in sectors        # no sector of their own
    for parent, child in (("src/bakery", "src/bakery/ui"), ("tests", "tests/integration")):
        region = next(r for r in sectors[parent]["regions"] if r["id"] == child)
        assert sectors[parent]["a0"] - 1e-6 <= region["a0"] < region["a1"] <= sectors[parent]["a1"] + 1e-6
        mine = [p for p in lay["points"] if p["group"] == child]
        assert mine and all(region["a0"] - 0.35 <= p["angle"] <= region["a1"] + 0.35 for p in mine)
    labels = {lb["gid"]: lb for lb in lay["labels"]}
    assert labels["src/bakery"]["text"] == "src/bakery · 9 files"                       # a sector says its folder and its size
    assert labels["src/bakery/ui"]["text"] == "ui · 3 files" and labels["src/bakery/ui"]["sub"] is True
    assert labels["scripts"]["text"] == "scripts · 2 files" and labels[""]["text"] == "top level · 2 files"


def test_source_files_sit_nearer_the_hub_the_more_they_are_imported(laid):
    for name in ("bakery", "big", "flat"):
        lay = laid["dump"][name]["layout"]
        points = {p["id"]: p for p in lay["points"]}
        by_group: dict[str, list] = {}
        for n in laid["views"][name]["nodes"]:
            if n["kind"] == "module" and n["id"] in points and not n["id"].startswith("more:"):
                by_group.setdefault(n["group"], []).append(n)
        checked = 0
        for members in by_group.values():
            for a in members:
                for b in members:
                    if len(a["imported_by"]) > len(b["imported_by"]):
                        assert points[a["id"]]["ring"] <= points[b["id"]]["ring"], (name, a["id"], b["id"])
                        checked += 1
        if name == "bakery":
            assert checked > 10
    points = {p["id"]: p for p in laid["dump"]["bakery"]["layout"]["points"]}
    assert points["src/bakery/models.py"]["ring"] == 0                                  # the most imported file is in the innermost ring
    assert points["src/bakery/util.py"]["ring"] >= points["src/bakery/orders.py"]["ring"]


def test_the_cap_and_the_other_folders_group_keep_their_place(laid):
    wide_lay = laid["dump"]["wide"]["layout"]
    assert wide_lay["order"][-1] == "(other folders)"                                  # the shared group is last
    big_lay = laid["dump"]["big"]["layout"]
    assert any(p["id"].startswith("more:") for p in big_lay["points"])                 # "+N more" is a part of its folder
    more = next(p for p in big_lay["points"] if p["id"].startswith("more:"))
    assert more["r"] == 15 and more["label"] == "more"
    assert len(laid["dump"]["big_expanded"]["layout"]["points"]) > len(big_lay["points"]) - 10
    flat_lay = laid["dump"]["flat"]["layout"]
    assert flat_lay["order"][0] == ""                                                   # loose files are the only folder with source: it is first
    assert len(flat_lay["points"]) == 7


# ------------------------------------------------------------------------------------------------------ links --

@pytest.mark.parametrize("name", ["bakery", "second", "flat", "big", "wide", "docs"])
def test_no_link_crosses_the_hub(laid, name):
    lay = laid["dump"][name]["layout"]
    hx, hy = lay["hub"]["x"], lay["hub"]["y"]
    for e in lay["edges"]:
        for p in e["samples"]:
            assert not (abs(p["x"]) < hx and abs(p["y"]) < hy), (name, e["from"], e["to"])
    drawn = {p["id"] for p in lay["points"]}
    expected = [e for e in laid["views"][name]["edges"] if e["from"] in drawn and e["to"] in drawn]
    assert len(lay["edges"]) == len(expected)                                         # every link between two drawn parts is drawn
    assert expected or name in ("big", "wide", "docs")                                   # (those three have no links to draw)


def test_a_link_across_the_hub_goes_round_it_and_a_short_link_stays_short(laid):
    lay = laid["dump"]["bakery"]["layout"]
    points = {p["id"]: p for p in lay["points"]}
    across = next(e for e in lay["edges"] if e["from"] == "scripts/seed.py" and e["to"] == "src/bakery/orders.py")
    a, b = points[across["from"]], points[across["to"]]
    chord = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
    assert chord > 300                                          # they are far apart ...
    assert any(abs(p["x"]) >= lay["hub"]["x"] or abs(p["y"]) >= lay["hub"]["y"] for p in across["samples"])
    near = next(e for e in lay["edges"] if e["from"] == "src/bakery/cli.py" and e["to"] == "src/bakery/reports.py")
    length = sum(((q["x"] - p["x"]) ** 2 + (q["y"] - p["y"]) ** 2) ** 0.5 for p, q in zip(near["samples"], near["samples"][1:]))
    chord2 = ((points["src/bakery/cli.py"]["x"] - points["src/bakery/reports.py"]["x"]) ** 2 + (points["src/bakery/cli.py"]["y"] - points["src/bakery/reports.py"]["y"]) ** 2) ** 0.5
    assert length < chord2 * 1.5 + 40                           # a link inside a sector is barely bowed


def test_only_a_failing_tests_links_are_the_bad_colour_and_imports_stay_plain(laid):
    lay = laid["dump"]["bakery"]["layout"]
    bad = [e for e in lay["edges"] if e["bad"]]
    assert bad and all(e["type"] == "tests" and e["from"] == "tests/test_reports.py" for e in bad)
    assert {e["to"] for e in bad} == {"src/bakery/reports.py"}
    assert not [e for e in lay["edges"] if e["type"] == "imports" and e["bad"]]
    assert {e["type"] for e in lay["edges"]} == {"imports", "tests"}


# --------------------------------------------------------------------------------------------- the plan graph --

def test_the_plan_reads_left_to_right_with_even_spacing(laid):
    plan = laid["dump"]["plan"]["layout"]
    nodes = {n["id"]: n for n in plan["nodes"]}
    graph = laid["graph"]
    assert len(nodes) == len(graph["nodes"])
    for n in graph["nodes"]:
        for need in n["depends_on"]:
            assert nodes[n["id"]]["x"] > nodes[need]["x"], (n["title"], "must be right of what it needs")
    done = [n for n in graph["nodes"] if n["state"] == "done"]
    assert done
    for d in done:
        for n in graph["nodes"]:
            if d["id"] in n["depends_on"]:
                assert nodes[d["id"]]["x"] < nodes[n["id"]]["x"]                       # done sits left of what depends on it
    xs = sorted({n["x"] for n in plan["nodes"]})
    pad, col = plan["box"]["pad"], plan["box"]["col"]
    assert xs == [pad + col * i for i in range(len(xs))]                              # every column in use, evenly spaced, none empty
    assert plan["columns"] == len(xs)
    for lane in plan["lanes"]:
        rows = [n for n in plan["nodes"] if n["track"] == lane["track"]]
        ys = sorted({n["y"] for n in rows})
        assert all(b - a == 62 for a, b in zip(ys, ys[1:]))                           # rows evenly spaced inside a lane


def test_no_plan_box_overlaps_another_and_no_link_runs_behind_a_box(laid):
    plan = laid["dump"]["plan"]["layout"]
    w, h = plan["box"]["w"], plan["box"]["h"]
    boxes = {n["id"]: {"x0": n["x"], "x1": n["x"] + w, "y0": n["y"], "y1": n["y"] + h} for n in plan["nodes"]}
    ids = sorted(boxes)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            assert not hit(boxes[a], boxes[b]), (a, b)
    skipped = [e for e in plan["edges"] if e["route"] == "channel"]
    assert skipped                                                                     # the fixture has a link that skips columns
    for e in plan["edges"]:
        for p in e["samples"]:
            for node_id, box in boxes.items():
                if node_id in (e["from"], e["to"]):
                    continue
                inside = box["x0"] + 1 < p["x"] < box["x1"] - 1 and box["y0"] + 1 < p["y"] < box["y1"] - 1
                assert not inside, (e["from"], e["to"], node_id)
    assert plan["W"] >= max(b["x1"] for b in boxes.values()) and plan["H"] >= max(b["y1"] for b in boxes.values())


def test_a_milestone_that_needs_you_is_marked_and_the_graph_draws_the_mark():
    source = (ROOT / "runesmith" / "app" / "static" / "js" / "views" / "map-plan.js").read_text(encoding="utf-8")
    assert "lm-flag" in source and "needs_you" in source
    css = (ROOT / "runesmith" / "app" / "static" / "app.css").read_text(encoding="utf-8")
    assert ".lm-plan .lm-flag circle" in css and ".lm-plan .lm-ms.needs_you" in css


def test_a_failing_plan_graph_state_is_in_the_fixture(laid):
    states = {n["state"] for n in laid["graph"]["nodes"]}
    assert {"done", "doing", "needs_you", "waiting", "ready"} <= states


def test_the_layout_file_is_pure_and_the_drawing_files_use_it():
    views = ROOT / "runesmith" / "app" / "static" / "js" / "views"
    layout = (views / "map-layout.js").read_text(encoding="utf-8")
    assert not re.search(r"\b(document|window|navigator|localStorage)\.", layout) and "Math.random" not in layout and "Date.now" not in layout
    assert not [line for line in layout.splitlines() if line.startswith("import ")]          # nothing to load: it runs under Node as it is
    for name, wanted in (("map-structure.js", "structureLayout"), ("map-plan.js", "planLayout")):
        text = (views / name).read_text(encoding="utf-8")
        assert "from './map-layout.js'" in text and wanted in text, name
