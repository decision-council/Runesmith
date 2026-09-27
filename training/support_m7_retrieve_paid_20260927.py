"""Retrieve only the existing m7 ticket; no code path submits another call."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runesmith.app.author_recovery import pending_authors
from runesmith.app.build_jobs import BuildJob,run_synchronous_build_job
from runesmith.app.inference_routes import route_view,save_route
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import _read_json,_write_json,_now
from support_m7_json_input_20260927 import HOME,ROOT,SOURCE,locked,sha
from support_m7_paid_author_20260927 import RECORD

REQUEST = 'b0cb4ea376de5e7881d7730d018365fc70c54cc14284c0cf4621627fae0e6ae3'


def assess(ws,job):
    original = _read_json(RECORD,{})
    request = _read_json(HOME/'inference-requests'/(REQUEST+'.json'),{})
    payload=request.get('payload') or {};meta=payload.get('meta') or {}
    terminal=request.get('state') in ('terminal','refused')
    restored=ws.config()==original['prior_config']
    if terminal and not pending_authors(ws) and sha(HOME/'runesmith.json')==original['config_sha256']:
        prior=original['prior_route'];current=route_view(ws,'paid-deepseek')
        save_route(ws,'paid-deepseek',revision=current['revision'],model=prior['model'],fallback_models=prior['fallback_models'],
            reason='Existing paid m7 ticket reconciled without a new generation; restore its prior route.')
        cfg=ws.config();cfg['roles']['plan']=original['prior_config']['roles']['plan'];ws.save_config(cfg)
        restored=ws.config()==original['prior_config']
    attempt_tokens=sum((a.get('tokens_in') or 0)+(a.get('tokens_out') or 0) for a in meta.get('attempts',[]))
    contradictory_zero=bool(terminal and attempt_tokens and meta.get('est_usd')==0)
    receipt={'utc':_now(),'job':job,'request_id':REQUEST,'gateway_job':request.get('job_id'),
        'remote_state':request.get('state'),'gateway_state':payload.get('state'),
        'model':meta.get('model'),'provider':meta.get('provider'),
        'estimated_usd':meta.get('est_usd') if terminal and not contradictory_zero else None,
        'reported_job_estimated_usd':meta.get('est_usd') if terminal else None,
        'contradictory_paid_job_zero':contradictory_zero,
        'reported_cost_field_present':bool(terminal and meta.get('est_usd') is not None),
        'cost_caution':'Gateway aggregate may omit failed-attempt costs. Field presence alone is not credible billing coverage; inspect attempts and account receipts.',
        'tokens_in':meta.get('tokens_in') if terminal else None,'tokens_out':meta.get('tokens_out') if terminal else None,
        'attempts':meta.get('attempts') if terminal else None,'configuration_restored':restored,
        'current_plan_role':ws.config()['roles'].get('plan'),
        'new_inference_calls':0,'source_unchanged':collect_snapshot(ws)['digest']==SOURCE,
        'protected_count':len(original['protected_sha256']),
        'protected_unchanged':all(Path(p).is_file() and sha(Path(p))==d for p,d in original['protected_sha256'].items()),
        'drafts':[{'id':d['id'],'state':d.get('state'),'author':d.get('drafted_by'),'verified':d.get('verified')}
                  for d in ws.drafts() if d.get('milestone')=='m7'],
        'scope':'Saved-ticket GET/admission only. No check, apply, new author dispatch or budget reset. Unknown spend is not zero.'}
    name='json-input-m7-paid-retrieval-'+receipt['utc'].replace(':','').replace('-','')+'.json'
    path=HOME/'trainer-trials'/name
    if path.exists():raise RuntimeError('Assessment path already exists; do not overwrite')
    _write_json(path,receipt)
    ws.ledger.append('trainer.m7_paid_ticket_retrieved',{'request_id':REQUEST,'receipt':path.relative_to(HOME).as_posix(),
        'state':receipt['remote_state'],'new_inference_calls':0,'estimated_usd':receipt['estimated_usd']})
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    job=run_synchronous_build_job(ROOT,BuildJob('resume_author',{'request_id':REQUEST}),home=HOME)
    locked(lambda ws:assess(ws,job))
