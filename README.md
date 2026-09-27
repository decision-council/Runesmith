# Runesmith

**A model-agnostic runtime that improves the things it works on — and improves itself.**

Runesmith is a small, open system for people who cannot afford frontier-model subscriptions. It is the cockpit, or suit, around whatever model you have: a weak local model, a free hosted tier, a router of many providers, or none at all. What Runesmith learns is kept in evidence-bearing state it owns: tested organs, frozen generations, memories and measured self-knowledge. That state is not locked inside one model, so it carries over when you change models.

> Status: **v0.1.0, research release.** Built alongside the MillinerOS/Runesmith scientific blueprint. Every capability claim below is either *implemented and tested here* or *under experiment*, never assumed. See [Evidence](#evidence).

Python 3.11+ and the standard library only. `pytest` is needed for code objects.

## Runesmith Studio: open it and go

**Double-click** the launcher for your system:

| System | Launcher |
|---|---|
| Windows | `Runesmith.cmd` |
| macOS | `Runesmith.command` |
| Linux | `./runesmith.sh` |

You can also run `python -m runesmith` inside any folder, or `runesmith` if it is installed with `pip install .`.

The Studio opens in your browser. It runs on this computer only, reached through a private link.

The first start is a short opening sequence:
1. Runesmith maps your folder and itself, then shows how it works under guard and how it improves only with evidence.
2. It asks **what you will create**: a name, and a description if you like.
3. It opens the living map of your world.

Drop it into any folder: empty, half-built or full. Give it as much or as little instruction as you like.

- **Living map, in four lenses.**
  - **Environment:** every object in the folder, its health band, and the next rung on its ladder.
  - **Self:** Runesmith's fixed kernel and living organs, its measured capabilities and its lineage.
  - **Development:** tracks for your goals, the plan, every object's ladder, and Runesmith's own generations.
  - **Operations:** the live work loop, which model does what, attention, trials and the schedule.
- **Thinking power, from none to a lot.**
  - Models on this computer (Ollama, LM Studio, llama.cpp), found automatically.
  - API keys for OpenRouter, Groq, Gemini, Mistral, DeepSeek, OpenAI, Anthropic, Together or any OpenAI-compatible endpoint. Keys are saved on this computer and never shown again.
  - A **chat window you copy and paste into**, with no key at all.
  - Each model gets roles: **Worker** repairs code, **Improver** improves Runesmith itself, **Planner** drafts plans and first files.
- **Goals, brief and plan.** Write goals and a brief, and pick blueprint documents from the folder. The Planner drafts milestones on named tracks, and can draft the first files for any milestone.
- **Work & proposals.** Fixes accepted by a held-out judge, and model-written drafts labelled unverified. Nothing touches your files until you click Apply. Every apply is conflict-checked, backed up and undoable.
- **Comment on anything, anywhere.** Press <kbd>C</kbd> and click anything: an object, a rung, a fix, a model, Runesmith itself. Open notes travel to the model that works on that thing, labelled as your guidance.
- **Self-improvement you can watch.** Generations, online trials, and a library with **C7**, the generation proven in SR7. It becomes active only if it wins a trial on your own work.
- **Activity** in two views: a live log, and a hash-chained ledger you can verify with one click.

The same opening sequence plays full screen at `/cinema`, looping on demo data, ready to share or record.

See [docs/STUDIO.md](docs/STUDIO.md) for the full guide.

## Try it in a minute (command line)

```bash
python -m runesmith --home .runesmith demo
```

The demo writes a tiny shop workspace with three slips, then:
1. maps the workspace (tests passing 0.25, band *bad*);
2. discovers the three failing tests;
3. serves them through the run loop;
4. applies each repair the held-out judge accepts;
5. maps the workspace again (1.0, band *optimal*; the next rung moves on);
6. writes `REPORT.md`.

Offline, a clearly labelled scripted stand-in plays the model, so the demo shows the machinery, not model skill. Once a model is configured, `demo --live` makes the repairs real.

To watch Runesmith **improve itself**, in a few minutes and offline:

```bash
python -m runesmith --home .runesmith demo --kaizen
```

The shipped organ struggles: a scripted weak model keeps breaking its navigation answers, and it gives up. Kaizen diagnoses the failure from Runesmith's own telemetry. The author's answer is replayed: the change a free model actually wrote for this target in the SR5 study. The change is qualified on held-out replays and frozen, then wins an online trial and is activated by compare-and-swap. The whole story is in the ledger and `REPORT.md`.
The demo shows the machinery. It does not show that the change helps. In SR5's preregistered confirmation on large repositories, that same change was **not shown** to help: its fallback rescued 0 of 26 navigation failures there. See [Evidence](#evidence).

## What it does

- **Maps where it is.** Lowered into a workspace, it inventories the objects it finds (`envmap`). For each object it proposes objectives and places measured metrics in bands: **bad / minimal / optimal / world-class**. It lays out a build ladder of ordered rungs, for example source → tests → green → fast → coverage → mutation-tested, and names the next rung. Anything it has not measured is `unknown`, not guessed.
- **Maps itself.** `selfmap` writes `SELF_MAP.json`: its components, its fixed kernel and mutable organs, the affordances it grants, its measured capabilities in the same bands, its lineage, what it could try next, and what it does not know about itself.
- **Improves objects.** The repair organ fixes failing code within a fixed resource envelope, using the object's own tests as its public signal. Fixes become **proposals** for you to review; Runesmith never edits your objects itself.
- **Improves itself (Kaizen, always).** The Kaizen engine reads Runesmith's own telemetry, finds where time goes and where work fails, ranks improvement targets by a declared rule, and asks a model to rewrite the organ that owns the top target. A change is kept only if it does better on held-out replays, and it is activated only if it then wins an **online trial** on live work. Self-improvement always has a standing share of attention. The share rises when Runesmith struggles: a failure recurs, or its yield drifts down.
- **Shares what it learned.** A generation of improved organs can be exported and imported between people. Every import must win a trial on the receiver's own work.
- **Stays honest.** An append-only, hash-chained ledger records every decision. Generations are frozen and digest-bound. Activation is compare-and-swap, and rollback is one pointer move.

## Set it up with your model

```bash
python -m runesmith --home .runesmith init
```

Edit `.runesmith/runesmith.json` to point at any OpenAI-compatible endpoint, for example Ollama on your own machine:

```json
{"instruments": {"local": {"kind": "openai", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5-coder:7b"}},
 "roles": {"repair": ["local"], "kaizen": ["local"]}}
```

Free hosted tiers work the same way. `api_key_env` names the environment variable that holds your key, and keys are never stored. See the `examples` block written by `init`, and [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md) for running on your own small model.

**No API key for a strong model? Use a chat window.** Self-improvement needs a strong *author* only a few times per campaign, and the generation it produces then runs on your everyday model. Give the `kaizen` role a `manual` instrument. Runesmith then writes each author request to a file, you paste it into any chat model you can reach (free tiers work), and you hand the reply back with `runesmith manual answer --clipboard`. See [docs/CHAT_AUTHOR.md](docs/CHAT_AUTHOR.md).

Check the setup at any time. `doctor` reports on Python, pytest, the home, the ledger chain, the active generation and each instrument (key present, endpoint reachable), and says how to fix each problem:

```bash
python -m runesmith --home .runesmith doctor
```

After you update Runesmith, the kernel changes, and the active generation must be re-qualified under it. `generations requalify` re-freezes the same organs after a static check and a confined smoke test.

## Everyday use

**Let it look after a workspace:**

```bash
python -m runesmith --home .runesmith steward path/to/workspace --rounds 24 --interval 3600 --exclude LiveService
```

Each steward round:
- maps the workspace;
- discovers failing tests in every Python object, on throwaway copies, so nothing is written into your repositories;
- serves only work it has not already served for the same source state;
- interleaves Kaizen steps and trials;
- writes `REPORT.md` and patch proposals.

`--exclude` names objects it must never probe. So does the `steward.exclude` list in `runesmith.json`.

**Review what it fixed:**

```bash
python -m runesmith --home .runesmith proposals --write proposals/
```

Each `proposals/<key>.patch` is a repair the held-out judge accepted. It applies from the repository root with `git apply`. If the repository has changed since, `git apply` refuses rather than guessing.

**See how it is doing:**

```bash
python -m runesmith --home .runesmith report
```

`REPORT.md` shows:
- the generation lineage;
- each capability in bands;
- yield and cycle time per generation and per model;
- where it struggles;
- the affordances its organs leave unused;
- the trials and recent work.

It is rebuilt only from the home's own records, so the same home always gives the same report.

**Work on one repository by hand:**

```bash
python -m runesmith --home .runesmith discover path/to/repo
```

```bash
python -m runesmith --home .runesmith run
```

`discover` turns each failing test file into a repair opportunity, and `run` serves them with Kaizen interleaved. Failures that no source edit can fix are triaged as `environment` and skipped without spending a model call: a missing third-party module, or a test that needs the network. `repair --repo … --test … --issue …` runs a single opportunity. It prints the diff, and it changes your repository only with `--apply` and only if the judge tests pass.

## How it improves itself

Every finished opportunity becomes replayable experience. A Kaizen step works like this:

1. **Diagnose.** It builds a value stream and failure families from Runesmith's own telemetry, then picks the target by a declared rule: the largest lost-opportunity family, or else the slowest stage.
2. **Author.** A model gets the organ contract, the envelope, the target, examples from one half of the experience, the organ's source and every earlier attempt with its diff and result. It also gets an **affordance audit**: the kernel abilities the organ never uses, such as the execution trace, memory recall or the budget, offered as untried mechanism classes.
3. **Qualify.** The candidate must pass a static check (allowed imports only), a confined smoke test, and replays on the *other* half of the experience, whose answers the author never saw. The incumbent is replayed twice on that half. A candidate is frozen only if its gain is larger than the incumbent's own replay-to-replay difference, a rule learned from SR5's negative result.
4. **Freeze, then trial.** A winning candidate is frozen but not activated. New live opportunities are split between it and the incumbent by a seeded coin. A pre-declared sequential exact test then activates it by compare-and-swap, or rejects it. `runesmith trial` shows the evidence.

**Attention** decides how often Kaizen runs. There is a standing 15% share. It rises to 25–40% while a failure signature recurs, or when a statistical process control chart (a Bernoulli CUSUM against Runesmith's own baseline yield) detects a downward drift. Attention state persists across runs.

`runesmith kaizen --tasks my_dev_tasks.json` runs one campaign on a task set you provide. Its candidate is frozen, not activated. You activate it yourself after it proves itself on fresh tasks, or you let a trial decide:

```bash
python -m runesmith --home .runesmith generations activate <id> --expected <current-id>
```

## Sharing what your Runesmith learned

```bash
python -m runesmith --home .runesmith generations export <id> --to my-generation.zip
```

```bash
python -m runesmith --home .runesmith generations import --from their-generation.zip
```

The receiver trusts nothing. Before an import can run:
- The archive may contain only a manifest and organ modules.
- Every digest must match.
- Every organ must pass the static check.
- It must pass a confined smoke test.

It is then frozen as an **inactive** generation, and an online trial opens against yours. It becomes active only if it wins on your own work. `runesmith trial --open <id>` starts a trial for any frozen generation later.

**Import only from people you trust.** Organs run confined, and an imported organ gets exactly the confinement your own organs get. That confinement is a Python audit hook in an isolated interpreter, with host-side limits. It stops careless or buggy code and every escape route we test for, but Python audit hooks are not a hardened security boundary (PEP 578). For generations from strangers, run Runesmith inside an OS-level sandbox, such as a container or a virtual machine.

## The shape: a fixed kernel and mutable organs

```
fixed kernel                                   mutable organs (rewritable by Kaizen)
  identity, ledger, generations                  repair.py  - how to repair code
  instrument router + transport retries          ... future organs: memory use, tools,
  resource envelope (calls, tokens, runs, time)      summarization, planning
  public signals of objects (tests, traces)
  confinement: organs run in an isolated         each organ: run(view, cockpit) -> result
  process with no files, network or secrets      cockpit.ask / run_signal / budget / log / recall
```

An organ can change **how** it spends its envelope, never **how much** it gets. That is what makes self-improvement measurable: the successor must do better under the same ceiling. An organ cannot read the judge, the ledger, your secrets or the network. It sees only what the kernel grants it. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/VISION.md](docs/VISION.md) for how each part maps to the project's vision and scientific blueprint.

## Evidence

Runesmith is developed as a falsifiable research program. A capability is claimed only when a preregistered experiment measures it:

| Claim | Status |
|---|---|
| Kernel integrity: hash-chained ledger, tamper detection, generation verification and CAS activation | Implemented; unit-tested (`tests/test_kernel.py`) |
| Organ confinement: no reads outside the organ, writes, sockets, subprocesses, directory listing, environment secrets, native code, process handles, guard introspection or sub-interpreters; stderr and message floods cut off | Implemented; unit-tested against each escape. Not a hardened boundary (PEP 578 audit hooks); see Safety |
| Envelope enforcement: call, run and request-size ceilings; transport censoring is never scored | Implemented; unit-tested |
| Non-invasive probing: discovery and probes never write into an object | Implemented; tested byte for byte |
| Imports cannot escalate: traversal, tampering and forbidden imports are refused; activation only by trial | Implemented; unit-tested (`tests/test_share.py`) |
| The repair organ g0 reproduces Runesmith v1 (the SR3/SR4 comparator) | Port with disclosed differences; see SR5 protocol |
| **A Kaizen-selected, model-authored organ change makes Runesmith repair more fresh tasks** | **Shown in SR7-FRONTIER** (preregistered, sealed 2026-09-25). Generation C7, written by a frontier author inside Runesmith's own Kaizen loop, repaired **57 of 162** attempts (54 fresh tasks, 3 rounds each) against its predecessor's **35 of 162**: +13.6 points, p = 0.00085, with no more errors or false claims, and about half the time per successful repair. One of C7's ranking steps (module paths in the error text) only recognises the package names of its two development repositories, so it never fires elsewhere; which steps carried the gain is untested. The repair model was a cheap free-class one (gpt-oss-20b). Earlier attempts are reported alongside: SR5 was not shown (36 vs 50 of 180 and 58 vs 60 of 138), and SR6, with a free-class author, closed before confirmation |
| **Weak-model amplification: a 2.6B free model repairs more inside the suit than in its strongest fixed scaffold** | **Not shown: SR6-W returned NULL** (sealed 2026-09-25). With the 2.6B model, g0 repaired 5 of 68 fresh tasks and a deterministic-retrieval scaffold at the same budget 12 of 68. The mirrored test's p = 0.033 is above the declared 0.025. C7 was not tested with this model |
| Model-succession retention; cumulative generations | Not yet shown. SR6 (free-class author) closed before confirmation. SR7 (frontier-class author) passed once; it is not replicated, and no later generation has been shown to improve on C7 |

The experiments, their preregistrations and receipts live in the MillinerOS research repository, and the scientific blueprint states the claim discipline. The negative results count as much as the positive ones.

## Safety model

- Two operator laws precede everything: do not harm humans, and obey the authenticated operator except where that conflicts with the first law.
- Self-modification is bounded to organs. The kernel, meaning budgets, authority, judges and the ledger, is outside the reach of any organ and of the Kaizen engine.
- A new generation is activated only by an explicit operator compare-and-swap, or by an online trial's pre-declared sequential test on fresh work. Development evidence alone never activates it, and rollback is one pointer move.
- Runesmith never edits the objects it inspects. Tests run on throwaway copies, fixes become proposals, and excluded objects are never probed.
- Organs see no secrets. Instruments read secrets on demand from environment variables that you name.
- **What confinement is.** An isolated interpreter with a secret-free environment, and a PEP 578 audit hook. The hook refuses:
  - reads outside the organ and the Python installation, and all writes;
  - the network and subprocesses;
  - native code, process handles and introspection of the guard itself;
  - sub-interpreters.
  The host also enforces the wall clock, a stderr cap and a protocol-message cap.
- **Under the hook, the operating system enforces two limits** that hold even against code that gets past the hook:
  - no child processes and a memory cap, through a Job Object on Windows;
  - `setrlimit` on POSIX: address space, no new processes, file size.
  File and network access still rest on the audit hook. That is defense in depth, not a proof against deliberate attack: PEP 578 states that audit hooks are not a sandbox. Use an OS-level sandbox, such as a container or a VM, for code you do not trust.

## Commands

| Command | What it does |
|---|---|
| `demo [--live \| --kaizen [--manual-author]]` | The whole loop in about a minute; `--kaizen` shows self-improvement end to end, with your own chat model as the author if you like |
| `init` / `status` | Create a home (config, ledger, generation g0) / show its state |
| `doctor [--offline]` | Check Python, pytest, the home, the instruments and disk; says how to fix each problem |
| `envmap WORKSPACE [--probe]` | Objects, objectives in bands, build ladders, unknowns → `ENVIRONMENT.json` |
| `selfmap` | Runesmith's map of itself → `SELF_MAP.json` |
| `steward WORKSPACE` | Rounds of map → discover → serve new work → Kaizen → report and proposals |
| `discover REPO` / `run` / `repair` | Find opportunities in one repository / serve them with Kaizen / run one by hand |
| `proposals [--write DIR]` | Judge-accepted fixes as patches for review |
| `report` | The one-page dashboard → `REPORT.md` |
| `diagnose` / `kaizen --tasks FILE` | Rank Kaizen targets / run one campaign on your own tasks |
| `trial [--open ID]` | Show the online trial, or open one for a frozen generation |
| `generations list/verify/activate/requalify/export/import` | Manage, re-qualify after an update, share and adopt generations |
| `manual list/show/answer` | Requests waiting for a chat model that you relay by hand ([docs/CHAT_AUTHOR.md](docs/CHAT_AUTHOR.md)) |
| `ledger` | Verify the hash chain |

## License

To be chosen by the project owner before public release.
