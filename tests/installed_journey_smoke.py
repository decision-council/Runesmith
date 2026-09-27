"""Opt-in installed-artifact journey; real HTTP/worker/checks, scripted author.

Run with --output-dir pointing to a NEW directory under an existing scratch
parent. No downloads, external inference, user browser, resident service or
training Hat is used. All generated fixtures/artifacts remain for inspection.
This is deliberately not a clean-machine or no-assistance release verdict.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import venv


PLAN = {"summary": "Two-step arithmetic integration fixture, not a real product",
        "tracks": [{"name": "Core", "purpose": "Retain working behavior across restart"}],
        "milestones": [
            {"title": "Answer", "track": "Core", "done_when": "app.answer() returns 42"},
            {"title": "Double", "track": "Core", "done_when": "app.double(n) returns twice n and answer() stays 42"}]}
APP1 = "def answer():\n    return 42\n"
APP2 = APP1 + "\ndef double(n):\n    return n * 2\n"
TEST1 = "import unittest\nfrom app import answer\nclass TestAnswer(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(), 42)\n"
TEST2 = "import unittest\nfrom app import double\nclass TestDouble(unittest.TestCase):\n    def test_double(self): self.assertEqual(double(3), 6)\n"
OWNER_MARKER = "PRIVATE_OWNER_ACCEPTANCE_B20_NOT_AUTHOR_CONTEXT"
OWNER1 = f"# {OWNER_MARKER}\nimport unittest\nfrom app import answer\nclass OwnerAnswer(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(), 42)\n"
OWNER2 = f"# {OWNER_MARKER}\nimport unittest\nfrom app import answer, double\nclass OwnerDouble(unittest.TestCase):\n    def test_contract(self):\n        self.assertEqual(answer(), 42)\n        self.assertEqual(double(-7), -14)\n        self.assertEqual(double(0), 0)\n"
DRAFT1 = {"title": "First bounded fixture", "files": [
    {"path": "app.py", "content": APP1}, {"path": "tests/__init__.py", "content": ""},
    {"path": "tests/test_answer.py", "content": TEST1}]}
DRAFT2 = {"title": "Second bounded fixture", "files": [
    {"path": "app.py", "edits": [{"old_text": APP1, "new_text": APP2}]},
    {"path": "tests/test_double.py", "content": TEST2}]}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


@contextmanager
def fixture_provider():
    """Three deterministic completions, independent of the installed runtime."""
    requests = []
    answers = [PLAN, DRAFT1, DRAFT2]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw)
            index = len(requests)
            owner_private = OWNER_MARKER.encode() in raw
            requests.append({"index": index, "path": self.path, "model": body.get("model"),
                             "request_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                             "owner_fixture_marker_exposed": owner_private})
            if owner_private or self.path != "/v1/chat/completions" or index >= len(answers):
                self.send_response(400)
                payload = {"error": "Unexpected scripted fixture request; no more responses"}
            else:
                self.send_response(200)
                payload = {"id": f"fixture-{index}", "model": "offline-installed-fixture",
                           "choices": [{"message": {"content": json.dumps(answers[index])}, "finish_reason": "stop"}]}
            data = json.dumps(payload).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/v1", requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(5)
        assert not thread.is_alive(), "Fixture provider did not stop"


def phase(args):
    """Executed with installed venv Python -I, never imports checkout code."""
    import runesmith
    from runesmith.app import server

    installed = Path(runesmith.__file__).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), str(installed)
    base = Path(args.output_dir).resolve()
    root, home = base / "project with spaces å", base / "isolated home ø" / ".runesmith"
    server.STUDIO_DIR = base / "profile" / "studio"
    # Test confinement only, not a product sandbox claim. Other hosts must never
    # be contacted by this installed test process, including accidental proxies.
    def local_network_only(event, values):
        if event == "socket.connect":
            address = values[1]
            if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1"):
                raise RuntimeError("Installed smoke test blocked a non-loopback connection")
    sys.addaudithook(local_network_only)
    result = {"phase": args.phase, "pid": os.getpid(), "installed_from": str(installed),
              "sys_prefix": sys.prefix, "python_executable": sys.executable, "version": runesmith.__version__,
              "pytest_installed": importlib.util.find_spec("pytest") is not None,
              "jobs": [], "api_actions": [], "state": "running"}
    studio = server.Studio(root, home)
    httpd = server.bind(studio, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    opener = build_opener(ProxyHandler({}))

    def request(method, route, body=None, *, expected=200, epoch=None, cookie=True, raw=False):
        headers = {"Content-Type": "application/json", "X-Runesmith-Workspace": epoch or studio.epoch}
        if cookie:
            headers["Cookie"] = f"rs_session={studio.token}"
        if method != "GET":
            headers["X-Runesmith"] = "1"
        req = Request(f"http://127.0.0.1:{studio.port}{route}", method=method, headers=headers,
                      data=None if body is None else json.dumps(body).encode())
        try:
            with opener.open(req, timeout=15) as response:
                status, payload = response.status, response.read()
        except HTTPError as error:
            status, payload = error.code, error.read()
        if route != "/api/worker" or method != "GET":
            result["api_actions"].append({"method": method, "route": route, "status": status})
        assert status == expected, (route, status, payload[:1000])
        return payload if raw else json.loads(payload or b"null")

    def idle():
        end = time.monotonic() + 45
        while time.monotonic() < end:
            worker = request("GET", "/api/worker")
            if not worker["current"] and not worker["queue"]:
                assert not (worker.get("recovery") or {}).get("required"), worker
                return worker
            time.sleep(.1)
        raise TimeoutError("Disposable worker did not become idle")

    def job(kind, **params):
        queued = request("POST", "/api/worker/run", {"job": kind, "params": params})
        end = time.monotonic() + 90
        while time.monotonic() < end:
            worker = request("GET", "/api/worker")
            found = next((r for r in worker["history"] if r["id"] == queued["id"]), None)
            if found:
                result["jobs"].append(found)
                assert found["result"] == "done", found
                idle()
                outcome = dict(found.get("outcome") or {})
                if outcome.get("draft"):
                    retained = next(d for d in request("GET", "/api/work")["drafts"] if d["id"] == outcome["draft"])
                    outcome["verification"] = retained.get("verification")
                return outcome
            time.sleep(.1)
        raise TimeoutError(f"Bounded fixture job did not finish: {queued['id']}")

    try:
        request("GET", "/api/state", cookie=False, expected=401)
        initial = request("GET", "/api/state")
        assert initial["workspace"]["home"] == str(home)
        assert b"Before you leave it working" in request("GET", "/static/js/views/home.js", raw=True)
        health = request("GET", "/api/health?network=0")
        assert any(r["check"] == "pytest" and r["ok"] is False for r in health["checks"])
        result["initial_settings"] = {k: initial["settings"][k] for k in
                                      ("onboarded", "auto_work", "kaizen", "build_steps", "build_apply")}
        if args.phase == "first":
            assert not initial["ready"]["any"]
            assert not initial["settings"]["onboarded"]
            request("POST", "/api/settings", {"auto_work": False, "kaizen": False, "probe_tests": False})
            request("GET", "/api/genesis")
            request("POST", "/api/genesis", {"name": "Installed fixture", "use_type": "build",
                    "description": "Build app.answer() returning 42, then app.double(n), preserving answer. This is an offline integration fixture."})
            idle()
            request("POST", "/api/inference/instruments", {"name": "fixture-author", "roles": ["plan"],
                    "spec": {"kind": "openai", "base_url": args.provider, "model": "offline-installed-fixture",
                             "json_mode": "object", "timeout_s": 5}})
            job("plan")
            plan = request("GET", "/api/plan")["plan"]
            assert [m["id"] for m in plan["milestones"]] == ["m1", "m2"]
            request("POST", "/api/settings", {"build_steps": True, "build_apply": False,
                                               "build_paths": ["app.py", "tests"]})
            before_source = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            checked = job("build")
            assert checked["verification"]["status"] == "acceptance_passed", checked
            assert not checked.get("advanced") and not (root / "app.py").exists()
            assert before_source == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            request("POST", "/api/settings", {"build_apply": True, "build_paths": ["tests"]})
            refused = job("build")
            assert refused["draft"] == checked["draft"] and not refused.get("advanced")
            assert refused["verification"]["status"] == "acceptance_passed"
            assert before_source == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result["out_of_scope_apply_wrote_nothing"] = True
            request("POST", "/api/settings", {"build_paths": ["app.py", "tests"]})
            applied = job("build")
            assert applied["draft"] == checked["draft"] and applied["advanced"], applied
            assert (root / "app.py").read_text(encoding="utf-8") == APP1
            result["first_draft"] = applied["draft"]
            result["old_epoch"] = studio.epoch  # local fixture marker, not the authentication secret
        elif args.phase == "continue":
            first = json.loads((base / "first.json").read_text(encoding="utf-8"))
            assert initial["settings"]["auto_work"] is False and initial["settings"]["kaizen"] is False
            request("POST", "/api/settings", {"auto_work": True}, epoch=first["old_epoch"], expected=409)
            assert request("GET", "/api/settings")["auto_work"] is False
            assert (root / "app.py").read_text(encoding="utf-8") == APP1
            plan = request("GET", "/api/plan")["plan"]
            assert [m["status"] for m in plan["milestones"]] == ["done", "open"]
            drafts = request("GET", "/api/work")["drafts"]
            assert any(d["id"] == first["first_draft"] and d["state"] == "applied" for d in drafts)
            retained = next(d for d in drafts if d["id"] == first["first_draft"])
            prior = next(d for d in first["drafts"] if d["id"] == retained["id"])
            assert retained["verification"] == prior["verification"]
            assert request("GET", "/api/build")["grant"] == first["final_grant"]["grant"]
            applied = job("build")
            assert applied["advanced"] and applied["milestone"] == "m2", applied
            assert applied["verification"]["project_checks"]["ran"] == 2
            assert applied["verification"]["acceptance"]["ran"] == 2
            assert (root / "app.py").read_text(encoding="utf-8") == APP2
        else:
            assert (root / "app.py").read_text(encoding="utf-8") == APP2
            assert [m["status"] for m in request("GET", "/api/plan")["plan"]["milestones"]] == ["done", "done"]
            saved = request("GET", "/api/work")["drafts"]
            assert len(saved) == 2 and all(d["state"] == "applied" and d["verified"] for d in saved)
            prior = json.loads((base / "continue.json").read_text(encoding="utf-8"))
            assert {d["id"]: d["verification"] for d in saved} == {d["id"]: d["verification"] for d in prior["drafts"]}
            assert request("GET", "/api/build")["grant"] == prior["final_grant"]["grant"]
            outcome = job("build")
            assert "No unfinished milestones" in outcome["summary"]
        idle()
        result["ledger"] = studio.ws.ledger.verify()
        assert result["ledger"]["ok"]
        result["final_plan"] = request("GET", "/api/plan")["plan"]
        result["final_settings"] = request("GET", "/api/settings")
        result["final_grant"] = request("GET", "/api/build")
        result["drafts"] = request("GET", "/api/work")["drafts"]
        result["ordinary_attempts"] = len(list((home / "build-attempts").glob("*.json")))
        result["state"] = "passed"
    except Exception as error:
        result["state"] = "failed"
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        closed = studio.close(timeout=10)
        httpd.shutdown()
        httpd.server_close()
        thread.join(5)
        result["closed"] = closed and not thread.is_alive()
        save(base / f"{args.phase}.json", result)
        assert result["closed"], "Disposable Studio fixture did not close"


def orchestrate(args):
    base = Path(args.output_dir).resolve()
    if base.exists() or not base.parent.is_dir():
        raise ValueError("Use a new output directory under an existing scratch parent; nothing is overwritten")
    base.mkdir()
    root = Path(__file__).resolve().parents[1]
    (base / "profile").mkdir()
    (base / "temp").mkdir()
    source = base / "source"
    source.mkdir()
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(root / name, source / name)
    shutil.copytree(root / "runesmith", source / "runesmith", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "PATHEXT", "COMSPEC", "PROCESSOR_ARCHITECTURE"}}
    env.update(TEMP=str(base / "temp"), TMP=str(base / "temp"), USERPROFILE=str(base / "profile"),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
               NO_PROXY="127.0.0.1,localhost", PIP_DISABLE_PIP_VERSION_CHECK="1")
    receipt = {"state": "running", "output_dir": str(base), "commands": [], "new_external_inference_calls": 0,
               "scope": "Installed Windows artifact + disposable HTTP fixtures, not live-model or human GUI qualification",
               "operator_assistance": ["Harness supplies three deterministic author answers, not a real model",
                                       "Owner acceptance unittest files prepared before launch outside the UI",
                                       "Scheduling and Kaizen explicitly disabled; each bounded action submitted by harness",
                                       "Runtime is created through an ephemeral test fixture, not the double-click launcher"]}

    def run(name, command, cwd=base, timeout=180):
        with (base / f"{name}.log").open("wb") as output:
            completed = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
        receipt["commands"].append({"name": name, "exit_code": completed.returncode})
        print(json.dumps({"step": name, "exit_code": completed.returncode, "artifacts": str(base)}), flush=True)
        if completed.returncode:
            raise RuntimeError(f"{name} failed; retained log: {base / (name + '.log')}")

    try:
        run("wheel", [sys.executable, "-m", "pip", "wheel", str(source), "--no-deps", "--no-build-isolation",
                      "--no-index", "--no-cache-dir", "--wheel-dir", str(base / "wheel")])
        wheel, = (base / "wheel").glob("*.whl")
        receipt["wheel"] = {"path": str(wheel), "sha256": digest(wheel), "bytes": wheel.stat().st_size}
        venv.EnvBuilder(with_pip=True, symlinks=False).create(base / "venv")
        python = base / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run("install", [str(python), "-m", "pip", "install", "--no-index", "--no-deps", "--no-cache-dir", str(wheel)])
        (base / "project with spaces å").mkdir()
        acceptance = base / "isolated home ø" / ".runesmith" / "acceptance"
        acceptance.mkdir(parents=True)
        for name, content in (("m1.py", OWNER1), ("m2.py", OWNER2)):
            (acceptance / name).write_text(content, encoding="utf-8")
        receipt["owner_fixture_hashes"] = {p.name: digest(p) for p in acceptance.glob("*.py")}
        with fixture_provider() as (provider, calls):
            receipt["scripted_local_requests"] = calls
            for name, expected_calls in (("first", 2), ("continue", 3), ("inspect", 3)):
                run(name, [str(python), "-I", str(Path(__file__).resolve()), "--phase", name,
                           "--output-dir", str(base), "--provider", provider])
                assert len(calls) == expected_calls, (name, calls)
            assert all(not call["owner_fixture_marker_exposed"] for call in calls)
        results = [json.loads((base / f"{name}.json").read_text(encoding="utf-8")) for name in ("first", "continue", "inspect")]
        assert len({r["pid"] for r in results}) == 3
        assert [r["ordinary_attempts"] for r in results] == [1, 2, 2]
        assert all(r["closed"] and not r["pytest_installed"] for r in results)
        assert receipt["owner_fixture_hashes"] == {p.name: digest(p) for p in acceptance.glob("*.py")}
        receipt["separate_processes"] = [r["pid"] for r in results]
        receipt["state"] = "passed"
    except Exception as error:
        receipt["state"] = "failed"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        save(base / "receipt.json", receipt)
        print(json.dumps({"state": receipt["state"], "receipt": str(base / "receipt.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--phase", choices=("first", "continue", "inspect"))
    parser.add_argument("--provider")
    args = parser.parse_args()
    phase(args) if args.phase else orchestrate(args)
