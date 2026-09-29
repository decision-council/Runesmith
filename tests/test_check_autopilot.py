"""The check autopilot (asked for by the owner of journey J11, 2026-09-29): Runesmith approves proposed acceptance
checks itself only when every gate passes, turns down the rest with the reason, and leaves what it cannot judge."""
import json

import pytest

from runesmith.app import acceptance_autopilot as autopilot
from runesmith.app.acceptance_proposals import acceptance_file, approve, propose, status
from runesmith.app.worker import EventBus, Worker
from test_acceptance_examples import EXAMPLES, workspace



def proposal(**overrides):
    base = {"id": "p1", "style": "examples", "drafted_by": "kilo3:nvidia/nemotron-3-super-120b-a12b:free",
            "dry_run": {"verdict": "fails_now", "ran": 2, "failures": 2, "errors": 0},
            "checks": [{"test": "test_01_x", "says": "x is 50 at 1 s"}],
            "examples": [{"test": "test_01_x", "files": [{"name": "x.motion.json", "text": "{}"}],
                          "steps": [{"run": ["node", "motion.mjs", "x.motion.json", "--at", "1"],
                                     "expect": {"exit": "ok", "lines": [{"has": "x", "number": 50}], "shows": ["x"]}}],
                          "contains": [{"name": "out.svg", "texts": ["<rect"]}], "exists": ["out.svg"]}]}
    base.update(overrides)
    return base


@pytest.mark.parametrize("change,finding", [
    ({"dry_run": {"verdict": "passes_now"}}, "already pass"),
    ({"dry_run": {"verdict": "broken"}}, "could not run"),
    ({"checks": [{"test": "t", "says": "s", "missing_input": ["position.motion.json"]}]}, "which nothing creates"),
    ({"checks": [{"test": "t", "says": "s", "unstated": ["x 50"]}]}, "exact text its sentence does not say"),
    ({"revision": {"after": "passes_now", "error": "no answer"}}, "revision Runesmith asked for did not work"),
])
def test_what_runesmith_found_itself_keeps_checks_from_approval(change, finding):
    assert any(finding in reason for reason in autopilot.gates(proposal(**change)))
    assert autopilot.gates(proposal()) == []


def test_checks_it_cannot_judge_wait_for_the_owner():
    assert "not tried" in autopilot.undecidable(proposal(dry_run={"verdict": "not_run"}))
    assert "examples" in autopilot.undecidable(proposal(style="code"))
    assert autopilot.undecidable(proposal()) is None


def test_the_cross_check_is_asked_questions_without_the_expected_values():
    rows = autopilot.questions(proposal())
    assert sorted((r["kind"], r["expected"]) for r in rows) == sorted(
        [("word", "yes"), ("word", "no")] * 4 + [("number", 50), ("number", 57.0), ("word", "no")])  # + its twin, the decoy
    assert all("50" not in r["question"] and "57" not in r["question"] for r in rows)   # the value is never shown
    number = next(r for r in rows if r["kind"] == "number" and not r["twin"])
    assert autopilot.agrees(number, "50") and autopilot.agrees(number, "x = 50.0") and not autopilot.agrees(number, "1")
    assert autopilot.agrees(number, "At t=1, x is 50") is None                # two numbers: unclear, never a match
    word = next(r for r in rows if r["kind"] == "word")
    assert autopilot.agrees(word, "probably") is None and autopilot.agrees(word, None) is None
    assert rows == autopilot.questions(proposal())                             # the same checks, the same questions


