"""Layer 0 of the out-of-box coverage plan: every switch combination against the rules that must always hold.

The owner's switches (autonomy, scheduled work, checks, automatic apply, test runs while mapping, self-improvement,
notes) and the work modes (not configured, or each of Map & Plan, Build, Troubleshoot, Optimize and Operations on or
off, with purpose inference on or off), with and without an explicit direction: 16,640 combinations. For each, every
job kind is asked whether it may start, and the answer is compared with an independent statement of the rules. The
rules that need real work (checks run, files written, models asked) get their own exhaustive tests over the switches
that govern them. See docs/JOURNEY_COVERAGE_PLAN.md, section 3 (rules I1-I10).
"""
import itertools

import pytest

from runesmith.app import building, work_modes
from runesmith.app.acceptance_proposals import dry_run
from runesmith.app.planner import plan_prompt
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import DEFAULT_SETTINGS, Workspace, WorkspaceError
from test_build_steps import setup
from test_studio import scripted

SWITCHES = ("auto_work", "build_steps", "build_apply", "probe_tests", "kaizen", "read_notes")
MODES = ("map_plan", "build", "troubleshoot", "optimize", "operations")
BUILD_KINDS = {"build", "draft", "escalate", "supplement", "revise", "correct", "breakdown", "propose_acceptance",
               "review_current", "resume_check", "allocate_check", "reconcile_check"}
KINDS = ("map", "round", "plan", "goalposts", "draft", "build", "escalate", "supplement", "revise", "correct",
         "breakdown", "propose_acceptance", "review_current", "resume_check", "resume_author", "source_baseline",
         "allocate_check", "reconcile_check", "health", "mode", "measure")


def combinations():
    for autonomy in ("observe", "propose"):
        for values in itertools.product((False, True), repeat=len(SWITCHES)):
            for configured in (False, True):
                for modes in (itertools.product((False, True), repeat=len(MODES)) if configured else [None]):
                    for infer in ((False, True) if configured else (True,)):
                        for brief in (False, True):
                            yield autonomy, dict(zip(SWITCHES, values, strict=True)), modes, infer, brief


def expected_refusal(kind, autonomy, modes, infer, brief):
    """The rules, stated independently of the code: may this job kind start?"""
    enabled = dict(zip(MODES, modes, strict=True)) if modes is not None else {"map_plan": True, "build": True, "troubleshoot": True}
    if kind in {"plan", "goalposts"}:
        return (not enabled["map_plan"]) or autonomy == "observe" or (not infer and not brief)
    if modes is None:
        return False
    if kind in BUILD_KINDS:
        return not enabled["build"]
    if kind == "round":
        return not enabled["troubleshoot"]
    return False


