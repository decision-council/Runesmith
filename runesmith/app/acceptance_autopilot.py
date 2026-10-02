"""The check autopilot: approve or turn down proposed acceptance checks without the owner, only when every gate passes.

An owner setting, off by default. Asked for by the owner of journey J11 (2026-09-29) so an unattended project does not
wait for approvals. The Checker is a model, and a wrong check is costly: one that expects the wrong value fails every
correct build (in J11, Groq's Checker expected x = 1 where 50 was right), one on a file nothing creates never passes.
So proposed checks are approved only when:

1. their trial on the project as it is today ran, and fails as a milestone not yet built should;
2. Runesmith's own findings are clean: no file nothing creates, no exact text the sentence does not say, no revision
   that failed;
3. the checks name every exact text the milestone's 'done when' names (journey J11-G40: Depth's checks left out the
   parallax values its 'done when' spells out, and were approved);
4. a different model, shown the milestone, the other milestones' approved checks, the inputs other checks proved and
   each example's input but not the values the checks expect, works out the same values, sees no contradiction with
   the other milestones' checks, and finds no field written under another name or in another place than the proven
   inputs and the milestone use (journey J11-G38: "color" for "fill", "grade" beside "project").

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
        "or false, and when true, \"contradiction\" names it in one short sentence. Last, \"proven_inputs\" are input "
        "files from checks that pass on the program today, and \"documents\" are the owner's own rules: \"misplaced\" "
        "is a list of short sentences naming any field an example writes under a different name or in a different "
        "place than the proven inputs, the documents and the milestone use (for example a colour written as "
        "\"color\" where they use \"fill\", or a setting written beside \"project\" that the milestone puts inside "
        "it); an empty list when there is none.")
SCHEMA = {'type': 'object', 'properties': {
    'answers': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'id': {'type': 'string'}, 'answer': {'type': 'string'}}, 'required': ['id', 'answer']}},
    'contradicts': {'type': 'boolean'}, 'contradiction': {'type': 'string'},
    'misplaced': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['answers', 'contradicts']}
DOCUMENTS = 4000                # characters of the owner's shared documents the second model reads (journey J11-G38)

# The exact texts a 'done when' names (journey J11-G40), found in one pass so a text inside another is not named twice:
# an attribute with its value (class="rs-layer", d="M 0 0 L 150 50": the value has no = < > and none of its edges is a
# space, which keeps a stray pair of quotes such as `r=" and, separately, fill="` from reading as one), a call written
# with numbers (translate(-510,-270), scale(1.5), url(#rs-clip-wipe1)), or a quoted phrase of two or more words.
_ATTRIBUTE = r'(?<![\w:.-])[A-Za-z_][\w:.-]*="[^\s"=<>][^"=<>]{0,118}?(?<=\S)"'
_ITEM = r'(?:[-+]?(?:\d+\.?\d*|\.\d+)[A-Za-z%]{0,4}|#[\w-]+)'
_CALL = r'(?<![\w.-])[A-Za-z][\w-]*\((?=[^()]*\d)' + _ITEM + '(?:,' + _ITEM + r')*\)'
_PHRASE = r'(?<![\w=])"(?=[^\s"])[^"=<>{};\n]{0,100}?(?<=[^\s"])"(?!\w)'
NAMED = re.compile(f'(?P<attribute>{_ATTRIBUTE})|(?P<call>{_CALL})|(?P<phrase>{_PHRASE})')
COVERAGE_ROOM = 380             # characters of texts the finding lists: the next Checker is told at most 600 of it


def named_texts(done_when) -> list[str]:
    """The exact texts a milestone's 'done when' names, in the order it names them, each once: attribute pairs
    (name="value"), calls written with numbers (translate(-510,-270)) and quoted phrases of two or more words
    ("Invalid project structure"). A 'done when' in plain prose names none, so nothing is asked of its checks.

    Journey J11-G40: Depth's checks required class="rs-layer" and data-depth="0.5" but none of the parallax values its
    'done when' spells out (translate(-510,-270), translate(-480,-270), translate(-540,-270)), Masks' left out the
    ids it names and Colour grade's the colours, and the autopilot approved all three; it never compared them.
    """
    found = []
    for match in NAMED.finditer(str(done_when or '')):
        text = match.group()
        if match.lastgroup == 'phrase':
            text = text[1:-1].rstrip('.,;:!?')
            if len(text.split()) < 2:
                continue
        if text not in found:
            found.append(text)
    return found


def _squash(text) -> str:
    """Whitespace runs as one space, and no difference of case: the checks compare texts that way."""
    return ' '.join(str(text).split()).lower()


def _line_texts(has, number) -> list[str]:
    """How a line check "has" + number looks in a file: has="3" and has 3 (the number without a trailing .0)."""
    try:
        shown = int(number) if float(number).is_integer() else number
    except (TypeError, ValueError, OverflowError):
        return []
    return [f'{has}="{shown}"', f'{has} {shown}']


def _required_texts(proposal) -> list[str]:
    """Every text the proposed checks require or forbid, in the forms they are looked for."""
    texts = []
    for example in proposal.get('examples') or []:
        for step in example.get('steps') or []:
            expect = step.get('expect') or {}
            for key in ('shows', 'hides', 'order'):
                texts += [t for t in expect.get(key) or [] if isinstance(t, str)]
            for line in expect.get('lines') or []:
                texts += _line_texts(line.get('has'), line.get('number'))
        for key in ('contains', 'lacks'):
            for files in example.get(key) or []:
                texts += [t for t in files.get('texts') or [] if isinstance(t, str)]
        for line in example.get('file_lines') or []:
            texts += _line_texts(line.get('has'), line.get('number'))
    return texts


def uncovered(proposal, done_when) -> list[str]:
    """The texts the 'done when' names that none of the checks requires or forbids, inside any text they use (journey
    J11-G40): `translate(-510,-270)` is covered by a check on `translate(480,270) scale(1) translate(-510,-270)`."""
    needed = named_texts(done_when)
    if not needed:
        return []
    held = [_squash(text) for text in _required_texts(proposal)]
    return [text for text in needed if not any(_squash(text) in one for one in held)]


def _coverage_finding(texts) -> str:
    shown, size = [], 0
    for text in texts:
        if shown and size + len(text) > COVERAGE_ROOM:
            break
        shown.append(f'“{text}”')
        size += len(text) + 4
    more = len(texts) - len(shown)
    return ("the checks leave out what the milestone's 'done when' names: " + ', '.join(shown)
            + (f' and {more} more' if more else '') + '; check each of them')


def gates(proposal, done_when=None) -> list[str]:
    """Why these checks cannot be approved without the owner, from what Runesmith itself found; empty when clean.
    `done_when` is the milestone's: the checks must name every exact text it names."""
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
        # A single check that passes today is not a finding on its own: "without a style the picture stays as it
        # is" passes today by design. Held against it, the Checker rewrote that right check into a wrong one so it
        # would fail today (journey J11-G18). The set must still fail today somewhere (above), and the second
        # model's cross-check judges every check.
    for note in proposal.get('dropped') or []:
        # A file check reduced to "the file exists" checks far less than its sentence says (review of J11-G19).
        if isinstance(note, str) and 'checked instead that it exists' in note:
            found.append(f'{note}: only that the file exists is checked, not what it should or should not contain')
    for example in proposal.get('examples') or []:
        for step in example.get('steps') or []:
            words, expect = step.get('run') or [], step.get('expect') or {}
            written = _written(words)
            if written and any(expect.get(k) for k in ('shows', 'hides', 'lines', 'order')):
                # The command writes its result to a file and may print nothing: printed-output checks on it may
                # fail every correct build (journey J11-G24: the Embers checks read the printed output of
                # --svg out.svg, and the second model, not knowing it prints nothing, agreed).
                found.append(f"{example.get('test')}: `{' '.join(words)}` writes {written}, and its checks read what "
                             'it prints; check the file instead')
    revision = proposal.get('revision') or {}
    if revision.get('error') and revision.get('after') != 'unusable':
        found.append('the revision Runesmith asked for did not work')
    if left_out := uncovered(proposal, done_when):
        found.append(_coverage_finding(left_out))
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


