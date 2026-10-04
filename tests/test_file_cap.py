"""A file a step must change is never too large to show (J11's motion.mjs: 40,179 bytes, refused as too large).

These tests use the production limits, with nothing patched: a file the step must change is shown whole up to 160,000
bytes, and a model whose window is too small for the request is turned away before the call.
"""
import json

import pytest

from runesmith.app.author_allowance import ordinary_allowance
from runesmith.app.building import _used_up_cause, build_step
from runesmith.app.planner import (PlannerUnavailable, admit_answer_files, milestone_contract, settled_state,
                                   source_context)
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.source_focus import (CONTEXT_CHARS, CONTEXT_FILE_BYTES, DEFAULT_FILE_BYTES, FOCUSED_FILE_BYTES,
                                        save_focus)
from runesmith.app.workspace import MAX_DRAFT_FILE_BYTES
from runesmith.instruments import OpenAICompatInstrument, Router, ScriptedInstrument
from test_source_parts import milestone, plan_for, program
from test_studio import scripted

J11_BYTES = 40179
EDIT = {'old_text': '  const value3 = project.items[3] * time;', 'new_text': '  const value3 = project.items[3] * time * 2;'}


def j11_program(root, size=J11_BYTES):
    """motion.mjs as J11 had it on 2026-10-04: a program of exactly `size` bytes (quotable lines throughout)."""
    text = program(root, functions=360)
    pad = size - len(text.encode())
    assert pad > 10
    text += '// ' + 'x' * (pad - 4) + '\n'
    (root / 'motion.mjs').write_bytes(text.encode('utf-8'))
    assert (root / 'motion.mjs').stat().st_size == size and text.count(EDIT['old_text']) == 1
    return text


def test_the_limits_leave_room_for_a_file_the_step_must_change():
    assert DEFAULT_FILE_BYTES < CONTEXT_FILE_BYTES < FOCUSED_FILE_BYTES == 160_000
    assert FOCUSED_FILE_BYTES + 40_000 <= CONTEXT_CHARS == 200_000          # such a file fits beside a little context
    assert FOCUSED_FILE_BYTES < MAX_DRAFT_FILE_BYTES == 400_000             # a file a build produced is shown, at least in parts


def test_a_40179_byte_program_that_is_prioritized_is_shown_whole(tmp_path):
    ws = plan_for(tmp_path, title='Camera follows', detail='renderFrame reads project.camera', done_when='the camera moves')
    text = j11_program(tmp_path)
    save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')
    context = source_context(ws, milestone=milestone(ws))
    assert context['files']['motion.mjs'] == text and 'motion.mjs' not in context.get('excerpts', {})
    assert context['omitted'] == [] and context['focus_errors'] == {}
    assert context['selection']['used_chars'] <= CONTEXT_CHARS


def test_a_40179_byte_program_the_step_names_is_shown_whole_and_a_whole_file_answer_is_admitted(tmp_path):
    # The step names the file, nobody prioritized it: it must still be shown, and a model may replace it whole.
    ws = plan_for(tmp_path, title='Wire the camera', detail='change motion.mjs so the camera follows the subject',
                  done_when='the camera moves')
    text = j11_program(tmp_path)
    context = source_context(ws, milestone=milestone(ws))
    assert context['files']['motion.mjs'] == text and 'motion.mjs' not in context.get('excerpts', {})
    changed = text.replace(EDIT['old_text'], EDIT['new_text'])
    ws.update_settings({'build_steps': True, 'build_apply': True, 'build_paths': ['motion.mjs']})
    scripted(ws, [{'title': 'Camera', 'files': [{'path': 'motion.mjs', 'content': changed}]}], roles=('plan',))
    draft = ws._draft(build_step(ws, ws.router(), author_only=True)['draft'])
    assert draft['files'][0]['content'] == changed and 'motion.mjs' in draft['shown_files'] and 'shown_excerpts' not in draft


def test_a_file_the_failing_checks_name_is_shown_whole_too(tmp_path, monkeypatch):
    # Named by the failing checks' sentences, not by the step's own words: the model must change it all the same.
    from runesmith.app import planner
    ws = plan_for(tmp_path, title='Camera follows', detail='the camera follows the subject', done_when='the camera moves')
    text = j11_program(tmp_path)
    assert 'motion.mjs' not in source_context(ws, milestone=milestone(ws))['files']          # nothing names it yet
    real = planner.milestone_terms
    monkeypatch.setattr(planner, 'milestone_terms', lambda ws_, milestone_, **kwargs: dict(
        real(ws_, milestone_, **kwargs), checks='motion.mjs: at 1 s the camera has not moved'))
    assert source_context(ws, milestone=milestone(ws))['files']['motion.mjs'] == text


