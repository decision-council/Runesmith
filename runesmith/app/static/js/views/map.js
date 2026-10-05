// The living map: four lenses on one world. Environment, Self, Development, Operations.
import { h, icon, get, post, bus, toast, commentable, openNotes, clear, ago, plural, KIND, worstBand, BAND_COLOR,
  BAND_LABEL, humanize, cap, bytes, withBusy, clock, debounce, $ } from '../core.js';
import { iconSvg } from '../icons.js';
import { bandPosition, fmtCap } from './home.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hubSize = (name) => { const n = String(name || 'Workspace').length; return n <= 9 ? 15 : n <= 12 ? 13.5 : n <= 15 ? 12 : 10.5; };
const trunc = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));
// Old maps stay on disk until the owner re-maps. Render their retained probe with
// current evidence semantics, without starting tests or rewriting the receipt.
function scopedObject(obj) {
  const probe = obj.probe || {}, unavailable = !!(probe.unavailable || probe.error);
  if (probe.runner !== 'unittest' && !unavailable) return obj;
  const objectives = (obj.objectives || []).map(row => ['test_pass_rate', 'test_suite_seconds'].includes(row.metric)
    ? {...row, value: null, band: 'unknown', evidence: 'unknown'} : row);
  const ladder = (obj.ladder || []).map(row => ['tests_collect', 'tests_pass', 'fast_suite'].includes(row.rung)
    ? {...row, status: row.rung === 'tests_pass' && !unavailable && probe.exit_code != null && probe.exit_code !== 0
      ? 'not_achieved' : 'unknown'} : row);
  return {...obj, objectives, ladder, next_rung: ladder.find(row => row.status !== 'achieved')?.rung || null};
}
// A long workspace name wraps onto two balanced lines inside the hub instead of being cut.
const hubLines = (name) => {
  const text = String(name || 'Workspace').trim(), words = text.split(/\s+/);
  if (text.length <= 13 || words.length < 2) return [trunc(text, 16)];
  let best = null;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' '), b = words.slice(i).join(' ');
    if (!best || Math.max(a.length, b.length) < best.w) best = { a, b, w: Math.max(a.length, b.length) };
  }
  return [trunc(best.a, 15), trunc(best.b, 15)];
};
const hubMarkup = (lines, facts) => {
  const size = hubSize(lines.reduce((a, b) => (b.length > a.length ? b : a), ''));
  const two = lines.length > 1, top = two ? -17 : -6, gap = size + 2;
  return lines.map((line, i) => `<text text-anchor="middle" y="${top + i * gap}" class="svg-text" font-size="${size}" font-weight="750">${esc(line)}</text>`).join('')
    + `<text text-anchor="middle" y="${two ? 18 : 14}" class="svg-muted" font-size="11.5">${facts.empty ? 'empty folder' : `${facts.files ?? 0}${facts.truncated_scan ? '+' : ''} files`}</text>`
    + `<text text-anchor="middle" y="${two ? 33 : 30}" class="svg-faint" font-size="10.5">workspace</text>`;
};
/** Every `.node` of a lens drawing takes the keyboard: a Tab stop, announced by its tooltip, picked by Enter or Space. */
function keyboardNodes(svg, pick) {
  for (const n of svg.querySelectorAll('.node')) {
    n.classList.add('kb');
    if (!n.hasAttribute('tabindex')) n.setAttribute('tabindex', '0');
    if (!n.hasAttribute('role')) n.setAttribute('role', 'button');
    const tip = n.querySelector(':scope > title');
    if (!n.hasAttribute('aria-label') && tip) n.setAttribute('aria-label', tip.textContent);
  }
  svg.addEventListener('keydown', (e) => {
    const n = e.target.closest && e.target.closest('.node');
    if (!n || (e.key !== 'Enter' && e.key !== ' ')) return;
    e.preventDefault();
    pick(n);
  });
}

// The environment map's rings: an ellipse wider than tall, like the canvas. A node is 196 × 66 plus a margin.
const RING_X = 270, RING_Y = 165, NODE_W = 196 + 26, NODE_H = 66 + 22;
export function ringLayout(n) {
  const ring = (count, k, offset) => Array.from({ length: count }, (_, i) => {
    const a = -Math.PI / 2 + (i / count) * Math.PI * 2 + offset;
    return { x: Math.cos(a) * RING_X * k, y: Math.sin(a) * RING_Y * k };
  });
  const clash = (p, q) => Math.abs(p.x - q.x) < NODE_W && Math.abs(p.y - q.y) < NODE_H;
  const fits = (pts) => pts.every((p, i) => pts.every((q, j) => j <= i || !clash(p, q)));
  if (n <= 12) {                                        // one ring, only as large as its nodes need
    let k = 1;
    while (k < 3 && !fits(ring(n, k, 0))) k += 0.05;
    return { points: ring(n, k, 0), scales: n ? [k] : [] };
  }
  // More: as few rings as hold them all, 0.95 apart (wider than a node, so rings never touch), shared out by capacity.
  const scaleOf = (r) => 1 + 0.95 * r, offsetOf = (r, count) => (r % 2 ? Math.PI / count : 0);   // odd rings sit between
  const caps = [];
  for (let total = 0; total < n; total += caps[caps.length - 1]) caps.push(ringCapacity(caps.length, ring, fits, scaleOf, offsetOf));
  const sum = caps.reduce((a, b) => a + b, 0);
  const counts = caps.map((c) => Math.floor((n * c) / sum));
  for (let rest = n - counts.reduce((a, b) => a + b, 0), r = 0; rest > 0; r = (r + 1) % caps.length) {
    if (counts[r] < caps[r]) { counts[r]++; rest--; }
  }
  const points = [], scales = [];
  counts.forEach((count, r) => { if (count) { points.push(...ring(count, scaleOf(r), offsetOf(r, count))); scales.push(scaleOf(r)); } });
  return { points, scales };
}
const CAPACITY = [];
/** The most nodes ring r can hold such that every smaller count fits as well (the same for every map: kept). */
function ringCapacity(r, ring, fits, scaleOf, offsetOf) {
  if (CAPACITY[r] == null) {
    let c = 0;
    while (c < 400 && fits(ring(c + 1, scaleOf(r), offsetOf(r, c + 1)))) c++;
    CAPACITY[r] = Math.max(1, c);
  }
  return CAPACITY[r];
}
const LENSES = [
  { id: 'environment', label: 'Environment', icon: 'globe', blurb: 'What is in this folder, how healthy each part is, and the next rung on each ladder.' },
  { id: 'self', label: 'Self', icon: 'rune', blurb: 'Runesmith’s own anatomy: a fixed kernel, living organs, measured capabilities and its lineage.' },
  { id: 'development', label: 'Development', icon: 'route', blurb: 'Tracks of progress: your goals, the plan, every object’s ladder, and Runesmith’s own generations.' },
  { id: 'operations', label: 'Operations', icon: 'activity', blurb: 'The work loop right now: what runs, which model does what, and how attention is spent.' },
];

export default async function render(root, ctx) {
  const lens = LENSES.find((l) => l.id === ctx.sub[0]) || LENSES[0];
  const tabs = h('div.seg', LENSES.map((l) => h('button', { class: l.id === lens.id ? 'on' : '', onclick: () => ctx.navigate('map', l.id) }, icon(l.icon), l.label)));
  const head = h('div.page-head', h('div', h('h2', 'Living map'), h('p', lens.blurb)), h('div.actions', tabs));
  const body = h('div');
  root.append(head, body);
  const draw = { environment: environmentLens, self: selfLens, development: developmentLens, operations: operationsLens }[lens.id];
  return draw(body, ctx);
}

