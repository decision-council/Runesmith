"""Large files are shown in parts, and changed only where shown (journeys J11-B15, J11-B16, J11-G39).

A file over its cap used to be shown to no model, so no model could change it, and the Checker never saw the program it
writes checks for. Now it is shown in parts: an outline and exact excerpts. The safety rule stays: a model may change
only text it was shown, exactly as it is.
"""
import hashlib
import json

from runesmith.app import source_parts as sp
from runesmith.app.planner import draft_prompt, milestone_contract, milestone_terms, source_context
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.source_focus import CONTEXT_CHARS, save_focus
from runesmith.app.workspace import Workspace

RENDER = """// Draws one frame: the camera, then every element.
export function renderFrame(project, time) {
  const camera = project.camera || [];
  let out = '';
  for (const element of project.elements) {
    switch (element.type) {
      case 'rect': {
        out += `<rect fill="${element.fill}"/>`;
        break;
      }
      case 'circle': {
        out += `<circle cx="${element.cx}"/>`;
        break;
      }
    }
  }
  return out + String(camera.length);
}

"""


FUNCTIONS = 520        # about 57,500 bytes: under the 60,000 bytes a draft may hold of one file


def program(root, name='motion.mjs', functions=FUNCTIONS):
    """A JavaScript program of about 60,000 bytes: small functions with lines of their own, and renderFrame, which
    reads project.camera and each element's fill, in the middle."""
    lines = ['// motion.mjs: the engine', "import fs from 'node:fs';", '']
    for i in range(functions):
        if i == functions // 2:
            lines += RENDER.split('\n')[:-1]
        lines += [f'function shape{i}(project, time) {{', f'  const value{i} = project.items[{i}] * time;',
                  f'  return value{i} + {i};', '}', '']
    text = '\n'.join(lines) + '\n'
    (root / name).write_bytes(text.encode('utf-8'))
    return text


def plan_for(tmp_path, title='Camera follows', detail='renderFrame reads project.camera and the fill of each element',
             done_when='the camera moves'):
    ws = Workspace(tmp_path)
    ws.set_brief('Build a small motion tool.')
    ws.save_plan({'summary': 'Tool', 'milestones': [{'title': title, 'detail': detail, 'done_when': done_when}]})
    return ws


def milestone(ws):
    return ws.plan()['milestones'][0]


def parts_of(context, rel='motion.mjs'):
    return context['excerpts'][rel]


def covered(part, line):
    return any(a <= line <= b for a, b in part['ranges'])


def line_of(text, needle):
    return next(n for n, line in enumerate(text.split('\n'), 1) if needle in line)


def outside_function(text, context, rel='motion.mjs'):
    """A function of the program none of whose lines were shown."""
    part = parts_of(context, rel)
    for i in range(0, FUNCTIONS, 7):
        first = line_of(text, f'function shape{i}(')
        if not any(covered(part, n) for n in range(first, first + 4)):
            return i
    raise AssertionError('every function was shown')


# ------------------------------------------------------------------ DD1: what is shown --

def test_a_file_over_the_cap_is_shown_in_parts_around_what_the_milestone_names(tmp_path):
    # Journey J11-B15: a 60,000-byte program was shown to no model. Now: an outline, and the function the milestone names.
    ws = plan_for(tmp_path)
    text = program(tmp_path)
    assert len(text.encode()) > 55000
    context = source_context(ws, milestone=milestone(ws))
    assert 'motion.mjs' not in context['files'] and 'motion.mjs' in context['excerpts']      # apart from whole files
    assert context['omitted'] == [] and 'motion.mjs' not in context['file_hashes']
    part = parts_of(context)
    assert part['lines'] == len(sp.split_lines(text)) and part['sha256'] == hashlib.sha256(text.encode()).hexdigest()
    shown = part['text']
    assert 'outline of motion.mjs' in shown and 'never copy old_text from it' in shown          # the outline says what it is
    assert 'declarations listed (the outline is shortened)' in shown                          # a sample of the functions, said so
    for needle in ("const camera = project.camera || [];", "out += `<rect fill=\"${element.fill}\"/>`;", "case 'circle': {"):
        assert needle in shown                                  # the function that reads the milestone's fields, whole
        assert covered(part, line_of(text, needle))
    assert len(shown) < len(text) and shown.count("function shape") < FUNCTIONS and part['chars'] == len(shown)
    assert not covered(part, line_of(text, f'function shape{outside_function(text, context)}('))     # not the whole file
    for first, last in part['ranges']:                          # every excerpt is the file's exact lines, labelled
        lines = text.split('\n')[first - 1:last]
        assert f'motion.mjs lines {first}–{last} of {part["lines"]}: the exact lines ---\n' + '\n'.join(lines) + '\n' in shown
    assert context['digest'] != hashlib.sha256(json.dumps(context['files'], sort_keys=True).encode()).hexdigest()