OUTPUT_OPTIONS = ('--svg', '--out', '--output', '-o', '--png', '--save', '--to')


def _written(words) -> str | None:
    """The file a command names as its output ("--svg out.svg", "--svg=out.svg"), or None. "-o" counts only before a
    file name with an extension: it has other meanings too (review of J11-G24)."""
    for i, word in enumerate(words):
        flag, sep, value = str(word).partition('=')
        if flag in OUTPUT_OPTIONS and sep and value:
            return value
        if word in OUTPUT_OPTIONS and i + 1 < len(words):
            target = str(words[i + 1])
            if word != '-o' or re.search(r'\.[A-Za-z0-9]{1,5}$', target):
                return target
    return None
DECOY_WORDS = ('violet walrus', 'paper comet', 'amber otter', 'silent tuba', 'velvet anchor', 'copper giraffe',
               'frozen trumpet', 'woolly lantern')


def questions(proposal, context: str = '') -> list[dict[str, Any]]:
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
        for line in example.get('file_lines') or []:
            # The check passes when some place has the text followed by the number, so the question asks exactly that,
            # with its negation (journey J11-G25: "which number comes first after data-ember" was 0 of embers 0-8;
            # verifier: a list question can always be parroted with a padded list).
            number = int(line['number']) if float(line['number']).is_integer() else line['number']
            decoy = decoy or (test, f'After the steps, must the file {line["name"]} contain')
            both(test, f'After the steps, does the file {line["name"]} have “{line["has"]}” followed by the number '
                       f'{number} somewhere?',
                 f'After the steps, is every number that follows “{line["has"]}” in the file {line["name"]} different '
                 f'from {number}?')
        for files in example.get('lacks') or []:          # journey J11-G19
            for text in files.get('texts') or []:
                decoy = decoy or (test, f'After the steps, must the file {files["name"]} contain')
                both(test, f'After the steps, must the file {files["name"]} leave out “{text}”?',
                     f'After the steps, must the file {files["name"]} contain “{text}”?')
    for check in proposal.get('checks') or []:
        # A check that already passes today is kept only when the milestone requires it, as "without a style the
        # picture stays as it is" does (journey J11-G18; review: dropped outright, a check that passes today by
        # accident went unexamined). A yes-sayer or a no-sayer answers both the same way and is not counted.
        if check.get('passes_today') and isinstance(check.get('says'), str) and check['says'].strip():
            said = check['says'].strip()[:300]
            both(check['test'], f'Does the milestone require this, which the project already does today: “{said}”?',
                 f'Could a project meet the milestone without this: “{said}”?', about='unchanged')
    if decoy and units:
        # One question whose honest answer is always "no", about a command or, for checks on files only, a file
        # (final autopilot check: checks without steps had none).
        # Two plainly unrelated words, never the project's own vocabulary (journey J11-G20: "rs-" and hex digits looked
        # like this project's own SVG ids, rs-light and rs-glow, and the second model said yes to it).
        digest = hashlib.sha256(json.dumps(proposal.get('examples'), sort_keys=True, default=str).encode('utf-8')).hexdigest()
        # What the second model reads: the examples, and the milestone and other checks (review of J11-G20).
        seen = (json.dumps(proposal.get('examples'), ensure_ascii=False, default=str) + ' ' + context).lower()
        start = int(digest[:8], 16)
        pairs = [DECOY_WORDS[(start + i) % len(DECOY_WORDS)] for i in range(len(DECOY_WORDS))]
        words = min(pairs, key=lambda w: sum(bool(re.search(r'\b' + re.escape(part) + r'\b', seen)) for part in w.split()))
        token = f'{words} {digest[:4]}'
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


