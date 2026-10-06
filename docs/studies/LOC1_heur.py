"""LOC1 comparator HEUR: a model-free localization composition of the failure text AND the execution trace.

Written for LOC1 (2026-10-06) next to SR6-W's DIRECT (`baseline_organ/direct.py`) as the arm the record's comparator rule
asks for (paper sections 5.1.2 and 6.1): "the strongest model-free composition of the failure text and the trace". It is
fixed before the LOC1 seal and never tuned on a LOC1 task. It differs from DIRECT only in how the model's view is chosen:

* one traced run of the failing tests (the same kernel affordance C7 uses, `cockpit.run_signal(trace=True)`), giving the
  source lines the failing test executed; no other signal run is spent on localization, and no candidate fix is tried
  without the model (no mutation search);
* a deterministic ranking of the source files that composes
  - the trace: files whose function or method BODIES executed (lines run at import time do not count), and how many;
  - the test-to-module mapping: the failing test file's name (`tests/.../test_text.py` -> `text.py`), its folders, the test
    class and the test function name, matched against each file's path words;
  - the symbols named in the failure text (issue excerpt and the traced run's FAILED/E lines): dotted module paths,
    class and function names, matched exactly against each file's module path and defined names;
  - the executed functions' names matched against the test name;
* a view of the top-ranked files up to the same 32,000-byte edit cap as DIRECT: a small file (at most 3,000 characters)
  whole, a larger file as its module header plus the full source of every function or method whose body executed,
  name-matched ones first; and a short localization note naming the ranked files and their executed functions;
* all five model calls spent on edits, with DIRECT's exact-edit rule and DIRECT's public-test feedback loop.

If the trace is empty (the run could not be traced), the ranking falls back to the failure-text tiers alone and whole files
in DIRECT's manner. Standard library only; it runs confined like any organ.
"""

import ast
import copy
import json
import re

ORGAN = "heur"
STRING = {"type": "string"}
EDIT_SCHEMA = {"type": "object", "properties": {"edits": {"type": "array", "items": {
    "type": "object", "properties": {"path": STRING, "old_text": STRING, "new_text": STRING},
    "required": ["path", "old_text", "new_text"], "additionalProperties": False}}},
    "required": ["edits"], "additionalProperties": False}
MAX_MODEL_CALLS = 5
WHOLE_FILE_CHARS = 3000
HEADER_CHARS = 900
NOTE_FILES = 12
WORD = re.compile(r"[a-z][a-z0-9]+")
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b")
TEST_ID = re.compile(r"^\s*-\s+(\S+\.py)(::\S+)?\s*$", re.M)
STOP = {"test", "tests", "src", "py", "the", "and", "for", "assert", "self", "none", "true", "false", "where",
        "failed", "error", "with", "from", "import", "def", "class", "return", "this", "that", "init", "main",
        "assertionerror", "typeerror", "valueerror", "keyerror", "attributeerror", "indexerror", "not", "len", "str",
        "int", "list", "dict", "set", "get", "obj", "value", "values", "args", "kwargs", "result", "expected"}


def canonical_bytes(payload):
    return len(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def words(text):
    out = set()
    for token in WORD.findall(text.replace("_", " ").lower()):
        if len(token) > 2 and token not in STOP:
            out.add(token)
    return out


def split_camel(name):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)


# ------------------------------------------------------------------ failure text --

