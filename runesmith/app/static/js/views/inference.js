// Thinking power: where Runesmith's thinking comes from. None, a model on this computer, API keys, or a chat window.
import { h, icon, get, post, del, bus, toast, commentable, openNotes, clear, ago, plural, humanize, withBusy, confirmDialog,
  modal, empty, debounce, copyText } from '../core.js';
import {gatewayUsage} from '../gateway-usage.js';

const MONO_COLORS = { ollama: '#111827', lmstudio: '#4f46e5', llamacpp: '#0f766e', openrouter: '#6d28d9', groq: '#f55036', gemini: '#1a73e8',
  mistral: '#fa520f', deepseek: '#4d6bfe', openai: '#10a37f', anthropic: '#d97757', together: '#0f6fff', custom: '#475569', milliner: '#b45309', manual: '#22d3c5' };
const ROLE_ICON = { repair: 'hammer', kaizen: 'spark', plan: 'wand', acceptance: 'check' };
// The roles this Studio's server reports, in a fixed order (an older server has no Checker).
const shownRoles = (data) => ['repair', 'kaizen', 'plan', 'acceptance'].filter((r) => data.role_labels[r]);
// In-memory only; keep a pending typed reply across redraws/panel navigation.
const relayReplies = new Map();
// In-memory only: each model's last test, so a provider's "use X instead" survives the page being redrawn.
const lastTest = new Map();

