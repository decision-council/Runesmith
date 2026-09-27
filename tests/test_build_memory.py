import hashlib
import json
from pathlib import Path

import pytest

from runesmith.app.build_memory import remember_check, recall_for_milestone, recent_observations
from runesmith.app.building import build_step
from runesmith.app.planner import draft_files, draft_prompt, PlannerUnavailable
from runesmith.app.workspace import Workspace
from runesmith.memory import Memory
from test_studio import scripted


def setup(tmp_path):
    ws = Workspace(tmp_path)
    ws.save_plan({'summary': 'Useful command-line tool', 'milestones': [
        {'title': 'Source CLI', 'done_when': 'source add, list and show work'},
        {'title': 'Extend source CLI', 'done_when': 'existing source commands still work'}]})
    draft = ws.save_draft(title='Extend source commands', why='Add a command', drafted_by='model-a',
                          milestone='m1', files=[{'path':'cli.py', 'content':'value=1\n'}])
    check = {'status':'failed', 'utc':'2026-09-25T22:00:00Z', 'evidence_dir':'build-runs/old/check-1',
             'candidate_digest':'candidate-1', 'snapshot_digest':'source-1',
             'project_checks': {'status':'failed', 'ran':5, 'failures':1, 'errors':0,
                 'failure_details':[{'test':'SourceTests.test_existing_command',
                                     'trace_tail':'AssertionError: missing list command'}]}}
    return ws, draft, check


def test_failure_persists_and_is_recalled_for_a_later_milestone_after_restart(tmp_path):
    ws, draft, check = setup(tmp_path)
    memory_id = remember_check(ws, draft, check)
    reopened = Workspace(tmp_path)
    rows = recall_for_milestone(reopened, reopened.plan()['milestones'][1])
    assert rows[0]['id'] == memory_id and rows[0]['kind'] == 'negative'
    assert 'SourceTests.test_existing_command' in rows[0]['text']
    assert rows[0]['source']['candidate_digest'] == 'candidate-1'
    assert rows[0]['source']['evidence_dir'] == 'build-runs/old/check-1'
    assert rows[0]['source']['author'] == 'model-a'
    assert not (tmp_path/'cli.py').exists()
    assert all(m['status']=='open' for m in reopened.plan()['milestones'])
    assert memory_id in draft_prompt(reopened, reopened.plan()['milestones'][1])


def test_identical_recheck_is_deduplicated_and_retirement_survives_import(tmp_path):
    ws, draft, check = setup(tmp_path)
    first = remember_check(ws, draft, check)
    check['evidence_dir'] = 'build-runs/old/check-2'
    check['utc'] = '2026-09-25T23:00:00Z'
    check['project_checks']['elapsed_s'] = 900
    assert remember_check(Workspace(tmp_path), draft, check) == first
    assert recent_observations(ws)['total'] == 1
    Memory(ws.home/'memory.jsonl').retire(first, 'obsolete observation')
    assert remember_check(ws, draft, check, origin='trainer_receipt_import') == first
    assert recent_observations(ws)['total'] == 0
    assert recall_for_milestone(ws, ws.plan()['milestones'][1]) == []


@pytest.mark.parametrize('status', ['stale', 'unsupported', 'refused', 'unknown'])
def test_unmeasured_results_are_not_negative_learning_evidence(tmp_path, status):
    ws, draft, _ = setup(tmp_path)
    remember_check(ws, draft, {'status':status, 'detail':'No completed measurement'})
    row = recent_observations(ws)['items'][0]
    assert row['kind']=='episode' and row['source']['outcome']=='unknown'


def test_timeout_is_incomplete_even_when_outer_status_is_failed(tmp_path):
    ws, draft, check = setup(tmp_path)
    check['project_checks'] = {'status':'timeout', 'ok':False, 'output':'partial check output'}
    remember_check(ws, draft, check)
    row = recent_observations(ws)['items'][0]
    assert row['kind']=='episode' and row['source']['outcome']=='incomplete_timeout'
    assert 'partial check output' not in row['text']


