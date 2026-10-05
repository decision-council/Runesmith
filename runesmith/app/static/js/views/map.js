// The living map: four lenses on one world. Environment, Self, Development, Operations.
import { h, icon, get, post, bus, toast, commentable, openNotes, clear, ago, plural, KIND, worstBand, BAND_COLOR,
  BAND_LABEL, humanize, cap, bytes, withBusy, clock, debounce, $ } from '../core.js';
import { iconSvg } from '../icons.js';
import { bandPosition, fmtCap } from './home.js';
import { automateSection, whatSection, evidenceSection, section, noAutomation, focusHeading, hhmm, when, panZoom, keyboardNodes, kv, scopedObject, withOverlay } from './map-parts.js';
import { structureSvg, structureList, nodePanel, groupPanel, morePanel, wireLinks } from './map-structure.js';
import { SIZE_NOTE } from './map-layout.js';
import selfLens from './map-self.js';
import developmentLens from './map-plan.js';
import operationsLens from './map-ops.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hubSize = (name) => { const n = String(name || 'Workspace').length; return n <= 9 ? 15 : n <= 12 ? 13.5 : n <= 15 ? 12 : 10.5; };
const trunc = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));
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
  ctx.refreshLens = () => ctx.navigate('map', lens.id);          // a control that changed what a lens draws asks for it again
  const draw = { environment: environmentLens, self: selfLens, development: developmentLens, operations: operationsLens }[lens.id];
  return draw(body, ctx);
}

