# Build additions from Lars — 2026-09-26

Owner requirements captured from this conversation. This is a new product-build record, not an amendment to the finished paper. Recorded at 21:46 UTC; implementation status below is a snapshot, not a claim that every requested capability already works.

## Release experience

Place Runesmith in a project folder, supply specifications of any useful form or level of detail, configure model names and credentials, choose modes and operating limits, and let it build, improve and operate without someone watching every step. Author, builder/worker and improver instruments may be free, paid, local or frontier models. A human or external AI trainer is a development aid, not a permanent hidden dependency of the released API-connected workflow.

Chat-author mode remains a supported alternative for users with frontier chat access but no API: a person copies requests and replies. That transport is necessarily human-assisted even if the rest of the workflow is automatic.

## 1. Real, independently enabled modes

The switches must change runtime behavior, not merely change a label. Put the active modes, definitions, instructions, readiness, running work and blocked reasons together in a prominent Studio location.

| Mode | Requested purpose |
| --- | --- |
| Map & Plan | Understand the environment, discover instructions, map capabilities/performance and determine useful goals and a road forward. Provide an explicit control for inferring purpose and proposing goals when instructions are sparse or absent. |
| Build | Construct the specified system or feature; break work into useful steps, implement, verify and integrate. A build-only objective is valid and needs no invented ongoing business metric. |
| Optimize | Improve an existing capability or outcome against defined measurements, preserving working behavior and recording tradeoffs. |
| Operations | Carry out the configured project's recurring and production duties automatically; observe results, respond to failures and report. It is not merely an inference-usage dashboard. |
| Troubleshoot / Bug hunt | Discover or investigate defects, including issues supplied through support logs, reports, text instructions or an authorized filtered intake. Diagnose, repair and verify within the enabled scope. |
| Custom modes | Add a named mode, clear definition, custom instructions and its own switch. Supported underlying actions and permissions remain explicit. |
| Self-improvement | Preserve and develop Runesmith's own measured improvement loop as a distinct control; Optimize must not silently switch it on. |

**There is no mutually exclusive mode selection and no limit on how many configured switches can be on together.** Build, Optimize, Operations, Map & Plan, Troubleshoot and custom modes may all be active. Resource limits constrain simultaneous actions, not the number of enabled modes. Scheduling must prevent one mode from starving the others.

Turning off Map & Plan or purpose inference does not inherently turn off Build or Operations. Existing specifications, plans and authority may still drive those modes. Reading applicable restrictions remains mandatory regardless of the inference switch.

## 2. Understand the folder before acting

- First look for applicable instructions about building, optimization and operations: project instructions, runbooks, goals, blueprints and relevant scoped guidance.
- Construct and maintain a map of what exists, how parts depend on each other, what works, what is unknown, and measured performance at different levels.
- Give explicit owner intent priority. Preserve the distinction between instructions, descriptions, measured evidence and inferred hypotheses.
- If purpose inference is enabled and specifications are absent, judge the likely purpose from the environment and propose a useful direction. Mark assumptions and uncertainty visibly; do not pretend they were supplied by the owner.
- Use support logs and measurement reports according to their configured interpretation. Report bodies and incoming messages are evidence, not new authority or executable instructions.
- Capture source paths, scope, hashes and observation dates so later decisions can be traced to the evidence actually available.

## 3. Automatic production operation

Lars's intended release includes **automatic production work**, not a permanent propose-only assistant. Once the user enables Operations and configures the project's operating authority, ordinary in-scope production actions should run without per-action supervision. Other enabled modes should likewise continue their authorized work automatically.

Configuration must explain which environments, paths, accounts, services, tools and runbooks may be used; which actions have live effects; applicable spend/rate limits; and how to stop or recover. An enabled production policy is explicit delegated authority. Guessing a folder's purpose is not, by itself, permission to send messages, deploy, spend money or alter an unrelated service.

New or materially broader authority must still be requested or reported as a blocker. Routine failures should invoke bounded recovery, not unnecessary questions to an unavailable user. Success must be measured honestly; a missing permission or failed measurement must not be reported as success.

The current training restrictions do not change: C:\dev\PRHat is read-only, its scheduler/Bellman/sender must remain untouched, and the denied Studio launch is not reauthorized by this product requirement.

## 4. Speed and safe concurrency

Expose understandable speed and concurrency settings. A speed choice should show its consequences for call rate, budget, latency and local resource use. Separately show active modes, in-flight jobs and jobs waiting on conflicts or provider capacity.

**Never run two concurrent operations that touch overlapping parts of the codebase.** Implementation requirements:

- Declare each job's read/write footprint before execution, including files, directories and relevant shared resources such as databases, outputs, dependencies and services.
- Resolve normalized paths, aliases and links before conflict checks. Independent-looking edits can still share a dependency or output resource.
- Use leases/locks to prevent write/write and relevant read/write conflicts. Unknown footprints must run serially or be refused, not assumed independent.
- Use isolated candidate workspaces, source-version checks and controlled integration. A worktree alone does not isolate external services or shared data.
- Revalidate before integration; retain receipts for interruptions and uncertain external/model requests. Never duplicate an uncertain paid call merely because a worker restarted.
- Expose conflict reasons and queue state in Studio. Turning a mode off prevents new work and is rechecked at safe boundaries; an already-started external request still needs accounting and reconciliation.

