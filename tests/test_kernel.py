"""Kernel tests: ledger integrity, organ confinement, opportunities and generations."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from runesmith import generations
from runesmith.instruments import CallOutcome, Router, ScriptedInstrument, classify
from runesmith.ledger import Ledger
from runesmith.objects.code import CodeTask
from runesmith.opportunity import Envelope, run_opportunity, stage_profile
from runesmith.sandbox import run_organ

ORGANS = Path(__file__).resolve().parents[1] / "runesmith" / "organs"


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    (repo / "src" / "calc").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "calc" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "calc" / "ops.py").write_text(textwrap.dedent('''
        def add(a, b):
            return a - b


        def double(x):
            return add(x, x)
    ''').lstrip(), encoding="utf-8")
    (repo / "tests" / "test_ops.py").write_text(textwrap.dedent('''
        from calc.ops import add, double

        def test_add():
            assert add(2, 3) == 5

        def test_double():
            assert double(4) == 8
    ''').lstrip(), encoding="utf-8")
    return repo


# ------------------------------------------------------------------ ledger --

def test_ledger_chain_detects_tampering(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for i in range(5):
        ledger.append("test.event", {"i": i})
    assert ledger.verify() == {"ok": True, "records": 5, "head": ledger.head}
    reopened = Ledger(tmp_path / "ledger.jsonl")
    assert reopened.head == ledger.head
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="ascii").splitlines()
    lines[2] = lines[2].replace('"i":2', '"i":7')
    (tmp_path / "ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="ascii")
    report = Ledger(tmp_path / "ledger.jsonl").verify()
    assert report["ok"] is False and "seq 3" in report["error"]


def test_tolerant_json_accepts_prose_wrapped_answers_only_when_asked():
    from runesmith.instruments import parse_json_answer
    chatty = 'Sure! Here is the fix:\n{"edits": [{"path": "src/a.py", "old_text": "x", "new_text": "y"}]}\nHope it helps.'
    assert parse_json_answer(chatty, tolerant=True)["edits"][0]["path"] == "src/a.py"
    with pytest.raises(json.JSONDecodeError):
        parse_json_answer(chatty)
    assert parse_json_answer('```json\n{"reads": []}\n```') == {"reads": []}


def test_classify_is_transport_first():
    assert classify("connection reset while reading truncated body") == "transport"
    assert classify("every route failed - model truncated") == "output"
    assert classify("something odd") == "transport"


# -------------------------------------------------------------- confinement --

def _organ(tmp_path: Path, body: str) -> Path:
    organ_dir = tmp_path / "organ"
    organ_dir.mkdir(exist_ok=True)
    (organ_dir / "probe.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return organ_dir


def test_organ_rpc_round_trip(tmp_path):
    organ_dir = _organ(tmp_path, '''
        def run(view, cockpit):
            print("organ prints go to stderr, not the protocol")
            answer = cockpit.call("echo", value=view["x"] * 2)
            return {"status": "done", "echo": answer}
    ''')
    outcome = run_organ(organ_dir, "probe", {"x": 21}, {"echo": lambda args: args["value"]},
                        wall_s=60, scratch=tmp_path / "scratch")
    assert outcome["ok"], outcome
    assert outcome["result"] == {"status": "done", "echo": 42}


@pytest.mark.parametrize("attack", [
    "open(r'%s').read()",
    "open('written.txt', 'w').write('x')",
    "__import__('socket').create_connection(('127.0.0.1', 9))",
    "__import__('subprocess').run(['cmd', '/c', 'echo hi'])",
    "__import__('os').listdir(r'%s')",
    "__import__('gc').get_objects()",                       # introspection could widen the guard's own allow-list
    "__import__('_interpreters')",                           # a sub-interpreter would run without this guard
    "__import__('ctypes')",                                  # native calls
    pytest.param("__import__('_winapi').OpenProcess(0x1000, False, __import__('os').getpid())",
                 marks=pytest.mark.skipif(sys.platform != "win32", reason="Windows API"),
                 id="winapi-open-process"),                  # the first step to killing other processes
])
def test_organ_confinement_refuses_escapes(tmp_path, attack):
    secret = tmp_path / "secret.txt"
    secret.write_text("hidden judge", encoding="utf-8")
    code = attack % secret if attack.count("%s") == 1 and "listdir" not in attack else attack
    if "listdir" in attack:
        code = attack % tmp_path
    organ_dir = _organ(tmp_path, f'''
        def run(view, cockpit):
            {code}
            return {{"status": "escaped"}}
    ''')
    outcome = run_organ(organ_dir, "probe", {}, {}, wall_s=60, scratch=tmp_path / "scratch")
    assert not outcome["ok"], outcome
    assert outcome["error_type"] == "PermissionError", outcome


def test_organ_cannot_see_secrets_in_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNESMITH_TEST_SECRET", "sk-should-not-leak")
    organ_dir = _organ(tmp_path, '''
        import os
        def run(view, cockpit):
            return {"status": "ok", "leak": os.environ.get("RUNESMITH_TEST_SECRET")}
    ''')
    outcome = run_organ(organ_dir, "probe", {}, {}, wall_s=60, scratch=tmp_path / "scratch")
    assert outcome["ok"] and outcome["result"]["leak"] is None


def test_organ_wall_clock_is_enforced(tmp_path):
    organ_dir = _organ(tmp_path, '''
        import time
        def run(view, cockpit):
            time.sleep(30)
    ''')
    outcome = run_organ(organ_dir, "probe", {}, {}, wall_s=2, scratch=tmp_path / "scratch")
    assert outcome["error_type"] == "Timeout"


# ------------------------------------------------------------ opportunities --

def _router(answers):
    return Router({"y": ScriptedInstrument("y", answers)}, {"repair": "y"}, backoff_s=(0, 0), sleep=lambda s: None)


def test_repair_organ_g0_fixes_a_simple_regression(tmp_path):
    repo = make_repo(tmp_path)
    task = CodeTask(repo, ["tests/test_ops.py::test_add"], scratch=tmp_path / "scratch")
    try:
        router = _router([
            {"reads": [{"path": "src/calc/ops.py", "symbols": ["add"]}]},
            {"edits": [{"path": "src/calc/ops.py", "old_text": "return a - b", "new_text": "return a + b"}]},
        ])
        record = run_opportunity(task=task, issue="add() returns the wrong value", organ_dir=ORGANS,
                                 router=router, envelope=Envelope(), key="t1", scratch=tmp_path / "scratch")
        assert record["status"] == "public_pass", record
        assert record["model_calls"] == 2 and record["public_runs"] == 1
        assert "return a + b" in (task.current_src_dir() / "calc" / "ops.py").read_text(encoding="utf-8")
        profile = stage_profile(record)
        assert profile["cycle_s"] >= profile["model_s"] + profile["signal_s"] - 1e-6
    finally:
        task.close()


def test_navigation_output_failure_ends_g0_session(tmp_path):
    repo = make_repo(tmp_path)
    task = CodeTask(repo, ["tests/test_ops.py::test_add"], scratch=tmp_path / "scratch")
    try:
        router = _router([CallOutcome(False, error_kind="output", error="truncated")])
        record = run_opportunity(task=task, issue="add() is wrong", organ_dir=ORGANS, router=router,
                                 envelope=Envelope(), key="t2", scratch=tmp_path / "scratch")
        assert record["status"] == "navigation_output_failure"
        assert record["model_calls"] == 1
    finally:
        task.close()


def test_envelope_refuses_extra_calls_and_censors_transport(tmp_path):
    repo = make_repo(tmp_path)
    task = CodeTask(repo, ["tests/test_ops.py::test_add"], scratch=tmp_path / "scratch")
    greedy = _organ(tmp_path, '''
        def run(view, cockpit):
            used = 0
            try:
                while True:
                    cockpit.ask({"q": used}, None, "probe")
                    used += 1
            except Exception as error:
                return {"status": "refused", "detail": str(error), "final_files": {}, "used": used}
    ''')
    try:
        router = _router([{"a": 1}] * 10)
        record = run_opportunity(task=task, issue="x", organ_dir=greedy, module="probe", router=router,
                                 envelope=Envelope(max_calls=3), key="t3", scratch=tmp_path / "scratch")
        assert record["status"] == "refused" and record["model_calls"] == 3
        down = Router({"y": ScriptedInstrument("y", [])}, {"repair": "y"}, backoff_s=(0,), sleep=lambda s: None)
        record = run_opportunity(task=task, issue="x", organ_dir=greedy, module="probe", router=down,
                                 envelope=Envelope(), key="t4", scratch=tmp_path / "scratch")
        assert record["status"] == "censored_transport"
    finally:
        task.close()


# -------------------------------------------------------------- generations --

def test_generation_freeze_verify_activate(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    g0 = generations.freeze(ORGANS, home, label="g0", provenance={"lineage": "human_authored"})
    assert generations.verify(Path(g0["path"]))["ok"]
    generations.activate(home, g0["id"], expected=None)
    assert generations.active(home) == g0["id"]
    with pytest.raises(generations.GenerationError):
        generations.activate(home, g0["id"], expected="someone-else")
    organ_file = Path(g0["path"]) / "organs" / "repair.py"
    organ_file.write_text(organ_file.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    assert not generations.verify(Path(g0["path"]))["ok"]


def test_trace_reports_the_lines_the_failing_test_executes(tmp_path):
    """The affordance the audit offers: run_signal(trace=True) must point at the defect's lines."""
    repo = make_repo(tmp_path)
    (repo / "src" / "calc" / "unused.py").write_text("def never():\n    return 1\n", encoding="utf-8")
    task = CodeTask(repo, ["tests/test_ops.py::test_add"], scratch=tmp_path / "scratch")
    try:
        result = task.run(trace=True)
    finally:
        task.close()
    assert result["passed"] is False
    executed = result["executed_src_lines"]
    assert 2 in executed["src/calc/ops.py"]                    # `return a - b`, the defect, ran
    assert 6 not in executed["src/calc/ops.py"]                # double()'s body did not run for test_add
    assert "src/calc/unused.py" not in executed                # never imported, never traced


