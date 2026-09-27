"""Recorded capacity is not current liveness, a spending grant or a retry."""
import json
import os
from types import SimpleNamespace

import pytest

from runesmith.app.inference_availability import availability_view
from runesmith.app.server import api_instrument_availability
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from runesmith.canon import digest

NOW = 1790478000.0


def workspace(tmp_path):
    ws = Workspace(tmp_path)
    ws.save_instrument('author', {'kind':'milliner', 'model':'gemini:small',
        'base_url':'http://gateway.test', 'fallback_models':['gemini2:small','openrouter:paid'],
        'caller_tag':'test-caller'}, key_value='SECRET-DO-NOT-RETURN', roles=['plan'])
    return ws


def save(ws, name='one', *, observed=NOW-60, attempts=None, **overrides):
    payload = {'state':'failed', 'finished_at':observed, 'text':'PRIVATE-REPLY', 'error':'SECRET-ERROR',
        'meta':{'attempts':attempts if attempts is not None else [{'provider':'gemini', 'model':'small',
            'outcome':'rate_limited', 'retry_after_s':3600, 'error':'SECRET-ERROR'}]}}
    body = {'prompt':'PRIVATE-PROMPT'}
    record = {'instrument':'author','origin':'http://gateway.test','caller':'test-caller',
        'state':'terminal','job_id':'mj_test','payload':payload,'payload_digest':digest(payload),
        'body':body,'body_digest':digest(body),'created':'2026-09-27T02:59:00Z'}
    record.update(overrides)
    path = ws.home/'inference-requests'/(name+'.json')
    _write_json(path,record)
    return path, record


