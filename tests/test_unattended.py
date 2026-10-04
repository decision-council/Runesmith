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


def one_more_try(ws, milestone_id, state="failed", key="e1"):
    milestone = next(m for m in ws.plan()["milestones"] if m["id"] == milestone_id)
    contract, snapshot = milestone_contract(ws, milestone), source_context(ws)["snapshot_digest"]
    _write_json(ws.home / "build-escalations" / (key + ".json"), {
        "id": key, "state": state, "contract": contract, "scope": ordinary_allowance(ws, contract, snapshot)["scope"],
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
    assert worker.scheduled_job() == ("escalate", {"milestone_id": "m2"})                  # what the owner's button would run
    one_more_try(ws, "m2", "failed")
    assert worker.scheduled_job() == ("build", {})                      # used: with "retry" nothing more by itself
    assert stuck.stuck_work(ws, "retry") is None


def test_the_one_more_try_takes_a_turn_and_the_others_build_in_between(tmp_path):
    ws = stuck_project(tmp_path, stuck_policy="retry")
    used_up(ws, "m2")
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("escalate", {"milestone_id": "m2"})
    _write_json(ws.home / "WORK.json", {"utc": "2026-10-02T04:00:00Z", "kind": "escalate", "result": "failed"})
    assert worker.scheduled_job() == ("build", {})                      # while it waits on a model, the plan goes on
    _write_json(ws.home / "WORK.json", {"utc": "2026-10-02T04:05:00Z", "kind": "build", "result": "done"})
    assert worker.scheduled_job() == ("escalate", {"milestone_id": "m2"})                   # then its turn again (nothing answered: unused)


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


# ---- EE4 (J11-G44): a draft whose checks did not finish ---------------------------------------------------------------

def owner_checks(tests):
    return ("import unittest\nfrom app import answer\n\n\nclass Acceptance(unittest.TestCase):\n"
            + "".join(f"    def test_c{n}(self):\n        self.assertEqual(answer(), 42)\n" for n in range(tests)))


def ran_out(tmp_path, monkeypatch, *, tests=97, phase="owner", policy="recheck"):
    """J11's Scatter: a draft whose checks ran out of time. 97 owner checks give the ordinary 254 s limit (60 + 2 each)."""
    from runesmith.app import building
    from test_build_steps import enable, setup
    ws = setup(tmp_path, acceptance=True)
    enable(ws)
    (ws.home / "acceptance" / "m1.py").write_text(owner_checks(tests), encoding="utf-8", newline="\n")
    ws.update_settings({"autonomy": "propose", "recheck_policy": policy})

    def run(stage, kind, logs, **kwargs):
        limit = kwargs.get("timeout_s") or 120        # an ordinary project phase is not told its limit
        if (kind == "project") != (phase == "project"):
            return {"status": "passed", "ok": True, "ran": 1, "elapsed_s": 1, "limit_s": limit}
        return {"status": "timeout", "ok": False, "elapsed_s": limit + 1.2, "limit_s": limit, "output": "unfinished"}
    monkeypatch.setattr(building, "_run_checks", run)
    result = building.build_step(ws, ws.router())
    assert result["verification"]["status"] == "inconclusive"
    return ws, result["draft"]


def finishing(monkeypatch, seen=None, times_out=None):
    """The checks run again: they pass, or the named phase ("owner") runs out of time again."""
    from runesmith.app import building

    def run(stage, kind, logs, **kwargs):
        phase = kind if kind == "project" else "owner"
        if seen is not None:
            seen.append((phase, kwargs.get("timeout_s")))
        if times_out == phase:
            return {"status": "timeout", "ok": False, "elapsed_s": kwargs["timeout_s"], "limit_s": kwargs["timeout_s"]}
        return {"status": "passed", "ok": True, "ran": 1, "elapsed_s": 1, "limit_s": kwargs.get("timeout_s")}
    monkeypatch.setattr(building, "_run_checks", run)


def scheduled_recheck(ws, did):
    from runesmith.app import rechecks
    return {"id": "j-" + did, "kind": "resume_check", "params": {"draft_id": did, "reason": rechecks.REASON}, "by": "schedule"}


def test_the_recheck_setting_waits_for_the_owner_by_default_and_refuses_other_words(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.settings()["recheck_policy"] == "wait"
    ws.update_settings({"recheck_policy": "recheck"})
    assert ws.settings()["recheck_policy"] == "recheck"
    with pytest.raises(WorkspaceError, match="must be one of"):
        ws.update_settings({"recheck_policy": "twice"})
    assert ws.settings()["recheck_policy"] == "recheck"


@pytest.mark.parametrize("ordinary,given", [(120, 240), (254, 508), (300, 600), (460, 600), (600, 600)])
def test_the_extensions_owner_phase_gets_twice_the_ordinary_limit_and_at_most_600(tmp_path, monkeypatch, ordinary, given):
    # Journey J11-G44: the limit that just ran out is likely to run out again on the same loaded computer.
    from runesmith.app import building, verification_resume
    from test_build_steps import setup
    ws = setup(tmp_path, acceptance=True)
    monkeypatch.setattr(building, "owner_check_limit", lambda bundle: ordinary)
    assert verification_resume.owner_limit(ws, "m1") == given


def test_a_check_that_ran_out_at_the_ordinary_owner_limit_gets_the_longer_extension(tmp_path, monkeypatch):
    from runesmith.app.verification_resume import resume_status, resume_verification
    ws, did = ran_out(tmp_path, monkeypatch)
    prior = ws._draft(did)["verification"]
    assert prior["acceptance"]["limit_s"] == 254                       # J11's Scatter: 255.2 s against 254 s
    status = resume_status(ws, ws._draft(did))
    assert status["eligible"] and status["timeout_s"] == 240 and status["owner_timeout_s"] == 508
    seen = []
    finishing(monkeypatch, seen)
    resume_verification(ws, did, "The owner's button")
    assert seen == [("project", 240), ("owner", 508)]
    assert resume_status(ws, ws._draft(did))["receipt"]["owner_timeout_s"] == 508


@pytest.mark.parametrize("phase,tests", [("project", 97), ("owner", 270)])
def test_an_extension_that_would_give_a_phase_no_more_than_it_had_is_not_offered(tmp_path, monkeypatch, phase, tests):
    # The project phase keeps its rule (240 s, offered only below it); the owner phase is not offered where 600 s, its
    # most, is what it already had (270 checks give the ordinary 600 s).
    from runesmith.app import building
    from runesmith.app.verification_resume import resume_status
    ws, did = ran_out(tmp_path, monkeypatch, tests=tests, phase=phase)
    first = ws._draft(did)["verification"]
    assert first["project_checks" if phase == "project" else "acceptance"]["status"] == "timeout"
    if phase == "project":                                              # an ordinary project phase is 120 s: offered
        assert resume_status(ws, ws._draft(did))["eligible"]
        draft = ws._draft(did)
        draft["verification"]["project_checks"]["limit_s"] = 240        # but not once it had the extension's 240 s
        ws._save_draft_state(draft, draft["state"])
    assert not resume_status(ws, ws._draft(did))["eligible"]


def test_the_default_waits_for_the_owner_when_checks_did_not_finish(tmp_path, monkeypatch):
    ws, did = ran_out(tmp_path, monkeypatch, policy="wait")
    assert Worker(ws, EventBus()).scheduled_job() == ("build", {})


def test_with_the_setting_the_schedule_rechecks_a_draft_whose_checks_did_not_finish(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    ws, did = ran_out(tmp_path, monkeypatch)
    assert Worker(ws, EventBus()).scheduled_job() == ("resume_check", {"draft_id": did, "reason": rechecks.REASON})


def test_the_recheck_by_the_setting_is_the_owners_button_with_no_model_said_and_once(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    from runesmith.app.verification_resume import resume_status
    ws, did = ran_out(tmp_path, monkeypatch)
    worker = Worker(ws, EventBus())

    def forbidden(*args, **kwargs):
        raise AssertionError("No model call for a recheck")
    monkeypatch.setattr(ws, "router", forbidden)
    seen = []
    finishing(monkeypatch, seen, times_out="owner")                       # it runs out again: the owner's button would too
    worker._execute(scheduled_recheck(ws, did), schedule_next=False)
    assert worker.history[-1]["result"] == "done" and seen == [("project", 240), ("owner", 508)]
    receipt = resume_status(ws, ws._draft(did))["receipt"]
    assert receipt["state"] == "completed" and receipt["outcome"] == "inconclusive" and receipt["inference_calls"] == 0
    assert receipt["reason"] == rechecks.REASON and receipt["owner_timeout_s"] == 508 and receipt["author_budget_reset"] is False
    [row] = automatic.recent(ws)
    assert row["kind"] == "recheck" and row["by"] == "Runesmith (your setting)" and row["draft"] == did
    assert "ran them once more with a longer limit and no model call" in row["what"] and "Answer" in row["what"]
    assert did in _read_json(ws.home / rechecks.MARKS, {})
    assert [e["data"]["id"] for e in ws.ledger.events("build.check_resume_completed")] == ["check-" + did]
    assert Worker(ws, EventBus()).scheduled_job() == ("build", {})      # once per draft, though it ran out again


def test_a_recheck_that_finishes_applies_the_draft_under_the_grant_like_the_owners_button(tmp_path, monkeypatch):
    ws, did = ran_out(tmp_path, monkeypatch)
    worker = Worker(ws, EventBus())
    finishing(monkeypatch)
    worker._execute(scheduled_recheck(ws, did), schedule_next=False)
    assert (tmp_path / "app.py").exists() and ws.plan()["milestones"][0]["status"] == "done"
    assert worker.history[-1]["outcome"].get("advanced")


def test_a_recheck_the_candidate_has_changed_under_refuses_like_the_button_and_is_not_asked_again(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    ws, did = ran_out(tmp_path, monkeypatch)
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job()[0] == "resume_check"
    (tmp_path / "unrelated.py").write_text("changed = 1\n", encoding="utf-8")       # the source moved on meanwhile
    finishing(monkeypatch)
    worker._execute(scheduled_recheck(ws, did), schedule_next=False)
    assert worker.history[-1]["result"] == "failed"
    [row] = automatic.recent(ws)
    assert row["kind"] == "recheck" and "could not" in row["what"] and "It waits for you." in row["what"]
    assert did in _read_json(ws.home / rechecks.MARKS, {})
    assert Worker(ws, EventBus()).scheduled_job()[0] != "resume_check"


def test_the_owners_own_extension_and_choices_win_over_the_setting(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    from runesmith.app.verification_resume import resume_verification
    ws, did = ran_out(tmp_path, monkeypatch)
    finishing(monkeypatch, times_out="owner")
    resume_verification(ws, did, "The owner pressed the button")           # his extension is the draft's one
    assert rechecks.next_draft(ws) is None
    other = tmp_path / "second"
    other.mkdir()
    ws2, did2 = ran_out(other, monkeypatch)
    ws2.update_settings({"build_steps": False})                            # building off: nothing to recheck for
    assert rechecks.next_draft(ws2) is None and Worker(ws2, EventBus()).scheduled_job() == ("round", {})
    ws2.update_settings({"build_steps": True, "autonomy": "observe"})
    assert Worker(ws2, EventBus()).scheduled_job() != ("resume_check", {"draft_id": did2, "reason": rechecks.REASON})


def test_only_the_newest_draft_of_a_milestone_is_rechecked_and_never_one_that_is_not_waiting(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    ws, did = ran_out(tmp_path, monkeypatch)
    assert rechecks.next_draft(ws)["id"] == did
    draft = ws._draft(did)
    ws._save_draft_state(draft, "rejected")                               # the owner rejected it
    assert rechecks.next_draft(ws) is None
    ws._save_draft_state(ws._draft(did), "waiting")
    newer = dict(ws._draft(did), id="d-newer", utc="2999-01-01T00:00:00Z", verification={"status": "failed"})
    _write_json(ws.home / "drafts" / "d-newer" / "DRAFT.json", newer)      # a newer draft supersedes it
    assert rechecks.next_draft(ws) is None


def test_a_recheck_the_owner_pressed_decides_nothing_for_him(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    ws, did = ran_out(tmp_path, monkeypatch)
    worker = Worker(ws, EventBus())
    finishing(monkeypatch)
    job = dict(scheduled_recheck(ws, did), by="owner")
    worker._execute(job, schedule_next=False)
    assert worker.history[-1]["result"] == "done" and not automatic.recent(ws)
    assert not (ws.home / rechecks.MARKS).exists()


def test_a_draft_made_for_an_earlier_contract_is_not_rechecked(tmp_path, monkeypatch):
    # The milestone was reworded after the draft: the button would refuse it (the contract moved), so the setting does
    # not spend its one ask on it.
    from runesmith.app import rechecks
    ws, did = ran_out(tmp_path, monkeypatch)
    assert rechecks.next_draft(ws)["id"] == did
    ws.update_milestone("m1", {"done_when": "answer() returns 42, always"})
    assert rechecks.next_draft(ws) is None


# ---- Review of batch EE (findings 6, 7, 8, 9, 10, 11, 12, 20, 21, 22) -------------------------------------------------

def two_stuck(tmp_path, **settings):
    """m2 and m3 have both used up their tries."""
    ws = stuck_project(tmp_path, **settings)
    third = ws.add_milestone("Second large feature", "does c", "", "c works")
    used_up(ws, "m2")
    used_up(ws, third["id"])
    return ws, third["id"]


def waiting_draft(ws, milestone_id, state="waiting", **extra):
    milestone = next(m for m in ws.plan()["milestones"] if m["id"] == milestone_id)
    draft = {"id": "dw-" + milestone_id, "state": state, "utc": "2026-10-02T04:00:00Z", "milestone": milestone_id,
             "contract": milestone_contract(ws, milestone), "files": [], **extra}
    _write_json(ws.home / "drafts" / draft["id"] / "DRAFT.json", draft)


# -- #6, #21: a breakdown no plan can adopt is never paid for ----------------------------------------------------------

def test_a_plan_without_room_for_the_steps_is_not_asked_and_the_old_proposal_is_not_held_back(tmp_path, monkeypatch):
    # Review of batch EE: J11's plan holds 124 milestones and the bound was 30, so every scheduled split paid for an
    # answer that could not be adopted, spent the milestone's only split, and kept the owner's proposal from coming.
    from runesmith.app import breakdowns
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")
    monkeypatch.setattr(breakdowns, "PLAN_BOUND", 5)                         # 2 milestones + up to 4 steps do not fit
    m2 = ws.plan()["milestones"][1]
    assert not stuck.may_split(ws, m2) and stuck.stuck_work(ws, "retry_split") is None
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("build", {})
    assert stuck.defers_breakdown(ws, "m2", "retry_split") is False          # the setting cannot act: the proposal comes
    calls = []

    class Asked:
        def call(self, *args, **kwargs):
            calls.append(1)
    with pytest.raises(WorkspaceError, match="nothing was asked"):
        stuck.split(ws, Asked(), "m2")
    assert not calls and not (ws.home / stuck.SPLITS).exists()                # and the once-only mark is not spent
    with pytest.raises(WorkspaceError, match="a plan holds at most 5"):
        breakdowns.input_packet(ws, "m2")


def test_a_plan_of_more_than_thirty_milestones_takes_a_breakdown_and_the_model_is_shown_it_in_outline(tmp_path):
    # Review of batch EE: the old bound of 30 refused every adoption on a plan an owner built; the request carried the
    # whole plan (206 KB of JSON on J11).
    from test_breakdowns import answer, setup
    from test_studio import scripted
    from runesmith.app.breakdowns import adopt_breakdown, propose_breakdown
    ws = setup(tmp_path)
    for n in range(40):
        ws.add_milestone(f"Extra {n}", "x" * 300, "", "done")
    ws.update_milestone("m2", {"depends_on": [ws.plan()["milestones"][2]["id"]]})
    scripted(ws, [answer()], roles=("plan",))
    record = propose_breakdown(ws, ws.router(), "m2")
    packet = json.loads((ws.home / record["packet_receipt"]).read_text())["packet"]
    shown = {m["id"]: m for m in packet["plan"]["milestones"]}
    parent = shown["m2"]
    assert parent["detail"] == "Add two functions" and set(shown[ws.plan()["milestones"][2]["id"]]) >= {"detail"}   # in full
    far = shown[ws.plan()["milestones"][-1]["id"]]
    assert set(far) == {"id", "title", "status"} and len(json.dumps(packet["plan"])) < 12000                  # in outline
    assert record["plan_digest"] == packet["plan_digest"] and "outline" in packet["plan"]
    assert len(adopt_breakdown(ws, record["id"])["children"]) == 2


def test_a_small_plan_is_sent_whole(tmp_path):
    from test_breakdowns import setup
    from runesmith.app.breakdowns import input_packet
    ws = setup(tmp_path)
    assert input_packet(ws, "m2")["plan"] == ws.plan()


@pytest.mark.parametrize("case", ["a smaller step", "split already", "not stuck any more"])
def test_the_old_proposal_waits_only_when_the_setting_will_act_on_that_milestone(tmp_path, case):
    # Review of batch EE: with "then break it down" the proposal of smaller steps was held back for every milestone,
    # also those the setting can never split.
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")
    assert stuck.defers_breakdown(ws, "m2", "retry_split") is True           # it will break it down itself
    if case == "a smaller step":
        plan = ws.plan()
        plan["milestones"][1]["parent_id"] = "m1"
        _write_json(ws.home / "PLAN.json", plan)
    elif case == "split already":
        _write_json(ws.home / stuck.SPLITS, {"m2": "2026-10-02T04:00:00Z"})
    else:
        ws.update_milestone("m2", {"status": "dropped"})
    assert stuck.defers_breakdown(ws, "m2", "retry_split") is False


# -- #7, #20: one blocked milestone does not hold the others back ------------------------------------------------------

def test_a_milestone_that_waits_on_a_draft_does_not_starve_the_one_more_try_of_the_others(tmp_path):
    # Review of batch EE: the one more try was offered only to the first milestone whose tries were used up, so one
    # that waited on a draft (an inconclusive check, an approval) stopped it for every milestone behind it.
    from runesmith.app.building import build_escalation_status
    ws, third = two_stuck(tmp_path, stuck_policy="retry")
    waiting_draft(ws, "m2")
    assert [r["milestone"]["id"] for r in stuck.stuck_milestones(ws)] == [third]
    state = build_escalation_status(ws)
    assert state["milestone"] == third and state["eligible"]
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("escalate", {"milestone_id": third})
    assert stuck.defers_breakdown(ws, third, "retry") is True               # its try is still to come
    assert build_escalation_status(ws, "m2")["eligible"] is False           # m2 itself is still held by its draft


def test_the_owners_button_and_the_setting_give_the_one_more_try_to_the_same_milestone(tmp_path, monkeypatch):
    from runesmith.app.building import build_escalation_status
    ws, third = two_stuck(tmp_path, stuck_policy="retry")
    waiting_draft(ws, "m2")
    assert build_escalation_status(ws)["milestone"] == third                # the button's choice
    worker = Worker(ws, EventBus())
    seen = []
    monkeypatch.setattr(worker, "_run_build_job", lambda kind, detail, **p: (seen.append((kind, p)), {"summary": "ok"})[1])
    worker._execute({"id": "j1", "kind": "escalate", "params": {"milestone_id": third}, "by": "schedule"}, schedule_next=False)
    assert seen == [("escalate", {"milestone_id": third})]
    [row] = automatic.recent(ws)
    assert row["milestone"] == third and "Second large feature" in row["what"]


# -- #8: a refusal for a file no model is shown is not paid for again ---------------------------------------------------

def test_the_setting_does_not_pay_again_for_a_one_more_try_refused_for_an_unshown_file(tmp_path):
    # Review of batch EE: such a refusal is not counted as used, so the schedule asked again every other step, a fresh
    # paid call each time, and never reached the split.
    from test_build_context import EDIT_HUGE, counting, gap_project
    from runesmith.app.building import escalate_build
    from runesmith.app.planner import PlannerUnavailable
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import save_focus
    ws = gap_project(tmp_path, [EDIT_HUGE] * 4)
    ws.update_settings({"stuck_policy": "retry_split", "autonomy": "propose"})
    used_up(ws, "m1")
    m1 = ws.plan()["milestones"][0]
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == ("escalate", {"milestone_id": "m1"})
    router = ws.router()
    calls = counting(router)
    with pytest.raises(PlannerUnavailable, match="huge.js was not shown"):
        escalate_build(ws, router, milestone_id="m1")
    assert len(calls) == 1 and stuck.gap_waits(ws, m1) == "huge.js"
    _write_json(ws.home / "WORK.json", {"utc": "2026-10-02T04:00:00Z", "kind": "build", "result": "done"})
    for _ in range(3):
        assert worker.scheduled_job() == ("build", {})                      # no second paid call while it is not shown
    save_focus(ws, ["huge.js"], collect_snapshot(ws)["digest"], "Builds of this milestone edit it")
    assert stuck.gap_waits(ws, m1) is None                                  # shown now: the setting resumes
    assert worker.scheduled_job() == ("escalate", {"milestone_id": "m1"})


def test_a_milestone_whose_try_waits_for_a_file_does_not_hold_back_the_next_one(tmp_path, monkeypatch):
    from test_build_context import EDIT_HUGE, gap_project
    from runesmith.app.building import escalate_build
    from runesmith.app.planner import PlannerUnavailable
    ws = gap_project(tmp_path, [EDIT_HUGE] * 2)
    ws.update_settings({"stuck_policy": "retry", "autonomy": "propose"})
    second = ws.add_milestone("Second step", "does b", "", "b works")
    used_up(ws, "m1")
    used_up(ws, second["id"])
    with pytest.raises(PlannerUnavailable, match="huge.js was not shown"):
        escalate_build(ws, ws.router(), milestone_id="m1")
    asked, real = [], stuck.build_escalation_status
    monkeypatch.setattr(stuck, "build_escalation_status", lambda ws, milestone_id=None: (asked.append(milestone_id), real(ws, milestone_id))[1])
    assert Worker(ws, EventBus()).scheduled_job() == ("escalate", {"milestone_id": second["id"]})
    assert asked == [second["id"]]                    # judged for the milestone it is given to, not for the first one


# -- #9: a decision reads the receipts once, outside the worker's lock --------------------------------------------------

def test_a_scheduling_decision_reads_each_receipt_once_not_once_per_ready_milestone(tmp_path, monkeypatch):
    # Review of batch EE: 29 ready milestones x 223 receipts = 6,500 reads per decision on J11's home (13 to 39 s).
    from pathlib import Path
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    for n in range(7):
        ws.add_milestone(f"Feature {n}", "does it", "", "it works")
    for milestone in ws.plan()["milestones"][1:]:
        used_up(ws, milestone["id"])
    receipts = list((ws.home / "build-attempts").glob("*.json"))
    assert len(receipts) == 24
    reads = []
    real = Path.read_text

    def counting_read(self, *args, **kwargs):
        if self.parent.name in ("build-attempts", "build-escalations"):
            reads.append(self.name)
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", counting_read)
    assert Worker(ws, EventBus()).scheduled_job()[0] == "escalate"
    assert len(reads) <= len(receipts) + 4, len(reads)                       # once each (before: several hundred)
    reads.clear()
    stuck.defers_breakdown(ws, "m2", "retry")
    assert len(reads) <= len(receipts) + 4, len(reads)


def test_the_schedule_chooses_its_next_step_without_holding_the_workers_lock(tmp_path, monkeypatch):
    ws = stuck_project(tmp_path)
    worker = Worker(ws, EventBus())
    held = []
    monkeypatch.setattr(worker, "scheduled_job", lambda: (held.append(worker._cv._is_owned()), ("build", {}))[1])
    monkeypatch.setattr(worker, "_due", lambda: 0)
    monkeypatch.setattr(worker, "_execute", lambda job: setattr(worker, "_closing", True))
    worker._run()
    assert held == [False]


def test_a_step_chosen_while_the_owner_paused_is_not_run(tmp_path, monkeypatch):
    ws = stuck_project(tmp_path)
    worker = Worker(ws, EventBus())

    def choose():
        worker.paused = True                                              # he pauses while the schedule is choosing
        return ("build", {})
    monkeypatch.setattr(worker, "scheduled_job", choose)
    monkeypatch.setattr(worker, "_due", lambda: 0)
    monkeypatch.setattr(worker._cv, "wait", lambda **kwargs: setattr(worker, "_closing", True))
    monkeypatch.setattr(worker, "_execute", lambda job: pytest.fail("ran a step chosen before the pause"))
    worker._run()


# -- #10, #22: one busy moment does not wedge every breakdown ------------------------------------------------------------

def test_a_split_turned_away_by_every_route_is_not_spent_and_blocks_nothing(tmp_path):
    # Review of batch EE: a call every route turned away was recorded as an uncertain one, which stops every breakdown
    # in the project until the owner abandons it, and the once-only mark stayed.
    from runesmith.app.breakdowns import propose_breakdown
    from runesmith.app.planner import PlannerUnavailable
    from runesmith.instruments import TransportCensored
    ws, third = two_stuck(tmp_path, stuck_policy="retry_split")
    one_more_try(ws, "m2", "failed")
    one_more_try(ws, third, "failed", key="e2")

    class Busy:
        def call(self, *args, **kwargs):
            raise TransportCensored("every route failed: overloaded", receipt={"no_route_accepted": True, "tokens_in": 0})
    with pytest.raises(PlannerUnavailable, match="did not reach a model") as refused:
        stuck.split(ws, Busy(), "m2")
    assert refused.value.nothing_ran
    [attempt] = [json.loads(p.read_text()) for p in (ws.home / "breakdown-attempts").glob("*.json")]
    assert attempt["state"] == "transport_failed" and "packet" not in attempt
    assert "m2" not in _read_json(ws.home / stuck.SPLITS, {})              # not spent
    milestones = {m["id"]: m for m in ws.plan()["milestones"]}
    assert stuck.may_split(ws, milestones["m2"]) and stuck.may_split(ws, milestones[third])
    assert Worker(ws, EventBus()).scheduled_job() == ("split", {"milestone": "m2"})
    from test_breakdowns import answer
    from test_studio import scripted
    scripted(ws, [answer()], roles=("plan",))
    assert propose_breakdown(ws, ws.router(), third)["state"] == "proposed"      # nothing waits for the owner to abandon


def test_three_turned_away_calls_do_not_count_as_attempts_on_unchanged_evidence(tmp_path):
    from runesmith.app.breakdowns import propose_breakdown
    from runesmith.app.planner import PlannerUnavailable
    from runesmith.instruments import TransportCensored
    from test_breakdowns import answer, setup
    from test_studio import scripted
    ws = setup(tmp_path)

    class Busy:
        def call(self, *args, **kwargs):
            raise TransportCensored("overloaded", receipt={"not_admitted": True})
    for _ in range(3):
        with pytest.raises(PlannerUnavailable, match="did not reach a model"):
            propose_breakdown(ws, Busy(), "m2")
    scripted(ws, [answer()], roles=("plan",))
    assert propose_breakdown(ws, ws.router(), "m2")["state"] == "proposed"


def test_a_call_that_may_have_been_processed_still_blocks_until_the_owner_reviews_it(tmp_path):
    from runesmith.app.breakdowns import propose_breakdown
    from runesmith.app.planner import PlannerUnavailable
    from runesmith.instruments import TransportCensored
    from test_breakdowns import setup
    ws = setup(tmp_path)

    class Lost:
        def call(self, *args, **kwargs):
            raise TransportCensored("no response after 3 attempts")             # no receipt: it may have run
    with pytest.raises(PlannerUnavailable, match="uncertain"):
        propose_breakdown(ws, Lost(), "m2")
    with pytest.raises(PlannerUnavailable, match="reconciliation"):
        propose_breakdown(ws, Lost(), "m2")


# -- #11: a queued step runs only while the setting still allows it ------------------------------------------------------

@pytest.mark.parametrize("kind", ["split", "escalate", "resume_check"])
def test_a_scheduled_step_queued_before_the_owner_set_the_policy_back_to_wait_does_nothing(tmp_path, monkeypatch, kind):
    # Review of batch EE: after a pause (or a restart that kept the queue) and "wait for me", the paid call and the
    # adoption still happened, said as "by your setting".
    from runesmith.app import rechecks
    if kind == "resume_check":
        ws, did = ran_out(tmp_path, monkeypatch)
        job = scheduled_recheck(ws, did)
        ws.update_settings({"recheck_policy": "wait"})
    else:
        ws = stuck_project(tmp_path, stuck_policy="retry_split")
        used_up(ws, "m2", escalation="failed" if kind == "split" else None)
        job = {"id": "j1", "kind": kind, "params": {"milestone": "m2"} if kind == "split" else {}, "by": "schedule"}
        ws.update_settings({"stuck_policy": "wait"})
    plan_before = ws.plan()
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(worker, "_run_build_job", lambda *a, **k: pytest.fail("a step ran after the setting was turned off"))
    monkeypatch.setattr(ws, "router", lambda *a, **k: pytest.fail("a model was asked after the setting was turned off"))
    worker._execute(job, schedule_next=False)
    assert worker.history[-1]["result"] == "skipped" and "no longer allows it" in worker.history[-1]["outcome"]["summary"]
    assert ws.plan() == plan_before and not automatic.recent(ws)
    assert not (ws.home / stuck.SPLITS).exists() and not (ws.home / rechecks.MARKS).exists()


def test_the_owners_own_button_is_not_asked_about_the_setting(tmp_path, monkeypatch):
    ws = stuck_project(tmp_path, stuck_policy="wait")
    used_up(ws, "m2")
    worker = Worker(ws, EventBus())
    monkeypatch.setattr(worker, "_run_build_job", lambda kind, detail, **p: {"summary": "ran"})
    worker._execute({"id": "j1", "kind": "escalate", "params": {}, "by": "owner"}, schedule_next=False)
    assert worker.history[-1]["result"] == "done"


# -- #12: a stop is no verdict ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("stop_at", [2, 3, 4])
def test_a_stop_during_a_recheck_gives_the_extension_back(tmp_path, monkeypatch, stop_at):
    # Review of batch EE: a stop, pause or close during the (up to 18 minute) extension used up the draft's only one and,
    # when it landed between phases, replaced the draft's verification with a record that nothing could resume.
    from runesmith.app.verification_resume import resume_status, resume_verification
    from runesmith.app.worker import StopRequested
    ws, did = ran_out(tmp_path, monkeypatch)
    before = ws._draft(did)["verification"]
    history = ws._draft(did).get("verification_history")
    finishing(monkeypatch)
    count = []

    def checkpoint():
        count.append(1)
        if len(count) >= stop_at:
            raise StopRequested()
    with pytest.raises(StopRequested):
        resume_verification(ws, did, "The owner's button", checkpoint=checkpoint)
    draft = ws._draft(did)
    status = resume_status(ws, draft)
    assert not status["used"] and status["eligible"], status
    assert draft["verification"] == before and draft.get("verification_history") == history
    assert [e["data"]["draft"] for e in ws.ledger.events("build.check_resume_stopped")] == [did]
    finishing(monkeypatch)                                                  # and it can be asked for again
    assert resume_verification(ws, did, "Again")["verification"]["status"] == "acceptance_passed"


def test_a_stop_after_the_checks_reached_a_verdict_keeps_the_verdict_and_the_extension_spent(tmp_path, monkeypatch):
    from runesmith.app.verification_resume import resume_status, resume_verification
    from runesmith.app.worker import StopRequested
    ws, did = ran_out(tmp_path, monkeypatch)
    finishing(monkeypatch, times_out="owner")
    count = []

    def checkpoint():
        count.append(1)
        if len(count) >= 5:                                                  # after both phases, before the apply
            raise StopRequested()
    with pytest.raises(StopRequested):
        resume_verification(ws, did, "The owner's button", checkpoint=checkpoint)
    status = resume_status(ws, ws._draft(did))
    assert status["used"] and status["receipt"]["state"] == "interrupted"
    assert ws._draft(did)["verification"]["acceptance"]["status"] == "timeout"


def test_a_scheduled_recheck_that_was_stopped_is_asked_for_again_by_the_setting(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    from runesmith.app.worker import StopRequested
    ws, did = ran_out(tmp_path, monkeypatch)
    worker = Worker(ws, EventBus())
    finishing(monkeypatch)
    calls = []

    def checkpoint():
        calls.append(1)
        if len(calls) >= 3:
            raise StopRequested()
    monkeypatch.setattr(worker, "_work_checkpoint", checkpoint)
    worker._execute(scheduled_recheck(ws, did), schedule_next=False)
    assert worker.history[-1]["result"] == "stopped"
    assert did not in _read_json(ws.home / rechecks.MARKS, {}) and rechecks.next_draft(ws)["id"] == did
    assert Worker(ws, EventBus()).scheduled_job() == ("resume_check", {"draft_id": did, "reason": rechecks.REASON})


# ---- saved work modes keep the unattended steps (found while writing the manual) --------------------------------------
# Once the owner pressed "Save modes", the schedule returned only the next mode: the check autopilot, the recheck and the
# stuck policy never started by themselves. With the build mode on they run first, in the same order and under the same
# conditions as before saving; with it off the schedule is the modes' alone.

def save_modes(ws, **on):
    """What "Save modes" on Modes & measurements writes: the named modes on, the rest off."""
    from runesmith.app import work_modes
    body = work_modes.configuration(ws)
    work_modes.save(ws, [dict(row, enabled=bool(on.get(row["id"], False))) for row in body["modes"]], body["revision"],
                    "Saved on Modes & measurements")
    assert work_modes.configuration(ws)["configured"]


def project_wanting_checks(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ws.update_settings({"build_steps": True, "checks_autopilot": True, "autonomy": "propose"})
    first = ws.add_milestone("First", "does a", "", "a works")
    return ws, ("propose_acceptance", {"milestone": first["id"]})


def project_with_a_draft_to_recheck(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    ws, did = ran_out(tmp_path, monkeypatch)
    return ws, (rechecks.KIND, {"draft_id": did, "reason": rechecks.REASON})


def project_with_tries_used_up(tmp_path, monkeypatch):
    ws = stuck_project(tmp_path, stuck_policy="retry")
    used_up(ws, "m2")
    return ws, ("escalate", {"milestone_id": "m2"})


STEPS = [("checks", project_wanting_checks), ("recheck", project_with_a_draft_to_recheck),
         ("stuck", project_with_tries_used_up)]


@pytest.mark.parametrize("name,project", STEPS, ids=[name for name, _ in STEPS])
def test_with_saved_modes_and_the_build_mode_on_the_unattended_step_comes_first(tmp_path, monkeypatch, name, project):
    ws, step = project(tmp_path, monkeypatch)
    assert Worker(ws, EventBus()).scheduled_job() == step                     # before saving: the step
    save_modes(ws, build=True)
    assert Worker(ws, EventBus()).scheduled_job() == step                     # after saving: the same step, not the mode


def test_with_saved_modes_the_checks_come_first_then_the_modes_take_their_turn(tmp_path, monkeypatch):
    ws, step = project_wanting_checks(tmp_path, monkeypatch)
    save_modes(ws, build=True)
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == step
    (ws.home / "acceptance").mkdir(exist_ok=True)
    (ws.home / "acceptance" / (step[1]["milestone"] + ".py")).write_text("# approved\n")
    assert worker.scheduled_job() == ("mode", {"mode": "build"})              # nothing unattended left: the next mode


def test_with_saved_modes_the_recheck_is_asked_once_and_then_the_modes_go_on(tmp_path, monkeypatch):
    from runesmith.app import rechecks
    ws, step = project_with_a_draft_to_recheck(tmp_path, monkeypatch)
    save_modes(ws, build=True)
    assert Worker(ws, EventBus()).scheduled_job() == step
    marks = ws.home / rechecks.MARKS
    _write_json(marks, {step[1]["draft_id"]: {"utc": "2026-10-04T00:00:00Z"}})   # once per draft: it was asked
    assert rechecks.next_draft(ws) is None
    assert Worker(ws, EventBus()).scheduled_job() == ("mode", {"mode": "build"})


def test_with_saved_modes_the_stuck_policy_takes_a_turn_and_the_modes_go_on_between(tmp_path, monkeypatch):
    ws, step = project_with_tries_used_up(tmp_path, monkeypatch)
    save_modes(ws, build=True)
    worker = Worker(ws, EventBus())
    assert worker.scheduled_job() == step
    _write_json(ws.home / "WORK.json", {"utc": "2026-10-04T04:00:00Z", "kind": "escalate", "result": "failed"})
    assert worker.scheduled_job() == ("mode", {"mode": "build"})              # while it waits on a model, the plan goes on
    _write_json(ws.home / "WORK.json", {"utc": "2026-10-04T04:05:00Z", "kind": "mode", "result": "done"})
    assert worker.scheduled_job() == step                                     # then its turn again


def test_with_saved_modes_the_breakdown_of_the_stuck_policy_is_scheduled_too(tmp_path):
    ws = stuck_project(tmp_path, stuck_policy="retry_split")
    used_up(ws, "m2", escalation="failed")
    save_modes(ws, build=True)
    assert Worker(ws, EventBus()).scheduled_job() == ("split", {"milestone": "m2"})


def test_with_saved_modes_the_stuck_policy_waits_when_it_is_the_default(tmp_path):
    ws = stuck_project(tmp_path)
    used_up(ws, "m2")
    save_modes(ws, build=True)
    assert Worker(ws, EventBus()).scheduled_job() == ("mode", {"mode": "build"})


@pytest.mark.parametrize("name,project", STEPS, ids=[name for name, _ in STEPS])
def test_with_saved_modes_and_the_build_mode_off_only_the_modes_choose(tmp_path, monkeypatch, name, project):
    from runesmith.app import acceptance_autopilot, rechecks
    ws, step = project(tmp_path, monkeypatch)
    assert Worker(ws, EventBus()).scheduled_job() == step
    save_modes(ws, troubleshoot=True)                                         # building is off in the saved modes

    def forbidden(*args, **kwargs):
        raise AssertionError("A step of the unattended settings was looked for with the build mode off")
    monkeypatch.setattr(acceptance_autopilot, "needs_checks", forbidden)
    monkeypatch.setattr(rechecks, "next_draft", forbidden)
    monkeypatch.setattr(stuck, "stuck_work", forbidden)
    assert Worker(ws, EventBus()).scheduled_job() == ("mode", {"mode": "troubleshoot"})
    save_modes(ws)                                                            # and with every mode off: nothing at all
    assert Worker(ws, EventBus()).scheduled_job() is None


def test_run_now_under_saved_modes_asks_for_the_same_unattended_step(tmp_path, monkeypatch):
    # "Run now" (api_worker_run job "next") asks scheduled_job: it queues the same step the schedule would.
    ws, step = project_with_tries_used_up(tmp_path, monkeypatch)
    save_modes(ws, build=True)
    worker = Worker(ws, EventBus())
    kind, params = worker.scheduled_job()
    job = worker.enqueue(kind, **params)
    assert (job["kind"], job["params"]) == step and job["by"] == "owner"
