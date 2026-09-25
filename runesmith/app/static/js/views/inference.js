// Thinking power: where Runesmith's thinking comes from. None, a model on this computer, API keys, or a chat window.
import { h, icon, get, post, del, bus, toast, commentable, openNotes, clear, ago, plural, humanize, withBusy, confirmDialog,
  modal, empty, debounce, copyText } from '../core.js';

const MONO_COLORS = { ollama: '#111827', lmstudio: '#4f46e5', llamacpp: '#0f766e', openrouter: '#6d28d9', groq: '#f55036', gemini: '#1a73e8',
  mistral: '#fa520f', deepseek: '#4d6bfe', openai: '#10a37f', anthropic: '#d97757', together: '#0f6fff', custom: '#475569', milliner: '#b45309', manual: '#22d3c5' };
const ROLE_ICON = { repair: 'hammer', kaizen: 'spark', plan: 'wand' };

export default async function render(root, ctx) {
  const offs = [];
  const head = h('div.page-head', h('div', h('h2', 'Thinking power'),
    h('p', 'Runesmith works with any model, weak or strong, and even with none: without a model it maps and watches. Add a model that runs on this computer (free and private), an API key, or simply a chat window you copy and paste into. Keys are saved on this computer only and are never shown again.')),
    h('div.actions', h('button.btn.primary', { onclick: () => addModel() }, icon('plus'), 'Add thinking power')));
  const body = h('div');
  root.append(head, body);
  let data;
  const load = async () => {
    data = await get('/api/inference');
    const relay = await get('/api/manual');
    clear(body);
    const waiting = relay.requests.filter((r) => !r.answered);
    if (waiting.length || ctx.sub[0] === 'relay') body.append(relayPanel(waiting, load), h('div.mt-16'));
    // ---- the three ways
    if (!data.instruments.length) body.append(threeWays(), h('div.mt-16'));
    // ---- instruments
    const inst = h('div.card', h('div.card-head', h('h3', icon('cpu'), 'Your models'), h('span.badge', plural(data.instruments.length, 'model'))));
    if (!data.instruments.length) inst.append(h('p.muted', 'None yet.'));
    for (const i of data.instruments) inst.append(instrumentRow(i, data, load));
    // ---- roles
    const roles = h('div.card', h('div.card-head', h('h3', icon('layers'), 'Who does what'), h('span.badge', 'first = preferred, then fallbacks')));
    for (const role of ['repair', 'kaizen', 'plan']) roles.append(roleLane(role, data, load));
    roles.append(h('p.tiny.faint', 'The Planner borrows the Improver’s (or the Worker’s) model when it has none of its own. A small free model is fine for the Worker; a stronger one pays off for the Improver.'));
    const local = h('div.card', h('div.card-head', h('h3', icon('laptop'), 'On this computer'), h('div.actions', h('button.btn.sm', { onclick: (e) => withBusy(e.currentTarget, () => scan(localList)) }, icon('refresh'), 'Look again'))));
    const localList = h('div');
    local.append(localList);
    scan(localList);
    const keys = h('div.card', h('div.card-head', h('h3', icon('key'), 'Saved keys'), h('span.badge.good', icon('lock'), 'never shown')),
      data.keys.length ? h('div.list', data.keys.map((k) => h('div.item', h('div.ico', icon('key')), h('div.body', h('div.title.mono', k.name), h('div.meta', `saved ${ago(k.saved_utc)} · stored in this folder's .runesmith/secrets.json`)))))
        : h('p.muted', 'No keys saved. Keys stay on this computer, outside your project files, and are sent only to the provider they belong to.'));
    body.append(h('div.grid.two', h('div.col.gap-16', inst, roles), h('div.col.gap-16', local, keys)));
    if (!waiting.length && ctx.sub[0] !== 'relay' && data.instruments.some((i) => i.kind === 'manual')) body.append(h('div.mt-16'), relayPanel([], load));
  };
  const scan = async (box) => {
    clear(box).append(h('div.skeleton', { style: { height: '48px' } }));
    const found = (await get('/api/inference/discover')).found;
    clear(box);
    if (!found.length) {
      box.append(h('p.muted.small', 'No local model server is answering right now. Free options:'),
        h('div.list', [['Ollama', 'ollama.com — then run: ollama pull qwen2.5-coder:7b', 'ollama'], ['LM Studio', 'lmstudio.ai — load a model and start the local server', 'lmstudio'], ['llama.cpp', 'llama-server -m model.gguf (the leanest option)', 'llamacpp']]
          .map(([n, t, p]) => h('div.item', h('div.monogram', { style: { background: MONO_COLORS[p] } }, n.slice(0, 2)), h('div.body', h('div.title', n), h('div.meta.mono', t)), h('button.btn.sm', { onclick: () => addModel(p) }, 'Set up')))));
      return;
    }
    for (const f of found) {
      const p = data.presets.find((x) => x.id === f.preset);
      box.append(h('div.item', h('div.monogram', { style: { background: MONO_COLORS[f.preset] } }, p.label.slice(0, 2)),
        h('div.body', h('div.title', `${p.label} is running`), h('div.meta', f.models.length ? plural(f.models.length, 'model') + ': ' + f.models.slice(0, 4).join(', ') : 'no model loaded yet')),
        f.models.length ? h('button.btn.sm.primary', { onclick: () => addModel(f.preset, { model: f.models[0], models: f.models }) }, icon('plus'), 'Use it') : null));
    }
  };
  // ---- add model wizard
  const addModel = (presetId, extra = {}) => {
    const presets = data.presets;
    let chosen = presets.find((p) => p.id === presetId) || null;
    const body = h('div');
    const m = modal({ title: 'Add thinking power', text: 'Pick where the thinking comes from. You can add several and give each a role.', body, wide: true });
    const step1 = () => {
      clear(body);
      const groups = ['This computer', 'With a key', 'No key needed', 'Advanced'];
      for (const g of groups) {
        const items = presets.filter((p) => p.group === g);
        if (!items.length) continue;
        body.append(h('div.label-text.mt-8', g), h('div.providers.mt-8', items.map((p) => h('div.provider', { onclick: () => { chosen = p; step2(); } },
          h('div.monogram', { style: { background: MONO_COLORS[p.id] || '#475569' } }, p.label.replace(/[^A-Za-z]/g, '').slice(0, 2)),
          h('div', h('b', p.label), h('span', p.blurb))))));
      }
    };
    const step2 = () => {
      clear(body);
      const p = chosen;
      const firstModel = !data.instruments.length;
      const name = h('input.input', { value: uniqueName(p.id, data), placeholder: 'a short name' });
      const model = h('input.input', { value: extra.model || (p.suggested || [])[0] || '', placeholder: p.kind === 'manual' ? 'which chat you will use, e.g. ChatGPT, Claude, Gemini' : 'model id', list: 'rs-models' });
      const dl = h('datalist#rs-models', [...new Set([...(extra.models || []), ...(p.suggested || [])])].map((x) => h('option', { value: x })));
      const base = h('input.input.mono', { value: p.base_url || '', placeholder: 'https://… or http://127.0.0.1:…' });
      const key = h('input.input.mono', { type: 'password', placeholder: p.key === 'required' ? 'paste your key' : 'optional', autocomplete: 'off' });
      const showKey = h('button.btn.icon', { type: 'button', title: 'Show or hide', onclick: () => { key.type = key.type === 'password' ? 'text' : 'password'; } }, icon('eye'));
      // A chat window suits the Improver and Planner (a few calls each); repairs take several calls, so it is off by default.
      const defaultOn = (r) => (p.kind === 'manual' ? r !== 'repair' : firstModel || (r === 'repair' && !data.ready.repair));
      const roleBoxes = ['repair', 'kaizen', 'plan'].map((r) => { const cb = h('input', { type: 'checkbox', checked: defaultOn(r), value: r });
        return { r, cb, el: h('label.chip', cb, icon(ROLE_ICON[r]), data.role_labels[r].split(':')[0]) }; });
      const listBtn = h('button.btn', { type: 'button', onclick: () => withBusy(listBtn, async () => {
        const r = await post('/api/inference/models', { preset: p.id, base_url: base.value, key: key.value });
        if (r.ok && r.models.length) { clear(dl).append(...r.models.map((x) => h('option', { value: x }))); toast(`${r.count} models available; start typing to pick one.`, 'good'); model.focus(); }
        else toast(r.status === 401 ? 'The provider refused the key.' : 'Could not list models (the provider may not support it, or it is not running).', 'warn', 6000);
      }) }, icon('search'), 'List models');
      const fields = [h('div.field', h('label', 'Name'), name, h('span.hint', 'How Runesmith refers to this model.'))];
      if (p.kind !== 'manual') fields.push(h('div.field', h('label', 'Model'), h('div.row', model, listBtn), dl, h('span.hint', 'Any model id the provider serves. Small models work for repairs; stronger ones help self-improvement.')));
      else fields.push(h('div.field', h('label', 'Which chat will you use? (for the record)'), model));
      if (p.id === 'custom' || p.id === 'milliner' || p.local) fields.push(h('div.field', h('label', 'Address'), base));
      if (p.key !== 'none') fields.push(h('div.field', h('label', p.kind === 'milliner' ? 'Agent token' : 'API key'), h('div.row', key, showKey),
        h('span.hint', 'Saved in this folder’s .runesmith/secrets.json, never in your project, never shown again.', p.key_url ? [' ', h('a', { href: p.key_url, target: '_blank', rel: 'noopener' }, 'Get a key')] : null)));
      fields.push(h('div.field', h('label', 'Roles'), h('div.pillbox', roleBoxes.map((x) => x.el)), h('span.hint', 'Worker repairs code · Improver improves Runesmith itself · Planner drafts plans and first files.')));
      if (p.kind === 'manual') fields.push(h('div.callout', icon('chat'), h('div', 'When Runesmith needs an answer, the request appears here and in the top bar. Copy it into any chat, paste the reply back, done. Best for the Improver and Planner: a few calls each time.')));
      if (p.setup) fields.push(h('div.callout', icon('info'), h('div', 'First time? Install it, then run ', h('code', p.setup))));
      const save = h('button.btn.primary', icon('check'), 'Save and test');
      save.addEventListener('click', () => withBusy(save, async () => {
        const spec = { kind: p.kind, preset: p.id, model: model.value.trim(), base_url: (p.id === 'custom' || p.id === 'milliner' || p.local) ? base.value.trim() : p.base_url, label: p.label };
        if (p.kind === 'openai') spec.json_mode = 'json_object';
        const roles = roleBoxes.filter((x) => x.cb.checked).map((x) => x.r);
        const saved = await post('/api/inference/instruments', { name: name.value.trim(), spec, key: key.value.trim() || undefined, roles });
        key.value = '';
        m.close();
        toast(`${saved.label} saved.`, 'good');
        await load();
        if (p.kind !== 'manual') testInstrument(saved.name, load);
      }));
      body.append(h('div.row', h('button.btn.ghost.sm', { onclick: step1 }, icon('left'), 'All options'), h('span.spacer'),
        h('div.monogram', { style: { background: MONO_COLORS[p.id] } }, p.label.replace(/[^A-Za-z]/g, '').slice(0, 2)), h('b', p.label)),
        h('p.small.muted', p.blurb), h('div.col.gap-16.mt-8', fields), h('div.row.mt-16', h('span.spacer'), save));
    };
    chosen ? step2() : step1();
  };
  await load();
  offs.push(bus.on('inference', debounce(load, 300)), bus.on('manual', debounce(load, 300)), bus.on('ui:add-model', () => addModel()));
  return () => offs.forEach((f) => f());

  function threeWays() {
    const way = (ic, title, text, go) => h('div.choice', { onclick: go }, icon(ic), h('b', title), h('span', text));
    return h('div.card', h('h3', icon('zap'), 'Three ways to give Runesmith a mind'), h('p.sub', 'Pick one now; add more any time.'),
      h('div.grid.three', way('laptop', 'On this computer', 'Free and private: Ollama, LM Studio or llama.cpp. Runesmith finds them for you.', () => addModel('ollama')),
        way('key', 'With an API key', 'OpenRouter, Groq, Gemini, Mistral, DeepSeek, OpenAI, Anthropic… several have free tiers.', () => addModel()),
        way('chat', 'Copy and paste', 'No key, no install: relay requests to any chat window you already use.', () => addModel('manual'))));
  }
}

