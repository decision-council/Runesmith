"""Command line: ``python -m runesmith <command>``.

    up          open Runesmith Studio, the local app, for a folder (what plain `runesmith` does)
    init        create a home, a config template, the ledger and generation g0
    demo        watch the whole loop on a tiny workspace in about a minute (offline unless --live)
    status      active generation, ledger integrity, configured instruments
    doctor      check Python, pytest, the home, the instruments and disk; says how to fix each problem
    selfmap     write SELF_MAP.json from Runesmith's own bytes and session records
    envmap      write ENVIRONMENT.json for a workspace (objects, objectives, bands, ladders)
    discover    run a repository's tests once and turn failures into repair opportunities
    repair      run one repair opportunity on a local repository
    run         Kaizen always: serve opportunities, storing experience and interleaving self-improvement
    steward     lowered into a workspace: map, discover, serve new work, improve itself, report; in rounds
    trial       show the online trial that decides whether a frozen candidate is activated
    report      write REPORT.md: generations, capability bands, struggles, trials, recent work
    proposals   judge-accepted fixes as patches for human review (Runesmith never edits objects itself)
    diagnose    rank Kaizen targets from recorded sessions
    kaizen      run one self-improvement campaign on a task set (freezes a candidate generation)
    manual      requests waiting for a chat model that you relay by hand: list / show [ID] / answer [ID]
    generations list / verify / activate / requalify / export --to FILE / import --from FILE
    ledger      verify the hash chain
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from pathlib import Path

from runesmith import __version__, generations
from runesmith.config import build_router, envelope_from, home_dir, load_config
from runesmith.ledger import Ledger
from runesmith.local import run_local_task


def _ledger(home: Path) -> Ledger:
    return Ledger(home / "ledger.jsonl")


def _active_organs(home: Path) -> Path:
    active = generations.active(home)
    if not active:
        raise SystemExit("no active generation; run `runesmith init` first")
    path = home / "generations" / active
    check = generations.verify(path)
    if not check["ok"]:
        raise SystemExit(f"active generation {active} does not verify: {check['problems']}")
    return path / "organs"


def _sessions(home: Path) -> list[dict]:
    root = home / "sessions"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*.json"))] if root.exists() else []


def cmd_up(args) -> None:
    from runesmith.app.server import Studio, serve
    folder = Path(args.folder)
    if args.last:                                   # the launchers: the folder used last time, or a fresh first project
        recent = Studio.recent()
        folder = Path(recent[0]["path"]) if recent else Path.home() / "Runesmith" / "My first project"
        folder.mkdir(parents=True, exist_ok=True)
    from runesmith.app.workspace import WorkspaceError
    try:
        serve(folder, home=Path(args.home).resolve() if args.home else None, port=args.port,
              open_browser=not args.no_browser)
    except WorkspaceError as error:                 # plain words in the launcher window, never a traceback (J7)
        raise SystemExit(f"Runesmith could not open {folder}: {error}") from None


def cmd_init(args) -> None:
    from runesmith.home import init_home
    result = init_home(home_dir(args.home))
    print(f"home: {result['home']}\nactive generation: {result['active_generation']}\nconfig: {result['config']}")
    # Journey J10-F3: say where a model is chosen, including the keyless chat window.
    print('next: choose a model for the repair and kaizen roles in that file. Its "examples" section has ready ones, '
          "including chat_by_hand (a chat window you relay to, no key needed). Or open the Studio: `runesmith up`.")


def cmd_status(args) -> None:
    home = home_dir(args.home)
    if not (home / "runesmith.json").is_file():      # journey J10-F2: it printed a default setup as if one existed
        raise SystemExit(f"No Runesmith home here yet ({home}). Run `runesmith init`, "
                         "or open the Studio with `runesmith up`.")
    config = load_config(home)
    report = {"version": __version__, "home": str(home), "active_generation": generations.active(home),
              "generations": [g["id"] for g in generations.list_generations(home)],
              "ledger": _ledger(home).verify(), "sessions": len(_sessions(home)),
              "instruments": {n: {k: s.get(k) for k in ("kind", "model", "base_url")} for n, s in config["instruments"].items()},
              "roles": config["roles"]}
    print(json.dumps(report, indent=1))


def cmd_selfmap(args) -> None:
    from runesmith.selfmap import write_self_map
    home = home_dir(args.home)
    records = json.loads(Path(args.records).read_text(encoding="utf-8")) if args.records else _sessions(home)
    self_map = write_self_map(home / "SELF_MAP.json", home=home, records=records)
    _ledger(home).append("self_map.written", {"map_digest": self_map["map_digest"], "records": len(records)})
    print(json.dumps({k: self_map[k] for k in ("identity", "capabilities", "open_targets", "unknowns")}, indent=1))


def cmd_envmap(args) -> None:
    from runesmith.envmap import write_environment_map
    home = home_dir(args.home)
    home.mkdir(parents=True, exist_ok=True)
    env_map = write_environment_map(home / "ENVIRONMENT.json", Path(args.workspace), probe=args.probe,
                                    scratch=home / "scratch")
    _ledger(home).append("environment_map.written", {"map_digest": env_map["map_digest"], "objects": len(env_map["objects"])})
    for obj in env_map["objects"]:
        bands = {o["id"]: o["band"] for o in obj.get("objectives", [])}
        print(f"{obj['name']:30} {obj['kind']:20} next rung: {obj.get('next_rung')}  bands: {bands}")
    print(f"unknowns: {env_map['unknowns']}\nwritten: {home / 'ENVIRONMENT.json'}")


def cmd_repair(args) -> None:
    home = home_dir(args.home)
    if args.opportunity is not None:
        opportunity = json.loads((home / "opportunities.json").read_text(encoding="utf-8"))[args.opportunity]
        args.repo, args.test = opportunity["repo"], opportunity["failing_tests"]
        args.issue, args.judge_test = opportunity["issue"], opportunity.get("judge_tests")
    if not (args.repo and args.test and args.issue):
        raise SystemExit("repair needs --opportunity N, or --repo, --test and --issue")
    repo = Path(args.repo).resolve()
    key = f"repair-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    record, final, _ = run_local_task(home=home, organ_dir=_active_organs(home), repo=repo, failing_tests=args.test,
                                      issue=args.issue, judge_tests=args.judge_test, key=key)
    (home / "sessions").mkdir(parents=True, exist_ok=True)
    (home / "sessions" / f"{key}.json").write_text(json.dumps(record, indent=1, default=str) + "\n", encoding="utf-8")
    _ledger(home).append("opportunity.closed", {"key": key, "status": record["status"],
                                                "strict_success": record.get("strict_success"),
                                                "cycle_seconds": record["cycle_seconds"], "model_calls": record["model_calls"]})
    from runesmith.objects.code import encode_like
    for path, text in sorted(final.items()):
        current = (repo / path).read_bytes()
        original = current.decode("utf-8-sig").replace("\r\n", "\n")
        sys.stdout.writelines(difflib.unified_diff(original.splitlines(True), text.splitlines(True), f"a/{path}", f"b/{path}"))
        if args.apply and record.get("strict_success"):
            (repo / path).write_bytes(encode_like(text, current))       # keeps the file's line endings and BOM
    print(json.dumps({k: record.get(k) for k in ("status", "strict_success", "model_calls", "public_runs", "cycle_seconds")}))
    if args.apply and not record.get("strict_success"):
        print("not applied: the judge did not pass")
    elif not args.apply and record.get("strict_success"):          # journey J10-F4
        print("not written: the fix above passed the held-out judge. Run the repair again with --apply to write "
              "such a fix into your files (it asks the model again).")


def cmd_discover(args) -> None:
    from runesmith.discover import discover
    home = home_dir(args.home)
    home.mkdir(parents=True, exist_ok=True)
    found = discover(Path(args.repo), scratch=home / "scratch")
    path = home / "opportunities.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    known.extend(found["opportunities"])
    path.write_text(json.dumps(known, indent=1) + "\n", encoding="utf-8")
    _ledger(home).append("objects.discovered", {"repo": found["repo"], "status": found["status"],
                                                "opportunities": len(found["opportunities"])})
    # The status in plain words, and why the tests could not run (journey J10-F1: "error_without_failures").
    words = {"green": "all tests pass", "failing": "some tests fail", "error_without_failures": "the tests could not run",
             "timed_out": "the tests did not finish in time"}.get(found["status"], found["status"])
    print(f"{found['repo']}: {words}, {len(found['opportunities'])} repair opportunities "
          f"(saved to {path}; run with `repair --opportunity <index>`)")
    if found["status"] == "error_without_failures":
        import importlib.util
        why = (found.get("detail") or "the test run printed no failure")
        if importlib.util.find_spec("pytest") is None:
            why = ("pytest is not installed for this Python: `python -m pip install pytest`, or open the Studio "
                   "(`runesmith up`), which runs unittest tests without it")
        print(f"  Why: {why}")
    for index, opportunity in enumerate(known[-len(found['opportunities']):] if found["opportunities"] else [],
                                        start=len(known) - len(found["opportunities"])):
        note = f"  (skipped: {opportunity['triage']['reason']})" if opportunity.get("triage") else ""
        print(f"  [{index}] {', '.join(opportunity['failing_tests'])}{note}")


def cmd_run(args) -> None:
    """Kaizen always: serve saved opportunities, interleaving self-improvement steps."""
    from runesmith.loop import run_loop
    home = home_dir(args.home)
    source = Path(args.opportunities) if args.opportunities else home / "opportunities.json"
    opportunities = json.loads(source.read_text(encoding="utf-8"))
    summary = run_loop(home=home, opportunities=opportunities * max(1, args.passes), seed=args.seed,
                       router=build_router(load_config(home), home=home), min_experience=args.min_experience,
                       kaizen_every=args.kaizen_every,
                       max_answered=args.max_answered, bar=args.bar,
                       on_step=lambda step: print(json.dumps(step, default=str)[:300], flush=True))
    print(json.dumps(summary, indent=1, default=str))


def cmd_steward(args) -> None:
    from runesmith.steward import steward
    home = home_dir(args.home)
    config = load_config(home)
    exclude = set((config.get("steward") or {}).get("exclude", [])) | set(args.exclude or [])
    steward(home=home, workspace=Path(args.workspace), router=build_router(config, home=home), seed=args.seed,
            rounds=args.rounds, interval_s=args.interval, exclude=exclude, max_objects=args.max_objects,
            loop_settings={"min_experience": args.min_experience, "kaizen_every": args.kaizen_every})


def cmd_trial(args) -> None:
    """Show the open online trial (if any) and the decisions of closed ones."""
    from runesmith.kaizen.trial import Trial
    home = home_dir(args.home)
    if args.open:
        from runesmith.share import open_trial_for
        print(json.dumps(open_trial_for(home, args.open), indent=1))
        return
    trial = Trial.load(home / "TRIAL.json")
    report = {"open": trial.summary() if trial else None,
              "open_looks": trial.looks if trial else [],
              "closed": [{"file": p.name, **Trial.load(p).summary()} for p in sorted(home.glob("TRIAL-*.json"))]}
    print(json.dumps(report, indent=1))


def cmd_doctor(args) -> None:
    from runesmith.doctor import diagnose_home
    rows = diagnose_home(home_dir(args.home), network=not args.offline)
    for row in rows:
        mark = {True: "ok ", False: "FIX", None: " - "}[row["ok"]]
        print(f"[{mark}] {row['check']:32} {row['detail']}")
        if row["fix"]:
            print(f"       -> {row['fix']}")
    problems = sum(1 for row in rows if row["ok"] is False)
    # No role names an instrument: nothing about a model was checked, so "all checks passed" would say too much.
    no_model = any(row["check"] == "config" and row["ok"] for row in rows) and not any(
        row["check"].startswith("instrument ") for row in rows)
    print(f"{problems} problem(s)" if problems else "no problems found" if no_model else "all checks passed")
    if no_model:
        print("no model is set up: Runesmith can map and watch, but not plan or repair. "
              "Add one under Thinking power in the Studio (runesmith up).")


PYTEST_FOR_DEMO = ("The demo repairs a small project whose tests run with pytest, which is not installed for this Python.\n"
                   "Install it with:  python -m pip install pytest\n"
                   "Or open the Studio (`runesmith up`): it plans, builds, checks and tries projects without pytest.")


def cmd_demo(args) -> None:
    import importlib.util
    if importlib.util.find_spec("pytest") is None:          # journey J10-B2: the demo showed "0 of 0 repairs", silently
        raise SystemExit(PYTEST_FOR_DEMO)
    cmd_init(args)
    if args.kaizen:
        from runesmith.demo_kaizen import run_kaizen_demo
        author = None
        if args.manual_author:
            from runesmith.manual import ManualInstrument
            author = ManualInstrument("chat", "the chat model you relay to", directory=home_dir(args.home) / "manual",
                                      timeout_s=6 * 3600)
        run_kaizen_demo(home_dir(args.home), author=author)
        return
    if args.manual_author:
        raise SystemExit("--manual-author goes with --kaizen")
    from runesmith.demo import run_demo
    run_demo(home_dir(args.home), live=args.live)


def cmd_proposals(args) -> None:
    from runesmith.proposals import list_proposals, write_proposals
    home = home_dir(args.home)
    if args.write:
        for path in write_proposals(home, Path(args.write)):
            print(f"written: {path}")
        return
    found = list_proposals(home)
    waiting = [p for p in found if p["state"] == "waiting"]
    for proposal in waiting:
        print(f"== {proposal['key']}  {proposal['repo']}")
        print(f"   fixes: {', '.join(proposal['failing_tests'])}")
        print(proposal["diff"])
    for proposal in found:                            # decided in the Studio: named, not offered again
        if proposal["state"] != "waiting":
            print(f"-- {proposal['key']}: {proposal['state']} in the Studio {proposal.get('state_utc') or ''}".rstrip())
    others = len(found) - len(waiting)
    print(f"{len(waiting)} judge-accepted proposal(s) waiting" + (f", {others} already decided in the Studio" if others else "")
          + "; `proposals --write DIR` saves the waiting ones as patches for review")


def cmd_report(args) -> None:
    from runesmith.report import write_report
    path = write_report(home_dir(args.home))
    print(f"written: {path}")
    print(path.read_text(encoding="utf-8"))


def _print_text(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:                  # a console or pipe that cannot encode it: write UTF-8 bytes
        sys.stdout.flush()
        sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.flush()


def cmd_manual(args) -> None:
    """The person's side of the manual instrument: see what is waiting, read it, hand back the reply."""
    from runesmith import manual
    home = home_dir(args.home)
    directory = manual.directory_for(load_config(home), home)
    if args.action == "list":
        rows = manual.pending_requests(directory)
        if not rows:
            print(f"no requests are waiting in {directory}")
        for row in rows:
            state = "answered, not yet read by the run" if row["answered"] else "waiting for an answer"
            print(f"{row['id']}  {state}\n    asked {row['created_utc']}; {row['prompt_kb']} KB "
                  f"(about {row['approx_tokens']} tokens)\n    paste or attach: {row['prompt']}")
        return
    try:
        rid = manual.resolve_request(directory, args.id)
    except LookupError as error:
        raise SystemExit(str(error)) from None
    if args.action == "show":
        _print_text((directory / f"{rid}.prompt.md").read_text(encoding="utf-8"))
        return
    if args.clipboard:
        text = manual.read_clipboard()
    elif args.file:
        text = manual.decode_reply(Path(args.file).read_bytes())
    else:
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
        text = manual.decode_reply(raw)
    result = manual.submit_answer(directory, rid, text, model=args.model, force=args.force)
    for problem in result["problems"]:
        print(f"  problem: {problem}")
    if result["written"]:
        print(f"answer saved for {rid}; the waiting run reads it within seconds")
    else:
        raise SystemExit("not saved: ask the chat model to fix the problems above and try again, "
                         "or add --force to hand the reply over as it is (it then counts as the model's answer)")


