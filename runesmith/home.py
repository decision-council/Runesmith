"""Creating a Runesmith home: the folder where everything Runesmith learns about a workspace lives.

A home is ``<workspace>/.runesmith`` by default. It holds the configuration, the
hash-chained ledger, frozen generations and the ACTIVE pointer, maps, memory,
session records, notes and saved keys. It ignores itself for version control, so
nothing in it is committed by accident: it can hold keys, and its maps describe
a machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runesmith import __version__, generations
from runesmith.config import DEFAULT_CONFIG
from runesmith.ledger import Ledger

GITIGNORE = "# Runesmith's home: keys, maps and records of this machine. Never commit it.\n*\n"


def init_home(home: Path) -> dict[str, Any]:
    """Create or complete a home. Safe to call again: nothing that exists is overwritten."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    ignore = home / ".gitignore"
    if not ignore.exists():
        ignore.write_bytes(GITIGNORE.encode("utf-8"))
    config = home / "runesmith.json"
    created = not config.exists()
    if created:
        config.write_bytes((json.dumps(DEFAULT_CONFIG, indent=1) + "\n").encode("utf-8"))
    ledger = Ledger(home / "ledger.jsonl")
    if not generations.active(home):
        g0 = generations.freeze(Path(generations.ORGANS_ROOT), home, label="g0 (shipped organs)",
                                provenance={"lineage": "shipped with runesmith " + __version__})
        generations.activate(home, g0["id"], expected=None)
        ledger.append("generation.activated", {"id": g0["id"], "organ_digest": g0["organ_digest"]})
    if created:
        ledger.append("home.initialized", {"version": __version__})
    return {"home": str(home), "config": str(config), "created": created, "active_generation": generations.active(home)}
