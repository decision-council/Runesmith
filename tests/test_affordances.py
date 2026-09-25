"""The affordance audit: what an organ leaves unused becomes a Kaizen option, never a false claim."""

from __future__ import annotations

import textwrap

from runesmith import cli
from runesmith.kaizen.affordances import AFFORDANCES, audit
from runesmith.kaizen.improve import author_packet, render_author_prompt
from runesmith.local import change_summary
from runesmith.opportunity import Envelope
from runesmith.organs import repair
from runesmith.selfmap import build_self_map


def _unused(source: str) -> set[str]:
    return {u["affordance"] for u in audit(source)["unused"]}


def test_g0_leaves_trace_recall_budget_and_system_unused():
    source = open(repair.__file__, encoding="utf-8").read()
    result = audit(source)
    assert result["used"] == ["ask", "run_signal", "log"]
    assert {"run_signal(trace=True)", "recall", "budget", "ask(system=...)", "run_signal before editing"} == _unused(source)


def test_audit_recognises_each_affordance_and_the_run_parameter_name():
    source = textwrap.dedent('''
        def run(view, cp):
            first = cp.run_signal(trace=True)
            cp.budget()
            cp.recall("similar failures", k=3)
            answer = cp.ask({"x": 1}, {}, "navigate", system="be exact")
            cp.log("reads", reads=["src/a.py"])
            return {"status": "gave_up", "final_files": {}}
    ''')
    assert _unused(source) == set()


def test_audit_does_not_count_other_objects_or_false_flags():
    source = textwrap.dedent('''
        import math

        def run(view, cockpit):
            math.log(2.0)
            cockpit.run_signal(files={"src/a.py": "x"}, trace=False)
            return {"status": "gave_up", "final_files": {}}
    ''')
    unused = _unused(source)
    assert "log" in unused                      # math.log is not the cockpit's log
    assert "run_signal(trace=True)" in unused   # trace=False is not a trace
    assert "run_signal before editing" in unused
    assert audit("def run(:\n")["error"].startswith("syntax error")


def test_author_packet_carries_the_audit_and_the_contract_documents_recall():
    source = open(repair.__file__, encoding="utf-8").read()
    diagnosis = {"targets": [], "uncensored": 0, "strict_successes": 0, "yield": None, "median_cycle_s": None,
                 "seconds_per_success": None, "calls_per_opportunity": None, "value_stream": {}, "families": [],
                 "false_promotions": 0}
    packet = author_packet(target={"type": "yield"}, diagnosis=diagnosis, incumbent_source=source, examples=[],
                           attempts=[], envelope=Envelope(), module="repair")
    unused = {u["affordance"] for u in packet["affordance_audit"]["unused"]}
    assert "run_signal(trace=True)" in unused and "recall" in unused
    prompt = render_author_prompt(packet)
    assert "affordance_audit" in prompt and "cockpit.recall(query, k=5)" in prompt


def test_self_map_lists_unused_affordances_as_improvement_options(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    options = build_self_map(home=home)["improvement_options"]
    assert "repair" in options
    assert {u["affordance"] for u in options["repair"]["unused_affordances"]} <= set(AFFORDANCES)


def test_change_summary_keeps_what_was_tried_bounded():
    parent = {"src/a.py": "def f(x):\n    return x - 1\n"}
    final = {"src/a.py": "def f(x):\n    return x + 1\n"}
    text = change_summary(parent, final)
    assert "-    return x - 1" in text and "+    return x + 1" in text
    big = {"src/a.py": "\n".join(f"line {i}" for i in range(2000))}
    assert len(change_summary({"src/a.py": ""}, big)) <= 1204