All modes may be on while the configured concurrency is one. Higher concurrency is a separate capability that needs evidence of correct conflict handling; it is not achieved by adding a slider alone.

## 5. Measurements attached to objectives

Provide an obvious place to define how a goal is measured, with helpful starting points for websites, stores, apps, tools and support/operational workflows. Examples include analytics events/conversions, completed orders, successful jobs, error rates, latency, quality outcomes and resolution times. These are choices, not mandatory metrics for every project.

A measurement definition should state:

- What it measures and which objective it informs.
- Source and connection/import method; whether that source is actually configured and functioning.
- Field/column/event mapping, filters and population/denominator.
- Unit, time window, aggregation and any target/threshold.
- Instructions explaining how to interpret it, including what counts as missing, invalid, stale or inconclusive.
- Provenance, data period and freshness. Changing definitions must not rewrite previous observations.

### Receiving measurements and support evidence

- Selected CSV or structured JSON reports dropped at a configured path in the project.
- Text pasted into a custom report field, with a declared format and field mapping; keep the receipt linked to the original payload hash.
- Read-only email intake restricted to configured senders/subjects/formats and the authorized mailbox scope. Do not scan unrelated mail. Record duplicate handling and parsing failures.
- GA4 and other service adapters, with explicit event/property mapping and narrowly scoped credentials. A local GA4 export is not a live GA4 connection.
- Build/test completion alone when that is the entire objective.

Treat support text and reports as untrusted data. Feed aggregate measurements and necessary summaries to models by default, not raw customer records. Never evaluate user-supplied formulas as code.

Measurements are evidence for decisions, not automatic proof of causality. A threshold crossing does not automatically establish that a code change caused it or satisfy an unrelated acceptance test. Empty data is not zero. Keep project checks, owner acceptance, business outcomes and scientific confirmation separate.

## 6. Inference and operating limits

Explain the practical tradeoffs in the UI:

- Free providers often impose tight quotas, lower concurrency, availability restrictions or changing model access.
- Paid providers still have rate limits, budgets and possible outages; payment does not make them unlimited.
- Local inference avoids a remote provider's per-call quota but remains limited by hardware, model speed, context and local concurrency.
- Show requested routes separately from receipt-confirmed provider/model authorship; make fallback order and current failures visible.
- Keep cost estimates, coverage and unknown costs explicit. Budget exhaustion should select an authorized fallback or park the work, not broaden spending silently.

## 7. Additional implementation requirements

These are trainer additions to make the requested behavior dependable:

- Separate activity switches from authority, scheduling, budget and connector readiness. Saving a mode does not silently change those other controls.
- Keep durable job state, resumability, rollback and an emergency stop visible.
- Persist learning from failures without converting a single observation into an unsupported general rule.
- Require fresh source/contract checks before applying delayed answers or merging concurrent candidates.
- Make production side effects idempotent or explicitly reconcilable where possible; uncertainty must remain visible where that cannot be guaranteed.
- Do not repeatedly purchase the same optimization proposal on unchanged evidence.
- Support a finite completed build as well as an ongoing operating objective.

## 8. Author strength, worker roles and frontier chat without an API

Added at Lars's request on 2026-09-26. Put this guidance in Studio's Thinking power setup, not only in a developer document.

There is no demonstrated universal minimum parameter count, price or model brand for authoring. Free is a pricing/access condition, not a capability grade. A connection test only establishes that a route answers; it does not qualify a model to design or change a system.

An **author** must integrate requirements, choose a coherent design, preserve interfaces and restrictions, produce complete changes in the requested format, and use validation feedback without concealing failures. Runesmith's Planner currently drafts plans and build files; its Improver proposes changes to Runesmith itself. These roles generally demand broader integration than a tightly bounded worker/subtask. Neither role name nor a frontier label guarantees success.

A **worker/subtask model** can operate with a smaller relevant packet, a narrower contract and mechanical checks. Smaller or cheaper models may be useful here. That is a task-dependent observation, not a claim that every small model repairs code reliably. Complex integration or diagnosis can also require a strong worker. Good decomposition helps but cannot make an incapable model correct by definition.

The practical minimum is a qualification on representative, bounded work:

1. It follows the actual packet and output format without inventing missing source, tests or permissions.
2. It produces a complete, applicable change and preserves unrelated behavior and interfaces.
3. It passes meaningful checks, including checks distinct from those it authored where feasible.
4. It can explain and repair a failed attempt using the recorded feedback within the assigned call budget.
5. The result remains valid after a fresh load/source check; cost, latency, failures and assistance are recorded.

Begin with a capable available model for authorship, qualify it, then test cheaper/free alternatives on the same bounded contract. If it fails, improve context selection, split the work or change the model; do not waive admission or acceptance checks. Match qualifications to the scope actually tested. A narrow successful draft is not evidence of general unattended competence.

### Manual frontier-chat author: user instructions

