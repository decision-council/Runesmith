"""Bounded Studio build steps, with receipts distinct from repair experiments.

A disposable working copy and a stripped environment prevent accidental use of
inherited keys. They are not an OS security sandbox. Enable executable checks
only for a project the operator authorizes. Tests do not send production work.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from runesmith.app.planner import draft_files, draft_plan, milestone_contract, source_context, next_milestone, milestone_ready
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.app.snapshots import (SnapshotUnsupported, collect_snapshot, digest_files,
                                     load_snapshot, path_kind)
from runesmith.objects.code import encode_like
from runesmith.app.acceptance_contracts import expectations, expectation_digest
from runesmith.app.check_progress import PROGRESS_RUNNER, read_progress
from runesmith.app.author_allowance import ordinary_allowance

CHECK_TIMEOUT_S = 120
# A check outcome in the owner's words, for the live log (journey J4-F17); receipts keep the raw status.
OUTCOME_WORDS = {'acceptance_passed': 'your acceptance checks passed', 'self_checks_passed': 'its own tests passed',
                 'unchecked': 'nothing checked it yet: add acceptance checks', 'failed': 'checks failed',
                 'inconclusive': 'checks did not finish', 'stale': 'its inputs changed since it was drafted',
                 'unsupported': 'it could not be checked here', 'refused': 'it was refused'}

RUNNER = '''import importlib.util,json,sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path.cwd()),str(Path.cwd()/"src")]
''' + PROGRESS_RUNNER + '''
if sys.argv[1] == "project":
    suite=unittest.defaultTestLoader.discover("tests",top_level_dir=".")
else:
    paths=json.loads(sys.argv[1]) if sys.argv[1].startswith("[") else [sys.argv[1]]
    suite=unittest.TestSuite()
    for index,path in enumerate(paths):
        spec=importlib.util.spec_from_file_location("owner_acceptance_"+str(index),path)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
progress.planned=suite.countTestCases();progress.phase="fixtures_or_between_tests"
progress.event("discovery_completed")
if len(sys.argv)>3:
    # Optional bounded discovery receipt for source-baseline diagnostics only.
    import hashlib
    def test_ids(node):
        if isinstance(node,unittest.TestSuite):
            for child in node:yield from test_ids(child)
        else:yield node.id()
    ids=[];count=0;truncated=0;identity=hashlib.sha256()
    for name in test_ids(suite):
        count+=1;identity.update((json.dumps(name,ensure_ascii=True)+"\\n").encode("ascii"))
        if len(ids)<128:
            ids.append(name[:192]);truncated+=int(len(name)>192)
    inventory={"schema":1,"count":count,"ids":ids,"omitted":count-len(ids),
               "truncated_ids":truncated,"sha256":identity.hexdigest()}
    try:
        target=Path(sys.argv[3]);temporary=target.with_suffix(".tmp")
        temporary.write_text(json.dumps(inventory,ensure_ascii=True),encoding="utf-8")
        os.replace(temporary,target)
    except OSError:pass
result=unittest.TextTestRunner(verbosity=2,resultclass=ProgressResult).run(suite)
bad=list(result.failures)+list(result.errors)
failure_details=[{"test":test.id(),"trace_tail":trace[-800:],
    "criteria":list(getattr(test,"PUBLIC_CRITERIA",{}).get(test._testMethodName,[]))} for test,trace in bad[:8]]
print("RUNESMITH_CHECK="+json.dumps({"ran":result.testsRun,"skipped":len(result.skipped),
    "errors":len(result.errors),"failures":len(result.failures),"ok":result.wasSuccessful(),
    "failure_details":failure_details,"failure_details_omitted":max(0,len(bad)-len(failure_details))}))
'''


def status(ws):
    grant = _read_json(ws.home / 'BUILD_GRANT.json', {})
    bound = grant.get('root') == str(ws.root) and grant.get('home') == str(ws.home)
    return {'enabled': ws.settings()['build_steps'], 'apply': bool(bound and grant.get('enabled')),
            'paths': grant.get('paths', []) if bound else [], 'grant': grant.get('id') if bound else None,
            'acceptance_folder': str(ws.home / 'acceptance'),
            'last': _read_json(ws.home / 'BUILD_LAST.json', None)}


def _run_checks(stage: Path, kind: str, logs: Path, *, timeout_s=None, inventory_path=None):
    limit=CHECK_TIMEOUT_S if timeout_s is None else timeout_s
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1 <= limit <= 600:
        raise WorkspaceError('Check deadline must be an integer from 1 to 600 seconds.')
    # SYSTEMDRIVE, PROGRAMDATA and ALLUSERSPROFILE are not secrets. Without them Windows components create a literal
    # "%SystemDrive%\ProgramData" folder inside the working copy (seen in journey J4).
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','SYSTEMDRIVE','PROGRAMDATA','ALLUSERSPROFILE'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
               TEMP=str(stage), TMP=str(stage), HOME=str(stage), USERPROFILE=str(stage))
    started = time.monotonic()
    timed_out = False
    progress_path = logs.with_suffix('.progress.json')
    command = [sys.executable, '-B', '-c', RUNNER, kind, str(progress_path.resolve())]
    if inventory_path is not None:
        command.append(str(inventory_path.resolve()))
    with logs.open('wb') as output:
        try:
            completed = subprocess.run(command, cwd=stage,
                           env=env, stdout=output, stderr=subprocess.STDOUT,
                           timeout=limit, check=False)
        except subprocess.TimeoutExpired:
            timed_out = True
    with logs.open('rb') as output:
        output.seek(max(0, logs.stat().st_size-16000))
        text = output.read(16000).decode('utf-8',errors='replace')
    ended = time.monotonic()
    timing = {'elapsed_s': round(ended-started, 3), 'limit_s': limit,
              'progress': read_progress(progress_path, ended_monotonic=ended, timed_out=timed_out)}
    if timed_out:
        return {'status':'timeout', 'ok':False, 'output':text[-8000:], **timing}
    rows = [line[len('RUNESMITH_CHECK='):] for line in text.splitlines() if line.startswith('RUNESMITH_CHECK=')]
    result = json.loads(rows[-1]) if rows else {'ok':False, 'ran':0}
    result['ok'] = bool(completed.returncode == 0 and result.get('ok') and result.get('ran',0) > result.get('skipped',0))
    raw_output = '\n'.join(line for line in text.splitlines() if not line.startswith('RUNESMITH_CHECK='))
    result.update(status='passed' if result['ok'] else 'failed', output=raw_output[-8000:], **timing)
    return result


def _candidate_files(snapshot, draft):
    files = dict(snapshot['files'])
    declared = snapshot['policy'].get('declared_documents', [])
    for f in draft['files']:
        rel = f['path']
        if not path_kind(rel, declared):
            raise SnapshotUnsupported(f'Output is outside the local verification profile: {rel}')
        base = files.get(rel)
        if f.get('expected_sha256') and (base is None or hashlib.sha256(base).hexdigest()!=f['expected_sha256']):
            raise SnapshotUnsupported('Candidate file base does not match the frozen source.')
        if f.get('expected_absent') and base is not None:
            raise SnapshotUnsupported('Candidate creation conflicts with a frozen input.')
        files[rel] = encode_like(f['content'], base)
    return files


def author_context_status(ws, draft, snapshot):
    """Validate the original author view, not today's packet-size policy.

    Full snapshot equality is still a separate mandatory gate. A retained
    host-recorded file list plus its original digest allows smaller/larger
    future packet budgets without falsely declaring unchanged source stale.
    """
    current = source_context(ws, snapshot=snapshot)
    if not draft.get('snapshot_digest') or not ('shown_files' in draft or 'bound_source_files' in draft):
        return {'ok': current['digest'] == draft.get('context_digest'), 'binding': 'legacy_current_packet',
                'file_count': len(current['files']), 'current_packet_differs': False}
    names = draft.get('bound_source_files', draft.get('shown_files'))
    if (not isinstance(names, list) or len(names) > 2000 or
            any(not isinstance(p, str) for p in names) or len(set(names)) != len(names)):
        return {'ok': False, 'binding': 'invalid_retained_file_list'}
    files = {}
    for name in names:
        if name not in snapshot['files'] or snapshot['manifest'].get(name, {}).get('visibility') != 'model':
            return {'ok': False, 'binding': 'invalid_retained_file_list'}
        try: files[name] = snapshot['files'][name].decode('utf-8-sig')
        except UnicodeError: return {'ok': False, 'binding': 'unreadable_retained_file'}
    # Older packets could retain literal CRLF; new ones normalize it. Both
    # must hash to the originally recorded digest, never a replacement digest.
    for normalization, view in [('literal', files), ('lf', {p: s.replace('\r\n', '\n') for p, s in files.items()})]:
        digest = hashlib.sha256(json.dumps(view, sort_keys=True).encode()).hexdigest()
        if digest == draft.get('context_digest'):
            return {'ok': True, 'binding': ('frozen_source_bindings' if 'bound_source_files' in draft else 'frozen_shown_files'), 'normalization': normalization,
                    'file_count': len(files), 'context_digest': digest,
                    'current_packet_differs': current['digest'] != digest}
    return {'ok': False, 'binding': 'retained_digest_mismatch', 'file_count': len(files)}


def author_context_preflight(ws, draft):
    """Read-only identity diagnostic; never replace a historical check verdict."""
    result = {'ok': False, 'diagnostic_only': True, 'full_snapshot_current': False}
    try:
        current = collect_snapshot(ws)
        if not draft.get('snapshot_digest') or current['digest'] != draft['snapshot_digest']:
            return result | {'detail': 'Full verification inputs no longer match the retained author snapshot.'}
        frozen = load_snapshot(ws, draft['snapshot_digest'])
        identity = author_context_status(ws, draft, frozen)
        return result | identity | {'full_snapshot_current': True,
            'detail': ('Original author view and full source snapshot match. This is not a new test result; '
                       'prior check verdicts and spent allocations are unchanged.' if identity['ok'] else
                       'Full source snapshot matches, but the retained author view cannot be validated.')}
    except (SnapshotUnsupported, OSError, ValueError, TypeError, KeyError):
        return result | {'detail': 'Author/source identity is unavailable; no check or resource allocation performed.'}


def verify_draft(ws, draft, *, check_timeout_s=None, project_timeout_s=None, owner_timeout_s=None,
                 phase_checkpoint=lambda: None):
    """Verify snapshot and optional owner-maintained acceptance tests, never live files."""
    from runesmith.app.build_jobs import validate_checkpoint
    validate_checkpoint(phase_checkpoint, 'phase_checkpoint')
    milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == draft.get('milestone')), None)
    if not milestone or milestone_contract(ws, milestone) != draft.get('contract'):
        return {'status':'stale', 'detail':'Milestone definition changed; draft needs review.'}
    public_digest = expectation_digest(ws, milestone['id'])
    if draft.get('public_acceptance_digest') != public_digest:
        return {'status':'stale', 'detail':'Public acceptance expectations changed; obtain a reviewed revision.'}
    try:
        snapshot = collect_snapshot(ws)
        if draft.get('snapshot_digest'):
            frozen = load_snapshot(ws, draft['snapshot_digest'])
            if frozen['digest'] != snapshot['digest']:
                return {'status':'stale', 'detail':'Full verification inputs changed since authoring.'}
            snapshot = frozen
        context = source_context(ws, snapshot=snapshot)
    except SnapshotUnsupported as error:
        return {'status':'unsupported', 'detail':str(error)}
    author_context = author_context_status(ws, draft, snapshot)
    if not author_context['ok']:
        return {'status':'stale', 'detail':'The retained author view does not match its recorded digest.',
                'author_context':author_context}
    if not draft.get('snapshot_digest') and (context['omitted'] or context.get('truncated_inventory')):
        return {'status':'unsupported', 'detail':'Full verification needs a larger or project-specific snapshot profile.'}
    try:
        candidate = _candidate_files(snapshot, draft)
    except SnapshotUnsupported as error:
        return {'status':'unsupported', 'detail':str(error)}
    candidate_digest = digest_files(candidate, snapshot['policy'].get('declared_documents', []))['digest']
    results = ws.home / 'build-runs' / draft['id'] / ('v-' + uuid.uuid4().hex[:12])
    results.mkdir(parents=True, exist_ok=True)
    def record(value):
        value.update(utc=_now(), evidence_dir=results.relative_to(ws.home).as_posix())
        value.update(snapshot_digest=snapshot['digest'], candidate_digest=candidate_digest,
                     snapshot_policy=snapshot['policy'], verification_input_files=len(candidate),
                     author_context=author_context)
        _write_json(results/'VERIFICATION.json',value)
        return value
    acceptance = ws.home / 'acceptance' / (milestone['id'] + '.py')
    acceptance_bytes = acceptance.read_bytes() if acceptance.is_file() else None
    acceptance_bundle = _acceptance_files(ws, milestone['id'])
    public_contracts = [c for c in (expectations(ws, name[:-len('.py')]) for name in acceptance_bundle) if c]
    with tempfile.TemporaryDirectory(prefix='stage-', dir=results) as directory:
        stage = Path(directory)
        for rel, content in candidate.items():
            if not ws._safe_rel(rel):
                return record({'status':'refused', 'detail':'An input path is outside the workspace.'})
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        # Compile without importing/executing project modules first.
        try:
            for path in stage.rglob('*.py'):
                compile(path.read_text(encoding='utf-8-sig'), str(path.relative_to(stage)), 'exec')
        except (SyntaxError, UnicodeError) as error:
            return record({'status':'failed', 'detail':str(error)[:500]})
        frozen_files = {p.relative_to(stage).as_posix():p.read_bytes() for p in stage.rglob('*') if p.is_file()}
        check_options={} if check_timeout_s is None else {'timeout_s':check_timeout_s}
        owner_options=dict(check_options)
        if project_timeout_s is not None:check_options={'timeout_s':project_timeout_s}
        if owner_timeout_s is not None:owner_options={'timeout_s':owner_timeout_s}
        def enter_phase(name, completed=None):
            try:
                phase_checkpoint()
            except Exception as error:
                # Preserve completed evidence and distinguish unrun phases. The
                # worker still receives its original stop/revocation exception.
                value = record({'status': 'inconclusive', 'detail': f'Execution stopped before {name}; no later phase ran.',
                    'project_checks': completed, 'acceptance': None, 'interrupted_before': name,
                    'public_acceptance_digest': public_digest,
                    'scope': 'Partial local checks; no acceptance verdict or automatic replay.'})
                error._runesmith_verification = value
                raise
        enter_phase('project checks')
        if (stage / 'tests').is_dir() or any(rel.endswith('.py') for rel in frozen_files):
            checks = _run_checks(stage, 'project', results / 'project-checks.txt', **check_options)
        else:
            # Documents or plain web pages: no tests folder and no Python, so there are no project tests to run. The
            # owner's acceptance checks decide; without them nothing is verified (status "unchecked", journey J4).
            checks = {'status': 'not_applicable', 'ok': True, 'ran': 0, 'skipped': 0, 'failures': 0, 'errors': 0,
                      'output': 'No tests folder and no Python files: no project tests to run.'}
        changed = [rel for rel,data in frozen_files.items() if not (stage/rel).is_file() or (stage/rel).read_bytes()!=data]
        if changed:
            return record({'status':'failed', 'detail':'Project tests changed candidate files: ' + ', '.join(changed),
                    'project_checks':checks})
        oracle = None
        if checks['ok'] and acceptance_bytes is not None:
            enter_phase('owner acceptance', checks)
            frozen_paths = []
            for name,data in acceptance_bundle.items():
                frozen = results / ('acceptance-'+name)
                frozen.write_bytes(data)
                frozen_paths.append(str(frozen))
            # Acceptance gets only the frozen candidate, never project-test outputs.
            with tempfile.TemporaryDirectory(prefix='acceptance-stage-', dir=results) as fresh:
                clean_stage = Path(fresh)
                for rel,data in frozen_files.items():
                    target=clean_stage/rel; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                oracle = _run_checks(clean_stage, json.dumps(frozen_paths), results / 'acceptance-checks.txt', **owner_options)
                changed = [rel for rel,data in frozen_files.items() if not (clean_stage/rel).is_file() or (clean_stage/rel).read_bytes()!=data]
                if changed:
                    oracle.update(ok=False,status='failed',detail='Acceptance changed candidate files: '+', '.join(changed))
        status_name = ('inconclusive' if checks.get('status')=='timeout' or (oracle or {}).get('status')=='timeout' else
                       'failed' if not checks['ok'] or (oracle and not oracle['ok']) else
                       'acceptance_passed' if oracle else
                       'unchecked' if checks.get('status') == 'not_applicable' else 'self_checks_passed')
        return record({'status':status_name, 'project_checks':checks, 'acceptance':oracle, 'utc':_now(),
                'public_acceptance_digest':public_digest, 'public_contracts':public_contracts,
                'acceptance_sha256':hashlib.sha256(acceptance_bytes).hexdigest() if acceptance_bytes else None,
                'acceptance_bundle':{name:hashlib.sha256(data).hexdigest() for name,data in acceptance_bundle.items()},
                'scope':'local executable checks; not business-outcome evidence or OS confinement'})


def _acceptance_files(ws, milestone_id):
    """The owner acceptance a candidate is judged by: its milestone's file and those of done milestones, in plan order."""
    files = {}
    for item in ws.plan()['milestones']:
        file = ws.home/'acceptance'/(item['id']+'.py')
        if (item['id']==milestone_id or item.get('status')=='done') and file.is_file():
            files[file.name] = file.read_bytes()
    return files