def test_the_second_model_is_never_the_one_that_wrote_the_checks(tmp_path):
    ws = workspace(tmp_path, [])
    config = ws.config()
    config["instruments"].update({
        "gate-nemotron": {"kind": "scripted", "model": "nvidia:nvidia/nemotron-3-super-120b-a12b",
                          "fallback_models": ["kilo3:nvidia/nemotron-3-super-120b-a12b:free"]},
        "gate-groq": {"kind": "scripted", "model": "groq3:openai/gpt-oss-120b"}})
    config["roles"]["acceptance"] = ["gate-nemotron", "gate-groq"]
    ws.save_config(config)
    assert autopilot.second_model(ws, "kilo3:nvidia/nemotron-3-super-120b-a12b:free") == "gate-groq"
    config["roles"]["acceptance"] = ["gate-nemotron"]
    config["roles"]["plan"] = ["gate-nemotron"]
    ws.save_config(config)
    assert autopilot.second_model(ws, "kilo3:nvidia/nemotron-3-super-120b-a12b:free") is None


def autopilot_workspace(tmp_path, checker_answers, verifier_answers):
    ws = workspace(tmp_path, checker_answers)
    config = ws.config()
    config["instruments"]["offline"]["model"] = "checker-model"
    config["instruments"]["verifier"] = {"kind": "scripted", "model": "verifier-model", "answers": list(verifier_answers)}
    config["roles"]["acceptance"] = ["offline", "verifier"]
    ws.save_config(config)
    ws.update_settings({"checks_autopilot": True})
    return ws


def answers_for(first, **overrides):
    return {"answers": [{"id": row["id"], "answer": str(overrides.get(row["id"], row["expected"]))}
                        for row in autopilot.questions(first)], "contradicts": "no"}


def test_checks_the_second_model_agrees_with_are_approved_by_the_autopilot(tmp_path):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [answers_for(first)]; ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "approve", verdict
    said, done = autopilot.act(ws, "m1", first, verdict)
    assert done == "approve" and "check autopilot approved them" in said and acceptance_file(ws, "m1").is_file()
    approved = status(ws)["m1"]["approved"]
    assert approved["provenance"] == "model-proposed, autopilot-approved" and "worked out the same" in approved["autopilot"]
    header = acceptance_file(ws, "m1").read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("# Runesmith check-autopilot acceptance (not owner-reviewed)") and "Owner acceptance" not in header


def test_a_disagreement_turns_the_checks_down_and_the_next_checker_hears_why(tmp_path):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    number = next(r for r in autopilot.questions(first) if r["kind"] == "number" and not r["twin"])
    twin = next(r for r in autopilot.questions(first) if r["pair"] == number["pair"] and r["twin"])
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [answers_for(first, **{number["id"]: 7, twin["id"]: 14})]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "turn_down" and "verifier-model worked out 7" in verdict["reason"], verdict
    autopilot.act(ws, "m1", first, verdict)
    from runesmith.app.acceptance_proposals import packet
    said = packet(ws, "m1", "examples")["owner_said_about_earlier_checks"]
    assert said and "check autopilot turned them down" in said[0] and "worked out 7" in said[0]
    assert autopilot.rounds_used(ws, "m1") == 1 and not acceptance_file(ws, "m1").is_file()


def test_after_two_turn_downs_the_checks_wait_for_the_owner(tmp_path, monkeypatch):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    monkeypatch.setattr(autopilot, "rounds_used", lambda ws, mid: autopilot.MAX_ROUNDS)
    monkeypatch.setattr(autopilot, "cross_check", lambda ws, mid, p: {"model": "v", "asked": 3, "disagreements": ["x"], "contradicts": None})
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "wait for you" in verdict["reason"]


def test_checks_the_owner_approved_are_never_replaced_by_the_autopilot(tmp_path):
    ws = autopilot_workspace(tmp_path, [EXAMPLES, EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    approve(ws, "m1", first["id"])
    second = propose(ws, ws.router(), "m1")
    verdict = autopilot.review(ws, "m1", second)
    assert verdict["decision"] == "owner" and "only you replace them" in verdict["reason"]


def test_with_the_autopilot_on_a_ready_milestone_without_checks_gets_them_first(tmp_path):
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"build_steps": True})
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("propose_acceptance", {"milestone": "m1"})
    ws.update_settings({"checks_autopilot": False})
    assert worker.scheduled_job() == ("build", {})


