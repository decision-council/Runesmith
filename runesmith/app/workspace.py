"""The workspace service: everything the Studio shows and does, as plain Python.

A ``Workspace`` is one folder Runesmith lives in, with its home at
``<folder>/.runesmith``. The web server is a thin layer over this class, so
everything here is testable without a browser.

Rules the service keeps:

* **It never edits the owner's files on its own.** Work produces proposals: repairs
  the held-out judge accepted, and drafts a model wrote (plans, first files), which
  are labelled as unverified. A proposal is applied only by an explicit ``apply_*``
  call, and only if every file is still as the proposal expects. A backup is kept,
  and ``undo_*`` restores it.
* **Keys go to the key store and never come back.** Listings say whether a key is
  saved, never what it is.
* **Unknown stays unknown.** Views report what was measured and say plainly what
  was not.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import threading
import time
import uuid
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from runesmith import __version__, generations
from runesmith.app.providers import PRESET_BY_ID, PRESETS, public_presets
from runesmith.config import build_router, load_config
from runesmith.home import init_home
from runesmith.keystore import KeyStore
from runesmith.ledger import Ledger
from runesmith.notes import NoteStore
from runesmith.objects.code import encode_like
from runesmith import atomic

LIBRARY = Path(__file__).resolve().parent.parent / "library"
ROLES = ("repair", "kaizen", "plan", "acceptance")
ROLE_LABELS = {"repair": "Worker: repairs code", "kaizen": "Improver: improves Runesmith itself",
               "plan": "Planner: drafts plans and first files",
               "acceptance": "Checker: proposes acceptance checks"}
PLAN_FALLBACK = ("plan", "kaizen", "repair")          # the planner borrows another role's instruments if it has none

DEFAULT_SETTINGS: dict[str, Any] = {
    "onboarded": False,
    "workspace_name": "",
    "use_type": "",                 # improve | build | docs | explore | numbers (chosen at onboarding)
    "autonomy": "propose",          # observe: map and watch only; propose: also work and propose fixes
    # The next three are the owner's explicit first-run choices (Overview, Settings). Finishing the introduction turns
    # none of them on: scheduled rounds spend model calls, running tests executes the project's code, and Kaizen
    # rewrites Runesmith's own organ.
    "auto_work": False,             # run rounds on a schedule
    "interval_minutes": 60,
    "probe_tests": False,           # run objects' own tests (always on throwaway copies) while mapping
    "exclude": [],                  # object names Runesmith must never probe or work on
    "max_objects": 50,
    "read_notes": True,             # give open notes to the model as the owner's guidance
    "kaizen": False,                # allow self-improvement steps
    "policy_chosen": False,         # the owner has made the three choices above
    "min_experience": 8,
    "kaizen_every": 8,
    "theme": "auto",
    "build_steps": False,          # executable build checks are explicitly enabled per workspace
    "build_apply": False,          # only owner acceptance + unchanged source + a root-bound grant can apply
    "build_paths": [],
    "checks_autopilot": False,    # Runesmith approves proposed checks that pass every gate (acceptance_autopilot)
    "full_speed": False,          # the next scheduled step starts as soon as one ends while models answer (J11-F21)
}
# Homes onboarded before the explicit choices existed keep the behaviour they were onboarded with, until their owner
# chooses (``policy_chosen`` absent from the stored settings marks such a home).
LEGACY_ONBOARDED: dict[str, Any] = {"auto_work": True, "probe_tests": True, "kaizen": True}
SETTING_TYPES: dict[str, Any] = {
    "onboarded": bool, "workspace_name": str, "use_type": str, "autonomy": str, "auto_work": bool,
    "interval_minutes": (int, float), "probe_tests": bool, "exclude": list, "max_objects": int, "read_notes": bool,
    "kaizen": bool, "min_experience": int, "kaizen_every": int, "theme": str, "policy_chosen": bool,
    "build_steps": bool, "build_apply": bool, "build_paths": list, "checks_autopilot": bool, "full_speed": bool,
}
CHOICES = {"autonomy": {"observe", "propose"}, "theme": {"auto", "light", "dark"},
           "use_type": {"", "improve", "build", "docs", "explore", "numbers"}}
RANGES = {"interval_minutes": (1, 7 * 24 * 60), "max_objects": (1, 500), "min_experience": (2, 10_000),
          "kaizen_every": (1, 10_000)}
MILESTONE_STATES = ("open", "doing", "done", "dropped")
GENERIC_NAMES = {"readme.md", "readme", "readme.txt", "readme.rst", "index.md", "index.html", "index.htm", "license",
                 "license.md", "changelog.md", "changes.md", "contributing.md", "notes.md", "todo.md", "main.py", "app.js"}
MAX_DRAFT_FILES, MAX_DRAFT_FILE_BYTES = 12, 60_000


OBSERVE_NO_CALLS = ("Observe mode reads and reports only, so no model was asked. Choose “propose” in Settings to let "
                    "Runesmith think and draft.")


class ObserveRouter:
    """What ``Workspace.router()`` returns in observe mode: the same call shape, and every call refused."""

    roles: dict[str, list[str]] = {}
    instruments: dict[str, Any] = {}

    def call(self, role: str, **_: Any):
        raise WorkspaceError(OBSERVE_NO_CALLS)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _key_file_ref(spec: dict[str, Any]) -> str | None:
    """A key read from a local settings file at call time (``*_env_file`` + ``*_key``), named but never read here."""
    for prefix in ("api_key", "token"):
        if spec.get(prefix + "_env_file") and spec.get(prefix + "_key"):
            return f"{spec[prefix + '_key']} in {spec[prefix + '_env_file']}"
    return None


def _write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_bytes((json.dumps(value, indent=1, default=str) + "\n").encode("utf-8"))
    atomic.replace(tmp, path)


def _tail_lines(path: Path, limit: int) -> list[str]:
    """The last ``limit`` non-empty lines of a text file without reading all of it."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, "rb") as stream:
        stream.seek(0, 2)
        size, data = stream.tell(), b""
        while size > 0 and data.count(b"\n") <= limit:
            step = min(65536, size)
            size -= step
            stream.seek(size)
            data = stream.read(step) + data
    return [line.decode("utf-8", "replace") for line in data.splitlines() if line.strip()][-limit:]


def _lf(data: bytes | None) -> str | None:
    """A file's text as Runesmith compares it: no byte-order mark, LF line endings."""
    return None if data is None else data.decode("utf-8-sig", "replace").replace("\r\n", "\n")


class WorkspaceError(RuntimeError):
    """A request the workspace refuses, with a message meant for the owner."""


