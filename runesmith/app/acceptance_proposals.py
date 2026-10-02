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
import time
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


def validate(data: Any, *, limit: int = MAX_CODE) -> dict[str, Any]:
    """The proposal as stored, or a WorkspaceError naming what is wrong with it."""
    if not isinstance(data, dict) or not isinstance(data.get('checks'), list) or not isinstance(data.get('code'), str):
        raise WorkspaceError('A proposal needs "checks" and "code".')
    code = data['code'].replace('\r\n', '\n')
    if not code.strip() or len(code) > limit:
        raise WorkspaceError(f'The checks file must contain 1-{limit} characters.')
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


def _other_checks(ws, milestone_id, limit=6000) -> list[dict[str, Any]]:
    """The checks the owner approved for the other milestones. In a new project there is no code to learn a file
    format from, so each Checker invented its own: m1's check refused a project file "{}" and m3's required the same
    file to be accepted (journey J11-G5)."""
    rows, used = [], 0
    for other in (ws.plan() or {}).get('milestones', []):
        if other.get('id') == milestone_id:
            continue
        said = [c['description'] for c in (expectations(ws, other['id']) or {}).get('criteria', [])
                if str(c.get('id', '')).startswith('check.')]
        if not said:
            continue
        row = {'milestone': other.get('title'), 'status': other.get('status'), 'checks': said}
        used += len(json.dumps(row, ensure_ascii=False))
        if used > limit:
            break
        rows.append(row)
    return rows


PROVEN_FILE = 1500          # characters of one proven input file
PROVEN_FILES = 3            # files taken from one milestone, so a few milestones' formats fit in the limit


def _approved_proposal(ws, milestone_id) -> dict[str, Any] | None:
    """The approved proposal whose file is the checks file in force, matched as status() matches it; None when the
    milestone has no checks, or the file is one the owner wrote or changed."""
    file = acceptance_file(ws, milestone_id)
    if not file.is_file():
        return None
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    return next((p for p in _proposal_rows(ws, milestone_id)
                 if p.get('state') == 'approved' and p.get('file_sha256') == digest), None)


def _accepted_files(examples) -> list[dict[str, str]]:
    """Input files of example checks that the program reads without refusing them: the files of an example are left out
    when only steps that must end in an error or a message read them (a damaged file, a project the program refuses),
    or, when no step names them, when the example is about a refusal."""
    def refusing(step) -> bool:
        expect = step.get('expect') or {}
        return expect.get('exit') in ('error', 'any') or bool(expect.get('message')) or 'raises' in expect

    def names(step, name) -> bool:
        return any(isinstance(w, str) and w.replace('\\', '/').removeprefix('./') == name for w in step.get('run') or [])
    found = []
    for example in examples if isinstance(examples, list) else []:
        steps = [s for s in example.get('steps') or [] if isinstance(s, dict)]
        for file in example.get('files') or []:
            if not isinstance(file, dict) or not isinstance(file.get('name'), str) or not isinstance(file.get('text'), str):
                continue
            named = [s for s in steps if names(s, file['name'])]
            if any(not refusing(s) for s in named) or (not named and not any(refusing(s) for s in steps)):
                found.append({'name': file['name'], 'text': file['text']})
    return found


def _short_title(title) -> str:
    """"Groups" of "Groups: shapes that move and fade together": the name another milestone's detail uses."""
    return re.split(r'\s+[-–—]\s+|:\s', str(title or '').strip(), maxsplit=1)[0].strip().lower()


