"""Bounded author-source selection and its read-only Studio inspector.

Focus changes input selection, not the verification snapshot, write authority,
acceptance criteria or a previous request's saved source binding.

A file over its cap, or one the budget cannot hold whole, is shown in parts (source_parts): an outline and exact
excerpts. The packet carries those apart from the fully shown files, so a whole-file replacement of such a file stays
refused and an edit must quote one excerpt (journey J11-B15).
"""
from __future__ import annotations

import hashlib
import json

from runesmith.app.source_parts import (MIN_PART_CHARS, build_parts, check_ranges, named_in, quotable, render_parts,
                                        split_lines)
from runesmith.app.workspace import MAX_DRAFT_FILE_BYTES, WorkspaceError, _now, _read_json, _write_json

CONTEXT_CHARS = 48000
DEFAULT_FILE_BYTES = 20000
FOCUSED_FILE_BYTES = 40000        # raised from 32000: motion.mjs reached 30,023 bytes and grows (journey J11-B15)
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
        raise WorkspaceError(f'Choose up to {MAX_FOCUS_PATHS} unique model-visible relative file paths.')


def context_digest(files, excerpts=None):
    """What a call was shown, as one digest: the whole files; and, when some were shown in parts, their ranges and
    text too. With no parts it is the digest every earlier receipt holds."""
    if not excerpts:
        return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    shown = {rel: {'ranges': part['ranges'], 'sha256': part['sha256'], 'text': part['text']}
             for rel, part in excerpts.items()}
    return hashlib.sha256(json.dumps({'files': files, 'excerpts': shown}, sort_keys=True).encode()).hexdigest()


def _context(files, hashes, snapshot, inventory, omitted, excerpts=None, **metadata):
    return {'files': files, **({'excerpts': excerpts} if excerpts else {}), 'file_hashes': hashes,
            'inventory': inventory[:2000], 'omitted': omitted, 'truncated_inventory': len(inventory) > 2000,
            'snapshot_digest': snapshot['digest'], 'digest': context_digest(files, excerpts), **metadata}


def recorded_excerpts(context):
    """The parts a call was shown, as a receipt keeps them (ranges, line count and the file's hash, not the text:
    recorded_context rebuilds the text from the file)."""
    return {rel: {'ranges': part['ranges'], 'lines': part['lines'], 'sha256': part['sha256']}
            for rel, part in (context.get('excerpts') or {}).items()}


def shown_view(context):
    """The fields a saved draft keeps of what its author was shown."""
    parts = recorded_excerpts(context)
    return {'shown_files': sorted(context['files']), **({'shown_excerpts': parts} if parts else {})}


