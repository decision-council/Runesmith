"""F12 (out-of-box journey R1, 2026-09-27): a refusal before admission moves on to the role's next instrument.

With retries off (``backoff_s=()``, every Studio call), the router used to try only the first instrument, so one
provider at capacity stopped the work although the role declared another. A refusal at submission never became a
job: nothing ran and nothing was charged, so moving on cannot pay twice. An admitted call never falls through.
"""
import pytest

from runesmith.instruments import MillinerInstrument, Router, TransportCensored

ANSWER = {'title': 'Plan', 'files': []}


def at_capacity(calls):
    def gateway(method, url, headers, body, timeout):
        calls.append(method)
        return 429, {'error': 'rate_limited', 'message': 'nvidia capacity reached; no alternative route available'}
    return gateway


def answering(calls):
    def gateway(method, url, headers, body, timeout):
        calls.append(method)
        if method == 'POST':
            return 202, {'job_id': 'mj_ok', 'state': 'queued', 'agent': 'test'}
        return 200, {'job_id': 'mj_ok', 'agent': 'test', 'state': 'succeeded', 'parsed': ANSWER,
                     'meta': {'model': 'worker', 'provider': 'free'}}
    return gateway


def admitted_then_silent(calls):
    def gateway(method, url, headers, body, timeout):
        calls.append(method)
        if method == 'POST':
            return 202, {'job_id': 'mj_slow', 'state': 'queued', 'agent': 'test'}
        raise TimeoutError('still running')
    return gateway


def milliner(tmp_path, name, transport):
    return MillinerInstrument(name, 'free:' + name, base_url='http://localhost:8765', token=lambda: 'unused',
                              caller_tag='test', timeout_s=2, request_dir=tmp_path / name, transport=transport)


def router(tmp_path, first, second, events):
    return Router({'a': milliner(tmp_path, 'a', first), 'b': milliner(tmp_path, 'b', second)},
                  {'plan': ['a', 'b']}, backoff_s=(), on_call=events.append)


def call(r):
    return r.call('plan', prompt='p', system='s', schema=None, max_tokens=10, key='k')


def test_a_refusal_before_admission_moves_on_to_the_next_instrument(tmp_path):
    a, b, events = [], [], []
    outcome = call(router(tmp_path, at_capacity(a), answering(b), events))
    assert outcome.ok and outcome.data == ANSWER
    assert a == ['POST'] and b.count('POST') == 1
    assert [e['instrument'] for e in events] == ['a', 'b'] and not events[0]['ok']


def test_every_instrument_refusing_ends_after_one_try_each(tmp_path):
    a, b, events = [], [], []
    with pytest.raises(TransportCensored, match='capacity reached'):
        call(router(tmp_path, at_capacity(a), at_capacity(b), events))
    assert a == ['POST'] and b == ['POST'] and len(events) == 2


def test_an_admitted_call_never_falls_through(tmp_path):
    a, b, events = [], [], []
    with pytest.raises(TransportCensored) as failure:
        call(router(tmp_path, admitted_then_silent(a), answering(b), events))
    assert failure.value.receipt['unresolved'] and a[0] == 'POST' and b == []



def every_route_refused(calls, spent=0):
    """Admitted, then turned away by every route before generating: Milliner's attempts say so (journey J11-F2)."""
    def gateway(method, url, headers, body, timeout):
        calls.append(method)
        if method == 'POST':
            return 202, {'job_id': 'mj_refused', 'state': 'queued', 'agent': 'test'}
        return 200, {'job_id': 'mj_refused', 'agent': 'test', 'state': 'failed',
                     'error': 'every route failed - gemini:flash rate_limited; gemini2:flash overloaded',
                     'meta': {'attempts': [{'provider': 'gemini', 'outcome': 'rate_limited', 'tokens_in': 0, 'tokens_out': 0},
                                           {'provider': 'gemini2', 'outcome': 'overloaded', 'tokens_in': 0,
                                            'tokens_out': spent}]}}
    return gateway


