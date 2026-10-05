"""One free Google key is enough for a newcomer (acceptance journey J0, phase 3, 2026-10-05).

Google's free key allowed 20 requests a day for gemini-3.8-flash ("limit: 20, model: gemini-3.8-flash"); a busy (503)
answer appeared to spend from it; the quota is per model. One milestone needs more than 20 requests, so nobody got from an
empty folder to an applied milestone in a day on one free Gemini model. These tests replay what the journey met:

* the key saved once sets up a chain of free Gemini models, each with its own hold, and a refusal on one moves to the next;
* a thinking model's answer is asked for with a low effort and room, and a cut-off answer is asked for once more;
* a busy answer is not asked again at once (one click is one request per model);
* a daily refusal holds until Pacific midnight, whatever its "retry in" words say, and the words are kept;
* the requests sent today are counted per model, and said as "about n of 20 used today";
* the first-run words, the model row and the Overview say which model answers.
"""
from __future__ import annotations

import calendar
import io
import json
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from runesmith import instruments
from runesmith.app import providers
from runesmith.app.providers import FREE_GEMINI_WORDS, gemini_free_chain
from runesmith.app.workspace import Workspace
from runesmith.instruments import OpenAICompatInstrument, Router, TransportCensored
from runesmith.pacing import (DayCount, GOOGLE_FREE_DAILY_REQUESTS, Pacing, next_pacific_midnight, reset_time, stated_limit,
                              used_words)

GEMINI = 'https://generativelanguage.googleapis.com/v1beta/openai'
GROQ = 'https://api.groq.com/openai/v1'
ROOT = Path(__file__).resolve().parent.parent
ANSWER = {'choices': [{'message': {'content': '{"ok": true}'}, 'finish_reason': 'stop'}]}
CUT_OFF = {'choices': [{'message': {'content': ''}, 'finish_reason': 'length'}]}      # a thinking model spent its room thinking
BUSY = {'error': {'code': 503, 'status': 'UNAVAILABLE',
                  'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. '
                             'Please try again later.'}}
# Google's own refusal in the journey (worker-errors.log, 2026-10-05 06:34Z), word for word.
DAILY_WORDS = ('Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, '
               'model: gemini-3.8-flash. Please retry in 17h25m25s.')
DAILY = {'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED', 'message': DAILY_WORDS}}
# The models Google listed for a new free key (chat models and some that are not).
LISTED = ['models/' + m for m in (
    'gemini-3.9-flash-preview-09-2026', 'gemini-3.8-flash', 'gemini-3.8-pro', 'gemini-3.8-flash-image', 'gemini-3.8-flash-tts',
    'gemini-3.7-flash', 'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite',
    'gemini-2.5-flash', 'gemini-embedding-001')]
IDS = [m.removeprefix('models/') for m in LISTED]


def utc(day, hour, minute=0, second=0, month=10):
    return float(calendar.timegm((2026, month, day, hour, minute, second)))


class Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class Google:
    """Google's chat endpoint, answering per model from a script: ``Google({'gemini-3.8-flash': [(429, DAILY)]})``. A model
    with nothing left to say answers well. Every request is kept: its model, its body."""

    def __init__(self, script=None):
        self.script, self.sent = {m: list(rows) for m, rows in (script or {}).items()}, []

    def __call__(self, request, timeout=None):
        body = json.loads(request.data.decode())
        self.sent.append(body)
        rows = self.script.get(body['model'])
        status, payload = rows.pop(0) if rows else (200, ANSWER)
        if status >= 400:
            raise HTTPError(request.full_url, status, 'refused', Message(), io.BytesIO(json.dumps(payload).encode()))
        return Response(payload)

    @property
    def models(self):
        return [body['model'] for body in self.sent]


@pytest.fixture
def listed(monkeypatch):
    """Google's model list (a read: it spends none of the allowance)."""
    monkeypatch.setattr(providers, '_get_json', lambda url, **kw: (200, {'data': [{'id': m} for m in LISTED]}))


def chained(tmp_path, listed_fixture=None, roles=('plan', 'repair'), **extra):
    ws = Workspace(tmp_path)
    spec = {'kind': 'openai', 'preset': 'gemini', 'model': 'gemini-3.8-flash', 'base_url': GEMINI, 'label': 'Google Gemini',
            'json_mode': 'json_object', **extra}
    row = ws.save_instrument('gemini', spec, key_value='synthetic-key', roles=list(roles), chain=True)
    return ws, row


def ask(router, role='plan', **extra):
    return router.call(role, prompt='p', system='s', schema=None, max_tokens=500, key='k', **extra)


# ============================================================================== F12: one key, several models ==

