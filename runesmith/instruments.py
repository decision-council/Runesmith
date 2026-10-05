"""Replaceable cognitive instruments and the router that calls them.

An instrument is anything that can answer a bounded JSON request: a local model
(Ollama, LM Studio, llama.cpp and vLLM all speak the OpenAI chat API), a hosted
free-tier model, a model router such as Milliner, or a scripted stand-in used in
tests. Runesmith never binds its state to one model: every call is recorded with
the instrument identity that actually answered, so competence can be traced to
the runtime state rather than to a particular brand of model.

Failure classes are typed and checked transport-first:

* ``transport`` — the route failed (rate limit, outage, connection). These are
  retried with backoff and, when exhausted, *censor* the opportunity; they are
  never scored as the model's behaviour.
* ``output`` — the model answered but the answer is unusable (truncated,
  schema failure, invalid JSON). This is charged to the caller as one call.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runesmith.canon import canonical

# The marker lists are Runesmith v1's (SR3/SR4 cockpit), kept identical so that
# generation-0 behaviour matches the measured v1 policy.
TRANSPORT_MARKERS = (
    "winerror 10054", "winerror 10061", "urlopen error", "connection", "timed out", "timeout",
    "overloaded", "rate_limited", "capacity reached", "no alternative route", "daily_request_cap",
    "503", "502", "504", "429", "auth_failed",
)
OUTPUT_MARKERS = ("truncated", "schema_failed", "invalid_json", "bad_request")
DEFAULT_BACKOFF_S = (15, 30, 45, 60, 90, 120, 180)


def classify(message: str) -> str:
    """Transport markers win over output markers; unknown errors are transport."""
    lowered = message.lower()
    if any(marker in lowered for marker in TRANSPORT_MARKERS):
        return "transport"
    if any(marker in lowered for marker in OUTPUT_MARKERS):
        return "output"
    return "transport"


class TransportCensored(RuntimeError):
    """No usable response after the declared retries; the opportunity is censored."""

    def __init__(self, message, *, receipt=None, plain=None, detail=None):
        super().__init__(message)
        self.receipt = receipt or {}
        self.plain = plain          # the whole message in the owner's words, when it already is (a limit, with its time)
        self.detail = detail        # what the service itself said, kept for the details panel and the job receipt


@dataclass
class CallOutcome:
    ok: bool
    data: dict | None = None
    text: str | None = None
    error_kind: str | None = None          # "output" | "transport"
    error: str | None = None
    latency_s: float = 0.0
    attempts: int = 1
    receipt: dict = field(default_factory=dict)

    def public(self) -> dict:
        """What an organ may see about its own call."""
        return {"ok": self.ok, "data": self.data, "error_kind": self.error_kind,
                "error": (self.error or "")[:400] or None, "latency_s": round(self.latency_s, 2)}


def _first_json_object(text: str) -> dict | None:
    """The first complete ``{...}`` object embedded in prose, if any (small local models add chatter)."""
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def parse_json_answer(text: str | None, parsed: Any = None, *, tolerant: bool = False) -> dict:
    """Parse a model's JSON answer.

    Strict by default (the kernel's historical behaviour). ``tolerant=True`` also
    accepts a JSON object wrapped in prose or code fences, which weak local models
    often produce; the object must still satisfy the organ's own checks.
    """
    if isinstance(parsed, dict):
        return parsed
    body = (text or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body)
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        value = _first_json_object(body) if tolerant else None
        if value is None:
            raise
    if not isinstance(value, dict):
        raise ValueError("invalid_json: answer is not a JSON object")
    return value


# ------------------------------------------------------------------ transports --

Transport = Callable[[str, str, Mapping[str, str], dict | None, float], tuple[int, dict]]


def http_json(method: str, url: str, headers: Mapping[str, str], body: dict | None,
              timeout_s: float) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=data, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout_s) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw[:500]}
        if isinstance(payload, list):                  # Google answers [{"error": {...}}]: its first object is the answer
            payload = next((row for row in payload if isinstance(row, dict)), None) or {"error": raw[:500]}
        if not isinstance(payload, dict):
            payload = {"error": str(payload)[:500]}
        if error.code in (429, 503):                   # when to ask again, read from the whole answer before it is cut short
            from runesmith.pacing import limit_hints
            hints = limit_hints(error.headers, raw)
            if hints:
                payload = dict(payload, _pacing=hints)
        return error.code, payload


def secret_from(env_var: str | None = None, env_file: str | None = None, key: str | None = None) -> Callable[[], str]:
    """A supplier that reads a secret on demand; the value is never stored or logged."""
    def supply() -> str:
        if env_var and os.environ.get(env_var):
            return os.environ[env_var].strip()
        if env_file and key and Path(env_file).exists():
            for line in Path(env_file).read_text(encoding="utf-8").splitlines():
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        return ""
    return supply


# ----------------------------------------------------------------- instruments --

class Instrument:
    kind = "abstract"
    free_tier = False          # set from the preset: a free key's allowance is spent by every retry (see runesmith/pacing.py)
    takes_reasoning_effort = False   # a model that thinks and takes an effort setting (Gemini): asked for a low effort and more room
    label = None               # the provider's name for the owner's words ("Google Gemini"); the instrument's name when None
    counter = None             # called with the HTTP status of every request sent (runesmith.pacing.DayCount.bump)

    def __init__(self, name: str, model: str) -> None:
        self.name, self.model = name, model

    def identity(self) -> dict:
        return {"instrument": self.name, "kind": self.kind, "model": self.model}

    def complete(self, *, prompt: str, system: str, schema: dict | None, max_tokens: int,
                 key: str, reasoning_effort: str | None = None) -> CallOutcome:
        raise NotImplementedError


class LenientSchema(dict):
    """A JSON schema whose optional fields are really optional; Runesmith validates the answer itself.

    Milliner's default strict mode makes every property required (Groq and OpenAI demand it), which forced a
    model to write out every optional field of every example step and truncated the answer (checker experiment,
    2026-09-28), and forced output on free routes lost every backslash escape in code (journey J2). A lenient
    schema is therefore sent to Milliner as text in the prompt, not as a forced schema.
    """


class MillinerInstrument(Instrument):
    """Milliner's pinned-model gate (``POST /v1/complete``)."""

    kind = "milliner"

    def __init__(self, name: str, model: str, *, base_url: str, token: Callable[[], str],
                 caller_tag: str = "runesmith", timeout_s: float = 900.0,
                 allow_uncatalogued: bool = False, budget_tag: str | None = None,
                 fallback_models: list[str] | None = None,
                 request_dir: Path | None = None,
                 transport: Transport = http_json) -> None:
        super().__init__(name, model)
        self.base_url, self._token, self.caller_tag = base_url.rstrip("/"), token, caller_tag
        self.timeout_s, self.allow_uncatalogued, self.budget_tag = timeout_s, allow_uncatalogued, budget_tag
        if fallback_models is not None and (not isinstance(fallback_models, list)
                or any(not isinstance(m, str) or not m.strip() for m in fallback_models)):
            raise ValueError('fallback_models must be a list of nonempty model names')
        chain = list(dict.fromkeys([model] + [m.strip() for m in (fallback_models or [])]))
        if len(chain) > 6:
            raise ValueError('Milliner accepts a primary and at most five fallback models')
        self.fallback_models = chain[1:]
        self._transport = transport
        self.request_dir = Path(request_dir) if request_dir is not None else None

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        token = self._token()
        if not token:
            return CallOutcome(False, error_kind="transport", error="auth_failed: Milliner token unavailable")
        lenient = isinstance(schema, LenientSchema)
        if lenient:                                     # in the system text: the prompt stays the frozen author prompt
            system = (system or "") + ("\n\nReply with one JSON object that satisfies this JSON schema (fields not "
                                       "listed as required are optional):\n" + canonical(schema))
            schema = None
        body: dict[str, Any] = {"model": self.model, "prompt": prompt, "system": system, "priority": 1,
                                "wait": True, "timeout_s": max(1.0, self.timeout_s - 5.0),
                                "max_tokens": max_tokens, "idempotency_key": key}
        if self.fallback_models:
            body.pop('model')
            body.update(models=[self.model, *self.fallback_models], allow_fallback=True,
                        max_fallbacks=len(self.fallback_models))
        if schema is not None:
            body["json_schema"] = schema
        if lenient:
            # Valid JSON without a pinned schema: the provider's JSON-object mode kept code escapes intact on the same
            # NVIDIA route whose forced schema lost them (probe, 2026-09-28), and invalid JSON stopped.
            body["json_mode"] = True
        if self.budget_tag:
            body["budget_tag"] = self.budget_tag
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
        if self.allow_uncatalogued:
            body["allow_uncatalogued"] = True
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                   "X-Milliner-Agent": self.caller_tag}
        if self.request_dir is not None:
            from runesmith.milliner_jobs import submit
            return submit(self, body, headers)
        started = time.monotonic()
        try:
            status, payload = self._transport("POST", f"{self.base_url}/v1/complete", headers, body, self.timeout_s)
        except (URLError, OSError, TimeoutError) as error:
            return CallOutcome(False, error_kind="transport", error=f"{type(error).__name__}: {error}",
                               latency_s=time.monotonic() - started)
        return self._response(status, payload, time.monotonic()-started)

    def resume_request(self, request_id, *, wait_s=20):
        """GET only: a saved ticket can never trigger a new generation."""
        from runesmith.milliner_jobs import read_request, poll
        if self.request_dir is None:
            raise ValueError('This instrument has no durable request directory')
        token = self._token()
        if not token:
            raise ValueError('Milliner token unavailable; no request resumed')
        headers = {'Authorization':f'Bearer {token}', 'X-Milliner-Agent':self.caller_tag}
        return poll(self, read_request(self.request_dir, request_id), headers, wait_s=min(30, max(0.1,wait_s)))

    def _response(self, status, payload, latency):
        from runesmith.inference_usage import qualify_usage
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        usage = qualify_usage(meta)
        receipt = {"provider": payload.get("provider") or meta.get("provider"),
                   "model": payload.get("model") or meta.get("model"), "job_id": payload.get("job_id"),
                   "tokens_in": usage['tokens_in'], "tokens_out": usage['tokens_out'],
                   "latency_ms": meta.get("latency_ms"), "est_usd": usage['est_usd'],
                   "cached": meta.get("cached"), "provider_attempts":meta.get('attempts',[]),
                   "accounting": usage}
        # Classify on the message text exactly as Runesmith v1 did (codes are recorded, not classified).
        if not 200 <= status < 300:
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or payload.get("message") or error.get("type")
                              or error.get("code") or f"http_{status}")
            else:
                message = str(payload.get("message") or error or f"http_{status}")
            return CallOutcome(False, error_kind=classify(message), error=message[:600], latency_s=latency,
                               receipt=dict(receipt, http_status=status))
        if payload.get("state") != "succeeded":
            message = str(payload.get("error") or f"Milliner job ended in state {payload.get('state')!r}")
            return CallOutcome(False, error_kind=classify(message), error=message[:600], latency_s=latency,
                               receipt=dict(receipt,error_code=payload.get("error_code")))
        try:
            data = parse_json_answer(payload.get("text"), payload.get("parsed"), tolerant=True)   # text-mode answers
        except (ValueError, json.JSONDecodeError) as error:
            return CallOutcome(False, text=payload.get("text"), error_kind="output",
                               error=f"invalid_json: {error}"[:600], latency_s=latency, receipt=receipt)
        return CallOutcome(True, data=data, text=payload.get("text"), latency_s=latency, receipt=receipt)


