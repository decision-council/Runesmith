"""Runesmith Studio: the workspace service, the worker, the planner and the local server."""

from __future__ import annotations

import http.client
import http.server
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from runesmith import generations
from runesmith.app.planner import PlannerUnavailable, SkippedByOwner, draft_files, draft_plan
from runesmith.app.server import Studio, bind
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import Workspace, WorkspaceError
from runesmith.envmap import build_environment_map
from runesmith.loop import ExperienceStore
from runesmith.objects.code import read_src_files, throwaway_copy

from test_kernel import make_repo

FIX_ANSWERS = [{"reads": [{"path": "src/calc/ops.py", "symbols": ["add"]}]},
               {"edits": [{"path": "src/calc/ops.py", "old_text": "return a - b", "new_text": "return a + b"}]}]


def scripted(ws: Workspace, answers: list, roles=("repair",)) -> None:
    config = ws.config()
    config["instruments"]["offline"] = {"kind": "scripted", "answers": answers}
    for role in roles:
        config["roles"][role] = ["offline"]
    ws.save_config(config)


def fake_proposal(ws: Workspace, repo: Path, *, key: str = "loop-test-0001") -> str:
    """A judge-accepted fix in the experience store, as the run loop leaves it."""
    parent = {"src/calc/ops.py": (repo / "src" / "calc" / "ops.py").read_bytes().decode("utf-8-sig").replace("\r\n", "\n")}
    final = {"src/calc/ops.py": parent["src/calc/ops.py"].replace("return a - b", "return a + b")}
    ExperienceStore(ws.home / "experience").add(
        key=key, opportunity={"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"], "issue": "add is wrong"},
        parent_src=parent, record={"status": "public_pass", "strict_success": True}, final=final)
    return key


# ------------------------------------------------------------------ envmap --

