from runesmith.app.workspace import Workspace
from runesmith.app.planner import source_context, draft_prompt, draft_files, PlannerUnavailable
from test_studio import scripted
import pytest


def planned(tmp_path):
    ws = Workspace(tmp_path)
    ws.set_brief('Build a useful local tool with tests.')
    ws.save_plan({'summary':'Tool', 'milestones':[{'title':'Step', 'done_when':'the command works'}]})
    return ws


def test_source_and_blueprints_are_in_draft_packet(tmp_path):
    ws = planned(tmp_path)
    (tmp_path/'tool.py').write_text('answer = 42\n')
    (tmp_path/'spec.md').write_text('Return the answer.')
    ws.set_brief(blueprints=['spec.md'])
    context = source_context(ws)
    prompt = draft_prompt(ws, ws.plan()['milestones'][0], context)
    assert 'answer = 42' in prompt and 'Return the answer.' in prompt
    assert '.runesmith' not in context['files']
    assert 'small exact edits for existing files' in prompt
    assert 'only new files require complete content' in prompt
    assert '8 files, each complete' not in prompt


def test_host_binds_source_and_reuses_waiting_draft(tmp_path):
    ws = planned(tmp_path)
    (tmp_path/'tool.py').write_text('x = 1\n')
    scripted(ws, [{'title':'Change', 'files':[{'path':'tool.py','content':'x = 2\n', 'base':'forged'}]}], roles=('plan',))
    router = ws.router()
    a = draft_files(ws, router)
    assert a['files'][0]['base'] == 'x = 1\n'
    assert draft_files(ws, router)['id'] == a['id']
    (tmp_path/'tool.py').write_text('x = 3\n')
    assert not ws.apply_draft(a['id'], overwrite=True)['ok']


def test_unseen_replacements_refused(tmp_path):
    ws = planned(tmp_path)
    (tmp_path/'large.py').write_text('x = 1\n'*7000)        # 42,000 bytes, over even the prioritized cap: shown in parts (J11-B15)
    scripted(ws, [{'title':'Blind edit','files':[{'path':'large.py','content':'x = 2'}]}], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='refused a whole-file replacement of large.py'):
        draft_files(ws, ws.router())


def test_a_file_no_part_of_which_can_be_shown_is_refused_in_plain_words(tmp_path):
    ws = planned(tmp_path)
    (tmp_path/'wide.py').write_text('x = 1; '*23000)        # one line of 161,000 characters: over the cap, too long to quote, so no part shows it
    scripted(ws, [{'title':'Blind edit','files':[{'path':'wide.py','content':'x = 2'}]}], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='wide.py is too large to show a model, even in parts'):
        draft_files(ws, ws.router())


def test_exact_build_edits_preserve_untouched_behavior(tmp_path):
    ws=planned(tmp_path)
    (tmp_path/'tool.py').write_text('def old_feature(): return 7\n\ndef value(): return 1\n')
    scripted(ws,[{'title':'Small edit','files':[{'path':'tool.py','edits':[
        {'old_text':'return 1','new_text':'return 2'}]}]}],roles=('plan',))
    draft=draft_files(ws,ws.router())
    assert draft['files'][0]['content']=='def old_feature(): return 7\n\ndef value(): return 2\n'
    assert draft['files'][0]['expected_sha256']
    assert not (tmp_path/'tool.py').read_text().endswith('return 2\n')


def test_draft_schema_survives_gateway_all_properties_required_transform():
    from runesmith.app.planner import DRAFT_SCHEMA
    # Reproduce the strict-schema contract without importing a local gateway
    # installation into the portable product's test suite.
    def strict(node):
        if isinstance(node,list):return [strict(n) for n in node]
        if not isinstance(node,dict):return node
        result={k:strict(v) for k,v in node.items()}
        if result.get('type')=='object' or 'properties' in result:
            result['additionalProperties']=False
            if result.get('properties'):result['required']=list(result['properties'])
        return result
    item=strict(DRAFT_SCHEMA)['properties']['files']['items']
    assert 'properties' not in item
    branches=item['anyOf']
    assert len(branches)==2
    assert {frozenset(b['required']) for b in branches}=={
        frozenset(('path','purpose','content')),frozenset(('path','purpose','edits'))}
    assert all(b['additionalProperties'] is False for b in branches)


@pytest.mark.parametrize('edits',[
    [{'old_text':'not in source','new_text':'new'}],
    [{'old_text':'1','new_text':'2'}],
    [],
])
def test_bad_exact_edit_never_silently_changes_source(tmp_path,edits):
    ws=planned(tmp_path);(tmp_path/'tool.py').write_text('x=11\n')
    scripted(ws,[{'title':'Bad edit','files':[{'path':'tool.py','edits':edits}]}],roles=('plan',))
    with pytest.raises(PlannerUnavailable,match='Exact edit'):draft_files(ws,ws.router())
    assert (tmp_path/'tool.py').read_text()=='x=11\n'


def test_exact_edit_refusal_retains_discriminating_source_feedback(tmp_path):
    from runesmith.app.building import build_step
    import json
    ws=planned(tmp_path);(tmp_path/'tool.py').write_text('# Existing command\nparser = make_parser()\nparser.add_argument("id")\n')
    scripted(ws,[{'title':'Mistaken old code','files':[{'path':'tool.py','edits':[
        {'old_text':'# Existing command\nmake_parser().add_argument("id")','new_text':'# new implementation'}]}]}],roles=('plan',))
    with pytest.raises(PlannerUnavailable):build_step(ws,ws.router())
    receipt=json.loads(next((ws.home/'build-attempts').glob('*.json')).read_text())
    assert receipt['feedback']['edit_index']==1
    assert 'parser = make_parser()' in receipt['feedback']['source_excerpt']
    assert 'source_excerpt' in draft_prompt(ws,ws.plan()['milestones'][0])
    assert (tmp_path/'tool.py').read_text().startswith('# Existing command\nparser =')


def test_invalid_later_file_edits_do_not_reuse_previous_file_index(tmp_path):
    ws=planned(tmp_path)
    (tmp_path/'first.py').write_text('first = 1\n')
    (tmp_path/'second.py').write_text('second = 1\n')
    scripted(ws,[{'title':'Malformed second file','files':[
        {'path':'first.py','edits':[{'old_text':'first = 1','new_text':'first = 2'}]},
        {'path':'second.py','edits':[{'old_text':'second = 1','new_text':'second = 2'}]*13},
    ]}],roles=('plan',))
    with pytest.raises(PlannerUnavailable,match='1-12 exact edits') as failure:
        draft_files(ws,ws.router())
    assert failure.value.feedback['path']=='second.py'
    assert 'edit_index' not in failure.value.feedback
    assert 'requested_old_text' not in failure.value.feedback
    assert (tmp_path/'first.py').read_text()=='first = 1\n'
    assert (tmp_path/'second.py').read_text()=='second = 1\n'


