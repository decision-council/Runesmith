"""Ordinary author budgets follow source and contract, never feedback wording."""
import hashlib
import json
import uuid

import pytest

from runesmith.app import building
from runesmith.app.planner import PlannerUnavailable, milestone_contract, source_context
from runesmith.app.workspace import WorkspaceError, _read_json, _write_json
from test_build_steps import setup


def note(ws, text):
    ws.notes.add(target_type='milestone', target_id='m1', author='external-trainer', text=text)


def failed_author(*args, **kwargs):
    raise WorkspaceError('Fixture author refused; no remote call.')


def spend(ws, monkeypatch, count=3):
    monkeypatch.setattr(building, 'draft_files', failed_author)
    for _ in range(count):
        with pytest.raises(WorkspaceError, match='Fixture author'):
            building.build_step(ws, None, author_only=True)


def legacy_attempt(ws, *, state='failed', scope=None, **changes):
    contract = milestone_contract(ws, ws.plan()['milestones'][0])
    snapshot = source_context(ws)['snapshot_digest']
    row = dict(contract=contract, snapshot_digest=snapshot, state=state,
        scope=scope or hashlib.sha256((contract + snapshot + ws.notes_for_plan()).encode()).hexdigest())
    row.update(changes)
    path = ws.home / 'build-attempts' / (uuid.uuid4().hex + '.json')
    _write_json(path, row)
    return path, row