def _unchanged_verdict(ws, draft, milestone, contract, context, checkpoint):
    """The last verdict of a waiting draft whose inputs have not changed since it was checked, or None (F14).

    Rechecking identical inputs on every scheduled round only repeats the answer. A changed source, public
    expectation or owner acceptance file (for example, checks the owner has just approved) means checking again.
    """
    verification = draft.get('verification') or {}
    if (verification.get('status') not in ('self_checks_passed', 'acceptance_passed')
            or verification.get('snapshot_digest') != context['snapshot_digest']
            or verification.get('acceptance_bundle') != {name: hashlib.sha256(data).hexdigest()
                                                         for name, data in _acceptance_files(ws, milestone['id']).items()}):
        return None
    checkpoint()
    result = {'draft': draft['id'], 'milestone': milestone['id'], 'verification': verification, 'unchanged': True,
              'summary': f"{draft['id']}: {verification['status']}, unchanged since its last check. Nothing applied."}
    if verification['status'] == 'acceptance_passed':
        with ws._lock:
            _apply_if_current(ws, draft, milestone, contract, status(ws), verification, result)
    else:
        result['summary'] = (f"{draft['id']} passed its own checks and is waiting for you. Applying it automatically "
                             f"needs acceptance checks for {milestone['id']}: propose them in Goals & plan.")
    return result


