// Runesmith Studio: the shell (navigation, status, command palette, comment mode) and the router.
import { $, $$, h, icon, clear, get, post, bus, connectEvents, toast, notesState, openNotes, refreshNoteBadges,
  confirmDialog, debounce, ago, modal, withBusy, closeDrawers, humanize } from './core.js';
import { logoMark, wordmark } from './icons.js';

// What a job is called in plain words (the worker's JOB_WORDS), for toasts (journey J2-F9).
const JOB_WORDS = { propose_acceptance: 'Proposing acceptance checks', plan: 'Drafting a plan', goalposts: 'Proposing goalposts',
  draft: 'Drafting files', build: 'Building the next step', revise: 'Revising a draft', correct: 'Correcting a draft',
  escalate: 'Giving the step one more try', readmit: 'Checking a kept answer again', readmit_answer: 'Checking a kept answer again', supplement: 'Asking for missing files', breakdown: 'Proposing smaller steps',
  map: 'Mapping the folder', round: 'The round', measure: 'Taking a measurement',
  resume_check: 'Rechecking a draft whose checks did not finish', split: 'Breaking a stuck step down' };

const NAV = [
  { section: 'Workspace' },
  { id: 'home', label: 'Overview', icon: 'home', key: '1' },
  { id: 'dashboards', label: 'Dashboards', icon: 'gauge' },
  { id: 'map', label: 'Living map', icon: 'map', key: '2' },
  { id: 'work', label: 'Work & proposals', icon: 'inbox', key: '3', count: 'work' },
  { id: 'goals', label: 'Goals & plan', icon: 'target', key: '4' },
  { id: 'mission', label: 'Modes & measurements', icon: 'sliders' },
  { section: 'Runesmith' },
  { id: 'improve', label: 'Self-improvement', icon: 'spark', key: '5', count: 'improve' },
  { id: 'inference', label: 'Thinking power', icon: 'cpu', key: '6', count: 'inference' },
  { id: 'notes', label: 'Notes', icon: 'note', key: '7', count: 'notes' },
  { id: 'activity', label: 'Activity', icon: 'activity', key: '8' },
  { id: 'settings', label: 'Settings', icon: 'sliders', key: '9' },
];
const TITLES = Object.fromEntries(NAV.filter((n) => n.id).map((n) => [n.id, n.label]));
const VIEWS = { home: './views/home.js', map: './views/map.js', work: './views/work.js', goals: './views/goals.js',
  improve: './views/improve.js', inference: './views/inference.js', notes: './views/notes.js', activity: './views/activity.js',
  settings: './views/settings.js', mission: './views/mission.js', dashboards: './views/dashboards.js' };

export const app = { state: null, session: null, current: null, cleanup: null, navigate };
let shell = null;

// ------------------------------------------------------------------- theme --
function applyTheme(pref) {
  const mode = pref || localStorage.getItem('rs-theme') || 'auto';
  const dark = mode === 'dark' || (mode === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}
window.matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => applyTheme(app.state?.settings?.theme));

// -------------------------------------------------------------------- boot --
async function boot() {
  try { applyTheme(localStorage.getItem('rs-theme')); } catch { applyTheme('auto'); }
  const root = $('#root');
  const cinema = location.pathname === '/cinema' || location.hash.startsWith('#/cinema');
  if (cinema) {
    const { runGenesis } = await import('./genesis.js');
    return runGenesis(root, { cinema: true });
  }
  try { app.session = await get('/api/session'); }
  catch (e) {
    if (e.status === 401) return renderLocked(root);
    return renderDown(root, e.message);
  }
  applyTheme(app.session.settings.theme);
  if (!new URLSearchParams(location.search).has('shot')) connectEvents();     // a still for docs needs no live stream
  if (!app.session.settings.onboarded || location.hash.startsWith('#/genesis')) {
    const { runGenesis } = await import('./genesis.js');
    await runGenesis(root, { cinema: false });
    location.hash = '#/home';                            // the Overview holds the next steps
  }
  renderShell(root);
  await refreshState();
  // A real page change closes drawers; a page redrawing itself (navigate to the same page) keeps them.
  window.addEventListener('hashchange', () => { closeDrawers(); route(); });
  route();
  wireEvents();
}