def test_the_chain_is_the_newest_flash_the_next_stable_flash_and_the_newest_flash_lite():
    assert gemini_free_chain(IDS) == ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite']   # no pro, preview, tts, image
    assert gemini_free_chain(IDS, 'gemini-3.6-flash') == ['gemini-3.6-flash', 'gemini-3.8-flash', 'gemini-3.7-flash',
                                                         'gemini-3.5-flash-lite']                        # the owner's own pick stays first
    assert gemini_free_chain(['gemini-3.8-flash']) == ['gemini-3.8-flash']
    assert gemini_free_chain([]) == []


def test_saving_a_google_key_sets_up_the_chain_on_the_same_key_for_the_same_roles(tmp_path, listed):
    ws, row = chained(tmp_path)
    config = ws.config()
    names = list(config['instruments'])
    assert names == ['gemini', 'gemini-3.7-flash', 'gemini-3.5-flash-lite']
    assert [config['instruments'][n]['model'] for n in names] == ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite']
    assert {config['instruments'][n]['api_key_secret'] for n in names} == {'gemini'}        # one key, typed once
    assert ws.keys.names() == ['gemini'] and 'synthetic-key' not in json.dumps(config)
    assert config['roles']['plan'] == names and config['roles']['repair'] == names          # the same roles, in the chain's order
    assert row['chain']['ok'] and row['chain']['added'] == names[1:] and 'on the same key' in row['chain']['detail']
    assert ws.ready()['acceptance'] and ws.ready()['usable']['plan'] == names              # the Checker borrows the chain too
    live = ws.router().instruments
    assert all(live[n].free_tier and live[n].takes_reasoning_effort for n in names)
    shown = {i['name']: i for i in ws.inference()['instruments']}
    assert shown['gemini-3.7-flash']['shares_key_with'] == ['gemini', 'gemini-3.5-flash-lite'] and shown['gemini-3.7-flash']['usable']


def test_a_chain_is_only_built_when_asked_and_never_twice(tmp_path, listed):
    ws = Workspace(tmp_path)
    spec = {'kind': 'openai', 'preset': 'gemini', 'model': 'gemini-3.8-flash', 'base_url': GEMINI}
    ws.save_instrument('gemini', spec, key_value='k', roles=['plan'])                         # no chain: as before
    assert list(ws.config()['instruments']) == ['gemini']
    first = ws.add_gemini_chain('gemini')                                                     # an owner's click, no key typed
    assert first['added'] == ['gemini-3.7-flash', 'gemini-3.5-flash-lite'] and ws.config()['roles']['plan'][0] == 'gemini'
    again = ws.add_gemini_chain('gemini')
    assert again['ok'] and again['added'] == [] and 'already set up' in again['detail']
    assert len(ws.config()['instruments']) == 3
    with pytest.raises(Exception):
        ws.save_instrument('paid', {'kind': 'openai', 'model': 'm', 'base_url': 'https://example.org/v1'}, roles=['plan'])
        ws.add_gemini_chain('paid')


def test_when_googles_list_cannot_be_read_the_first_model_is_saved_and_the_way_on_is_said(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, '_get_json', lambda url, **kw: (503, None))
    ws, row = chained(tmp_path)
    assert list(ws.config()['instruments']) == ['gemini'] and ws.ready()['plan']
    assert row['chain']['ok'] is False and 'Add the other free Gemini models' in row['chain']['detail']


def test_a_refusal_on_one_model_moves_to_the_next_at_once_and_each_model_has_its_own_hold(tmp_path, listed, monkeypatch):
    ws, _ = chained(tmp_path)
    google = Google({'gemini-3.8-flash': [(429, DAILY)], 'gemini-3.7-flash': [(429, DAILY)]})
    monkeypatch.setattr(instruments, 'urlopen', google)
    out = ask(ws.router(backoff_s=()))
    # In the role's order: 3.8 refuses, 3.7 refuses, flash-lite answers (the router once jumped from 3.8 straight to lite).
    assert out.ok and google.models == ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite']
    held = Pacing(ws.home / 'PACING.json').active()
    assert sorted(held) == ['gemini', 'gemini-3.7-flash'] and 'gemini-3.5-flash-lite' not in held
    # The next click asks neither of the held models: nothing is spent on them.
    assert ask(ws.router(backoff_s=())).ok and google.models[3:] == ['gemini-3.5-flash-lite']


def test_the_second_model_answers_the_next_click_while_the_first_is_held_until_pacific_midnight(tmp_path, listed, monkeypatch):
    ws, _ = chained(tmp_path)
    google = Google({'gemini-3.8-flash': [(429, DAILY)]})
    monkeypatch.setattr(instruments, 'urlopen', google)
    for _ in range(3):
        assert ask(ws.router(backoff_s=())).ok
    assert google.models == ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.7-flash', 'gemini-3.7-flash']
    view = ws.pacing_view()
    assert view['waiting'] is False and view['answering']['plan']['model'] == 'gemini-3.7-flash'
    assert [row['name'] for row in view['limited']] == ['gemini'] and 'Google Gemini (gemini-3.8-flash)' in view['limited'][0]['words']
    states = {k['name']: (k['held'], k['answering']) for k in view['free_keys']}
    assert states == {'gemini': (True, []), 'gemini-3.7-flash': (False, ['repair', 'plan', 'acceptance']),
                      'gemini-3.5-flash-lite': (False, [])}