def test_envmap_maps_empty_loose_and_excluded_folders(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    env = build_environment_map(empty)
    assert env["objects"] == [] and env["workspace_facts"]["empty"] is True
    loose = tmp_path / "loose"
    (loose / "keep").mkdir(parents=True)
    (loose / "keep" / "a.bin").write_bytes(b"x")
    (loose / "script.py").write_text("print(1)\n", encoding="utf-8")
    (loose / "secret").mkdir()
    env = build_environment_map(loose, exclude={"secret"})
    by = {o["name"]: o for o in env["objects"]}
    assert by["loose"]["root"] is True and by["loose"]["kind"] == "folder"          # its own loose files
    assert by["keep"]["kind"] == "folder" and by["keep"]["facts"]["files"] == 1
    assert by["secret"]["kind"] == "excluded" and "facts" not in by["secret"]
    assert {e["name"] for e in env["workspace_facts"]["entries"]} == {"keep", "secret", "script.py"}


def test_projects_nested_in_a_plain_folder_are_found(tmp_path):
    make_repo(tmp_path / "services")                                    # services/repo is a Python project
    (tmp_path / "services" / "web").mkdir()
    (tmp_path / "services" / "web" / "package.json").write_text('{"name": "web"}', encoding="utf-8")
    (tmp_path / "services" / "notes").mkdir()                           # a plain sub-folder is not a project
    (tmp_path / "services" / "legal").mkdir()
    env = build_environment_map(tmp_path, exclude={"services/legal"})
    by = {o["name"]: o["kind"] for o in env["objects"]}
    assert by == {"services/repo": "python_repository", "services/web": "node_repository"}
    make_repo(tmp_path / "apps")
    assert "apps/repo" not in {o["name"] for o in build_environment_map(tmp_path, exclude={"apps"})["objects"]}


def _link_dir(link: Path, target: Path) -> bool:
    """A directory link: a symbolic link where the system allows one, else (Windows) a junction, which needs no rights."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        if os.name != "nt":
            return False
    return subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True).returncode == 0


def test_links_and_junctions_are_never_followed(tmp_path):
    outside = tmp_path / "outside"                          # someone's private files, next to the folder
    outside.mkdir()
    for i in range(5):
        (outside / f"secret_{i}.py").write_text("SECRET = 1\n", encoding="utf-8")
    root = tmp_path / "ws"
    repo = make_repo(root)
    (root / "handbook").mkdir()
    (root / "handbook" / "index.md").write_text("# Handbook\n", encoding="utf-8")
    if not (_link_dir(root / "notes", outside) and _link_dir(repo / "src" / "calc" / "data", outside)
            and _link_dir(root / "handbook" / "loop", root / "handbook")):
        pytest.skip("this system cannot make directory links")
    objects = {o["name"]: o for o in build_environment_map(root)["objects"]}
    assert objects["notes"]["kind"] == "excluded" and objects["notes"]["reason"] == "link"     # shown, never read
    assert objects["handbook"]["facts"]["documents"] == 1                                       # the loop is not walked
    assert objects["repo"]["facts"]["python_files"] == 3                                        # its own files only
    assert set(read_src_files(repo / "src")) == {"src/calc/__init__.py", "src/calc/ops.py"}     # what a model sees
    with throwaway_copy(repo, tmp_path / "scratch") as copy:
        assert (copy / "src" / "calc" / "ops.py").is_file() and not (copy / "src" / "calc" / "data").exists()
    ws = Workspace(root)
    assert ws._safe_rel("notes/secret_0.py") is None                                            # no draft writes through it
    through = "src/calc/data/secret_0.py"                                                       # nor a fix
    ExperienceStore(ws.home / "experience").add(
        key="loop-link-0001", opportunity={"repo": str(repo), "failing_tests": ["tests/test_ops.py::test_add"], "issue": "x"},
        parent_src={through: "SECRET = 1\n"}, record={"status": "public_pass", "strict_success": True}, final={through: "SECRET = 2\n"})
    refused = ws.apply_proposal("loop-link-0001")
    assert refused["ok"] is False and refused["outside"] == [through]
    assert (outside / "secret_0.py").read_text(encoding="utf-8") == "SECRET = 1\n"


def test_measurements_are_kept_while_an_object_is_unchanged(tmp_path):
    repo = make_repo(tmp_path)
    measured = build_environment_map(repo, probe=True, scratch=tmp_path / "scratch")
    [obj] = measured["objects"]
    assert obj["probe"]["failed"] >= 1 and obj["measured_utc"]
    quick = build_environment_map(repo, previous=measured)
    assert quick["objects"][0]["probe"] == obj["probe"] and quick["objects"][0]["measured_utc"] == obj["measured_utc"]
    assert any("keep the test measurements" in u for u in quick["unknowns"])
    (repo / "src" / "calc" / "ops.py").write_text("def add(a, b):\n    return a + b\n\n\ndef double(x):\n    return add(x, x)\n",
                                                encoding="utf-8")
    changed = build_environment_map(repo, previous=quick)
    assert changed["objects"][0]["probe"] is None and any("not probed" in u for u in changed["unknowns"])


def test_text_documents_count_as_documents(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "ideas.txt").write_text("bread\n", encoding="utf-8")
    [obj] = build_environment_map(tmp_path)["objects"]
    assert obj["kind"] == "document_collection" and obj["facts"]["documents"] == 1
    assert {r["rung"]: r["status"] for r in obj["ladder"]}["documents_present"] == "achieved"


def test_discovery_says_why_tests_could_not_run(tmp_path):
    from runesmith.discover import discover
    repo = tmp_path / "netthing"
    (repo / "src" / "netthing").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "netthing" / "__init__.py").write_text("VERSION = 1\n", encoding="utf-8")
    (repo / "tests" / "test_net.py").write_text("import requests_totally_missing\n\n\ndef test_x():\n    assert True\n",
                                               encoding="utf-8")
    found = discover(repo, scratch=tmp_path / "scratch")
    assert found["status"] == "error_without_failures" and found["opportunities"] == []
    assert "No module named 'requests_totally_missing'" in found["detail"]
    assert found["triage"]["kind"] == "environment" and str(tmp_path) not in found["detail"]


def test_a_static_website_gets_its_own_ladder(tmp_path):
    site = tmp_path / "site"
    (site / "img").mkdir(parents=True)
    (site / "img" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    (site / "index.html").write_text('<html><head><title>Bakery</title><link rel="stylesheet" href="style.css"></head>'
                                     '<body><img src="img/logo.svg"><a href="order.html">Order</a>'
                                     '<a href="https://example.org">x</a></body></html>', encoding="utf-8")
    (site / "style.css").write_text("body{}", encoding="utf-8")
    [obj] = build_environment_map(site)["objects"]                       # the workspace is the website
    assert obj["kind"] == "website" and obj["facts"]["pages"] == 1 and obj["facts"]["broken_references"] == 1
    rungs = {r["rung"]: r["status"] for r in obj["ladder"]}
    assert rungs["styles_present"] == "achieved" and rungs["mobile_ready"] == "not_achieved"
    assert obj["next_rung"] == "mobile_ready" and {o["id"]: o["band"] for o in obj["objectives"]}["links_resolve"] == "bad"


def test_the_studio_interface_is_not_part_of_the_kernel_digest(tmp_path):
    from runesmith.canon import digest_tree
    files = digest_tree(generations.PACKAGE_ROOT, suffixes=(".py",))
    assert any(p.startswith("app/") for p in files)
    kernel = {p for p in files if not p.startswith(generations.NOT_KERNEL)}
    assert not any(p.startswith(("app/", "organs/")) for p in kernel)


# --------------------------------------------------------------- workspace --

def test_a_new_studio_home_starts_without_models_and_validates_settings(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.config()["instruments"] == {} and ws.ready()["any"] is False
    assert (ws.home / ".gitignore").read_text(encoding="utf-8").strip().endswith("*")
    assert ws.settings()["workspace_name"] == tmp_path.name
    assert ws.update_settings({"interval_minutes": 15, "autonomy": "observe"})["autonomy"] == "observe"
    for bad in ({"autonomy": "rampage"}, {"interval_minutes": 0}, {"nope": 1}, {"read_notes": "yes"}, {"max_objects": True}):
        with pytest.raises(WorkspaceError):
            ws.update_settings(bad)
    goal = ws.add_goal("ship it")
    assert ws.update_goal(goal["id"], {"status": "done"})["status"] == "done"
    ws.remove_goal(goal["id"])
    assert ws.goals() == []
    assert ws.ledger.verify()["ok"]


def test_keys_are_saved_but_never_listed_and_roles_decide_readiness(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(WorkspaceError):
        ws.save_instrument("router", {"kind": "openai", "preset": "openrouter", "model": "x"}, "sk-secret")   # no endpoint
    saved = ws.save_instrument("router", {"kind": "openai", "preset": "openrouter", "base_url": "https://openrouter.ai/api/v1",
                                          "model": "openai/gpt-oss-20b"}, "sk-secret-value", roles=["repair"])
    assert saved["key"]["saved"] and "sk-secret-value" not in json.dumps(ws.inference())
    assert "sk-secret-value" not in (ws.home / "runesmith.json").read_text(encoding="utf-8")
    assert ws.ready()["repair"] and ws.ready()["plan_source"] == "repair"             # the planner borrows a model
    assert set(ws.router().roles) == {"repair", "plan"}
    ws.keys.delete("router")
    assert not ws.ready()["repair"]                                                     # a missing key is not ready
    ws.remove_instrument("router")
    assert ws.config()["roles"]["repair"] == [] and not ws.keys.has("router")


def test_a_skipped_model_leaves_every_role_including_the_planners_borrowed_one(tmp_path):
    ws = Workspace(tmp_path)
    for name in ("desk", "backup"):
        ws.save_instrument(name, {"kind": "openai", "base_url": "http://127.0.0.1:9", "model": "m"}, roles=["repair"])
    assert ws.router().roles["repair"] == ["desk", "backup"] and ws.router().roles["plan"] == ["desk", "backup"]
    router = ws.router(skip={"desk"})
    assert router.roles["repair"] == ["backup"] and router.roles["plan"] == ["backup"] and "desk" not in router.instruments


def test_applying_a_fix_checks_for_conflicts_keeps_crlf_and_undoes_exactly(tmp_path):
    ws = Workspace(tmp_path)
    repo = make_repo(tmp_path)
    ops = repo / "src" / "calc" / "ops.py"
    ops.write_bytes(ops.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))    # a Windows-style file
    original = ops.read_bytes()
    key = fake_proposal(ws, repo)
    assert ws.work()["counts"] == {"waiting": 1}
    result = ws.apply_proposal(key)
    assert result["ok"] and b"return a + b\r\n" in ops.read_bytes() and b"\n\n" not in ops.read_bytes().replace(b"\r\n", b"")
    assert ws.apply_proposal(key)["ok"] is False                                        # not twice
    from runesmith.proposals import list_proposals, write_proposals                     # the terminal agrees
    assert [p["state"] for p in list_proposals(ws.home)] == ["applied"]
    assert write_proposals(ws.home, tmp_path / "patches") == []                         # no stale patch is handed out
    assert ws.undo_proposal(key)["ok"] and ops.read_bytes() == original                 # byte for byte
    ops.write_bytes(original + b"# owner edit\r\n")
    refused = ws.apply_proposal(key)
    assert refused["ok"] is False and refused["conflicts"] == ["src/calc/ops.py"]      # the owner changed the file
    assert ops.read_bytes() == original + b"# owner edit\r\n"
    assert ws.reject_proposal(key, "wrong approach")["ok"]
    assert ws.notes.for_target("proposal", key)[0]["text"] == "Rejected: wrong approach"


def test_a_file_with_a_byte_order_mark_is_read_parsed_and_written_back_with_it(tmp_path):
    import ast
    from runesmith.objects.code import BOM, encode_like, read_src_files
    repo = make_repo(tmp_path)
    ops = repo / "src" / "calc" / "ops.py"
    ops.write_bytes(BOM + ops.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    text = read_src_files(repo / "src")["src/calc/ops.py"]
    assert not text.startswith("﻿") and "\r" not in text
    ast.parse(text)                                                          # organs can index it
    assert encode_like(text, ops.read_bytes()) == ops.read_bytes()           # the same bytes back
    ws = Workspace(tmp_path)
    original = ops.read_bytes()
    key = fake_proposal(ws, repo)
    assert ws.apply_proposal(key)["ok"]
    assert ops.read_bytes().startswith(BOM) and b"return a + b\r\n" in ops.read_bytes()
    assert ws.undo_proposal(key)["ok"] and ops.read_bytes() == original


def test_drafts_refuse_unsafe_paths_and_never_overwrite_silently(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "README.md").write_text("mine\n", encoding="utf-8")
    draft = ws.save_draft(title="first files", why="start", drafted_by="test", files=[
        {"path": "app/main.py", "content": "print('hi')\n"}, {"path": "README.md", "content": "theirs\n"},
        {"path": "../escape.py", "content": "x"}, {"path": ".runesmith/runesmith.json", "content": "{}"},
        {"path": "C:/abs.py", "content": "x"}, {"path": ".git/config", "content": "x"}, {"path": "/root.py", "content": "x"}])
    assert [f["path"] for f in draft["files"]] == ["app/main.py", "README.md"] and len(draft["refused"]) == 5
    first = ws.apply_draft(draft["id"])
    assert first["ok"] is False and first["conflicts"] == ["README.md"] and not (tmp_path / "app").exists()
    assert ws.apply_draft(draft["id"], overwrite=True)["ok"]
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "theirs\n"
    assert ws.undo_draft(draft["id"])["ok"]
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "mine\n" and not (tmp_path / "app" / "main.py").exists()
    with pytest.raises(WorkspaceError):
        ws.save_draft(title="bad", why="", drafted_by=None, files=[{"path": "../x", "content": "x"}])


def test_the_link_doctor_drafts_edits_that_apply_only_onto_the_version_they_were_made_from(tmp_path):
    docs = tmp_path / "docs"
    (docs / "guide").mkdir(parents=True)
    (docs / "guide" / "setup.md").write_text("# Setup\n", encoding="utf-8")
    (docs / "README.md").write_text("# Docs\n- [setup](setup.md#install)\n- [gone](nowhere-at-all.md)\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    ws.map_environment(probe=False)
    result = ws.suggest_link_fixes()
    assert result["draft"] and [f["change"] for f in result["fixed"]] == ["setup.md#install → guide/setup.md#install"]
    assert [u["target"] for u in result["unresolved"]] == ["nowhere-at-all.md"]
    draft = next(d for d in ws.drafts() if d["id"] == result["draft"])
    assert draft["files"][0]["path"] == "docs/README.md" and "+- [setup](guide/setup.md#install)" in draft["files"][0]["diff"]
    (docs / "README.md").write_text("# Docs (edited)\n- [setup](setup.md#install)\n", encoding="utf-8")
    assert ws.apply_draft(result["draft"])["conflicts"] == ["docs/README.md"]      # the owner changed it meanwhile
    (docs / "README.md").write_text("# Docs\n- [setup](setup.md#install)\n- [gone](nowhere-at-all.md)\n", encoding="utf-8")
    assert ws.apply_draft(result["draft"])["ok"]
    assert "[setup](guide/setup.md#install)" in (docs / "README.md").read_text(encoding="utf-8")
    assert ws.map_environment(probe=False)                                            # and the map sees one fewer
    assert ws.undo_draft(result["draft"])["ok"] and "(setup.md#install)" in (docs / "README.md").read_text(encoding="utf-8")


def test_the_link_doctor_does_not_guess_generic_names(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# Top\n", encoding="utf-8")
    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / "docs" / "guide.md").write_text("[api](../services/api/README.md) [billing](../services/billing/README.md)\n",
                                                encoding="utf-8")
    (tmp_path / "services" / "api" / "README.md").write_text("# API\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text("[api](../services/api/readme.md) [billing](../services/billing/README.md)\n",
                                                encoding="utf-8")
    ws = Workspace(tmp_path)
    ws.map_environment(probe=False)
    result = ws.suggest_link_fixes()
    assert [f["change"] for f in result["fixed"]] == ["../services/api/readme.md → ../services/api/README.md"]
    assert [u["target"] for u in result["unresolved"]] == ["../services/billing/README.md"]   # not ../README.md


def test_a_link_that_only_works_on_a_case_insensitive_disk_is_broken_and_fixed(tmp_path):
    from runesmith.envmap import document_object
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "FAQ.md").write_text("# FAQ\n", encoding="utf-8")
    (docs / "README.md").write_text("# Docs\n[faq](faq.md)\n", encoding="utf-8")
    facts = document_object(docs)["facts"]
    assert facts["broken_links"] == 1                                    # on Windows it opens; on a web server it does not
    ws = Workspace(tmp_path)
    ws.map_environment(probe=False)
    result = ws.suggest_link_fixes()
    assert [f["change"] for f in result["fixed"]] == ["faq.md → FAQ.md"]


def test_notes_travel_with_the_work_they_are_about(tmp_path):
    ws = Workspace(tmp_path)
    ws.add_note("object", "calc", "keep the public API unchanged", "calc")
    ws.add_note("objective", "calc/tests_green", "flaky test_net is known", "calc: tests green")
    ws.add_note("object", "other", "unrelated", "other")
    ws.add_note("self", "runesmith", "prefer reading the traceback first", "Runesmith")
    text = ws.notes_for_object("calc")
    assert "keep the public API unchanged" in text and "flaky test_net" in text and "unrelated" not in text
    assert "prefer reading the traceback" in ws.notes_for_self()
    ws.update_settings({"read_notes": False})
    assert ws.notes_for_object("calc") == "" and ws.notes_for_self() == ""


def test_the_library_generation_is_adopted_only_through_a_trial(tmp_path):
    ws = Workspace(tmp_path)
    active = generations.active(ws.home)
    [entry] = ws.library()
    result = ws.adopt_from_library(entry["id"])
    assert result["ok"] and result["trial"]["opened"]
    assert generations.active(ws.home) == active                                        # not switched on
    view = ws.generations_view()
    assert view["trial"]["candidate"] == result["id"] and ws.library()[0]["imported_as"] == result["id"]
    assert ws.generation_name(result["id"]) == entry["name"]
    assert ws.adopt_from_library(entry["id"])["ok"] is False                            # once
    owner = ws.activate_generation(result["id"])                                        # the owner's own choice
    assert owner["ok"] and owner["trial_closed"] == result["id"] and ws.generations_view()["trial"] is None
    assert [t["decision"] for t in ws.generations_view()["closed_trials"]] == ["closed_by_owner"]
    assert ws.activate_generation(active)["ok"] and generations.active(ws.home) == active   # and back


# ----------------------------------------------------------- planner/worker --

def test_the_planner_drafts_a_plan_and_first_files_through_any_model(tmp_path):
    ws = Workspace(tmp_path)
    ws.set_brief("A tiny todo app for my family.")
    plan_answer = {"summary": "A todo app.", "tracks": [{"name": "Foundation", "purpose": "basics"}],
                   "milestones": [{"title": "A list you can add to", "track": "Foundation", "done_when": "items persist"}],
                   "first_steps": ["write the page"], "questions": ["phone or computer?"]}
    draft_answer = {"title": "The first page", "why": "a start",
                    "files": [{"path": "todo/index.html", "purpose": "the page", "content": "<h1>Todo</h1>\n"}]}
    scripted(ws, [plan_answer, draft_answer], roles=("plan",))
    router = ws.router()                                    # one scripted instrument answers both calls in order
    plan = draft_plan(ws, router)
    assert plan["milestones"][0]["title"] == "A list you can add to" and plan["version"] == 1
    draft = draft_files(ws, router, None)
    assert draft["files"][0]["path"] == "todo/index.html" and draft["verified"] is False
    assert not (tmp_path / "todo").exists()                                              # drafts wait for the owner
    # a skipped relay request, or half an answer, never replaces the plan the owner has
    scripted(ws, [{"skipped_by_owner": True}, {"summary": "half an answer"}], roles=("plan",))
    router = ws.router()
    with pytest.raises(SkippedByOwner):
        draft_plan(ws, router)
    with pytest.raises(PlannerUnavailable):
        draft_plan(ws, router)
    assert ws.plan()["version"] == 1 and ws.plan()["milestones"][0]["title"] == "A list you can add to"


def test_a_worker_round_finds_repairs_and_proposes_with_the_owners_notes(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    make_repo(workspace)                                         # workspace/repo, with add() broken
    ws = Workspace(workspace)
    ws.update_settings({"onboarded": True, "auto_work": False, "kaizen": False})
    scripted(ws, FIX_ANSWERS)
    ws.add_note("object", "repo", "the bug is in add, not in the tests", "repo")
    bus = EventBus()
    seen: list[str] = []
    sub = bus.subscribe()
    worker = Worker(ws, bus)
    worker.start()
    try:
        worker.enqueue("round")
        deadline = time.time() + 180
        while time.time() < deadline and not any(j["kind"] == "round" for j in worker.history):
            time.sleep(0.2)
        job = next(j for j in worker.history if j["kind"] == "round")
    finally:
        worker.close()
    while not sub.empty():
        seen.append(sub.get_nowait()["kind"])
    assert job["result"] == "done", job
    work = ws.work()
    assert work["counts"] == {"waiting": 1} and work["last_round"]["accepted"] == 1
    [session] = ws.sessions()
    assert "Operator notes" in session["issue"] and "the bug is in add" in session["issue"]
    assert {"worker", "log", "round", "step"} <= set(seen)
    assert "return a - b" in (workspace / "repo" / "src" / "calc" / "ops.py").read_text(encoding="utf-8")   # untouched
    # the map's test dot follows what happened since the round: a fix applied, then a fresh measurement
    assert ws.object_statuses()["repo"] == "failing"
    [proposal] = work["proposals"]
    assert proposal["object"] == "repo"
    time.sleep(1.1)                                                   # timestamps are to the second
    assert ws.apply_proposal(proposal["key"])["ok"]
    assert ws.object_statuses()["repo"] == "fix_applied"
    time.sleep(1.1)
    ws.map_environment(probe=True)
    assert ws.object_statuses()["repo"] == "green"
    assert ws.ledger.verify()["ok"]


# ------------------------------------------------------------------ server --

@pytest.fixture()
def studio(tmp_path, monkeypatch):
    from runesmith.app import server
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path / 'profile')
    s = Studio(tmp_path)
    httpd = bind(s, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield s
    s.closing = True
    s.close()
    httpd.shutdown()
    httpd.server_close()


def call(s: Studio, method: str, path: str, body=None, *, cookie=True, headers=None):
    head = {"Content-Type": "application/json", 'X-Runesmith-Workspace': s.epoch}
    if method != "GET":
        head["X-Runesmith"] = "1"
    if cookie:
        head["Cookie"] = f"rs_session={s.token}"
    head.update(headers or {})
    request = Request(f"http://127.0.0.1:{s.port}{path}", data=json.dumps(body).encode() if body is not None else None,
                      headers=head, method=method)
    try:
        with urlopen(request, timeout=30) as reply:
            return reply.status, json.loads(reply.read() or b"null"), dict(reply.headers)
    except HTTPError as error:
        return error.code, json.loads(error.read() or b"null"), dict(error.headers)


def test_the_server_answers_only_its_owner(studio):
    assert call(studio, "GET", "/api/state", cookie=False)[0] == 401
    status, body, _ = call(studio, "GET", "/api/state")
    assert status == 200 and body["workspace"]["path"] == str(studio.ws.root)
    conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=10)             # DNS rebinding: wrong Host
    conn.request("GET", "/api/state", headers={"Host": "evil.example:80", "Cookie": f"rs_session={studio.token}"})
    assert conn.getresponse().status == 421
    assert call(studio, "POST", "/api/goals", {"text": "x"}, headers={"X-Runesmith": ""})[0] == 403
    assert call(studio, "POST", "/api/goals", {"text": "x"}, headers={"Origin": "http://evil.example"})[0] == 403
    conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=10)             # the launcher's link
    conn.request("GET", f"/?t={studio.token}")
    reply = conn.getresponse()
    assert reply.status == 303 and "HttpOnly" in reply.getheader("Set-Cookie") and "SameSite=Strict" in reply.getheader("Set-Cookie")
    conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=10)
    conn.request("GET", "/?t=wrong")
    assert conn.getresponse().getheader("Set-Cookie") is None
    for length in ("abc", "-1"):                    # a broken or negative Content-Length: an answer, not a hang
        conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=10)
        conn.putrequest("POST", "/api/goals")
        for key, value in (("Cookie", f"rs_session={studio.token}"), ("X-Runesmith", "1"), ("Content-Length", length)):
            conn.putheader(key, value)
        conn.endheaders()
        assert conn.getresponse().status == 400


def test_one_studio_per_folder_and_one_listener_per_port(tmp_path):
    from runesmith.app.server import InstanceLock, QuietServer
    first = InstanceLock(tmp_path / "home")
    assert first.acquire() and not InstanceLock(tmp_path / "home").acquire()      # a second launch waits for the first
    first.handle.close()
    assert InstanceLock(tmp_path / "home").acquire()                               # gone with its process: free again
    one = QuietServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    try:
        with pytest.raises(OSError):                     # Windows' SO_REUSEADDR would have let two share the port
            QuietServer(("127.0.0.1", one.server_address[1]), http.server.BaseHTTPRequestHandler)
    finally:
        one.server_close()


def test_the_server_serves_the_app_and_its_api(studio):
    conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=10)
    conn.request("GET", "/")
    reply = conn.getresponse()
    assert reply.status == 200 and b"Runesmith Studio" in reply.read() and "script-src 'self'" in reply.getheader("Content-Security-Policy")
    for path in ("/static/js/app.js", "/static/app.css", "/static/js/views/map.js", "/cinema"):
        conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=10)
        conn.request("GET", path)
        assert conn.getresponse().status == 200, path
    for path in ("/static/../workspace.py", "/static/%2e%2e/server.py"):
        conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=10)
        conn.request("GET", path)
        assert conn.getresponse().status == 404, path
    for path in ("/api/genesis", "/api/map/environment", "/api/map/self", "/api/map/development", "/api/map/operations",
                 "/api/work", "/api/improve", "/api/notes", "/api/manual", "/api/activity", "/api/health", "/api/plan",
                 "/api/inference", "/api/brief", "/api/goalposts", "/api/workspaces", "/api/browse"):
        assert call(studio, "GET", path)[0] == 200, path
    status, body, _ = call(studio, "POST", "/api/genesis", {"name": "Moonlight", "description": "Bread for neighbours",
                                                            "use_type": "build"})
    assert status == 200 and body["settings"]["onboarded"] and body["settings"]["workspace_name"] == "Moonlight"
    assert "Bread for neighbours" in studio.ws.brief()["text"] and studio.ws.goals()[0]["kind"] == "vision"
    assert call(studio, "POST", "/api/settings", {"interval_minutes": -3})[0] == 400
    assert call(studio, "POST", "/api/proposals/nope/apply", {})[0] == 404
    assert call(studio, "GET", "/api/nothing")[0] == 404
