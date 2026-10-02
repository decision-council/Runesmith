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


def test_after_a_milestone_is_done_the_next_step_asks_for_checks_first(tmp_path, monkeypatch):
    # Journey J11-F25: the build chained after a completed milestone drafted the next one before it had checks.
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"build_steps": True, "auto_work": True, "policy_chosen": True, "onboarded": True,
                        "checks_autopilot": True})
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(worker, "_job_build", lambda **params: {"advanced": True, "summary": "applied"})
    monkeypatch.setattr(autopilot, "needs_checks", lambda ws: "m1")
    worker._execute({"id": "b1", "kind": "build", "params": {}, "by": "schedule"})
    assert [(j["kind"], j["params"]) for j in worker._jobs] == [("propose_acceptance", {"milestone": "m1"})]
    worker._jobs.clear()
    monkeypatch.setattr(autopilot, "needs_checks", lambda ws: None)
    worker._execute({"id": "b2", "kind": "build", "params": {}, "by": "schedule"})
    assert [j["kind"] for j in worker._jobs] == ["build"]                  # every ready milestone has checks


def test_the_owner_withdraws_approved_checks_with_a_reason_the_next_checker_reads(tmp_path):
    # Journey J11-G37: Envelope's wrong approved checks could only be replaced, never withdrawn with a reason.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations
    from runesmith.app.workspace import WorkspaceError
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    with pytest.raises(WorkspaceError, match="no approved checks"):
        acceptance_proposals.withdraw(ws, "m1", reason="wrong")
    first = propose(ws, ws.router(), "m1")
    acceptance_proposals.approve(ws, "m1", first["id"], by="autopilot")
    target = acceptance_proposals.acceptance_file(ws, "m1")
    assert target.is_file() and expectations(ws, "m1")
    with pytest.raises(WorkspaceError, match="Say why"):
        acceptance_proposals.withdraw(ws, "m1", reason="  ")
    done = acceptance_proposals.withdraw(ws, "m1", reason="The milestone keeps the envelope inside project.")
    assert not target.is_file() and (target.parent / done["kept"]).is_file()
    assert not expectations(ws, "m1")                                      # builders are not shown their sentences
    assert acceptance_proposals._owner_reasons(ws, "m1")[0] == "The milestone keeps the envelope inside project."
    assert autopilot.needs_checks(ws) == "m1" and autopilot.rounds_used(ws, "m1") == 0
    with pytest.raises(WorkspaceError, match="no approved checks"):
        acceptance_proposals.withdraw(ws, "m1", reason="again")


def approved_workspace(tmp_path, *, by="autopilot", answers=3):
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * answers, [])
    approve(ws, "m1", propose(ws, ws.router(), "m1")["id"], by=by)
    return ws


def test_withdrawing_keeps_the_owners_own_criteria_interfaces_and_every_version(tmp_path):
    # Review of J11-G37: withdrawing deleted the owner's own criteria and interfaces with the checks' sentences, and
    # approving again restarted at version 1, overwriting history/1.json.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations, publish_expectations
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 3, [])
    interface = {"id": "api", "invocation": "tally months", "description": "", "criterion_ids": ["owner.1"],
                 "response_type": "array", "fields": [{"name": "month", "type": "string", "required": True, "nullable": False,
                                                       "unit": "", "description": ""}]}
    publish_expectations(ws, "m1", [{"id": "owner.1", "description": "The report is for one person only."}],
                         "the owner says so", interfaces=[interface])
    approve(ws, "m1", propose(ws, ws.router(), "m1")["id"])
    assert expectations(ws, "m1")["version"] == 2
    history = ws.home / "acceptance-contracts" / "history" / "m1"
    first_version = (history / "1.json").read_bytes()
    acceptance_proposals.withdraw(ws, "m1", reason="The envelope belongs inside project.")
    left = expectations(ws, "m1")
    assert [c["id"] for c in left["criteria"]] == ["owner.1"] and left["interfaces"] == [interface]
    assert left["version"] == 3 and left["reason"] == "Checks withdrawn: The envelope belongs inside project."
    assert not acceptance_file(ws, "m1").is_file()                          # the checks themselves no longer judge
    approve(ws, "m1", propose(ws, ws.router(), "m1")["id"])
    assert expectations(ws, "m1")["version"] == 4
    assert [c["id"] for c in expectations(ws, "m1")["criteria"]][0] == "owner.1"
    assert sorted(p.name for p in history.glob("*.json")) == ["1.json", "2.json", "3.json", "4.json"]
    assert (history / "1.json").read_bytes() == first_version


