// Work & proposals: judge-accepted fixes, model-written drafts, and every attempt, all waiting for the owner.
import { h, icon, get, post, bus, toast, commentable, openNotes, clear, ago, plural, humanize, diffView, withBusy,
  confirmDialog, askText, drawer, empty, debounce, copyText } from '../core.js';
import { checkProgressLines } from '../check-progress.js';

const TABS = [
  { id: 'proposals', label: 'Fixes', icon: 'check' },
  { id: 'drafts', label: 'Drafts', icon: 'filePlus' },
  { id: 'attempts', label: 'Attempts', icon: 'hammer' },
  { id: 'opportunities', label: 'Last round', icon: 'search' },
  { id: 'memory', label: 'Build memory', icon: 'note' },
];

export default async function render(root, ctx) {
  root.classList.add('work-page');
  const tab = TABS.find((t) => t.id === ctx.sub[0]) || TABS[0];
  const offs = [];
  const head = h('div.page-head', h('div', h('h2', 'Work & proposals'),
    h('p', 'Fixes, model-written drafts, and their check receipts. A draft is not verified until its checks run; project tests and owner acceptance are shown separately. Files are applied by you, or by a checked build under your enabled workspace grant. Every apply has a backup.')),
    h('div.actions', h('button.btn.primary', { onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'round' }); toast('Round queued: map, find work, work, report.', 'good'); }) }, icon('play'), 'Find work now')));
  const tabs = h('div.tabs');
  const body = h('div');
  root.append(head, tabs, body);
  const load = async () => {
    const w = await get('/api/work');
    const counts = { proposals: w.counts.waiting || 0, drafts: w.draft_counts.waiting || 0, attempts: w.recent_sessions.length, opportunities: w.opportunities.length, memory: w.build_memory?.total || 0 };
    clear(tabs).append(...TABS.map((t) => h('button', { class: t.id === tab.id ? 'on' : '', onclick: () => ctx.navigate('work', t.id) }, icon(t.icon), t.label,
      counts[t.id] ? h('span.badge', String(counts[t.id])) : null)));
    clear(body);
    ({ proposals: drawProposals, drafts: drawDrafts, attempts: drawAttempts, opportunities: drawOpportunities, memory: drawMemory })[tab.id](body, w, load, ctx);
  };
  await load();
  offs.push(bus.on('work', debounce(load, 300)), bus.on('round', debounce(load, 300)));
  return () => { offs.forEach((f) => f()); root.classList.remove('work-page'); };
}

const STATE_BADGE = { waiting: ['accent', 'waiting for you'], needs_revision: ['warn', 'needs revision'], applied: ['good', 'applied'], rejected: ['', 'rejected'], undone: ['warn', 'undone'] };

function drawProposals(body, w, reload, ctx) {
  if (!w.proposals.length) {
    body.append(empty('inbox', 'No fixes yet', 'When a round finds failing tests in a code object, Runesmith attempts a repair on a private copy. A held-out judge must accept it before it shows up here.',
      h('button.btn.primary', { onclick: () => post('/api/worker/run', { job: 'round' }).then(() => toast('Round queued', 'good')) }, icon('play'), 'Run a round')));
    return;
  }
  const order = { waiting: 0, applied: 1, undone: 2, rejected: 3 };
  for (const p of w.proposals.slice().sort((a, b) => order[a.state] - order[b.state])) {
    const [cls, label] = STATE_BADGE[p.state] || ['', p.state];
    const actions = h('div.row.wrap');
    if (p.state === 'waiting' || p.state === 'undone' || p.state === 'rejected') actions.append(
      h('button.btn.primary', { onclick: (e) => apply(e.currentTarget, p, reload) }, icon('check'), 'Apply to my files'));
    if (p.state === 'waiting') actions.append(h('button.btn', { onclick: (e) => reject(e.currentTarget, p, reload) }, icon('x'), 'Reject'));
    if (p.state === 'applied') actions.append(h('button.btn', { onclick: (e) => withBusy(e.currentTarget, async () => {
      const r = await post(`/api/proposals/${p.key}/undo`, {});
      r.ok ? toast('Undone: your files are back as they were.', 'good') : toast(`${r.detail}${r.conflicts ? ': ' + r.conflicts.join(', ') : ''}`, 'warn', 8000);
      reload(); }) }, icon('undo'), 'Undo'));
    actions.append(h('button.btn.ghost', { onclick: () => copyText(p.diff) }, icon('copy'), 'Copy patch'), h('button.btn.ghost', { onclick: () => openNotes('proposal', p.key, `fix ${p.key}`) }, icon('note'), 'Comment'));
    const card = h('div.card.mt-16', { class: p.state === 'waiting' ? 'glow' : '' },
      h('div.card-head', h('div.grow', h('h3', icon('check'), `Fix for ${p.object}`), h('div.small.muted', `${plural(p.files.length, 'file')} · ${p.failing_tests.length} failing test(s) now pass · ${p.key}`)),
        h('span.badge.good', icon('shield'), 'judge-accepted'), h('span', { class: `badge ${cls}` }, label)),
      h('div.pillbox.mb-8', p.failing_tests.slice(0, 6).map((t) => h('span.badge.mono', t))),
      diffView(p.diff), p.reason ? h('p.small.muted.mt-8', `Rejected because: ${p.reason}`) : null,
      p.inside ? null : h('div.callout.warn.mt-8', icon('alert'), h('div', 'This fix belongs to a folder outside this workspace; apply it from there with the patch.')),
      h('div.mt-16', actions));
    commentable(card, 'proposal', p.key, `fix ${p.key}`);
    body.append(card);
  }
}
async function apply(btn, p, reload) {
  const ok = await confirmDialog({ title: `Apply this fix to ${p.object}?`, text: `Runesmith writes ${plural(p.files.length, 'file')} (${p.files.join(', ')}) only if they are still exactly as the fix expects. A backup is kept, and Undo restores it.`, confirm: 'Apply', icon: 'check' });
  if (!ok) return;
  await withBusy(btn, async () => {
    const r = await post(`/api/proposals/${p.key}/apply`, {});
    if (r.ok) toast(`Applied to ${r.files.join(', ')}. Undo is one click away.`, 'good', 6000);
    else toast(`${r.detail}${r.conflicts ? ': ' + r.conflicts.join(', ') : ''}`, 'warn', 9000);
    reload();
  });
}
async function reject(btn, p, reload) {
  const reason = await askText({ title: 'Reject this fix', text: 'Optional: say why. Your reason becomes a note that the model reads next time it works on this object.', placeholder: 'e.g. the real problem is in the test, not the source', confirm: 'Reject', multiline: true });
  if (reason === null) return;
  await withBusy(btn, async () => { await post(`/api/proposals/${p.key}/reject`, { reason }); toast('Rejected.', 'good'); reload(); });
}

