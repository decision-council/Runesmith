// Runesmith Studio core: DOM helpers, API, live events, dialogs, notes. No framework, no build.
import { iconSvg } from './icons.js';

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const SVG_TAGS = new Set(['svg', 'g', 'path', 'circle', 'rect', 'line', 'polyline', 'polygon', 'text', 'tspan', 'defs',
  'linearGradient', 'radialGradient', 'stop', 'filter', 'feGaussianBlur', 'feMerge', 'feMergeNode', 'ellipse', 'clipPath',
  'mask', 'textPath', 'use', 'marker', 'pattern', 'title', 'animate', 'animateTransform', 'foreignObject']);

/** h('div.card#id', {onclick, class, style:{...}, dataset:{...}, html:'...'}, ...children) */
export function h(tag, attrs, ...children) {
  let cls = [], id = null;
  const m = tag.match(/^[a-zA-Z0-9]+/);
  const name = m ? m[0] : 'div';
  tag.slice(name.length).replace(/([.#])([^.#]+)/g, (_, kind, value) => { kind === '.' ? cls.push(value) : (id = value); });
  const el = SVG_TAGS.has(name) ? document.createElementNS('http://www.w3.org/2000/svg', name) : document.createElement(name);
  if (id) el.id = id;
  if (attrs && (attrs.nodeType || typeof attrs !== 'object' || Array.isArray(attrs))) { children.unshift(attrs); attrs = null; }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') cls.push(...String(v).split(/\s+/).filter(Boolean));
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value' && 'value' in el) el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  if (cls.length) el.setAttribute('class', cls.join(' '));
  if (attrs && typeof attrs.onclick === 'function' && !NATIVE.has(name) && !SVG_TAGS.has(name)) pressable(el, name);
  append(el, children);
  return el;
}
// A card, row or tile that reacts to a click also takes the keyboard: Tab reaches it, Enter or Space presses it.
const NATIVE = new Set(['a', 'button', 'input', 'select', 'textarea', 'summary', 'label', 'option', 'details']);
function pressable(el, name) {
  if (!el.hasAttribute('tabindex')) el.tabIndex = 0;
  if (!el.hasAttribute('role') && name !== 'tr') el.setAttribute('role', 'button');
  el.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target === el) { e.preventDefault(); el.click(); }
  });
}
export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false || c === true) continue;
    el.appendChild(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}
export function icon(name, cls = '') {
  const t = document.createElement('template');
  t.innerHTML = iconSvg(name, cls).trim();
  return t.content.firstChild;
}
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
export function frag(markup) { const t = document.createElement('template'); t.innerHTML = markup.trim(); return t.content; }

// ---------------------------------------------------------------------- API --
export class ApiError extends Error { constructor(status, message, body) { super(message); this.status = status; this.body = body; } }
let workspaceEpoch = null;
export async function api(path, { method = 'GET', body } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (workspaceEpoch) opts.headers['X-Runesmith-Workspace'] = workspaceEpoch;
  if (method !== 'GET') { opts.headers['X-Runesmith'] = '1'; opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body || {}); }
  let res;
  try { res = await fetch(path, opts); }
  catch (e) { throw new ApiError(0, 'Runesmith Studio is not answering. Is it still running?'); }
  let data = null;
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new ApiError(res.status, (data && data.error) || res.statusText, data);
  // A page binds once, at bootstrap. Never silently retarget old forms after a
  // switch in another tab. The workspace event/explicit picker reloads the page.
  if (!workspaceEpoch && path === '/api/session') workspaceEpoch = res.headers.get('X-Runesmith-Workspace');
  return data;
}
export const get = (p) => api(p);
export const post = (p, b) => api(p, { method: 'POST', body: b });
export const del = (p) => api(p, { method: 'DELETE' });