def second_model(ws, drafted_by, skip=()) -> str | None:
    """A usable instrument for the Checker's or the Planner's role that is not the model which wrote the checks, and
    not one of `skip` (the ones already asked about these checks)."""
    config = ws.config()
    wrote = _family(drafted_by)
    for role in ('acceptance', 'plan'):
        for name in (config.get('roles') or {}).get(role) or []:
            spec = (config.get('instruments') or {}).get(name) or {}
            models = [spec.get('model')] + list(spec.get('fallback_models') or [])
            if (name not in skip and spec.get('kind') != 'manual' and models[0] and ws._usable(name, spec)
                    and all(_family(m) != wrote for m in models)):
                return name
    return None


def _documents(ws) -> str:
    """The documents the owner shared with models, at most DOCUMENTS characters of them."""
    try:
        return ws.blueprint_text(DOCUMENTS)[:DOCUMENTS]
    except (OSError, WorkspaceError):
        return ''


def _packet(ws, milestone_id, proposal, asked) -> dict[str, Any]:
    from runesmith.app.acceptance_proposals import _milestone, _other_checks, proven_inputs
    from runesmith.app.planner import program_excerpts
    milestone = _milestone(ws, milestone_id)
    by_test = {}
    for row in asked:
        by_test.setdefault(row['test'], []).append({'id': row['id'], 'question': row['question']})
    return {'task': TASK,
            'milestone': {k: milestone.get(k) for k in ('title', 'detail', 'done_when')},
            'other_milestones_checks': _other_checks(ws, milestone_id),
            # What the program reads, which the second model is never shown: input files of checks that pass today, and
            # the owner's own documents (journey J11-G38: it "worked out the same 23 expected values" of examples whose
            # camera was written as timeline elements, where the owner's HOUSE_RULES.md says a list of keyframes).
            'proven_inputs': proven_inputs(ws, milestone_id),
            'documents': _documents(ws),
            # The lines of the program the Checker was shown, so the examples are worked out from its code (J11-B16).
            **({'program_excerpts': excerpts} if (excerpts := program_excerpts(ws, milestone)) else {}),
            'examples': [{'name': e['test'], 'files': e.get('files') or [],
                          'steps': [_command(s) for s in e.get('steps') or [] if _command(s)],
                          'questions': by_test.get(e['test'], [])} for e in proposal.get('examples') or []]}


