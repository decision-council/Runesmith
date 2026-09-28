"""Explicit, bounded continuations for model answers rejected at admission.

The original answer remains immutable.  A correction can replace operation
groups only for paths that answer already named, against the same frozen source
and milestone contract.  Ordinary project and owner checks still decide the
result.  This is representation recovery, not an acceptance bypass.
"""
from __future__ import annotations

import copy
import calendar
import hashlib
import json
import time
import uuid

from runesmith.app.build_memory import _check_summary
from runesmith.app.planner import (DRAFT_SCHEMA, PlannerUnavailable,
                                   admit_revision_answer, milestone_contract,
                                   source_context)
from runesmith.app.snapshots import collect_snapshot, freeze_snapshot
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.instruments import LenientSchema, TransportCensored
from runesmith.app.acceptance_contracts import expectations, expectation_digest, owner_feedback

MAX_CORRECTIONS = 2


def _answers(ws, attempt):
    feedback = attempt.get('feedback') or {}
    named = feedback.get('answer_receipt')
    if named:
        path = ws.home / named
        return [(path, _read_json(path, {}))] if path.is_file() else []
    rows = []
    try:
        started=calendar.timegm(time.strptime(attempt['utc'],'%Y-%m-%dT%H:%M:%SZ'))
        finished=calendar.timegm(time.strptime(attempt.get('finished',attempt['utc']),'%Y-%m-%dT%H:%M:%SZ'))
    except (KeyError,ValueError):
        started=finished=None
    for path in (ws.home / 'draft-answers').glob('*.json'):
        answer = _read_json(path, {})
        if (answer.get('contract') == attempt.get('contract') and
                answer.get('snapshot_digest') == attempt.get('snapshot_digest') and
                (started is None or started-2 <= path.stat().st_mtime <= finished+3)):
            rows.append((path, answer))
    return sorted(rows, key=lambda row: row[0].stat().st_mtime, reverse=True)


def _corrections(ws, attempt_id):
    rows = [_read_json(path,{}) for path in (ws.home/'build-corrections').glob('*.json')]
    # A call no route accepted produced no answer: it neither spends a correction nor blocks one (journey J2-F17).
    return sorted((row for row in rows if row.get('attempt')==attempt_id and row.get('state')!='transport_failed'),
                  key=lambda row:row.get('utc',''))


def correction_candidates(ws):
    current_snapshot = None
    try:
        current_snapshot = collect_snapshot(ws)['digest']
    except Exception:
        pass
    rows=[]
    for path in (ws.home/'build-attempts').glob('*.json'):
        attempt=_read_json(path,{})
        if not isinstance(attempt,dict) or attempt.get('state')!='failed' or not isinstance(attempt.get('feedback'),dict) or not attempt['feedback'].get('path'):
            continue
        answers=_answers(ws,attempt); history=_corrections(ws,path.stem)
        if not answers:continue
        # A correction whose answer never arrived blocks the next one until the owner sets it aside (journey J2-F18).
        late=next((row.get('id') for row in history if row.get('state') in ('started','uncertain')),None)
        # An answer for an earlier source can never be corrected, late correction or not; its card was noise under a
        # later milestone (J2-F21).
        if current_snapshot and attempt.get('snapshot_digest')!=current_snapshot:continue
        rows.append({'attempt':path.stem,'milestone_contract':attempt.get('contract'),
                     'path':attempt['feedback']['path'],'error':attempt.get('error'),
                     'snapshot_current':attempt.get('snapshot_digest')==current_snapshot,
                     'corrections':len(history),'remaining':max(0,MAX_CORRECTIONS-len(history)),
                     'last_state':history[-1].get('state') if history else None,'late_correction':late,
                     'eligible':len(history)<MAX_CORRECTIONS and not late and attempt.get('snapshot_digest')==current_snapshot})
    return sorted(rows,key=lambda row:row['attempt'],reverse=True)


def abandon_uncertain_correction(ws,key,reason,*,by='owner'):
    """Close a correction receipt only after its remote outcome is inspected."""
    if not isinstance(key,str) or not key.startswith('c') or not key[1:].isalnum():
        raise WorkspaceError('Invalid correction ID.')
    if not isinstance(reason,str) or not reason.strip():
        raise WorkspaceError('Record the evidence used to reconcile this uncertain correction.')
    with ws._lock:
        path=ws.home/'build-corrections'/(key+'.json');record=_read_json(path,{})
        if record.get('state') not in ('uncertain','started'):
            raise WorkspaceError('Only a correction whose answer never arrived can be set aside.')
        _write_json(path,dict(record,state='abandoned',reconciled_by=by,reconciled_utc=_now(),
                              reconciliation_reason=reason[:2000]))
        ws.ledger.append('build.correction_reconciled',{'id':key,'state':'abandoned','by':by,
                         'reason':reason[:2000]})
    return {'id':key,'state':'abandoned'}