def test_with_every_model_of_the_chain_held_the_way_out_is_a_second_provider(tmp_path, listed, monkeypatch):
    ws, _ = chained(tmp_path)
    google = Google({m: [(429, DAILY)] for m in ('gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite')})
    monkeypatch.setattr(instruments, 'urlopen', google)
    with pytest.raises(TransportCensored) as error:
        ask(ws.router(backoff_s=()))
    words = error.value.plain
    assert len(google.sent) == 3 and 'Add a second free provider' in words           # three models of one provider are one provider
    # The models of one key stop together, so they are told as one sentence, not three.
    assert 'Google Gemini: gemini-3.8-flash, gemini-3.7-flash and gemini-3.5-flash-lite have all used up their free allowance for today' in words
    assert words.count('Runesmith will not ask them again before about') == 1 and words.count('Add a second free provider') == 1
    view = ws.pacing_view()
    assert view['waiting'] and view['only_provider_limited'] and len(view['limited']) == 3
    assert view['limited_summary'].count('have all used up their free allowance for today') == 1      # the Overview's one sentence
    # A second provider beside them: the suggestion goes, and its model answers.
    ws.save_instrument('groq', {'kind': 'openai', 'preset': 'groq', 'model': 'openai/gpt-oss-20b', 'base_url': GROQ},
                       key_value='synthetic-2', roles=['plan', 'repair'])
    view = ws.pacing_view()
    assert view['waiting'] is False and view['only_provider_limited'] is False and view['answering']['plan']['name'] == 'groq'


def test_removing_a_model_of_the_chain_keeps_the_key_for_the_others_and_the_last_removal_deletes_it(tmp_path, listed):
    ws, _ = chained(tmp_path)
    ws.remove_instrument('gemini')                                                    # the model that holds the key's name
    assert ws.keys.names() == ['gemini'] and [i['name'] for i in ws.inference()['instruments']] == ['gemini-3.7-flash',
                                                                                                    'gemini-3.5-flash-lite']
    assert all(i['key']['saved'] and i['usable'] for i in ws.inference()['instruments'])
    ws.remove_instrument('gemini-3.5-flash-lite')
    assert ws.keys.names() == ['gemini']
    ws.remove_instrument('gemini-3.7-flash')
    assert ws.keys.names() == []


def test_a_new_key_lifts_the_holds_and_counts_of_the_whole_chain(tmp_path, listed, monkeypatch):
    ws, _ = chained(tmp_path)
    monkeypatch.setattr(instruments, 'urlopen', Google({'gemini-3.8-flash': [(429, DAILY)], 'gemini-3.7-flash': [(429, DAILY)]}))
    ask(ws.router(backoff_s=()))
    assert len(Pacing(ws.home / 'PACING.json').active()) == 2
    ws.save_instrument('gemini', ws.config()['instruments']['gemini'], key_value='a-new-synthetic-key')
    assert Pacing(ws.home / 'PACING.json').active() == {}
    assert DayCount(ws.home / 'REQUESTS_TODAY.json').today('gemini-3.7-flash', GEMINI)['count'] == 0
    assert ws.config()['instruments']['gemini-3.7-flash']['api_key_secret'] == 'gemini'     # still the one key


def test_re_saving_a_model_of_the_chain_keeps_pointing_at_the_shared_key(tmp_path, listed):
    ws, _ = chained(tmp_path)
    sibling = dict(ws.config()['instruments']['gemini-3.7-flash'])
    ws.save_instrument('gemini-3.7-flash', sibling, roles=['plan'])
    assert ws.config()['instruments']['gemini-3.7-flash']['api_key_secret'] == 'gemini' and ws.keys.names() == ['gemini']


# ===================================================================== F13: room and effort for models that think ==

def probe(model='gemini-3.8-flash', *answers, base=GEMINI, thinks=True, **options):
    """An instrument whose requests are kept: (instrument, bodies)."""
    bodies, queue = [], list(answers)

    def transport(method, url, headers, body, timeout):
        bodies.append(body)
        return (200, queue.pop(0)) if queue else (200, ANSWER)
    made = OpenAICompatInstrument(model, model, base_url=base, api_key=lambda: 'k', transport=transport, **options)
    made.takes_reasoning_effort, made.free_tier = thinks, True
    return made, bodies