def _within_scope(path, paths):
    return any(path == prefix.rstrip('/') or path.startswith(prefix.rstrip('/') + '/') for prefix in paths)


def verification_inconclusive(verification):
    """Recognize new and legacy time-censored checks without rewriting receipts."""
    value=verification or {}
    if value.get('status')=='inconclusive':
        return True
    return bool(value.get('status')=='failed' and not value.get('detail') and any(
        (value.get(key) or {}).get('status')=='timeout' for key in ('project_checks','acceptance')))


def _ordinary_revision_lineage(ws, drafts, snapshot):
    """A normal build must not bypass the focused revision lineage guard."""
    # Only drafts from ordinary author attempts have that lineage. A correction's draft has no author request key,
    # and the guard failed on it with "Invalid author request key" (journey J2-B7); the allowance still applies.
    revision=next((d for d in drafts if d.get('state')=='needs_revision'
                   and d.get('snapshot_digest')==snapshot and d.get('author_request_key')),None)
    if revision:
        from runesmith.app.author_revisions import _lineage
        _lineage(ws,revision)


def build_step(ws, router, *, checkpoint=lambda: None, author_only=False):
    """One author attempt and bounded checks. No unattended repeated blind retries."""
    if type(author_only) is not bool:
        raise WorkspaceError('Author-only selection must be boolean.')
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: no build or model call.'}
    from runesmith.app.author_recovery import pending_authors, resume_author
    saved = pending_authors(ws)
    if saved:
        # Journey J2-F12: an answer that arrived after the wait stopped every later round until the owner came back.
        # Fetching it is no new model call, so the round fetches it and checks it through the normal gates.
        ready = next((row for row in saved if row['can_resume']), None)
        if author_only or ready is None:
            return {'summary':'Saved remote author request requires recovery before another build. No inference.'}
        recovered = resume_author(ws, ready['id'], checkpoint=checkpoint)
        if not recovered.get('draft') or recovered.get('already_used'):
            return dict(recovered, summary='Saved remote author request requires recovery: ' + recovered['summary'])
        draft = ws._draft(recovered['draft'])
        milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == draft.get('milestone')), None)
        if not milestone or not milestone_ready(ws.plan(), milestone):
            return recovered
        return _check_and_record(ws, draft, milestone, milestone_contract(ws, milestone), checkpoint=checkpoint)
    checkpoint()
    if not ws.plan():
        if author_only:
            raise WorkspaceError('Save a plan before requesting an author-only build.')
        plan = draft_plan(ws, router, checkpoint=checkpoint, automatic=True)
        return {'summary':f"Drafted plan v{plan['version']}; no files applied."}
    milestone = next_milestone(ws.plan())
    if not milestone:
        return {'summary':'No unfinished milestones. Review goals before starting another plan.'}
    contract = milestone_contract(ws, milestone)
    previous = [d for d in ws.drafts() if d.get('contract') == contract]
    if any(d.get('state') == 'applied' for d in previous):
        return {'summary':'Files applied; milestone awaits acceptance or owner review.'}
    context = source_context(ws)
    inconclusive=next((d for d in previous if d.get('state') in ('waiting','needs_revision')
        and d.get('snapshot_digest')==context['snapshot_digest']
        and d.get('public_acceptance_digest')==expectation_digest(ws,milestone['id'])
        and verification_inconclusive(d.get('verification'))),None)
    if inconclusive:
        return {'summary':'Saved candidate has an inconclusive check. Explicitly recheck it without inference; no new author call or automatic check retry.',
                'draft':inconclusive['id'],'milestone':milestone['id'],'verification_required':True}
    try:
        allowance = ordinary_allowance(ws, contract, context['snapshot_digest'])
    except WorkspaceError as error:
        return {'summary':str(error), 'allowance_blocked':True, 'milestone':milestone['id']}
    scope = allowance['scope']
    pending = next((d for d in previous if d.get('state') == 'waiting' and d.get('snapshot_digest') == context['snapshot_digest']
                  and d.get('context_digest') == context['digest']
                  and d.get('public_acceptance_digest') == expectation_digest(ws,milestone['id'])), None)
    if not pending:
        try:_ordinary_revision_lineage(ws,previous,context['snapshot_digest'])
        except (WorkspaceError,ValueError,KeyError,TypeError,OSError) as error:
            return {'summary':str(error),'allowance_blocked':True,'milestone':milestone['id']}
    if pending is not None and (unchanged := _unchanged_verdict(ws, pending, milestone, contract, context, checkpoint)):
        return unchanged
    if not pending and not allowance['remaining']:
        return {'summary':'Ordinary author allowance exhausted on this source and milestone. Review retained evidence; changing feedback does not grant more calls.',
                'replan_needed':True,'milestone':milestone['id']}
    attempt_path = ws.home/'build-attempts'/(uuid.uuid4().hex+'.json')
    attempt = {'scope':scope,'contract':contract,'context_digest':context['digest'],
               'snapshot_digest':context['snapshot_digest'],'state':'started','utc':_now()}
    if not pending:
        _write_json(attempt_path,attempt)
    try:
        # Reuse the selected object directly. Re-entering the planner can turn a
        # cache hit into an unreserved call if context changes on its next read.
        draft = pending if pending is not None else draft_files(ws, router, milestone['id'], attempt_id=attempt_path.name)
    except Exception as error:
        if not pending:
            remote=getattr(error,'remote_receipt',{})
            _write_json(attempt_path,dict(attempt,state='uncertain' if remote.get('unresolved') else 'failed',
                                         remote_receipt=remote,error=type(error).__name__+': '+str(error)[:300],
                                         feedback=getattr(error,'feedback',None),finished=_now()))
            ws.ledger.append('build.authoring_refused',{'milestone':milestone['id'],'error':str(error)[:300],
                              'feedback':getattr(error,'feedback',None),'attempt':attempt_path.name})
        raise
    if not pending:
        _write_json(attempt_path,dict(attempt,state='answered',draft=draft['id'],finished=_now()))
    if author_only:
        checkpoint()
        return {'draft':draft['id'], 'milestone':milestone['id'], 'author_only':True,
                'summary':f"Draft {draft['id']} retained for review. No checks, apply or follow-on work; existing checks, if any, are unchanged."}
    return _check_and_record(ws, draft, milestone, contract, checkpoint=checkpoint)