def proven_inputs(ws, milestone_id, limit=6000) -> list[dict[str, Any]]:
    """Input files from the approved example checks of finished milestones, as {milestone, files: [{name, text}]}.

    Those checks pass on the program today, so their inputs are written the way the program reads them (journey
    J11-B16, G38: the Checker was not shown the program, which no longer fitted its packet, and wrote a rect's colour
    as "color" where the program reads "fill", a camera as an object where it reads a list, and a setting beside
    "project" where it sits inside). A milestone whose title this milestone's detail names ("Builds on: Groups")
    comes first, then the one whose checks were approved last. At most `limit` characters in all, `PROVEN_FILES` files
    of a milestone, each file cut at `PROVEN_FILE` characters.
    """
    detail = str(_milestone(ws, milestone_id).get('detail') or '').lower()
    found = []
    for position, other in enumerate((ws.plan() or {}).get('milestones', [])):
        other_id = other.get('id')
        if other_id == milestone_id or other.get('status') != 'done' or not isinstance(other_id, str) \
                or not MILESTONE_ID.fullmatch(other_id):
            continue
        proposal = _approved_proposal(ws, other_id)
        files = _accepted_files((proposal or {}).get('examples')) if proposal and proposal.get('style') == 'examples' else []
        if not files:
            continue
        title = str(other.get('title') or '').strip().lower()
        short = _short_title(title)
        named = bool(title and title in detail) or bool(len(short) >= 3 and re.search(
            r'(?<![A-Za-z0-9_])' + re.escape(short) + r'(?![A-Za-z0-9_])', detail))
        found.append((named, str(proposal.get('approved_utc') or ''), position, other.get('title'), files))
    found.sort(key=lambda row: (row[1], row[2]), reverse=True)          # the most recently approved first
    found.sort(key=lambda row: not row[0])                              # then the ones this detail names, in that order
    rows, seen = [], set()
    for _, _, _, title, files in found:
        row = {'milestone': title, 'files': []}
        for file in files:
            if len(row['files']) >= PROVEN_FILES or (file['name'], file['text']) in seen:
                continue
            text = file['text'] if len(file['text']) <= PROVEN_FILE else file['text'][:PROVEN_FILE] + '…'
            next_row = dict(row, files=[*row['files'], {'name': file['name'], 'text': text}])
            if len(json.dumps([*rows, next_row], ensure_ascii=False)) > limit:
                continue                    # too big for what is left: a smaller file may still fit
            row = next_row
            seen.add((file['name'], file['text']))
        if row['files']:
            rows.append(row)
    return rows


def _record(ws, milestone_id, default=None) -> dict[str, Any]:
    """A milestone's proposal record with only well-formed rows (reviews of J11-G16: one malformed row made every
    reader fail, the schedule's among them). A row that is not a proposal is left out, also when the record is
    written back."""
    fresh = dict(default) if default else {'proposals': []}
    record = _read_json(_record_path(ws, milestone_id), fresh)
    record = record if isinstance(record, dict) else fresh
    rows = record.get('proposals')
    record['proposals'] = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return record


def _proposal_rows(ws, milestone_id) -> list[dict[str, Any]]:
    return _record(ws, milestone_id)['proposals']


def _kept_beyond_window(rows) -> set[int]:
    """The rows the record keeps beyond its last ten (review of J11-G37): the row of the checks in force, which
    Withdraw and the provenance read, and the newest withdrawal, whose reason the next Checker reads, until checks are
    approved after it."""
    kept = [r for r in rows[:-10] if r.get('state') == 'approved'][-1:]
    withdrawn = [i for i, r in enumerate(rows) if r.get('state') == 'withdrawn']
    if (withdrawn and withdrawn[-1] < len(rows) - 10
            and not any(r.get('state') in ('approved', 'replaced') for r in rows[withdrawn[-1] + 1:])):
        kept.append(rows[withdrawn[-1]])
    return {id(r) for r in kept}


def _withdrawals(ws, milestone_id) -> int:
    """How many times the owner withdrew this milestone's checks: a count on the record, which the window of kept
    proposals does not trim."""
    return _record(ws, milestone_id).get('withdrawals') or 0


def _owner_words(row) -> list[tuple[str, int, str]]:
    """(when, order, what) the owner wrote on one proposal row, newest first: why he discarded or withdrew it, and why
    it replaced earlier checks. An approved row he later withdrew carries both (review of J11-G37: the replacement's
    reason vanished once its checks were withdrawn). Times are whole seconds: of two words in one second, a withdrawal
    is the later (order 1), since it is written last."""
    words = []
    if row.get('state') in ('discarded', 'withdrawn'):
        words.append((str(row.get('discarded_utc') or row.get('withdrawn_utc') or ''),
                      int(row.get('state') == 'withdrawn'), row.get('reason')))
    words.append((str(row.get('approved_utc') or row.get('utc') or ''), 0, row.get('replace_reason')))
    return [(when, order, text.strip()) for when, order, text in words if isinstance(text, str) and text.strip()]


