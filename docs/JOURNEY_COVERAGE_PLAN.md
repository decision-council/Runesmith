# Out-of-box coverage plan: every option, every switch, live

Written 2026-09-27, after out-of-box journey R1 (`D:/oob/JOURNEY_LOG.md`). The owner asked for three things:
- live journey runs using all the options, improving each as it goes;
- the switches and modes exercised in any on/off configuration;
- the results turned into an easy, IKEA-style Out-of-Box Manual, including where to get free inference and how to run it.

## 1. Where we start

A read-only inventory of the product at `1c172ff` found **460 user-facing options, modes, paths and situations**. Five readers (models, setup, building, operating, evidence) did the inventory, and a completeness critic added 20 situations the readers missed. Every row, its current evidence and its planned coverage are in [journeys/COVERAGE.md](journeys/COVERAGE.md); the full rows are in `journeys/option_inventory_2026-09-27.json`.

| Evidence before this plan | Options |
|---|---|
| **Live**: a real or relayed model in a running Studio (use loops 1–15, journey R1, field training) | 204 |
| **Tests only**: unit tests, or the B1–B19 browser loops, which run on *simulated* server answers | 78 |
| **None found** | 178 |

The inventory's most important finding: the 150+ browser loops check UI wiring against a scripted server, not real model behaviour. Only three sources are live: the use loops, journey R1 (the only run with a chat relay plus free API models end to end), and the field training. Dashboards, most of Modes & measurements, the Notes page, most of Settings, and 9 of the CLI's ~14 verbs have no live run at all.

### Prerequisites (before the coverage journeys)

1. **R1 Phase B:** m4–m6 of the Reading Log built unattended, with checks the owner approved (in progress; the Checker role and F14 exist for it).
2. **G2:** "Try it" for what was built.
3. **F4:** plain wording on milestone and draft cards.
4. **Remove the temporary Milliner gate** from the journey home.
5. **A clean dry run** of the release candidate.

## 2. The switches

These are the choices an owner can turn on and off, in any combination:

| Group | Switch | Values |
|---|---|---|
| Policy | Scheduled work (`auto_work`) | on / off |
| | Run the project's tests while mapping (`probe_tests`) | on / off |
| | Self-improvement (`kaizen`) | on / off |
| | Give my notes to the model (`read_notes`) | on / off |
| | Check drafts by running their tests (`build_steps`) | on / off |
| | Apply checked drafts automatically (`build_apply`) | on / off |
| | Autonomy | observe / propose |
| | Home age | new (explicit choices) / onboarded by an older version (legacy defaults) |
| Modes | Map & Plan, Build, Troubleshoot, Optimize, Operations | each on / off |
| | Infer the folder's purpose | on / off |
| | Modes configured at all | yes / no (older behaviour) |
| Context | A model for each role (Worker, Improver, Planner, Checker) | none / chat window / API |
| | Approved acceptance checks for the milestone | yes / no |
| | Allowed paths cover the draft | yes / no |
| | Use type chosen in the introduction | improve / build / docs / explore / none |

That is 15 on/off choices, over 30,000 combinations, before the context is added. No number of live runs covers that by hand, so the coverage has three layers.

## 3. Layer 0: every combination, instantly

