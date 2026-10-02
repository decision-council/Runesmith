"""Batch CC (journey J11, 2026-10-01): checks that cover what the milestone's 'done when' names, Checkers that see the
inputs other checks proved, examples that list the files they run, and a second cross-check model before the owner."""
import hashlib
import json

import pytest

from runesmith.app import acceptance_autopilot as autopilot
from runesmith.app import acceptance_proposals as proposals
from runesmith.app.acceptance_examples import validate_examples
from runesmith.app.acceptance_proposals import _record_path, acceptance_file, packet, propose, proven_inputs
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from test_acceptance_examples import EXAMPLES, T, workspace
from test_check_autopilot import answers_for, autopilot_workspace, proposal

# The 'done when' texts of three J11 milestones, as the owner wrote them.
DEPTH = ('960x540, camera time0 x480y270zoom1, time2 x600y270zoom1, layer "far" depth0.5, child rect x100y100 width50 '
         'height50 fill#223344. --at 1: depth0.5 out.svg contains class="rs-layer", data-depth="0.5", '
         'translate(480,270) scale(1) translate(-510,-270); depth0 gives translate(-480,-270); depth1 gives '
         'translate(-540,-270). No layer element: out.svg has no rs-layer.')
EMITTER = ('Worked example (emitter e1, project 300x300, style runes): node motion.mjs FILE --at 0.75 --svg out.svg '
           'contains data-particle="0" cx="100" cy="77.5" r=" and, separately, fill="#ff7a3d" opacity="0.25"; contains '
           'data-particle="1" cx="100" cy="87.875" r=" and, separately, fill="#ffae5c" opacity="0.75"; not '
           'data-particle="2". Rendering twice: same file.')
MASKS = ('With the WORKED EXAMPLE, node motion.mjs FILE --at 0 --svg out.svg writes: id="rs-clip-wipe1", '
         'clip-path="url(#rs-clip-wipe1)", and cx="25". With "mask":{"ref":"win"} instead: id="rs-mask-wipe1", '
         'mask="url(#rs-mask-wipe1)". "wipe1" with both clip and mask, or "wipe2" (same children) with '
         '"clip":{"ref":"missing"}, is refused: prints "Invalid project structure", exits 1.')
PROSE = 'Tests show correct counts, and a damaged file is explained in words.'
TRANSLATES = ['translate(480,270)', 'scale(1)', 'translate(-510,-270)', 'translate(-480,-270)', 'translate(-540,-270)']


def svg_checks(*texts, lines=(), file_lines=(), shows=(), lacks=()):
    """A proposal whose one example runs the program and checks out.svg."""
    step = {"run": ["node", "motion.mjs", "x.motion.json", "--at", "1", "--svg", "out.svg"], "expect": {"exit": "ok"}}
    if shows:
        step["expect"]["shows"] = list(shows)
    if lines:
        step["expect"]["lines"] = list(lines)
    example = {"test": "test_01_x", "files": [{"name": "x.motion.json", "text": "{}"}], "steps": [step],
               "contains": [{"name": "out.svg", "texts": list(texts)}] if texts else [],
               "lacks": [{"name": "out.svg", "texts": list(lacks)}] if lacks else [],
               "file_lines": list(file_lines)}
    return proposal(examples=[example])


# ---------------------------------------------------------------------------------------------------- CC1 (J11-G40)

def test_a_done_when_names_its_attributes_calls_and_quoted_phrases_and_prose_names_nothing():
    # Journey J11-G40: Depth's checks left out the parallax values its 'done when' spells out.
    assert autopilot.named_texts(DEPTH) == ['class="rs-layer"', 'data-depth="0.5"'] + TRANSLATES
    assert autopilot.named_texts(MASKS) == ['id="rs-clip-wipe1"', 'clip-path="url(#rs-clip-wipe1)"', 'cx="25"',
                                            'id="rs-mask-wipe1"', 'mask="url(#rs-mask-wipe1)"', 'Invalid project structure']
    assert autopilot.named_texts('d="M 0 0 L 150 50" and scale(1.5), rgb(255,0,0)') == ['d="M 0 0 L 150 50"', 'scale(1.5)',
                                                                                         'rgb(255,0,0)']
    assert autopilot.named_texts(PROSE) == [] and autopilot.named_texts(None) == [] and autopilot.named_texts("") == []
    # no digit inside the parentheses, or letters that are only a placeholder: not an exact text
    assert autopilot.named_texts('the clip is url(#rs-light) and cubic-bezier(x1,y1,x2,y2) and f(x)') == []
    # one word in quotes is a word, not a phrase
    assert autopilot.named_texts('prints "same" and "drawn", and neither "<svg" nor "Usage"') == []


