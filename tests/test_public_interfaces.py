import copy
import json
from types import SimpleNamespace

import pytest

from runesmith.app.acceptance_contracts import expectations, publish_expectations
from runesmith.app.building import verify_draft
from runesmith.app.planner import draft_files, draft_prompt
from runesmith.app.public_interfaces import clean_interfaces
from runesmith.app.revision_context import inspect_revision, save_selection
from runesmith.app.server import api_acceptance_expectations
from runesmith.app.workspace import WorkspaceError
from test_build_steps import setup

CRITERIA = [{'id': 'receipt.count', 'description': 'Return the cumulative count after a successful local operation.'}]
INTERFACES = [{'id': 'receipt', 'invocation': 'example --json record ITEM', 'description': 'Public response; no hidden fixture values.',
    'criterion_ids': ['receipt.count'], 'response_type': 'object', 'fields': [
        {'name': 'count', 'type': 'integer', 'required': True, 'nullable': False, 'unit': 'events', 'description': 'Cumulative count for the requested item.'}]}]


def test_versioned_interface_reaches_author_and_preserves_old_contract_and_budget(tmp_path):
    ws = setup(tmp_path, acceptance=True)
    first = publish_expectations(ws, 'm1', CRITERIA, 'Initial behavior')
    draft = draft_files(ws, ws.router())
    protected = {p: p.read_bytes() for p in (ws.home / 'acceptance').rglob('*') if p.is_file()}
    budget = ws.home / 'build-attempts/spent.json'; budget.parent.mkdir(exist_ok=True); budget.write_text('{"state":"failed"}')
    second = publish_expectations(ws, 'm1', CRITERIA, 'Prospective response clarification',
                                  interfaces=INTERFACES, expected_digest=first['digest'], by='trainer')
    assert second['version'] == 2 and second['interfaces'] == INTERFACES
    packet = json.loads(draft_prompt(ws, ws.plan()['milestones'][0], revision=draft))
    assert packet['public_acceptance']['interfaces'] == INTERFACES
    assert verify_draft(ws, draft)['status'] == 'stale'
    assert json.loads((ws.home / 'acceptance-contracts/history/m1/1.json').read_text()) == first
    assert budget.read_text() == '{"state":"failed"}'
    assert all(p.read_bytes() == data for p, data in protected.items())
    third = publish_expectations(ws, 'm1', CRITERIA, 'Reason update only', expected_digest=second['digest'])
    assert third['interfaces'] == INTERFACES  # old editor cannot silently erase them
    clear = publish_expectations(ws, 'm1', CRITERIA, 'Explicitly remove declaration', interfaces=[], expected_digest=third['digest'])
    assert clear['interfaces'] == []


@pytest.mark.parametrize('change', ['duplicate_interface', 'unknown_criterion', 'missing_criterion', 'wrong_type',
                                  'wrong_boolean', 'duplicate_field', 'empty_field', 'unknown_attribute', 'nested_schema',
                                  'root_type', 'unit_too_long', 'missing_invocation'])
def test_malformed_interfaces_refuse_before_state_changes(tmp_path, change):
    ws = setup(tmp_path)
    first = publish_expectations(ws, 'm1', CRITERIA, 'Original')
    rows = copy.deepcopy(INTERFACES)
    if change == 'duplicate_interface': rows.append(copy.deepcopy(rows[0]))
    elif change == 'unknown_criterion': rows[0]['criterion_ids'] = ['other']
    elif change == 'missing_criterion': rows[0]['criterion_ids'] = []
    elif change == 'wrong_type': rows[0]['fields'][0]['type'] = 'int'
    elif change == 'wrong_boolean': rows[0]['fields'][0]['required'] = 'true'
    elif change == 'duplicate_field': rows[0]['fields'].append(copy.deepcopy(rows[0]['fields'][0]))
    elif change == 'empty_field': rows[0]['fields'][0]['name'] = ''
    elif change == 'unknown_attribute': rows[0]['allow_write'] = True
    elif change == 'nested_schema': rows[0]['fields'][0]['properties'] = {'hidden': True}
    elif change == 'root_type': rows[0]['response_type'] = 'anything'
    elif change == 'unit_too_long': rows[0]['fields'][0]['unit'] = 'x' * 81
    else: rows[0]['invocation'] = ''
    with pytest.raises(WorkspaceError):
        publish_expectations(ws, 'm1', CRITERIA, 'Rejected', interfaces=rows, expected_digest=first['digest'])
    assert expectations(ws, 'm1') == first
    assert not (ws.home / 'acceptance-contracts/history/m1/2.json').exists()


