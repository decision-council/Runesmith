import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runesmith.app import revision_context as rc
from runesmith.app.author_recovery import admit_packet, prepare_packet
from runesmith.app.building import author_context_preflight
from runesmith.app.planner import draft_files, draft_prompt, source_context, PlannerUnavailable
from runesmith.app.workspace import WorkspaceError, _write_json
from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
from test_build_context import planned
from test_studio import scripted


def setup_revision(tmp_path, padding=0):
    ws = planned(tmp_path)
    source = 'import os\n\ndef target():\n    return 1\n\ndef other():\n    return 987654321\n' + ('#' + 'z' * padding + '\n' if padding else '')
    (tmp_path / 'app.py').write_text(source, encoding='utf-8')
    scripted(ws, [{'title': 'Candidate', 'files': [
        {'path': 'app.py', 'edits': [{'old_text': 'return 1', 'new_text': 'return 2'}]},
        {'path': 'helper.py', 'content': 'retained = 9\n'}]}], roles=('plan',))
    prior = draft_files(ws, ws.router())
    ws._save_draft_state(prior, 'needs_revision')
    return ws, ws._draft(prior['id'])


def selections(ws, prior, label='target'):
    unit = next(u for u in rc.inspect_revision(ws, prior['id'])['units'] if u['label'] == label)
    return [{'path': unit['path'], 'unit': unit['unit']}]


def save(ws, prior, selected=None):
    info = rc.inspect_revision(ws, prior['id'])
    return rc.save_selection(ws, prior['id'], version=info['version'],
                             selections=selected or selections(ws, prior), reason='Bounded local repair')


def test_actual_preview_removes_duplicate_source_and_keeps_feedback(tmp_path):
    ws, prior = setup_revision(tmp_path, padding=8000)
    ws.notes.add(target_type='draft', target_id=prior['id'], text='Retain important failure feedback', author='owner')
    result = save(ws, prior)
    prompt = result['preview']['prompt']
    packet, _ = json.JSONDecoder().raw_decode(prompt)
    assert 'return 2' in prompt and '987654321' not in prompt
    assert 'Retain important failure feedback' in prompt
    assert 'files' not in packet['source_context']
    assert packet['candidate_to_revise']['retained_files'][1]['path'] == 'helper.py'
    assert packet['public_acceptance'] == json.loads(draft_prompt(ws, ws.plan()['milestones'][0],
        source_context(ws), revision=prior).split('\n\n')[0])['public_acceptance']
    assert result['preview']['focused_prompt_bytes'] < result['preview']['broad_prompt_bytes']
    assert result['preview']['inference_calls'] == 0


def test_small_packet_overhead_is_measured_not_hidden(tmp_path):
    ws, prior = setup_revision(tmp_path)
    preview = save(ws, prior)['preview']
    assert preview['focused_prompt_bytes'] == len(preview['prompt'].encode('utf-8'))
    assert preview['focused_prompt_bytes'] > preview['broad_prompt_bytes']


def test_real_draft_path_keeps_host_bindings_and_omitted_candidate_bytes(tmp_path):
    ws, prior = setup_revision(tmp_path); save(ws, prior)
    before = collect_snapshot(ws)['digest']
    scripted(ws, [{'title': 'Focused correction', 'files': [{'path': 'app.py',
        'edits': [{'old_text': 'return 2', 'new_text': 'return 3'}]}]}], roles=('plan',))
    revised = draft_files(ws, ws.router(), 'm1', revision=prior)
    files = {f['path']: f['content'] for f in revised['files']}
    assert 'return 3' in files['app.py'] and 'return 987654321' in files['app.py']
    assert files['helper.py'] == 'retained = 9\n'
    assert revised['shown_files'] == [] and revised['bound_source_files'] == ['app.py']
    assert len(revised['revision_view']['editable_units']) == 1
    assert not (tmp_path / 'helper.py').exists()
    assert collect_snapshot(ws)['digest'] == before
    preflight = author_context_preflight(ws, revised)
    assert preflight['ok'] and preflight['binding'] == 'frozen_source_bindings'


