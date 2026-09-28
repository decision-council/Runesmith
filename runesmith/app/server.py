"""Runesmith Studio's local web server: standard library only, bound to this computer.

``runesmith`` (or ``runesmith up [folder]``) starts it and opens the browser. The
page and its API are served on ``127.0.0.1`` only.

Access is granted by a random token in the link the launcher opens. The first visit
trades the token for an HttpOnly, SameSite=Strict cookie and drops it from the address
bar. Every request's Host header must name this server, which blocks DNS-rebinding
pages. Requests that change anything must carry the ``X-Runesmith`` header, which a
cross-site form cannot send.

The server is a thin layer: every route calls one method of
:class:`runesmith.app.workspace.Workspace` or the :class:`Worker`.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import queue
import re
import secrets
import socket
import string
import subprocess
import sys
import threading
import time
import webbrowser
from contextlib import contextmanager, nullcontext
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

from runesmith import __version__
from runesmith.app.worker import EventBus, Worker
from runesmith.app.workspace import Workspace, WorkspaceError, _read_json, _write_json
from runesmith.app.workspace_ownership import Bindings, RootLease

STATIC = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 7300
STUDIO_DIR = Path.home() / ".runesmith-studio"
MAX_BODY = 4_000_000
COOKIE = "rs_session"
WORKSPACE_HEADER = 'X-Runesmith-Workspace'
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def home_tag(home: Path) -> str:
    return hashlib.sha256(str(Path(home).resolve()).encode("utf-8")).hexdigest()[:12]


class WorkspaceConflict(WorkspaceError):
    """An ownership or stale-context conflict, not permission to retry a write."""


class WorkspaceOwned(WorkspaceConflict):
    pass


class Studio:
    """The open workspace and its worker. The Studio can switch to another folder without restarting."""

    def __init__(self, root: Path, home: Path | None = None, *, token: str | None = None) -> None:
        self.bus = EventBus()
        self.token = token or secrets.token_urlsafe(24)
        self.lock = threading.RLock()
        self.ws: Workspace | None = None
        self.worker: Worker | None = None
        self._instance: InstanceLock | None = None
        self._inflight = 0
        self.epoch = ''
        self.startup_error = ''
        self.port: int | None = None
        self.started = _now()
        self.closing = False
        self.httpd_shutdown: Callable[[], None] = lambda: None
        self.open(root, home)

    def open(self, root: Path, home: Path | None = None, *, create: bool = False) -> Workspace:
        with self.lock:
            if self.closing:
                raise WorkspaceConflict('Studio is closing; no folder was opened.')
            root = Path(root).expanduser().resolve()
            # Picking the same root must retain an explicitly isolated home.
            if self.ws and root == self.ws.root:
                if home is None or Path(home).expanduser().resolve() == self.ws.home:
                    return self.ws
                raise WorkspaceConflict('This root is already open with a different home.')
            if self._inflight:
                raise WorkspaceConflict('Another workspace request is still finishing. No folder was opened.')
            destination = Path(Bindings(STUDIO_DIR).resolve(root, home)['home'])
            if self.ws and destination == self.ws.home:
                raise WorkspaceConflict('The same home cannot be rebound to a different root.')
            old, old_ws, old_bus, old_instance = self.worker, self.ws, self.bus, self._instance
            instance = None
            try:
                # No folder creation, destination initialization, or old-worker
                # shutdown until the old claim boundary is held idle.
                with old.switch_guard() if old else nullcontext():
                    if create and root.exists():
                        raise WorkspaceError('The new folder already exists. Select it explicitly instead of creating it.')
                    if not create and not root.is_dir():
                        raise WorkspaceError(f'{root} is not a folder')
                    instance = InstanceLock(destination, root=root)
                    if not instance.acquire():
                        raise WorkspaceOwned('The destination home is owned by another Runesmith writer. No switch was made.')
                    if create:
                        root.mkdir(parents=True, exist_ok=True)
                    Bindings(STUDIO_DIR).remember(root, destination)
                    ws = Workspace(root, destination)
                    bus = EventBus()
                    worker = Worker(ws, bus)
                    if old:
                        if not worker.paused:
                            worker.pause()
                        old.close()
                if old and not old.wait_stopped():
                    raise WorkspaceConflict('The previous worker is still stopping. Its home remains owned; no new worker was started.')
            except BaseException:
                if instance:
                    instance.close()
                raise

            # Commit only after both old threads have stopped. From here, even a
            # startup error leaves the selected home owned and closed to work.
            self.ws, self.worker, self.bus, self._instance = ws, worker, bus, instance
            # A thread must retain its own ownership lease even if __init__ is
            # interrupted and the caller never receives the Studio reference.
            worker._studio_lease = instance
            self.epoch = secrets.token_hex(16)
            self.startup_error = ''
            if old_ws:
                self._remove_beacon(old_ws.home)
                old_instance.close()
            try:
                self.publish_beacon()
                ws.ledger.append('studio.opened', {'version': __version__, 'switched_paused': bool(old)})
                worker.start()
                try:
                    self._remember(ws)
                except Exception:
                    worker.say('Recent folders could not be saved. Workspace ownership and work are unchanged.', 'warn')
            except BaseException as error:
                worker.close()
                stopped = worker.wait_stopped()
                if not isinstance(error, Exception):
                    if stopped:
                        self.closing = True
                        self._remove_beacon(ws.home)
                        instance.close()
                    raise  # Unjoined threads retain the lease, including on interruption.
                self.startup_error = f'Worker startup failed; this home remains owned. Restart Studio after inspection: {type(error).__name__}: {error}'
            if old_ws:
                old_bus.publish('workspace', {'path': str(ws.root), 'reload': True})
            return ws

    def switch_status(self):
        blockers = []
        if self.closing:
            blockers.append('Studio is closing.')
        if self.worker and self.worker.current:
            blockers.append('The current job is still running. Wait for it to finish; switching does not cancel it.')
        if self._inflight > 1:
            blockers.append('Another workspace request is still finishing.')
        warning = self.startup_error
        if not warning and self.worker and self.worker._closing:
            warning = 'The previous worker was asked to stop. Finish the folder switch or restart Studio; this worker cannot resume.'
        return {'allowed': not blockers, 'blockers': blockers, 'warning': warning,
                'waiting': len(self.worker.snapshot()['queue']) if self.worker else 0,
                'policy': 'Waiting jobs stay in their original home. A different home opens paused; review it before Resume.'}

    def check_epoch(self, epoch, *, mutating=False):
        if self.closing:
            raise WorkspaceConflict('Studio is closing. Reload after it restarts.')
        if (mutating and not epoch) or (epoch and epoch != self.epoch):
            raise WorkspaceConflict('Workspace changed or this action has no workspace context. Reload Studio before acting; nothing was submitted.')

    @contextmanager
    def operation(self, epoch, *, mutating=False):
        # Pin ws/worker/bus for an entire handler without blocking Pause behind a
        # slow API read. A switch cannot commit while any handler is in flight.
        with self.lock:
            self.check_epoch(epoch, mutating=mutating)
            self._inflight += 1
            bound_epoch = self.epoch
        try:
            yield bound_epoch
        finally:
            with self.lock:
                self._inflight -= 1

    def publish_beacon(self):
        if self.port is not None:
            _write_json(self.ws.home / 'studio.lock.json', {'pid': os.getpid(), 'port': self.port,
                        'token': self.token, 'started': self.started, 'folder': str(self.ws.root)})

    def _remove_beacon(self, home):
        try:
            record = _read_json(home / 'studio.lock.json', {})
            if isinstance(record, dict) and record.get('token') == self.token:
                (home / 'studio.lock.json').unlink()
        except OSError:
            pass

    def close(self, timeout: float = 2.0) -> bool:
        with self.lock:
            self.closing = True
            if self.worker:
                self.worker.close()
                if not self.worker.wait_stopped(timeout) or self._inflight:
                    # Keep the lease alive even if a caller drops its Studio
                    # reference while the worker thread is still finishing.
                    self.worker._studio_lease = self._instance
                    return False
            if self._instance:
                self._remove_beacon(self.ws.home)
                self._instance.close()
            return True

    @staticmethod
    def recent() -> list[dict[str, Any]]:
        data = _read_json(STUDIO_DIR / 'studio.json', {})
        rows = data.get('recent', []) if isinstance(data, dict) else []
        valid = []
        for row in rows[:12] if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get('path'), str) or not row['path'].strip():
                continue
            try:
                if Path(row['path']).is_dir():
                    valid.append(row)
            except (OSError, ValueError):
                continue
        return valid

    def _remember(self, ws: Workspace) -> None:
        try:
            rows = [r for r in self.recent() if r["path"] != str(ws.root)]
            rows.insert(0, {"path": str(ws.root), "home": str(ws.home), "name": ws.settings()["workspace_name"], "opened": _now()})
            _write_json(STUDIO_DIR / "studio.json", {"recent": rows[:12]})
        except OSError:                                  # a read-only profile must not stop the Studio
            pass


# ---------------------------------------------------------------------- routes --

Route = tuple[str, re.Pattern, Callable[..., Any]]
ROUTES: list[Route] = []


def route(method: str, pattern: str):
    def register(fn):
        ROUTES.append((method, re.compile(pattern), fn))
        return fn
    return register


def _ws(s: Studio) -> Workspace:
    assert s.ws is not None
    return s.ws


@route("GET", r"/api/session")
def api_session(s: Studio, q, body):
    ws = _ws(s)
    return {"ok": True, "version": __version__, "workspace": {"path": str(ws.root), "name": ws.settings()["workspace_name"]},
            "settings": ws.settings(), "started": s.started, "platform": sys.platform}


@route("GET", r"/api/state")
def api_state(s: Studio, q, body):
    state = _ws(s).state()
    state["worker"] = {k: v for k, v in s.worker.snapshot().items() if k != "lines"}
    state["recent_events"] = s.bus.recent[-1]["id"] if s.bus.recent else 0
    return state


@route("GET", r"/api/worker")
def api_worker(s: Studio, q, body):
    return s.worker.snapshot()


@route("GET", r"/api/build")
def api_build(s: Studio, q, body):
    from runesmith.app.building import status
    return status(_ws(s))


@route('GET', r'/api/dashboards')
def api_dashboards(s: Studio, q, body):
    from runesmith.app.dashboards import view
    return view(_ws(s))


@route('POST', r'/api/dashboards')
def api_dashboards_change(s: Studio, q, body):
    from runesmith.app.dashboards import change
    result = change(_ws(s), revision=body.get('revision'), action=body.get('action'),
                    project=body.get('project'), project_id=body.get('project_id'), panels=body.get('panels'))
    s.bus.publish('dashboards', {})
    return result


@route("POST", r"/api/worker/run")
def api_worker_run(s: Studio, q, body):
    job = body.get("job", "round")
    allowed = {"map":{"probe"}, "draft":{"milestone"}, "build":{"draft_id","author_only"}, "escalate":set(),
               "supplement":{"draft_id","reason","instrument","author_only"},
               "revise":{"draft_id","quote_id","instrument","operation_id","reason"},
               "review_current":{"milestone"},
               "resume_check":{"draft_id","reason"},
               "resume_author":{"request_id"}, "mode":{"mode"}, "measure":{"measurement"},
               "source_baseline":{"reason"},
               "allocate_check":{"draft_id","quote_id","reason"},
               "reconcile_check":{"draft_id","quote_id","reason"},
               "correct":{"attempt"}, "breakdown":{"milestone"}, "propose_acceptance":{"milestone"}}.get(job, set())
    params = {k: v for k, v in (body.get("params") or {}).items() if k in allowed}
    return s.worker.enqueue(job, **params)


@route("POST", r"/api/worker/(pause|resume|stop)")
def api_worker_control(s: Studio, q, body, action):
    {"pause": s.worker.pause, "resume": s.worker.resume, "stop": s.worker.stop_current}[action]()
    return s.worker.snapshot()


@route('POST', r'/api/worker/recovery')
def api_worker_recovery(s: Studio, q, body):
    return s.worker.review_recovery(revision=body.get('revision'), decision=body.get('decision'),
                                    reviewed=body.get('reviewed'))


@route("GET", r"/api/settings")
def api_settings(s: Studio, q, body):
    return _ws(s).settings()


@route("POST", r"/api/settings")
def api_settings_update(s: Studio, q, body):
    settings = _ws(s).update_settings(body)
    s.bus.publish("settings", settings)
    with s.worker._cv:
        s.worker._cv.notify_all()                        # a new interval or autonomy takes effect now
    return settings


@route("GET", r"/api/goals")
def api_goals(s: Studio, q, body):
    return _ws(s).goals()


@route("POST", r"/api/goals")
def api_goal_add(s: Studio, q, body):
    goal = _ws(s).add_goal(body.get("text", ""), kind=body.get("kind") or "outcome")
    s.bus.publish("goals", {})
    return goal


@route("POST", r"/api/goals/([A-Za-z0-9]+)")
def api_goal_update(s: Studio, q, body, goal_id):
    goal = _ws(s).update_goal(goal_id, body)
    s.bus.publish("goals", {})
    return goal


@route("DELETE", r"/api/goals/([A-Za-z0-9]+)")
def api_goal_remove(s: Studio, q, body, goal_id):
    _ws(s).remove_goal(goal_id)
    s.bus.publish("goals", {})
    return {"ok": True}


@route("GET", r"/api/brief")
def api_brief(s: Studio, q, body):
    ws = _ws(s)
    return dict(ws.brief(), candidates=ws.candidate_blueprints())


@route("POST", r"/api/brief")
def api_brief_update(s: Studio, q, body):
    brief = _ws(s).set_brief(body.get("text"), body.get("blueprints"))
    s.bus.publish("brief", {})
    return brief


@route("GET", r"/api/plan")
def api_plan(s: Studio, q, body):
    ws = _ws(s)
    from runesmith.app.breakdowns import proposals
    from runesmith.app.acceptance_contracts import expectations
    from runesmith.app.building import current_file_reviews
    from runesmith.app.planner import plan_readiness
    from runesmith.app.work_modes import planning_blockers, held_plans
    from runesmith.app.acceptance_proposals import status as acceptance_status
    return {"plan": ws.plan(), "milestones": ws.milestones(), "ready": ws.ready()["plan"], 'breakdowns':proposals(ws),
            'acceptance_checks':acceptance_status(ws),
            'acceptance_expectations':{m['id']:expectations(ws,m['id']) for m in (ws.plan() or {}).get('milestones',[])},
            'current_checks':current_file_reviews(ws), 'readiness':plan_readiness(ws.plan()),
            'planning_blockers':planning_blockers(ws), 'autonomy': ws.settings()['autonomy'],
            'held_plans':[{k:r.get(k) for k in ('id', 'utc', 'author', 'reason', 'answer')} for r in held_plans(ws)[:10]]}


@route('GET', r'/api/author-context')
def api_author_context(s: Studio, q, body):
    from runesmith.app.source_focus import inspect_context
    return inspect_context(_ws(s))


@route('POST', r'/api/author-context')
def api_author_context_save(s: Studio, q, body):
    from runesmith.app.source_focus import save_focus
    result = save_focus(_ws(s), body.get('paths'), body.get('snapshot_digest'), body.get('reason'))
    s.bus.publish('plan', {}); s.bus.publish('work', {})
    return result


@route('GET', r'/api/drafts/([A-Za-z0-9]+)/revision-context')
def api_revision_context(s: Studio, q, body, draft_id):
    from runesmith.app.revision_context import inspect_revision
    return inspect_revision(_ws(s), draft_id)


@route('GET', r'/api/drafts/([A-Za-z0-9]+)/revision-request')
def api_revision_request(s: Studio, q, body, draft_id):
    from runesmith.app.author_revisions import revision_status
    return revision_status(_ws(s), draft_id, (q.get('instrument') or [None])[0])


@route('POST', r'/api/drafts/([A-Za-z0-9]+)/revision-context')
def api_revision_context_save(s: Studio, q, body, draft_id):
    from runesmith.app.revision_context import save_selection
    result = save_selection(_ws(s), draft_id, version=body.get('version'), selections=body.get('selections'),
                            reason=body.get('reason'), enabled=body.get('enabled', True))
    s.bus.publish('work', {})
    return result


@route('POST', r'/api/plan/milestones/([A-Za-z0-9_-]+)/expectations')
def api_acceptance_expectations(s: Studio,q,body,milestone_id):
    from runesmith.app.acceptance_contracts import publish_expectations
    from runesmith.app.workspace import WorkspaceError
    if 'expected_digest' not in body:
        raise WorkspaceError('Reload public expectations before publishing; their current digest is required.')
    result=publish_expectations(_ws(s),milestone_id,body.get('criteria'),body.get('reason'),
                                interfaces=body.get('interfaces'),expected_digest=body['expected_digest'])
    s.bus.publish('plan',{});s.bus.publish('work',{})
    return result


@route('GET', r'/api/fix-tests')
def api_fix_tests(s: Studio, q, body):
    from runesmith.app.fix_tests import offer
    return {"offer": offer(_ws(s))}


@route('POST', r'/api/fix-tests')
def api_fix_tests_start(s: Studio, q, body):
    """Fix the failing tests (J3): the owner's own tests, frozen, decide; builders change only the code."""
    from runesmith.app.fix_tests import start
    result = start(_ws(s), allow_apply=body.get('allow_apply') is True)
    s.bus.publish('plan', {})
    s.bus.publish('settings', _ws(s).settings())
    return result


