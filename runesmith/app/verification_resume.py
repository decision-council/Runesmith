"""One explicit deadline extension for a retained, time-censored candidate.

No model call, counter reset or new work episode. The caller owns the normal
per-home instance lock, as for other Studio Workspace mutations.
"""
from __future__ import annotations

import copy
import hashlib

from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.app.planner import milestone_contract, milestone_ready
from runesmith.app.acceptance_contracts import expectations, expectation_digest
from runesmith.app.snapshots import collect_snapshot, digest_files, SnapshotUnsupported
from runesmith.app import building

RESUME_TIMEOUT_S = 240


def owner_limit(ws, milestone_id):
    """What the owner phase of the extension may take: twice what an ordinary build gives that bundle, at most 600 s (never
    less than 240 s, as an ordinary limit is never below 120). The ordinary limit just ran out, and on the same busy
    computer it is likely to run out again: J11's Scatter timed out at 255.2 s against its 254 s limit while a test run
    loaded the machine, and the same bundle takes about 30 s unloaded (journey J11-G44; before, the extension gave the
    owner phase no more than the ordinary limit unless the bundle was small)."""
    try:
        return min(building.OWNER_LIMIT_S, 2 * building.owner_check_limit(building._acceptance_files(ws, milestone_id)))
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
    # The extension gives each phase that timed out more than it had: the project phase 240 s, the owner phase its own
    # (longer) limit, so an owner phase that ran out at the ordinary 254 s can be given 508 s (journey J11-G44).
    given={'project_checks':RESUME_TIMEOUT_S,'acceptance':owner_limit(ws,draft.get('milestone'))}
    limits=[(key,(prior.get(key) or {}).get('limit_s',building.CHECK_TIMEOUT_S))
            for key in ('project_checks','acceptance')
            if (prior.get(key) or {}).get('status')=='timeout']
    shorter=bool(limits) and all(isinstance(v,(int,float)) and not isinstance(v,bool) and v<given[key] for key,v in limits)
    return {'eligible':bool(not used and draft.get('state') in ('waiting','needs_revision')
                            and building.verification_inconclusive(prior) and shorter),
            'used':used,'receipt':receipt,'timeout_s':RESUME_TIMEOUT_S,'owner_timeout_s':owner_limit(ws,draft.get('milestone')),
            'max_phases':2,'inference_calls':0}


def _given_back(ws,draft_id,before,receipt,path):
    """A stop, pause or Studio close during the extension is no verdict: when no phase reached one, the draft's earlier
    verification is put back and the extension is not spent, so it can be asked for again (review of batch EE: a stop
    during a recheck, which can run 18 minutes, used up the draft's only extension and left it inconclusive for good).
    A stop after the checks reached a verdict leaves that verdict and the spent receipt."""
    with ws._lock:
        current=ws._draft(draft_id)
        now=current.get('verification') or {}
        if not (now.get('interrupted_before') or now==before['verification']):
            return False
        if now!=before['verification']:             # the partial record the stop wrote (no phase ran to its end)
            ws._save_draft_state(current,current['state'],**before)
        path.unlink(missing_ok=True)
        ws.ledger.append('build.check_resume_stopped',{'id':receipt['id'],'draft':draft_id,
                         'note':'Stopped before any phase reached a verdict: the extension is not spent.'})
    return True


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
        # The owner phase gets twice the ordinary limit (journey J11-G44), and an ordinary build gives it more than 240 s
        # once its bundle is large (J11-B17 review): it is used only once, so it must not be shorter than either.
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
    before=copy.deepcopy({key:draft.get(key) for key in ('verification','verification_history','check_memory_id','verified')})
    try:
        result=building._check_and_record(ws,draft,milestone,contract,checkpoint=checkpoint,
                                         check_timeout_s=RESUME_TIMEOUT_S,owner_timeout_s=receipt['owner_timeout_s'])
    except BaseException as error:
        if type(error).__name__=='StopRequested' and _given_back(ws,draft['id'],before,receipt,path):
            raise
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
