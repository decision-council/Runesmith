"""A newcomer never meets a stale model name: the live list decides, the provider's own hint becomes a button.

Offline: lists are fixtures, and the one real call goes to a local stand-in that answers as Google did on 2026-10-04
(404 "This model models/gemini-2.5-flash is no longer available to new users ...").
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from local_standins import StandIn
from runesmith.app import providers
from runesmith.app.providers import PRESET_BY_ID, model_hint, recommend_models
from runesmith.app.server import api_instrument_model
from runesmith.app.workspace import Workspace, WorkspaceError

GOOGLE_404 = ("This model models/gemini-2.5-flash is no longer available to new users. "
              "Please update your code to use models/gemini-3.8-flash")
UI = (Path(__file__).parents[1] / "runesmith/app/static/js/views/inference.js").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------- the recommendation rule --

GEMINI_LIST = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-3.6-flash", "gemini-3.8-flash",
               "gemini-3.8-flash-lite", "gemini-3.8-pro", "gemini-3.8-flash-001", "gemini-3.10-flash-preview",
               "gemini-3.8-flash-image", "gemini-3.8-flash-live-001", "gemini-3.8-flash-tts", "gemini-flash-latest",
               "gemini-embedding-001", "text-embedding-004", "imagen-4.0-generate-001"]


def test_gemini_recommends_the_newest_stable_flash_not_a_preview_lite_pro_or_non_chat_model():
    got = recommend_models("gemini", GEMINI_LIST)
    assert got["recommended"] == "gemini-3.8-flash"            # not 3.10 preview, not -001 pinned, not pro, not lite
    assert got["choices"][:2] == ["gemini-3.6-flash", "gemini-2.5-flash"]       # older stable generations
    assert "gemini-3.8-flash-lite" in got["choices"] and "gemini-3.8-pro" in got["choices"]
    assert not {"gemini-3.8-flash-image", "gemini-3.8-flash-live-001", "gemini-3.8-flash-tts",
                "gemini-embedding-001", "gemini-3.10-flash-preview"} & ({got["recommended"]} | set(got["choices"]))


def test_gemini_versions_compare_as_numbers_and_the_order_is_stable_then_lite_then_preview():
    assert recommend_models("gemini", ["gemini-3.8-flash", "gemini-3.10-flash"])["recommended"] == "gemini-3.10-flash"
    assert recommend_models("gemini", ["gemini-3-flash", "gemini-3.8-flash"])["recommended"] == "gemini-3.8-flash"
    assert recommend_models("gemini", ["gemini-4-flash-preview", "gemini-3.8-flash"])["recommended"] == "gemini-3.8-flash"
    assert recommend_models("gemini", ["gemini-4-flash-preview", "gemini-3.8-flash-lite", "gemini-3.8-pro"])["recommended"] == "gemini-3.8-flash-lite"
    assert recommend_models("gemini", ["gemini-4-flash-preview-10-2026", "gemini-3.8-pro"])["recommended"] == "gemini-4-flash-preview-10-2026"
    assert recommend_models("gemini", ["gemini-3.8-pro", "gemini-3.8-flash-image"])["recommended"] is None
    assert recommend_models("gemini", [])["recommended"] is None


OPENAI_LIST = ["babbage-002", "dall-e-3", "gpt-4o", "gpt-5-mini", "gpt-5.1", "gpt-5.1-2025-11-13", "gpt-5.5",
               "gpt-5.5-mini", "gpt-5.5-codex", "text-embedding-3-small", "whisper-1"]


def test_an_openai_style_list_gives_the_first_suggestion_it_contains_and_the_newer_names_as_choices():
    got = recommend_models("openai", OPENAI_LIST)
    assert got["recommended"] == "gpt-5.1"                      # the preset's first suggestion, still served
    assert "gpt-5.5" in got["choices"] and "gpt-5-mini" in got["choices"]
    assert recommend_models("openai", ["gpt-4o", "gpt-5.5-2026-01-01", "gpt-5.5", "gpt-5.5-mini"])["recommended"] == "gpt-5.5"
    only_old = recommend_models("openai", ["gpt-4o", "text-embedding-3-small"])
    assert only_old["recommended"] is None and only_old["choices"] == []      # the form keeps its fallback name


def test_anthropic_dated_releases_match_their_suggestion_and_the_newest_family_name_is_a_choice():
    got = recommend_models("anthropic", ["claude-opus-5-5-20260922", "claude-sonnet-5-5-20260928", "claude-haiku-4-5-20251001"])
    assert got["recommended"] == "claude-opus-5-5-20260922" and "claude-sonnet-5-5-20260928" in got["choices"]
    gone = recommend_models("anthropic", ["claude-opus-6-0-20270101", "claude-opus-5-1-20260301", "claude-sonnet-6-0"])
    assert gone["recommended"] == "claude-opus-6-0-20270101"     # no suggestion served: the newest of the first family


def test_a_local_server_recommends_a_loaded_suggestion_else_its_first_chat_model():
    assert recommend_models("ollama", ["nomic-embed-text:latest", "llama3.2:3b"])["recommended"] == "llama3.2:3b"
    assert recommend_models("ollama", ["llama3.2:3b", "qwen2.5-coder:7b"])["recommended"] == "qwen2.5-coder:7b"
    assert recommend_models("lmstudio", [])["recommended"] is None


def test_openrouter_and_unknown_presets_use_what_the_list_contains():
    assert recommend_models("openrouter", ["x/y", "openai/gpt-oss-120b"])["recommended"] == "openai/gpt-oss-120b"
    assert recommend_models("custom", ["a", "b"]) == {"recommended": None, "choices": []}


# ------------------------------------------------------------------------- live list, then fallback --

def test_listing_recommends_from_the_whole_list_and_strips_googles_models_prefix(monkeypatch):
    names = ["models/" + n for n in GEMINI_LIST] + [f"models/zz-filler-{i:03d}" for i in range(600)]   # past the 500 cap
    seen = []
    monkeypatch.setattr(providers, "_get_json", lambda url, **kw: (seen.append((url, kw)) or (200, {"object": "list", "data": [{"id": n} for n in names]})))
    result = providers.list_models(PRESET_BY_ID["gemini"]["base_url"], "synthetic-key", preset="gemini")
    assert seen[0][0].endswith("/v1beta/openai/models") and seen[0][1]["headers"] == {"Authorization": "Bearer synthetic-key"}
    assert result["ok"] and result["recommended"] == "gemini-3.8-flash" and "models/gemini-3.8-flash" not in result["models"]
    assert len(result["models"]) == 500 and result["count"] == len(GEMINI_LIST) + 600
    assert "synthetic-key" not in str(result)


def test_when_the_list_cannot_be_read_there_is_no_recommendation_and_the_fallback_name_stays(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_get_json", lambda url, **kw: (401, {"error": "refused"}))
    result = providers.list_models("https://generativelanguage.googleapis.com/v1beta/openai", "k", preset="gemini")
    assert result == {"ok": False, "status": 401, "models": []}
    monkeypatch.setattr(providers, "_get_json", lambda url, **kw: (0, None))
    assert providers.list_models("http://127.0.0.1:9/v1", preset="ollama")["ok"] is False
    # What the form falls back to: every tile that takes a key starts with a name in the box, and Google's is current.
    for preset in providers.PRESETS:
        if preset["kind"] == "openai" and preset["key"] == "required":
            assert preset["suggested"] and all(isinstance(n, str) and n for n in preset["suggested"]), preset["id"]
    assert PRESET_BY_ID["gemini"]["suggested"] == ["gemini-3.8-flash", "gemini-3.6-flash"]
    from runesmith.config import DEFAULT_CONFIG
    assert DEFAULT_CONFIG["examples"]["gemini_openai_endpoint"]["model"] == "gemini-3.8-flash"


def test_the_workspace_lists_with_the_instruments_preset_and_a_saved_key(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ws.save_instrument("g", {"kind": "openai", "preset": "gemini", "model": "gemini-2.5-flash",
                             "base_url": PRESET_BY_ID["gemini"]["base_url"]}, key_value="synthetic-saved-key")
    monkeypatch.setattr(providers, "_get_json", lambda url, **kw: (
        200, {"data": [{"id": "models/gemini-3.8-flash"}, {"id": "models/gemini-3.8-pro"}]}) if kw["headers"] == {"Authorization": "Bearer synthetic-saved-key"} else (401, None))
    result = ws.list_models(name="g")
    assert result["ok"] and result["recommended"] == "gemini-3.8-flash"
    assert ws.list_models(preset="gemini", key_value="synthetic-saved-key")["recommended"] == "gemini-3.8-flash"


# ------------------------------------------------------------------------------------ the hint parser --

def test_the_hint_parser_reads_googles_exact_answer_in_every_wrapping_it_arrives_in():
    wrapped = [GOOGLE_404,
               "http_404 " + json.dumps(GOOGLE_404),
               "http_404 " + json.dumps({"error": {"code": 404, "message": GOOGLE_404, "status": "NOT_FOUND"}}),
               "http_404 " + json.dumps(str([{"error": {"code": 404, "message": GOOGLE_404, "status": "NOT_FOUND"}}])),
               "The service does not know this model or address. Check the model's exact name in its model list. (http_404 "
               + json.dumps(str([{"error": {"code": 404, "message": GOOGLE_404}}])) + ")"]
    for text in wrapped:
        assert model_hint(text, "gemini-2.5-flash") == "gemini-3.8-flash", text
    assert model_hint(GOOGLE_404 + ".", "models/gemini-2.5-flash") == "gemini-3.8-flash"


def test_the_hint_parser_handles_other_providers_and_refuses_what_is_not_a_model():
    assert model_hint("The model `gpt-4-32k` has been deprecated. Use `gpt-5.1` instead.", "gpt-4-32k") == "gpt-5.1"
    assert model_hint("No endpoints found for foo/bar. Try openrouter/auto", "foo/bar") == "openrouter/auto"
    assert model_hint("model not found, did you mean 'gpt-5.1'?", "gpt-5") == "gpt-5.1"
    # OpenAI's "does not exist" and OpenRouter's "not a valid model" often name nothing: no button then.
    assert model_hint("The model `gpt-4-32k` does not exist or you do not have access to it.", "gpt-4-32k") is None
    assert model_hint("foo/bar is not a valid model ID", "foo/bar") is None
    # Only when the model is said to be gone; never the model already set, a web address or an API version.
    assert model_hint("rate limited; try again in 20s") is None
    assert model_hint("Use gemini-3.8-flash for everything", "x") is None
    assert model_hint(GOOGLE_404, "gemini-3.8-flash") is None
    assert model_hint("model not found; see https://platform.openai.com/docs/models and use https://x.com/a-b") is None
    assert model_hint("not found: use v1beta endpoint, or json_object mode") is None
    assert model_hint("", "x") is None and model_hint(None) is None


class GoogleRetired(StandIn):
    """Google's OpenAI-compatible endpoint for a new user: the old model is refused with a list-shaped 404."""

    def get(self, path):
        return 200, {"object": "list", "data": [{"id": "models/gemini-3.8-flash"}, {"id": "models/gemini-2.5-flash"}]}

    def post(self, path, body, headers):
        if body.get("model") != "gemini-3.8-flash":
            return 404, [{"error": {"code": 404, "message": GOOGLE_404, "status": "NOT_FOUND"}}]
        return 200, self.completion(body)