def test_the_emitter_s_unfinished_attribute_is_no_text_and_the_next_attribute_is_found():
    # The emitter's 'done when' says `r=" and, separately, fill="#ff7a3d"`: no garbage text such as that whole run.
    found = autopilot.named_texts(EMITTER)
    assert found == ['data-particle="0"', 'cx="100"', 'cy="77.5"', 'fill="#ff7a3d"', 'opacity="0.25"',
                     'data-particle="1"', 'cy="87.875"', 'fill="#ffae5c"', 'opacity="0.75"', 'data-particle="2"']
    assert not any('separately' in text or text.startswith('r=') for text in found)


def test_checks_that_leave_out_the_parallax_values_are_held_back_and_covered_ones_pass():
    only_the_class = svg_checks('class="rs-layer"', 'data-depth="0.5"')
    finding = autopilot.gates(only_the_class, DEPTH)
    assert len(finding) == 1 and finding[0].startswith("the checks leave out what the milestone's 'done when' names: ")
    assert finding[0].endswith('; check each of them')
    assert all(f'“{text}”' in finding[0] for text in TRANSLATES) and 'rs-layer' not in finding[0]
    # one longer text covers the three it holds; the other two are still left out
    longer = svg_checks('class="rs-layer"', 'data-depth="0.5"', "translate(480,270) scale(1) translate(-510,-270)")
    assert autopilot.uncovered(longer, DEPTH) == ['translate(-480,-270)', 'translate(-540,-270)']
    covered = svg_checks('class="rs-layer"', 'data-depth="0.5"', "translate(480,270) scale(1) translate(-510,-270)",
                         'translate(-480,-270)', 'translate(-540,-270)')
    assert autopilot.gates(covered, DEPTH) == []
    assert autopilot.gates(only_the_class, PROSE) == [] and autopilot.gates(only_the_class) == []   # prose: silent


def test_a_text_the_checks_forbid_counts_and_whitespace_and_case_do_not_matter():
    assert autopilot.uncovered(svg_checks(lacks=['data-particle="2"']), 'not data-particle="2"') == []
    spaced = svg_checks('d="M  0 0\n L 150   50"')
    assert autopilot.uncovered(spaced, 'gives d="M 0 0 L 150 50"') == []
    assert autopilot.uncovered(svg_checks('FILL="#0000FF"'), 'fill="#0000ff"') == []
    assert autopilot.uncovered(svg_checks(shows=['Invalid project structure']), 'prints "Invalid project structure"') == []
    assert autopilot.uncovered(svg_checks(), 'prints "Invalid project structure"') == ['Invalid project structure']


def test_a_line_check_covers_the_attribute_written_with_its_number():
    # file_lines {"has": "x1", "number": 0.5} looks for x1="0.5" and "x1 0.5"; a whole number has no trailing .0.
    by_file = svg_checks(file_lines=[{"name": "out.svg", "has": "x1", "number": 0.5}])
    assert autopilot.uncovered(by_file, 'gradient x1="0.5"') == [] and autopilot.uncovered(by_file, 'x1="0.6"') == ['x1="0.6"']
    assert autopilot.uncovered(by_file, 'x1="0"') == ['x1="0"']                  # 0.5 is not 0: the whole attribute
    by_step = svg_checks(lines=[{"has": "cx", "number": 25.0}])
    assert autopilot.uncovered(by_step, 'cx="25"') == [] and autopilot.uncovered(by_step, 'cx="2"') == ['cx="2"']
    assert autopilot._line_texts("cx", 25.0) == ['cx="25"', 'cx 25'] and autopilot._line_texts("cx", "x") == []


