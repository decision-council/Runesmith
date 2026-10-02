"""Bounded author-only jobs: offline inputs and fake gateway, never live Hats."""
import json
import uuid
from types import SimpleNamespace

import pytest

from runesmith.app import building
from runesmith.app.author_recovery import pending_authors, resume_author
from runesmith.app.author_revisions import revision_status
from runesmith.app.build_jobs import BuildJob, execute_build_job, run_synchronous_build_job
from runesmith.app.planner import PlannerUnavailable, draft_files
from runesmith.app.revision_context import inspect_revision, save_selection
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import WorkspaceError, _read_json, _write_json
from runesmith.instruments import Router
from test_author_recovery import Gateway, instrument
from test_build_context import planned
from test_studio import scripted


def answer(before=2, after=3):
    return {'title': 'Focused revision', 'files': [{'path': 'app.py', 'edits': [
        {'old_text': f'return {before}', 'new_text': f'return {after}'}]}]}


def mark_for_revision(ws, draft):
    ws._save_draft_state(draft, 'needs_revision')
    ws.notes.add(target_type='draft', target_id=draft['id'], author='external-trainer',
        text='Fix the observed return value. Retain other() and existing CLI behavior. This is public review feedback, not acceptance.')
    data = inspect_revision(ws, draft['id'])
    unit = next(row for row in data['units'] if row['label'] == 'target')
    save_selection(ws, draft['id'], version=data['version'],
        selections=[{'path': unit['path'], 'unit': unit['unit']}], reason='One known function, other behavior retained.')


def setup(tmp_path, monkeypatch, *, legacy=False):
    ws = planned(tmp_path)
    (ws.root / 'app.py').write_text('def target():\n    return 1\n\ndef other():\n    return 999\n')
    owner = ws.home / 'acceptance' / 'm1.py'; owner.parent.mkdir(exist_ok=True)
    owner.write_text('# PRIVATE_OWNER_SENTINEL never in an author prompt\n')
    scripted(ws, [answer(1, 2)], roles=('plan',))
    monkeypatch.setattr(building, '_check_and_record', lambda ws, draft, *a, **kw: {'draft': draft['id']})
    draft = draft_files(ws, ws.router()) if legacy else ws._draft(building.build_step(ws, ws.router())['draft'])
    mark_for_revision(ws, draft)
    scripted(ws, [answer()], roles=('plan',))
    return ws, ws._draft(draft['id'])


def request(ws, draft_id, *, operation=None, instrument_name='offline'):
    state = revision_status(ws, draft_id, instrument_name)
    assert state['eligible'], state['blockers']
    return BuildJob('revise', {'draft_id': draft_id, 'quote_id': state['quote']['id'],
        'instrument': instrument_name, 'operation_id': operation or uuid.uuid4().hex,
        'reason': 'One explicit author-only attempt. No new checks or apply.'})


def tree(home):
    return {p.relative_to(home).as_posix(): p.read_bytes() for p in home.rglob('*') if p.is_file()}


def test_quote_is_read_only_and_untrusted_legacy_gets_no_new_allowance(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch, legacy=True)
    from runesmith.app.server import api_revision_request
    before = tree(ws.home)
    result = api_revision_request(SimpleNamespace(ws=ws), {'instrument': ['offline']}, {}, draft['id'])
    assert not result['eligible'] and 'No new budget' in ' '.join(result['blockers'])
    assert tree(ws.home) == before


def test_eligible_status_and_api_queue_preserve_home_before_execution(tmp_path, monkeypatch):
    from runesmith.app.server import api_revision_request, api_worker_run
    from runesmith.app.worker import Worker, EventBus
    ws, draft = setup(tmp_path, monkeypatch); worker = Worker(ws, EventBus())
    before = tree(ws.home)
    info = api_revision_request(SimpleNamespace(ws=ws), {}, {}, draft['id'])
    assert info['eligible'] and info['instrument'] == 'offline'
    job = request(ws, draft['id'])
    queued = api_worker_run(SimpleNamespace(worker=worker), {}, {'job': 'revise', 'params': dict(job.params)})
    assert queued['params'] == dict(job.params) and queued['kind'] == 'revise'
    assert api_worker_run(SimpleNamespace(worker=worker), {}, {'job': 'revise', 'params': dict(job.params)}) == queued
    after = tree(ws.home)
    assert len(worker._jobs) == 1 and set(after) - set(before) == {'STUDIO_QUEUE.json'}
    assert all(after[name] == value for name, value in before.items())
    assert _read_json(ws.home / 'STUDIO_QUEUE.json', {})['jobs'] == [queued]


