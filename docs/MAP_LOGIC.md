# MAP_LOGIC: what every part of the Living map means, where its facts come from, and how to automate it

Spec for the Living map (Environment, Self, Development, Operations). First written 2026-10-05 by the operator; this copy is kept
true to the code (`runesmith/app/living_map.py` builds the facts, `runesmith/app/static/js/views/map*.js` draws them). Where the
code made a rule impossible or wrong, the rule here is the one the code keeps, and section 8 lists what changed from the first
draft and why.

## 0. Principles (apply to every tab)

1. **Facts only.** Every node, edge, color, number and badge comes from files on disk, Runesmith's ledger and state, or a
   recorded test run. No model writes anything shown on the map. Missing evidence is shown as **unknown**, never guessed.
2. **Every fact names its source and time** in the detail panel: "read from disk at 13:02Z", "latest test run 12:58Z, during a
   repair round", "ledger, 2026-10-05T04:28:44Z". A color always has its reason one click away.
3. **Every part is clickable, and every click opens three sections:** *What this is* (one plain sentence), *Evidence* (the facts
   with sources), *Automate* (the owner controls that govern this part). Where nothing can be automated, *Automate* says why in
   plain words and names what governs the part instead.
4. **Automate uses what exists.** Each control is an existing owner setting or action, sent through its existing endpoint, with
   its existing confirmation, default and ledger record. The map adds reach, never authority. A control shows its current
   value and what changes if it is switched ("Scheduled rounds: off. Turning on runs a round every 60 min while the Studio is
   open; each round can spend model calls."). Nothing is sent until the owner presses the control's own button, and Cancel on a
   confirmation sends nothing.
5. **Stable and bounded.** Deterministic ordering (by folder, then name; by plan order), so a refresh never rearranges the
   drawing. At most about 60 nodes drawn; beyond that, folders or tracks show "+N more", expandable. Keyboard and screen
   reader: every node is a Tab stop, Enter opens its panel; a list view carries the same facts. Phone width: one column, the
   list view first. Light and dark.
6. **Fallback.** If a builder fails, its endpoint still returns the older fields, names what could not be read
   (`living_problems`), and the tab shows the current view and a plain line saying what could not be read.

Read-only: the builders read files, the ledger, state and session records. They run no test, ask no model and write nothing. The
map's endpoints change no file (a test checks it).

## 1. Environment: the project as it is on disk

**Hub:** the workspace folder. Evidence: files, languages, version control, last map time. Automate: scheduled rounds
(`auto_work`, `interval_minutes`), run the project's tests while mapping (`probe_tests`), never-touch objects (`exclude`), how many
objects to map (`max_objects`), read notes (`read_notes`), and the "Re-map & measure" action.

**Objects (ring 1):** the mapper's objects, as before. When the workspace holds exactly one object that is not excluded (the
common single-project case), that object is expanded at once into its **structure**; with several objects, "Show its structure"
in an object's panel expands it. If the structure cannot be read, the objects are drawn as before and a line says why.

**Structure nodes** (`GET /api/map/structure?object=NAME&expand=FOLDER|FOLDER`, from disk only):

- Files are those the mapper itself reads: no version-control or tool folders, nothing hidden, never through a link or junction,
  at most 20,000; a container workspace reads only its own loose files (its subfolders are objects of their own).
- Kinds, from the file's name and place: *module* (source code in a language the map knows), *test* (a file named `test_*`,
  `*_test`, `*.test.*`, `*.spec.*`, `conftest`, or any code under a `tests`, `test` or `__tests__` folder), *doc* (Markdown, text,
  reStructuredText), *config* (toml, ini, json, yaml, requirements, package.json, Makefile and the like), *data* (everything else).
- **Groups:** a folder with more than one file of its own. A file in a folder with a single file is drawn with the nearest folder
  above it that has more than one (or at the top of the project). Folders sort by path; at most 12 are drawn as groups, the
  smallest share one "(other folders)" group. A group is a clickable part.