def test_a_long_list_of_left_out_texts_stays_short_enough_for_the_next_checker():
    many = ' '.join(f'data-n="{n}"' for n in range(60))
    finding = autopilot.gates(svg_checks(), many)[-1]
    assert len(finding) < 600 and ' more; check each of them' in finding and finding.count('“') < 60


def test_the_autopilot_turns_checks_down_that_leave_out_the_done_when_before_asking_the_second_model(tmp_path):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])      # the second model has no answers: asking it would be "undecided"
    ws.update_milestone("m1", {"done_when": 'python -m tally months prints total="12" and count="9"'})
    first = propose(ws, ws.router(), "m1")
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "turn_down", verdict
    assert "the checks leave out what the milestone's 'done when' names: “total=\"12\"”, “count=\"9\"”" in verdict["reason"]
    autopilot.act(ws, "m1", first, verdict)
    assert autopilot.rounds_used(ws, "m1") == 1                              # counted like every turn-down
    said = packet(ws, "m1", "examples")["owner_said_about_earlier_checks"]
    assert said and 'total="12"' in said[0] and "check each of them" in said[0]       # the next Checker is told
    assert autopilot.gates(first, "Tests show correct counts.") == []                 # prose: the gate stays silent


# ---------------------------------------------------------------------------------------------------- CC2 (J11-B16)

def approved(ws, milestone_id, examples, utc, *, state="approved", style="examples", digest=True):
    """Checks in force for a milestone: its acceptance file, and the proposal whose file digest matches it."""
    body = f"# checks of {milestone_id}\n".encode()
    file = acceptance_file(ws, milestone_id)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(body)
    _write_json(_record_path(ws, milestone_id), {"milestone": milestone_id, "proposals": [
        {"id": "p-" + milestone_id, "state": state, "style": style, "examples": examples, "checks": [],
         "file_sha256": hashlib.sha256(body).hexdigest() if digest else "f" * 64, "approved_utc": utc}]})


def example(name, *files, steps=None):
    return {"test": "test_01_" + name, "files": [{"name": n, "text": t} for n, t in files],
            "steps": steps if steps is not None else [{"run": ["node", "motion.mjs", files[0][0], "--at", "1"],
                                                       "expect": {"exit": "ok"}}]}


def format_workspace(tmp_path):
    root = tmp_path / "motion"
    root.mkdir()
    ws = Workspace(root)
    ws.save_plan({"summary": "Motion", "milestones": [
        {"id": "g1", "title": "Camera: slow pushes and pans", "detail": "Camera.", "status": "done"},
        {"id": "g2", "title": "Groups: shapes that move together", "detail": "Groups.", "status": "done"},
        {"id": "g3", "title": "Colour: tints", "detail": "Tints.", "status": "done"},
        {"id": "g4", "title": "Open one", "detail": "Not built.", "status": "open"},
        {"id": "g5", "title": "Dropped one", "detail": "Dropped.", "status": "dropped"},
        {"id": "g6", "title": "Owner file", "detail": "Checks the owner wrote.", "status": "done"},
        {"id": "g7", "title": "Code style", "detail": "Checks written as code.", "status": "done"},
        {"id": "m9", "title": "Depth: layers that move less",
         "detail": "Builds on: Camera: a layer reads the camera's keyframes.", "status": "open"}]})
    camera = '{"project": {"name": "c", "width": 960, "height": 540, "fps": 30, "camera": [{"time": 0, "x": 480, "y": 270, "zoom": 1}]}, "timeline": []}'
    approved(ws, "g1", [example("camera", ("camera.motion.json", camera))], "2026-09-30T08:00:00Z")
    approved(ws, "g2", [example("groups", ("groups.motion.json", '{"project": {"name": "g"}, "timeline": []}'))],
             "2026-10-01T09:00:00Z")
    approved(ws, "g3", [example("colour", ("colour.motion.json", '{"project": {"name": "t", "grade": []}}'))],
             "2026-10-01T07:00:00Z")
    approved(ws, "g4", [example("open", ("open.motion.json", "{}"))], "2026-10-01T10:00:00Z")
    approved(ws, "g5", [example("dropped", ("dropped.motion.json", "{}"))], "2026-10-01T10:00:00Z")
    approved(ws, "g6", [example("owner", ("owner.motion.json", "{}"))], "2026-10-01T10:00:00Z", digest=False)
    approved(ws, "g7", [example("code", ("code.motion.json", "{}"))], "2026-10-01T10:00:00Z", style="code")
    return ws


