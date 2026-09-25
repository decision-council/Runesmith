# Runesmith architecture

This document explains how Runesmith is built and why. The scientific basis is the MillinerOS/Runesmith blueprint. Section numbers below refer to it, and Runesmith implements its central separation: a small authoritative kernel and a broad adaptive surface (§9.1).

## 1. The instrument–substrate idea

A model is an **instrument**. It supplies interpretation, search and novelty for the length of one call. The **substrate** is what remains after the call ends. For Runesmith that means:
- organs;
- generations;
- memories;
- maps;
- the ledger.

The scientific bet is that some useful competence can be moved from the instrument into the substrate. After that move, a weaker instrument can reuse it, or no instrument at all. Runesmith is engineered so the bet can be tested, which is why every piece of state is typed, versioned and measured (§1.2–1.3).

## 2. Regions

| Region | Contents | Who may change it |
|---|---|---|
| **Kernel (fixed)** | `canon`, `ledger`, `generations`, `instruments` (router, transport retries, failure classes) + `manual` (a person relays requests to a chat model), `opportunity` (envelope, cockpit handlers, telemetry), `objects/code` (public signal, trace, throwaway copies), `sandbox` + `organ_child` (confinement), `kaizen` (diagnosis, attention with drift detection, PDSA, online trials, affordance audit), `selfmap`, `envmap`, `memory`, `config`, `cli` | Humans, through ordinary review. Kernel changes are never produced by the Kaizen engine. |
| **Operations (fixed)** | `discover` (opportunities and triage), `local` (one opportunity end to end), `loop` (Kaizen always), `steward` (workspace rounds), `proposals` (fixes as patches), `report` (the dashboard), `share` (export and import of generations), `doctor` (health and requalification), `demo` | Humans, through ordinary review. They compose the kernel. None of them edits an object or activates a generation except by a trial or an explicit operator compare-and-swap. |
| **Organs (mutable)** | `organs/repair.py`, and future organs | The Kaizen engine may propose changes. A change becomes real only as a new frozen generation, after qualification. |

## 3. Organs and the cockpit

An organ is one standard-library module with `run(view, cockpit) -> dict`. The kernel runs it in `organ_child.py`, under `python -I -B`, with a secret-free environment and a PEP 578 audit hook. The hook refuses:
- reads outside the organ's staged directory and the Python installation;
- all writes;
- directory listing elsewhere;
- sockets;
- subprocesses;
- native code (`ctypes`) and Windows process handles (`_winapi`);
- registry access;
- introspection that could reach the guard itself (`gc.get_objects` and similar), crafted code objects, and tracing hooks;
- sub-interpreters, because Python-level audit hooks are per interpreter.

The host kills an organ that exceeds its wall clock, writes more than 16 MB to stderr, or sends a protocol line over 8 MB. Lines are read with a bound, so a missing newline cannot exhaust host memory.

**OS limits under the hook** (`oslimits.py`). On Windows each organ process runs in a Job Object: one active process (no children) and a memory cap (2 GB by default). Closing the job kills it. On POSIX, `setrlimit` caps the address space and the file size and forbids new processes. These limits hold even for code that bypasses the audit hook. `run_organ` records which ones applied (`os_limits`).

**Limits of this design.** For file and network access, PEP 578 audit hooks are defense in depth, not a security boundary: code written specifically to escape an interpreter-level guard may find a route the tests do not cover. Code you do not trust, including generations imported from strangers, belongs in an OS-level sandbox such as a container or a VM.

Everything else goes through the cockpit, as JSON lines over the original stdio:

| Affordance | Meaning | Charged to |
|---|---|---|
| `ask(packet, schema, purpose, system=None)` | One model call through the router | call budget (even if the answer is unusable) |
| `run_signal(files, trace=False)` | The object's public tests with file overrides; optional executed-line trace | signal-run budget |
| `budget()` | Remaining calls, runs and seconds | — |
| `log(stage, **data)` | A telemetry mark; `reads=[...]` tells the diagnosis what was inspected | — |
| `recall(query, k)` | Memory retrieval, when granted | — |

