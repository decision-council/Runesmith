# Measuring self-improvement: the right numbers, and the rules for using them

Status: **catalogue built 2026-09-28, instrumentation not yet built.** Asked for by Lars: "the precisely right measurement points for self improvement … speed, efficiency, production iteration specs, cheaper model efficiency, Runesmith ability to map better, make milestones, success rates … hundreds, maybe thousands."

The machine-readable catalogue is [measurements_catalog.json](measurements_catalog.json). It was built by a workflow of 13 agents:
- six domain extractors, each reading only named source files;
- six adversarial verifiers, which checked every claimed source against the code and corrected vague or gameable definitions;
- one completeness critic.

The merge script is `D:/oob/checker/catalogue_merge.py`.

## What is in it

- **424 measurement points** in 9 domains:

  | Domain | Points |
  |---|---|
  | build pipeline | 67 |
  | mapping and planning | 105 |
  | self-improvement engine | 78 |
  | acceptance checks | 56 |
  | owner experience and reliability | 46 |
  | inference and cost | 45 |
  | end-to-end | 12 |
  | community | 9 |
  | meta (the loop measured on itself) | 6 |

- Each point has:
  - an exact definition over named receipts;
  - its source: a ledger event and field, a receipt file, or the instrumentation it still needs;
  - its unit and direction, and its role;
  - the levers it judges;
  - a minimum sample, with its noise sources;
  - how it could be gamed, and what guards it;
  - its privacy class and collection cost.
- **65 breakdown dimensions**, such as model tier, exact model and route, role, project kind, project size band, milestone type, autonomy mode, check phase, provider load, pipeline stage, generation and release. The catalogue lists 833 metric-and-dimension pairs; expanded by each dimension's values, that is many thousands of concrete measurements, as Lars expected.
- **Roles:** 43 primaries (a trial may optimise them), 126 guardrails (must not get worse when a primary improves) and 255 diagnostics (explain, never optimised).
- **Available today:** 168 are recorded, 95 can be derived from existing receipts, and 161 need instrumentation. Verifiers reviewed 355 points and confirmed 296 sources in the code.
- **Privacy:** 401 are aggregate numbers that could go to a community log; 20 are local only; 3 are never shared.

## The rule: a lever's own win is necessary, never sufficient

Any single number can be gamed. A check proposer can look better by proposing fewer checks, and a router can look cheaper by giving up on hard calls. So a self-improvement trial of any lever is judged against the **project scorecard**, together with its own domain's bundle, and must hold every guardrail.

### The project scorecard (end to end, the owner's felt experience)

| Primary | What it is |
|---|---|
| `e2e.milestone_lead_time_total` | Seconds from a milestone being added to its change being applied (median and p90) |
| `e2e.milestone_cost_usd` | Money, or free quota, spent across every call for that milestone |
| `e2e.full_pipeline_success_rate` | Milestones applied without corrections, escalations, revisions or discards |
| `e2e.throughput_per_hour` | Applied milestones per hour of Studio time: "production iteration speed" |

**Guardrails for any trial:**
- Faking by weaker gates: `checks.vacuity_rate` and `checks.over_specification_rate`, so speed cannot come from a weaker or wrong acceptance gate.
- Failure moved downstream: `build.check_fail_rate` and `e2e.rework_after_apply_rate`.
- Winning trials wrongly: `self_improvement.false_promotion_rate`.
- Owner trust and safety: `owner_reliability.rescue_rate` and `owner_reliability.invariant_violation_rate`.
- Community privacy: `community.aggregate_only_leak_rate`, once the community exists.

