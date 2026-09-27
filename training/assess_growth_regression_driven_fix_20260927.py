"""Assess one returned fix against retained probes and its unchanged project test.

No full project/owner verification, inference, acceptance edits or application.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnose_growth_export_review_20260926 import probe
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.building import _candidate_files
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.snapshots import collect_snapshot, load_snapshot
from runesmith.app.workspace import Workspace, _read_json, _write_json, _now


def main():
    root = Path(__file__).resolve().parent / 'GrowthHat'; home = root / '.runesmith'
    out = home / 'trainer-trials/gemini-m5-regression-driven-assessment-20260927.json'
    lock = InstanceLock(home)
    if not lock.acquire(): raise RuntimeError('Home has another writer.')
    try:
        if out.exists():
            print(json.dumps({'already_assessed': True, 'state': _read_json(out, {}).get('state')})); return
        if _existing(home) or (home / 'STUDIO_CURRENT.json').exists():
            raise RuntimeError('Resident/current/interrupted work requires reconciliation.')
        ws = Workspace(root, home)
        if pending_authors(ws) or ws.manual_waiting(): raise RuntimeError('Remote/manual work pending.')
        author = _read_json(home / 'trainer-trials/gemini-m5-regression-driven-fix-20260927.json', {})
        if author.get('state') != 'admitted': raise RuntimeError('No admitted author result.')
        draft = ws._draft(author['draft']); prior = ws._draft(author['prior_draft'])
        if draft['state'] != 'waiting' or draft.get('verification'):
            raise RuntimeError('Candidate already assessed or changed.')
        source = collect_snapshot(ws)['digest']
        if source != author['source_digest'] or expectation_digest(ws, 'm5') != author['public_acceptance_digest']:
            raise RuntimeError('Source or acceptance changed.')
        def intact():
            return all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
                       for p, sha in author['protected_sha256'].items())
        if not intact(): raise RuntimeError('Historical or acceptance record changed.')
        changed = [f['path'] for f in draft['files']
                   if f['content'] != next(p['content'] for p in prior['files'] if p['path'] == f['path'])]
        if changed != ['growthhat/cli.py']: raise RuntimeError('Unexpected changed paths.')
        test = 'tests.test_recommendation_cli.TestExportRecommendationsCLI.test_export_serialization_error_cleanup'
        record = {'state': 'started', 'utc': _now(), 'draft': draft['id'], 'prior': prior['id'],
            'source_digest': source, 'author': draft['drafted_by'], 'changed_files': changed,
            'inference_calls': 0, 'full_project_checks': False, 'owner_checks': False, 'apply': False,
            'project_tests_unchanged': True, 'test': test, 'timeout_s': 45,
            'scope': 'Existing trainer controlled-function probes plus one unchanged model-authored development regression. Not full project, owner or production acceptance.',
            'probe_script_sha256': hashlib.sha256((Path(__file__).parent / 'diagnose_growth_export_review_20260926.py').read_bytes()).hexdigest(),
            'probe_limit': 'Existing descriptor counter tracks os.open handles only; built-in open handles are not fully instrumented. No broad leak-freedom claim.',
            'review_observation': 'Returned code uses exists then a fixed .tmp path then Path.replace. Review predicts racing-destination overwrite and possible unrelated .tmp overwrite; test those claims distinctly, do not infer from a passing serialization test.'}
        _write_json(out, record)
        results = []
        for candidate in (prior, draft):
            race = probe(candidate, 'race'); export = probe(candidate, 'export_error')
            with patch('json.dump', side_effect=TypeError('synthetic serialization failure')) as injected:
                serializer = probe(candidate, 'serialization_error'); injections = injected.call_count
            results.append({'draft': candidate['id'], 'race': race, 'export_error': export,
                            'serialization_error': serializer, 'serializer_injections': injections})
        record['function_probes'] = results
        stage = Path(tempfile.mkdtemp(prefix='growth-regression-positive-check-', dir=root.parent / '.tmp'))
        for rel, data in _candidate_files(load_snapshot(ws, draft['snapshot_digest']), draft).items():
            dest = stage / rel
            if not dest.resolve().is_relative_to(stage): raise RuntimeError('Invalid staged path.')
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
        record['stage'] = str(stage); _write_json(out, record)
        env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC'}}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                   TEMP=str(stage), TMP=str(stage), USERPROFILE=str(stage))
        try:
            run = subprocess.run([sys.executable, '-m', 'unittest', test, '-v'], cwd=stage, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=45)
            record['project_regression'] = {'exit_code': run.returncode, 'output': run.stdout[-12000:],
                                             'passed': run.returncode == 0 and 'Ran 1 test' in run.stdout}
        except subprocess.TimeoutExpired as error:
            record['project_regression'] = {'passed': None, 'status': 'timeout', 'output': str(error.output)[-12000:]}
        before, after = results
        race_preserved = after['race'].get('return_code') == 1 and after['race'].get('competitor_preserved') is True
        export_ok = after['export_error'].get('return_code') == 1 and after['export_error'].get('destination_exists') is False
        serial_ok = after['serialization_error'].get('return_code') == 1 and after['serialization_error'].get('destination_exists') is False
        record.update(race_preserved=race_preserved, export_error_passed=export_ok, serialization_probe_passed=serial_ok,
                      regression_resolves_reported_failure=record['project_regression']['passed'] is True)
        if not (race_preserved and export_ok and serial_ok and record['project_regression']['passed'] is True):
            note = ws.notes.add(target_type='draft', target_id=draft['id'], target_label=draft['title'], author='external-trainer',
                text='This implementation-only allocation is finished and parked. The unchanged model-authored serialization regression '
                     'and serializer probe passed, but the retained competitor-at-open probe regressed: the predecessor returned 1 '
                     'and preserved competitor bytes; this candidate returned 0 and overwrote them. Do not apply or buy a silent '
                     'retry. The author traded one failure for a previously solved invariant. Source, tests and private/public '
                     'acceptance remain unchanged. The fixed .tmp filename also raises an untested collateral-file clobber concern. '
                     'Next work should retain all diagnostic behaviors, use a better-qualified author or improve the revision '
                     'context before a separately authorized attempt; passing the one new test alone is insufficient.')
            ws._save_draft_state(draft, 'needs_revision', review_requested_by='external-trainer', review_note=note['id'],
                                review_reason='Serialization fixed but existing no-clobber race regressed; no apply.')
            record.update(review_note=note['id'], decision='park_known_regression_no_full_suite_no_apply')
        else:
            record['decision'] = 'eligible_for_separately_allocated_full_checks; no acceptance or application yet'
        record.update(state='completed', finished=_now(), source_unchanged=collect_snapshot(ws)['digest'] == source,
                      protected_unchanged=intact())
        _write_json(out, record); ws.ledger.append('trainer.regression_driven_assessment', record)
        print(json.dumps(record), flush=True)
    finally:
        if lock.handle: lock.handle.close()


if __name__ == '__main__':
    main()
