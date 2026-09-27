# Filling the blanks in building Runesmith — 2026-09-27

Prepared at Lars's request as a comprehensive companion to [Build additions from Lars](BUILD_ADDITIONS_FROM_LARS_2026-09-26.md). This is the trainer's engineering backlog for constructing and improving **Runesmith itself, across the whole product**. It is not a manual for Runesmith's Build mode. Build mode is only one of the capabilities discussed below.

This is a product design/backlog, not the finished paper, an experiment result, or a claim that every item exists today. Lars corrected the title/scope at the local date rollover to 2026-09-27; the additions record retains its original 2026-09-26 date.

The product is a fast codebase **builder, optimizer, planner and operator**, usable with anything from assisted chat authorship to unattended API/local operation. The central ambition is useful work without a permanent external trainer secretly supplying the decisions. Runesmith is the persistent layer between its operator, replaceable models and the environment it is improving.

Labels distinguish **R — owner requirement**, **D — derived requirement needed to make it dependable**, and **I — suggested idea requiring evaluation**. Suggested sequencing is not a new authorization to alter a live service. Current training restrictions, budgets and application execution controls still apply. Completion must be supported by code, UI and receipts; this document alone completes no feature.

## 1. Define the unit of useful work [R, D]

A useful unit connects a purpose to a result: objective, selected opportunity, plan, bounded change or action, checks, integration and observation. Producing code is an intermediate artifact, not necessarily success. An objective can also be finite: build and verify a particular tool, then stop.

Each unit needs an identity, parent objective, mode, source version, permitted resources, acceptance contract, budget, current state and evidence pointers. It must be possible to answer “why this work, why now, who authored it, what changed, what passed and what is still unknown?” without reconstructing a chat transcript.

The smallest useful delivery should be preferred over large speculative rewrites. Decomposition must preserve an explicit integration plan; four individually plausible modules do not automatically make one working system.

## 2. Three honest starting conditions [R, D]

- **Empty folder plus a sentence:** infer candidate requirements if enabled, label assumptions, define a smallest demonstrable result, choose a modest architecture and build a thin working slice. Do not invent accounts, live datasets or permission to publish.
- **Blueprint or partial implementation:** inventory what is already present, identify gaps against the blueprint, preserve working pieces and make dependencies explicit before scheduling.
- **Productive existing environment:** first read applicable instructions, map entry points, tests, deployments, data and operating duties. Establish a baseline and protected resources before editing. Existing behavior and external state need preservation, not automatic replacement.

The first-run UI should show which situation Runesmith believes it is in and allow correction. A read-only preview should make its proposed boundaries understandable before automatic work is enabled. Lack of a conventional README must not make the whole product unusable.

## 3. An environment model, not just a file list [R, D]

Persist a navigable map of modules, interfaces, dependencies, tests, build commands, data flows, runtime entry points, external services, operational procedures and available measurements. Link summaries to exact sources and revisions. Track unknowns instead of filling them with confident guesses.

Separate owner instructions from descriptive documents, inferred purpose, observations and model hypotheses. Scope instructions to the affected paths. Conflicts or unreadable required instructions should block the affected action with a useful explanation. Incoming support messages and reports never become permission to run commands.

The map should support zooming: a compact project overview, a subsystem summary, then the exact source and tests required for one change. Invalidate summaries when their sources change. A summary may guide navigation; it must not replace unseen source when constructing an exact edit.

**Acceptance:** a model can identify the relevant subsystem, request every advertised symbol and receive the right source. Listed-but-unfetchable methods must fail qualification. Tests should include nested/scoped guidance and changed files, not only ideal small repositories.

## 4. Goals and contracts before implementation [R, D]

Permit owner-authored goals, imported blueprints and Runesmith-proposed goals. Store their provenance separately. When inference is enabled, Runesmith may select routine in-scope goals under the configured delegation; it must not relabel its choices as explicit owner instructions.

Each goal needs a definition of done, a verification method and relevant constraints. Useful measures include functional acceptance, latency, resource use, reliability, successful jobs, support outcomes or business metrics. A website is not obliged to have analytics before its first page can be built.

Attach each milestone to an executable or inspectable acceptance contract. Declare dependencies, non-goals, excluded paths, compatibility requirements and expected artifacts. Mark missing credentials or unavailable services as blockers or test substitutions, never silently as passed integrations.

Changes to an acceptance contract must be versioned and visible. A model may propose a correction to a defective test, but must not erase a failing requirement merely to obtain green checks.

## 5. Independent modes with one coherent agenda [R, D]

All enabled modes should draw from the same goal graph, environment map, evidence and resource scheduler. There is no cap on active switches. Map & Plan, Build, Optimize, Operations, Troubleshoot and custom modes must have clear purposes and observable runtime effects.

Map & Plan should have an explicit purpose-inference control. Reading restrictions is mandatory even when inference is off. Existing goals can drive Build while mapping is disabled. Self-improvement remains a distinct control rather than a hidden consequence of Optimize.

A custom mode should specify its objective, instructions, supported underlying actions, inputs, cadence and stop conditions. Naming a mode does not create a new privileged tool. Show unsupported requested actions as unsupported.

**D:** share priorities and prevent starvation. An urgent service problem may interrupt lower-priority construction at a safe boundary, but ordinary Operations must not permanently starve Build. Preserve queued work and the reason for reprioritization.

## 6. Autonomy and authority are separate from activity [R, D]

Support assisted planning, unattended bounded building and authorized live operation without pretending they are the same permission. The user should configure what may run automatically, where, with which credentials, within which spend limits and under which acceptance rules.

Within that envelope, avoid unnecessary approval prompts. Request or record a blocker only for a genuinely new decision or authority boundary. No reply from an unavailable owner is not new permission.

Suggested profiles are **observe**, **propose**, **build and apply inside the project**, and **operate configured live services**. These are bundles of explicit capabilities, not a single magic “autonomous” flag. Users may refine them. Self-modification and deployment authority should remain separately inspectable.

In Studio show active modes, automatic scheduling, allowed effects, project boundaries and emergency stop together. Turning off automatic scheduling need not delete plans; turning off a mode must prevent new dispatch and be rechecked at safe execution boundaries. In-flight external calls require reconciliation even after cancellation.

## 7. Model roles and capability qualification [R, D]

Authors integrate requirements and design coherent changes. Workers execute bounded tasks; reviewers and evaluators check them. These are roles, not permanent identities or prices. A capable free model may author a bounded change; a paid frontier model may fail it. Small workers still need qualification for their assigned tasks.

There is no established universal parameter-count cutoff. Qualify with representative packets and real checks: valid output, applicable complete edits, preserved interfaces, diagnosis of feedback, fresh-load success and documented assistance. A connection probe is not such a qualification.

Use smaller tasks, source-aware packets and feedback to make economical models useful. Escalate only the failing decision or subsystem when practical, not the entire repository by default. Never treat an escalation as evidence that the original weaker model succeeded unaided.

The manual frontier-chat workflow must remain first-class: copy the complete request, obtain the specified response, paste into the matching request, correct formatting if necessary, then follow normal admission and verification. Keep request IDs and model attribution. Explain that copy/paste requires a person; unattended operation requires API/local routes. See the companion document for exact UI steps.

## 8. Planning that can revise itself without losing the goal [R, D]

Create a dependency graph of small deliverables, not an unbounded to-do list. Every step should state the interface it consumes and produces, its acceptance checks, dependencies and affected resources. Include integration, documentation for the delivered artifact and operational readiness where those belong to the goal.

Planning should distinguish uncertainty that can be cheaply measured from uncertainty needing an owner decision. Use short spikes only when they answer a named question. Limit speculative scaffolding that never reaches a working result.

