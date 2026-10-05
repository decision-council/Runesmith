// Overview: where things stand, what needs you, and what comes next.
import { h, icon, get, post, bus, toast, commentable, ago, plural, KIND, worstBand, BAND_COLOR, BAND_LABEL, humanize,
  withBusy, clock, confirmDialog } from '../core.js';
import { logoMark } from '../icons.js';

function greeting() {
  const hr = new Date().getHours();
  return hr < 5 ? 'Working late' : hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening';
}

// Your numbers: the latest value of each measurement, in plain words, where the owner looks first (journey J5:
// the value was only on a project dashboard, under receipt hashes).
// What Runesmith decided by the owner's own settings, in plain words (journey J11-G42, G43): keeping the queue after a
// restart, one more try for a milestone whose tries are used up, smaller steps for one that failed that too.
function automaticCard(s) {
  const rows = s.automatic || [];
  if (!rows.length) return null;
  return h('section.card', { 'aria-label': 'Decided by your settings' },
    h('div.card-head', h('h3', icon('shield'), 'Decided by your settings')),
    h('div.list', rows.map((r) => h('div.item', h('div.body', h('div.title', r.what), h('div.meta', `${ago(r.utc)} · ${r.by}`))))));
}

// A stuck milestone nothing more is tried for by itself (journey J11-B28: after a failed one more try and a refused break-down
// the project idled for good and the owner was told nothing). What is stuck, why, and what he can do; no choice grants tries.
function needsYouCard(s, navigate, redraw) {
  const rows = s.needs_you || [];
  if (!rows.length) return null;
  const act = {
    escalate: (e) => withBusy(e.currentTarget, async () => {
      await post('/api/worker/run', { job: 'escalate' });
      toast('Asked for one more try with another model. It is checked like any other.', 'good');
    }),
    breakdown: (e, r) => withBusy(e.currentTarget, async () => {
      await post('/api/worker/run', { job: 'breakdown', params: { milestone: r.milestone } });
      toast('Asked a model for smaller steps. They wait for your review under Goals & plan.', 'good', 6000);
    }),
    close_interrupted: (e, r) => withBusy(e.currentTarget, async () => {
      await post(`/api/build/escalations/${r.receipt}/close`, {});
      toast('Closed. Its one more try counts as used, nothing was sent, and the build goes on from there.', 'good', 6000);
      redraw?.();
    }),
    review: () => navigate('goals'),
    show_file: () => navigate('goals'),
    edit: () => navigate('goals'),
    set_aside: (e, r) => withBusy(e.currentTarget, async () => {
      if (!(await confirmDialog({ title: 'Set this milestone aside?', confirm: 'Set it aside', icon: 'flag',
        text: `“${r.title}” is dropped from the plan, and the plan goes on without it. You can reopen it any time in Goals & plan.` }))) return;
      await post(`/api/plan/milestones/${r.milestone}`, { status: 'dropped' });
      toast('Set aside. The plan goes on without it.', 'good');
      redraw?.();
    }),
  };
  return h('section.card.mt-24', { 'aria-label': 'Needs you', 'data-needs-you': '' },
    h('div.card-head', h('h3', icon('alert'), 'Needs you'), h('span.badge.warn', plural(rows.length, 'milestone'))),
    h('div.list', rows.map((r) => h('div.item', { 'data-milestone': r.milestone },
      h('div.body', h('div.title', r.title), h('p.small', r.what),
        h('div.row.wrap.mt-8', r.choices.map((c, i) => h(i === 0 ? 'button.btn.sm.primary' : 'button.btn.sm', {
          title: c.detail || '', 'data-choice': c.id,
          onclick: (e) => act[c.id]?.(e, r) }, c.label))))))));
}