def _estimate_tokens(*texts: str) -> int:
    """A cautious token estimate (about three characters a token) for window checks before a request is sent."""
    return sum(len(t or "") for t in texts) // 3 + 16


CONTEXT_OVERFLOW = ("exceeds the available context size", "exceed_context_size", "maximum context length",
                    "context length of only", "context_length_exceeded", "exceeds the context size")


def _permanent(status: int, message: str) -> str | None:
    """Plain words for a refusal that no retry can change, or None (research: context overflow, 413, 404)."""
    low = message.lower()
    if any(p in low for p in CONTEXT_OVERFLOW):
        return ("The request is longer than this model's context window on that server. Load the model with a larger "
                "context length (LM Studio: when loading the model; llama.cpp: --ctx-size 16384), or give this role a "
                "model with a larger window.")
    if status == 413 or "request too large" in low:
        return ("The request is too large for this service's limit (on a free tier, its tokens-per-minute window). "
                "Give this role a model with a larger window.")
    if status == 404 or "model_not_found" in low or "does not exist" in low:
        return "The service does not know this model or address. Check the model's exact name in its model list."
    if status in (401, 403) or "invalid_api_key" in low or "invalid api key" in low:     # journey J8-F3
        return (f"The service refused the key ({status}). Check it, or paste it again, under Thinking power; a retry "
                "with the same key cannot help.")
    return None