def test_checks_approved_again_after_a_withdrawal_never_overwrite_the_history(tmp_path):
    # Review of J11-G37: with nothing else stated nothing stays in force, and the next version still follows the last.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations
    ws = approved_workspace(tmp_path)
    history = ws.home / "acceptance-contracts" / "history" / "m1"
    first_version = (history / "1.json").read_bytes()
    acceptance_proposals.withdraw(ws, "m1", reason="wrong")
    assert expectations(ws, "m1") is None
    approve(ws, "m1", propose(ws, ws.router(), "m1")["id"])
    assert expectations(ws, "m1")["version"] == 2 and (history / "1.json").read_bytes() == first_version


def test_the_sentences_of_withdrawn_checks_reach_no_builder(tmp_path):
    # Review of J11-G37: a builder was still shown the milestone's memories of the withdrawn sentences, a draft that
    # failed them as the candidate to revise, and their feedback among the previous attempts.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations
    from runesmith.app.build_memory import recall_for_milestone, remember_check
    from runesmith.app.planner import draft_prompt, milestone_contract, source_context
    ws = approved_workspace(tmp_path)
    contract = expectations(ws, "m1")
    check = next(c for c in contract["criteria"] if c["id"].startswith("check."))
    sentence = check["description"][:40]
    milestone, context = ws.plan()["milestones"][0], source_context(ws)
    draft = ws.save_draft(title="Build 1", why="w", files=[{"path": "new.py", "content": "x = 1\n", "expected_absent": True}],
                          drafted_by="x", milestone="m1")
    verification = {"status": "failed", "utc": "2026-10-01T10:00:00Z", "snapshot_digest": context["snapshot_digest"],
                    "candidate_digest": "b" * 64, "public_acceptance_digest": contract["digest"], "public_contracts": [contract],
                    "acceptance": {"status": "failed", "ran": 3, "failures": 1, "errors": 0, "failure_details": [
                        {"test": check["id"][6:], "criteria": [check["id"]], "trace_tail": "AssertionError: x"}]}}
    ws._save_draft_state(draft, "needs_revision", contract=milestone_contract(ws, milestone), context_digest=context["digest"],
                         snapshot_digest=context["snapshot_digest"], public_acceptance_digest=contract["digest"],
                         verification=verification)
    remember_check(ws, ws._draft(draft["id"]), verification)
    seen = draft_prompt(ws, milestone, context)
    assert sentence in seen and "Resolve every listed owner-acceptance failure" in seen
    assert sentence in recall_for_milestone(ws, milestone)[0]["text"]
    acceptance_proposals.withdraw(ws, "m1", reason="these checks are wrong")
    assert recall_for_milestone(ws, milestone) == []
    unseen = draft_prompt(ws, milestone, context)
    assert sentence not in unseen and "Resolve every listed owner-acceptance failure" not in unseen
    assert '"candidate_to_revise": null' in unseen
    assert "have since been withdrawn or replaced" in unseen                  # the attempt is named, never its sentences


def test_what_the_owner_said_when_replacing_checks_survives_their_withdrawal(tmp_path):
    # Review of J11-G37: both readers took only "reason" from a withdrawn row, so the reason it was approved with
    # (replace_reason) disappeared once its checks were withdrawn.
    from runesmith.app import acceptance_proposals
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 3, [])
    approve(ws, "m1", propose(ws, ws.router(), "m1")["id"])
    approve(ws, "m1", propose(ws, ws.router(), "m1")["id"], replace=True, reason="x goes from 0 to 100, so at 1 s it is 50")
    acceptance_proposals.withdraw(ws, "m1", reason="The envelope belongs inside project.")
    assert acceptance_proposals._owner_reasons(ws, "m1") == ["The envelope belongs inside project.",
                                                             "x goes from 0 to 100, so at 1 s it is 50"]
    elsewhere = acceptance_proposals._owner_reasons_elsewhere(ws, "m2")
    assert [row["said"] for row in elsewhere] == ["The envelope belongs inside project.",
                                                  "x goes from 0 to 100, so at 1 s it is 50"]