def build_escalation_status(ws):
    """Describe the one-shot alternate-author escape after a bounded miss.

    This does not increase the ordinary three-attempt budget.  It exposes one
    separately receipted call after that budget is exhausted, under the same
    source snapshot, milestone contract, paths and acceptance gates.
    """
    plan=ws.plan() or {};milestone=next_milestone(plan)
    if not milestone:return None
    contract=milestone_contract(ws,milestone);context=source_context(ws)
    try:
        allowance=ordinary_allowance(ws,contract,context['snapshot_digest'])
    except WorkspaceError as error:
        return {'eligible':False,'milestone':milestone['id'],'attempts':None,'used':None,
                'reason':str(error),'allowance':{'known':False,'can_draft':False,'blockers':[str(error)]}}
    scope=allowance['scope'];escalations=allowance['escalations']
    drafts=[d for d in ws.drafts() if d.get('contract')==contract]
    eligible=(ws.settings()['autonomy']!='observe' and not allowance['remaining']
              and not escalations and not any(d.get('state') in ('waiting','applied') for d in drafts))
    matching=[d for d in drafts if d.get('snapshot_digest')==context['snapshot_digest']
              and d.get('public_acceptance_digest')==expectation_digest(ws,milestone['id'])]
    reuse=next((d['id'] for d in matching if d.get('state')=='waiting' and d.get('context_digest')==context['digest']),None)
    blockers=[]
    from runesmith.app.work_modes import guard_job
    try:guard_job(ws,'build')
    except WorkspaceError as error:blockers.append(str(error))
    if ws.settings()['autonomy']=='observe':blockers.append('Observe mode does not permit authoring.')
    if any(d.get('state')=='applied' for d in drafts):blockers.append('Applied files await acceptance or owner review.')
    if any(d.get('state') in ('waiting','needs_revision') and verification_inconclusive(d.get('verification')) for d in matching):
        blockers.append('A saved candidate has an inconclusive check. Recheck it explicitly without inference.')
    from runesmith.app.author_recovery import pending_authors
    if pending_authors(ws):blockers.append('Recover or reconcile the saved author request before another call.')
    lineage_error=None
    if not reuse:
        try:_ordinary_revision_lineage(ws,drafts,context['snapshot_digest'])
        except (WorkspaceError,ValueError,KeyError,TypeError,OSError) as error:
            lineage_error=str(error);blockers.append(lineage_error)
    eligible=bool(eligible) and not blockers
    if not allowance['remaining'] and not reuse:blockers.append('Ordinary author allowance exhausted. Review saved candidates or an explicitly available continuation.')
    view=dict(allowance,known=True,reuse_draft=reuse,blockers=blockers,can_draft=not blockers)
    if lineage_error:
        view.update(known=False,remaining=None,recorded_attempts=allowance['used'])
    return {'eligible':eligible,'milestone':milestone['id'],'attempts':allowance['used'],
            'scope':scope,'used':bool(escalations),'receipt':escalations[-1].get('id') if escalations else None,
            'snapshot_digest':context['snapshot_digest'],'allowance':view,
            'reason':('Three ordinary author attempts were recorded without an accepted candidate.'
                      if eligible else None)}