function renderLocked(root) {
  clear(root).append(h('div.lock-screen', h('div.box',
    h('div', { html: logoMark({ forge: true }), style: { width: '72px', height: '72px', margin: '0 auto 18px' } }),
    h('h2', 'Runesmith Studio is locked'),
    h('p.muted', 'For your safety, the Studio opens only through the link its launcher prints. Start Runesmith again (double-click the launcher or run `runesmith` in your folder) and it will open this page for you.'),
    h('p.small.faint', 'Why: anything that can reach this page could otherwise act on your folder. The link carries a one-time key that stays in this browser.'))));
}
function renderDown(root, message) {
  clear(root).append(h('div.lock-screen', h('div.box', icon('power'), h('h2', 'Runesmith is not answering'), h('p.muted', message),
    h('button.btn.primary', { onclick: () => location.reload() }, icon('refresh'), 'Try again'))));
}

// ------------------------------------------------------------------- shell --
function renderShell(root) {
  const collapsed = localStorage.getItem('rs-collapsed') === '1';
  const nav = h('nav.nav');
  for (const item of NAV) {
    if (item.section) { nav.append(h('div.section', item.section)); continue; }
    nav.append(h('a', { href: `#/${item.id}`, dataset: { view: item.id }, title: item.key ? `${item.label}  (${item.key})` : item.label },
      icon(item.icon), h('span.label', item.label), item.count ? h('span.count.hidden', { dataset: { count: item.count } }) : null));
  }
  const ws = h('button.ws-switch', { type: 'button', title: 'Switch folder', onclick: () => import('./views/settings.js').then((m) => m.openFolderPicker()) },
    h('span.dot', '·'), h('span.label', h('b', '…'), h('span', '')));
  const collapse = h('button.btn.ghost.sm', { title: 'Collapse the sidebar', 'aria-label': 'Collapse or expand the sidebar', onclick: () => {
    const on = !$('.app').classList.contains('collapsed'); $('.app').classList.toggle('collapsed', on); localStorage.setItem('rs-collapsed', on ? '1' : '0');
  } }, icon('menu'), h('span.label', 'Collapse'));
  const sidebar = h('aside.sidebar',
    h('div.brand', h('div.mark', { html: logoMark() }), h('div.word', h('span.wm', { html: wordmark() }), h('small', 'Studio'))),
    nav, h('div.side-foot', ws, collapse));
  const pill = h('button.status-pill.idle', { title: 'What Runesmith is doing (click for details)', onclick: () => {
    if (app.state?.manual_waiting) import('./views/inference.js').then((m) => m.openRelayDrawer());
    else if (app.state && !app.state.ready.any) navigate('inference');
    else navigate('activity');
  } },
    h('span.led'), h('span.ellipsis', 'Starting…'));
  const runBtn = h('button.btn.primary.sm', { title: 'Run a round now: map, find work, work, report', onclick: (e) => runNow(e.currentTarget) }, icon('play'), h('span', 'Run now'));
  const pauseBtn = h('button.btn.sm', { title: 'Pause or resume all work: scheduled rounds and the jobs you start', onclick: (e) => togglePause(e.currentTarget) }, icon('pause'), h('span', 'Pause'));
  const commentBtn = h('button.btn.sm.icon', { title: 'Comment on anything (C)', 'aria-label': 'Comment mode: comment on anything (C)', 'aria-pressed': 'false',
    onclick: toggleCommentMode }, icon('note'));
  const cmdBtn = h('button.btn.sm.ghost', { title: 'Command palette (Ctrl+K)', 'aria-label': 'Command palette (Ctrl+K)', onclick: openPalette }, icon('command'), h('span.kbd', 'Ctrl K'));
  const themeBtn = h('button.btn.sm.icon.ghost', { title: 'Light or dark', 'aria-label': 'Switch between light and dark', onclick: cycleTheme }, icon('sun'));
  const topbar = h('header.topbar', h('div.col.gap-4', { style: { gap: '0' } }, h('h1', { tabindex: '-1' }, ''), h('div.crumb', '')), h('span.spacer'),
    pill, runBtn, pauseBtn, commentBtn, cmdBtn, themeBtn);
  const content = h('main.content', { id: 'main', tabindex: '-1' });
  shell = { sidebar, pill, runBtn, pauseBtn, topbar, content, ws, commentBtn };
  const skip = h('button.skip-link', { type: 'button', onclick: () => content.focus() }, 'Skip to the page');
  nav.setAttribute('aria-label', 'Pages');
  clear(root).append(skip, h('div', { class: `app${collapsed ? ' collapsed' : ''}` }, sidebar, h('div.main', topbar, content)));
  document.addEventListener('keydown', onKey);
  document.addEventListener('keydown', onCommentKey, true);
  document.addEventListener('click', onCommentClick, true);
}

