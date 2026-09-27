# Option coverage matrix (generated 2026-09-27)

Every user-facing option, mode, path and situation found in the product by a read-only inventory. Five readers (models, setup, building, operating, evidence) plus a completeness critic worked over the code at commit `1c172ff`.
- **Evidence** is what exercised the option before the coverage plan: **live** means a real or relayed model in a running Studio (use loops, journey R1, field training); **tests only** means unit tests or the fixture browser loops (B1–B19, simulated server answers); **none** means nothing found.
- **Planned in** refers to [JOURNEY_COVERAGE_PLAN.md](../JOURNEY_COVERAGE_PLAN.md): L0 is the all-combinations decision sweep, L1 the three-way scenario sweep, J0–J10 the live journeys.
- The full rows (file:line, values, prerequisites, risks) are in `option_inventory_2026-09-27.json`.

**460 options:** 204 with live evidence, 78 tests only, 178 none.

| # | Surface | Option | Evidence | A live run needs | Planned in |
|---|---|---|---|---|---|
| 1 | Instrument kind — preset | Ollama (This computer) | live | local model server | J8 · L0/L1 (no-model, roles) |
| 2 | Instrument kind — preset | LM Studio (This computer) | none | local model server | J8 · L0/L1 (no-model, roles) |
| 3 | Instrument kind — preset | llama.cpp server (This computer) | none | local model server | J8 · L0/L1 (no-model, roles) |
| 4 | Instrument kind — preset | OpenRouter (With a key) | live | API key | J8 · L0/L1 (no-model, roles) |
| 5 | Instrument kind — preset | Groq (With a key) | none | API key | J8 · L0/L1 (no-model, roles) |
| 6 | Instrument kind — preset | Google Gemini (With a key) | live | API key | J8 · L0/L1 (no-model, roles) |
| 7 | Instrument kind — preset | Mistral (With a key) | none | API key | J8 · L0/L1 (no-model, roles) |
| 8 | Instrument kind — preset | DeepSeek (With a key) | none | API key | J8 · L0/L1 (no-model, roles) |
| 9 | Instrument kind — preset | OpenAI (With a key) | none | API key | J8 · L0/L1 (no-model, roles) |
| 10 | Instrument kind — preset | Anthropic OpenAI-compatible (With a key) | none | API key | J8 · L0/L1 (no-model, roles) |
| 11 | Instrument kind — preset | Together AI (With a key) | none | API key | J8 · L0/L1 (no-model, roles) |
| 12 | Instrument kind — preset | Custom / Any OpenAI-compatible endpoint (Advanced) | none | local model server or API key (either) | J8 · L0/L1 (no-model, roles) |
| 13 | Instrument kind — preset | Milliner router (Advanced) | live | local model server (Milliner gateway) + API  | J8 · L0/L1 (no-model, roles) |
| 14 | Instrument kind — preset | Manual / chat window relay (No key needed) | live | chat relay | J8 · L0/L1 (no-model, roles) |
| 15 | Onboarding shortcut | 'Three ways to give Runesmith a mind' cards (shown only with zero instruments) | live | none (UI-only observation) | J8 · L0/L1 (no-model, roles) |
| 16 | Add-wizard field | Instrument name | none | none | J8 · L0/L1 (no-model, roles) |
| 17 | Add-wizard field | Model ID field + 'List models' catalog button | live | local model server or API key (for a live ca | J8 · L0/L1 (no-model, roles) |
| 18 | Add-wizard field | Catalog provider filter (Milliner only) | tests only | API key (Milliner token) | J8 · L0/L1 (no-model, roles) |
| 19 | Add-wizard field | Address / base_url field | none | none | J8 · L0/L1 (no-model, roles) |
| 20 | Add-wizard field | Milliner fallback models textarea | live | API key (Milliner token) | J8 · L0/L1 (no-model, roles) |
| 21 | Add-wizard field | API key / Agent token field + show/hide toggle | live | API key | J8 · L0/L1 (no-model, roles) |
| 22 | Add-wizard field | Roles checkboxes (repair/kaizen/plan) with smart defaults | none | none | J8 · L0/L1 (no-model, roles) |
| 23 | Add-wizard action | Save button ('Save and test' vs 'Save chat instrument') | none | API key or local model server | J8 · L0/L1 (no-model, roles) |
| 24 | Add-wizard callout | First-time setup hint (p.setup, Ollama only) | none | none | J8 · L0/L1 (no-model, roles) |
| 25 | Local discovery | 'On this computer' auto-scan ('Look again') | tests only | local model server (for the positive-result  | J8 · L0/L1 (no-model, roles) |
| 26 | Local discovery | Per-found-server 'Use it' quick-add | none | local model server | J8 · L0/L1 (no-model, roles) |
| 27 | Instrument row action | Test (per instrument) | none | API key or local model server | J8 · L0/L1 (no-model, roles) |
| 28 | Instrument row action | Recorded availability (Milliner only) | live | local model server (Milliner gateway, for re | J8 · L0/L1 (no-model, roles) |
| 29 | Instrument row action | Route editor (Milliner only) | live | local model server (Milliner gateway) | J8 · L0/L1 (no-model, roles) |
| 30 | Instrument row action | 'List free-catalog models' inside the route editor | none | API key (Milliner token) | J8 · L0/L1 (no-model, roles) |
| 31 | Instrument row action | Remove instrument | none | none | J8 · L0/L1 (no-model, roles) |
| 32 | Instrument row display | Status badges (local / incomplete / key saved / key missing) | none | none | J8 · L0/L1 (no-model, roles) |
| 33 | Instrument row display | Call-stats / spend line | none | none | J8 · L0/L1 (no-model, roles) |
| 34 | Roles ('Who does what') | Role lane per role (repair/kaizen/plan) | live | none | J8 · L0/L1 (no-model, roles) |
| 35 | Roles ('Who does what') | Fallback tag drag handle (draggable='true') | none | none | J8 · L0/L1 (no-model, roles) |
| 36 | Roles ('Who does what') | 'Move up' button per fallback | none | none | J8 · L0/L1 (no-model, roles) |
| 37 | Roles ('Who does what') | '+ add a model' select per role | none | none | J8 · L0/L1 (no-model, roles) |
| 38 | Roles ('Who does what') | Planner auto-borrow ('uses <role>') | live | none | J8 · L0/L1 (no-model, roles) |
| 39 | Keys | Saved-keys panel (names + timestamp only) | tests only | none | J8 · L0/L1 (no-model, roles) |
| 40 | Keys | Key storage — typed key (UI path) | tests only | API key | J8 · L0/L1 (no-model, roles) |
| 41 | Keys | Key storage — environment variable (api_key_env / token_env) | tests only | scripted/offline (hand-edit config; no live  | J8 · L0/L1 (no-model, roles) |
| 42 | Keys | Key storage — read from a local file (*_env_file + *_key) | live | scripted/offline (hand-edit config; no live  | J8 · L0/L1 (no-model, roles) |
| 43 | Usage & budget | 'Usage & cost coverage' modal (header button) | live | local model server (Milliner gateway, to acc | J8 · L0/L1 (no-model, roles) |
| 44 | Usage & budget | No-cost-reporting state for non-Milliner instruments | none | API key | J8 · L0/L1 (no-model, roles) |
| 45 | No-model state | Status pill: 'Mapping only: add thinking power to let it work' | live | none | J8 · L0/L1 (no-model, roles) |
| 46 | No-model state | Home CTA 'Add thinking power' + onboarding checklist item | live | none | J8 · L0/L1 (no-model, roles) |
| 47 | No-model state | Goals & plan blocked callout | live | none | J8 · L0/L1 (no-model, roles) |
| 48 | No-model state | Command-palette shortcut 'Add thinking power (a model)' | none | none | J8 · L0/L1 (no-model, roles) |
| 49 | Chat relay | Relay panel auto-surfacing rules | live | chat relay | J1 · J2 (Checker) |
| 50 | Chat relay | Copy request / Paste reply + model-label fields | tests only | chat relay | J1 · J2 (Checker) |
| 51 | Chat relay | Send the answer (format precheck) | live | chat relay | J1 · J2 (Checker) |
| 52 | Chat relay | 'Send unchanged anyway' (force bypass) | live | chat relay | J1 · J2 (Checker) |
| 53 | Chat relay | Skip (decline a waiting request) | tests only | chat relay | J1 · J2 (Checker) |
| 54 | Chat relay | Global relay drawer (from the top-bar 'Needs you' pill / toast) | live | chat relay | J1 · J2 (Checker) |
| 55 | Author guidance (static help) | 'Choosing authors and workers' + 'What is strong enough?' details | none | none | J8 · L0/L1 (no-model, roles) |
| 56 | Router behavior (backend, affects every journey) | Transport retry with backoff, then TransportCensored | live | API key or local model server | J8 · L0/L1 (no-model, roles) |
| 57 | Router behavior (backend, affects every journey) | Skip-unreachable-model + fallback take-over | live | local model server (a deliberately-off one)  | J8 · L0/L1 (no-model, roles) |
| 58 | Config-only, no Studio UI | json_mode (json_object / json_schema / none) | none | scripted/offline (hand-edit config) | J8 · L0/L1 (no-model, roles) |
| 59 | Config-only, no Studio UI | tolerant_json / timeout_s / caller_tag / budget_tag | live | scripted/offline (hand-edit config) | J8 · L0/L1 (no-model, roles) |
| 60 | Launcher | Runesmith.cmd, no argument | live | none | J0 · J7 |
| 61 | Launcher | Runesmith.cmd with a folder dropped onto it | live | none | J0 · J7 |
| 62 | Launcher | Runesmith.cmd Python-not-found branch | none | none (needs a machine/profile without Python | J0 · J7 |
| 63 | Launcher | Runesmith.cmd old-Python branch | none | none | J0 · J7 |
| 64 | Launcher | Runesmith.command (macOS) | none | macOS/Linux | J0 · J7 |
| 65 | Launcher | runesmith.sh (Linux) | none | macOS/Linux | J0 · J7 |
| 66 | CLI | python -m runesmith (bare, no subcommand) | tests only | none | J10 |
| 67 | CLI | runesmith up [folder] | live | none | J10 |
| 68 | CLI | runesmith up --last | live | none | J10 |
| 69 | CLI | runesmith up --port N | none | none | J10 |
| 70 | CLI | runesmith up --no-browser | none | none | J10 |
| 71 | CLI | runesmith --home PATH (global, all subcommands) | live | none | J10 |
| 72 | Genesis | Scene sequence (spark/forge/world/itself/guard/evidence/minds) | live | none | J1 · J0 · L0/L1 (policy) |
| 73 | Genesis | Finale: name field | live | none | J1 · J0 · L0/L1 (policy) |
| 74 | Genesis | Finale: description textarea | live | none | J1 · J0 · L0/L1 (policy) |
| 75 | Genesis | Finale: use_type choice | tests only | none | J1 · J0 · L0/L1 (policy) |
| 76 | Genesis | Finale: Skip for now | none | none | J1 · J0 · L0/L1 (policy) |
| 77 | Genesis | Finale: Forge it (submit) | tests only | none | J1 · J0 · L0/L1 (policy) |
| 78 | Genesis | Keyboard: Space/→ next, ← back | none | none | J1 · J0 · L0/L1 (policy) |
| 79 | Genesis | Keyboard: Esc = skip to finale (non-cinema only) | none | none | J1 · J0 · L0/L1 (policy) |
| 80 | Genesis | Keyboard: F = fullscreen (cinema only) | none | none | J1 · J0 · L0/L1 (policy) |
| 81 | Genesis | 'Skip intro' top button (non-cinema) | live | none | J1 · J0 · L0/L1 (policy) |
| 82 | Genesis | Cinema mode /cinema | tests only | none | J1 · J0 · L0/L1 (policy) |
| 83 | Genesis | Cinema: Restart button | none | none | J1 · J0 · L0/L1 (policy) |
| 84 | Genesis | Cinema: Full screen button | none | none | J1 · J0 · L0/L1 (policy) |
| 85 | Genesis | Replay from Settings -> Behaviour -> Introduction -> Replay | none | none | J1 · J0 · L0/L1 (policy) |
| 86 | Genesis | Cinema button in Settings (Behaviour) | none | none | J1 · J0 · L0/L1 (policy) |
| 87 | Folder kind | Empty folder | live | none | J7 · J3 · J4 |
| 88 | Folder kind | python_repository (pyproject.toml/setup.py/setup.cfg) | live | none | J7 · J3 · J4 |
| 89 | Folder kind | node_repository (package.json) | live | none | J7 · J3 · J4 |
| 90 | Folder kind | website (*.html/*.htm present) | live | none | J7 · J3 · J4 |
| 91 | Folder kind | document_collection (*.md/*.rst/*.txt/.markdown/.adoc/.org) | live | none | J7 · J3 · J4 |
| 92 | Folder kind | Unknown/plain folder (no marker) | tests only | none | J7 · J3 · J4 |
| 93 | Folder kind | Nested multi-object workspace | live | none | J7 · J3 · J4 |
| 94 | Folder kind | Owner-excluded object | tests only | none | J7 · J3 · J4 |
| 95 | Folder kind | Link/junction at top level | live | none | J7 · J3 · J4 |
| 96 | Folder kind | Huge folder / monorepo (>=20,000 files) | live | none | J7 · J3 · J4 |
| 97 | First-run policy | autonomy: observe / propose | tests only | none | J1 · J0 · L0/L1 (policy) |
| 98 | First-run policy | auto_work + interval_minutes | tests only | none | J1 · J0 · L0/L1 (policy) |
| 99 | First-run policy | probe_tests | live | none | J1 · J0 · L0/L1 (policy) |
| 100 | First-run policy | max_objects | none | none | J1 · J0 · L0/L1 (policy) |
| 101 | First-run policy | exclude (never-touch list) | tests only | none | J1 · J0 · L0/L1 (policy) |
| 102 | First-run policy | kaizen (self-improvement) + min_experience + kaizen_every | live | none | J1 · J0 · L0/L1 (policy) |
| 103 | First-run policy | 'Keep these choices' button | tests only | none | J1 · J0 · L0/L1 (policy) |
| 104 | First-run policy | Legacy-onboarded home behaviour | tests only | none | J1 · J0 · L0/L1 (policy) |
| 105 | First-run policy | read_notes (give notes to model) | live | none | J1 · J0 · L0/L1 (policy) |
| 106 | Settings page | Behaviour tab: workspace name | none | none | L0/L1 · J9 |
| 107 | Settings page | Behaviour tab: theme (Auto/Light/Dark) | none | none | L0/L1 · J9 |
| 108 | Settings page | Health tab: local checks + network check | none | none / API key for a real network check | L0/L1 · J9 |
| 109 | Settings page | Data tab: Work in another folder | tests only | none | L0/L1 · J9 |
| 110 | Settings page | Data tab: Open in file manager (workspace/home) | none | none | L0/L1 · J9 |
| 111 | Settings page | Data tab: Export a snapshot | none | none | L0/L1 · J9 |
| 112 | Settings page | Data tab: Quit Runesmith Studio | none | none | L0/L1 · J9 |
| 113 | Settings page | About tab | none | none | L0/L1 · J9 |
| 114 | Settings page | build_steps / build_apply / build_paths | live | none | L0/L1 · J9 |
| 115 | Switch folders | Recent-folder chips | tests only | none | J7 |
| 116 | Switch folders | Typed path + Go (browse tree) | tests only | none | J7 |
| 117 | Switch folders | Optional separate Runesmith home | tests only | none | J7 |
| 118 | Switch folders | 'New folder here...' (create+open) | tests only | none | J7 |
| 119 | Switch folders | 'Work here' (open existing) | tests only | none | J7 |
| 120 | Switch folders | Switch guard (blockers/warnings) | tests only | none | J7 |
| 121 | Switch folders | Several Studios, several folders concurrently | live | none | J7 |
| 122 | Switch folders | One-owner-per-Studio limit (several people, one Studio) | none | none | J7 |
| 123 | Restart | Kill + relaunch preserves state | live | none | J7 |
| 124 | Restart | Interrupted-job restart recovery banner | tests only | none | J7 |
| 125 | Restart | Second launch on an already-open folder | live | none | J7 |
| 126 | Upgrade | Automatic organ requalification on kernel change | live | none | J7 |
| 127 | Upgrade | runesmith generations requalify (manual CLI) | tests only | none | J7 |
| 128 | One-Studio-per-folder lock | InstanceLock (OS file lock on the home) | live | none | J7 |
| 129 | One-Studio-per-folder lock | RootLease (overlapping root/home exclusion) | tests only | none | J7 |
| 130 | One-Studio-per-folder lock | Windows port exclusivity | live | none / Windows | J7 |
| 131 | Theme | Settings 3-way Auto/Light/Dark | none | none | J9 |
| 132 | Theme | Topbar cycle button (light<->dark only) | none | none | J9 |
| 133 | Theme | System prefers-color-scheme auto-follow | none | none | J9 |
| 134 | Theme | prefers-reduced-motion | none | none | J9 |
| 135 | Phone layout | <=860px sidebar collapse to icon rail | live | none | J9 |
| 136 | Phone layout | <=640px topbar wraps, icon-only buttons | live | none | J9 |
| 137 | Phone layout | Living-map column layout <560px width | live | none | J9 |
| 138 | Phone layout | Manual sidebar Collapse toggle | none | none | J9 |
| 139 | Keyboard/SR | Global shortcuts (Ctrl K, C, R, 1-9, ?, Esc) | live | none | J9 |
| 140 | Keyboard/SR | Skip-to-content link | live | none | J9 |
| 141 | Keyboard/SR | Focus-follows-navigation on route change | live | none | J9 |
| 142 | Keyboard/SR | Dialog/drawer focus trap + stacked Escape | live | none | J9 |
| 143 | Keyboard/SR | Any clickable element auto-keyboard-operable | live | none | J9 |
| 144 | Keyboard/SR | Window title reflects page + workspace | live | none | J9 |
| 145 | Keyboard/SR | '?' Keyboard shortcuts help modal | live | none | J9 |
| 146 | Comment mode | Toggle (C key or topbar button) | live | none | J9 |
| 147 | Comment mode | Click-anywhere-commentable targets | live | none | J9 |
| 148 | Comment mode | Notes drawer: write/reply/resolve | live | none | J9 |
| 149 | Comment mode | Delivery routing by target type (READS map) | tests only | none | J9 |
| 150 | Command palette | Open (Ctrl+K) / filter / arrow-nav / Enter / Esc | live | none | J9 |
| 151 | Command palette | Each of the 16 built-in commands | none | none | J9 |
| 152 | Goals & plan · Goals list | Add a goal | none | none | J1 · J2 |
| 153 | Goals & plan · Goals list | Mark a goal done / active (toggle) | none | none | J1 · J2 |
| 154 | Goals & plan · Goals list | Edit a goal's text | none | none | J1 · J2 |
| 155 | Goals & plan · Goals list | Remove a goal | none | none | J1 · J2 |
| 156 | Goals & plan · Goals list | Comment on a goal | none | none | J1 · J2 |
| 157 | Goals & plan · Brief & blueprints | Write/save the brief | live | none | J1 · J2 |
| 158 | Goals & plan · Brief & blueprints | Comment on the brief | none | none | J1 · J2 |
| 159 | Goals & plan · Brief & blueprints | Select blueprint documents for the Planner to read | none | none | J1 · J2 |
| 160 | Goals & plan · Plan | Draft a plan (first draft) | live | chat relay or model route | J1 · J2 |
| 161 | Goals & plan · Plan | Redraft the plan | none | chat relay or model route | J1 · J2 |
| 162 | Goals & plan · Plan | Author context (workspace-wide source-selection scope) | none | none | J1 · J2 |
| 163 | Goals & plan · Plan / Milestones | Add a milestone (manually) | none | none | J1 · J2 |
| 164 | Goals & plan / Milestones | Milestone status change (open/doing/done/dropped) | live | none | J1 · J2 |
| 165 | Goals & plan · Milestones | Edit milestone title | none | none | J1 · J2 |
| 166 | Goals & plan · Milestones | Draft first files (per milestone) | live | chat relay or model route | J1 · J2 |
| 167 | Goals & plan · Milestones | Check current files (review_current) | none | none | J1 · J2 |
| 168 | Goals & plan · Milestones | Propose smaller steps (breakdown) | none | chat relay or model route | J1 · J2 |
| 169 | Goals & plan · Milestones | Adopt prerequisites (breakdown proposal) | none | none once a proposal exists | J1 · J2 |
| 170 | Goals & plan · Milestones | Reconsider (reject breakdown proposal) | none | none | J1 · J2 |
| 171 | Goals & plan · Milestones | Breakdown history (read-only) | none | none | J1 · J2 |
| 172 | Goals & plan · Acceptance checks | Propose acceptance checks | live | chat relay or model route (R1 used a free Ge | J1 · J2 |
| 173 | Goals & plan · Acceptance checks | Use these checks (approve proposal) | live | chat relay or model route, to get a proposal | J1 · J2 |
| 174 | Goals & plan · Acceptance checks | Discard (proposal) | live | none, once a proposal exists | J1 · J2 |
| 175 | Goals & plan · Public expectations | Edit public acceptance expectations (criteria JSON) | none | none | J1 · J2 |
| 176 | Goals & plan · Public expectations | JSON response interfaces (public interface declarations) | live | none for the editor itself; chat relay upstr | J1 · J2 |
| 177 | Goals & plan · Goalposts | Propose / Reassess goalposts | none | chat relay or model route | J1 · J2 |
| 178 | Goals & plan · Build continuation | Check drafts by running their tests (build_steps toggle) | live | none | J1 · J2 |
| 179 | Goals & plan · Build continuation | Apply checked drafts automatically (build_apply grant) | none | none to toggle; needs approved acceptance ch | J1 · J2 |
| 180 | Goals & plan · Build continuation | Allowed files/folders (build_paths) | live | none | J1 · J2 |
| 181 | Goals & plan · Build continuation | Save build settings | live | none | J1 · J2 |
| 182 | Goals & plan · Build continuation | Build next step | live | chat relay or model route | J1 · J2 |
| 183 | Goals & plan · Onboarding | Use a chat window (no key) - quick relay setup | live | none itself; the relays it sets up need a hu | J1 · J2 |
| 184 | Goals & plan · Onboarding | Other options (nav to Thinking power/Inference page) | none | none | J1 · J2 |
| 185 | Goals & plan · Plan | Held plan review (read-only) | tests only | none | J1 · J2 |
| 186 | Goals & plan · Plan | Comment on the plan | none | none | J1 · J2 |
| 187 | Goals & plan · Milestones | Comment on a milestone | none | none | J1 · J2 |
| 188 | Goals & plan (backend-only, no UI/route) | Abandon an uncertain breakdown/correction attempt | tests only | n/a | J1 · J2 |
| 189 | Work & proposals · Fixes tab | Find work now (round) | none | chat relay or model route | J2 · J3 |
| 190 | Work & proposals · Fixes tab | Apply to my files (proposal) | none | none to click; needs a prior 'round' to have | J2 · J3 |
| 191 | Work & proposals · Fixes tab | Reject (proposal) | none | none | J2 · J3 |
| 192 | Work & proposals · Fixes tab | Undo (applied proposal) | none | none | J2 · J3 |
| 193 | Work & proposals · Fixes tab | Copy patch | none | none | J2 · J3 |
| 194 | Work & proposals · Drafts tab | Measure current source (source-baseline diagnostic) | none | none, but up to 240s wall time | J2 · J3 |
| 195 | Work & proposals · Drafts tab | Retrieve saved answer (resume_author) | none | a genuinely interrupted live call, or script | J2 · J3 |
| 196 | Work & proposals · Drafts tab | Draft next milestone only (author-only build) | live | chat relay or model route | J2 · J3 |
| 197 | Work & proposals · Drafts tab | Refresh allowance | tests only | none | J2 · J3 |
| 198 | Work & proposals · Drafts tab | Review goals (nav) | tests only | none | J2 · J3 |
| 199 | Work & proposals · Drafts tab | Use alternate author (one-shot escalation) | live | chat relay or model route, after exhausting  | J2 · J3 |
| 200 | Work & proposals · Drafts tab | Correct retained answer (bounded correction) | none | chat relay or model route, after a host-refu | J2 · J3 |
| 201 | Work & proposals · per-draft actions | Reconcile preflight · recheck only | tests only | none (local, no model call), but needs prior | J2 · J3 |
| 202 | Work & proposals · per-draft actions | Allocate checks (verification_allocation) | none | none (local); needs a prior source-baseline  | J2 · J3 |
| 203 | Work & proposals · per-draft actions | Resume timed-out check once | none | none (local); needs a prior timed-out check  | J2 · J3 |
| 204 | Work & proposals · per-draft actions | Revise after clarification (requirement supplement) | tests only | chat relay or model route | J2 · J3 |
| 205 | Work & proposals · per-draft actions | Revision packet (inspect candidate scope, needs_revision drafts) | none | none (local, no model call per its own text) | J2 · J3 |
| 206 | Work & proposals · per-draft actions | Create one revision draft (author-only revision) | tests only | chat relay or model route | J2 · J3 |
| 207 | Work & proposals · per-draft actions | Recheck saved draft | live | none (local execution) | J2 · J3 |
| 208 | Work & proposals · per-draft actions | Write these files (apply draft) | live | none to click; needs a prior draft (chat rel | J2 · J3 |
| 209 | Work & proposals · per-draft actions | Reject (draft) | none | none | J2 · J3 |
| 210 | Work & proposals · per-draft actions | Undo (applied draft) | none | none | J2 · J3 |
| 211 | Work & proposals · per-draft actions | View/Hide a draft file's diff | tests only | none | J2 · J3 |
| 212 | Work & proposals · per-draft actions | Open review notes | tests only | none | J2 · J3 |
| 213 | Work & proposals · per-draft actions | Mark milestone done (post-apply prompt) | live | none | J2 · J3 |
| 214 | Work & proposals · Attempts tab | View attempt detail / comment | none | none | J2 · J3 |
| 215 | Work & proposals · Last round tab | Last-round summary / code-object health (read-only) | none | none | J2 · J3 |
| 216 | Work & proposals · Build memory tab | Next author memory preview / historical observations (read-only) | none | none | J2 · J3 |
| 217 | Work & proposals · navigation | Switch tabs: Fixes / Drafts / Attempts / Last round / Build memory | tests only | none | J2 · J3 |
| 218 | Scheduled rounds | Work on a schedule (auto_work) | live | none | J2 · L0/L1 (auto_work) |
| 219 | Scheduled rounds | How often (interval_minutes) | none | none | J2 · L0/L1 (auto_work) |
| 220 | Scheduled rounds | How Runesmith may act: Observe vs Propose (autonomy) | live | none | J2 · L0/L1 (auto_work) |
| 221 | Scheduled rounds | Run a round now | live | scripted/offline or local model for a live r | J2 · L0/L1 (auto_work) |
| 222 | Scheduled rounds | Pause / Resume queue | tests only | none | J2 · L0/L1 (auto_work) |
| 223 | Scheduled rounds | Stop current job (after this step) | tests only | none | J2 · L0/L1 (auto_work) |
| 224 | Scheduled rounds | Restart recovery: Keep / Set aside / Refresh | tests only | none | J2 · L0/L1 (auto_work) |
| 225 | Mapping | Measure code by running its tests while mapping (probe_tests) | live | none | J3 · L0/L1 (probe_tests) |
| 226 | Mapping | Most objects to map (max_objects) | none | none | J3 · L0/L1 (probe_tests) |
| 227 | Mapping | Never touch (exclude) an object | live | none | J3 · L0/L1 (probe_tests) |
| 228 | Mapping/Living map | Living map lens: Environment | live | none | J3 · L0/L1 (probe_tests) |
| 229 | Mapping/Living map | Living map lens: Self | live | none | J3 · L0/L1 (probe_tests) |
| 230 | Mapping/Living map | Living map lens: Development | live | none | J3 · L0/L1 (probe_tests) |
| 231 | Mapping/Living map | Living map lens: Operations | none | none | J3 · L0/L1 (probe_tests) |
| 232 | Mapping/Living map | Re-map & measure (probe on demand) | live | none | J3 · L0/L1 (probe_tests) |
| 233 | Mapping/Living map | Measure its tests (per-object) | none | none | J3 · L0/L1 (probe_tests) |
| 234 | Mapping/Living map | Suggest fixes for broken links | none | none | J3 · L0/L1 (probe_tests) |
| 235 | Mapping/Living map | Comment on any map node (hub/object/kernel module/organ/generation/capability/station) | live | none | J3 · L0/L1 (probe_tests) |
| 236 | Work & proposals | Apply / Undo / Reject a proposal or draft | live | none | J2 · J3 |
| 237 | Work & proposals | Draft first files for a milestone | live | chat relay or API route | J2 · J3 |
| 238 | Work & proposals | Recheck saved draft / Check existing files (review_current) | live | none | J2 · J3 |
| 239 | Work & proposals | Build next step (build job) | live | chat relay or API route | J2 · J3 |
| 240 | Work & proposals | Escalate to an alternate author | live | a second configured author instrument | J2 · J3 |
| 241 | Work & proposals | Supplement / clarify after a requirement change | tests only | none | J2 · J3 |
| 242 | Work & proposals | Correct a retained rejected answer | none | none | J2 · J3 |
| 243 | Work & proposals | Source baseline measurement | none | none | J2 · J3 |
| 244 | Work & proposals | Allocate a separately-authorized full verification check | live | none | J2 · J3 |
| 245 | Work & proposals | Reconcile a linked preflight refusal | none | none | J2 · J3 |
| 246 | Work & proposals | Resume a retained-candidate check extension | none | none | J2 · J3 |
| 247 | Work & proposals | Retrieve a saved author answer (resume_author) | live | none | J2 · J3 |
| 248 | Work & proposals | Revise via the existing allowance | none | none | J2 · J3 |
| 249 | Work & proposals | Break a milestone into prerequisites | none | none | J2 · J3 |
| 250 | Work & proposals | Propose / approve / discard acceptance checks | live | a configured plan/kaizen-role model (chat re | J2 · J3 |
| 251 | Modes & measurements | Work-mode executor: Map & Plan | tests only | none | J5 · L0/L1 (modes) |
| 252 | Modes & measurements | Work-mode executor: Build | tests only | none | J5 · L0/L1 (modes) |
| 253 | Modes & measurements | Work-mode executor: Troubleshoot | live | none | J5 · L0/L1 (modes) |
| 254 | Modes & measurements | Work-mode executor: Optimize | live | a measurement with a real prior observation, | J5 · L0/L1 (modes) |
| 255 | Modes & measurements | Work-mode executor: Operations | tests only | a saved CSV/JSON/pasted report | J5 · L0/L1 (modes) |
| 256 | Modes & measurements | Enable/disable a mode switch | tests only | none | J5 · L0/L1 (modes) |
| 257 | Modes & measurements | Per-mode instructions text | tests only | none | J5 · L0/L1 (modes) |
| 258 | Modes & measurements | Add custom mode | tests only | none | J5 · L0/L1 (modes) |
| 259 | Modes & measurements | Infer purpose without explicit direction | tests only | none | J5 · L0/L1 (modes) |
| 260 | Modes & measurements | Save modes | tests only | none | J5 · L0/L1 (modes) |
| 261 | Modes & measurements | Run mode now | tests only | depends on executor (see above) | J5 · L0/L1 (modes) |
| 262 | Modes & measurements | Add/edit a measurement definition | live | none for csv/json/paste; ga4/email are non-f | J5 · L0/L1 (modes) |
| 263 | Modes & measurements | Measurement aggregation | tests only | none | J5 · L0/L1 (modes) |
| 264 | Modes & measurements | Measurement threshold | tests only | none | J5 · L0/L1 (modes) |
| 265 | Modes & measurements | Measurement max_age_hours (recency rule) | tests only | none | J5 · L0/L1 (modes) |
| 266 | Modes & measurements | Paste report (csv/json) | tests only | none | J5 · L0/L1 (modes) |
| 267 | Modes & measurements | Measure now (per measurement) | tests only | a saved report | J5 · L0/L1 (modes) |
| 268 | Modes & measurements | Support reports: paste a support report | live | none | J5 · L0/L1 (modes) |
| 269 | Modes & measurements | Support reports: select/exclude for repair context | tests only | none | J5 · L0/L1 (modes) |
| 270 | Dashboards | General dashboard tab | tests only | none | J5 · L0/L1 (modes) |
| 271 | Dashboards | Add project dashboard | tests only | none | J5 · L0/L1 (modes) |
| 272 | Dashboards | Customize panels | tests only | none | J5 · L0/L1 (modes) |
| 273 | Dashboards | Remove dashboard | tests only | none | J5 · L0/L1 (modes) |
| 274 | Dashboards | Refresh receipts | tests only | none | J5 · L0/L1 (modes) |
| 275 | Self-improvement / Kaizen | Let Runesmith improve itself (kaizen setting) | live | a Worker/kaizen-capable model plus >= min_ex | J6 · L0/L1 (kaizen) |
| 276 | Self-improvement / Kaizen | Experience before first campaign (min_experience) | live | none | J6 · L0/L1 (kaizen) |
| 277 | Self-improvement / Kaizen | New attempts between campaigns (kaizen_every) | live | none | J6 · L0/L1 (kaizen) |
| 278 | Self-improvement / Kaizen | Generations lineage view | live | none | J6 · L0/L1 (kaizen) |
| 279 | Self-improvement / Kaizen | Make active (rollback / owner override) | live | none | J6 · L0/L1 (kaizen) |
| 280 | Self-improvement / Kaizen | Online trial (live view) | live | a live repair round(s) with kaizen on, or th | J6 · L0/L1 (kaizen) |
| 281 | Self-improvement / Kaizen | Library: Adopt (start a trial) — C7 | live | none for adopt itself; a real trial decision | J6 · L0/L1 (kaizen) |
| 282 | Self-improvement / Kaizen | Capabilities gauges (read-only) | none | real repair history | J6 · L0/L1 (kaizen) |
| 283 | Self-improvement / Kaizen | Kaizen campaigns list (read-only) | live | a live round that crosses min_experience/kai | J6 · L0/L1 (kaizen) |
| 284 | Self-improvement / Kaizen | Tell the Improver something (comment) | none | none | J6 · L0/L1 (kaizen) |
| 285 | Self-improvement / Kaizen | Kaizen job kind 'health' (worker enqueue) | none | n/a (backend-only path) | J6 · L0/L1 (kaizen) |
| 286 | Notes & comments | Notes page filters | none | none | J1 |
| 287 | Notes & comments | Note on the whole workspace | none | none | J1 |
| 288 | Notes & comments | Comment on anything (comment-mode / 'C' key) | live | none | J1 |
| 289 | Notes & comments | Give notes to the model (read_notes) | none | none | J1 |
| 290 | Notes & comments | Resolve a note | none | none | J1 |
| 291 | Activity | Activity tab: Live log | tests only | none | J2 |
| 292 | Activity | Activity tab: Ledger | live | none | J2 |
| 293 | Activity | Activity tab: Jobs | tests only | none | J2 |
| 294 | Worker restart behaviour | Interrupted job recovery on restart | live | a live process kill mid-job for full coverag | J7 |
| 295 | Home/Overview onboarding | Getting-set-up checklist (6 steps incl. 'Chose how Runesmith may work here') | live | none | J1 · J0 · L0/L1 (policy) |
| 296 | Cross-cutting / non-Studio surface | CLI self-improvement commands (kaizen, generations activate/export/import/requalify, trial --open) | live | local shell access (not a Studio/browser jou | J0 |
| 297 | Entry point | Windows launcher Runesmith.cmd | tests only | none | J1 · J0 · L0/L1 (policy) |
| 298 | Entry point | macOS launcher Runesmith.command | none | macOS/Linux | J1 · J0 · L0/L1 (policy) |
| 299 | Entry point | Linux launcher runesmith.sh | none | macOS/Linux | J1 · J0 · L0/L1 (policy) |
| 300 | Entry point | CLI `runesmith up [folder] [--port] [--no-browser] [--last]` | live | none | J1 · J0 · L0/L1 (policy) |
| 301 | Entry point | CLI `runesmith init` | live | none | J1 · J0 · L0/L1 (policy) |
| 302 | Onboarding | Genesis intro: 7 scenes (spark, forge, world, itself, guard, evidence, minds) | live | none | J1 · J0 · L0/L1 (policy) |
| 303 | Onboarding | Genesis: Skip intro button | live | none | J1 · J0 · L0/L1 (policy) |
| 304 | Onboarding | Genesis finale: name + description + 4 type buttons (build/improve/docs/explore) + Forge it | live | none | J1 · J0 · L0/L1 (policy) |
| 305 | Onboarding | Genesis finale: Skip for now | none | none | J1 · J0 · L0/L1 (policy) |
| 306 | Onboarding | /cinema mode (loops 3 demo stories: bakery/freight/clinics) | live | none | J1 · J0 · L0/L1 (policy) |
| 307 | Onboarding | Replay introduction / open Cinema from Settings | none | none | J1 · J0 · L0/L1 (policy) |
| 308 | Overview | Hero CTA (7 states): restart-recovery review / open chat relay / inspect current job / review paused work / ad | live | chat relay | J1 · J0 · L0/L1 (policy) |
| 309 | Overview | 'Use a chat window' one-click setup | live | none | J1 · J0 · L0/L1 (policy) |
| 310 | Overview | Setup checklist (6 steps, 'Do it' jump links) | tests only | none | J1 · J0 · L0/L1 (policy) |
| 311 | Overview | 'How Runesmith may work here' policy switches: schedule / probe tests / self-improve | tests only | none | J1 · J0 · L0/L1 (policy) |
| 312 | Overview | Local setup checks / Refresh local checks | tests only | none | J1 · J0 · L0/L1 (policy) |
| 313 | Overview | KPI cards (objects mapped / waiting for you / repairs accepted / active generation) | tests only | none | J1 · J0 · L0/L1 (policy) |
| 314 | Overview | 'What Runesmith found here' object grid | live | none | J1 · J0 · L0/L1 (policy) |
| 315 | Overview | 'What comes next' (goal/milestone/rung feed) | none | none | J1 · J0 · L0/L1 (policy) |
| 316 | Overview | Live console + Capabilities gauges | tests only | none | J1 · J0 · L0/L1 (policy) |
| 317 | Global shell | Sidebar navigation (11 pages) | live | none | J9 |
| 318 | Global shell | Keyboard shortcuts (1-9 page jump, C comment, R run, ? help, Ctrl+K palette) | live | none | J9 |
| 319 | Global shell | Command palette (16 built-in commands) | live | none | J9 |
| 320 | Global shell | Comment mode (press C or hover bubble on any card/node) | live | none | J9 |
| 321 | Global shell | Theme toggle (light/dark/auto) | live | none | J9 |
| 322 | Global shell | Sidebar collapse toggle | none | none | J9 |
| 323 | Global shell | Status pill (click routes to relay/inference/activity by state) | tests only | none | J9 |
| 324 | Global shell | Run now / Pause-Resume worker buttons (topbar) | live | scripted/offline | J9 |
| 325 | Global shell | Folder/workspace switcher button (sidebar) | live | none | J9 |
| 326 | Living map | Lens switcher: Environment / Self / Development / Operations | live | none | J3 · L0/L1 (probe_tests) |
| 327 | Living map · Environment | Pan / zoom / reset view (SVG canvas) | live | none | J3 · L0/L1 (probe_tests) |
| 328 | Living map · Environment | Narrow/phone column layout (auto-switches <560px) | live | none | J3 · L0/L1 (probe_tests) |
| 329 | Living map · Environment | 'Re-map & measure' button | live | none | J3 · L0/L1 (probe_tests) |
| 330 | Living map · Environment | Object node select → side panel (click or Tab+Enter) | live | none | J3 · L0/L1 (probe_tests) |
| 331 | Living map · Environment | Exclude / Include an object | live | none | J3 · L0/L1 (probe_tests) |
| 332 | Living map · Environment | 'Suggest fixes for N broken links' (link doctor) | live | none | J3 · L0/L1 (probe_tests) |
| 333 | Living map · Environment | 'Measure its tests' button (per unmeasured Python object) | live | none | J3 · L0/L1 (probe_tests) |
| 334 | Living map · Self | Kernel ring / organs / lineage (pan/zoom/select) | live | none | J3 · L0/L1 (probe_tests) |
| 335 | Living map · Development | Goals pillbox + development tracks (plan/object/self lanes) + campaigns | live | none | J3 · L0/L1 (probe_tests) |
| 336 | Living map · Operations | Work-loop pipeline, roles, attention, trial, schedule, live log | live | none | J3 · L0/L1 (probe_tests) |
| 337 | Work & proposals | Tabs: Fixes / Drafts / Attempts / Last round / Build memory | live | none | J2 · J3 |
| 338 | Work & proposals | 'Find work now' (queue a round) | live | scripted/offline | J2 · J3 |
| 339 | Work & proposals · Fixes | Apply to my files | live | scripted/offline | J2 · J3 |
| 340 | Work & proposals · Fixes | Reject (with optional reason) | none | scripted/offline | J2 · J3 |
| 341 | Work & proposals · Fixes | Undo (exact restore) | live | scripted/offline | J2 · J3 |
| 342 | Work & proposals · Fixes | Copy patch / Comment on a fix | none | none | J2 · J3 |
| 343 | Work & proposals · Drafts | Measure current source (source-baseline diagnostic) | none | scripted/offline | J2 · J3 |
| 344 | Work & proposals · Drafts | Retrieve saved answer (author recovery ticket) | live | API key | J2 · J3 |
| 345 | Work & proposals · Drafts | Draft next milestone only (author-only build) | live | API key | J2 · J3 |
| 346 | Work & proposals · Drafts | Use alternate author (one-time escalation) | live | API key | J2 · J3 |
| 347 | Work & proposals · Drafts | Correct retained answer (bounded correction, ≤2) | live | API key | J2 · J3 |
| 348 | Work & proposals · Drafts | Reconcile preflight — recheck only | live | scripted/offline | J2 · J3 |
| 349 | Work & proposals · Drafts | Allocate checks (separate verification budget) | live | scripted/offline | J2 · J3 |
| 350 | Work & proposals · Drafts | Resume timed-out check once | live | scripted/offline | J2 · J3 |
| 351 | Work & proposals · Drafts | Revise after clarification (requirement supplement) | live | API key | J2 · J3 |
| 352 | Work & proposals · Drafts | Revision packet / Create one revision draft | live | API key | J2 · J3 |
| 353 | Work & proposals · Drafts | Recheck saved draft | live | chat relay | J2 · J3 |
| 354 | Work & proposals · Drafts | Write these files (apply draft) | live | chat relay | J2 · J3 |
| 355 | Work & proposals · Drafts | Milestone-done prompt after a checked write | tests only | chat relay | J2 · J3 |
| 356 | Work & proposals · Drafts | Reject / Undo a draft | tests only | chat relay | J2 · J3 |
| 357 | Work & proposals | Attempts tab (per-attempt drawer, plain-words outcome) | live | scripted/offline | J2 · J3 |
| 358 | Work & proposals | Last round / opportunities tab | live | scripted/offline | J2 · J3 |
| 359 | Work & proposals | Build memory tab | none | scripted/offline | J2 · J3 |
| 360 | Goals & plan | Goals list: add / edit / remove / mark done | none | none | J1 · J2 |
| 361 | Goals & plan | Brief + blueprint document picker + save | live | none | J1 · J2 |
| 362 | Goals & plan | Draft / Redraft plan | live | chat relay | J1 · J2 |
| 363 | Goals & plan | 'Use a chat window (no key)' quick setup (in-plan variant) | live | none | J1 · J2 |
| 364 | Goals & plan | Author context editor (workspace-wide file prioritization) | live | scripted/offline | J1 · J2 |
| 365 | Goals & plan | Add milestone manually | none | none | J1 · J2 |
| 366 | Goals & plan | Milestone status dropdown (open/doing/done/dropped) | tests only | none | J1 · J2 |
| 367 | Goals & plan | Draft first files (per milestone) | live | chat relay | J1 · J2 |
| 368 | Goals & plan | Check current files (review_current) | none | none | J1 · J2 |
| 369 | Goals & plan | Propose smaller steps (breakdown) | live | API key | J1 · J2 |
| 370 | Goals & plan | Adopt / Reconsider a proposed breakdown | live | API key | J1 · J2 |
| 371 | Goals & plan | Propose acceptance checks (per milestone) | live | free model via Milliner | J1 · J2 |
| 372 | Goals & plan | Use these checks / Discard (acceptance approval) | live | free model via Milliner | J1 · J2 |
| 373 | Goals & plan | Trial run on a throwaway copy (auto, shown with the proposal) | live | free model via Milliner | J1 · J2 |
| 374 | Goals & plan | Edit expectations (public acceptance criteria, JSON) | live | API key | J1 · J2 |
| 375 | Goals & plan | JSON response interfaces editor | live | API key | J1 · J2 |
| 376 | Goals & plan | Goalposts: Propose / Reassess | live | free model via Milliner | J1 · J2 |
| 377 | Goals & plan | Build continuation: check-drafts toggle / auto-apply toggle / allowed paths / Build next step | live | chat relay | J1 · J2 |
| 378 | Modes & measurements | 5 built-in modes (Map & Plan, Build, Troubleshoot, Optimize, Operations): enable + instructions + linked measu | live | scripted/offline | J5 · L0/L1 (modes) |
| 379 | Modes & measurements | Add custom mode (name + executor) | none | scripted/offline | J5 · L0/L1 (modes) |
| 380 | Modes & measurements | Infer purpose without explicit direction (toggle) | none | free model via Milliner | J5 · L0/L1 (modes) |
| 381 | Modes & measurements | Measurement: Add/Edit definition | none | none | J5 · L0/L1 (modes) |
| 382 | Modes & measurements | Measurement: Paste report / Measure now | none | none | J5 · L0/L1 (modes) |
| 383 | Modes & measurements | Optimization hypotheses (read-only proposal list) | none | free model via Milliner | J5 · L0/L1 (modes) |
| 384 | Modes & measurements | Support reports: Paste support report | live | API key | J5 · L0/L1 (modes) |
| 385 | Modes & measurements | Support reports: Select/Exclude for repair context | live | API key | J5 · L0/L1 (modes) |
| 386 | Thinking power | Three ways to give Runesmith a mind (local / API key / chat window) | live | none | J8 · L0/L1 (no-model, roles) |
| 387 | Thinking power | Add-model wizard: preset picker (This computer / With a key / No key needed / Advanced) | live | API key | J8 · L0/L1 (no-model, roles) |
| 388 | Thinking power | Local model scan / 'Look again' | live | local model server | J8 · L0/L1 (no-model, roles) |
| 389 | Thinking power | Role lanes: reorder / remove / add fallback (repair / kaizen / plan) | live | scripted/offline | J8 · L0/L1 (no-model, roles) |
| 390 | Thinking power | Instrument row: Test / Remove / Recorded availability / Route editor | live | API key | J8 · L0/L1 (no-model, roles) |
| 391 | Thinking power | Chat relay: Copy request / paste reply+model / Send / Skip / Send unchanged anyway / Copy correction request | live | chat relay | J8 · L0/L1 (no-model, roles) |
| 392 | Thinking power | Usage & cost coverage modal | live | API key | J8 · L0/L1 (no-model, roles) |
| 393 | Notes | Filters (Open / Resolved / All) | none | none | J1 |
| 394 | Notes | Note on the whole workspace / per-target comment (everywhere) | live | none | J1 |
| 395 | Activity | Live log: Pause/Resume, Stop current job | live | scripted/offline | J2 |
| 396 | Activity | Restart recovery review: Keep waiting jobs / Set aside waiting jobs | live | scripted/offline | J2 |
| 397 | Activity | Ledger: filter chips (Everything/Work/Self-improvement/Your input/Models/System) + Verify the chain | live | none | J2 |
| 398 | Activity | Jobs tab (running/queued/history table) | live | none | J2 |
| 399 | Self-improvement | Generations list + 'Make active' (manual rollback) | live | scripted/offline | J6 · L0/L1 (kaizen) |
| 400 | Self-improvement | Online trial view (read-only counts/looks) | live | scripted/offline | J6 · L0/L1 (kaizen) |
| 401 | Self-improvement | Library: Adopt (starts a trial) | live | scripted/offline | J6 · L0/L1 (kaizen) |
| 402 | Self-improvement | Capabilities gauges + Kaizen campaigns view | none | free model via Milliner | J6 · L0/L1 (kaizen) |
| 403 | Dashboards | General / per-project tabs | live | API key | J5 · L0/L1 (modes) |
| 404 | Dashboards | Add project dashboard (name/folder/home) | none | none | J5 · L0/L1 (modes) |
| 405 | Dashboards | Customize panels (5 panel types: progress/modes/measurements/activity/inference) | none | none | J5 · L0/L1 (modes) |
| 406 | Dashboards | Remove dashboard / Refresh receipts | none | none | J5 · L0/L1 (modes) |
| 407 | Settings · Behaviour | Workspace name / Autonomy (Observe vs Propose) | none | none | L0/L1 · J9 |
| 408 | Settings · Behaviour | Work on a schedule + interval picker | tests only | none | L0/L1 · J9 |
| 409 | Settings · Behaviour | Measure code by running its tests (probe_tests) + Most objects to map + Never-touch exclusions | live | scripted/offline | L0/L1 · J9 |
| 410 | Settings · Behaviour | Give notes to the model (read_notes) | none | none | L0/L1 · J9 |
| 411 | Settings · Behaviour | Self-improvement (kaizen) toggle + experience thresholds | tests only | none | L0/L1 · J9 |
| 412 | Settings · Health | Local checks + 'Also check the models over the network' | none | none | L0/L1 · J9 |
| 413 | Settings · Data | Work in another folder (opens folder picker) / Open in file manager / Open the home / Export a snapshot / Quit | live | scripted/offline | J7 |
| 414 | Settings · About | Evidence table (SR7 shown-once, SR5/SR6 not-shown, SR6-W null, sandbox unit-tested) | tests only | none | L0/L1 · J9 |
| 415 | Folder picker | Browse / Recent chips / path+home text inputs / New folder here / Work here | none | none | J0 |
| 416 | CLI (non-Studio) | `runesmith demo [--live] [--kaizen] [--manual-author]` | none | API key | J10 |
| 417 | CLI (non-Studio) | `runesmith status` | live | none | J10 |
| 418 | CLI (non-Studio) | `runesmith doctor [--offline]` | live | none | J10 |
| 419 | CLI (non-Studio) | `runesmith selfmap [--records]` | none | none | J10 |
| 420 | CLI (non-Studio) | `runesmith envmap <workspace> [--probe]` | none | none | J10 |
| 421 | CLI (non-Studio) | `runesmith discover <repo>` | none | none | J10 |
| 422 | CLI (non-Studio) | `runesmith repair --repo --test --judge-test --issue --apply --opportunity` | none | scripted/offline | J10 |
| 423 | CLI (non-Studio) | `runesmith run [--opportunities --passes --seed --min-experience --max-answered --bar --kaizen-every]` | none | scripted/offline | J10 |
| 424 | CLI (non-Studio) | `runesmith steward <workspace> --rounds --interval --exclude --max-objects --seed --min-experience --kaizen-ev | live | scripted/offline | J10 |
| 425 | CLI (non-Studio) | `runesmith trial [--open ID]` | none | scripted/offline | J10 |
| 426 | CLI (non-Studio) | `runesmith report` | none | none | J10 |
| 427 | CLI (non-Studio) | `runesmith proposals [--write DIR]` | live | none | J10 |
| 428 | CLI (non-Studio) | `runesmith diagnose [--records]` | none | none | J10 |
| 429 | CLI (non-Studio) | `runesmith kaizen --tasks --workers --max-answered` | none | scripted/offline | J10 |
| 430 | CLI (non-Studio) | `runesmith manual {list,show,answer} [--file --clipboard --model --force]` | none | scripted/offline | J10 |
| 431 | CLI (non-Studio) | `runesmith generations {list,verify,activate,export,import,requalify} [--expected --to --from]` | none | scripted/offline | J10 |
| 432 | CLI (non-Studio) | `runesmith ledger` | live | none | J10 |
| 433 | Open gap | G1/G1.3: non-programmer acceptance-check path (evolved live across 4 releases in one session) | live | free model via Milliner | Prerequisite (before the journeys) |
| 434 | Open gap | G2: no 'Try it' affordance to run the built program from the Studio | none | chat relay | Prerequisite (before the journeys) |
| 435 | Open gap | F4: expert wording in milestone/draft cards ('Public acceptance expectations…', 'Private assertions stay in ve | none | chat relay | Prerequisite (before the journeys) |
| 436 | Open gap | F3: 'Executable build checks'/'Delegated build application' shown as bare Off badges with no switch or link fr | none | chat relay | Prerequisite (before the journeys) |
| 437 | Open gap | F12: a gateway-refused call (before admission) doesn't fall through to the role's next model when retries are  | none | free model via Milliner | Prerequisite (before the journeys) |
| 438 | Open gap | F8/F9: alarming/raw confirm-dialog wording on 'Write these files' when only self-checks passed | none | chat relay | Prerequisite (before the journeys) |
| 439 | Open gap | No independent security review / OS-level file+network isolation for untrusted organs (AppContainer/seccomp) | none | other | Prerequisite (before the journeys) |
| 440 | Open gap | Full production/unattended release path (place in a folder, supply keys, walk away) | none | other | Prerequisite (before the journeys) |
| 441 | Global shell — connectivity | Studio unreachable / 'not answering' screen with Try again | none | none — start Studio, then kill the server pr | J7 (situations) |
| 442 | Global shell — auth | 'Studio is locked' screen (401, missing/stale token) | none | none — restart Runesmith, reopen a bookmarke | J7 (situations) |
| 443 | Global shell — live updates | SSE 'Reconnecting to Runesmith…' status-pill state | none | none — start a long job, then sleep/wake or  | J7 (situations) |
| 444 | Global shell — multiple tabs | Cross-tab forced reload on workspace switch ('workspace' bus event) | none | none — two tabs on the same Studio, switch f | J7 (situations) |
| 445 | Settings · Data · Work in another folder | Uncertain-switch-outcome recovery state | none | none — kill the server right after clicking  | J7 (situations) |
| 446 | Settings · Data · Work in another folder | 'Refresh switch readiness' / 'Reload selected workspace' buttons | none | none | J7 (situations) |
| 447 | Settings · Data · folder picker | Browsing into a permission-denied subfolder | none | other — a folder this OS account cannot list | J7 (situations) |
| 448 | Settings · Data · New folder here… | New-folder name validation (reserved characters / . / ..) | none | none | J7 (situations) |
| 449 | Work & proposals · Drafts tab | Undo (applied draft) refuses when files changed after apply | none | none — apply a draft, hand-edit one of its f | J7 (situations) |
| 450 | Modes & measurements — per-mode Run now | Per-mode blockers gate 'Run now' with a warning message | none | none | J7 (situations) |
| 451 | Modes & measurements / any job enqueue | guard_job: "All <executor> modes are off. No work started." | none | none — disable all Build-executor modes, tri | J7 (situations) |
| 452 | Modes & measurements / any multi-step build job | Mid-step guard: mode policy or workspace instructions changed during an in-flight job | none | none — start a multi-step build, change mode | J7 (situations) |
| 453 | Modes & measurements | Legacy mode-configuration upgrade callout | none | other — a workspace home created by an older | J7 (situations) |
| 454 | Thinking power — Add-wizard 'List models' | Catalog-listing failure messaging (bad key vs. provider down vs. unsupported) | none | API key (an invalid one) or local model serv | J7 (situations) |
| 455 | Goals & plan — Edit public acceptance expectatio | Stale-digest conflict on concurrent expectations edit | none | none — two tabs, edit the same milestone's e | J7 (situations) |
| 456 | Goals & plan — Edit public acceptance expectatio | Malformed JSON entry loses the whole edit (no retry loop) | none | none | J7 (situations) |
| 457 | CLI / Launcher — first run, no argument, no hist | runesmith up --last with zero recent workspaces falls back to a default project folder | none | none — needs a machine/profile with no prior | J7 (situations) |
| 458 | CLI / Launcher — port binding | Automatic port fallback scan (no --port) vs. immediate hard failure (explicit --port busy) | none | none — occupy the default port range, or a c | J7 (situations) |
| 459 | Launcher — Windows console codepage / non-ASCII  | Runesmith.cmd path handling for non-ASCII or spaced folder names | none | other — Windows account/folder with non-ASCI | J7 (situations) |
| 460 | Settings · Data · folder picker — typed path | Relative or non-absolute path typed directly (bypassing Browse) | none | none | J7 (situations) |