def _refusal(status: int, message: str) -> str:
    """How a service refused a request before any answer: \"too_large\" when a smaller request might be taken, else
    \"refused\" (a key or a model name). Either way nothing was generated and nothing charged."""
    low = message.lower()
    if status == 413 or "request too large" in low or any(p in low for p in CONTEXT_OVERFLOW):
        return "too_large"
    return "refused"


def _unreachable(base_url: str, error: Exception) -> str:
    local = any(h in base_url for h in ("127.0.0.1", "localhost", "[::1]"))
    if local:
        return (f"Nothing answers at {base_url}: the model server on this computer is not running. Start it "
                f"(LM Studio: Developer, Start Server; llama.cpp: llama-server), then try again. ({type(error).__name__})")
    return f"{type(error).__name__}: {error}"


class OpenAICompatInstrument(Instrument):
    """Any OpenAI-compatible chat endpoint: Ollama, LM Studio, vLLM, Groq, OpenRouter, ..."""

    kind = "openai"

    def __init__(self, name: str, model: str, *, base_url: str, api_key: Callable[[], str] | None = None,
                 timeout_s: float = 600.0, json_mode: str = "json_object", transport: Transport = http_json,
                 tolerant_json: bool = True, max_request_tokens: int | None = None) -> None:
        super().__init__(name, model)
        self.base_url, self._api_key, self.timeout_s = base_url.rstrip("/"), api_key, timeout_s
        self.json_mode, self._transport, self.tolerant_json = json_mode, transport, tolerant_json
        self.max_request_tokens = max_request_tokens      # e.g. a free tier's tokens-per-minute window

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        headers = {"Content-Type": "application/json"}
        secret = self._api_key() if self._api_key else ""
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        instruction = system
        if schema is not None:
            instruction += "\nReply with one JSON object that satisfies this JSON schema:\n" + canonical(schema)
        body: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens,
                                "messages": [{"role": "system", "content": instruction},
                                             {"role": "user", "content": prompt}]}
        if self.json_mode == "json_schema" and schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "answer", "schema": schema}}
        elif self.json_mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
        needed = _estimate_tokens(instruction, prompt) + max_tokens
        if self.max_request_tokens and needed > self.max_request_tokens:
            return CallOutcome(False, error_kind="config", receipt={"refused_before_answer": "too_large"}, error=(
                f"This request needs about {needed} tokens (the text plus room for the answer), more than this service "
                f"accepts at once ({self.max_request_tokens} tokens a minute on its free tier). Give this role a model "
                "with a larger window."))
        started = time.monotonic()
        fallback = None
        while True:
            try:
                status, payload = self._transport("POST", f"{self.base_url}/chat/completions", headers, body, self.timeout_s)
            except (URLError, OSError, TimeoutError) as error:
                return CallOutcome(False, error_kind="transport", error=_unreachable(self.base_url, error),
                                   latency_s=time.monotonic() - started)
            if self.counter is not None:                # a request was sent and answered: it spent from today's allowance
                try:
                    self.counter(status)
                except Exception:                       # a counter is a courtesy: never stop a call because of it
                    pass
            message = "" if 200 <= status < 300 else (
                f"http_{status} " + json.dumps(payload.get("error", {k: v for k, v in payload.items() if k != "_pacing"}))[:500])
            if status == 400 and "response_format" in message.lower() and "response_format" in body and fallback is None:
                body.pop("response_format")                 # a server that rejects this JSON mode: once, without it
                fallback = "none"
                continue
            break
        latency = time.monotonic() - started
        if not 200 <= status < 300:
            plain = _permanent(status, message)
            if plain:
                return CallOutcome(False, error_kind="config", error=f"{plain} ({message[:300]})", latency_s=latency,
                                   receipt={"refused_before_answer": _refusal(status, message)})
            hints = payload.get("_pacing") if isinstance(payload.get("_pacing"), dict) else {}
            return CallOutcome(False, error_kind=classify(message), error=message, latency_s=latency,
                               receipt={"http_status": status, **hints})
        try:
            choice = payload["choices"][0]
            text = choice["message"].get("content") or ""
            finish = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError):
            return CallOutcome(False, error_kind="output", error="bad_request: malformed completion", latency_s=latency)
        usage = payload.get("usage") or {}
        receipt = {"provider": self.base_url, "model": payload.get("model", self.model),
                   "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens")}
        if fallback:
            receipt["json_mode_fallback"] = fallback
        if finish == "length":
            return CallOutcome(False, text=text, error_kind="output", error="truncated: finish_reason=length",
                               latency_s=latency, receipt=receipt)
        try:
            data = parse_json_answer(text, tolerant=self.tolerant_json)
        except (ValueError, json.JSONDecodeError) as error:
            return CallOutcome(False, text=text, error_kind="output", error=f"invalid_json: {error}"[:600],
                               latency_s=latency, receipt=receipt)
        return CallOutcome(True, data=data, text=text, latency_s=latency, receipt=receipt)


