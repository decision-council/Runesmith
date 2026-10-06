# LOC1 Amendment 3, the last (before any session): workers back to 12, stop time 16:20Z; the pool as closed

Designer: Claude Opus 5.5 (the agent running LOC1). Written at about 12:05Z, after the pool was closed and the no-model dry run, before
PROTOCOL.json and before any LOC1 session. No outcome of LOC1 exists.

1. **Pool (facts, no change of rule).** At the 12:00Z cutoff (Amendment 2, point 6) pygments' and astroid's generators had finished
   (26 and 20 valid tasks); sqlglot's was stopped at 12:00:17Z by its exact process id with 13 tasks that had passed both controls.
   The pool holds 59 valid tasks, so the selection rule (20 per repository, others fill) selects all 59 (pygments 26, sqlglot 13,
   astroid 20), one fewer than the protocol's 60. The dry run (`DRYRUN_NO_MODEL.json`, stand-in model, no call) ran every arm to its end
   on one task per repository, the judge ran, and C7's navigation index was truncated in all three (astroid 60 of 96 rows delivered,
   pygments 84 of 338, sqlglot 20 of 180).
2. **Primary workers 12** (Amendment 2 had cut them to 10 for disk space): free space on C: recovered to 6.2 GB at 12:00Z once the
   generators ended. The 700 MB start floor on C: stays.
3. **Stop time 2026-10-06T16:20:00Z** (was 16:15Z): the first session starts at about 12:10Z instead of the planned 11:45Z because the
   pool took longer to validate; five minutes are added and no more, so that the analysis still ends by about 17:00Z.
4. Reported as a deviation, with this amendment's digest, wherever LOC1 is reported.
