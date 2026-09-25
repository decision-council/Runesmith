"""Which kernel affordances an organ uses, and which it leaves unused.

A static scan of an organ's source for cockpit calls. Each unused affordance is
offered to the Kaizen author as an untried mechanism class: a resource already
inside the suit that the current policy does not exploit. This is the classic
Kaizen/TRIZ move of using what is already there before asking for more.

The scan is conservative. It recognises calls on the name of ``run``'s second
parameter (normally ``cockpit``) and a few common aliases. An aliased use can be
missed, and then an affordance is listed as unused although it is used. It never
claims an affordance is used when it is not.
"""

from __future__ import annotations

import ast
from typing import Any

AFFORDANCES: dict[str, str] = {
    "ask": "one model call with a JSON-schema answer",
    "ask(system=...)": "a system message for the model on a call (role, rules, output discipline)",
    "run_signal": "run the failing tests on candidate files: the public signal, as feedback after an edit",
    "run_signal before editing": "run the failing tests before any edit, to read the failure itself first",
    "run_signal(trace=True)": "the source lines the failing tests execute, per file: where the defect can be",
    "budget": "what remains of the envelope (calls, signal runs, seconds), to plan the rest of the attempt",
    "log": "telemetry marks, e.g. reads=[paths], so the diagnosis sees which files were inspected",
    "recall": "Runesmith's own memory of earlier opportunities: what was changed and whether the judge accepted it",
}
ALIASES = {"cockpit", "cp", "ck", "cpit"}


def _receivers(tree: ast.Module) -> set[str]:
    names = set(ALIASES)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run" and len(node.args.args) >= 2:
            names.add(node.args.args[1].arg)
    return names


def _truthy(node: ast.AST) -> bool:
    return not (isinstance(node, ast.Constant) and not node.value)


def audit(source: str) -> dict[str, Any]:
    """``{"used": [...], "unused": [{"affordance", "offers"}...]}`` for one organ source."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return {"used": [], "unused": [], "error": f"syntax error: {error}"}
    receivers = _receivers(tree)
    used: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in receivers):
            continue
        name = node.func.attr
        if name not in ("ask", "run_signal", "budget", "log", "recall"):
            continue
        used.add(name)
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        if name == "ask" and (len(node.args) >= 4 or ("system" in keywords and _truthy(keywords["system"]))):
            used.add("ask(system=...)")
        if name == "run_signal":
            if (len(node.args) >= 2 and _truthy(node.args[1])) or ("trace" in keywords and _truthy(keywords["trace"])):
                used.add("run_signal(trace=True)")
            files = node.args[0] if node.args else keywords.get("files")
            if files is None or (isinstance(files, ast.Constant) and files.value is None):
                used.add("run_signal before editing")          # no overriding files: the failure as it stands
    return {"used": [k for k in AFFORDANCES if k in used],
            "unused": [{"affordance": k, "offers": v} for k, v in AFFORDANCES.items() if k not in used]}
