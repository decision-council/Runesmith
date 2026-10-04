"""All Studio profiles/coordination files in tests stay in disposable folders."""
import pytest


@pytest.fixture(autouse=True)
def isolated_studio_profile(tmp_path, monkeypatch):
    from runesmith.app import server
    # Profile/binding writes must not become project source between a quote and
    # its synchronous execution. This sibling remains inside pytest's D: temp.
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path.parent / (tmp_path.name + '-studio-profile'))


@pytest.fixture
def old_caps(monkeypatch):
    """The size limits as they were before a file the milestone must change was shown whole up to 160,000 bytes: 40,000
    bytes a file and 48,000 characters in all. The tests of files shown in parts, and of a source budget that other files
    fill, use files of that size; the limits are parameters of the same rules, so the rules are tested as before."""
    from runesmith.app import source_focus
    monkeypatch.setattr(source_focus, 'FOCUSED_FILE_BYTES', 40000)
    monkeypatch.setattr(source_focus, 'CONTEXT_FILE_BYTES', 40000)
    monkeypatch.setattr(source_focus, 'CONTEXT_CHARS', 48000)
