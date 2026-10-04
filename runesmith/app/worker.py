"""The Studio's worker: one background thread per workspace that maps, works, plans and reports.

Jobs run one at a time, in order, so a small computer is never asked to do two heavy
things at once:

* ``map``   — map the folder (and, if allowed, run objects' tests on throwaway copies);
* ``round`` — map, find repair opportunities in every code object, serve the new ones
  through the run loop (which interleaves Kaizen steps and online trials), then write
  the report. In ``observe`` autonomy a round only maps;
* ``plan``  — ask the planner model for a plan from the brief and the map;
* ``draft`` — ask it for the first files of a milestone, as an unverified draft;
* ``health`` — the doctor's checks, with network probes.

Rounds also run on a schedule (``auto_work``, ``interval_minutes``). Everything the
worker does is published on an event bus that the web page listens to, and written
to the home's ledger by the kernel as usual.
"""

from __future__ import annotations

import calendar
import importlib.util
import json
import queue
import threading
import time
import traceback
import uuid
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from runesmith.app.planner import SkippedByOwner
from runesmith.app.workspace import Workspace, WorkspaceError, _read_json, _write_json
from runesmith.app.worker_journal import Record, MAX_JOBS, validate_job, validate_queue


# What a job does, in the owner's words, for the live log (journey J1-F3: "Propose_acceptance skipped").
JOB_WORDS = {"propose_acceptance": "Proposing acceptance checks", "plan": "Drafting a plan", "goalposts": "Proposing goalposts",
             "draft": "Drafting files", "build": "Building the next step", "revise": "Revising a draft",
             "correct": "Correcting a draft", "escalate": "Giving the step one more try", "readmit": "Checking a kept answer again", "readmit_answer": "Checking a kept answer again", "supplement": "Asking for missing files",
             "breakdown": "Proposing smaller steps", "split": "Breaking a stuck step down",
             "resume_check": "Rechecking a draft whose checks did not finish",
             "map": "Mapping the folder", "round": "The round",
             "measure": "Taking a measurement"}
KIND_WORDS = {"python_repository": ("Python project", "Python projects"), "node_repository": ("Node project", "Node projects"),
              "document_collection": ("document collection", "document collections"), "website": ("website", "websites"),
              "folder": ("folder", "folders"), "data_reports": ("report folder", "report folders"),
              "excluded": ("excluded folder", "excluded folders")}
