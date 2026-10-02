"""Acceptance checks from examples: the first slice of docs/design/WEAK_MODEL_CHECKS.md.

Free models wrote checks that rejected correct builds (overnight experiment 2026-09-28: 16 of 17 answered proposals
failed a correct build). They required an exact layout, invented a message, or read a line by position. Here the model
only describes what a person would try by hand, as data: prepare files or earlier commands, run the program, and say
what the result shows. Runesmith turns that into the checks file with its own trusted template:
  - text is matched whole, ignoring case (so "2" never matches inside "2026"), and a number is looked for on the
    line that names its subject, wherever the layout puts it;
  - a text the milestone never mentions and the example never typed in is dropped before the owner sees it, and
    the owner is told, because it would reject a correct build that words things differently;
  - what is checked exactly is written out by Runesmith from the same data, so a sentence cannot promise less than
    the check requires.
The rendered file never imports runesmith and runs every example in its own fresh copy of the project.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
from typing import Any

from runesmith.app.workspace import WorkspaceError
from runesmith.instruments import LenientSchema

# Kept lenient on purpose: a strict provider (Groq) refuses a whole answer that misses a schema detail, while
# Runesmith checks every value itself and can tell the model what to fix.
STRINGS = {'type': 'array', 'items': {'type': 'string'}}
EXPECT = {'type': 'object', 'properties': {
    'exit': {'type': 'string'},
    'shows': STRINGS, 'hides': STRINGS, 'order': STRINGS,
    'lines': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'has': {'type': 'string'}, 'number': {'type': 'number'}}, 'required': ['has', 'number']}},
    'message': {'type': 'boolean'},
    'returns_json': {'type': 'string'}, 'raises': {'type': 'string'}}}
STEP = {'type': 'object', 'properties': {
    'run': STRINGS, 'input': {'type': 'string'}, 'fault': {'type': 'string'},
    'call': {'type': 'string'}, 'args_json': {'type': 'string'},
    'doc': {'type': 'string'}, 'program': STRINGS, 'mention': STRINGS,
    'expect': EXPECT}}
SCHEMA = LenientSchema({'type': 'object', 'properties': {
    'examples': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'name': {'type': 'string'}, 'says': {'type': 'string'},
        'files': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'name': {'type': 'string'}, 'text': {'type': 'string'}}, 'required': ['name', 'text']}},
        'steps': {'type': 'array', 'items': STEP},
        'unchanged': STRINGS, 'exists': STRINGS,
        'contains': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'name': {'type': 'string'}, 'texts': STRINGS}, 'required': ['name', 'texts']}},
        'lacks': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'name': {'type': 'string'}, 'texts': STRINGS}, 'required': ['name', 'texts']}},
        'file_lines': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'name': {'type': 'string'}, 'has': {'type': 'string'}, 'number': {'type': 'number'}},
            'required': ['name', 'has', 'number']}},
        'links_resolve': {'type': 'boolean'}, 'pages_reachable': {'type': 'boolean'}},
        'required': ['name', 'says']}},
    'not_checked': STRINGS}, 'required': ['examples']})

TASK = (
    "Describe the owner's acceptance checks for ONE milestone as EXAMPLES, not code. Runesmith turns each example "
    "into a check with its own trusted code. An example is what a person would try by hand: prepare files or run "
    "earlier commands, run the program, and look at the result. Each example runs in a fresh copy of the project "
    "folder, so any file it names is relative to that folder.\n"
    "- A step {\"run\": [words]} runs a command exactly as a person types it in the project folder. It starts with "
    "\"python\" followed by \"-m\" and a module, or by a script path, or with \"node\" and a script path. Use the "
    "command the milestone or README documents, with arguments the program accepts (see source_context). An empty "
    "word \"\" is an empty argument, as typed with two quotes.\n"
    "- A command that writes its result to a file (for example --svg out.svg or -o out.txt) often prints nothing: "
    "check that file with \"contains\", \"lacks\" or \"file_lines\", never with \"shows\" on the printed output.\n"
    "- A step without \"expect\" prepares the example and must succeed. On the step whose result matters, "
    "\"expect\" may say: \"exit\": \"ok\" or \"error\"; \"shows\": texts the output must contain; \"hides\": texts it "
    "must not contain; \"lines\": [{\"has\": text, \"number\": n}] for a line that shows that text together with "
    "that number; \"order\": texts that must appear in that order; \"message\": true when a problem must be "
    "explained in words.\n"
    "- Require only what the milestone states. Never invent a wording, heading or layout: every text you expect "
    "must come from the milestone's own words or from this example's own input (a title you added, a date you "
    "used). Runesmith drops any other text.\n"
    "- \"owner_said_about_earlier_checks\" is what the owner said when turning down earlier checks for this "
    "milestone, and \"owner_said_about_other_milestones_checks\" what they said about other milestones' checks. "
    "Do not repeat those mistakes.\n"
    "- \"other_milestones_checks\" lists the checks the owner already approved for other milestones of this "
    "project. Stay consistent with them: use the same file format, file names and commands, and never require "
    "what one of them forbids (if one says a file is refused, do not require the same file to be accepted).\n"
    "- \"proven_inputs\" are input files from checks that pass on the program today: write new inputs in the same "
    "format (field names, nesting, where a setting sits) unless the milestone itself changes that format.\n"
    "- \"fault\": \"interrupted_write\" on a python run step makes every file write inside the folder stop halfway, "
    "as if the power failed. Use it when the milestone promises safety against interruption, then check the result "
    "with a later step.\n"
    "- \"files\": [{\"name\", \"text\"}], on the example next to \"steps\", creates files before the steps (for "
    "example a damaged data file). A file "
    "a step hands the program must exist: create it with \"files\" or an earlier step, or use one the project "
    "has (source_context lists them); another example's files are not there, so list every file an example runs "
    "in that example's own \"files\". "
    "\"unchanged\": [names of files this example creates with \"files\"] checks that they are exactly the same "
    "afterwards (to check that a program leaves its data alone, create that data file with \"files\"); \"exists\": [names]; "
    "\"contains\": [{\"name\", \"texts\"}] checks a file's text afterwards (never use \"files\" to say what "
    "the finished project should contain: those files are created before the steps); \"lacks\": [{\"name\", \"texts\"}] "
    "checks that a file afterwards contains none of those texts (for \"there is no X in the file\"; never put a text "
    "that must be absent under \"contains\"); \"file_lines\": [{\"name\", \"has\", \"number\"}] checks that in "
    "that file the first number after the text \"has\", or the text of the element that holds it, is \"number\" (for "
    "\"out.svg has stroke-dashoffset 57.5\" or a label <text class=\"x\">120</text>; "
    "never write the layout, such as 'stroke-dashoffset=\"57.5\"', under \"contains\"); \"links_resolve\": true checks that every "
    "link between the Markdown pages leads to an existing file; \"pages_reachable\": true checks that every Markdown "
    "page can be reached by following links from the front page (README.md or index.md). For documents there is often "
    "no program to run: then an example has no steps and only these file checks, and \"documents\" shows the pages "
    "the owner chose to share.\n"
    "- To check the examples in a document: {\"doc\": \"README.md\", \"program\": [\"python\", \"-m\", \"pkg\"], "
    "\"mention\": [words]}. The document must show the program with each mentioned word, and every example "
    "without placeholders must run without an error.\n"
    "- For a Python function the milestone names: {\"call\": \"package.module.function\", \"args_json\": \"[...]\", "
    "\"expect\": {\"returns_json\": \"...\"} or {\"raises\": \"ErrorName\"}}.\n"
    "Give 2 to 6 examples. Each has \"name\" (a few words in snake_case), \"says\" (one plain sentence a "
    "non-programmer understands) and \"steps\" (empty when it only checks files). Together they should fail on a project that lacks what this "
    "milestone adds and pass once it is built. If part of the milestone cannot be checked this way, say so in "
    "\"not_checked\", in plain words. The feature may not exist yet: do not implement it. Return JSON only.")
REVISE = ("Runesmith tried your examples once on a copy of the project as it is today. {finding} Revise them so that "
          "each example fails on a project that lacks what this milestone adds and passes once it is built. If the "
          "project already does everything the milestone says, return the same examples and say so in "
          "\"not_checked\". Same JSON shape.")
UNUSABLE = "Runesmith could not use your answer: {error} Same JSON shape, following the rules above."

PYTHONS = ('python', 'python3', 'py')
MODULE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*')
FUNCTION = re.compile(r'[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+')
SCRIPT = re.compile(r'[^\\/:*?"<>|]+(/[^\\/:*?"<>|]+)*\.(py|js|mjs|cjs)')
ABSOLUTE = re.compile(r'^([\\/]|[A-Za-z]:)')
LIMITS = {'examples': 8, 'steps': 12, 'words': 40, 'word': 300, 'files': 8, 'file': 20000, 'texts': 12, 'text': 200}


def _plain(value, what, limit=LIMITS['text']):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise WorkspaceError(f'{what} must be text of 1-{limit} characters.')
    return value.strip()


def _texts(value, what):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > LIMITS['texts']:
        raise WorkspaceError(f'{what} must be a list of at most {LIMITS["texts"]} texts.')
    return [_plain(v, what) for v in value]


def _notes(value, limit=400):
    """What the examples leave unchecked, in the Checker's words, for the owner to judge.

    A long note is shortened, never a reason to refuse the whole answer (journey J2-F8: a 220-character note did).
    """
    notes = []
    for note in ([value] if isinstance(value, str) else value if isinstance(value, list) else [])[:8]:
        if isinstance(note, str) and note.strip():
            note = ' '.join(note.split())
            notes.append(note if len(note) <= limit else note[:limit - 1].rsplit(' ', 1)[0] + '…')
    return notes


EXIT_WORDS = {'ok': 'ok', 'success': 'ok', 'succeeds': 'ok', 'pass': 'ok', 'passes': 'ok', 'zero': 'ok', '0': 'ok',
              'error': 'error', 'fail': 'error', 'fails': 'error', 'failure': 'error', 'nonzero': 'error',
              'non-zero': 'error', 'non_zero': 'error', 'any': 'any'}


def _exit_word(value):
    """ok, error or any, from the words a model uses for them (checker experiment 2026-09-28: a whole answer was
    refused twice over this). A number means its exit code: 0 is ok, anything else an error."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return 'ok' if value == 0 else 'error'
    if isinstance(value, str):
        word = value.strip().lower()
        return EXIT_WORDS.get(word, 'error' if word.isdigit() else value)
    return value