def test_the_parts_are_the_same_for_the_same_file_and_words_and_follow_the_words(tmp_path):
    one, two = tmp_path / 'one', tmp_path / 'two'
    one.mkdir(), two.mkdir()
    ws = plan_for(one)
    program(one)
    first = source_context(ws, milestone=milestone(ws))
    assert source_context(ws, milestone=milestone(ws))['digest'] == first['digest']
    assert source_context(ws, milestone=milestone(ws))['excerpts'] == first['excerpts']
    other = plan_for(two, title='Shapes', detail='shape100 and shape101 return their value', done_when='')
    text = program(two)
    again = source_context(other, milestone=milestone(other))
    assert covered(parts_of(again), line_of(text, 'function shape100(')) and covered(parts_of(again), line_of(text, 'function shape101('))
    assert again['digest'] != first['digest']


def test_the_packet_carries_the_parts_apart_so_a_whole_file_replacement_stays_refused(tmp_path):
    ws = plan_for(tmp_path)
    program(tmp_path)
    context = source_context(ws, milestone=milestone(ws))
    prompt = json.loads(draft_prompt(ws, milestone(ws), context))
    assert 'motion.mjs' in prompt['source_context']['excerpts'] and 'motion.mjs' not in prompt['source_context']['files']
    assert any('source_context.excerpts' in rule and 'never from the outline' in rule for rule in prompt['rules'])
    assert 'source_context.excerpts' in draft_prompt.__globals__['DRAFT_SYSTEM']


def test_budget_excerpts_never_push_the_packet_past_the_limit_and_small_files_keep_their_priority(tmp_path):
    ws = plan_for(tmp_path)
    program(tmp_path)
    for n in range(8):
        (tmp_path / f'small{n}.mjs').write_text(f'export const n{n} = {n};\n' * 40)
    for limit in (CONTEXT_CHARS, 30000, 16000, 9000, 5000):
        context = source_context(ws, limit=limit, milestone=milestone(ws))
        used = sum(map(len, context['files'].values())) + sum(p['chars'] for p in context.get('excerpts', {}).values())
        assert used <= limit and context['selection']['used_chars'] == used
        assert all(f'small{n}.mjs' in context['files'] for n in range(8)) or limit <= 9000     # small files come first
    full = source_context(ws, milestone=milestone(ws))
    assert all(f'small{n}.mjs' in full['files'] for n in range(8)) and 'motion.mjs' in full['excerpts']
    # too little room left for a useful part: the file is left out for the budget, as before
    tight = source_context(ws, limit=3000, milestone=milestone(ws))
    assert 'motion.mjs' not in tight.get('excerpts', {}) and tight['omission_reasons']['motion.mjs'] == 'packet_budget'


def test_a_prioritized_file_is_shown_first_and_the_owner_can_prioritize_one_over_the_cap(tmp_path, old_caps):
    ws = plan_for(tmp_path)
    program(tmp_path)
    for n in range(4):
        (tmp_path / f'a{n}.mjs').write_text('export const x = 1;\n' * 900)                # 17,100 bytes each
    unlisted = source_context(ws, milestone=milestone(ws))
    assert unlisted['selection']['used_chars'] <= CONTEXT_CHARS
    preview = save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds of this milestone edit it')
    assert not preview['focus_errors']                                         # over the cap: accepted, shown in parts
    context = source_context(ws, milestone=milestone(ws))
    assert 'motion.mjs' in context['excerpts'] and context['excerpts']['motion.mjs']['chars'] > 20000
    assert not context['focus_errors']


