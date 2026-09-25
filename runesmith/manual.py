"""The manual instrument: a person relays requests to any chat model they can reach.

Runesmith writes each request as a paste-ready text file. A person pastes it into a
chat model (a free chat tier works) or attaches the file, then hands the model's whole
reply back with ``runesmith manual answer``. The kernel treats the person and the chat
model together as one instrument:

* the reply is parsed like any other answer. Parsing is tolerant: prose around a
  ```json block is fine. Long values, such as whole source files, may arrive in named
  fenced blocks, so that the model never has to escape code inside JSON;
* no answer within ``timeout_s`` is a *transport* failure. The opportunity is censored
  and never scored as the model's behaviour. The request stays pending, and the
  router's retries keep waiting on the same request;
* the receipt records the model that the person says answered (``--model``) as
  ``answered_by``, next to the instrument's configured label.

The instrument is made for the few calls of a Kaizen author (``"roles": {"kaizen":
["chat"]}``): a frontier chat model can author a generation once, and the generation
then runs on free models. Any role works.

Files in the manual directory (default ``<home>/manual``):

* ``<id>.prompt.md``: the text to paste, or the file to attach;
* ``<id>.request.json``: what was asked (key, schema, digest, time);
* ``<id>.answer.md``: the reply, written by ``runesmith manual answer`` or saved by hand;
* ``<id>.answer.json``: optional, the answering model's name.

A consumed request moves to ``done/<id>/`` with ``outcome.json``.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

from runesmith.canon import canonical
from runesmith.instruments import CallOutcome, Instrument

REPLY_FORMAT = """\
---
HOW TO REPLY
Reply with one JSON object that satisfies the JSON schema below, in a single ```json fenced block.

Long text values, such as whole source files, may be moved out of the JSON so that they need no escaping.
Write the value as "@block:NAME". Then give the text in its own fenced block: it opens with four
backticks followed by @block:NAME, and it closes with four backticks on a line of their own. For example:

```json
{{"a_short_field": "a short value", "a_long_field": "@block:long1"}}
```

````python @block:long1
def example():
    return 1
````

A block's text is every line between its two fences. Keep short values and exact text fragments in the JSON.

JSON schema:
{schema}
"""

_BLOCK_OPEN = re.compile(r"^(`{3,})[^`\n]*?@block:([A-Za-z0-9_.-]+)\s*$")
_JSON_OPEN = re.compile(r"^(`{3,})\s*json\s*$", re.IGNORECASE)
_BLOCK_REF = re.compile(r"^@block:([A-Za-z0-9_.-]+)$")
_ATTEMPT_SUFFIX = re.compile(r"-a\d+$")
_TYPES: dict[str, Any] = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


# -------------------------------------------------------------------- requests --

def request_id(key: str, system: str, prompt: str, schema: dict | None) -> str:
    """A readable, content-addressed id: retries of one call share it, distinct calls never do."""
    digest = hashlib.sha256(canonical({"key": key, "system": system, "prompt": prompt,
                                       "schema": schema}).encode("utf-8")).hexdigest()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", key).strip("-.")[:48] or "request"
    return f"{slug}-{digest[:8]}"


def render_request(system: str, prompt: str, schema: dict | None) -> str:
    """The text to paste into a chat model: instructions, task, then the reply format."""
    parts = [system.strip()] if system.strip() else []
    parts.append(prompt.rstrip())
    if schema is not None:
        parts.append(REPLY_FORMAT.format(schema=json.dumps(schema, indent=1, ensure_ascii=False)).rstrip())
    return "\n\n".join(parts) + "\n"


def _paths(directory: Path, rid: str) -> dict[str, Path]:
    return {"prompt": directory / f"{rid}.prompt.md", "request": directory / f"{rid}.request.json",
            "answer": directory / f"{rid}.answer.md", "meta": directory / f"{rid}.answer.json"}


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def decode_reply(raw: bytes) -> str:
    """Bytes a person saved (UTF-8, UTF-8 with BOM, or UTF-16 from some Windows tools) -> text with LF endings."""
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------------- answers --

def _split_blocks(text: str) -> tuple[str, dict[str, str]]:
    """Take the named ``@block:NAME`` fenced blocks out of a reply; return (rest, blocks)."""
    lines, rest, blocks, i = text.split("\n"), [], {}, 0
    while i < len(lines):
        opened = _BLOCK_OPEN.match(lines[i])
        if not opened:
            rest.append(lines[i])
            i += 1
            continue
        fence, name = opened.group(1), opened.group(2)
        closing = re.compile(rf"^`{{{len(fence)},}}\s*$")
        j = i + 1
        while j < len(lines) and not closing.match(lines[j]):
            j += 1
        if j >= len(lines):
            raise ValueError(f"invalid_json: block {name} is never closed")
        if name in blocks:
            raise ValueError(f"invalid_json: block {name} appears twice")
        blocks[name] = "".join(line + "\n" for line in lines[i + 1:j])
        i = j + 1
    return "\n".join(rest), blocks


