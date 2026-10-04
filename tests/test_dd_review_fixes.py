"""Fixes after the review of the merged batch DD+EE+CC (large files shown in parts).

Each test names the finding it covers and fails without its fix.
"""
import hashlib
import json

import pytest

from runesmith.app.author_allowance import ordinary_allowance
from runesmith.app.author_recovery import replay_context
from runesmith.app.building import build_step
from runesmith.app.planner import (PlannerUnavailable, admit_answer_files, admit_revision_answer, candidate_shown,
                                   milestone_contract, milestone_terms, settled_state, source_context)
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.source_focus import (CONTEXT_CHARS, recorded_context, recorded_excerpts, save_focus,
                                        select_context)
from test_source_parts import covered, line_of, milestone, parts_of, plan_for, program
from test_studio import scripted


def module(name, size):
    """A JavaScript module of about `size` bytes: small exported functions with names of their own."""
    out, i = [], 0
    while sum(len(x) + 1 for x in out) < size:
        out += [f'export function {name}{i}(a) {{', f'  return a + {i};', '}']
        i += 1
    return '\n'.join(out) + '\n'


def j11_program(root):
    """J11's motion.mjs on 2026-10-04: 40,179 bytes, past the 40,000 cap, prioritized."""
    text = program(root, functions=372)
    assert 40000 < len(text.encode()) < 42000
    return text


# -------------------------------------------------------------------- findings 1 and 25 --

def test_a_module_the_milestone_names_is_shown_whole_beside_the_prioritized_program(tmp_path):
    # Finding 1: a_layout.mjs and z_util.mjs took the room before effects.mjs, which the milestone names; with the
    # program's parts spending the rest, effects.mjs was omitted and the milestone waited for the owner.
    ws = plan_for(tmp_path, title='Wire the effects module',
                  detail='effects.mjs applies the blur: change blurRadius in effects.mjs and call it from motion.mjs',
                  done_when='blur works')
    program(tmp_path, functions=480)
    for name, size in (('a_layout.mjs', 6000), ('effects.mjs', 5000), ('z_util.mjs', 1000)):
        (tmp_path / name).write_text(module(name[:-4], size), encoding='utf-8', newline='\n')
    save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')
    context = source_context(ws, milestone=milestone(ws))
    assert 'effects.mjs' in context['files'] and 'motion.mjs' in context['excerpts'] and context['omitted'] == []
    assert context['selection']['used_chars'] <= CONTEXT_CHARS


def test_room_is_kept_for_new_modules_beside_a_prioritized_program_over_the_cap(tmp_path):
    # Finding 25: J11's motion.mjs filled about 40,000 of the 48,000 characters, so the modules the models add (each
    # feature in a file of its own) were omitted one by one, also the ones that already existed.
    ws = plan_for(tmp_path, title='Named paints', detail='masks.mjs holds the mask shapes; paints.mjs the named paints',
                  done_when='paints can be named')
    j11_program(tmp_path)
    for name in ('editor.mjs', 'index.html', 'record.html', 'renderer.mjs', 'scatter.mjs'):
        (tmp_path / name).write_text(f'// {name}\n' + 'export const ready = true;\n' * 24, encoding='utf-8', newline='\n')
    for name in ('effects', 'masks', 'paints', 'typefaces'):
        (tmp_path / f'{name}.mjs').write_text(module(name, 2500), encoding='utf-8', newline='\n')
    save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')
    context = source_context(ws, milestone=milestone(ws))
    assert set(context['omitted']) <= {'typefaces.mjs'} and 'motion.mjs' in context['excerpts']       # 12,000 kept, not more
    assert {'masks.mjs', 'paints.mjs', 'effects.mjs', 'scatter.mjs', 'editor.mjs', 'record.html', 'renderer.mjs'} <= set(context['files'])
    assert context['selection']['used_chars'] <= CONTEXT_CHARS


def test_the_named_files_come_before_the_others_when_the_budget_is_short(tmp_path):
    ws = plan_for(tmp_path, title='Late module', detail='z_last.mjs needs a change', done_when='done')
    for n in range(10):
        (tmp_path / f'a_pad{n}.mjs').write_text(module(f'pad{n}', 5000), encoding='utf-8', newline='\n')
    (tmp_path / 'z_last.mjs').write_text(module('last', 5000), encoding='utf-8', newline='\n')
    plain = source_context(ws)
    assert 'z_last.mjs' not in plain['files']                                   # alphabetical: the pads fill the budget
    named = source_context(ws, milestone=milestone(ws))
    assert 'z_last.mjs' in named['files'] and named['selection']['used_chars'] <= CONTEXT_CHARS


