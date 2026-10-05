"""RUNESMITH.md: Runesmith's own log of what it did in a project folder (and nothing else)."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import pytest

from runesmith import __version__
from runesmith.app import runesmith_md
from runesmith.app.building import build_step, verify_draft
from runesmith.app.planner import draft_files, draft_prompt
from runesmith.app.snapshots import collect_snapshot, path_kind
from runesmith.app.workspace import Workspace
from runesmith.envmap import OWN_LOG, build_environment_map, classify_object
from test_build_steps import enable, setup as build_setup
from test_studio import fake_proposal, make_repo, scripted

FILE = runesmith_md.FILE_NAME
FAKE_KEY = "sk-proj-AbCdEf0123456789ZyXwVu"


def log_of(root: Path) -> list[str]:
    """The event lines of the log, oldest first."""
    text = (Path(root) / FILE).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.startswith("- ")]


def draft(ws, path="app.py", content="x = 1\n", **extra):
    return ws.save_draft(title="A draft", why="because", files=[{"path": path, "content": content}],
                         drafted_by=extra.pop("drafted_by", "gemini-2.5-flash"), **extra)


# ---------------------------------------------------------------------------------------------- the file --

def test_the_file_is_created_on_the_first_event_with_the_header_the_mark_and_the_version(tmp_path):
    ws = Workspace(tmp_path)
    assert not (tmp_path / FILE).exists()                     # nothing happened yet: nothing is written
    ws.add_milestone("Read the config")
    raw = (tmp_path / FILE).read_bytes()
    text = raw.decode("utf-8")
    assert b"\r" not in raw and text.startswith("# RUNESMITH.md\n")
    assert "open-source system that plans software as milestones" in text and "Runesmith's own log" in text
    assert f"**Runesmith {__version__}**" in text              # the version, named like a model
    block = text.split("```text\n", 1)[1].split("\n```", 1)[0].split("\n")
    assert tuple(block) == runesmith_md.LOGO
    assert len(runesmith_md.LOGO) == 12 and max(len(row) for row in runesmith_md.LOGO) <= 24
    assert set("".join(runesmith_md.LOGO)) <= set("█▀▄ ")
    assert log_of(tmp_path)[0].endswith(': The milestone "Read the config" was added.')
    assert re.match(r"^- \d{4}-\d\d-\d\d \d\d:\d\dZ: ", log_of(tmp_path)[0])        # a UTC stamp from the clock


def test_the_logo_is_the_marks_stone_with_the_rune_carved_through_it():
    rows = runesmith_md.LOGO
    assert rows[0].strip().startswith("▄▄██") and rows[0].rstrip().endswith("██▄▄")                 # the block's rounded top
    stem = [row for row in rows[2:10]]
    assert all(row.startswith("██████") and row[6] == " " for row in stem)                           # the rune's stem
    assert "▄▄▄▄" in rows[10] and rows[-1][12:15] == "   "                                            # the leg leaves the bottom


def test_the_log_is_append_only_newest_last(tmp_path):
    ws = Workspace(tmp_path)
    ws.add_milestone("First")
    before = (tmp_path / FILE).read_bytes()
    ws.add_milestone("Second")
    after = (tmp_path / FILE).read_bytes()
    assert after.startswith(before) and len(after) > len(before)
    assert [line.split(": ", 1)[1] for line in log_of(tmp_path)] == [
        'The milestone "First" was added.', 'The milestone "Second" was added.']


def test_a_new_version_refreshes_the_header_and_keeps_every_line(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ws.add_milestone("First")
    lines = log_of(tmp_path)
    monkeypatch.setattr(runesmith_md, "__version__", "9.8.7")
    ws.add_milestone("Second")
    text = (tmp_path / FILE).read_text(encoding="utf-8")
    assert "**Runesmith 9.8.7**" in text and f"**Runesmith {__version__}**" not in text
    assert log_of(tmp_path)[:1] == lines and len(log_of(tmp_path)) == 2


def test_a_file_that_is_not_runesmiths_is_left_alone(tmp_path):
    (tmp_path / FILE).write_text("my own notes\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    ws.add_milestone("First")
    assert (tmp_path / FILE).read_text(encoding="utf-8") == "my own notes\n"


def test_the_file_survives_concurrent_writers(tmp_path):
    ws = Workspace(tmp_path)
    ws.add_milestone("Start")
    threads = [threading.Thread(target=lambda n=n: [runesmith_md.record(ws, f"event {n}-{i}") for i in range(10)])
               for n in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(log_of(tmp_path)) == 61 and len({line.split(": ", 1)[1] for line in log_of(tmp_path)}) == 61


# ----------------------------------------------------------------------------------------------- the switch --

def test_off_means_no_file_and_no_change(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.settings()["runesmith_md"] is True               # on by default
    ws.update_settings({"runesmith_md": False})
    ws.add_milestone("First")
    assert not (tmp_path / FILE).exists()
    ws.update_settings({"runesmith_md": True})
    ws.add_milestone("Second")
    written = (tmp_path / FILE).read_bytes()
    ws.update_settings({"runesmith_md": False})
    ws.add_milestone("Third")
    ws.save_plan({"summary": "s", "milestones": [{"title": "Plan item"}]})
    assert (tmp_path / FILE).read_bytes() == written          # not touched either
    with pytest.raises(Exception):
        ws.update_settings({"runesmith_md": "yes"})           # on or off, nothing else


def test_observe_mode_only_looks_so_nothing_is_written(tmp_path):
    ws = Workspace(tmp_path)
    ws.update_settings({"autonomy": "observe"})
    ws.add_milestone("First")
    assert not (tmp_path / FILE).exists()


# ---------------------------------------------------------------------------- not the project's source --

def test_it_is_not_part_of_what_models_see_as_the_projects_source(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "NOTES.md").write_text("# notes\n", encoding="utf-8")
    ws.set_brief(blueprints=["NOTES.md"])                      # a shared document declares every document beside it
    ws.update_settings({"build_paths": ["."]})
    ws.add_milestone("First")
    assert (tmp_path / FILE).is_file()
    snapshot = collect_snapshot(ws)
    assert FILE not in snapshot["files"] and FILE not in snapshot["manifest"] and "NOTES.md" in snapshot["files"]
    for name in ("RUNESMITH.md", "runesmith.md", "sub/Runesmith.MD"):
        assert path_kind(name, ("**", "./", "sub/")) is None
    assert [b["path"] for b in ws.candidate_blueprints()] == ["NOTES.md"]       # never offered as a blueprint
    assert ws.set_brief(blueprints=[FILE])["blueprints"] == []                 # nor accepted as one
    ws.save_plan({"summary": "Tiny", "milestones": [{"title": "Answer", "done_when": "answer() returns 42"}]})
    packet = json.loads(draft_prompt(ws, ws.plan()["milestones"][0]))
    assert "NOTES.md" in packet["existing_documents_not_to_replace"] and FILE not in json.dumps(packet)


def test_the_instruction_reader_skips_the_log_but_still_reads_an_owners_own_runesmith_md(tmp_path):
    from runesmith.app.environment_intent import inspect_intent
    ws = Workspace(tmp_path)
    ws.add_milestone("First")
    first = inspect_intent(ws)
    assert [r["path"] for r in first["instructions"]] == []             # the log is not an instruction to any model
    ws.add_milestone("Second")
    assert inspect_intent(ws)["instruction_digest"] == first["instruction_digest"]   # nor does it move the digest
    own = tmp_path / "owners"
    own.mkdir()
    (own / FILE).write_text("# My rules\nAlways use tabs.\n", encoding="utf-8")       # a file by that name that he wrote
    mine = Workspace(own)
    mine.add_milestone("First")
    assert (own / FILE).read_text(encoding="utf-8") == "# My rules\nAlways use tabs.\n"   # left alone, as always
    assert [r["path"] for r in inspect_intent(mine)["instructions"]] == [FILE]            # and still read as his


def test_the_log_never_changes_what_a_waiting_draft_was_checked_against(tmp_path):
    ws = build_setup(tmp_path, acceptance=True)
    enable(ws)
    (tmp_path / "GUIDE.md").write_text("# guide\n", encoding="utf-8")
    ws.set_brief(blueprints=["GUIDE.md"])                      # with documents declared, the log would be an input
    ws.update_settings({"build_paths": ["."]})
    assert (tmp_path / FILE).is_file() and FILE not in collect_snapshot(ws)["files"]
    first = draft_files(ws, ws.router())
    for title in ("One", "Two", "Three"):
        ws.add_milestone(title)                                # each one adds a line to RUNESMITH.md
    assert len(log_of(tmp_path)) == 4                          # the plan, then the three milestones
    assert verify_draft(ws, first)["status"] == "acceptance_passed"          # not "stale"


def test_an_empty_folder_with_only_the_log_still_maps_as_an_empty_folder(tmp_path):
    ws = Workspace(tmp_path)
    ws.add_milestone("First")
    assert OWN_LOG == FILE.lower()
    env = build_environment_map(tmp_path)
    assert env["workspace_facts"]["empty"] is True and env["objects"] == []
    assert env["workspace_facts"]["entries"] == [] and classify_object(tmp_path) == "unknown"
    (tmp_path / "script.py").write_text("print(1)\n", encoding="utf-8")
    assert [e["name"] for e in build_environment_map(tmp_path)["workspace_facts"]["entries"]] == ["script.py"]


# ------------------------------------------------------------------------------------------------- drafts --

def test_drafts_that_touch_it_are_refused_and_never_applied(tmp_path):
    ws = Workspace(tmp_path)
    ws.add_milestone("First")
    before = (tmp_path / FILE).read_bytes()
    for name in ("RUNESMITH.md", "runesmith.md", "./Runesmith.MD", "docs\\RUNESMITH.md"):
        with pytest.raises(Exception, match="no usable files"):
            draft(ws, name, "forged\n")
    mixed = ws.save_draft(title="Mixed", why="", drafted_by="m", files=[
        {"path": "RUNESMITH.md", "content": "forged\n"}, {"path": "app.py", "content": "x = 1\n"}])
    assert [f["path"] for f in mixed["files"]] == ["app.py"] and mixed["refused"] == ["RUNESMITH.md"]
    # A draft file written by hand (an older or tampered record) is refused again when it is applied.
    forged = ws.home / "drafts" / "dforged0001" / "DRAFT.json"
    forged.parent.mkdir(parents=True)
    forged.write_text(json.dumps({"id": "dforged0001", "title": "t", "why": "", "state": "waiting", "milestone": None,
                                  "files": [{"path": "RUNESMITH.md", "content": "forged\n", "existed": True}]}), encoding="utf-8")
    result = ws.apply_draft("dforged0001", overwrite=True)
    assert result["ok"] is False and result["conflicts"] == ["RUNESMITH.md"]
    assert (tmp_path / FILE).read_bytes() == before
    with pytest.raises(Exception):
        ws.update_settings({"build_paths": [FILE]})            # nor can it be an "allowed file"


def test_a_repair_proposal_that_names_it_is_refused_too(tmp_path):
    from runesmith.loop import ExperienceStore
    ws = Workspace(tmp_path)
    repo = make_repo(tmp_path)
    (repo / FILE).write_text("old\n", encoding="utf-8")
    ExperienceStore(ws.home / "experience").add(
        key="loop-test-0009", opportunity={"repo": str(repo), "failing_tests": [], "issue": "x"},
        parent_src={FILE: "old\n"}, record={"status": "public_pass", "strict_success": True}, final={FILE: "forged\n"})
    result = ws.apply_proposal("loop-test-0009")
    assert result["ok"] is False and result["conflicts"] == [FILE]
    assert (repo / FILE).read_text(encoding="utf-8") == "old\n"


# -------------------------------------------------------------------------------------------- no secrets --

def test_a_key_in_an_events_text_never_reaches_the_file(tmp_path):
    ws = Workspace(tmp_path)
    ws.keys.set("mine", "correct-horse-battery-staple")
    ws.add_milestone(f"Call the API with {FAKE_KEY} soon")
    ws.add_milestone("Use correct-horse-battery-staple here")                 # a key the home keeps, as typed
    runesmith_md.record(ws, f"Authorization: Bearer abcdefgh12345678 and api_key = {FAKE_KEY}")
    runesmith_md.record(ws, "Saw https://example.com/v1?key=AIzaSyA1234567890123456789012345&x=1 and sk-live1234567")
    runesmith_md.record(ws, "token=ghp_abcdefghijklmnopqrstuvwxyz0123456789 and 0123456789abcdef0123456789abcdef0123")
    runesmith_md.record(ws, "a" * 40 + "9" + " and AKIAIOSFODNN7EXAMPLE and eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4")
    runesmith_md.record(ws, "line one\nline two with `backticks`\r\n- 2026-01-01 00:00Z: a forged entry")
    text = (tmp_path / FILE).read_text(encoding="utf-8")
    for secret in (FAKE_KEY, "correct-horse-battery-staple", "abcdefgh12345678", "AIzaSy", "example.com", "sk-live",
                   "ghp_", "0123456789abcdef", "AKIAIOSFODNN", "eyJhbGci"):
        assert secret not in text, secret
    assert len(log_of(tmp_path)) == 7 and "[removed]" in text      # the forged "entry" stayed inside one line
    assert all(line.count("`") == 0 for line in log_of(tmp_path))
    assert "forged entry" in log_of(tmp_path)[-1] and "\n- 2026-01-01" not in text


def test_ordinary_words_and_file_names_are_not_mistaken_for_secrets(tmp_path):
    ws = Workspace(tmp_path)
    ws.add_milestone("Parse the token stream and show the key points")
    ws.add_milestone("Write tests/test_the_very_long_module_name_for_the_parser.py")
    assert [line.split(": ", 1)[1] for line in log_of(tmp_path)] == [
        'The milestone "Parse the token stream and show the key points" was added.',
        'The milestone "Write tests/test_the_very_long_module_name_for_the_parser.py" was added.']


def test_nothing_internal_is_named_and_a_line_stays_short(tmp_path):
    ws = Workspace(tmp_path)
    runesmith_md.record(ws, "Asked Milliner and milliner-router, " + "word " * 100)
    [line] = log_of(tmp_path)
    assert "illiner" not in line and len(line) < 300 and line.endswith("…")


# ---------------------------------------------------------------------------------------------- the events --

def test_each_owner_decision_and_milestone_change_is_one_plain_line(tmp_path):
    ws = Workspace(tmp_path)
    config = ws.config()
    config["instruments"]["gem"] = {"kind": "openai", "model": "gemini-2.5-flash", "preset": "gemini"}
    ws.save_config(config)
    plan = ws.save_plan({"summary": "s", "drafted_by": "gemini-2.5-flash", "milestones": [
        {"title": "Read the config"}, {"title": "Write the report"}]})
    first, second = (m["id"] for m in plan["milestones"])
    ws.add_milestone("Add a help page")
    ws.update_milestone(first, {"detail": "more words"})                  # a text edit: no event
    ws.update_milestone(first, {"status": "doing"})                       # not an event either
    ws.update_milestone(first, {"status": "done"})
    ws.update_milestone(second, {"status": "dropped"})
    ws.save_plan({"summary": "s", "drafted_by": "gemini-2.5-flash", "milestones": [{"title": "Read the config"}, {"title": "New idea"}]},
                 kept=[])
    made = draft(ws, "app.py", "x = 1\n", milestone=first)
    assert ws.apply_draft(made["id"])["ok"] and ws.undo_draft(made["id"])["ok"]
    ws.reject_draft(draft(ws, "b.py")["id"], "not what I meant")
    lines = [line.split(": ", 1)[1] for line in log_of(tmp_path)]
    assert lines[0] == "A plan was drafted by Google Gemini (gemini-2.5-flash) with 2 milestones: \"Read the config\", \"Write the report\"."
    assert 'The milestone "Add a help page" was added.' in lines
    assert 'The milestone "Read the config" was marked done.' in lines
    assert 'The milestone "Write the report" was dropped from the plan.' in lines
    assert any(l.startswith("The plan was redrafted by Google Gemini") and 'added "New idea"' in l for l in lines)
    assert ('You approved a draft for the milestone "Read the config"; its files were written: app.py. '
            'Code by Google Gemini (gemini-2.5-flash).') in lines
    assert 'You undid a draft for the milestone "Read the config"; its files were put back: app.py.' in lines
    assert "You turned down a draft. Code by Google Gemini (gemini-2.5-flash)." in lines
    assert not any("because" in l or "not what I meant" in l or "x = 1" in l for l in lines)     # no why, reason or content


def test_a_repair_the_owner_applies_undoes_or_turns_down_is_logged(tmp_path):
    ws = Workspace(tmp_path)
    repo = make_repo(tmp_path)
    key = fake_proposal(ws, repo)
    assert ws.apply_proposal(key)["ok"] and ws.undo_proposal(key)["ok"]
    assert ws.reject_proposal(key, "wrong approach")["ok"]
    assert [line.split(": ", 1)[1] for line in log_of(tmp_path)] == [
        "You approved a repair Runesmith proposed; its files were written: src/calc/ops.py.",
        "You undid a repair; its files were put back: src/calc/ops.py.",
        "You turned down a repair Runesmith proposed."]


def test_a_finished_build_says_how_many_checks_passed_and_which_model_wrote_the_code(tmp_path):
    ws = build_setup(tmp_path, acceptance=True)
    enable(ws)
    config = ws.config()
    config["instruments"]["offline"].update(label="The offline model", model="scripted")     # as a real instrument has
    ws.save_config(config)
    assert build_step(ws, ws.router())["advanced"]
    lines = [line.split(": ", 1)[1] for line in log_of(tmp_path)]
    done = [l for l in lines if l.startswith("Runesmith built")]
    assert len(done) == 1 and 'the milestone "Answer": 1 of 1 checks passed' in done[0]
    assert "app.py" in done[0] and "tests/test_app.py" in done[0] and "the milestone is done" in done[0]
    assert done[0].endswith("Code by The offline model (scripted).")
    assert not any(l.startswith("You approved a draft") or "was marked done" in l for l in lines)    # one line, not three
    # Undoing the applied build keeps what the log already said, and says what happened next.
    draft_id = ws.drafts()[0]["id"]
    assert ws.undo_draft(draft_id)["ok"]
    after = [line.split(": ", 1)[1] for line in log_of(tmp_path)]
    assert after[:len(lines)] == lines and after[-1].startswith("You undid a draft for the milestone \"Answer\"")


def test_checks_approved_withdrawn_and_discarded_are_logged_by_whom(tmp_path, monkeypatch):
    from test_acceptance_proposals import ANSWER, workspace
    from runesmith.app.acceptance_proposals import approve, discard, propose, withdraw
    monkeypatch.setattr("runesmith.app.acceptance_proposals.STYLE", "code")
    ws = workspace(tmp_path, [ANSWER, ANSWER, ANSWER])
    first = propose(ws, ws.router(), "m1")
    approve(ws, "m1", first["id"])
    withdraw(ws, "m1", reason="checks the wrong command")
    second = propose(ws, ws.router(), "m1")
    discard(ws, "m1", second["id"], reason="not these")
    third = propose(ws, ws.router(), "m1")
    approve(ws, "m1", third["id"], by="autopilot")
    lines = [line.split(": ", 1)[1] for line in log_of(tmp_path) if "heck" in line]
    assert len(lines) == 4
    assert lines[0].startswith('Checks for the milestone "Add a book" were approved by you: 2 checks.')
    assert lines[1] == 'You withdrew the approved checks for the milestone "Add a book".'
    assert lines[2] == 'You discarded the proposed checks for the milestone "Add a book".'
    assert lines[3].startswith("Checks for the milestone \"Add a book\" were approved by Runesmith's check autopilot: 2 checks.")
    assert not any("wrong command" in l or "not these" in l or "subprocess" in l for l in lines)   # no reasons, no code


def test_a_restart_decision_and_a_retry_are_logged(tmp_path):
    ws = Workspace(tmp_path)
    runesmith_md.restart_decision(ws, "keep", "owner", 2)
    runesmith_md.restart_decision(ws, "park", "owner", 1)
    runesmith_md.restart_decision(ws, "keep", "Runesmith (your setting)", 3)
    runesmith_md.retry_asked(ws)
    runesmith_md.retry_asked(ws, "resume_author")
    runesmith_md.retry_asked(ws, "map")                         # not a retry: nothing is written
    assert [line.split(": ", 1)[1] for line in log_of(tmp_path)] == [
        "After a restart, you chose to keep the waiting work (2 jobs).",
        "After a restart, you chose to set the waiting work aside (1 jobs).",
        "After a restart, Runesmith chose to keep the waiting work (3 jobs), as your setting says.",
        "You asked for one more try, with another model, for the milestones whose tries were used up.",
        "You asked Runesmith to retrieve a model's saved answer after an interruption (no new model call)."]


RETRY_JOBS = {"escalate": {}, "resume_author": {"request_id": "saved"}, "readmit": {"escalation": "e1"},
              "readmit_answer": {"attempt": "a1"}, "resume_check": {"draft_id": "d1", "reason": "it timed out"}}


@pytest.mark.parametrize("job", sorted(RETRY_JOBS))
def test_an_owner_s_retry_request_has_a_ledger_event_whether_or_not_anything_starts_and_with_the_log_off(tmp_path, job):
    # Starvation-integrity study (SI, T03): with no model the one more try could not start, so RUNESMITH.md said "You
    # asked for one more try..." and no ledger event said the owner had asked.
    from types import SimpleNamespace
    from runesmith.app.server import api_worker_run
    from runesmith.app.worker import EventBus, Worker
    ws = Workspace(tmp_path)
    app = SimpleNamespace(worker=Worker(ws, EventBus()), ws=ws)
    queued = api_worker_run(app, {}, {"job": job, "params": RETRY_JOBS[job]})
    assert [e["data"] for e in ws.ledger.events("build.retry_asked")] == [{"job": job, "id": queued["id"]}]
    assert len(log_of(tmp_path)) == 1
    assert not list(ws.ledger.events("build.escalation_started"))        # nothing started: that event would be false
    ws.update_settings({"runesmith_md": False})                           # the owner turned his own log off
    again = api_worker_run(app, {}, {"job": job, "params": dict(RETRY_JOBS[job], **({"reason": "again"} if job == "resume_check" else {}))})
    assert len(log_of(tmp_path)) == 1 and again["id"]
    assert [e["data"]["job"] for e in ws.ledger.events("build.retry_asked")] == [job, job]
    api_worker_run(app, {}, {"job": "map", "params": {}})                 # not a retry: no event
    assert len(list(ws.ledger.events("build.retry_asked"))) == 2


def test_a_build_judged_by_finished_milestones_checks_too_says_so(tmp_path):
    ws = Workspace(tmp_path)
    ws.save_plan({"summary": "s", "milestones": [{"title": "Groups"}]})
    runesmith_md.build_done(ws, "m1", {"drafted_by": None}, ["a.py"], 312, 312, 11)
    runesmith_md.build_done(ws, "m1", {"drafted_by": None}, ["a.py"], 5, 5, 1)
    runesmith_md.build_done(ws, "m1", {"drafted_by": None}, ["a.py"], 3, 3)
    one, two, three = [line.split(": ", 1)[1] for line in log_of(tmp_path)[1:]]
    assert "312 of 312 checks passed (this milestone's and those of the 11 finished milestones before it)," in one
    assert "5 of 5 checks passed (this milestone's and those of the 1 finished milestone before it)," in two
    assert "3 of 3 checks passed, its files" in three


def test_a_logging_failure_never_breaks_the_work(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(runesmith_md, "_write", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        assert ws.add_milestone("First")["title"] == "First"
    assert not (tmp_path / FILE).exists()
    (tmp_path / FILE).mkdir()                                  # a folder where the file belongs: left alone
    assert ws.add_milestone("Second")["title"] == "Second" and (tmp_path / FILE).is_dir()


# -------------------------------------------------------------------------------------------- undo, cap --

def test_undo_and_restore_never_erase_the_log(tmp_path):
    ws = Workspace(tmp_path)
    ws.add_milestone("First")
    made = draft(ws, "app.py", "x = 1\n")
    assert ws.apply_draft(made["id"])["ok"]
    written = (tmp_path / FILE).read_bytes()
    # Even a restore that lists the log (a record from elsewhere, an older version) leaves it exactly as it is.
    backup = ws.home / "backups" / "draft-evil" / FILE
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"old content\n")
    ws._restore("draft-evil", tmp_path, [FILE, "RUNESMITH.md", "runesmith.md"])
    assert (tmp_path / FILE).read_bytes() == written
    absent = ws.home / "backups" / "draft-gone" / (FILE + ".absent")
    absent.parent.mkdir(parents=True)
    absent.write_bytes(b"")
    ws._restore("draft-gone", tmp_path, [FILE])                 # "it did not exist before": still not removed
    assert (tmp_path / FILE).read_bytes() == written
    assert ws.undo_draft(made["id"])["ok"] and not (tmp_path / "app.py").exists()
    kept = log_of(tmp_path)
    assert len(kept) == 3 and kept[0].endswith('The milestone "First" was added.') and "You undid a draft" in kept[2]
    # An interrupted write that is rolled back never reaches the log either.
    assert ws.recover_writes() == []


def test_the_log_keeps_only_the_newest_entries_and_says_how_many_were_trimmed(tmp_path, monkeypatch):
    monkeypatch.setattr(runesmith_md, "MAX_ENTRIES", 5)
    ws = Workspace(tmp_path)
    for n in range(1, 13):
        runesmith_md.record(ws, f"event {n}")
    text = (tmp_path / FILE).read_text(encoding="utf-8")
    assert [line.split(": ", 1)[1] for line in log_of(tmp_path) if "trimmed" not in line] == [f"event {n}" for n in range(8, 13)]
    assert text.count("Older entries were trimmed: 7 earlier events") == 1
    assert text.split("## Log\n\n", 1)[1].startswith("- Older entries were trimmed")      # one line, at the top
    runesmith_md.record(ws, "event 13")                          # and it keeps counting
    text = (tmp_path / FILE).read_text(encoding="utf-8")
    assert "Older entries were trimmed: 8 earlier events" in text and "event 13" in text and "event 8" not in text
    assert text.count("```text") == 1 and "**Runesmith" in text   # the header survives every rewrite
    assert len([l for l in log_of(tmp_path) if "trimmed" not in l]) == 5
    assert not (tmp_path / (FILE + ".tmp")).exists()


def test_the_real_cap_is_a_thousand_entries():
    assert runesmith_md.MAX_ENTRIES == 1000


def test_scripted_models_do_not_need_a_label_to_be_named(tmp_path):
    ws = Workspace(tmp_path)
    scripted(ws, [], roles=("plan",))
    assert runesmith_md.model_name(ws, "offline") == "offline"
    assert runesmith_md.model_name(ws, "mystery-model-1") == "mystery-model-1"
    assert runesmith_md.model_name(ws, "Runesmith (no model): closest existing file") is None
    assert runesmith_md.model_name(ws, None) is None
