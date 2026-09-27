"""Explicit, compare-and-swap Milliner routing edits; never a generation or probe."""
from __future__ import annotations

from runesmith.canon import digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.workspace import WorkspaceError, _read_json, _now


def _spec(ws, name):
    spec = ws.config()['instruments'].get(name)
    if not spec:
        raise KeyError(name)
    if spec.get('kind') != 'milliner':
        raise WorkspaceError('This route editor is for Milliner instruments.')
    return spec


def route_view(ws, name):
    spec = _spec(ws, name)
    blockers = []
    try:
        if any(r['instrument'] == name for r in pending_authors(ws)):
            blockers.append('An author request still needs reconciliation. Retrieve or resolve it before changing this route.')
    except (AttributeError, KeyError, TypeError, ValueError):
        blockers.append('An author receipt has invalid structure; reconcile it before editing routes.')
    # Terminal unadmitted author answers are covered above; non-author requests
    # with uncertain submission/poll states must also remain pinned.
    for path in (ws.home/'inference-requests').glob('*.json'):
        record = _read_json(path, None)
        if not isinstance(record, dict):
            blockers.append('An inference receipt is unreadable; reconcile it before editing routes.')
            break
        if record.get('instrument') == name and record.get('state') not in ('terminal','refused'):
            blockers.append('A saved inference request has an unresolved outcome. No silent resubmission or rerouting.')
            break
    if (ws.home/'STUDIO_CURRENT.json').exists():
        blockers.append('A worker job is active or interrupted. Finish or reconcile it before editing routes.')
    return {'name':name,'revision':digest(spec),'model':spec.get('model',''),
            'fallback_models':list(spec.get('fallback_models') or []), 'blockers':blockers,
            'coverage':'Configuration only. Catalog presence does not prove free pricing, permission, quota or author quality.',
            'inference_calls':0}


def save_route(ws, name, *, revision, model, fallback_models, reason):
    """Call under the home's single-writer owner; keep credentials/roles/limits."""
    if not isinstance(reason,str) or not reason.strip() or len(reason)>2000:
        raise WorkspaceError('Give a route-change reason (1–2000 characters).')
    if not isinstance(fallback_models,list) or len(fallback_models)>5:
        raise WorkspaceError('Use at most five explicit fallback model names.')
    names=[model,*fallback_models]
    if any(not isinstance(n,str) or not n.strip() or len(n)>300 or any(c.isspace() for c in n.strip()) for n in names):
        raise WorkspaceError('Use nonempty model IDs, without whitespace, at most300 characters each.')
    names=list(dict.fromkeys(n.strip() for n in names))
    with ws._lock:
        view=route_view(ws,name)
        if revision != view['revision']:
            raise WorkspaceError('Instrument settings changed; reload the route before saving.')
        if view['blockers']:
            raise WorkspaceError(' '.join(view['blockers']))
        config=ws.config(); old=config['instruments'][name]
        updated=dict(old,model=names[0],fallback_models=names[1:])
        if updated == old:
            return dict(view,changed=False)
        config['instruments'][name]=updated
        ws.save_config(config)
        ws.ledger.append('instrument.route_changed',{'name':name,'utc':_now(),'before':view['revision'],
            'after':digest(updated),'model':names[0],'fallback_models':names[1:],
            'reason':reason.strip(),'inference_calls':0,'tested':False})
    return dict(route_view(ws,name),changed=True)
