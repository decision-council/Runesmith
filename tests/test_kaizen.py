"""Kaizen tests: diagnosis, target ranking, qualification and the keep-best loop."""

from __future__ import annotations

from pathlib import Path

from runesmith.instruments import CallOutcome, Router, ScriptedInstrument
from runesmith.kaizen.attention import BLOCKED, HEALTHY, RECOVERING, SUSPECTED, Attention
from runesmith.kaizen.diagnose import diagnose, signature
from runesmith.kaizen.improve import KaizenRun, apply_answer, better, smoke_test, static_check
from runesmith.opportunity import Envelope

ORGANS = Path(__file__).resolve().parents[1] / "runesmith" / "organs"


def rec(task, status, strict, cycle=10.0, reads=None, ref=None, calls=2):
    marks = [{"t": 0.1, "stage": "edit_loop", "reads": reads}] if reads is not None else []
    return {"task_id": task, "status": status, "strict_success": strict, "cycle_seconds": cycle,
            "marks": marks, "reference": ref,
            "calls": [{"purpose": "navigate", "t_start": 0.0, "t_end": cycle * 0.4, "error_kind": None}] * calls,
            "signal_runs": [{"t_start": 5.0, "t_end": 6.0}]}


def test_signature_refines_failures_with_reference_reads():
    ref = {"path": "src/a.py", "line": 3}
    assert signature(rec("t", "budget_exhausted", False, reads=["src/b.py"], ref=ref)) == "budget_exhausted|reference_not_read"
    assert signature(rec("t", "budget_exhausted", False, reads=["src/a.py"], ref=ref)) == "budget_exhausted|reference_read"
    assert signature(rec("t", "public_pass", True)) == "strict_success"
    assert signature(rec("t", "public_pass", False)) == "public_pass_but_strict_fail"
    assert signature(rec("t", "censored_transport", None)) == "censored"


def test_rank_targets_prefers_largest_lost_family_then_time():
    records = ([rec(f"s{i}", "public_pass", True) for i in range(5)]
               + [rec(f"n{i}", "navigation_output_failure", False) for i in range(3)]
               + [rec(f"b{i}", "budget_exhausted", False) for i in range(2)]
               + [rec("c", "censored_transport", None)])
    diagnosis = diagnose(records)
    assert diagnosis["uncensored"] == 10 and diagnosis["censored"] == 1
    first = diagnosis["targets"][0]
    assert first["type"] == "yield" and first["family"] == "navigation_output_failure" and first["share"] == 0.3
    assert diagnosis["targets"][-1]["type"] == "cycle_time"


def test_static_check_and_apply_answer():
    source = (ORGANS / "repair.py").read_text(encoding="utf-8")
    assert static_check(source) == []
    assert static_check("import os\ndef run(view, cockpit):\n    return {}\n") == ["import of 'os' is not allowed"]
    assert "no top-level run" in static_check("x = 1\n")[0]
    new, problems = apply_answer(source, {"edits": [{"old_text": "MAX_MODEL_CALLS = 5", "new_text": "MAX_MODEL_CALLS = 4"}],
                                          "module_source": ""})
    assert problems == [] and "MAX_MODEL_CALLS = 4" in new
    _, problems = apply_answer(source, {"edits": [{"old_text": "def ", "new_text": "def  "}], "module_source": ""})
    assert "occurs" in problems[0]


def test_smoke_test_accepts_g0_and_rejects_a_crashing_organ(tmp_path):
    assert smoke_test(ORGANS, "repair", tmp_path)["ok"]
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "repair.py").write_text("def run(view, cockpit):\n    raise RuntimeError('boom')\n", encoding="utf-8")
    result = smoke_test(broken, "repair", tmp_path)
    assert not result["ok"] and "boom" in result["error"]


def test_better_is_strict_keep_best():
    base = {"strict_successes": 10, "total_cycle_s": 1000.0, "organ_errors": 0}
    assert better({"strict_successes": 11, "total_cycle_s": 2000.0, "organ_errors": 0}, base)
    assert not better({"strict_successes": 10, "total_cycle_s": 990.0, "organ_errors": 0}, base)
    assert better({"strict_successes": 10, "total_cycle_s": 900.0, "organ_errors": 0}, base)
    assert not better({"strict_successes": 20, "total_cycle_s": 100.0, "organ_errors": 1}, base)


def test_kaizen_run_keeps_best_and_logs_every_attempt(tmp_path):
    baseline = ([rec(f"s{i}", "public_pass", True) for i in range(2)]
                + [rec(f"n{i}", "navigation_output_failure", False) for i in range(4)])
    good_edit = {"hypotheses": ["h"], "mechanism": "m", "prediction": "p", "falsifier": "f", "module_source": "",
                 "edits": [{"old_text": "MAX_MODEL_CALLS = 5", "new_text": "MAX_MODEL_CALLS = 5  # kaizen"}]}
    answers = [CallOutcome(False, error_kind="output", error="truncated"),                     # iteration 1
               dict(good_edit, edits=[{"old_text": "not present anywhere", "new_text": "x"}]),  # iteration 2
               good_edit]                                                                       # iteration 3
    router = Router({"author": ScriptedInstrument("author", answers)}, {"kaizen": "author"},
                    backoff_s=(0,), sleep=lambda s: None)
    replays = []

    def dev_evaluate(organ_dir, label):
        replays.append(label)
        return [rec(f"s{i}", "public_pass", True) for i in range(5)] + [rec("n0", "budget_exhausted", False)]

    run = KaizenRun(incumbent_organs=ORGANS, module="repair", router=router, baseline_records=baseline,
                    baseline_score={"strict_successes": 2, "total_cycle_s": 60.0, "organ_errors": 0},
                    dev_evaluate=dev_evaluate, out_dir=tmp_path / "kz", scratch=tmp_path / "scratch",
                    envelope=Envelope(), max_answered=3, patience=4)
    result = run.run()
    assert result["decision"] == "candidate" and result["best_iteration"] == 3
    assert replays == ["iter-03"]
    stages = [a.get("stage") for a in result["attempts"]]
    assert stages == ["author_output", "apply", "dev_replay"]
    assert (tmp_path / "kz" / "iter-03" / "organs" / "repair.py").read_text(encoding="utf-8").count("# kaizen") == 1
    assert (tmp_path / "kz" / "PDSA_LOG.jsonl").exists()


