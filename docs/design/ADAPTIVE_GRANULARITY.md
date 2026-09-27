# Adaptive granularity: chunk size learned per model, by trial

Status: design proposal, 2026-09-27. The idea is Lars's; the design is Sol's. Not implemented. It needs Lars's go-ahead before build.

## Why

Field training (25–27 Sept) suggested that free and small models fail whole milestones they can complete in pieces.

On GrowthHat m3:
1. Three free-model attempts at the whole milestone produced no acceptable change.
2. After a model-proposed breakdown, free routes (Kimi K3, Gemini 3.1 Flash Lite) completed accepted slices.

Of 16 applied changes, 6 had a free model as final author, most of them on small slices. This is confounded by trainer clarifications, so it is a hypothesis, not a finding.

Today the chunk size is whatever the plan happened to contain. A person decides to break a milestone down (`runesmith/app/breakdowns.py`). A strong model gets the same size of task as a weak one, and a weak model keeps failing at a size it cannot handle.

## The idea

Treat granularity as a controlled, measured variable, like TCP's congestion window: additive increase, multiplicative decrease.

- **Split on failure.** When an author fails a chunk for semantic reasons (not transport or capacity), the next attempt goes to smaller pieces of the same goal.
- **Grow on success.** After a streak of accepted chunks at one size, offer that author a larger chunk: two sibling milestones in one request, or a milestone without its prerequisites.
- **Remember per instrument and task type.** Each author route keeps a comfortable size, learned from its own accepted and failed attempts. This becomes part of Runesmith's self-map, next to the capability bands.
- **Assemble through acceptance.** Pieces never lower the bar. Every child has its own contract, and the parent's unchanged acceptance must pass on the assembled result before the parent counts as done. This is exactly how GrowthHat m3 and m4 closed.

## What "size" means

This needs one measurable scale, recorded for every attempt:

| Measure | Why |
|---|---|
| public criteria in the contract | how many behaviours must hold at once |
| files the change may touch (`suggested_paths`) | the width of integration |
| lines changed in the accepted result (after the fact) | the actual size |
| author packet bytes | context pressure; failures cluster near packet limits |

The first version uses a coarse ladder, not a continuous number:
1. **L1:** one function or command, one criterion.
2. **L2:** one module or feature slice, 2–3 criteria.
3. **L3:** a milestone as planned.
4. **L4:** two sibling milestones in one request.

## The controller

This is per `(instrument, task_type)`, where the task type is build or repair.

```
level starts at L3 for a new instrument (or at L2 when the route is marked free or small)
on semantic failure at level L:      level ← max(L1, L − 1); next attempt uses a breakdown of this chunk
on transport/capacity failure:       level unchanged (censored, as in the paper)
on inconclusive (timeout):           level unchanged; recheck without inference first
on accepted at level L:              streak += 1; if streak ≥ 3 and L < L4: level ← L + 1, streak ← 0
```

## Where it plugs in

- **Splitting uses the existing breakdown path.** It is model-proposed, adopted separately, and keeps the parent criterion. The change is that the controller may request a breakdown automatically, and adopt it automatically when the owner has enabled that.
- **Depth.** Today the depth limit is 2 (`_breakdown_depth`). The controller needs L1 reachable from L3, which is depth 2 and fits. Do not raise the limit; it guards against endless replanning.
- **Growing** is new: a request that bundles sibling milestones, with all their contracts, into one packet. The result must pass every sibling's acceptance, or none of them is applied.
- **Memory.** Every attempt already writes a verification record with author and outcome. The controller reads those records, so it adds no new evidence store.
- **Budgets.** A split spends from the same allowance; it never adds fresh attempts. Growing must not buy bigger responses beyond the author's token cap.
- **Studio** shows each model's current comfortable size and why ("split after a regression at L3 on 26 Sept"), with a switch to turn the controller off.

## How we would know it works

This is an experiment worth preregistering, and paper material either way:

- **Arms:**
  1. fixed as-planned granularity (L3);
  2. fixed fine granularity (L1/L2);
  3. the adaptive controller.
- **Authors:** at least one free route, one local small model and one frontier model.
- **Tasks:** fresh construction tasks with owner acceptance written before authoring.
- **Primary endpoint:** accepted milestones per fixed call and token budget.
- **Guards:** regressions caught by cumulative acceptance, assembly failures, total cost, wall time.
- **Prediction:** adaptive ≥ the best fixed arm for weak models, and no worse than L3 for frontier models.

## Open questions for Lars

1. Automatic splitting spends attempts without asking. Should it be on by default, or only when the owner allows it?
2. Should grown (bundled) requests ever be applied piecewise if only some siblings pass? The proposal says no: all or nothing.
3. Build this before or after the out-of-box release gate? My recommendation is after the release gate. First make the first-user journey work with today's machinery, then run the experiment. It could become the paper's next confirmatory study.
