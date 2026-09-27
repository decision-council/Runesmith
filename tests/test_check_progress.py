from pathlib import Path
import shutil
import subprocess
import time

import pytest

from runesmith.app import building
from runesmith.app.check_progress import read_progress
from runesmith.app.build_memory import _check_summary
from test_build_steps import setup, enable


def suite(tmp_path, source):
    stage = tmp_path / 'stage'
    (stage / 'tests').mkdir(parents=True)
    (stage / 'tests/__init__.py').write_text('')
    (stage / 'tests/test_sample.py').write_text(source, encoding='utf-8')
    return stage


def test_progress_preserves_aggregate_counts_when_history_is_bounded(tmp_path):
    source = 'import unittest\nclass Checks(unittest.TestCase):\n'
    source += ''.join(f'    def test_{i:02d}(self): self.assertEqual(2+2,4)\n' for i in range(40))
    source += '    @unittest.skip("not in this fixture")\n    def test_skip(self): pass\n'
    stage = suite(tmp_path, source)
    result = building._run_checks(stage, 'project', tmp_path/'checks.txt', timeout_s=10)
    assert result['status'] == 'passed' and result['ran'] == 41
    progress = result['progress']
    assert progress['available'] and progress['phase'] == 'finished'
    assert progress['planned'] == progress['started'] == progress['completed'] == 41
    assert progress['skipped'] == 1 and progress['active'] is None
    assert progress['retained_events'] == 8 and progress['omitted_events'] > 60
    assert len(progress['slowest']) == 5
    assert all(row['elapsed_s'] >= 0 and row['cpu_s'] >= 0 for row in progress['slowest'])
    assert (tmp_path/progress['snapshot']).stat().st_size < 65536
    assert not list(stage.glob('*.progress*'))


def test_timeout_keeps_finished_count_and_unfinished_active_test(tmp_path):
    stage = suite(tmp_path, '''import unittest,time
class Checks(unittest.TestCase):
    def test_01_fast(self): self.assertTrue(True)
    def test_02_slow(self): time.sleep(20)
''')
    result = building._run_checks(stage, 'project', tmp_path/'checks.txt', timeout_s=2)
    assert result['status'] == 'timeout' and result['ok'] is False
    assert 'ran' not in result  # No fabricated final verdict from partial counts.
    progress = result['progress']
    assert progress['planned'] == progress['started'] == 2
    assert progress['completed'] == 1 and progress['failures'] == progress['errors'] == 0
    assert progress['active']['test'].endswith('test_02_slow')
    assert progress['active']['unfinished'] and progress['active']['elapsed_s'] > 0
    assert progress['timed_out'] and progress['last_report_age_s'] > 0


@pytest.mark.parametrize('source,phase,planned', [
    ('import time\ntime.sleep(20)\n', 'discovery', None),
    ('''import unittest,time
class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls): time.sleep(20)
    def test_unstarted(self): pass
''', 'fixtures_or_between_tests', 1),
])
def test_discovery_and_class_setup_are_not_mislabeled_as_active_tests(tmp_path,source,phase,planned):
    stage = suite(tmp_path, source)
    result = building._run_checks(stage, 'project', tmp_path/'checks.txt', timeout_s=2)
    progress = result['progress']
    assert result['status'] == 'timeout' and progress['phase'] == phase
    assert progress['active'] is None and progress['completed'] == progress['started'] == 0
    assert progress['planned'] == planned


def test_failure_and_class_fixture_errors_keep_existing_verdict(tmp_path):
    stage = suite(tmp_path, '''import unittest
class BadFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls): raise ValueError("bad fixture")
    def test_unstarted(self): pass
class Checks(unittest.TestCase):
    def test_failure(self): self.assertEqual(1,2)
    def test_ok(self): self.assertTrue(True)
''')
    result = building._run_checks(stage, 'project', tmp_path/'checks.txt', timeout_s=10)
    assert result['status'] == 'failed' and not result['ok']
    progress = result['progress']
    assert progress['completed'] == 2 and progress['planned'] == 3
    assert progress['errors'] == progress['failures'] == 1
    assert progress['active'] is None


