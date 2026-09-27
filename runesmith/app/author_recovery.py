"""Retain author packets and recover their answers without a second model call.

The normal per-home writer lock is required, including for the legacy
trainer-attested exception. That exception is not an automatic binding rule.
"""
from __future__ import annotations

import hashlib
import re

from runesmith.canon import digest
from runesmith.app.workspace import WorkspaceError, _read_json, _write_json, _now


def _key(key):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,180}', key):
        raise WorkspaceError('Invalid author request key')
    return key


def acceptance_identity(ws, milestone):
    return {m['id']:hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            for m in (ws.plan() or {}).get('milestones',[])
            if m['id']==milestone or m.get('status')=='done'
            for p in [ws.home/'acceptance'/(m['id']+'.py')]}


def prepare_packet(ws, key, *, milestone, context, contract, public_digest, exposure,
                   revision=None, explicit_revision=False, attempt_id=None, binding='before_submission', revision_view=None,
                   revision_operation=None):
    packet={'request_key':_key(key), 'root':str(ws.root), 'milestone':milestone['id'],
            'contract':contract, 'context_digest':context['digest'], 'snapshot_digest':context['snapshot_digest'],
            'shown_files':sorted(context['files']), 'source_focus_paths':context.get('focus_paths', []),
            'public_acceptance_digest':public_digest, 'acceptance_identity':acceptance_identity(ws,milestone['id']),
            'revision':revision, 'explicit_revision':explicit_revision, 'attempt_id':attempt_id,
            'memory_exposure':exposure, 'binding':binding}
    if revision_operation is not None:
        packet['revision_operation'] = revision_operation
    if revision_view is not None:
        packet.update(revision_view=revision_view, bound_source_files=sorted(context['files']), shown_files=[])
    path=ws.home/'build-author-packets'/(key+'.json')
    if path.exists():
        raise WorkspaceError('Author packet already exists; do not replace its context')
    _write_json(path, {'packet':packet,'digest':digest(packet)})
    return packet


def read_packet(ws, key):
    saved=_read_json(ws.home/'build-author-packets'/(_key(key)+'.json'),{})
    packet=saved.get('packet')
    if not packet or digest(packet)!=saved.get('digest') or packet.get('root')!=str(ws.root):
        raise WorkspaceError('Missing or changed author packet')
    return packet