def test_a_failed_test_carries_the_providers_suggestion_and_a_good_test_does_not(tmp_path):
    with GoogleRetired() as server:
        spec = {"kind": "openai", "base_url": server.root + "/v1", "model": "gemini-2.5-flash"}
        failed = providers.test_instrument("g", spec, tmp_path)
        assert not failed["ok"] and failed["suggested_model"] == "gemini-3.8-flash"
        assert "gemini-3.8-flash" in failed["detail"]                     # the owner's own words, not truncated away
        assert len([r for r in server.requests if r[0] == "POST"]) == 1   # a refusal that no retry can change
        fixed = providers.test_instrument("g", dict(spec, model="gemini-3.8-flash"), tmp_path)
        assert fixed["ok"] and "suggested_model" not in fixed


def test_a_work_step_that_hits_a_retired_model_names_the_replacement_in_plain_words():
    from runesmith.app.planner import why_no_answer
    text = why_no_answer("http_404 " + json.dumps(GOOGLE_404))
    assert "gemini-3.8-flash" in text and "Thinking power" in text


# ----------------------------------------------------------------------------------- the one-click switch --

def saved_gemini(tmp_path):
    ws = Workspace(tmp_path)
    ws.save_instrument("g", {"kind": "openai", "preset": "gemini", "model": "gemini-2.5-flash", "label": "Google Gemini",
                             "base_url": PRESET_BY_ID["gemini"]["base_url"], "json_mode": "json_object",
                             "reasoning_effort": "low", "max_request_tokens": 12000},
                       key_value="synthetic-saved-key", roles=["repair", "plan"])
    return ws