# How a repair attempt ended, in the owner's words (the Work page uses the same wording).
ATTEMPT_WORDS = {
    "public_pass": "a fix passed the tests the model may see; the held-out judge decides next",
    "budget_exhausted": "no fix the tests accept within the model's allowed calls",
    "navigation_rejected": "the model asked to read no usable file",
    "navigation_output_failure": "the model's answer was not in the requested form",
    "instrument_subject_failure": "the model could not be reached, or answered with an error",
    "censored_transport": "the connection to the model failed, so this attempt does not count",
    "organ_error": "the repair organ failed; recorded so Runesmith can improve it",
    "organ_timeout": "the repair organ ran out of time",
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _same_waiting_round(last, done) -> bool:
    """A scheduled round that ended exactly like the one before, having advanced nothing (for example, every try
    for a step used up, or the same draft still waiting for checks): recorded as one row with a count. A new draft
    has a new id, so its outcome never equals the one before."""
    # A scheduled round that failed exactly like the one before counts too (review of J11-G17: a refused key or a
    # request too large for every model uses no try, so each round failed the same way and pushed real work out).
    return (isinstance(last, dict) and last.get('by') == done.get('by') == 'schedule'
            and last.get('kind') == done.get('kind') and last.get('params') == done.get('params')
            and last.get('result') == done.get('result')
            and done.get('result') in ('done', 'failed')
            and last.get('outcome') == done.get('outcome') and not (done.get('outcome') or {}).get('advanced'))


class StopRequested(Exception):
    """Raised from the run loop's step hook when the owner asked to stop after the current step."""


class EventBus:
    """Fan-out of events to every open page (server-sent events), with a short replay buffer."""

    def __init__(self, keep: int = 400) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._seq = 0
        self.recent: deque[dict[str, Any]] = deque(maxlen=keep)

    def publish(self, kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            event = {"id": self._seq, "kind": kind, "utc": _now(), "data": data or {}}
            self.recent.append(event)
            for subscriber in list(self._subscribers):
                try:
                    subscriber.put_nowait(event)
                except queue.Full:                         # a stalled page misses events, never blocks work
                    pass
        return event

    def subscribe(self) -> queue.Queue:
        subscriber: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def since(self, event_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self.recent if e["id"] > event_id]


def reachable(spec: dict[str, Any], timeout: float = 3.0) -> tuple[bool, str]:
    """Does a local model server answer at all? Remote providers are not probed here (that costs nothing, but
    is slow and their keys are checked by the call itself)."""
    base = str(spec.get("base_url") or "")
    if spec.get("kind") != "openai" or not ("127.0.0.1" in base or "localhost" in base):
        return True, "not probed"
    hint = {"ollama": "is Ollama running? Start the Ollama app, or run `ollama serve`",
            "lmstudio": "is LM Studio's local server started?",
            "llamacpp": "is `llama-server` running?"}.get(str(spec.get("preset") or ""), "is the model server running?")
    try:
        with urlopen(Request(base.rstrip("/") + "/models"), timeout=timeout) as reply:
            return reply.status < 500, f"answered {reply.status}"
    except (URLError, OSError):
        return False, f"nothing answers at {base}: {hint}"


# Full speed (J11-F21): the steps whose end starts the next one at once while models answer, and the wait when a
# step had nothing to ask a model.
FULL_SPEED_KINDS = frozenset({'build', 'mode', 'propose_acceptance', 'escalate', 'split'})
FULL_SPEED_IDLE_S = 120.0


class Worker:
    def __init__(self, ws: Workspace, bus: EventBus) -> None:
        self.ws, self.bus = ws, bus
        self._jobs: deque[dict[str, Any]] = deque()
        self._cv = threading.Condition()
        self._closing = False
        self._stop_after_step = False
        self._records = {}
        self._storage_error = ''
        for name in ('STUDIO_STATE.json', 'STUDIO_JOBS.json', 'STUDIO_QUEUE.json', 'STUDIO_CURRENT.json'):
            try:
                self._records[name] = Record(ws.home / name)
            except (OSError, ValueError, WorkspaceError) as error:
                self._storage_error += f'{name}: {error}. '
        state = self._records.get('STUDIO_STATE.json')
        state = state.value if state and state.value is not None else {}
        if not isinstance(state, dict) or ('paused' in state and type(state['paused']) is not bool):
            self._storage_error += 'Invalid STUDIO_STATE.json. '
            state = {}
        history = self._records.get('STUDIO_JOBS.json')
        history = history.value if history and history.value is not None else []
        if not isinstance(history, list) or not all(isinstance(row, dict) and isinstance(row.get('id'), str) for row in history):
            self._storage_error += 'Invalid STUDIO_JOBS.json. '
            history = []
        self._recovery = None
        try:
            queued = self._records.get('STUDIO_QUEUE.json')
            jobs, self._recovery = validate_queue(queued.value if queued else None, ws.root)
            self._jobs.extend(jobs)
        except (ValueError, WorkspaceError) as error:
            self._storage_error += str(error)
        marker = self._records.get('STUDIO_CURRENT.json')
        if self._jobs or (marker and marker.digest) or self._storage_error:
            self._add_recovery('Saved work needs review after restart. Nothing has been replayed.')
        self.paused = bool(state.get('paused')) or bool(self._recovery)
        # Who paused: a hold that only the restart review made may be lifted by the owner's recovery setting; a pause
        # the owner chose never is (an old record names nobody, so it is the owner's).
        self._pause_by = ('recovery' if state.get('by') == 'recovery' else 'owner') if state.get('paused') else (
            'recovery' if self.paused else None)
        self.current: dict[str, Any] | None = None
        self.status, self.detail, self.since = "idle", "", _now()
        self.history: deque[dict[str, Any]] = deque(history[-30:], maxlen=30)
        self._recovered = False
        self.lines: deque[dict[str, Any]] = deque(maxlen=300)
        self._manual_seen: list[str] | None = None
        self._thread = threading.Thread(target=self._run, name="runesmith-worker", daemon=True)
        self._watch = threading.Thread(target=self._watch_manual, name="runesmith-watch", daemon=True)

    # ------------------------------------------------------------------ control --

    def start(self) -> None:
        self._recover()
        self._watch.start()
        self._thread.start()

    def _recover(self) -> None:
        """After the Studio was closed mid-job: record the interrupted job, and set aside relay requests nobody waits for."""
        try:
            self._recover_records()
        except (OSError, ValueError, WorkspaceError) as error:
            self._block_storage(error)
        self._keep_by_setting()

    def _keep_by_setting(self):
        """Journey J11-G42: a project that runs without its owner never gets the review a restart asks for, so the
        owner may choose "keep the queue and continue". Runesmith then records the decision the owner's own "keep" makes
        (reviewed by "Runesmith (your setting)"), and resumes unless the owner had paused. It never replays the
        interrupted call, and decides nothing the review could not: unreadable or changed control records, a current
        job, or a write-recovery conflict still wait for the owner."""
        try:
            if self.ws.settings().get('recovery_policy') != 'keep':
                return
            with self._cv:
                recovery = self._recovery
                if (not recovery or self._storage_error or self.current or self._records['STUDIO_CURRENT.json'].digest
                        or any(str(reason).startswith('A write-recovery conflict') for reason in recovery['reasons'])):
                    return
                revision, lifted = recovery['revision'], self._pause_by != 'owner'
            self.review_recovery(revision=revision, decision='keep', reviewed=True, by='Runesmith (your setting)')
            if lifted:
                self.resume()
            from runesmith.app import automatic
            waiting = len(self._jobs)
            said = ('The Studio was restarted after a job was interrupted. By your setting, Runesmith kept the waiting work '
                    f'({waiting} job{"" if waiting == 1 else "s"}) and ' + ('went on.' if lifted else 'left the pause you set.')
                    + ' The interrupted job itself was not run again.')
            automatic.record(self.ws, said, kind='recovery', decision='keep', resumed=lifted, waiting=waiting)
            self.say(said, 'warn')
        except (OSError, ValueError, WorkspaceError) as error:
            # Nothing is decided on evidence it cannot read: the review waits for the owner, as it always did.
            self.say(f'Your recovery setting could not be followed ({error}); the restart review waits for you.', 'warn')

    def _recover_records(self):
        if self._recovered:
            return
        if self._storage_error:
            self.paused = True
            self.say(self._storage_error + 'Recovery is blocked; no control evidence was overwritten.', 'warn')
            return
        for receipt in self.ws.recover_writes():
            self.say(f"Write recovery: {receipt['key']} — {receipt['state']}", "warn")
            if receipt['state'] == 'conflict':
                self._add_recovery('A write-recovery conflict needs inspection before continuing.')
        marker = self._records['STUDIO_CURRENT.json']
        interrupted = marker.value
        try:
            marker.check()
            if marker.digest:
                validate_job(interrupted)
                same_id = next((job for job in self._jobs if job['id'] == interrupted['id']), None)
                if same_id and (same_id['kind'] != interrupted['kind'] or
                        same_id.get('params', {}) != interrupted.get('params', {})):
                    raise WorkspaceError('Current marker and waiting intention disagree; neither was discarded.')
                self._add_recovery('Studio closed with a current-job marker. Inspect saved outcomes and provider receipts.')
                self._recovery['interrupted'] = interrupted.get('kind')      # for the owner's plain summary (J4-F11)
            if self._recovery:
                self.pause(by=self._pause_by or 'recovery')  # Persist the hold before clearing any current marker.
                self._save_queue(list(self._jobs))
        except (OSError, ValueError, WorkspaceError) as error:
            self._block_storage(error)
            return
        if interrupted:
            guidance = ('Studio closed while this job ran. Inspect Work & proposals and its saved receipts before continuing. '
                        'An author call may already have been processed: retrieve its saved response rather than submit it again. '
                        'Spent check allocations remain spent; no job was automatically replayed.')
            # A crash after history was committed but before marker removal is
            # not another interrupted outcome, and must never replay that job.
            previous = next((row for row in self.history if row['id'] == interrupted['id']), None)
            if previous and (previous.get('kind') != interrupted['kind'] or
                    previous.get('params', {}) != interrupted.get('params', {}) or
                    previous.get('result') not in {'done', 'failed', 'stopped', 'skipped', 'interrupted'}):
                raise WorkspaceError('Current job and saved outcome disagree; inspect records before continuing.')
            if not previous:
                self.history.append(dict(interrupted, finished=_now(), result="interrupted",
                                         outcome={"summary": guidance}))
                self._records['STUDIO_JOBS.json'].write(list(self.history))
            remaining = [job for job in self._jobs if job['id'] != interrupted['id']]
            self._save_queue(remaining)
            self._jobs = deque(remaining)
            marker.remove()
            what = JOB_WORDS.get(interrupted['kind'], interrupted['kind'].replace('_', ' ').capitalize())
            self.say(f"The Studio closed during this job: {what}. Its saved outcome is kept. {guidance}",   # J2-F5
                     "warn")
        if self._recovery:
            # A park decision is written before changing the queue/history. A
            # crash between those writes must not make those intentions runnable
            # again, even when there were more jobs than the history window.
            decision = Record(self.ws.home / 'studio-recovery' / (self._recovery['revision'] + '.json')).value
            if decision is not None:
                if (not isinstance(decision, dict) or decision.get('revision') != self._recovery['revision'] or
                        decision.get('decision') not in {'keep', 'park'} or decision.get('jobs') != list(self._jobs)):
                    raise WorkspaceError('Interrupted recovery decision differs from the saved queue; inspect both records.')
                if decision['decision'] == 'park':
                    self._add_recovery('A saved set-aside decision was recovered; its intentions remain archived, not queued.')
                    # A new review identity preserves the previous immutable receipt.
                    self._recovery['revision'] = uuid.uuid4().hex
                    self._save_queue([])
                    self._jobs.clear()
        orphaned = self.ws.set_aside_orphaned_requests()
        if orphaned and self._recovery:
            self._recovery['relay_set_aside'] = orphaned
        if orphaned:
            self.say(f"Set aside {orphaned} chat-relay request(s) from before the restart: nothing waits for them now.",
                     "warn")
        self._recovered = True

    def _add_recovery(self, reason):
        if not self._recovery:
            self._recovery = {'revision': uuid.uuid4().hex, 'created': _now(), 'reasons': []}
        if reason not in self._recovery['reasons']:
            self._recovery['reasons'].append(reason)

    def _block_storage(self, error):
        self._storage_error = str(error)
        self._add_recovery('Control storage could not be committed. Inspect records; no automatic retry.')
        self.paused = True
        self.say(self._storage_error, 'error')
        self._set('blocked', 'Recovery review required; control storage is uncertain.')

    def _save_queue(self, jobs, *, recovery=...):
        value = {'version': 1, 'root': str(self.ws.root), 'jobs': jobs,
                 'recovery': self._recovery if recovery is ... else recovery}
        validate_queue(value, self.ws.root)
        self._records['STUDIO_QUEUE.json'].write(value)

    def _require_ready(self):
        if self._recovery or self._storage_error:
            raise WorkspaceError('Recovery review is required. Inspect Activity; no job has been replayed.')

    def review_recovery(self, *, revision, decision, reviewed, by='owner'):
        """Acknowledge inspected evidence; keep paused and never replay a current job. `by` is the owner, or Runesmith
        acting on the owner's recovery setting (journey J11-G42)."""
        with self._cv:
            if (not self._recovery or revision != self._recovery['revision'] or reviewed is not True or not isinstance(decision, str)
                    or decision not in {'keep', 'park'}):
                raise WorkspaceError('Recovery review changed or was not acknowledged; refresh Activity.')
            if self._storage_error or self.current or self._records['STUDIO_CURRENT.json'].digest:
                raise WorkspaceError('Recovery records still need reconciliation; nothing resumed.')
            for record in self._records.values():
                record.check()
            self.pause(by=self._pause_by or 'recovery')
            receipt = {'revision': revision, 'decision': decision, 'reviewed_by': by, 'utc': _now(),
                       'jobs': list(self._jobs), 'recovery': self._recovery,
                       'scope': 'Review acknowledgement only. Queue stays paused; no job, call, check or apply was run. '
                                'This does not reconcile provider outcomes or restore spent allocations.'}
            saved = Record(self.ws.home / 'studio-recovery' / (revision + '.json'))
            if saved.value is not None:
                if not isinstance(saved.value, dict) or saved.value.get('decision') != decision or saved.value.get('jobs') != receipt['jobs']:
                    raise WorkspaceError('A different recovery decision is already recorded; inspect it first.')
            else:
                saved.write(receipt)
            if decision == 'park':
                for job in self._jobs:
                    if not any(row['id'] == job['id'] for row in self.history):
                        self.history.append(dict(job, finished=_now(), result='not_started',
                                                 outcome={'summary': 'Waiting intention set aside after restart review; no work run.'}))
                self._records['STUDIO_JOBS.json'].write(list(self.history))
            jobs = list(self._jobs) if decision == 'keep' else []
            self._save_queue(jobs, recovery=None)
            self._jobs = deque(jobs)
            self._recovery = None
        self.say('Recovery review recorded. Queue remains paused; Resume is a separate decision.')
        self._publish_state()
        return self.snapshot()

    def close(self) -> None:
        with self._cv:
            self._closing = True
            self._stop_after_step = True
            self._cv.notify_all()

    @contextmanager
    def switch_guard(self):
        """Prevent a new claim while Studio prepares an idle-home handoff."""
        with self._cv:
            if self.current:
                raise WorkspaceError('The current job is still running. Wait for it to finish before switching folders.')
            marker = self._records.get('STUDIO_CURRENT.json')
            if marker is None:
                raise WorkspaceError('Current-job custody is unreadable; inspect recovery before switching folders.')
            marker.check()
            if marker.digest:
                raise WorkspaceError('A current-job marker needs recovery before switching folders.')
            yield

    def wait_stopped(self, timeout: float = 2.0) -> bool:
        """A stop request is not proof of completion. Never join while holding _cv."""
        deadline = time.monotonic() + timeout
        for thread in (self._thread, self._watch):
            if thread.ident is not None and thread is not threading.current_thread():
                thread.join(max(0, deadline - time.monotonic()))
        return not (self._thread.is_alive() or self._watch.is_alive())

    def enqueue(self, kind: str, *, by: str = "owner", **params: Any) -> dict[str, Any]:
        """Queue one job. ``by`` records who asked: the owner, or the schedule continuing its own work."""
        if by not in ("owner", "schedule"):
            raise ValueError(f"unknown requester {by!r}")
        if kind not in ("map", "round", "plan", "goalposts", "draft", "build", "escalate", "supplement", "revise", "correct", "readmit", "readmit_answer", "breakdown", "split", "propose_acceptance", "review_current", "resume_check", "resume_author", "source_baseline", "allocate_check", "reconcile_check", "health", "mode", "measure"):
            raise ValueError(f"unknown job {kind!r}")
        from runesmith.app.build_jobs import BuildJob, PARAMETERS
        if kind in PARAMETERS:
            BuildJob(kind, params)  # Validate before creating a queued job or consuming an allocation.
        from runesmith.app.work_modes import guard_job
        guard_job(self.ws, kind)
        with self._cv:
            self._require_ready()
            if self._closing:
                raise WorkspaceError('Studio is closing; no new work was queued.')
            for job in self._jobs:                          # the same job twice in a row is one job
                if job["kind"] == kind and job["params"] == params:
                    return json.loads(json.dumps(job))
            if len(self._jobs) >= MAX_JOBS:
                raise WorkspaceError('The queue is full; inspect waiting jobs before adding more.')
            job = {"id": uuid.uuid4().hex, "kind": kind, "params": params, "queued": _now(), "by": by}
            validate_job(job)
            job = json.loads(json.dumps(job, allow_nan=False))
            try:
                self._save_queue([*self._jobs, job])  # Acknowledge only a committed intention.
            except (OSError, WorkspaceError) as error:
                self._block_storage(error)
                raise
            self._jobs.append(job)
            self._cv.notify_all()
        self._publish_state()
        return json.loads(json.dumps(job))

    def pause(self, by: str = 'owner') -> None:
        with self._cv:
            self.paused = True
            self._pause_by = by
            if self._storage_error:
                raise WorkspaceError('Control records need repair; pause is held in memory and no evidence was overwritten.')
            self._records['STUDIO_STATE.json'].write({'paused': True, 'by': by})
        self.say("Paused. Nothing new starts until you resume; the current step finishes.")
        self._publish_state()

    def resume(self) -> None:
        with self._cv:
            if self._closing:
                raise WorkspaceError('This worker is stopping. Inspect the folder handoff or restart Studio; it cannot resume.')
            self._require_ready()
            for record in self._records.values():
                record.check()
            self._records['STUDIO_STATE.json'].write({'paused': False})
            self.paused = False
            self._pause_by = None
            self._cv.notify_all()
        self.say("Resumed.")
        self._publish_state()

    def stop_current(self) -> None:
        self._stop_after_step = True
        self.say("Stopping after the current step…")
        self._publish_state()

    def snapshot(self) -> dict[str, Any]:
        settings = self.ws.settings()
        with self._cv:
            recovery = dict(self._recovery, required=True, blocked=bool(self._storage_error),
                            error=self._storage_error, waiting=len(self._jobs)) if self._recovery else None
            return {"status": "paused" if self.paused and not self.current else self.status, "detail": self.detail,
                    "since": self.since, "paused": self.paused, "current": self.current,
                    "stop_requested": bool(self.current and self._stop_after_step),
                    "queue": json.loads(json.dumps(list(self._jobs))),
                    "recovery": json.loads(json.dumps(recovery)),
                    "history": list(self.history)[::-1][:12],
                    "next_round_utc": self._next_round_utc(settings), "lines": list(self.lines)[-80:],
                    "autonomy": settings["autonomy"], "auto_work": settings["auto_work"],
                    "interval_minutes": settings["interval_minutes"]}

    # ------------------------------------------------------------------ helpers --

    def say(self, text: str, level: str = "info", **extra: Any) -> None:
        line = {"utc": _now(), "text": text, "level": level, **extra}
        self.lines.append(line)
        self.bus.publish("log", line)

    def _set(self, status: str, detail: str = "") -> None:
        self.status, self.detail, self.since = status, detail, _now()
        self._publish_state()

    def _publish_state(self) -> None:
        self.bus.publish("worker", {k: v for k, v in self.snapshot().items() if k != "lines"})

    def _on_call(self, event: dict[str, Any]) -> None:
        self.ws.record_call(event)
        model = event.get("answered_by") or event.get("model") or event.get("instrument")
        if str(model).startswith("(skipped"):              # the owner declined a chat-window request (J1-F4)
            self.say(f"You skipped the chat-window request ({event.get('role')}).", "info", kind="call")
        else:
            outcome = "answered" if event.get("ok") else f"failed ({event.get('error_kind') or 'error'})"
            self.say(f"{model} ({event.get('role')}) {outcome} in {event.get('latency_s', 0):.1f} s",
                     "info" if event.get("ok") else "warn", kind="call")
        self.bus.publish("call", {k: event.get(k) for k in ("role", "instrument", "model", "ok", "error_kind",
                                                            "latency_s", "answered_by")})

    def _next_round_utc(self, settings: dict[str, Any]) -> str | None:
        if not settings["auto_work"] or not settings["onboarded"] or self.paused:
            return None
        work = _read_json(self.ws.home / "WORK.json", {})
        last = work.get("utc")
        if not last:
            return _now()
        ended = calendar.timegm(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ"))
        wait = float(settings["interval_minutes"]) * 60
        if settings.get("full_speed") and work.get("kind") in FULL_SPEED_KINDS:
            # Full speed (J11-F21): the wait the last step earned; a round is paced by the interval as before.
            earned = work.get("wait_s")
            wait = min(wait, float(earned)) if isinstance(earned, (int, float)) and earned >= 0 else 0.0
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended + wait))

    def _full_speed_wait(self, before: dict[str, int], settings: dict[str, Any]) -> dict[str, Any]:
        """How long full speed waits after a scheduled step: not at all when a model answered (well or badly: the
        models are there, and the next step has the answer's feedback); 1, 2, 4 ... minutes, at most the interval,
        when none answered; FULL_SPEED_IDLE_S when the step called no model, as when everything waits for the owner."""
        tally = getattr(self.ws, "call_tally", None) or {}
        answered = tally.get("answered", 0) - before.get("answered", 0)
        unanswered = tally.get("unanswered", 0) - before.get("unanswered", 0)
        longest = float(settings["interval_minutes"]) * 60
        if answered > 0:
            return {"wait_s": 0, "busy_streak": 0}
        if unanswered > 0:
            streak = int(_read_json(self.ws.home / "WORK.json", {}).get("busy_streak") or 0) + 1
            return {"wait_s": min(longest, 60.0 * 2 ** min(streak - 1, 16)), "busy_streak": streak}
        return {"wait_s": min(longest, FULL_SPEED_IDLE_S), "busy_streak": 0}

    def _due(self) -> float | None:
        """Seconds until the next scheduled round, or None when nothing is scheduled."""
        nxt = self._next_round_utc(self.ws.settings())
        if nxt is None:
            return None
        return max(0.0, calendar.timegm(time.strptime(nxt, "%Y-%m-%dT%H:%M:%SZ")) - time.time())

    # --------------------------------------------------------------------- loop --

    def scheduled_job(self) -> tuple[str, dict[str, Any]] | None:
        """What a scheduled round runs now: the next configured mode (None when none is ready), a build step when
        building is on, or a round. "Run now" asks the same (journey J11-F11: it always ran a repair round, which
        never builds, and told the owner to draft a plan that already had ten milestones)."""
        from runesmith.app.work_modes import configuration, choose_next
        if configuration(self.ws)['configured']:
            mid = choose_next(self.ws)
            return None if mid is None else ('mode', {'mode': mid})
        settings = self.ws.settings()
        if settings.get('checks_autopilot') and settings['build_steps'] and settings['autonomy'] != 'observe':
            # With the check autopilot on, a ready milestone without checks gets them first, so an unattended
            # project never waits for an approval.
            from runesmith.app.acceptance_autopilot import needs_checks
            if (missing := needs_checks(self.ws)) is not None:
                return 'propose_acceptance', {'milestone': missing}
        from runesmith.app import rechecks
        if (settings['build_steps'] and settings.get('recheck_policy') == rechecks.POLICY
                and settings['autonomy'] != 'observe'):
            # The owner's setting for a draft whose checks did not finish (journey J11-G44): the one-time extension, no
            # model call, so a milestone does not stall until he presses its button.
            if (draft := rechecks.next_draft(self.ws)) is not None:
                return rechecks.KIND, {'draft_id': draft['id'], 'reason': rechecks.REASON}
        from runesmith.app import stuck
        if settings['build_steps'] and settings.get('stuck_policy') in stuck.POLICIES:
            # The owner's setting for a milestone whose tries are used up (journey J11-G43): its one more try, or its
            # breakdown, takes a turn, and the step after it builds the others, so a milestone that waits on a model
            # never holds the plan.
            if _read_json(self.ws.home / 'WORK.json', {}).get('kind') not in stuck.TURN_KINDS:
                if (turn := stuck.stuck_work(self.ws, settings['stuck_policy'])) is not None:
                    return turn
        return ('build' if settings['build_steps'] else 'round'), {}

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._closing:
                    if self._jobs and not self.paused:
                        job = self._jobs[0]  # Claim durably before removing the waiting intention.
                        break
                    due = None if self.paused else self._due()
                    if due is not None and due <= 0 and not self._jobs:
                        try:
                            choice = self.scheduled_job()
                            if choice is None:
                                self._cv.wait(timeout=30.0)
                                continue
                            kind, params = choice
                        except WorkspaceError as error:
                            self._set('blocked', str(error))
                            self._cv.wait(timeout=30.0)
                            continue
                        except Exception as error:          # never end the worker thread (review of J11-G16)
                            try:
                                (self.ws.home / 'logs').mkdir(parents=True, exist_ok=True)
                                with open(self.ws.home / 'logs' / 'worker-errors.log', 'a', encoding='utf-8', newline='\n') as stream:
                                    stream.write(f"{_now()} choosing scheduled work\n{traceback.format_exc()}\n")
                            except OSError:                 # the log is best effort (review of batch H)
                                pass
                            self._set('blocked', f'The schedule could not choose the next step ({type(error).__name__}: '
                                                 f'{str(error)[:200]}). Activity has the details.')
                            self._cv.wait(timeout=30.0)
                            continue
                        job = {"id": uuid.uuid4().hex, "kind": kind, "params": params, "queued": _now(), "by": "schedule"}
                        break
                    self._cv.wait(timeout=min(30.0, due) if due is not None else 30.0)
                else:
                    return
            try:
                self._execute(job)
            except StopRequested:
                continue  # A pause/close racing with the claim leaves the intention queued.
            except Exception as error:
                # Control-record failures must not kill the thread or retry a
                # possibly dispatched action. Keep its marker and wait for review.
                self._block_storage(error)

    def _execute(self, job: dict[str, Any], *, schedule_next=True) -> dict[str, Any]:
        if job['kind'] == 'build' and job.get('params', {}).get('author_only') is True:
            schedule_next = False
        with self._cv:
            self._require_ready()
            if self.paused or self._closing:
                raise StopRequested()
            if self.current or self._records['STUDIO_CURRENT.json'].digest:
                raise WorkspaceError('A current job already owns this worker; nothing else started.')
            for record in self._records.values():
                record.check()
            validate_job(job)
            current = dict(job, started=_now())
            self._records['STUDIO_CURRENT.json'].write(current)
            remaining = [row for row in self._jobs if row['id'] != job['id']]
            self._save_queue(remaining)
            self._jobs = deque(remaining)
            self.current = current
            self._stop_after_step = False
        started = time.monotonic()
        outcome: dict[str, Any] = {}
        calls_before = dict(getattr(self.ws, "call_tally", None) or {})
        try:
            from runesmith.app.work_modes import guard_job
            guard_job(self.ws, job['kind'])  # A switch may have changed since enqueue.
            if job['kind'] in {'plan', 'goalposts', 'draft', 'build', 'round', 'escalate', 'supplement', 'revise', 'correct', 'breakdown', 'split', 'propose_acceptance'}:
                from runesmith.app.environment_intent import require_intent
                require_intent(self.ws)
            handler = getattr(self, f"_job_{job['kind']}")
            outcome = handler(**job["params"]) or {}
            result = "done"
        except StopRequested:
            result = "stopped"
            self.say("Stopped at your request.")
        except SkippedByOwner as error:                    # the owner said no to a relay request: not a failure
            result = "skipped"
            outcome = {"summary": str(error)}
            self.say(f"{JOB_WORDS.get(job['kind'], job['kind'].replace('_', ' ').capitalize())}: {error}.")
        except Exception as error:                         # a failed job never stops the worker
            result = "failed"
            explained = type(error).__name__ in ("PlannerUnavailable", "WorkspaceError")   # already in plain words
            outcome = {"error": (str(error) if explained else f"{type(error).__name__}: {error}")[:500]}
            what = JOB_WORDS.get(job['kind'], job['kind'].replace('_', ' ').capitalize())   # not "propose_acceptance" (J2-F9)
            self.say(f"{what} did not finish: {outcome['error']}", "error")
            (self.ws.home / "logs").mkdir(parents=True, exist_ok=True)
            with open(self.ws.home / "logs" / "worker-errors.log", "a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"{_now()} {job['kind']}\n{traceback.format_exc()}\n")
        finally:
            # A scheduled check request moves the schedule on like a build (journey J11-B9: it did not, so while every
            # free model was busy the autopilot asked again as soon as the last request failed, six times in 2.5 min).
            if job['kind'] in {'build', 'mode'} or (job['kind'] in ('propose_acceptance', 'escalate', 'split') and job.get('by') == 'schedule'):
                work = {'utc':_now(), 'kind':job['kind'], 'result':result}
                try:
                    settings = self.ws.settings()
                    if settings.get('full_speed'):
                        work.update(self._full_speed_wait(calls_before, settings))
                except Exception:                    # the schedule then keeps its interval (never stop the worker)
                    pass
                _write_json(self.ws.home / 'WORK.json', work)
            done = dict(job, finished=_now(), seconds=round(time.monotonic() - started, 1), result=result,
                        outcome={k: v for k, v in outcome.items() if k in ("summary", "error", "detail", "objects",
                                                                            "opportunities", "served", "accepted", "draft", "milestone", "advanced",
                                                                            "replan_needed", "cause")})
            with self._cv:
                last = self.history[-1] if self.history else None
                if _same_waiting_round(last, done):    # one row, counted: not 30 rows pushing real work out (J2-F20)
                    self.history.pop()
                    done = dict(done, repeats=int(last.get('repeats') or 1) + 1,
                                first_finished=last.get('first_finished') or last.get('finished'))
                self.history.append(done)
                self._records['STUDIO_JOBS.json'].write(list(self.history))
                self._records['STUDIO_CURRENT.json'].remove()
                self.current = None
            self._set("idle", "")
            self.bus.publish("job", done)
            from runesmith.app.work_modes import configuration
            try:
                legacy = not configuration(self.ws)['configured']
            except WorkspaceError:
                legacy = False  # Keep the failure receipt; malformed policy cannot restart work.
            if (schedule_next and legacy and job['kind'] == 'build' and outcome.get('advanced') and self.ws.settings()['auto_work']
                    and not self.paused and not self._closing and not self._stop_after_step):
                # What the schedule would run now: checks first for a ready milestone without them (journey J11-F25:
                # the next milestone was drafted before it had checks, a model call for a draft that must wait).
                try:
                    kind, params = self.scheduled_job() or ('build', {})
                except Exception:                     # choosing never stops the worker (review of J11-G16)
                    kind, params = 'build', {}
                self.enqueue(kind, by='schedule', **params)
            if (schedule_next and legacy and job['kind']=='build' and outcome.get('replan_needed') and self.ws.settings()['auto_work']
                    and not self.paused and not self._closing and not self._stop_after_step):
                if not self._breakdown_waiting(outcome['milestone']) and not self._stuck_setting_first(outcome['milestone']):
                    self.enqueue('breakdown', by='schedule', milestone=outcome['milestone'])    # one proposal waits: no repeat (J2-F16)
        return dict(done, outcome=outcome)

    # --------------------------------------------------------------------- jobs --

    def _stuck_setting_first(self, milestone: str) -> bool:
        """The owner's setting for used-up tries (J11-G43) goes before the proposal of smaller steps: it makes the one
        more try, and for "one more try, then break it down" the breakdown too, itself."""
        try:
            from runesmith.app.stuck import defers_breakdown
            return defers_breakdown(self.ws, milestone, self.ws.settings().get('stuck_policy'))
        except Exception:                          # choosing never stops the worker
            return False

    def _breakdown_waiting(self, milestone: str) -> bool:
        """No scheduled breakdown: one proposal already waits (J2-F16), or the milestone already has smaller steps, which
        a breakdown refuses (J2-F31: it failed every 5 minutes with "already has prerequisite steps")."""
        if any(m.get('parent_id') == milestone for m in (self.ws.plan() or {}).get('milestones', [])):
            return True
        return any(_read_json(p, {}).get('milestone') == milestone and _read_json(p, {}).get('state') == 'proposed'
                   for p in (self.ws.home / 'breakdowns').glob('*.json'))

    def _work_checkpoint(self):
        if self._stop_after_step or self._closing or self.paused:
            raise StopRequested()
        from runesmith.app.work_modes import checkpoint, guard_job
        if self.current: guard_job(self.ws, self.current['kind'])
        checkpoint(self.ws)
        if hasattr(self, '_support_report_revision'):
            from runesmith.app.support_reports import checkpoint as reports_checkpoint
            reports_checkpoint(self.ws, self._support_report_revision)

    def _job_mode(self, mode: str) -> dict[str, Any]:
        from runesmith.app.work_modes import run
        self._work_checkpoint()
        result = run(self, mode)
        self.say(result['summary']); self.bus.publish('mission', {})
        return result

    def _job_measure(self, measurement: str) -> dict[str, Any]:
        from runesmith.app.measurements import measure
        self._work_checkpoint()
        from runesmith.app.environment_intent import require_intent
        require_intent(self.ws)
        receipt = measure(self.ws, measurement)
        self.bus.publish('mission', {})
        from runesmith.app.measurements import definitions
        name = next((i['name'] for i in definitions(self.ws)['items'] if i['id'] == measurement), measurement)
        if receipt['status'] == 'measured':        # the number itself, in plain words (journey J5)
            where = f" from {receipt['source_file']}" if receipt.get('source_file') else ''
            item = next((i for i in definitions(self.ws)['items'] if i['id'] == measurement), {})
            number = (f"{receipt['value'] * 100:.1f}%" if item.get('aggregation') == 'ratio'
                      else f"{receipt['value']:g} {receipt.get('unit') or ''}".rstrip())
            said = f"{name}: {number}{where}. No model call or project change."
        else:
            said = f"{name}: {receipt['status']}" + (f" ({receipt['detail']})" if receipt.get('detail') else '') + '.'
        return {'summary': said, 'receipt': receipt['id']}

    def _job_map(self, probe: bool | None = None) -> dict[str, Any]:
        settings = self.ws.settings()
        probing = settings["probe_tests"] if probe is None else probe
        self._set("mapping", "Running tests on throwaway copies to measure them" if probing else "Reading the folder")
        self.say("Mapping the folder" + (" and measuring code objects (tests run on throwaway copies)" if probing else ""))
        t0 = time.monotonic()
        env_map = self.ws.map_environment(probe=probing)
        self.ws.self_map(refresh=True)
        kinds: dict[str, int] = {}
        for o in env_map["objects"]:
            kinds[o["kind"]] = kinds.get(o["kind"], 0) + 1
        text = ", ".join(f"{n} {KIND_WORDS.get(k, (k, k + 's'))[n != 1]}" for k, n in sorted(kinds.items())) or "no objects yet"
        self.say(f"Mapped in {time.monotonic() - t0:.1f} s: {text}.")
        self.bus.publish("map", {"objects": len(env_map["objects"]), "digest": env_map["map_digest"]})
        return {"objects": len(env_map["objects"]), "summary": text}

    def _job_health(self) -> dict[str, Any]:
        self._set("checking", "Checking the setup")
        rows = self.ws.health(network=True)
        bad = [r for r in rows if r["ok"] is False]
        self.say(f"Health check: {len(rows) - len(bad)} of {len(rows)} fine" + (f"; {len(bad)} need attention" if bad else "."))
        self.bus.publish("health", {"rows": rows})
        return {"summary": f"{len(bad)} problems"}

    def _job_plan(self) -> dict[str, Any]:
        from runesmith.app.planner import draft_plan
        self._set("planning", "Drafting a plan from your brief and the map")
        self.say("Asking the planner model for a plan from your brief, goals, blueprints and the map")
        plan = draft_plan(self.ws, self.ws.router(on_call=self._on_call, backoff_s=(5, 20, 60)),
                          checkpoint=self._work_checkpoint,
                          automatic=bool(getattr(self.ws, '_active_work_mode', None)))
        self.say(f"Plan v{plan['version']} drafted: {len(plan['milestones'])} milestones on "
                 f"{len(plan['tracks'])} tracks. It is yours to edit.")
        self.bus.publish("plan", {"version": plan["version"]})
        return {"summary": f"{len(plan['milestones'])} milestones"}

    def _job_goalposts(self) -> dict[str, Any]:
        from runesmith.app.goalposts import draft_goalposts
        def checkpoint():
            self._work_checkpoint()
            if self._stop_after_step or self._closing or self.paused:
                raise StopRequested()
        self._set("planning", "Proposing measurable goalposts from the evidence")
        result = draft_goalposts(self.ws, self.ws.router(on_call=self._on_call, backoff_s=()),
                                 checkpoint=checkpoint)
        self.bus.publish("goalposts", {"version": result["version"]})
        return {"summary": f"{len(result['goalposts'])} model-proposed goalposts; no outcomes marked achieved."}

    def _job_draft(self, milestone: str | None = None) -> dict[str, Any]:
        from runesmith.app.planner import draft_files
        self._set("drafting", "Writing first files for a milestone")
        self.say("Asking the planner model for the first files of a milestone (a draft you review)")
        draft = draft_files(self.ws, self.ws.router(on_call=self._on_call, backoff_s=(5, 20, 60)), milestone)
        self.say(f"Draft ready: {draft['title']} ({len(draft['files'])} files). Nothing is written until you apply it.")
        self.bus.publish("work", {"draft": draft["id"]})
        from runesmith.app.building import status as checking
        if checking(self.ws)["enabled"] and self.ws.settings()["autonomy"] != "observe":
            # Journey J1-F7: with checking on, a fresh draft waited unverified until Recheck. The same recheck runs
            # now, under the same guards: no model call, and nothing is applied.
            checked = self._run_build_job("build", "Checking the fresh draft on a throwaway copy; no model call or apply",
                                          draft_id=draft["id"], author_only=False)
            return {"summary": checked["summary"], "draft": draft["id"]}
        return {"summary": draft["title"], "draft": draft["id"]}

    def _job_breakdown(self,milestone: str) -> dict[str, Any]:
        from runesmith.app.breakdowns import propose_breakdown
        def checkpoint():
            self._work_checkpoint()
            if self._stop_after_step or self._closing or self.paused:raise StopRequested()
        self._set('planning','Breaking down a milestone from its recorded evidence')
        proposal=propose_breakdown(self.ws,self.ws.router(on_call=self._on_call,backoff_s=()),
                                   milestone,checkpoint=checkpoint)
        self.bus.publish('plan',{'breakdown':proposal['id']})
        return {'summary':f"Proposed {len(proposal['steps'])} prerequisites for {milestone}; original goal unchanged. Review under Goals & plan."}

    def _job_split(self, milestone: str) -> dict[str, Any]:
        """A stuck milestone broken down by the owner's setting (journey J11-G43), once."""
        from runesmith.app import stuck

        def checkpoint():
            self._work_checkpoint()
            if self._stop_after_step or self._closing or self.paused: raise StopRequested()
        self._set('planning', 'Breaking down a stuck milestone by your setting')
        result = stuck.split(self.ws, self.ws.router(on_call=self._on_call, backoff_s=()), milestone, checkpoint=checkpoint)
        self.say(result['summary'], 'warn')
        self.bus.publish('plan', {'breakdown': milestone})
        return result

    def _job_propose_acceptance(self, milestone: str) -> dict[str, Any]:
        from runesmith.app.acceptance_proposals import REQUEST_FAILURES, clear_request_failures, note_request_failure, propose
        def checkpoint():
            self._work_checkpoint()
            if self._stop_after_step or self._closing or self.paused: raise StopRequested()
        autopilot_on = bool(self.ws.settings().get('checks_autopilot'))       # read once: wording and decision agree
        self._set('planning', 'Proposing acceptance checks for a milestone ('
                  + ('the check autopilot reviews them' if autopilot_on else 'you approve them') + ')')   # J11-F13
        self.say('Asking the planner model to propose acceptance checks from the milestone’s own words')
        try:
            proposal = propose(self.ws, self.ws.router(on_call=self._on_call, backoff_s=()), milestone, checkpoint=checkpoint)
        except (StopRequested, SkippedByOwner):
            raise
        except Exception as error:
            # A scheduled request that failed is counted (journey J11, review of batch CC): after two on the same milestone
            # and source the schedule stops asking, so a request whose answer is not usable cannot hold every build back
            # for ever. The owner's own request is never counted, and never held back.
            if (self.current or {}).get('by') == 'schedule':
                try:
                    failures = note_request_failure(self.ws, milestone, error)
                except Exception:                    # the record is a convenience: never hide the failure itself
                    failures = None
                if failures and type(error).__name__ in ('PlannerUnavailable', 'WorkspaceError'):
                    error.args = (f"{error} " + (f"That was failed request {failures['count']} of {REQUEST_FAILURES} for "
                                                 'these checks, so Runesmith stops asking for them by itself and builds other '
                                                 'work until the project’s files or this milestone change.'
                                                 if failures['count'] >= REQUEST_FAILURES else
                                                 f"(Failed request {failures['count']} of {REQUEST_FAILURES}; Runesmith asks "
                                                 'once more.)'),)
            raise
        clear_request_failures(self.ws, milestone)          # answered: the count of failures ends
        self.bus.publish('plan', {'acceptance': proposal['id']})
        dry = proposal.get('dry_run') or {}
        failing = f"{(dry.get('failures') or 0) + (dry.get('errors') or 0)} of {dry['ran']}" if dry.get('ran') else 'They'
        trial = {'fails_now': f' {failing} fail on today’s project, as expected before it is built.',   # J2-F10: the counts
                 'passes_now': ' Note: they already pass on today’s project.',
                 'broken': ' Note: they could not run on today’s project.'}.get((proposal.get('dry_run') or {}).get('verdict'), '')
        missing = sum(1 for c in proposal['checks'] if c.get('missing_input'))
        if missing and dry.get('verdict') == 'fails_now':        # J11-F10: those fail on a correct build too
            trial = (f' {failing} fail on today’s project; {missing} of the checks use a file nothing creates, so they '
                     'would fail on a correct build too.')
        revised = ' Revised once after Runesmith tried and read them.' if proposal.get('revision') and not proposal['revision'].get('error') else ''
        head = f"Proposed {len(proposal['checks'])} acceptance checks for {milestone}.{revised}{trial}"
        if autopilot_on and proposal.get('state') == 'proposed':
            from runesmith.app import acceptance_autopilot
            self._set('planning', 'The check autopilot is reviewing the proposed checks')
            verdict = acceptance_autopilot.review(self.ws, milestone, proposal)
            done, carried_out = acceptance_autopilot.act(self.ws, milestone, proposal, verdict)
            self.say(done)
            if carried_out == 'turn_down' and not (self.paused or self._closing or self._stop_after_step):
                self.enqueue('propose_acceptance', by='schedule', milestone=milestone)
            settings = self.ws.settings()
            if (carried_out == 'approve' and settings['build_steps'] and settings['auto_work']
                    and not (self.paused or self._closing or self._stop_after_step)):
                try:
                    self.enqueue('build', by='schedule')     # approved checks build at once (J11-F14)
                except (WorkspaceError, OSError) as error:  # e.g. building was switched off meanwhile: the
                    self.say(f'The next build waits for the schedule: {error}')   # approval stands (review)
            self.bus.publish('plan', {'acceptance': proposal['id']})
            return {'summary': f'{head} {done}'}
        return {'summary': f"{head} Read and approve them under Goals & plan; nothing is used until you do."}

    def _job_build(self, draft_id: str | None = None, author_only: bool = False,
                   milestone_id: str | None = None) -> dict[str, Any]:
        return self._run_build_job('build',
            'Rechecking saved files; no model call or apply' if draft_id is not None else
            ('Drafting one bounded milestone step; no checks or apply' if author_only else
             'Drafting and checking one bounded milestone step'), draft_id=draft_id, author_only=author_only,
            milestone_id=milestone_id)

    def _run_build_job(self, kind, detail, **params):
        from runesmith.app.build_jobs import BuildJob, execute_build_job
        request = BuildJob(kind, params)
        self._set('building', detail)
        result = execute_build_job(self.ws, request, checkpoint=self._work_checkpoint,
            on_call=self._on_call, active_job=(self.current or {}).get('id'))
        self.say(result['summary'])
        self.bus.publish('work', {'draft': result.get('draft')})
        self.bus.publish('plan', {'milestone': result.get('milestone')})
        return result

    def _job_resume_author(self,request_id: str) -> dict[str,Any]:
        return self._run_build_job('resume_author', 'Retrieving a saved model answer; no new inference', request_id=request_id)

    def _job_revise(self, draft_id: str, quote_id: str, instrument: str, operation_id: str, reason: str) -> dict[str, Any]:
        return self._run_build_job('revise', 'Authoring one revision from the existing allowance; no checks or apply',
            draft_id=draft_id, quote_id=quote_id, instrument=instrument, operation_id=operation_id, reason=reason)

    def _job_source_baseline(self, reason: str) -> dict[str, Any]:
        return self._run_build_job('source_baseline', 'Measuring current source only; no candidate checks or inference', reason=reason)

    def _job_allocate_check(self, draft_id: str, quote_id: str, reason: str) -> dict[str, Any]:
        return self._run_build_job('allocate_check', 'Running one separately allocated full verification; no inference',
                                   draft_id=draft_id, quote_id=quote_id, reason=reason)

    def _job_reconcile_check(self, draft_id: str, quote_id: str, reason: str) -> dict[str, Any]:
        return self._run_build_job('reconcile_check', 'Rechecking a linked preflight refusal once; no inference or apply',
                                   draft_id=draft_id, quote_id=quote_id, reason=reason)

    def _job_resume_check(self,draft_id: str,reason: str) -> dict[str,Any]:
        # The schedule runs the extension when the owner's setting says so (journey J11-G44): once per draft whatever
        # happens, and said as such.
        by_setting = (self.current or {}).get('by') == 'schedule'
        if not by_setting:
            return self._run_build_job('resume_check', 'One retained-candidate check extension; no inference', draft_id=draft_id, reason=reason)
        from runesmith.app import automatic, rechecks
        title = rechecks.mark(self.ws, draft_id)
        try:
            result = self._run_build_job('resume_check', 'One retained-candidate check extension; no inference', draft_id=draft_id, reason=reason)
        except WorkspaceError as error:
            said = f'“{title}”: a draft’s checks did not finish. By your setting, Runesmith tried to run them once more, but could not: {error} It waits for you.'
            automatic.record(self.ws, said, kind='recheck', draft=draft_id)
            self.say(said, 'warn')
            raise
        said = (f'“{title}”: a draft’s checks did not finish (they ran out of time). By your setting, Runesmith ran them once more '
                f'with a longer limit and no model call: {result["summary"]}')
        automatic.record(self.ws, said, kind='recheck', draft=draft_id)
        self.say(said, 'warn')
        return result

    def _job_readmit(self, escalation: str) -> dict[str, Any]:
        return self._run_build_job('readmit', 'Checking a kept answer again; no model call', escalation=escalation)

    def _job_readmit_answer(self, attempt: str) -> dict[str, Any]:
        return self._run_build_job('readmit_answer', 'Checking a kept answer again; no model call', attempt=attempt)

    def _job_correct(self, attempt: str) -> dict[str, Any]:
        return self._run_build_job('correct', 'Correcting one retained rejected answer under its original scope', attempt=attempt)

    def _job_review_current(self,milestone: str) -> dict[str,Any]:
        return self._run_build_job('review_current', 'Checking existing project files; no model call or source edits', milestone=milestone)

    def _job_supplement(self,draft_id: str,reason: str,instrument: str,author_only: bool=False) -> dict[str,Any]:
        return self._run_build_job('supplement', 'One authorized revision after a clarified requirement; spent attempts retained',
                                   draft_id=draft_id, reason=reason, instrument=instrument, author_only=author_only)

    def _job_escalate(self) -> dict[str, Any]:
        # The schedule gives the one more try when the owner's setting says so (journey J11-G43): said as such.
        by_setting = (self.current or {}).get('by') == 'schedule'
        from runesmith.app import stuck
        milestone = stuck.next_escalation(self.ws) if by_setting else None
        result = self._run_build_job('escalate', 'Using one alternate author after the bounded ordinary attempts')
        if by_setting and milestone:
            from runesmith.app import automatic
            said = (f'“{milestone["title"]}” had used up its tries. By your setting, Runesmith gave it one more try with '
                    f'another model: {result["summary"]}')
            automatic.record(self.ws, said, kind='one_more_try', milestone=milestone['id'])
            self.say(said, 'warn')
        return result

    def _job_round(self) -> dict[str, Any]:
        from runesmith.app.work_modes import prompt_context
        from runesmith.app.support_reports import view
        work_policy = json.dumps(prompt_context(self.ws), ensure_ascii=False)
        self._job_map(probe=False)
        self._support_report_revision = view(self.ws)['revision']
        try:
            self._work_checkpoint()
            return self._repair_round(work_policy)
        finally:
            del self._support_report_revision

    def _repair_round(self, work_policy: str) -> dict[str, Any]:
        from runesmith.discover import discover
        from runesmith.loop import run_loop
        from runesmith.report import write_report
        from runesmith.steward import opportunity_id
        ws, settings = self.ws, self.ws.settings()
        env_map = ws.environment_map() or {"objects": []}
        objects = [o for o in env_map["objects"] if o["kind"] == "python_repository"]
        statuses: dict[str, str] = {}
        details: dict[str, dict[str, Any]] = {}
        self._round_details = details
        if settings["autonomy"] == "observe":
            self.say("Observe mode: mapped and watching. Switch to Propose in Settings to let Runesmith work.")
            return self._finish_round([], statuses, {}, "observed")
        if not objects:
            # Honest: no tests ran, so this round cannot say that nothing is broken (journey J3).
            self.say("No Python project with tests was found here, so no tests were run. To build something new, "
                     "draft a plan under Goals & plan.")
            return self._finish_round([], statuses, {}, "no project with tests found")
        # The repair organ (the measured path) needs a src/ folder and pytest. Anything else is measured first, with
        # Python's own unittest and no model at all, and offered "Fix the failing tests", which works for any project
        # (J3); only the organ's own projects need a Worker model (J7).
        organ_ok = importlib.util.find_spec("pytest") is not None
        measured_only = [o for o in objects if not organ_ok or not (Path(o["path"]) / "src").is_dir()]
        organ_objects = [o for o in objects if o not in measured_only]
        fix_offered = False
        for obj in measured_only:
            flat = not (Path(obj["path"]) / "src").is_dir()
            why =(f"{obj['name']} keeps its code at the top, not in the src/ folder Runesmith's repair organ needs"
                   if flat else "Runesmith's repair organ needs pytest, which is not installed here")
            if not settings["probe_tests"]:
                statuses[obj["name"]] = "not measured: running this project's tests is off"
                self.say(f"Runesmith has not run {obj['name']}'s tests, so it cannot tell whether anything is "
                         "broken. Turn on “Run this project’s tests while mapping” to let it check them.")
                continue
            from runesmith.app.fix_tests import measure
            self._set("discovering", f"Running {obj['name']}'s tests on a throwaway copy")
            measured = measure(ws, Path(obj["path"]), obj["name"])
            failing = measured["failures"] + measured["errors"]
            statuses[obj["name"]] = f"measured: {failing} of {measured['ran']} tests fail"
            if failing:
                fix_offered = True
                self.say(f"{failing} of {measured['ran']} tests fail in {obj['name']}. {why}: use “Fix the failing "
                         "tests” on the Overview, which works for any project.", "warn")
            elif measured["ran"]:
                self.say(f"All {measured['ran']} tests pass in {obj['name']}.", "success")
            else:
                self.say(f"No tests ran in {obj['name']}: Runesmith looks for them in a tests/ folder.")
        if not organ_objects:
            # Not "nothing new" when the tests were not run at all (journey J6-F2).
            unmeasured = any(status.startswith("not measured") for status in statuses.values())
            return self._finish_round([], statuses, {}, "tests fail: fix offered" if fix_offered
                                      else "tests not run: running this project's tests is off" if unmeasured
                                      else "nothing new")
        ready = ws.ready()
        if not ready["repair"]:
            self.say("No Worker model is set up, so Runesmith can map but not repair. Add one under Thinking power.", "warn")
            self.bus.publish("needs", {"what": "inference", "role": "repair"})
            return self._finish_round([], statuses, {}, "no worker model")
        config = ws.config()
        down: dict[str, str] = {}
        for name in ready["usable"]["repair"]:
            ok, detail = reachable(config["instruments"][name])
            if not ok:
                down[name] = detail
        if len(down) == len(ready["usable"]["repair"]):
            name, detail = next(iter(down.items()))
            self.say(f"No Worker model is reachable ('{name}': {detail}). Start it, or pick another under Thinking power.",
                     "warn")
            self.bus.publish("needs", {"what": "reachability", "instrument": name, "detail": detail})
            return self._finish_round([], statuses, {}, "worker model unreachable")
        for name, detail in down.items():
            self.say(f"Skipping the Worker model '{name}' this round: {detail}. Its fallbacks take over.", "warn")
        served_path = ws.home / "served_opportunities.json"
        served: dict[str, str] = _read_json(served_path, {})
        fresh: list[dict[str, Any]] = []
        for obj in organ_objects:
            self._set("discovering", f"Running {obj['name']}'s tests on a throwaway copy")
            self.say(f"Running {obj['name']}'s tests on a throwaway copy")
            found = discover(Path(obj["path"]), scratch=ws.home / "scratch")
            statuses[obj["name"]] = found["status"]
            if found.get("detail"):
                details[obj["name"]] = {"detail": found["detail"], "triage": found.get("triage")}
            new = 0
            for opportunity in found["opportunities"]:
                oid = opportunity_id(opportunity)
                if oid in served:
                    continue
                notes = ws.notes_for_object(obj["name"])
                if notes:
                    opportunity["issue"] = opportunity["issue"] + "\n\n" + notes
                opportunity['issue'] += '\n\nWORKSPACE GUIDANCE AND WORK POLICY:\n' + work_policy
                from runesmith.app.support_reports import packet
                evidence = packet(ws, obj['name'], expected=obj)
                if evidence['included']:
                    # Keep restricted support context out of the generic issue
                    # stored for learning. The run loop adds it only to this
                    # repair and excludes the resulting task from reuse/trials.
                    opportunity['support_evidence'] = evidence
                    ws.ledger.append('support_report.packet_selected', {
                        'opportunity': oid, 'object': obj['name'], 'target_path': obj['path'],
                        'reports': [{'id': r['id'], 'source_sha256': r['source_sha256']} for r in evidence['included']],
                        'omitted': evidence['omitted'],
                        'scope': 'Selected for repair context; not proof a provider was called or the report was resolved.'})
                fresh.append(dict(opportunity, id=oid, object=obj["name"]))
                new += 1
            label = {"green": "all tests pass", "failing": f"{len(found['opportunities'])} failing test file(s)",
                     "timed_out": "the test run timed out",
                     "error_without_failures": "the tests could not run"
                     + (f" ({found['detail']})" if found.get("detail") else "")
                     + (f": {found['triage']['reason']}" if found.get("triage") else "")
                     }.get(found["status"], found["status"].replace("_", " "))
            self.say(f"{obj['name']}: {label}" + (f"; {new} new to work on" if new else ""))
            self._work_checkpoint()
        summary: dict[str, Any] = {}
        consumed = 0
        if fresh:
            self._set("working", f"Working on {len(fresh)} opportunity(ies)")
            self.say(f"Working on {len(fresh)} opportunity(ies). Fixes become proposals; your files are not touched.")

            def on_step(step: dict[str, Any]) -> None:
                nonlocal consumed
                if step.get("lane") in ("object", "skipped"):
                    consumed += 1
                self._report_step(step)
                self.bus.publish("step", {k: v for k, v in step.items() if isinstance(v, (str, int, float, bool))
                                          or v is None})
                self._work_checkpoint()

            loop_settings = {"min_experience": int(settings["min_experience"]) if settings["kaizen"] else 10**9,
                             "kaizen_every": int(settings["kaizen_every"]),
                             "trial_settings": {"look_every": 10, "min_per_arm": 10, "max_per_arm": 40}}
            try:
                summary = run_loop(home=ws.home, opportunities=fresh, seed=ws.seed(),
                                   router=ws.router(on_call=self._on_call, skip=set(down)), owner_notes=ws.notes_for_self(),
                                   on_step=on_step, **loop_settings)
                consumed = len(fresh)
            finally:
                for opportunity in fresh[:consumed]:
                    served[opportunity["id"]] = _now()
                _write_json(served_path, served)
        elif not fix_offered:
            self.say("Nothing new to work on this round.")
        write_report(ws.home)
        return self._finish_round(fresh[:consumed] if fresh else [], statuses, summary,
                                  "worked" if fresh else "tests fail: fix offered" if fix_offered else "nothing new")

    def _report_step(self, step: dict[str, Any]) -> None:
        lane = step.get("lane")
        if lane == "object":
            status = ATTEMPT_WORDS.get(step.get("status"), str(step.get("status") or "").replace("_", " "))
            arm = f" (trial arm: {step['trial_arm']})" if step.get("trial_arm") else ""
            self.say(f"Repair attempt {step.get('key')}: {status}{arm}", "success" if step.get("status") == "public_pass" else "info")
        elif lane == "subject":
            decision = str(step.get("decision") or "").replace("_", " ")
            self.say(f"Kaizen step: Runesmith tried to improve its own repair organ: {decision}",
                     "success" if step.get("generation") else "info")
        elif lane == "skipped":
            self.say(f"Skipped (no source edit can fix it): {step.get('reason')}", "warn")

    def _finish_round(self, served: list[dict[str, Any]], statuses: dict[str, str], summary: dict[str, Any],
                      outcome: str) -> dict[str, Any]:
        ws = self.ws
        work = {"utc": _now(), "outcome": outcome, "objects": statuses, "details": getattr(self, "_round_details", {}),
                "opportunities": [{"id": o["id"], "object": o.get("object"), "failing_tests": o["failing_tests"],
                                   "triage": o.get("triage"), "issue": o["issue"][:1200]} for o in served],
                "summary": {"outcome": outcome, "served": len(served),
                            "accepted": summary.get("strict_successes", 0), "kaizen_steps": summary.get("subject_steps", 0),
                            "skipped_environment": summary.get("skipped_environment", 0),
                            "frozen": summary.get("frozen", []), "trials": len(summary.get("trials", []))}}
        _write_json(ws.home / "WORK.json", work)
        ws.self_map(refresh=True)
        ws.ledger.append("studio.round", work["summary"])
        waiting = ws.work()["counts"].get("waiting", 0)
        if served:
            self.say(f"Round done: {len(served)} served, {work['summary']['accepted']} accepted by the judge; "
                     f"{waiting} proposal(s) wait for your review.", "success" if work["summary"]["accepted"] else "info")
        self.bus.publish("round", work["summary"])
        self.bus.publish("work", {"waiting": waiting})
        return {"summary": outcome, "served": len(served), "accepted": work["summary"]["accepted"]}

    # ------------------------------------------------------------------- watcher --

    def _watch_manual(self) -> None:
        """Tell the page when a chat-relay request is waiting for the owner, and when it is answered."""
        while not self._closing:
            try:
                self._check_manual()
            except Exception:                              # never let the watcher die on a half-written file
                pass
            with self._cv:
                if not self._closing:
                    self._cv.wait(timeout=3.0)

    def _check_manual(self) -> None:
        # Which requests, not how many (journey J2-B4): an answer and the revision request that followed it
        # within one poll left the count at 1, so the page never heard of the new request.
        waiting = self.ws.manual_waiting_ids()
        if waiting != self._manual_seen:
            fresh = [r for r in waiting if r not in (self._manual_seen or [])]
            self._manual_seen = waiting
            if fresh:
                self.say("A request is waiting for you to relay it to a chat model (Thinking power, Chat relay).", "warn")
            self.bus.publish("manual", {"waiting": len(waiting), "new": len(fresh)})


def dump_json(value: Any) -> str:
    return json.dumps(value, default=str)
