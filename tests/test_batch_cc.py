"""Batch CC (journey J11, 2026-10-01): checks that cover what the milestone's 'done when' names, Checkers that see the
inputs other checks proved, examples that list the files they run, and a second cross-check model before the owner."""
import hashlib
import json

import pytest

from runesmith.app import acceptance_autopilot as autopilot
from runesmith.app import acceptance_proposals as proposals
from runesmith.app.acceptance_examples import validate_examples
from runesmith.app.acceptance_proposals import _record_path, acceptance_file, packet, propose, proven_inputs
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from runesmith.app.planner import PlannerUnavailable, SkippedByOwner
from runesmith.instruments import CallOutcome, TransportCensored
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
    kept = propose(stubborn, stubborn.router(), "m1")      # the one more try is kept, with the finding (review of batch CC)
    assert kept["checks"][-1]["missing_input"] == ["backup.json"] and kept["revision"]["after"] == "unusable"


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


# ------------------------------------------------------------------------------------- review of batch CC (fix-cc)

BACKUP = {"name": "listed from a backup", "says": "Entries are listed from a backup file.",
          "steps": [{"run": T + ["list", "backup.json"], "expect": {"exit": "ok"}}]}
UNUSABLE = {"examples": [{"name": "x", "says": "x", "steps": [{"run": ["bash", "-c", "true"]}]}]}


def scheduled(ws):
    ws.update_settings({"build_steps": True, "auto_work": True, "policy_chosen": True, "onboarded": True})
    return Worker(ws, EventBus())


def test_13_a_checker_that_still_runs_an_unlisted_file_on_its_one_more_try_is_turned_down_and_counted(tmp_path):
    # Review of batch CC: refused twice, nothing was stored, so rounds_used stayed 0 and the schedule asked again at once
    # for ever, and never built (before CC4 this was a stored, counted turn-down that ended at MAX_ROUNDS).
    ws = autopilot_workspace(tmp_path, [{"examples": EXAMPLES["examples"] + [BACKUP]}] * 2, [])
    worker = scheduled(ws)
    for used in (1, 2):
        assert worker.scheduled_job() == ("propose_acceptance", {"milestone": "m1"})
        made = propose(ws, ws.router(), "m1")                      # kept with the finding, not refused
        assert made["checks"][-1]["missing_input"] == ["backup.json"] and made["revision"]["after"] == "unusable"
        verdict = autopilot.review(ws, "m1", made)
        assert verdict["decision"] == "turn_down" and "backup.json" in verdict["reason"], verdict
        assert autopilot.act(ws, "m1", made, verdict)[1] == "turn_down" and autopilot.rounds_used(ws, "m1") == used
    assert autopilot.needs_checks(ws) is None and worker.scheduled_job() == ("build", {})     # the owner, and the schedule builds


def test_19_a_checker_answer_refused_twice_leaves_a_trace_that_counts_and_the_next_checker_reads(tmp_path):
    ws = autopilot_workspace(tmp_path, [UNUSABLE] * 2, [])
    worker = scheduled(ws)
    for used in (1, 2):
        assert worker.scheduled_job() == ("propose_acceptance", {"milestone": "m1"})
        with pytest.raises(WorkspaceError, match="Both answers broke a rule"):
            propose(ws, ws.router(), "m1")
        assert autopilot.rounds_used(ws, "m1") == used
    assert autopilot.needs_checks(ws) is None and worker.scheduled_job() == ("build", {})
    row = proposals._proposal_rows(ws, "m1")[-1]
    assert row["state"] == "discarded" and row["refused"] and "could not use either answer" in row["reason"]
    assert any("could not use either answer" in said for said in packet(ws, "m1", "examples")["owner_said_about_earlier_checks"])
    nothing = {"examples": [{"name": "files", "says": "Nothing to run.", "steps": []}]}      # "nothing could be checked": too
    quiet = autopilot_workspace(tmp_path / "nothing", [nothing] * 2, [])
    with pytest.raises(WorkspaceError, match="Nothing in this milestone could be checked"):
        propose(quiet, quiet.router(), "m1")
    assert autopilot.rounds_used(quiet, "m1") == 1


