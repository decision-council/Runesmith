"""One journaled free Pixel Canary author draft; no project checks or apply here."""
from pathlib import Path
import json
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import publish_expectations, expectations
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from runesmith.config import build_instrument
from runesmith.instruments import Router

ROOT = Path(__file__).resolve().parent/'GrowthHat'
CRITERIA = [
    {'id':'recommendation.create','description':'Preserve existing behavior. Add CLI recommendation add with --title, --action, --reasoning, --outcome-id and --uncertainty-level low|medium|high. Persist through Repository/Recommendation. Derive hypothesis_id from the outcome→test link; do not invent evidence.'},
    {'id':'recommendation.export','description':'Provide growthhat.exporting.export_recommendations(repo) returning {schema:"growthhat.recommendations.v1",recommendations:[{recommendation,outcome,test,hypothesis,sources,missing_links}]}. Use complete entity dictionaries (EvidenceType serialized to its string value); resolve outcome→test→hypothesis→source plus additional valid recommendation.source_ids. CLI export recommendations --output PATH writes this UTF-8 JSON. Include every stored recommendation exactly once; export must not mutate entity records.'},
    {'id':'recommendation.values','description':'Preserve exact IDs, source names, actions, uncertainty levels and evidence labels. Preserve negative outcome supports_hypothesis=false and confidence=0 as those values, separately from unknown null. Do not promote assumptions into measurements.'},
    {'id':'recommendation.gaps','description':'Legacy recommendations may lack links. Export absent outcome/test/hypothesis as null, absent sources as [], and explicit nonempty missing_links for unresolved provenance. Fully connected chains have missing_links=[]. Never fabricate missing records or call an incomplete chain complete.'},
    {'id':'recommendation.validation','description':'CLI recommendation creation rejects unknown outcome IDs, invalid uncertainty levels, and empty required text before storing anything. Preserve existing records and commands; use only local data.'},
    {'id':'recommendation.schema','description':'Expose a JSON-Schema dictionary EXPORT_SCHEMA in growthhat.exporting. Root type object requires schema and recommendations; schema has const growthhat.recommendations.v1; recommendations is array with items requiring recommendation,outcome,test,hypothesis,sources,missing_links. Document remaining field types and nullability in this schema and add executable tests. Empty export is {schema:"growthhat.recommendations.v1",recommendations:[]}. Do not edit existing documentation.'},
    {'id':'recommendation.local','description':'No network, model calls, dispatch or real-person records. Work only in growthhat/ and tests/. CLI export refuses an existing output path without overwriting its contents; report nonzero exit on refusal. No changes to .runesmith or owner acceptance.'},
]


def main():
    home=ROOT/'.runesmith'
    if _existing(home):
        raise RuntimeError('Resident Studio found; use its queue, not this direct writer')
    lock=InstanceLock(home)
    if not lock.acquire():
        raise RuntimeError('Home already has a writer')
    try:
        ws=Workspace(ROOT,home)
        receipt_path=home/'trainer-trials'/'cline-pixel-m5-20260926.json'
        if receipt_path.exists():
            print(json.dumps({'existing_trial':_read_json(receipt_path,{}),'no_inference':True})); return
        if pending_authors(ws):
            raise RuntimeError('Reconcile pending author request first')
        if any(d.get('milestone')=='m5' and d.get('state') in ('waiting','applied') for d in ws.drafts()):
            raise RuntimeError('Existing m5 candidate; no duplicate authoring')
        if expectations(ws,'m5') or (home/'acceptance/m5.py').exists():
            raise RuntimeError('m5 already has expectations; review before replacing anything')
        before=source_context(ws)['snapshot_digest']
        fixture=Path(__file__).resolve().parent/'fixtures/growth_m5_acceptance.py'
        shutil.copyfile(fixture,home/'acceptance/m5.py')
        contract=publish_expectations(ws,'m5',CRITERIA,
            'Trainer operationalizes the existing model-authored m5 before its first author attempt; synthetic acceptance only.',
            by='external-trainer')
        old=ws.config()['instruments']['author']
        original=build_instrument('author',old,home)
        name='free-cline-pixel'
        ws.save_instrument(name,{'kind':'milliner','preset':'milliner','model':'cline:stealth/pixel-canary',
            'base_url':old['base_url'],'timeout_s':300,'fallback_models':[],
            'budget_tag':'runesmith-field-training','caller_tag':'runesmith/trainer/growth-m5-cline',
            'note':'Bounded free Pixel Canary author trial; no paid fallback and no primary role changes.'},
            key_value=original._token(),roles=[])
        instrument=build_instrument(name,ws.config()['instruments'][name],home)
        events=[]
        def record(event):
            events.append(event);ws.record_call(event)
        router=Router({name:instrument},{'plan':[name]},backoff_s=(),on_call=record)
        receipt={'state':'started','utc':_now(),'milestone':'m5','requested_model':instrument.model,
            'source_digest':before,'public_acceptance_digest':contract['digest'],
            'author_limit':1,'paid_fallback':False,'trainer_assistance':'public interface/acceptance and route setup'}
        _write_json(receipt_path,receipt)
        try:
            draft=draft_files(ws,router,'m5')
            receipt.update(state='admitted',draft=draft['id'],authored_by=draft.get('drafted_by'),
                paths=[f['path'] for f in draft['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved',error=type(error).__name__+': '+str(error)[:500],
                remote_receipt=getattr(error,'remote_receipt',{}))
        receipt.update(finished=_now(),calls=events,source_unchanged=source_context(ws)['snapshot_digest']==before)
        _write_json(receipt_path,receipt);ws.ledger.append('trainer.author_trial',receipt)
        print(json.dumps(receipt,ensure_ascii=True))
    finally:
        if lock.handle: lock.handle.close()


if __name__=='__main__':
    main()