def test_a_thinking_model_is_asked_for_a_low_effort_and_the_room_of_a_draft_and_others_exactly_as_before():
    gemini, thought = probe('gemini-3.8-flash')
    groq, plain = probe('openai/gpt-oss-120b', base=GROQ, thinks=False, max_request_tokens=8000)
    for made, bodies in ((gemini, thought), (groq, plain)):
        router = Router({made.name: made}, {'acceptance': [made.name]}, backoff_s=())
        from runesmith.app.acceptance_proposals import ANSWER_TOKENS
        from runesmith.app.planner import call_short_answer
        assert call_short_answer(router, 'acceptance', prompt='p', system='s', schema=None, max_tokens=ANSWER_TOKENS, key='k').ok
    assert thought[0]['reasoning_effort'] == 'low' and thought[0]['max_tokens'] == 12000
    assert 'reasoning_effort' not in plain[0] and plain[0]['max_tokens'] == 3000           # Groq's 8,000-token window still takes it
    from runesmith.app.planner import DRAFT_TOKENS, THINKING_ROOM
    assert THINKING_ROOM == DRAFT_TOKENS


def test_an_owners_own_effort_for_a_model_is_not_overridden_by_the_low_default():
    made, bodies = probe()
    made.default_reasoning = 'high'
    router = Router({made.name: made}, {'plan': [made.name]}, backoff_s=())
    assert router.call('plan', prompt='p', system='s', schema=None, max_tokens=3000, key='k', soft_effort='low', room=12000).ok
    assert bodies[0]['reasoning_effort'] == 'high'


def test_an_answer_cut_off_is_asked_for_once_more_with_double_the_room_and_the_log_says_so(tmp_path):
    from runesmith.app.planner import call_short_answer
    made, bodies = probe('gemini-3.8-flash', CUT_OFF, ANSWER)
    router = Router({made.name: made}, {'acceptance': [made.name]}, backoff_s=())
    out = call_short_answer(router, 'acceptance', prompt='p', system='s', schema=None, max_tokens=3000, key='k')
    assert out.ok and [b['max_tokens'] for b in bodies] == [12000, 24000]                  # the journey's one wasted request, not two
    assert out.receipt['asked_again_with_room'] is True
    from runesmith.app.worker import EventBus, Worker
    worker = Worker(Workspace(tmp_path), EventBus())
    worker._on_call(dict(out.receipt, ok=True, role='acceptance', latency_s=3.0))
    texts = [line['text'] for line in worker.lines]
    assert any('the model ran out of room before finishing: Runesmith asked again with more room' in t for t in texts)
    worker._on_call({'ok': False, 'error_kind': 'output', 'error': 'truncated: finish_reason=length', 'role': 'acceptance',
                     'instrument': 'gemini', 'model': 'gemini-3.8-flash', 'latency_s': 9.8})
    assert 'ran out of room before finishing its answer' in worker.lines[-1]['text'] and 'could not be used' not in worker.lines[-1]['text']


def test_an_answer_cut_off_twice_is_given_up_in_plain_words_after_two_requests_only():
    from runesmith.app import acceptance_proposals as proposals
    made, bodies = probe('gemini-3.8-flash', CUT_OFF, CUT_OFF, CUT_OFF)
    router = Router({made.name: made}, {'acceptance': [made.name]}, backoff_s=())
    with pytest.raises(proposals.PlannerUnavailable) as failure:
        proposals._ask(router, {'x': 1}, 'examples', 'k')
    words = str(failure.value)
    assert len(bodies) == 2 and 'ran out of room before finishing its answer, and again when Runesmith asked with more room' in words
    assert 'finish_reason' not in words and 'truncated' not in words
    one, single = probe('gemini-3.8-flash', CUT_OFF, CUT_OFF)
    # A plan goes the same way: asked again once, and the words are the plain ones.
    from runesmith.app.planner import PlannerUnavailable, _call
    plan_router = Router({one.name: one}, {'plan': [one.name]}, backoff_s=())
    with pytest.raises(PlannerUnavailable) as plan:
        _call(None, plan_router, 'p', 's', {'type': 'object'}, 'k', 6000, short_answer=True)
    assert [b['max_tokens'] for b in single] == [12000, 24000] and 'ran out of room' in str(plan.value)


def test_a_cut_off_answer_that_the_second_ask_cannot_repeat_keeps_the_first_words():
    from runesmith.app.planner import call_short_answer
    small, bodies = probe('openai/gpt-oss-120b', CUT_OFF, base=GROQ, thinks=False, max_request_tokens=3600)
    router = Router({small.name: small}, {'acceptance': [small.name]}, backoff_s=())
    out = call_short_answer(router, 'acceptance', prompt='p' * 90, system='s', schema=None, max_tokens=3000, key='k')
    assert len(bodies) == 1 and out.error_kind == 'output' and 'truncated' in out.error      # the doubled ask did not fit its window


# ================================================================================ F14: a busy answer is not asked twice ==

