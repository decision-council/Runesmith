# Contributing

Thank you for trying Runesmith. Issues and discussions are the best way to reach us.

## Reporting a problem

Open an issue with:

- what you did, what you expected and what happened instead;
- the version (`python -m runesmith --version`), your operating system and Python version;
- the matching lines from the Studio's Activity page, if any.

Never paste API keys, tokens or private code. For security problems, see [SECURITY.md](SECURITY.md).

## Proposing a change

1. Open an issue first for anything larger than a small fix, so we can agree on the direction.
2. Keep the change focused, and add a test that fails before it and passes after.
3. Run the tests: `python -m pytest tests -q`, and for Studio changes the browser use-loops in `tests/studio_use_loops_browser.mjs`.
4. Describe in plain words what changed and why.

Contributions are accepted under the project's license, the Apache License 2.0 (see `LICENSE`).

## How Runesmith decides

Runesmith changes code only on evidence: approved acceptance checks for your projects, and online trials for its own generations. Changes to the kernel, the evidence gates or the ledger are reviewed with particular care, because the rest of the system relies on them.
