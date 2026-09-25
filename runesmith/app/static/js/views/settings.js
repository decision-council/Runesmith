// Settings: how Runesmith behaves here, health checks, data, the folder, and what Runesmith has (and has not) shown.
import { h, icon, get, post, bus, toast, clear, ago, plural, humanize, withBusy, confirmDialog, modal, empty, askText, $ } from '../core.js';

export default async function render(root, ctx) {
  const tab = ['behaviour', 'health', 'data', 'about'].includes(ctx.sub[0]) ? ctx.sub[0] : 'behaviour';
  const head = h('div.page-head', h('div', h('h2', 'Settings'), h('p', 'How Runesmith behaves in this folder. Everything here is saved in the folder’s own .runesmith home, so every folder can be set up differently.')));
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
  const toggle = (key, label, text, onMsg) => h('div.setting', h('div.text', h('b', label), h('span', text)),
    h('label.switch', h('input', { type: 'checkbox', checked: s[key], onchange: (e) => save({ [key]: e.target.checked }, onMsg && onMsg(e.target.checked)) }), h('span')));
  const seg = (key, options) => h('div.seg', options.map(([v, l, ic]) => h('button', { class: s[key] === v ? 'on' : '', onclick: async (e) => { await save({ [key]: v }); for (const b of e.currentTarget.parentNode.children) b.classList.toggle('on', b === e.currentTarget); } }, ic ? icon(ic) : null, l)));
  const name = h('input.input', { value: s.workspace_name, style: { maxWidth: '320px' } });
  name.addEventListener('change', () => save({ workspace_name: name.value }));
  const interval = h('select.select', { style: { width: '180px' }, onchange: () => save({ interval_minutes: Number(interval.value) }) },
    [[5, 'every 5 minutes'], [15, 'every 15 minutes'], [30, 'every 30 minutes'], [60, 'every hour'], [180, 'every 3 hours'], [720, 'twice a day'], [1440, 'once a day']]
      .map(([v, l]) => h('option', { value: v, selected: Number(s.interval_minutes) === v }, l)));
  if (![5, 15, 30, 60, 180, 720, 1440].includes(Number(s.interval_minutes))) interval.append(h('option', { value: s.interval_minutes, selected: true }, `every ${s.interval_minutes} minutes`));
  const objects = (env.map?.objects || []).filter((o) => !o.root && o.reason !== 'link').map((o) => o.name);   // a link is never read anyway
  const exclude = new Set(s.exclude);
  const exChips = h('div.pillbox', objects.length ? objects.map((n) => h('button', { class: `chip${exclude.has(n) ? ' on' : ''}`, onclick: async (e) => {
    exclude.has(n) ? exclude.delete(n) : exclude.add(n); e.currentTarget.classList.toggle('on'); await save({ exclude: [...exclude] }, exclude.has(n) ? `${n} will never be touched` : `${n} is included`);
    post('/api/worker/run', { job: 'map' }); } }, exclude.has(n) ? icon('lock') : null, n)) : h('span.small.faint', 'No sub-folders mapped yet.'));
  const num = (key, label, text, min, max) => {
    const input = h('input.input', { type: 'number', min, max, value: s[key], style: { width: '100px' } });
    input.addEventListener('change', () => save({ [key]: Number(input.value) }));
    return h('div.setting', h('div.text', h('b', label), h('span', text)), input);
  };
  body.append(h('div.grid.two',
    h('div.col.gap-16',
      h('div.card', h('h3', icon('home'), 'This workspace'),
        h('div.setting', h('div.text', h('b', 'Name'), h('span', 'What you build here. Shown everywhere in the Studio.')), name),
        h('div.setting', h('div.text', h('b', 'How Runesmith may act'), h('span', 'Observe maps and watches only. Propose also works on what it finds and brings you fixes to approve. It never writes to your files by itself.')),
          seg('autonomy', [['observe', 'Observe', 'eye'], ['propose', 'Propose', 'hammer']]))),
      h('div.card', h('h3', icon('clock'), 'Rhythm'),
        toggle('auto_work', 'Work on a schedule', 'Run rounds automatically while the Studio is open.'),
        h('div.setting', h('div.text', h('b', 'How often'), h('span', 'A round maps, finds work, works on what is new, and reports.')), interval)),
      h('div.card', h('h3', icon('map'), 'Mapping'),
        toggle('probe_tests', 'Measure code by running its tests', 'Tests always run on a throwaway copy; nothing is written into your folder. Turn off if tests are slow or need special set-up.'),
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
      h('div.divider'), h('h3', icon('rune'), 'Runesmith’s home in this folder'), h('p.mono.small', s.workspace.home),
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
        row('A self-authored generation repairs more fresh tasks than its predecessor (SR7: 57 vs 35 of 162, p = 0.00085; synthetic single-line bugs, one cheap model)', 'shown once', 'good'),
        row('Free-class models as the self-improvement author (SR5, SR6)', 'not shown', ''),
        row('The suit makes a 2.6B free model repair more than a strong simple scaffold (SR6-W: 5 vs 12 of 68)', 'not shown', ''),
        row('Organ confinement (no files, network, subprocesses or secrets)', 'unit-tested', 'rune'),
        row('Natural bugs, other task families, economic value', 'not tested', 'warn')))));
}

