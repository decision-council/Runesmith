"""Workspace handoffs in disposable homes; no resident Studio or inference."""
import json
import io
import gc
import threading

import pytest

from runesmith.app import server
from runesmith.app.workspace import WorkspaceError


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # Even a regression to Path('') must stay disposable.
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path / 'profile')
    root = tmp_path / 'first'
    root.mkdir()
    s = server.Studio(root)
    yield s
    s.close()


def available(home):
    lock = server.InstanceLock(home)
    ok = lock.acquire()
    if ok:
        lock.close()
    return ok


def target(studio):
    root = studio.ws.root.parent / 'second'
    root.mkdir()
    return root


def test_studio_owns_home_until_worker_has_stopped(studio):
    home = studio.ws.home
    assert not available(home)
    assert studio.close()
    assert not studio.worker._thread.is_alive()
    assert not studio.worker._watch.is_alive()
    assert available(home)


def test_destination_is_locked_before_workspace_initialization(studio, monkeypatch):
    root = target(studio)
    original = server.Workspace
    seen = []
    def checked(path, home=None):
        seen.append(not available(home or path / '.runesmith'))
        return original(path, home)
    monkeypatch.setattr(server, 'Workspace', checked)
    studio.open(root)
    assert seen == [True]


def test_busy_destination_is_not_initialized_or_old_worker_stopped(studio):
    root = target(studio)
    hold = server.InstanceLock(root / '.runesmith')
    assert hold.acquire()
    before = set(hold.path.parent.iterdir())
    old = studio.worker
    try:
        with pytest.raises(WorkspaceError, match='owned|another'):
            studio.open(root)
        assert studio.worker is old and not old._closing
        assert set(hold.path.parent.iterdir()) == before
    finally:
        hold.close()


def test_active_job_refuses_even_folder_creation(studio, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def job():
        entered.set()
        release.wait(5)
        return {}
    monkeypatch.setattr(studio.worker, '_job_health', job)
    studio.worker.enqueue('health')
    assert entered.wait(3)
    root = studio.ws.root.parent / 'not-created'
    try:
        with pytest.raises(WorkspaceError, match='current|running'):
            server.api_workspace_open(studio, {}, {'path': str(root), 'create': True})
        assert not root.exists() and not studio.worker._closing
    finally:
        release.set()


def test_idle_handoff_stops_both_threads_and_retains_queue(studio):
    old, old_home, old_bus, epoch = studio.worker, studio.ws.home, studio.bus, studio.epoch
    old.pause()
    queued = old.enqueue('health')
    studio.open(target(studio))
    assert not old._thread.is_alive() and not old._watch.is_alive()
    assert available(old_home) and not available(studio.ws.home)
    assert json.loads((old_home / 'STUDIO_QUEUE.json').read_text())['jobs'] == [queued]
    assert studio.worker.paused and studio.epoch != epoch
    assert studio.bus is not old_bus
    assert old_bus.recent[-1]['kind'] == 'workspace'


def test_same_workspace_is_noop_and_does_not_drop_isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path / 'profile')
    root = tmp_path / 'project'; root.mkdir()
    isolated = tmp_path / 'isolated'
    s = server.Studio(root, isolated)
    old = s.worker
    try:
        assert s.open(root) is s.ws
        assert s.worker is old and s.ws.home == isolated
        assert not (root / '.runesmith').exists()
        with pytest.raises(WorkspaceError, match='different'):
            s.open(root, tmp_path / 'other-home')
    finally:
        s.close()


def test_preparation_failure_leaves_source_live_and_destination_unowned(studio, monkeypatch):
    root = target(studio); old = studio.worker
    def fail(*args):
        raise WorkspaceError('fixture initialization failed')
    monkeypatch.setattr(server, 'Workspace', fail)
    with pytest.raises(WorkspaceError, match='initialization failed'):
        studio.open(root)
    assert studio.worker is old and not old._closing
    assert not available(old.ws.home) and available(root / '.runesmith')


def test_drain_timeout_retains_source_lease_and_starts_no_destination(studio, monkeypatch):
    old, root = studio.worker, target(studio)
    with monkeypatch.context() as patch:
        patch.setattr(old, 'wait_stopped', lambda timeout=2: False)
        with pytest.raises(WorkspaceError, match='stopp'):
            studio.open(root)
        assert studio.worker is old and not available(old.ws.home)
        assert available(root / '.runesmith')
        assert 'cannot resume' in studio.switch_status()['warning']
        with pytest.raises(WorkspaceError, match='cannot resume'):
            old.resume()
    studio.open(root)
    assert studio.ws.root == root and studio.worker.paused


