# Community evolution: self-improvement replicated by the community

Status: **idea and design direction, not built.** Proposed by Lars on 2026-09-28. Sequencing: after the out-of-box release has proven reliable building in the coverage journeys (J1–J11). Local self-improvement is tested first in J6.

## What exists today

Runesmith can already improve itself locally (Kaizen, `runesmith/kaizen/`, `runesmith/generations.py`):
- it writes a new generation of its repair organ;
- the generation is kept only if it **wins a trial on the owner's own work**;
- every step leaves receipts: the trial results and the ledger.

C7, the paper's measured result, came from this loop. Self-improvement is off by default and opt-in in the Studio.

## The rule (Lars, 2026-09-28)

**Only Runesmith's own improvements and aggregate numbers ever travel. People's projects never leave their machine.** It is Runesmith updating itself; no project is ever sent to another user.

## A careful first version, possibly at release (opt-in at first run, off by default)

- **Evidence cards.** When a local improvement wins a trial, the Studio shows a small card:
  - the generation's fingerprint;
  - its aggregate numbers (repair yield, calls, time, false promotions);
  - the model routes it ran on.
  It holds no code and no project text, and it shows exactly what would be shared.
- **The owner submits it.** "Share with the community" opens a prefilled GitHub issue or pull request that the owner reviews and submits. There is no server and nothing is sent automatically, so every shared byte is visible.
- **Receiving is a separate opt-in.** "Try community improvements" starts with declarative improvements only (prompts, policies, packet shapes). They are always trial-gated on the owner's own work and never become active without winning there.

## Automatic updates, run by bots and open to everyone (Lars, 2026-09-28)

- **A public, append-only evidence log**, like a transparency log, written by the bots and readable and monitorable by anyone. For every promoted improvement it records:
  - its fingerprint;
  - the benchmark and community-trial results that earned it;
  - who reviewed it, and when.
- **Opt-in automatic updates** from that channel. Each update is signed and reproducible from its log entry. The Studio says in plain words what changed and why, linking to the evidence.
- **Safety:**
  - staged rollout (a few volunteers first);
  - a local trial before activation: an update must still win on the owner's own work, or it stays inactive;
  - one-click rollback (generations already support it);
  - a public kill switch if the log shows a problem.

## The idea

Let the community do what one Runesmith does alone, so that improvements are **replicated across many independent projects** before anyone depends on them. As far as we know, this would be the first open-source tool that improves itself through community-replicated evidence.

1. **Share an improvement.** A user's Runesmith packages a winning generation together with its trial receipts, as a signed bundle. It becomes a pull request to a community repository, created by the user with one click, never automatically without consent.
2. **Bots test it** on public benchmarks: the task pools behind the paper's studies (SR1–SR7) are ready-made. Nothing is merged without evidence and a human review.
3. **Community trials.** Volunteers opt in to let their Runesmith trial community generations on their *own* projects, using the existing trial mechanism.
   - Only aggregate numbers are reported: repair yield, calls, time, false promotions. Project content never leaves the machine.
   - Each volunteer is an independent replication.
4. **Promotion.** A generation joins the default library only when it wins across many unrelated projects and on held-out benchmarks. Its evidence is published with it, the way `library/LIBRARY.json` records C7's today.

## Hard problems (to solve before building)

| Problem | Why it matters | Direction |
|---|---|---|
| **Security** | A generation is code that runs on other people's machines. Runesmith has no OS sandbox today (see `journeys/COVERAGE.md`). | First share only declarative improvements (prompts, policies, packet shapes), not arbitrary code. Code generations wait for real isolation (AppContainer on Windows, seccomp or namespaces on Linux) and signed, reviewed bundles. |
| **Privacy** | Trials run on private projects. | Report only aggregate metrics, with a schema that cannot carry text; publish that schema for auditing. |
| **Gaming and Goodhart** | An improvement can overfit to the trial measure. | Diverse projects, held-out benchmarks, false-promotion rates reported next to yield, and promotion thresholds fixed in advance. |
| **Consent and trust** | People must stay in control. | Everything opt-in; sharing and trialling are separate choices; every result is traceable to its receipts. |
| **Reproducibility** | Claims must hold up. | Bundles carry model routes, seeds and task identities, so bots and other users can rerun them. |

## Why it matters for the paper and the community

It turns the paper's evidence-first stance into a community practice: improvements earn their place through independent replication, not reputation. It is also a natural future-work section for the paper, and a strong reason for people to join the GitHub community.

## Order of work

1. **Release:** local, opt-in, trial-gated self-improvement, as today. Journey J6 proves it live.
2. **v1.x:** "Share this improvement" (a signed bundle plus receipts, as a pull request), and CI bots that run benchmarks. Declarative generations only.
3. **Later:** opt-in community trials with aggregate reporting, and code generations once isolation exists.