def test_the_switch_changes_only_the_model_name_and_is_recorded(tmp_path):
    ws = saved_gemini(tmp_path)
    before = ws.config()
    events = []
    studio = SimpleNamespace(ws=ws, bus=SimpleNamespace(publish=lambda *a: events.append(a)))
    result = api_instrument_model(studio, {}, {"model": "gemini-3.8-flash", "expect": "gemini-2.5-flash"}, "g")
    assert result["model"] == "gemini-3.8-flash" and events == [("inference", {})]
    after = ws.config()
    assert after["instruments"]["g"] == {**before["instruments"]["g"], "model": "gemini-3.8-flash"}   # key, address, limits stay
    assert after["roles"] == before["roles"]
    assert "synthetic-saved-key" not in json.dumps(after) and ws.keys.supplier("g")() == "synthetic-saved-key"
    [switched] = list(ws.ledger.events("instrument.model_switched"))
    assert switched["data"] == {"name": "g", "from": "gemini-2.5-flash", "to": "gemini-3.8-flash", "reason": "provider_hint"}


def test_a_stale_or_odd_switch_changes_nothing(tmp_path):
    ws = saved_gemini(tmp_path)
    ws.set_instrument_model("g", "gemini-3.6-flash")                          # the owner changed it meanwhile
    snapshot = ws.config()
    with pytest.raises(WorkspaceError, match="look again"):
        ws.set_instrument_model("g", "gemini-3.8-flash", expect="gemini-2.5-flash")
    for bad in ("", "has space", "x" * 301, "-leading", "a;b"):
        with pytest.raises(WorkspaceError):
            ws.set_instrument_model("g", bad)
    with pytest.raises(KeyError):
        ws.set_instrument_model("nobody", "gemini-3.8-flash")
    ws.save_instrument("gate", {"kind": "milliner", "model": "gemini:x", "base_url": "http://127.0.0.1:8765"}, key_value="synthetic-token")
    with pytest.raises(WorkspaceError, match="OpenAI-style"):
        ws.set_instrument_model("gate", "gemini:y")
    assert ws.config()["instruments"]["g"] == snapshot["instruments"]["g"]


# ------------------------------------------------------------------------------------- the form's wiring --

def test_the_form_prefills_checks_on_the_key_and_offers_the_hint_as_a_button_that_survives_a_redraw():
    assert "checked when you add your key" in UI and "value: extra.model || fallbackName" in UI     # a value, not a placeholder
    assert "r.recommended" in UI and "r.choices" in UI and "button.chip" in UI
    assert "key.addEventListener('paste'" in UI and "key.addEventListener('change'" in UI          # not on every keystroke
    assert "!touched" in UI                                                                         # an owner's own name is kept
    assert "was only a suggestion" in UI                                                            # a replacement on Save is said
    assert "const lastTest = new Map()" in UI and "testStatus(i, reload)" in UI                     # the hint outlives load()
    assert "/model`, { model: t.hint, expect: i.model }" in UI and "suggests ${t.hint}" in UI