def test_a_job_every_route_refused_moves_on_to_the_next_instrument(tmp_path):
    # Journey J11-F2: the Checker's Gemini Flash was rate-limited on every route; Flash Lite, its second model, was
    # never asked. Nothing ran and nothing was charged, as with a refusal at submission.
    a, b, events = [], [], []
    outcome = call(router(tmp_path, every_route_refused(a), answering(b), events))
    assert outcome.ok and outcome.data == ANSWER and [e['instrument'] for e in events] == ['a', 'b']
    c, d, events = [], [], []
    with pytest.raises(TransportCensored):                  # one route generated: saved for review, never paid twice
        call(router(tmp_path / 'spent', every_route_refused(c, spent=40), answering(d), events))
    assert d == [] and [e['instrument'] for e in events] == ['a']


def too_large_everywhere(calls):
    """Journey J11-B7: Groq's 8,000 tokens a minute cannot hold a build prompt with its answer room; every Groq route
    refused it with bad_request in 0.0 s, before generating anything."""
    def gateway(method, url, headers, body, timeout):
        calls.append(method)
        if method == 'POST':
            return 202, {'job_id': 'mj_large', 'state': 'queued', 'agent': 'test'}
        return 200, {'job_id': 'mj_large', 'agent': 'test', 'state': 'failed',
                     'error': 'every route failed - groq3:gpt-oss-120b bad_request; groq:gpt-oss-120b bad_request',
                     'meta': {'attempts': [{'provider': 'groq3', 'outcome': 'bad_request', 'tokens_in': 0, 'tokens_out': 0},
                                           {'provider': 'groq', 'outcome': 'bad_request', 'tokens_in': 0, 'tokens_out': 0}]}}
    return gateway


def test_a_request_no_route_could_take_moves_on_to_the_next_instrument(tmp_path):
    a, b, events = [], [], []
    outcome = call(router(tmp_path, too_large_everywhere(a), answering(b), events))
    assert outcome.ok and outcome.data == ANSWER and [e['instrument'] for e in events] == ['a', 'b']


def test_a_request_every_model_turned_away_is_no_answer_even_when_it_reads_like_an_output_failure(tmp_path):
    # Review of J11-B7: "bad_request" is classified like an output failure, so when the last model refused it too the
    # router returned an output failure and the caller used up a try, although nothing ran.
    a, b, events = [], [], []
    with pytest.raises(TransportCensored) as caught:
        call(router(tmp_path, too_large_everywhere(a), too_large_everywhere(b), events))
    assert caught.value.receipt.get('no_route_accepted') and [e['instrument'] for e in events] == ['a', 'b']


def test_a_model_s_own_reasoning_effort_is_sent_when_the_call_names_none(tmp_path):
    # Journey J11-B8: Nemotron's answers looped in hidden reasoning to the token cap and were truncated; each used a try.
    import json as _json
    from runesmith.config import build_router
    bodies = []

    def effort(body):
        if isinstance(body, (bytes, bytearray)):
            body = body.decode()
        if isinstance(body, str):
            try:
                body = _json.loads(body)
            except ValueError:
                return None
        return body.get('reasoning_effort') if isinstance(body, dict) else None

    def gateway(method, url, headers, body, timeout):
        bodies.append(body)
        if method == 'POST':
            return 202, {'job_id': 'mj_ok', 'state': 'queued', 'agent': 'test'}
        return 200, {'job_id': 'mj_ok', 'agent': 'test', 'state': 'succeeded', 'parsed': ANSWER,
                     'meta': {'model': 'worker', 'provider': 'free'}}
    spec = {'kind': 'scripted', 'answers': [ANSWER, ANSWER], 'reasoning_effort': 'low'}
    router = build_router({'instruments': {'s': spec}, 'roles': {'plan': ['s']}}, backoff_s=())
    assert router.instruments['s'].default_reasoning == 'low'
    inst = milliner(tmp_path, 'm', gateway)
    inst.default_reasoning = 'low'
    Router({'m': inst}, {'plan': ['m']}, backoff_s=()).call('plan', prompt='p', system='s', schema=None, max_tokens=10, key='k')
    assert 'low' in [effort(b) for b in bodies]
    bodies.clear()
    Router({'m': inst}, {'plan': ['m']}, backoff_s=()).call('plan', prompt='p', system='s', schema=None, max_tokens=10,
                                                           key='k2', reasoning_effort='high')
    assert 'high' in [effort(b) for b in bodies]      # the call's own wins
    nothing = build_router({'instruments': {'s': dict(spec, reasoning_effort='maximum')}, 'roles': {'plan': ['s']}}, backoff_s=())
    assert nothing.instruments['s'].default_reasoning is None                                       # unknown values ignored