def test_checks_withdrawn_after_a_turn_down_give_the_autopilot_its_rounds_afresh(tmp_path):
    # Review of J11-G37: a turn-down made after the approval but before the withdrawal sits behind the withdrawn row
    # in the list and still counted, though it was judged by checks the owner took back.
    from runesmith.app import acceptance_proposals
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 4, [])
    approve(ws, "m1", propose(ws, ws.router(), "m1")["id"], by="autopilot")

    def turn_down():
        row = propose(ws, ws.router(), "m1")
        acceptance_proposals.note_autopilot(ws, "m1", row["id"], {"decision": "turned_down", "reason": "x"})
        acceptance_proposals.discard(ws, "m1", row["id"], reason="Runesmith's check autopilot turned them down: x")
    turn_down()
    assert autopilot.rounds_used(ws, "m1") == 1
    acceptance_proposals.withdraw(ws, "m1", reason="wrong")
    assert autopilot.rounds_used(ws, "m1") == 0
    turn_down()
    assert autopilot.rounds_used(ws, "m1") == 1                              # only what came after the withdrawal


def test_withdrawing_waits_for_whoever_holds_the_workspace(tmp_path):
    # Review of J11-G37: withdraw took no workspace lock, so an apply that was judging a build by the checks file
    # could lose it halfway.
    import threading
    from runesmith.app import acceptance_proposals
    ws = approved_workspace(tmp_path, answers=1)
    done = []
    worker = threading.Thread(target=lambda: done.append(acceptance_proposals.withdraw(ws, "m1", reason="wrong")))
    with ws._lock:
        worker.start()
        worker.join(0.5)
        assert not done and acceptance_file(ws, "m1").is_file()
    worker.join(30)
    assert done and not acceptance_file(ws, "m1").is_file()


def test_the_server_will_not_withdraw_a_checks_file_the_owner_wrote_or_changed(tmp_path):
    # Review of J11-G37: only the studio hid the button for "owner file" checks; the endpoint withdrew anything.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations
    from runesmith.app.workspace import WorkspaceError
    ws = approved_workspace(tmp_path, answers=1)
    acceptance_file(ws, "m1").write_bytes(b"import unittest\n# the owner wrote this himself\n")
    assert status(ws)["m1"]["approved"]["provenance"] == "owner file"
    with pytest.raises(WorkspaceError, match="wrote or changed it yourself"):
        acceptance_proposals.withdraw(ws, "m1", reason="x")
    assert acceptance_file(ws, "m1").is_file() and expectations(ws, "m1")


# ---- review of the withdraw batch (J11-G37), second round ------------------------------------------------------------

OK_TEST = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"
OTHER = {"examples": [dict(e, name="other %d" % i, says="Replacement check number %d stands alone." % i)
                      for i, e in enumerate(EXAMPLES["examples"])]}


def with_project_tests(ws):
    (ws.root / "tests").mkdir()
    (ws.root / "tests" / "__init__.py").write_text("")
    (ws.root / "tests" / "test_ok.py").write_text(OK_TEST)


def answers_now(ws, answers):
    config = ws.config()
    config["instruments"]["offline"]["answers"] = list(answers)
    ws.save_config(config)


def draft_for(ws, milestone, verification=None, state="waiting"):
    from runesmith.app.acceptance_contracts import expectation_digest
    from runesmith.app.planner import milestone_contract, source_context
    from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
    snapshot = collect_snapshot(ws)
    freeze_snapshot(ws, snapshot)                   # a build is checked against the source it was drafted on
    context = source_context(ws, snapshot=snapshot)
    draft = ws.save_draft(title="Build", why="w", files=[{"path": "new.py", "content": "x = 1\n", "expected_absent": True}],
                          drafted_by="x", milestone=milestone["id"])
    ws._save_draft_state(draft, state, contract=milestone_contract(ws, milestone), context_digest=context["digest"],
                         snapshot_digest=context["snapshot_digest"], shown_files=sorted(context["files"]),
                         public_acceptance_digest=expectation_digest(ws, milestone["id"]),
                         **({"verification": verification} if verification else {}))
    return ws._draft(draft["id"]), context