def test_a_file_that_is_only_context_keeps_its_old_caps(tmp_path):
    # An unrelated 98,000-byte program is not sent whole with every call: it is shown in parts, as before; prioritizing
    # it (it must be changed after all) shows it whole.
    ws = plan_for(tmp_path)
    program(tmp_path, functions=900)
    size = (tmp_path / 'motion.mjs').stat().st_size
    assert CONTEXT_FILE_BYTES < size < FOCUSED_FILE_BYTES
    context = source_context(ws, milestone=milestone(ws))
    assert 'motion.mjs' in context['excerpts'] and 'motion.mjs' not in context['files']
    assert context['excerpts']['motion.mjs']['chars'] <= CONTEXT_FILE_BYTES
    save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')
    context = source_context(ws, milestone=milestone(ws))
    assert 'motion.mjs' in context['files'] and 'motion.mjs' not in context.get('excerpts', {})
    assert context['selection']['used_chars'] <= CONTEXT_CHARS


def test_a_prioritized_program_near_the_new_cap_is_shown_whole_and_one_over_it_in_parts(tmp_path):
    ws = plan_for(tmp_path)
    program(tmp_path, functions=1380)                                        # about 152,000 bytes
    assert 140_000 < (tmp_path / 'motion.mjs').stat().st_size <= FOCUSED_FILE_BYTES
    save_focus(ws, ['motion.mjs'], collect_snapshot(ws)['digest'], 'Builds edit it')
    assert 'motion.mjs' in source_context(ws, milestone=milestone(ws))['files']
    program(tmp_path, functions=1500)                                        # about 166,000 bytes: over the cap
    assert (tmp_path / 'motion.mjs').stat().st_size > FOCUSED_FILE_BYTES
    context = source_context(ws, milestone=milestone(ws))
    assert 'motion.mjs' in context['excerpts'] and 'motion.mjs' not in context['files'] and not context['focus_errors']
    assert context['selection']['used_chars'] <= CONTEXT_CHARS


