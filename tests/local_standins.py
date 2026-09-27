"""Faithful local stand-ins for model servers we cannot run here (Ollama, LM Studio, llama.cpp, Groq's free tier).

Each answers the way its official documentation says, including the unhappy paths: a model that is not downloaded, a
context window that is too small, a structured-output mode it rejects, a request too large for a free per-minute
window. Sources and dates: docs/journeys/local_servers_research_2026-09-27.json. These are docs-conformant stand-ins,
not the real servers; the coverage file records that evidence level.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

CHARS_PER_TOKEN = 4          # the stand-ins' own token estimate (servers count real tokens)


def tokens(messages) -> int:
    return sum(len(m.get("content") or "") for m in messages) // CHARS_PER_TOKEN + 1


class StandIn:
    """A small HTTP server in a thread; ``requests`` records every (method, path, body) it received."""

    def __init__(self):
        self.requests: list[tuple[str, str, Any]] = []
        self.answer: Any = {"ok": True}              # the JSON a model 'writes' when it answers
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, payload):
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                stand_in.requests.append(("GET", self.path, None))
                self._reply(*stand_in.get(self.path))

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"null")
                stand_in.requests.append(("POST", self.path, body))
                self._reply(*stand_in.post(self.path, body, dict(self.headers)))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    @property
    def root(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def get(self, path):
        return 404, {"error": "not found"}

    def post(self, path, body, headers):
        return 404, {"error": "not found"}

    def completion(self, body, *, finish="stop"):
        return {"id": "chatcmpl-standin", "object": "chat.completion", "model": body.get("model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(self.answer)},
                             "finish_reason": finish}],
                "usage": {"prompt_tokens": tokens(body.get("messages", [])), "completion_tokens": 20}}


class Ollama(StandIn):
    """Ollama: native /api/chat and /api/tags, plus the OpenAI-compatible /v1 surface.

    - A model that was never pulled: 404 {"error": "model 'x' not found, try pulling it first"}.
    - The context window defaults to 4,096 tokens. /api/chat honours options.num_ctx; /v1 cannot set it. On overflow
      the real server answers 200 while dropping the front of the prompt, where the instructions are, and
      ``prompt_eval_count`` shows how much it actually read.
    """

    def __init__(self, pulled=("qwen2.5-coder:7b",), default_ctx=4096):
        super().__init__()
        self.pulled, self.default_ctx = list(pulled), default_ctx

    def get(self, path):
        if path == "/api/tags":
            return 200, {"models": [{"name": m, "model": m} for m in self.pulled]}
        if path == "/v1/models":
            return 200, {"object": "list", "data": [{"id": m, "object": "model"} for m in self.pulled]}
        return 404, {"error": "not found"}

    def post(self, path, body, headers):
        if body.get("model") not in self.pulled:
            return 404, {"error": f"model '{body.get('model')}' not found, try pulling it first"}
        if path == "/api/chat":
            window = int((body.get("options") or {}).get("num_ctx") or self.default_ctx)
            wanted = tokens(body["messages"])
            read = min(wanted, window - int((body.get("options") or {}).get("num_predict") or 0))
            content = json.dumps(self.answer) if read >= wanted else "I am not sure what you want."
            return 200, {"model": body["model"], "message": {"role": "assistant", "content": content},
                         "done": True, "done_reason": "stop", "prompt_eval_count": max(read, 1), "eval_count": 20}
        if path == "/v1/chat/completions":
            wanted = tokens(body["messages"])
            if wanted > self.default_ctx:               # silent front truncation: the instructions are gone
                reply = self.completion(body)
                reply["choices"][0]["message"]["content"] = "I am not sure what you want."
                reply["usage"]["prompt_tokens"] = self.default_ctx
                return 200, reply
            return 200, self.completion(body)
        return 404, {"error": "not found"}


class LMStudio(StandIn):
    """LM Studio's local server: rejects response_format json_object (400); fixed context per loaded model."""

    def __init__(self, loaded=("qwen2.5-7b-instruct",), context=8000):
        super().__init__()
        self.loaded, self.context = list(loaded), context

    def get(self, path):
        if path == "/v1/models":
            return 200, {"object": "list", "data": [{"id": m, "object": "model"} for m in self.loaded]}
        return 404, {"error": "not found"}

    def post(self, path, body, headers):
        if path != "/v1/chat/completions":
            return 404, {"error": "not found"}
        if body.get("model") not in self.loaded:
            return 404, {"error": {"message": f"Model '{body.get('model')}' not found", "type": "invalid_request_error"}}
        if (body.get("response_format") or {}).get("type") == "json_object":
            return 400, {"error": "'response_format.type' must be 'json_schema' or 'text'"}
        wanted = tokens(body["messages"]) + int(body.get("max_tokens") or 0)
        if wanted > self.context:
            return 400, {"error": f"Trying to keep the first {wanted} tokens when context the overflows. However, the "
                                  f"model is loaded with context length of only {self.context} tokens, which is not "
                                  "enough. Try to load the model with a larger context length, or provide a shorter input"}
        return 200, self.completion(body)


