"""The check autopilot: approve or turn down proposed acceptance checks without the owner, only when every gate passes.

An owner setting, off by default. Asked for by the owner of journey J11 (2026-09-29) so an unattended project does not
wait for approvals. The Checker is a model, and a wrong check is costly: one that expects the wrong value fails every
correct build (in J11, Groq's Checker expected x = 1 where 50 was right), one on a file nothing creates never passes.
So proposed checks are approved only when:

1. their trial on the project as it is today ran, and fails as a milestone not yet built should;
2. Runesmith's own findings are clean: no file nothing creates, no exact text the sentence does not say, no revision
   that failed;
3. a different model, shown the milestone, the other milestones' approved checks and each example's input but not the
   values the checks expect, works out the same values, and sees no contradiction with the other milestones' checks.

Checks that fail a gate are discarded with the reason, which the next Checker is told (J11-G14), and asked for again,
at most MAX_ROUNDS times per milestone; after that they wait for the owner. When the autopilot cannot judge (checks
were not tried, no second model, the cross-check got no answer, or the owner approved the checks now in force), it
leaves the proposal for the owner and says why. Its approvals say "approved by Runesmith's check autopilot", never
owner-approved.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from runesmith.app.workspace import WorkspaceError, _now, _read_json

MAX_ROUNDS = 2
VERIFY_TOKENS = 1500
SYSTEM = ("You are Runesmith's independent cross-checker. You did not write these checks. For each question, work out "
          "the answer from the milestone and the example's own input alone, as a careful person would by hand. "
          "Return JSON only.")
TASK = ("Each example below prepares its input files, then runs the program as shown. Answer every question: for a "
        "number, the exact number (as digits, no units); otherwise \"yes\", \"no\", \"ok\" or \"error\" as the question "
        "asks. Then say whether any of these examples contradicts one of the checks already approved for the other "
        "milestones (for example a different file format, or accepting what another refuses): \"contradicts\" is true "
        "or false, and when true, \"contradiction\" names it in one short sentence.")
SCHEMA = {'type': 'object', 'properties': {
    'answers': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'id': {'type': 'string'}, 'answer': {'type': 'string'}}, 'required': ['id', 'answer']}},
    'contradicts': {'type': 'boolean'}, 'contradiction': {'type': 'string'}}, 'required': ['answers', 'contradicts']}


def gates(proposal) -> list[str]:
    """Why these checks cannot be approved without the owner, from what Runesmith itself found; empty when clean."""
    found = []
    verdict = (proposal.get('dry_run') or {}).get('verdict')
    if verdict == 'passes_now':
        found.append('they already pass on the project as it is, so they may not test what the milestone adds')
    elif verdict == 'broken':
        found.append('they could not run on the project as it is')
    for check in proposal.get('checks') or []:
        if check.get('missing_input'):
            found.append(f"{check['test']} runs the program on {', '.join(check['missing_input'])}, which nothing creates")
        if check.get('unstated'):
            found.append(f"{check['test']} requires exact text its sentence does not say: "
                         + ', '.join(json.dumps(t, ensure_ascii=False) for t in check['unstated']))
        if check.get('passes_today'):
            found.append(f"{check['test']} already passes on the project as it is, so it may not test what the milestone adds")
    revision = proposal.get('revision') or {}
    if revision.get('error') and revision.get('after') != 'unusable':
        found.append('the revision Runesmith asked for did not work')
    return found


def undecidable(proposal) -> str | None:
    """Why the autopilot cannot judge these checks at all, so they wait for the owner."""
    if proposal.get('style') != 'examples':
        return 'only checks written as examples can be cross-checked'
    if (proposal.get('dry_run') or {}).get('verdict') in (None, 'not_run'):
        return 'the checks were not tried on the project (checking drafts is off)'
    if any(step.get('call') or step.get('doc') for e in proposal.get('examples') or [] for step in e.get('steps') or []):
        return 'checks that call a function or read a document are not cross-examined yet'
    return None


def _command(step) -> str:
    return ' '.join(step.get('run') or [])


def questions(proposal) -> list[dict[str, Any]]:
    """What the checks expect, as questions a second model answers without seeing the expected values.

    Each yes-or-no question comes with its negation ("must contain" and "must leave out"): a second model that says
    yes, or no, to both is not judging, and its cross-check does not count (review of the autopilot: a model that
    agreed with everything approved a check that required the opposite of the milestone). Pairs alternate which of
    the two is asked first and are shuffled among the other questions by the questions' own text, so a model that
    answers by position is caught too, and one question has an answer that is always "no" (fix verifier: a model
    answering every pair "yes, then no" approved two contradictory checks).
    """
    units = []

    def row(test, kind, question, expected, pair=None, about='value', twin=False):
        return {'test': test, 'kind': kind, 'question': question, 'expected': expected, 'pair': pair, 'about': about,
                'twin': twin}

    def ask(test, kind, question, expected, about='value'):
        units.append([row(test, kind, question, expected, about=about)])

    def twins(members):
        units.append(members if sum(len(unit) == 2 for unit in units) % 2 == 0 else members[::-1])

    def both(test, claim, negation, about='value'):
        pair = f'p{len(units) + 1}'
        twins([row(test, 'word', claim + ' Answer "yes" or "no".', 'yes', pair, about),
               row(test, 'word', negation + ' Answer "yes" or "no".', 'no', pair, about, twin=True)])

    decoy = None
    for example in proposal.get('examples') or []:
        test = example['test']
        for step in example.get('steps') or []:
            expect, command = step.get('expect') or {}, _command(step)
            if not command:
                continue
            decoy = decoy or (test, f'Must the printed output of `{command}` contain')
            if expect.get('exit') in ('ok', 'error'):
                normally, error = f'Does `{command}` finish normally?', f'Does `{command}` stop with an error?'
                both(test, *((normally, error) if expect['exit'] == 'ok' else (error, normally)), about='exit')
            for line in expect.get('lines') or []:
                # With its twin ("add 7"): a model copying a number it sees, such as the --at argument, cannot keep the
                # two consistent (final autopilot check: a parrot approved x = 1 where 50 was right).
                pair, shown = f'p{len(units) + 1}', f'After `{command}`, one line of its printed output shows “{line["has"]}”.'
                twins([row(test, 'number', shown + ' Which number does that line show? Answer with that number only.',
                           line['number'], pair),
                       row(test, 'number', shown + ' Add 7 to the number that line shows. What is the result? Answer with '
                                                   'that number only.', float(line['number']) + 7, pair, twin=True)])
            for text in expect.get('shows') or []:
                both(test, f'Must the printed output of `{command}` contain “{text}”?',
                     f'Must the printed output of `{command}` leave out “{text}”?')
            for text in expect.get('hides') or []:
                both(test, f'Must the printed output of `{command}` leave out “{text}”?',
                     f'Must the printed output of `{command}` contain “{text}”?')
            order = expect.get('order') or []
            for first, then in zip(order, order[1:]):
                # "First" and "last" with the options shown in the same order: a model copying the first quoted text
                # gives the same answer to both (final autopilot check).
                one, other = (first, then) if not _flip(first + '\n' + then) else (then, first)
                pair, options = f'p{len(units) + 1}', f'“{one}” or “{other}”'
                twins([row(test, 'text', f'In the printed output of `{command}`, which comes first: {options}? Answer with '
                                         'that text only.', first, pair),
                       row(test, 'text', f'In the printed output of `{command}`, which comes last: {options}? Answer with '
                                         'that text only.', then, pair, twin=True)])
        for name in example.get('exists') or []:
            decoy = decoy or (test, f'After the steps, must the file {name} contain')
            both(test, f'After the steps, must the file {name} exist?', f'After the steps, may the file {name} be missing?')
        for files in example.get('contains') or []:
            for text in files.get('texts') or []:
                decoy = decoy or (test, f'After the steps, must the file {files["name"]} contain')
                both(test, f'After the steps, must the file {files["name"]} contain “{text}”?',
                     f'After the steps, must the file {files["name"]} leave out “{text}”?')
    if decoy and units:
        # One question whose honest answer is always "no", about a command or, for checks on files only, a file
        # (final autopilot check: checks without steps had none).
        token = 'rs-' + hashlib.sha256(json.dumps(proposal.get('examples'), sort_keys=True, default=str).encode('utf-8')).hexdigest()[:10]
        ask(decoy[0], 'word', f'{decoy[1]} “{token}”? Answer "yes" or "no".', 'no', about='decoy')
    ordered = [r for unit in sorted(units, key=lambda unit: hashlib.sha256(unit[0]['question'].encode('utf-8')).hexdigest())
               for r in unit]
    for number, r in enumerate(ordered, 1):
        r['id'] = f'q{number}'
    return ordered


def _flip(text) -> bool:
    return hashlib.sha256(str(text).encode('utf-8')).digest()[0] % 2 == 1


NO_CONTRADICTION = ('no', 'none', 'false', 'nothing', 'no contradiction', 'no contradictions')


def _contradiction(value) -> str | None:
    """The contradiction the second model named, or None when it said there is none, in whatever words ("No
    contradiction." counts as none: fix verifier)."""
    if value is None or value is False:
        return None
    said = _said(value)
    if said in NO_CONTRADICTION or re.match(r"(no|nope|none|nothing|all good|consistent|there (is|are) no)\b", said):
        return None
    return str(value).strip()[:400]


def _numbers(text) -> set[float]:
    return {float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', str(text).replace(',', ''))}


def _said(answer) -> str:
    return str(answer).strip().strip('.“”"\'').strip().lower()


def agrees(row, answer) -> bool | None:
    """Whether the second model's answer matches what the checks expect; None when the answer is unclear (none, more
    than one number, or not one of the allowed words). An unclear answer never counts either way (review of the
    autopilot: "At t=1, x is 50" was read as 1)."""
    if answer is None:
        return None
    if row['kind'] == 'number':
        found = _numbers(answer)
        if len(found) != 1:
            return None
        got, want = found.pop(), float(row['expected'])
        return abs(got - want) <= 1e-6 * max(1.0, abs(want)) + 1e-9
    said = _said(answer)
    if row['kind'] == 'text':
        return said == str(row['expected']).strip().lower()
    if said not in ('yes', 'no', 'ok', 'error'):
        return None
    return said == str(row['expected']).lower()


def _family(model) -> str:
    """The model itself, whichever route serves it: "kilo3:nvidia/nemotron-3-super-120b-a12b:free" and
    "nvidia:nvidia/nemotron-3-super-120b-a12b" are one model. A local "name:tag" (Ollama) keeps its own name."""
    name = str(model or '').lower()
    head, _, rest = name.partition(':')
    if rest and '/' in rest and '/' not in head:
        name = rest
    return re.sub(r':free$', '', name)


def second_model(ws, drafted_by) -> str | None:
    """A usable instrument for the Checker's or the Planner's role that is not the model which wrote the checks."""
    config = ws.config()
    wrote = _family(drafted_by)
    for role in ('acceptance', 'plan'):
        for name in (config.get('roles') or {}).get(role) or []:
            spec = (config.get('instruments') or {}).get(name) or {}
            models = [spec.get('model')] + list(spec.get('fallback_models') or [])
            if (spec.get('kind') != 'manual' and models[0] and ws._usable(name, spec)
                    and all(_family(m) != wrote for m in models)):
                return name
    return None


def _packet(ws, milestone_id, proposal, asked) -> dict[str, Any]:
    from runesmith.app.acceptance_proposals import _milestone, _other_checks
    milestone = _milestone(ws, milestone_id)
    by_test = {}
    for row in asked:
        by_test.setdefault(row['test'], []).append({'id': row['id'], 'question': row['question']})
    return {'task': TASK,
            'milestone': {k: milestone.get(k) for k in ('title', 'detail', 'done_when')},
            'other_milestones_checks': _other_checks(ws, milestone_id),
            'examples': [{'name': e['test'], 'files': e.get('files') or [],
                          'steps': [_command(s) for s in e.get('steps') or [] if _command(s)],
                          'questions': by_test.get(e['test'], [])} for e in proposal.get('examples') or []]}


def cross_check(ws, milestone_id, proposal) -> dict[str, Any]:
    """Ask a second model; {'model', 'disagreements': [...], 'contradicts': str|None} or {'undecided': why}."""
    from runesmith.config import build_router
    name = second_model(ws, proposal.get('drafted_by'))
    if name is None:
        return {'undecided': 'there is no second model to cross-check with (add another under Thinking power)'}
    asked = questions(proposal)
    if not asked:
        return {'undecided': 'the checks expect nothing that can be worked out by hand'}
    if all(row['about'] in ('exit', 'decoy') for row in asked):
        return {'undecided': 'the checks only ask whether the program finishes; there is nothing to work out by hand'}
    try:
        spec = ws.config()['instruments'][name]
        router = build_router({'instruments': {name: spec}, 'roles': {'acceptance': [name]}}, home=ws.home,
                              on_call=ws.record_call, backoff_s=())
        out = router.call('acceptance', prompt=json.dumps(_packet(ws, milestone_id, proposal, asked), ensure_ascii=False),
                          system=SYSTEM, schema=SCHEMA, max_tokens=VERIFY_TOKENS,
                          key='autopilot-' + str(proposal.get('id')))
    except Exception as error:
        return {'undecided': f'the cross-check got no answer ({str(error)[:160]})', 'model': name}
    if not out.ok or not isinstance(out.data, dict):
        return {'undecided': f'the cross-check answer was unusable ({(out.error or "no JSON")[:160]})', 'model': name}
    answers = {str(a.get('id')): a.get('answer') for a in out.data.get('answers') or [] if isinstance(a, dict)}
    model = out.receipt.get('answered_by') or out.receipt.get('model') or name
    judged = {row['id']: agrees(row, answers.get(row['id'])) for row in asked}
    unclear = [row for row in asked if judged[row['id']] is None]
    pairs = {}
    for row in asked:
        if row['pair']:
            pairs.setdefault(row['pair'], []).append(row)
    def consistent(rows) -> bool:
        base, twin = sorted(rows, key=lambda row: row['twin'])
        if base['kind'] == 'number':         # the twin asks for the same number plus 7
            got, plus = _numbers(answers.get(base['id'])), _numbers(answers.get(twin['id']))
            return len(got) == 1 == len(plus) and abs(plus.pop() - got.pop() - 7) <= 1e-6
        return _said(answers.get(base['id'])) != _said(answers.get(twin['id']))
    blind = [rows for rows in pairs.values() if len(rows) == 2 and not consistent(rows)]
    fooled = [row for row in asked if row['about'] == 'decoy' and judged[row['id']] is False]
    if unclear or blind or fooled:
        return {'undecided': f'{model} gave no clear judgement ({len(unclear)} unclear answers, {len(blind)} questions '
                             'answered the same way as their opposite' + (', and it said yes to a text nothing asks for'
                                                                          if fooled else '') + ')', 'model': model}
    disagreements = [f"{row['test']}: {row['question']} The checks expect {row['expected']}; {model} worked out "
                     f"{answers.get(row['id'])}." for row in asked
                     if judged[row['id']] is False and row['about'] != 'decoy' and not row['twin']]
    said = out.data.get('contradicts')
    contradicts = (str(out.data.get('contradiction') or 'yes, without saying which').strip()[:400] if said is True
                   else None if said is False else _contradiction(said))
    return {'model': model, 'asked': len(asked), 'disagreements': disagreements, 'contradicts': contradicts}


def rounds_used(ws, milestone_id) -> int:
    """Proposals the autopilot turned down since the last approval of this milestone's checks."""
    from runesmith.app.acceptance_proposals import _record_path
    used = 0
    for row in reversed(_read_json(_record_path(ws, milestone_id), {'proposals': []}).get('proposals') or []):
        if row.get('state') in ('approved', 'replaced'):
            break
        used += (row.get('autopilot') or {}).get('decision') == 'turned_down'
    return used


def review(ws, milestone_id, proposal) -> dict[str, Any]:
    """Decide on one waiting proposal: {'decision': 'approve'|'turn_down'|'owner', 'reason': ..., ...}."""
    from runesmith.app.acceptance_proposals import status
    approved = (status(ws).get(milestone_id) or {}).get('approved')
    if approved and approved.get('provenance') != 'model-proposed, autopilot-approved':
        return {'decision': 'owner', 'reason': 'you approved the checks now in force; only you replace them'}
    why = undecidable(proposal)
    if why:
        return {'decision': 'owner', 'reason': why}
    found = gates(proposal)
    if not found:
        check = cross_check(ws, milestone_id, proposal)
        if check.get('undecided'):
            return {'decision': 'owner', 'reason': check['undecided'], 'cross_check': check}
        if check['contradicts'] and not check['disagreements']:
            # A second model's claim of a contradiction may itself be wrong; it is the owner's call, never a turn-down
            # (final autopilot check: "Nope, these are consistent." once read as a contradiction).
            return {'decision': 'owner', 'reason': f"{check['model']} says these contradict another milestone's checks: "
                                                   f"{check['contradicts']}", 'cross_check': check}
        found = check['disagreements']
        if not found:
            return {'decision': 'approve', 'reason': f"trial and findings clean; {check['model']} worked out the same "
                    f"{check['asked']} expected values", 'cross_check': check}
    if rounds_used(ws, milestone_id) >= MAX_ROUNDS:
        return {'decision': 'owner', 'reason': f'turned down {MAX_ROUNDS} times already; these wait for you: '
                + '; '.join(found)[:600], 'findings': found}
    return {'decision': 'turn_down', 'reason': '; '.join(found)[:1000], 'findings': found}


def needs_checks(ws) -> str | None:
    """A ready milestone with no checks and nothing proposed or waiting, which the autopilot may ask for."""
    from runesmith.app.acceptance_proposals import acceptance_file, _record_path
    from runesmith.app.planner import ready_milestones
    for milestone in ready_milestones(ws.plan()):
        if acceptance_file(ws, milestone['id']).is_file():
            continue
        proposals = _read_json(_record_path(ws, milestone['id']), {'proposals': []}).get('proposals') or []
        if any(p.get('state') == 'proposed' for p in proposals):
            continue
        if rounds_used(ws, milestone['id']) >= MAX_ROUNDS:
            continue
        return milestone['id']
    return None


def act(ws, milestone_id, proposal, verdict) -> tuple[str, str]:
    """Carry out a review: approve, turn down (discard with the reason), or leave for the owner.

    Returns (what it did, the decision carried out: approve, turn_down, owner or none). The owner may have decided
    while the cross-check ran; then the autopilot stands aside (review of the autopilot).
    """
    from runesmith.app.acceptance_proposals import _record_path, acceptance_file, approve, discard, note_autopilot
    current = next((row for row in _read_json(_record_path(ws, milestone_id), {'proposals': []}).get('proposals') or []
                    if row.get('id') == proposal['id']), None)
    if not current or current.get('state') != 'proposed':
        return 'You decided about these checks meanwhile; the autopilot left them alone.', 'none'
    note = {k: verdict.get(k) for k in ('decision', 'reason', 'findings') if verdict.get(k)}
    if verdict.get('cross_check'):
        note['cross_check'] = {k: verdict['cross_check'].get(k) for k in ('model', 'asked', 'contradicts') if k in verdict['cross_check']}
    note_autopilot(ws, milestone_id, proposal['id'], dict(note, decision={'approve': 'approved', 'turn_down': 'turned_down',
                                                                          'owner': 'left_for_owner'}[verdict['decision']], utc=_now()))
    if verdict['decision'] == 'approve':
        replace = acceptance_file(ws, milestone_id).is_file()
        try:
            approve(ws, milestone_id, proposal['id'], replace=replace, by='autopilot',
                    reason=('Runesmith’s check autopilot: ' + verdict['reason']) if replace else '')
        except WorkspaceError as error:
            return f'The check autopilot could not approve them: {error}', 'none'
        return f"Runesmith’s check autopilot approved them: {verdict['reason']}.", 'approve'
    if verdict['decision'] == 'turn_down':
        try:
            discard(ws, milestone_id, proposal['id'], reason='Runesmith’s check autopilot turned them down: ' + verdict['reason'])
        except WorkspaceError as error:
            return f'The check autopilot could not turn them down: {error}', 'none'
        return f"Runesmith’s check autopilot turned them down and asks again: {verdict['reason']}.", 'turn_down'
    return f"Left for you: {verdict['reason']}.", 'owner'