def test_progress_write_failure_cannot_change_the_test_result(tmp_path):
    stage = suite(tmp_path, 'import unittest\nclass Checks(unittest.TestCase):\n    def test_ok(self): pass\n')
    (tmp_path/'checks.progress.json').mkdir()  # Journal destination unwritable as a file.
    result = building._run_checks(stage, 'project', tmp_path/'checks.txt', timeout_s=10)
    assert result['status'] == 'passed' and result['ran'] == 1
    assert not result['progress']['available']


@pytest.mark.parametrize('contents', ['{', '[]', '{"schema":1}', 'x'*65537],
                         ids=['partial-json', 'wrong-shape', 'incomplete-fields', 'oversized'])
def test_missing_or_invalid_telemetry_is_unknown_not_a_verdict(tmp_path,contents):
    path = tmp_path/'progress.json'
    assert not read_progress(path, ended_monotonic=time.monotonic(), timed_out=True)['available']
    path.write_text(contents)
    assert not read_progress(path, ended_monotonic=time.monotonic(), timed_out=True)['available']


def test_project_timeout_never_runs_owner_checks_or_applies(tmp_path,monkeypatch):
    ws = setup(tmp_path, acceptance=True); enable(ws)
    original = building._run_checks
    phases = []
    # Verify the runner directly for partial telemetry, then return that immutable
    # observation without changing the candidate passed to custody checks.
    stage = suite(tmp_path/'fixture', 'import unittest,time\nclass T(unittest.TestCase):\n    def test_wait(self): time.sleep(20)\n')
    observed = original(stage, 'project', tmp_path/'timeout.txt', timeout_s=2)
    def retained_observation(stage, kind, logs, **kwargs):
        phases.append(kind); return observed
    monkeypatch.setattr(building, '_run_checks', retained_observation)
    result = building.build_step(ws, ws.router())
    assert phases == ['project']
    assert result['verification']['status'] == 'inconclusive'
    assert result['verification']['acceptance'] is None
    assert result['verification']['project_checks']['progress']['completed'] == 0
    assert not result.get('advanced') and not (tmp_path/'app.py').exists()


def test_diagnostic_ids_do_not_enter_author_memory_projection():
    check = {'status':'timeout','progress':{'active':{'test':'private_owner_fixture_name'}}}
    summary = _check_summary(check)
    assert summary['status'] == 'timeout'
    assert 'progress' not in summary and 'private_owner_fixture_name' not in str(summary)


def test_studio_presentation_covers_timeout_owner_unrun_and_legacy_receipts():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is unavailable for the pure Studio presentation test')
    module = Path(__file__).parents[1]/'runesmith/app/static/js/check-progress.js'
    script = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
const source=fs.readFileSync(process.argv[1], 'utf8');
const {checkProgressLines}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
assert.equal(checkProgressLines('Owner acceptance', null)[0], 'Owner acceptance: not started.');
assert.match(checkProgressLines('Project checks', {status:'timeout'})[0], /completed count unknown/);
const lines=checkProgressLines('Project checks',{status:'timeout',progress:{available:true,completed:7,planned:8,skipped:1,failures:0,errors:0,active:{test:'T.unfinished',elapsed_s:2},last_report_age_s:2,retained_events:8,omitted_events:12,slowest:[{test:'T.slow',elapsed_s:1,cpu_s:0.01,outcome:'passed'}]}}).join('\n');
assert.match(lines,/7 completed \/ 8 discovered/);
assert.match(lines,/Unfinished.*T.unfinished/);
assert.match(lines,/not a failure verdict/);
assert.match(lines,/Slow completed test: T.slow/);
assert.match(lines,/No deadline change/);
'''
    result = subprocess.run([node,'--input-type=module','-e',script,str(module)],capture_output=True,text=True,timeout=20)
    assert result.returncode == 0, result.stderr
    view = (module.parent/'views/work.js').read_text(encoding='utf-8')
    assert "import { checkProgressLines } from '../check-progress.js'" in view
    assert "checkProgressLines('Project checks', d.verification.project_checks)" in view
    assert "checkProgressLines('Owner acceptance', d.verification.acceptance)" in view