def cmd_diagnose(args) -> None:
    from runesmith.kaizen.diagnose import diagnose
    home = home_dir(args.home)
    records = json.loads(Path(args.records).read_text(encoding="utf-8")) if args.records else _sessions(home)
    print(json.dumps(diagnose(records), indent=1))


def cmd_kaizen(args) -> None:
    """Baseline the active generation on a task set, run one Kaizen campaign, freeze the best candidate."""
    from concurrent.futures import ThreadPoolExecutor
    from runesmith.kaizen.improve import KaizenRun, dev_score
    home = home_dir(args.home)
    spec = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
    tasks = spec["tasks"] if isinstance(spec, dict) else spec
    config = load_config(home)
    active = generations.active(home)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    def evaluate(organ_dir: Path, label: str) -> list[dict]:
        def one(task: dict) -> dict:
            record, _, _ = run_local_task(home=home, organ_dir=organ_dir, repo=Path(task["repo"]).resolve(),
                                       failing_tests=task["failing_tests"], issue=task["issue"],
                                       judge_tests=task.get("judge_tests"), key=f"kaizen-{stamp}-{label}-{task['id']}")
            record["task_id"] = task["id"]
            if task.get("reference"):
                record["reference"] = task["reference"]
            return record
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            return list(pool.map(one, tasks))

    baseline = evaluate(_active_organs(home), "baseline")
    run = KaizenRun(incumbent_organs=_active_organs(home), module="repair", router=build_router(config, home=home),
                    baseline_records=baseline, baseline_score=dev_score(baseline), dev_evaluate=evaluate,
                    out_dir=home / "kaizen" / stamp, scratch=home / "scratch", envelope=envelope_from(config),
                    max_answered=args.max_answered, on_event=lambda kind, data: _ledger(home).append(kind, data))
    result = run.run()
    if result["decision"] == "candidate":
        manifest = generations.freeze(Path(result["best_organ_dir"]), home, label=f"kaizen {stamp}", parent=active,
                                      provenance={"lineage": "kaizen: rule-selected target, model-authored change",
                                                  "target": result["target"], "score": result["best_score"],
                                                  "baseline": result["baseline_score"]})
        print(f"candidate generation {manifest['id']} frozen (not active). Activate after confirmation on fresh tasks:\n"
              f"  runesmith generations activate {manifest['id']} --expected {active}")
    print(json.dumps({k: result[k] for k in ("decision", "target", "best_score", "baseline_score", "answered")}, indent=1, default=str))


