"""``runesmith demo``: watch the whole loop in about a minute.

The demo writes a tiny shop workspace with three slips, then:

1. maps the workspace: objects, objectives in bands, the next rung of the build ladder;
2. discovers repair opportunities from the failing tests;
3. serves them with the active generation through the run loop (experience, attention, ledger);
4. applies each repair the judge accepted, to the demo's own workspace only;
5. maps the workspace again, so the band visibly moves;
6. writes REPORT.md.

Offline (the default), a scripted stand-in plays the model. It knows the three demo
fixes, so the offline demo shows the machinery, not model skill. With ``live=True``
the instruments configured in ``runesmith.json`` answer instead, and the repairs are real.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path
from typing import Any, Callable

from runesmith.canon import canonical
from runesmith.config import build_router, load_config
from runesmith.discover import discover
from runesmith.envmap import build_environment_map
from runesmith.instruments import CallOutcome, Instrument, Router
from runesmith.kaizen.improve import _fill
from runesmith.loop import ExperienceStore, run_loop
from runesmith.report import write_report

MARKER = ".runesmith-demo"
PRICING = textwrap.dedent('''\
    """Prices for a small shop."""


    def subtotal(prices):
        """Sum of all item prices."""
        return sum(prices[1:])


    def apply_discount(amount, percent):
        """The amount after a percentage discount."""
        return round(amount * (1 + percent / 100), 2)


    def free_shipping(total, threshold=50):
        """Orders of at least the threshold ship free."""
        return total > threshold


    def format_price(amount):
        return f"${amount:,.2f}"
''')
TESTS = {
    "tests/test_subtotal.py": textwrap.dedent('''\
        from shop.pricing import subtotal

        def test_subtotal_counts_every_item():
            assert subtotal([10, 20, 30]) == 60
    '''),
    "tests/test_discount.py": textwrap.dedent('''\
        from shop.pricing import apply_discount

        def test_discount_lowers_the_price():
            assert apply_discount(100, 15) == 85
    '''),
    "tests/test_shipping.py": textwrap.dedent('''\
        from shop.pricing import free_shipping

        def test_shipping_is_free_at_the_threshold():
            assert free_shipping(50) is True
            assert free_shipping(49.99) is False
    '''),
    "tests/test_format.py": textwrap.dedent('''\
        from shop.pricing import format_price

        def test_format_price():
            assert format_price(1234.5) == "$1,234.50"
    '''),
}
# What the offline stand-in "knows": one fix per slip, keyed by a word from the failing test.
DEMO_FIXES = {
    "subtotal": ("subtotal", "return sum(prices[1:])", "return sum(prices)"),
    "discount": ("apply_discount", "return round(amount * (1 + percent / 100), 2)",
                 "return round(amount * (1 - percent / 100), 2)"),
    "shipping": ("free_shipping", "return total > threshold", "return total >= threshold"),
}


class DemoStandIn(Instrument):
    """Plays the model offline. It knows only the demo's own slips: machinery, not skill."""

    kind = "demo-stand-in"

    def __init__(self) -> None:
        super().__init__("demo-stand-in", "scripted")

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        for marker, (symbol, old, new) in DEMO_FIXES.items():
            if f"test_{marker}" in prompt:
                hints = {"reads": [{"path": "src/shop/pricing.py", "symbols": [symbol]}],
                         "edits": [{"path": "src/shop/pricing.py", "old_text": old, "new_text": new}]}
                data = _fill(schema, hints) if schema else hints
                return CallOutcome(True, data=data, text=canonical(data))
        return CallOutcome(False, error_kind="output", error="the demo stand-in knows only the demo's own slips")


def write_workspace(root: Path) -> Path:
    """(Re)create the demo workspace. Refuses to touch a directory the demo did not create."""
    root = Path(root)
    if root.exists():
        if not (root / MARKER).exists():
            raise SystemExit(f"{root} exists and was not created by the demo; refusing to overwrite it")
        shutil.rmtree(root)
    repo = root / "shop"
    (repo / "src" / "shop").mkdir(parents=True)
    (repo / "tests").mkdir()
    (root / MARKER).write_text("created by `runesmith demo`; safe to delete\n", encoding="utf-8")
    (repo / "src" / "shop" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "shop" / "pricing.py").write_text(PRICING, encoding="utf-8")
    for rel, text in TESTS.items():
        (repo / rel).write_text(text, encoding="utf-8")
    return repo


def _tests_green(env_map: dict[str, Any]) -> dict[str, Any]:
    for obj in env_map["objects"]:
        for objective in obj.get("objectives", []):
            if objective["id"] == "tests_green":
                return {"value": objective.get("value"), "band": objective.get("band"), "next_rung": obj.get("next_rung")}
    return {"value": None, "band": "unknown", "next_rung": None}


def run_demo(home: Path, *, live: bool = False, out: Callable[[str], None] = print) -> dict[str, Any]:
    """Run the demo in an initialized home. Returns a summary; prints the story as it goes."""
    home = Path(home)
    repo = write_workspace(home / "demo-workspace")
    out(f"1. Lowered into {repo.parent}. Mapping it ...")
    before = _tests_green(build_environment_map(repo.parent, probe=True, scratch=home / "scratch"))
    out(f"   shop: tests passing {before['value']} -> band {before['band']}; next rung: {before['next_rung']}")

    found = discover(repo, scratch=home / "scratch")
    opportunities = found["opportunities"]
    out(f"2. Discovered {len(opportunities)} repair opportunities from the failing tests:")
    for opportunity in opportunities:
        out(f"   - {', '.join(opportunity['failing_tests'])}")

    if live:
        router = build_router(load_config(home), home=home)
        out("3. Serving them with the instruments in runesmith.json (live: real model answers) ...")
    else:
        router = Router({"stand-in": DemoStandIn()}, {"repair": "stand-in"}, backoff_s=(0,), sleep=lambda s: None)
        out("3. Serving them offline: a scripted stand-in plays the model (it knows these three slips;")
        out("   the demo shows the machinery, not model skill; add --live to use your configured model) ...")
    store = ExperienceStore(home / "experience")
    served: list[str] = []
    repaired: list[str] = []

    def on_step(step: dict) -> None:
        # A verified fix holds whole files, so it is applied at once: the next opportunity then
        # starts from the improved workspace instead of overwriting this fix with an older copy.
        if step.get("lane") != "object":
            return
        served.append(step["key"])
        fix = store.verified_fix(step["key"])
        if fix:
            repaired.append(step["key"])
            for rel, text in fix.items():
                (repo / rel).write_text(text, encoding="utf-8")
        out(f"   {step['key']}: {step['status']}" + (" -> judge accepted, applied" if fix else ""))

    run_loop(home=home, opportunities=opportunities, seed="runesmith-demo", router=router,
             min_experience=10 ** 6, on_step=on_step)
    out(f"4. The held-out judge accepted {len(repaired)} of {len(served)} repairs; each was applied to the demo workspace.")

    after = _tests_green(build_environment_map(repo.parent, probe=True, scratch=home / "scratch"))
    out(f"5. Mapped again: tests passing {after['value']} -> band {after['band']}; next rung: {after['next_rung']}")
    report = write_report(home)
    out(f"6. Report: {report}")
    out("   Every step above is in the hash-chained ledger (`runesmith ledger`).")
    out("   Next: `runesmith run` keeps serving work and interleaves Kaizen steps once experience accumulates.")
    return {"opportunities": len(opportunities), "served": len(served), "repaired": len(repaired),
            "before": before, "after": after, "report": str(report), "live": live}