function numbersCard(s, navigate) {
  const rows = s.numbers || [];
  if (!rows.length) return null;
  const pct = (v) => `${(v * 100).toFixed(1).replace(/\.0$/, '')}%`;
  const shown = (n) => n.value == null ? '—' : n.aggregation === 'ratio' ? pct(n.value)
    : `${Number(n.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${n.unit ? ` ${n.unit}` : ''}`;
  const target = (n) => !n.threshold ? '' : `target ${n.threshold.op === 'gte' ? 'at least' : 'at most'} ${n.aggregation === 'ratio' ? pct(n.threshold.value) : n.threshold.value}`;
  const row = (n) => h('div.item', h('div.body', h('div.title', `${n.name}: `, h('b', shown(n))),
    h('div.meta', [n.status === 'measured' ? `${n.source_file ? `from ${n.source_file} · ` : ''}measured ${ago(n.measured_at)}`
      : n.status ? `not measured: ${n.detail || n.status}` : 'not measured yet', target(n)].filter(Boolean).join(' · '))),
    n.threshold_met === true ? h('span.badge.good', 'on target') : n.threshold_met === false ? h('span.badge.warn', 'off target') : null);
  return h('section.card.mt-24', { 'aria-label': 'Your numbers' },
    h('div.card-head', h('h3', icon('gauge'), 'Your numbers'), h('div.actions',
      h('button.btn.sm', { onclick: (e) => withBusy(e.currentTarget, async () => {
        for (const n of rows) await post('/api/worker/run', { job: 'measure', params: { measurement: n.id } });
        toast('Reading your reports now. No model is asked.', 'good');
      }) }, icon('refresh'), 'Measure now'),
      h('button.btn.sm.ghost', { onclick: () => navigate('mission') }, 'Change what is measured'))),
    h('div.list', rows.map(row)));
}

// A model server already running on this computer is named and offered first (journey J8-F1).
const SERVER_NAMES = { ollama: 'Ollama', lmstudio: 'LM Studio', llamacpp: 'llama.cpp' };
async function offerLocalServer(hero, cta, navigate) {
  let found = [];
  try { found = (await get('/api/inference/discover')).found || []; } catch { return; }
  const f = found.find((x) => x.models?.length);
  if (!f) return;                    // the hero may not be on the page yet: it is changed in place either way
  const name = SERVER_NAMES[f.preset] || f.preset;
  hero.querySelector('p')?.after(h('p.small', { 'data-local-server': f.preset },
    `${name} is already running on this computer, with ${plural(f.models.length, 'model')} (${f.models.slice(0, 3).join(', ')}). It is free and nothing leaves this computer.`));
  cta.classList.remove('primary');
  cta.before(h('button.btn.primary.lg', { onclick: () => { navigate('inference'); setTimeout(() => bus.emit('ui:add-model', { preset: f.preset, extra: { model: f.models[0], models: f.models } }), 250); } },
    icon('cpu'), `Use ${name}`));
}

