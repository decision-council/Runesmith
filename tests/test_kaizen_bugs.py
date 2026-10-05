"""Four Kaizen bugs found with a Python project and a missing or dead Improver, each pinned by a test.

1. Kaizen on with no Improver model stopped all repair: every round replayed the validation split and then died with
   ``KeyError: no instrument serves role 'kaizen'``. Now there is no campaign, it is said once, and repairs go on.
2. A dead Improver cost at least 54 minutes per campaign (the router's default backoff, six failed calls). Now a campaign
   asks on a short leash and gives up the campaign, not the round.
3. ``kaizen_every`` did nothing between rounds (the count started again at every round). Now it is kept in the home.
4. A campaign overrode an instrument's own reasoning effort with "high". Now the instrument's setting wins.
"""

from __future__ import annotations

import time

import pytest

from runesmith import cli
from runesmith.instruments import CallOutcome, Instrument, Router, ScriptedInstrument
from runesmith.kaizen.attention import Attention
from runesmith.kaizen.improve import FixtureInstrument, KaizenRun
from runesmith.loop import (CAMPAIGN_BACKOFF_S, ExperienceStore, improver_available, load_campaign_state, run_loop)
from runesmith.opportunity import Envelope

from test_kaizen import ORGANS, rec
from test_kernel import make_repo
from test_loop import HINTS


def opportunity_for(repo):
    return {"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"], "judge_tests": ["tests/test_ops.py"],
            "issue": "add() returns a wrong value"}


def seed_experience(home, repo, count, ws_seed=None):
    """``count`` stored attempts with fixed keys. A task's half of the split depends on the seed and its key, so a seed
    that fills both halves is found (a fixed one, unless the Studio's own is given); returns the store and that seed."""
    store = ExperienceStore(home / "experience")
    parent = {"src/calc/ops.py": (repo / "src" / "calc" / "ops.py").read_bytes().decode("utf-8")}
    for index in range(count):
        store.add(key=f"seed-{index:02d}", opportunity=opportunity_for(repo), parent_src=parent,
                  record={"status": "public_pass", "strict_success": True, "cycle_seconds": 4.0, "model_calls": 2,
                          "marks": [], "calls": [{"purpose": "navigate", "t_start": 0.0, "t_end": 1.0}]}, final={})
    if ws_seed:
        return store, ws_seed
    for seed in [f"fixed-{i}" for i in range(100)]:
        experience, validation = store.split(seed)
        if experience and validation:
            return store, seed
    raise AssertionError("no seed fills both halves of the split")


class DeadImprover(Instrument):
    kind = "dead"

    def __init__(self) -> None:
        super().__init__("dead-improver", "dead-1")
        self.calls = 0

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        self.calls += 1
        return CallOutcome(False, error_kind="transport", error="connection refused (the Improver route is down)")


class Recorder(Instrument):
    """Remembers the reasoning effort each call arrived with, and answers with an unusable answer."""
    kind = "recorder"

    def __init__(self, name, default=None) -> None:
        super().__init__(name, name + "-1")
        self.efforts = []
        self.default_reasoning = default

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        self.efforts.append(reasoning_effort)
        return CallOutcome(False, error_kind="output", error="truncated")