async function showRevisionContext(draftId, reload) {
  const url = `/api/drafts/${draftId}/revision-context`;
  const data = await get(url);
  drawer({title: 'Focused revision packet', sub: 'Candidate code selection — no new call or check authority', render(body, close) {
    const selected = new Map((data.settings?.enabled ? data.settings.selections : []).map(s => [`${s.path}:${s.unit}`, s]));
    const reason = h('textarea.input', {'aria-label': 'Revision context reason', rows: 2, value: data.settings?.reason || ''});
    const count = h('p.small.muted');
    const refresh = () => {
      const chars = data.units.filter(u => selected.has(`${u.path}:${u.unit}`)).reduce((sum, u) => sum + u.chars, 0);
      clear(count).append(`${selected.size}/${data.max_units} units · ${chars}/${data.code_budget_chars} editable characters. Choose a complete file OR its functions, not both.`);
    };
    const list = h('div', {style: 'max-height:360px;overflow:auto'});
    for (const u of data.units) {
      const key = `${u.path}:${u.unit}`;
      list.append(h('label.row.small.mt-8', h('input', {type: 'checkbox', checked: selected.has(key),
        disabled: u.chars > data.code_budget_chars, onchange: e => {
          e.target.checked ? selected.set(key, {path: u.path, unit: u.unit}) : selected.delete(key); refresh();
        }}), `${u.path} — ${u.label} (${u.chars} chars)`));
    }
    refresh();
    if(data.feedback){
      const delivery=h('details.mt-8',h('summary','Inspect feedback delivery'));
      for(const n of data.feedback.included)delivery.append(h('p.tiny',`Included ${n.id} · ${n.author||'unknown author'} · ${n.target.type}:${n.target.label||n.target.id}`));
      for(const n of data.feedback.omitted)delivery.append(h('p.tiny',`Omitted ${n.id} · ${n.reason}`));
      body.append(h('div.callout',h('div',
        `${data.feedback.enabled?'Feedback on':'Feedback off'} · ${data.feedback.included.length} whole notes included · ${data.feedback.omitted.length} omitted · ${data.feedback.used_chars}/${data.feedback.budget_chars} characters. Latest selected-draft and milestone notes take priority; an oversized required note blocks authoring.`,delivery)));
    }
    body.append(h('p.small', data.scope), h('p.small', 'Only exact edits inside displayed candidate code will be admitted. Other candidate files and functions are retained unchanged. Imports/symbol maps are orientation, not a complete dependency graph. Expand context if the fix needs more.'),
      data.blockers.length ? h('div.callout.warn', data.blockers.join(' ')) : null,
      data.settings_error ? h('div.callout.warn', data.settings_error) : null, count, list,
      h('label.field.mt-16', h('span', 'Why this scope?'), reason));
    if (data.preview) {
      body.append(h('p.small', `Full packet: ${data.preview.broad_prompt_bytes} bytes. Saved focused packet: ${data.preview.focused_prompt_bytes ?? 'not selected'} bytes. These are serialized UTF-8 bytes, not tokens.`));
      if (data.preview.prompt) body.append(h('details.mt-8', h('summary', 'Exact saved author packet preview'),
        h('textarea.input.mono', {readOnly: true, rows: 12, value: data.preview.prompt, 'aria-label': 'Focused author packet preview'})));
    }
    const save = async enabled => {
      if (!reason.value.trim()) {toast('Explain the context selection.', 'warn'); return;}
      await post(url, {version: data.version, selections: [...selected.values()], reason: reason.value, enabled});
      close(); await reload(); toast('Context saved. No inference, retry, verification or apply was authorized.', 'good');
      await showRevisionContext(draftId, reload);
    };
    body.append(h('div.row.mt-16.wrap',
      h('button.btn.primary', {disabled: data.blockers.length > 0, onclick: e => withBusy(e.currentTarget, () => save(true))}, 'Save focused packet without a call'),
      h('button.btn', {disabled: data.blockers.length > 0 || !data.settings?.enabled, onclick: e => withBusy(e.currentTarget, () => save(false))}, 'Use full revision packet')));
  }});
}

