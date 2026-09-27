"""Whole-note selection and actual author prompt delivery; no external calls."""
import pytest

from runesmith.notes import NoteStore
from runesmith.app.workspace import WorkspaceError
from runesmith.app.planner import draft_prompt, source_context, draft_files
from runesmith.app import revision_context
from test_revision_context import setup_revision


def add(store, text, target='current', kind='draft', author='external-trainer'):
    return store.add(target_type=kind, target_id=target, text=text, author=author)


def test_newest_whole_feedback_survives_full_old_history_and_same_second(tmp_path, monkeypatch):
    monkeypatch.setattr('runesmith.notes._now', lambda: '2026-09-27T00:00:00Z')
    store = NoteStore(tmp_path)
    old = add(store, 'OLD ' + 'x' * 1700)
    newest = add(store, 'NEW TASK ' + 'λ' * 1700)
    result = store.operator_note_selection([('draft', 'current')], priority_targets=[('draft', 'current')])
    assert [r['id'] for r in result['included']] == [newest['id']]
    assert [r['id'] for r in result['omitted']] == [old['id']]
    assert newest['text'] in result['text'] and old['text'] not in result['text']
    assert 'author=external-trainer' in result['text'] and "owner's own" not in result['text']
    assert result['used_chars'] == len(result['text']) <= result['budget_chars']
    assert not result['blockers']


def test_large_nonpriority_note_does_not_suppress_later_small_note(tmp_path):
    store = NoteStore(tmp_path)
    small = add(store, 'small whole note')
    large = add(store, 'X' * 3900)
    result = store.operator_note_selection([('draft', 'current')])
    assert [r['id'] for r in result['included']] == [small['id']]
    assert result['omitted'][0]['id'] == large['id']


def test_latest_draft_and_milestone_precede_draft_history(tmp_path):
    store = NoteStore(tmp_path)
    milestone = add(store, 'Milestone instruction ' + 'm' * 350, 'm1', 'milestone')
    add(store, 'old draft history ' + 'x' * 700)
    newest = add(store, 'New draft instruction ' + 'n' * 350)
    result = store.operator_note_selection([('draft', 'current'), ('milestone', 'm1')], max_chars=1200,
                                          priority_targets=[('draft', 'current'), ('milestone', 'm1')])
    assert [r['id'] for r in result['included']] == [newest['id'], milestone['id']]
    assert not result['blockers']


def test_resolved_or_unrelated_feedback_not_selected(tmp_path):
    store = NoteStore(tmp_path)
    note = add(store, 'Resolved text'); store.resolve(note['id'])
    add(store, 'unrelated', 'other')
    assert store.operator_notes([('draft', 'current')]) == ''


def test_real_revision_preview_delivers_latest_complete_task(tmp_path):
    ws, prior = setup_revision(tmp_path)
    for i in range(5): add(ws.notes, f'OLD TASK {i} ' + 'x' * 1400, prior['id'])
    note = add(ws.notes, 'NEW TESTS-ONLY TASK ' + 'important feedback ' * 115, prior['id'])
    before = ws.notes.path.read_bytes()
    info = revision_context.inspect_revision(ws, prior['id'])
    selected = info['feedback']
    prompt = draft_prompt(ws, ws.plan()['milestones'][0], source_context(ws), revision=prior)
    assert note['text'] in prompt
    assert selected['included'][0]['id'] == note['id'] and selected['omitted']
    assert not info['blockers'] and ws.notes.path.read_bytes() == before


def test_oversized_required_feedback_refuses_before_model_call(tmp_path):
    ws, prior = setup_revision(tmp_path)
    add(ws.notes, 'x' * 3900, prior['id'])
    info = revision_context.inspect_revision(ws, prior['id'])
    assert info['preview'] is None and any('Latest feedback' in b for b in info['blockers'])
    with pytest.raises(WorkspaceError, match='Latest feedback'):
        draft_prompt(ws, ws.plan()['milestones'][0], source_context(ws), revision=prior)
    class NoCall:
        def call(self, *a, **k): pytest.fail('oversized feedback triggered inference')
    with pytest.raises(WorkspaceError, match='Latest feedback'):
        draft_files(ws, NoCall(), revision=prior)


def test_notes_off_remains_explicit_and_unmodified(tmp_path):
    ws, prior = setup_revision(tmp_path)
    add(ws.notes, 'UNIQUE UNDELIVERED NOTE', prior['id'])
    ws.update_settings({'read_notes': False})
    info = revision_context.inspect_revision(ws, prior['id'])
    assert info['feedback']['enabled'] is False and not info['feedback']['included']
    assert 'UNIQUE UNDELIVERED NOTE' not in draft_prompt(ws, ws.plan()['milestones'][0], revision=prior)
