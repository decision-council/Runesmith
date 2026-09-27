"""Offline route editing: credentials, receipt custody and no hidden test call."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runesmith.app.inference_routes import route_view, save_route
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from runesmith.app.server import api_instrument_route, api_instrument_route_save


def workspace(tmp_path):
    ws=Workspace(tmp_path)
    ws.save_instrument('author',{'kind':'milliner','model':'openrouter:paid','base_url':'http://gateway.test',
        'fallback_models':['gemini3:free'],'timeout_s':240,'budget_tag':'existing-budget','caller_tag':'existing-caller'},
        key_value='never-print-this-test-secret',roles=['plan','kaizen'])
    return ws


def change(ws, **overrides):
    data={'revision':route_view(ws,'author')['revision'],'model':'gemini3:free',
          'fallback_models':['gemini2:free'],'reason':'Paid credit low; explicit free preference'}
    data.update(overrides)
    return save_route(ws,'author',**data)


def test_change_preserves_all_non_route_fields_roles_keys_and_makes_no_call(tmp_path,monkeypatch):
    ws=workspace(tmp_path);before=ws.config();key_bytes=(ws.home/'secrets.json').read_bytes()
    monkeypatch.setattr(ws,'router',lambda **_:pytest.fail('No router creation'))
    monkeypatch.setattr(ws,'test_instrument',lambda *_:pytest.fail('No probe'))
    result=change(ws)
    after=ws.config()
    for key,value in before['instruments']['author'].items():
        if key not in ('model','fallback_models'):assert after['instruments']['author'][key]==value
    assert after['roles']==before['roles']
    assert (ws.home/'secrets.json').read_bytes()==key_bytes
    assert result['changed'] and result['inference_calls']==0
    assert 'never-print-this-test-secret' not in json.dumps(result)
    assert after['instruments']['author']['model']=='gemini3:free'
    assert not (ws.home/'OPERATIONS.json').exists()
    assert 'instrument.route_changed' in (ws.home/'ledger.jsonl').read_text()


def test_noop_does_not_rewrite_config_or_append_a_route_event(tmp_path):
    ws=workspace(tmp_path)
    change(ws)
    before={p:p.read_bytes() for p in (ws.home/'runesmith.json',ws.home/'ledger.jsonl')}
    assert not change(ws)['changed']
    assert all(p.read_bytes()==data for p,data in before.items())


def test_stale_tab_or_other_instrument_field_change_refuses(tmp_path):
    ws=workspace(tmp_path);view=route_view(ws,'author')
    config=ws.config();config['instruments']['author']['timeout_s']=300;ws.save_config(config)
    with pytest.raises(WorkspaceError,match='changed'):change(ws,revision=view['revision'])
    assert ws.config()['instruments']['author']['model']=='openrouter:paid'


@pytest.mark.parametrize('args', [dict(model=''),dict(model=4),dict(model='bad model'),dict(model='x'*301),
    dict(fallback_models='not-a-list'),dict(fallback_models=[None]),dict(fallback_models=['']),
    dict(fallback_models=['x']*6),dict(reason=''),dict(reason=None),dict(reason='x'*2001)])
def test_invalid_edits_leave_bytes_unchanged(tmp_path,args):
    ws=workspace(tmp_path);before=(ws.home/'runesmith.json').read_bytes()
    with pytest.raises(WorkspaceError):change(ws,**args)
    assert (ws.home/'runesmith.json').read_bytes()==before


def test_order_is_kept_and_duplicate_primary_is_removed(tmp_path):
    ws=workspace(tmp_path)
    result=change(ws,model=' gemini3:free ',fallback_models=['gemini3:free','gemini2:free','gemini2:free','gemini:free'])
    assert result['fallback_models']==['gemini2:free','gemini:free']


@pytest.mark.parametrize('state',['submitting','pending','binding_mismatch','unknown'])
def test_unresolved_requests_block_rerouting_without_rewriting_receipts(tmp_path,state):
    ws=workspace(tmp_path);path=ws.home/'inference-requests/ticket.json'
    _write_json(path,{'instrument':'author','state':state,'key':'repair-request'})
    before=path.read_bytes()
    with pytest.raises(WorkspaceError,match='unresolved'):change(ws)
    assert path.read_bytes()==before


def test_unadmitted_terminal_author_stays_pinned(tmp_path,monkeypatch):
    ws=workspace(tmp_path)
    monkeypatch.setattr('runesmith.app.inference_routes.pending_authors',lambda _:[{'instrument':'author'}])
    with pytest.raises(WorkspaceError,match='reconciliation'):change(ws)


def test_damaged_receipt_and_interrupted_worker_block_edits(tmp_path):
    ws=workspace(tmp_path);path=ws.home/'inference-requests/broken.json'
    path.parent.mkdir(exist_ok=True);path.write_text('{')
    with pytest.raises(WorkspaceError,match='unreadable'):change(ws)
    path.unlink()
    _write_json(ws.home/'STUDIO_CURRENT.json',{'kind':'build'})
    with pytest.raises(WorkspaceError,match='active or interrupted'):change(ws)


@pytest.mark.parametrize('value',[[],['bad'],42,{'state':'terminal','payload':['not-a-response']}])
def test_valid_json_but_invalid_receipt_shape_is_a_visible_blocker(tmp_path,value):
    ws=workspace(tmp_path);path=ws.home/'inference-requests/broken.json'
    _write_json(path,value)
    before=path.read_bytes()
    assert route_view(ws,'author')['blockers']
    with pytest.raises(WorkspaceError):change(ws)
    assert path.read_bytes()==before


def test_terminal_non_author_or_other_instrument_does_not_block(tmp_path):
    ws=workspace(tmp_path)
    _write_json(ws.home/'inference-requests/done.json',{'instrument':'author','state':'terminal','key':'repair-request','payload':{'state':'succeeded'}})
    _write_json(ws.home/'inference-requests/other.json',{'instrument':'other','state':'pending','key':'repair-other'})
    assert change(ws)['changed']


def test_actual_api_and_ui_no_secret_endpoint_budget_or_role_edit(tmp_path):
    ws=workspace(tmp_path);events=[]
    studio=SimpleNamespace(ws=ws,bus=SimpleNamespace(publish=lambda *a:events.append(a)))
    view=api_instrument_route(studio,{},None,'author')
    before=ws.config()
    result=api_instrument_route_save(studio,{},dict(revision=view['revision'],model='gemini3:free',
        fallback_models=[],reason='Explicit selection',key='do-not-save',base_url='https://other.test',
        roles=['repair'],budget_tag='override',timeout_s=999),'author')
    assert result['changed'] and events==[('inference',{})]
    after=ws.config()
    assert after['roles']==before['roles']
    for key in ('base_url','timeout_s','budget_tag','token_secret'):
        assert after['instruments']['author'][key]==before['instruments']['author'][key]
    ui=(Path(__file__).parents[1]/'runesmith/app/static/js/views/inference.js').read_text(encoding='utf-8')
    assert 'editMillinerRoute(i.name, reload)' in ui
    assert 'Save route without a test call' in ui and 'revision: route.revision' in ui


def test_missing_and_non_milliner_instruments_refuse(tmp_path):
    ws=workspace(tmp_path)
    with pytest.raises(KeyError):route_view(ws,'missing')
    ws.save_instrument('chat',{'kind':'manual','model':'manual'})
    with pytest.raises(WorkspaceError,match='Milliner'):route_view(ws,'chat')
