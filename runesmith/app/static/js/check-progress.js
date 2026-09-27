// Pure presentation: telemetry never supplies the check verdict or a deadline.
export function checkProgressLines(label, check) {
  if (!check) return [`${label}: not started.`];
  const progress = check.progress;
  if (!progress?.available) {
    return [`${label}: ${check.status || 'unknown'}; ${check.ran == null ? 'completed count unknown' : `${check.ran} run`}. Per-test progress was not captured in this receipt.`];
  }
  const lines = [
    `${label}: ${check.status || 'unknown'}; ${progress.completed} completed / ${progress.planned ?? 'unknown'} discovered; ${progress.skipped} skipped; ${progress.failures} failure and ${progress.errors} error event(s).`,
  ];
  if (progress.active) {
    lines.push(`Unfinished at the end of this check: ${progress.active.test} (${progress.active.elapsed_s.toFixed(3)}s since test start). This is not a failure verdict.`);
  } else if (progress.phase !== 'finished') {
    lines.push(progress.phase === 'discovery' ? 'Last reported phase: test discovery.'
      : 'Last reported phase: fixture work or between tests; no active test was reported.');
  }
  lines.push(`Progress snapshot age at check end: ${progress.last_report_age_s.toFixed(3)}s; ${progress.retained_events} recent events retained, ${progress.omitted_events} older events omitted. Aggregate counts are not truncated.`);
  if (progress.write_errors) lines.push(`${progress.write_errors} progress write error(s); counts describe the last captured snapshot.`);
  for (const row of progress.slowest || []) {
    lines.push(`Slow completed test: ${row.test} — ${row.elapsed_s.toFixed(3)}s wall / ${row.cpu_s.toFixed(3)}s runner CPU (${row.outcome}). Runner CPU excludes child processes.`);
  }
  lines.push('Diagnostic observations only. No deadline change or acceptance result is inferred.');
  return lines;
}