The code that decides what may happen is evaluated for **every** combination, with nothing sampled:
- which job may start (`guard_job`);
- what a scheduled round does (the worker's choice between a mode, a build and a round);
- which mode goes next (`choose_next`);
- whether a build may check, write or apply;
- whether notes enter a packet.

No work is done, so each combination takes milliseconds.

**The rules that must hold in every configuration:**

| # | Rule |
|---|---|
| I1 | Observe: no model call, no project code executed, no project file written. |
| I2 | Checks off: no project code executes, whether for checks or a trial run. |
| I3 | Test-running off: mapping never runs the project's tests. |
| I4 | Apply off, or no approved acceptance checks: Runesmith writes no project file on its own. |
| I5 | Scheduled work off: nothing starts without an owner click. |
| I6 | Self-improvement off: no change to Runesmith itself, no trial. |
| I7 | A disabled mode's work never runs, and the refusal says which mode and where to turn it on. |
| I8 | Notes off: no note text in any model packet. |
| I9 | Every refusal names the switch and where to change it, in plain words. |
| I10 | What the Overview says about each switch matches its effective value, legacy defaults included. |

**Deliverable:** `tests/test_switch_matrix.py`. It enumerates all combinations, runs in under two minutes, and joins the ordinary suite, so no future change can break a rule unnoticed.

## 4. Layer 1: every triple, as a real scenario

**Every combination of any three switch values** appears in at least one run: a strength-3 covering array over the switches above, a few hundred rows, generated deterministically.

Each row runs a real Studio process on a fresh profile and a fixture folder, with a scripted model:
1. First run with the row's choices.
2. A plan, a round and a build step.
3. Approving checks, if the row says so, then an apply attempt.
4. **One switch flipped mid-work**, chosen per row: owners change their minds.
5. A restart, then continuing.

The rules I1–I10 are then checked from the receipts: ledger events, project file hashes, the call log, and the checks that actually ran.

**Deliverable:** `tests/switch_sweep/`, run before each release (not in the quick suite). It produces a report with one line per row and the rules checked. It runs unattended in under an hour.

## 5. Layer 2: every pair, live, with real models

Live runs are slow, so they cover **every pair** of switch values at least once (strength 2), spread across the persona journeys below. Each journey also changes switches mid-work, so it passes through several configurations.

A script reads every journey's recorded setting changes (ledger `settings.changed` and mode events) and **proves** which pairs were exercised live. Any pair left over gets a short extra journey.

| Journey | Persona and folder | Models | Starts as | Flips mid-journey | Special situations | For the manual |
|---|---|---|---|---|---|---|
| **J0** | Release candidate reference run: clean export, empty folder | The manual's recommended free setup | New home, all off | Turns on checks, then apply | None: the "happy path" | Step-by-step pictures for chapter 1 |
| **J1** | Mira, shop owner, non-technical; empty folder, "a small tool" | Chat window only (no key) | Propose, all policies off | Checks on after the first draft; notes off and on | Walks away mid-relay; skips a request | "No key at all" recipe |
| **J2** | R1's Reading Log continued: builds while the owner is away | Free API model builds; the Checker is the chat window | Checks + apply + 5-minute schedule | Build mode off while a draft waits; pause and resume; apply off mid-build | Closes the Studio mid-build; provider at capacity; restart | "Build while I'm away" recipe |
| **J3** | Dev: an existing Python repo with failing tests | Free API model as Worker | Troubleshoot on, test-running on | Test-running off mid-map; Troubleshoot off during a repair | Hand-edits a file while a build runs; Undo after the file changed | "Fix my failing tests" recipe |
| **J4** | A documents-only folder (Markdown, no code) | None, then chat window | Observe | Observe → propose | A use type of docs; the purpose inferred | "Just look" recipe; observe rules live |
| **J5** | Operations: a folder with local reports (CSV) | Free API model | Operations + Optimize on, measurements | Operations off while measuring; Optimize on halfway | Dashboards; two folders; two browser tabs | "Keep an eye on my numbers" recipe |
| **J6** | Self-improvement on the user's own work | Free API model as Improver | Self-improvement on | Self-improvement off during a trial | C7 trial against g0; rollback | "Let it improve itself" (advanced) |
| **J7** | Hostile environment | Chat window | Mixed | Folder switch in one tab while another is open | A path with spaces and non-ASCII; a read-only subfolder; a huge folder and junctions; port busy; a second Studio; the "locked" screen; the server killed mid-job; sleep and wake | The troubleshooting chapter |
| **J8** | Every way to connect a model | Each preset | New home | A role reordered; a bad key; a provider down | Catalog listing errors; key read from a local file | The "Free thinking power" chapter |
| **J9** | Keyboard only, screen reader names, phone, light and dark | Chat window | Any | Theme | Command palette, comment mode | Accessibility notes |
| **J10** | A terminal user | Scripted and free API | CLI only | CLI only | Every CLI verb: run, kaizen, discover, selfmap, envmap, trial, repair, report, demo, generations, manual | Appendix: the command line |

Order, by release risk: J2 (running now), J1, J4, J3, J7, J5, J8, J9, J6, J10, and J0 last, on the release candidate.

## 6. The protocol for every live journey (R1's, kept)

- **Setup:** a clean `git archive` export of the release under test, a fresh venv without extras, and a fake profile (`USERPROFILE`, `APPDATA` and so on) on its own port. The Studio opens through a one-time redirect, so the access key never appears anywhere. Nobody types a key: keys are read from a file the owner controls.
- **Logging:** `D:/oob/journeys/Jn/LOG.md`, stamped from the clock. It records:
  - every owner action;
  - every **rescue**: anything the persona could not have done alone;
  - friction (F), gaps (G) and bugs (B), each with an ID;
  - a screenshot for every step, because they become the manual's pictures.
- **Fix loop:** each finding goes through fix → test → full suite and browser loops → commit and push → re-release into the same journey. Each re-release also exercises the upgrade path.
- **Exit:** the journey passes with **0 rescues** on the final release. Every rule I1–I10 holds in its receipts.

## 7. Thinking power for the live runs (free only)

| Route | Status here | How it's covered |
|---|---|---|
| Chat window (copy and paste) | Available: the relayed model | J1, J2 (Checker), J4, J7, J9 |
| Free API models through the temporary Milliner gate (Gemini Flash Lite; Kimi K3 via NVIDIA) | Available, free only. Kimi times out often | J2, J3, J5, J6, J10; the gate is removed before J0 |
| Free keyed providers direct (Google AI Studio, Groq, OpenRouter free models, Mistral …) | Needs keys the owner creates; nobody types them here | J8, once the owner puts keys in a local `.env` file (the Studio reads them at call time). Until then, the wiring is checked against a local OpenAI-compatible stand-in |
| Local models (Ollama, LM Studio, llama.cpp) | This machine is too weak | Wiring checked against the stand-in, plus the documented setup. A community run is marked as wanted |
| macOS and Linux | Not on this machine | Docker Desktop, only if the owner allows starting it; otherwise a community run |

## 8. What becomes the Out-of-Box Manual

- **"What you need" and numbered picture steps**, one action per step, from J0 and J1 screenshots.
- **A card for every switch and mode:** what it does, when to turn it on or off, what is safe. It is taken from the inventory, and the Layer 0 rules guarantee what each card says.
- **Recipes:** ready-made configurations that were proven live (J1–J6): "No key at all", "Build while I'm away", "Fix my failing tests", "Just look", "Keep an eye on my numbers", "Let it improve itself".
- **Free thinking power:** where to get free inference, how to start it, and how to connect it. Each provider is checked against its own current pages when the chapter is written, and the date is printed.
- **Troubleshooting:** "if you see this, do that", from every friction, gap and J7 situation.
- **A glossary** in plain words.

## 9. Order of work

1. **Prerequisites** (section 1), finishing R1.
2. **Layer 0:** the switch matrix test, then fixes.
3. **Layer 1:** the scenario sweep harness, a first full run, then fixes.
4. **Live journeys J1–J10**, in the order above, each through the fix loop.
5. **The pairs report:** any pair not yet live gets a short extra run.
6. **J0** on the release candidate, with the gate removed.
7. **Assemble the manual** from the recorded material.

Each step is logged. `COVERAGE.md` is regenerated as options move from "none" to "live".