**The envelope** (`opportunity.Envelope`) is kernel-owned: max calls, max tokens per call, max signal runs, max request bytes and wall-clock seconds. Its purpose is to make improvement mean *better use of the same resources*.

**Failure classes.** Transport failures are retried with backoff by the kernel. They never reach the organ, and if retries run out, the opportunity is *censored*: excluded from scoring. Output failures (truncated, schema failure, invalid JSON) reach the organ and are charged as one call.

## 4. Objects and public signals

A code object is a repository observed through its tests. The kernel keeps a private work copy. It applies an organ's file overrides and runs the named failing tests with `-x -q -p no:cacheprovider`. It returns pass/fail and sanitized `FAILED`/`E` lines, which never quote source files. Optionally it also returns the lines the tests executed, from a `sys.settrace` pytest plugin.

The judge that decides whether a repair really worked is a separate, held-out evaluation, for example the full test files. The organ never sees it.

**Finding work without touching it.** `discover` and `envmap --probe` run an object's own tests on a throwaway copy, with no bytecode writes, so Runesmith never writes into an object it inspects. Each failing test file becomes an opportunity. Failures no source edit can fix (a missing third-party module, a network dependency) are triaged as `environment`. The loop skips them without spending a call and records the skip in the ledger.

## 5. Kaizen: the self-improvement loop

```
opportunities -> telemetry (calls, runs, marks, statuses, cycle time)
      -> diagnose: value stream + failure families (+ matured references when available)
      -> rank_targets (declared rule): largest lost-opportunity family >= 10%, else largest stage
      -> author packet: contract, envelope, target, experience records, organ source, past attempts (with diffs),
                        affordance audit (kernel affordances the organ never uses)
      -> model proposes: hypotheses, mechanism, prediction, falsifier, edits
      -> qualify: static check -> confined smoke test -> development replay (real instrument, held-out judge)
      -> keep-best -> noise-aware freeze bar (gain > the incumbent's own replay spread) -> frozen candidate (not active)
      -> online trial on live work (seeded assignment, sequential exact test) -> CAS activation, or rejection
```