def test_self_checks_and_owner_acceptance_stay_distinct(tmp_path):
    ws, draft, check = setup(tmp_path)
    check.update(status='self_checks_passed', project_checks={'status':'passed','ran':5})
    remember_check(ws,draft,check)
    check.update(status='acceptance_passed', acceptance={'status':'passed','ran':2})
    remember_check(ws,draft,check)
    assert {r['source']['outcome'] for r in recent_observations(ws)['items']} == {
        'self_checks_passed','acceptance_passed'}
    assert not (tmp_path/'cli.py').exists()
    assert ws.plan()['milestones'][0]['status']=='open'


def test_build_recall_is_filtered_before_ranking_and_bounded(tmp_path):
    ws, draft, check = setup(tmp_path)
    for number in range(8):
        remember_check(ws, dict(draft, id='old-'+str(number)), check)
    memory = Memory(ws.home/'memory.jsonl')
    other = memory.add('note', 'source CLI existing source commands '*500)
    rows = recall_for_milestone(ws, ws.plan()['milestones'][1])
    assert len(rows)==3 and all(row['id']!=other for row in rows)
    assert all(len(row['text'])<=1600 for row in rows)
    assert all(row['source']['kind']=='build_check' for row in rows)
    assert recall_for_milestone(ws, {'title':'zoological aardvarks'}) == []


def test_actual_draft_packet_and_saved_receipt_bind_the_same_memories(tmp_path):
    ws, old, check = setup(tmp_path)
    memory_id = remember_check(ws, old, check)
    scripted(ws,[{'title':'New source command','files':[{'path':'cli.py','content':'value=2\n'}]}],roles=('plan',))
    captured = {}
    inner = ws.router()
    class Capture:
        def call(self, role, **kwargs):
            captured.update(kwargs)
            return inner.call(role, **kwargs)
    draft = draft_files(ws,Capture(),'m2')
    receipt = json.loads((ws.home/draft['memory_exposure']).read_text())
    assert receipt['state']=='answer_received'
    assert receipt['memory_ids']==draft['memory_ids']==[memory_id]
    packet = json.loads(captured['prompt'])
    assert packet['historical_build_observations']==receipt['observations']
    assert hashlib.sha256(captured['prompt'].encode()).hexdigest()==receipt['prompt_sha256']
    assert ws.work()['build_memory']['items'][0]['id']==memory_id
    # Reusing a waiting draft does not expose new context or make a new call.
    assert draft_files(ws,Capture(),'m2')['id']==draft['id']
    assert len(list((ws.home/'build-memory-exposures').glob('*.json')))==1


def test_distinct_rechecks_of_one_candidate_do_not_fill_the_packet(tmp_path):
    ws, draft, check = setup(tmp_path)
    for number in range(8):
        remember_check(ws, draft, dict(check, detail='source CLI failure '+str(number)))
    remember_check(ws, dict(draft, id='another-candidate'), check)
    rows=recall_for_milestone(ws,ws.plan()['milestones'][1])
    assert len(rows)==2
    assert {r['source']['draft'] for r in rows}=={draft['id'],'another-candidate'}


def test_unanswered_packet_is_not_labelled_as_received(tmp_path):
    ws, draft, check = setup(tmp_path)
    remember_check(ws,draft,check)
    class Unavailable:
        def call(self,*args,**kwargs):
            raise KeyError('no configured instrument')
    with pytest.raises(PlannerUnavailable):
        draft_files(ws,Unavailable(),'m2')
    [path] = list((ws.home/'build-memory-exposures').glob('*.json'))
    assert json.loads(path.read_text())['state']=='prepared'


