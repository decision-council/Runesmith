"""Bounded author-source selection and its read-only Studio inspector.

Focus changes input selection, not the verification snapshot, write authority,
acceptance criteria or a previous request's saved source binding.
"""
from __future__ import annotations

import hashlib
import json

from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

CONTEXT_CHARS = 48000
DEFAULT_FILE_BYTES = 20000
FOCUSED_FILE_BYTES = 32000
MAX_FOCUS_PATHS = 12


def focus_settings(ws):
    path = ws.home / 'AUTHOR_FOCUS.json'
    if not path.exists():return {'paths': [], 'reason': '', 'utc': None}
    value = _read_json(path, None)
    if not isinstance(value, dict):raise WorkspaceError('Author context focus is damaged; review or clear it in Studio.')
    _validate_paths(value.get('paths'))
    return value


def _validate_paths(paths):
    if (not isinstance(paths, list) or len(paths) > MAX_FOCUS_PATHS or
            any(not isinstance(p, str) or not p or len(p) > 240 for p in paths) or
            len(set(paths)) != len(paths)):
        raise WorkspaceError('Choose up to12 unique model-visible relative file paths.')


def _context(files, hashes, snapshot, inventory, omitted, **metadata):
    return {'files': files, 'file_hashes': hashes, 'inventory': inventory[:2000],
            'omitted': omitted, 'truncated_inventory': len(inventory) > 2000,
            'snapshot_digest': snapshot['digest'],
            'digest': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), **metadata}


def select_context(ws, snapshot, limit=CONTEXT_CHARS, *, focus_paths=None, include_rows=False):
    if type(limit) is not int or not 0 <= limit <= CONTEXT_CHARS:
        raise WorkspaceError('Author source budget must be between0 and48000 characters.')
    paths = focus_settings(ws)['paths'] if focus_paths is None else focus_paths
    _validate_paths(paths)
    inventory = [p for p, e in snapshot['manifest'].items() if e['visibility'] == 'model']
    visible = set(inventory)
    focus_errors = {p: 'not_model_visible' for p in paths if p not in visible}
    order = [p for p in paths if p in visible] + [p for p in inventory[:2000] if p not in paths]
    files, hashes, omitted, reasons, rows, used = {}, {}, [], {}, [], 0
    for rel in order:
        data = snapshot['files'][rel]
        focused = rel in paths
        cap = FOCUSED_FILE_BYTES if focused else DEFAULT_FILE_BYTES
        reason = None
        try: content = data.decode('utf-8-sig').replace('\r\n', '\n')
        except UnicodeError:content = ''; reason = 'not_utf8'
        if reason is None and len(data) > cap:reason = 'file_limit'
        if reason is None and used + len(content) > limit:reason = 'packet_budget'
        if reason:
            omitted.append(rel); reasons[rel] = reason
            if focused:focus_errors[rel] = reason
        else:
            files[rel] = content; hashes[rel] = snapshot['manifest'][rel]['sha256']; used += len(content)
        rows.append({'path': rel, 'bytes': len(data), 'chars': len(content) if reason != 'not_utf8' else None,
                     'included': reason is None, 'focused': focused, 'reason': reason, 'file_limit_bytes': cap})
    return _context(files, hashes, snapshot, inventory, omitted,
        focus_paths=list(paths), focus_errors=focus_errors, omission_reasons=reasons,
        selection={'budget_chars': limit, 'used_chars': used, 'normal_file_bytes': DEFAULT_FILE_BYTES,
                   'focused_file_bytes': FOCUSED_FILE_BYTES, 'max_focus_paths': MAX_FOCUS_PATHS,
                   **({'rows': rows} if include_rows else {})})


def recorded_context(snapshot, names):
    """Reconstruct a new-format host packet's original complete file selection."""
    if (not isinstance(names, list) or len(names) > 2000 or
            any(not isinstance(p, str) for p in names) or len(set(names)) != len(names)):
        raise WorkspaceError('Retained author selection is invalid.')
    inventory = [p for p, e in snapshot['manifest'].items() if e['visibility'] == 'model']
    files, hashes = {}, {}
    for rel in names:
        if rel not in inventory or rel not in snapshot['files']:
            raise WorkspaceError('Retained author selection is no longer model-visible.')
        data = snapshot['files'][rel]
        if len(data) > FOCUSED_FILE_BYTES:raise WorkspaceError('Retained author file exceeds its bounded profile.')
        try:files[rel] = data.decode('utf-8-sig').replace('\r\n', '\n')
        except UnicodeError as error:raise WorkspaceError('Retained author input is not UTF-8.') from error
        hashes[rel] = snapshot['manifest'][rel]['sha256']
    if sum(map(len, files.values())) > CONTEXT_CHARS:raise WorkspaceError('Retained author packet exceeds its source budget.')
    return _context(files, hashes, snapshot, inventory, [p for p in inventory[:2000] if p not in files])


def inspect_context(ws):
    from runesmith.app.snapshots import collect_snapshot
    snapshot = collect_snapshot(ws)
    error = None
    try: settings = focus_settings(ws)
    except WorkspaceError as failure:
        settings = {'paths': [], 'reason': '', 'utc': None}; error = str(failure)
    context = select_context(ws, snapshot, focus_paths=settings['paths'], include_rows=True)
    return {'snapshot_digest': snapshot['digest'], 'context_digest': context['digest'],
            'focus': settings, 'focus_errors': context['focus_errors'], 'settings_error': error,
            'included_count': len(context['files']), 'omitted_count': len(context['omitted']),
            'truncated_inventory': context['truncated_inventory'], **context['selection'],
            'scope': 'Source selection only. No inference, source writes, permission changes or verification credit.'}


def save_focus(ws, paths, snapshot_digest, reason):
    from runesmith.app.snapshots import collect_snapshot
    _validate_paths(paths)
    if not isinstance(reason, str) or not reason.strip():raise WorkspaceError('Explain this author-context selection.')
    with ws._lock:
        snapshot = collect_snapshot(ws)
        if snapshot['digest'] != snapshot_digest:raise WorkspaceError('Source changed; inspect the current context before saving.')
        context = select_context(ws, snapshot, focus_paths=paths)
        if context['focus_errors']:
            raise WorkspaceError('Focus files must be model-visible UTF-8, at most32000bytes each, and fit the48000character source budget: '
                                 + ', '.join(f'{p}: {why}' for p, why in context['focus_errors'].items()))
        receipt = {'schema': 1, 'paths': list(paths), 'reason': reason.strip()[:1200], 'utc': _now(),
                   'snapshot_at_selection': snapshot_digest, 'scope': 'Input selection only; fresh source is bound for each request.'}
        _write_json(ws.home / 'AUTHOR_FOCUS.json', receipt)
        ws.ledger.append('author.context_focus', receipt)
    return inspect_context(ws)