def _verification(ws, draft):
    value=draft.get('verification') or {}
    return {'draft':draft.get('id'),'status':value.get('status'),
            'detail':str(value.get('detail') or '')[:400],
            'project_checks':_check_summary(value.get('project_checks')),
            'owner_acceptance':owner_feedback(ws, value)}


def correct_rejected_answer(ws, router, attempt_id: str, *, checkpoint=lambda:None):
    attempt_path=ws.home/'build-attempts'/(attempt_id+'.json')
    attempt=_read_json(attempt_path,{})
    if attempt.get('state')!='failed' or not (attempt.get('feedback') or {}).get('path'):
        raise WorkspaceError('Choose a recorded admission refusal with structured feedback.')
    history=_corrections(ws,attempt_id)
    if any(row.get('state') in ('started','uncertain') for row in history):
        raise PlannerUnavailable('The last correction’s answer has not arrived. Set it aside under Work & proposals '
                                 '→ Drafts before asking again.')
    if len(history)>=MAX_CORRECTIONS:
        raise PlannerUnavailable('Two correction continuations were used; replan from the retained evidence.')
    answers=_answers(ws,attempt)
    if not answers:raise WorkspaceError('The rejected answer receipt is unavailable.')
    answer_path,original=answers[0]
    answer=original.get('answer') or {}
    original_files=[row for row in (answer.get('files') or []) if isinstance(row,dict)]
    allowed={ws._safe_rel(str(row.get('path') or '')) for row in original_files}
    if not allowed or any(not path for path in allowed):
        raise WorkspaceError('The rejected answer has no safe correction paths.')
    plan=ws.plan() or {}
    milestone=next((row for row in plan.get('milestones',[])
                    if milestone_contract(ws,row)==attempt.get('contract')),None)
    if not milestone:raise WorkspaceError('The milestone contract changed; correction is stale.')
    snapshot=collect_snapshot(ws)
    if snapshot['digest']!=attempt.get('snapshot_digest'):
        raise WorkspaceError('Source changed since the rejected answer; correction is stale.')
    context=source_context(ws,snapshot=snapshot)
    freeze_snapshot(ws,snapshot)

    previous_draft=None
    for record in reversed(history):
        if record.get('draft'):
            try:previous_draft=ws._draft(record['draft'])
            except KeyError:pass
            if previous_draft:break
    if previous_draft:
        base_files=[{'path':row['path'],'purpose':row.get('purpose',''),'content':row['content']}
                    for row in previous_draft['files']]
        base_title,base_why=previous_draft['title'],previous_draft.get('why','')
    else:
        base_files=copy.deepcopy(original_files)
        base_title,base_why=str(answer.get('title') or milestone['title']),str(answer.get('why') or '')
    if {row.get('path') for row in base_files} != allowed:
        raise WorkspaceError('Correction path custody no longer matches the original answer.')

    recent=[_verification(ws, draft) for draft in ws.drafts()
            if draft.get('contract')==attempt.get('contract') and draft.get('verification')][:3]
    packet={
        'task':('Correct the retained answer without expanding scope. Return operation groups for one or more '
                'of the allowed paths only. Prefer small exact edits. Copy old_text from current_source on the '
                'first correction; on a later correction, exact edits may target candidate_to_correct. '
                'Address every listed owner-acceptance failure relevant to these paths while preserving passing '
                'behavior. The host will retain any candidate path you do not return, rerun admission, all project '
                'tests and owner acceptance, and reject stale or fuzzy edits. If you choose content instead of '
                'edits for an existing path, it MUST be the complete file from first line to last; a fragment is '
                'not content.'),
        'milestone':milestone, 'original_refusal':attempt.get('feedback'),
        'public_acceptance':expectations(ws,milestone['id']),
        'allowed_paths':sorted(allowed),
        'current_source':{path:context['files'].get(path) for path in sorted(allowed)},
        'candidate_to_correct':{'title':base_title,'why':base_why,'files':base_files},
        'recent_verification':recent,
        'limits':{'correction':len(history)+1,'maximum':MAX_CORRECTIONS,
                  'same_snapshot':snapshot['digest'],'same_contract':attempt['contract']},
    }
    item=copy.deepcopy(DRAFT_SCHEMA['properties']['files']['items'])
    for branch in item['anyOf']:
        branch['properties']['path']['enum']=sorted(allowed)
    schema=LenientSchema({'type':'object','properties':{            # code inside: sent as text (see DRAFT_SCHEMA)
        'title':{'type':'string'},'why':{'type':'string'},
        'files':{'type':'array','minItems':1,'maxItems':len(allowed),'items':item},
        },'required':['title','why','files'],'additionalProperties':False})
    key='c'+uuid.uuid4().hex[:12]
    receipt_path=ws.home/'build-corrections'/(key+'.json')
    receipt={'id':key,'attempt':attempt_id,'state':'started','utc':_now(),
             'number':len(history)+1,'original_answer':answer_path.relative_to(ws.home).as_posix(),
             'input_sha256':hashlib.sha256(json.dumps(packet,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
             'packet':packet,'trainer_runtime':'local-correction-v3'}
    _write_json(receipt_path,receipt);checkpoint()
    try:
        outcome=router.call('plan',prompt=json.dumps(packet,ensure_ascii=False),
            system=('You are Runesmith\'s bounded correction instrument. Repair the retained answer representation '
                    'and behavior within its existing paths. Prefer exact edits; content means an entire file, '
                    'never a snippet. Return JSON only.'),
            schema=schema,max_tokens=10000,key='build-correction-'+key)
    except TransportCensored as error:
        if not (getattr(error,'receipt',None) or {}).get('unresolved'):
            from runesmith.app.planner import why_no_answer
            _write_json(receipt_path,dict(receipt,state='transport_failed',error=str(error)[:300],finished=_now()))
            raise PlannerUnavailable(why_no_answer(error)+' Nothing was used up: the correction can be asked again.') from error
        _write_json(receipt_path,dict(receipt,state='uncertain',error=str(error)[:300],finished=_now()))
        raise PlannerUnavailable('The correction’s answer did not arrive in time. Runesmith kept the request and '
                                 'does not pay for it twice; under Work & proposals → Drafts you can set it aside '
                                 'and ask again.') from error
    except Exception as error:
        _write_json(receipt_path,dict(receipt,state='uncertain',error=type(error).__name__+': '+str(error)[:300],finished=_now()))
        raise
    receipt.update(state='answered',finished=_now(),answer=outcome.data,
                   instrument={k:outcome.receipt.get(k) for k in ('model','requested_model','answered_by','job_id','est_usd')})
    _write_json(receipt_path,receipt);checkpoint()
    if not outcome.ok or not isinstance(outcome.data,dict):
        _write_json(receipt_path,dict(receipt,state='refused',error=(outcome.error or 'unusable answer')[:300]))
        raise PlannerUnavailable('Correction answer was unusable; receipt retained.')
    replacements={}
    for row in outcome.data.get('files') or []:
        path=ws._safe_rel(str(row.get('path') or '')) if isinstance(row,dict) else None
        if not path or path not in allowed or path in replacements:
            _write_json(receipt_path,dict(receipt,state='refused',error='Correction changed or duplicated its path set.'))
            raise PlannerUnavailable('Correction changed or duplicated its path set.')
        replacements[path]=row
    if not replacements:raise PlannerUnavailable('Correction returned no permitted operation group.')
    operations=list(replacements.values())
    if not previous_draft:
        admitted=set((attempt.get('feedback') or {}).get('admitted_paths') or []) & allowed
        required=allowed-admitted
        if not required.issubset(replacements):
            _write_json(receipt_path,dict(receipt,state='refused',error='First correction omitted a path that was never admitted.'))
            raise PlannerUnavailable('The first correction omitted an originally rejected path.')
        operations += [copy.deepcopy(row) for row in original_files
                       if row.get('path') in admitted and row.get('path') not in replacements]
    try:
        files=admit_revision_answer(ws,context,operations,previous_draft,
                                    allowed_paths=allowed)
    except PlannerUnavailable as error:
        _write_json(receipt_path,dict(receipt,state='refused',error=str(error)[:300],feedback=getattr(error,'feedback',None)))
        raise
    by=outcome.receipt.get('answered_by') or outcome.receipt.get('model')
    draft=ws.save_draft(title=str(outcome.data.get('title') or base_title),
                        why=str(outcome.data.get('why') or base_why),files=files,
                        drafted_by=by,milestone=milestone['id'])
    ws._save_draft_state(draft,'waiting',contract=attempt['contract'],context_digest=context['digest'],
                         public_acceptance_digest=(packet['public_acceptance'] or {}).get('digest'),
                         snapshot_digest=snapshot['digest'],shown_files=sorted(context['files']),
                         correction_of=attempt_id,correction_receipt=receipt_path.relative_to(ws.home).as_posix(),
                         retained_paths=sorted(allowed-set(replacements)))
    _write_json(receipt_path,dict(receipt,state='candidate',draft=draft['id'],
                                  corrected_paths=sorted(replacements),retained_paths=sorted(allowed-set(replacements))))
    ws.ledger.append('build.correction_candidate',{'id':key,'attempt':attempt_id,'draft':draft['id'],
                     'author':by,'corrected_paths':sorted(replacements),'retained_paths':sorted(allowed-set(replacements))})
    return draft
