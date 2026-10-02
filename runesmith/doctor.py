"""``runesmith doctor`` and ``generations requalify``: keep a home healthy across upgrades.

``doctor`` checks what Runesmith needs and says how to fix what is missing:
Python, pytest, the home (config, ledger chain, active generation), the configured
instruments (keys present, endpoint reachable) and disk space. It never prints a secret.

A generation is bound to the kernel it was qualified under. Updating Runesmith changes
the kernel, so the active generation no longer verifies. ``requalify`` re-freezes the
same organ files under the current kernel, after the static check and a confined smoke
test, and records it in the ledger. The organs are byte-identical; only the kernel they
are qualified against changes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from runesmith import generations
from runesmith.config import load_config
from runesmith.ledger import Ledger


def _probe_openai(spec: dict[str, Any], timeout_s: float) -> tuple[bool, str]:
    headers = {}
    if spec.get("api_key_env"):
        key = os.environ.get(spec["api_key_env"])
        if not key:
            return False, f"environment variable {spec['api_key_env']} is not set"
        headers["Authorization"] = f"Bearer {key}"
    try:
        with urlopen(Request(spec["base_url"].rstrip("/") + "/models", headers=headers), timeout=timeout_s) as reply:
            return reply.status == 200, f"{spec['base_url']} answered {reply.status}"
    except Exception as error:                             # unreachable, refused, 401, ...
        return False, f"{spec['base_url']}: {type(error).__name__}: {str(error)[:120]}"


def diagnose_home(home: Path, *, network: bool = True, timeout_s: float = 5.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(check: str, ok: bool | None, detail: str, fix: str | None = None) -> None:
        rows.append({"check": check, "ok": ok, "detail": detail, "fix": None if ok else fix})

    add("python", sys.version_info >= (3, 11), platform.python_version(), "install Python 3.11 or newer")
    add("pytest", importlib.util.find_spec("pytest") is not None,
        "needed for pytest-based repair observation; Build's unittest checks and limited unittest mapping can run without it",
        "pip install pytest")
    home = Path(home)
    if not (home / "ACTIVE").exists():
        add("home", False, f"{home} is not initialized", "runesmith init")
        return rows
    try:
        config = load_config(home)
        add("config", True, str(home / "runesmith.json"))
    except (json.JSONDecodeError, OSError) as error:
        add("config", False, f"runesmith.json does not parse: {error}", "fix the JSON in runesmith.json")
        return rows
    chain = Ledger(home / "ledger.jsonl").verify()
    add("ledger", chain["ok"], f"{chain['records']} records" + ("" if chain["ok"] else f": {chain.get('error')}"),
        "the ledger was altered; keep the damaged file for inspection and start a new home")
    active = generations.active(home)
    gen_dir = home / "generations" / str(active)
    if not gen_dir.exists():
        add("active generation", False, f"{active} is missing", "runesmith generations list, then activate one")
    else:
        organs = generations.verify(gen_dir, check_kernel=False)
        add("active generation", organs["ok"], f"{active}: organ files " + ("intact" if organs["ok"] else "CHANGED"),
            "organ files were altered; activate an intact generation")
        same_kernel = generations.load(gen_dir)["kernel_digest"] == generations.kernel_digest()
        add("generation kernel", same_kernel,
            "qualified under this kernel" if same_kernel else "frozen under another kernel (Runesmith was updated)",
            "runesmith generations requalify")
    instruments = config.get("instruments") if isinstance(config.get("instruments"), dict) else {}
    if not config.get("roles"):
        add("roles", False, "no roles are configured, so no instrument will be called", "add a roles block to runesmith.json")
    for role, names in sorted((config.get("roles") or {}).items()):
        for name in names:
            spec = instruments.get(name)
            if spec is None:
                add(f"instrument {name}", False, f"role {role} names an undefined instrument", "define it in runesmith.json")
                continue
            if spec.get("kind") == "openai" and network:
                ok, detail = _probe_openai(spec, timeout_s)
                add(f"instrument {name} ({role})", ok, detail,
                    "start the model server, check base_url, or set the key's environment variable")
            elif spec.get("kind") == "openai":
                add(f"instrument {name} ({role})", None, "not probed (offline)")
            elif spec.get("kind") == "manual":
                from runesmith.manual import pending_requests
                directory = Path(spec["dir"]) if spec.get("dir") else Path(home) / "manual"
                waiting = [r for r in pending_requests(directory) if not r["answered"]] if directory.exists() else []
                add(f"instrument {name} ({role})", True,
                    f"manual: a person relays requests through {directory}; {len(waiting)} waiting"
                    + ("; see `runesmith manual list`" if waiting else ""))
            else:
                add(f"instrument {name} ({role})", True, f"kind {spec.get('kind')}")
    free_gb = shutil.disk_usage(home).free / 1e9
    add("disk", free_gb >= 1.0, f"{free_gb:.1f} GB free next to the home", "free some disk space (work copies need room)")
    return rows


def requalify(home: Path, generation_id: str | None = None, *, activate_if_active: bool = True) -> dict[str, Any]:
    """Re-freeze a generation's organs under the current kernel after static and smoke checks."""
    from runesmith.kaizen.improve import smoke_test, static_check
    home = Path(home)
    source_id = generation_id or generations.active(home)
    gen_dir = home / "generations" / str(source_id)
    manifest = generations.load(gen_dir)
    organs = generations.verify(gen_dir, check_kernel=False)
    if not organs["ok"]:
        raise generations.GenerationError(f"{source_id}: organ files changed; refusing to requalify")
    if manifest["kernel_digest"] == generations.kernel_digest():
        return {"requalified": False, "id": source_id, "reason": "already qualified under this kernel"}
    for path in sorted((gen_dir / "organs").glob("*.py")):
        if path.name != "__init__.py" and (problems := static_check(path.read_text(encoding="utf-8"))):
            raise generations.GenerationError(f"{path.name} fails the static check under this kernel: {problems}")
    scratch = home / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    smoke = smoke_test(gen_dir / "organs", "repair", scratch)
    if not smoke["ok"]:
        raise generations.GenerationError(f"confined smoke test failed under this kernel: {smoke}")
    new = generations.freeze(gen_dir / "organs", home, label=f"{manifest['label']} (requalified)", parent=source_id,
                             provenance={"requalified_from": source_id, "previous_kernel_digest": manifest["kernel_digest"],
                                         "smoke": smoke["status"]})
    ledger = Ledger(home / "ledger.jsonl")
    ledger.append("generation.requalified", {"id": new["id"], "from": source_id, "smoke": smoke["status"]})
    activated = False
    if activate_if_active and generations.active(home) == source_id:
        generations.activate(home, new["id"], expected=source_id)
        ledger.append("generation.activated", {"id": new["id"], "previous": source_id, "evidence": "requalified: same organs"})
        activated = True
    return {"requalified": True, "id": new["id"], "from": source_id, "activated": activated, "smoke": smoke["status"]}
