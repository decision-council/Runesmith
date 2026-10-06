# NATURAL-BUGS: Runesmith's repair organ C7 against the shipped organ g0 on natural bug-fix tasks

Stage-0 declaration, written 2026-10-06 at about 10:35Z, before any natural task is mined. Designer: Claude Sonnet 5.5 (the agent running the study), on the
instruction of the lead investigator (Lars), who approved the study ("reported whatever it shows"; cost 0). This file is sealed by its SHA-256 in
`SEAL.txt` and pushed to branch `u1-protocol` of the lab's private repository before the first task is mined, so the push time is an outside timestamp.
**The seed of every ordering below is this file's SHA-256** (the 32 bytes of the digest are the HMAC key), so it cannot be chosen after the fact.

This is the registered follow-up to LOC1 (a sealed C7-vs-g0 study on large repositories with synthetic mutants). It is sealed before LOC1 has a
session or a result: LOC1's `STATUS.txt` (updated 2026-10-06T10:10Z) reads "phase DESIGN (no session yet; no model call yet)". Results of the two studies
are reported separately and are not pooled.

## Question

On natural bugs, that is real historical bug-fix commits of public Python repositories (not injected mutants), does Runesmith's self-improved repair
organ C7 repair more tasks than the shipped organ g0, with the same model, the same envelope and the same judge?

Reviewers' objection that this answers: Runesmith's sealed evidence so far uses synthetic single-line mutants. C7's ranking tiers (test names to module
names, executed files) change what the model sees only when the navigation packet is truncated at the kernel's navigation cap. **The navigation cap is
`nav_cap_bytes` = 12,000 bytes (kernel envelope, `opportunity.py`); the 32,000-byte cap is the edit cap.** In U1, U2 and U2b the repositories were too small
for the navigation cap to bind. This study therefore uses only repositories and tasks where it binds strongly (rule below).

## Arms, model, route, envelope

- **R-C7:** the released Core's repair organ at generation C7 (`gen-e12d76179a3d`; `repair.py` sha256 `d70bff99d6afcdc44db4de2f5b1ab06d5bbd7e6b0979177e092e688a1b63b2a5`).
- **R-g0:** the shipped default generation g0 (`gen-e510c73e230f`; `repair.py` sha256 `140bae1ac6058635b5ce3b5c9e3d765025fc54657e5de06e747f8b5ed1d9c71c`).
- Both run in U1's frozen Core (`CORE_MANIFEST.json` sha256 `1612274ab7e2001739c84f6f37af7716b8eb1b3e026e09521e49ecd1381de838`), organs byte for byte as in U1/U2b.
- Model: `gpt-oss-20b`, free route `nvidia:openai/gpt-oss-20b` through the lab's local gateway (`http://127.0.0.1:8765`), the route of U2b's medium model (probed
  free on 2026-10-05) and LOC1's primary route. **Cost 0:** any call that reports a cost above zero, or is answered by another provider, stops all new
  sessions. No paid route, no author model. No new probe is made by this study; the first session is the check.
- Envelope, as SR7's and U1's: at most 5 model calls, 8,192 tokens, 45 signal runs, 64,000 request bytes and 1,800 s per session; navigation cap 12,000 B,
  edit cap 32,000 B; provider-default reasoning.
- Rounds: 3 per arm and task (6 sessions per task). Within a task the six sessions run in HMAC order (SHA-256 HMAC keyed with the seed over
  `natural|order|<task>|<arm>|<round>`), so arms and rounds are interleaved.

## Repositories and the navigation-index size rule

