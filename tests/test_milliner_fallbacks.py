import pytest

from runesmith.app.workspace import Workspace, WorkspaceError
from runesmith.config import build_instrument
from runesmith.instruments import MillinerInstrument, Router


def test_explicit_fallback_chain_keeps_actual_author_and_receipt(tmp_path):
    sent=[]
    def transport(method,url,headers,body,timeout):
        sent.append(body)
        return 200, {'state':'succeeded', 'provider':'gemini3', 'model':'free-model',
                     'job_id':'test-job', 'parsed':{'answer':42},
                     'meta':{'est_usd':0.0,'tokens_in':5,'tokens_out':3}}
    inst=MillinerInstrument('author','openrouter:paid-model',base_url='http://localhost:8765',
        token=lambda:'test-key',fallback_models=['openrouter:free-model:free','gemini3:free-model'],
        budget_tag='test-training',transport=transport)
    events=[]
    ws=Workspace(tmp_path)
    def record(event):
        events.append(event);ws.record_call(event)
    router=Router({'author':inst},{'plan':['author']},backoff_s=(),on_call=record)
    outcome=router.call('plan',prompt='test',system='test',schema=None,max_tokens=100,key='one')
    assert sent[0]['models']==['openrouter:paid-model','openrouter:free-model:free','gemini3:free-model']
    assert 'model' not in sent[0] and sent[0]['max_fallbacks']==2
    assert sent[0]['allow_fallback'] is True and sent[0]['budget_tag']=='test-training'
    assert outcome.receipt['model']=='gemini3:free-model'
    assert outcome.receipt['requested_model']=='openrouter:paid-model'
    assert events[0]['job_id']=='test-job' and events[0]['est_usd']==0.0
    text=(ws.home/'ledger.jsonl').read_text()
    assert 'requested_model' in text and 'gemini3:free-model' in text


def test_no_chain_preserves_single_pin():
    sent=[]
    def transport(method,url,headers,body,timeout):
        sent.append(body)
        return 200, {'state':'succeeded','parsed':{'answer':42}}
    inst=MillinerInstrument('author','provider:model',base_url='http://localhost:8765',
                           token=lambda:'test-key',transport=transport)
    inst.complete(prompt='test',system='test',schema=None,max_tokens=20,key='single')
    assert sent[0]['model']=='provider:model' and 'models' not in sent[0]


def test_workspace_persists_and_exposes_fallback_chain(tmp_path):
    ws=Workspace(tmp_path)
    saved=ws.save_instrument('author',{'kind':'milliner','base_url':'http://localhost:8765',
        'model':'openrouter:paid','fallback_models':['gemini3:free','gemini2:free']},
        key_value='test-key',roles=['plan'])
    assert saved['fallback_models']==['gemini3:free','gemini2:free']
    inst=build_instrument('author',ws.config()['instruments']['author'],home=ws.home)
    assert inst.fallback_models==saved['fallback_models']
    assert 'test-key' not in str(saved)


@pytest.mark.parametrize('models',['not-a-list',[''],[None],['m'+str(i) for i in range(6)]])
def test_invalid_chains_are_rejected(tmp_path,models):
    ws=Workspace(tmp_path)
    with pytest.raises(WorkspaceError):
        ws.save_instrument('author',{'kind':'milliner','base_url':'http://localhost:8765',
            'model':'primary','fallback_models':models})
    with pytest.raises(ValueError):
        MillinerInstrument('author','primary',base_url='http://localhost:8765',token=lambda:'test',
                           fallback_models=models)