def escalate_build(ws,router,*,checkpoint=lambda:None):
    """Run one alternate-author continuation after the ordinary cap."""
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: no escalation call or executable checks.'}
    state=build_escalation_status(ws)
    if not state or not state['eligible']:
        raise WorkspaceError('No one-shot build escalation is eligible on the current source and contract.')
    milestone=next(m for m in ws.plan()['milestones'] if m['id']==state['milestone'])
    contract=milestone_contract(ws,milestone)
    key='e'+uuid.uuid4().hex[:12];path=ws.home/'build-escalations'/(key+'.json')
    receipt={'id':key,'state':'started','utc':_now(),'scope':state['scope'],'milestone':milestone['id'],
             'contract':contract,'snapshot_digest':state['snapshot_digest'],'ordinary_attempts':state['attempts']}
    _write_json(path,receipt);ws.ledger.append('build.escalation_started',{'id':key,'milestone':milestone['id']})
    try:
        draft=draft_files(ws,router,milestone['id'])
    except Exception as error:
        _write_json(path,dict(receipt,state='failed',finished=_now(),error=type(error).__name__+': '+str(error)[:300],
                              feedback=getattr(error,'feedback',None)))
        ws.ledger.append('build.escalation_failed',{'id':key,'milestone':milestone['id'],'error':str(error)[:300]})
        raise
    _write_json(path,dict(receipt,state='answered',finished=_now(),draft=draft['id'],
                          author=draft.get('drafted_by')))
    ws.ledger.append('build.escalation_answered',{'id':key,'milestone':milestone['id'],
                     'draft':draft['id'],'author':draft.get('drafted_by')})
    return _check_and_record(ws,draft,milestone,contract,checkpoint=checkpoint)