def test_confirm_replay_rejects_a_lucky_candidate(tmp_path):
    baseline = [rec("s0", "public_pass", True)] + [rec(f"n{i}", "navigation_output_failure", False) for i in range(3)]
    edit = {"hypotheses": ["h"], "mechanism": "m", "prediction": "p", "falsifier": "f", "module_source": "",
            "edits": [{"old_text": "MAX_MODEL_CALLS = 5", "new_text": "MAX_MODEL_CALLS = 5  # lucky"}]}
    router = Router({"author": ScriptedInstrument("author", [edit])}, {"kaizen": "author"}, backoff_s=(0,),
                    sleep=lambda s: None)
    outcomes = iter([5, 0, 0])            # first replay looks great, the confirmations do not

    def dev_evaluate(organ_dir, label):
        wins = next(outcomes)
        return [rec(f"s{i}", "public_pass", True) for i in range(wins)] + \
               [rec(f"f{i}", "budget_exhausted", False) for i in range(6 - wins)]

    run = KaizenRun(incumbent_organs=ORGANS, module="repair", router=router, baseline_records=baseline,
                    baseline_score={"strict_successes": 2, "total_cycle_s": 60.0, "organ_errors": 0},
                    dev_evaluate=dev_evaluate, out_dir=tmp_path / "kz", scratch=tmp_path / "scratch",
                    envelope=Envelope(), max_answered=1, confirm_replays=2)
    result = run.run()
    assert result["decision"] == "no_improvement"
    attempt = result["attempts"][0]
    assert attempt["stage"] == "dev_replay_confirmed" and attempt["replays"] == 3
    assert abs(attempt["score"]["strict_successes"] - 5 / 3) < 1e-9


def test_attention_rises_under_struggle_and_recovers():
    attention = Attention()
    assert attention.observe("nav_fail", success=False) == HEALTHY
    assert attention.observe("nav_fail", success=False) == SUSPECTED
    assert attention.observe("nav_fail", success=False) == BLOCKED
    lanes = [attention.next_lane() for _ in range(10)]
    assert lanes.count("subject") == 4
    attention.subject_repaired()
    assert attention.mode == RECOVERING
    for _ in range(3):
        attention.observe("-", success=True)
    assert attention.mode == HEALTHY


def test_attention_detects_yield_drift_without_a_recurring_signature():
    import random
    rng = random.Random(7)
    attention = Attention()
    for i in range(30):                                   # baseline: about 60% yield, varied failures
        attention.observe(f"fail-{i}", success=rng.random() < 0.6)
    assert attention.p0 is not None and attention.mode == HEALTHY
    for i in range(100):                                  # stable process: no alarm
        attention.observe(f"stable-{i}", success=rng.random() < 0.6)
    assert attention.mode == HEALTHY, attention.transitions
    for i in range(120):                                  # yield drops to about 15%; every failure is different
        attention.observe(f"drift-{i}", success=rng.random() < 0.15)
        if attention.mode == BLOCKED:
            break
    assert attention.mode == BLOCKED and attention.blocking_signature == "yield_drift"
    assert "yield drift" in attention.transitions[-1]["reason"]
    attention.subject_repaired()                          # a new generation: the baseline is re-estimated
    assert attention.p0 is None and attention.baseline == [] and attention.cusum == 0.0


def test_drift_chart_ignores_censoring_and_a_perfect_baseline_needs_repeated_failures():
    attention = Attention()
    for _ in range(30):
        attention.observe("-", success=True)
    for _ in range(5):
        attention.observe("transport", success=False, censored=True)
    assert 0.9 < attention.p0 < 0.95 and attention.mode != BLOCKED   # Wilson lower bound, not 1.0
    attention.observe("new-a", success=False)
    attention.observe("new-b", success=False)
    assert attention.mode == HEALTHY                      # two different failures after 30 successes: not yet drift
    attention.observe("new-c", success=False)
    assert attention.mode == BLOCKED and attention.blocking_signature == "yield_drift"


def test_attention_state_survives_a_save_and_load(tmp_path):
    attention = Attention()
    for i in range(35):
        attention.observe(f"f{i % 4}", success=i % 3 == 0)
    attention.next_lane()
    path = tmp_path / "ATTENTION.json"
    attention.save(path)
    again = Attention.load(path)
    assert again.snapshot() == attention.snapshot()
    assert again.recent.maxlen == attention.window and again.p0 == attention.p0
    assert Attention.load(tmp_path / "missing.json") is None