def test_shutdown_does_not_release_lease_while_job_remains(studio, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def job():
        entered.set(); release.wait(5); return {}
    monkeypatch.setattr(studio.worker, '_job_health', job)
    studio.worker.enqueue('health'); assert entered.wait(3)
    try:
        assert not studio.close(timeout=0.01)
        assert not available(studio.ws.home)
    finally:
        release.set()
        assert studio.close()
    assert available(studio.ws.home)


def test_api_operation_blocks_switch_and_stale_epoch_is_rejected(studio):
    root = target(studio); epoch = studio.epoch
    with studio.operation(epoch, mutating=True):
        with pytest.raises(WorkspaceError, match='request'):
            studio.open(root)
        assert not (root / '.runesmith').exists()
    studio.open(root)
    with pytest.raises(WorkspaceError, match='changed'):
        with studio.operation(epoch, mutating=True):
            pytest.fail('stale action admitted')
    with pytest.raises(WorkspaceError, match='Reload'):
        with studio.operation(None, mutating=True):
            pytest.fail('unbound mutation admitted')


def test_beacon_moves_only_with_owned_home(studio):
    studio.port = 17300  # synthetic metadata, no listener
    studio.publish_beacon()
    old = studio.ws.home
    studio.open(target(studio))
    assert not (old / 'studio.lock.json').exists()
    beacon = json.loads((studio.ws.home / 'studio.lock.json').read_text())
    assert beacon['folder'] == str(studio.ws.root) and beacon['port'] == 17300
    studio.close()
    assert not (studio.ws.home / 'studio.lock.json').exists()


@pytest.mark.parametrize('value', ['', '   ', None, 123, '.', '..', 'relative-project'])
def test_missing_or_nontext_path_never_resolves_to_cwd(studio, value):
    with pytest.raises(WorkspaceError):
        server.api_workspace_open(studio, {}, {'path': value})


def dispatch(s, method, path, body=None, epoch=None):
    handler = object.__new__(server.make_handler(s))
    handler.headers = {server.WORKSPACE_HEADER: epoch} if epoch is not None else {}
    result = []
    handler._send = lambda status, raw, content_type, extra=None: result.append((status, json.loads(raw), extra))
    handler._dispatch(method, path, {}, body or {})
    return result[0]


def test_handler_binds_mutations_and_reads_to_the_page_home(studio):
    epoch = studio.epoch
    status, data, headers = dispatch(studio, 'GET', '/api/session')
    assert status == 200 and headers[server.WORKSPACE_HEADER] == epoch
    assert dispatch(studio, 'POST', '/api/settings', {'workspace_name': 'wrong'})[0] == 409
    root = target(studio)
    status, data, headers = dispatch(studio, 'POST', '/api/workspaces/open', {'path': str(root)}, epoch)
    assert status == 200 and data['paused'] and headers[server.WORKSPACE_HEADER] != epoch
    assert dispatch(studio, 'POST', '/api/settings', {'workspace_name': 'wrong'}, epoch)[0] == 409
    assert dispatch(studio, 'GET', '/api/state', epoch=epoch)[0] == 409
    assert studio.ws.settings()['workspace_name'] != 'wrong'
    assert dispatch(studio, 'POST', '/api/settings', {'workspace_name': 'right'}, studio.epoch)[0] == 200


def test_stale_switch_cannot_create_destination(studio):
    root = studio.ws.root.parent / 'never-created'
    assert dispatch(studio, 'POST', '/api/workspaces/open', {'path': str(root), 'create': True}, 'stale')[0] == 409
    assert not root.exists()


def test_api_handler_stays_pinned_during_a_concurrent_switch(studio, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    old_ws, epoch = studio.ws, studio.epoch
    seen = []
    def handler(s, q, body):
        entered.set(); release.wait(5); seen.append(s.ws); return {'ok': True}
    monkeypatch.setattr(server, 'ROUTES', [('GET', server.re.compile('/api/fixture'), handler)])
    thread = threading.Thread(target=lambda: dispatch(studio, 'GET', '/api/fixture', epoch=epoch))
    thread.start(); assert entered.wait(3)
    try:
        with pytest.raises(WorkspaceError, match='request'):
            studio.open(target(studio))
    finally:
        release.set(); thread.join(3)
    assert seen == [old_ws] and not thread.is_alive()


def test_start_failure_keeps_destination_owned_and_stopped(studio, monkeypatch):
    old = studio.ws.home
    def fail_start(worker):
        worker._watch.start()  # partial startup must not leave a live watcher
        raise RuntimeError('fixture thread startup failure')
    monkeypatch.setattr(server.Worker, 'start', fail_start)
    root = target(studio)
    assert studio.open(root).root == root
    assert 'startup failed' in studio.startup_error
    assert studio.worker._closing and not studio.worker._watch.is_alive()
    assert available(old) and not available(studio.ws.home)


def event_handler(studio, ready):
    h = object.__new__(server.make_handler(studio))
    h.wfile = io.BytesIO()
    h.send_response = lambda *args: None
    h.send_header = lambda *args: None
    h.end_headers = ready.set
    return h


def test_old_event_stream_gets_only_old_events_then_reload(studio):
    ready = threading.Event(); handler = event_handler(studio, ready)
    epoch, old_bus = studio.epoch, studio.bus
    thread = threading.Thread(target=lambda: handler._events({'workspace': [epoch]}))
    thread.start(); assert ready.wait(3)
    studio.open(target(studio))
    studio.bus.publish('log', {'text': 'new-home-private-fixture'})
    thread.join(3)
    assert not thread.is_alive() and not old_bus._subscribers
    raw = handler.wfile.getvalue()
    assert b'event: workspace' in raw and b'new-home-private-fixture' not in raw
    late = event_handler(studio, threading.Event())
    late._events({'workspace': [epoch]})
    assert b'event: workspace' in late.wfile.getvalue() and b'new-home-private-fixture' not in late.wfile.getvalue()


def test_optional_recent_failure_cannot_orphan_constructor_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path / 'profile')
    def fail(*args):
        raise TypeError('malformed optional recent metadata')
    monkeypatch.setattr(server.Studio, '_remember', fail)
    s = server.Studio(tmp_path)
    worker, home = s.worker, s.ws.home
    try:
        del s; gc.collect()
        assert worker._thread.is_alive() and not available(home)
        assert any('Recent folders could not be saved' in row['text'] for row in worker.lines)
    finally:
        worker.close(); assert worker.wait_stopped(); worker._studio_lease.close()


def test_constructor_base_exception_keeps_lease_on_surviving_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path / 'profile')
    release = threading.Event(); survivors = []
    def partial_start(worker):
        def stubborn_watch():
            worker._manual_seen = 0  # Retain the real worker just like a bound thread target.
            release.wait(8)
        worker._watch = threading.Thread(target=stubborn_watch)
        worker._watch.start(); survivors.append(worker)
        raise KeyboardInterrupt('fixture interrupt during partial startup')
    monkeypatch.setattr(server.Worker, 'start', partial_start)
    try:
        with pytest.raises(KeyboardInterrupt):
            server.Studio(tmp_path)
        gc.collect()
        assert survivors[0]._watch.is_alive() and not available(tmp_path / '.runesmith')
    finally:
        release.set()
        for worker in survivors:
            worker.close(); assert worker.wait_stopped(); worker._studio_lease.close()