// ------------------------------------------------------------------ events --
const handlers = new Map();
export const bus = {
  on(kind, fn) { if (!handlers.has(kind)) handlers.set(kind, new Set()); handlers.get(kind).add(fn); return () => handlers.get(kind)?.delete(fn); },
  emit(kind, data) { for (const fn of handlers.get(kind) || []) { try { fn(data); } catch (e) { console.error(e); } } for (const fn of handlers.get('*') || []) { try { fn(kind, data); } catch (e) { console.error(e); } } },
};
let source = null, lastId = 0;
const KINDS = ['worker', 'log', 'call', 'step', 'map', 'round', 'plan', 'work', 'job', 'manual', 'notes', 'settings', 'goals',
  'brief', 'inference', 'improve', 'health', 'needs', 'workspace', 'mission', 'dashboards', 'support_reports'];
export function connectEvents() {
  if (source) source.close();
  source = new EventSource(`/api/events?since=${lastId}&workspace=${encodeURIComponent(workspaceEpoch || '')}`);
  for (const kind of KINDS) {
    source.addEventListener(kind, (ev) => { try { const e = JSON.parse(ev.data); lastId = Math.max(lastId, e.id); bus.emit(kind, e.data); } catch (err) { console.error(err); } });
  }
  source.onopen = () => bus.emit('connection', { up: true });
  source.onerror = () => bus.emit('connection', { up: false });
}

