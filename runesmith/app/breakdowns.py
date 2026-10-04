"""Evidence-led milestone decomposition, proposed separately from adoption.

The host preserves every existing milestone and its acceptance criterion. A
model proposes small prerequisites, not a replacement goal or a weaker test.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid

from runesmith.app import runesmith_md
from runesmith.app.build_memory import recall_for_milestone, _check_summary
from runesmith.app.acceptance_contracts import expectations, expectation_digest
from runesmith.app.planner import PlannerUnavailable, milestone_contract, source_context
from runesmith.app.snapshots import collect_snapshot
from runesmith.app.workspace import WorkspaceError, _now, _read_json, _write_json
from runesmith.canon import digest

SCHEMA = {'type':'object', 'properties':{
    'diagnosis':{'type':'string'}, 'coverage':{'type':'string'},
    'evidence_refs':{'type':'array','items':{'type':'string'}},
    'steps':{'type':'array','minItems':2,'maxItems':4,'items':{'type':'object','properties':{
        'kind':{'type':'string','enum':['build','repair']},
        'title':{'type':'string'}, 'detail':{'type':'string'}, 'done_when':{'type':'string'},
        'suggested_paths':{'type':'array','maxItems':6,'items':{'type':'string'}}},
        'required':['kind','title','detail','done_when','suggested_paths'], 'additionalProperties':False}}
}, 'required':['diagnosis','coverage','evidence_refs','steps'], 'additionalProperties':False}


def proposals(ws):
    rows = [_read_json(p,{}) for p in (ws.home/'breakdowns').glob('*.json')]
    return sorted((r for r in rows if r.get('id')),key=lambda r:r.get('utc',''),reverse=True)[:20]


def _breakdown_depth(plan, milestone_id):
    """Return the number of prerequisite-parent edges above a milestone.

    One nested decomposition is intentionally supported: a broad owner
    milestone may have prerequisites, and one of those prerequisites may be
    split once more.  Deeper trees are refused so replanning cannot turn into
    an unbounded escape from the unchanged success criterion.
    """
    by_id={m.get('id'):m for m in plan.get('milestones',[]) if m.get('id')}
    depth=0;seen=set();current=by_id.get(milestone_id)
    while current and current.get('parent_id'):
        if current['id'] in seen:raise WorkspaceError('Milestone parent cycle detected.')
        seen.add(current['id']);depth+=1;current=by_id.get(current['parent_id'])
    return depth


def can_break_down(plan, milestone_id):
    milestone=next((m for m in plan.get('milestones',[]) if m.get('id')==milestone_id),None)
    if not milestone or milestone.get('status') not in ('open','doing'):
        return False
    has_children=any(m.get('parent_id')==milestone_id for m in plan.get('milestones',[]))
    return not has_children and _breakdown_depth(plan,milestone_id)<2


PLAN_BOUND = 400          # milestones a plan may hold once a breakdown is adopted (it was 30, the most a drafted plan holds)
MAX_STEPS = 4             # a breakdown adds 2 to 4 steps
OUTLINE_FROM = 30         # a plan with more milestones is sent to the model in outline


def room_for_breakdown(plan):
    """Whether the plan can take the longest breakdown. Checked before a model is asked, so a call is never paid for
    whose answer could not be adopted (review of batch EE: J11's plan holds 124 milestones, an owner-built plan the
    old bound of 30 refused every adoption of, by the owner as well as by his setting)."""
    return len((plan or {}).get('milestones', [])) + MAX_STEPS <= PLAN_BOUND


def _plan_outline(plan, parent):
    """The plan as the model is shown it: whole for a small plan; for a big one (J11's is 206 KB of JSON) the parent, its
    prerequisites, its ancestors, its steps and what depends on it in full, and every other milestone by id, title and
    status. The digest the proposal is bound to is the whole plan's."""
    milestones = plan.get('milestones', [])
    if len(milestones) <= OUTLINE_FROM:
        return plan
    by_id = {m['id']: m for m in milestones}
    near = {parent['id'], *(parent.get('depends_on') or [])}
    above = parent.get('parent_id')
    while above in by_id and above not in near:
        near.add(above)
        above = by_id[above].get('parent_id')
    near |= {m['id'] for m in milestones if parent['id'] in (m.get('depends_on') or []) or m.get('parent_id') == parent['id']}
    return dict(plan, milestones=[m if m['id'] in near else {k: m.get(k) for k in ('id', 'title', 'status')} for m in milestones],
                outline='Milestones other than this one, its prerequisites, ancestors, steps and dependents are shown by id, '
                        'title and status only.')


def input_packet(ws, milestone_id):
    plan = ws.plan() or {}
    parent = next((m for m in plan.get('milestones',[]) if m['id']==milestone_id),None)
    if not parent or parent.get('status') not in ('open','doing'):
        raise WorkspaceError('Choose an unfinished milestone to break down.')
    if not room_for_breakdown(plan):
        raise WorkspaceError(f"This plan has {len(plan.get('milestones', []))} milestones and a breakdown adds up to {MAX_STEPS}; "
                             f'a plan holds at most {PLAN_BOUND}. Drop or finish some first.')
    if any(m.get('parent_id')==milestone_id for m in plan.get('milestones',[])):
        raise WorkspaceError('This milestone already has prerequisite steps; review them before another breakdown.')
    if _breakdown_depth(plan,milestone_id)>=2:
        raise WorkspaceError('This prerequisite is already at the maximum breakdown depth; execute or reconsider its parent plan.')
    if not ws.settings()['build_paths']:
        raise WorkspaceError('Choose the allowed build paths before requesting a breakdown.')
    contract = milestone_contract(ws,parent)
    attempts = [_read_json(p,{}) for p in (ws.home/'build-attempts').glob('*.json')]
    attempts = [a for a in attempts if a.get('contract')==contract]
    if any(a.get('state') in ('started','uncertain') for a in attempts):
        raise WorkspaceError('Reconcile interrupted build calls before replanning.')
    snapshot = collect_snapshot(ws)
    failed = []
    for draft in ws.drafts():
        if draft.get('contract')!=contract or not draft.get('verification'):
            continue
        v=draft['verification']
        failed.append({'draft':draft['id'],'status':v.get('status'),'detail':v.get('detail'),
                       'candidate_state':draft.get('state'),
                       'scope':'Historical check of candidate bytes, NOT a fresh measurement of working files.',
                       'candidate_files':[{'path':f['path'],'exists_in_current_source':f['path'] in snapshot['files']}
                                          for f in draft.get('files',[])],
                       'evidence_dir':v.get('evidence_dir'),
                       'project_checks':_check_summary(v.get('project_checks')),
                       'acceptance':_check_summary(v.get('acceptance'))})
    return {
        'task':('Propose 2-4 small, sequential prerequisites for this unfinished milestone. '
                'Use actual failure evidence and current code. Preserve the original goal and completed '
                'behavior; do not replace the parent or weaken its done_when. Avoid a whole-file rewrite '
                'when a small addition suffices. Each step needs a concrete checkable public interface '
                'and at most six suggested code/test paths. Explain uncertainty in your diagnosis and '
                'how the steps cover the parent and its public acceptance criteria. Return planning JSON only, not implementation, test '
                'code, shell commands or changes to existing documentation. This proposes work; it '
                'does not claim success or grant more authority. Evidence refs name supplied fields. '
                'Failed unapplied drafts have NOT changed the working source. Never assume their errors '
                'exist in the current project. A repair step may name only existing files; missing files '
                'can only be proposed as new builds. Prefer complete vertical slices (one useful command '
                'with persistence and tests) over parser stubs or a rewrite of every command at once. Files listed under '
                'files_no_model_can_see cannot be shown to any model, so no step may edit them as they are: a step that '
                'splits such a file into smaller files comes first, and the others build on the pieces.'),
        'parent':parent, 'breakdown_depth':_breakdown_depth(plan,milestone_id),
        'public_acceptance':expectations(ws,milestone_id),
        'ancestor_done_when':[m.get('done_when') for m in plan.get('milestones',[])
                              if m.get('id') in {parent.get('parent_id')} and m.get('done_when')],
        'plan':_plan_outline(plan,parent), 'plan_digest':digest(plan),
        'snapshot_digest':snapshot['digest'], 'brief':ws.brief().get('text',''),
        'allowed_build_paths':ws.settings()['build_paths'],
        'source_context':source_context(ws,limit=20000,snapshot=snapshot),
        'failed_checks':failed[:3],
        # Files no model can be shown (over the limit, not UTF-8): steps that edit them are refused every time (journey
        # J11-B15 review of the 40,000-byte wall), so the steps must split them first.
        'files_no_model_can_see':{p:r for p,r in (source_context(ws,snapshot=snapshot).get('omission_reasons') or {}).items()
                                  if r in ('file_limit','not_utf8')},
        'refusals':[a['error'] for a in attempts[-3:] if a.get('error')],
        'memory_observations':recall_for_milestone(ws,parent),
        'review_feedback':[{'id':r['id'],'reason':r.get('rejection_reason'),'steps':r['steps']}
                           for r in proposals(ws) if r.get('state')=='rejected' and r['milestone']==milestone_id][:2],
    }


def _validate(ws,data,packet):
    if not isinstance(data,dict) or not isinstance(data.get('steps'),list) or not 2<=len(data['steps'])<=4:
        raise WorkspaceError('A breakdown needs 2-4 bounded prerequisite steps.')
    clean={}
    for key,limit in (('diagnosis',2000),('coverage',1500)):
        value=data.get(key)
        if not isinstance(value,str) or not value.strip() or len(value)>limit:
            raise WorkspaceError(f'Breakdown {key} needs nonempty text, at most {limit} characters.')
        clean[key]=value.strip()
    refs=data.get('evidence_refs')
    if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or r not in packet or r=='task' for r in refs):
        raise WorkspaceError('Breakdown evidence references must name supplied fields.')
    clean['evidence_refs']=list(dict.fromkeys(refs)); clean['steps']=[]
    for raw in data['steps']:
        if not isinstance(raw,dict):raise WorkspaceError('Invalid prerequisite step.')
        row={}
        if raw.get('kind') not in ('build','repair'):
            raise WorkspaceError('Each prerequisite must distinguish build from repair.')
        row['kind']=raw['kind']
        for key,limit in (('title',200),('detail',1500),('done_when',400)):
            value=raw.get(key)
            if not isinstance(value,str) or not value.strip() or len(value)>limit:
                raise WorkspaceError(f'Step {key} needs nonempty bounded text.')
            row[key]=value.strip()
        paths=raw.get('suggested_paths')
        if not isinstance(paths,list) or not 1<=len(paths)<=6:
            raise WorkspaceError('Each step needs 1-6 suggested code/test paths.')
        absent=[]
        for path in paths:
            if not isinstance(path,str) or ws._safe_rel(path)!=path or path.lower().endswith(('.md','.rst','.txt')):
                raise WorkspaceError('Step paths must be workspace-relative code/test paths, not documentation.')
            from runesmith.app.building import _within_scope
            if not _within_scope(path, packet['allowed_build_paths']):
                raise WorkspaceError('A prerequisite cannot broaden the existing build-path grant.')
            if path not in packet['source_context']['inventory']:
                absent.append(path)
        if row['kind']=='repair' and absent:
            # A repair is for files that exist now; a failed candidate's files are not the project's (candidate failures are not
            # current-source failures). A step that also names files its milestone creates is a build: the label was the model's
            # slip, and refusing the whole answer cost the one break-down the owner's setting makes, which left a stuck
            # milestone with nothing to try (journey J11-B28: the milestone's own checks name the files it creates).
            row['kind']='build'
            clean.setdefault('corrections',[]).append(
                f"The step “{row['title'][:80]}” was labelled a repair but names files that do not exist yet "
                f"({', '.join(absent[:4])}{' and more' if len(absent)>4 else ''}); it creates them, so it is recorded as a build.")
        row['suggested_paths']=list(dict.fromkeys(paths));clean['steps'].append(row)
    if len({s['title'].casefold() for s in clean['steps']})!=len(clean['steps']):
        raise WorkspaceError('Prerequisite titles must be distinct.')
    return clean