async function runNow(btn) {
  await withBusy(btn, async () => {
    // What a scheduled round would run now: a build step when building is on (journey J11-F11).
    const job = await post('/api/worker/run', { job: 'next' });
    toast({ round: 'A round is queued: map, find work, work, report.', build: 'A build step is queued: the next milestone that can move.',
      mode: 'The next work mode is queued.' }[job.kind] || 'Queued.', 'good');
  });
}
async function togglePause(btn) {
  const paused = app.state?.worker?.paused;
  await withBusy(btn, () => post(`/api/worker/${paused ? 'resume' : 'pause'}`, {}));
  refreshState();
}
function cycleTheme() {
  const now = document.documentElement.dataset.theme;
  const next = now === 'dark' ? 'light' : 'dark';
  localStorage.setItem('rs-theme', next);
  applyTheme(next);
  post('/api/settings', { theme: next }).catch(() => {});
}

// ------------------------------------------------------------------- state --
export async function refreshState() {
  try { app.state = await get('/api/state'); } catch (e) { return; }
  const s = app.state;
  notesState.counts = s.note_counts || {}; notesState.readNotes = s.settings.read_notes;
  refreshNoteBadges();
  const name = s.workspace.name || 'Workspace';
  const [dot, label] = [shell.ws.querySelector('.dot'), shell.ws.querySelector('.label')];
  dot.textContent = name.trim().charAt(0).toUpperCase() || 'R';
  label.querySelector('b').textContent = name; label.querySelector('span').textContent = s.workspace.path;
  const struggling = s.attention && ['SUSPECTED_BLOCKAGE', 'SUBJECT_BLOCKED'].includes(s.attention.mode);
  const counts = { work: (s.proposals.waiting || 0) + (s.drafts.waiting || 0), notes: s.notes_open, inference: s.manual_waiting,
    improve: struggling ? '!' : 0 };
  for (const el of $$('[data-count]', shell.sidebar)) {
    const v = counts[el.dataset.count];
    el.textContent = v || ''; el.classList.toggle('hidden', !v);
    el.classList.toggle('hot', el.dataset.count === 'inference' && !!v);
  }
  updatePill();
  const paused = s.worker.paused;
  shell.pauseBtn.replaceChildren(icon(paused ? 'play' : 'pause'), h('span', paused ? 'Resume' : 'Pause'));
  setTitle();
}
/** The window title names the page and the folder: what a screen reader announces and a taskbar shows. */
function setTitle() {
  const page = $('h1', shell.topbar).textContent;
  const name = app.state?.workspace?.name;
  document.title = [page, name, 'Runesmith Studio'].filter(Boolean).join(' · ');
}
function updatePill() {
  const s = app.state; if (!s) return;
  const w = s.worker;
  let cls = 'idle', text;
  if (s.manual_waiting) { cls = 'needs'; text = `Needs you: ${s.manual_waiting} request to relay to a chat model`; }
  else if (w.current) { cls = 'busy'; text = w.detail || `${w.status}…`; }
  else if (w.paused) { cls = 'paused'; const waiting = (w.queue || []).length; text = waiting ? `Paused · ${waiting} waiting until you resume` : 'Paused'; }
  else if (s.settings.autonomy === 'observe') { text = 'Just looking: maps and reports, asks no model'; }
  else if (!s.ready.any) { cls = 'needs'; text = 'Mapping only: add thinking power to let it work'; }
  else if (w.next_round_utc) { text = `Idle · next round ${ago(w.next_round_utc)}`; }
  else text = s.settings.auto_work ? 'Idle' : 'Idle · scheduled work is off';
  shell.pill.className = `status-pill ${cls}`;
  shell.pill.querySelector('span:last-child').textContent = text;
}

