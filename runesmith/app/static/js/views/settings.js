// Settings: how Runesmith behaves here, health checks, data, the folder, and what Runesmith has (and has not) shown.
import { h, icon, get, post, bus, toast, clear, ago, plural, humanize, withBusy, confirmDialog, modal, empty, askText, $ } from '../core.js';

export default async function render(root, ctx) {
  const tab = ['behaviour', 'health', 'data', 'about'].includes(ctx.sub[0]) ? ctx.sub[0] : 'behaviour';
  const head = h('div.page-head', h('div', h('h2', 'Settings'), h('p', 'How Runesmith behaves in this folder. Settings and history live in its registered Runesmith home, which can be separate from the project.')));
  const tabs = h('div.tabs', [['behaviour', 'Behaviour', 'sliders'], ['health', 'Health', 'shield'], ['data', 'Folder & data', 'folder'], ['about', 'About & evidence', 'info']]
    .map(([id, l, ic]) => h('button', { class: id === tab ? 'on' : '', onclick: () => ctx.navigate('settings', id) }, icon(ic), l)));
  const body = h('div');
  root.append(head, tabs, body);
  ({ behaviour, health, data, about })[tab](body, ctx);
}

async function behaviour(body, ctx) {
  const s = await get('/api/settings');
  const env = await get('/api/map/environment');
  const save = async (patch, msg) => {
    try { const r = await post('/api/settings', patch); Object.assign(s, r); toast(msg || 'Saved', 'good', 1800); ctx.refreshState(); }
    catch (e) { toast(e.message, 'bad'); }
  };
  const POLICY = new Set(['auto_work', 'probe_tests', 'kaizen']);   // the owner's first-run choices (see Overview)
  const toggle = (key, label, text, onMsg) => h('div.setting', h('div.text', h('b', label), h('span', text)),
    h('label.switch', h('input', { type: 'checkbox', checked: s[key], 'aria-label': label, onchange: (e) => save(
      { [key]: e.target.checked, ...(POLICY.has(key) ? { policy_chosen: true } : {}) }, onMsg && onMsg(e.target.checked)) }), h('span')));
  // The button is taken before saving: after an await the click event no longer knows which button it came from.
  const seg = (key, options) => h('div.seg', options.map(([v, l, ic]) => h('button', { class: s[key] === v ? 'on' : '', 'aria-pressed': String(s[key] === v),
    onclick: async (e) => { const chosen = e.currentTarget; await save({ [key]: v });
      for (const b of chosen.parentNode.children) { b.classList.toggle('on', b === chosen); b.setAttribute('aria-pressed', String(b === chosen)); } } },
    ic ? icon(ic) : null, l)));
  const name = h('input.input', { value: s.workspace_name, 'aria-label': 'Name of this workspace', style: { maxWidth: '320px' } });
  name.addEventListener('change', () => save({ workspace_name: name.value }));
  const interval = h('select.select', { style: { width: '180px' }, onchange: () => save({ interval_minutes: Number(interval.value) }) },
    [[5, 'every 5 minutes'], [15, 'every 15 minutes'], [30, 'every 30 minutes'], [60, 'every hour'], [180, 'every 3 hours'], [720, 'twice a day'], [1440, 'once a day']]
      .map(([v, l]) => h('option', { value: v, selected: Number(s.interval_minutes) === v }, l)));
  if (![5, 15, 30, 60, 180, 720, 1440].includes(Number(s.interval_minutes))) interval.append(h('option', { value: s.interval_minutes, selected: true }, `every ${s.interval_minutes} minutes`));
  const objects = (env.map?.objects || []).filter((o) => !o.root && o.reason !== 'link').map((o) => o.name);   // a link is never read anyway
  const exclude = new Set(s.exclude);
  const exChips = h('div.pillbox', objects.length ? objects.map((n) => h('button', { class: `chip${exclude.has(n) ? ' on' : ''}`, 'aria-pressed': String(exclude.has(n)), onclick: async (e) => {
    exclude.has(n) ? exclude.delete(n) : exclude.add(n); e.currentTarget.classList.toggle('on'); e.currentTarget.setAttribute('aria-pressed', String(exclude.has(n))); await save({ exclude: [...exclude] }, exclude.has(n) ? `${n} will never be touched` : `${n} is included`);
    post('/api/worker/run', { job: 'map' }); } }, exclude.has(n) ? icon('lock') : null, n)) : h('span.small.faint', 'No sub-folders mapped yet.'));
  const num = (key, label, text, min, max) => {
    const input = h('input.input', { type: 'number', min, max, value: s[key], 'aria-label': label, style: { width: '100px' } });
    input.addEventListener('change', () => save({ [key]: Number(input.value) }));
    return h('div.setting', h('div.text', h('b', label), h('span', text)), input);
  };
  body.append(h('div.grid.two',
    h('div.col.gap-16',
      h('div.card', h('h3', icon('home'), 'This workspace'),
        h('div.setting', h('div.text', h('b', 'Name'), h('span', 'What you build here. Shown everywhere in the Studio.')), name),
        h('div.setting', h('div.text', h('b', 'How Runesmith may act'), h('span', 'Observe: just look. Runesmith maps and reports, and asks no model. Propose: it also plans, drafts and brings you changes to review. Your files change only when you approve a change, or when you allow automatic apply for checked builds.')),
          seg('autonomy', [['observe', 'Observe', 'eye'], ['propose', 'Propose', 'hammer']]))),
      h('div.card', h('h3', icon('clock'), 'Rhythm'),
        toggle('auto_work', 'Work on a schedule', 'Run rounds automatically while the Studio is open. Each round can spend model calls. Off until you choose.'),
        h('div.setting', h('div.text', h('b', 'How often'), h('span', 'A round maps, finds work, works on what is new, and reports. With full speed on, the longest wait.')), interval),
        toggle('full_speed', 'Full speed', 'Start the next step as soon as one ends, while the models answer. When none answers (busy or at its limit), wait 1, 2, 4 … minutes, never longer than above; when there is nothing to do, 2 minutes. Uses the free allowances faster.')),
      // Journey J11-G42, G43: a project that runs to the end of its plan without its owner. Both wait for you until you choose.
      h('div.card', h('h3', icon('shield'), 'Running on its own'),
        h('div.setting', h('div.text', h('b', 'After an interrupted job'), h('span', 'If the Studio is restarted while a job runs, you normally review what was left before anything continues. “Keep and continue” lets Runesmith keep the waiting work and go on by itself. The interrupted job is never run again, and what it decided is said on the Overview.')),
          seg('recovery_policy', [['wait', 'Wait for me'], ['keep', 'Keep and continue']])),
        h('div.setting', h('div.text', h('b', 'When a milestone’s tries are used up'), h('span', 'Three tries, and then it waits for you. “One more try” gives it the one extra try with another model, as the button on Work does; “then break it down” also asks for smaller steps and adopts them, once. Other milestones keep building meanwhile, and each decision is said on the Overview.')),
          seg('stuck_policy', [['wait', 'Wait for me'], ['retry', 'One more try'], ['retry_split', 'One more try, then break it down']])),
        h('div.setting', h('div.text', h('b', 'When a draft’s checks did not finish'), h('span', 'Checks that run out of time wait for you to press “Resume timed-out check once” on Work. “Recheck once” lets Runesmith run them once more itself, with a longer limit and no model call, once for each draft. What it did is said on the Overview.')),
          seg('recheck_policy', [['wait', 'Wait for me'], ['recheck', 'Recheck once']]))),
      h('div.card', h('h3', icon('map'), 'Mapping'),
        toggle('probe_tests', 'Measure code by running its tests', 'This executes the project’s own code, on a throwaway copy of the folder, so nothing is written into it. Only for projects you trust: the copy is not a security boundary. Off until you choose.'),
        num('max_objects', 'Most objects to map', 'For very large folders.', 1, 500),
        h('div.setting', h('div.text', h('b', 'Never touch'), h('span', 'Excluded folders are listed on the map but never read, probed or worked on.'), h('div.mt-8', exChips))))),
    h('div.col.gap-16',
      h('div.card', h('h3', icon('note'), 'Notes'),
        toggle('read_notes', 'Give notes to the model', 'Your open notes travel with the work they are about, labelled as your guidance.')),
      h('div.card', h('h3', icon('spark'), 'Self-improvement'),
        toggle('kaizen', 'Let Runesmith improve itself', 'Kaizen campaigns rewrite its repair organ from its own experience. A candidate is only ever activated by winning a trial on your work.'),
        num('min_experience', 'Experience before the first campaign', 'Stored repair attempts needed.', 2, 10000),
        num('kaizen_every', 'New attempts between campaigns', 'So every campaign works from fresh evidence.', 1, 10000)),
      h('div.card', h('h3', icon('sun'), 'Appearance'),
        h('div.setting', h('div.text', h('b', 'Theme'), h('span', 'Auto follows your computer.')), seg('theme', [['auto', 'Auto', 'monitor'], ['light', 'Light', 'sun'], ['dark', 'Dark', 'moon']]))),
        h('div.setting', h('div.text', h('b', 'Introduction'), h('span', 'Replay the opening sequence, or open it full-screen to share.')),
          h('div.row', h('button.btn.sm', { onclick: () => { location.hash = '#/genesis'; location.reload(); } }, icon('flame'), 'Replay'), h('button.btn.sm', { onclick: () => window.open('/cinema', '_blank') }, icon('maximize'), 'Cinema'))))));
}