def test_mode_can_be_revoked_after_queue_without_a_call(tmp_path, monkeypatch):
    from runesmith.app.work_modes import configuration, save
    from runesmith.app.worker import Worker, EventBus
    ws, draft = setup(tmp_path, monkeypatch); worker = Worker(ws, EventBus())
    queued = worker.enqueue('revise', **request(ws, draft['id']).params)
    policy = configuration(ws)
    modes = [dict(row, enabled=False) if row['executor'] == 'build' else row for row in policy['modes']]
    save(ws, modes, policy['revision'], 'Revoke build before revision dispatch')
    monkeypatch.setattr('runesmith.config.build_router', lambda *a, **kw: pytest.fail('Revoked mode called a model'))
    result = worker._execute(queued)
    assert result['result'] == 'failed' and 'off' in result['outcome']['error']
    assert not (ws.home / 'build-revisions').exists()


def test_shared_worker_job_admits_unverified_without_checks_apply_or_followup(tmp_path, monkeypatch):
    ws, parent = setup(tmp_path, monkeypatch)
    for method in ('verify_draft', '_check_and_record'):
        monkeypatch.setattr(building, method, lambda *a, **kw: pytest.fail('Author-only must not check'))
    before = collect_snapshot(ws)['digest']; old_parent = ws._draft(parent['id'])
    state = revision_status(ws, parent['id']); assert state['allowance']['remaining'] == 2
    job = request(ws, parent['id'])
    outcome = run_synchronous_build_job(ws.root, job, home=ws.home)
    assert outcome['result'] == 'done', outcome
    result = outcome['outcome']; revised = ws._draft(result['draft'])
    assert result['author_only'] and not result['advanced']
    assert not revised.get('verified') and not revised.get('verification')
    assert revised['state'] == 'waiting' and 'return 3' in revised['files'][0]['content']
    assert 'return 999' in revised['files'][0]['content']
    assert ws._draft(parent['id']) == old_parent and collect_snapshot(ws)['digest'] == before
    assert ws.plan()['milestones'][0]['status'] == 'open'
    assert not (ws.home / 'STUDIO_CURRENT.json').exists()
    assert len(_read_json(ws.home / 'STUDIO_JOBS.json', [])) == 1
    assert not (ws.home / 'build-runs').exists()
    packet = _read_json(ws.home / 'build-author-packets' / (revised['author_request_key'] + '.json'), {})['packet']
    exposure = _read_json(ws.home / packet['memory_exposure'], {})
    assert packet['revision']['id'] == parent['id'] and packet['explicit_revision']
    assert exposure['prompt_sha256'] == state['quote']['binding']['prompt']


def test_notes_focus_and_descendant_ids_never_refill_shared_allowance(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch); scopes = []
    for before in (2, 3):
        scripted(ws, [answer(before, before + 1)], roles=('plan',))
        quote = revision_status(ws, draft['id']); scopes.append(quote['allowance']['scope'])
        result = execute_build_job(ws, request(ws, draft['id']))
        draft = ws._draft(result['draft']); mark_for_revision(ws, draft)
    info = revision_status(ws, draft['id'])
    assert not info['eligible'] and 'exhausted' in ' '.join(info['blockers'])
    assert info['allowance']['used'] == 3 and info['allowance']['remaining'] == 0
    assert scopes[0] == scopes[1] == info['allowance']['scope']
    assert len(list((ws.home / 'build-attempts').glob('*.json'))) == 3


def test_duplicate_operation_is_one_admission_and_changed_signature_refused(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch); job = request(ws, draft['id'])
    first = execute_build_job(ws, job); before = tree(ws.home)
    repeated = execute_build_job(ws, job)
    assert repeated['already_used'] and repeated['draft'] == first['draft']
    assert tree(ws.home) == before and len(ws.drafts()) == 2
    with pytest.raises(WorkspaceError, match='different'):
        execute_build_job(ws, BuildJob('revise', dict(job.params, reason='Different authorization')))
    assert tree(ws.home) == before


