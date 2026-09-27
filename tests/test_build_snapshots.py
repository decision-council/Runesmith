import hashlib
import json

import pytest

from runesmith.app.building import build_step, verify_draft
from runesmith.app.planner import draft_files, source_context, PlannerUnavailable
from runesmith.app.snapshots import collect_snapshot, freeze_snapshot, load_snapshot, SnapshotUnsupported
from test_build_steps import setup, enable
from test_studio import scripted


def test_prompt_omissions_do_not_truncate_verification(tmp_path):
    ws=setup(tmp_path);enable(ws)
    tests=tmp_path/'tests';tests.mkdir()
    (tests/'__init__.py').write_text('')
    # Too large for the model packet, but still a required local regression.
    (tests/'test_large.py').write_text('# filler\n'*5000+'import unittest\nclass Regression(unittest.TestCase):\n    def test_existing(self): self.fail("omitted regression must still run")\n')
    draft=draft_files(ws,ws.router())
    assert 'tests/test_large.py' in source_context(ws)['omitted']
    result=verify_draft(ws,draft)
    assert result['status']=='failed'
    assert 'omitted regression must still run' in result['project_checks']['output']
    assert result['project_checks']['failure_details'][0]['test'].endswith('Regression.test_existing')
    assert 'omitted regression must still run' in result['project_checks']['failure_details'][0]['trace_tail']
    assert result['verification_input_files']==4


@pytest.mark.parametrize('change',['edit','add','delete'])
def test_unseen_file_changes_invalidate_verification(tmp_path,change):
    ws=setup(tmp_path);enable(ws)
    path=tmp_path/'unseen.py';path.write_text('# filler\n'*5000)
    draft=draft_files(ws,ws.router())
    assert 'unseen.py' not in draft['shown_files']
    if change=='edit':path.write_text('# changed\n'*5000)
    elif change=='add':(tmp_path/'extra.py').write_text('x=1\n')
    else:path.unlink()
    assert verify_draft(ws,draft)['status']=='stale'