def failing(ws, milestone, contract, context, check):
    return {"status": "failed", "utc": "2026-10-01T10:00:00Z", "snapshot_digest": context["snapshot_digest"],
            "candidate_digest": "b" * 64, "public_acceptance_digest": contract["digest"], "public_contracts": [contract],
            "acceptance": {"status": "failed", "ran": 3, "failures": 1, "errors": 0, "failure_details": [
                {"test": check["id"][6:], "criteria": [check["id"]], "trace_tail": "AssertionError: x"}]}}


def test_withdrawing_a_done_milestones_checks_reaches_no_later_builder(tmp_path):
    # Review of J11-G37: a done milestone's checks judge every later build, so a later milestone's failed build quotes
    # their sentences in its draft feedback, its candidate to revise and a memory keyed to the later milestone; the
    # withdrawal looked only at the done milestone's own digest and own memories.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import draft_owner_feedback, expectations
    from runesmith.app.build_memory import recall_for_milestone
    from runesmith.app.planner import draft_prompt, milestone_contract, source_context
    from runesmith.app.building import _check_and_record
    from test_acceptance_examples import MILESTONE
    second = {"examples": [dict(e, name="second %d" % i, says="Second milestone check number %d stands alone." % i)
                           for i, e in enumerate(EXAMPLES["examples"])]}
    ws = autopilot_workspace(tmp_path, [EXAMPLES, second], [])
    with_project_tests(ws)
    later = ws.add_milestone("Second step", MILESTONE, "", "Tests show correct counts.")
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    ws.update_milestone("m1", {"status": "done"})
    answers_now(ws, [second])
    approve(ws, later["id"], propose(ws, ws.router(backoff_s=()), later["id"])["id"], by="autopilot")
    sentences = [c["description"][:40] for c in expectations(ws, "m1")["criteria"] if c["id"].startswith("check.")]
    milestone = next(m for m in ws.plan()["milestones"] if m["id"] == later["id"])
    draft, _ = draft_for(ws, milestone)
    result = _check_and_record(ws, draft, milestone, milestone_contract(ws, milestone), checkpoint=lambda: None)
    assert result["verification"]["status"] == "failed"
    assert "m1" in [c["milestone"] for c in result["verification"]["public_contracts"]]
    saved = ws._draft(draft["id"])
    hit = lambda text: [s for s in sentences if s in text]
    assert hit(json.dumps(draft_owner_feedback(ws, saved))) and hit(json.dumps(recall_for_milestone(ws, milestone)))
    acceptance_proposals.withdraw(ws, "m1", reason="The next milestone changes what these checks required.")
    assert not hit(json.dumps(draft_owner_feedback(ws, saved)))
    assert recall_for_milestone(ws, milestone) == []
    prompt = draft_prompt(ws, milestone, source_context(ws))
    assert not hit(prompt) and not hit(draft_prompt(ws, milestone, source_context(ws), revision=saved))


def test_a_build_checked_while_the_owner_withdraws_leaves_no_memory_of_the_sentences(tmp_path):
    # Review of J11-G37: the check finished against the bytes it had read and remembered the withdrawn sentences after
    # the withdrawal had retired the milestone's memories.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations
    from runesmith.app.build_memory import recall_for_milestone
    from runesmith.app.building import _check_and_record
    from runesmith.app.planner import draft_prompt, milestone_contract, source_context
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    with_project_tests(ws)
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    sentences = [c["description"][:40] for c in expectations(ws, "m1")["criteria"] if c["id"].startswith("check.")]
    milestone = ws.plan()["milestones"][0]
    draft, _ = draft_for(ws, milestone)
    calls = []

    def checkpoint():
        calls.append(1)
        if len(calls) == 3:         # between "project checks" and "owner acceptance": the owner withdraws now
            acceptance_proposals.withdraw(ws, "m1", reason="These checks are wrong.")
    result = _check_and_record(ws, draft, milestone, milestone_contract(ws, milestone), checkpoint=checkpoint)
    assert result["verification"]["status"] == "failed" and not acceptance_file(ws, "m1").is_file()
    hit = lambda text: [s for s in sentences if s in text]
    assert not hit(json.dumps(recall_for_milestone(ws, milestone), ensure_ascii=False))
    assert not hit(draft_prompt(ws, milestone, source_context(ws)))


