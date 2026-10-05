"""A free key is paced (newcomer path, 2026-10-05): one Google AI Studio key made 38 calls in an hour and 36 failed.

Every retry spends from the key's small allowance. A "429" now stops the retrying at once and is remembered until the
service's reset; a "503" is asked once more after a longer wait; a free key gets one retry at most; and each says so in
plain words, with the time.
"""
import io
import json
from email.message import Message
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from runesmith import instruments
from runesmith.instruments import OpenAICompatInstrument, Router, TransportCensored
from runesmith.pacing import (BUSY_WAIT_S, Pacing, limit_hints, next_pacific_midnight, reset_time)

GEMINI = 'https://generativelanguage.googleapis.com/v1beta/openai'
NOW = 1_791_182_000.0                                  # 2026-10-05 06:33:20Z
GOOGLE_429 = [{'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED',
                         'message': 'You exceeded your current quota, please check your plan and billing details. '
                                    'For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits.'}}]
GOOGLE_429_DAILY = [{'error': dict(GOOGLE_429[0]['error'], details=[{'@type': 'type.googleapis.com/google.rpc.QuotaFailure',
                     'violations': [{'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}])}]
GOOGLE_429_MINUTE = [{'error': dict(GOOGLE_429[0]['error'], details=[{'@type': 'type.googleapis.com/google.rpc.RetryInfo',
                      'retryDelay': '34s'}])}]
GOOGLE_503 = [{'error': {'code': 503, 'status': 'UNAVAILABLE',
                         'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. '
                                    'Please try again later.'}}]
ANSWER = {'choices': [{'message': {'content': '{"ok": true}'}, 'finish_reason': 'stop'}]}


class Service:
    """A transport that answers from a list (an HTTP status and a body), and counts the requests it was asked."""

    def __init__(self, *answers):
        self.answers, self.requests = list(answers), 0

    def __call__(self, method, url, headers, body, timeout):
        self.requests += 1
        status, payload = self.answers.pop(0) if self.answers else self.answers_left()
        return status, payload

    def answers_left(self):
        raise AssertionError('the service was asked more often than the test allows')


def instrument(service, name='gemini', *, free=True, base=GEMINI):
    made = OpenAICompatInstrument(name, 'gemini-3.8-flash', base_url=base, api_key=lambda: 'k', transport=service)
    made.free_tier = free
    return made


def router(tmp_path, *instruments_, backoff=(5, 20, 60), sleeps=None, clock=lambda: NOW):
    return Router({i.name: i for i in instruments_}, {'plan': [i.name for i in instruments_]}, backoff_s=backoff,
                  sleep=(sleeps if sleeps is not None else []).append, pacing=Pacing(tmp_path / 'PACING.json', clock=clock),
                  clock=clock)


def ask(r):
    return r.call('plan', prompt='p', system='s', schema=None, max_tokens=50, key='k')


def google(status, body):
    return status, body[0]


# ------------------------------------------------------------------------------------------------ a 429 --

def test_a_429_stops_the_retrying_at_once_and_says_when_it_will_be_asked_again(tmp_path):
    service, sleeps = Service(google(429, GOOGLE_429_DAILY)), []
    with pytest.raises(TransportCensored) as error:
        ask(router(tmp_path, instrument(service), sleeps=sleeps))
    assert service.requests == 1 and sleeps == []              # four attempts and 3 waits before; now one request
    words = error.value.plain
    assert 'gemini' in words and 'free allowance' in words and 'will not ask it again before about' in words
    assert 'Add a second free provider' in words              # one provider only: the way out is named
    assert error.value.receipt['not_admitted'] and error.value.receipt['limited_until'] > NOW


def test_a_day_limit_the_service_names_is_held_until_its_midnight_on_the_pacific_coast():
    # 06:33Z on 5 October 2026: the quota came back at 07:00Z (the journey's own account).
    until, daily, guessed = reset_time(GEMINI, {}, 'http_429 ' + json.dumps(GOOGLE_429_DAILY[0]['error']),
                                       NOW)
    assert daily and not guessed and until == 1_791_183_600.0  # 2026-10-05 07:00:00Z
    from datetime import datetime, timezone
    assert datetime.fromtimestamp(next_pacific_midnight(datetime(2026, 12, 5, 6, 33, tzinfo=timezone.utc).timestamp()),
                                  timezone.utc).hour == 8      # standard time in winter: 08:00Z


def test_a_per_minute_limit_with_its_time_is_held_for_that_time_only():
    until, daily, guessed = reset_time(GEMINI, {}, 'http_429 ' + json.dumps(GOOGLE_429_MINUTE[0]['error']), NOW)
    assert (until, daily, guessed) == (NOW + 34, False, False)


def test_a_429_that_names_no_time_is_held_two_minutes_and_a_second_one_right_after_means_the_day_is_used_up(tmp_path):
    # Google's per-minute and per-day refusals both read "You exceeded your current quota": a first refusal without a
    # time must not lock a newcomer out for hours, and a second right after the guess ran out must not be asked again.
    service, now = Service(google(429, GOOGLE_429), google(429, GOOGLE_429), (200, ANSWER)), [NOW]

    def click():
        return router(tmp_path, instrument(service), clock=lambda: now[0])
    with pytest.raises(TransportCensored) as first:
        ask(click())
    assert first.value.receipt['limited_until'] == NOW + 120 and 'free limit for now' in first.value.plain
    now[0] = NOW + 30                                           # the next click inside the hold sends nothing
    with pytest.raises(TransportCensored):
        ask(click())
    assert service.requests == 1
    now[0] = NOW + 125                                          # the hold ran out: one request goes to see
    with pytest.raises(TransportCensored) as second:
        ask(click())
    assert service.requests == 2 and second.value.receipt['limited_until'] == 1_791_183_600.0    # 07:00Z, the day's end
    assert 'allowance for today' in second.value.plain
    now[0] = 1_791_183_000.0                                    # still the same day: nothing is sent
    with pytest.raises(TransportCensored):
        ask(click())
    assert service.requests == 2
    now[0] = 1_791_183_601.0                                    # past 07:00Z: asked again, and answered
    assert ask(click()).ok and service.requests == 3
    assert Pacing(tmp_path / 'PACING.json', clock=lambda: now[0]).recent('gemini') is None     # the answer cleared it


def test_a_guess_that_is_not_followed_by_a_second_refusal_is_forgotten(tmp_path):
    service, now = Service(google(429, GOOGLE_429), (200, ANSWER), google(429, GOOGLE_429)), [NOW]

    def click():
        return router(tmp_path, instrument(service), clock=lambda: now[0])
    with pytest.raises(TransportCensored):
        ask(click())
    now[0] = NOW + 125
    assert ask(click()).ok                                      # the per-minute limit had passed
    now[0] = NOW + 4000                                         # much later: a new first refusal, the short guess again
    with pytest.raises(TransportCensored) as again:
        ask(click())
    assert again.value.receipt['limited_until'] == NOW + 4000 + 120
    other = Service((429, {'error': {'message': 'Too many requests'}}), (429, {'error': {'message': 'Too many requests'}}))
    clock = [NOW]
    r = lambda: router(tmp_path / 'other', instrument(other, 'groq-ish', base='https://api.groq.com/openai/v1'), clock=lambda: clock[0])      # not Google
    with pytest.raises(TransportCensored):
        ask(r())
    clock[0] = NOW + 125
    with pytest.raises(TransportCensored) as escalated:
        ask(r())
    assert escalated.value.receipt['limited_until'] == NOW + 125 + 900                  # longer each time, never midnight


def test_the_next_click_does_not_ask_again_until_the_reset_and_then_does(tmp_path):
    service, now = Service(google(429, GOOGLE_429_DAILY), (200, ANSWER)), [NOW]
    first = router(tmp_path, instrument(service), clock=lambda: now[0])
    with pytest.raises(TransportCensored):
        ask(first)
    # A new router (the next click) over the same project folder asks nothing: no request is spent.
    again = router(tmp_path, instrument(service), clock=lambda: now[0])
    with pytest.raises(TransportCensored) as held:
        ask(again)
    assert service.requests == 1 and 'will not ask it again' in held.value.plain and held.value.receipt['not_admitted']
    now[0] = 1_791_183_601.0                                   # past 07:00Z
    assert ask(router(tmp_path, instrument(service), clock=lambda: now[0])).ok and service.requests == 2
    assert Pacing(tmp_path / 'PACING.json', clock=lambda: now[0]).active() == {}     # the answer cleared the mark


def test_the_retry_after_header_and_the_message_name_the_wait(tmp_path, monkeypatch):
    headers = Message()
    headers['Retry-After'] = '90'
    assert limit_hints(headers, '') == {'retry_after_s': 90.0, 'daily': False}
    assert limit_hints(None, 'Please retry in 34.5s.')['retry_after_s'] == 34.5
    assert limit_hints(None, '"retryDelay": "34s"')['retry_after_s'] == 34.0
    assert limit_hints(None, 'tokens per day (TPD): Limit 100000. Please try again in 7m12s.') == {'retry_after_s': 432.0, 'daily': True}
    assert limit_hints(None, 'nothing about time') is None

    # Through the real transport: Google's list-shaped body is read, and the header's wait is kept.
    def refuse(request, timeout=None):
        raise HTTPError(request.full_url, 429, 'Too Many Requests', headers, io.BytesIO(json.dumps(GOOGLE_429).encode()))
    monkeypatch.setattr(instruments, 'urlopen', refuse)
    status, payload = instruments.http_json('POST', GEMINI + '/chat/completions', {}, {}, 5)
    assert status == 429 and payload['error']['status'] == 'RESOURCE_EXHAUSTED' and payload['_pacing']['retry_after_s'] == 90.0
    out = OpenAICompatInstrument('g', 'm', base_url=GEMINI).complete(prompt='p', system='s', schema=None, max_tokens=20, key='k')
    assert out.receipt['http_status'] == 429 and out.receipt['retry_after_s'] == 90.0
    until, daily, guessed = reset_time(GEMINI, out.receipt, out.error, NOW)
    assert until == NOW + 90 and not daily and not guessed


def test_a_short_wait_the_service_names_is_waited_out_once_and_a_long_one_is_not(tmp_path):
    short = Service((429, {'error': {'message': 'Rate limit reached. Please try again in 2s.'}}), (200, ANSWER))
    sleeps = []
    assert ask(router(tmp_path, instrument(short), sleeps=sleeps)).ok and short.requests == 2 and sleeps == [3.0]
    long = Service((429, {'error': {'message': 'Rate limit reached. Please try again in 2m.'}}))
    with pytest.raises(TransportCensored):
        ask(router(tmp_path / 'other', instrument(long)))
    assert long.requests == 1


def test_a_second_provider_answers_while_the_first_is_held_back(tmp_path):
    first, second = Service(google(429, GOOGLE_429_DAILY)), Service((200, ANSWER), (200, ANSWER))
    r = router(tmp_path, instrument(first, 'gemini'), instrument(second, 'groq'))
    assert ask(r).ok and (first.requests, second.requests) == (1, 1)
    assert ask(r).ok and (first.requests, second.requests) == (1, 2)       # the first is not asked again before its reset


def test_when_every_provider_is_limited_both_are_named(tmp_path):
    a, b = Service(google(429, GOOGLE_429)), Service((429, {'error': {'message': 'quota per day exhausted'}}))
    with pytest.raises(TransportCensored) as error:
        ask(router(tmp_path, instrument(a, 'gemini'), instrument(b, 'groq')))
    assert 'gemini' in error.value.plain and 'groq' in error.value.plain and 'Add a second' not in error.value.plain


# ------------------------------------------------------------------------------------------------ a 503 --

def test_a_503_backs_off_longer_and_is_asked_once_more_only(tmp_path):
    service, sleeps = Service(google(503, GOOGLE_503), google(503, GOOGLE_503)), []
    with pytest.raises(TransportCensored) as error:
        ask(router(tmp_path, instrument(service), sleeps=sleeps))
    assert service.requests == 2 and sleeps == [BUSY_WAIT_S] and BUSY_WAIT_S > 20
    assert 'very busy' in error.value.plain and '{' not in error.value.plain and error.value.receipt['not_admitted']
    assert 'high demand' in str(error.value)                      # the service's own words stay in the details


def test_a_503_that_clears_on_the_second_try_answers(tmp_path):
    service, sleeps = Service(google(503, GOOGLE_503), (200, ANSWER)), []
    assert ask(router(tmp_path, instrument(service), sleeps=sleeps)).ok and sleeps == [BUSY_WAIT_S]


def test_a_503_with_retries_off_is_asked_once(tmp_path):
    service = Service(google(503, GOOGLE_503))
    with pytest.raises(TransportCensored):
        ask(router(tmp_path, instrument(service), backoff=()))
    assert service.requests == 1


def test_a_busy_first_provider_hands_the_request_to_the_second_without_waiting(tmp_path):
    first, second, sleeps = Service(google(503, GOOGLE_503)), Service((200, ANSWER)), []
    assert ask(router(tmp_path, instrument(first, 'gemini'), instrument(second, 'groq'), sleeps=sleeps)).ok
    assert sleeps == [] and (first.requests, second.requests) == (1, 1)


# ------------------------------------------------------------------------------ the fan-out of one click --

@pytest.mark.parametrize('free,asked', [(True, 2), (False, 4)])
def test_a_free_key_gets_one_retry_where_other_instruments_get_three(tmp_path, free, asked):
    def down(*args):
        down.requests += 1
        raise TimeoutError('timed out')
    down.requests = 0
    with pytest.raises(TransportCensored):
        ask(router(tmp_path, instrument(down, free=free)))
    assert down.requests == asked


def test_a_workspace_marks_a_google_key_as_free_and_calls_it_less(tmp_path, monkeypatch):
    from runesmith.app.workspace import Workspace
    ws = Workspace(tmp_path)
    ws.save_instrument('g', {'kind': 'openai', 'preset': 'gemini', 'model': 'gemini-3.8-flash', 'base_url': GEMINI,
                             'json_mode': 'json_object'}, key_value='synthetic-key', roles=['plan'])
    ws.save_instrument('paid', {'kind': 'openai', 'preset': 'openai', 'model': 'gpt-5-mini',
                                'base_url': 'https://api.openai.com/v1'}, key_value='synthetic-key-2', roles=['repair'])
    live = ws.router(backoff_s=(5, 20, 60)).instruments
    assert live['g'].free_tier is True and live['paid'].free_tier is False
    calls = []

    def refuse(request, timeout=None):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 429, 'Too Many Requests', Message(), io.BytesIO(json.dumps(GOOGLE_429_DAILY).encode()))
    monkeypatch.setattr(instruments, 'urlopen', refuse)
    from runesmith.app.planner import PlannerUnavailable, _call
    with pytest.raises(PlannerUnavailable) as failure:
        _call(ws, ws.router(backoff_s=(5, 20, 60)), 'p', 's', {'type': 'object'}, 'k', 100)
    assert len(calls) == 1                                       # was four requests (and three waits) for one click
    from runesmith.app.planner import nothing_ran
    assert nothing_ran(failure.value)                            # nothing ran: no try of the milestone is used up
    assert 'free allowance' in str(failure.value) and '{' not in str(failure.value)
    assert (tmp_path / '.runesmith' / 'PACING.json').is_file()
    assert 'will not ask it again' in str(failure.value) and 'Add a second free provider' in str(failure.value)
    before = len(calls)
    with pytest.raises(PlannerUnavailable):
        _call(ws, ws.router(backoff_s=(5, 20, 60)), 'p', 's', {'type': 'object'}, 'k', 100)
    assert len(calls) == before                                  # the next click is not sent at all


# ------------------------------------------------------------------------------------------ the words --

@pytest.mark.parametrize('raw', ['http_503 ' + json.dumps(GOOGLE_503[0]['error']),
                                 "role 'plan': no response after 4 attempts; last: http_503 " + json.dumps(GOOGLE_503[0]['error']),
                                 'http_502 ' + json.dumps({'error': 'bad gateway'}),
                                 'http_429 ' + json.dumps(GOOGLE_429[0]['error'])])
def test_a_busy_service_gets_the_same_friendly_line_and_no_json_on_screen(raw):
    from runesmith.app.planner import why_no_answer
    text = why_no_answer(RuntimeError(raw))
    assert 'busy or at its free limit' in text and '{' not in text and '"' not in text


def test_a_failed_job_keeps_the_service_words_for_its_details(tmp_path):
    from runesmith.app.planner import PlannerUnavailable, error_detail
    cause = TransportCensored("role 'plan': no response; last: http_503 " + json.dumps(GOOGLE_503[0]['error']))
    failure = PlannerUnavailable('the model is busy')
    failure.__cause__ = cause
    assert 'high demand' in error_detail(failure)


# ------------------------------------------------------------------ the Overview, the model row, the Test --

def saved(tmp_path, *names):
    from runesmith.app.workspace import Workspace
    ws = Workspace(tmp_path)
    presets = {'g': ('gemini', 'gemini-3.8-flash', GEMINI), 'n': ('nvidia', 'nvidia/nemotron-3-super-120b-a12b',
                                                                  'https://integrate.api.nvidia.com/v1')}
    for name in names:
        preset, model, address = presets[name]
        ws.save_instrument(name, {'kind': 'openai', 'preset': preset, 'model': model, 'base_url': address,
                                  'label': preset.capitalize()}, key_value='synthetic-key-' + name, roles=['plan', 'repair'])
    return ws


def hold(ws, name, seconds=3000):
    import time
    return Pacing(ws.home / 'PACING.json').mark(name, time.time() + seconds, daily=True)


def test_with_one_provider_at_its_limit_the_overview_suggests_a_second_free_one(tmp_path):
    from runesmith.app.server import api_state
    ws = saved(tmp_path, 'g')
    studio = SimpleNamespace(ws=ws, worker=SimpleNamespace(snapshot=lambda: {}), bus=SimpleNamespace(recent=[]))
    from runesmith.app import guide
    assert api_state(studio, {}, None)['pacing'] == {'limited': [], 'only_provider_limited': False, 'guide_url': '',
                                                     'guide_words': guide.FREE_INFERENCE_WORDS}
    hold(ws, 'g')
    pacing = api_state(studio, {}, None)['pacing']
    assert pacing['only_provider_limited'] and len(pacing['limited']) == 1
    assert 'Gemini' in pacing['limited'][0]['words'] and 'free allowance' in pacing['limited'][0]['words']
    # With a second provider there is something to go on with: no suggestion.
    other = saved(tmp_path, 'g', 'n')
    assert api_state(SimpleNamespace(ws=other, worker=studio.worker, bus=studio.bus), {}, None)['pacing']['only_provider_limited'] is False


def test_the_overview_card_and_its_guide_link_are_in_the_page():
    from pathlib import Path
    home = (Path(__file__).resolve().parent.parent / 'runesmith/app/static/js/views/home.js').read_text(encoding='utf-8')
    assert 'pacingCard(s, navigate)' in home and 'Add a second free provider' in home and 'p.guide_url' in home
    assert 'p.guide_words' in home                                  # the chapter is named in words, linked or not
    from runesmith.app import guide
    assert guide.free_inference_url() == ''                          # no address yet: the chapter is named, not linked
    guide.GUIDE_URL = 'https://example.org/guide/'
    try:
        assert guide.free_inference_url() == 'https://example.org/guide' + guide.FREE_INFERENCE_CHAPTER
        assert guide.FREE_INFERENCE_CHAPTER == '#chapter-4-thinking-power-where-to-get-a-model-for-free-and-how-to-connect-it'
    finally:
        guide.GUIDE_URL = ''


def test_a_test_does_not_ask_a_held_back_provider_and_a_new_key_lifts_the_hold(tmp_path, monkeypatch):
    ws = saved(tmp_path, 'g')
    hold(ws, 'g')
    asked = []
    monkeypatch.setattr(instruments, 'urlopen', lambda *a, **k: asked.append(a) or (_ for _ in ()).throw(AssertionError('asked')))
    result = ws.test_instrument('g')
    assert not result['ok'] and result.get('limited') and 'Nothing was sent' in result['detail'] and not asked
    assert [r['name'] for r in ws.inference()['pacing']['limited']] == ['g']
    ws.save_instrument('g', ws.config()['instruments']['g'], key_value='a-new-synthetic-key')
    assert ws.inference()['pacing']['limited'] == []


def test_a_test_that_hits_the_limit_says_so_in_words_and_marks_it(tmp_path, monkeypatch):
    ws = saved(tmp_path, 'g')

    def refuse(request, timeout=None):
        raise HTTPError(request.full_url, 429, 'Too Many Requests', Message(), io.BytesIO(json.dumps(GOOGLE_429_DAILY).encode()))
    monkeypatch.setattr(instruments, 'urlopen', refuse)
    result = ws.test_instrument('g')
    assert not result['ok'] and 'free allowance' in result['detail'] and '{' not in result['detail']
    assert [r['name'] for r in ws.inference()['pacing']['limited']] == ['g']


def test_list_models_without_a_key_says_to_add_the_key_first(tmp_path, monkeypatch):
    from runesmith.app.workspace import Workspace
    monkeypatch.setattr(instruments, 'urlopen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('asked')))
    result = Workspace(tmp_path).list_models(preset='gemini', base_url=GEMINI, key_value='')
    assert not result['ok'] and result['needs_key'] and 'Add your key first' in result['detail']
    assert 'not running' not in result['detail']


def test_the_model_row_shows_a_test_only_as_old_as_it_is_and_a_failure_replaces_it():
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / 'runesmith/app/static/js/views/inference.js').read_text(encoding='utf-8')
    assert 'at: Date.now()' in source and "t.ok ? `✓ tested ${when}" in source and 'The test could not run' in source
    assert 'r.needs_key ? r.detail' in source


def test_a_test_that_meets_a_busy_service_says_so_plainly_and_keeps_the_service_words_apart(tmp_path, monkeypatch):
    ws = saved(tmp_path, 'g')

    def busy(request, timeout=None):
        raise HTTPError(request.full_url, 503, 'Service Unavailable', Message(), io.BytesIO(json.dumps(GOOGLE_503).encode()))
    monkeypatch.setattr(instruments, 'urlopen', busy)
    result = ws.test_instrument('g')
    assert not result['ok'] and 'busy or at its free limit' in result['detail']
    assert '{' not in result['detail'] and '"' not in result['detail']
    assert 'high demand' in result['raw']
    assert ws.inference()['pacing']['limited'] == []              # a 503 holds nothing back: only a 429 does


@pytest.mark.parametrize('event,words', [({'http_status': 429, 'error_kind': 'transport'}, 'is at its free limit'),
                                         ({'http_status': 503, 'error_kind': 'transport'}, 'is busy'),
                                         ({'error_kind': 'transport'}, 'did not answer'),
                                         ({'error_kind': 'config'}, 'refused the request'),
                                         ({'error_kind': 'output'}, 'could not be used')])
def test_the_live_log_says_what_happened_not_failed_transport(tmp_path, event, words):
    from runesmith.app.worker import EventBus, Worker
    from runesmith.app.workspace import Workspace
    worker = Worker(Workspace(tmp_path), EventBus())
    worker._on_call(dict(event, ok=False, role='plan', instrument='gemini', model='gemini-3.8-flash', latency_s=1.2))
    text = worker.lines[-1]['text']
    assert words in text and 'failed (' not in text and 'transport' not in text


def test_a_busy_service_beside_one_that_has_used_its_retry_never_loops(tmp_path):
    def down(*args):
        down.requests += 1
        raise TimeoutError('timed out')
    down.requests = 0
    busy = Service(*[google(503, GOOGLE_503)] * 6)
    sleeps = []
    with pytest.raises(TransportCensored) as error:
        ask(router(tmp_path, instrument(down, 'a'), instrument(busy, 'b'), sleeps=sleeps))
    assert down.requests == 2 and busy.requests <= 3 and sleeps.count(BUSY_WAIT_S) == 1
    assert 'busy' in error.value.plain
    # Two busy providers: each asked once, then once more after the longer wait, and no more.
    first, second = Service(*[google(503, GOOGLE_503)] * 2), Service(*[google(503, GOOGLE_503)] * 2)
    sleeps = []
    with pytest.raises(TransportCensored):
        ask(router(tmp_path / 'two', instrument(first, 'a'), instrument(second, 'b'), sleeps=sleeps))
    assert (first.requests, second.requests) == (2, 2) and sleeps == [BUSY_WAIT_S]
