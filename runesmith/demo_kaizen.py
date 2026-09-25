"""``runesmith demo --kaizen``: watch Runesmith improve itself, offline, in about three minutes.

This replays, on a tiny bundled workspace, what Runesmith's own Kaizen loop did in the
SR5-KAIZEN study (2026-09-24):

1. **Struggle.** The shipped repair organ g0 serves eight slips. A stand-in plays a weak
   model whose navigation answers are always malformed, so g0 gives up on every one of
   them (``navigation_output_failure``).
2. **Diagnose and author.** A Kaizen step reads Runesmith's own telemetry, and the declared
   rule picks the lost family as the target. The author's answer is the one a free model
   (gpt-oss-120b) actually wrote for this target in SR5: generation ``gen-a4415db24a53``,
   which never abandons an opportunity after a bad navigation answer and falls back to a
   deterministic read set.
3. **Qualify and freeze.** Static check, confined smoke test, and replays on the held-out
   half of the experience. The candidate is frozen, not activated.
4. **Trial.** New opportunities are split between g0 and the candidate by a seeded coin, and
   the sequential exact test activates the candidate by compare-and-swap.

The stand-in model knows the demo's fixes. What the demo shows is the machinery of
self-improvement, not model skill. On real fresh work, SR5's preregistered confirmation
found that this change does **not** transfer to large repositories: its fallback read set
rescued 0 of 26 navigation failures there, against 2 of 6 in the small development
repositories. The demo replays the machinery; the evidence is reported as it came out.

With ``--manual-author`` the author is not replayed: the request is written to
``<home>/manual/`` for you to paste into a chat model of your choice, and the model's
own change goes through the same qualification and trial.
"""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path
from typing import Any, Callable

from runesmith import generations
from runesmith.canon import canonical
from runesmith.discover import discover
from runesmith.instruments import CallOutcome, Instrument, Router
from runesmith.kaizen.improve import _fill
from runesmith.kaizen.trial import Trial
from runesmith.ledger import Ledger
from runesmith.loop import ExperienceStore, run_loop, subject_step
from runesmith.report import write_report
from runesmith.share import open_trial_for

MARKER = ".runesmith-demo"
SEED = "runesmith-demo-kaizen"
B_ANSWER = Path(__file__).with_name("demo_data") / "sr5_b_answer.json"
NUMBERS = textwrap.dedent('''\
    def mean(values):
        return sum(values) / (len(values) + 1)


    def clamp(x, low, high):
        return max(low, min(x, low))


    def is_even(n):
        return n % 2 == 1


    def percent(part, whole):
        return round(100 * whole / part, 1)
''')
WORDS = textwrap.dedent('''\
    def count_words(text):
        return len(text.split(" ")) - 1


    def initials(name):
        return "".join(p[-1] for p in name.split()).upper()


    def shout(text):
        return text.lower() + "!"


    def title_case(text):
        return " ".join(w.capitalize() for w in text.split(","))
''')
TESTS = {
    "mean": ("numbers", "assert mean([2, 4, 6]) == 4"),
    "clamp": ("numbers", "assert clamp(15, 0, 10) == 10 and clamp(-1, 0, 10) == 0"),
    "is_even": ("numbers", "assert is_even(4) is True and is_even(7) is False"),
    "percent": ("numbers", "assert percent(1, 4) == 25.0"),
    "count_words": ("words", 'assert count_words("one two three") == 3'),
    "initials": ("words", 'assert initials("ada lovelace") == "AL"'),
    "shout": ("words", 'assert shout("hi") == "HI!"'),
    "title_case": ("words", 'assert title_case("hello big world") == "Hello Big World"'),
}
FIXES = {
    "mean": ("numbers", "return sum(values) / (len(values) + 1)", "return sum(values) / len(values)"),
    "clamp": ("numbers", "return max(low, min(x, low))", "return max(low, min(x, high))"),
    "is_even": ("numbers", "return n % 2 == 1", "return n % 2 == 0"),
    "percent": ("numbers", "return round(100 * whole / part, 1)", "return round(100 * part / whole, 1)"),
    "count_words": ("words", 'return len(text.split(" ")) - 1', "return len(text.split())"),
    "initials": ("words", 'return "".join(p[-1] for p in name.split()).upper()',
                 'return "".join(p[0] for p in name.split()).upper()'),
    "shout": ("words", 'return text.lower() + "!"', 'return text.upper() + "!"'),
    "title_case": ("words", 'return " ".join(w.capitalize() for w in text.split(","))',
                   'return " ".join(w.capitalize() for w in text.split())'),
}