// ------------------------------------------------------------ pan and zoom --
function panZoom(svg, g, fit) {
  let view = { x: 0, y: 0, k: 1 }, drag = null;
  const apply = () => g.setAttribute('transform', `translate(${view.x},${view.y}) scale(${view.k})`);
  const toLocal = (e) => { const r = svg.getBoundingClientRect(); const vb = svg.viewBox.baseVal; return { x: (e.clientX - r.left) / r.width * vb.width + vb.x, y: (e.clientY - r.top) / r.height * vb.height + vb.y }; };
  svg.addEventListener('wheel', (e) => { e.preventDefault(); const p = toLocal(e); const f = Math.exp(-e.deltaY * 0.0015); const k = Math.max(0.35, Math.min(3.2, view.k * f));
    view.x = p.x - (p.x - view.x) * (k / view.k); view.y = p.y - (p.y - view.y) * (k / view.k); view.k = k; apply(); }, { passive: false });
  svg.addEventListener('pointerdown', (e) => { if (e.target.closest('.node')) return; drag = { ...toLocal(e), vx: view.x, vy: view.y }; svg.classList.add('dragging'); svg.setPointerCapture(e.pointerId); });
  svg.addEventListener('pointermove', (e) => { if (!drag) return; const p = toLocal(e); view.x = drag.vx + (p.x - drag.x); view.y = drag.vy + (p.y - drag.y); apply(); });
  svg.addEventListener('pointerup', () => { drag = null; svg.classList.remove('dragging'); });
  svg.addEventListener('dblclick', (e) => { if (!e.target.closest('.node')) { view = { x: 0, y: 0, k: 1 }; apply(); } });
  return { zoom: (f) => { view.k = Math.max(0.35, Math.min(3.2, view.k * f)); apply(); }, reset: () => { view = { x: 0, y: 0, k: 1 }; apply(); fit && fit(); } };
}

// ============================================================== ENVIRONMENT ==
async function environmentLens(body, ctx) {
  const offs = [];
  const wrap = h('div.map-wrap');
  body.append(wrap);
  let data, selected = ctx.params.get('focus') || null;
  let focusAfter = null;                  // after a redraw: 'panel' (details just opened) or a node's name to return to
  let lastNarrow = null;
  // the drawing's width, even before the page is on screen (the first draw happens before it is attached)
  const availableWidth = () => wrap.clientWidth || ((document.querySelector('main.content')?.clientWidth || window.innerWidth) - 28);
  const isNarrow = () => availableWidth() < 560;
  const onResize = debounce(() => { if (data && isNarrow() !== lastNarrow) drawMap(); }, 200);
  window.addEventListener('resize', onResize);
  offs.push(() => window.removeEventListener('resize', onResize));

  const load = async () => {
    data = await get('/api/map/environment');
    drawMap();
  };
  const drawMap = () => {
    const held = document.activeElement?.closest?.('.map-wrap .node')?.dataset.name;   // a live update keeps the focus
    if (!focusAfter && held) focusAfter = held;
    clear(wrap);
    const env = data.map;
    if (!env) { wrap.append(h('div.empty', icon('map', 'big'), h('h4', 'Mapping…'), h('p', 'The first map takes a few seconds.'))); return; }
    const statuses = data.round.objects || {};
    const objects = (env.objects || []).map(scopedObject);
    const rootObj = objects.find((o) => o.root);
    const others = objects.filter((o) => !o.root);
    const facts = env.workspace_facts || {};
    // layout: rings around the hub, spaced so that no two nodes ever overlap; on a phone, one column under the hub,
    // at a readable size and exactly as tall as it needs
    const narrow = isNarrow();
    lastNarrow = narrow;
    const { points, scales } = narrow ? { points: others.map((_, i) => ({ x: 0, y: 170 + i * 92 })), scales: [] } : ringLayout(others.length);
    const placed = points.map((p, i) => ({ o: others[i], x: p.x, y: p.y }));
    let W, H, top;
    if (narrow) {                                   // room for the tool bar above the hub and the legend below the last one
      top = -150;
      W = 280; H = (placed.length ? placed[placed.length - 1].y : 90) + 100 - top;
    } else {                                        // fit the drawing: room for the tool bar above and the legend below
      const halfW = placed.reduce((m, p) => Math.max(m, Math.abs(p.x) + 120), 330);
      top = placed.reduce((m, p) => Math.min(m, p.y - 50), -140) - 70;
      const bottom = placed.reduce((m, p) => Math.max(m, p.y + 50), 140) + 70;
      W = Math.max(halfW * 2, (bottom - top) * 1.85); H = bottom - top;
    }
    const wsName = ctx.app.state?.workspace?.name || 'Workspace';
    let s = `<svg class="map" viewBox="${-W / 2} ${top} ${W} ${H}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="group"
      aria-label="${esc(`Map of ${wsName}: ${others.length} object${others.length === 1 ? '' : 's'} around the workspace. Tab to one and press Enter for its details.`)}">
      <defs><radialGradient id="hubg" cx="50%" cy="40%" r="70%"><stop offset="0" stop-color="#f8dc94"/><stop offset=".6" stop-color="#e8b04a"/><stop offset="1" stop-color="#c58a34"/></radialGradient>
      <radialGradient id="halo" r="50%"><stop offset="0" stop-color="#e8b04a" stop-opacity=".35"/><stop offset="1" stop-color="#e8b04a" stop-opacity="0"/></radialGradient></defs><g class="pz">`;
    for (const k of scales) s += `<ellipse cx="0" cy="0" rx="${RING_X * k}" ry="${RING_Y * k}" fill="none" stroke="var(--line)" stroke-dasharray="3 7"/>`;
    if (!others.length) s += `<ellipse cx="0" cy="0" rx="270" ry="165" fill="none" stroke="var(--line-2)" stroke-dasharray="4 9"/>`;
    if (narrow && placed.length) s += `<path class="edge" d="M0 70 L0 ${placed[placed.length - 1].y}" stroke="var(--line-2)"/>`;   // one spine
    for (const p of narrow ? [] : placed) {
      const band = worstBand((p.o.objectives || []).map((x) => x.band));
      const st = statuses[p.o.name] || '';
      const hot = st === 'failing';
      const mx = p.x * 0.5 - p.y * 0.12, my = p.y * 0.5 + p.x * 0.12;
      s += `<path class="edge${hot ? ' flow' : ''}" d="M0 0 Q ${mx} ${my} ${p.x} ${p.y}" stroke="${band === 'unknown' ? 'var(--line-2)' : BAND_COLOR[band]}" stroke-opacity="${band === 'unknown' ? 1 : 0.55}"/>`;
    }
    s += `<circle r="120" fill="url(#halo)"/>`;
    s += `<g class="node${selected === '__hub' ? ' sel' : ''}" data-name="__hub" data-note="workspace|root" data-note-label="the whole workspace" tabindex="0" role="button"
      aria-label="${esc(`${wsName}, the whole workspace: ${facts.empty ? 'an empty folder' : `${facts.files ?? 0} files`}`)}"><path class="halo" d="M-56 -86 L56 -86 L86 -56 L86 56 L56 86 L-56 86 L-86 56 L-86 -56 Z" fill="none" stroke="#e8b04a" stroke-opacity=".35" stroke-width="8"/>
      <path d="M-42 -66 L42 -66 L66 -42 L66 42 L42 66 L-42 66 L-66 42 L-66 -42 Z" fill="url(#hubg)"/>
      <path d="M-37.9 -56 L37.9 -56 L56 -37.9 L56 37.9 L37.9 56 L-37.9 56 L-56 37.9 L-56 -37.9 Z" fill="var(--bg-1)"/>
      ${hubMarkup(hubLines(ctx.app.state?.workspace?.name), facts)}</g>`;
    for (const p of placed) s += nodeMarkup(p, statuses[p.o.name], selected === p.o.name);
    s += `</g></svg>`;
    const holder = h('div', { html: s });
    const svg = holder.firstChild;
    if (narrow) svg.style.height = `${Math.round(H * Math.min(1.3, availableWidth() / W))}px`;
    const g = svg.querySelector('.pz');
    const pz = panZoom(svg, g);
    svg.addEventListener('click', (e) => { const n = e.target.closest('.node'); if (!n) return; selected = n.dataset.name; drawMap(); });
    svg.addEventListener('keydown', (e) => {        // Enter or Space on a node opens its details, and the focus goes there
      const n = e.target.closest && e.target.closest('.node');
      if (!n || (e.key !== 'Enter' && e.key !== ' ')) return;
      e.preventDefault(); selected = n.dataset.name; focusAfter = 'panel'; drawMap();
    });
    wrap.append(
      h('div.map-tools', h('button.btn.sm.icon', { title: 'Zoom in', 'aria-label': 'Zoom in', onclick: () => pz.zoom(1.2) }, icon('plus')),
        h('button.btn.sm.icon', { title: 'Zoom out', 'aria-label': 'Zoom out', onclick: () => pz.zoom(1 / 1.2) }, icon('minus')),
        h('button.btn.sm.icon', { title: 'Reset view', 'aria-label': 'Reset the view', onclick: () => pz.reset() }, icon('crosshair')),
        h('button.btn.sm', { title: 'Map again, running each object’s tests on throwaway copies', onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'map', params: { probe: true } }); toast('Mapping and measuring… the map updates when done.', 'good'); }) }, icon('refresh'), 'Re-map & measure'),
        h('span.badge', `mapped ${ago(env.utc)}`),
        // A map made by an earlier version lacks what this one finds (journey J4-F7); re-mapping is the owner's choice.
        data.outdated ? h('button.btn.sm.primary', { title: 'This map was made by an earlier version of Runesmith, which found less. Map again to see everything.',
          onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'map' }); toast('Mapping… the map updates when done.', 'good'); }) },
          icon('refresh'), 'Made by an earlier version: map again') : null),
      svg,
      h('div.map-legend', ['bad', 'minimal', 'optimal', 'world_class', 'unknown'].map((b) => h('span', { class: `band ${b}` }, BAND_LABEL[b])),
        h('span.faint', '· drag to pan · scroll to zoom · Tab to an object')));
    if (!others.length && facts.empty) wrap.append(h('div', { style: { position: 'absolute', left: '50%', top: '72%', transform: 'translate(-50%,0)', textAlign: 'center' } },
      h('p.muted', 'An empty world. Perfect for something new.'), h('button.btn.primary', { onclick: () => ctx.navigate('goals') }, icon('wand'), 'Tell Runesmith what to build')));
    if (selected) wrap.append(sidePanel(selected === '__hub' ? null : objects.find((o) => o.name === selected), env, data,
      () => { focusAfter = selected; selected = null; drawMap(); }, ctx, rootObj));
    if (focusAfter === 'panel') $('.map-side h3', wrap)?.focus();
    else if (focusAfter) svg.querySelector(`.node[data-name="${CSS.escape(focusAfter)}"]`)?.focus({ preventScroll: true });
    focusAfter = null;
  };
  await load();
  offs.push(bus.on('map', debounce(load, 300)), bus.on('round', debounce(load, 300)));
  return () => offs.forEach((f) => f());
}