def readmit_escalation_answer(ws,key,*,checkpoint=lambda:None):
    """Replay a retained escalation answer after a host-admission fix, with no call."""
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: no retained-answer admission or executable checks.'}
    if not isinstance(key,str) or not key.startswith('e') or not key[1:].isalnum():
        raise WorkspaceError('Invalid build escalation ID.')
    path=ws.home/'build-escalations'/(key+'.json');receipt=_read_json(path,{})
    if receipt.get('state')!='failed':
        raise WorkspaceError('Only a failed retained escalation answer can be readmitted.')
    answer_rel=(receipt.get('feedback') or {}).get('answer_receipt')
    answer_path=(ws.home/str(answer_rel or '')).resolve()
    if not answer_rel or ws.home.resolve() not in answer_path.parents:
        raise WorkspaceError('The escalation has no safe retained answer receipt.')
    saved=_read_json(answer_path,{})
    if not isinstance(saved.get('answer'),dict):
        raise WorkspaceError('The retained escalation answer is missing or unusable.')
    if saved.get('public_acceptance_digest') != expectation_digest(ws, receipt.get('milestone')):
        raise WorkspaceError('Public acceptance changed; the retained answer needs a new reviewed revision.')
    milestone=next((m for m in (ws.plan() or {}).get('milestones',[])
                    if m.get('id')==receipt.get('milestone')),None)
    if not milestone or not milestone_ready(ws.plan(),milestone):
        raise WorkspaceError('The escalation milestone is no longer ready.')
    contract=milestone_contract(ws,milestone);context=source_context(ws)
    allowance=ordinary_allowance(ws,contract,context['snapshot_digest'])
    if contract!=receipt.get('contract') or not any(row['id']==key for row in allowance['escalations']):
        raise WorkspaceError('Source or milestone changed; the retained answer cannot be replayed.')
    revision=next((d for d in ws.drafts() if d.get('contract')==contract and d.get('state')=='needs_revision'
                   and d.get('snapshot_digest')==context['snapshot_digest']),None)
    if not revision:raise WorkspaceError('The answer has no matching frozen candidate to revise.')
    from runesmith.app.planner import admit_revision_answer
    files=admit_revision_answer(ws,context,saved['answer'].get('files'),revision)
    draft=ws.save_draft(title=str(saved['answer'].get('title') or milestone['title']),
                        why=str(saved['answer'].get('why') or ''),files=files,
                        drafted_by=saved.get('author'),milestone=milestone['id'])
    exposure_rel=saved.get('memory_exposure');exposure=_read_json(ws.home/str(exposure_rel or ''),{})
    ws._save_draft_state(draft,'waiting',contract=contract,context_digest=context['digest'],
                         public_acceptance_digest=saved.get('public_acceptance_digest'),
                         snapshot_digest=context['snapshot_digest'],shown_files=sorted(context['files']),
                         memory_ids=exposure.get('memory_ids',[]),memory_exposure=exposure_rel,
                         recovered_from_escalation=key)
    ws.ledger.append('build.escalation_readmitted',{'id':key,'draft':draft['id'],'author':saved.get('author'),
                     'answer_receipt':answer_rel})
    result=_check_and_record(ws,draft,milestone,contract,checkpoint=checkpoint)
    _write_json(path,dict(receipt,state='recovered',recovered_utc=_now(),draft=draft['id'],
                          verification=(result.get('verification') or {}).get('status'),
                          advanced=bool(result.get('advanced'))))
    return result


def recheck_draft(ws, draft_id, *, checkpoint=lambda: None):
    """Check the saved candidate without a model call or applying any files."""
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: executable build checks are off.'}
    draft = ws._draft(draft_id)
    if draft.get('state') not in ('waiting', 'needs_revision'):
        return {'summary':'Only a pending candidate can be rechecked.'}
    milestone = next((m for m in (ws.plan() or {}).get('milestones', [])
                      if m['id'] == draft.get('milestone')), None)
    if not milestone or not milestone_ready(ws.plan(),milestone):
        return {'summary':'Milestone is no longer active; no checks run.'}
    return _check_and_record(ws, draft, milestone, milestone_contract(ws, milestone),
                             checkpoint=checkpoint, allow_apply=False)


