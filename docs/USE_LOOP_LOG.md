# Use-loop log

Runesmith Studio is improved in loops. In each loop someone uses the product for real, through its own interface and API. They play a named persona with a goal. Everything that gets in the way is fixed, and the loop is written down here. Nothing in this log is a claim about Runesmith's capabilities: those live in the evidence table in the README. This is product work.

**Format.** Each loop records:
- the persona and their goal;
- what they did;
- what got in the way (**findings**);
- what changed (**fixes**);
- how the fixes were checked.

Times are UTC.

## Personas

| Persona | Folder | Thinking power | Wants |
|---|---|---|---|
| **Mira**, owns a bakery, not technical | empty | none, then a chat window | a small order website, without learning tools |
| **Dev**, maintains a Python library | a repo with failing tests | a small local model | fixes to review, without surprises |
| **Ola**, writes documentation | a docs folder with broken links | an API key | tidy docs and a plan |
| **Tam**, leads a team | a folder of several projects, one sensitive | a router with fallbacks | an audit trail, and one project never touched |
| **Ren**, evidence-minded researcher | any | several models | to verify claims: trials, the ledger, receipts |
| **Kit**, a tester of edges | strange folders: huge, unicode, CRLF, BOM, read-only, symlinks | any | to break it |

## Loops

### Loop 1 — Kit breaks the folder (2026-09-25T05:38Z)

**Goal.** Point the Studio at a hostile folder:
- unicode names (`日本語 プロジェクト`);
- `&`, quotes and braces in names;
- a workspace name with `<b>` tags;
- a Python package with CRLF endings and a UTF-8 BOM;
- invalid UTF-8, a binary file;
- spaces in paths;
- a Node project;
- 3,000 one-byte text files;
- 14 levels of nesting.

**Did.** Opened it and completed genesis in explore mode. Called every read endpoint, ran a measured map, then a quick one. Checked the rendered map.

**Findings.**
1. Every endpoint answered (the genesis map of 3,012 files took 1.7 s). The name with `<b>` rendered as literal text everywhere, in the page and in the SVG map: escaping holds.
2. **A quick map erased measurements.** The scheduled round's map (no test run) replaced the pass rates of the earlier measured map, although nothing had changed. The map flip-flopped between measured and unknown.
3. **The document ladder was wrong for plain text.** A folder of `.txt` files counted as a document collection, but its first rung said "documents present: not achieved", because only Markdown was counted.
4. **The legend covered a node.** With objects below the hub, the legend overlapped the lowest node.
5. (Windows itself refuses `<>` in names, and paths near 260 characters, so those could not be tried here.)

**Fixes.**
- `envmap.build_environment_map(previous=...)`: a code object keeps an earlier measurement while its fingerprint is unchanged (names, sizes and modification times of its Python and config files). The measurement is marked `measured_utc`, and the unknowns say so. A changed object becomes unknown again. The Studio passes the previous map.
- Documents are `.md`, `.markdown`, `.rst`, `.txt`, `.adoc` and `.org`. The ladder counts all of them, while links are still checked only in Markdown. There is a new `documents` fact, and the index can be `README.rst`, `README.txt` or `README`.
- The map fits its real bounds, with room for the tool bar and legend, and flatter rings that use the wide canvas.
- The side panel shows "tests measured N min ago", or a **Measure its tests** button.

**Checked.** Two new tests: measurements are kept, then dropped after an edit; text files count as documents. 24/24 map and Studio tests pass. Live on the edge folder: `crlf-lib` kept its measurement across a quick map, and "many files" shows 3,000 documents.

### Loop 2 — Dev keeps a library green (2026-09-25T05:58Z)

**Goal.** Dev's folder holds two projects:
- `mathkit`, with two real bugs in two files. One file is saved the Windows way: a UTF-8 byte-order mark (BOM) and CRLF line endings.
- `netthing`, whose only test imports a module that is not installed.

Dev wants fixes to review and no surprises. A scripted offline Worker plays the small local model.

**Did.** Ran a round, read the proposals, applied both, ran the tests, ran a second round, then undid one fix.

**Findings.**
1. **Files with a byte-order mark could not be repaired.** The kernel handed organs the source text with the BOM still in it, and Python's `ast.parse` rejects that character. The organ could not index `twice`, and the attempt ended "navigation rejected". This is a kernel bug that would hit every file saved with a BOM, which some Windows editors do.
2. **The CLI's `repair --apply` wrote in text mode.** On Windows that turns LF into CRLF, and it dropped a file's BOM.
3. **"Error without failures" said nothing.** When `netthing`'s tests could not even start, the Studio did not say why.
4. Worth knowing, working as designed: after one fix is applied, the other failing test counts as new work, because its object's source changed. A second round serves it again.