def test_api_requires_current_digest_and_cas_preserves_newer_revision(tmp_path):
    ws = setup(tmp_path)
    studio = SimpleNamespace(ws=ws, bus=SimpleNamespace(publish=lambda *a: None))
    body = {'criteria': CRITERIA, 'interfaces': INTERFACES, 'reason': 'Public interface'}
    with pytest.raises(WorkspaceError, match='digest'):
        api_acceptance_expectations(studio, {}, body, 'm1')
    first = api_acceptance_expectations(studio, {}, dict(body, expected_digest=None), 'm1')
    second = publish_expectations(ws, 'm1', CRITERIA, 'Another editor', expected_digest=first['digest'])
    with pytest.raises(WorkspaceError, match='changed'):
        api_acceptance_expectations(studio, {}, dict(body, expected_digest=first['digest']), 'm1')
    assert expectations(ws, 'm1') == second


def test_interface_declarations_cannot_outlive_removed_criterion_silently(tmp_path):
    ws = setup(tmp_path)
    first = publish_expectations(ws, 'm1', CRITERIA, 'Initial', interfaces=INTERFACES)
    with pytest.raises(WorkspaceError, match='criterion'):
        publish_expectations(ws, 'm1', [{'id':'new', 'description':'Different'}], 'Changed criteria', expected_digest=first['digest'])


def test_array_object_fields_and_nullable_units_are_explicit():
    rows = copy.deepcopy(INTERFACES); rows[0]['response_type'] = 'array'
    rows[0]['fields'][0].update(type='number', nullable=True, required=False, unit='seconds')
    assert clean_interfaces(rows, {'receipt.count'}) == rows


def test_clarified_contract_allows_packet_selection_without_spending(tmp_path):
    ws = setup(tmp_path)
    first = publish_expectations(ws, 'm1', CRITERIA, 'Initial')
    draft = draft_files(ws, ws.router())
    ws._save_draft_state(draft, 'needs_revision')
    publish_expectations(ws, 'm1', CRITERIA, 'Typed public response', interfaces=INTERFACES, expected_digest=first['digest'])
    view = inspect_revision(ws, draft['id'])
    assert not view['blockers']
    selected = save_selection(ws, draft['id'], version=view['version'],
        selections=[{'path':draft['files'][0]['path'], 'unit':'*'}], reason='Focus the clarified response')
    assert selected['view'] and not selected['blockers']
    packet = json.loads(selected['preview']['prompt'])
    assert packet['public_acceptance']['interfaces'] == INTERFACES
    assert not list((ws.home/'build-supplements').glob('*.json'))
    assert ws._draft(draft['id'])['public_acceptance_digest'] == first['digest']


def test_training_guard_reads_real_packet_with_appended_operator_notes(tmp_path):
    import importlib.util
    from pathlib import Path
    file = Path(__file__).parents[1] / 'training/support_m6_public_interface_20260927.py'
    spec = importlib.util.spec_from_file_location('support_public_interface_trial', file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    ws = setup(tmp_path)
    publish_expectations(ws, 'm1', CRITERIA, 'Typed interface', interfaces=INTERFACES)
    note = 'Operator clarification for the exact response contract.'
    ws.add_note('milestone', 'm1', note, 'Response clarification')
    prompt = draft_prompt(ws, ws.plan()['milestones'][0])
    assert note in prompt
    # The former whole-string parser fails on the real mixed-format packet.
    with pytest.raises(json.JSONDecodeError): json.loads(prompt)
    assert module.public_packet(prompt)['public_acceptance']['interfaces'] == INTERFACES
