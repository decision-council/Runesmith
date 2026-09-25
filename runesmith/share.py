"""Sharing generations between Runesmith homes: Kaizen that compounds across people.

``export`` packs one frozen generation (its manifest and organ files) into a zip.
``import_generation`` lets a receiver adopt someone else's improved organs without
trusting them. Before an imported generation ever serves real work:

1. the archive may hold only ``MANIFEST.json`` and ``organs/**.py``: no absolute paths, no
   ``..``, no other files, bounded sizes;
2. the organ files must match the manifest's digests;
3. every organ module must pass the static check (allowed imports only, a ``run`` function);
4. the repair organ must pass a confined smoke test on a kernel-owned fixture;
5. it is frozen as a new, inactive generation, bound to the receiver's kernel, with provenance
   naming the source generation and its kernel;
6. an online trial against the receiver's active generation is opened. The import becomes
   active only if it wins on the receiver's own work, and is rejected otherwise.

Organs always run confined (isolated interpreter, audit hook, no files, network or secrets),
so an imported organ gets no more power than a locally authored one.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from runesmith import generations
from runesmith.canon import digest_tree
from runesmith.kaizen.improve import smoke_test, static_check
from runesmith.kaizen.trial import Trial
from runesmith.ledger import Ledger

MAX_FILE_BYTES = 200_000
MAX_TOTAL_BYTES = 2_000_000


class ImportRefused(RuntimeError):
    pass


def export_generation(home: Path, generation_id: str, target: Path) -> Path:
    gen_dir = Path(home) / "generations" / generation_id
    check = generations.verify(gen_dir, check_kernel=False)
    if not check["ok"]:
        raise ImportRefused(f"{generation_id} does not verify: {check['problems']}")
    target = Path(target)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest = generations.load(gen_dir)
        manifest.pop("path", None)
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        for path in sorted((gen_dir / "organs").rglob("*.py")):
            archive.write(path, "organs/" + path.relative_to(gen_dir / "organs").as_posix())
    return target


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members, total = [], 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = PurePosixPath(info.filename)
        if info.filename != "MANIFEST.json":
            if (name.is_absolute() or ".." in name.parts or "\\" in info.filename or name.parts[0] != "organs"
                    or name.suffix != ".py"):
                raise ImportRefused(f"unexpected archive member: {info.filename!r}")
        if info.file_size > MAX_FILE_BYTES:
            raise ImportRefused(f"{info.filename} is larger than {MAX_FILE_BYTES} bytes")
        total += info.file_size
        members.append(info)
    if total > MAX_TOTAL_BYTES:
        raise ImportRefused("archive too large")
    if "MANIFEST.json" not in {m.filename for m in members}:
        raise ImportRefused("archive has no MANIFEST.json")
    return members


def import_generation(home: Path, archive_path: Path, *, open_trial: bool = True,
                      trial_settings: dict | None = None) -> dict[str, Any]:
    home = Path(home)
    ledger = Ledger(home / "ledger.jsonl")
    staging = Path(tempfile.mkdtemp(prefix="rs-import-", dir=home))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in _safe_members(archive):
                target = staging / PurePosixPath(info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        manifest = json.loads((staging / "MANIFEST.json").read_text(encoding="utf-8"))
        organs = staging / "organs"
        if digest_tree(organs, suffixes=(".py",)) != manifest.get("organ_files"):
            raise ImportRefused("organ files do not match the manifest's digests")
        problems = {path.name: static_check(path.read_text(encoding="utf-8"))
                    for path in sorted(organs.glob("*.py")) if path.name != "__init__.py"}
        problems = {name: found for name, found in problems.items() if found}
        if problems:
            raise ImportRefused(f"static check failed: {problems}")
        if not (organs / "repair.py").exists():
            raise ImportRefused("the generation has no repair organ")
        smoke = smoke_test(organs, "repair", staging)
        if not smoke["ok"]:
            raise ImportRefused(f"confined smoke test failed: {smoke}")
        active = generations.active(home)
        frozen = generations.freeze(organs, home, label=f"imported: {manifest.get('label')}", parent=active,
                                    provenance={"imported_from": manifest.get("id"),
                                                "source_kernel_digest": manifest.get("kernel_digest"),
                                                "same_kernel": manifest.get("kernel_digest") == generations.kernel_digest(),
                                                "source_provenance": manifest.get("provenance")})
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    ledger.append("generation.imported", {"id": frozen["id"], "imported_from": manifest.get("id"),
                                          "smoke": smoke["status"]})
    result: dict[str, Any] = {"id": frozen["id"], "imported_from": manifest.get("id"),
                              "same_kernel": frozen["provenance"]["same_kernel"], "trial": None}
    if open_trial:
        result["trial"] = open_trial_for(home, frozen["id"], trial_settings=trial_settings)
    return result


def open_trial_for(home: Path, candidate: str, *, trial_settings: dict | None = None) -> dict[str, Any]:
    """Open an online trial for a frozen generation against the active one, if none is open."""
    home = Path(home)
    path = home / "TRIAL.json"
    existing = Trial.load(path)
    if existing is not None and existing.decision is None:
        return {"opened": False, "reason": f"a trial of {existing.candidate} is still open"}
    incumbent = generations.active(home)
    if candidate == incumbent:
        return {"opened": False, "reason": "candidate is already the active generation"}
    trial = Trial(incumbent=incumbent, candidate=candidate, seed=f"trial|{candidate}", **(trial_settings or {}))
    trial.save(path)
    Ledger(home / "ledger.jsonl").append("trial.opened", trial.summary())
    return {"opened": True, **trial.summary()}