def _owner_reasons(ws, milestone_id, limit=3) -> list[str]:
    """What the owner said when turning down or replacing earlier checks for this milestone, newest first. Asked
    again, the Checker was never told (journey J11-G14: "x goes from 0 to 100 over 2 seconds, so at 1 second it is
    50, not 1")."""
    # By time: the row of withdrawn checks sits where they were proposed, behind every proposal made while they stood,
    # and by position its reason was crowded out by three later turn-downs (review of J11-G37). A stable sort keeps
    # the newest-by-position order for rows with no time.
    pairs = [pair for row in reversed(_proposal_rows(ws, milestone_id)) for pair in _owner_words(row)]
    said = []
    for _, _, reason in sorted(pairs, key=lambda pair: pair[:2], reverse=True):
        if reason[:600] not in said:
            said.append(reason[:600])
    return said[:limit]


def _owner_reasons_elsewhere(ws, milestone_id, limit=3) -> list[dict[str, str]]:
    """What the owner said when turning down checks for the project's other milestones, newest first: advice such
    as \"with --svg the program writes a file, so check the file\" holds for every milestone (journey J11-G16: the
    runes-light Checker repeated the mistake the owner had just named for the styles milestone)."""
    said = []
    for other in (ws.plan() or {}).get('milestones', []):
        if other.get('id') == milestone_id or not isinstance(other.get('id'), str) or not MILESTONE_ID.fullmatch(other['id']):
            continue
        for row in _proposal_rows(ws, other['id']):
            for when, order, reason in _owner_words(row):
                said.append(((when, order), {'milestone': other.get('title'), 'said': reason[:600]}))
    return [row for _, row in sorted(said, key=lambda pair: pair[0], reverse=True)][:limit]


def packet(ws, milestone_id, style='code') -> dict[str, Any]:
    milestone = _milestone(ws, milestone_id)
    return {'task': acceptance_examples.TASK if style == 'examples' else TASK,
            'milestone': {k: milestone.get(k) for k in ('id', 'title', 'detail', 'done_when', 'track')},
            'brief': ws.brief().get('text', ''),
            'public_acceptance': expectations(ws, milestone_id),
            'other_milestones_checks': _other_checks(ws, milestone_id),
            'owner_said_about_earlier_checks': _owner_reasons(ws, milestone_id),
            'owner_said_about_other_milestones_checks': _owner_reasons_elsewhere(ws, milestone_id),
            # A program over the cap is shown in parts: its outline and the lines that read this milestone's fields, so
            # the Checker no longer guesses formats (journey J11-B16). The program may take 60% of the budget, and 6,000
            # characters are held back for it from the small files.
            'source_context': source_context(ws, limit=16000, milestone=milestone, feedback=False, parts_share=0.6,
                                             parts_reserve=6000),
            # Input files of checks that pass on the program today (journey J11-B16): the source above holds only parts of
            # a large program, so the formats it reads are also shown by example.
            **({'proven_inputs': proven_inputs(ws, milestone_id)} if style == 'examples' else {}),
            # The documents the owner chose to share with models (Goals & plan). Code goes in source_context; documents
            # never do, so without this a Checker could not see a single page of a handbook it is asked to check.
            'documents': ws.blueprint_text(),
            'note': 'Each example runs in its own fresh copy of the project folder, with the current directory set to it.'
            if style == 'examples' else
            'Owner acceptance runs on a clean copy of the project folder, with the current directory set to it.'}


def _holds(ws):
    """Whether the project holds a file in the copy the checks run in: that copy has files no model is shown
    (fixtures, shared documents), so the source context's list is not all of it. Read from a snapshot only when asked,
    once; a snapshot that cannot be taken holds everything, so nothing is refused on a guess (J11-CC4)."""
    names = []

    def held(rel) -> bool:
        if not names:
            try:
                names.append({name.casefold() for name in collect_snapshot(ws)['files']})
            except SnapshotUnsupported:
                names.append(None)
        return names[0] is None or rel.casefold() in names[0]
    return held


