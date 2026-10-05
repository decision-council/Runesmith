"""Retain author packets and recover their answers without a second model call.

The normal per-home writer lock is required, including for the legacy
trainer-attested exception. That exception is not an automatic binding rule.
"""
from __future__ import annotations

import glob
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
                   revision_operation=None, candidate_view=None, escalation_id=None):
    from runesmith.app.source_focus import recorded_excerpts
    packet={'request_key':_key(key), 'root':str(ws.root), 'milestone':milestone['id'],
            'contract':contract, 'context_digest':context['digest'], 'snapshot_digest':context['snapshot_digest'],
            'shown_files':sorted(context['files']), 'source_focus_paths':context.get('focus_paths', []),
            'public_acceptance_digest':public_digest, 'acceptance_identity':acceptance_identity(ws,milestone['id']),
            'revision':revision, 'explicit_revision':explicit_revision, 'attempt_id':attempt_id,
            'memory_exposure':exposure, 'binding':binding}
    # The parts of files over their limit that this call was shown, and how a revision candidate was shown: a late answer
    # or a correction is judged against these, not today's selection (journey J11-B15). An `excerpts` entry, even an
    # empty one, marks a packet recorded with parts.
    packet['excerpts'] = recorded_excerpts(context)
    if candidate_view:
        packet['candidate_view'] = candidate_view
    if revision_operation is not None:
        packet['revision_operation'] = revision_operation
    if revision_view is not None:
        packet.update(revision_view=revision_view, bound_source_files=sorted(context['files']), shown_files=[])
    if escalation_id is not None:
        # The one more try this call belongs to, so that its late answer settles that receipt (an ordinary try is reached
        # by `attempt_id`). Only when there is one: every other packet keeps the bytes and digest it had.
        packet['escalation_id'] = _escalation_key(escalation_id)
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
        context=recorded_context(collect_snapshot(ws),packet.get('bound_source_files', packet.get('shown_files')),
                                 packet.get('excerpts'))
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
        # The same words as when the answer first came (journey J2-F30: "does not satisfy the draft contract").
        raise PlannerUnavailable("the model's late answer has no title or files, so nothing was saved")
    revision=packet.get('revision')
    try:
        raw_files = data['files']
        materialized = ()
        if packet.get('revision_view') is not None:
            from runesmith.app.revision_context import materialize_answer
            raw_files = materialize_answer(ws, revision, packet['revision_view'], raw_files)
            materialized = {f['path'] for f in raw_files}          # built by the host from the candidate (J11-B15)
        files=admit_revision_answer(ws,context,raw_files,revision,
            allowed_paths={f['path'] for f in revision['files']} if packet['explicit_revision'] else None,
            candidate_view=packet.get('candidate_view'),materialized=materialized)
    except PlannerUnavailable as error:
        error.feedback=dict(getattr(error,'feedback',{}) or {},
                            answer_receipt=answer_path.relative_to(ws.home).as_posix())
        raise
    draft=existing or ws.save_draft(title=data['title'] or milestone['title'],why=str(data.get('why') or ''),
        files=files,drafted_by=author,milestone=milestone['id'],
        author_request_key=key,answer_digest=answer_digest)
    exposure=_read_json(ws.home/packet['memory_exposure'],{})
    from runesmith.app.source_focus import shown_view
    visibility = ({**shown_view(context), 'shown_files': [], 'bound_source_files': sorted(context['files']),
                   'revision_view': packet['revision_view']} if packet.get('revision_view') is not None
                  else shown_view(context))
    ws._save_draft_state(draft,'waiting',contract=packet['contract'],context_digest=context['digest'],
        snapshot_digest=packet['snapshot_digest'],public_acceptance_digest=packet['public_acceptance_digest'],
        **visibility,memory_ids=exposure.get('memory_ids',[]),
        memory_exposure=packet['memory_exposure'],answer_binding=packet['binding'])
    return draft