**How a trial is judged**, in order:
1. It wins its own decision (the one-sided Fisher trial on the owner's work).
2. `meta.e2e_delta_per_generation` confirms a favourable move on the scorecard, on matched milestones.
3. No guardrail regresses (`meta.guardrail_regression_incidence`).
4. Its gain is weighed against what the campaign cost (`meta.trial_roi`). Self-improvement is never free; it spends the owner's self-improvement share.
5. Over time, `meta.local_proxy_transfer_rate` shows whether lever-level wins actually move the scorecard. If they keep disagreeing, the loop is optimising the wrong thing precisely.

### Domain bundles (primaries with the guardrails they must never be read without)

- **Build:** `first_attempt_success_rate` and `calls_to_green` (or `time_to_green`). Guarded by the acceptance pass rate, stale and timeout rates, draft waste, and the escalation trigger rate.
- **Inference:** `output_failure_rate`, `cost_per_successful_call` and `latency_p90_s`. Guarded by censorship and pre-admission refusal rates, binding mismatches (must stay at zero), and honest token accounting. The downstream check pass rate is the real scoreboard.
- **Mapping and planning:**
  - mapper speed, guarded by classification accuracy and truncated scans;
  - breakdown child completion, guarded by adoption and rejection;
  - milestone completion and plan survival, guarded by drop, hold and "done when" rates;
  - repair yield, guarded by false promotions.
- **Checks:** `soundness_rate` (fails before, passes every correct build, fails every broken build). Until the reference-build and mutation gates exist, it is proxied by the trial health and revision yield, plus approval rate and milestone coverage. Also `model_tier_soundness_gap`. Guarded by over-specification, vacuity, unstated text, cost and time to approval, and discard and replace rates.
- **Self-improvement engine:** `repair_yield` (or `seconds_per_success`) and cost per activated generation. Guarded by false promotions, organ errors, the gain-to-noise margin and post-activation regression. Trial win rate and mechanism diversity are diagnostics only: optimising them directly is exactly the gaming the community scoreboard rule forbids.
- **Owner experience:** rescue rate and zero-rescue releases, time and owner actions to the first applied change, and the journey pass rate. Guarded by every safety invariant (I1-I10, path escapes, key exposure, ledger integrity, write rollback), and by friction and bug counts, so rescues cannot be hidden as "friction".

### Cheaper-model efficiency

Lars's central question has its own points, computed on the same milestones: `e2e.cheap_vs_strong_e2e_efficiency_gap`, `checks.model_tier_soundness_gap`, `checks.style_soundness_gap` and `e2e.cheap_model_e2e_share`. The paced Checker experiment (`D:/oob/experiments/checkers/FINDINGS.md`) is their first manual instance: it compared examples with code on the same model.

## What the catalogue revealed

- **Only 1 of 12 levers can improve itself today** (`meta.lever_coverage`). Kaizen trials the repair organ only. The catalogue already measures the other eleven: planner prompt, milestone breakdown, check proposer, examples template, router policy, mapper, author packet, context focus, retry policy, UI wording and scheduler. None of them has a trial mechanism yet. That is the roadmap for self-improvement after the release.
- **The end-to-end primaries are derivable now**: lead time, cost, calls and throughput per milestone come from existing ledger events (`milestone.added`, `draft.applied`, and `instrument.call` keys `draft-<milestone>-…`). A scorecard report needs no new recording. This is the first thing to build.
- **Gaps that need recording:**
  - goal lineage on milestones (for idea-to-applied yield);
  - journey rescues and frictions as receipts, not only log text;
  - schema and invalid-JSON failures as a structured error kind;
  - the reference-build and mutation gates for check soundness (see `WEAK_MODEL_CHECKS.md`).
- **Verifier corrections:** 59 claimed sources did not hold and were corrected, often to "needs instrumentation". One exact duplicate was removed: `build.needs_revision_rate` is the same as `build.check_fail_rate`.

## Order of work

1. **Release:** no change. The catalogue is design; journeys and the paper use its end-to-end numbers by hand.
2. **Right after release:**
   - a scorecard report computed from the ledger (derivable points only);
   - rescues and frictions recorded as receipts in the journey protocol.
3. **Then:** trial mechanisms for the next levers, starting with the check proposer and the examples template (the Checker experiment already measures them), each judged by the scorecard as above.
4. **With the community** (`COMMUNITY_EVOLUTION.md`): only `aggregate_ok` points travel; the scoreboard counts replicated scorecard gains, never lever-local wins.