def test_constructor_interrupt_after_start_cleans_up_when_threads_drain(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path / 'profile')
    def fail(*args):
        raise KeyboardInterrupt('fixture post-start interrupt')
    monkeypatch.setattr(server.Studio, '_remember', fail)
    with pytest.raises(KeyboardInterrupt):
        server.Studio(tmp_path)
    assert available(tmp_path / '.runesmith')


def test_interrupted_committed_switch_cannot_serve_unowned_mutations(studio, monkeypatch):
    def fail(*args):
        raise KeyboardInterrupt('fixture switch interruption')
    monkeypatch.setattr(server.Studio, '_remember', fail)
    with pytest.raises(KeyboardInterrupt):
        studio.open(target(studio))
    assert studio.closing and available(studio.ws.home)
    assert dispatch(studio, 'POST', '/api/settings', {'auto_work': True}, studio.epoch)[0] == 409


@pytest.mark.parametrize('data', [[], {'recent': None}, {'recent': 'wrong'}, {'recent': [None, 12, {}, {'path': 12}]}])
def test_malformed_recent_rows_are_not_startup_or_picker_failures(tmp_path, monkeypatch, data):
    monkeypatch.setattr(server, 'STUDIO_DIR', tmp_path)
    (tmp_path / 'studio.json').write_text(json.dumps(data), encoding='utf-8')
    assert server.Studio.recent() == []