def _json_block(text: str) -> str | None:
    """The body of the first ```json fenced block, if any."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        opened = _JSON_OPEN.match(line)
        if opened:
            closing = re.compile(rf"^`{{{len(opened.group(1))},}}\s*$")
            for j in range(i + 1, len(lines)):
                if closing.match(lines[j]):
                    return "\n".join(lines[i + 1:j])
            return "\n".join(lines[i + 1:])
    return None


def _loads_object(text: str) -> dict:
    """One JSON object. Literal newlines inside strings are accepted (chat models write code that way)."""
    body = text.strip()
    try:
        value = json.loads(body, strict=False)
    except json.JSONDecodeError:
        decoder, value = json.JSONDecoder(strict=False), None
        for start in (i for i, ch in enumerate(body) if ch == "{"):
            try:
                value, _ = decoder.raw_decode(body[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                break
        if not isinstance(value, dict):
            raise ValueError("invalid_json: no JSON object found in the reply") from None
    if not isinstance(value, dict):
        raise ValueError("invalid_json: the reply's JSON is not an object")
    return value


def _substitute(value: Any, blocks: dict[str, str]) -> Any:
    if isinstance(value, str):
        ref = _BLOCK_REF.match(value.strip())
        if ref:
            if ref.group(1) not in blocks:
                raise ValueError(f"invalid_json: the reply names block {ref.group(1)} but does not contain it")
            return blocks[ref.group(1)]
        return value
    if isinstance(value, list):
        return [_substitute(v, blocks) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, blocks) for k, v in value.items()}
    return value


def parse_chat_answer(text: str) -> dict:
    """A chat model's whole reply -> the answer object (named blocks substituted, LF line endings)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    rest, blocks = _split_blocks(text)
    fenced = _json_block(rest)
    return _substitute(_loads_object(fenced if fenced is not None else rest), blocks)


def _is_type(value: Any, kind: str) -> bool:
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    expected = _TYPES.get(kind)
    return True if expected is None else isinstance(value, expected)