function drawDrafts(body, w, reload, ctx) {
  const baseline = w.source_baseline;
  if (baseline) {
    const last = baseline.last;
    const card = h('div.card.mt-8', h('h3', 'Current-source timing diagnostic'),
      h('p.small', baseline.coverage),
      h('p.tiny.muted', `One measurement per source snapshot · ${baseline.timeout_s}s ceiling · no model call, candidate evaluation or apply.`),
      h('button.btn.sm', {disabled: !baseline.enabled || Boolean(baseline.pending), onclick: (e) => withBusy(e.currentTarget, async () => {
        const reason = await askText({title: 'Measure current source only',
          text: 'Run the complete current project suite in a disposable copy, once per source snapshot, for up to 240 seconds. Pending draft changes and owner acceptance are not evaluated. A timeout remains inconclusive.',
          confirm: 'Measure current source'});
        if (!reason?.trim()) return;
        await post('/api/worker/run', {job: 'source_baseline', params: {reason}});
        toast('Source-only measurement queued. Existing candidate verdicts and budgets stay unchanged.'); reload();
      })}, icon('clock'), 'Measure current source'));
    if (baseline.pending) card.append(h('p.small', `Measurement ${baseline.pending.state}: no second run until completion or reconciliation.`));
    if (last) card.append(h('p.small', `Last measurement: ${last.state} · ${last.outcome || 'outcome pending'}`),
      last.source_still_current === false ? h('p.small', 'Source changed during measurement. These timings describe the frozen snapshot, not the current source.') : null,
      ...checkProgressLines('Current-source project checks', last.project_checks).map(line => h('p.tiny', line)),
      h('p.tiny', last.inventory?.available
        ? `Discovered ${last.inventory.count} tests; inventory ${last.inventory.complete ? 'complete' : 'bounded / partially displayed'}.`
        : 'Discovery inventory not yet available.'),
      h('p.tiny.mono', `Source: ${last.snapshot_digest} · Evidence: ${last.evidence_dir}`));
    body.append(card);
  }
  for (const request of (w.pending_authors || [])) {
    body.append(h('div.callout.warn.mt-8',icon('cpu'),h('div.grow',
      h('b','Saved author request'),
      h('div.small',`${request.instrument} · ${request.state} · ${request.job_id || 'ticket not received'}`),
      h('div.tiny',request.can_resume
        ? 'Retrieve the same gateway job. No new model call; a recovered draft still needs its normal checks.'
        : 'The submission outcome is unknown. Automatic resubmission is blocked; reconcile with the gateway first.')),
      h('button.btn.sm',{disabled:!request.can_resume,onclick:(e)=>withBusy(e.currentTarget,async()=>{
        await post('/api/worker/run',{job:'resume_author',params:{request_id:request.id}});
        toast('Saved-job retrieval queued. No new inference.');reload();
      })},icon('check'),'Retrieve saved answer')));
  }
  body.append(h('div.callout', icon('info'), h('div', 'Drafts are model-written changes for a milestone. Check receipts below distinguish unverified drafts, project tests and owner acceptance. Read the change before manual application; delegated builds need an enabled grant and passing acceptance.')));
  const allowance = w.build_escalation?.allowance;
  const budget = h('div.col.gap-6', {'aria-label':'Ordinary author allowance'});
  if (allowance?.known) {
    budget.append(h('b', `${w.build_escalation.milestone} · ${allowance.used} of ${allowance.limit} ordinary attempts used · ${allowance.remaining} remaining`),
      h('div.small.muted', 'Counted across the same milestone and frozen source, including older receipts. Feedback, focused packets and model changes do not refill it. Answered and failed reservations count, even if no model call was sent.'));
    if (allowance.reuse_draft) budget.append(h('div.small', `Matching saved draft ${allowance.reuse_draft} can be reused without another author call.`));
  } else budget.append(h('b', w.build_escalation ? 'Author allowance needs reconciliation' : 'No ready milestone'),
    h('div.small.muted', w.build_escalation ? 'Unknown is not unused. No new author call is offered until the saved records can be checked.' : 'Review Goals & plan to see completed work, dependencies and the next intended milestone.'));
  for (const reason of allowance?.blockers || []) budget.append(h('div.small.warn-text', reason));
  if (w.build_escalation?.used === true) budget.append(h('div.small', 'The separate alternate-author continuation is already recorded; it is not offered again on this source.'));
  budget.append(h('div.tiny.faint', 'Status at last refresh. Execution rechecks current inputs and enabled modes; this is not a provider credit balance.'));
  body.append(h('div.card.mt-8', h('h3', 'Separate authoring from checks'),
    h('p.small', 'Use the configured plan author for the next ready milestone under its ordinary attempt budget. A matching waiting draft is reused. No checks, file application or follow-on job; automatic-work settings stay unchanged.'),
    budget,
    h('div.row.wrap.mt-8', h('button.btn.sm', {disabled:!allowance?.can_draft, onclick: e => withBusy(e.currentTarget, async () => {
      const ok = await confirmDialog({title: 'Draft next milestone only',
        text: 'This may make a model call using the configured plan author and gateway fallbacks. Existing attempt limits apply, with no host retry. Provider costs and gateway attempts depend on your route. No checks, apply or automatic follow-on job. This does not pause an already enabled schedule.',
        confirm: 'Queue draft only'});
      if (!ok) return;
      await post('/api/worker/run', {job:'build', params:{author_only:true}});
      toast('Draft-only job queued. Review its receipt before authorizing checks.'); reload();
    })}, icon('cpu'), 'Draft next milestone only'),
    h('button.btn.sm.ghost', {onclick: e => withBusy(e.currentTarget, reload)}, icon('refresh'), 'Refresh allowance'),
    h('button.btn.sm.ghost', {onclick: () => ctx.navigate('goals')}, icon('target'), 'Review goals'))));
  if (w.build_escalation?.eligible) {
    const e = w.build_escalation;
    body.append(h('div.callout.accent.mt-8', icon('cpu'), h('div.grow',
      h('b', `Alternate author available for ${e.milestone}`),
      h('div.small', e.reason),
      h('div.tiny.muted', 'One separately receipted call · unchanged source, scope, milestone and owner acceptance · no repeat on this snapshot')),
      h('button.btn.sm.primary', {onclick:(event)=>withBusy(event.currentTarget,async()=>{
        const ok=await confirmDialog({title:'Use the one alternate-author continuation?',
          text:'The ordinary three-attempt cap remains closed. This asks the configured planning author once, then runs the same project and owner gates.',confirm:'Use alternate author'});
        if (!ok) return;
        await post('/api/worker/run',{job:'escalate'});
        toast('Alternate-author continuation queued.','good',6000);
      })},icon('cpu'),'Use alternate author')));
  }
  for (const c of (w.build_corrections || []).filter(c => c.remaining > 0)) {
    body.append(h('div.callout.warn.mt-8', icon('wrench'), h('div.grow',
      h('b', `Rejected answer can be corrected: ${c.path}`),
      h('div.small', c.error || 'The answer did not pass host admission.'),
      h('div.tiny.muted', `${c.remaining} of 2 bounded correction continuation(s) remain · same paths, source snapshot, milestone and acceptance gates`)),
      h('button.btn.sm', {disabled:!c.eligible, onclick:(e)=>withBusy(e.currentTarget,async()=>{
        const ok=await confirmDialog({title:'Correct this retained answer?',
          text:'This makes one model call with the exact refusal and frozen source. It cannot add paths or bypass project tests and owner acceptance.',confirm:'Run correction'});
        if (!ok) return;
        await post('/api/worker/run',{job:'correct',params:{attempt:c.attempt}});
        toast('Bounded correction queued. The original answer remains unchanged.','good',6000);
      })},icon('wrench'),'Correct retained answer')));
  }
  if (!w.drafts.length) {
    body.append(empty('filePlus', 'No drafts yet', 'Open Goals & plan, pick a milestone and choose “Draft first files”.', h('button.btn.primary', { onclick: () => ctx.navigate('goals') }, icon('wand'), 'Goals & plan')));
    return;
  }
  for (const d of w.drafts) {
    const [cls, label] = STATE_BADGE[d.state] || ['', d.state];
    const files = h('div.col.gap-6');
    for (const f of d.files) {
      const edit = 'base' in f;
      const pre = edit ? diffView(f.diff || '') : h('pre.code', f.content);
      const body = h('div.mt-8', { class: edit ? '' : 'hidden' }, pre);
      files.append(h('div.card.flat', { style: { padding: '10px 12px' } },
        h('div.row', icon(edit ? 'pencil' : f.exists_now ? 'alert' : 'filePlus'), h('b.mono.small', f.path),
          edit ? h('span.badge.rune', 'edit') : f.exists_now && d.state !== 'applied' ? h('span.badge.warn', 'exists now') : h('span.badge', 'new'),
          h('span.spacer'), h('span.tiny.faint', edit ? 'changes shown' : `${f.content.length} chars`),
          h('button.btn.sm.ghost', { onclick: () => body.classList.toggle('hidden') }, icon('eye'), edit ? 'Hide' : 'View')),
        f.purpose ? h('div.small.muted.mt-8', f.purpose) : null, body));
    }
    const actions = h('div.row.wrap.mt-16');
    if (d.check_reconciliation?.eligible) {
      const q = d.check_reconciliation.quote;
      actions.append(h('button.btn', {onclick: e => withBusy(e.currentTarget, async () => {
        const reason = await askText({title: 'Reconcile preflight — recheck only',
          text: `One linked replacement for allocation ${q.parent_allocation}. ${q.evidence.detail} Legacy evidence is not instrumented phase proof. Confirm your adjudication below. All project checks (${q.project_timeout_s}s ceiling) and owner checks (${q.owner_timeout_s}s ceiling) run anew. Zero model calls. No automatic apply. Old timeouts and the rejected allocation remain unchanged. A timeout or interruption consumes this replacement; it cannot be repeated.`,
          confirm: 'Reserve one recheck only'});
        if (!reason?.trim()) return;
        await post('/api/worker/run', {job:'reconcile_check', params:{draft_id:d.id, quote_id:q.id, reason}});
        toast('Linked recheck queued. Current inputs and authority will be checked again. Nothing automatically applied.'); reload();
      })}, icon('check'), 'Reconcile preflight · recheck only'));
    }
    if (d.check_allocation?.eligible) {
      const q = d.check_allocation.quote;
      actions.append(h('button.btn', {onclick: (e) => withBusy(e.currentTarget, async () => {
        const reason = await askText({title: 'Reserve a separate verification budget',
          text: `Project ceiling ${q.project_timeout_s}s; owner ceiling ${q.owner_timeout_s}s; maximum ${q.maximum_check_s}s of check execution. Basis: ${q.baseline_elapsed_s}s current-source measurement, equal host-variation allowance, plus ${q.unmeasured_candidate_allowance_s}s for unmeasured additions (rounded up, minimum ${q.minimum_project_s}s); owner time is a separate fixed allowance. All tests run anew. Earlier timeouts and budgets stay spent. One allocation per draft. Passing may apply only under the existing build grant.`,
          confirm: 'Reserve and run once'});
        if (!reason?.trim()) return;
        await post('/api/worker/run', {job: 'allocate_check', params: {draft_id: d.id, quote_id: q.id, reason}});
        toast('Separately budgeted verification queued. No inference or counter reset.'); reload();
      })}, icon('clock'), `Allocate checks: ${q.project_timeout_s}s + ${q.owner_timeout_s}s`));
    }
    if(d.check_resume?.eligible) actions.append(h('button.btn',{
      onclick:(e)=>withBusy(e.currentTarget,async()=>{
        const reason=await askText({title:'One extended check, no model call',
          text:'Grant up to 240 seconds per phase (project and owner checks), once for this saved candidate. Existing author budgets remain spent. Passing may apply only under your existing build grant. A second timeout stays inconclusive.',
          confirm:'Grant one check extension'});
        if(!reason?.trim())return;
        await post('/api/worker/run',{job:'resume_check',params:{draft_id:d.id,reason}});
        toast('One extended check queued. No inference or counter reset.');reload();
      })},icon('check'),'Resume timed-out check once'));
    if(d.requirement_supplement?.eligible) actions.append(h('button.btn',{
      onclick:(e)=>withBusy(e.currentTarget,async()=>{
        const inference=await get('/api/inference');
        const names=inference.instruments.map(i=>i.name);
        const instrument=await askText({title:'One explicitly authorized revision',
          text:`Public requirements changed. Existing attempts remain spent. Choose a configured instrument: ${names.join(', ')}`,
          value:names.includes('free-author')?'free-author':names[0],confirm:'Continue'});
        if(!names.includes(instrument))return;
        const reason=await askText({title:'Reason for one additional call',
          text:'This grants one author call for this milestone, with no automatic retry or escalation. Save the answer for review; checks and apply are separate actions. The selected instrument may have provider fallbacks.',confirm:'Authorize one revision'});
        if(!reason?.trim())return;
        await post('/api/worker/run',{job:'supplement',params:{draft_id:d.id,reason,instrument,author_only:true}});
        toast('One author-only revision queued. No checks or apply; prior attempts retained.');reload();
      })},icon('pencil'),'Revise after clarification'));
    if (d.state === 'needs_revision' && d.milestone) actions.append(h('button.btn', {
      onclick: e => withBusy(e.currentTarget, () => showRevisionContext(d.id, reload))
    }, icon('eye'), 'Revision packet'), h('button.btn', {
      onclick: e => withBusy(e.currentTarget, () => showAuthorRevision(d.id, reload))
    }, icon('pencil'), 'Create one revision draft'));
    if (['waiting', 'needs_revision'].includes(d.state) && d.milestone) actions.append(h('button.btn', {
      onclick: (e) => withBusy(e.currentTarget, async () => {
        const settings = await get('/api/settings');
        if (!settings.build_steps) {        // say why nothing would run, and offer the one switch that makes it run
          const on = await confirmDialog({ title: 'Checking drafts is off in this folder',
            text: 'To check a draft, Runesmith runs its tests (Python unittest) in a throwaway working copy of your folder. That executes the project’s code, so it is off until you choose. You can also change it later in Goals & plan → Build continuation.',
            confirm: 'Turn checking on and check this draft', icon: 'check' });
          if (!on) return;
          await post('/api/settings', { build_steps: true });
        }
        await post('/api/worker/run', {job:'build', params:{draft_id:d.id}});
        toast('Checking this draft now: its tests run in a throwaway copy. No model call and nothing is written. Follow it in Activity.', 'good', 7000);
      })}, icon('check'), 'Recheck saved draft'));
    if (d.state !== 'applied') actions.append(h('button.btn.primary', { onclick: (e) => applyDraft(e.currentTarget, d, reload) }, icon('check'), 'Write these files'));
    if (d.state === 'waiting') actions.append(h('button.btn', { onclick: async (e) => { const reason = await askText({ title: 'Reject this draft', text: 'Optional: say why; the Planner reads it next time.', multiline: true, confirm: 'Reject' }); if (reason === null) return; withBusy(e.currentTarget, async () => { await post(`/api/drafts/${d.id}/reject`, { reason }); reload(); }); } }, icon('x'), 'Reject'));
    if (d.state === 'applied') actions.append(h('button.btn', { onclick: (e) => withBusy(e.currentTarget, async () => { const r = await post(`/api/drafts/${d.id}/undo`, {}); r.ok ? toast('Undone.', 'good') : toast(r.detail, 'warn'); reload(); }) }, icon('undo'), 'Undo'));
    const card = h('div.card.mt-16', { class: d.state === 'waiting' ? 'glow' : '' },
      h('div.card-head', h('div.grow', h('h3', icon('filePlus'), d.title), h('div.small.muted', `${plural(d.files.length, 'file')} · by ${d.drafted_by || 'a model'} · ${ago(d.utc)}${d.milestone ? ' · milestone ' + d.milestone : ''}`)),
        h('span', {class:`badge ${d.verified ? 'good' : 'warn'}`, title: d.verification?.status || 'unverified'}, checkBadge(d)), h('span', { class: `badge ${cls}` }, label)),
      d.review_reason || d.review_note || d.review_requested_by ? h('div.callout.warn.mt-8', h('div',
        h('b.small', 'Recorded review feedback — separate from check status'),
        h('p.small', d.review_reason || 'Review feedback is recorded in this draft’s notes.'),
        h('p.tiny.muted', `Reviewer: ${d.review_requested_by || 'not recorded'}. This is not a full test receipt or owner acceptance; later check status is shown separately.`),
        h('button.btn.sm', {onclick: () => openNotes('draft', d.id, d.title)}, icon('note'), 'Open review notes'))) : null,
      d.verification ? h('div.callout.mt-8', h('div', d.verification.detail || d.verification.scope || d.verification.status,
        d.verification.status==='inconclusive' || d.verification.project_checks?.status==='timeout' || d.verification.acceptance?.status==='timeout'
          ? h('p.small', 'Verification did not finish. This is not a code-defect verdict. Retain the candidate and explicitly recheck it without another model call; automatic rebuilding is paused.') : null,
        h('div.tiny', `Project checks: ${d.verification.project_checks?.status || 'not run'}; completed count: ${d.verification.project_checks?.ran ?? 'unknown'}; owner acceptance: ${d.verification.acceptance?.status || 'not run'}`),
        d.verification.author_context?.binding === 'frozen_shown_files' ? h('div.tiny',
          `Author input verified against ${d.verification.author_context.file_count} originally shown files${d.verification.author_context.current_packet_differs ? '; current packet selection differs, not the frozen source' : ''}. Full source snapshot is checked separately.`) : null,
        d.verification.author_context?.binding === 'frozen_source_bindings' ? h('div.tiny',
          'Full source bindings verified separately from the focused candidate units shown to the author. This is not a claim that all bound files were shown.') : null,
        d.author_context_preflight ? h('div.callout.mt-8',
          h('b.small', 'Current author/source identity — diagnostic only'),
          h('p.tiny', d.author_context_preflight.detail),
          d.author_context_preflight.current_packet_differs ? h('p.tiny', 'Today’s packet selection differs from the retained author input. Original inputs, check history and budgets have not been rewritten.') : null) : null,
        d.public_feedback?.public_failures?.length ? h('div.small.mt-8',d.public_feedback.public_failures.map(f=>
          h('p',f.expectations?.length?f.expectations.join('; '):f.diagnosis))) : null,
        d.verification.project_checks?.elapsed_s != null ? h('div.tiny', `Project check time: ${d.verification.project_checks.elapsed_s}s / ${d.verification.project_checks.limit_s}s limit`) : null,
        h('details.mt-8', h('summary.small', 'Test progress and timings'),
          ...checkProgressLines('Project checks', d.verification.project_checks).map(line => h('p.tiny', line)),
          ...checkProgressLines('Owner acceptance', d.verification.acceptance).map(line => h('p.tiny', line))),
        d.verification.evidence_dir ? h('div.tiny.mono', `Evidence: ${d.verification.evidence_dir}`) : null,
        d.check_resume?.used ? h('div.tiny', `One-time check continuation: ${d.check_resume.receipt?.state}; ${d.check_resume.receipt?.outcome || 'not adjudicated'}. No second extension is automatically available.`) : null,
        d.check_allocation?.used ? h('div.tiny', `Separate resource allocation: ${d.check_allocation.receipt?.state}; ${d.check_allocation.receipt?.outcome || 'not adjudicated'}. Prior check receipts stay unchanged; no repeat of this allocation.`) : null,
        d.check_reconciliation?.eligible ? h('div.callout.mt-8', h('div',
          h('b.small', 'Preflight recovery available — not a passing verification'),
          h('p.tiny', d.check_reconciliation.quote.evidence.detail),
          h('p.tiny.mono', `Original allocation: ${d.check_reconciliation.quote.parent_allocation}`),
          h('p.tiny', `One recheck-only replacement: project ${d.check_reconciliation.quote.project_timeout_s}s + owner ${d.check_reconciliation.quote.owner_timeout_s}s. Prior outcomes retained. Review separately before applying.`))) : null,
        d.check_reconciliation?.used ? h('div.callout.mt-8', h('div',
          h('b.small', 'Linked preflight recovery is consumed'),
          h('p.tiny', `${d.check_reconciliation.receipt?.state}; ${d.check_reconciliation.receipt?.outcome || 'unknown'}. No automatic replay, extension or apply.`),
          d.check_reconciliation.receipt?.detail ? h('p.tiny', d.check_reconciliation.receipt.detail) : null)) : null,
        d.verification.snapshot_digest ? h('div.tiny',
          `Local verification: ${d.verification.verification_input_files} files · ${d.verification.snapshot_policy?.profile || 'recorded profile'}; model saw ${d.shown_files?.length ?? 'unknown'} files`) : null,
        d.verification.candidate_digest ? h('div.tiny.mono', `Checked candidate: ${d.verification.candidate_digest}`) : null,
        d.verification.project_checks?.failure_details?.length ? h('details.mt-8',
          h('summary.small', 'Failed checks'), h('pre.code', d.verification.project_checks.failure_details.map(
            f=>`${f.test}\n${f.trace_tail}`).join('\n\n')),
          d.verification.project_checks.failure_details_omitted ? h('p.tiny.faint',
            `${d.verification.project_checks.failure_details_omitted} more failures; full output is in the evidence folder.`) : null) : null,
        h('details.mt-8', h('summary.small', 'Check output'), h('pre.code',
          [d.verification.detail, d.verification.project_checks?.output, d.verification.acceptance?.output].filter(Boolean).join('\n\n') || 'No executable check output.')),
        d.applied_by ? h('div.tiny', `Applied by ${d.applied_by} · grant ${d.grant || 'owner'}`) : null)) : null,
      d.memory_ids?.length ? h('details.mt-8', h('summary.small', `${d.memory_ids.length} historical build observation(s) in the author packet`),
        h('p.tiny.mono', d.memory_ids.join(', ')), h('p.tiny.mono', d.memory_exposure || ''),
        h('p.tiny.muted', 'Included context, not proof that the model used it or improved because of it.')) : null,
      d.why ? h('p.muted', d.why) : null, files, d.refused?.length ? h('p.small.faint', `Refused paths: ${d.refused.join(', ')}`) : null, actions);
    commentable(card, 'draft', d.id, d.title);
    body.append(card);
  }
}