def test_unseen_change_during_checks_blocks_promotion(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    unseen=tmp_path/'unseen.py';unseen.write_text('# filler\n'*5000)
    count=[0]
    def checkpoint():
        count[0]+=1
        if count[0]==3:unseen.write_text('# changed after checking\n'*5000)
    result=build_step(ws,ws.router(),checkpoint=checkpoint)
    assert result['verification']['status']=='acceptance_passed'
    assert not result.get('advanced') and not (tmp_path/'app.py').exists()


def test_overlay_and_apply_preserve_bom_crlf_and_binary_fixture(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    path=tmp_path/'app.py'
    path.write_bytes(b'\xef\xbb\xbfdef answer():\r\n    return 0\r\n')
    fixture=tmp_path/'tests/fixtures/image.bin';fixture.parent.mkdir(parents=True)
    binary=b'\x00\xff\x10 synthetic fixture';fixture.write_bytes(binary)
    result=build_step(ws,ws.router())
    assert result.get('advanced') is True
    assert path.read_bytes()==b'\xef\xbb\xbfdef answer():\r\n    return 42\r\n'
    assert fixture.read_bytes()==binary
    snapshot=load_snapshot(ws,ws._draft(result['draft'])['snapshot_digest'])
    assert snapshot['files']['tests/fixtures/image.bin']==binary
    assert 'tests/fixtures/image.bin' not in source_context(ws)['files']


def test_snapshot_excludes_live_data_and_keeps_clock_source(tmp_path):
    ws=setup(tmp_path)
    (tmp_path/'clock.py').write_text('x=1\n')
    (tmp_path/'.env').write_text('SECRET=not-for-a-model')
    (tmp_path/'credentials.json').write_text('{"private":"not-for-a-model"}')
    var=tmp_path/'var';var.mkdir();(var/'customers.json').write_text('{"name":"not-for-a-model"}')
    fixture=tmp_path/'tests/fixtures/example.json';fixture.parent.mkdir(parents=True)
    fixture.write_text('{"synthetic":"local-only-example"}')
    snapshot=collect_snapshot(ws);freeze_snapshot(ws,snapshot)
    assert set(snapshot['files'])=={'clock.py','tests/fixtures/example.json'}
    context=source_context(ws,snapshot=snapshot)
    assert 'clock.py' in context['files']
    assert 'local-only-example' not in json.dumps(context)
    assert 'not-for-a-model' not in json.dumps(context)


def test_unseen_replacement_is_still_refused_with_full_local_snapshot(tmp_path):
    ws=setup(tmp_path)
    (tmp_path/'large.py').write_text('# filler\n'*5000)
    scripted(ws,[{'title':'blind edit','files':[{'path':'large.py','content':'x=2\n'}]}],roles=('plan',))
    with pytest.raises(PlannerUnavailable,match='unseen'):draft_files(ws,ws.router())


def test_byte_hash_prevents_line_ending_race(tmp_path):
    ws=setup(tmp_path)
    (tmp_path/'app.py').write_bytes(b'def answer():\n    return 0\n')
    draft=draft_files(ws,ws.router())
    original=(tmp_path/'app.py').read_bytes()
    assert draft['files'][0]['expected_sha256']==hashlib.sha256(original).hexdigest()
    (tmp_path/'app.py').write_bytes(original.replace(b'\n',b'\r\n'))
    assert not ws.apply_draft(draft['id'],overwrite=True)['ok']


def test_snapshot_resource_failure_precedes_model_call(tmp_path,monkeypatch):
    import runesmith.app.snapshots as snapshots
    ws=setup(tmp_path);(tmp_path/'app.py').write_text('x=1')
    monkeypatch.setattr(snapshots,'MAX_FILE_BYTES',1)
    class NoCall:
        def call(self,*args,**kwargs):pytest.fail('no model spend before snapshot qualification')
    with pytest.raises(SnapshotUnsupported):draft_files(ws,NoCall())


def test_retained_author_view_survives_a_smaller_current_packet_budget(tmp_path, monkeypatch):
    import runesmith.app.building as building
    ws = setup(tmp_path, acceptance=True); enable(ws)
    (tmp_path / 'context.py').write_text('context = "original author input"\n')
    draft = draft_files(ws, ws.router())
    original_digest = draft['context_digest']
    real = source_context
    monkeypatch.setattr(building, 'source_context', lambda ws, **kw: real(ws, limit=0, **kw))
    result = verify_draft(ws, draft)
    assert result['status'] == 'acceptance_passed'
    assert result['project_checks']['ran'] == result['acceptance']['ran'] == 1
    assert result['author_context']['binding'] == 'frozen_shown_files'
    assert result['author_context']['current_packet_differs']
    assert draft['context_digest'] == original_digest


@pytest.mark.parametrize('tamper', ['digest', 'missing_name', 'duplicate', 'local_only', 'wrong_type'])
def test_invalid_retained_author_view_is_not_admitted_to_checks(tmp_path, monkeypatch, tamper):
    import runesmith.app.building as building
    ws = setup(tmp_path); enable(ws)
    (tmp_path / 'context.py').write_text('context=1\n')
    fixture = tmp_path / 'tests/fixtures/hidden.json'; fixture.parent.mkdir(parents=True)
    fixture.write_text('{"local_only":true}')
    draft = draft_files(ws, ws.router())
    if tamper == 'digest':draft['context_digest'] = '0' * 64
    if tamper == 'missing_name':draft['shown_files'] = ['not_present.py']
    if tamper == 'duplicate':draft['shown_files'] *= 2
    if tamper == 'local_only':draft['shown_files'] = ['tests/fixtures/hidden.json']
    if tamper == 'wrong_type':draft['shown_files'] = {'context.py': True}
    def forbidden(*args, **kwargs):raise AssertionError('Invalid context must not execute')
    monkeypatch.setattr(building, '_run_checks', forbidden)
    assert verify_draft(ws, draft)['status'] == 'stale'


def test_smaller_packet_policy_does_not_allow_hidden_source_changes(tmp_path, monkeypatch):
    import runesmith.app.building as building
    ws = setup(tmp_path); enable(ws)
    path = tmp_path / 'unseen.py'; path.write_text('# filler\n' * 5000)
    draft = draft_files(ws, ws.router())
    monkeypatch.setattr(building, 'source_context', lambda ws, **kw: source_context(ws, limit=0, **kw))
    path.write_text('# changed\n' * 5000)
    assert verify_draft(ws, draft)['status'] == 'stale'


def test_work_exposes_read_only_author_identity_without_rewriting_stale_verdict(tmp_path, monkeypatch):
    from pathlib import Path
    import runesmith.app.building as building
    from runesmith.app.workspace import _write_json
    ws = setup(tmp_path); enable(ws)
    (tmp_path / 'context.py').write_text('context=1\n')
    draft = draft_files(ws, ws.router())
    draft['verification'] = {'status': 'stale', 'detail': 'Historical preflight result'}
    path = ws.home / 'drafts' / draft['id'] / 'DRAFT.json'
    _write_json(path, draft)
    before = path.read_bytes()
    monkeypatch.setattr(building, 'source_context', lambda ws, **kw: source_context(ws, limit=0, **kw))
    def forbidden(*args, **kwargs):raise AssertionError('A read-only view must not execute checks')
    monkeypatch.setattr(building, '_run_checks', forbidden)
    view = next(d for d in ws.work()['drafts'] if d['id'] == draft['id'])
    diagnostic = view['author_context_preflight']
    assert diagnostic['ok'] and diagnostic['diagnostic_only'] and diagnostic['full_snapshot_current']
    assert diagnostic['current_packet_differs']
    assert view['verification']['status'] == 'stale'
    assert path.read_bytes() == before
    ui = (Path(__file__).parents[1] / 'runesmith/app/static/js/views/work.js').read_text(encoding='utf-8')
    assert 'd.author_context_preflight' in ui and 'diagnostic only' in ui


@pytest.mark.parametrize('change', ['source', 'context_digest', 'missing_snapshot'])
def test_author_identity_diagnostic_refuses_invalid_inputs(tmp_path, change):
    from runesmith.app.building import author_context_preflight
    ws = setup(tmp_path)
    (tmp_path / 'context.py').write_text('context=1\n')
    draft = draft_files(ws, ws.router())
    if change == 'source':(tmp_path / 'context.py').write_text('context=2\n')
    if change == 'context_digest':draft['context_digest'] = '0' * 64
    if change == 'missing_snapshot':draft['snapshot_digest'] = None
    diagnostic = author_context_preflight(ws, draft)
    assert not diagnostic['ok'] and diagnostic['diagnostic_only']
