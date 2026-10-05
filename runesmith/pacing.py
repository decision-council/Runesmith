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


def limited_words(name: str, until: float, daily: bool, now: float, *, alone: bool = False) -> str:
    what = "has used up its free allowance for today" if daily else "has reached its free limit for now"
    words = (f"{name} {what}. Runesmith will not ask it again before about {clock(until)} "
             f"({how_long(until - now)} from now), so no more of the allowance is spent.")
    if alone:
        words += " Add a second free provider under Thinking power so work can go on meanwhile."
    return words


def busy_words(name: str) -> str:
    return (f"{name} is very busy right now (the service said so, and did not take the request). Nothing was lost: "
            "try again in a few minutes, or put a second model first under Thinking power.")


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

    def mark(self, name: str, until: float, *, daily: bool = False, guessed: bool = False) -> dict:
        now = self.now()
        with _LOCK:
            stored = self._read()
            before = stored.get(name) if isinstance(stored.get(name), dict) else {}
            strikes = 0
            if guessed:
                again = before.get('guessed') and now <= float(before.get('until') or 0) + ESCALATE_WINDOW_S
                strikes = int(before.get('strikes') or 1) + 1 if again else 1
            row = {'until': float(until), 'daily': bool(daily), 'since': now, 'guessed': bool(guessed), 'strikes': strikes}
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