- **Rule (measured with C7's own code):** for a task, `canonical_bytes(navigation_packet(issue, source_index(files, sizes)))`, with the functions of C7's
  `repair.py`, on the task's parent source is the size of the whole-index navigation packet. **The cap binds strongly when this is at least 18,000 bytes**
  (1.5 x the 12,000-byte cap: at most about two thirds of the index rows reach the model). g0's `source_index` is identical (diff silent).
  **The 18,000-byte threshold was set after the whole-index sizes at HEAD had been seen** (counts and sizes only, no task content, no outcome): it keeps `astroid` (20,046 B) and leaves out `rich` (12,180 B).
- **Repository list**, ordered, fixed now: `yt-dlp/yt-dlp` (package `yt_dlp`, tests `test/`), `PyCQA/astroid` (`astroid`, `tests/`), `pygments/pygments` (`pygments`,
  `tests/`), `openai/openai-python` (`src/openai`, `tests/`), `anthropics/anthropic-sdk-python` (`src/anthropic`, `tests/`). They are the repositories of a
  pre-seal feasibility list whose whole-index packet at HEAD (stub issue) is at least 18,000 bytes: 127,440 / 20,046 / 40,919 / 328,591 / 278,725 B.
  Considered and left out by that measurement: `Textualize/rich` (12,180 B) and `docker/docker-py` (9,809 B). `FEASIBILITY_PRESEAL.json` (sha256
  `c101b46f5990682a3b8e527141455bfbda3535b00ef1d3cb5900cae8a8b7f3ad`) holds, per repository, counts only (commits in the window, subject matches, structural candidates),
  the index size at HEAD and a collect-only run of the tests at HEAD; no task, diff, message or test output was read. Collect-only at HEAD failed for pygments (1 error),
  openai and anthropic (a module the machine lacks, needed by their current test configuration), and docker-py; this is reported, not a rule: per-task validation decides, and an
  older commit may run where HEAD does not.
- Excluded repositories (used for the shake-out of the miner before this seal, in a throwaway folder): `pallets/click`, `mahmoud/boltons`.

## Task mining rule (fixed now; implemented in `natural_mine.py`, sha256 `de310c8a94fa55d7c790ee3dde95b6173828292f94b1597230891deb26901ecf`)

Candidates, per repository: non-merge commits reachable from the default branch's HEAD at clone time, with committer date from 2023-01-01T00:00:00Z to
2026-09-30T23:59:59Z, whose **subject line matches** `\b(fix(e[sd]|ing)?|bug ?fix(es)?|regression)\b` (case-insensitive), and which, by `git log --name-status --no-renames`:
(a) change **exactly one file under the package directory**, with status M, a `.py` file; (b) add or modify (A or M) between 1 and 3 test files, `.py` files named `test_*.py` or `*_test.py` under the
repository's top-level test directory; other changed files (documentation, changelog, configuration, test data) are allowed and stay in their fix-commit state;
(c) the source file's diff against the first parent has **1 to 10 changed lines** (`git diff --numstat`: added plus deleted).

Per-task validation, mechanical, in this order (the first failing check rejects the candidate; the log keeps only the reason code and counts):
1. the fix commit's tree is extracted (`git archive`, without `.git`, `.github`, `docs`, `doc`, `.devcontainer`); a package at the top level is moved under `src/` with no source byte changed
   (U1 Amendment 1), and a dist-info stub (`<name>-0.0.0.dist-info`) is written at the root; **a package containing a directory named `test` or `tests` is rejected** (it would expose judge tests to the organs);
2. **positive control:** the commit's test files pass (exit 0, skips allowed) on the fix tree, in at most 60 s;
3. **negative control:** with the one source file replaced by its first-parent version, the same test files **exit with code 1** (as in U1; an import or collection failure, exit 2 or 4, is rejected)
   in at most 60 s, and at least one `FAILED` test id is parsed (the visible failure signal follows U1's harness: `build_issue_text` of the failing ids and a sanitized excerpt);
4. the file is in the navigation index (at most 120,000 bytes and parseable: otherwise it is unreachable for both organs);
5. **the navigation-index size rule:** the whole-index packet with the task's real issue is at least 18,000 bytes;
6. the public signal as the harness runs it (the failing ids, `-q -p no:cacheprovider -x`) passes on the fix tree (so a public pass is reachable).

Tests run under the machine's Python 3.13.14 with pytest 9.1.1 and the kernel's invocation (`PYTHONPATH` = `src`, the snapshot root; no addopts override), offline: proxy
variables point to a closed port (raw sockets are not blocked). A repository whose pytest configuration needs a plugin or module the machine lacks fails validation by itself.

## Selection and stopping rule

- Per repository the candidates are ordered ascending by HMAC-SHA256 (key: the seed) over `natural|<repository key>|<full commit sha>`. The miner takes the next valid task from each
  repository in turn, in the declared repository order (round robin), until **30 tasks** are accepted. A repository stops contributing after **40 validations** (candidates that reach step 1 count; those
  rejected by the numstat rule do not) or when its list is exhausted; the others continue. If fewer than 12 valid tasks exist at the end, the study is declared **not run** (pool too small) and reported with the counts; a pool of 12 to 29 tasks runs as mined, and the post-hoc minimum detectable effect for that size is reported.
- Nobody and no model reads a task's issue, source, test, diff, commit message or outcome before the analysis; the miner logs reason codes and counts only (`MINING_LOG.jsonl`).
  The miner was shaken out before the seal on the excluded repositories, where its output was read; the dry run on the real pool prints statuses only.
- The task is the fix commit with the fix's source change reverted; the judge is the commit's own test files on a fresh snapshot with the candidate's `src/` (U1's evaluator, strict: exit 0, no timeout, 180 s limit);
  the test files are in the checkout but only `src/` files are shown to the organs (as in U1).

## Run schedule (LOC1 has strict priority; nothing here may slow it)

- Mining and setup need no model call and run now, one test process at a time, waiting while free RAM is under 400 MB or free space on C: under 5 GB, **and waiting while LOC1's sessions run** (the miner reads LOC1's `EVAL_START_UTC.txt`, `EVAL_END_UTC.txt` and `STATUS.txt`; LOC1 targets a start about 12:30Z); clones and the pool are on C: (`C:\Users\aithi\oob-overflow\natural`);
  D: holds only small text files and stays above 300 MB.