def propose_breakdown(ws,router,milestone_id,*,checkpoint=lambda:None):
    packet=input_packet(ws,milestone_id)
    text=json.dumps(packet,sort_keys=True,ensure_ascii=False)
    packet_digest=hashlib.sha256(text.encode()).hexdigest()
    old=[_read_json(p,{}) for p in (ws.home/'breakdown-attempts').glob('*.json')]
    if any(a.get('state') in ('started','uncertain') for a in old):
        raise PlannerUnavailable('An interrupted breakdown call needs reconciliation before another call.')
    for record in proposals(ws):
        if record.get('input_sha256')==packet_digest and record.get('state')=='proposed':
            return record
    if sum(a.get('input_sha256')==packet_digest and a.get('state')!='transport_failed' for a in old)>=2:
        raise PlannerUnavailable('Two breakdown attempts on unchanged evidence; inspect the saved answers.')
    checkpoint()
    key='b'+uuid.uuid4().hex[:12]
    path=ws.home/'breakdown-attempts'/(key+'.json')
    receipt={'id':key,'state':'started','utc':_now(),'input_sha256':packet_digest,'packet':packet}
    _write_json(path,receipt)
    schema=copy.deepcopy(SCHEMA)
    schema['properties']['evidence_refs']['items']['enum']=[k for k in packet if k!='task']
    try:
        out=router.call('plan',prompt=text,system='You are Runesmith\'s planning instrument. Propose smaller steps from evidence; return JSON only.',
                        schema=schema,max_tokens=4500,key='breakdown-'+key)
    except Exception as error:
        # Turned away by every route, or failed at capacity before generating: nothing ran, so nothing is uncertain and
        # nothing blocks the next breakdown (review of batch EE: one busy moment on a free model left an 'uncertain'
        # receipt that stopped every breakdown in the project until the owner abandoned it). The gateway's receipt is
        # `receipt` on a transport error, `remote_receipt` elsewhere.
        from types import SimpleNamespace
        from runesmith.app.planner import nothing_ran
        remote=getattr(error,'receipt',None) or getattr(error,'remote_receipt',None)
        if nothing_ran(SimpleNamespace(remote_receipt=remote)):
            _write_json(path,{k:v for k,v in dict(receipt,state='transport_failed',finished=_now(),remote_receipt=remote,
                                                  error=type(error).__name__+': '+str(error)[:300]).items() if k!='packet'})
            failure=PlannerUnavailable('Breakdown call did not reach a model; nothing was used up, ask again later.')
            failure.nothing_ran=True
            raise failure from error
        _write_json(path,dict(receipt,state='uncertain',error=type(error).__name__+': '+str(error)[:300]))
        raise PlannerUnavailable('Breakdown call uncertain; inspect its receipt before retrying.') from error
    receipt.update(state='answered',answer=out.data,finished=_now(),instrument={k:out.receipt.get(k) for k in
                    ('model','requested_model','answered_by','job_id','est_usd')})
    _write_json(path,receipt)
    if not out.ok:
        unusable=PlannerUnavailable('Breakdown answer was unusable; receipt retained.');unusable.answered=True
        raise unusable
    checkpoint()
    if input_packet(ws,milestone_id)!=packet:
        changed=WorkspaceError('Breakdown inputs changed; saved answer needs review.');changed.answered=True
        raise changed
    try:clean=_validate(ws,out.data,packet)
    except WorkspaceError as error:
        _write_json(path,dict(receipt,validation_error=str(error)));error.answered=True;raise
    record=dict(clean,id=key,state='proposed',utc=_now(),milestone=milestone_id,
                drafted_by=out.receipt.get('answered_by') or out.receipt.get('model'),
                input_sha256=packet_digest,plan_digest=packet['plan_digest'],snapshot_digest=packet['snapshot_digest'],
                public_acceptance_digest=(packet['public_acceptance'] or {}).get('digest'),
                packet_receipt=path.relative_to(ws.home).as_posix(),parent=packet['parent'])
    _write_json(ws.home/'breakdowns'/(key+'.json'),record)
    ws.ledger.append('breakdown.proposed',{'id':key,'milestone':milestone_id,'author':record['drafted_by']})
    return record


