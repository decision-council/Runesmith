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
5. **Stable and bounded.** Deterministic placement (section 9: every place has a stated meaning, and no list order, font or chance
   changes it), so a refresh never rearranges the drawing. At most about 60 nodes drawn; beyond that, folders or tracks show "+N more", expandable. Keyboard and screen
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
- An object on your never-touch list (`exclude`) is not read: the structure answers with the never-touch sentence from the list as
  it is now, even before the next map is written (it matches the object's name, the name of its folder, or a folder above it).
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
    the first 2,500 code files, **the test files first**, then the source files in path order, so a cap never hides a test. A file
    whose imports were not read (past the cap, a syntax error, over 1.5 MB, not opened) is counted (`imports_not_read`; the
    syntax errors are listed in `parse_errors`), its own panel says "not read" with the reason instead of "no project file", and
    the summary sentence says how many: never guessed. The JavaScript pattern looks at most 3,000 characters from `import` to its
    path (a longer list of names is not found) and takes time in proportion to the file.
  - `tests` (test to module): the test file imports the module, or is named for it (`test_foo.py` and `foo_test.py` and
    `foo.test.js` all say `foo`). Both reasons are kept on the edge. *Reach is direct:* a test reaches the modules it imports or is
    named for, not what those import in turn. When several modules answer to the name (`pkg_a/models.py` and `pkg_b/models.py`),
    the name picks the one in the test's own folder, else the one in the folder the test's folder mirrors (`tests/pkg_a` and
    `src/pkg_a`), else the nearest folder above or below it; when none is nearer than the rest the name gives no edge (an import
    still does). A name that only one module in the project answers to is the answer wherever that module sits.
- **State of a module** (the existing bands, Bad / Minimal / Optimal / Unknown; World-class is never assigned here):
  - **Minimal**: no test reaches it. This is a fact about the files, so it holds whether or not a run is recorded, as long as
    every test file could be read. If a test file could not be read (past the cap, a syntax error, over 1.5 MB, not opened), a
    module that no read test reaches is **Unknown**, not Minimal: "Some test files could not be read, so it cannot say that no
    test reaches this module. Not read: ...", naming up to three of them with the reason.
  - Otherwise it follows the **latest recorded test run** (below), and only if nothing it depends on changed on disk after that
    run. What it depends on is the module itself, every file it imports (directly or through other files), every test that
    reaches it, and what such a test imports or reaches. A change in any of them makes it **Unknown**: "Changed since the last
    test run: FILE changed at HH:MMZ, after the latest test run ...", and, when FILE is not the module or a test that reaches
    it, how it matters ("... and this file imports it, directly or through other files"). A changed or new test file makes
    Unknown only the modules it reaches. A changed or new `conftest.py` or pytest configuration (`pytest.ini`, or a `pyproject.toml`,
    `tox.ini` or `setup.cfg` that has a pytest section) is wider: it can change every test's outcome without being imported, so it
    makes every tested module **Unknown** ("a conftest or pytest configuration changed after the run, so the earlier result may
    not hold for any module"). A change to another file (a document, another kind of configuration) changes nothing.
  - **Bad**: a test file that reaches it is *named as failing* by that run.
  - **Optimal**: at least one test reaches it, and the run was a **whole-suite pytest run that passed** (a green round, or a probe
    with exit code 0).
  - **Unknown**: everything else, with the reason: no run is recorded; the run was a unittest subset (which cannot show that
    every test passed); the run failed but did not record which test files; a fix was applied after the run; the project is a Node
    project (Runesmith does not run npm test).
- **The latest recorded test run, whatever ran it.** Chosen by the same rule as `Workspace.object_statuses` (so the node, the ring
  and the ladder never disagree): the map's probe (`ENVIRONMENT.json`) if it is newer than the round and conclusive (made at the
  same second as the round, an error, an unavailable runner, a failing run and a unittest run still win; a passing pytest probe
  does not override the round's record), else the repair round's own discovery run (`WORK.json`), else a measuring round
  (`fix-tests/MEASURED.json`); a fix applied after the round supersedes it as "tests not run since the fix". What each records:
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
  *changed since the last test run* (it changed, or something it imports or reaches changed, or a conftest or pytest
  configuration changed), *not run* (no run recorded), or *no result of its own is recorded* (stated plainly).
- **Badges** (read from existing state; nothing is written): a fix or draft waiting for the owner that touches the file (Work &
  proposals); last changed by Runesmith (ledger and draft/proposal records: applied by you, applied automatically by a checked
  build, or a fix applied; time and author model); in an open milestone (a draft for it touches the file, or its own words name the
  file); failing tests count. If the file changed on disk after Runesmith's change, the panel says so and says who is not
  recorded. A milestone's words name a file only as the exact relative path of a file the scan found: a web address, a network
  or drive path, an absolute path or one that climbs out of the folder names nothing, whatever its last part is called. No path
  from a milestone, a draft or a proposal is ever resolved on the disk (on Windows that would reach out to a network path); it is
  joined and checked as text, and only used to find a file the scan already listed, which never follows a link.
- **Detail panel:** path, kind, lines, imports, imported by, tests that reach it and their last results, last change and by whom
  (ledger where known, else file time), open work, and the state's reason, each with its source and time.
- **Scale:** at most about 60 nodes drawn; over that, each folder keeps its most important parts (a failing one, one with work
  waiting, then the largest) and shows one "+N more" part; "Show all" for a folder draws up to 60 of its files. The list view
  and the panel reach every file the list carries, and the list carries at most 500 (a folder that large is read in part and says
  so): every part that is drawn first, then the most important of the rest by the same order, returned in path order. A part
  carries at most 50 entries of each of its lists (`imports`, `imported_by`, `tests` on a module, `reaches` on a test file),
  sorted by path; `imports_count`, `imported_by_count`, `tests_count` (modules) and `reaches_count` (test files) hold the true
  totals, and the panel's list ends "… and N more". The facts of a part (its evidence) are built only for the parts the list
  carries. The layout is a function of the structure alone and follows section 9: sectors in a fixed order
  (source, tests beside their source, documents, configuration, data), source files by how central they are.
- **Empty folder / non-code folder:** an object with no files shows a plain sentence and the objects as before; documents are
  grouped with no edges and the sentence says there is no code to link.

**Automate (module):** "Watch its tests" (turns on `probe_tests` and runs Re-map & measure, after a confirmation that carries the
Settings switch's own warning that the project's code runs on a throwaway copy); "Fix the failing tests" (the Overview action,
offered only when the Overview offers it; it works on the whole project and the button says so); "Make a milestone for this
file" (a small form; nothing is saved until Save); "Keep Runesmith out of an object" (`exclude`, only for objects, with the same
immediate request Settings and the object panel send; the control reads the list again just before it writes, so a panel that
was open while the list changed elsewhere cannot overwrite that change). **Test file:** "Watch its tests" and a link to Activity. **Doc:** a link
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
  target, created, validation, trial record, when it was last made active (its latest activation). Automate: "Make active" (roll back) and, for the
  generation on trial, "Stop this trial", both with their existing confirmations and ledger records.
- **Self-knowledge metrics** (repair yield, seconds per repair, calls per repair, false "fixed" rate): each with its sample size
  and window ("41 judged sessions since 09:01Z") and, during a trial, per arm (sessions marked with the arm since the trial
  opened). Fewer than 10 judged sessions: "few sessions", and no band (only the value). Each metric opens its definition and evidence; Automate: the share and
  the self-improvement switch.

## 3. Development: the plan and the climbs

- **Goals** ("Operating toward"): the owner's goals, as before. Automate: Goals & plan.
- **Plan graph** (`plan_graph`): milestones as nodes, **prerequisites as edges** (an arrow means "needs this first"; dashed is still
  open); grouped by track, columns by how many prerequisites deep (placed as section 9 says); color by state: **done**, **ready** (open, nothing it needs is
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
  project, or by the map's own test probe when no round has seen that failure; the window says which); **Repair** (judged attempts: session records that got the held-out judge's verdict; since the
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
width, light and dark. The layout of section 9 is checked by `tests/test_map_layout.py` (with the helper `tests/map_layout_dump.mjs`,
which runs `map-layout.js` under Node): no two names, parts or folder labels overlap, the same layout twice and for any order of the
lists, the fixed order of the sectors, tests beside the source they reach most and in the order of their modules, parts nearer the
hub the more they are imported, links that keep out of the hub (including one between opposite sides), the failing test's links in
the Bad colour, a plan read left to right with even columns and no link behind a milestone; and in the browser by B28.13 to B28.15
(measured names, hover and focus, the phone list) and B30.07 (the real plan drawing).

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
11. **A probe and a round at the same second** are chosen by the rule `Workspace.object_statuses` uses (a passing pytest probe never
    overrides the round's record at a tie), so the node and the ring cannot show different runs. The first draft let the probe win
    every tie.
12. **A change reaches what depends on it.** A module is no longer Optimal when a file it imports changed after the run, directly or
    through other files, or when a test that reaches it depends on a changed file (a changed or new test file makes Unknown the
    modules it reaches); and a changed `conftest.py` or pytest configuration makes every tested module Unknown, because it can change
    any test's outcome without being imported. The first
    draft only looked at the module and the tests that reach it, so a green run stayed Optimal over code that had changed under it.
13. **Minimal needs every test file read.** Imports are read for test files first; a test file that could not be read (past the cap, a
    syntax error, over 1.5 MB, not opened) leaves a module that no read test reaches Unknown, not Minimal, with the reason. The first
    draft read the files in path order, so a long project's tests, which sort after its source, were the ones skipped.
14. **A test name shared by several modules** links to the nearest one, or to none when none is nearer than the rest. The first draft
    linked a name to every module in the project that carried it, so one package's test blessed another package's module.
15. **No path from a record or a milestone's words is resolved on the disk.** A web address, a network path or a drive path in a
    milestone gave a file badge by its last name, and resolving it would reach out to the network on Windows. The words now count only
    as the exact relative path of a scanned file; draft and proposal paths are joined and checked as text.
16. **The never-touch list applies at once.** An object added to it is not read by the structure view before the next map is written;
    the first draft trusted the map file until then. The control that edits the list reads it again before writing.
17. **The list keeps what is drawn.** Over 500 files the list carries every drawn part first, then the most important of the rest, in
    path order (the first draft cut the list at 500 in path order, so a failing test late in the alphabet was drawn by no list and
    could not be opened). A part carries at most 50 entries per list with the true total beside it; the facts of a part are built only
    for the parts the list carries, which is what keeps a 20,000-file project fast.
18. **Discover says how it found a failure** (this changes the Discover sentence in section 4): a failing probe the round has not
    seen is counted as found by the map's test probe, with the probe's time, and the unit, definition and window say so; a round
    alone keeps its older words.
19. **Self-knowledge metrics** (this changes the sentences in section 2): under 10 judged sessions a metric has no band, only its value
    and "few sessions"; each arm of a trial names its window ("N judged sessions since the trial opened"); a generation's "made
    active" time is its latest activation, not its first.
20. **The drawing's layout now carries meaning** (section 9). The first draft ordered folders by path and filled rings in name order,
    so a tests folder could sit anywhere, a sub-folder was a sector of its own, links curved through the hub, folder names floated
    away from their sectors and names could touch. Now the sectors have a fixed order (source, the tests beside their source,
    documents, configuration, data), a sub-folder is inside its parent, source files sit nearer the hub the more they are imported,
    links never cross the hub and are faint until a part is in hand, names are cut in the middle and never overlap, and the plan
    graph has even columns, ordered rows, and links that do not run behind a milestone. Nothing was added to what the map says: only
    where it says it.
21. **Test links are not short, parallel or uncrossed; only their order is kept.** The brief asked for each test file at the angle
    of the module it reaches, so that the dashed links are short and parallel. That cannot hold for a sector of tests that is next to
    its source sector (the two sets of angles differ), so a test file keeps the *order* of its module, counted from the edge the two
    sectors share, and the sectors are neighbours. Measured on the 42-file demo project, the dashed links average about 300 px
    against about 200 px for imports, and about a third of the pairs of dashed links cross (placing each test at the mirror image of
    its module, or by order only, gave the same figures). Source files are ordered by how central they are, so a tested module is
    often in an inner ring, which keeps the links long. They are faint until a part is in hand for that reason. An outer band of tests
    over the same angles as the source sector would make every link a short radial line, but it takes the tests out of the sector
    order the brief fixes (source, tests, documents, ...), so it was not done; it is the one change to try if the dashed links read badly.

## 9. Layout: where every part is placed, and why

The geometry is `runesmith/app/static/js/views/map-layout.js`: plain arithmetic, no browser, nothing random and nothing measured, so
the same project always gives the same drawing and no position depends on the order a list arrives in. Text widths are estimated
from the letters (generously: a real browser measures 5 to 15 per cent narrower), so the drawing does not depend on a font. It is
tested by `tests/test_map_layout.py` (the same file run under Node, on fixture projects) and by the browser loops B28.13 to B28.15 and
B30.07, which measure the real drawing. The purpose of a map is perspective, so the rules below put the same kind of thing in the
same place every time; none of them adds a fact or a control.

**Environment: hierarchy.** The project is the hub, its folders are sectors (wedges of the circle around it), and its files are the
parts inside a sector.

- **What a folder is.** The most common kind among the files in it (and in the folders inside it) decides: *source*, *tests*,
  *documents*, *configuration* or *data and other*; a tie goes in that order. The loose files at the top of the project are one folder
  ("top level"), sorted the same way. The shared "(other folders)" group always comes last.
- **Where the sectors go.** Clockwise from 12 o'clock: the source folders, the one with the most files first (the folder's own files
  and those of the folders inside it count; the path breaks a tie), each followed by the folders of tests that reach it most; then
  folders of tests that reach no source folder; then documents; then configuration and build; then data and other; then "(other
  folders)". A sector's width grows with its parts: 60 per cent by its share of the parts and 40 per cent in equal shares, so a small
  folder is never lost.
- **Tests beside their source.** A folder of tests sits right after (clockwise) the source sector that holds the most of its test
  files' main modules, so the two share an edge (the dashed links are as short as neighbouring sectors allow; see section 8, item 21, for how
  short that is). The *main module*
  of a test file is the one it is named for, else the one it reaches by most reasons, else the first by path; only drawn modules count.
  (This reconciles "then tests" in the order with "next to the source they reach": the tests come after the source they belong to.)
