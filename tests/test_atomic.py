"""Atomic replacement survives a brief reader on Windows (found by out-of-box journey R1, 2026-09-27)."""

from __future__ import annotations

import os
import threading

import pytest

from runesmith import atomic


@pytest.mark.skipif(os.name != "nt", reason="a sharing violation on an open file is Windows behaviour")
def test_replace_waits_for_a_brief_reader_on_windows(tmp_path):
    target = tmp_path / "DRAFT.json"
    target.write_text("old", encoding="utf-8")
    new = tmp_path / "DRAFT.json.1a2b3c.tmp"
    new.write_text("new", encoding="utf-8")
    reader = open(target, "rb")                     # the Studio page reading the draft while a build saves it
    try:
        with pytest.raises(PermissionError):        # what broke the journey's build: plain os.replace refuses
            os.replace(new, target)
        threading.Timer(0.3, reader.close).start()
        atomic.replace(new, target)                 # waits for the reader, then replaces
    finally:
        reader.close()
    assert target.read_text(encoding="utf-8") == "new" and not new.exists()


def test_replace_gives_up_with_the_original_error(tmp_path, monkeypatch):
    calls = []

    def refuse(src, dst):
        calls.append((src, dst))
        raise PermissionError(13, "denied")

    monkeypatch.setattr(atomic.os, "replace", refuse)
    monkeypatch.setattr(atomic.time, "sleep", lambda seconds: None)
    with pytest.raises(PermissionError):
        atomic.replace(tmp_path / "a", tmp_path / "b", attempts=3)
    assert len(calls) == (3 if os.name == "nt" else 1)   # elsewhere a refusal is not a transient sharing violation
