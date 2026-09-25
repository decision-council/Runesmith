# Writing an organ

An organ is a policy: how Runesmith spends its resources on one kind of opportunity. Organs are the part of Runesmith that improves itself. The Kaizen engine rewrites them, and so can you.

## Contract

```python
def run(view: dict, cockpit) -> dict:
    ...
    return {"status": "public_pass", "final_files": {"src/pkg/mod.py": "...full new text..."}}
```

- **Standard library only.** The organ runs in an isolated interpreter (`python -I -B`) and cannot import Runesmith.
- **No ambient authority.** It cannot:
  - read files outside its own directory;
  - write anything;
  - list directories;
  - open sockets;
  - start processes;
  - see environment secrets.

  Everything goes through the cockpit.
- **`view`** carries:
  - `issue` (text);
  - `failing_tests` (node ids);
  - `src_files` (path → text);
  - `src_sizes`;
  - `caps` (advisory byte caps).
- **Cockpit affordances:**
  - `ask(packet, schema, purpose, system=None)`: one model call, always charged. It returns `{ok, data, error_kind, error, latency_s}`.
  - `run_signal(files=None, trace=False)`: runs the failing tests with your file overrides. With `trace=True` it also returns `executed_src_lines` (path → executed line numbers).
    - Module-level lines run at import time are included.
    - Lines inside function bodies show which functions the failing tests actually called, usually the best clue to where the defect is.
    - Calling it before any edit (`files=None`) shows the failure as it stands.
  - `budget()`: what remains.
  - `log(stage, **data)`: a telemetry mark. Log `reads=[paths]` so the diagnosis knows what you inspected.
  - `recall(query, k)`: Runesmith's own memory of earlier opportunities: the issue, the status, the changed lines and the judge's verdict. It is always available and returns an empty list when the host keeps no memory. It costs no model call.
- **Return value.** `status` names your terminal state. `final_files` is what the held-out judge evaluates.

## Rules of thumb that the evidence supports

- **Log what you read.** The Kaizen diagnosis splits failures by "the fix was in a file you read" vs "not read". That split is the difference between a navigation problem and an editing problem.
- **Do not end early with budget left** unless you can justify it. An unusable answer costs one call; the envelope is fixed, and unspent calls are wasted.
- **Prefer checkable steps.** Spend a call only where its result can be checked, by a test run, a parse or an exact match.
- **Keep packets small.** Large requests are slower, more often truncated, and capped by the envelope.
- **At scale, navigation coverage is the bottleneck.** SR5 (2026-09-24, sealed) repaired repositories of about 115 source files. After a successful navigation answer, the organ read the defective file in only 86 of 160 sessions. A fixed fallback read set of the first four indexed files reached it in 0 of 26. In 6 of 6 probes on the same kind of task, the execution trace (`run_signal(trace=True)`) contained both the defective file and the defective line. Many files appear because of import-time lines, so weigh the lines executed inside function bodies.
- **A development gain is not a result.** Identical organs scored 10/32 and 16/32 on the same replay. Trust improvements that survive repeated replays and a trial on fresh work.

## Qualification: how a changed organ becomes a generation

1. **Static check.** It parses, defines `run`, and imports only allowed standard-library modules.
2. **Smoke test.** It runs once in the confined process on the kernel's fixture repository.
3. **Replay.** It is replayed on held-out development tasks with the real instrument and scored by a judge it cannot see. Keep-best applies: a candidate is kept only if it is strictly better.
4. **Freeze.** It is frozen as a new generation: digest-bound, with its parent, author and mechanism recorded.
5. **Activation.** It is activated only by winning an online trial on live work (a sequential exact test), or by an explicit operator compare-and-swap.

`runesmith report` and `SELF_MAP.json` list the affordances each organ leaves unused. Kaizen authors see the same list as untried mechanism classes.

## Testing an organ locally

```bash
python -m pytest tests/test_kernel.py -q
```

The kernel tests run the shipped organ against a scripted instrument. Write the same kind of test for your organ with `runesmith.instruments.ScriptedInstrument`, or with `runesmith.kaizen.improve.FixtureInstrument`, which answers any schema from hints.