export function nodeMarkup(p, status, sel) {
  const o = scopedObject(p.o), k = KIND[o.kind] || KIND.unknown;
  const band = worstBand((o.objectives || []).map((x) => x.band));
  const color = BAND_COLOR[band];
  const w = 196, hgt = 66;
  const ladder = o.ladder || [];
  const done = ladder.filter((r) => r.status === 'achieved').length;
  const cut = o.name.lastIndexOf('/');
  const title = cut >= 0 ? o.name.slice(cut + 1) : o.name;               // services/billing → billing, "in services"
  const where = cut >= 0 ? `${o.name.slice(0, cut)} · ` : '';
  const sub = where + (o.kind === 'excluded' ? (o.reason === 'link' ? 'a link: not followed' : 'never touched')
    : o.next_rung ? `next: ${humanize(o.next_rung)}` : ladder.length ? 'every rung achieved' : k.label);
  const stat = { green: ['#5fd3a0', 'tests pass'], failing: ['#ff5a4f', 'tests failing'], timed_out: ['#e8b04a', 'tests timed out'],
    unittest_passed: ['#e8b04a', 'unittest subset passes'], probe_unavailable: ['#e8b04a', 'test probe unavailable'],
    error_without_failures: ['#e8b04a', 'tests could not run'],
    fix_applied: ['#f8dc94', 'a fix was applied: measure the tests to confirm'] }[status];
  let seg = '';
  const segW = ladder.length ? (w - 64) / ladder.length : 0;
  ladder.forEach((r, i) => {
    const fill = r.status === 'achieved' ? '#5fd3a0' : r.status === 'not_achieved' ? '#e8b04a' : 'var(--bg-4)';
    seg += `<rect x="${-w / 2 + 54 + i * segW}" y="${hgt / 2 - 12}" width="${Math.max(2, segW - 3)}" height="4" rx="2" fill="${fill}" fill-opacity="${r.status === 'unknown' ? 1 : 0.9}"/>`;
  });
  const spoken = [`${o.name}: ${k.label}`, band !== 'unknown' && o.kind !== 'excluded' ? `${BAND_LABEL[band]} health` : '',
    o.kind === 'excluded' ? (o.reason === 'link' ? 'a link to another place, not followed' : 'excluded, never read')
      : o.next_rung ? `next: ${humanize(o.next_rung)}` : ladder.length ? 'every rung achieved' : '',
    stat ? stat[1] : ''].filter(Boolean).join(', ');
  return `<g class="node${sel ? ' sel' : ''}" data-name="${esc(o.name)}" data-note="object|${esc(o.name)}" data-note-label="${esc(o.name)}" transform="translate(${p.x},${p.y})"
    tabindex="0" role="button" aria-label="${esc(spoken)}">
    <rect class="halo" x="${-w / 2 - 7}" y="${-hgt / 2 - 7}" width="${w + 14}" height="${hgt + 14}" rx="20" fill="none" stroke="${color}" stroke-opacity=".35" stroke-width="6"/>
    <rect x="${-w / 2}" y="${-hgt / 2}" width="${w}" height="${hgt}" rx="15" fill="var(--bg-2)" stroke="${o.kind === 'excluded' ? 'var(--line-2)' : color}" stroke-width="1.6" ${o.kind === 'excluded' ? 'stroke-dasharray="4 4"' : ''}/>
    <circle cx="${-w / 2 + 28}" cy="-2" r="17" fill="${k.color}" fill-opacity=".16"/>
    <svg x="${-w / 2 + 17}" y="-13" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="${k.color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${iconSvg(k.icon).replace(/^<svg[^>]*>|<\/svg>$/g, '')}</svg>
    <text x="${-w / 2 + 54}" y="-6" class="svg-text" font-size="14" font-weight="680">${esc(trunc(title, 17))}</text>
    <text x="${-w / 2 + 54}" y="11" class="svg-muted" font-size="11">${esc(trunc(sub, 28))}</text>
    ${seg}
    ${stat ? `<circle cx="${w / 2 - 14}" cy="${-hgt / 2 + 14}" r="5" fill="${stat[0]}"><title>${stat[1]}</title></circle>` : ''}
    <title>${esc(o.name)} — ${esc(k.label)}${ladder.length ? ` — ${done}/${ladder.length} rungs` : ''}</title></g>`;
}

