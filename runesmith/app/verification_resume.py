"""One explicit deadline extension for a retained, time-censored candidate.

No model call, counter reset or new work episode. The caller owns the normal
per-home instance lock, as for other Studio Workspace mutations.
"""
from __future__ import annotations

import hashlib

from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.app.planner import milestone_contract, milestone_ready
from runesmith.app.acceptance_contracts import expectations, expectation_digest
from runesmith.app.snapshots import collect_snapshot, digest_files, SnapshotUnsupported
from runesmith.app import building

RESUME_TIMEOUT_S = 240


def owner_limit(ws, milestone_id):
    """What the owner phase of the extension may take: no less than 240 s, and what an ordinary build gets for a large
    bundle of owner checks (journey J11-B17 review)."""
    try:
        return max(RESUME_TIMEOUT_S, building.owner_check_limit(building._acceptance_files(ws, milestone_id)))
    except (KeyError, TypeError, OSError):
        return RESUME_TIMEOUT_S


def resume_status(ws, draft):
    path=ws.home/'build-check-resumes'/(draft['id']+'.json')
    used=path.exists()
    receipt=_read_json(path,None)
    if used and (not isinstance(receipt,dict) or not receipt.get('id') or not receipt.get('state')):
        receipt={'id':'unresolved-'+draft['id'],'state':'unresolved','outcome':'unknown',
                 'detail':'The existing continuation receipt cannot be validated. No automatic replay.'}
    prior=draft.get('verification') or {}
    limits=[(prior.get(key) or {}).get('limit_s',building.CHECK_TIMEOUT_S)
            for key in ('project_checks','acceptance')
            if (prior.get(key) or {}).get('status')=='timeout']
    shorter=bool(limits) and all(isinstance(v,(int,float)) and v<RESUME_TIMEOUT_S for v in limits)
    return {'eligible':bool(not used and draft.get('state') in ('waiting','needs_revision')
                            and building.verification_inconclusive(prior) and shorter),
            'used':used,'receipt':receipt,'timeout_s':RESUME_TIMEOUT_S,'owner_timeout_s':owner_limit(ws,draft.get('milestone')),
            'max_phases':2,'inference_calls':0}


def resume_verification(ws, draft_id, reason, *, checkpoint=lambda:None):
    if ws.settings()['autonomy']=='observe' or not building.status(ws)['enabled']:
        return {'summary':'Executable checks are off; no continuation, checks or inference.'}
    if not isinstance(reason,str) or not reason.strip():
        raise WorkspaceError('Explain this one-time check-time extension.')
    with ws._lock:
        draft=ws._draft(draft_id)
        path=ws.home/'build-check-resumes'/(draft['id']+'.json')
        current_status=resume_status(ws,draft)
        if current_status['used']:
            return {'summary':'This candidate already has a reserved or completed extended check. Nothing rerun.',
                    'draft':draft['id'],'resume':current_status['receipt']['id'],'already_used':True}
        if not current_status['eligible']:
            raise WorkspaceError('Only an unchanged time-censored candidate may receive this extension.')
        milestone=next((m for m in (ws.plan() or {}).get('milestones',[]) if m['id']==draft.get('milestone')),None)
        if not milestone or not milestone_ready(ws.plan(),milestone):
            raise WorkspaceError('The candidate milestone is no longer ready.')
        contract=milestone_contract(ws,milestone);snapshot=collect_snapshot(ws)
        prior=draft['verification']
        try:
            candidate=building._candidate_files(snapshot,draft)
        except SnapshotUnsupported as error:
            raise WorkspaceError('Candidate source changed; review before continuing.') from error
        candidate_digest=digest_files(candidate,snapshot['policy'].get('declared_documents',[]))['digest']
        current_bundle={}; current_public={}
        for item in ws.plan()['milestones']:
            file=ws.home/'acceptance'/(item['id']+'.py')
            if (item['id']==milestone['id'] or item.get('status')=='done') and file.is_file():
                current_bundle[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
                public=expectations(ws,item['id'])
                if public:current_public[item['id']]=public['digest']
        unchanged=(contract==draft.get('contract') and snapshot['digest']==draft.get('snapshot_digest')
                   and building.author_context_status(ws,draft,snapshot)['ok']
                   and candidate_digest==prior.get('candidate_digest')
                   and expectation_digest(ws,milestone['id'])==draft.get('public_acceptance_digest')
                   and current_public=={c['milestone']:c['digest'] for c in prior.get('public_contracts',[])}
                   and current_bundle==prior.get('acceptance_bundle',{}))
        if not unchanged:
            raise WorkspaceError('Candidate, source or acceptance changed; review new evidence before continuing.')
        checkpoint()
        # An ordinary build gives the owner phase more than 240 s once its bundle is large (journey J11-B17 review): an
        # extension that gave less could time out a bundle the ordinary limit lets finish, and it is used only once.
        owner_s=owner_limit(ws,milestone['id'])
        receipt={'id':'check-'+draft['id'],'draft':draft['id'],'milestone':milestone['id'],
                 'state':'started','utc':_now(),'reason':reason.strip()[:2000],
                 'prior_evidence':prior.get('evidence_dir'),'snapshot_digest':snapshot['digest'],
                 'candidate_digest':candidate_digest,'contract':contract,
                 'public_acceptance_digest':draft.get('public_acceptance_digest'),
                 'acceptance_bundle':prior.get('acceptance_bundle',{}),
                 'timeout_s_per_phase':RESUME_TIMEOUT_S,'owner_timeout_s':owner_s,'max_phases':2,
                 'inference_calls':0,'author_budget_reset':False}
        _write_json(path,receipt)
        ws.ledger.append('build.check_resume_started',receipt)
    try:
        result=building._check_and_record(ws,draft,milestone,contract,checkpoint=checkpoint,
                                         check_timeout_s=RESUME_TIMEOUT_S,owner_timeout_s=receipt['owner_timeout_s'])
    except BaseException as error:
        receipt.update(state='interrupted',finished=_now(),error=type(error).__name__)
        _write_json(path,receipt)
        ws.ledger.append('build.check_resume_interrupted',{'id':receipt['id'],'error':type(error).__name__})
        raise
    verification=result.get('verification') or {}
    receipt.update(state='completed',finished=_now(),outcome=verification.get('status','not_run'),
                   evidence_dir=verification.get('evidence_dir'),advanced=bool(result.get('advanced')),
                   elapsed_check_s=sum((verification.get(k) or {}).get('elapsed_s',0)
                                       for k in ('project_checks','acceptance')))
    _write_json(path,receipt)
    ws.ledger.append('build.check_resume_completed',receipt)
    result['resume']=receipt['id']
    return result
