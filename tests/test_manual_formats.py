"""Chat-relay format feedback is a precheck, not code admission or acceptance."""
import json
from types import SimpleNamespace

import pytest

from runesmith import manual
from runesmith.app.planner import DRAFT_SCHEMA, PlannerUnavailable, draft_files
from runesmith.app.server import api_manual_answer
from runesmith.app.worker import EventBus
from runesmith.app.workspace import Workspace
from runesmith.instruments import Router


@pytest.mark.parametrize('file', [
    {'path': 'tool.py', 'content': 'x = 2\n'},
    {'path': 'tool.py', 'purpose': 'Update value', 'edits': [{'old_text': '1', 'new_text': '2'}]},
    {'path': 'tool.py', 'edits': [{'old_text': '# stale', 'new_text': ''}]},
])
def test_current_draft_alternatives_accept_valid_file_shapes(file):
    assert manual.schema_problems({'title': 'Change', 'files': [file]}, DRAFT_SCHEMA) == []


@pytest.mark.parametrize('file, detail', [
    ({'path': 'tool.py'}, 'missing required'),
    ({'path': 'tool.py', 'content': 'x', 'edits': [{'old_text': '1', 'new_text': '2'}]}, 'unexpected field'),
    ({'path': 'tool.py', 'edits': []}, 'outside the allowed range'),
    ({'path': 'tool.py', 'edits': [{'old_text': '1'}]}, 'new_text'),
    ({'path': 'tool.py', 'edits': [{'old_text': True, 'new_text': '2'}]}, 'expected string'),
    ({'path': 7, 'content': 'x'}, 'expected string'),
    ({'path': 'tool.py', 'content': 'x', 'base': 'forged'}, 'unexpected field'),
    ({'path': 'tool.py', 'edits': [{'old_text': '1', 'new_text': '2'}] * 13}, 'outside the allowed range'),
    ('not a file operation', 'expected object'),
])
def test_current_draft_alternatives_reject_bad_shapes_with_local_feedback(file, detail):
    problems = manual.schema_problems({'title': 'Change', 'files': [file]}, DRAFT_SCHEMA)
    assert problems, 'The manual relay must not silently skip files.items.anyOf'
    assert all('answer.files[0]' in p for p in problems)
    assert any(detail in p for p in problems)


@pytest.mark.parametrize('value, schema, accepted', [
    (1, {'anyOf': [{'type': 'number'}, {'type': 'integer'}]}, True),
    (1, {'oneOf': [{'type': 'number'}, {'type': 'integer'}]}, False),
    ('one', {'oneOf': [{'type': 'string'}, {'type': 'integer'}]}, True),
    (True, {'oneOf': [{'type': 'string'}, {'type': 'integer'}]}, False),
    ('x', {'allOf': [{'type': 'string'}, {'minLength': 2}]}, False),
    ('xx', {'allOf': [{'type': 'string'}, {'minLength': 2}]}, True),
    ('x', {'anyOf': [{'type': 'string'}], 'minLength': 2}, False),
    (2, {'allOf': [{'type': 'integer'}], 'enum': [1]}, False),
    ('x', {'anyOf': [False, {'type': 'string'}]}, True),
    ('x', {'allOf': [False, {'type': 'string'}]}, False),
    ('x', {'oneOf': [True, {'type': 'string'}]}, False),
    ('x', {'anyOf': []}, False),
])
def test_compositions_do_not_ignore_siblings_or_exclusive_matches(value, schema, accepted):
    assert (manual.schema_problems(value, schema) == []) is accepted


def make_pending(ws):
    clock = [0.0]
    instrument = manual.ManualInstrument('chat', directory=ws.home / 'manual', timeout_s=1,
        poll_s=1, clock=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
        notify=lambda *args: None)
    result = instrument.complete(prompt='Draft a tool.', system='Builder.', schema=DRAFT_SCHEMA,
                                 max_tokens=100, key='draft-format')
    assert not result.ok and result.error_kind == 'transport'
    return manual.resolve_request(ws.home / 'manual', None)


def test_manual_api_rejects_bad_shape_without_publishing_delivery_and_accepts_correction(tmp_path):
    ws = Workspace(tmp_path)
    rid = make_pending(ws)
    studio = SimpleNamespace(ws=ws, bus=EventBus())
    bad = {'title': 'Change', 'files': [{'path': 'tool.py', 'edits': []}]}
    refused = api_manual_answer(studio, {}, {'text': json.dumps(bad), 'model': 'user-reported'}, rid)
    assert refused['written'] is None and refused['problems']
    assert not (ws.home / 'manual' / f'{rid}.answer.md').exists()
    assert not (ws.home / 'manual' / f'{rid}.answer.json').exists()
    assert not studio.bus.recent
    good = {'title': 'Change', 'files': [{'path': 'tool.py', 'content': 'x = 2\n'}]}
    accepted = api_manual_answer(studio, {}, {'text': json.dumps(good), 'model': 'user-reported'}, rid)
    assert accepted['written'] and accepted['problems'] == []
    assert len(studio.bus.recent) == 1
    assert not (tmp_path / 'tool.py').exists() and ws.drafts() == []


@pytest.mark.parametrize('forced', [False, True])
def test_chat_draft_uses_normal_admission_even_when_format_precheck_is_overridden(tmp_path, forced):
    ws = Workspace(tmp_path)
    ws.save_plan({'summary': 'Local tool', 'milestones': [{'title': 'Change value', 'done_when': 'value is 2'}]})
    source = tmp_path / 'tool.py'
    source.write_bytes(b'x = 1\n')
    operation = {'path': 'tool.py', 'edits': [{'old_text': '1', 'new_text': '2'}]}
    if forced:
        operation['content'] = 'x = 3\n'  # Forbidden dual representation, even after force=True.
    def person(rid, prompt_path):
        reply = json.dumps({'title': 'Small change', 'files': [operation]})
        result = ws.answer_manual(rid, reply, model='self-reported-chat', force=forced)
        assert bool(result['problems']) is forced and result['written']
    instrument = manual.ManualInstrument('chat', directory=ws.home / 'manual', poll_s=0.001, notify=person)
    router = Router({'chat': instrument}, {'plan': ['chat']})
    if forced:
        with pytest.raises(PlannerUnavailable):
            draft_files(ws, router)
        assert ws.drafts() == []
    else:
        draft = draft_files(ws, router)
        assert draft['state'] == 'waiting' and not draft.get('verification')
        assert draft['files'][0]['content'] == 'x = 2\n'
        assert draft['snapshot_digest'] and draft['author_request_key']
    assert source.read_bytes() == b'x = 1\n'