class OllamaInstrument(Instrument):
    """Ollama through its native chat API, which accepts a context window per request (LS1).

    Ollama's OpenAI-style /v1 address cannot raise its default window (4,096 tokens on modest machines), and an
    overflowing prompt silently loses its beginning, where Runesmith's instructions are. So each request asks for a
    window that fits it, and the answer's own count of tokens read shows whether the whole request arrived.
    """

    kind = "ollama"

    def __init__(self, name: str, model: str, *, base_url: str = "http://127.0.0.1:11434", timeout_s: float = 900.0,
                 transport: Transport = http_json, min_context: int = 8192, max_context: int = 32768) -> None:
        super().__init__(name, model)
        self.base_url, self.timeout_s, self._transport = base_url.rstrip("/"), timeout_s, transport
        self.min_context, self.max_context = min_context, max_context

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        instruction = system
        if schema is not None:
            instruction += "\nReply with one JSON object that satisfies this JSON schema:\n" + canonical(schema)
        estimate = _estimate_tokens(instruction, prompt)
        needed = estimate + max_tokens + 256
        if needed > self.max_context:
            return CallOutcome(False, error_kind="config", receipt={"refused_before_answer": "too_large"}, error=(
                f"This request needs about {needed} tokens (the text plus room for the answer), more than the "
                f"{self.max_context}-token window allowed for this Ollama model. Allow it a larger window, or give "
                "this role a model with a larger window."))
        window = min(self.max_context, max(self.min_context, -(-needed // 2048) * 2048))
        body: dict[str, Any] = {"model": self.model, "stream": False,
                                "messages": [{"role": "system", "content": instruction},
                                             {"role": "user", "content": prompt}],
                                "options": {"num_ctx": window, "num_predict": max_tokens}}
        if schema is not None:
            body["format"] = schema
        started = time.monotonic()
        try:
            status, payload = self._transport("POST", f"{self.base_url}/api/chat", {"Content-Type": "application/json"},
                                              body, self.timeout_s)
        except (URLError, OSError, TimeoutError) as error:
            return CallOutcome(False, error_kind="transport", latency_s=time.monotonic() - started, error=(
                f"Ollama is not running on this computer (nothing answers at {self.base_url}): open the Ollama app "
                f"(it sits in the system tray) or run 'ollama serve', then try again. ({type(error).__name__})"))
        latency = time.monotonic() - started
        if not 200 <= status < 300:
            message = str(payload.get("error") or payload)[:500]
            if "not found" in message.lower():
                return CallOutcome(False, error_kind="config", latency_s=latency, receipt={"refused_before_answer": "refused"}, error=(
                    f"The model '{self.model}' is not downloaded yet: run 'ollama pull {self.model}' (or choose one "
                    f"that is), then try again. ({message[:200]})"))
            return CallOutcome(False, error_kind=classify(message), error=f"http_{status} {message}", latency_s=latency)
        text = (payload.get("message") or {}).get("content") or ""
        read = payload.get("prompt_eval_count")
        receipt = {"provider": "ollama", "model": payload.get("model", self.model), "tokens_in": read,
                   "tokens_out": payload.get("eval_count"), "num_ctx": window}
        if isinstance(read, int) and read < estimate * 0.5:
            return CallOutcome(False, text=text, error_kind="config", latency_s=latency, receipt=receipt, error=(
                f"Ollama read only {read} of about {estimate} tokens of this request, so its answer cannot be trusted. "
                "This Ollama may be too old to accept a window per request: update Ollama, or set "
                "OLLAMA_CONTEXT_LENGTH=32768 and restart it."))
        if payload.get("done_reason") == "length":
            return CallOutcome(False, text=text, error_kind="output", error="truncated: done_reason=length",
                               latency_s=latency, receipt=receipt)
        try:
            data = parse_json_answer(text, tolerant=True)
        except (ValueError, json.JSONDecodeError) as error:
            return CallOutcome(False, text=text, error_kind="output", error=f"invalid_json: {error}"[:600],
                               latency_s=latency, receipt=receipt)
        return CallOutcome(True, data=data, text=text, latency_s=latency, receipt=receipt)


class ScriptedInstrument(Instrument):
    """Deterministic stand-in: answers from a list of prepared outcomes (tests, replays)."""

    kind = "scripted"

    def __init__(self, name: str, answers: Iterable[dict | CallOutcome | Exception], model: str = "scripted") -> None:
        super().__init__(name, model)
        self._answers = list(answers)
        self.requests: list[dict] = []

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None) -> CallOutcome:
        self.requests.append({"prompt": prompt, "schema": schema, "max_tokens": max_tokens, "key": key})
        if not self._answers:
            return CallOutcome(False, error_kind="transport", error="unavailable: script exhausted")
        answer = self._answers.pop(0)
        if isinstance(answer, CallOutcome):
            return answer
        if isinstance(answer, Exception):
            return CallOutcome(False, error_kind=classify(str(answer)), error=str(answer))
        return CallOutcome(True, data=answer, text=canonical(answer))


# ---------------------------------------------------------------------- router --

class Router:
    """Maps roles to instruments and owns transport retries.

    A role (``repair``, ``kaizen`` ...) names what a call is for; the router
    decides which instrument answers. Output failures return at once (one call
    charged); transport failures back off and finally raise
    :class:`TransportCensored`. A call the gateway refused before admitting it,
    or that every one of its routes refused before generating (nothing ran,
    nothing was charged), moves straight on to the role's next instrument, each
    at most once per attempt, even when retries are off.
    """

    def __init__(self, instruments: Mapping[str, Instrument], roles: Mapping[str, str | list[str]],
                 *, backoff_s: tuple[float, ...] = DEFAULT_BACKOFF_S, sleep: Callable[[float], None] = time.sleep,
                 on_call: Callable[[dict], None] | None = None, pacing=None,
                 clock: Callable[[], float] = time.time, counts=None) -> None:
        self.instruments = dict(instruments)
        self.roles = {role: ([names] if isinstance(names, str) else list(names)) for role, names in roles.items()}
        for role, names in self.roles.items():
            missing = [n for n in names if n not in self.instruments]
            if missing:
                raise ValueError(f"role {role!r} names unknown instruments {missing}")
        self.backoff_s, self._sleep, self._on_call = tuple(backoff_s), sleep, on_call
        self.pacing, self._clock = pacing, clock        # pacing: runesmith.pacing.Pacing, where a "429" is remembered
        self.counts = counts                            # runesmith.pacing.DayCount: requests sent today, per instrument

    def call(self, role: str, *, prompt: str, system: str, schema: dict | None, max_tokens: int,
             key: str, reasoning_effort: str | None = None, own_effort_first: bool = False,
             soft_effort: str | None = None, room: int | None = None, room_retry: bool = False) -> CallOutcome:
        """``reasoning_effort`` is what the caller asks for; an instrument's own setting (its model's needs, journey
        J11-B8) is used when the call names none. With ``own_effort_first`` the order is the other way round: the
        call's effort is only the fallback for an instrument that has no setting of its own (a Kaizen campaign asks
        for high effort, but must not override a model the owner set to low).

        ``soft_effort`` and ``room`` are for a call whose answer is short but whose model may think first (acceptance
        checks, a plan): an instrument that thinks and takes an effort setting (``takes_reasoning_effort``: Gemini on
        its OpenAI-compatible address) is asked for ``soft_effort`` when nothing else names one, and its answer gets at
        least ``room`` tokens, since hidden reasoning is counted in them (journey J0: a 3,000-token answer was cut off).
        Every other instrument is asked exactly as before. ``room_retry`` marks the second ask after an answer was cut."""
        names = self.roles.get(role)
        if not names:
            raise KeyError(f"no instrument serves role {role!r}")
        from runesmith.pacing import BUSY_WAIT_S, FREE_TIER_TRIES, SHORT_WAIT_S, reset_time
        errors = []
        attempt = 0
        gone: dict[str, CallOutcome] = {}          # refused before answering: not asked again in this call
        # What this call has learned about its instruments, so that a free key's allowance is not spent on retries:
        # a service at its limit ("429") is not asked again until its reset, one that is busy ("503") is asked once more
        # after a longer wait, and a free key gets one retry at most (journey J0: 36 of 38 calls failed on one free key).
        stopped: dict[str, dict] = {}              # at its limit: {'until', 'daily'}
        busy: set[str] = set()
        spent: dict[str, int] = {}
        waited_short = busy_waited = False
        asks, wait, last = 0, 0.0, (None, None)

        def askable(n):                                 # not at its limit, not turned away for good, no retry of a free key left unused
            return (n not in stopped and n not in gone and not self._held(n, stopped)
                    and not (getattr(self.instruments[n], 'free_tier', False) and spent.get(n, 0) >= FREE_TIER_TRIES))
        while True:
            if wait:
                self._sleep(wait)
                wait = 0.0
            live = [n for n in names if n not in stopped and not self._held(n, stopped)
                    and not (getattr(self.instruments[n], 'free_tier', False) and spent.get(n, 0) >= FREE_TIER_TRIES)]
            if not live:
                if stopped:
                    raise self._limited_error(names, stopped)
                break
            outcome = self._attempt(role, live, attempt, prompt=prompt, system=system, schema=schema,
                                    max_tokens=max_tokens, key=key, reasoning_effort=reasoning_effort, gone=gone,
                                    own_effort_first=own_effort_first, order=names, soft_effort=soft_effort, room=room,
                                    room_retry=room_retry)
            attempt = outcome.attempts
            if not outcome.ok and (outcome.receipt.get('not_admitted') or outcome.receipt.get('no_route_accepted')):
                # Every model turned the request away before generating: nothing ran, so this is no answer, never an
                # output failure, whatever the refusal says (review of J11-B7: a bad_request from the last model used
                # up a try).
                raise TransportCensored(outcome.error or 'every model turned the request away', receipt=outcome.receipt)
            name = outcome.receipt.get('instrument')
            if outcome.ok:
                if self.pacing is not None and name in self.instruments:
                    self.pacing.clear(name)
                return outcome
            if outcome.error_kind in ("output", "config"):
                return outcome                          # "config": a refusal that no retry can change (LS1)
            if outcome.receipt.get('no_retry'):
                raise TransportCensored(outcome.error or 'Saved remote request requires review', receipt=outcome.receipt)
            errors.append(outcome.error)
            spent[name] = spent.get(name, 0) + 1
            status = outcome.receipt.get('http_status') if getattr(self.instruments.get(name), 'kind', '') == 'openai' else None
            last = (status, outcome)
            if status == 429:
                now = self._clock()
                until, daily, guessed = reset_time(getattr(self.instruments[name], 'base_url', ''), outcome.receipt,
                                                   outcome.error or '', now,
                                                   self.pacing.recent(name) if self.pacing is not None else None)
                if not daily and until - now <= SHORT_WAIT_S and not waited_short and self.backoff_s:
                    waited_short = True                 # the service's own short wait (a per-minute limiter): once
                    wait = until - now + 1
                    continue
                stopped[name] = {'until': until, 'daily': daily, 'said': outcome.error}
                if self.pacing is not None:
                    self.pacing.mark(name, until, daily=daily, guessed=guessed, said=outcome.error)
                if self.counts is not None:             # a day's refusal that names its limit teaches the cap
                    self.counts.learn_cap(name, getattr(self.instruments[name], 'base_url', ''), outcome.error, daily)
                continue
            if status == 503:
                busy.add(name)
                if any(n not in busy for n in names if askable(n)):
                    continue                            # another model has not been asked: it goes first, no wait
                if busy_waited or not self.backoff_s:
                    raise self._busy_error(names, outcome)
                busy_waited, wait = True, BUSY_WAIT_S   # one more try, after a longer wait
                busy.clear()
                continue
            if asks >= len(self.backoff_s):
                break
            wait = self.backoff_s[asks]
            asks += 1
        if last[0] == 503:                              # the last word was "busy": the owner's words, not a count of attempts
            raise self._busy_error(names, last[1])
        refusals = '; '.join(f"{name} refused before answering: {(o.error or '')[:200]}" for name, o in gone.items())
        raise TransportCensored(f"role {role!r}: no response after {attempt} attempts; last: {errors[-1] if errors else ''}"
                                + (f"; {refusals}" if refusals else ''))

    def _held(self, name, stopped):
        """Whether an earlier call saw this instrument at its limit and its reset has not come (then it is not asked)."""
        mark = self.pacing.limited(name) if self.pacing is not None else None
        if mark:
            stopped[name] = {'until': mark['until'], 'daily': bool(mark.get('daily')), 'said': mark.get('said')}
            return True
        return False

    def _name(self, name):
        """How an instrument is called in the owner's words: its provider and model ("Google Gemini (gemini-3.8-flash)"),
        or its own name when it has no provider's name. Several models of one provider are told apart by their model."""
        instrument = self.instruments.get(name)
        label, model = getattr(instrument, 'label', None), getattr(instrument, 'model', None)
        return f"{label} ({model})" if label and model else name

    def _provider(self, name):
        return getattr(self.instruments.get(name), 'base_url', None) or name

    def _limited_error(self, names, stopped):
        from runesmith.pacing import limited_summary, used_words
        now = self._clock()
        named = [n for n in names if n in stopped]
        # "Add a second free provider" is the way out when every model there is belongs to one provider, however many
        # models of it are set up: they all stop with the same key.
        alone = len({self._provider(n) for n in names}) == 1

        def used(n):
            if self.counts is None:
                return None
            instrument = self.instruments[n]
            return used_words(self.counts.today(n, getattr(instrument, 'base_url', ''), free=bool(getattr(instrument, 'free_tier', False))),
                              refused=bool(stopped[n]['daily']))
        rows = [{'name': n, 'label': getattr(self.instruments.get(n), 'label', None) or n,
                 'model': getattr(self.instruments.get(n), 'model', None) if getattr(self.instruments.get(n), 'label', None) else None,
                 'until': stopped[n]['until'], 'daily': stopped[n]['daily'], 'used': used(n)} for n in named]
        words = limited_summary(rows, now, alone=alone)
        said = {n: stopped[n].get('said') for n in named if stopped[n].get('said')}
        detail = '; '.join(f"{self._name(n)}: {text}" for n, text in said.items()) or None
        return TransportCensored(words, plain=words, detail=detail,
                                 receipt={'not_admitted': True, 'paced': 'limited', 'said': said,
                                          'limited_until': min(stopped[n]['until'] for n in named)})

    def _busy_error(self, names, outcome):
        from runesmith.pacing import busy_words
        providers = list(dict.fromkeys(getattr(self.instruments.get(n), 'label', None) or n for n in names))
        words = busy_words(', '.join(providers))
        return TransportCensored(f"{words} ({(outcome.error or '')[:300]})", plain=words,
                                 detail=(outcome.error or '')[:1500] or None, receipt={'not_admitted': True, 'paced': 'busy'})

    def _attempt(self, role, names, attempt, *, prompt, system, schema, max_tokens, key, reasoning_effort, gone=None,
                 own_effort_first=False, order=None, soft_effort=None, room=None, room_retry=False):
        refused = set()
        gone = {} if gone is None else gone
        order = list(order or names)
        while True:
            live = [n for n in names if n not in gone]
            if not live:                                # every model refused for good: its own plain words
                return next(iter(gone.values()))
            # Rotate over the declared fallbacks: from this attempt's place in the role's whole order, the next model that
            # may still be asked. A model held back at its limit keeps its place, so the one after it is next, not the one after that.
            start = attempt % len(order)
            name = next(n for n in (order[(start + k) % len(order)] for k in range(len(order))) if n in live)
            instrument = self.instruments[name]
            own = getattr(instrument, 'default_reasoning', None)
            effort = (own or reasoning_effort) if own_effort_first else (reasoning_effort or own)
            takes_effort = bool(getattr(instrument, 'takes_reasoning_effort', False))
            if effort is None and soft_effort and takes_effort:
                effort = soft_effort
            asked_tokens = max(max_tokens, room) if room and takes_effort else max_tokens
            outcome = instrument.complete(prompt=prompt, system=system, schema=schema, max_tokens=asked_tokens,
                                          key=f"{key}-a{attempt}", reasoning_effort=effort)
            attempt += 1
            outcome.attempts = attempt
            identity = instrument.identity()
            answered_model = outcome.receipt.get('model')
            provider = outcome.receipt.get('provider')
            if answered_model and provider and not answered_model.startswith(provider + ':'):
                answered_model = provider + ':' + answered_model
            outcome.receipt = dict(outcome.receipt, **identity, role=role,
                                   prompt_bytes=len(prompt.encode("utf-8")), max_tokens_asked=asked_tokens)
            if room_retry:
                outcome.receipt['asked_again_with_room'] = True
            if answered_model:
                outcome.receipt.update(requested_model=identity['model'], model=answered_model)
            if self._on_call:
                self._on_call({"role": role, "key": key, "attempt": attempt, "ok": outcome.ok,
                               "error_kind": outcome.error_kind, "error": (outcome.error or "")[:300] or None,
                               "latency_s": round(outcome.latency_s, 3), **outcome.receipt})
            refused.add(name)
            # Nothing ran and nothing was charged: refused at submission, or refused by every route (journey J11-F2),
            # or refused by a model called directly before it answered: too large for it, a refused key, an unknown
            # model (review of J11-G17: a directly called Groq's size refusal never let the role's next model try).
            turned_away = (outcome.receipt.get('not_admitted') or outcome.receipt.get('no_route_accepted')
                           or outcome.receipt.get('refused_before_answer'))
            if not outcome.ok and (outcome.receipt.get('refused_before_answer') or outcome.receipt.get('no_route_accepted')):
                # Refused for good, or by every route it has for this very request: a later backoff tier does not
                # ask it again (reviews). Refused at admission (capacity) may pass later, so it is asked again.
                gone[name] = outcome
            if outcome.ok or not turned_away or set(names) <= refused | set(gone):
                return outcome
