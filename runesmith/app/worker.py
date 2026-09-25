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
import json
import queue
import threading
import time
import traceback
import uuid
from collections import deque
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from runesmith.app.planner import SkippedByOwner
from runesmith.app.workspace import Workspace, _read_json, _write_json


KIND_WORDS = {"python_repository": ("Python project", "Python projects"), "node_repository": ("Node project", "Node projects"),
              "document_collection": ("document collection", "document collections"), "website": ("website", "websites"),
              "folder": ("folder", "folders"),
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


class Worker:
    def __init__(self, ws: Workspace, bus: EventBus) -> None:
        self.ws, self.bus = ws, bus
        self._jobs: deque[dict[str, Any]] = deque()
        self._cv = threading.Condition()
        self._closing = False
        self._stop_after_step = False
        self.paused = bool(_read_json(ws.home / "STUDIO_STATE.json", {}).get("paused"))
        self.current: dict[str, Any] | None = None
        self.status, self.detail, self.since = "idle", "", _now()
        self.history: deque[dict[str, Any]] = deque(_read_json(ws.home / "STUDIO_JOBS.json", [])[-30:], maxlen=30)
        self.lines: deque[dict[str, Any]] = deque(maxlen=300)
        self._manual_seen = -1
        self._thread = threading.Thread(target=self._run, name="runesmith-worker", daemon=True)
        self._watch = threading.Thread(target=self._watch_manual, name="runesmith-watch", daemon=True)

    # ------------------------------------------------------------------ control --

    def start(self) -> None:
        self._recover()
        self._thread.start()
        self._watch.start()

    def _recover(self) -> None:
        """After the Studio was closed mid-job: record the interrupted job, and set aside relay requests nobody waits for."""
        marker = self.ws.home / "STUDIO_CURRENT.json"
        interrupted = _read_json(marker, None)
        if interrupted:
            self.history.append(dict(interrupted, finished=_now(), result="interrupted",
                                     outcome={"summary": "the Studio was closed while this ran; run it again"}))
            _write_json(self.ws.home / "STUDIO_JOBS.json", list(self.history))
            marker.unlink(missing_ok=True)
            self.say(f"The last {interrupted['kind']} was interrupted when the Studio closed. Run it again when you like.",
                     "warn")
        orphaned = self.ws.set_aside_orphaned_requests()
        if orphaned:
            self.say(f"Set aside {orphaned} chat-relay request(s) from before the restart: nothing waits for them now.",
                     "warn")

    def close(self) -> None:
        with self._cv:
            self._closing = True
            self._stop_after_step = True
            self._cv.notify_all()

    def enqueue(self, kind: str, **params: Any) -> dict[str, Any]:
        if kind not in ("map", "round", "plan", "draft", "health"):
            raise ValueError(f"unknown job {kind!r}")
        with self._cv:
            for job in self._jobs:                          # the same job twice in a row is one job
                if job["kind"] == kind and job["params"] == params:
                    return job
            job = {"id": uuid.uuid4().hex[:8], "kind": kind, "params": params, "queued": _now(), "by": "owner"}
            self._jobs.append(job)
            self._cv.notify_all()
        self._publish_state()
        return job

    def pause(self) -> None:
        self.paused = True
        _write_json(self.ws.home / "STUDIO_STATE.json", {"paused": True})
        self.say("Paused. Nothing new starts until you resume; the current step finishes.")
        self._publish_state()

    def resume(self) -> None:
        self.paused = False
        _write_json(self.ws.home / "STUDIO_STATE.json", {"paused": False})
        with self._cv:
            self._cv.notify_all()
        self.say("Resumed.")
        self._publish_state()

    def stop_current(self) -> None:
        self._stop_after_step = True
        self.say("Stopping after the current step…")

    def snapshot(self) -> dict[str, Any]:
        settings = self.ws.settings()
        return {"status": "paused" if self.paused and not self.current else self.status, "detail": self.detail,
                "since": self.since, "paused": self.paused, "current": self.current,
                "queue": list(self._jobs), "history": list(self.history)[::-1][:12],
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
        outcome = "answered" if event.get("ok") else f"failed ({event.get('error_kind') or 'error'})"
        self.say(f"{model} ({event.get('role')}) {outcome} in {event.get('latency_s', 0):.1f} s",
                 "info" if event.get("ok") else "warn", kind="call")
        self.bus.publish("call", {k: event.get(k) for k in ("role", "instrument", "model", "ok", "error_kind",
                                                            "latency_s", "answered_by")})

    def _next_round_utc(self, settings: dict[str, Any]) -> str | None:
        if not settings["auto_work"] or not settings["onboarded"] or self.paused:
            return None
        last = _read_json(self.ws.home / "WORK.json", {}).get("utc")
        if not last:
            return _now()
        ended = calendar.timegm(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ"))
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended + float(settings["interval_minutes"]) * 60))

    def _due(self) -> float | None:
        """Seconds until the next scheduled round, or None when nothing is scheduled."""
        nxt = self._next_round_utc(self.ws.settings())
        if nxt is None:
            return None
        return max(0.0, calendar.timegm(time.strptime(nxt, "%Y-%m-%dT%H:%M:%SZ")) - time.time())

    # --------------------------------------------------------------------- loop --

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._closing:
                    if self._jobs and not self.paused:
                        job = self._jobs.popleft()
                        break
                    due = None if self.paused else self._due()
                    if due is not None and due <= 0 and not self._jobs:
                        job = {"id": uuid.uuid4().hex[:8], "kind": "round", "params": {}, "queued": _now(),
                               "by": "schedule"}
                        break
                    self._cv.wait(timeout=min(30.0, due) if due is not None else 30.0)
                else:
                    return
            self._execute(job)

    def _execute(self, job: dict[str, Any]) -> None:
        self.current = dict(job, started=_now())
        _write_json(self.ws.home / "STUDIO_CURRENT.json", self.current)
        self._stop_after_step = False
        started = time.monotonic()
        outcome: dict[str, Any] = {}
        try:
            handler = getattr(self, f"_job_{job['kind']}")
            outcome = handler(**job["params"]) or {}
            result = "done"
        except StopRequested:
            result = "stopped"
            self.say("Stopped at your request.")
        except SkippedByOwner as error:                    # the owner said no to a relay request: not a failure
            result = "skipped"
            outcome = {"summary": str(error)}
            self.say(f"{job['kind'].capitalize()} skipped: {error}.")
        except Exception as error:                         # a failed job never stops the worker
            result = "failed"
            explained = type(error).__name__ in ("PlannerUnavailable", "WorkspaceError")   # already in plain words
            outcome = {"error": (str(error) if explained else f"{type(error).__name__}: {error}")[:500]}
            self.say(f"{job['kind']} failed: {outcome['error']}", "error")
            (self.ws.home / "logs").mkdir(parents=True, exist_ok=True)
            with open(self.ws.home / "logs" / "worker-errors.log", "a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"{_now()} {job['kind']}\n{traceback.format_exc()}\n")
        finally:
            done = dict(job, finished=_now(), seconds=round(time.monotonic() - started, 1), result=result,
                        outcome={k: v for k, v in outcome.items() if k in ("summary", "error", "detail", "objects",
                                                                            "opportunities", "served", "accepted")})
            self.history.append(done)
            _write_json(self.ws.home / "STUDIO_JOBS.json", list(self.history))
            (self.ws.home / "STUDIO_CURRENT.json").unlink(missing_ok=True)
            self.current = None
            self._set("idle", "")
            self.bus.publish("job", done)

    # --------------------------------------------------------------------- jobs --

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
        plan = draft_plan(self.ws, self.ws.router(on_call=self._on_call, backoff_s=(5, 20, 60)))
        self.say(f"Plan v{plan['version']} drafted: {len(plan['milestones'])} milestones on "
                 f"{len(plan['tracks'])} tracks. It is yours to edit.")
        self.bus.publish("plan", {"version": plan["version"]})
        return {"summary": f"{len(plan['milestones'])} milestones"}

    def _job_draft(self, milestone: str | None = None) -> dict[str, Any]:
        from runesmith.app.planner import draft_files
        self._set("drafting", "Writing first files for a milestone")
        self.say("Asking the planner model for the first files of a milestone (a draft you review)")
        draft = draft_files(self.ws, self.ws.router(on_call=self._on_call, backoff_s=(5, 20, 60)), milestone)
        self.say(f"Draft ready: {draft['title']} ({len(draft['files'])} files). Nothing is written until you apply it.")
        self.bus.publish("work", {"draft": draft["id"]})
        return {"summary": draft["title"]}

    def _job_round(self) -> dict[str, Any]:
        from runesmith.discover import discover
        from runesmith.loop import run_loop
        from runesmith.report import write_report
        from runesmith.steward import opportunity_id
        ws, settings = self.ws, self.ws.settings()
        self._job_map(probe=False)
        env_map = ws.environment_map() or {"objects": []}
        objects = [o for o in env_map["objects"] if o["kind"] == "python_repository"]
        statuses: dict[str, str] = {}
        details: dict[str, dict[str, Any]] = {}
        self._round_details = details
        if settings["autonomy"] == "observe":
            self.say("Observe mode: mapped and watching. Switch to Propose in Settings to let Runesmith work.")
            return self._finish_round([], statuses, {}, "observed")
        if not objects:
            self.say("No code objects with tests here yet. Draft a plan under Goals & Plan to start something new.")
            return self._finish_round([], statuses, {}, "nothing to repair")
        ready = ws.ready()
        if not ready["repair"]:
            self.say("No Worker model is set up, so Runesmith can map but not repair. Add one under Inference.", "warn")
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
        for obj in objects:
            if not (Path(obj["path"]) / "src").is_dir():
                statuses[obj["name"]] = "skipped: the shipped repair organ needs a src/ layout"
                continue
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
                fresh.append(dict(opportunity, id=oid, object=obj["name"]))
                new += 1
            label = {"green": "all tests pass", "failing": f"{len(found['opportunities'])} failing test file(s)",
                     "timed_out": "the test run timed out",
                     "error_without_failures": "the tests could not run"
                     + (f" ({found['detail']})" if found.get("detail") else "")
                     + (f": {found['triage']['reason']}" if found.get("triage") else "")
                     }.get(found["status"], found["status"].replace("_", " "))
            self.say(f"{obj['name']}: {label}" + (f"; {new} new to work on" if new else ""))
            if self._stop_after_step:
                raise StopRequested
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
                if self._stop_after_step:
                    raise StopRequested

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
        else:
            self.say("Nothing new to work on this round.")
        write_report(ws.home)
        return self._finish_round(fresh[:consumed] if fresh else [], statuses, summary, "worked" if fresh else "nothing new")

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
                waiting = self.ws.manual_waiting()
                if waiting != self._manual_seen:
                    self._manual_seen = waiting
                    if waiting:
                        self.say("A request is waiting for you to relay it to a chat model (Thinking power, Chat relay).",
                                 "warn")
                    self.bus.publish("manual", {"waiting": waiting})
            except Exception:                              # never let the watcher die on a half-written file
                pass
            time.sleep(3.0)


def dump_json(value: Any) -> str:
    return json.dumps(value, default=str)