def checks_workspace(tmp_path, listed_fixture):
    ws, _ = chained(tmp_path)
    ws.save_plan({'summary': 'Reading log', 'milestones': [{'title': 'Delete a book by its number',
                  'detail': 'python readinglog.py delete 2 removes book number 2.',
                  'done_when': 'After delete 1, list no longer shows that book.', 'status': 'open'}]})
    ws.update_settings({'build_steps': True})
    from runesmith.app.worker import EventBus, Worker
    return ws, Worker(ws, EventBus())


def propose_job(worker, n=[0]):
    n[0] += 1
    worker._execute({'id': f'job{n[0]}', 'kind': 'propose_acceptance', 'params': {'milestone': 'm1'}, 'by': 'owner'})
    return worker.history[-1]


def test_one_click_on_busy_models_sends_one_request_per_model_and_no_lean_retry(tmp_path, listed, monkeypatch):
    ws, worker = checks_workspace(tmp_path, listed)
    ws.remove_instrument('gemini-3.7-flash')
    ws.remove_instrument('gemini-3.5-flash-lite')                                             # one model, as in the journey
    google = Google({'gemini-3.8-flash': [(503, BUSY)] * 4})
    monkeypatch.setattr(instruments, 'urlopen', google)
    row = propose_job(worker)
    assert row['result'] == 'failed' and len(google.sent) == 1                                 # the journey spent two on one click
    assert 'very busy' in row['outcome']['error'] and '{' not in row['outcome']['error']
    assert 'high demand' in row['outcome']['detail']                                           # the service's words stay in the details
    assert [l['text'] for l in worker.lines if 'is busy in' in l['text']] and len([l for l in worker.lines if 'is busy in' in l['text']]) == 1


def test_a_chain_of_busy_models_is_asked_once_each(tmp_path, listed, monkeypatch):
    ws, worker = checks_workspace(tmp_path, listed)
    google = Google({m: [(503, BUSY)] * 4 for m in ('gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite')})
    monkeypatch.setattr(instruments, 'urlopen', google)
    row = propose_job(worker)
    assert row['result'] == 'failed' and google.models == ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite']
    assert Pacing(ws.home / 'PACING.json').active() == {}                                      # busy is not a hold: only a 429 is


def test_a_request_too_large_for_the_window_still_gets_the_lean_retry_and_a_busy_one_does_not():
    from runesmith.app import acceptance_proposals as proposals
    busy = TransportCensored('x', receipt={'not_admitted': True, 'paced': 'busy'})
    limited = TransportCensored('x', receipt={'not_admitted': True, 'paced': 'limited'})
    large = TransportCensored('x', receipt={'refused_before_answer': 'too_large'})
    gateway = TransportCensored('x', receipt={'not_admitted': True})
    assert [proposals._turned_away(e) for e in (busy, limited, large, gateway)] == [False, False, True, True]


# ======================================================================= F15: a daily limit holds until its midnight ==

def test_the_journeys_own_refusal_is_held_until_pacific_midnight_whatever_it_says_it_will_retry_in(tmp_path):
    # 06:34Z on 5 October: "retry in 17h25m25s" read as 23:59Z, and the key answered again at 07:02Z.
    morning = utc(5, 6, 34)
    assert reset_time(GEMINI, {}, 'http_429 ' + json.dumps(DAILY['error']), morning) == (utc(5, 7), True, False)
    # 09:08Z the same day (phase 3): the next midnight, 07:00Z on the 6th, not 00:00Z (the hold used to follow the words).
    later = utc(5, 9, 8, 2)
    assert reset_time(GEMINI, {}, 'http_429 ' + json.dumps(DAILY['error']), later) == (utc(6, 7), True, False)
    assert next_pacific_midnight(later) == utc(6, 7)
    # A daily refusal that says "PerDay" and a short wait is held the same way; so is a "retry in" of hours without the word.
    assert reset_time(GEMINI, {}, 'PerDay quota. Please retry in 30s', later) == (utc(6, 7), True, False)
    # Another service's own words are kept (Groq's day is rolling): never Google's midnight.
    until, daily, _ = reset_time(GROQ, {}, 'tokens per day (TPD): Limit 100000. Please try again in 7m12s.', later)
    assert daily and until == later + 432
    # A per-minute limit is still held for its minute.
    assert reset_time(GEMINI, {}, 'Please retry in 34s', later) == (later + 34, False, False)


