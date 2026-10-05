"""Runesmith's plan for improving itself: struggles, the scored plan, the owner's share, and a gate for every change."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from runesmith import generations
from runesmith.app import self_plan
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from runesmith.canon import digest_tree

BLOCKS = {share: [n for n in range(1, 11) if self_plan.is_self_turn(n, share)] for share in range(10, 100, 10)}
LONG = "x" * 25_000                                     # a file of 25,000 characters: large for a draft


def workspace(tmp_path, **settings) -> Workspace:
    root = tmp_path / "ws"
    root.mkdir(exist_ok=True)
    ws = Workspace(root)
    ws.update_settings({"onboarded": True, "auto_work": False, "kaizen": True, "policy_chosen": True, **settings})
    return ws


def job(kind, result, outcome, *, params=None, repeats=None, finished="2026-10-04T21:00:00Z", first=None, by="schedule"):
    row = {"id": f"{kind}-{finished}-{len(str(outcome))}", "kind": kind, "params": params or {}, "queued": finished,
           "by": by, "finished": finished, "seconds": 3.0, "result": result, "outcome": outcome}
    if repeats:
        row.update(repeats=repeats, first_finished=first or finished)
    return row


def stuck_milestone(ws, *, repeats=3, status="open"):
    """What the J11 run left behind for one milestone: a one-more-try draft of a large file whose checks failed, builds
    that then ended at once for want of an author allowance, and a break-down that was refused (the strings are the real
    ones; the counts are smaller)."""
    title = "Convert motion.mjs to module-compatible engine"
    _write_json(ws.home / "PLAN.json", {"summary": "s", "milestones": [
        {"id": "m1", "title": "Project Serialization Schema", "status": "done"},
        {"id": "mf5efcd", "title": title, "status": status}]})
    for draft_id in ("d20261004201918be2d", "d20261004195501aaaa"):
        folder = ws.home / "drafts" / draft_id
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "DRAFT.json", {"id": draft_id, "milestone": "mf5efcd", "state": "rejected", "files": [
            {"path": "motion.mjs", "content": LONG, "base": "y" * 40_179}], "verification": {
                "status": "failed", "project_checks": {"status": "ok", "output": ""},
                "acceptance": {"output": "1 failed", "failure_details": ["expected the engine to export generateSvg"]}}})
    draft = lambda d: {"draft": d, "milestone": "mf5efcd",                                            # noqa: E731
                       "summary": f"Draft “{title}”: checks failed. Nothing was written."}
    _write_json(ws.home / "STUDIO_JOBS.json", [
        job("build", "done", draft("d20261004195501aaaa"), finished="2026-10-04T19:55:00Z"),
        job("escalate", "done", draft("d20261004201918be2d"), params={"milestone_id": "mf5efcd"}, finished="2026-10-04T20:20:00Z"),
        job("build", "done", {"summary": "No unambiguous ordinary author allowance for this lineage. No new budget granted.",
                              "milestone": "mf5efcd"}, repeats=repeats, first="2026-10-04T20:22:00Z", finished="2026-10-04T21:00:00Z"),
        job("split", "failed", {"error": "A repair prerequisite names an absent file; candidate failures are not current-source failures."},
            params={"milestone": "mf5efcd"}, finished="2026-10-04T20:30:00Z")])
    _write_json(ws.home / "STUCK_REFUSED.json", {"mf5efcd": {"utc": "2026-10-04T20:30:00Z", "answered": False,
                                                              "why": "A repair prerequisite names an absent file"}})
    return title


def failed_repairs(ws, count=10):
    """Repair attempts that all ended the same way, so the repair organ has a ranked Kaizen target."""
    (ws.home / "sessions").mkdir(exist_ok=True)
    for index in range(count):
        _write_json(ws.home / "sessions" / f"loop-20261004T2{index // 10}0000Z-{index:04d}.json", {
            "key": f"loop-{index}", "status": "budget_exhausted", "strict_success": False, "cycle_seconds": 20.0,
            "model_calls": 2, "marks": [], "calls": [{"purpose": "navigate", "t_start": 0.0, "t_end": 5.0}]})


# ------------------------------------------------------------------------------------------------- the turns --

def test_self_improvement_turns_are_spread_evenly_in_every_block_of_ten():
    assert BLOCKS[20] == [5, 10]                          # the owner's example: the 5th and the 10th
    assert BLOCKS[10] == [10] and BLOCKS[50] == [2, 4, 6, 8, 10] and BLOCKS[30] == [4, 7, 10]
    for share, turns in BLOCKS.items():
        assert len(turns) == share // 10                  # exactly share/10 of every 10
        assert all(self_plan.is_self_turn(n + 10, share) == (n in turns) for n in range(1, 11))   # the same in every block
        gaps = [b - a for a, b in zip(turns, turns[1:] + [turns[0] + 10])]                 # around the block, wrapping
        assert max(gaps) - min(gaps) <= 1, (share, turns)                                    # evenly spread: no clumps
    assert self_plan.next_self_turn_in(0, 20) == 5 and self_plan.next_self_turn_in(4, 20) == 1
    assert self_plan.next_self_turn_in(5, 20) == 5 and self_plan.next_self_turn_in(10, 20) == 5


def test_the_share_is_a_setting_from_10_to_90_in_steps_of_10(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.settings()["self_improvement_share"] == 20
    assert ws.update_settings({"self_improvement_share": 60})["self_improvement_share"] == 60
    for bad in (5, 25, 0, 100, 95, "20", 20.0, True):
        with pytest.raises(WorkspaceError):
            ws.update_settings({"self_improvement_share": bad})
    assert ws.settings()["self_improvement_share"] == 60
    assert self_plan.sentence(20) == "2 of every 10 work turns go to improving Runesmith itself"
    assert self_plan.sentence(10) == "1 of every 10 work turns goes to improving Runesmith itself"
    # the owner's share is the Overview's baseline; attention's mode stays as a health signal
    from runesmith.kaizen.attention import Attention
    Attention().save(ws.home / "ATTENTION.json")
    assert ws.state()["attention"]["share"] == 0.6 and ws.state()["attention"]["mode"] == "HEALTHY"


def test_the_turn_counter_is_kept_in_the_home_and_survives_a_restart(tmp_path):
    ws = workspace(tmp_path)
    for _ in range(4):
        assert self_plan.turn(ws) == "object"
    restarted = Workspace(ws.root)                        # the Studio was closed and opened again
    self_plan.turn(restarted)                             # the 5th work turn: a self-improvement turn at 20 percent
    state = json.loads((ws.home / "SELF_PLAN.json").read_text(encoding="utf-8"))
    assert [row["turn"] for row in state["history"]] == [5]
    assert json.loads((ws.home / "SELF_TURNS.json").read_text(encoding="utf-8"))["turns"] == 5
    for _ in range(4):
        self_plan.turn(Workspace(ws.root))
    self_plan.turn(Workspace(ws.root))                    # the 10th
    state = json.loads((ws.home / "SELF_PLAN.json").read_text(encoding="utf-8"))
    assert [row["turn"] for row in state["history"]] == [5, 10]
    ws.update_settings({"kaizen": False})                 # off: turns are counted, none is a self-improvement turn
    for _ in range(10):
        assert self_plan.turn(ws) == "object"
    assert [row["turn"] for row in json.loads((ws.home / "SELF_PLAN.json").read_text(encoding="utf-8"))["history"]] == [5, 10]


# ---------------------------------------------------------------------------------------------- struggles --

def test_the_self_map_gets_a_struggles_section_from_the_object_side_records(tmp_path):
    ws = workspace(tmp_path)
    title = stuck_milestone(ws)
    struggles = {s["signature"]: s for s in ws.self_map(refresh=True)["struggles"]}
    assert {"draft_checks_failed_large_file", "no_author_allowance", "split_refused", "tries_used_up"} >= set(struggles) >= {
        "draft_checks_failed_large_file", "no_author_allowance", "split_refused"}
    allowance = struggles["no_author_allowance"]
    assert (allowance["milestone"], allowance["milestone_title"], allowance["count"]) == ("mf5efcd", title, 3)
    assert allowance["since"] == "2026-10-04T20:22:00Z" and allowance["current"] is True
    assert struggles["draft_checks_failed_large_file"]["count"] == 2           # two drafts of a large file failed their checks
    assert struggles["split_refused"]["count"] == 1 and struggles["split_refused"]["current"] is True   # the job and the record: once
    # a milestone that is done is no longer struggling; a project-wide failure no milestone owns is counted, never current
    stuck_milestone(ws, status="done")
    assert not any(s["current"] for s in ws.self_map(refresh=True)["struggles"])
    jobs = json.loads((ws.home / "STUDIO_JOBS.json").read_text(encoding="utf-8"))
    jobs += [job("build", "failed", {"error": "the model's answer was not usable: every route failed - gemini:flash truncated"},
                 repeats=4, finished="2026-10-04T22:00:00Z")]
    _write_json(ws.home / "STUDIO_JOBS.json", jobs)
    free = [s for s in ws.self_map(refresh=True)["struggles"] if s["scope"] == "project"]
    assert [(s["signature"], s["count"], s["current"]) for s in free] == [("answer_truncated", 4, False)]


def test_a_failure_seen_once_is_no_struggle_and_the_map_is_unchanged_by_asking_again(tmp_path):
    ws = workspace(tmp_path)
    _write_json(ws.home / "STUDIO_JOBS.json", [job("build", "failed", {"error": "Exact edit refused for renderer.mjs: old_text "
                                                                                 "did not match exactly once in the current file"})])
    assert ws.self_map(refresh=True)["struggles"] == []
    first = (ws.home / "SELF_MAP.json").read_bytes()
    mtime = (ws.home / "SELF_MAP.json").stat().st_mtime_ns
    ws.self_map(refresh=True)
    assert (ws.home / "SELF_MAP.json").read_bytes() == first and (ws.home / "SELF_MAP.json").stat().st_mtime_ns == mtime


# ------------------------------------------------------------------------------------------------ scoring --

def test_the_score_follows_the_declared_rule_and_the_same_records_give_the_same_plan(tmp_path):
    ws = workspace(tmp_path)
    stuck_milestone(ws, repeats=23)
    failed_repairs(ws, 10)
    plan = self_plan.build_plan(ws.self_map(refresh=True))
    again = self_plan.build_plan(Workspace(ws.root).self_map(refresh=True))
    assert plan == again and plan["plan_digest"] == again["plan_digest"]                  # deterministic
    by_id = {item["id"]: item for item in plan["items"]}
    # 23 builds ended for want of an allowance, and that milestone struggles now: 46 weighted failures, 6 doublings:
    # benefit 60 (the cap); its last failure is the newest record: recency 20; no gate for this kind of change: 0
    assert by_id["fresh_try_after_one_more_try"]["score"] == {"total": 80, "benefit": 60, "recency": 20, "gate": 0}
    # every lost repair ended the same way: 100 percent of the lost repairs, capped at 60, plus the repair organ's gate
    target = next(i for i in plan["items"] if i["kind"] == "kaizen_target")
    assert target["score"] == {"total": 80, "benefit": 60, "recency": 0, "gate": 20} and target["rank"] == 1
    assert target["gate"] and not by_id["fresh_try_after_one_more_try"]["gate"]
    # two failed drafts of a large file on a struggling milestone: 4 weighted, 3 bits, 30; 40 minutes before the newest record: 20
    assert by_id["targeted_edits_large_files"]["score"] == {"total": 30 + 20, "benefit": 30, "recency": 20, "gate": 0}
    order = lambda i: (not i["priority"], -i["score"]["total"], i["id"])                   # noqa: E731
    assert [i["id"] for i in plan["items"]] == [i["id"] for i in sorted(plan["items"], key=order)]
    assert [i["id"] for i in plan["items"] if i["priority"]] == [i["id"] for i in plan["items"]][:sum(i["priority"] for i in plan["items"])]
    assert by_id["fresh_try_after_one_more_try"]["priority"] and not target["priority"]    # it answers a struggling milestone
    assert all(item["reason"] and item["title"] for item in plan["items"])               # a reason in plain words for each
    assert "No trial gate" in by_id["fresh_try_after_one_more_try"]["reason"]


# ------------------------------------------------------------------------------- the struggle takes priority --

def test_a_struggling_milestone_decides_what_the_self_improvement_turn_takes(tmp_path):
    """Tonight's sequence: the one-more-try draft failed its checks, no author allowance was left, the break-down was
    refused. The best-scored item of the whole plan is something else (the repair organ's own target), but the turn takes
    the best-scored option linked to that milestone's struggle."""
    ws = workspace(tmp_path)
    stuck_milestone(ws, repeats=3)
    failed_repairs(ws, 10)
    state = self_plan.refresh(ws)
    items = state["plan"]["items"]
    best = max(items, key=lambda i: i["score"]["total"])
    assert best["kind"] == "kaizen_target" and best["score"]["total"] == 80                # the best score in the plan
    struggles = {s["id"]: s for s in ws.self_map()["struggles"]}
    linked_ids = {i["id"] for i in items if set(i["struggles"]) & {k for k, s in struggles.items() if s["current"]}}
    assert linked_ids and best["id"] not in linked_ids and items[0]["id"] in linked_ids    # but the plan's first item answers the struggle
    assert items[0]["id"] == "fresh_try_after_one_more_try" and items[0]["score"]["total"] == 50
    chosen = self_plan.choose(state["plan"], list(struggles.values()), {}, campaign_ready=True)
    assert chosen["mode"] == "struggle" and chosen["action"] == "plan"                       # not the (ready) campaign
    assert chosen["item"] == "fresh_try_after_one_more_try"                                  # best-scored of the linked ones
    assert chosen["item"] in linked_ids
    link = struggles[chosen["struggle"]]
    assert link["milestone"] == "mf5efcd" and link["signature"] == "no_author_allowance"
    assert "Convert motion.mjs to module-compatible engine" in chosen["why"] and "struggling now" in chosen["why"]
    # the preview the page shows is the same choice
    assert state["next"]["item"] == chosen["item"] and state["next"]["struggle"] == chosen["struggle"]
    # once that milestone is no longer struggling, the plan's first item comes first again
    stuck_milestone(ws, status="done")
    calm = self_plan.refresh(ws)
    assert calm["next"]["mode"] == "top"                  # (no Improver is set up here, so the preview itself can only plan)
    again = self_plan.choose(calm["plan"], ws.self_map()["struggles"], calm["activity"], campaign_ready=True)
    assert again["mode"] == "top" and again["action"] == "campaign" and again["item"] == best["id"]
    assert calm["plan"]["items"][0]["id"] == best["id"]               # the plan's first item is the highest score again


def test_nothing_that_answers_the_struggle_means_the_plans_own_order(tmp_path):
    plan = {"items": [{"id": "kaizen:yield:x", "title": "Repair organ", "kind": "kaizen_target", "gate": "g", "rank": 1,
                       "struggles": [], "score": {"total": 60}},
                      {"id": "other", "title": "Other", "kind": "struggle", "gate": None, "struggles": [], "score": {"total": 10}}]}
    struggles = [{"id": "m|odd", "current": True, "milestone_title": "M", "words": "w", "count": 2, "since": None}]
    assert self_plan.choose(plan, struggles, {}, campaign_ready=True)["action"] == "campaign"
    assert self_plan.choose(plan, struggles, {}, campaign_ready=False)["item"] == "other"


# ------------------------------------------------------------------------------- no change without a gate --

def test_an_item_without_a_gate_is_recorded_as_planned_and_nothing_about_runesmith_changes(tmp_path, monkeypatch):
    from runesmith import loop
    ws = workspace(tmp_path)
    stuck_milestone(ws, repeats=3)                        # struggles and no repair attempts: no gate-able item exists
    kernel_before = digest_tree(Path(self_plan.__file__).resolve().parents[1])
    organs = ws.home / "generations" / generations.active(ws.home) / "organs"
    organs_before, active_before, listed_before = digest_tree(organs), generations.active(ws.home), generations.list_generations(ws.home)
    monkeypatch.setattr(loop, "subject_step", lambda **k: pytest.fail("a campaign was started without its gate"))
    said = []
    results = [self_plan.turn(ws, campaign_ready=True, say=lambda *a, **k: said.append(a[0])) for _ in range(10)]
    assert results == ["object"] * 10                     # every turn went back to the project's work
    state = json.loads((ws.home / "SELF_PLAN.json").read_text(encoding="utf-8"))
    assert [(row["turn"], row["action"]) for row in state["history"]] == [(5, "plan"), (10, "plan")]
    planned = {k: v for k, v in state["activity"].items() if v["status"].startswith("planned")}
    assert len(planned) == 2 and all(v["status"] == "planned: needs a gate" for v in planned.values())
    assert state["history"][0]["item"] != state["history"][1]["item"]               # the next turn takes the next item, not the same
    assert len(said) == 2 and all("needs a gate" in text and "Nothing about Runesmith was changed" in text for text in said)
    assert organs_before == digest_tree(organs) and active_before == generations.active(ws.home)
    assert listed_before == generations.list_generations(ws.home) and kernel_before == digest_tree(Path(self_plan.__file__).resolve().parents[1])
    assert not (ws.home / "kaizen").exists() and not (ws.home / "TRIAL.json").exists()
    assert len(list(ws.ledger.events("self_plan.planned"))) == 2


def test_a_gated_item_starts_a_campaign_only_when_it_can_run(tmp_path):
    ws = workspace(tmp_path)
    failed_repairs(ws, 10)
    for _ in range(4):
        self_plan.turn(ws, campaign_ready=True)
    assert self_plan.turn(ws, campaign_ready=False) == "object"                       # the 5th turn: the gate cannot run now
    for _ in range(4):
        self_plan.turn(ws, campaign_ready=True)
    assert self_plan.turn(ws, campaign_ready=True) == "subject"                      # the 10th: it can, and it does
    state = json.loads((ws.home / "SELF_PLAN.json").read_text(encoding="utf-8"))
    assert [(r["turn"], r["action"]) for r in state["history"]][-1] == (10, "campaign")
    [running] = [k for k, v in state["activity"].items() if v["status"] == "campaign running"]
    assert running.startswith("kaizen:yield:")
    self_plan.campaign_finished(ws, {"lane": "subject", "decision": "no_improvement"})
    assert json.loads((ws.home / "SELF_PLAN.json").read_text(encoding="utf-8"))["activity"][running]["status"] == "campaign: no improvement"


def test_the_run_loop_serves_the_object_at_every_turn_the_plan_cannot_use(tmp_path):
    """Through the real loop: the owner's policy decides, a self-improvement turn with nothing gate-able goes back to the
    repair at once (it never idles), and the repair is served."""
    from runesmith import cli
    from runesmith.instruments import Router
    from runesmith.kaizen.improve import FixtureInstrument
    from runesmith.loop import run_loop
    from test_kernel import make_repo
    from test_loop import HINTS
    ws = workspace(tmp_path)
    stuck_milestone(ws, repeats=3)
    repo = make_repo(tmp_path)
    opportunity = {"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"], "judge_tests": ["tests/test_ops.py"],
                   "issue": "add() returns a wrong value"}
    router = Router({"y": FixtureInstrument(HINTS)}, {"repair": "y", "kaizen": "y"}, backoff_s=(0,), sleep=lambda s: None)
    steps = []
    summary = run_loop(home=ws.home, opportunities=[opportunity] * 5, seed="plan", router=router, min_experience=1, kaizen_every=1,
                       on_step=steps.append, lane_policy=lambda ready: self_plan.turn(ws, campaign_ready=ready))
    assert summary["object_steps"] == 5 and summary["subject_steps"] == 0 and summary["strict_successes"] == 5
    state = json.loads((ws.home / "SELF_PLAN.json").read_text(encoding="utf-8"))
    assert [(r["turn"], r["action"]) for r in state["history"]] == [(5, "plan")]         # the 5th turn took an item, then served
    assert json.loads((ws.home / "SELF_TURNS.json").read_text(encoding="utf-8"))["turns"] == 5