- **Inside a source folder: how central.** Files are ordered by how many files import them, most first, then by name; the most
  imported are nearest the hub, ring by ring outwards, and inside a ring by name. Documents, configuration and data have no links, so
  they go by name; in a folder that mixes kinds the source files come first.
- **Inside a folder of tests: the module's place.** Each test file takes its place, in order, by the module it reaches most, counted
  from the edge the two sectors share (the module nearest that edge gives the first place); this keeps the order of the modules and the
  two sectors side by side, and does not make the dashed links short, parallel or free of crossings; files that reach no module come
  last, by name. A test file whose module is in its own sector (a folder of tests inside a source
  folder) counts from that sector's start instead, with no mirroring.
- **A folder inside a folder.** A folder that sits inside a folder that is itself drawn is a sub-folder: it is drawn inside its
  parent's wedge with its own share, its own dashed outline and its own label ("ui · 3 files"). One level only: deeper folders join the
  topmost one. Beyond 12 folders the smallest share one "(other folders)" group, and beyond about 60 parts a folder shows "+N more" as
  one of its parts (the existing cap; section 1).
- **Rings and room.** Rings are as far apart as the largest part and its name need, and the parts on a ring are spaced for the boxes
  their names make (a name is wide at the top and bottom of the circle and narrow at the sides). A last pass moves any part that still
  touches another, or the hub, outwards along its own line, so no two parts, names, folder labels or the hub's box ever overlap.