def _clean(answer, style, data, ws=None) -> dict[str, Any]:
    """The proposal as stored, from the model's answer in either style; a WorkspaceError says what is wrong."""
    if style != 'examples':
        return validate(answer)
    milestone = data['milestone']
    context = data.get('source_context')
    # An example that runs a file it does not list, and the project does not hold, is refused here so the Checker is
    # told once (J11-CC4); with no complete list of the project's files (a list cut at 2,000 names, or no source) it
    # is only named under its check, for the autopilot's gate.
    listed = isinstance(context, dict) and isinstance(context.get('inventory'), list) and not context.get('truncated_inventory')
    shaped = acceptance_examples.validate_examples(
        answer, ' '.join(str(milestone.get(k) or '') for k in ('title', 'detail', 'done_when')),
        json.dumps(context, ensure_ascii=False) + '\n' + str(data.get('documents') or ''),
        refuse_missing=listed, held=_holds(ws) if ws is not None else None)
    # The limit is for check code a model writes; here the file is Runesmith's own template plus the examples,
    # which the examples format already bounds (journey J11-B12: the template grew, and three examples with their
    # motion files were refused as too long).
    checked = validate({'checks': [{'test': c['test'], 'says': c['says']} for c in shaped['checks']],
                        'assumes': [], 'code': shaped['code']}, limit=MAX_CODE + len(acceptance_examples.HARNESS))
    checks = [{'test': c['test'], 'says': c['says'], 'exact': e['exact'],
               **({'missing_input': e['missing_input']} if e.get('missing_input') else {})}
              for c, e in zip(checked['checks'], shaped['checks'])]
    return dict(shaped, checks=checks, code_sha256=checked['code_sha256'])


# A revision or retry request carries the first answer too. Its source excerpt is smaller, so the request still fits
# a free per-minute window (Groq's free gpt-oss-120b: 8,000 tokens a minute, prompt and answer room together).
LEAN_SOURCE = 6000


def _lean(ws, data):
    return dict(data, source_context=source_context(ws, limit=LEAN_SOURCE, milestone=data.get('milestone'), feedback=False,
                                                     parts_reserve=4000))


def _bounded(answer, limit=40000):
    text = json.dumps(answer, ensure_ascii=False)
    return answer if len(text) <= limit else {'truncated': text[:limit]}