async function health(body) {
  const list = h('div.list');
  const run = async (network) => {
    clear(list).append(h('div.skeleton', { style: { height: '120px' } }));
    const data = await get(`/api/health?network=${network ? 1 : 0}`);
    clear(list);
    for (const c of data.checks) list.append(h('div.item', h('div', { class: `ico ${c.ok === true ? 'good' : c.ok === false ? 'bad' : 'warn'}` }, icon(c.ok === true ? 'check' : c.ok === false ? 'x' : 'info')),
      h('div.body', h('div.title', humanize(c.check)), h('div.meta', c.detail), c.fix ? h('div.small', { style: { color: 'var(--accent)' } }, `Fix: ${c.fix}`) : null)));
  };
  const net = h('button.btn', icon('globe'), 'Also check the models over the network');
  net.addEventListener('click', () => withBusy(net, () => run(true)));
  body.append(h('div.card', h('div.card-head', h('h3', icon('shield'), 'Health'), h('div.actions', net)), list));
  run(false);
}

async function data(body, ctx) {
  const s = ctx.app.state;
  const reveal = (which) => post('/api/reveal', { which }).catch((e) => toast(e.message, 'bad'));
  const snap = h('button.btn', icon('download'), 'Export a snapshot');
  snap.addEventListener('click', () => withBusy(snap, async () => { const r = await post('/api/snapshot', {}); toast(`Snapshot saved (keys left out): ${r.file}`, 'good', 9000); }));
  const quit = h('button.btn.danger', icon('power'), 'Quit Runesmith Studio');
  quit.addEventListener('click', async () => { if (await confirmDialog({ title: 'Quit the Studio?', text: 'Runesmith stops working until you start it again. Nothing is lost.', confirm: 'Quit', danger: true })) { await post('/api/shutdown', {}); document.body.innerHTML = '<div class="lock-screen"><div class="box"><h2>Runesmith Studio has stopped.</h2><p class="muted">Start it again from its launcher or with <code>runesmith</code> in your folder.</p></div></div>'; } });
  body.append(h('div.grid.two',
    h('div.card', h('h3', icon('folder'), 'The folder'), h('p.mono.small', s.workspace.path),
      h('div.row.wrap', h('button.btn.primary', { onclick: () => openFolderPicker() }, icon('folder'), 'Work in another folder'), h('button.btn', { onclick: () => reveal('workspace') }, icon('external'), 'Open in file manager')),
      h('div.divider'), h('h3', icon('rune'), 'Runesmith’s home for this folder'), h('p.mono.small', s.workspace.home),
      h('p.small.muted', 'Everything Runesmith learns about this folder lives here: settings, the ledger, maps, generations, notes and saved keys. It ignores itself for version control, so it is never committed by accident.'),
      h('div.row.wrap', h('button.btn', { onclick: () => reveal('home') }, icon('external'), 'Open the home'), snap)),
    h('div.card', h('h3', icon('power'), 'Session'), h('p.small.muted', `Runesmith ${s.version}. The Studio runs on this computer only (127.0.0.1) and opens through a private link.`), quit)));
}

