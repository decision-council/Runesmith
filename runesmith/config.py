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
                                   "model": "gemini-2.5-flash", "api_key_env": "GEMINI_API_KEY"},
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


def build_instrument(name: str, spec: dict[str, Any], home: Path | None = None) -> Instrument:
    kind = spec.get("kind")
    if kind == "scripted":                      # offline demos and tests: answers are replayed in order
        return ScriptedInstrument(name, spec.get("answers", []))
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
                                      tolerant_json=bool(spec.get("tolerant_json", True)))
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


def build_router(config: dict[str, Any], *, home: Path | None = None, **kwargs) -> Router:
    instruments = {name: build_instrument(name, spec, home) for name, spec in config["instruments"].items()}
    return Router(instruments, config["roles"], **kwargs)


def envelope_from(config: dict[str, Any]) -> Envelope:
    fields = {k: v for k, v in (config.get("envelope") or {}).items() if k in Envelope.__dataclass_fields__}
    return Envelope(**fields)
