# Changelog

## Unreleased: release hardening (2026-09-27)

**From out-of-box journey R1.** A first-time-user run on a clean export, a fresh profile and a Python without pytest completed with zero rescues (`D:/oob/JOURNEY_LOG.md`, research folder). The run surfaced the following.
- **Acceptance checks you approve in plain words (G1).** Automatic apply needs the owner's own acceptance checks, and few owners can write a unittest file.
  - A milestone now offers "Propose acceptance checks". A separate model call writes black-box checks from the milestone's own words, with one plain sentence per check.
  - The owner reads the sentences (the code is one click away) and chooses "Use these checks" or "Discard".
  - Approval freezes the file with its provenance, *model-proposed, owner-approved*. Replacing approved checks needs a reason and keeps the old file.
  - Proposals are validated: unittest only, no network modules, and every test must carry a sentence.
  - The first live proposals (journey Phase B) checked more, or less, than their sentences said. So each proposal now lists in plain words what it **assumes** that the milestone does not state, such as an exact output layout. The request asks the model not to invent formats.
  - Each proposal also gets a **trial run** on a throwaway copy of today's project, but only when checking is on. Checks that already pass on an unbuilt milestone, or that cannot run at all, carry a warning before the owner decides.
  - When the trial finds that checks already pass or cannot run, the model is asked **once** to revise them, and told what the trial found. If the revision fails, the first proposal stands with its warning.
  - Any exact word, layout or value a check requires must appear in its sentence. When a milestone promises behaviour under a failure (an interruption, damaged input), the check must cause that failure itself.
  - **Runesmith reads the checks itself** instead of trusting the model to follow that rule, because the weak free model ignored it. It finds every exact text a check's assertions require that its sentence does not say. Test input data and failure messages don't count.
    - Such text triggers the one revision, with the test and the text named.
    - Whatever remains is shown under the sentence ("Also requires the exact text: …") and published with it, so the builder is always told.
  - **A Checker role.** Proposing checks takes only a few calls, and they decide what "done" means. So Thinking power now has a Checker role. It uses the Planner's model unless the owner picks another, for example their chat window, while a free API model keeps building.
    - In the journey, the free model built well but wrote weak checks across four rounds. The stronger free route (Kimi K3 through NVIDIA) timed out after 211 s on every call.
  - **Replacing checks from the Studio (G3).** In the journey, a correct README failed a faulty check, and there was no way to replace approved checks from the page. Approved checks now offer "Ask for new checks", with a plain hint that a build which looks right may be failing wrong checks. New checks proposed next to approved ones replace them only through "Replace my checks" with a reason; the old file is kept.
  - A stray "null" no longer appears under proposals and owner files (B2).
  - Browser loop B20 now covers the acceptance-check page: the proposal display, approval, "Ask for new checks" and replacing with a reason. B20 fails on the previous page.
  - **On approval, the sentences become the milestone's public expectations.** Whoever builds the milestone now knows what "done" means, while the code stays private. A failing check is reported to the builder by its sentence, never by its assertion. Owner-written expectations are kept.
- **A refused call moves on to the next model (F12).** With retries off, as in every Studio call, the router tried only a role's first model. So one free provider at capacity stopped the work although the role listed another.
  - A call the gateway refused at submission never became a job: nothing ran and nothing was charged. Such a call now moves straight on to the role's next model, each at most once.
  - A call that was admitted never falls through, so a lost or slow answer is still never paid for twice.
  - **A call every route refused also moves on (J11-F2).** In journey J11, Milliner admitted the Checker's call to Gemini Flash, then every one of its routes answered "rate limited" before generating anything. The job failed, and Flash Lite, the Checker's second model, was never asked. When Milliner's own attempts show that every route refused and no token was used, the call now moves on like a refusal at submission. If any route generated, the answer is still kept for review and never paid for twice.
- **Journey J11 (make a small motion-graphics tool):** a new empty folder, and a brief for a command-line tool that turns a JSON project of shapes and keyframes into SVG frames.
  - **A builder sees the whole file a check starts with (J11-G1).** The Checker's first examples fed the program a project file in the format they defined. The owner's "What exactly is checked" and the builder's expectations showed only its first 60 characters, so a builder would have had to guess the rest of the format. Such files are now shown whole, up to 600 characters.
- **Journey J6 (let it improve itself):** a developer's `tally-tools`, with six everyday bugs and 7 failing tests.
  - **A fix whose files changed no longer "waits for you" (J6-F4).** A round repaired 5 failing tests with the free Flash Lite model, and the held-out judge accepted 4. Each repair had seen every bug and fixed all four files, so after the owner applied the first, the other three still said "waiting for you", although Apply would refuse them. A waiting fix whose files changed since it was made now reads "no longer fits: the files changed after this fix was made, often because another fix already covered them". It is not counted as waiting and offers no Apply or Reject. Browser loop B26.03.
  - **Stopping a trial, and what "self-improvement off" means for it (J6-F5).** With C7 adopted and its trial running, turning "Let Runesmith improve itself" off stopped new campaigns, but not the trial the owner had opened. The page now says so. The only way to stop a trial was to switch generations; there is now a plain "Stop this trial", which keeps what runs and records the trial as closed by the owner's choice.
  - The Planner, with no model of its own, said "uses kaizen" (an internal role name). It now says "uses the Improver's model" (J6-F1).
  - **A stray "null" on the Overview (J6-B1, introduced by the J5 release).** With no measurements, the "Your numbers" card is empty, and a plain DOM append printed it as the text "null" under the hero. Only real cards are passed now, and browser loop B19.14 fails on any stray "null" on the Overview.
- **Journey J5 (keep an eye on my numbers):** a bakery folder, with weekly till exports as CSV (`reports/week-35.csv` … `week-39.csv`) and a README: keep an eye on weekly revenue, and keep waste under 15% of what is baked.
  - **A report that arrives as a new file every week (J5-G2).** A measurement read one fixed file, so the owner would have had to edit it every week. A `*` in the file name now means the newest matching file in natural order (week-10 after week-9), for example `reports/week-*.csv`. The receipt names the file read. A pattern may match nothing yet.
  - **A share, such as sold ÷ baked (J5-G3).** "Waste under 15%" could not be expressed: no formulas. A new calculation, "Ratio: this column's total divided by another's", with its target: Share sold = sold ÷ baked, at least 85%.
  - **Modes & measurements in plain words (J5-F3).** The page read like an engineering spec: "Legacy routing retained until you save modes", "Construct milestones through the existing draft, check and delegated-apply gates", "Current execution is serial. Production adapters and speed/concurrency controls remain open additions", raw ids such as `map_plan`, and the toast "Queued through the normal serial worker". Each mode now says what it does, for example Operations: "Read your report files and record each number against its target. It never contacts a live service, deploys or sends messages." The limits read "Modes decide what Runesmith works on, never what it may do…". Operations and Optimize show "Numbers this mode reads" openly. They used to sit inside a closed section, next to the blocker "Select at least one measurement". An id is shown only for a custom mode.
  - **An idea to improve the numbers is easy to read (J5-F6).** With Optimize on, the free model's idea for the bakery was sound: split revenue and waste by item, to find the breads that are over-baked. On the page, though, it was folded shut under "proposed · model · time", with raw keys such as `expected_effect`, and the job said only "Optimization hypothesis saved". The newest idea is now open, under "Ideas to improve your numbers", with plain labels (The idea, What it should change, How to tell if it worked, Limits). The job says "An idea to improve your numbers is ready under Modes & measurements; nothing was changed." A ratio reads as a percentage in the live log ("Share sold: 90.2%").
  - **The numbers are on the Overview (J5).** The value was only on a project dashboard, under receipt hashes and caveats. A "Your numbers" card now shows each measurement's latest value, the file it came from, when it was measured, and its target (on target, off target), with "Measure now". Measuring says the number too: "Revenue this week: 2010.5 EUR from reports/week-39.csv." It used to say "Report measurement: measured".
