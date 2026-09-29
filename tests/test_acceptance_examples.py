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
    validate({"checks": [{"test": c["test"], "says": c["says"]} for c in shaped["checks"]], "code": shaped["code"]})
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
    source = json.dumps({"inventory": ["motion.mjs", "sample.motion.json"]}) + ' if (command === "save")'
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
    checks = validate_examples(answer, milestone, source_text=source)["checks"]
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


def test_a_check_on_a_file_nothing_creates_is_revised_once_and_the_owner_sees_why(tmp_path):
    backup = {"name": "listed from a backup", "says": "Entries are listed from a backup file.",
              "steps": [add("Tea", "2026-01-05"), {"run": T + ["list", "backup.json"], "expect": {"shows": ["Tea"]}}]}
    first = {"examples": EXAMPLES["examples"] + [backup]}
    ws = workspace(tmp_path, [first, EXAMPLES])
    proposal = propose(ws, ws.router(), "m1")
    assert proposal["revision"]["after"] == "missing_input"
    assert not any(c.get("missing_input") for c in proposal["checks"])
    assert proposal["revision"]["first_checks"][-1]["missing_input"] == ["backup.json"]


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
    assert any("does not contain some text" in d for d in shaped["dropped"])
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