function sidePanel(obj, env, data, close, ctx, rootObj) {
  const panel = h('div.map-side');
  const settings = data.settings;
  const top = h('div.row', h('div.grow', h('div.small.faint', obj ? (KIND[obj.kind]?.label || obj.kind) : 'Workspace'), h('h3', { style: { margin: '2px 0 0', fontSize: '17px' }, tabindex: '-1' }, obj ? obj.name : (ctx.app.state?.workspace?.name || 'Workspace'))),
    h('button.btn.icon.sm.ghost', { onclick: close, title: 'Close', 'aria-label': 'Close the details' }, icon('x')));
  panel.setAttribute('role', 'region');
  panel.setAttribute('aria-label', `Details: ${obj ? obj.name : 'the whole workspace'}`);
  panel.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('.modal-wrap, .drawer, .cmdk')) { e.stopPropagation(); close(); } });
  panel.append(top);
  const target = obj ? ['object', obj.name, obj.name] : ['workspace', 'root', 'the whole workspace'];
  panel.append(h('div.row.mt-8', h('button.btn.sm', { onclick: () => openNotes(...target) }, icon('note'), 'Comment'),
    obj && obj.kind !== 'excluded' && !obj.root ? h('button.btn.sm', { onclick: async (e) => withBusy(e.currentTarget, async () => {
      const ex = new Set(settings.exclude); ex.add(obj.name); await post('/api/settings', { exclude: [...ex] }); await post('/api/worker/run', { job: 'map' });
      toast(`${obj.name} is excluded: Runesmith will never probe or work on it.`, 'good'); }) }, icon('lock'), 'Exclude') : null,
    obj && obj.kind === 'excluded' ? h('button.btn.sm', { onclick: async (e) => withBusy(e.currentTarget, async () => {
      await post('/api/settings', { exclude: settings.exclude.filter((x) => x !== obj.name) }); await post('/api/worker/run', { job: 'map' }); toast(`${obj.name} is included again.`, 'good'); }) }, icon('eye'), 'Include') : null));
  if (!obj) {
    const f = env.workspace_facts || {};
    const e = env.environment || {};
    panel.append(h('div.divider'), h('div.label-text', 'This folder'),
      kv([['Path', env.workspace], ['Files', f.files], ['Size', bytes(f.bytes)], ['Top-level entries', f.entries_total], ['Readme', f.readme || 'none'], ['Version control', f.version_control ? 'yes (git)' : 'no']]));
    if (f.top_extensions?.length) {
      const max = f.top_extensions[0][1];
      panel.append(h('div.label-text.mt-16', 'Kinds of files'), h('div.col.gap-6.mt-8', f.top_extensions.map(([ext, n]) =>
        h('div', h('div.row.small', h('span.mono', ext), h('span.spacer'), h('span.faint', n)), h('div.bar.rune', h('i', { style: { width: `${(n / max) * 100}%` } }))))));
    }
    if (rootObj) {
      const label = KIND[rootObj.kind]?.label || humanize(rootObj.kind);
      panel.append(h('div.divider'), h('div.row', h('span', { class: 'badge rune' }, label),
        h('span.small.muted', rootObj.kind === 'folder' ? 'the loose files at the top level' : 'this folder itself')), ...objectDetails(rootObj, env, data));
    }
    panel.append(h('div.divider'), h('div.label-text', 'This computer'),
      kv([['System', e.os], ['Python', e.python], ['Processors', e.cpus], ['Free disk', e.disk_free_gb != null ? `${e.disk_free_gb} GB` : '—']]));
    panel.append(h('div.divider'), h('div.label-text', 'What Runesmith does not know yet'),
      h('ul.small.muted', { style: { paddingLeft: '18px', margin: '6px 0 0' } }, (env.unknowns || []).map((u) => h('li', u))));
    return panel;
  }
  panel.append(...objectDetails(obj, env, data));
  panel.append(h('div.tiny.faint.mt-16.mono', obj.path));
  return panel;
}