Replan after evidence: failed checks, changed source, a new constraint, a completed milestone or an unavailable route. Preserve superseded plans and explain why they changed. Do not replan unchanged evidence indefinitely or mark abandoned work complete.

**I:** a small “next best action” comparison using expected value, estimated cost, uncertainty and dependencies. Start with transparent rules and receipts; a sophisticated decision model is optional, not a prerequisite.

## 9. A reliable build transaction [D]

Use a durable progression:

`select → snapshot/context → author → admit → verify → integrate → observe → retain learning`

Stages may branch into recoverable failure states. Persist the stage and artifact identities before costly or externally visible work. A draft should bind to its base source and acceptance-contract revision. Unknown source drift requires review or reauthoring, not a blind overwrite.

Admission should reject paths outside the project, missing edit targets, incompatible file representations, oversized changes and malformed responses. Keep exact-edit and complete-file paths explicit. Checks establish bounded behavioral evidence, not general security trust. Generated code remains subject to confinement, authority restrictions and review even after checks pass.

Verification should be isolated from live customer state, with finite time and resource limits. Integration should be controlled, source-checked and recoverable. A model message saying “tests pass” is not a verifier receipt. The UI must distinguish draft produced, admitted, checked, applied, accepted and observed in operation.

## 10. Feedback loops and bounded recovery [D]

Return actionable feedback: the real source when an edit target is missing, parser errors for malformed replies, the relevant failing check and the smallest useful context. Do not make a model repeatedly guess unseen text.

Classify failures: infrastructure, quota, transport uncertainty, malformed output, stale source, admission refusal, test failure, acceptance gap and authority blocker. Recovery must address the class rather than blindly repeating the same prompt.

Give each unit a finite repair and verification allocation. Reuse a completed check only where an explicit policy validates the exact candidate, environment, verifier and contract. A completed prefix of a timed-out suite cannot substitute for full candidate acceptance. Preserve a timed-out check as timed out; any continuation or extra allocation must remain separate in the record.

Known lost responses should be retrieved by job/ticket ID. Uncertain external submissions must not be duplicated automatically. If recovery is exhausted, park that unit with a diagnosis and continue another eligible unit where possible. “Keep working” does not mean “spend forever on one failure.”

## 11. Fast without pretending unlimited resources [R, D]

Expose conservative speed presets mapped to concrete call concurrency, request pacing, local CPU/memory limits and budget envelopes. Show both configured and effective capacity. A free route may impose a smaller effective limit; paid providers also throttle and local models have hardware limits.

Avoid needless work before buying more inference: cache source-index results by hash, reuse unchanged packets and check receipts, fetch focused source, perform format checks locally and reconcile jobs instead of resubmitting. Record cache validity, not just cache hits.

Measure end-to-end useful progress: time to a verified milestone, accepted changes per call, failure/recovery rates and elapsed blocked time. A faster parser alone may be valuable but does not prove faster project delivery.

**I:** token/call budgets per stage with evidence-driven escalation; parallel independent read-only discovery; adaptive backoff per provider. Evaluate these against a simple baseline rather than assuming complexity helps.

## 12. Concurrency with a real conflict model [R, D]

Never let concurrent jobs touch overlapping codebase parts. Declare read/write footprints and shared resources before dispatch, normalize paths and aliases, and serialize unknown footprints. Enforce relevant read/write as well as write/write conflicts.

Isolated candidate trees protect files but not shared databases, deployment targets, dependency caches or ports. Those resources also need leases. Lease recovery after restart must distinguish an abandoned worker from an in-flight external action.

Integrate serially or under equivalent source/version protection; recheck affected dependencies and interfaces. File-disjoint patches can still conflict semantically. Run integration checks on the combined result before treating both jobs as delivered.

UI requirements: requested/effective concurrency, live jobs, conflict reasons, lease owner, waiting dependencies and cancellation status. Do not display a functioning parallelism slider before these controls and tests exist.

## 13. Operations as accountable production work [R, D]

Operations should execute configured runbooks, monitor service health, process authorized intake, produce reports and carry out routine in-scope actions. It must not be reduced permanently to reading metrics, though read-only report ingestion is a useful first implementation slice.

An operation definition should bind a trigger/cadence, inputs, permitted tools/resources, credentials, preconditions, success measure, deduplication identity and recovery policy. Distinguish an internal report from an externally sent message or deployment.

Before enabling a live adapter, test it in a safe environment or dry run with concrete output evidence. Use least privilege, explicit destination/account identity and reliable handling of partial success. Where exactly-once execution is unavailable, provide idempotency or reconciliation and say what remains uncertain.

Include maintenance duties such as certificate/expiry warnings, queue growth, recurring failures and backup verification only where relevant and authorized. Do not install unrelated schedulers or silently take over another operator's workflows.

## 14. Measurements and support intake [R, D]

Make local report drops and pasted CSV/JSON easy first. Define fields, population, filters, timestamps/timezone, aggregation, units, thresholds and interpretation. Empty, invalid, stale and unavailable data are distinct from zero.

Then add narrow adapters for analytics, stores, apps, tools and filtered email as needed. Show configured, authenticated, reachable, last-successful-read and current-error states. An adapter placeholder must not look connected; a GA4 export is not a live GA4 integration.

Support logs should drive reproducible issue hypotheses with context and privacy controls. Treat report bodies and mail as untrusted data, not prompts granting tool access. Deduplicate arrivals and preserve source identity without routinely sending raw customer records to models.

Tie observations to the goal and definition revision. Expose data period separately from observation time. Threshold attainment is not necessarily causal improvement. Where a numerator and denominator are required, record both and their population rather than comparing ambiguous percentages.

## 15. Optimize against something observable [R, D]

Start with a baseline, a proposed mechanism, expected benefit, possible regressions and a verification plan. Optimize may target speed, reliability, quality, resource use, planning, inference efficiency or business outcomes. Preserve constraints and tradeoffs.

The workflow should proceed from measured hypothesis to a bounded candidate, an appropriate comparator, validation and controlled integration. A proposal alone is not an optimization. A faster implementation consuming much more memory should show both results.

Use deterministic checks where appropriate and repeated/noise-aware measurements where necessary. Avoid selecting a favorable result from many attempts and presenting it as a preplanned confirmation. Product experimentation and scientific claims remain distinct.

**I:** schedule periodic opportunities from measured bottlenecks, but require headroom and a finite investment rule before expensive searches. Retain unsuccessful hypotheses to avoid paying for them repeatedly.

## 16. Memory, focus and durable learning [R, D]

Maintain a compact working state: current purpose, active plan, constraints, known interfaces, completed work, open failures, tested hypotheses and next eligible actions. A replacement model should reconstruct the relevant state from evidence rather than depend on the departed model's chat history.

Use layered summaries with provenance and revision checks. Keep raw receipts accessible for zoom-in, while preventing irrelevant detail from dominating every call. Confidence must reflect evidence quality and freshness.

Store lessons as scoped claims: “this correction resolved this failure under these conditions,” not “always do this.” Test reuse on a new relevant case before generalizing. Remove or supersede stale lessons transparently.

**I:** an experience retrieval benchmark based on real builder failures, measuring retrieval usefulness, source fidelity and downstream repair quality separately. Do not assume a retrieval speedup necessarily changes repair outcomes.

## 17. Self-improvement without defeating the evaluator [R, D]

Let Runesmith map its own capabilities and propose improvements from performance/failure evidence, including planning, context assembly, memory, navigation, tool use and evaluation efficiency. It needs access to relevant source behind a defined boundary, not permission to edit every controlling rule.

Freeze the evaluator/authority relevant to a candidate, version the predecessor and successor, test the change and restart/load the successor before claiming adoption. Do not allow a candidate to rewrite the criterion by which it is approved.

