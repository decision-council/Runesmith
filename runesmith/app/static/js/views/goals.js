// Goals & plan: what the owner wants, in their words; the brief and blueprints; the plan the Planner drafts.
import { h, icon, get, post, del, bus, toast, commentable, openNotes, clear, ago, plural, humanize, withBusy,
  confirmDialog, askText, drawer, empty, debounce, modal } from '../core.js';

// A milestone in the owner's words: what it should do and when it is done, not only a title. Checkers and builders
// read all three; an owner's own milestone used to get a title and nothing else (journey J11-G7).
// Save a milestone; a refusal is said and the form opens again with what was typed (journey J11-F19: after a
// restart the session was stale, the dialog closed with nothing said, and the owner's text was lost).
async function saveMilestone(heading, url, start, redraw, others = []) {
  let values = start;
  for (;;) {
    const f = await milestoneForm(heading, values, others);
    if (!f) return;
    try { await post(url, f); redraw(); return; }
    catch (error) { toast(`Not saved: ${error.message}`, 'bad', 8000); values = { ...f, depends_on: f.depends_on ?? start.depends_on }; }
  }
}

// What Runesmith keeps of each field (workspace MILESTONE_LIMITS); longer text is refused, never cut (J11-F22).
const LIMITS = { title: 200, detail: 1500, done_when: 400 };
const counted = (field, limit) => {
  const count = h('span.tiny.muted', { 'aria-live': 'polite' });
  const show = () => { const n = [...field.value.trim()].length;          // characters as the Studio counts them
    count.textContent = `${n.toLocaleString()} of ${limit.toLocaleString()} characters${n > limit ? ': too long, shorten it' : ''}`;
    count.className = n > limit ? 'tiny warn' : 'tiny muted'; };
  field.addEventListener('input', show); show();
  return count;
};

// "Needs first" (journey J11-G41): a plan loaded at once waits on its prerequisites, which only breakdown steps could name.
function milestoneForm(heading, m = {}, others = []) {
  return new Promise((resolve) => {
    const title = h('input.input', { value: m.title || '', placeholder: 'e.g. A first page that lists tasks', 'aria-label': 'Title' });
    const detail = h('textarea.textarea', { rows: 3, placeholder: 'What it should do, in your own words (optional)', 'aria-label': 'What it should do' }, m.detail || '');
    const done = h('textarea.textarea', { rows: 2, placeholder: 'e.g. Opening the page shows the list (optional)', 'aria-label': 'Done when' }, m.done_when || '');
    const wanted = new Set(m.depends_on || []);
    const needs = h('select.select', { multiple: true, size: Math.min(6, Math.max(2, others.length)), 'aria-label': 'Needs first' },
      others.map((o) => h('option', { value: o.id, selected: wanted.has(o.id) }, `${o.title} (${(STATUS[o.status] || STATUS.open)[1]})`)));
    const body = (close) => {
      if (!title.value.trim()) return close(null);
      const out = { title: title.value.trim(), detail: detail.value.trim(), done_when: done.value.trim() };
      // Sent only when the choice changed, so a save of the words alone never touches what the milestone waits for.
      const chosen = [...needs.selectedOptions].map((o) => o.value);
      const before = [...wanted].filter((id) => others.some((o) => o.id === id));
      if (chosen.length !== before.length || !chosen.every((id) => before.includes(id))) out.depends_on = chosen;
      close(out);
    };
    modal({ title: heading, body: h('div.col.gap-8', h('label.col', h('span.small', 'Title'), title, counted(title, LIMITS.title)),
      h('label.col', h('span.small', 'What it should do'), detail, counted(detail, LIMITS.detail)),
      h('label.col', h('span.small', 'Done when'), done, counted(done, LIMITS.done_when)),
      others.length ? h('label.col', h('span.small', 'Needs first'), needs,
        h('span.tiny.muted', 'Optional. It waits until these are done or dropped. Hold Ctrl (or Cmd) to choose several.')) : null),
      onClose: (v) => resolve(v || null),
      actions: [{ label: 'Cancel', kind: 'ghost', value: null }, { label: 'Save', kind: 'primary', onClick: body }] });
  });
}

const STATUS ={ open: ['', 'open'], doing: ['rune', 'in progress'], done: ['good', 'done'], dropped: ['', 'dropped'] };
// Exact text a check's code requires that its sentence does not say (found by Runesmith, not by the model).
const exactText = (c) => c.unstated?.length
  ? h('div.tiny.warn', 'Also requires the exact text: ' + c.unstated.map((x) => `“${x}”`).join(', '))
  : c.exact ? h('details.tiny', h('summary', 'What exactly is checked'), h('div.muted', c.exact)) : null;
// A check that hands the program a file nothing creates fails even on a correct build (journey J11-G10).
const missingNote = (c) => c.missing_input?.length
  ? h('div.tiny.warn', 'Uses ' + c.missing_input.map((x) => `“${x}”`).join(', ') + ', a file nothing creates, so it fails even on a correct build unless the build adds that file.')
  : null;
// A check that already passed on today's project, while others failed (journey J1-G2).
const todayNote = (c) => c.passes_today
  ? h('div.tiny.warn', 'Already passes on your project today, so it may not test what this milestone adds.') : null;
// Examples-style proposals: texts Runesmith removed because the milestone never states them, and what no check covers.
const examplesNotes = (p) => [
  p.dropped?.length ? h('div.small.mt-8', h('b', 'Runesmith loosened or removed wording your milestone does not state, so a correct build is not rejected for it:'),
    h('ul.small', p.dropped.map((d) => h('li', d)))) : null,
  p.not_checked?.length ? h('div.small.mt-8', h('b', 'Not checked automatically; judge these yourself when you try the result:'),
    h('ul.small', p.not_checked.map((d) => h('li', d)))) : null];