export function objectDetails(obj, env, data) {
  obj = scopedObject(obj);
  const out = [];
  const probe = obj.probe || {}, limited = probe.runner === 'unittest', unavailable = !!(probe.unavailable || probe.error);
  const status = (data.round.objects || {})[obj.name];
  const badges = h('div.row.wrap.mt-8');
  const words = { green: 'tests pass', failing: 'tests failing', timed_out: 'tests timed out', error_without_failures: 'tests could not run',
    unittest_passed: 'unittest subset passes', probe_unavailable: 'test probe unavailable',
    fix_applied: 'fix applied · measure to confirm' }[status] || (status ? `last round: ${humanize(status)}` : '');
  if (status) badges.append(h('span', { class: `badge ${status === 'green' ? 'good' : status === 'failing' ? 'bad' : status === 'fix_applied' ? 'rune' : 'warn'}` }, words));
  if (obj.measured_utc) badges.append(h('span.badge.rune', { title: 'Kept while the files stay unchanged' },
    `${unavailable ? 'probe attempted' : limited ? 'unittest subset measured' : 'tests measured'} ${ago(obj.measured_utc)}`));
  else if (obj.kind === 'python_repository') badges.append(h('button.btn.sm', { onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'map', params: { probe: true } }); toast('Measuring: the tests run on throwaway copies.', 'good'); }) }, icon('gauge'), 'Measure its tests'));
  const broken = (obj.facts && (obj.facts.broken_links || obj.facts.broken_references)) || 0;
  if (broken) badges.append(h('button.btn.sm.primary', { title: 'Runesmith points each broken link at the existing file with the closest name: a draft you review, no model needed',
    onclick: (e) => withBusy(e.currentTarget, async () => {
      const r = await post('/api/links/suggest', { object: obj.name });
      if (r.draft) toast(`Drafted ${plural(r.fixed.length, 'link fix', 'link fixes')}${r.unresolved.length ? `; ${r.unresolved.length} left (no similar file)` : ''}. Review it under Work → Drafts.`, 'good', 8000);
      else toast(r.detail || 'Nothing to fix.', r.unresolved?.length ? 'warn' : 'good', 7000);
    }) }, icon('wand'), `Suggest fixes for ${plural(broken, 'broken link')}`));
  if (badges.children.length) out.push(badges);
  if (limited) out.push(h('div.callout.warn.mt-8', icon('alert'), h('div',
    h('b', 'Limited test scope. '), 'Pytest is missing in this Python. ',
    probe.collected != null ? `Unittest discovery ran ${plural(probe.collected, 'test')}. ` : 'Unittest discovery was attempted. ',
    'Pytest-style tests may be omitted; whole-suite coverage is unknown. Build’s unittest checks are separate.')));
  if (unavailable) out.push(h('div.callout.warn.mt-8', icon('alert'), h('div',
    h('b', 'No passing test result was established. '), probe.unavailable || probe.error)));
  const why = (data.round.details || {})[obj.name];
  if (why) out.push(h('div.callout.warn.mt-8', icon('alert'), h('div', h('b', 'The tests could not run. '), why.detail,
    why.triage ? h('div.small.mt-8', why.triage.reason) : null)));
  if (obj.objectives?.length) {
    out.push(h('div.divider'), h('div.label-text', 'Objectives (proposed by Runesmith; yours to change)'));
    for (const ob of obj.objectives) {
      const row = h('div.card.flat.mt-8', { style: { padding: '10px 12px' } },
        h('div.row', h('b.small', humanize(ob.id)), h('span.spacer'), h('span', { class: `band ${ob.band}` }, ob.value == null ? 'unknown' : `${fmtVal(ob)} · ${BAND_LABEL[ob.band]}`)),
        h('div', { class: `bandbar mt-8${ob.value == null ? ' unknown' : ''}` }, ob.value != null ? h('span.mark', { style: { left: `${bandPosition(ob)}%` } }) : null),
        h('div.tiny.faint.mt-8', `${ob.unit}. ${cap(ob.why)}.`));
      commentable(row, 'objective', `${obj.name}/${ob.id}`, `${obj.name}: ${humanize(ob.id)}`);
      out.push(row);
    }
  }
  if (obj.ladder?.length) out.push(h('div.divider'), h('div.label-text', 'Build ladder'), ladderEl(obj));
  if (obj.facts) {
    const skip = new Set(['broken_examples', 'orphan_examples', 'todo_examples', 'top_extensions', 'recursive', 'fingerprint']);
    out.push(h('div.divider'), h('div.label-text', 'Facts read from disk'),
      kv(Object.entries(obj.facts).filter(([k, v]) => !skip.has(k) && v !== null && typeof v !== 'object').map(([k, v]) => [humanize(k), typeof v === 'boolean' ? (v ? 'yes' : 'no') : v])));
    if (obj.facts.broken_examples?.length) out.push(h('div.label-text.mt-16', 'Broken links (examples)'),
      h('ul.small.mono', { style: { paddingLeft: '18px' } }, obj.facts.broken_examples.map((b) => h('li', `${b.document || b.page} → ${b.target}`))));
    if (obj.facts.orphan_examples?.length) out.push(h('div.label-text.mt-16', 'Pages no other page links to'),
      h('ul.small.mono', { style: { paddingLeft: '18px' } }, obj.facts.orphan_examples.map((p) => h('li', p))));
    if (obj.facts.todo_examples?.length) out.push(h('div.label-text.mt-16', 'Notes still to do (TODO, FIXME)'),
      h('ul.small', { style: { paddingLeft: '18px' } }, obj.facts.todo_examples.map((t) => h('li', h('span.mono', `${t.document}:${t.line}`), ' ', t.text))));
  }
  if (obj.probe) out.push(h('div.divider'), h('div.label-text',
    unavailable ? 'Last probe attempt (throwaway copy)' : limited ? 'Last unittest subset run (throwaway copy)' : 'Last measured test run (throwaway copy)'),
    kv(Object.entries(obj.probe).map(([k, v]) => [humanize(k), v])));
  const unknown = (env.unknowns || []).filter((u) => u.startsWith(obj.name + ':'));
  if (unknown.length) out.push(h('div.divider'), h('div.label-text', 'Unknown'), h('ul.small.muted', { style: { paddingLeft: '18px' } }, unknown.map((u) => h('li', u.slice(obj.name.length + 1).trim()))));
  return out;
}
function fmtVal(ob) {
  if (ob.unit && ob.unit.includes('seconds')) return `${Math.round(ob.value)} s`;
  if (ob.value <= 1 && ob.higher_is_better) return `${Math.round(ob.value * 100)}%`;
  return String(ob.value);
}
function ladderEl(obj) {
  const box = h('div.ladder.mt-8');
  for (const r of obj.ladder) {
    const row = h('div', { class: `rung ${r.status}${obj.next_rung === r.rung ? ' next' : ''}` }, h('span.pip'), h('span', humanize(r.rung)),
      h('span.spacer'), h('span.tiny.faint', r.status === 'achieved' ? 'achieved' : r.status === 'unknown' ? 'unknown' : obj.next_rung === r.rung ? 'next' : 'not yet'));
    commentable(row, 'rung', `${obj.name}/${r.rung}`, `${obj.name}: ${humanize(r.rung)}`);
    row.querySelector('.note-btn').style.top = '-4px';
    box.append(row);
  }
  return box;
}
function kv(rows) {
  return h('table.table.small', { style: { marginTop: '6px' } }, rows.map(([k, v]) => h('tr', h('td.faint', { style: { padding: '5px 8px 5px 0', width: '44%' } }, k), h('td', { style: { padding: '5px 0', wordBreak: 'break-word' } }, v == null || v === '' ? '—' : String(v)))));
}

