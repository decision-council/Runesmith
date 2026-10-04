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
import re
import subprocess
import sys
import tempfile
import time
import uuid

from runesmith.app import runesmith_md
from runesmith.app.planner import (draft_files, draft_plan, focus_missing, focus_problem, milestone_contract, milestone_view,
                                   source_context, next_milestone, milestone_ready, ready_milestones, revisable_candidates)
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.app.snapshots import (SnapshotUnsupported, collect_snapshot, digest_files,
                                     load_snapshot, path_kind)
from runesmith.objects.code import encode_like
from runesmith.app.acceptance_contracts import expectations, expectation_digest
from runesmith.app.check_progress import PROGRESS_RUNNER, read_progress
from runesmith.app.author_allowance import ordinary_allowance
from runesmith.app.source_focus import shown_view

CHECK_TIMEOUT_S = 120
# Every done milestone's checks judge each build, so the owner run grows with the plan: a fixed 120 s stopped every
# J11 build once 41 milestones had checks (journey J11-B17). Per check, about three times what J11 measured (0.64 s).
OWNER_CHECK_S = 2
OWNER_LIMIT_S = 600


def owner_check_limit(bundle) -> int:
    """The time limit for an owner acceptance bundle ({file name: bytes}), from the number of checks in it."""
    # Also in the one-line form a frozen project suite is embedded in (escaped newlines), and async tests: both ran
    # and were not counted, so such a bundle got the old 120 s (review of J11-B17).
    tests = sum(len(re.findall(rb'(?:^|\\n)[ \t]+(?:async[ \t]+)?def test', data, re.M)) for data in bundle.values())
    return min(OWNER_LIMIT_S, max(CHECK_TIMEOUT_S, 60 + OWNER_CHECK_S * tests))

# A check outcome in the owner's words, for the live log (journey J4-F17); receipts keep the raw status.
OUTCOME_WORDS = {'acceptance_passed': 'your acceptance checks passed', 'self_checks_passed': 'its own tests passed',
                 'unchecked': 'nothing checked it yet: add acceptance checks', 'failed': 'checks failed',
                 'inconclusive': 'checks did not finish', 'stale': 'its inputs changed since it was drafted',
                 'unsupported': 'it could not be checked here', 'refused': 'it was refused'}

