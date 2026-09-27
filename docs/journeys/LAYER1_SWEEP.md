# Layer 1 switch sweep: first full run

Run: 2026-09-27T22:41Z, on the working tree after commit `418d577` (Layer 0), plus LS1. Harness: `tests/switch_sweep/sweep.py`.

**The covering array:** 45 rows cover **every triple of values** of 10 factors:
- autonomy, scheduled work, checks, automatic apply, test runs while mapping, self-improvement, notes;
- work modes: not configured, Build on, or Build off;
- approved acceptance checks;
- the switch flipped mid-work: nothing, checks, apply, autonomy, or schedule.

**Each row** runs a real Studio process on a fresh folder and profile, with a scripted model:
1. build;
2. flip one switch through the Studio API;
3. build;
4. restart the Studio;
5. build again.

**Rules checked per phase from the receipts:**
- I1: observe mode asks no model.
- I2: no checks run with checks off or in observe mode.
- I4: project files are written only with checks, automatic apply *and* owner acceptance, and with Build allowed.
- I5: nothing is scheduled with scheduled work off.
- I6: no self-improvement while it is off.
- I7: a build is refused when every Build mode is off.
- I9: every refusal gives a reason.
- Settings survive a restart.
- **Liveness:** where every switch allows an automatic apply, one must happen, so the harness cannot pass by seeing nothing.

## Result: 45 of 45 rows hold every rule

What the receipts saw (the harness is not vacuous):
- 135 phases;
- 2 automatic applies, exactly where every condition allowed one;
- 14 phases with model calls and 10 with checks run;
- 14 scheduled jobs, all with scheduled work on;
- 45 refusals, each with a reason.