def load_b_answer() -> dict[str, Any]:
    return json.loads(B_ANSWER.read_text(encoding="utf-8"))


class KaizenStandIn(Instrument):
    """Plays a weak repair model (navigation answers always malformed) and replays SR5's Kaizen author."""

    kind = "demo-stand-in"

    def __init__(self) -> None:
        super().__init__("demo-kaizen-stand-in", "scripted")
        self.b = load_b_answer()

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        fields = set((schema or {}).get("properties") or {})
        if "module_source" in fields:                           # the Kaizen author
            data = {k: self.b[k] for k in ("hypotheses", "mechanism", "prediction", "falsifier", "module_source")}
            data["edits"] = []
            return CallOutcome(True, data=data, text=canonical(data))
        if "reads" in fields:                                   # navigation: a weak model's answer breaks
            return CallOutcome(False, error_kind="output", error="navigation answer truncated (weak-model stand-in)")
        for name, (module, old, new) in FIXES.items():          # an edit request for one of the demo's slips
            if f"test_{name}.py" in prompt:
                hints = {"edits": [{"path": f"src/tally/{module}.py", "old_text": old, "new_text": new}]}
                data = _fill(schema, hints) if schema else hints
                return CallOutcome(True, data=data, text=canonical(data))
        return CallOutcome(False, error_kind="output", error="the demo stand-in knows only the demo's own slips")


def write_workspace(root: Path) -> Path:
    root = Path(root)
    if root.exists():
        if not (root / MARKER).exists():
            raise SystemExit(f"{root} exists and was not created by the demo; refusing to overwrite it")
        shutil.rmtree(root)
    repo = root / "tally"
    (repo / "src" / "tally").mkdir(parents=True)
    (repo / "tests").mkdir()
    (root / MARKER).write_text("created by `runesmith demo --kaizen`; safe to delete\n", encoding="utf-8")
    (repo / "src" / "tally" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "tally" / "numbers.py").write_text(NUMBERS, encoding="utf-8")
    (repo / "src" / "tally" / "words.py").write_text(WORDS, encoding="utf-8")
    for name, (module, assertion) in TESTS.items():
        (repo / "tests" / f"test_{name}.py").write_text(
            f"from tally.{module} import {name}\n\n\ndef test_{name}():\n    {assertion}\n", encoding="utf-8")
    return repo


def _last_attempt(ledger: Ledger) -> dict:
    attempts = [entry["data"] for entry in ledger if entry["kind"] == "kaizen.attempt"]
    return attempts[-1] if attempts else {}


