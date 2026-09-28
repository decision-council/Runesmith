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
