"""Local model servers and free gateways, against docs-conformant stand-ins (LS1; coverage plan section 7).

The research behind each behaviour, with sources: docs/journeys/local_servers_research_2026-09-27.json. These tests
prove conformance to the documented behaviour, not to a live server; the coverage file records that level.
"""
import pytest

from local_standins import GroqFree, LlamaCpp, LMStudio, Ollama, OverflowWordings
from runesmith.app.providers import PRESET_BY_ID
from runesmith.config import build_instrument
from runesmith.instruments import OllamaInstrument, OpenAICompatInstrument, Router

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
BIG = "word " * 9000          # about 11,000 tokens by the stand-ins' count: more than a default local window


def call(instrument, prompt="Say ok.", max_tokens=500, schema=SCHEMA):
    return instrument.complete(prompt=prompt, system="Reply with JSON.", schema=schema, max_tokens=max_tokens, key="k")


def ollama(server, model="qwen2.5-coder:7b", **extra):
    preset = PRESET_BY_ID["ollama"]
    return build_instrument("local", dict({"kind": preset["kind"], "preset": "ollama", "base_url": server.root + "/v1",
                                           "model": model}, **extra))


def routed(instrument, backoff_s=(0, 0)):
    return Router({"m": instrument}, {"plan": ["m"]}, backoff_s=backoff_s, sleep=lambda _: None)


def test_ollama_is_asked_for_a_context_window_large_enough_for_each_request():
    with Ollama() as server:
        instrument = ollama(server)
        assert isinstance(instrument, OllamaInstrument)          # the /v1 address is upgraded to the native API
        outcome = call(instrument, prompt=BIG, max_tokens=3000)
        assert outcome.ok and outcome.data == {"ok": True}, outcome.error
        method, path, body = server.requests[-1]
        assert path == "/api/chat" and body["stream"] is False and body["format"] == SCHEMA
        assert body["options"]["num_ctx"] >= len(BIG) // 4 + 3000 and body["options"]["num_predict"] == 3000


def test_why_the_openai_style_address_is_not_used_for_ollama():
    # The documented hazard: /v1 cannot raise the 4,096-token default, and an overflowing prompt loses its front
    # (the instructions) without any error. Runesmith would read a confused answer as if it were real.
    with Ollama() as server:
        direct = OpenAICompatInstrument("v1", "qwen2.5-coder:7b", base_url=server.root + "/v1", tolerant_json=False)
        assert not call(direct, prompt=BIG).ok


def test_a_model_that_is_not_downloaded_fails_at_once_and_says_how_to_get_it():
    with Ollama(pulled=["qwen2.5-coder:7b"]) as server:
        outcome = routed(ollama(server, model="llama3.2:3b")).call("plan", prompt="p", system="s", schema=SCHEMA,
                                                                    max_tokens=100, key="k")
        assert not outcome.ok and outcome.error_kind == "config"
        assert "ollama pull llama3.2:3b" in outcome.error and len(server.requests) == 1   # no retries


def test_ollama_not_running_is_said_plainly():
    with Ollama() as server:
        address = server.root
    instrument = build_instrument("local", {"kind": "openai", "preset": "ollama", "base_url": address + "/v1",
                                            "model": "qwen2.5-coder:7b"})
    outcome = call(instrument)
    assert not outcome.ok and outcome.error_kind == "transport" and "Ollama is not running" in outcome.error


def test_a_request_too_big_for_the_allowed_window_is_refused_before_sending():
    with Ollama() as server:
        outcome = call(ollama(server, max_context=8192), prompt=BIG, max_tokens=3000)
        assert not outcome.ok and outcome.error_kind == "config" and "about" in outcome.error and not server.requests


def test_a_server_that_reads_less_than_it_was_sent_is_caught():
    class OldOllama(Ollama):                          # a build that ignores num_ctx and clips the prompt
        def post(self, path, body, headers):
            body = dict(body, options={})
            return super().post(path, body, headers)
    with OldOllama() as server:
        outcome = call(ollama(server), prompt=BIG, max_tokens=500)
        assert not outcome.ok and outcome.error_kind == "config" and "read only" in outcome.error


