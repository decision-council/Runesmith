# LOC1 Amendment 2 (before any session): disk floor on C:, workers, clean-up

Designer: Claude Opus 5.5 (the agent running LOC1). Written while the pool was being generated, before PROTOCOL.json, the dry run or any
LOC1 session exists. No outcome of LOC1 exists; nothing here depends on one.

What happened: free space on C: fell from about 7.8 GB (10:31Z) to about 0.75 GB (11:16Z). LOC1's own files on C: total about 0.55 GB
(pool, checkouts, generator worker copies); the rest is the system-managed page file, which grew to about 11.3 GB under memory pressure
(commit 16.2 of 19.9 GB at 11:18Z) and shrinks only on reboot. The brief's floor (keep C: above 5 GB) can therefore not be met by any
action of LOC1, and the protocol's start gate (no session starts while C: has under 5 GB) would start no session at all.

1. **Start floor on C: 700 MB** (was 5 GB). No session starts while C: has less; sessions already running finish. A session holds one
   copy of its repository snapshot (pygments 45 MB, sqlglot 16 MB, astroid 2 MB) plus, while judged, a second one, so at the floor ten
   running sessions can take C: down by at most about 0.5 GB, leaving it above about 0.2 GB in the worst case. RAM and D: floors unchanged.
2. **Primary workers 10** (was 12), for the same reason (fewer snapshot copies at once). The 8 gateway call slots stay the binding limit;
   the pilot's sessions spent most of their time waiting for a slot, so the expected loss of throughput is small. Replication: 1 worker.
3. **Clean-up after the pool exists, before the first session:** LOC1's checkouts (reproducible from the recorded tag and commit) and the
   generator's worker copies (`pool/scratch`) are deleted; the pool's snapshots and tasks are kept.
4. The lead investigator and the coordinator are told (STATUS.txt and the launch report): C: is below the brief's 5 GB floor because of the
   page file, not because of LOC1's files.
5. Reported as a deviation, with this amendment's digest, wherever LOC1 is reported.
6. **Pool cutoff 12:00Z.** The generators validate tasks one at a time after their kill-check phase, and sqlglot's (many dialect test
   files per target) had validated none by 11:40Z. To keep LOC1's end time, the pool is closed at 2026-10-06T12:00:00Z: a repository whose
   generator has finished contributes its manifest; one still running at the cutoff contributes exactly the tasks that had passed both
   controls by then (read from their HIDDEN.json, the generator's own validation rule) and its generator is then stopped by its exact
   process id (`loc1_run.py merge`). The selection rule (20 per repository, others fill, seeded ranks) is unchanged. The truncation is by
   time and takes validated tasks in the order their kill-checks finished (components were submitted in seeded order); no model and no
   person read a task.
