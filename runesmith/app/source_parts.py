"""A file too large to show whole is shown in parts: an outline, then exact excerpts (journeys J11-B15, J11-B16).

Every real project grows a file past any fixed cap. Past the cap no model could be shown the file, so none could change
it (J11 stood still for two days on motion.mjs), and the Checker never saw the program it writes checks for. The safety
rule stays: a model may change only text it was shown, exactly as it is. So a file is shown in parts: an outline of its
declarations, with line numbers, to find the way, and the file's exact lines around what the milestone is about. An
answer may then change the file only with exact edits whose old text lies inside one shown part.

Everything here is a function of the file's text and the milestone's words: the same inputs always give the same parts.
"""
from __future__ import annotations

import bisect
import difflib
import hashlib
import re
import threading
from typing import NamedTuple

MIN_PART_CHARS = 4000       # a file is shown in parts only when the budget has room for at least this much
OUTLINE_CHARS = 3000        # the outline is short: it only shows the way
MAX_LINE_CHARS = 2000       # a longer line (minified code, data) is never part of an excerpt
DECLARATION_LINES = 120     # a declaration longer than this is shown by windows around its matches
DECLARATION_CHARS = 6000
WINDOW_LINES = 12
CONTEXT_LINES = 3
GAP_LINES = 2               # two parts at most this many lines apart are shown as one
FILL_STEPS = (6, 12, 24, 48, 96, 200, 400)     # how far the left-over budget widens each part, step by step
HEAD_LINES, HEAD_CHARS = 25, 1500       # the top of the file (imports) and its end, when the budget has room
TAIL_LINES, TAIL_CHARS = 12, 900
MAX_TERMS = 120
DASH = '–'

STOPWORDS = frozenset('''
a about above after again all also always am an and another any are as at back be because been before being both but by
can cannot case cases code could did does doing done each either else etc even ever every example examples file files
for from get gets got had has have having her here him his how into its just like line lines list made make makes many may
might more most much must need needs neither new nor not now off once one only onto other our out over own per program
project same should show shows shown since some such than that the their them then there these they this those through
to too two three under until up upon use used uses using very want wants was way we were what when where which while who
whom whose why will with within without would yet you your step steps work works milestone output input result results
return returns text value values name names page
'''.split())

_QUOTED = re.compile(r'"([^"\n]{2,60})"|\'([^\'\n]{2,60})\'|`([^`\n]{2,60})`')
_WORD = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*')


def extract_terms(*texts, anchors=()):
    """The words a milestone's parts are chosen by: identifiers (also dotted, like project.camera) and quoted strings
    from the texts, and, as phrases, whole lines a refused answer tried to change (its anchors). Stable order."""
    words, seen = [], set()

    def add(word):
        low = word.strip().lower()
        if len(low) >= 3 and low not in STOPWORDS and not low.isdigit() and low not in seen:
            seen.add(low)
            words.append(low)
    for text in texts:
        text = str(text or '')
        for match in _QUOTED.finditer(text):
            add(next(group for group in match.groups() if group))
        for match in _WORD.finditer(text):
            word = match.group(0)
            add(word)
            if '.' in word:
                for piece in word.split('.'):
                    add(piece)
    phrases = []
    for anchor in anchors:
        anchor = str(anchor or '').strip()
        if len(anchor) > 5 and anchor not in phrases:
            phrases.append(anchor)
    return {'words': words[:MAX_TERMS], 'phrases': phrases[:40]}


def named_in(text, rel):
    """Whether a text names this file by its path or its file name."""
    low = str(text or '').lower()
    return rel.lower() in low or rel.rsplit('/', 1)[-1].lower() in low


def split_lines(text):
    """A file's lines as the parts count them: from 1, the end of the last line is not another line."""
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    return lines


class Entry(NamedTuple):
    n: int          # line number, from 1
    indent: int
    tier: int       # 0 a function/class/def/heading, 1 another top-level declaration, 2 a nested one, 3 a case
    text: str


_DECLARES = re.compile(r'(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|def|interface|struct|fn|impl|enum|trait)\b')
_TOP = re.compile(r'(?:export|async|function|class|const|let|var|def|interface|type|struct|fn|impl|pub|enum|trait)\b')
_NESTED = re.compile(r'(?:export\s+)?(?:async\s+)?(?:function|class|def)\b')
_CASE = re.compile(r'case\s+[^:\n]{1,80}:')
_HEADING = re.compile(r'#{1,6}\s+\S')


