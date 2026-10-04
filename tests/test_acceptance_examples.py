"""Acceptance checks from examples: the model describes examples as data, Runesmith's trusted template writes the code.

Free models' own check code rejected correct builds in 16 of 17 overnight trials (2026-09-28). These tests hold the
template to the rule those checks broke: fail before the milestone and on broken builds, pass on every correct build,
however it words its output.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from runesmith.app.acceptance_examples import validate_examples
from runesmith.app.acceptance_proposals import acceptance_file, approve, findings, propose, status, validate
from runesmith.app.building import _run_checks
from runesmith.app.workspace import Workspace, WorkspaceError

T = ["python", "-m", "tally"]
MILESTONE = ("Months: python -m tally months prints how many entries each month (YYYY-MM) has, in order. Saving is safe "
             "from interruption, and a damaged file gives a clear message and is left untouched.")


def add(name, day):
    return {"run": T + ["add", name, day]}


EXAMPLES = {"examples": [
    {"name": "counts per month", "says": "Each month shows how many entries it has, oldest month first.",
     "steps": [add("Tea", "2026-01-05"), add("Cake", "2026-01-20"), add("Pie", "2026-03-02"),
               {"run": T + ["months"], "expect": {"lines": [{"has": "2026-01", "number": 2}, {"has": "2026-03", "number": 1}],
                                                   "order": ["2026-01", "2026-03"]}}]},
    {"name": "interrupted save", "says": "If saving is interrupted, what was saved before is still there.",
     "steps": [add("Old", "2026-01-01"), dict(add("New", "2026-01-02"), fault="interrupted_write"),
               {"run": T + ["list"], "expect": {"shows": ["Old"]}}]},
    {"name": "damaged file", "says": "A damaged file gives a clear message and is left as it was.",
     "files": [{"name": "tally.json", "text": '[{"name": "Ha'}],
     "steps": [{"run": T + ["list"], "expect": {"message": True}}], "unchanged": ["tally.json"]}]}


def program(*, months=True, safe=True, damaged=True, off_by_one=False, wordy=False):
    """A tiny tally CLI. The flags make the project as it is before the milestone, correct builds and broken ones."""
    save = ('    temporary = FILE + ".tmp"\n    with open(temporary, "w", encoding="utf-8") as handle:\n'
            '        handle.write(json.dumps(items))\n    os.replace(temporary, FILE)\n') if safe else (
            '    with open(FILE, "w", encoding="utf-8") as handle:\n        handle.write(json.dumps(items))\n')
    load = ('        try:\n            return json.load(handle)\n        except ValueError:\n'
            '            print("tally.json is damaged, so nothing was changed.", file=sys.stderr)\n            sys.exit(3)\n'
            ) if damaged else '        return json.load(handle)\n'
    line = ('f"In {month} you logged {count} entries"' if wordy else 'f"{month}: {count}"')
    report = (f'    if argv[0] == "months":\n        counts = {{}}\n        for item in load():\n'
              f'            counts[item["on"][:7]] = counts.get(item["on"][:7], 0) + 1\n'
              f'        for month in sorted(counts):\n            count = counts[month]{" + 1" if off_by_one else ""}\n'
              f'            print({line})\n        return 0\n') if months else ''
    return ('import json, os, sys\nFILE = "tally.json"\n\n\ndef load():\n    if not os.path.exists(FILE):\n        return []\n'
            '    with open(FILE, encoding="utf-8") as handle:\n' + load + '\n\ndef save(items):\n' + save +
            '\n\ndef main(argv):\n    if argv[0] == "add":\n        items = load()\n'
            '        items.append({"name": argv[1], "on": argv[2]})\n        save(items)\n        print("Added", argv[1])\n'
            '        return 0\n    if argv[0] == "list":\n        for item in load():\n            print(item["on"], item["name"])\n'
            '        return 0\n' + report + '    print("unknown command", file=sys.stderr)\n    return 2\n\n\n'
            'sys.exit(main(sys.argv[1:]))\n')


def project(folder: Path, readme=None, **flags):
    (folder / "tally").mkdir(parents=True)
    (folder / "tally" / "__init__.py").write_text("", encoding="utf-8")
    (folder / "tally" / "__main__.py").write_text(program(**flags), encoding="utf-8")
    if readme is not None:
        (folder / "README.md").write_text(readme, encoding="utf-8")
    return folder


def run(tmp_path, name, code, **flags):
    stage = project(tmp_path / name / "project", **flags)
    checks = tmp_path / name / "acceptance.py"
    checks.write_text(code, encoding="utf-8")
    return _run_checks(stage, json.dumps([str(checks)]), tmp_path / name / "log.txt", timeout_s=240)


def test_the_rendered_checks_fail_before_and_on_broken_builds_and_pass_on_every_correct_build(tmp_path):
    shaped = validate_examples(EXAMPLES, MILESTONE)
    assert shaped["dropped"] == [] and "runesmith" not in shaped["code"].split("EXAMPLES =")[0].split('"""', 2)[2]
    from runesmith.app.acceptance_examples import HARNESS
    from runesmith.app.acceptance_proposals import MAX_CODE
    # As proposals do: the limit leaves room for Runesmith's own template (journey J11-B12).
    validate({"checks": [{"test": c["test"], "says": c["says"]} for c in shaped["checks"]], "code": shaped["code"]},
             limit=MAX_CODE + len(HARNESS))
    verdicts = {name: run(tmp_path, name, shaped["code"], **flags) for name, flags in {
        "before": {"months": False, "safe": False, "damaged": False},
        "correct": {}, "correct_worded_differently": {"wordy": True},
        "counts_wrong": {"off_by_one": True}, "saves_unsafely": {"safe": False}, "damaged_overwritten": {"damaged": False},
    }.items()}
    assert {n: v["ok"] for n, v in verdicts.items()} == {
        "before": False, "correct": True, "correct_worded_differently": True,
        "counts_wrong": False, "saves_unsafely": False, "damaged_overwritten": False}, {
        n: v.get("output", "")[-600:] for n, v in verdicts.items()}
    assert verdicts["before"]["failures"] + verdicts["before"]["errors"] == 3      # every example fails before


def test_document_examples_must_mention_each_command_and_run_as_written(tmp_path):
    answer = {"examples": [{"name": "readme", "says": "The README shows add and months, and its examples work.",
                            "steps": [{"doc": "README.md", "program": T, "mention": ["add", "months"]}]}]}
    code = validate_examples(answer, MILESTONE, source_text='if argv[0] == "add"')["code"]
    good = ("# Tally\n\n    python -m tally add Tea 2026-01-05\n\nIn general: `python -m tally add NAME YYYY-MM-DD`.\n\n"
            "See each month with `python -m tally months`. Run everything with `python -m tally`.\n")
    assert run(tmp_path, "good", code, readme=good)["ok"]
    assert not run(tmp_path, "none", code)["ok"]                                             # no README yet
    assert not run(tmp_path, "unknown", code, readme=good.replace("tally months", "tally count"))["ok"]
    assert not run(tmp_path, "placeholders_only", code, readme="`python -m tally add NAME YYYY-MM-DD`, `python -m tally months --file PATH`\n")["ok"]


def test_links_between_markdown_pages_must_lead_somewhere(tmp_path):
    answer = {"examples": [{"name": "links", "says": "Every link in the handbook leads to a page.",
                            "steps": [{"run": T + ["list"]}], "links_resolve": True}]}
    code = validate_examples(answer, MILESTONE)["code"]
    for name, target, ok in (("ok", "rye.md", True), ("wrong_case", "Rye.md", False), ("missing", "cinnamon-buns.md", False)):
        folder = tmp_path / name
        (folder / "project" / "recipes").mkdir(parents=True)
        (folder / "project" / "recipes" / "rye.md").write_text("# Rye\n", encoding="utf-8")
        (folder / "project" / "index.md").write_text(f"[Rye](recipes/{target}) and [web](https://example.org)\n", encoding="utf-8")
        project(folder / "project")
        checks = folder / "acceptance.py"
        checks.write_text(code, encoding="utf-8")
        assert _run_checks(folder / "project", json.dumps([str(checks)]), folder / "log.txt", timeout_s=120)["ok"] is ok, name


def test_a_python_function_can_be_checked_by_calling_it(tmp_path):
    answer = {"examples": [{"name": "months", "says": "Counting by month works for two entries in one month.",
                            "steps": [{"call": "tally.report.by_month", "args_json": '[["2026-01-05", "2026-01-20"]]',
                                       "expect": {"returns_json": '{"2026-01": 2}'}}]},
                           {"name": "bad date", "says": "A date that is not a date is refused.",
                            "steps": [{"call": "tally.report.by_month", "args_json": '[["soon"]]', "expect": {"raises": "ValueError"}}]}]}
    code = validate_examples(answer, MILESTONE)["code"]
    report = ('def by_month(days):\n    counts = {}\n    for day in days:\n        if len(day) != 10:\n'
              '            raise ValueError("not a date: " + day)\n        counts[day[:7]] = counts.get(day[:7], 0) + 1\n    return counts\n')
    for name, text, ok in (("built", report, True), ("wrong", report.replace("+ 1", "+ 2"), False), ("absent", None, False)):
        folder = tmp_path / name
        project(folder / "project")
        if text:
            (folder / "project" / "tally" / "report.py").write_text(text, encoding="utf-8")
        checks = folder / "acceptance.py"
        checks.write_text(code, encoding="utf-8")
        assert _run_checks(folder / "project", json.dumps([str(checks)]), folder / "log.txt", timeout_s=120)["ok"] is ok, name


