"""Journey J7: a hostile environment. What a person meets must be plain words, never a traceback."""
import socket
from types import SimpleNamespace

import pytest

from runesmith import cli
from runesmith.app import server
from runesmith.app.workspace import WorkspaceError
from runesmith.app.workspace_ownership import Bindings


def test_a_deleted_home_inside_the_folder_starts_fresh_but_a_missing_home_elsewhere_is_refused(tmp_path):
    # J7-B1: deleting the folder's hidden .runesmith data used to lock the folder out for good.
    profile, root = tmp_path / "profile", tmp_path / "Mina böcker & anteckningar (2026)"
    profile.mkdir()
    root.mkdir()
    bindings = Bindings(profile)
    first = bindings.resolve(root)
    (root / ".runesmith").mkdir()
    bindings.remember(root, first["home"])
    assert "recreated" not in bindings.resolve(root)
    (root / ".runesmith").rmdir()                                    # deleted with a "clean up hidden folders"
    again = bindings.resolve(root)
    assert again["recreated"] and again["home"] == first["home"]
    other_root, elsewhere = tmp_path / "project", tmp_path / "drive" / "home"
    other_root.mkdir()
    elsewhere.mkdir(parents=True)
    bindings.remember(other_root, elsewhere)
    elsewhere.rmdir()                                                # like an unplugged drive: keep refusing
    with pytest.raises(WorkspaceError, match="missing or unavailable"):
        bindings.resolve(other_root)


def test_the_launcher_says_why_it_cannot_open_a_folder_without_a_traceback(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise WorkspaceError("The registered home is missing or unavailable; restore it before opening this root.")
    monkeypatch.setattr(server, "serve", refuse)
    with pytest.raises(SystemExit) as stop:
        cli.cmd_up(SimpleNamespace(folder=str(tmp_path), last=False, home=None, port=None, no_browser=True))
    assert str(stop.value).startswith("Runesmith could not open") and "restore it" in str(stop.value)


def test_a_busy_port_asked_for_explicitly_is_explained(monkeypatch):
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    try:
        studio = SimpleNamespace(port=None, publish_beacon=lambda: None)
        monkeypatch.setattr(server, "make_handler", lambda studio: None)
        with pytest.raises(SystemExit, match=f"Port {busy} is already in use by another program"):
            server.bind(studio, busy)
    finally:
        blocker.close()