def test_the_service_words_are_kept_beside_the_hold_in_the_receipt_and_in_the_job_details(tmp_path, listed, monkeypatch):
    ws, worker = checks_workspace(tmp_path, listed)
    ws.remove_instrument('gemini-3.7-flash')
    ws.remove_instrument('gemini-3.5-flash-lite')
    monkeypatch.setattr(instruments, 'urlopen', Google({'gemini-3.8-flash': [(429, DAILY)]}))
    row = propose_job(worker)
    assert row['result'] == 'failed' and 'allowance for today' in row['outcome']['error']
    assert 'limit: 20' in row['outcome']['detail'] and 'retry in 17h25m25s' in row['outcome']['detail']     # what Google said
    held = json.loads((ws.home / 'PACING.json').read_text(encoding='utf-8'))['gemini']
    assert held['daily'] is True and 'limit: 20, model: gemini-3.8-flash' in held['said']
    # The next click sends nothing and still carries the words in its receipt.
    again = propose_job(worker)
    assert again['result'] == 'failed' and 'limit: 20' in again['outcome']['detail']
    assert [r['said'] for r in ws.pacing_view()['limited']] == [held['said']]


# ========================================================================== F17: the requests sent today, per model ==

def test_every_request_sent_is_counted_but_one_a_limit_turned_away_and_a_test_counts_too(tmp_path, listed, monkeypatch):
    ws, _ = chained(tmp_path)
    google = Google({'gemini-3.8-flash': [(503, BUSY), (503, BUSY), (200, ANSWER)]})
    monkeypatch.setattr(instruments, 'urlopen', google)
    counts = DayCount(ws.home / 'REQUESTS_TODAY.json')

    def only_gemini():                                  # the first model alone, so that its refusal is the whole answer
        return Router(ws.router().instruments, {'plan': ['gemini']}, backoff_s=(), pacing=Pacing(ws.home / 'PACING.json'), counts=counts)
    for _ in range(2):
        with pytest.raises(TransportCensored):
            ask(only_gemini())                                                              # busy: sent, counted
    assert counts.today('gemini', GEMINI)['count'] == 2
    assert ws.test_instrument('gemini')['ok'] and counts.today('gemini', GEMINI)['count'] == 3    # the Test button spends one too
    monkeypatch.setattr(instruments, 'urlopen', Google({'gemini-3.8-flash': [(429, DAILY)]}))
    with pytest.raises(TransportCensored):
        ask(only_gemini())
    today = counts.today('gemini', GEMINI)
    assert today['count'] == 3 and today['cap'] == 20 and today['learned']                    # the refused one is not counted
    assert counts.today('gemini-3.7-flash', GEMINI)['count'] == 0                              # each model has its own count


def test_the_count_is_the_services_day_and_the_cap_is_learned_from_the_first_refusal(tmp_path):
    now = [utc(5, 6, 59)]
    counts = DayCount(tmp_path / 'REQUESTS_TODAY.json', clock=lambda: now[0])
    for _ in range(3):
        counts.bump('g', GEMINI, 200)
    assert counts.today('g', GEMINI) == {'count': 3, 'cap': 20, 'learned': False, 'day': '2026-10-04'}   # still the 4th, Pacific
    now[0] = utc(5, 7, 1)                                                                      # past Pacific midnight: a new day
    counts.bump('g', GEMINI, 200)
    assert counts.today('g', GEMINI)['count'] == 1 and counts.today('g', GEMINI)['day'] == '2026-10-05'
    assert counts.learn_cap('g', GEMINI, DAILY_WORDS, daily=True) == 20
    assert counts.learn_cap('g', GEMINI, 'limit: 5 requests per minute', daily=False) is None   # a minute's limit is not the day's
    counts.learn_cap('g', GEMINI, 'limit: 1000', daily=True)
    assert counts.today('g', GEMINI)['cap'] == 1000 and counts.today('g', GEMINI)['learned']
    now[0] = utc(6, 12)                                                                        # the cap outlives the day
    assert counts.today('g', GEMINI) == {'count': 0, 'cap': 1000, 'learned': True, 'day': '2026-10-06'}
    other = counts.today('x', GROQ)                                                            # another service: UTC day, no cap guess
    assert other['cap'] is None and other['day'] == '2026-10-06'
    assert stated_limit(DAILY_WORDS) == 20 and stated_limit('no number') is None and GOOGLE_FREE_DAILY_REQUESTS == 20


def test_the_counter_says_about_n_of_20_used_today_and_does_not_pretend_beyond_it():
    assert used_words({'count': 3, 'cap': 20, 'learned': False}) == 'about 3 of 20 used today'
    assert used_words({'count': 0, 'cap': 20, 'learned': False}) == 'about 0 of 20 used today'
    assert used_words({'count': 23, 'cap': 20, 'learned': False}) == 'more than 20 sent today (this key may allow more)'
    assert used_words({'count': 23, 'cap': 20, 'learned': True}) == 'more than 20 sent today'
    assert used_words({'count': 4, 'cap': None}) == 'about 4 sent today' and used_words({'count': 0, 'cap': None}) is None