def test_build_checks_automatically_record_without_changing_acceptance(tmp_path, monkeypatch):
    ws, old, check = setup(tmp_path)
    ws.update_settings({'build_steps':True})
    scripted(ws,[{'title':'Source CLI attempt','files':[{'path':'new.py','content':'value=2\n'}]}],roles=('plan',))
    def verify(*_, phase_checkpoint):
        phase_checkpoint()
        return check
    monkeypatch.setattr('runesmith.app.building.verify_draft', verify)
    result=build_step(ws,ws.router())
    saved=ws._draft(result['draft'])
    assert saved['state']=='needs_revision'
    assert saved['check_memory_id']==recent_observations(ws)['items'][0]['id']
    assert saved['verification']==check
    assert not (tmp_path/'new.py').exists()


def add_observation(ws, *, draft='candidate', milestone='m1', outcome='failed',
                    text='source CLI', utc='2026-09-25T22:00:00Z', extra=None):
    source = {'kind': 'build_check', 'draft': draft, 'milestone': milestone,
              'outcome': outcome, 'observed_utc': utc, 'feedback_projection': 'public-v1'}
    source.update(extra or {})
    return Memory(ws.home/'memory.jsonl').add('negative' if outcome == 'failed' else 'episode',
                                           text, tags=['build_check'], source=source)


def test_newer_distinct_observation_replaces_a_more_keyword_dense_old_failure(tmp_path):
    ws, _, _ = setup(tmp_path)
    old = add_observation(ws, text='source CLI existing source commands '*40)
    new = add_observation(ws, text='source CLI passed', outcome='acceptance_passed',
                          utc='2026-09-25T23:00:00Z')
    assert Memory(ws.home/'memory.jsonl').recall('source CLI existing source commands', 20,
                                               source_kind='build_check')[0]['id'] == old
    rows = recall_for_milestone(ws, ws.plan()['milestones'][1])
    assert [row['id'] for row in rows] == [new]
    assert rows[0]['selection']['earlier_distinct_observations'] == 1
    assert 'deduplicated' in rows[0]['selection']['caution']
    assert {row['id'] for row in recent_observations(ws)['items']} == {old, new}
    assert all(m['status'] == 'open' for m in ws.plan()['milestones'])


def test_old_import_cannot_supersede_later_observed_receipt(tmp_path):
    ws, _, _ = setup(tmp_path)
    latest = add_observation(ws, outcome='acceptance_passed', utc='2026-09-26T00:00:00Z')
    add_observation(ws, utc='2026-09-25T22:00:00Z')
    assert recall_for_milestone(ws, ws.plan()['milestones'][0])[0]['id'] == latest


def test_equal_receipt_times_use_append_order_not_lexical_or_id_order(tmp_path):
    ws, _, _ = setup(tmp_path)
    add_observation(ws, text='source CLI '*50)
    latest = add_observation(ws, text='source CLI passed', outcome='self_checks_passed')
    assert recall_for_milestone(ws, ws.plan()['milestones'][0])[0]['id'] == latest


@pytest.mark.parametrize('value', [None, '', 'not-a-date', '2026-09-26T20:00:00', 42])
def test_missing_or_bad_receipt_time_falls_back_without_crashing(tmp_path, value):
    ws, _, _ = setup(tmp_path)
    memory_id = add_observation(ws, utc=value)
    assert recall_for_milestone(ws, ws.plan()['milestones'][0])[0]['id'] == memory_id


def test_collapse_precedes_top_k_and_same_milestone_is_prioritized(tmp_path):
    ws, _, _ = setup(tmp_path)
    for n in range(30):
        add_observation(ws, draft='repeated', text='source CLI existing source commands '*10+str(n))
    own = add_observation(ws, draft='own', milestone='m2', text='source')
    unrelated = add_observation(ws, draft='different', milestone='m3', text='source CLI')
    rows = recall_for_milestone(ws, ws.plan()['milestones'][1])
    assert len(rows) == 3 and rows[0]['id'] == own
    assert unrelated in {r['id'] for r in rows}
    assert rows[0]['selection']['reason'] == 'same_milestone'
    assert next(r for r in rows if r['source']['draft'] == 'repeated')['selection']['earlier_distinct_observations'] == 29