async function about(body) {
  const row = (claim, status, cls) => h('tr', h('td', claim), h('td', h('span', { class: `badge ${cls}` }, status)));
  body.append(h('div.grid.two',
    h('div.card', h('h3', icon('rune'), 'What Runesmith is'),
      h('p', 'A small, fixed kernel that keeps budgets, authority, judges and a hash-chained ledger, and wears any model as an instrument. Its repair organ is the only part that changes, and it changes only with evidence: experience is split, candidates are tested on held-out work, and a winner must still win a live trial before it is switched on.'),
      h('p.muted', 'It maps your folder and itself, proposes objectives in bands (bad · minimal · optimal · world-class), and says “unknown” wherever it has no evidence.'),
      h('div.divider'), h('div.small.faint', 'Open source. Standard-library Python, no build step, runs on modest computers.')),
    h('div.card', h('h3', icon('beaker'), 'What has been shown, and what has not'),
      h('p.small.muted', 'Runesmith is developed as a falsifiable research programme: a claim counts only when a preregistered, sealed experiment measured it. Negative results are reported with the same weight.'),
      h('table.table.small', h('tr', h('th', 'Claim'), h('th', 'Status')),
        row('A self-authored generation repairs more fresh tasks than its predecessor (SR7: 57 vs 35 of 162 attempts at 54 unseen tasks, p = 0.00085; synthetic single-line bugs, one cheap model)', 'shown once', 'good'),
        row('Free-class models as the self-improvement author (SR5, SR6)', 'not shown', ''),
        row('The suit makes a 2.6B free model repair more than a strong simple scaffold (SR6-W: 5 vs 12 of 68)', 'not shown', ''),
        row('Organ confinement (no files, network, subprocesses or secrets)', 'unit-tested', 'rune'),
        row('Natural bugs, other task families, economic value', 'not tested', 'warn')))));
}