Separate “the external trainer improved Runesmith,” “a model authored a self-change,” “a measured capability improved” and “later project work improved.” All are useful observations, but they are not interchangeable. Current trainer-authored product changes must remain labelled as such.

**I:** promote reusable lessons into tools or policies only after validation; retain a last-known-good generation and rollback instructions. Repeated safe self-improvement is a release qualification target, not a property proved by one successful patch.

## 18. Security, privacy and secrets [D]

Enforce project boundaries independently of model instructions. Protect secrets, home state, evaluator records, excluded paths and unrelated repositories. Resolve links and path aliases before reads or writes. Never place credentials in model packets or exported reports.

External model services receive project information: show what will be transmitted, support exclusions/redaction and allow local routes. Manual copy/paste must include the same privacy warning. Do not imply local execution makes every configured remote call private.

Generated commands and dependencies require bounded execution and policy checks. Protect against malicious instructions in source comments, logs, websites and email. Restrict network and production credentials to the actions that need them.

## 19. Studio should explain the real machine [R, D]

Provide a coherent home view: purpose/assumptions, enabled modes, authority, current activity, next work, progress, budget and blockers. Let users drill into environment maps, goals, model roles, measurements, drafts, checks, operations and self-improvement receipts.

Every action should show whether it only saves configuration, makes inference calls, reads local data, verifies a draft, applies code or causes a live effect. Disabled controls need explanations. Unknown cost or authorship must not become zero or a confident model label.

Preserve unsaved forms and waiting chat replies across routine view refreshes. Offer recoverable error messages, readable keyboard-accessible controls and logs that do not require internal experiment codes to interpret.

Advanced settings can be progressive, but important switches and limits must not be hidden. “All modes on” should show many eligible activities, not pretend all are running concurrently.

## 20. Evidence, qualification and release [D]

Keep a traceable ledger of goals, packets, model/provider receipts, retries, costs and estimate coverage, source hashes, contracts, checks, integrations and observations. Record trainer intervention and manual assistance. Provide a secret-safe export for user support and external review.

Qualify the real UI-to-runtime path, not only helpers: save configuration, enqueue work, observe state, process a reply, reject an invalid candidate, verify a valid candidate and recover after interruption. Test cold start and restart on Windows, not only an already-initialized happy path.

Release profiles need evidence under their actual constraints: free-only routes with quota failures; manual chat with a human relay; API/local unattended operation; existing repositories with unrelated edits; empty folders; and explicit production adapters in a non-customer test environment.

A supervised demonstration is not an unattended soak test. A generated test passing is not owner acceptance. A useful field improvement is not automatically a publication claim. Keep those distinctions visible without burying the actual positive results.

## 21. Proposed implementation order [D; sequencing suggestion]

These are work packages for the trainer developing Runesmith's reusable runtime and Studio, not instructions for a model to implement the three Hats directly. Hat implementations remain authored through the configured Runesmith instruments. Keep the master and three project logs synchronized, and distinguish trainer-written runtime improvements from Runesmith-authored subject changes.

1. **Foundation:** instruction provenance, independent modes, local/pasted measurements and clear model/manual-chat guidance, wired to the existing queue and Studio. Preserve legacy behavior unless modes are explicitly configured.
2. **Reliable delivery:** tighten context/edit contracts, feedback recovery, verification allocation and end-to-end goal completion. Diagnose actual field failures before adding more planning abstractions.
3. **Explicit inference and autonomy controls:** Map & Plan/purpose-inference switches, authority profiles, predictable scheduling and accurate UI capability states.
4. **One real operations adapter:** choose a useful bounded duty on an authorized training project, implement its dry run/receipts/reconciliation and then qualify automatic in-scope execution. PRHat remains read-only under current authority.
5. **Conflict-safe speed:** footprints, leases, integration checks and interruption tests before enabling parallel writers or a concurrency slider.
6. **Measured optimization and self-improvement:** close the proposal-to-tested-change loop with preserved evaluation and accurate attribution.
7. **Unattended qualification:** run representative goals without hidden trainer assistance, publish the limitations, and improve the bottlenecks found.

Continue delivering small reusable improvements along this path. Do not spend the entire program perfecting one subsystem while the rest of the product cannot complete a goal.

## 22. Optional ideas worth testing, not automatic scope expansion [I]

- A capability passport per model/role, based on local observed results rather than price or marketing names.
- A reusable recipe/tool library with source provenance, compatibility checks and retirement of failed recipes.
- A “why this action?” panel showing the chosen objective and rejected alternatives with their evidence.
- A simulation/dry-run view for an operations schedule before it is granted live authority.
- A portable, secret-free project handoff bundle so another machine or instrument can reconstruct state.
- A deterministic scheduling replay for investigating starvation, retry storms and conflicting jobs.
- A builder regression garden of small real failures used to compare changes to context, memory and recovery.

These should earn their place through a named user need or measured bottleneck. They are not reasons to delay a reliable, useful minimal release.

## 23. Numbered use-loop series [R, D]

Lars requested repeating B1, B2 and subsequent series, with approximately 5–25 loops per area, covering buttons, fields, settings and complete phases. These are engineering qualification loops for the trainer building Runesmith. They do not silently become scientific experiments or production authorization.

Maintain a coverage inventory: screen/control, starting state, user action, expected UI and runtime outcome, source/authority boundary, actual result, evidence, defect/fix and retest. Exercise happy paths, invalid input, empty state, quota/transport failure, stale source/configuration, interruption and recovery. A visible button or passing helper test alone does not cover the workflow.

| Series | Intended coverage | Initial disposition |
| --- | --- | --- |
| B1, 5 loops | Mode switches/save/dispatch; custom policies; measurement fields; paste versus evaluate; live-event subscription/responsive layout | First isolated browser series passed on 2026-09-27 local date. Actual frontend/CSS, in-memory API fixtures. Backend is separately tested. |
| B2, 5 initial loops | Author capability guidance; manual-chat setup; role preferences; matching requests/replies; malformed/edited/declined answers; keyboard and drawer recovery | B2.01–B2.05 passed in the isolated browser fixture on 2026-09-27 local date. Typed replies now survive event refresh/navigation within the page session. No live chat, restart-persistence or full role-editor qualification claim. |
| B3, 10–15 loops | Empty/blueprint/existing-folder onboarding, instructions, maps, inferred assumptions, goals, contracts and plan revision | Planned; no blanket completion claim. |
| B4, 15–25 loops | Draft, exact edits, admission, source drift, verification, checks/allocation, repair feedback, apply/undo and milestone integration | Planned; reuse existing regression evidence but test the full UI path. |
| B5, 10–15 loops | Scheduling, enabled modes, resource controls, stop/pause, restarts, uncertain calls and provider fallback | Planned; only exercise implemented controls, record missing ones. |
| B6, 5–15 loops | Measurements, local reports, unavailable connectors, later authorized runbooks and operational recovery | Local intake foundations exist; live adapters still need implementation and authority. |
| B7, 5–15 loops | Optimization hypotheses, comparisons, tradeoffs, self-target selection and successor restart/rollback | Planned; preserve evaluator and attribution boundaries. |
| B8, 10–25 loops | Cross-project and free-only/unattended end-to-end scenarios, cold starts, changed instruments, export/handoff and long-run reliability | Release qualification, not achieved by the current supervised fixture runs. |

Series sizes may change for sensible coverage; record the actual loop IDs rather than forcing a count. Reopen affected loops after changes. Do not claim that all product development is complete before beginning useful regression loops on a completed slice. A separate end-to-end release pass follows the broader build-out.

Between runtime/UI work, keep eligible configured-author/worker project jobs progressing with their own bounded allocations. Reconcile parked/uncertain work, avoid conflicting writers and do not manufacture activity by resetting exhausted attempts. Record failures and trainer assistance as carefully as delivered milestones.