class Workspace:
    def __init__(self, root: Path, home: Path | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise WorkspaceError(f"{self.root} is not a folder")
        self.home = Path(home).resolve() if home else self.root / ".runesmith"
        created = init_home(self.home)["created"]
        self.keys = KeyStore(self.home)
        self.notes = NoteStore(self.home)
        self.ledger = Ledger(self.home / "ledger.jsonl")
        self._lock = threading.RLock()
        self._ops_lock = threading.Lock()
        # Model calls since the Studio started: answered (an answer came back, usable or not) or unanswered (busy,
        # limited, unreachable). Full speed reads it to tell a step the models answered from one they did not.
        self.call_tally = {"answered": 0, "unanswered": 0}
        if created:
            # A Studio home starts with no instrument: the owner chooses where thinking comes from.
            config = self.config()
            config["instruments"], config["roles"] = {}, {role: [] for role in ROLES}
            self.save_config(config)
        self.requalification = self._requalify_if_needed()

    def _requalify_if_needed(self) -> dict[str, Any] | None:
        """After an update of Runesmith, re-qualify the active organs under the new kernel (same bytes, re-checked)."""
        active = generations.active(self.home)
        if not active:
            return None
        try:
            manifest = generations.load(self.home / "generations" / active)
        except (OSError, ValueError):
            return None
        if manifest.get("kernel_digest") == generations.kernel_digest():
            return None
        from runesmith.doctor import requalify
        try:
            return requalify(self.home)
        except Exception as error:                        # surfaced in health; the owner decides
            return {"requalified": False, "error": str(error)[:300]}

    # ------------------------------------------------------------ config & settings --

    def config(self) -> dict[str, Any]:
        config = load_config(self.home)
        config.setdefault("instruments", {})
        config.setdefault("roles", {})
        return config

    def save_config(self, config: dict[str, Any]) -> None:
        with self._lock:
            _write_json(self.home / "runesmith.json", config)

    def seed(self) -> str:
        """A per-home secret that fixes the experience/validation split and trial coins for this home."""
        with self._lock:
            config = self.config()
            app = config.setdefault("app", {})
            if not app.get("seed"):
                app["seed"] = secrets.token_hex(16)
                self.save_config(config)
            return app["seed"]

    def settings(self) -> dict[str, Any]:
        stored = {k: v for k, v in (self.config().get("app") or {}).items() if k in DEFAULT_SETTINGS}
        merged = dict(DEFAULT_SETTINGS)
        if stored.get("onboarded") and "policy_chosen" not in stored:
            merged.update(LEGACY_ONBOARDED)
        merged.update(stored)
        if not merged["workspace_name"]:
            merged["workspace_name"] = self.root.name or str(self.root)
        return merged

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in (patch or {}).items():
            if key not in SETTING_TYPES:
                raise WorkspaceError(f"unknown setting {key!r}")
            expected = SETTING_TYPES[key]
            if expected is bool:
                if not isinstance(value, bool):
                    raise WorkspaceError(f"{key} is on or off")
            elif isinstance(value, bool) or not isinstance(value, expected):
                raise WorkspaceError(f"{key} has the wrong type")
            if key in CHOICES and value not in CHOICES[key]:
                raise WorkspaceError(f"{key} must be one of {sorted(CHOICES[key])}")
            if key in RANGES and not RANGES[key][0] <= value <= RANGES[key][1]:
                raise WorkspaceError(f"{key} must be between {RANGES[key][0]} and {RANGES[key][1]}")
            if key == "exclude":
                value = sorted({str(v).strip() for v in value if str(v).strip()})
            if key == "build_paths":
                value = sorted({str(v).strip().rstrip('/') for v in value if str(v).strip()})
                # "." is the whole folder: for a new project nobody knows its files yet (journey J11-B1). Runesmith's
                # own records and version-control folders stay out of reach, as for every path.
                if any(v != '.' and not self._safe_rel(v) for v in value):
                    raise WorkspaceError("Allowed files or folders must be inside this folder and not Runesmith's own "
                                         "records. Use . for the whole folder.")
            if key == "workspace_name":
                value = value.strip()[:80]
            clean[key] = value
        with self._lock:
            config = self.config()
            if clean.get("policy_chosen"):
                # Choosing keeps exactly what the owner was shown: a home onboarded before the explicit choices
                # still runs on its legacy values, so those become stored choices rather than silently changing.
                effective = self.settings()
                for key in LEGACY_ONBOARDED:
                    if key not in clean and key not in (config.get("app") or {}):
                        clean[key] = effective[key]
            config["app"] = dict(config.get("app") or {}, **clean)
            self.save_config(config)
            if "build_apply" in clean or "build_paths" in clean:
                _write_json(self.home / "BUILD_GRANT.json", {"id":uuid.uuid4().hex, "root":str(self.root),
                    "home":str(self.home), "enabled":config["app"].get("build_apply", False),
                    "paths":config["app"].get("build_paths", []), "utc":_now(), "by":"operator"})
        self.ledger.append("settings.changed", {"keys": sorted(clean)})
        return self.settings()

    # ------------------------------------------------------------- goals and brief --

    def goals(self) -> list[dict[str, Any]]:
        return _read_json(self.home / "GOALS.json", [])

    def add_goal(self, text: str, *, kind: str = "outcome") -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise WorkspaceError("a goal needs some words")
        goal = {"id": uuid.uuid4().hex[:10], "text": text[:600], "kind": (kind or "outcome")[:30], "status": "active",
                "created": _now()}
        with self._lock:
            goals = self.goals()
            goals.append(goal)
            _write_json(self.home / "GOALS.json", goals)
        self.ledger.append("goal.added", {"id": goal["id"], "text": goal["text"][:200]})
        return goal

    def update_goal(self, goal_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            goals = self.goals()
            for goal in goals:
                if goal["id"] == goal_id:
                    if str(patch.get("text") or "").strip():
                        goal["text"] = str(patch["text"]).strip()[:600]
                    if patch.get("status") in ("active", "done", "paused"):
                        goal["status"] = patch["status"]
                    goal["updated"] = _now()
                    _write_json(self.home / "GOALS.json", goals)
                    self.ledger.append("goal.updated", {"id": goal_id, "status": goal["status"]})
                    return goal
        raise KeyError(goal_id)

    def remove_goal(self, goal_id: str) -> None:
        with self._lock:
            goals = self.goals()
            if not any(g["id"] == goal_id for g in goals):
                raise KeyError(goal_id)
            _write_json(self.home / "GOALS.json", [g for g in goals if g["id"] != goal_id])
        self.ledger.append("goal.removed", {"id": goal_id})

    def brief(self) -> dict[str, Any]:
        data = _read_json(self.home / "BRIEF.json", {"text": "", "blueprints": [], "updated": None})
        data["blueprints"] = [dict(b, exists=(self.root / b["path"]).is_file()) for b in data.get("blueprints", [])]
        return data

    def set_brief(self, text: str | None = None, blueprints: list[str] | None = None) -> dict[str, Any]:
        with self._lock:
            data = _read_json(self.home / "BRIEF.json", {"text": "", "blueprints": []})
            if text is not None:
                data["text"] = str(text)[:20000]
            if blueprints is not None:
                cleaned = []
                for entry in blueprints:
                    rel = self._safe_rel(str(entry), allow_missing=False)
                    if rel and {"path": rel} not in cleaned:
                        cleaned.append({"path": rel})
                data["blueprints"] = cleaned[:50]
            data["updated"] = _now()
            _write_json(self.home / "BRIEF.json", {k: data.get(k) for k in ("text", "blueprints", "updated")})
        self.ledger.append("brief.updated", {"chars": len(data["text"]), "blueprints": len(data["blueprints"])})
        return self.brief()

    def candidate_blueprints(self, limit: int = 80) -> list[dict[str, Any]]:
        """Documents in the workspace that could serve as a brief or blueprint, for the picker. Never through a
        link or junction: a linked folder can hold someone's private documents, and a blueprint goes to a model."""
        from runesmith.envmap import walk_files
        found = []
        for path in sorted(walk_files(self.root)):
            if len(found) >= limit:
                break
            if path.suffix.lower() in (".md", ".txt", ".rst", ".markdown") and self.home not in path.parents:
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size < 5_000_000:
                    found.append({"path": path.relative_to(self.root).as_posix(), "bytes": size})
        return found

    def blueprint_text(self, max_chars: int = 12000) -> str:
        """The brief's blueprint documents, bounded, for a model's context."""
        chunks, used = [], 0
        for entry in self.brief()["blueprints"]:
            if not self._safe_rel(entry["path"], allow_missing=False):     # checked again: it may be a link by now
                continue
            path = self.root / entry["path"]
            text = path.read_text(encoding="utf-8", errors="replace")
            room = max_chars - used
            if room <= 200:
                break
            piece = text if len(text) <= room else text[:room] + "\n... (truncated)"
            chunks.append(f"--- {entry['path']} ---\n{piece}")
            used += len(piece)
        return "\n\n".join(chunks)

    # ------------------------------------------------------------------ inference --

    def inference(self) -> dict[str, Any]:
        config = self.config()
        instruments = []
        for name, spec in config["instruments"].items():
            secret = spec.get("api_key_secret") or spec.get("token_secret")
            preset = PRESET_BY_ID.get(spec.get("preset") or "")
            base_url = str(spec.get("base_url") or "")
            instruments.append({
                "name": name, "kind": spec.get("kind"), "model": spec.get("model"), "base_url": spec.get("base_url"),
                "fallback_models": list(spec.get('fallback_models') or []),
                "preset": spec.get("preset"), "label": spec.get("label") or (preset or {}).get("label") or name,
                "local": spec.get("kind") != "milliner" and (bool((preset or {}).get("local")) or "127.0.0.1" in base_url
                                                             or "localhost" in base_url),
                "key": {"secret": secret, "saved": bool(secret and self.keys.has(secret)),
                        "env": spec.get("api_key_env") or spec.get("token_env") or _key_file_ref(spec),
                        "needed": (preset or {}).get("key", "optional")},
                "usable": self._usable(name, spec),
                "roles": [role for role in ROLES if name in (config["roles"].get(role) or [])],
                "note": spec.get("note")})
        roles = {role: list(config["roles"].get(role) or []) for role in ROLES}
        return {"instruments": instruments, "roles": roles, "role_labels": ROLE_LABELS, "keys": self.keys.describe(),
                "presets": public_presets(spec.get("kind") for spec in (self.config().get("instruments") or {}).values()),
                "ready": self.ready(), "stats": self.call_stats()}

    def _usable(self, name: str, spec: dict[str, Any] | None) -> bool:
        if not spec:
            return False
        secret = spec.get("api_key_secret") or spec.get("token_secret")
        if secret and not self.keys.has(secret):
            return False
        preset = PRESET_BY_ID.get(spec.get("preset") or "") or {}
        needs_key = preset.get("key") == "required" or spec.get("kind") == "milliner"
        if needs_key and not (secret or spec.get("api_key_env") or spec.get("token_env") or _key_file_ref(spec)):
            return False
        if spec.get("kind") in ("openai", "milliner") and not (spec.get("base_url") and spec.get("model")):
            return False
        return spec.get("kind") in ("openai", "milliner", "manual", "scripted")

    def ready(self) -> dict[str, Any]:
        """Which roles can work: a role is ready when it names at least one fully set-up instrument."""
        config = self.config()
        usable = {role: [n for n in (config["roles"].get(role) or []) if self._usable(n, config["instruments"].get(n))]
                  for role in ROLES}
        plan_source = next((r for r in PLAN_FALLBACK if usable[r]), None)
        # The checker writes few, decisive calls; it uses the planner's instruments unless the owner picks its own.
        return {"repair": bool(usable["repair"]), "kaizen": bool(usable["kaizen"]), "plan": plan_source is not None,
                "plan_source": plan_source, "acceptance": bool(usable["acceptance"]) or plan_source is not None, "usable": usable, "any": any(usable.values()),
                "instruments": len(config["instruments"])}

    def router(self, *, on_call=None, backoff_s: tuple[float, ...] | None = None, skip: set[str] | None = None):
        """A router over the usable instruments only (minus ``skip``); the planner borrows another role's instruments.

        In observe mode every Studio model call is refused here, where they all pass (rule I1 of the coverage plan),
        instead of relying on each job to check.
        """
        if self.settings()["autonomy"] == "observe":
            return ObserveRouter()
        config = self.config()
        ready = self.ready()
        roles = {role: [n for n in names if n not in (skip or set())] for role, names in ready["usable"].items()}
        roles = {role: names for role, names in roles.items() if names}
        if not roles.get("plan"):
            source = next((r for r in PLAN_FALLBACK if roles.get(r)), None)
            if source:
                roles["plan"] = list(roles[source])
        if not roles.get("acceptance") and roles.get("plan"):
            roles["acceptance"] = list(roles["plan"])
        instruments = {n: config["instruments"][n] for names in roles.values() for n in names}
        kwargs: dict[str, Any] = {"on_call": on_call}
        if backoff_s is not None:
            kwargs["backoff_s"] = backoff_s
        return build_router({"instruments": instruments, "roles": roles}, home=self.home, **kwargs)

    def save_instrument(self, name: str, spec: dict[str, Any], key_value: str | None = None,
                        roles: list[str] | None = None) -> dict[str, Any]:
        name = (name or "").strip()
        if not name or len(name) > 40 or not all(c.isalnum() or c in "-_." for c in name):
            raise WorkspaceError("a name uses letters, digits, '-', '_' or '.' (at most 40)")
        kind = spec.get("kind")
        if kind not in ("openai", "milliner", "manual"):
            raise WorkspaceError("the kind must be openai, milliner or manual")
        clean = {k: spec[k] for k in ("kind", "model", "base_url", "preset", "label", "json_mode", "timeout_s", "note",
                                      "api_key_env", "token_env", "caller_tag", "budget_tag")
                 if spec.get(k) not in (None, "")}
        for key in ("model", "base_url", "label", "note", "caller_tag", "budget_tag"):
            if key in clean:
                clean[key] = str(clean[key]).strip()[:300]
        # Kept on save (review of J11-B8): the Groq preset's request limit (8,000 tokens a minute on its free tier) was
        # dropped here, so a model added in the Studio was never checked for size before sending; and a model's own
        # reasoning effort.
        if spec.get("max_request_tokens") not in (None, ""):
            limit = spec["max_request_tokens"]
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1000 <= limit <= 10_000_000:
                raise WorkspaceError("the request limit is a whole number of tokens from 1000 up")
            clean["max_request_tokens"] = limit
        if spec.get("reasoning_effort") not in (None, ""):
            from runesmith.config import REASONING_EFFORTS
            if spec["reasoning_effort"] not in REASONING_EFFORTS:
                raise WorkspaceError("the reasoning effort is low, medium or high")
            clean["reasoning_effort"] = spec["reasoning_effort"]
        if kind == 'milliner' and 'fallback_models' in spec:
            models = spec['fallback_models']
            if (not isinstance(models, list) or len(models) > 5 or
                    any(not isinstance(m, str) or not m.strip() or len(m) > 300 for m in models)):
                raise WorkspaceError('Use up to five fallback model names.')
            clean['fallback_models'] = list(dict.fromkeys(m.strip() for m in models if m.strip() != clean.get('model')))
        if kind in ("openai", "milliner") and not (clean.get("base_url") and clean.get("model")):
            raise WorkspaceError("an endpoint address and a model name are needed")
        if clean.get("base_url") and not str(clean["base_url"]).startswith(("http://", "https://")):
            raise WorkspaceError("the endpoint address starts with http:// or https://")
        if kind == "manual":
            clean.setdefault("model", "a chat window")
            clean.setdefault("timeout_s", 3600)
        key_value = (key_value or "").strip() or None
        if key_value:
            try:
                self.keys.set(name, key_value)
            except ValueError as error:
                raise WorkspaceError(str(error)) from error
        existing = self.config()["instruments"].get(name, {})
        if key_value or existing.get("api_key_secret") or existing.get("token_secret"):
            clean["token_secret" if kind == "milliner" else "api_key_secret"] = name
        if kind == "milliner":
            clean.setdefault("caller_tag", "runesmith/studio")
        with self._lock:
            config = self.config()
            config["instruments"][name] = clean
            for role in roles or []:
                if role in ROLES and name not in config["roles"].setdefault(role, []):
                    config["roles"][role].append(name)
            self.save_config(config)
        self.ledger.append("instrument.saved", {"name": name, "kind": kind, "model": clean.get("model"),
                                                "key_saved": bool(key_value), "roles": roles or []})
        return next(i for i in self.inference()["instruments"] if i["name"] == name)

    def remove_instrument(self, name: str) -> None:
        with self._lock:
            config = self.config()
            if name not in config["instruments"]:
                raise KeyError(name)
            config["instruments"].pop(name)
            for role in list(config["roles"]):
                config["roles"][role] = [n for n in config["roles"][role] if n != name]
            self.save_config(config)
        self.keys.delete(name)
        self.ledger.append("instrument.removed", {"name": name})

    def set_roles(self, roles: dict[str, list[str]]) -> dict[str, list[str]]:
        with self._lock:
            config = self.config()
            names = set(config["instruments"])
            for role in ROLES:
                if role in roles:
                    config["roles"][role] = [n for n in dict.fromkeys(roles[role] or []) if n in names]
            self.save_config(config)
        self.ledger.append("roles.changed", {r: roles.get(r) or [] for r in ROLES if r in roles})
        return {role: list(self.config()["roles"].get(role) or []) for role in ROLES}

    def test_instrument(self, name: str) -> dict[str, Any]:
        from runesmith.app.providers import test_instrument
        spec = self.config()["instruments"].get(name)
        if not spec:
            raise KeyError(name)
        result = test_instrument(name, spec, self.home)
        self.ledger.append("instrument.tested", {"name": name, "ok": result["ok"]})
        return result

    def list_models(self, *, name: str | None = None, preset: str | None = None, base_url: str | None = None,
                    key_value: str | None = None, provider: str = "") -> dict[str, Any]:
        from runesmith.app.providers import list_models
        key = (key_value or "").strip()
        kind = (PRESET_BY_ID.get(preset) or {}).get("kind", "openai")
        if name:
            spec = self.config()["instruments"].get(name) or {}
            kind = spec.get("kind", kind)
            if (base_url and base_url.rstrip('/') != str(spec.get('base_url', '')).rstrip('/')
                    and not key):
                return {"ok": False, "models": [], "detail": "Supply a key explicitly for a different endpoint."}
            base_url = base_url or spec.get("base_url")
            secret = spec.get("api_key_secret") or spec.get("token_secret")
            key = key or (self.keys.supplier(secret)() if secret else "")
            if not key:
                from runesmith.instruments import secret_from
                prefix = 'token' if kind == 'milliner' else 'api_key'
                key = secret_from(spec.get(prefix+'_env'), spec.get(prefix+'_env_file'),
                                  spec.get(prefix+'_key'))()
        if not base_url and preset:
            base_url = (PRESET_BY_ID.get(preset) or {}).get("base_url")
        if not base_url:
            return {"ok": False, "models": [], "detail": "no endpoint address"}
        return list_models(base_url, key, kind=kind, provider=provider)

    def record_call(self, event: dict[str, Any]) -> None:
        """Count one model call per instrument (the router's on_call hook), for the operations view."""
        name = event.get("instrument") or event.get("name") or "?"
        with self._ops_lock:
            stats = _read_json(self.home / "OPERATIONS.json", {"instruments": {}})
            row = stats["instruments"].setdefault(name, {"calls": 0, "ok": 0, "errors": 0, "latency_s": 0.0})
            row["calls"] += 1
            row["ok" if event.get("ok") else "errors"] += 1
            self.call_tally["answered" if event.get("ok") or event.get("error_kind") == "output" else "unanswered"] += 1
            row["latency_s"] = round(row["latency_s"] + float(event.get("latency_s") or 0), 3)
            row["last_utc"] = _now()
            row["model"] = event.get("model")
            for field in ('tokens_in', 'tokens_out'):
                if isinstance(event.get(field), (int, float)):
                    row[field] = row.get(field, 0) + event[field]
            if isinstance(event.get('est_usd'), (int, float)):
                row['estimated_usd'] = round(row.get('estimated_usd', 0) + event['est_usd'], 8)
                row['costed_calls'] = row.get('costed_calls', 0) + 1
            if not event.get("ok"):
                row["last_error"] = (event.get("error") or event.get("error_kind") or "")[:200]
            _write_json(self.home / "OPERATIONS.json", stats)
        self.ledger.append('instrument.call', {k:event[k] for k in ('key','attempt','role','instrument','model',
            'provider','requested_model','job_id','request_id','ok','error_kind','latency_s','tokens_in','tokens_out','est_usd','accounting','cached','prompt_bytes')
            if k in event})

    def call_stats(self) -> dict[str, Any]:
        return _read_json(self.home / "OPERATIONS.json", {"instruments": {}})["instruments"]

    # ------------------------------------------------------------------ the maps --

    def environment_map(self) -> dict[str, Any] | None:
        return _read_json(self.home / "ENVIRONMENT.json", None)

    def map_environment(self, *, probe: bool | None = None) -> dict[str, Any]:
        from runesmith.envmap import write_environment_map
        settings = self.settings()
        probe = settings["probe_tests"] if probe is None else probe
        env_map = write_environment_map(self.home / "ENVIRONMENT.json", self.root, probe=probe,
                                        max_objects=int(settings["max_objects"]), scratch=self.home / "scratch",
                                        exclude=set(settings["exclude"]), previous=self.environment_map())
        self.ledger.append("environment_map.written", {"map_digest": env_map["map_digest"],
                                                       "objects": len(env_map["objects"]), "probed": probe})
        return env_map

    def sessions(self) -> list[dict[str, Any]]:
        """Every session record, oldest first. Records never change once written, so each file is read once."""
        root = self.home / "sessions"
        cache = self.__dict__.setdefault("_session_cache", {})
        rows = []
        for path in sorted(root.glob("*.json")) if root.exists() else []:
            record = cache.get(path.name)
            if record is None:
                record = _read_json(path, None)
                if not isinstance(record, dict):
                    continue
                record.setdefault("key", path.stem)
                cache[path.name] = record
            rows.append(record)
        return rows

    def proposal_counts(self) -> dict[str, int]:
        """Proposals by state, without computing any diff (for the summary)."""
        state = self.proposal_state()
        counts: Counter = Counter()
        for folder in (self.home / "experience").glob("*/verified_fix.json.gz"):
            name = state.get(folder.parent.name, {}).get("state", "waiting")
            counts["outdated" if name == "waiting" and self._fix_outdated(folder.parent.name) else name] += 1
        return dict(counts)

    def _fix_outdated(self, key: str) -> bool:
        """True when a fix's files changed after it was made, so Apply would refuse it (journey J6-F4: each repair
        saw every bug and fixed all four files; after one was applied, the others still said "waiting for you")."""
        try:
            p = self._proposal(key)
        except (OSError, ValueError, KeyError, WorkspaceError):
            return False
        repo = Path(p["task"]["repo"]).resolve()
        for rel in p["fix"]:
            target = repo / rel
            current = target.read_bytes() if target.is_file() else None
            if current is None or _lf(current) != (p["parent"].get(rel) or "").lstrip("\ufeff"):
                return True
        return False

    def self_map(self, *, refresh: bool = False) -> dict[str, Any]:
        cached = None if refresh else _read_json(self.home / "SELF_MAP.json", None)
        if cached and cached.get("identity", {}).get("active_generation") == generations.active(self.home):
            return cached
        from runesmith.selfmap import write_self_map
        return write_self_map(self.home / "SELF_MAP.json", home=self.home, records=self.sessions())

    def self_view(self) -> dict[str, Any]:
        self_map = self.self_map()
        kernel = [c for c in self_map["components"] if c.get("region", "").startswith("kernel")]
        organs = [c for c in self_map["components"] if c.get("region", "").startswith("organ")]
        return {"identity": self_map["identity"], "regions": self_map["regions"], "affordances": self_map["affordances"],
                "envelope": self_map["default_envelope"], "capabilities": self_map["capabilities"],
                "open_targets": self_map["open_targets"][:6], "improvement_options": self_map["improvement_options"],
                "lineage": self_map["lineage"], "unknowns": self_map["unknowns"],
                "kernel": [{k: c.get(k) for k in ("path", "purpose", "lines", "public_symbols")} for c in kernel],
                "organs": [{k: c.get(k) for k in ("path", "purpose", "lines", "public_symbols")} for c in organs],
                "active_organs": self._active_organ_files()}

    def _active_organ_files(self) -> list[dict[str, Any]]:
        active = generations.active(self.home)
        folder = self.home / "generations" / str(active) / "organs"
        return [{"path": p.name, "lines": p.read_text(encoding="utf-8").count("\n") + 1}
                for p in sorted(folder.glob("*.py"))] if folder.exists() else []

    def development_view(self) -> dict[str, Any]:
        env_map = self.environment_map() or {"objects": []}
        objects = [{"name": o["name"], "kind": o["kind"], "ladder": o.get("ladder", []), "next_rung": o.get("next_rung"),
                    "objectives": [{k: ob.get(k) for k in ("id", "metric", "unit", "value", "band", "minimal", "optimal",
                                                           "higher_is_better", "why", "evidence")}
                                   for ob in o.get("objectives", [])]}
                   for o in env_map.get("objects", [])]
        campaigns = []
        for path in sorted((self.home / "kaizen").glob("*/KAIZEN_RESULT.json")):
            result = _read_json(path, {})
            target = result.get("target") or {}
            campaigns.append({"campaign": path.parent.name, "decision": result.get("decision"),
                              "target": target.get("family") or target.get("stage") or target.get("kind"),
                              "best": (result.get("best_score") or {}).get("strict_successes"),
                              "baseline": (result.get("baseline_score") or {}).get("strict_successes"),
                              "attempts": [{k: a.get(k) for k in ("iteration", "stage", "accepted", "mechanism")}
                                           for a in result.get("attempts", [])]})
        active = generations.active(self.home)
        lineage = [{k: g.get(k) for k in ("id", "label", "parent", "frozen_utc")} | {"active": g["id"] == active}
                   for g in generations.list_generations(self.home)]
        return {"objects": objects, "goals": self.goals(), "plan": self.plan(), "milestones": self.milestones(),
                "campaigns": campaigns[-12:], "lineage": lineage, "active_generation": active}

    def milestones(self) -> list[dict[str, Any]]:
        """Goals, plan milestones and each object's next rung, as one list of what comes next."""
        rows = [{"id": f"goal:{g['id']}", "kind": "goal", "title": g["text"], "status": g["status"]}
                for g in self.goals()]
        for m in (self.plan() or {}).get("milestones", []):
            rows.append({"id": f"milestone:{m['id']}", "kind": "milestone", "title": m.get("title"),
                         "status": m.get("status", "open"), "track": m.get("track"), "detail": m.get("detail")})
        for o in (self.environment_map() or {}).get("objects", []):
            if o.get("next_rung"):
                done = sum(1 for r in o.get("ladder", []) if r["status"] == "achieved")
                rows.append({"id": f"rung:{o['name']}/{o['next_rung']}", "kind": "rung", "object": o["name"],
                             "title": f"{o['name']}: {o['next_rung'].replace('_', ' ')}", "status": "next",
                             "progress": [done, len(o.get("ladder", []))]})
        return rows

    # ----------------------------------------------------------------------- plan --

    def plan(self) -> dict[str, Any] | None:
        return _read_json(self.home / "PLAN.json", None)

    def goalposts(self) -> dict[str, Any] | None:
        return _read_json(self.home / "GOALPOSTS.json", None)

    def save_plan(self, plan: dict[str, Any], *, kept: list[dict[str, Any]] = ()) -> dict[str, Any]:
        """Save a plan. `kept` milestones (a redraft's finished or linked work) go first, exactly as they were."""
        previous = self.plan()
        milestones = [json.loads(json.dumps(m)) for m in kept]
        for index, m in enumerate(plan.get("milestones") or []):
            if not isinstance(m, dict) or not str(m.get("title") or "").strip():
                continue
            milestones.append({"id": str(m.get("id") or f"m{index + 1}")[:20], "title": str(m["title"]).strip()[:200],
                               "detail": str(m.get("detail") or "").strip()[:1500],
                               "track": str(m.get("track") or "").strip()[:60],
                               "done_when": str(m.get("done_when") or "").strip()[:400],
                               "status": m.get("status") if m.get("status") in MILESTONE_STATES else "open"})
        body = {"summary": str(plan.get("summary") or "").strip()[:3000], "milestones": milestones[:30],
                "tracks": _with_kept_tracks([{"name": str(t.get("name") or "")[:60], "purpose": str(t.get("purpose") or "")[:300]}
                                             for t in (plan.get("tracks") or []) if isinstance(t, dict) and t.get("name")][:10],
                                            kept, (previous or {}).get("tracks") or []),
                "first_steps": [str(s)[:300] for s in (plan.get("first_steps") or [])][:10],
                "questions": [str(s)[:300] for s in (plan.get("questions") or [])][:10],
                "assumptions": [str(s)[:500] for s in (plan.get("assumptions") or [])][:20],
                "drafted_by": plan.get("drafted_by"), "utc": _now(), "version": (previous or {}).get("version", 0) + 1}
        if isinstance(plan.get('purpose_origin'), dict):
            body['purpose_origin'] = {k: str(plan['purpose_origin'].get(k, ''))[:200]
                                      for k in ('kind', 'policy_revision', 'direction_digest')}
        with self._lock:
            if previous:
                _write_json(self.home / "plans" / f"PLAN-v{previous.get('version', 0)}.json", previous)
            _write_json(self.home / "PLAN.json", body)
        self.ledger.append("plan.saved", {"version": body["version"], "milestones": len(milestones),
                                          "drafted_by": body["drafted_by"]})
        return body

    def update_milestone(self, milestone_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            plan = self.plan()
            for m in (plan or {}).get("milestones", []):
                if m["id"] == milestone_id:
                    if patch.get("status") in MILESTONE_STATES:
                        m["status"] = patch["status"]
                    for key, limit in (("title", 200), ("detail", 1500), ("track", 60), ("done_when", 400)):
                        if isinstance(patch.get(key), str) and (key != "title" or patch[key].strip()):
                            m[key] = patch[key].strip()[:limit]
                    _write_json(self.home / "PLAN.json", plan)
                    self.ledger.append("milestone.updated", {"id": milestone_id, "status": m["status"]})
                    return m
        raise KeyError(milestone_id)

    def add_milestone(self, title: str, detail: str = "", track: str = "", done_when: str = "") -> dict[str, Any]:
        title = (title or "").strip()
        if not title:
            raise WorkspaceError("a milestone needs a title")
        with self._lock:
            plan = self.plan() or {"summary": "", "milestones": [], "tracks": [], "first_steps": [], "questions": [],
                                   "drafted_by": "owner", "utc": _now(), "version": 1}
            milestone = {"id": "m" + uuid.uuid4().hex[:6], "title": title[:200], "detail": (detail or "").strip()[:1500],
                         "track": (track or "").strip()[:60], "done_when": str(done_when or "").strip()[:400], "status": "open"}
            plan["milestones"].append(milestone)
            _write_json(self.home / "PLAN.json", plan)
        self.ledger.append("milestone.added", {"id": milestone["id"]})
        return milestone

    # ----------------------------------------------------------------------- work --

    def proposal_state(self) -> dict[str, Any]:
        return _read_json(self.home / "PROPOSALS_STATE.json", {})

    def work(self) -> dict[str, Any]:
        from runesmith.proposals import list_proposals
        state = self.proposal_state()
        proposals = []
        for p in list_proposals(self.home):
            s = state.get(p["key"], {})
            repo = Path(p["repo"])
            proposals.append(dict(p, object=self._object_label(repo), state=s.get("state", "waiting"),
                                  state_utc=s.get("utc"), reason=s.get("reason"), inside=self._inside(repo),
                                  outdated=s.get("state", "waiting") == "waiting" and self._fix_outdated(p["key"])))
        proposals.sort(key=lambda p: p["key"], reverse=True)
        work = _read_json(self.home / "WORK.json", {"opportunities": [], "objects": {}, "utc": None})
        recent = []
        for s in self.sessions()[-40:][::-1]:
            row = {k: s.get(k) for k in ("key", "status", "strict_success", "cycle_seconds", "generation", "repo",
                                         "trial_arm", "context_scope")}
            row["calls"] = len(s.get("calls") or [])
            row["object"] = self._object_label(Path(row["repo"])) if row.get("repo") else None
            row["issue"] = (s.get("issue") or "")[:400]
            recent.append(row)
        drafts = self.drafts()
        from runesmith.app.build_memory import recent_observations
        from runesmith.app.build_corrections import correction_candidates
        from runesmith.app.building import author_context_preflight, build_escalation_status, supplement_status
        from runesmith.app.acceptance_contracts import owner_feedback
        from runesmith.app.verification_resume import resume_status
        from runesmith.app.author_recovery import pending_authors
        from runesmith.app.source_baseline import baseline_status
        from runesmith.app.verification_allocation import allocation_status
        from runesmith.app.verification_reconciliation import reconciliation_status
        superseded = superseded_drafts(drafts, self.plan())
        titles = {m['id']: m.get('title') for m in (self.plan() or {}).get('milestones', [])}
        for draft in drafts:
            draft['superseded_by'] = superseded.get(draft['id'])
            draft['milestone_title'] = titles.get(draft.get('milestone'))    # not "b3a755fd75179-s1" (J2-F27)
            if draft.get('milestone'):
                draft['requirement_supplement'] = supplement_status(self,draft)
            draft['public_feedback'] = owner_feedback(self,draft.get('verification') or {})
            draft['check_resume'] = resume_status(self,draft)
            draft['check_allocation'] = allocation_status(self,draft)
            draft['check_reconciliation'] = reconciliation_status(self,draft)
            if draft.get('state') == 'waiting' and (draft.get('verification') or {}).get('status') == 'stale':
                draft['author_context_preflight'] = author_context_preflight(self, draft)
        return {"proposals": proposals, "drafts": drafts, "opportunities": work.get("opportunities", []),
                "objects": work.get("objects", {}), "round_utc": work.get("utc"), "last_round": work.get("summary"),
                "recent_sessions": recent, "build_memory": recent_observations(self),
                "build_corrections": correction_candidates(self),
                "build_escalation": build_escalation_status(self),
                "pending_authors": pending_authors(self),
                "source_baseline": baseline_status(self),
                "counts": dict(Counter("outdated" if p.get("outdated") else p["state"] for p in proposals)),
                "draft_counts": draft_counts(drafts, superseded)}

    def _inside(self, path: Path) -> bool:
        path = Path(path).resolve()
        return path == self.root or self.root in path.parents

    def _object_label(self, repo: Path) -> str:
        """The object's name as the map shows it: services/billing for a nested project, not just billing."""
        try:
            rel = Path(repo).resolve().relative_to(self.root).as_posix()
        except (OSError, ValueError):
            return Path(repo).name
        return rel if rel and rel != "." else Path(repo).name

    def object_statuses(self, work: dict[str, Any] | None = None, env_map: dict[str, Any] | None = None) -> dict[str, str]:
        """Each code object's test status now: the last round's, unless something happened since.

        A fix applied after the round makes it ``fix_applied`` until the tests are measured again; a measurement
        taken after both says ``green`` or ``failing`` from the tests themselves.
        """
        from runesmith.proposals import list_proposals
        work = work if work is not None else _read_json(self.home / "WORK.json", {})
        env_map = env_map if env_map is not None else (self.environment_map() or {})
        statuses = dict(work.get("objects") or {})
        since = work.get("utc") or ""
        applied: dict[str, str] = {}
        state = self.proposal_state()
        for p in list_proposals(self.home):
            s = state.get(p["key"], {})
            if s.get("state") == "applied" and (s.get("utc") or "") > since:
                label = self._object_label(Path(p["repo"]))
                applied[label] = max(applied.get(label, ""), s["utc"])
        for o in env_map.get("objects", []):
            probe, when = o.get("probe") or {}, o.get("measured_utc") or ""
            if "exit_code" in probe and when > since and when >= applied.get(o["name"], ""):
                statuses[o["name"]] = "green" if probe["exit_code"] == 0 else "failing"
            elif o["name"] in applied:
                statuses[o["name"]] = "fix_applied"
        return statuses

    def _proposal(self, key: str) -> dict[str, Any]:
        from runesmith.loop import ExperienceStore
        if not key or "/" in key or "\\" in key or ".." in key:
            raise KeyError(key)
        task_path = self.home / "experience" / key / "TASK.json"
        if not task_path.exists():
            raise KeyError(key)
        store = ExperienceStore(self.home / "experience")
        fix = store.verified_fix(key)
        if not fix:
            raise KeyError(key)
        return {"task": json.loads(task_path.read_text(encoding="utf-8")), "fix": fix, "parent": store.parent_src(key)}

    def apply_proposal(self, key: str) -> dict[str, Any]:
        """Write a judge-accepted fix into the owner's files, only if every file is still as the fix expects."""
        with self._lock:
            state = self.proposal_state()
            if state.get(key, {}).get("state") == "applied":
                return {"ok": False, "detail": "this fix is already applied"}
            p = self._proposal(key)
            repo = Path(p["task"]["repo"]).resolve()
            if not self._inside(repo):
                return {"ok": False, "detail": "this fix belongs to a folder outside this workspace"}
            conflicts, plans, outside = [], [], []
            for rel, new_text in sorted(p["fix"].items()):
                target = repo / rel
                real = target.resolve()
                if real != repo and repo not in real.parents:           # through a link or junction: not ours to write
                    outside.append(rel)
                    continue
                current = target.read_bytes() if target.is_file() else None
                if _lf(current) != (p["parent"].get(rel) or "").lstrip("﻿") or current is None:
                    conflicts.append(rel)
                    continue
                plans.append((rel, target, current, encode_like(new_text.lstrip("﻿"), current)))
            if outside:
                return {"ok": False, "outside": outside,
                        "detail": "these files lead out of the folder through a link, so nothing was written"}
            if conflicts:
                return {"ok": False, "conflicts": conflicts,
                        "detail": "these files changed after the fix was made, so nothing was written"}
            self._backup_and_write(f"proposal-{key}", plans)
            state[key] = {"state": "applied", "utc": _now(), "files": [rel for rel, *_ in plans], "repo": str(repo)}
            _write_json(self.home / "PROPOSALS_STATE.json", state)
        self.ledger.append("proposal.applied", {"key": key, "files": [rel for rel, *_ in plans]})
        return {"ok": True, "files": [rel for rel, *_ in plans]}

    def undo_proposal(self, key: str) -> dict[str, Any]:
        with self._lock:
            state = self.proposal_state()
            entry = state.get(key) or {}
            if entry.get("state") != "applied":
                return {"ok": False, "detail": "this fix is not applied"}
            p = self._proposal(key)
            repo = Path(entry["repo"])
            changed = [rel for rel in entry["files"]
                       if _lf((repo / rel).read_bytes() if (repo / rel).is_file() else None) != p["fix"][rel].lstrip("﻿")]
            if changed:
                return {"ok": False, "conflicts": changed,
                        "detail": "these files changed after the fix was applied, so nothing was restored"}
            self._restore(f"proposal-{key}", repo, entry["files"])
            state[key] = {"state": "undone", "utc": _now()}
            _write_json(self.home / "PROPOSALS_STATE.json", state)
        self.ledger.append("proposal.undone", {"key": key})
        return {"ok": True}

    def reject_proposal(self, key: str, reason: str = "") -> dict[str, Any]:
        self._proposal(key)
        with self._lock:
            state = self.proposal_state()
            if state.get(key, {}).get("state") == "applied":
                return {"ok": False, "detail": "undo the fix before rejecting it"}
            state[key] = {"state": "rejected", "utc": _now(), "reason": (reason or "")[:500]}
            _write_json(self.home / "PROPOSALS_STATE.json", state)
        if (reason or "").strip():
            self.notes.add(target_type="proposal", target_id=key, target_label=f"fix {key}", text=f"Rejected: {reason}")
        self.ledger.append("proposal.rejected", {"key": key})
        return {"ok": True}

    def _backup_and_write(self, backup_key: str, plans: list[tuple[str, Path, bytes | None, bytes]]) -> None:
        backup = self.home / "backups" / backup_key
        if not backup.resolve().is_relative_to((self.home / 'backups').resolve()):
            raise WorkspaceError('invalid backup target')
        prior = _read_json(backup / 'TRANSACTION.json', {})
        if prior.get('state') in ('prepared', 'conflict'):
            raise WorkspaceError('a previous partial write must be recovered first')
        # Keep earlier journal attempts instead of deleting their evidence.
        if backup.exists():
            archived = backup.with_name(backup.name + '-prior-' + uuid.uuid4().hex[:8])
            backup.rename(archived)
        manifest = {'key':backup_key, 'state':'prepared', 'root':str(self.root), 'utc':_now(),
                    'files':[{'path':rel, 'before':hashlib.sha256(old).hexdigest() if old is not None else None,
                              'after':hashlib.sha256(data).hexdigest()} for rel, _target, old, data in plans]}
        for rel, _target, current, _data in plans:
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            if current is not None:
                saved.write_bytes(current)
            else:
                saved.with_name(saved.name + ".absent").write_bytes(b"")
        _write_json(backup / 'TRANSACTION.json', manifest)
        try:
            for _rel, target, _current, data in plans:
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + '.runesmith-' + uuid.uuid4().hex[:8] + '.tmp')
                temp.write_bytes(data)
                temp.replace(target)
        except BaseException:
            self.recover_writes()
            raise
        _write_json(backup / 'TRANSACTION.json', dict(manifest, state='committed', committed=_now()))

    def recover_writes(self) -> list[dict[str, Any]]:
        """Rollback unfinished batches only where bytes still belong to that batch."""
        receipts = []
        for path in (self.home / 'backups').glob('*/TRANSACTION.json'):
            manifest = _read_json(path, {})
            if manifest.get('state') != 'prepared' or manifest.get('root') != str(self.root):
                continue
            conflicts = []
            for f in manifest.get('files', []):
                rel = self._safe_rel(f['path'])
                if not rel:
                    conflicts.append(f['path']); continue
                target, saved = self.root / rel, path.parent / rel
                current = target.read_bytes() if target.is_file() else None
                digest = hashlib.sha256(current).hexdigest() if current is not None else None
                if digest == f['before']:
                    continue
                if digest != f['after']:
                    conflicts.append(rel); continue
                if f['before'] is None:
                    target.unlink()
                elif saved.is_file() and hashlib.sha256(saved.read_bytes()).hexdigest() == f['before']:
                    target.write_bytes(saved.read_bytes())
                else:
                    conflicts.append(rel)
            recovered = dict(manifest, state='conflict' if conflicts else 'rolled_back', conflicts=conflicts,
                             recovered=_now())
            _write_json(path, recovered)
            self.ledger.append('write.recovered', {'key':manifest['key'], 'state':recovered['state'], 'conflicts':conflicts})
            receipts.append(recovered)
        return receipts

    def _restore(self, backup_key: str, base: Path, files: list[str]) -> None:
        backup = self.home / "backups" / backup_key
        for rel in files:
            target, saved = base / rel, backup / rel
            if saved.is_file():
                target.write_bytes(saved.read_bytes())
            elif saved.with_name(saved.name + ".absent").exists() and target.exists():
                target.unlink()

    # --------------------------------------------------------------------- drafts --

    def _safe_rel(self, raw: str, *, allow_missing: bool = True) -> str | None:
        """A workspace-relative POSIX path that stays inside the workspace and out of Runesmith's home, or None."""
        rel = str(raw or "").strip().replace("\\", "/")
        while rel.startswith("./"):
            rel = rel[2:]
        path = PurePosixPath(rel)
        if (not rel or not path.parts or path.is_absolute() or ":" in path.parts[0] or ".." in path.parts
                or any(p in ("", ".") for p in path.parts) or len(rel) > 240):
            return None
        if path.parts[0] in (self.home.name, ".git", ".hg", ".svn"):
            return None
        target = (self.root / rel).resolve()
        if not self._inside(target) or target == self.root or self.home == target or self.home in target.parents:
            return None
        if not allow_missing and not target.is_file():
            return None
        return path.as_posix()

    def drafts(self) -> list[dict[str, Any]]:
        import difflib
        rows = []
        for path in sorted((self.home / "drafts").glob("*/DRAFT.json")):
            draft = _read_json(path, None)
            if isinstance(draft, dict):
                for f in draft.get("files", []):
                    f["exists_now"] = (self.root / f["path"]).is_file()
                    if "base" in f:
                        f["diff"] = "".join(difflib.unified_diff(f["base"].splitlines(True), f["content"].splitlines(True),
                                                                 f"a/{f['path']}", f"b/{f['path']}", n=1))
                rows.append(draft)
        return sorted(rows, key=lambda d: d.get("utc") or "", reverse=True)

    # ------------------------------------------------------------- link doctor --

    def suggest_link_fixes(self, object_name: str | None = None) -> dict[str, Any]:
        """For each broken internal link in documents and web pages, point it at the closest existing file.

        No model is involved: the closest file is found by name. The result is an unverified draft of edits, each
        applied only onto the version it was made from.
        """
        import difflib
        import os
        import re as _re
        from urllib.parse import unquote
        from runesmith.envmap import _internal_targets, _scan, exists_exactly
        env = self.environment_map() or {"objects": []}
        excluded = set(self.settings()["exclude"])
        scope = [Path(o["path"]) for o in env["objects"]
                 if o["kind"] in ("document_collection", "website") and o["kind"] != "excluded"
                 and (object_name is None or o["name"] == object_name)]
        if not scope:
            return {"ok": False, "detail": "no documents or web pages to check here"}
        def excluded_path(p: Path) -> bool:
            rel = p.relative_to(self.root).as_posix()
            return any(rel == e or rel.startswith(e + "/") for e in excluded)
        # the map's own walk: never through a link, at most MAX_FILES_SCANNED files, one pass
        pool = [p for p, _, _ in _scan(self.root) if not p.name.startswith(".") and not excluded_path(p)]
        listing: dict[str, set[str]] = {}                                   # each directory is listed once per run
        by_name: dict[str, list[Path]] = {}
        for p in pool:
            by_name.setdefault(p.name.lower(), []).append(p)
        html_ref = _re.compile(r"""((?:href|src)\s*=\s*["'])([^"'#?]+)""", _re.I)
        files, fixed, unresolved = [], [], []
        seen: set[Path] = set()
        pool_text = [(p, str(p)) for p in pool]                   # string tests: Path.parents is slow on 20,000 files
        for base_dir in scope:
            recursive = base_dir != self.root
            base = str(base_dir)
            prefix = base.rstrip("\\/") + os.sep
            candidates = [p for p, s in pool_text if s.startswith(prefix) and (recursive or os.path.dirname(s) == base)]
            for doc in candidates:
                suffix = doc.suffix.lower()
                if doc in seen or suffix not in (".md", ".markdown", ".html", ".htm"):
                    continue
                seen.add(doc)
                try:
                    text = doc.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
                except (OSError, UnicodeDecodeError):
                    continue
                targets = (_internal_targets(text) if suffix in (".md", ".markdown")
                           else [m.group(2) for m in html_ref.finditer(text)
                                 if not m.group(2).lower().startswith(("http:", "https:", "mailto:", "data:", "tel:", "//", "javascript:"))])
                new_text, changes = text, []
                for target in dict.fromkeys(targets):
                    path_part = unquote(target.split("#", 1)[0].split("?", 1)[0])
                    if not path_part:
                        continue
                    resolved = (self.root / path_part.lstrip("/")) if path_part.startswith("/") else (doc.parent / path_part)
                    if exists_exactly(resolved, listing) or _re.match(r"^.+?:\d+(?:[:-]\d+)?$", path_part):
                        continue
                    name = Path(path_part).name.lower()
                    options = by_name.get(name) or []
                    if not options:
                        near = difflib.get_close_matches(name, list(by_name), n=1, cutoff=0.72)
                        options = by_name.get(near[0], []) if near else []
                    options = [o for o in options if o != doc]
                    wanted = [p.lower() for p in Path(path_part).parts if p not in ("..", ".")]

                    def agreement(o: Path, wanted: list[str] = wanted) -> int:   # trailing path parts that match the link's
                        have = [p.lower() for p in o.relative_to(self.root).parts]
                        n = 0
                        while n < min(len(have), len(wanted)) and have[-1 - n] == wanted[-1 - n]:
                            n += 1
                        return n
                    if name in GENERIC_NAMES:              # README.md, index.html…: a name alone says too little
                        options = [o for o in options if agreement(o) >= 2]
                    if not options:
                        unresolved.append({"document": doc.relative_to(self.root).as_posix(), "target": target})
                        continue
                    best = max(options, key=lambda o: (agreement(o), -len(os.path.relpath(o, doc.parent))))
                    new_path = os.path.relpath(best, doc.parent).replace("\\", "/")
                    replacement = new_path + target[len(target.split("#", 1)[0].split("?", 1)[0]):]
                    pattern = (_re.compile(r"(\]\(\s*<?|^\s{0,3}\[[^\]]+\]:\s*<?)" + _re.escape(target) + r"(?=[)\s>]|$)", _re.M)
                               if suffix in (".md", ".markdown") else
                               _re.compile(r"""((?:href|src)\s*=\s*["'])""" + _re.escape(target) + r"""(?=["'#?])""", _re.I))
                    new_text, count = pattern.subn(lambda m, r=replacement: m.group(1) + r, new_text)
                    if count:
                        changes.append(f"{target} → {replacement}")
                if changes:
                    rel = doc.relative_to(self.root).as_posix()
                    files.append({"path": rel, "base": text, "content": new_text,
                                  "purpose": "; ".join(changes)[:300]})
                    fixed.extend({"document": rel, "change": c} for c in changes)
        if not files:
            return {"ok": True, "draft": None, "fixed": [], "unresolved": unresolved,
                    "detail": "no broken link has a similar file to point to" if unresolved else "every internal link resolves"}
        why = (f"{len(fixed)} link(s) pointed to files that do not exist. Each now points to the existing file with the "
               f"closest name. Check that each is the one you meant." + (f" {len(unresolved)} link(s) have no similar file "
                                                                             "and are left as they are." if unresolved else ""))
        draft = self.save_draft(title=f"Fix {len(fixed)} broken link{'s' if len(fixed) != 1 else ''}", why=why,
                                files=files[:MAX_DRAFT_FILES], drafted_by="Runesmith (no model): closest existing file")
        return {"ok": True, "draft": draft["id"], "fixed": fixed, "unresolved": unresolved}

    def save_draft(self, *, title: str, why: str, files: list[dict[str, Any]], drafted_by: str | None,
                   milestone: str | None = None, author_request_key: str | None = None,
                   answer_digest: str | None = None) -> dict[str, Any]:
        clean, refused = [], []
        for f in files[:MAX_DRAFT_FILES]:
            rel = self._safe_rel(str(f.get("path") or ""))
            content = f.get("content")
            if not rel or not isinstance(content, str) or len(content.encode("utf-8")) > MAX_DRAFT_FILE_BYTES:
                refused.append(str(f.get("path"))[:120])
                continue
            if any(c["path"] == rel for c in clean):
                continue
            entry = {"path": rel, "content": content.replace("\r\n", "\n"),
                     "purpose": str(f.get("purpose") or "")[:300], "existed": (self.root / rel).is_file()}
            if isinstance(f.get("base"), str):      # an edit of a known version: applied only onto that version
                entry["base"] = f["base"].replace("\r\n", "\n")
            if f.get("expected_absent") is True:
                entry["expected_absent"] = True
            if isinstance(f.get("expected_sha256"), str):
                entry["expected_sha256"] = f["expected_sha256"]
            if isinstance(f.get("retained_from"), str):
                entry["retained_from"] = f["retained_from"][:80]
            if f.get("revision_base") in ("current", "candidate"):
                entry["revision_base"] = f["revision_base"]
            clean.append(entry)
        if not clean:
            raise WorkspaceError("the draft had no usable files" + (f" (refused: {', '.join(refused)})" if refused else ""))
        draft = {"id": "d" + time.strftime("%Y%m%d%H%M%S", time.gmtime()) + uuid.uuid4().hex[:4],
                 "title": (title or "Draft").strip()[:200], "why": (why or "").strip()[:2000], "files": clean,
                 "refused": refused, "drafted_by": drafted_by, "milestone": milestone, "state": "waiting",
                 "verified": False, "utc": _now(),
                 "author_request_key":author_request_key, "answer_digest":answer_digest}
        _write_json(self.home / "drafts" / draft["id"] / "DRAFT.json", draft)
        self.ledger.append("draft.created", {"id": draft["id"], "files": [f["path"] for f in clean],
                                             "drafted_by": drafted_by})
        return draft

    def _draft(self, draft_id: str) -> dict[str, Any]:
        if not draft_id or "/" in draft_id or "\\" in draft_id or ".." in draft_id:
            raise KeyError(draft_id)
        draft = _read_json(self.home / "drafts" / draft_id / "DRAFT.json", None)
        if not isinstance(draft, dict):
            raise KeyError(draft_id)
        return draft

    def _save_draft_state(self, draft: dict[str, Any], state: str, **extra: Any) -> None:
        draft.update(state=state, state_utc=_now(), **extra)
        for f in draft.get("files", []):
            f.pop("exists_now", None)
        _write_json(self.home / "drafts" / draft["id"] / "DRAFT.json", draft)

    def apply_draft(self, draft_id: str, *, overwrite: bool = False) -> dict[str, Any]:
        """Write a draft's files. A file that exists now with other content is replaced only with ``overwrite``."""
        with self._lock:
            draft = self._draft(draft_id)
            if draft["state"] == "applied":
                return {"ok": False, "detail": "this draft is already applied"}
            plans, conflicts = [], []
            for f in draft["files"]:
                rel = self._safe_rel(f["path"])
                if not rel:
                    conflicts.append(f["path"])
                    continue
                target = self.root / rel
                current = target.read_bytes() if target.is_file() else None
                if f.get('expected_sha256') and (current is None or hashlib.sha256(current).hexdigest()!=f['expected_sha256']):
                    conflicts.append(rel)
                    continue
                if f.get("expected_absent") and target.exists():
                    conflicts.append(rel)
                    continue
                if "base" in f:                          # an edit: only onto the version it was made from
                    if current is None or _lf(current) != f["base"]:
                        conflicts.append(rel)
                        continue
                elif current is not None and _lf(current) != f["content"] and not overwrite:
                    conflicts.append(rel)
                    continue
                plans.append((rel, target, current, encode_like(f["content"], current)))
            if conflicts:
                return {"ok": False, "conflicts": conflicts,
                        "detail": "these files already exist with other content, so nothing was written"}
            self._backup_and_write(f"draft-{draft_id}", plans)
            self._save_draft_state(draft, "applied", applied_files=[rel for rel, *_ in plans])
        self.ledger.append("draft.applied", {"id": draft_id, "files": [rel for rel, *_ in plans]})
        moved = None
        plan = self.plan() or {}
        milestone = next((m for m in plan.get("milestones", []) if m["id"] == draft.get("milestone")), None)
        if milestone and milestone.get("status") == "open":        # its first files exist: the milestone is under way
            self.update_milestone(milestone["id"], {"status": "doing"})
            moved = milestone["id"]
        return {"ok": True, "files": [rel for rel, *_ in plans], "milestone_doing": moved}

    def undo_draft(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            draft = self._draft(draft_id)
            if draft["state"] != "applied":
                return {"ok": False, "detail": "this draft is not applied"}
            contents = {f["path"]: f["content"] for f in draft["files"]}
            files = draft.get("applied_files") or list(contents)
            changed = [rel for rel in files
                       if _lf((self.root / rel).read_bytes() if (self.root / rel).is_file() else None) != contents.get(rel)]
            if changed:
                return {"ok": False, "conflicts": changed,
                        "detail": "these files changed after the draft was applied, so nothing was restored"}
            self._restore(f"draft-{draft_id}", self.root, files)
            self._save_draft_state(draft, "undone")
            if draft.get('applied_by') == 'delegated_build' and draft.get('milestone'):
                self.update_milestone(draft['milestone'], {'status':'doing'})
        self.ledger.append("draft.undone", {"id": draft_id})
        return {"ok": True}

    def reject_draft(self, draft_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            draft = self._draft(draft_id)
            if draft["state"] == "applied":
                return {"ok": False, "detail": "undo the draft before rejecting it"}
            self._save_draft_state(draft, "rejected", reason=(reason or "")[:500])
        if (reason or "").strip():
            self.notes.add(target_type="draft", target_id=draft_id, target_label=draft["title"], text=f"Rejected: {reason}")
        self.ledger.append("draft.rejected", {"id": draft_id})
        return {"ok": True}

    # --------------------------------------------------------------- improvement --

    def library(self) -> list[dict[str, Any]]:
        lib = _read_json(LIBRARY / "LIBRARY.json", {"generations": []})
        imported = {(g.get("provenance") or {}).get("imported_from"): g["id"]
                    for g in generations.list_generations(self.home)}
        return [dict(entry, imported_as=imported.get(entry["id"])) for entry in lib.get("generations", [])]

    def generation_name(self, generation_id: str | None, _depth: int = 0) -> str:
        """A short human name: g0, C7 (from the library), Kaizen-xxxx, or the id; requalified copies keep their name."""
        if not generation_id:
            return "—"
        gens = {g["id"]: g for g in generations.list_generations(self.home)}
        g = gens.get(generation_id)
        if not g:
            return generation_id
        provenance = g.get("provenance") or {}
        if provenance.get("requalified_from") and _depth < 6:
            return self.generation_name(provenance["requalified_from"], _depth + 1)
        if provenance.get("imported_from"):
            entry = next((e for e in _read_json(LIBRARY / "LIBRARY.json", {"generations": []})["generations"]
                          if e["id"] == provenance["imported_from"]), None)
            return entry["name"] if entry else "imported " + provenance["imported_from"][4:10]
        label = g.get("label") or ""
        if label.startswith("g0"):
            return "g0"
        if provenance.get("target") or label.startswith("kaizen"):
            return "Kaizen " + generation_id[4:8]
        return generation_id[4:10]

    def generations_view(self) -> dict[str, Any]:
        from runesmith.kaizen.trial import Trial
        active = generations.active(self.home)
        lineage = []
        for g in generations.list_generations(self.home):
            provenance = g.get("provenance") or {}
            lineage.append({"id": g["id"], "name": self.generation_name(g["id"]), "label": g.get("label"), "parent": g.get("parent"),
                            "frozen_utc": g.get("frozen_utc"), "active": g["id"] == active,
                            "same_kernel": g.get("kernel_digest") == generations.kernel_digest(),
                            "origin": ("imported" if provenance.get("imported_from") else
                                       "requalified" if provenance.get("requalified_from") else
                                       "kaizen" if provenance.get("target") else "shipped"),
                            "imported_from": provenance.get("imported_from"),
                            "validation": provenance.get("validation"),
                            "incumbent_validation": provenance.get("incumbent_validation")})
        trial = Trial.load(self.home / "TRIAL.json")
        closed = []
        for path in sorted(self.home.glob("TRIAL-*.json")):
            t = Trial.load(path)
            if t:
                closed.append(dict(t.summary(), looks_detail=t.looks))
        open_trial = None
        if trial and trial.decision is None:
            open_trial = dict(trial.summary(), looks_detail=trial.looks, opened_utc=trial.opened_utc,
                              max_per_arm=trial.max_per_arm, min_per_arm=trial.min_per_arm, look_every=trial.look_every)
        return {"active": active, "lineage": lineage, "library": self.library(), "trial": open_trial,
                "closed_trials": closed, "requalification": self.requalification}

    def adopt_from_library(self, generation_id: str) -> dict[str, Any]:
        from runesmith.share import ImportRefused, import_generation
        entry = next((e for e in self.library() if e["id"] == generation_id), None)
        if not entry:
            raise KeyError(generation_id)
        if entry.get("imported_as"):
            return {"ok": False, "detail": f"already adopted as {entry['imported_as']}"}
        archive = LIBRARY / entry["file"]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != entry.get("sha256"):
            return {"ok": False, "detail": "the library file does not match its recorded digest, so it was not adopted"}
        try:
            result = import_generation(self.home, archive,
                                       trial_settings={"look_every": 10, "min_per_arm": 10, "max_per_arm": 40})
        except ImportRefused as refusal:
            return {"ok": False, "detail": str(refusal)}
        return dict(result, ok=True)

    def activate_generation(self, generation_id: str) -> dict[str, Any]:
        """The owner's own choice of generation (a rollback, usually); the ledger records who chose.

        An open trial is closed by that choice: its arms compared generations that no longer describe what runs.
        """
        from runesmith.kaizen.trial import Trial
        previous = generations.active(self.home)
        try:
            generations.activate(self.home, generation_id, expected=previous)
        except generations.GenerationError as error:
            return {"ok": False, "detail": str(error)}
        self.ledger.append("generation.activated", {"id": generation_id, "previous": previous, "evidence": "owner's choice"})
        closed = None
        trial_path = self.home / "TRIAL.json"
        trial = Trial.load(trial_path)
        if trial is not None and trial.decision is None:
            trial.decision = "closed_by_owner"
            trial.save(trial_path)
            trial_path.replace(trial_path.with_name(f"TRIAL-{trial.candidate}-closed_by_owner.json"))
            self.ledger.append("trial.closed_by_owner", dict(trial.summary(), active=generation_id))
            closed = trial.candidate
        return {"ok": True, "active": generation_id, "previous": previous, "trial_closed": closed}

    # --------------------------------------------------------------------- notes --

    def add_note(self, target_type: str, target_id: str, text: str, target_label: str = "",
                 reply_to: str | None = None) -> dict[str, Any]:
        try:
            note = self.notes.add(target_type=target_type, target_id=target_id, text=text, target_label=target_label,
                                  reply_to=reply_to)
        except ValueError as error:
            raise WorkspaceError(str(error)) from error
        self.ledger.append("note.added", {"id": note["id"], "target": note["target"]})
        return note

    def resolve_note(self, note_id: str, resolution: str = "") -> None:
        if not any(n["id"] == note_id for n in self.notes.all()):
            raise KeyError(note_id)
        self.notes.resolve(note_id, resolution=resolution)
        self.ledger.append("note.resolved", {"id": note_id})

    def notes_for_object(self, name: str) -> str:
        """Open notes that travel with work on one object: the object, its objectives and rungs, the workspace."""
        if not self.settings()["read_notes"]:
            return ""
        targets = [("workspace", "root"), ("object", name)]
        for note in self.notes.all():
            t = note["target"]
            if t["type"] in ("objective", "rung") and t["id"].startswith(name + "/"):
                targets.append((t["type"], t["id"]))
        return self.notes.operator_notes(targets)

    def notes_for_self(self) -> str:
        """Open notes about Runesmith itself, for the Kaizen author."""
        if not self.settings()["read_notes"]:
            return ""
        targets = [("self", "runesmith")]
        for note in self.notes.all():
            if note["target"]["type"] in ("generation", "capability", "component", "organ"):
                targets.append((note["target"]["type"], note["target"]["id"]))
        return self.notes.operator_notes(targets)

    def planning_note_selection(self, *, milestone_id=None, draft_id=None) -> dict[str, Any]:
        targets = [("workspace", "root"), ("plan", "current"), ("brief", "current")]
        for note in self.notes.all():
            if note["target"]["type"] in ("goal", "milestone", "object", "draft"):
                targets.append((note["target"]["type"], note["target"]["id"]))
        priority = [('draft', draft_id)] if draft_id else []
        if milestone_id: priority.append(('milestone', milestone_id))
        enabled = self.settings()['read_notes']
        result = self.notes.operator_note_selection(targets if enabled else [], max_chars=3000,
                                                    priority_targets=priority)
        return dict(result, enabled=enabled)

    def notes_for_plan(self, *, milestone_id=None, draft_id=None) -> str:
        selection = self.planning_note_selection(milestone_id=milestone_id, draft_id=draft_id)
        if selection['blockers']:
            raise WorkspaceError('; '.join(selection['blockers']))
        return selection['text']

    # ----------------------------------------------------------------- the manual --

    def manual_requests(self) -> list[dict[str, Any]]:
        from runesmith.manual import directory_for, pending_requests
        directory = directory_for(self.config(), self.home)
        rows = pending_requests(directory) if directory.exists() else []
        for row in rows:
            try:
                row["text"] = Path(row["prompt"]).read_text(encoding="utf-8")
            except (OSError, KeyError):
                row["text"] = ""
        return rows

    def manual_waiting(self) -> int:
        """How many chat-relay requests wait for the owner (without reading their texts)."""
        return len(self.manual_waiting_ids())

    def manual_waiting_ids(self) -> list[str]:
        """Which chat-relay requests wait for the owner, oldest first."""
        from runesmith.manual import directory_for, pending_requests
        directory = directory_for(self.config(), self.home)
        return [r["id"] for r in pending_requests(directory) if not r["answered"]] if directory.exists() else []

    def set_aside_orphaned_requests(self) -> int:
        """Relay requests left from a closed Studio have no waiting call: move them aside, unanswered, and say so."""
        from runesmith.manual import directory_for, pending_requests
        directory = directory_for(self.config(), self.home)
        if not directory.exists():
            return 0
        aside = directory / "set-aside"
        moved = 0
        for request in pending_requests(directory):
            if request["answered"]:
                continue
            aside.mkdir(parents=True, exist_ok=True)
            for path in directory.glob(f"{request['id']}.*"):
                path.replace(aside / path.name)
            moved += 1
            self.ledger.append("manual.set_aside", {"id": request["id"], "reason": "the Studio restarted"})
        return moved

    def skip_manual(self, request_id: str) -> dict[str, Any]:
        """Decline a relay request: the waiting call gets an unusable answer and moves on, recorded as such."""
        result = self.answer_manual(request_id, '{"skipped_by_owner": true}', model="(skipped by the owner)", force=True)
        self.ledger.append("manual.skipped", {"id": request_id})
        return result

    def answer_manual(self, request_id: str, text: str, model: str | None = None, force: bool = False) -> dict[str, Any]:
        from runesmith.manual import directory_for, submit_answer
        return submit_answer(directory_for(self.config(), self.home), request_id, text, model=model, force=force)

    # ------------------------------------------------------------ activity & health --

    def activity(self, limit: int = 150, kinds: str | None = None) -> list[dict[str, Any]]:
        rows = []
        prefix = tuple(k.strip() for k in (kinds or "").split(",") if k.strip())
        for line in _tail_lines(self.home / "ledger.jsonl", limit * (6 if prefix else 1)):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if prefix and not str(event.get("kind", "")).startswith(prefix):
                continue
            rows.append({"seq": event.get("seq"), "utc": event.get("utc"), "kind": event.get("kind"),
                         "data": event.get("data")})
        return rows[::-1][:limit]

    def health(self, network: bool = False) -> list[dict[str, Any]]:
        from runesmith.doctor import diagnose_home
        rows = diagnose_home(self.home, network=network)
        for row in rows:
            if row["check"] == "roles" and not row["ok"]:
                row["fix"] = "add thinking power under Inference"
        if not self.ready()["any"]:
            rows.append({"check": "thinking power", "ok": None, "fix": "add a model under Inference",
                         "detail": "no model is set up yet: Runesmith can map and watch, but not work or plan"})
        if self.requalification and self.requalification.get("error"):
            rows.append({"check": "requalification", "ok": False, "fix": "see Improve",
                         "detail": self.requalification["error"]})
        return rows

    # ----------------------------------------------------------------- the summary --

    def state(self) -> dict[str, Any]:
        """Everything the home screen needs, in one call."""
        from runesmith.kaizen.attention import SHARE_BP, Attention
        env_map = self.environment_map()
        self_map = _read_json(self.home / "SELF_MAP.json", None)
        round_file = _read_json(self.home / "WORK.json", {})
        drafts = self.drafts()
        work = {"counts": self.proposal_counts(), "draft_counts": draft_counts(drafts, superseded_drafts(drafts, self.plan())),
                "opportunities": round_file.get("opportunities", []), "last_round": round_file.get("summary"),
                "round_utc": round_file.get("utc")}
        settings = self.settings()
        judged = [s for s in self.sessions() if s.get("strict_success") is not None]
        attention = Attention.load(self.home / "ATTENTION.json")
        waiting = self.manual_waiting()
        facts = (env_map or {}).get("workspace_facts") or {}
        plan = self.plan() or {}
        return {
            "version": __version__,
            "workspace": {"name": settings["workspace_name"], "path": str(self.root), "home": str(self.home),
                          "empty": facts.get("empty"), "files": facts.get("files"), "entries": facts.get("entries_total")},
            "settings": settings, "ready": self.ready(),
            "objects": [{"name": o["name"], "kind": o["kind"], "next_rung": o.get("next_rung"), "root": bool(o.get("root")),
                         "bands": [ob.get("band") for ob in o.get("objectives", [])],
                         "ladder": [r["status"] for r in o.get("ladder", [])]}
                        for o in (env_map or {}).get("objects", [])],
            "mapped_utc": (env_map or {}).get("utc"),
            # A map written by an earlier mapper may miss what today's mapper sees (journey J2: an old map
            # listed a package and its tests as plain folders); the Overview then makes no claim from it.
            "map_outdated": bool(env_map) and (env_map.get("mapper_revision") or 1) < _mapper_revision(),
            "numbers": _numbers(self),
            "capabilities": (self_map or {}).get("capabilities", {}),
            "active_generation": generations.active(self.home),
            "active_name": self.generation_name(generations.active(self.home)),
            "generations": len(generations.list_generations(self.home)),
            "proposals": work["counts"], "drafts": work["draft_counts"], "opportunities": len(work["opportunities"]),
            "last_round": work["last_round"], "round_utc": work["round_utc"],
            "repairs": {"judged": len(judged), "accepted": sum(1 for s in judged if s.get("strict_success"))},
            "attention": {"mode": attention.mode, "share": SHARE_BP[attention.mode] / 10000} if attention else None,
            "goals": [g for g in self.goals() if g["status"] == "active"],
            "plan": {"milestones": len(plan.get("milestones", [])),
                     "done": sum(1 for m in plan.get("milestones", []) if m.get("status") == "done"),
                     "next": next(({"id": m.get("id"), "title": m.get("title")} for m in plan.get("milestones", [])
                                   if m.get("status") not in ("done", "dropped")), None)},
            "brief": bool(self.brief().get("text")),
            "notes_open": sum(self.notes.counts().values()), "note_counts": self.notes.counts(),
            "manual_waiting": waiting,
            "activity": self.activity(10),
        }

    def export_snapshot(self, target: Path) -> Path:
        """A zip of the home's records, without keys or backups, for sharing evidence or asking for help."""
        target = Path(target)
        staging = self.home / "scratch" / f"snapshot-{int(time.time())}"
        shutil.copytree(self.home, staging / "runesmith-home",
                        ignore=shutil.ignore_patterns("secrets.json*", "scratch", "backups", "*.lock*", "*.tmp"))
        archive = shutil.make_archive(str(target.with_suffix("")), "zip", staging)
        shutil.rmtree(staging, ignore_errors=True)
        self.ledger.append("snapshot.exported", {"file": Path(archive).name})
        return Path(archive)


def _mapper_revision() -> int:
    from runesmith.envmap import MAPPER_REVISION
    return MAPPER_REVISION


def superseded_drafts(drafts: list[dict[str, Any]], plan: dict[str, Any] | None) -> dict[str, str]:
    """Drafts still pending for a milestone that another draft finished and wrote: {draft id: that draft's id}.

    Journey J2-F1: an early, never-checked draft for a milestone finished hours later by a second draft kept the
    Overview saying "1 draft waits for your review". Only the listing and the counts change; the stored state does not.
    """
    done = {m.get("id") for m in (plan or {}).get("milestones", []) if m.get("status") == "done"}
    written = {d.get("milestone"): d["id"] for d in drafts if d.get("state") == "applied" and d.get("milestone") in done}
    return {d["id"]: written[d["milestone"]] for d in drafts
            if d.get("state") in ("waiting", "needs_revision") and d.get("milestone") in written}


def draft_counts(drafts: list[dict[str, Any]], superseded: dict[str, str]) -> dict[str, int]:
    return dict(Counter("superseded" if d["id"] in superseded else d["state"] for d in drafts))


def _with_kept_tracks(tracks: list[dict[str, str]], kept, earlier: list[dict[str, Any]]) -> list[dict[str, str]]:
    """A kept milestone keeps its track, with the purpose it had, even when a redraft names only new tracks."""
    names = {t["name"] for t in tracks}
    purposes = {t.get("name"): t.get("purpose", "") for t in earlier if isinstance(t, dict)}
    for m in kept:
        if m.get("track") and m["track"] not in names:
            names.add(m["track"])
            tracks.append({"name": m["track"], "purpose": str(purposes.get(m["track"]) or "")[:300]})
    return tracks


def _numbers(ws) -> list[dict[str, Any]]:
    """The owner's measurements with their latest values, for the Overview (journey J5: the number was only on a
    dashboard, under receipt hashes)."""
    from runesmith.app import measurements
    try:
        items = [item for item in measurements.definitions(ws)["items"] if item.get("enabled")]
    except WorkspaceError:
        return []
    rows = []
    for item in items[:8]:
        last = measurements.latest(ws, item) or {}
        rows.append({"id": item["id"], "name": item["name"], "unit": item.get("unit") or "",
                     "aggregation": item.get("aggregation"), "threshold": item.get("threshold"),
                     "status": last.get("status"), "value": last.get("value"), "detail": last.get("detail"),
                     "measured_at": last.get("measured_at"), "source_file": last.get("source_file"),
                     "threshold_met": last.get("threshold_met")})
    return rows
