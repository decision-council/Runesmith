# U1-UPLIFT Amendment 3 (before any model session): more tasks, a fourth arm, both balances

Designer: Claude Opus 5.5 (integration operator), at the lead investigator's request to use the remaining credits for more data.
Written before any U1 evaluation session (no `EVAL_START_UTC.txt`, no `eval/`); the 30-task pool exists, unread; no outcome
of U1 exists.

1. **Tasks.** The original 30 tasks stay first in the queue, unchanged. After them come additional tasks: every further valid
   one-task-per-source-file task the pool generator yields from the same two repositories, up to 30 per repository in all, in a
   seeded order drawn before their generation and recorded in `SEEDS_AMENDMENT_3.json`. Validation stays mechanical.
2. **A fourth arm, R-B.** The released Core's repair organ at generation B (`gen-a4415db24a53`, SR5's Kaizen generation and
   SR7's predecessor), run exactly like R-C7 and R-g0.
3. **Queue and credit.** Within a task, all four arms run in HMAC-interleaved order on the same task revision. Tasks run in the
   order of point 1. Before each task the remaining balance is checked; a task is started only if the balance covers all four of
   its sessions at the observed per-session cost, so no task is left partial. Routes: Vercel's `gpt-oss-20b` while its balance
   covers a task, then OpenRouter's `gpt-oss-20b`; a route change happens only at a task boundary, so all arms of a task share a
   route. The route of every call is recorded. Transport censoring as the protocol defines.
4. **Analysis.** The analysed set is every task with all four sessions complete. Primary, unchanged: R-C7 > DIRECT, exact
   one-sided sign test on discordant tasks, alpha 0.025 (mirrored test and the fewer-than-4-discordant rule as declared).
   **Declared secondary confirmatory test:** R-C7 > R-B on the same tasks, the same test, alpha 0.025: a replication attempt of
   SR7's direction on public repositories. Both p-values are also reported against a Bonferroni threshold of 0.0125. The other
   secondaries stay descriptive (R-g0 vs DIRECT; R-C7 vs R-g0; per repository; per route; false promotions; censoring).
5. Reported as a deviation, with this amendment's digest, wherever U1 is reported.