def test_19_with_the_autopilot_off_the_trace_tells_the_next_checker_but_counts_no_round(tmp_path):
    ws = workspace(tmp_path, [UNUSABLE] * 2)
    with pytest.raises(WorkspaceError, match="Both answers broke a rule"):
        propose(ws, ws.router(), "m1")
    assert autopilot.rounds_used(ws, "m1") == 0
    assert "could not use either answer" in packet(ws, "m1", "examples")["owner_said_about_earlier_checks"][0]


def test_14_what_is_typed_in_or_run_is_not_demanded_of_the_output():
    # Review of batch CC: 'square_demo with d "M 0 0 l 100 0" prints Invalid project structure': the path is the input
    # the program refuses, never printed; the only way past the gate was a check on the file the example writes itself.
    done_when = 'square_demo with d "M 0 0 l 100 0" prints Invalid project structure, exit 1'
    assert autopilot.named_texts(done_when) == ["M 0 0 l 100 0"]
    refused = {"test": "t", "files": [{"name": "square_bad.motion.json",
                                       "text": '{"timeline": [{"elements": [{"type": "path", "d": "M 0 0 l 100 0"}]}]}'}],
               "steps": [{"run": ["node", "motion.mjs", "square_bad.motion.json"],
                          "expect": {"exit": "error", "shows": ["Invalid project structure"]}}]}
    assert autopilot.gates(proposal(examples=[refused]), done_when) == []
    command = 'The command "python -m tally months" prints total="12" and creates "my notes.txt".'
    ran = {"test": "t", "files": [], "steps": [{"run": ["python", "-m", "tally", "months"]}], "exists": ["my notes.txt"]}
    assert autopilot.uncovered(proposal(examples=[ran]), command) == ['total="12"']          # only the output is asked for


def test_14_prose_maths_and_escaped_text_are_not_demanded_in_a_form_no_output_has():
    assert autopilot.named_texts("(2*sqrt(100)=20, then x=\"112.4\") and sqrt(100) alone") == ['x="112.4"', 'sqrt(100)']
    assert autopilot.named_texts("a spring that overshoots: 3 + sqrt(9) and scale(1.5)") == ["scale(1.5)"]
    escaped = svg_checks('<text>Runesmith &amp; co</text>')
    assert autopilot.uncovered(escaped, 'A text "Runesmith & co" renders as Runesmith &amp; co') == []
    assert autopilot.uncovered(svg_checks(), 'A text "Runesmith & co" renders') == ["Runesmith & co"]


def test_14_a_check_on_a_file_the_example_writes_itself_with_the_text_already_in_it_covers_nothing():
    own = {"test": "t", "files": [{"name": "in.svg", "text": '<g total="12"/>'}],
           "steps": [{"run": ["node", "motion.mjs", "in.svg", "--svg", "out.svg"]}],
           "contains": [{"name": "in.svg", "texts": ['total="12"']}]}
    assert autopilot.uncovered(proposal(examples=[own]), 'out.svg has total="12"') == ['total="12"']
    in_the_output = dict(own, contains=[{"name": "out.svg", "texts": ['total="12"']}])
    assert autopilot.uncovered(proposal(examples=[in_the_output]), 'out.svg has total="12"') == []
    edited = dict(own, contains=[{"name": "in.svg", "texts": ['total="13"']}])                  # a step may change it
    assert autopilot.uncovered(proposal(examples=[edited]), 'in.svg then has total="13"') == []


