"""The Checker, the second model and the Studio see large files in parts too (journeys J11-B15, J11-B16)."""
import json

from runesmith.app.acceptance_autopilot import _packet as second_model_packet
from runesmith.app.acceptance_proposals import packet as checker_packet
from runesmith.app.planner import draft_prompt, source_context
from runesmith.app.source_focus import CONTEXT_CHARS, inspect_context, save_focus
from runesmith.app.snapshots import collect_snapshot
from test_source_parts import covered, line_of, milestone, plan_for, program

CAMERA = '  const camera = project.camera || [];'
FILL = '        out += `<rect fill="${element.fill}"/>`;'


def j11_shaped(tmp_path):
    """J11 on 2026-10-01: motion.mjs of about 45,000 bytes, and a milestone about the camera and each element's fill."""
    ws = plan_for(tmp_path, title='The camera follows the subject',
                  detail='project.camera is a list of keyframes {t, x, y, zoom}; every element is drawn with its fill',
                  done_when='at 1 s the camera has moved and the fill of each shape is unchanged')
    text = program(tmp_path, functions=420)
    assert 44000 < len(text.encode()) < 48000
    for name in ('editor.mjs', 'index.html', 'record.html', 'renderer.mjs'):
        (tmp_path / name).write_text(f'// {name}\n' + 'export const ready = true;\n' * 30)
    (tmp_path / 'sample.motion.json').write_text(json.dumps({'project': {'name': 'x', 'width': 1, 'height': 1, 'fps': 1}}))
    return ws, text


def source_size(context):
    return sum(map(len, context['files'].values())) + sum(p['chars'] for p in context.get('excerpts', {}).values())


def test_the_checker_is_shown_the_lines_that_read_the_milestones_fields(tmp_path):
    # J11-B16: motion.mjs passed the Checker's 16,000 characters long ago, so the model writing J11's checks never saw
    # the program and guessed its formats ("color" for "fill", a camera object for the camera list).
    ws, text = j11_shaped(tmp_path)
    context = checker_packet(ws, 'm1')['source_context']
    assert 'motion.mjs' not in context['files'] and 'motion.mjs' in context['excerpts']
    shown = context['excerpts']['motion.mjs']['text']
    assert CAMERA in shown and FILL in shown and 'case \'circle\': {' in shown          # what shows "project.camera" and "fill"
    assert 'outline of motion.mjs' in shown
    assert source_size(context) <= 16000                                                # the Checker's budget holds
    assert context['excerpts']['motion.mjs']['chars'] <= 9600                           # the program may take 60% of it
    assert all(name in context['files'] for name in ('editor.mjs', 'index.html', 'sample.motion.json'))   # small files too
    assert 'omission_reasons' in context and 'motion.mjs' not in context['omission_reasons']


def test_the_build_packet_holds_the_same_lines(tmp_path):
    ws, text = j11_shaped(tmp_path)
    prompt = json.loads(draft_prompt(ws, milestone(ws)))['source_context']
    shown = prompt['excerpts']['motion.mjs']
    assert 'motion.mjs' not in prompt['files']
    assert covered(shown, line_of(text, CAMERA)) and covered(shown, line_of(text, 'element.fill'))
    assert CAMERA in shown['text'] and FILL in shown['text']
    assert source_size(prompt) <= CONTEXT_CHARS


def test_the_second_model_gets_the_lines_bounded(tmp_path):
    ws, text = j11_shaped(tmp_path)
    packet = second_model_packet(ws, 'm1', {'examples': []}, [])
    shown = packet['program_excerpts']['motion.mjs']
    assert CAMERA in shown and FILL in shown and 'outline of motion.mjs' in shown
    assert sum(map(len, packet['program_excerpts'].values())) <= 6000
    plain = plan_for(tmp_path / 'plain') if (tmp_path / 'plain').mkdir() is None else None
    (tmp_path / 'plain' / 'a.py').write_text('x = 1\n')
    assert 'program_excerpts' not in second_model_packet(plain, 'm1', {'examples': []}, [])      # nothing large: nothing added


def test_a_revision_or_retry_request_to_the_checker_keeps_the_lines_too(tmp_path):
    from runesmith.app.acceptance_proposals import _lean
    ws, text = j11_shaped(tmp_path)
    lean = _lean(ws, checker_packet(ws, 'm1'))['source_context']
    assert CAMERA in lean['excerpts']['motion.mjs']['text'] and source_size(lean) <= 6000


def test_the_drawer_says_which_files_are_shown_in_parts_and_which_lines(tmp_path):
    ws, text = j11_shaped(tmp_path)
    shown = inspect_context(ws)
    row = next(r for r in shown['rows'] if r['path'] == 'motion.mjs')
    assert row['included'] and row['in_parts'] and row['reason'] is None and row['lines'] == len(text.split('\n')) - 1
    assert row['ranges'] and row['chars'] > 4000 and covered({'ranges': row['ranges']}, line_of(text, CAMERA))
    assert next(r for r in shown['rows'] if r['path'] == 'editor.mjs').get('in_parts') is None      # a whole file is just included
    assert shown['parts_count'] == 1 and shown['parts_for'] == {'id': 'm1', 'title': 'The camera follows the subject'}
    assert shown['included_count'] == shown['whole_count'] + 1 and shown['used_chars'] <= CONTEXT_CHARS
    saved = save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')        # over the cap, accepted
    assert not saved['focus_errors'] and next(r for r in saved['rows'] if r['path'] == 'motion.mjs')['focused']


def test_many_small_files_do_not_use_up_the_checkers_budget_before_the_program(tmp_path):
    # The small files are read first, in path order: with J11's 52 features in their own module files they would fill
    # 16,000 characters and the Checker would be as blind as before.
    ws, text = j11_shaped(tmp_path)
    for n in range(24):
        (tmp_path / f'a_module{n:02}.mjs').write_text(f'// module {n}\n' + 'export const value = 1;\n' * 36)       # 850 bytes
    context = checker_packet(ws, 'm1')['source_context']
    assert CAMERA in context['excerpts']['motion.mjs']['text'] and source_size(context) <= 16000
    assert context['excerpts']['motion.mjs']['chars'] >= 6000
    assert 0 < len(context['files']) < 24 + 5                    # some small files were held back, none of them cut
    whole = source_context(ws, milestone=milestone(ws))          # the author's own budget is not held back
    assert len(whole['files']) == 24 + 5 and 'motion.mjs' in whole['excerpts']
