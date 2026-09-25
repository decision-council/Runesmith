# Roadmap

Each step ships only with its tests. A capability is claimed only after a preregistered experiment measures it.

## v0.1 (this release)

- A fixed kernel and confined organs.
- The repair organ g0, a port of v1.
- One Kaizen campaign per command (`runesmith kaizen`).
- Self and environment maps.
- Memory.
- The CLI.
- SR5-KAIZEN tests the first full loop on fresh tasks.

## v0.2 — Kaizen always (the run loop)

1. **Object discovery.** Probe the mapped objects (opt-in) and turn failing tests into repair opportunities. The issue text is the failure excerpt; the judge is the full test file.
2. **Experience store.** Every closed opportunity becomes a replayable development task: the parent source, the failing tests, the judge tests, and the matured outcome once known. Runesmith grows its own development set from its own history.
3. **Run loop.** For each opportunity, `attention.next_lane()` chooses the lane:
   - **object:** repair with the active generation, record the result, and let the attention controller observe it;
   - **subject:** one Kaizen step. Experience examples come from the store's experience split; candidates are scored on the held-out validation split (SR5 Amendment 1).
4. **Online confirmation (done: `kaizen/trial.py`).** A frozen candidate is confirmed on the next fresh opportunities before CAS activation:
   - opportunities are assigned between incumbent and candidate by a seeded coin;
   - the stop rule is sequential and preregistered;
   - the rollback trigger is declared.
5. **Organs beyond repair.**
   - `memory_use`: when to recall, and what to write back.
   - `summarize`: context compaction with source anchors (blueprint §6.9).
   - `toolsmith`: builds small tested tools as skill packages (§6.10). A tool is kept only with measured reuse.
6. **Object templates beyond Python.** Node (`npm test`), documents (link checks and freshness), services (health endpoints). The build ladder and bands are owned per kind.

## Observed gaps (feed the next Kaizen campaigns)

- **Weak models.** A 2.6B free model answered through the OpenAI-compatible path, but its navigation JSON was malformed, and g0 rejected the opportunity (live smoke, 2026-09-24). A weak-model organ needs:
  - tolerant parsing;
  - smaller schemas;
  - deterministic fallbacks before calling the model at all.
- **Repository scale.** g0's navigation index is capped at 12,000 bytes and sorted alphabetically. In repositories with 80–180 source files, the defective file can fall outside the index. The next navigation mechanism should rank files by evidence before truncating: failing-test names, executed-line traces, recent failures.
- **Memorization.** Keep-best scored on tasks whose answers the author has seen produces memorized rules (SR4). Kaizen must always score on held-out validation, as `loop.py` and SR5 Amendment 1 do.
- **Replay noise.** Identical organs scored 10/32 and 16/32 on the same validation replay (SR5 iterations 4 and 5). Keep-best needs more replay rounds, or a paired comparison of incumbent and candidate on the same tasks in the same batch, before it can trust gains of a few tasks.
- **Author diversity.** The SR5 author proposed one refinement in four consecutive iterations (4–7), even though the packet listed earlier attempts. The next improve step should show rejected diffs, require a mechanism class not yet tried, and spend at most one attempt per class. This is the first "improve the improver" target.
- **SR5's result: a fallback that does not scale (2026-09-24, sealed).** B's navigation fallback, the first four indexed files, rescued 2/6 failures in development repositories of about 15 files, and 0/26 in confirmation repositories of about 115. The confirmation was not shown (36 vs 50 of 180). The next navigation mechanism must find the defect at scale; the execution trace is the obvious candidate. Keep-best must also stop trusting single replays: only about +2 of B's 11 → 17 development gain was mechanism.
- **Unused affordances (done: `kaizen/affordances.py`).** SR5's candidate B, written by Kaizen, falls back to the first four indexed files (alphabetical) when navigation fails. Its later attempts refined that same fallback. Meanwhile the kernel always offered `run_signal(trace=True)`, which returns the source lines the failing tests execute. On large repositories that points at the defective file where an alphabetical fallback cannot. No attempt used it. The audit now puts every unused affordance in front of the author as an untried mechanism class. Whether authors then use them, and whether that helps, is for the next preregistered campaign to measure.

- **Finding did not become fixing (SR6 development, 2026-09-24, exploratory).** The audit worked in one sense: a free-class author adopted the execution trace on its second attempt, and later attempts refined it. Every trace variant read the defective file more often than B did (21–23 of 40 sessions, against 15 and 17 in B's two replays). Their repair counts (9–11, against 13) stayed within B's own replay noise (13 → 10).
  - A paired comparison per task and round first suggested that the changes hurt fixing: the candidates lost 5–6 of B's successes. **Corrected:** B replayed against itself lost 4 such successes (13 → 10). The losses are within replay noise, and "fixing got worse" is not established.
  - The lesson for the engine: a paired view needs a same-organ noise reference beside it.
  - The author packet shows aggregate failure families per attempt, not which of the incumbent's successes an attempt lost, or where. The next "improve the improver" step is a **paired regression view in the PDSA Study step**, **calibrated against the incumbent's own replay-to-replay churn**: for each rejected attempt, the incumbent successes it lost, with the stage at which each diverged.
  - This is proposed, not built. It changes the author packet, so it waits until the declared campaigns (SR6, and SR7 if run) have concluded.

## v0.3 — evidence for the vision

- **Weak-model amplification (WMA).** The same small model at equal total budget, with vs. without the suit, on sealed fresh tasks (blueprint §10 W).
- **Model succession.** Learn with model A; B inherits only the frozen state, with no transcript (blueprint §10 S, P27).
  - *Candidate considered 2026-09-24T05:39Z, not launched.* SR5's B (authored with gpt-oss models) against A, with the 2.6B free model as the instrument. The exploratory probe gave no support: 8 opened development tasks, A 4/8 vs B 2/8. None of A's losses were navigation failures (4 budget exhaustions), so B's navigation fallback had nothing to rescue. It would also spend about 540 calls of the shared OpenRouter free allowance. Revisit with a model whose navigation answers do fail, or after a Kaizen generation that targets budget exhaustion.
- **Cumulative generations.** A → B → C with old-task replay (blueprint S4).
- **Starvation integrity.** Remove all models: integrity must hold while coverage contracts (blueprint §5.5).
