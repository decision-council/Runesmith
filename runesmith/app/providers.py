"""Where Runesmith's thinking can come from: presets, local discovery, model listing and a connection test.

Everything here is a convenience over one fact: any OpenAI-compatible endpoint
works, and so do Milliner and a person relaying to a chat window. Suggested model
names are starting points, not requirements; the owner can type any model id, and
``list_models`` asks the provider what it actually serves. Model names go stale every few months, so the names
below are only the fallback for when the provider's own list cannot be read: with a key, ``list_models`` also
returns a ``recommended`` model and a few ``choices`` chosen from what the provider serves today, and a provider's
own "no longer available, use X instead" answer becomes a one-click switch (``model_hint``).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# The "suggested" names are a FALLBACK, shown before a key is added and used when the provider's list cannot be read;
# with a key, the live list decides (recommend_models). Names last checked against the providers' public model pages
# on 2026-10-04: Gemini (3.8 and 3.6 flash are current; 2.5 is limited to users who already used it), Anthropic (Opus 5.5 and
# Sonnet 5.5 are current), Groq (gpt-oss-20b/120b are production), DeepSeek (its page lists deepseek-flash and deepseek-v4-pro),
# Together (gpt-oss-120b and Llama 3.3 70B Turbo are in its chat table). Not confirmable from a page, left as they were:
# OpenAI, Mistral (the -latest aliases), OpenRouter, NVIDIA (checked 2026-09-28). The live list covers them once a key is in.
PRESETS: list[dict[str, Any]] = [
    {"id": "ollama", "label": "Ollama", "group": "This computer", "kind": "openai",
     "base_url": "http://127.0.0.1:11434/v1", "key": "none", "local": True,
     "suggested": ["qwen2.5-coder:7b", "qwen2.5-coder:3b", "llama3.2:3b"],
     "blurb": "Free and private: models run on this computer. Install from ollama.com, then pull a model. "
              "Runesmith asks Ollama for a context window that fits each request.",
     "setup": "ollama pull qwen2.5-coder:7b"},
    {"id": "lmstudio", "label": "LM Studio", "group": "This computer", "kind": "openai",
     "base_url": "http://127.0.0.1:1234/v1", "key": "none", "local": True, "suggested": [], "json_mode": "json_schema",
     "blurb": "Free and private. Start LM Studio's local server and load a model.",
     "setup": "load the model with a context length of at least 16384 tokens, then Developer: Start Server"},
    {"id": "llamacpp", "label": "llama.cpp server", "group": "This computer", "kind": "openai",
     "base_url": "http://127.0.0.1:8080/v1", "key": "none", "local": True, "suggested": [],
     "blurb": "The leanest local option: `llama-server -m model.gguf`.",
     "setup": "llama-server -m model.gguf --ctx-size 16384   (a context of 16384 tokens or more)"},
    {"id": "openrouter", "label": "OpenRouter", "group": "With a key", "kind": "openai",
     "base_url": "https://openrouter.ai/api/v1", "key": "required", "key_url": "https://openrouter.ai/keys",
     "suggested": ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "anthropic/claude-opus-4.5"],
     "blurb": "One key for hundreds of models, several of them free."},
    {"id": "groq", "label": "Groq", "group": "With a key", "kind": "openai",
     "base_url": "https://api.groq.com/openai/v1", "key": "required", "key_url": "https://console.groq.com/keys",
     "suggested": ["openai/gpt-oss-20b", "openai/gpt-oss-120b"], "max_request_tokens": 8000,
     "blurb": "Very fast, with a free tier (up to 8,000 tokens a minute per model, so large requests need another model)."},
    {"id": "gemini", "label": "Google Gemini", "group": "With a key", "kind": "openai",
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "key": "required",
     "key_url": "https://aistudio.google.com/apikey", "suggested": ["gemini-3.8-flash", "gemini-3.6-flash"],
     "blurb": "A free tier through Google AI Studio."},
    {"id": "mistral", "label": "Mistral", "group": "With a key", "kind": "openai",
     "base_url": "https://api.mistral.ai/v1", "key": "required", "key_url": "https://console.mistral.ai/api-keys",
     "suggested": ["codestral-latest", "mistral-small-latest"],
     "blurb": "Code-strong models; the free plan includes monthly API credits."},
    # Many hosted models with a free endpoint (build.nvidia.com/models, checked 2026-09-28). The journeys' Planner and
    # Checker fell back to NVIDIA's Nemotron when Gemini's free tier ran out, but it had no ready-made tile.
    {"id": "nvidia", "label": "NVIDIA", "group": "With a key", "kind": "openai",
     "base_url": "https://integrate.api.nvidia.com/v1", "key": "required", "key_url": "https://build.nvidia.com/models",
     "suggested": ["nvidia/nemotron-3-super-120b-a12b", "moonshotai/kimi-k3"],
     "blurb": "Many models with a free endpoint, among them NVIDIA Nemotron and Kimi."},
    {"id": "deepseek", "label": "DeepSeek", "group": "With a key", "kind": "openai",
     "base_url": "https://api.deepseek.com/v1", "key": "required", "key_url": "https://platform.deepseek.com/api_keys",
     "suggested": ["deepseek-flash", "deepseek-v4-pro"], "blurb": "Strong and inexpensive."},
    {"id": "openai", "label": "OpenAI", "group": "With a key", "kind": "openai",
     "base_url": "https://api.openai.com/v1", "key": "required", "key_url": "https://platform.openai.com/api-keys",
     "suggested": ["gpt-5.1", "gpt-5-mini"], "blurb": "Paid models."},
    {"id": "anthropic", "label": "Anthropic (OpenAI-compatible)", "group": "With a key", "kind": "openai",
     "base_url": "https://api.anthropic.com/v1", "key": "required", "key_url": "https://console.anthropic.com/settings/keys",
     "suggested": ["claude-opus-5-5", "claude-sonnet-5-5"],
     "blurb": "Claude through Anthropic's OpenAI-compatible layer. Test the connection after saving."},
    {"id": "together", "label": "Together AI", "group": "With a key", "kind": "openai",
     "base_url": "https://api.together.xyz/v1", "key": "required", "key_url": "https://api.together.ai/settings/api-keys",
     "suggested": ["openai/gpt-oss-120b", "meta-llama/Llama-3.3-70B-Instruct-Turbo"], "blurb": "Many open models."},
    {"id": "custom", "label": "Any OpenAI-compatible endpoint", "group": "Advanced", "kind": "openai",
     "base_url": "", "key": "optional", "suggested": [],
     "blurb": "vLLM, a company gateway, or any server that speaks the OpenAI chat API."},
    # Internal: a router run by Runesmith's own team, not offered to the public (see public_presets).
    {"id": "milliner", "label": "Milliner router", "group": "Advanced", "kind": "milliner", "internal": True,
     "base_url": "http://127.0.0.1:8765", "key": "required", "suggested": [],
     "blurb": "Route through a Milliner gateway with an agent token."},
    {"id": "manual", "label": "A chat window (copy and paste)", "group": "No key needed", "kind": "manual",
     "base_url": "", "key": "none", "suggested": [],
     "blurb": "Runesmith writes each request; paste it into any chat model you can reach and paste the answer back, "
              "right here. Best for the author role: a few calls per improvement."},
]
PRESET_BY_ID = {p["id"]: p for p in PRESETS}


def public_presets(kinds_in_use=()) -> list[dict[str, Any]]:
    """The tiles an owner is offered. Internal ones appear only where one is already set up, or with
    RUNESMITH_INTERNAL=1, so an existing internal instrument can still be edited."""
    import os
    internal = os.environ.get("RUNESMITH_INTERNAL") == "1"
    return [p for p in PRESETS if not p.get("internal") or internal or p["kind"] in set(kinds_in_use)]


# ----------------------------------------------------------------- which model to suggest, from the live list --

def _versions(text: str) -> tuple[int, ...]:
    """Numbers as integers, so 3.10 is newer than 3.8, padded so 3 is older than 3.8."""
    return (tuple(int(n) for n in re.findall(r"\d+", text)) + (0, 0, 0, 0))[:4]


def _older_first(version: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(-n for n in version)


_GEMINI = re.compile(r"^gemini-(?P<v>\d+(?:\.\d+)*)-(?P<tier>flash|pro)(?P<rest>(?:-[a-z0-9.]+)*)$")
# Models in Google's list that do not chat in text (or are not for general use): never recommended.
_GEMINI_NOT_CHAT = ("image", "tts", "audio", "live", "embed", "robotics", "computer", "native", "vision", "dictation",
                    "translate", "customtools")


def _gemini_model(model_id: str) -> dict[str, Any] | None:
    found = _GEMINI.match(model_id)
    if not found or any(word in found["rest"] for word in _GEMINI_NOT_CHAT):
        return None
    rest = found["rest"]
    lite = "lite" in rest
    preview = bool(re.search(r"preview|exp|beta|\d{2}-\d{2,4}", rest))
    # 0 stable, 1 stable lite, 2 preview, 3 preview lite: a stable model beats any preview, and "-lite" is the last resort.
    return {"id": model_id, "tier": found["tier"], "version": _versions(found["v"]), "lite": lite, "preview": preview,
            "rank": (2 if preview else 0) + (1 if lite else 0), "pinned": bool(re.search(r"-\d{3}$", rest))}


def _gemini_order(row: dict[str, Any]) -> tuple:
    return (row["rank"], _older_first(row["version"]), row["pinned"], row["id"])


def _recommend_gemini(ids: list[str]) -> tuple[str | None, list[str]]:
    """The newest generally available "flash" model: not "pro", "-lite" only when nothing else, a preview only when no
    stable one exists. The other good choices: the next flash generations, the newest lite, the newest pro."""
    rows = [row for row in map(_gemini_model, ids) if row]
    flash = sorted((r for r in rows if r["tier"] == "flash"), key=_gemini_order)
    pro = sorted((r for r in rows if r["tier"] == "pro" and not r["lite"]), key=_gemini_order)
    if not flash:
        return None, [r["id"] for r in pro[:2]]
    best = flash[0]
    choices: list[str] = []
    seen = {best["version"]}
    for row in flash[1:]:                                       # older flash generations, one name each
        if not row["lite"] and not row["preview"] and row["version"] not in seen and len(choices) < 2:
            choices.append(row["id"]); seen.add(row["version"])
    lite = next((r for r in flash if r["lite"] and r["id"] != best["id"] and not r["preview"]), None)
    if lite:
        choices.append(lite["id"])
    if pro:
        choices.append(pro[0]["id"])
    return best["id"], choices


# Families used when none of a preset's suggestions is served any more: the newest name of each, best first.
_FAMILIES: dict[str, list[str]] = {
    "openai": [r"gpt-(?P<v>\d+(?:\.\d+)*)", r"gpt-(?P<v>\d+(?:\.\d+)*)-mini"],
    "anthropic": [r"claude-opus-(?P<v>\d+(?:[.-]\d+)*?)", r"claude-sonnet-(?P<v>\d+(?:[.-]\d+)*?)"],
}
_DATED = r"(?:-\d{8}|-\d{4}-\d{2}-\d{2})?"


def _family_top(pattern: str, ids: list[str]) -> str | None:
    rows = []
    for model_id in ids:
        found = re.fullmatch(pattern + _DATED, model_id)
        if found:                                               # newest version first, an undated name before a dated one
            dated = bool(re.search(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$", model_id))
            rows.append((_older_first(_versions(found["v"])), dated, model_id))
    return min(rows)[2] if rows else None


def _match_suggestion(suggestion: str, ids: list[str]) -> str | None:
    """A suggested name the list serves, exactly or as its dated release (claude-opus-4-5 -> claude-opus-4-5-20251101)."""
    if suggestion in ids:
        return suggestion
    dated = [i for i in ids if i.startswith(suggestion + "-") and re.fullmatch(r"\d{8}|\d{4}-\d{2}-\d{2}", i[len(suggestion) + 1:])]
    return max(dated) if dated else None


def recommend_models(preset_id: str, ids: list[str]) -> dict[str, Any]:
    """Pick a default model for a preset from the model ids its provider serves right now, and a few other good
    choices. ``recommended`` is None when nothing in the list fits (the form then keeps the preset's fallback name).
    Gemini: the newest generally available flash. Local servers: a suggestion that is loaded, else the first model.
    Others: the first suggestion the list contains, else the newest name of a known family."""
    preset = PRESET_BY_ID.get(preset_id) or {}
    ids = [i for i in dict.fromkeys(ids) if isinstance(i, str) and i]
    best: str | None = None
    choices: list[str] = []
    if preset_id == "gemini":
        best, choices = _recommend_gemini(ids)
    if best is None:
        served = [m for m in (_match_suggestion(s, ids) for s in preset.get("suggested") or []) if m]
        if served:
            best, choices = served[0], served[1:]
        if preset.get("local"):
            chat = [i for i in ids if "embed" not in i.lower()]
            if best is None and chat:
                best = chat[0]
            choices = [i for i in chat[:6] if i != best] if best else []
        else:
            tops = [t for t in (_family_top(p, ids) for p in _FAMILIES.get(preset_id, [])) if t]
            if best is None and tops:
                best = tops[0]
            choices += [t for t in tops if t != best and t not in choices]
    return {"recommended": best, "choices": [c for c in dict.fromkeys(choices) if c != best][:5]}


# ----------------------------------------------------------------- the provider's own "use X instead" --

_GONE = re.compile(r"no longer|deprecat|retire|decommission|discontinu|shut ?down|sunset|not[ _]found|does not exist"
                   r"|doesn't exist|no such model|invalid model|not a valid model|unknown model|no endpoints found|not available"
                   r"|unavailable",
                   re.IGNORECASE)
_USE = re.compile(r"\b(?:use|using|try|switch to|migrate to|move to|upgrade to|replaced (?:by|with)|superseded by"
                  r"|did you mean)\s+(?:the\s+)?(?:model\s+)?[\\\"'`]*(?P<id>[A-Za-z0-9][A-Za-z0-9._:/@+-]{1,118}[A-Za-z0-9])",
                  re.IGNORECASE)


def model_hint(message: str, current: str = "") -> str | None:
    """The model a provider's refusal points to ("... is no longer available to new users. Please update your code to
    use models/gemini-3.8-flash"), or None. Works on the plain words and on the JSON or repr they come wrapped in;
    answers only when the message says the model is gone, and never returns the current model or a web address."""
    text = str(message or "")
    if not _GONE.search(text):
        return None
    now = str(current or "").lower().removeprefix("models/")
    for found in _USE.finditer(text):
        name = found["id"].removeprefix("models/")
        low = name.lower()
        if (low == now or low.startswith(("http:", "https:")) or "//" in name or re.search(r"\.(com|ai|org|io|dev|net)\b", low)
                or re.match(r"v\d", low) or not re.search(r"[\d/-]", name)):
            continue
        return name
    return None


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


def list_models(base_url: str, key: str = "", *, kind: str = "openai", provider: str = "",
                timeout: float = 8.0, preset: str = "") -> dict[str, Any]:
    """Read the selected endpoint's catalog, without generating or probing models. For an OpenAI-style endpoint the
    answer also carries ``recommended`` (the model to pre-fill, or None) and ``choices`` (other good ones), chosen from
    the whole list by the preset's rule (``recommend_models``)."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    base = base_url.rstrip("/")
    if kind == "milliner":
        if not isinstance(provider, str) or (provider and not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", provider)):
            return {"ok": False, "models": [], "detail": "Use a bare provider name, such as opencode or cline."}
        # Milliner is not an OpenAI /models endpoint: it returns `models`,
        # with provider-qualified call_name values. Keep this selector free-only.
        url = base + ("/models" if base.endswith("/v1") else "/v1/models")
        url += "?free=true&profiles=false&limit=500"
        if provider:
            url += "&provider=" + provider
    else:
        url = base + "/models"
    status, body = _get_json(url, headers=headers, timeout=timeout)
    if status != 200 or not isinstance(body, dict):
        return {"ok": False, "status": status, "models": []}
    rows = body.get("models" if kind == "milliner" else "data")
    if not isinstance(rows, list):
        return {"ok": False, "status": status, "models": [], "detail": "Unrecognized catalog response."}
    ids = set()
    for model in rows:
        if not isinstance(model, dict):
            continue
        model_id = model.get("call_name" if kind == "milliner" else "id")
        if kind == "milliner" and not model_id:
            provider, bare = model.get("provider"), model.get("model_id")
            if isinstance(provider, str) and provider and isinstance(bare, str) and bare:
                model_id = provider + ":" + bare
        if isinstance(model_id, str) and model_id.strip():
            ids.add(model_id.strip())
    if kind != "milliner" and (preset == "gemini" or "generativelanguage.googleapis.com" in base):
        ids = {i.removeprefix("models/") for i in ids}      # Google lists "models/gemini-..."; the chat call takes the bare name
    result = {"ok": True, "status": status, "models": sorted(ids)[:500], "count": len(ids)}
    if kind != "milliner":
        result.update(recommend_models(preset, sorted(ids)))      # from the whole list, not the first 500 names
    if kind == "milliner":
        result['provider'] = provider
        result['detail'] = ('Up to 500 free-catalog entries. Listing does not confirm routing permission, '
                            'remaining quota or authoring quality. Filter by provider to narrow large catalogs, '
                            'or enter an exact model ID.')
    return result


def test_instrument(name: str, spec: dict[str, Any], home) -> dict[str, Any]:
    """One tiny JSON call through the kernel's own instrument, exactly as work would make it."""
    from runesmith.config import build_instrument, default_reasoning
    if spec.get("kind") == "manual":
        return {"ok": True, "detail": "a chat-window relay has nothing to test; requests appear under Inference when work needs one"}
    try:
        instrument = build_instrument(name, spec, home)
    except (KeyError, ValueError) as error:
        return {"ok": False, "detail": f"incomplete settings: {error}"}
    started = time.monotonic()
    out = instrument.complete(prompt='Reply with the JSON object {"ok": true}.', system="Reply with JSON only.",
                              schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                              max_tokens=400, key=f"runesmith-test-{int(time.time())}",
                              reasoning_effort=default_reasoning(spec))     # as work sends it (review of J11-B8)
    if out.ok:
        detail = "answered with usable JSON"
    elif out.error_kind == "config":                        # already plain words (a refused key, a missing model)
        detail = (out.error or "the service refused this request")[:300]
    else:                                                   # journey J8-F3: say what happened, then the service's words
        from runesmith.app.planner import why_no_answer
        detail = why_no_answer(out.error or "no answer")[:300]
    result = {"ok": bool(out.ok), "latency_s": round(time.monotonic() - started, 2), "kind": out.error_kind,
              "detail": detail, "model": (out.receipt or {}).get("model") or spec.get("model")}
    if not out.ok and spec.get("kind") == "openai":
        hint = model_hint(out.error or "", spec.get("model") or "")      # from the whole answer, before it is cut short
        if hint:
            result["suggested_model"] = hint
    return result