def review_current_files(ws, milestone_id, *, checkpoint=lambda:None):
    """Evaluate existing project bytes without commissioning another implementation.

    This is a review receipt, not a model-authored draft or automatic completion.
    The owner can use it when children may already satisfy a parent milestone.
    """
    if ws.settings()['autonomy']=='observe' or not status(ws)['enabled']:
        return {'summary':'Executable current-file checks are off; no checks or model calls.'}
    milestone=next((m for m in (ws.plan() or {}).get('milestones',[]) if m['id']==milestone_id),None)
    if not milestone or not milestone_ready(ws.plan(),milestone):
        raise WorkspaceError('Select a ready open milestone for current-file review.')
    checkpoint()
    from runesmith.app.snapshots import freeze_snapshot
    snapshot=collect_snapshot(ws);freeze_snapshot(ws,snapshot)
    context=source_context(ws,snapshot=snapshot)
    probe={'id':'current-'+uuid.uuid4().hex[:12],'milestone':milestone_id,'files':[],
           'contract':milestone_contract(ws,milestone),'context_digest':context['digest'],
           'snapshot_digest':snapshot['digest'],'public_acceptance_digest':expectation_digest(ws,milestone_id)}
    verification=verify_draft(ws,probe,phase_checkpoint=lambda: _phase_guard(ws, checkpoint))
    result={'id':probe['id'],'milestone':milestone_id,'utc':_now(),
            'contract':probe['contract'],'verification':verification,'inference_calls':0,'source_writes':0,
            'summary':f"Current files for {milestone_id}: {verification['status']}. No inference, source edits or milestone completion."}
    _write_json(ws.home/'current-checks'/(probe['id']+'.json'),result)
    ws.ledger.append('build.current_files_checked',{'id':probe['id'],'milestone':milestone_id,
                     'status':verification['status'],'evidence_dir':verification.get('evidence_dir'),
                     'snapshot_digest':snapshot['digest'],'inference_calls':0,'source_writes':0})
    return result


def current_file_reviews(ws):
    rows=[_read_json(p,{}) for p in (ws.home/'current-checks').glob('*.json')]
    return sorted(rows,key=lambda r:r.get('utc',''),reverse=True)[:10]


def correct_refusal(ws, router, attempt_id, *, checkpoint=lambda: None):
    """Run one receipt-linked correction, then the ordinary verification/apply gates."""
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: correction calls and executable checks are off.'}
    from runesmith.app.build_corrections import correct_rejected_answer
    draft=correct_rejected_answer(ws,router,attempt_id,checkpoint=checkpoint)
    milestone=next((row for row in (ws.plan() or {}).get('milestones',[])
                    if row.get('id')==draft.get('milestone')),None)
    if not milestone or not milestone_ready(ws.plan(),milestone):
        return {'summary':'Correction milestone is no longer ready; candidate retained, no checks run.',
                'draft':draft['id']}
    return _check_and_record(ws,draft,milestone,milestone_contract(ws,milestone),checkpoint=checkpoint)


def supplement_status(ws, draft):
    current=expectation_digest(ws,draft['milestone'])
    used=any(_read_json(p,{}).get('milestone')==draft['milestone']
             for p in (ws.home/'build-supplements').glob('*.json'))
    return {'eligible':bool(current and current!=draft.get('public_acceptance_digest')
                            and draft.get('state')=='needs_revision' and not used),
            'used':used,'public_acceptance_digest':current}


def supplement_build(ws,router,draft_id,reason,*,checkpoint=lambda:None,author_only=False):
    """One explicitly authorized call after a public requirement clarification.

    No ordinary attempt, escalation or correction counter is reset. This never
    runs from auto-work and cannot trigger a further automatic continuation.
    """
    if type(author_only) is not bool:
        raise WorkspaceError('Author-only selection must be boolean.')
    if ws.settings()['autonomy']=='observe':
        return {'summary':'Observe mode: no supplemental author call or checks.'}
    if not isinstance(reason,str) or not reason.strip():
        raise WorkspaceError('A supplemental call requires an explicit authorization reason.')
    draft=ws._draft(draft_id)
    if not supplement_status(ws,draft)['eligible']:
        raise WorkspaceError('No unused requirement-clarification supplement is eligible.')
    milestone=next((m for m in (ws.plan() or {}).get('milestones',[]) if m['id']==draft['milestone']),None)
    if not milestone or not milestone_ready(ws.plan(),milestone):
        raise WorkspaceError('The selected candidate milestone is no longer ready.')
    contract=milestone_contract(ws,milestone); context=source_context(ws)
    if draft.get('contract')!=contract or draft.get('snapshot_digest')!=context['snapshot_digest']:
        raise WorkspaceError('The selected candidate source or milestone changed.')
    if any(_read_json(p,{}).get('state') in ('started','uncertain')
           for folder in ('build-attempts','build-corrections','build-escalations','build-supplements')
           for p in (ws.home/folder).glob('*.json')):
        raise WorkspaceError('Reconcile unfinished author receipts before authorizing a supplement.')
    checkpoint()
    key='s'+uuid.uuid4().hex[:12];path=ws.home/'build-supplements'/(key+'.json')
    receipt={'id':key,'state':'started','utc':_now(),'milestone':milestone['id'],
             'candidate':draft_id,'contract':contract,'snapshot_digest':context['snapshot_digest'],
             'reason':reason[:2000],'public_acceptance_digest':expectation_digest(ws,milestone['id']),
             'author_only':author_only}
    _write_json(path,receipt);ws.ledger.append('build.supplement_authorized',receipt)
    try:
        revised=draft_files(ws,router,milestone['id'],revision=draft)
    except Exception as error:
        _write_json(path,dict(receipt,state='failed',finished=_now(),error=str(error)[:500]))
        raise
    _write_json(path,dict(receipt,state='answered',finished=_now(),draft=revised['id'],author=revised.get('drafted_by')))
    ws._save_draft_state(revised,'waiting',supplement_of=key)
    if author_only:
        return {'summary':f"Draft {revised['id']} saved unverified. No checks or apply; review and allocate checks separately.",
                'draft':revised['id'],'milestone':milestone['id'],'advanced':False,'author_only':True}
    return _check_and_record(ws,revised,milestone,contract,checkpoint=checkpoint)