export default async function render(root, ctx) {
  const offs = [];
  const head = h('div.page-head', h('div', h('h2', 'Thinking power'),
    h('p', 'Runesmith works with any model, weak or strong, and even with none: without a model it maps and watches. Add a model that runs on this computer (free and private), an API key, or simply a chat window you copy and paste into. Keys are saved on this computer only and are never shown again.')),
    h('div.actions', h('button.btn', {onclick:e=>withBusy(e.currentTarget,recordedUsage)}, icon('layers'), 'Usage & cost coverage'),
      h('button.btn.primary', { onclick: () => addModel() }, icon('plus'), 'Add thinking power')));
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
    for (const role of shownRoles(data)) roles.append(roleLane(role, data, load));
    roles.append(h('p.tiny.faint', 'Ready means configured, not available quota. The Planner borrows the Improver’s (or the Worker’s) model when it has none of its own. Qualify each route for its role: a connection test is not an authoring test.'));
    const local = h('div.card', h('div.card-head', h('h3', icon('laptop'), 'On this computer'), h('div.actions', h('button.btn.sm', { onclick: (e) => withBusy(e.currentTarget, () => scan(localList)) }, icon('refresh'), 'Look again'))));
    const localList = h('div');
    local.append(localList);
    scan(localList);
    const keys = h('div.card', h('div.card-head', h('h3', icon('key'), 'Saved keys'), h('span.badge.good', icon('lock'), 'never shown')),
      data.keys.length ? h('div.list', data.keys.map((k) => h('div.item', h('div.ico', icon('key')), h('div.body', h('div.title.mono', k.name), h('div.meta', `saved ${ago(k.saved_utc)} · stored in this folder's .runesmith/secrets.json`)))))
        : h('p.muted', 'No keys saved. Keys stay on this computer, outside your project files, and are sent only to the provider they belong to.'));
    body.append(h('div.grid.two', h('div.col.gap-16', inst, roles, authorGuidance()), h('div.col.gap-16', local, keys)));
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
      const name = h('input.input', { value: uniqueName(p.id, data), placeholder: 'a short name', 'aria-label': 'Instrument name' });
      // Never empty: the preset's first suggestion is the value (not a placeholder) until the provider's own list says
      // better. A model name that came with the choice (a running local server's), or one the owner typed or picked, is kept.
      const fallbackName = (p.suggested || [])[0] || '';
      const hosted = p.kind === 'openai' && p.key === 'required';
      let touched = Boolean(extra.model);
      const model = h('input.input', { value: extra.model || fallbackName, placeholder: p.kind === 'manual' ? 'which chat you will use, e.g. ChatGPT, Claude, Gemini' : 'model id', list: 'rs-models', 'aria-label': p.kind === 'manual' ? 'Chat/model label (optional)' : 'Model ID' });
      model.addEventListener('input', () => { touched = true; });
      const dl = h('datalist#rs-models', [...new Set([...(extra.models || []), ...(p.suggested || [])])].map((x) => h('option', { value: x })));
      const modelNote = h('span.hint', { role: 'status', 'aria-live': 'polite' }, hosted && fallbackName && !extra.model ? `Suggested for now: ${fallbackName} (checked when you add your key).` : '');
      const chipBox = h('div.pillbox.mt-8');
      const base = h('input.input.mono', { value: p.base_url || '', placeholder: 'https://… or http://127.0.0.1:…' });
      const providerFilter = h('input.input.mono', { placeholder: 'all providers, or e.g. opencode / cline' });
      const fallbacks = h('textarea.input.mono', {rows:3, placeholder:'provider:model — one fallback per line (up to five)'});
      const key = h('input.input.mono', { type: 'password', placeholder: p.key === 'required' ? 'paste your key' : 'optional', autocomplete: 'off' });
      const showKey = h('button.btn.icon', { type: 'button', title: 'Show or hide', onclick: () => { key.type = key.type === 'password' ? 'text' : 'password'; } }, icon('eye'));
      // Prefer author roles for manual relay; any role can require several human-relayed calls.
      // The Checker follows the Planner until the owner picks a model for it on purpose.
      const defaultOn = (r) => r !== 'acceptance' && (p.kind === 'manual' ? r !== 'repair' : firstModel || (r === 'repair' && !data.ready.repair));
      const roleBoxes = shownRoles(data).map((r) => { const cb = h('input', { type: 'checkbox', checked: defaultOn(r), value: r });
        return { r, cb, el: h('label.chip', cb, icon(ROLE_ICON[r]), data.role_labels[r].split(':')[0]) }; });
      // Ask the provider what it serves now. The newest answer wins; an older one that comes back late is dropped.
      let seq = 0, pending = null, checkedWith = null;
      const label = p.label;
      const showChips = (names) => {
        clear(chipBox);
        for (const name of [...new Set(names)].filter((x) => x && x !== model.value.trim()))
          chipBox.append(h('button.chip', { type: 'button', title: `Use ${name}`, onclick: () => { model.value = name; touched = true; showChips(names); modelNote.textContent = `Using ${name}.`; } }, name));
      };
      const applyList = (r) => {
        if (!r.ok) {
          clear(chipBox);
          modelNote.textContent = r.needs_key ? r.detail : r.status === 401 || r.status === 403 ? `${label} refused the key, so its model list could not be read: check the key.`
            : `Could not read ${label}'s model list${model.value.trim() ? `; keeping ${model.value.trim()}` : ''}. Any model id can be typed.`;
          return;
        }
        clear(dl).append(...r.models.map((x) => h('option', { value: x })));
        if (r.recommended && (!touched || !model.value.trim())) model.value = r.recommended;
        const now = model.value.trim();
        showChips([r.recommended, ...(r.choices || [])]);
        if (r.recommended && now === r.recommended) modelNote.textContent = `Recommended from ${label}'s list today: ${now}.${chipBox.children.length ? ' Other good choices:' : ''}`;
        else if (r.models.length && now && !r.models.includes(now)) modelNote.textContent = `${now} is not in ${label}'s list. Pick one of these, or keep it if you know it works.`;
        else modelNote.textContent = `${plural(r.models.length, 'model')} listed by ${label}.`;
      };
      const check = () => {
        const mine = ++seq, k = key.value.trim();
        pending = post('/api/inference/models', { preset: p.id, base_url: base.value, key: key.value,
          provider: p.kind === 'milliner' ? providerFilter.value.trim().toLowerCase() : '' }).catch(() => ({ ok: false, status: 0, models: [] }))
          .then((r) => { if (mine === seq) { checkedWith = k; applyList(r); } return r; });
        return pending;
      };
      const listBtn = h('button.btn', { type: 'button', onclick: () => withBusy(listBtn, async () => {
        const r = await check();
        if (r.ok) {
          toast(`${r.models.length} catalog entries shown. ${r.detail || 'Start typing to pick one.'}`, r.models.length ? 'good' : 'warn', 8000);
          model.focus();
        } else toast(r.needs_key ? r.detail : r.status === 401 ? 'The provider refused the key.' : (r.detail || 'Could not list models (the provider may not support it, or it is not running).'), 'warn', 6000);
      }) }, icon('search'), 'List models');
      // The key goes in: look at once (a paste, or leaving the field), not on every keystroke, so a half-typed key is never sent.
      if (hosted) {
        key.addEventListener('paste', () => setTimeout(() => { if (key.value.trim().length >= 8) check(); }, 0));
        key.addEventListener('change', () => { if (key.value.trim().length >= 8 && checkedWith !== key.value.trim()) check(); });
      }
      // A local server needs no key: show what it has loaded.
      if (p.local && !extra.model && base.value) check();
      const fields = [h('div.field', h('label', 'Name'), name, h('span.hint', 'How Runesmith refers to this model.'))];
      if (p.kind === 'milliner') fields.push(h('div.field', h('label', 'Catalog provider filter'), providerFilter,
        h('span.hint', 'Narrows List models without making an inference call. It does not change the saved model, routing or fallback policy.')));
      if (p.kind !== 'manual') fields.push(h('div.field', h('label', 'Model'), h('div.row', model, listBtn), dl, modelNote, chipBox, h('span.hint', 'Use a served model id. Qualify it on representative work: authoring needs coherent design and complete changes; workers may handle narrower, checked tasks. Free or paid is not a capability grade.')));
      else fields.push(h('div.field', h('label', 'Which chat will you use? (for the record)'), model));
      if (p.id === 'custom' || p.id === 'milliner' || p.local) fields.push(h('div.field', h('label', 'Address'), base));
      if (p.kind === 'milliner') fields.push(h('div.field', h('label', 'Milliner fallback models'), fallbacks,
        h('span.hint', 'Milliner tries this explicit chain after the primary fails. Only add free models here if this is a free-only fallback. Their quotas still apply.')));
      // A free key's allowance is small: said before anything is built, in the words the guide uses (one place: the preset).
      const chain = p.free_chain ? h('input', { type: 'checkbox', checked: true, 'aria-label': 'Also set up the other free models on this key' }) : null;
      if (p.free_note) fields.push(h('div.callout', { 'data-free-note': p.id }, icon('info'), h('div', p.free_note,
        chain ? h('label.row.mt-8', chain, 'Also set up the other free models on this key, to be used in turn (recommended)') : null)));
      if (p.key !== 'none') fields.push(h('div.field', h('label', p.kind === 'milliner' ? 'Agent token' : 'API key'), h('div.row', key, showKey),
        h('span.hint', 'Saved only in this folder’s .runesmith/secrets.json (not encrypted: keep that folder private), never shown again.', p.key_url ? [' ', h('a', { href: p.key_url, target: '_blank', rel: 'noopener' }, 'Get a key')] : null)));
      fields.push(h('div.field', h('label', 'Roles'), h('div.pillbox', roleBoxes.map((x) => x.el)), h('span.hint', 'Worker repairs code · Improver improves Runesmith itself · Planner drafts plans and first files · Checker proposes acceptance checks (a few calls that decide what “done” means: your best model pays off here).')));
      if (p.kind === 'manual') fields.push(h('div.callout', icon('chat'), h('div', 'Requests appear here and in the top bar. Copy the whole packet into your chat, then paste its reply back. Useful for Planner/Improver work; every call requires a person to relay it. Keep Studio running while waiting. Saving this instrument does not make a model call.')));
      if (p.setup) fields.push(h('div.callout', icon('info'), h('div', 'First time? Install it, then run ', h('code', p.setup))));
      const save = h('button.btn.primary', icon('check'), p.kind === 'manual' ? 'Save chat instrument' : 'Save and test');
      save.addEventListener('click', () => withBusy(save, async () => {
        // A key that was never checked (typed, then Save at once): ask the provider's list first. Only a name the owner did
        // not choose is replaced, and the screen says so.
        const suggestedName = model.value.trim();
        if (pending) await pending;
        if (hosted && key.value.trim() && checkedWith !== key.value.trim() && !touched) await check();
        if (!touched && suggestedName && model.value.trim() !== suggestedName)
          toast(`Using ${model.value.trim()}: that is what ${label} serves today (${suggestedName} was only a suggestion).`, 'info', 8000);
        const spec = { kind: p.kind, preset: p.id, model: model.value.trim(), base_url: (p.id === 'custom' || p.id === 'milliner' || p.local) ? base.value.trim() : p.base_url, label: p.label };
        if (p.kind === 'openai') spec.json_mode = p.json_mode || 'json_object';      // LM Studio refuses json_object
        if (p.max_request_tokens) spec.max_request_tokens = p.max_request_tokens;      // a free tier's per-minute window
        if (p.kind === 'milliner') spec.fallback_models = fallbacks.value.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
        const roles = roleBoxes.filter((x) => x.cb.checked).map((x) => x.r);
        const saved = await post('/api/inference/instruments', { name: name.value.trim(), spec, key: key.value.trim() || undefined, roles,
          chain: chain ? chain.checked : undefined });
        key.value = '';
        m.close();
        toast(`${saved.label} saved.${saved.chain?.detail ? ' ' + saved.chain.detail : ''}`, saved.chain && !saved.chain.ok ? 'warn' : 'good', saved.chain?.detail ? 9000 : undefined);
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
  offs.push(bus.on('inference', debounce(load, 300)), bus.on('manual', debounce(load, 300)), bus.on('ui:add-model', (e) => addModel(e?.preset, e?.extra || {})));
  return () => offs.forEach((f) => f());

  function threeWays() {
    const way = (ic, title, text, go) => h('div.choice', { onclick: go }, icon(ic), h('b', title), h('span', text));
    return h('div.card', h('h3', icon('zap'), 'Three ways to give Runesmith a mind'), h('p.sub', 'Pick one now; add more any time.'),
      h('div.grid.three', way('laptop', 'On this computer', 'Free and private: Ollama, LM Studio or llama.cpp. Runesmith finds them for you.', () => addModel('ollama')),
        way('key', 'With an API key', 'OpenRouter, Groq, Gemini, Mistral, DeepSeek, OpenAI, Anthropic… several have free tiers. A free Gemini key allows about 20 requests a day for each model, so add a second free provider (Groq) to build comfortably.', () => addModel()),
        way('chat', 'Copy and paste', 'No key, no install: relay requests to any chat window you already use.', () => addModel('manual'))));
  }
}

function uniqueName(base, data) {
  const names = new Set(data.instruments.map((i) => i.name));
  if (!names.has(base)) return base;
  for (let i = 2; ; i++) if (!names.has(`${base}-${i}`)) return `${base}-${i}`;
}

function authorGuidance() {
  return h('div.card', h('h3', icon('info'), 'Choosing authors and workers'),
    h('p.small', 'There is no established minimum model size or price. Planner authors integrate requirements and draft plans/files; Improver authors change Runesmith itself. These roles usually need broader design and integration ability than a bounded Worker task.'),
    h('p.small', 'A cheaper or smaller worker can be useful with focused source, a narrow contract and real checks. Complex repairs may still need a stronger model. A free model can be a good author; qualify the task, not the price tag.'),
    h('p.small', 'The Checker proposes each milestone’s acceptance checks: a few calls that decide what “done” means for automatic apply. In our testing a small free model built well but wrote weak checks, so give the Checker your best model (a chat window works well), and let a free API model build.'),
    h('details', h('summary', 'What is strong enough?'),
      h('ul.small', h('li', 'Follows the actual packet and required format; does not invent unseen source or permission.'),
        h('li', 'Produces a complete, applicable change while preserving interfaces and unrelated behavior.'),
        h('li', 'Passes meaningful checks and uses failure feedback within a bounded call budget.'),
        h('li', 'Still works after a fresh load/source check; failures, assistance and cost remain recorded.')),
      h('p.small.muted', 'Start with a capable available author, then qualify economical alternatives on the same contract. If it fails, narrow the work, improve the packet or change models—do not waive checks. One successful draft does not qualify general unattended work.')),
    h('details', h('summary', 'Use a frontier chat without an API key'),
      h('ol.small',
        h('li', 'Add thinking power → No key needed → A chat window. Name it; the chat/model label is optional.'),
        h('li', 'Assign Planner for plans/build drafts, or Improver for self-improvement proposals. Move it first in the intended role under Who does what. An API/local Worker avoids relaying every repair call. Roles do not enable automatic work or self-improvement by themselves.'),
        h('li', 'Start the intended action. Copy the complete waiting request into your chosen model’s chat. Preserve its requested JSON or file-block format and check what project information you are sharing.'),
        h('li', 'Paste the complete reply into the matching request. The model label is self-reported, not provider-verified. Do not mix request IDs.'),
        h('li', 'If refused, use Copy correction request in that chat and return the whole corrected reply. Format acceptance is not code approval: normal admission, source checks, tests and application permissions still apply.'),
        h('li', 'Keep Studio running. Closing the panel is safe; a restart may set unanswered requests aside. Follow current recovery status and read the resulting check/apply receipts.')),
      h('p.small.muted', 'Copy/paste is human-assisted transport, not unattended execution. Fully automatic work needs API or local inference for every role it uses.')));
}

async function editMillinerRoute(name, reload) {
  const route = await get(`/api/inference/routes/${name}`);
  const body = h('div');
  const m = modal({title: `Route for ${name}`, wide: true, body, actions:[{label:'Close',kind:'ghost'}]});
    const model = h('input.input.mono', {value: route.model, 'aria-label': 'Primary model ID'});
    const fallbacks = h('textarea.textarea.mono', {rows: 4, value: route.fallback_models.join('\n'),
      'aria-label': 'Fallback model IDs', placeholder: 'One provider:model per line; up to five'});
    const reason = h('input.input', {'aria-label': 'Route change reason', placeholder: 'Why change this route?'});
    const provider = h('input.input', {'aria-label': 'Catalog provider', placeholder: 'Optional provider filter, e.g. gemini3'});
    const catalog = h('div.small.muted');
    const list = h('button.btn.sm', {onclick: e => withBusy(e.currentTarget, async () => {
      const result = await post('/api/inference/models', {name, provider: provider.value.trim().toLowerCase()});
      clear(catalog).append(result.ok
        ? h('div', h('p.tiny', result.detail || 'Catalog only; not a tested route.'),
            h('pre.code', result.models.slice(0, 100).join('\n') || 'No catalog entries.'),
            result.models.length > 100 ? h('p.tiny', 'Showing100 entries; filter by provider to narrow.') : null)
        : h('p', result.detail || `Catalog unavailable (${result.status || 'no response'}).`));
    })}, icon('search'), 'List free-catalog models');
    body.append(h('p', 'Changes routing for future jobs. Keys, endpoint, caller, timeouts, spending tags and role assignments stay unchanged.'),
      h('p.small.muted', 'These are requested preferences, not a guarantee of which model answers. Milliner selects an eligible route; request receipts identify the actual author.'),
      h('p.small.muted', 'This does not enforce a free-only spending policy. Select only authorized routes; gateway permissions and quotas still apply. Saving makes no inference or connection-test call.'),
      ...route.blockers.map(message => h('p.callout.warn', message)),
      h('div.field', h('label', 'Primary model'), model),
      h('div.field', h('label', 'Explicit fallback preferences'), fallbacks),
      h('div.field', h('label', 'Reason'), reason),
      h('details.mt-8', h('summary', 'Look up free catalog IDs (no generation)'), provider, list, catalog),
      h('button.btn.primary.mt-16', {disabled: Boolean(route.blockers.length), onclick: e => withBusy(e.currentTarget, async () => {
        if (!reason.value.trim()) { toast('Add a reason for changing this route.', 'warn'); return; }
        await post(`/api/inference/routes/${name}`, {revision: route.revision, model: model.value.trim(),
          fallback_models: fallbacks.value.split(/\r?\n/).map(value => value.trim()).filter(Boolean), reason: reason.value.trim()});
        m.close(); await reload(); toast('Route saved. No model call made; this configuration is not a quality test.', 'good', 7000);
      })}, icon('check'), 'Save route without a test call'));
}

async function recordedAvailability(name) {
  const data = await get(`/api/inference/availability/${name}`);
  const body = h('div');
  modal({title: `Recorded availability for ${name}`, wide: true, body, actions:[{label:'Close',kind:'ghost'}]});
    body.append(h('p.small', data.scope), h('p.callout.warn', data.caution),
      h('p.tiny.muted', `Read at ${data.observed_at}. Scanned ${data.coverage.scanned} receipts; ${data.coverage.matching} match this instrument; ${data.coverage.omitted} outside the window; ${data.coverage.unreadable} unreadable or invalid.`));
    if (data.unresolved_requests) body.append(h('p.callout.warn',
      `${data.unresolved_requests} unresolved request(s). Retrieve the saved ticket in Work & proposals; do not submit another copy.`));
    for (const row of data.routes) body.append(h('div.card.mt-8',
      h('h4.mono', {style:{overflowWrap:'anywhere'}}, row.model),
      h('span.badge', humanize(row.status)), h('p.small', row.detail),
      row.outcome ? h('p.tiny.muted', `Last gateway outcome: ${humanize(row.outcome)} · ${row.gateway_attempts} recorded attempt(s) in that job`) : null,
      row.observed_at ? h('p.tiny.muted', `Outcome recorded ${row.observed_at}${row.job_id ? ' · job ' + row.job_id : ''}`) : null,
      row.retry_at ? h('p.small', `Reported retry time: ${row.retry_at}${row.remaining_s > 0 ? ' (about ' + Math.ceil(row.remaining_s / 60) + ' minutes at this reading)' : ' (elapsed, not confirmed available)'}`) : null));
}

async function recordedUsage(){
  const body=h('div');
  modal({title:'Recorded gateway accounting',wide:true,body,actions:[{label:'Close',kind:'ghost'}]});
  const content=h('div');
  const load=async()=>{
    const report=await get('/api/inference/accounting');
    clear(content).append(gatewayUsage(report));
  };
  body.append(h('button.btn.sm',{onclick:e=>withBusy(e.currentTarget,load)},icon('refresh'),'Refresh saved receipts'),content);
  await load();
}

// Who answers now, or that the service turned this model's last requests away as busy (journey J0-F24: four 503s in a row and
// the row still said "answering now").
function answeringBadge(i, data) {
  if (i.busy?.streak) {
    const n = i.busy.streak;
    return h('span.badge.warn', { 'data-busy': i.name, title: `The service turned away this model's last ${n > 1 ? `${n} requests` : 'request'} as busy, in the last few minutes. Nothing was lost.` }, icon('clock'), 'busy lately');
  }
  return i.answering?.length ? h('span.badge.accent', { 'data-answering': i.name, title: `Answers for: ${i.answering.map((r) => data.role_labels[r].split(':')[0]).join(', ')}` }, icon('zap'), 'answering now') : null;
}

function instrumentRow(i, data, reload) {
  const st = data.stats[i.name];
  const status = h('div.small', ...testStatus(i, reload));
  const held = ((data.pacing || {}).limited || []).find((x) => x.name === i.name);     // at its free limit until a reset (J0-F3)
  const row = h('div.instrument', h('div.monogram', { style: { background: MONO_COLORS[i.preset] || '#475569' } }, (i.label || i.name).replace(/[^A-Za-z]/g, '').slice(0, 2)),
    h('div', {style:{paddingRight:'22px'}}, h('div.row.wrap', h('b', i.label), h('span.badge.mono', i.name), i.local ? h('span.badge.good', 'local') : null, i.usable ? null : h('span.badge.warn', 'incomplete'),
      i.key.secret ? h('span', { class: `badge ${i.key.saved ? 'good' : 'bad'}` }, icon('key'), i.key.saved ? 'key saved' : 'key missing') : null,
      // Who answers now (the first model of a role that is not waiting for its free limit), and who shares this key.
      answeringBadge(i, data),
      i.shares_key_with?.length ? h('span.badge', { title: `The same saved key as ${i.shares_key_with.join(', ')}; each model has its own free allowance` }, icon('key'), `same key as ${i.shares_key_with[0]}${i.shares_key_with.length > 1 ? ` +${i.shares_key_with.length - 1}` : ''}`) : null),
      h('div.small.muted.mono.ellipsis', `${i.model || ''}${i.base_url ? ' · ' + i.base_url : ''}`),
      i.used_today?.words ? h('div.small', { 'data-used-today': i.name }, i.used_today.words) : null,
      i.fallback_models?.length ? h('div.tiny.mono', `Milliner fallbacks: ${i.fallback_models.join(' → ')}`) : null,
      h('div.tiny.faint', i.roles.length ? `roles: ${i.roles.map((r) => data.role_labels[r].split(':')[0]).join(', ')}` : 'no role yet: assign one below',
        st ? ` · ${st.calls} host callbacks, ${st.errors} errors, ~${(st.latency_s / Math.max(1, st.calls)).toFixed(1)} s each${i.kind==='milliner'?' · see Usage & cost coverage for reconciled gateway receipts':st.costed_calls ? ` · $${st.estimated_usd.toFixed(4)} reported estimate (${st.costed_calls}/${st.calls} callbacks costed)` : ' · spend not reported'}` : ''), status, held && !String(lastTest.get(i.name)?.detail || '').includes('will not ask it again') ? h('div.small.callout.warn', held.words) : null),
    h('div.row.wrap.instrument-actions', i.kind === 'milliner' ? h('button.btn.sm', {onclick: e => withBusy(e.currentTarget, () => recordedAvailability(i.name))}, icon('clock'), 'Recorded availability') : null,
      i.kind === 'milliner' ? h('button.btn.sm', {onclick: e => withBusy(e.currentTarget, () => editMillinerRoute(i.name, reload))}, icon('layers'), 'Route') : null,
      i.free_chain && i.kind === 'openai' && i.usable && !i.shares_key_with?.length ? h('button.btn.sm', { 'data-add-chain': i.name, title: 'Uses the key already saved: nothing is typed again, and nothing is spent', onclick: (e) => withBusy(e.currentTarget, async () => {
        const r = await post(`/api/inference/instruments/${encodeURIComponent(i.name)}/chain`, {});
        toast(r.detail, r.ok ? 'good' : 'warn', 9000);
        reload();
      }) }, icon('plus'), 'Add the other free Gemini models') : null,
      i.kind !== 'manual' ? h('button.btn.sm', { onclick: () => testInstrument(i.name, reload) }, icon('zap'), 'Test') : null,
      h('button.btn.sm.icon.ghost', { title: 'Remove', onclick: async () => { if (await confirmDialog({ title: `Remove ${i.label}${i.model ? ` (${i.model})` : ''}?`, text: removeWords(i), confirm: 'Remove', danger: true })) { await del(`/api/inference/instruments/${i.name}`); lastTest.delete(i.name); reload(); } } }, icon('trash'))));
  commentable(row, 'instrument', i.name, i.label);
  row.querySelector('.note-btn').style.right = '8px';
  return row;
}
// Several models of one provider share one saved key: removing one keeps the key for the others.
function removeWords(i) {
  if (i.shares_key_with?.length) return `The saved key stays: ${i.shares_key_with.join(', ')} still use${i.shares_key_with.length === 1 ? 's' : ''} it. Only this model is removed.`;
  return 'Its saved key is deleted too.';
}
// What the last test said, kept on the model's row. When the provider named a replacement ("no longer available to new
// users, use X"), it is offered as a button: one click changes only the model name, and nothing switches without it.
function testStatus(i, reload) {
  const t = lastTest.get(i.name);
  if (!t) return [];
  // "Tested just now" only for a test that worked, and only while it is just now (journey J0-F8: it stayed on the row after
  // a failed test, hours old); a failed test replaces it with what went wrong.
  const ageS = Math.max(0, (Date.now() - (t.at || Date.now())) / 1000);
  const when = ageS < 90 ? 'just now' : ageS < 5400 ? `${Math.round(ageS / 60)} minutes ago` : `${Math.round(ageS / 3600)} hours ago`;
  const out = [t.ok ? `✓ tested ${when} (${t.latency_s} s)` : `✗ ${t.detail}`];
  if (!t.ok && t.raw) out.push(h('details', h('summary.tiny', 'What the service said'), h('pre.tiny.mono', { style: { whiteSpace: 'pre-wrap' } }, t.raw)));
  if (!t.ok && t.hint) out.push(h('div.row.wrap.mt-8', h('span', `${t.label || 'The provider'} suggests ${t.hint}:`),
    h('button.btn.sm.primary', { onclick: (e) => withBusy(e.currentTarget, async () => {
      await post(`/api/inference/instruments/${encodeURIComponent(i.name)}/model`, { model: t.hint, expect: i.model });
      lastTest.delete(i.name);
      toast(`${i.name} now uses ${t.hint}.`, 'good');
      await reload();
      testInstrument(i.name, reload);
    }) }, icon('check'), `Use ${t.hint}`)));
  return out;
}
async function testInstrument(name, reload) {
  toast(`Testing ${name}: one tiny call…`, 'info', 2500);
  try {
    const r = await post(`/api/inference/test/${name}`, {});
    lastTest.set(name, { ok: r.ok === true, detail: r.detail, latency_s: r.latency_s, at: Date.now(), raw: r.raw || '', hint: r.ok ? null : r.suggested_model || null, label: r.label });
    if (r.ok) toast(`${name} works: ${r.detail}${r.latency_s != null ? ` in ${r.latency_s} s` : ''}.`, 'good', 6000);
    else toast(`${name} did not work: ${r.detail}`, 'bad', 10000);
    if (reload) await reload();
  } catch (e) { lastTest.set(name, { ok: false, detail: `The test could not run: ${e.message}`, at: Date.now() }); toast(e.message, 'bad'); if (reload) await reload(); }
}

function roleLane(role, data, reload) {
  const names = data.roles[role] || [];
  const usable = new Set(data.ready.usable[role] || []);
  const others = data.instruments.filter((i) => !names.includes(i.name));
  const lane = h('div.role-lane.mt-8');
  const save = (list) => post('/api/inference/roles', { roles: { [role]: list } }).then(reload);
  const who = (data.role_labels[role] || role).split(':')[0];     // screen readers hear which role (journey J2-F2)
  lane.append(h('h4', icon(ROLE_ICON[role]), data.role_labels[role], h('span.spacer'),
    role === 'plan' && !names.length && data.ready.plan ? h('span.badge', `uses the ${(data.role_labels[data.ready.plan_source] || data.ready.plan_source).split(':')[0]}’s model`) :
    role === 'acceptance' && !names.length && data.ready.acceptance ? h('span.badge', 'uses the Planner’s model') : names.length && !usable.size ? h('span.badge.warn', 'not ready') : names.length ? h('span.badge.good', 'ready') : h('span.badge', 'empty')));
  const box = h('div.pillbox');
  names.forEach((n, idx) => {
    const tag = h('span.tag', { draggable: 'true', title: idx ? 'fallback' : 'preferred' }, idx ? h('span.faint.tiny', `${idx + 1}.`) : icon('check'), n,
      idx ? h('button', { title: 'Move up', 'aria-label': `Move ${n} up for the ${who}`, onclick: () => { const l = names.slice(); [l[idx - 1], l[idx]] = [l[idx], l[idx - 1]]; save(l); } }, icon('up')) : null,
      h('button', { title: 'Remove from this role', 'aria-label': `Remove ${n} from the ${who}`, onclick: () => save(names.filter((x) => x !== n)) }, icon('x')));
    box.append(tag);
  });
  if (others.length) {
    const sel = h('select.select', { 'aria-label': `Add a model to the ${who}`, style: { width: 'auto', height: '28px', fontSize: '12.5px' }, onchange: () => { if (sel.value) save([...names, sel.value]); } },
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
        if (!waiting.length) { body.append(empty('check', 'Nothing is waiting', 'There are no unanswered chat requests in this workspace.')); setTimeout(close, 1400); return; }
        body.append(relayPanel(waiting, draw));
      };
      draw();
    } }));
}

