import json

import pytest

from runesmith.app.acceptance_contracts import publish_expectations, expectations, public_check_feedback
from runesmith.app.building import (build_step, escalate_build, readmit_escalation_answer,
                                    supplement_build, verify_draft)
from runesmith.app.planner import draft_files, draft_prompt
from test_build_steps import setup, enable
from test_studio import scripted


CRITERIA=[{'id':'answer.value','description':'The public answer function returns the required value.'}]


def test_contract_is_versioned_and_projected_without_assertions(tmp_path):
    ws=setup(tmp_path,acceptance=True)
    first=publish_expectations(ws,'m1',CRITERIA,'Make intended public behavior explicit',by='trainer')
    assert expectations(ws,'m1')==first
    packet=json.loads(draft_prompt(ws,ws.plan()['milestones'][0]))
    assert packet['public_acceptance']['criteria']==CRITERIA
    assert 'assertEqual' not in packet['public_acceptance']['criteria'][0]['description']
    second=publish_expectations(ws,'m1',CRITERIA,'Add provenance, no behavioral relaxation')
    assert second['version']==2 and second['digest']!=first['digest']
    assert json.loads((ws.home/'acceptance-contracts/history/m1/1.json').read_text())==first


def test_feedback_does_not_guess_or_expose_private_fixture(tmp_path):
    projected=public_check_feedback({'status':'failed','failure_details':[
        {'test':'private.test','trace_tail':'SECRET_FIXTURE assert x=123','criteria':['answer.value']},
        {'test':'other','trace_tail':'another secret'},
    ]},[{'criteria':CRITERIA}])
    text=json.dumps(projected)
    assert 'SECRET' not in text and 'private.test' not in text and 'another secret' not in text
    assert 'answer.value' in text and 'not localized' in text


def test_revision_invalidates_verification_not_spent_budget(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    scripted(ws,[{'title':'bad','files':[]}]*3,roles=('plan',))
    for _ in range(3):
        with pytest.raises(Exception):build_step(ws,ws.router())
    before={p.name:p.read_bytes() for p in (ws.home/'build-attempts').glob('*.json')}
    publish_expectations(ws,'m1',CRITERIA,'Clarify the acceptance contract')
    assert build_step(ws,ws.router()).get('replan_needed')
    assert before=={p.name:p.read_bytes() for p in (ws.home/'build-attempts').glob('*.json')}


def test_clarified_candidate_gets_one_explicit_supplement_and_no_reset(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    draft=draft_files(ws,ws.router())
    ws._save_draft_state(draft,'needs_revision',verification={'status':'failed'})
    publish_expectations(ws,'m1',CRITERIA,'Make the expected output public')
    assert verify_draft(ws,draft)['status']=='stale'
    # Only the declared public expectations change, not the private predicate.
    result=supplement_build(ws,ws.router(),draft['id'],'Owner grants one clarification revision')
    assert result['advanced']
    receipt=json.loads(next((ws.home/'build-supplements').glob('*.json')).read_text())
    assert receipt['state']=='answered' and receipt['candidate']==draft['id']
    assert result['verification']['public_contracts'][0]['criteria']==CRITERIA
    with pytest.raises(Exception,match='eligible'):
        supplement_build(ws,ws.router(),draft['id'],'No second call allowed')


def test_acceptance_runner_captures_declared_criterion_ids(tmp_path):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    publish_expectations(ws,'m1',CRITERIA,'Expose public behavior, keep fixtures private')
    (ws.home/'acceptance/m1.py').write_text(
        'import unittest\nfrom app import answer\nclass Acceptance(unittest.TestCase):\n'
        '    PUBLIC_CRITERIA={"test_contract":["answer.value"]}\n'
        '    def test_contract(self): self.assertEqual(answer(),99,"PRIVATE_LITERAL")\n')
    result=build_step(ws,ws.router())
    assert result['verification']['status']=='failed'
    assert result['verification']['acceptance']['failure_details'][0]['criteria']==['answer.value']
    packet=draft_prompt(ws,ws.plan()['milestones'][0])
    assert 'PRIVATE_LITERAL' not in packet and 'answer.value' in packet


def test_observe_mode_blocks_all_recovery_entry_points(tmp_path):
    ws=setup(tmp_path);ws.update_settings({'autonomy':'observe'})
    assert 'Observe mode' in escalate_build(ws,None)['summary']
    assert 'Observe mode' in readmit_escalation_answer(ws,'e123')['summary']
    assert 'Observe mode' in supplement_build(ws,None,'absent','reason')['summary']


def test_author_only_supplement_parks_without_checking_or_applying(tmp_path, monkeypatch):
    ws=setup(tmp_path,acceptance=True);enable(ws)
    draft=draft_files(ws,ws.router())
    ws._save_draft_state(draft,'needs_revision',verification={'status':'failed'})
    publish_expectations(ws,'m1',CRITERIA,'Public clarification')
    def forbidden(*args, **kwargs): raise AssertionError('Author-only cannot run checks')
    monkeypatch.setattr('runesmith.app.building._check_and_record',forbidden)
    result=supplement_build(ws,ws.router(),draft['id'],'Save answer first',author_only=True)
    assert result['author_only'] and not result['advanced']
    revised=ws._draft(result['draft'])
    assert revised['state']=='waiting' and not revised.get('verification')
    assert not (ws.root/'app.py').exists()
    assert ws.plan()['milestones'][0]['status']=='open'
    with pytest.raises(Exception,match='eligible'):
        supplement_build(ws,ws.router(),draft['id'],'Cannot replay',author_only=True)


def test_supplement_author_only_rejects_truthy_strings(tmp_path):
    from runesmith.app.workspace import WorkspaceError
    ws=setup(tmp_path)
    with pytest.raises(WorkspaceError,match='boolean'):
        supplement_build(ws,None,'absent','reason',author_only='false')
