# U2-TIERS: the U1 comparison at three model sizes (free models), sealed before any U1 outcome

Designer: Claude Opus 5.5 (integration operator), at the lead investigator's request for a model-size chart. Written before any
U1 or U2 evaluation session exists. Sealed in `SEAL_U2.txt` and pushed to GitHub before its first session.

**Question.** On U1's tasks, does Runesmith's repair organ (C7) repair more tasks than the same model driven by SR6-W's fixed
DIRECT script, for a small and a large free model as well as U1's gpt-oss-20b?

**Arms.** R-C7 and DIRECT, exactly as in U1 (byte-identical organs, the same frozen Core, the same envelope: 5 calls, 8,192
tokens, 45 signal runs, 64,000 request bytes, 1,800 s).

**Models (fixed now; free routes only; no paid spend).**
- Small: `liquid/lfm-2.5-2.6b:free` (OpenRouter free; SR6-W's model), default reasoning.
- Large: `nvidia/nemotron-3-super-120b-a12b` (NVIDIA's free endpoint), reasoning effort "low" (the setting the program
  uses for this model since 2026-09-29 to keep its answers inside the token budget).
- The medium point is U1's gpt-oss-20b result itself (U1's R-C7 and DIRECT arms); U2 does not re-run it.
Models of different families: reported as "three free models of increasing size", not as a scaling law.

**Tasks.** U1's analysed tasks in U1's queue order (all four U1 sessions complete), the same task revisions and public
information. If a free route's daily limit stops a model, its later tasks are censored, never scored; no partial tasks
(both arms of a task or neither).

**Execution.** Starts after U1's end marker. Per model, one interleaved queue of the two arms; the route of every call recorded;
transport censoring as in U1. No outcome of U2 is read before its end marker.

**Analysis.** Per model, primary: R-C7 > DIRECT, exact one-sided sign test on discordant tasks, alpha 0.025 (mirrored test
declared; fewer than 4 discordant tasks: "no difference detectable at this size"). The two models are two declared tests;
both are also reported against a Bonferroni threshold of 0.0125. The figure: strict success with and without Runesmith at
each of the three sizes (U1's gpt-oss-20b as the middle point), with exact 95% intervals; every number reported, whatever it shows.
