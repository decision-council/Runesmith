"""All Studio profiles/coordination files in tests stay in disposable folders."""
import pytest


@pytest.fixture(autouse=True)
def isolated_studio_profile(tmp_path, monkeypatch):
    from runesmith.app import server
    # Profile/binding writes must not become project source between a quote and
    # its synchronous execution. This sibling remains inside pytest's D: temp.
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path.parent / (tmp_path.name + '-studio-profile'))