def _command_word(step) -> str | None:
    """The subcommand a run step names right after the program ("count" in python -m readinglog count), if any."""
    words = step.get('run') or []
    rest = words[3:] if len(words) > 2 and words[1] == '-m' else words[2:]
    first = rest[0] if rest else ''
    return first if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', first) else None


def _mentioned(word: str, text: str) -> bool:
    return re.search(r'(?<![A-Za-z0-9_])' + re.escape(word.lower()) + r'(?![A-Za-z0-9_])', text.lower()) is not None


def _options(step) -> list[str]:
    """The long options a run step passes its program ("--svg" in node motion.mjs a.json --svg out.svg)."""
    words = step.get('run') or []
    rest = words[3:] if len(words) > 2 and words[1] == '-m' else words[2:]
    found = []
    for word in rest:
        name = str(word).partition('=')[0]
        if re.fullmatch(r'--[A-Za-z][A-Za-z0-9_-]*', name) and name not in found:
            found.append(name)
    return found


def _option_named(option: str, text: str) -> bool:
    """The option itself ("--svg"), or its bare name as a word of its own ("PNG" for --png), is in the text; a piece
    of another hyphenated name (a file export-png-helper.js, a class btn-export-png) does not count (review of
    J11-G30: it let an invented --export-png through)."""
    if _mentioned(option, text):
        return True
    bare = re.escape(option[2:].lower())
    return re.search(r'(?<![A-Za-z0-9_-])' + bare + r'(?![A-Za-z0-9_-])', text.lower()) is not None


def _same_file(name):
    """A project file name as the file is found, so two spellings of one file compare equal."""
    return posixpath.normpath(name).casefold()


def _relative(name, what):
    name = _plain(name, what, 200).replace('\\', '/')
    parts = name.split('/')
    if ABSOLUTE.match(name) or '..' in parts or parts[0] in ('.git', '.runesmith'):
        raise WorkspaceError(f'{what} must be a file inside the project, not {name!r}.')
    return name


def _command(words, what, *, program_only=False):
    """A command a person types: python -m module, python script.py, or node script.js, then plain arguments."""
    # An empty argument is allowed (journey J2-F3: "an empty query is refused" needs `--query ""`); the program
    # part below still has to be a real python or node command.
    if not isinstance(words, list) or not words or len(words) > LIMITS['words'] or any(
            not isinstance(w, str) or len(w) > LIMITS['word'] for w in words):
        raise WorkspaceError(f'{what} must be a list of 1-{LIMITS["words"]} words.')
    first = words[0].lower()
    if first in PYTHONS:
        if len(words) >= 3 and words[1] == '-m' and MODULE.fullmatch(words[2]):
            rest = words[3:]
        elif len(words) >= 2 and SCRIPT.fullmatch(words[1]) and words[1].endswith('.py'):
            rest = words[2:]
        else:
            raise WorkspaceError(f'{what} must run "python -m <module>" or "python <script>.py", not {" ".join(words)!r}.')
    elif first == 'node' and len(words) >= 2 and SCRIPT.fullmatch(words[1]) and not words[1].endswith('.py'):
        rest = words[2:]
    else:
        raise WorkspaceError(f'{what} must start with python or node, not {words[0]!r}.')
    if program_only and rest:
        raise WorkspaceError(f'{what} names the program only, without arguments.')
    if any(ABSOLUTE.match(w) or '..' in w.replace('\\', '/').split('/') for w in words[1:]):
        raise WorkspaceError(f'{what} may only use files inside the project folder.')
    return [('python' if first in PYTHONS else words[0]), *words[1:]]


def _expect(value, kind, what):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorkspaceError(f'{what}: "expect" must be an object.')
    out = {}
    value = dict(value, exit=_exit_word(value.get('exit')))
    if value.get('exit') not in (None, 'ok', 'error', 'any'):
        raise WorkspaceError(f'{what}: "exit" is ok, error or any.')
    if value.get('exit'):
        out['exit'] = value['exit']
    for key in ('shows', 'hides', 'order'):
        if texts := _texts(value.get(key), f'{what}: "{key}"'):
            out[key] = texts
    lines = value.get('lines') or []
    if not isinstance(lines, list) or len(lines) > LIMITS['texts']:
        raise WorkspaceError(f'{what}: "lines" must be a short list.')
    for row in lines:
        number = row.get('number') if isinstance(row, dict) else None
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            raise WorkspaceError(f'{what}: each line needs "has" and a "number".')
        out.setdefault('lines', []).append({'has': _plain(row.get('has'), f'{what}: "lines"'), 'number': number})
    if value.get('message'):
        out['message'] = True
    if kind == 'call':
        if 'returns_json' in value and value['returns_json'] not in (None, ''):
            try:
                out['returns'] = json.loads(value['returns_json'])
            except (TypeError, ValueError):
                raise WorkspaceError(f'{what}: "returns_json" is not valid JSON.') from None
        if value.get('raises'):
            out['raises'] = _plain(value['raises'], f'{what}: "raises"', 100)
    return out


def _step(value, what):
    if not isinstance(value, dict):
        raise WorkspaceError(f'{what} must be an object.')
    kinds = [k for k in ('run', 'call', 'doc') if value.get(k)]
    if len(kinds) != 1:
        raise WorkspaceError(f'{what} needs exactly one of "run", "call" or "doc".')
    kind = kinds[0]
    step: dict[str, Any] = {}
    if kind == 'run':
        step['run'] = _command(value['run'], what)
        if value.get('fault') not in (None, '', 'none', 'interrupted_write'):
            raise WorkspaceError(f'{what}: the only fault is "interrupted_write".')
        if value.get('fault') == 'interrupted_write':
            if step['run'][0] != 'python':
                raise WorkspaceError(f'{what}: an interrupted write can only be simulated for a Python program.')
            step['fault'] = 'interrupted_write'
        if isinstance(value.get('input'), str) and value['input']:
            step['input'] = value['input'][:2000]
    elif kind == 'call':
        target = _plain(value['call'], f'{what}: "call"', 200)
        if not FUNCTION.fullmatch(target):
            raise WorkspaceError(f'{what}: "call" names a public function as package.module.function.')
        try:
            args = json.loads(value.get('args_json') or '[]')
        except ValueError:
            raise WorkspaceError(f'{what}: "args_json" is not valid JSON.') from None
        if not isinstance(args, list) or len(json.dumps(args)) > 4000:
            raise WorkspaceError(f'{what}: "args_json" must be a JSON list.')
        step.update(call=target, args=args)
    else:
        step['doc'] = _relative(value['doc'], f'{what}: "doc"')
        step['program'] = _command(value.get('program'), f'{what}: "program"', program_only=True)
        step['mention'] = _texts(value.get('mention'), f'{what}: "mention"')
    expect = _expect(value.get('expect'), kind, what)
    if kind == 'run' and step.get('fault') and expect:
        # What an interrupted run itself prints or returns proves nothing; a later step checks what it left behind.
        step['unchecked_expect'] = True
        expect = {}
    if kind == 'call' and 'returns' not in expect and 'raises' not in expect:
        raise WorkspaceError(f'{what}: a call needs "returns_json" or "raises".')
    if expect:
        step['expect'] = expect
    return step


