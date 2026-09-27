# Runesmith — Studio and runtime handoff

**Date:** 27 September 2026. **Owner:** Lars O. Horpestad. **Author:** Astra, external trainer.

This is a product-engineering handoff for the 25–27 September field-training session, not an amendment to the finished scientific paper. Core status below is through B18; field custody was freshly checked at 07:10 UTC. Later work, if any, is recorded separately at the end. All times are UTC.

## 1. Executive judgment

Runesmith is now a substantially stronger **developer alpha for bounded, inspected construction**. It has produced useful model-authored project increments, and its Studio exposes much more of the machinery that previously required a trainer to inspect files or run helpers. It can retain work, explain failures, continue selected work under bounded authority, and distinguish a proposal from something checked and applied.

It is **not yet qualified for the full release promise: place it in an arbitrary folder, supply a brief and keys, and leave it building, optimizing and operating without anyone watching.** The largest remaining gap is an uninterrupted, representative new-user journey on a clean machine—not another collection of isolated passing tests.

| Intended user experience | Judgment at handoff |
| --- | --- |
| Developer installs dependencies, opens a trusted project, reviews controls and runs bounded work | Suitable for a carefully managed alpha; expect rough edges and assistance. |
| Chat-only frontier author, with a person carrying packets/replies | Implemented and locally UI-tested; inherently human-assisted. No fresh external-chat round trip was qualified in this session. |
| First-time nontechnical user double-clicks a self-contained installer | Not ready: Python/dependencies/setup remain prerequisites; no clean-machine installer/browser journey has been certified. |
| API-connected, unattended construction across several projects | Machinery exists for guarded builds, but field work remained externally supervised; not commissioned or soak-tested as this product experience. |
| General production operator, live analytics/email, deployments or sending | Not implemented as a general capability. Current Operations is selected local-report intake. |

These are evidence-based readiness categories, not a percentage-complete estimate.

## 2. The intended product and the boundary we kept

Runesmith is the persistent layer between an operator and a project. Models are replaceable instruments; plans, source snapshots, memories, tests, generations, receipts and operating policy live outside any one model. The desired release supports empty folders, partial projects and productive environments; independent modes; affordable/free/local/paid inference; and automatic work within explicit authority.

This session kept two authorship lanes separate:

- **External trainer:** changed reusable Runesmith machinery/UI, supplied bounded tasks and public contracts, wrote or reviewed owner checks, diagnosed failures and adjudicated promotion.
- **Configured instruments:** authored SupportHat and GrowthHat implementation changes through Runesmith. The trainer did not substitute hand-written Hat implementations when an author failed.

PRHat was the existing-project observation case, not a third writable construction sandbox. Its live root, scheduler, sender, Bellman transport and other agent's work remained protected. The finished paper and website/presentation were not work targets.

## 3. What changed in the machinery

“Implemented and tested” below means the scoped tests/receipts cited here, not universal correctness or independent scientific confirmation.