def test_wording_the_milestone_never_states_is_loosened_or_dropped_and_the_owner_is_told():
    # The shapes gpt-oss-120b wrote on the first night of examples (2026-09-28): its own guess of each layout.
    answer = {"examples": [{"name": "over specified", "says": "The report shows the months and their counts.",
                            "steps": [dict(add("Tea", "2025-12-05"), expect={"shows": ["Added 'Tea'"]}), add("Pie", "2026-01-05"),
                                      {"run": T + ["months"], "expect": {"shows": ["2026-01 1"], "hides": ["Error"],
                                                                         "order": ["Monthly report", "2025-12 1", "2026-01 1"],
                                                                         "lines": [{"has": "Month 2026-01", "number": 1}]}}]},
                           {"name": "empty", "says": "No books, no months.",
                            "steps": [{"run": T + ["months"], "expect": {"shows": ["No entries yet"]}}]}]}
    shaped = validate_examples(answer, MILESTONE)
    steps = shaped["examples"][0]["steps"]
    assert steps[0]["expect"] == {"shows": ["Tea"]}
    assert steps[2]["expect"] == {"order": ["2025-12", "2026-01"],
                                  "lines": [{"has": "2026-01", "number": 1}, {"has": "2025-12", "number": 1}]}
    assert "expect" not in shaped["examples"][1]["steps"][0]                           # nothing of it was typed in: it runs
    said = [d.split("` ", 1)[1] for d in shaped["dropped"]]
    assert said == ["shows “Added 'Tea'” (checked instead: it shows “Tea”)",
                    "shows “2026-01 1” (checked instead: a line with “2026-01” shows the number 1)",
                    "lists “Monthly report”",
                    "lists “2025-12 1” (checked instead: “2025-12” with the number 1)",
                    "lists “2026-01 1” (checked instead: “2026-01” with the number 1)",
                    "has a line with “Month 2026-01” (checked instead: “2026-01”)",
                    "does not show “Error”", "shows “No entries yet”"]
    exact = shaped["checks"][0]["exact"]
    assert "a line with “2026-01” also shows the number 1" in exact and "“2025-12”, “2026-01” appear in that order" in exact
    assert "2026-01 1”" not in exact and "Added" not in exact


def test_words_typed_in_together_stay_one_phrase_when_loosened():
    # gpt-oss-120b (2026-09-28) expected its own layout of a list line; the title typed in as one argument stays whole.
    answer = {"examples": [{"name": "listed", "says": "A saved entry is listed.",
                            "steps": [add("The Hobbit", "2026-01-14"),
                                      {"run": T + ["list"], "expect": {"shows": ["2026-01-14  The Hobbit by J. R. R. Tolkien"]}}]}]}
    shaped = validate_examples(answer, MILESTONE)
    assert shaped["examples"][0]["steps"][1]["expect"] == {"shows": ["2026-01-14", "The Hobbit"]}


def test_loosened_checks_catch_a_wrong_count_yet_pass_a_correct_build_worded_differently(tmp_path):
    answer = {"examples": [{"name": "counts", "says": "Two entries in January count as 2.",
                            "steps": [add("Tea", "2026-01-05"), add("Pie", "2026-01-09"),
                                      {"run": T + ["months"], "expect": {"shows": ["2026-01: 2 entries"]}}]}]}
    code = validate_examples(answer, MILESTONE)["code"]
    assert run(tmp_path, "worded", code, wordy=True)["ok"] and run(tmp_path, "plain", code)["ok"]
    assert not run(tmp_path, "wrong", code, off_by_one=True)["ok"]


def test_texts_are_matched_whole_so_a_digit_never_matches_inside_a_year(tmp_path):
    answer = {"examples": [{"name": "one", "says": "One entry counts as 1.",
                            "steps": [add("Tea", "2026-01-05"), {"run": T + ["list"], "expect": {"shows": ["2"]}}]}]}
    shaped = validate_examples(answer, "shows 2")
    assert not run(tmp_path, "digit", shaped["code"])["ok"]            # "2026-01-05 Tea" contains no whole "2"


@pytest.mark.parametrize("step, why", [
    ({"run": ["bash", "-c", "rm -rf /"]}, "start with python or node"),
    ({"run": ["python", "-c", "print(1)"]}, "python -m"),
    ({"run": ["python", "-m", "tally", "--file", "C:/Users/x/data.json"]}, "inside the project"),
    ({"run": ["python", "-m", "tally", "../elsewhere"]}, "inside the project"),
    ({"run": ["node", "app.js"], "fault": "interrupted_write"}, "Python program"),
    ({"run": T + ["add", "x", "y"], "fault": "interrupted_write", "expect": {"shows": ["x"]}}, "later step"),
    ({"call": "tally.report.by_month", "args_json": "[]"}, "returns_json"),
    ({"call": "tally._private", "args_json": "[]", "expect": {"raises": "X"}}, "public function"),
    ({"doc": "README.md", "program": T + ["add"]}, "program only"),
    ({"doc": "../README.md", "program": T}, "inside the project"),
    ({"run": T, "call": "tally.a.b"}, "exactly one"),
    ({"run": ["python", "-m", ""]}, "python -m"),                     # an empty word is an argument, never the program
    ({"run": ["", "tally"]}, "start with python or node"),
])
def test_examples_that_break_a_rule_are_refused_with_the_reason(step, why):
    with pytest.raises(WorkspaceError, match=why):
        validate_examples({"examples": [{"name": "x", "says": "x", "steps": [step]}]}, MILESTONE)


def test_an_empty_argument_can_be_given_as_a_person_types_two_quotes(tmp_path):
    # Journey J2-F3: "an empty query is refused" needs `--query ""`, and an empty word was refused as not a word.
    answer = {"examples": [{"name": "empty name", "says": "An entry with an empty name is still listed by its date.",
                            "steps": [{"run": T + ["add", "", "2026-01-05"]},
                                      {"run": T + ["list"], "expect": {"shows": ["2026-01-05"]}}]}]}
    shaped = validate_examples(answer, MILESTONE)
    assert '"add", "", "2026-01-05"' in shaped["code"]
    assert run(tmp_path, "empty", shaped["code"])["ok"]          # dropping the empty word would crash the program


def test_a_long_not_checked_note_is_shortened_and_the_unchanged_rule_is_stated():
    # Journey J2-F8: a 220-character note made Runesmith refuse the whole answer. J2-F7: "unchanged" may only name
    # files the example creates, and the Checker was never told.
    from runesmith.app.acceptance_examples import TASK
    long_note = "That the file holds exactly these books and nothing else, and that reading it back gives the same " \
                "data: the checks look for the header and for each title, author and date, not for the exact row layout."
    answer = {"examples": [{"name": "listed", "says": "An entry is listed.",
                            "steps": [add("Tea", "2026-01-05"), {"run": T + ["list"], "expect": {"shows": ["Tea"]}}]}],
              "not_checked": [long_note, "x " * 300, "", 7]}
    notes = validate_examples(answer, MILESTONE)["not_checked"]
    assert notes[0] == long_note and len(notes) == 2 and len(notes[1]) <= 400 and notes[1].endswith("…")
    assert 'names of files this example creates with "files"' in TASK


def handbook(folder: Path, *, index: str, extra_pages=()):
    """Journey J4's bakery handbook: a front page, a recipe index and recipe pages, and no program to run."""
    (folder / "recipes").mkdir(parents=True)
    (folder / "README.md").write_text("# Moonlight Bakery handbook\n\n[Recipes](recipes/index.md)\n", encoding="utf-8")
    (folder / "recipes" / "index.md").write_text(index, encoding="utf-8")
    for name in ("rye.md", "Seeded-Loaf.md", *extra_pages):
        (folder / "recipes" / name).write_text(f"# {name}\n\n[Back](index.md)\n", encoding="utf-8")
    return folder


DOC_MILESTONE = ("Every recipe is reachable from the recipe index. Add the seeded loaf to recipes/index.md with a link to "
                 "Seeded-Loaf.md. Done when recipes/index.md links to Seeded-Loaf.md and every link leads to a page that exists.")
DOC_EXAMPLES = {"examples": [
    {"name": "seeded loaf in the index", "says": "The recipe index links to the seeded loaf, and every page can be reached.",
     "steps": [], "contains": [{"name": "recipes/index.md", "texts": ["Seeded-Loaf.md", "rye.md"]}], "pages_reachable": True},
    {"name": "no dead links", "says": "Every link in the handbook leads to a page that exists.", "links_resolve": True}]}


def run_docs(tmp_path, name, code, index):
    folder = tmp_path / name
    handbook(folder / "project", index=index)
    checks = folder / "acceptance.py"
    checks.write_text(code, encoding="utf-8")
    return _run_checks(folder / "project", json.dumps([str(checks)]), folder / "log.txt", timeout_s=120)


def test_documents_are_checked_by_their_files_and_links_with_no_program_to_run(tmp_path):
    # J4-G1: a handbook has no program, so an example may check files only; the pages the owner shared count as known text.
    shaped = validate_examples(DOC_EXAMPLES, DOC_MILESTONE, source_text="--- recipes/index.md ---\n[Rye](rye.md)")
    assert shaped["dropped"] == [] and shaped["examples"][0]["steps"] == []
    assert "every Markdown page can be reached by following links from the front page" in shaped["checks"][0]["exact"]
    code = shaped["code"]
    before = "# Recipes\n\n- [Rye](rye.md)\n- [Cinnamon buns](cinnamon-buns.md)\n"
    built = "# Recipes\n\n- [Rye](rye.md)\n- [Seeded loaf](Seeded-Loaf.md)\n- Cinnamon buns (coming soon)\n"
    assert not run_docs(tmp_path, "before", code, before)["ok"]
    assert run_docs(tmp_path, "built", code, built)["ok"]
    assert not run_docs(tmp_path, "wrong_case", code, built.replace("(Seeded-Loaf.md)", "(seeded-loaf.md)"))["ok"]
    assert not run_docs(tmp_path, "dead_link_left", code, built + "- [Buns](cinnamon-buns.md)\n")["ok"]