def admit_packet(ws, packet, data, author, *, receipt=None, admission_guard=None):
    from runesmith.app.planner import (PlannerUnavailable, milestone_contract, milestone_ready,
        source_context, admit_revision_answer, DRAFT_SCHEMA)
    from runesmith.app.acceptance_contracts import expectation_digest
    key=packet['request_key']; answer_digest=digest(data)
    answer_path=ws.home/'draft-answers'/(key+'.json')
    retained=_read_json(answer_path,None)
    if retained and retained.get('answer_digest')!=answer_digest:
        raise WorkspaceError('A different answer is already retained for this request')
    if not retained:
        _write_json(answer_path, {'author':author,'answer':data,'answer_digest':answer_digest,
            'contract':packet['contract'],'context_digest':packet['context_digest'],
            'snapshot_digest':packet['snapshot_digest'],
            'public_acceptance_digest':packet['public_acceptance_digest'],
            'memory_exposure':packet['memory_exposure'],'receipt':receipt})
    existing=next((d for d in ws.drafts() if d.get('author_request_key')==key),None)
    if existing and existing.get('answer_digest')!=answer_digest:
        raise WorkspaceError('Existing draft belongs to a different answer')
    if existing and existing.get('contract'):
        return existing  # idempotent; never recheck, regenerate or reapply here
    if admission_guard is not None:
        admission_guard()  # Retain the answer before honoring a stop or policy change.
    from runesmith.app.author_revisions import validate_admission
    validate_admission(ws, packet)
    milestone=next((m for m in (ws.plan() or {}).get('milestones',[]) if m['id']==packet['milestone']),None)
    if 'shown_files' in packet or 'bound_source_files' in packet:
        from runesmith.app.snapshots import collect_snapshot
        from runesmith.app.source_focus import recorded_context
        context=recorded_context(collect_snapshot(ws),packet.get('bound_source_files', packet.get('shown_files')))
    else:
        context=source_context(ws)
    if (not milestone or not milestone_ready(ws.plan(),milestone)
            or milestone_contract(ws,milestone)!=packet['contract']
            or context['snapshot_digest']!=packet['snapshot_digest'] or context['digest']!=packet['context_digest']
            or expectation_digest(ws,milestone['id'])!=packet['public_acceptance_digest']
            or acceptance_identity(ws,milestone['id'])!=packet['acceptance_identity']):
        raise WorkspaceError('Author source, milestone or acceptance changed; retained answer cannot be admitted')
    if (not isinstance(data,dict) or any(k not in data for k in DRAFT_SCHEMA['required'])
            or not isinstance(data['title'],str) or not isinstance(data['files'],list)):
        raise PlannerUnavailable('Retained answer does not satisfy the draft contract')
    revision=packet.get('revision')
    try:
        raw_files = data['files']
        if packet.get('revision_view') is not None:
            from runesmith.app.revision_context import materialize_answer
            raw_files = materialize_answer(ws, revision, packet['revision_view'], raw_files)
        files=admit_revision_answer(ws,context,raw_files,revision,
            allowed_paths={f['path'] for f in revision['files']} if packet['explicit_revision'] else None)
    except PlannerUnavailable as error:
        error.feedback=dict(getattr(error,'feedback',{}) or {},
                            answer_receipt=answer_path.relative_to(ws.home).as_posix())
        raise
    draft=existing or ws.save_draft(title=data['title'] or milestone['title'],why=str(data.get('why') or ''),
        files=files,drafted_by=author,milestone=milestone['id'],
        author_request_key=key,answer_digest=answer_digest)
    exposure=_read_json(ws.home/packet['memory_exposure'],{})
    visibility = ({'shown_files': [], 'bound_source_files': sorted(context['files']),
                   'revision_view': packet['revision_view']} if packet.get('revision_view') is not None
                  else {'shown_files': sorted(context['files'])})
    ws._save_draft_state(draft,'waiting',contract=packet['contract'],context_digest=context['digest'],
        snapshot_digest=packet['snapshot_digest'],public_acceptance_digest=packet['public_acceptance_digest'],
        **visibility,memory_ids=exposure.get('memory_ids',[]),
        memory_exposure=packet['memory_exposure'],answer_binding=packet['binding'])
    return draft


def pending_authors(ws):
    rows=[]
    admitted={d.get('author_request_key') for d in ws.drafts() if d.get('contract')}
    for path in (ws.home/'inference-requests').glob('*.json'):
        record=_read_json(path,{})
        if record.get('state')=='refused' or (record.get('state')=='terminal'
                and (record.get('payload') or {}).get('state')!='succeeded'):
            continue
        key=re.sub(r'-a\d+$','',record.get('key',''))
        if not key.startswith('draft-') or not (ws.home/'build-author-packets'/(key+'.json')).is_file():
            continue
        recovery=_read_json(ws.home/'author-recoveries'/(record['id']+'.json'),{})
        if recovery.get('state') in ('admitted','rejected','remote_failed'):
            continue
        if key in admitted:
            continue
        if _read_json(ws.home/'author-admissions'/(key+'.json'),{}).get('state')=='rejected':
            continue
        rows.append({'id':record['id'],'key':key,'state':record['state'],
            'job_id':record.get('job_id'),'instrument':record['instrument'],
            'can_resume':bool(record.get('job_id') and record['state']!='binding_mismatch'),'new_inference_calls':0})
    return rows