- **Size** grows with lines (log scale, clamped); lines are counted for the first 4,000 files and read from files up to 1.5 MB.
- **Edges, each with how it was found:**
  - `imports` (module to module, or test to test helper): Python by `ast` (import and from-import resolved to project files: by
    dotted name from the top of the project, from `src`, from the folder above a package, relative imports by their package, and
    a neighbour in the same folder); JavaScript and TypeScript by a pattern match on `import`, `export ... from`, `require` and
    `import()` of relative paths (the edge says "found by pattern, not by a parser"); other languages: none. Imports are read for
    the first 2,500 code files; the rest are counted, never guessed.
  - `tests` (test to module): the test file imports the module, or is named for it (`test_foo.py` and `foo_test.py` and
    `foo.test.js` all say `foo`). Both reasons are kept on the edge. *Reach is direct:* a test reaches the modules it imports or is
    named for, not what those import in turn.
- **State of a module** (the existing bands, Bad / Minimal / Optimal / Unknown; World-class is never assigned here):
  - **Minimal**: no test reaches it. This is a fact about the files, so it holds whether or not a run is recorded.
  - Otherwise it follows the **latest recorded test run** (below), and only if neither the module nor any test that reaches it
    changed on disk after that run (a changed file makes it **Unknown**: "Changed since the last test run: FILE changed at
    HH:MMZ, after the latest test run ...").
  - **Bad**: a test file that reaches it is *named as failing* by that run.
  - **Optimal**: at least one test reaches it, and the run was a **whole-suite pytest run that passed** (a green round, or a probe
    with exit code 0).
  - **Unknown**: everything else, with the reason: no run is recorded; the run was a unittest subset (which cannot show that
    every test passed); the run failed but did not record which test files; a fix was applied after the run; the project is a Node
    project (Runesmith does not run npm test).
- **The latest recorded test run, whatever ran it.** Chosen by the same rule as `Workspace.object_statuses` (so the node, the ring
  and the ladder never disagree): the map's probe (`ENVIRONMENT.json`) if it is newer than the round and conclusive, else the
  repair round's own discovery run (`WORK.json`), else a measuring round (`fix-tests/MEASURED.json`); a fix applied after the
  round supersedes it as "tests not run since the fix". What each records:
  - *Probe*: pytest runs the whole suite; the unittest fallback is a subset. It records counts, never which files failed, so a
    failing probe blames no file.
  - *Repair round* (`WORK.json`, pytest, the whole suite; `utc` is when the round **finished**, so a file changed during the round
    still counts as covered by it): green means every test file passed. A failing round names only the failing test files it
    *served* as repair opportunities (a file served in an earlier round is not listed again), so a named file's modules are Bad
    and every other module stays Unknown: "the other test files' results are not recorded".
  - *Measuring round* (unittest, a subset): names its failing tests; those test files' modules are Bad; nothing is Optimal.
  - Not evidence: the repair organ's "signal runs" in session records (they run a candidate's edits on a work copy, not the
    project as it is) and the build's draft checks (they run a draft, not the project).
- **State of a test file:** its last result from that run: *passed* (whole-suite green), *failed* (named, with its failing tests),
  *changed since the last test run*, *not run* (no run recorded), or *no result of its own is recorded* (stated plainly).
- **Badges** (read from existing state; nothing is written): a fix or draft waiting for the owner that touches the file (Work &
  proposals); last changed by Runesmith (ledger and draft/proposal records: applied by you, applied automatically by a checked
  build, or a fix applied; time and author model); in an open milestone (a draft for it touches the file, or its own words name the
  file); failing tests count. If the file changed on disk after Runesmith's change, the panel says so and says who is not
  recorded.
- **Detail panel:** path, kind, lines, imports, imported by, tests that reach it and their last results, last change and by whom
  (ledger where known, else file time), open work, and the state's reason, each with its source and time.
