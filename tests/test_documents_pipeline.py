"""A folder of documents can be drafted, created and verified once the owner shares it (journey J4-G3).

Code goes to models as source; documents never do unless the owner ticks them on Goals & plan. A ticked document shares
its folder with the build pipeline as local verification inputs, so a draft may edit it or add a page beside it, and the
owner's acceptance checks run on a copy that holds them. Only ticked documents' text is ever sent to a model.
"""
from __future__ import annotations

import json

from runesmith.app.acceptance_examples import validate_examples
from runesmith.app.building import build_step, verify_draft
from runesmith.app.planner import source_context
from runesmith.app.snapshots import collect_snapshot, path_kind
from runesmith.app.workspace import Workspace
from test_studio import scripted

INDEX = "# Recipes\n\n- [Rye](rye.md)\n"
EDIT = {"title": "Seeded loaf in the index", "why": "Every recipe reachable", "files": [
    {"path": "recipes/index.md", "purpose": "link the seeded loaf",
     "edits": [{"old_text": "- [Rye](rye.md)\n", "new_text": "- [Rye](rye.md)\n- [Seeded loaf](seeded-loaf.md)\n"}]},
    {"path": "shop/pickup.md", "purpose": "a destination for the ordering link",
     "content": "# Pickup\n\nOrders are collected during opening hours.\n\n[Back](ordering.md)\n"}]}


def handbook(tmp_path):
    root = tmp_path / "Bakery handbook"
    for rel, text in {"README.md": "# Handbook\n\n[Recipes](recipes/index.md) · [Orders](shop/ordering.md)\n",
                      "recipes/index.md": INDEX, "recipes/rye.md": "# Rye\n\n[Back](index.md)\n",
                      "recipes/seeded-loaf.md": "# Seeded loaf\n\n[Back](index.md)\n",
                      "shop/ordering.md": "# Orders\n\nSee [pickup](pickup.md).\n",
                      "private/notes.md": "# Private\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    ws = Workspace(root)
    ws.save_plan({"summary": "Tidy handbook", "milestones": [{"title": "Every recipe reachable",
        "detail": "Add the seeded loaf to recipes/index.md (seeded-loaf.md) and give the ordering link a pickup page.",
        "done_when": "recipes/index.md links to seeded-loaf.md and every page can be reached.", "status": "open"}]})
    return ws


def test_only_folders_with_a_shared_document_enter_the_snapshot_and_models_still_see_no_document(tmp_path):
    ws = handbook(tmp_path)
    assert collect_snapshot(ws)["files"] == {}                           # nothing shared: no document is an input
    ws.set_brief(blueprints=["recipes/index.md", "shop/ordering.md"])
    snapshot = collect_snapshot(ws)
    assert sorted(snapshot["files"]) == ["recipes/index.md", "recipes/rye.md", "recipes/seeded-loaf.md", "shop/ordering.md"]
    assert set(snapshot["policy"]["declared_documents"]) == {"recipes/", "shop/"}
    assert path_kind("shop/pickup.md", snapshot["policy"]["declared_documents"]) == "local"    # a new page there
    assert path_kind("private/notes.md", snapshot["policy"]["declared_documents"]) is None     # never shared
    assert source_context(ws, snapshot=snapshot)["files"] == {}          # verification input, not model context


def test_a_draft_for_documents_is_judged_by_the_owners_checks_and_unchecked_without_them(tmp_path):
    ws = handbook(tmp_path)
    ws.set_brief(blueprints=["README.md", "recipes/index.md", "shop/ordering.md"])
    ws.update_settings({"build_steps": True})
    scripted(ws, [EDIT, EDIT], roles=("plan",))
    unchecked = build_step(ws, ws.router())
    assert unchecked["verification"]["status"] == "unchecked", unchecked["verification"].get("detail")
    assert unchecked["verification"]["project_checks"]["status"] == "not_applicable"
    assert not unchecked["verification"].get("acceptance")

    checks = validate_examples({"examples": [
        {"name": "index", "says": "The index links the seeded loaf.", "contains": [{"name": "recipes/index.md", "texts": ["seeded-loaf.md"]}]},
        {"name": "reachable", "says": "Every page can be reached, and every link leads somewhere.", "pages_reachable": True,
         "links_resolve": True}]}, ws.plan()["milestones"][0]["detail"])
    (ws.home / "acceptance").mkdir(parents=True, exist_ok=True)
    (ws.home / "acceptance" / "m1.py").write_text(checks["code"], encoding="utf-8")
    draft = next(d for d in ws.drafts() if d["id"] == unchecked["draft"])
    verified = verify_draft(ws, draft)
    assert verified["status"] == "acceptance_passed", json.dumps(verified.get("acceptance"), default=str)[:1500]
    assert not (ws.root / "shop" / "pickup.md").exists()                # checked on a copy; nothing written


def test_a_python_project_without_tests_still_fails_instead_of_passing_unchecked(tmp_path):
    ws = Workspace(tmp_path)
    ws.save_plan({"summary": "Tool", "milestones": [{"title": "Answer", "done_when": "answer() returns 42"}]})
    ws.update_settings({"build_steps": True})
    scripted(ws, [{"title": "No tests", "files": [{"path": "app.py", "content": "def answer():\n    return 42\n"}]}],
             roles=("plan",))
    result = build_step(ws, ws.router())
    assert result["verification"]["status"] == "failed"