| Subsystem | Implemented change and why it matters | Remaining qualification |
| --- | --- | --- |
| Construction context | Source-aware author packets, bounded file/symbol selection, omitted-context explanations, frozen exposure identity and source-linked feedback. Complete verification inputs are separate from the smaller model packet. | Broad heterogeneous repositories, long-running source changes and quality gains from context selection remain unmeasured. |
| Draft admission | Full-content or exact-edit formats, candidate-relative edits, missing/ambiguous text refusal, preserved omitted candidate files and no silent fuzzy patching. | Adversarial and large mixed-language projects; not a general untrusted-code sandbox. |
| Plan progression | Model-authored milestone decomposition, dependencies and explicit adoption; completed work/public criteria are preserved. Checked builds can advance milestones. | End-to-end unattended plan completion and long-horizon replanning. |
| Verification and application | Project checks and separate owner acceptance; frozen source/criteria/fixture identity; bounded, separately receipted check continuations; root-bound revocable apply grants; stale-source refusal and write recovery. | A passed author test is not owner acceptance. Manual writes can remain unverified. Durable external-side-effect recovery is not established. |
| Feedback and build memory | Compact receipt-linked observations, bounded retrieval, newest relevant feedback and explicit omissions. Actual sent packets retain exposure provenance. | Recorded inclusion does not establish that the model used it or improved because of it. No general memory-learning benefit estimate. |
| Author recovery | Durable request/attempt journals, retained responses, ticket-based GET retrieval and idempotent readmission. Uncertain calls stop rather than silently repeat. | A lost ticket may still require reconciliation. Host-side “one call” is not proof a gateway made one upstream attempt. |
| Budgets and lineage | Ordinary Build/revision share source-and-contract-bound allowances; notes/model changes do not replenish them. Corrupt or unproven legacy history is unknown, not unused. | No complete account-wide spending ceiling or automatic legacy adjudication. |
| Execution lifecycle | Shared Worker/Studio/synchronous build path; durable waiting intentions; current-job markers; explicit restart review; pause, resume and stop-at-step-boundary behavior. | No global exactly-once guarantee or power-loss durability claim. Stopping is not cancellation of an already-sent provider request. |
| Workspace ownership | Exact root/home registration, safe handoff, stale-page isolation and cooperative OS leases excluding equal/nested writable scopes. Real Windows process-boundary tests passed. | One active home per Studio. Other apps/users, legacy direct entry points and all alias/mount cases are not excluded. POSIX behavior unqualified here. |
| Modes and intent | Map & Plan, Build, Troubleshoot, Optimize, Operations and custom policies; independent enablement, fair serial scheduling, instruction provenance and separately controlled inferred purpose. | All switches may be on, but execution is serial. Custom labels only choose supported executors; they are not arbitrary new production tools. |
| Measurement evidence | Pasted/local CSV/JSON aggregates with mappings, filters, population/window/unit/threshold and immutable receipts; optional data-age rules and stale/superseded-input refusal. | No live GA4/email adapter or watcher. One recent row does not make a whole population fresh. Threshold crossing is not causality or acceptance. |
| Optimization | Evidence-bound, retained hypotheses; changed evidence holds an answer; unchanged evidence cannot repeatedly purchase the same proposal. | No automatic implementation or validated performance gain from this path. |
| Support-report intake | Explicitly selected, minimized excerpts, exact component binding, bounded packets and reversible future sharing; malformed stores fail closed. | Paste only; reports supplement existing failing-test repairs in supported Python src layouts. No report-only diagnosis trigger or archive/delete UI. |
| Restricted learning | Report-assisted repairs remain local review records but are excluded from episodic memory, Kaizen replay/example sets and online trial assignment/scoring. | Local exports still contain retained records; this is not a general information-flow or prompt-injection guarantee. |

Primary implementation entry points: [workspace](runesmith/app/workspace.py), [worker](runesmith/app/worker.py), [build jobs](runesmith/app/build_jobs.py), [building](runesmith/app/building.py), [planner](runesmith/app/planner.py), [modes](runesmith/app/work_modes.py), [ownership](runesmith/app/workspace_ownership.py), [request journals](runesmith/milliner_jobs.py), [support reports](runesmith/app/support_reports.py), [learning loop](runesmith/loop.py).

## 4. What changed in Studio

These are real frontend/API integrations, not separate mockup screens. Most visual qualification used actual frontend/CSS with intercepted, simulated APIs; actual backend/HTTP tests were separate.

| User-facing area | What the user can now inspect or control |
| --- | --- |
| Goals & plan | Brief/blueprints, inferred-purpose distinction, author context, milestone breakdowns, public criteria and typed response-interface declarations; retained/held plans. |
| Work & proposals | Draft versus project checks versus owner acceptance versus applied state; named failure feedback, test progress/timings, memory/exposure references, source-bound review, retained answers, revision controls and used/remaining/unknown allowances. |
| Modes & measurements | Independent built-in/custom switches, instructions, evidence selections, purpose-inference switch, saved report definitions/readiness and the new support-report inbox. Saving a mode is not a grant or schedule change. |
| Thinking power | Provider/model route editing, author-versus-worker guidance, manual chat setup/format correction, role assignment, recorded availability and cost/coverage detail. Model presence is not live capacity or author qualification. |
| Dashboards | General/project receipt views, explicit project/home association and selectable panels. Removing a dashboard view does not remove project files or stop/start its worker. |
| Activity | Current and waiting work, pause/resume/stop distinctions, persistent restart recovery and explicit keep/set-aside review. |
| Folder picker | Visible source/home pair, isolated-home fidelity, active-work blockers, paused destination, stale-page refusal and guarded duplicate submissions. |
| Self-improvement | Existing generation/trial evidence remains visible; eligible learning experience is distinguished from support-assisted local review work. No silent enabling of Kaizen. |

Responsive checks covered desktop, tablet and phone widths. Actual loops found and fixed missing parentheses, modal cancellation semantics, stale feedback delivery, lost typed replies, delayed-refresh races and horizontal overflow. That is useful exercised behavior, but does not mean every screen, button, assistive technology or real provider combination is covered.

