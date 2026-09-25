// Overview: where things stand, what needs you, and what comes next.
import { h, icon, get, post, bus, toast, commentable, ago, plural, KIND, worstBand, BAND_COLOR, BAND_LABEL, humanize,
  withBusy, clock } from '../core.js';
import { LOGO } from '../icons.js';

function greeting() {
  const hr = new Date().getHours();
  return hr < 5 ? 'Working late' : hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening';
}

export default async function render(root, { app, navigate, refreshState }) {
  await refreshState();
  const s = app.state;
  const offs = [];
  const waiting = (s.proposals.waiting || 0) + (s.drafts.waiting || 0);

  // ---- hero: the one thing to do next
  let cta, line, extra = null;
  if (!s.ready.any) {
    line = 'Runesmith has mapped your folder. Give it thinking power (a model on this computer, an API key, or a chat window) and it can start working.';
    cta = h('button.btn.primary.lg', { onclick: () => { navigate('inference'); setTimeout(() => bus.emit('ui:add-model', {}), 250); } }, icon('cpu'), 'Add thinking power');
    extra = h('button.btn.lg', { title: 'No key and no install: you relay each request to a chat you already use', onclick: (e) => withBusy(e.currentTarget, async () => {
      const { useChatWindow } = await import('./goals.js');
      await useChatWindow();
      toast('A chat window is set up for planning. Next: Goals & plan → Draft a plan.', 'good', 7000);
      navigate('goals');
    }) }, icon('chat'), 'Use a chat window');
  } else if (waiting) {
    const fixes = s.proposals.waiting || 0, drafts = s.drafts.waiting || 0;     // judged fixes and unverified drafts
    const what = [fixes ? plural(fixes, 'fix', 'fixes') : '', drafts ? plural(drafts, 'draft') : ''].filter(Boolean).join(' and ');
    line = `${what} ${waiting === 1 ? 'waits' : 'wait'} for your review. Nothing is written to your files until you apply it.`;
    cta = h('button.btn.primary.lg', { onclick: () => navigate('work') }, icon('inbox'), waiting === 1 ? 'Review it' : 'Review them');
  } else if (s.manual_waiting) {
    line = 'A request is waiting for you to relay it to a chat model.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('inference', 'relay') }, icon('chat'), 'Open the chat relay');
  } else if (s.workspace.empty || (!s.objects.some((o) => o.kind === 'python_repository') && !s.plan.milestones)) {
    line = s.workspace.empty ? 'This folder is empty: a clean slate. Describe what to build and let the planner lay out milestones and first files.'
      : 'There is no code with tests to repair here yet. Draft a plan from your brief to start building.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('goals') }, icon('wand'), 'Plan what to build');
  } else {
    line = s.last_round ? `Last round ${ago(s.round_utc)}: ${humanize(s.last_round.outcome)}. ${s.worker.next_round_utc ? 'Next round ' + ago(s.worker.next_round_utc) + '.' : ''}`
      : 'Everything is set. Run a round to map, find work, work and report.';
    cta = h('button.btn.primary.lg', { onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'round' }); toast('Round queued', 'good'); }) }, icon('play'), 'Run a round now');
  }
  const hero = h('section.hero', h('div', { class: 'runes', html: LOGO }),
    h('div.small.faint', `${greeting()} · ${s.workspace.path}`),
    h('h2', s.workspace.name),
    h('p', line),
    h('div.row.mt-16.wrap', cta, extra,
      extra ? null : h('button.btn.lg', { onclick: () => navigate('map') }, icon('map'), 'Open the living map'),
      h('button.btn.lg.ghost', { onclick: () => import('../core.js').then((c) => c.openNotes('workspace', 'root', 'the whole workspace')) }, icon('note'), 'Tell Runesmith something')));
  commentable(hero, 'workspace', 'root', 'the whole workspace');

  // ---- setup checklist
  const steps = [
    { done: s.settings.onboarded, label: 'Named what you build here', go: () => navigate('goals') },
    { done: !!s.mapped_utc, label: 'Folder mapped', go: () => navigate('map') },
    { done: s.ready.any, label: 'Thinking power added', go: () => navigate('inference') },
    { done: s.goals.length > 0 || s.brief, label: 'Goals or a brief written', go: () => navigate('goals') },
    { done: !!s.round_utc, label: 'First round run', go: () => post('/api/worker/run', { job: 'round' }).then(() => toast('Round queued', 'good')) },
  ];
  const doneCount = steps.filter((x) => x.done).length;
  const checklist = doneCount < steps.length ? h('div.card',
    h('div.card-head', h('h3', icon('flag'), 'Getting set up'), h('span.badge.accent', `${doneCount} of ${steps.length}`)),
    h('div.bar.mb-8', h('i', { style: { width: `${(doneCount / steps.length) * 100}%` } })),
    h('div.list', steps.map((st) => h('div.item', h('div', { class: `ico ${st.done ? 'good' : ''}` }, icon(st.done ? 'check' : 'right')),
      h('div.body', h('div.title', st.label)), st.done ? null : h('button.btn.sm', { onclick: st.go }, 'Do it'))))) : null;

  // ---- KPIs
  const bands = s.objects.flatMap((o) => o.bands);
  const kpi = (k, v, sub, onclick, iconName) => h('div.card.hoverable', { onclick }, h('div.kpi', h('div.k', icon(iconName), ' ', k), h('div.v', v), h('div.trend', sub)));
  const trialText = s.attention ? `attention ${humanize(s.attention.mode).toLowerCase()}` : 'no work observed yet';
  const kpis = h('div.grid.four',
    kpi('Objects mapped', String(s.objects.length), s.mapped_utc ? `mapped ${ago(s.mapped_utc)}` : 'not mapped yet', () => navigate('map'), 'map'),
    kpi('Waiting for you', String(waiting), `${s.proposals.applied || 0} applied so far`, () => navigate('work'), 'inbox'),
    kpi('Repairs accepted', `${s.repairs.accepted}`, `of ${plural(s.repairs.judged, 'judged attempt')}`, () => navigate('work', 'attempts'), 'check'),
    kpi('Active generation', s.active_name || '—', `${(s.active_generation || '').replace('gen-', '')} · ${plural(s.generations, 'generation')} · ${trialText}`, () => navigate('improve'), 'branch'));

  // ---- objects
  const objects = h('div.card', h('div.card-head', h('h3', icon('grid'), 'What Runesmith found here'),
    h('div.actions', h('button.btn.sm', { onclick: () => navigate('map') }, 'Open map', icon('right')))));
  if (!s.objects.length) objects.append(h('p.muted', 'Nothing mapped yet. It takes a few seconds after the first start.'));
  const og = h('div.grid.auto');
  for (const o of s.objects.slice(0, 12)) {
    const band = worstBand(o.bands);
    const k = KIND[o.kind] || KIND.unknown;
    const done = o.ladder.filter((x) => x === 'achieved').length;
    const card = h('div.card.flat.hoverable', { onclick: () => navigate('map', `environment?focus=${encodeURIComponent(o.name)}`) },
      h('div.row', h('div.monogram', { style: { background: k.color } }, icon(k.icon)), h('div.grow', h('b.ellipsis', o.name), h('div.small.muted', k.label)),
        h('span', { class: `band ${band}` }, BAND_LABEL[band])),
      o.ladder.length ? h('div.mt-8', h('div.bar', h('i', { style: { width: `${(done / o.ladder.length) * 100}%` } })),
        h('div.tiny.faint.mt-8', o.next_rung ? `Next: ${humanize(o.next_rung)}` : 'Every rung achieved')) : null);
    commentable(card, 'object', o.name, o.name);
    og.append(card);
  }
  objects.append(og);

  // ---- next up
  const plan = await get('/api/plan').catch(() => ({ milestones: [] }));
  const next = h('div.card', h('div.card-head', h('h3', icon('route'), 'What comes next'),
    h('div.actions', h('button.btn.sm', { onclick: () => navigate('goals') }, 'Goals & plan', icon('right')))));
  const rows = plan.milestones.filter((m) => !['done', 'dropped', 'paused'].includes(m.status)).slice(0, 7);
  if (!rows.length) next.append(h('p.muted', 'No goals, milestones or rungs yet. Add a goal, or draft a plan from your brief.'));
  next.append(h('div.list', rows.map((m) => {
    const ic = { goal: 'target', milestone: 'flag', rung: 'layers' }[m.kind] || 'flag';
    const item = h('div.item', h('div.ico.accent', icon(ic)), h('div.body', h('div.title', m.title),
      h('div.meta', m.kind === 'rung' ? `rung ${m.progress[0] + 1} of ${m.progress[1]} on ${m.object}` : `${m.kind}${m.track ? ' · ' + m.track : ''} · ${m.status}`)));
    const [type, id] = m.kind === 'goal' ? ['goal', m.id.slice(5)] : m.kind === 'milestone' ? ['milestone', m.id.slice(10)] : ['rung', m.id.slice(5)];
    commentable(item, type, id, m.title);
    return item;
  })));

  // ---- live
  const live = h('div.card', h('div.card-head', h('h3', icon('activity'), 'Live'), h('div.actions', h('button.btn.sm', { onclick: () => navigate('activity') }, 'Full log', icon('right')))));
  const consoleBox = h('div.console');
  const worker = await get('/api/worker');
  const addLine = (l) => { consoleBox.append(h('div', { class: `l ${l.level || ''}` }, h('time', clock(l.utc)), l.text)); while (consoleBox.children.length > 60) consoleBox.firstChild.remove(); consoleBox.scrollTop = 1e9; };
  (worker.lines || []).slice(-25).forEach(addLine);
  if (!worker.lines?.length) consoleBox.append(h('div.l', h('time', ''), 'Quiet so far. Lines appear here as Runesmith works.'));
  offs.push(bus.on('log', addLine));
  live.append(consoleBox);

  // ---- capabilities
  const caps = h('div.card', h('div.card-head', h('h3', icon('gauge'), 'How well Runesmith works here'), h('span.badge', 'measured, never assumed')));
  const capNames = { repair_yield: 'Repair yield', seconds_per_repair: 'Seconds per repair', calls_per_repair: 'Model calls per repair', false_promotion_rate: 'False "fixed" rate' };
  for (const [key, label] of Object.entries(capNames)) {
    const c = (s.capabilities || {})[key] || { band: 'unknown', value: null };
    const row = h('div.gauge-row', h('span', label), h('div', { class: `bandbar${c.value == null ? ' unknown' : ''}` },
      c.value != null ? h('span.mark', { style: { left: `${bandPosition(c)}%` } }) : null),
      h('span', { class: `band ${c.band}` }, c.value == null ? 'unknown' : fmtCap(key, c.value)));
    commentable(row, 'capability', key, label);
    caps.append(row);
  }
  caps.append(h('p.tiny.faint.mt-8', 'Bands: bad · minimal · optimal. "Unknown" means there is no evidence yet, not that things are fine.'));

  root.append(hero, h('div.mt-24'), checklist ? h('div.grid.two', checklist, kpisWrap(kpis)) : kpis,
    h('div.grid.two.mt-24', objects, next), h('div.grid.two.mt-24', live, caps));
  function kpisWrap(k) { k.classList.remove('four'); k.classList.add('two'); return k; }
  return () => offs.forEach((off) => off());
}

function fmtCap(key, v) {
  if (key === 'repair_yield' || key === 'false_promotion_rate') return `${Math.round(v * 100)}%`;
  if (key === 'seconds_per_repair') return `${Math.round(v)} s`;
  return String(Math.round(v * 10) / 10);
}
function bandPosition(c) {
  // place the value on a 3-zone bar: bad | minimal | optimal
  const { value: v, minimal: lo, optimal: hi, higher_is_better: up } = c;
  if (v == null || lo == null || hi == null) return 50;
  const t = up ? (v - lo) / (hi - lo) : (lo - v) / (lo - hi);
  return Math.max(2, Math.min(98, 33 + t * 33));
}
export { bandPosition, fmtCap };