def reject_breakdown(ws,key,reason,*,by='owner'):
    if not re.fullmatch(r'b[0-9a-f]{12}',key):raise WorkspaceError('Invalid breakdown ID.')
    if not isinstance(reason,str) or not reason.strip():raise WorkspaceError('Record why this proposal should be reconsidered.')
    with ws._lock:
        path=ws.home/'breakdowns'/(key+'.json');record=_read_json(path,{})
        if record.get('state')!='proposed':raise WorkspaceError('Only a proposed breakdown can be rejected.')
        _write_json(path,dict(record,state='rejected',rejection_reason=reason[:2000],reviewed_by=by,reviewed_utc=_now()))
        ws.ledger.append('breakdown.rejected',{'id':key,'by':by,'reason':reason[:2000]})
        runesmith_md.split_rejected(ws,record.get('milestone'))
    return {'id':key,'state':'rejected'}


def abandon_uncertain_breakdown(ws,key,reason,*,by='owner'):
    """Explicitly close a transport-uncertain planning receipt after review.

    This is deliberately not automatic: a timeout may hide a completed paid
    call.  A reviewer must record the concrete evidence used to conclude that
    no answer can be recovered before another request is permitted.
    """
    if not re.fullmatch(r'b[0-9a-f]{12}',key):raise WorkspaceError('Invalid breakdown attempt ID.')
    if not isinstance(reason,str) or not reason.strip():
        raise WorkspaceError('Record the evidence used to reconcile this uncertain call.')
    with ws._lock:
        path=ws.home/'breakdown-attempts'/(key+'.json');record=_read_json(path,{})
        if record.get('state')!='uncertain':
            raise WorkspaceError('Only an uncertain breakdown attempt can be abandoned after review.')
        resolved=dict(record,state='abandoned',reconciled_by=by,reconciled_utc=_now(),
                      reconciliation_reason=reason[:2000])
        _write_json(path,resolved)
        ws.ledger.append('breakdown.call_reconciled',{'id':key,'state':'abandoned','by':by,
                         'reason':reason[:2000]})
    return {'id':key,'state':'abandoned'}