- **Size.** A part's radius is 8 + 4.6 × log10(1 + lines), clamped to 8 to 24 px (a file of about 3,000 lines or more is the largest;
  a file whose lines are not counted is drawn at 10 px). The legend says so in one line.
- **Names.** A part's name is drawn at 10 px, at most 16 characters, cut in the middle so that both its beginning and its extension
  stay ("test_app_en…long_name.py"); the full path is in the part's tooltip and its panel. A folder's label reads "src/bakery · 8
  files" (a sub-folder by its path inside its parent, a long path cut in the middle); it stands just outside the sector's last ring at
  the sector's middle angle, and if it would touch a name or another label it moves outwards until clear (a thin dotted line joins it to
  its sector when it had to move far).
- **Links.** One thin curve per link: an import is a solid line, a test reaching a module is dashed. All links are faint until a part
  is in hand: hovering or focusing a part brightens its own links and dims the rest; a selected part keeps its links bright. The links
  of a failing test file are drawn in the Bad colour, and stay red when bright. No link crosses the hub: a curve bows away from it, as
  far as it must (so two parts on opposite sides are joined by a curve that goes round). Links are drawn under the parts.
- **Order for the keyboard and the list.** The drawing lists its parts folder by folder, ring by ring, which is also the Tab order;
  the list view shows the same folders in the same order (a sub-folder under its parent), the files of a source folder by how central
  they are.