// ------------------------------------------------------------ folder picker --
export async function openFolderPicker() {
  const list = h('div.folder-list');
  const pathInput = h('input.input.mono', { placeholder: 'Type or paste a folder path', 'aria-label': 'Workspace folder path' });
  const homeInput = h('input.input.mono', { placeholder: 'Automatic: registered home, otherwise <folder>/.runesmith', 'aria-label': 'Runesmith home path (optional)' });
  const pairNotice = h('div.small.muted.mt-8', { 'aria-live': 'polite' }, 'The exact folder and home will be shown for confirmation before anything opens.');
  const recentBox = h('div.pillbox.mb-8');
  const notice = h('div.callout.mt-8', { role: 'status', 'aria-live': 'polite' });
  let switching = false, uncertain = false, active = true, guard = null, m;
  const paintGuard = () => {
    clear(notice);
    notice.append(h('div', guard?.policy || 'Waiting jobs stay in their original home. A different home opens paused; review it before Resume.'));
    for (const reason of guard?.blockers || []) notice.append(h('div', reason));
    if (guard?.warning) notice.append(h('div', guard.warning));
    if (guard?.waiting) notice.append(h('div', `${guard.waiting} waiting job(s) will remain saved here.`));
    if (uncertain) notice.append(h('div', 'The switch outcome is uncertain. Reload Studio to inspect its selected folder; do not resubmit.'));
    for (const button of m?.el.querySelectorAll('[data-switch-action]') || []) {
      button.disabled = switching || uncertain || !guard?.allowed;
    }
    pathInput.disabled = homeInput.disabled = switching || uncertain;
  };
  const refreshGuard = async () => {
    try { guard = (await get('/api/workspaces')).switch; }
    catch (error) { guard = { allowed: false, blockers: [error.message] }; }
    paintGuard();
  };
  const switchTo = async (path, create, close) => {
    if (!active || switching || uncertain || !guard?.allowed) return false;
    if (!path?.trim()) { toast('Choose an explicit folder path.', 'warn'); return false; }
    const requestedHome = homeInput.value.trim();
    ++browseVersion;
    switching = true; paintGuard();
    let submitted = false;
    try {
      const pair = await get(`/api/workspaces/resolve?path=${encodeURIComponent(path.trim())}${requestedHome ? '&home=' + encodeURIComponent(requestedHome) : ''}`);
      if (!active) return false;
      clear(pairNotice).append(h('div', `Folder: ${pair.path}`), h('div', `Home: ${pair.home}`));
      const confirmed = await confirmDialog({ title: 'Open this folder and home?',
        text: h('div.workspace-pair', h('p', create ? 'Create this project folder:' : 'Project folder:'), h('p.mono.small', pair.path),
          h('p', `${pair.registered ? 'Registered' : pair.basis === 'explicit' ? 'Separate' : 'Default'} Runesmith home:`), h('p.mono.small', pair.home),
          h('p.small.muted', 'Settings, saved keys, queues and history belong to this home. This does not move them or rebind an existing home. A different home opens paused.')),
        confirm: create ? 'Create and open this pair' : 'Open this pair' });
      if (!confirmed || !active) return false;
      submitted = true;
      const result = await post('/api/workspaces/open', { path: pair.path, home: pair.home, create });
      close(); toast(result.warning || 'Folder selected. Review its settings before resuming work.', result.warning ? 'warn' : 'good');
      bus.emit('workspace', { path: result.path, reload: true });
    } catch (error) {
      uncertain = submitted && (error.status === 0 || error.status >= 500);
      guard = { allowed: false, blockers: [error.message] };
      toast(error.message, 'bad');
    } finally { switching = false; paintGuard(); }
    return false;
  };
  let current = '', browseVersion = 0;
  const browse = async (path) => {
    const version = ++browseVersion;
    try {
      const r = await get(`/api/browse?path=${encodeURIComponent(path || '')}`);
      if (version !== browseVersion || switching || !active) return;
      current = r.path; pathInput.value = r.path;
      clear(list);
      if (r.parent !== null && r.path) list.append(h('div.f', { onclick: () => browse(r.parent) }, icon('up'), h('span', '.. (up)')));
      for (const d of r.dirs) list.append(h('div.f', { onclick: () => browse(d.path) }, icon('folder'), h('span', d.name)));
      if (!r.dirs.length) list.append(h('div.f.faint', 'No sub-folders here.'));
    } catch (e) { if (version === browseVersion) toast(e.message, 'bad'); }
  };
  const edited = () => { browseVersion++; clear(pairNotice).append('Selection edited; the folder and home will be reviewed again before opening.'); };
  pathInput.addEventListener('input', edited);
  homeInput.addEventListener('input', edited);
  const ws = await get('/api/workspaces');
  guard = ws.switch;
  for (const r of ws.recent.slice(0, 8)) recentBox.append(h('button', { class: `chip${r.path === ws.current ? ' on' : ''}`, title: r.path + (r.home ? '\nHome: ' + r.home : ''), onclick: () => browse(r.path) }, icon('clock'), r.name || r.path));
  pathInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') browse(pathInput.value); });
  m = modal({ title: 'Choose a folder', onClose: () => { active = false; ++browseVersion; }, text: 'Select one active workspace. Switching waits for idle work, transfers home ownership and opens a different home paused. It does not run two projects concurrently.',
    body: h('div', ws.recent.length ? [h('div.label-text', 'Recent'), recentBox] : null,
      h('div.label-text', 'Project folder'), h('div.row', pathInput, h('button.btn', { onclick: () => browse(pathInput.value) }, 'Go')), h('div.mt-8', list),
      h('div.label-text.mt-8', 'Runesmith home — optional separate location'), homeInput,
      h('p.small.muted.mt-8', 'Leave blank to reuse the registered home. A new project defaults to .runesmith inside its folder. Existing bindings cannot be changed here.'), pairNotice,
      h('p.small.faint.mt-8', 'Participating Studio and one-shot workers in this user profile exclude overlapping folders and homes. This is not a sandbox for other apps or legacy direct writers.'), notice,
      h('button.btn.mt-8', { onclick: refreshGuard }, 'Refresh switch readiness'),
      h('button.btn.ghost.mt-8', { onclick: () => bus.emit('workspace', { reload: true }) }, 'Reload selected workspace')),
    actions: [{ label: 'Cancel', kind: 'ghost' },
      { label: 'New folder here…', icon: 'plus', onClick: async (close) => {
        if (switching || uncertain || !guard?.allowed) return false;
        if (!pathInput.value.trim()) { toast('Choose an explicit folder path.', 'warn'); return false; }
        const parent = pathInput.value.trim();
        ++browseVersion; // Outstanding navigation cannot retarget this confirmation.
        switching = true; paintGuard();
        const name = await askText({ title: 'A new folder', text: `Inside ${parent}`, placeholder: 'e.g. moonlight-bakery', confirm: 'Create and open' });
        switching = false; paintGuard();
        if (!name || !name.trim() || ['.', '..'].includes(name.trim()) || /[\\/:*?"<>|]/.test(name)) { if (name) toast('Use a new folder name, without \\ / : * ? " < > | or . / ..', 'warn'); return false; }
        const base = parent.replace(/[\\/]+$/, '');
        const target = base + (base.includes('\\') ? '\\' : '/') + name.trim();
        return switchTo(target, true, close); } },
      { label: 'Work here', kind: 'primary', icon: 'check', onClick: async (close) => switchTo(pathInput.value, false, close) }] });
  m.el.classList.add('workspace-picker');
  for (const button of m.el.querySelectorAll('footer button')) {
    if (['Work here', 'New folder here…'].some(label => button.textContent.trim() === label)) button.dataset.switchAction = 'true';
  }
  paintGuard();
  browse(ws.current);
  return m;
}
