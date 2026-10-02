"""A project that runs to the end of its plan without its owner (batch EE; journeys J11-G41, G42, G43).

Each choice is the owner's, off by default: what to do after an interrupted job, and when a milestone's tries are used
up. Everything Runesmith decides by them is said as "Runesmith (your setting)", on the Overview and in the ledger.
"""
import json
import threading
import uuid

import pytest

from runesmith.app import automatic, stuck
from runesmith.app.author_allowance import ordinary_allowance
from runesmith.app.planner import milestone_contract, source_context
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import Workspace, WorkspaceError, _read_json, _write_json


# ---- the two settings ------------------------------------------------------------------------------------------------

def test_both_settings_wait_for_the_owner_by_default_and_refuse_other_words(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.settings()["recovery_policy"] == "wait" and ws.settings()["stuck_policy"] == "wait"
    ws.update_settings({"recovery_policy": "keep", "stuck_policy": "retry_split"})
    assert ws.settings()["recovery_policy"] == "keep" and ws.settings()["stuck_policy"] == "retry_split"
    for key, word in (("recovery_policy", "always"), ("stuck_policy", "forever")):
        with pytest.raises(WorkspaceError, match="must be one of"):
            ws.update_settings({key: word})
    assert ws.settings()["stuck_policy"] == "retry_split"                    # a refused change changes nothing


def test_automatic_decisions_are_kept_newest_first_and_bounded(tmp_path):
    ws = Workspace(tmp_path)
    for n in range(automatic.KEPT + 5):
        automatic.record(ws, f"decision {n}", kind="recovery")
    rows = automatic.recent(ws, 3)
    assert [r["what"] for r in rows] == [f"decision {n}" for n in (automatic.KEPT + 4, automatic.KEPT + 3, automatic.KEPT + 2)]
    assert len(_read_json(ws.home / automatic.FILE, [])) == automatic.KEPT and rows[0]["by"] == "Runesmith (your setting)"


# ---- EE1 (J11-G41): prerequisites ------------------------------------------------------------------------------------

def test_naming_prerequisites_does_not_change_what_a_milestone_builds(tmp_path):
    # What to build is unchanged when only the order changes, so the milestone's contract (which budgets, checks and
    # drafts are bound to) must not move: milestone_contract hashes depends_on only for a breakdown's steps.
    ws = Workspace(tmp_path)
    first, second = ws.add_milestone("First"), ws.add_milestone("Second")
    before = milestone_contract(ws, next(m for m in ws.plan()["milestones"] if m["id"] == second["id"]))
    ws.update_milestone(second["id"], {"depends_on": [first["id"]]})
    after = next(m for m in ws.plan()["milestones"] if m["id"] == second["id"])
    assert after["depends_on"] == [first["id"]] and milestone_contract(ws, after) == before


def test_the_schedule_neither_builds_nor_asks_checks_for_a_milestone_whose_prerequisites_are_open(tmp_path):
    ws = Workspace(tmp_path)
    ws.update_settings({"build_steps": True, "checks_autopilot": True, "autonomy": "propose"})
    first = ws.add_milestone("First", "does a", "", "a works")
    second = ws.add_milestone("Second", "does b", "", "b works", depends_on=[first["id"]])
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("propose_acceptance", {"milestone": first["id"]})
    (ws.home / "acceptance").mkdir(exist_ok=True)
    (ws.home / "acceptance" / (first["id"] + ".py")).write_text("# approved\n")
    assert worker.scheduled_job() == ("build", {})                       # not "propose_acceptance" for the second
    ws.update_milestone(first["id"], {"status": "done"})
    assert worker.scheduled_job() == ("propose_acceptance", {"milestone": second["id"]})


# ---- EE2 (J11-G42): after an interrupted job --------------------------------------------------------------------------

def interrupted(tmp_path, **settings):
    root = tmp_path / "project"
    root.mkdir()
    ws = Workspace(root)
    ws.update_settings({"auto_work": False, "kaizen": False, **settings})
    original = Worker(ws, EventBus())
    claimed = original.enqueue("health")
    waiting = original.enqueue("map", probe=False)
    _write_json(ws.home / "STUDIO_CURRENT.json", dict(claimed, started="2026-10-02T03:00:00Z"))
    return ws, claimed, waiting


def test_a_restart_after_an_interrupted_job_waits_for_the_owner_unless_he_chose_otherwise(tmp_path):
    ws, claimed, waiting = interrupted(tmp_path)
    worker = Worker(ws, EventBus())
    worker._recover()
    assert worker.paused and worker.snapshot()["recovery"]["required"] and worker.snapshot()["queue"] == [waiting]
    assert automatic.recent(ws) == []                                    # nothing was decided for him


def test_with_the_setting_a_restart_keeps_the_queue_continues_and_says_who_decided(tmp_path, monkeypatch):
    ws, claimed, waiting = interrupted(tmp_path, recovery_policy="keep")
    worker = Worker(ws, EventBus())
    worker._recover()
    state = worker.snapshot()
    assert state["recovery"] is None and not state["paused"] and state["queue"] == [waiting]
    assert worker.history[-1]["id"] == claimed["id"] and worker.history[-1]["result"] == "interrupted"
    revision = next((ws.home / "studio-recovery").glob("*.json"))
    receipt = json.loads(revision.read_text())
    assert receipt["decision"] == "keep" and receipt["reviewed_by"] == "Runesmith (your setting)"
    assert _read_json(ws.home / "STUDIO_STATE.json", {})["paused"] is False
    [row] = automatic.recent(ws)
    assert row["kind"] == "recovery" and row["by"] == "Runesmith (your setting)" and "interrupted job" in row["what"]
    assert "was not run again" in row["what"] and "kept the waiting work (1 job)" in row["what"]
    assert any(r["kind"] == "automatic.decision" and r["data"]["kind"] == "recovery" for r in ws.ledger)
    ran, done = [], threading.Event()
    monkeypatch.setattr(worker, "_job_health", lambda: ran.append("health") or {})
    monkeypatch.setattr(worker, "_job_map", lambda probe=None: (ran.append("map"), done.set(), {})[2])
    worker.start()
    try:
        assert done.wait(5)
    finally:
        worker.close(); worker._thread.join(3); worker._watch.join(3)
    assert ran == ["map"]                                                # the interrupted job itself was never replayed


def test_unreadable_control_records_still_wait_for_the_owner_with_the_setting_on(tmp_path):
    ws, claimed, waiting = interrupted(tmp_path, recovery_policy="keep")
    (ws.home / "STUDIO_QUEUE.json").write_text("{damaged", encoding="utf-8")
    worker = Worker(ws, EventBus())
    worker._recover()
    state = worker.snapshot()
    assert worker.paused and state["recovery"]["required"] and state["recovery"]["blocked"]
    assert not list((ws.home / "studio-recovery").glob("*.json")) and automatic.recent(ws) == []


def test_a_write_recovery_conflict_still_waits_for_the_owner_with_the_setting_on(tmp_path, monkeypatch):
    ws, claimed, waiting = interrupted(tmp_path, recovery_policy="keep")
    monkeypatch.setattr(ws, "recover_writes", lambda: [{"key": "app.py", "state": "conflict"}])
    worker = Worker(ws, EventBus())
    worker._recover()
    assert worker.paused and worker.snapshot()["recovery"]["required"] and automatic.recent(ws) == []


def test_a_pause_the_owner_chose_is_kept_by_the_setting(tmp_path):
    ws, claimed, waiting = interrupted(tmp_path, recovery_policy="keep")
    _write_json(ws.home / "STUDIO_STATE.json", {"paused": True})        # the owner paused before the interruption
    worker = Worker(ws, EventBus())
    worker._recover()
    assert worker.snapshot()["recovery"] is None and worker.paused       # reviewed, but his pause is still his
    [row] = automatic.recent(ws)
    assert "left the pause you set" in row["what"] and row["resumed"] is False


# ---- EE3 (J11-G43): a milestone whose tries are used up --------------------------------------------------------------

def stuck_project(tmp_path, **settings):
    from test_breakdowns import setup
    ws = setup(tmp_path)
    ws.update_settings({"build_steps": True, "autonomy": "propose", "auto_work": True, **settings})
    return ws


def used_up(ws, milestone_id, *, escalation=None):
    """Three tries used on today's source, and (when given) the one more try in this state."""
    milestone = next(m for m in ws.plan()["milestones"] if m["id"] == milestone_id)
    contract, snapshot = milestone_contract(ws, milestone), source_context(ws)["snapshot_digest"]
    scope = ordinary_allowance(ws, contract, snapshot)["scope"]
    for n in range(3):
        _write_json(ws.home / "build-attempts" / (uuid.uuid4().hex + ".json"), {
            "scope": scope, "contract": contract, "context_digest": "c" * 64, "snapshot_digest": snapshot,
            "state": "failed", "utc": f"2026-10-02T03:0{n}:00Z", "error": "x"})
    if escalation:
        one_more_try(ws, milestone_id, escalation)


def one_more_try(ws, milestone_id, state="failed"):
    milestone = next(m for m in ws.plan()["milestones"] if m["id"] == milestone_id)
    contract, snapshot = milestone_contract(ws, milestone), source_context(ws)["snapshot_digest"]
    _write_json(ws.home / "build-escalations" / "e1.json", {
        "id": "e1", "state": state, "contract": contract, "scope": ordinary_allowance(ws, contract, snapshot)["scope"],
        "snapshot_digest": snapshot, "milestone": milestone_id, "utc": "2026-10-02T03:10:00Z"})


def test_the_default_waits_for_the_owner_when_a_milestones_tries_are_used_up(tmp_path):
    ws = stuck_project(tmp_path)
    used_up(ws, "m2")
    assert stuck.stuck_work(ws, "wait") is None
    assert Worker(ws, EventBus()).scheduled_job() == ("build", {})


def test_one_more_try_is_scheduled_once_per_milestone_and_source(tmp_path):
    ws = stuck_project(tmp_path, stuck_policy="retry")
    worker = Worker(ws, EventBus())
    used_up(ws, "m2")
    assert [r["milestone"]["id"] for r in stuck.stuck_milestones(ws)] == ["m2"]
    assert worker.scheduled_job() == ("escalate", {})                  # what the owner's button would run
    one_more_try(ws, "m2", "failed")
    assert worker.scheduled_job() == ("build", {})                      # used: with "retry" nothing more by itself
    assert stuck.stuck_work(ws, "retry") is None


def test_the_one_more_try_takes_a_turn_and_the_others_build_in_between(tmp_path):
    ws = stuck_project(tmp_path, stuck_policy="retry")
    used_up(ws, "m2")
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("escalate", {})
    _write_json(ws.home / "WORK.json", {"utc": "2026-10-02T04:00:00Z", "kind": "escalate", "result": "failed"})
    assert worker.scheduled_job() == ("build", {})                      # while it waits on a model, the plan goes on
    _write_json(ws.home / "WORK.json", {"utc": "2026-10-02T04:05:00Z", "kind": "build", "result": "done"})
    assert worker.scheduled_job() == ("escalate", {})                   # then its turn again (nothing answered: unused)


def test_then_break_it_down_asks_once_and_never_for_a_smaller_step_or_over_the_owner(tmp_path):
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("split", {"milestone": "m2"})
    # the owner's own proposal, adopted or rejected, is his decision: the setting does not decide over it
    _write_json(ws.home / "breakdowns" / ("b" + "0" * 12 + ".json"), {"id": "b" + "0" * 12, "milestone": "m2", "state": "rejected"})
    assert not stuck.may_split(ws, ws.plan()["milestones"][1]) and worker.scheduled_job() == ("build", {})
    (ws.home / "breakdowns" / ("b" + "0" * 12 + ".json")).unlink()
    # a smaller step of a breakdown is not broken down again: no recursion
    plan = ws.plan()
    plan["milestones"][1]["parent_id"] = "m1"
    _write_json(ws.home / "PLAN.json", plan)
    assert not stuck.may_split(ws, ws.plan()["milestones"][1])


def test_a_milestone_the_owner_dropped_meanwhile_is_no_stuck_milestone(tmp_path):
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")
    ws.update_milestone("m2", {"status": "dropped"})
    assert stuck.stuck_milestones(ws) == [] and stuck.stuck_work(ws, "retry_split") is None


def test_the_split_proposes_adopts_in_the_owners_way_and_says_so(tmp_path):
    from test_breakdowns import answer
    from test_studio import scripted
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")
    scripted(ws, [answer()], roles=("plan",))
    result = stuck.split(ws, ws.router(), "m2")
    plan = ws.plan()
    children = [m for m in plan["milestones"] if m.get("parent_id") == "m2"]
    assert len(children) == 2 and next(m for m in plan["milestones"] if m["id"] == "m2")["depends_on"] == [c["id"] for c in children]
    [row] = automatic.recent(ws)
    assert row["kind"] == "split" and row["adopted"] is True and row["by"] == "Runesmith (your setting)"
    assert "broke it down into 2 smaller steps" in row["what"] and result["summary"] == row["what"]
    adopted = [r["data"] for r in ws.ledger if r["kind"] == "breakdown.adopted"]
    assert adopted and adopted[-1]["by"] == "Runesmith (your setting)"
    with pytest.raises(WorkspaceError, match="not one to break down by your setting"):
        stuck.split(ws, ws.router(), "m2")                              # once


def test_a_split_whose_call_failed_is_not_asked_again(tmp_path, monkeypatch):
    # "At most once per milestone": a call that left no proposal (no model answered, an unusable answer) is still the one.
    from runesmith.app.planner import PlannerUnavailable
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")

    def nobody(*args, **kwargs):
        raise PlannerUnavailable("no model answered")
    monkeypatch.setattr(stuck, "propose_breakdown", nobody)
    with pytest.raises(PlannerUnavailable):
        stuck.split(ws, ws.router(), "m2")
    assert "m2" in _read_json(ws.home / stuck.SPLITS, {}) and not stuck.may_split(ws, ws.plan()["milestones"][1])
    assert Worker(ws, EventBus()).scheduled_job() == ("build", {})


def test_a_proposal_the_owners_changes_make_stale_waits_for_him_instead_of_being_forced(tmp_path, monkeypatch):
    from test_breakdowns import answer
    from test_studio import scripted
    from runesmith.app import breakdowns
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")
    scripted(ws, [answer()], roles=("plan",))

    def changed(*args, **kwargs):
        raise WorkspaceError("Plan changed since the proposal; do not adopt stale work.")
    monkeypatch.setattr(stuck, "adopt_breakdown", changed)
    stuck.split(ws, ws.router(), "m2")
    assert not [m for m in ws.plan()["milestones"] if m.get("parent_id")]
    [row] = automatic.recent(ws)
    assert row["adopted"] is False and "they wait for you" in row["what"]
    assert [p for p in (ws.home / "breakdowns").glob("*.json")]            # the proposal is there to review


def test_the_one_more_try_by_the_setting_is_said_and_paced_like_other_scheduled_steps(tmp_path, monkeypatch):
    ws = stuck_project(tmp_path, stuck_policy="retry")
    used_up(ws, "m2")
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(worker, "_run_build_job", lambda kind, detail, **p: {"summary": "Draft d1: its own tests passed."})
    worker._execute({"id": "j1", "kind": "escalate", "params": {}, "by": "schedule"}, schedule_next=False)
    [row] = automatic.recent(ws)
    assert row["kind"] == "one_more_try" and "By your setting, Runesmith gave it one more try" in row["what"]
    assert "Large feature" in row["what"]
    assert _read_json(ws.home / "WORK.json", {})["kind"] == "escalate"        # the schedule's pacing sees it
    other = Worker(ws, EventBus())
    monkeypatch.setattr(other, "_run_build_job", lambda kind, detail, **p: {"summary": "x"})
    before = len(automatic.recent(ws, 99))
    other._execute({"id": "j2", "kind": "escalate", "params": {}, "by": "owner"}, schedule_next=False)
    assert len(automatic.recent(ws, 99)) == before                         # the owner's own button decides nothing for him


@pytest.mark.parametrize("policy,escalated,expected", [("wait", False, False), ("retry", False, True), ("retry", True, False),
                                                       ("retry_split", False, True), ("retry_split", True, True)])
def test_the_proposal_of_smaller_steps_waits_for_the_setting_to_have_its_turn(tmp_path, policy, escalated, expected):
    ws = stuck_project(tmp_path, stuck_policy=policy)
    used_up(ws, "m2", escalation="failed" if escalated else None)
    assert stuck.defers_breakdown(ws, "m2", policy) is expected
    assert Worker(ws, EventBus())._stuck_setting_first("m2") is expected


# ---- the five residuals of the last verification ---------------------------------------------------------------------

def test_a_focused_revision_is_blocked_only_by_a_prioritized_path_that_is_gone_and_names_it(tmp_path, monkeypatch):
    # Review of J11-B15 (verification round 3): author_revisions still refused every explicit revision on any focus
    # error, naming no file, when an ordinary build had gone on past a file too large to show.
    from test_author_revisions import setup, revision_status
    (tmp_path / "big.mjs").write_bytes(b"// y\n" * 8200)                  # 41,000 bytes: over the limit
    ws, draft = setup(tmp_path, monkeypatch)
    _write_json(ws.home / "AUTHOR_FOCUS.json", {"paths": ["big.mjs"], "reason": "It edits it", "utc": "2026-10-02T03:00:00Z"})
    assert revision_status(ws, draft["id"])["eligible"], revision_status(ws, draft["id"])["blockers"]
    _write_json(ws.home / "AUTHOR_FOCUS.json", {"paths": ["gone.mjs"], "reason": "It edits it", "utc": "2026-10-02T03:00:00Z"})
    blocked = revision_status(ws, draft["id"])
    assert not blocked["eligible"] and any("gone.mjs is prioritized" in text for text in blocked["blockers"])


def test_the_candidate_an_escalation_answer_is_checked_against_follows_the_one_rule(tmp_path):
    from test_build_steps import setup, enable
    from runesmith.app import building, planner
    from runesmith.app.building import build_escalation_status, build_step, escalate_build, readmit_escalation_answer
    from test_studio import scripted
    ws = setup(tmp_path, acceptance=True)
    enable(ws)
    lines = "".join(f"A{n} = {n}\n" for n in range(1, 8))
    wrong = {"title": "wrong", "files": [{"path": "app.py", "content": lines + "def answer():\n    return 0\n"},
                                         {"path": "tests/__init__.py", "content": ""},
                                         {"path": "tests/test_app.py", "content": "import unittest\nfrom app import answer\nclass Tests(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(),42)\n"}]}
    scripted(ws, [wrong] * 3, roles=("plan",))
    for _ in range(3):
        try:
            build_step(ws, ws.router())
        except Exception:
            pass
    eight = {"title": "eight edits", "why": "fix", "files": [{"path": "app.py", "edits":
        [{"old_text": f"A{n} = {n}", "new_text": f"B{n} = {n}"} for n in range(1, 8)] + [{"old_text": "return 0", "new_text": "return 42"}]}]}
    real = planner.MAX_EDITS
    planner.MAX_EDITS = 6
    try:
        scripted(ws, [eight], roles=("plan",))
        with pytest.raises(Exception, match="1-6 exact edits"):
            escalate_build(ws, ws.router())
    finally:
        planner.MAX_EDITS = real
    kept = build_escalation_status(ws)["kept_answer"]
    assert kept
    for draft in [d for d in ws.drafts() if d.get("state") == "needs_revision"]:
        ws._save_draft_state(draft, "needs_revision", public_acceptance_digest="f" * 64)   # checked by checks no longer in force
    assert build_escalation_status(ws)["kept_answer"] is None
    with pytest.raises(WorkspaceError, match="no matching frozen candidate"):
        readmit_escalation_answer(ws, kept["id"])
    assert building.revisable_candidates is planner.revisable_candidates


@pytest.mark.parametrize("damage", ["integer", "null", "mapping", "strings_and_numbers", "integer_and_no_receipt"])
def test_a_hand_damaged_quoted_index_never_breaks_a_withdrawal(tmp_path, damage):
    # Review of J11-G37 (verification round 3): an entry that was not a list raised inside withdraw(), after its checks
    # file had been moved, or silently stopped the retirement.
    from runesmith import memory as memory_module
    from runesmith.app import acceptance_proposals, build_memory
    from test_check_autopilot import approved_workspace
    ws = approved_workspace(tmp_path, answers=1)
    store = memory_module.Memory(ws.home / "memory.jsonl")
    evidence = ws.home / "build-evidence" / "later"
    _write_json(evidence / "VERIFICATION.json", {
        "public_contracts": [{"milestone": "m1", "digest": "d", "criteria": [{"id": "check.test_a"}]}],
        "acceptance": {"failure_details": [{"criteria": ["check.test_a"]}]}})
    later = store.add("negative", "Build check later", tags=["build_check"], source={
        "kind": "build_check", "milestone": "m2", "evidence_dir": "build-evidence/later", "draft": "later"})
    broken = {"integer": 7, "null": None, "mapping": {"m1": True}, "strings_and_numbers": ["m1", 3, None],
              "integer_and_no_receipt": 7}[damage]
    _write_json(ws.home / build_memory.QUOTED_INDEX, {later: broken})
    if damage == "integer_and_no_receipt":
        (evidence / "VERIFICATION.json").unlink()                            # nothing to read it again from
    acceptance_proposals.withdraw(ws, "m1", reason="wrong")                  # must not raise, the file already moved
    assert not acceptance_proposals.acceptance_file(ws, "m1").is_file()
    # An entry that is not a list says nothing: the receipt is read again, and the memory that quotes m1 is retired
    # (when there is no receipt, it quotes nothing and stays: it names no sentence of m1's).
    retired = later not in {row["id"] for row in store.active(source_kind=build_memory.SOURCE_KIND)}
    assert retired == (damage != "integer_and_no_receipt")


def test_a_receipt_that_could_not_be_read_is_not_indexed_as_quoting_nothing(tmp_path, monkeypatch):
    # Review of J11-G37 (verification round 3): one transient failure to read a receipt indexed its memory as "quotes
    # nothing" for ever, so a memory of withdrawn sentences stayed. Only a receipt that was read is indexed.
    from runesmith import memory as memory_module
    from runesmith.app import acceptance_proposals, build_memory
    from test_check_autopilot import approved_workspace
    ws = approved_workspace(tmp_path, answers=1)
    store = memory_module.Memory(ws.home / "memory.jsonl")
    _write_json(ws.home / "build-evidence" / "later" / "VERIFICATION.json", {
        "public_contracts": [{"milestone": "m1", "digest": "d", "criteria": [{"id": "check.test_a"}]}],
        "acceptance": {"failure_details": [{"criteria": ["check.test_a"]}]}})
    later = store.add("negative", "Build check later", tags=["build_check"], source={
        "kind": "build_check", "milestone": "m2", "evidence_dir": "build-evidence/later", "draft": "later"})
    real = build_memory._read_json
    failing = {"once": True}

    def flaky(path, default):
        if path.parent.name == "later" and failing["once"]:
            failing["once"] = False
            return default                                              # what an OSError becomes
        return real(path, default)
    monkeypatch.setattr(build_memory, "_read_json", flaky)
    build_memory.backfill_quoted(ws)
    assert later not in build_memory._quoted_index(ws)                  # not indexed: the next pass reads it again
    acceptance_proposals.withdraw(ws, "m1", reason="wrong")
    assert later not in {row["id"] for row in store.active(source_kind=build_memory.SOURCE_KIND)}


def test_a_verification_that_returned_early_is_not_called_withdrawn(tmp_path):
    # Review of J11-G37 (verification round 3): a syntax error, a stale source or a refusal never reached the owner's
    # checks and carries no digest of them; its memory read "checked by expectations since withdrawn or replaced".
    from runesmith.app.build_memory import recall_for_milestone, remember_check
    from test_check_autopilot import approved_workspace, draft_for
    ws = approved_workspace(tmp_path, answers=1)
    milestone = ws.plan()["milestones"][0]
    draft, _ = draft_for(ws, milestone)
    remember_check(ws, draft, {"status": "failed", "detail": "invalid syntax (app.py, line 1)", "utc": "2026-10-02T03:00:00Z"})
    text = json.dumps(recall_for_milestone(ws, milestone), ensure_ascii=False)
    assert "invalid syntax" in text and "withdrawn or replaced" not in text


def test_an_approval_waits_for_a_withdrawal_instead_of_overwriting_it(tmp_path):
    # Review of J11-G37 (verification round 3): approve() read the proposal record before it took any lock, so a
    # withdrawal landing in between was overwritten (6 of 40 overlaps of an autopilot replacement with a withdrawal).
    from runesmith.app import acceptance_proposals as ap
    from test_acceptance_examples import EXAMPLES
    from test_check_autopilot import autopilot_workspace
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 2, [])
    ap.approve(ws, "m1", ap.propose(ws, ws.router(backoff_s=()), "m1")["id"], by="autopilot")
    waiting = ap.propose(ws, ws.router(backoff_s=()), "m1")
    refused = []

    def autopilot():
        try:
            ap.approve(ws, "m1", waiting["id"], by="autopilot", replace=True, reason="Runesmith's check autopilot: x")
        except WorkspaceError as error:
            refused.append(str(error))
    thread = threading.Thread(target=autopilot)
    with ws._lock:
        thread.start()
        thread.join(0.5)                       # it has had time to read the record, if it reads before the lock
        ap.withdraw(ws, "m1", reason="The owner withdrew these checks.")
    thread.join(60)
    assert refused and "not waiting for approval" in refused[0]            # it read the record after the withdrawal
    assert not ap.acceptance_file(ws, "m1").is_file()                      # and the withdrawal stands


