"""Context navigation is bounded input selection, not permission or test credit."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runesmith.app.planner import source_context, draft_files, milestone_contract, plan_readiness, PlannerUnavailable
from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
from runesmith.app.source_focus import CONTEXT_CHARS, FOCUSED_FILE_BYTES, inspect_context, save_focus, recorded_context
from runesmith.app.workspace import WorkspaceError
from test_build_context import planned
from test_studio import scripted


def large_source(ws, name='cli.py', size=20554):
    path = ws.root / name
    path.write_bytes(b'#' + b'x' * (size - 2) + b'\n')
    return path


def test_default_selection_and_digest_are_preserved(tmp_path):
    ws = planned(tmp_path)
    (tmp_path / 'a.py').write_text('answer=1\n')
    large_source(ws, size=FOCUSED_FILE_BYTES + 1)   # over even the prioritized cap, one line: never shown (J11-B15)
    context = source_context(ws)
    assert context['files'] == {'a.py': 'answer=1\n'}
    assert context['digest'] == hashlib.sha256(json.dumps(context['files'], sort_keys=True).encode()).hexdigest()
    assert context['omission_reasons']['cli.py'] == 'file_limit'
    assert 'rows' not in context['selection']  # full display metadata does not inflate model packets


def test_a_file_over_the_normal_cap_is_shown_after_the_others_when_the_budget_has_room(tmp_path, old_caps):
    # Journey J11-B15: motion.mjs passed 20,000 bytes and was never shown again, so every build that edited it was refused.
    ws = planned(tmp_path)
    (tmp_path / 'a.py').write_text('answer=1\n')
    large_source(ws)                                # 20,554 bytes: over the normal cap, under the prioritized one
    context = source_context(ws)
    assert list(context['files']) == ['a.py', 'cli.py'] and context['omission_reasons'] == {}
    large_source(ws, 'big.py', 30000)               # read before cli.py: together over the budget, so cli.py is left out
    context = source_context(ws)
    assert list(context['files']) == ['a.py', 'big.py'] and context['omission_reasons'] == {'cli.py': 'packet_budget'}
    save_focus(ws, ['cli.py'], collect_snapshot(ws)['digest'], 'Builds of this milestone edit it')
    assert 'cli.py' in source_context(ws)['files']  # prioritizing it is the remedy the refusal names


def test_focused_file_is_in_the_real_author_packet_without_larger_total_budget(tmp_path):
    ws = planned(tmp_path)
    large_source(ws)
    before = collect_snapshot(ws)['digest']
    preview = save_focus(ws, ['cli.py'], before, 'Needed public command implementation')
    assert preview['included_count'] == 1 and preview['budget_chars'] == CONTEXT_CHARS
    assert preview['rows'][0]['included'] and preview['rows'][0]['focused']
    scripted(ws, [{'title': 'Exact local edit', 'files': [{'path': 'cli.py',
        'edits': [{'old_text': '#xxx', 'new_text': '#yyy'}]}]}], roles=('plan',))
    draft = draft_files(ws, ws.router())
    assert 'cli.py' in draft['shown_files']
    assert draft['files'][0]['content'].startswith('#yyy')
    assert (tmp_path / 'cli.py').read_bytes().startswith(b'#xxx')
    assert collect_snapshot(ws)['digest'] == before
    assert source_context(ws)['selection']['used_chars'] <= CONTEXT_CHARS


@pytest.mark.parametrize('paths', [['../outside.py'], ['/absolute.py'], ['.env'], ['tests/fixtures/private.json'],
                                 ['cli.py', 'cli.py'], ['missing.py'], [True], 'cli.py'])
def test_invalid_or_private_focus_is_rejected_before_saving(tmp_path, paths):
    ws = planned(tmp_path); large_source(ws)
    (tmp_path / '.env').write_text('SECRET=not-for-authors')
    fixture = tmp_path / 'tests/fixtures/private.json'; fixture.parent.mkdir(parents=True)
    fixture.write_text('{"private":"do-not-expose"}')
    with pytest.raises(WorkspaceError):save_focus(ws, paths, collect_snapshot(ws)['digest'], 'Invalid choice')
    assert not (ws.home / 'AUTHOR_FOCUS.json').exists()
    preview = json.dumps(inspect_context(ws))
    assert 'not-for-authors' not in preview and 'private.json' not in preview and 'do-not-expose' not in preview


@pytest.mark.parametrize('kind', ['too_large', 'total_budget', 'not_utf8'])
def test_focus_never_silently_expands_caps_or_truncates_required_files(tmp_path, kind):
    ws = planned(tmp_path)
    if kind == 'too_large':large_source(ws, size=FOCUSED_FILE_BYTES + 1); paths = ['cli.py']
    elif kind == 'total_budget':
        large_source(ws, 'a.py', CONTEXT_CHARS // 2 + 1000); large_source(ws, 'b.py', CONTEXT_CHARS // 2 + 1000); paths = ['a.py', 'b.py']
    else:(tmp_path / 'cli.py').write_bytes(b'\xff'); paths = ['cli.py']
    with pytest.raises(WorkspaceError, match='budget'):
        save_focus(ws, paths, collect_snapshot(ws)['digest'], 'Must fit all requested files')
    assert not (ws.home / 'AUTHOR_FOCUS.json').exists()


def test_small_diagnostic_packets_can_omit_focus_without_growing_their_budget(tmp_path):
    ws = planned(tmp_path); large_source(ws)
    save_focus(ws, ['cli.py'], collect_snapshot(ws)['digest'], 'Full author focus')
    small = source_context(ws, limit=20000)
    assert small['files'] == {} and small['focus_errors']['cli.py'] == 'packet_budget'
    assert small['selection']['used_chars'] == 0


def test_changed_source_refuses_stale_focus_selection(tmp_path):
    ws = planned(tmp_path); large_source(ws)
    old = collect_snapshot(ws)['digest']
    (tmp_path / 'new.py').write_text('new=1\n')
    with pytest.raises(WorkspaceError, match='Source changed'):save_focus(ws, ['cli.py'], old, 'Old inspector view')


def test_missing_focused_file_blocks_new_author_call(tmp_path):
    ws = planned(tmp_path); path = large_source(ws)
    save_focus(ws, ['cli.py'], collect_snapshot(ws)['digest'], 'Need this source')
    path.unlink()
    class NoCall:
        def call(self, *args, **kwargs):raise AssertionError('No spend with unavailable required context')
    with pytest.raises(PlannerUnavailable, match='Author context'):draft_files(ws, NoCall())


def test_damaged_settings_are_visible_and_can_be_explicitly_cleared(tmp_path):
    ws = planned(tmp_path); large_source(ws)
    path = ws.home / 'AUTHOR_FOCUS.json'; path.write_bytes(b'{')
    preview = inspect_context(ws)
    assert preview['settings_error'] and path.read_bytes() == b'{'
    with pytest.raises(WorkspaceError, match='damaged'):source_context(ws)
    cleared = save_focus(ws, [], preview['snapshot_digest'], 'Explicitly restore default selection')
    assert not cleared['settings_error'] and cleared['focus']['paths'] == []


def test_retained_answer_uses_its_original_selection_after_focus_changes(tmp_path, old_caps):
    from runesmith.app.author_recovery import prepare_packet, admit_packet
    from runesmith.app.acceptance_contracts import expectation_digest
    ws = planned(tmp_path); large_source(ws); large_source(ws, 'big.py', 30000)     # cli.py does not fit beside big.py
    (tmp_path / 'small.py').write_text('value=1\n')
    snapshot = collect_snapshot(ws); freeze_snapshot(ws, snapshot)
    context = source_context(ws, snapshot=snapshot); milestone = ws.plan()['milestones'][0]
    packet = prepare_packet(ws, 'original-focus', milestone=milestone, context=context,
        contract=milestone_contract(ws, milestone), public_digest=expectation_digest(ws, 'm1'), exposure='unused.json')
    save_focus(ws, ['cli.py'], snapshot['digest'], 'Next request should include the CLI')
    assert source_context(ws)['digest'] != context['digest']
    draft = admit_packet(ws, packet, {'title': 'Earlier answer', 'files': [{'path': 'new.py', 'content': 'new=1\n'}]}, 'synthetic')
    assert draft['shown_files'] == ['big.py', 'small.py'] and draft['context_digest'] == context['digest']
    assert not (tmp_path / 'new.py').exists()


@pytest.mark.parametrize('names', [['.env'], ['missing.py'], ['a.py','a.py'], [1], 'a.py'])
def test_recorded_selection_rejects_tampering(tmp_path, names):
    ws = planned(tmp_path); (tmp_path / 'a.py').write_text('a=1\n')
    with pytest.raises(WorkspaceError):recorded_context(collect_snapshot(ws), names)


def test_api_and_actual_studio_connect_focus_without_arbitrary_caps(tmp_path):
    from runesmith.app.server import api_author_context, api_author_context_save
    ws = planned(tmp_path); large_source(ws)
    events = []; studio = SimpleNamespace(ws=ws, bus=SimpleNamespace(publish=lambda *a: events.append(a)))
    initial = api_author_context(studio, {}, {})
    result = api_author_context_save(studio, {}, {'paths': ['cli.py'], 'reason': 'Public command source',
        'snapshot_digest': initial['snapshot_digest'], 'limit': 9999999, 'allow_apply': True})
    assert result['budget_chars'] == CONTEXT_CHARS and result['included_count'] == 1
    assert [event[0] for event in events] == ['plan', 'work']
    ui = (Path(__file__).parents[1] / 'runesmith/app/static/js/views/goals.js').read_text(encoding='utf-8')
    assert "get('/api/author-context')" in ui and "post('/api/author-context'" in ui
    assert 'snapshot_digest: data.snapshot_digest' in ui and '!readiness?.ready' in ui


def test_plan_readiness_matches_dependencies_and_closed_states():
    plan = {'milestones': [{'id':'a','title':'First','status':'doing'},
        {'id':'b','title':'Second','status':'open','depends_on':['a']},
        {'id':'c','title':'Missing','status':'open','depends_on':['not-there']},
        {'id':'done','title':'Done','status':'done'}, {'id':'drop','title':'Dropped','status':'dropped'}]}
    states = plan_readiness(plan)
    assert states['a']['ready'] and not states['b']['ready']
    assert states['b']['unmet'] == [{'id':'a','title':'First','status':'doing'}]
    assert states['c']['unmet'][0]['status'] == 'missing'
    assert not states['done']['ready'] and not states['drop']['ready']
    plan['milestones'][0]['status'] = 'done'
    assert plan_readiness(plan)['b']['ready']


def test_the_author_context_refusals_read_with_their_spaces(tmp_path):
    # Review of J11-B15: "Choose up to12 ..." and "between0 and48000" in the Studio's errors, beside the fixed line.
    from runesmith.app.source_focus import select_context
    ws = planned(tmp_path)
    with pytest.raises(WorkspaceError, match='Choose up to 12 unique model-visible relative file paths'):
        save_focus(ws, [f'f{n}.py' for n in range(13)], collect_snapshot(ws)['digest'], 'Too many')
    with pytest.raises(WorkspaceError, match=f'between 0 and {CONTEXT_CHARS} characters'):
        select_context(ws, collect_snapshot(ws), limit=CONTEXT_CHARS + 1)