def _indent(line):
    return len(line) - len(line.lstrip(' \t'))


def outline_entries(rel, lines):
    """Every line that starts a declaration: unindented export/async/function/class/const/let/var/def/interface/type/
    struct/fn/impl, Markdown headings, indented functions, classes and defs, and `case '…':` lines at their indent."""
    markdown = rel.lower().endswith(('.md', '.markdown'))
    entries = []
    for number, line in enumerate(lines, 1):
        stripped = line.lstrip(' \t')
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        tier = None
        if indent == 0:
            if markdown:
                tier = 0 if _HEADING.match(stripped) else None
            elif _TOP.match(stripped):
                tier = 0 if _DECLARES.match(stripped) else 1
        elif not markdown and _NESTED.match(stripped):
            tier = 2
        elif not markdown and _CASE.match(stripped):
            tier = 3
        if tier is not None:
            entries.append(Entry(number, indent, tier, line.rstrip()))
    return entries


_HEAD = re.compile(r"(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?|class|def|interface|struct|fn|impl|enum|trait|"
                   r"pub\s+fn|const|let|var|type)\s+[A-Za-z0-9_$.<>]+\(?")
_CASE_HEAD = re.compile(r"case\s+[^:]{1,60}:")


def _head(entry):
    """The part of a declaration line that names it: `function shape12(`, `case 'rect':`; the whole line otherwise."""
    text = entry.text
    stripped = text.lstrip(' \t')
    indent = text[:len(text) - len(stripped)]
    found = _CASE_HEAD.match(stripped) or _HEAD.match(stripped)
    text = indent + (found.group(0) if found else stripped)
    return text if len(text) <= 96 else text[:95] + '…'