def test_proven_inputs_name_the_prerequisite_first_then_the_most_recently_approved(tmp_path):
    ws = format_workspace(tmp_path)
    found = proven_inputs(ws, "m9")
    assert [row["milestone"] for row in found] == ["Camera: slow pushes and pans", "Groups: shapes that move together",
                                                   "Colour: tints"]
    assert found[0]["files"][0]["name"] == "camera.motion.json" and '"camera": [' in found[0]["files"][0]["text"]
    assert found == proven_inputs(ws, "m9")                                  # deterministic
    plain = proven_inputs(ws, "g4")                                          # nothing named: newest approval first
    assert [row["milestone"] for row in plain][:2] == ["Groups: shapes that move together", "Colour: tints"]


def test_proven_inputs_skip_undone_milestones_unapproved_checks_and_files_the_program_refuses(tmp_path):
    ws = format_workspace(tmp_path)
    titles = [row["milestone"] for row in proven_inputs(ws, "m9")]
    for left_out in ("Open one", "Dropped one", "Owner file", "Code style"):    # not done, a file the owner changed, no examples
        assert left_out not in titles
    approved(ws, "g2", [example("groups", ("good.motion.json", "GOOD"), ("bad.motion.json", "BAD"),
                                steps=[{"run": ["node", "motion.mjs", "good.motion.json"], "expect": {"exit": "ok"}},
                                       {"run": ["node", "motion.mjs", "bad.motion.json"],
                                        "expect": {"exit": "error", "message": True}}]),
                         example("damaged", ("tally.json", "[{"), steps=[
                             {"run": ["python", "-m", "tally", "list"], "expect": {"message": True}}])],
             "2026-10-01T09:00:00Z")
    names = [f["name"] for row in proven_inputs(ws, "m9") for f in row["files"]]
    assert "good.motion.json" in names and "bad.motion.json" not in names and "tally.json" not in names
    record = json.loads(_record_path(ws, "g1").read_text(encoding="utf-8"))
    record["proposals"][0]["state"] = "proposed"                              # approved checks only
    _write_json(_record_path(ws, "g1"), record)
    assert "Camera: slow pushes and pans" not in [row["milestone"] for row in proven_inputs(ws, "m9")]


def test_proven_inputs_keep_to_their_limit_cut_long_files_and_take_a_few_files_from_each_milestone(tmp_path):
    ws = format_workspace(tmp_path)
    many = [(f"f{n}.motion.json", "x" * 5000 if n == 0 else f'{{"n": {n}}}') for n in range(6)]
    approved(ws, "g1", [example("camera", *many)], "2026-09-30T08:00:00Z")
    full = proven_inputs(ws, "m9")
    assert [f["name"] for f in full[0]["files"]] == ["f0.motion.json", "f1.motion.json", "f2.motion.json"]     # three each
    assert len(full[0]["files"][0]["text"]) == proposals.PROVEN_FILE + 1 and full[0]["files"][0]["text"].endswith("…")
    for limit in (6000, 1700, 600, 100, 0):
        found = proven_inputs(ws, "m9", limit=limit)
        assert len(json.dumps(found, ensure_ascii=False)) <= limit or not found, limit
    assert len(json.dumps(proven_inputs(ws, "m9", limit=1700))) > 1500          # the first big file is kept, cut
    small = proven_inputs(ws, "m9", limit=600)                                 # too big for the room: a smaller one fits
    assert small[0]["milestone"] == "Camera: slow pushes and pans" and small[0]["files"][0]["name"] == "f1.motion.json"
    assert proven_inputs(ws, "m9", limit=0) == []


def test_the_checker_s_packet_carries_the_proven_inputs_and_so_does_a_shorter_request(tmp_path):
    ws = format_workspace(tmp_path)
    data = packet(ws, "m9", "examples")
    assert [row["milestone"] for row in data["proven_inputs"]][0] == "Camera: slow pushes and pans"
    assert "proven_inputs" not in packet(ws, "m9", "code")                    # the code style has no examples to learn from
    assert proposals._lean(ws, data)["proven_inputs"] == data["proven_inputs"]    # the lean request keeps them
    from runesmith.app import acceptance_examples
    assert "proven_inputs" in acceptance_examples.TASK and "same format" in acceptance_examples.TASK