### Advisor checkpoint — 2026-09-27 local date, 22:36 UTC on September 26

The read-only Astra advisor recommends completing and qualifying the existing delivery workflow before adding another planning abstraction. These are engineering suggestions, not new grants or completed tests.

The next implementation priority is **Map & Plan plus purpose-inference controls**. Restrictions must always be read; explicit owner specifications can support planning with inference off; an existing plan can drive Build with Map & Plan off; an empty folder without a plan must not infer its purpose through a hidden Build fallback. Neither switch enables scheduling, grants or Kaizen. Retained inferred suggestions remain labelled when inference is disabled. An enabled activity must be displayed separately from permission, available capacity and actual readiness. Current Operations means local report intake and current Optimize means hypothesis proposal, not complete production executors.

| Proposed next loop | Behavior to qualify; not yet a passing use-loop claim |
| --- | --- |
| B3.01 | Empty folder, inference off: preserve facts; no invented purpose or model call. |
| B3.02 | Inference on: visibly attribute proposed direction and assumptions. |
| B3.03 | Explicit brief, inference off: owner-directed planning works. |
| B3.04 | Existing plan, Map & Plan off: Build stays eligible and still reads restrictions. |
| B3.05 | Nested instructions retain scope; report text cannot grant authority. |
| B4.01 | Validate the original author file selection independently of today's packet policy. |
| B4.02 | Source changes after verification: refuse application and preserve both candidate and owner edits. |
| B4.03 | Show timeout, resources used and unrun owner phase; no pass or automatic reauthoring. |
| B4.04 | Proven preflight-only rejection: a future explicit reconciliation operation may create at most one linked replacement allocation, preserving the spent original. This operation still needs implementation and qualification; no reset is authorized by this row. |
| B5.01 | Disable/pause queued work without losing uncertain request identities. |
| B5.02 | Exhausted free routes: explicit capacity state, no paid fallback or counter reset. |
| B5.03 | Reconstruct pending work without duplicate dispatch; absent terminal evidence remains unknown. |

The project-track recommendation is to reconcile SupportHat's preflight identity before another author call. A read-only diagnostic now confirms its original 14-file author view and full snapshot match; that does not replace the historical stale verdict or reopen the spent allocation. GrowthHat remains parked. The next separately justified author allocation should request only a discriminating serializer-cleanup regression, written by the configured instrument and assessed against the saved faulty candidate. If this smaller task is ineffective, change to a qualified available author or keep it parked; do not repeat the same combined request or assume an old credit balance is current.

## Status and use of this document

### Coverage addition: dashboards and feedback delivery

- **Owner-requested:** General and per-project dashboards, add/remove views, building/troubleshooting/optimization/operations progress, and goal-linked analytics/report/API-hook measurements. Initial implementation uses explicit local project/home registration plus receipt-only panels, not new connector or worker authority. Planned B6 loops cover adding, selecting, customizing, removing, conflict refusal and narrow layouts. B4/B5 recovery loops remain open; numbering does not imply completion.
- **Measured runtime gap:** a tests-only Growth author task added as a note was absent from the frozen request. Oldest-first note budgeting had consumed the available 3000 characters. The terminal response therefore cannot establish whether that model can follow the intended task. Whole-note newest-first selection, selected-draft/milestone priority, actual author attribution, visible omissions and pre-call refusal for oversized required feedback are now implemented and under regression review. Frozen requests/history remain unchanged. Check what reached the author before interpreting its behavior.
- **Product completeness:** dashboards must distinguish recorded activity, current in-process worker state and unverified cross-home liveness; show measurement definition/source identity and timestamps; never blend different units into one universal score. Removing a dashboard is not stopping a project. Later connectors require scoped credentials, read-only fetch policy, explicit refresh/backoff, provenance and redaction. A dashboard must not quietly create those permissions.
- **Trainer cadence:** rotate across subsystems, then zoom in on the current measured failure. Do not mistake the breadth of the backlog for permission to leave a small defect unverified or to keep retrying an author with undelivered instructions.

Drafted across the 2026-09-26/27 local date boundary during supervised field training; corrected to the present engineering scope on 2026-09-27. The same turn is implementing the first modes/local-measurement slice and improving the manual chat relay. Those changes require their own test receipts; production adapters, configurable conflict-safe parallelism and the full unattended release contract are not established by this document.

Use this file and Lars's additions record as a coverage map. Record shipped work, failures, assistance and remaining gaps in the four trainer logs. Do not edit the finished paper or replace existing product documentation as part of this task.

### Latest coverage checkpoint — 23:33 UTC

B3.01–06 planning-control/browser loops and B6.01–07 dashboard loops now pass with B1/B2, **23 loops total**. B6 covers General/project views, explicit isolated-home registration, stale measurement/unknown cost/liveness labels, hide-all/restore panels, concurrent-edit refusal, three viewport sizes, cancelled removal and view-only removal. No worker/settings/project-delete API was called by B6. B4/B5 remain proposed and uncompleted. Browser fixture routes are not a live Studio/router commissioning test.

Broad Python regression:322passed/1Windows-symlink-creation skip in382.09s. Final dashboard-specific15passed/1skip includes a mocked-link rejection test and refusal to infer enabled modes from an unknown saved schema. Actual revision-context and chat-relay renderer tests pass;16frontend modules explicitly parsed as JavaScript modules. A missing closing parenthesis introduced in the feedback drawer was caught and corrected before these final passes. Fresh dashboard desktop/phone screenshots were inspected; Goals phone overflow is fixed.

Growth delivery checkpoint: the exact task note absent from jobmj_27e9f7d4a8924b8dbc62 is fully present in the new frozen jobmj_2056b2617b8341f08c5b. The latter free Gemini author changed only the permitted test file. Its new regression raises the known bad-file-descriptor failure on the saved faulty implementation, so it detects that defect. It does not directly assert descriptor closure and has no corrected positive control yet. Candidate remains unverified/unapplied. Treat this as a useful development observation, not an effect-size estimate or automatic acceptance.

Next bounded options: rotate to Support's explicit retained-candidate reconciliation/B4 recovery work, or commission a separately scoped implementation correction using the now-authored regression, without weakening it or reopening old allocations. The next hourly read-only advisor may run no earlier than23:36UTC. Live connectors, meaningful production runbooks, concurrency and unattended release qualification remain backlog work.

### B4 implementation checkpoint — 2026-09-27 local date

Astra's23:40UTC read-only review led to a narrow linked preflight reconciliation rather than resetting the spent allocation. New operation and actual Work > Drafts UI bind the original receipt/history, original model-visible view, full source/candidate, owner bundle/public criteria, current controls and runtime-fix fingerprint. Exclusive durable creation provides at-most-once reservation across callers. Unknown/corrupt/interrupted replacements cannot execute again. Prior outcomes remain unchanged and the replacement cannot be the parent of another replacement. The fixed original ceilings are shown before authorizing. A successful result records evidence only, leaving application to a separate guarded decision.

Legacy qualification is explicitly **adjudication from a specific rejection path plus ledger and run inventory**, not instrumented historical phase evidence and not zero elapsed time alone. This exception does not generalize to an unknown subprocess or lost provider response. Stop/disablement is responsive before subsequent phases; the current bounded subprocess is not claimed to stop instantly. Future general recovery should have explicit phase-start/completion receipts so fewer legacy inferences are needed.