# --------------------------------------------------------------------------------------------- RUNESMITH.md --

def test_runesmith_md_gets_a_line_when_the_first_item_changes_and_when_a_campaign_starts(tmp_path):
    ws = workspace(tmp_path)
    failed_repairs(ws, 10)
    self_plan.refresh(ws)
    log = (ws.root / "RUNESMITH.md").read_text(encoding="utf-8")
    assert log.count("Self-improvement plan: the first item is now") == 1 and "Repair organ: fewer" in log
    self_plan.refresh(ws)                                 # nothing changed: no second line
    assert (ws.root / "RUNESMITH.md").read_text(encoding="utf-8").count("Self-improvement plan:") == 1
    stuck_milestone(ws, repeats=23)                       # a struggle outscores the repair target: the first item changes
    self_plan.refresh(ws)
    log = (ws.root / "RUNESMITH.md").read_text(encoding="utf-8")
    assert log.count("Self-improvement plan: the first item is now") == 2
    assert "A fresh ordinary try after the one more try fails" in log
    stuck_milestone(ws, status="done")                    # calm again: the repair target comes first again
    self_plan.refresh(ws)
    for _ in range(4):
        self_plan.turn(ws, campaign_ready=True)
    assert self_plan.turn(ws, campaign_ready=True) == "subject"                      # the 5th turn
    log = (ws.root / "RUNESMITH.md").read_text(encoding="utf-8")
    assert "Self-improvement: Runesmith started a campaign on its repair organ" in log and log.count("started a campaign") == 1
    assert "illiner" not in log
    ws.update_settings({"runesmith_md": False})
    before = (ws.root / "RUNESMITH.md").read_text(encoding="utf-8")
    stuck_milestone(ws, repeats=40)
    self_plan.refresh(ws)
    assert (ws.root / "RUNESMITH.md").read_text(encoding="utf-8") == before            # off means never touched