export default async function render(root, { app, navigate, refreshState }) {
  await refreshState();
  const s = app.state;
  const offs = [];
  const waiting = (s.proposals.waiting || 0) + (s.drafts.waiting || 0);

  // ---- hero: the one thing to do next
  let cta, line, extra = null, offerLocal = false;
  if (s.worker?.recovery?.required) {
    line = 'Runesmith was restarted in the middle of a job. Nothing was repeated or sent twice, and nothing continues until you have had a look.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('activity') }, icon('alert'), 'Review restart recovery');
  } else if (s.manual_waiting) {
    line = 'A request is waiting for your chat window: copy it into the chat you use, then paste the reply back here. Runesmith cannot send it on its own, even on a schedule.';   // journey J2-F4
    cta = h('button.btn.primary.lg', { onclick: () => navigate('inference', 'relay') }, icon('chat'), 'Open the chat relay');
  } else if (s.worker?.current) {
    line = 'A job is already in progress. Inspect its current step and saved outcomes; running is not the same as passing checks or applying a change.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('activity') }, icon('activity'), 'Inspect current work');
  } else if (s.worker?.paused) {
    line = 'The work queue is paused. Review Activity before resuming; an enabled schedule or configured model does not override the pause.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('activity') }, icon('activity'), 'Review paused work');
  } else if (s.settings.use_type === 'numbers' && !(s.numbers || []).length) {
    // Someone who came to keep an eye on their numbers: the one next step is choosing a number (journey J5-F1).
    const reports = (s.objects || []).filter((o) => o.kind === 'data_reports');
    const where = reports.map((o) => o.root ? 'this folder' : o.name).join(', ');
    line = `You want to keep an eye on your numbers. ${reports.length ? `Runesmith found report files in ${where}.` : 'Runesmith has found no report files yet: put your exports (CSV) in this folder.'} Choose one number to watch: which file, which column, and your target. Measuring asks no model.`;
    cta = h('button.btn.primary.lg', { onclick: () => navigate('mission', 'add-measurement') }, icon('gauge'), 'Choose a number to watch');
  } else if (s.settings.use_type === 'numbers' && s.settings.autonomy === 'observe') {
    // A number is watched: say how it stays current, not "you chose to just look" (journey J12-F2).
    line = `Runesmith keeps an eye on your numbers, below. Each measurement reads the newest report and asks no model. ${s.settings.auto_work ? 'Rounds run on a schedule; the Operations mode measures in them.' : 'To measure without clicking, turn on the Operations mode and “Work on a schedule”.'}`;
    cta = h('button.btn.primary.lg', { onclick: () => navigate('mission') }, icon('gauge'), 'Your numbers and targets');
  } else if (s.settings.autonomy === 'observe') {
    line = 'You chose to just look. Runesmith maps your folder and reports what it finds; it asks no model and changes nothing.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('map') }, icon('map'), 'See what it found');
    extra = h('button.btn.lg', { title: 'Plan and draft with a model; you review every change', onclick: (e) => withBusy(e.currentTarget, async () => {
      if (!(await confirmDialog({ title: 'Let Runesmith help?', confirm: 'Let it help', icon: 'wand',
        text: 'Runesmith will ask a model to plan and draft, and will propose changes for you to review. It still changes no file on its own unless you allow automatic apply.' }))) return;
      await post('/api/settings', { autonomy: 'propose' });
      toast('Runesmith may now plan and draft; you review every change.', 'good');
      navigate('home');
    }) }, icon('wand'), 'Let it help');
  } else if (!s.ready.any) {
    // Plain words for a first-time owner (journey J1-F1): what this folder is, and the one thing Runesmith needs.
    line = `${s.workspace.empty ? `An empty folder: a clean start for ${s.workspace.name}.` : s.mapped_utc ? 'Runesmith has mapped your folder.' : 'Runesmith can map your folder.'} To plan and build, it needs thinking power: a model on this computer, an API key, or simply a chat window you already use.`;
    cta = h('button.btn.primary.lg', { onclick: () => { navigate('inference'); setTimeout(() => bus.emit('ui:add-model', {}), 250); } }, icon('cpu'), 'Add thinking power');
    offerLocal = true;
    extra = h('button.btn.lg', { title: 'No key and no install: you relay each request to a chat you already use', onclick: (e) => withBusy(e.currentTarget, async () => {
      const { useChatWindow } = await import('./goals.js');
      await useChatWindow();
      toast('A chat window is set up for planning. Next: Goals & plan → Draft a plan.', 'good', 7000);
      navigate('goals');
    }) }, icon('chat'), 'Use a chat window');
  } else if (waiting) {
    const fixes = s.proposals.waiting || 0, drafts = s.drafts.waiting || 0;     // judged fixes and unverified drafts
    const what = [fixes ? plural(fixes, 'fix', 'fixes') : '', drafts ? plural(drafts, 'draft') : ''].filter(Boolean).join(' and ');
    line = `${what} ${waiting === 1 ? 'waits' : 'wait'} for your review. Check the saved verification and application state. Delegated build application, if enabled with a valid grant, is separate from manual review.`;
    cta = h('button.btn.primary.lg', { onclick: () => navigate('work') }, icon('inbox'), waiting === 1 ? 'Review it' : 'Review them');
  } else if (s.workspace.empty || (!s.objects.some((o) => o.kind === 'python_repository') && !s.plan.milestones)) {
    line = s.workspace.empty ? 'This folder is empty: a clean slate. Describe what to build and let the planner lay out milestones and first files.'
      : 'There is no code with tests to repair here yet. Draft a plan from your brief to start building.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('goals') }, icon('wand'), 'Plan what to build');
  } else if (s.plan?.next) {
    // With a plan under way, the next step is the plan's next milestone (journey J1-F2).
    line = `Next in your plan: “${s.plan.next.title}” (${s.plan.done || 0} of ${s.plan.milestones} done). Try what was built below, or continue in Goals & plan.`;
    // An owner back from "build while I'm away" hears that the last attempt did not work (journey J2-F11).
    const builds = (s.worker?.history || []).filter((j) => ['build', 'escalate', 'correct'].includes(j.kind));
    const last = builds[0], streak = builds.findIndex((j) => j.result !== 'failed');
    const tries = streak < 0 ? builds.length : streak;          // failed tries in a row (J2-F13)
    if (last?.result === 'failed') line += ` The last attempt did not work (${ago(last.finished)}): ${String(last.outcome?.error || 'see Activity').slice(0, 180)}`
      + (tries >= 3 ? ` ${tries} tries in a row did not work, so it waits for you: Work & proposals → Drafts shows what you can do.` : s.settings.auto_work ? ' The next round tries again.' : '');
    // Rounds that find every try used up end "done", but building waits all the same (journey J2-F16).
    else if (last?.outcome?.replan_needed) line += ' The tries for this step are used up, so building waits for you: Work & proposals → Drafts shows what you can do, and Goals & plan may offer smaller steps to adopt.'
      + (last.outcome.cause ? ` The cause: ${last.outcome.cause}` : '');
    if (s.needs_you?.length) line += ` Runesmith has nothing more to try by itself for ${s.needs_you.length === 1 ? `“${s.needs_you[0].title}”` : plural(s.needs_you.length, 'milestone')}: see Needs you below.`;
    cta = h('button.btn.primary.lg', { onclick: () => navigate('goals') }, icon('target'), 'Continue the plan');
  } else {
    line = 'Review enabled modes and their prerequisites before starting. A configured route is not a capacity test, and a saved work outcome is not proof that the project is complete.';
    cta = h('button.btn.primary.lg', { onclick: () => navigate('mission') }, icon('sliders'), 'Choose the next work mode');
  }
  const hero = h('section.hero', h('div', { class: 'runes', html: logoMark({ forge: true }) }),
    h('div.small.faint', `${greeting()} · ${s.workspace.path}`),
    h('h2', s.workspace.name),
    h('p', line),
    h('div.row.mt-16.wrap', cta, extra,
      h('button.btn.lg', {onclick:()=>navigate('dashboards')}, icon('gauge'), 'Project dashboards'),
      extra ? null : h('button.btn.lg', { onclick: () => navigate('map') }, icon('map'), 'Open the living map'),
      h('button.btn.lg.ghost', { onclick: () => import('../core.js').then((c) => c.openNotes('workspace', 'root', 'the whole workspace')) }, icon('note'), 'Tell Runesmith something')));
  commentable(hero, 'workspace', 'root', 'the whole workspace');
  if (offerLocal) offerLocalServer(hero, cta, navigate);

  // ---- setup checklist
  const steps = [
    { done: s.settings.onboarded, label: 'Named what you build here', go: () => navigate('goals') },
    { done: !!s.mapped_utc, label: 'Folder mapped', go: () => navigate('map') },
    { done: s.ready.any, label: 'Thinking power configured (not tested)', go: () => navigate('inference') },
    { id: 'policy', done: !!s.settings.policy_chosen, label: 'Chose how Runesmith may work here',
      go: () => document.getElementById('work-policy')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) },
    { done: s.goals.length > 0 || s.brief, label: 'Goals or a brief written', go: () => navigate('goals') },
    { done: !!s.round_utc, label: 'Work history recorded (not a success verdict)', go: () => navigate('mission') },
  ];
  const doneCount = steps.filter((x) => x.done).length;
  const checklist = doneCount < steps.length ? h('div.card',
    h('div.card-head', h('h3', icon('flag'), 'Getting set up'), h('span.badge.accent', `${doneCount} of ${steps.length}`)),
    h('div.bar.mb-8', h('i', { style: { width: `${(doneCount / steps.length) * 100}%` } })),
    h('div.list', steps.map((st) => h('div.item', { 'data-step': st.id }, h('div', { class: `ico ${st.done ? 'good' : ''}` }, icon(st.done ? 'check' : 'right')),
      h('div.body', h('div.title', st.label)), st.done ? null : h('button.btn.sm', { onclick: st.go }, 'Do it'))))) : null;

  // How Runesmith may work here: the owner's explicit choices. Finishing the introduction switches none of them on.
  // This is setup evidence, not an unattended-readiness score or a launch action.
  const choose = async (patch, message) => {
    try {
      const saved = await post('/api/settings', { ...patch, policy_chosen: true });
      Object.assign(s.settings, saved);
      toast(message, 'good', 2200);
      keep?.remove();
      stepDone();
    } catch (e) { toast(e.message, 'bad'); }
  };
  const choice = (key, label, detail) => h('div.setting', h('div.text', h('b', label), h('span', detail)),
    h('label.switch', h('input', { type: 'checkbox', checked: !!s.settings[key], 'aria-label': label,
      onchange: (e) => choose({ [key]: e.target.checked }, `${label}: ${e.target.checked ? 'on' : 'off'}`) }), h('span')));
  const keep = s.settings.policy_chosen ? null : h('div.row.mt-8', h('button.btn.primary', {
    onclick: (e) => withBusy(e.currentTarget, () => choose({}, 'Your choices are saved')) }, icon('check'), 'Keep these choices'));
  const stepDone = () => {
    const item = checklist?.querySelector('[data-step="policy"]');
    if (!item) return;
    item.querySelector('.ico')?.replaceWith(h('div', { class: 'ico good' }, icon('check')));
    item.querySelector('button')?.remove();
  };
  const policy = h('section.card.mt-24', {'aria-label':'Setup and work policy', id:'work-policy'},
    h('div.card-head', h('h3', icon('sliders'), 'How Runesmith may work here'),
      h('button.btn.sm', {onclick:()=>navigate('settings')}, 'Review settings')),
    h('p.small.muted', s.settings.policy_chosen
      ? 'Your choices. Change them any time; every change is recorded in Activity.'
      : 'Nothing below runs until you choose. Finishing the introduction does not switch any of it on.'),
    choice('auto_work', 'Work on a schedule',
      `Run a round every ${s.settings.interval_minutes} minutes while the Studio is open. Each round can spend model calls. Pause, mode guards and provider limits still apply.`),
    choice('probe_tests', 'Run this project’s tests while mapping',
      // Journey J4-F2: a folder of documents was offered this switch with nothing to run.
      (s.mapped_utc && !s.map_outdated && !s.objects.some((o) => o.kind === 'python_repository') ? 'Nothing to run yet: the map found no code with tests here. ' : '') +
      'This executes the project’s own code, on a throwaway copy of the folder. Only for projects you trust: the copy is not a security boundary.'),
    choice('kaizen', 'Let Runesmith improve itself',
      'Separate from Optimize. A self-made improvement becomes active only by winning a trial on your work.'),
    keep,
    h('div.list.mt-16', [
      ['Check drafts by running their tests', s.settings.build_steps, 'Runs project code in a throwaway working copy. Set in Goals & plan → Build continuation.'],
      ['Apply checked drafts automatically', s.settings.build_apply, 'Also needs your own acceptance checks, allowed folders and an unchanged source. Set in Goals & plan.'],
    ].map(([label,value,detail])=>h('div.item',h('div.body',h('div.title',label),h('div.meta',detail)),
      h('span.badge',typeof value==='boolean'?(value?'On':'Off'):'Not reported'),
      h('button.btn.sm',{onclick:()=>navigate('goals')},'Change')))),
    h('p.small.muted', 'API/local routes are needed for unattended transport. A chat-window instrument waits for your copied replies. Operations currently reads selected local reports; it is not a production deployment or messaging engine.'));
  const healthBody=h('div'); let closed=false,healthSerial=0;
  const checkLocal=async()=>{
    const serial=++healthSerial;
    let rows;
    try {
      const result=await get('/api/health?network=0');
      if(!Array.isArray(result?.checks)||!result.checks.length)throw new Error('No diagnostic results returned');
      if(result.checks.some(r=>!r||typeof r.check!=='string'||!r.check.trim()||![true,false,null].includes(r.ok)))
        throw new Error('Incomplete diagnostic results returned');
      rows=result.checks;
    } catch(error) {
      if(!closed&&serial===healthSerial)healthBody.replaceChildren(h('p.callout.warn',`Local checks unavailable: ${error.message}. Setup is unknown; nothing was installed or started.`));
      return;
    }
    if(closed||serial!==healthSerial)return;
    const issues=rows.filter(r=>r.ok===false);
    healthBody.replaceChildren(h('p',{class:issues.length?'callout warn':'small muted'},issues.length
      ? `${issues.length} local setup issue(s) need review. No automatic installation or repair.`
      : 'No failure reported by these local checks. Model reachability, quota, author quality and unattended completion are not established.'),
      h('details', h('summary.small','Inspect local checks'),h('div.list',rows.map(r=>h('div.item',
        h('div.body',h('b.small',String(r.check||'Unnamed check')),h('p.small',String(r.detail||'')),
          r.fix?h('p.tiny.mono',`Suggested next step: ${r.fix}`):null),
        h('span.badge',r.ok===true?'Passed':r.ok===false?'Needs attention':'Not checked'))))));
  };
  policy.append(h('div.card-head.mt-16',h('h4','Local setup checks'),
    h('button.btn.sm',{onclick:e=>withBusy(e.currentTarget,checkLocal)},icon('refresh'),'Refresh local checks')),
    h('p.tiny.muted','Read-only and offline: no provider probe, model call, package installation or queued job.'),healthBody);
  await checkLocal();

  // ---- KPIs
  const bands = s.objects.flatMap((o) => o.bands);
  const kpi = (k, v, sub, onclick, iconName) => h('div.card.hoverable', { onclick }, h('div.kpi', h('div.k', icon(iconName), ' ', k), h('div.v', v), h('div.trend', sub)));
  const trialText = s.attention ? `attention ${humanize(s.attention.mode).toLowerCase()}` : 'no work observed yet';
  const kpis = h('div.grid.four',
    kpi('Objects mapped', String(s.objects.length), s.map_outdated ? 'made by an earlier version: map again' : s.mapped_utc ? `mapped ${ago(s.mapped_utc)}` : 'not mapped yet', () => navigate('map'), 'map'),
    kpi('Waiting for you', String(waiting), `${(s.proposals.applied || 0) + (s.drafts.applied || 0)} applied so far`, () => navigate('work'), 'inbox'),
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

  // ---- fix the failing tests (J3): the owner's own tests, frozen, decide; builders change only the code
  const fixCard = h('section.card.mt-24', { 'aria-label': 'Fix the failing tests', hidden: true });
  const loadFix = () => get('/api/fix-tests').then((f) => {
    if (closed) return;
    fixCard.replaceChildren();
    fixCard.hidden = !f.offer;
    if (f.offer) drawFix(fixCard, f.offer, navigate);
  }).catch(() => {});
  loadFix();
  offs.push(bus.on('round', loadFix));

  // ---- try what was built (G2): the owner runs the project's own program, on a practice copy unless they choose
  const tryCard = h('section.card.mt-24', { 'aria-label': 'Try what was built', hidden: true });
  get('/api/try').then((t) => { if (!closed && t.suggestions?.length) drawTry(tryCard, t); }).catch(() => {});

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

  // A plain DOM append prints "null" for an empty card (journey J6-B1), so only real cards are passed.
  root.append(hero, ...[needsYouCard(s, navigate, () => navigate('home')), automaticCard(s), numbersCard(s, navigate)].filter(Boolean), policy, h('div.mt-24'), checklist ? h('div.grid.two', checklist, kpisWrap(kpis)) : kpis,
    h('div.grid.two.mt-24', objects, next), fixCard, tryCard, h('div.grid.two.mt-24', live, caps));
  function kpisWrap(k) { k.classList.remove('four'); k.classList.add('two'); return k; }
  return () => {closed=true;healthSerial++;offs.forEach((off) => off());};
}