def answer_packet(ws, answer_rel):
    """The author packet of the call that produced a kept answer (`draft-answers/<request key>.json`), or {} when
    there is none (an answer from before packets, or from a correction)."""
    try:
        return read_packet(ws, str(answer_rel).rsplit('/', 1)[-1].removesuffix('.json'))
    except (WorkspaceError, OSError, ValueError, TypeError):
        return {}


def replay_context(ws, snapshot, excerpts):
    """The selection a kept answer is checked against again with no model call (a newer Runesmith may accept it): today's
    whole files, and the parts its own call was shown, never today's choice of parts (journey J11-B15)."""
    from runesmith.app.planner import source_context
    from runesmith.app.source_focus import with_recorded_parts
    context = source_context(ws, snapshot=snapshot, parts=False)
    return with_recorded_parts(context, snapshot, excerpts) if excerpts else context


def pending_authors(ws, milestone=None):
    """Late answers still expected. With `milestone`, only those that hold that milestone back: its own, and any
    whose milestone is unknown (journey J11-B6: one milestone's late answer no longer stalls the others)."""
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
        packet=_read_json(ws.home/'build-author-packets'/(key+'.json'),{}).get('packet')
        owner=packet.get('milestone') if isinstance(packet,dict) and isinstance(packet.get('milestone'),str) else None
        if milestone is not None and owner not in (milestone,None):
            continue
        rows.append({'id':record['id'],'key':key,'state':record['state'],'milestone':owner,
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
        _settle_attempt(ws,packet,request_id,'answered' if prior['state']=='admitted' else prior.get('settled') or 'failed',
                        **({'draft':prior['draft']} if prior.get('draft') else {}))
        _settle_escalation_from(ws,packet,request_id,prior)
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
        return {'summary':'The late answer has not arrived yet; Runesmith waits for it and does not ask twice.'}
    if not outcome.ok:
        _write_json(path,dict(receipt,state='remote_failed',error=outcome.error))
        _settle_attempt(ws,packet,request_id,'failed',error=outcome.error)
        # A call no route took up and that cost nothing used no try (the same rule as when it was first made).
        _settle_escalation(ws,packet,request_id,
                           'transport_failed' if outcome.receipt.get('no_route_accepted') or outcome.receipt.get('not_admitted') else 'failed',
                           error=outcome.error)
        # Plain words for the owner (journey J11-F8: "Saved gateway job failed. Failure retained; no automatic
        # resubmission."); the next round asks again under the usual limits.
        return {'summary':'The late answer never came: the model’s job failed, so this try ended without an answer.'}
    checkpoint()
    author=outcome.receipt.get('model') or record['body'].get('model')
    provider=outcome.receipt.get('provider')
    if provider and author and not author.startswith(provider+':'):author=provider+':'+author
    try:
        draft=admit_packet(ws,packet,outcome.data,author,receipt=outcome.receipt)
    except Exception as error:
        from runesmith.app.planner import settled_state
        settled=settled_state(error)          # a file the model was not shown uses up no try (journey J11-B15)
        _write_json(path,dict(receipt,state='rejected',error=str(error)[:500],settled=settled,
                             feedback=getattr(error,'feedback',None)))
        _settle_attempt(ws,packet,request_id,settled,error=str(error)[:500],
                        feedback=getattr(error,'feedback',None))
        _settle_escalation(ws,packet,request_id,settled,error=str(error)[:500],feedback=getattr(error,'feedback',None))
        raise
    _write_json(path,dict(receipt,state='admitted',draft=draft['id']))
    _settle_attempt(ws,packet,request_id,'answered',draft=draft['id'])
    _settle_escalation(ws,packet,request_id,'answered',draft=draft['id'],author=author)
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


# ---- the one more try ----------------------------------------------------------------------------------------------------
# An escalation's receipt is written "started" before its call and settled when the call ends. A restart or a crash in
# between used to leave it started for good: every build of that milestone then ended "Unresolved author allowance
# receipt ...; reconcile it before another call", and nothing told the owner. Its saved answer is retrieved by
# `resume_author` like an ordinary try's (the packet names the receipt); what cannot be retrieved is closed here.

INTERRUPTED = 'interrupted by a restart'


def _escalation_key(key):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', key):
        raise WorkspaceError('Invalid build escalation ID.')
    return key


def _settled(receipt):
    from runesmith.app.author_allowance import ESCALATION_SETTLED, NOTHING_USED
    return receipt.get('state') in ESCALATION_SETTLED or receipt.get('state') in NOTHING_USED


def settle_escalation(ws, key, state, *, by, **extra):
    """Record how a one more try that had no outcome ended. Only a receipt still unresolved is moved: one that is settled
    is never rewritten (an answer that arrives after the owner closed the call, a second pass after a crash). Returns the
    receipt as it stands, or None when there is none."""
    path = ws.home/'build-escalations'/(_escalation_key(key)+'.json')
    with ws._lock:
        receipt = _read_json(path, None)
        if not isinstance(receipt, dict):
            return None
        if _settled(receipt):
            return receipt
        now = _now()
        settled = dict(receipt, state=state, finished=now, reconciled_by=by, reconciled_utc=now,
                       prior_state=receipt.get('state'), **{k: v for k, v in extra.items() if v is not None})
        _write_json(path, settled)
        ws.ledger.append('build.escalation_reconciled', {'id': key, 'milestone': receipt.get('milestone'), 'state': state,
                                                         'by': by, 'draft': extra.get('draft'),
                                                         'error': str(extra.get('error') or '')[:300]})
        return settled


def _settle_escalation(ws, packet, request_id, state, **extra):
    """Where `_settle_attempt` settles an ordinary try, this settles the one more try the packet's call belonged to."""
    if packet.get('escalation_id'):
        settle_escalation(ws, packet['escalation_id'], state, by=request_id, **extra)


def _settle_escalation_from(ws, packet, request_id, record):
    """The same, from an author recovery record kept before (the call's outcome was recorded, its receipt not yet)."""
    if not packet.get('escalation_id'):
        return
    if record.get('state') == 'admitted':
        draft = _read_json(ws.home/'drafts'/str(record.get('draft') or '-')/'DRAFT.json', {})
        _settle_escalation(ws, packet, request_id, 'answered', draft=record.get('draft'), author=draft.get('drafted_by'))
    elif record.get('state') == 'rejected':
        _settle_escalation(ws, packet, request_id, record.get('settled') or 'failed', error=record.get('error'),
                           feedback=record.get('feedback'))
    else:
        gateway = record.get('gateway') if isinstance(record.get('gateway'), dict) else {}
        _settle_escalation(ws, packet, request_id,
                           'transport_failed' if gateway.get('no_route_accepted') or gateway.get('not_admitted') else 'failed',
                           error=record.get('error'))


def _linked_packets(ws, milestone_id, key):
    """The saved author packets whose call was the one more try `key` (newer packets name it; older ones do not)."""
    if not isinstance(milestone_id, str) or not milestone_id:
        return []
    rows = []
    for path in sorted((ws.home/'build-author-packets').glob(glob.escape(f'draft-{milestone_id}-') + '*.json')):
        try:
            packet = read_packet(ws, path.stem)
        except (WorkspaceError, OSError, ValueError, TypeError, KeyError):
            continue
        if packet.get('escalation_id') == key and packet.get('milestone') == milestone_id:
            rows.append(packet)
    return rows


def _kept_outcome(ws, packet):
    """How the call of this packet ended, as far as what is kept says, as (state, fields), or None when nothing says."""
    key = packet['request_key']
    draft = next((d for d in ws.drafts() if d.get('author_request_key') == key and d.get('contract')), None)
    if draft:
        return 'answered', {'draft': draft['id'], 'author': draft.get('drafted_by')}
    for attempt in range(12):
        request_id = hashlib.sha256(f'{key}-a{attempt}'.encode()).hexdigest()
        record = _read_json(ws.home/'author-recoveries'/(request_id+'.json'), {})
        if record.get('state') == 'admitted' and record.get('draft'):
            return 'answered', {'draft': record['draft']}
        if record.get('state') == 'rejected':
            return record.get('settled') or 'failed', {'error': record.get('error'), 'feedback': record.get('feedback')}
        if record.get('state') == 'remote_failed':
            return 'failed', {'error': record.get('error')}
    admission = _read_json(ws.home/'author-admissions'/(key+'.json'), {})
    if admission.get('state') == 'rejected':
        return 'failed', {'error': admission.get('error'), 'feedback': admission.get('feedback')}
    return None


def _release_requests(ws, packet, reason):
    """A saved request of a call that is being closed no longer holds its milestone back, and its answer, if one ever
    comes, is not used (it is recorded as a remote failure, as when the model's job fails)."""
    for row in pending_authors(ws, milestone=packet['milestone']):
        if row['key'] == packet['request_key']:
            _write_json(ws.home/'author-recoveries'/(row['id']+'.json'),
                        {'id': row['id'], 'request_key': row['key'], 'utc': _now(), 'inference_calls': 0,
                         'original_attempt': None, 'binding': 'closed', 'gateway': {}, 'state': 'remote_failed',
                         'error': reason})


def _close(ws, key, linked, *, by, reason):
    """Settle one unresolved receipt from what is kept: its answer if one was kept, else the one more try is used up."""
    outcome = next((found for found in (_kept_outcome(ws, packet) for packet in linked) if found), None)
    state, fields = outcome if outcome else ('failed', {'error': reason})
    if not outcome:
        for packet in linked:
            _release_requests(ws, packet, reason)
    return settle_escalation(ws, key, state, by=by, **fields)


def close_interrupted_escalations(ws, *, contract=None, by='Runesmith'):
    """Settle the one more try receipts a restart or a crash left started, with no call and no gateway request; of this
    milestone contract only when one is given. A call whose saved model job can still be retrieved is left: the next build
    retrieves it (`resume_author` settles the receipt). One whose answer was kept is recorded as answered, or as refused
    with its answer kept. Any other used its one more try: it is recorded as failed, "interrupted by a restart", and
    nothing is sent again by itself. A receipt in a state this does not know stays for the owner (Needs you offers to
    close it). Call it only where no one more try can be running: at start, and in the worker's own job. Returns what it
    settled."""
    from runesmith.app.author_allowance import unresolved_escalations
    closed = []
    for name, receipt in unresolved_escalations(ws, contract):
        if receipt.get('state') != 'started':
            continue
        key, milestone = name.removesuffix('.json'), receipt.get('milestone')
        milestone = milestone if isinstance(milestone, str) and milestone else None
        if any(row['can_resume'] for row in pending_authors(ws, milestone=milestone)):
            continue
        settled = _close(ws, key, _linked_packets(ws, milestone, key), by=by, reason=INTERRUPTED)
        if settled and settled.get('prior_state') == 'started':
            closed.append({'id': key, 'milestone': milestone, 'state': settled['state'], 'draft': settled.get('draft')})
    return closed


def close_interrupted_escalation(ws, key, *, by='owner'):
    """The owner's "Close the interrupted call": the one more try is recorded as used (or as answered, when its answer was
    kept), and a saved request of it is not waited for any more. Nothing is sent."""
    key = _escalation_key(key)
    with ws._lock:
        receipt = _read_json(ws.home/'build-escalations'/(key+'.json'), None)
        if not isinstance(receipt, dict):
            raise WorkspaceError('There is no such one more try to close.')
        if _settled(receipt):
            raise WorkspaceError('That call is already settled; there is nothing to close.')
        milestone = receipt.get('milestone')
        settled = _close(ws, key, _linked_packets(ws, milestone, key), by=by, reason='interrupted; closed by the owner')
    return {'id': key, 'state': settled['state'], 'milestone': milestone}
