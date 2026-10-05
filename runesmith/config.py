"""Runesmith home and configuration (``<home>/runesmith.json``).

The home directory holds everything Runesmith learns: the ledger, frozen
generations and the ACTIVE pointer, memory, session records, and the self and
environment maps. Instruments are declared by name; secrets are referenced by
environment-variable name (or an env file and key), or by the name of a key saved on this
machine (``api_key_secret`` / ``token_secret``, see ``runesmith.keystore``); never stored in the config.

Any OpenAI-compatible endpoint works, including a weak local model::

    {"instruments": {"local": {"kind": "openai", "base_url": "http://127.0.0.1:11434/v1",
                               "model": "qwen2.5-coder:7b"}},
     "roles": {"repair": ["local"], "kaizen": ["local"]}}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runesmith.instruments import (Instrument, MillinerInstrument, OpenAICompatInstrument, Router,
                                   ScriptedInstrument, secret_from)
from runesmith.opportunity import Envelope

DEFAULT_CONFIG: dict[str, Any] = {
    "schema": "runesmith.config.v1",
    "instruments": {
        "local": {"kind": "openai", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5-coder:7b",
                  "json_mode": "json_object", "note": "Ollama; any OpenAI-compatible server works"},
    },
    "roles": {"repair": ["local"], "kaizen": ["local"]},
    "envelope": {"max_calls": 5, "max_tokens": 8192, "max_signal_runs": 45, "max_request_bytes": 64000,
                 "wall_s": 1800.0},
    "examples": {
        "groq_free_tier": {"kind": "openai", "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-20b",
                           "api_key_env": "GROQ_API_KEY"},
        "openrouter_free_small": {"kind": "openai", "base_url": "https://openrouter.ai/api/v1",
                                  "model": "liquid/lfm-2.5-2.6b:free", "api_key_env": "OPENROUTER_API_KEY",
                                  "note": "2.6B free model; repaired real code through the suit in 2026-09-24 probes"},
        "gemini_openai_endpoint": {"kind": "openai", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                                   "model": "gemini-3.8-flash", "api_key_env": "GEMINI_API_KEY"},
        "milliner_router": {"kind": "milliner", "base_url": "http://127.0.0.1:8765", "model": "groq:openai/gpt-oss-20b",
                            "token_env": "MILLINER_TOKEN"},
        "chat_by_hand": {"kind": "manual", "model": "the chat model you relay to", "timeout_s": 3600,
                         "note": "no key needed: Runesmith writes each request to <home>/manual/, you paste it into any "
                                 "chat model and return the reply with `runesmith manual answer`; suited to the kaizen role"},
    },
}


def home_dir(home: str | Path | None) -> Path:
    return Path(home or ".runesmith").resolve()


def load_config(home: Path) -> dict[str, Any]:
    path = Path(home) / "runesmith.json"
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    return json.loads(path.read_text(encoding="utf-8"))


def _ollama_address(spec: dict[str, Any]) -> bool:
    """An OpenAI-style instrument pointed at Ollama: its native API is used instead, for the context window (LS1)."""
    from urllib.parse import urlparse
    url = urlparse(str(spec.get("base_url") or ""))
    return spec.get("preset") == "ollama" or (url.port == 11434 and url.path.rstrip("/").endswith("/v1"))


def build_instrument(name: str, spec: dict[str, Any], home: Path | None = None) -> Instrument:
    kind = spec.get("kind")
    if kind == "ollama" or (kind == "openai" and _ollama_address(spec)):
        from runesmith.instruments import OllamaInstrument
        base = str(spec["base_url"]).rstrip("/")
        base = base[:-3] if base.endswith("/v1") else base
        return OllamaInstrument(name, spec["model"], base_url=base, timeout_s=float(spec.get("timeout_s", 900)),
                                max_context=int(spec.get("max_context", 32768)))
    if kind == "scripted":                      # offline demos and tests: answers are replayed in order
        return ScriptedInstrument(name, spec.get("answers", []), model=str(spec.get("model") or "scripted"))
    if kind == "openai":
        if spec.get("api_key_secret"):
            from runesmith.keystore import KeyStore
            key = KeyStore(home_dir(home)).supplier(spec["api_key_secret"])
        elif spec.get("api_key_env") or spec.get("api_key_env_file"):
            key = secret_from(env_var=spec.get("api_key_env"), env_file=spec.get("api_key_env_file"),
                              key=spec.get("api_key_key"))
        else:
            key = None
        return OpenAICompatInstrument(name, spec["model"], base_url=spec["base_url"], api_key=key,
                                      timeout_s=float(spec.get("timeout_s", 600)),
                                      json_mode=spec.get("json_mode", "json_object"),
                                      tolerant_json=bool(spec.get("tolerant_json", True)),
                                      max_request_tokens=spec.get("max_request_tokens"))
    if kind == "milliner":
        if spec.get("token_secret"):
            from runesmith.keystore import KeyStore
            token = KeyStore(home_dir(home)).supplier(spec["token_secret"])
        else:
            token = secret_from(env_var=spec.get("token_env"), env_file=spec.get("token_env_file"), key=spec.get("token_key"))
        return MillinerInstrument(name, spec["model"], base_url=spec["base_url"], token=token,
                                  caller_tag=spec.get("caller_tag", "runesmith"), timeout_s=float(spec.get("timeout_s", 900)),
                                  allow_uncatalogued=bool(spec.get("allow_uncatalogued", False)),
                                  budget_tag=spec.get("budget_tag"), fallback_models=spec.get('fallback_models'),
                                  request_dir=home_dir(home)/'inference-requests')
    if kind == "manual":                        # a person relays each request to a chat model (runesmith.manual)
        from runesmith.manual import ManualInstrument
        directory = Path(spec["dir"]) if spec.get("dir") else home_dir(home) / "manual"
        return ManualInstrument(name, spec.get("model", "chat"), directory=directory,
                                timeout_s=float(spec.get("timeout_s", 3600)), poll_s=float(spec.get("poll_s", 2.0)))
    raise ValueError(f"instrument {name!r}: unknown kind {kind!r}")


REASONING_EFFORTS = ('low', 'medium', 'high')


def default_reasoning(spec: dict[str, Any]) -> str | None:
    """The reasoning effort an instrument's settings name for every call that names none, or None."""
    effort = spec.get("reasoning_effort")
    return effort if effort in REASONING_EFFORTS else None