**Fixes.**
- `objects/code.read_src_files` reads source with `utf-8-sig`, so organs never see the BOM.
- A new `objects/code.encode_like(text, current)` writes text back in the style of the file it replaces: its BOM and its line endings. The Studio's apply, undo and draft overwrite use it, and so does the CLI's `repair --apply`. The comparison text is BOM-free and LF.
- `discover` gives a `detail` (the first error, with local paths removed) and a `triage` when no test could run. The round log says, for example, "the tests could not run (ModuleNotFoundError: No module named '…'): missing third-party module …: install it". The map's side panel shows it in a warning box.

**Checked.**
- Two new tests:
  - a BOM+CRLF file is read without the BOM, parses, comes back byte-identical, and survives apply and undo;
  - discovery explains a collection error and triages it as environment.
- 29 of 29 Studio, map and steward tests pass, and 42 of 42 Studio, kernel and proposals tests.
- Live rerun: 2 of 2 fixes were accepted, including the BOM file. Apply kept the BOM and CRLF, the tests went from 2 failed to 2 passed, round 2 was green, and undo restored the exact bytes.

### Loop 3 — Mira starts a bakery website from nothing (2026-09-25T06:05Z)

**Goal.** Mira is not technical. She has an empty folder, no model and no key, and she wants a page where neighbours can see today's bread. She works only through the Studio, by clicking. For this test the chat model's replies were pasted by hand.

**Did.**
1. Watched the opening sequence and skipped to the naming.
2. Named it "Moonlight Bakery" and described it. "Build something new" was already chosen, because the folder is empty.
3. Followed the map's "Tell Runesmith what to build".
4. Set up a chat window, drafted a plan through the relay, then drafted and wrote the first files.

**Findings.**
1. The naming step and the empty-world map were clear. The one call to action led straight to Goals & plan, with her description already in the brief.
2. **She got stuck at "Draft a plan".** It needed a model, and the only way forward was "Add thinking power" on another page, through a provider picker. For a non-technical owner, that is a detour at exactly the wrong moment.
3. **The relay was hard to find.** When the Planner's request was waiting, the only sign was the top-bar pill, and the relay lived on the Thinking power page.
4. The "Skip intro" button stayed on screen during the naming step, where there was nothing left to skip.
5. **Her website did not look like one on the map.** An `index.html` and a `style.css` were mapped as a plain folder of loose files, with nothing to say what a website should reach next.
6. The plan card's header buttons overflowed in a narrow column.
7. Writing a milestone's first files left the milestone at "open".

**Fixes.**
- **"Use a chat window (no key)"** is one click, on Goals & plan where drafting stops and on the Overview when there is no model. It sets up the relay for the Planner and Improver roles: not the Worker, since repairs take many calls.
- **The relay is reachable from anywhere.**
  - The "Needs you" pill opens it in a side drawer: copy, paste, send, then the drawer closes itself.
  - When a request arrives on another page, a toast offers **Open the relay**.
  - The relay panel also has **Skip**, which declines a request; the skip is recorded in the ledger.
- **A website object kind** in `envmap`, all static, with nothing executed or fetched:
  - facts: pages, stylesheets, scripts, and the internal `href`/`src` references that resolve;
  - objectives: link integrity, and phone readiness (the viewport tag);
  - a ladder: pages, index, styles, mobile ready, titles, links resolve;
  - a folder with an `index.html` at its top is one website.
  - The Planner now sees these facts.
- The map's center panel shows the folder's own object (a website, documents or loose files) with its objectives and ladder.
- The naming step drops the Skip button. Card headers wrap.
- Writing a draft moves its milestone from open to "in progress", and the toast says so.

**Checked.**
- A new test for the website ladder, including a broken image reference, and 27 of 27 Studio and map tests pass.
- Live, Mira's whole journey ran through the UI:
  1. genesis;
  2. one-click chat window;
  3. plan v1, through the drawer;
  4. a draft sent in the relay's `@block` reply format;
  5. "Write these files";
  6. the map shows **Website: links 100 % optimal, mobile ready 100 % optimal, every rung achieved**.

### Loop 4 — Tam runs a team folder (2026-09-25T06:09Z)

**Goal.** Tam's folder holds several projects:
- `billing`, which has a bug;
- `payroll`, which is sensitive and must never be read;
- a handbook.

The Worker role lists a desk Ollama first and a second model as fallback, but the Ollama is off. Tam also keeps a key for a remote Improver. Tam wants work done, an audit trail, and a way to share the records safely.

**Did.**
1. Excluded `payroll`.
2. Added the dead local model and a keyed remote model through the API, then ran a round.
3. Verified the ledger and exported a snapshot.
4. Searched everything for the key.

**Findings.**
1. **One dead model stopped the whole round.** The reachability check refused the round as soon as the first Worker model was down, although a fallback was listed. The Planner's borrowed models also ignored which models were skipped.
2. The message quoted a raw Windows socket error ("[WinError 10061] …") instead of saying what to do.
3. Everything else held:
   - `payroll` was listed as excluded and was byte-for-byte untouched after the round;
   - the ledger verified (12 records);
   - the snapshot had 28 files, no secrets file and no key text;
   - the key never appeared in the inference API or `runesmith.json`.