class LlamaCpp(StandIn):
    """llama.cpp llama-server: 503 while loading; 400 exceed_context_size_error on overflow."""

    def __init__(self, ctx=4096, loading_requests=0):
        super().__init__()
        self.ctx, self.loading = ctx, loading_requests

    def get(self, path):
        if path == "/v1/models":
            return 200, {"object": "list", "data": [{"id": "model.gguf", "object": "model"}]}
        if path == "/health":
            return (503, {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}) if self.loading \
                else (200, {"status": "ok"})
        return 404, {"error": "not found"}

    def post(self, path, body, headers):
        if path != "/v1/chat/completions":
            return 404, {"error": "not found"}
        if self.loading:
            self.loading -= 1
            return 503, {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
        wanted = tokens(body["messages"])
        if wanted > self.ctx:
            return 400, {"error": {"code": 400, "message": "the request exceeds the available context size, try increasing it",
                                   "type": "exceed_context_size_error"}, "n_prompt_tokens": wanted, "n_ctx": self.ctx}
        return 200, self.completion(body)


class GroqFree(StandIn):
    """Groq's free tier at /openai/v1: 413 when prompt + max_tokens exceed the tokens-per-minute window; 429 for rate."""

    def __init__(self, tpm=8000, rate_limited=0):
        super().__init__()
        self.tpm, self.rate_limited = tpm, rate_limited

    def get(self, path):
        if path == "/openai/v1/models":
            return 200, {"object": "list", "data": [{"id": "openai/gpt-oss-120b", "object": "model"}]}
        return 404, {"error": "not found"}

    def post(self, path, body, headers):
        if path != "/openai/v1/chat/completions":
            return 404, {"error": "not found"}
        requested = tokens(body["messages"]) + int(body.get("max_completion_tokens") or body.get("max_tokens") or 0)
        if requested > self.tpm:
            return 413, {"error": {"message": f"Request too large for model `{body.get('model')}` in organization `org_x` "
                                              f"service tier `on_demand` on tokens per minute (TPM): Limit {self.tpm}, "
                                              f"Requested {requested}, please reduce your message size and try again.",
                                   "type": "tokens", "code": "rate_limit_exceeded"}}
        if self.rate_limited:
            self.rate_limited -= 1
            return 429, {"error": {"message": "Rate limit reached for model on requests per minute (RPM): Limit 30, "
                                              "Used 30, Requested 1. Please try again in 2s.",
                                   "type": "requests", "code": "rate_limit_exceeded"}}
        return 200, self.completion(body)


class OverflowWordings(StandIn):
    """One endpoint answering with the context-overflow wording of vLLM or LocalAI (chosen per instance)."""

    WORDINGS = {
        "vllm": (400, {"object": "error", "message": "This model's maximum context length is 4096 tokens. However, you "
                                                     "requested 9000 tokens (6000 in the messages, 3000 in the completion). "
                                                     "Please reduce the length of the messages or completion.",
                       "type": "BadRequestError", "code": 400}),
        "localai": (500, {"error": {"code": 500, "message": "rpc error: code = Unknown desc = the request (9000 tokens) "
                                                            "exceeds the context size (4096 tokens)", "type": ""}}),
    }

    def __init__(self, family):
        super().__init__()
        self.family = family

    def post(self, path, body, headers):
        return self.WORDINGS[self.family]