def cmd_generations(args) -> None:
    home = home_dir(args.home)
    if args.action == "list":
        for g in generations.list_generations(home):
            marker = "*" if g["id"] == generations.active(home) else " "
            print(f"{marker} {g['id']}  parent={g.get('parent')}  {g['label']}  {g['frozen_utc']}")
    elif args.action == "verify":
        # Without an id, every generation is verified (journey J10-B1: it crashed with a traceback).
        if args.id:
            print(json.dumps(generations.verify(home / "generations" / args.id), indent=1))
        else:
            ids = [g["id"] for g in generations.list_generations(home)]
            if not ids:
                raise SystemExit("No generations yet. Run `runesmith init` first.")
            print(json.dumps({gid: generations.verify(home / "generations" / gid) for gid in ids}, indent=1))
    elif args.action in ("activate", "requalify") and not args.id:
        raise SystemExit(f"generations {args.action} needs a generation id; `runesmith generations list` shows them.")
    elif args.action == "activate":
        previous = generations.active(home)
        generations.activate(home, args.id, expected=args.expected)
        _ledger(home).append("generation.activated", {"id": args.id, "previous": previous})
        print(f"active: {args.id} (was {previous})")
    elif args.action == "requalify":
        from runesmith.doctor import requalify
        print(json.dumps(requalify(home, args.id), indent=1))
    elif args.action == "export":
        from runesmith.share import export_generation
        if not (args.id and args.to):
            raise SystemExit("generations export needs an id and --to FILE")
        print(f"written: {export_generation(home, args.id, Path(args.to))}")
    elif args.action == "import":
        from runesmith.share import ImportRefused, import_generation
        if not args.source:
            raise SystemExit("generations import needs --from FILE")
        try:
            result = import_generation(home, Path(args.source))
        except ImportRefused as refusal:
            raise SystemExit(f"import refused: {refusal}") from None
        print(json.dumps(result, indent=1, default=str))