**Fixes.**
- A round now skips unreachable Worker models ("Skipping the Worker model 'desk-ollama' this round: … Its fallbacks take over"). It stops only when none is reachable.
- `Workspace.router(skip=…)` leaves skipped models out of every role, including the Planner's borrowed ones.
- Unreachable messages name the fix for the preset: "is Ollama running? Start the Ollama app, or run `ollama serve`"; LM Studio's local server; `llama-server`.

**Checked.** Live: the round skipped the dead Ollama, the fallback repaired `billing` (1 served, 1 accepted), and `payroll` stayed untouched.

**Noted, not changed.** The Studio has one owner. The ledger records what happened, not which person did it, so a shared team Studio would need identities. This is a limitation for teams, to state in the docs.

### Loop 5 — Ren checks the claims (2026-09-25T06:13Z)

**Goal.** Ren trusts receipts, not words. Ren wants to see self-improvement as it really works:
- adopting C7 from the library;
- the trial and its looks;
- lineage and rollback;
- whether the ledger tells the truth about who decided.

**Did.**
1. Adopted C7 in a scratch home, which opened a trial.
2. For the page only, gave the trial synthetic outcomes through the kernel's own `Trial` class.
3. Made C7 active by hand, then rolled back to g0.
4. Read the ledger and verified the chain. Captured the page.

**Findings.**
1. **Choosing by hand left the trial running.** When the owner made a generation active, the open trial kept assigning work to "incumbent" and "candidate" arms that no longer described what ran. Its looks could even have "activated" a generation that was already active.
2. The closed-trials list would have called such a trial "rejected".
3. The trial showed raw generation ids ("gen-57e0cda73731") where the owner thinks "g0" and "C7". The library button said "Adopted as gen-…".
4. Everything else held:
   - the adoption was checked and frozen, but not activated;
   - the looks table showed each look's counts and both p-values;
   - the ledger recorded "owner's choice" for both manual activations;
   - the chain verified.

**Fixes.**
- `Workspace.activate_generation` closes an open trial with the decision `closed_by_owner`. The file is archived as `TRIAL-<candidate>-closed_by_owner.json` and the ledger gets `trial.closed_by_owner`. The confirmation says so beforehand, and the toast afterwards.
- The page and activity feed describe each trial outcome in plain words: "won: activated", "did not win: rejected", "closed by your choice".
- Arms and closed trials show names ("g0 · 57e0cda73731"). The library button says "Adopted: on trial now", "Adopted: active" or "Adopted".

**Checked.** The library test now covers:
- adopting;
- the owner's activation closing the trial;
- `closed_by_owner` in the closed list;
- rolling back.

Captured, the page shows the running trial, the arms, the looks and the closed trial.

### Loop 6 — Ola tidies a handbook (2026-09-25T06:27Z)

**Goal.** Ola writes documentation. Over time her handbook's links went stale:
- a page moved into `setup/`;
- `faq.md` became `FAQ.md`;
- a link misspells `configuraton.md`;
- one link points to a changelog that was never written.

Her small site references `images/hero.png`, which lives in `img/`. She wants tidy docs, preferably without a model for chores like this.

**Did.** Mapped the folder, asked for fixes on each object, applied the drafts, mapped again and read the result.

**Findings.**
1. **Only a model could help.** Broken links were reported, but fixing them meant drafting a plan through a model, for what is mostly a lookup.
2. **A case-only mismatch was invisible.** `faq.md` → `FAQ.md` counted as fine on Windows, whose disk ignores case, although the link breaks on a web server or on Linux.

**Fixes.**
- **Link doctor** (`Workspace.suggest_link_fixes`, `POST /api/links/suggest`, and "Suggest fixes for N broken links" on the map). No model is involved.
  - For each broken internal link in Markdown or HTML, it finds the existing file with the same name, or failing that the closest name (difflib, cutoff 0.72), and rewrites the path. It keeps any `#anchor`.
  - The fixes become one unverified draft ("Runesmith (no model): closest existing file").
  - Links with no similar file are listed and left alone.
- **Drafts can hold edits** (`base`). An edit is applied only onto the exact version it was made from: a changed file is a conflict, not an overwrite. The Drafts tab shows edits as diffs.
- **`envmap.exists_exactly`.** Link and reference checks require the exact case of every path part, so `faq.md` → `FAQ.md` counts as broken, flagged `case`, and the link doctor fixes it.

**Checked.**
- Two new tests:
  - the link doctor: anchors kept, an unresolvable link left alone, a conflict when the file changed, then applied and undone;
  - a case-only mismatch found and fixed.
- 30/30 map and Studio tests pass.
- Live: four handbook links fixed (a move, a case change, a typo) and the site's image fixed. `CHANGES.md` and `handbook.html` were honestly left, with no similar file, and the map still shows those two as broken.

### Loop 7 — Kim closes the window mid-plan (logged 2026-09-25T06:59Z)