function wireEvents() {
  const later = debounce(refreshState, 350);
  for (const k of ['worker', 'round', 'work', 'notes', 'manual', 'map', 'settings', 'improve', 'inference', 'goals', 'plan', 'job', 'mission'])
    bus.on(k, later);
  bus.on('worker', (w) => { if (app.state) { app.state.worker = w; updatePill(); } });
  bus.on('needs', (d) => {
    if (d.what === 'inference') toast('Runesmith needs a Worker model to repair code. Add one under Thinking power.', 'warn', 8000);
    if (d.what === 'reachability') toast(`Model not reachable: ${d.detail}`, 'warn', 8000);
  });
  bus.on('job', (j) => {
    if (j.result === 'failed') toast(`${JOB_WORDS[j.kind] || humanize(j.kind)} did not finish: ${j.outcome?.error || ''}`, 'bad', 8000);
  });
  let lastWaiting = 0;
  bus.on('manual', (d) => {
    const n = d && typeof d.waiting === 'number' ? d.waiting : null;
    // A new request can replace an answered one at the same count (journey J2-B4), so `new` is announced too.
    if (n !== null && (d.new > 0 || n > lastWaiting) && !location.hash.startsWith('#/inference')) {
      actionToast('Runesmith needs you: a request is ready to relay to your chat model.', 'Open the relay',
        () => import('./views/inference.js').then((m) => m.openRelayDrawer()));
    }
    if (n !== null) lastWaiting = n;
  });
  bus.on('workspace', () => location.reload());
  bus.on('settings', (st) => { if (st && st.theme) { try { localStorage.setItem('rs-theme', st.theme); } catch { /* private mode */ } applyTheme(st.theme); } });
  bus.on('connection', ({ up }) => { if (!up && shell) { shell.pill.className = 'status-pill paused'; shell.pill.querySelector('span:last-child').textContent = 'Reconnecting to Runesmith…'; } else refreshState(); });
}

function actionToast(text, label, run) {
  let box = $('.toasts');
  if (!box) { box = h('div.toasts'); document.body.appendChild(box); }
  const el = h('div.toast.warn', { role: 'alert' }, icon('chat'), h('div.grow', text,
    h('div.mt-8', h('button.btn.sm.primary', { onclick: () => { el.remove(); run(); } }, label))),
    h('button.btn.icon.sm.ghost', { title: 'Dismiss', onclick: () => el.remove() }, icon('x')));
  box.appendChild(el);
  setTimeout(() => el.remove(), 20000);
}