def test_15_a_line_check_that_starts_the_attribute_covers_the_attribute():
    # Review of batch CC: the Checker writes has 'r=', 'x="' or 'x1="0" y1=' (the first number after that text).
    for has, number, covers in (("r=", 10, 'r="10"'), ('x="', 100, 'x="100"'), ('x1="0" y1=', 0.5, 'y1="0.5"'), ("r:", 3, 'r="3"')):
        assert autopilot.uncovered(svg_checks(file_lines=[{"name": "out.svg", "has": has, "number": number}]), covers) == [], has
        assert autopilot.uncovered(svg_checks(lines=[{"has": has, "number": number}]), covers) == [], has
    assert autopilot.uncovered(svg_checks(file_lines=[{"name": "out.svg", "has": "r=", "number": 10}]), 'r="20"') == ['r="20"']
    assert autopilot._line_texts("r=", 10.0) == ['r=="10"', "r= 10", 'r="10"', "r 10"]


def test_24_a_longer_name_does_not_cover_the_named_attribute():
    # Review of batch CC: stop-opacity="0.5" held opacity="0.5", cx="100" held x="100", fr held r, data-class held class.
    wrong = svg_checks('stop-opacity="0.5"', 'cx="100"', 'stroke-width="100"')
    assert autopilot.uncovered(wrong, 'opacity="0.5" x="100" width="100"') == ['opacity="0.5"', 'x="100"', 'width="100"']
    assert autopilot.uncovered(svg_checks('rx="0"', 'stroke-width="100"'), 'x="0" and width="100"') == ['x="0"', 'width="100"']
    assert autopilot.uncovered(svg_checks('data-class="rs-layer"', 'fr="55.902"'),
                               'class="rs-layer" and r="55.902"') == ['class="rs-layer"', 'r="55.902"']
    right = svg_checks('<rect x="100" y="0" width="100"', "translate(480,270) scale(1) translate(-510,-270)", 'fill-opacity="0.5" opacity="0.5"')
    assert autopilot.uncovered(right, 'x="100" width="100" translate(-510,-270) opacity="0.5"') == []


FILLERS = ["N/A", "n/a", "N.A.", "not applicable", "Not applicable: nothing is written under a different name.", "not found",
           "-", "nil", "null", "Empty", "All fields are placed correctly.", "Everything is consistent.",
           "All fields match the proven inputs.", "The examples are consistent with the proven inputs and the milestone.",
           "Every example uses the same fields as the proven inputs."]
CLAIMS = ['Example 1 writes "color" where the proven inputs use "fill".',
          "All examples write the camera as timeline elements instead of project.camera.",
          "Not found: the camera is written as keyframes"]


def test_16_and_26_filler_in_the_misplaced_list_is_no_finding_and_a_real_claim_is():
    assert autopilot._misplaced(FILLERS) == []
    assert autopilot._misplaced(FILLERS + CLAIMS) == CLAIMS
    assert autopilot._contradiction("N/A") is None and autopilot._contradiction("Everything is consistent.") is None
    assert autopilot._contradiction("m1 refuses an empty project file, which this check requires") is not None


@pytest.mark.parametrize("filler", ["N/A", "All fields are placed correctly.", "Not applicable: nothing is written elsewhere."])
def test_16_and_26_a_second_model_that_answers_filler_does_not_turn_correct_checks_down(tmp_path, filler):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [dict(answers_for(first), misplaced=[filler])]
    ws.save_config(config)
    assert autopilot.review(ws, "m1", first)["decision"] == "approve"