def test_feedback_does_not_reset_normal_attempt_limit(tmp_path, monkeypatch):
    ws = setup(tmp_path); spend(ws, monkeypatch)
    before = {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')}
    note(ws, 'More precise failure feedback; not a new milestone or source.')
    result = building.build_step(ws, None, author_only=True)
    assert result['replan_needed']
    assert before == {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')}
    assert building.build_escalation_status(ws)['attempts'] == 3


def test_legacy_feedback_scopes_aggregate_without_rewriting_receipts(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    for i in range(3):
        note(ws, f'Feedback version {i}')
        legacy_attempt(ws)
    before = {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')}
    note(ws, 'New note after three old attempts')
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Allowance was replenished'))
    result = building.build_step(ws, None, author_only=True)
    assert result['replan_needed']
    assert before == {p.name: p.read_bytes() for p in (ws.home / 'build-attempts').glob('*.json')}


@pytest.mark.parametrize('damage', ['corrupt', 'duplicate', 'nonfinite', 'overflow', 'list', 'unknown', 'uncertain', 'missing_source'])
def test_unclear_receipts_block_normal_dispatch(tmp_path, monkeypatch, damage):
    ws = setup(tmp_path)
    path, row = legacy_attempt(ws)
    if damage == 'corrupt': path.write_text('{')
    elif damage == 'duplicate': path.write_text(json.dumps(row)[:-1] + ',"state":"failed"}')
    elif damage == 'nonfinite': path.write_text(json.dumps(dict(row, extra=float('nan'))))
    elif damage == 'overflow': path.write_text(json.dumps(row)[:-1] + ',"extra":1e999}')
    elif damage == 'list': path.write_text('[]')
    elif damage == 'missing_source': row.pop('snapshot_digest'); _write_json(path, row)
    else: _write_json(path, dict(row, state=damage))
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Damaged/unresolved budget called author'))
    result = building.build_step(ws, None, author_only=True)
    assert result.get('allowance_blocked')
    before = {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    info = ws.work()['build_escalation']
    assert not info['eligible'] and not info['allowance']['known'] and not info['allowance']['can_draft']
    assert info['attempts'] is None
    assert before == {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}


def test_legacy_escalation_stays_consumed_after_feedback_change(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    for _ in range(3): _, row = legacy_attempt(ws)
    _write_json(ws.home / 'build-escalations' / 'e123.json',
        dict(id='e123', contract=row['contract'], scope=row['scope'], state='failed', milestone='m1'))
    note(ws, 'Changing advice cannot repeat the separately receipted continuation.')
    info = building.build_escalation_status(ws)
    assert info['attempts'] == 3 and info['used'] and not info['eligible']
    with pytest.raises(WorkspaceError, match='No one-shot'):
        building.escalate_build(ws, None)


def test_new_escalation_records_source_and_never_repeats(tmp_path, monkeypatch):
    ws = setup(tmp_path); spend(ws, monkeypatch)
    with pytest.raises(WorkspaceError, match='Fixture author'): building.escalate_build(ws, None)
    [path] = list((ws.home / 'build-escalations').glob('*.json'))
    old = path.read_bytes(); record = _read_json(path, {})
    assert record['snapshot_digest'] == source_context(ws)['snapshot_digest']
    note(ws, 'A different explanation, still the same work.')
    assert building.build_escalation_status(ws)['used']
    with pytest.raises(WorkspaceError, match='No one-shot'): building.escalate_build(ws, None)
    assert path.read_bytes() == old


# A receipt left "started" is not in this list any more: a restart or a build settles it as used ("interrupted by a restart"),
# which is still never unused (tests/test_interrupted_escalation.py). A state nothing knows stays unresolved, for the owner.
@pytest.mark.parametrize('kind', ['unknown_source', 'corrupt', 'conflicting_source', 'unknown_state'])
def test_escalation_evidence_cannot_become_unused(tmp_path, monkeypatch, kind):
    ws = setup(tmp_path); _, row = legacy_attempt(ws)
    record = dict(id='e123', state='failed', contract=row['contract'], scope=row['scope'])
    if kind == 'unknown_source': record['scope'] = 'a' * 64
    if kind == 'conflicting_source': record['snapshot_digest'] = 'b' * 64
    if kind == 'unknown_state': record['state'] = 'uncertain'
    path = ws.home / 'build-escalations' / 'e123.json'; _write_json(path, record)
    if kind == 'corrupt': path.write_text('{')
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Ambiguous continuation called author'))
    assert building.build_step(ws, None, author_only=True)['allowance_blocked']
    status = building.build_escalation_status(ws)
    assert not status['eligible'] and status['used'] is None and not status['allowance']['known']


def test_old_settled_different_contract_does_not_poison_current_budget(tmp_path):
    ws = setup(tmp_path)
    _, old = legacy_attempt(ws, contract='f' * 64, snapshot_digest=None)
    info = building.build_escalation_status(ws)
    assert info['attempts'] == 0 and info['allowance']['remaining'] == 3
    assert info['allowance']['can_draft']


def test_conflicting_alias_is_not_silently_counted_elsewhere(tmp_path, monkeypatch):
    ws = setup(tmp_path); _, row = legacy_attempt(ws)
    legacy_attempt(ws, scope=row['scope'], contract='f' * 64, snapshot_digest=None)
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Conflicting receipt dispatched'))
    assert building.build_step(ws, None, author_only=True)['allowance_blocked']


def test_source_boundary_is_distinct_but_returning_to_it_keeps_spent_budget(tmp_path, monkeypatch):
    ws = setup(tmp_path); spend(ws, monkeypatch)
    original = building.build_escalation_status(ws)['scope']
    source = ws.root / 'new.py'; source.write_text('changed = True\n')
    info = building.build_escalation_status(ws)
    assert info['scope'] != original and info['allowance']['remaining'] == 3
    source.unlink()  # Disposable fixture: restore the identical original source.
    info = building.build_escalation_status(ws)
    assert info['scope'] == original and info['allowance']['remaining'] == 0


def test_waiting_candidate_reuse_is_not_a_fourth_attempt(tmp_path, monkeypatch):
    ws = setup(tmp_path)
    first = building.build_step(ws, ws.router(), author_only=True)
    for _ in range(2): legacy_attempt(ws)
    info = building.build_escalation_status(ws)['allowance']
    assert info['used'] == 3 and info['remaining'] == 0 and info['reuse_draft'] == first['draft'] and info['can_draft']
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Saved draft must be reused'))
    assert building.build_step(ws, None, author_only=True)['draft'] == first['draft']
    assert len(list((ws.home / 'build-attempts').glob('*.json'))) == 3


def test_mode_disabled_is_visible_without_resetting_budget(tmp_path):
    from runesmith.app.work_modes import configuration, save
    ws = setup(tmp_path); legacy_attempt(ws)
    policy = configuration(ws)
    save(ws, [dict(r, enabled=False) if r['executor'] == 'build' else r for r in policy['modes']],
         policy['revision'], 'Disable build but retain receipts')
    state = building.build_escalation_status(ws)
    assert state['allowance']['remaining'] == 2 and not state['allowance']['can_draft']
    assert 'off' in ' '.join(state['allowance']['blockers'])


def test_revision_counts_other_legacy_scopes_and_cannot_refill(tmp_path, monkeypatch):
    from test_author_revisions import setup as revision_setup
    from runesmith.app.author_revisions import revision_status
    ws, parent = revision_setup(tmp_path, monkeypatch)
    for i in range(2):
        note(ws, f'Legacy feedback {i}')
        legacy_attempt(ws)
    info = revision_status(ws, parent['id'])
    assert info['allowance']['used'] == 3 and not info['eligible']
    assert 'exhausted' in ' '.join(info['blockers'])


def test_legacy_parent_then_new_revision_share_proven_boundary(tmp_path, monkeypatch):
    from test_author_revisions import setup as revision_setup, request, mark_for_revision
    from runesmith.app.author_revisions import revision_status
    from runesmith.app.build_jobs import execute_build_job
    ws, parent = revision_setup(tmp_path, monkeypatch)
    [path] = list((ws.home / 'build-attempts').glob('*.json'))
    old = _read_json(path, {}); _write_json(path, dict(old, scope='a' * 64))
    immutable = path.read_bytes()
    info = revision_status(ws, parent['id']); assert info['eligible']
    child = ws._draft(execute_build_job(ws, request(ws, parent['id']))['draft'])
    mark_for_revision(ws, child)
    state = revision_status(ws, child['id'])
    assert state['eligible'] and state['allowance']['used'] == 2 and state['allowance']['remaining'] == 1
    assert path.read_bytes() == immutable
    assert building.build_escalation_status(ws)['allowance']['used'] == 2


def test_normal_build_cannot_bypass_unproven_revision_lineage(tmp_path, monkeypatch):
    from test_author_revisions import setup as revision_setup, tree
    ws, parent = revision_setup(tmp_path, monkeypatch, legacy=True)
    before = tree(ws.home)
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Normal build bypassed legacy lineage'))
    result = building.build_step(ws, None, author_only=True)
    assert result['allowance_blocked'] and 'No new budget' in result['summary']
    view = building.build_escalation_status(ws)['allowance']
    assert not view['known'] and not view['can_draft'] and view['remaining'] is None
    assert view['recorded_attempts'] == 0 and tree(ws.home) == before


def test_normal_revision_and_focused_revision_share_remaining_calls(tmp_path, monkeypatch):
    from test_author_revisions import setup as revision_setup, mark_for_revision, request, answer
    from runesmith.app.author_revisions import revision_status
    from runesmith.app.build_jobs import execute_build_job
    from test_studio import scripted
    ws, first = revision_setup(tmp_path, monkeypatch)
    second = ws._draft(building.build_step(ws, ws.router(), author_only=True)['draft'])
    mark_for_revision(ws, second)
    assert revision_status(ws, second['id'])['allowance']['remaining'] == 1
    scripted(ws, [answer(3, 4)], roles=('plan',))
    last = ws._draft(execute_build_job(ws, request(ws, second['id']))['draft'])
    mark_for_revision(ws, last)
    assert not revision_status(ws, last['id'])['eligible']
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Fourth ordinary call'))
    assert building.build_step(ws, None, author_only=True)['replan_needed']


@pytest.mark.parametrize('change', ['source', 'contract'])
def test_reservation_cannot_charge_another_source_or_contract(tmp_path, monkeypatch, change):
    ws = setup(tmp_path)
    real_context = building.source_context
    def changed(*a, **kw):
        result = real_context(*a, **kw)
        if change == 'source': (ws.root / 'changed.py').write_text('new = True\n')
        else: ws.update_milestone('m1', {'done_when':'Changed during reservation'})
        return result
    monkeypatch.setattr(building, 'source_context', changed)
    class NoCall:
        def call(self, *a, **kw): pytest.fail('Reservation no longer matches source')
    with pytest.raises(PlannerUnavailable, match='reservation no longer matches'):
        building.build_step(ws, NoCall(), author_only=True)
    [path] = list((ws.home / 'build-attempts').glob('*.json'))
    assert _read_json(path, {})['state'] == 'failed'
    assert not list((ws.home / 'build-author-packets').glob('*.json'))


@pytest.mark.parametrize('folder', ['build-attempts', 'build-escalations'])
def test_unreadable_receipt_directory_is_not_an_empty_allowance(tmp_path, monkeypatch, folder):
    from pathlib import Path
    ws = setup(tmp_path); directory = ws.home / folder; directory.mkdir(exist_ok=True)
    real = Path.iterdir
    def unreadable(path):
        if path == directory: raise PermissionError('Fixture locked directory')
        return real(path)
    monkeypatch.setattr(Path, 'iterdir', unreadable)
    monkeypatch.setattr(building, 'draft_files', lambda *a, **k: pytest.fail('Unreadable history dispatched'))
    result = building.build_step(ws, None, author_only=True)
    assert result['allowance_blocked'] and 'unreadable' in result['summary']
    assert not building.build_escalation_status(ws)['allowance']['known']


def test_an_unresolved_call_blocks_its_own_milestone_not_the_others(tmp_path):
    # Journey J11-B6: an in-flight call for one milestone refused every milestone's allowance.
    import hashlib, json as _json
    from runesmith.app.author_allowance import ordinary_allowance
    from runesmith.app.workspace import Workspace, WorkspaceError
    ws = Workspace(tmp_path)
    digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
    mine, other, source = digest('contract-a'), digest('contract-b'), digest('source')
    folder = ws.home / 'build-attempts'; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'x.json').write_text(_json.dumps({'contract': mine, 'scope': digest('scope-a'), 'snapshot_digest': source,
                                                'state': 'uncertain'}), encoding='utf-8')
    assert ordinary_allowance(ws, other, source)['remaining'] == 3
    import pytest as _pytest
    with _pytest.raises(WorkspaceError, match='Unresolved author allowance receipt'):
        ordinary_allowance(ws, mine, source)
    (folder / 'y.json').write_text('{damaged', encoding='utf-8')
    with _pytest.raises(WorkspaceError, match='Damaged author allowance receipt'):
        ordinary_allowance(ws, other, source)


@pytest.mark.parametrize('folder', ['build-attempts', 'build-escalations'])
@pytest.mark.parametrize('state', ['transport_failed', 'context_gap'])
def test_a_call_that_got_no_answer_for_a_file_it_was_shown_uses_no_allowance(tmp_path, folder, state):
    # Journey J11-B15 (and J2-B9 before it): no model answered, or it answered for a file it was never shown.
    from runesmith.app.author_allowance import ordinary_allowance
    ws = setup(tmp_path)
    contract = milestone_contract(ws, ws.plan()['milestones'][0])
    snapshot = source_context(ws)['snapshot_digest']
    row = dict(id='e1', state=state, contract=contract, scope='5' * 64, snapshot_digest=snapshot, milestone='m1')
    _write_json(ws.home / folder / (uuid.uuid4().hex + '.json'), row)
    allowance = ordinary_allowance(ws, contract, snapshot)
    assert allowance['used'] == 0 and allowance['remaining'] == 3 and allowance['escalations'] == []