def test_sources_and_docs_use_lf_line_endings():
    """Digests are over bytes, and the project is cross-platform: every text file uses LF."""
    root = Path(__file__).resolve().parents[1]
    offenders = [p.relative_to(root).as_posix() for p in sorted(root.rglob("*"))
                 if p.is_file() and p.suffix in (".py", ".md", ".toml") and b"\r\n" in p.read_bytes()
                 and not {".tmp", ".demo-home", "__pycache__"} & set(p.relative_to(root).parts)]
    assert offenders == []


def test_recall_is_always_granted_and_empty_without_memory(tmp_path):
    """The contract promises recall; a host without memory returns an empty list instead of refusing."""
    repo = make_repo(tmp_path)
    task = CodeTask(repo, ["tests/test_ops.py::test_add"], scratch=tmp_path / "scratch")
    remembering = _organ(tmp_path, '''
        def run(view, cockpit):
            hits = cockpit.recall("add returns a wrong value", k=3)
            return {"status": "recalled", "detail": repr(hits), "final_files": {}}
    ''')
    try:
        without = run_opportunity(task=task, issue="x", organ_dir=remembering, module="probe", router=_router([]),
                                  envelope=Envelope(), key="r1", scratch=tmp_path / "scratch")
        assert without["status"] == "recalled" and without["detail"] == "[]"
        with_memory = run_opportunity(task=task, issue="x", organ_dir=remembering, module="probe", router=_router([]),
                                      envelope=Envelope(), key="r2", scratch=tmp_path / "scratch",
                                      recall=lambda query, k: [{"text": "fixed add by + instead of -"}])
        assert "fixed add" in with_memory["detail"]
    finally:
        task.close()