**Goal.** Kim asked the Planner for a plan through a chat window, then closed the Studio before pasting the answer. Later she opens it again. Nothing should be lost silently, and nothing should wait for an answer that can no longer arrive.

**Did.** Started a plan job on the chat relay, stopped the Studio while the request waited, started it again and read the state, the job history, the relay and the live log.

**Findings.**
1. **The interrupted job vanished.** After the restart, the history had no trace of the plan job that was running.
2. **An orphaned relay request stayed "waiting" for ever.** No call was waiting for it any more, so answering it did nothing, yet the status pill kept saying a request was waiting.

**Fixes.**
- The Worker writes `STUDIO_CURRENT.json` while a job runs. On the next start, `_recover()` records that job as `interrupted` in the history and says so in the live log ("run it again when you like").
- `Workspace.set_aside_orphaned_requests()` moves relay requests from before the restart aside, unanswered, records `manual.set_aside` in the ledger, and says how many it moved.

**Checked.** Live: after the restart, nothing waits, the history shows the plan job as interrupted, and both messages appear in the log.

### Loop 8 — Three businesses, one suit (logged 2026-09-25T06:59Z)

**Goal.** Show Runesmith at three very different sizes and use them like their owners would, for the website and the trailer:
- **Moonlight Bakery**, one owner on an old laptop: an order service, a shop website, docs and recipes;
- **Northwind Freight**, a company: four services nested in `services/`, a Node portal, runbooks, infrastructure, data contracts, and `payroll/` excluded;
- **Helio Clinics**, three clinics: a booking website, a reminder API, policies, a staff handbook, and `patient-records/` excluded.

**Did.** Built the three folders and drove each Studio through its API:
- first boot, goals, notes and blueprints;
- measurement and a repair round;
- a plan and a draft through the chat relay;
- the link doctor;
- in the freight case, a snapshot export for auditors;
- in the clinics case, applying the fix and measuring again.

Then captured every screen of each folder.

**Findings.**
1. **Nested projects had two names.** The map said `services/tracking-api`, but proposals and attempts said `tracking-api`.
2. **Nested nodes were hard to read.** The map node showed the whole path, cut short.
3. **Long workspace names were cut** in the map's hub ("Northwind Freight…").
4. **The test dot went stale.** Helio applied the reminder fix and measured again, and all tests passed. The map still showed the last round's red "failing" dot.
5. **The overview called drafts "proposals".** It said "2 proposals wait for your review" when both were drafts.
6. **The trailer's naming form could outlive its scene.** Restarting, or clicking a scene dot, during the finale left the form over the next scene. The demo typing ran on and could forge the name over another scene.
7. **Map nodes overlapped in a company-sized folder.** With ten objects, a second ring of 175 units sat closer than a node is wide: `web-portal` covered `customs`, and `infra` covered `tracking-api`.
8. **The trailer drew wide scenes small.** Every scene was fitted into a fixed 16:9 box inside a band about 2.7 times wider than tall, so a third of the width went unused and folder names were tiny.
9. **A stray "null" in the embedded trailer.** The DOM's `append()` prints a skipped element as the text "null".
10. **The phone-sized player kept its corner buttons** over the scene. Its rule came before the base rules, at equal specificity, so the base rules won.
11. **The evidence count could run negative for a frame** ("-366" in a capture), because a frame's timestamp can precede the animation's start.

**Fixes.**
1. `Workspace._object_label()` names a proposal's or attempt's object by its path in the folder, as the map does.
2. A map node shows the last path part as its title, with the parent in the subtitle ("services · next: tests pass").
3. The hub wraps a long name onto two balanced lines.
4. `Workspace.object_statuses()` reconciles each test status with what happened since the round:
   - a fix applied after the round shows as `fix_applied` ("measure to confirm");
   - a measurement taken after both replaces the round's verdict with the tests' own result.
5. The overview names what waits: "1 fix and 1 draft wait for your review".
6. Genesis:
   - each finale has a token, and changing the scene ends the typing;
   - `go()` removes the naming form whenever the scene is not the finale;
   - pages can follow and pick the three stories (`genesis:story`, `genesis:play`).
7. `ringLayout()` in the map:
   - up to 12 objects share one ring, grown only as far as its nodes need;
   - more go on rings 0.95 apart, which is wider than a node, and each ring's share is sized to its capacity;
   - a check of every folder size from 0 to 200 objects finds no overlap, in at most 26 ms.
8. `Genesis.frame()` gives the drawing the band's own shape and refits it on resize. Wide scenes, such as the folder's world, grew by about 40 %.
9. Genesis filters the empty parts before `append()`.
10. The phone-sized rule now comes last in `genesis.css`.
11. The count's progress is clamped to between 0 and 1.
12. **Website:**
    - the player's class no longer collides with the trailer's own `svg.stage`;
    - no grid can be stretched wider than a phone by its content;
    - any Studio screenshot opens full size.