def adopt_breakdown(ws,key,*,by='owner'):
    if not re.fullmatch(r'b[0-9a-f]{12}',key):raise WorkspaceError('Invalid breakdown ID.')
    with ws._lock:
        path=ws.home/'breakdowns'/(key+'.json');record=_read_json(path,{})
        if not record:raise WorkspaceError('Breakdown not found.')
        plan=ws.plan() or {}
        # The plan is the atomic commit; reconcile a receipt interrupted after that commit.
        children=[m['id'] for m in plan.get('milestones',[]) if m.get('parent_id')==record['milestone'] and m.get('breakdown_id')==key]
        if children:
            _write_json(path,dict(record,state='adopted',children=children,adopted_by=by))
            return {'id':key,'children':children,'already_adopted':True}
        if record.get('state')!='proposed' or digest(plan)!=record.get('plan_digest'):
            raise WorkspaceError('Plan changed since the proposal; do not adopt stale work.')
        if expectation_digest(ws,record['milestone'])!=record.get('public_acceptance_digest'):
            raise WorkspaceError('Public acceptance changed since the proposal; reassess first.')
        if collect_snapshot(ws)['digest']!=record.get('snapshot_digest'):
            raise WorkspaceError('Source changed since the proposal; reassess first.')
        if len(plan['milestones'])+len(record['steps'])>PLAN_BOUND:
            raise WorkspaceError(f'This breakdown exceeds the current {PLAN_BOUND}-milestone plan bound.')
        parent=next(m for m in plan['milestones'] if m['id']==record['milestone'])
        before=copy.deepcopy(plan);steps=[]
        for i,row in enumerate(record['steps']):
            step_id=f'{key}-s{i+1}'
            dependencies=[steps[-1]['id']] if steps else list(parent.get('depends_on',[]))
            steps.append(dict(row,id=step_id,status='open',track=parent.get('track',''),parent_id=parent['id'],
                              depends_on=dependencies,breakdown_id=key,drafted_by=record['drafted_by']))
        parent['depends_on']=[s['id'] for s in steps]
        parent['decomposed_by']=key
        if not parent.get('parent_id'):
            parent['breakdown_id']=key
        index=plan['milestones'].index(parent);plan['milestones'][index:index]=steps
        plan.update(version=plan.get('version',0)+1,utc=_now())
        _write_json(ws.home/'plans'/f"PLAN-v{before.get('version',0)}.json",before)
        _write_json(ws.home/'PLAN.json',plan)
        children=[s['id'] for s in steps]
        _write_json(path,dict(record,state='adopted',children=children,adopted_by=by,adopted_utc=_now()))
        ws.ledger.append('breakdown.adopted',{'id':key,'children':children,'by':by,'author':record['drafted_by'],
                        'parent_done_when':parent['done_when']})
        runesmith_md.split_adopted(ws,record['milestone'],len(children),by)
        return {'id':key,'children':children,'already_adopted':False}
