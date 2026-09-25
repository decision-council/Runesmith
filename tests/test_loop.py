"""Run-loop tests: experience accumulates, attention schedules Kaizen, generations stay safe."""

from __future__ import annotations

from runesmith import cli, generations
from runesmith.instruments import Router, ScriptedInstrument
from runesmith.kaizen.attention import Attention
from runesmith.kaizen.improve import FixtureInstrument
from runesmith.loop import ExperienceStore, run_loop

from test_kernel import make_repo

HINTS = {"reads": [{"path": "src/calc/ops.py", "symbols": ["add"]}],
         "edits": [{"path": "src/calc/ops.py", "old_text": "return a - b", "new_text": "return a + b"}]}


def test_run_loop_stores_experience_and_runs_a_kaizen_step(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    repo = make_repo(tmp_path)
    opportunity = {"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"],
                   "judge_tests": ["tests/test_ops.py"], "issue": "add() returns a wrong value"}
    author = ScriptedInstrument("author", [{
        "hypotheses": ["h"], "mechanism": "comment only", "prediction": "no change", "falsifier": "f",
        "module_source": "", "edits": [{"old_text": "MAX_MODEL_CALLS = 5", "new_text": "MAX_MODEL_CALLS = 5  # noted"}]}])
    router = Router({"y": FixtureInstrument(HINTS), "author": author}, {"repair": "y", "kaizen": "author"},
                    backoff_s=(0,), sleep=lambda s: None)
    attention = Attention()
    attention.credit_bp = 9000                        # make a subject step due as soon as experience suffices
    steps = []
    summary = run_loop(home=home, opportunities=[opportunity] * 6, seed="loop-test", router=router,
                       min_experience=4, kaizen_every=4, max_answered=1, attention=attention, on_step=steps.append)
    assert summary["object_steps"] == 6 and summary["strict_successes"] == 6
    assert summary["subject_steps"] >= 1
    subject = [s for s in steps if s["lane"] == "subject"]
    assert subject and subject[0]["decision"] in ("no_improvement", "candidate", "frozen_candidate", "within_noise",
                                                  "not_enough_experience")   # a tie on successes is timing-dependent
    assert len(ExperienceStore(home / "experience").tasks()) == 6
    assert generations.verify(home / "generations" / generations.active(home))["ok"]
    assert "return a - b" in (repo / "src" / "calc" / "ops.py").read_text(encoding="utf-8")   # the loop never edits objects


def test_freeze_rule_refuses_a_gain_within_the_incumbents_own_replay_noise():
    from runesmith.loop import freeze_rule
    # SR5's numbers: the successor scored 17/32 on validation. Replayed once, the incumbent scored 11, and the
    # candidate would freeze. Identical organs differed by 6 between replays (10 vs 16), and the successor
    # then failed on fresh work.
    assert freeze_rule(17, [11], bar=1)["freeze"] is True                # the old single-replay rule
    rule = freeze_rule(17, [10, 16], bar=1)
    assert rule["noise"] == 6 and rule["gain"] == 4 and rule["freeze"] is False
    assert freeze_rule(9, [0, 0], bar=1)["freeze"] is True               # a clear gain over a stable incumbent
    assert freeze_rule(3, [2, 2], bar=2)["freeze"] is False              # the declared bar still applies


def test_replayed_sources_keep_their_exact_bytes(tmp_path):
    """Materialized parent sources are written as stored; text mode would add CR on Windows."""
    store = ExperienceStore(tmp_path / "exp")
    store.add(key="k1", opportunity={"repo": "r", "failing_tests": ["t"], "issue": "i"},
              parent_src={"src/pkg/mod.py": "def f():\n    return 1\n"}, record={"status": "x"}, final={})
    [task] = store.tasks()
    store.materialize(task, tmp_path / "copy")
    assert (tmp_path / "copy" / "src" / "pkg" / "mod.py").read_bytes() == b"def f():\n    return 1\n"
