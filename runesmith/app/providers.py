"""Where Runesmith's thinking can come from: presets, local discovery, model listing and a connection test.

Everything here is a convenience over one fact: any OpenAI-compatible endpoint
works, and so do Milliner and a person relaying to a chat window. Suggested model
names are starting points, not requirements; the owner can type any model id, and
``list_models`` asks the provider what it actually serves.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PRESETS: list[dict[str, Any]] = [
    {"id": "ollama", "label": "Ollama", "group": "This computer", "kind": "openai",
     "base_url": "http://127.0.0.1:11434/v1", "key": "none", "local": True,
     "suggested": ["qwen2.5-coder:7b", "qwen2.5-coder:3b", "llama3.2:3b"],
     "blurb": "Free and private: models run on this computer. Install from ollama.com, then pull a model.",
     "setup": "ollama pull qwen2.5-coder:7b"},
    {"id": "lmstudio", "label": "LM Studio", "group": "This computer", "kind": "openai",
     "base_url": "http://127.0.0.1:1234/v1", "key": "none", "local": True, "suggested": [],
     "blurb": "Free and private. Start LM Studio's local server and load a model."},
    {"id": "llamacpp", "label": "llama.cpp server", "group": "This computer", "kind": "openai",
     "base_url": "http://127.0.0.1:8080/v1", "key": "none", "local": True, "suggested": [],
     "blurb": "The leanest local option: `llama-server -m model.gguf`."},
    {"id": "openrouter", "label": "OpenRouter", "group": "With a key", "kind": "openai",
     "base_url": "https://openrouter.ai/api/v1", "key": "required", "key_url": "https://openrouter.ai/keys",
     "suggested": ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "anthropic/claude-opus-4.5"],
     "blurb": "One key for hundreds of models, several of them free."},
    {"id": "groq", "label": "Groq", "group": "With a key", "kind": "openai",
     "base_url": "https://api.groq.com/openai/v1", "key": "required", "key_url": "https://console.groq.com/keys",
     "suggested": ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"],
     "blurb": "Very fast, with a free tier."},
    {"id": "gemini", "label": "Google Gemini", "group": "With a key", "kind": "openai",
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "key": "required",
     "key_url": "https://aistudio.google.com/apikey", "suggested": ["gemini-2.5-flash", "gemini-2.5-pro"],
     "blurb": "A free tier through Google AI Studio."},
    {"id": "mistral", "label": "Mistral", "group": "With a key", "kind": "openai",
     "base_url": "https://api.mistral.ai/v1", "key": "required", "key_url": "https://console.mistral.ai/api-keys",
     "suggested": ["codestral-latest", "mistral-small-latest"], "blurb": "Code-strong models, a free experiment tier."},
    {"id": "deepseek", "label": "DeepSeek", "group": "With a key", "kind": "openai",
     "base_url": "https://api.deepseek.com/v1", "key": "required", "key_url": "https://platform.deepseek.com/api_keys",
     "suggested": ["deepseek-chat", "deepseek-reasoner"], "blurb": "Strong and inexpensive."},
    {"id": "openai", "label": "OpenAI", "group": "With a key", "kind": "openai",
     "base_url": "https://api.openai.com/v1", "key": "required", "key_url": "https://platform.openai.com/api-keys",
     "suggested": ["gpt-5.1", "gpt-5-mini"], "blurb": "Paid models."},
    {"id": "anthropic", "label": "Anthropic (OpenAI-compatible)", "group": "With a key", "kind": "openai",
     "base_url": "https://api.anthropic.com/v1", "key": "required", "key_url": "https://console.anthropic.com/settings/keys",
     "suggested": ["claude-opus-4-5", "claude-sonnet-4-5"],
     "blurb": "Claude through Anthropic's OpenAI-compatible layer. Test the connection after saving."},
    {"id": "together", "label": "Together AI", "group": "With a key", "kind": "openai",
     "base_url": "https://api.together.xyz/v1", "key": "required", "key_url": "https://api.together.ai/settings/api-keys",
     "suggested": [], "blurb": "Many open models."},
    {"id": "custom", "label": "Any OpenAI-compatible endpoint", "group": "Advanced", "kind": "openai",
     "base_url": "", "key": "optional", "suggested": [],
     "blurb": "vLLM, a company gateway, or any server that speaks the OpenAI chat API."},
    {"id": "milliner", "label": "Milliner router", "group": "Advanced", "kind": "milliner",
     "base_url": "http://127.0.0.1:8765", "key": "required", "suggested": [],
     "blurb": "Route through a Milliner gateway with an agent token."},
    {"id": "manual", "label": "A chat window (copy and paste)", "group": "No key needed", "kind": "manual",
     "base_url": "", "key": "none", "suggested": [],
     "blurb": "Runesmith writes each request; paste it into any chat model you can reach and paste the answer back, "
              "right here. Best for the author role: a few calls per improvement."},
]
PRESET_BY_ID = {p["id"]: p for p in PRESETS}


def _get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 3.0) -> tuple[int, Any]:
    request = Request(url, headers=dict(headers or {}), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "null")
    except HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode("utf-8") or "null")
        except ValueError:
            return error.code, None
    except (URLError, OSError, TimeoutError, ValueError):
        return 0, None


def discover_local(timeout: float = 0.8) -> list[dict[str, Any]]:
    """Local model servers answering on this computer, with the models they serve."""
    found = []
    status, body = _get_json("http://127.0.0.1:11434/api/tags", timeout=timeout)
    if status == 200 and isinstance(body, dict):
        models = [m.get("name") for m in body.get("models", []) if isinstance(m, dict) and m.get("name")]
        found.append({"preset": "ollama", "base_url": PRESET_BY_ID["ollama"]["base_url"], "models": models})
    for preset in ("lmstudio", "llamacpp"):
        base = PRESET_BY_ID[preset]["base_url"]
        status, body = _get_json(base + "/models", timeout=timeout)
        if status == 200 and isinstance(body, dict):
            models = [m.get("id") for m in body.get("data", []) if isinstance(m, dict) and m.get("id")]
            found.append({"preset": preset, "base_url": base, "models": models})
    return found


def list_models(base_url: str, key: str = "", *, timeout: float = 8.0) -> dict[str, Any]:
    """Ask an OpenAI-compatible endpoint which models it serves."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    status, body = _get_json(base_url.rstrip("/") + "/models", headers=headers, timeout=timeout)
    if status != 200 or not isinstance(body, dict):
        return {"ok": False, "status": status, "models": []}
    ids = sorted({m.get("id") for m in body.get("data", []) if isinstance(m, dict) and m.get("id")})
    return {"ok": True, "status": status, "models": ids[:500], "count": len(ids)}


def test_instrument(name: str, spec: dict[str, Any], home) -> dict[str, Any]:
    """One tiny JSON call through the kernel's own instrument, exactly as work would make it."""
    from runesmith.config import build_instrument
    if spec.get("kind") == "manual":
        return {"ok": True, "detail": "a chat-window relay has nothing to test; requests appear under Inference when work needs one"}
    try:
        instrument = build_instrument(name, spec, home)
    except (KeyError, ValueError) as error:
        return {"ok": False, "detail": f"incomplete settings: {error}"}
    started = time.monotonic()
    out = instrument.complete(prompt='Reply with the JSON object {"ok": true}.', system="Reply with JSON only.",
                              schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                              max_tokens=400, key=f"runesmith-test-{int(time.time())}")
    detail = "answered with usable JSON" if out.ok else (out.error or "no answer")[:300]
    return {"ok": bool(out.ok), "latency_s": round(time.monotonic() - started, 2), "kind": out.error_kind,
            "detail": detail, "model": (out.receipt or {}).get("model") or spec.get("model")}