def test_the_cross_check_packet_carries_proven_inputs_and_the_owner_s_documents_within_a_bound(tmp_path):
    ws = format_workspace(tmp_path)
    rules = "# House rules\n\n- project.camera is a list of {time, x, y, zoom}, not an object.\n" + "More rules. " * 2000
    (ws.root / "HOUSE_RULES.md").write_text(rules, encoding="utf-8")
    ws.set_brief(blueprints=["HOUSE_RULES.md"])
    checks = proposal()
    sent = autopilot._packet(ws, "m9", checks, autopilot.questions(checks))
    assert sent["proven_inputs"] == proven_inputs(ws, "m9")
    assert "project.camera is a list" in sent["documents"] and sent["documents"].startswith("--- HOUSE_RULES.md ---")
    assert len(sent["documents"]) <= autopilot.DOCUMENTS < len(rules)
    ws.set_brief(blueprints=[])
    assert autopilot._packet(ws, "m9", checks, autopilot.questions(checks))["documents"] == ""
    assert "misplaced" in autopilot.TASK and "misplaced" in autopilot.SCHEMA["properties"]
    assert "misplaced" not in autopilot.SCHEMA["required"]                      # optional, and not an answer


def misplaced_answers(first, misplaced, contradicts="no"):
    return dict(answers_for(first), misplaced=misplaced, contradicts=contradicts)


def test_a_field_written_in_the_wrong_place_turns_the_checks_down_like_a_disagreement(tmp_path):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    sentence = 'a rect\'s colour is written as "color", where the proven inputs use "fill"'
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [misplaced_answers(first, [sentence])]
    ws.save_config(config)
    check = autopilot.cross_check(ws, "m1", first)
    assert check["misplaced"] == [sentence] and check["disagreements"] == []
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "turn_down" and sentence in verdict["reason"], verdict
    assert "verifier-model found a field written differently from the proven inputs" in verdict["reason"]
    # a claimed contradiction does not hide it: the sentences are the turn-down
    config["instruments"]["verifier"]["answers"] = [misplaced_answers(first, [sentence], True)]
    ws.save_config(config)
    assert autopilot.review(ws, "m1", first)["decision"] == "turn_down"
    said, done = autopilot.act(ws, "m1", first, autopilot.review(ws, "m1", first))
    assert done == "turn_down" and autopilot.rounds_used(ws, "m1") == 1
    kept = next(r for r in proposals._proposal_rows(ws, "m1") if r["id"] == first["id"])["autopilot"]
    assert kept["decision"] == "turned_down" and sentence in kept["reason"]         # the owner can read what was found


@pytest.mark.parametrize("none", [[], "none", ["None."], None, ["", "  "]])
def test_an_empty_misplaced_list_changes_nothing(tmp_path, none):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [dict(answers_for(first), misplaced=none)]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "approve" and verdict["cross_check"]["misplaced"] == []


# ---------------------------------------------------------------------------------------------------- CC4 (J11-G36)

SOURCE = json.dumps({"inventory": ["motion.mjs", "sample.motion.json"]}) + ' args.indexOf("--svg")'
MILESTONE = "Light pools: node motion.mjs FILE --at 1 --svg out.svg draws them."
REFUSAL = ("Example 2 runs light.motion.json, which neither that example's files nor the project hold; each example runs in "
           "its own fresh copy, so list every file it runs in that example's own files.")


def motion(*words, **expect):
    step = {"run": ["node", "motion.mjs", *words]}
    return dict(step, expect=expect) if expect else step


def j11_answer(second):
    return {"examples": [
        {"name": "pool", "says": "A pool is drawn.", "files": [{"name": "light.motion.json", "text": "{}"}],
         "steps": [motion("light.motion.json", "--at", "1", "--svg", "a.svg")], "contains": [{"name": "a.svg", "texts": ["rs-light"]}]},
        dict(second, name="pool again", says="A pool is drawn again.")]}


