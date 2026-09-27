"""Bounded, diagnostic-only progress for the disposable unittest process.

The last atomic snapshot survives a test timeout. It never supplies a verdict or
permission to extend a deadline. A missing/malformed snapshot is just unknown.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


# Embedded in the existing stripped-environment child; no dependency on an
# installed Runesmith package, nor any import into the project being checked.
PROGRESS_RUNNER = r'''
import os,time

class ProgressJournal:
    def __init__(self, path):
        self.path=Path(path);self.result=None;self.start=time.monotonic()
        self.completed=0;self.active=None;self.phase="discovery"
        self.planned=None;self.recent=[];self.slowest=[];self.events=0
        self.write_errors=0
        self.event("discovery_started")

    def event(self, name, **details):
        now=time.monotonic();self.events+=1
        self.recent=(self.recent+[{"event":name,"elapsed_s":round(now-self.start,6),**details}])[-8:]
        result=self.result
        counts={"started":result.testsRun if result else 0,"completed":self.completed,
                "skipped":len(result.skipped) if result else 0,
                "failures":len(result.failures) if result else 0,
                "errors":len(result.errors) if result else 0}
        state={"schema":1,"phase":self.phase,"planned":self.planned,**counts,
               "active":self.active,"elapsed_s":round(now-self.start,6),
               "last_update_monotonic":now,"recent_events":self.recent,
               "events_total":self.events,"slowest":self.slowest,
               "write_errors":self.write_errors}
        temporary=self.path.with_suffix(self.path.suffix+".tmp")
        try:
            with temporary.open("w",encoding="utf-8") as stream:
                json.dump(state,stream,ensure_ascii=True,allow_nan=False)
            os.replace(temporary,self.path)
        except OSError:
            # Diagnostics are best-effort, not an alternative test result.
            self.write_errors+=1

progress=ProgressJournal(sys.argv[2])

class ProgressResult(unittest.TextTestResult):
    def startTestRun(self):
        super().startTestRun();progress.result=self
        progress.phase="fixtures_or_between_tests";progress.event("run_started")

    def startTest(self,test):
        super().startTest(test)
        self._test_start=time.monotonic();self._cpu_start=time.process_time()
        self._before=(len(self.failures),len(self.errors),len(self.skipped),
                      len(self.expectedFailures),len(self.unexpectedSuccesses))
        progress.active={"test":test.id()[:512],"started_monotonic":self._test_start}
        progress.phase="test";progress.event("test_started",test=test.id()[:512])

    def stopTest(self,test):
        elapsed=time.monotonic()-self._test_start;cpu=time.process_time()-self._cpu_start
        before=self._before
        outcome=("failed" if len(self.failures)>before[0] else
                 "error" if len(self.errors)>before[1] else
                 "skipped" if len(self.skipped)>before[2] else
                 "expected_failure" if len(self.expectedFailures)>before[3] else
                 "unexpected_success" if len(self.unexpectedSuccesses)>before[4] else "passed")
        timing={"test":test.id()[:512],"elapsed_s":round(elapsed,6),
                "cpu_s":round(cpu,6),"outcome":outcome}
        progress.slowest=sorted(progress.slowest+[timing],key=lambda row:row["elapsed_s"],reverse=True)[:5]
        progress.completed+=1;progress.active=None;progress.phase="fixtures_or_between_tests"
        super().stopTest(test);progress.event("test_completed",**timing)

    def addError(self,test,err):
        super().addError(test,err)
        # setUpClass / setUpModule failures have no matching startTest call.
        if progress.active is None:progress.event("fixture_error",test=test.id()[:512])

    def stopTestRun(self):
        super().stopTestRun();progress.phase="finished";progress.event("run_finished")
'''


def read_progress(path: Path, *, ended_monotonic: float, timed_out: bool) -> dict:
    """Read at most 64 KiB; never mistake telemetry for successful completion."""
    unknown = {'available': False, 'detail': 'No valid structured progress was captured.'}
    try:
        with path.open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            return unknown
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get('schema') != 1:
            return unknown
        phase = value['phase']
        if phase not in ('discovery', 'fixtures_or_between_tests', 'test', 'finished'):
            return unknown
        for key in ('started', 'completed', 'skipped', 'failures', 'errors', 'events_total', 'write_errors'):
            if type(value.get(key)) is not int or value[key] < 0:
                return unknown
        planned = value.get('planned')
        if planned is not None and (type(planned) is not int or planned < 0):
            return unknown
        if value['completed'] > value['started']:
            return unknown
        def duration(number):
            return type(number) in (int, float) and math.isfinite(number) and number >= 0
        if not duration(value.get('elapsed_s')) or not duration(value.get('last_update_monotonic')):
            return unknown
        updated = value['last_update_monotonic']
        if updated > ended_monotonic:
            return unknown
        active = value.get('active')
        if active is not None:
            if (not isinstance(active, dict) or not isinstance(active.get('test'), str)
                    or len(active['test']) > 512 or not duration(active.get('started_monotonic'))
                    or active['started_monotonic'] > updated):
                return unknown
            active = {'test': active['test'], 'unfinished': True,
                      'elapsed_s': round(ended_monotonic-active['started_monotonic'], 6)}
        slowest = value.get('slowest')
        events = value.get('recent_events')
        if not isinstance(slowest, list) or len(slowest) > 5 or not isinstance(events, list) or len(events) > 8:
            return unknown
        for row in slowest:
            if (not isinstance(row, dict) or not isinstance(row.get('test'), str)
                    or len(row['test']) > 512 or not duration(row.get('elapsed_s'))
                    or not duration(row.get('cpu_s')) or row.get('outcome') not in
                    ('passed', 'failed', 'error', 'skipped', 'expected_failure', 'unexpected_success')):
                return unknown
        # Project code can write arbitrary text; diagnostics are explicitly
        # reported observations, not a security boundary or acceptance evidence.
        return {key: value[key] for key in ('schema', 'phase', 'planned', 'started', 'completed', 'skipped',
                    'failures', 'errors', 'events_total', 'write_errors', 'slowest', 'elapsed_s')} | {
            'available': True, 'active': active, 'timed_out': timed_out,
            'last_report_age_s': round(ended_monotonic-updated, 6),
            'retained_events': len(events), 'omitted_events': max(0, value['events_total']-len(events)),
            'snapshot': path.name, 'scope': 'diagnostics only; not a verdict or additional time allowance'}
    except (OSError, ValueError, TypeError, KeyError):
        return unknown