def select_context(ws, snapshot, limit=CONTEXT_CHARS, *, focus_paths=None, include_rows=False, terms=None,
                   parts_share=1.0, parts_reserve=0, parts=True):
    """The files a model is shown, for a budget of characters: whole where they fit their cap and the budget, else in
    parts (source_parts) when the budget has room for a useful excerpt. `terms` (the milestone's words, from
    planner.milestone_terms) choose the excerpts; `parts_share` bounds how much of the budget one file's parts may take;
    `parts_reserve` holds that many characters back from the whole files when some file needs parts, so a small
    budget (the Checker's) is not all spent on small files before the program is reached; `parts=False` leaves such a file out, as a retained selection that was recorded without parts does."""
    if type(limit) is not int or not 0 <= limit <= CONTEXT_CHARS:
        raise WorkspaceError(f'Author source budget must be between 0 and {CONTEXT_CHARS} characters.')
    paths = focus_settings(ws)['paths'] if focus_paths is None else focus_paths
    _validate_paths(paths)
    terms = terms or {}
    inventory = [p for p, e in snapshot['manifest'].items() if e['visibility'] == 'model']
    visible = set(inventory)
    focus_errors = {p: 'not_model_visible' for p in paths if p not in visible}
    # Prioritized files first, then the files the milestone names or that its last refused answer asked for (the
    # `wanted` words: a gap closes itself in the next round), then the rest (journey J11-B15, review of the merged batch:
    # a named module was crowded out by the prioritized program's parts and the milestone waited for good).
    rest = [p for p in inventory[:2000] if p not in paths]
    named = {p for p in rest if named_in(terms.get('text'), p) or p in (terms.get('wanted') or ())}
    order = [p for p in paths if p in visible] + [p for p in rest if p in named] + [p for p in rest if p not in named]
    files, hashes, omitted, reasons, rows, used = {}, {}, [], {}, [], 0
    shown_parts, deferred, row_of, texts = {}, [], {}, {}
    part_cap = min(FOCUSED_FILE_BYTES, max(MIN_PART_CHARS, int(limit * parts_share)))

    def in_parts(rel, budget):
        """Why the file cannot be shown in parts (None when it was): no room for a useful excerpt, or no line short enough."""
        if len(snapshot['files'][rel]) > MAX_DRAFT_FILE_BYTES:
            return 'file_limit'             # a draft cannot hold it, so no answer to it could ever be kept (review of the merged batch)
        if len(snapshot['files'][rel]) > FOCUSED_FILE_BYTES and not quotable(texts[rel]):
            return 'file_limit'             # no line short enough to quote: no budget could ever show it
        if budget < MIN_PART_CHARS:
            return 'packet_budget'
        part = build_parts(rel, texts[rel], terms, budget)
        if part is None:
            # A file within the prioritized cap could be shown whole with more room (prioritize it); one over it, with
            # no line short enough to quote, can never be shown.
            return 'file_limit' if len(snapshot['files'][rel]) > FOCUSED_FILE_BYTES else 'packet_budget'
        shown_parts[rel] = dict(part, sha256=snapshot['manifest'][rel]['sha256'])
        return None

    def settle(rel, reason, focused):
        row = row_of[rel]
        if reason:
            omitted.append(rel); reasons[rel] = reason
            if focused:focus_errors[rel] = reason
        elif rel in shown_parts:
            part = shown_parts[rel]
            row.update(chars=part['chars'], in_parts=True, ranges=part['ranges'], lines=part['lines'])
        row.update(included=reason is None, reason=reason)
    # A file over the normal cap, up to the prioritized cap, is shown after the others when the budget has room (journey
    # J11-B15: motion.mjs grew to 20,316 bytes, was never shown again, and every build that edited it was refused).
    larger = [rel for rel in order if rel not in paths and DEFAULT_FILE_BYTES < len(snapshot['files'][rel]) <= FOCUSED_FILE_BYTES]
    caps = {rel: FOCUSED_FILE_BYTES if rel in paths or rel in larger else DEFAULT_FILE_BYTES for rel in order}
    whole_limit = limit - min(parts_reserve, limit) if parts and any(
        len(snapshot['files'][rel]) > min(caps[rel], limit) for rel in order) else limit
    # Room kept for the other files before a prioritized file's parts take the rest: the small files and the named ones,
    # at most a quarter of the budget, so a module added later is still shown whole.
    room = min(limit // 4, sum(len(snapshot['files'][rel]) for rel in rest
                               if len(snapshot['files'][rel]) <= DEFAULT_FILE_BYTES or rel in named))
    over_cap = set()
    for rel in [rel for rel in order if rel not in larger or rel in named] + [rel for rel in larger if rel not in named]:
        data = snapshot['files'][rel]
        focused = rel in paths
        cap = caps[rel]
        reason = None
        try: content = data.decode('utf-8-sig').replace('\r\n', '\n')
        except UnicodeError:content = ''; reason = 'not_utf8'
        row_of[rel] = {'path': rel, 'bytes': len(data), 'chars': len(content) if reason != 'not_utf8' else None,
                       'included': False, 'focused': focused, 'reason': reason, 'file_limit_bytes': cap}
        rows.append(row_of[rel])
        if reason is None and len(data) <= cap and used + len(content) <= (limit if focused else whole_limit):
            files[rel] = content; hashes[rel] = snapshot['manifest'][rel]['sha256']; used += len(content)
            row_of[rel].update(included=True)
            continue
        if reason is None and not parts:
            reason = 'file_limit' if len(data) > cap else 'packet_budget'
        elif reason is None:
            # Over its cap, or the budget cannot hold it whole: shown in parts instead of not at all (journey J11-B15,
            # B16). A prioritized file is shown at once, so it keeps its place at the front of the budget; the others
            # after the whole files, the ones the milestone names first.
            texts[rel] = content
            if len(data) > cap:
                over_cap.add(rel)
            if not focused:
                deferred.append(rel)
                continue
            reason = in_parts(rel, max(min(part_cap, limit - used - room), min(MIN_PART_CHARS, limit - used)))
            used += shown_parts[rel]['chars'] if rel in shown_parts else 0
        settle(rel, reason, focused)
    # The files the milestone names first, then those that can never be whole: they share what is left, and a file that
    # fits whole after all (the budget held back for them was not needed) is shown whole.
    deferred.sort(key=lambda rel: (not named_in(terms.get('text'), rel), rel not in over_cap))
    for number, rel in enumerate(deferred):
        remaining = limit - used
        if rel not in over_cap and len(texts[rel]) <= remaining:
            files[rel] = texts[rel]; hashes[rel] = snapshot['manifest'][rel]['sha256']; used += len(texts[rel])
            row_of[rel].update(included=True)
            continue
        waiting = sum(1 for later in deferred[number:] if later in over_cap) if rel in over_cap else 1
        share = remaining // max(waiting, 1)
        reason = in_parts(rel, min(part_cap, share if share >= MIN_PART_CHARS else remaining))
        used += shown_parts[rel]['chars'] if rel in shown_parts else 0
        settle(rel, reason, False)
    return _context(files, hashes, snapshot, inventory, omitted, shown_parts,
        focus_paths=list(paths), focus_errors=focus_errors, omission_reasons=reasons,
        selection={'budget_chars': limit, 'used_chars': used, 'normal_file_bytes': DEFAULT_FILE_BYTES,
                   'focused_file_bytes': FOCUSED_FILE_BYTES, 'max_focus_paths': MAX_FOCUS_PATHS,
                   **({'rows': rows} if include_rows else {})})