def _inputs(example) -> str:
    """Everything the example itself types in: an expected text may repeat it."""
    parts = [f['text'] for f in example.get('files', [])]
    for step in example['steps']:
        parts += step.get('run', []) + [step.get('input', ''), json.dumps(step.get('args', []), ensure_ascii=False)]
    return ' '.join(parts).lower()


TOKEN = re.compile(r"[^\W_](?:[\w.'-]*[^\W_])?")
NUMBER_TOKEN = re.compile(r'\d+(?:\.\d+)?')
WHOLE_ATTRIBUTE = re.compile(r'[A-Za-z][\w:.-]*\s*=\s*("[^"]*"|\'[^\']*\')')
ATTRIBUTE_NUMBER = re.compile(r'\s*([A-Za-z][\w:.-]*)\s*[=:]\s*["\']?(-?\d+(?:\.\d+)?)(?:px|%|em|s|ms)?["\']?\s*;?\s*')


def _loosen(text, inputs):
    """The parts of an over-specified text that the example itself typed in, and the numbers in it.

    "2026-01 2" becomes the subject "2026-01" with the number 2, and "Added 'Tea'" becomes "Tea". The loosened check
    accepts every output the original did, so it can only stop rejecting a correct build for its layout or wording.
    """
    typed = set(TOKEN.findall(inputs))
    found = list(TOKEN.finditer(text))

    def own(word):
        # Short words are kept only as a key the example's own data names ("x" of {"x": 0}); other short words
        # ("a", "to") say nothing. Journey J11-G12: "x 50" was dropped, so s1's checks passed a program that
        # printed nothing at all.
        return len(word) >= 3 or f'"{word.lower()}"' in inputs

    # A whole word the example typed in, or the leading part of one (the month "2026-01" of the date "2026-01-05").
    kept = [m for m in found if not NUMBER_TOKEN.fullmatch(m.group()) and own(m.group()) and (
        m.group().lower() in typed or any(u.startswith(m.group().lower() + sep) for u in typed for sep in '-./:'))]
    # Neighbouring words that were typed in together stay one phrase: "The Hobbit", not "The" and "Hobbit".
    subjects, start, end = [], None, None
    for m in kept:
        if start is not None and text[start:m.end()].lower() in inputs:
            end = m.end()
            continue
        if start is not None:
            subjects.append(text[start:end])
        start, end = m.start(), m.end()
    if start is not None:
        subjects.append(text[start:end])
    numbers = [float(m.group()) for m in found if NUMBER_TOKEN.fullmatch(m.group())]
    return subjects, numbers


def _number(value):
    return int(value) if float(value).is_integer() else value


def _ground(example, milestone_text, source_text):
    """Keep expected texts the milestone states or the example typed in; loosen or drop the rest, and say which.

    A free model tends to require its own guess of the layout ("2026-01 2", "Added 'Tea'", "No books"). A correct
    build that words it differently would fail, so such text is loosened to what the example itself typed in, with
    the number next to it, or dropped when nothing of it is the example's own.
    """
    inputs = _inputs(example)
    known = milestone_text.lower() + ' ' + inputs
    changed = []

    def plain(value):
        return ' ' + ' '.join(re.findall(r'[a-z0-9]+', value.lower())) + ' '

    known_words = plain(known)
    emptied = []                                   # files whose contains/lacks lost every text
    def stated_after(name, number) -> bool:
        """Whether the milestone or the example's input states this number after this name, in the same sentence,
        as a number of its own (verifier of batch L: a flat set of every number, the digits of "m2" and "#1b2130"
        included, rescued a number stated for another name)."""
        for match in re.finditer(r'(?<![\w-])' + re.escape(name.lower()) + r'(?![\w-])', known):
            sentence = re.split(r'\.(?=\s|$)', known[match.end():match.end() + 160], maxsplit=1)[0]
            if any(float(n) == number for n in re.findall(r'(?<![\w#.-])-?\d+(?:\.\d+)?(?!\w|\.\d)', sentence)):
                return True
        return False

    def grounded(text, extra=''):
        if text.lower() in known or bool(extra and text.lower() in extra):
            return True
        # The same words in the same order, ignoring punctuation and spacing: "<svg" follows from a milestone that says
        # SVG, and 'x="10"' from an input with "x": 10. A guessed layout ("Added Tea", "No books") still does not
        # (journey J11-G8: every expected SVG text was dropped).
        words = plain(text)
        return words.strip() != '' and (words in known_words or bool(extra and words in plain(extra)))

    for step in example['steps']:
        expect = step.get('expect')
        if not expect:
            continue
        shown = _show(step)
        shows, lines, order = [], list(expect.get('lines', [])), []
        for text in expect.get('shows', []):
            if grounded(text):
                shows.append(text)
                continue
            subjects, numbers = _loosen(text, inputs)
            if subjects and len(numbers) == 1:
                lines.append({'has': subjects[-1], 'number': _number(numbers[0])})
                shows += subjects[:-1]
                changed.append(f'the output of {shown} shows “{text}” (checked instead: a line with “{subjects[-1]}” '
                               f'shows the number {_number(numbers[0])})')
            elif subjects:
                shows += subjects
                changed.append(f'the output of {shown} shows “{text}” (checked instead: it shows {_quote(subjects)})')
            else:
                changed.append(f'the output of {shown} shows “{text}”')
        for text in expect.get('order', []):
            if grounded(text):
                order.append(text)
                continue
            subjects, numbers = _loosen(text, inputs)
            if subjects:
                order.append(subjects[0])
                if len(numbers) == 1:
                    lines.append({'has': subjects[0], 'number': _number(numbers[0])})
                changed.append(f'the output of {shown} lists “{text}” (checked instead: “{subjects[0]}”'
                               + (f' with the number {_number(numbers[0])})' if len(numbers) == 1 else ')'))
            else:
                changed.append(f'the output of {shown} lists “{text}”')
        kept_lines = []
        for row in lines:
            if grounded(row['has']):
                kept_lines.append(row)
            elif subjects := _loosen(row['has'], inputs)[0]:
                kept_lines.append(dict(row, has=subjects[0]))
                changed.append(f'the output of {shown} has a line with “{row["has"]}” (checked instead: “{subjects[0]}”)')
            else:
                changed.append(f'the output of {shown} has a line with “{row["has"]}”')
        hides = [t for t in expect.get('hides', []) if grounded(t)]
        changed += [f'the output of {shown} does not show “{t}”' for t in expect.get('hides', []) if t not in hides]
        unique = lambda items: list(dict.fromkeys(items))
        expect.update(shows=unique(shows), hides=hides, order=unique(order) if len(unique(order)) >= 2 else [],
                      lines=[dict(r) for r in {(r['has'].lower(), r['number']): r for r in kept_lines}.values()])
        for key in [k for k, v in expect.items() if v in ([], None)]:
            expect.pop(key)
        if not expect:
            step.pop('expect')
    for step in example['steps']:
        if 'mention' in step:
            kept = [t for t in step['mention'] if grounded(t, source_text.lower())]
            changed += [f'{step["doc"]} mentions “{t}”' for t in step['mention'] if t not in kept]
            step['mention'] = kept
    for row in example.get('contains', []):
        texts = []
        for text in row['texts']:
            if grounded(text, source_text.lower()):            # a file may hold text the project already has
                texts.append(text)
            elif ((pair := ATTRIBUTE_NUMBER.fullmatch(text)) and grounded(pair.group(1))
                  and stated_after(pair.group(1), float(pair.group(2)))):     # the number too (review of J11-G21)
                # 'stroke-dashoffset="57.5"' guesses the layout; the number after the name is what the milestone
                # states (journey J11-G21: dropped, the self-drawing rune's checks never looked at its offset).
                example.setdefault('file_lines', []).append(
                    {'name': row['name'], 'has': pair.group(1), 'number': _number(float(pair.group(2)))})
                changed.append(f'{row["name"]} contains “{text}” (checked instead: the first number after '
                               f'“{pair.group(1)}” is {_number(float(pair.group(2)))})')
            elif subjects := _loosen(text, inputs)[0]:
                texts += subjects
                changed.append(f'{row["name"]} contains “{text}” (checked instead: {_quote(subjects)})')
            else:
                changed.append(f'{row["name"]} contains “{text}”')
        row['texts'] = list(dict.fromkeys(texts))
        if not row['texts']:
            emptied.append(row['name'])
    example['contains'] = [r for r in example.get('contains', []) if r['texts']]
    for row in example.get('lacks', []):
        # A text to remove is often one only the project has now ("the leftover debug banner"): grounded like
        # "contains" (review of J11-G19).
        # A single character is in almost every file: "lacks M" failed every correct build of the self-drawing
        # rune, whose path starts with M (journey J11-G23). Two characters ("px", "<g") may be stated (review).
        kept = [text for text in row['texts'] if len(text.strip()) > 1 and grounded(text, source_text.lower())]
        changed += [f'{row["name"]} leaves out “{text}”' for text in row['texts'] if text not in kept]
        row['texts'] = list(dict.fromkeys(kept))
        if not row['texts']:
            emptied.append(row['name'])
    example['lacks'] = [r for r in example.get('lacks', []) if r['texts']]
    kept_lines = []
    for row in example.get('file_lines', []):
        if grounded(row['has']):
            kept_lines.append(row)
        else:
            changed.append(f'{row["name"]}: the number after “{row["has"]}”')
    example['file_lines'] = [dict(r) for r in {(r['name'], r['has'].lower(), r['number']): r for r in kept_lines}.values()]
    # A file whose checks lost all their stated text is still checked to exist: without this, m5's checks ended up
    # checking nothing and passed on an empty folder (journey J11-B3). Only when no other check on it remains
    # (journey J11-B13: "checked instead that it exists" was said while its contents and offset were still
    # checked, and the check autopilot turned a good set down on it).
    remaining = ({r['name'] for r in example.get('contains', [])} | {r['name'] for r in example.get('lacks', [])}
                 | {r['name'] for r in example.get('file_lines', [])})
    for name in dict.fromkeys(emptied):
        if name not in remaining and name not in example.setdefault('exists', []):
            example['exists'].append(name)
            changed.append(f'{name}: checked instead that it exists')
    return changed