def is_free_tier(spec: dict[str, Any]) -> bool:
    """Whether an instrument is a service's free key (its preset says so, or its address is that preset's): every retry
    spends from a small allowance, so such an instrument is asked less often (runesmith.pacing)."""
    if spec.get("kind") != "openai":
        return False
    from runesmith.app.providers import PRESETS, PRESET_BY_ID
    if (PRESET_BY_ID.get(spec.get("preset")) or {}).get("free_tier"):
        return True
    address = str(spec.get("base_url") or "").rstrip("/")
    return bool(address) and any(p.get("free_tier") and p["base_url"].rstrip("/") == address for p in PRESETS)


def build_router(config: dict[str, Any], *, home: Path | None = None, **kwargs) -> Router:
    instruments = {name: build_instrument(name, spec, home) for name, spec in config["instruments"].items()}
    if home is not None:                            # a service that said "429" is not asked again until its reset
        from runesmith.pacing import Pacing
        kwargs.setdefault("pacing", Pacing(Path(home) / "PACING.json"))
    for name, spec in config["instruments"].items():
        instruments[name].free_tier = is_free_tier(spec)
        # A model's own reasoning effort, used when a call names none (journey J11-B8: Nemotron 3 Super spent the
        # whole answer budget on hidden reasoning, looping to the 16,384-token cap, and each truncated answer used
        # up a try; "low" is what fixed the same model elsewhere).
        instruments[name].default_reasoning = default_reasoning(spec)
    return Router(instruments, config["roles"], **kwargs)


def envelope_from(config: dict[str, Any]) -> Envelope:
    fields = {k: v for k, v in (config.get("envelope") or {}).items() if k in Envelope.__dataclass_fields__}
    return Envelope(**fields)
