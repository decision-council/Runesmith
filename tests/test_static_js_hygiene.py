"""Two browser slips found live in journey J4, checked across every Studio script so they cannot come back.

- Element.append prints null as the word "null" (J4-B3: a stray "null" under Build continuation). A part that may be
  missing must be filtered out: ``el.append(...[a, b ? c : null].filter(Boolean))``.
- After an ``await``, a click event's ``currentTarget`` is null (J4-B2: Settings choices never moved their highlight).
  A handler takes the button before it awaits anything.
"""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "runesmith" / "app" / "static" / "js"
APPEND = re.compile(r"\.(append|prepend|replaceChildren|after|before)\(")
HANDLER = re.compile(r"async \(\s*(\w+)\s*\)\s*=>\s*\{")


def _call_args(text: str, start: int) -> tuple[list[str], int]:
    """The top-level arguments of a call whose opening parenthesis ends at ``start``, and where the call ends."""
    depth, i, parts, current = 1, start, [], start
    while i < len(text) and depth:
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c in "'\"`":
            quote, i = c, i + 1
            while i < len(text) and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
        elif c == "," and depth == 1:
            parts.append(text[current:i])
            current = i + 1
        i += 1
    parts.append(text[current:i - 1])
    return parts, i


def null_appends(text: str) -> list[int]:
    lines = []
    for match in APPEND.finditer(text):
        parts, end = _call_args(text, match.end())
        if text[match.end():match.end() + 3] == "..." and ".filter(Boolean)" in text[match.end():end]:
            continue
        if any(re.search(r":\s*(null|undefined)\s*$", p.strip()) or re.match(r"^[\w.?]+\s*&&", p.strip()) for p in parts):
            lines.append(text.count("\n", 0, match.start()) + 1)
    return lines


def target_after_await(text: str) -> list[int]:
    lines = []
    for match in HANDLER.finditer(text):
        name, i, depth = match.group(1), match.end(), 1
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[match.end():i]
        waited, target = body.find("await "), body.find(name + ".currentTarget")
        if waited != -1 and target != -1 and waited < target:
            lines.append(text.count("\n", 0, match.start()) + 1)
    return lines


def scripts():
    found = sorted(STATIC.rglob("*.js"))
    assert found, STATIC
    return found


def test_no_studio_script_can_print_null_or_false_into_the_page():
    bad = {p.name: lines for p in scripts() if (lines := null_appends(p.read_text(encoding="utf-8")))}
    assert bad == {}, f"append() with a part that may be null or false (prints as text); filter them: {bad}"


def test_no_click_handler_reads_its_button_after_waiting():
    bad = {p.name: lines for p in scripts() if (lines := target_after_await(p.read_text(encoding="utf-8")))}
    assert bad == {}, f"currentTarget read after an await is null; take it first: {bad}"


def test_the_checks_catch_the_slips_they_are_for():
    assert null_appends("el.append(h('b', 'x'), last ? h('p', last) : null);") == [1]
    assert null_appends("el.append(...[h('b', 'x'), last ? h('p', last) : null].filter(Boolean));") == []
    assert null_appends("el.append(ok && h('p', 'x'));") == [1]
    assert target_after_await("b.onclick = async (e) => { await save(); e.currentTarget.blur(); };") == [1]
    assert target_after_await("b.onclick = async (e) => { const b = e.currentTarget; await save(); b.blur(); };") == []