def _check_and_record(ws, draft, milestone, contract, *, checkpoint, allow_apply=True, check_timeout_s=None,
                      project_timeout_s=None, owner_timeout_s=None, phase_checkpoint=None):
    from runesmith.app.build_jobs import validate_checkpoint
    validate_checkpoint(checkpoint)
    if phase_checkpoint is not None:
        validate_checkpoint(phase_checkpoint, 'phase_checkpoint')
    checkpoint()
    grant = status(ws)
    if not grant['enabled']:
        return {'summary':f"Draft {draft['id']} is ready for review. Checking drafts is off: turn on 'Check drafts by running their tests' in Goals & plan → Build continuation, or use Recheck on the draft."}
    options={} if check_timeout_s is None else {'check_timeout_s':check_timeout_s}
    if project_timeout_s is not None:options['project_timeout_s']=project_timeout_s
    if owner_timeout_s is not None:options['owner_timeout_s']=owner_timeout_s
    options['phase_checkpoint'] = lambda: _phase_guard(ws, checkpoint, phase_checkpoint)
    try:
        verification = verify_draft(ws, draft, **options)
    except Exception as error:
        partial = getattr(error, '_runesmith_verification', None)
        if partial is not None:
            _save_checked_draft(ws, draft, contract, partial, allow_apply=False)
            _write_json(ws.home / 'BUILD_LAST.json', {'draft': draft['id'], 'milestone': milestone['id'],
                'verification': partial, 'summary': partial['detail'], 'utc': _now()})
        raise
    _save_checked_draft(ws, draft, contract, verification, allow_apply=allow_apply)
    result = {'draft':draft['id'], 'milestone':milestone['id'], 'verification':verification,
              'summary':f"Draft “{draft.get('title') or draft['id']}”: {OUTCOME_WORDS.get(verification['status'], verification['status'])}. Nothing was written."}
    checkpoint()
    if allow_apply:
        with ws._lock:
            _apply_if_current(ws, draft, milestone, contract, grant, verification, result)
    _write_json(ws.home / 'BUILD_LAST.json', dict(result, utc=_now()))
    return result


def _save_checked_draft(ws, draft, contract, verification, *, allow_apply):
    state = 'needs_revision' if verification['status'] == 'failed' else 'waiting'
    history = list(draft.get('verification_history', []))
    if verification.get('evidence_dir'):
        history.append(verification['evidence_dir'])
    ws._save_draft_state(draft, state, verification=verification, verification_history=history,
                         verified=verification['status'] == 'acceptance_passed')
    ws.ledger.append('build.checked', {'draft':draft['id'], 'status':verification['status'],
                                      'contract':contract, 'author':draft.get('drafted_by'),
                                      'recheck_only':not allow_apply})
    from runesmith.app.build_memory import remember_check
    memory_id = remember_check(ws, draft, verification)
    ws._save_draft_state(draft, state, check_memory_id=memory_id)
    ws.ledger.append('build.remembered', {'draft':draft['id'], 'memory_id':memory_id,
                                         'evidence_dir':verification.get('evidence_dir')})


def _phase_guard(ws, checkpoint, phase_checkpoint=None):
    checkpoint()
    if phase_checkpoint is not None and phase_checkpoint is not checkpoint:
        phase_checkpoint()
    if not status(ws)['enabled'] or ws.settings()['autonomy'] == 'observe':
        raise WorkspaceError('Executable checks were disabled before the next phase; no further tests started.')


def _apply_if_current(ws, draft, milestone, contract, grant, verification, result):
    current_grant = status(ws)
    if (verification['status'] == 'acceptance_passed' and current_grant['enabled'] and current_grant['apply']
            and ws.settings()['autonomy'] == 'propose' and current_grant['grant'] == grant['grant']
            and all(_within_scope(f['path'], current_grant['paths']) for f in draft['files'])):
        # Source, goal, acceptance fixture and grant must still be unchanged after checks.
        current = next((m for m in ws.plan()['milestones'] if m['id'] == milestone['id']), {})
        acceptance = ws.home / 'acceptance' / (milestone['id'] + '.py')
        try:
            live_snapshot = collect_snapshot(ws)
            current_draft = ws._draft(draft['id'])
            candidate_matches = digest_files(_candidate_files(live_snapshot,current_draft),
                live_snapshot['policy'].get('declared_documents',[]))['digest'] == verification.get('candidate_digest')
        except SnapshotUnsupported:
            candidate_matches = False
            live_snapshot = {}
        valid = (milestone_ready(ws.plan(),current) and candidate_matches and
                 live_snapshot.get('digest') == verification.get('snapshot_digest') and
                 milestone_contract(ws,current) == contract and acceptance.is_file() and
                 expectation_digest(ws,current['id']) == verification.get('public_acceptance_digest') and
                 all(expectation_digest(ws,c['milestone']) == c['digest']
                     for c in verification.get('public_contracts',[])) and
                 hashlib.sha256(acceptance.read_bytes()).hexdigest() == verification['acceptance_sha256'] and
                 all((ws.home/'acceptance'/name).is_file() and
                     hashlib.sha256((ws.home/'acceptance'/name).read_bytes()).hexdigest()==digest
                     for name,digest in verification.get('acceptance_bundle',{}).items()))
        if not valid:
            result['summary'] = 'Verified snapshot changed before apply; no files written.'
        else:
            applied = ws.apply_draft(draft['id'])
            if applied['ok']:
                ws.update_milestone(milestone['id'], {'status':'done'})
                ws._save_draft_state(ws._draft(draft['id']), 'applied', applied_by='delegated_build',
                                     grant=grant['grant'])
                ws.ledger.append('build.advanced', {'draft':draft['id'], 'milestone':milestone['id'],
                    'grant':grant['grant'], 'acceptance_sha256':verification['acceptance_sha256']})
                result.update(advanced=True, summary=f"Applied {draft['id']}; acceptance passed; {milestone['id']} complete.")
            else:
                result['summary'] = applied['detail']