function drawFix(card, o, navigate) {
  const share = o.tests_green == null ? 'Some of its tests fail.' : `${Math.round(o.tests_green * 100)}% of its tests pass.`;
  const auto = h('input', { type: 'checkbox', 'aria-label': 'Apply the fix automatically when every test passes' });
  card.append(h('div.card-head', h('h3', icon('hammer'), 'Fix the failing tests'), h('span.badge', o.object)),
    h('p.small', `${share} Runesmith can fix the code for you. Your tests, as they are now, decide when it is done; it changes the code only, never the tests.`),
    h('label.row.mt-8', auto, `Apply the fix automatically when every test passes (it may write only: ${o.code_paths.join(', ')})`),
    h('div.row.wrap.mt-8', h('button.btn.primary', { onclick: (e) => withBusy(e.currentTarget, async () => {
      if (!(await confirmDialog({ title: 'Fix the failing tests?', confirm: 'Fix them', icon: 'hammer',
        text: `Runesmith adds a milestone, “Make the failing tests pass”. Your ${o.test_files} test file(s) are frozen as they are now and decide when it is done. ` +
          (auto.checked ? 'When every test passes, the fix is applied to your code automatically; your tests are never changed.' : 'You review the fix and apply it yourself.') }))) return;
      await post('/api/fix-tests', { allow_apply: auto.checked });
      await post('/api/worker/run', { job: 'build' });
      toast('Fixing the failing tests: follow it in Goals & plan and Activity.', 'good', 6000);
      navigate('goals');
    }) }, icon('hammer'), 'Fix the failing tests')));
  card.hidden = false;
}

