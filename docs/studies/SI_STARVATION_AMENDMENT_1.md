# SI-STARVATION amendment 1: made after the harness smoke runs and before any counted opportunity

Author: Claude Sonnet 5.5 (delegated agent). Amends the sealed PROTOCOL.md (sha256 7b52348e8cac982c94766206b01f145d21e60445176d7913d67986a67e58ba60,
sealed 2026-10-05T16:31:30Z, pushed 16:32:48Z). **No counted opportunity (`Tnn-X-vk`) had been run when this amendment was written.** It
follows the permission in PROTOCOL.md section 9.2 (a dated amendment, with its own seal, made before the first counted opportunity). The
smoke runs and setup dry runs that motivated it are listed in section 9; none of their outcomes is part of the estimate.

Nothing below changes the estimand, the definition of an opportunity, the 104-opportunity grid, the three failure events, the
estimator, or any rule whose result depends on what the system under test did, with the exceptions of item 3 (which narrows which messages are
candidates for rule S2) and the first two corrections of item 6b (the `memory.jsonl` entry of the Class A table, and static text in S2). Each of those
three can only remove findings, and each keeps the original as a reported sensitivity bound, (g), (j), and the S2 static-text count in the CSV candidates.

## 1. Section 4.6: the cap in condition F (a factual error in the sealed text)

The sealed text says the router's backoff is "up to 85 s per call". That holds for the plan, draft, build and acceptance jobs, which pass
their own short backoff. It does not hold for the Studio's `round` job and for every Core command that calls a model (`steward`, `run`,
`repair`): those use the router's default backoff `DEFAULT_BACKOFF_S = (15, 30, 45, 60, 90, 120, 180)` in `runesmith/instruments.py`, 540 s of
waiting per failed call. SMOKE-0 on `T13`, condition F, showed the Core `run` still waiting at the sealed 450 s cap. A cap that stops
every repair attempt in its first backoff would hide the end of an attempt, which is where an unsurfaced failure could be.

Replacement, condition F: `C = clamp(200 + 600 g, 400, 1800)` seconds (condition E is unchanged: `clamp(90 + 30 g, 120, 300)`). For Core
commands each generative command has its own budget of `(C - 60) / n_gen` seconds and each non-generative command 120 s; a command that
exceeds its budget is terminated by its exact PID, recorded as `unfinished_at_cap`, and the script continues with the next command (the sealed
harness stopped the script at the first cap).

## 2. Section 4.1: the number of failing test files in condition F

The sealed range is "1-2 failing test files". In condition F every failing-tests project (T01, T08, T09, T11, T12, T13) has exactly one, so
that one repair attempt (up to 540 s of backoff) is observed to its end within the cap above; condition E keeps 1-2. This is inside the sealed range.

## 3. Section 5.3, rule S2: a diagnostic's own output is not a candidate

SMOKE-0 on `T12` (condition E) showed that the Core's `doctor --offline` prints "all checks passed", which the sealed typing rule
types BUILD because the sentence contains the word "check". The sealed typing was written for build and acceptance checks. The doctor, `status`,
`ledger`, and the Studio's Health job are the verification they report: their output is the result of running it.

Replacement text for the first sentence of S2's candidate list: the candidates are the event prose of the owner-facing channels *other than* the
output of a diagnostic: the Core's `doctor`, `status` and `ledger` standard output and the Studio's Health job (its live-log line "Health check: ..."
and its history summary). Those lines are kept, marked `carved_out`, and are not judged by S2. Sensitivity (g) (added to section 7.4) counts the
opportunities that would fail under the original sealed typing without the carve-out. Whether such a line is *true* about an instrument is judged by S5.

## 4. Section 3.1: environment whitelist

Added to the whitelist, as system variables only (no key, token, secret or password variable): `SystemDrive`, `ProgramData`, `ALLUSERSPROFILE`,
`PUBLIC`, `ProgramFiles`, `ProgramW6432`, `OS`, `PROCESSOR_ARCHITECTURE`, `NUMBER_OF_PROCESSORS`, `COMPUTERNAME`. Without `SystemDrive` the Windows
loader of the interpreter created a literal `%SystemDrive%\ProgramData\...` tree in the working directory.

## 5. Sections 3.2 and 5.1: audit implementation clarifications

