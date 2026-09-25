"""Sharing generations: an import is checked, smoke-tested, frozen inactive, and must win a trial."""

from __future__ import annotations

import json
import zipfile

import pytest

from runesmith import cli, generations
from runesmith.canon import digest_text
from runesmith.kaizen.trial import Trial
from runesmith.ledger import Ledger
from runesmith.share import ImportRefused, export_generation, import_generation


def _home(tmp_path, name):
    home = tmp_path / name
    cli.main(["--home", str(home), "init"])
    return home


def _variant(tmp_path, home):
    """A second generation in the sender's home: g0 plus a harmless comment."""
    organs = tmp_path / "variant"
    source = (home / "generations" / generations.active(home) / "organs")
    organs.mkdir()
    for path in source.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "repair.py":
            text += "\n# variant: shared for a trial\n"
        (organs / path.name).write_text(text, encoding="utf-8")
    return generations.freeze(organs, home, label="sender's variant", parent=generations.active(home))


def test_export_import_opens_a_trial_and_never_activates(tmp_path, capsys):
    sender, receiver = _home(tmp_path, "sender"), _home(tmp_path, "receiver")
    variant = _variant(tmp_path, sender)
    archive = export_generation(sender, variant["id"], tmp_path / "variant.zip")
    before = generations.active(receiver)
    result = import_generation(receiver, archive)
    assert result["imported_from"] == variant["id"] and result["same_kernel"] is True
    assert generations.active(receiver) == before                       # imported, frozen, not active
    assert generations.verify(receiver / "generations" / result["id"])["ok"]
    trial = Trial.load(receiver / "TRIAL.json")
    assert trial.candidate == result["id"] and trial.incumbent == before and trial.decision is None
    kinds = [event["kind"] for event in Ledger(receiver / "ledger.jsonl")]
    assert "generation.imported" in kinds and "trial.opened" in kinds
    cli.main(["--home", str(receiver), "trial"])
    assert result["id"] in capsys.readouterr().out


def _write_zip(path, members: dict[str, str]):
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def _manifest_for(organs: dict[str, str]) -> str:
    return json.dumps({"id": "gen-evil", "label": "evil", "kernel_digest": "x",
                       "organ_files": {name.split("/", 1)[1]: digest_text(text) for name, text in organs.items()}})


def test_import_refuses_path_traversal(tmp_path):
    receiver = _home(tmp_path, "receiver")
    archive = _write_zip(tmp_path / "evil.zip", {"MANIFEST.json": "{}", "../outside.py": "x = 1\n"})
    with pytest.raises(ImportRefused, match="unexpected archive member"):
        import_generation(receiver, archive)
    assert not (tmp_path / "outside.py").exists()


def test_import_refuses_tampered_organs(tmp_path):
    sender, receiver = _home(tmp_path, "sender"), _home(tmp_path, "receiver")
    variant = _variant(tmp_path, sender)
    archive = export_generation(sender, variant["id"], tmp_path / "variant.zip")
    with zipfile.ZipFile(archive) as source:
        members = {name: source.read(name).decode("utf-8") for name in source.namelist()}
    members["organs/repair.py"] += "\n# changed after export\n"
    with pytest.raises(ImportRefused, match="digests"):
        import_generation(receiver, _write_zip(tmp_path / "tampered.zip", members))


def test_import_refuses_forbidden_imports_even_with_matching_digests(tmp_path):
    receiver = _home(tmp_path, "receiver")
    organs = {"organs/repair.py": "import socket\n\ndef run(view, cockpit):\n    return {'status': 'x', 'final_files': {}}\n"}
    archive = _write_zip(tmp_path / "net.zip", {"MANIFEST.json": _manifest_for(organs), **organs})
    with pytest.raises(ImportRefused, match="static check failed"):
        import_generation(receiver, archive)
    assert len(generations.list_generations(receiver)) == 1              # nothing was frozen
