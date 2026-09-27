"""One named model-authored test on a frozen faulty candidate, not acceptance."""
from pathlib import Path
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.author_recovery import pending_authors
from runesmith.app.building import _candidate_files
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot, load_snapshot
from runesmith.app.workspace import Workspace, _read_json, _write_json, _now


def main():
    root=Path(__file__).resolve().parent/'GrowthHat';home=root/'.runesmith'
    if _existing(home):raise RuntimeError('Use the resident Studio queue')
    lock=InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Home has another writer')
    try:
        out=home/'trainer-trials/gemini-m5-tests-delivered-assessment-20260927.json'
        if out.exists():print(json.dumps({'already_started':True,'state':_read_json(out,{}).get('state')}));return
        ws=Workspace(root,home)
        if pending_authors(ws) or ws.manual_waiting() or (home/'STUDIO_CURRENT.json').exists():
            raise RuntimeError('Pending or interrupted home work')
        run=_read_json(home/'trainer-trials/gemini-m5-tests-delivered-20260927.json',{})
        if run.get('state')!='admitted':raise RuntimeError('No admitted test candidate')
        draft=ws._draft(run['draft']);prior=ws._draft(run['prior_draft'])
        if draft['state']!='needs_revision' or draft.get('verification'):raise RuntimeError('Candidate already used')
        source=collect_snapshot(ws)['digest']
        if source!=run['source_digest']:raise RuntimeError('Source changed')
        changed=[f['path'] for f in draft['files'] if f['content']!=next(o['content'] for o in prior['files'] if o['path']==f['path'])]
        if changed!=['tests/test_recommendation_cli.py']:raise RuntimeError('Not tests-only')
        code=next(f['content'] for f in draft['files'] if f['path']==changed[0]); tree=ast.parse(code)
        names=[f'{c.name}.{m.name}' for c in tree.body if isinstance(c,ast.ClassDef) for m in c.body
               if isinstance(m,ast.FunctionDef) and m.name=='test_export_serialization_error_cleanup']
        if len(names)!=1:raise RuntimeError('Cannot uniquely identify the model-authored test')
        test='tests.test_recommendation_cli.'+names[0]
        stage=Path(tempfile.mkdtemp(prefix='growth-test-discrimination-',dir=str(root.parent/'.tmp')))
        files=_candidate_files(load_snapshot(ws,draft['snapshot_digest']),draft)
        for rel,raw in files.items():
            dest=stage/rel
            if not dest.resolve().is_relative_to(stage):raise RuntimeError('Unsafe staged path')
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        record={'state':'started','utc':_now(),'draft':draft['id'],'author':draft.get('drafted_by'),'test':test,
            'stage':str(stage),'source_digest':source,'candidate_test_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'scope':'One named model-authored development test on the retained faulty implementation. Not full project/owner acceptance, patch validation, or a positive control.',
            'call_count':0,'timeout_s':45,'apply':False,'trainer_test_authorship':False,
            'review_limit':'Test checks graceful failure and destination cleanup; it does not directly assert descriptor closure.'}
        _write_json(out,record)
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TEMP=str(stage),TMP=str(stage))
        env.pop('PYTHONPATH',None)
        try:
            result=subprocess.run([sys.executable,'-m','unittest',test,'-v'],cwd=stage,env=env,
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=45)
            record.update(state='completed',exit_code=result.returncode,output=result.stdout[-12000:])
            record['detected_known_defect']=result.returncode!=0 and 'Bad file descriptor' in result.stdout and '_os.close(fd)' in result.stdout
        except subprocess.TimeoutExpired as error:
            record.update(state='timeout',detected_known_defect=None,output=str(error.output)[-12000:])
        record.update(finished=_now(),source_unchanged=collect_snapshot(ws)['digest']==source,
                      decision='park_one_call_allocation; implementation correction and full acceptance remain open')
        _write_json(out,record);ws.ledger.append('trainer.authored_test_discrimination',record)
        print(json.dumps(record),flush=True)
    finally:
        if lock.handle:lock.handle.close()


if __name__=='__main__':main()