-32new backend tests pass;203related regression tests pass (overlapping count). They cover actual tiny candidate/owner execution, no automatic apply/inference, changed queued inputs/authority, corrupt receipts, duplicate callers, restart, timeout, and between-phase revocation.
-B4.01–07 now pass as seven browser-fixture loops: original/current context distinction, cancellation, blank/Escape refusal, stale quote, consumed-slot display, timeout versus unrun owner phase across three viewport sizes, and separate simulated stale-source application refusal. Combined B1/B2/B3/B4/B6=30loops/88simulated requests. First B4 cancellation failed and exposed a real shared modal bug; fixed explicit-null handling, then reran all series. Actual frontend/CSS is exercised; live API/router commissioning is not established.
-Support's Opus-authored retained m6 entered its one replacement at23:55:44UTC,360s project+240s owner. No new inference or file application; the field outcome is pending at this entry. Do not count synthetic recovery qualification as project acceptance or self-authored Subject improvement.

**Next B5 series, still pending:** queued pause/disable; positive preservation of uncertain request identity; exhausted free routes with no paid fallback unless explicitly configured; restart reconstruction without duplicate dispatch; completed versus unknown cancellation; and absence of cross-home writers. Pair frontend behavior with actual backend invariants. Then rotate to safe operational adapters or a separately justified Growth implementation correction rather than endlessly revisiting one serializer. Neither this list nor the advisor grants new production permissions.

**Field closure00:03UTC / interface-completeness gap:** Support completed61project checks in163.027s and16owner checks in48.818s, with1owner error. OverallFAIL retained, no apply. The missing handoffs output member was an unstated public response requirement, confirmed against the original frozen104059-character author prompt. This is not a clean test of whether the author obeys an explicitly stated schema. The next product addition should help operators declare command/API response fields, types, units, nullability and error behavior prospectively. Contract revisions must remain versioned, invalidate stale verification and leave spent author/check allocations unchanged. Keep private synthetic cases/assertions separate; a schema is an interface specification, not permission to expose the private test program. Any later corrected pass must disclose the clarification. No new inference or automatic retry occurred in this recovery step.

### Interface completeness implemented; B5 partly covered — 00:30 UTC

The bounded public-response editor is now implemented in Goals & Plan and the author packet. It records flat typed fields for objects/arrays of objects, not arbitrary JSON Schema or executable conformance checking. Criterion links, version history, explicit clearing, invalidation and stale-edit refusal are tested. The ordinary criteria editor preserves existing interfaces. Clarification does not restore spent budgets. Context focus can be selected after public clarification because selecting context itself grants no author/check authority; source/candidate/milestone bindings still hold.

B7.01–06 pass: criteria-first gating; typed fields and required/nullable/unit controls; blank-reason refusal; three responsive sizes; exact payload/readable milestone; stale edit preserving unsaved input; and cancellation versus explicit removal without model/worker calls. B4.08 adds explicit author-only supplement dispatch. All37B1/B2/B3/B4/B6/B7 loops pass together after fixing narrow-screen overflow and a harness transition that had not waited for a pending Work refresh. Screenshots and renderer checks are retained. Backend124related tests and51final focused tests pass, with substantial overlap.

B5 now has four **backend** lifecycle tests: paused state survives worker reconstruction, queued work waits for resume and deduplicates, stop/pause observes step boundaries, write conflicts pause, and interrupted provider/check receipt identities stay unchanged without replay. Visible restart guidance directs users to reconciliation. Do not mark the full B5 series complete: quota-exhaustion/live-response/cancellation interleavings and actual top-bar use still need further coverage.

Field lesson from the trainer itself: a real prompt is a JSON object plus appended operator notes. A JSON-only safety guard rejected it before calling the router and consumed the recorded supplement locally. The parser is fixed and tested against a real generated packet; prospective validation now precedes reservation as well as actual dispatch. The failed local receipt remains intact, no model call was made, and no silent retry was performed. Any later new allocation must distinguish this proven local failure from an uncertain submitted request. Keep this assistance visible; it is not author-model failure or new scientific Subject improvement.

Next rotate to a separately scoped project correction or finish B5 UI/capacity loops, retaining original failures and private fixtures. Broader production adapters, concurrency and unattended end-to-end release requirements remain open. The finished paper and existing product documentation remain out of scope.

### Qualified execution path: next engineering target — 00:50 UTC

Supportm6 is now accepted and applied:61project plus16owner checks passed under the prospectively clarified public interface, and Studio's actual read handlers expose the receipt. A free Gemini author supplied the narrow correction to retained Opus implementation/tests. The requested extra regression was omitted and remains a follow-up; no standalone free-author, autonomous, business-outcome or scientific claim is justified. See the four logs for original failures, protected hashes, model/job/cost attribution and the separate guarded promotion.

The trainer itself exposed two orchestration defects: assuming the full prompt was JSON, and passing the wrong checkpoint signature. Both were caught and fixed with retained failure records and isolated tests, but custom wrappers are still a deployment weakness. The00:40 advisor recommends a bounded refactor, **not yet implemented**:

1. Define a structured job request shared by Worker/Studio and synchronous callers, with one checkpoint contract and explicit stage/authority inputs.
2. Treat rendered prompts as opaque strings. Supply structured context directly to validation instead of reparsing appended prose.
3. Validate before reservation as well as before execution; bind input hashes, authority and durable request identities. Preserve unknown/started records without automatic replay.
4. Qualify the exact public entry point with tiny real project checks, owner checks and separate guarded application, including stop/revocation, stale inputs and failed callbacks.
5. Exercise the connected Studio controls in the unfinished B5 series. Keep author response, generated tests, owner acceptance and application as distinct visible states.

Do this as a small reusable seam rather than a new sprawling retry subsystem, then rotate back to Growth's regression-driven correction or Supportm7. No protected project documentation, finished paper, PRHat operations or production authority is implicated by this proposal.

### Execution seam implemented; qualification in progress — 01:16 UTC

`BuildJob` plus `execute_build_job` now provide a validated, zero-argument-checkpoint contract for ten existing build/recovery operations. `run_synchronous_build_job(root, request, home=...)` is the supported one-shot path when no resident Studio owns the home: it takes the OS lock, refuses current/interrupted/paused/manual-wait state, runs the normal Worker/history/accounting path without background startup, and suppresses follow-on scheduling without changing owner settings. With a resident Studio, use its API queue instead. This does not create a new override for expired author budgets, check deadlines or integration grants. Prompts remain opaque; structured author-packet metadata is a separate future task, not supplied by this job-request schema.

The real field lesson also led to ordinary verification checking controls between phases. An interruption stores completed project checks plus explicitly unrun owner acceptance as inconclusive; it cannot masquerade as a defect verdict, acceptance or another automatic attempt. Activity exposes that boundary and distinguishes current-job Stop from queue Pause. Jobs now refresh on worker events and warn that a completed job need not have passed acceptance.

Eight B5 scenarios and all45combined frontend-fixture loops pass (132 simulated requests); desktop/tablet/phone bounds checked and phone screenshot inspected. Final expanded Python regression is running. Development errors and their fixes are recorded rather than hidden. Still open: full top-bar interaction coverage, provider exhaustion/response-loss interleavings, durable queued-job restart behavior, cross-home overlapping-root exclusion, configurable concurrency, production adapters and genuinely unattended commissioning. Keep these separate from the narrower B5 control coverage achieved here.

**Closure01:21UTC:** final341Python tests passed328.84s, all45UI-fixture loops passed, desktop/phone screenshots inspected, syntax/whitespace checks clean. Real tiny candidate/owner/apply fixtures exercise the shared route; lock/current/pause/manual conflicts refuse it. A sequential-queue fixture confirms Stop finishes the current job at its boundary and does not pause the next job or overlap execution. No live home/provider job ran through the one-shot entry point in this step. Next rotate to an eligible, separately scoped model-authored project step with intact source/receipt/budget checks. The larger release requirements above remain unresolved; do not extend this bounded qualification into an unattended-readiness claim.

### Preserve behaviors across revisions; make review evidence visible — 01:38 UTC