def test_lm_studio_gets_the_json_mode_it_accepts_and_others_fall_back_once():
    with LMStudio() as server:
        preset = PRESET_BY_ID["lmstudio"]
        good = build_instrument("lm", {"kind": "openai", "preset": "lmstudio", "base_url": server.root + "/v1",
                                       "model": "qwen2.5-7b-instruct", "json_mode": preset["json_mode"]})
        assert call(good).ok and server.requests[-1][2]["response_format"]["type"] == "json_schema"
        server.requests.clear()
        custom = build_instrument("any", {"kind": "openai", "base_url": server.root + "/v1",
                                          "model": "qwen2.5-7b-instruct", "json_mode": "json_object"})
        outcome = call(custom)
        assert outcome.ok and outcome.receipt.get("json_mode_fallback") == "none"
        assert [r[2].get("response_format") for r in server.requests] == [{"type": "json_object"}, None]


@pytest.mark.parametrize("server_class,args", [(LMStudio, {}), (LlamaCpp, {}), (OverflowWordings, {"family": "vllm"}),
                                                (OverflowWordings, {"family": "localai"})])
def test_a_context_overflow_fails_at_once_in_plain_words(server_class, args):
    with server_class(**args) as server:
        model = "qwen2.5-7b-instruct" if server_class is LMStudio else "model.gguf"
        instrument = build_instrument("x", {"kind": "openai", "base_url": server.root + "/v1", "model": model,
                                            "json_mode": "json_schema"})
        outcome = routed(instrument).call("plan", prompt=BIG, system="s", schema=SCHEMA, max_tokens=3000, key="k")
        assert not outcome.ok and outcome.error_kind == "config" and "context" in outcome.error.lower()
        assert len([r for r in server.requests if r[0] == "POST"]) == 1


def test_a_loading_llama_cpp_server_is_retried_like_any_busy_service():
    with LlamaCpp(loading_requests=1) as server:
        instrument = build_instrument("x", {"kind": "openai", "base_url": server.root + "/v1", "model": "model.gguf"})
        outcome = routed(instrument).call("plan", prompt="p", system="s", schema=SCHEMA, max_tokens=100, key="k")
        assert outcome.ok and len(server.requests) == 2


def test_groq_free_windows_are_respected_before_and_after_sending():
    with GroqFree(tpm=8000, rate_limited=1) as server:
        preset = PRESET_BY_ID["groq"]
        spec = {"kind": "openai", "preset": "groq", "base_url": server.root + "/openai/v1", "model": "openai/gpt-oss-120b",
                "max_request_tokens": preset["max_request_tokens"]}
        refused = call(build_instrument("g", spec), prompt=BIG, max_tokens=3000)
        assert not refused.ok and refused.error_kind == "config" and "8000" in refused.error and not server.requests
        unchecked = build_instrument("g", dict(spec, max_request_tokens=None))
        too_large = routed(unchecked).call("plan", prompt=BIG, system="s", schema=SCHEMA, max_tokens=3000, key="k")
        assert not too_large.ok and too_large.error_kind == "config" and len(server.requests) == 1
        server.requests.clear()
        busy_then_fine = routed(unchecked).call("plan", prompt="p", system="s", schema=SCHEMA, max_tokens=100, key="k2")
        assert busy_then_fine.ok and len(server.requests) == 2          # a 429 is waited out, a 413 is not


def test_presets_follow_the_research():
    assert "llama-3.3-70b-versatile" not in PRESET_BY_ID["groq"]["suggested"]          # shut down 2026-08-16
    assert PRESET_BY_ID["lmstudio"]["json_mode"] == "json_schema"                       # json_object is refused
    assert PRESET_BY_ID["groq"]["max_request_tokens"] == 8000
    for local in ("lmstudio", "llamacpp"):
        assert "context" in PRESET_BY_ID[local]["setup"].lower()
