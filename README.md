# Runesmith

**A non-traditional model that turns the AI model you already have into a builder of real software.**

[Quick start](#quick-start-in-60-seconds) · [What the Studio does](#what-the-studio-does) · [The paper](#the-paper) · [The guide](#the-guide) · [License](#license) · [Contributing](#contributing) · [Reference](#reference-the-command-line-and-the-internals)

## What Runesmith is

Runesmith is a *non-traditional model*. It has no weights of its own. It is a system that wraps a model and makes that model useful for building software, whichever model you have:

- **free**: Google AI Studio, NVIDIA;
- **paid**: Anthropic, OpenAI;
- **on your own computer**: Ollama, LM Studio.

Around that model, Runesmith:

- **plans** milestones from your goals and your brief;
- has the model **write the code**, one milestone at a time;
- **checks every step** against acceptance checks that are written in plain words for you to read and approve, and runs them on a throwaway copy of your project;
- **builds and improves software on its own**, round after round, once you have said how much freedom it has. Nothing is written to your files until you apply it, or until you have allowed automatic apply for checked builds, in folders you name.

In our own out-of-the-box journeys, free models built **Runesmith Motion** this way: a browser animation and video studio, grown milestone by milestone from a short brief. It is a real application, and at the time of writing it is still being built. The operator who approved its checks stepped in often, and the paper says plainly what worked, what broke and what it took to fix.

Runesmith can also **improve its own system.** It reads its own records, finds where it struggles, asks a model to rewrite the part responsible, and keeps the change only if it does better on work its author never saw, and then wins a live trial on your own work. That is a nudge in the direction of recursive self-improvement, and only a nudge: one such change has been shown to help in a sealed experiment, and cumulative improvement has not been shown (see [Evidence](#evidence)).

What Runesmith learns is kept in records it owns (a hash-chained ledger, frozen generations, maps and memories), not inside any one model.

> **Status: v0.1.0, a research release.** Every capability claim here is either implemented and tested, backed by a named experiment, or marked as not shown.

**What to expect.**

- Results depend on the model. Larger models plan and write better. Small models do best on small, checked steps. We have no minimum model size to promise you.
- Free tiers have rate limits. When a model is busy or at its limit, a round waits or moves on to the next model you listed.
- With a hosted model, your goals and your project's code are sent to the provider you chose. With a model on your own computer, nothing leaves it. Read your provider's terms.
- Checking a build runs your project's own code, on a throwaway copy of the folder. The copy is not a security boundary, so use it on code you trust.

## Quick start in 60 seconds

You need **Python 3.11 or newer** and a web browser. There is nothing else to install: Runesmith uses only the Python standard library.

### 1. Get it

On this page, click **Code → Download ZIP** and unzip it, or clone the repository with Git.

### 2. Start the Studio

| System | How |
|---|---|
| **Windows** | Double-click `Runesmith.cmd`. If Python is missing, it opens the download page; tick "Add python.exe to PATH" in the installer. |
| **macOS** | In Terminal, in the Runesmith folder: `sh Runesmith.command` |
| **Linux** | In a terminal, in the Runesmith folder: `sh runesmith.sh` |

Your browser opens Runesmith Studio. It runs on this computer only, through a private link. If the browser does not open, copy the link printed in the launcher window. Keep that window open while you work. Close it, or press <kbd>Ctrl</kbd>+<kbd>C</kbd>, to stop.

The launchers open the folder you used last time, or a new `My first project` folder under `~/Runesmith`. To work in a folder of your own:

- **Windows:** drop the folder onto `Runesmith.cmd`.
- **macOS and Linux:** `sh runesmith.sh path/to/folder`
- **Any system, from the Runesmith folder:** `python -m runesmith up path/to/folder` (`python3` on macOS and Linux).
- **Installed:** run `pip install .` once, inside a virtual environment if your system asks for one. Then run `runesmith` inside any folder.

To double-click on macOS or Linux instead, first make the launcher executable: `chmod +x Runesmith.command runesmith.sh`.

### 3. Name what you build

The first start plays a short opening you can skip. Then Runesmith asks **What will you create?** Give it a name. A description is optional. Choose the kind of work: *Build something new*, *Improve my code*, *Tend my documents*, *Keep an eye on my numbers* or *Just explore*. You can change all of it later.

### 4. Give it a model (Thinking power)

Until you add a model, Runesmith can map your folder and watch it, but it cannot plan or build. Open **Thinking power** in the left menu (or press <kbd>6</kbd>) and click **Add thinking power**.

**A free key from Google AI Studio or NVIDIA**

1. Under **With a key**, choose **Google Gemini** (the free tier of Google AI Studio) or **NVIDIA** (many models with a free endpoint, among them Nemotron and Kimi).
2. Click **Get a key**. It opens [aistudio.google.com/apikey](https://aistudio.google.com/apikey) or [build.nvidia.com/models](https://build.nvidia.com/models). Make a key and paste it into Runesmith.
3. Paste your key and Runesmith asks the provider which models it serves today, then fills in a recommended one (for Gemini, the newest flash model) and offers a few others as buttons. Keep it, or type another. **List models** asks again. If a provider ever answers that a model is no longer available and names its replacement, Runesmith shows that as a button; it never switches silently.
4. Leave the roles ticked and click **Save and test**. One tiny call confirms that the model answers.

Add both if you like. Under **Who does what**, the first model in each role is preferred and the others are fallbacks.

Your key is saved in a file in Runesmith's own `.runesmith` folder inside your project folder. It is never shown again, and it is sent only to the provider it belongs to. The file is not encrypted: it relies on your account's file permissions. The `.runesmith` folder ignores itself for version control, so it is not committed by accident.

**A model on your own computer (Ollama, LM Studio, llama.cpp)**

- **Ollama:** install it from [ollama.com](https://ollama.com), then `ollama pull qwen2.5-coder:7b`.
- **LM Studio:** load a model with a context length of at least 16384 tokens, then **Developer: Start Server**.
- **llama.cpp:** `llama-server -m model.gguf --ctx-size 16384`

With a server running, Thinking power shows it under **On this computer**. Click **Use it**. Free, private, and nothing leaves your computer.

**No key at all**

Choose **A chat window (copy and paste)** under **No key needed**. Runesmith shows each request. You paste it into any chat model you can reach and paste the reply back. It suits roles that need only a few calls, such as the Checker, the Improver and drafting a plan. Every call waits for you, so it is not unattended work.

**The roles.** The **Worker** repairs code. The **Planner** drafts plans and first files and writes the builds. The **Checker** proposes acceptance checks and follows the Planner's model unless you pick another. The **Improver** improves Runesmith itself.

### 5. Plan and build

Open **Goals & plan** (<kbd>4</kbd>). Write a goal, add a brief if you like, and click **Draft a plan**. Then use **Draft first files** on a milestone, or **Build next step** in the Build continuation card. Drafts wait in **Work & proposals → Drafts** for you to read, and nothing is written to your files until you click **Write these files**.

Check your setup at any time with **Settings → Health**, or `python -m runesmith doctor`. To repair existing Python projects, and to run the command-line demo, also install pytest: `python -m pip install pytest`. The Studio builds and checks projects without it.

## What the Studio does

Runesmith Studio is a web app that Runesmith serves on your own computer. It listens on `127.0.0.1` only. Everything below can be done in it, without a terminal. The [Studio guide](docs/STUDIO.md) covers every page.

**Goals, brief and plan** (Goals & plan). Write your goals in your own words and a brief as long as you like. Tick any documents in the folder that the Planner should read (`.md`, `.txt`, `.rst`). Only the ones you tick go to a model. **Draft a plan** and the Planner writes milestones on named tracks, each with a "done when", plus first steps and the questions only you can answer. Edit anything. On each milestone you can **Draft first files**, **Propose smaller steps** when it is too big, or **Check current files** against it.

**Checks: what "done" means.** **Propose acceptance checks** asks the Checker to write small black-box tests from the milestone's own words, with one plain sentence for each. You read the sentences (the code is one click away) and choose **Use these checks** or **Discard**. Runesmith first tries them on a throwaway copy of your project and warns you when they already pass or cannot run. Builders are told the sentences and never the code. If a correct build fails its checks, the checks may be wrong: **Ask for new checks**, **Replace my checks** or **Withdraw these checks**, each with a reason that is kept. The Checker is a role of its own because a few calls decide what "done" means, so your best model pays off there.

**Building and applying** (Build continuation). **Build next step** asks the Planner's model to write the next ready milestone. With **Check drafts on a throwaway copy** on, a draft must pass your project's own tests, if it has any, and your acceptance checks. You read the draft under **Work & proposals → Drafts**, then **Write these files**, **Reject** it with a reason, or **Undo** it later. Every write is conflict-checked against the files as they are now, backed up and undoable. With **Apply checked drafts automatically** on, Runesmith applies a draft itself, but only when your acceptance checks for that milestone pass, the source has not changed, and the files lie inside the files or folders you named.

**Fixes for code that already exists.** When a round finds failing tests in a Python project, Runesmith attempts a repair on a private copy. A held-out judge must accept it before it reaches you as a **Fix**, which you can **Apply to my files** or **Reject**. See [Limits worth knowing](docs/STUDIO.md#limits-worth-knowing) for the layouts it can repair today.

**Check autopilot** (optional, off by default). Runesmith asks for acceptance checks for ready milestones and approves them itself, but only when they pass every gate: tried on your project, no problem found by Runesmith's own automatic review of them, and a second model working out the same expected values. Otherwise it turns them down with the reason, asks again at most twice, and then leaves them for you. It never replaces checks you approved. The paper records autopilot approvals that turned out wrong, and each one led to a new gate, so read the checks it approves and withdraw any that are wrong.

**Running on its own.** Nothing runs on its own until you choose it.

- **Settings → Rhythm.** **Work on a schedule** runs a round every few minutes while the Studio is open: map, find work, build, check, report. **Full speed** starts the next step as soon as one ends.
- **Settings → Running on its own.** Three choices decide what happens when something goes wrong. After an interrupted job: wait for you, or keep and continue. When a milestone's three tries are used up: wait for you, give it one more try, or one more try and then break it into smaller steps. When a draft's checks did not finish: wait for you, or recheck once. Each is said on the Overview when Runesmith acts on it. When a milestone is stuck and nothing more is left to try by itself, the Overview shows a **Needs you** card (and RUNESMITH.md a line): what is stuck and why, and your choices: ask for smaller steps, edit the milestone, or set it aside.
- **Pause** stops all work, and **Run now** (<kbd>R</kbd>) runs one round immediately.

Honest note: in our longest journey, the operator still had to step in. At one point the work sat idle for about two days until the operator noticed, and the interrupted, stuck and unfinished-check policies exist because of what that run taught us. Read the paper before you leave Runesmith alone for days.

**Seeing what is going on.**

- **Overview:** where things stand and the one thing to do next.
- **Living map:** your folder and Runesmith itself in four lenses, *Environment*, *Self*, *Development* and *Operations*.
- **Activity:** the live log, and a hash-chained ledger you can verify with one click.
- **Dashboards:** read-only dashboards, one per tracked project.
- **Modes & measurements:** choose what Runesmith works on (Map & Plan, Build, Troubleshoot, Optimize, Operations), and numbers to watch from CSV or JSON reports.

**Self-improvement you can watch.** Generations, online trials, Kaizen campaigns, and a library with **C7**, the generation proven in SR7. Adopting it starts a trial against your active generation. It becomes active only if it wins on your own work. In the Studio, self-improvement is off until you switch it on under Settings.

**Comment on anything.** Press <kbd>C</kbd> and click anything: an object, a milestone, a fix, a model, Runesmith itself. Open notes travel to the model that works on that thing, labelled as your guidance.

**Other keys.** <kbd>Ctrl</kbd>+<kbd>K</kbd> opens the command palette, <kbd>1</kbd> to <kbd>9</kbd> go to a page, and <kbd>?</kbd> lists the shortcuts. The opening sequence also plays full screen at `/cinema`.

## The paper

*Beyond the Model: The Instrument–Substrate Hypothesis and a Falsifiable Runtime for Persistent Adaptive Intelligence*, by Lars O. Horpestad, is the scientific paper behind Runesmith. It argues that a model is an instrument and that some of what a system learns can live outside it, in state the system owns. It describes the runtime built to test that, and it reports the experiments, the ones that did not work with the same weight as the ones that did.

**[Read the paper](PAPER_URL)**

## The guide

A step-by-step guide to using Runesmith, from the first start to a finished project.

**[Read the guide](GUIDE_URL)**

The Studio is also documented page by page in [docs/STUDIO.md](docs/STUDIO.md).

## License

Runesmith is released by **AI ThinkLab** under the [Apache License 2.0](LICENSE). The copyright line is in [NOTICE](NOTICE): Copyright 2026 AI ThinkLab. You may use, change and share Runesmith, commercially too, under the terms in `LICENSE`. If you redistribute it, keep the `LICENSE` and `NOTICE` files with it.

## Contributing

Contributions are welcome: bug reports, fixes, documentation, new object kinds, and results that disagree with ours.

- **Start with an issue** for anything larger than a small fix, so we can agree on the shape before you spend your time.
- **Set up.** Clone the repository, then `python -m pip install -e ".[dev]"`. This installs pytest.
- **Test.** `python -m pytest` runs the suite. It is large, so while you work, run the file for the area you touched, for example `python -m pytest tests/test_kernel.py`.
- **Every change ships with a test** that fails without it.
- **Keep the runtime dependency-free.** Runesmith runs on Python 3.11 and the standard library alone.
- **Use LF line endings.** The repository's `.gitattributes` enforces them. The one exception is the Windows launcher, `Runesmith.cmd`. Digests of the kernel and the organs are computed over bytes, so line endings matter here.
- **Take care with the kernel.** The kernel is the fixed part: identity, the ledger, generations, instrument routing, budgets and confinement. Organs change through the Kaizen engine, with evidence. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before you change either.
- **Keep claims honest.** A capability is claimed only when a test or a sealed experiment shows it. If you find a claim in this repository that does not trace to one, that is a bug worth reporting. Negative results are welcome.
- **Never commit a home.** `.runesmith/` holds keys and maps of your machine. `.gitignore` already keeps it out.
- **Security.** Please do not post exploit details in a public issue. Open an issue that says you have found a problem, and we will arrange a private way for you to send the details.

Where help is most welcome:

- running the launchers and the Studio on macOS and Linux desktops, and reporting what breaks;
- repairs beyond projects laid out as `src/<package>`, and object kinds beyond Python code and documents;
- OS-level isolation for untrusted organs (AppContainer on Windows, namespaces or seccomp on Linux), and an independent security review;
- replicating SR7, and testing C7 on natural bugs and with other repair models;
- better behaviour with small models: tolerant parsing, smaller schemas, deterministic fallbacks.

---

# Reference: the command line and the internals

The Studio is the front door. Everything below is the engine underneath, and every part of it works from the command line. The global option `--home` comes before the command: `python -m runesmith --home .runesmith <command>`. The default home is `./.runesmith`.

## Try it in a minute (command line)

```bash
python -m runesmith --home .runesmith demo
```

The demo needs pytest (`python -m pip install pytest`). It writes a tiny shop workspace with three slips, then:

1. maps the workspace (tests passing 0.25, band *bad*);
2. discovers the three failing tests;
3. serves them through the run loop;
4. applies each repair the held-out judge accepts, to the demo's own workspace only;
5. maps the workspace again (1.0, band *optimal*; the next rung moves on);
6. writes `REPORT.md`.

Offline, a clearly labelled scripted stand-in plays the model, so the demo shows the machinery, not model skill. Once a model is configured, `demo --live` makes the repairs real.

To watch Runesmith **improve itself**, in a few minutes and offline:

```bash
python -m runesmith --home .runesmith demo --kaizen
```

The shipped organ struggles: a scripted weak model keeps breaking its navigation answers, and it gives up. Kaizen diagnoses the failure from Runesmith's own telemetry. The author's answer is replayed: the change a free model actually wrote for this target in the SR5 study. The change is qualified on held-out replays and frozen, then wins an online trial and is activated by compare-and-swap. The whole story is in the ledger and `REPORT.md`.
The demo shows the machinery. It does not show that the change helps. In SR5's preregistered confirmation on large repositories, that same change was **not shown** to help: its fallback rescued 0 of 26 navigation failures there. See [Evidence](#evidence).

## What the engine does

- **Maps where it is.** Lowered into a workspace, it inventories the objects it finds (`envmap`). For each object it proposes objectives and places measured metrics in bands: **bad / minimal / optimal / world-class**. It lays out a build ladder of ordered rungs, for example source → tests → green → fast → coverage → mutation-tested, and names the next rung. Anything it has not measured is `unknown`, not guessed.
- **Maps itself.** `selfmap` writes `SELF_MAP.json`: its components, its fixed kernel and mutable organs, the affordances it grants, its measured capabilities in the same bands, its lineage, what it could try next, and what it does not know about itself.
- **Improves objects.** The repair organ fixes failing code within a fixed resource envelope, using the object's own tests as its public signal. On the command line, fixes become **proposals** for you to review. In the Studio, a fix is written to your files only when you click Apply, or when you have allowed automatic apply for checked builds.
- **Improves itself (Kaizen).** The Kaizen engine reads Runesmith's own telemetry, finds where time goes and where work fails, ranks improvement targets by a declared rule, and asks a model to rewrite the organ that owns the top target. A change is kept only if it does better on held-out replays, and it is activated only if it then wins an **online trial** on live work. On the command line, self-improvement always has a standing share of attention, and the share rises when Runesmith struggles: a failure recurs, or its yield drifts down. In the Studio, self-improvement is a setting that stays off until you switch it on.
- **Shares what it learned.** A generation of improved organs can be exported and imported between people. Every import must win a trial on the receiver's own work.
- **Stays honest.** An append-only, hash-chained ledger records every decision. Generations are frozen and digest-bound. Activation is compare-and-swap, and rollback is one pointer move.

## Set it up with your model (command line)

The Studio does this for you under Thinking power. For the command line, create a home:

```bash
python -m runesmith --home .runesmith init
```

Edit `.runesmith/runesmith.json` to point at any OpenAI-compatible endpoint, for example Ollama on your own machine:

```json
{"instruments": {"local": {"kind": "openai", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5-coder:7b"}},
 "roles": {"repair": ["local"], "kaizen": ["local"]}}
```

Free hosted tiers work the same way. `api_key_env` names the environment variable that holds your key, so the configuration file never contains it. For Google's free tier:

```json
{"instruments": {"gemini": {"kind": "openai", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                            "model": "gemini-3.8-flash", "api_key_env": "GEMINI_API_KEY"}},
 "roles": {"repair": ["gemini"], "kaizen": ["gemini"]}}
```

See [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md) for running on your own small model.

**No API key for a strong model? Use a chat window.** Self-improvement needs a strong *author* only a few times per campaign, and the generation it produces then runs on your everyday model. Give the `kaizen` role a `manual` instrument. Runesmith then writes each author request to a file, you paste it into any chat model you can reach (free tiers work), and you hand the reply back with `runesmith manual answer --clipboard`. See [docs/CHAT_AUTHOR.md](docs/CHAT_AUTHOR.md).

Check the setup at any time. `doctor` reports on Python, pytest, the home, the ledger chain, the active generation and each instrument (key present, endpoint reachable), and says how to fix each problem:

```bash
python -m runesmith --home .runesmith doctor
```

After you update Runesmith, the kernel changes, and the active generation must be re-qualified under it. `generations requalify` re-freezes the same organs after a static check and a confined smoke test. The Studio does this for you.

## Everyday use

**Let it look after a workspace:**

```bash
python -m runesmith --home .runesmith steward path/to/workspace --rounds 24 --interval 3600 --exclude payments_service
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

**Attention** decides how often Kaizen runs. There is a standing 15% share. It rises to 25-40% while a failure signature recurs, or when a statistical process control chart (a Bernoulli CUSUM against Runesmith's own baseline yield) detects a downward drift. Attention state persists across runs.

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

An organ can change **how** it spends its envelope, never **how much** it gets. That is what makes self-improvement measurable: the successor must do better under the same ceiling. An organ cannot read the judge, the ledger, your secrets or the network. It sees only what the kernel grants it. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/VISION.md](docs/VISION.md) for how each part maps to the project's vision and to the paper.

## Evidence

Runesmith is developed as a falsifiable research program. A capability is claimed only when a test or a preregistered experiment shows it:

| Claim | Status |
|---|---|
| Kernel integrity: hash-chained ledger, tamper detection, generation verification and CAS activation | Implemented; unit-tested (`tests/test_kernel.py`) |
| Organ confinement: no reads outside the organ, writes, sockets, subprocesses, directory listing, environment secrets, native code, process handles, guard introspection or sub-interpreters; stderr and message floods cut off | Implemented; unit-tested against each escape. Not a hardened boundary (PEP 578 audit hooks); see Safety |
| Envelope enforcement: call, run and request-size ceilings; transport censoring is never scored | Implemented; unit-tested |
| Non-invasive probing: discovery and probes never write into an object | Implemented; tested byte for byte |
| Imports cannot escalate: traversal, tampering and forbidden imports are refused; activation only by trial | Implemented; unit-tested (`tests/test_share.py`) |
| The repair organ g0 reproduces Runesmith v1 (the SR3/SR4 comparator) | Port with disclosed differences; see SR5 protocol |
| **A Kaizen-selected, model-authored organ change makes Runesmith repair more fresh tasks** | **Shown in SR7-FRONTIER** (preregistered, sealed 2026-09-25). Generation C7, written by a frontier author inside Runesmith's own Kaizen loop, repaired **57 of 162** attempts (54 fresh tasks, 3 rounds each) against its predecessor's **35 of 162**: +13.6 points, p = 0.00085, with no more errors or false claims, and about half the time per successful repair. One of C7's ranking steps (module paths in the error text) only recognises the package names of its two development repositories, so it never fires elsewhere; which steps carried the gain is untested. The repair model was a cheap free-class one (gpt-oss-20b). The task family was synthetic single-line bugs. Earlier attempts are reported alongside: SR5 was not shown (36 vs 50 of 180 and 58 vs 60 of 138), and SR6, with a free-class author, closed before confirmation |
| **Weak-model amplification: a 2.6B free model repairs more inside the suit than in its strongest fixed scaffold** | **Not shown: SR6-W returned NULL** (sealed 2026-09-25). With the 2.6B model, g0 repaired 5 of 68 fresh tasks and a deterministic-retrieval scaffold at the same budget 12 of 68. The mirrored test's p = 0.033 is above the declared 0.025. C7 was not tested with this model |
| Model-succession retention; cumulative generations | Not yet shown. SR6 (free-class author) closed before confirmation. SR7 (frontier-class author) passed once; it is not replicated, and no later generation has been shown to improve on C7 |
| **Free-tier models can write the accepted increments of a real, brief-driven application** | **Observed, in progress. Not a controlled experiment.** In the out-of-the-box journeys, free-tier models wrote the code of Runesmith Motion, built through the Studio from a short brief. An AI operator acting as the owner approved and audited the checks and intervened frequently, and the journey is not finished. "Done" means a milestone's approved checks passed and its draft was applied, not that the feature works. The thirteen journeys also recorded more than two hundred findings in Runesmith itself, most of them since fixed; the paper gives the counts. This is not evidence of unattended operation or of economic value |
| Natural bugs, other task families, economic value | Not tested |

The paper describes each experiment, its preregistration and its result, and it states the claim discipline. The negative results count as much as the positive ones.

## Safety model

- Self-modification is bounded to organs. The kernel, meaning budgets, authority, judges and the ledger, is outside the reach of any organ and of the Kaizen engine.
- A new generation is activated only by an explicit operator compare-and-swap, or by an online trial's pre-declared sequential test on fresh work. Development evidence alone never activates it, and rollback is one pointer move.
- **Your files.** Runesmith runs tests on throwaway copies and never probes an excluded object. On the command line, fixes become proposals. In the Studio, files are written only when you click Apply, or when you have allowed automatic apply for checked builds, inside the files or folders you named. Every write is conflict-checked, backed up and undoable.
- **The Studio is private.** It listens on `127.0.0.1` only. It opens through a link with a one-time key, which becomes a browser cookie. It refuses requests that name another host, to stop DNS rebinding, and it refuses changes from other sites.
- Organs see no secrets. Instruments read secrets on demand: from environment variables that you name on the command line, or from the keys the Studio saved.
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
| `up [FOLDER] [--port N] [--no-browser] [--last]` | Open Runesmith Studio for a folder. This is what plain `runesmith` does. `runesmith-studio` is the same, installed under its own name |
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

More in [docs/STUDIO.md](docs/STUDIO.md), [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md), [docs/CHAT_AUTHOR.md](docs/CHAT_AUTHOR.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/ROADMAP.md](docs/ROADMAP.md) and the [CHANGELOG](CHANGELOG.md).