function uniqueName(base, data) {
  const names = new Set(data.instruments.map((i) => i.name));
  if (!names.has(base)) return base;
  for (let i = 2; ; i++) if (!names.has(`${base}-${i}`)) return `${base}-${i}`;
}

function instrumentRow(i, data, reload) {
  const st = data.stats[i.name];
  const status = h('div.small');
  const row = h('div.instrument', h('div.monogram', { style: { background: MONO_COLORS[i.preset] || '#475569' } }, (i.label || i.name).replace(/[^A-Za-z]/g, '').slice(0, 2)),
    h('div', h('div.row.wrap', h('b', i.label), h('span.badge.mono', i.name), i.local ? h('span.badge.good', 'local') : null, i.usable ? null : h('span.badge.warn', 'incomplete'),
      i.key.secret ? h('span', { class: `badge ${i.key.saved ? 'good' : 'bad'}` }, icon('key'), i.key.saved ? 'key saved' : 'key missing') : null),
      h('div.small.muted.mono.ellipsis', `${i.model || ''}${i.base_url ? ' · ' + i.base_url : ''}`),
      h('div.tiny.faint', i.roles.length ? `roles: ${i.roles.map((r) => data.role_labels[r].split(':')[0]).join(', ')}` : 'no role yet: assign one below',
        st ? ` · ${st.calls} calls, ${st.errors} errors, ~${(st.latency_s / Math.max(1, st.calls)).toFixed(1)} s each` : ''), status),
    h('div.row', i.kind !== 'manual' ? h('button.btn.sm', { onclick: () => testInstrument(i.name, reload, status) }, icon('zap'), 'Test') : null,
      h('button.btn.sm.icon.ghost', { title: 'Remove', onclick: async () => { if (await confirmDialog({ title: `Remove ${i.label}?`, text: 'Its saved key is deleted too.', confirm: 'Remove', danger: true })) { await del(`/api/inference/instruments/${i.name}`); reload(); } } }, icon('trash'))));
  commentable(row, 'instrument', i.name, i.label);
  row.querySelector('.note-btn').style.right = '96px';
  return row;
}
async function testInstrument(name, reload, statusEl) {
  toast(`Testing ${name}: one tiny call…`, 'info', 2500);
  try {
    const r = await post(`/api/inference/test/${name}`, {});
    if (r.ok) toast(`${name} works: ${r.detail}${r.latency_s != null ? ` in ${r.latency_s} s` : ''}.`, 'good', 6000);
    else toast(`${name} did not work: ${r.detail}`, 'bad', 10000);
    if (statusEl) statusEl.textContent = r.ok ? `✓ tested just now (${r.latency_s} s)` : `✗ ${r.detail}`;
  } catch (e) { toast(e.message, 'bad'); }
}