def test_checks_on_documents_are_tried_even_when_running_project_code_is_off(tmp_path):
    # J4-F13: file-only checks run none of the project's code, so they are tried on today's copy without that switch.
    # J4-F12: and what they check says nothing about Python crash reports.
    ws = Workspace(handbook(tmp_path / "handbook", index="# Recipes\n\n[Rye](rye.md)\n"))
    ws.save_plan({"summary": "Tidy handbook", "milestones": [{"title": "Seeded loaf in the index", "detail": DOC_MILESTONE,
                                                               "done_when": "It is linked.", "status": "open"}]})
    ws.set_brief(blueprints=["README.md", "recipes/index.md"])
    config = ws.config()
    config["instruments"]["offline"] = {"kind": "scripted", "answers": [DOC_EXAMPLES]}
    config["roles"]["plan"] = ["offline"]
    ws.save_config(config)
    assert not ws.settings().get("build_steps")
    proposal = propose(ws, ws.router(), "m1")
    assert proposal["dry_run"]["verdict"] == "fails_now", proposal["dry_run"]      # the seeded loaf is not linked yet
    assert not any("crash report" in c["exact"] for c in proposal["checks"])


def test_an_example_that_runs_nothing_and_checks_no_file_is_refused():
    with pytest.raises(WorkspaceError, match="needs steps, or a check on files"):
        validate_examples({"examples": [{"name": "x", "says": "x", "steps": []}]}, DOC_MILESTONE)


def test_the_checker_reads_the_documents_the_owner_chose_to_share(tmp_path):
    # J4-G2: code goes to models in source_context; documents never do, unless the owner ticks them in Goals & plan.
    from runesmith.app.acceptance_proposals import packet
    ws = Workspace(handbook(tmp_path / "handbook", index="# Recipes\n\n[Rye](rye.md)\n"))
    ws.save_plan({"summary": "Tidy handbook", "milestones": [{"title": "Seeded loaf in the index", "detail": DOC_MILESTONE,
                                                               "done_when": "It is linked.", "status": "open"}]})
    assert packet(ws, "m1", "examples")["documents"] == ""
    ws.set_brief(blueprints=["recipes/index.md"])
    shared = packet(ws, "m1", "examples")["documents"]
    assert "--- recipes/index.md ---" in shared and "[Rye](rye.md)" in shared and "rye.md ---" not in shared


def test_what_an_interrupted_run_prints_is_not_checked_but_what_it_leaves_behind_is():
    # gpt-oss-120b put an expectation on the interrupted run itself, twice (2026-09-28): dropped with a note, not refused.
    answer = {"examples": [{"name": "interrupted", "says": "An interrupted save keeps what was saved before.",
                            "steps": [add("Old", "2026-01-01"),
                                      dict(add("New", "2026-01-02"), fault="interrupted_write", expect={"exit": "error"}),
                                      {"run": T + ["list"], "expect": {"shows": ["Old"]}}]}]}
    shaped = validate_examples(answer, MILESTONE)
    assert "expect" not in shaped["examples"][0]["steps"][1]
    assert shaped["dropped"] == ["Example 1: what `python -m tally add New 2026-01-02` shows while it is interrupted "
                                 "(a later check looks at what it left behind)"]


def test_file_rules_are_refused_with_the_reason():
    one = {"name": "x", "says": "x", "steps": [add("Tea", "2026-01-05")]}
    for example, why in (
            (dict(one, unchanged=["tally.json"]), "only name files the example creates"),
            (dict(one, files=[{"name": "C:/tally.json", "text": "x"}]), "inside the project"),
            (dict(one, files=[{"name": ".git/config", "text": "x"}]), "inside the project")):
        with pytest.raises(WorkspaceError, match=why):
            validate_examples({"examples": [example]}, MILESTONE)
    with pytest.raises(WorkspaceError, match="1-8 examples"):
        validate_examples({"examples": [one] * 9}, MILESTONE)


def workspace(tmp_path, answers):
    root = project(tmp_path / "folder", months=False, safe=False, damaged=False)
    ws = Workspace(root)
    ws.save_plan({"summary": "Tally", "milestones": [{"title": "Months and safety", "detail": MILESTONE,
                                                       "done_when": "Tests show correct counts.", "status": "open"}]})
    config = ws.config()
    config["instruments"]["offline"] = {"kind": "scripted", "answers": list(answers)}
    config["roles"]["plan"] = ["offline"]
    ws.save_config(config)
    ws.update_settings({"build_steps": True})
    return ws


def test_propose_asks_for_examples_retries_an_unusable_answer_once_and_publishes_what_is_checked(tmp_path):
    unusable = {"examples": [{"name": "x", "says": "x", "steps": [{"run": ["bash", "-c", "true"]}]}]}
    ws = workspace(tmp_path, [unusable, EXAMPLES])
    proposal = propose(ws, ws.router(), "m1")
    assert proposal["style"] == "examples" and proposal["revision"]["after"] == "unusable"
    assert proposal["dry_run"]["verdict"] == "fails_now"                   # the trial ran on the project before the milestone
    waiting = status(ws)["m1"]["proposal"]
    assert waiting["style"] == "examples" and waiting["dropped"] == [] and all(c["exact"] for c in waiting["checks"])
    approve(ws, "m1", proposal["id"])
    assert acceptance_file(ws, "m1").is_file()
    criteria = json.loads((ws.home / "ACCEPTANCE_EXPECTATIONS.json").read_text(encoding="utf-8")) \
        if (ws.home / "ACCEPTANCE_EXPECTATIONS.json").is_file() else None
    from runesmith.app.acceptance_contracts import expectations
    described = " ".join(c["description"] for c in expectations(ws, "m1")["criteria"])
    assert "Checked exactly:" in described and "a line with “2026-01” also shows the number 2" in described, criteria


def test_a_check_that_already_passes_today_is_marked_on_its_own(tmp_path):
    # Journey J1-G2: "an unknown item is refused" passed before the milestone, because the command did not exist yet.
    today_passes = {"examples": [
        {"name": "months", "says": "Months are counted.", "steps": [add("Tea", "2026-01-05"),
         {"run": T + ["months"], "expect": {"lines": [{"has": "2026-01", "number": 1}]}}]},
        {"name": "nonsense refused", "says": "A command the program does not know is refused with a message.",
         "steps": [{"run": T + ["weekly"], "expect": {"exit": "error", "message": True}}]}]}
    ws = workspace(tmp_path, [today_passes])
    proposal = propose(ws, ws.router(), "m1")
    assert proposal["dry_run"]["verdict"] == "fails_now"
    marked = {c["test"]: c.get("passes_today", False) for c in proposal["checks"]}
    assert marked == {"test_01_months": False, "test_02_nonsense_refused": True}


def test_a_second_unusable_answer_is_reported_in_plain_words(tmp_path):
    unusable = {"examples": [{"name": "x", "says": "x", "steps": [{"run": ["bash", "-c", "true"]}]}]}
    ws = workspace(tmp_path, [unusable, unusable])
    with pytest.raises(WorkspaceError, match="start with python or node"):
        propose(ws, ws.router(), "m1")


def test_milliner_gets_the_lenient_examples_schema_as_text_not_as_a_forced_schema():
    # Checker experiment 2026-09-28: Gemini refused the schema (400, minItems/maxItems), and Milliner's strict mode
    # made every optional field required, truncating one-example answers. A lenient schema goes into the prompt.
    from runesmith.app.acceptance_examples import SCHEMA
    from runesmith.instruments import LenientSchema, MillinerInstrument
    sent = []

    def gateway(method, url, headers, body, timeout):
        sent.append(body)
        return 200, {"state": "succeeded", "text": '{"examples": []}', "parsed": None, "meta": {}}
    instrument = MillinerInstrument("m", "gemini:flash", base_url="http://localhost:8765", token=lambda: "t",
                                    caller_tag="test", timeout_s=30, transport=gateway)
    assert isinstance(SCHEMA, LenientSchema) and "minItems" not in json.dumps(SCHEMA)
    assert instrument.complete(prompt="Describe examples.", system="s", schema=SCHEMA, max_tokens=100, key="k1").ok
    assert "json_schema" not in sent[-1] and '"examples"' in sent[-1]["system"]
    assert "fields not listed as required are optional" in sent[-1]["system"]
    assert sent[-1]["prompt"] == "Describe examples."                  # the prompt itself is never changed
    assert sent[-1]["json_mode"] is True                                 # valid JSON, without a pinned schema
    plain = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    instrument.complete(prompt="p", system="s", schema=plain, max_tokens=100, key="k2")
    assert sent[-1]["json_schema"] == plain and sent[-1]["prompt"] == "p"          # other schemas: unchanged
    assert "json_mode" not in sent[-1]


def test_a_file_a_step_hands_the_program_that_nothing_creates_is_named_under_its_check():
    # Journey J11-G10: "node motion.mjs position.motion.json --at 1" ran on a file no one made; every correct build
    # failed with ENOENT, and prerequisite s1 used two of its three tries on it.
    source = (json.dumps({"inventory": ["motion.mjs", "sample.motion.json"]}) + ' if (command === "save")'
              ' args.indexOf("--out")')                    # an option the program names (J11-G30)
    milestone = "Make --at optional: node motion.mjs sample.motion.json checks the project."

    def motion(*words, **expect):
        return {"run": ["node", "motion.mjs", *words], "expect": expect or {"exit": "ok"}}
    answer = {"examples": [
        {"name": "checked", "says": "Without --at the project is checked.", "steps": [motion("sample.motion.json")]},
        {"name": "at one", "says": "With --at each property is printed.",
         "steps": [motion("position.motion.json", "--at", "1")]},
        {"name": "made here", "says": "A project the example makes is read.",
         "files": [{"name": "made.motion.json", "text": "{}"}], "steps": [motion("./made.motion.json", "--at", "1")]},
        {"name": "saved then read", "says": "A saved project opens.",
         "steps": [motion("save", "saved.motion.json"), motion("saved.motion.json", "--at", "0")]},
        {"name": "missing on purpose", "says": "A missing file is refused with a message.",
         "steps": [motion("nowhere.motion.json", exit="error", message=True)]},
        {"name": "written", "says": "The frame is written.", "steps": [motion("--at", "0", "--out", "frame.json")]}]}
    # Told while the Checker drafts (J11-CC4): the answer is refused with the file named, and only a caller that cannot
    # tell what the project holds gets the finding under its check.
    with pytest.raises(WorkspaceError, match="Example 2 runs position.motion.json, which neither that example's files"):
        validate_examples(answer, milestone, source_text=source)
    checks = validate_examples(answer, milestone, source_text=source, refuse_missing=False)["checks"]
    assert [c.get("missing_input") for c in checks] == [None, ["position.motion.json"], None, None, None, None]
    assert "missing_input" not in validate_examples(answer, milestone)["checks"][1]          # no project: not judged
    said = " ".join(findings({"dry_run": {"verdict": "fails_now"}, "checks": checks}))
    assert 'test_02_at_one runs the program on "position.motion.json", a file nothing creates' in said, said