- **Journey J2 (build while I'm away):** R1's Reading Log, upgraded in place and continued by the same owner.
  - **An old draft no longer "waits for your review" (J2-F1).** After the upgrade, the Overview said "1 draft waits for your review". It was R1's first, never-checked draft for "Books per month", left from hours before a second draft for the same milestone passed its checks, was written and finished it. Such a draft is now marked **superseded**: "Nothing to do here: its milestone is done. A later draft finished it and was written, so this one is no longer needed." It no longer counts as waiting, and it offers no write, recheck or revision. Its stored record is unchanged. Browser loop B26.02.
  - **Redrafting a plan keeps the work already done (J2-B2, caught before any harm).** With six milestones finished, the owner added a goal and was about to press "Redraft the plan". The model answers with titles only, and that answer was saved as the whole plan:
    - every finished milestone would have reopened, so a scheduled build would rebuild finished work;
    - ids were given by position, so the owner's approved checks (`acceptance/m4.py`), public expectations and drafts, all kept by milestone id, would have attached to other milestones.

    A redraft now keeps, exactly as they are, the milestones that are finished, under way or dropped, or that have drafts, checks, proposals, public expectations or a breakdown, and whatever those depend on. The model is told which ones are kept and plans only what is still to do. A repeated kept title is dropped, and new milestones get ids never used in the folder. A model can no longer mark any milestone done or choose its id, even in a first plan. The Redraft dialog says so.
  - **A check can type an empty value (J2-F3).** The new milestone "Search books" promises that "an empty query is rejected". The Checker's example ran `python -m readinglog search --query ""`, and Runesmith refused the whole answer: "Example 5, step 2 must be a list of 1-40 words". An empty word is now an empty argument, as a person types it with two quotes; the program part must still be a real `python -m`, script or `node` command. The Checker is told so.
  - **The map no longer says passing tests fail when pytest is missing (J2-B3).** After mapping again, Reading Log's ladder said "tests collect: not achieved; tests pass: not achieved" for 16 tests that pass on every build check, and "fast suite: achieved" for a run that never started. The map's probe ran only pytest, which a fresh Python does not have. It now runs the tests with Python's own unittest, as the build checks do. If unittest finds no tests either (pytest-style test functions, for example), every test rung stays unknown, with the reason. Maps made before this are marked "made by an earlier version: map again".
  - **Code written by a free model through Milliner arrives intact (J2-B5).** Three unattended attempts at "Search books" were refused. Nemotron's edits asked to replace `commands.add_parser(__list__, …)` for `commands.add_parser("list", …)`, and its new test file arrived as a single line with no quotation marks. A probe showed the cause: with the schema forced, the free routes lost every backslash escape inside JSON strings (`"def greet(name):n    return "`), while the same request with the schema as text came back intact. Answers that carry code (drafts, corrections and code-style checks) now send their schema to Milliner as text, like the examples checks. The prompt itself is unchanged, so a late answer still matches its saved request. Plans and other prose keep the forced schema. Milliner answers are parsed tolerantly (a JSON object after a sentence is accepted); every answer is still validated by Runesmith.
  - Answers that carry code now ask Milliner for valid JSON without pinning a schema (`json_mode`). A probe on the NVIDIA route whose forced schema lost every escape: in JSON mode its code came back intact, and so did Gemini's. In text mode alone, 2 of 3 Gemini answers had been invalid JSON.
  - **A build switch changed during a running job is no longer undone (J2-F19).** The owner turned "Apply checked drafts automatically" off while a build ran. When the job finished, its event redrew Goals & plan, and the switch silently went back on before the owner pressed Save. Unsaved build settings now survive those redraws, and the page says "Not saved yet: press Save build settings." Browser loop B20.06.
  - Pause during a build, seen live: the model call finished, its answer was kept as a draft, and the job stopped before the checks ("Stopped at your request"). After Resume, the next round checked the kept draft without a new call.
  - **Corrections, seen live (J2-B7, F17).** The owner asked the model to correct a refused answer. Its code now arrived intact and was admitted as a draft, and the project's own tests caught its mistake (`search.add_argument` without `search`); a normal outcome. Two faults showed around it:
    - The next scheduled round ended "Invalid author request key". The guard for revision lineages assumed every draft needing revision came from an ordinary attempt, and a correction's draft has no request key. The guard now applies only to drafts from ordinary attempts; the allowance still decides.
    - A second correction, now by Gemini Flash, found every route overloaded or at its free limit. It was recorded as "uncertain", which blocked any further correction of that answer until someone reconciled a call that never produced an answer. A call that no route accepted now spends nothing and blocks nothing, and it is reported plainly. Only a call whose outcome is truly unknown stays uncertain.
  - With every try used up, each scheduled round still queued a breakdown that only returned the proposal already waiting for the owner. That cost no model call, but it filled the history every five minutes. A waiting proposal is no longer proposed again. Those rounds end "done", so the Overview now also says "The tries for this step are used up, so building waits for you", and Work opens on Drafts (J2-F16).
  - **After three failed tries, the owner is shown the way on (J2-F13, F14).** The Overview said "The next round tries again" when it would not. After three failures in a row it now says "3 tries in a row did not work, so it waits for you: Work & proposals → Drafts shows what you can do". Work opens on Drafts after a failed build. There, "Alternate author available… One separately receipted call · unchanged source, scope…" now reads "Three tries at m7 did not work: one more is available…". A refused answer reads "An answer for readinglog/cli.py could not be used", with the reason and "The model can be asked to correct it, told exactly why it was refused (2 of 2 corrections left)".
  - **An edit off by its indentation is applied, not refused (J2-F15).** With the code now arriving intact, the alternate author's answer for "Search books" was still refused. It had two exact edits: the first matched, and the second wrote `        if args.command == "months":` with 8 spaces where the file has 4. When an edit's old text occurs nowhere exactly, the same lines at one uniform indentation shift are now accepted if they occur exactly once, and the new text is shifted to match. Tabs, mixed shifts, different text or more than one match are refused as before, and the checks still judge the result. The repair organ's own exact edits are unchanged. The retained answer now applies and compiles, and can be readmitted without a new call.
  - **Weaker Checkers get further (checker experiment, 2026-09-28, restarted with JSON mode).** Gemini Flash Lite, the weakest free model, now writes sound checks for m4 in 3 of 4 samples and for m5 in 4 of 4. Before, 1 answer in 17 was sound. What still went wrong is now caught:
    - its README checks ran `python -m readinglog count` for the `months` command, and failed every correct build. A run step whose command neither the milestone nor the program mentions is refused with the word named, which triggers the one revision. An example that runs an unknown command to show it is refused is allowed.
    - A whole answer was refused twice over its word for the exit code. `0`, "success", "failure", "non-zero" and other plain words are now understood; anything else is still refused.
  - **Examples-style checks work with Gemini (checker experiment, 2026-09-28).** After Gemini's daily reset, every examples-format request to it ended in 400 "Request contains an invalid argument". A probe found two causes. Gemini refuses `minItems`/`maxItems` in the schema as sent. And Milliner's default strict mode makes every property required (Groq and OpenAI demand this), so the model had to write out every optional field of every step, and even a one-example answer was truncated. The examples schema is now marked lenient: for Milliner it goes into the prompt as text instead of as a forced schema (Runesmith validates every answer itself), and the counts are enforced locally. Other schemas are sent as before. Seen live: Gemini Flash answered with 2 valid examples in 344 tokens.
  - **A late answer no longer stops "build while I'm away" (J2-F12).** The free model's answer for "Search books" took longer than the 300 s wait: NVIDIA's route truncated it three times, and the Kilo mirror answered 55 s after Runesmith stopped waiting. Runesmith rightly kept the request instead of sending it twice. But every later scheduled round then stopped at "Saved remote author request requires recovery before another build", until the owner came back and fetched it by hand. Fetching a saved answer is no new model call, so a round now fetches it itself and checks it through the normal gates. If the answer is not there yet, the round says so and waits. An author-only request still leaves it to the owner.
  - When the owner comes back, "Next in your plan" says if the last attempt did not work, and why: "The last attempt did not work (10 minutes ago): Exact edit refused for readinglog/cli.py… The next round tries again." (J2-F11). A proposal's summary gives the trial's counts, "1 of 2 fail on today's project", instead of "They fail" (J2-F10).
  - **A second chat-window request no longer goes unseen (J2-B4).** When Runesmith refused the Checker's answer, it wrote a revision request within the same second. The relay panel said "nothing waiting", with no badge, no "Needs you" and no toast, while the job waited for the owner. The Studio noticed changes in how many requests waited, and one request had replaced another at the same count. It now notices which requests wait, announces each new one, and the page toasts for it.
  - **The Checker is told the format's rules, and a long note no longer sinks an answer (J2-F7, F8).** Two answers for "Export library to CSV" were refused for rules the Checker was never told: "unchanged" may only name files the example creates, and each "not checked" note was limited to 200 characters. The rule for "unchanged" is now in the instructions, with how to check that a program leaves its data alone (create the data file with "files"). A long note is shortened for the owner instead of refusing the answer.
  - A job that fails is named in plain words, in the live log and in its toast: "Proposing acceptance checks did not finish: …", not "propose_acceptance failed: …" (J2-F9).
  - After a restart, the live log reads "The Studio closed during this job: Proposing acceptance checks. Its saved outcome is kept." It said "Recovered the last propose_acceptance marker" (J2-F5). The restart itself was handled well: nothing was repeated, and the owner was told what happened and what to do.
  - The Overview's banner for a waiting chat-window request now reads "A request is waiting for your chat window: copy it into the chat you use, then paste the reply back here. Runesmith cannot send it on its own, even on a schedule." It said "Manual transport needs a person even when scheduling is enabled" (J2-F4).
  - **The model roles speak to screen readers (J2-F2).** Thinking power's four role pickers were each named "+ add a model", and their buttons "Remove from this role". They now say, for example, "Add a model to the Planner" and "Remove gate-gemini from the Planner". Browser loop B2.06.
  - **Rounds that find nothing new no longer fill Activity (J2-F20).** With every try for m8 used up, a scheduled round every 5 minutes checked, found nothing it could do (no model call) and added a "done" row. Activity keeps 30 jobs, so within hours the real attempts had been pushed out. A scheduled round that ends exactly like the one before, having advanced nothing, now updates that row: "The same 14 times since 11:10." Failed tries, and everything the owner asks for, keep their own rows. Browser loop B5.09.
- **Journey J8 (every way to connect a model):** a fresh profile, with docs-conformant stand-ins on the real default ports (Ollama 11434, LM Studio 1234, llama.cpp 8080) and a key-checking OpenAI-compatible endpoint.
  - **A wrong key is said plainly and is not retried (J8-F3).** The test showed `http_401 {"message": "Invalid API Key", …}` as a transport error, which the router would retry with the same key. A 401 or 403 is now a configuration error, sent once: "The service refused the key (401). Check it, or paste it again, under Thinking power; a retry with the same key cannot help." The test uses a key file with a typo, then the corrected file, so a key read from the owner's own file is covered too.
  - **The Overview names a model server already running on this computer (J8-F1).** It used to say only "Add thinking power". Now, for example: "Ollama is already running on this computer, with 1 model (qwen2.5-coder:7b). It is free and nothing leaves this computer." "Use Ollama" opens the setup form prefilled with that server and model. A server without a model loaded is not offered.
  - Seen working:
    - Thinking power discovered all three local servers, each with "Use it";
    - the Ollama preset form, "List models" and "Save and test" ("answered with usable JSON in 0.02 s");
    - a model not yet downloaded names the `ollama pull` command;
    - a stopped server names the app to open.
- **Journey J10 (a terminal user, every CLI command):** a fresh folder, a fresh profile and a Python without pytest, then the chat relay by hand.
  - **No more tracebacks at the terminal.** `python -m runesmith` now answers any unexpected error with one plain line ("Runesmith stopped: …") and points to `runesmith doctor`; `RUNESMITH_DEBUG=1` shows the details. `generations verify` without an id crashed that way (J10-B1); it now verifies every generation.
  - **The demo no longer shows nothing (J10-B2).** In a fresh Python, `runesmith demo` found "0 repair opportunities" and "accepted 0 of 0 repairs" without saying why: its small project's tests need pytest. It now says so, how to install it, and that the Studio works without it.
  - Plain words:
    - `discover` says "the tests could not run", and why, instead of "error_without_failures" (J10-F1);
    - `status` before `init` says there is no home yet, instead of printing a default setup (J10-F2);
    - `init` says where to choose a model, including the keyless chat window (J10-F3);
    - a successful repair without `--apply` says it was not written (J10-F4).
  - Seen working: a repair through the chat relay at the terminal (`manual list`, `show`, `answer --file`). Strict success, in 2 calls.
- **Journey J9 (keyboard only, screen-reader names, phone size, light and dark):** a scripted audit of all 20 Studio pages and sub-tabs, then keyboard-only checks by hand.
  - **The command palette pressed the wrong button (J9-B1).** "Go to Notes" + Enter opened Goals & plan: closing the palette returned the focus to the button pressed before, and the same Enter then pressed it too. Enter and Escape in the palette are now consumed.
  - **Nothing scrolls sideways on a phone (J9-F2 to F5).** At 390 px, four pages were wider than the screen:
    - the Activity ledger, by 601 px: raw event data has no spaces to break at;
    - Settings → Folder & data (long folder paths) and Health (a long button label);
    - Thinking power, by 9 px.

    Ledger rows and monospace text (paths, digests, commands) now wrap anywhere; buttons never grow wider than their container and may wrap on small screens; cards may shrink inside columns. All 20 pages now fit at 390 px.
  - **Light theme status colours are readable (J9-F6).** Green, amber, red and link text measured 1.9-3.5:1 on the light background; they now reach 4.6-5.6:1 (WCAG AA). `tests/test_theme_contrast.py` computes every text and status colour of both themes from the stylesheet, so a later tweak cannot fall below 4.5:1.
  - **Every field has a name for screen readers (J9-F1):** the goal, allowed paths, workspace name and number fields.
  - Checked and fine:
    - no unnamed buttons or links, no positive tab orders, and a heading on every page;
    - "Skip to the page" is the first Tab stop and works;
    - the palette uses a labelled combobox and listbox;
    - comment mode by keyboard (C, Escape) works;
    - there is a visible focus ring everywhere.
- **Journey J1 (no key at all, an empty folder):**
  - **Try it found no commands in the plan (J1-G1).** The plan wrote its commands in single quotes mid-sentence ("A command 'python -m stockbook list' shows every item…"). Each match ran on to the end of the line, and its quotes then failed to parse, so the Overview offered nothing to try. A command inside matching quotes now ends at its closing quote, and suggestions keep their order in the text. Mira's plan now offers 8 commands, 3 of them marked as having placeholders.
  - **The Overview speaks to a first-time owner (J1-F1, F2).** After the introduction, an empty folder said "Runesmith has a saved map of your folder… review the modes and prerequisites". It now reads "An empty folder: a clean start for Mira's stock book. To plan and build, it needs thinking power…". A folder that hasn't been mapped still never claims a map.
  - **A check that already passes today is marked on its own (J1-G2).** Mira's checks for "Record a sale" included "an unknown item is refused". It already passed before the milestone was built, because the command did not exist yet and the parser refused it. The owner only saw "2 of 3 fail". Each such check now carries "Already passes on your project today, so it may not test what this milestone adds." It stays usable: after the build it tests the right thing.
  - **Skipping a chat-window request reads plainly (J1-F3, F4):** "Proposing acceptance checks: you skipped the request, so nothing changed." and "You skipped the chat-window request (acceptance)." It used to say "Propose_acceptance skipped…" and "…answered in 38.0 s".
  - **Notes in plain words (J1-F5):** "Open notes travel with the work they are about, newest first, as long as there is room. A draft's details show which notes went with it." It used to speak of a "bounded prompt budget" and a "Revision packet".
  - **Changing pages closes an open drawer (J1-F6).** Using the Back button or typing an address left a drawer covering the next page. A page that redraws itself keeps its drawers.
  - With a plan under way, the Overview now reads, for example: Next in your plan: "Record a sale" (1 of 5 done). Try what was built below, or continue in Goals & plan. It offers "Continue the plan", instead of "Review enabled modes and their prerequisites…".
  - **A fresh draft is checked at once when checking is on (J1-F7).** "Draft first files" left the draft unverified until the owner pressed Recheck. With checking on, the same recheck now follows in the same job: no model call, and nothing is applied. With checking off, nothing changes.
- **The measurement catalogue for self-improvement** (`docs/design/SELF_IMPROVEMENT_MEASUREMENTS.md`, `measurements_catalog.json`). Lars asked for "the precisely right measurement points": 424 points in 9 domains and 65 breakdown dimensions, built and adversarially verified by a 13-agent workflow.
  - Every point has an exact definition, its source (or the recording it still needs), its role (primary, guardrail or diagnostic), the levers it judges, a minimum sample, gaming risks and guards, and a privacy class.
  - A project scorecard (lead time, cost, full-pipeline success and throughput per milestone) judges any trial of any lever, with guardrails.
  - Finding: only 1 of 12 improvable levers (the repair organ) can be trialled today.
- **Acceptance checks from examples, so free models can write them (first slice of `docs/design/WEAK_MODEL_CHECKS.md`).** In a paced overnight run (`D:/oob/experiments/checkers/FINDINGS.md`), free models wrote their own check code for Reading Log m4–m6. Only 1 of 17 answered proposals was sound. **All 16 others rejected at least one correct build**: they required their own guess of a layout ("2026-01 1"), invented a message ("No books"), or read a line by its position.
  - The model now describes **examples as data**: files to prepare, commands a person would type, and what the result shows. Runesmith's own trusted template (`runesmith/app/acceptance_examples.py`) writes the checks file. The file never imports Runesmith and runs every example in its own fresh copy of the project.
  - **Matching that cannot trip on layout.** A text is matched whole and without regard to case, so "2" never matches inside "2026". A number is looked for on the line that names its subject, wherever the layout puts it. An order is the order of first appearance.
  - **Wording the milestone never states is loosened, or dropped.** A text the milestone doesn't contain and the example never typed in is cut down to what the example did type in, plus the number next to it: "2026-01 2" becomes "a line with 2026-01 shows 2", and "Added 'Tea'" becomes "Tea". The loosened check accepts every output the original did, so it can only stop rejecting correct builds. Words typed in together stay one phrase ("The Hobbit", not "The" and "Hobbit"). If nothing of a text was typed in ("No books"), it is dropped. Either way the owner is told.
  - **What is checked exactly is written by Runesmith** from the same data the template checks: every command, text and number. It is shown under each sentence and published to builders with it, so a sentence can no longer promise less than its check requires.
  - Beyond commands: a simulated **interrupted save** (every write in the folder stops halfway), prepared files (for example a damaged one) that must be left **exactly as they were**, the **examples in a README** (each mentioned command shown, and every example without placeholders runs), **links between Markdown pages**, and **calling a public Python function**.
  - Commands are limited to `python -m <module>`, `python <script>.py` and `node <script>`, with files inside the project only. An answer that breaks a rule is refused with the reason, and the model is told that reason once. A rule that wins nothing by refusing is applied quietly instead: an expectation on the interrupted run itself is dropped with a note, because what it prints proves nothing; a later step checks what the interruption left behind. gpt-oss put one there twice in a row.
  - Revisions and retries carry a smaller slice of the project's source, so a request that includes the first answer still fits Groq's free 8,000-tokens-a-minute window. The model's own answer is kept with each proposal.
  - Calibration: hand-written examples for m4–m6 score sound against two correct builds and six broken ones. So does a replay of Flash Lite's over-specified m4 checks, after loosening. Browser loop B20.05 covers the page.
  - The old way, where the model writes the unittest file itself, remains available (`style='code'`).
- **Someone who chose to just look is spoken to directly (journey J4).** In J4, a documents-only folder opened in "Just explore" (observe). "Draft a plan" was disabled with "Observe permission allows reading facts, not model planning", and its only button sent the person to Modes & measurements, where no switch named "observe" exists.
  - The Overview now says so in plain words: Runesmith maps and reports, asks no model and changes nothing. It offers "See what it found" (the map) and "Let it help", which switches to propose after a plain confirm (J4-F1, F5).
  - On Goals & plan, the same block offers "Let Runesmith plan and draft" in place. "Review planning controls" appears only when something else also blocks planning (J4-F5).
  - The blocker reads "You chose to just look (observe), so Runesmith does not ask a model to plan" (J4-F4).
  - On a case-insensitive disk, the map named a folder's index as `INDEX.md` when the file is `index.md`. It now shows the file's real name (J4-F3).
  - Browser loop B23 covers both screens and the switch.
  - After "Let it help", the Overview kept saying "You chose to just look" until the page was reloaded (J4-B1). Navigating to the page already shown now draws it again, so any change made on a page shows at once. The header now says "Just looking: maps and reports, asks no model" instead of asking for thinking power (J4-F6).
  - **Choices in Settings now show at once (J4-B2).** Choosing Observe or Propose (and the schedule and theme choices) saved correctly, but the highlight stayed on the old choice, because the page read the clicked button after waiting for the save, when the browser no longer knows it. Each choice and each "Never touch" folder chip now also tells screen readers whether it is pressed. Browser loop B24 fails on the old page. The same slip in a draft's Reject button only lost its busy indicator; it is fixed too.
  - **A folder of documents can now be checked and tended (J4-G1, G2).** When the persona asked for acceptance checks on "every recipe is reachable from the recipe index", two gaps showed.
    - The Checker saw not a single page. Code goes to models as source; documents never do unless the owner ticks them on Goals & plan, and the acceptance request did not include even the ticked ones. It now does, like the Planner's and authors' requests. The list is now called "Documents a model may read" and says that only ticked documents are sent to a model. A folder of only documents with nothing ticked gets a callout and a "Tick all, then save" button (browser loop B25).
    - The examples format could not express a check on documents: every example had to run a program. An example may now check files only, and a new check, "every Markdown page can be reached by following links from the front page", follows links from README.md or index.md with exact file names. Text a file must contain may be text the shared documents already hold, such as a page's real name.
  - **Documents can be drafted, created and verified (J4-G3).** Asked to "draft first files" for the handbook, the author was told never to replace a file it had not been shown, and no document is ever shown as source. So it could not edit `recipes/index.md` at all. The build snapshot also left documents out, so approved checks would have run on a copy without the handbook.
    - A document the owner ticks now shares its folder with the build pipeline. The folder's documents, including a new page a draft adds there, become local verification inputs. They are used only to check drafts on a copy; a model still sees only the ticked documents' text.
    - An exact edit to a ticked document is bound to the text the author was shown in full (not cut by the 12,000-character bound) and to that file's bytes, like an edit to a shown source file. The author's rules now say how to edit shared documents, and ask for unittest tests only when a change touches code.
    - A draft with no tests folder and no Python files (documents, plain web pages) has no project tests to run. The owner's acceptance checks decide, and without them its status is "unchecked", which never counts as verified. A Python project without tests still fails as before.
  - **Smaller frictions from the handbook's first milestones (J4-F7, F9, F14-F18):**
    - A map made by an earlier version is marked as such: the Living map offers "Made by an earlier version: map again". Maps carry a mapper revision, raised whenever mapping starts to record something new. It does not re-map by itself, because work starts only when the owner or the schedule asks.
    - Work & proposals opens on Drafts when a draft waits and there are no fixes. The expert panels (source timing and the author budget) move into one folded "For experts" section below the drafts (browser loop B26, which fails on the old page).
    - A draft that passed the owner's checks with no project tests to run reads "your checks passed", not "its tests and your checks passed".
    - The live log names a check outcome in plain words: "Draft “Seeded loaf in the recipe index”: your acceptance checks passed. Nothing was written." It used to show the raw status "acceptance_passed".
    - The checking switch and its dialog no longer speak only of Python unittest. They say that a draft is tried on a throwaway copy with the project's own tests, if it has any, and the owner's acceptance checks. The allowed-paths hint no longer suggests `pyproject.toml` to a folder of documents.
    - In a mapped folder without code, the switch for running the project's tests while mapping says there is nothing to run yet (J4-F2). It says so only from a map made by the current version: in journey J2, a map made by an earlier version had listed a package and its tests as plain folders, and the first release of this sentence believed it. The Overview's map figure now says "made by an earlier version: map again" in that case.
  - **Restart recovery in plain words (J4-F11).** After a restart interrupted a request waiting for the chat window, the Overview said "Saved work needs restart recovery review. Inspect retained outcomes…", and the recovery panel spoke of current-job markers, provider receipts and spent check allocations. The rules are unchanged; only the words are new.
    - The Overview now says that Runesmith was restarted in the middle of a job, that nothing was repeated or sent twice, and that nothing continues until you have had a look.
    - The panel opens with one plain summary, for example: "Runesmith was restarted while proposing acceptance checks, waiting for your chat window. Nothing was repeated or sent twice. It changes no file in your folder, so nothing there was touched. The request it waited on was set aside; ask again when you are ready." It then says the three steps to carry on.
    - The summary says nothing changed in the folder only for jobs that never write there. The worker now records which job was interrupted and how many chat-window requests were set aside.
  - Checks on files only are tried on today's copy even when running project code is off, because they run none of it (J4-F13). Their exact wording no longer mentions Python crash reports (J4-F12). After saving shared documents, the page redraws and says a model reads them from now on (J4-F10).
  - Checks run with Windows' `SYSTEMDRIVE`, `PROGRAMDATA` and `ALLUSERSPROFILE` set. Without them, Windows components created a literal `%SystemDrive%\ProgramData` folder inside each working copy, and copying it nested paths past Windows' length limit.
  - **No stray "null" on any page (J4-B3).** Goals & plan printed "null" under Build continuation when nothing had been built yet. A scan of every Studio script found the same possible slip in seven more places (Goals & plan, Work, Thinking power, the Living map); all are fixed. `tests/test_static_js_hygiene.py` now scans every script for both slips found in this journey (a part that may be null handed to `append`, and a click handler that reads its button after waiting), so neither can come back.
  - Settings now say exactly when files change: only when you approve a change, or when you allow automatic apply for checked builds. They used to say "It never writes to your files by itself".
  - **The map now finds pages nothing links to and notes still to do.** In a document collection, it lists Markdown pages that no other page in the folder links to (an index is the way in, so it never counts), plus TODO, FIXME and XXX notes outside code examples. Both appear on the Living map and in what the Planner is told. J4's handbook has one of each; before, only its broken links were visible.
- **A hostile environment, plain words (journey J7).**
  - **Deleting a folder's hidden `.runesmith` data no longer locks the folder out for good (J7-B1).** Runesmith used to refuse to open the folder ever again, with a Python traceback in the launcher window. That happened when someone cleaned hidden folders, restored a backup without them, or deleted the data to "reset".
    - A data folder that lived *inside* the project cannot be "unavailable" while the project is there, the way data on an unplugged drive can. So Runesmith starts fresh in the same place and says so.
    - Data kept elsewhere that has gone missing is still refused, as before.
  - The launcher never shows a traceback when it cannot open a folder; it says why in one sentence.
  - **A round measures the tests before asking for a model.** It used to stop at "no Worker model" before looking, so someone who had not set up a model was never told their tests fail. Measuring needs no model; only the fix does. Projects the repair organ cannot serve are now measured first, and only the organ's own projects need a Worker model.
  - An explicitly chosen port that is already in use is explained, with what to do, instead of a raw Windows error (J7-F1).
  - Also confirmed in J7, and passing:
    - a path with spaces, an ampersand, parentheses and non-ASCII letters (mapping, the introduction, Try it with non-ASCII output);
    - a second launch for the same folder points to the open Studio;
    - an old access key after a restart is refused with "open Runesmith from its launcher to get access".
- **Journey J3 passed**: an existing project with 5 failing tests was fixed by a free model and applied automatically in 5.5 s. The owner's own frozen tests decided, and the test files were untouched. Its smaller findings, fixed:
  - The introduction's use-type choice tells screen readers which one is selected.
  - Pressing Space (the intro's "skip ahead" key) once too often no longer types spaces into the name.
  - A Milliner gateway on this computer is no longer badged "local", because its models are remote.
  - The round's message names the right subject, and no longer ends with "nothing new" after saying that tests fail.
  - The Overview shows the Fix card as soon as a round finds failing tests, without a reload.
- **Fix the failing tests, for any layout (J3).** Runesmith's repair organ, the measured g0/C7 path, works on projects with a `src/` folder, and it stays unchanged. For any other layout, a round skipped the project and said nothing useful.
  - The Overview now offers **"Fix the failing tests"** whenever the map shows failing tests. It adds a milestone, "Make the failing tests pass", through the proven Build path.
  - Its acceptance is the project's **own tests, frozen as they are now**, embedded in one self-contained acceptance file. Rewriting the tests cannot pass it; only fixing the code can.
  - Automatic apply, only if the owner ticks it, may write only the code folders, never the tests.
  - Rounds say plainly when no tests were run, or when a project is skipped for its layout, and point to this path.
  - **Rounds measure what the repair organ cannot serve (J3-G2).** The organ's test discovery and the map's test probe use pytest, which a clean install does not have, so out of the box a round could not see failing tests at all.
    - A project without a `src/` folder, or any project where pytest is missing, is now measured with Python's own unittest, on a throwaway copy, if the owner allows running its tests.
    - The round says "N of M tests fail … use Fix the failing tests", and the Overview offers the fix from that measurement.
    - Without permission, the round says it has not run the tests and how to allow it, instead of implying all is well.
  - `runesmith/app/fix_tests.py`, `/api/fix-tests`, browser loop B22.
- **Small Python projects are recognised (J3-B1).** In journey J3 (an existing project with failing tests), the common flat layout (a package folder and `tests/`, a README, no packaging files) was mapped as a "document collection". So the introduction suggested "Tend my documents", the tests were never run, and a round reported **"nothing to repair"** while five tests failed.
  - A folder now counts as a Python project with any common marker (`requirements.txt`, `Pipfile` and `tox.ini` too), or with Python code at the top plus its tests.
- **Local model servers and free gateways work as their docs say (LS1).** The research (official docs, with sources and dates) is in `docs/journeys/local_servers_research_2026-09-27.json`. It is tested against faithful local stand-ins (`tests/local_standins.py`), because these servers cannot run on the development machine; the evidence level is recorded as "docs-conformant".
  - **Ollama now uses its native chat API**, so Runesmith can ask for a context window that fits each request. Its OpenAI-style address cannot raise the small default (4,096 tokens on modest machines), and an overflowing prompt silently loses its beginning, where the instructions are. Existing Ollama instruments are upgraded automatically.
    - Runesmith checks from Ollama's own count that the whole request was read.
    - "Model not found" tells the owner the exact `ollama pull` command.
    - An Ollama that is not running is named as such.
  - **Refusals no retry can change fail at once, in plain words**, instead of minutes of retries: a context overflow (in the wordings of llama.cpp, LM Studio, vLLM and LocalAI), a request too large for a free tier, an unknown model or address. A server that rejects Runesmith's JSON mode gets one retry without it.
  - **Presets:**
    - LM Studio uses the JSON-schema mode it accepts; it refuses the old default.
    - Groq requests are checked against its free 8,000-tokens-a-minute window before sending.
    - A shut-down Groq model and a disputed Gemini free model are no longer suggested.
    - LM Studio and llama.cpp setup hints say to load models with a large enough context.
- **Every triple of switch values, as a real scenario (Layer 1).** `tests/switch_sweep/sweep.py` runs a 45-row covering array (every triple of values of 10 factors) through real Studio processes: build, flip one switch through the API, build, restart, build.
  - The rules are checked from the receipts, phase by phase, with a liveness check so the harness cannot pass by seeing nothing.
  - First run: 45 of 45 rows hold every rule (`docs/journeys/LAYER1_SWEEP.md`). It runs unattended before each release, not in the quick suite.
- **Every switch combination is tested (Layer 0 of the coverage plan).** `tests/test_switch_matrix.py` asks every job kind whether it may start, under all 16,640 combinations of the owner's switches and the work modes, and compares the answer with an independent statement of the rules. That is 349,440 decisions in seconds, all matching.
  - Exhaustive tests also cover the rules that need real work: nothing is scheduled unless scheduled work is on; no project code runs with checks off or in observe mode; files change only with checks, automatic apply *and* passing owner checks; notes reach a model only when allowed.
  - **Found and fixed:** in observe mode ("read and report only") a model could still be asked, for example when proposing acceptance checks, because observe was enforced separately in some twenty places. `Workspace.router()`, which every Studio model call passes through, now refuses all calls in observe mode, in plain words.
- **Try what was built (G2).** The Overview now offers "Try what was built": the program's own commands, taken from its README and milestones. The owner picks or edits one and runs it, and sees its output and whether it finished normally.
  - It runs on a practice copy of the folder that lasts between runs, until the owner starts it again. The real folder is used only after a plain confirmation.
  - Only the project's own Python program runs: no shell and no other programs. Input is closed, output is capped, and each run has a time limit and a ledger entry. Browser loop B21 covers the card.
- **Plain words on milestone cards (F4).**
  - "Public acceptance expectations" is now "What builders are told", with the sentences only, no internal IDs. When approved checks already show their sentences, it folds into a "for experts" section.
  - The automatic-apply confirmation and the build description say what happens in everyday words ("Allow automatic apply").
- **Smaller requests for acceptance checks.** They leave room for a 3,000-token answer instead of 6,000, so they fit free per-minute windows such as Groq's 8,000 tokens a minute.
- **Honest receipts and a clear pause (F16–F18).**
  - Builds the schedule chains after an applied milestone are now recorded as started by the schedule, not the owner.
  - The top-bar Pause says what it does: it holds *all* work, scheduled rounds and the jobs you start. While paused, the status shows how many jobs are waiting ("Paused · 1 waiting until you resume"), so a job requested during a pause no longer waits silently.
  - A replaced proposal is marked "replaced" in its record, next to the kept file.
- **Plain words when a model does not answer (F15).** A timed-out free model used to show "every route failed - nvidia:moonshotai/kimi-k3 timeout". The owner now reads what happened and what to try: the model didn't answer in time, is busy or at its free limit, refused the key, or its answer hasn't arrived yet (and won't be requested twice). The gateway's own words follow, shortened.
- **No endless rechecking (F14).** With scheduled work on, every round used to check the same waiting draft again, writing new evidence each time, although nothing had changed. That is hundreds of identical checks a day at a 5-minute interval.
  - A waiting draft whose source, public expectations and owner acceptance are unchanged now keeps its last verdict.
  - If it passed only its own checks, the round says it is waiting for the owner and needs acceptance checks.
  - New or changed acceptance checks (for example, just approved) mean checking again, then applying if they pass. An explicit Recheck always checks.
- **Windows-safe saves (B1).** Saving a draft could fail with "Access is denied" when the Studio page read the file at that moment. `runesmith/atomic.py` retries briefly on a Windows sharing violation.
- **Keys in a local settings file.** An instrument whose key is read from a file at call time (`*_env_file` + `*_key`) now counts as ready, so an owner can keep keys in their own `.env` file rather than pasting them into the UI.
- **Friction fixes:**
  - "Recheck" explains and offers to turn checking on;
  - one name for the checking setting;
  - plain check words, and a calm write dialog when a draft's own tests passed;
  - the owner is asked whether a checked milestone is done;
  - "applied so far" counts drafts;
  - milestone cards no longer squeeze to one word per line;
  - the introduction ends on the Overview;
  - sidebar links without a keyboard shortcut no longer end in "(undefined)" (F13).

**First-run safety.**
- A new home starts with scheduled work, running the project's tests while mapping, and self-improvement all **off**. Finishing the introduction switches none of them on.
- The Overview's "How Runesmith may work here" panel asks for each choice in plain words, with the switch right there. "Getting set up" keeps a step open until the owner has chosen.
- Settings now says that measuring code executes the project's own code, on a throwaway copy that is not a security boundary.
- Homes onboarded by earlier versions keep their behaviour until their owner chooses. Choosing stores exactly the values the owner was shown.
- Tests: two backend tests, and browser loop B19.11. B19.01 and B19.09 were updated for the new defaults.

**Claims match the paper.**
- SR7 is described as 57 of 162 *attempts*: 54 unseen tasks, 3 rounds each. Its speed is "about half the time per successful repair". This applies across the README, the website, the Genesis introduction, the Settings evidence panel, the library card and the Atlas.
- C7's library card now says that its module-path step only recognises its two development repositories' package names, and that which steps carried the gain was not tested.
- `LOCAL_MODELS.md` now reports SR6-W's sealed null, and `RELEASE_CHECKLIST.md` records that B does not ship.

**Tests.** `test_sources_and_docs_use_lf_line_endings` walks project sources only. It prunes scratch, homes, fetched tools and the byte-exact field-training evidence before entering them. On the field-training tree it previously never finished, and it would have failed on the deliberately byte-exact logs.

## Unreleased: the Atlas (2026-09-25)

- **`site/atlas/`: the Runesmith Atlas**, one page that tells how Runesmith was built, failures included (`python scripts/build_atlas.py`).
  - An explorable map: the Core ringed by its kernel runes, a spiral path through the seven studies (the nulls included) that ends at C7 joining the Core, the family line g0 → B → C7, and the example folders. Tap anything for its story. There is a guided tour, and it pans and pinches on a phone.
  - Three reading levels: *Simply* (for children and elders, with an optional bigger text size), *Fully* (numbers, sections, receipts) and *For machines* (the raw record).
  - **Runes from real fingerprints.** Every rune is drawn from a SHA-256: a study's `RESULT.json`, a generation's organ digest, the paper itself. The rune forge draws one from any text or hash.
  - **For AI readers:** a letter written to them, schema.org JSON-LD, the whole story as JSON (`#runesmith-story`), the SVG's `<desc>`, and `llms.txt`. All of it is generated from `site/atlas/story.json`, the same file that draws the page, so there is no hidden version.
  - `--verify MILLINEROS_ROOT` re-hashes every receipt the story cites. At build time, 18 of 18 on disk matched.
  - Motion respects `prefers-reduced-motion`. Every node is keyboard-reachable, and the page has no horizontal scroll at phone width.

## Unreleased: Runesmith Studio (2026-09-25)

**The app** (`runesmith/app`, standard library only, no build step)
- `runesmith` with no arguments, or `runesmith up [folder]`, opens **Runesmith Studio**, a local web app for the folder.
  - It listens on 127.0.0.1 only.
  - Access is by a one-time link that becomes an HttpOnly, SameSite=Strict cookie.
  - It checks the Host header (against DNS rebinding) and requires a custom header for every change (against CSRF).
  - A strict Content-Security-Policy applies.
  - Launchers: `Runesmith.cmd`, `Runesmith.command` and `runesmith.sh`. Each checks for Python and opens the last folder or a new first project.
- **Genesis**, the opening sequence: seven scenes on the real folder (spark, forge, your world, itself, the guard, the evidence, any mind). It ends by naming what you will create, with an optional description. `/cinema` plays it looping on demo data, for sharing.
  - It is sized to the player, not the window (container units): the scene keeps the upper band and the words the lower one, so nothing overlaps on a full screen, a laptop or a small web player. On a phone-sized player it keeps the title line alone.
  - The cinema cycles three stories: a corner bakery, a freight company and a group of clinics. Their folders and file counts are those of the website's demo folders. A page can follow the stories (`genesis:story`) and pick one (`genesis:play`).
- **Living map** in four lenses:
  - Environment: objects, health bands, ladders, last-round status; exclude an object.
  - Self: the kernel ring, organs, capabilities, lineage.
  - Development: goal, plan, ladder and generation tracks.
  - Operations: the work loop, roles and calls, attention, trial, schedule.
- **Work & proposals.**
  - Apply judge-accepted fixes only when every file is unchanged since the fix was made. Line endings are preserved, a backup is kept, Undo is exact, and Reject records the reason as a note.
  - Model-written **drafts** are labelled unverified. Unsafe paths are refused, and an existing file is replaced only after a second confirmation.
- **Goals, brief, blueprints and plan.** The **Planner** role drafts milestones on tracks, then first files per milestone. When it has no model of its own it borrows the Improver's or the Worker's.
- **Thinking power.**
  - Presets for local servers (auto-discovered), key providers, a chat window, and Milliner.
  - Model listing and a one-call test.
  - Roles with ordered fallbacks.
  - Keys go in `<home>/secrets.json` and are never returned.
  - The manual chat relay works inside the app.
- **Comment on anything.** Press C or use the hover bubble on any card, map node, rung, fix, model or generation. Open notes reach the model that works on that thing, labelled as the owner's guidance. The Kaizen author also gets the owner's notes on Runesmith itself.
- **Self-improvement page:**
  - generations with friendly names;
  - the open trial and its looks;
  - the library with **C7**, which is adopted only through a trial;
  - campaigns and capabilities.
- **Activity:** the live log, the verifiable ledger timeline, and the jobs history.
- **Settings:** autonomy (observe or propose), the schedule, mapping, exclusions, notes, Kaizen, theme, health, the folder picker, a snapshot export, and About & evidence.
- A background worker runs jobs one at a time (map, round, plan, draft, health), on a schedule or on demand. Live events stream to the page.

**Kernel and maps**
- `envmap`:
  - maps empty folders, and plain folders as a `folder` kind with a small ladder;
  - maps the workspace's own loose files as an object;
  - lists excluded objects without reading them;
  - adds `workspace_facts`.
- `generations.kernel_digest` leaves out the Studio interface (`app/`), which never runs an organ. The self-map shows it as its own region.
- `KaizenRun`, `subject_step` and `run_loop` accept `owner_notes`. When empty, the author packet is byte-identical to before.
- `home.init_home`, `keystore`, `notes`.
- The shipped library holds C7 (`library/c7.zip`, with its evidence and caveat).

**Fixed in use loops** (see [docs/USE_LOOP_LOG.md](docs/USE_LOOP_LOG.md))
- Source files with a UTF-8 byte-order mark could not be repaired: organs got the BOM inside the text, and `ast.parse` rejects it. `read_src_files` now strips it. `encode_like` restores it, and the line endings, on every write-back, including `repair --apply`, which used to write in text mode.
- A quick map no longer erases test measurements. A code object keeps the measurement while its files are unchanged (a fingerprint of names, sizes and times), marked `measured_utc`.
- Plain-text documents (`.txt`, `.rst`, `.adoc`, `.org`) count as documents on the ladder. Links are still checked only in Markdown.
- `discover` explains a test run that could not start (`detail`, `triage`). The Studio shows it.
- A new **website** object kind (static HTML): link and image integrity, phone readiness, titles, and a ladder from pages to links resolving. The Planner reads these facts.
- For non-technical owners:
  - "Use a chat window (no key)" is one click;
  - the chat relay opens in a drawer from anywhere, with a toast when a request arrives, and has **Skip**;
  - writing a draft moves its milestone to in progress.
- A round skips unreachable Worker models and uses their fallbacks. It stops only when none answers, and its message names the fix.
- Choosing a generation by hand closes an open trial as `closed_by_owner`, recorded in the ledger. Before this, its arms went on comparing generations that no longer described what ran.
- **Link doctor**, with no model involved. Broken internal links in Markdown and HTML are pointed at the existing file with the same or closest name. The fixes come as an unverified draft of edits, each applied only onto the version it was made from.
- Link checks require the exact case of every path part (`envmap.exists_exactly`). A link that only works on a case-insensitive disk counts as broken, because it breaks on a web server.
- Projects nested inside plain folders (`services/billing`) are found as objects of their own. They carry their path as their name on the map and in proposals and attempts. A map node shows the last part as its title and the parent in its subtitle.
- The link doctor no longer guesses generic names such as `README.md` or `index.md`: such a target is used only when the surrounding path agrees.
- After a restart, a job that was running is recorded as interrupted. Chat-relay requests that nothing waits for any more are set aside, and the ledger records it.
- The map's test dot follows what happened since the last round. A fix applied afterwards shows as "fix applied, measure to confirm", and a later measurement replaces the round's verdict.
- The overview names what waits ("1 fix and 1 draft"), and a long workspace name wraps in the map's hub instead of being cut.
- Changing scene during the opening's finale removes the naming form, and the demo typing stops with it.
- The map's rings never let nodes overlap, from 0 to 200 objects. Up to 12 share one ring, grown as needed; more are shared out over rings wider apart than a node.
- The opening's drawing takes the shape of its band (`Genesis.frame()`), so wide scenes fill a full screen or a web player. It no longer prints "null" when embedded, keeps a phone-sized player free of corner buttons, and never shows a negative count.
- **Links and junctions are never followed** (loop 10). Python's walkers follow Windows junctions, so through them:
  - the map read folders outside the workspace;
  - the throwaway test copy copied outside files;
  - a model was shown outside code;
  - applying a fix could write outside the workspace.

  Now a single `is_link()` check guards every walker. A fix that resolves outside the workspace is refused (`outside`), and a linked top-level folder shows as "a link: not followed".
- **Large folders** (loop 10). The map walks with `os.scandir`, reading links, sizes and times from the directory listing: 29,000 files now map in 2.6 s instead of 18.6 s. A scan that stops at 20,000 files says so in the unknowns and shows "20000+ files". Blueprint candidates take 0.7 s instead of 2.6 s, and the link doctor 1.1 s instead of 4.9 s.
- **One Studio per folder, one listener per port** (loop 15). On Windows, `SO_REUSEADDR` let a second Studio, or any program, bind a port that was already listening, so a second folder's link reached the wrong Studio. The server now takes its port exclusively there.

  An OS-held `InstanceLock` allows one Studio per folder: a second launch opens the first instead of crashing on the half-made home. `generations.freeze` also accepts a generation another process froze a moment earlier.
- **The Studio on a phone** (loop 14). Every page used to scroll sideways, because the top bar never wrapped. Now, under 640 px:
  - the top bar takes two rows, and its buttons show icons, with their names kept for screen readers;
  - rows, the lens switcher, model cards and settings wrap;
  - the living map becomes a readable column under the workspace, as tall as it needs.
- **Skipping a chat-relay request no longer wipes the plan** (loop 13). The forced "skipped" answer was saved as an empty plan. A skip now ends a plan or draft job as `skipped` (`SkippedByOwner`) and saves nothing, and the Planner saves no answer that lacks its required parts. Attempts end in plain words (`ATTEMPT_WORDS`), and failed jobs and relay problems no longer show internal names.
- `runesmith proposals` respects what was decided in the Studio (loop 12). It shows the proposals still waiting and names the applied, undone or rejected ones, and `--write` saves patches only for waiting ones. It used to offer a fix already applied in the Studio as a patch that no longer applies.
- The server answers a broken or negative `Content-Length` with 400 (loop 11). A negative length used to hold a server thread until the client hung up. The Self and Development lenses of the map work by keyboard too (`keyboardNodes`).
- **Keyboard and screen readers** (loop 9):
  - map objects are focusable buttons with spoken summaries;
  - every clickable card, row or tile answers Tab, Enter and Space;
  - dialogs and drawers stack (`core.layer`): Tab stays inside the top one, Escape closes only it, and the focus returns to what opened it;
  - comment mode works by keyboard;
  - there is a skip link, and the focus moves to the new page's heading;
  - the window title names the page and the folder;
  - the palette is announced as a combobox with its options;
  - faint text meets WCAG AA in both themes.

## 0.1.0 — 2026-09-24 (research release)

**Kernel**
- Canonical identity and content digests (`canon`).
- A hash-chained, append-only ledger with tamper detection (`ledger`).
- Instrument router with transport-first failure classes and censoring. Adapters: Milliner and any OpenAI-compatible endpoint, plus a scripted instrument for tests and offline demos (`instruments`).
- A kernel-owned resource envelope and a per-opportunity cockpit with call, signal-run, request-size and wall-clock ceilings (`opportunity`).
- Code objects observed through their tests, with an optional executed-line trace (`objects/code`).
- Confined organ execution: an isolated interpreter, a secret-free environment and a PEP 578 audit hook, with RPC over stdio (`sandbox`, `organ_child`).
- Frozen generations with verification and compare-and-swap activation (`generations`).

**Organs**
- `repair` g0: a port of the Runesmith v1 repair policy.

**Kaizen**
- `diagnose`: value stream, failure families refined by matured references, and the declared target-ranking rule.
- `attention`: a standing self-improvement share that rises under struggle, with exact credit carry.
- `improve`: plan-do-study-act with prediction and falsifier, static check, confined smoke test, development replay, keep-best and a PDSA log.

**Maps, memory, loop and CLI**
- `SELF_MAP.json` and `ENVIRONMENT.json`, with the owner's band vocabulary (bad / minimal / optimal / world-class) and explicit unknowns.
- Append-only memory with BM25 recall and retirement.
- Object-target discovery from failing tests (`discover`).
- The Kaizen-always run loop (`loop`): an experience store, experience/validation splits, freeze without activation.
- CLI: `init`, `status`, `selfmap`, `envmap`, `discover`, `repair`, `run`, `diagnose`, `kaizen`, `generations`, `ledger`.

**Post-snapshot development (not part of the SR5 subject snapshot)**
- `envmap`: Node repositories get objectives, a build ladder and a next rung. Probing with npm is not implemented yet and stays unknown.
- `kaizen.improve`: the author packet now carries each attempt's diff and a diversity rule. This responds to SR5, where the author proposed one refinement in four consecutive iterations (4–7).
- `kaizen.improve`: optional `confirm_replays`. A candidate that beats the incumbent once must keep beating it on the average of further replays. This responds to SR5, where identical organs scored 10/32 and 16/32.

- `loop.subject_step`: a **noise-aware freeze bar**, learned from SR5. The incumbent is replayed twice on the validation split, and a candidate is frozen only if its gain over the incumbent's mean is at least `bar` and larger than the spread between the incumbent's two replays (`freeze_rule`). SR5 froze B on +6 (11 → 17) although identical organs had differed by 6 between replays, and B then failed on fresh work. Under the new rule, with replays of 10 and 16, B's +4 over their mean is within the noise and it is not frozen. The rule's numbers are recorded in the frozen generation's provenance.
- `kaizen.trial` and `loop`: online confirmation.
  - Seeded assignment of live opportunities between incumbent and candidate.
  - Sequential one-sided Fisher tests with Bonferroni-spent α.
  - Compare-and-swap activation or rejection, with no campaign while a trial is open.
  - New command: `runesmith trial`.
- `instruments`: tolerant JSON extraction for OpenAI-compatible (local) models, on by default and configurable with `tolerant_json`. The Milliner path stays strict.
- `docs/LOCAL_MODELS.md`: running Runesmith on a small local model, with measured expectations.
- `report`: a reproducible `REPORT.md` dashboard of one home. It shows the lineage, capability bands, per-generation yield and cycle time, open Kaizen targets, trials and recent opportunities. New command: `runesmith report`.
- `demo`: `runesmith demo` shows the whole loop in about a minute on a bundled three-slip workspace: map, discover, repair through the run loop, apply judge-accepted fixes, map again, report. It is offline by default, with a labelled scripted stand-in, and uses real models with `--live`. It refuses to overwrite a directory it did not create.
- `demo --kaizen`: watch self-improvement offline in a few minutes. On a bundled eight-slip workspace:
  1. The shipped organ g0 struggles, because a scripted weak model always breaks its navigation answer.
  2. Kaizen diagnoses `navigation_output_failure` from its own telemetry.
  3. The author's answer is replayed: the change gpt-oss-120b actually wrote in SR5 (generation `gen-a4415db24a53`, in `demo_data/`).
  4. It qualifies on held-out replays, is frozen, wins an online trial (0/4 vs 4/4, p = 0.014) and is activated by compare-and-swap.
  An end-to-end test asserts the whole chain, including that the activated organ is exactly SR5's B.
  The demo ends with an honest footnote: in SR5's preregistered confirmation on large repositories, this change was not shown to help. It rescued 0/26 navigation failures there.
- **Sandbox hardening after a security review.** Generation sharing made the organ sandbox matter against deliberately hostile code. Each gap below was first shown by a failing test, then closed:
  - `_winapi` calls (OpenProcess/TerminateProcess could kill other processes);
  - `gc` introspection (it could reach and widen the guard's own allow-list);
  - sub-interpreter imports (Python-level audit hooks do not apply inside them);
  - `ctypes` imports, crafted code objects, tracing and adding audit hooks, and `signal`;
  - stderr floods (capped at 16 MB) and endless protocol lines (the host now reads lines with a bound).
  The documentation now says plainly that PEP 578 audit hooks are not a hardened boundary: import generations only from people you trust, or run Runesmith in an OS-level sandbox.
- `oslimits`: **OS-level limits under the audit hook.** On Windows each organ process runs in a Job Object that allows no child processes and caps memory (2 GB by default). On POSIX, `setrlimit` caps the address space and the file size and forbids new processes. Tests show the job refuses a spawn (WinError 1816) and a 600 MB allocation under a 200 MB cap, and that a sandboxed organ cannot hoard memory. These limits hold even for code that bypasses the hook.
- **`ledger` fix: one chain, however many writers.** `append` used to chain onto the tail each `Ledger` object cached. Two objects on one file wrote duplicate sequence numbers and broken links, and the steward and the Kaizen demo each held such a second object. Every append now re-reads the file's real tail under a per-path lock and an OS file lock (`<ledger>.lock`). A test appends from 2 objects, 4 threads and 2 processes and verifies one intact chain of 143 records. The MillinerOS experiment ledgers were checked and are intact: their runners append from one thread per process, at distinct moments.
- `loop.ExperienceStore`: keeps each judge-accepted fix (`verified_fix.json.gz`), so later recall and replays can use what worked.
- `kaizen.affordances`: an affordance audit. It lists the kernel affordances an organ never uses, for g0: trace, recall, budget, a system message, a pre-edit signal run. They appear in the author packet (and in the diversity rule), in `SELF_MAP.json` under `improvement_options`, and in `REPORT.md`.
- The organ contract shown to Kaizen authors now documents `cockpit.recall`. It was granted before but undocumented, so no author could use it.
- `opportunity`: `recall` is now always granted and returns an empty list when the host has no memory, as in experiments and smoke tests. Before, the contract promised an affordance that some hosts refused, and an organ that followed the contract crashed there.
- All text files use LF line endings, and a test keeps it that way. Digests are over bytes, and the project is cross-platform.
- The contract now says how to read a trace. Import-time module lines are included, and lines inside function bodies show which functions the failing tests called. A kernel test pins the trace end to end: the defect's line is traced, an uncalled function body is not, and a never-imported module is absent.
- `local`: memory episodes record the judge's verdict and a bounded summary of the changed lines, so recall returns what was tried, not only where.
- `proposals`: `runesmith proposals [--write DIR]` turns judge-accepted fixes into unified-diff patches for human review. They are relative to the source as it was when the opportunity was served, and `git apply` refuses stale ones.
- `report` gains a **By model** table: calls, unusable-answer share, opportunities, strict repairs and output tokens per call for each model that answered. It is Runesmith's measured knowledge of its own instruments, and it carries across model changes. Call records now also name the answering instrument.
- **First Linux run** (Python 3.12.14 in a local container, no network, 1 CPU). The first full run gave 83 passed, 1 failed and 4 skipped. The skips are the three Windows-only Job Object and Windows API tests, plus the proposals test, because the image has no git.
  - The failure showed a platform difference, not a hole. On POSIX, `RLIMIT_FSIZE` equals the stderr cap, so a flooding organ's write fails with EFBIG exactly at the cap, and the organ dies before the host's poll saw the file grow *over* the cap. The flood was refused either way, but the verdict differed by OS (`OSError` vs `OutputFlood`).
  - `sandbox` now checks *at* the cap and classifies an organ that dies at the cap as `OutputFlood`, so the verdict is the same everywhere.
  - The kernel, OS-limit and proposal tests then passed on Linux (26 passed, 4 skipped) and on Windows (25 passed).
  - A second full Linux run passed: 84 passed, 4 skipped.
- **Fix: organ and replay sources are written as exact bytes.** On Windows, text-mode writes turned every LF into CRLF.
  - Affected: the Kaizen candidate organ (`improve.py`) and replayed task sources (`ExperienceStore.materialize`).
  - Effect: an organ frozen on Windows differed in bytes from its author's text, so it carried two digests. Behaviour was identical, because Python reads source with universal newlines.
  - Found by the new byte-level end-to-end test of the manual author. SR5's B is one such organ: file bytes `efef2b5c…`, author text `38d4be00…`. This is recorded in the SR5 and SR6 protocols.
  - A regression test pins `materialize`.
  - A flaky assertion in the loop test is fixed too: it did not allow the freeze rule's `within_noise` decision, which a timing tie can produce.
- `manual`: **a chat model as the author, relayed by hand.** Anyone with access to a strong model only through a chat window can author generations: a campaign needs at most a few author calls, and the result runs on free models.
  - An instrument of kind `manual` writes each request as a paste-ready file under `<home>/manual/` and waits for the reply.
  - `runesmith manual list / show / answer [--clipboard | --file] [--model]` hands the reply back. Replies are checked against the request's schema first, so a person can ask the model to fix its answer before it counts.
  - Replies may be written the way chat models write: prose around a ```` ```json ```` block, raw line breaks inside strings, and whole source files in named `@block:NAME` fenced blocks, which need no escaping. CRLF and UTF-16 are handled.
  - A request nobody answers is a transport failure, so the work is censored, never scored. Router retries wait on the same content-addressed request.
  - Receipts keep `answered_by` next to the instrument's label, and the Kaizen attempt record prefers it.
  - `demo --kaizen --manual-author` puts your chat model's change through the demo's qualification and trial. An end-to-end test relays SR5's author answer as a chat reply with CRLF endings and a named block, and asserts that the activated organ is byte-identical to it.
  - Guide: [docs/CHAT_AUTHOR.md](docs/CHAT_AUTHOR.md).
- **Safety:** `discover` and `envmap --probe` run an object's tests on a throwaway copy, with no bytecode writes, so Runesmith never writes into the objects it inspects. A test checks the repository byte for byte. `in_place=True` remains available to library callers.
- `attention`: **SPC drift detection**. A Bernoulli CUSUM watches strict-success yield against Runesmith's own baseline: the Wilson lower bound of its first 30 outcomes. It moves attention to blocked when yield drifts down although no single failure recurs, for example after a model or environment change. Its operating characteristics were simulated and are reproducible with `docs/simulations/drift_cusum.py`:
  - at most 3.7% false alarms within 200 stable opportunities;
  - a drop from 0.6 to 0.15 detected with a median delay of 22.
  The baseline resets when a new generation is activated.
- `attention` state now persists in `<home>/ATTENTION.json`, so struggle and drift are tracked across `run` invocations and steward rounds. Before, each run started fresh.
- `report` shows attention: its mode, the resulting Kaizen share, the blocking signal, the last change with its reason, and the drift chart's state. It shows why Runesmith is spending more or less time on itself.
- `discover`: **triage**. A failing test that only an environment change can fix (a missing third-party module, or a network dependency) is marked `environment`. The run loop and the steward skip it: no model call is spent, and it is recorded in the ledger. The rule is conservative. A missing module that exists in the object's own `src/` stays a repairable source defect, and anything unrecognised is left to the repair attempt. Discovery runs pytest with a wide terminal, so summary reasons are never truncated.
- `envmap`: a **document-collection template**. It reads only and executes nothing. It measures internal Markdown link integrity in bands, and it knows:
  - inline and reference links;
  - anchors and URL-encoding;
  - `file:line` code references;
  - that code fences are ignored.
  It also records a ladder (documents → index → links resolve) and the first broken links as examples. External links are not checked, and that is listed as an unknown. First real use: MillinerOS `docs/` has 78 documents and 499 internal links, none broken (band *optimal*), and its next rung is an index.
- `doctor`: `runesmith doctor [--offline]` checks Python, pytest, the home, the ledger chain, the active generation (its organ files and kernel), the instruments (key present, endpoint reachable) and disk space. It gives a fix for each problem and never prints a secret.
- `generations requalify`: after a Runesmith update, it re-freezes the active organs under the new kernel after a static check and a confined smoke test. The organs are byte-identical; the ledger records the requalification and the compare-and-swap activation.
- `share`: `generations export <id> --to FILE` and `generations import --from FILE`, so improvements compound across people. An import must pass these checks, in order:
  - archive members restricted to a manifest and `organs/**.py`, with no traversal and bounded sizes;
  - digest match;
  - static check;
  - a confined smoke test.
  It is then frozen inactive, bound to the receiver's kernel with provenance naming the source, and an online trial is opened. It is activated only by winning that trial. There is also a new `trial --open <id>`.
- `steward`: `runesmith steward WORKSPACE [--rounds N --interval S --exclude NAME]` is the top-level "lowered into an environment" mode. Each round maps the workspace, discovers failing tests across all Python objects on throwaway copies, and serves only new work. Opportunity identity includes a digest of the object's `src`, so unchanged work is never re-served. The seed stays fixed across rounds, so the Kaizen validation split never leaks. The steward interleaves Kaizen and trials, writes the report and proposals, never edits an object, and never probes excluded objects.
  Objects without a `src/` layout are skipped with a stated reason, because the shipped repair organ needs `src/`. Before this fix, one flat-layout repository crashed the round.

**Evidence**
- 29 tests.
- SR5-KAIZEN, preregistered in the MillinerOS research repository, tests the first full Kaizen loop on fresh tasks.