async function showAuthorRevision(draftId, reload) {
  const url = `/api/drafts/${draftId}/revision-request`;
  let data = await get(url);
  // Kept for the lifetime of this dialog. A failed response is never retried
  // automatically under a fresh operation ID.
  const operationId = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
  let submitted = false, loading = false, closed = false;
  drawer({title: 'Create one revision draft', sub: 'Existing allowance · author only · no checks or apply', render(body, close) {
    const author = h('select.input', {'aria-label': 'Revision author'});
    for (const row of data.instruments) author.append(h('option', {value: row.name}, `${row.name} · ${row.model || row.kind}`));
    author.value = data.instrument || '';
    const reason = h('textarea.input', {'aria-label': 'Revision authorization reason', rows: 3, maxLength: 2000, style: 'min-height:88px',
      placeholder: 'Why authorize this one attempt? Record defect and retained behavior in the draft notes first.'});
    const detail = h('div'), outcome = h('div', {'aria-live': 'polite'});
    const submit = h('button.btn.primary', {onclick: async () => {
      if (submitted || loading || !data.eligible) return;
      if (!reason.value.trim()) {toast('Give a reason for this one attempt.', 'warn'); reason.focus(); return;}
      submitted = true; update();
      try {
        const queued = await post('/api/worker/run', {job: 'revise', params: {draft_id: draftId,
          quote_id: data.quote.id, instrument: data.instrument, operation_id: operationId, reason: reason.value}});
        clear(outcome).append(h('div.callout', `Revision queued${queued.id ? ': ' + queued.id : ''}. Eligibility is checked again at execution. Any admitted draft stays unverified; no checks, apply or automatic continuation.`));
        await reload();
      } catch (error) {
        clear(outcome).append(h('div.callout.warn', `${error.message || error} Nothing will be automatically resubmitted. Inspect job history and saved author requests before considering another action.`));
      }
    }}, 'Queue one author-only revision');
    const update = () => {
      submit.disabled = submitted || loading || !data.eligible;
      author.disabled = submitted || loading;
      reason.disabled = submitted;
      clear(detail).append(h('p.small', data.scope));
      if (data.blockers.length) detail.append(h('div.callout.warn', data.blockers.join(' ')));
      if (data.allowance) detail.append(h('p.small', `${data.allowance.remaining} of ${data.allowance.limit} ordinary attempts remain; ${data.allowance.used} already used. Notes, focused packets and descendant draft IDs do not replenish this allowance.`));
      if (!data.eligible) return;
      detail.append(h('p.small', `Parent: ${data.parent} · ${data.prompt_bytes} packet bytes (not tokens).`));
      if (data.review_reason) detail.append(h('div.callout.warn', `Recorded review: ${data.review_reason}`));
      detail.append(
        h('p.small', `Limit: ${data.limits.host_dispatches} host dispatch, ${data.limits.host_retries} host retries, ${data.limits.max_output_tokens} output tokens; configured timeout ${data.limits.timeout_s ?? 'default'} seconds.`),
        h('p.tiny', `Gateway/provider attempts may differ. Configured fallbacks: ${(data.limits.gateway_fallbacks || []).join(', ') || 'none listed'}. No zero-cost promise; consult the instrument’s provider pricing.`),
        h('p.tiny', `Editable scope: ${(data.selections || []).map(s => `${s.path} · ${s.unit}`).join('; ')}`),
        h('p.tiny', `Included notes: ${(data.feedback_included || []).map(n => `${n.id} (${n.author || 'unknown author'})`).join(', ') || 'none'}. Omitted: ${(data.feedback_omitted || []).length}. Notes are attributed feedback, not hidden acceptance criteria.`));
    };
    author.onchange = () => withBusy(author, async () => {
      loading = true; update();
      try {data = await get(`${url}?instrument=${encodeURIComponent(author.value)}`);}
      catch (error) {data = {...data, eligible: false, blockers: [error.message || String(error)]};}
      finally {loading = false; if (!closed) update();}
    });
    body.append(h('label.field', h('span', 'Author instrument'), author), detail,
      h('button.btn.sm', {onclick: () => {close(); withBusy(null, () => showRevisionContext(draftId, reload));}}, 'Inspect revision packet and notes'),
      h('label.field.mt-16', h('span', 'Reason for this attempt'), reason),
      h('div.row.wrap.mt-16', h('button.btn', {onclick: close}, 'Close'), submit), outcome,
      h('p.tiny.mono', `Operation: ${operationId}`));
    update();
    return () => {closed = true;};
  }});
}