**Checked.**
- The worker-round test now also covers the dot: `failing` after the round, `fix_applied` after Apply, `green` after a new measurement.
- 22/22 Studio tests pass.
- Live: Helio's API shows green after its applied fix, and Northwind's map shows ten objects without an overlap.
- The trailer was checked in the website's player at seven moments across the three stories: nothing overlaps.
- The Studio's `/cinema` was checked at player, full-screen and portrait sizes.
- At phone width (375 px), the page is exactly as wide as the screen.
- The three folders' 30 screens are on the website (republished, version 2).

### Loop 9 — Ada uses only the keyboard and a screen reader (logged 2026-09-25T07:51Z)

**Goal.** Ada cannot use a mouse. She drives the Studio with Tab, Enter, Escape and the shortcuts, and listens with a screen reader. Every part of the Studio should be reachable, say what it is, and never strand her focus behind a dialog.

**Did.**
- Walked every part of the Studio by keyboard alone, reading what each control announces:
  - the shell and the map;
  - comment mode and notes;
  - dialogs and drawers, and the command palette;
  - page changes.
- Checked text contrast in both themes.

**Findings.**
1. **The living map could not be used by keyboard.** Its objects were SVG groups that listened for clicks only.
2. **Nine clickable elements listened for clicks only:**
   - the overview's figures and its found objects;
   - notes cards and the attempts table;
   - model choices and presets;
   - the folder picker's entries and the folder switcher itself.
3. **Dialogs could strand the focus:**
   - drawers neither took focus nor gave it back;
   - Tab walked out of a dialog into the page behind it;
   - Escape closed every open layer at once, so a confirmation over a drawer closed both.
4. **Comment mode was for the mouse only** ("click anything").
5. **Page changes left the focus behind.** After a page change the focus stayed where the old page had been, and the window title never named the page.
6. **Several controls had no spoken name:**
   - icon-only buttons had only tooltips;
   - the palette's options were not announced as options;
   - every comment button said only "Comment on this".
7. **Faint text failed WCAG AA:** 4.0:1 on dark cards and 3.6:1 on white. The same held on the website and in the opening's fine print.

**Fixes.**
1. **Map objects are focusable buttons.** Each announces its name, kind, health, next rung and test result.
   - Enter opens the details and moves the focus there.
   - Escape closes them and returns the focus to the object.
   - A live update of the map keeps the focus where it was.
2. **`h()` makes every click handler keyboard-ready.** Any element with a click handler that is not natively interactive becomes a Tab stop, is announced as a button, and answers Enter and Space. This fixed all nine elements at once, and any future ones.
3. **`core.layer()`:**
   - dialogs and drawers stack, and only the top one hears Escape;
   - Tab wraps inside the top layer;
   - closing a layer returns the focus to what opened it;
   - drawers are labelled and modal.
4. **Comment mode works by keyboard.** Tab to anything commentable and press Enter. The banner says so, and the comment button reports whether it is on.
5. **Focus and titles follow the page:**
   - a skip link leads past the sidebar;
   - after a page change, its heading takes the focus;
   - the current page's link is marked with `aria-current`;
   - the window title names the page and the folder.
6. **Spoken names and roles:**
   - icon-only buttons have names;
   - the palette is announced as a combobox with a list of options, and follows the active one;
   - comment buttons name their target and their number of open notes.
7. **Faint text now passes AA:** #7e8aa4 in the dark theme and #636d86 in the light one, at least 4.7:1 on every panel. This applies across the Studio, the website and the opening.

**Checked.** Live in the browser, by key events only (the pane was in the background, where Chrome paints no `:focus` styles, so focus was read from the DOM):
- the skip link leads to the page;
- a map object announces "bakery-api: Python project, Bad health, next: tests pass, tests failing";
- Enter opens its details with the focus on their heading, and Escape brings the focus back to the object;
- comment mode plus Enter opens the notes with the focus in the text box; Tab wraps inside, and Escape returns to the object;
- key 1 opens the Overview with the focus on its heading, titled "Overview · Moonlight Bakery · Runesmith Studio";
- Enter opens a figure card;
- the palette's arrows move the announced option;
- with a dialog over a drawer, the first Escape closes only the dialog and the second the drawer, and the focus returns to "Run now".

22/22 Studio tests pass, and the website was republished (version 4).

### Loop 10 — Mallory's folder, and a monorepo (logged 2026-09-25T08:25Z)

**Goal.** "Drop it into any folder" has to hold for awkward folders too.

On Windows, anyone can make a junction (a folder link that needs no rights). Mallory's folder has three:
- one to a private folder beside it;
- one inside a Python project's `src/`;
- one that loops back into its own handbook.

The second folder is a monorepo: 29,065 files in 60 packages, vendored assets, 600 guide pages, a 20-level-deep path and odd file names.

**Did.**
- Mapped both folders.
- Ran test discovery and a throwaway copy on Mallory's project.
- Checked what a model would be shown and what a draft or a fix could write.
- Timed each Studio call on the monorepo, and profiled the slow ones.