**Affordance audit** (`kaizen/affordances.py`). A static scan of the incumbent organ lists which kernel affordances it never calls, for example `run_signal(trace=True)` (the lines the failing tests execute), `recall` (Runesmith's own memory), `budget`, or a system message. The author sees these as untried mechanism classes, and the self-map and report list them as improvement options. The scan never claims an affordance is used when it is not. This came from SR5. Its author spent all seven attempts on variants of one navigation fallback, while the organ had never used the execution trace that locates the defect.

**Attention** (`kaizen/attention.py`) decides when to spend opportunities on the subject:
- a standing 15% share while healthy;
- 25% when a failure signature recurs (suspected blockage);
- 40% when it keeps recurring (blocked);
- 20% while recovering.

**Drift.** Attention also watches for drift: yield sliding although no single failure recurs. A Bernoulli CUSUM against Runesmith's own baseline yield (the Wilson lower bound of its first 30 outcomes) moves attention to blocked when the evidence for "yield has halved" reaches the threshold. The simulated operating characteristics are in `docs/simulations/drift_cusum.py`. Attention state persists in `ATTENTION.json`.

Credit carries remainders, so shares are met exactly. Credit is capped while self-work is unavailable, so object work is never starved by a backlog. These are commissioning defaults from the Astra subject-cognition architecture (§5), not tuned optima.

## 5b. Online trials: how a candidate earns activation

`kaizen/trial.py` runs a trial whenever the run loop freezes a candidate.

- **Assignment.** Each new object opportunity goes to the incumbent or the candidate by HMAC of its key, a seeded coin that nobody can steer.
- **Looks.** Every `look_every` completed opportunities per arm, a one-sided Fisher exact test compares strict successes. The significance level is split evenly across the maximum number of looks (Bonferroni spending), so repeated peeking cannot inflate false activation.
- **Outcomes.**
  - **Activate** by compare-and-swap if the candidate is better at the look's level.
  - **Reject** if it is worse, or if the maximum sample passes without evidence. There is never a default promotion.
- **Records.** Every look is written to the trial file and the ledger.
- **One at a time.** No new campaign runs while a trial is open, so candidates never stack.

## 6. Maps

- **SELF_MAP.json** (`selfmap.py`) records:
  - identity and kernel digest;
  - components by region, with purpose, public symbols and digest;
  - affordances and the default envelope;
  - capability ladders with measured values in bands (bad / minimal / optimal / world-class);
  - open Kaizen targets, improvement options (unused affordances per organ) and lineage;
  - explicit unknowns.
- **ENVIRONMENT.json** (`envmap.py`) records:
  - the objects found in a workspace and their kinds;
  - proposed objectives with bands;
  - a build ladder with the next rung;
  - optional probes, meaning running the object's tests on a throwaway copy;
  - for document collections, internal Markdown link integrity, read statically;
  - explicit unknowns.

Both maps are deterministic projections of bytes and records. Rebuilding them gives the same digest. "Optimal" is an owner-chosen strong target, not a proven optimum. "World-class" requires external evidence and starts unknown (§8.19.2).

## 7. Generations

A generation is a frozen copy of the organ surface. Its manifest records:
- organ digests;
- the kernel digest;
- the parent;
- provenance: the lineage class, the author model, and the mechanism, prediction and falsifier.

`verify` recomputes the digests. `activate` is compare-and-swap on the `ACTIVE` pointer. Generations are never edited, so a failed successor always leaves its parent intact (§8.19.1: the frozen subject capsule).

- **Requalification.** A Runesmith update changes the kernel digest. `requalify` re-freezes the same organ files under the new kernel after the static check and a confined smoke test.
- **Sharing.** `export` packs a generation into a zip. `import` refuses:
  - any archive member outside the organ surface;
  - digest mismatches;
  - forbidden imports;
  - a failed smoke test.
  An accepted import is frozen inactive and must win an online trial on the receiver's own work.

## 7b. The Studio: the owner's side of the glass

`runesmith/app` is the local app, Runesmith Studio. It is an interface, not kernel:
- it never runs an organ;
- it is left out of the kernel digest, so updating it does not force requalification;
- the self-map shows it as its own region.

It has four layers, each a thin shell over the one below.

- **`workspace.Workspace`** is the service. It wraps one folder and its home (settings, goals, brief, plan, inference, maps, proposals, drafts, notes, library, activity). Every rule that protects the owner lives here:
  - apply only when every file is unchanged since the fix was made;
  - keep a backup and preserve line endings;
  - undo exactly;
  - refuse draft paths outside the folder or inside the home;
  - never return a saved key.
- **`worker.Worker`** is one background thread per workspace. It runs jobs one at a time: `map`, `round`, `plan`, `draft`, `health`.
  - A round:
    1. maps;
    2. discovers opportunities on throwaway copies;
    3. adds the owner's open notes to each issue;
    4. serves the opportunities through `loop.run_loop` (with `owner_notes` for the Kaizen author);
    5. writes `WORK.json` and the report.
  - Events go to an in-memory bus that the page reads as server-sent events.
- **`planner`** is the owner-facing counterpart of Kaizen, for folders with nothing to repair.
  - It builds a plan (tracks, milestones, first steps, questions for the owner) from the brief, the chosen blueprints, goals, notes and the map.
  - It drafts first files for a milestone. Drafts are unverified proposals.
  - It uses the `plan` role, or borrows `kaizen`/`repair` instruments.
- **`server`** is `ThreadingHTTPServer` on 127.0.0.1.
  - Token-to-cookie access, a Host check, a custom header for changes, and a strict CSP.
  - A JSON API, SSE, and static files. The page is vanilla JavaScript modules, CSS and SVG with no build step.

**Genesis** (`static/js/genesis.js`) is the first boot and the explainer. On first start it draws the real folder and Runesmith's real kernel. It ends with the owner naming the workspace, and the name, description and use type are stored through `POST /api/genesis`. `/cinema` plays it on demo data.

## 8. What is deliberately not here yet

These are planned only when evidence earns them:
- vector or graph memory;
- simulation and decision twins;
- multi-subject councils;
- activation without evidence. A generation becomes active only through an online trial's sequential test or an explicit operator compare-and-swap.

The blueprint's rule applies: add an arm only after a measured deficit, and keep the simple baseline as the comparator.
