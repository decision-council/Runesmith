// Activity: the live log, the hash-chained ledger (everything Runesmith did, provably in order), and jobs.
import { h, icon, get, post, bus, clear, ago, clock, datetime, humanize, empty, debounce, withBusy, toast } from '../core.js';
import {recoveryPanel} from '../worker-recovery.js';

const KIND_ICON = [['proposal', 'check'], ['draft', 'filePlus'], ['generation', 'branch'], ['trial', 'scale'], ['kaizen', 'spark'], ['loop.subject', 'spark'],
  ['loop.object', 'hammer'], ['opportunity', 'search'], ['environment', 'map'], ['instrument', 'cpu'], ['roles', 'layers'], ['note', 'note'], ['goal', 'target'],
  ['milestone', 'flag'], ['plan', 'route'], ['brief', 'book'], ['settings', 'sliders'], ['studio', 'monitor'], ['home', 'home'], ['genesis', 'flame'], ['snapshot', 'download']];
const iconFor = (kind) => (KIND_ICON.find(([p]) => kind.startsWith(p)) || [null, 'activity'])[1];
const toneFor = (kind, data) => (kind.includes('rejected') || data?.ok === false ? 'warn' : kind.includes('applied') || kind.includes('activated') ? 'success' : '');

function describe(e) {
  const d = e.data || {};
  switch (e.kind) {
    case 'loop.object_step': return `Repair attempt ${d.key}: ${humanize(d.status)}${d.strict_success ? ' (judge accepted)' : d.strict_success === false ? ' (judge rejected)' : ''}`;
    case 'loop.subject_step': return `Kaizen step: ${humanize(d.decision)}${d.generation ? ' → ' + d.generation : ''}`;
    case 'proposal.applied': return `You applied fix ${d.key} (${(d.files || []).join(', ')})`;
    case 'proposal.undone': return `You undid fix ${d.key}`;
    case 'proposal.rejected': return `You rejected fix ${d.key}`;
    case 'draft.created': return `Draft written by ${d.drafted_by || 'a model'}: ${(d.files || []).length} file(s)`;
    case 'draft.applied': return `You wrote draft ${d.id} (${(d.files || []).join(', ')})`;
    case 'generation.activated': return `Generation ${d.id} activated${d.evidence ? ' (' + d.evidence + ')' : ''}`;
    case 'generation.imported': return `Generation ${d.imported_from} adopted as ${d.id} (smoke test ${d.smoke})`;
    case 'trial.opened': return `Trial opened: ${d.candidate} vs ${d.incumbent}`;
    case 'trial.rejected': return `Trial closed: ${d.candidate} rejected`;
    case 'trial.closed_by_owner': return `Trial of ${d.candidate} closed by your choice of ${d.active}`;
    case 'manual.skipped': return `You skipped a chat-relay request`;
    case 'environment_map.written': return `Folder mapped: ${d.objects} object(s)${d.probed ? ', tests measured' : ''}`;
    case 'studio.round': return `Round: ${humanize(d.outcome)} · ${d.served} served, ${d.accepted} accepted`;
    case 'instrument.saved': return `Model ${d.name} saved (${d.model || d.kind})${d.key_saved ? ', key stored' : ''}`;
    case 'instrument.tested': return `Model ${d.name} tested: ${d.ok ? 'works' : 'failed'}`;
    case 'note.added': return `Note on ${d.target?.label || d.target?.id}`;
    case 'goal.added': return `Goal added: ${d.text}`;
    case 'plan.saved': return `Plan v${d.version} saved (${d.milestones} milestones, by ${d.drafted_by || 'owner'})`;
    case 'genesis.completed': return `Named “${d.name}”${d.described ? ' with a description' : ''}`;
    case 'settings.changed': return `Settings changed: ${(d.keys || []).join(', ')}`;
    case 'studio.opened': return `Studio opened (version ${d.version})`;
    case 'opportunity.skipped': return `Skipped (environment): ${d.reason}`;
    default: return humanize(e.kind) + (Object.keys(d).length ? ' · ' + JSON.stringify(d).slice(0, 120) : '');
  }
}