def test_a_file_no_model_can_be_shown_is_refused_in_words_that_say_who_splits_it(tmp_path):
    ws = plan_for(tmp_path)
    (tmp_path / 'wide.py').write_bytes(b'x = 1; ' * ((FOCUSED_FILE_BYTES + 700) // 7))        # one line: no part can be quoted
    (tmp_path / 'big.py').write_bytes(b'x = 1\n' * ((MAX_DRAFT_FILE_BYTES + 600) // 6))
    context = source_context(ws, milestone=milestone(ws))
    assert context['omission_reasons'] == {'big.py': 'file_limit', 'wide.py': 'file_limit'}
    edit = {'edits': [{'old_text': 'x = 1', 'new_text': 'x = 2'}]}
    with pytest.raises(PlannerUnavailable, match=r'wide.py is too large to show a model, even in parts \(over 160,000 bytes') as refused:
        admit_answer_files(ws, context, [dict(edit, path='wide.py')])
    words = str(refused.value)
    assert 'No model can be shown it to split it' in words and 'yourself' in words and settled_state(refused.value) == 'failed'
    with pytest.raises(PlannerUnavailable, match=r'big.py is too large to draft \(400,000 bytes at most\)') as refused:
        admit_answer_files(ws, context, [dict(edit, path='big.py')])
    assert 'yourself' in str(refused.value) and settled_state(refused.value) == 'failed'


def attempt(ws, row):
    folder = ws.home / 'build-attempts'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'a1.json').write_text(json.dumps(row), encoding='utf-8')


def test_split_it_first_is_said_only_for_a_file_over_the_cap(tmp_path):
    ws = plan_for(tmp_path)
    contract = milestone_contract(ws, milestone(ws))
    (tmp_path / 'wide.py').write_bytes(b'x = 1; ' * ((FOCUSED_FILE_BYTES + 700) // 7))
    (tmp_path / 'big.py').write_bytes(b'x = 1\n' * ((MAX_DRAFT_FILE_BYTES + 600) // 6))
    (tmp_path / 'ok.py').write_bytes(b'x = 1\n' * 3000)                                    # 18,000 bytes: not over any cap
    context, tight = source_context(ws), source_context(ws, limit=3000)
    assert 'ok.py' in context['files'] and 'ok.py' not in tight['files']

    def cause(reason, name='wide.py', shown=context):
        attempt(ws, {'contract': contract, 'snapshot_digest': shown['snapshot_digest'], 'state': 'failed',
                     'utc': '2026-10-04T22:00:00Z', 'feedback': {'not_shown': name, 'reason': reason}})
        return _used_up_cause(ws, contract, shown)
    over = cause('file_limit')
    assert over.startswith('wide.py is too large to show a model, even in parts (over 160,000 bytes')
    assert 'split it first, yourself' in over and 'no step can do that' in over and '40,000 bytes at most' not in over
    assert 'too large to draft (400,000 bytes at most)' in cause('file_limit', 'big.py')
    # An attempt recorded before the cap was raised, for a file within it: nothing to split, and nothing to say once it is shown.
    assert cause('file_limit', 'ok.py') == ''
    within = cause('file_limit', 'ok.py', tight)
    assert 'split it' not in within and 'prioritize it under Author context' in within
    assert 'split' not in cause('not_utf8') and 'UTF-8' in cause('not_utf8')
    assert 'split' not in cause('budget_together') and 'Author context' in cause('budget_together')


def test_a_late_answer_replay_shows_the_same_files_whole(tmp_path):
    # The replay of a late answer (and every selection made without parts) judges an answer by what its call was shown:
    # the 40,179-byte program is whole there too, and a context-only file within the cap is a gap prioritizing closes, not
    # a refusal for its size.
    ws = plan_for(tmp_path, title='Wire the camera', detail='change motion.mjs so the camera follows the subject',
                  done_when='the camera moves')
    text = j11_program(tmp_path)
    program(tmp_path, name='other.mjs', functions=360)
    program(tmp_path, name='aside.mjs', functions=380)
    assert CONTEXT_FILE_BYTES < (tmp_path / 'aside.mjs').stat().st_size < FOCUSED_FILE_BYTES
    context = source_context(ws, milestone=milestone(ws), parts=False)
    assert context['files']['motion.mjs'] == text and 'motion.mjs' not in context['omission_reasons']
    assert context['omission_reasons'].get('aside.mjs') == 'packet_budget'           # not 'file_limit': prioritizing shows it
    edit = {'path': 'aside.mjs', 'edits': [{'old_text': 'function shape3(', 'new_text': 'function shape3x('}]}
    with pytest.raises(PlannerUnavailable, match='aside.mjs was not shown to the model') as refused:
        admit_answer_files(ws, context, [edit])
    assert settled_state(refused.value) == 'context_gap' and refused.value.context_gap['path'] == 'aside.mjs'


def tries_used(ws):
    return ordinary_allowance(ws, milestone_contract(ws, milestone(ws)), source_context(ws)['snapshot_digest'])['used']


def test_a_model_whose_window_is_too_small_is_turned_away_before_the_call_and_the_next_builds(tmp_path):
    # A 98,000-byte file shown whole is about 25,000 tokens: Groq's free tier takes 8,000 at once. It is refused before
    # anything is sent (as the router has always done), the role's next model is asked, and no try is used for the first.
    ws = plan_for(tmp_path, title='Wire the camera', detail='change motion.mjs so the camera follows the subject',
                  done_when='the camera moves')
    text = program(tmp_path, functions=900)
    assert 90_000 < len(text.encode()) <= FOCUSED_FILE_BYTES
    ws.update_settings({'build_steps': True, 'build_apply': True, 'build_paths': ['motion.mjs']})
    assert 'motion.mjs' in source_context(ws, milestone=milestone(ws))['files']
    sent = []

    def transport(*args):
        sent.append(args)
        return 200, {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
    small = OpenAICompatInstrument('groq', 'openai/gpt-oss-120b', base_url='http://groq.invalid/openai/v1',
                                   transport=transport, max_request_tokens=8000)
    large = ScriptedInstrument('large', [{'title': 'Camera', 'files': [{'path': 'motion.mjs', 'edits': [EDIT]}]}])
    events = []
    router = Router({'groq': small, 'large': large}, {'plan': ['groq', 'large']}, backoff_s=(), on_call=events.append)
    draft = ws._draft(build_step(ws, router, author_only=True)['draft'])
    assert not sent and [event['instrument'] for event in events] == ['groq', 'large']
    assert draft['files'][0]['content'] == text.replace(EDIT['old_text'], EDIT['new_text'])
    assert len(large.requests) == 1 and len(large.requests[0]['prompt']) > 90_000          # it was shown the whole file
    assert tries_used(ws) == 1                                                             # the one answer, none for the refusal


def test_a_large_file_shown_whole_gets_room_to_come_back_whole():
    # Journey J11: a 40,179-byte file came back truncated at 12,000 tokens on every route.
    from runesmith.app.planner import draft_answer_tokens, DRAFT_TOKENS, REVISION_TOKENS, MAX_DRAFT_TOKENS
    small = {"files": {"a.py": "x = 1\n"}}
    large = {"files": {"motion.mjs": "y" * 40179, "a.py": "x = 1\n"}}
    huge = {"files": {"big.js": "z" * 400000}}
    assert draft_answer_tokens(small) == DRAFT_TOKENS and draft_answer_tokens(small, True) == REVISION_TOKENS
    assert draft_answer_tokens(large) >= 16000 and draft_answer_tokens(large, True) >= 16000
    assert draft_answer_tokens(huge) == MAX_DRAFT_TOKENS and draft_answer_tokens(None) == DRAFT_TOKENS
