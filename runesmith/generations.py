"""Frozen subject generations.

A generation is an immutable, digest-bound copy of the mutable organ surface
plus a manifest naming its parent, provenance and the kernel it was qualified
against. Generations are never edited: an improvement produces a *new*
generation, and activation moves one pointer with compare-and-swap, so a bad
successor can always be rolled back to its intact parent.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from runesmith.canon import digest, digest_tree
from runesmith.ledger import utc_now
from runesmith import atomic

PACKAGE_ROOT = Path(__file__).resolve().parent
ORGANS_ROOT = PACKAGE_ROOT / "organs"


NOT_KERNEL = ("organs/", "app/")      # the mutable organs, and the Studio interface (it never runs an organ)


def kernel_digest() -> str:
    """Digest of every kernel source file (the package minus the mutable organs and the Studio interface)."""
    files = {path: value for path, value in digest_tree(PACKAGE_ROOT, suffixes=(".py",)).items()
             if not path.startswith(NOT_KERNEL)}
    return digest(files)


class GenerationError(RuntimeError):
    pass


def freeze(organs_dir: Path, home: Path, *, label: str, parent: str | None = None,
           provenance: dict[str, Any] | None = None) -> dict:
    """Copy ``organs_dir`` into ``home/generations/<id>`` and write its manifest."""
    organs_dir = Path(organs_dir)
    files = digest_tree(organs_dir, suffixes=(".py",))
    if not files:
        raise GenerationError(f"no organ modules under {organs_dir}")
    body = {"schema": "runesmith.generation.v1", "label": label, "parent": parent,
            "kernel_digest": kernel_digest(), "organ_files": files, "provenance": provenance or {}}
    generation_id = "gen-" + digest(body)[7:19]
    target = Path(home) / "generations" / generation_id
    if target.exists():
        existing = load(target)
        if existing["organ_digest"] == digest(files):
            return existing
        raise GenerationError(f"{generation_id} exists with different content")
    staging = Path(tempfile.mkdtemp(prefix=".freeze-", dir=Path(home)))
    try:
        shutil.copytree(organs_dir, staging / "organs",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.orig", "*.rej"))
        manifest = dict(body, id=generation_id, organ_digest=digest(files), frozen_utc=utc_now())
        (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(staging, target)
        except OSError:                             # another process froze the same generation a moment earlier
            if not (target / "MANIFEST.json").exists() or load(target)["organ_digest"] != digest(files):
                raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return load(target)


def load(generation_dir: Path) -> dict:
    manifest = json.loads((Path(generation_dir) / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["path"] = str(Path(generation_dir))
    return manifest


def verify(generation_dir: Path, *, check_kernel: bool = True) -> dict:
    """Recompute organ digests (and optionally the kernel digest) against the manifest."""
    manifest = load(generation_dir)
    actual = digest_tree(Path(generation_dir) / "organs", suffixes=(".py",))
    problems = []
    if actual != manifest["organ_files"]:
        changed = sorted(set(actual) ^ set(manifest["organ_files"]) |
                         {p for p in actual if manifest["organ_files"].get(p) != actual[p]})
        problems.append({"organ_files_changed": changed})
    if check_kernel and manifest["kernel_digest"] != kernel_digest():
        problems.append({"kernel_changed": True})
    return {"ok": not problems, "id": manifest["id"], "problems": problems}


def list_generations(home: Path) -> list[dict]:
    root = Path(home) / "generations"
    if not root.exists():
        return []
    return [load(path) for path in sorted(root.iterdir()) if (path / "MANIFEST.json").exists()]


def active(home: Path) -> str | None:
    pointer = Path(home) / "ACTIVE"
    return pointer.read_text(encoding="ascii").strip() if pointer.exists() else None


def activate(home: Path, generation_id: str, *, expected: str | None) -> str:
    """Compare-and-swap the active pointer; refuses if someone else moved it."""
    current = active(home)
    if current != expected:
        raise GenerationError(f"active generation is {current!r}, expected {expected!r}")
    target = Path(home) / "generations" / generation_id
    if not verify(target)["ok"]:
        raise GenerationError(f"{generation_id} does not verify")
    tmp = Path(home) / ".ACTIVE.tmp"
    tmp.write_text(generation_id + "\n", encoding="ascii")
    atomic.replace(tmp, Path(home) / "ACTIVE")
    return generation_id
