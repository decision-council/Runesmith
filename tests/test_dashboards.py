"""Dashboard reads/configuration in isolated folders, never resident Studio."""
import json
from types import SimpleNamespace

import pytest

from runesmith.app import dashboards as db
from runesmith.app.workspace import Workspace, WorkspaceError, _write_json
from runesmith.app.server import api_dashboards, api_dashboards_change
from runesmith.app.worker import EventBus
from runesmith.canon import digest


@pytest.fixture
def ws(tmp_path):
    root = tmp_path/'current'; root.mkdir()
    return Workspace(root)


def other(ws):
    root = ws.root.parent/'other'; root.mkdir()
    home = ws.root.parent/'isolated-home'; home.mkdir()
    return root, home


def register(ws, root, home):
    return db.change(ws, revision=db.configuration(ws)['revision'], action='add',
                     project={'name':'Other project', 'root':str(root), 'home':str(home)})


def test_default_view_does_not_create_configuration_or_change_files(ws):
    before = {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    info = db.view(ws)
    after = {p.relative_to(ws.home): p.read_bytes() for p in ws.home.rglob('*') if p.is_file()}
    assert before == after and info['projects'][0]['id'] == 'current'
    assert not (ws.home/'DASHBOARDS.json').exists()


def test_add_remove_only_view_and_isolated_home_not_workspace(ws, monkeypatch):
    root, home = other(ws)
    (root/'code.py').write_text('untouched')
    (home/'secrets.json').write_text('SECRET_NEVER_RETURNED')
    _write_json(home/'PLAN.json', {'milestones':[{'status':'done'},{'status':'open'}]})
    before = {p: p.read_bytes() for p in ws.root.parent.rglob('*') if p.is_file() and not p.is_relative_to(ws.home)}
    config = register(ws, root, home)
    monkeypatch.setattr(Workspace, '__init__', lambda *a, **k: pytest.fail('Read initialized a project'))
    info = db.view(ws); row = info['projects'][1]
    assert row['progress']['milestones'] == {'done':1,'open':1}
    assert 'SECRET_NEVER_RETURNED' not in json.dumps(info)
    db.change(ws, revision=config['revision'], action='remove', project_id=row['id'])
    assert all(p.read_bytes()==raw for p, raw in before.items())
    assert len(db.view(ws)['projects']) == 1


def test_missing_home_is_unavailable_without_initializing(ws):
    root, home = other(ws); missing = home/'not-created'
    register(ws, root, missing)
    assert not db.view(ws)['projects'][1]['available'] and not missing.exists()


def test_panels_and_registration_are_cas_guarded_and_not_grants(ws):
    config = db.configuration(ws); settings = ws.settings()
    db.change(ws, revision=config['revision'], action='panels', project_id='current', panels=[])
    assert db.view(ws)['projects'][0]['panels'] == [] and ws.settings() == settings
    with pytest.raises(WorkspaceError, match='reload'):
        db.change(ws, revision=config['revision'], action='panels', project_id='current', panels=['modes'])
    with pytest.raises(WorkspaceError, match='stays available'):
        db.change(ws, revision=db.configuration(ws)['revision'], action='remove', project_id='current')


@pytest.mark.parametrize('root', ['relative/folder', '//server/share', 'C:\\fake\\..\\other'])
def test_nonlocal_or_ambiguous_paths_refused(ws, root):
    with pytest.raises(WorkspaceError): register(ws, root, ws.home)


def test_duplicate_project_or_home_refused(ws):
    with pytest.raises(WorkspaceError, match='already tracked'): register(ws, ws.root, ws.home)


def test_measurement_current_vs_stale_and_unavailable_connector(ws):
    item = {'id':'orders','name':'Orders','goal':'Sales','unit':'orders','source_kind':'ga4','enabled':True}
    _write_json(ws.home/'MEASUREMENTS.json', {'items':[item]})
    rid='a'*64
    _write_json(ws.home/'measurement-latest/orders.json', {'receipt':rid})
    _write_json(ws.home/f'measurement-receipts/{rid}.json', {'status':'measured','value':0,
        'measured_at':'2026-01-01T00:00:00Z','definition_digest':digest(item),'raw_rows':['PRIVATE']})
    m = db.view(ws)['projects'][0]['measurements'][0]
    assert m['value']==0 and m['current_definition'] is True and m['connector']=='unavailable'
    assert 'PRIVATE' not in json.dumps(db.view(ws)) and 'does not remeasure' in m['freshness']
    item['goal']='New goal'; _write_json(ws.home/'MEASUREMENTS.json', {'items':[item]})
    assert db.view(ws)['projects'][0]['measurements'][0]['current_definition'] is False


def test_recorded_worker_is_not_claimed_live_and_outputs_are_filtered(ws):
    _write_json(ws.home/'STUDIO_CURRENT.json', {'kind':'build','id':'job1','params':{'secret':'HIDE'}})
    _write_json(ws.home/'STUDIO_JOBS.json', [{'kind':'build','result':'failed','outcome':{'summary':'Failed','raw':'HIDE'}}])
    row=db.view(ws)['projects'][0]
    assert row['recorded_inflight']['id']=='job1' and 'HIDE' not in json.dumps(row)
    assert 'not an atomic snapshot or a liveness check' in row['scope']


def test_corrupt_evidence_does_not_hide_other_project_or_rewrite(ws):
    root, home=other(ws);register(ws,root,home)
    _write_json(home/'PLAN.json', {'milestones':[{'status':[]}]})
    (home/'MEASUREMENTS.json').write_text('broken')
    before=(home/'PLAN.json').read_bytes()
    rows=db.view(ws)['projects']
    assert rows[0]['available'] and not rows[1]['available'] and rows[1]['errors']
    assert (home/'PLAN.json').read_bytes()==before


def test_oversized_or_corrupt_registry_fails_closed(ws):
    path=ws.home/'DASHBOARDS.json';path.write_text('broken')
    with pytest.raises(WorkspaceError,match='unreadable'):db.view(ws)
    assert path.read_text()=='broken'


def test_api_calls_do_not_enqueue_jobs(ws):
    studio=SimpleNamespace(ws=ws,bus=EventBus())  # no worker exists
    info=api_dashboards(studio,{},{});
    api_dashboards_change(studio,{}, {'revision':info['revision'],'action':'panels','project_id':'current','panels':['progress']})
    assert db.configuration(ws)['projects'][0]['panels']==['progress']


def test_linked_receipts_are_not_followed(ws):
    secret=ws.root.parent/'secret.json';secret.write_text('{"PRIVATE": true}')
    try:(ws.home/'PLAN.json').symlink_to(secret)
    except OSError:pytest.skip('Symlink creation unavailable')
    row=db.view(ws)['projects'][0]
    assert row['errors'] and 'PRIVATE' not in json.dumps(row)


def test_link_guard_without_windows_symlink_privilege(ws, monkeypatch):
    from pathlib import Path
    target=ws.home/'PLAN.json';target.write_text('{"PRIVATE":true}')
    original=Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda p:p==target or original(p))
    row=db.view(ws)['projects'][0]
    assert row['errors'] and 'PRIVATE' not in json.dumps(row)


def test_unknown_mode_schema_is_not_presented_as_enabled(ws):
    _write_json(ws.home/'WORK_MODES.json',{'schema':'future','modes':[{'id':'build','enabled':True}]})
    row=db.view(ws)['projects'][0]
    assert row['errors'] and row['modes']==[]
