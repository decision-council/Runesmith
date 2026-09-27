"""Build-check observations in the existing persistent memory, not learned rules.

Checks, owner acceptance, application and business outcomes are different facts.
This bridge records the first two only. Receipts remain authoritative; lexical
recall supplies historical context and does not prove a later improvement.
"""
from __future__ import annotations

import json
from datetime import datetime

from runesmith.canon import digest
from runesmith.memory import Memory, rank_memories
from runesmith.app.acceptance_contracts import owner_feedback

SOURCE_KIND = 'build_check'
MEMORY_LIMIT = 3
SELECTION_POLICY = 'latest-distinct-per-draft / same-milestone-first / BM25-v1'
SOURCE_FIELDS = ('kind', 'draft', 'milestone', 'author', 'contract', 'snapshot_digest',
                 'candidate_digest', 'outcome', 'evidence_dir', 'observed_utc', 'origin',
                 'feedback_projection')


def _check_summary(check):
    if not isinstance(check, dict):
        return {'status': 'not_run'}
    result = {key: check[key] for key in ('status', 'ran', 'skipped', 'failures', 'errors') if key in check}
    result.setdefault('status', 'unknown')
    details=[]
    for row in check.get('failure_details', [])[:3]:
        if not isinstance(row,dict):continue
        trace=str(row.get('trace_tail',''))
        signals=[]
        for line in trace.splitlines():
            lower=line.casefold()
            if any(word in lower for word in ('assertionerror','argumenterror','invalid choice','unrecognized arguments',
                                               'expected ','actual ','not found','no such','typeerror','valueerror')):
                text=line.strip()
                if text and text not in signals:signals.append(text)
        details.append({'test':str(row.get('test',''))[:200],
                        'salient':'\n'.join(signals[-5:])[:700],
                        'trace_tail':trace[-350:]})
    result['failure_details']=details
    if check.get('detail'):
        result['detail'] = str(check['detail'])[:300]
    return result


def remember_check(ws, draft, verification, *, origin='runtime'):
    """Record once per distinct check observation; callers own the home lock.

    Identical rechecks retain all verification receipts but do not create extra
    retrieval votes. Neither re-import nor a recheck revives a retired memory.
    """
    checks = {name: _check_summary(verification.get(name)) for name in ('project_checks', 'acceptance')}
    checks['acceptance'] = owner_feedback(ws, verification)
    outcome = verification.get('status', 'unknown')
    if any(c['status'] == 'timeout' for c in checks.values()):
        outcome = 'incomplete_timeout'
    elif outcome not in ('failed', 'self_checks_passed', 'acceptance_passed'):
        outcome = 'unknown'
    observation = {
        'draft': draft['id'], 'contract': draft.get('contract'),
        'snapshot_digest': verification.get('snapshot_digest') or draft.get('snapshot_digest'),
        'candidate_digest': verification.get('candidate_digest'),
        'status': verification.get('status', 'unknown'), 'outcome': outcome,
        'detail': str(verification.get('detail', ''))[:400], 'checks': checks,
        'acceptance_bundle': verification.get('acceptance_bundle', {}),
    }
    milestone = next((m for m in (ws.plan() or {}).get('milestones', [])
                      if m.get('id') == draft.get('milestone')), {})
    lines = [f"Build check: {draft.get('title', draft['id'])}",
             f"Milestone: {milestone.get('title', draft.get('milestone'))}",
             'Files: ' + ', '.join(f['path'] for f in draft.get('files', [])),
             f"Observed outcome: {outcome}. This describes a candidate check, not current project state or application."]
    if observation['detail']:
        lines.append(observation['detail'])
    for name, check in checks.items():
        lines.append(name + ': ' + json.dumps(check, ensure_ascii=False))
    source = {key: observation[key] for key in ('draft', 'contract', 'snapshot_digest', 'candidate_digest', 'outcome')}
    source.update(kind=SOURCE_KIND, milestone=draft.get('milestone'), author=draft.get('drafted_by'),
                  evidence_dir=verification.get('evidence_dir'), observed_utc=verification.get('utc'), origin=origin,
                  feedback_projection='public-v1')
    with ws._lock:
        return Memory(ws.home / 'memory.jsonl').add(
            'negative' if outcome == 'failed' else 'episode', '\n'.join(lines)[:2400],
            tags=['build_check', outcome], source=source, dedupe_key='build-check:' + digest(observation))


