"""Pacing for free keys: when a service says it is at its limit, remember until when.

A free key allows a few requests a minute and a few hundred a day. Every retry spends from that allowance, and a
request refused with "429" tells when the allowance returns (a Retry-After header, a "retry in 34s" in the message, or,
for a daily limit, midnight on the service's own clock). The router stops asking an instrument that said so, here is
where that is remembered (a small file in the project's Runesmith folder, so the next click does not ask again), and
how the wait is put in plain words.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHORT_WAIT_S = 20            # a wait this short is waited out once, inside the call (a per-minute limiter's own words)
BUSY_WAIT_S = 45             # a busy service ("503, high demand") is asked again once, after this long
UNKNOWN_LIMIT_S = 120        # a 429 that names no time: assume a per-minute limit (the first time)
ESCALATED_LIMIT_S = (900, 3600)   # refused again right after such a guess ran out: longer each time (not Google: see below)
ESCALATE_WINDOW_S = 600      # "right after": within this long of the guess ending
MAX_LIMIT_S = 36 * 3600      # nothing is held back longer than a day and a half
FREE_TIER_TRIES = 2          # at most one retry per call for an instrument with a free tier (retries spend its allowance)
GOOGLE_DAY_HINT_S = 3600     # Google's free tier names a wait this long only for its day's limit (a minute's limit is seconds)
GOOGLE_FREE_DAILY_REQUESTS = 20   # what Google's free key allowed a model per day in the journeys; a refusal's own number replaces it
SAID_CHARS = 600             # how much of the service's own refusal is kept beside the hold
BUSY_RECENT_S = 600          # a model whose last request was turned away as busy this recently is told as busy, not as answering
_LOCK = threading.Lock()

_DURATION = (r"(?:\d+(?:\.\d+)?\s*(?:hours?|hrs?|h|minutes?|mins?|ms|m|seconds?|secs?|s)\s*)+")
_RETRY_WORDS = (re.compile(r'"retryDelay"\s*:\s*"(' + _DURATION + r')"', re.I),
                re.compile(r'(?:retry|try again) (?:in|after) (' + _DURATION + ')', re.I))
_UNIT_S = {'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600, 'm': 60, 'min': 60, 'mins': 60,
           'minute': 60, 'minutes': 60, 's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1, 'ms': 0.001}
_DAILY = re.compile(r'per ?day|PerDay', re.I)


def _seconds_in(text: str) -> float | None:
    """The seconds in the service's own wording ("34s", "7m12s", "1h 2m", "850ms"), or None."""
    total = 0.0
    found = False
    for number, unit in re.findall(r'(\d+(?:\.\d+)?)\s*([a-z]+)', text, re.I):
        factor = _UNIT_S.get(unit.lower())
        if factor is not None:
            total += float(number) * factor
            found = True
    return total if found else None


def _stated_wait(text: str) -> float | None:
    for pattern in _RETRY_WORDS:
        found = pattern.search(text or '')
        if found:
            seconds = _seconds_in(found.group(1))
            if seconds is not None:
                return seconds
    return None


def limit_hints(headers, raw: str) -> dict | None:
    """What a refusal ("429" or "503") says about when to ask again: {"retry_after_s": seconds or None, "daily": bool}."""
    seconds = None
    value = None
    try:
        value = headers.get('Retry-After') if headers is not None else None
    except Exception:                                   # a headers object that cannot be read: use the body only
        value = None
    if value:
        value = str(value).strip()
        if re.fullmatch(r'\d+(?:\.\d+)?', value):
            seconds = float(value)
        else:
            try:
                from email.utils import parsedate_to_datetime
                seconds = max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                seconds = None
    text = raw or ''
    if seconds is None:
        seconds = _stated_wait(text)
    daily = bool(_DAILY.search(text))
    if seconds is None and not daily:
        return None
    return {'retry_after_s': seconds, 'daily': daily}


# ------------------------------------------------------------------------------- the service's own midnight --

def _nth_sunday(year: int, month: int, n: int) -> datetime:
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    return first + timedelta(days=(6 - first.weekday()) % 7, weeks=n - 1)


def _pacific_offset_h(moment: datetime) -> int:
    """-7 in US daylight saving time (second Sunday of March, 2:00 to first Sunday of November, 2:00), else -8."""
    start = _nth_sunday(moment.year, 3, 2).replace(hour=10)
    end = _nth_sunday(moment.year, 11, 1).replace(hour=9)
    return -7 if start <= moment < end else -8