export default async function render(root, ctx) {
  const offs = [];
  const tab = ['live', 'ledger', 'jobs'].includes(ctx.sub[0]) ? ctx.sub[0] : 'live';
  const head = h('div.page-head', h('div', h('h2', 'Activity'), h('p', 'The live log shows what Runesmith is doing now. The ledger is its permanent record: every event is hash-chained to the one before, so the history cannot be quietly rewritten.')));
  const tabs = h('div.tabs', [['live', 'Live log', 'activity'], ['ledger', 'Ledger', 'shield'], ['jobs', 'Jobs', 'clock']].map(([id, l, ic]) =>
    h('button', { class: id === tab ? 'on' : '', onclick: () => ctx.navigate('activity', id) }, icon(ic), l)));
  const body = h('div');
  root.append(head, tabs, body);
  if (tab === 'live') {
    const box = h('div.console', { style: { maxHeight: '64vh', minHeight: '320px' } });
    const add = (l) => { box.append(h('div', { class: `l ${l.level || ''}` }, h('time', clock(l.utc)), l.text)); box.scrollTop = 1e9; };
    const w = await get('/api/worker');
    (w.lines || []).forEach(add);
    if (!w.lines?.length) box.append(h('div.l', 'Quiet. Lines appear as Runesmith works.'));
    offs.push(bus.on('log', add));
    let worker = w, changingControl = false;
    const status = h('span.badge', { 'aria-live': 'polite' });
    const queue = h('p.small.muted', { 'aria-live': 'polite' });
    const pause = h('button.btn.sm', { title: 'Pause holds queued work and persists across Studio restart.' });
    const stop = h('button.btn.sm', { title: 'Stop this job at the next checkpoint. Other queued jobs are not paused.' }, icon('stop'), 'Stop current job');
    const recovery = recoveryPanel(s => update(s));
    const update = (s) => {
      worker = s;
      status.textContent = s.recovery ? 'Recovery review required' : s.current ? s.stop_requested ? 'Finishing current step before stopping' :
        s.paused ? 'Paused · finishing current step' : (s.detail || s.status) : s.paused ? 'Paused' : 'Idle';
      status.className = `badge ${s.current ? 'rune' : ''}`;
      queue.textContent = `${(s.queue || []).length} queued · one job at a time in this workspace${s.recovery ? ' · restart review required before Resume' : s.paused ? ' · queue held until Resume' : ''}`;
      pause.replaceChildren(icon(s.paused ? 'play' : 'pause'), s.paused ? 'Resume queue' : 'Pause queue');
      pause.disabled = changingControl || !!s.recovery;
      stop.classList.toggle('hidden', !s.current); stop.disabled = changingControl || !!s.stop_requested;
      recovery.update(s);
    };
    const control = async (button, action) => {
      if (changingControl) return;
      changingControl = true; update(worker);
      try {
        await withBusy(button, async () => {
          await post(`/api/worker/${action}`, {});
          update(await get('/api/worker'));
          if (action === 'stop') toast('This job stops at the next checkpoint. Pause the queue to hold other jobs.', 'good');
        });
      } finally { changingControl = false; update(worker); }
    };
    pause.addEventListener('click', () => control(pause, worker.paused ? 'resume' : 'pause'));
    stop.addEventListener('click', () => control(stop, 'stop'));
    update(w); offs.push(bus.on('worker', update));
    body.append(recovery.root, h('div.card', h('div.card-head', h('h3', icon('activity'), 'Live'), status, h('div.actions', pause, stop)),
      queue, h('p.small.faint', 'Pause and Stop let an active model call or test phase finish within its limit. Build checks recheck controls before owner acceptance and application. Unrun phases are not passes; inspect saved receipts before continuing.'), box));
  } else if (tab === 'ledger') {
    let kinds = '';
    const filterRow = h('div.row.wrap.mb-8');
    const list = h('div.feed');
    const verify = h('button.btn.sm', icon('shield'), 'Verify the chain');
    verify.addEventListener('click', () => withBusy(verify, async () => {
      const r = await get('/api/activity?limit=1&verify=1');
      r.ledger.ok ? toast(`The ledger verifies: ${r.ledger.records} records, every link intact.`, 'good', 6000) : toast(`The ledger does NOT verify: ${r.ledger.error}`, 'bad', 12000);
    }));
    const load = async () => {
      const data = await get(`/api/activity?limit=300${kinds ? '&kinds=' + encodeURIComponent(kinds) : ''}`);
      clear(list);
      if (!data.events.length) list.append(empty('shield', 'Nothing yet', ''));
      for (const e of data.events) {
        const row = h('div', { class: `ev ${toneFor(e.kind, e.data)}` }, h('time', { title: datetime(e.utc) }, `${clock(e.utc)} · #${e.seq}`), h('span.dot', icon(iconFor(e.kind))),
          h('div', h('div', describe(e)), h('div.tiny.faint.mono', e.kind)));
        list.append(row);
      }
    };
    const chips = [['', 'Everything'], ['loop.,proposal.,draft.', 'Work'], ['generation.,trial.,kaizen.', 'Self-improvement'], ['note.,goal.,plan.,brief.,milestone.', 'Your input'], ['instrument.,roles.', 'Models'], ['settings.,studio.,environment_map.', 'System']];
    const drawChips = () => clear(filterRow).append(...chips.map(([k, l]) => h('button', { class: `chip${k === kinds ? ' on' : ''}`, onclick: () => { kinds = k; drawChips(); load(); } }, l)), h('span.spacer'), verify);
    drawChips();
    body.append(h('div.card', filterRow, list));
    await load();
    offs.push(bus.on('job', debounce(load, 400)), bus.on('work', debounce(load, 400)));
  } else {
    const queueStatus = h('p.small.muted', { 'aria-live': 'polite' }), table = h('div.card.pad-0', { style: { overflowX: 'auto' } });
    const recovery = recoveryPanel(w => draw(w));
    const draw = (w) => {
      recovery.update(w);
      queueStatus.textContent = `${w.recovery ? 'Restart review required; nothing is replayed.' : w.paused ? 'Paused; queued work is held until Resume.' : 'One job at a time in this workspace.'} Job completion is not project acceptance; read the outcome.`;
      const rows = [...(w.current ? [dictJob(w.current, 'running')] : []), ...(w.queue || []).map((j) => dictJob(j, 'queued')), ...(w.history || []).map((j) => dictJob(j, j.result))];
      clear(table).append(rows.length ? h('table.table', h('tr', ['Job', 'By', 'State', 'Started', 'Took', 'Outcome'].map((t) => h('th', t))),
      rows.map((j) => h('tr', h('td', h('b', j.kind)), h('td', j.by || 'owner'), h('td', h('span', { class: `badge ${j.state === 'done' ? 'good' : j.state === 'failed' ? 'bad' : j.state === 'running' ? 'rune' : ''}` }, j.state)),
        h('td', j.started ? ago(j.started) : j.queued ? `queued ${ago(j.queued)}` : '—'), h('td', j.seconds != null ? `${j.seconds} s` : '—'), h('td.small.muted', (j.repeats > 1 ? `The same ${j.repeats} times since ${clock(j.first_finished)}. ` : '') + (j.outcome ? (j.outcome.error || j.outcome.summary || '') : '')))))
      : empty('clock', 'No jobs yet', 'Maps, rounds, plans and drafts appear here.'));
    };
    body.append(recovery.root, queueStatus, table); draw(await get('/api/worker'));
    offs.push(bus.on('worker', draw));
  }
  return () => offs.forEach((f) => f());
}
function dictJob(j, state) { return { ...j, state }; }