function roleLane(role, data, reload) {
  const names = data.roles[role] || [];
  const usable = new Set(data.ready.usable[role] || []);
  const others = data.instruments.filter((i) => !names.includes(i.name));
  const lane = h('div.role-lane.mt-8');
  const save = (list) => post('/api/inference/roles', { roles: { [role]: list } }).then(reload);
  lane.append(h('h4', icon(ROLE_ICON[role]), data.role_labels[role], h('span.spacer'),
    role === 'plan' && !names.length && data.ready.plan ? h('span.badge', `uses ${data.ready.plan_source}`) : names.length && !usable.size ? h('span.badge.warn', 'not ready') : names.length ? h('span.badge.good', 'ready') : h('span.badge', 'empty')));
  const box = h('div.pillbox');
  names.forEach((n, idx) => {
    const tag = h('span.tag', { draggable: 'true', title: idx ? 'fallback' : 'preferred' }, idx ? h('span.faint.tiny', `${idx + 1}.`) : icon('check'), n,
      idx ? h('button', { title: 'Move up', onclick: () => { const l = names.slice(); [l[idx - 1], l[idx]] = [l[idx], l[idx - 1]]; save(l); } }, icon('up')) : null,
      h('button', { title: 'Remove from this role', onclick: () => save(names.filter((x) => x !== n)) }, icon('x')));
    box.append(tag);
  });
  if (others.length) {
    const sel = h('select.select', { style: { width: 'auto', height: '28px', fontSize: '12.5px' }, onchange: () => { if (sel.value) save([...names, sel.value]); } },
      h('option', { value: '' }, '+ add a model'), others.map((i) => h('option', { value: i.name }, i.label + ' (' + i.name + ')')));
    box.append(sel);
  }
  if (!data.instruments.length) box.append(h('span.small.faint', 'Add a model first.'));
  lane.append(box);
  return lane;
}

