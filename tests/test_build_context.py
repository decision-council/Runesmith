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
    (tmp_path/'large.py').write_text('x = 1\n'*5000)
    scripted(ws, [{'title':'Blind edit','files':[{'path':'large.py','content':'x = 2'}]}], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='unseen'):
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
