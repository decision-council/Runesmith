"""A file shown in parts is changed only where it was shown, judged by what that call was shown (journey J11-B15).

Admission: each old_text must occur exactly once in the whole current file, and its lines must lie inside one shown part;
the file is rebuilt exactly; a whole-file replacement stays refused; a late answer, a correction and a revision are
judged against the lines recorded for their own call, never today's selection.
"""
import hashlib
import json

import pytest

from runesmith.app import source_parts as sp
from runesmith.app.author_allowance import ordinary_allowance
from runesmith.app.author_recovery import admit_packet, prepare_packet
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.build_corrections import correct_rejected_answer, correction_candidates
from runesmith.app.building import author_context_status, build_step, readmit_refused_answer, verify_draft
from runesmith.app.planner import PlannerUnavailable, draft_files, draft_prompt, milestone_contract, settled_state, source_context
from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
from runesmith.app.workspace import _write_json
from test_source_parts import covered, line_of, milestone, outside_function, parts_of, plan_for, program
from test_studio import scripted

CAMERA = '  const camera = project.camera || [];'
CAMERA_NEW = '  const camera = (project.camera || []).slice();'
RETURN = '  return out + String(camera.length);'


def project(tmp_path):
    ws = plan_for(tmp_path)
    text = program(tmp_path)
    ws.update_settings({'build_steps': True, 'build_apply': True, 'build_paths': ['motion.mjs']})
    return ws, text


def answer(*edits, path='motion.mjs', title='Change'):
    return {'title': title, 'files': [{'path': path, 'edits': [{'old_text': o, 'new_text': n} for o, n in edits]}]}


def tries_used(ws):
    contract = milestone_contract(ws, milestone(ws))
    return ordinary_allowance(ws, contract, source_context(ws)['snapshot_digest'])['used']


def an_outside_edit(text, context):
    i = outside_function(text, context)
    return f'  const value{i} = project.items[{i}] * time;', f'  const value{i} = project.items[{i}] * time * 2;', i


# ------------------------------------------------------------------------- admitting --