def test_the_outline_lists_every_declaration_with_its_line_and_the_cases_at_their_indent(tmp_path):
    text = program(tmp_path, functions=40)
    lines = sp.split_lines(text)
    outline = '\n'.join(sp._outline_lines(sp.outline_entries('motion.mjs', lines)))
    assert f"{line_of(text, 'function shape0(')}: function shape0(" in outline
    assert f"{line_of(text, 'function shape39(')}: function shape39(" in outline
    assert f"{line_of(text, 'export function renderFrame')}: export function renderFrame(" in outline
    assert f"{line_of(text, 'case ' + chr(39) + 'rect' + chr(39))}:       case 'rect':" in outline        # indented as in the file
    assert 'shortened' not in outline and len(outline) <= sp.OUTLINE_CHARS
    markdown = sp.outline_entries('guide.md', ['# Title', 'text', '## Section', 'const notADeclaration = 1;'])
    assert [(e.n, e.text) for e in markdown] == [(1, '# Title'), (3, '## Section')]
    python = sp.outline_entries('tool.py', ['import os', 'def f():', '    def inner():', '        pass', 'class A:', '    def m(self):', '        pass'])
    assert [e.n for e in python] == [2, 3, 5, 6]


def test_a_file_none_of_whose_lines_can_be_quoted_is_not_shown_even_in_parts(tmp_path):
    ws = plan_for(tmp_path)
    (tmp_path / 'wide.mjs').write_bytes(b'const a = 1; ' * 12500)                 # one line of 162,500 characters: over the cap
    context = source_context(ws, milestone=milestone(ws))
    assert 'wide.mjs' not in context.get('excerpts', {}) and context['omission_reasons']['wide.mjs'] == 'file_limit'


def test_the_terms_are_the_milestones_identifiers_and_quoted_strings_and_the_refused_lines(tmp_path):
    terms = sp.extract_terms('Camera follows', 'project.camera is a list; the "runes" style fills the shape',
                             'fillStyle', anchors=['  const camera = project.camera || [];', 'x'])
    assert 'project.camera' in terms['words'] and 'camera' in terms['words'] and 'runes' in terms['words']
    assert 'the' not in terms['words'] and 'fillstyle' in terms['words']
    assert terms['phrases'] == ['const camera = project.camera || [];']


def test_a_builds_words_include_the_newest_failing_checks_and_the_lines_a_refusal_asked_for(tmp_path):
    from runesmith.app.acceptance_contracts import expectation_digest, expectations, publish_expectations
    ws = plan_for(tmp_path)
    publish_expectations(ws, 'm1', [{'id': 'c1', 'description': 'The sunrise glow fades out at 2 seconds.'}], 'first')
    contract = expectations(ws, 'm1')
    draft = ws.save_draft(title='D', why='w', files=[{'path': 'a.py', 'content': 'x = 1\n', 'expected_absent': True}],
                          drafted_by='x', milestone='m1')
    ws._save_draft_state(draft, 'needs_revision', contract=milestone_contract(ws, milestone(ws)),
                         public_acceptance_digest=expectation_digest(ws, 'm1'),
                         verification={'status': 'failed', 'public_contracts': [
                             {'milestone': 'm1', 'digest': contract['digest'], 'criteria': contract['criteria']}],
                             'acceptance': {'status': 'failed', 'failure_details': [{'test': 't', 'criteria': ['c1'], 'trace_tail': ''}]}})
    words = milestone_terms(ws, milestone(ws))['words']
    assert 'sunrise' in words and 'glow' in words and 'camera' in words            # the failing check, and the milestone's own
    assert 'sunrise' not in milestone_terms(ws, milestone(ws), feedback=False)['words']      # the Checker's words are the milestone's
    ws._save_draft_state(ws._draft(draft['id']), 'waiting')
    assert 'sunrise' not in milestone_terms(ws, milestone(ws))['words']            # only a draft that still needs revision counts
    ws.home.joinpath('build-attempts').mkdir(exist_ok=True)
    (ws.home / 'build-attempts' / ('c' * 32 + '.json')).write_text(json.dumps({
        'state': 'failed', 'utc': '2026-10-02T06:00:00Z', 'contract': milestone_contract(ws, milestone(ws)),
        'feedback': {'requested_old_text': '  const aurora = project.sky;\n  x\n'}}))
    terms = milestone_terms(ws, milestone(ws))
    assert terms['phrases'] == ['const aurora = project.sky;']                         # whole lines the answer tried to change
    assert milestone_terms(ws, milestone(ws), feedback=False)['phrases'] == []
