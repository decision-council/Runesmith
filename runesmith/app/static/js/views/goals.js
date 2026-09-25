// Goals & plan: what the owner wants, in their words; the brief and blueprints; the plan the Planner drafts.
import { h, icon, get, post, del, bus, toast, commentable, openNotes, clear, ago, plural, humanize, withBusy,
  confirmDialog, askText, empty, debounce } from '../core.js';

const STATUS = { open: ['', 'open'], doing: ['rune', 'in progress'], done: ['good', 'done'], dropped: ['', 'dropped'] };

/** One click: a chat window you relay by hand, for planning and self-improvement (not for repairs, which take many calls). */
export async function useChatWindow() {
  const inf = await get('/api/inference');
  const existing = inf.instruments.find((i) => i.kind === 'manual');
  if (existing) {
    const roles = { ...inf.roles };
    for (const r of ['plan', 'kaizen']) if (!roles[r].includes(existing.name)) roles[r] = [...roles[r], existing.name];
    await post('/api/inference/roles', { roles });
    return existing.name;
  }
  const name = inf.instruments.some((i) => i.name === 'chat') ? 'chat-window' : 'chat';
  await post('/api/inference/instruments', { name, spec: { kind: 'manual', preset: 'manual', model: 'a chat window', label: 'A chat window (copy and paste)' }, roles: ['plan', 'kaizen'] });
  return name;
}

