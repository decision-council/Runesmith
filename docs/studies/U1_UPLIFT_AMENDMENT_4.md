# U1-UPLIFT Amendment 4, the last (before any model session): power, three rounds, the gate metric

Designer: Claude Opus 5.5 (integration operator), after an outside review of the test design. Written before any U1
evaluation session and before PROTOCOL.json is sealed; no outcome of U1 exists.

1. **Power, computed now.** From SR7's released per-task outcomes (`sr7_sessions.csv`), resampling 39 tasks with SR7's effect
   (C7 vs B): one round per arm gives power 0.27 for the exact one-sided test at 0.025; three rounds give 0.78 (2,000 seeded
   draws; script and seed in OPERATIONS_LOG.md). One round would make a null uninformative, so:
2. **Rounds.** R-C7, R-B and DIRECT run **three rounds** per task; R-g0 runs one round (descriptive only). Per task, all ten
   sessions run HMAC-interleaved, task by task in the queue order of Amendment 3 (the original 30 first, then the 9 further
   boltons tasks); a task starts only if the balance covers all ten of its sessions, so no task is partial. Routes and censoring
   as in Amendments 2 and 3.
3. **Statistic.** Both declared tests use SR7's statistic: per task, the mean over its three rounds of the paired difference;
   one-sided sign-flip test over tasks, exact enumeration, alpha 0.025 each (also reported against Bonferroni 0.0125).
   Primary: R-C7 > DIRECT. Secondary confirmatory: R-C7 > R-B (a replication attempt of SR7's direction). Mirrored tests
   declared. The minimum detectable effect at this size is reported with each result.
4. **Expectation stated before any outcome.** click (14 source files) and boltons (25) are small repositories. C7's accepted
   tiers mainly fix localization, which matters most in large repositories (SR7: 85 and 181 files), and SR5 found B's own rescue
   works in small ones; the C7-vs-B effect is therefore expected to be smaller here than in SR7. No expectation is stated for
   C7 vs DIRECT (no prior data with this model).
5. **Gate metric, descriptive, zero cost.** Per arm: sessions whose final edit passed the public tests but failed the hidden
   judge (false promotions). If the session records hold each edit's content, also: DIRECT's first edit applied unchecked and
   judged by the hidden tests (a "first answer, no checking" proxy; tests only, no model call).
6. **Naming.** DIRECT is always described as "the same model with a simple fixed script in place of Runesmith's repair organ",
   never as "without Runesmith": it runs in the same kernel with the same envelope and judge.
7. **U3-POLYGLOT is withdrawn**, sealed but not run: implement-from-stub exercises make localization trivial, so the comparison
   could not show what Runesmith's repair organ does. No U3 checkout, task or session ever existed; no outcome exists.