function editInterfaces(milestone, contract, reload) {
  // Freeze the reviewed revision even if a plan event refreshes behind this drawer.
  const expectedDigest = contract?.digest ?? null;
  const rows = structuredClone(contract?.interfaces || []);
  drawer({title:'Public JSON response interfaces', sub:'Shown to authors · changes invalidate old verification, not spent budgets', render(body, close) {
    body.append(h('p.small.muted', 'Declare the output names and types before asking a model to build. These declarations do not execute a command, create tests, or prove that an implementation conforms. Never paste private fixture literals. Object fields are flat; array fields describe each returned object.'));
    const list=h('div');
    const field=(label,input)=>h('label.field',h('span',label),input);
    const input=(row,key,label)=>h('input.input',{value:row[key]||'', 'aria-label':label,oninput:e=>row[key]=e.target.value});
    const draw=()=>{clear(list);rows.forEach((row,index)=>{
      const card=h('div.card.flat.mt-12');
      const fields=h('div');
      card.append(field('Interface ID',input(row,'id',`Interface ${index+1} ID`)),
        field('Command or API invocation',input(row,'invocation',`Interface ${index+1} invocation`)),
        field('Public criterion IDs (comma separated)',h('input.input',{value:row.criterion_ids.join(', '),
          'aria-label':`Interface ${index+1} criteria`,oninput:e=>row.criterion_ids=e.target.value.split(',').map(v=>v.trim()).filter(Boolean)})),
        field('Response',h('select.input',{'aria-label':`Interface ${index+1} response`,onchange:e=>row.response_type=e.target.value},
          ['object','array'].map(type=>h('option',{value:type,selected:row.response_type===type},type==='array'?'Array of objects':'Object')))),
        field('Meaning and error behavior',input(row,'description',`Interface ${index+1} description`)));
      row.fields.forEach((f,j)=>{
        const prefix=`Interface ${index+1} field ${j+1}`;
        fields.append(h('div.card.flat.mt-8',field('Field name',input(f,'name',prefix+' name')),
          field('Type',h('select.input',{'aria-label':prefix+' type',onchange:e=>f.type=e.target.value},
            ['string','integer','number','boolean','object','array'].map(type=>h('option',{value:type,selected:f.type===type},type)))),
          h('label.row',h('input',{type:'checkbox',checked:f.required,'aria-label':prefix+' required',onchange:e=>f.required=e.target.checked}),'Required'),
          h('label.row',h('input',{type:'checkbox',checked:f.nullable,'aria-label':prefix+' nullable',onchange:e=>f.nullable=e.target.checked}),'May be null'),
          field('Unit (optional)',input(f,'unit',prefix+' unit')),
          field('Meaning and constraints',input(f,'description',prefix+' description')),
          h('button.btn.sm.ghost',{onclick:()=>{row.fields.splice(j,1);draw();}},'Remove field')));
      });
      card.append(fields,h('div.row.wrap.mt-8',h('button.btn.sm',{onclick:()=>{
        row.fields.push({name:'',type:'string',required:true,nullable:false,unit:'',description:''});draw();}},'Add response field'),
        h('button.btn.sm.ghost',{onclick:()=>{rows.splice(index,1);draw();}},'Remove interface')));list.append(card);
    });};
    const reason=h('textarea.textarea',{rows:2,'aria-label':'Interface revision reason',placeholder:'What was clarified, and why?'});
    body.append(list,h('button.btn.mt-12',{onclick:()=>{rows.push({id:'',invocation:'',description:'',criterion_ids:[],response_type:'object',fields:[]});draw();}},'Add public interface'),
      field('Revision reason',reason),h('div.row.wrap.mt-12',h('button.btn.primary',{onclick:e=>withBusy(e.currentTarget,async()=>{
        if(!contract?.criteria?.length){toast('Publish public acceptance criteria first.','warn');return;}
        if(!reason.value.trim()){toast('Explain this interface revision.','warn');return;}
        await post(`/api/plan/milestones/${milestone.id}/expectations`,{criteria:contract.criteria,interfaces:rows,
          expected_digest:expectedDigest,reason:reason.value});close();await reload();toast('Public interfaces published. No call, test, apply or budget reset.','good');
      })},'Publish response interfaces'),h('button.btn.ghost',{onclick:close},'Cancel')));draw();
  }});
}