def test_the_model_row_and_the_waiting_card_say_how_much_of_the_day_is_used(tmp_path, listed, monkeypatch):
    ws, _ = chained(tmp_path)
    script = {'gemini-3.8-flash': [(200, ANSWER)] * 20 + [(429, DAILY)]}
    monkeypatch.setattr(instruments, 'urlopen', Google(script))
    router = lambda: Router(ws.router().instruments, {'plan': ['gemini']}, backoff_s=(), pacing=Pacing(ws.home / 'PACING.json'),
                            counts=DayCount(ws.home / 'REQUESTS_TODAY.json'))
    for _ in range(20):
        assert ask(router()).ok
    row = next(i for i in ws.inference()['instruments'] if i['name'] == 'gemini')
    assert row['used_today']['words'] == 'about 20 of 20 used today' and row['answering'] == ['repair', 'plan', 'acceptance']
    with pytest.raises(TransportCensored) as error:
        ask(router())
    assert 'about 20 of 20 used today' in error.value.plain                                    # the waiting card's words
    card = ws.pacing_view()
    assert 'about 20 of 20 used today' in card['limited'][0]['words'] and card['limited'][0]['used'] == 'about 20 of 20 used today'
    assert card['free_keys'][0]['used']['words'] == 'about 20 of 20 used today' and card['free_keys'][0]['held']
    shown = next(i for i in ws.inference()['instruments'] if i['name'] == 'gemini')
    assert shown['answering'] == [] and next(i for i in ws.inference()['instruments']
                                             if i['name'] == 'gemini-3.7-flash')['answering'] == ['repair', 'plan', 'acceptance']


