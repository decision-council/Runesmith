import importlib
import json
from pathlib import Path

import pytest

from runesmith.app.planner import draft_files
from runesmith.app.revision_context import candidate_identity
from test_build_steps import setup, enable


def test_field_wrapper_completes_real_tiny_phases_and_keeps_old_record(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'training'))
    trial=importlib.import_module('support_m6_public_interface_20260927')
    ws=setup(tmp_path,acceptance=True);enable(ws)
    ws.save_plan({'summary':'Tiny wrapper qualification','milestones':[{'id':'m6','title':'Answer','done_when':'answer() returns 42'}]})
    (ws.home/'acceptance/m1.py').rename(ws.home/'acceptance/m6.py')
    draft=draft_files(ws,ws.router(),'m6')
    calls=[]
    monkeypatch.setattr(trial,'checkpoint',lambda *args:calls.append('checkpoint'))
    old=ws.home/'trainer-trials/original.json';old.parent.mkdir();old.write_text('{"state":"check_started"}')
    path=old.with_name('new-explicit-allocation.json')
    record={'state':'admitted','draft':draft['id'],'candidate_digest':candidate_identity(draft),'protected_sha256':{str(old):trial.sha(old)}}
    trial.check(ws,record,record_path=path)
    checked=json.loads(path.read_text())
    assert checked['state']=='checked'
    assert checked['check_result']['verification']['status']=='acceptance_passed'
    assert checked['check_result']['verification']['project_checks']['ran']==1
    assert checked['check_result']['verification']['acceptance']['ran']==1
    assert len(calls)>=5  # initial, before verification, before both phases, after recording
    assert not (tmp_path/'app.py').exists()
    assert old.read_text()=='{"state":"check_started"}'
    with pytest.raises(RuntimeError,match='consumed'):
        trial.check(ws,checked,record_path=path)
    trial.apply(ws,checked,record_path=path)
    assert json.loads(path.read_text())['state']=='applied'
    assert ws.plan()['milestones'][0]['status']=='done'
    assert old.read_text()=='{"state":"check_started"}'


def test_postguard_author_rejects_any_transport_identity_or_unknown_receipt(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'training'))
    trial=importlib.import_module('support_m6_post_guard_20260927')
    old={'state':'refused_or_unresolved','calls':[],'error':'JSONDecodeError: Extra data: example'}
    supplement={'state':'failed','id':'scc1d47957233','error':'Extra data: line 531 column 1 (char 41558)'}
    trial.validate_no_dispatch(old,supplement,[])
    for requests in ([None],[{'body':{'idempotency_key':trial.UNSENT_KEY},'state':'terminal'}]):
        with pytest.raises(RuntimeError,match='transport receipt'):
            trial.validate_no_dispatch(old,supplement,requests)
    for changed in (dict(old,request_key='possibly-sent'),dict(old,remote_receipt={'job_id':'possibly-sent'}),
                    dict(old,calls=[{'ok':False}])):
        with pytest.raises(RuntimeError,match='pre-submission'):
            trial.validate_no_dispatch(changed,supplement,[])