@route('GET', r'/api/try')
def api_try(s: Studio, q, body):
    from runesmith.app.try_it import status
    return status(_ws(s))


@route('POST', r'/api/try/run')
def api_try_run(s: Studio, q, body):
    """The owner runs the project's own program (G2): practice copy unless ``real`` is exactly true."""
    from runesmith.app.try_it import run
    return run(_ws(s), str(body.get('command') or ''), real=body.get('real') is True)


@route('POST', r'/api/try/reset')
def api_try_reset(s: Studio, q, body):
    from runesmith.app.try_it import reset_practice
    return reset_practice(_ws(s))


@route('POST', r'/api/plan/milestones/([A-Za-z0-9_-]+)/acceptance/approve')
def api_acceptance_approve(s: Studio,q,body,milestone_id):
    from runesmith.app.acceptance_proposals import approve
    result=approve(_ws(s),milestone_id,str(body.get('proposal') or ''),replace=bool(body.get('replace')),
                   reason=str(body.get('reason') or ''))
    s.bus.publish('plan',{})
    return result


@route('POST', r'/api/plan/milestones/([A-Za-z0-9_-]+)/acceptance/discard')
def api_acceptance_discard(s: Studio,q,body,milestone_id):
    from runesmith.app.acceptance_proposals import discard
    result=discard(_ws(s),milestone_id,str(body.get('proposal') or ''),reason=str(body.get('reason') or ''))
    s.bus.publish('plan',{})
    return result