def _outline_lines(entries, cap=OUTLINE_CHARS):
    def fmt(entry):
        return f'{entry.n}: {_head(entry)}'
    for tier in (3, 2, 1, 0):
        chosen = [fmt(entry) for entry in entries if entry.tier <= tier]
        if sum(len(row) + 1 for row in chosen) <= cap:
            break
    else:
        # Still too long: every n-th declaration, so the outline covers the whole file rather than only its start.
        size = sum(len(row) + 1 for row in chosen)
        keep = max(1, int(len(chosen) * (cap - 100) / size))
        chosen = [chosen[i * len(chosen) // keep] for i in range(keep)]
    if len(chosen) < len(entries):
        chosen = chosen + [f'… {len(chosen)} of {len(entries)} declarations listed (the outline is shortened)']
    return chosen


def _header(rel, lines, cap=OUTLINE_CHARS, entries=None):
    n = len(lines)
    outline = _outline_lines(outline_entries(rel, lines) if entries is None else entries, cap)
    return [f'{rel} is shown in parts (it has {n} lines): change it only with exact edits whose old_text is copied '
            'from ONE excerpt below, never from the outline, and never by writing the whole file.',
            f'--- outline of {rel}: every declaration with its line number. An outline only: never copy old_text '
            'from it ---'] + outline


def _label(rel, a, b, n):
    return f'--- {rel} lines {a}{DASH}{b} of {n}: the exact lines ---'


def render_parts(rel, lines, ranges, outline_cap=OUTLINE_CHARS, entries=None):
    """The text a model reads for a file shown in parts: a labelled outline, then each excerpt, labelled with its lines.
    A function of the file and the ranges alone, so a recorded range list rebuilds exactly what a call was shown."""
    n = len(lines)
    out = _header(rel, lines, outline_cap, entries)
    for a, b in ranges:
        out.append(_label(rel, a, b, n))
        out.extend(lines[a - 1:b])
    return '\n'.join(out) + '\n'


def check_ranges(ranges, count):
    """The ranges as a list of [first, last] pairs, or None when they are not ascending, separate, whole-line spans of a
    file with this many lines."""
    if not isinstance(ranges, list) or not ranges:
        return None
    clean, last = [], 0
    for pair in ranges:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(type(x) is not int for x in pair)
                or not last < pair[0] <= pair[1] <= count):
            return None
        clean.append([pair[0], pair[1]])
        last = pair[1]
    return clean


def format_ranges(ranges):
    return ', '.join(f'{a}{DASH}{b}' if a != b else str(a) for a, b in ranges)


def _merge(covered, lines):
    ranges = []
    for number in sorted(covered):
        if ranges:
            gap = number - ranges[-1][1] - 1
            if gap == 0 or (gap <= GAP_LINES and all(len(lines[k - 1]) <= MAX_LINE_CHARS
                                                     for k in range(ranges[-1][1] + 1, number))):
                ranges[-1][1] = number
                continue
        ranges.append([number, number])
    return ranges


_CACHE: dict = {}
_LOCK = threading.Lock()


def build_parts(rel, text, terms, budget, *, must=(), outline_cap=OUTLINE_CHARS):
    """_build_parts, remembered: a build round chooses the same parts for the same file and words again and again."""
    terms = terms or {}
    key = (rel, hashlib.sha1(text.encode('utf-8')).hexdigest(), tuple(terms.get('words') or ()),
           tuple(terms.get('phrases') or ()), budget, tuple(must), outline_cap)
    with _LOCK:
        known = key in _CACHE
        found = _CACHE.get(key)
    if not known:
        found = _build_parts(rel, text, terms, budget, must=must, outline_cap=outline_cap)
        with _LOCK:
            if len(_CACHE) >= 64:
                _CACHE.pop(next(iter(_CACHE)), None)
            _CACHE[key] = found
    return None if found is None else dict(found, ranges=[list(r) for r in found['ranges']])


def _build_parts(rel, text, terms, budget, *, must=(), outline_cap=OUTLINE_CHARS):
    """The outline and excerpts of a file for a budget of characters, or None when it cannot be shown even in parts
    (the budget is below MIN_PART_CHARS, or every useful line is too long).

    Excerpts, in this order while the budget lasts: `must` spans (lines a revision candidate changed); the enclosing
    declaration of every line that matches a term (the best-matching first, a long one by windows around its matches);
    a few lines around plain matches; the top of the file and its end."""
    lines = split_lines(text)
    n = len(lines)
    if n == 0 or budget < MIN_PART_CHARS:
        return None
    terms = terms or {}
    entries = outline_entries(rel, lines)
    fixed = sum(len(row) + 1 for row in _header(rel, lines, outline_cap, entries))
    if fixed >= budget:
        return None
    covered: set[int] = set()

    def cost(cover):
        return fixed + sum(len(_label(rel, a, b, n)) + 1 + sum(len(lines[k - 1]) + 1 for k in range(a, b + 1))
                           for a, b in _merge(cover, lines))

    def add(wanted):
        wanted = {k for k in wanted if 1 <= k <= n and len(lines[k - 1]) <= MAX_LINE_CHARS}
        if not wanted or wanted <= covered:
            return False
        if cost(covered | wanted) > budget:
            return False
        covered.update(wanted)
        return True

    for first, last in must:
        if not add(range(first - 2, last + 3)):
            add(range(first, last + 1))
    # How well each line matches: a term that matches few lines tells more than one that matches many.
    lower = [line.lower() for line in lines]
    scores: dict[int, int] = {}
    for word in terms.get('words') or ():
        found = [k for k, low in enumerate(lower, 1) if word in low]
        if found and len(found) <= max(30, n // 12):
            for k in found:
                scores[k] = scores.get(k, 0) + 1000 // len(found)
    for phrase in terms.get('phrases') or ():
        found = [k for k, line in enumerate(lines, 1) if phrase in line]
        if found and len(found) <= 20:
            for k in found:
                scores[k] = scores.get(k, 0) + 6000 // len(found)
    starts = [entry.n for entry in entries]

    def enclosing(k):
        index = bisect.bisect_right(starts, k) - 1
        indent = _indent(lines[k - 1])
        while index >= 0 and entries[index].indent > indent and entries[index].n != k:
            index -= 1
        return index

    def extent(index):
        if index < 0:
            first, last = 1, (entries[0].n - 1 if entries else n)
        else:
            first, last = entries[index].n, n
            for later in entries[index + 1:]:
                if later.indent <= entries[index].indent:
                    last = later.n - 1
                    break
        while last > first and not lines[last - 1].strip():
            last -= 1
        return first, last
    groups: dict[int, list[int]] = {}
    for k in scores:
        groups.setdefault(enclosing(k), []).append(k)
    ranked = []
    for index, hits in groups.items():
        first, last = extent(index)
        ranked.append((-sum(scores[k] for k in hits), first, last, index, hits))
    for _, first, last, index, hits in sorted(ranked):
        chars = sum(len(lines[k - 1]) + 1 for k in range(first, last + 1))
        if last - first + 1 <= DECLARATION_LINES and chars <= DECLARATION_CHARS and add(range(first, last + 1)):
            continue
        if index >= 0:
            add([first])                    # its first line, then a window around each match, the best first
        for k in sorted(hits, key=lambda k: (-scores[k], k)):
            add(range(max(first, k - WINDOW_LINES), min(last, k + WINDOW_LINES) + 1))
    for k in sorted(scores, key=lambda k: (-scores[k], k)):
        if k not in covered:
            add(range(k - CONTEXT_LINES, k + CONTEXT_LINES + 1))
    # The top of the file (imports) and its end, so a new line can be placed there, when the budget still has room.
    head, used = [], 0
    for k in range(1, min(n, HEAD_LINES) + 1):
        used += len(lines[k - 1]) + 1
        if used > HEAD_CHARS:
            break
        head.append(k)
    add(head)
    tail, used = [], 0
    for k in range(n, max(0, n - TAIL_LINES), -1):
        used += len(lines[k - 1]) + 1
        if used > TAIL_CHARS:
            break
        tail.append(k)
    add(tail)
    # What budget is left goes to the lines around what is already shown, widening in steps, the best-matching places
    # first: an edit often needs the code beside the code it changes (a new function after its neighbour).
    for width in FILL_STEPS:
        for first, last in sorted(_merge(covered, lines),
                                  key=lambda r: (-max((scores.get(k, 0) for k in range(r[0], r[1] + 1)), default=0), r[0])):
            add(range(first - width, first))
            add(range(last + 1, last + 1 + width))
    ranges = _merge(covered, lines)
    if not ranges:
        return None
    rendered = render_parts(rel, lines, ranges, outline_cap, entries)
    return {'ranges': ranges, 'lines': n, 'text': rendered, 'chars': len(rendered)}


def line_span(text, old):
    """(first, last) line of the one place `old` occurs in `text`, or None when it occurs nowhere or more than once."""
    if not old or text.count(old) != 1:
        return None
    start = text.find(old)
    return text.count('\n', 0, start) + 1, text.count('\n', 0, start + len(old) - 1) + 1


def changed_lines(before, after):
    """(first, last) line of `before` that an edit changed, found by comparing the two texts line by line; a pure
    insertion is the line it follows."""
    old, new = split_lines(before), split_lines(after)
    low = min(len(old), len(new))
    prefix = 0
    while prefix < low and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while suffix < low - prefix and old[-1 - suffix] == new[-1 - suffix]:
        suffix += 1
    first, last = prefix + 1, len(old) - suffix
    if last < first:
        first = last = min(max(prefix, 1), max(len(old), 1))
    return first, last


def holding_range(ranges, first, last):
    """The index of the shown range that holds lines first..last whole, or None."""
    return next((i for i, (a, b) in enumerate(ranges) if a <= first and last <= b), None)


def shifted_ranges(ranges, index, last, delta):
    """The ranges after an edit inside range `index` ending at line `last` added `delta` lines: the range grows by it,
    the ranges after it move."""
    moved = []
    for i, (a, b) in enumerate(ranges):
        if i == index:
            a, b = a, b + delta
        elif a > last:
            a, b = a + delta, b + delta
        if b >= a:
            moved.append([a, b])
    return moved


def changed_blocks(current, candidate):
    """The (first, last) lines of `candidate` that differ from `current`: where a revision candidate made its changes."""
    old, new = split_lines(current), split_lines(candidate)
    blocks = []
    for tag, _, _, start, stop in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag != 'equal' and stop > start:
            blocks.append((start + 1, stop))
    return blocks


def quotable(text):
    """Whether any line of the text is short enough to be part of an excerpt."""
    return any(len(line) <= MAX_LINE_CHARS for line in text.split('\n'))
