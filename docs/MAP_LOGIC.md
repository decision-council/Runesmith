# MAP_LOGIC: what every part of the Living map means, where its facts come from, and how to automate it

Spec for the Living map (Environment, Self, Development, Operations), written 2026-10-05 by the operator for the MAP work
(brief: MAP_living_graph.md). The implementer copies it to `docs/MAP_LOGIC.md` in the branch and keeps it true to the code.

## 0. Principles (apply to every tab)

1. **Facts only.** Every node, edge, color, number and badge comes from files on disk, Runesmith's ledger and state, or a
   recorded test run. No model writes anything shown on the map. Missing evidence is shown as **unknown**, never guessed.
2. **Every fact names its source and time** in the detail panel: "read from disk at 13:02Z", "latest test run 12:58Z (repair
   round)", "ledger, 2026-10-05T04:28:44Z". A color always has its reason one click away.
3. **Every part is clickable, and every click opens three sections:** *What this is* (one plain sentence), *Evidence* (the facts
   with sources), *Automate* (the owner controls that govern this part). Where nothing can be automated, *Automate* says why in
   plain words and names what governs the part instead.
4. **Automate uses what exists.** Each control is an existing owner setting or action, sent through its existing endpoint, with
   its existing confirmation, default and ledger record. The map adds reach, never authority. A control shows its current
   value and what changes if it is switched ("Scheduled rounds: off. Turning on runs a round every 1 min while the Studio is
   open; each round can spend model calls.").
5. **Stable and bounded.** Deterministic ordering (by folder, then name; by plan order), so a refresh never rearranges the
   drawing. At most ~60 nodes drawn; beyond that, group by folder or track with "+N more", expandable. Keyboard and screen
   reader: every node reachable by Tab, Enter opens its panel; a list view carries the same facts. Phone width: one column.
6. **Fallback.** If a builder fails, the tab shows the current view and a plain line saying what could not be read.

## 1. Environment: the project as it is on disk

**Hub:** the workspace folder. Evidence: files, languages, version control, last map time. Automate: scheduled rounds
(`auto_work`, `interval_minutes`), run the project's tests while mapping (`probe_tests`), never-touch folders (`exclude`),
how many objects to map (`max_objects`), read notes (`read_notes`), and the "Re-map & measure" action.

**Objects (ring 1):** the mapper's objects, as today. When the workspace holds one object (the common single-project case), that
object is expanded at once into its **structure** (below); with several objects, clicking one expands it.

**Structure nodes** (new builder, deterministic, from disk only, no model calls):
- Kinds: *module* (source file), *test* (test file), *doc*, *config*, *data*; grouped by folder (a group node per folder when a
  folder has more than one file). Size grows with lines (log scale, clamped).
- **Edges, each with how it was found:**
  - `imports`: module to module. Python by `ast` (import and from-import resolved to files in the project); JS/TS/MJS by
    import/require regex resolved to project files; other languages: none.
  - `tests`: test file to module, when the test file imports the module, or its name is `test_<module>` / `<module>.test`.
- **State of a module** (the existing bands), from the **latest recorded test run that covers it**, whatever ran it (a map
  probe, a repair round's signal run, a build's checks), and only if that run is not older than the module's last change on
  disk:
  - **Bad**: a test that reaches it failed in that run.
  - **Optimal**: at least one test reaches it and all of them passed.
  - **Minimal**: no test reaches it.
  - **Unknown**: no recorded run, or the run is older than the file's last change ("changed since the last test run").
  - World-class is not assigned by the map (no evidence rule earns it here).
- **State of a test file:** its last result (passed / failed n of m / not run) with time and source.
- **Badges** (from existing state, no new writes): a fix waiting for you that touches the file (Work & proposals); last changed
  by Runesmith (ledger: applied draft or fix, time, author model); in an open milestone (plan); failing tests count.
- **Detail panel:** path, kind, lines, imports, imported by, tests that reach it and their last results, last change and by whom
  (ledger where known, else file time), open work, and the state's reason.
- **Automate (module):** "Watch its tests" (turns on `probe_tests` and runs Re-map & measure, with the existing warning that the
  project's code runs on a throwaway copy); "Fix the failing tests" (the existing Overview action; it is whole-project, and the
  button says so); "Make a milestone for this file" (opens the milestone form prefilled; nothing is saved until the owner saves);
  "Keep Runesmith out of this folder" (`exclude`, with its confirmation).
- **Automate (test file):** "Watch its tests" as above; open its results in Activity.
- **Automate (doc/config/data):** "Documents a model may read" (existing brief control) for docs; otherwise none, with why.

## 2. Self: Runesmith's own anatomy

- **Kernel ring** (fixed modules, count): What: "the fixed part that owns identity, budgets, the ledger and promotion".
  Evidence: module names, digest of the running build, version. **Automate: none, by design**: "The kernel is not
  self-modifiable; it changes only with a Runesmith release, so no improvement loop can rewrite its own judge." (Governed by:
  updates.)
