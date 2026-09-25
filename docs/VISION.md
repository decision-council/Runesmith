# Vision: the HatOS forge

This document records the owner's vision for Runesmith and maps each part to what exists, where the scientific blueprint already speaks to it, and what remains to build. Owner statements are paraphrased from Lars's messages of 2026-09-23/24 and are quoted where short.

## The vision in the owner's terms

1. **An open-source gift.** "I want to give that to all the people in the world who might not be able to afford a Claude subscription." Runesmith is released with the paper.
2. **Model-agnostic, with memory that carries across models.** It routes whatever models are available and works with a very weak local model, thanks to its suit or cockpit. What it learns lives in its own state and survives a change of model.
3. **Lowered into any environment.** With minimal specs, it learns:
   - where it is;
   - its objects and objectives;
   - each object's build and progression ladder;
   - the object's performance bands: **bad, minimal, optimal, world-class**.
4. **Maps itself.** It keeps a JSON map of itself, including what it could improve about itself.
5. **The forge of HatOS.** Runesmith builds and operates the Hats and tools (Gazetteer, Milliner, …) and improves its own hammer.
6. **Subject improvement is broad.** Any of these counts:
   - a task done faster;
   - a cycle quicker;
   - a summarization more efficient;
   - memory better or larger;
   - better tools it builds for itself;
   - better processes, state transfer and focus;
   - doing more with less inference.
7. **Kaizen.** "It should always strive to improve itself no matter what. There is always a new level." It improves itself especially when it is struggling with an object.
8. **The 3D-printer analogy.** It prints and tests its own parts, improving its functions using measurements from reality, like analytics. Where it has no measurement yet, it infers likely-good directions.

## Map: vision → blueprint → implementation

| # | Vision element | Where the blueprint already says it | Implemented in Runesmith v0.1 | Open work |
|---|---|---|---|---|
| 1 | Open, affordable, runs on weak models | §2.8 weak-model amplification (WMA); §9.1 "lean modular monolith for a slow Windows computer"; §12.2 models as capability explorers | Standard library only; any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, free tiers); Milliner router adapter; runs offline with scripted instruments; `runesmith demo` shows the whole loop in a minute without any model; **generation sharing** (`generations export/import`) lets improvements compound across people, with every import checked, smoke-tested and activated only by winning a local trial | A measured WMA experiment: equal-budget weak model with vs. without the suit (§10 W). SR6-W returned NULL (g0 5/68 vs a deterministic-retrieval scaffold 12/68): the suit did not amplify a 2.6B model. C7-style retrieval with weak models is the next question |
| 2 | Memory across models | §1.2 instrument–substrate hypothesis; §5.3 substitution retention (SR); §6.13 portable identity; §12.8 identity persisting while the instrument changes | All learned state (organs, generations, memory, maps, ledger) is instrument-independent; each call records which instrument answered | Model-succession test: learn with model A, use with model B, no transcript (§10 S) |
| 3 | Environment map: objects, objectives, ladders, bands | §8.19.1 required self-map; §8.19.2 performance ladder and milestone cloud (minimum / strong target, legacy "optimal" / verified frontier) | `envmap.py` → `ENVIRONMENT.json`: object discovery and kinds, proposed objectives with bands, build ladder with the next rung, opt-in probes, explicit unknowns | Object kinds beyond Python and Node repositories and document collections (services, websites); Node probing; owner acceptance of objectives; milestone cloud over ladders |
| 4 | Self-map | §8.19.1 (`SELF_MAP`, `OPERATIONS.json`/`BUILD.json`); S0 qualification (§8.19.4) | `selfmap.py` → `SELF_MAP.json`: kernel/organ regions, components and digests, affordances, envelope, capability ladders in bands, open Kaizen targets, lineage, unknowns | Runtime-semantic self-model (S0-RUNTIME); an independent challenge set as in S0-V1 |
| 5 | Forge of HatOS: builds and operates tools | §9.12 HatOS ownership boundary; §6.8 self-building artifact pipeline; §6.10 skills as executable procedural memory | The repair organ improves code objects through their tests; the envmap can map a HatOS workspace | Organs that build new tools (skill packages) and operate Hats through owner adapters; a semantic round trip (§10 supporting qualification) |
| 6 | Broad subject improvement | §2.7 (object / subject / learner / evaluator updates); dated Goalpost 2 revision (§8.19.3); S2-CAP (M1 memory retrieval) | Kaizen targets both **yield** (lost-opportunity families) and **cycle time** (value-stream stages); the envelope makes "more with less" measurable | Targets for memory use, summarization/context compaction (§6.9), and self-built tools |
| 7 | Kaizen always, and more when struggling | `research/TRON_KAIZEN_AUTONOMOUS_TARGET_DISCOVERY_RESEARCH_2026-09-11.md` (PDSA, TOC, SPC, MAPE-K); Astra §3.7 (object blockage → subject change → object return) and §5 (85/15 healthy, 60/40 blocked) | `kaizen/attention.py` (standing share, struggle-driven rise, recovery); `kaizen/diagnose.py` (value stream, failure families, declared ranking); `kaizen/improve.py` (PDSA with prediction and falsifier, qualification, keep-best, freeze); `kaizen/trial.py` (online trials); `kaizen/affordances.py` (unused affordances as untried mechanism classes); `steward.py` (rounds over a whole workspace: map, discover, serve new work, Kaizen, report, proposals) | A steward daemon with a schedule (rounds with an interval exist); drift detection is implemented (Bernoulli CUSUM, `attention.py`) and awaits field data |
| 8 | Prints and tests its own parts; reality measurements; inference where there are none | §4.6 learning and promotion; §6.8 pipeline; §6.14 capability-learning bridge; §12.4 evaluators are part of cognition | Organs are the printable parts. A change is kept only after confined smoke and replay against a held-out judge; generations are frozen, verified and rollback-able | Hypothesis packets and decision twins for directions without measurements (§6.8), always labelled as inference |
| 9 | Drop into any folder; simple for anyone; comment anywhere; a map of everything | §9.1 lean monolith for a slow computer; §6.13 portable identity; the owner as authority (operator laws) | **Runesmith Studio** (`runesmith/app`, docs/STUDIO.md):<br>• the genesis first boot, ending in naming what you build;<br>• a four-lens living map (environment, self, development, operations);<br>• thinking power from none to many, including a chat window;<br>• goals, brief and blueprints, with a Planner for milestones and first files;<br>• proposals and drafts with conflict-checked apply and undo;<br>• notes on anything, which reach the model that works on that thing;<br>• generations, trials and the C7 library;<br>• a verifiable ledger. | Desktop-level testing on macOS and Linux; object kinds beyond code and documents; the owner accepting or editing objectives in the UI |