def _misplaced(value) -> list[str]:
    """The sentences the second model gave for fields written under another name or in another place; an empty list
    for none, for "none", and for what is not text."""
    found = []
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, str) and (said := _contradiction(item)):
            found.append(' '.join(said.split())[:240])
    return found[:5]


def cross_check(ws, milestone_id, proposal) -> dict[str, Any]:
    """Ask a second model; {'model', 'disagreements': [...], 'misplaced': [...], 'contradicts': str|None} or
    {'undecided': why}.

    When that model gave no clear judgement (unclear answers, a pair answered the same both ways, a decoy it said yes
    to), ONE more model is asked: a different instrument that is still not the drafter's family, its answer judged by
    the same rules. Journey J11-CC5: the owner was away for 36 hours, and Envelope's sound checks waited for him
    because one free model answered unclearly. Both attempts are kept under 'attempts'; only when the second is
    undecided too do the checks wait for the owner. No second model, a model that did not answer, and a claimed
    contradiction are not asked again.
    """
    name = second_model(ws, proposal.get('drafted_by'))
    if name is None:
        return {'undecided': 'there is no second model to cross-check with (add another under Thinking power)'}
    first = _ask_second(ws, milestone_id, proposal, name)
    if not first.pop('retry', False):
        return first
    other = second_model(ws, proposal.get('drafted_by'), skip=(name,))
    if other is None:
        return first
    second = _ask_second(ws, milestone_id, proposal, other, 'again-')
    second.pop('retry', None)
    second['attempts'] = [{k: attempt[k] for k in ('model', 'undecided', 'answers') if k in attempt}
                          for attempt in (first, second)]
    if second.get('undecided'):
        second['undecided'] = f"{first['undecided']}; asked once more: {second['undecided']}"
    return second


def _ask_second(ws, milestone_id, proposal, name, key='') -> dict[str, Any]:
    """One second model's cross-check; a dict with 'retry' when it gave no clear judgement, so another may be asked."""
    from runesmith.config import build_router
    from runesmith.app.acceptance_proposals import _milestone, _other_checks
    try:
        context = json.dumps({'milestone': {k: _milestone(ws, milestone_id).get(k) for k in ('title', 'detail', 'done_when')},
                              'others': _other_checks(ws, milestone_id)}, ensure_ascii=False, default=str)
    except Exception:                               # the decoy then avoids only the examples' own words
        context = ''
    asked = questions(proposal, context)
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
                          key='autopilot-' + key + str(proposal.get('id')))
    except Exception as error:
        return {'undecided': f'the cross-check got no answer ({str(error)[:160]})', 'model': name}
    if not out.ok or not isinstance(out.data, dict):
        return {'undecided': f'the cross-check answer was unusable ({(out.error or "no JSON")[:160]})', 'model': name}
    answers = {str(a.get('id')): a.get('answer') for a in out.data.get('answers') or [] if isinstance(a, dict)}
    # Kept with the decision, so the owner can see what was asked and answered (journey J11-F15).
    record = [{'test': row['test'], 'question': row['question'][:300], 'expected': row['expected'],
               'answer': str(answers.get(row['id']))[:160]} for row in asked][:40]
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
                                                                          if fooled else '') + ')', 'model': model,
                'answers': record, 'retry': True}
    disagreements = [f"{row['test']}: {row['question']} The checks expect {row['expected']}; {model} worked out "
                     f"{answers.get(row['id'])}." for row in asked
                     if judged[row['id']] is False and row['about'] != 'decoy' and not row['twin']]
    said = out.data.get('contradicts')
    contradicts = (str(out.data.get('contradiction') or 'yes, without saying which').strip()[:400] if said is True
                   else None if said is False else _contradiction(said))
    return {'model': model, 'asked': len(asked), 'disagreements': disagreements, 'contradicts': contradicts,
            'misplaced': _misplaced(out.data.get('misplaced')), 'answers': record}