def parse_failure(text):
    """Test files, test-name words, and the identifiers the failure text names."""
    test_files, name_words, test_words = [], set(), set()
    for match in TEST_ID.finditer(text):
        path, rest = match.group(1).replace("\\", "/"), match.group(2) or ""
        test_files.append(path)
        parts = path.split("/")
        stem = parts[-1][:-3]
        for chunk in parts[:-1] + [stem[5:] if stem.startswith("test_") else stem]:
            test_words |= words(chunk)
        for piece in rest.split("::"):
            piece = piece.split("[")[0]
            if piece.startswith("Test"):
                name_words |= words(split_camel(piece[4:]))
            elif piece.startswith("test_"):
                name_words |= words(piece[5:])
    for line in text.splitlines():
        if line.strip().startswith("FAILED "):
            node = line.strip().split()[1]
            for piece in node.split("::")[1:]:
                piece = piece.split("[")[0]
                if piece.startswith("test_"):
                    name_words |= words(piece[5:])
    idents = set(IDENT.findall(text))
    dotted = {i for i in idents if "." in i}
    names = {i for i in idents if len(i) > 3 and i.lower() not in STOP}
    for d in dotted:
        names |= {p for p in d.split(".") if len(p) > 3 and p.lower() not in STOP}
    test_stems = set()
    for path in test_files:
        stem = path.split("/")[-1][:-3]
        test_stems.add(stem[5:] if stem.startswith("test_") else stem)
    return {"test_files": test_files, "test_stems": test_stems, "test_words": test_words, "name_words": name_words,
            "dotted": dotted, "names": names}


# ------------------------------------------------------------------- source units --