// ------------------------------------------------------------------ router --
async function route() {
  const hash = location.hash.replace(/^#\/?/, '') || 'home';
  const [path, qs] = hash.split('?');
  const [view, ...rest] = path.split('/');
  const name = VIEWS[view] ? view : 'home';
  for (const a of $$('.nav a')) {
    a.classList.toggle('active', a.dataset.view === name);
    if (a.dataset.view === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  $('h1', shell.topbar).textContent = TITLES[name];
  $('.crumb', shell.topbar).textContent = app.state ? app.state.workspace.name : '';
  setTitle();
  const moved = (route.visits = (route.visits || 0) + 1) > 1;       // after the first page, a new page takes the focus
  if (app.cleanup) { try { app.cleanup(); } catch { /* ignore */ } app.cleanup = null; }
  const page = h('div.page');
  const loading = h('div.page-loading', h('div.skeleton'), h('div.skeleton'), h('div.skeleton'));
  const token = (route.token = (route.token || 0) + 1);
  clear(shell.content).append(loading);
  shell.content.scrollTop = 0;
  try {
    const mod = await import(VIEWS[name]);
    const cleanup = await mod.default(page, { app, sub: rest, params: new URLSearchParams(qs || ''), navigate, refreshState });
    if (token !== route.token) { if (typeof cleanup === 'function') cleanup(); return; }   // the owner already moved on
    app.cleanup = cleanup;
    clear(shell.content).append(page);
    // Keyboard and screen-reader users start on the new page's heading, not where the old page was.
    if (moved && !page.contains(document.activeElement) && !$('.modal-wrap, .drawer, .cmdk')) $('h1', shell.topbar).focus({ preventScroll: true });
  } catch (e) {
    console.error(e);
    if (token !== route.token) return;
    clear(shell.content).append(page);
    page.append(h('div.card', h('h3', icon('alert'), 'This page could not load'), h('p.muted', e.message || String(e)),
      h('button.btn.mt-8', { onclick: route }, icon('refresh'), 'Try again')));
  }
}
// Navigating to the page already shown draws it again, so a change made on it (a switch, a setting) shows at once.
export function navigate(view, sub) {
  const target = `#/${view}${sub ? '/' + sub : ''}`;
  if (location.hash === target) route(); else location.hash = target;
}

// ------------------------------------------------------------ comment mode --
function toggleCommentMode(force) {
  const on = typeof force === 'boolean' ? force : !document.body.classList.contains('comment-mode');
  document.body.classList.toggle('comment-mode', on);
  shell.commentBtn.classList.toggle('primary', on);
  shell.commentBtn.setAttribute('aria-pressed', String(on));
  $('.comment-banner')?.remove();
  if (on) document.body.append(h('div.comment-banner', { role: 'status' }, icon('note'),
    'Comment mode: click anything, or Tab to it and press Enter, to talk to Runesmith about it', h('span.kbd', 'Esc')));
}
function commentOn(el) {
  const [type, id] = el.dataset.note.split('|');
  toggleCommentMode(false);
  openNotes(type, id, el.dataset.noteLabel);
}
function onCommentClick(e) {
  if (!document.body.classList.contains('comment-mode')) return;
  const el = e.target.closest('[data-note]');
  if (!el || e.target.closest('.drawer, .modal, .comment-banner')) return;
  e.preventDefault(); e.stopPropagation();
  commentOn(el);
}
function onCommentKey(e) {       // capture phase: in comment mode, Enter on anything commentable opens its notes
  if (!document.body.classList.contains('comment-mode') || (e.key !== 'Enter' && e.key !== ' ') || typing(e)) return;
  const el = e.target.closest && e.target.closest('[data-note]');
  if (!el || e.target.closest('.drawer, .modal, .comment-banner, .note-btn')) return;
  e.preventDefault(); e.stopPropagation();
  commentOn(el);
}

// ---------------------------------------------------------------- keyboard --
function typing(e) { const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable); }
function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); return; }
  if (e.key === 'Escape' && document.body.classList.contains('comment-mode')) { toggleCommentMode(false); return; }
  if (typing(e) || e.ctrlKey || e.metaKey || e.altKey || $('.modal-wrap, .drawer, .cmdk')) return;
  if (e.key === 'c' || e.key === 'C') { toggleCommentMode(); return; }
  if (e.key === 'r' || e.key === 'R') { runNow(shell.runBtn); return; }
  if (e.key === '?') { showShortcuts(); return; }
  const item = NAV.find((n) => n.key === e.key);
  if (item) navigate(item.id);
}
function showShortcuts() {
  const rows = [['Ctrl K', 'Command palette'], ['C', 'Comment on anything'], ['R', 'Run a round now'], ['1 – 9', 'Go to a page'], ['Esc', 'Close'], ['?', 'This list']];
  modal({ title: 'Keyboard shortcuts', body: h('table.table', rows.map(([k, v]) => h('tr', h('td', h('span.kbd', k)), h('td', v)))),
    actions: [{ label: 'Close', kind: 'primary' }] });
}

