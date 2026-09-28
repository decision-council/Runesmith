"""Owner acceptance checks that a non-programmer can approve (gap G1, out-of-box journey R1, 2026-09-27).

Applying a checked build automatically needs the owner's own acceptance checks for its milestone: a unittest file at
``<home>/acceptance/<milestone>.py`` that runs, frozen, against a clean copy of every candidate. Few owners can write
one. So Runesmith asks a model, in a call separate from any build author call, to propose black-box checks from the
milestone's own words, with one plain sentence per check. The owner reads the sentences (and may read the code) and
approves or discards them. Approval freezes the file. Its provenance is recorded as model-proposed and owner-approved,
never owner-written. Build authors are never shown the file, only public criteria.

The caller owns the Workspace instance lock, as with other Studio mutations.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from runesmith import atomic
from runesmith.app import acceptance_examples
from runesmith.app.acceptance_contracts import expectations, publish_expectations
from runesmith.app.building import _run_checks
from runesmith.app.planner import PlannerUnavailable, SkippedByOwner, source_context, why_no_answer
from runesmith.app.snapshots import SnapshotUnsupported, collect_snapshot
from runesmith.instruments import LenientSchema
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

SCHEMA = LenientSchema({'type': 'object', 'properties': {   # code inside: sent as text
    'checks': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': {'type': 'object', 'properties': {
        'test': {'type': 'string'}, 'says': {'type': 'string'}}, 'required': ['test', 'says'], 'additionalProperties': False}},
    'assumes': {'type': 'array', 'maxItems': 8, 'items': {'type': 'string'}},
    'code': {'type': 'string'}}, 'required': ['checks', 'assumes', 'code'], 'additionalProperties': False})

SYSTEM = ("You are Runesmith's acceptance-check instrument. You write the owner's checks for one milestone; "
          "you do not implement it. Return JSON only.")
TASK = ("Write the owner's acceptance checks for ONE milestone of this project. They decide whether the milestone is "
        "done, so check the behaviour the milestone text describes, from the outside: prefer running the command the "
        "milestone documents (subprocess with sys.executable and cwd=os.getcwd(), which is the project folder when the "
        "checks run) or the public functions the milestone names. Do not rely on private names the milestone does not "
        "mention, and do not require more than it says. Use Python unittest only (no pytest), temporary directories for "
        "any files, no network and deterministic data. Keep it small: 2 to 8 tests, each checking one thing a person "
        "would recognise. For each test give its method name and one plain sentence a non-programmer understands, and make "
        "the sentence say exactly what the code checks, no more: any exact word, layout, name or value a check requires "
        "must appear in its sentence, because the sentences are all a builder is shown. Do not require an exact output "
        "layout, wording or file name unless the milestone states it: check the saved data, the exit status, or that the "
        "key facts (numbers, titles) appear. When the milestone promises behaviour under a failure (an interruption, "
        "damaged or missing input), the test must cause that failure itself; a check that would also pass on a project "
        "that ignores the failure checks nothing. When it asks for a clear message, check that the message is shown and "
        "that the program did not stop with a Python traceback. In \"assumes\", list in plain words every exact "
        "format, name or behaviour your checks rely on that the milestone text does not state (an empty list means "
        "none). The feature may not exist yet: do not implement it. Return JSON with \"checks\", \"assumes\" and "
        "\"code\" (the complete file).")
REVISE = ("Runesmith tried your checks once on a copy of the project as it is today, and read them. {finding} Revise them "
          "so that each check fails on a project that lacks what this milestone adds, passes once it is built, and says "
          "in its sentence every exact text it requires. If the project already does everything the milestone says, "
          "return the same checks and say so in \"assumes\". Same JSON shape.")
FINDINGS = {'passes_now': 'They all passed, although this milestone is not built yet, so they may not test what it adds.',
            'broken': 'They could not run: no test ran, or they did not finish in time.'}
NETWORK_MODULES = {'socket', 'ssl', 'urllib', 'http', 'requests', 'ftplib', 'smtplib', 'telnetlib', 'asyncio'}
MAX_CODE = 20000
# Room for the answer: a checks file is a few thousand characters. Keeping prompt + answer small lets the request fit
# free per-minute windows (Groq's free gpt-oss-120b allows 8,000 tokens a minute; 6,000 here made it impossible).
ANSWER_TOKENS = 3000
# Assertion methods and how many leading arguments state the requirement (the rest are messages).
ASSERT_ARGS = {'assertTrue': 1, 'assertFalse': 1, 'assertIn': 2, 'assertNotIn': 2, 'assertEqual': 2, 'assertNotEqual': 2,
               'assertRegex': 2, 'assertNotRegex': 2, 'assertCountEqual': 2, 'assertListEqual': 2,
               'assertMultiLineEqual': 2, 'assertStartsWith': 2, 'assertEndsWith': 2}
# How the model is asked. 'examples' (the default since 2026-09-28): the model describes examples as data and
# Runesmith's trusted template writes the code (acceptance_examples.py); free models' own test code rejected correct
# builds in 16 of 17 overnight trials. 'code': the model writes the unittest file itself.
STYLE = 'examples'
SCHEMAS = {'code': SCHEMA, 'examples': acceptance_examples.SCHEMA}
MILESTONE_ID = re.compile(r'[A-Za-z0-9_-]+')
CRITERION_ID = re.compile(r'[A-Za-z0-9_.-]{1,100}')


def _folder(ws):
    return ws.home / 'acceptance-proposals'


def _record_path(ws, milestone_id):
    if not isinstance(milestone_id, str) or not MILESTONE_ID.fullmatch(milestone_id):
        raise WorkspaceError('Invalid milestone ID.')
    return _folder(ws) / (milestone_id + '.json')


def _milestone(ws, milestone_id):
    milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m.get('id') == milestone_id), None)
    if milestone is None:
        raise WorkspaceError('Unknown milestone.')
    return milestone


def acceptance_file(ws, milestone_id):
    _record_path(ws, milestone_id)
    return ws.home / 'acceptance' / (milestone_id + '.py')


def _literals(root):
    """String constants an assertion compares against: direct operands, `in`/`==` operands, startswith/endswith."""
    if isinstance(root, (ast.List, ast.Tuple, ast.Set)):
        yield from (e for e in root.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    for node in ast.walk(root):
        if node is root and isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node
        elif isinstance(node, ast.Compare):
            yield from (s for s in (node.left, *node.comparators) if isinstance(s, ast.Constant) and isinstance(s.value, str))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('startswith', 'endswith'):
            for arg in node.args:
                elements = arg.elts if isinstance(arg, ast.Tuple) else [arg]
                yield from (e for e in elements if isinstance(e, ast.Constant) and isinstance(e.value, str))


def required_texts(tree, tests) -> dict[str, list[str]]:
    """Per test: the exact texts its assertions require, apart from its own input data and its failure messages.

    A weak model may promise one thing in a sentence and require an exact layout or word in the code. The sentence is
    all an owner reads and all a builder is shown, so Runesmith finds such texts itself instead of trusting the model.
    """
    required, marked = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in tests:
            found = []
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr in ASSERT_ARGS:
                    roots = inner.args[:ASSERT_ARGS[inner.func.attr]]
                elif isinstance(inner, ast.Assert):
                    roots = [inner.test]
                else:
                    continue
                for root in roots:
                    found.extend(_literals(root))
            required[node.name] = found
            marked |= {id(n) for n in found}
    docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}
    inputs = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and id(n) not in marked and id(n) not in docstrings]
    return {name: sorted({n.value.strip() for n in nodes if len(n.value.strip()) >= 2
                          and not any(n.value.strip() in data for data in inputs)})
            for name, nodes in required.items()}


def validate(data: Any) -> dict[str, Any]:
    """The proposal as stored, or a WorkspaceError naming what is wrong with it."""
    if not isinstance(data, dict) or not isinstance(data.get('checks'), list) or not isinstance(data.get('code'), str):
        raise WorkspaceError('A proposal needs "checks" and "code".')
    code = data['code'].replace('\r\n', '\n')
    if not code.strip() or len(code) > MAX_CODE:
        raise WorkspaceError(f'The checks file must contain 1-{MAX_CODE} characters.')
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise WorkspaceError(f'The checks file is not valid Python: line {error.lineno}: {error.msg}') from None
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split('.')[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
    if imported & NETWORK_MODULES:
        raise WorkspaceError('Acceptance checks may not use the network: ' + ', '.join(sorted(imported & NETWORK_MODULES)))
    if 'unittest' not in imported or 'pytest' in imported:
        raise WorkspaceError('Acceptance checks must use unittest, not pytest.')
    tests = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(
                (isinstance(b, ast.Attribute) and b.attr == 'TestCase') or (isinstance(b, ast.Name) and b.id == 'TestCase')
                for b in node.bases):
            tests |= {f.name for f in node.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test')}
    if not tests:
        raise WorkspaceError('The checks file defines no unittest test methods.')
    texts = required_texts(tree, tests)
    checks = []
    for row in data['checks']:
        if not isinstance(row, dict) or not isinstance(row.get('test'), str) or not isinstance(row.get('says'), str):
            raise WorkspaceError('Each check needs its test name and one plain sentence.')
        says = row['says'].strip()
        if row['test'] not in tests:
            raise WorkspaceError(f'"{row["test"]}" is not a test in the checks file.')
        if not says or len(says) > 300:
            raise WorkspaceError('Each plain sentence needs 1-300 characters.')
        check = {'test': row['test'], 'says': says}
        if unstated := [text for text in texts.get(row['test'], []) if text not in says]:
            check['unstated'] = unstated                # required by the code, not said in the sentence
        checks.append(check)
    if not 1 <= len(checks) <= 8:
        raise WorkspaceError('Propose 1-8 checks.')
    if missing := sorted(tests - {c['test'] for c in checks}):
        raise WorkspaceError('Every test needs a plain sentence; missing: ' + ', '.join(missing))
    assumes = data.get('assumes', [])
    if not isinstance(assumes, list) or len(assumes) > 8 or any(not isinstance(a, str) or not a.strip() or len(a) > 300 for a in assumes):
        raise WorkspaceError('List 0-8 assumptions, each 1-300 characters.')
    return {'checks': checks, 'assumes': [a.strip() for a in assumes], 'code': code,
            'code_sha256': hashlib.sha256(code.encode('utf-8')).hexdigest()}


def packet(ws, milestone_id, style='code') -> dict[str, Any]:
    milestone = _milestone(ws, milestone_id)
    return {'task': acceptance_examples.TASK if style == 'examples' else TASK,
            'milestone': {k: milestone.get(k) for k in ('id', 'title', 'detail', 'done_when', 'track')},
            'brief': ws.brief().get('text', ''),
            'public_acceptance': expectations(ws, milestone_id),
            'source_context': source_context(ws, limit=16000),
            # The documents the owner chose to share with models (Goals & plan). Code goes in source_context; documents
            # never do, so without this a Checker could not see a single page of a handbook it is asked to check.
            'documents': ws.blueprint_text(),
            'note': 'Each example runs in its own fresh copy of the project folder, with the current directory set to it.'
            if style == 'examples' else
            'Owner acceptance runs on a clean copy of the project folder, with the current directory set to it.'}


def _clean(answer, style, data) -> dict[str, Any]:
    """The proposal as stored, from the model's answer in either style; a WorkspaceError says what is wrong."""
    if style != 'examples':
        return validate(answer)
    milestone = data['milestone']
    shaped = acceptance_examples.validate_examples(
        answer, ' '.join(str(milestone.get(k) or '') for k in ('title', 'detail', 'done_when')),
        json.dumps(data.get('source_context'), ensure_ascii=False) + '\n' + str(data.get('documents') or ''))
    checked = validate({'checks': [{'test': c['test'], 'says': c['says']} for c in shaped['checks']],
                        'assumes': [], 'code': shaped['code']})
    checks = [{'test': c['test'], 'says': c['says'], 'exact': e['exact']} for c, e in zip(checked['checks'], shaped['checks'])]
    return dict(shaped, checks=checks, code_sha256=checked['code_sha256'])