// ============================================================== ENVIRONMENT ==
async function environmentLens(body, ctx) {
  const offs = [];
  const wrap = h('div.map-wrap');
  body.append(wrap);
  let data, selected = ctx.params.get('focus') || null;
  let focusAfter = null;                  // after a redraw: 'panel' (details just opened) or a node's name to return to
  let lastNarrow = null;
  // The structure of one object, when there is one to show: the only object the folder holds, or the one the owner asked for.
  let structure = null, structureNote = null, wanted = ctx.params.get('object') || null, mode = null, panelToken = 0;
  const expanded = new Set();             // folders the owner opened up past the drawing's cap
  // the drawing's width, even before the page is on screen (the first draw happens before it is attached)
  const availableWidth = () => wrap.clientWidth || ((document.querySelector('main.content')?.clientWidth || window.innerWidth) - 28);
  const isNarrow = () => availableWidth() < 560;
  const onResize = debounce(() => { if (data && isNarrow() !== lastNarrow) drawMap(); }, 200);
  window.addEventListener('resize', onResize);
  offs.push(() => window.removeEventListener('resize', onResize));

  const currentObjects = () => (data.map?.objects || []).map((o) => withOverlay(o, data.ladders));
  const targetName = () => {
    const real = (data.map?.objects || []).filter((o) => o.kind !== 'excluded');
    if (wanted && real.some((o) => o.name === wanted)) return wanted;
    return real.length === 1 ? real[0].name : null;
  };
  const loadStructure = async () => {
    structure = null; structureNote = null;
    const name = targetName();
    if (!name) return;
    try {
      const st = await get(`/api/map/structure?object=${encodeURIComponent(name)}&expand=${encodeURIComponent([...expanded].join('|'))}`);
      if (st && st.schema === 'runesmith.map.structure.v1') structure = st;
      else structureNote = `The structure of ${name} could not be read, so its objects are shown as before.`;
    } catch (error) { structureNote = `The structure of ${name} could not be read (${error.message || error}), so its objects are shown as before.`; }
  };
  const load = async () => {
    data = await get('/api/map/environment');
    await loadStructure();
    drawMap();
  };
  const drawMap = () => {
    const held = document.activeElement?.closest?.('.map-wrap .node, .map-wrap .lm-row')?.dataset.name;   // a live update keeps the focus
    if (!focusAfter && held) focusAfter = held;
    ++panelToken;
    clear(wrap);
    wrap.classList.remove('lm-flow', 'with-panel');
    const env = data.map;
    if (!env) { wrap.append(h('div.empty', icon('map', 'big'), h('h4', 'Mapping…'), h('p', 'The first map takes a few seconds.'))); return; }
    if (structure && !structure.empty) return drawStructure(env);
    const notice = structure?.empty ? structure.sentence : structureNote;
    const statuses = data.round.objects || {};
    const objects = currentObjects();
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
    if (notice) wrap.append(h('div.lm-notice.small', { role: 'status' }, icon('info'), notice));
    if (!others.length && facts.empty) wrap.append(h('div', { style: { position: 'absolute', left: '50%', top: '72%', transform: 'translate(-50%,0)', textAlign: 'center' } },
      h('p.muted', 'An empty world. Perfect for something new.'), h('button.btn.primary', { onclick: () => ctx.navigate('goals') }, icon('wand'), 'Tell Runesmith what to build')));
    if (selected) wrap.append(sidePanel(selected === '__hub' ? null : objects.find((o) => o.name === selected), env, data,
      () => { focusAfter = selected; selected = null; drawMap(); }, ctx, rootObj, selectionHooks()));
    if (focusAfter === 'panel') $('.map-side h3', wrap)?.focus();
    else if (focusAfter) svg.querySelector(`.node[data-name="${CSS.escape(focusAfter)}"]`)?.focus({ preventScroll: true });
    focusAfter = null;
  };
  // What a panel of an object may ask of this lens: open its structure.
  const selectionHooks = () => ({ showStructure: (name) => { wanted = name; selected = name; mode = null; expanded.clear(); load(); } });

  // ---- the structure of one object: its files around the project, grouped by folder
  const drawStructure = (env) => {
    const st = structure, objects = currentObjects();
    const obj = objects.find((o) => o.name === st.object.name) || { name: st.object.name, root: st.object.root, kind: st.object.kind, objectives: [], ladder: [] };
    const rootObj = objects.find((o) => o.root);
    const wsName = ctx.app.state?.workspace?.name || 'Workspace';
    const narrow = isNarrow();
    lastNarrow = narrow;
    if (!mode) mode = narrow ? 'list' : 'graph';
    const centreId = obj.root ? '__hub' : obj.name;
    const centreName = obj.root ? wsName : obj.name;
    const lines = hubLines(centreName), size = hubSize(lines.reduce((a, b) => (b.length > a.length ? b : a), ''));
    const centre = { id: centreId, name: centreName, note: obj.root ? 'workspace|root' : `object|${obj.name}`,
      spoken: `${centreName}, ${obj.root ? 'the whole workspace' : 'an object'}: ${st.counts.files} files. ${st.sentence}`,
      markup: lines.map((line, i) => `<text text-anchor="middle" y="${(lines.length > 1 ? -17 : -6) + i * (size + 2)}" class="svg-text" font-size="${size}" font-weight="750">${esc(line)}</text>`).join('')
        + `<text text-anchor="middle" y="${lines.length > 1 ? 18 : 14}" class="svg-muted" font-size="11.5">${st.counts.files}${st.truncated_scan ? '+' : ''} files</text>`
        + `<text text-anchor="middle" y="${lines.length > 1 ? 33 : 30}" class="svg-faint" font-size="10.5">${obj.root ? 'workspace' : 'object'}</text>` };
    const pick = (name) => { selected = name; focusAfter = 'panel'; drawMap(); };
    const expand = async (gid) => { expanded.has(gid) ? expanded.delete(gid) : expanded.add(gid); selected = `group:${gid}`; await loadStructure(); drawMap(); };
    const tools = h('div.map-tools.lm-tools');
    const content = [];
    const panelOpen = !!selected && !narrow;
    wrap.classList.add('lm-flow');
    wrap.classList.toggle('with-panel', panelOpen);
    let pz = null;
    if (mode === 'graph') {
      const built = structureSvg(st, { selected, centre });
      const holder = h('div', { html: built.markup });
      const svg = holder.firstChild;
      const room = availableWidth() - (panelOpen ? 372 : 0);          // an open panel takes its own room: nothing is drawn under it
      svg.style.height = `${Math.max(420, Math.min(820, Math.round(room * built.height / built.width)))}px`;
      pz = panZoom(svg, svg.querySelector('.pz'));
      wireLinks(svg, selected);
      svg.addEventListener('click', (e) => { const n = e.target.closest('.node'); if (n) pick(n.dataset.name); });
      svg.addEventListener('keydown', (e) => {
        const n = e.target.closest && e.target.closest('.node');
        if (!n || (e.key !== 'Enter' && e.key !== ' ')) return;
        e.preventDefault(); pick(n.dataset.name);
      });
      content.push(svg);
    } else {
      content.push(h('div.lm-listbox', h('p.small.muted', st.sentence), structureList(st, pick, selected)));
    }
    const several = (data.map?.objects || []).filter((o) => o.kind !== 'excluded').length > 1;
    tools.append(...[several ? h('button.btn.sm', { title: 'Back to the objects around the workspace', onclick: () => { wanted = null; selected = null; mode = null; expanded.clear(); load(); } }, icon('left'), 'All objects') : null,
      pz ? h('button.btn.sm.icon', { title: 'Zoom in', 'aria-label': 'Zoom in', onclick: () => pz.zoom(1.2) }, icon('plus')) : null,
      pz ? h('button.btn.sm.icon', { title: 'Zoom out', 'aria-label': 'Zoom out', onclick: () => pz.zoom(1 / 1.2) }, icon('minus')) : null,
      pz ? h('button.btn.sm.icon', { title: 'Reset view', 'aria-label': 'Reset the view', onclick: () => pz.reset() }, icon('crosshair')) : null,
      h('div.seg.lm-mode', { role: 'group', 'aria-label': 'How to show the parts' }, [['graph', 'Graph', 'branch'], ['list', 'List', 'menu']].map(([id, label, ic]) => h('button', { class: mode === id ? 'on' : '',
        'aria-pressed': String(mode === id), onclick: () => { mode = id; drawMap(); } }, icon(ic), label))),
      h('button.btn.sm', { title: 'Map again, running each object’s tests on throwaway copies', onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'map', params: { probe: true } }); toast('Mapping and measuring… the map updates when done.', 'good'); }) }, icon('refresh'), 'Re-map & measure'),
      h('span.badge', `mapped ${ago(env.utc)}`),
      data.outdated ? h('button.btn.sm.primary', { title: 'This map was made by an earlier version of Runesmith, which found less. Map again to see everything.',
        onclick: (e) => withBusy(e.currentTarget, async () => { await post('/api/worker/run', { job: 'map' }); toast('Mapping… the map updates when done.', 'good'); }) },
        icon('refresh'), 'Made by an earlier version: map again') : null].filter(Boolean));
    const runLine = st.run ? h('div.lm-runline.small', { 'data-run': '' }, icon('gauge'), h('span', st.run.words), null) : null;
    const others = (data.map?.objects || []).filter((o) => o.name !== st.object.name);
    const outside = others.length ? h('div.lm-runline.small', icon('lock'), h('span', `Not drawn: ${others.map((o) => (o.kind === 'excluded' ? `${o.name} (${o.reason === 'link' ? 'a link, not followed' : 'never touched'})` : o.name)).join(', ')}.`)) : null;
    wrap.append(tools, ...content, ...[runLine, outside].filter(Boolean),
      h('div.map-legend.lm-legend', ['bad', 'minimal', 'optimal', 'unknown'].map((b) => h('span', { class: `band ${b}` }, BAND_LABEL[b])),
        h('span.faint', '● source · ■ test · ▭ document · ▲ config · ◌ data'),
        h('span.faint.lm-key', h('svg', { class: 'lm-sw', viewBox: '0 0 26 8', width: 26, height: 8, 'aria-hidden': 'true' }, h('path', { class: 'lm-sw-imports', d: 'M1 4H25' })), 'imports'),
        h('span.faint.lm-key', h('svg', { class: 'lm-sw', viewBox: '0 0 26 8', width: 26, height: 8, 'aria-hidden': 'true' }, h('path', { class: 'lm-sw-tests', d: 'M1 4H25' })), 'a test reaches it'),
        h('span.faint.lm-key', h('svg', { class: 'lm-sw', viewBox: '0 0 26 8', width: 26, height: 8, 'aria-hidden': 'true' }, h('path', { class: 'lm-sw-bad', d: 'M1 4H25' })), 'a failing test'),
        h('span.faint', SIZE_NOTE),
        h('span.faint', 'dots: gold waits for you · violet changed by Runesmith · blue in an open milestone')));
    if (structureNote) wrap.append(h('div.lm-notice.small', { role: 'status' }, icon('info'), structureNote));
    if (selected) showPanel(st, obj, rootObj, env, expand);
    if (mode === 'graph' && focusAfter && focusAfter !== 'panel') wrap.querySelector(`.node[data-name="${CSS.escape(focusAfter)}"]`)?.focus({ preventScroll: true });
    else if (mode === 'list' && focusAfter && focusAfter !== 'panel') wrap.querySelector(`.lm-row[data-name="${CSS.escape(focusAfter)}"]`)?.focus({ preventScroll: true });
    if (focusAfter !== 'panel') focusAfter = null;
  };
  const showPanel = (st, obj, rootObj, env, expand) => {
    const token = panelToken, pick = selected;
    const close = () => { focusAfter = pick; selected = null; drawMap(); };
    let build;
    if (pick === '__hub' || pick === obj.name) build = async () => sidePanel(pick === '__hub' ? null : obj, env, data, close, ctx, rootObj, selectionHooks());
    else if (pick.startsWith('group:')) {
      const g = st.groups.find((x) => x.id === pick.slice(6));
      build = g ? () => groupPanel(g, st, ctx, close, expand) : null;
    } else if (pick.startsWith('more:')) {
      const g = st.groups.find((x) => x.id === pick.slice(5));
      build = g ? async () => morePanel(g, st, ctx, close, expand) : null;
    } else {
      const n = st.nodes.find((x) => x.id === pick);
      build = n ? () => nodePanel(n, st, ctx, close) : null;
    }
    if (!build) return;
    Promise.resolve(build()).then((el) => {
      if (token !== panelToken || !el) return;                     // the owner moved on while the controls were read
      wrap.append(el);
      if (focusAfter === 'panel') { focusAfter = null; focusHeading(el); }
    }).catch((error) => toast(error.message || String(error), 'warn'));
  };
  await load();
  // a control the owner is using (a field with text in it) is not redrawn under their hand
  const refresh = debounce(() => { if (document.activeElement?.closest?.('.lm-ctl input, .lm-ctl select')) return; load(); }, 300);
  offs.push(bus.on('map', refresh), bus.on('round', refresh));
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