// ------------------------------------------------------------------ format --
export function ago(utc) {
  if (!utc) return '—';
  const s = Math.round((Date.now() - Date.parse(utc)) / 1000);
  if (s < 0) { const f = -s; return f < 60 ? `in ${f}s` : f < 3600 ? `in ${Math.round(f / 60)} min` : f < 86400 ? `in ${Math.round(f / 3600)} h` : `in ${Math.round(f / 86400)} d`; }
  if (s < 10) return 'just now';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
export function clock(utc) { if (!utc) return ''; const d = new Date(utc); return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
export function datetime(utc) { if (!utc) return ''; return new Date(utc).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); }
export function plural(n, one, many) { return `${n} ${n === 1 ? one : (many || one + 's')}`; }
export function bytes(n) { if (n == null) return '—'; if (n < 1024) return `${n} B`; if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`; return `${(n / 1048576).toFixed(1)} MB`; }
export function humanize(s) { return String(s || '').replace(/_/g, ' '); }
export function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }
export function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
export const KIND = {
  python_repository: { label: 'Python project', icon: 'code', color: '#4aa8ff' },
  node_repository: { label: 'Node project', icon: 'box', color: '#22c55e' },
  document_collection: { label: 'Documents', icon: 'doc', color: '#ffb547' },
  website: { label: 'Website', icon: 'globe', color: '#22d3c5' },
  folder: { label: 'Folder', icon: 'folder', color: '#8a94ab' },
  excluded: { label: 'Excluded', icon: 'lock', color: '#6c7791' },
  unknown: { label: 'Unknown', icon: 'info', color: '#8a94ab' },
};
export const BAND_LABEL = { bad: 'Bad', minimal: 'Minimal', optimal: 'Optimal', world_class: 'World-class', unknown: 'Unknown' };
export function worstBand(bands) {
  const order = ['bad', 'minimal', 'optimal', 'world_class'];
  const known = (bands || []).filter((b) => b && b !== 'unknown');
  if (!known.length) return 'unknown';
  return known.sort((a, b) => order.indexOf(a) - order.indexOf(b))[0];
}
export const BAND_COLOR = { bad: '#ef4444', minimal: '#f5a524', optimal: '#22c55e', world_class: '#8b6cff', unknown: '#8a94ab' };

// ------------------------------------------------------------ toast/modal --
export function toast(text, kind = 'info', ms = 4200) {
  let box = $('.toasts');
  if (!box) { box = h('div.toasts'); document.body.appendChild(box); }
  const ic = { good: 'check', bad: 'alert', warn: 'alert', info: 'info' }[kind] || 'info';
  const el = h('div', { class: `toast ${kind}`, role: 'status' }, icon(ic), h('div.grow', text));
  box.appendChild(el);
  // Rapid normal use must not cover the workspace with an unbounded stack.
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(() => { el.style.transition = 'opacity .3s, transform .3s'; el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; setTimeout(() => el.remove(), 320); }, ms);
}
// ------------------------------------------------------------------ layers --
// Dialogs and drawers stack. Only the top one hears Escape, Tab stays inside it, and closing it hands the focus
// back to whatever opened it, so a keyboard or screen-reader user never lands on the page behind.
const LAYERS = [];
let layerSeq = 0;
export const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
export function layer(box, onEscape) {
  const opener = document.activeElement;
  const entry = { box };
  LAYERS.push(entry);
  const onKey = (e) => {
    if (LAYERS[LAYERS.length - 1] !== entry) return;
    if (e.key === 'Escape') { e.preventDefault(); onEscape(); return; }
    if (e.key !== 'Tab') return;
    const items = $$(FOCUSABLE, box).filter((el) => el.getClientRects().length);
    if (!items.length) { e.preventDefault(); return; }
    const first = items[0], last = items[items.length - 1], at = document.activeElement;
    if (e.shiftKey && (at === first || !box.contains(at))) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (at === last || !box.contains(at))) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', onKey);
  return () => {
    document.removeEventListener('keydown', onKey);
    const i = LAYERS.indexOf(entry);
    if (i >= 0) LAYERS.splice(i, 1);
    if (opener && opener.isConnected && typeof opener.focus === 'function') opener.focus({ preventScroll: true });
  };
}
export function modal({ title, text, body, actions = [], wide = false, onClose }) {
  const scrim = h('div.scrim');
  const titleId = `layer-${++layerSeq}`;
  const box = h('div', { class: `modal${wide ? ' wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId },
    h('header', h('h3', { id: titleId }, title || ''), text ? h('p', text) : null),
    h('div.body', body || null),
    actions.length ? h('footer') : null);
  const wrap = h('div.modal-wrap', box);
  let release = null;
  const close = (v) => { scrim.remove(); wrap.remove(); if (release) { release(); release = null; } onClose && onClose(v); };
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close(null); });
  const footer = $('footer', box);
  for (const a of actions) {
    const b = h('button', { class: `btn ${a.kind || ''}` }, a.icon ? icon(a.icon) : null, a.label);
    b.addEventListener('click', async () => {
      // An explicit null is a cancellation, not a missing button value.
      if (!a.onClick) return close(Object.prototype.hasOwnProperty.call(a, 'value') ? a.value : a.label);
      b.classList.add('busy');
      try { const r = await a.onClick(close); if (r !== false) { /* handler closes when it wants */ } }
      catch (e) { toast(e.message || String(e), 'bad'); }
      finally { b.classList.remove('busy'); }
    });
    footer.appendChild(b);
  }
  document.body.append(scrim, wrap);
  release = layer(box, () => close(null));
  setTimeout(() => { const f = box.querySelector('input, textarea, select, button.primary') || box.querySelector(FOCUSABLE); f && f.focus(); }, 30);
  return { close, el: box };
}
export function confirmDialog({ title, text, confirm = 'Confirm', cancel = 'Cancel', danger = false, icon: ic }) {
  return new Promise((resolve) => {
    modal({ title, text, onClose: (v) => resolve(v === true),
      actions: [{ label: cancel, kind: 'ghost', value: false }, { label: confirm, kind: danger ? 'danger' : 'primary', icon: ic, value: true }] });
  });
}
export function askText({ title, text, placeholder = '', value = '', confirm = 'Save', multiline = false }) {
  return new Promise((resolve) => {
    const input = multiline ? h('textarea.textarea', { placeholder, rows: 4 }, value) : h('input.input', { placeholder, value });
    const m = modal({ title, text, body: input, onClose: (v) => resolve(v),
      actions: [{ label: 'Cancel', kind: 'ghost', value: null }, { label: confirm, kind: 'primary', onClick: (close) => close(input.value) }] });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (!multiline || e.ctrlKey || e.metaKey)) { e.preventDefault(); m.close(input.value); } });
  });
}
export function drawer({ title, sub, render, width }) {
  const scrim = h('div.scrim');
  const body = h('div.body');
  const titleId = `layer-${++layerSeq}`;
  const closeBtn = h('button.btn.icon.ghost', { title: 'Close (Esc)', 'aria-label': 'Close', onclick: () => close() }, icon('x'));
  const el = h('aside.drawer', { role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId, style: width ? { width } : null },
    h('header', h('div.grow', h('h3', { id: titleId }, title), sub ? h('div.small.muted', sub) : null), closeBtn), body);
  let release = null, cleanup = null;
  const close = () => { scrim.remove(); el.remove(); if (release) { release(); release = null; } cleanup && cleanup(); };
  scrim.addEventListener('click', close);
  document.body.append(scrim, el);
  release = layer(el, close);
  cleanup = render(body, close, el);
  setTimeout(() => { if (el.isConnected && !el.contains(document.activeElement)) closeBtn.focus(); }, 60);   // unless it focused something itself
  return { close, el, body };
}
export async function withBusy(btn, fn) {
  btn && btn.classList.add('busy');
  try { return await fn(); }
  catch (e) { toast(e.message || String(e), 'bad', 6000); return undefined; }
  finally { btn && btn.classList.remove('busy'); }
}
export function copyText(text) {
  if (navigator.clipboard && window.isSecureContext !== false) return navigator.clipboard.writeText(text).then(() => toast('Copied', 'good', 1600));
  const ta = h('textarea', { style: { position: 'fixed', opacity: '0' } }, text); document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); toast('Copied', 'good', 1600); } finally { ta.remove(); }
  return Promise.resolve();
}
export function empty(iconName, title, text, action) {
  return h('div.empty', icon(iconName, 'big'), h('h4', title), text ? h('p', text) : null, action || null);
}
export function diffView(diff) {
  const box = h('div.diff');
  for (const line of String(diff || '').split('\n')) {
    let cls = '';
    if (line.startsWith('+++') || line.startsWith('---')) cls = 'file';
    else if (line.startsWith('@@')) cls = 'hunk';
    else if (line.startsWith('+')) cls = 'add';
    else if (line.startsWith('-')) cls = 'del';
    box.appendChild(h('span', { class: `ln ${cls}` }, line || ' '));
  }
  return box;
}