def test_a_second_model_that_agrees_with_everything_is_not_counted(tmp_path):
    # Review of the autopilot: a yes-saying second model approved a check that required the opposite of the milestone.
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    yes = {"answers": [{"id": r["id"], "answer": "yes" if r["kind"] == "word" and r["expected"] in ("yes", "no")
                        else str(r["expected"])} for r in autopilot.questions(first)], "contradicts": "no"}
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [yes]; ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "answered the same way as their opposite" in verdict["reason"], verdict


def test_a_check_requiring_the_opposite_is_turned_down(tmp_path):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    rows = autopilot.questions(first)
    claim = next(r for r in rows if r["pair"] and r["expected"] == "yes")
    negation = next(r for r in rows if r["pair"] == claim["pair"] and r["expected"] == "no")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [answers_for(first, **{claim["id"]: "no", negation["id"]: "yes"})]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "turn_down" and claim["question"] in verdict["reason"], verdict


def test_checks_that_call_a_function_wait_for_the_owner_and_one_check_passing_today_is_not_a_finding():
    calling = proposal(examples=[{"test": "t", "steps": [{"call": "pkg.mod.f", "args": [], "expect": {"returns": 1}}]}])
    assert "call a function" in autopilot.undecidable(calling)
    # Journey J11-G18: "without a style the picture stays as it is" passes today by design; held against it, the
    # Checker rewrote it into a wrong check. A set that passes today as a whole is still held back.
    assert autopilot.gates(proposal(checks=[{"test": "t", "says": "s", "passes_today": True}])) == []
    assert autopilot.gates(proposal(dry_run={"verdict": "passes_now"}))


def test_a_local_model_name_with_a_tag_is_its_own_family():
    assert autopilot._family("llama3:8b") == "llama3:8b" and autopilot._family("qwen2.5:7b") != autopilot._family("llama3:8b")
    assert autopilot._family("kilo3:nvidia/nemotron-3-super-120b-a12b:free") == autopilot._family("nvidia:nvidia/nemotron-3-super-120b-a12b")


def test_the_autopilot_stands_aside_when_the_owner_decided_meanwhile(tmp_path):
    from runesmith.app.acceptance_proposals import discard
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    discard(ws, "m1", first["id"], reason="the owner turned them down while the cross-check ran")
    said, done = autopilot.act(ws, "m1", first, {"decision": "approve", "reason": "clean"})
    assert done == "none" and "left them alone" in said and not acceptance_file(ws, "m1").is_file()


def test_a_model_answering_by_position_or_saying_yes_to_anything_is_not_counted(tmp_path):
    # Fix verifier: a model answering every pair "yes, then no" by position approved two contradictory checks.
    ws = autopilot_workspace(tmp_path, [], [])
    checks = proposal(drafted_by="checker-model")
    rows, seen, answers = autopilot.questions(checks), set(), []
    for r in rows:
        if r["pair"]:
            answers.append({"id": r["id"], "answer": "no" if r["pair"] in seen else "yes"})
            seen.add(r["pair"])
        else:
            answers.append({"id": r["id"], "answer": str(r["expected"])})
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [{"answers": answers, "contradicts": "no"}]
    ws.save_config(config)
    assert autopilot.review(ws, "m1", checks)["decision"] != "approve"
    anything = [{"id": r["id"], "answer": str(r["expected"]) if r["about"] != "decoy" else "yes"} for r in rows]
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [{"answers": anything, "contradicts": "no"}]
    ws.save_config(config)
    assert "said yes to a text nothing asks for" in autopilot.cross_check(ws, "m1", checks)["undecided"]


def test_a_check_that_only_asks_whether_the_program_finishes_waits_for_the_owner(tmp_path):
    ws = autopilot_workspace(tmp_path, [], [])
    exit_only = proposal(drafted_by="checker-model", examples=[{"test": "t", "steps": [
        {"run": ["python", "-m", "tally", "months"], "expect": {"exit": "ok"}}]}])
    assert "only ask whether the program finishes" in autopilot.cross_check(ws, "m1", exit_only)["undecided"]