def make_home(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    return home, make_repo(tmp_path)


# ------------------------------------------------------------------------------------------------- bug 1 --

def test_without_an_improver_there_is_no_campaign_and_the_repairs_go_on(tmp_path):
    home, repo = make_home(tmp_path)
    _, seed = seed_experience(home, repo, 4)
    router = Router({"y": FixtureInstrument(HINTS)}, {"repair": "y"}, backoff_s=(0,), sleep=lambda s: None)
    assert not improver_available(router)
    attention = Attention()
    attention.credit_bp = 9000                       # a campaign is due, and the experience is there
    steps = []
    summary = run_loop(home=home, opportunities=[opportunity_for(repo)] * 3, seed=seed, router=router, min_experience=2,
                       kaizen_every=1, attention=attention, on_step=steps.append)
    assert summary["object_steps"] == 3 and summary["strict_successes"] == 3     # every repair was served
    assert summary["subject_steps"] == 0 and not [s for s in steps if s["lane"] == "subject"]
    assert load_campaign_state(home) is None         # nothing was started, so nothing counts as the last campaign


def test_a_campaign_that_cannot_start_replays_nothing(tmp_path):
    from runesmith.loop import subject_step
    home, repo = make_home(tmp_path)
    store, seed = seed_experience(home, repo, 4)
    router = Router({"y": FixtureInstrument(HINTS)}, {"repair": "y"}, backoff_s=(0,), sleep=lambda s: None)
    before = time.time()
    result = subject_step(home=home, store=store, seed=seed, router=router)
    assert result["decision"] == "no_improver" and time.time() - before < 2     # no replay of the validation split
    assert not (home / "scratch").exists() or not any((home / "scratch").iterdir())


def test_the_studio_says_once_that_no_improver_is_set_up_and_still_repairs(tmp_path):
    from runesmith.app import self_notices
    from runesmith.app.worker import EventBus, Worker
    from runesmith.app.workspace import Workspace
    from test_studio import FIX_ANSWERS, scripted
    workspace = tmp_path / "ws"
    workspace.mkdir()
    make_repo(workspace)
    ws = Workspace(workspace)
    ws.update_settings({"onboarded": True, "auto_work": False, "kaizen": True, "min_experience": 2, "kaizen_every": 1})
    scripted(ws, FIX_ANSWERS)                        # the repair role only: nobody serves the Improver's role
    assert ws.ready()["repair"] and not ws.ready()["kaizen"]
    seed_experience(ws.home, workspace / "repo", 4, ws_seed=ws.seed())      # enough experience: a campaign would be due
    worker = Worker(ws, EventBus())
    worker.start()
    try:
        worker.enqueue("round")
        deadline = time.time() + 180
        while time.time() < deadline and not any(j["kind"] == "round" for j in worker.history):
            time.sleep(0.2)
        job = next(j for j in worker.history if j["kind"] == "round")
    finally:
        worker.close()
    assert job["result"] == "done", job                  # it used to end "failed": KeyError, no instrument serves role 'kaizen'
    assert ws.work()["last_round"]["accepted"] == 1      # and the repair was served
    [said] = [row for row in (ws.home / "AUTOMATIC.json").read_text(encoding="utf-8").split("\n") if "Improver" in row]
    assert "no Improver model is set up" in said
    log = (workspace / "RUNESMITH.md").read_text(encoding="utf-8")
    assert log.count("no Improver model is set up") == 1
    # said once: asking again, with nothing changed, says nothing; with an Improver it is quiet and re-armed
    assert self_notices.improver_check(ws, kaizen_on=True, improver_ready=False) is None
    assert self_notices.improver_check(ws, kaizen_on=True, improver_ready=True) is None
    assert self_notices.improver_check(ws, kaizen_on=True, improver_ready=False) is not None


# ------------------------------------------------------------------------------------------------- bug 2 --

def test_a_dead_improver_gives_up_the_campaign_after_a_short_wait_and_the_round_goes_on(tmp_path):
    home, repo = make_home(tmp_path)
    _, seed = seed_experience(home, repo, 4)
    dead, slept = DeadImprover(), []
    router = Router({"y": FixtureInstrument(HINTS), "dead": dead}, {"repair": "y", "kaizen": "dead"},
                    sleep=slept.append)               # the router's own default backoff: 15+30+45+60+90+120+180 s a call
    attention = Attention()
    attention.credit_bp = 9000
    steps = []
    summary = run_loop(home=home, opportunities=[opportunity_for(repo)] * 2, seed=seed, router=router, min_experience=2,
                       kaizen_every=1, attention=attention, on_step=steps.append)
    [campaign] = [s for s in steps if s["lane"] == "subject"]
    assert campaign["decision"] == "improver_unreachable"
    assert dead.calls == len(CAMPAIGN_BACKOFF_S) + 1         # one call, retried on the short leash, then given up
    assert sum(slept) == sum(CAMPAIGN_BACKOFF_S) <= 60       # about a minute, not the 54 minutes of the default
    assert summary["object_steps"] == 2 and summary["strict_successes"] == 2     # the round went on and served both


def test_a_campaign_that_raises_ends_the_campaign_not_the_round(tmp_path, monkeypatch):
    from runesmith import loop
    home, repo = make_home(tmp_path)
    _, seed = seed_experience(home, repo, 4)
    router = Router({"y": FixtureInstrument(HINTS)}, {"repair": "y", "kaizen": "y"}, backoff_s=(0,), sleep=lambda s: None)

    def broken(**kwargs):
        raise RuntimeError("the Improver's answer could not be read")

    monkeypatch.setattr(loop, "subject_step", broken)
    attention = Attention()
    attention.credit_bp = 9000
    steps = []
    summary = run_loop(home=home, opportunities=[opportunity_for(repo)] * 2, seed=seed, router=router, min_experience=2,
                       kaizen_every=1, attention=attention, on_step=steps.append)
    [campaign] = [s for s in steps if s["lane"] == "subject"]
    assert campaign["decision"] == "campaign_failed" and "could not be read" in campaign["error"]
    assert summary["object_steps"] == 2                       # the repairs were served all the same


# ------------------------------------------------------------------------------------------------- bug 3 --

def test_kaizen_every_holds_between_rounds(tmp_path):
    home, repo = make_home(tmp_path)
    _, seed = seed_experience(home, repo, 4)
    dead = DeadImprover()
    router = Router({"y": FixtureInstrument(HINTS), "dead": dead}, {"repair": "y", "kaizen": "dead"}, backoff_s=(0,),
                    sleep=lambda s: None)

    def round_of_one():
        attention = Attention()
        attention.credit_bp = 9000                            # attention would take a subject slot whenever one is ready
        steps = []
        run_loop(home=home, opportunities=[opportunity_for(repo)], seed=seed, router=router, min_experience=4,
                 kaizen_every=3, attention=attention, on_step=steps.append)
        return [s for s in steps if s["lane"] == "subject"]

    assert len(round_of_one()) == 1                           # 4 stored: the first campaign
    assert load_campaign_state(home) == 4
    assert round_of_one() == []                               # 5 stored, 1 new since the campaign: not 3 yet (it ran again)
    assert round_of_one() == []                               # 6 stored, 2 new
    assert len(round_of_one()) == 1                           # 7 stored, 3 new: the next campaign
    assert load_campaign_state(home) == 7


# ------------------------------------------------------------------------------------------------- bug 4 --

def test_a_campaign_respects_an_instruments_own_reasoning_effort(tmp_path):
    baseline = ([rec(f"s{i}", "public_pass", True) for i in range(2)]
                + [rec(f"n{i}", "navigation_output_failure", False) for i in range(4)])

    def one_call(instrument, name):
        router = Router({name: instrument}, {"kaizen": name}, backoff_s=(0,), sleep=lambda s: None)
        KaizenRun(incumbent_organs=ORGANS, module="repair", router=router, baseline_records=baseline,
                  baseline_score={"strict_successes": 2, "total_cycle_s": 60.0, "organ_errors": 0},
                  dev_evaluate=lambda organ_dir, label: [], out_dir=tmp_path / name, scratch=tmp_path / "scratch",
                  envelope=Envelope(), max_answered=1, patience=1).run()
        return instrument.efforts

    assert one_call(Recorder("low-model", default="low"), "low-model") == ["low"]    # the owner's setting stands
    assert one_call(Recorder("plain-model"), "plain-model") == ["high"]              # no setting: the campaign's own


def test_the_routers_default_order_is_unchanged_for_every_other_call():
    asked, plain = Recorder("a", default="low"), Recorder("b")
    router = Router({"a": asked, "b": plain}, {"x": "a", "y": "b"}, backoff_s=(), sleep=lambda s: None)
    for role in ("x", "y"):
        router.call(role, prompt="p", system="s", schema=None, max_tokens=10, key="k", reasoning_effort="high")
    router.call("x", prompt="p", system="s", schema=None, max_tokens=10, key="k")
    assert asked.efforts == ["high", "low"] and plain.efforts == ["high"]     # a call's effort wins, then the instrument's