def _observed_order(row, position):
    """Receipt time, then capture time; append order resolves equal/missing times."""
    for value in (row.get('source', {}).get('observed_utc'), row.get('utc')):
        if not isinstance(value, str):
            continue
        try:
            instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if instant.tzinfo is not None:
                return instant.timestamp(), position
        except (ValueError, OverflowError, OSError):
            pass
    return float('-inf'), position


def _author_observation(row):
    """Project before ranking or exposure; legacy private metadata is not context."""
    source = row.get('source', {})
    text = row['text']
    if source.get('feedback_projection') != 'public-v1':
        # Legacy captures stored each check on a separate JSON-escaped line.
        text = '\n'.join(line for line in text.splitlines()
                         if not line.lstrip().startswith('acceptance:'))
        text += '\nPrivate legacy acceptance details withheld; no public criterion mapping recorded.'
    # Historical extensions must not smuggle private checks through source or tags.
    safe_source = {key: value[:1024] if isinstance(value, str) else None
                   for key in SOURCE_FIELDS if (value := source.get(key)) is not None}
    return dict(row, text=text, source=safe_source, tags=[SOURCE_KIND])


def _select_observations(rows, milestone):
    """Collapse before lexical ranking, so old rechecks cannot crowd out other work."""
    query = ' '.join(str(milestone.get(key) or '') for key in ('title', 'detail', 'done_when'))
    groups = {}
    for position, row in enumerate(rows):
        key = row.get('source', {}).get('draft') or row['id']
        groups.setdefault(key, []).append((_observed_order(row, position), row))
    latest, history_counts = [], {}
    for group in groups.values():
        row = max(group, key=lambda entry: entry[0])[1]
        latest.append(_author_observation(row))
        history_counts[row['id']] = len(group) - 1
    # The selected milestone gets first claim on scarce context slots, but only
    # for observations with lexical overlap. Other milestones can fill the rest.
    same = [row for row in latest if milestone.get('id') and row['source'].get('milestone') == milestone['id']]
    same_ids = {row['id'] for row in same}
    other = [row for row in latest if row['id'] not in same_ids]
    ranked = rank_memories(same, query, MEMORY_LIMIT) + rank_memories(other, query, MEMORY_LIMIT)
    selected = []
    for row in ranked[:MEMORY_LIMIT]:
        selected.append(dict(row, text=row['text'][:1600], selection={
            'policy': SELECTION_POLICY,
            'reason': 'same_milestone' if row['id'] in same_ids else 'related_milestone',
            'earlier_distinct_observations': history_counts[row['id']],
            'caution': 'Historical candidate observation, not current status. Repeated identical checks '
                       'are deduplicated; consult the latest verification receipt for the last check.'}))
    return selected


def recall_for_milestone(ws, milestone):
    """At most three short, public-projected historical observations; no model call."""
    return _select_observations(Memory(ws.home / 'memory.jsonl').active(source_kind=SOURCE_KIND), milestone)


def recent_observations(ws):
    from runesmith.app.planner import next_milestone
    rows = Memory(ws.home / 'memory.jsonl').active(source_kind=SOURCE_KIND)
    milestone = next_milestone(ws.plan())
    working_set = {'policy': SELECTION_POLICY, 'limit': MEMORY_LIMIT,
        'milestone': {key: milestone.get(key) for key in ('id', 'title', 'status')} if milestone else None,
        'items': _select_observations(rows, milestone) if milestone else [],
        'preview_only': True}
    rows.sort(key=lambda row: (row.get('utc', ''), row['id']), reverse=True)
    return {'total': len(rows), 'working_set': working_set,
            'items': [{key: row.get(key) for key in ('id', 'kind', 'text', 'source', 'utc')}
                                       for row in rows[:20]]}