def rounds_used(ws, milestone_id) -> int:
    """Proposals the autopilot turned down since the last approval of this milestone's checks, and since the owner
    last withdrew them."""
    from runesmith.app.acceptance_proposals import _proposal_rows
    # A turn-down made after the approval but before the owner's withdrawal sits behind the withdrawn row in the list,
    # and was judged by checks he took back: the withdrawal marks every row then made, and only the rows after the
    # newest mark count. A mark, not a position: the record keeps ten rows, and a position moves when it trims
    # (review of J11-G37).
    used = 0
    for row in reversed(_proposal_rows(ws, milestone_id)):
        if row.get('state') in ('approved', 'replaced', 'withdrawn') or row.get('before_withdrawal'):
            break
        used += (row.get('autopilot') or {}).get('decision') == 'turned_down'
    return used


def review(ws, milestone_id, proposal) -> dict[str, Any]:
    """Decide on one waiting proposal: {'decision': 'approve'|'turn_down'|'owner', 'reason': ..., ...}."""
    from runesmith.app.acceptance_proposals import _milestone, status
    approved = (status(ws).get(milestone_id) or {}).get('approved')
    if approved and approved.get('provenance') != 'model-proposed, autopilot-approved':
        return {'decision': 'owner', 'reason': 'you approved the checks now in force; only you replace them'}
    why = undecidable(proposal)
    if why:
        return {'decision': 'owner', 'reason': why}
    found = gates(proposal, _milestone(ws, milestone_id).get('done_when'))
    if not found:
        check = cross_check(ws, milestone_id, proposal)
        if check.get('undecided'):
            return {'decision': 'owner', 'reason': check['undecided'], 'cross_check': check}
        # A field written under another name or in another place than the program reads it (journey J11-G38) is a
        # turn-down like a disagreement: the examples cannot pass a correct build.
        misplaced = [f"{check['model']} found a field written differently from the proven inputs and the milestone: {s}"
                     for s in check.get('misplaced') or []]
        if check['contradicts'] and not (check['disagreements'] or misplaced):
            # A second model's claim of a contradiction may itself be wrong; it is the owner's call, never a turn-down
            # (final autopilot check: "Nope, these are consistent." once read as a contradiction).
            return {'decision': 'owner', 'reason': f"{check['model']} says these contradict another milestone's checks: "
                                                   f"{check['contradicts']}", 'cross_check': check}
        found = check['disagreements'] + misplaced
        if not found:
            return {'decision': 'approve', 'reason': f"trial and findings clean; {check['model']} worked out the same "
                    f"{check['asked']} expected values", 'cross_check': check}
    if rounds_used(ws, milestone_id) >= MAX_ROUNDS:
        return {'decision': 'owner', 'reason': f'turned down {MAX_ROUNDS} times already; these wait for you: '
                + '; '.join(found)[:600], 'findings': found}
    return {'decision': 'turn_down', 'reason': '; '.join(found)[:1000], 'findings': found}


def needs_checks(ws) -> str | None:
    """A ready milestone with no checks and nothing proposed or waiting, which the autopilot may ask for."""
    from runesmith.app.acceptance_proposals import acceptance_file, _proposal_rows
    from runesmith.app.planner import ready_milestones
    for milestone in ready_milestones(ws.plan()):
        if acceptance_file(ws, milestone['id']).is_file():
            continue
        proposals = _proposal_rows(ws, milestone['id'])
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
    from runesmith.app.acceptance_proposals import _proposal_rows, acceptance_file, approve, discard, note_autopilot
    current = next((row for row in _proposal_rows(ws, milestone_id)
                    if row.get('id') == proposal['id']), None)
    if not current or current.get('state') != 'proposed':
        return 'You decided about these checks meanwhile; the autopilot left them alone.', 'none'
    note = {k: verdict.get(k) for k in ('decision', 'reason', 'findings') if verdict.get(k)}
    if verdict.get('cross_check'):
        note['cross_check'] = {k: verdict['cross_check'].get(k) for k in ('model', 'asked', 'contradicts', 'misplaced',
                                                                             'answers', 'attempts')
                               if k in verdict['cross_check']}
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