def change(ws, draft, kind):
    if kind == 'source': (ws.root / 'another.py').write_text('x = 9\n')
    elif kind == 'candidate': ws._save_draft_state(draft, 'needs_revision', review_reason='Changed diagnosis')
    elif kind == 'contract': ws.update_milestone('m1', {'done_when': 'A different requirement'})
    elif kind == 'owner': (ws.home / 'acceptance' / 'm1.py').write_text('# changed owner bundle\n')
    elif kind == 'feedback': ws.notes.add(target_type='draft', target_id=draft['id'], text='New relevant feedback', author='owner')
    elif kind == 'focus':
        info = inspect_revision(ws, draft['id'])
        save_selection(ws, draft['id'], version=info['version'], selections=[{'path': 'app.py', 'unit': '*'}], reason='Broader scope')
    elif kind == 'route': scripted(ws, [answer(2, 4)], roles=('plan',))


@pytest.mark.parametrize('kind', ['source', 'candidate', 'contract', 'owner', 'feedback', 'focus', 'route'])
def test_stale_quote_refused_before_reservation_or_transport(tmp_path, monkeypatch, kind):
    ws, draft = setup(tmp_path, monkeypatch); job = request(ws, draft['id'])
    change(ws, draft, kind)
    before = tree(ws.home)
    monkeypatch.setattr('runesmith.config.build_router', lambda *a, **kw: pytest.fail('Stale quote constructed router'))
    with pytest.raises(WorkspaceError, match='stale'): execute_build_job(ws, job)
    assert tree(ws.home) == before


def test_change_between_quote_validation_and_reservation_is_refused(tmp_path, monkeypatch):
    import runesmith.app.author_revisions as revisions
    ws, draft = setup(tmp_path, monkeypatch); job = request(ws, draft['id'])
    original = revisions._inputs; reads = []
    def changed(*args, **kwargs):
        reads.append(1)
        if len(reads) == 2: change(ws, draft, 'feedback')
        return original(*args, **kwargs)
    monkeypatch.setattr(revisions, '_inputs', changed)
    monkeypatch.setattr('runesmith.config.build_router', lambda *a, **kw: pytest.fail('Changed quote must not dispatch'))
    with pytest.raises(WorkspaceError, match='validating the quote'): execute_build_job(ws, job)
    assert not (ws.home / 'build-revisions').exists()
    assert len(list((ws.home / 'build-attempts').glob('*.json'))) == 1


def fake_gateway(ws, monkeypatch):
    ws.save_instrument('model', {'kind': 'milliner', 'model': 'free:worker', 'base_url': 'http://localhost:8765'},
                       key_value='unused', roles=['plan'])
    gateway = Gateway(); gateway.answer = answer()
    inst = instrument(ws.home, gateway)
    monkeypatch.setattr('runesmith.config.build_instrument', lambda *a, **kw: inst)
    # Use the real Router and Milliner ticket custody with a fake transport only.
    return gateway


def test_successful_gateway_response_is_not_blocked_as_its_own_pending_request(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch); gateway = fake_gateway(ws, monkeypatch); gateway.fail_poll = False
    result = execute_build_job(ws, request(ws, draft['id'], instrument_name='model'))
    assert result['draft'] and len(ws.drafts()) == 2 and not pending_authors(ws)
    posts = [body for method, body in gateway.requests if method == 'POST']
    assert len(posts) == 1
    prompt = posts[0]['prompt']
    assert 'Retain other()' in prompt and 'external-trainer' in prompt
    assert 'PRIVATE_OWNER_SENTINEL' not in prompt and 'return 999' not in prompt
    assert 'editable_units' in prompt


def test_uncertain_job_reuses_original_ticket_once_and_preserves_budget(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch); gateway = fake_gateway(ws, monkeypatch)
    job = request(ws, draft['id'], instrument_name='model')
    with pytest.raises(PlannerUnavailable): execute_build_job(ws, job)
    saved = execute_build_job(ws, job)
    assert saved['already_used'] and saved['state'] == 'uncertain'
    assert not revision_status(ws, draft['id'])['eligible']
    [pending] = pending_authors(ws); gateway.fail_poll = False
    result = resume_author(ws, pending['id'])
    assert result['draft'] and len(ws.drafts()) == 2
    assert resume_author(ws, pending['id'])['already_used']
    assert execute_build_job(ws, job)['draft'] == result['draft']
    assert [m for m, _ in gateway.requests].count('POST') == 1
    assert len(list((ws.home / 'build-attempts').glob('*.json'))) == 2
    assert not (ws.home / 'build-runs').exists() and not ws._draft(result['draft']).get('verified')