// ------------------------------------------------------------------- notes --
export const notesState = { counts: {}, readNotes: true };
export function noteKey(type, id) { return `${type}:${id}`; }
/** Make any element commentable: a hover button, a count badge, and comment-mode clicks. */
export function commentable(el, type, id, label) {
  el.dataset.note = `${type}|${id}`;
  el.dataset.noteLabel = label || id;
  const n = notesState.counts[noteKey(type, id)] || 0;
  const btn = h('button', { class: `note-btn${n ? ' has' : ''}`, title: n ? `${n} open note(s)` : 'Comment on this', type: 'button',
    'aria-label': noteLabel(n, label || id) }, n ? String(n) : icon('note'));
  btn.addEventListener('click', (e) => { e.stopPropagation(); e.preventDefault(); openNotes(type, id, label); });
  el.appendChild(btn);
  return el;
}
function noteLabel(n, label) { return n ? `${n} open note${n === 1 ? '' : 's'} on ${label}` : `Comment on ${label}`; }
export function refreshNoteBadges() {
  for (const el of $$('[data-note]')) {
    const [type, id] = el.dataset.note.split('|');
    const n = notesState.counts[noteKey(type, id)] || 0;
    const btn = el.querySelector(':scope > .note-btn');
    if (!btn) continue;
    btn.classList.toggle('has', !!n);
    btn.title = n ? `${n} open note(s)` : 'Comment on this';
    btn.setAttribute('aria-label', noteLabel(n, el.dataset.noteLabel || id));
    clear(btn); btn.append(n ? document.createTextNode(String(n)) : icon('note'));
  }
}
const TARGET_WORDS = { workspace: 'the whole workspace', object: 'this object', objective: 'this objective', rung: 'this rung',
  proposal: 'this fix', draft: 'this draft', generation: 'this generation', goal: 'this goal', milestone: 'this milestone',
  instrument: 'this model', capability: 'this capability', component: 'this part of Runesmith', self: 'Runesmith itself',
  plan: 'the plan', brief: 'the brief', session: 'this attempt', event: 'this event', organ: 'this organ', trial: 'this trial' };