@pytest.mark.parametrize('files', [
    [{'path': 'app.py', 'edits': [{'old_text': 'return 987654321', 'new_text': 'return 4'}]}],
    [{'path': 'app.py', 'edits': [{'old_text': 'import os', 'new_text': 'import sys'}]}],
    [{'path': 'app.py', 'content': 'overwrite everything'}],
    [{'path': 'helper.py', 'edits': [{'old_text': 'retained = 9', 'new_text': 'retained = 0'}]}],
    [{'path': 'new.py', 'content': 'new = True'}],
    [{'path': 'app.py', 'edits': [{'old_text': '', 'new_text': 'blind'}]}],
    [{'path': 'app.py', 'edits': [{'old_text': 'return 2', 'new_text': 'return 2'}]}],
    [None], [],
])
def test_unseen_full_replacement_new_path_and_noop_refused(tmp_path, files):
    ws, prior = setup_revision(tmp_path); save(ws, prior)
    before = (tmp_path / 'app.py').read_bytes()
    scripted(ws, [{'title': 'Unsafe correction', 'files': files}], roles=('plan',))
    with pytest.raises(PlannerUnavailable): draft_files(ws, ws.router(), 'm1', revision=prior)
    assert (tmp_path / 'app.py').read_bytes() == before and len(ws.drafts()) == 1


def test_sequential_edits_stay_in_displayed_units_and_full_file_ambiguity_still_refused(tmp_path):
    ws, prior = setup_revision(tmp_path)
    view = rc.make_view(ws, prior, selections(ws, prior))
    result = rc.materialize_answer(ws, prior, view, [{'path': 'app.py', 'edits': [
        {'old_text': 'return 2', 'new_text': 'return 3'}, {'old_text': 'return 3', 'new_text': 'return 4'}]}])
    assert 'return 4' in result[0]['content'] and '987654321' in result[0]['content']
    ambiguous = copy.deepcopy(prior)
    ambiguous['files'][0]['content'] += '\ndef duplicate():\n    return 2\n'
    view = rc.make_view(ws, ambiguous, selections(ws, prior))
    with pytest.raises(PlannerUnavailable): rc.materialize_answer(ws, ambiguous, view,
        [{'path': 'app.py', 'edits': [{'old_text': 'return 2', 'new_text': 'return 4'}]}])


def test_invalid_overlapping_over_budget_and_private_selections_refused(tmp_path):
    ws, prior = setup_revision(tmp_path)
    selected = selections(ws, prior)
    for bad in ([], 'bad', [None], selected * 2, selected + [{'path': 'app.py', 'unit': '*'}],
                [{'path': '../outside.py', 'unit': '*'}], [{'path': 'app.py', 'unit': 'missing'}]):
        with pytest.raises(WorkspaceError): rc.make_view(ws, prior, bad)
    giant = copy.deepcopy(prior); giant['files'][0]['content'] = 'x' * 24001
    with pytest.raises(WorkspaceError, match='24000'): rc.make_view(ws, giant, [{'path': 'app.py', 'unit': '*'}])
    private = copy.deepcopy(prior); private['files'].append({'path': 'tests/fixtures/data.json', 'content': 'private'})
    with pytest.raises(WorkspaceError): rc.make_view(ws, private, [{'path': 'tests/fixtures/data.json', 'unit': '*'}])


def test_selection_cas_detects_other_editor_and_source_changes(tmp_path):
    ws, prior = setup_revision(tmp_path); old = rc.inspect_revision(ws, prior['id'])
    save(ws, prior)
    with pytest.raises(WorkspaceError, match='changed'): rc.save_selection(ws, prior['id'], version=old['version'],
        selections=selections(ws, prior), reason='Stale editor')
    fresh = rc.inspect_revision(ws, prior['id'])
    (tmp_path / 'app.py').write_text('changed source')
    with pytest.raises(WorkspaceError, match='changed'): rc.save_selection(ws, prior['id'], version=fresh['version'],
        selections=[{'path': 'app.py', 'unit': '*'}], reason='Stale source')
    assert 'Full source snapshot changed.' in rc.inspect_revision(ws, prior['id'])['blockers']


def test_readiness_pending_and_worker_block_saving(tmp_path, monkeypatch):
    ws, prior = setup_revision(tmp_path)
    import runesmith.app.author_recovery as recovery
    monkeypatch.setattr(recovery, 'pending_authors', lambda ws: [{'id': 'pending'}])
    with pytest.raises(WorkspaceError, match='Reconcile'): save(ws, prior)
    monkeypatch.setattr(recovery, 'pending_authors', lambda ws: [])
    _write_json(ws.home / 'STUDIO_CURRENT.json', {'job': 'build'})
    with pytest.raises(WorkspaceError, match='Studio worker'): save(ws, prior)
    (ws.home / 'STUDIO_CURRENT.json').unlink()
    ws._save_draft_state(prior, 'waiting')
    assert rc.inspect_revision(ws, prior['id'])['blockers']