def test_lost_submission_response_stays_spent_and_is_never_reposted(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch); fake_gateway(ws, monkeypatch)
    calls = []
    def lost(method, *args):
        calls.append(method); raise TimeoutError('Lost ticket response')
    inst = instrument(ws.home, lost)
    monkeypatch.setattr('runesmith.config.build_instrument', lambda *a, **kw: inst)
    job = request(ws, draft['id'], instrument_name='model')
    with pytest.raises(PlannerUnavailable): execute_build_job(ws, job)
    assert execute_build_job(ws, job)['state'] == 'uncertain'
    assert calls == ['POST'] and len(ws.drafts()) == 1
    assert not revision_status(ws, draft['id'])['eligible']
    assert not pending_authors(ws)[0]['can_resume']


def test_mid_call_feedback_change_retains_answer_but_prevents_admission(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch); gateway = fake_gateway(ws, monkeypatch); gateway.fail_poll = False
    inst = instrument(ws.home, gateway)
    original = inst.complete
    def changed(**kwargs):
        result = original(**kwargs)
        change(ws, draft, 'feedback')
        return result
    monkeypatch.setattr(inst, 'complete', changed)
    monkeypatch.setattr('runesmith.config.build_instrument', lambda *a, **kw: inst)
    job = request(ws, draft['id'], instrument_name='model')
    with pytest.raises(WorkspaceError, match='changed'): execute_build_job(ws, job)
    assert execute_build_job(ws, job)['state'] == 'uncertain'
    assert len(ws.drafts()) == 1 and list((ws.home / 'draft-answers').glob('*.json'))
    assert [m for m, _ in gateway.requests].count('POST') == 1


def test_stop_after_response_retains_answer_for_explicit_recovery(tmp_path, monkeypatch):
    from runesmith.app.worker import StopRequested
    ws, draft = setup(tmp_path, monkeypatch); gateway = fake_gateway(ws, monkeypatch); gateway.fail_poll = False
    stop = [False]
    def record(event): ws.record_call(event); stop[0] = True
    def checkpoint():
        if stop[0]: raise StopRequested()
    job = request(ws, draft['id'], instrument_name='model')
    with pytest.raises(StopRequested): execute_build_job(ws, job, checkpoint=checkpoint, on_call=record)
    assert len(ws.drafts()) == 1 and list((ws.home / 'draft-answers').glob('*.json'))
    [pending] = pending_authors(ws)
    result = resume_author(ws, pending['id'])
    assert result['draft'] and len(ws.drafts()) == 2
    assert [m for m, _ in gateway.requests].count('POST') == 1


@pytest.mark.parametrize('kind', ['candidate', 'owner', 'feedback', 'focus', 'route'])
def test_saved_ticket_recovery_does_not_bypass_revision_binding(tmp_path, monkeypatch, kind):
    ws, draft = setup(tmp_path, monkeypatch); gateway = fake_gateway(ws, monkeypatch)
    job = request(ws, draft['id'], instrument_name='model')
    with pytest.raises(PlannerUnavailable): execute_build_job(ws, job)
    [pending] = pending_authors(ws)
    if kind == 'focus':
        # Simulate another writer editing persisted policy despite pending guards.
        path = ws.home / 'revision-focus' / (draft['id'] + '.json')
        data = _read_json(path, {}); data['enabled'] = False; _write_json(path, data)
    elif kind == 'route':
        config = ws.config(); config['instruments']['model']['timeout_s'] = 99; ws.save_config(config)
    else: change(ws, draft, kind)
    gateway.fail_poll = False
    with pytest.raises(WorkspaceError): resume_author(ws, pending['id'])
    assert len(ws.drafts()) == 1 and list((ws.home / 'draft-answers').glob('*.json'))
    assert [m for m, _ in gateway.requests].count('POST') == 1
    assert execute_build_job(ws, job)['state'] == 'failed'