**Findings.**
1. **Junctions were followed.** Python's walkers treat a junction as an ordinary folder:
   - the map read the private folder as a document collection, 42 files that are not in the workspace;
   - the project counted 46 files instead of 4;
   - the handbook's loop was walked 45 times, so it showed 90 documents instead of 2;
   - the workspace counted 179 files instead of 7.
2. **The throwaway copy that tests run in copied the private files through the junction.** A junction to a whole Documents folder would have copied all of it.
3. **A model would have been shown code from outside the folder.** Through the junction in `src/`, a fix could then target such a file, and Apply would have written outside the workspace. Drafts were already safe, because `_safe_rel` resolves every path.
4. **Blueprint candidates listed documents through links.** A chosen blueprint's text goes to the Planner model.
5. **The monorepo was slow and quietly incomplete:**
   - the first map took 18.6 s, half of it the new link checks, which cost two system calls per file;
   - the file count stopped at 20,000 without a word;
   - loading the goals page took 2.6 s;
   - the link doctor took 4.9 s, mostly spent building `Path.parents` for 20,000 files, and had no cap.

**Fixes.**
1. **`is_link()` in the kernel's code module** (a symbolic link or a junction). Every walker now skips links:
   - the map, where a linked top-level folder shows as "a link: not followed";
   - the source files a model sees;
   - both throwaway copies;
   - the blueprint candidates;
   - the link doctor.
2. **Writes cannot leave the folder:**
   - `apply_proposal` refuses any file whose real path leaves the project (`outside`);
   - `blueprint_text` checks each path again before reading it.
3. **The map walks with `os.scandir` (`_scan`).** Links, junctions, sizes and times come from the directory listing, with no per-file call on Windows.
   - The order and the fingerprints are unchanged.
   - The monorepo now maps in 2.6 s instead of 18.6 s.
4. **A scan that stops is reported:**
   - "20000 files or more in vendor, the folder as a whole: file counts and checks stop at 20000";
   - the middle of the map shows "20000+ files".
5. **The other two slow calls:**
   - blueprint candidates use the same scan: 0.7 s instead of 2.6 s;
   - the link doctor uses the scan, string prefix tests and one directory-listing cache: 1.1 s instead of 4.9 s.
6. **Lint:** three late-binding closures in the link doctor are bound explicitly (ruff B023).

**Checked.**
- New test: `test_links_and_junctions_are_never_followed`, with real junctions on this machine. It covers:
  - the map;
  - the source view;
  - the throwaway copy;
  - `_safe_rel`;
  - a fix routed through a link, which is refused while the outside file stays unchanged.
- 111/111 before the speed work; 58/58 Studio, map and kernel tests after it; ruff is clean.
- Live, after the fixes:
  - Mallory's folder counts 7 files, and `notes` shows as a link;
  - the throwaway copy holds the project's own 4 files;
  - the model sees `src/app/__init__.py` and `calc.py` only;
  - the monorepo timings are as above.
- `docs/STUDIO.md` now lists both limits.

### Loop 11 — Eve knocks on the Studio (logged 2026-09-25T08:32Z)

**Goal.** A web page Eve controls, or another program on the same computer, tries to reach the Studio, and a model's answer or a folder name tries to smuggle markup into it. Nothing should get in, and the Studio should answer bad requests instead of hanging.

**Did.**
- Probed a running Studio with raw requests (scratchpad `eve.py`, which reads the access key itself and never prints it), testing:
  - no cookie, and a rebinding Host;
  - a change without the custom header (as a plain form post would be), and one from another origin;
  - the key in an API query;
  - three traversal tricks on `/static`;
  - bodies that are oversized, not JSON, or not objects;
  - a broken or negative `Content-Length`;
  - the security headers.
- Read every place the Studio turns data into markup.

**Findings.**
1. **A `Content-Length` that is not a number dropped the request with no answer.** A negative one passed the size check, and `read(-1)` then held a server thread until the client hung up. Both need the owner's cookie, so this is robustness rather than a hole, but a Studio should answer.
2. **No markup injection was found.** Every name, label, title and status that the map lenses write into SVG goes through `esc()`, and everything else is a text node or set through the DOM.
3. **Loop 9 had missed two lenses.** The Self lens (kernel modules, organs, lineage) and the Development lens (every station) could still be used only with a mouse, and the Self lens's zoom buttons had no names.

Everything else held:
- no cookie gets 401, and a rebinding Host gets 421;
- a form-style post, another origin, and the key in an API query are all refused;
- all three traversal tricks get 404;
- oversized bodies get 413, and bodies that are not JSON objects get 400;
- the Frame-Options, nosniff, CSP and Referrer-Policy headers are present.

**Fixes.**
1. A broken or negative `Content-Length` gets 400 at once.
2. `keyboardNodes()` gives every node of a lens drawing:
   - a Tab stop, named by its tooltip;
   - Enter and Space to pick it;
   - a visible focus ring.

   In the Self lens, the picked part's details take the focus; in the Development lens, the station's notes open. Both drawings are labelled (for example "Runesmith's anatomy: 39 kernel modules, 2 organs and 3 generations…"), and the zoom buttons have names.