def test_ledger_stays_chained_when_instances_threads_and_processes_share_it(tmp_path):
    import subprocess
    import threading
    path = tmp_path / "ledger.jsonl"
    first, second = Ledger(path), Ledger(path)                    # both cache the same (empty) tail
    first.append("a")
    second.append("b")                                            # must chain onto "a", not onto genesis
    first.append("c")
    assert Ledger(path).verify() == {"ok": True, "records": 3, "head": Ledger(path).head}

    def writer(n: int) -> None:
        own = Ledger(path)
        for i in range(25):
            own.append("thread", {"writer": n, "i": i})
    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert Ledger(path).verify()["ok"] and Ledger(path).verify()["records"] == 103

    code = ("import sys; sys.path.insert(0, sys.argv[2]); from runesmith.ledger import Ledger\n"
            "ledger = Ledger(sys.argv[1])\n"
            "for i in range(20): ledger.append('process', {'i': i})\n")
    root = str(Path(__file__).resolve().parents[1])
    procs = [subprocess.Popen([sys.executable, "-c", code, str(path), root]) for _ in range(2)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    report = Ledger(path).verify()
    assert report["ok"] and report["records"] == 143


def test_organ_cannot_flood_the_disk_through_stderr(tmp_path):
    organ_dir = _organ(tmp_path, '''
        import sys, time
        def run(view, cockpit):
            for _ in range(40):
                sys.stderr.write("x" * 100_000)
                sys.stderr.flush()
            time.sleep(20)
    ''')
    outcome = run_organ(organ_dir, "probe", {}, {}, wall_s=30, scratch=tmp_path / "scratch", max_stderr_bytes=1_000_000)
    assert outcome["ok"] is False and outcome["error_type"] == "OutputFlood", outcome
    assert outcome["elapsed_s"] < 15


def test_organ_cannot_exhaust_host_memory_with_one_endless_line(tmp_path):
    organ_dir = _organ(tmp_path, '''
        import os, time
        def run(view, cockpit):
            chunk = b"x" * 1_000_000
            for _ in range(12):
                os.write(1, chunk)                              # the protocol pipe, never a newline
            time.sleep(20)
    ''')
    outcome = run_organ(organ_dir, "probe", {}, {}, wall_s=30, scratch=tmp_path / "scratch")
    assert outcome["ok"] is False and outcome["error_type"] == "OutputTooLarge", outcome
    assert outcome["elapsed_s"] < 15                                    # detected while writing, not at exit
