# U1-UPLIFT Amendment 1 (before seeds, pool, PROTOCOL.json or any session)

Designer: Claude Opus 5.5 (integration operator). Written after the runner stopped on an undefined term and reported, and before
any seed, task, protocol seal or model session existed (OPERATIONS_LOG.md). No outcome of U1 exists; the choice cannot be
outcome-driven. Sealed by its SHA-256 in SEAL_AMENDMENT_1.txt and pushed to the same GitHub branch as the protocol.

1. **"The experiment's interpreter" (Repositories rule) is defined as:** the machine's Python 3.13.14 with pytest 9.1.1, no
   network after checkout, and each repository registered as installed by a name-and-version `dist-info` stub on `PYTHONPATH`
   (what an editable install provides; a real install is impossible offline here). A repository qualifies if its own default
   pytest invocation exits 0 (skips allowed). Under this definition the declared order gives `pallets/click` 8.5.0 and
   `mahmoud/boltons` 26.2.0 (both pass; the runner's log records Python-Markdown and toolz failing the original strict reading).
2. **Layout:** a repository whose package is at the top level (boltons) is moved under `src/` in the task snapshot, without
   changing any source byte, so the pool generator and the DIRECT script (which read `src/` paths) treat it like a src-layout
   project. The move is identical for every arm; the generator's own baseline and per-task controls validate the result.
3. Both are reported as deviations from the protocol's text, with this amendment's digest, wherever U1 is reported.