def schema_problems(value: Any, schema: dict | None, path: str = "answer") -> list[str]:
    """What a person should ask the chat model to fix (the JSON-schema subset Runesmith's schemas use)."""
    if not isinstance(schema, dict):
        return []
    kind = schema.get("type")
    if kind is not None:
        kinds = kind if isinstance(kind, list) else [kind]
        if not any(_is_type(value, k) for k in kinds):
            return [f"{path}: expected {' or '.join(kinds)}, got {type(value).__name__}"]
    problems = []
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: must be one of {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            problems.append(f"{path}: length {len(value)} is outside the allowed range")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        problems += [f"{path}: missing required field {name!r}" for name in schema.get("required") or []
                     if name not in value]
        if schema.get("additionalProperties") is False:
            problems += [f"{path}: unexpected field {name!r}" for name in value if name not in properties]
        for name, sub in properties.items():
            if name in value:
                problems += schema_problems(value[name], sub, f"{path}.{name}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            problems.append(f"{path}: {len(value)} items is outside the allowed range")
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                problems += schema_problems(item, schema["items"], f"{path}[{i}]")
    return problems


# ---------------------------------------------------------- the person's side --

def pending_requests(directory: Path) -> list[dict]:
    """Requests waiting in ``directory``, oldest first."""
    rows = []
    for path in sorted(Path(directory).glob("*.request.json")):
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        paths = _paths(Path(directory), request["id"])
        size = paths["prompt"].stat().st_size if paths["prompt"].exists() else 0
        rows.append({"id": request["id"], "key": request.get("key"), "created_utc": request.get("created_utc"),
                     "prompt": str(paths["prompt"]), "prompt_kb": round(size / 1024, 1),
                     "approx_tokens": size // 4, "answered": paths["answer"].exists()})
    return sorted(rows, key=lambda r: (r["created_utc"] or "", r["id"]))


def resolve_request(directory: Path, token: str | None) -> str:
    """A full id or a unique prefix; with no token, the only pending request."""
    ids = [r["id"] for r in pending_requests(directory)]
    matches = [i for i in ids if token and (i == token or i.startswith(token))] if token else ids
    exact = [i for i in matches if i == token]
    if exact:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LookupError(f"no pending request matches {token!r} in {directory}" if token
                          else f"no requests are waiting in {directory}")
    raise LookupError(f"{len(matches)} pending requests match; give more of the id: " + ", ".join(matches))


def submit_answer(directory: Path, rid: str, text: str, *, model: str | None = None,
                  force: bool = False) -> dict:
    """Check a reply against the request's schema and hand it to the waiting instrument.

    A reply with problems is not saved unless ``force``: the person can ask the chat
    model to fix it first. The problems are returned either way.
    """
    paths = _paths(Path(directory), rid)
    if not paths["request"].exists():
        raise LookupError(f"no pending request {rid} in {directory}")
    request = json.loads(paths["request"].read_text(encoding="utf-8"))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    try:
        problems = schema_problems(parse_chat_answer(text), request.get("schema"))
    except (ValueError, json.JSONDecodeError) as error:
        problems = [str(error)]
    if problems and not force:
        return {"written": None, "problems": problems}
    if model:
        _atomic_write(paths["meta"], json.dumps({"model": model, "utc": _utc()}) + "\n")
    _atomic_write(paths["answer"], text)            # last: the instrument reads the name only when complete
    return {"written": str(paths["answer"]), "problems": problems}


def read_clipboard() -> str:
    """The clipboard's text, via tkinter (bundled with Python on Windows and macOS)."""
    try:
        import tkinter
    except ImportError as error:                     # pragma: no cover - platform dependent
        raise RuntimeError("tkinter is not available; save the reply to a file and use --file") from error
    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    finally:
        root.destroy()


def directory_for(config: dict, home: Path) -> Path:
    """The manual directory of the first manual instrument in ``config`` (default ``<home>/manual``)."""
    for spec in (config.get("instruments") or {}).values():
        if isinstance(spec, dict) and spec.get("kind") == "manual" and spec.get("dir"):
            return Path(spec["dir"])
    return Path(home) / "manual"


# ------------------------------------------------------------------ instrument --

class ManualInstrument(Instrument):
    """Writes each request for a person to relay, then waits for the reply (see module docstring)."""

    kind = "manual"

    def __init__(self, name: str, model: str = "chat", *, directory: Path, timeout_s: float = 3600.0,
                 poll_s: float = 2.0, notify: Callable[[str, Path], None] | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        super().__init__(name, model)
        self.directory, self.timeout_s, self.poll_s = Path(directory), float(timeout_s), float(poll_s)
        self._notify = notify or self._tell
        self._clock, self._sleep = clock, sleep

    def _tell(self, rid: str, prompt_path: Path) -> None:
        home = f" --home {self.directory.parent}" if self.directory.name == "manual" else ""
        print(f"[runesmith] waiting for a chat model's answer to request {rid}\n"
              f"  1. paste the text of {prompt_path} into any chat model (or attach the file)\n"
              f"  2. copy the model's whole reply and run:  runesmith{home} manual answer {rid} --clipboard\n"
              f"     (or save it to a file and use --file PATH). Waiting up to {self.timeout_s / 60:.0f} min.",
              file=sys.stderr, flush=True)

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        base = _ATTEMPT_SUFFIX.sub("", key)          # the router appends -a<attempt>; retries share one request
        rid = request_id(base, system, prompt, schema)
        paths = _paths(self.directory, rid)
        self.directory.mkdir(parents=True, exist_ok=True)
        if not paths["request"].exists():
            _atomic_write(paths["prompt"], render_request(system, prompt, schema))
            _atomic_write(paths["request"], json.dumps({
                "format": "runesmith.manual.request.v1", "id": rid, "key": base, "instrument": self.name,
                "model": self.model, "created_utc": _utc(), "max_tokens": max_tokens,
                "reasoning_effort": reasoning_effort,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "system": system, "schema": schema}, indent=1) + "\n")
        if not paths["answer"].exists():             # new, or resumed after a retry or a restart
            self._notify(rid, paths["prompt"])
        started, seen = self._clock(), None
        while True:
            state = None
            if paths["answer"].exists():
                stat = paths["answer"].stat()
                state = (stat.st_size, stat.st_mtime_ns)
            if state is not None and state == seen:  # unchanged across two looks: the save is complete
                break
            seen = state
            if self._clock() - started >= self.timeout_s:
                return CallOutcome(False, error_kind="transport",
                                   error=f"timeout: no answer to manual request {rid} after "
                                         f"{self.timeout_s:.0f} s; it stays pending",
                                   latency_s=self._clock() - started, receipt={"request_id": rid})
            self._sleep(self.poll_s)
        text = decode_reply(paths["answer"].read_bytes())
        meta = {}
        if paths["meta"].exists():
            try:
                meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        receipt = {"provider": "manual", "model": self.model, "answered_by": str(meta.get("model") or self.model),
                   "request_id": rid, "tokens_in": None, "tokens_out": None}
        latency = self._clock() - started
        try:
            outcome = CallOutcome(True, data=parse_chat_answer(text), text=text, latency_s=latency, receipt=receipt)
        except (ValueError, json.JSONDecodeError) as error:
            outcome = CallOutcome(False, text=text, error_kind="output", error=f"invalid_json: {error}"[:600],
                                  latency_s=latency, receipt=receipt)
        self._archive(rid, paths, outcome)
        return outcome

    def _archive(self, rid: str, paths: dict[str, Path], outcome: CallOutcome) -> None:
        done = self.directory / "done"
        target, n = done / rid, 2
        while target.exists():
            target, n = done / f"{rid}-{n}", n + 1
        target.mkdir(parents=True)
        for path in paths.values():
            if path.exists():
                try:
                    os.replace(path, target / path.name)
                except OSError:                      # held open elsewhere: keep a copy, remove when possible
                    shutil.copy2(path, target / path.name)
        (target / "outcome.json").write_bytes((json.dumps(
            {"id": rid, "ok": outcome.ok, "error_kind": outcome.error_kind, "error": outcome.error,
             "answered_by": outcome.receipt.get("answered_by"), "consumed_utc": _utc(),
             "wait_s": round(outcome.latency_s, 1)}, indent=1) + "\n").encode("utf-8"))