function drawMemory(body, w) {
  const memory = w.build_memory || { total: 0, items: [] };
  body.append(h('div.callout', icon('info'), h('div', 'Persistent observations from candidate checks, not learned rules or current project status. Relevant entries can enter later author packets. Timeouts are incomplete; owner acceptance is not a business outcome.')));
  const working = memory.working_set;
  if (working) {
    const card = h('div.card.mt-16', h('h3', icon('note'), 'Next author memory preview'),
      h('p.small', working.milestone
        ? `${working.milestone.title} · ${working.items.length} / ${working.limit} context slots`
        : 'No ready milestone. Resolve plan prerequisites before choosing the next build.'),
      h('p.tiny.muted', 'Newest active distinct observation per draft; matching milestone first, then related work. Earlier entries remain below. Identical checks are deduplicated, so the latest verification receipt remains authoritative.'),
      h('p.tiny.muted', 'Read-only preview, not proof a model received this context. Saved author-exposure receipts record what was actually sent.'));
    if (working.milestone && !working.items.length) card.append(h('p.small', 'No matching build observations. No unrelated memory is forced into the packet.'));
    for (const row of working.items) {
      const selection = row.selection || {};
      card.append(h('details.mt-8', h('summary',
        `${humanize(row.source?.outcome || 'unknown')} · ${selection.reason === 'same_milestone' ? 'same milestone' : 'related milestone'} · ${row.id}`),
        h('p.tiny', `${selection.earlier_distinct_observations || 0} earlier distinct observation(s) retained in history. This is not the current project verdict.`),
        h('p.tiny.mono', `Draft: ${row.source?.draft || 'unknown'} · observed: ${row.source?.observed_utc || 'not recorded'}`),
        h('pre.code', row.text)));
    }
    body.append(card);
  }
  if (!memory.items.length) {
    body.append(empty('note', 'No build observations yet', 'Build checks will leave source-linked observations here.'));
    return;
  }
  body.append(h('p.small.muted', `Showing ${memory.items.length} of ${memory.total} active observations.`));
  for (const m of memory.items) {
    const s = m.source || {};
    body.append(h('div.card.mt-16', h('div.card-head', h('h3', humanize(s.outcome || 'unknown')),
      h('span.badge', m.kind === 'negative' ? 'failed check' : 'observation')),
      h('p.tiny.mono', `${m.id} · draft ${s.draft || 'unknown'} · milestone ${s.milestone || 'unknown'}`),
      h('p.tiny.muted', `Author: ${s.author || 'not recorded'} · recorded ${ago(m.utc)} · origin: ${s.origin || 'runtime'}`),
      h('pre.code', m.text), h('p.tiny.mono', `Evidence: ${s.evidence_dir || 'no executable receipt'}`)));
  }
}
// Check outcomes in plain words; the raw status stays in the badge's tooltip and the receipts.
function checkBadge(d) {
  const v = d.verification;
  if (!v) return 'unverified';
  return ({ acceptance_passed: 'its tests and your checks passed', self_checks_passed: 'its own tests passed',
    failed: 'checks failed', inconclusive: 'checks did not finish' })[v.status] || humanize(v.status || 'unverified');
}

