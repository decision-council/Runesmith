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
import uuid
from typing import Any

from runesmith import atomic
from runesmith.app.acceptance_contracts import expectations
from runesmith.app.planner import PlannerUnavailable, SkippedByOwner, source_context
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

SCHEMA = {'type': 'object', 'properties': {
    'checks': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': {'type': 'object', 'properties': {
        'test': {'type': 'string'}, 'says': {'type': 'string'}}, 'required': ['test', 'says'], 'additionalProperties': False}},
    'code': {'type': 'string'}}, 'required': ['checks', 'code'], 'additionalProperties': False}

SYSTEM = ("You are Runesmith's acceptance-check instrument. You write the owner's checks for one milestone; "
          "you do not implement it. Return JSON only.")
TASK = ("Write the owner's acceptance checks for ONE milestone of this project. They decide whether the milestone is "
        "done, so check the behaviour the milestone text describes, from the outside: prefer running the command the "
        "milestone documents (subprocess with sys.executable and cwd=os.getcwd(), which is the project folder when the "
        "checks run) or the public functions the milestone names. Do not rely on private names the milestone does not "
        "mention, and do not require more than it says. Use Python unittest only (no pytest), temporary directories for "
        "any files, no network and deterministic data. Keep it small: 2 to 8 tests, each checking one thing a person "
        "would recognise. For each test give its method name and one plain sentence a non-programmer understands. The "
        "feature may not exist yet: do not implement it. Return JSON with \"checks\" and \"code\" (the complete file).")
NETWORK_MODULES = {'socket', 'ssl', 'urllib', 'http', 'requests', 'ftplib', 'smtplib', 'telnetlib', 'asyncio'}
MAX_CODE = 20000
MILESTONE_ID = re.compile(r'[A-Za-z0-9_-]+')


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
    checks = []
    for row in data['checks']:
        if not isinstance(row, dict) or not isinstance(row.get('test'), str) or not isinstance(row.get('says'), str):
            raise WorkspaceError('Each check needs its test name and one plain sentence.')
        says = row['says'].strip()
        if row['test'] not in tests:
            raise WorkspaceError(f'"{row["test"]}" is not a test in the checks file.')
        if not says or len(says) > 300:
            raise WorkspaceError('Each plain sentence needs 1-300 characters.')
        checks.append({'test': row['test'], 'says': says})
    if not 1 <= len(checks) <= 8:
        raise WorkspaceError('Propose 1-8 checks.')
    if missing := sorted(tests - {c['test'] for c in checks}):
        raise WorkspaceError('Every test needs a plain sentence; missing: ' + ', '.join(missing))
    return {'checks': checks, 'code': code, 'code_sha256': hashlib.sha256(code.encode('utf-8')).hexdigest()}


def packet(ws, milestone_id) -> dict[str, Any]:
    milestone = _milestone(ws, milestone_id)
    return {'task': TASK,
            'milestone': {k: milestone.get(k) for k in ('id', 'title', 'detail', 'done_when', 'track')},
            'brief': ws.brief().get('text', ''),
            'public_acceptance': expectations(ws, milestone_id),
            'source_context': source_context(ws, limit=16000),
            'note': 'Owner acceptance runs on a clean copy of the project folder, with the current directory set to it.'}


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
                        'proposal': {k: waiting.get(k) for k in ('id', 'checks', 'code', 'drafted_by', 'utc')} if waiting else None}
    return out


def propose(ws, router, milestone_id, *, checkpoint=lambda: None) -> dict[str, Any]:
    milestone = _milestone(ws, milestone_id)
    if milestone.get('status') not in ('open', 'doing'):
        raise WorkspaceError('Propose acceptance checks for an unfinished milestone.')
    data = packet(ws, milestone_id)
    text = json.dumps(data, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    path = _record_path(ws, milestone_id)
    record = _read_json(path, {'milestone': milestone_id, 'proposals': []})
    for old in record['proposals']:
        if old.get('input_sha256') == digest and old.get('state') == 'proposed':
            return old                                  # an unchanged request reuses the waiting answer
    checkpoint()
    key = 'a' + uuid.uuid4().hex[:12]
    try:
        out = router.call('plan', prompt=text, system=SYSTEM, schema=SCHEMA, max_tokens=6000, key='acceptance-' + key)
    except KeyError as error:
        raise PlannerUnavailable('no model is set up for planning: add one under Thinking power') from error
    except Exception as error:
        raise PlannerUnavailable(f'the acceptance-check call did not answer: {str(error)[:200]}') from error
    if isinstance(out.data, dict) and out.data.get('skipped_by_owner'):
        raise SkippedByOwner('you skipped the request, so nothing changed')
    if not out.ok:
        raise PlannerUnavailable(f"the model's answer was not usable: {(out.error or 'no JSON')[:200]}")
    checkpoint()
    clean = validate(out.data)
    proposal = dict(clean, id=key, state='proposed', utc=_now(), milestone=milestone_id, input_sha256=digest,
                    drafted_by=out.receipt.get('answered_by') or out.receipt.get('model'))
    record = _read_json(path, {'milestone': milestone_id, 'proposals': []})
    record['proposals'] = (record['proposals'] + [proposal])[-10:]
    _write_json(path, record)
    ws.ledger.append('acceptance.proposed', {'milestone': milestone_id, 'proposal': key, 'checks': len(clean['checks']),
                                             'code_sha256': clean['code_sha256'], 'proposed_by': proposal['drafted_by']})
    return proposal


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
    header = (f"# Owner acceptance for milestone {milestone_id}. Proposed by {proposal.get('drafted_by') or 'a model'} "
              f"({proposal['utc']}), approved by the owner ({_now()}).\n"
              "# Builds of this milestone are judged by this file; build authors never see it.\n")
    body = (header + proposal['code'].rstrip('\n') + '\n').encode('utf-8')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        keep = target.with_name(f"{target.stem}.replaced-{uuid.uuid4().hex[:6]}.py.txt")
        keep.write_bytes(target.read_bytes())
    temporary = target.with_name(target.name + f'.{uuid.uuid4().hex[:6]}.tmp')
    temporary.write_bytes(body)
    atomic.replace(temporary, target)
    file_sha = hashlib.sha256(body).hexdigest()
    proposal.update(state='approved', approved_utc=_now(), file_sha256=file_sha, replace_reason=reason.strip() or None)
    for other in record['proposals']:
        if other is not proposal and other.get('state') == 'proposed':
            other.update(state='superseded')
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
