# U2b-TIERS: a larger version of U2, sealed before any outcome on its primary tasks

Designer: Claude Sonnet 5.5 (the agent running the study), on the instruction of the lead investigator (Lars), who approved a larger U2 because
"U2 sample sizes are too small". Written on 2026-10-05, about 23:45Z, before any U2b session exists. Sealed in `SEAL.txt`; pushed to the lab's
private repository (branch `u1-protocol`) before the first session.

**Question.** On tasks U1 never started, does Runesmith's repair organ (generation C7) repair more tasks than the same model driven by a simple
fixed script, at three free model sizes? U2 asked this on 17 tasks with one round per task and arm; its samples were too small to say much.

**Arms.** R-C7: Runesmith's released repair organ, generation C7. DIRECT: the same model with a simple fixed script in place of Runesmith's repair
organ (SR6-W's script). Both run in the same kernel, with the same envelope and the same judge (the hidden strict tests). Organs, frozen Core,
pool, prompts and envelope are byte-identical to U1 and U2 (digests in PROTOCOL.json): 5 calls, 8,192 tokens, 45 signal runs, 64,000 request
bytes, 1,800 s per session. Nothing about either arm is tuned for this study.

## Models (free routes only; no paid spend)

| key | model | route | reasoning | setup evidence |
|---|---|---|---|---|
| small | liquid/lfm-2.5-2.6b (2.6B) | OpenRouter free (`openrouter:liquid/lfm-2.5-2.6b:free`) | provider default, as in U2 | U2's probe (`ROUTE_PROBE_U2.json`, digest bound); no new call |
| medium | openai/gpt-oss-20b (20B, 3.6B active) | NVIDIA free (`nvidia:openai/gpt-oss-20b`) | provider default, as in U1's gpt-oss-20b runs | `ROUTE_PROBE_U2B.json`: one tiny and one full-size (32,032 bytes) call, both answered by provider nvidia and model openai/gpt-oss-20b, reported cost 0.0 |
| large | nvidia/nemotron-3-super-120b-a12b (120B, 12B active) | NVIDIA free | effort low, as in U2 | U2's probe; no new call |

The medium model is included because its full-size probe call worked at reported cost 0 on NVIDIA's free endpoint (the rule fixed before the probe).
It runs on a different route from U1's gpt-oss-20b (Vercel, then OpenRouter, paid); U1's medium results are not reused here. Three models of different
families and sizes are reported as "three free models of increasing size", not as a scaling law. Any call on a free route that reports a cost
above zero stops all new sessions (no paid spend is allowed); the paid balances are read before and after as a cross-check.

## Populations

**Primary: the 21 tasks U1 never started** (U1's 39 protocol tasks minus the 18 in `ADMISSIONS.jsonl` with admitted = true; U1's queue positions 19 to 39;
17 from boltons, 4 from click). No one has seen an outcome on them. Per model, 3 rounds per task and arm: 21 x 2 x 3 = 126 sessions.
Tasks: boltons-c3e933a689, click-7184508430, click-2d95542292, boltons-95fbe7a374, boltons-03f3d74cfb, boltons-29e3343f7d, boltons-6108a70655,
boltons-e74844551d, boltons-f6f2250dd7, click-755ff4a259, boltons-83b61a84a6, click-698ffa031b, boltons-66d1ec01e8, boltons-b1270dd309,
boltons-19dbc15c12, boltons-a42ebd5a14, boltons-7922498c9b, boltons-4ac16c1e6b, boltons-52f2603303, boltons-6ac83a7d5d, boltons-b019bb974d.

**Secondary, declared descriptive: U2's 17 tasks, small and large only.** U2 holds round 1 (session receipts, digests bound); U2b runs rounds 2 and 3
for both arms (68 sessions per model) so each task has 3 rounds. Medium has no secondary (U1's medium runs were on another route and are not reused).
The secondary and the pooled 38-task view are descriptive: not part of the Bonferroni family and not used for any claim of a test.

Total planned: small 194, medium 126, large 194 sessions.

## Order

Per model one queue: all primary sessions first, then (small and large) all secondary sessions, and the next phase starts only after the previous
phase, including its censored re-queue, has finished. Primary tasks follow U1's queue order. Within a task the sessions (arms x rounds) are in
HMAC order: SHA-256 HMAC keyed with U1's `order_seed` over `u2b|<model>|<task>|<arm>|<round>`; so the arms and rounds of a task are interleaved
in a seeded order, as in U1. Two workers per model, six sessions at most at once; sessions start in queue order. Session keys (idempotency) are
`u2b-<model>-<arm>-<task>-r<round>`, unique per round.

## Execution and stopping rule

- **Stop.** The evaluation ends at whichever comes first: every queued session written or logged as not run, or **2026-10-06T06:30:00Z**. After the
  stop time no session starts (the re-queue included). Sessions already started finish (each is bounded by the 1,800 s wall of the envelope), and the
  end marker is written when the last one has, so it may carry a time up to about 07:00Z.
- **Only tasks with all their sessions complete are analysed** (all six: two arms, three rounds, each judged). A task with a missing or censored
  session leaves the analysis and is reported, with the counts, as excluded. Nothing is imputed.
- **Censoring.** A session whose model route failed by transport (`censored_transport`) is never scored. Each model's primary and secondary phase ends
  with one re-queue of its censored sessions (new key suffix `-requeue1`), if before the stop time; the first receipt is kept in `eval_censored`.
- **Quota guard.** After 4 consecutive transport-censored sessions on a model, no new session starts on it for 20 minutes; a third such stop is final for
  that model. Free-route limits (OpenRouter about 1,000 requests per day, resetting at 00:00Z; NVIDIA about 40 per minute) are therefore handled by
  pausing, not by scoring failures. Sessions not run are logged with their reason in `NOT_RUN.jsonl`. The secondary comes last, so it is dropped first.
- **Resources.** Checkouts and temp live under `C:\Users\aithi\oob-overflow\u2b` (the judge's two temp locations are moved there too; nothing else of the
  judge changes). Each session's checkout is deleted as soon as the session is judged. Before every session start the run waits while free RAM is under 400 MB, free space on D: under 300 MB, or free space on C: under 300 MB;
  it never starts a session below those floors; sessions already running finish. The floors on C: and D: are the coordinator's of 2026-10-05, replacing
  the first brief's 5 GB and 400 MB (see below). No Docker. Five harness errors in a row halt a model (reported, never scored).
- **No outcome is read before the end marker.** Progress is monitored by counting session files and call-log lines only.
- **Known state at sealing.** At 23:38Z free space on C: is 760 MB and on D: 584 MB; a test suite is also running on D:. Free space on C: was 6.1 GB at
  22:32Z and 0.2 GB at 22:52Z; `pagefile.sys` is 14.35 GB, last written at about 22:41Z, and a system-managed pagefile shrinks only on reboot, which comes
  after the release. For that reason the coordinator waived the first brief's 5 GB floor on C: for this night and set the floors above. The stop time
  does not move.
- The harness (`u2b_run.py`, derived from `u2_run.py`; `u1_run.py` and `u2_run.py` imported, not changed) was exercised before the seal against a
  throwaway folder with a model-less stand-in (no model call): sealing, queueing, the stop time, the quota guard, analysis, recomputation and the
  report. The self-test switches are inert in the study.

## Statistic (SR7's, as in U1 and U2; imported code, not rewritten)

Per model, on its complete primary tasks. For task t, round k: s(arm, t, k) = 1 if the judge's strict tests pass, else 0. Per task the integer
d_t = sum over k = 1..3 of [s(R-C7, t, k) - s(DIRECT, t, k)] (the per-task mean difference is d_t / 3). T = sum of d_t. **Exact one-sided sign-flip
test** (`u1_run.signflip`, `task_sums`, `test_pair`): p(R-C7 better) = P(T* >= T) over all sign assignments of the nonzero |d_t|, p(DIRECT better) =
P(T* <= T) (the mirrored test, declared). Verdict: fewer than 4 tasks with nonzero d_t: NO_DIFFERENCE_DETECTABLE; else p(R-C7 better) <= 0.025: PASS;
else p(DIRECT better) <= 0.025: FIXED_SCRIPT_BETTER; else NULL. **Bonferroni over the three models**: every p is also reported against
0.025 / 3 = 0.008333 (the family-wise threshold). Also reported, with exact (Clopper-Pearson) 95% intervals that treat sessions as independent
(three rounds on one task are not): strict successes per arm, public passes, false promotions, organ errors, calls, seconds.

**Minimum detectable effect, before the seal** (`MDE_PRESEAL.json`, `u2b_mde.py`: U1's simulation with a declared per-task comparator rate; 21 tasks,
3 rounds, 1,000 simulated studies per step of 0.02, power 0.80, one-sided alpha 0.025, U1's analysis seed). Absolute gain in the per-session success
rate detectable: **small 0.14** (prior fixed-script rate 0.00, U2: 0 of 17; 0.20 at a rate of 0.05, 0.24 at 0.10), **medium 0.28** (prior rate 0.51,
U1's fixed script, all rounds), **large 0.26** (prior rate 0.59, U2). At rates of 0.20 to 0.50 the value is 0.28, and 0.22 at 0.70. A result smaller
than these is not evidence of no effect; the report states this next to every NULL. After the run the post-hoc value from the observed rates is also
reported (U1's `minimum_detectable_effect`).

## The figure

`model_size_u2b.csv` has the columns of `model_size.csv` and holds the primary population over 3 rounds, with the tasks complete on every model (the
intersection) so that `tasks`, `rounds_per_task`, `task_set_id` and `run_dates` (2026-10-05 to 2026-10-06) are the same on every row; per-model tests
use each model's own complete tasks. Arm labels: `runesmith_repair_organ` and `fixed_script`. Every number is reported, whatever it shows.

## Pacing (estimate, not a rule)

U2 sessions averaged about 240 s (small) and 250 s (large); at two workers a model runs about 29 sessions an hour, so the primary takes about 4.3 h and
the secondary about 2.3 h more; the medium model has no secondary. The small model used about 4.9 calls per session in U2 (about 950 calls for 194
sessions; the Milliner ledger counted about 1.3 attempts per call), spread over two quota days. The run starts at about 23:50Z, so the primary should
finish at about 04:10Z and the secondary would need until about 06:30Z: the expected end is the stop time, 06:30Z, for small and large (a part of the
secondary may be left out), earlier for medium (about 04:10Z).

## Outputs

`PROTOCOL.md` and `PROTOCOL.json` (digests in `SEAL.txt`), `PUSH_RECEIPT.txt`, `EVAL_START_UTC.txt`, `EVAL_END_UTC.txt` and one end marker per model,
`eval/` (session receipts), `NOT_RUN.jsonl`, `CALLS_LOG.jsonl`, `SPEND_RECEIPT.json`, `RESULT.json`, `RECOMPUTE.json` (an independent recomputation,
including a brute-force check of the sign-flip tests), `REPORT.md`, `u2b_sessions.csv`, `model_size_u2b.csv`. Nothing under the paper's folders is touched.