def test_an_example_that_runs_a_file_it_does_not_list_is_refused_with_the_file_and_the_remedy():
    # Journey J11-G36 again: the file is listed in another example only, and each example runs in its own copy.
    unlisted = {"steps": [motion("light.motion.json", "--at", "1", "--svg", "b.svg")],
                "contains": [{"name": "b.svg", "texts": ["rs-light"]}]}
    with pytest.raises(WorkspaceError) as caught:
        validate_examples(j11_answer(unlisted), MILESTONE, source_text=SOURCE)
    assert str(caught.value) == REFUSAL
    shaped = validate_examples(j11_answer(unlisted), MILESTONE, source_text=SOURCE, refuse_missing=False)
    assert shaped["checks"][1]["missing_input"] == ["light.motion.json"] and "missing_input" not in shaped["checks"][0]
    assert validate_examples(j11_answer(unlisted), MILESTONE)["examples"]                  # no project text: not judged


def test_one_refusal_names_every_example_and_file_that_is_missing():
    both = {"examples": [
        {"name": "one", "says": "One.", "steps": [motion("a.motion.json", "--at", "1", "--svg", "a.svg")],
         "contains": [{"name": "a.svg", "texts": ["rs-light"]}]},
        {"name": "two", "says": "Two.", "steps": [motion("b.motion.json", "--at", "1", "--svg", "b.svg")],
         "contains": [{"name": "b.svg", "texts": ["rs-light"]}]}]}
    with pytest.raises(WorkspaceError) as caught:
        validate_examples(both, MILESTONE, source_text=SOURCE)
    said = str(caught.value)
    assert said.startswith("Example 1 runs a.motion.json, which neither") and "; Example 2 runs b.motion.json, which" in said
    assert said.count("each example runs in its own fresh copy") == 1


def test_a_file_the_example_lists_makes_earlier_or_the_project_holds_is_allowed_and_a_refusal_on_purpose_too():
    def second(**more):
        return j11_answer(dict({"contains": [{"name": "c.svg", "texts": ["rs-light"]}]}, **more))
    own = second(steps=[motion("light.motion.json", "--svg", "c.svg")], files=[{"name": "light.motion.json", "text": "{}"}])
    made = second(steps=[motion("save", "light.motion.json"), motion("light.motion.json", "--at", "1", "--svg", "c.svg")])
    project = second(steps=[motion("sample.motion.json", "--at", "1", "--svg", "c.svg")])
    on_purpose = second(steps=[motion("nowhere.motion.json", exit="error", message=True)], contains=[])
    for answer in (own, made, project, on_purpose):
        shaped = validate_examples(answer, MILESTONE + " save saves a project.", source_text=SOURCE + ' command === "save"')
        assert len(shaped["examples"]) == 2 and not any(c.get("missing_input") for c in shaped["checks"])


def test_a_file_the_project_holds_without_a_model_seeing_it_is_not_refused_but_one_it_lacks_is(tmp_path):
    # The checks' copy of the project holds files the source context does not list (fixtures, shared documents).
    ws = workspace(tmp_path, [])
    (ws.root / "fixtures").mkdir()
    (ws.root / "fixtures" / "seed.json").write_text("[]", encoding="utf-8")
    answer = {"examples": [{"name": "seeded", "says": "Entries are listed from the fixture.",
                            "steps": [{"run": T + ["months", "fixtures/seed.json"], "expect": {"exit": "ok"}}]}]}
    data = packet(ws, "m1", "examples")
    assert "fixtures/seed.json" not in data["source_context"]["inventory"]                # not shown to the model
    assert proposals._clean(answer, "examples", data, ws)["checks"][0].get("missing_input") is None
    gone = json.loads(json.dumps(answer).replace("fixtures/seed.json", "fixtures/gone.json"))
    with pytest.raises(WorkspaceError, match="Example 1 runs fixtures/gone.json, which neither"):
        proposals._clean(gone, "examples", data, ws)


def test_without_a_complete_list_of_the_project_s_files_the_missing_file_is_only_named_under_its_check(tmp_path):
    ws = workspace(tmp_path, [])
    answer = {"examples": [{"name": "backup", "says": "Entries are listed from a backup.",
                            "steps": [{"run": T + ["months", "backup.json"], "expect": {"exit": "ok"}}]}]}
    data = packet(ws, "m1", "examples")
    for context in (dict(data["source_context"], truncated_inventory=True), None, {"files": {}}):
        cut = dict(data, source_context=context)
        assert proposals._clean(answer, "examples", cut)["checks"][0]["missing_input"] == ["backup.json"], context