def next_pacific_midnight(now: float) -> float:
    """When Google's daily free limits start again (midnight at the US Pacific coast), as epoch seconds."""
    moment = datetime.fromtimestamp(now, timezone.utc)
    local = moment + timedelta(hours=_pacific_offset_h(moment))
    following = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    guess = following - timedelta(hours=_pacific_offset_h(following))
    return (following - timedelta(hours=_pacific_offset_h(guess))).timestamp()


def reset_time(base_url: str, hints: dict | None, message: str, now: float,
               previous: dict | None = None) -> tuple[float, bool, bool]:
    """(epoch seconds the limit ends, whether it is the day's limit, whether that is only a guess), from the service's words.

    A service that names no time is guessed to have a per-minute limit: held for UNKNOWN_LIMIT_S. Refused again right after
    that guess ran out (``previous`` is the saved hold), the limit is not per-minute: Google's free key is then held
    until its midnight (its day is used up: its refusal says "You exceeded your current quota" in both cases, and a
    per-minute one must not lock a newcomer out for hours), any other service for longer each time."""
    hints = hints or {}
    seconds = hints.get('retry_after_s')
    daily = bool(hints.get('daily')) or bool(_DAILY.search(message or ''))
    google = 'generativelanguage.googleapis.com' in (base_url or '')
    if seconds is None:
        seconds = _stated_wait(message)
    if google and (daily or (seconds is not None and seconds >= GOOGLE_DAY_HINT_S)):
        # Google's day ends at midnight on the US Pacific coast, whatever its "retry in" words say (journey J0: "retry
        # in 17h25m25s" at 06:34Z, and the key answered again at 07:02Z). The service's own words are kept beside the hold.
        return min(next_pacific_midnight(now), now + MAX_LIMIT_S), True, False
    if seconds is not None and not (daily and seconds < 60):
        return now + min(MAX_LIMIT_S, max(1.0, seconds)), daily, False
    if daily:                                           # the day's limit, named as such
        return min(next_pacific_midnight(now), now + MAX_LIMIT_S), True, False
    strikes = 0
    if isinstance(previous, dict) and previous.get('guessed') and now <= float(previous.get('until') or 0) + ESCALATE_WINDOW_S:
        strikes = int(previous.get('strikes') or 1)
    if strikes and google:
        return min(next_pacific_midnight(now), now + MAX_LIMIT_S), True, True
    if strikes:
        return now + ESCALATED_LIMIT_S[min(strikes, len(ESCALATED_LIMIT_S)) - 1], False, True
    return now + UNKNOWN_LIMIT_S, False, True


# ----------------------------------------------------------------------------------------- plain words --

def clock(epoch: float) -> str:
    return time.strftime('%H:%M', time.localtime(epoch))