1. Open **Thinking power → Add thinking power → No key needed → A chat window**. Name the instrument and optionally record the chat/model you intend to use; no API key is required.
2. Assign it to **Planner** for plans/build drafts and, if desired, **Improver** for self-improvement proposals. In **Who does what**, move it to the preferred position for the intended role. Keep an API/local worker for repeated repair calls when possible. Assigning a role does not enable automatic work or self-improvement by itself.
3. Start the intended planning, drafting or improvement action. When a chat request appears in **Thinking power** or the top bar, copy the complete packet into the chosen model's chat. The packet's required JSON or file-block format is the contract; do not replace it with a prose summary. Check what source information you are sending to that service.
4. Paste the complete reply into the matching Runesmith request. An optional model name is a self-reported attribution label, not provider-verified authorship. Do not mix replies from different request IDs or edit the project behind a waiting draft.
5. If the format precheck refuses it, use **Copy correction request** in the same model chat and return the complete corrected answer. The existing **Send unchanged anyway** option bypasses only that early format check; normal admission, source freshness, tests and application authority remain in force.
6. Keep Studio running while waiting. Closing the relay panel is different from restarting Studio; unanswered requests may be set aside on restart and must be reconciled through the current request/recovery UI. A pasted answer is not proof that code was accepted or applied: read the resulting draft/check/apply receipts.

Manual chat is deliberately human-assisted transport. It gives users with chat-only frontier access an author option, but it cannot deliver a fully unattended workflow without someone carrying requests and replies. A fully automatic installation needs an API or local inference route for every role it may invoke.

The companion [Filling the blanks in building Runesmith](FILLING_THE_BLANKS_IN_BUILDING_RUNESMITH_2026-09-27.md) is the trainer's whole-product engineering backlog, not a manual for Runesmith's Build mode. It expands the release design and proposed implementation order. Neither document changes current training authority or asserts that the release checklist is complete.

## Implementation status at capture

| Area | Status at 21:46 UTC |
| --- | --- |
| Existing environment maps, briefs, blueprints, goals, checked builds and repair/self-improvement machinery | Present in Runesmith; field limitations remain as recorded in the four trainer logs. |
| Chat-author format validation and correction assistance | New local backend/renderer checks passed; no fresh frontier-chat trial or browser commissioning. |
| Modes, instruction preflight, local report measurements and measurement-based optimization proposals | Implementation in progress in this turn. Not yet qualified or presented as complete. |
| Dedicated Map & Plan/purpose-inference switch | Requested; still to implement/qualify. |
| All modes enabled together | Required. Serial execution in the first slice is not a limit on enabled switches. |
| Automatic production adapters/runbooks and live GA4/email intake | Requested; not connected or implemented by the initial local-report slice. |
| Speed selector and conflict-safe parallel execution | Requested; not implemented/qualified by the existing single-worker queue. |
| Three training homes | Automatic scheduling and Kaizen remain off; no mode/measurement configuration changed by writing this document. |

## Acceptance checklist for subsequent work

1. UI switches persist and actually govern manual and scheduled dispatch; queued work obeys later disablement.
2. Every configured mode can be enabled together, with fair progress under a finite budget.
3. Instruction-first behavior is demonstrated; inferred purpose is separately labelled and obeys its switch.
4. A dropped or pasted report yields a traceable, correctly filtered/windowed measurement; bad and absent data remain explicit.
5. Operations uses the configured intake and production authority without unrelated side effects or routine babysitting.
6. Optimize consumes the actual observation receipt and produces a checkable hypothesis; further implementation needs the appropriate test/acceptance contract.
7. Concurrency tests demonstrate independent jobs progressing and overlapping jobs refusing or waiting, including restart and stale-source cases.
8. A representative unattended run completes useful work with no undocumented external trainer interventions; its UI, logs, authorship and costs tell the same story.

Further completion evidence belongs in the trainer logs and subsequent dated status entries. This requirements record must not be mistaken for a passed acceptance checklist.

### Follow-up qualification — 2026-09-27 local date (22:21 UTC on September 26)

The first modes/local-measurement implementation passed a 180-test targeted regression run and five isolated browser interaction loops, with actual frontend/CSS and simulated API responses. Local report intake, explicit mode policies, instruction preflight, aggregate-based optimization proposals and manual-author guidance now have bounded test evidence. Browser review led to collapsed policy details, closer save controls, a tablet-width layout fix and capped notification stacks. This is not a resident Studio launch, live connector test or unattended release qualification. Production adapters, Map & Plan/inference switches and conflict-safe configurable concurrency remain open requirements. Training home automatic-work/Kaizen settings remain unchanged.

### Follow-up qualification — 22:40 UTC on September 26

B1 and B2 now pass together as ten isolated browser loops. B2 covers keyless manual-author setup, role defaults, request copying, format refusal/correction, cancelled override, typed-reply retention across event refresh/navigation, and explicit skip. The relay retains unsent replies only in the current page session, not across browser/Studio restarts. Additional renderer checks guard request-identity changes and prune obsolete replies. Seven new failing corrupt-mode tests exposed missing validation before scheduling; common saved/API policy validation now blocks malformed settings without replacing their bytes. The ensuing focused modes/manual suite passed 80 tests. These counts overlap the prior suites and are not independent experiments.

The 22:36 read-only advisor checkpoint prioritizes explicit Map & Plan/inference controls and delivery/recovery qualification next. Its proposed B3–B5 loops and precise control interactions are recorded in the companion backlog. Broader release requirements remain open.

### Additional owner requirement — 2026-09-27 local date