def test_a_short_key_of_the_example_s_own_data_is_checked_with_its_number():
    # Journey J11-G12: "x 50" was dropped because "x" is short, so s1's checks passed a program that printed nothing.
    data = '{"timeline": [{"time": 0, "elements": [{"id": "e1", "x": 0}]}, {"time": 2, "elements": [{"id": "e1", "x": 100}]}]}'
    example = {"name": "at one", "says": "Halfway through, x is halfway.", "files": [{"name": "p.motion.json", "text": data}],
               "steps": [{"run": ["node", "motion.mjs", "p.motion.json", "--at", "1"], "expect": {"shows": ["x 50", "a 1"]}}]}
    shaped = validate_examples({"examples": [example]}, "node motion.mjs FILE --at SECONDS prints each property")
    assert shaped["examples"][0]["steps"][0]["expect"] == {"lines": [{"has": "x", "number": 50}]}
    assert any("a line with “x” shows the number 50" in d for d in shaped["dropped"])
    assert any("shows “a 1”" in d and "checked instead" not in d for d in shaped["dropped"])     # "a": not the example's own


def test_files_given_inside_a_step_are_created_for_the_example():
    # Journey J11-G11: for s1 Nemotron wrote position.motion.json inside the step that reads it, where it was ignored;
    # its revision made the file a step of its own, which was refused.
    source = json.dumps({"inventory": ["motion.mjs"]})
    text = '{"timeline": [{"time": 0, "x": 0}, {"time": 2, "x": 100}]}'
    at_one = {"run": ["node", "motion.mjs", "position.motion.json", "--at", "1"], "expect": {"exit": "ok"}}
    given = [{"name": "position.motion.json", "text": text}]
    inside = {"name": "at one", "says": "With --at the position is printed.", "steps": [dict(at_one, files=given)]}
    alone = {"name": "at one", "says": "With --at the position is printed.", "steps": [{"files": given}, at_one]}
    for example in (inside, alone):
        shaped = validate_examples({"examples": [example]}, "node motion.mjs FILE --at SECONDS", source_text=source)
        assert shaped["examples"][0]["files"] == given and len(shaped["examples"][0]["steps"]) == 1
        assert "missing_input" not in shaped["checks"][0]
    checked = dict(at_one, contains=[{"name": "position.motion.json", "texts": ["timeline"]}])
    shaped = validate_examples({"examples": [dict(inside, steps=[dict(checked, files=given)])]}, "node motion.mjs FILE --at SECONDS")
    assert shaped["examples"][0]["contains"] == [{"name": "position.motion.json", "texts": ["timeline"]}]
    later = {"name": "damaged", "says": "A damaged file gives a message.",
             "steps": [add("Tea", "2026-01-05"), {"files": [{"name": "tally.json", "text": "[{"}]},
                       {"run": T + ["list"], "expect": {"message": True}}]}
    with pytest.raises(WorkspaceError, match='step 2: "files" is not a step'):
        validate_examples({"examples": [later]}, MILESTONE)


def test_the_owner_s_reasons_for_turning_down_checks_reach_the_next_checker(tmp_path):
    # Journey J11-G14: asked again after "x goes from 0 to 100 over 2 seconds, so at 1 second it is 50, not 1", the
    # Checker was never told why the owner had turned its checks down.
    from runesmith.app.acceptance_proposals import discard, packet
    ws = workspace(tmp_path, [EXAMPLES])
    first = propose(ws, ws.router(), "m1")
    assert packet(ws, "m1", "examples")["owner_said_about_earlier_checks"] == []
    discard(ws, "m1", first["id"], reason="x goes from 0 to 100 over 2 seconds, so at 1 second it is 50, not 1")
    assert packet(ws, "m1", "examples")["owner_said_about_earlier_checks"] == [
        "x goes from 0 to 100 over 2 seconds, so at 1 second it is 50, not 1"]


def test_a_check_on_a_file_nothing_creates_is_asked_again_once_and_the_owner_sees_why(tmp_path):
    backup = {"name": "listed from a backup", "says": "Entries are listed from a backup file.",
              "steps": [add("Tea", "2026-01-05"), {"run": T + ["list", "backup.json"], "expect": {"shows": ["Tea"]}}]}
    first = {"examples": EXAMPLES["examples"] + [backup]}
    ws = workspace(tmp_path, [first, EXAMPLES])
    proposal = propose(ws, ws.router(), "m1")
    # Journey J11-CC4: asked again at once with the refusal, as for any other rule of the examples format.
    assert proposal["revision"]["after"] == "unusable" and "backup.json" in proposal["revision"]["error"]
    assert not any(c.get("missing_input") for c in proposal["checks"])


def test_a_command_neither_the_milestone_nor_the_program_mentions_is_refused_with_its_name():
    # Checker experiment 2026-09-28: Flash Lite ran "python -m tally count" where the program's command is "months";
    # every correct build failed its checks. The revision is told the word.
    source = 'if argv[0] == "add": ... if argv[0] == "list": ... if argv[0] == "months":'
    invented = {"examples": [{"name": "counts", "says": "Each month is counted.",
                              "steps": [add("Tea", "2026-01-05"), {"run": T + ["count"], "expect": {"shows": ["2026-01"]}}]}]}
    with pytest.raises(WorkspaceError, match="runs “count”, a command neither the milestone nor the program mentions"):
        validate_examples(invented, "A README that shows each command.", source_text=source)
    real = {"examples": [{"name": "months", "says": "Each month is counted.",
                          "steps": [add("Tea", "2026-01-05"), {"run": T + ["months"], "expect": {"shows": ["2026-01"]}}]}]}
    assert validate_examples(real, "A README that shows each command.", source_text=source)["examples"]
    new = {"examples": [{"name": "search", "says": "A word finds the entry.",
                         "steps": [add("Tea", "2026-01-05"), {"run": T + ["search", "Tea"], "expect": {"shows": ["Tea"]}}]}]}
    assert validate_examples(new, "Add python -m tally search WORD.", source_text=source)["examples"]   # the milestone names it
    assert validate_examples(invented, "A README that shows each command.")["examples"]                  # no source: not judged
    on_purpose = {"examples": [{"name": "unknown", "says": "A command the program does not know is refused.",
                                "steps": [{"run": T + ["count"], "expect": {"exit": "error", "message": True}}]}]}
    assert validate_examples(on_purpose, "A README that shows each command.", source_text=source)["examples"]


def test_an_option_neither_the_milestone_nor_the_program_mentions_is_refused_with_its_name():
    # Journey J11-G30: for a browser export milestone the Checker ran --export-png and --export-webm, which nothing
    # names, and the autopilot approved them.
    source = ('{"inventory": ["motion.mjs", "sample.txt"]} '
              "const at = args.indexOf('--at'); const svg = args.indexOf('--svg');")
    milestone = "Export Capabilities. Implement WebM and PNG export functionality from the browser canvas."
    run = lambda *words: {"examples": [{"name": "export", "says": "The frame is exported.",
                                         "steps": [{"run": ["node", "motion.mjs", "sample.txt", *words]}],
                                         "exists": ["frame.png"]}]}
    with pytest.raises(WorkspaceError, match="with “--export-png”, an option neither the milestone nor the program"):
        validate_examples(run("--export-png", "frame.png"), milestone, source_text=source)
    with pytest.raises(WorkspaceError, match="“--export-png”, “--scale”, options neither"):
        validate_examples(run("--export-png=frame.png", "--scale", "2"), milestone, source_text=source)
    assert validate_examples(run("--at", "0", "--svg", "frame.png"), milestone, source_text=source)["examples"]
    assert validate_examples(run("--png", "frame.png"), milestone, source_text=source)["examples"]   # the milestone says PNG
    for piece in ('{"inventory": ["export-png-helper.js"]}', '<button class="btn-export-png">'):
        with pytest.raises(WorkspaceError, match="“--export-png”, an option neither"):     # review: a piece of another name
            validate_examples(run("--export-png", "frame.png"), milestone, source_text=source + piece)
    with pytest.raises(WorkspaceError, match="“--json”, an option neither"):
        validate_examples(run("--json"), "Export the canvas as a picture.", source_text=source + " legacy-json-migrator.js")
    assert validate_examples(run("--json"), "Print the frame as JSON.", source_text=source)["examples"]
    assert validate_examples(run("--export-png", "frame.png"), milestone)["examples"]              # no source: not judged
    on_purpose = {"examples": [{"name": "unknown", "says": "An option the program does not know is refused.",
                                "steps": [{"run": ["node", "motion.mjs", "sample.txt", "--export-png"],
                                           "expect": {"exit": "error", "message": True}}]}]}
    assert validate_examples(on_purpose, milestone, source_text=source)["examples"]


@pytest.mark.parametrize("given,meant", [(0, "ok"), ("0", "ok"), ("success", "ok"), ("Succeeds", "ok"), (2, "error"),
                                         ("1", "error"), ("failure", "error"), ("non-zero", "error"), ("any", "any")])
def test_common_words_for_the_exit_are_understood(given, meant):
    # Checker experiment 2026-09-28: a whole answer was refused twice over its word for the exit.
    answer = {"examples": [{"name": "listed", "says": "An entry is listed.",
                            "steps": [add("Tea", "2026-01-05"), {"run": T + ["list"], "expect": {"exit": given, "shows": ["Tea"]}}]}]}
    assert validate_examples(answer, MILESTONE)["examples"][0]["steps"][1]["expect"]["exit"] == meant