- Sessions: only on capacity LOC1 leaves idle. **While LOC1 is not finished: one worker;** a session starts only when the route's gate at the gateway (`GET /v1/status`) shows no queue and at least two free slots (the slots are the smaller of the gate's concurrency and the 8 concurrent calls that the operator token allows for all its traffic, which LOC1 shares: LOC1 runs 12 workers for those 8 slots, so a queue is expected for as long as LOC1 runs);
  on a 429, 5xx, timeout or transport failure on one of this study's calls the study backs off 15 minutes, and on the second such event it holds all new sessions until LOC1 is finished (a session
  that has started finishes). LOC1 is finished when `D:\MillinerOS\experiments\RUNESMITH-LOC1-2026-10-06\EVAL_END_UTC.txt` exists, or the `phase` line of its `STATUS.txt` begins with ENDED, DONE, FINISHED or COMPLETE (not ANALYSIS: replication sessions may still run), or the
  operator says so in a control file. **After that: up to 3 workers.** The operator may lower the worker count or pause, never raise it above these limits.
- Order: task-major (all six sessions of a task, then the next task, tasks in acceptance order); sessions already started finish.
- Quota guard as in U2b: after 4 consecutive transport-censored sessions no session starts for 20 minutes; the third such stop is final. Censored sessions are re-queued once at the end; never scored.
- **Stop time: 2026-10-07T06:00:00Z** (no session starts at or after it). **Only tasks with all six sessions judged are analysed**; others are reported as excluded with counts; nothing is imputed.
- Expected: because LOC1 saturates the 8 call slots, the first session is likely only after LOC1 ends (stop time 16:15Z, last session about 16:45Z), so about 17:00Z; the 30 tasks (180 sessions, about 4 minutes each, 3 workers) then finish about 21:00-22:00Z.

## Primary test