@route('POST', r'/api/plan/breakdowns/(b[0-9a-f]{12})/adopt')
def api_breakdown_adopt(s: Studio,q,body,key):
    from runesmith.app.breakdowns import adopt_breakdown
    result=adopt_breakdown(_ws(s),key)
    s.bus.publish('plan',{})
    return result


@route('POST', r'/api/plan/breakdowns/(b[0-9a-f]{12})/reject')
def api_breakdown_reject(s: Studio,q,body,key):
    from runesmith.app.breakdowns import reject_breakdown
    result=reject_breakdown(_ws(s),key,body.get('reason',''))
    s.bus.publish('plan',{})
    return result


@route("GET", r"/api/goalposts")
def api_goalposts(s: Studio, q, body):
    ws = _ws(s)
    from runesmith.app.work_modes import planning_blockers
    blockers = planning_blockers(ws)
    return {"goalposts": ws.goalposts(), "ready": ws.ready()["plan"] and not blockers,
            'planning_blockers': blockers}


@route("POST", r"/api/plan/milestones")
def api_milestone_add(s: Studio, q, body):
    milestone = _ws(s).add_milestone(body.get("title", ""), body.get("detail", ""), body.get("track", ""))
    s.bus.publish("plan", {})
    return milestone


@route("POST", r"/api/plan/milestones/([A-Za-z0-9_-]+)")
def api_milestone_update(s: Studio, q, body, milestone_id):
    milestone = _ws(s).update_milestone(milestone_id, body)
    s.bus.publish("plan", {})
    return milestone


