"""No providers, resident services, or field homes; real OS locks in tmp_path."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from runesmith.app import server
from runesmith.app.workspace import WorkspaceError


def test_revisit_and_restart_preserve_isolated_home(tmp_path):
    first, second, home = tmp_path / 'first', tmp_path / 'second', tmp_path / 'isolated'
    first.mkdir(); second.mkdir()
    s = server.Studio(first, home)
    try:
        s.open(second)
        s.open(first)
        assert s.ws.home == home
        assert not (first / '.runesmith').exists()
        assert next(r for r in s.recent() if r['path'] == str(first))['home'] == str(home)
    finally:
        s.close()
    again = server.Studio(first)
    try:
        assert again.ws.home == home and not (first / '.runesmith').exists()
    finally:
        again.close()


def test_two_homes_cannot_own_same_source_root(tmp_path):
    root = tmp_path / 'project'; root.mkdir()
    first = server.Studio(root, tmp_path / 'home-a')
    try:
        with pytest.raises(WorkspaceError, match='overlap|bound|different'):
            server.Studio(root, tmp_path / 'home-b')
        assert not (tmp_path / 'home-b').exists()
    finally:
        first.close()


@pytest.mark.parametrize('reverse', [False, True])
def test_parent_and_child_roots_exclude_each_other(tmp_path, reverse):
    parent = tmp_path / 'project'; child = parent / 'child'; child.mkdir(parents=True)
    a, b = (child, parent) if reverse else (parent, child)
    first = server.Studio(a, tmp_path / 'home-a')
    try:
        with pytest.raises(WorkspaceError, match='overlap'):
            server.Studio(b, tmp_path / 'home-b')
        assert not (tmp_path / 'home-b').exists()
    finally:
        first.close()


def test_siblings_remain_allowed_and_root_lock_releases_on_close(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'ab'
    a.mkdir(); b.mkdir()
    one = server.Studio(a); two = server.Studio(b)
    try:
        assert one.ws.root == a and two.ws.root == b
    finally:
        one.close(); two.close()
    again = server.Studio(a)
    assert again.close()


def test_missing_registered_home_never_silently_initializes_default(tmp_path):
    root = tmp_path / 'project'; root.mkdir()
    home = tmp_path / 'isolated'; s = server.Studio(root, home); s.close()
    home.rename(tmp_path / 'preserved-home')
    with pytest.raises(WorkspaceError, match='missing|unavailable'):
        server.Studio(root)
    assert not (root / '.runesmith').exists() and not home.exists()


def test_a_registered_home_cannot_be_rebound_to_another_root(tmp_path):
    a, b, home = tmp_path / 'a', tmp_path / 'b', tmp_path / 'isolated'
    a.mkdir(); b.mkdir()
    s = server.Studio(a, home); s.close()
    with pytest.raises(WorkspaceError, match='bound|different'):
        server.Studio(b, home)


def test_synchronous_entrypoint_obeys_overlapping_root_ownership(tmp_path, monkeypatch):
    from runesmith.app.build_jobs import BuildJob, run_synchronous_build_job
    from runesmith.app.workspace import Workspace
    root = tmp_path / 'project'; child = root / 'child'; child.mkdir(parents=True)
    prepared = Workspace(child, tmp_path / 'prepared')
    first = server.Studio(root)
    monkeypatch.setattr(server.Worker, '_execute', lambda *args, **kw: pytest.fail('Overlapping job executed'))
    try:
        with pytest.raises(WorkspaceError, match='overlap'):
            run_synchronous_build_job(child, BuildJob('build', {}), home=prepared.home)
    finally:
        first.close()


@pytest.mark.parametrize('which', ['root_contains_home', 'home_inside_root', 'nested_homes'])
def test_an_isolated_home_is_also_an_owned_write_scope(tmp_path, which):
    a, b, home = tmp_path / 'a', tmp_path / 'b', tmp_path / 'separate'
    a.mkdir(); b.mkdir()
    first = server.Studio(a, home)
    target, destination = {
        'root_contains_home': (home, tmp_path / 'third'),
        'home_inside_root': (b, a / 'child-home'),
        'nested_homes': (b, home / 'child-home'),
    }[which]
    try:
        with pytest.raises(WorkspaceError, match='overlap'):
            server.Studio(target, destination)
        assert not destination.exists()
    finally:
        first.close()


def test_root_lease_excludes_other_process_and_is_released_after_crash(tmp_path):
    from runesmith.app.workspace_ownership import RootLease
    root, profile = tmp_path / 'root', tmp_path / 'locks'
    # Only a disposable lock-holder child, never a Studio or external provider.
    script = """