@pytest.mark.parametrize("act", ["note_autopilot", "discard"])
def test_the_record_is_never_read_and_written_back_outside_the_workspace_lock(tmp_path, act):
    # Review of J11-G37 (verification round 3): note_autopilot and discard read the record and wrote it back with no
    # lock, in a shorter window than approve.
    from runesmith.app import acceptance_proposals as ap
    from test_acceptance_examples import EXAMPLES
    from test_check_autopilot import autopilot_workspace
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 2, [])
    first = ap.propose(ws, ws.router(backoff_s=()), "m1")
    ap.approve(ws, "m1", first["id"])
    waiting = ap.propose(ws, ws.router(backoff_s=()), "m1")
    call = {"note_autopilot": lambda: ap.note_autopilot(ws, "m1", waiting["id"], {"decision": "turned_down", "reason": "x"}),
            "discard": lambda: ap.discard(ws, "m1", waiting["id"], reason="no")}[act]
    done = []
    worker = threading.Thread(target=lambda: (call(), done.append(1)))
    with ws._lock:
        worker.start()
        worker.join(0.5)
        assert not done                                                   # waits for whoever holds the workspace
    worker.join(60)
    assert done


# ---- J11-F30: a slow Withdraw -----------------------------------------------------------------------------------------

def approved_workspace(tmp_path):
    from runesmith.app import acceptance_proposals as ap
    from test_acceptance_examples import EXAMPLES
    from test_check_autopilot import autopilot_workspace
    ws = autopilot_workspace(tmp_path, [EXAMPLES] * 2, [])
    ap.approve(ws, "m1", ap.propose(ws, ws.router(backoff_s=()), "m1")["id"])
    return ws