RUNNER = '''import importlib.util,json,sys,types,unittest
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
        # Each test class once: the approved files' footer leaves its loop variable _case naming the same class, and
        # loading by name ran every check twice (journey J11-B17: 188 runs of 94 checks passed the time limit). The
        # module is loaded through a view that omits a second name for a class, so a module with its own load_tests
        # (which gets that view's standard suite, and runs in the module's own globals) is loaded once too.
        seen=set();skip=set()
        for name in dir(module):
            value=getattr(module,name)
            if isinstance(value,type) and issubclass(value,unittest.TestCase):
                if value in seen:skip.add(name)
                else:seen.add(value)
        view=types.ModuleType(module.__name__);view.__dict__.update({k:v for k,v in vars(module).items() if k not in skip})
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(view))
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
    outputs = tuple(declared) + tuple(snapshot.get('document_outputs') or ())    # allowed folders (J11-G32)
    for f in draft['files']:
        rel = f['path']
        if not path_kind(rel, declared) and not path_kind(rel, outputs):
            raise SnapshotUnsupported(f'{rel} cannot be checked here: Runesmith checks code, settings and documents '
                                      'only inside the files or folders you allow under Goals & plan → Build '
                                      '("Allowed files or folders"), and never secrets, data or logs.')
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
    from runesmith.app.source_focus import context_digest, recorded_parts
    current = source_context(ws, snapshot=snapshot)
    if not draft.get('snapshot_digest') or not ('shown_files' in draft or 'bound_source_files' in draft):
        # An old receipt holds the digest of the whole files alone (parts came later, J11-B15).
        return {'ok': draft.get('context_digest') in (current['digest'], context_digest(current['files'])),
                'binding': 'legacy_current_packet', 'file_count': len(current['files']), 'current_packet_differs': False}
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
    # The parts of files over their limit that the author was shown, rebuilt from the file and the recorded lines: they
    # are part of the digest too (journey J11-B15).
    saved = draft.get('shown_excerpts') or {}
    try:
        if not isinstance(saved, dict):
            raise WorkspaceError('invalid')
        parts = recorded_parts(snapshot, {p for p, e in snapshot['manifest'].items() if e['visibility'] == 'model'}, saved)
    except WorkspaceError:
        return {'ok': False, 'binding': 'retained_digest_mismatch', 'file_count': len(files)}
    # Older packets could retain literal CRLF; new ones normalize it. Both
    # must hash to the originally recorded digest, never a replacement digest.
    for normalization, view in [('literal', files), ('lf', {p: s.replace('\r\n', '\n') for p, s in files.items()})]:
        digest = context_digest(view, parts)
        if digest == draft.get('context_digest'):
            return {'ok': True, 'binding': ('frozen_source_bindings' if 'bound_source_files' in draft else 'frozen_shown_files'), 'normalization': normalization,
                    'file_count': len(files), 'context_digest': digest,
                    'current_packet_differs': current['digest'] != digest, **({'parts_count': len(parts)} if parts else {})}
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
        owner_options=dict(check_options) or {'timeout_s':owner_check_limit(acceptance_bundle)}
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
    # "unchecked": nothing could check it yet; unchanged, checking it again only repeats that (journey J11-B11).
    if (verification.get('status') not in ('self_checks_passed', 'acceptance_passed', 'unchecked')
            or verification.get('snapshot_digest') != context['snapshot_digest']
            or verification.get('acceptance_bundle') != {name: hashlib.sha256(data).hexdigest()
                                                         for name, data in _acceptance_files(ws, milestone['id']).items()}):
        return None
    checkpoint()
    result = {'draft': draft['id'], 'milestone': milestone['id'], 'verification': verification, 'unchanged': True,
              'summary': f"Draft “{draft.get('title') or draft['id']}” is unchanged since its last check. Nothing applied."}
    if verification['status'] == 'acceptance_passed':
        with ws._lock:
            _apply_if_current(ws, draft, milestone, contract, status(ws), verification, result)
    elif verification['status'] == 'unchecked':
        result['summary'] = (f"Draft “{draft.get('title') or draft['id']}” waits for you: nothing can check it until "
                             f"“{milestone.get('title') or milestone['id']}” has acceptance checks. Propose them in Goals & plan.")
    else:
        # Titles, not ids (journey J2-F26: "d2026092813431050d4 … needs acceptance checks for b3a755fd75179-s1").
        result['summary'] = (f"Draft “{draft.get('title') or draft['id']}” passed its own checks and waits for you. "
                             f"Applying it automatically needs acceptance checks for “{milestone.get('title') or milestone['id']}”: "
                             f"propose them in Goals & plan.")
    return result


def _within_scope(path, paths):
    """Whether a (safe, workspace-relative) path is inside the grant; "." grants the whole folder (J11-B1)."""
    return any(prefix.rstrip('/') == '.' or path == prefix.rstrip('/') or path.startswith(prefix.rstrip('/') + '/')
               for prefix in paths)


def verification_inconclusive(verification):
    """Recognize new and legacy time-censored checks without rewriting receipts."""
    value=verification or {}
    if value.get('status')=='inconclusive':
        return True
    return bool(value.get('status')=='failed' and not value.get('detail') and any(
        (value.get(key) or {}).get('status')=='timeout' for key in ('project_checks','acceptance')))


def _ordinary_revision_lineage(ws, drafts, snapshot, milestone):
    """A normal build must not bypass the focused revision lineage guard."""
    # Only drafts from ordinary author attempts have that lineage. A correction's draft has no author request key,
    # and the guard failed on it with "Invalid author request key" (journey J2-B7); the allowance still applies.
    # The candidate is the one the build would revise, by the one rule (review of J11-G37).
    revision=next((d for d in revisable_candidates(ws,drafts,milestone,snapshot) if d.get('author_request_key')),None)
    if revision:
        from runesmith.app.author_revisions import _lineage
        _lineage(ws,revision)


def build_step(ws, router, *, checkpoint=lambda: None, author_only=False, milestone_id=None):
    """One author attempt and bounded checks. No unattended repeated blind retries.

    The first ready milestone that can move is built. One that needs the owner or a late answer (its tries used up,
    files applied and awaiting review, an inconclusive check, a draft waiting for checks) no longer holds back the
    others: in journey J11-B6, one step's used-up tries left five independent milestones idle for 1 h 39 min. Still at
    most one author call per step. `milestone_id` builds that milestone only (the owner's choice).
    """
    if type(author_only) is not bool:
        raise WorkspaceError('Author-only selection must be boolean.')
    if milestone_id is not None and (not isinstance(milestone_id, str) or not milestone_id):
        raise WorkspaceError('Choose a milestone by its id.')
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: no build or model call.'}
    from runesmith.app.author_recovery import pending_authors, resume_author
    saved = pending_authors(ws, milestone=milestone_id)
    fetched = {}                        # milestone id -> what fetching its late answer said this round
    unknown = [row for row in saved if row.get('milestone') is None]
    resumable = [row for row in (unknown or saved) if row['can_resume']]
    # Journey J2-F12: an answer that arrived after the wait stopped every later round until the owner came back.
    # Fetching it is no new model call, so the round fetches it and checks it through the normal gates. Every
    # milestone's own late answer is fetched, not only the first one's: with two outstanding, a second that had
    # arrived was never fetched and both milestones waited for good (review of J11-B6). One whose milestone is
    # unknown is fetched alone and holds everything, as before.
    for ready in ([] if author_only else resumable[:1] if unknown else resumable):
        recovered = resume_author(ws, ready['id'], checkpoint=checkpoint)
        if recovered.get('already_used') or (not recovered.get('draft') and ready.get('milestone') is None):
            return recovered
        if recovered.get('draft'):
            draft = ws._draft(recovered['draft'])
            milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == draft.get('milestone')), None)
            if not milestone or not milestone_ready(ws.plan(), milestone):
                return recovered
            return _check_and_record(ws, draft, milestone, milestone_contract(ws, milestone), checkpoint=checkpoint)
        # Not arrived yet, or its job failed: that milestone rests this round, another may move (J11-B6).
        fetched[ready['milestone']] = recovered
    if fetched:
        saved = pending_authors(ws, milestone=milestone_id)
    expected = {row.get('milestone') for row in saved} | set(fetched)   # milestones a late answer holds back
    waiting = {'summary':'A late answer is still expected, so building waits for it and asks no model meanwhile.'}
    if None in expected:
        return waiting                  # an answer whose milestone is unknown holds everything, as before
    checkpoint()
    if not ws.plan():
        if saved:
            return waiting
        if author_only:
            raise WorkspaceError('Save a plan before requesting an author-only build.')
        plan = draft_plan(ws, router, checkpoint=checkpoint, automatic=True)
        return {'summary':f"Drafted plan v{plan['version']}; no files applied."}
    plan = ws.plan()
    if milestone_id is not None:
        chosen = next((m for m in plan.get('milestones', []) if m['id'] == milestone_id), None)
        if not chosen or not milestone_ready(plan, chosen):
            return {'summary':'That milestone cannot be built now: it is finished, dropped, or waits for another.',
                    'milestone':milestone_id}
        candidates = [chosen]
    else:
        candidates = ready_milestones(plan)
    if not candidates:
        return waiting if saved else {'summary':'No unfinished milestones. Review goals before starting another plan.'}
    snapshot = collect_snapshot(ws)
    context = source_context(ws)        # the folder's source, observed once: every candidate is decided from this reading
    if snapshot['digest'] != context['snapshot_digest']:
        snapshot = None                 # it changed between the two reads: no milestone gets a view of its own
    blocked = []
    for milestone in candidates:
        if milestone['id'] in expected:
            blocked.append((milestone, fetched.get(milestone['id']) or dict(waiting, milestone=milestone['id']),
                            'a late answer is still expected'))
            continue
        # The folder's source is the same for every milestone, but a file shown in parts is shown by the milestone's own
        # words (journey J11-B15), so each is judged by its own view of the one reading.
        result, reason = _build_milestone(ws, router, milestone,
                                          context if snapshot is None else milestone_view(ws, context, snapshot, milestone),
                                          checkpoint=checkpoint, author_only=author_only)
        if reason is None:
            return result
        blocked.append((milestone, result, reason))
    if len(blocked) == 1:
        return blocked[0][1]
    names = '; '.join(f"“{m.get('title') or m['id']}”: {reason}" for m, _, reason in blocked)
    result = {'summary':f'All {len(blocked)} ready milestones need you or a late answer. {names}.',
              'all_blocked':True, 'milestones_blocked':[m['id'] for m, _, _ in blocked]}
    used_up = next((r for _, r, _ in blocked if r.get('replan_needed')), None)
    if used_up:                         # a smaller-steps proposal for the first one whose tries are used up, as before
        result.update(replan_needed=True, milestone=used_up['milestone'])
    return result


def _used_up_cause(ws, contract, context):
    """Why the tries were used up, when it was a file no model can be shown (journey J11-B15, review of the 40,000-byte
    wall): every answer that edits it is refused, so smaller steps that edit it fail the same way. The summary and the
    breakdown packet say so, instead of only that the tries are gone."""
    from runesmith.app.source_focus import FOCUSED_FILE_BYTES
    newest = None
    for path in (ws.home / 'build-attempts').glob('*.json'):
        row = _read_json(path, {})
        feedback = row.get('feedback') if isinstance(row, dict) and isinstance(row.get('feedback'), dict) else {}
        if (isinstance(row, dict) and row.get('contract') == contract and row.get('snapshot_digest') == context['snapshot_digest']
                and row.get('state') == 'failed' and isinstance(feedback.get('not_shown'), str)
                and feedback.get('reason') in ('file_limit', 'not_utf8', 'budget_together')):
            key = (str(row.get('utc') or ''), path.stat().st_mtime_ns)
            if newest is None or key > newest[0]:
                newest = (key, feedback['not_shown'], feedback['reason'])
    if newest is None:
        return ''
    why = {'file_limit': f'is too large to show a model ({FOCUSED_FILE_BYTES:,} bytes at most)',
           'not_utf8': 'is not UTF-8 text, so no model can be shown it',
           'budget_together': 'does not fit the source budget together with the other files this step needs'}[newest[2]]
    return f'{newest[1]} {why}, so every answer that edits it is refused; smaller steps that edit it fail the same way: split it first.'


def _context_gap(ws, contract, context):
    """The file this milestone's latest answer could not change because the model was not shown it, when it still
    is not shown; else None (journey J11-B15)."""
    rows = []
    for path in (ws.home / 'build-attempts').glob('*.json'):
        row = _read_json(path, {})
        if isinstance(row, dict) and row.get('contract') == contract and row.get('snapshot_digest') == context['snapshot_digest']:
            rows.append((str(row.get('utc') or ''), path.stat().st_mtime_ns, row))
    if not rows:
        return None
    latest = max(rows, key=lambda r: (r[0], r[1]))[2]
    feedback = latest.get('feedback') if isinstance(latest.get('feedback'), dict) else {}
    path = feedback.get('not_shown')
    if (latest.get('state') == 'context_gap' and isinstance(path, str) and path not in context['files']
            and path not in (context.get('excerpts') or {})):
        return path
    return None


def _build_milestone(ws, router, milestone, context, *, checkpoint, author_only):
    """(result, None) after building or checking this milestone, or (result, reason) when it needs the owner."""
    contract = milestone_contract(ws, milestone)
    previous = [d for d in ws.drafts() if d.get('contract') == contract]
    if any(d.get('state') == 'applied' for d in previous):
        # Journey J11-F24: the owner reopened a milestone whose draft was applied, and nothing said what to do.
        return {'summary':'A draft of this milestone is already applied, so Runesmith does not build it again. To have '
                          'it built anew, undo that draft on Work; otherwise mark the milestone done.',
                'milestone':milestone['id']}, \
            'a draft of it is already applied (undo it on Work to build it anew)'
    inconclusive=next((d for d in previous if d.get('state') in ('waiting','needs_revision')
        and d.get('snapshot_digest')==context['snapshot_digest']
        and d.get('public_acceptance_digest')==expectation_digest(ws,milestone['id'])
        and verification_inconclusive(d.get('verification'))),None)
    if inconclusive:
        return {'summary':'Saved candidate has an inconclusive check. Explicitly recheck it without inference; no new author call or automatic check retry.',
                'draft':inconclusive['id'],'milestone':milestone['id'],'verification_required':True}, \
            'an inconclusive check to recheck'
    pending = next((d for d in previous if d.get('state') == 'waiting' and d.get('snapshot_digest') == context['snapshot_digest']
                  and d.get('context_digest') == context['digest']
                  and d.get('public_acceptance_digest') == expectation_digest(ws,milestone['id'])), None)
    gap = None if pending else _context_gap(ws, contract, context)      # a draft that waits needs no new call (J11-B15 review)
    if gap:
        # The last answer edited a file the model was not shown, and it still is not: a new call would fail the same
        # way, and such a refusal uses up no try, so the milestone waits for the owner (journey J11-B15).
        return {'summary': f"{gap} is not shown to the models, so builds of this milestone cannot change it. Prioritize "
                           f"{gap} under Goals & plan, Author context.", 'milestone': milestone['id']}, \
            f'{gap} is not shown to the models (prioritize it under Author context)'
    try:
        allowance = ordinary_allowance(ws, contract, context['snapshot_digest'])
    except WorkspaceError as error:
        return {'summary':str(error), 'allowance_blocked':True, 'milestone':milestone['id']}, str(error)[:120]
    scope = allowance['scope']
    if not pending:
        try:_ordinary_revision_lineage(ws,previous,context['snapshot_digest'],milestone)
        except (WorkspaceError,ValueError,KeyError,TypeError,OSError) as error:
            return {'summary':str(error),'allowance_blocked':True,'milestone':milestone['id']}, str(error)[:120]
    if pending is not None and (unchanged := _unchanged_verdict(ws, pending, milestone, contract, context, checkpoint)):
        return unchanged, (None if unchanged.get('advanced') else 'a draft waits for you')
    if not pending and not allowance['remaining']:
        cause = _used_up_cause(ws, contract, context)
        return {'summary':'Ordinary author allowance exhausted on this source and milestone. Review retained evidence; changing feedback does not grant more calls.'
                          + (' The cause: ' + cause if cause else ''),
                'replan_needed':True,'milestone':milestone['id'],**({'cause':cause} if cause else {})}, \
            'its three tries are used up' + (' (' + cause + ')' if cause else '')
    unshowable = None if pending else focus_problem(context)
    if unshowable:
        # A prioritized path is gone or hidden: no call can be made, and recording one as a failed try used up every
        # milestone's three with no model asked (journey J11-B15 review). It waits for the owner; after the exhausted
        # verdict above, which still asks for smaller steps.
        return {'summary': 'Selected author source cannot fit or is unavailable: ' + unshowable, 'milestone': milestone['id']}, \
            ', '.join(focus_missing(context)) + ' is prioritized but not a file models can be shown (see Author context)'
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
            from runesmith.app.planner import nothing_ran, settled_state
            state=('uncertain' if remote.get('unresolved') else 'transport_failed' if nothing_ran(error)
                   else settled_state(error))                                                  # J11-B15
            _write_json(attempt_path,dict(attempt,state=state,
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
                'summary':f"Draft {draft['id']} retained for review. No checks, apply or follow-on work; existing checks, if any, are unchanged."}, None
    result = _check_and_record(ws, draft, milestone, contract, checkpoint=checkpoint)
    if (pending is not None and not result.get('advanced')
            and (result.get('verification') or {}).get('status') in ('unchecked', 'self_checks_passed')):
        # A saved draft checked again (no model call) that only waits for checks or for you: the next milestone
        # may build meanwhile (journey J11-B11: Styles' draft held every build, so Runes light, with approved
        # checks, never ran). A draft whose checks now fail is reported as before (review of batch J).
        return result, 'a draft waits for you'
    return result, None

def build_escalation_status(ws,milestone_id=None):
    """Describe the one-shot alternate-author escape after a bounded miss.

    This does not increase the ordinary three-attempt budget.  It exposes one
    separately receipted call after that budget is exhausted, under the same
    source snapshot, milestone contract, paths and acceptance gates.

    Of the milestones whose tries are used up it describes the first the one more try can be given to now, not simply
    the first: one that waits on a draft, an inconclusive check or a saved author answer held every other one back
    (review of batch EE: an unattended project's one more try never reached the milestones behind it). With
    `milestone_id` it describes that milestone, as the owner's setting asks for a particular one.
    """
    plan=ws.plan() or {};ready=ready_milestones(plan)
    if not ready:return None
    context=source_context(ws)
    held={}                                       # the drafts and receipts are read once for every milestone judged here
    def every_draft():
        if 'drafts' not in held:held['drafts']=ws.drafts()
        return held['drafts']

    def used_up(candidate):
        try:return not ordinary_allowance(ws,milestone_contract(ws,candidate),context['snapshot_digest'])['remaining']
        except WorkspaceError:return False
    def unescalated(candidate):
        try:return not ordinary_allowance(ws,milestone_contract(ws,candidate),context['snapshot_digest'])['escalations']
        except WorkspaceError:return False
    # The one more try belongs to the ready milestone whose tries are used up, not simply the first (J11-B6), and
    # to one that has not used its own yet (journey J2-F34: m8 had, and m9's was never offered).
    def spent():
        if 'spent' not in held:held['spent']=[m for m in ready if used_up(m)]
        return held['spent']
    escalations_of={}

    def describe(milestone):
        contract=milestone_contract(ws,milestone)
        try:
            allowance=ordinary_allowance(ws,contract,context['snapshot_digest'])
        except WorkspaceError as error:
            return {'eligible':False,'milestone':milestone['id'],'attempts':None,'used':None,
                    'reason':str(error),'allowance':{'known':False,'can_draft':False,'blockers':[str(error)]}}
        scope=allowance['scope'];escalations=allowance['escalations']
        escalations_of[milestone['id']]=escalations
        drafts=[d for d in every_draft() if d.get('contract')==contract]
        eligible=(ws.settings()['autonomy']!='observe' and not allowance['remaining']
                  and not escalations and not any(d.get('state') in ('waiting','applied') for d in drafts))
        matching=[d for d in drafts if d.get('snapshot_digest')==context['snapshot_digest']
                  and d.get('public_acceptance_digest')==expectation_digest(ws,milestone['id'])]
        waiting=[d for d in matching if d.get('state')=='waiting']
        own_digest=source_context(ws,milestone=milestone)['digest'] if waiting else None      # the view its own words give (J11-B15)
        reuse=next((d['id'] for d in waiting if d.get('context_digest')==own_digest),None)
        blockers=[]
        from runesmith.app.work_modes import guard_job
        try:guard_job(ws,'build')
        except WorkspaceError as error:blockers.append(str(error))
        if ws.settings()['autonomy']=='observe':blockers.append('Observe mode does not permit authoring.')
        if any(d.get('state')=='applied' for d in drafts):blockers.append('Applied files await acceptance or owner review.')
        if any(d.get('state') in ('waiting','needs_revision') and verification_inconclusive(d.get('verification')) for d in matching):
            blockers.append('A saved candidate has an inconclusive check. Recheck it explicitly without inference.')
        from runesmith.app.author_recovery import pending_authors
        if pending_authors(ws,milestone=milestone['id']):blockers.append('Recover or reconcile the saved author request before another call.')
        lineage_error=None
        if not reuse:
            try:_ordinary_revision_lineage(ws,drafts,context['snapshot_digest'],milestone)
            except (WorkspaceError,ValueError,KeyError,TypeError,OSError) as error:
                lineage_error=str(error);blockers.append(lineage_error)
        eligible=bool(eligible) and not blockers
        if not allowance['remaining'] and not reuse:blockers.append('Ordinary author allowance exhausted. Review saved candidates or an explicitly available continuation.')
        view=dict(allowance,known=True,reuse_draft=reuse,blockers=blockers,can_draft=not blockers)
        if lineage_error:
            view.update(known=False,remaining=None,recorded_attempts=allowance['used'])
        return {'eligible':eligible,'milestone':milestone['id'],'attempts':allowance['used'],
                'scope':scope,'used':bool(escalations),'receipt':escalations[-1].get('id') if escalations else None,
                'snapshot_digest':context['snapshot_digest'],'allowance':view,'kept_answer':None,
                'reason':('The three tries for this step did not produce a build that passed.'   # plain words (J2-F22)
                          if eligible else None)}

    if milestone_id is not None:
        milestone=next((m for m in ready if m['id']==milestone_id),None)
        if milestone is None:return None
        state=describe(milestone)
    else:
        state=None
        for candidate in [m for m in spent() if unescalated(m)] or spent()[:1] or ready[:1]:
            view=describe(candidate)
            state=state or view
            if view['eligible']:
                state=view;break
        milestone=next(m for m in ready if m['id']==state['milestone'])
    # The one more try's answer, refused by the host, is kept. A newer Runesmith may accept it: the owner can check
    # it again with no model call (journey J2-G1). Readmitting revises a checked candidate on this source.
    kept=None
    # Of every milestone whose tries are used up, not only the one the one more try belongs to now (review of
    # J2-F34: when it moved to the next milestone, the first one's kept answer disappeared).
    for candidate in [milestone]+([] if milestone_id is not None else [m for m in spent() if m is not milestone]):
        own=milestone_contract(ws,candidate)
        try:own_escalations=escalations_of[candidate['id']] if candidate['id'] in escalations_of else ordinary_allowance(ws,own,context['snapshot_digest'])['escalations']
        except WorkspaceError:continue
        revisable=bool(revisable_candidates(ws,every_draft(),candidate,context['snapshot_digest']))
        for row in own_escalations if revisable and ws.settings()['autonomy']!='observe' else []:
            receipt=_read_json(ws.home/'build-escalations'/(row['id']+'.json'),{})
            if row['state']=='failed' and (receipt.get('feedback') or {}).get('answer_receipt'):
                if not kept or str(receipt.get('utc') or '')>kept['utc']:
                    kept={'id':row['id'],'utc':str(receipt.get('utc') or ''),'error':str(receipt.get('error') or '')[:300],
                          'last_recheck':receipt.get('last_recheck'),'milestone':candidate['id']}
    return dict(state,kept_answer=kept) if 'kept_answer' in state else state


def escalate_build(ws,router,*,checkpoint=lambda:None,milestone_id=None):
    """Run one alternate-author continuation after the ordinary cap (for `milestone_id` when the owner's setting names
    one, else for the first milestone it can be given to)."""
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: no escalation call or executable checks.'}
    state=build_escalation_status(ws,milestone_id)
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
        from runesmith.app.planner import nothing_ran, settled_state
        # No model answered: the one more try is not used up (journey J2-B9). Nor when it answered for a file it was
        # never shown (J11-B15).
        _write_json(path,dict(receipt,state='transport_failed' if nothing_ran(error) else settled_state(error),finished=_now(),
                              error=type(error).__name__+': '+str(error)[:300],feedback=getattr(error,'feedback',None),
                              remote_receipt=getattr(error,'remote_receipt',None)))
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
    contract=milestone_contract(ws,milestone);snapshot=collect_snapshot(ws)
    # Checked against the lines its own call was shown, never today's choice of parts (journey J11-B15).
    from runesmith.app.author_recovery import answer_packet, replay_context
    packet=answer_packet(ws,answer_rel)
    context=replay_context(ws,snapshot,packet.get('excerpts'))
    allowance=ordinary_allowance(ws,contract,context['snapshot_digest'])
    if contract!=receipt.get('contract') or not any(row['id']==key for row in allowance['escalations']):
        raise WorkspaceError('Source or milestone changed; the retained answer cannot be replayed.')
    # The candidate by the one rule the prompt and the packet use (review of J11-G37: this chose by an older one).
    revision=next(iter(revisable_candidates(ws,ws.drafts(),milestone,context['snapshot_digest'])),None)
    if not revision:raise WorkspaceError('The answer has no matching frozen candidate to revise.')
    from runesmith.app.planner import admit_revision_answer
    try:
        files=admit_revision_answer(ws,context,saved['answer'].get('files'),revision,
                                    candidate_view=packet.get('candidate_view'))
    except Exception as error:     # the owner sees when it was checked again and why it still does not fit (J2-F24)
        _write_json(path,dict(receipt,last_recheck={'utc':_now(),'error':str(error)[:300]}))
        raise
    draft=ws.save_draft(title=str(saved['answer'].get('title') or milestone['title']),
                        why=str(saved['answer'].get('why') or ''),files=files,
                        drafted_by=saved.get('author'),milestone=milestone['id'])
    exposure_rel=saved.get('memory_exposure');exposure=_read_json(ws.home/str(exposure_rel or ''),{})
    ws._save_draft_state(draft,'waiting',contract=contract,context_digest=context['digest'],
                         public_acceptance_digest=saved.get('public_acceptance_digest'),
                         snapshot_digest=context['snapshot_digest'],**shown_view(context),
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


def readmit_refused_answer(ws, attempt_id, *, checkpoint=lambda: None):
    """Check a refused answer again with no model call, then the ordinary verification/apply gates."""
    if ws.settings()['autonomy'] == 'observe':
        return {'summary':'Observe mode: no answer admission or executable checks.'}
    from runesmith.app.build_corrections import readmit_kept_answer
    draft=readmit_kept_answer(ws,attempt_id,checkpoint=checkpoint)
    milestone=next((row for row in (ws.plan() or {}).get('milestones',[])
                    if row.get('id')==draft.get('milestone')),None)
    if not milestone or not milestone_ready(ws.plan(),milestone):
        return {'summary':'The kept answer fits now, but its milestone is no longer ready; the draft is kept, no checks run.',
                'draft':draft['id']}
    return _check_and_record(ws,draft,milestone,milestone_contract(ws,milestone),checkpoint=checkpoint)


def supplement_status(ws, draft):
    current=expectation_digest(ws,draft['milestone'])
    used=any(row.get('milestone')==draft['milestone'] and row.get('state')!='context_gap'    # J11-B15: no answer, no use
             for row in (_read_json(p,{}) for p in (ws.home/'build-supplements').glob('*.json')))
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
        from runesmith.app.planner import settled_state
        _write_json(path,dict(receipt,state=settled_state(error),finished=_now(),error=str(error)[:500]))
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
            applied = ws.apply_draft(draft['id'], by='build')
            if applied['ok']:
                ws.update_milestone(milestone['id'], {'status':'done'}, log=False)
                ws._save_draft_state(ws._draft(draft['id']), 'applied', applied_by='delegated_build',
                                     grant=grant['grant'])
                ws.ledger.append('build.advanced', {'draft':draft['id'], 'milestone':milestone['id'],
                    'grant':grant['grant'], 'acceptance_sha256':verification['acceptance_sha256']})
                oracle = verification.get('acceptance') or {}
                ran = int(oracle.get('ran') or 0)
                skipped = int(oracle.get('skipped') or 0)
                passed = max(0, ran - skipped - int(oracle.get('failures') or 0) - int(oracle.get('errors') or 0))
                runesmith_md.build_done(ws, milestone['id'], draft, applied['files'], passed, ran - skipped)
                result.update(advanced=True, summary=f"Applied {draft['id']}; acceptance passed; {milestone['id']} complete.")
            else:
                result['summary'] = applied['detail']
