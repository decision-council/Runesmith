// Work & proposals: judge-accepted fixes, model-written drafts, and every attempt, all waiting for the owner.
import { h, icon, get, post, bus, toast, commentable, openNotes, clear, ago, plural, humanize, diffView, withBusy,
  confirmDialog, askText, drawer, empty, debounce, copyText } from '../core.js';

const TABS = [
  { id: 'proposals', label: 'Fixes', icon: 'check' },
  { id: 'drafts', label: 'Drafts', icon: 'filePlus' },
  { id: 'attempts', label: 'Attempts', icon: 'hammer' },
  { id: 'opportunities', label: 'Last round', icon: 'search' },
];

export default async function render(root, ctx) {
  const tab = TABS.find((t) => t.id === ctx.sub[0]) || TABS[0];
  const offs = [];
  const head = h('div.page-head', h('div', h('h2', 'Work & proposals'),
    h('p', 'Everything Runesmith produced, waiting for your decision. Fixes were accepted by a held-out judge (tests the repair never saw). Drafts were written by a model and are not verified. Nothing is written to your files until you apply it, and every apply can be undone.')),
    h('div.actions', h('button.btn.primary', { onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'round' }); toast('Round queued: map, find work, work, report.', 'good'); }) }, icon('play'), 'Find work now')));
  const tabs = h('div.tabs');
  const body = h('div');
  root.append(head, tabs, body);
  const load = async () => {
    const w = await get('/api/work');
    const counts = { proposals: w.counts.waiting || 0, drafts: w.draft_counts.waiting || 0, attempts: w.recent_sessions.length, opportunities: w.opportunities.length };
    clear(tabs).append(...TABS.map((t) => h('button', { class: t.id === tab.id ? 'on' : '', onclick: () => ctx.navigate('work', t.id) }, icon(t.icon), t.label,
      counts[t.id] ? h('span.badge', String(counts[t.id])) : null)));
    clear(body);
    ({ proposals: drawProposals, drafts: drawDrafts, attempts: drawAttempts, opportunities: drawOpportunities })[tab.id](body, w, load, ctx);
  };
  await load();
  offs.push(bus.on('work', debounce(load, 300)), bus.on('round', debounce(load, 300)));
  return () => offs.forEach((f) => f());
}

const STATE_BADGE = { waiting: ['accent', 'waiting for you'], applied: ['good', 'applied'], rejected: ['', 'rejected'], undone: ['warn', 'undone'] };

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

function drawDrafts(body, w, reload, ctx) {
  body.append(h('div.callout', icon('info'), h('div', 'Drafts are first files written by the Planner model for a milestone of your plan. No test has judged them, so read before you apply. Existing files are never replaced without asking you twice.')));
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
    if (d.state !== 'applied') actions.append(h('button.btn.primary', { onclick: (e) => applyDraft(e.currentTarget, d, reload) }, icon('check'), 'Write these files'));
    if (d.state === 'waiting') actions.append(h('button.btn', { onclick: async (e) => { const reason = await askText({ title: 'Reject this draft', text: 'Optional: say why; the Planner reads it next time.', multiline: true, confirm: 'Reject' }); if (reason === null) return; withBusy(e.currentTarget, async () => { await post(`/api/drafts/${d.id}/reject`, { reason }); reload(); }); } }, icon('x'), 'Reject'));
    if (d.state === 'applied') actions.append(h('button.btn', { onclick: (e) => withBusy(e.currentTarget, async () => { const r = await post(`/api/drafts/${d.id}/undo`, {}); r.ok ? toast('Undone.', 'good') : toast(r.detail, 'warn'); reload(); }) }, icon('undo'), 'Undo'));
    const card = h('div.card.mt-16', { class: d.state === 'waiting' ? 'glow' : '' },
      h('div.card-head', h('div.grow', h('h3', icon('filePlus'), d.title), h('div.small.muted', `${plural(d.files.length, 'file')} · by ${d.drafted_by || 'a model'} · ${ago(d.utc)}${d.milestone ? ' · milestone ' + d.milestone : ''}`)),
        h('span.badge.warn', icon('alert'), 'unverified'), h('span', { class: `badge ${cls}` }, label)),
      d.why ? h('p.muted', d.why) : null, files, d.refused?.length ? h('p.small.faint', `Refused paths: ${d.refused.join(', ')}`) : null, actions);
    commentable(card, 'draft', d.id, d.title);
    body.append(card);
  }
}
async function applyDraft(btn, d, reload) {
  const ok = await confirmDialog({ title: 'Write these files?', text: `${plural(d.files.length, 'file')} will be written into your folder. Anything replaced is backed up, and Undo removes what was added.`, confirm: 'Write files', icon: 'check' });
  if (!ok) return;
  await withBusy(btn, async () => {
    let r = await post(`/api/drafts/${d.id}/apply`, {});
    if (!r.ok && r.conflicts) {
      const again = await confirmDialog({ title: 'Some files already exist', text: `${r.conflicts.join(', ')} already exist with other content. Replace them? The current versions are backed up and Undo restores them.`, confirm: 'Replace them', danger: true });
      if (again) r = await post(`/api/drafts/${d.id}/apply`, { overwrite: true });
    }
    if (r.ok) toast(`Written: ${r.files.join(', ')}${r.milestone_doing ? '. Its milestone is now in progress.' : ''}`, 'good', 6000);
    else if (r.detail) toast(r.detail, 'warn', 8000);
    reload();
  });
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
