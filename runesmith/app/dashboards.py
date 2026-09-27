"""Read-only cross-project receipt dashboards. Never instantiate another Workspace.

Registering a folder adds a view, not a worker, source writer, probe or connector.
The registry belongs to the current home; tracked homes are read-only even if a
different Studio is operating them. Each read is bounded and not an atomic snapshot.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from runesmith.canon import digest
from runesmith.app.workspace import WorkspaceError, _write_json, _now

SCHEMA = 'runesmith.dashboards.v1'
PANELS = ('progress', 'modes', 'measurements', 'activity', 'inference')
MAX_READ = 4_000_000


def _local_path(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise WorkspaceError('Use an absolute local folder path.')
    path = Path(value)
    if not path.is_absolute() or value.startswith(('\\\\', '//')) or '..' in path.parts:
        raise WorkspaceError('Use an absolute local path, not a network path or parent traversal.')
    for part in [*reversed(path.parents), path]:
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise WorkspaceError('Dashboard paths may not follow links or junctions.')
    return path


def _read(home, rel, default, errors):
    try:
        path = _local_path(str(Path(home) / rel))
        if not path.exists(): return default
        with path.open('rb') as stream: raw = stream.read(MAX_READ + 1)
        if len(raw) > MAX_READ: raise ValueError('oversized receipt')
        def unique_keys(pairs):
            value = {}
            for key, item in pairs:
                if key in value: raise ValueError('duplicate receipt field')
                value[key] = item
            return value
        return json.loads(raw, object_pairs_hook=unique_keys,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, ValueError, WorkspaceError):
        errors.append(f'{rel}: unavailable, linked, oversized or malformed; not treated as success.')
        return default


def _current(ws):
    return {'id': 'current', 'name': ws.root.name or str(ws.root), 'root': str(ws.root),
            'home': str(ws.home), 'panels': list(PANELS)}


def configuration(ws):
    path = ws.home / 'DASHBOARDS.json'
    errors = []
    body = _read(ws.home, 'DASHBOARDS.json', None, errors)
    if errors or (path.exists() and body is None):
        raise WorkspaceError('Dashboard registry unreadable; preserve it and repair explicitly.')
    body = body if body is not None else {'schema': SCHEMA, 'projects': [_current(ws)]}
    if (not isinstance(body, dict) or body.get('schema') != SCHEMA
            or not isinstance(body.get('projects'), list)):
        raise WorkspaceError('Dashboard registry schema is invalid.')
    seen = set()
    for row in body['projects']:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', row['id']) or row['id'] in seen
                or not isinstance(row.get('name'), str) or not row['name'].strip() or len(row['name']) > 100
                or not isinstance(row.get('root'), str) or not isinstance(row.get('home'), str)
                or not isinstance(row.get('panels'), list) or any(p not in PANELS for p in row['panels'])
                or len(set(row['panels'])) != len(row['panels'])):
            raise WorkspaceError('Dashboard project settings are malformed.')
        seen.add(row['id'])
    if 'current' not in seen: raise WorkspaceError('The current-project dashboard is required.')
    current = next(p for p in body['projects'] if p['id'] == 'current')
    if current['root'] != str(ws.root) or current['home'] != str(ws.home):
        raise WorkspaceError('Dashboard registry belongs to another workspace; do not silently retarget it.')
    return dict(body, revision=digest(body))


def change(ws, *, revision, action, project=None, project_id=None, panels=None):
    with ws._lock:
        config = configuration(ws)
        if config['revision'] != revision: raise WorkspaceError('Dashboards changed; reload before saving.')
        rows = list(config['projects'])
        if action == 'add':
            if not isinstance(project, dict): raise WorkspaceError('Project details are required.')
            name = project.get('name', '')
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise WorkspaceError('Give the dashboard a name of 1-100 characters.')
            root = _local_path(project.get('root'))
            home = _local_path(project.get('home') or str(root / '.runesmith'))
            if not root.is_dir(): raise WorkspaceError('Project folder does not exist.')
            if home.exists() and not home.is_dir(): raise WorkspaceError('Runesmith home must be a folder.')
            key = lambda p: os.path.normcase(os.path.abspath(p))
            if any(key(r['root']) == key(str(root)) or key(r['home']) == key(str(home)) for r in rows):
                raise WorkspaceError('This project or home is already tracked.')
            project_id = digest({'root': key(str(root)), 'home': key(str(home))}).split(':')[-1][:16]
            rows.append({'id': project_id, 'name': name.strip(), 'root': str(root), 'home': str(home), 'panels': list(PANELS)})
        elif action == 'remove':
            if project_id == 'current': raise WorkspaceError('The current project stays available; its panels can be hidden.')
            if not any(r['id'] == project_id for r in rows): raise WorkspaceError('Unknown project dashboard.')
            rows = [r for r in rows if r['id'] != project_id]
        elif action == 'panels':
            if not any(r['id'] == project_id for r in rows): raise WorkspaceError('Unknown project dashboard.')
            if (not isinstance(panels, list) or any(p not in PANELS for p in panels)
                    or len(set(panels)) != len(panels)):
                raise WorkspaceError('Choose supported dashboard panels without duplicates.')
            rows = [dict(r, panels=panels) if r['id'] == project_id else r for r in rows]
        else: raise WorkspaceError('Unknown dashboard action.')
        _write_json(ws.home / 'DASHBOARDS.json', {'schema': SCHEMA, 'projects': rows})
        ws.ledger.append('dashboard.configured', {'action': action, 'project': project_id, 'scope': 'view only'})
    return configuration(ws)


def snapshot(project):
    result = dict(project, observed_at=_now(), errors=[], available=False)
    errors = result['errors']
    try:
        root, home = _local_path(project['root']), _local_path(project['home'])
        if not root.is_dir() or not home.is_dir():
            result['detail'] = 'Project or Runesmith home unavailable / not initialized. No worker was started.'
            return result
    except WorkspaceError as error:
        result['detail'] = str(error); return result
    read = lambda rel, default=None: _read(home, rel, default, errors)
    def shaped(rel, expected, default):
        value = read(rel, default)
        if not isinstance(value, expected):
            errors.append(f'{rel}: wrong shape; observation is unknown.')
            return default
        return value
    result['available'] = True
    # Never return instrument configuration, keys, raw report rows, test output,
    # arbitrary stored packets or source code.
    plan = shaped('PLAN.json', dict, {})
    goals = shaped('GOALS.json', list, [])
    milestones = [m for m in plan.get('milestones', []) if isinstance(m, dict)] if isinstance(plan.get('milestones', []), list) else []
    result['progress'] = {'plan_at': plan.get('utc'), 'plan_author': plan.get('drafted_by'),
        'milestones': dict(Counter(m.get('status', 'unknown') for m in milestones)), 'milestone_total': len(milestones),
        'goals': dict(Counter(g.get('status', 'unknown') for g in goals if isinstance(g, dict))),
        'scope': 'Recorded milestone states, not independent acceptance or business impact.'}
    build = shaped('BUILD_LAST.json', dict, {})
    verification = build.get('verification') if isinstance(build.get('verification'), dict) else {}
    result['build'] = {'draft': build.get('draft'), 'milestone': build.get('milestone'),
        'verification': verification.get('status', 'unknown'), 'applied': build.get('applied'),
        'summary': str(build.get('summary') or '')[:500],
        'scope': 'Last retained build receipt; not necessarily the latest draft or current source.'}
    mode_config = shaped('WORK_MODES.json', dict, {})
    valid_modes = mode_config.get('schema') in ('runesmith.work-modes.v1', 'runesmith.work-modes.v2')
    if mode_config and not valid_modes:
        errors.append('WORK_MODES.json: unknown schema; effective mode status is not inferred.')
    modes = mode_config.get('modes') if valid_modes and isinstance(mode_config.get('modes'), list) else []
    result['modes'] = []
    for m in modes:
        if not isinstance(m, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', str(m.get('id', ''))):
            errors.append('Invalid recorded mode; its status is unknown.'); continue
        last = shaped('mode-latest/' + m['id'] + '.json', dict, {})
        answer = last.get('result') if isinstance(last.get('result'), dict) else {}
        result['modes'].append({'id': m['id'], 'name': str(m.get('name', m['id']))[:120],
            'executor': m.get('executor'), 'enabled': m.get('enabled') if type(m.get('enabled')) is bool else None,
            'utc': last.get('utc'), 'summary': str(answer.get('summary') or '')[:400]})
    result['modes_configured'] = bool(mode_config)
    definitions = shaped('MEASUREMENTS.json', dict, {})
    items = definitions.get('items') if isinstance(definitions.get('items'), list) else []
    result['measurements'] = []
    from runesmith.app.measurements import assess
    for item in items[:32]:
        if not isinstance(item, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', str(item.get('id', ''))):
            errors.append('Invalid measurement definition; no external fetch attempted.'); continue
        pointer = shaped('measurement-latest/' + item['id'] + '.json', dict, {})
        rid = pointer.get('receipt')
        receipt = shaped('measurement-receipts/' + rid + '.json', dict, {}) if isinstance(rid, str) and re.fullmatch('[a-f0-9]{64}', rid) else {}
        if receipt and (receipt.get('id', rid) != rid or receipt.get('measurement_id', item['id']) != item['id']):
            errors.append('Measurement receipt identity does not match its pointer; result is unknown.')
            receipt = {}
        source = shaped('measurement-inputs/' + item['id'] + '.json', dict, {}) if item.get('source_kind') in {'paste_csv', 'paste_json'} else {}
        assessment = assess(item, receipt, pasted_sha=source.get('sha256'))
        current = receipt.get('definition_digest') == digest(item) if receipt else None
        metric = {k: item.get(k) for k in ('id', 'name', 'goal', 'unit', 'source_kind', 'enabled', 'source_label')}
        if receipt:
            metric['unit'] = receipt.get('unit')  # Never relabel history with an edited definition's unit.
        metric.update({k: receipt.get(k) for k in ('value', 'measured_at', 'latest_data_at', 'threshold_met', 'source_sha256')})
        metric.update(status=receipt.get('status', 'unknown'), current_definition=current, receipt=rid,
            connector='local report' if item.get('source_kind') in ('csv', 'json', 'paste_csv', 'paste_json') else 'unavailable',
            assessment=assessment, freshness=assessment['detail'] + ' Dashboard refresh does not remeasure.')
        result['measurements'].append(metric)
    jobs = shaped('STUDIO_JOBS.json', list, [])
    result['activity'] = []
    for job in list(reversed(jobs))[:20]:
        if not isinstance(job, dict): continue
        outcome = job.get('outcome') if isinstance(job.get('outcome'), dict) else {}
        result['activity'].append({**{k: job.get(k) for k in ('id', 'kind', 'started', 'finished', 'result', 'seconds')},
                                  'summary': str(outcome.get('summary') or outcome.get('error') or '')[:500]})
    inflight = shaped('STUDIO_CURRENT.json', dict, {})
    result['recorded_inflight'] = {k: inflight.get(k) for k in ('id', 'kind', 'started')} if inflight else None
    ops = shaped('OPERATIONS.json', dict, {})
    instruments = ops.get('instruments') if isinstance(ops.get('instruments'), dict) else {}
    result['inference'] = [{'instrument': str(name)[:100], **{k: row.get(k) for k in
        ('model', 'calls', 'ok', 'errors', 'costed_calls', 'estimated_usd', 'last_utc')}}
        for name, row in list(instruments.items())[:50] if isinstance(row, dict)]
    from runesmith.app.inference_accounting import accounting_view
    result['gateway_accounting'] = accounting_view(home)
    result['scope'] = 'Read-only local receipts, not an atomic snapshot or a liveness check. No automatic fetch, call, check or apply.'
    return result


def view(ws):
    config = configuration(ws)
    projects = []
    for project in config['projects']:
        try: projects.append(snapshot(project))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            # One damaged project must not erase every other project's dashboard.
            projects.append(dict(project, available=False, observed_at=_now(), errors=['Malformed saved evidence.'],
                                 detail='Saved evidence could not be interpreted. No successful result is inferred.'))
    return {'revision': config['revision'], 'observed_at': _now(), 'panels': list(PANELS),
            'projects': projects,
            'scope': 'General and per-project dashboards. Adding/removing a view never starts/stops a worker or deletes a project. Live API/webhook connectors are not implemented.'}
