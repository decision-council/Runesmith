"""An answer that leaves code out is refused (journey J11-G39).

J11's renderer.mjs was written as "// ... (renderer logic from motion.mjs)" and record.html stopped at "// Recording logic
including MediaStreamAudioDestinationNode...": both passed, and the milestones were done in name only. Nothing refused a
file written with its code left out. Now an answer may not ADD such a comment; one already in the file stays.
"""
import pytest

from runesmith.app.planner import PlannerUnavailable, admit_answer_files, draft_files, settled_state, source_context
from runesmith.app.workspace import Workspace
from test_studio import scripted


def workspace(tmp_path, **files):
    ws = Workspace(tmp_path)
    ws.set_brief('Build a small motion tool.')
    ws.save_plan({'summary': 'Tool', 'milestones': [{'title': 'Render', 'done_when': 'frames render'}]})
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding='utf-8', newline='\n')
    return ws


def admit(ws, *answers):
    return admit_answer_files(ws, source_context(ws), list(answers))


STUB = '// ... (renderer logic from motion.mjs)'


def test_the_renderer_stub_is_refused_in_plain_words_naming_the_line(tmp_path):
    ws = workspace(tmp_path)
    content = "import { renderFrame } from './motion.mjs';\n\n" + STUB + '\nexport { renderFrame };\n'
    with pytest.raises(PlannerUnavailable) as refused:
        admit(ws, {'path': 'renderer.mjs', 'content': content})
    assert str(refused.value) == ('renderer.mjs line 3 leaves code out (“// ... (renderer logic from motion.mjs)”): '
                                  'write the code in full; never abbreviate.')
    assert refused.value.feedback == {'path': 'renderer.mjs', 'elided_line': 3}             # an ordinary failed try
    assert settled_state(refused.value) == 'failed' and not getattr(refused.value, 'context_gap', None)


def test_the_recorder_comment_that_stops_at_an_ellipsis_is_refused(tmp_path):
    ws = workspace(tmp_path)
    page = ('<script>\nconst recorder = new MediaRecorder(stream);\n'
            '// Recording logic including MediaStreamAudioDestinationNode...\n</script>\n')
    with pytest.raises(PlannerUnavailable, match='record.html line 3 leaves code out'):
        admit(ws, {'path': 'record.html', 'content': page})


@pytest.mark.parametrize('comment', [
    '// ... the rest',
    '// … more here',
    '// for brevity the other cases are the same',
    '// Rest of the code remains the same',
    '// rest of file',
    '// the rest of the function is unchanged',
    '// rest of the logic',
    '// rest of the implementation',
    '// implementation omitted',
    '// logic omitted for now',
    '// code is omitted',
    '// your code goes here',
    '// handling of errors...',
    '// drawing logic…',
    '// the implementation ...',
    '/* ... */',
    '/* rest of the code */',
    ' * ... remaining methods',
    '<!-- ... rest of the page -->',
    '# ... rest of the module',
    '# implementation goes here',
])
def test_each_way_of_leaving_code_out_is_refused(tmp_path, comment):
    ws = workspace(tmp_path)
    suffix = '.py' if comment.startswith('#') else '.html' if comment.startswith('<!--') else '.js'
    with pytest.raises(PlannerUnavailable, match='leaves code out'):
        admit(ws, {'path': 'new' + suffix, 'content': f'first = 1\n{comment}\nlast = 2\n'})


@pytest.mark.parametrize('comment', [
    '// wait for the frame...',
    '// Draws one frame: the camera, then every element.',
    '// the rest is drawn by renderFrame',
    '// then the next step...',
    '/* the camera */',
    '// TODO: handle resize',
    '// logic is in motion.mjs',
])
def test_an_ordinary_comment_is_allowed(tmp_path, comment):
    ws = workspace(tmp_path)
    files = admit(ws, {'path': 'new.js', 'content': f'first = 1;\n{comment}\nlast = 2;\n'})
    assert files[0]['content'].count(comment) == 1 and files[0]['expected_absent']


def test_pythons_bare_ellipsis_is_a_statement_not_a_comment(tmp_path):
    ws = workspace(tmp_path)
    content = 'from typing import Protocol\n\n\ndef f(): ...\n\n\nclass P(Protocol):\n    def g(self) -> int: ...\n\n\nx = ...\n'
    assert admit(ws, {'path': 'tool.py', 'content': content})[0]['content'] == content


def test_a_document_is_not_code(tmp_path):
    ws = workspace(tmp_path)
    assert admit(ws, {'path': 'notes.md', 'content': '# Notes\n\nand so on...\n// ... for brevity\n'})


def test_an_edit_that_adds_a_stub_is_refused_naming_the_line_in_the_file(tmp_path):
    ws = workspace(tmp_path, **{'engine.mjs': 'function a() {\n  return 1;\n}\n\nfunction b() {\n  return 2;\n}\n'})
    edit = {'path': 'engine.mjs', 'edits': [{'old_text': '  return 2;', 'new_text': '  // ... the rest of the function\n  return 2;'}]}
    with pytest.raises(PlannerUnavailable) as refused:
        admit(ws, edit)
    assert str(refused.value).startswith('engine.mjs line 6 leaves code out (“// ... the rest of the function”)')
    assert refused.value.feedback == {'path': 'engine.mjs', 'elided_line': 6}


def test_an_elision_already_in_the_file_and_left_untouched_is_allowed(tmp_path):
    ws = workspace(tmp_path, **{'legacy.mjs': 'function a() {\n  // ... rest of the code\n  return 1;\n}\n\nfunction b() {\n  return 2;\n}\n'})
    elsewhere = admit(ws, {'path': 'legacy.mjs', 'edits': [{'old_text': '  return 2;', 'new_text': '  return 3;'}]})
    assert elsewhere[0]['content'].count('// ... rest of the code') == 1
    kept = admit(ws, {'path': 'legacy.mjs', 'edits': [{'old_text': '  // ... rest of the code\n  return 1;',
                                                       'new_text': '  // ... rest of the code\n  return 10;'}]})
    assert 'return 10;' in kept[0]['content']                             # the line is the file's own, only quoted again
    whole = admit(ws, {'path': 'legacy.mjs', 'content': 'function a() {\n  // ... rest of the code\n  return 5;\n}\n'})
    assert 'return 5;' in whole[0]['content']
    with pytest.raises(PlannerUnavailable, match='legacy.mjs line 2 leaves code out'):          # another one is new
        admit(ws, {'path': 'legacy.mjs', 'content': 'function a() {\n  // for brevity\n  return 5;\n}\n'})


def test_a_stub_added_to_a_file_shown_in_parts_is_refused_too(tmp_path):
    from test_source_parts import plan_for, program
    ws = plan_for(tmp_path)
    program(tmp_path)
    scripted(ws, [{'title': 'Stub', 'files': [{'path': 'motion.mjs', 'edits': [
        {'old_text': '  const camera = project.camera || [];', 'new_text': '  // ... camera logic\n  const camera = [];'}]}]}],
             roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='motion.mjs line \\d+ leaves code out'):
        draft_files(ws, ws.router())