async function applyDraft(btn, d, reload) {
  const warning = draftWriteWarning(d);
  const selfOnly = !warning && d.verification?.status === 'self_checks_passed';
  const ran = d.verification?.project_checks?.ran;
  const ok = await confirmDialog({ title: warning ? 'Write files despite unresolved checks or review?' : 'Write these files?',
    text: `${warning ? warning + '\n\n' : ''}${selfOnly ? `Its own tests passed${ran ? ` (${ran} ran)` : ''}. You have not added acceptance checks of your own for this milestone, so this rests on the author’s tests. Read the change before writing.\n\n` : ''}${plural(d.files.length, 'file')} will be written into your folder. Anything replaced is backed up, and Undo removes what was added.`,
    confirm: 'Write files', danger: Boolean(warning), icon: 'check' });
  if (!ok) return;
  await withBusy(btn, async () => {
    let r = await post(`/api/drafts/${d.id}/apply`, {});
    if (!r.ok && r.conflicts) {
      const again = await confirmDialog({ title: 'Some files already exist', text: `${r.conflicts.join(', ')} already exist with other content. Replace them? The current versions are backed up and Undo restores them.`, confirm: 'Replace them', danger: true });
      if (again) r = await post(`/api/drafts/${d.id}/apply`, { overwrite: true });
    }
    if (r.ok) toast(`Written: ${r.files.join(', ')}${r.milestone_doing ? '. Its milestone is now in progress.' : ''}`, 'good', 6000);
    else if (r.detail) toast(r.detail, 'warn', 8000);
    if (r.ok && d.milestone && ['self_checks_passed', 'acceptance_passed'].includes(d.verification?.status)) await offerMilestoneDone(d);
    reload();
  });
}