def test_new_file_cannot_overwrite_a_concurrent_creation(tmp_path):
    ws = planned(tmp_path)
    scripted(ws, [{'title':'New','files':[{'path':'new.py','content':'x = 2'}]}], roles=('plan',))
    draft = draft_files(ws, ws.router())
    (tmp_path/'new.py').write_text('someone else')
    assert not ws.apply_draft(draft['id'], overwrite=True)['ok']


def test_doing_milestone_precedes_open_and_done_is_refused(tmp_path):
    ws = planned(tmp_path)
    ws.save_plan({'milestones':[{'title':'later'}, {'title':'in progress','status':'doing'}]})
    scripted(ws, [{'title':'Now','files':[{'path':'x.py','content':'x=1'}]}], roles=('plan',))
    assert draft_files(ws, ws.router())['milestone'] == 'm2'
    ws.update_milestone('m2', {'status':'done'})
    with pytest.raises(PlannerUnavailable):
        draft_files(ws, ws.router(), 'm2')


def test_milliner_tags_survive_studio_configuration(tmp_path):
    ws = planned(tmp_path)
    ws.save_instrument('author', {'kind':'milliner', 'model':'openrouter:example/model',
        'base_url':'http://127.0.0.1:8765','caller_tag':'runesmith/supporthat','budget_tag':'field-training'},
        key_value='test-only-not-a-real-key', roles=['plan'])
    spec = ws.config()['instruments']['author']
    assert spec['caller_tag'] == 'runesmith/supporthat'
    assert spec['budget_tag'] == 'field-training'


def test_call_receipts_preserve_estimate_coverage_without_keys(tmp_path):
    ws = planned(tmp_path)
    ws.record_call({'instrument':'author','model':'example','ok':True,'latency_s':1,
                    'est_usd':0.01,'tokens_in':20,'tokens_out':30,'job_id':'job-1','secret':'never log me'})
    ws.record_call({'instrument':'author','model':'example','ok':False,'latency_s':1})
    stats = ws.call_stats()['author']
    assert stats['calls'] == 2 and stats['costed_calls'] == 1 and stats['estimated_usd'] == 0.01
    assert stats['tokens_in'] == 20
    events = ws.activity()
    event = next(e for e in events if e['data'].get('job_id') == 'job-1')
    assert event['kind'] == 'instrument.call'
    assert 'secret' not in event['data']


def test_revision_packet_contains_unapplied_candidate_code(tmp_path):
    ws=planned(tmp_path)
    scripted(ws,[{'title':'new command','files':[{'path':'new_cli.py','content':'def command(): return 7'}]}],roles=('plan',))
    draft=draft_files(ws,ws.router())
    ws._save_draft_state(draft,'needs_revision',verification={'status':'failed','detail':'expected 8'})
    prompt=draft_prompt(ws,ws.plan()['milestones'][0])
    assert 'def command(): return 7' in prompt and 'expected 8' in prompt
    assert not (tmp_path/'new_cli.py').exists()


def test_revision_packet_uses_public_owner_failures_without_private_traces(tmp_path):
    ws=planned(tmp_path)
    (tmp_path/'tool.py').write_text('def command(): return 7\n')
    scripted(ws,[{'title':'candidate','files':[{'path':'tool.py','content':'def command(): return 8\n'}]}],roles=('plan',))
    draft=draft_files(ws,ws.router())
    ws._save_draft_state(draft,'needs_revision',verification={
        'status':'failed',
        'public_contracts':[{'criteria':[{'id':'list.links','description':'Listing exposes stored source IDs.'}]}],
        'project_checks':{'status':'passed','ran':20,'output':'P'*9000},
        'acceptance':{'status':'failed','ran':2,'failures':2,'output':'HIDDEN_NOISE'*900,
            'failure_details':[
                {'test':'acceptance.links','trace_tail':'reject missing source'},
                {'test':'acceptance.list','trace_tail':'PRIVATE_FIXTURE','criteria':['list.links']},
            ]},
    })
    prompt=draft_prompt(ws,ws.plan()['milestones'][0])
    assert 'Failure not localized' in prompt
    assert 'list.links' in prompt and 'Listing exposes stored source IDs.' in prompt
    assert 'reject missing source' not in prompt and 'PRIVATE_FIXTURE' not in prompt
    assert 'every listed owner-acceptance failure' in prompt
    assert 'HIDDEN_NOISE' not in prompt and 'P'*100 not in prompt


def test_revision_can_patch_candidate_bytes_and_retains_omitted_candidate_files(tmp_path):
    ws=planned(tmp_path)
    (tmp_path/'tool.py').write_text('def command():\n    return 7\n')
    scripted(ws,[{'title':'candidate','files':[
        {'path':'tool.py','content':'def command():\n    value = 8\n    return value\n'},
        {'path':'tests/test_tool.py','content':'from tool import command\ndef test_command(): assert command() == 8\n'},
    ]}],roles=('plan',))
    first=draft_files(ws,ws.router())
    ws._save_draft_state(first,'needs_revision',verification={'status':'failed','detail':'also expose the value'})
    scripted(ws,[{'title':'candidate patch','files':[{'path':'tool.py','edits':[
        {'old_text':'    value = 8\n    return value','new_text':'    value = 9\n    return value'}]}]}],roles=('plan',))
    second=draft_files(ws,ws.router())
    by_path={f['path']:f for f in second['files']}
    assert by_path['tool.py']['content']=='def command():\n    value = 9\n    return value\n'
    assert by_path['tool.py']['base']=='def command():\n    return 7\n'
    assert by_path['tests/test_tool.py']['retained_from']==first['id']
    assert by_path['tests/test_tool.py']['content'].endswith('command() == 8\n')


def test_revision_prefers_candidate_when_edit_also_matches_live_source(tmp_path):
    from runesmith.app.planner import admit_revision_answer
    ws=planned(tmp_path)
    (tmp_path/'tool.py').write_text('def answer(): return 7\n')
    candidate={'id':'prior','files':[{'path':'tool.py','content':'def answer(): return 7\ndef added(): return 8\n'}]}
    files=admit_revision_answer(ws,source_context(ws),[{'path':'tool.py','edits':[
        {'old_text':'return 7','new_text':'return 9'}]}],candidate)
    assert files[0]['revision_base']=='candidate'
    assert 'def added(): return 8' in files[0]['content']