def resume_author(ws, request_id, *, checkpoint=lambda:None):
    from runesmith.milliner_jobs import read_request
    from runesmith.config import build_instrument
    if ws.settings()['autonomy']=='observe':
        return {'summary':'Observe mode: no answer admission or checks.'}
    checkpoint()
    record=read_request(ws.home/'inference-requests',request_id)
    key=re.sub(r'-a\d+$','',record['key']);packet=read_packet(ws,key)
    exposure=_read_json(ws.home/packet['memory_exposure'],{})
    if hashlib.sha256(record['body'].get('prompt','').encode()).hexdigest()!=exposure.get('prompt_sha256'):
        raise WorkspaceError('Saved gateway request does not match the frozen author prompt')
    path=ws.home/'author-recoveries'/(request_id+'.json')
    prior=_read_json(path,{})
    if prior.get('state') in ('admitted','rejected','remote_failed'):
        _settle_attempt(ws,packet,request_id,'answered' if prior['state']=='admitted' else 'failed',
                        **({'draft':prior['draft']} if prior.get('draft') else {}))
        return {'summary':'Recovery already recorded. No inference, checks or writes repeated.',
                'draft':prior.get('draft'),'already_used':True}
    spec=ws.config()['instruments'].get(record['instrument'])
    if not spec or spec.get('kind')!='milliner':
        raise WorkspaceError('Original configured instrument is unavailable')
    instrument=build_instrument(record['instrument'],spec,ws.home)
    outcome=instrument.resume_request(request_id)
    receipt={'id':request_id,'request_key':key,'utc':_now(),'inference_calls':0,
             'original_attempt':packet.get('attempt_id'),'binding':'direct_ticket',
             'gateway':outcome.receipt}
    if outcome.receipt.get('unresolved'):
        _write_json(path,dict(receipt,state='pending'))
        return {'summary':'Gateway outcome still unresolved. Saved ticket retained; no new model call.'}
    if not outcome.ok:
        _write_json(path,dict(receipt,state='remote_failed',error=outcome.error))
        _settle_attempt(ws,packet,request_id,'failed',error=outcome.error)
        return {'summary':'Saved gateway job failed. Failure retained; no automatic resubmission.'}
    checkpoint()
    author=outcome.receipt.get('model') or record['body'].get('model')
    provider=outcome.receipt.get('provider')
    if provider and author and not author.startswith(provider+':'):author=provider+':'+author
    try:
        draft=admit_packet(ws,packet,outcome.data,author,receipt=outcome.receipt)
    except Exception as error:
        _write_json(path,dict(receipt,state='rejected',error=str(error)[:500],
                             feedback=getattr(error,'feedback',None)))
        _settle_attempt(ws,packet,request_id,'failed',error=str(error)[:500],
                        feedback=getattr(error,'feedback',None))
        raise
    _write_json(path,dict(receipt,state='admitted',draft=draft['id']))
    _settle_attempt(ws,packet,request_id,'answered',draft=draft['id'])
    ws.ledger.append('build.answer_recovered',dict(receipt,draft=draft['id'],author=author))
    # Deliberately only admission. Normal Build/Recheck owns execution/application.
    return {'summary':'Late answer retained as an unverified draft. Check it through the normal build gates; no new inference.',
            'draft':draft['id'],'milestone':packet['milestone']}


def _settle_attempt(ws,packet,request_id,state,**extra):
    attempt_id=packet.get('attempt_id')
    if not attempt_id:return
    if not re.fullmatch(r'[0-9a-f]{32}\.json',attempt_id):
        raise WorkspaceError('Invalid original author attempt reference')
    path=ws.home/'build-attempts'/attempt_id
    original=_read_json(path,{})
    if original.get('contract')!=packet['contract'] or original.get('snapshot_digest')!=packet['snapshot_digest']:
        raise WorkspaceError('Original attempt no longer matches the packet')
    if original.get('reconciled_by')==request_id and original.get('state')==state:
        return
    _write_json(path,dict(original,state=state,prior_receipt=original,
                         reconciled_by=request_id,reconciled_utc=_now(),**extra))