def test_retired_observation_stays_excluded_from_preview_and_recall(tmp_path):
    ws, _, _ = setup(tmp_path)
    memory_id = add_observation(ws)
    Memory(ws.home/'memory.jsonl').retire(memory_id, 'Not usable')
    assert recent_observations(ws)['working_set']['items'] == []
    assert recall_for_milestone(ws, ws.plan()['milestones'][0]) == []


def test_private_legacy_text_metadata_and_tags_are_projected_before_ranking(tmp_path):
    ws, _, _ = setup(tmp_path)
    memory = Memory(ws.home/'memory.jsonl')
    memory_id = memory.add('negative', 'source CLI\n  acceptance: PRIVATE_LITERAL',
        tags=['PRIVATE_TAG'], source={'kind':'build_check', 'draft':'legacy',
            'checks': {'acceptance': {'failure_details': 'PRIVATE_METADATA'}},
            'detail': 'PRIVATE_DETAIL', 'surprise': 'PRIVATE_EXTENSION'})
    rows = recall_for_milestone(ws, ws.plan()['milestones'][0])
    assert rows[0]['id'] == memory_id
    assert 'PRIVATE_' not in json.dumps(rows)
    assert 'Private legacy acceptance details withheld' in rows[0]['text']
    for term in ('PRIVATE_LITERAL','PRIVATE_TAG','PRIVATE_METADATA'):
        assert recall_for_milestone(ws, {'title':term}) == []
    assert 'PRIVATE_METADATA' in memory.path.read_text()  # Archive not rewritten.


def test_working_set_preview_matches_actual_draft_exposure_without_mutations(tmp_path):
    ws, _, _ = setup(tmp_path)
    memory_id = add_observation(ws)
    before = (ws.home/'memory.jsonl').read_bytes()
    preview = recent_observations(ws)['working_set']
    assert preview['preview_only'] and preview['milestone']['id'] == 'm1'
    assert preview['items'] == recall_for_milestone(ws, ws.plan()['milestones'][0])
    assert [r['id'] for r in preview['items']] == [memory_id]
    assert (ws.home/'memory.jsonl').read_bytes() == before
    assert not (ws.home/'build-memory-exposures').exists()
    # Advance to the second fixture milestone, which has no waiting draft.
    ws.update_milestone('m1', {'status':'done'})
    add_observation(ws, milestone='m2', draft='next')
    preview = recent_observations(ws)['working_set']
    scripted(ws,[{'title':'Source CLI','files':[{'path':'cli.py','content':'value=2\n'}]}],roles=('plan',))
    draft = draft_files(ws,ws.router(),'m2')
    receipt = json.loads((ws.home/draft['memory_exposure']).read_text())
    assert receipt['observations'] == preview['items']


def test_no_ready_milestone_has_no_preview_and_studio_renders_selection(tmp_path):
    ws, _, _ = setup(tmp_path)
    add_observation(ws)
    for m in ws.plan()['milestones']:
        ws.update_milestone(m['id'], {'status':'done'})
    preview = ws.work()['build_memory']['working_set']
    assert preview['milestone'] is None and preview['items'] == []
    ui = (Path(__file__).parents[1]/'runesmith/app/static/js/views/work.js').read_text(encoding='utf-8')
    assert 'memory.working_set' in ui and 'Next author memory preview' in ui
    assert 'working.items' in ui and 'selection.reason' in ui


def test_pure_ranker_preserves_generic_memory_recall(tmp_path):
    from runesmith.memory import rank_memories
    memory = Memory(tmp_path/'generic.jsonl')
    for n in range(30):
        memory.add('note', f'compiler memory allocation issue {n}', tags=['issue'])
    assert memory.recall('compiler issue', 20) == rank_memories(memory.active(), 'compiler issue', 20)
    assert rank_memories([], 'anything') == []
    assert rank_memories(memory.active(), 'compiler', 0) == []