def run_kaizen_demo(home: Path, *, out: Callable[[str], None] = print,
                    trial_settings: dict | None = None, author: Instrument | None = None) -> dict[str, Any]:
    """The demo; ``author`` replaces SR5's replayed author (for example a manual chat instrument)."""
    home = Path(home)
    ledger = Ledger(home / "ledger.jsonl")
    g0 = generations.active(home)
    repo = write_workspace(home / "demo-kaizen-workspace")
    opportunities = discover(repo, scratch=home / "scratch")["opportunities"]
    instruments: dict[str, Instrument] = {"stand-in": KaizenStandIn()}
    if author is not None:
        instruments["author"] = author
    router = Router(instruments, {"repair": "stand-in", "kaizen": "author" if author is not None else "stand-in"},
                    backoff_s=(0,), sleep=lambda s: None)
    statuses: list[str] = []

    def on_step(step: dict) -> None:
        if step.get("lane") == "object":
            statuses.append(step["status"])
            arm = f", trial arm {step['trial_arm']}" if step.get("trial_arm") else ""
            out(f"   {step['key']}: {step['status']} (generation {step['generation']}{arm})")

    out(f"1. Struggle. The shipped organ g0 ({g0}) serves {len(opportunities)} slips twice. A stand-in plays a weak")
    out("   model whose navigation answers are always malformed (the demo's model is scripted; see --help).")
    first = run_loop(home=home, opportunities=opportunities * 2, seed=SEED, router=router, min_experience=10 ** 6,
                     on_step=on_step)
    out(f"   g0 repaired {first['strict_successes']} of {first['object_steps']}. Attention: {first['attention']['mode']}.")

    out("2. Kaizen. Runesmith diagnoses its own telemetry and asks the author for a change to the organ.")
    if author is not None:
        out(f"   The author is {author.model} ({author.kind}). Its request follows; the demo waits for the answer.")
    step = subject_step(home=home, store=ExperienceStore(home / "experience"), seed=SEED, router=router,
                        max_answered=1, bar=1, ledger=ledger)
    target = step.get("target") or {}
    out(f"   Target, by the declared rule: {target.get('family') or target.get('stage')} "
        f"(share {target.get('share')}).")
    b = load_b_answer() if author is None else _last_attempt(ledger)
    source = "the answer gpt-oss-120b wrote for this target in SR5" if author is None else f"answered by {b.get('author')}"
    out(f"   The author's mechanism ({source}): {str(b.get('mechanism'))[:160]}...")
    out(f"   Its prediction: {str(b.get('prediction'))[:140]}")
    out(f"   Its falsifier: {str(b.get('falsifier'))[:140]}")
    out(f"3. Qualification on held-out replays: g0 {step['baseline']['strict_successes']} vs candidate "
        f"{(step.get('best') or {}).get('strict_successes')}. Decision: {step['decision']}.")
    candidate = step.get("generation")
    result: dict[str, Any] = {"g0": g0, "first": {"strict_successes": first["strict_successes"],
                                                  "served": first["object_steps"]},
                              "kaizen": step, "candidate": candidate, "trial": None, "active": generations.active(home)}
    if not candidate:
        out("   No candidate was frozen, so there is nothing to trial.")
        return result
    out(f"   Frozen, not active: {candidate}. It must now win an online trial on new work.")
    opened = open_trial_for(home, candidate, trial_settings=trial_settings or
                            {"look_every": 4, "min_per_arm": 4, "max_per_arm": 8})
    out(f"4. Trial. Each new opportunity goes to g0 or the candidate by a seeded coin (level per look "
        f"{opened.get('level_per_look')}).")
    statuses.clear()
    for _ in range(4):                          # the coin decides the arms, so serve batches until the trial concludes
        run_loop(home=home, opportunities=opportunities, seed=SEED, router=router, min_experience=10 ** 6,
                 on_step=on_step)
        if not (home / "TRIAL.json").exists():
            break
    closed = sorted(home.glob(f"TRIAL-{candidate}-*.json"))
    trial = Trial.load(closed[-1]) if closed else Trial.load(home / "TRIAL.json")
    result.update(trial=trial.summary() if trial else None, active=generations.active(home))
    if trial and trial.looks:
        look = trial.looks[-1]
        out(f"   Look {look['look']}: g0 {look['incumbent'][0]}/{look['incumbent'][1]}, candidate "
            f"{look['candidate'][0]}/{look['candidate'][1]}, p = {look['p_candidate_better']} -> {trial.decision}.")
    out(f"   Active generation now: {generations.active(home)}"
        + (" (the candidate, activated by compare-and-swap)." if generations.active(home) == candidate else "."))
    out(f"5. Report: {write_report(home)}. The whole story is in the hash-chained ledger.")
    if author is None:
        out("   Honest footnote: in SR5's preregistered confirmation on large repositories this same change was NOT shown")
        out("   to help (its fallback rescued 0 of 26 navigation failures there). The demo shows the machinery, not the result.")
    else:
        out("   Footnote: the demo's repair model is a scripted stand-in, so this shows your author's change passing the")
        out("   machinery on eight small slips. Whether a change helps on real work is what a preregistered trial decides.")
    return result