- **Scale:** at most about 60 nodes drawn; over that, each folder keeps its most important parts (a failing one, one with work
  waiting, then the largest) and shows one "+N more" part; "Show all" for a folder draws up to 60 of its files. The list view
  and the panel reach every file (the list carries at most 500; a folder that large is read in part and says so). The layout is
  a function of the structure alone: folders in path order take sectors of a circle, parts fill rings in name order.
- **Empty folder / non-code folder:** an object with no files shows a plain sentence and the objects as before; documents are
  grouped with no edges and the sentence says there is no code to link.

**Automate (module):** "Watch its tests" (turns on `probe_tests` and runs Re-map & measure, after a confirmation that carries the
Settings switch's own warning that the project's code runs on a throwaway copy); "Fix the failing tests" (the Overview action,
offered only when the Overview offers it; it works on the whole project and the button says so); "Make a milestone for this
file" (a small form; nothing is saved until Save); "Keep Runesmith out of an object" (`exclude`, only for objects, with the same
immediate request Settings and the object panel send). **Test file:** "Watch its tests" and a link to Activity. **Doc:** a link
to the brief's blueprints in Goals & plan. **Config and data, and a folder inside a project:** none, and why (the never-touch
list works on whole objects; automatic apply is limited to the folders allowed in Goals & plan).

## 2. Self: Runesmith's own anatomy

- **Kernel ring** (fixed modules, count): the fixed part that owns identity, budgets, the ledger and promotion. Evidence: module
  name, purpose, lines, public parts, and the digest of the running build and the version. **Automate: none, by design**: "The
  kernel is not self-modifiable; it changes only with a Runesmith release, so no improvement loop can rewrite its own judge."
  Governed by: updates.
- **Organs** (self-modifiable modules, e.g. `repair`): the active generation's file and lines. Automate: self-improvement on/off
  (`kaizen`), its share (`self_improvement_share`), how often (`kaizen_every`), how much experience first (`min_experience`),
  and "Adopt: start a trial" for a library generation.
- **Lineage:** generations in **parent-to-child order** from their manifests (`parent`), never by name or digest (roots and
  siblings by frozen time, then id; a generation whose parent is missing is a root). Each station's state, in plain words, from the
  manifest, the trial records and the ledger: **active**; **on trial** (counts per arm, looks done, next look); **won** (its trial
  ended in activation, and it is no longer active); **rejected** (lost its trial); **rolled back** (it was active and you made
  another active); **trial stopped** (you ended its trial); **superseded** (replaced when another won its trial); **frozen** (a
  candidate not adopted); **imported** (frozen from the library, not on trial). A tick is drawn only on the active generation and on
  a generation that won its trial. A candidate on trial is the child of the generation it challenges (a library generation is frozen
  with the active one as its parent), so it follows it; a sibling pair is ordered by frozen time, never by digest. Detail: digest, parent, author model (from the campaign record, else "unknown"), campaign and
  target, created, validation, trial record, when it was made active. Automate: "Make active" (roll back) and, for the
  generation on trial, "Stop this trial", both with their existing confirmations and ledger records.
- **Self-knowledge metrics** (repair yield, seconds per repair, calls per repair, false "fixed" rate): each with its sample size
  and window ("41 judged sessions since 09:01Z") and, during a trial, per arm (sessions marked with the arm since the trial
  opened). Fewer than 10 judged sessions: "few sessions". Each metric opens its definition and evidence; Automate: the share and
  the self-improvement switch.

## 3. Development: the plan and the climbs

- **Goals** ("Operating toward"): the owner's goals, as before. Automate: Goals & plan.
- **Plan graph** (`plan_graph`): milestones as nodes, **prerequisites as edges** (an arrow means "needs this first"; dashed is still
  open); grouped by track, columns by how many prerequisites deep; color by state: **done**, **ready** (open, nothing it needs is
  still open), **waiting** (a prerequisite is open; dashed outline), **in progress** (pulse), **needs you** (red outline: its tries
  are used up and it waits, a draft waits for your review, proposed checks wait for your approval, or proposed smaller steps wait
  for your decision), **dropped** (struck through). At most about 60 drawn, in the order needs you, in progress, ready, waiting,
  done, dropped; each track shows "+N more" and expands (J11 has 137 items). The list view carries every milestone.