Endpoint: strict success per session. For task t and round k, s(arm,t,k) = 1 if the judge passes. d_t = sum over k=1..3 of [s(R-C7,t,k) - s(R-g0,t,k)] (the per-task mean difference is d_t/3).
**Statistic (SR7's, imported unchanged as `u1_run.signflip`, `task_sums`, `test_pair`): exact one-sided sign-flip test of T = sum d_t over the complete tasks.** p(C7 better) = P(T* >= T) over all sign
assignments of the nonzero |d_t|; alpha = 0.025. Verdict: fewer than 4 tasks with nonzero d_t: NO_DIFFERENCE_DETECTABLE; else p(C7 better) <= 0.025: PASS; else the mirrored p(g0 better) <= 0.025: G0_BETTER; else NULL.
No other test is registered. The sign-flip over tasks treats the three rounds of a task as one unit.

**Power, computed before the seal** (`natural_power.py`, sha256 `9a487c59a433289032e64eff25d8fe0a552d38845b777c1815ba647e6984d017`; `POWER_PRESEAL.json` sha256 `a74173908c0572548659e5787e4333d6974640f8e8cc34a479a1b5a3e9ec244d`).
U1's simulation (power 0.80, one-sided alpha 0.025, 1,000 simulated studies per step of 0.02, U1's analysis seed) with per-task comparator rates drawn from a Beta distribution whose intra-task correlation is
estimated from U2b's gpt-oss-20b sessions (rho = 0.70: tasks are largely all-or-nothing), the treated rate = comparator + delta. **With 30 tasks x 3 rounds the minimum detectable absolute gain in the per-session
success rate is 0.18 if g0 succeeds at 0.28 (g0: SR5 50/180, U1 round 1 5/17), 0.16 at 0.20 and 0.14 at 0.10** (24 tasks: 0.20 / 0.18 / 0.16; 36 tasks: 0.16 / 0.14 / 0.12). A smaller C7 advantage is not
detectable here, and a null is not evidence that none exists; the report states the post-hoc value from the observed rates next to every null.

## Secondary, descriptive (no test, no claim of a test)

Per arm and task: whether the navigation cap bound in the session (the `navigate` mark: `indexed` and `delivered` rows) and the task's whole-index packet size (mining receipt); strict successes, public passes, false
promotions (public pass, strict fail), organ errors, calls and seconds; per-repository counts; the sessions where g0's navigation failed; exact (Clopper-Pearson) intervals that treat sessions as independent (rounds of a task are not).

## What a pass would and would not license

A pass licenses: "on natural bug-fix tasks (single-file, 1-10 line fixes with a test in the same commit) in public Python repositories large enough that the navigation index exceeds the cap, with one free
20B model, Runesmith's self-improved repair organ C7 repaired more tasks than the shipped organ g0." It does not license general uplift over the model alone, other models, other languages, bugs without a
same-commit test, larger fixes, or cost claims. **Limits stated now:** the public repositories and their fixes are probably in the model's training data (this affects both arms equally); tasks are those whose tests
run under this machine's interpreter and installed packages offline (a selection toward self-contained test suites); the task unit is the fix commit, and one repository (`yt-dlp`) may supply many of them. A null or a reverse
result is reported with the same prominence. Both arms are Runesmith organs; a model-free localization arm is not part of this study.

## Amendments, outputs, receipts

Amendments only before the first session, each a new sealed file with its own digest. After the mining and before any session, `PROTOCOL.json` binds this file's digest, the pool (per-task digests), the miner and runner code, the frozen Core, the organs,
the route, the queue and the stop time; its digest is pushed to the same branch before the first session. Outputs in `D:\MillinerOS\experiments\RUNESMITH-NATURAL-2026-10-06\`: `SEAL.txt`, `PUSH_RECEIPT.txt`, `FEASIBILITY_PRESEAL.json`, `POWER_PRESEAL.json`,
`MINING_LOG.jsonl`, `POOL_DECISION.json`, `PROTOCOL.json`, `DRYRUN_NO_MODEL.json`, `eval/` (session receipts), `CALLS_LOG.jsonl`, `NOT_RUN.jsonl`, `EVAL_START_UTC.txt`, `EVAL_END_UTC.txt`, `SPEND_RECEIPT.json`, later `RESULT.json`, `RECOMPUTE.json`,
`REPORT.md`. The pool (tasks, snapshots) is on C: and is regenerable from the repositories, this protocol and the miner. Nothing under the paper's folders or another study's sealed files is touched.