| Row | Switches | Phases (calls/checks/applied/scheduled) | Broken |
|---|---|---|---|
| 0 | autonomy=observe, auto_work=off, build_steps=off, build_apply=off, probe_tests=off, kaizen=off, read_notes=on, modes=build off, acceptance=off, flip=auto_work | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 1 | autonomy=observe, auto_work=off, build_steps=on, build_apply=on, probe_tests=on, kaizen=on, read_notes=off, modes=build on, acceptance=on, flip=build_apply | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 2 | autonomy=observe, auto_work=on, build_steps=off, build_apply=on, probe_tests=off, kaizen=on, read_notes=on, modes=not configured, acceptance=on, flip=autonomy | A:0/0/-/1 · B:1/0/-/0 · C:0/0/-/0 | none |
| 3 | autonomy=observe, auto_work=on, build_steps=on, build_apply=off, probe_tests=on, kaizen=off, read_notes=off, modes=not configured, acceptance=off, flip=nothing | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 4 | autonomy=propose, auto_work=off, build_steps=off, build_apply=off, probe_tests=on, kaizen=on, read_notes=off, modes=build off, acceptance=on, flip=build_steps | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 5 | autonomy=propose, auto_work=off, build_steps=on, build_apply=on, probe_tests=off, kaizen=off, read_notes=on, modes=build on, acceptance=off, flip=autonomy | A:1/1/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 6 | autonomy=propose, auto_work=on, build_steps=off, build_apply=off, probe_tests=off, kaizen=off, read_notes=off, modes=build on, acceptance=on, flip=build_apply | A:1/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 7 | autonomy=propose, auto_work=on, build_steps=on, build_apply=on, probe_tests=on, kaizen=on, read_notes=on, modes=build off, acceptance=off, flip=auto_work | A:0/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 8 | autonomy=observe, auto_work=off, build_steps=on, build_apply=on, probe_tests=on, kaizen=off, read_notes=on, modes=not configured, acceptance=on, flip=build_steps | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 9 | autonomy=observe, auto_work=on, build_steps=on, build_apply=off, probe_tests=off, kaizen=on, read_notes=off, modes=build on, acceptance=off, flip=build_steps | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 10 | autonomy=observe, auto_work=on, build_steps=off, build_apply=on, probe_tests=on, kaizen=off, read_notes=off, modes=build off, acceptance=off, flip=autonomy | A:0/0/-/0 · B:0/0/-/1 · C:0/0/-/0 | none |
| 11 | autonomy=propose, auto_work=off, build_steps=off, build_apply=off, probe_tests=off, kaizen=on, read_notes=on, modes=not configured, acceptance=off, flip=nothing | A:1/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 12 | autonomy=propose, auto_work=on, build_steps=on, build_apply=on, probe_tests=off, kaizen=off, read_notes=off, modes=not configured, acceptance=on, flip=auto_work | A:0/1/Y/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 13 | autonomy=observe, auto_work=off, build_steps=on, build_apply=on, probe_tests=off, kaizen=off, read_notes=off, modes=build off, acceptance=on, flip=nothing | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 14 | autonomy=observe, auto_work=off, build_steps=on, build_apply=off, probe_tests=on, kaizen=on, read_notes=on, modes=build on, acceptance=on, flip=autonomy | A:0/0/-/0 · B:1/1/-/0 · C:0/0/-/0 | none |
| 15 | autonomy=observe, auto_work=on, build_steps=off, build_apply=on, probe_tests=on, kaizen=off, read_notes=on, modes=build on, acceptance=off, flip=build_apply | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 16 | autonomy=observe, auto_work=on, build_steps=off, build_apply=off, probe_tests=on, kaizen=on, read_notes=off, modes=not configured, acceptance=on, flip=auto_work | A:0/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 17 | autonomy=propose, auto_work=off, build_steps=on, build_apply=off, probe_tests=off, kaizen=on, read_notes=on, modes=build off, acceptance=off, flip=build_apply | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 18 | autonomy=propose, auto_work=off, build_steps=off, build_apply=on, probe_tests=on, kaizen=on, read_notes=off, modes=build on, acceptance=off, flip=auto_work | A:1/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 19 | autonomy=propose, auto_work=on, build_steps=off, build_apply=on, probe_tests=on, kaizen=off, read_notes=on, modes=build off, acceptance=on, flip=nothing | A:0/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 20 | autonomy=propose, auto_work=on, build_steps=off, build_apply=on, probe_tests=off, kaizen=off, read_notes=on, modes=not configured, acceptance=off, flip=build_steps | A:1/0/-/1 · B:0/1/-/0 · C:0/0/-/0 | none |
| 21 | autonomy=propose, auto_work=on, build_steps=on, build_apply=off, probe_tests=off, kaizen=on, read_notes=off, modes=build off, acceptance=on, flip=autonomy | A:0/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 22 | autonomy=observe, auto_work=off, build_steps=off, build_apply=on, probe_tests=on, kaizen=on, read_notes=off, modes=build on, acceptance=off, flip=nothing | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 23 | autonomy=observe, auto_work=on, build_steps=off, build_apply=on, probe_tests=off, kaizen=on, read_notes=on, modes=build off, acceptance=on, flip=build_steps | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 24 | autonomy=observe, auto_work=off, build_steps=on, build_apply=off, probe_tests=on, kaizen=off, read_notes=on, modes=build on, acceptance=on, flip=auto_work | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 25 | autonomy=propose, auto_work=off, build_steps=off, build_apply=off, probe_tests=on, kaizen=off, read_notes=off, modes=not configured, acceptance=off, flip=autonomy | A:1/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 26 | autonomy=propose, auto_work=on, build_steps=on, build_apply=off, probe_tests=off, kaizen=on, read_notes=on, modes=build on, acceptance=on, flip=nothing | A:0/1/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 27 | autonomy=propose, auto_work=off, build_steps=on, build_apply=off, probe_tests=on, kaizen=off, read_notes=on, modes=build on, acceptance=off, flip=build_steps | A:1/1/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 28 | autonomy=observe, auto_work=on, build_steps=on, build_apply=off, probe_tests=off, kaizen=on, read_notes=on, modes=not configured, acceptance=on, flip=build_apply | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 29 | autonomy=observe, auto_work=off, build_steps=on, build_apply=on, probe_tests=off, kaizen=on, read_notes=on, modes=not configured, acceptance=off, flip=auto_work | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 30 | autonomy=propose, auto_work=on, build_steps=on, build_apply=off, probe_tests=on, kaizen=off, read_notes=off, modes=build off, acceptance=on, flip=auto_work | A:0/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 31 | autonomy=propose, auto_work=off, build_steps=on, build_apply=on, probe_tests=on, kaizen=off, read_notes=off, modes=not configured, acceptance=off, flip=build_apply | A:1/1/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 32 | autonomy=observe, auto_work=on, build_steps=on, build_apply=off, probe_tests=on, kaizen=on, read_notes=on, modes=build off, acceptance=off, flip=nothing | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 33 | autonomy=propose, auto_work=off, build_steps=on, build_apply=on, probe_tests=off, kaizen=on, read_notes=off, modes=not configured, acceptance=on, flip=nothing | A:1/1/Y/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 34 | autonomy=observe, auto_work=off, build_steps=off, build_apply=on, probe_tests=on, kaizen=off, read_notes=off, modes=build off, acceptance=on, flip=build_apply | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 35 | autonomy=observe, auto_work=off, build_steps=off, build_apply=on, probe_tests=off, kaizen=off, read_notes=off, modes=build on, acceptance=on, flip=build_steps | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 36 | autonomy=observe, auto_work=on, build_steps=on, build_apply=on, probe_tests=on, kaizen=off, read_notes=on, modes=build off, acceptance=off, flip=build_steps | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 37 | autonomy=observe, auto_work=off, build_steps=on, build_apply=on, probe_tests=off, kaizen=on, read_notes=on, modes=build off, acceptance=off, flip=autonomy | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 38 | autonomy=propose, auto_work=on, build_steps=off, build_apply=on, probe_tests=on, kaizen=off, read_notes=off, modes=build on, acceptance=on, flip=autonomy | A:1/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 39 | autonomy=propose, auto_work=on, build_steps=on, build_apply=off, probe_tests=off, kaizen=off, read_notes=off, modes=build on, acceptance=off, flip=auto_work | A:1/1/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 40 | autonomy=propose, auto_work=on, build_steps=off, build_apply=on, probe_tests=off, kaizen=on, read_notes=on, modes=build off, acceptance=on, flip=build_apply | A:0/0/-/1 · B:0/0/-/0 · C:0/0/-/0 | none |
| 41 | autonomy=observe, auto_work=off, build_steps=off, build_apply=off, probe_tests=on, kaizen=on, read_notes=off, modes=not configured, acceptance=off, flip=build_apply | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 42 | autonomy=observe, auto_work=off, build_steps=on, build_apply=off, probe_tests=off, kaizen=on, read_notes=off, modes=not configured, acceptance=on, flip=autonomy | A:0/0/-/0 · B:1/1/-/0 · C:0/0/-/0 | none |
| 43 | autonomy=observe, auto_work=off, build_steps=off, build_apply=off, probe_tests=off, kaizen=on, read_notes=off, modes=not configured, acceptance=on, flip=build_steps | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
| 44 | autonomy=observe, auto_work=off, build_steps=off, build_apply=on, probe_tests=on, kaizen=off, read_notes=off, modes=build on, acceptance=on, flip=nothing | A:0/0/-/0 · B:0/0/-/0 · C:0/0/-/0 | none |