def test_the_autopilots_rounds_start_afresh_although_the_record_keeps_only_ten_rows(tmp_path):
    # Review of J11-G37: the boundary was a position in the list, which moves when the record trims to its last ten
    # rows: rounds stayed 0 for three turn-downs, then jumped to ten when the withdrawn row rolled out.
    from runesmith.app import acceptance_proposals
    from runesmith.app.workspace import _read_json, _write_json
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 3, [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    path = acceptance_proposals._record_path(ws, "m1")
    record = _read_json(path, {})
    for n in range(8):               # eight turn-downs made while the checks stood: nine rows, one short of the window
        record["proposals"].append({"id": f"x{n}", "state": "discarded", "milestone": "m1", "utc": "2026-10-01T00:00:00Z",
                                    "autopilot": {"decision": "turned_down"}, "checks": [], "code": "", "dry_run": {}})
    _write_json(path, record)
    assert len(acceptance_proposals._proposal_rows(ws, "m1")) == 9
    acceptance_proposals.withdraw(ws, "m1", reason="wrong")
    assert autopilot.rounds_used(ws, "m1") == 0

    def turn_down():
        row = propose(ws, ws.router(backoff_s=()), "m1")
        acceptance_proposals.note_autopilot(ws, "m1", row["id"], {"decision": "turned_down", "reason": "x"})
        acceptance_proposals.discard(ws, "m1", row["id"], reason="turned down")
    turn_down()
    assert autopilot.rounds_used(ws, "m1") == 1
    turn_down()
    assert len(acceptance_proposals._proposal_rows(ws, "m1")) == 11          # the window's ten and the newest withdrawal
    assert autopilot.rounds_used(ws, "m1") == autopilot.MAX_ROUNDS == 2 and autopilot.needs_checks(ws) is None


def test_a_supplement_after_a_withdrawal_is_not_told_to_resolve_the_withdrawn_sentences(tmp_path):
    # Review of J11-G37: the explicit revision's candidate carried its feedback through an ungated reader, so the call
    # the owner authorizes after a clarification was told to satisfy sentences he took back.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations, publish_expectations
    from runesmith.app.building import supplement_status
    from runesmith.app.planner import draft_prompt, source_context
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    publish_expectations(ws, "m1", [{"id": "owner.1", "description": "The report is for one person only."}], "the owner says so")
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    contract = expectations(ws, "m1")
    check = next(c for c in contract["criteria"] if c["id"].startswith("check."))
    milestone, context = ws.plan()["milestones"][0], source_context(ws)
    draft, _ = draft_for(ws, milestone)
    ws._save_draft_state(draft, "needs_revision", verification=failing(ws, milestone, contract, context, check))
    saved = ws._draft(draft["id"])
    assert check["description"][:40] in draft_prompt(ws, milestone, source_context(ws), revision=saved)
    acceptance_proposals.withdraw(ws, "m1", reason="These checks are wrong.")
    assert supplement_status(ws, saved)["eligible"]
    asked = draft_prompt(ws, milestone, source_context(ws), revision=saved)
    assert check["description"][:40] not in asked


def test_the_withdrawal_reason_is_read_before_three_later_turn_downs(tmp_path):
    # Review of J11-G37: _owner_reasons walked the rows by position; the withdrawn row sits where its checks were
    # proposed, behind every proposal made while they stood, so three reasoned turn-downs crowded its reason out.
    from runesmith.app import acceptance_proposals
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 4, [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    for n in (1, 2, 3):
        acceptance_proposals.discard(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], reason=f"discard reason {n}")
    acceptance_proposals.withdraw(ws, "m1", reason="WITHDRAWAL REASON: the envelope belongs inside project.")
    assert acceptance_proposals._owner_reasons(ws, "m1")[0].startswith("WITHDRAWAL REASON")
    assert any(s.startswith("WITHDRAWAL REASON") for s in acceptance_proposals.packet(ws, "m1", "examples")["owner_said_about_earlier_checks"])


def test_approved_checks_stay_withdrawable_after_ten_more_proposals(tmp_path):
    # Review of J11-G37: the record keeps ten rows, so the approved checks' row rolled out after nine more proposals,
    # Withdraw refused, and the Studio called the file "your own".
    from runesmith.app import acceptance_proposals
    from runesmith.app.workspace import _read_json, _write_json
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 2, [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"])
    path = acceptance_proposals._record_path(ws, "m1")
    record = _read_json(path, {})
    for n in range(9):
        record["proposals"].append({"id": f"x{n}", "state": "discarded", "milestone": "m1", "utc": "2026-10-01T00:00:00Z",
                                    "reason": f"no {n}", "checks": [], "code": "", "dry_run": {}})
    _write_json(path, record)
    propose(ws, ws.router(backoff_s=()), "m1")
    rows = acceptance_proposals._proposal_rows(ws, "m1")
    assert len(rows) == 11 and [r["state"] for r in rows].count("approved") == 1          # ten, and the checks in force
    assert status(ws)["m1"]["approved"]["provenance"] == "model-proposed, owner-approved"
    acceptance_proposals.withdraw(ws, "m1", reason="wrong")
    assert not acceptance_file(ws, "m1").is_file()


def test_replacing_checks_that_an_interface_links_to_leaves_nothing_half_done(tmp_path):
    # Review of J11-G37: the new file was written, then publishing refused the interface linked to a replaced sentence;
    # the checks and their public sentences disagreed, and neither approving nor withdrawing worked.
    from runesmith.app import acceptance_proposals
    from runesmith.app.acceptance_contracts import expectations, publish_expectations
    ws = autopilot_workspace(tmp_path, [EXAMPLES, OTHER], [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"])
    contract = expectations(ws, "m1")
    check_id = next(c["id"] for c in contract["criteria"] if c["id"].startswith("check."))
    interface = {"id": "api", "invocation": "tally months", "description": "", "criterion_ids": [check_id], "response_type": "array",
                 "fields": [{"name": "month", "type": "string", "required": True, "nullable": False, "unit": "", "description": ""}]}
    publish_expectations(ws, "m1", contract["criteria"], "link an interface to a sentence", interfaces=[interface],
                         expected_digest=contract["digest"])
    answers_now(ws, [OTHER])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], replace=True, reason="better")
    assert [c["id"] for c in expectations(ws, "m1")["criteria"]][0].startswith("check.test_01_other")
    assert expectations(ws, "m1")["interfaces"] == []                     # nothing left to link to, so it goes
    assert status(ws)["m1"]["approved"]["provenance"] == "model-proposed, owner-approved"
    acceptance_proposals.withdraw(ws, "m1", reason="wrong")


def test_replacing_checks_retires_the_memories_of_their_sentences(tmp_path):
    # Review of J11-G37: only a withdrawal retired the milestone's memories, so builders kept seeing replaced sentences.
    from runesmith.app.acceptance_contracts import expectations
    from runesmith.app.build_memory import recall_for_milestone, remember_check
    from runesmith.app.planner import source_context
    ws = autopilot_workspace(tmp_path, [EXAMPLES, OTHER], [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"])
    contract = expectations(ws, "m1")
    check = next(c for c in contract["criteria"] if c["id"].startswith("check."))
    milestone = ws.plan()["milestones"][0]
    draft, context = draft_for(ws, milestone)
    remember_check(ws, draft, failing(ws, milestone, contract, context, check))
    assert check["description"][:40] in json.dumps(recall_for_milestone(ws, milestone))
    answers_now(ws, [OTHER])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], replace=True, reason="the first checks were wrong")
    assert recall_for_milestone(ws, milestone) == []


def test_a_request_written_before_a_withdrawal_is_not_stored_as_if_it_read_the_reason(tmp_path):
    # Review of J11-G37: the Checker's answer to a request composed before the withdrawal was stored as a waiting
    # proposal, and the autopilot then approved checks the owner had just withdrawn, which never read his reason.
    from runesmith.app import acceptance_proposals
    from runesmith.app.workspace import WorkspaceError
    ws = autopilot_workspace(tmp_path, [EXAMPLES, EXAMPLES], [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    fired = []

    def checkpoint():
        if not fired:
            fired.append(1)
            acceptance_proposals.withdraw(ws, "m1", reason="WITHDRAWAL REASON: the envelope belongs inside project.")
    with pytest.raises(WorkspaceError, match="never read your reason"):
        propose(ws, ws.router(backoff_s=()), "m1", checkpoint=checkpoint)
    assert status(ws).get("m1") is None and autopilot.needs_checks(ws) == "m1"
    router = ws.router(backoff_s=())
    propose(ws, router, "m1")
    assert "WITHDRAWAL REASON" in router.instruments["offline"].requests[0]["prompt"]


# ---- review of the withdraw batch (J11-G37), verification round --------------------------------------------------------

def test_a_proposal_waiting_when_the_owner_withdraws_is_never_approved(tmp_path):
    # Review of J11-G37: a proposal stored before the withdrawal stayed waiting, and the autopilot, finishing its
    # cross-check afterwards, approved it: the owner's withdrawal was undone and the checks never read his reason.
    from runesmith.app import acceptance_proposals
    from runesmith.app.workspace import WorkspaceError
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 2, [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    waiting = propose(ws, ws.router(backoff_s=()), "m1")
    assert status(ws)["m1"]["proposal"]["id"] == waiting["id"]
    acceptance_proposals.withdraw(ws, "m1", reason="WITHDRAWAL REASON: the envelope belongs inside project.")
    assert status(ws).get("m1") is None                                   # nothing waits, nothing is in force
    row = next(r for r in acceptance_proposals._proposal_rows(ws, "m1") if r["id"] == waiting["id"])
    assert row["state"] == "stale" and "never read" in row["stale_note"]
    said, done = autopilot.act(ws, "m1", waiting, {"decision": "approve", "reason": "worked out the same"})
    assert done == "none" and "decided about these checks meanwhile" in said and not acceptance_file(ws, "m1").is_file()
    with pytest.raises(WorkspaceError, match="not waiting for approval"):
        approve(ws, "m1", waiting["id"], by="autopilot")
    assert autopilot.needs_checks(ws) == "m1"                             # asked again, with the reason
    # a waiting row stamped by a withdrawal is refused whoever asks, also when its state says otherwise
    record = acceptance_proposals._record(ws, "m1")
    next(r for r in record["proposals"] if r["id"] == waiting["id"]).update(state="proposed")
    acceptance_proposals._write_json(acceptance_proposals._record_path(ws, "m1"), record)
    with pytest.raises(WorkspaceError, match="never read the reason"):
        approve(ws, "m1", waiting["id"], by="autopilot")


def test_the_newest_withdrawal_stays_in_the_record_until_checks_are_approved_after_it(tmp_path):
    # Review of J11-G37: the first proposal after a withdrawal trimmed its row out of the ten-row window, and the
    # reason went with it: only that first request ever read why the checks were withdrawn.
    from runesmith.app import acceptance_proposals
    from runesmith.app.workspace import _read_json, _write_json
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 4, [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"])
    path = acceptance_proposals._record_path(ws, "m1")
    record = _read_json(path, {})
    for n in range(9):
        record["proposals"].append({"id": f"x{n}", "state": "discarded", "milestone": "m1", "utc": "2026-10-01T00:00:00Z",
                                    "checks": [], "code": "", "dry_run": {}})
    _write_json(path, record)
    acceptance_proposals.withdraw(ws, "m1", reason="WITHDRAWAL REASON: the envelope belongs inside project.")
    for _ in range(3):
        acceptance_proposals.discard(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], reason="not these either")
    assert [r["state"] for r in acceptance_proposals._proposal_rows(ws, "m1")].count("withdrawn") == 1
    assert "WITHDRAWAL REASON" in " ".join(acceptance_proposals.packet(ws, "m1", "examples")["owner_said_about_earlier_checks"])
    # checks approved after it let it go: its row is trimmed like any other
    rows = [{"state": "withdrawn"}] + [{"state": "discarded"} for _ in range(5)] + [{"state": "approved"}] + [{"state": "discarded"}] * 6
    assert acceptance_proposals._kept_beyond_window(rows) == set()               # the old withdrawal goes: checks were approved after it
    rows = [{"state": "withdrawn"}] + [{"state": "discarded"} for _ in range(12)]
    assert acceptance_proposals._kept_beyond_window(rows) == {id(rows[0])}


def test_replacing_checks_says_which_interface_links_it_removed(tmp_path):
    # Review of J11-G37: a replacement drops the owner's links to replaced sentences, and an interface left with none;
    # neither the result nor the ledger said so, also when the autopilot replaced them.
    from runesmith.app.acceptance_contracts import expectations, publish_expectations
    ws = autopilot_workspace(tmp_path, [EXAMPLES, OTHER], [])
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"])
    contract = expectations(ws, "m1")
    check_id = next(c["id"] for c in contract["criteria"] if c["id"].startswith("check."))
    field = {"name": "month", "type": "string", "required": True, "nullable": False, "unit": "", "description": ""}
    both = {"id": "both", "invocation": "tally months", "description": "", "criterion_ids": ["owner.1", check_id],
            "response_type": "array", "fields": [field]}
    only = dict(both, id="only", criterion_ids=[check_id])
    publish_expectations(ws, "m1", [*contract["criteria"], {"id": "owner.1", "description": "One person only."}],
                         "link interfaces", interfaces=[both, only], expected_digest=contract["digest"])
    answers_now(ws, [OTHER])
    result = approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], replace=True, reason="better")
    assert result["interface_links_removed"] == [{"interface": "both", "removed": [check_id], "dropped": False},
                                                 {"interface": "only", "removed": [check_id], "dropped": True}]
    assert [row["id"] for row in expectations(ws, "m1")["interfaces"]] == ["both"]
    logged = [r["data"] for r in ws.ledger if r["kind"] == "acceptance.approved"][-1]
    assert logged["interface_links_removed"] == result["interface_links_removed"]


def test_a_build_checked_while_the_owner_withdraws_is_remembered_without_a_phantom_failure(tmp_path):
    # Review of J11-G37: the memory kept the outcome with its sentences stripped, which read as failures that "need the
    # owner's clarification" for checks the owner had already withdrawn.
    from runesmith.app import acceptance_proposals
    from runesmith.app.build_memory import recall_for_milestone
    from runesmith.app.building import _check_and_record
    from runesmith.app.planner import milestone_contract
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    with_project_tests(ws)
    approve(ws, "m1", propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    milestone = ws.plan()["milestones"][0]
    draft, _ = draft_for(ws, milestone)
    calls = []

    def checkpoint():
        calls.append(1)
        if len(calls) == 3:
            acceptance_proposals.withdraw(ws, "m1", reason="These checks are wrong.")
    _check_and_record(ws, draft, milestone, milestone_contract(ws, milestone), checkpoint=checkpoint)
    remembered = json.dumps(recall_for_milestone(ws, milestone), ensure_ascii=False)
    assert "Observed outcome: failed" in remembered
    assert "Owner clarification needed" not in remembered and "have since been withdrawn or replaced" in remembered


def test_withdrawing_reads_the_receipts_of_older_memories_once_and_outside_the_lock(tmp_path):
    # Review of J11-G37: every legacy memory's receipt was read under the workspace lock on each withdrawal or
    # replacement: 64 s on J11's 131 memories, the lock held throughout and nothing kept.
    from runesmith import memory as memory_module
    from runesmith.app import acceptance_proposals, build_memory
    from runesmith.app.workspace import _write_json
    ws = approved_workspace(tmp_path, answers=1)
    store = memory_module.Memory(ws.home / "memory.jsonl")

    def legacy(name, milestone, quoting):
        evidence = f"build-evidence/{name}"
        _write_json(ws.home / evidence / "VERIFICATION.json", {
            "public_contracts": [{"milestone": quoting, "digest": "d", "criteria": [{"id": "check.test_a"}]}],
            "acceptance": {"failure_details": [{"criteria": ["check.test_a"]}]}})
        return store.add("negative", f"Build check {name}", tags=["build_check"], source={
            "kind": "build_check", "milestone": milestone, "evidence_dir": evidence, "draft": name})
    own, later, other = legacy("own", "m1", "m1"), legacy("later", "m2", "m1"), legacy("other", "m2", "m3")
    reads = []
    real = build_memory._read_json

    def watched(path, default):
        if str(path).endswith("VERIFICATION.json"):
            reads.append((path.parent.name, ws._lock._is_owned()))
        return real(path, default)
    build_memory._read_json = watched
    try:
        acceptance_proposals.withdraw(ws, "m1", reason="wrong")
        assert sorted(name for name, _ in reads) == ["later", "other"]       # its own milestone's needs no receipt
        assert not any(held for _, held in reads)                            # none read under the lock
        active = {row["id"] for row in store.active(source_kind=build_memory.SOURCE_KIND)}
        assert active == {other}                                             # own and the one quoting m1 are retired
        reads.clear()
        build_memory.retire_for_milestone(ws, "m3", "again")
        assert reads == [] and (ws.home / build_memory.QUOTED_INDEX).is_file()      # kept: nothing read twice
        assert {row["id"] for row in store.active(source_kind=build_memory.SOURCE_KIND)} == set()
    finally:
        build_memory._read_json = real