@route("GET", r"/api/inference")
def api_inference(s: Studio, q, body):
    return _ws(s).inference()


@route("GET", r"/api/inference/accounting")
def api_inference_accounting(s: Studio, q, body):
    from runesmith.app.inference_accounting import accounting_view
    return accounting_view(_ws(s).home)


@route("POST", r"/api/inference/instruments")
def api_instrument_save(s: Studio, q, body):
    saved = _ws(s).save_instrument(body.get("name", ""), body.get("spec") or {}, body.get("key"), body.get("roles"))
    s.bus.publish("inference", {})
    return saved


@route("GET", r"/api/inference/routes/([A-Za-z0-9_.-]+)")
def api_instrument_route(s: Studio, q, body, name):
    from runesmith.app.inference_routes import route_view
    return route_view(_ws(s), name)


@route("GET", r"/api/inference/availability/([A-Za-z0-9_.-]+)")
def api_instrument_availability(s: Studio, q, body, name):
    from runesmith.app.inference_availability import availability_view
    return availability_view(_ws(s), name)


@route("POST", r"/api/inference/routes/([A-Za-z0-9_.-]+)")
def api_instrument_route_save(s: Studio, q, body, name):
    from runesmith.app.inference_routes import save_route
    saved = save_route(_ws(s), name, revision=body.get('revision'), model=body.get('model'),
                       fallback_models=body.get('fallback_models'), reason=body.get('reason'))
    s.bus.publish('inference', {})
    return saved


@route("DELETE", r"/api/inference/instruments/([A-Za-z0-9_.-]+)")
def api_instrument_remove(s: Studio, q, body, name):
    _ws(s).remove_instrument(name)
    s.bus.publish("inference", {})
    return {"ok": True}


@route("POST", r"/api/inference/roles")
def api_roles(s: Studio, q, body):
    roles = _ws(s).set_roles(body.get("roles") or {})
    s.bus.publish("inference", {})
    return roles


@route("POST", r"/api/inference/test/([A-Za-z0-9_.-]+)")
def api_instrument_test(s: Studio, q, body, name):
    result = _ws(s).test_instrument(name)
    s.bus.publish("inference", {"tested": name, "ok": result["ok"]})
    return result


@route("GET", r"/api/inference/discover")
def api_discover(s: Studio, q, body):
    from runesmith.app.providers import discover_local
    return {"found": discover_local()}


@route("POST", r"/api/inference/models")
def api_models(s: Studio, q, body):
    return _ws(s).list_models(name=body.get("name"), preset=body.get("preset"), base_url=body.get("base_url"),
                              key_value=body.get("key"), provider=body.get("provider", ""))


@route("GET", r"/api/map/environment")
def api_map_environment(s: Studio, q, body):
    ws = _ws(s)
    work = _read_json(ws.home / "WORK.json", {})
    env_map = ws.environment_map()
    return {"map": env_map, "round": {"utc": work.get("utc"), "objects": ws.object_statuses(work, env_map or {}),
                                      "details": work.get("details", {})},
            "settings": {"exclude": ws.settings()["exclude"], "probe_tests": ws.settings()["probe_tests"]}}


@route("GET", r"/api/map/self")
def api_map_self(s: Studio, q, body):
    return _ws(s).self_view()


@route("GET", r"/api/map/development")
def api_map_development(s: Studio, q, body):
    return _ws(s).development_view()


@route("GET", r"/api/map/operations")
def api_map_operations(s: Studio, q, body):
    ws = _ws(s)
    inference = ws.inference()
    state = ws.state()
    gens = ws.generations_view()
    env_map = ws.environment_map() or {"objects": []}
    work = {"counts": state["proposals"], "draft_counts": state["drafts"], "opportunities": [None] * state["opportunities"],
            "last_round": state["last_round"], "round_utc": state["round_utc"]}
    judged = state["repairs"]
    return {"worker": s.worker.snapshot(), "roles": inference["roles"], "role_labels": inference["role_labels"],
            "instruments": inference["instruments"], "stats": inference["stats"], "ready": inference["ready"],
            "attention": state["attention"], "trial": gens["trial"], "active_generation": gens["active"],
            "pipeline": {"objects": len(env_map["objects"]),
                         "code_objects": sum(1 for o in env_map["objects"] if o["kind"] == "python_repository"),
                         "opportunities": len(work["opportunities"]), "attempts": judged["judged"],
                         "accepted": judged["accepted"], "waiting": work["counts"].get("waiting", 0),
                         "applied": work["counts"].get("applied", 0), "drafts": work["draft_counts"]},
            "last_round": work["last_round"], "round_utc": work["round_utc"], "settings": ws.settings()}