def _omission_reason(data, rel='', parts_era=False):
    """Why a file is not in a recorded selection, as select_context says it: not text, over the size limit, else the
    source budget. A selection recorded with parts left a file over the limit out for the budget, unless no line of it
    is short enough to show (journey J11-B15)."""
    try: content = data.decode('utf-8-sig')
    except UnicodeError:return 'not_utf8'
    if len(data) <= FOCUSED_FILE_BYTES:
        return 'packet_budget'
    if len(data) > MAX_DRAFT_FILE_BYTES:
        return 'file_limit'
    if parts_era and build_parts(rel, content.replace('\r\n', '\n'), None, FOCUSED_FILE_BYTES):
        return 'packet_budget'
    return 'file_limit'


def recorded_parts(snapshot, inventory, excerpts):
    """The parts a call was shown, rebuilt from the file and the recorded ranges; the file must be what it was."""
    shown = {}
    for rel, saved in (excerpts or {}).items():
        if (not isinstance(rel, str) or rel not in inventory or rel not in snapshot['files'] or not isinstance(saved, dict)
                or not isinstance(saved.get('sha256'), str)):
            raise WorkspaceError('Retained author excerpts are no longer model-visible.')
        data = snapshot['files'][rel]
        if snapshot['manifest'][rel]['sha256'] != saved['sha256']:
            raise WorkspaceError('A file shown in parts has changed since; its retained excerpts no longer match.')
        try:lines = split_lines(data.decode('utf-8-sig').replace('\r\n', '\n'))
        except UnicodeError as error:raise WorkspaceError('Retained author input is not UTF-8.') from error
        ranges = check_ranges(saved.get('ranges'), len(lines))
        if ranges is None:
            raise WorkspaceError('Retained author excerpt ranges are invalid.')
        text = render_parts(rel, lines, ranges)
        shown[rel] = {'ranges': ranges, 'lines': len(lines), 'sha256': saved['sha256'], 'text': text, 'chars': len(text)}
    return shown