def test_revision_can_edit_a_new_unapplied_file_without_inventing_live_base(tmp_path):
    from runesmith.app.planner import admit_revision_answer
    ws=planned(tmp_path)
    candidate={'id':'new-file','files':[{'path':'new.py','content':'def answer(): return 7\n'}]}
    files=admit_revision_answer(ws,source_context(ws),[{'path':'new.py','edits':[
        {'old_text':'return 7','new_text':'return 9'}]}],candidate)
    assert files[0]['content']=='def answer(): return 9\n'
    assert files[0]['revision_base']=='candidate' and files[0]['expected_absent']
    assert 'base' not in files[0] and not (tmp_path/'new.py').exists()



def test_a_javascript_module_is_a_source_file_a_draft_may_write():
    # Journey J11-B5: the first draft of Runesmith Motion wrote motion.mjs, "outside the local verification profile",
    # so it could not be checked and nothing could ever be applied.
    from runesmith.app.snapshots import path_kind
    assert [path_kind(p) for p in ("motion.mjs", "lib/tool.cjs", "src/a.mts", "app.js")] == ["model"] * 4


def test_a_prerequisite_builder_sees_the_checks_approved_for_its_goal(tmp_path):
    # Journey J2-G2: the "Integrate export command" step's builder chose `export --output`; the checks approved for its
    # goal (Export library to CSV) run `export --file`, which it never saw.
    from runesmith.app.acceptance_contracts import publish_expectations
    from runesmith.app.workspace import _write_json
    ws = planned(tmp_path)
    ws.save_plan({'summary': 'Tool', 'milestones': [{'title': 'Export', 'done_when': 'export works'},
                                                     {'title': 'CLI step', 'done_when': 'the command runs'}]})
    plan = ws.plan()
    goal, step = plan['milestones']
    step['parent_id'] = goal['id']
    _write_json(ws.home / 'PLAN.json', plan)
    said = 'Exporting writes a CSV file. Checked exactly: running `python -m tool export --file books.csv`.'
    publish_expectations(ws, goal['id'], [{'id': 'check.test_01_export', 'description': said}], 'approved by the owner')
    assert 'export --file books.csv' in draft_prompt(ws, ws.plan()['milestones'][1])
    assert 'parent_public_acceptance' in draft_prompt(ws, ws.plan()['milestones'][0])       # null for a goal itself


def test_a_refusal_for_quoting_the_output_shows_the_code_and_says_so(tmp_path):
    # Journey J11-G28: the model quoted the SVG the program writes; those lines are pieces of string literals in the
    # code, the refusal showed no source, and the model repeated the mistake four times.
    from runesmith.app.building import build_step
    import json
    ws=planned(tmp_path);(tmp_path/'tool.py').write_text("out = ''\nout += '  <defs>\\n'\nout += '    <filter id=\"glow\"/>\\n'\nout += '  </defs>\\n'\n")
    scripted(ws,[{'title':'Quoted output','files':[{'path':'tool.py','edits':[
        {'old_text':'    <filter id="glow"/>\n  </defs>','new_text':'x'}]}]}],roles=('plan',))
    with pytest.raises(PlannerUnavailable):build_step(ws,ws.router())
    receipt=json.loads(next((ws.home/'build-attempts').glob('*.json')).read_text())
    assert '<filter id="glow"/>' in receipt['feedback']['source_excerpt']
    assert 'only inside a longer line' in receipt['feedback']['hint'] and 'not the text the program writes' in receipt['feedback']['hint']


def test_stale_code_that_is_part_of_a_longer_line_gets_no_output_hint(tmp_path):
    # Verifier of J11-G28: "self.value = 10" against "self.value = 100" is stale code, not the program's output.
    from runesmith.app.building import build_step
    import json
    ws=planned(tmp_path);(tmp_path/'tool.py').write_text("class A:\n    def f(self):\n        self.value = 100\n        self.count = 200\n")
    scripted(ws,[{'title':'Stale code','files':[{'path':'tool.py','edits':[
        {'old_text':'        self.value = 10\n        self.count = 20','new_text':'x'}]}]}],roles=('plan',))
    with pytest.raises(PlannerUnavailable):build_step(ws,ws.router())
    receipt=json.loads(next((ws.home/'build-attempts').glob('*.json')).read_text())
    assert 'hint' not in receipt['feedback'] and 'self.value = 100' in receipt['feedback']['source_excerpt']


