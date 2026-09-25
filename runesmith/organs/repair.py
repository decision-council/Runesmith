"""Repair organ, generation 0: the Runesmith v1 repair policy.

This organ is a faithful port of Runesmith v1 — the generic navigate → edit →
public-feedback loop that served as the SR3/SR4 comparator — so that the first
Runesmith Core generation starts from the measured v1 policy rather than from a
policy tuned in advance. It is deliberately *mutable*: the Kaizen engine may
rewrite this file, and a rewritten copy becomes a new generation only after
qualification.

Contract (fixed by the kernel, not by this file):

* ``run(view, cockpit) -> dict`` is called once per repair opportunity.
* ``view`` holds ``issue``, ``failing_tests``, ``src_files`` (path -> text),
  ``src_sizes`` (path -> bytes on disk) and ``caps``; nothing else about the
  object is visible.
* ``cockpit.ask(packet, schema, purpose)`` makes one model call (charged even
  when the answer is unusable); ``cockpit.run_signal(files, trace)`` runs the
  object's public tests with ``files`` overriding the originals;
  ``cockpit.budget()`` reports what remains; ``cockpit.log(stage, **data)``
  records a telemetry mark.
* The return value names a ``status`` and the ``final_files`` to be judged.

Standard library only; the organ runs confined and cannot import the kernel.
"""

import ast
import copy
import json

ORGAN = "repair"
ORGAN_VERSION = "repair-g0 (Runesmith v1 policy port)"

STRING = {"type": "string"}
NAV_SCHEMA = {"type": "object", "properties": {"reads": {"type": "array", "items": {
    "type": "object", "properties": {"path": STRING, "symbols": {"type": "array", "items": STRING}},
    "required": ["path", "symbols"], "additionalProperties": False}}},
    "required": ["reads"], "additionalProperties": False}
EDIT_SCHEMA = {"type": "object", "properties": {"edits": {"type": "array", "items": {
    "type": "object", "properties": {"path": STRING, "old_text": STRING, "new_text": STRING},
    "required": ["path", "old_text", "new_text"], "additionalProperties": False}}},
    "required": ["edits"], "additionalProperties": False}
MAX_MODEL_CALLS = 5
MAX_INDEXED_FILE_BYTES = 120_000


# ------------------------------------------------------------------ packets --