def test_an_exit_that_is_no_known_word_is_still_refused():
    answer = {"examples": [{"name": "x", "says": "x", "steps": [{"run": T + ["list"], "expect": {"exit": "maybe"}}]}]}
    with pytest.raises(WorkspaceError, match='"exit" is ok, error or any'):
        validate_examples(answer, MILESTONE)



def test_a_file_a_check_starts_with_is_shown_whole_to_the_owner_and_the_builder():
    # Journey J11-G1: the Checker's example fed the program a project file in the format it defined; the builder saw
    # only its first 60 characters and would have had to guess the rest.
    project = '{"version": "1.0", "stage": {"width": 1920, "height": 1080}, "keyframes": [{"id": "rect1", "time": 0}]}'
    answer = {"examples": [{"name": "reads a project", "says": "A project file is read and its object is shown.",
                            "files": [{"name": "test.motion.json", "text": project}],
                            "steps": [{"run": ["node", "motion.mjs", "test.motion.json", "--at", "0"],
                                       "expect": {"shows": ["rect1"]}}]}]}
    shaped = validate_examples(answer, "A project file format read by node motion.mjs.")
    assert project in shaped["checks"][0]["exact"]


NODE_MILESTONE = ("Project file: node motion.mjs FILE --at SECONDS reads a Runesmith Motion project and prints each "
                  "object at that time; a file that is not a project is refused with an error message.")
NODE_EXAMPLES = {"examples": [{"name": "not a project", "says": "A file that is not a project is refused with an error.",
                               "files": [{"name": "bad.motion.json", "text": '{"not_a_project": true}'}],
                               "steps": [{"run": ["node", "motion.mjs", "bad.motion.json", "--at", "0"],
                                          "expect": {"exit": "error"}}]}]}
READ = "import { readFileSync } from 'node:fs';\nconst project = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_a_node_program_that_crashes_does_not_pass_a_check_that_expects_an_error(tmp_path):
    # Journey J11-G2: the checks promised "nothing stops with a Python crash report" for a program run by node. A missing
    # motion.mjs (before the milestone) or an uncaught exception also ends with an error, so such a check passed before
    # anything was built.
    shaped = validate_examples(NODE_EXAMPLES, NODE_MILESTONE)
    assert shaped["dropped"] == [] and "Python" not in shaped["checks"][0]["exact"]
    programs = {"before": None,
                "crashes": READ + "if (!project.version) throw new Error('not a project');\nconsole.log('ok');\n",
                "refuses": READ + "if (!project.version) { console.error(process.argv[2] + ' is not a project'); process.exit(1); }\n"}
    verdicts = {}
    for name, source in programs.items():
        stage = tmp_path / name / "project"
        stage.mkdir(parents=True)
        if source is not None:
            (stage / "motion.mjs").write_text(source, encoding="utf-8")
        checks = tmp_path / name / "acceptance.py"
        checks.write_text(shaped["code"], encoding="utf-8")
        verdicts[name] = _run_checks(stage, json.dumps([str(checks)]), tmp_path / name / "log.txt", timeout_s=240)
    assert {n: v["ok"] for n, v in verdicts.items()} == {"before": False, "crashes": False, "refuses": True}, {
        n: v.get("output", "")[-600:] for n, v in verdicts.items()}



def test_an_expectation_written_as_its_own_step_joins_the_step_before_it():
    # Journey J11-G4: Nemotron wrote [{"run": [...]}, {"expect": {...}}] for m1, m2 and m5; each answer was refused whole.
    answer = {"examples": [{"name": "not a project", "says": "A file that is not a project is refused with an error.",
                            "files": [{"name": "bad.motion.json", "text": "{}"}],
                            "steps": [{"run": ["node", "motion.mjs", "bad.motion.json"]}, {"expect": {"exit": "error"}}]}]}
    shaped = validate_examples(answer, NODE_MILESTONE)
    assert shaped["examples"][0]["steps"] == [{"run": ["node", "motion.mjs", "bad.motion.json"], "expect": {"exit": "error"}}]
    assert "it ends with an error" in shaped["checks"][0]["exact"]
    alone = {"examples": [dict(answer["examples"][0], steps=[{"expect": {"exit": "error"}}])]}
    with pytest.raises(WorkspaceError, match='needs exactly one of'):              # nothing before it to join
        validate_examples(alone, NODE_MILESTONE)



def test_a_last_step_without_expectations_is_shown_in_what_is_checked():
    # Journey J11-B2: m4's only step ran `node motion.mjs project.motion.json --at 0` and had to finish normally, but
    # "What exactly is checked" left the command out and showed only the starting file.
    answer = {"examples": [{"name": "runs", "says": "The inspector runs on a project.",
                            "files": [{"name": "p.motion.json", "text": "{}"}],
                            "steps": [{"run": ["node", "motion.mjs", "p.motion.json", "--at", "0"]}]}]}
    shaped = validate_examples(answer, NODE_MILESTONE)
    assert "running `node motion.mjs p.motion.json --at 0`: it finishes normally" in shaped["checks"][0]["exact"]
    # and a preparing step after a checked one is told after it, once, not folded into an "after" before it
    run = lambda at: {"run": ["node", "motion.mjs", "p.motion.json", "--at", at]}
    answer["examples"][0]["steps"] = [run("0"), dict(run("1"), expect={"exit": "ok"}), run("2")]
    told = validate_examples(answer, NODE_MILESTONE)["checks"][0]["exact"]
    assert told.index("after `node motion.mjs p.motion.json --at 0`") < told.index("running `node motion.mjs p.motion.json --at 1`")
    assert told.count("--at 2") == 1 and told.index("--at 1") < told.index("--at 2")


def test_the_checker_sees_the_checks_approved_for_other_milestones(tmp_path):
    # Journey J11-G5: m1's approved check refused a project file "{}"; m3's Checker, seeing only its own milestone in an
    # empty folder, required the same "{}" to be accepted. No build could pass both.
    from runesmith.app.acceptance_contracts import publish_expectations
    from runesmith.app.acceptance_proposals import packet
    ws = Workspace(tmp_path)
    ws.save_plan({"summary": "Motion", "milestones": [
        {"title": "Project file", "detail": "The project file format.", "done_when": "It is read."},
        {"title": "Inspector", "detail": "node motion.mjs FILE --at SECONDS", "done_when": "It prints the state."}]})
    assert packet(ws, "m2", "examples")["other_milestones_checks"] == []
    refused = "A file missing required data is refused. Checked exactly: Starting with `broken.motion.json` containing “{}”."
    publish_expectations(ws, "m1", [{"id": "check.test_02_invalid", "description": refused}], "approved by the owner")
    assert packet(ws, "m2", "examples")["other_milestones_checks"] == [
        {"milestone": "Project file", "status": "open", "checks": [refused]}]
    assert packet(ws, "m1", "examples")["other_milestones_checks"] == []            # never its own
    assert "other_milestones_checks" in packet(ws, "m2", "examples")["task"]



def test_long_starting_files_shrink_so_what_is_checked_stays_whole():
    # Review of J11-G1 (2026-09-28): with 600 characters per file, two long files pushed the steps and the closing
    # sentence past the 900-character cut, silently.
    from runesmith.app.acceptance_examples import EXACT_LIMIT, exact
    long_file = lambda name: {"name": name, "text": "x" * 2500}
    example = {"files": [long_file("a.motion.json"), long_file("b.motion.json")],
               "steps": [{"run": ["node", "motion.mjs", "a.motion.json"], "expect": {"exit": "error"}}]}
    told = exact(example)
    assert len(told) <= EXACT_LIMIT and told.endswith("and nothing stops with a crash report.")
    assert "running `node motion.mjs a.motion.json`: it ends with an error" in told and told.count("…”") == 2



def test_a_file_whose_wording_is_not_stated_is_still_checked_to_exist():
    # Journey J11-B3: m5's checks required index.html to contain "Export PNG", wording the milestone does not state.
    # It was removed, nothing was left, and the checks passed on an empty folder.
    answer = {"examples": [{"name": "png button", "says": "The page shows a button to export a PNG.",
                            "contains": [{"name": "index.html", "texts": ["Export PNG"]}]}]}
    shaped = validate_examples(answer, "Export: the page offers PNG and WebM export.")
    assert shaped["examples"][0]["exists"] == ["index.html"] and shaped["examples"][0]["contains"] == []
    assert shaped["checks"][0]["exact"] == "`index.html` exists."
    assert any("checked instead that it exists" in d for d in shaped["dropped"])


def test_files_used_as_what_the_page_should_contain_is_explained_to_the_checker():
    # Journey J11-G6: for the editor page the Checker put the wanted HTML under "files" (which creates files first).
    from runesmith.app.acceptance_examples import NothingToCheck
    answer = {"examples": [{"name": "stage", "says": "The page has a stage.", "steps": [],
                            "files": [{"name": "index.html", "text": "<div id=\"stage\">"}]}]}
    with pytest.raises(NothingToCheck, match='use "exists" or "contains"'):
        validate_examples(answer, "Editor: a page with a stage and a timeline.")


def test_a_milestone_nothing_can_check_is_told_to_the_owner_in_plain_words(tmp_path):
    # Journey J11-G6: both answers for the editor page only described files, and the owner read "Both answers broke a
    # rule of the examples format".
    only_files = {"examples": [{"name": "stage", "says": "The page has a stage.", "steps": [],
                                "files": [{"name": "index.html", "text": "<div id=\"stage\">"}]}],
                  "not_checked": "Clicking in the page needs a browser."}
    ws = workspace(tmp_path, [only_files, only_files])
    with pytest.raises(WorkspaceError) as refused:
        propose(ws, ws.router(), "m1", style="examples")
    said = str(refused.value)
    assert said.startswith("Nothing in this milestone could be checked automatically: Clicking in the page needs a browser.")
    assert "read each draft yourself" in said and "acceptance-proposals/refused/" in said and "broke a rule" not in said


