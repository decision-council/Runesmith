"""Trainer commissioning: prospective contract, one ordinary author-only step.

Not Hat implementation. Keep all receipts; a rerun cannot buy another call.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app import building
from runesmith.app.acceptance_contracts import expectation_digest, publish_expectations
from runesmith.app.author_recovery import pending_authors
from runesmith.app.build_jobs import BuildJob, run_synchronous_build_job
from runesmith.app.planner import draft_prompt, milestone_contract, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.source_focus import save_focus
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _read_json, _write_json, _now

ROOT=Path(__file__).resolve().parent/'SupportHat'
HOME=ROOT/'.runesmith'
RECORD=HOME/'trainer-trials/json-input-m7-20260927.json'
SOURCE='4a93c8e6050949db9f7c645d652fccff88653a6f1e32a1a9a7558c4eda01a523'
CRITERIA=[
 {'id':'json.invocation','description':'Add global --input-json PATH, with - for stdin, while keeping --db and --json global flags. Read one UTF-8 JSON object {"command":"COMMAND","args":{...}}; args may be omitted for commands with no required arguments. JSON supplies the command and its arguments; reject combining it with a CLI subcommand or command arguments. --db and --json come only from CLI, never the JSON object. Example: python -m supporthat --db cases.db --json --input-json request.json. No shell evaluation or extra execution.'},
 {'id':'json.arguments','description':'Cover all 18 existing subcommands. args keys are existing argparse destination names: create-case subject/description/priority/source/assignee; list-cases status/assignee/limit; show-case id; update-case id/status/priority/assignee/subject; triage id/priority/assignee/note/by; transition id/to/note/by; history id; add-note id/content/author; notes id; ingest-docs directory; list-sources none; search query (nonempty array of strings); draft-response id/query (query is string); list-drafts id; record-handoff case_id; record-feedback case_id/rating; list-feedback case_id; metrics-summary none. Preserve required fields, defaults and existing enum choices. Integer fields must be JSON integers, not bools, floats or numeric strings. All other scalar arguments must be strings, not null; search query is the only array. Treat text beginning with - as literal argument data, not as another option.'},
 {'id':'json.validation','description':'Before opening/creating the SQLite database, reject malformed JSON, duplicate keys, non-finite JSON numbers, unknown top-level/command/argument keys, missing required args, wrong types, invalid enum choices, mixed CLI/JSON commands, missing/unreadable/non-UTF8 input, and input exceeding 1 MiB (1048576 UTF-8 bytes) from file or stdin. Fail nonzero with a useful stderr message rather than an uncaught traceback. No partial mutation for a rejected input. Existing domain-level checks (case existence, rating range, transitions) remain unchanged; do not bypass them.'},
 {'id':'json.output','description':'--json still returns parseable JSON for successful calls to every command, with existing output shapes, including m6 case_id/handoffs. Omitting --json still gives the existing human-readable default. All ordinary CLI invocations, flags, status compatibility, command behavior and project tests must keep working; JSON mode is additive, not a replacement.'},
 {'id':'json.local','description':'Stay local and stdlib-only. No sending messages, network, hosted services or subprocess execution from input. Preserve all accepted m1-m6 behavior and previous files/tests. Do not alter existing documentation, the private home or owner acceptance. Add implementation in supporthat/ and new runnable unittest tests in tests/test_json_input.py. Include file+stdin input, representative read and write commands, invalid/no-write cases and legacy compatibility. Do not replace or weaken existing tests.'},
]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def check_idle(ws, record=None):
    if (_existing(HOME) or (HOME/'STUDIO_CURRENT.json').exists() or pending_authors(ws) or ws.manual_waiting()
            or ws.settings()['auto_work'] or ws.settings()['kaizen'] or ws.settings()['autonomy']!='propose'):
        raise RuntimeError('Home is no longer the reviewed idle, single-writer state')
    if collect_snapshot(ws)['digest']!=SOURCE: raise RuntimeError('Source changed')
    if record:
        if any(not Path(p).is_file() or sha(Path(p))!=value for p,value in record['protected_sha256'].items()):
            raise RuntimeError('Protected record changed')
        if expectation_digest(ws,'m7')!=record['public_digest']:raise RuntimeError('Contract changed')
        if sha(HOME/'acceptance/m7.py')!=record['owner_fixture_sha256']:raise RuntimeError('Owner fixture changed')
        if sha(HOME/'runesmith.json')!=record['config_sha256']:raise RuntimeError('Configuration changed')

def prepare(ws):
    if RECORD.exists():raise RuntimeError('Preparation exists; inspect instead of recreating')
    check_idle(ws)
    if expectation_digest(ws,'m7') is not None:raise RuntimeError('m7 contract already exists')
    if any(d.get('milestone')=='m7' for d in ws.drafts()):raise RuntimeError('m7 already has a draft')
    protected=[]
    for folder in ('build-attempts','build-check-resumes','build-check-allocations','build-check-reconciliations','build-supplements','build-escalations'):
        protected.extend((HOME/folder).glob('*.json'))
    protected.extend((HOME/'build-runs').glob('*/v-*/VERIFICATION.json'))
    protected.extend((HOME/'acceptance').glob('*.py'))
    protected.extend((HOME/'drafts').glob('*/DRAFT.json'))
    protected.extend([HOME/'PLAN.json',HOME/'BUILD_GRANT.json'])
    record={'state':'preparing','utc':_now(),'source':SOURCE,
        'protected_sha256':{str(p):sha(p) for p in protected if p.is_file()},
        'owner_fixture_sha256':sha(HOME/'acceptance/m7.py'),
        'author_limit':'One ordinary build job, author_only=true, no host retries; existing ordinary cap unchanged.',
        'stop_rule':'One returned/refused/unresolved result. No executable checks, apply or next milestone in this allocation. Recover unknown job only; never repeat POST.',
        'trainer_assistance':'Prospective public interface, private acceptance, source focus and free author choice by external trainer. Instrument must author all Hat implementation/project tests.',
        'scope':'Operational field development, not scientific confirmation or autonomous targeting.',
        'old_plan_role':ws.config()['roles'].get('plan',[])}
    _write_json(RECORD,record)
    public=publish_expectations(ws,'m7',CRITERIA,'Prospective JSON-input contract before any m7 author or candidate scoring. Existing JSON output is not new work.',by='external-trainer',expected_digest=None)
    save_focus(ws,['supporthat/cli.py','supporthat/db.py','supporthat/metrics.py','tests/test_cases.py'],SOURCE,
               'Complete command interface, database validation, accepted metrics and representative tests for additive JSON input.')
    config=ws.config();spec=config['instruments']['free-author']
    if [spec['model']]+spec.get('fallback_models',[])!=['gemini:gemini-3.1-flash-lite-preview','gemini3:gemini-3.1-flash-lite','gemini2:gemini-3.1-flash-lite']:
        raise RuntimeError('Reviewed configured free route changed')
    config['roles']['plan']=['free-author'];ws.save_config(config)
    ws.ledger.append('trainer.plan_author_selected',{'instrument':'free-author','prior_role':record['old_plan_role'],'reason':'One m7 author-only step; restore role after terminal result.'})
    m=next(m for m in ws.plan()['milestones'] if m['id']=='m7');context=source_context(ws)
    prompt=draft_prompt(ws,m,context)
    if context.get('focus_errors'):
        raise RuntimeError('Invalid focused packet')
    packet,_=json.JSONDecoder().raw_decode(prompt)
    if packet['public_acceptance']['criteria']!=CRITERIA or len(prompt.encode())>90000:
        raise RuntimeError('Complete public contract missing or packet too large')
    record.update(state='prepared',public_digest=public['digest'],contract=milestone_contract(ws,m),
        config_sha256=sha(HOME/'runesmith.json'),preview_bytes=len(prompt.encode()),
        preview_sha256=hashlib.sha256(prompt.encode()).hexdigest(),source_files=list(context['files']),
        configured_instrument='free-author',configured_routes=[spec['model']]+spec.get('fallback_models',[]))
    _write_json(RECORD,record);check_idle(ws,record)
    ws.ledger.append('trainer.m7_prepared',{k:v for k,v in record.items() if k!='protected_sha256'})

def locked(function):
    lock=InstanceLock(HOME)
    if not lock.acquire():raise RuntimeError('Home has another writer; use resident API')
    try:
        if _existing(HOME):raise RuntimeError('Use resident Studio API')
        return function(Workspace(ROOT,HOME))
    finally:
        if lock.handle:lock.handle.close()

def author():
    def reserve(ws):
        record=_read_json(RECORD,{})
        if record.get('state')!='prepared':raise RuntimeError('Allocation already consumed or unprepared')
        check_idle(ws,record)
        record.update(state='author_reserved',started=_now(),before_requests=[p.name for p in (HOME/'inference-requests').glob('*.json')])
        _write_json(RECORD,record)
        return record
    record=locked(reserve)
    result=run_synchronous_build_job(ROOT,BuildJob('build',{'author_only':True}),home=HOME)
    def finish(ws):
        new=[_read_json(p,{}) for p in (HOME/'inference-requests').glob('*.json') if p.name not in record['before_requests']]
        record.update(state='finished',finished=_now(),job=result,new_requests=[{'id':r.get('id'),'state':r.get('state'),'job_id':r.get('job_id'),'instrument':r.get('instrument')} for r in new])
        cfg=ws.config()
        if not pending_authors(ws) and sha(HOME/'runesmith.json')==record['config_sha256'] and cfg['roles'].get('plan')==['free-author']:
            cfg['roles']['plan']=record['old_plan_role'];ws.save_config(cfg);record['plan_role_restored']=True
            ws.ledger.append('trainer.plan_author_restored',{'role':record['old_plan_role'],'no_pending_author':True})
        else:record['plan_role_restored']=False
        record['source_unchanged']=collect_snapshot(ws)['digest']==SOURCE
        record['protected_unchanged']=all(Path(p).is_file() and sha(Path(p))==v for p,v in record['protected_sha256'].items())
        _write_json(RECORD,record)
        print(json.dumps({k:v for k,v in record.items() if k not in ('protected_sha256','before_requests')}),flush=True)
    locked(finish)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','author']);args=parser.parse_args()
    if args.action=='prepare':
        locked(prepare);print(json.dumps({'state':'prepared','record':str(RECORD)}))
    else:author()