def test_the_checker_is_asked_once_more_with_the_refusal_while_it_drafts(tmp_path):
    backup = {"name": "listed from a backup", "says": "Entries are listed from a backup file.",
              "steps": [{"run": T + ["list", "backup.json"], "expect": {"exit": "ok"}}]}
    ws = workspace(tmp_path, [{"examples": EXAMPLES["examples"] + [backup]}, EXAMPLES])
    router = ws.router()
    made = propose(ws, router, "m1")
    asked = router.instruments["offline"].requests
    assert len(asked) == 2 and "Example 4 runs backup.json, which neither that example's files nor the project hold" in asked[1]["prompt"]
    assert made["revision"]["after"] == "unusable" and "backup.json" in made["revision"]["error"]
    assert not any(c.get("missing_input") for c in made["checks"])
    stubborn = workspace(tmp_path / "again", [{"examples": EXAMPLES["examples"] + [backup]}] * 2)
    with pytest.raises(WorkspaceError, match="Both answers broke a rule of the examples format.*Example 4 runs backup.json"):
        propose(stubborn, stubborn.router(), "m1")


# ---------------------------------------------------------------------------------------------------- CC5

def two_models(tmp_path, first_answers, second_answers, *, third=False):
    """A checker, a first second model and (when given) another; `third` adds one of the checker's own family."""
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = first_answers
    if second_answers is not None:
        config["instruments"]["verifier2"] = {"kind": "scripted", "model": "verifier2-model", "answers": second_answers}
        config["roles"]["acceptance"] = ["offline", "verifier", "verifier2"]
    if third:
        config["instruments"]["clone"] = {"kind": "scripted", "model": "checker-model", "answers": []}
        config["roles"]["acceptance"] = config["roles"]["acceptance"] + ["clone"]
    ws.save_config(config)
    return ws


def calls(ws):
    path = ws.home / "OPERATIONS.json"
    return {name: row["calls"] for name, row in json.loads(path.read_text(encoding="utf-8"))["instruments"].items()} if path.is_file() else {}


def unclear(first):
    return {"answers": [{"id": row["id"], "answer": "maybe"} for row in autopilot.questions(first)], "contradicts": "no"}


def test_a_model_without_a_clear_judgement_is_followed_by_one_other_model_whose_answers_decide(tmp_path):
    ws = two_models(tmp_path, [], [])
    first = propose(ws, ws.router(), "m1")
    rows = autopilot.questions(first)
    number = next(r for r in rows if r["kind"] == "number" and not r["twin"])
    twin = next(r for r in rows if r["pair"] == number["pair"] and r["twin"])
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [unclear(first)]
    config["instruments"]["verifier2"]["answers"] = [answers_for(first)]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "approve" and "verifier2-model worked out the same" in verdict["reason"], verdict
    attempts = verdict["cross_check"]["attempts"]
    assert [a["model"] for a in attempts] == ["verifier-model", "verifier2-model"]
    assert "gave no clear judgement" in attempts[0]["undecided"] and "undecided" not in attempts[1]
    assert attempts[0]["answers"] and attempts[1]["answers"] and calls(ws) == {"verifier": 1, "verifier2": 1}
    said, done = autopilot.act(ws, "m1", first, verdict)
    assert done == "approve"
    from runesmith.app.acceptance_proposals import _proposal_rows
    kept = next(r for r in _proposal_rows(ws, "m1") if r["id"] == first["id"])["autopilot"]["cross_check"]
    assert [a["model"] for a in kept["attempts"]] == ["verifier-model", "verifier2-model"]       # both attempts are kept
    # the second model's answers decide a turn-down too
    config["instruments"]["verifier2"]["answers"] = [answers_for(first, **{number["id"]: 7, twin["id"]: 14})]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "turn_down" and "verifier2-model worked out 7" in verdict["reason"], verdict