## 5. What the field projects actually achieved

Fresh read-only custody at **07:10:10–11 UTC** found all three locks available, no resident Studio, current job, waiting intention, recovery hold, pending author or waiting chat request. `auto_work=false` and `kaizen=false` remain in these training homes. This is external scheduled training, not evidence that a resident unattended Studio did the work.

| Project | Current accepted state | Next/open state |
| --- | --- | --- |
| SupportHat | m1–m6 plus the m2 compatibility milestone are done: persisted case queue, triage/history, document ingestion/index, grounded search, stored cited response drafts, metrics/tracking. | m7 JSON I/O and m8 inspectable local UI remain open. m7 has **2 ordinary attempts used / 1 remaining**, no admitted m7 draft. |
| GrowthHat | m1–m4 and their prerequisite slices are done: persistence, source CLI, audience/offer/hypothesis links, tests/outcomes/confidence including negative findings. | m5 recommendation export remains unaccepted; m6–m8 remain open. Latest m5 fix repairs serialization handling but regresses no-clobber behavior. Legacy revision allowance is **unknown**, not three fresh attempts. |
| PRHat | Isolated home, observation plan and model-proposed goalposts; read-only observation experience. | No PRHat source improvement or production uplift from this session. Last actual production observation is **26 September 03:05 UTC**, now stale. |

Support's latest applied draft is `d202609270035308828`: **61 project tests + 16 cumulative owner checks passed**, followed by a separate guarded apply. It combines retained Opus 4.5 implementation/tests with a Gemini Flash Lite-authored correction. Gemini omitted an explicitly requested extra regression; record that shortfall even though the unchanged acceptance bundle caught the missing-field defect and passed after correction.

Growth's parked draft is `d2026092701292460f1`. A model-authored regression detects the serialization defect, and the later implementation fixes that case, but a competing-destination probe now overwrites bytes it should preserve. It is `needs_revision`, not verified or applied. Do not present it as an overall successful repair.

Free authors did contribute accepted bounded work: recorded Gemini continuation and NVIDIA-hosted Kimi slices, as well as useful model-authored regression tests. Other attempts failed or regressed behavior. This supports “free inference can author useful bounded increments with this machinery and assistance,” not “free equals frontier” or “any free author can run the product unattended.” Use receipt-confirmed model names, not conversational nicknames.

Cline Pixel Canary timed out without a candidate; a Cline Gemini route returned a product-surface restriction. LongCat direct API and the genuine OpenCode CLI trial both ended in terminal 403 outcomes. Those are transport/access results, not author-quality verdicts or successful author routes. No fresh provider catalogue review was performed for this handoff.

## 6. Evidence inventory: what was tested, and what was not

### Final B18 evidence

- **162 passing backend tests**, no failures/skips, 241.46 seconds: support intake, restricted learning, modes/measurements, Studio, loop, proposals, trials and worker lifecycle/restart. This is a targeted integration suite, not the whole repository.
- **139 passing B1–B18 frontend interaction loops**, 272 simulated API requests, no browser errors. A final ten-loop B18 rerun added phone-field bounds and steady-state screenshots; those ten are overlapping, not additional independent cases.
- Real offline model-packet construction and disposable authenticated HTTP tests complement the intercepted-browser fixtures. No live external inference or field service was needed for those checks.
- Desktop/phone screenshots inspected; 1440/820/390 widths checked. JavaScript syntax and tracked diff whitespace checks passed.

The numbered browser series cover: B1 modes/measurements; B2 chat relay; B3 intent/planning; B4 verification recovery; B5 worker controls; B6 dashboards; B7 response interfaces; B8 review visibility; B9 revisions; B10 draft-only acquisition; B11 routes/availability; B12 accounting; B13 restart recovery; B14 home handoff; B15 bindings/overlap; B16 measurement readiness; B17 allowances; B18 support intake.

Earlier suites overlap heavily and must not be added into a headline “total passed.” The earlier whole-repository run recorded **274 passes and one CRLF-format failure** in trainer/support files. Subsequent targeted green suites do **not** certify that this whole-suite failure is gone or that the present much-expanded tree passes every test. Host symlink creation was unavailable in some ownership/dashboard tests; mocks are not equivalent to native cross-platform coverage.

### New distribution diagnostic for this handoff