## Why a suit can carry a weak model

The MillinerOS research synthesis on small-model scaffolding (`research/small_model_scaffolding.md`, 2026-09-04) makes the design rule explicit. A modest model is useful as a proposal generator inside a deterministic closed loop, where four mechanisms act together:
- **Generation:** decomposition, retrieval and tools make good proposals likelier.
- **Selection:** tests and independent evidence choose among proposals.
- **Control:** typed state, permissions and budgets stop invalid changes.
- **Escalation:** failed checks or high task value justify more compute or a stronger model.

It also names the untrustworthy substitutes: generic self-critique, agreement among correlated samples, and verbal confidence. Runesmith's shape follows this:
- Organs generate.
- The public signal and a held-out judge select.
- The kernel's envelope and confinement control.
- Attention and routing escalate.

The rule Runesmith inherits:

> Spend inference only where a candidate has an independently checkable consequence. Otherwise, abstain or escalate.

## What makes this scientifically different from "an agent that edits itself"

Many systems let a model edit its own scaffold. Runesmith's contribution is the evidence contract around that editing:
- the target comes from telemetry by a declared rule;
- the change carries a prediction and a falsifier;
- the resource envelope is fixed;
- the judge is out of the organ's reach;
- every failed attempt stays in the ledger;
- a successor is kept only when it does better on work it has never seen.

The blueprint's claim discipline applies unchanged. See §1.5 (nonclaims) and §12.7 (negative results are informative).

## First proof point

**SR5-KAIZEN** (preregistered 2026-09-24) tests the full loop once:
1. Runesmith Core generation A runs on development tasks.
2. The Kaizen engine picks its own target from its own telemetry.
3. A free model rewrites the repair organ.
4. The successor is compared with its predecessor on fresh tasks under the same envelope.

The receipts live in the MillinerOS research repository.

`runesmith demo --kaizen` replays that loop offline on a bundled workspace. g0 struggles, Kaizen targets the lost family, and the change the free model actually wrote in SR5 is qualified, frozen, trialled and activated. The replay shows the machinery; the preregistered confirmation on fresh work is what decides the claim.