def test_a_free_key_that_is_not_google_counts_without_inventing_a_cap(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ws.save_instrument('groq', {'kind': 'openai', 'preset': 'groq', 'model': 'openai/gpt-oss-20b', 'base_url': GROQ},
                       key_value='k', roles=['plan'])
    monkeypatch.setattr(instruments, 'urlopen', Google())
    for _ in range(2):
        assert ask(ws.router(backoff_s=())).ok
    assert next(i for i in ws.inference()['instruments'])['used_today']['words'] == 'about 2 sent today'


# =========================================================================== F12 (1)(2): the plain words at first run ==

def test_the_free_key_words_say_what_a_newcomer_needs_before_building():
    words = FREE_GEMINI_WORDS
    for needed in ('about 20 requests a day for each model', 'in AI Studio', 'several free Gemini models', 'on this one key',
                   'second free provider', 'Groq', 'chat window'):
        assert needed in words, needed
    assert providers.PRESET_BY_ID['gemini']['free_note'] == words and providers.PRESET_BY_ID['gemini']['free_chain']
    assert '20 requests a day' in providers.PRESET_BY_ID['gemini']['blurb']


def test_the_words_are_on_the_screens_a_newcomer_sees_before_building(tmp_path):
    inference = (ROOT / 'runesmith/app/static/js/views/inference.js').read_text(encoding='utf-8')
    home = (ROOT / 'runesmith/app/static/js/views/home.js').read_text(encoding='utf-8')
    assert "p.free_note" in inference and "'data-free-note'" in inference and "chain: chain ? chain.checked : undefined" in inference
    assert 'about 20 requests a day for each model' in inference                                 # the "Three ways" card
    assert 's.pacing?.free_key_words' in home                                                    # the first-run hero
    assert 'Add the other free Gemini models' in inference and 'data-add-chain' in inference
    from runesmith.app.server import api_state
    ws = Workspace(tmp_path)
    studio = SimpleNamespace(ws=ws, worker=SimpleNamespace(snapshot=lambda: {}), bus=SimpleNamespace(recent=[]))
    assert api_state(studio, {}, None)['pacing']['free_key_words'] == FREE_GEMINI_WORDS


# ================================================================================================ F16: the hero ==

PHASE_2 = ("role 'plan': no response after 3 attempts; last: http_503 \"[{'error': {'code': 503, 'message': 'This model is "
           "currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': "
           "'UNAVAILABLE'}}]\"")


def test_a_failure_saved_with_the_services_raw_reply_is_told_plainly_and_the_raw_words_move_to_the_details(tmp_path):
    from runesmith.app.planner import plain_stored_error
    plain = plain_stored_error(PHASE_2)
    assert 'busy' in plain and '{' not in plain and 'attempts' not in plain and 'http_503' not in plain
    assert plain_stored_error("checks failed: AssertionError {'a': 1} != {'a': 2}") == "checks failed: AssertionError {'a': 1} != {'a': 2}"   # code's own braces are not a service's reply
    assert plain_stored_error('the model ran out of room before finishing its answer') == 'the model ran out of room before finishing its answer'
    assert 'ran out of room' in plain_stored_error("the model's answer was not usable: truncated: finish_reason=length")
    from runesmith.app.worker import EventBus, Worker
    worker = Worker(Workspace(tmp_path), EventBus())
    old = {'id': 'a', 'kind': 'build', 'result': 'failed', 'finished': '2026-10-05T07:10:22Z', 'outcome': {'error': PHASE_2}}
    new = [{'id': f'p{n}', 'kind': 'propose_acceptance', 'result': 'failed', 'finished': f'2026-10-05T09:0{n}:00Z',
            'outcome': {'error': 'no acceptance checks: the model is busy or at its free limit right now: try again later'}}
           for n in range(4)]
    worker.history.extend([old, *new])
    rows = worker.snapshot()['history']
    assert [r['id'] for r in rows] == ['p3', 'p2', 'p1', 'p0', 'a']                           # newest first, as the Overview reads it
    assert rows[0]['outcome']['error'] == new[3]['outcome']['error']
    assert 'busy' in rows[-1]['outcome']['error'] and '{' not in rows[-1]['outcome']['error']
    assert 'high demand' in rows[-1]['outcome']['detail']                                     # kept, as the service said it
    assert old['outcome']['error'] == PHASE_2                                                  # the stored history is not rewritten


def test_the_hero_reads_the_latest_model_job_not_the_latest_build():
    home = (ROOT / 'runesmith/app/static/js/views/home.js').read_text(encoding='utf-8')
    assert 'latestModelJob(s.worker?.history)' in home and 'plainFailure(last.outcome?.error)' in home
    assert "const last = builds[0]" not in home


def test_a_model_the_service_refused_before_the_count_reached_its_cap_says_so_instead_of_contradicting_itself():
    # The key is used by another program too: "used up (about 3 of 20 used today)" would read as a mistake.
    info = {'count': 3, 'cap': 20, 'learned': True}
    assert used_words(info) == 'about 3 of 20 used today'
    assert used_words(info, refused=True) == 'the service said so after about 3 of 20 sent from here, so this key is used elsewhere too'
    assert 'none were sent from here' in used_words({'count': 0, 'cap': 20, 'learned': True}, refused=True)
    assert used_words({'count': 20, 'cap': 20, 'learned': True}, refused=True) == 'about 20 of 20 used today'
    from runesmith.pacing import limited_summary
    one = limited_summary([{'label': 'Google Gemini', 'model': 'gemini-3.8-flash', 'until': utc(6, 7), 'daily': True, 'used': 'about 20 of 20 used today'}],
                          utc(5, 9, 8), alone=True)
    assert one.startswith('Google Gemini (gemini-3.8-flash) has used up its free allowance for today (about 20 of 20 used today).')
    assert one.endswith('Add a second free provider under Thinking power so work can go on meanwhile.')
    apart = limited_summary([{'label': 'Google Gemini', 'model': 'a', 'until': utc(6, 7), 'daily': True},
                             {'label': 'Groq', 'model': 'b', 'until': utc(5, 10), 'daily': False}], utc(5, 9, 8))
    assert 'Google Gemini (a) has used up' in apart and 'Groq (b) has reached its free limit for now' in apart


def test_the_studios_save_route_sets_up_the_chain_for_a_typed_gemini_key_and_an_owner_click_does_it_for_a_saved_one(tmp_path, listed):
    from runesmith.app import server
    ws = Workspace(tmp_path)
    studio = SimpleNamespace(ws=ws, bus=SimpleNamespace(publish=lambda *a, **k: None))
    spec = {'kind': 'openai', 'preset': 'gemini', 'model': 'gemini-3.8-flash', 'base_url': GEMINI, 'label': 'Google Gemini'}
    saved = server.api_instrument_save(studio, {}, {'name': 'gemini', 'spec': spec, 'key': 'synthetic', 'roles': ['plan']})
    assert saved['chain']['added'] == ['gemini-3.7-flash', 'gemini-3.5-flash-lite'] and len(ws.config()['instruments']) == 3
    # The owner can decline the chain (the dialog's ticked choice), and a save with no key typed never builds one.
    (tmp_path / 'declined').mkdir()
    (tmp_path / 'later').mkdir()
    other = Workspace(tmp_path / 'declined')
    declined = server.api_instrument_save(SimpleNamespace(ws=other, bus=studio.bus), {},
                                          {'name': 'gemini', 'spec': spec, 'key': 'synthetic', 'roles': ['plan'], 'chain': False})
    assert 'chain' not in declined and list(other.config()['instruments']) == ['gemini']
    third = Workspace(tmp_path / 'later')
    third.save_instrument('gemini', spec, key_value='synthetic', roles=['plan'])
    server.api_instrument_save(SimpleNamespace(ws=third, bus=studio.bus), {}, {'name': 'gemini', 'spec': spec, 'roles': ['plan']})
    assert list(third.config()['instruments']) == ['gemini']                                  # no key typed: no chain by itself
    added = server.api_instrument_chain(SimpleNamespace(ws=third, bus=studio.bus), {}, {}, 'gemini')
    assert added['ok'] and len(third.config()['instruments']) == 3                            # the click, with the key already saved