// ------------------------------------------------------------ folder picker --
export async function openFolderPicker() {
  const list = h('div.folder-list');
  const pathInput = h('input.input.mono', { placeholder: 'Type or paste a folder path' });
  const recentBox = h('div.pillbox.mb-8');
  let current = '';
  const browse = async (path) => {
    try {
      const r = await get(`/api/browse?path=${encodeURIComponent(path || '')}`);
      current = r.path; pathInput.value = r.path;
      clear(list);
      if (r.parent !== null && r.path) list.append(h('div.f', { onclick: () => browse(r.parent) }, icon('up'), h('span', '.. (up)')));
      for (const d of r.dirs) list.append(h('div.f', { onclick: () => browse(d.path) }, icon('folder'), h('span', d.name)));
      if (!r.dirs.length) list.append(h('div.f.faint', 'No sub-folders here.'));
    } catch (e) { toast(e.message, 'bad'); }
  };
  const ws = await get('/api/workspaces');
  for (const r of ws.recent.slice(0, 8)) recentBox.append(h('button', { class: `chip${r.path === ws.current ? ' on' : ''}`, title: r.path, onclick: () => browse(r.path) }, icon('clock'), r.name || r.path));
  pathInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') browse(pathInput.value); });
  const m = modal({ title: 'Choose a folder', text: 'Runesmith works in any folder: empty, half-built or full. It creates a .runesmith home inside it and changes nothing else without your say-so.',
    body: h('div', ws.recent.length ? [h('div.label-text', 'Recent'), recentBox] : null, h('div.row', pathInput, h('button.btn', { onclick: () => browse(pathInput.value) }, 'Go')), h('div.mt-8', list)),
    actions: [{ label: 'Cancel', kind: 'ghost' },
      { label: 'New folder here…', icon: 'plus', onClick: async (close) => {
        const name = await askText({ title: 'A new folder', text: `Inside ${pathInput.value || current}`, placeholder: 'e.g. moonlight-bakery', confirm: 'Create and open' });
        if (!name || !name.trim() || /[\\/:*?"<>|]/.test(name)) { if (name) toast('A folder name cannot contain \\ / : * ? " < > |', 'warn'); return false; }
        const base = (pathInput.value || current).replace(/[\\/]+$/, '');
        const target = base + (base.includes('\\') ? '\\' : '/') + name.trim();
        await post('/api/workspaces/open', { path: target, create: true }); close(); toast('Opening…', 'good'); } },
      { label: 'Work here', kind: 'primary', icon: 'check', onClick: async (close) => { await post('/api/workspaces/open', { path: pathInput.value || current }); close(); toast('Opening…', 'good'); } }] });
  browse(ws.current);
  return m;
}