Built a wheel from a disposable copy of the B18 package source, before the B19 Overview changes below, with no network/build dependency fetch. Installed it into a fresh isolated Windows virtual environment, using isolated-mode imports rather than the developer checkout. The CLI help, home initialization, ledger, active generation and kernel checks worked. Six representative new runtime/Studio assets were present, including support reports, dashboards, modes and ownership.

**The base wheel did not install pytest.** `doctor --offline` reported it missing as expected; code-object work requires the optional code dependencies. This was an installation/initialization diagnostic, not a launched browser session or an end-to-end authored build. The diagnostic wheel is local evidence, not a public release artifact.

### Evidence locations

- [Master trainer log](TRAINER_LOG.md), [Support log](training/SupportHat/TRAINER_LOG.md), [Growth log](training/GrowthHat/TRAINER_LOG.md), [PRHat log](training/PRHat/TRAINER_LOG.md).
- [B18 validation and code hashes](training/trainer-receipts/support-report-validation-20260927.json); [B18 custody](training/trainer-receipts/support-report-audit-20260927T065532Z.json).
- [B17 allowance validation](training/trainer-receipts/author-allowance-validation-20260927.json); [B16 measurement validation](training/trainer-receipts/measurement-validation-20260927.json).
- [Handoff custody](training/trainer-receipts/handoff-audit-20260927T071010Z.json); [isolated distribution diagnostic](training/trainer-receipts/handoff-distribution-diagnostic-20260927.json).
- Full B1–B18 browser receipt: `training/.tmp/studio-use-loops-2026-09-27T06-59-40-838Z/receipt.json`. Final B18 screenshots: `training/.tmp/studio-use-loops-2026-09-27T07-02-50-430Z/`.
- Current requested release scope: [Build additions from Lars](BUILD_ADDITIONS_FROM_LARS_2026-09-26.md). Derived engineering backlog: [Filling the blanks in building Runesmith](FILLING_THE_BLANKS_IN_BUILDING_RUNESMITH_2026-09-27.md). Earlier status paragraphs there are historical; later dated entries supersede them.

## 7. Out-of-box readiness: the actual path

The [Windows launcher](Runesmith.cmd), [macOS launcher](Runesmith.command) and [Linux launcher](runesmith.sh) exist. They find/check Python 3.11+ and launch the local browser app; they do not bundle Python or install project dependencies. A no-argument double-click opens the last project, or a first-project directory under the user's home—not necessarily the directory containing the launcher. Passing/dropping a project folder is the explicit targeting path.

For a technical alpha installation from the repository, `python -m pip install ".[code]"` supplies the optional pytest dependency. Users also need a suitable browser, writable local space, project-specific dependencies and configured model routes. The first-start presentation and local HTTP/token controls exist. Their combined clean-machine journey still needs testing across OSes and profiles, including spaces/non-ASCII paths, missing dependencies, offline startup and browser-launch failures.

New Studio homes start with no instruments. Code inspection shows default scheduling and Kaizen enabled, propose autonomy, and executable Build/apply disabled; scheduling is held until onboarding. Training-home settings are different and must not be generalized to new users. Before release, make the first-run spending/scheduling/role/permission choices explicit and test the transition after a model is added. A mode switch, configured key or elapsed cooldown is not proof that useful work can run.

For the fully automatic release, an API/local route is needed for every role that may run. Manual chat remains valuable but cannot be unattended transport. Production authority must be scoped separately; asking a system to infer a folder's purpose is not an operating grant.

## 8. Suggested next release gates — recommendations, not new authority

1. **Close one reference journey before expanding features.** From a clean home and installed artifact, a new user supplies a small real specification, configures models, sees a plan, authors/checks/applies a useful increment, restarts and continues. Record every trainer rescue; the unattended pass requires zero hidden interventions. Repeat with a free-only route and paid/local alternatives where available.
2. **Surface setup truth at the front door.** Missing pytest, absent roles, manual transport, scheduling, recovery holds and missing delegated authority should be visible before “ready” language. Buttons should lead to the correct guarded workflow, not a generic repair round for every project.
3. **Complete a fresh release-wide regression.** Preserve existing failures and protected receipts. Resolve the CRLF-test/release-packaging issue deliberately; qualify real Windows links and POSIX ownership separately. Exercise upgrade/restart/rollback of an installed version, not just source-tree fixtures.
4. **Qualify bounded unattended runs.** Test provider exhaustion, lost responses, client/process termination, disk pressure, stale source, changing instructions, stop/restart and no-useful-work states. Demonstrate no duplicate paid calls or false completion. Long-run end-to-end evidence is separate from the present unit/integration evidence.
5. **Finish the two construction projects under existing custody.** Support's last m7 attempt deserves a fresh route/capacity review and a well-formed packet. Growth needs proof of its lineage or separately explicit bounded continuation, with the full previously passing behavioral envelope retained—not only the newest failing test.
6. **Add real operations incrementally.** Choose one narrowly authorized connector/runbook, including filtering, credential scope, idempotency/reconciliation, measurement freshness and a stop path. Do not describe local imports as live integrations. Separate Optimize's hypothesis from its implementation/evaluation.
7. **Add concurrency only after conflict qualification.** Current serial execution is honest. Adjustable speed/parallelism needs read/write/resource footprints, independent-job progress tests and shared-service conflict handling, not just a slider. Dashboard project registration is not a multi-project executor.
8. **Prepare a distributable release.** Reconcile the dirty/untracked tree, curate source and assets, run secret/privacy scanning, create a versioned artifact with a manifest, and test that exact artifact. Do not publish the whole training directory, homes, keys, raw support material or diagnostic archives.