function sidePanel(obj, env, data, close, ctx, rootObj, hooks) {
  const panel = h('div.map-side');
  const settings = data.settings;
  const top = h('div.row', h('div.grow', h('div.small.faint', obj ? (KIND[obj.kind]?.label || obj.kind) : 'Workspace'), h('h3', { style: { margin: '2px 0 0', fontSize: '17px' }, tabindex: '-1' }, obj ? obj.name : (ctx.app.state?.workspace?.name || 'Workspace'))),
    h('button.btn.icon.sm.ghost', { onclick: close, title: 'Close', 'aria-label': 'Close the details' }, icon('x')));
  panel.setAttribute('role', 'region');
  panel.setAttribute('aria-label', `Details: ${obj ? obj.name : 'the whole workspace'}`);
  panel.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('.modal-wrap, .drawer, .cmdk')) { e.stopPropagation(); close(); } });
  panel.append(top);
  const target = obj ? ['object', obj.name, obj.name] : ['workspace', 'root', 'the whole workspace'];
  panel.append(h('div.row.mt-8.wrap', h('button.btn.sm', { onclick: () => openNotes(...target) }, icon('note'), 'Comment'),
    obj && obj.kind !== 'excluded' && !obj.root ? h('button.btn.sm', { onclick: async (e) => withBusy(e.currentTarget, async () => {
      const ex = new Set(settings.exclude); ex.add(obj.name); await post('/api/settings', { exclude: [...ex] }); await post('/api/worker/run', { job: 'map' });
      toast(`${obj.name} is excluded: Runesmith will never probe or work on it.`, 'good'); }) }, icon('lock'), 'Exclude') : null,
    obj && obj.kind === 'excluded' ? h('button.btn.sm', { onclick: async (e) => withBusy(e.currentTarget, async () => {
      await post('/api/settings', { exclude: settings.exclude.filter((x) => x !== obj.name) }); await post('/api/worker/run', { job: 'map' }); toast(`${obj.name} is included again.`, 'good'); }) }, icon('eye'), 'Include') : null,
    obj && obj.kind !== 'excluded' && hooks?.showStructure ? h('button.btn.sm', { title: 'Draw this object’s files around it, with the links found in its code', onclick: () => hooks.showStructure(obj.name) }, icon('branch'), 'Show its structure') : null));
  const f0 = env.workspace_facts || {};
  panel.append(whatSection(obj ? objectWhat(obj) : `The folder you opened: ${f0.files ?? 0} files in ${plural((env.objects || []).length, 'object')}. The map reads it from disk and from Runesmith’s own records; where it has no evidence it says unknown.`));
  const ev = section('Evidence');
  const mapped = `the map written ${when(env.utc)}`;
  if (!obj) {
    const f = env.workspace_facts || {};
    const e = env.environment || {};
    ev.append(h('div.label-text', 'This folder'),
      kv([['Path', env.workspace], ['Files', f.files], ['Size', bytes(f.bytes)], ['Top-level entries', f.entries_total], ['Readme', f.readme || 'none'], ['Version control', f.version_control ? 'yes (git)' : 'no']]));
    if (f.top_extensions?.length) {
      const max = f.top_extensions[0][1];
      ev.append(h('div.label-text.mt-16', 'Kinds of files'), h('div.col.gap-6.mt-8', f.top_extensions.map(([ext, n]) =>
        h('div', h('div.row.small', h('span.mono', ext), h('span.spacer'), h('span.faint', n)), h('div.bar.rune', h('i', { style: { width: `${(n / max) * 100}%` } }))))));
    }
    if (rootObj) {
      const label = KIND[rootObj.kind]?.label || humanize(rootObj.kind);
      ev.append(h('div.divider'), h('div.row', h('span', { class: 'badge rune' }, label),
        h('span.small.muted', rootObj.kind === 'folder' ? 'the loose files at the top level' : 'this folder itself')), ...objectDetails(rootObj, env, data));
    }
    ev.append(h('div.divider'), h('div.label-text', 'This computer'),
      kv([['System', e.os], ['Python', e.python], ['Processors', e.cpus], ['Free disk', e.disk_free_gb != null ? `${e.disk_free_gb} GB` : '—']]));
    ev.append(h('div.divider'), h('div.label-text', 'What Runesmith does not know yet'),
      h('ul.small.muted', { style: { paddingLeft: '18px', margin: '6px 0 0' } }, (env.unknowns || []).map((u) => h('li', u))),
      h('div.tiny.faint.lm-src.mt-8', `Source: ${mapped}, from the folder on disk and this computer.`));
    panel.append(ev);
    const names = (env.objects || []).filter((o) => !o.root && o.reason !== 'link').map((o) => o.name);
    automateSection(ctx, ['auto_work', 'interval_minutes', 'probe_tests', 'max_objects', 'read_notes', { id: 'exclude', objects: names }, 'remap'])
      .then((sec) => panel.append(sec)).catch(() => {});
    return panel;
  }
  ev.append(...objectDetails(obj, env, data));
  ev.append(h('div.tiny.faint.mt-16.mono', obj.path),
    h('div.tiny.faint.lm-src', `Source: ${mapped}${obj.measured_utc ? `; its tests were last measured ${when(obj.measured_utc)}` : '; its tests were not measured by the map'}; each rung names the test run it rests on.`));
  panel.append(ev);
  const controls = obj.kind === 'excluded' ? [] : ['watch_tests', { id: 'fix_tests', object: obj.name }, { id: 'exclude', objects: obj.root ? [] : [obj.name] }, 'remap'];
  if (obj.kind === 'data_reports') controls.push({ id: 'link', label: 'Watch a number in these reports', now: 'A measurement reads the newest report and asks no model.', effect: 'The measurement editor, filled from this map.', button: 'Choose a number to watch', go: ['mission'] });
  if (obj.kind === 'excluded') panel.append(noAutomation(obj.reason === 'link' ? 'A link to another place is never followed: it can lead out of the folder.' : 'This object is on your never-touch list.',
    obj.reason === 'link' ? 'the rule that Runesmith never follows a link or junction out of the folder.' : 'Settings → Never touch, or the Include button above.'));
  else automateSection(ctx, controls).then((sec) => panel.append(sec)).catch(() => {});
  return panel;
}
const objectWhat = (o) => ({
  python_repository: 'A Python project. Its source files and tests can be drawn around it; its tests can be run on a throwaway copy of the folder.',
  node_repository: 'A Node project. Its source files and tests can be drawn around it; Runesmith does not run npm test, so its tests stay unknown.',
  document_collection: 'A collection of documents: its pages, the links between them, and whether the links resolve.',
  website: 'A website: its pages, styles, and whether its links and images resolve.',
  data_reports: 'A folder of report files (spreadsheets or CSV exports), whose numbers can be watched.',
  folder: 'A folder Runesmith has no richer template for: it is mapped by what it holds.',
  excluded: 'A folder on your never-touch list, or a link: it is listed here and never read, probed or worked on.',
}[o.kind] || 'Something Runesmith found in the folder and could not classify.');

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
    if (r.evidence?.note) box.append(h('div.tiny.faint.lm-src', { style: { marginLeft: '26px' } }, `Source: ${r.evidence.note}`));
  }
  return box;
}