import sys
from pathlib import Path
from runesmith.app.workspace_ownership import RootLease
lease = RootLease(Path(sys.argv[1]), Path(sys.argv[2]))
assert lease.acquire()
print('held', flush=True)
sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, '-u', '-c', script, str(root), str(profile)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'held'
        for candidate in (root, root / 'child', root.parent):
            lease = RootLease(candidate, profile)
            assert not lease.acquire() and not lease.leases
        sibling = RootLease(tmp_path / 'root-other', profile)
        assert sibling.acquire(); sibling.close()
    finally:
        child.kill(); child.communicate(timeout=5)
    lease = RootLease(root, profile)
    assert lease.acquire(); lease.close()


def test_failed_partial_acquisition_does_not_hold_shared_ancestors(tmp_path):
    from runesmith.app.workspace_ownership import RootLease
    profile = tmp_path / 'profile'; root = tmp_path / 'root'
    one = RootLease(root, profile); assert one.acquire()
    failed = RootLease(root / 'child', profile); assert not failed.acquire()
    one.close()
    parent = RootLease(root.parent, profile)
    assert parent.acquire(); parent.close()


def test_bad_registry_never_falls_back_to_new_home(tmp_path):
    root = tmp_path / 'root'; root.mkdir()
    server.STUDIO_DIR.mkdir()
    (server.STUDIO_DIR / 'workspace-bindings.json').write_text('{broken')
    with pytest.raises(WorkspaceError, match='unreadable'):
        server.Studio(root)
    assert not (root / '.runesmith').exists()


def test_binding_lives_beyond_optional_recent_cache(tmp_path):
    from runesmith.app.workspace_ownership import Bindings
    root, home = tmp_path / 'root', tmp_path / 'home'; root.mkdir()
    s = server.Studio(root, home); s.close()
    (server.STUDIO_DIR / 'studio.json').write_text('{broken')
    assert Bindings(server.STUDIO_DIR).resolve(root)['home'] == str(home)
    again = server.Studio(root)
    assert again.ws.home == home
    again.close()


def test_resolver_is_read_only_and_open_preserves_reviewed_home(tmp_path):
    first, other = tmp_path / 'first', tmp_path / 'other'; first.mkdir(); other.mkdir()
    home = tmp_path / 'isolated'
    s = server.Studio(first)
    try:
        before = (server.STUDIO_DIR / 'workspace-bindings.json').read_bytes()
        pair = server.api_workspace_resolve(s, {'path': [str(other)], 'home': [str(home)]}, {})
        assert pair == {'path': str(other), 'home': str(home), 'basis': 'explicit', 'registered': False}
        assert not home.exists() and (server.STUDIO_DIR / 'workspace-bindings.json').read_bytes() == before
        result = server.api_workspace_open(s, {}, {'path': pair['path'], 'home': pair['home']})
        assert result['home'] == str(home) and s.worker.paused
        assert not (other / '.runesmith').exists()
    finally:
        s.close()


def test_conflicting_binding_after_preview_refuses_before_initializing(tmp_path):
    from runesmith.app.workspace_ownership import Bindings
    root = tmp_path / 'root'; root.mkdir()
    picked, changed = tmp_path / 'picked', tmp_path / 'changed'; changed.mkdir()
    pair = Bindings(server.STUDIO_DIR).resolve(root, picked)
    Bindings(server.STUDIO_DIR).remember(root, changed)
    with pytest.raises(WorkspaceError, match='different'):
        server.Studio(root, Path(pair['home']))
    assert not picked.exists()


def test_new_folder_cannot_implicitly_open_an_existing_project(tmp_path):
    first, other = tmp_path / 'first', tmp_path / 'other'; first.mkdir(); other.mkdir()
    s = server.Studio(first)
    try:
        with pytest.raises(WorkspaceError, match='already exists'):
            server.api_workspace_open(s, {}, {'path': str(other), 'create': True})
        assert not (other / '.runesmith').exists() and s.ws.root == first
    finally:
        s.close()


