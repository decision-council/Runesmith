"""Record trainer-only function probes and review; no owner tests or model calls."""
from pathlib import Path
import hashlib
import json
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnose_growth_export_review_20260926 import probe
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    if _existing(home): raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Home has another writer')
    try:
        ws = Workspace(root, home); path = home / 'trainer-trials/gemini-m5-focused-units-assessment-20260926.json'
        if path.exists():
            print(json.dumps({'already_assessed': True, 'state': _read_json(path, {}).get('state')})); return
        if pending_authors(ws): raise RuntimeError('Pending author requires reconciliation')
        author = _read_json(home / 'trainer-trials/gemini-m5-focused-units-20260926.json', {})
        if author.get('state') != 'admitted': raise RuntimeError('No admitted focused candidate')
        draft = ws._draft(author['draft']); prior = ws._draft(author['prior_draft'])
        if draft['state'] != 'waiting' or draft.get('verification'): raise RuntimeError('Candidate changed')
        if collect_snapshot(ws)['digest'] != author['source_digest']: raise RuntimeError('Source changed')
        if expectation_digest(ws, 'm5') != author['public_acceptance_digest']: raise RuntimeError('Criteria changed')
        receipt = {'state': 'started', 'utc': _now(), 'draft': draft['id'], 'inference_calls': 0,
            'scope': 'Trainer controlled-function probes, not project/owner/full-application verification.',
            'original_probes': ['race', 'export_error'],
            'additional_probe': 'Exploratory serializer-error injection motivated by review of close(fd) after fdopen context exit. Not added to owner criteria.',
            'probe_script_sha256': hashlib.sha256((Path(__file__).parent / 'diagnose_growth_export_review_20260926.py').read_bytes()).hexdigest()}
        _write_json(path, receipt)
        race, export_error = probe(draft, 'race'), probe(draft, 'export_error')
        serialization = []
        for candidate in (prior, draft):
            with patch('json.dump', side_effect=TypeError('synthetic serialization failure')) as injected:
                result = probe(candidate, 'serialization_error')
                calls = injected.call_count
            serialization.append({'draft': candidate['id'], 'injected_calls': calls, 'result': result})
        original_pass = (race.get('return_code') == 1 and race.get('competitor_preserved')
                         and race.get('open_descriptors_after') == 0
                         and not export_error.get('destination_exists') and export_error.get('open_descriptors_after') == 0)
        tests_unchanged = next(f['content'] for f in draft['files'] if f['path'] == 'tests/test_recommendation_cli.py') == next(
            f['content'] for f in prior['files'] if f['path'] == 'tests/test_recommendation_cli.py')
        note = ws.notes.add(target_type='draft', target_id=draft['id'], target_label=draft['title'], author='external-trainer',
            text='Focused-packet review: the original competitor-race and export-data-exception function probes now pass. '
                 'However no new CLI regression was authored; the retained precreated-file test still does not discriminate '
                 'the earlier check-then-open defect. Additional exploratory serialization-failure injection reproduced OSError '
                 'and a leftover destination in both predecessor and this candidate: fdopen context exit closes fd, then '
                 'the exception handler closes it again before unlink. This is an inherited defect, not a newly introduced '
                 'regression. Preserve the two observed improvements. No owner criteria changed; full suites not run. '
                 'This one-call allocation is finished; no automatic author retry or apply.')
        ws._save_draft_state(draft, 'needs_revision', review_requested_by='external-trainer', review_note=note['id'],
                            review_reason='Original probes pass, but serializer cleanup and discriminating regression remain unresolved')
        receipt.update(state='finished', finished=_now(), race=race, export_error=export_error,
            original_probe_gate_passed=bool(original_pass), serialization_error=serialization,
            cli_tests_unchanged=tests_unchanged, review_note=note['id'],
            project_checks_run=False, owner_checks_run=False, applied=False,
            decision='park_one_call_allocation_with_partial_progress',
            source_unchanged=collect_snapshot(ws)['digest'] == author['source_digest'],
            protected_unchanged=all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
                                    for p, sha in author['protected_sha256'].items()))
        _write_json(path, receipt); ws.ledger.append('trainer.focused_unit_assessment', receipt)
        print(json.dumps(receipt))
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__': main()