@route("GET", r"/api/work")
def api_work(s: Studio, q, body):
    return _ws(s).work()


@route("POST", r"/api/proposals/([A-Za-z0-9_.-]+)/(apply|undo|reject)")
def api_proposal(s: Studio, q, body, key, action):
    ws = _ws(s)
    result = {"apply": lambda: ws.apply_proposal(key), "undo": lambda: ws.undo_proposal(key),
              "reject": lambda: ws.reject_proposal(key, body.get("reason", ""))}[action]()
    s.bus.publish("work", {"proposal": key, "action": action, "ok": result.get("ok")})
    return result


@route("POST", r"/api/drafts/([A-Za-z0-9]+)/(apply|undo|reject)")
def api_draft(s: Studio, q, body, draft_id, action):
    ws = _ws(s)
    result = {"apply": lambda: ws.apply_draft(draft_id, overwrite=bool(body.get("overwrite"))),
              "undo": lambda: ws.undo_draft(draft_id),
              "reject": lambda: ws.reject_draft(draft_id, body.get("reason", ""))}[action]()
    s.bus.publish("work", {"draft": draft_id, "action": action, "ok": result.get("ok")})
    if action == "apply" and result.get("ok"):
        s.worker.enqueue("map", probe=False)
    return result


@route("POST", r"/api/links/suggest")
def api_links_suggest(s: Studio, q, body):
    result = _ws(s).suggest_link_fixes(body.get("object") or None)
    if result.get("draft"):
        s.bus.publish("work", {"draft": result["draft"]})
    return result


@route("GET", r"/api/improve")
def api_improve(s: Studio, q, body):
    ws = _ws(s)
    view = ws.generations_view()
    view["campaigns"] = ws.development_view()["campaigns"]
    view["self"] = {k: v for k, v in ws.self_view().items() if k in ("capabilities", "open_targets", "identity")}
    return view


@route("POST", r"/api/improve/adopt/([A-Za-z0-9-]+)")
def api_adopt(s: Studio, q, body, generation_id):
    result = _ws(s).adopt_from_library(generation_id)
    s.bus.publish("improve", {"adopted": generation_id, "ok": result.get("ok")})
    return result


@route("POST", r"/api/improve/activate/([A-Za-z0-9-]+)")
def api_activate(s: Studio, q, body, generation_id):
    result = _ws(s).activate_generation(generation_id)
    s.bus.publish("improve", {"activated": generation_id, "ok": result.get("ok")})
    return result


@route("GET", r"/api/notes")
def api_notes(s: Studio, q, body):
    ws = _ws(s)
    return {"notes": ws.notes.all(), "counts": ws.notes.counts(), "read_notes": ws.settings()["read_notes"],
            'planning_feedback': ws.planning_note_selection()}


@route("POST", r"/api/notes")
def api_note_add(s: Studio, q, body):
    note = _ws(s).add_note(body.get("target_type", "workspace"), body.get("target_id", "root"), body.get("text", ""),
                           body.get("target_label", ""), body.get("reply_to"))
    s.bus.publish("notes", {"id": note["id"]})
    return note


@route("POST", r"/api/notes/([A-Za-z0-9]+)/resolve")
def api_note_resolve(s: Studio, q, body, note_id):
    _ws(s).resolve_note(note_id, body.get("resolution", ""))
    s.bus.publish("notes", {"resolved": note_id})
    return {"ok": True}


@route("GET", r"/api/manual")
def api_manual(s: Studio, q, body):
    return {"requests": _ws(s).manual_requests()}


@route('GET', r'/api/mission')
def api_mission(s, q, body):
    from runesmith.app.work_modes import view
    return view(_ws(s))


@route('POST', r'/api/mission/modes')
def api_mission_modes(s, q, body):
    from runesmith.app.work_modes import save
    result = save(_ws(s), body.get('modes'), body.get('revision'), body.get('reason'), body.get('infer_purpose'))
    s.bus.publish('mission', {})
    return result


@route('POST', r'/api/measurements')
def api_measurement_definition(s, q, body):
    from runesmith.app.measurements import save_definition
    result = save_definition(_ws(s), body.get('definition'), body.get('revision'))
    s.bus.publish('mission', {})
    return result


@route('GET', r'/api/support-reports')
def api_support_reports(s, q, body):
    from runesmith.app.support_reports import view
    return view(_ws(s))


@route('POST', r'/api/support-reports')
def api_support_report_add(s, q, body):
    from runesmith.app.support_reports import add
    result = add(_ws(s), body.get('report'), body.get('revision'))
    s.bus.publish('support_reports', {'id': result['report']['id'], 'received': True})
    return result


@route('POST', r'/api/support-reports/([a-f0-9]{64})/selection')
def api_support_report_select(s, q, body, report_id):
    from runesmith.app.support_reports import select
    result = select(_ws(s), report_id, body.get('selected'), body.get('revision'),
                    confirm_model_sharing=body.get('confirm_model_sharing', False))
    s.bus.publish('support_reports', {'id': report_id, 'selected': result['report']['selected']})
    return result


@route('POST', r'/api/measurements/([A-Za-z0-9_-]+)/report')
def api_measurement_report(s, q, body, measurement):
    from runesmith.app.measurements import save_pasted_report
    result = save_pasted_report(_ws(s), measurement, body.get('text'))
    s.bus.publish('mission', {'measurement': measurement, 'report_received': True})
    return result


@route("POST", r"/api/manual/([A-Za-z0-9_.-]+)/answer")
def api_manual_answer(s: Studio, q, body, request_id):
    result = _ws(s).answer_manual(request_id, body.get("text", ""), body.get("model") or None, bool(body.get("force")))
    if result.get("written"):
        s.bus.publish("manual", {"answered": request_id})
    return result


@route("POST", r"/api/manual/([A-Za-z0-9_.-]+)/skip")
def api_manual_skip(s: Studio, q, body, request_id):
    result = _ws(s).skip_manual(request_id)
    s.bus.publish("manual", {"skipped": request_id})
    return result