Lars requests a general dashboard showing building, troubleshooting, optimizing and operations, alongside goals/objectives and the analytics, reports or API/webhook sources connected to them. Every project needs its own dashboard; users must be able to add and remove project views. Panels should expose useful progress and obstacles together, without implying that an enabled mode is running, a proposed improvement is achieved, or a connected data source is current.

The implementation slice now being qualified adds a General view, per-project views, panel visibility and explicit local project/home registration. It reads existing saved receipts only, does not instantiate another Workspace, and never starts workers or deletes project files when views are added/removed. Cross-project receipt reads are not atomic or liveness checks. Live API/webhook/email/GA4 connectors remain a separate unimplemented requirement; local export receipts can already appear. Missing, stale-definition and malformed evidence must remain visible. Dashboard settings must not change execution grants or mode switches.

### Qualification closure — 23:33 UTC on September 26 / September 27 local date

- Map & Plan and the separate purpose-inference switch are implemented in the runtime and Studio. Explicit owner direction works with inference off; existing plans remain buildable with planning off. Returned plans are held rather than installed when relevant inputs or controls change during the call. Old v1 policies gain no enabled new activity from a read-only migration. No training-home scheduling or grants changed.
- Dashboards are linked from navigation and Overview. General/per-project views support adding/removing explicit local project/home pairs and showing/hiding all five panels. They expose recorded build/goal status, modes, local measurement receipts and connection limitations, work history, and model/cost coverage. Refresh reads receipts; it does not fetch new analytics or operate the project. Removing a view preserves every project file and worker. Current-project dashboard remains available; all its panels may be hidden.
- B1+B2+B3+B6 pass together as **23 isolated frontend loops**, with actual renderer/CSS, intercepted fixture APIs and screenshots. These are not a resident Studio or live connector test. B4/B5 recovery work remains open. Broad Python regression **322 passed, 1 skipped**; final dashboard-only tests **15 passed, 1 skipped**, overlapping the broad run. Actual symlink creation was unavailable on this Windows account; a separate mocked-link rejection case passes. Real junction/cross-platform qualification remains outstanding.
- A field-discovered note-delivery bug is fixed and visible in Notes/Revision packet: newest complete relevant feedback takes priority; omitted notes are explicit; oversized required draft/milestone feedback blocks before inference. A new free-author call with verified task delivery produced a tests-only regression which caught the saved Growth defect. The implementation still needs correction and normal acceptance. This is field engineering evidence, not autonomous Subject improvement or a new scientific confirmation.

Production adapters, live API/webhook intake, configurable safe parallelism and an unattended end-to-end release run are still open. These qualification results supersede earlier dated “still to implement” entries for Map & Plan and receipt dashboards only.

### Recovery/control qualification — 2026-09-27 local date

- Work > Drafts now exposes one explicit linked, recheck-only recovery for a specifically evidenced legacy author-view preflight refusal. It identifies the spent parent, unchanged input/criteria/owner-test bindings, adjudication basis, fixed project/owner ceilings and immutable history. It does not turn a timeout into failure or success, buy another author call, reset budgets, apply files, or grant an unlimited chain of extensions. A corrupt/interrupted reservation remains consumed. Revocation is checked before the next phase; an already running phase may finish within its ceiling.
- **Shared control defect found through use:** the Cancel button of a text-entry modal was returning its label instead of null. The shared modal now preserves explicit null cancellation. Cancel, Escape and empty recovery reasons produce no request. This is a concrete benefit of exercising buttons, not just testing backend functions.
- New recovery backend tests:32passed. Broader related regression:203passed in225.59s, overlapping the32. B1/B2/B3/B4/B6 now total30passing actual-frontend/intercepted-API loops, including seven B4 recovery scenarios. They do not imply every Studio control or every platform is covered. Support field recheck began23:55:44UTC with360/240s limits; its outcome must be read from the eventual receipt, not inferred from these synthetic tests.
- Next coverage rotation remains B5 execution controls/capacity/restart reconstruction. No resident Studio has been commissioned; a denied launch has not been retried. Production adapters, live connectors, nonconflicting parallel writes and genuinely unattended end-to-end operation still require their own qualification.

**Field outcome appended00:03UTC:** Support's retained Opus4.5 candidate completed61project checks successfully;16owner checks completed with1error, so overallFAIL/no apply. The handoff-response field expected by the private fixture was not specified in the original public contract or actual frozen prompt. Preserve that failure and publish a prospective explicit response schema before a separately bounded model-authored correction; do not weaken the fixture or spend another blind retry. Recovery therefore produced usable evidence, not a completed milestone. All older receipts and source stayed unchanged; no new inference call.

### Response interfaces and restart controls — September 27, 00:30 UTC

- Goals & Plan now has an explicit public JSON response editor beside each milestone's criteria. Operators can declare commands/APIs, object or array-of-objects outputs, named field types, required/nullability switches, units, descriptions and criterion links. These versioned declarations go to authors; they do not run commands, generate private fixtures, validate executable behavior or prove acceptance. A concurrent edit is refused without discarding typed input. Existing criteria edits preserve declarations unless explicitly removed; removed criteria cannot silently orphan them.
- Work > Drafts now labels clarification as one **author-only** call, saving the answer for review with checks/application separate. It retains the existing bounded supplement rule and spent allocations. This helps users control model, test and integration stages individually instead of assuming all three succeeded together.
- Restart guidance no longer invites a blind resubmission: saved provider outcomes must be reconciled, and spent checks remain spent. Four backend lifecycle tests establish limited pause/resume/recovery properties; full B5 frontend/capacity/unattended qualification is still incomplete.
- Qualification:124related backend tests, then51final focused tests (overlapping);37combined browser-fixture loops across B1/B2/B3/B4/B6/B7. Six B7 loops cover the new editor and B4.08 checks author-only requests. New Goals phone overflow was caught and fixed. Actual frontend/CSS is tested against intercepted APIs, not a resident Studio.
- Support's real public contract was clarified prospectively. The attempted correction stopped in a trainer-written preflight guard before any provider dispatch; that failed receipt is retained, the parser fix tested, and no author capability, project pass or new self-improvement result is claimed. There was no new provider spend. See the four trainer logs for exact attribution and remaining work.