def test_root_and_home_lease_remain_held_through_inflight_handler(tmp_path):
    from runesmith.app.workspace_ownership import RootLease
    root, home = tmp_path / 'root', tmp_path / 'home'; root.mkdir()
    s = server.Studio(root, home)
    try:
        with s.operation(s.epoch):
            assert not s.close()
            for path in (root, home):
                contender = RootLease(path, server.STUDIO_DIR)
                assert not contender.acquire()
        assert s.close()
        for path in (root, home):
            contender = RootLease(path, server.STUDIO_DIR)
            assert contender.acquire(); contender.close()
    finally:
        s.close()


def test_failed_registry_write_leaves_source_running_and_releases_destination(tmp_path, monkeypatch):
    from runesmith.app.workspace_ownership import Bindings, RootLease
    a, b = tmp_path / 'a', tmp_path / 'b'; a.mkdir(); b.mkdir()
    s = server.Studio(a)
    try:
        def unavailable(*_args):
            raise OSError('fixture registry unavailable')
        monkeypatch.setattr(Bindings, 'remember', unavailable)
        with pytest.raises(OSError, match='unavailable'):
            s.open(b)
        assert s.ws.root == a and not s.worker._closing
        assert not (b / '.runesmith' / 'config.json').exists()
        contender = RootLease(b, server.STUDIO_DIR)
        assert contender.acquire(); contender.close()
    finally:
        s.close()


@pytest.mark.parametrize('document', [
    'null', '{"version":1,"version":1,"bindings":[]}',
    '{"version":true,"bindings":[]}', '{"version":1,"bindings":[{}]}',
    '{"version":1,"bindings":[{"root":"relative","home":"relative"}]}',
])
def test_malformed_binding_record_fails_closed(tmp_path, document):
    from runesmith.app.workspace_ownership import Bindings
    server.STUDIO_DIR.mkdir()
    (server.STUDIO_DIR / 'workspace-bindings.json').write_text(document)
    with pytest.raises(WorkspaceError):
        Bindings(server.STUDIO_DIR).resolve(tmp_path / 'project')


def test_registry_lock_contention_does_not_write_or_initialize(tmp_path):
    from runesmith.app.workspace_ownership import FileLease
    root = tmp_path / 'root'; root.mkdir()
    held = FileLease(server.STUDIO_DIR / 'workspace-bindings.lock'); assert held.acquire()
    try:
        with pytest.raises(WorkspaceError, match='being updated'):
            server.Studio(root)
        assert not (server.STUDIO_DIR / 'workspace-bindings.json').exists()
        assert not (root / '.runesmith' / 'STUDIO_STATE.json').exists()
    finally:
        held.close()
    s = server.Studio(root); assert s.close()


def test_redirected_profile_control_is_refused(tmp_path):
    from runesmith.app.workspace_ownership import RootLease
    target = tmp_path / 'actual'; target.mkdir()
    link = tmp_path / 'redirect'
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks is unavailable on this host')
    with pytest.raises(WorkspaceError, match='redirected'):
        RootLease(tmp_path / 'project', link).acquire()
    assert not list(target.iterdir())


def test_http_root_home_selection_is_authenticated_and_context_bound(tmp_path):
    import threading
    from urllib.parse import urlencode
    from test_studio import call
    first, second, home = tmp_path / 'first', tmp_path / 'second', tmp_path / 'isolated'
    first.mkdir(); second.mkdir()
    s = server.Studio(first); httpd = server.bind(s, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    try:
        route = '/api/workspaces/resolve?' + urlencode({'path': str(second), 'home': str(home)})
        assert call(s, 'GET', route, cookie=False)[0] == 401
        status, pair, _ = call(s, 'GET', route)
        assert status == 200 and pair['home'] == str(home) and not home.exists()
        old_epoch = s.epoch
        status, selected, _ = call(s, 'POST', '/api/workspaces/open',
                                   {'path': pair['path'], 'home': pair['home']})
        assert status == 200 and selected['home'] == str(home) and selected['paused']
        assert call(s, 'POST', '/api/workspaces/open', {'path': str(first)},
                    headers={server.WORKSPACE_HEADER: old_epoch})[0] == 409
        child = second / 'child'; child.mkdir()
        status, error, _ = call(s, 'POST', '/api/workspaces/open',
                               {'path': str(child), 'home': str(tmp_path / 'blocked-home')})
        assert status == 409 and 'overlap' in error['error']
        assert s.ws.root == second and not (tmp_path / 'blocked-home').exists()
    finally:
        s.close(); httpd.shutdown(); httpd.server_close(); thread.join(3)