@route("GET", r"/api/activity")
def api_activity(s: Studio, q, body):
    limit = max(1, min(1000, int((q.get("limit") or ["150"])[0])))
    return {"events": _ws(s).activity(limit, (q.get("kinds") or [""])[0]), "lines": list(s.worker.lines)[-150:],
            "ledger": _ws(s).ledger.verify() if (q.get("verify") or ["0"])[0] == "1" else None}


@route("GET", r"/api/health")
def api_health(s: Studio, q, body):
    return {"checks": _ws(s).health(network=(q.get("network") or ["0"])[0] == "1")}


@route("GET", r"/api/workspaces")
def api_workspaces(s: Studio, q, body):
    return {"current": str(_ws(s).root), "home": str(_ws(s).home), "recent": Studio.recent(), 'switch': s.switch_status()}


def _workspace_path(raw, label='folder'):
    if not isinstance(raw, str) or not raw.strip():
        raise WorkspaceError(f'Choose an explicit {label} path.')
    if not Path(raw.strip()).expanduser().is_absolute():
        raise WorkspaceError(f'Choose an absolute {label} path, or browse to the folder.')
    return Path(raw.strip()).expanduser().resolve()


@route('GET', r'/api/workspaces/resolve')
def api_workspace_resolve(s: Studio, q, body):
    root = _workspace_path((q.get('path') or [None])[0])
    raw_home = (q.get('home') or [None])[0]
    home = _workspace_path(raw_home, 'home') if raw_home else None
    return Bindings(STUDIO_DIR).resolve(root, home)


@route("POST", r"/api/workspaces/open")
def api_workspace_open(s: Studio, q, body):
    root = _workspace_path(body.get('path'))
    home = _workspace_path(body['home'], 'home') if 'home' in body else None
    if 'create' in body and type(body['create']) is not bool:
        raise WorkspaceError('Create must be true or false.')
    ws = s.open(root, home, create=body.get('create', False))
    return {'ok': True, 'path': str(ws.root), 'home': str(ws.home), 'paused': s.worker.paused, 'warning': s.startup_error}


@route("GET", r"/api/browse")
def api_browse(s: Studio, q, body):
    """Folders only, for the folder picker. Hidden folders are left out."""
    raw = (q.get("path") or [""])[0]
    if not raw:
        roots = [str(Path.home())]
        if os.name == "nt":
            roots += [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        return {"path": "", "parent": None, "dirs": [{"name": r, "path": r} for r in roots]}
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise WorkspaceError("not a folder")
    dirs = []
    try:
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and not child.name.startswith((".", "$")) and child.name not in ("node_modules", "__pycache__"):
                dirs.append({"name": child.name, "path": str(child)})
    except PermissionError:
        pass
    return {"path": str(path), "parent": str(path.parent) if path.parent != path else "", "dirs": dirs[:400]}


@route("POST", r"/api/snapshot")
def api_snapshot(s: Studio, q, body):
    ws = _ws(s)
    target = ws.home / "exports" / f"runesmith-snapshot-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "file": str(ws.export_snapshot(target))}


@route("POST", r"/api/reveal")
def api_reveal(s: Studio, q, body):
    """Open the workspace or Runesmith's home in the computer's file manager."""
    ws = _ws(s)
    target = {"workspace": ws.root, "home": ws.home, "exports": ws.home / "exports"}.get(body.get("which"), ws.root)
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(target))                        # noqa: S606 (a folder, chosen from a fixed list)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return {"ok": True}


@route("GET", r"/api/genesis")
def api_genesis(s: Studio, q, body):
    ws = _ws(s)
    env_map = ws.environment_map()
    if env_map is None:                                  # the first boot maps the folder while the intro plays
        env_map = ws.map_environment(probe=False)
    facts = env_map.get("workspace_facts") or {}
    self_map = ws.self_map()
    settings = ws.settings()
    entries = []
    for e in facts.get("entries", [])[:16]:
        row = {"name": e["name"], "type": e["type"]}
        if e["type"] == "dir":                          # one level deeper, so a small folder still makes a map
            try:
                kids = sorted((p for p in (ws.root / e["name"]).iterdir() if not p.name.startswith((".", "__"))),
                              key=lambda p: (not p.is_dir(), p.name.lower()))
                row["children"] = [{"name": p.name, "type": "dir" if p.is_dir() else "file"} for p in kids[:5]]
            except OSError:
                row["children"] = []
        entries.append(row)
    return {"onboarded": settings["onboarded"], "name": settings["workspace_name"], "path": str(ws.root),
            "folder": ws.root.name or str(ws.root), "empty": facts.get("empty"), "files": facts.get("files"),
            "entries_total": facts.get("entries_total"), "entries": entries,
            "kinds": facts.get("top_extensions"),
            "objects": [{"name": o["name"], "kind": o["kind"], "next_rung": o.get("next_rung")}
                        for o in env_map.get("objects", [])][:24],
            "self": {"version": __version__, "active_generation": self_map["identity"]["active_generation"],
                     "kernel": [c["path"] for c in self_map["components"] if c["region"].startswith("kernel")],
                     "organs": [c["path"] for c in self_map["components"] if c["region"].startswith("organ")],
                     "capabilities": list(self_map["capabilities"])},
            "ready": ws.ready()}


@route("POST", r"/api/genesis")
def api_genesis_complete(s: Studio, q, body):
    """The end of the first boot: the owner names what they build here and, if they like, describes it."""
    ws = _ws(s)
    name = str(body.get("name") or "").strip()
    description = str(body.get("description") or "").strip()
    patch: dict[str, Any] = {"onboarded": True}
    stored = ws.config().get("app") or {}
    if "policy_chosen" not in stored and not stored.get("onboarded"):
        patch["policy_chosen"] = False          # a first onboarding: scheduling, test runs and Kaizen wait for the owner
    if name:
        patch["workspace_name"] = name[:80]
    if body.get("use_type") in ("improve", "build", "docs", "explore"):
        patch["use_type"] = body["use_type"]
        if body["use_type"] == "explore":
            patch["autonomy"] = "observe"
    settings = ws.update_settings(patch)
    if description:
        brief = ws.brief()
        text = brief.get("text") or ""
        ws.set_brief(text=(f"# {name}\n\n{description}\n" if name else description + "\n") + (("\n" + text) if text else ""))
        if not any(g["text"] == description[:600] for g in ws.goals()):
            ws.add_goal(description.split("\n")[0][:600], kind="vision")
    ws.ledger.append("genesis.completed", {"name": name[:80], "described": bool(description),
                                           "use_type": settings["use_type"]})
    s.bus.publish("settings", settings)
    s.worker.enqueue("map")
    return {"ok": True, "settings": settings}