- **Organs** (self-modifiable modules, e.g. `repair`): active generation, its metrics. Automate: self-improvement on/off
  (`kaizen`), its share (`self_improvement_share`), how often (`kaizen_every`), how much experience first (`min_experience`),
  and "Adopt: start a trial" for a library generation.
- **Lineage:** generations in **parent-to-child order** from their manifests (`parent` field), never by name or digest. Each
  station's state, in plain words, from the generation and trial records: **active**; **on trial** (counts per arm, looks done,
  next look); **frozen** (a candidate not adopted); **rejected** (lost its trial); **rolled back**; **imported**. A tick is drawn
  only on the active generation and on a generation that won its trial. Detail: digest, parent, author model, campaign and
  target, created, trial record. Automate: adopt (start a trial), end the trial, roll back, all with their existing
  confirmations and ledger records.
- **Self-knowledge metrics** (repair yield, seconds per repair, calls per repair, false "fixed" rate): each with its sample size
  and window ("41 sessions since 09:01Z") and, during a trial, per arm. Fewer than 10 sessions: shown with "few sessions".

## 3. Development: the plan and the climbs

- **Goals** ("Operating toward"): the owner's goals, as today. Automate: Goals & plan.
- **Plan graph:** milestones as nodes, **prerequisites as edges**; grouped by track; color by status: done (green), ready
  (amber), waiting on a prerequisite (grey, dashed edge), doing (pulse), needs you (red outline: tries used up, checks
  waiting, a draft waiting), dropped (struck through). Cap and "+N more" per track (J11 has 137 items).
- **Milestone detail:** title, "done when", status history, origin (Runesmith's first plan / a breakdown the owner adopted / a
  step split off by the stuck policy / added by the owner, from the ledger), checks (approved by owner or autopilot), drafts
  (count, last author), tries left. Automate: propose acceptance checks; check autopilot (`checks_autopilot`); stuck policy
  (`stuck_policy`); recheck policy (`recheck_policy`); check drafts by running their tests (`build_steps`); apply checked drafts
  automatically (`build_apply` with folder grants `build_paths`), each with its existing confirmation.
- **Tracks / ladders:** the build ladder per object uses the **latest recorded test run, whatever ran it**, with source and time
  on the station ("latest test run 13:11Z, during a repair round"); so "tests collect" is achieved when any recorded run
  collected tests, and "tests pass" shows its true state. The generations track follows the lineage rule of §2.

## 4. Operations: the loop as it runs

- **Work-loop stages** with defined counters (each stage's panel states the definition and window, e.g. "since this home was
  created" or "today"): Map (objects mapped; last map), Discover (objects with work found), Repair (attempts), Judge (accepted),
  Propose (waiting for you), Apply (applied by you / applied automatically).
- **Automate per stage:** Map: `probe_tests`, `max_objects`, Re-map & measure. Discover and Repair: scheduled rounds
  (`auto_work`, `interval_minutes`), `full_speed`, autonomy level (`autonomy`). Judge: check autopilot (`checks_autopilot`).
  Propose and Apply: automatic apply (`build_apply` + `build_paths`) and autonomy level.
- **Who thinks what:** each role and its chain with calls, errors and latency. A route that failed every recent call is marked
  "failing every call" with its count. Automate: Thinking power (role assignment, the free-key chain).
- **Attention:** the self-improvement share and the health line, with its definition. Automate: `self_improvement_share`.
- **Trial:** counts per arm, alpha, looks done and next; Automate: through Self (adopt, end).
- **Schedule:** autonomy, interval, next and last round. Automate: those settings. **Restart hold** (when present): the review
  and Resume controls as in Activity, and the recovery policy (`recovery_policy`).

## 5. Not automatable, by design (said in plain words where clicked)

Kernel modules (fixed; changes only by release), the ledger (append-only), recorded history (read-only), and the judge's hidden
tests where a study uses them. Each says what governs it instead.

## 6. Tests the implementation must carry

Builder unit tests on fixtures: a Python src-layout project with a failing test (Bad and Optimal and Minimal modules; a
module changed after the run is Unknown), a JS project (import edges), an empty folder, a docs-only folder, a 200-file project
(grouping, "+N more", stable order across two builds). Lineage ordering from manifests with a trial in progress. A plan with
prerequisites (graph edges, needs-you state, origin from the ledger). Browser use-loops: each tab renders; clicking a module,
a stage, an organ, a generation and a milestone opens What/Evidence/Automate; every Automate control sends exactly its existing
request after its existing confirmation, and Cancel sends nothing; keyboard path and phone width; light and dark.
