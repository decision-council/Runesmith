"""Saved review metadata survives the real Studio read projection unchanged."""
from types import SimpleNamespace

from runesmith.app.planner import draft_files
from runesmith.app.server import api_work
from test_build_steps import setup


def test_review_feedback_is_read_only_and_not_promoted_to_verification(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    draft = draft_files(ws, ws.router())
    reason = 'A targeted test passes but a preserved behavior regressed.'
    note = ws.notes.add(target_type='draft', target_id=draft['id'], target_label=draft['title'],
                        author='external-trainer', text=reason)
    ws._save_draft_state(draft, 'needs_revision', review_reason=reason,
                        review_requested_by='external-trainer', review_note=note['id'])
    before = {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    monkeypatch.setattr(ws, 'router', lambda **kwargs: (_ for _ in ()).throw(AssertionError('No inference from review projection')))
    row = next(d for d in api_work(SimpleNamespace(ws=ws), {}, {})['drafts'] if d['id'] == draft['id'])
    assert row['review_reason'] == reason and row['review_requested_by'] == 'external-trainer'
    assert row['review_note'] == note['id'] and row['state'] == 'needs_revision'
    assert row.get('verification') is None and not row.get('verified')
    assert before == {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