def ledger_event(ws, kind):
    return [event for event in ws.ledger.events(kind)][-1]


def test_a_withdrawal_that_took_long_says_where_the_time_went_and_a_quick_one_says_nothing(tmp_path, monkeypatch):
    # Review of J11-F30: a Withdraw took two minutes on J11 and nothing recorded whether it had waited for the workspace
    # lock or worked: the ledger now keeps both numbers for a slow one.
    from runesmith.app import acceptance_proposals as ap
    ws = approved_workspace(tmp_path)
    ap.withdraw(ws, "m1", reason="The first checks were wrong.")
    assert "slow" not in ledger_event(ws, "acceptance.withdrawn")["data"]            # quick: nothing added
    ap.approve(ws, "m1", ap.propose(ws, ws.router(backoff_s=()), "m1")["id"])
    assert "slow" not in ledger_event(ws, "acceptance.approved")["data"]
    monkeypatch.setattr(ap, "SLOW_S", 0.2)
    holder = threading.Event()

    def hold_the_workspace():
        with ws._lock:
            holder.set()
            threading.Event().wait(0.5)
    thread = threading.Thread(target=hold_the_workspace)
    thread.start()
    holder.wait(5)
    ap.withdraw(ws, "m1", reason="Wrong again.")                                       # waits for the holder
    thread.join(5)
    slow = ledger_event(ws, "acceptance.withdrawn")["data"]["slow"]
    assert slow["seconds"] >= 0.4 and slow["waited_for_workspace_s"] >= 0.3 and slow["waited_for_workspace_s"] <= slow["seconds"]