@route("POST", r"/api/shutdown")
def api_shutdown(s: Studio, q, body):
    threading.Timer(0.3, s.httpd_shutdown).start()
    return {"ok": True}


# --------------------------------------------------------------------- handler --

def make_handler(studio: Studio):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"RunesmithStudio/{__version__}"
        protocol_version = "HTTP/1.1"
        timeout = 120                                   # an idle keep-alive connection frees its thread

        def log_message(self, fmt, *args):         # quiet: the Studio has its own activity log
            pass

        # -- guards --------------------------------------------------------
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            port = studio.port
            return host in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

        def _authed(self) -> bool:
            cookie = SimpleCookie(self.headers.get("Cookie") or "")
            value = cookie[COOKIE].value if COOKIE in cookie else ""
            return bool(value) and secrets.compare_digest(value, studio.token)

        def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", CSP)
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, value: Any) -> None:
            self._send(status, json.dumps(value, default=str).encode("utf-8"), "application/json; charset=utf-8",
                       {"Cache-Control": "no-store", WORKSPACE_HEADER: getattr(self, '_workspace_epoch', '')})

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

        # -- verbs ---------------------------------------------------------
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self._host_ok():
                return self._error(421, "this server only answers to 127.0.0.1")
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            if parts.path == "/api/ping":
                return self._json(200, {"app": "runesmith-studio", "version": __version__,
                                        "home": home_tag(studio.ws.home) if studio.ws else None})
            if "t" in query and parts.path in ("/", "/index.html"):
                if secrets.compare_digest(query["t"][0], studio.token):
                    page = (query.get("page") or [""])[0]            # land on a page: only an in-app route
                    if not re.fullmatch(r"[a-z]+(/[a-z-]+)?", page):
                        page = ""
                    still = "?shot=1" if "shot" in query else ""   # screenshots: no live stream, so the page settles
                    return self._send(303, b"", "text/plain", {
                        "Location": "/" + still + (f"#/{page}" if page else ""),
                        "Set-Cookie": f"{COOKIE}={studio.token}; HttpOnly; SameSite=Strict; Path=/",
                        "Cache-Control": "no-store"})
            if parts.path.startswith("/api/"):
                if not self._authed():
                    return self._error(401, "open Runesmith from its launcher to get access")
                if parts.path == "/api/events":
                    return self._events(query)
                return self._dispatch("GET", parts.path, query, {})
            return self._static(parts.path)

        def do_POST(self):
            self._mutating("POST")

        def do_DELETE(self):
            self._mutating("DELETE")

        def _mutating(self, method: str) -> None:
            if not self._host_ok():
                return self._error(421, "this server only answers to 127.0.0.1")
            parts = urlsplit(self.path)
            if not parts.path.startswith("/api/") or not self._authed():
                return self._error(401, "open Runesmith from its launcher to get access")
            if self.headers.get("X-Runesmith") != "1":
                return self._error(403, "missing the X-Runesmith header")
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc.lower() != (self.headers.get("Host") or "").lower():
                return self._error(403, "cross-origin request refused")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._error(400, "the Content-Length is not a number")
            if length < 0:                                  # read(-1) would wait for the client to hang up
                return self._error(400, "the Content-Length is negative")
            if length > MAX_BODY:
                return self._error(413, "request too large")
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                return self._error(400, "the body is not JSON")
            if not isinstance(body, dict):
                return self._error(400, "the body must be a JSON object")
            self._dispatch(method, parts.path, parse_qs(parts.query), body)

        def _dispatch(self, method: str, path: str, query, body) -> None:
            for verb, pattern, handler in ROUTES:
                if verb != method:
                    continue
                match = pattern.fullmatch(path)
                if match:
                    try:
                        epoch = self.headers.get(WORKSPACE_HEADER)
                        if method == 'POST' and path == '/api/workspaces/open':
                            with studio.lock:
                                studio.check_epoch(epoch, mutating=True)
                                result = handler(studio, query, body)
                                self._workspace_epoch = studio.epoch
                        else:
                            with studio.operation(epoch, mutating=method != 'GET') as bound_epoch:
                                self._workspace_epoch = bound_epoch
                                result = handler(studio, query, body, *[unquote(g) for g in match.groups()])
                    except WorkspaceConflict as error:
                        return self._error(409, str(error))
                    except LookupError as error:                 # KeyError and the manual relay's LookupError
                        return self._error(404, f"not found: {str(error).strip(chr(39))}")
                    except (WorkspaceError, ValueError) as error:
                        return self._error(400, str(error))
                    except Exception as error:                   # report, never crash the server
                        self._log_error(path, error)
                        return self._error(500, f"{type(error).__name__}: {error}"[:400])
                    return self._json(200, result)
            return self._error(404, "no such endpoint")

        def _log_error(self, path: str, error: Exception) -> None:
            import traceback
            try:
                with studio.lock:
                    if getattr(self, '_workspace_epoch', None) != studio.epoch:
                        return  # Never write an old request's error into a new home.
                    logs = studio.ws.home / "logs"
                    logs.mkdir(parents=True, exist_ok=True)
                    with open(logs / "studio-errors.log", "a", encoding="utf-8", newline="\n") as stream:
                        stream.write(f"{_now()} {path}\n{traceback.format_exc()}\n")
            except OSError:
                pass

        def _events(self, query) -> None:
            # Bind the subscription to a home, including automatic SSE reconnects.
            # A stale page receives only a reload event, never another home's log.
            with studio.lock:
                event_bus = studio.bus
                epoch = (query.get('workspace') or [''])[0]
                stale = epoch != studio.epoch
                subscriber = None if stale else event_bus.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                if stale:
                    self._write_event({'id': 0, 'kind': 'workspace', 'data': {'reload': True}})
                    self.wfile.flush()
                    return
                since = int((query.get("since") or ["0"])[0] or 0)
                backlog = event_bus.since(since) if since else []
                self.wfile.write(b"retry: 3000\n\n")
                for event in backlog:
                    self._write_event(event)
                self.wfile.flush()
                while not getattr(studio, "closing", False):
                    try:
                        event = subscriber.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    self._write_event(event)
                    self.wfile.flush()
                    if event['kind'] == 'workspace':
                        break
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError, ValueError):
                pass
            finally:
                if subscriber is not None:
                    event_bus.unsubscribe(subscriber)
                self.close_connection = True

        def _write_event(self, event: dict[str, Any]) -> None:
            data = json.dumps(event, default=str)
            self.wfile.write(f"id: {event['id']}\nevent: {event['kind']}\ndata: {data}\n\n".encode("utf-8"))

        def _static(self, path: str) -> None:
            if path in ("", "/", "/index.html", "/genesis", "/cinema"):
                path = "/index.html"
            rel = path.lstrip("/")
            if rel.startswith("static/"):
                rel = rel[len("static/"):]
            target = (STATIC / rel).resolve()
            if STATIC not in target.parents or not target.is_file():
                return self._error(404, "not found")
            content_type = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                            ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml",
                            ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json"
                            }.get(target.suffix, mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self._send(200, target.read_bytes(), content_type, {"Cache-Control": "no-cache"})

    return Handler


# ----------------------------------------------------------------------- serve --

def _existing(home: Path) -> dict[str, Any] | None:
    """A Studio already running for this home (from its lock file), if it still answers."""
    lock = _read_json(home / "studio.lock.json", None)
    if not lock:
        return None
    try:
        with urlopen(Request(f"http://127.0.0.1:{lock['port']}/api/ping"), timeout=1.5) as reply:
            info = json.loads(reply.read().decode("utf-8"))
        if info.get("app") == "runesmith-studio" and info.get("home") == home_tag(home):
            return lock
    except (URLError, OSError, ValueError, KeyError):
        return None
    return None


class QuietServer(ThreadingHTTPServer):
    """A browser closing a connection is normal; only real errors are reported.

    On Windows, SO_REUSEADDR lets a second process bind a port that is already listening: two Studios (or any other
    program) would share one port, and the browser, with its access link, would reach the wrong one. There the port
    is taken exclusively instead. Elsewhere SO_REUSEADDR only skips TIME_WAIT, which a quick restart needs.
    """
    daemon_threads = True
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address) -> None:
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def bind(studio: Studio, port: int | None) -> ThreadingHTTPServer:
    handler = make_handler(studio)
    candidates = [port] if port is not None else [DEFAULT_PORT + i for i in range(20)] + [0]
    last: OSError | None = None
    for candidate in candidates:
        try:
            httpd = QuietServer(("127.0.0.1", candidate), handler)
        except OSError as error:
            last = error
            continue
        studio.port = httpd.server_address[1]
        try:
            studio.publish_beacon()
        except Exception:
            httpd.server_close()
            raise
        return httpd
    if port is not None:
        raise SystemExit(f"Port {port} is already in use by another program. Leave out --port to let Runesmith choose "
                         f"a free one, or choose another port. ({last})")
    raise SystemExit(f"Runesmith could not open a local port for its window. ({last})")