def cmd_ledger(args) -> None:
    print(json.dumps(_ledger(home_dir(args.home)).verify(), indent=1))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="runesmith", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=None, help="Runesmith home directory (default ./.runesmith)")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("up", help="open Runesmith Studio for a folder (the default command)")
    p.add_argument("folder", nargs="?", default=".", help="the folder Runesmith works in (default: this one)")
    p.add_argument("--port", type=int, default=None, help="local port (default: the first free from 7300)")
    p.add_argument("--no-browser", action="store_true", help="print the link instead of opening the browser")
    p.add_argument("--last", action="store_true", help="open the folder used last time (or a new first project)")
    sub.add_parser("init")
    p = sub.add_parser("demo"); p.add_argument("--live", action="store_true",
                                               help="use the instruments in runesmith.json instead of the offline stand-in")
    p.add_argument("--kaizen", action="store_true",
                   help="watch self-improvement offline: struggle, diagnosis, SR5's model-authored fix, trial, activation")
    p.add_argument("--manual-author", action="store_true",
                   help="with --kaizen: you relay the author request to a chat model of your choice instead of replaying SR5")
    sub.add_parser("status")
    p = sub.add_parser("doctor"); p.add_argument("--offline", action="store_true", help="do not contact instruments")
    p = sub.add_parser("selfmap"); p.add_argument("--records")
    p = sub.add_parser("envmap"); p.add_argument("workspace"); p.add_argument("--probe", action="store_true")
    p = sub.add_parser("discover"); p.add_argument("repo")
    p = sub.add_parser("repair"); p.add_argument("--repo"); p.add_argument("--test", action="append")
    p.add_argument("--judge-test", action="append"); p.add_argument("--issue"); p.add_argument("--apply", action="store_true")
    p.add_argument("--opportunity", type=int, help="index into <home>/opportunities.json (from `discover`)")
    p = sub.add_parser("run"); p.add_argument("--opportunities"); p.add_argument("--passes", type=int, default=1)
    p.add_argument("--seed", default="runesmith-loop"); p.add_argument("--min-experience", type=int, default=8)
    p.add_argument("--max-answered", type=int, default=2); p.add_argument("--bar", type=int, default=1)
    p.add_argument("--kaizen-every", type=int, default=8)
    p = sub.add_parser("steward"); p.add_argument("workspace"); p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--interval", type=float, default=3600.0, help="seconds between rounds")
    p.add_argument("--exclude", action="append", help="object name never to probe (repeatable)")
    p.add_argument("--max-objects", type=int, default=50); p.add_argument("--seed", default="runesmith-steward")
    p.add_argument("--min-experience", type=int, default=8); p.add_argument("--kaizen-every", type=int, default=8)
    p = sub.add_parser("trial"); p.add_argument("--open", metavar="ID", help="open a trial of a frozen generation")
    sub.add_parser("report")
    p = sub.add_parser("proposals"); p.add_argument("--write", metavar="DIR", help="save each proposal as DIR/<key>.patch")
    p = sub.add_parser("diagnose"); p.add_argument("--records")
    p = sub.add_parser("kaizen"); p.add_argument("--tasks", required=True); p.add_argument("--workers", type=int, default=2)
    p.add_argument("--max-answered", type=int, default=4)
    p = sub.add_parser("manual"); p.add_argument("action", choices=["list", "show", "answer"])
    p.add_argument("id", nargs="?", help="a request id or a unique prefix (default: the only waiting request)")
    p.add_argument("--file", help="answer: read the reply from this file")
    p.add_argument("--clipboard", action="store_true", help="answer: read the reply from the clipboard")
    p.add_argument("--model", help="answer: which chat model answered (recorded in the receipt)")
    p.add_argument("--force", action="store_true", help="answer: save a reply even if it does not fit the schema")
    p = sub.add_parser("generations"); p.add_argument("action", choices=["list", "verify", "activate", "export", "import", "requalify"])
    p.add_argument("id", nargs="?"); p.add_argument("--expected")
    p.add_argument("--to", help="export: the zip file to write")
    p.add_argument("--from", dest="source", help="import: a zip exported by another Runesmith home")
    sub.add_parser("ledger")
    args = parser.parse_args(argv)
    if args.command is None:                                  # plain `runesmith`: open the Studio here
        args = parser.parse_args(["up"] if args.home is None else ["--home", args.home, "up"])
    {"up": cmd_up, "init": cmd_init, "status": cmd_status, "selfmap": cmd_selfmap, "envmap": cmd_envmap, "discover": cmd_discover,
     "repair": cmd_repair, "run": cmd_run, "trial": cmd_trial, "report": cmd_report, "demo": cmd_demo, "proposals": cmd_proposals, "steward": cmd_steward, "doctor": cmd_doctor, "diagnose": cmd_diagnose, "kaizen": cmd_kaizen, "manual": cmd_manual, "generations": cmd_generations,
     "ledger": cmd_ledger}[args.command](args)


if __name__ == "__main__":
    main()