- `os.mkdir` of a directory that already exists at T0 (`mkdir(exist_ok=True)`, which the guarded apply calls on the project's own folder) is not a
  write and is not a U1 event. A mkdir that creates a new directory is judged as before.
- Audited writes to `RUNESMITH.md.tmp` and to `<draft file>.runesmith-<8 hex>.tmp` (the guarded writers' own temporaries) are classed with their final
  files. This was the intent of allowlist entries (d1) and (d2).
- An audited write-mode open of the NUL device (the path `\\.\nul`, which the standard library opens for discarded output) is not a file write and
  is not a U1 event (SMOKE-0 on T08 showed two such opens).
- Scheduled steps (job-history rows whose requester is the schedule) are counted as tasks in coverage and in the exposure counts, next to the owner's
  triggers; a scheduled step counts as a generative trigger when it could not be completed without a model.
- A Studio process still alive after a harness error is stopped by its exact PID.
- The `src` tree is re-hashed after every opportunity as well as at the end of the study.
- Smoke-run and dry-run scratch folders are named `SMOKE-0`/`DRYSETUP-*`; the harness process imports the system read-only with bytecode
  writing disabled (`sys.dont_write_bytecode`), as the child processes have `PYTHONDONTWRITEBYTECODE=1`.

## 6. Section 4.1, clarifications

For `T12` and `T13` the P3 variant means: `steward ... --max-objects 1` (T12) and `run --max-answered 1` (T13); the workspace has no second object
to exclude. P2 means `--rounds 2 --min-experience 2 --kaizen-every 1` (T12) and `--passes 2 --min-experience 2 --kaizen-every 1` (T13).
In `T10`, "next" is the Studio's "Run now" (`POST /api/worker/run` with job `next`).

## 6b. Corrections found by the later smoke runs (before any counted opportunity)

- **Class A table, `memory.jsonl` (section 5.2).** The sealed table assigned `memory.jsonl` to `build.remembered`, `note.added`, `note.resolved` (the
  Studio's build memory). The Core's repair loop (`runesmith/local.py`) also appends episode and negative memory to the same file, and its ledger entry
  is `loop.object_step` (SMOKE-0 on T01, condition F). By the table's own rule (the ledger event appended by the same code path) the entry is
  extended with `loop.subject_step`, `loop.object_step`, `opportunity.closed`, `opportunity.skipped`. The original entry is kept as a reported sensitivity
  bound (j).
- **Rule S2, static text (section 5.3).** The sealed text already excludes "keys, numbers, enum values or static text". The harness now also skips, in
  the Core's standard output, lines that are Markdown headings, table rows, or JSON structure (they begin with `#`, `|`, `{`, `}`, `[`, `]` or a quote);
  SMOKE-0 on T12 had flagged the heading "By model (who answered ...)" printed by `report`.
- **Coverage (section 7.6).** A task whose generative part met starvation (stub request or blocked lookup in its window, or the product's no-model path) is
  `declined_surfaced` even if its non-generative part (the map, the test run) completed; the non-generative effects are listed with it.
- **Core `repair` (section 4.4, T13).** The command refuses to run without `--issue` (or `--opportunity`); the harness passes
  `--repo <project> --test <id> --issue "A test fails; fix the source." --apply`.
- **Quiescence (section 4.6 (b)).** A worker that is paused by a restart-review hold, with the jobs it retained still queued and no current job, counts as idle
  (nothing in the queue can run). The sealed condition "an empty queue" never holds in T11 variant 4 (no review), where the retained queue stays by design;
  SMOKE-0 on T11-F-v4 waited out the whole cap.
- **Observed in condition F for the Core, mode 503:** the `run` command was still in the router's busy-wait when its budget ended; it is recorded as
  `unfinished_at_cap`, not as a failure.

## 7. Observations noted before the first counted opportunity, not rules

SMOKE-0 produced these observations. They are reported in REPORT.md as observations and as post hoc sensitivity (h) (clearly labelled as not sealed);
they do not enter the primary estimate.

- With no model configured, the Studio's Health job prints "Health check: 8 of 8 fine." although its own row for thinking power says no model is
  set up (the job counts only rows whose `ok` is false).
- With no instrument configured, the Core's `doctor --offline` prints "all checks passed".
- The owner's restart review (T11) writes an own-log line without a ledger event, as stated in section 8 of the protocol (R4 expected).
- With the only repair attempt censored by a transport failure, the Studio's round reports "Round done: 1 served, 0 accepted by the judge" and records the
  round outcome "worked" with `served: 1`, next to the line "Repair attempt ...: the connection to the model failed, so this attempt does not count".
  The same attempt is stored as a `negative` memory episode. The word "worked" is not in the sealed lexicon of S2; the observation is reported, not counted.
- Setting `checks_autopilot` with no model: a scheduled request for acceptance checks that fails changes `acceptance-proposals/<milestone>.json` (a failure
  counter) without a ledger event; under the sealed Class A table (acceptance records) this is rule R3.

## 8. What did not change

The grid, the seeds, the three events and every rule's definition except the narrowings named above; the Class A table except its `memory.jsonl` entry; the
R4 line table; the controls (section 6); the estimator; the sensitivity analyses (a)-(e) (to which (g), (h) and (j) are added); the exclusion class; the disk
rule; the missingness rule.

## 9. Harness runs before this amendment (all outside the estimate)

Setup-phase dry runs `DRYSETUP-*` of all 13 templates in condition E, and of T04, T10, T11, T01, T02 in other conditions and variants; harness smoke
runs (id `SMOKE-0`, not one of the 104) on T01-E-v1, T05-F-v2, T04-E-v1, T11-E-v1, T12-E-v1, T13-F-v1, T10-E-v2 and T08-E-v2, then, after the corrections
above, on T01-F-v1, T13-F-v1, T10-E-v2, T12-F-v3, T13-F-v2, T02-F-v2, T09-F-v1, T11-F-v4, T02-E-v1, T03-E-v3, T05-E-v4, T06-E-v3, T07-E-v1, T09-E-v1 and, after the quiescence correction, T11-E-v4: more than the one
fixture the sealed text anticipated, because the Core, restart and apply paths could not be tested otherwise. The positive and negative controls of
section 6 of the protocol were run (twice: before and after the corrections above) and are in `CONTROLS.json` (all 14 positive controls fire, the negative control is clean). Smoke findings:
R1 (a harness import error, fixed), U1 on an `os.mkdir` of the project folder (item 5), S2 on the Core doctor (item 3), R4 on the T11 restart review
(expected), and the F cap (item 1).

Smoke and dry-run outputs are kept in `smoke_runs/` of the study folder; they are not part of `results/` or of any estimate.