def test_a_slow_approval_says_where_the_time_went_too(tmp_path, monkeypatch):
    from runesmith.app import acceptance_proposals as ap
    ws = approved_workspace(tmp_path)
    ap.withdraw(ws, "m1", reason="Wrong.")
    waiting = ap.propose(ws, ws.router(backoff_s=()), "m1")
    monkeypatch.setattr(ap, "SLOW_S", 0.0)
    ap.approve(ws, "m1", waiting["id"])
    slow = ledger_event(ws, "acceptance.approved")["data"]["slow"]
    assert set(slow) == {"seconds", "waited_for_workspace_s"} and slow["waited_for_workspace_s"] < 0.2


def test_the_overview_and_the_schedule_do_not_work_out_draft_diffs_which_only_the_work_page_reads(tmp_path, monkeypatch):
    # Review of J11-F30: Workspace.state() worked out the change of every edit of every draft on each refresh (half a
    # second on J11's 130 drafts), all of it Python competing with whatever else the Studio was doing.
    import difflib
    ws = Workspace(tmp_path)
    _write_json(ws.home / "drafts" / "d1" / "DRAFT.json", {
        "id": "d1", "state": "waiting", "utc": "2026-10-02T00:00:00Z", "milestone": "m1",
        "files": [{"path": "a.txt", "base": "one\ntwo\n", "content": "one\nthree\n"}]})
    seen = []
    real = difflib.unified_diff
    monkeypatch.setattr(difflib, "unified_diff", lambda *a, **k: (seen.append(1), real(*a, **k))[1])
    ws.state()
    assert not seen and "diff" not in ws.drafts()[0]["files"][0]
    work = ws.work()["drafts"][0]["files"][0]                  # the Work page still gets the change
    assert "-two" in work["diff"] and "+three" in work["diff"] and seen
    assert "+three" in ws.drafts(diffs=True)[0]["files"][0]["diff"]