def test_file_checks_inside_a_step_and_too_many_texts_are_forgiven():
    # Journey J11-G9: for the SVG frame the Checker put "exists" and "contains" for out.svg inside the step that writes
    # it, used "hides" on a file, and then listed 13 texts to find; both answers were refused whole.
    svg = ["<svg", "<rect", 'x="50"', 'y="50"', 'width="50"', 'height="50"', 'fill="red"', "</svg>",
           "<g", "<title", "viewBox", "xmlns", "version"]
    answer = {"examples": [
        {"name": "frame", "says": "The frame is written as an SVG file.",
         "steps": [{"run": ["node", "motion.mjs", "p.motion.json", "--at", "1", "--svg", "out.svg"],
                    "expect": {"exists": ["out.svg"], "contains": [{"name": "out.svg", "texts": svg}],
                               "hides": [{"name": "out.svg", "texts": ["<circle"]}]}}]}]}
    shaped = validate_examples(answer, "Frames: node motion.mjs FILE --at SECONDS --svg OUT.svg writes an SVG file.")
    example = shaped["examples"][0]
    assert example["exists"] == ["out.svg"] and example["steps"][0].get("expect") is None
    assert any("1 more texts to find in out.svg" in d for d in shaped["dropped"])
    # J11-G19: a "hides" naming a file is a "lacks" check; "<circle" is not in the milestone, so it is dropped as unstated
    assert any("leaves out" in d and "<circle" in d for d in shaped["dropped"]) and example.get("lacks") == []
    assert answer["examples"][0]["steps"][0]["expect"]["exists"] == ["out.svg"]          # the answer itself is kept


def test_texts_that_follow_from_the_milestone_and_the_input_are_kept():
    # Journey J11-G8: every expected SVG text ("<svg", "<rect", 'x="10"') was dropped as wording the milestone does not
    # state, so the frame's content was not checked at all.
    project = '{"project": {"width": 100}, "timeline": [{"time": 0, "elements": [{"id": "a", "type": "rect", "x": 10, "color": "red"}]}]}'
    answer = {"examples": [{"name": "frame", "says": "The frame is an SVG with the rectangle where it is.",
                            "files": [{"name": "p.motion.json", "text": project}],
                            "steps": [{"run": ["node", "motion.mjs", "p.motion.json", "--at", "0", "--svg", "out.svg"]}],
                            "contains": [{"name": "out.svg", "texts": ["<svg", "<rect", 'x="10"', 'fill="red"']}]}]}
    shaped = validate_examples(answer, "Frames: node motion.mjs FILE --at SECONDS --svg OUT.svg writes an SVG file.")
    assert shaped["examples"][0]["contains"] == [{"name": "out.svg", "texts": ["<svg", "<rect", 'x="10"', "red"]}]
    assert any('fill="red"' in d and "checked instead" in d for d in shaped["dropped"])   # the input's word, not its layout


def test_the_owner_s_reasons_about_other_milestones_reach_the_checker(tmp_path):
    # Journey J11-G16: the runes-light Checker repeated the mistake the owner had named for the styles milestone.
    from runesmith.app.acceptance_proposals import discard, packet
    ws = workspace(tmp_path, [EXAMPLES])
    ws.add_milestone("Second part", "Another milestone.", "", "It works.")
    first = propose(ws, ws.router(), "m1")
    discard(ws, "m1", first["id"], reason="With --svg the program writes a file; check the file, not the output.")
    second = next(m["id"] for m in ws.plan()["milestones"] if m["title"] == "Second part")
    said = packet(ws, second, "examples")["owner_said_about_other_milestones_checks"]
    assert said and said[0]["said"].startswith("With --svg the program writes a file") and said[0]["milestone"]
    assert packet(ws, "m1", "examples")["owner_said_about_other_milestones_checks"] == []


def test_a_check_request_every_model_turned_away_is_asked_once_more_smaller(tmp_path, monkeypatch):
    # Journey J11-G17: Groq refused the Checker's full request as too large; nothing ran, so a smaller one is tried.
    from runesmith.app import acceptance_proposals as proposals
    from runesmith.instruments import TransportCensored
    ws = workspace(tmp_path, [EXAMPLES])
    asked = []
    real_ask = proposals._ask

    def ask(router, request, style, key):
        asked.append((key, len(json.dumps(request.get("source_context"), ensure_ascii=False))))
        if len(asked) == 1:
            try:
                raise TransportCensored("every route failed - groq3 bad_request", receipt={"no_route_accepted": True})
            except TransportCensored as error:
                raise proposals.PlannerUnavailable("no acceptance checks: every route refused") from error
        return real_ask(router, request, style, key)
    monkeypatch.setattr(proposals, "_ask", ask)
    proposal = propose(ws, ws.router(), "m1")
    assert proposal["checks"] and [k.endswith("-lean") for k, _ in asked] == [False, True]


def test_a_malformed_record_of_another_milestone_does_not_stop_proposing(tmp_path):
    # Review of J11-G16: one record with a row that is not a proposal made packet() fail for every milestone.
    from runesmith.app.acceptance_proposals import _record_path, packet
    ws = workspace(tmp_path, [EXAMPLES])
    ws.add_milestone("Second part", "Another milestone.", "", "It works.")
    second = next(m["id"] for m in ws.plan()["milestones"] if m["title"] == "Second part")
    path = _record_path(ws, second)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"proposals": [None, "oops", {"state": "discarded", "reason": "Check the file."}]}),
                    encoding="utf-8")
    assert packet(ws, "m1", "examples")["owner_said_about_other_milestones_checks"][0]["said"] == "Check the file."
    path.write_text(json.dumps(["not", "a", "record"]), encoding="utf-8")
    assert packet(ws, "m1", "examples")["owner_said_about_other_milestones_checks"] == []


def test_a_check_request_too_large_for_a_directly_called_model_is_asked_again_smaller(tmp_path):
    # Review of J11-G17: the smaller retry covered only the gateway's refusals, not Groq called directly.
    from runesmith.app import acceptance_proposals as proposals
    from runesmith.instruments import OpenAICompatInstrument, Router
    small = OpenAICompatInstrument("groq", "openai/gpt-oss-120b", base_url="http://groq.invalid/openai/v1",
                                   transport=lambda *args: (500, {}), max_request_tokens=1000)
    router = Router({"groq": small}, {"acceptance": ["groq"]}, backoff_s=())
    with pytest.raises(proposals.PlannerUnavailable) as caught:
        proposals._ask(router, {"x": "y" * 9000}, "examples", "k")
    assert proposals._turned_away(caught.value) and "tokens" in str(caught.value)


LACKS = {"examples": [
    {"name": "no draft marks", "says": "After adding an entry, tally.json holds no DRAFT mark.",
     "steps": [add("Tea", "2026-01-05"), {"run": T + ["list"], "expect": {"shows": ["Tea"]}}],
     "lacks": [{"name": "tally.json", "texts": ["DRAFT", "banana split"]}]}]}


def test_a_file_that_must_not_contain_a_text_is_checked(tmp_path):
    # Journey J11-G19: "with no style there is no rs-bg in out.svg" could not be said, so the Checker put the text
    # that must be absent under "contains", the opposite of its own sentence.
    from runesmith.app.acceptance_examples import TASK, SCHEMA
    assert '"lacks"' in TASK and "lacks" in json.dumps(SCHEMA)
    ws = workspace(tmp_path, [LACKS])
    ws.update_milestone("m1", {"detail": MILESTONE + " The saved tally.json never holds a DRAFT mark."})
    # one scripted answer: the revise call that follows finds none, so no real backoff sleeps (they took 9 minutes)
    proposal = propose(ws, ws.router(backoff_s=()), "m1")
    example = proposal["examples"][0]
    assert example["lacks"] == [{"name": "tally.json", "texts": ["DRAFT"]}]      # "banana split" is not stated
    assert "leaves out" in proposal["checks"][0]["exact"] and "DRAFT" in proposal["checks"][0]["exact"]
    assert 'for row in example.get("lacks", [])' in proposal["code"]
    assert proposal["dry_run"]["verdict"] in ("passes_now", "fails_now", "broken")


def test_a_hides_naming_a_file_becomes_a_lacks_check():
    from runesmith.app.acceptance_examples import _lifted
    dropped = []
    row, steps = _lifted({"name": "x"}, [{"run": ["node", "m.mjs"], "expect": {
        "exit": "ok", "hides": ["Error", {"name": "out.svg", "texts": ["rs-bg"]}]}}], "Example 1", dropped)
    assert row["lacks"] == [{"name": "out.svg", "texts": ["rs-bg"]}] and steps[0]["expect"]["hides"] == ["Error"]
    assert dropped == []


def test_an_expect_next_to_the_steps_is_read_not_ignored():
    # Journey J11-B10: Runes light's checks put their expectations in an "expect" next to "steps"; nothing read it and
    # nothing said so, so both checks only ran the program.
    milestone = ('Runes light: node motion.mjs FILE --at 0 --svg out.svg writes out.svg containing id="rs-light"; '
                 'other styles have no rs-light.')
    answer = {"examples": [
        {"name": "glow", "says": "With the runes style out.svg has the light gradient.",
         "files": [{"name": "t.motion.json", "text": "{}"}],
         "steps": [{"run": ["node", "motion.mjs", "t.motion.json", "--at", "0", "--svg", "out.svg"]}],
         "expect": {"contains": [{"name": "out.svg", "texts": ['id="rs-light"']}],
                    "hides": [{"name": "out.svg", "texts": ["rs-light-2"]}, "Error"]},
         "priority": "high"}]}
    shaped = validate_examples(answer, milestone)
    example = shaped["examples"][0]
    assert example["contains"] == [{"name": "out.svg", "texts": ['id="rs-light"']}]
    # the output text "Error" reached its step, where it is dropped as unstated, and said
    assert any("Error" in d for d in shaped["dropped"]) and any("rs-light-2" in d for d in shaped["dropped"])
    assert any('"priority" is not something these checks read' in d for d in shaped["dropped"])
    files_only = {"examples": [{"name": "doc", "says": "The guide exists.", "expect": {"exists": ["GUIDE.md"]}}]}
    assert validate_examples(files_only, "A GUIDE.md")["examples"][0]["exists"] == ["GUIDE.md"]