/** The chat relay in a drawer, from any page: copy the request, paste the answer, carry on. */
export function openRelayDrawer() {
  import('../core.js').then(({ drawer }) => drawer({ title: 'Chat relay', sub: 'Runesmith is waiting for an answer from a chat model', width: 'min(880px, 100vw)',
    render: (body, close) => {
      const draw = async () => {
        const relay = await get('/api/manual');
        const waiting = relay.requests.filter((r) => !r.answered);
        clear(body);
        if (!waiting.length) { body.append(empty('check', 'Nothing is waiting', 'Runesmith carries on with the answer you gave.')); setTimeout(close, 1400); return; }
        body.append(relayPanel(waiting, draw));
      };
      draw();
    } }));
}

function relayPanel(requests, reload) {
  const card = h('div.card.glow', h('div.card-head', h('h3', icon('chat'), 'Chat relay'), requests.length ? h('span.badge.accent', `${requests.length} waiting`) : h('span.badge', 'nothing waiting')));
  if (!requests.length) { card.append(h('p.muted', 'When a model set up as “a chat window” is needed, its request appears here. Copy it into any chat, paste the reply back.')); return card; }
  for (const r of requests) {
    const answer = h('textarea.textarea.mono', { rows: 12, placeholder: 'Paste the chat model’s whole reply here…' });
    const model = h('input.input', { placeholder: 'Which model answered? (optional, recorded in the receipt)' });
    const send = h('button.btn.primary', icon('send'), 'Send the answer');
    send.addEventListener('click', () => withBusy(send, async () => {
      if (!answer.value.trim()) { toast('Paste the reply first.', 'warn'); return; }
      const res = await post(`/api/manual/${encodeURIComponent(r.id)}/answer`, { text: answer.value, model: model.value });
      if (res.written) { toast('Answer delivered. Runesmith continues.', 'good'); reload(); return; }
      const problems = (res.problems || []).slice(0, 6).map((p) => p.replace(/^[a-z_]+:\s*/, '')).join('; ');   // no internal codes
      if (await confirmDialog({ title: 'The reply does not fit the requested format', text: `${problems}. You can ask the chat model to fix it, or send it anyway (Runesmith records an unusable answer as such).`, confirm: 'Send anyway' })) {
        await post(`/api/manual/${encodeURIComponent(r.id)}/answer`, { text: answer.value, model: model.value, force: true });
        toast('Sent as it is.', 'good'); reload();
      }
    }));
    const skip = h('button.btn.ghost', { title: 'Decline: the waiting step gets no answer and moves on' }, icon('x'), 'Skip');
    skip.addEventListener('click', async () => {
      if (!(await confirmDialog({ title: 'Skip this request?', text: 'The step that asked stops without an answer, and nothing it would have changed is changed: a plan or draft stays as it is. This is recorded in the ledger.', confirm: 'Skip it' }))) return;
      withBusy(skip, async () => { await post(`/api/manual/${encodeURIComponent(r.id)}/skip`, {}); toast('Skipped.', 'good'); reload(); });
    });
    card.append(h('div.relay.mt-8',
      h('div', h('div.row', h('b.small', '1. Copy this request'), h('span.spacer'), h('span.tiny.faint', `~${r.approx_tokens} tokens`), h('button.btn.sm.primary', { onclick: () => copyText(r.text) }, icon('copy'), 'Copy')), h('pre.code.mt-8', r.text)),
      h('div', h('b.small', '2. Paste it into any chat model, then paste its reply here'), h('div.col.mt-8', answer, model, h('div.row', h('span.tiny.faint', `request ${r.id}`), h('span.spacer'), skip, send)))));
  }
  return card;
}