### Field follow-through — September 27, 00:50 UTC

The explicit public interface reached a separately commissioned free Gemini author, which corrected the retained Opus command. Supportm6 then passed61project and16unchanged owner checks and was separately applied through normal source/candidate/contract/grant guards. Existing Studio plan/work APIs expose m6done and the applied acceptance receipt. The original failures and contractv1 remain. This is a concrete field-use result for the declarations added above, not a controlled estimate of their effect, proof of autonomous improvement, or a fully free-authored milestone. The requested additional project regression was omitted; existing project and cumulative owner checks passed, and the omitted follow-up is retained in the trainer logs.

**Next proposed addition, not built in this heartbeat:** use one qualified execution entry point for the Studio worker and external trainer so a user does not need bespoke internal wrappers. Carry prompts as opaque transport strings with separately available structured metadata; validate operations before reserving them; keep checkpoint signatures consistent; retain explicit author/check/apply stages. Exercise the same entry point with small real candidate and owner-check fixtures plus B5 UI use loops. Do not turn local wrapper repairs into unlimited retry entitlement or silently replay uncertain model requests. This recommendation came from the00:40 read-only advisor and the trainer's observed parser/callback mistakes.

### Shared job path and visible execution controls — September 27, 01:16 UTC

The prior proposed job seam is now implemented for ten build/recovery operations. Studio's Worker and the new one-shot synchronous trainer runner use the same validated BuildJob dispatcher and normal history/receipts. The one-shot runner owns the home lock, refuses conflicting or unresolved work, honors queue pause/manual waiting, starts no server/thread and schedules no follow-on milestone. Existing router behavior, author/check budgets and integration guards remain. This is not yet a refactor of every repair/planning operation or a new structured author-packet API.

Candidate checks now recheck stop/pause/execution permission before each test phase. If stopped between phases, completed project evidence is retained, unrun owner acceptance stays explicit and the result is inconclusive; ordinary automatic builds cannot silently reauthor/recheck it. An active call/test may finish within its ceiling. Activity now shows separate queue Pause/Resume and current-job Stop controls, stopping feedback and live Jobs updates, with completion clearly distinguished from acceptance.

All45B1–B7 browser-fixture loops pass, including eight B5 scenarios; phone layout inspected. A final expanded Python rerun is still pending at this entry, after fixing test interface assumptions and an introduced syntax error. The four logs retain those failures. These tests do not establish live provider exhaustion handling, durable queued-job restoration, global cross-home write exclusion, adjustable parallelism or unattended-release readiness. Training Hat implementations and the finished paper were not changed in this step.

**Qualification closure01:21UTC:** final expanded regression341passed328.84s; all45frontend-fixture loops passed, desktop/phone screenshots inspected, module syntax and diff whitespace clean. The sequential-worker test confirms Stop does not pause the next queued job, and no two queued jobs overlap. The synchronous runner was tested in disposable fixtures only; a live training-provider run through it remains future work. All three project homes/source states were preserved and no provider calls were made. Earlier failures remain documented in the four logs; broader release gaps above remain open.

### Field-driven review visibility — September 27, 01:38 UTC

A free-author Growth correction made the preserved serialization test pass but regressed an already-passing no-clobber diagnostic. It was parked without full checks/application. This demonstrates a remaining requirement: retaining test bytes or fixing the latest failure does not by itself retain previously demonstrated behavior. The diagnosis/provenance is documented in the four logs; it is not a successful full milestone or Subject-improvement claim.

Shipped to actual Studio: Drafts now displays recorded review reasons, reviewer attribution and a direct notes action, independently of test/acceptance status. Manual-write confirmation explicitly lists outstanding checks/review and explains that a manual write does not establish acceptance. Existing owner/manual authority is unchanged; this is not an automatic backend block. Six B8use loops/all51combinedfrontend-fixtureloops and32focusedbackendtests pass; desktop/phone review screens inspected. The full fixture initially had an async request assertion race, now awaiting the specific request before asserting its payload.

Still open: bring explicit author-only revisions onto the shared typed execution path with visible, bounded authorization and frozen regression context. This field call used the existing focused revision API under a home lock because none of the ten shared jobs was an eligible author-only correction. Do not manufacture a requirements change, reset spent allocations, or imply the one-shot runner handled this call.

### Explicit author-only revisions — 2026-09-27 02:16 UTC