def test_a_model_that_repeats_a_refused_edit_is_asked_last(tmp_path):
    # Journey J11-G31: Gemini Flash Lite sent Surfaces the same refused edit six times, always asked first.
    import json as _json
    import os
    from types import SimpleNamespace
    from runesmith.app.planner import _rotate_repeating_author
    home = tmp_path / "home"
    (home / "build-attempts").mkdir(parents=True)
    (home / "draft-answers").mkdir()
    logged = []
    ws = SimpleNamespace(home=home, ledger=SimpleNamespace(append=lambda kind, data: logged.append((kind, data))),
                         config=lambda: {"instruments": {
                             "a": {"model": "g:lite", "fallback_models": ["g2:lite"]},
                             "b": {"model": "n:tron"},
                             "c": {"kind": "openai", "model": "google/lite:free", "base_url": "https://or.example/v1"}}})
    clock = [0]

    def attempt(n, old=None, author=None, instrument=None, utc=None, state="failed"):
        receipt = f"draft-answers/d{n}.json"
        if author is not None:
            (home / "draft-answers" / f"d{n}.json").write_text(_json.dumps(
                {"author": author, "receipt": {"instrument": instrument} if instrument else None}), encoding="utf-8")
        feedback = {"requested_old_text": old, "answer_receipt": receipt} if old is not None else None
        path = home / "build-attempts" / f"{n}.json"
        path.write_text(_json.dumps({"contract": "k", "utc": utc or f"2026-09-29T10:{n:02d}:00Z", "state": state,
                                     "error": "Exact edit refused" if old else "no answer", "feedback": feedback}),
                        encoding="utf-8")
        clock[0] += 1
        os.utime(path, ns=(clock[0] * 10**9, clock[0] * 10**9))
    router = lambda: SimpleNamespace(roles={"plan": ["a", "b", "c"]})
    attempt(1, "<filter/>", "g:lite", "a")
    first = router()
    assert _rotate_repeating_author(ws, first, "k") is None and first.roles["plan"] == ["a", "b", "c"]   # once
    attempt(2, state="transport_failed")                                      # nothing answered: does not count
    attempt(3, "<filter/>", "g2:lite", "a")                                   # the same instrument by another route
    again = router()
    assert _rotate_repeating_author(ws, again, "k") == ["a"] and again.roles["plan"] == ["b", "c", "a"]
    assert logged[-1][1]["asked_last"] == ["a"] and logged[-1][1]["instruments"] == ["a", "a"]
    assert _rotate_repeating_author(ws, router(), "another milestone") is None
    alone = SimpleNamespace(roles={"plan": ["a"]})
    assert _rotate_repeating_author(ws, alone, "k") is None and alone.roles["plan"] == ["a"]       # never removed
    attempt(4, "<filter/>", "n:tron", "b")
    assert _rotate_repeating_author(ws, router(), "k") is None               # two different instruments
    attempt(5, "<g/>", "n:tron", "b")
    assert _rotate_repeating_author(ws, router(), "k") is None               # a different edit: it is trying
    # An OpenAI-compatible answer kept without its instrument: its model string starts with the base URL (review).
    attempt(6, "<h/>", "https://or.example/v1:google/lite:free", utc="2026-09-29T10:59:00Z")
    attempt(7, "<h/>", "https://or.example/v1:google/lite:free", utc="2026-09-29T10:59:00Z")   # the same second
    assert _rotate_repeating_author(ws, router(), "k") == ["c"]
    attempt(8, "<h/>", utc="2026-09-29T10:59:30Z")                            # its answer file was never kept
    (home / "build-attempts" / "9.json").write_text(_json.dumps({
        "contract": "k", "utc": "2026-09-29T10:59:40Z", "state": "failed", "error": "x",
        "feedback": {"requested_old_text": "<h/>", "answer_receipt": "../../secret.json"}}), encoding="utf-8")
    assert _rotate_repeating_author(ws, router(), "k") is None               # only a receipt under draft-answers


def crowded(root):
    """A project where huge.js is left out of what models are shown: the pads, read first, leave it less room than a
    part needs (4,000 characters). The pads are 20,000, 20,000 and 5,000 bytes, huge.js 28,000: under every cap, and
    together over the 48,000-character source budget."""
    for name, lines in (("a_pad.js", 4000), ("b_pad.js", 4000), ("c_pad.js", 1000), ("huge.js", 5600)):
        (root / name).write_bytes(b"// y\n" * lines)


EDIT_HUGE = {"title": "Edit", "files": [{"path": "huge.js", "edits": [{"old_text": "// y", "new_text": "// z"}]}]}