- **Around the drawing.** The tool bar, the line naming the test run and the legend are in the page's flow, above and below the
  drawing, never over it. An open panel lies over the right of the drawing, as before; the line naming the run stops before it. On a phone the list view
  is the first view and nothing is wider than the screen.

**Development: the plan graph.**

- **Rows and columns.** One lane per track, in the plan's order; a lane is as tall as its tallest column. A milestone's *depth* is how
  many prerequisites deep it is (the longest chain behind it). Every depth in use takes one column, so there is no empty column and the
  columns are evenly spaced; the columns are shared by all lanes, so a milestone sits to the right of everything it needs, even when
  that is in another lane, and a done milestone sits to the left of what depends on it.
- **Order inside a column.** By where what it needs sits (the average height of its prerequisites); the plan's own order breaks a tie.
  Links cross as little as the order allows; the graph never reorders by name.
- **Links.** Between neighbouring columns a smooth curve; a link that skips a column leaves the right side of its milestone, runs in
  the space between two rows and enters the left side of the next one, so no link runs behind a milestone. An arrow means "needs this
  first"; dashed is still open. Track names are drawn over the links, never under them.
- **Needs you** is marked three ways, never by colour alone: a thick red outline, a red "!" flag on the corner, and the reason on the
  second line ("1 draft waiting for your review").
- **Spacing.** Columns are 232 px apart, rows 62 px, lanes 10 px; boxes are 172 by 46 px.

**Self, Operations and the tracks.** Only spacing: the tool bar and the legend sit in the page's flow (the legend no longer covers the
caption under the ring), and the Self ring is centred in the room left of its panel instead of running under it. The tracks and
ladders, and Operations, are as they were.