def test_profile_never_applies_to_other_or_nonexplicit_drafts(tmp_path):
    ws, prior = setup_revision(tmp_path); info = save(ws, prior)
    broad = draft_prompt(ws, ws.plan()['milestones'][0], source_context(ws), revision=prior)
    assert '987654321' in broad
    other = copy.deepcopy(prior); other['files'][0]['diff'] = 'display-only'; other['files'][0]['exists_now'] = True
    assert rc.selected_view(ws, other) == rc.selected_view(ws, prior)
    rc.save_selection(ws, prior['id'], version=info['version'], selections=[], reason='Need broader context', enabled=False)
    assert rc.selected_view(ws, prior) is None


def test_recovered_answer_uses_its_original_selection_not_current_preference(tmp_path):
    ws, prior = setup_revision(tmp_path); save(ws, prior)
    snapshot = collect_snapshot(ws); freeze_snapshot(ws, snapshot)
    context = source_context(ws, snapshot=snapshot)
    packet = prepare_packet(ws, 'draft-m1-recovery', milestone=ws.plan()['milestones'][0], context=context,
        contract=prior['contract'], public_digest=prior['public_acceptance_digest'], exposure='unused-exposure.json',
        revision=prior, explicit_revision=True, revision_view=rc.selected_view(ws, prior))
    save(ws, prior, selections(ws, prior, 'other'))
    answer = {'title': 'Recovered', 'files': [{'path': 'app.py', 'edits': [{'old_text': 'return 2', 'new_text': 'return 8'}]}]}
    result = admit_packet(ws, packet, answer, 'scripted:author')
    assert 'return 8' in result['files'][0]['content']
    assert result['revision_view']['selections'] != rc.selected_view(ws, prior)['selections']
    assert admit_packet(ws, packet, answer, 'scripted:author')['id'] == result['id']


def test_changed_candidate_view_and_source_refuse_recovery(tmp_path):
    ws, prior = setup_revision(tmp_path); save(ws, prior)
    view = rc.selected_view(ws, prior); altered = copy.deepcopy(view)
    altered['editable_units'][0]['content'] += '\n# invented'
    with pytest.raises(WorkspaceError): rc.materialize_answer(ws, prior, altered, [])
    context = source_context(ws)
    packet = prepare_packet(ws, 'draft-m1-stale', milestone=ws.plan()['milestones'][0], context=context,
        contract=prior['contract'], public_digest=prior['public_acceptance_digest'], exposure='unused-exposure.json',
        revision=prior, explicit_revision=True, revision_view=view)
    (tmp_path / 'app.py').write_text('different = 1\n')
    with pytest.raises(WorkspaceError, match='changed'): admit_packet(ws, packet,
        {'title': 'Stale', 'files': [{'path': 'app.py', 'edits': [{'old_text': 'return 2', 'new_text': 'return 8'}]}]}, 'author')


def test_decorated_unicode_crlf_methods_are_complete_units(tmp_path):
    ws, prior = setup_revision(tmp_path)
    prior['files'][0]['content'] = 'class T:\r\n    @staticmethod\r\n    def method():\r\n        return "h\u00e5p"\r\n'
    rows, _ = rc._units('app.py', prior['files'][0]['content'])
    unit = next(u for u in rows if u['label'] == 'T.method')
    view = rc.make_view(ws, prior, [{'path': 'app.py', 'unit': unit['unit']}])
    assert view['editable_units'][0]['content'].startswith('    @staticmethod\r\n')
    assert view['editable_units'][0]['content'].endswith('"h\u00e5p"\r\n')


def test_actual_api_ignores_extra_authority_and_ui_is_connected(tmp_path):
    from runesmith.app.server import api_revision_context, api_revision_context_save
    ws, prior = setup_revision(tmp_path); events = []
    studio = SimpleNamespace(ws=ws, bus=SimpleNamespace(publish=lambda *a: events.append(a)))
    view = api_revision_context(studio, {}, None, prior['id'])
    before = ws.settings()
    result = api_revision_context_save(studio, {}, {'version': view['version'], 'reason': 'Local function',
        'selections': selections(ws, prior), 'auto_work': True, 'allow_apply': True}, prior['id'])
    assert result['view']['code_chars'] > 0 and ws.settings() == before
    assert events == [('work', {})]
    ui = (Path(__file__).parents[1] / 'runesmith/app/static/js/views/work.js').read_text(encoding='utf-8')
    assert 'showRevisionContext(d.id, reload)' in ui and 'Save focused packet without a call' in ui