def _turned_away(error) -> bool:
    """Whether every model refused the request before generating anything, so asking again spends nothing."""
    receipt = getattr(error, 'receipt', None) or getattr(error.__cause__, 'receipt', None) or {}
    return bool(receipt.get('no_route_accepted') or receipt.get('not_admitted')
                or receipt.get('refused_before_answer') == 'too_large')


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
        failure = PlannerUnavailable(out.error or "the model service refused this request")
        failure.receipt = dict(out.receipt or {})          # a model called directly may have refused it as too large
        raise failure
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
        record = _record(ws, mid)
        file = acceptance_file(ws, mid)
        approved = None
        if file.is_file():
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            match = next((p for p in record['proposals'] if p.get('state') == 'approved' and p.get('file_sha256') == digest), None)
            autopilot = match is not None and match.get('approved_by') == 'autopilot'
            approved = ({'provenance': 'model-proposed, autopilot-approved' if autopilot else 'model-proposed, owner-approved',
                         'proposed_by': match.get('drafted_by'), 'approved_utc': match.get('approved_utc'),
                         'checks': match['checks'], 'sha256': digest,
                         'autopilot': (match.get('autopilot') or {}).get('reason') if autopilot else None}
                        if match else {'provenance': 'owner file', 'checks': None, 'sha256': digest})
        waiting = next((p for p in reversed(record['proposals']) if p.get('state') == 'proposed'), None)
        if approved or waiting:
            out[mid] = {'approved': approved,
                        'proposal': {k: waiting.get(k) for k in ('id', 'checks', 'assumes', 'dry_run', 'revision', 'code',
                                                                      'drafted_by', 'utc', 'dropped', 'not_checked', 'style',
                                                                      'autopilot')}
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
    withdrawals = _withdrawals(ws, milestone_id)         # before the packet: a later withdrawal is then seen
    data = packet(ws, milestone_id, style)
    text = json.dumps(data, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    path = _record_path(ws, milestone_id)
    record = _record(ws, milestone_id, {'milestone': milestone_id, 'proposals': []})
    for old in record['proposals']:
        if old.get('input_sha256') == digest and old.get('state') == 'proposed':
            return old                                  # an unchanged request reuses the waiting answer
    checkpoint()
    key = 'a' + uuid.uuid4().hex[:12]
    try:
        out = _ask(router, data, style, 'acceptance-' + key)
    except PlannerUnavailable as error:
        # Every model turned the request away before generating (nothing ran). One of them may take a smaller one:
        # Groq's free gpt-oss-120b refused the Checker's full request as too large for its 8,000 tokens a minute
        # (journey J11-G17). Asked once more with the shorter source excerpt a revision already uses.
        if not _turned_away(error):
            raise
        checkpoint()
        data = _lean(ws, data)
        out = _ask(router, data, style, 'acceptance-' + key + '-lean')
    checkpoint()
    drafted_by = out.receipt.get('answered_by') or out.receipt.get('model')
    first_answer = out.data
    try:
        clean = _clean(out.data, style, data, ws)
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
            clean = _clean(out.data, style, data, ws)
        except WorkspaceError as again:
            # Both answers are kept, so what the Checker wrote can be read (journey J11-G3).
            kept = ws.home / 'acceptance-proposals' / 'refused' / (key + '.json')
            _write_json(kept, {'milestone': milestone_id, 'utc': _now(), 'drafted_by': drafted_by,
                               'errors': [str(error)[:300], str(again)[:300]],
                               'answers': [_bounded(first_answer), _bounded(out.data)]})
            if isinstance(error, acceptance_examples.NothingToCheck) and isinstance(again, acceptance_examples.NothingToCheck):
                said = acceptance_examples._notes((out.data or {}).get('not_checked') if isinstance(out.data, dict) else None)
                raise WorkspaceError('Nothing in this milestone could be checked automatically'
                                     + (': ' + ' '.join(said) if said else '.') + ' Build it and read each draft '
                                     'yourself before writing it, or reword the milestone so what it makes can be '
                                     'checked by running a command. The Checker’s answers are kept in '
                                     f'{kept.relative_to(ws.home).as_posix()}.') from None
            raise WorkspaceError(f'Both answers broke a rule of the examples format. First: {str(error)[:200]} '
                                 f'Then: {str(again)[:200]} Both are kept in '
                                 f'{kept.relative_to(ws.home).as_posix()}.') from None
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
    with ws._lock:                  # withdraw() holds it too
        if _withdrawals(ws, milestone_id) != withdrawals:
            # Its answer never read the owner's reason, and a waiting proposal would let the autopilot approve checks
            # again at once (review of J11-G37).
            raise WorkspaceError('You withdrew checks for this milestone while these were being written, so they never '
                                 'read your reason: nothing was proposed. Ask again.')
        record = _record(ws, milestone_id, {'milestone': milestone_id, 'proposals': []})
        rows = record['proposals'] + [proposal]
        keep = _kept_beyond_window(rows)
        record['proposals'] = [r for i, r in enumerate(rows) if i >= len(rows) - 10 or id(r) in keep]
        _write_json(path, record)
    ws.ledger.append('acceptance.proposed', {'milestone': milestone_id, 'proposal': key, 'checks': len(clean['checks']),
                                             'code_sha256': clean['code_sha256'], 'proposed_by': proposal['drafted_by']})
    return proposal


def findings(proposal) -> list[str]:
    """What Runesmith itself found wrong with a proposal: its trial result, and texts its sentences do not say."""
    found = [FINDINGS[proposal['dry_run']['verdict']]] if proposal['dry_run']['verdict'] in FINDINGS else []
    for check in proposal['checks']:
        if check.get('missing_input'):
            found.append(f"{check['test']} runs the program on " + ', '.join(json.dumps(n, ensure_ascii=False)
                         for n in check['missing_input']) + ', a file nothing creates and the project does not have, '
                         'so it fails even on a correct build: create it with "files" (with the content the '
                         'example needs), or use a file the project has.')
        if check.get('unstated'):
            found.append(f"{check['test']} requires the exact text " + ', '.join(json.dumps(t, ensure_ascii=False)
                         for t in check['unstated']) + ', which its sentence does not say: put it in the sentence, '
                         'or stop requiring it.')
    return found


def _revise_once(ws, router, data, first, key, drafted_by, checkpoint, *, style='code', first_answer=None):
    """One more call, told what Runesmith found. The first proposal is kept (with its warnings) if this fails."""
    finding = (first['dry_run']['verdict'] if first['dry_run']['verdict'] in FINDINGS else 'missing_input'
               if any(c.get('missing_input') for c in first['checks']) else 'unstated_text')
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
        revised = _clean(out.data, style, data, ws)
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
# Inside a function, so no module name is left holding a test class: a loop variable at module level made unittest
# load the class twice, and every check ran twice (journey J11-B17).
FOOTER = '''

def _acceptance_public_criteria():
    import unittest
    for case in [v for v in list(globals().values()) if isinstance(v, type) and v.__module__ == __name__
                 and issubclass(v, unittest.TestCase)]:
        case.PUBLIC_CRITERIA = {name: ["check." + name] for name in dir(case) if name.startswith("test")}


_acceptance_public_criteria()
'''


def _owner_criteria(ws, milestone_id) -> list[dict[str, str]]:
    """The criteria the owner stated himself: every public one except the sentences of approved checks."""
    return [c for c in (expectations(ws, milestone_id) or {}).get('criteria', [])
            if not c['id'].startswith(('check.', 'assumes.'))]


def _interfaces_kept(ws, milestone_id, criteria):
    """(interfaces, lost): the owner's public interfaces for these criteria, and what had to go. Links to sentences that
    are no longer public go, and an interface left with none goes; `lost` says which, as {interface, removed,
    dropped}, so the owner is told (interfaces is None when the milestone declares none)."""
    before = expectations(ws, milestone_id) or {}
    if 'interfaces' not in before:
        return None, []
    ids = {c['id'] for c in criteria}
    kept, lost = [], []
    for row in before['interfaces']:
        links = [k for k in row['criterion_ids'] if k in ids]
        if len(links) < len(row['criterion_ids']):
            lost.append({'interface': row.get('id'), 'removed': [k for k in row['criterion_ids'] if k not in ids],
                         'dropped': not links})
        if links:
            kept.append(dict(row, criterion_ids=links))
    return kept, lost


def public_criteria(ws, milestone_id, proposal) -> list[dict[str, str]]:
    """The milestone's public expectations after approval: the owner's own criteria, plus these sentences."""
    kept = _owner_criteria(ws, milestone_id)
    ours = [{'id': 'check.' + c['test'], 'description': (c['says'] + (' Checked exactly: ' + c['exact'] if c.get('exact') else '')
                                                           + (' It requires the exact text: ' + ', '.join(
                 f'“{text}”' for text in c['unstated']) + '.' if c.get('unstated') else '')
                                                           + (' It runs the program on ' + ', '.join(
                 f'“{name}”' for name in c['missing_input']) + ', which the project does not have yet.'
                                                              if c.get('missing_input') else ''))[:1200]}
            for c in proposal['checks']]
    if proposal.get('assumes'):
        ours.append({'id': 'assumes.1', 'description': ('Also assumed: ' + '; '.join(proposal['assumes']))[:1200]})
    if any(not CRITERION_ID.fullmatch(c['id']) for c in ours):
        raise WorkspaceError('A test name is too long to become a public expectation; ask for the checks again.')
    if len(kept) + len(ours) > 20:
        raise WorkspaceError('This milestone has too many public expectations to add these checks; remove some first.')
    return kept + ours


SLOW_S = 5.0        # an approval or withdrawal that took this long says where the time went (journey J11-F30)


def _slow(started, waited) -> dict[str, Any]:
    """What the ledger keeps of a slow approval or withdrawal: its seconds, and how many of them were spent waiting for
    the workspace lock. Nothing for a quick one. J11's Withdraw took two minutes once, on a computer three programs
    were overloading, and nothing recorded whether it had waited for the lock or for the disk."""
    seconds = time.monotonic() - started
    return {'slow': {'seconds': round(seconds, 1), 'waited_for_workspace_s': round(waited, 1)}} if seconds >= SLOW_S else {}


def approve(ws, milestone_id, proposal_id, *, replace: bool = False, reason: str = '', by: str = 'owner') -> dict[str, Any]:
    started = time.monotonic()
    if by not in ('owner', 'autopilot'):
        raise WorkspaceError('Checks are approved by the owner or by the check autopilot.')
    _milestone(ws, milestone_id)
    if acceptance_file(ws, milestone_id).is_file():
        from runesmith.app.build_memory import backfill_quoted
        backfill_quoted(ws, milestone_id)               # slow reads of old receipts, before the lock is taken
    # It reads the record and writes it back: a withdrawal landing in between was overwritten or half undone, 3 runs in
    # 40 overlaps of an autopilot replacement with a withdrawal (review of J11-G37).
    asked = time.monotonic()
    with ws._lock:
        waited = time.monotonic() - asked
        return _approve(ws, milestone_id, proposal_id, replace=replace, reason=reason, by=by,
                        slow=lambda: _slow(started, waited))


def _approve(ws, milestone_id, proposal_id, *, replace, reason, by, slow=lambda: {}) -> dict[str, Any]:
    path = _record_path(ws, milestone_id)
    record = _record(ws, milestone_id)
    proposal = next((p for p in record['proposals'] if p.get('id') == proposal_id), None)
    if proposal is None or proposal.get('state') != 'proposed':
        raise WorkspaceError('That proposal is not waiting for approval.')
    if proposal.get('before_withdrawal'):
        # Whoever asks, the owner or the autopilot: it was written before the owner withdrew checks, so it never read
        # his reason (review of J11-G37).
        raise WorkspaceError('The owner withdrew checks after these were written, so they never read the reason: ask for '
                             'new ones.')
    target = acceptance_file(ws, milestone_id)
    if target.is_file() and not replace:
        raise WorkspaceError('This milestone already has acceptance checks. Replacing them needs a reason.')
    if target.is_file() and not reason.strip():
        raise WorkspaceError('Say why the existing checks are replaced; the old file is kept.')
    criteria = public_criteria(ws, milestone_id, proposal)
    # Settled before the file is touched: an interface linked to a sentence these checks do not have refused the
    # publication after the file was replaced, leaving checks nobody could withdraw (review of J11-G37).
    interfaces, lost = _interfaces_kept(ws, milestone_id, criteria)
    # Checks the autopilot approved never read as the owner's, not even in the file's first words (review of the
    # autopilot).
    title = 'Owner acceptance' if by == 'owner' else 'Runesmith check-autopilot acceptance (not owner-reviewed)'
    header = (f"# {title} for milestone {milestone_id}. Proposed by {proposal.get('drafted_by') or 'a model'} "
              f"({proposal['utc']}), approved by {'the owner' if by == 'owner' else 'Runesmith’s check autopilot'} ({_now()}).\n"
              "# Builds of this milestone are judged by this file; build authors never see it, only its sentences.\n")
    body = (header + proposal['code'].rstrip('\n') + '\n' + FOOTER).encode('utf-8')
    target.parent.mkdir(parents=True, exist_ok=True)
    replacing = target.is_file()
    if replacing:
        keep = target.with_name(f"{target.stem}.replaced-{uuid.uuid4().hex[:6]}.py.txt")
        keep.write_bytes(target.read_bytes())
    temporary = target.with_name(target.name + f'.{uuid.uuid4().hex[:6]}.tmp')
    temporary.write_bytes(body)
    atomic.replace(temporary, target)
    file_sha = hashlib.sha256(body).hexdigest()
    published = publish_expectations(ws, milestone_id, criteria, 'The owner approved these acceptance checks in plain words.'
                                     if by == 'owner' else 'Runesmith’s check autopilot approved these acceptance checks.',
                                     by='owner (approved acceptance checks)' if by == 'owner' else 'check autopilot (approved acceptance checks)',
                                     interfaces=interfaces)
    proposal.update(state='approved', approved_utc=_now(), approved_by=by, file_sha256=file_sha, replace_reason=reason.strip() or None,
                    expectations_version=published['version'])
    for other in record['proposals']:
        if other is not proposal and other.get('state') == 'proposed':
            other.update(state='superseded')
        elif other is not proposal and other.get('state') == 'approved':
            other.update(state='replaced', replaced_utc=_now())      # its file is kept as *.replaced-*.py.txt
    _write_json(path, record)
    if replacing:           # builders keep no memory of the sentences just replaced (review of J11-G37)
        from runesmith.app.build_memory import retire_for_milestone
        retire_for_milestone(ws, milestone_id, 'The owner replaced the checks these observations quote.')
    ws.ledger.append('acceptance.approved', {'milestone': milestone_id, 'proposal': proposal_id, 'sha256': file_sha,
                                             'proposed_by': proposal.get('drafted_by'), 'replaced': bool(reason.strip()),
                                             'approved_by': by, **({'interface_links_removed': lost} if lost else {}), **slow()})
    # The owner's interface links to sentences these checks do not have are gone, and he is told which.
    return {'ok': True, 'sha256': file_sha, 'checks': proposal['checks'], **({'interface_links_removed': lost} if lost else {})}


def note_autopilot(ws, milestone_id, proposal_id, note) -> None:
    """What the check autopilot decided about a proposal, kept with it for the owner to read."""
    path = _record_path(ws, milestone_id)
    with ws._lock:                          # read, change, write back: never across a withdrawal (review of J11-G37)
        record = _record(ws, milestone_id)
        proposal = next((p for p in record['proposals'] if p.get('id') == proposal_id), None)
        if proposal is None:
            raise WorkspaceError('Unknown proposal.')
        proposal['autopilot'] = note
        _write_json(path, record)
    ws.ledger.append('acceptance.autopilot', {'milestone': milestone_id, 'proposal': proposal_id,
                                              'decision': note.get('decision'), 'reason': str(note.get('reason') or '')[:300]})


def withdraw(ws, milestone_id, *, reason: str) -> dict[str, Any]:
    """The owner takes back approved checks that are wrong, saying why (journey J11-G37: Envelope's checks put the
    envelope where the milestone does not, and could only be replaced, never withdrawn with a reason).

    The file is kept beside it as *.withdrawn-*.py.txt; the sentences builders were shown are taken back (their
    history stays; the milestone's memories of builds checked by them are retired), the owner's own criteria and
    interfaces are published again without them; the reason is read by the next Checker; the milestone then needs
    checks again.
    """
    started = time.monotonic()
    _milestone(ws, milestone_id)
    if not isinstance(reason, str) or not reason.strip():
        raise WorkspaceError('Say why these checks are wrong: the next checks are written with your reason.')
    from runesmith.app.build_memory import backfill_quoted
    backfill_quoted(ws, milestone_id)       # the receipts older memories need are read before the lock is taken
    asked = time.monotonic()
    with ws._lock:              # an apply may be judging a build by this file right now (review of J11-G37)
        waited = time.monotonic() - asked
        path = _record_path(ws, milestone_id)
        record = _record(ws, milestone_id)
        proposal = next((p for p in reversed(record['proposals']) if p.get('state') == 'approved'), None)
        target = acceptance_file(ws, milestone_id)
        if proposal is None or not target.is_file():
            raise WorkspaceError('This milestone has no approved checks to withdraw.')
        body = target.read_bytes()
        if hashlib.sha256(body).hexdigest() != proposal.get('file_sha256'):
            # The studio hides the button, but the server decides: a file the owner wrote or edited is his own to remove.
            raise WorkspaceError('This checks file is not the one that was approved here: you wrote or changed it yourself, '
                                 'so remove or replace it yourself.')
        keep = target.with_name(f"{target.stem}.withdrawn-{uuid.uuid4().hex[:6]}.py.txt")
        keep.write_bytes(body)
        target.unlink()
        owned = _owner_criteria(ws, milestone_id)
        if owned:               # the owner's own criteria (and the interfaces on them) stay in force; a new version
            interfaces, lost = _interfaces_kept(ws, milestone_id, owned)
            publish_expectations(ws, milestone_id, owned, 'Checks withdrawn: ' + reason.strip(),
                                 by='owner (withdrew checks)', interfaces=interfaces)
        else:                   # nothing else was stated: no public expectations, every version stays in its history
            lost = []
            contract = ws.home / 'acceptance-contracts' / (milestone_id + '.json')
            if contract.is_file():
                contract.unlink()
        from runesmith.app.build_memory import retire_for_milestone
        retire_for_milestone(ws, milestone_id, 'The owner withdrew the checks these observations quote.')
        # (A record written by an interim tree carried `rows_at_withdrawal` instead of these marks; that tree was never
        # released, so no home has one and it is not read.)
        for row in record['proposals']:     # all judged by checks he took back; the mark survives the window's trim
            row['before_withdrawal'] = True
            if row.get('state') == 'proposed':      # written before his reason: neither he nor the autopilot approves it
                row.update(state='stale', stale_note='Written before the owner withdrew checks, so it never read his reason.')
        record['withdrawals'] = (record.get('withdrawals') or 0) + 1
        proposal.update(state='withdrawn', withdrawn_utc=_now(), reason=reason.strip()[:1000])
        _write_json(path, record)
        ws.ledger.append('acceptance.withdrawn', {'milestone': milestone_id, 'proposal': proposal.get('id'), 'kept': keep.name,
                                                  **({'interface_links_removed': lost} if lost else {}), **_slow(started, waited)})
    return {'ok': True, 'kept': keep.name, **({'interface_links_removed': lost} if lost else {})}


def discard(ws, milestone_id, proposal_id, *, reason: str = '') -> dict[str, Any]:
    path = _record_path(ws, milestone_id)
    with ws._lock:                          # read, change, write back: never across a withdrawal (review of J11-G37)
        record = _record(ws, milestone_id)
        proposal = next((p for p in record['proposals'] if p.get('id') == proposal_id), None)
        if proposal is None or proposal.get('state') != 'proposed':
            raise WorkspaceError('That proposal is not waiting for approval.')
        proposal.update(state='discarded', discarded_utc=_now(), reason=reason.strip()[:1000] or None)
        _write_json(path, record)
    ws.ledger.append('acceptance.discarded', {'milestone': milestone_id, 'proposal': proposal_id})
    return {'ok': True}