def test_17_a_second_model_that_gives_no_answer_is_followed_by_another(tmp_path):
    # Review of batch CC: its free quota used up, or it is down: every proposal waited for the owner for as long as
    # that lasted, and the next model in the role was never asked.
    ws = two_models(tmp_path, [], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = []                       # unavailable: script exhausted
    config["instruments"]["verifier2"]["answers"] = [answers_for(first)]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "approve" and "verifier2-model worked out the same" in verdict["reason"], verdict
    assert calls(ws) == {"verifier": 1, "verifier2": 1}
    assert "got no answer" in verdict["cross_check"]["attempts"][0]["undecided"]
    config["instruments"]["verifier"]["answers"] = [["not", "an", "object"]]        # an answer that is no JSON object
    ws.save_config(config)
    assert autopilot.review(ws, "m1", first)["decision"] == "approve"
    config["instruments"]["verifier2"]["answers"] = []                       # both down: the owner, with both reasons
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "asked once more: the cross-check got no answer" in verdict["reason"], verdict


def test_18_a_proposal_whose_review_never_happened_is_reviewed_and_reused_without_asking_the_checker_again(tmp_path):
    # Review of batch CC: the Studio stopped between the proposal and its review; the row stayed 'proposed' without a
    # verdict, and needs_checks skipped the milestone for the whole unattended run.
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    router = ws.router()
    first = propose(ws, router, "m1")                      # ... the job ended here
    assert autopilot.needs_checks(ws) == "m1" and scheduled(ws).scheduled_job() == ("propose_acceptance", {"milestone": "m1"})
    again = propose(ws, router, "m1")
    assert again["id"] == first["id"] and len(router.instruments["offline"].requests) == 1      # reused, no new Checker call
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [answers_for(first)]
    ws.save_config(config)
    verdict = autopilot.review(ws, "m1", again)
    assert autopilot.act(ws, "m1", again, verdict)[1] == "approve" and autopilot.needs_checks(ws) is None


def test_18_a_review_that_breaks_off_with_an_error_is_left_for_the_owner_and_not_asked_for_again(tmp_path, monkeypatch):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    first = propose(ws, ws.router(), "m1")

    def broken(*args):
        raise AttributeError("'NoneType' object has no attribute 'get'")
    monkeypatch.setattr(autopilot, "_review", broken)
    verdict = autopilot.review(ws, "m1", first)
    assert verdict["decision"] == "owner" and "could not finish its review (AttributeError" in verdict["reason"]
    assert autopilot.act(ws, "m1", first, verdict)[1] == "owner" and autopilot.needs_checks(ws) is None   # a note: no loop


def test_23_the_one_more_model_reads_a_lean_packet(tmp_path):
    # Review of batch CC: the full packet measured up to 31 KB and J11's Groq route refuses about 22 KB; the one more
    # model can be Groq, and had no lean fallback.
    ws = format_workspace(tmp_path)
    (ws.root / "HOUSE_RULES.md").write_text("# Rules\n" + "More rules. " * 2000, encoding="utf-8")
    ws.set_brief(blueprints=["HOUSE_RULES.md"])
    checks = proposal()
    asked = autopilot.questions(checks)
    full, lean = autopilot._packet(ws, "m9", checks, asked), autopilot._packet(ws, "m9", checks, asked, lean=True)
    assert "other_milestones_checks" in full and "other_milestones_checks" not in lean and "program_excerpts" not in lean
    assert len(lean["documents"]) <= autopilot.LEAN_DOCUMENTS < len(full["documents"])
    assert len(json.dumps(lean["proven_inputs"])) <= autopilot.LEAN_PROVEN
    assert len(json.dumps(lean, ensure_ascii=False)) < len(json.dumps(full, ensure_ascii=False)) - 2000
    assert lean["examples"] == full["examples"] and lean["milestone"] == full["milestone"]    # what is judged is the same


@pytest.mark.parametrize("kind,refusal", [("config", {"refused_before_answer": "too_large"}), ("transport", {"no_route_accepted": True})])
def test_23_a_model_whose_route_refused_the_full_request_as_too_large_is_asked_again_leaner(tmp_path, monkeypatch, kind, refusal):
    ws = two_models(tmp_path / "second", [], [])
    first = propose(ws, ws.router(), "m1")
    config = ws.config()
    config["instruments"]["verifier"]["answers"] = [unclear(first)]
    config["instruments"]["verifier2"]["answers"] = [answers_for(first)]
    ws.save_config(config)
    from runesmith import instruments
    real, seen = instruments.ScriptedInstrument.complete, []

    def spy(self, **kwargs):
        seen.append((self.name, '"other_milestones_checks"' in kwargs["prompt"], kwargs["key"].rsplit("-a", 1)[0]))
        if self.name == "verifier" and len(seen) == 1:                 # the first, full request is refused as too large
            return CallOutcome(False, error_kind=kind, error="too large for this route", receipt=dict(refusal))
        return real(self, **kwargs)
    monkeypatch.setattr(instruments.ScriptedInstrument, "complete", spy)
    verdict = autopilot.review(ws, "m1", first)
    # the full request, refused; the same model again, leaner; it is unclear, so the other model, leaner
    assert seen == [("verifier", True, "autopilot-" + first["id"]), ("verifier", False, "autopilot-lean-" + first["id"]),
                    ("verifier2", False, "autopilot-again-" + first["id"])], seen
    assert verdict["decision"] == "approve", verdict


# ------------------------------------------------------------------ failed scheduled requests (review of batch CC, #19)

def checker_that_fails(monkeypatch, outcome):
    """Every model of the Checker's role fails each request with `outcome()`; the state counts the asks, and its
    'works' flips them back to answering."""
    from runesmith import instruments
    real, state = instruments.ScriptedInstrument.complete, {"asked": 0, "works": False}

    def complete(self, **kwargs):
        if self.name not in ("offline", "verifier") or state["works"]:
            return real(self, **kwargs)
        state["asked"] += 1
        return outcome()
    monkeypatch.setattr(instruments.ScriptedInstrument, "complete", complete)
    return state


def unusable_answer():
    return CallOutcome(False, error_kind="output", error="no JSON in the answer")


def run_request(worker, by="schedule", n=[0]):
    n[0] += 1
    worker._execute({"id": f"{by}{n[0]}", "kind": "propose_acceptance", "params": {"milestone": "m1"}, "by": by})
    return worker.history[-1]


def test_two_scheduled_requests_whose_answers_are_not_usable_stop_the_asking_and_the_schedule_builds(tmp_path, monkeypatch):
    # Review of batch CC (#19, wider class): the Checker's answer was not usable, nothing was stored, and every round
    # asked again at once, ahead of every build, for ever.
    ws = autopilot_workspace(tmp_path, [], [])
    asked = checker_that_fails(monkeypatch, unusable_answer)
    worker = scheduled(ws)
    for n in (1, 2):
        assert worker.scheduled_job() == ("propose_acceptance", {"milestone": "m1"})
        row = run_request(worker)
        assert row["result"] == "failed" and "not usable" in row["outcome"]["error"]
        assert f"{n} of 2" in row["outcome"]["error"]
    assert "stops asking for them by itself and builds other work" in row["outcome"]["error"]
    assert asked["asked"] == 2 and autopilot.needs_checks(ws) is None and worker.scheduled_job() == ("build", {})
    said = proposals.status(ws)["m1"]["requests_paused"]
    assert said["count"] == 2 and "stopped asking for them by itself" in said["message"] and "not usable" in said["message"]
    assert proposals.status(ws)["m1"]["approved"] is None and proposals.status(ws)["m1"]["proposal"] is None


def test_a_change_of_the_source_or_the_milestone_lets_the_schedule_ask_again_and_the_count_starts_afresh(tmp_path, monkeypatch):
    ws = autopilot_workspace(tmp_path, [], [])
    checker_that_fails(monkeypatch, unusable_answer)
    worker = scheduled(ws)
    run_request(worker), run_request(worker)
    assert autopilot.needs_checks(ws) is None
    (ws.root / "tally" / "extra.py").write_text("EXTRA = 1\n", encoding="utf-8")            # the project's files change
    assert autopilot.needs_checks(ws) == "m1"
    assert "(Failed request 1 of 2;" in run_request(worker)["outcome"]["error"]                # counted afresh
    assert proposals.status(ws).get("m1") is None                                           # one failure: not paused
    run_request(worker)
    assert autopilot.needs_checks(ws) is None and proposals.status(ws)["m1"]["requests_paused"]["count"] == 2
    ws.update_milestone("m1", {"detail": "Months: python -m tally months prints how many entries each month has."})
    assert autopilot.needs_checks(ws) == "m1"                                               # the milestone changed


def test_the_owner_s_own_request_still_runs_when_the_schedule_has_stopped_and_an_answer_ends_the_count(tmp_path, monkeypatch):
    ws = autopilot_workspace(tmp_path, [EXAMPLES], [])
    state = checker_that_fails(monkeypatch, unusable_answer)
    worker = scheduled(ws)
    run_request(worker), run_request(worker)
    assert state["asked"] == 2 and autopilot.needs_checks(ws) is None
    owner = run_request(worker, "owner")                                                    # asked by hand: it runs
    assert state["asked"] == 3 and owner["result"] == "failed" and "stops asking" not in owner["outcome"]["error"]
    assert proposals.status(ws)["m1"]["requests_paused"]["count"] == 2                      # his failure is not counted
    state["works"] = True
    assert run_request(worker, "owner")["result"] == "done"
    shown = proposals.status(ws)["m1"]
    assert shown["proposal"] and "requests_paused" not in shown                              # answered: the count ended
    assert "request_failures" not in proposals._record(ws, "m1")


def test_a_request_that_no_model_accepted_backs_off_and_does_not_count_but_a_model_that_did_not_answer_does(tmp_path, monkeypatch):
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"full_speed": True})
    nobody = checker_that_fails(monkeypatch, lambda: CallOutcome(False, error_kind="transport", error="capacity",
                                                                 receipt={"no_route_accepted": True}))
    worker = scheduled(ws)
    for _ in range(3):
        assert run_request(worker)["result"] == "failed"
    assert autopilot.needs_checks(ws) == "m1" and proposals.status(ws).get("m1") is None   # nothing ran: not counted
    assert worker._due() > 30                                                               # it waits, and asks later
    silent = checker_that_fails(monkeypatch, lambda: CallOutcome(False, error_kind="transport", error="timeout"))
    run_request(worker), run_request(worker)
    assert silent["asked"] >= 2 and autopilot.needs_checks(ws) is None                      # asked, not answered: counted
    assert nobody["asked"] >= 3


