"""Canonical JSON and content digests: the identity layer every record uses."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

EXCLUDED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".git"})


def canonical(value: Any) -> str:
    """Deterministic, ASCII-only JSON text (safe on any console code page)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical(value).encode("ascii"))


def digest_text(text: str) -> str:
    return digest_bytes(text.encode("utf-8"))


def digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def iter_tree(root: str | Path, suffixes: Iterable[str] | None = None) -> list[Path]:
    """Files under ``root`` in a stable order, skipping caches and VCS metadata."""
    root = Path(root)
    wanted = tuple(suffixes) if suffixes else None
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if EXCLUDED_PARTS.intersection(path.relative_to(root).parts):
            continue
        if wanted and not path.name.endswith(wanted):
            continue
        files.append(path)
    return files


def digest_tree(root: str | Path, suffixes: Iterable[str] | None = None) -> dict[str, str]:
    """Map of relative POSIX path -> file digest for every file under ``root``."""
    root = Path(root)
    return {path.relative_to(root).as_posix(): digest_file(path) for path in iter_tree(root, suffixes)}