def test_no_contradiction_in_a_full_sentence_is_no_contradiction():
    assert autopilot._contradiction("No contradiction.") is None and autopilot._contradiction(False) is None
    assert autopilot._contradiction("There is no contradiction with the other milestones.") is None
    assert autopilot._contradiction("m1 refuses an empty project file, which this check requires") is not None
    assert autopilot._contradiction("Nope, these are consistent.") is None
    assert autopilot._contradiction("Not consistent: m1 refuses what this accepts") is not None


def test_a_number_parrot_a_first_quoted_parrot_and_file_only_checks_are_all_caught(tmp_path):
    # Final autopilot check: copying a number from the command, copying the first quoted text, and a keyword rule on
    # checks without steps each got a wrong check approved.
    ws = autopilot_workspace(tmp_path, [], [])
    checks = proposal(drafted_by="checker-model")
    rows = autopilot.questions(checks)
    parrot = [{"id": r["id"], "answer": "1" if r["kind"] == "number" else str(r["expected"])} for r in rows]
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [{"answers": parrot, "contradicts": False}]
    ws.save_config(config)
    assert "undecided" in autopilot.cross_check(ws, "m1", checks)
    ordered = proposal(drafted_by="checker-model", examples=[{"test": "t", "steps": [
        {"run": ["python", "-m", "tally", "months"], "expect": {"order": ["2026-01", "2026-03"], "lines": [{"has": "2026-01", "number": 2}]}}]}])
    rows = autopilot.questions(ordered)
    first_quoted = [{"id": r["id"], "answer": r["question"].split("“")[1].split("”")[0] if r["kind"] == "text"
                     else str(r["expected"])} for r in rows]
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [{"answers": first_quoted, "contradicts": False}]
    ws.save_config(config)
    assert "undecided" in autopilot.cross_check(ws, "m1", ordered)
    files_only = proposal(drafted_by="checker-model", examples=[{"test": "t", "steps": [], "exists": ["README.md"],
                                                               "contains": [{"name": "README.md", "texts": ["Tally"]}]}])
    assert any(r["about"] == "decoy" for r in autopilot.questions(files_only))


def test_a_claimed_contradiction_is_the_owner_s_call(tmp_path):
    ws = autopilot_workspace(tmp_path, [], [])
    checks = proposal(drafted_by="checker-model")
    right = [{"id": r["id"], "answer": str(r["expected"])} for r in autopilot.questions(checks)]
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [{"answers": right, "contradicts": True, "contradiction": "m1 refuses this file"}]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", checks)
    assert verdict["decision"] == "owner" and "m1 refuses this file" in verdict["reason"]


def test_saving_a_model_keeps_its_request_limit_and_reasoning_effort(tmp_path):
    # Review of J11-B8: the Groq preset's request limit and a model's reasoning effort were dropped on save.
    from runesmith.app.workspace import WorkspaceError
    ws = autopilot_workspace(tmp_path, [], [])
    spec = {"kind": "openai", "model": "openai/gpt-oss-120b", "base_url": "https://api.groq.com/openai/v1",
            "preset": "groq", "max_request_tokens": 8000, "reasoning_effort": "low"}
    ws.save_instrument("groqfree", spec)
    saved = ws.config()["instruments"]["groqfree"]
    assert saved["max_request_tokens"] == 8000 and saved["reasoning_effort"] == "low"
    from runesmith.config import build_instrument
    assert build_instrument("groqfree", saved, ws.home).max_request_tokens == 8000
    for bad in ({"max_request_tokens": "lots"}, {"max_request_tokens": True}, {"max_request_tokens": 5},
                {"reasoning_effort": "maximum"}):
        with pytest.raises(WorkspaceError):
            ws.save_instrument("groqbad", dict(spec, **bad))


