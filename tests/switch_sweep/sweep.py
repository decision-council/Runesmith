"""Layer 1 of the out-of-box coverage plan: every triple of switch values, as a real scenario.

A strength-3 covering array over the owner's switches, the work modes, approved acceptance checks and one switch
flipped mid-work: every combination of any three factor values appears in at least one row. Each row runs a real
Studio process on a fresh folder, with a fresh profile and a scripted model:

  1. build under the row's switches;
  2. flip one switch through the Studio API, the way an owner changes their mind;
  3. build again;
  4. restart the Studio, and build once more.

The rules that must always hold are then checked from the receipts, phase by phase: model calls in the ledger, checks
that ran, files written, scheduled jobs. See docs/JOURNEY_COVERAGE_PLAN.md, section 4. This is not part of the quick
suite; it runs unattended before a release:

    python tests/switch_sweep/sweep.py [--rows N] [--out DIR]
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from runesmith.app import work_modes            # noqa: E402
from runesmith.app.workspace import Workspace   # noqa: E402

FACTORS = {
    "autonomy": ["observe", "propose"],
    "auto_work": [False, True],
    "build_steps": [False, True],
    "build_apply": [False, True],
    "probe_tests": [False, True],
    "kaizen": [False, True],
    "read_notes": [False, True],
    "modes": ["not configured", "build on", "build off"],
    "acceptance": [False, True],
    "flip": ["nothing", "build_steps", "build_apply", "autonomy", "auto_work"],
}
ANSWER = {"title": "Implementation", "files": [
    {"path": "app.py", "content": "def answer():\n    return 42\n"},
    {"path": "tests/__init__.py", "content": ""},
    {"path": "tests/test_app.py", "content": "import unittest\nfrom app import answer\n\n\nclass Tests(unittest.TestCase):\n"
                                             "    def test_answer(self):\n        self.assertEqual(answer(), 42)\n"}]}
ACCEPTANCE = ("import unittest\nfrom app import answer\n\n\nclass Acceptance(unittest.TestCase):\n"
              "    def test_contract(self):\n        self.assertEqual(answer(), 42)\n")


# ------------------------------------------------------------------------------------------------ covering array
def covering_array(factors: dict, strength: int = 3, seed: int = 7, candidates: int = 300) -> list[dict]:
    """Greedy strength-t covering array: every t-way combination of factor values appears in some row."""
    names = list(factors)
    rng = random.Random(seed)
    uncovered = {(combo, values) for combo in itertools.combinations(range(len(names)), strength)
                 for values in itertools.product(*(range(len(factors[names[i]])) for i in combo))}
    rows = []
    while uncovered:
        best, best_score = None, -1
        target = next(iter(sorted(uncovered)))                   # make sure each new row covers something
        for _ in range(candidates):
            row = [rng.randrange(len(factors[n])) for n in names]
            for i, v in zip(target[0], target[1], strict=True):
                row[i] = v
            score = sum(1 for combo in itertools.combinations(range(len(names)), strength)
                        if (combo, tuple(row[i] for i in combo)) in uncovered)
            if score > best_score:
                best, best_score = row, score
        rows.append(best)
        uncovered -= {(combo, tuple(best[i] for i in combo)) for combo in itertools.combinations(range(len(names)), strength)}
    return [{n: factors[n][v] for n, v in zip(names, row, strict=True)} for row in rows]


# ------------------------------------------------------------------------------------------------ one Studio
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Studio:
    """A real Studio process for one folder, with its own fake profile; the key is read from its lock file."""

    def __init__(self, folder: Path, profile: Path, log: Path):
        self.folder, self.profile, self.log, self.process = folder, profile, log, None
        self.epoch = ""

    def start(self):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "VIRTUAL_ENV"))}
        env.update(USERPROFILE=str(self.profile), HOME=str(self.profile), APPDATA=str(self.profile / "Roaming"),
                   LOCALAPPDATA=str(self.profile / "Local"), PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8")
        self.port = free_port()
        with open(self.log, "ab") as out:
            self.process = subprocess.Popen([sys.executable, "-m", "runesmith", "up", str(self.folder), "--port", str(self.port),
                                             "--no-browser"], cwd=str(REPO), env=env, stdout=out, stderr=out,
                                            stdin=subprocess.DEVNULL)
        for _ in range(120):
            try:
                with urlopen(f"http://127.0.0.1:{self.port}/api/ping", timeout=1) as r:
                    if json.loads(r.read()).get("app") == "runesmith-studio":
                        lock = json.loads((self.folder / ".runesmith" / "studio.lock.json").read_text(encoding="utf-8"))
                        self.token = lock["token"]
                        self.get("/api/state")
                        return
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.25)
        raise RuntimeError(f"Studio did not start; see {self.log}")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=15)

    def call(self, method, path, body=None):
        headers = {"Cookie": f"rs_session={self.token}", "X-Runesmith": "1", "Content-Type": "application/json"}
        if method != "GET":
            headers["X-Runesmith-Workspace"] = self.epoch
        request = Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request, timeout=120) as response:
                self.epoch = response.headers.get("X-Runesmith-Workspace") or self.epoch
                return json.loads(response.read() or b"null")
        except HTTPError as error:
            return {"http_error": error.code, "body": error.read().decode("utf-8", "replace")[:400]}

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body=None):
        return self.call("POST", path, body or {})

    def run(self, job, timeout=240, **params):
        """Queue one job and wait until the worker is idle again; the queue answer or refusal is returned."""
        queued = self.post("/api/worker/run", {"job": job, "params": params})
        deadline = time.time() + timeout
        while time.time() < deadline:
            w = self.get("/api/worker")
            if isinstance(w, dict) and not w.get("current") and not w.get("queue"):
                return queued
            time.sleep(0.3)
        return dict(queued if isinstance(queued, dict) else {}, timed_out=True)


# ------------------------------------------------------------------------------------------------ one row
def prepare(folder: Path, row: dict):
    ws = Workspace(folder)
    ws.save_plan({"summary": "Tiny calculation service", "milestones": [{"title": "Answer", "done_when": "answer() returns 42"}]})
    config = ws.config()
    config["instruments"]["offline"] = {"kind": "scripted", "answers": [ANSWER]}
    for role in ("plan", "repair", "kaizen"):
        config["roles"][role] = ["offline"]
    ws.save_config(config)
    ws.update_settings({"onboarded": True, "policy_chosen": True, "interval_minutes": 1, "build_paths": ["app.py", "tests"],
                        **{k: row[k] for k in ("autonomy", "auto_work", "build_steps", "build_apply", "probe_tests",
                                               "kaizen", "read_notes")}})
    if row["modes"] != "not configured":
        current = work_modes.configuration(ws)
        rows = [dict(r, enabled=(r["executor"] == "build") == (row["modes"] == "build on") if r["executor"] == "build"
                     else r["enabled"]) for r in current["modes"]]
        work_modes.save(ws, rows, current["revision"], "switch sweep row")
    if row["acceptance"]:
        (ws.home / "acceptance").mkdir(parents=True, exist_ok=True)
        (ws.home / "acceptance" / "m1.py").write_text(ACCEPTANCE, encoding="utf-8")


def ledger(folder: Path) -> list[dict]:
    path = folder / ".runesmith" / "ledger.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def jobs(folder: Path) -> list[dict]:
    try:
        data = json.loads((folder / ".runesmith" / "STUDIO_JOBS.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data if isinstance(data, list) else data.get("jobs", data)
    return list(rows.values() if isinstance(rows, dict) else rows)


def flipped(row: dict) -> dict:
    after = dict(row)
    if row["flip"] == "autonomy":
        after["autonomy"] = "propose" if row["autonomy"] == "observe" else "observe"
    elif row["flip"] != "nothing":
        after[row["flip"]] = not row[row["flip"]]
    return after


def check_phase(name, switches, events, applied_now, scheduled, queued):
    """The rules (coverage plan I1, I2, I4, I5, I6, I7) for one phase, from its receipts."""
    broken = []
    calls = [e for e in events if e["kind"] == "instrument.call"]
    checks = [e for e in events if e["kind"] == "build.checked" and not e["data"].get("recheck_only")]
    if switches["autonomy"] == "observe" and calls:
        broken.append(f"{name}: I1 observe mode asked a model {len(calls)} time(s)")
    if (switches["autonomy"] == "observe" or not switches["build_steps"]) and checks:
        broken.append(f"{name}: I2 checks ran with checks off or in observe mode")
    may_write = (switches["autonomy"] == "propose" and switches["build_steps"] and switches["build_apply"]
                 and switches["acceptance"] and switches["modes"] != "build off")
    if applied_now and not may_write:
        broken.append(f"{name}: I4 project files were written without checks, automatic apply and owner acceptance")
    if scheduled and not switches["auto_work"]:
        broken.append(f"{name}: I5 work was scheduled with scheduled work off")
    if not switches["kaizen"] and any(e["kind"].startswith(("kaizen.", "generation.trial")) for e in events):
        broken.append(f"{name}: I6 self-improvement ran while it was off")
    refused = isinstance(queued, dict) and "http_error" in queued
    if switches["modes"] == "build off" and not refused:
        broken.append(f"{name}: I7 a build started although every Build mode is off")
    if refused and not queued.get("body", "").strip():
        broken.append(f"{name}: I9 a refusal without a reason")
    return broken


def run_row(index: int, row: dict, out: Path) -> dict:
    base = out / f"row-{index:03d}"
    shutil.rmtree(base, ignore_errors=True)
    folder, profile = base / "project", base / "profile"
    folder.mkdir(parents=True)
    profile.mkdir(parents=True)
    prepare(folder, row)
    studio = Studio(folder, profile, base / "studio.log")
    result = {"row": index, "switches": row, "phases": [], "broken": []}
    phases = [("A", row), ("B", flipped(row)), ("C", flipped(row))]
    try:
        studio.start()
        for name, switches in phases:
            if name == "B" and row["flip"] != "nothing":
                key = row["flip"]
                answer = studio.post("/api/settings", {key: switches[key], "policy_chosen": True})
                if isinstance(answer, dict) and "http_error" in answer:
                    result["broken"].append(f"flip {key} was refused: {answer}")
            if name == "C":
                studio.stop()
                studio.start()
                kept = studio.get("/api/settings")
                for key in ("autonomy", "auto_work", "build_steps", "build_apply"):
                    if kept.get(key) != switches[key]:
                        result["broken"].append(f"C: restart changed {key} to {kept.get(key)!r}")
            before = len(ledger(folder))
            had_app = (folder / "app.py").exists()
            job_count = len(jobs(folder))
            queued = studio.run("build")
            events = ledger(folder)[before:]
            new_jobs = jobs(folder)[job_count:]
            scheduled = [j for j in new_jobs if j.get("by") == "schedule"]
            applied_now = (folder / "app.py").exists() and not had_app
            result["phases"].append({"phase": name, "queued": queued if isinstance(queued, dict) else str(queued),
                                     "calls": sum(e["kind"] == "instrument.call" for e in events),
                                     "checks": sum(e["kind"] == "build.checked" for e in events),
                                     "applied": applied_now, "scheduled": len(scheduled)})
            result["broken"] += check_phase(name, switches, events, applied_now, scheduled, queued)
            may_write = (switches["autonomy"] == "propose" and switches["build_steps"] and switches["build_apply"]
                         and switches["acceptance"] and switches["modes"] != "build off")
            if may_write and not had_app and not applied_now:
                # Liveness: the sweep must also see things happen, or a silent harness would pass every rule.
                result["broken"].append(f"{name}: liveness: every switch allowed an automatic apply, but none happened")
    except Exception as error:                                   # a harness failure is a result too
        result["broken"].append(f"harness: {type(error).__name__}: {error}")
    finally:
        studio.stop()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=0, help="run only the first N rows (0: all)")
    parser.add_argument("--out", default=str(REPO / "training" / ".tmp" / "switch-sweep"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = covering_array(FACTORS)
    selected = rows[: args.rows] if args.rows else rows
    print(f"{len(rows)} rows cover every triple of {len(FACTORS)} factors; running {len(selected)}", flush=True)
    results = []
    for index, row in enumerate(selected):
        started = time.monotonic()
        result = run_row(index, row, out)
        results.append(result)
        print(f"row {index:03d} {'OK  ' if not result['broken'] else 'FAIL'} {time.monotonic() - started:5.1f}s "
              f"{json.dumps(row)} {result['broken'][:2]}", flush=True)
        (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    failed = [r for r in results if r["broken"]]
    print(f"done: {len(results) - len(failed)} of {len(results)} rows hold every rule", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