// Checks passing and files written do not finish a milestone by themselves: the owner decides, and is asked here.
async function offerMilestoneDone(d) {
  let milestone;
  try { milestone = ((await get('/api/plan')).plan?.milestones || []).find((m) => m.id === d.milestone); } catch { return; }
  if (!milestone || milestone.status === 'done') return;
  const done = await confirmDialog({ title: `Is “${milestone.title}” done?`,
    text: `The draft’s checks passed and its files are written.${milestone.done_when ? ` The milestone is done when: ${milestone.done_when}` : ''}\n\nMark it done, or keep it in progress if there is more to do. You can change this later in Goals & plan.`,
    confirm: 'Mark done', cancel: 'Keep in progress', icon: 'check' });
  if (!done) return;
  await post(`/api/plan/milestones/${d.milestone}`, { status: 'done' });
  toast(`“${milestone.title}” is done. Build next step in Goals & plan continues with the next milestone.`, 'good', 7000);
}

function draftWriteWarning(d) {
  if (d.verified === true && d.verification?.status === 'acceptance_passed' && !['needs_revision', 'rejected'].includes(d.state)) return '';
  if (d.verification?.status === 'self_checks_passed' && d.verification?.project_checks?.status === 'passed'
      && d.state === 'waiting' && !d.review_reason && !d.review_note && !d.review_requested_by) return '';
  return `Draft state: ${humanize(d.state || 'unknown')}. Verification: ${d.verification?.status || 'not run'}. ` +
    `Project checks: ${d.verification?.project_checks?.status || 'not run'}; owner acceptance: ${d.verification?.acceptance?.status || 'not run'}. ` +
    (d.review_reason ? `Recorded review: ${d.review_reason} ` : '') +
    'Manual writing does not run checks, resolve review feedback, or establish owner acceptance. Cancel to inspect or revise the candidate first.';
}

