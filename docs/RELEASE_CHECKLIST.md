# Release checklist (before the public release with the paper)

Items marked **owner** are Lars's decisions. The rest are technical and can be done before them.

## Decisions (owner)

- [ ] **License.** Nothing is chosen yet. The README says so.
- [ ] **Repository location and name.**
- [ ] **What ships.** The Core only, or also the MillinerOS experiment harness (`scripts/sr*_run.py`, generators) as a reproducibility package.
- [x] **Organs shipped as generations.** g0 (the v1 port) ships as the default. SR5 did not show B, so B does not ship. C7 (SR7, shown once against B, not tested against g0) ships in the library and becomes active only by winning an online trial.

## Hygiene

- [x] `.gitignore` excludes local homes (`.runesmith/`, `.demo-home/`), scratch (`.tmp/`) and caches. `.demo-home/` holds a map of a private workspace and must never be published.
- [ ] Start the public history from a clean tree: `git init` in a fresh copy, without `.demo-home/` or `.tmp/`.
- [ ] Search the tree for machine paths and personal data before the first push. On 2026-09-24 the source and docs held none, only references to "the MillinerOS research repository". This was re-checked at about 12:45Z after the manual-author work. `runesmith/`, `tests/`, `docs/`, README, CHANGELOG and `pyproject.toml` are clean; the only hits were false positives, `\n` escapes inside the demo data's JSON.
- [ ] `pyproject.toml`: add authors, project URLs and the license once decided.
- [x] Static checks: `ruff check runesmith tests --select E9,F,B` is clean (2026-09-24). All text files use LF, enforced by a test.

## Portability (not yet verified)

- [x] **Linux** (2026-09-24): Python 3.12.14, x86_64, in a local container with no network and 1 CPU.
  - The first full run gave 83 passed, 1 failed (the stderr flood verdict on POSIX, since fixed) and 4 skipped (three Windows-only tests; the proposals test, because the image has no git).
  - **After the fix, a second full run: 84 passed, 4 skipped** (the same skips).
  - `setrlimit` limits ran for the first time here: they stopped a stderr flood at the cap.
  - Receipts: `runtime/sr5-kaizen-2026-09-24/CORE_LINUX_TESTS*.txt` in the research repository.
- [ ] **macOS**, and Python 3.11 and 3.13 on Linux. Git should be present so the proposals test runs too.
- [ ] A CI workflow running the tests on all three systems. No workflow is committed yet, because none has run.

## Runesmith Studio (2026-09-25)

- [x] `tests/test_studio.py`: 12 tests. They cover:
  - the workspace rules: conflict-checked apply, CRLF kept, exact undo, unsafe draft paths refused, keys never listed;
  - notes reaching the right model;
  - the library adopted only through a trial;
  - the planner and a full worker round;
  - the server's guards: token-to-cookie, Host check, the custom header for changes, cross-origin refusal, path traversal.
  - The full Windows suite: **100 passed** (Python 3.13).
- [x] The wheel packages the static files and the library. A fresh-venv install served the Studio (`runesmith up`).
- [x] Launchers: `Runesmith.cmd` (CRLF), `Runesmith.command` and `runesmith.sh` (LF). **Before publishing:** set the executable bit on the shell launchers (`git update-index --chmod=+x Runesmith.command runesmith.sh`).
- [ ] Try the launchers by double-click on macOS and Linux desktops.
- [ ] Linux and macOS test runs with the Studio tests. The Linux container run needs Docker, so ask the owner first.
- [ ] Optional: an MP4 of the opening sequence. Record `/cinema` full screen, or install ffmpeg (ask the owner first).
- [x] Website: `site/src/page.html`, built with `scripts/build_site.py`. Screenshots come from `scripts/studio_shots.py`. A private preview is published for the owner.

## Evidence that should be final before release

- [x] SR5 (main and SR5b) verdicts in the README's evidence table.
- [x] SR6-W verdict in the README's evidence table (NULL, 2026-09-25).
- [ ] Every README claim traced to a test or a sealed result. There must be no capability claim without one.
- [x] Internal adversarial review of the organ sandbox (2026-09-24). It found and closed `_winapi` process handles, `gc` introspection, sub-interpreters, `ctypes` imports, stderr floods and unbounded protocol lines, each with a test.
- [x] OS-level process and memory limits under the audit hook: a Job Object on Windows (tested) and `setrlimit` on POSIX (run on Linux on 2026-09-24; not yet on macOS).
- [ ] An **independent** security review, and OS-level **file and network** isolation for untrusted organs: AppContainer on Windows, namespaces or seccomp on Linux. PEP 578 audit hooks are not a hardened boundary. Until then the README tells users to import generations only from people they trust.