def test_the_number_after_a_name_in_a_file_is_checked():
    # Journey J11-G21: 'stroke-dashoffset="57.5"' was dropped as an unstated layout, so the self-drawing rune's three
    # checks never looked at its offset and would pass a rune that never draws.
    milestone = ('One rune: at --at 0 out.svg has a line with stroke-dashoffset and 115; at --at 1 the number 57.5. '
                 'node motion.mjs FILE --at SECONDS --svg out.svg writes out.svg.')
    answer = {"examples": [{"name": "half", "says": "At 1 s the rune is half drawn.",
                            "files": [{"name": "r.motion.json", "text": "{}"}],
                            "steps": [{"run": ["node", "motion.mjs", "r.motion.json", "--at", "1", "--svg", "out.svg"]}],
                            "contains": [{"name": "out.svg", "texts": ['stroke-dashoffset="57.5"']}]}]}
    shaped = validate_examples(answer, milestone)
    example = shaped["examples"][0]
    assert example["file_lines"] == [{"name": "out.svg", "has": "stroke-dashoffset", "number": 57.5}]
    assert "first number after" in shaped["checks"][0]["exact"] and "57.5" in shaped["checks"][0]["exact"]
    assert any("checked instead" in d for d in shaped["dropped"])
    explicit = {"examples": [dict(answer["examples"][0], contains=[],
                                  file_lines=[{"name": "out.svg", "has": "stroke-dashoffset", "number": 57.5}])]}
    assert validate_examples(explicit, milestone)["examples"][0]["file_lines"][0]["number"] == 57.5


def test_the_template_reads_the_first_number_after_the_name():
    from runesmith.app.acceptance_examples import HARNESS
    scope = {}
    source = HARNESS[HARNESS.index("def number_after"):HARNESS.index("def number_on_line")]
    exec("import re\n" + source, scope)
    after = scope["number_after"]
    svg = '<path stroke-dasharray="115" stroke-dashoffset="57.5"/>\n<path stroke-dashoffset="57.5" d="M20,60"/>'
    assert after("stroke-dashoffset", 57.5, svg) and not after("stroke-dashoffset", 115, svg)
    assert not after("stroke-dashoffset", 57.5, '<path stroke-dashoffset="115"/> 57.5')
    assert not after("stroke", 57.5, svg)                    # "stroke-dasharray" is not "stroke" followed by a number


def test_a_text_to_remove_may_be_one_only_the_project_has_and_a_joined_name_is_another_name():
    # Review of J11-G19: "remove the leftover debug banner" lost its text (only the source has it) and became "the file
    # exists"; and "no rs-bg" failed a correct build with "rs-bg-2".
    from runesmith.app.acceptance_examples import HARNESS, _ground
    example = {"steps": [], "files": [], "exists": [], "contains": [], "unchanged": [],
               "lacks": [{"name": "report.txt", "texts": ["DEBUG BUILD - DO NOT SHIP"]}]}
    _ground(example, "Remove the leftover debug banner from the report.", "BANNER = 'DEBUG BUILD - DO NOT SHIP'")
    assert example["lacks"] == [{"name": "report.txt", "texts": ["DEBUG BUILD - DO NOT SHIP"]}] and example["exists"] == []
    scope = {}
    exec("import re\n" + HARNESS[HARNESS.index("def found_whole"):HARNESS.index("def number_after")], scope)
    whole = scope["found_whole"]
    assert not whole("rs-bg", '<rect class="rs-bg-2"/>') and whole("rs-bg", '<rect class="rs-bg"/>')
    assert whole('class="rs-bg"', '<rect class="rs-bg"/>')


def test_a_rescued_number_must_be_stated_and_an_unreadable_expect_is_said():
    # Review of J11-G21: 'width="9999"' became a requirement though only the name "width" was stated anywhere.
    milestone = 'node motion.mjs FILE --at 1 --svg out.svg writes out.svg; at 1 s its stroke-dashoffset is 57.5.'
    base = {"name": "e", "says": "At 1 s.", "files": [{"name": "r.motion.json", "text": '{"width": 200}'}],
            "steps": [{"run": ["node", "motion.mjs", "r.motion.json", "--at", "1", "--svg", "out.svg"]}]}
    invented = validate_examples({"examples": [dict(base, contains=[{"name": "out.svg", "texts": ['width="9999"']}])]}, milestone)
    assert not invented["examples"][0].get("file_lines")
    stated = validate_examples({"examples": [dict(base, contains=[{"name": "out.svg", "texts": ['stroke-dashoffset="57.5px"']}])]}, milestone)
    assert stated["examples"][0]["file_lines"] == [{"name": "out.svg", "has": "stroke-dashoffset", "number": 57.5}]
    # Review of J11-B10: an "expect" that is not an object, or whose output checks have no single program step, is said
    odd = validate_examples({"examples": [dict(base, expect="contains rs-light")]}, milestone)
    assert any("could not be read" in d for d in odd["dropped"])
    two = dict(base, steps=base["steps"] * 2, expect={"shows": ["57.5"], "contains": [{"name": "out.svg", "texts": ["<svg"]}]})
    shaped = validate_examples({"examples": [two]}, milestone)
    assert any("inside the step it is about" in d for d in shaped["dropped"]) and shaped["examples"][0]["contains"]


def test_the_number_after_a_name_is_not_read_inside_a_longer_name():
    from runesmith.app.acceptance_examples import HARNESS
    scope = {}
    exec("import re\n" + HARNESS[HARNESS.index("def number_after"):HARNESS.index("def number_on_line")], scope)
    after = scope["number_after"]
    assert not after("stroke-dashoffset", 57.5, '<path data-stroke-dashoffset="57.5" stroke-dashoffset="115"/>')
    assert after("stroke-dashoffset", 57.5, '<path style="stroke-dashoffset: 5.75e1px"/>')


def test_a_rescued_number_follows_its_own_name_in_the_milestone():
    # Verifier of batch L: 115 was stated for the dasharray, and "m2" / "#1b2130" gave digits nobody stated.
    milestone = ('For milestone m2: node motion.mjs FILE --at 1 --svg out.svg writes out.svg with fill #1b2130; the '
                 'stroke-dasharray is 115 and the stroke-dashoffset moves; at --at 1 its stroke-dashoffset is 57.5.')
    base = {"name": "e", "says": "At 1 s.", "files": [{"name": "r.motion.json", "text": "{}"}],
            "steps": [{"run": ["node", "motion.mjs", "r.motion.json", "--at", "1", "--svg", "out.svg"]}]}
    def rescued(text):
        shaped = validate_examples({"examples": [dict(base, contains=[{"name": "out.svg", "texts": [text]}])]}, milestone)
        return shaped["examples"][0].get("file_lines") or []
    assert rescued('stroke-dashoffset="57.5"') == [{"name": "out.svg", "has": "stroke-dashoffset", "number": 57.5}]
    assert rescued('stroke-dashoffset="115"') == [] and rescued('fill="2130"') == []
    from runesmith.app.acceptance_examples import HARNESS
    scope = {}
    exec("import re\n" + HARNESS[HARNESS.index("def number_after"):HARNESS.index("def number_on_line")], scope)
    assert scope["number_after"]("width:", 200, "width:200")


def test_checks_written_from_examples_are_not_refused_for_the_template_s_length(tmp_path):
    # Journey J11-B12: the signature's three examples, each with its motion file, were refused as "The checks file must
    # contain 1-20000 characters": most of that file is Runesmith's own template.
    from runesmith.app.acceptance_proposals import MAX_CODE
    big = "x" * 1500
    answer = {"examples": [dict(EXAMPLES["examples"][2], name=f"damaged {n}",
                                files=[{"name": "tally.json", "text": '[{"name": "Ha' + big}]) for n in range(3)]}
    ws = workspace(tmp_path, [answer])
    proposal = propose(ws, ws.router(), "m1")
    assert len(proposal["code"]) > MAX_CODE and len(proposal["checks"]) == 3     # over the old limit, accepted


def test_checked_instead_that_it_exists_only_when_nothing_else_checks_the_file():
    # Journey J11-B13: a dropped "lacks" text added "checked instead that it exists" while the file's contents and
    # offset were still checked, and the check autopilot turned a good set down on that note.
    from runesmith.app.acceptance_examples import _ground
    example = {"steps": [], "files": [], "exists": [], "unchanged": [],
               "contains": [{"name": "out.svg", "texts": ['stroke-dasharray="115"']}],
               "lacks": [{"name": "out.svg", "texts": ["M20,60 L35,0 M"]}],
               "file_lines": [{"name": "out.svg", "has": "stroke-dashoffset", "number": 115}]}
    changed = _ground(example, 'out.svg has stroke-dasharray="115" and a line with stroke-dashoffset and 115.', "")
    assert example["exists"] == [] and not any("checked instead that it exists" in c for c in changed)
    alone = {"steps": [], "files": [], "exists": [], "unchanged": [], "contains": [{"name": "page.html", "texts": ["Welcome, friend"]}]}
    assert any("checked instead that it exists" in c for c in _ground(alone, "A page.", "")) and alone["exists"] == ["page.html"]