def gap_project(tmp_path):
    """effects.mjs, which the milestone does not name, does not fit beside the prioritized program."""
    ws = plan_for(tmp_path, title='Wire the effects module', detail='apply the blur radius to each frame', done_when='blur works')
    program(tmp_path, functions=480)
    (tmp_path / 'a_layout.mjs').write_text(module('layout', 9000), encoding='utf-8', newline='\n')
    effects = module('effect', 5000)
    (tmp_path / 'effects.mjs').write_text(effects, encoding='utf-8', newline='\n')
    (tmp_path / 'b_pad.mjs').write_text(module('util', 5000), encoding='utf-8', newline='\n')
    ws.update_settings({'build_steps': True, 'build_apply': True, 'build_paths': ['motion.mjs', 'effects.mjs']})
    save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')
    old = '  return a + 3;'
    assert effects.count(old) == 1
    answer = {'title': 'Blur', 'files': [{'path': 'effects.mjs', 'edits': [{'old_text': old, 'new_text': '  return a + 3 + 1;'}]}]}
    scripted(ws, [answer, answer, answer], roles=('plan',))
    return ws, effects.replace(old, '  return a + 3 + 1;')


def tries_used(ws):
    return ordinary_allowance(ws, milestone_contract(ws, milestone(ws)), source_context(ws)['snapshot_digest'])['used']


def test_a_file_the_last_answer_could_not_change_is_shown_in_the_next_round_with_no_try_and_no_owner(tmp_path):
    # Finding 1: the refusal waited for the owner, who was away, and a source change made one more refused call.
    ws, changed = gap_project(tmp_path)
    assert 'effects.mjs' not in source_context(ws, milestone=milestone(ws))['files']
    with pytest.raises(PlannerUnavailable, match='effects.mjs was not shown to the model') as refused:
        build_step(ws, ws.router(), author_only=True)
    assert settled_state(refused.value) == 'context_gap' and tries_used(ws) == 0
    assert milestone_terms(ws, milestone(ws))['wanted'] == ['effects.mjs']
    assert milestone_terms(ws, milestone(ws), feedback=False)['wanted'] == []        # the Checker's words are the milestone's
    context = source_context(ws, milestone=milestone(ws))
    assert 'effects.mjs' in context['files'] and context['selection']['used_chars'] <= CONTEXT_CHARS
    draft = ws._draft(build_step(ws, ws.router(), author_only=True)['draft'])       # the next round builds, nobody asked
    assert draft['files'][0]['path'] == 'effects.mjs' and draft['files'][0]['content'] == changed
    assert tries_used(ws) == 1


# ------------------------------------------------------------------------- finding 2 --

def revision_over(ws, text, ctx):
    """A candidate that added a 150-line block, so its shown lines differ from the current file's."""
    block = [f'  // candidate work line {i} ' + 'x' * 60 for i in range(150)]
    anchor = '  const value300 = project.items[300] * time;'
    candidate = text.replace(anchor, anchor + '\n' + '\n'.join(block))
    revision = {'id': 'd0001', 'files': [{'path': 'motion.mjs', 'content': candidate, 'base': text,
                                          'expected_sha256': hashlib.sha256(text.encode()).hexdigest()}]}
    return revision, candidate, block, candidate_shown(ws, revision, ctx, milestone(ws))[3]


def test_an_edit_copied_from_the_current_excerpt_keeps_the_candidates_work(tmp_path):
    ws = plan_for(tmp_path)
    text = program(tmp_path)
    ctx = source_context(ws, milestone=milestone(ws))
    revision, candidate, block, view = revision_over(ws, text, ctx)
    cand_shown = {n for a, b in view['motion.mjs']['ranges'] for n in range(a, b + 1)}
    lines, cand_lines = text.split('\n'), candidate.split('\n')
    pick = next(line for a, b in parts_of(ctx)['ranges'] for k in range(a, b + 1) for line in [lines[k - 1]]
                if len(line.strip()) > 20 and text.count(line) == 1 and candidate.count(line) == 1
                and cand_lines.index(line) + 1 not in cand_shown)
    changed = pick + ' // touched'
    done = admit_revision_answer(ws, ctx, [{'path': 'motion.mjs', 'edits': [{'old_text': pick, 'new_text': changed}]}],
                                 revision, candidate_view=view)[0]
    assert done['revision_base'] == 'candidate' and block[0] in done['content'] and changed in done['content']
    assert done['content'] == candidate.replace(pick, changed) and done['base'] == text


def test_an_edit_the_candidate_no_longer_has_is_still_applied_to_the_current_file(tmp_path):
    ws = plan_for(tmp_path)
    text = program(tmp_path)
    ctx = source_context(ws, milestone=milestone(ws))
    revision, candidate, block, view = revision_over(ws, text, ctx)
    probe = '  const camera = project.camera || [];'
    assert probe in candidate
    revision['files'][0]['content'] = candidate.replace(probe + '\n', '')       # the candidate dropped the camera line
    view = candidate_shown(ws, revision, ctx, milestone(ws))[3]
    out = admit_revision_answer(ws, ctx, [{'path': 'motion.mjs', 'edits': [{'old_text': probe, 'new_text': probe + ' // x'}]}],
                                revision, candidate_view=view)[0]
    assert out['revision_base'] == 'current' and out['content'] == text.replace(probe, probe + ' // x')


# ------------------------------------------------------------------------- finding 3 --