class InstanceLock:
    """One Studio per home: an OS file lock held for the Studio's whole life. The system releases it when the process
    ends, even by a crash, so a stale lock can never keep anyone out."""

    def __init__(self, home: Path, *, root: Path | None = None) -> None:
        self.path = home / "studio.instance.lock"
        self.handle = None
        self.root_lease = RootLease(root, STUDIO_DIR, home=home) if root is not None else None

    def acquire(self) -> bool:
        if self.handle is not None:
            raise WorkspaceConflict('This ownership lease is already held.')
        if self.root_lease and not self.root_lease.acquire():
            raise WorkspaceOwned('The source root or home overlaps another Runesmith writer (possibly this Studio). Close that writer before opening this root.')
        try:
            return self._acquire_home()
        except BaseException:
            self.close()
            raise

    def _acquire_home(self) -> bool:
        from runesmith.app.workspace_ownership import safe_control
        safe_control(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            if self.root_lease:
                self.root_lease.close()
            return False
        self.handle = handle
        return True

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        if self.root_lease:
            self.root_lease.close()


def serve(folder: Path, *, home: Path | None = None, port: int | None = None, open_browser: bool = True,
          out: Callable[[str], None] = print) -> None:
    folder = Path(folder).expanduser().resolve()
    resolved = Bindings(STUDIO_DIR).resolve(folder, home)
    probe_home = Path(resolved['home'])
    if resolved.get('recreated'):
        out(f"Runesmith's data for this folder ({probe_home.name}) was missing, so it starts fresh here. "
            "Your own files are untouched.")
    try:
        studio = Studio(folder, home)
    except WorkspaceOwned as error:                # another writer owns this home/root, or is opening it now
        running = None
        for _ in range(60):
            running = _existing(probe_home)
            if running:
                break
            time.sleep(0.25)
        if running:
            url = f"http://127.0.0.1:{running['port']}/?t={running['token']}"
            out(f"Runesmith Studio is already open for {folder}.\n  {url}")
            if open_browser:
                webbrowser.open(url)
        else:
            out(str(error))
        return
    try:
        httpd = bind(studio, port)
    except BaseException:
        studio.close()
        raise

    def shutdown() -> None:
        studio.closing = True
        studio.close()
        httpd.shutdown()

    studio.httpd_shutdown = shutdown
    url = f"http://127.0.0.1:{studio.port}/?t={studio.token}"
    out(f"Runesmith Studio {__version__} is running for {folder}\n  Open: {url}\n  (Keep this window open; press Ctrl+C to stop.)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        out("Stopping Runesmith Studio…")
    finally:
        studio.closing = True
        studio.close()
        httpd.server_close()


def main(argv: list[str] | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="runesmith-studio", description="Open Runesmith Studio for a folder.")
    parser.add_argument("folder", nargs="?", default=".")
    parser.add_argument("--home", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    serve(Path(args.folder), home=Path(args.home) if args.home else None, port=args.port,
          open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