def test_unrelated_pending_or_corrupt_reservation_fail_closed(tmp_path, monkeypatch):
    ws, draft = setup(tmp_path, monkeypatch)
    monkeypatch.setattr('runesmith.app.author_recovery.pending_authors', lambda ws: [{'key': 'other'}])
    assert 'Recover' in ' '.join(revision_status(ws, draft['id'])['blockers'])
    monkeypatch.setattr('runesmith.app.author_recovery.pending_authors', lambda ws: [])
    _write_json(ws.home / 'build-revisions' / (uuid.uuid4().hex + '.json'), {'attempt_id': '../outside.json'})
    assert 'damaged' in ' '.join(revision_status(ws, draft['id'])['blockers'])


@pytest.mark.parametrize('state', [None, 'unknown', 'started', 'uncertain'])
def test_unsettled_or_missing_attempt_state_grants_no_revision(tmp_path, monkeypatch, state):
    ws, draft = setup(tmp_path, monkeypatch)
    _write_json(ws.home / 'build-attempts' / (uuid.uuid4().hex + '.json'), {'state': state})
    info = revision_status(ws, draft['id'])
    assert not info['eligible'] and 'unfinished or damaged' in ' '.join(info['blockers'])


@pytest.mark.parametrize('damage', ['removed_reference', 'missing_attempt'])
def test_missing_attempt_evidence_cannot_downgrade_to_ordinary_recovery(tmp_path, monkeypatch, damage):
    from runesmith.app.author_recovery import read_packet
    ws, draft = setup(tmp_path, monkeypatch); gateway = fake_gateway(ws, monkeypatch)
    job = request(ws, draft['id'], instrument_name='model')
    with pytest.raises(PlannerUnavailable): execute_build_job(ws, job)
    [pending] = pending_authors(ws); packet = read_packet(ws, pending['key'])
    assert packet['revision_operation'] == job.params['operation_id']
    path = ws.home / 'build-attempts' / packet['attempt_id']
    if damage == 'missing_attempt': path.unlink()
    else:
        record = _read_json(path, {}); record.pop('revision_operation'); _write_json(path, record)
    gateway.fail_poll = False
    with pytest.raises(WorkspaceError): resume_author(ws, pending['id'])
    assert len(ws.drafts()) == 1 and [m for m, _ in gateway.requests].count('POST') == 1


@pytest.mark.parametrize('folder', ['build-attempts', 'build-escalations', 'build-corrections', 'build-supplements'])
@pytest.mark.parametrize('state', ['context_gap', 'transport_failed'])
def test_a_call_that_got_no_answer_does_not_block_a_revision(tmp_path, monkeypatch, folder, state):
    # Review of J11-B15: _unresolved took every such row for an unfinished call and refused every revision.
    from runesmith.app.author_revisions import _unresolved
    ws, draft = setup(tmp_path, monkeypatch)
    _write_json(ws.home / folder / (uuid.uuid4().hex + '.json'),
                {'state': state, 'contract': 'c' * 64, 'scope': '5' * 64, 'snapshot_digest': 'd' * 64})
    _unresolved(ws)
    assert revision_status(ws, draft['id'])['eligible']


def test_an_author_only_revision_refused_for_an_unshown_file_uses_no_try(tmp_path, monkeypatch):
    # Review of J11-B15: a revision's refusal for an unshown file was recorded as a used "failed" try.
    from runesmith.app.author_revisions import _unresolved
    from runesmith.app.planner import _not_shown
    ws, parent = setup(tmp_path, monkeypatch)
    before = revision_status(ws, parent['id'])['allowance']
    job = request(ws, parent['id'])
    def refused(*args, **kwargs):
        raise _not_shown('huge.js', {'omission_reasons': {'huge.js': 'packet_budget'}})
    monkeypatch.setattr('runesmith.app.planner.draft_files', refused)
    with pytest.raises(PlannerUnavailable, match='huge.js was not shown'):
        execute_build_job(ws, job)
    [operation] = (ws.home / 'build-revisions').glob('*.json')
    assert _read_json(operation, {})['state'] == 'context_gap'
    assert [_read_json(p, {})['state'] for p in (ws.home / 'build-attempts').glob('*.json')].count('context_gap') == 1
    _unresolved(ws)
    after = revision_status(ws, parent['id'])
    assert after['eligible'] and after['allowance']['remaining'] == before['remaining']