def test_a_program_over_the_normal_cap_is_still_shown_when_the_budget_has_room(tmp_path):
    # Journey J11-B15: motion.mjs grew past 20,000 bytes, was never shown again, and every build that edited it was
    # refused until all tries were used up and J11 stood still for two days.
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import DEFAULT_FILE_BYTES, select_context
    ws = planned(tmp_path)
    (tmp_path / "motion.mjs").write_bytes(b"// x\n" * ((DEFAULT_FILE_BYTES + 400) // 5))
    (tmp_path / "small.js").write_bytes(b"export const a = 1;\n")
    context = select_context(ws, collect_snapshot(ws))
    assert "motion.mjs" in context["files"] and "small.js" in context["files"]          # over the normal cap, shown
    assert context["omission_reasons"] == {}


def test_a_file_that_can_never_be_shown_is_an_ordinary_refusal_that_says_what_to_change(tmp_path):
    # Review of J11-B15: waiting for the owner to prioritize such a file left the milestone stuck, since the Author
    # context refuses a file over 40,000 bytes or one that is not UTF-8. It stays a failed try, in plain words.
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import FOCUSED_FILE_BYTES, select_context
    from runesmith.app.planner import admit_answer_files, settled_state
    ws = planned(tmp_path)
    (tmp_path / "huge.js").write_bytes(b"// y " * ((FOCUSED_FILE_BYTES + 400) // 5))     # one line, too long to quote: no part shows it
    (tmp_path / "wide.js").write_bytes("var a = 1;\n".encode("utf-16"))
    context = select_context(ws, collect_snapshot(ws))
    assert context["omission_reasons"] == {"huge.js": "file_limit", "wide.js": "not_utf8"}
    for name, words, remedy in (("huge.js", "is too large to show a model", "Split it into smaller files"),
                                ("wide.js", "is not UTF-8 text", "Save it as UTF-8 text")):
        for answer in ({"path": name, "edits": [{"old_text": "a", "new_text": "b"}]}, {"path": name, "content": "// whole\n"}):
            with pytest.raises(PlannerUnavailable, match=f"{name} {words}") as refused:
                admit_answer_files(ws, context, [answer])
            assert remedy in str(refused.value)
            assert not getattr(refused.value, "context_gap", None) and settled_state(refused.value) == "failed"
            assert "path" not in refused.value.feedback and refused.value.feedback["not_shown"] == name


def test_a_file_the_budget_left_out_is_a_gap_the_owner_can_close(tmp_path, old_caps):
    # Journey J11-B15: the other files filled the source budget; prioritizing the file shows it, so such a refusal
    # uses up no try.
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import save_focus, select_context
    from runesmith.app.planner import admit_answer_files, settled_state
    ws = planned(tmp_path)
    crowded(tmp_path)
    context = select_context(ws, collect_snapshot(ws))
    assert "a_pad.js" in context["files"] and context["omission_reasons"] == {"huge.js": "packet_budget"}
    for answer in (EDIT_HUGE["files"][0], {"path": "huge.js", "content": "// whole\n"}):
        with pytest.raises(PlannerUnavailable, match="huge.js was not shown to the model") as refused:
            admit_answer_files(ws, context, [answer])
        assert refused.value.context_gap == {"path": "huge.js", "reason": "packet_budget"}
        assert settled_state(refused.value) == "context_gap" and "Prioritize huge.js" in str(refused.value)
    save_focus(ws, ["huge.js"], collect_snapshot(ws)["digest"], "Builds of this milestone edit it")
    assert "huge.js" in source_context(ws)["files"]                                    # the remedy works


def test_a_retained_selection_says_why_each_file_was_left_out(tmp_path):
    # Review of J11-B15: a late answer is admitted against its recorded selection, which kept no reasons, so every
    # file read "packet_budget", a file over the limit or not UTF-8 included.
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import FOCUSED_FILE_BYTES, recorded_context
    from runesmith.app.planner import admit_answer_files
    ws = planned(tmp_path)
    (tmp_path / "small.js").write_bytes(b"export const a = 1;\n")
    (tmp_path / "big.js").write_bytes(b"// y\n" * 5600)
    (tmp_path / "huge.js").write_bytes(b"// y\n" * ((FOCUSED_FILE_BYTES + 400) // 5))
    (tmp_path / "wide.js").write_bytes("var a = 1;\n".encode("utf-16"))
    context = recorded_context(collect_snapshot(ws), ["small.js"])
    assert context["omission_reasons"] == {"big.js": "packet_budget", "huge.js": "file_limit", "wide.js": "not_utf8"}
    edit = {"edits": [{"old_text": "a", "new_text": "b"}]}
    with pytest.raises(PlannerUnavailable, match="huge.js is too large") as refused:
        admit_answer_files(ws, context, [dict(edit, path="huge.js")])
    assert not getattr(refused.value, "context_gap", None)
    with pytest.raises(PlannerUnavailable, match="wide.js is not UTF-8") as refused:
        admit_answer_files(ws, context, [dict(edit, path="wide.js")])
    assert not getattr(refused.value, "context_gap", None)
    with pytest.raises(PlannerUnavailable, match="big.js was not shown") as refused:
        admit_answer_files(ws, context, [dict(edit, path="big.js")])
    assert refused.value.context_gap == {"path": "big.js", "reason": "packet_budget"}


def test_a_try_refused_for_an_unshown_file_uses_nothing_and_the_milestone_waits(tmp_path):
    # Journey J11-B15: such refusals used up every try; now they use none, and the milestone waits for the owner.
    import json as _json
    from runesmith.app.author_allowance import ordinary_allowance
    from runesmith.app.building import _context_gap
    from runesmith.app.planner import milestone_contract
    ws = planned(tmp_path)
    milestone = ws.plan()["milestones"][0]
    contract = milestone_contract(ws, milestone)
    snapshot = "a" * 64
    (ws.home / "build-attempts").mkdir(parents=True, exist_ok=True)
    (ws.home / "build-attempts" / "g1.json").write_text(_json.dumps({
        "scope": "b" * 64, "contract": contract, "context_digest": "c" * 64, "snapshot_digest": snapshot,
        "state": "context_gap", "utc": "2026-10-01T16:00:00Z", "error": "PlannerUnavailable: motion.mjs was not shown",
        "feedback": {"not_shown": "motion.mjs", "reason": "packet_budget"}}), encoding="utf-8")
    assert ordinary_allowance(ws, contract, snapshot)["used"] == 0
    assert _context_gap(ws, contract, {"snapshot_digest": snapshot, "files": {}}) == "motion.mjs"
    assert _context_gap(ws, contract, {"snapshot_digest": snapshot, "files": {"motion.mjs": "x"}}) is None   # shown now
    assert _context_gap(ws, contract, {"snapshot_digest": "d" * 64, "files": {}}) is None                     # other source


def gap_project(tmp_path, answers):
    ws = planned(tmp_path)
    ws.update_settings({"build_steps": True, "build_apply": True, "build_paths": ["app.py", "tests", "huge.js"]})
    crowded(tmp_path)
    scripted(ws, answers, roles=("plan",))
    return ws


def counting(router):
    calls = []
    real = router.call
    router.call = lambda *args, **kwargs: (calls.append(1), real(*args, **kwargs))[1]
    return calls


def tries_used(ws):
    from runesmith.app.author_allowance import ordinary_allowance
    from runesmith.app.planner import milestone_contract
    contract = milestone_contract(ws, ws.plan()["milestones"][0])
    return ordinary_allowance(ws, contract, source_context(ws)["snapshot_digest"])["used"]


def test_a_build_refused_for_an_unshown_file_uses_no_try_and_shows_it_in_the_next_round(tmp_path, old_caps):
    # Journey J11-B15, end to end: no try used; the next round shows the file (it is wanted: the owner is not needed, and
    # a source change no longer makes another call that is refused the same way), and its edit is judged like any other.
    from runesmith.app.building import build_step
    ws = gap_project(tmp_path, [EDIT_HUGE] * 4)
    router = ws.router()
    calls = counting(router)
    with pytest.raises(PlannerUnavailable, match="huge.js was not shown"):
        build_step(ws, router)
    assert tries_used(ws) == 0 and len(calls) == 1
    with pytest.raises(PlannerUnavailable, match="Exact edit refused for huge.js"):
        build_step(ws, router)
    assert len(calls) == 2 and tries_used(ws) == 1


def test_a_draft_that_waits_is_checked_although_an_older_answer_was_refused_for_an_unshown_file(tmp_path, old_caps):
    # Review of J11-B15: the stale refusal was looked at before the waiting draft, so a draft the owner made on the
    # same source was never checked.
    from runesmith.app.building import build_step
    from runesmith.app.planner import draft_files
    good = {"title": "Good", "files": [{"path": "app.py", "content": "def answer():\n    return 42\n"}]}
    ws = gap_project(tmp_path, [EDIT_HUGE])
    with pytest.raises(PlannerUnavailable, match="huge.js was not shown"):
        build_step(ws, ws.router())
    scripted(ws, [good], roles=("plan",))
    waiting = draft_files(ws, ws.router(), "m1")
    assert waiting["state"] == "waiting"
    result = build_step(ws, ws.router())
    assert result["draft"] == waiting["id"] and "verification" in result and "not shown" not in result["summary"]


def test_the_one_more_try_refused_for_an_unshown_file_is_not_used_up(tmp_path, old_caps):
    # Review of J11-B15: escalate_build recorded such a refusal as a used "failed" try.
    import json as _json
    import uuid
    from runesmith.app.building import build_escalation_status, escalate_build
    from runesmith.app.author_allowance import ordinary_allowance
    from runesmith.app.planner import milestone_contract
    ws = gap_project(tmp_path, [EDIT_HUGE] * 2)
    contract = milestone_contract(ws, ws.plan()["milestones"][0])
    context = source_context(ws)
    scope = ordinary_allowance(ws, contract, context["snapshot_digest"])["scope"]
    (ws.home / "build-attempts").mkdir(parents=True, exist_ok=True)
    for n in range(3):
        (ws.home / "build-attempts" / (uuid.uuid4().hex + ".json")).write_text(_json.dumps({
            "scope": scope, "contract": contract, "context_digest": "c" * 64, "snapshot_digest": context["snapshot_digest"],
            "state": "failed", "utc": f"2026-10-01T10:0{n}:00Z", "error": "x"}), encoding="utf-8")
    assert build_escalation_status(ws)["eligible"]
    with pytest.raises(PlannerUnavailable, match="huge.js was not shown"):
        escalate_build(ws, ws.router())
    assert [_json.loads(p.read_text())["state"] for p in (ws.home / "build-escalations").glob("*.json")] == ["context_gap"]
    state = build_escalation_status(ws)
    assert state["eligible"] and not state["used"]


def test_a_correction_refused_for_an_unshown_file_is_not_counted(tmp_path, old_caps):
    # Review of J11-B15: the refusal was recorded as "refused" and spent one of the two corrections.
    import json as _json
    from runesmith.app.build_corrections import _corrections, correct_rejected_answer, correction_candidates
    from runesmith.app.building import build_step
    first = {"title": "Two", "files": [{"path": "app.py", "edits": [{"old_text": "x = 99", "new_text": "x = 2"}]},
                                       EDIT_HUGE["files"][0]]}
    fixed = {"title": "Two", "why": "w", "files": [{"path": "app.py", "edits": [{"old_text": "x = 1", "new_text": "x = 2"}]},
                                                   EDIT_HUGE["files"][0]]}
    ws = gap_project(tmp_path, [first])
    (tmp_path / "app.py").write_bytes(b"x = 1\n")
    with pytest.raises(PlannerUnavailable, match="Exact edit refused for app.py"):
        build_step(ws, ws.router())
    attempt = correction_candidates(ws)[0]["attempt"]
    scripted(ws, [fixed], roles=("plan",))
    with pytest.raises(PlannerUnavailable, match="huge.js was not shown"):
        correct_rejected_answer(ws, ws.router(), attempt)
    assert [_json.loads(p.read_text())["state"] for p in (ws.home / "build-corrections").glob("*.json")] == ["context_gap"]
    assert _corrections(ws, attempt) == []
    row = correction_candidates(ws)[0]
    assert row["remaining"] == 2 and row["eligible"]


def marked(root):
    """crowded() with four files an answer can need, each 39,000 bytes with a first line of its own so an edit can
    name it once: the pads leave them no room, and prioritized, they fill the budget (one whole, two in parts of 4,000
    characters each, none for the fourth)."""
    crowded(root)
    for name in ("huge.js", "mid.js", "tall.js", "wide.js"):
        (root / name).write_bytes(f"// {name}\n".encode() + b"// y\n" * 7790)


def test_files_that_cannot_be_shown_together_are_no_gap_the_owner_can_close(tmp_path, old_caps):
    # Review of J11-B15: each time the owner prioritized the file named, another became the gap, until Author context
    # refused the whole list; the milestone then waited forever, and used no try, so no replan was ever asked. With
    # parts (DD) it takes four files of this size: one whole, two in the 9,000 characters left, none for the fourth.
    from runesmith.app.building import build_step
    every = {"title": "All", "files": [{"path": name, "edits": [{"old_text": f"// {name}", "new_text": "// one"}]}
                                       for name in ("huge.js", "mid.js", "tall.js", "wide.js")]}
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir(), second.mkdir()
    ws = gap_project(first, [every] * 5)
    marked(first)
    router = ws.router()
    for _ in range(3):
        with pytest.raises(PlannerUnavailable, match="do not fit the source budget together"):
            build_step(ws, router)
    assert tries_used(ws) == 3
    assert build_step(ws, router).get("replan_needed")                       # the way out: smaller steps
    # a gap the next round closes is no try, and the next round builds
    only = {"title": "Only", "files": [{"path": "huge.js", "edits": [{"old_text": "// huge.js", "new_text": "// one"}]}]}
    ws2 = gap_project(second, [only] * 2)
    marked(second)
    with pytest.raises(PlannerUnavailable, match="was not shown to the model"):
        build_step(ws2, ws2.router())
    assert tries_used(ws2) == 0
    assert build_step(ws2, ws2.router(), author_only=True)["draft"] and tries_used(ws2) == 1


def test_a_retained_candidate_file_that_is_no_longer_shown_is_the_same_uncounted_gap(tmp_path, old_caps):
    # Review of J11-B15: an answer that edits only one file of a candidate retains the others; one the budget no longer
    # shows was refused as a counted failed try with no remedy, where an edit to it is an uncounted gap.
    import json as _json
    from runesmith.app.building import build_step
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import save_focus
    ws = planned(tmp_path)
    ws.update_settings({"build_steps": True, "build_apply": True, "build_paths": ["a.js", "b_y.js", "c_x.js"]})
    (tmp_path / "a.js").write_bytes(b"// MARK\n")
    for name, lines in (("b_y.js", 4000), ("b_z.js", 4000), ("b_zz.js", 1000), ("c_x.js", 5600)):
        (tmp_path / name).write_bytes(b"// MARK\n" + b"// y\n" * lines)
    save_focus(ws, ["c_x.js"], collect_snapshot(ws)["digest"], "Needs it")
    first = {"title": "First", "files": [{"path": "a.js", "edits": [{"old_text": "// MARK", "new_text": "// one"}]},
                                         {"path": "c_x.js", "edits": [{"old_text": "// MARK", "new_text": "// one"}]}]}
    scripted(ws, [first], roles=("plan",))
    candidate = ws._draft(build_step(ws, ws.router(), author_only=True)["draft"])
    ws._save_draft_state(candidate, "needs_revision")
    save_focus(ws, [], collect_snapshot(ws)["digest"], "Clear it")               # c_x.js no longer fits beside the b_ files
    retain = {"title": "Retain", "files": [{"path": "a.js", "edits": [{"old_text": "// MARK", "new_text": "// two"}]}]}
    scripted(ws, [retain], roles=("plan",))
    used = tries_used(ws)
    with pytest.raises(PlannerUnavailable, match="c_x.js was not shown to the model"):
        build_step(ws, ws.router())
    states = sorted(_json.loads(p.read_text())["state"] for p in (ws.home / "build-attempts").glob("*.json"))
    assert states == ["answered", "context_gap"] and tries_used(ws) == used
    assert build_step(ws, ws.router(), author_only=True)["draft"]            # the next round shows c_x.js: admitted now
    assert tries_used(ws) == used + 1


def two_steps(tmp_path):
    ws = planned(tmp_path)
    ws.save_plan({"summary": "Tool", "milestones": [{"title": "Other", "done_when": "other.py exists"},
                                                     {"title": "Motion", "done_when": "motion.mjs changes"}]})
    ws.update_settings({"build_steps": True, "build_apply": True, "build_paths": ["other.py", "motion.mjs"]})
    return ws


def tries_of(ws, milestone_id):
    from runesmith.app.author_allowance import ordinary_allowance
    from runesmith.app.planner import milestone_contract
    milestone = next(m for m in ws.plan()["milestones"] if m["id"] == milestone_id)
    return ordinary_allowance(ws, milestone_contract(ws, milestone), source_context(ws)["snapshot_digest"])["used"]


def test_a_prioritized_file_that_outgrows_the_limit_is_shown_in_parts_and_still_changeable(tmp_path, old_caps):
    # Journey J11-B15, with excerpts: the owner prioritized motion.mjs as the remedy said and it grew past 40,000 bytes;
    # it was an omitted file that no milestone could change. It is shown in parts now, and an edit inside a shown part
    # is admitted, with a try used only where a model answered.
    from runesmith.app.building import build_step
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import FOCUSED_FILE_BYTES, save_focus
    ws = two_steps(tmp_path)
    (tmp_path / "motion.mjs").write_bytes(b"// MARK\n" + b"// y\n" * 7990)           # 39,958 bytes: prioritized
    save_focus(ws, ["motion.mjs"], collect_snapshot(ws)["digest"], "Builds of this milestone edit it")
    (tmp_path / "motion.mjs").write_bytes(b"// MARK\n" + b"// y\n" * 8010)           # an applied draft grew it past the limit
    assert (tmp_path / "motion.mjs").stat().st_size > FOCUSED_FILE_BYTES
    context = source_context(ws)
    assert "motion.mjs" in context["excerpts"] and "motion.mjs" not in context["files"] and not context["focus_errors"]
    scripted(ws, [{"title": "Motion", "files": [{"path": "motion.mjs", "edits": [{"old_text": "// MARK", "new_text": "// z"}]}]}],
             roles=("plan",))
    draft = ws._draft(build_step(ws, ws.router(), milestone_id="m2", author_only=True)["draft"])
    assert draft["files"][0]["content"].startswith("// z\n") and "motion.mjs" in draft["shown_excerpts"]
    assert draft["shown_files"] == ["other.py"] or "motion.mjs" not in draft["shown_files"]


def test_a_prioritized_file_no_part_of_which_can_be_shown_blocks_only_the_milestones_that_edit_it(tmp_path, old_caps):
    # Review of J11-B15 (verification round): the owner prioritized motion.mjs as the remedy said, it became a file no
    # part of which can be shown (here one line too long to quote), and every milestone was blocked, also the ones that
    # never touch it. It is an omitted file: a milestone that edits it is refused in words naming it, and no try is used
    # without a model asked.
    from runesmith.app.building import build_step
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import FOCUSED_FILE_BYTES, save_focus
    ws = two_steps(tmp_path)
    (tmp_path / "motion.mjs").write_bytes(b"// MARK " + b"// y " * 7990)             # one line of 39,958 bytes: prioritized
    save_focus(ws, ["motion.mjs"], collect_snapshot(ws)["digest"], "Builds of this milestone edit it")
    (tmp_path / "motion.mjs").write_bytes(b"// MARK " + b"// y " * 8010)             # an applied draft grew it past the limit
    assert (tmp_path / "motion.mjs").stat().st_size > FOCUSED_FILE_BYTES
    calls = []

    def asked(answer):
        scripted(ws, [answer], roles=("plan",))
        router = ws.router()
        real = router.call
        router.call = lambda *args, **kwargs: (calls.append(1), real(*args, **kwargs))[1]
        return router
    other = asked({"title": "Other", "files": [{"path": "other.py", "content": "x = 1\n"}]})
    assert build_step(ws, other, milestone_id="m1", author_only=True)["draft"]       # it never touches the file: it proceeds
    edits = asked({"title": "Motion", "files": [{"path": "motion.mjs", "edits": [{"old_text": "// MARK", "new_text": "// z"}]}]})
    with pytest.raises(PlannerUnavailable, match="motion.mjs is too large to show a model") as refused:
        build_step(ws, edits, milestone_id="m2")
    assert "prioritized under Author context" in str(refused.value) and "Split it" in str(refused.value)
    assert len(calls) == 2 and tries_of(ws, "m1") + tries_of(ws, "m2") == len(calls)  # a try only where a model answered


def test_a_prioritized_path_that_is_gone_blocks_without_a_try_and_is_named(tmp_path):
    # Review of J11-B15: no call is made while the owner's own selection names a file that is gone, and the summary of
    # several blocked milestones names it (it only said "a prioritized file"); a milestone whose tries are used up still
    # asks for smaller steps instead of reporting the file.
    import json as _json
    import uuid
    from runesmith.app.author_allowance import ordinary_allowance
    from runesmith.app.building import build_step
    from runesmith.app.planner import milestone_contract, settled_state
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import save_focus
    ws = two_steps(tmp_path)
    (tmp_path / "motion.mjs").write_bytes(b"// MARK\n")
    save_focus(ws, ["motion.mjs"], collect_snapshot(ws)["digest"], "Builds edit it")
    (tmp_path / "motion.mjs").unlink()
    scripted(ws, [{"title": "x", "files": [{"path": "other.py", "content": "x = 1\n"}]}] * 4, roles=("plan",))
    router = ws.router()
    calls = counting(router)
    result = build_step(ws, router)
    assert "motion.mjs is prioritized but not a file models can be shown" in result["summary"]
    assert len(calls) == 0 and not list((ws.home / "build-attempts").glob("*.json"))
    with pytest.raises(PlannerUnavailable, match="motion.mjs is prioritized under Author context") as refused:
        draft_files(ws, router)
    assert settled_state(refused.value) == "context_gap" and "Remove it from the prioritized files" in str(refused.value)
    milestone = ws.plan()["milestones"][0]
    contract, snapshot = milestone_contract(ws, milestone), source_context(ws)["snapshot_digest"]
    scope = ordinary_allowance(ws, contract, snapshot)["scope"]
    (ws.home / "build-attempts").mkdir(parents=True, exist_ok=True)
    for n in range(3):
        (ws.home / "build-attempts" / (uuid.uuid4().hex + ".json")).write_text(_json.dumps({
            "scope": scope, "contract": contract, "context_digest": "c" * 64, "snapshot_digest": snapshot,
            "state": "failed", "utc": f"2026-10-01T10:0{n}:00Z", "error": "x"}), encoding="utf-8")
    assert build_step(ws, router, milestone_id="m1").get("replan_needed")


def test_a_candidate_hidden_from_the_prompt_is_not_merged_into_the_next_draft(tmp_path):
    # Review of J11-G37 (fresh review): draft_files chose the candidate to retain by a rule without the expectations
    # test the prompt uses, so a candidate the model was never shown still had its files merged into the next draft.
    import json as _json
    from runesmith.app.acceptance_contracts import publish_expectations
    ws = planned(tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    publish_expectations(ws, "m1", [{"id": "c1", "description": "It prints hello."}], "first")
    first = {"title": "First", "files": [{"path": "app.py", "edits": [{"old_text": "x = 1", "new_text": "x = 2"}]},
                                         {"path": "legacy.py", "content": "OLD_BEHAVIOUR = True\n"}]}
    scripted(ws, [first], roles=("plan",))
    d1 = draft_files(ws, ws.router())
    ws._save_draft_state(ws._draft(d1["id"]), "needs_revision")
    assert _json.loads(draft_prompt(ws, ws.plan()["milestones"][0], source_context(ws)))["candidate_to_revise"]["id"] == d1["id"]
    publish_expectations(ws, "m1", [{"id": "c1", "description": "It prints goodbye instead."}], "second")
    assert _json.loads(draft_prompt(ws, ws.plan()["milestones"][0], source_context(ws)))["candidate_to_revise"] is None
    scripted(ws, [{"title": "Second", "files": [{"path": "app.py", "edits": [{"old_text": "x = 1", "new_text": "x = 3"}]}]}],
             roles=("plan",))
    second = draft_files(ws, ws.router())
    assert [f["path"] for f in second["files"]] == ["app.py"]                # nothing retained from the hidden candidate


def test_the_lineage_guard_counts_only_the_candidate_a_build_would_revise(tmp_path, monkeypatch):
    # Review of J11-G37 (fresh review): the guard picked its candidate by a third rule.
    from runesmith.app import author_revisions, building
    from runesmith.app.acceptance_contracts import expectation_digest, publish_expectations
    from runesmith.app.planner import milestone_contract
    ws = planned(tmp_path)
    publish_expectations(ws, "m1", [{"id": "c1", "description": "It prints hello."}], "first")
    milestone, context = ws.plan()["milestones"][0], source_context(ws)
    draft = ws.save_draft(title="D", why="w", files=[{"path": "a.py", "content": "x = 1\n", "expected_absent": True}],
                          drafted_by="x", milestone="m1")
    ws._save_draft_state(draft, "needs_revision", contract=milestone_contract(ws, milestone), context_digest=context["digest"],
                         snapshot_digest=context["snapshot_digest"], public_acceptance_digest=expectation_digest(ws, "m1"),
                         author_request_key="k")
    guarded = []
    monkeypatch.setattr(author_revisions, "_lineage", lambda ws_, d: guarded.append(d["id"]))
    building._ordinary_revision_lineage(ws, ws.drafts(), context["snapshot_digest"], milestone)
    assert guarded == [draft["id"]]                                          # the candidate the build would revise
    publish_expectations(ws, "m1", [{"id": "c1", "description": "It prints goodbye instead."}], "second")
    building._ordinary_revision_lineage(ws, ws.drafts(), context["snapshot_digest"], milestone)
    assert guarded == [draft["id"]]                                          # hidden from the prompt: not counted


def test_another_file_that_can_never_be_shown_is_named_instead_of_the_budget(tmp_path, old_caps):
    # Review of J11-B15 (fresh review): "do not fit the source budget together" was said when another file the answer
    # edits was over the size limit, whichever file came first in the answer; the real obstacle was that file.
    from runesmith.app.planner import admit_answer_files
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.source_focus import FOCUSED_FILE_BYTES, select_context
    ws = planned(tmp_path)
    crowded(tmp_path)
    (tmp_path / "zbig.js").write_bytes(b"// y " * ((FOCUSED_FILE_BYTES + 400) // 5))      # one line, too long to quote
    context = select_context(ws, collect_snapshot(ws))
    assert context["omission_reasons"] == {"huge.js": "packet_budget", "zbig.js": "file_limit"}
    edit = {"edits": [{"old_text": "// y", "new_text": "// z"}]}
    for order in (["huge.js", "zbig.js"], ["zbig.js", "huge.js"]):
        with pytest.raises(PlannerUnavailable, match="zbig.js is too large to show a model") as refused:
            admit_answer_files(ws, context, [dict(edit, path=name) for name in order])
        assert "together" not in str(refused.value) and not getattr(refused.value, "context_gap", None)
        assert refused.value.feedback["not_shown"] == "zbig.js"


def test_the_used_up_summary_and_the_breakdown_packet_name_the_file_no_model_can_see(tmp_path):
    # Review of J11-B15 (the 40,000-byte wall): three answers editing a file over the limit are refused, and the summary
    # only said the tries were used up; smaller steps that edit the same file fail the same way, so the cause is said
    # in the summary, the reason it is blocked, and in what the breakdown is asked from.
    from runesmith.app.breakdowns import input_packet
    from runesmith.app.building import build_step
    from runesmith.app.source_focus import FOCUSED_FILE_BYTES
    edit = {"title": "Edit", "files": [{"path": "zbig.js", "edits": [{"old_text": "// y", "new_text": "// z"}]}]}
    ws = gap_project(tmp_path, [edit] * 5)
    # One line, too long to quote: no part of it can be shown either (batch DD shows a long file in parts when it can).
    (tmp_path / "zbig.js").write_bytes(b"// y " * ((FOCUSED_FILE_BYTES + 400) // 5))
    router = ws.router()
    for _ in range(3):
        with pytest.raises(PlannerUnavailable, match="zbig.js is too large to show a model"):
            build_step(ws, router)
    result = build_step(ws, router)
    assert result["replan_needed"] and "The cause: zbig.js is too large to show a model, even in parts (over 160,000 bytes" in result["summary"]
    assert "split it first, yourself" in result["cause"] and "smaller steps that edit it fail the same way" in result["cause"]
    packet = input_packet(ws, "m1")
    assert packet["files_no_model_can_see"] == {"zbig.js": "file_limit"} and "files_no_model_can_see" in packet["task"]