def _words(words) -> str:
    return ' '.join(json.dumps(w, ensure_ascii=False) if not w or re.search(r'[\s"]', w) else w for w in words)


def _show(step) -> str:
    if 'run' in step:
        return '`' + _words(step['run']) + '`'
    if 'call' in step:
        return '`' + step['call'] + '(' + ', '.join(json.dumps(a, ensure_ascii=False) for a in step['args']) + ')`'
    return '`' + step['doc'] + '`'


def _quote(texts):
    return ', '.join(f'“{t}”' for t in texts)


FILE_SHOWN = 600


def exact(example) -> str:
    """What the check requires, written by Runesmith from the same data the template checks."""
    # Whole, up to a limit: the file a check starts with is often the format the milestone defines, and a builder
    # that saw only its first 60 characters had to guess the rest (journey J11-G1).
    # Several long files would not fit, so their share shrinks until what is checked fits whole (review, 2026-09-28).
    for shown in (FILE_SHOWN, 300, 150, 60):
        text = _exact(example, shown)
        if len(text) <= EXACT_LIMIT:
            return text
    return text[:EXACT_LIMIT - 1] + '…'


EXACT_LIMIT = 900


def _exact(example, shown) -> str:
    parts = [f'starting with `{f["name"]}` containing “{f["text"][:shown]}{"…" if len(f["text"]) > shown else ""}”'
             for f in example.get('files', [])]
    preparation = []                        # steps that prepare the next one, in order
    for step in example['steps']:
        if 'run' in step and not step.get('expect') and not step.get('fault'):
            preparation.append(step)
            continue
        if preparation:
            ran = ', '.join(_show(s) for s in preparation[:2]) + (f' and {len(preparation) - 2} more' if len(preparation) > 2 else '')
            parts.append('after ' + ran)
            preparation = []
        expect = step.get('expect', {})
        if step.get('fault'):
            parts.append(f'{_show(step)} is interrupted while saving')
            continue
        if 'doc' in step:
            said = f'{_show(step)} shows `{" ".join(step["program"])}`'
            if step['mention']:
                said += ' with ' + _quote(step['mention'])
            parts.append(said + ', and every example there without placeholders runs without an error')
            continue
        said = ('calling ' if 'call' in step else 'running ') + _show(step)
        found = []
        exit_ = expect.get('exit') or ('any' if expect.get('message') or 'call' in step else 'ok')
        found += {'ok': ['it finishes normally'], 'error': ['it ends with an error'], 'any': []}[exit_]
        if expect.get('message'):
            found.append('it explains the problem in words')
        if 'returns' in expect:
            found.append('it returns ' + json.dumps(expect['returns'], ensure_ascii=False)[:200])
        if 'raises' in expect:
            found.append('it raises ' + expect['raises'])
        if expect.get('shows'):
            found.append('the output shows ' + _quote(expect['shows']))
        if expect.get('hides'):
            found.append('the output does not show ' + _quote(expect['hides']))
        for row in expect.get('lines', []):
            number = int(row['number']) if float(row['number']).is_integer() else row['number']
            found.append(f'a line with “{row["has"]}” also shows the number {number}')
        if expect.get('order'):
            found.append(_quote(expect['order']) + ' appear in that order')
        parts.append(said + (': ' + '; '.join(found) if found else ''))
    # Steps at the end with no expectation of their own still run and must finish normally; they were left out, so
    # the owner was shown less than was checked (journey J11-B2).
    parts += [f'running {_show(s)}: it finishes normally' for s in preparation]
    parts += [f'`{n}` is left exactly as it was' for n in example.get('unchanged', [])]
    parts += [f'`{n}` exists' for n in example.get('exists', [])]
    parts += [f'`{r["name"]}` contains ' + _quote(r['texts']) for r in example.get('contains', [])]
    parts += [f'`{r["name"]}` leaves out ' + _quote(r['texts']) for r in example.get('lacks', [])]
    parts += [f'in `{r["name"]}` the first number after “{r["has"]}” is '
              f'{int(r["number"]) if float(r["number"]).is_integer() else r["number"]}' for r in example.get('file_lines', [])]
    if example.get('links_resolve'):
        parts.append('every link between the Markdown pages leads to an existing file')
    if example.get('pages_reachable'):
        parts.append('every Markdown page can be reached by following links from the front page')
    text = '; '.join(parts) + ('; and nothing stops with a crash report.' if example['steps'] else '.')
    return text[:1].upper() + text[1:]


def _name(value, index, taken):
    slug = re.sub(r'[^a-z0-9]+', '_', str(value or '').lower()).strip('_')[:40] or 'example'
    name = f'test_{index:02d}_{slug}'
    while name in taken:
        name += '_'
    taken.add(name)
    return name


class NothingToCheck(WorkspaceError):
    """An example that neither runs anything nor checks a file (journey J11-G6)."""


def _joined(steps):
    """Steps with a lone expectation joined to the step before it. Weak models often write what to expect as a step
    of its own, as in [{"run": [...]}, {"expect": {...}}] (journey J11-G4: Nemotron, for m1, m2 and m5)."""
    joined = []
    for step in steps:
        previous = joined[-1] if joined else None
        if (isinstance(step, dict) and set(step) == {'expect'} and isinstance(previous, dict)
                and any(k in previous for k in ('run', 'call', 'doc')) and 'expect' not in previous):
            joined[-1] = dict(previous, expect=step['expect'])
        else:
            joined.append(step)
    return joined


FILE_CHECKS = ('exists', 'contains', 'lacks', 'file_lines', 'unchanged')


EXAMPLE_KEYS = {'name', 'says', 'files', 'steps', 'unchanged', 'exists', 'contains', 'lacks', 'file_lines',
                'links_resolve', 'pages_reachable'}