// ===================================================================== SELF ==
async function selfLens(body, ctx) {
  const data = await get('/api/map/self');
  const wrap = h('div.map-wrap');
  let selected = null;
  const kernel = data.kernel, organs = data.active_organs;
  const draw = () => {
    clear(wrap);
    const R1 = 190, R2 = 262, N = kernel.length;
    let s = `<svg class="map" viewBox="-560 -330 1120 660" xmlns="http://www.w3.org/2000/svg"><defs>
      <radialGradient id="core" r="60%"><stop offset="0" stop-color="#f8dc94"/><stop offset=".55" stop-color="#e8b04a"/><stop offset="1" stop-color="#c58a34"/></radialGradient>
      <radialGradient id="coreHalo" r="50%"><stop offset="0" stop-color="#e8b04a" stop-opacity=".4"/><stop offset="1" stop-color="#e8b04a" stop-opacity="0"/></radialGradient></defs><g class="pz">`;
    s += `<circle r="${R2 + 34}" fill="none" stroke="var(--line)" stroke-dasharray="2 8"><animateTransform attributeName="transform" type="rotate" from="0" to="-360" dur="140s" repeatCount="indefinite"/></circle>`;
    kernel.forEach((c, i) => {
      const a0 = (i / N) * Math.PI * 2 - Math.PI / 2 + 0.012, a1 = ((i + 1) / N) * Math.PI * 2 - Math.PI / 2 - 0.012;
      const p = (r, a) => `${(Math.cos(a) * r).toFixed(1)} ${(Math.sin(a) * r).toFixed(1)}`;
      const d = `M ${p(R2, a0)} A ${R2} ${R2} 0 0 1 ${p(R2, a1)} L ${p(R1, a1)} A ${R1} ${R1} 0 0 0 ${p(R1, a0)} Z`;
      const sel = selected === c.path;
      const shade = 0.18 + 0.5 * Math.min(1, (c.lines || 50) / 450);
      s += `<g class="node${sel ? ' sel' : ''}" data-kind="kernel" data-name="${esc(c.path)}" data-note="component|${esc(c.path)}" data-note-label="${esc(c.path)}"><path d="${d}" fill="var(--rune)" fill-opacity="${sel ? 0.95 : shade.toFixed(2)}" stroke="var(--bg-1)" stroke-width="1.5"/><title>${esc(c.path)} — ${esc(c.purpose || '')}</title></g>`;
    });
    s += `<circle r="${R1 - 26}" fill="url(#coreHalo)"/>`;
    s += `<circle r="118" fill="var(--bg-1)" stroke="var(--line-2)"/>`;
    const m = organs.length || 1;
    organs.forEach((o, i) => {
      const a = (i / m) * Math.PI * 2 - Math.PI / 2;
      const x = Math.cos(a) * 64, y = Math.sin(a) * 64;
      s += `<g class="node" data-kind="organ" data-name="${esc(o.path)}" data-note="organ|${esc(o.path)}" data-note-label="organ ${esc(o.path)}" transform="translate(${m === 1 ? 0 : x},${m === 1 ? -20 : y})"><circle r="${m === 1 ? 46 : 30}" fill="url(#core)"/><text text-anchor="middle" y="4" font-size="12" font-weight="700" fill="#0b0e14">${esc(o.path.replace('.py', ''))}</text><title>organ ${esc(o.path)} · ${o.lines} lines</title></g>`;
    });
    const gen = data.identity.active_generation || '';
    s += `<text text-anchor="middle" y="${m === 1 ? 50 : 104}" class="svg-muted" font-size="11.5">active generation</text><text text-anchor="middle" y="${m === 1 ? 68 : 120}" class="svg-text" font-size="13" font-weight="700">${esc(gen)}</text>`;
    s += `<text x="0" y="${-R2 - 44}" text-anchor="middle" class="svg-faint" font-size="12" letter-spacing="3">KERNEL · FIXED · ${N} MODULES</text>`;
    s += `<text x="0" y="${R2 + 58}" text-anchor="middle" class="svg-faint" font-size="12" letter-spacing="3">ORGANS · LIVING · REWRITTEN ONLY WITH EVIDENCE</text>`;
    // lineage along the left
    const lin = data.lineage || [];
    lin.forEach((g, i) => {
      const y = -150 + i * 64, x = -470;
      const active = g.id === gen;
      s += `${i ? `<path d="M${x} ${y - 46} L${x} ${y - 16}" stroke="var(--line-2)" stroke-width="2"/>` : ''}
        <g class="node" data-kind="generation" data-name="${esc(g.id)}" data-note="generation|${esc(g.id)}" data-note-label="${esc(g.id)}" transform="translate(${x},${y})"><circle r="14" fill="${active ? '#ff8a3d' : 'var(--bg-3)'}" stroke="${active ? '#f8dc94' : 'var(--line-2)'}" stroke-width="2"/>
        <text x="24" y="-2" class="svg-text" font-size="12" font-weight="650">${esc(g.id.replace('gen-', ''))}</text><text x="24" y="13" class="svg-faint" font-size="10.5">${esc(trunc(g.label || '', 28))}</text><title>${esc(g.label || '')}</title></g>`;
    });
    if (lin.length) s += `<text x="-484" y="-190" class="svg-faint" font-size="11" letter-spacing="2">LINEAGE</text>`;
    s += `</g></svg>`;
    const holder = h('div', { html: s });
    const svg = holder.firstChild;
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', `Runesmith's anatomy: ${N} kernel modules, ${organs.length} organ${organs.length === 1 ? '' : 's'} and ${lin.length} generation${lin.length === 1 ? '' : 's'}. Tab to a part and press Enter for its details.`);
    const pz = panZoom(svg, svg.querySelector('.pz'));
    svg.addEventListener('click', (e) => { const n = e.target.closest('.node'); if (!n) return; selected = n.dataset.name; drawPanel(n.dataset.kind, n.dataset.name); draw(); });
    keyboardNodes(svg, (n) => {                     // details open beside the drawing, and the focus goes there
      selected = n.dataset.name; drawPanel(n.dataset.kind, n.dataset.name); draw();
      const head = panel.querySelector('h3'); if (head) { head.setAttribute('tabindex', '-1'); head.focus(); }
    });
    wrap.append(h('div.map-tools', h('button.btn.sm.icon', { 'aria-label': 'Zoom in', title: 'Zoom in', onclick: () => pz.zoom(1.2) }, icon('plus')),
      h('button.btn.sm.icon', { 'aria-label': 'Zoom out', title: 'Zoom out', onclick: () => pz.zoom(1 / 1.2) }, icon('minus')),
      h('button.btn.sm.icon', { 'aria-label': 'Reset the view', title: 'Reset view', onclick: () => pz.reset() }, icon('crosshair')), h('span.badge.rune', `Runesmith ${data.identity.version}`)), svg,
      h('div.map-legend', h('span', h('b', { style: { color: 'var(--rune)' } }, '■'), ' kernel module (fixed)'), h('span', h('b', { style: { color: 'var(--ember)' } }, '●'), ' organ (can be improved)'), h('span.faint', 'click any part')));
    wrap.append(panel);
  };
  const panel = h('div.map-side');
  const drawPanel = (kind, name) => {
    clear(panel);
    const close = h('button.btn.icon.sm.ghost', { onclick: () => { selected = null; drawPanel(); draw(); } }, icon('x'));
    if (kind === 'kernel' || kind === 'organ') {
      const c = kind === 'kernel' ? kernel.find((k) => k.path === name) : data.organs.find((o) => o.path.endsWith(name)) || { path: name };
      panel.append(...[h('div.row', h('div.grow', h('div.small.faint', kind === 'kernel' ? 'Kernel module · fixed' : 'Organ · improvable'), h('h3', { style: { margin: '2px 0 0' } }, c.path)), close),
        h('p.muted', c.purpose || 'No docstring.'),
        c.public_symbols?.length ? h('div', h('div.label-text', 'Public parts'), h('div.pillbox.mt-8', c.public_symbols.slice(0, 30).map((p) => h('span.badge.mono', p)))) : null,
        c.lines ? h('p.small.faint.mt-8', `${c.lines} lines`) : null,
        h('button.btn.sm.mt-8', { onclick: () => openNotes('component', c.path, c.path) }, icon('note'), 'Comment for the Improver')].filter(Boolean));
      return;
    }
    if (kind === 'generation') {
      const g = data.lineage.find((x) => x.id === name) || {};
      panel.append(h('div.row', h('div.grow', h('div.small.faint', 'Generation'), h('h3', { style: { margin: '2px 0 0' } }, g.id)), close),
        h('p.muted', g.label), kv([['Parent', g.parent || '—'], ['Frozen', g.frozen_utc], ['Organ digest', (g.organ_digest || '').slice(0, 22) + '…']]),
        h('button.btn.sm.mt-8', { onclick: () => ctx.navigate('improve') }, icon('spark'), 'Open Self-improvement'),
        h('button.btn.sm.mt-8', { onclick: () => openNotes('generation', g.id, g.id) }, icon('note'), 'Comment'));
      return;
    }
    // default: identity + capabilities
    panel.append(h('div.row', h('div.grow', h('div.small.faint', 'Runesmith itself'), h('h3', { style: { margin: '2px 0 0' } }, 'Self-knowledge')),
      h('button.btn.sm', { onclick: () => openNotes('self', 'runesmith', 'Runesmith itself') }, icon('note'), 'Comment')),
      h('p.small.muted', 'Everything here is read from Runesmith’s own bytes and its own records. Nothing is assumed: a capability without evidence says unknown.'));
    const capNames = { repair_yield: 'Repair yield', seconds_per_repair: 'Seconds per repair', calls_per_repair: 'Calls per repair', false_promotion_rate: 'False "fixed" rate' };
    for (const [k, label] of Object.entries(capNames)) {
      const c = data.capabilities[k] || { band: 'unknown', value: null };
      const row = h('div.gauge-row', h('span.small', label), h('div', { class: `bandbar${c.value == null ? ' unknown' : ''}` }, c.value != null ? h('span.mark', { style: { left: `${bandPosition(c)}%` } }) : null),
        h('span', { class: `band ${c.band}` }, c.value == null ? '?' : fmtCap(k, c.value)));
      commentable(row, 'capability', k, label);
      panel.append(row);
    }
    panel.append(h('div.divider'), h('div.label-text', 'What an organ may ask of the kernel'),
      h('div.col.gap-6.mt-8', Object.entries(data.affordances).map(([k, v]) => h('div.small', h('b.mono', k), h('span.muted', ` — ${v}`)))),
      h('div.divider'), h('div.label-text', 'Envelope per attempt'),
      kv(Object.entries(data.envelope).map(([k, v]) => [humanize(k), v])));
    if (data.open_targets?.length) panel.append(h('div.divider'), h('div.label-text', 'Where it struggles most (Kaizen targets)'),
      h('div.col.gap-6.mt-8', data.open_targets.map((t) => h('div.small', h('b', humanize(t.family || t.stage || t.kind || 'target')), h('span.muted', ` · share ${Math.round((t.share || 0) * 100)}%`)))));
    panel.append(h('div.divider'), h('div.label-text', 'Unknown'), h('ul.small.muted', { style: { paddingLeft: '18px' } }, data.unknowns.map((u) => h('li', u))));
  };
  body.append(wrap);
  drawPanel();
  draw();
}

// ============================================================== DEVELOPMENT ==
async function developmentLens(body, ctx) {
  const data = await get('/api/map/development');
  const lanes = [];
  const goals = (data.goals || []).filter((g) => g.status !== 'removed');
  const plan = data.plan;
  if (plan?.milestones?.length) {
    const byTrack = new Map();
    for (const m of plan.milestones) { const t = m.track || 'Plan'; if (!byTrack.has(t)) byTrack.set(t, []); byTrack.get(t).push(m); }
    for (const [t, ms] of byTrack) lanes.push({ kind: 'plan', label: t, sub: 'plan track', stations: ms.map((m) => ({ id: m.id, label: m.title, status: m.status === 'done' ? 'achieved' : m.status === 'doing' ? 'doing' : m.status === 'dropped' ? 'dropped' : 'open', note: ['milestone', m.id, m.title] })) });
  }
  for (const o of data.objects.map(scopedObject)) if (o.ladder?.length) lanes.push({ kind: 'object', label: o.name, sub: KIND[o.kind]?.label || o.kind, stations: o.ladder.map((r) => ({ id: r.rung, label: humanize(r.rung), status: r.status, next: o.next_rung === r.rung, note: ['rung', `${o.name}/${r.rung}`, `${o.name}: ${humanize(r.rung)}`] })) });
  if (data.lineage?.length) lanes.push({ kind: 'self', label: 'Runesmith itself', sub: 'generations', stations: data.lineage.map((g) => ({ id: g.id, label: g.id.replace('gen-', ''), status: g.active ? 'active' : 'achieved', note: ['generation', g.id, g.id], title: g.label })) });
  const goalsCard = h('div.card', h('div.card-head', h('h3', icon('target'), 'Operating toward'), h('div.actions', h('button.btn.sm', { onclick: () => ctx.navigate('goals') }, icon('plus'), 'Goals & plan'))),
    goals.length ? h('div.pillbox', goals.map((g) => { const c = h('span', { class: `chip${g.status === 'done' ? ' on' : ''}` }, icon(g.status === 'done' ? 'check' : 'target'), g.text); commentable(c, 'goal', g.id, g.text); c.querySelector('.note-btn').style.top = '-10px'; return c; }))
      : h('p.muted', 'No goals yet. Goals tell the planner and the map what matters to you.'));
  const laneW = 210, stepW = 158, rowH = 96;
  const maxStations = Math.max(3, ...lanes.map((l) => l.stations.length));
  const W = laneW + maxStations * stepW + 60, H = Math.max(1, lanes.length) * rowH + 30;
  let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg" style="display:block">`;
  lanes.forEach((lane, i) => {
    const y = 30 + i * rowH + 26;
    const color = lane.kind === 'self' ? 'var(--rune)' : lane.kind === 'plan' ? 'var(--violet)' : 'var(--ember)';
    s += `<rect x="8" y="${y - 32}" width="${W - 16}" height="${rowH - 12}" rx="14" fill="var(--bg-1)" stroke="var(--line)"/>`;
    s += `<text x="26" y="${y - 4}" class="svg-text" font-size="14" font-weight="680">${esc(trunc(lane.label, 22))}</text><text x="26" y="${y + 14}" class="svg-faint" font-size="11">${esc(lane.sub)}</text>`;
    const x0 = laneW, x1 = laneW + (lane.stations.length - 1) * stepW;
    s += `<path d="M${x0} ${y} L${x1} ${y}" stroke="var(--line-2)" stroke-width="4" stroke-linecap="round"/>`;
    const lastDone = lane.stations.reduce((m, st, j) => (st.status === 'achieved' || st.status === 'active' ? j : m), -1);
    if (lastDone > 0) s += `<path d="M${x0} ${y} L${laneW + lastDone * stepW} ${y}" stroke="${color}" stroke-width="4" stroke-linecap="round"/>`;
    lane.stations.forEach((st, j) => {
      const x = laneW + j * stepW;
      const fill = st.status === 'achieved' ? color : st.status === 'active' ? '#ff8a3d' : st.status === 'doing' ? 'var(--bg-2)' : 'var(--bg-2)';
      const stroke = st.status === 'unknown' ? 'var(--text-3)' : st.status === 'not_achieved' ? '#e8b04a' : st.status === 'dropped' ? 'var(--line-2)' : color;
      s += `<g class="node" data-lane="${i}" data-st="${j}" transform="translate(${x},${y})">${st.next || st.status === 'doing' ? `<circle r="17" fill="none" stroke="${color}" stroke-opacity=".45" stroke-width="5"><animate attributeName="r" values="14;19;14" dur="2.2s" repeatCount="indefinite"/></circle>` : ''}
        <circle r="10" fill="${fill}" stroke="${stroke}" stroke-width="2.5" ${st.status === 'unknown' ? 'stroke-dasharray="3 3"' : ''}/>
        ${st.status === 'achieved' || st.status === 'active' ? '<path d="M-4 0 L-1 3 L4 -3" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>' : ''}
        <text y="30" text-anchor="middle" class="${st.status === 'dropped' ? 'svg-faint' : 'svg-muted'}" font-size="11" ${st.status === 'dropped' ? 'text-decoration="line-through"' : ''}>${esc(trunc(st.label, 22))}</text><title>${esc(st.title || st.label)} — ${esc(st.status)}</title></g>`;
    });
  });
  if (!lanes.length) s += `<text x="${W / 2}" y="60" text-anchor="middle" class="svg-muted" font-size="14">No tracks yet: map the folder, set goals, or draft a plan.</text>`;
  s += '</svg>';
  const holder = h('div', { html: s, style: { overflowX: 'auto' } });
  const station = (n) => lanes[+n.dataset.lane].stations[+n.dataset.st];
  holder.addEventListener('click', (e) => { const n = e.target.closest('.node'); if (!n) return; openNotes(...station(n).note); });
  if (holder.firstChild) {
    holder.firstChild.setAttribute('role', 'group');
    holder.firstChild.setAttribute('aria-label', `${lanes.length} development track${lanes.length === 1 ? '' : 's'}. Tab to a station and press Enter to comment on it.`);
    keyboardNodes(holder.firstChild, (n) => openNotes(...station(n).note));
  }
  const tracks = h('div.card', h('div.card-head', h('h3', icon('route'), 'Development tracks'), h('span.badge', 'click a station to comment')), holder,
    h('div.row.mt-8.small.faint', h('span', { class: 'band optimal' }, 'achieved'), h('span', { class: 'band minimal' }, 'not yet'), h('span', { class: 'band unknown' }, 'unknown'), h('span', '· a glowing ring marks what is next')));
  const camp = h('div.card', h('div.card-head', h('h3', icon('spark'), 'Self-improvement campaigns')),
    data.campaigns.length ? h('div.list', data.campaigns.slice().reverse().map((c) => h('div.item', h('div', { class: `ico ${c.decision === 'candidate' ? 'good' : ''}` }, icon('beaker')),
      h('div.body', h('div.title', `${humanize(c.decision)} · target: ${humanize(c.target || '?')}`), h('div.meta', `${c.campaign} · ${c.attempts.length} attempt(s) · validation ${c.best ?? '—'} vs baseline ${c.baseline ?? '—'}`)))))
      : h('p.muted', 'None yet. Runesmith starts one when it has enough of its own experience (Settings → Self-improvement).'));
  body.append(goalsCard, h('div.mt-16'), tracks, h('div.mt-16'), camp);
}

// =============================================================== OPERATIONS ==
async function operationsLens(body, ctx) {
  const offs = [];
  const box = h('div');
  body.append(box);
  const load = async () => {
    const d = await get('/api/map/operations');
    clear(box);
    const w = d.worker;
    const liveStage = { mapping: 0, discovering: 1, working: 2, planning: -1, drafting: -1 }[w.status];
    const stages = [
      ['Map', 'map', d.pipeline.objects, 'objects'], ['Discover', 'search', d.pipeline.code_objects, 'code objects'],
      ['Repair', 'hammer', d.pipeline.attempts, 'attempts'], ['Judge', 'scale', d.pipeline.accepted, 'accepted'],
      ['Propose', 'inbox', d.pipeline.waiting, 'waiting'], ['You apply', 'user', d.pipeline.applied, 'applied']];
    const pipe = h('div.card', h('div.card-head', h('h3', icon('activity'), 'The work loop'),
      h('span', { class: `badge ${w.current ? 'rune' : w.paused ? 'warn' : ''}` }, w.current ? (w.detail || w.status) : w.paused ? 'paused' : 'idle')),
      h('div.pipeline', stages.map(([label, ic, n, unit], i) => h('div', { class: `stage${i === liveStage ? ' live' : ''}` }, h('div.orb', icon(ic)), h('b', String(n ?? 0)), h('span', `${label} · ${unit}`)))),
      h('p.tiny.faint', 'Runesmith never writes to your files on its own: every fix waits in Work & proposals until you apply it.'));
    const roles = h('div.card', h('div.card-head', h('h3', icon('cpu'), 'Who thinks what'), h('div.actions', h('button.btn.sm', { onclick: () => ctx.navigate('inference') }, 'Thinking power', icon('right')))));
    for (const [role, label] of Object.entries(d.role_labels)) {
      const names = d.roles[role] || [];
      const row = h('div.item', h('div', { class: `ico ${names.length ? 'rune' : 'warn'}` }, icon(role === 'repair' ? 'hammer' : role === 'kaizen' ? 'spark' : role === 'acceptance' ? 'check' : 'wand')),
        h('div.body', h('div.title', label), h('div.meta', names.length ? names.map((n) => { const st = d.stats[n]; return `${n}${st ? ` (${st.calls} calls, ${st.errors} errors, ~${(st.latency_s / Math.max(1, st.calls)).toFixed(1)} s)` : ''}`; }).join(' → ')
          : role === 'plan' && d.ready.plan ? `borrows the ${d.ready.plan_source} role's model`
          : role === 'acceptance' && d.ready.acceptance ? 'uses the Planner’s model' : 'no model yet')));
      roles.append(row);
    }
    const att = d.attention;
    const modeText = { HEALTHY: 'Healthy: most attention goes to your work', SUSPECTED_BLOCKAGE: 'A failure keeps recurring: the repairs may be struggling',
      SUBJECT_BLOCKED: 'Blocked by a recurring failure: the improvement plan treats it as a struggle', RECOVERING: 'Recovering after an improvement',
      CAPACITY_CONSTRAINED: 'Models are short of capacity: work waits, nothing is scored' };
    const attention = h('div.card', h('div.card-head', h('h3', icon('gauge'), 'Attention')),
      att ? h('div', h('div.kpi', h('div.v', `${Math.round(att.share * 100)}%`, h('small', 'self')), h('div.k', modeText[att.mode] || att.mode)),
        h('div.bar.rune.mt-8', h('i', { style: { width: `${att.share * 100}%` } })), h('p.tiny.faint.mt-8', 'Your share of work turns that go to improving Runesmith itself (Settings, Self-improvement). The line above is only a health signal: it shows when the same failure keeps recurring, and it no longer changes the share.'))
        : h('p.muted', 'Attention starts once Runesmith has worked on something.'));
    const t = d.trial;
    const trial = h('div.card', h('div.card-head', h('h3', icon('scale'), 'Trial')),
      t ? h('div', h('p.small', `${t.candidate} challenges ${t.incumbent}. New work is split between them by a seeded coin; the result decides activation.`),
        h('div.grid.two', ['incumbent', 'candidate'].map((arm) => h('div.kpi', h('div.k', arm), h('div.v', `${t.counts[arm][0]}`, h('small', `/ ${t.counts[arm][1]}`)), h('div.bar.mt-8', h('i', { style: { width: `${Math.min(100, t.counts[arm][1] / t.max_per_arm * 100)}%` } })))))) : h('p.muted', 'No trial open. A candidate generation must win one before it can become active.'));
    const sched = h('div.card', h('div.card-head', h('h3', icon('clock'), 'Schedule')),
      kv([['Autonomy', d.settings.autonomy === 'propose' ? 'Propose: works, then asks you' : 'Observe: maps and watches'], ['Scheduled rounds', d.settings.auto_work ? (d.settings.full_speed ? `full speed (waits at most ${d.settings.interval_minutes} min)` : `every ${d.settings.interval_minutes} min`) : 'off'],
        ['Next round', w.next_round_utc ? `${clock(w.next_round_utc)} (${ago(w.next_round_utc)})` : '—'], ['Last round', d.round_utc ? `${ago(d.round_utc)}: ${humanize(d.last_round?.outcome)}` : 'never']]),
      h('div.row.mt-8', h('button.btn.sm', { onclick: () => ctx.navigate('settings') }, icon('sliders'), 'Change')));
    const consoleBox = h('div.console');
    (w.lines || []).slice(-60).forEach((l) => consoleBox.append(h('div', { class: `l ${l.level || ''}` }, h('time', clock(l.utc)), l.text)));
    const live = h('div.card', h('div.card-head', h('h3', icon('activity'), 'Live log')), consoleBox);
    box.append(pipe, h('div.grid.two.mt-16', roles, attention), h('div.grid.two.mt-16', trial, sched), h('div.mt-16'), live);
    setTimeout(() => { consoleBox.scrollTop = 1e9; }, 0);
  };
  await load();
  const later = debounce(load, 500);
  for (const k of ['worker', 'round', 'call', 'improve', 'settings']) offs.push(bus.on(k, later));
  return () => offs.forEach((f) => f());
}