# ----------------------------------------------------------------------------------------------- the worker --

def test_a_scheduled_build_step_is_one_work_turn_and_a_round_is_not(tmp_path):
    from runesmith.app.worker import EventBus, Worker
    ws = workspace(tmp_path)
    worker = Worker(ws, EventBus())
    worker.start()
    try:
        worker.enqueue("map", by="schedule", probe=False)
        deadline = time.time() + 120
        while time.time() < deadline and not any(j["kind"] == "map" for j in worker.history):
            time.sleep(0.2)
        assert any(j["kind"] == "map" for j in worker.history)
        assert json.loads((ws.home / "SELF_TURNS.json").read_text(encoding="utf-8"))["turns"] == 1
        worker.enqueue("map", by="owner", probe=False)           # the owner's own press is no turn
        while time.time() < deadline and sum(j["kind"] == "map" for j in worker.history) < 2:
            time.sleep(0.2)
        assert json.loads((ws.home / "SELF_TURNS.json").read_text(encoding="utf-8"))["turns"] == 1
        assert (ws.home / "SELF_PLAN.json").exists()              # the plan was refreshed after the scheduled step
    finally:
        worker.close()


# -------------------------------------------------------------------------------------------------- the page --

def test_the_page_reads_the_plan_and_the_studio_serves_it(tmp_path):
    ws = workspace(tmp_path, self_improvement_share=30)
    stuck_milestone(ws, repeats=3)
    failed_repairs(ws, 10)
    view = self_plan.view(ws)
    assert view["share"] == 30 and view["sentence"] == "3 of every 10 work turns go to improving Runesmith itself"
    assert view["next_self_turn_in"] == 4 and view["kaizen_on"]
    assert view["map"]["struggles"] >= 3 and view["map"]["current_struggles"] >= 3 and view["map"]["components"] > 50
    assert len(view["items"]) <= 10 and view["items"][0]["priority"] and view["items"][0]["status"].startswith("not yet planned")
    target = next(i for i in view["items"] if i["kind"] == "kaizen_target" and i.get("rank") == 1)
    assert target["status"].startswith("waits: no Improver model is set up")      # nothing here can run a campaign yet
    assert view["next"]["mode"] == "struggle" and view["next"]["struggle"] and view["rule"]["score"]
    assert all(s["words"] for s in view["struggles"])
    # served by the Studio's own route
    from types import SimpleNamespace
    from runesmith.app import server
    served = server.api_improve(SimpleNamespace(ws=ws), {}, {})
    assert served["plan"]["items"][0]["id"] == view["items"][0]["id"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_self_improvement_page_renders_the_plan():
    here = Path(__file__).resolve().parent
    result = subprocess.run(["node", str(here / "test_self_plan_view.mjs")], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "self-improvement view: ok" in result.stdout