def test_pairs_answered_alike_and_a_fooled_decoy_are_asked_again_too(tmp_path):
    ws = two_models(tmp_path, [], [])
    first = propose(ws, ws.router(), "m1")
    rows = autopilot.questions(first)
    seen, alike = set(), []
    for r in rows:
        if r["pair"]:
            alike.append({"id": r["id"], "answer": "no" if r["pair"] in seen else "yes"})
            seen.add(r["pair"])
        else:
            alike.append({"id": r["id"], "answer": str(r["expected"])})
    fooled = [{"id": r["id"], "answer": str(r["expected"]) if r["about"] != "decoy" else "yes"} for r in rows]
    for bad in (alike, fooled):
        config = ws.config()
        config["instruments"]["verifier"]["answers"] = [{"answers": bad, "contradicts": "no"}]
        config["instruments"]["verifier2"]["answers"] = [answers_for(first)]
        ws.save_config(config)
        assert autopilot.review(ws, "m1", first)["decision"] == "approve"


def test_when_the_second_model_is_undecided_too_the_checks_wait_for_the_owner_with_both_reasons(tmp_path):
    ws = two_models(tmp_path, [], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [unclear(first)]
    config["instruments"]["verifier2"]["answers"] = [unclear(first)]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "verifier-model gave no clear judgement" in verdict["reason"]
    assert "asked once more: verifier2-model gave no clear judgement" in verdict["reason"], verdict
    assert [a["model"] for a in verdict["cross_check"]["attempts"]] == ["verifier-model", "verifier2-model"]
    assert calls(ws) == {"verifier": 1, "verifier2": 1}                         # one more, never a third


def test_with_no_other_usable_model_it_waits_for_the_owner_as_before(tmp_path):
    ws = two_models(tmp_path, [], None)
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [unclear(first)]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "gave no clear judgement" in verdict["reason"]
    assert "asked once more" not in verdict["reason"] and "attempts" not in verdict["cross_check"]
    assert calls(ws) == {"verifier": 1}
    assert autopilot.second_model(ws, "checker-model", skip=("verifier",)) is None
    assert autopilot.second_model(ws, "checker-model", skip=()) == "verifier"


def test_a_claimed_contradiction_and_a_missing_second_model_are_not_asked_again(tmp_path):
    ws = two_models(tmp_path, [], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [dict(answers_for(first), contradicts=True, contradiction="m2 refuses this file")]
    config["instruments"]["verifier2"]["answers"] = [answers_for(first)]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "m2 refuses this file" in verdict["reason"]
    assert calls(ws) == {"verifier": 1}                                          # the other model was never asked
    alone = autopilot_workspace(tmp_path / "alone", [EXAMPLES], [])
    alone_config = alone.config()
    alone_config["roles"]["acceptance"] = ["offline"]
    alone.save_config(alone_config)
    only = propose(alone, alone.router(), "m1")
    assert "no second model" in autopilot.cross_check(alone, "m1", only)["undecided"]


def test_the_checker_s_own_family_is_never_asked_even_when_every_other_model_is_undecided(tmp_path):
    ws = two_models(tmp_path, [], [], third=True)
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [unclear(first)]
    config["instruments"]["verifier2"]["answers"] = [unclear(first)]
    config["instruments"]["clone"]["answers"] = [answers_for(first)]             # would approve, if it were asked
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "clone" not in calls(ws), calls(ws)
    assert autopilot.second_model(ws, "checker-model", skip=("verifier", "verifier2")) is None


def test_the_second_call_is_a_separate_request(tmp_path, monkeypatch):
    ws = two_models(tmp_path, [], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [unclear(first)]
    config["instruments"]["verifier2"]["answers"] = [answers_for(first)]
    ws.save_config(config)
    keys = []
    from runesmith import instruments
    real = instruments.ScriptedInstrument.complete

    def spy(self, **kwargs):
        keys.append((self.name, kwargs["key"]))
        return real(self, **kwargs)
    monkeypatch.setattr(instruments.ScriptedInstrument, "complete", spy)
    autopilot.review(ws, "m1", first)
    assert [(name, key.rsplit("-a", 1)[0]) for name, key in keys] == [("verifier", "autopilot-" + first["id"]),
                                                                    ("verifier2", "autopilot-again-" + first["id"])]