def how_long(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 90:
        return f'about {max(1, seconds)} seconds'
    minutes = round(seconds / 60)
    if minutes < 90:
        return f'about {minutes} minutes'
    hours = round(seconds / 3600)
    return f'about {hours} hours'


def limited_words(name: str, until: float, daily: bool, now: float, *, alone: bool = False, used: str | None = None) -> str:
    what = "has used up its free allowance for today" if daily else "has reached its free limit for now"
    counted = f" ({used})" if used and daily else ""
    words = (f"{name} {what}{counted}. Runesmith will not ask it again before about {clock(until)} "
             f"({how_long(until - now)} from now), so no more of the allowance is spent.")
    if alone:
        words += " Add a second free provider under Thinking power so work can go on meanwhile."
    return words


def limited_summary(rows: list[dict], now: float, *, alone: bool = False) -> str:
    """One plain sentence for every model that is held back. Models of one provider that stop together (the models of one
    free key do) are told as one ("Google Gemini: gemini-3.8-flash, gemini-3.7-flash and gemini-3.5-flash-lite have all
    used up their free allowance for today ..."), not once each. A row is {label, model, until, daily, used}; ``alone``
    adds the way out (a second provider) after the last sentence."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row.get('label') or row.get('model') or '', bool(row.get('daily')), int(float(row['until']) // 60)), []).append(row)
    sentences = []
    for number, ((label, daily, _), members) in enumerate(groups.items()):
        last = number == len(groups) - 1
        first = members[0]
        if len(members) == 1:
            name = f"{label} ({first['model']})" if first.get('label') and first.get('model') else label
            sentences.append(limited_words(name, first['until'], daily, now, alone=alone and last, used=first.get('used')))
            continue
        models = [m.get('model') or m.get('name') or label for m in members]
        named = ', '.join(models[:-1]) + ' and ' + models[-1]
        what = "have all used up their free allowance for today" if daily else "have all reached their free limit for now"
        words = (f"{label}: {named} {what}. Runesmith will not ask them again before about {clock(first['until'])} "
                 f"({how_long(first['until'] - now)} from now), so no more of the allowance is spent.")
        if alone and last:
            words += " Add a second free provider under Thinking power so work can go on meanwhile."
        sentences.append(words)
    return ' '.join(sentences)


def truncated_words(retried: bool = False) -> str:
    """An answer that ran out of room before it was finished (a model that thinks spends the room on its reasoning)."""
    if retried:
        return ("the model ran out of room before finishing its answer, and again when Runesmith asked with more room: "
                "try again, or put a model that answers directly first under Thinking power")
    return ("the model ran out of room before finishing its answer: try again, or put a model that answers directly "
            "first under Thinking power")


ROOM_RETRY_WORDS = "the model ran out of room before finishing: Runesmith asked again with more room"


def busy_words(name: str, *, models: int = 1, providers: int = 1) -> str:
    """The plain line for a call every model of which was turned away as busy. What helps depends on what there is: with one
    model, a second one; with a chain of models of one provider (they share one service's busy hours), a second provider;
    with several providers there is nothing to add (journey J0-F24: a chain was told to put a second model first)."""
    words = f"{name} is very busy right now (the service said so, and did not take the request). Nothing was lost: "
    if models <= 1:
        return words + "try again in a few minutes, or put a second model first under Thinking power."
    if providers <= 1:
        return words + "try again in a few minutes, or add a second free provider (Groq, for example) under Thinking power."
    return words + "try again in a few minutes."


# ------------------------------------------------------------------------------------------ the saved marks --

class Pacing:
    """Which instruments are held back until when: ``{name: {until, daily, since, plain}}`` in one small JSON file."""

    def __init__(self, path: str | Path, *, clock=time.time) -> None:
        self.path, self.now = Path(path), clock

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        from runesmith.atomic import replace
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, sort_keys=True), encoding='utf-8', newline='\n')
            replace(temporary, self.path)
        except OSError:                                  # pacing is a courtesy: never stop a call because it cannot be saved
            pass

    def limited(self, name: str) -> dict | None:
        mark = self._read().get(name)
        if isinstance(mark, dict) and isinstance(mark.get('until'), (int, float)) and mark['until'] > self.now():
            return mark
        return None

    def active(self) -> dict:
        now = self.now()
        return {n: m for n, m in self._read().items()
                if isinstance(m, dict) and isinstance(m.get('until'), (int, float)) and m['until'] > now}

    def recent(self, name: str) -> dict | None:
        """The saved hold, even when it has just run out (a guess is judged by what happens next)."""
        mark = self._read().get(name)
        return mark if isinstance(mark, dict) and isinstance(mark.get('until'), (int, float)) else None

    def mark(self, name: str, until: float, *, daily: bool = False, guessed: bool = False, said: str | None = None) -> dict:
        """Hold ``name`` back until ``until``. ``said`` is the service's own refusal, kept as it was told (the hold may
        follow Runesmith's reading of the service's day, not its "retry in" words: the two can then be told apart)."""
        now = self.now()
        with _LOCK:
            stored = self._read()
            before = stored.get(name) if isinstance(stored.get(name), dict) else {}
            strikes = 0
            if guessed:
                again = before.get('guessed') and now <= float(before.get('until') or 0) + ESCALATE_WINDOW_S
                strikes = int(before.get('strikes') or 1) + 1 if again else 1
            row = {'until': float(until), 'daily': bool(daily), 'since': now, 'guessed': bool(guessed), 'strikes': strikes}
            if said:
                row['said'] = str(said)[:SAID_CHARS]
            data = {n: m for n, m in stored.items()
                    if isinstance(m, dict) and isinstance(m.get('until'), (int, float)) and m['until'] + ESCALATE_WINDOW_S > now}
            data[name] = row
            self._write(data)
        return row

    def clear(self, name: str) -> None:
        with _LOCK:
            data = self._read()
            if name in data:
                del data[name]
                self._write(data)


# ------------------------------------------------------------------------------------- requests sent today --

GOOGLE_HOST = 'generativelanguage.googleapis.com'
_STATED_LIMIT = re.compile(r'\blimit:\s*(\d{1,6})\b', re.I)


def is_google(base_url: str | None) -> bool:
    return GOOGLE_HOST in (base_url or '')


def service_day(base_url: str | None, now: float) -> str:
    """The day a service counts its daily allowance in: Google's ends at midnight on the US Pacific coast (the journeys'
    allowance came back at 07:00Z), any other service's is taken as the UTC day."""
    moment = datetime.fromtimestamp(now, timezone.utc)
    if is_google(base_url):
        moment = moment + timedelta(hours=_pacific_offset_h(moment))
    return moment.strftime('%Y-%m-%d')