def _lifted(row, steps, what, dropped):
    """File checks written inside a step's "expect" moved to the example they belong to (journey J11-G9: for the SVG
    frame, the Checker put "exists" and "contains" for out.svg under the step that writes it). A "hides" naming a file
    is a "lacks" check (J11-G19). Copies: the model's answer itself is kept as sent.

    An "expect" next to "steps" belongs to the last step that runs something (journey J11-B10: for Runes light it
    was ignored without a word, so both checks only ran the program); its file checks move to the example.

    Files given inside a step are created for the example (journey J11-G11: for s1 Nemotron wrote position.motion.json
    inside the step that reads it, where it was ignored, and its revision made each file a step of its own, which was
    refused). Files are created before the first step, so a step that gives files after another step ran is refused
    with that reason: moving them would change what the example does."""
    if not isinstance(steps, list):
        return row, steps
    row, moved = dict(row), []
    top = row.pop('expect', None)
    if top is not None and not isinstance(top, dict):
        dropped.append(f'{what}: "expect" next to "steps" could not be read (it is not an object)')
    elif top:
        top = dict(top)
        # File checks, and a "hides" naming a file, belong to the example wherever they were written.
        for key in FILE_CHECKS:
            if isinstance(top.get(key), list):
                row[key] = list(row.get(key) or []) + top.pop(key)
        if isinstance(top.get('hides'), list):
            texts_only = []
            for h in top['hides']:
                texts = h.get('texts') if isinstance(h, dict) and isinstance(h.get('texts'), list) else None
                if isinstance(h, dict) and isinstance(h.get('name'), str) and texts:
                    row['lacks'] = list(row.get('lacks') or []) + [{'name': h['name'], 'texts': texts}]
                elif isinstance(h, dict):
                    dropped.append(f'{what}: a "hides" beside the steps without a file name and its texts')
                else:
                    texts_only.append(h)
            top['hides'] = texts_only
            if not texts_only:
                top.pop('hides')
        # What the output shows belongs to a step: only when exactly one step runs a program is it clear which
        # (review of J11-B10: a document step ignores it, and with several steps the last is only a guess).
        acting = [n for n, s in enumerate(steps) if isinstance(s, dict) and any(s.get(k) for k in ('run', 'call', 'doc'))]
        runs = [n for n in acting if steps[n].get('run') or steps[n].get('call')]      # a call reads its output too
        if top and len(acting) == 1 and runs:
            steps = list(steps)
            last = dict(steps[runs[0]])
            own = dict(last.get('expect') or {}) if isinstance(last.get('expect'), dict) else {}
            for key, value in top.items():
                if isinstance(value, list) and isinstance(own.get(key), list):
                    own[key] = own[key] + value
                elif key not in own:
                    own[key] = value
                else:
                    dropped.append(f'{what}: "expect" next to "steps" gave another "{key}" than its step')
            last['expect'] = own
            steps[runs[0]] = last
        elif top:
            dropped.append(f'{what}: "expect" next to "steps" ({", ".join(sorted(map(str, top)))}): put what the '
                           'output shows inside the step it is about')
    for n, step in enumerate(steps, 1):
        if isinstance(step, dict) and ('files' in step or any(k in step for k in FILE_CHECKS)):
            step = dict(step)
            for key in FILE_CHECKS:
                if isinstance(step.get(key), list):
                    row[key] = list(row.get(key) or []) + step.pop(key)
            files = step.pop('files', None)
            if isinstance(files, list) and files:
                if any(isinstance(s, dict) and any(s.get(k) for k in ('run', 'call', 'doc')) for s in moved):
                    raise WorkspaceError(f'{what}, step {n}: "files" is not a step. Files are created before the first '
                                         'step; put them in the example\'s own "files".')
                row['files'] = list(row.get('files') or []) + files
            if not step:
                continue
        expect = step.get('expect') if isinstance(step, dict) else None
        if not isinstance(expect, dict):
            moved.append(step)
            continue
        expect = dict(expect)
        for key in FILE_CHECKS:
            if key in expect and isinstance(expect[key], list):
                row[key] = list(row.get(key) or []) + expect.pop(key)
        hides = expect.get('hides')
        if isinstance(hides, list) and any(isinstance(h, dict) for h in hides):
            expect['hides'] = [h for h in hides if not isinstance(h, dict)]
            for h in (h for h in hides if isinstance(h, dict)):
                # That a file does not contain some text is a "lacks" check (journey J11-G19).
                texts = h.get('texts') if isinstance(h.get('texts'), list) else [h['text']] if isinstance(h.get('text'), str) else None
                if isinstance(h.get('name'), str) and texts:
                    row['lacks'] = list(row.get('lacks') or []) + [{'name': h['name'], 'texts': texts}]
                else:
                    dropped.append(f'{what}: that a file does not contain some text, without naming the file and the text')
            if not expect['hides']:
                expect.pop('hides')
        step = dict(step, expect=expect) if expect else {k: v for k, v in step.items() if k != 'expect'}
        moved.append(step)
    return row, moved


# Files a person hands a program to read (journey J11-G10).
INPUT_SUFFIXES = ('.json', '.jsonl', '.ndjson', '.csv', '.tsv', '.txt', '.yaml', '.yml', '.xml', '.toml', '.ini', '.md')


def _missing_inputs(example, source_text, held=None) -> list[str]:
    """Files a run step hands its program that nothing creates: not "files", not the project, not another step.

    Journey J11-G10: a check ran "node motion.mjs position.motion.json --at 1" on a file no one made, so every correct
    build failed with ENOENT, and the trial on today's project read that failure as "fails, as expected". Only the
    first file name a step passes on its own counts (not one after an option such as --out, which the program may
    write), and a step that is expected to fail may name a missing file on purpose.

    `held` says whether the project holds a file the source text does not list: the checks' copy of the project has
    files a model is never shown (fixtures, shared documents), and a file that is there is not missing (J11-CC4).
    """
    named = ({f['name'] for f in example['files']} | set(example['exists']) | set(example['unchanged'])
             | {c['name'] for c in example['contains']} | {c['name'] for c in example.get('lacks', [])}
             | {c['name'] for c in example.get('file_lines', [])})
    missing = []
    for n, step in enumerate(example['steps']):
        if 'run' not in step or (step.get('expect') or {}).get('exit') == 'error':
            continue
        words = step['run'][3:] if step['run'][1] == '-m' else step['run'][2:]
        name = next((w for i, w in enumerate(words) if w.lower().endswith(INPUT_SUFFIXES) and ' ' not in w
                     and not w.startswith('-') and not (i and words[i - 1].startswith('-'))), None)
        if name is None:
            continue
        rel = name.replace('\\', '/').removeprefix('./')
        # A step that runs the program directly on the file reads it, so only an earlier step can have made it
        # (journey J11-G36: two steps both ran dots.motion.json, each counted as making it for the other, and the
        # autopilot approved checks every correct build fails). "save X" then "X --at 0" still makes X first.
        reads = bool(words) and words[0] == name
        others = ' '.join(' '.join(s.get('run', [])) + ' ' + s.get('input', '')
                          for m, s in enumerate(example['steps']) if (m < n if reads else m != n))
        if (rel not in named and rel not in source_text and rel not in others and rel not in missing
                and not (held and held(rel))):
            missing.append(rel)
    return missing


RUNS_IN_ITS_OWN_COPY = ('; each example runs in its own fresh copy, so list every file it runs in that example\'s own '
                        'files.')


def _refusal(refused) -> str:
    """What the Checker is told once: which example runs which file that neither it nor the project holds."""
    return '; '.join(f'{what} runs {", ".join(missing)}, which neither that example\'s files nor the project hold'
                     for what, missing in refused) + RUNS_IN_ITS_OWN_COPY