The narrow integration gap above is now implemented as the eleventh shared job, `revise`, with a read-only quote API and **Create one revision draft** in actual Studio Drafts. It requires a ready needs-revision candidate, explicit focused packet, included attributed draft feedback and a trustworthy ordinary-attempt lineage. It uses the remaining original three-attempt allowance; no extra per-candidate allowance or reset from changed notes/focus/IDs. Missing, damaged, exhausted or unresolved history blocks it. Source/candidate/requirements/owner-bundle identity/feedback/route/settings are bound and revalidated; a durable operation ID prevents duplicate dispatch and the immutable author packet retains that operation identity for recovery.

The user chooses the configured author and supplies a reason after seeing parent, scope, notes, remaining allowance and limits. One host dispatch/no host retry; gateway-internal fallback attempts and pricing remain separate. It saves an unverified draft only—no checks, apply, milestone advance or automatic continuation. Unknown submissions are not reposted, successful answers are retained before a stop/refusal, and saved-ticket recovery uses the same binding. This is not a redesign of all older build/correction/escalation/supplement budgets or an authorization to restart parked legacy work.

Qualification: expanded226tests passed, final99focused tests passed after hardening;59B1–B9actualfrontend/simulatedAPI loops passed, desktop/phone screenshots inspected. Runtime/recovery and browser-fixture failures plus the visible null rendering fix are recorded in the four logs. No new live gateway call or Hat mutation; Growth's parked legacy lineage remains ineligible. Supportm7 needs a prospective JSON-input contract before authoring. Broader unattended-release requirements remain open; no new scientific or autonomous Subject-improvement claim.

### Initial draft-only builds — 2026-09-27 02:36 UTC

Studio Drafts now also offers **Draft next milestone only**, backed by `build(author_only=true)` in the same Worker/API/synchronous runner. It keeps ordinary attempts and saved-answer recovery, reuses a matching waiting draft, forbids a simultaneous check-only draft ID, and does not implicitly generate a plan, execute checks, apply files or enqueue a replan/next build. Existing settings and grants stay unchanged; an already enabled schedule is not paused by this action. Confirmation states configured-author/fallback/cost limits; host retries are off. This provides an explicit initial-acquisition option alongside the previous candidate-specific revision action.

Supportm7 exercised the real shared path after prospective JSON-input commissioning: Milliner returned a terminal daily-cap/circuit-open failure, no model answer or candidate. Failed ordinary attempt remains consumed; no silent replay.63focused tests and64frontend-fixture use loops pass; a broader API-test normalization expectation is corrected and rerunning, with closure in the four logs. This is reusable trainer-authored engineering and a retained availability failure, not an autonomous improvement or m7completion.

Closure02:45UTC: corrected163test rerun passed. Review found that an old-context waiting draft could hide a new ordinary author call from its budget; two tests reproduced both a missing receipt and exhausted-cap bypass. Predicate alignment passed210expandedtests. Read-only advisor02:40 confirmed that directly reusing the matched draft is also necessary to eliminate a second-read race. Implemented; final92focusedtests pass, including focus/source changes and cache-hit/miss custody, with64browser loops green. The UI does not turn every old budget path into a globally unified allowance. Source/project custody and the single failed free allocation remain unchanged; next route selection is separate work.


## 2026-09-27 03:17 UTC — inference availability connected to the actual UI

Delivered a read-only **Recorded availability** action beside Milliner routes in Thinking power. It shows recent matching gateway evidence, receipt coverage, latest outcome, reported retry time, elapsed-but-unverified waits, per-job attempt count and unresolved-ticket cautions. Unknown is not zero/available. Configured readiness now explicitly does not mean quota availability. No probe, credit query, automatic reroute or inference is triggered; this is not a spend-policy implementation.

Actual-browser use exposed that Route used an unsupported modal render callback; corrected to the real body contract with Close, fixed the overly permissive mock and added real edit/blocker/cancel/save loops. Card actions wrap under model details. Final127focusedtests and74B1–B11frontend-fixture loops pass; desktop/phone visual checks and1440/800/390bounds covered. Four logs retain all failures, limitations and the brief final regression-run overlap. No resident Studio was launched.

The next field lesson is accounting: one Supportm7 host dispatch generated three paid gateway format attempts, all failing to deliver a candidate. Aggregate zero cost/token fields contradicted nonzero attempt usage. Separate cost qualification records the ~$0.01283103 catalog estimate and $0.107401465 account balance without claiming invoice-level attribution. Failed-attempt/late-recovery accounting, explicit gateway retry/cost envelopes and clear UI estimate coverage remain follow-up work; none is silently claimed complete here.


## 2026-09-27 03:49 UTC — usage coverage wired to Thinking power and both dashboard levels

Delivered **Usage & cost coverage** in Thinking power, a general-dashboard subtotal/coverage summary, and the full common renderer in each project dashboard. Saved-receipt refresh never starts inference or retrieves a remote ticket. Failed attempts retain tokens; missing, contradictory and cached costs stay unknown. Bound tickets are deduplicated within the explicit100-receipt window, including late recovered answers; legacy host callback counters are separately labelled and not added again.

The actual prior failed DeepSeek job is now recognized as62430input/36000outputtokens,not0usage/$0spend. No current catalog prices or shared-account deltas are silently applied as billing truth. The prior separately derived estimate remains in its original qualification receipt. Expanded184tests/1platformskip,final affected81tests/1skip and82B1–B12UIloops pass; clean isolated8-loop rerun and desktop/phone visual inspection complete. Four logs retain failures and external-trainer attribution. No new model calls or Hat implementation. This closes a bounded visibility/reconciliation gap, not hard spend enforcement, all-time billing or unattended-release readiness.