const READS = { object: 'the Worker model, whenever Runesmith works on this object', objective: 'the Worker model, when it works on this object',
  rung: 'the Worker model, when it works on this object', workspace: 'every model Runesmith asks, for work anywhere here',
  self: 'the Improver model, when Runesmith improves itself', generation: 'the Improver model', capability: 'the Improver model',
  component: 'the Improver model', organ: 'the Improver model', plan: 'the Planner model', brief: 'the Planner model',
  goal: 'the Planner model', milestone: 'the Planner model', draft: 'the Planner model' };
export function openNotes(type, id, label) {
  drawer({ title: `Notes on ${label || id}`, sub: TARGET_WORDS[type] || type, render: (body, close) => {
    const list = h('div');
    const reads = READS[type];
    const info = h('div.callout.mb-8', icon('info'), h('div', notesState.readNotes && reads
      ? `Open notes here are eligible for ${reads}, within the prompt budget. Delivery is not guaranteed; inspect the draft's Revision packet for included and omitted feedback. Resolve notes that no longer apply.`
      : notesState.readNotes ? 'Notes here are kept for you and your team. They are recorded in the ledger.'
      : 'Models do not read notes right now (Settings → Give notes to the model).'));
    const ta = h('textarea.textarea', { placeholder: `Say anything about ${TARGET_WORDS[type] || 'this'}… (Ctrl+Enter to save)`, rows: 4 });
    let replyTo = null;
    const replyHint = h('div.small.muted.hidden');
    const save = h('button.btn.primary', icon('send'), 'Add note');
    const load = async () => {
      const data = await get('/api/notes');
      notesState.counts = data.counts; notesState.readNotes = data.read_notes; refreshNoteBadges();
      const mine = data.notes.filter((n) => n.target.type === type && n.target.id === id).reverse();
      clear(list);
      if (!mine.length) list.append(h('p.muted.small', 'No notes yet. Be the first to say something.'));
      const byParent = new Map();
      for (const n of mine) { const k = n.reply_to || ''; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k).push(n); }
      const renderNote = (n, depth) => {
        const el = h('div', { class: `note${n.resolved ? ' resolved' : ''}${depth ? ' reply' : ''}` },
          h('div.who', icon('user'), h('span', n.author === 'owner' ? 'You' : n.author), h('span', '·'), h('span', ago(n.utc)),
            n.resolved ? h('span.badge.good', 'resolved') : null, h('span.spacer'),
            h('button.btn.sm.ghost', { onclick: () => { replyTo = n.id; replyHint.textContent = 'Replying to this note'; replyHint.classList.remove('hidden'); ta.focus(); } }, 'Reply'),
            !n.resolved ? h('button.btn.sm.ghost', { onclick: async () => { await post(`/api/notes/${n.id}/resolve`, {}); load(); } }, icon('check'), 'Resolve') : null),
          h('div.text', n.text), n.resolved && n.resolved.resolution ? h('div.small.muted', `Resolution: ${n.resolved.resolution}`) : null);
        list.appendChild(el);
        for (const child of byParent.get(n.id) || []) renderNote(child, depth + 1);
      };
      for (const n of byParent.get('') || []) renderNote(n, 0);
      for (const [k, rows] of byParent) if (k && !mine.some((m) => m.id === k)) rows.forEach((n) => renderNote(n, 1));
    };
    const submit = () => withBusy(save, async () => {
      const text = ta.value.trim(); if (!text) return;
      await post('/api/notes', { target_type: type, target_id: id, target_label: label || id, text, reply_to: replyTo });
      ta.value = ''; replyTo = null; replyHint.classList.add('hidden');
      toast(reads && notesState.readNotes ? 'Note saved for future context selection. Existing requests are unchanged.' : 'Noted.', 'good');
      load();
    });
    save.addEventListener('click', submit);
    ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit(); });
    body.append(info, h('div.col', ta, replyHint, h('div.row', h('span.tiny.faint', 'Ctrl+Enter to save'), h('span.spacer'), save)), h('div.divider'), list);
    load();
    setTimeout(() => ta.focus(), 50);
  } });
}