# A revision or retry request carries the first answer too. Its source excerpt is smaller, so the request still fits
# a free per-minute window (Groq's free gpt-oss-120b: 8,000 tokens a minute, prompt and answer room together).
LEAN_SOURCE = 6000


def _lean(ws, data):
    return dict(data, source_context=source_context(ws, limit=LEAN_SOURCE))


def _bounded(answer, limit=40000):
    text = json.dumps(answer, ensure_ascii=False)
    return answer if len(text) <= limit else {'truncated': text[:limit]}


def _ask(router, request, style, key):
    """One acceptance call; a PlannerUnavailable or SkippedByOwner says in plain words why there is no answer."""
    try:
        out = router.call('acceptance', prompt=json.dumps(request, sort_keys=True, ensure_ascii=False), system=SYSTEM,
                          schema=SCHEMAS[style], max_tokens=ANSWER_TOKENS, key=key)
    except KeyError as error:
        raise PlannerUnavailable('no model is set up for planning or checking: add one under Thinking power') from error
    except Exception as error:
        raise PlannerUnavailable('no acceptance checks: ' + why_no_answer(error)) from error
    if isinstance(out.data, dict) and out.data.get('skipped_by_owner'):
        raise SkippedByOwner('you skipped the request, so nothing changed')
    if not out.ok and out.error_kind == "config":
        raise PlannerUnavailable(out.error or "the model service refused this request")
    if not out.ok:
        raise PlannerUnavailable(f"the model's answer was not usable: {(out.error or 'no JSON')[:200]}")
    return out