Advisor03:40 caught pre-ticket copies counted separately from the same request's recovered ticket, and aggregate-only estimates incorrectly sharing the reconciled label. Five red regressions preceded exact-ID alias grouping and separate UI evidence labels; distinct unknown IDs never merge by prompt similarity, and conflicting tickets remain explicit. No billing-completeness claim.

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

## 2026-09-27 04:51 UTC — Implemented B14 workspace handoff UI

- Studio's folder switch now reflects backend custody: it refuses active work, requires destination-home ownership, waits for source threads, retains source intentions and opens a different home paused. API epochs keep stale pages from editing the newly selected project. Event streams are home-bound.
- The picker shows blockers and waiting jobs, includes readiness refresh/reload, prevents duplicate/uncertain retries, labels its path field and freezes the parent approved for a new folder. Phone overflow discovered by screenshot inspection was fixed and added to geometry assertions. Same-root selection retains a custom home; no claim of concurrent project workers.
- **Validation:** final serial integration suite: 205 passed, 1 skipped in 153.67s. The skip is the pre-existing dashboard symlink case because symlink creation is unavailable on this host. This is not the full repository suite. All 101 B1–B14 actual-frontend/simulated-API loops passed (208 fixture requests, no browser errors); artifacts: training/.tmp/studio-use-loops-2026-09-27T04-50-21-605Z/. Final desktop and phone picker screenshots inspected; 1440/800/390 widths checked. JS syntax and diff whitespace checks passed. Earlier overlapping 45/79/197-pass development runs are not additive.
- Advisor consulted read-only at 04:41 UTC; constructor/partial-start ownership, late navigation and timeout findings were incorporated. External trainer engineering, no new project-instrument calls or autonomous Subject-improvement claim. All three field homes unchanged in switch-audit-20260927T044856Z.json.
- Trainer test-isolation incident was preserved and corrected, not hidden: a pre-fix empty path created a fresh repository-root home, now moved intact into trainer-receipts. See the master 04:51 entry and test-fixture-escape-20260927T043238Z.json.
- **Remaining release work / next bounded step:** this is one active Studio home, not concurrent multi-project execution. Per-home ownership does not exclude equal/nested source roots through different homes. Recent-folder records still omit custom-home bindings: the tested same-root no-op preserves an isolated home, but switching away and revisiting via recents is not yet a safe isolated-home launch mechanism. Next address explicit root/home registration, revisit fidelity and overlapping-root admission before broader concurrency. Keep PRHat on its explicit isolated-home path; do not launch it via recents. No global exactly-once external-effect, power-loss or unattended-production guarantee.

## 2026-09-27 05:18 UTC — B15 folder/home identity and overlap guard implemented

- Actual picker now accepts a separate home, resolves saved bindings read-only, and confirms the exact pair before opening. Recents preserve home details; missing or corrupt registered state is not converted into a fresh default home. Cancel and delayed-response paths do not submit work.
- Shared-ancestor/exclusive-scope OS leases cover both source root and isolated home for Studio and the shared synchronous build entry point. Equal/nested ownership refuses; siblings can coexist. Persistent binding records outlive optional recents. No home migration or parallel scheduler is implied.
- Final serial integration run: 231 passed, 2 skipped in 185.21s across ownership, switching, Studio, worker lifecycle/restart, shared build jobs, modes/measurements and dashboards. One additional distinct authenticated HTTP selection test passed in 1.99s: 232 distinct passing checks in total, not the full repository suite. Both skips require unavailable host symlink creation. Earlier overlapping 39/88-pass runs are not additive. All 109 B1–B15 actual-frontend/in-memory-API loops passed, 227 fixture requests, no browser errors; final artifacts: training/.tmp/studio-use-loops-2026-09-27T05-16-27-692Z/. Desktop/phone picker and pair-confirmation screenshots inspected; 1440/800/390 widths checked. JS syntax and diff whitespace checks passed.
- Zero new Milliner/project-instrument requests; job IDs none; new provider spend $0, estimate coverage N/A. External trainer authored reusable Runesmith runtime/UI/tests, not Hat implementations. No new author candidate, owner acceptance or scientific Subject-improvement confirmation. OpenRouter credit was not refreshed: $0.107401465 at 03:12:05 remains stale. No advisor consultation this slice; last 04:41 UTC, next eligible 05:41 UTC. All three field homes remain unchanged in training/trainer-receipts/binding-audit-20260927T051434Z.json; no live PRHat scan. Four logs retain the red cases and corrected browser-test ambiguity.
- This protects cooperating Studio and synchronous-build writers using the same OS user profile; it does not constrain other apps, legacy direct Workspace/Worker/kernel entry points, other users, hard-link/mount aliases or an external process replacing paths/control files. A single Studio still runs one home. Moving/deleting a profile, home migration, adjustable parallel scheduling, production adapters and unattended commissioning need separate qualification. Dashboard view registration is still read-only and is not execution registration. The three legacy field homes were not registered or relaunched by this step; PRHat still requires its explicit isolated-home path on any future authorized commissioning. Next rotate to measurements/operations readiness and evidence ingestion, or an eligible configured-instrument author step when fresh capacity and remaining allowance justify it; do not create extra retries to keep instruments busy.