def test_every_switch_and_mode_combination_starts_exactly_the_work_the_rules_allow(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    state = {}
    monkeypatch.setattr(Workspace, "settings", lambda self: dict(state["settings"]))
    monkeypatch.setattr(work_modes, "configuration", lambda ws: state["config"])
    monkeypatch.setattr(work_modes, "planning_direction", lambda ws: {"brief": "A reading log." if state["brief"] else "",
                                                                    "goals": [], "blueprints": "", "explicit": state["brief"]})
    checked = mismatches = 0
    examples = []
    for autonomy, switches, modes, infer, brief in combinations():
        state["settings"] = dict(DEFAULT_SETTINGS, **switches, autonomy=autonomy, onboarded=True, interval_minutes=5)
        rows = [{"id": m, "executor": m, "enabled": bool(modes[i]) if modes is not None else m in {"map_plan", "build", "troubleshoot"}}
                for i, m in enumerate(MODES)]
        state["config"] = {"configured": modes is not None, "modes": rows, "infer_purpose": infer, "revision": "r"}
        state["brief"] = brief
        for kind in KINDS:
            try:
                work_modes.guard_job(ws, kind)
                refused = False
            except WorkspaceError as error:
                refused = True
                assert str(error).strip(), "a refusal must say why"            # I9: every refusal is explained
            checked += 1
            if refused != expected_refusal(kind, autonomy, modes, infer, brief):
                mismatches += 1
                if len(examples) < 5:
                    examples.append((kind, autonomy, switches, modes, infer, brief, refused))
    assert checked == 16_640 * len(KINDS)
    assert mismatches == 0, examples


def test_observe_mode_asks_no_model_whatever_the_job(tmp_path):
    # I1: every Studio model call passes through Workspace.router(); in observe mode it refuses, in plain words.
    ws = Workspace(tmp_path)
    scripted(ws, [{"answer": 1}] * 4, roles=("plan", "repair", "kaizen", "acceptance"))
    for role in ("plan", "repair", "kaizen", "acceptance"):
        assert ws.router().call(role, prompt="p", system="s", schema=None, max_tokens=10, key="k-" + role).ok
    ws.update_settings({"autonomy": "observe"})
    for role in ("plan", "repair", "kaizen", "acceptance"):
        with pytest.raises(WorkspaceError, match="Observe mode"):
            ws.router().call(role, prompt="p", system="s", schema=None, max_tokens=10, key="o-" + role)


@pytest.mark.parametrize("auto_work,onboarded,paused", list(itertools.product((False, True), repeat=3)))
def test_nothing_is_scheduled_unless_the_owner_turned_scheduled_work_on(tmp_path, auto_work, onboarded, paused):
    # I5: a round is scheduled only with scheduled work on, a finished introduction and no pause.
    ws = Workspace(tmp_path)
    ws.update_settings({"auto_work": auto_work, "onboarded": onboarded})
    worker = Worker(ws, EventBus())
    worker.paused = paused
    assert (worker._next_round_utc(ws.settings()) is not None) == (auto_work and onboarded and not paused)


@pytest.mark.parametrize("autonomy,build_steps", list(itertools.product(("observe", "propose"), (False, True))))
def test_proposed_checks_are_tried_only_when_checks_may_run(tmp_path, monkeypatch, autonomy, build_steps):
    # I2: with checks off, or in observe mode, no project code runs, not even a trial of proposed checks.
    ws = Workspace(tmp_path)
    ws.update_settings({"autonomy": autonomy, "build_steps": build_steps})
    ran = []
    monkeypatch.setattr("runesmith.app.acceptance_proposals._run_checks", lambda *a, **k: ran.append(1) or {"ok": True, "status": "passed", "ran": 1})
    verdict = dry_run(ws, "import unittest\n")["verdict"]
    assert (verdict != "not_run") == (autonomy == "propose" and build_steps) and bool(ran) == (verdict != "not_run")


@pytest.mark.parametrize("autonomy,build_steps,build_apply,acceptance",
                         list(itertools.product(("observe", "propose"), (False, True), (False, True), (False, True))))
def test_project_files_change_only_with_checks_apply_and_owner_acceptance(tmp_path, monkeypatch, autonomy, build_steps,
                                                                          build_apply, acceptance):
    # I1, I2, I4 on a real build: observe asks no model; checks off runs no project code; files change only when
    # checks and automatic apply are on and the owner's acceptance checks pass.
    ws = setup(tmp_path, acceptance=acceptance)
    ws.update_settings({"build_steps": build_steps, "build_apply": build_apply, "build_paths": ["app.py", "tests"],
                        "autonomy": autonomy})
    ran = []
    real_run = building._run_checks
    monkeypatch.setattr(building, "_run_checks", lambda *a, **k: ran.append(1) or real_run(*a, **k))
    result = building.build_step(ws, ws.router())
    wrote = (tmp_path / "app.py").exists()
    assert wrote == (autonomy == "propose" and build_steps and build_apply and acceptance), result["summary"]
    assert bool(ran) <= (autonomy == "propose" and build_steps)
    if autonomy == "observe":
        assert "Observe mode" in result["summary"] and not ws.drafts()
    if autonomy == "propose" and not build_steps:
        assert "Check drafts by running their tests" in result["summary"]          # I9: it names the switch


@pytest.mark.parametrize("read_notes", (False, True))
def test_notes_reach_the_model_only_when_the_owner_allows_it(tmp_path, read_notes):
    # I8
    ws = Workspace(tmp_path)
    ws.add_note("workspace", "root", "Please keep the unusual word quokka in mind.")
    ws.update_settings({"read_notes": read_notes})
    assert ("quokka" in plan_prompt(ws)) == read_notes