def status(ws) -> dict[str, Any]:
    """Per milestone: the approved checks (with provenance) and the newest proposal waiting for the owner."""
    out = {}
    for milestone in (ws.plan() or {}).get('milestones', []):
        mid = milestone.get('id')
        if not isinstance(mid, str) or not MILESTONE_ID.fullmatch(mid):
            continue
        record = _read_json(_record_path(ws, mid), {'proposals': []})
        file = acceptance_file(ws, mid)
        approved = None
        if file.is_file():
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            match = next((p for p in record['proposals'] if p.get('state') == 'approved' and p.get('file_sha256') == digest), None)
            approved = ({'provenance': 'model-proposed, owner-approved', 'proposed_by': match.get('drafted_by'),
                         'approved_utc': match.get('approved_utc'), 'checks': match['checks'], 'sha256': digest}
                        if match else {'provenance': 'owner file', 'checks': None, 'sha256': digest})
        waiting = next((p for p in reversed(record['proposals']) if p.get('state') == 'proposed'), None)
        if approved or waiting:
            out[mid] = {'approved': approved,
                        'proposal': {k: waiting.get(k) for k in ('id', 'checks', 'assumes', 'dry_run', 'revision', 'code',
                                                                      'drafted_by', 'utc', 'dropped', 'not_checked', 'style')}
                        if waiting else None}
    return out


