"""Read-only field custody/accounting audit; no Workspace initialization or job.

Only Support/Growth source is hashed. Live PRHat is never scanned. Existing OS
locks are briefly acquired to distinguish a free home from a concurrent writer.
"""
import hashlib
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.author_recovery import pending_authors
from runesmith.app.building import build_escalation_status
from runesmith.app.inference_accounting import accounting_view
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _read_json, _now
from runesmith.app.worker_journal import Record, validate_queue
from runesmith.keystore import KeyStore
from runesmith.notes import NoteStore

TRAINING = Path(__file__).resolve().parent
BASELINES = {
    'SupportHat': 'json-input-m7-paid-author-20260927.json',
    'GrowthHat': 'gemini-m5-regression-driven-fix-20260927.json',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(name):
    home = TRAINING / name / '.runesmith'
    if not home.is_dir() or not (home / 'studio.instance.lock').exists():
        return {'project': name, 'error': 'Existing home/lock missing; not initialized'}
    ws = object.__new__(Workspace)
    ws.root = Path('C:/dev/PRHat') if name == 'PRHat' else TRAINING / name
    ws.home = home
    ws.notes, ws.keys = NoteStore(home), KeyStore(home)
    ws._lock, ws._ops_lock = threading.RLock(), threading.RLock()
    lock = InstanceLock(home)
    acquired = lock.acquire()
    try:
        result = {'project': name, 'utc': _now(), 'lock_available': acquired,
            'resident': bool(_existing(home)), 'recorded_current': (home / 'STUDIO_CURRENT.json').exists()}
        if not acquired or result['resident'] or result['recorded_current']:
            return result
        queued, hold = validate_queue(Record(home / 'STUDIO_QUEUE.json').value, ws.root)
        control = Record(home / 'STUDIO_STATE.json').value or {}
        result.update(queued_intentions=len(queued), recovery_hold=bool(hold), paused=bool(control.get('paused')))
        result.update(pending_authors=len(pending_authors(ws)), manual_waiting=ws.manual_waiting(),
            auto_work=ws.settings()['auto_work'], kaizen=ws.settings()['kaizen'],
            plan_role=ws.config()['roles'].get('plan'))
        report = accounting_view(home)
        result['accounting'] = {k: report[k] for k in ('summary', 'coverage')}
        if name == 'SupportHat':
            result['m7_failed_job'] = next((r for r in report['requests']
                if r['job_id'] == 'mj_3514978f176848a89e60'), None)
        if name != 'PRHat':
            prior = _read_json(home / 'trainer-trials' / BASELINES[name], {})
            protected = prior['protected_sha256']
            result.update(source_digest=collect_snapshot(ws)['digest'],
                protected_count=len(protected),
                protected_unchanged=all(Path(p).is_file() and sha(Path(p)) == value for p, value in protected.items()),
                milestones=[{'id': m['id'], 'status': m.get('status')}
                    for m in (ws.plan() or {}).get('milestones', [])])
            # Read retained headers only; no checks, admission or source writes.
            drafts = [_read_json(p, {}) for p in sorted((home / 'drafts').glob('*/DRAFT.json'))]
            latest = drafts[-1] if drafts else {}
            result['latest_draft'] = {k: latest.get(k) for k in ('id', 'milestone', 'state', 'verified')}
            allowance = build_escalation_status(ws)
            if allowance:
                result['ordinary_author_allowance'] = dict(
                    milestone=allowance['milestone'], escalation_eligible=allowance['eligible'],
                    escalation_used=allowance['used'], **(allowance.get('allowance') or {}))
            if name == 'SupportHat':
                result['m7_drafts'] = sum(d.get('milestone') == 'm7' for d in drafts)
        else:
            result['live_root_scanned'] = False
        return result
    finally:
        if lock.handle:
            lock.handle.close()


if __name__ == '__main__':
    print(json.dumps({'utc': _now(), 'new_model_calls': 0,
        'scope': 'Read-only home receipts and Support/Growth source identity; no live PRHat scan.',
        'projects': [audit(name) for name in ('SupportHat', 'GrowthHat', 'PRHat')]}))