**Checked.**
- The probe reports 0 problems.
- The server test now sends both broken lengths and expects 400.
- Live in the browser:
  - the Self lens has 44 parts, each named ("__init__.py — Runesmith Core: …"), and Enter moves the focus to the details' heading;
  - the Development lens has 29 stations; Enter opens that milestone's notes with the focus inside, and Escape returns to the station.

### Loop 12 — Sam upgrades from the command line (logged 2026-09-25T08:44Z)

**Goal.** Sam used Runesmith 0.1 before the Studio existed:
- `runesmith init`;
- a scripted repair model in `runesmith.json`;
- `runesmith steward . --rounds 1`, which found the bug and proposed a fix;
- `runesmith proposals`.

Now Sam opens the Studio on the same folder, and later goes back to the terminal. Nothing should be lost, and the two views should agree.

**Did.**
- Ran the 0.1 commands in a fresh folder.
- Started the Studio there and read its state, its work, its attempts, its ledger and its roles.
- Named the creation, applied the fix and added a note from the Studio.
- Ran `status`, `ledger` and `proposals` in the terminal again.

**Findings.**
1. **The two share one home cleanly, with no migration needed.**
   - The Studio showed the terminal's proposal, attempt, generation and ledger history, and its roles came from the same config.
   - Applying from the Studio fixed the file.
   - Afterwards the terminal's `status` still read the home, and the ledger's 9 entries verified.
2. **The terminal ignored the owner's decisions made in the Studio.** `runesmith proposals` still listed the applied fix as waiting, showing a diff that was already in the file, and `--write` would have saved a patch that no longer applies.

**Fixes.**
- `list_proposals` carries each proposal's state from `PROPOSALS_STATE.json`: waiting, applied, undone or rejected, with its time.
- `runesmith proposals` shows the waiting ones in full, names the others ("applied in the Studio 2026-09-25T08:41:15Z"), and counts both.
- `--write` saves patches for waiting proposals only.

**Checked.**
- The apply test now also asserts that the terminal sees `applied` and writes no patch.
- 35/35 Studio, proposal and CLI tests pass, and ruff is clean.
- Live: Sam's `runesmith proposals` names the fix as applied in the Studio, and `--write` writes nothing.

### Loop 13 — Priya's model misbehaves (logged 2026-09-25T08:59Z)

**Goal.** Priya's models do everything wrong, on purpose:
- The Worker answers in prose.
- It tries to pass by editing the test.
- It quotes code that is not in the file.
- It hard-codes the visible case.
- Through the chat relay, Priya pastes prose instead of JSON, a 1.2 MB answer, and a draft that reaches for `../escape.txt`, `C:/Windows/…`, `.runesmith/runesmith.json` and `.git/config`.
- Then she skips a plan request.

Nothing unsafe may happen, and the owner should understand what did.

**Did.** Drove a fresh Studio with scripted misbehaving stand-ins, and read after each step:
- the rounds, the attempt records and the live log;
- the files;
- the relay's replies, the plan and the drafts.

**Findings.**
1. **Safety held.** Four misbehaving rounds gave no proposal, and neither the source nor the test changed. The relay refused the prose and the 1.2 MB answer, and the Studio kept answering. The reaching draft kept only `notes/ok.md` and refused the other four paths.
2. **Skipping a relay request destroyed the plan.** Skip sends a forced `{"skipped_by_owner": true}`, and the Planner took it as a valid answer: the job ended "done, 0 milestones" and replaced the owner's plan with an empty one. The next draft then failed ("draft a plan first"). A forced answer with no summary or milestones would have done the same.
3. **The owner read jargon:**
   - attempts ended "navigation rejected" or "budget exhausted";
   - failed jobs began with a class name ("PlannerUnavailable: …");
   - relay problems began with a code ("invalid_json: …");
   - the Skip dialog promised only that the step "moves on".

**Fixes.**
1. **`SkippedByOwner`.** A skipped request ends a plan or draft job as `skipped`, and nothing is saved: "Plan skipped: you skipped the request, so nothing changed."
2. **The Planner saves nothing unless the answer has every required part** (a summary and milestones, or a title and files).
3. **Plain words:**
   - each way an attempt can end has one sentence (`ATTEMPT_WORDS`), shared by the live log and the Work page, shown in the attempt's drawer and as the badge's tooltip;
   - failed Planner and Workspace jobs report their message only;
   - relay problems drop their codes;
   - the Skip dialog says a plan or draft stays as it is.

**Checked.**
- The planner test now also covers a skipped answer (`SkippedByOwner`, plan unchanged) and half an answer (`PlannerUnavailable`, plan unchanged).
- 23/23 Studio tests pass, and ruff and the JS syntax check are clean.
- Live after the fix:
  - skipping the second plan request left plan version 3 and its milestone in place, and the job reads "skipped";
  - the reaching draft kept `notes/ok.md` only;
  - nothing was written outside the folder, and Runesmith's config is intact.