def test_unknown_is_not_available_and_view_has_no_writes_calls_or_secret_access(tmp_path,monkeypatch):
    ws=workspace(tmp_path)
    monkeypatch.setattr(ws,'router',lambda **_:pytest.fail('No router'))
    monkeypatch.setattr(ws,'test_instrument',lambda *_:pytest.fail('No probe'))
    before={p:p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    result=availability_view(ws,'author',now=NOW)
    assert [r['status'] for r in result['routes']]==['unknown']*3
    assert result['inference_calls']==0 and result['coverage']['scanned']==0
    assert before=={p:p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    assert 'SECRET' not in json.dumps(result)


def test_cooldown_is_anchored_to_gateway_completion_not_view_time(tmp_path):
    ws=workspace(tmp_path);save(ws)
    first=availability_view(ws,'author',now=NOW)
    later=availability_view(ws,'author',now=NOW+30)
    row=first['routes'][0]
    assert row['status']=='cooldown_recorded' and row['remaining_s']==3540
    assert row['retry_at']==later['routes'][0]['retry_at']
    assert later['routes'][0]['remaining_s']==3510
    assert all(x not in json.dumps(first) for x in ('SECRET','PRIVATE','gateway.test'))
    assert first['coverage']=={'scanned':1,'matching':1,'omitted':0,'unreadable':0}


def test_expired_wait_does_not_turn_into_available(tmp_path):
    ws=workspace(tmp_path);save(ws,observed=NOW-5000)
    row=availability_view(ws,'author',now=NOW)['routes'][0]
    assert row['status']=='cooldown_elapsed' and row['remaining_s']==0
    assert 'has not been rechecked' in row['detail']


def test_later_success_overrides_old_limit_but_does_not_prove_quality(tmp_path):
    ws=workspace(tmp_path);old,_=save(ws,'old',observed=NOW-100)
    save(ws,'new',observed=NOW-20,attempts=[{'provider':'gemini','model':'small','outcome':'ok','retry_after_s':500}])
    os.utime(old,(NOW+100,NOW+100))
    row=availability_view(ws,'author',now=NOW)['routes'][0]
    assert row['status']=='past_success' and row['retry_at'] is None
    assert 'unverified' in row['detail']


@pytest.mark.parametrize('retry',[None,True,-1,'3600',float('inf'),float('nan'),31_536_001])
def test_bad_retry_values_do_not_manufacture_a_wait(tmp_path,retry):
    ws=workspace(tmp_path)
    if isinstance(retry,float) and not __import__('math').isfinite(retry):
        # Invalid legacy JSON should be a coverage warning, not an API crash.
        path,record=save(ws)
        record['payload']['meta']['attempts'][0]['retry_after_s']=retry
        _write_json(path,record)
        result=availability_view(ws,'author',now=NOW)
        assert result['coverage']['unreadable']==1
    else:
        save(ws,attempts=[{'provider':'gemini','model':'small','outcome':'overloaded','retry_after_s':retry}])
        row=availability_view(ws,'author',now=NOW)['routes'][0]
        assert row['status']=='capacity_failure' and row['retry_at'] is None


@pytest.mark.parametrize('field,value',[('origin','http://old.test'),('caller','other-caller'),('instrument','worker')])
def test_other_gateway_identity_or_instrument_does_not_become_current_evidence(tmp_path,field,value):
    ws=workspace(tmp_path);save(ws,**{field:value})
    result=availability_view(ws,'author',now=NOW)
    assert result['coverage']['matching']==0 and result['routes'][0]['status']=='unknown'


@pytest.mark.parametrize('state',['submitting','pending','remote_outcome_unknown','binding_mismatch'])
def test_uncertain_request_is_not_retried_or_misread_as_terminal(tmp_path,state):
    ws=workspace(tmp_path);save(ws,state=state)
    result=availability_view(ws,'author',now=NOW)
    assert result['unresolved_requests']==1 and result['routes'][0]['status']=='unknown'


@pytest.mark.parametrize('field',['body','payload'])
def test_changed_custody_bytes_are_not_displayed_as_evidence(tmp_path,field):
    ws=workspace(tmp_path);path,record=save(ws)
    record[field]['extra']='changed';_write_json(path,record)
    result=availability_view(ws,'author',now=NOW)
    assert result['coverage']['unreadable']==1 and result['routes'][0]['status']=='unknown'


def test_scan_window_is_disclosed_and_limits_large_or_invalid_receipts(tmp_path,monkeypatch):
    ws=workspace(tmp_path)
    import runesmith.app.inference_availability as module
    monkeypatch.setattr(module,'MAX_RECEIPTS',3)
    monkeypatch.setattr(module,'MAX_RECEIPT_BYTES',2000)
    for index in range(5):
        path,_=save(ws,str(index));os.utime(path,(NOW+index,NOW+index))
    path=ws.home/'inference-requests/4.json';path.write_text(' '*2001);os.utime(path,(NOW+4,NOW+4))
    path=ws.home/'inference-requests/3.json';path.write_text('[]');os.utime(path,(NOW+3,NOW+3))
    result=availability_view(ws,'author',now=NOW)
    assert result['coverage']=={'scanned':3,'matching':1,'omitted':2,'unreadable':2}


@pytest.mark.parametrize('stamp',[True,'not-a-date',NOW+100,None])
def test_bad_time_never_claims_a_current_wait_without_an_anchor(tmp_path,stamp):
    ws=workspace(tmp_path);path,record=save(ws,observed=stamp,created='not-a-date')
    result=availability_view(ws,'author',now=NOW)
    assert result['coverage']['unreadable']==1 and result['routes'][0]['status']=='unknown'


def test_actual_api_separates_configured_chain_outcomes_and_raw_error_strings(tmp_path):
    ws=workspace(tmp_path);save(ws,attempts=[
        {'provider':'gemini','model':'small','outcome':'rate_limited','retry_after_s':400},
        {'provider':'gemini2','model':'small','outcome':'overloaded','retry_after_s':20},
        {'provider':'openrouter','model':'paid','outcome':'no_credits','error':'Bearer SECRET'},
        {'provider':'other','model':'unused','outcome':'ok'}])
    result=api_instrument_availability(SimpleNamespace(ws=ws),{},None,'author')
    assert len(result['routes'])==3 and result['routes'][2]['status']=='route_refused'
    assert result['routes'][2]['outcome']=='no_credits' and 'SECRET' not in json.dumps(result)
    assert result['routes'][2]['gateway_attempts']==4
    assert result['inference_calls']==0


def test_missing_and_manual_instrument_refuse(tmp_path):
    ws=workspace(tmp_path)
    with pytest.raises(KeyError):availability_view(ws,'missing')
    ws.save_instrument('chat',{'kind':'manual','model':'copy-paste'})
    with pytest.raises(WorkspaceError,match='Milliner'):availability_view(ws,'chat')


def test_multiple_format_attempts_do_not_mean_multiple_host_jobs_or_free_failure(tmp_path):
    ws=workspace(tmp_path)
    save(ws,attempts=[{'provider':'openrouter','model':'paid','outcome':'truncated','tokens_out':12000} for _ in range(3)])
    result=availability_view(ws,'author',now=NOW)
    row=result['routes'][2]
    assert row['status']=='past_failure' and row['outcome']=='truncated' and row['gateway_attempts']==3
    assert row['job_id']=='mj_test' and row['retry_at'] is None
    assert 'not a spend ledger' in result['caution']
    assert 'estimated_usd' not in row