def stated_limit(message: str | None) -> int | None:
    """The number a day's refusal names ("... free_tier_requests, limit: 20, model: gemini-3.8-flash"), or None."""
    found = _STATED_LIMIT.search(message or '')
    return int(found.group(1)) if found else None


def used_words(info: dict | None, *, refused: bool = False) -> str | None:
    """How much of today's allowance has gone, in the owner's words ("about 3 of 20 used today"), or None when there is
    nothing to say. The count is what this Runesmith sent: another program on the same key spends from it too. For a model
    the service has just refused for the day (``refused``), a count below its cap is told as it is: the service said so
    after that many requests from here, so the key is used somewhere else too."""
    if not info:
        return None
    count, cap = int(info.get('count') or 0), info.get('cap')
    if refused and cap and count < cap:
        return (f"the service said so after about {count} of {cap} sent from here, so this key is used elsewhere too"
                if count else "the service said so, though none were sent from here today: this key is used elsewhere too")
    if not cap:
        return f"about {count} sent today" if count else None
    if count > cap:
        return f"more than {cap} sent today (this key may allow more)" if not info.get('learned') else f"more than {cap} sent today"
    return f"about {count} of {cap} used today"


class DayCount:
    """Requests sent per instrument today, counted where they are sent (so a Test, a retry and an answer that was cut off
    all count): ``{name: {day, count, cap}}`` in one small JSON file. A day is the service's own day (``service_day``).
    A request a limit turned away ("429") is not counted: it did not spend the allowance. ``cap`` is learned from the
    first day's refusal that names a limit; Google's free key is taken to allow GOOGLE_FREE_DAILY_REQUESTS until then."""

    def __init__(self, path: str | Path, *, clock=time.time) -> None:
        self.path, self.now = Path(path), clock

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        from runesmith.atomic import replace
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, sort_keys=True), encoding='utf-8', newline='\n')
            replace(temporary, self.path)
        except OSError:                                  # a counter is a courtesy: never stop a call because it cannot be saved
            pass

    def bump(self, name: str, base_url: str | None, status: int | None = None) -> None:
        if status == 429:
            return
        day = service_day(base_url, self.now())
        with _LOCK:
            data = self._read()
            row = data.get(name) if isinstance(data.get(name), dict) else {}
            count = int(row.get('count') or 0) + 1 if row.get('day') == day else 1
            busy = {}                                   # the run of requests in a row that the service turned away as busy
            if status == 503:
                busy = {'busy': int(row.get('busy') or 0) + 1, 'busy_at': self.now()}
            elif row.get('busy'):
                busy = {'busy': 0}
            data[name] = dict(row, day=day, count=count, **busy)
            self._write(data)

    def busy_now(self, name: str) -> dict | None:
        """{streak, at} when this instrument's last requests (``streak`` of them, in a row) were all turned away as busy and
        the last was within BUSY_RECENT_S; otherwise None (journey J0-F24: a row kept saying "answering now" after four 503s)."""
        row = self._read().get(name)
        row = row if isinstance(row, dict) else {}
        streak, at = int(row.get('busy') or 0), row.get('busy_at')
        if streak > 0 and isinstance(at, (int, float)) and 0 <= self.now() - at <= BUSY_RECENT_S:
            return {'streak': streak, 'at': float(at)}
        return None

    def learn_cap(self, name: str, base_url: str | None, message: str | None, daily: bool) -> int | None:
        """Keep the limit a day's refusal names. Only a daily refusal: a per-minute one names a different (smaller) number."""
        limit = stated_limit(message) if daily else None
        if not limit:
            return None
        with _LOCK:
            data = self._read()
            row = data.get(name) if isinstance(data.get(name), dict) else {}
            data[name] = dict(row, cap=limit, day=row.get('day') or service_day(base_url, self.now()),
                              count=int(row.get('count') or 0))
            self._write(data)
        return limit

    def today(self, name: str, base_url: str | None, *, free: bool = True) -> dict:
        row = self._read().get(name)
        row = row if isinstance(row, dict) else {}
        day = service_day(base_url, self.now())
        count = int(row.get('count') or 0) if row.get('day') == day else 0
        cap = row.get('cap') if isinstance(row.get('cap'), int) and row.get('cap') > 0 else None
        learned = cap is not None
        if cap is None and free and is_google(base_url):
            cap = GOOGLE_FREE_DAILY_REQUESTS
        return {'count': count, 'cap': cap, 'learned': learned, 'day': day}

    def clear(self, name: str) -> None:
        with _LOCK:
            data = self._read()
            if name in data:
                del data[name]
                self._write(data)