def validate_examples(data: Any, milestone_text: str, source_text: str = '', *, refuse_missing: bool = True,
                      held=None) -> dict[str, Any]:
    """The examples as stored, the checks file rendered from them, and what Runesmith dropped; or a WorkspaceError.

    An example that runs a file it does not list and the project does not hold is refused in plain words, so the
    Checker is told once while it drafts (journey J11-CC4, after J11-G36: three of five drafts did, and the owner had
    to find each by reading it). With `refuse_missing` off, the file is only named under its check (`missing_input`),
    for a caller that cannot tell what the project holds. `held`: see _missing_inputs.
    """
    if not isinstance(data, dict) or not isinstance(data.get('examples'), list):
        raise WorkspaceError('The answer needs "examples".')
    rows = data['examples']
    if not 1 <= len(rows) <= LIMITS['examples']:
        raise WorkspaceError(f'Give 1-{LIMITS["examples"]} examples.')
    examples, checks, dropped, taken, refused = [], [], [], set(), []
    for index, row in enumerate(rows, 1):
        what = f'Example {index}'
        if not isinstance(row, dict):
            raise WorkspaceError(f'{what} must be an object.')
        says = _plain(row.get('says'), f'{what}: "says"', 300)
        steps = row.get('steps') if row.get('steps') is not None else []
        steps = _joined(steps) if isinstance(steps, list) else steps
        row, steps = _lifted(row, steps, what, dropped)
        if unread := sorted(str(k) for k in row if k not in EXAMPLE_KEYS):
            dropped.append(f'{what}: ' + ', '.join(f'"{k}"' for k in unread) + ' is not something these checks read')
        if not isinstance(steps, list) or len(steps) > LIMITS['steps']:
            raise WorkspaceError(f'{what} needs at most {LIMITS["steps"]} steps.')
        example: dict[str, Any] = {'test': _name(row.get('name'), index, taken), 'says': says,
                                   'steps': [_step(s, f'{what}, step {n}') for n, s in enumerate(steps, 1)]}
        files = row.get('files') or []
        if not isinstance(files, list) or len(files) > LIMITS['files']:
            raise WorkspaceError(f'{what}: at most {LIMITS["files"]} files.')
        example['files'] = []
        for f in files:
            if not isinstance(f, dict) or not isinstance(f.get('text'), str) or len(f['text']) > LIMITS['file']:
                raise WorkspaceError(f'{what}: each file needs a name and a text of at most {LIMITS["file"]} characters.')
            example['files'].append({'name': _relative(f.get('name'), f'{what}: a file name'), 'text': f['text']})
        written = {f['name'] for f in example['files']}
        example['unchanged'] = [_relative(n, f'{what}: "unchanged"') for n in _texts(row.get('unchanged'), f'{what}: "unchanged"')]
        if missing := [n for n in example['unchanged'] if n not in written]:
            raise WorkspaceError(f'{what}: "unchanged" can only name files the example creates, not {missing[0]!r}.')
        example['exists'] = [_relative(n, f'{what}: "exists"') for n in _texts(row.get('exists'), f'{what}: "exists"')]
        for key in ('contains', 'lacks'):              # "lacks": journey J11-G19
            rows = row.get(key) or []
            if not isinstance(rows, list) or len(rows) > LIMITS['files']:
                raise WorkspaceError(f'{what}: "{key}" must be a short list.')
            example[key] = []
            for c in rows:
                texts = c.get('texts') if isinstance(c, dict) else None
                if isinstance(texts, list) and len(texts) > LIMITS['texts']:
                    # Too many texts is not a reason to refuse the answer: the first ones are checked (J11-G9).
                    dropped.append(f'{what}: {len(texts) - LIMITS["texts"]} more texts to find in {c.get("name")} '
                                   f'(at most {LIMITS["texts"]} are checked)')
                    texts = texts[:LIMITS['texts']]
                example[key].append({'name': _relative(c.get('name') if isinstance(c, dict) else None,
                                                       f'{what}: "{key}"'),
                                     'texts': _texts(texts, f'{what}: "{key}"')})
        lines = row.get('file_lines') or []
        if not isinstance(lines, list) or len(lines) > LIMITS['texts']:
            raise WorkspaceError(f'{what}: "file_lines" must be a short list.')
        example['file_lines'] = []
        for line in lines:
            if (not isinstance(line, dict) or not isinstance(line.get('has'), str) or not line['has'].strip()
                    or len(line['has']) > 200 or isinstance(line.get('number'), bool)
                    or not isinstance(line.get('number'), (int, float))):
                raise WorkspaceError(f'{what}: each of "file_lines" needs a file "name", a text "has" and a "number".')
            name, has = _relative(line.get('name'), f'{what}: "file_lines"'), line['has'].strip()
            if WHOLE_ATTRIBUTE.fullmatch(has):
                # A whole attribute with its value is a text the file contains, not a name a number follows
                # (journey J11-G23: "the first number after stroke-dasharray=\"115\" is 0").
                # `slot`, never `row`: that is the example being read (verifier of batch N2).
                slot = next((r for r in example['contains'] if r['name'] == name), None)
                if slot is None and len(example['contains']) < LIMITS['files']:
                    slot = {'name': name, 'texts': []}
                    example['contains'].append(slot)
                if slot is not None and has not in slot['texts'] and len(slot['texts']) < LIMITS['texts']:
                    slot['texts'].append(has)
                if slot is not None and has in slot['texts']:
                    dropped.append(f'{what}: "file_lines" for {has} (checked instead: {name} contains it)')
                else:                              # the limits are full: said, never claimed (review)
                    dropped.append(f'{what}: "file_lines" for {has} (not checked: too many texts for {name})')
                continue
            example['file_lines'].append({'name': name, 'has': has, 'number': line['number']})
        example['links_resolve'] = bool(row.get('links_resolve'))
        example['pages_reachable'] = bool(row.get('pages_reachable'))
        if not example['steps'] and not (example['exists'] or example['contains'] or example['lacks']
                                         or example['file_lines'] or example['links_resolve'] or example['pages_reachable']):
            # "files" was used to say what the finished page should contain (journey J11-G6, m4 and m5).
            hint = (' "files" only prepares files before the steps, so they would always be there; to check what '
                    'the finished project contains, use "exists" or "contains".' if example['files'] else '')
            raise NothingToCheck(f'{what} needs steps, or a check on files ("exists", "contains", "lacks", "links_resolve" '
                                 'or "pages_reachable").' + hint)
        if not example['steps'] and example['files']:
            # Journey J11-F28: the video milestone's checks put record.html in "files", then looked for texts in it.
            # Names are compared as the files are found: "./record.html" and "Record.html" are the same file (review).
            own = {_same_file(f['name']) for f in example['files']}
            own_checks = sorted({c['name'] for key in ('contains', 'lacks', 'file_lines') for c in example[key]
                                 if _same_file(c['name']) in own} | {n for n in example['exists'] if _same_file(n) in own})
            real = ([c for key in ('contains', 'lacks', 'file_lines') for c in example[key] if _same_file(c['name']) not in own]
                    + [n for n in example['exists'] if _same_file(n) not in own])
            if own_checks and not real and not (example['links_resolve'] or example['pages_reachable']):
                raise WorkspaceError(f'{what} checks ' + ', '.join(own_checks) + ', which it writes itself in "files" and no '
                                     'step changes, so it checks nothing the build makes. Leave the project\'s own files out '
                                     'of "files".')
            if own_checks:           # it also checks the project's own files: only the trivial checks go
                for key in ('contains', 'lacks', 'file_lines'):
                    example[key] = [c for c in example[key] if _same_file(c['name']) not in own]
                example['exists'] = [n for n in example['exists'] if _same_file(n) not in own]
                dropped.append(f'{what}: the checks on ' + ', '.join(own_checks) + ' (the example writes them itself in '
                               '"files", so they check nothing the build makes)')
        for n, step in enumerate(example['steps'], 1):
            word = _command_word(step)
            refused_on_purpose = (step.get('expect') or {}).get('exit') == 'error'   # "an unknown command is refused"
            if word and source_text and not refused_on_purpose and not _mentioned(word, milestone_text + ' ' + source_text):
                # Checker experiment 2026-09-28: Flash Lite ran "python -m readinglog count" for the "months" command,
                # so its checks failed every correct build. The one revision is told the word.
                raise WorkspaceError(f'{what}, step {n}: runs “{word}”, a command neither the milestone nor the program '
                                     'mentions. Use a command they name.')
            invented = [o for o in _options(step) if not _option_named(o, milestone_text + ' ' + source_text)]
            if invented and source_text and not refused_on_purpose:
                # Journey J11-G30: for "export a PNG frame and a WebM clip from the browser canvas", the Checker ran
                # --export-png and --export-webm, which nothing names; the autopilot's second model agreed with the
                # commands as given, and a build would have had to invent the same options to pass.
                raise WorkspaceError(f'{what}, step {n}: runs the program with ' + ', '.join(f'“{o}”' for o in invented)
                                     + (', options' if len(invented) > 1 else ', an option')
                                     + ' neither the milestone nor the program mentions. Use the options they name; if '
                                     'they name none for this, check what the milestone does name, and say in '
                                     '"not_checked" what cannot be checked.')
        for n, step in enumerate(example['steps'], 1):
            if not step.pop('unchecked_expect', False):
                continue
            if n == len(example['steps']) and not (example['unchanged'] or example['exists'] or example['contains']
                                                   or example['lacks'] or example['file_lines']):
                raise WorkspaceError(f'{what}, step {n}: check what an interrupted run leaves behind with a later step.')
            dropped.append(f'{what}: what {_show(step)} shows while it is interrupted (a later check looks at what it left behind)')
        dropped += [f'{what}: {d}' for d in _ground(example, milestone_text, source_text)]
        check = {'test': example['test'], 'says': says, 'exact': exact(example)}
        if source_text and (missing := _missing_inputs(example, source_text, held)):
            if refuse_missing:
                refused.append((what, missing))
            else:
                check['missing_input'] = missing
        checks.append(check)
        examples.append(example)
    if refused:                 # after every example was read, so one answer names all of them (J11-CC4)
        raise WorkspaceError(_refusal(refused))
    not_checked = _notes(data.get('not_checked'))
    code = render(examples)
    return {'checks': checks, 'assumes': [], 'examples': examples, 'dropped': dropped[:20], 'not_checked': not_checked,
            'code': code, 'code_sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(), 'style': 'examples'}


def render(examples) -> str:
    methods = ''.join(f'\n    def {e["test"]}(self):\n        run_example(self, EXAMPLES[{i}])\n'
                      for i, e in enumerate(examples))
    data = json.dumps([{k: v for k, v in e.items() if k != 'says'} for e in examples], ensure_ascii=False, sort_keys=True)
    return (HARNESS.replace('__EXAMPLES__', repr(data))
            + '\n\nclass OwnerExamples(unittest.TestCase):\n    """One test per example the owner approved."""\n' + methods)


# The trusted template. It runs inside the check runner, so it never imports runesmith.
HARNESS = r'''"""Owner acceptance checks written from examples by Runesmith's trusted template (runesmith/app/acceptance_examples.py).

Each example runs in its own fresh copy of the project. Texts are matched whole and without regard to case.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

EXAMPLES = json.loads(__EXAMPLES__)
PROJECT = os.getcwd()
SKIP = {".git", ".runesmith", "__pycache__", ".pytest_cache"}
WORK = "rs-example-"
STEP_TIMEOUT = 30
TRACEBACK = "Traceback (most recent call last)"
NODE_VERSION = re.compile(r"Node\.js v\d+\.\d+\.\d+")
PLACEHOLDER = re.compile(r"\b[A-Z]{2,}\b|YYYY|<[^>]*>|\.\.\.")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")

INTERRUPTED = r"""
import builtins, io, os, runpy, sys
folder = os.path.normcase(os.path.abspath(sys.argv[1]))
words = sys.argv[2:]
real_open = io.open

class HalfWriter:
    def __init__(self, handle):
        self.handle = handle
    def write(self, text):
        self.handle.write(text[: max(1, len(text) // 2)])
        self.handle.flush()
        raise OSError("simulated interruption while saving")
    def __getattr__(self, name):
        return getattr(self.handle, name)
    def __enter__(self):
        return self
    def __exit__(self, *problem):
        self.handle.close()
        return False
    def __iter__(self):
        return iter(self.handle)

def interrupting_open(file, mode="r", *args, **kwargs):
    handle = real_open(file, mode, *args, **kwargs)
    inside = isinstance(file, (str, bytes, os.PathLike)) and os.path.normcase(
        os.path.abspath(os.fsdecode(file))).startswith(folder)
    return HalfWriter(handle) if inside and any(flag in mode for flag in "wax+") else handle

io.open = builtins.open = interrupting_open
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "src")]
try:
    if words[0] == "-m":
        sys.argv = [words[1]] + words[2:]
        runpy.run_module(words[1], run_name="__main__", alter_sys=True)
    else:
        sys.argv = words
        runpy.run_path(words[0], run_name="__main__")
except BaseException:
    pass
"""

CALLER = r"""
import importlib, json, os, sys
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "src")]
target, args = sys.argv[1], json.loads(sys.argv[2])
module_name, _, name = target.rpartition(".")
try:
    value = getattr(importlib.import_module(module_name), name)(*args)
    answer = {"returns": json.loads(json.dumps(value, default=repr))}
except Exception as error:
    answer = {"raises": [kind.__name__ for kind in type(error).__mro__], "message": str(error)[:300]}
print("RUNESMITH_CALL=" + json.dumps(answer))
"""


def read_checked(case, path, name):
    """A checked file's text; an .svg or .xml file must be well-formed and a .json file must parse, or the check
    fails (journey J11-G29: Blueprint wrote an SVG whose rect tag never closed, and its text checks passed)."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    low = name.lower()
    if low.endswith((".svg", ".xml")):
        import xml.dom.minidom
        try:
            xml.dom.minidom.parseString(text.encode("utf-8"))
        except Exception as error:
            case.fail(name + " is not well-formed XML: " + str(error))
    elif low.endswith(".json"):
        try:
            json.loads(text)
        except ValueError as error:
            case.fail(name + " is not valid JSON: " + str(error))
    return text


def found(text, output):
    """Where text appears as a whole (not inside a longer word or number), ignoring case; None if it does not."""
    pattern = (r"(?<!\w)" if text[:1].isalnum() else "") + re.escape(text)
    if text[-1:].isdigit():
        pattern += r"(?!\w|[-./]\d)"
    elif text[-1:].isalnum():
        pattern += r"(?!\w)"
    return re.search(pattern, output, re.IGNORECASE)


def found_whole(text, content):
    """Like found, but a name joined by '-' is another name: "rs-bg-2" does not contain "rs-bg"."""
    pattern = (r"(?<![\w-])" if text[:1].isalnum() else "") + re.escape(text) + (r"(?![\w-])" if text[-1:].isalnum() else "")
    return re.search(pattern, content, re.IGNORECASE)


def number_after(has, number, text):
    """Whether, somewhere in text, the first number after has (on the same line) is number."""
    pattern = (r"(?<![\w-])" if has[:1].isalnum() else "") + re.escape(has)
    for match in re.finditer(pattern, text, re.IGNORECASE):
        rest = text[match.end():].split("\n", 1)[0]
        first = re.search(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", rest)
        joined = has[-1:].isalnum() and re.match(r"[\w-]", rest[:1])     # "stroke" inside "stroke-width"
        if first and not joined and float(first.group()) == float(number):
            return True
        # Or the whole text of the element that holds the name: <text class="rs-dim-label" x="100">120</text> is "a
        # line with rs-dim-label and the number 120" (journey J11-G27).
        inner = re.match(r"[^<>]*>\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*<", rest)
        # Only when the name is not itself an attribute with a value (verifier: stroke-dashoffset="115">57.5 passed).
        if not joined and not re.match(r"\s*[=:]", rest) and inner and float(inner.group(1)) == float(number):
            return True
    return False


def number_on_line(has, number, output):
    for line in output.splitlines():
        match = found(has, line)
        if match and any(float(n) == float(number) for n in NUMBER.findall(line[:match.start()] + " " + line[match.end():])):
            return True
    return False


def copy_project(work):
    copy = os.path.join(work, "project")
    # A name starting with "%" is an unexpanded Windows variable some tool made into a folder; it is never project content.
    shutil.copytree(PROJECT, copy, ignore=lambda folder, names: [n for n in names if n in SKIP or n.startswith((WORK, "%"))])
    return copy


def environment(work):
    home = os.path.join(work, "home")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ)
    env.update(HOME=home, USERPROFILE=home, APPDATA=home, LOCALAPPDATA=home, TEMP=home, TMP=home,
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def command(words):
    if words[0] == "python":
        return [sys.executable] + words[1:]
    return [shutil.which(words[0]) or words[0]] + words[1:]


def shown(words):
    return "`" + " ".join(words) + "`"


def execute(case, argv, label, copy, env, stdin=""):
    try:
        done = subprocess.run(argv, cwd=copy, env=env, input=stdin, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=STEP_TIMEOUT)
    except subprocess.TimeoutExpired:
        case.fail(label + " did not finish within " + str(STEP_TIMEOUT) + " seconds")
    except OSError as error:
        case.fail(label + " could not start: " + str(error))
    return done.returncode, (done.stdout or "") + "\n" + (done.stderr or "")


def node_crashed(output):
    """An uncaught Node.js error: its stack ("    at ..."), then the runtime's version as the last line. A program
    that reports an error on purpose prints neither (journey J11-G2)."""
    lines = output.rstrip().splitlines()
    return bool(lines) and NODE_VERSION.fullmatch(lines[-1].strip()) is not None and "\n    at " in output


def check_output(case, label, expect, code, output, default_exit):
    case.assertNotIn(TRACEBACK, output, label + " stopped with a Python crash report:\n" + output[-1500:])
    case.assertFalse(node_crashed(output), label + " stopped with an uncaught Node.js error:\n" + output[-1500:])
    wanted = expect.get("exit") or default_exit
    if wanted == "ok":
        case.assertEqual(code, 0, label + " did not finish normally:\n" + output[-1500:])
    elif wanted == "error":
        case.assertNotEqual(code, 0, label + " finished normally, but an error was expected:\n" + output[-1500:])
    if expect.get("message"):
        case.assertTrue(output.strip(), label + " explained nothing in words")
    for text in expect.get("shows", []):
        case.assertTrue(found(text, output), label + " does not show " + repr(text) + ":\n" + output[-1500:])
    for text in expect.get("hides", []):
        case.assertFalse(found(text, output), label + " shows " + repr(text) + ":\n" + output[-1500:])
    for row in expect.get("lines", []):
        case.assertTrue(number_on_line(row["has"], row["number"], output),
                        label + " has no line with " + repr(row["has"]) + " and the number " + str(row["number"])
                        + ":\n" + output[-1500:])
    if expect.get("order"):
        places = [found(text, output) for text in expect["order"]]
        missing = [t for t, p in zip(expect["order"], places) if not p]
        case.assertFalse(missing, label + " does not show " + repr(missing) + ":\n" + output[-1500:])
        starts = [p.start() for p in places]
        case.assertEqual(starts, sorted(starts), label + " does not list " + repr(expect["order"]) + " in that order:\n"
                         + output[-1500:])


def run_step(case, step, copy, env):
    expect = step.get("expect", {})
    if "run" in step:
        label = shown(step["run"])
        if step.get("fault") == "interrupted_write":
            execute(case, [sys.executable, "-c", INTERRUPTED, copy] + step["run"][1:], label, copy, env)
            return
        code, output = execute(case, command(step["run"]), label, copy, env, step.get("input", ""))
        check_output(case, label, expect, code, output, "any" if expect.get("message") else "ok")
    elif "call" in step:
        label = "`" + step["call"] + "`"
        code, output = execute(case, [sys.executable, "-c", CALLER, step["call"], json.dumps(step["args"])], label, copy, env)
        rows = [line[len("RUNESMITH_CALL="):] for line in output.splitlines() if line.startswith("RUNESMITH_CALL=")]
        case.assertTrue(rows, label + " could not be called:\n" + output[-1500:])
        answer = json.loads(rows[-1])
        if "raises" in expect:
            case.assertIn(expect["raises"], answer.get("raises", []), label + " did not raise " + expect["raises"] + ": "
                          + json.dumps(answer)[:600])
        else:
            case.assertNotIn("raises", answer, label + " failed: " + json.dumps(answer)[:600])
        if "returns" in expect:
            case.assertEqual(answer.get("returns"), expect["returns"], label + " returned something else")
        text = output + "\n" + json.dumps(answer.get("returns"), ensure_ascii=False)
        check_output(case, label, {k: v for k, v in expect.items() if k in ("shows", "hides", "lines", "order")}, 0, text, "any")
    else:
        check_document(case, step, copy, env)


def check_document(case, step, copy, env):
    path = os.path.join(copy, step["doc"])
    case.assertTrue(os.path.isfile(path), step["doc"] + " is missing")
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    program = step["program"]
    head = r"(?:python3?|py)" if program[0] == "python" else re.escape(program[0])
    pattern = re.compile(r"(?<![\w/.-])" + head + "".join(r"\s+" + re.escape(w) for w in program[1:])
                         + r"(?![\w.-])(?P<rest>[^`\n]*)")
    examples = [m.group("rest").strip().rstrip(".,;:") for m in pattern.finditer(text)]
    examples = [e for e in examples if e]
    for word in step.get("mention", []):
        case.assertTrue(any(found(word, e) for e in examples),
                        step["doc"] + " shows no example of " + " ".join(program) + " with " + repr(word))
    runnable = [e for e in examples if not PLACEHOLDER.search(e)]
    case.assertTrue(runnable, step["doc"] + " shows no example of " + " ".join(program) + " that can be run as written")
    for example in runnable:
        try:
            words = shlex.split(example)
        except ValueError:
            case.fail(step["doc"] + " has an example that cannot be read: " + example)
        label = "the example `" + " ".join(program) + " " + example + "`"
        code, output = execute(case, command(program + words), label, copy, env)
        check_output(case, label, {}, code, output, "ok")


def exists_exactly(path, root):
    relative = os.path.relpath(path, root)
    if relative.startswith(".."):
        return False
    current = root
    for part in relative.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        try:
            names = os.listdir(current)
        except OSError:
            return False
        if part not in names:
            return False
        current = os.path.join(current, part)
    return True


def unquote(text):
    return re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), text)


def check_links(case, copy):
    broken = []
    for folder, folders, names in os.walk(copy):
        folders[:] = [f for f in folders if f not in SKIP and not f.startswith(WORK)]
        for name in names:
            if not name.lower().endswith((".md", ".markdown")):
                continue
            page = os.path.join(folder, name)
            with open(page, encoding="utf-8", errors="replace") as handle:
                targets = LINK.findall(handle.read())
            for target in targets:
                if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith(("#", "//")):
                    continue
                relative = unquote(target.split("#")[0].split("?")[0])
                if not relative:
                    continue
                full = os.path.join(copy, relative.lstrip("/")) if relative.startswith("/") else os.path.join(folder, relative)
                if not exists_exactly(os.path.normpath(full), copy):
                    broken.append(os.path.relpath(page, copy).replace("\\", "/") + " -> " + target)
    case.assertEqual(broken, [], "links that lead nowhere: " + ", ".join(broken[:10]))


def markdown_pages(copy):
    for folder, folders, names in os.walk(copy):
        folders[:] = sorted(f for f in folders if f not in SKIP and not f.startswith(WORK) and not f.startswith("."))
        for name in sorted(names):
            if name.lower().endswith((".md", ".markdown")):
                yield os.path.normpath(os.path.join(folder, name))


def check_reachable(case, copy):
    """Every Markdown page can be reached by following links from the front page (README.md or index.md)."""
    pages = {os.path.normcase(p): p for p in markdown_pages(copy)}        # compared without case, opened by real name
    front = [key for key, p in pages.items() if os.path.dirname(p) == os.path.normpath(copy)
             and os.path.basename(p).lower() in ("readme.md", "index.md")]
    seen, todo = set(front), list(front)
    while todo:
        page = pages[todo.pop()]
        with open(page, encoding="utf-8", errors="replace") as handle:
            targets = LINK.findall(handle.read())
        for target in targets:
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith(("#", "//")):
                continue
            relative = unquote(target.split("#")[0].split("?")[0])
            if not relative:
                continue
            full = os.path.join(copy, relative.lstrip("/")) if relative.startswith("/") else os.path.join(os.path.dirname(page), relative)
            key = os.path.normcase(os.path.normpath(full))
            if key in pages and key not in seen and exists_exactly(os.path.normpath(full), copy):
                seen.add(key)
                todo.append(key)
    case.assertTrue(front, "there is no README.md or index.md to start from")
    missing = sorted(os.path.relpath(pages[k], copy).replace("\\", "/") for k in set(pages) - seen)
    case.assertEqual(missing, [], "pages that cannot be reached from the front page: " + ", ".join(missing[:10]))


def run_example(case, example):
    work = tempfile.mkdtemp(prefix=WORK)
    try:
        copy = copy_project(work)
        env = environment(work)
        for item in example.get("files", []):
            target = os.path.join(copy, item["name"])
            os.makedirs(os.path.dirname(target) or copy, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(item["text"])
        for step in example["steps"]:
            run_step(case, step, copy, env)
        for item in example.get("files", []):
            if item["name"] in example.get("unchanged", []):
                with open(os.path.join(copy, item["name"]), encoding="utf-8", newline="", errors="replace") as handle:
                    case.assertEqual(handle.read(), item["text"], item["name"] + " was changed")
        for name in example.get("exists", []):
            case.assertTrue(exists_exactly(os.path.join(copy, name), copy), name + " does not exist")
        for row in example.get("contains", []):
            path = os.path.join(copy, row["name"])
            case.assertTrue(os.path.isfile(path), row["name"] + " does not exist")
            text = read_checked(case, path, row["name"])
            for wanted in row["texts"]:
                case.assertTrue(found(wanted, text), row["name"] + " does not contain " + repr(wanted))
        for row in example.get("lacks", []):
            path = os.path.join(copy, row["name"])
            case.assertTrue(os.path.isfile(path), row["name"] + " does not exist")
            text = read_checked(case, path, row["name"])
            for unwanted in row["texts"]:
                case.assertFalse(found_whole(unwanted, text), row["name"] + " contains " + repr(unwanted))
        for row in example.get("file_lines", []):
            path = os.path.join(copy, row["name"])
            case.assertTrue(os.path.isfile(path), row["name"] + " does not exist")
            text = read_checked(case, path, row["name"])
            case.assertTrue(number_after(row["has"], row["number"], text),
                            row["name"] + ": the first number after " + repr(row["has"]) + " is not " + repr(row["number"]))
        if example.get("links_resolve"):
            check_links(case, copy)
        if example.get("pages_reachable"):
            check_reachable(case, copy)
    finally:
        shutil.rmtree(work, ignore_errors=True)
'''
