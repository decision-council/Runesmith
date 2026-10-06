# LOC1: generation C7 against the shipped organ g0 and against a trace-aware model-free localization arm, on large public repositories

Stage-0 declaration, written on 2026-10-06 before any LOC1 checkout, task or session exists. Designer: Claude Opus 5.5 (the agent running
LOC1), at the lead investigator's approval (Lars: "the result is reported whatever it shows"; free routes only, no paid spend). This file is
sealed by its SHA-256 in `SEAL.txt` together with the files it names (seeds, HEUR organ, power computation, route probes, pilot) and pushed
to the lab's private repository (branch `u1-protocol`) BEFORE any repository is checked out or any task generated. A second seal,
`PROTOCOL.json` (stage B, in `SEAL_STAGE_B.txt`), binds the pool, the selected tasks, the queues and the runner code after the pool is
generated and BEFORE the first session; it is pushed too. Amendments are allowed only before the first session and are reported.

## Question

On fresh synthetic single-line regressions in large public Python repositories, where C7's navigation index does not fit its cap (so its
file-ranking tiers decide what the model sees), and with the same free model and an identical envelope:

1. **Primary:** does Runesmith's self-improved repair organ, generation C7, repair more tasks than the organ it shipped with, g0?
2. **Secondary (confirmatory):** does C7 repair more tasks than HEUR, the strongest model-free composition of the failure text and the
   execution trace that the designer could write (the record's comparator rule, paper sections 5.1.2 and 6.1)?

Why: SR7 (C7 57/162 against B 35/162, p = 0.000845) compared C7 with B, not with g0 (SR5 did not show B above g0), and no arm composing the
failure text AND the trace was ever run. The October studies U1, U2 and U2b used small repositories (click, boltons) where the navigation
index fit in view (the 12,000-byte cap never bound), so C7's ranking tiers could not act there; in SR7 the cap bound in 54 of 54 tasks
(`D:\oob\paper\EXISTING_CONTROL_EVIDENCE.md`, read 2026-10-06).

## Arms (primary model), each 3 rounds per task

- **R-C7:** the released Core's repair organ at generation C7 (`gen-e12d76179a3d`), byte-identical to U1/U2b's copy, in U1's frozen Core.
- **R-g0:** the same, at the shipped default generation g0, byte-identical to U1's copy.
- **HEUR (new):** `heur_organ/heur.py`, written for LOC1 next to SR6-W's DIRECT and fixed before this seal (digest in `SEAL.txt`). It spends
  one traced run of the failing tests (the kernel affordance C7 also uses) and no model call on localization. It ranks the source files by
  (a) the trace: files whose function or method BODIES executed during the failing test (import-time lines do not count), (b) the
  test-to-module mapping (the failing test file's stem and folders, the test class and test name, against each file's path words),
  (c) symbols named in the failure text (dotted module paths, class and function names, matched exactly), and (d) executed functions whose
  names match the test name. The model sees the top-ranked files up to the same 32,000-byte edit cap: a file of at most 3,000 characters
  whole, a larger one as its module header plus every function whose body executed (name-matched first), plus a short localization note
  naming the ranked files and their executed functions. All five model calls go to edits, with DIRECT's exact-edit rule and DIRECT's
  public-test feedback loop. It never tries a candidate fix without the model (no mutation search). If the trace is empty it falls back to
  the failure-text tiers with whole files, as DIRECT does. Development (model-free, `HEUR_DEV_CHECK.txt`): on 30 tasks of SR7's already
  analysed pool, the mutated line was inside HEUR's first edit view in 26 of 30 tasks against 15 of 30 for DIRECT; one parameter was
  changed once (whole-file limit 8,000 to 3,000 characters), then frozen. HEUR was never run on a LOC1 task before this seal.
- DIRECT (SR6-W's failure-text-only script) is not run: HEUR supersedes it as the comparator rule's arm. Nothing about R-C7 or R-g0 is
  tuned for LOC1.

All arms run in the same kernel, with the same envelope (SR7's: at most 5 model calls, 8,192 output tokens, 45 signal runs, 64,000 request
bytes, 1,800 s per session; caps 12,000 bytes navigation, 32,000 bytes edit), the same public signal and the same judge (the hidden targeted
test files on a fresh pristine snapshot: SR7's strict success).

## Models and routes (free only; cost 0)

- **Primary model: `openai/gpt-oss-20b`** (SR7's repair model) on **NVIDIA's free endpoint** (`nvidia:openai/gpt-oss-20b`), provider-default
  reasoning, through the Milliner gateway. Every other route serving gpt-oss-20b was checked before this seal (`PROBE_RULE.md`, written before
  the probes; receipts in `ROUTE_PROBES.json`): OpenRouter's free gpt-oss-20b answered `model_not_found`; Groq answered `bad_request` to a
  full-size request (its free tier allows 8,000 tokens a minute, below one full-size request); Vercel is paid. NVIDIA alone carries the
  primary model. A call that reports a cost above zero stops all new sessions.
- **Replication model: `gemini-3.5-flash`** (Google AI Studio free tier) on three separate projects (`gemini`, `gemini2`, `gemini3`; each
  project a route with its own free daily allowance of about 250 requests). Its full-size probes answered with the asked model at cost 0.0 on
  all three. It runs **R-C7 and R-g0 only**, 3 rounds, on the same tasks, in the same task order; all sessions of a task run on one project
  (task position modulo 3). It has its own provider quota but shares the gateway's per-caller limit (below), so it runs with ONE worker in
  all, to take as little as possible from the primary. Its daily allowance and that one worker cover roughly 30 of the 60 tasks by the stop
  time; the tasks it completes are analysed, the rest are reported as not run.

## Repositories (rule fixed before any checkout)

Ordered candidates (large public Python projects never used by the program): `pygments/pygments`, `Textualize/rich`, `tobymao/sqlglot`,
`pylint-dev/astroid`, `pydantic/pydantic`, `pallets/werkzeug`, `pallets/jinja`, `sqlalchemy/sqlalchemy`, `sympy/sympy`,
`networkx/networkx`. For each in order: its latest stable release tag (the highest version among tags of the form `vX.Y[.Z[.W]]` or
`X.Y[.Z[.W]]`, read with `git ls-remote` on 2026-10-06), a depth-1 checkout of that tag. It qualifies if all three hold:

1. **Suite:** its own default pytest invocation (`python -m pytest -q -p no:cacheprovider` at the root) exits 0 within 1,200 s under U1
   Amendment 1's interpreter definition: the machine's Python 3.13.14 with pytest 9.1.1, nothing installed or downloaded after checkout,
   the package registered by a name-and-version `dist-info` stub, a top-level package moved under `src/` without changing any byte.
2. **Layout:** the pool generator's requirement, a top-level `tests/` folder holding `test_*.py` files, and `src/` after the move.
3. **Size:** the navigation index exceeds the cap. Measured as: C7's own `source_index` over the prepared `src/` tree, rendered in C7's own
   `navigation_packet` with an EMPTY issue, in canonical JSON bytes, is above `nav_cap_bytes` = 12,000. (With any real issue the packet only
   grows, so the index is truncated in every task of a qualifying repository.) Reference values: SR7's SignalHat 13,391 bytes, SocialHat
   31,539 bytes (`HEUR_DEV_CHECK.txt`).

The **first three** qualifying repositories are used. The check and its receipts are `loc1_run.py qualify` -> `REPOSITORY_RULE_CHECK.json`,
`REPOSITORIES.json`. Checkouts, pool and temp files live under `C:\Users\aithi\oob-overflow\loc1`.

## Tasks

- Family: SR7's: synthetic single-line regressions (comparison swaps, and/or exchanges, `not` removal, sign changes, integer off-by-one,
  flipped boolean returns) in test-covered function bodies, one task per source file, by the program's existing pool generator with its
  existing validation (the mutant fails at least one targeted test; the pristine source passes; positive and negative controls).
  `loc1_generate_pool_tasks.py` is a copy of U1's generator (digest in `SEAL.txt`) with declared changes only: folders; repositories read from
  `REPOSITORIES.json`; components submitted in `HMAC(generation_seed, repo|path)` order so that the per-repository wall cap, if reached,
  leaves a seeded random sample of files; one process per repository then a merge; wall cap 1,500 s per repository, 4 workers, baseline
  timeout 900 s. Seeds: `SEEDS.json`, drawn 2026-10-06T10:19:16Z before this seal and before any checkout.
- **Size: 60 tasks**, 20 per repository (a repository with fewer valid tasks is filled by the others in rank order), ranked by
  `HMAC(pool_seed, "pool|" + task_id)`; queue order by `HMAC(order_seed, "task|" + task_id)` (`loc1_run.py select` ->
  `POOL_DECISION.json`). Tasks are handled mechanically only; **no person or model reads a task, its issue or any outcome before the
  analysis.** The selection records, per task, that C7's module-path tier cannot fire (its regex names only Runesmith's own two
  development repositories).
- Public information per task, identical for every arm: failing test identifiers and a sanitized failure excerpt (SR7's issue template).

## Power (computed before this seal: `POWER_PRESEAL.json`, `loc1_power.py`)

U1/U2b's plug-in simulation with the same exact sign-flip test: N tasks, comparator per-task rates resampled from a prior pool, treated
rate = comparator + 0.15 (capped at 1), 3 rounds, 2,000 simulated studies per N, seeded with LOC1's analysis seed. Power at one-sided alpha
0.008333 (the Bonferroni level below):

| prior comparator rates | N = 40 | N = 50 | N = 60 | N = 70 |
|---|---|---|---|---|
| SR7's B arm (54 tasks, large repositories, mean 0.22) | 0.76 | 0.86 | **0.93** | |
| U2b's medium DIRECT arm (20 tasks, mean 0.38) | 0.65 | 0.79 | **0.88** | 0.92 |
| SR7's paired C7-B outcomes resampled (observed +13.6 points) | 0.64 | 0.79 | **0.86** | 0.92 |
| U2b's medium C7 arm as comparator (mean 0.55, least favourable) | 0.47 | 0.58 | **0.70** | 0.79 |

60 tasks give at least 0.86 under the three priors closest to g0 on large repositories with this model (g0's own rate on such tasks is
unknown; SR7's B, g0's successor, is the closest) and 0.70 under the least favourable prior. **Expected at the stop time:** at the
pilot's rate (about 100 to 115 primary sessions an hour with the replication's one worker beside it) and a start at about 11:45Z, about
450 to 510 of the 540 primary sessions, i.e. about 50 to 56 complete tasks; at 50 tasks the power is 0.86, 0.79, 0.79 and 0.58 under the
four priors. The analysed set is whatever is complete at the stop; the queue order makes the earliest tasks complete first. The replication model's power is lower (about
30 tasks within its free allowance: 0.46 to 0.57 under the same priors); a null there is uninformative and is reported as such.

## Throughput pilot and schedule

Every LOC1 call goes through the Milliner gateway under the operator's token, whose cap is **8 concurrent model calls** for all of that
caller's traffic (`C:\dev\Milliner\config\milliner.toml`, `[[tokens]] agent = "operator"`, `max_concurrency = 8`); LOC1 does not
change it. That cap, not NVIDIA's 40 requests a minute, bounds throughput. Before this seal, a pilot measured the primary route at 16 workers
on SR7's analysed pool (not LOC1 tasks; sessions not judged; receipts reduced to timing and deleted, no outcome kept or read):
`PILOT_W16.json`: 28 sessions in 18.3 minutes including ramp-up and ramp-down (92 sessions an hour; about 120 an hour in the saturated middle), 3.5 calls per session, median call latency 105 s of which most is waiting for one of the 8 slots, no censoring, free RAM never below 1,856 MB. LOC1 runs **12 workers** on the NVIDIA route (enough to keep the 8 call slots busy while other sessions run
tests) and **1 worker** for the replication model. Sessions start in queue order; within a task the sessions (arms x rounds) are in HMAC
order (`HMAC(order_seed, "loc1|<model>|<task>|<arm>|<round>")`), so arms and rounds are interleaved in a seeded order. LOC1 has strict
priority on every gpt-oss-20b route.

## Execution and stopping rule

- **Stop.** The evaluation ends at whichever comes first: every queued session written or logged as not run, or **2026-10-06T16:15:00Z**.
  After the stop time no session starts (re-queue included); sessions already started finish (each is bounded by its 1,800 s wall). The
  chain then runs the analysis, an independent recomputation and the report at once.
- **Only tasks with all their sessions complete are analysed**, per model (primary: 9 sessions, 3 arms x 3 rounds; replication: 6). A task
  with a missing or censored session is excluded and reported with the counts. Nothing is imputed.
- **Censoring.** A session whose model route failed by transport (`censored_transport`) is never scored. Each route's queue ends with one
  re-queue of its censored sessions (key suffix `-requeue1`), if before the stop time; the first receipt is kept in `eval_censored`.
- **Guards.** After 4 consecutive transport-censored sessions on a route, no session starts on it for 300 s; the sixth such pause stops the
  route. Five harness errors in a row halt a model (reported, never scored). Before every session start the run waits while free RAM is
  under 400 MB, free space on D: under 300 MB or on C: under 5 GB. No Docker. Sessions not run are logged in `NOT_RUN.jsonl`.
- **No outcome is read before the end marker.** Progress is monitored by counting session files and call-log lines only; `STATUS.txt`
  carries routes, workers, sessions per hour and the expected end.

## Statistic and declared tests (SR7's; imported code, `u1_run.signflip`, `task_sums`, `test_pair`)

Per model, on its complete tasks. For task t, round k: s(arm, t, k) = 1 if the judge's strict tests pass, else 0; d_t = sum over k of
[s(a, t, k) - s(b, t, k)] (the per-task mean difference is d_t / 3); T = sum of d_t. Exact one-sided sign-flip test over all sign
assignments of the nonzero |d_t|: p(a better) = P(T* >= T); mirrored p(b better) = P(T* <= T).

| test | model | a vs b | role |
|---|---|---|---|
| primary | gpt-oss-20b | R-C7 > R-g0 | confirmatory |
| secondary | gpt-oss-20b | R-C7 > HEUR | confirmatory |
| replication | gemini-3.5-flash | R-C7 > R-g0 | confirmatory replication of the primary |

**Bonferroni over the three declared tests: alpha = 0.025 / 3 = 0.008333 each** (one-sided; family-wise 0.025). Verdict per test: fewer
than 4 tasks with a nonzero d_t: NO_DIFFERENCE_DETECTABLE; else p(a better) <= 0.008333: PASS; else p(b better) <= 0.008333:
`<b>_BETTER` (the mirrored result, reported with the same prominence); else NULL. Every p is reported exactly, also against 0.025.
A recomputation from the session receipts by a different routine (generating polynomial) must agree before the report is written.

**Declared descriptive (no test claim):** HEUR vs g0 (both directions); per-repository counts; localization checks (the share of C7
sessions whose navigation index was truncated; per arm, the share of sessions whose edit view held the mutated file); false promotions
(public pass, strict fail); organ errors; calls and seconds per strict success; censoring by arm and route; the post-hoc minimum
detectable effect. Exact (Clopper-Pearson) intervals treat sessions as independent and are descriptive only.

## Tier ablation

Not part of LOC1 (the coordinator's ruling on 2026-10-06: it must not cost LOC1 power or time). If run, it is a separate protocol
(ABL1) on LOC1's task pool, sealed and pushed before its own first session, using only capacity LOC1 leaves idle. Known before any outcome:
C7's two module-path tiers (Kaizen attempts 5 and 6) cannot fire on these repositories; their contribution is zero by construction.

## What a result licenses

A primary PASS licenses: "On fresh synthetic single-line regressions in three large public Python repositories, where C7's navigation
index exceeded its cap, with one free model (gpt-oss-20b) and an identical envelope, Runesmith's self-improved repair organ (C7) repaired
more tasks than the organ it shipped with (g0)." A secondary PASS adds: "and more than the strongest model-free localization composition of
the failure text and the trace the designer wrote (HEUR)"; a `HEUR_BETTER` or NULL secondary says that a hand-written localization rule
matched or beat the organ's learned gain on this family. Neither licenses natural-bug repair, other task families, other models (except as
the replication shows), or cost claims. Every number of every arm is reported, whatever it shows.

## Outputs

`PROTOCOL.md`, `SEAL.txt`, `PUSH_RECEIPT.txt`, `PROTOCOL.json`, `SEAL_STAGE_B.txt`, `PUSH_RECEIPT_B.txt`, `REPOSITORY_RULE_CHECK.json`,
`REPOSITORIES.json`, `POOL_DECISION.json`, `EVAL_START_UTC.txt`, `EVAL_END_UTC.txt`, `eval/` (session receipts), `NOT_RUN.jsonl`,
`CALLS_LOG.jsonl`, `RESULT.json`, `RECOMPUTE.json`, `REPORT.md`, `loc1_sessions.csv`, `STATUS.txt`. Nothing under `D:\oob\paper` or in
`D:\Runesmith`'s main working tree is touched.