These recommendations do not authorize new external sends, deployments, purchases, provider workarounds or PRHat changes.

## 9. Important limitations and review findings

- Python audit-hook confinement is not an OS security boundary. Running arbitrary project tests or code from strangers needs a stronger isolation design. Passing tests is not proof a project is safe to execute.
- Saved keys are in local `secrets.json`, not an encrypted OS key vault. On Windows the current implementation relies on inherited permissions. Existing README wording about keys/configuration should be reconciled before release; it was deliberately not edited during training.
- Home snapshot exports exclude named secret files but can still contain source, notes, prompts and support excerpts. Treat them as sensitive. No blanket redaction guarantee exists.
- One shared modal Cancel defect, swallowed latest feedback and several trainer test-fixture/setup errors were found and corrected. One test accidentally initialized a new repository-root home; it was preserved/moved to a receipt location, and the fixture was isolated. No affected field home was silently reset. These incidents argue for more end-to-end and isolation testing, not for hiding the failures.
- Requirements/acceptance needed trainer clarification in real builds. Some checks were written after reviewing drafts. That is legitimate supervised product work, not a sealed causal experiment or an untouched benchmark.
- The runtime's existing Kaizen/generation/trial mechanisms predate much of this work. Field Kaizen remained off. **This session did not demonstrate a new unaided, model-authored improvement to Runesmith itself.** Trainer-written runtime fixes and model-authored Hat progress must not be relabelled as that result.

## 10. Custody, cost and continuation facts

At 07:10 UTC, Support source digest was `4a93c8e6050949db9f7c645d652fccff88653a6f1e32a1a9a7558c4eda01a523`; 53 protected records unchanged. Growth source digest was `4cf544972e5cf976e6276ef40d83df7fee6c09829a8493165dfd7d6fde93cdb5`; 106 protected records unchanged. PRHat's live root was not scanned for this handoff.

The **retained current accounting window**, not the entire session bill, contains Support's $0.32907398 estimate subtotal with 4/6 requests costed, and Growth's $0.78811 subtotal with 12/13 costed. Failed Support job `mj_3514978f176848a89e60` consumed recorded tokens across three gateway attempts but has a contradictory aggregate zero estimate; its cost is unknown, not free. Historical/project/trainer costs cannot honestly be reduced to one exact session total from these records.

Last observed OpenRouter balance was approximately **$0.107401465 at 06:35:04 UTC**. That is dated account-wide credit, not a current purchasing guarantee. Gemini routes had daily-exhaustion/cooldown evidence at that observation. Recheck before a new author call; an elapsed reset is not enough. No new inference was used for this handoff/installation diagnostic.

Repository base HEAD at inspection: `ae302d8fd1a3fee5b23636822dbe0d939f95a7ed`. The working tree contained 23 modified tracked paths and 89 untracked entries before this handoff/additional work. Counts are not ownership attribution or a release manifest. Many new modules are untracked; **HEAD alone is not the improved product**. Do not hard-reset, discard or blindly commit the mixed workspace. Do not use a current mutable source tree as evidence of an earlier test snapshot.

The pre-training backup recorded in the log is `D:/Runesmith-backup-20260925-221931.tar.gz`, SHA-256 `178fce6af916d1fbdc9b26c4222fdcafb1d20829abf4a72b7227099fbc62a752`; it predates these improvements and is not a backup of the handoff state.