def propose(ws, router, milestone_id, *, checkpoint=lambda: None, style=None) -> dict[str, Any]:
    style = style or STYLE
    if style not in SCHEMAS:
        raise WorkspaceError('Unknown way of asking for checks.')
    milestone = _milestone(ws, milestone_id)
    if milestone.get('status') not in ('open', 'doing'):
        raise WorkspaceError('Propose acceptance checks for an unfinished milestone.')
    if ws.settings().get('autonomy') == 'observe':
        from runesmith.app.workspace import OBSERVE_NO_CALLS
        raise WorkspaceError(OBSERVE_NO_CALLS)
    data = packet(ws, milestone_id, style)
    text = json.dumps(data, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    path = _record_path(ws, milestone_id)
    record = _read_json(path, {'milestone': milestone_id, 'proposals': []})
    for old in record['proposals']:
        if old.get('input_sha256') == digest and old.get('state') == 'proposed':
            return old                                  # an unchanged request reuses the waiting answer
    checkpoint()
    key = 'a' + uuid.uuid4().hex[:12]
    out = _ask(router, data, style, 'acceptance-' + key)
    checkpoint()
    drafted_by = out.receipt.get('answered_by') or out.receipt.get('model')
    first_answer = out.data
    try:
        clean = _clean(out.data, style, data)
    except WorkspaceError as error:
        if style != 'examples':
            raise
        # A weak model's answer may break a rule of the examples format; it is told which, once.
        request = dict(_lean(ws, data), revise=acceptance_examples.UNUSABLE.format(error=str(error)),
                       your_first_answer=out.data)
        try:
            out = _ask(router, request, style, 'acceptance-' + key + '-retry')
        except PlannerUnavailable as again:
            raise PlannerUnavailable(f'the first answer broke a rule ({str(error)[:200]}), and asking again failed: {again}') from again
        checkpoint()
        try:
            clean = _clean(out.data, style, data)
        except WorkspaceError as again:
            raise WorkspaceError(f'Both answers broke a rule of the examples format. First: {str(error)[:200]} '
                                 f'Then: {str(again)[:200]}') from None
        clean['revision'] = {'after': 'unusable', 'error': str(error)[:300], 'first_answer': _bounded(first_answer)}
        drafted_by = out.receipt.get('answered_by') or out.receipt.get('model') or drafted_by
        clean['dry_run'] = dry_run(ws, clean['code'], runs_project_code=_runs_project_code(clean))
        _mark_passing_today(clean)
    else:
        clean['dry_run'] = dry_run(ws, clean['code'], runs_project_code=_runs_project_code(clean))
        _mark_passing_today(clean)
        if findings(clean):
            clean, drafted_by = _revise_once(ws, router, data, clean, key, drafted_by, checkpoint,
                                             style=style, first_answer=out.data)
    if style == 'examples':
        clean.setdefault('answer', _bounded(out.data))     # the model's own words, kept for review and re-scoring
    proposal = dict(clean, id=key, state='proposed', utc=_now(), milestone=milestone_id, input_sha256=digest,
                    drafted_by=drafted_by)
    record = _read_json(path, {'milestone': milestone_id, 'proposals': []})
    record['proposals'] = (record['proposals'] + [proposal])[-10:]
    _write_json(path, record)
    ws.ledger.append('acceptance.proposed', {'milestone': milestone_id, 'proposal': key, 'checks': len(clean['checks']),
                                             'code_sha256': clean['code_sha256'], 'proposed_by': proposal['drafted_by']})
    return proposal


def findings(proposal) -> list[str]:
    """What Runesmith itself found wrong with a proposal: its trial result, and texts its sentences do not say."""
    found = [FINDINGS[proposal['dry_run']['verdict']]] if proposal['dry_run']['verdict'] in FINDINGS else []
    for check in proposal['checks']:
        if check.get('unstated'):
            found.append(f"{check['test']} requires the exact text " + ', '.join(json.dumps(t, ensure_ascii=False)
                         for t in check['unstated']) + ', which its sentence does not say: put it in the sentence, '
                         'or stop requiring it.')
    return found


def _revise_once(ws, router, data, first, key, drafted_by, checkpoint, *, style='code', first_answer=None):
    """One more call, told what Runesmith found. The first proposal is kept (with its warnings) if this fails."""
    finding = first['dry_run']['verdict'] if first['dry_run']['verdict'] in FINDINGS else 'unstated_text'
    if style == 'examples':
        request = dict(_lean(ws, data), revise=acceptance_examples.REVISE.format(finding=' '.join(findings(first))),
                       your_first_proposal=first_answer)
    else:
        request = dict(data, revise=REVISE.format(finding=' '.join(findings(first))),
                       your_first_proposal={k: first[k] for k in ('checks', 'assumes', 'code')})
    checkpoint()
    try:
        out = router.call('acceptance', prompt=json.dumps(request, sort_keys=True, ensure_ascii=False), system=SYSTEM,
                          schema=SCHEMAS[style], max_tokens=ANSWER_TOKENS, key='acceptance-' + key + '-revise')
    except Exception as error:
        return dict(first, revision={'after': finding, 'error': str(error)[:300]}), drafted_by
    checkpoint()
    try:
        if not out.ok or not isinstance(out.data, dict) or out.data.get('skipped_by_owner'):
            raise WorkspaceError((out.error or 'no usable answer')[:200])
        revised = _clean(out.data, style, data)
    except WorkspaceError as error:
        return dict(first, revision={'after': finding, 'error': str(error)[:300]}), drafted_by
    revised['dry_run'] = dry_run(ws, revised['code'], runs_project_code=_runs_project_code(revised))
    _mark_passing_today(revised)
    revised['revision'] = {'after': finding, 'first_code_sha256': first['code_sha256'],
                           'first_checks': first['checks']}
    if style == 'examples':
        revised['answer'] = _bounded(out.data)
        revised['revision']['first_answer'] = _bounded(first_answer)
    return revised, out.receipt.get('answered_by') or out.receipt.get('model') or drafted_by


def _runs_project_code(proposal) -> bool:
    """Whether trying these checks runs the project's own code. Checks on files only (documents) do not (J4-F13)."""
    return proposal.get('style') != 'examples' or any(e.get('steps') for e in proposal.get('examples', []))


def dry_run(ws, code: str, *, runs_project_code: bool = True) -> dict[str, Any]:
    """Run proposed checks once against a throwaway copy of the project as it is today.

    Checks that already pass on an unfinished milestone may not test what it adds; checks that cannot run at all are
    broken. Runs only when the owner allows checks to execute project code (the same switch as build checks).
    """
    settings = ws.settings()
    if settings.get('autonomy') == 'observe' or (runs_project_code and not settings.get('build_steps')):
        return {'verdict': 'not_run', 'why': 'Checking drafts is off, so the checks were not tried.'}
    try:
        snapshot = collect_snapshot(ws)
    except SnapshotUnsupported as error:
        return {'verdict': 'not_run', 'why': f'The project could not be copied for a trial: {error}'}
    folder = _folder(ws) / 'dry-runs'
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dry-', dir=folder, ignore_cleanup_errors=True) as directory:
        stage = Path(directory) / 'project'
        for rel, data in snapshot['files'].items():
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        stage.mkdir(parents=True, exist_ok=True)
        proposed = Path(directory) / 'proposed_acceptance.py'
        proposed.write_text(code, encoding='utf-8')
        result = _run_checks(stage, json.dumps([str(proposed)]), Path(directory) / 'dry-run.txt', timeout_s=120)
    ran = result.get('ran') or 0
    verdict = 'passes_now' if result['ok'] else 'fails_now' if result['status'] == 'failed' and ran else 'broken'
    out = {'verdict': verdict, 'ran': ran, 'failures': result.get('failures', 0), 'errors': result.get('errors', 0),
           'snapshot_digest': snapshot['digest'], 'utc': _now()}
    if verdict == 'fails_now' and not result.get('failure_details_omitted'):
        out['failing_tests'] = sorted({d['test'].rsplit('.', 1)[-1] for d in result.get('failure_details', [])})
    return out


def _mark_passing_today(proposal):
    """Name each check that already passed on today's project, though others failed (journey J1-G2).

    A check that passes before the milestone is built may pass for a reason the milestone does not change, for
    example a command the program does not have yet being refused. The owner sees it under that check.
    """
    failing = proposal.get('dry_run', {}).get('failing_tests')
    if failing is None:
        return proposal
    for check in proposal['checks']:
        if check['test'] not in failing:
            check['passes_today'] = True
    return proposal


# Appended to an approved file: a failing check is reported to the builder by its sentence, never by its assertion.
FOOTER = '''

import unittest as _acceptance_unittest
for _case in [v for v in list(globals().values()) if isinstance(v, type) and v.__module__ == __name__
              and issubclass(v, _acceptance_unittest.TestCase)]:
    _case.PUBLIC_CRITERIA = {_name: ["check." + _name] for _name in dir(_case) if _name.startswith("test")}
'''


def public_criteria(ws, milestone_id, proposal) -> list[dict[str, str]]:
    """The milestone's public expectations after approval: the owner's own criteria, plus these sentences."""
    kept = [c for c in (expectations(ws, milestone_id) or {}).get('criteria', [])
            if not c['id'].startswith(('check.', 'assumes.'))]
    ours = [{'id': 'check.' + c['test'], 'description': (c['says'] + (' Checked exactly: ' + c['exact'] if c.get('exact') else '')
                                                           + (' It requires the exact text: ' + ', '.join(
                 f'“{text}”' for text in c['unstated']) + '.' if c.get('unstated') else ''))[:1200]}
            for c in proposal['checks']]
    if proposal.get('assumes'):
        ours.append({'id': 'assumes.1', 'description': ('Also assumed: ' + '; '.join(proposal['assumes']))[:1200]})
    if any(not CRITERION_ID.fullmatch(c['id']) for c in ours):
        raise WorkspaceError('A test name is too long to become a public expectation; ask for the checks again.')
    if len(kept) + len(ours) > 20:
        raise WorkspaceError('This milestone has too many public expectations to add these checks; remove some first.')
    return kept + ours


def approve(ws, milestone_id, proposal_id, *, replace: bool = False, reason: str = '') -> dict[str, Any]:
    _milestone(ws, milestone_id)
    path = _record_path(ws, milestone_id)
    record = _read_json(path, {'proposals': []})
    proposal = next((p for p in record['proposals'] if p.get('id') == proposal_id), None)
    if proposal is None or proposal.get('state') != 'proposed':
        raise WorkspaceError('That proposal is not waiting for approval.')
    target = acceptance_file(ws, milestone_id)
    if target.is_file() and not replace:
        raise WorkspaceError('This milestone already has acceptance checks. Replacing them needs a reason.')
    if target.is_file() and not reason.strip():
        raise WorkspaceError('Say why the existing checks are replaced; the old file is kept.')
    criteria = public_criteria(ws, milestone_id, proposal)
    header = (f"# Owner acceptance for milestone {milestone_id}. Proposed by {proposal.get('drafted_by') or 'a model'} "
              f"({proposal['utc']}), approved by the owner ({_now()}).\n"
              "# Builds of this milestone are judged by this file; build authors never see it, only its sentences.\n")
    body = (header + proposal['code'].rstrip('\n') + '\n' + FOOTER).encode('utf-8')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        keep = target.with_name(f"{target.stem}.replaced-{uuid.uuid4().hex[:6]}.py.txt")
        keep.write_bytes(target.read_bytes())
    temporary = target.with_name(target.name + f'.{uuid.uuid4().hex[:6]}.tmp')
    temporary.write_bytes(body)
    atomic.replace(temporary, target)
    file_sha = hashlib.sha256(body).hexdigest()
    published = publish_expectations(ws, milestone_id, criteria, 'The owner approved these acceptance checks in plain words.',
                                     by='owner (approved acceptance checks)')
    proposal.update(state='approved', approved_utc=_now(), file_sha256=file_sha, replace_reason=reason.strip() or None,
                    expectations_version=published['version'])
    for other in record['proposals']:
        if other is not proposal and other.get('state') == 'proposed':
            other.update(state='superseded')
        elif other is not proposal and other.get('state') == 'approved':
            other.update(state='replaced', replaced_utc=_now())      # its file is kept as *.replaced-*.py.txt
    _write_json(path, record)
    ws.ledger.append('acceptance.approved', {'milestone': milestone_id, 'proposal': proposal_id, 'sha256': file_sha,
                                             'proposed_by': proposal.get('drafted_by'), 'replaced': bool(reason.strip())})
    return {'ok': True, 'sha256': file_sha, 'checks': proposal['checks']}


def discard(ws, milestone_id, proposal_id, *, reason: str = '') -> dict[str, Any]:
    path = _record_path(ws, milestone_id)
    record = _read_json(path, {'proposals': []})
    proposal = next((p for p in record['proposals'] if p.get('id') == proposal_id), None)
    if proposal is None or proposal.get('state') != 'proposed':
        raise WorkspaceError('That proposal is not waiting for approval.')
    proposal.update(state='discarded', discarded_utc=_now(), reason=reason.strip()[:1000] or None)
    _write_json(path, record)
    ws.ledger.append('acceptance.discarded', {'milestone': milestone_id, 'proposal': proposal_id})
    return {'ok': True}
