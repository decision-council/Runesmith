# LOC1 Amendment 1 (before any task or session): the suite criterion of the repository rule, and tag forms

Designer: Claude Opus 5.5 (the agent running LOC1). Written after the sealed repository rule (PROTOCOL.md, Repositories) ran once and
selected no repository (`REPOSITORY_RULE_CHECK_ORIGINAL.json`), and before any pool, task, seed use, PROTOCOL.json or model session of
LOC1 exists. No outcome of LOC1 exists; the change cannot be outcome-driven. Sealed in `SEAL_AMENDMENT_1.txt`, pushed to the same branch.

What the first run showed (receipts in `REPOSITORY_RULE_CHECK_ORIGINAL.json`): no large candidate's whole default suite exits 0 on this
offline Windows machine. pygments: one test file fails to collect (an optional dependency, `wcag_contrast_ratio`, is not installed), which
interrupts the whole run; sqlglot: three files fail to collect, likewise; astroid: the suite runs, 2,104 tests pass and 119 fail (symlink
and platform tests); pydantic: the installed pydantic-core (2.46.4) is not the one its tag requires (2.46.5); werkzeug and jinja: missing
runtime or test dependencies (and both indexes are under the cap); rich: the suite passes but its navigation index is 11,641 bytes, under
the 12,000-byte cap; sympy: tests live inside the package (no top-level `tests/`); sqlalchemy and networkx: their tags (`rel_X_Y_Z`,
`networkx-X.Y`) were not read by the rule's tag pattern.

1. **Suite criterion (replaces criterion 1).** The repository's suite, run as the pool generator runs it (`python -m pytest tests -q -p
   no:cacheprovider -rA --continue-on-collection-errors`, same interpreter definition, 1,200 s), runs to completion (pytest exit 0 or 1)
   and **at least half of its `tests/**/test_*.py` files pass entirely** (every collected test passed or was skipped; a file with any
   failure, error or collection error does not count). Rationale: the generator only ever uses test files that pass entirely at baseline
   (a failing or uncollectable file never targets a task), and every task is validated by its positive and negative controls, so a
   partial suite cannot produce an invalid task; requiring the whole suite to exit 0 only selects repositories without optional or
   platform-specific tests. The half-of-files floor keeps out repositories whose suite is mostly broken here.
2. **Generator, same reason.** `loc1_generate_pool_tasks.py`'s baseline run adds `--continue-on-collection-errors`, so one uncollectable
   test file does not abort the baseline (its new digest is in `SEAL_AMENDMENT_1.txt`). Nothing else of the generator changes.
3. **Tags.** Release tags of the forms `rel_X_Y_Z` and `<name>-X.Y.Z` are read as versions too (highest version wins, as before).
4. Criteria 2 (layout) and 3 (navigation index above 12,000 bytes, measured as declared) and the candidate order are unchanged; the
   first three qualifying repositories are used. Existing checkouts are reused (same tag, same commit).
5. Reported as a deviation, with this amendment's digest, wherever LOC1 is reported.