def test_the_test_button_sends_the_model_s_own_reasoning_effort(tmp_path, monkeypatch):
    # Review of J11-B8: "Test" under Thinking power built the model without its reasoning effort.
    from runesmith.app import providers
    from runesmith import config as config_module
    sent = {}

    class Fake:
        def complete(self, **kwargs):
            sent.update(kwargs)
            from runesmith.instruments import CallOutcome
            return CallOutcome(True, data={"ok": True})
    monkeypatch.setattr(config_module, "build_instrument", lambda *args, **kwargs: Fake())
    spec = {"kind": "openai", "model": "m", "base_url": "https://x.invalid/v1", "reasoning_effort": "low"}
    assert providers.test_instrument("x", spec, tmp_path)["ok"] and sent["reasoning_effort"] == "low"
    providers.test_instrument("x", dict(spec, reasoning_effort=None), tmp_path)
    assert sent["reasoning_effort"] is None


def test_a_scheduled_check_request_moves_the_schedule_on(tmp_path, monkeypatch):
    # Journey J11-B9: a scheduled check request did not move the schedule on, so failed ones ran back to back.
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"build_steps": True, "auto_work": True, "policy_chosen": True, "onboarded": True})
    worker = Worker(ws, EventBus())

    def refused(milestone):
        from runesmith.app.planner import PlannerUnavailable
        raise PlannerUnavailable("no acceptance checks: every model is busy")
    monkeypatch.setattr(worker, "_job_propose_acceptance", refused)
    assert worker._due() == 0
    worker._execute({"id": "own", "kind": "propose_acceptance", "params": {"milestone": "m1"}, "by": "owner"})
    assert worker._due() == 0                               # the owner's own request leaves the schedule alone
    worker._execute({"id": "sched", "kind": "propose_acceptance", "params": {"milestone": "m1"}, "by": "schedule"})
    assert worker._due() > 60 and json.loads((ws.home / "WORK.json").read_text())["kind"] == "propose_acceptance"


def test_checks_the_autopilot_approved_build_at_once(tmp_path, monkeypatch):
    # J11-F14: approved checks waited a whole schedule interval before their milestone was built.
    from runesmith.app import acceptance_proposals
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"build_steps": True, "auto_work": True, "policy_chosen": True})
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(acceptance_proposals, "propose", lambda *a, **k: proposal(state="proposed"))
    monkeypatch.setattr(autopilot, "review", lambda *a, **k: {"decision": "approve", "reason": "ok"})
    monkeypatch.setattr(autopilot, "act", lambda *a, **k: ("The check autopilot approved them.", "approve"))
    statuses = []
    monkeypatch.setattr(worker, "_set", lambda state, detail="": statuses.append(detail))
    worker._job_propose_acceptance("m1")
    assert [j["kind"] for j in worker._jobs] == ["build"]
    assert "the check autopilot reviews them" in statuses[0]            # J11-F13: not "(you approve them)"


def test_a_lacks_check_is_asked_as_leave_out_with_its_negation():
    # J11-G19: the second model is asked whether the file must leave the text out, paired with "must contain".
    checks = proposal(examples=[{"test": "t", "files": [], "steps": [{"run": ["node", "motion.mjs", "x.json"],
                                                                        "expect": {"exit": "ok"}}],
                                 "lacks": [{"name": "out.svg", "texts": ['class="rs-bg"']}]}])
    rows = [r for r in autopilot.questions(checks) if 'rs-bg' in r["question"]]
    assert sorted((("leave out" in r["question"]), r["expected"]) for r in rows) == [(False, "no"), (True, "yes")]


def test_every_reader_of_a_proposal_record_skips_a_malformed_row(tmp_path):
    # Review of batch E: status, propose, approve, discard, rounds_used and needs_checks still failed on such a row,
    # and needs_checks runs in the schedule, where the error ended the worker thread.
    from runesmith.app.acceptance_proposals import _record_path, discard, status
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    path = _record_path(ws, "m1")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["proposals"] = [None, "oops"] + record["proposals"]
    path.write_text(json.dumps(record), encoding="utf-8")
    assert status(ws)["m1"]["proposal"]["id"] == first["id"]
    assert autopilot.rounds_used(ws, "m1") == 0 and autopilot.needs_checks(ws) is None      # one is waiting
    discard(ws, "m1", first["id"], reason="Not these.")
    assert autopilot.needs_checks(ws) == "m1"


