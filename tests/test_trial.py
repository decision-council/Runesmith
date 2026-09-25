"""Online-trial tests: exact test, sequential decisions, and activation inside the run loop."""

from __future__ import annotations

import math

import pytest

from runesmith import cli, generations, loop
from runesmith.instruments import Router
from runesmith.kaizen.improve import FixtureInstrument
from runesmith.kaizen.trial import Trial, fisher_one_sided

from test_kernel import make_repo

HINTS = {"reads": [{"path": "src/calc/ops.py", "symbols": ["add"]}],
         "edits": [{"path": "src/calc/ops.py", "old_text": "return a - b", "new_text": "return a + b"}]}


def test_fisher_one_sided_matches_hand_computation():
    expected = (math.comb(10, 8) * math.comb(10, 2) + math.comb(10, 9) * 10 + 1) / math.comb(20, 10)
    assert fisher_one_sided(8, 10, 2, 10) == pytest.approx(expected)
    assert fisher_one_sided(5, 10, 5, 10) > 0.5
    assert fisher_one_sided(0, 0, 3, 5) == 1.0


def feed(trial, outcomes):
    decision = None
    for arm, success in outcomes:
        decision = trial.record(arm, success)
        if decision:
            break
    return decision


def test_clearly_better_candidate_is_activated_at_the_first_look():
    trial = Trial(incumbent="g0", candidate="g1", seed="s", alpha=0.05, look_every=10, max_per_arm=60, min_per_arm=10)
    outcomes = [("candidate", i != 0) for i in range(10)] + [("incumbent", i < 2) for i in range(10)]
    assert feed(trial, outcomes) == "activate"
    assert trial.looks[0]["p_candidate_better"] <= trial.level


def test_equal_arms_end_in_rejection_never_activation():
    trial = Trial(incumbent="g0", candidate="g1", seed="s", alpha=0.05, look_every=5, max_per_arm=20, min_per_arm=5)
    outcomes = [(arm, i % 2 == 0) for i in range(20) for arm in ("candidate", "incumbent")]
    assert feed(trial, outcomes) == "reject"
    assert all(look["p_candidate_better"] > trial.level for look in trial.looks)


def test_censored_outcomes_are_not_counted_and_assignment_is_seeded():
    trial = Trial(incumbent="g0", candidate="g1", seed="s")
    assert trial.record("candidate", None) is None and trial.counts["candidate"] == [0, 0]
    assert [trial.assign(f"k{i}") for i in range(20)] == [trial.assign(f"k{i}") for i in range(20)]
    assert {trial.assign(f"k{i}") for i in range(50)} == {"candidate", "incumbent"}


def test_loop_trial_activates_a_better_candidate_by_compare_and_swap(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    g0 = generations.active(home)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "repair.py").write_text("def run(view, cockpit):\n    return {'status': 'gave_up', 'final_files': {}}\n",
                                      encoding="utf-8")
    weak = generations.freeze(broken, home, label="weak incumbent", parent=g0)
    generations.activate(home, weak["id"], expected=g0)
    calls = {"n": 0, "while_trial_open": 0}

    def fake_subject_step(**kwargs):
        calls["n"] += 1
        calls["while_trial_open"] += int((home / "TRIAL.json").exists())
        if calls["n"] == 1:
            return {"decision": "frozen_candidate", "generation": g0}
        return {"decision": "no_improvement"}

    monkeypatch.setattr(loop, "subject_step", fake_subject_step)
    repo = make_repo(tmp_path)
    opportunity = {"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"],
                   "judge_tests": ["tests/test_ops.py"], "issue": "add() returns a wrong value"}
    router = Router({"y": FixtureInstrument(HINTS)}, {"repair": "y", "kaizen": "y"}, backoff_s=(0,), sleep=lambda s: None)
    from runesmith.kaizen.attention import Attention
    attention = Attention()
    attention.credit_bp = 9_000
    summary = loop.run_loop(home=home, opportunities=[opportunity] * 24, seed="trial-test", router=router,
                            min_experience=1, kaizen_every=1, attention=attention,
                            trial_settings={"alpha": 0.05, "look_every": 3, "max_per_arm": 6, "min_per_arm": 3})
    assert calls["while_trial_open"] == 0                    # no campaign runs while a trial is open
    assert summary["trials"] and summary["trials"][0]["decision"] == "activate"
    assert generations.active(home) == g0                    # CAS moved the pointer to the candidate
    assert (home / f"TRIAL-{g0}-activate.json").exists() and not (home / "TRIAL.json").exists()