def canonical(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def canonical_bytes(payload):
    return len(canonical(payload).encode("utf-8"))


def fit_rows(payload, key, cap):
    fitted = copy.deepcopy(payload)
    while canonical_bytes(fitted) > cap and fitted[key]:
        fitted[key].pop()
    if canonical_bytes(fitted) > cap:
        raise ValueError("fixed packet fields exceed the byte cap")
    return fitted


def fit_segments(payload, cap):
    fitted = copy.deepcopy(payload)
    packets = fitted["source_packets"]
    while canonical_bytes(fitted) > cap and packets:
        last = packets[-1]
        if last.get("source_segments"):
            last["source_segments"].pop()
        else:
            packets.pop()
    if canonical_bytes(fitted) > cap or not packets:
        raise ValueError("edit packet cannot fit the byte cap")
    return fitted


def navigation_packet(issue, index):
    return {
        "task": "Inspect this parent source index; choose at most four files and up to three exact symbols per file to read before editing.",
        "issue": issue,
        "source_index": index,
        "output": {"reads": [{"path": "src/example.py", "symbols": ["function_name"]}]},
        "constraints": ["Choose only listed parent paths and symbols.",
                        "No tests, Git history or solution is available."],
    }


def edit_packet(issue, snippets):
    return {
        "task": "Implement the issue using exact old_text/new_text source edits; no tests are visible.",
        "issue": issue, "source_packets": snippets,
        "constraints": ["Edit only the source paths shown in source_packets.",
                        "Each old_text must occur exactly once in the original full file.",
                        "Copy old_text only from source_segments[].source; metadata is not code.",
                        "Review callers and downstream behavior visible in these snippets.",
                        "Return an empty edits list if the visible source cannot justify a change."],
        "output": {"edits": [{"path": "src/example.py", "old_text": "exact original text",
                              "new_text": "replacement text"}]},
    }


# ---------------------------------------------------------------- selector --

def _path_key(path):
    return tuple(part.lower() for part in path.split("/"))


def source_index(files, sizes):
    """One row per parseable src/*.py file: its top-level symbols."""
    rows = []
    for path in sorted((p for p in files if p.startswith("src/") and p.endswith(".py")), key=_path_key):
        if sizes.get(path, len(files[path].encode("utf-8"))) > MAX_INDEXED_FILE_BYTES:
            continue
        try:
            tree = ast.parse(files[path])
        except (SyntaxError, ValueError):
            continue
        symbols = [node.name for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        rows.append({"path": path, "symbols": symbols, "read_only": False})
    return rows


def requested_excerpt(path, text, symbols, max_chars=6000):
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    header = ""
    for line in lines[:25]:
        if len(header) + len(line) > min(900, max_chars):
            break
        header += line
    output = [{"kind": "module_header", "start_line": 1, "source": header}]
    used = len(header)
    selected_nodes = []
    for name in symbols:
        found = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and node.name == name and hasattr(node, "end_lineno")]
        if not found:
            output.append({"kind": "missing_symbol", "name": name})
            continue
        node = sorted(found, key=lambda value: (value.lineno, value.end_lineno))[0]
        selected_nodes.append(node)
        body_lines = lines[node.lineno - 1:node.end_lineno]
        body = "".join(body_lines)
        remaining = max_chars - used
        if remaining < 300:
            break
        if len(body) <= remaining:
            output.append({"kind": "symbol", "name": name, "start_line": node.lineno, "source": body})
            used += len(body)
            continue
        prefix_lines = []
        prefix_budget = remaining * 2 // 3
        for line in body_lines:
            if sum(map(len, prefix_lines)) + len(line) > prefix_budget:
                break
            prefix_lines.append(line)
        suffix_lines = []
        suffix_budget = remaining - sum(map(len, prefix_lines))
        for line in reversed(body_lines[len(prefix_lines):]):
            if sum(map(len, suffix_lines)) + len(line) > suffix_budget:
                break
            suffix_lines.append(line)
        if prefix_lines:
            output.append({"kind": "symbol_prefix", "name": name, "start_line": node.lineno,
                           "source": "".join(prefix_lines), "truncated": True})
            used += sum(map(len, prefix_lines))
        if suffix_lines:
            output.append({"kind": "symbol_suffix", "name": name,
                           "start_line": node.end_lineno - len(suffix_lines) + 1,
                           "source": "".join(reversed(suffix_lines)), "truncated": True})
            used += sum(map(len, suffix_lines))
    # Two bounded same-module dependency hops.
    if path.startswith("src/"):
        top_level = {node.name: node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and hasattr(node, "end_lineno")}
        seen = set(symbols)
        frontier = selected_nodes
        for depth in range(1, 3):
            counts = {}
            for node in frontier:
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        name = child.func.id
                        if name in top_level and name not in seen:
                            counts[name] = counts.get(name, 0) + 1
            next_frontier = []
            for name in sorted(counts, key=lambda value: (-counts[value], value)):
                seen.add(name)
                node = top_level[name]
                body = "".join(lines[node.lineno - 1:node.end_lineno])
                if used + len(body) > max_chars:
                    continue
                output.append({"kind": "dependency", "depth": depth, "name": name,
                               "start_line": node.lineno, "source": body})
                used += len(body)
                next_frontier.append(node)
            frontier = next_frontier
    return output


def normalize_navigation(files, catalog, navigation):
    """Compile model-proposed reads into bounded exact source packets."""
    reads = navigation.get("reads", [])
    if not isinstance(reads, list) or not reads:
        raise ValueError("invalid navigation reads")
    snippets, allowed = [], set()
    for item in reads[:4]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        path, symbols = item["path"], item.get("symbols", [])
        if path not in catalog:
            continue
        if not isinstance(symbols, list):
            symbols = []
        valid = [name for name in symbols if isinstance(name, str) and name in catalog[path]["symbols"]][:3]
        if not catalog[path]["read_only"]:
            allowed.add(path)
        snippets.append({"path": path, "read_only": catalog[path]["read_only"],
                         "source_segments": requested_excerpt(path, files[path], valid)})
    if not snippets or not allowed:
        raise ValueError("navigation yielded no editable source paths")
    return snippets, allowed


# -------------------------------------------------------------------- edits --

def apply_edits(current, edits, allowed):
    """All-or-nothing exact edits against the current file texts; returns changed texts."""
    if not isinstance(edits, list) or not 1 <= len(edits) <= 6:
        raise ValueError("invalid edit count")
    staged = {}
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {"path", "old_text", "new_text"}:
            raise ValueError("invalid edit schema")
        path, old, new = edit["path"], edit["old_text"], edit["new_text"]
        if path not in allowed or not isinstance(old, str) or not isinstance(new, str) or not old or old == new:
            raise ValueError("edit outside delivered source or no-op")
        text = staged.get(path, current[path])
        if text.count(old) != 1:
            raise ValueError("old_text did not match exactly once in the current file")
        staged[path] = text.replace(old, new, 1)
    return staged


# ---------------------------------------------------------------------- run --

def run(view, cockpit):
    issue = view["issue"]
    files = view["src_files"]
    caps = view["caps"]
    state = {}                      # cumulative overrides: path -> current full text
    calls = 0
    cockpit.log("index")
    index = source_index(files, view.get("src_sizes", {}))
    nav_packet = fit_rows(navigation_packet(issue, index), "source_index", caps["nav_cap_bytes"])
    cockpit.log("navigate", indexed=len(index), delivered=len(nav_packet["source_index"]))
    navigation = cockpit.ask(nav_packet, NAV_SCHEMA, "navigate")
    calls += 1
    if not navigation["ok"]:
        return {"status": "navigation_output_failure", "final_files": state,
                "detail": navigation.get("error")}
    catalog = {row["path"]: row for row in nav_packet["source_index"]}
    try:
        snippets, _ = normalize_navigation(files, catalog, navigation["data"])
    except Exception as error:  # v1 treated any selector failure as a rejected navigation
        return {"status": "navigation_rejected", "final_files": state, "detail": str(error)[:300]}
    try:
        packet0 = fit_segments(edit_packet(issue, snippets), caps["edit_cap_bytes"])
    except ValueError as error:
        return {"status": "instrument_subject_failure", "final_files": state, "detail": str(error)[:300]}
    allowed = {item["path"] for item in packet0["source_packets"]}
    cockpit.log("edit_loop", reads=sorted(allowed))
    packet, feedback, last_edits, edited = packet0, None, None, set()
    while calls < MAX_MODEL_CALLS:
        if feedback is not None:
            packet = {"task": "Your previous edit did not fix the failing tests. Use the feedback and the current source to propose corrected exact old_text/new_text edits.",
                      "issue": issue, "source_packets": packet0["source_packets"],
                      "current_files": {p: state.get(p, files[p])[:12000] for p in sorted(edited)},
                      "previous_edits": last_edits, "feedback": feedback,
                      "constraints": packet0["constraints"], "output": packet0["output"]}
            try:
                packet = fit_rows(packet, "source_packets", caps["edit_cap_bytes"] + 16000)
            except ValueError as error:
                return {"status": "instrument_subject_failure", "final_files": state, "detail": str(error)[:300]}
        answer = cockpit.ask(packet, EDIT_SCHEMA, "edit" if feedback is None else f"retry{calls}")
        calls += 1
        if not answer["ok"]:
            feedback = {"kind": "output_failure", "detail": answer.get("error")}
            continue
        last_edits = answer["data"].get("edits")
        try:
            current = {p: state.get(p, files[p]) for p in allowed}
            changed = apply_edits(current, last_edits, allowed)
        except ValueError as error:
            feedback = {"kind": "edit_rejected", "detail": str(error)}
            continue
        state.update(changed)
        edited.update(changed)
        result = cockpit.run_signal(files=state)
        if result["passed"]:
            return {"status": "public_pass", "final_files": state}
        feedback = {"kind": "public_tests_failed", "signal_lines": result["signal_lines"]}
    return {"status": "budget_exhausted", "final_files": state}
