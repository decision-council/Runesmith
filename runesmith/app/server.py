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

STATIC = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 7300
STUDIO_DIR = Path.home() / ".runesmith-studio"
MAX_BODY = 4_000_000
COOKIE = "rs_session"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def home_tag(home: Path) -> str:
    return hashlib.sha256(str(Path(home).resolve()).encode("utf-8")).hexdigest()[:12]


class Studio:
    """The open workspace and its worker. The Studio can switch to another folder without restarting."""

    def __init__(self, root: Path, home: Path | None = None, *, token: str | None = None) -> None:
        self.bus = EventBus()
        self.token = token or secrets.token_urlsafe(24)
        self.lock = threading.RLock()
        self.ws: Workspace | None = None
        self.worker: Worker | None = None
        self.port: int | None = None
        self.started = _now()
        self.closing = False
        self.httpd_shutdown: Callable[[], None] = lambda: None
        self.open(root, home)

    def open(self, root: Path, home: Path | None = None) -> Workspace:
        ws = Workspace(Path(root), home)              # may raise WorkspaceError before anything is closed
        with self.lock:
            if self.worker:
                self.worker.close()
            self.ws, self.worker = ws, Worker(ws, self.bus)
            self.worker.start()
        self._remember(ws)
        ws.ledger.append("studio.opened", {"version": __version__})
        self.bus.publish("workspace", {"path": str(ws.root), "name": ws.settings()["workspace_name"]})
        return ws

    def close(self) -> None:
        with self.lock:
            if self.worker:
                self.worker.close()

    @staticmethod
    def recent() -> list[dict[str, Any]]:
        rows = _read_json(STUDIO_DIR / "studio.json", {}).get("recent", [])
        return [r for r in rows if Path(r.get("path", "")).is_dir()]

    def _remember(self, ws: Workspace) -> None:
        try:
            rows = [r for r in self.recent() if r["path"] != str(ws.root)]
            rows.insert(0, {"path": str(ws.root), "name": ws.settings()["workspace_name"], "opened": _now()})
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


@route("POST", r"/api/worker/run")
def api_worker_run(s: Studio, q, body):
    job = body.get("job", "round")
    params = {k: v for k, v in (body.get("params") or {}).items() if k in ("probe", "milestone")}
    return s.worker.enqueue(job, **params)


@route("POST", r"/api/worker/(pause|resume|stop)")
def api_worker_control(s: Studio, q, body, action):
    {"pause": s.worker.pause, "resume": s.worker.resume, "stop": s.worker.stop_current}[action]()
    return s.worker.snapshot()


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
    return {"plan": ws.plan(), "milestones": ws.milestones(), "ready": ws.ready()["plan"]}


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


@route("POST", r"/api/inference/instruments")
def api_instrument_save(s: Studio, q, body):
    saved = _ws(s).save_instrument(body.get("name", ""), body.get("spec") or {}, body.get("key"), body.get("roles"))
    s.bus.publish("inference", {})
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
                              key_value=body.get("key"))


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
    return {"notes": ws.notes.all(), "counts": ws.notes.counts(), "read_notes": ws.settings()["read_notes"]}


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


@route("POST", r"/api/manual/([A-Za-z0-9_.-]+)/answer")
def api_manual_answer(s: Studio, q, body, request_id):
    result = _ws(s).answer_manual(request_id, body.get("text", ""), body.get("model") or None, bool(body.get("force")))
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
    return {"current": str(_ws(s).root), "recent": Studio.recent()}


@route("POST", r"/api/workspaces/open")
def api_workspace_open(s: Studio, q, body):
    path = Path(str(body.get("path") or "")).expanduser()
    if body.get("create"):
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise WorkspaceError(f"{path} is not a folder")
    ws = s.open(path)
    return {"ok": True, "path": str(ws.root)}


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
                       {"Cache-Control": "no-store"})

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
                        result = handler(studio, query, body, *[unquote(g) for g in match.groups()])
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
                logs = studio.ws.home / "logs"
                logs.mkdir(parents=True, exist_ok=True)
                with open(logs / "studio-errors.log", "a", encoding="utf-8", newline="\n") as stream:
                    stream.write(f"{_now()} {path}\n{traceback.format_exc()}\n")
            except OSError:
                pass

        def _events(self, query) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            subscriber = studio.bus.subscribe()
            try:
                since = int((query.get("since") or ["0"])[0] or 0)
                backlog = studio.bus.since(since) if since else []
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
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError, ValueError):
                pass
            finally:
                studio.bus.unsubscribe(subscriber)
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
        return httpd
    raise SystemExit(f"could not open a local port: {last}")


class InstanceLock:
    """One Studio per home: an OS file lock held for the Studio's whole life. The system releases it when the process
    ends, even by a crash, so a stale lock can never keep anyone out."""

    def __init__(self, home: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        self.path = home / "studio.instance.lock"
        self.handle = None

    def acquire(self) -> bool:
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
            return False
        self.handle = handle
        return True


def serve(folder: Path, *, home: Path | None = None, port: int | None = None, open_browser: bool = True,
          out: Callable[[str], None] = print) -> None:
    folder = Path(folder).expanduser().resolve()
    probe_home = (Path(home).resolve() if home else folder / ".runesmith")
    instance = InstanceLock(probe_home)
    if not instance.acquire():                      # another Studio has this folder, or is opening it right now
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
            out(f"Another Runesmith Studio is opening {folder}; it did not answer yet. Try again in a moment.")
        return
    studio = Studio(folder, home)
    httpd = bind(studio, port)

    def shutdown() -> None:
        studio.closing = True
        studio.close()
        httpd.shutdown()

    studio.httpd_shutdown = shutdown
    url = f"http://127.0.0.1:{studio.port}/?t={studio.token}"
    lock = {"pid": os.getpid(), "port": studio.port, "token": studio.token, "started": _now(), "folder": str(folder)}
    _write_json(studio.ws.home / "studio.lock.json", lock)
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
        try:
            if _read_json(studio.ws.home / "studio.lock.json", {}).get("token") == studio.token:
                (studio.ws.home / "studio.lock.json").unlink()
        except OSError:
            pass


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