function relayPanel(requests, reload) {
  const activeIds = new Set(requests.map(r => r.id));
  for (const id of relayReplies.keys()) if (!activeIds.has(id)) relayReplies.delete(id);
  const card = h('div.card.glow', h('div.card-head', h('h3', icon('chat'), 'Chat relay'), requests.length ? h('span.badge.accent', `${requests.length} waiting`) : h('span.badge', 'nothing waiting')));
  if (!requests.length) { card.append(h('p.muted', 'When a model set up as “a chat window” is needed, its request appears here. Copy it into any chat, paste the reply back.')); return card; }
  card.append(h('p.small.muted', 'No API key is needed for this author; you relay the messages. Keep Studio running while a reply is pending. Restarting Studio sets aside unanswered requests. Closing this panel is safe.'));
  for (const r of requests) {
    const saved = relayReplies.get(r.id);
    const current = saved?.request === r.text ? saved : {};
    if (saved && saved.request !== r.text) relayReplies.delete(r.id);
    const answer = h('textarea.textarea.mono', { rows: 12, value: current.text || '', 'aria-label': `Reply for request ${r.id}`, placeholder: 'Paste the chat model’s whole reply here…' });
    const model = h('input.input', { value: current.model || '', 'aria-label': `Model label for request ${r.id}`, placeholder: 'Which model answered? (optional, self-reported in the receipt)' });
    const remember = () => relayReplies.set(r.id, {request: r.text, text: answer.value, model: model.value});
    const feedback = h('div.mt-8', { role: 'status', 'aria-live': 'polite' });
    answer.addEventListener('input', () => { remember(); clear(feedback); });
    model.addEventListener('input', () => { remember(); clear(feedback); });
    const send = h('button.btn.primary', icon('send'), 'Send the answer');
    send.addEventListener('click', () => withBusy(send, async () => {
      if (!answer.value.trim()) { toast('Paste the reply first.', 'warn'); return; }
      const submitted = { text: answer.value, model: model.value };
      remember();
      const sameReply = () => answer.value === submitted.text && model.value === submitted.model;
      const res = await post(`/api/manual/${encodeURIComponent(r.id)}/answer`, submitted);
      if (res.written) { relayReplies.delete(r.id); toast('Answer delivered. Runesmith continues.', 'good'); reload(); return; }
      if (!sameReply()) { toast('The reply changed while it was checked. Send the current reply to check it.', 'warn'); return; }
      const problems = Array.isArray(res.problems) && res.problems.length ? res.problems.map(String) : ['The reply does not fit the requested format.'];
      const correction = `Runesmith has not accepted the format of my reply for request ${r.id}.\n` +
        'Please correct these format problems using the original request and its JSON schema. Return the complete corrected reply, not just a fragment. Preserve the task and its constraints; this feedback is not a test result or permission to change the requirements.\n\n' +
        problems.map((p) => `- ${p}`).join('\n');
      const force = h('button.btn.ghost', icon('send'), 'Send unchanged anyway');
      force.addEventListener('click', () => withBusy(force, async () => {
        if (!sameReply()) { clear(feedback); toast('Check the edited reply before sending it.', 'warn'); return; }
        if (!(await confirmDialog({ title: 'Send this reply despite format problems?', text: 'Only this early format check is bypassed. Normal admission, source bindings, tests and application permissions still apply. The reply may be rejected without producing a draft.', confirm: 'Send anyway' }))) return;
        if (!sameReply()) { clear(feedback); toast('The reply changed. Check it again before sending.', 'warn'); return; }
        const delivered = await post(`/api/manual/${encodeURIComponent(r.id)}/answer`, { ...submitted, force: true });
        if (delivered.written) { relayReplies.delete(r.id); toast('Sent without passing the format precheck.', 'warn'); reload(); }
      }));
      clear(feedback);
      feedback.append(...[h('p.small', 'Not submitted: the reply needs a format correction. Your pasted reply is kept above.'),
        h('ul.small', ...problems.slice(0, 6).map((p) => h('li', p))),
        problems.length > 6 ? h('p.small.muted', `Showing 6 of ${problems.length} problems; the correction request includes all of them.`) : null,
        h('div.row', h('button.btn.sm.primary', { onclick: () => copyText(correction) }, icon('copy'), 'Copy correction request'), force)].filter(Boolean));
    }));
    const skip = h('button.btn.ghost', { title: 'Decline: the waiting step gets no answer and moves on' }, icon('x'), 'Skip');
    skip.addEventListener('click', async () => {
      if (!(await confirmDialog({ title: 'Skip this request?', text: 'The step that asked stops without an answer, and nothing it would have changed is changed: a plan or draft stays as it is. This is recorded in the ledger.', confirm: 'Skip it' }))) return;
      withBusy(skip, async () => { await post(`/api/manual/${encodeURIComponent(r.id)}/skip`, {}); relayReplies.delete(r.id); toast('Skipped.', 'good'); reload(); });
    });
    card.append(h('div.relay.mt-8',
      h('div', h('div.row', h('b.small', '1. Copy this request'), h('span.spacer'), h('span.tiny.faint', `~${r.approx_tokens} tokens`), h('button.btn.sm.primary', { onclick: () => copyText(r.text) }, icon('copy'), 'Copy')), h('pre.code.mt-8', r.text)),
      h('div', h('b.small', '2. Paste it into any chat model, then paste its reply here'), h('div.col.mt-8', answer, model,
        h('p.tiny.faint', 'The format precheck does not approve the code or apply changes.'),
        h('div.row', h('span.tiny.faint', `request ${r.id}`), h('span.spacer'), skip, send), feedback))));
  }
  return card;
}