def test_a_request_too_large_for_a_directly_called_model_moves_on_to_the_next_one():
    # Review of J11-G17: Groq called directly refused a request as too large for its 8,000 tokens a minute before
    # sending it, and the role's next model was never asked.
    from runesmith.instruments import OpenAICompatInstrument, ScriptedInstrument
    sent = []

    def transport(*args):
        sent.append(args)
        return 200, {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
    small = OpenAICompatInstrument("groq", "openai/gpt-oss-120b", base_url="http://groq.invalid/openai/v1",
                                   transport=transport, max_request_tokens=1000)
    events = []
    router = Router({"groq": small, "next": ScriptedInstrument("next", [ANSWER])}, {"plan": ["groq", "next"]},
                    backoff_s=(), on_call=events.append)
    outcome = router.call("plan", prompt="p" * 9000, system="s", schema=None, max_tokens=10, key="k")
    assert outcome.ok and outcome.data == ANSWER and not sent and [e["instrument"] for e in events] == ["groq", "next"]
    alone = Router({"groq": small}, {"plan": ["groq"]}, backoff_s=()).call("plan", prompt="p" * 9000, system="s",
                                                                          schema=None, max_tokens=10, key="k2")
    assert not alone.ok and alone.error_kind == "config" and alone.receipt["refused_before_answer"] == "too_large"


def test_a_model_that_refused_for_good_is_not_asked_again_and_its_refusal_is_named():
    # Review of batch E: with [bad key, flaky], every backoff tier asked the bad key again, and the final error named
    # only the flaky one's network failure.
    from runesmith.instruments import CallOutcome, ScriptedInstrument
    asked = []

    class BadKey(ScriptedInstrument):
        def complete(self, **kwargs):
            asked.append("bad")
            return CallOutcome(False, error_kind="config", receipt={"refused_before_answer": "refused"},
                               error="The service refused the key (401). Check it, or paste it again, under Thinking power.")

    class Flaky(ScriptedInstrument):
        def complete(self, **kwargs):
            asked.append("flaky")
            return CallOutcome(False, error_kind="transport", error="URLError: connection refused")
    router = Router({"bad": BadKey("bad", []), "flaky": Flaky("flaky", [])}, {"plan": ["bad", "flaky"]},
                    backoff_s=(0, 0, 0), sleep=lambda _: None)
    with pytest.raises(TransportCensored) as caught:
        router.call("plan", prompt="p", system="s", schema=None, max_tokens=10, key="k")
    assert asked.count("bad") == 1 and asked.count("flaky") == 4
    assert "refused the key" in str(caught.value)
    alone = Router({"bad": BadKey("bad", [])}, {"plan": ["bad"]}, backoff_s=(0, 0), sleep=lambda _: None)
    outcome = alone.call("plan", prompt="p", system="s", schema=None, max_tokens=10, key="k2")
    assert outcome.error_kind == "config" and "refused the key" in outcome.error