Observed field case: Gemini authored a correction to a retained export function, preserving all tests and passing the new model-authored serialization regression. The existing race probe nevertheless changed from preserving a competing file to overwriting it. The trainer parked the candidate. This is a concrete reason to retain a compact, source-bound set of prior behavioral diagnostics alongside the latest failure, and eventually have project authors encode discriminating regressions for each. It is not evidence that one prompt strategy or model family generally succeeds/fails, nor permission to expand hidden acceptance retrospectively.

Completed UI slice: saved reviewer/reason/notes are visible in Drafts, separated from executable check status; manual-write confirmation distinguishes unresolved review, unrun checks, project-only success and owner acceptance. Cancel/Escape submit nothing, content is escaped, and the notes action reads the existing draft notes. No backend permission change or claim that a warning prevents all manual bad writes. B8six scenarios/all51combinedfixtureloops pass with desktop/phone inspection;32focusedPython tests confirm projection is read-only and does not promote feedback into verification. A first full-browser request-timing assertion was corrected to await the exact request, then rerun successfully.

Next integration suggestion, not a completed feature: explicit author-only revisions should have a supported typed Worker/Studio/trainer job with one durable allocation, exact candidate/feedback binding, no implicit check/apply, and all current pending/paused/source guards. The latest field call used the existing focused-revision API under lock because the shared ten-job entry point cannot represent it. Avoid another collection of private wrappers or a general retry framework; retain unknown outcomes and old budgets. Rotate to another useful subsystem or eligible project step before buying another attempt on this parked Growth defect.

### Revision integration completed, broader release work still separate — 2026-09-27 02:16 UTC

Implemented the prior suggestion through a shared `revise` job and actual Studio confirmation drawer. This is deliberately an author-only operation using a provable existing ordinary allowance, not a fresh revision entitlement. It binds source, candidate, contract, private owner-bundle identity (not content sent to the model), focus, attributed feedback, selected instrument and exact prompt/limits. Durable operation/attempt reservations and immutable packet linkage allow duplicate and saved-ticket handling without a new POST; an unknown or damaged history cannot silently become an unused budget. It admits an unverified draft, with executable checks/application/advancement left separate.

Development revealed why recovery needs its own tests: a call's newly written timeout must not be mistaken for input that existed before it was sent; that one receipt is excluded from input reconstruction, while earlier failures and all genuine input changes remain checked. A just-returned answer must not block itself as an unrelated pending job. The browser loops caught label/timing mistakes, and screenshot inspection caught a visible null and undersized input. All were corrected and rerun. Final99focusedtests and59B1–B9frontend-fixtureloops pass; expanded226tests passed earlier in this checkpoint. No live-provider or unattended-operation confirmation is inferred from those fixtures.

Next rotation: prospective Supportm7 JSON-input requirements/acceptance, then configured-instrument authoring—not another Growth retry or repetition of acceptedm6. Keep remaining work explicit: legacy allowance reconciliation, whole-program budget semantics, durable queued-job restart, overlapping-root write exclusion, adjustable concurrency, live metrics/operations adapters and full unattended commissioning are not solved by this revision drawer. Four logs carry fresh preserved-home evidence and zero new gateway spend; existing paper/product docs/site remain untouched.

### Separate initial acquisition and respect capacity evidence — 2026-09-27 02:36 UTC

Filled the initial-authoring companion gap with shared `build(author_only=true)` and a Studio confirmation, without temporarily disabling checks or altering apply grants. Ordinary attempt custody still applies and no follow-on job is queued, including at the cap. This lets a user inspect a candidate and choose a justified check budget instead of knowingly invoking a too-short default suite. It is not a concurrency, scheduling or global-budget redesign.

The first field use hit an important unattended-use boundary: Milliner reported a daily cap and two open circuit breakers before returning any model output. A failed provider allocation must not become a claimed bad patch or trigger repeated blind author attempts. Preserve the terminal ticket, requested/actual-model distinction, individual route outcomes, estimate coverage and recorded cooldown (about07:00UTC here, not a promise). The default paid-capable author role was restored after the bounded free call; later dispatch must inspect fresh routing/credit. A future bounded improvement could surface saved provider cooldowns directly beside author selection and prevent unchanged unavailable routes from consuming repeated work, while preserving explicit user overrides and not silently switching to paid inference. That cooldown feature is a suggestion, not implemented or qualified in this checkpoint. Four logs carry source/fixture custody, UI/runtime qualification and the single $0estimated gateway result.

Closure02:45UTC adds a concrete cache/budget lesson: matching a cached candidate requires its selected context as well as full source/contract. Even matching predicates cannot make two observations atomic. The builder now directly reuses the already-matched candidate; it does not call a planner that could recollect changed focus/source and dispatch without a reserved attempt. Stale candidates remain stale and cannot trigger an inference fallback. Two static failures were reproduced before fixing; advisor02:40 recommended direct reuse and boundary regressions. Final92focusedtests pass after that closure, with64frontend loops green; earlier210expandedtests passed before the final adjustment. This is a narrow engineering improvement, not proof that broader budget, queue restart, parallelism or unattended deployment requirements are finished. Four logs preserve failures, sources, attribution and the terminal no-author-answer field result.


## 2026-09-27 03:17 UTC — bounded availability surface implemented; accounting gap identified

Implemented the earlier saved-cooldown suggestion as a read-only retained-evidence view in Thinking power. It is intentionally not a live quota oracle or scheduling block: bounded-window coverage, identity matching, unknown states, elapsed waits and unresolved tickets are displayed honestly; it does not spend tokens or automatically switch to paid models. The older Route dialog was actually blank because its mock and real modal disagreed; actual-browser loops now guard that boundary. Final127focusedtests and74B1–B11UIloops pass; four logs preserve failures and validation scope.

New concrete requirement for a later bounded slice: **cost accounting must include failed provider/format attempts and late recoveries exactly once.** A single pinned-model request can still cause multiple format attempts. This Supportm7 job had three12000-output-token attempts but Milliner's aggregate reported0tokens/$0. Preserve that raw mismatch, surface unreliable coverage, calculate a clearly labelled estimate only where attempt usage/prices are known, and reconcile a late result without duplicating the original call or charge. Account balance deltas are shared-account observations, not per-job invoices. The one-attempt estimate was not a valid maximum for the gateway job; cost limits need an explicit format/retry envelope or conservative multiplier before further paid authoring.

This checkpoint has no new Hat implementation or acceptance result. Supportm7 remains open with two consumed ordinary attempts; Growth's earlier no-clobber failure remains parked; PRHat stays read-only. Do not add more calls just to keep instruments busy when the remaining route or budget is unsuitable. The next trial needs a deliberate route/packet choice, unchanged public requirements and separately adequate verification time. No paper/product-doc/site changes; next hourly advisor eligible03:40UTC.


## 2026-09-27 03:49 UTC — failed-attempt/late-recovery accounting slice implemented

The prior field requirement now has reusable implementation and visible Studio controls: qualify provider-attempt usage independently of success; reject a contradictory aggregate estimate; preserve raw metadata; count one bound gateway ticket once when its retained state moves from pending to terminal; disclose invalid/unreadable/omitted/conflicting evidence; show covered subtotal rather than implying total spend. Missing metadata has unknown attempt count. A cached report is not automatically assigned as fresh billed usage. Historical instrument identities stay visible after routes change.

Thinking power's Usage & cost coverage and general/per-project dashboards share this projection. Legacy host callbacks are not treated as distinct provider attempts and their old estimates are not added to gateway totals. No provider call, current-price lookup, retroactive receipt rewrite or project mutation is triggered by inspection. This is deliberately not a billing engine or hard dollar limit. Next distinct reliability targets remain interrupted-work/queue recovery, safe overlapping-root exclusion and a truly bounded gateway retry/cost envelope; do not broaden this accounting slice merely to keep busy.