function drawTry(card, t) {
  let realConfirmed = false;
  const usable = t.suggestions.find((x) => !x.placeholders) || t.suggestions[0];
  const command = h('input.input.mono', { value: usable.command, 'aria-label': 'Command to try', spellcheck: 'false' });
  const real = h('input', { type: 'checkbox', 'aria-label': 'Use my real folder (changes are kept)' });
  const output = h('pre.code.mt-8', { hidden: true, 'aria-live': 'polite' });
  const verdict = h('div.small.mt-8', { hidden: true });
  const chips = h('div.pillbox.mt-8', t.suggestions.map((x) => h('button.chip', { type: 'button', title: `From ${x.source}`,
    onclick: () => { command.value = x.command; command.focus(); } }, x.command, x.placeholders ? h('span.faint', ' · fill in the capitals') : null)));
  const runBtn = h('button.btn.primary', { onclick: (e) => withBusy(e.currentTarget, async () => {
    if (real.checked && !realConfirmed) {
      if (!(await confirmDialog({ title: 'Run it in your real folder?', confirm: 'Run for real', icon: 'play',
        text: 'Your program runs in your own folder, so what it changes is kept, for example a book you add. The practice copy is the safe way to try things first.' }))) return;
      realConfirmed = true;
    }
    const r = await post('/api/try/run', { command: command.value, real: real.checked });
    verdict.hidden = false; output.hidden = false;
    verdict.textContent = r.timed_out ? `Stopped after ${t.timeout_s} s: a program that keeps running or waits for typing cannot be tried here.`
      : r.exit_code === 0 ? `Finished normally in ${r.seconds} s${r.real ? ', in your real folder' : ', on the practice copy'}.`
        : `Ended with an error (exit status ${r.exit_code}) in ${r.seconds} s.`;
    verdict.className = `small mt-8 ${r.exit_code === 0 ? 'good' : 'warn'}`;
    output.textContent = [r.stdout, r.stderr].filter((x) => x && x.trim()).join('\n') || '(no output)';
  }) }, icon('play'), 'Run');
  const resetBtn = h('button.btn.ghost', { onclick: (e) => withBusy(e.currentTarget, async () => {
    await post('/api/try/reset', {}); toast('The practice copy starts again from your real folder.', 'good'); }) }, icon('refresh'), 'Start the practice copy again');
  card.append(h('div.card-head', h('h3', icon('play'), 'Try what was built'), h('span.badge', 'runs your program')),
    h('p.small.muted', 'Pick a command from your project’s own instructions, change it if you like, and run it. It runs on a practice copy of your folder, so nothing real changes, unless you choose your real folder.'),
    chips, h('div.row.wrap.mt-8', command), h('label.row.mt-8', real, 'Use my real folder (changes are kept)'),
    h('div.row.wrap.mt-8', runBtn, resetBtn), verdict, output);
  card.hidden = false;
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