// ----------------------------------------------------------------- palette --
function openPalette() {
  if ($('.cmdk')) return;
  const cmds = [
    ...NAV.filter((n) => n.id).map((n) => ({ label: `Go to ${n.label}`, icon: n.icon, key: n.key, run: () => navigate(n.id) })),
    { label: 'Run a round now', icon: 'play', key: 'R', run: () => runNow(shell.runBtn) },
    { label: 'Re-map the folder (measure tests too)', icon: 'map', run: () => post('/api/worker/run', { job: 'map', params: { probe: true } }).then(() => toast('Mapping queued', 'good')) },
    { label: 'Draft a plan from the brief', icon: 'wand', run: () => post('/api/worker/run', { job: 'plan' }).then(() => toast('The planner is on it', 'good')) },
    { label: 'Add thinking power (a model)', icon: 'cpu', run: () => { navigate('inference'); setTimeout(() => bus.emit('ui:add-model', {}), 300); } },
    { label: 'Comment on the whole workspace', icon: 'note', run: () => openNotes('workspace', 'root', 'the whole workspace') },
    { label: 'Comment mode (click anything)', icon: 'note', key: 'C', run: () => toggleCommentMode(true) },
    { label: 'Check health', icon: 'shield', run: () => navigate('settings', 'health') },
    { label: 'Switch folder', icon: 'folder', run: () => import('./views/settings.js').then((m) => m.openFolderPicker()) },
    { label: 'Replay the introduction', icon: 'flame', run: () => { location.hash = '#/genesis'; location.reload(); } },
    { label: 'Open the intro in cinema mode (for sharing)', icon: 'maximize', run: () => window.open('/cinema', '_blank') },
    { label: 'Pause or resume all work', icon: 'pause', run: () => togglePause(shell.pauseBtn) },
    { label: 'Stop the current job after this step', icon: 'stop', run: () => post('/api/worker/stop', {}).then(() => toast('Stopping after the current step.', 'good')) },
    { label: 'Toggle light / dark', icon: 'sun', run: cycleTheme },
    { label: 'Keyboard shortcuts', icon: 'keyboard', key: '?', run: showShortcuts },
  ];
  const input = h('input', { placeholder: 'Type a command or a page…', 'aria-label': 'Command', role: 'combobox', 'aria-expanded': 'true',
    'aria-controls': 'cmdk-list', 'aria-autocomplete': 'list' });
  const opts = h('div.opts#cmdk-list', { role: 'listbox', 'aria-label': 'Commands' });
  let sel = 0, shown = cmds;
  const draw = () => {
    const q = input.value.toLowerCase().trim();
    shown = cmds.filter((c) => !q || c.label.toLowerCase().includes(q));
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    // options are chosen from the input (arrows, Enter) or by mouse: they are not separate Tab stops
    clear(opts).append(...shown.map((c, i) => {
      const opt = h('div', { class: `opt${i === sel ? ' on' : ''}`, id: `cmdk-${i}`, role: 'option', 'aria-selected': String(i === sel) },
        icon(c.icon), h('span', c.label), c.key ? h('span.kbd', c.key) : null);
      opt.addEventListener('click', () => { close(); c.run(); });
      return opt;
    }));
    if (shown.length) input.setAttribute('aria-activedescendant', `cmdk-${sel}`); else input.removeAttribute('aria-activedescendant');
    opts.children[sel]?.scrollIntoView({ block: 'nearest' });
  };
  const opener = document.activeElement;
  const wrap = h('div.cmdk', h('div.box', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Command palette' }, input, opts));
  const scrim = h('div.scrim');
  const close = () => { wrap.remove(); scrim.remove(); if (opener && opener.isConnected) opener.focus({ preventScroll: true }); };
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close(); });
  input.addEventListener('input', () => { sel = 0; draw(); });
  input.addEventListener('keydown', (e) => {
    // Enter and Escape are consumed: closing hands the focus back to the opener, and the same key must not then
    // press that button too (journey J9-B1: "Go to Notes" + Enter opened Goals & plan through the focused button).
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, shown.length - 1); draw(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); draw(); e.preventDefault(); }
    else if (e.key === 'Enter' && shown[sel]) { e.preventDefault(); close(); shown[sel].run(); }
  });
  document.body.append(scrim, wrap);
  draw();
  input.focus();
}

boot();