Continuation boundaries: use existing per-home locks/journals and the Studio queue if resident; never replay a consumed commissioning script or uncertain paid request blindly. Keep PRHat at `C:/dev/PRHat` read-only with its isolated home under training. Do not retry the denied resident launch through another route. Preserve the paper, existing product docs and presentation/site. The existing heartbeat remains the continuation mechanism unless the owner changes it; this document does not silently pause or commission anything.

## 11. Trainer self-assessment

I built a more capable and much more inspectable machine, but I did not finish the owner's unattended release goal. My strongest work was converting observed failures into reusable controls, preserving evidence and connecting those controls to Studio. The model-authored applied work is real, and refusing regressive or uncertain work was valuable.

My main shortfall was allocation of attention: too much effort accumulated around individual recovery/accounting mechanisms while the complete new-user path and a sustained no-rescue run remained unfinished. The growing collection of narrowly different recovery paths is itself a maintainability and usability risk. I also introduced defects during implementation and testing; the logs retain them rather than treating only green reruns as history.

The next trainer should optimize for **completed user outcomes with fewer interventions**, not the number of added controls or tests. A smaller, well-qualified automatic path would be more valuable now than another broad layer of features. This assessment is deliberately not a self-awarded numerical score or a claim that the product is release-ready.

## 12. Follow-on work after this snapshot

No later work is implied by sections 1–11. Dated, verified continuation entries belong here so a future reader can distinguish this handoff snapshot from subsequent implementation.

### 27 September, 07:33 UTC — B19: an honest first-use Overview

The handoff's setup finding led to a bounded, trainer-authored Studio improvement:

- Overview now prioritizes restart review, pending manual relay, active work and pause before suggesting new work. The configured-project button opens **Modes & measurements**, rather than submitting a generic repair round. Draft review no longer implies that delegated application is impossible.
- A persistent **Before you leave it working** panel displays the saved scheduling, self-improvement, executable-check and delegated-apply settings, with their prerequisites. It stays visible after the setup checklist completes and links to Settings. It does not change defaults, grant permissions or turn anything on.
- **Local setup checks** use the existing authenticated offline diagnostic. Missing pytest and suggested remedies are visible; unavailable/empty/malformed results say unknown. Refresh performs no installation, provider probe, model call or queued work. Passing local checks explicitly does not establish provider capacity, author quality or unattended readiness.
- The setup checklist now calls configuration untested and recorded work history something other than a success verdict. A not-yet-mapped folder is no longer described as already mapped. All status is qualified as of opening the page; this is not a live health monitor.

**Verification:** 41 targeted backend tests passed, no skips/failures, including real disposable HTTP checks that offline health never probes the configured provider, retains home bytes and leaves the worker unchanged. The held instance-lock byte is excluded from the byte comparison because Windows correctly prohibits reading it. All **149 B1–B19 frontend-fixture loops** passed, 304 intercepted requests and zero browser errors. The ten B19 loops include malformed results, inert diagnostic text, navigation without POSTs and 1440/820/390 layout checks. Desktop/phone screenshots were inspected. These counts overlap earlier work and are not an end-to-end live-provider qualification.

Development failures are retained: the first backend slice was 39 passes/2 failures from the test trying to read that active lock; the first full browser rerun stopped after 145 passing loops because the new helper waited on `disabled` instead of the actual `busy` class. Both test-fixture mistakes were corrected; neither required relaxing product controls. The final passing receipts do not replace the failed ones.

Fresh **07:30:50–54 UTC** field checks found unchanged Support/Growth source digests and all 53/106 protected records intact. All three homes were idle/unowned with no pending/recovery work, scheduling/Kaizen still off. Support retains its one m7 attempt; Growth remains parked with unproven lineage; PRHat live root was not inspected. No new provider inference calls, job IDs or inference spend; no field source, acceptance, grant or route changes. No resident Studio launch or denied-action retry. No further advisor consultation in this slice: the previous review was 06:42:21 UTC.

Evidence: [B19 validation](training/trainer-receipts/overview-readiness-validation-20260927.json), [fresh custody](training/trainer-receipts/overview-readiness-audit-20260927T073050Z.json), browser receipt `training/.tmp/studio-use-loops-2026-09-27T07-31-48-802Z/receipt.json`, backend result `training/.tmp/b19-backend-final.xml`.

**Readiness judgment unchanged.** This closes a first-use visibility gap, not installation, all release regressions, production integrations or the uninterrupted unattended journey. The B18 diagnostic wheel predates this UI change and must not be presented as its packaged release. Suggested next focus: exercise one installed, clean-home construction journey through restart/continuation and measure trainer interventions, while separately preserving the existing field-project custody.