**Not changed.** The shipped repair organ quietly drops an edit to a file outside `src/`: the kernel only accepts source overrides, so the test was never at risk. Recording "the model tried to edit a test" belongs in a future organ, which must win its own trial, not in an edit to the frozen g0.

### Loop 14 — Leo checks in from his phone (logged 2026-09-25T09:09Z)

**Goal.** Leo left a round running at the bakery and looks at the Studio on his phone, 375 px wide. Every page should fit the screen, and the living map should be readable.

**Did.** Opened the bakery's Studio in the browser's phone emulation. Visited all 12 pages and measured anything wider than the screen, ignoring decorations that are clipped anyway and containers that scroll on purpose, such as tabs and code. Looked at the overview and the map, then checked the desktop again.

**Findings.**
1. **Every page scrolled sideways.** Each was 730–770 px wide, because the top bar (title, status, Run now, Pause, comment, palette, theme) never wrapped and pushed the whole column wider than the phone.
2. **With the top bar fixed, smaller parts still spilled past the screen:**
   - the map's lens switcher (435 px);
   - model cards on Thinking power;
   - setting rows and chips;
   - a long key badge on Work;
   - rows of buttons.
3. **Section labels showed half-cut** in the icon-only sidebar ("WORKSP", "RUNESM").
4. **The map was unreadable.** Its wide ring drawing shrank to a strip about 150 px tall, in a 620 px box that was mostly empty.

**Fixes.**
- The main column may shrink (`minmax(0, 1fr)`).
- **Under 640 px:**
  - the top bar wraps into rows: the page first, then what is happening and the actions;
  - its buttons show their icons, and keep their names for screen readers;
  - rows wrap;
  - the lens switcher wraps;
  - a model card's actions take their own row;
  - a setting's control goes under its text;
  - long keys are cut with an ellipsis;
  - the map's tool bar wraps.
- **The icon-only sidebar hides its section labels.**
- **On a narrow screen the living map is a column.** The workspace sits on top, with the objects below it on one spine at full size, in a drawing exactly as tall as it needs. It switches between column and rings when the window crosses 560 px, and works out its width even before the page is on screen.

**Checked.**
- At 375 px all 12 pages are exactly as wide as the screen, and nothing spills out.
- The map shows the bakery's four objects as readable cards under the workspace.
- At 1440 px the map still draws its rings, and the top bar is one row with its labels.
- 111/111 (the full suite, after loop 13).

### Loop 15 — Olu's messy lifecycle (logged 2026-09-25T09:20Z)

**Goal.** Olu handles the Studio the way people handle apps:
- double-clicks the launcher twice on a new folder;
- kills the Studio mid-flight, which leaves a stale lock;
- opens a second folder while the first runs;
- tries to delete a folder whose Studio is open.

Each launch should reach the right Studio, and nothing should crash.

**Did.** Ran real `runesmith up <folder>` processes on the default ports, the way the launchers do. After each step I read which Studios answered for which folder, what each process printed, and which processes listened on which port.

**Findings.**
1. **Two launches at once crashed one of them.** Both started to set up the new folder's home. One died with a raw `PermissionError` traceback while freezing the first generation, because the other had just put it in place.
2. **On Windows, two Studios shared one port.** Python's `HTTPServer` sets `SO_REUSEADDR`, which on Windows lets a second process bind a port that is already listening. The second folder's Studio also bound 7300 (netstat showed two LISTENING processes). Its link reached the first Studio, which did not know its key, so opening two folders at once did not work.

   This is also a security gap: any local program could bind the Studio's port and receive the browser's requests, access link included.
3. **The rest held:**
   - a stale lock after a crash is ignored, because the old port no longer answers;
   - quitting from Settings removes the lock;
   - Windows refuses to delete a folder whose Studio still has files open, like any open app.

**Fixes.**
1. **The server takes its port exclusively on Windows** (`SO_EXCLUSIVEADDRUSE`, no `SO_REUSEADDR`). Elsewhere SO_REUSEADDR stays, where it only skips TIME_WAIT on a quick restart.
2. **`InstanceLock`: one Studio per folder.**
   - It is an OS file lock held for the Studio's whole life (`msvcrt` or `fcntl`), which the system releases when the process ends, even by a crash.
   - A second launch waits up to 15 s for the first one to answer, then opens it ("Runesmith Studio is already open for …").
3. **`generations.freeze` accepts a generation frozen a moment earlier by another process**, with the same digest, instead of failing.

**Checked.**
- Live, with real processes:
  - two launches at once: one Studio, and the other launch opens it;
  - kill then relaunch: a new Studio on the same port;
  - a second folder: its own port (7301);
  - netstat: no port with two listeners.
- New test: `test_one_studio_per_folder_and_one_listener_per_port`. The second instance lock is refused and becomes free after release, and binding a port already in use raises.
- Ruff is clean.

**Note.** The first run of this loop printed three throwaway Studios' access links into the working log. Those processes were stopped, so the keys are dead. The loop script now redacts any `t=` key before printing.