Qualification:184expanded tests passed/1platformskip,final affected81passed/1skip,82B1–B12actual-frontend/simulated-API loops passed plus clean isolated8-loop rerun. Master log retains red reproductions, test-construction and assertion corrections, visual review and unchanged53Support/106Growth protected records. No new Hat candidate, owner acceptance, autonomous Subject-improvement result or scientific confirmation. Four logs/current engineering records only; finished paper, existing product documentation and site untouched.

Advisor03:40 refinement: logical-request and ticket identities both matter. A retained pre-ticket copy may alias its terminal copy only by the exact request ID within the same gateway/caller, while body similarity is insufficient. Conflicting tickets for one request stay unresolved. Separately expose estimates based on aggregate metadata without attempt history; valid aggregate fields are not an independent cross-attempt check. Missing attempt history is unknown, not an invented0. Five regressions reproduced these boundaries before implementation; next advisor eligible04:40UTC.

Final post-advisor closure: **189runtime tests passed,1platform skip**, all82B1–B12UIloops passed again. Final isolatedB12's8loops also passed using the exact production API scope/caution wording. Desktop/phone visual checks complete. Final03:48:13–18custody audit reconfirmed unchanged Support/Growth sources and53/106protected records,all3homes idle,no pending work,no live PRHat scan. Receipt: training/trainer-receipts/accounting-audit-20260927T034813Z.json. No new model calls; four logs and both authorized engineering records closed together. Next advisor eligible04:40UTC.

Accounting scope: zero new Milliner/project-instrument calls. External Codex trainer and read-only advisor work is separately attributed above and is not priced here.


## 2026-09-27 04:20 UTC — Implemented B13 restart custody and Studio controls

- **Added:** durable single-writer queued intentions; commit-before-acknowledgement and marker-before-dispatch ordering; restart review hold; deduplicated completed/interrupted outcomes; strict/corrupt-record refusal; queue-aware synchronous runner; recovery receipt retention across interrupted set-aside. No generic retry or hidden budget reset.
- **Actual UI:** Restart recovery panels in Activity Live log and Jobs, parameter inspection, revision-bound reviewed Keep / Set aside controls, separate Resume, visible blocked-storage states. Phone layout refined after screenshots. Review is an acknowledgement, not provider reconciliation or project acceptance.
- **Validation:** final integration run: 309 passed in 285.44s. Two additional, distinct real-process-exit tests passed in 3.55s (claim interrupted / completed outcome retained): 311 distinct final backend checks, not a full-repository suite. Earlier overlapping runs were 63 passed, 149 passed, and 33 edge/lifecycle checks; do not add those counts. All 90 B1–B13 actual-frontend/in-memory-API use loops passed, 192 fixture requests, no browser errors. Final artifacts: training/.tmp/studio-use-loops-2026-09-27T04-17-49-031Z/. Desktop and phone screenshots inspected; 1440/800/390 widths checked. JS syntax and diff whitespace checks passed.
- **Fresh field custody 04:18:27–34 UTC:** all three existing home locks available; no resident Studio, current marker, waiting intention, recovery hold, pending author or manual request. Existing auto_work/Kaizen off and plan role author preserved. No live PRHat scan. Audit: training/trainer-receipts/restart-audit-20260927T041827Z.json. New audit fields read queue/hold state without initializing it.
- **Accounting/attribution:** zero new Milliner/project-instrument requests, job IDs none, new provider spend $0, estimate coverage N/A. This is external trainer-authored Runesmith engineering, not autonomous Hat authorship or scientific Subject-improvement confirmation. No new author answer, candidate, project acceptance or application. OpenRouter credit was not refreshed; the last $0.107401465 at 03:12:05 is stale, not current buying capacity. No advisor consultation in this slice: last 03:40 UTC, next eligible 04:40 UTC.
- **Boundaries:** all managed interpreter/browser/test sessions ended; heavy suites ran serially, with a lightweight custody audit during the final browser run. Temp/cache stayed on D: (C:2.69GiB/D:16.50GiB free at closure). No resident launch or denied-action retry. No Hat implementation, project test, grant, acceptance contract, finished paper, existing product documentation, website or presentation edit. Four trainer logs and the two specifically authorized engineering records updated.
- **Next bounded step / release gap:** code inspection found that Studio.open creates a Workspace before closing the prior worker, Worker.close requests a stop without waiting, and serve holds the initial home's instance lock. Reproduce and fix safe workspace switching / writer ownership in isolated fixtures before claiming unattended multi-project readiness. No live overlap incident was observed. This queue slice provides restart custody, not global exactly-once external effects, a power-loss durability guarantee, overlapping-root exclusion, or automatic uncertain-call replay. Existing dispatch-time mode, source, contract and allocation guards still apply after an explicit Resume.

## 2026-09-27 04:51 UTC — B14 closes handoff ownership, not global concurrency

- Added the actual home-lock lifecycle to Studio, request-lease/epoch isolation, drained-worker handoff and paused destination activation. Partial starts, constructor interruption, stale API actions, old event streams, destination contention and preserved queued intentions have tests. A worker retains its lease independently of the constructor's lifetime.
- Folder switching is no longer only a path picker: it exposes whether work can move, keeps timeout/uncertain outcomes explicit and has no implicit remote-call retry or budget reset. Delayed browse responses cannot alter the parent that a user confirms. Responsive screenshots caught and corrected a layout issue missed by the first assertion.
- **Validation:** final serial integration suite: 205 passed, 1 skipped in 153.67s. The skip is the pre-existing dashboard symlink case because symlink creation is unavailable on this host. This is not the full repository suite. All 101 B1–B14 actual-frontend/simulated-API loops passed (208 fixture requests, no browser errors); artifacts: training/.tmp/studio-use-loops-2026-09-27T04-50-21-605Z/. Final desktop and phone picker screenshots inspected; 1440/800/390 widths checked. JS syntax and diff whitespace checks passed. Earlier overlapping 45/79/197-pass development runs are not additive.
- Advisor at 04:41 UTC supplied the exception and confirmation-race checks; next consultation no earlier than 05:41 UTC. All field homes unchanged, no new inference cost. External trainer assistance and the corrected empty-path fixture escape are recorded in the master 04:51 entry and incident manifest.
- **Remaining release work / next bounded step:** this is one active Studio home, not concurrent multi-project execution. Per-home ownership does not exclude equal/nested source roots through different homes. Recent-folder records still omit custom-home bindings: the tested same-root no-op preserves an isolated home, but switching away and revisiting via recents is not yet a safe isolated-home launch mechanism. Next address explicit root/home registration, revisit fidelity and overlapping-root admission before broader concurrency. Keep PRHat on its explicit isolated-home path; do not launch it via recents. No global exactly-once external-effect, power-loss or unattended-production guarantee.

## 2026-09-27 05:18 UTC — B15 closes known revisit and cooperative overlap gaps