def recorded_context(snapshot, names, excerpts=None):
    """Reconstruct a new-format host packet's original complete file selection, and the parts it was shown (a packet
    recorded with parts has an `excerpts` entry, even an empty one)."""
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
    shown = recorded_parts(snapshot, set(inventory), excerpts)
    if sum(map(len, files.values())) + sum(part['chars'] for part in shown.values()) > CONTEXT_CHARS:
        raise WorkspaceError('Retained author packet exceeds its source budget.')
    omitted = [p for p in inventory[:2000] if p not in files and p not in shown]
    # Said as select_context says it (journey J11-B15: every gap read "packet_budget" here, a file over the limit too).
    return _context(files, hashes, snapshot, inventory, omitted, shown,
                    omission_reasons={rel: _omission_reason(snapshot['files'][rel], rel, excerpts is not None)
                                      for rel in omitted})


def with_recorded_parts(context, snapshot, excerpts):
    """A selection made without parts, with the parts a recorded call was shown instead: an answer kept from that call
    is checked again against the lines its author saw, never against today's choice (journey J11-B15)."""
    inventory = {p for p, e in snapshot['manifest'].items() if e['visibility'] == 'model'}
    shown = recorded_parts(snapshot, inventory, excerpts)
    # A file its call was shown only in parts is not whole here, though today's budget would hold it (review of the merged
    # batch: the replay then took any edit to it, with no range check).
    whole = {rel: text for rel, text in context['files'].items() if rel not in shown}
    result = {k: v for k, v in context.items() if k != 'excerpts'}
    result.update(files=whole, file_hashes={rel: h for rel, h in context['file_hashes'].items() if rel in whole},
                  omitted=[rel for rel in context['omitted'] if rel not in shown],
                  omission_reasons={rel: why for rel, why in (context.get('omission_reasons') or {}).items()
                                    if rel not in shown},
                  digest=context_digest(whole, shown))
    return dict(result, excerpts=shown) if shown else result


def inspect_context(ws):
    from runesmith.app.snapshots import collect_snapshot
    snapshot = collect_snapshot(ws)
    error = None
    try: settings = focus_settings(ws)
    except WorkspaceError as failure:
        settings = {'paths': [], 'reason': '', 'utc': None}; error = str(failure)
    # The parts a file over its limit is shown in depend on what a step is about: the drawer shows them for the next
    # step to build (journey J11-B15).
    from runesmith.app.planner import milestone_terms, next_milestone
    milestone = next_milestone(ws.plan())
    context = select_context(ws, snapshot, focus_paths=settings['paths'], include_rows=True,
                             terms=milestone_terms(ws, milestone) if milestone else None)
    return {'snapshot_digest': snapshot['digest'], 'context_digest': context['digest'],
            'focus': settings, 'focus_errors': context['focus_errors'], 'settings_error': error,
            'included_count': len(context['files']) + len(context.get('excerpts') or {}),
            'whole_count': len(context['files']), 'parts_count': len(context.get('excerpts') or {}),
            'parts_for': {'id': milestone['id'], 'title': milestone.get('title')} if milestone else None,
            'omitted_count': len(context['omitted']),
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
            raise WorkspaceError(f'Focus files must be model-visible UTF-8 and fit the {CONTEXT_CHARS} character source budget (a file over {FOCUSED_FILE_BYTES} bytes is shown in parts, at least {MIN_PART_CHARS} characters of it): '
                                 + ', '.join(f'{p}: {why}' for p, why in context['focus_errors'].items()))
        receipt = {'schema': 1, 'paths': list(paths), 'reason': reason.strip()[:1200], 'utc': _now(),
                   'snapshot_at_selection': snapshot_digest, 'scope': 'Input selection only; fresh source is bound for each request.'}
        _write_json(ws.home / 'AUTHOR_FOCUS.json', receipt)
        ws.ledger.append('author.context_focus', receipt)
    return inspect_context(ws)