def test_an_old_text_ending_in_a_newline_cannot_change_the_line_after_the_last_shown_one(tmp_path):
    ws = plan_for(tmp_path)
    text = program(tmp_path)
    ctx = source_context(ws, milestone=milestone(ws))
    last = parts_of(ctx)['ranges'][0][1]
    lines = text.split('\n')
    line = lines[last - 1]
    assert not covered(parts_of(ctx), last + 1) and lines[last] == '}'
    with pytest.raises(PlannerUnavailable, match=f'on lines {last}–{last + 1} of') as refused:
        admit_answer_files(ws, ctx, [{'path': 'motion.mjs', 'edits': [{'old_text': line + '\n', 'new_text': line + '\n// note'}]}])
    assert refused.value.feedback['lines'] == [last, last + 1]
    # the same edit with its newline kept changes only shown lines
    kept = admit_answer_files(ws, ctx, [{'path': 'motion.mjs', 'edits': [{'old_text': line + '\n', 'new_text': line + '\n// note\n'}]}])
    assert kept[0]['content'].split('\n')[last - 1:last + 2] == [line, '// note', '}']
    # and an edit inside the shown lines, joined to nothing, is as before
    assert admit_answer_files(ws, ctx, [{'path': 'motion.mjs', 'edits': [{'old_text': line, 'new_text': line + ' // ok'}]}])


# ------------------------------------------------------------------------- finding 4 --

def test_a_kept_answer_is_not_checked_against_a_whole_file_its_call_was_shown_only_in_parts(tmp_path):
    ws = plan_for(tmp_path)
    program(tmp_path)
    other = '\n'.join(f'export function helper{i}(a, b) {{\n  const r{i} = a * {i} + b;\n  return r{i};\n}}\n' for i in range(230)) + '\n'
    (tmp_path / 'other.mjs').write_text(other, encoding='utf-8', newline='\n')
    assert 17000 < len(other.encode()) < 20000
    save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')
    ctx = source_context(ws, milestone=milestone(ws))
    assert 'other.mjs' in ctx['excerpts'] and 'other.mjs' not in ctx['files']     # shown in parts: the budget could not hold it
    replay = replay_context(ws, collect_snapshot(ws), recorded_excerpts(ctx))
    assert 'other.mjs' not in replay['files'] and 'other.mjs' not in replay['file_hashes'] and 'other.mjs' in replay['excerpts']
    shown = ctx['excerpts']['other.mjs']['ranges']
    i = next(i for i in range(0, 230, 3) if not any(a <= n <= b for a, b in shown for n in range(line_of(other, f'function helper{i}('),
                                                                                                  line_of(other, f'function helper{i}(') + 4)))
    edit = {'path': 'other.mjs', 'edits': [{'old_text': f'  const r{i} = a * {i} + b;', 'new_text': f'  const r{i} = a * {i} + b + 1;'}]}
    for label, context in (('the call', ctx), ('the replay', replay)):
        with pytest.raises(PlannerUnavailable, match='which the model was not shown'):
            admit_answer_files(ws, context, [edit])


# ------------------------------------------------------------------------- finding 5 --

def test_a_file_over_what_a_draft_can_hold_is_not_shown_and_says_so_before_any_call(tmp_path):
    from runesmith.app.workspace import MAX_DRAFT_FILE_BYTES
    ws = plan_for(tmp_path)
    (tmp_path / 'big.py').write_text('x = 1\n' * 66700, encoding='utf-8', newline='\n')      # 400,200 bytes
    (tmp_path / 'ok.py').write_text('x = 1\n' * 66000, encoding='utf-8', newline='\n')       # 396,000 bytes
    assert (tmp_path / 'big.py').stat().st_size > MAX_DRAFT_FILE_BYTES > (tmp_path / 'ok.py').stat().st_size
    context = source_context(ws, milestone=milestone(ws))
    assert 'big.py' not in context.get('excerpts', {}) and context['omission_reasons']['big.py'] == 'file_limit'
    assert 'ok.py' in context['excerpts']                                                    # still shown, and can be drafted
    with pytest.raises(PlannerUnavailable, match='big.py is too large to draft \\(400,000 bytes at most\\)') as refused:
        admit_answer_files(ws, context, [{'path': 'big.py', 'edits': [{'old_text': 'x = 1', 'new_text': 'x = 2'}]}])
    assert settled_state(refused.value) != 'context_gap' and 'Split it' in str(refused.value)
    assert recorded_context(collect_snapshot(ws), [], {})['omission_reasons']['big.py'] == 'file_limit'
    # a file that is quotable and small enough but has no line short enough is still said as before
    (tmp_path / 'wide.py').write_text('x = 1; ' * 7000, encoding='utf-8', newline='\n')
    with pytest.raises(PlannerUnavailable, match='wide.py is too large to show a model, even in parts'):
        admit_answer_files(ws, source_context(ws, milestone=milestone(ws)),
                           [{'path': 'wide.py', 'edits': [{'old_text': 'x = 1', 'new_text': 'x = 2'}]}])
