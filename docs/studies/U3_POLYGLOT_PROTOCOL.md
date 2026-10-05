# U3-POLYGLOT: Runesmith against a fixed script on Aider's polyglot benchmark (Python), sealed before any session

Designer: Claude Opus 5.5 (integration operator), at the lead investigator's request for a benchmark people know. Written before
any U3 task checkout or session. Sealed in `SEAL_U3.txt` and pushed to GitHub before its first session.

**Benchmark.** The Python exercises of Aider's polyglot benchmark (`Aider-AI/polyglot-benchmark`, Exercism-derived, MIT
licensed), at the repository's latest commit on 2026-10-05 (recorded). Each exercise: a stub file, its instructions and its
tests. A task is solved strictly when the exercise's own tests pass on a fresh copy (the benchmark's own criterion). All Python
exercises are used, in the repository's alphabetical order; none is read by the designer or a model before the run.

**Arms.** R-C7 (Runesmith's released repair organ, C7) and DIRECT (SR6-W's fixed script), byte-identical to U1, in the same
frozen Core and envelope (5 calls, 8,192 tokens, 45 signal runs, 64,000 request bytes, 1,800 s). The public information is the
exercise's instructions (`.docs/`) and the failing test output, the same for both arms; the tests are the judge.

**Model.** `nvidia/nemotron-3-super-120b-a12b` on NVIDIA's free endpoint, reasoning effort "low"; free routes only, no paid spend.

**Execution.** After U1 and U2 end (one route load at a time); one HMAC-interleaved queue, one round per arm; route per call
recorded; transport censoring as in U1; if the free route's daily limit stops the run, the remaining exercises are censored,
never scored (no partial exercises).

**Analysis.** Primary: R-C7 > DIRECT, exact one-sided sign test on discordant exercises, alpha 0.025 (mirrored test declared;
fewer than 4 discordant: "no difference detectable at this size"). Reported as the benchmark reports it: percent of exercises
solved per arm, with exact 95% intervals; every number reported, whatever it shows. Not comparable to Aider's published
leaderboard numbers (different harness, one attempt, a fixed small envelope), and said so wherever it is shown.