export default async function render(root, ctx) {
  const offs = [];
  const head = h('div.page-head', h('div', h('h2', 'Goals & plan'),
    h('p', 'Tell Runesmith what matters in your own words. Say as much or as little as you like: a sentence, a brief, or whole blueprint documents from this folder. The Planner turns it into milestones on named tracks, and can write first files for any milestone as a draft you review.')));
  const left = h('div.col.gap-16'), right = h('div.col.gap-16');
  root.append(head, h('div.grid.two', left, right));

  // ---- goals
  const goalsCard = h('div.card');
  const drawGoals = async () => {
    const goals = await get('/api/goals');
    const input = h('input.input', { placeholder: 'A goal, e.g. “Every test passes” or “Launch the booking page by Friday”' });
    const add = h('button.btn.primary', icon('plus'), 'Add');
    const submit = () => withBusy(add, async () => { if (!input.value.trim()) return; await post('/api/goals', { text: input.value }); input.value = ''; drawGoals(); });
    add.addEventListener('click', submit);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    clear(goalsCard).append(h('div.card-head', h('h3', icon('target'), 'Goals'), h('span.badge', `${goals.filter((g) => g.status === 'active').length} active`)),
      h('div.row', input, add));
    const list = h('div.list.mt-8');
    if (!goals.length) list.append(h('p.muted.small', 'No goals yet. Goals appear on the map and guide the Planner.'));
    for (const g of goals) {
      const item = h('div.item', h('button', { class: `btn icon sm ${g.status === 'done' ? 'rune' : ''}`, title: g.status === 'done' ? 'Mark active' : 'Mark done',
        onclick: async () => { await post(`/api/goals/${g.id}`, { status: g.status === 'done' ? 'active' : 'done' }); drawGoals(); } }, icon('check')),
        h('div.body', h('div.title', { style: g.status === 'done' ? { textDecoration: 'line-through', opacity: '.6' } : null }, g.text), h('div.meta', `${g.kind} · added ${ago(g.created)}`)),
        h('button.btn.icon.sm.ghost', { title: 'Edit', onclick: async () => { const t = await askText({ title: 'Edit goal', value: g.text, confirm: 'Save' }); if (t) { await post(`/api/goals/${g.id}`, { text: t }); drawGoals(); } } }, icon('pencil')),
        h('button.btn.icon.sm.ghost', { title: 'Remove', onclick: async () => { if (await confirmDialog({ title: 'Remove this goal?', text: g.text, confirm: 'Remove', danger: true })) { await del(`/api/goals/${g.id}`); drawGoals(); } } }, icon('trash')));
      commentable(item, 'goal', g.id, g.text);
      item.querySelector('.note-btn').style.right = '76px';
      list.append(item);
    }
    goalsCard.append(list);
  };

  // ---- brief & blueprints
  const briefCard = h('div.card');
  const drawBrief = async () => {
    const b = await get('/api/brief');
    const ta = h('textarea.textarea', { rows: 9, placeholder: 'Describe what this folder is for, who it serves, what “done” looks like, constraints, style. Markdown is fine.' }, b.text || '');
    const save = h('button.btn.primary', icon('check'), 'Save brief');
    const status = h('span.small.faint', b.updated ? `saved ${ago(b.updated)}` : 'not saved yet');
    const chosen = new Set((b.blueprints || []).map((x) => x.path));
    const picks = h('div.col.gap-6.mt-8', { style: { maxHeight: '220px', overflowY: 'auto' } });
    if (!b.candidates.length) picks.append(h('p.small.muted', 'No documents (.md, .txt, .rst) found in this folder yet.'));
    for (const c of b.candidates) {
      const cb = h('input', { type: 'checkbox', checked: chosen.has(c.path), onchange: () => { cb.checked ? chosen.add(c.path) : chosen.delete(c.path); } });
      picks.append(h('label.row.small', { style: { cursor: 'pointer' } }, cb, h('span.mono.grow.ellipsis', c.path), h('span.faint', `${Math.round(c.bytes / 1024)} KB`)));
    }
    save.addEventListener('click', () => withBusy(save, async () => { await post('/api/brief', { text: ta.value, blueprints: [...chosen] }); status.textContent = 'saved just now'; toast('Brief saved. The Planner reads it next time.', 'good'); }));
    clear(briefCard).append(h('div.card-head', h('h3', icon('book'), 'Brief'), h('div.actions', status)), ta,
      h('div.label-text.mt-16', 'Blueprint documents the Planner should read'), picks, h('div.row.mt-16', h('span.tiny.faint', 'The Planner reads up to 12,000 characters of blueprints.'), h('span.spacer'), save));
    commentable(briefCard, 'brief', 'current', 'the brief');
  };

  // ---- plan
  const planCard = h('div.card');
  const drawPlan = async () => {
    const data = await get('/api/plan');
    const plan = data.plan;
    const draftBtn = h('button.btn.primary', { disabled: !data.ready, title: data.ready ? '' : 'Add a model under Thinking power first' }, icon('wand'), plan ? 'Redraft the plan' : 'Draft a plan');
    draftBtn.addEventListener('click', () => withBusy(draftBtn, async () => {
      if (plan && !(await confirmDialog({ title: 'Redraft the plan?', text: 'The Planner writes a new version from your brief, goals, blueprints, notes and the map. The current version is kept in the home’s plans/ folder.', confirm: 'Redraft' }))) return;
      await post('/api/worker/run', { job: 'plan' }); toast('The Planner is drafting. This page updates when it is done.', 'good', 6000);
    }));
    clear(planCard).append(h('div.card-head', h('h3', icon('route'), 'Plan'), plan ? h('span.badge', `v${plan.version} · ${plan.drafted_by || 'owner'} · ${ago(plan.utc)}`) : null,
      h('div.actions', h('button.btn.sm', { onclick: async () => { const t = await askText({ title: 'Add a milestone', placeholder: 'e.g. A first page that lists tasks', confirm: 'Add' }); if (t) { await post('/api/plan/milestones', { title: t }); drawPlan(); } } }, icon('plus'), 'Milestone'), draftBtn)));
    if (!data.ready) {
      const quick = h('button.btn.sm.primary', icon('chat'), 'Use a chat window (no key)');
      quick.addEventListener('click', () => withBusy(quick, async () => {
        await useChatWindow();
        toast('Ready. When the Planner needs an answer, the request appears under Thinking power → Chat relay.', 'good', 7000);
        drawPlan(); ctx.refreshState();
      }));
      planCard.append(h('div.callout.warn', icon('cpu'), h('div', 'To draft a plan, Runesmith needs a model. The simplest is a chat window you already use: Runesmith shows each request, you paste it into the chat and paste the answer back.',
        h('div.row.wrap.mt-8', quick, h('button.btn.sm', { onclick: () => ctx.navigate('inference') }, 'Other options')))));
    }
    if (!plan) { planCard.append(empty('route', 'No plan yet', 'Write a brief (or just a goal), then let the Planner draft milestones on tracks. You can edit everything.')); return; }
    commentable(planCard, 'plan', 'current', 'the plan');
    if (plan.summary) planCard.append(h('p', plan.summary));
    if (plan.tracks?.length) planCard.append(h('div.pillbox.mb-8', plan.tracks.map((t) => h('span.badge.violet', { title: t.purpose }, t.name))));
    const list = h('div.list');
    for (const m of plan.milestones) {
      const [cls, label] = STATUS[m.status] || STATUS.open;
      const sel = h('select.select', { style: { width: '140px', height: '30px' }, onchange: async () => { await post(`/api/plan/milestones/${m.id}`, { status: sel.value }); drawPlan(); } },
        Object.entries(STATUS).map(([k, [, l]]) => h('option', { value: k, selected: m.status === k }, l)));
      const item = h('div.item', h('div', { class: `ico ${m.status === 'done' ? 'good' : m.status === 'doing' ? 'rune' : 'accent'}` }, icon(m.status === 'done' ? 'check' : 'flag')),
        h('div.body', h('div.title', m.title), m.detail ? h('div.small.muted', m.detail) : null,
          h('div.meta', [m.track, m.done_when ? `done when: ${m.done_when}` : null].filter(Boolean).join(' · ')),
          h('div.row.mt-8.wrap', sel, h('button.btn.sm', { disabled: !data.ready, onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'draft', params: { milestone: m.id } }); toast('Drafting first files for this milestone. They appear under Work → Drafts.', 'good', 6000); }) }, icon('filePlus'), 'Draft first files'),
            h('button.btn.sm.ghost', { onclick: async () => { const t = await askText({ title: 'Edit milestone', value: m.title, confirm: 'Save' }); if (t) { await post(`/api/plan/milestones/${m.id}`, { title: t }); drawPlan(); } } }, icon('pencil'), 'Edit'))),
        h('span', { class: `badge ${cls}` }, label));
      commentable(item, 'milestone', m.id, m.title);
      list.append(item);
    }
    planCard.append(list);
    if (plan.first_steps?.length) planCard.append(h('div.label-text.mt-16', 'First steps'), h('ol.small', { style: { paddingLeft: '18px' } }, plan.first_steps.map((s) => h('li', s))));
    if (plan.questions?.length) planCard.append(h('div.callout.accent.mt-16', icon('info'), h('div', h('b', 'The Planner asks you'), h('ul.small', { style: { paddingLeft: '18px', margin: '6px 0 0' } }, plan.questions.map((q) => h('li', q))),
      h('div.tiny.faint', 'Answer by commenting on the plan (the comment button on this card) or by editing the brief; the next draft reads both.'))));
  };

  left.append(goalsCard, briefCard);
  right.append(planCard);
  await Promise.all([drawGoals(), drawBrief(), drawPlan()]);
  offs.push(bus.on('plan', debounce(drawPlan, 300)), bus.on('goals', debounce(drawGoals, 300)), bus.on('job', (j) => { if (j.kind === 'plan' || j.kind === 'draft') drawPlan(); }));
  return () => offs.forEach((f) => f());
}