def test_a_whole_attribute_under_file_lines_is_read_as_contains_and_a_one_letter_lacks_is_dropped():
    # Journey J11-G23: "the first number after stroke-dasharray=\"115\" is 0", and "lacks M" for a path that starts with M.
    milestone = ('node motion.mjs FILE --at 0 --svg out.svg writes out.svg with stroke-dasharray="115" and a line with '
                 'stroke-dashoffset and 115; the rune has no second M.')
    answer = {"examples": [{"name": "rune", "says": "At 0 s the rune is not drawn yet.",
                            "files": [{"name": "r.motion.json", "text": "{}"}],
                            "steps": [{"run": ["node", "motion.mjs", "r.motion.json", "--at", "0", "--svg", "out.svg"]}],
                            "file_lines": [{"name": "out.svg", "has": "stroke-dashoffset=", "number": 115},
                                           {"name": "out.svg", "has": 'stroke-dasharray="115"', "number": 0}],
                            "lacks": [{"name": "out.svg", "texts": ["M"]}]}]}
    shaped = validate_examples(answer, milestone)
    example = shaped["examples"][0]
    assert example["file_lines"] == [{"name": "out.svg", "has": "stroke-dashoffset=", "number": 115}]
    assert example["contains"] == [{"name": "out.svg", "texts": ['stroke-dasharray="115"']}]
    assert example.get("lacks") == [] and any("leaves out" in d and "“M”" in d for d in shaped["dropped"])


def test_a_moved_attribute_is_said_only_when_it_is_checked_and_two_letter_lacks_stay():
    # Review of J11-G23: "checked instead: contains it" was said when the per-file cap blocked the move.
    milestone = 'out.svg has stroke-dasharray="115"; ' + " ".join(f'k{n}="{n}"' for n in range(12)) + '; no px left.'
    full = [f'k{n}="{n}"' for n in range(12)]
    answer = {"examples": [{"name": "e", "says": "It is drawn.", "files": [{"name": "r.json", "text": "{}"}],
                            "steps": [{"run": ["node", "motion.mjs", "r.json", "--svg", "out.svg"]}],
                            "contains": [{"name": "out.svg", "texts": full}],
                            "file_lines": [{"name": "out.svg", "has": 'stroke-dasharray="115"', "number": 0}],
                            "lacks": [{"name": "out.svg", "texts": ["px"]}]}]}
    shaped = validate_examples(answer, milestone)
    assert any("not checked: too many texts" in d for d in shaped["dropped"])
    assert not any("checked instead: out.svg contains it" in d for d in shaped["dropped"])
    assert shaped["examples"][0]["lacks"] == [{"name": "out.svg", "texts": ["px"]}]


def test_moving_an_attribute_never_touches_the_example_s_own_settings():
    # Verifier of batch N2: the move reused the name of the example being read; links_resolve was reset, and past the
    # file cap validation crashed.
    milestone = 'out.svg has stroke-dasharray="115"; ' + " ".join(f'f{n}.svg' for n in range(8))
    answer = {"examples": [{"name": "e", "says": "It is drawn.", "files": [{"name": "r.json", "text": "{}"}],
                            "steps": [{"run": ["node", "motion.mjs", "r.json", "--svg", "out.svg"]}],
                            "contains": [{"name": f"f{n}.svg", "texts": [f"f{n}.svg"]} for n in range(8)],
                            "file_lines": [{"name": "out.svg", "has": 'stroke-dasharray="115"', "number": 0}],
                            "links_resolve": True}]}
    shaped = validate_examples(answer, milestone)
    assert shaped["examples"][0]["links_resolve"] is True
    assert any("not checked: too many texts" in d for d in shaped["dropped"])


def test_a_file_line_number_may_be_the_text_of_the_element_that_holds_the_name():
    # Journey J11-G27: "a line with rs-dim-label and the number 120" is the label's text, after its x and y.
    from runesmith.app.acceptance_examples import HARNESS
    scope = {}
    exec("import re\n" + HARNESS[HARNESS.index("def number_after"):HARNESS.index("def number_on_line")], scope)
    after = scope["number_after"]
    label = '<text class="rs-dim-label" x="100" y="52">120</text>'
    assert after("rs-dim-label", 120, label) and not after("rs-dim-label", 130, label)
    assert after("stroke-dashoffset", 57.5, '<path stroke-dashoffset="57.5" d="M20,60"/>')
    assert not after("stroke-dashoffset", 60, '<path stroke-dashoffset="57.5" d="M20,60"/>')     # not any number
    assert not after("stroke-dashoffset", 57.5, '<path stroke-dashoffset="115">57.5</path>')      # an attribute's own value
    assert not after("stroke-dashoffset", 120, '<path stroke-dashoffset="57.5" d="M1"/>120<circle/>')


def test_a_checked_svg_or_json_file_must_parse(tmp_path):
    # Journey J11-G29: Blueprint wrote <rect ... stroke-width="1.5"<line .../> and its text checks passed.
    from runesmith.app.acceptance_examples import HARNESS
    import unittest
    scope = {}
    exec("import json\nimport re\n" + HARNESS[HARNESS.index("def read_checked"):HARNESS.index("def found")], scope)
    read = scope["read_checked"]
    case = unittest.TestCase()
    good, broken, data = tmp_path / "good.svg", tmp_path / "bad.svg", tmp_path / "bad.json"
    good.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect class="rs-dim"/></svg>', encoding="utf-8")
    broken.write_text('<svg><rect x="1" stroke-width="1.5"<line class="rs-dim"/></svg>', encoding="utf-8")
    data.write_text('{"a": 1,', encoding="utf-8")
    assert 'rs-dim' in read(case, str(good), "good.svg")
    for path, name in ((broken, "bad.svg"), (data, "bad.json")):
        try:
            read(case, str(path), name)
        except AssertionError as error:
            assert "not well-formed" in str(error) or "not valid JSON" in str(error)
        else:
            raise AssertionError(name + " was accepted")


def test_a_file_two_steps_only_read_is_refused_as_missing():
    # Journey J11-G36: two steps both ran the program on dots.motion.json, which the example never made.
    source = json.dumps({"inventory": ["motion.mjs", "sample.motion.json"]}) + ' args.indexOf("--svg")'
    milestone = "Scatter: node motion.mjs FILE --at 3.5 --svg mid.svg shows the fade."
    run = lambda *words: {"run": ["node", "motion.mjs", *words]}
    twice = {"examples": [{"name": "fade", "says": "The dots fade.", "steps": [
        run("dots.motion.json", "--at", "3.5", "--svg", "mid.svg"), run("dots.motion.json", "--at", "6", "--svg", "end.svg")],
        "contains": [{"name": "mid.svg", "texts": ["opacity"]}]}]}
    with pytest.raises(WorkspaceError, match="Example 1 runs dots.motion.json, which neither that example's files"):
        validate_examples(twice, milestone, source_text=source)                   # J11-CC4: refused while it drafts
    assert validate_examples(twice, milestone, source_text=source, refuse_missing=False)["checks"][0]["missing_input"] == ["dots.motion.json"]
    made = json.loads(json.dumps(twice))
    made["examples"][0]["files"] = [{"name": "dots.motion.json", "text": "{}"}]
    assert "missing_input" not in validate_examples(made, milestone, source_text=source)["checks"][0]


def test_an_example_that_checks_only_a_file_it_writes_itself_is_refused():
    # Journey J11-F28: record.html was put in "files" and then checked for texts: nothing the build made was checked.
    own = {"examples": [{"name": "page", "says": "The page records video.",
                          "files": [{"name": "record.html", "text": "captureStream"}],
                          "contains": [{"name": "record.html", "texts": ["captureStream"]}]}]}
    with pytest.raises(WorkspaceError, match="record.html, which it writes itself"):
        validate_examples(own, "A page record.html that uses captureStream.")
    project = {"examples": [{"name": "page", "says": "The page records video.",
                              "contains": [{"name": "record.html", "texts": ["captureStream"]}]}]}
    assert validate_examples(project, "A page record.html that uses captureStream.")["examples"]


@pytest.mark.parametrize("written,checked", [("./record.html", "record.html"), ("Record.html", "record.html"),
                                              ("docs/./record.html", "docs/record.html"), ("./Record.HTML", "record.html")])
def test_a_file_written_in_files_is_matched_by_the_name_it_is_found_under(written, checked):
    # Review of J11-F28: names were compared as written, so "./record.html" or "Record.html" slipped through.
    own = {"examples": [{"name": "page", "says": "The page records video.",
                          "files": [{"name": written, "text": "captureStream"}],
                          "contains": [{"name": checked, "texts": ["captureStream"]}]}]}
    with pytest.raises(WorkspaceError, match="which it writes itself"):
        validate_examples(own, "A page record.html that uses captureStream.")
    slashes = {"examples": [{"name": "page", "says": "The page links its sibling.",
                              "files": [{"name": "docs\\a.html", "text": "x"}],
                              "exists": ["docs/A.html"]}]}
    with pytest.raises(WorkspaceError, match="which it writes itself"):
        validate_examples(slashes, "A page docs/a.html.")


def test_an_example_with_no_steps_that_also_checks_a_project_file_drops_only_the_files_it_wrote():
    # Review of J11-F28: one trivial check on a file the example writes itself refused the whole example, with its
    # real checks of the project's files.
    milestone = "A handbook with recipes/index.md linking seeded-loaf.md."
    mixed = {"examples": [{"name": "index", "says": "The index links the loaf.",
                           "files": [{"name": "fixture.md", "text": "x"}],
                           "exists": ["fixture.md", "recipes/index.md"],
                           "contains": [{"name": "./Fixture.md", "texts": ["x"]},
                                        {"name": "recipes/index.md", "texts": ["seeded-loaf.md"]}]}]}
    stored = validate_examples(mixed, milestone)
    example = stored["examples"][0]
    assert example["exists"] == ["recipes/index.md"] and [c["name"] for c in example["contains"]] == ["recipes/index.md"]
    assert any("fixture.md" in note and "writes them itself" in note for note in stored["dropped"])
    assert "fixture.md" in [f["name"] for f in example["files"]]                  # only its checks go, not the file
    pages = {"examples": [{"name": "new page", "says": "A page added to recipes can be reached.",
                           "files": [{"name": "recipes/new.md", "text": "# New"}],
                           "exists": ["recipes/new.md"], "pages_reachable": True}]}
    kept = validate_examples(pages, milestone)["examples"][0]                    # the project's own pages are still checked
    assert kept["exists"] == [] and kept["pages_reachable"] is True
