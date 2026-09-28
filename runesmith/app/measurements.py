"""Selected local report measurements. No live connectors, formulas or code execution."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from runesmith.canon import digest
from runesmith.app.workspace import WorkspaceError, _write_json, _now
from runesmith.app.worker_journal import Record

PARSER = 'local-reports-v2'  # Reject ambiguous JSON; older receipts remain historical evidence.
MAX_BYTES, MAX_ROWS = 256_000, 5_000
SOURCES = {'csv', 'json', 'paste_csv', 'paste_json', 'ga4', 'email'}
AGGREGATIONS = {'count', 'sum', 'mean', 'latest', 'ratio'}


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', value):
        raise WorkspaceError('Invalid measurement ID.')
    return value


def _text(value, name, limit=500, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise WorkspaceError(f'{name} must be text, at most {limit} characters' + (' and nonempty.' if required else '.'))
    return value.strip()


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        raise WorkspaceError('Timestamps must be ISO 8601 with a timezone.') from None
    if result.tzinfo is None:
        raise WorkspaceError('Timestamps must include a timezone.')
    return result.astimezone(timezone.utc)


def report_path(ws, rel):
    p = PurePosixPath(rel.replace('\\', '/'))
    if (not rel or p.is_absolute() or any(part in ('..', '.') or ':' in part or part.startswith('.') for part in p.parts)
            or any(part.lower() in {'secrets', 'credentials', 'private', 'customers', 'node_modules'} for part in p.parts)):
        raise WorkspaceError('Select a relative report path, outside private and internal folders.')
    path = ws.root
    for part in p.parts:
        path = path / part
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise WorkspaceError('Report paths may not follow links or junctions.')
    resolved = path.resolve()
    excluded = [os.path.normcase(str(v).replace('\\', '/').strip('/')).replace('\\', '/') for v in ws.settings()['exclude']]
    comparable = os.path.normcase(p.as_posix()).replace('\\', '/')
    if (not resolved.is_relative_to(ws.root) or resolved.is_relative_to(ws.home)
            or any(comparable == e or comparable.startswith(e + '/') for e in excluded)):
        raise WorkspaceError('Report path is outside the allowed workspace scope.')
    if path.suffix.lower() not in {'.csv', '.json', '.txt'} or any(word in path.name.lower() for word in ('secret', 'credential', 'token')):
        raise WorkspaceError('Select a CSV/JSON/text report, not a credential file.')
    return path


def _natural(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', name)]


def report_file(ws, rel):
    """The report a definition reads. A * in the file name means the newest matching file, in natural order
    (week-9 before week-10), so a report that arrives as a new file every week needs no new definition
    (journey J5-G2: the till exports reports/week-40.csv next week)."""
    name = PurePosixPath(rel.replace('\\', '/')).name
    if '*' not in name:
        return report_path(ws, rel)
    probe = report_path(ws, rel.replace('*', 'x'))               # the folder and the pattern follow the same rules
    matches = sorted((p for p in probe.parent.glob(name) if p.is_file()), key=lambda p: _natural(p.name))
    if not matches:
        raise WorkspaceError(f'No report matches {rel} yet.')
    newest = matches[-1]
    return report_path(ws, (PurePosixPath(rel.replace('\\', '/')).parent / newest.name).as_posix())


def definitions(ws):
    path = ws.home / 'MEASUREMENTS.json'
    body = Record(path).value
    if path.exists() and (not isinstance(body, dict) or not isinstance(body.get('items'), list)):
        raise WorkspaceError('Measurement definitions are unreadable; do not silently replace them.')
    body = body or {'schema': 'runesmith.measurements.v1', 'items': []}
    seen = set()
    for row in body['items']:
        if not isinstance(row, dict):
            raise WorkspaceError('Measurement definition has an invalid shape.')
        mid = _id(row.get('id'))
        if mid in seen:
            raise WorkspaceError('Measurement definitions contain a duplicate ID.')
        seen.add(mid)
    return {'revision': digest(body), 'items': body['items']}


def save_definition(ws, raw, revision):
    with ws._lock:
        current = definitions(ws)
        if current['revision'] != revision:
            raise WorkspaceError('Measurement definitions changed; reload before saving.')
        if not isinstance(raw, dict):
            raise WorkspaceError('A measurement definition is required.')
        mid = _id(raw.get('id') or 'metric-' + uuid.uuid4().hex[:12])
        item = {'id': mid}
        for field, limit, required in [('name', 120, True), ('goal', 200, False), ('source_kind', 20, True),
                ('path', 500, False), ('field', 100, False), ('unit', 80, False), ('aggregation', 20, True),
                ('denominator_field', 100, False),
                ('time_field', 100, False), ('start', 60, False), ('end', 60, False),
                ('filter_field', 100, False), ('filter_equals', 200, False), ('instructions', 2000, False),
                ('source_label', 200, False), ('email_subject', 200, False), ('email_sender', 200, False)]:
            item[field] = _text(raw.get(field, ''), field, limit, required)
        if item['source_kind'] not in SOURCES or item['aggregation'] not in AGGREGATIONS:
            raise WorkspaceError('Choose a supported source and aggregation.')
        if type(raw.get('enabled', True)) is not bool:
            raise WorkspaceError('Enabled must be true or false.')
        item['enabled'] = raw.get('enabled', True)
        if item['source_kind'] in {'csv', 'json'}:
            report_path(ws, item['path'].replace('*', 'x'))   # a pattern may match nothing yet
        if item['aggregation'] != 'count' and not item['field']:
            raise WorkspaceError('This aggregation needs a numeric field.')
        if item['aggregation'] == 'ratio' and not item['denominator_field']:
            raise WorkspaceError('A ratio needs the column to divide by.')
        if (item['start'] or item['end']) and not item['time_field']:
            raise WorkspaceError('A time window needs a timestamp field.')
        if item['start']: _time(item['start'])
        if item['end']: _time(item['end'])
        if item['start'] and item['end'] and _time(item['start']) >= _time(item['end']):
            raise WorkspaceError('Window start must precede end (end is exclusive).')
        if item['aggregation'] == 'latest' and not item['time_field']:
            raise WorkspaceError('Latest needs a timestamp field; file order is not time order.')
        max_age = raw.get('max_age_hours')
        if max_age is not None:
            if type(max_age) not in (int, float) or not math.isfinite(max_age) or not 0 < max_age <= 87600:
                raise WorkspaceError('Maximum data age must be a finite positive number of hours, at most 87600.')
            if not item['time_field']:
                raise WorkspaceError('A data-age rule needs a timestamp field; measurement time is not data time.')
            item['max_age_hours'] = max_age
        threshold = raw.get('threshold')
        if threshold is not None:
            if (not isinstance(threshold, dict) or threshold.get('op') not in {'gte', 'lte'}
                    or type(threshold.get('value')) not in (int, float) or not math.isfinite(threshold['value'])):
                raise WorkspaceError('Threshold must be a finite number with gte or lte.')
            item['threshold'] = {'op': threshold['op'], 'value': threshold['value']}
        else:
            item['threshold'] = None
        rows = [item if r['id'] == mid else r for r in current['items']]
        if not any(r['id'] == mid for r in current['items']): rows.append(item)
        if len(rows) > 32: raise WorkspaceError('At most 32 measurements per workspace.')
        _write_json(ws.home / 'MEASUREMENTS.json', {'schema': 'runesmith.measurements.v1', 'items': rows})
        ws.ledger.append('measurement.configured', {'id': mid, 'definition_digest': digest(item), 'source_kind': item['source_kind']})
    return definitions(ws)


def _definition(ws, mid):
    return next((r for r in definitions(ws)['items'] if r['id'] == _id(mid)), None)


def save_pasted_report(ws, mid, text):
    item = _definition(ws, mid)
    if not item or item['source_kind'] not in {'paste_csv', 'paste_json'}:
        raise WorkspaceError('Select a pasted-report measurement first.')
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > MAX_BYTES:
        raise WorkspaceError(f'Paste a nonempty report of at most {MAX_BYTES} bytes.')
    sha = hashlib.sha256(text.encode()).hexdigest()
    with ws._lock:
        if digest(_definition(ws, mid)) != digest(item):
            raise WorkspaceError('Measurement definition changed before receiving this report; reload first.')
        path = ws.home / 'measurement-inputs' / mid / (sha + '.json')
        if not path.exists(): _write_json(path, {'text': text, 'received_at': _now()})
        _write_json(ws.home / 'measurement-inputs' / (mid + '.json'), {'sha256': sha})
        ws.ledger.append('measurement.report_received', {'id': mid, 'source_sha256': sha})
    return {'id': mid, 'source_sha256': sha, 'measured': False}


def _raw_report(ws, item):
    if item['source_kind'].startswith('paste_'):
        pointer = Record(ws.home / 'measurement-inputs' / (item['id'] + '.json')).value
        sha = pointer.get('sha256') if isinstance(pointer, dict) else None
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha):
            raise WorkspaceError('No valid pasted-report identity has been received.')
        saved = Record(ws.home / 'measurement-inputs' / item['id'] / (sha + '.json')).value
        text = saved.get('text') if isinstance(saved, dict) else None
        if not isinstance(text, str): raise WorkspaceError('Saved report payload is missing or invalid.')
        raw = text.encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != sha: raise WorkspaceError('Saved report identity does not match.')
        return raw
    path = report_file(ws, item['path'])
    with path.open('rb') as stream:
        return stream.read(MAX_BYTES + 1)


def evaluate(raw, item):
    if len(raw) > MAX_BYTES: raise WorkspaceError(f'Report exceeds {MAX_BYTES} bytes.')
    text = raw.decode('utf-8-sig')
    if item['source_kind'].endswith('csv'):
        reader = csv.DictReader(io.StringIO(text), strict=True)
        fields = reader.fieldnames or []
        if len(set(fields)) != len(fields) or any(not f for f in fields):
            raise WorkspaceError('CSV headers must be unique and nonempty.')
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS: raise WorkspaceError('Report row limit exceeded.')
            if None in row or any(v is None for v in row.values()): raise WorkspaceError('CSV row does not match its headers.')
            rows.append(row)
    else:
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise WorkspaceError('JSON report contains duplicate field names.')
                result[key] = value
            return result
        rows = json.loads(text, object_pairs_hook=unique_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(WorkspaceError('JSON report contains a non-finite value.')))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise WorkspaceError('JSON report must be an array of row objects.')
        if len(rows) > MAX_ROWS: raise WorkspaceError('Report row limit exceeded.')
    counts = {'total': len(rows), 'filter_excluded': 0, 'window_excluded': 0, 'included': 0}
    selected = []
    for row in rows:
        required = [item[k] for k in ('field', 'time_field', 'filter_field') if item[k]]
        if item['aggregation'] == 'ratio':
            required.append(item.get('denominator_field') or '')
        if any(k not in row for k in required): raise WorkspaceError('A configured field is missing from a report row.')
        if item['filter_field'] and str(row[item['filter_field']]) != item['filter_equals']:
            counts['filter_excluded'] += 1; continue
        at = _time(row[item['time_field']]) if item['time_field'] else None
        if at and ((item['start'] and at < _time(item['start'])) or (item['end'] and at >= _time(item['end']))):
            counts['window_excluded'] += 1; continue
        number = 1.0
        if item['aggregation'] != 'count':
            value = row[item['field']]
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise WorkspaceError('The numeric field contains a nonnumeric value.')
            try: number = float(value)
            except (TypeError, ValueError): raise WorkspaceError('The numeric field contains a nonnumeric value.') from None
            if not math.isfinite(number): raise WorkspaceError('The numeric field contains a non-finite value.')
        below = _number(row[item['denominator_field']]) if item['aggregation'] == 'ratio' else None
        selected.append((at, number, below)); counts['included'] += 1
    if not selected:
        return {'status': 'unknown', 'value': None, 'detail': 'No rows in the selected population/window; not zero.', 'rows': counts}
    values = [v for _, v, _ in selected]
    kind = item['aggregation']
    if kind == 'ratio':
        below = math.fsum(b for _, _, b in selected)
        if below == 0:
            return {'status': 'unknown', 'value': None, 'detail': 'The column to divide by sums to zero; not a ratio.', 'rows': counts}
        return {'status': 'measured', 'value': math.fsum(values) / below, 'rows': counts,
                'latest_data_at': max(at for at, _, _ in selected).isoformat() if item['time_field'] else None}
    if kind == 'latest':
        newest = max(at for at, _, _ in selected)
        candidates = {v for at, v, _ in selected if at == newest}
        if len(candidates) != 1: raise WorkspaceError('Latest timestamp has conflicting values.')
        value = candidates.pop()
    else:
        value = len(values) if kind == 'count' else math.fsum(values) / (len(values) if kind == 'mean' else 1)
    if not math.isfinite(value): raise WorkspaceError('Aggregate is not finite.')
    return {'status': 'measured', 'value': value, 'rows': counts,
            'latest_data_at': max(at for at, _, _ in selected).isoformat() if item['time_field'] else None}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise WorkspaceError('The numeric field contains a nonnumeric value.')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise WorkspaceError('The numeric field contains a nonnumeric value.') from None
    if not math.isfinite(number):
        raise WorkspaceError('The numeric field contains a non-finite value.')
    return number


def measure(ws, mid):
    item = _definition(ws, mid)
    if not item: raise WorkspaceError('Unknown measurement.')
    if not item['enabled']: raise WorkspaceError('This measurement is disabled.')
    raw, sha = None, None
    if item['source_kind'] in {'ga4', 'email'}:
        result = {'status': 'unavailable', 'value': None, 'detail': 'Live connector not implemented or connected. Use a selected local export instead.'}
    else:
        try:
            if item['source_kind'] in {'csv', 'json'}:              # the file read: the newest match of a pattern
                source = report_file(ws, item['path'])
                with source.open('rb') as stream:
                    raw = stream.read(MAX_BYTES + 1)
            else:
                source, raw = None, _raw_report(ws, item)
            sha = hashlib.sha256(raw).hexdigest()
            result = evaluate(raw, item)
            if source is not None:
                result['source_file'] = source.relative_to(ws.root).as_posix()
        except (OSError, UnicodeError, ValueError, csv.Error, WorkspaceError, OverflowError) as error:
            result = {'status': 'error', 'value': None, 'detail': str(error)[:400] if isinstance(error, WorkspaceError) else f'Report could not be read: {type(error).__name__}'}
    rid = digest({'parser': PARSER, 'definition': item, 'source': sha, 'result': result}).split(':', 1)[-1]
    path = ws.home / 'measurement-receipts' / (rid + '.json')
    old = Record(path).value
    receipt = dict(result, id=rid, measurement_id=mid, measured_at=_now(), parser=PARSER,
        source_sha256=sha, source_kind=item['source_kind'], definition_digest=digest(item), unit=item['unit'],
        window={'start': item['start'], 'end_exclusive': item['end']}, threshold=item['threshold'], threshold_met=None,
        scope='Selected local report only. Not verified business truth, code acceptance or scientific confirmation.')
    if item['threshold'] and result['status'] == 'measured':
        t = item['threshold']; receipt['threshold_met'] = result['value'] >= t['value'] if t['op'] == 'gte' else result['value'] <= t['value']
    if old is not None:
        if not isinstance(old, dict) or any(old.get(k) != v for k, v in receipt.items() if k != 'measured_at'):
            raise WorkspaceError('Existing measurement receipt conflicts with this observation; preserved for inspection.')
        _time(old.get('measured_at'))
        receipt = old
    with ws._lock:
        if digest(_definition(ws, mid)) != digest(item): raise WorkspaceError('Measurement definition changed while reading; try again.')
        if old is None:
            _write_json(path, receipt)
            ws.ledger.append('measurement.observed', {'id': mid, 'receipt': rid, 'status': receipt['status']})
        _write_json(ws.home / 'measurement-latest' / (mid + '.json'), {'receipt': rid})
    return dict(receipt, reused=bool(old))


def assess(item, receipt, *, pasted_sha=None, input_error=None):
    """Pure projection of saved evidence; never re-read reports or renew receipts.

    Deliberately no moving clock/age counter in the returned object: readiness
    may change at a boundary, but viewing it does not invent new evidence.
    """
    row = receipt if isinstance(receipt, dict) else {}
    reasons, notes = [], []
    current = bool(row) and row.get('definition_digest') == digest(item)
    numeric = type(row.get('value')) in (int, float) and math.isfinite(row['value'])
    if row.get('status') != 'measured' or not numeric:
        reasons.append('A successful numeric observation is required.')
    if not current:
        reasons.append('The saved receipt does not match the current definition.')
    kind = item.get('source_kind')
    if kind in {'paste_csv', 'paste_json'}:
        if input_error or not isinstance(pasted_sha, str) or not re.fullmatch('[a-f0-9]{64}', pasted_sha):
            source = 'unknown'
            reasons.append('The current pasted-report identity is missing or unreadable; inspect and measure the intended report.')
        elif pasted_sha != row.get('source_sha256'):
            source = 'superseded'
            reasons.append('A different pasted report is waiting to be measured; this is a historical result.')
        else:
            source = 'matching_paste'
            notes.append('Saved receipt matches the selected pasted-report identity; payload not re-read here.')
    elif kind in {'csv', 'json'}:
        source = 'not_rechecked'
        notes.append('The selected local file was not re-read; use Measure now after replacing it.')
    else:
        source = 'unavailable'
        reasons.append('Live connector is unavailable; this is not a live operational measurement.')
    maximum = item.get('max_age_hours')
    if maximum is None:
        age = 'not_configured'
        notes.append('No data-age rule configured; usable history is not evidence of current conditions.')
    elif type(maximum) not in (int, float) or not math.isfinite(maximum) or not 0 < maximum <= 87600:
        age = 'invalid_policy'
        reasons.append('The saved data-age rule is invalid; repair the definition before using it.')
    else:
        try:
            elapsed = (_time(_now()) - _time(row.get('latest_data_at'))).total_seconds()
            if elapsed < 0:
                age = 'future'
                reasons.append('The newest selected data timestamp is in the future; inspect the report and clock.')
            elif elapsed > maximum * 3600:
                age = 'expired'
                reasons.append(f'The newest selected data exceeds the configured age limit of {maximum:g} hours.')
            else:
                age = 'within_limit'
                notes.append(f'The newest selected data is within the configured {maximum:g}-hour age limit.')
        except WorkspaceError:
            age = 'unknown'
            reasons.append('Data age is unknown: a valid timezone-qualified data timestamp is required.')
    usable = not reasons
    return {'usable': usable, 'blockers': reasons, 'current_definition': current,
            'source_status': source, 'age_status': age,
            'qualified_threshold_met': row.get('threshold_met') if usable and age == 'within_limit' and type(row.get('threshold_met')) is bool else None,
            'detail': ' '.join(reasons + notes),
            'scope': 'Saved-report readiness only. The newest included row does not prove completeness, current source contents, business truth or causality. Refresh does not remeasure.'}


def latest(ws, item):
    mid = _id(item['id'])
    try:
        pointer = Record(ws.home / 'measurement-latest' / (mid + '.json')).value
        if pointer is None:
            return None
        rid = pointer.get('receipt') if isinstance(pointer, dict) else None
        if not isinstance(rid, str) or not re.fullmatch('[a-f0-9]{64}', rid):
            raise WorkspaceError('Measurement receipt pointer is invalid; inspect the retained evidence.')
        row = Record(ws.home / 'measurement-receipts' / (rid + '.json')).value
        if not isinstance(row, dict):
            raise WorkspaceError('Referenced measurement receipt is missing or invalid.')
        if row.get('id', rid) != rid or row.get('measurement_id', mid) != mid:
            raise WorkspaceError('Measurement receipt identity does not match its pointer.')
    except (WorkspaceError, OSError) as error:
        row = {'status': 'error', 'value': None, 'threshold_met': None, 'detail': str(error)[:400]}
    pasted_sha, input_error = None, None
    if item.get('source_kind') in {'paste_csv', 'paste_json'}:
        try:
            source = Record(ws.home / 'measurement-inputs' / (mid + '.json')).value
            pasted_sha = source.get('sha256') if isinstance(source, dict) else None
        except (WorkspaceError, OSError) as error:
            input_error = str(error)
    assessment = assess(item, row, pasted_sha=pasted_sha, input_error=input_error)
    # No arbitrary stored packets or report rows in the model-facing projection.
    fields = ('status', 'value', 'rows', 'latest_data_at', 'detail', 'id', 'measurement_id', 'measured_at',
              'parser', 'source_sha256', 'source_kind', 'definition_digest', 'unit', 'window', 'threshold',
              'threshold_met', 'scope', 'source_file')
    return dict({k: row[k] for k in fields if k in row},
                current_definition=assessment['current_definition'], assessment=assessment)


def view(ws):
    body = definitions(ws)
    return dict(body, items=[dict(item, last=latest(ws, item), adapter='local import' if item['source_kind'] not in {'ga4', 'email'} else 'unavailable') for item in body['items']],
                max_bytes=MAX_BYTES, max_rows=MAX_ROWS,
                scope='No inbox access or live analytics requests. Raw report rows are not sent to models.')


def prompt_summary(ws, ids=None):
    return [{'id': item['id'], 'name': item['name'], 'goal': item['goal'], 'instructions': item['instructions'],
             'unit': item['unit'], 'aggregation': item['aggregation'], 'source_label': item['source_label'],
             'last': latest(ws, item)} for item in definitions(ws)['items'] if item['enabled'] and (ids is None or item['id'] in ids)]