def test_an_edit_inside_a_shown_part_is_admitted_and_the_whole_file_rebuilt_exactly(tmp_path):
    ws, text = project(tmp_path)
    scripted(ws, [answer((CAMERA, CAMERA_NEW), (RETURN, '  return out;'))], roles=('plan',))
    draft = draft_files(ws, ws.router())
    entry = draft['files'][0]
    assert entry['content'] == text.replace(CAMERA, CAMERA_NEW).replace(RETURN, '  return out;')      # the whole file, exactly
    assert entry['base'] == text and entry['expected_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert 'motion.mjs' not in draft['shown_files'] and draft['shown_excerpts']['motion.mjs']['ranges']
    assert draft['shown_excerpts']['motion.mjs']['sha256'] == entry['expected_sha256']
    assert (tmp_path / 'motion.mjs').read_bytes() == text.encode()                 # nothing was written


def test_an_edit_quoting_text_outside_the_shown_lines_is_refused_naming_the_lines_shown(tmp_path):
    ws, text = project(tmp_path)
    context = source_context(ws, milestone=milestone(ws))
    old, new, i = an_outside_edit(text, context)
    scripted(ws, [answer((CAMERA, CAMERA_NEW), (old, new))], roles=('plan',))
    with pytest.raises(PlannerUnavailable) as refused:
        draft_files(ws, ws.router())
    shown = parts_of(context)['ranges']
    first = line_of(text, f'const value{i} =')
    assert f'on lines {first}–{first} of {parts_of(context)["lines"]}, which the model was not shown' in str(refused.value)
    assert f'It was shown lines {sp.format_ranges(shown)} of motion.mjs' in str(refused.value)
    assert 'never from the outline' in str(refused.value)
    feedback = refused.value.feedback                    # what a correction can use
    assert feedback['path'] == 'motion.mjs' and feedback['shown_ranges'] == shown and feedback['lines'] == [first, first]
    assert feedback['edit_index'] == 2 and feedback['requested_old_text'] == old
    assert settled_state(refused.value) == 'failed' and not getattr(refused.value, 'context_gap', None)   # the model's error


def test_a_refused_edit_outside_the_shown_lines_is_a_failed_try(tmp_path):
    ws, text = project(tmp_path)
    old, new, _ = an_outside_edit(text, source_context(ws, milestone=milestone(ws)))
    scripted(ws, [answer((old, new))], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='which the model was not shown'):
        build_step(ws, ws.router(), author_only=True)
    assert tries_used(ws) == 1                                         # a model answered, wrongly: a try is used
    assert (tmp_path / 'motion.mjs').read_bytes() == text.encode()


def test_a_whole_file_replacement_of_a_file_shown_in_parts_is_refused(tmp_path):
    ws, text = project(tmp_path)
    context = source_context(ws, milestone=milestone(ws))
    scripted(ws, [{'title': 'Rewrite', 'files': [{'path': 'motion.mjs', 'content': text.replace(CAMERA, CAMERA_NEW)}]}],
             roles=('plan',))
    with pytest.raises(PlannerUnavailable) as refused:
        draft_files(ws, ws.router())
    assert 'refused a whole-file replacement of motion.mjs' in str(refused.value) and 'never write the whole file' in str(refused.value)
    assert refused.value.feedback['path'] == 'motion.mjs' and refused.value.feedback['shown_ranges'] == parts_of(context)['ranges']
    assert settled_state(refused.value) == 'failed'
    # also with edits and content together
    with pytest.raises(PlannerUnavailable, match='no content field'):
        from runesmith.app.planner import admit_answer_files
        admit_answer_files(ws, context, [{'path': 'motion.mjs', 'content': 'x', 'edits': [{'old_text': CAMERA, 'new_text': CAMERA_NEW}]}])


def test_an_old_text_that_occurs_more_than_once_in_the_file_is_refused(tmp_path):
    ws, text = project(tmp_path)
    assert text.count('        break;') == 2                          # both inside the shown function, still not unique
    scripted(ws, [answer(('        break;', '        break; // done'))], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='exactly once'):
        draft_files(ws, ws.router())


def test_the_same_edit_given_for_each_place_replaces_them_all_when_all_are_shown(tmp_path):
    ws, text = project(tmp_path)
    edit = ('        break;', '        break; // done')
    scripted(ws, [answer(edit, edit, (CAMERA, CAMERA_NEW))], roles=('plan',))
    draft = draft_files(ws, ws.router())
    assert draft['files'][0]['content'] == text.replace(*edit).replace(CAMERA, CAMERA_NEW)


def test_the_same_edit_for_places_the_model_was_not_shown_is_refused(tmp_path):
    ws, text = project(tmp_path)
    i = outside_function(text, source_context(ws, milestone=milestone(ws)))
    for n in (0, i):                                  # the same line in an early function (shown) and in one never shown
        text = text.replace(f'  return value{n} + {n};', '  return REPEATED;')
    (tmp_path / 'motion.mjs').write_bytes(text.encode())
    context = source_context(ws, milestone=milestone(ws))
    assert covered(parts_of(context), line_of(text, 'return REPEATED;')) and text.count('return REPEATED;') == 2
    edit = ('  return REPEATED;', '  return 0;')
    scripted(ws, [answer(edit, edit)], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='which the model was not shown'):
        draft_files(ws, ws.router())


def test_edits_in_a_row_move_the_shown_lines_with_them(tmp_path):
    ws, text = project(tmp_path)
    grown = CAMERA_NEW + '\n  const extra = camera.length;\n  const more = extra + 1;'
    scripted(ws, [answer((CAMERA, grown), ('  const more = extra + 1;', '  const more = extra + 2;'),
                         (RETURN, '  return out + String(more);'))], roles=('plan',))
    draft = draft_files(ws, ws.router())
    assert draft['files'][0]['content'] == text.replace(CAMERA, CAMERA_NEW + '\n  const extra = camera.length;\n  const more = extra + 2;') \
        .replace(RETURN, '  return out + String(more);')


def test_a_repaired_indentation_is_forgiven_only_where_the_file_was_shown(tmp_path):
    one, two = tmp_path / 'one', tmp_path / 'two'
    one.mkdir(), two.mkdir()
    ws, text = project(one)
    scripted(ws, [answer(('    const camera = project.camera || [];', '    const camera = [];'))], roles=('plan',))
    draft = draft_files(ws, ws.router())                                  # 4 spaces for the file's 2: shifted, inside a part
    assert draft['files'][0]['content'] == text.replace(CAMERA, '  const camera = [];')
    ws2, text2 = project(two)
    old, new, i = an_outside_edit(text2, source_context(ws2, milestone=milestone(ws2)))
    scripted(ws2, [answer(('    ' + old[2:], '    ' + new[2:]))], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='which the model was not shown'):
        draft_files(ws2, ws2.router())


def test_the_lines_a_refusal_asked_for_are_shown_to_the_next_call(tmp_path):
    ws, text = project(tmp_path)
    old, new, i = an_outside_edit(text, source_context(ws, milestone=milestone(ws)))
    line = line_of(text, f'const value{i} =')
    assert not covered(parts_of(source_context(ws, milestone=milestone(ws))), line)
    scripted(ws, [answer((old, new)), answer((old, new))], roles=('plan',))
    router = ws.router()
    with pytest.raises(PlannerUnavailable):
        build_step(ws, router, author_only=True)
    context = source_context(ws, milestone=milestone(ws))                    # the next call: the refused lines are shown
    assert covered(parts_of(context), line) and covered(parts_of(context), line + 1)
    draft = ws._draft(build_step(ws, router, author_only=True)['draft'])
    assert draft['files'][0]['content'] == text.replace(old, new) and tries_used(ws) == 2


# ----------------------------------------------------------------- judged by its own call --

def prepared(ws, key='original-call'):
    snapshot = collect_snapshot(ws)
    freeze_snapshot(ws, snapshot)
    context = source_context(ws, snapshot=snapshot, milestone=milestone(ws))
    packet = prepare_packet(ws, key, milestone=milestone(ws), context=context, contract=milestone_contract(ws, milestone(ws)),
                            public_digest=expectation_digest(ws, 'm1'), exposure='unused.json')
    return context, packet


def test_a_late_answer_is_judged_against_the_lines_recorded_for_its_own_call(tmp_path):
    ws, text = project(tmp_path)
    context, packet = prepared(ws, 'first-call')
    _, second = prepared(ws, 'second-call')                      # the same view, for a second late answer
    assert packet['excerpts']['motion.mjs']['ranges'] == parts_of(context)['ranges'] and 'text' not in packet['excerpts']['motion.mjs']
    old, new, i = an_outside_edit(text, context)
    line = line_of(text, f'const value{i} =')
    # since then a refusal asked for those lines, so today's selection shows them
    _write_json(ws.home / 'build-attempts' / ('b' * 32 + '.json'), {
        'state': 'failed', 'utc': '2026-10-02T06:00:00Z', 'contract': packet['contract'], 'snapshot_digest': packet['snapshot_digest'],
        'feedback': {'path': 'motion.mjs', 'requested_old_text': old}})
    assert covered(parts_of(source_context(ws, milestone=milestone(ws))), line)
    with pytest.raises(PlannerUnavailable, match='which the model was not shown'):
        admit_packet(ws, packet, answer((old, new)), 'late-author')
    draft = admit_packet(ws, second, answer((CAMERA, CAMERA_NEW), title='Inside'), 'late-author')
    assert draft['files'][0]['content'] == text.replace(CAMERA, CAMERA_NEW)
    assert draft['shown_excerpts'] == packet['excerpts'] and draft['context_digest'] == context['digest']


def test_a_late_answer_whose_file_changed_since_cannot_be_admitted(tmp_path):
    ws, text = project(tmp_path)
    context, packet = prepared(ws)
    (tmp_path / 'motion.mjs').write_bytes((text + '// grown\n').encode())
    with pytest.raises(Exception, match='changed'):
        admit_packet(ws, packet, answer((CAMERA, CAMERA_NEW)), 'late-author')


def refused_first(tmp_path):
    """A build whose first answer quotes lines the model was not shown: failed, with the refusal kept."""
    ws, text = project(tmp_path)
    old, new, i = an_outside_edit(text, source_context(ws, milestone=milestone(ws)))
    scripted(ws, [answer((old, new), title='Outside')], roles=('plan',))
    with pytest.raises(PlannerUnavailable):
        build_step(ws, ws.router())
    attempt = correction_candidates(ws)[0]['attempt']
    return ws, text, old, new, i, attempt


def test_a_correction_is_judged_against_the_lines_its_own_call_was_shown(tmp_path):
    ws, text, old, new, i, attempt = refused_first(tmp_path)
    line = line_of(text, f'const value{i} =')
    scripted(ws, [{'title': 'Fixed', 'why': 'now shown', 'files': [{'path': 'motion.mjs', 'edits': [{'old_text': old, 'new_text': new}]}]}],
             roles=('plan',))
    router = ws.router()
    seen = []
    real = router.call
    router.call = lambda *args, **kwargs: (seen.append(json.loads(kwargs['prompt'])), real(*args, **kwargs))[1]
    draft = correct_rejected_answer(ws, router, attempt)
    packet = seen[0]
    assert old in packet['current_source']['motion.mjs'] and 'shown in parts' in packet['current_source']['motion.mjs']
    assert draft['files'][0]['content'] == text.replace(old, new)             # the correction's own call showed the lines
    assert draft['shown_excerpts']['motion.mjs']['ranges'] != []
    assert any(a <= line <= b for a, b in draft['shown_excerpts']['motion.mjs']['ranges'])
    receipt = json.loads(next((ws.home / 'build-corrections').glob('*.json')).read_text())
    assert receipt['excerpts']['motion.mjs']['ranges'] == draft['shown_excerpts']['motion.mjs']['ranges']
    # a correction that quotes other lines it was not shown is refused again
    ws2, text2, old2, new2, i2, attempt2 = refused_first(tmp_path / 'second') if (tmp_path / 'second').mkdir() is None else None
    other, other_new, j = an_outside_edit(text2, source_context(ws2, milestone=milestone(ws2)))
    scripted(ws2, [{'title': 'Wrong', 'why': 'x', 'files': [{'path': 'motion.mjs', 'edits': [{'old_text': other, 'new_text': other_new}]}]}],
             roles=('plan',))
    if j != i2:
        with pytest.raises(PlannerUnavailable, match='which the model was not shown'):
            correct_rejected_answer(ws2, ws2.router(), attempt2)


def test_a_kept_answer_is_checked_again_against_the_lines_its_own_call_was_shown(tmp_path):
    ws, text, old, new, i, attempt = refused_first(tmp_path)
    line = line_of(text, f'const value{i} =')
    assert covered(parts_of(source_context(ws, milestone=milestone(ws))), line)       # today the lines would be shown
    with pytest.raises(PlannerUnavailable, match='still does not fit'):
        readmit_refused_answer(ws, attempt)                                           # but the answer was made without them
    assert correction_candidates(ws)[0]['can_check_again']


# -------------------------------------------------------------------------- revisions --

def test_a_revision_candidate_too_large_to_show_whole_is_shown_by_what_it_changed(tmp_path):
    ws, text = project(tmp_path)
    scripted(ws, [answer((CAMERA, CAMERA_NEW), title='First')], roles=('plan',))
    first = draft_files(ws, ws.router())
    ws._save_draft_state(ws._draft(first['id']), 'needs_revision')
    candidate = first['files'][0]['content']
    assert len(candidate) > 40000
    prompt = json.loads(draft_prompt(ws, milestone(ws), source_context(ws, milestone=milestone(ws))))['candidate_to_revise']
    shown = prompt['excerpts']['motion.mjs']
    assert prompt['files'] == [] and prompt['omitted'] == [] and CAMERA_NEW in shown['text']      # the lines it changed
    # edit what the candidate wrote, and something else inside its shown lines: the candidate's change is preserved
    scripted(ws, [answer((CAMERA_NEW, CAMERA_NEW + ' // fixed'), (RETURN, '  return out;'), title='Second')], roles=('plan',))
    second = draft_files(ws, ws.router())
    assert second['files'][0]['content'] == candidate.replace(CAMERA_NEW, CAMERA_NEW + ' // fixed').replace(RETURN, '  return out;')
    assert second['files'][0]['revision_base'] == 'candidate' and second['files'][0]['base'] == text
    packet = json.loads((ws.home / 'build-author-packets' / (second['author_request_key'] + '.json')).read_text())['packet']
    assert packet['candidate_view']['motion.mjs']['shown'] == 'parts' and packet['candidate_view']['motion.mjs']['ranges']


def test_an_edit_to_a_candidate_outside_the_lines_it_was_shown_in_is_refused(tmp_path):
    ws, text = project(tmp_path)
    scripted(ws, [answer((CAMERA, CAMERA_NEW), title='First')], roles=('plan',))
    first = draft_files(ws, ws.router())
    ws._save_draft_state(ws._draft(first['id']), 'needs_revision')
    context = source_context(ws, milestone=milestone(ws))
    old, new, i = an_outside_edit(text, context)
    scripted(ws, [answer((old, new), title='Second')], roles=('plan',))
    with pytest.raises(PlannerUnavailable, match='which the model was not shown'):
        draft_files(ws, ws.router())


# -------------------------------------------------------------------- what is recorded --

def test_the_retained_view_is_checked_with_its_parts_and_old_receipts_without_them_keep_working(tmp_path):
    ws, text = project(tmp_path)
    scripted(ws, [answer((CAMERA, CAMERA_NEW))], roles=('plan',))
    draft = draft_files(ws, ws.router())
    snapshot = collect_snapshot(ws)
    status = author_context_status(ws, draft, snapshot)
    assert status['ok'] and status['binding'] == 'frozen_shown_files' and status['parts_count'] == 1
    verification = verify_draft(ws, draft)
    assert verification['status'] != 'stale' and verification['author_context']['ok']
    tampered = dict(draft, shown_excerpts={'motion.mjs': dict(draft['shown_excerpts']['motion.mjs'], ranges=[[1, 2]])})
    assert not author_context_status(ws, tampered, snapshot)['ok']              # the lines are part of the digest
    changed = dict(draft, shown_excerpts={'motion.mjs': dict(draft['shown_excerpts']['motion.mjs'], sha256='0' * 64)})
    assert not author_context_status(ws, changed, snapshot)['ok']
    old = {k: v for k, v in draft.items() if k != 'shown_excerpts'}              # a receipt from before parts
    assert not author_context_status(ws, old, snapshot)['ok']                   # its digest covers parts it does not name
    small = plan_for(tmp_path / 'small') if (tmp_path / 'small').mkdir() is None else None
    (tmp_path / 'small' / 'a.py').write_text('x = 1\n')
    scripted(small, [{'title': 'x', 'files': [{'path': 'b.py', 'content': 'y = 2\n'}]}], roles=('plan',))
    plain = draft_files(small, small.router())
    assert 'shown_excerpts' not in plain and author_context_status(small, plain, collect_snapshot(small))['ok']


def test_a_file_with_windows_line_ends_is_edited_in_parts_and_rebuilt_with_its_own_line_ends(tmp_path):
    from runesmith.app.building import _candidate_files
    ws = plan_for(tmp_path)
    text = program(tmp_path, functions=480)
    (tmp_path / 'motion.mjs').write_bytes(text.replace('\n', '\r\n').encode())
    scripted(ws, [answer((CAMERA, CAMERA_NEW))], roles=('plan',))
    draft = draft_files(ws, ws.router())
    entry = draft['files'][0]
    assert '\r' not in entry['content'] and entry['content'] == text.replace(CAMERA, CAMERA_NEW)
    assert entry['expected_sha256'] == hashlib.sha256((tmp_path / 'motion.mjs').read_bytes()).hexdigest()
    rebuilt = _candidate_files(collect_snapshot(ws), draft)['motion.mjs']
    assert rebuilt == text.replace(CAMERA, CAMERA_NEW).replace('\n', '\r\n').encode()


def test_a_focused_revision_of_a_file_shown_in_parts_is_admitted_against_its_candidate(tmp_path, monkeypatch):
    # The focused revision path builds the whole file from the candidate itself (journey J11-B15): for a file shown in
    # parts that is still not a whole-file replacement by the model, and its bytes stay bound to the current file.
    from runesmith.app import building
    from runesmith.app.build_jobs import run_synchronous_build_job
    from test_author_revisions import mark_for_revision, request
    from test_build_context import planned
    ws = planned(tmp_path)
    (tmp_path / 'app.py').write_text('def target():\n    return 1\n\n' + ''.join(f'def other{i}():\n    return {i}00000\n\n' for i in range(1200)))
    assert (tmp_path / 'app.py').stat().st_size > 40000
    first = {'title': 'First', 'files': [{'path': 'app.py', 'edits': [{'old_text': 'def target():\n    return 1', 'new_text': 'def target():\n    return 2'}]}]}
    scripted(ws, [first], roles=('plan',))
    monkeypatch.setattr(building, '_check_and_record', lambda ws, draft, *a, **kw: {'draft': draft['id']})
    draft = ws._draft(building.build_step(ws, ws.router())['draft'])
    assert 'app.py' in draft['shown_excerpts'] and 'app.py' not in draft['shown_files']
    mark_for_revision(ws, draft)
    scripted(ws, [{'title': 'Focused', 'files': [{'path': 'app.py', 'edits': [
        {'old_text': 'def target():\n    return 2', 'new_text': 'def target():\n    return 3'}]}]}], roles=('plan',))
    outcome = run_synchronous_build_job(ws.root, request(ws, draft['id']), home=ws.home)
    assert outcome['result'] == 'done', json.dumps(outcome.get('outcome'), default=str)[:1500]
    revised = ws._draft(outcome['outcome']['draft'])
    content = revised['files'][0]['content']
    assert 'def target():\n    return 3' in content and 'def other1199():\n    return 119900000' in content
    assert revised['files'][0]['base'].startswith('def target():\n    return 1') and revised['files'][0]['expected_sha256']
    assert 'app.py' in revised['shown_excerpts'] and revised['shown_files'] == []


def test_a_waiting_draft_made_from_parts_is_reused_and_the_model_is_not_asked_again(tmp_path):
    # The view a milestone is built from depends on its own words, so the schedule compares a waiting draft with that view.
    ws, text = project(tmp_path)
    scripted(ws, [answer((CAMERA, CAMERA_NEW))] * 3, roles=('plan',))
    router = ws.router()
    calls = []
    real = router.call
    router.call = lambda *args, **kwargs: (calls.append(1), real(*args, **kwargs))[1]
    first = build_step(ws, router, author_only=True)
    assert first['draft'] and len(calls) == 1
    second = build_step(ws, router)                                  # checks it (no model call), as it waits
    assert second['draft'] == first['draft'] and len(calls) == 1 and tries_used(ws) == 1