async function showAuthorContext() {
  const data = await get('/api/author-context');
  drawer({title: 'Author context', sub: 'Workspace-wide source selection for future build requests', render(body, close) {
    const paths = h('textarea.textarea.mono', {rows: 5, value: data.focus.paths.join('\n'),
      placeholder: 'One exact relative file path per line', 'aria-label': 'Prioritized source files'});
    const reason = h('input.input', {value: '', placeholder: 'Why does the author need these files?', 'aria-label': 'Context selection reason'});
    const search = h('input.input', {placeholder: 'Filter file paths', 'aria-label': 'Filter source inventory'});
    const rows = h('div.list.mt-8');
    const draw = () => {
      const matches = data.rows.filter(r => r.path.toLowerCase().includes(search.value.toLowerCase()));
      // A file over its limit is shown in parts (journey J11-B15): say so, and which lines, for the next step.
      const shown = r => r.in_parts ? `shown in parts: lines ${r.ranges.map(([a, b]) => a === b ? a : `${a}–${b}`).join(', ')} of ${r.lines}`
        : r.included ? 'included' : 'omitted: ' + r.reason;
      clear(rows).append(...matches.slice(0, 100).map(r => h('div.item', h('div.body',
        h('div.mono.small', r.path), h('div.tiny.muted',
          `${r.bytes} bytes · ${shown(r)}${r.focused ? ' · prioritized' : ''}`)))));
      if (matches.length > 100) rows.append(h('p.tiny.muted', `Showing 100 of ${matches.length} matches; narrow the filter.`));
    };
    search.addEventListener('input', draw);
    body.append(...[h('p.small', `${data.included_count} files included${data.parts_count ? ` (${data.parts_count} in parts)` : ''}; ${data.omitted_count} omitted. Source text uses ${data.used_chars} / ${data.budget_chars} characters. This excludes prompt instructions and retained candidate text.`),
      h('p.tiny.muted', `Prioritize up to ${data.max_focus_paths} files. Other files over ${data.normal_file_bytes} bytes are still shown, up to the same size, when the source budget has room after the rest. Total source budget stays fixed. Empty the list to restore default selection.`),
      // A file over its limit, or one the budget cannot hold whole, is shown in parts rather than not at all (J11-B15).
      h('p.tiny.muted', `A file over ${data.focused_file_bytes} bytes, or one the budget cannot hold whole, is shown in parts: an outline of its declarations and the lines the step is about${data.parts_for ? ` (here for “${data.parts_for.title}”)` : ''}. A change to such a file uses exact edits copied from those lines.`),
      data.settings_error ? h('p.callout.warn', data.settings_error) : null,
      // Each file by name, with what to do (review of J11-B15: a prioritized file that outgrew the limit was only "some files").
      Object.keys(data.focus_errors).length ? h('p.callout.warn', 'Prioritized files that models cannot be shown: '
        + Object.entries(data.focus_errors).map(([file, why]) => `${file} ` + ({
          not_model_visible: 'is gone or hidden: take it out of the list.',
          file_limit: `is too large to draft, or has lines too long to show even in parts: split it, then take it out of the list.`,
          not_utf8: 'is not UTF-8 text: save it as UTF-8, or take it out of the list.',
          packet_budget: `does not fit the ${data.budget_chars}-character budget with the other prioritized files: take one out.`,
        }[why] || `cannot be shown (${why}).`)).join(' ')) : null,
      data.truncated_inventory ? h('p.callout.warn', 'Inventory display is bounded; not every file is listed.') : null,
      paths, reason, h('button.btn.primary.mt-8', {onclick: e => withBusy(e.currentTarget, async () => {
        const selected = paths.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
        await post('/api/author-context', {paths: selected, reason: reason.value, snapshot_digest: data.snapshot_digest});
        toast('Future source selection saved. No model call, project write or permission change.'); close();
      })}, icon('check'), 'Save future context'),
      h('p.tiny.muted', 'Existing requests keep their original inputs. Full-source verification and owner acceptance are unchanged. This does not authorize editing the selected files.'),
      search, rows].filter(Boolean));
    draw();
  }});
}

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
  root.classList.add('goals-page');
  const offs = [];
  const head = h('div.page-head', h('div', h('h2', 'Goals & plan'),
    h('p', 'Tell Runesmith what matters in your own words. Say as much or as little as you like: a sentence, a brief, or whole blueprint documents from this folder. The Planner turns it into milestones on named tracks, and can write first files for any milestone as a draft you review.')));
  const left = h('div.col.gap-16'), right = h('div.col.gap-16');
  root.append(head, h('div.grid.two', left, right));
  head.append(h('button.btn', {onclick: () => ctx.navigate('mission')}, icon('sliders'), 'Modes & measurements'));

  // ---- goals
  const goalsCard = h('div.card');
  const drawGoals = async () => {
    const goals = await get('/api/goals');
    const input = h('input.input', { 'aria-label': 'New goal', placeholder: 'A goal, e.g. “Every test passes” or “Launch the booking page by Friday”' });
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
    save.addEventListener('click', () => withBusy(save, async () => { await post('/api/brief', { text: ta.value, blueprints: [...chosen] }); status.textContent = 'saved just now'; toast(chosen.size ? 'Saved. A model reads the brief and the ticked documents from now on.' : 'Brief saved. The Planner reads it next time.', 'good'); drawBrief(); drawPlan(); drawGoalposts(); }));
    // Documents never go to a model unless ticked here (code does, as source). A folder of documents therefore cannot
    // be planned, drafted or checked by a model until the owner chooses what it may read (journey J4-G2).
    const objects = ctx.app?.state?.objects || [];
    const onlyDocuments = objects.length > 0 && objects.every((o) => o.kind === 'document_collection');
    const none = onlyDocuments && b.candidates.length && !chosen.size ? h('div.callout.warn.mt-8', icon('alert'), h('div',
      'This folder holds documents, and a model reads only the ones you tick. Until you tick some, Runesmith can map and check links, but a model cannot plan, draft or check changes to them.',
      h('div.mt-8', h('button.btn.sm', { onclick: () => { for (const input of picks.querySelectorAll('input[type=checkbox]')) input.checked = true;
        b.candidates.forEach((c) => chosen.add(c.path)); } }, icon('check'), 'Tick all, then save')))) : null;
    clear(briefCard).append(...[h('div.card-head', h('h3', icon('book'), 'Brief'), h('div.actions', status)), ta,
      h('div.label-text.mt-16', 'Documents a model may read'), none, picks,
      h('div.row.mt-16', h('span.tiny.faint', 'Only the documents you tick are sent to a model: for planning, drafting and checking, up to 12,000 characters.'), h('span.spacer'), save)].filter(Boolean));
    commentable(briefCard, 'brief', 'current', 'the brief');
  };

  // ---- plan
  const planCard = h('div.card');
  const drawPlan = async () => {
    const data = await get('/api/plan');
    const plan = data.plan;
    const planningBlocks=data.planning_blockers||[];
    const draftBtn = h('button.btn.primary', { disabled: !data.ready||planningBlocks.length>0, title: planningBlocks.join(' ')||(data.ready ? '' : 'Add a model under Thinking power first') }, icon('wand'), plan ? 'Redraft the plan' : 'Draft a plan');
    draftBtn.addEventListener('click', () => withBusy(draftBtn, async () => {
      if (plan && !(await confirmDialog({ title: 'Redraft the plan?', text: 'The Planner writes a new version from your brief, goals, blueprints, notes and the map. Finished milestones, and any with your checks or drafts, stay exactly as they are: it plans only what is still to do. The current version is kept in the home’s plans/ folder.', confirm: 'Redraft' }))) return;
      await post('/api/worker/run', { job: 'plan' }); toast('The Planner is drafting. This page updates when it is done.', 'good', 6000);
    }));
    clear(planCard).append(h('div.card-head', h('h3', icon('route'), 'Plan'), plan ? h('span.badge', `v${plan.version} · ${plan.drafted_by || 'owner'} · ${ago(plan.utc)}`) : null,
      h('div.actions', h('button.btn.sm', {onclick: e => withBusy(e.currentTarget, showAuthorContext)}, icon('eye'), 'Author context'), h('button.btn.sm', { onclick: () => saveMilestone('Add a milestone', '/api/plan/milestones', {}, drawPlan, plan?.milestones || []) }, icon('plus'), 'Milestone'), draftBtn)));
    if(planningBlocks.length)planCard.append(h('div.callout.warn',h('div',planningBlocks.join(' '),
      h('div.row.wrap.mt-8',
        data.autonomy==='observe' ? h('button.btn.sm.primary',{onclick:(e)=>withBusy(e.currentTarget,async()=>{
          if(!(await confirmDialog({title:'Let Runesmith plan and draft?',confirm:'Let it help',icon:'wand',
            text:'Runesmith will ask a model to plan and draft, and will propose changes for you to review. It still changes no file on its own unless you allow automatic apply. You can go back to just looking in Settings.'})))return;
          await post('/api/settings',{autonomy:'propose'});toast('Runesmith may now plan and draft; you review every change.','good');drawPlan();})},icon('wand'),'Let Runesmith plan and draft') : null,
        planningBlocks.length>(data.autonomy==='observe'?1:0) ? h('button.btn.sm',{onclick:()=>ctx.navigate('mission')},'Review planning controls') : null))));
    for(const held of data.held_plans||[])planCard.append(h('details.mt-8',
      h('summary.small',`Returned plan held — ${held.author||'author not recorded'} · ${held.utc}`),
      h('p.small',held.reason),h('p.small',held.answer?.summary||'No summary returned.'),
      h('p.tiny.muted','Not installed. Review the retained answer and current inputs before deliberately drafting again. No automatic author retry.'),
      h('pre.code',JSON.stringify(held.answer,null,2))));
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
    if(plan.purpose_origin?.kind)planCard.append(h('p.small.muted',`Purpose origin: ${plan.purpose_origin.kind}. ${plan.purpose_origin.kind==='inferred'?'Inferred suggestions are not owner-approved requirements; disabling inference does not change this provenance.':'Explicit owner inputs guided the model; this is not evidence of completion.'}`));
    if (plan.tracks?.length) planCard.append(h('div.pillbox.mb-8', plan.tracks.map((t) => h('span.badge.violet', { title: t.purpose }, t.name))));
    const byId = new Map(plan.milestones.map((m) => [m.id, m]));
    const parentsWithChildren = new Set(plan.milestones.map((m) => m.parent_id).filter(Boolean));
    const breakdownDepth = (milestone) => {
      let depth = 0, current = milestone, seen = new Set();
      while (current?.parent_id && !seen.has(current.id)) {
        seen.add(current.id); depth += 1; current = byId.get(current.parent_id);
      }
      return depth;
    };
    const list = h('div.list');
    for (const m of plan.milestones) {
      const [cls, label] = STATUS[m.status] || STATUS.open;
      const readiness = data.readiness?.[m.id];
      const sel = h('select.select', { style: { width: '140px', height: '30px' }, onchange: async () => { await post(`/api/plan/milestones/${m.id}`, { status: sel.value }); drawPlan(); } },
        Object.entries(STATUS).map(([k, [, l]]) => h('option', { value: k, selected: m.status === k }, l)));
      const item = h('div.item', h('div', { class: `ico ${m.status === 'done' ? 'good' : m.status === 'doing' ? 'rune' : 'accent'}` }, icon(m.status === 'done' ? 'check' : 'flag')),
        h('div.body', h('div.title', m.title), m.detail ? h('div.small.muted', m.detail) : null,
          h('div.meta', [m.track, m.done_when ? `done when: ${m.done_when}` : null].filter(Boolean).join(' · ')),
          m.parent_id ? h('div.tiny.faint', `Prerequisite of ${m.parent_id} · authored by ${m.drafted_by || 'model'}`) : null,
          readiness?.unmet.length ? h('div.tiny.warn', `Waiting for: ${readiness.unmet.map(p => `${p.title} (${p.status})`).join('; ')}`) : readiness?.ready ? h('div.tiny.good', 'Prerequisites satisfied — ready to draft') : null,
          h('div.row.mt-8.wrap', sel, h('button.btn.sm', { disabled: !data.ready || !readiness?.ready, onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'draft', params: { milestone: m.id } }); toast('Drafting first files for this milestone. They appear under Work → Drafts.', 'good', 6000); }) }, icon('filePlus'), 'Draft first files'),
            ['open','doing'].includes(m.status) && (m.depends_on || []).every(id=>['done','dropped'].includes(byId.get(id)?.status)) ? h('button.btn.sm',{
              onclick:(e)=>withBusy(e.currentTarget,async()=>{
                await post('/api/worker/run',{job:'review_current',params:{milestone:m.id}});
                toast('Checking current files against the milestone. No model call, source edits or automatic completion.','good',7000);
              })},icon('check'),'Check current files') : null,
            ['open','doing'].includes(m.status) && !parentsWithChildren.has(m.id) && breakdownDepth(m) < 2 ? h('button.btn.sm', {
              disabled:!data.ready, onclick:(e)=>withBusy(e.currentTarget,async()=>{
                await post('/api/worker/run',{job:'breakdown',params:{milestone:m.id}});
                toast('Runesmith is proposing smaller prerequisites from the evidence. The goal stays unchanged.','good',6000);
              })},icon('route'),'Propose smaller steps') : null,
            h('button.btn.sm.ghost', { onclick: () => saveMilestone('Edit milestone', `/api/plan/milestones/${m.id}`, m, drawPlan, plan.milestones.filter((o) => o.id !== m.id)) }, icon('pencil'), 'Edit'))),
        h('span', { class: `badge ${cls}` }, label));
      // Acceptance checks the owner approves in plain words: automatic apply for this milestone is judged by them.
      const acc = data.acceptance_checks?.[m.id];
      const accBlock = h('div.mt-8', {'aria-label': `Acceptance checks for ${m.title}`});
      if (acc?.approved) {
        // Element.append would print a null part as the word "null"; empty parts are dropped.
        accBlock.append(...[h('b.small', '✓ Your acceptance checks'),
          h('div.tiny.muted', acc.approved.provenance === 'owner file' ? 'Your own checks file. Automatic apply for this milestone is judged by it.'
            : acc.approved.provenance === 'model-proposed, autopilot-approved'
              ? `Proposed by ${acc.approved.proposed_by || 'a model'}, approved by Runesmith’s check autopilot${acc.approved.autopilot ? ` (${acc.approved.autopilot})` : ''}. Read them; you can replace them at any time.`
              : `Proposed by ${acc.approved.proposed_by || 'a model'}, approved by you. Automatic apply for this milestone is judged by them; builders see only their sentences, never the code.`),
          acc.approved.checks ? h('ul.small', acc.approved.checks.map((c) => h('li', c.says, exactText(c)))) : null,
          !acc.proposal && ['open', 'doing'].includes(m.status) ? h('div.mt-8',
            h('div.tiny.muted', 'If a build that looks right fails these checks, the checks may be wrong. Ask for new ones: you read them and decide whether they replace these.'),
            h('button.btn.sm.mt-8', { disabled: !data.ready, onclick: (e) => withBusy(e.currentTarget, async () => {
              await post('/api/worker/run', { job: 'propose_acceptance', params: { milestone: m.id } });
              toast('Asking for new acceptance checks. They appear here next to yours; nothing changes until you choose.', 'good', 6000); }) },
              icon('refresh'), 'Ask for new checks')) : null,
          // Journey J11-G37: wrong approved checks could only be replaced, never taken back with a reason. A done milestone's
          // checks too: a later milestone may change what they required (J11-F29), and they keep judging every build. A
          // dropped milestone's too: its checks judge nothing while it is dropped, but they do after a reopen, and their
          // sentences still reach the other milestones' Checkers; J11 holds milestones dropped until their wrong checks
          // can be withdrawn, then reopens them.
          !acc.proposal && acc.approved.provenance !== 'owner file' ? h('div.mt-8', h('button.btn.sm.ghost', { onclick: async (e) => {
              const button = e.currentTarget;      // null after the first await
              const reason = await askText({ title: 'Withdraw these checks?', confirm: 'Withdraw', multiline: true,
                text: 'Say what is wrong with them. They stop judging builds, their file is kept, and the checks written next read your reason.',
                placeholder: 'e.g. the milestone keeps the envelope inside "project"; these checks put it at the top level' });
              if (reason === null) return;          // cancelled
              if (!reason.trim()) { toast('Say what is wrong with the checks; it is kept with them.', 'warn'); return; }
              await withBusy(button, async () => {
                await post(`/api/plan/milestones/${m.id}/acceptance/withdraw`, { reason: reason.trim() });
                // A done or dropped milestone gets no new checks until it is reopened: propose() refuses it. An open one
                // gets them when the owner asks, or at the autopilot's next round (J11-G37 review).
                toast(['done', 'dropped'].includes(m.status) ? `Checks withdrawn. This milestone is ${m.status}: set its status to open to have new checks written with your reason.`
                  : 'Checks withdrawn. Press “Propose acceptance checks” to have new ones written with your reason.', 'good', 6000); drawPlan(); }, 'Withdrawing the checks'); } },
              icon('x'), 'Withdraw these checks')) : null].filter(Boolean));
      }
      if (acc?.proposal) {
        // A proposal next to approved checks replaces them only if the owner says so, with a reason.
        const replacing = Boolean(acc.approved);
        const p = acc.proposal;
        // A trial run on today's project: checks that already pass may not test what an unbuilt milestone adds.
        const dry = p.dry_run || {};
        const missing = p.checks.some((c) => c.missing_input?.length);
        const trial = dry.verdict === 'passes_now'
          ? h('div.callout.warn.mt-8', h('div', 'These checks already pass on your project as it is today. If this milestone is not built yet, they may not test what it adds. ' + (p.revision && !p.revision.error
              ? 'Runesmith already asked for a revision once. You can discard them and ask again, choose a stronger model for planning under Thinking power, or propose smaller steps for this milestone.'
              : 'Consider discarding them and asking again.')))
          : dry.verdict === 'broken'
            ? h('div.callout.warn.mt-8', h('div', 'These checks could not run on your project as it is today, so they may be broken. Consider discarding them and asking again.'))
            : dry.verdict === 'fails_now'
              ? h('div.tiny.muted', `Tried on your project as it is today: ${dry.failures + dry.errors} of ${dry.ran} fail` + (missing
                ? '. The checks that use a file nothing creates (shown under them) would fail on a correct build too.'   // J11-F10
                : ', as expected before the milestone is built.'))
              : dry.why ? h('div.tiny.muted', dry.why) : null;
        const firstTry = { broken: 'could not run', passes_now: 'already passed on today’s project', unstated_text: 'required exact text their sentences did not say', missing_input: 'used a file nothing creates',
          unusable: 'broke a rule of the examples format' }[p.revision?.after] || 'needed work';
        // For a broken examples answer the saved error is the first answer's, and the revision worked (journey J11-F4).
        const fixed = p.revision?.after === 'unusable';
        const revised = p.revision && h('div.tiny.muted', p.revision.error && !fixed
          ? `The first checks ${firstTry}; asking for a revision did not work (${p.revision.error}).`
          : `Revised once: the first checks ${firstTry}${fixed && p.revision.error ? ` (${p.revision.error})` : ''}.`);
        const unstated = p.checks.some((c) => c.unstated?.length);
        // New checks can read the same as the approved ones and differ only in what is checked exactly (J11-F9).
        const yours = new Map((acc.approved?.checks || []).map((c) => [c.says, c.exact]));
        const differs = (c) => replacing && yours.has(c.says) && yours.get(c.says) !== c.exact
          ? h('div.tiny.muted', 'Reads the same as one of yours but is checked differently: compare “What exactly is checked” under each.')
          : null;
        accBlock.append(...[h('b.small', replacing ? 'New checks proposed to replace yours: do these describe “done” better?' : 'Proposed acceptance checks: do these describe “done”?'),
          h('ul.small', p.checks.map((c) => h('li', c.says, exactText(c), todayNote(c), missingNote(c), differs(c)))),
          p.assumes?.length ? h('div.small.mt-8', h('b', 'They assume (your milestone does not say this):'), h('ul.small', p.assumes.map((a) => h('li', a)))) : null,
          ...examplesNotes(p),
          trial, revised,
          p.autopilot?.decision === 'left_for_owner' ? h('div.callout.mt-8', h('div', `Runesmith’s check autopilot left these for you: ${p.autopilot.reason}`)) : null,
          h('details', h('summary.tiny', p.style === 'examples' ? `Show the code (examples by ${p.drafted_by || 'a model'}, code written by Runesmith)`
            : `Show the code (proposed by ${p.drafted_by || 'a model'})`), h('pre.code', p.code)),
          h('div.row.wrap.mt-8',
            h('button.btn.sm.primary', { onclick: (e) => withBusy(e.currentTarget, async () => {
              if (replacing) {
                const reason = await askText({ title: `Replace your checks for “${m.title}”?`, multiline: true, confirm: 'Replace my checks',
                  text: 'Say why, for example “a correct build failed the old checks”. Your current checks are kept in a file, and the new sentences become the milestone’s public expectations.' });
                if (reason === null) return;
                if (!reason.trim()) { toast('Say why the checks are replaced; it is kept with them.', 'warn'); return; }
                await post(`/api/plan/milestones/${m.id}/acceptance/approve`, { proposal: p.id, replace: true, reason: reason.trim() });
                toast('Your checks were replaced. The old ones are kept.', 'good'); drawPlan(); return;
              }
              if (!(await confirmDialog({ title: `Use these checks for “${m.title}”?`,
                text: (dry.verdict === 'passes_now' ? 'Note: they already pass on your project today. ' : '') + (unstated ? 'Some checks require exact text their sentences do not say (shown under them); whoever builds the milestone is told it too. ' : '') + (missing ? 'Some checks use a file nothing creates (shown under them), so they fail until a build adds it. ' : '') + (p.assumes?.length ? 'They also assume what is listed under the checks. ' : '') + 'They decide when this milestone is done. Work is applied automatically only when they pass, and only if you allow automatic apply. Their sentences become the milestone’s public expectations, so whoever builds it knows what “done” means; the code stays private. You can replace them later, with a reason.',
                confirm: 'Use these checks', icon: 'check' }))) return;
              await post(`/api/plan/milestones/${m.id}/acceptance/approve`, { proposal: p.id });
              toast('Acceptance checks saved for this milestone.', 'good'); drawPlan(); }) }, icon('check'), replacing ? 'Replace my checks' : 'Use these checks'),
            h('button.btn.sm.ghost', { onclick: (e) => withBusy(e.currentTarget, async () => {
              const reason = await askText({ title: 'Discard these checks?', text: 'Optional: say why. It is kept with the proposal.', multiline: true, confirm: 'Discard' });
              if (reason === null) return;
              await post(`/api/plan/milestones/${m.id}/acceptance/discard`, { proposal: p.id, reason }); drawPlan(); }) }, icon('x'), 'Discard'))].filter(Boolean));
      } else if (!acc?.approved && ['open', 'doing'].includes(m.status)) {
        accBlock.append(h('div.small.muted', 'No acceptance checks yet. Automatic apply needs them, and you approve them in plain words.'),
          h('button.btn.sm.mt-8', { disabled: !data.ready, onclick: (e) => withBusy(e.currentTarget, async () => {
            await post('/api/worker/run', { job: 'propose_acceptance', params: { milestone: m.id } });
            toast('Proposing acceptance checks for this milestone. They appear here for you to read and approve.', 'good', 6000); }) },
            icon('check'), 'Propose acceptance checks'));
      }
      if (accBlock.childNodes.length) item.append(accBlock);
      const expectations = data.acceptance_expectations?.[m.id];
      const currentCheck = data.current_checks?.find(c=>c.milestone===m.id);
      if(currentCheck) item.append(h('div.callout.mt-8',h('div',currentCheck.summary,
        h('div.tiny.muted',`${currentCheck.utc} · project ${currentCheck.verification?.project_checks?.status || 'not run'} · owner acceptance ${currentCheck.verification?.acceptance?.status || 'not run'}`),
        h('div.tiny.mono',currentCheck.verification?.evidence_dir || 'No executable receipt'),
        h('div.tiny.muted','Historical check of the recorded snapshot. Review freshness before marking a milestone done.'))));
      // What builders are told (F4: plain words). With approved checks their sentences already show above, so the
      // expert view folds away; without them it stays open.
      const told = h(acc?.approved ? 'details.mt-8' : 'div.mt-8');
      item.append(told);
      told.append(...[acc?.approved ? h('summary.small', 'What builders are told (for experts)') : h('b.small','What builders are told'),
        expectations ? h('div',h('div.tiny.muted',`Version ${expectations.version} · ${expectations.by} · ${expectations.reason}`),
          h('ul.small',expectations.criteria.map(c=>h('li',{title:c.id},c.description)))) : h('div.small.muted','Only the milestone’s own words so far. When you approve acceptance checks, their sentences are added here.'),
        expectations?.interfaces?.length ? h('details.mt-8',h('summary.small',`${expectations.interfaces.length} public JSON response interface(s)`),
          expectations.interfaces.map(row=>h('div.card.flat.mt-8',h('b.small',row.invocation),h('p.tiny',row.description),
            h('p.tiny.muted',`${row.response_type}; criteria: ${row.criterion_ids.join(', ')}`),
            h('ul.small',row.fields.map(f=>h('li',`${f.name}: ${f.type} · ${f.required?'required':'optional'}${f.nullable?' · nullable':''}${f.unit?' · '+f.unit:''} — ${f.description}`)))))) : null,
        h('div.tiny.muted','Builders see these sentences, never the code of your checks. Changing them does not give a builder extra attempts.'),
        h('div.row.wrap.mt-8',h('button.btn.sm.ghost',{onclick:async()=>{
          const value=await askText({title:'Public acceptance criteria',text:'JSON array of {id, description}. Describe behavior, not private fixture values.',
            value:JSON.stringify(expectations?.criteria || [{id:`${m.id}.behavior`,description:m.done_when || ''}],null,2),multiline:true,confirm:'Continue'});
          if(value===null)return;
          let criteria;try{criteria=JSON.parse(value);}catch{toast('Enter a valid JSON array.','warn');return;}
          const reason=await askText({title:'Why clarify this requirement?',text:'The reason and previous revisions are retained; no budget is reset.',confirm:'Publish'});
          if(!reason?.trim())return;
          await post(`/api/plan/milestones/${m.id}/expectations`,{criteria,reason,expected_digest:expectations?.digest ?? null});drawPlan();
        }},icon('pencil'),'Edit (JSON)'),
        h('button.btn.sm.ghost',{disabled:!expectations?.criteria?.length,onclick:()=>editInterfaces(m,expectations,drawPlan)},icon('code'),'JSON response interfaces'))].filter(Boolean));
      commentable(item, 'milestone', m.id, m.title);
      list.append(item);
    }
    planCard.append(list);
    // A breakdown for a milestone that is already done or dropped has nothing left to break down (journey J2-F25).
    const unfinished = new Set((data.plan?.milestones || []).filter((m) => ['open','doing'].includes(m.status)).map((m) => m.id));
    for (const b of (data.breakdowns || []).filter(b=>b.state==='proposed' && unfinished.has(b.milestone))) {
      planCard.append(h('div.card.flat.mt-16',h('h3','Proposed breakdown'),
        h('p.tiny.muted', `${b.milestone} · ${b.drafted_by || 'unknown author'} · awaiting adoption`),
        h('p.small', b.diagnosis), h('p.small.muted', b.coverage),
        h('ol.small', {style:{paddingLeft:'18px'}}, b.steps.map(s=>h('li.mt-8', h('b',s.title),
          h('div',s.detail),h('div.muted',`Done when: ${s.done_when}`),h('div.tiny.mono',s.suggested_paths.join(', '))))),
        h('p.tiny.muted','The parent goal and completed milestones stay intact. Each new step requires its own owner acceptance before delegated application.'),
        h('button.btn.primary',{onclick:(e)=>withBusy(e.currentTarget,async()=>{
          if (!(await confirmDialog({title:'Adopt these prerequisite steps?',text:'This adds the proposed steps before the original milestone without changing its success criterion. Existing drafts may need review against the new plan version. No project files are written.',confirm:'Adopt steps'}))) return;
          await post(`/api/plan/breakdowns/${b.id}/adopt`,{});toast('Prerequisites added; original goal preserved.','good');drawPlan();
        })},icon('check'),'Adopt prerequisites'),
        h('button.btn.ghost',{onclick:(e)=>withBusy(e.currentTarget,async()=>{
          const reason=await askText({title:'Why should this breakdown be reconsidered?',multiline:true,confirm:'Keep feedback'});
          if (!reason?.trim()) return;
          await post(`/api/plan/breakdowns/${b.id}/reject`,{reason});toast('Proposal retained with feedback for the next attempt.');drawPlan();
        })},icon('x'),'Reconsider')));
    }
    const reviews=(data.breakdowns || []).filter(b=>b.state!=='proposed');
    if (reviews.length) planCard.append(h('details.mt-16',h('summary.small','Breakdown history'),reviews.map(b=>
      h('div.card.flat.mt-8',h('b.small',`${b.milestone} · ${b.state}`),
        h('p.tiny.muted',`${b.id} · ${b.drafted_by || 'model'} · reviewed by ${b.reviewed_by || b.adopted_by || 'owner'}`),
        b.rejection_reason ? h('p.small',b.rejection_reason) : h('p.small',`Prerequisites: ${(b.children || []).join(', ')}`),
        h('p.tiny.mono',`Evidence packet: ${b.packet_receipt || 'not recorded'}`)))));
    if (plan.first_steps?.length) planCard.append(h('div.label-text.mt-16', 'First steps'), h('ol.small', { style: { paddingLeft: '18px' } }, plan.first_steps.map((s) => h('li', s))));
    if (plan.assumptions?.length) planCard.append(h('div.callout.warn.mt-16', h('b', 'Planner assumptions — not owner-approved requirements'), h('ul.small', plan.assumptions.map(a => h('li', a)))));
    if (plan.questions?.length) planCard.append(h('div.callout.accent.mt-16', icon('info'), h('div', h('b', 'The Planner asks you'), h('ul.small', { style: { paddingLeft: '18px', margin: '6px 0 0' } }, plan.questions.map((q) => h('li', q))),
      h('div.tiny.faint', 'Answer by commenting on the plan (the comment button on this card) or by editing the brief; the next draft reads both.'))));
  };

  const goalpostsCard = h('div.card');
  const drawGoalposts = async () => {
    const data = await get('/api/goalposts');
    const record = data.goalposts;
    const propose = h('button.btn.sm', {disabled:!data.ready,title:(data.planning_blockers||[]).join(' '), onclick:(e)=>withBusy(e.currentTarget,async()=>{
      await post('/api/worker/run', {job:'goalposts'});
      toast('Runesmith is proposing measurable targets. Existing plans and owner goals stay unchanged.', 'good', 6000);
    })}, icon('wand'), record ? 'Reassess goalposts' : 'Propose goalposts');
    clear(goalpostsCard).append(h('div.card-head', h('h3', icon('target'), 'Runesmith’s goalposts'), propose),
      h('p.small.muted', 'Model-authored targets, not measured achievements. Minimum, good and frontier tiers guide construction and optimization; they do not replace owner acceptance.' ));
    if(data.planning_blockers?.length)goalpostsCard.append(h('p.small.warn',data.planning_blockers.join(' ')));
    if (!record) { goalpostsCard.append(h('p.small.faint', 'No proposed goalposts yet. Give Runesmith your purpose and observations, then ask it to define useful measures.')); return; }
    goalpostsCard.append(h('p.tiny.faint', `v${record.version} · ${record.drafted_by || 'unknown author'} · ${ago(record.utc)}`),
      h('p.small', record.summary));
    const list = h('div.list');
    for (const g of record.goalposts) {
      list.append(h('div.item', h('div.body', h('div.title', g.title),
        h('div.meta', `${g.tier} · proposed · ${g.milestone_ids.join(', ') || 'future direction'}`),
        h('div.small.mt-8', h('b', 'Measure: '), g.measurement),
        h('div.small', h('b', 'Target: '), g.target),
        h('div.small', h('b', 'Scenario: '), g.scenario || 'not yet specified'),
        h('div.small', h('b', 'Window: '), g.window || 'not yet specified'),
        h('div.small.muted', g.why),
        h('div.small.mt-8', h('b', 'Next check: '), g.next_check),
        h('div.tiny.faint', `Basis in supplied context: ${g.evidence_refs.join(', ') || 'new hypothesis; no evidence cited'}`))));
    }
    goalpostsCard.append(list);
  };

  const buildCard = h('div.card');
  // Unsaved changes survive the redraws a running job causes (journey J2-F19: a switch turned off mid-build was
  // silently switched back when the job finished, before the owner pressed Save).
  let buildDirty = false;
  const drawBuild = async (options) => {
    if (buildDirty && options?.force !== true) return;
    const [settings, build] = await Promise.all([get('/api/settings'), get('/api/build')]);
    const checks = h('input', {type:'checkbox', checked:settings.build_steps});
    const apply = h('input', {type:'checkbox', checked:build.apply});
    const autopilot = h('input', {type:'checkbox', checked:Boolean(settings.checks_autopilot)});
    const paths = h('input.input.mono', {value:(settings.build_paths || []).join(', '), 'aria-label':'Allowed files or folders', placeholder:'for example: src, tests, docs (or . for the whole folder)'});
    const save = h('button.btn', {onclick: () => withBusy(save, async () => {
      const chosen = paths.value.split(',').map(x=>x.trim()).filter(Boolean);
      // The dialog names what may be written, and a grant with nothing in it is not offered (journey J11-F3).
      const where = chosen.some((p) => p === '.' || p === './') ? 'anywhere in this folder (never in Runesmith’s own records or .git)' : `only in: ${chosen.join(', ')}`;
      if (apply.checked && !chosen.length) { toast('Name the files or folders Runesmith may write first, for example: src, tests. A . means the whole folder.', 'warn', 8000); return; }
      if (apply.checked && !build.apply && !(await confirmDialog({title:'Apply checked drafts automatically in this folder?',
        text:`Runesmith may then write ${where}. It writes only when a draft passes both its own tests and your acceptance checks for the milestone. You can turn this off here at any time; backups and Undo stay available.`,confirm:'Allow automatic apply'}))) return;
      if (autopilot.checked && !settings.checks_autopilot && !(await confirmDialog({title:'Let Runesmith approve checks itself?',
        text:'Runesmith then asks for acceptance checks for ready milestones and approves them only when they pass every test: tried on your project, no problems it found itself, and a second model working out the same expected values. Otherwise it turns them down with the reason and asks again, twice at most, then leaves them for you. Checks you approved are never replaced by it. You can read and replace any of its checks.',
        confirm:'Turn on the check autopilot'}))) return;
      await post('/api/settings', {build_steps:checks.checked, build_apply:apply.checked, build_paths:chosen, checks_autopilot:autopilot.checked});
      toast('Build settings saved for this folder.', 'good'); buildDirty = false; drawBuild({ force: true });
    })}, 'Save build settings');
    const unsaved = h('span.small.warn', 'Not saved yet: press Save build settings.');
    const markDirty = () => { buildDirty = true; save.classList.add('primary'); if (!unsaved.isConnected) save.after(unsaved); };
    checks.addEventListener('change', markDirty); apply.addEventListener('change', markDirty); paths.addEventListener('input', markDirty);
    autopilot.addEventListener('change', markDirty);
    clear(buildCard).append(...[h('h3', icon('hammer'), 'Build continuation'),
      h('p.small.muted', 'Builds the next milestone from your project as it is now. By default you review each draft yourself. Automatic apply needs your acceptance checks to pass, not only the draft’s own tests, and nothing may have changed in the meantime.'),
      h('label.row', checks, 'Check drafts on a throwaway copy before they are written (the project’s own tests, if it has any, and your acceptance checks)'),
      h('label.row.mt-8', apply, 'Apply checked drafts automatically (needs your own acceptance checks for the milestone)'),
      h('label.row.mt-8', autopilot, 'Let Runesmith approve acceptance checks that pass every test (check autopilot)'),
      h('div.label-text.mt-8', 'Allowed files or folders, comma separated'), paths,
      h('p.small.muted', 'Automatic apply needs acceptance checks for each milestone. Use “Propose acceptance checks” on a milestone above and approve them in plain words; nothing is applied automatically without them.'),
      h('p.tiny.faint', `Owner acceptance files: ${build.acceptance_folder} / <milestone-id>.py (unittest). Working copies are not an OS sandbox.`),
      h('div.row.wrap', save, h('button.btn.primary', {onclick:async()=>{await post('/api/worker/run',{job:'build'});toast('Build step queued. Follow it under Work.', 'good');}}, icon('play'), 'Build next step')),
      build.last ? h('p.small.mt-8', build.last.summary) : null].filter(Boolean));
  };

  left.append(goalsCard, briefCard);
  right.append(goalpostsCard, planCard, buildCard);
  await Promise.all([drawGoals(), drawBrief(), drawPlan(), drawBuild(), drawGoalposts()]);
  offs.push(bus.on('goalposts', debounce(drawGoalposts, 300)));
  offs.push(bus.on('job', debounce(drawBuild, 300)));
  offs.push(bus.on('mission', debounce(()=>{drawPlan();drawGoalposts();}, 300)));
  offs.push(bus.on('brief', debounce(()=>{drawPlan();drawGoalposts();}, 300)),
    bus.on('settings', debounce(()=>{drawPlan();drawGoalposts();}, 300)),
    bus.on('inference', debounce(()=>{drawPlan();drawGoalposts();}, 300)),
    bus.on('goals', debounce(()=>{drawPlan();drawGoalposts();}, 300)));
  offs.push(bus.on('plan', debounce(drawPlan, 300)), bus.on('goals', debounce(drawGoals, 300)), bus.on('job', (j) => { if (['plan','draft','build','breakdown'].includes(j.kind)) drawPlan(); }));
  return () => {root.classList.remove('goals-page');offs.forEach((f) => f());};
}