def test_what_counts_as_a_failed_request_and_when_the_pause_ends_by_itself(tmp_path, monkeypatch):
    assert proposals.counts_as_failure(PlannerUnavailable("the model's answer was not usable: no JSON"))
    assert proposals.counts_as_failure(WorkspaceError("Both answers broke a rule of the examples format."))
    assert not proposals.counts_as_failure(SkippedByOwner("you skipped the request"))
    assert not proposals.counts_as_failure(WorkspaceError("You withdrew checks for this milestone while these were being written"))
    for flag in ("not_admitted", "no_route_accepted"):
        try:
            try:
                raise TransportCensored("every model turned it away", receipt={flag: True})
            except TransportCensored as cause:
                raise PlannerUnavailable("no acceptance checks: every model turned it away") from cause
        except PlannerUnavailable as error:
            assert not proposals.counts_as_failure(error), flag
    ws = autopilot_workspace(tmp_path, [], [])
    ws.update_settings({"build_steps": True})
    for _ in range(2):
        proposals.note_request_failure(ws, "m1", PlannerUnavailable("not usable"))
    assert autopilot.needs_checks(ws) is None
    monkeypatch.setattr(proposals, "FORGIVEN_AFTER_S", -1)           # a long outage must not stall a project for good
    assert autopilot.needs_checks(ws) == "m1" and proposals.status(ws).get("m1") is None


def test_an_owner_withdrawing_checks_ends_the_count(tmp_path):
    ws = format_workspace(tmp_path)
    proposals.note_request_failure(ws, "g1", PlannerUnavailable("not usable"))
    assert proposals._record(ws, "g1")["request_failures"]["count"] == 1
    proposals.withdraw(ws, "g1", reason="These checks put the camera in the wrong place.")
    assert "request_failures" not in proposals._record(ws, "g1")