def test_the_schedule_survives_an_unexpected_error_in_choosing_work(tmp_path, monkeypatch):
    import threading
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"build_steps": True, "auto_work": True, "policy_chosen": True, "onboarded": True})
    worker = Worker(ws, EventBus())
    calls = []

    def broken():
        calls.append(1)
        raise AttributeError("'NoneType' object has no attribute 'get'")
    monkeypatch.setattr(worker, "scheduled_job", broken)
    waited = threading.Event()
    real_wait = worker._cv.wait

    def wait(timeout=None):
        waited.set()
        worker._closing = True
        return real_wait(timeout=0)
    monkeypatch.setattr(worker._cv, "wait", wait)
    thread = threading.Thread(target=worker._run, daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert calls and waited.is_set() and not thread.is_alive()
    assert worker.status == "blocked" and "could not choose the next step" in worker.detail
    assert "choosing scheduled work" in (ws.home / "logs" / "worker-errors.log").read_text(encoding="utf-8")


def test_a_check_that_passes_today_is_asked_whether_the_milestone_requires_it():
    # Review of batch F (J11-G18): such a check is not a gate on its own, but it is not left unexamined either.
    checks = proposal(checks=[{"test": "test_01_x", "says": "x is 50 at 1 s"},
                              {"test": "test_02_plain", "says": "Without a style the picture stays as it is.",
                               "passes_today": True}])
    rows = [r for r in autopilot.questions(checks) if r["about"] == "unchanged"]
    assert sorted(r["expected"] for r in rows) == ["no", "yes"] and all(r["test"] == "test_02_plain" for r in rows)
    assert all("stays as it is" in r["question"] for r in rows)


def test_the_decoy_is_never_the_project_s_own_vocabulary_and_answers_are_kept(tmp_path):
    # J11-G20: the decoy "rs-…" looked like this project's own ids; J11-F15: the answers were not kept.
    checks = proposal(examples=[{"test": "t", "files": [], "steps": [{"run": ["node", "motion.mjs", "x.json"],
                                                                        "expect": {"exit": "ok"}}],
                                 "contains": [{"name": "out.svg", "texts": ['id="rs-light"']}]}])
    decoy = next(r for r in autopilot.questions(checks) if r["about"] == "decoy")
    assert "rs-" not in decoy["question"] and any(w in decoy["question"] for w in autopilot.DECOY_WORDS)
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config(); config["instruments"]["verifier"]["answers"] = [answers_for(first)]; ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    autopilot.act(ws, "m1", first, verdict)
    from runesmith.app.acceptance_proposals import _proposal_rows
    kept = next(r for r in _proposal_rows(ws, "m1") if r["id"] == first["id"])["autopilot"]["cross_check"]["answers"]
    assert kept and all({"question", "expected", "answer"} <= set(r) for r in kept)


def test_a_file_check_reduced_to_the_file_existing_is_not_approved():
    reduced = proposal(dropped=["Example 1: report.txt leaves out “DEBUG”", "Example 1: report.txt: checked instead that it exists"])
    assert any("only that the file exists" in f for f in autopilot.gates(reduced))


def test_the_decoy_avoids_the_words_the_second_model_reads():
    checks = proposal()
    every = " ".join(autopilot.DECOY_WORDS)
    decoy = next(r for r in autopilot.questions(checks, context=every.replace("tuba", "")) if r["about"] == "decoy")
    assert "silent tuba" in decoy["question"]              # the one pair the context leaves free


def test_printed_output_checks_on_a_command_that_writes_a_file_wait_for_the_owner():
    # Journey J11-G24: the Embers checks read the printed output of "--svg out.svg", which prints nothing.
    printed = proposal(examples=[{"test": "t", "files": [], "steps": [
        {"run": ["node", "motion.mjs", "e.json", "--at", "2", "--svg", "out.svg"], "expect": {"shows": ["data-ember"]}}]}])
    assert any("writes out.svg" in f for f in autopilot.gates(printed))
    in_file = proposal(examples=[{"test": "t", "files": [], "steps": [
        {"run": ["node", "motion.mjs", "e.json", "--at", "2", "--svg", "out.svg"]}],
        "contains": [{"name": "out.svg", "texts": ["data-ember"]}]}])
    assert not any("writes out.svg" in f for f in autopilot.gates(in_file))


def test_a_file_line_is_asked_as_a_claim_and_its_negation():
    # Journey J11-G25: the check passes when some place has the text followed by the number (embers 0 to 8);
    # verifier of batch N2: a list question could always be parroted with a padded list.
    checks = proposal(examples=[{"test": "t", "files": [], "steps": [{"run": ["node", "motion.mjs", "x.json"],
                                                                        "expect": {"exit": "ok"}}],
                                 "file_lines": [{"name": "out.svg", "has": "data-ember", "number": 8}]}])
    rows = [r for r in autopilot.questions(checks) if "data-ember" in r["question"]]
    assert sorted(r["expected"] for r in rows) == ["no", "yes"] and len({r["pair"] for r in rows}) == 1
    claim = next(r for r in rows if r["expected"] == "yes")
    assert "followed by the number 8 somewhere" in claim["question"]


def test_the_output_gate_reads_the_joined_form_and_minus_o_only_before_a_file_name():
    assert autopilot._written(["node", "m.mjs", "--svg=out.svg"]) == "out.svg"
    assert autopilot._written(["node", "m.mjs", "-o", "fast"]) is None and autopilot._written(["node", "m.mjs", "-o", "a.txt"]) == "a.txt"


def test_full_speed_starts_the_next_step_at_once_while_models_answer(tmp_path, monkeypatch):
    # Journey J11-F21 (Lars: "go straight to next process after being done"): a failed build waited the whole
    # interval (10:14:17Z, then nothing until 10:29:39Z).
    from runesmith.app.planner import PlannerUnavailable
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"build_steps": True, "auto_work": True, "policy_chosen": True, "onboarded": True,
                        "interval_minutes": 15, "full_speed": True})
    worker = Worker(ws, EventBus())
    calls = []

    def step(milestone):
        for event in calls:
            ws.record_call(dict(event, instrument="x", role="acceptance"))
        raise PlannerUnavailable("no usable checks")
    monkeypatch.setattr(worker, "_job_propose_acceptance", step)

    def run(*events):
        calls[:] = events
        worker._execute({"id": f"s{len(events)}", "kind": "propose_acceptance", "params": {"milestone": "m1"}, "by": "schedule"})
        return worker._due()
    assert run({"ok": True}) == 0                                            # answered: straight on
    assert run({"ok": False, "error_kind": "output"}) == 0                   # answered badly: straight on, with feedback
    assert 55 < run({"ok": False, "error_kind": "transport"}) <= 60          # nobody answered: 1 minute
    assert 115 < run({"ok": False, "error_kind": "transport"}) <= 120        # again: 2 minutes
    assert 235 < run({"ok": False, "error_kind": "transport"}, {"ok": False, "error_kind": "transport"}) <= 240
    for _ in range(4):
        waited = run({"ok": False, "error_kind": "transport"})
    assert 895 < waited <= 900                                               # never longer than the interval
    assert run({"ok": True}) == 0 and json.loads((ws.home / "WORK.json").read_text())["busy_streak"] == 0
    assert 115 < run() <= 120                                                # nothing asked of a model: 2 minutes
    ws.update_settings({"full_speed": False})
    assert 895 < worker._due() <= 900                                        # off: the interval, as before
    ws.update_settings({"full_speed": True})
    (ws.home / "WORK.json").write_text(json.dumps({"utc": json.loads((ws.home / "WORK.json").read_text())["utc"],
                                                   "objects": {}}), encoding="utf-8")
    assert 895 < worker._due() <= 900                                        # a round keeps the interval
