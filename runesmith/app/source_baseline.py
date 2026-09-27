"""One diagnostic of current source per snapshot, never candidate acceptance.

The caller owns the normal per-home instance lock / Studio worker queue. Results
cannot apply files, advance a milestone, reset a budget or automatically retry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile

from runesmith.app import building
from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json

TIMEOUT_S = 240
COVERAGE = ('Current-source project suite only; pending candidate additions and '
            'owner acceptance were not evaluated. Not a milestone or business-outcome verdict.')


def baseline_status(ws):
    pending = _read_json(ws.home / 'SOURCE_BASELINE_PENDING.json', None)
    last = _read_json(ws.home / 'SOURCE_BASELINE_LAST.json', None)
    return {'enabled': bool(ws.settings()['build_steps'] and ws.settings()['autonomy'] != 'observe'),
            'pending': pending, 'last': last, 'timeout_s': TIMEOUT_S,
            'coverage': COVERAGE, 'inference_calls': 0}


def _inventory(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(262145)
        if len(raw) > 262144:
            return {'available': False}
        value = json.loads(raw)
        if (not isinstance(value, dict) or value.get('schema') != 1 or
                type(value.get('count')) is not int or value['count'] < 0 or
                not isinstance(value.get('ids'), list) or len(value['ids']) > 128 or
                any(not isinstance(name, str) or len(name) > 192 for name in value['ids']) or
                value.get('omitted') != value['count'] - len(value['ids']) or
                type(value.get('truncated_ids')) is not int or not 0 <= value['truncated_ids'] <= len(value['ids']) or
                not isinstance(value.get('sha256'), str) or len(value['sha256']) != 64):
            return {'available': False}
        return value | {'available': True, 'complete': value['omitted'] == value['truncated_ids'] == 0}
    except (OSError, ValueError, TypeError):
        return {'available': False}


def measure_current_source(ws, reason, *, checkpoint=lambda: None):
    if not baseline_status(ws)['enabled']:
        return {'summary': 'Executable checks are off; no baseline measured.'}
    if not isinstance(reason, str) or not reason.strip():
        raise WorkspaceError('Explain this source-only timing measurement.')
    marker = ws.home / 'SOURCE_BASELINE_PENDING.json'
    with ws._lock:
        if marker.exists():
            raise WorkspaceError('A source measurement is active or unresolved; reconcile it before another run.')
        snapshot = collect_snapshot(ws)
        folder = ws.home / 'source-baseline-runs' / snapshot['digest']
        receipt_path = folder / 'BASELINE.json'
        if receipt_path.exists():
            prior = _read_json(receipt_path, {})
            return {'summary': 'This source snapshot already has a reserved measurement. Nothing rerun.',
                    'already_used': True, 'baseline': prior}
        checkpoint()
        freeze_snapshot(ws, snapshot)
        receipt = {'id': 'source-' + snapshot['digest'], 'kind': 'source_baseline_diagnostic',
            'state': 'started', 'started': _now(), 'reason': reason.strip()[:2000],
            'snapshot_digest': snapshot['digest'], 'input_files': len(snapshot['files']),
            'timeout_s': TIMEOUT_S, 'max_phases': 1, 'inference_calls': 0,
            'candidate_applied': False, 'milestone_advanced': False, 'author_budget_reset': False,
            'coverage': COVERAGE, 'interpreter': sys.executable, 'python': sys.version,
            'runner_sha256': hashlib.sha256(building.RUNNER.encode()).hexdigest(),
            'host_contention': 'Other-process workload is not measured; caller serializes workspace checks.',
            'evidence_dir': folder.relative_to(ws.home).as_posix()}
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(receipt_path, receipt)
        _write_json(marker, {'id': receipt['id'], 'state': 'started', 'evidence_dir': receipt['evidence_dir']})
        _write_json(ws.home / 'SOURCE_BASELINE_LAST.json', receipt)
        ws.ledger.append('source_baseline.started', receipt)
    try:
        checkpoint()
        with tempfile.TemporaryDirectory(prefix='source-stage-', dir=folder) as directory:
            stage = Path(directory)
            for rel, content in snapshot['files'].items():
                if not ws._safe_rel(rel):
                    raise WorkspaceError('Snapshot contains an unsafe relative path.')
                target = stage / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            inventory_path = folder / 'project-checks.inventory.json'
            checks = building._run_checks(stage, 'project', folder / 'project-checks.txt',
                                         timeout_s=TIMEOUT_S, inventory_path=inventory_path)
            changed = [rel for rel, content in snapshot['files'].items()
                       if not (stage / rel).is_file() or (stage / rel).read_bytes() != content]
        receipt.update(state='completed', finished=_now(), project_checks=checks,
            inventory=_inventory(inventory_path), stage_inputs_changed=changed,
            source_still_current=collect_snapshot(ws)['digest'] == snapshot['digest'],
            outcome='inconclusive' if checks.get('status') == 'timeout' else
                    'baseline_discrepancy' if changed or not checks.get('ok') else 'measured')
        _write_json(receipt_path, receipt)
        _write_json(ws.home / 'SOURCE_BASELINE_LAST.json', receipt)
        ws.ledger.append('source_baseline.completed', {'id': receipt['id'], 'outcome': receipt['outcome'],
            'evidence_dir': receipt['evidence_dir'], 'coverage': COVERAGE})
        marker.unlink()
        return {'summary': 'Source-only timing diagnostic: ' + receipt['outcome'] + '. ' + COVERAGE,
                'baseline': receipt}
    except BaseException as error:
        # Even a stopped process retains its reservation. No automatic rerun,
        # candidate credit, or pass inferred from partial progress.
        receipt.update(state='interrupted', finished=_now(), error=type(error).__name__, outcome='unknown')
        _write_json(receipt_path, receipt)
        _write_json(ws.home / 'SOURCE_BASELINE_LAST.json', receipt)
        _write_json(marker, {'id': receipt['id'], 'state': 'interrupted', 'evidence_dir': receipt['evidence_dir']})
        ws.ledger.append('source_baseline.interrupted', {'id': receipt['id'], 'error': type(error).__name__})
        raise