// How an attempt ended, in plain words (the live log says the same).
const ATTEMPT_WORDS = {
  public_pass: 'A fix passed the tests the model may see; the held-out judge decides next.',
  budget_exhausted: 'No fix the tests accept within the model’s allowed calls.',
  navigation_rejected: 'The model asked to read no usable file.',
  navigation_output_failure: 'The model’s answer was not in the requested form.',
  instrument_subject_failure: 'The model could not be reached, or answered with an error.',
  censored_transport: 'The connection to the model failed, so this attempt does not count.',
  organ_error: 'The repair organ failed; this is recorded so Runesmith can improve it.',
  organ_timeout: 'The repair organ ran out of time.',
};

function drawAttempts(body, w) {
  if (!w.recent_sessions.length) { body.append(empty('hammer', 'No attempts yet', 'Each repair attempt, successful or not, is recorded here with its status and cost.')); return; }
  const statusBadge = (s) => ({ public_pass: 'good', budget_exhausted: 'warn', censored_transport: '', organ_error: 'bad', organ_timeout: 'bad' }[s] || '');
  const table = h('table.table', h('tr', ['Attempt', 'Object', 'Status', 'Judge', 'Calls', 'Time', 'Generation'].map((t) => h('th', t))),
    w.recent_sessions.map((s) => h('tr.click', { onclick: () => drawer({ title: `Attempt ${s.key}`, sub: s.object, render: (b) => {
      b.append(h('div.row.wrap', h('span', { class: `badge ${statusBadge(s.status)}` }, humanize(s.status)), s.strict_success ? h('span.badge.good', 'judge accepted') : s.strict_success === false ? h('span.badge.bad', 'judge rejected') : h('span.badge', 'not judged'),
        s.trial_arm ? h('span.badge.violet', `trial arm: ${s.trial_arm}`) : null),
        ATTEMPT_WORDS[s.status] ? h('p.mt-8', ATTEMPT_WORDS[s.status]) : null,
        s.context_scope ? h('p.callout',s.context_scope) : null,
        h('div.label-text.mt-16', 'The issue as the model saw it'), h('pre.code.mt-8', s.issue || '—'),
        h('button.btn.sm.mt-16', { onclick: () => openNotes('session', s.key, `attempt ${s.key}`) }, icon('note'), 'Comment'));
    } }) }, h('td.mono.small', s.key), h('td', s.object || '—'), h('td', h('span', { class: `badge ${statusBadge(s.status)}`, title: ATTEMPT_WORDS[s.status] || '' }, humanize(s.status))),
      h('td', s.strict_success ? h('span.badge.good', 'accepted') : s.strict_success === false ? h('span.badge.bad', 'rejected') : '—'),
      h('td', String(s.calls)), h('td', s.cycle_seconds != null ? `${Math.round(s.cycle_seconds)} s` : '—'), h('td.mono.small', (s.generation || '').replace('gen-', '')))));
  body.append(h('div.card.pad-0', table));
}

function drawOpportunities(body, w) {
  body.append(h('div.card', h('div.card-head', h('h3', icon('search'), 'Last round'), h('span.badge', w.round_utc ? ago(w.round_utc) : 'never')),
    w.last_round ? h('div.grid.four', [['Outcome', humanize(w.last_round.outcome)], ['Served', w.last_round.served], ['Accepted', w.last_round.accepted], ['Kaizen steps', w.last_round.kaizen_steps]].map(([k, v]) => h('div.kpi', h('div.k', k), h('div.v', { style: { fontSize: '20px' } }, String(v ?? 0)))))
      : h('p.muted', 'No round has run yet.'),
    Object.keys(w.objects || {}).length ? h('div.mt-16', h('div.label-text', 'Code objects'), h('div.list', Object.entries(w.objects).map(([name, status]) =>
      h('div.item', h('div', { class: `ico ${status === 'green' ? 'good' : status === 'failing' ? 'bad' : 'warn'}` }, icon(status === 'green' ? 'check' : 'alert')), h('div.body', h('div.title', name), h('div.meta', humanize(status))))))) : null));
  for (const o of w.opportunities) body.append(h('div.card.mt-16', h('div.card-head', h('h3', icon('hammer'), `${o.object}: ${plural(o.failing_tests.length, 'failing test')}`),
    o.triage ? h('span.badge.warn', 'not fixable by editing source') : null), o.triage ? h('p.small.muted', o.triage.reason) : null, h('pre.code', o.issue)));
}
