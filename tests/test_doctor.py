"""doctor explains problems; requalify carries a generation across a kernel update."""

from __future__ import annotations

import json

from runesmith import cli, generations
from runesmith.doctor import diagnose_home, requalify
from runesmith.ledger import Ledger


def _by_check(rows):
    return {row["check"]: row for row in rows}


def test_doctor_on_a_fresh_home_and_on_a_missing_one(tmp_path, capsys):
    rows = _by_check(diagnose_home(tmp_path / "nowhere", network=False))
    assert rows["home"]["ok"] is False and rows["home"]["fix"] == "runesmith init"
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    rows = _by_check(diagnose_home(home, network=False))
    assert rows["ledger"]["ok"] and rows["active generation"]["ok"] and rows["generation kernel"]["ok"]
    assert rows["instrument local (repair)"]["ok"] is None            # offline: not probed, not a failure
    cli.main(["--home", str(home), "doctor", "--offline"])
    out = capsys.readouterr().out
    fixes = [line for line in out.splitlines() if line.startswith("[FIX]")]
    assert all(" disk " in line for line in fixes), fixes            # only the machine's free disk may vary
    assert "[ok ] ledger" in out and "[ok ] generation kernel" in out


def test_requalify_after_a_kernel_update(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    old = generations.active(home)
    manifest_path = home / "generations" / old / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["kernel_digest"] = "sha256:" + "0" * 64                  # as if frozen under an older Runesmith
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    rows = _by_check(diagnose_home(home, network=False))
    assert rows["generation kernel"]["ok"] is False and rows["generation kernel"]["fix"] == "runesmith generations requalify"
    result = requalify(home)
    assert result["requalified"] and result["activated"] and result["from"] == old
    new = generations.active(home)
    assert new == result["id"] and new != old
    assert generations.verify(home / "generations" / new)["ok"]       # organs and kernel both verify now
    assert generations.load(home / "generations" / new)["organ_files"] == manifest["organ_files"]   # same organs
    assert _by_check(diagnose_home(home, network=False))["generation kernel"]["ok"]
    kinds = [event["kind"] for event in Ledger(home / "ledger.jsonl")]
    assert "generation.requalified" in kinds
    assert requalify(home)["requalified"] is False                    # idempotent under the same kernel


def test_doctor_survives_a_config_without_instruments_or_roles(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    (home / "runesmith.json").write_text('{"schema": "runesmith.config.v1"}', encoding="utf-8")
    rows = _by_check(diagnose_home(home, network=False))
    assert rows["roles"]["ok"] is False and "roles" in rows["roles"]["fix"]


def test_corrupted_attention_state_starts_fresh(tmp_path):
    from runesmith.kaizen.attention import Attention
    (tmp_path / "ATTENTION.json").write_text("{not json", encoding="utf-8")
    assert Attention.load(tmp_path / "ATTENTION.json") is None
