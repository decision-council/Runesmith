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

    def __init__(self, message, *, receipt=None):
        super().__init__(message)
        self.receipt = receipt or {}


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
        return error.code, payload if isinstance(payload, dict) else {"error": str(payload)[:500]}


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

    def __init__(self, name: str, model: str) -> None:
        self.name, self.model = name, model

    def identity(self) -> dict:
        return {"instrument": self.name, "kind": self.kind, "model": self.model}

    def complete(self, *, prompt: str, system: str, schema: dict | None, max_tokens: int,
                 key: str, reasoning_effort: str | None = None) -> CallOutcome:
        raise NotImplementedError


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
        body: dict[str, Any] = {"model": self.model, "prompt": prompt, "system": system, "priority": 1,
                                "wait": True, "timeout_s": max(1.0, self.timeout_s - 5.0),
                                "max_tokens": max_tokens, "idempotency_key": key}
        if self.fallback_models:
            body.pop('model')
            body.update(models=[self.model, *self.fallback_models], allow_fallback=True,
                        max_fallbacks=len(self.fallback_models))
        if schema is not None:
            body["json_schema"] = schema
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
            data = parse_json_answer(payload.get("text"), payload.get("parsed"))
        except (ValueError, json.JSONDecodeError) as error:
            return CallOutcome(False, text=payload.get("text"), error_kind="output",
                               error=f"invalid_json: {error}"[:600], latency_s=latency, receipt=receipt)
        return CallOutcome(True, data=data, text=payload.get("text"), latency_s=latency, receipt=receipt)


class OpenAICompatInstrument(Instrument):
    """Any OpenAI-compatible chat endpoint: Ollama, LM Studio, vLLM, Groq, OpenRouter, ..."""

    kind = "openai"

    def __init__(self, name: str, model: str, *, base_url: str, api_key: Callable[[], str] | None = None,
                 timeout_s: float = 600.0, json_mode: str = "json_object", transport: Transport = http_json,
                 tolerant_json: bool = True) -> None:
        super().__init__(name, model)
        self.base_url, self._api_key, self.timeout_s = base_url.rstrip("/"), api_key, timeout_s
        self.json_mode, self._transport, self.tolerant_json = json_mode, transport, tolerant_json

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
        started = time.monotonic()
        try:
            status, payload = self._transport("POST", f"{self.base_url}/chat/completions", headers, body, self.timeout_s)
        except (URLError, OSError, TimeoutError) as error:
            return CallOutcome(False, error_kind="transport", error=f"{type(error).__name__}: {error}",
                               latency_s=time.monotonic() - started)
        latency = time.monotonic() - started
        if not 200 <= status < 300:
            message = f"http_{status} " + json.dumps(payload.get("error", payload))[:500]
            return CallOutcome(False, error_kind=classify(message), error=message, latency_s=latency)
        try:
            choice = payload["choices"][0]
            text = choice["message"].get("content") or ""
            finish = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError):
            return CallOutcome(False, error_kind="output", error="bad_request: malformed completion", latency_s=latency)
        usage = payload.get("usage") or {}
        receipt = {"provider": self.base_url, "model": payload.get("model", self.model),
                   "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens")}
        if finish == "length":
            return CallOutcome(False, text=text, error_kind="output", error="truncated: finish_reason=length",
                               latency_s=latency, receipt=receipt)
        try:
            data = parse_json_answer(text, tolerant=self.tolerant_json)
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
    :class:`TransportCensored`. A call the gateway refused before admitting it
    (nothing ran, nothing was charged) moves straight on to the role's next
    instrument, each at most once per attempt, even when retries are off.
    """

    def __init__(self, instruments: Mapping[str, Instrument], roles: Mapping[str, str | list[str]],
                 *, backoff_s: tuple[float, ...] = DEFAULT_BACKOFF_S, sleep: Callable[[float], None] = time.sleep,
                 on_call: Callable[[dict], None] | None = None) -> None:
        self.instruments = dict(instruments)
        self.roles = {role: ([names] if isinstance(names, str) else list(names)) for role, names in roles.items()}
        for role, names in self.roles.items():
            missing = [n for n in names if n not in self.instruments]
            if missing:
                raise ValueError(f"role {role!r} names unknown instruments {missing}")
        self.backoff_s, self._sleep, self._on_call = tuple(backoff_s), sleep, on_call

    def call(self, role: str, *, prompt: str, system: str, schema: dict | None, max_tokens: int,
             key: str, reasoning_effort: str | None = None) -> CallOutcome:
        names = self.roles.get(role)
        if not names:
            raise KeyError(f"no instrument serves role {role!r}")
        errors = []
        attempt = 0
        for delay in (0,) + self.backoff_s:
            if delay:
                self._sleep(delay)
            outcome = self._attempt(role, names, attempt, prompt=prompt, system=system, schema=schema,
                                    max_tokens=max_tokens, key=key, reasoning_effort=reasoning_effort)
            attempt = outcome.attempts
            if outcome.ok or outcome.error_kind == "output":
                return outcome
            if outcome.receipt.get('no_retry'):
                raise TransportCensored(outcome.error or 'Saved remote request requires review', receipt=outcome.receipt)
            errors.append(outcome.error)
        raise TransportCensored(f"role {role!r}: no response after {attempt} attempts; last: {errors[-1] if errors else ''}")

    def _attempt(self, role, names, attempt, *, prompt, system, schema, max_tokens, key, reasoning_effort):
        refused = set()
        while True:
            name = names[attempt % len(names)]          # rotate over declared fallbacks
            instrument = self.instruments[name]
            outcome = instrument.complete(prompt=prompt, system=system, schema=schema, max_tokens=max_tokens,
                                          key=f"{key}-a{attempt}", reasoning_effort=reasoning_effort)
            attempt += 1
            outcome.attempts = attempt
            identity = instrument.identity()
            answered_model = outcome.receipt.get('model')
            provider = outcome.receipt.get('provider')
            if answered_model and provider and not answered_model.startswith(provider + ':'):
                answered_model = provider + ':' + answered_model
            outcome.receipt = dict(outcome.receipt, **identity, role=role,
                                   prompt_bytes=len(prompt.encode("utf-8")))
            if answered_model:
                outcome.receipt.update(requested_model=identity['model'], model=answered_model)
            if self._on_call:
                self._on_call({"role": role, "key": key, "attempt": attempt, "ok": outcome.ok,
                               "error_kind": outcome.error_kind, "error": (outcome.error or "")[:300] or None,
                               "latency_s": round(outcome.latency_s, 3), **outcome.receipt})
            refused.add(name)
            if outcome.ok or not outcome.receipt.get('not_admitted') or set(names) <= refused:
                return outcome
