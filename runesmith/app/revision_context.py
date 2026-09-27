"""Opt-in, candidate-bound revision views; not new author/check authority.

The host keeps complete source/candidate bindings. Only displayed editable units
may change, and omitted candidate bytes are carried forward, never regenerated.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json

from runesmith.canon import digest
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

MAX_UNITS = 12
MAX_CODE_CHARS = 24000


def candidate_identity(revision):
    return digest({**{k: revision.get(k) for k in ('id', 'contract', 'snapshot_digest')},
                   'files': [{k: f.get(k) for k in ('path', 'content', 'base', 'expected_sha256', 'expected_absent')}
                             for f in revision['files']]})


def _path(ws, draft_id):
    # Resolve through the normal draft-id validator before constructing a path.
    ws._draft(draft_id)
    return ws.home / 'revision-focus' / (draft_id + '.json')


def _units(path, content):
    lines = content.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1] + len(line))
    rows = [{'unit': '*', 'label': 'Complete file', 'start': 0, 'end': len(content)}]
    outline, imports = [], []
    if path.endswith('.py'):
        try: tree = ast.parse(content)
        except (SyntaxError, ValueError): tree = None
        if tree:
            def add(node, name):
                start = min([node.lineno] + [d.lineno for d in getattr(node, 'decorator_list', [])])
                rows.append({'unit': f'{name}@{start}', 'label': name,
                             'start': offsets[start - 1], 'end': offsets[node.end_lineno]})
                outline.append(name)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    add(node, node.name)
                    if isinstance(node, ast.ClassDef):
                        for child in node.body:
                            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                add(child, node.name + '.' + child.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.append(content[offsets[node.lineno - 1]:offsets[node.end_lineno]])
    for row in rows: row['chars'] = row['end'] - row['start']
    return rows, {'symbols': outline[:300], 'imports': ''.join(imports)[:4000]}


def make_view(ws, revision, selections):
    from runesmith.app.snapshots import path_kind
    if (not isinstance(selections, list) or not 1 <= len(selections) <= MAX_UNITS
            or any(not isinstance(s, dict) or set(s) != {'path', 'unit'}
                   or not isinstance(s['path'], str) or not isinstance(s['unit'], str) for s in selections)):
        raise WorkspaceError('Choose 1-12 distinct complete files or code units.')
    files = {f['path']: f for f in revision['files']}
    editable, maps, used = [], {}, 0
    for selection in selections:
        path = selection['path']
        if path not in files or ws._safe_rel(path) != path or path_kind(path) != 'model':
            raise WorkspaceError('Revision selection must belong to the retained candidate.')
        content = files[path]['content']
        units, outline = _units(path, content)
        unit = next((u for u in units if u['unit'] == selection['unit']), None)
        if not unit: raise WorkspaceError('Selected code unit changed or is unavailable.')
        if any(e['path'] == path and unit['start'] < e['end'] and e['start'] < unit['end'] for e in editable):
            raise WorkspaceError('Revision code units overlap; choose the file OR its functions.')
        code = content[unit['start']:unit['end']]
        used += len(code)
        if used > MAX_CODE_CHARS: raise WorkspaceError('Selected revision code exceeds 24000 characters.')
        editable.append(dict(unit, path=path, content=code))
        maps[path] = outline
    # Metadata only for other files: never silently substitute a summary for an edit base.
    retained = [{'path': f['path'], 'chars': len(f['content']),
                 'sha256': hashlib.sha256(f['content'].encode()).hexdigest()}
                for f in revision['files']]
    return {'schema': 1, 'candidate': revision['id'], 'candidate_digest': candidate_identity(revision),
            'selections': copy.deepcopy(selections), 'editable_units': editable,
            'read_only_file_maps': maps, 'retained_files': retained,
            'code_chars': used, 'code_budget_chars': MAX_CODE_CHARS,
            'scope': 'Only exact edits entirely inside editable_units. Other candidate bytes are retained unchanged. '
                     'Maps/imports are read-only orientation, not an exhaustive dependency graph or edit authority. '
                     'No new files in this profile.'}


def selected_view(ws, revision):
    path = _path(ws, revision['id'])
    if not path.exists(): return None
    settings = _read_json(path, None)
    if not isinstance(settings, dict): raise WorkspaceError('Saved revision context is damaged; inspect it in Studio.')
    if not settings.get('enabled'): return None
    if settings.get('candidate_digest') != candidate_identity(revision):
        raise WorkspaceError('Saved revision selection is stale; inspect the changed candidate.')
    return make_view(ws, revision, settings.get('selections'))


def _inspection(ws, draft_id):
    from runesmith.app.snapshots import collect_snapshot
    from runesmith.app.author_recovery import pending_authors
    from runesmith.app.planner import milestone_contract, milestone_ready
    from runesmith.app.acceptance_contracts import expectation_digest
    revision = ws._draft(draft_id)
    snapshot = collect_snapshot(ws)
    settings = _read_json(_path(ws, draft_id), None)
    version = digest({'candidate': candidate_identity(revision), 'source': snapshot['digest'], 'settings': settings})
    milestone = next((m for m in (ws.plan() or {}).get('milestones', []) if m['id'] == revision.get('milestone')), None)
    blockers = []
    if revision.get('state') != 'needs_revision': blockers.append('Draft must be explicitly marked needs_revision first.')
    if revision.get('snapshot_digest') != snapshot['digest']: blockers.append('Full source snapshot changed.')
    if not milestone or not milestone_ready(ws.plan(), milestone): blockers.append('Milestone is not ready.')
    elif revision.get('contract') != milestone_contract(ws, milestone):
        blockers.append('Milestone changed.')
    # A versioned public clarification is a legitimate input to the separately
    # authorized supplement path. Selecting context grants no author/check budget.
    try:
        if pending_authors(ws): blockers.append('Reconcile saved author requests before changing context.')
    except (AttributeError, KeyError, TypeError, ValueError):
        blockers.append('An author receipt is damaged; reconcile it first.')
    if (ws.home / 'STUDIO_CURRENT.json').exists(): blockers.append('Finish or reconcile the Studio worker first.')
    for f in revision['files']:
        if (f['path'] in snapshot['manifest'] and snapshot['manifest'][f['path']]['visibility'] != 'model'):
            blockers.append('Candidate contains a non-model-visible path.')
    return revision, snapshot, settings, version, milestone, blockers


def inspect_revision(ws, draft_id):
    revision, snapshot, settings, version, milestone, blockers = _inspection(ws, draft_id)
    rows = []
    for f in revision['files']:
        units, _ = _units(f['path'], f['content'])
        rows.extend(dict(u, path=f['path']) for u in units[:300])
    view, error, preview = None, None, None
    try: view = selected_view(ws, revision)
    except WorkspaceError as failure: error = str(failure)
    feedback = ws.planning_note_selection(milestone_id=revision.get('milestone'), draft_id=draft_id)
    blockers.extend(feedback['blockers'])
    if milestone and not blockers:
        from runesmith.app.planner import source_context, draft_prompt
        context = source_context(ws, snapshot=snapshot)
        broad = draft_prompt(ws, milestone, context, revision=revision)
        focused = draft_prompt(ws, milestone, context, revision=revision, revision_view=view) if view else None
        preview = {'broad_prompt_bytes': len(broad.encode()),
                   'focused_prompt_bytes': len(focused.encode()) if focused else None,
                   'prompt': focused, 'inference_calls': 0}
    return {'draft': draft_id, 'version': version, 'settings': settings, 'settings_error': error,
            'blockers': blockers, 'units': rows, 'view': view, 'preview': preview, 'feedback': feedback,
            'max_units': MAX_UNITS, 'code_budget_chars': MAX_CODE_CHARS,
            'scope': 'Future explicitly authorized revisions only. Saving grants no calls, retries, checks or apply. '
                     'Full source, candidate and acceptance bindings remain unchanged.'}


def save_selection(ws, draft_id, *, version, selections, reason, enabled=True):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise WorkspaceError('Give a revision context reason of 1-2000 characters.')
    if type(enabled) is not bool: raise WorkspaceError('Enabled must be boolean.')
    with ws._lock:
        revision, _, _, current, _, blockers = _inspection(ws, draft_id)
        if current != version: raise WorkspaceError('Revision context changed; inspect it again before saving.')
        if blockers: raise WorkspaceError('; '.join(blockers))
        view = make_view(ws, revision, selections) if enabled else None
        record = {'schema': 1, 'enabled': enabled, 'selections': selections if enabled else [],
                  'candidate_digest': candidate_identity(revision), 'reason': reason.strip(), 'utc': _now()}
        _write_json(_path(ws, draft_id), record)
        ws.ledger.append('author.revision_context', {'draft': draft_id, **record,
                         'view_digest': digest(view) if view else None, 'inference_calls': 0})
    return inspect_revision(ws, draft_id)


def focus_packet(packet, view):
    """Replace duplicate full source with bounded candidate units; keep all goals/feedback."""
    packet = copy.deepcopy(packet)
    source = packet['source_context']
    packet['source_context'] = {'snapshot_digest': source['snapshot_digest'],
        'binding_digest': source['digest'], 'inventory': source['inventory'],
        'scope': 'Full current files are host-bound, NOT shown here and NOT available as edit bases.'}
    candidate = packet['candidate_to_revise']
    candidate.pop('files', None)
    candidate.pop('omitted', None)
    candidate.update(view)
    packet['rules'] = [r for r in packet['rules'] if not (
        r.startswith('never replace an existing file not included') or
        r.startswith('for a new draft copy old_text') or r.startswith('use either content'))]
    packet['rules'].append(view['scope'])
    packet['rules'].append('Return edits only, never complete content. Copy old_text exactly from an editable unit. '
                           'If the fix needs omitted code, stop and request expanded context; do not invent it.')
    packet['output']['files'] = '[{path, purpose, edits:[{old_text,new_text}]}] for displayed editable units only'
    return packet


def materialize_answer(ws, revision, view, raw_files):
    """Check visibility before the existing full-file binding/admission machinery."""
    from runesmith.app.planner import PlannerUnavailable
    from runesmith.organs.repair import apply_edits
    if digest(make_view(ws, revision, view.get('selections'))) != digest(view):
        raise WorkspaceError('Retained revision view no longer matches its candidate.')
    if not isinstance(raw_files, list) or not raw_files:
        raise PlannerUnavailable('Focused revision needs exact edits to displayed code.')
    outputs, seen = [], set()
    for raw in raw_files:
        if not isinstance(raw, dict): raise PlannerUnavailable('Focused file operation is invalid.')
        path, edits = raw.get('path'), raw.get('edits')
        units = [u['content'] for u in view['editable_units'] if u['path'] == path]
        if (not units or path in seen or 'content' in raw or not isinstance(edits, list) or not 1 <= len(edits) <= 6):
            raise PlannerUnavailable('Focused revisions allow 1-6 exact edits per displayed path, no content or new paths.')
        seen.add(path)
        content = next(f['content'] for f in revision['files'] if f['path'] == path)
        try:
            for edit in edits:
                old = edit.get('old_text') if isinstance(edit, dict) else None
                if not isinstance(old, str) or not old or sum(u.count(old) for u in units) != 1:
                    raise ValueError('old_text must occur exactly once inside displayed editable code.')
                index = next(i for i, u in enumerate(units) if old in u)
                # Full-file uniqueness still applies; no fuzzy/hidden-context fallback.
                content = apply_edits({path: content}, [dict(edit, path=path)], {path})[path]
                units[index] = units[index].replace(old, edit['new_text'], 1)
        except (ValueError, TypeError, KeyError) as error:
            raise PlannerUnavailable(f'Focused exact edit refused for {path}: {error}') from error
        output = copy.deepcopy(raw)
        output.pop('edits'); output['content'] = content
        outputs.append(output)
    return outputs
