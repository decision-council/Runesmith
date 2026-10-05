"""The living map's browser fixture: a small bakery project with a failing test, a plan with prerequisites, a lineage with a trial.

``python tests/living_map_fixture.py`` regenerates ``tests/fixtures/living_map.json``, the answers the browser loops (B28 to B31)
serve for the map's endpoints. ``test_living_map.py`` builds the same scenario again and checks that the committed answers have
the shape the builders produce now, so a change to a builder cannot leave the loops testing an answer that no longer exists.
Nothing here touches a real home: the project, its home and the Studio's profile are under the folder it is given.
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ENDPOINTS = {"environment": "/api/map/environment", "structure": "/api/map/structure", "development": "/api/map/development",
             "self": "/api/map/self", "operations": "/api/map/operations", "settings": "/api/settings", "build": "/api/build",
             "improve": "/api/improve", "fix": "/api/fix-tests"}


def _write(root: Path, rel: str, text: str = "x = 1\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def seed(base: Path):
    """The project and its home, as the Studio leaves them after a round that found one failing test file."""
    from runesmith import generations
    from runesmith.app.workspace import Workspace, _write_json
    from runesmith.kaizen.trial import Trial
    root, home = base / "bakery", base / "home"
    pad = lambda n: "\n# padding\n" * n  # noqa: E731
    _write(root, "pyproject.toml", '[project]\nname = "bakery"\nversion = "0.1"\n')
    _write(root, "requirements.txt", "pytest\n")
    _write(root, "README.md", "# Moonlight Bakery\n\nOrders, prices and the oven.\n")
    _write(root, "docs/GUIDE.md", "# Guide\n\nSee [README](../README.md).\n")
    _write(root, "docs/NOTES.md", "# Notes\n\nTODO: oven timings\n")
    _write(root, "data/sample.csv", "date,item,sold\n2026-10-01,loaf,12\n")
    _write(root, "scripts/seed.py", "from bakery import orders\n\nprint(orders)\n")
    _write(root, "scripts/export.py", "import csv\n\nprint(csv)\n")
    _write(root, "src/bakery/__init__.py", "from .orders import Order\nfrom .prices import price_of\n")
    _write(root, "src/bakery/orders.py", "from bakery.prices import price_of\nfrom bakery import inventory\n\n\nclass Order:\n    def __init__(self, item, qty):\n        self.item, self.qty = item, qty\n\n    def total(self):\n        return price_of(self.item) * self.qty\n" + pad(60))
    _write(root, "src/bakery/prices.py", "PRICES = {'loaf': 4, 'bun': 2}\n\n\ndef price_of(item):\n    return PRICES[item]\n" + pad(25))
    _write(root, "src/bakery/inventory.py", "STOCK = {'loaf': 10}\n\n\ndef take(item, qty):\n    STOCK[item] -= qty\n    return STOCK[item]\n" + pad(120))
    _write(root, "src/bakery/oven.py", "from bakery.inventory import take\n\n\ndef bake(item, qty):\n    return take(item, qty)\n" + pad(40))
    _write(root, "src/bakery/reports.py", "from bakery.orders import Order\n\n\ndef daily(orders):\n    return sum(o.total() for o in orders)\n" + pad(200))
    _write(root, "src/bakery/cli.py", "from bakery.reports import daily\n\n\ndef main():\n    print(daily([]))\n")
    _write(root, "src/bakery/legacy.py", "VALUE = 1\n" + pad(15))
    _write(root, "tests/__init__.py", "")
    _write(root, "tests/test_orders.py", "from bakery.orders import Order\n\n\ndef test_total():\n    assert Order('loaf', 2).total() == 8\n")
    _write(root, "tests/test_prices.py", "from bakery.prices import price_of\n\n\ndef test_price():\n    assert price_of('bun') == 2\n")
    _write(root, "tests/test_inventory.py", "from bakery.inventory import take\n\n\ndef test_take():\n    assert take('loaf', 1) == 9\n")
    _write(root, "tests/test_reports.py", "from bakery.reports import daily\n\n\ndef test_daily():\n    assert daily([]) == 1\n")
    ws = Workspace(root, home)
    ws.update_settings({"onboarded": True, "workspace_name": "Moonlight Bakery", "autonomy": "propose", "policy_chosen": True,
                        "kaizen": True, "build_paths": ["src"]})
    old = time.time() - 4 * 3600                                  # every file is older than the round below
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))
    ws.map_environment(probe=False)
    name = next(o["name"] for o in ws.environment_map()["objects"])
    _write_json(home / "WORK.json", {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600)), "outcome": "worked", "objects": {name: "failing"},
        "details": {}, "summary": {"outcome": "worked", "served": 1, "accepted": 0},
        "opportunities": [{"id": "o1", "object": name, "failing_tests": ["tests/test_reports.py::test_daily"], "issue": "daily is wrong"}]})
    g0 = generations.active(home)

    def candidate(parent: str, tag: str):
        src, dst = home / "generations" / parent / "organs", home / "scratch" / f"organs-{tag}"
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
        repair = dst / "repair.py"
        repair.write_bytes(repair.read_bytes() + f"\n# {tag}\n".encode())
        return generations.freeze(dst, home, label=f"kaizen-loop {tag}", parent=parent,
                                  provenance={"target": {"family": "retry policy"}, "validation": {"strict_successes": 9},
                                              "incumbent_validation": {"strict_successes": 6}})

    a, b = candidate(g0, "a1"), candidate(g0, "b2")
    c = candidate(a["id"], "c3")
    Trial(incumbent=g0, candidate=b["id"], seed="s", decision="reject", counts={"incumbent": [8, 10], "candidate": [2, 10]},
          looks=[{"look": 1, "incumbent": [8, 10], "candidate": [2, 10], "p_candidate_better": 0.99, "p_candidate_worse": 0.001, "level": 0.0125}]
          ).save(home / f"TRIAL-{b['id']}-reject.json")
    trial = Trial(incumbent=g0, candidate=c["id"], seed="s", min_per_arm=10, look_every=10, max_per_arm=40)
    trial.counts = {"incumbent": [3, 8], "candidate": [5, 9]}
    trial.save(home / "TRIAL.json")
    ws.ledger.append("trial.opened", trial.summary())
    m1 = ws.add_milestone("Take orders", "Orders can be placed", "Core", "an order has a total")
    m2 = ws.add_milestone("Price list", "Prices for every item", "Core", "every item has a price", depends_on=[m1["id"]])
    m3 = ws.add_milestone("Daily report", "Sum the day", "Reports", "the report adds up", depends_on=[m1["id"], m2["id"]])
    ws.add_milestone("Oven timings", "Know how long to bake", "Reports", "timings listed")
    m5 = ws.add_milestone("Old spreadsheet import", "retired", "Reports", "n/a")
    ws.update_milestone(m1["id"], {"status": "done"})
    ws.update_milestone(m5["id"], {"status": "dropped"})
    ws.update_milestone(m2["id"], {"status": "doing"})
    ws.save_draft(title="Daily report first files", why="w", files=[{"path": "src/bakery/reports.py", "content": "def daily(orders):\n    return 0\n"}],
                  drafted_by="gemini-2.5-flash", milestone=m3["id"])
    (home / "sessions").mkdir(exist_ok=True)
    for i in range(14):
        _write_json(home / "sessions" / f"s{i:02d}.json", {
            "key": f"s{i:02d}", "status": "public_pass", "strict_success": i % 3 != 0, "cycle_seconds": 20 + i, "calls": [{"model": "gemini"}] * 3,
            "utc_start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200 + i * 60)),
            "trial_arm": ("candidate" if i % 2 else "incumbent") if i > 8 else None})
    return root, home


def build(base: Path) -> dict:
    """Seed the scenario under ``base``, ask a Studio for each map endpoint, and return the answers."""
    from runesmith.app import server
    from test_studio import call
    root, home = seed(base)
    server.STUDIO_DIR = base / "profile"
    studio = server.Studio(root, home)
    httpd = server.bind(studio, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        out = {key: call(studio, "GET", path)[1] for key, path in ENDPOINTS.items()}
    finally:
        studio.closing = True
        studio.close()
        httpd.shutdown()
        httpd.server_close()
    out["improve"].pop("plan", None)                              # the Self-improvement page's own parts, not the map's
    out["improve"].pop("self", None)
    text = json.dumps(out).replace(str(root).replace("\\", "\\\\"), "D:/fixture/bakery").replace(str(home).replace("\\", "\\\\"), "D:/fixture/home")
    return json.loads(text)


if __name__ == "__main__":
    import tempfile
    target = Path(__file__).resolve().parent / "fixtures" / "living_map.json"
    with tempfile.TemporaryDirectory(prefix="living-map-fixture-", dir=os.environ.get("TEMP")) as folder:
        result = build(Path(folder))
    target.parent.mkdir(exist_ok=True)
    target.write_bytes((json.dumps(result, indent=None, separators=(",", ":")) + "\n").encode("utf-8"))
    print("wrote", target, len(target.read_bytes()), "bytes")