def units_of(text):
    """Top-level functions, and methods of top-level (and once-nested) classes: (qualname, def_line, body_start, end)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None, []
    out = []

    def add(node, prefix):
        if not hasattr(node, "end_lineno") or not node.body:
            return
        out.append((prefix + node.name, node.lineno, node.body[0].lineno, node.end_lineno))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, "")
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(child, node.name + ".")
                elif isinstance(child, ast.ClassDef):
                    for grand in child.body:
                        if isinstance(grand, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            add(grand, node.name + "." + child.name + ".")
    return tree, out


def defined_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def module_of(path):
    parts = path[len("src/"):-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def rank(files, failure, executed):
    """Rank the src .py files; returns rows (path, score, executed units, units) best first."""
    rows = []
    for path, text in files.items():
        if not (path.startswith("src/") and path.endswith(".py")):
            continue
        tree, units = units_of(text)
        if tree is None:
            continue
        lines = executed.get(path, set())
        hit_units = []
        body_lines = 0
        for unit in units:
            name, _def, start, end = unit
            n = sum(1 for ln in lines if start <= ln <= end)
            if n:
                hit_units.append((unit, n))
                body_lines += n
        module = module_of(path)
        stem = path.rsplit("/", 1)[-1][:-3]
        path_words = words(path[len("src/"):-3].replace("/", " "))
        symbols = defined_names(tree)
        named_module = any(d == module or d.startswith(module + ".") for d in failure["dotted"]) if module else False
        stem_match = stem in failure["test_stems"] or (stem == "__init__" and module.rsplit(".", 1)[-1] in failure["test_stems"])
        word_overlap = len(path_words & (failure["test_words"] | failure["name_words"]))
        named_symbols = len(symbols & failure["names"])
        unit_name_overlap = sum(1 for (u, _n) in hit_units if words(u[0].rsplit(".", 1)[-1]) & failure["name_words"])
        score = (100 * (body_lines > 0) + 30 * named_module + 20 * stem_match + 6 * min(word_overlap, 4)
                 + 8 * min(named_symbols, 3) + 5 * min(unit_name_overlap, 4) + min(10, body_lines.bit_length()))
        rows.append({"path": path, "score": score, "hit_units": hit_units, "units": units, "body_lines": body_lines,
                     "size": len(text)})
    rows.sort(key=lambda r: (-r["score"], r["size"], r["path"]))
    return rows


# ------------------------------------------------------------------------ the view --

def header_of(text):
    header = ""
    for line in text.splitlines(keepends=True)[:40]:
        if len(header) + len(line) > HEADER_CHARS:
            break
        header += line
    return header


def segments_for(row, text, failure):
    if len(text) <= WHOLE_FILE_CHARS or not row["hit_units"]:
        return [[{"kind": "file", "start_line": 1, "source": text}]]
    lines = text.splitlines(keepends=True)
    ordered = sorted(row["hit_units"], key=lambda h: (not (words(h[0][0].rsplit(".", 1)[-1]) & failure["name_words"]), h[0][1]))
    pieces = [{"kind": "module_header", "start_line": 1, "source": header_of(text)}]
    for (name, def_line, _start, end), _n in ordered:
        pieces.append({"kind": "symbol", "name": name, "start_line": def_line, "source": "".join(lines[def_line - 1:end])})
    return [pieces]


def build_packet(issue, files, rows, failure, cap):
    note = [{"path": r["path"], "executed_functions": [u[0][0] for u in r["hit_units"]][:8]} for r in rows[:NOTE_FILES]]
    packet = {"task": "Implement the issue using exact old_text/new_text source edits; no tests are visible.",
              "issue": issue, "source_packets": [],
              "localization": {"method": "files ranked by the failing test's execution trace, test-to-module names and "
                                         "symbols named in the failure; functions listed ran during the failing test",
                               "ranked_files": note},
              "constraints": ["Edit only the source paths shown in source_packets.",
                              "Each old_text must occur exactly once in the original full file.",
                              "Copy old_text only from source_segments[].source; metadata is not code.",
                              "Return an empty edits list if the visible source cannot justify a change."],
              "output": {"edits": [{"path": "src/example.py", "old_text": "exact original text",
                                    "new_text": "replacement text"}]}}
    while canonical_bytes(packet) > cap // 4 and packet["localization"]["ranked_files"]:
        packet["localization"]["ranked_files"].pop()
    for row in rows:
        path = row["path"]
        for segs in segments_for(row, files[path], failure):
            entry = {"path": path, "read_only": False, "source_segments": []}
            trial = copy.deepcopy(packet)
            trial["source_packets"].append(entry)
            for seg in segs:
                entry_trial = copy.deepcopy(trial)
                entry_trial["source_packets"][-1]["source_segments"].append(seg)
                if canonical_bytes(entry_trial) <= cap:
                    trial = entry_trial
            kept = trial["source_packets"][-1]["source_segments"]
            if any(s["kind"] in ("file", "symbol") for s in kept):
                packet = trial
    return packet


# -------------------------------------------------------------------------- edits --

def apply_edits(current, edits, allowed):
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


def run(view, cockpit):
    issue, files, caps = view["issue"], view["src_files"], view["caps"]
    traced = cockpit.run_signal(trace=True)
    by_lower = {p.lower(): p for p in files}
    executed = {}
    for path, lines in (traced.get("executed_src_lines") or {}).items():
        real = by_lower.get(path.replace("\\", "/").lower())
        if real is not None:
            executed[real] = set(lines)
    failure = parse_failure(issue + "\n" + "\n".join(traced.get("signal_lines") or []))
    rows = rank(files, failure, executed)
    cockpit.log("localize", traced_files=len(executed), ranked=len(rows),
                top=[(r["path"], r["score"]) for r in rows[:5]])
    packet0 = build_packet(issue, files, rows, failure, caps["edit_cap_bytes"])
    allowed = [item["path"] for item in packet0["source_packets"]]
    cockpit.log("edit_loop", reads=sorted(allowed))
    if not allowed:
        return {"status": "no_source_fits", "final_files": {}}
    state, feedback, last_edits, edited, calls = {}, None, None, set(), 0
    packet = packet0
    while calls < MAX_MODEL_CALLS:
        if feedback is not None:
            packet = dict(packet0, task="Your previous edit did not fix the failing tests. Use the feedback and the "
                                        "current source to propose corrected exact old_text/new_text edits.",
                          current_files={p: state.get(p, files[p])[:12000] for p in sorted(edited)},
                          previous_edits=last_edits, feedback=feedback)
            while canonical_bytes(packet) > caps["edit_cap_bytes"] + 16000 and packet["source_packets"]:
                packet = dict(packet, source_packets=packet["source_packets"][:-1])
        answer = cockpit.ask(packet, EDIT_SCHEMA, "edit" if feedback is None else f"retry{calls}")
        calls += 1
        if not answer["ok"]:
            feedback = {"kind": "output_failure", "detail": answer.get("error")}
            continue
        last_edits = answer["data"].get("edits")
        try:
            changed = apply_edits({p: state.get(p, files[p]) for p in allowed}, last_edits, set(allowed))
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