- **Milestone detail:** title, done when, status and its history (ledger `milestone.updated`), origin (from the ledger and the
  plan: created by "Fix the failing tests"; a breakdown you adopted; a step split off by your stuck-milestone setting; added by you;
  in the plan drafted by MODEL, version N; else "unknown"), what it needs first, what waits for you, drafts (count, waiting, last
  author and time), acceptance checks (approved by you or by the autopilot, with who proposed them), and its **tries**, read on
  click against the files as they are now (or "unknown", with the reason). Automate: propose acceptance checks; check autopilot
  (`checks_autopilot`); stuck policy (`stuck_policy`); recheck policy (`recheck_policy`); check drafts by running their tests
  (`build_steps`); apply checked drafts automatically (`build_apply` with the folder grant `build_paths`), each with its
  existing confirmation. A done or dropped milestone is recorded history: none, and why.
- **Tracks / ladders:** the build ladder per object uses the **latest recorded test run, whatever ran it** (section 1), with its
  source and time on the station ("latest test run 13:11Z, during a repair round"): "tests collect" is achieved when a whole-suite
  run ran tests, or when a measuring round (Python's own unittest, which is the runner for a project the repair organ cannot serve)
  ran at least one test (the station says it found tests, as a subset, and does not show every file collects; a unittest *probe*
  keeps the older scoped rule: collect stays unknown); "tests pass" is achieved when it passed, not achieved when any test failed (a subset run too), and unknown when
  the run was a subset that passed, could not run, timed out, or a fix was applied after it; "fast suite" is unknown unless the
  latest run is a probe that timed the suite. With no run recorded the map's own ladder stays. The same overlay feeds the
  Environment panel's ladder.
- **Generations track:** the lineage of section 2, in parent-to-child order, each station labelled by its name and its state; a
  tick only where section 2 allows it.

## 4. Operations: the loop as it runs

- **Work-loop stages**, each with its counter, what it counts and since when (the panel says it; `stages_view`):
  **Map** (objects the latest map lists, including excluded ones; as of the latest map); **Discover** (objects whose tests failed in
  the latest round, found by pytest discovery or by the unittest measurement a round makes where the repair organ cannot serve the
  project; the latest round); **Repair** (judged attempts: session records that got the held-out judge's verdict; since the
  first one, else since this home was created); **Judge** (judged attempts the judge accepted; same window); **Propose** (accepted
  fixes you have not applied or rejected, now; drafts waiting are counted apart); **Apply** (fixes you applied, drafts you applied,
  drafts a checked build applied automatically; same window as Repair).
- **Automate per stage:** Map: `probe_tests`, `max_objects`, Re-map & measure. Discover and Repair: scheduled rounds (`auto_work`,
  `interval_minutes`), `full_speed`, autonomy level (`autonomy`). Judge: check autopilot (`checks_autopilot`). Propose and Apply:
  automatic apply (`build_apply`, with its allowed folders in Goals & plan) and autonomy level.
- **Who thinks what:** each role and its chain with calls, errors and latency (call counters, `OPERATIONS.json`, since this home was
  created). A route that failed every call is marked "failing every call (N of N)". Automate: Thinking power (role assignment).
- **Attention:** the self-improvement share and the health line, with its definition. Automate: `self_improvement_share`,
  `kaizen`.
- **Trial:** counts per arm, level per look, looks done and next; Automate: "Stop this trial", or "Adopt" when none is open, and a
  link to Self-improvement.
- **Schedule:** autonomy, interval, next and last round. Automate: those settings and `recovery_policy`. **Restart hold** (when
  present): shown, with a link to Activity, where the review and Resume controls (which need the current revision) keep their own
  confirmations.

## 5. Not automatable, by design (said in plain words where clicked)

Kernel modules (fixed; changes only by release), the ledger (append-only), recorded history (read-only: a done or dropped milestone,
a closed trial), a count of files, and the judge's hidden tests where a study uses them. Each says what governs it instead.

## 6. Tests the implementation carries

`tests/test_living_map.py`: builder unit tests on fixtures: a Python src-layout project (Bad, Optimal, Minimal and Unknown modules;
a module or a test changed after the run is Unknown; a unittest subset and a counts-only probe never blame or bless a file; an
applied fix makes the tests unknown), a JavaScript project (import edges), an empty folder, documents with no edges, a container
workspace, a 200-file project (grouping, "+N more", expansion, the same drawing twice), ladders from the latest run, lineage order
from manifests with a trial in progress (a child whose id sorts before its parent's), a plan with prerequisites (edges, needs-you
state, origins from the ledger, the cap), stage counters, metrics samples, the endpoints (fallback leaves the older fields), read-only,
the fixture shape, and this document's Automate table against the code. `tests/studio_use_loops_browser.mjs` series B28 to B31:
each tab renders; clicking a module, a stage, an organ, a generation and a milestone opens What / Evidence / Automate; every Automate
control sends exactly its existing request after its existing confirmation, and Cancel sends nothing; the keyboard path, phone
width, light and dark.

## 7. The Automate mapping

Each row is a control the map offers (its id in `map-parts.js`), the request it sends, where the same request is already sent, and
whether that place asks first. `{...}` lists the keys of the body. A `policy_chosen: true` travels with `auto_work`, `probe_tests`
and `kaizen`, as Settings and the Overview send it.

| Part | Control id | Request | Existing call site | Confirmation |
| --- | --- | --- | --- | --- |
| Hub, Schedule, Discover, Repair | `auto_work` | `POST /api/settings {auto_work, policy_chosen}` | settings.js (toggle, `save`), home.js (`choose`) | none; the effect is written beside the button |
| Hub, Schedule, Discover, Repair | `interval_minutes` | `POST /api/settings {interval_minutes}` | settings.js (select) | none |
| Schedule, Discover, Repair | `full_speed` | `POST /api/settings {full_speed}` | settings.js (toggle) | none |
| Schedule, Discover, Repair, Propose, Apply | `autonomy` | `POST /api/settings {autonomy}` | settings.js (segmented choice) | none |
| Hub, Map, module | `probe_tests`, `watch_tests` | `POST /api/settings {probe_tests, policy_chosen}` then `POST /api/worker/run {job: 'map', params: {probe: true}}` | settings.js (toggle), map.js (Re-map & measure) | the Settings switch's warning, shown as a confirmation (new, stricter) |
| Hub, Map | `max_objects` | `POST /api/settings {max_objects}` | settings.js (number) | none |
| Hub | `read_notes` | `POST /api/settings {read_notes}` | settings.js (toggle) | none |
| Hub, object, module | `exclude` | `POST /api/settings {exclude}` then `POST /api/worker/run {job: 'map'}` | settings.js (chips), map.js (Exclude button) | none (it narrows what Runesmith may touch) |
| Hub, Map, object, test file, rung | `remap` | `POST /api/worker/run {job: 'map', params: {probe: true}}` | map.js (Re-map & measure) | none |
| module, object, rung | `fix_tests` | `POST /api/fix-tests {allow_apply: false}` then `POST /api/worker/run {job: 'build'}` | home.js (Fix the failing tests) | the Overview's own text; offered only when `GET /api/fix-tests` returns an offer for the object |
| module | `milestone_form` | `POST /api/plan/milestones {title, detail, track, done_when}` | goals.js (add a milestone) | the form's Save button |
| milestone | `propose_checks` | `POST /api/worker/run {job: 'propose_acceptance', params: {milestone}}` | goals.js (Propose acceptance checks) | none |
| milestone, Judge | `checks_autopilot` | `POST /api/settings {build_steps, build_apply, build_paths, checks_autopilot}` | goals.js (Save build settings) | the Goals & plan text, word for word, when turning on |
| milestone | `build_steps` | `POST /api/settings {build_steps, build_apply, build_paths, checks_autopilot}` | goals.js (Save build settings) | none |
| milestone, Propose, Apply | `build_apply` | `POST /api/settings {build_steps, build_apply, build_paths, checks_autopilot}` | goals.js (Save build settings) | the Goals & plan text, word for word, when turning on; refused without allowed folders, as there |
| milestone | `stuck_policy` | `POST /api/settings {stuck_policy}` | settings.js (segmented choice) | none |
| milestone | `recheck_policy` | `POST /api/settings {recheck_policy}` | settings.js (segmented choice) | none |
| Schedule | `recovery_policy` | `POST /api/settings {recovery_policy}` | settings.js (segmented choice) | none |
| organ, metric, Attention | `kaizen` | `POST /api/settings {kaizen, policy_chosen}` | settings.js (toggle), home.js (`choose`) | none |
| organ, metric, Attention | `self_improvement_share` | `POST /api/settings {self_improvement_share}` | settings.js (select) | none |
| organ | `kaizen_every` | `POST /api/settings {kaizen_every}` | settings.js (number) | none |
| organ | `min_experience` | `POST /api/settings {min_experience}` | settings.js (number) | none |
| organ, Trial | `adopt` | `POST /api/improve/adopt/{generation}` | improve.js (Adopt: start a trial) | the Self-improvement text, word for word; disabled while a trial is open or once adopted |
| generation | `activate` | `POST /api/improve/activate/{generation}` | improve.js (Make active) | the Self-improvement text, word for word |
| generation, Trial | `stop_trial` | `POST /api/improve/activate/{incumbent}` | improve.js (Stop this trial) | the Self-improvement text, word for word |
| role, restart hold, reports, documents, settings | `link` | none: opens Thinking power, Activity, Goals & plan, Work & proposals, Self-improvement, Settings or the measurement editor | the pages' own navigation | the page's own |
| kernel module, ledger, closed trial, folder inside a project | (none) | none, and the panel says why | n/a | n/a |

A control with no row above is not offered. A change to a row is a change to the code that sends it, and
`test_the_automate_table_matches_the_code` fails until both agree.

## 8. What changed from the first draft of this spec, and why

1. **Test-run evidence.** The draft named "a repair round's signal run" and "a build's checks". Those run a candidate's edits or a
   draft on a work copy, not the project as it is, so they are not evidence about its files. The repair round's evidence is its own
   discovery run (`WORK.json`), which records only the failing files it served; so a failing round blames the named files and
   leaves every other module Unknown, and only a whole-suite pytest pass makes a module Optimal. A probe records counts, never
   names, so a failing probe blames no file. A unittest subset is never Optimal or "achieved", as the older map already held.
2. **Minimal beats Unknown** for a module nothing reaches: it is a fact about the files, not about a run.
3. **Reach is direct** (the test imports the module or is named for it), as the draft's edge definition says; a longer chain
   would overclaim.
4. **"Exclude" has no confirmation anywhere today** (Settings and the object panel send it at once), so the map matches that; it
   only narrows what Runesmith may touch. **"Watch its tests" asks first**: the Settings switch's warning is shown as a confirmation,
   because it runs the project's code. That is stricter than before, not a new power.
5. **Restart-hold review** needs the current revision and a "reviewed" flag; the map links to Activity instead of repeating it.
6. **"Make a milestone for this file"** is a small form on the panel that posts to the existing milestone endpoint on Save; Goals &
   plan has no entry point that takes a prefilled milestone, and that page is not touched.
7. **Folders inside a project cannot be excluded** (`exclude` names objects); their panel says so and names what governs them.
8. **Tries left** are read on click (`GET /api/map/milestone/ID`), because counting them reads the project once; until then the row says so.
9. **A "won" and a "superseded" state** were added to the lineage vocabulary, for a generation that won its trial and was replaced,
   and one that was replaced by a winner.
10. **World-class** is never assigned: no evidence rule earns it here.