## 2026-09-27 05:55 UTC — B16 measurement-age and source readiness implemented

- Added an optional maximum data-age field with timestamp requirement; age derives from the newest included row, not the time a report was read. Blank explicitly means historical evidence with no currency claim. One recent row is not proof that the full aggregate is recent or complete.
- Studio and dashboards expose saved-report readiness, superseded pasted inputs and historical thresholds/units. A replacement paste notifies pages without revealing its payload. Refresh reads saved evidence only, preserves unsaved input even across delayed responses, and is labeled as a last-refresh snapshot.
- Optimize refuses unusable selected evidence and retains a valid returned answer as held if evidence changes. Mere readiness annotations do not reset memo identity; an actual pre-B16 started/unresolved receipt is tested with zero calls. Operations remains local report intake.
- 176 distinct backend checks passed overall, one host symlink skip; 121 full frontend loops and final 12-loop B16 rerun passed. Evidence/failures/05:42 advisor review: TRAINER_LOG.md and training/trainer-receipts/measurement-validation-20260927.json.
- External trainer-authored engineering; no new project instruments, spend or Hat acceptance. Four field logs updated; all source/protected receipts unchanged. Live connectors, watchers, automatic hypothesis implementation and unattended production commissioning remain open, not implied by these controls.

## 2026-09-27 06:27 UTC — B17 author budgets visible and consistent

- Work → Drafts now shows ordinary attempts used/remaining, unknown-history blockers, saved-candidate reuse and spent alternate continuation. Read-only refresh and goal review are adjacent to the existing confirmed draft-only action. Disabled authoring explains why; no reset control or new automatic loop.
- Feedback, focused context and model changes do not refill the ordinary allowance. Source/contract-proven legacy scopes are aggregated without rewriting receipts. Normal Build cannot bypass the focused revision lineage rule. A changed source/contract is still distinct work, not a global spend limit.
- 247-pass integration (215.72s), then the final 29-pass allowance suite (19.17s), including two new unreadable-directory cases: 249 distinct backend passes, not 276. The 27 overlapping tests are not additive; the final directory guard was added after the broader integration. No skips. All 129 B1–B17 actual-frontend/in-memory-API loops passed (259 requests, zero browser errors), including eight B17 loops at 1440/820/390 widths. Not the full repository suite or field acceptance. Desktop/phone screenshots inspected; engineering receipts and failures are in TRAINER_LOG.md and training/trainer-receipts/author-allowance-validation-20260927.json.
- No new project call/spend or Hat change. Support m7 has one genuine ordinary attempt remaining; Growth m5 legacy lineage remains unknown and blocked. This is runtime/Studio reliability, not new autonomous authorship, acceptance, scientific improvement or an unattended-release claim.

## 2026-09-27 07:05 UTC — B18 support reports connected to Troubleshoot and Studio

- Modes & measurements now includes a Support reports inbox: paste a minimized excerpt, source label, exact mapped component and optional reported time; inspect provenance, then deliberately allow or exclude future repair context. Saving is local with sharing off; neither save nor selection starts a job. Packet omissions and changed/unavailable targets are visible.
- Matching existing failing-test repair steps receive bounded, labelled untrusted evidence. Actual captured component identity, selection revision and already-served opportunity identity are preserved. Reports do not become tests, instructions, verified incidents or production authority.
- Local repair sessions/checked proposals remain inspectable, while report-assisted tasks are excluded from episodic learning, Kaizen author examples/replays and online trial scoring. Work and Improve carry those qualifications. Home exports include retained records; there is no automatic secret removal.
- Final targeted integration 162 passed; all 139 B1–B18 frontend-fixture loops passed, plus a non-additive final ten-loop B18 layout rerun. Desktop and phone screens inspected. Master TRAINER_LOG.md and support-report-validation-20260927.json retain hashes, failures, scope and advisor findings.
- No field Hat code, model call/spend, report selection or acceptance changed. Manual paste is implemented; email/file watching, standalone incident diagnosis, non-Python repair adapters and retention archive/delete controls remain open. This is not unattended production commissioning.

## 2026-09-27 07:33 UTC — B19 first-use truth and session handoff

- Overview now carries the saved scheduling, Kaizen, executable-build-check and delegated-application policy with prerequisites; recovery/manual relay/current/paused states lead to the relevant review surface. The general next action navigates to Modes & measurements instead of purchasing a generic repair round.
- Offline local setup checks expose missing dependencies and unknown/malformed results. Nothing is installed, called, queued or enabled by a refresh. The complete setup checklist is not presented as proof of success. Desktop/tablet/phone layouts and navigation are tested.
- New RUNESMITH_STUDIO_AND_RUNTIME_HANDOFF_2026-09-27.md records the broader changes, scoped evidence, model-authored versus trainer-authored work, current field state, release gaps and self-assessment. Isolated B18 wheel installation succeeded but requires optional pytest for code work; no clean-machine click-to-start or unattended build qualification yet.
- Final B19 evidence: 41 targeted backend passes, all 149 B1-B19 frontend-fixture loops green; no inference/field-source changes. Failures/receipts/hashes are in the master log and overview-readiness-validation-20260927.json. Next aim is a complete installed-user journey with measured interventions, not a release-ready claim.