- Separate execution identity from recent-folder convenience: durable root/home bindings, strict parse/conflict refusal, serialized registry writes and explicit root/home UI review are now implemented. A missing known home blocks; an existing home cannot silently be rebound. Legacy field homes were not automatically registered.
- A home outside the source tree is writable state too. Coalesced root/home scopes receive exclusive OS leases and shared ancestor leases, preserving sibling concurrency while refusing cross-home root overlap. Studio lifetime/drain and one-shot jobs retain them; partial acquisitions and fixture process death release them. No stale-PID unlock heuristics or deletion of live lock files.
- Final serial integration run: 231 passed, 2 skipped in 185.21s across ownership, switching, Studio, worker lifecycle/restart, shared build jobs, modes/measurements and dashboards. One additional distinct authenticated HTTP selection test passed in 1.99s: 232 distinct passing checks in total, not the full repository suite. Both skips require unavailable host symlink creation. Earlier overlapping 39/88-pass runs are not additive. All 109 B1–B15 actual-frontend/in-memory-API loops passed, 227 fixture requests, no browser errors; final artifacts: training/.tmp/studio-use-loops-2026-09-27T05-16-27-692Z/. Desktop/phone picker and pair-confirmation screenshots inspected; 1440/800/390 widths checked. JS syntax and diff whitespace checks passed.
- Zero new Milliner/project-instrument requests; job IDs none; new provider spend $0, estimate coverage N/A. External trainer authored reusable Runesmith runtime/UI/tests, not Hat implementations. No new author candidate, owner acceptance or scientific Subject-improvement confirmation. OpenRouter credit was not refreshed: $0.107401465 at 03:12:05 remains stale. No advisor consultation this slice; last 04:41 UTC, next eligible 05:41 UTC. All field custody checks remain unchanged; see training/trainer-receipts/binding-audit-20260927T051434Z.json and the four B15 trainer entries.
- This protects cooperating Studio and synchronous-build writers using the same OS user profile; it does not constrain other apps, legacy direct Workspace/Worker/kernel entry points, other users, hard-link/mount aliases or an external process replacing paths/control files. A single Studio still runs one home. Moving/deleting a profile, home migration, adjustable parallel scheduling, production adapters and unattended commissioning need separate qualification. Dashboard view registration is still read-only and is not execution registration. The three legacy field homes were not registered or relaunched by this step; PRHat still requires its explicit isolated-home path on any future authorized commissioning. Next rotate to measurements/operations readiness and evidence ingestion, or an eligible configured-instrument author step when fresh capacity and remaining allowance justify it; do not create extra retries to keep instruments busy.

## 2026-09-27 05:55 UTC — B16 closes a saved-evidence readiness gap

- A numeric result is not automatically usable now. Preserve immutable observations, project current readiness separately, record whether the latest selected paste matches, and make data-age policy explicit. Keep live-source claims, whole-population freshness, causal improvement and owner acceptance separate.
- A data-age limit is an optional definition field, checked both at dispatch and after a returned hypothesis. Re-measuring old data cannot refresh its timestamp. Changing evidence retains the already-returned answer for review and cannot silently buy another call for the same memo identity. A literal pre-change fixture qualifies backward compatibility.
- User paths were exercised in the real frontend against in-memory APIs: configuring/clearing age, timestamp refusal, expired/superseded/future data, Operations versus Optimize, retained hold reasons, read-only refresh, delayed GET versus unsaved edits, dashboard parity and narrow phone layouts. The 05:42 advisor's last-refresh and newest-row qualifications are explicit.
- Validation: 176 distinct backend passes overall, one unavailable-host symlink skip; 121 B1–B16 loops and final 12 focused B16 loops passed. Master log and measurement-validation-20260927.json retain evidence and development failures; repeated suites are not additive.
- This does not turn reports into live connectors or hypotheses into implemented improvements. Next rotate toward author/revision feedback and a useful field step only when real allowance/capacity supports it. Do not reset budgets, silently replay calls, cross PRHat's live boundary, or infer scientific confirmation from trainer-authored runtime fixes.

## 2026-09-27 06:27 UTC — B17 history must survive better feedback

- A feedback edit should improve the next packet, not create a new resource allowance. Ordinary Build, focused revisions and separately budgeted alternate continuation now share source/contract-proven historical accounting. Reservations remain consumed on failure, including pre-dispatch refusal; changing models or descendant draft IDs cannot replenish them.
- Missing lineage, ambiguous old scope, corrupted/nonfinite/duplicate-key records and unreadable directories are unknown, not unused. Retain old bytes and display reconciliation rather than infer new authority. A pre-call source/contract check prevents charging a changed packet to the old reservation. Saved candidates can still be reused without inference.
- Field inspection made this concrete: Support m7 really has 2/3 ordinary attempts used; Growth m5's zero matching ordinary rows do not establish a new budget. Its ordinary-build bypass is now closed. Future legacy continuation must be explicitly bounded and justified, not manufactured through note edits or artificial re-planning.
- Studio carries the distinctions: remaining/unknown/used continuation, disabled-action reasons, review navigation and GET-only refresh. Broader loops caught and fixed horizontal overflow in retained check details on phones.
- 247-pass integration (215.72s), then the final 29-pass allowance suite (19.17s), including two new unreadable-directory cases: 249 distinct backend passes, not 276. The 27 overlapping tests are not additive; the final directory guard was added after the broader integration. No skips. All 129 B1–B17 actual-frontend/in-memory-API loops passed (259 requests, zero browser errors), including eight B17 loops at 1440/820/390 widths. Not the full repository suite or field acceptance. Full receipts/failures/13 code hashes in author-allowance-validation-20260927.json; all four trainer logs updated. No project provider calls/spend, Hat implementation edits or scientific confirmation. Next rotate to an eligible field author step and broader release gaps, preserving the three existing projects and read-only PRHat boundary.

## 2026-09-27 07:05 UTC — B18 consent must survive downstream reuse

- Support intake is useful only when its sharing boundary matches the whole path. Sending a report to a repair model must not silently consent to episodic memory, author examples, evaluation replays or a different trial generation. Code inspection exposed that issue reuse would do exactly this; the new separate support-evidence channel and learning/trial exclusions are tested through real offline packet construction, not only mocked view payloads.
- Evidence identity must include the captured target path/kind/name, not a mutable map name. A same-name/different-folder race test now prevents misbinding. Selection changes are checked between steps, not advertised as cancellation of an already-sent request. Import cannot reopen a served failure or purchase a fresh attempt.
- UI separates local retention, inspectable provenance, explicit future sharing, budget omission and actual repair outcome. Refresh preserves unrelated unsaved fields. Corrupt records are unknown, not empty; duplicate import does not change selection. Phone field bounds, long hashes and inert raw text were exercised in the actual frontend.
- Final targeted backend suite: 162 passes, no skips. Full B1–B18 browser suite: 139 passing loops, with a final non-additive ten-loop B18 screenshot/assertion rerun. Engineering evidence/attribution/failures: TRAINER_LOG.md and training/trainer-receipts/support-report-validation-20260927.json.
- Still required: a deliberate retention/archive/delete design, more repair adapters, a report-to-reproduction path with separate authority, and live connector commissioning. This slice does not implement those or prove unattended operation. No new project instruments were called; next rotate back to an eligible configured-author step after fresh route/custody checks, retaining Growth's unknown lineage and PRHat's read-only boundary.

## 2026-09-27 07:33 UTC — B19 configuration is not readiness

- A release front door needs to tell users what will happen, what is missing and what needs their intervention. Overview now exposes saved automation policy, offline dependencies and truthful next actions; no missing/malformed health result can look green, no configured model is labelled tested, and manual relay remains explicitly human transport.
- The clean-venv diagnostic is a useful partial check: package assets/init work, while plain installation does not supply pytest. It is not the self-contained installer, browser launch, first authored build, restart/continuation or zero-rescue unattended journey. Preserve those distinct release gates.
- Final targeted backend 41 passes; full B1-B19 actual-frontend/in-memory-API 149 passes (304 requests, zero errors). Desktop/phone inspected. Initial lock-byte snapshot and busy-class test timing errors are retained; product guards were not weakened. No new model calls, Hat code edits or field acceptance.
- Comprehensive dated handoff: RUNESMITH_STUDIO_AND_RUNTIME_HANDOFF_2026-09-27.md. Recommendations, evidence/limitations and honest self-assessment are explicit. Suggested next work closes an installed clean-home journey and counts interventions; current general production/connectors/concurrency/soak limitations stay visible. Existing heartbeat and authority boundaries are unchanged.
