// The structure graph of one mapped object: its files around the project, grouped by folder, with the links found in the
// code, and a list view that carries the same facts for the keyboard and screen readers (docs/MAP_LOGIC.md, section 1).
import { h, icon, clear, plural, BAND_LABEL, BAND_COLOR } from '../core.js';
import { esc, trunc, hhmm, panel, section, whatSection, evidenceSection, automateSection, noAutomation } from './map-parts.js';

const SLOT = 80, R0 = 122, DR = 60, GAP = 0.05, WIDE = 1.2;
export const KIND_LABEL = { module: 'Source file', test: 'Test file', doc: 'Document', config: 'Configuration', data: 'Data or other file' };
const GLYPH = { bad: '✕', optimal: '✓', minimal: '–', unknown: '?', world_class: '★' };

/** Radius of a part: it grows with its lines, on a log scale, clamped. */
export const radiusOf = (lines) => (lines == null ? 10 : Math.max(8, Math.min(24, 8 + 4.6 * Math.log10(1 + Math.max(0, lines)))));

/** Places every drawn part. Folders take sectors of the circle in path order; inside a sector the parts fill rings from the
 *  centre outwards in name order. The same structure always gives the same drawing: nothing here is random or measured. */
export function structureLayout(st, wide = WIDE) {
  const groups = st.groups.map((g) => ({ ...g, items: [] }));
  const byId = new Map(groups.map((g) => [g.id, g]));
  for (const n of st.nodes.filter((x) => x.drawn)) byId.get(n.group)?.items.push({ kind: 'node', n });
  for (const g of groups) { g.items.sort((a, b) => (a.n.id < b.n.id ? -1 : 1)); if (g.more > 0) g.items.push({ kind: 'more', g }); }
  const live = groups.filter((g) => g.items.length);
  const total = live.reduce((a, g) => a + g.items.length, 0) || 1;
  const usable = 2 * Math.PI - GAP * live.length;
  let a0 = -Math.PI / 2;
  const points = new Map(), wedges = [];
  for (const g of live) {
    g.angle = usable * (0.6 * (g.items.length / total) + 0.4 / live.length);
    let i = 0, k = 0, first = a0;
    while (i < g.items.length) {
      const r = R0 + k * DR;
      const take = Math.min(Math.max(1, Math.floor((g.angle * r * wide) / SLOT)), g.items.length - i);
      for (let j = 0; j < take; j++) {
        const t = a0 + ((j + 0.5) * g.angle) / take;
        const item = g.items[i + j];
        points.set(item.kind === 'node' ? item.n.id : `more:${g.id}`, { x: Math.cos(t) * r * wide, y: Math.sin(t) * r, r: item.kind === 'node' ? radiusOf(item.n.lines) : 15, ring: k });
      }
      i += take; k++;
    }
    const wedge = { g, a0: first, a1: first + g.angle, rOut: R0 + (k - 1) * DR + 40, rings: k };
    const t = (wedge.a0 + wedge.a1) / 2, r = wedge.rOut + 14 + (wedges.length % 2) * 14;     // its name, just outside its outermost ring
    wedge.label = { x: Math.cos(t) * r * wide, y: Math.sin(t) * r, anchor: Math.abs(Math.cos(t)) < 0.3 ? 'middle' : Math.cos(t) > 0 ? 'start' : 'end' };
    wedges.push(wedge);
    a0 += g.angle + GAP;
  }
  const xs = [...points.values()].flatMap((p) => [p.x - 54, p.x + 54]), ys = [...points.values()].flatMap((p) => [p.y - 40, p.y + 46]);
  const lx = wedges.flatMap((w) => [w.label.x - (w.label.anchor === 'end' ? 120 : w.label.anchor === 'middle' ? 60 : 0), w.label.x + (w.label.anchor === 'start' ? 120 : w.label.anchor === 'middle' ? 60 : 0)]);
  const ly = wedges.flatMap((w) => [w.label.y - 16, w.label.y + 14]);
  const minX = Math.min(-120, ...xs, ...lx), maxX = Math.max(120, ...xs, ...lx);
  const minY = Math.min(-110, ...ys, ...ly), maxY = Math.max(110, ...ys, ...ly);
  return { points, wedges, bounds: { minX, maxX, minY, maxY }, wide };
}

const shape = (n, r) => {
  if (n.kind === 'test') return `<rect x="${-r}" y="${-r}" width="${2 * r}" height="${2 * r}" rx="4"/>`;
  if (n.kind === 'doc') return `<rect x="${-r * 1.3}" y="${-r * 0.8}" width="${r * 2.6}" height="${r * 1.6}" rx="3"/>`;
  if (n.kind === 'config') return `<path d="M0 ${-r * 1.15} L${r * 1.1} ${r * 0.85} L${-r * 1.1} ${r * 0.85} Z" stroke-linejoin="round"/>`;
  if (n.kind === 'data') return `<circle r="${r}" stroke-dasharray="3 3"/>`;
  return `<circle r="${r}"/>`;
};
const BADGE_DOT = { fix_waiting: 'var(--gold)', draft_waiting: 'var(--gold)', changed: 'var(--violet)', milestone: 'var(--sky)' };

/** The words a screen reader hears for a part: what it is, where, its state and why, and what waits on it. */
export function spokenNode(n) {
  const badges = (n.badges || []).map((b) => b.text).slice(0, 3).join('; ');
  return [`${n.id}: ${KIND_LABEL[n.kind] || n.kind}`, n.lines != null ? `${n.lines} lines` : '', `${BAND_LABEL[n.state.band]}: ${n.state.reason}`, badges].filter(Boolean).join(', ');
}

const wedgePath = (w, wide) => {
  const rIn = R0 - 42, steps = Math.max(4, Math.ceil((w.a1 - w.a0) / 0.12));
  const outer = [], inner = [];
  for (let i = 0; i <= steps; i++) {
    const t = w.a0 + ((w.a1 - w.a0) * i) / steps;
    outer.push(`${(Math.cos(t) * w.rOut * wide).toFixed(1)} ${(Math.sin(t) * w.rOut).toFixed(1)}`);
    inner.push(`${(Math.cos(t) * rIn * wide).toFixed(1)} ${(Math.sin(t) * rIn).toFixed(1)}`);
  }
  return `M ${outer.join(' L ')} L ${inner.reverse().join(' L ')} Z`;
};

/** The structure drawing as SVG markup, plus the facts the page needs about it. */
export function structureSvg(st, { selected, centre, wsName, groupsOpen }) {
  const lay = structureLayout(st);
  const { points, wedges, bounds, wide } = lay;
  const pad = 40, W = bounds.maxX - bounds.minX + 2 * pad, H = bounds.maxY - bounds.minY + 2 * pad + 40;
  const top = bounds.minY - pad - 40;
  const byId = new Map(st.nodes.map((n) => [n.id, n]));
  const hot = selected && !selected.startsWith('group:') && !selected.startsWith('more:') ? selected : null;
  let s = `<svg class="map lm-structure" viewBox="${bounds.minX - pad} ${top} ${W} ${H}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="group"
    aria-label="${esc(`Structure of ${centre.name}: ${st.counts.drawn} of ${st.counts.files} files drawn around the project, ${st.counts.edges} links between them. Tab to a part and press Enter for its details, or use the list view.`)}"><defs><radialGradient id="hubg" cx="50%" cy="40%" r="70%"><stop offset="0" stop-color="#f8dc94"/><stop offset=".6" stop-color="#e8b04a"/><stop offset="1" stop-color="#c58a34"/></radialGradient></defs><g class="pz">`;
  wedges.forEach((w, i) => {
    s += `<path class="lm-wedge${i % 2 ? ' alt' : ''}" d="${wedgePath(w, wide)}"/>`;
  });
  // links first, so the parts sit on top of them
  for (const e of st.edges) {
    const a = points.get(e.from), b = points.get(e.to);
    if (!a || !b) continue;
    const mx = ((a.x + b.x) / 2) * 0.55, my = ((a.y + b.y) / 2) * 0.55;
    const on = hot && (e.from === hot || e.to === hot);
    s += `<path class="lm-edge ${e.type}${on ? ' hot' : hot ? ' dim' : ''}" d="M${a.x.toFixed(1)} ${a.y.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}"><title>${esc(`${e.type === 'tests' ? 'tests' : 'imports'}: ${e.from} → ${e.to} (${(e.how || []).join('; ')})`)}</title></path>`;
  }
  // the centre: the project itself
  s += `<g class="node lm-centre${selected === centre.id ? ' sel' : ''}" data-name="${esc(centre.id)}" data-kind="centre" data-note="${esc(centre.note)}" data-note-label="${esc(centre.name)}"
    tabindex="0" role="button" aria-label="${esc(centre.spoken)}"><path class="halo" d="M-56 -86 L56 -86 L86 -56 L86 56 L56 86 L-56 86 L-86 56 L-86 -56 Z" fill="none" stroke="#e8b04a" stroke-opacity=".35" stroke-width="8"/>
    <path d="M-42 -66 L42 -66 L66 -42 L66 42 L42 66 L-42 66 L-66 42 L-66 -42 Z" fill="url(#hubg)"/>
    <path d="M-37.9 -56 L37.9 -56 L56 -37.9 L56 37.9 L37.9 56 L-37.9 56 L-56 37.9 L-56 -37.9 Z" fill="var(--bg-1)"/>${centre.markup}</g>`;
  for (const [id, p] of points) {
    if (id.startsWith('more:')) {
      const gid = id.slice(5), g = st.groups.find((x) => x.id === gid);
      s += `<g class="node lm-more${selected === id ? ' sel' : ''}" data-name="${esc(id)}" data-kind="more" transform="translate(${p.x.toFixed(1)},${p.y.toFixed(1)})" tabindex="0" role="button"
        aria-label="${esc(`${g.more} more files in ${g.label}, not drawn. Enter to see them.`)}"><rect x="-24" y="-18" width="48" height="52" fill="transparent"/><circle r="15" fill="var(--bg-2)" stroke="var(--line-2)" stroke-width="1.6" stroke-dasharray="3 3"/>
        <text text-anchor="middle" y="4" class="svg-text" font-size="11" font-weight="700">+${g.more}</text><text text-anchor="middle" y="30" class="svg-faint" font-size="9.5">more</text><title>${esc(`+${g.more} more files in ${g.label}`)}</title></g>`;
      continue;
    }
    const n = byId.get(id);
    const dots = (n.badges || []).filter((b) => BADGE_DOT[b.kind]).slice(0, 3).map((b, i) => `<circle cx="${p.r * 0.85 + 2}" cy="${-p.r * 0.85 + i * 8}" r="3.4" fill="${BADGE_DOT[b.kind]}"><title>${esc(b.text)}</title></circle>`).join('');
    s += `<g class="node lm-part lm-b-${n.state.band}${selected === id ? ' sel' : ''}" data-name="${esc(id)}" data-kind="part" data-note="file|${esc(centre.name)}/${esc(id)}" data-note-label="${esc(id)}"
      transform="translate(${p.x.toFixed(1)},${p.y.toFixed(1)})" tabindex="0" role="button" aria-label="${esc(spokenNode(n))}">
      <rect x="-42" y="${-p.r - 8}" width="84" height="${2 * p.r + 30}" fill="transparent"/>
      <rect class="halo" x="${-p.r - 7}" y="${-p.r - 7}" width="${2 * p.r + 14}" height="${2 * p.r + 14}" rx="${p.r + 7}" fill="none" stroke="${BAND_COLOR[n.state.band]}" stroke-opacity=".4" stroke-width="5"/>
      <g class="lm-shape">${shape(n, p.r)}</g>
      <text text-anchor="middle" y="4" class="lm-glyph" font-size="${Math.max(9, Math.min(13, p.r * 0.7))}">${GLYPH[n.state.band]}</text>${dots}
      <text text-anchor="middle" y="${p.r + 13}" class="svg-muted" font-size="10">${esc(trunc(n.name, 15))}</text>
      <title>${esc(`${n.id} — ${KIND_LABEL[n.kind]} — ${BAND_LABEL[n.state.band]}`)}</title></g>`;
  }
  for (const w of wedges) {                                   // a folder's name, just outside its outermost ring
    const { x, y, anchor } = w.label;
    const label = w.g.id === '' ? 'top level' : w.g.id.split('/').slice(-2).join('/');
    s += `<g class="node lm-group-label${selected === `group:${w.g.id}` ? ' sel' : ''}" data-name="group:${esc(w.g.id)}" data-kind="group" transform="translate(${x.toFixed(1)},${y.toFixed(1)})" tabindex="0" role="button"
      aria-label="${esc(`Folder ${w.g.label}: ${plural(w.g.files, 'file')}`)}"><rect x="${anchor === 'end' ? -118 : anchor === 'middle' ? -59 : 0}" y="-13" width="118" height="22" rx="8" fill="var(--bg-2)" fill-opacity=".85" stroke="var(--line-2)"/>
      <text x="${anchor === 'end' ? -59 : anchor === 'middle' ? 0 : 59}" y="2" text-anchor="middle" class="svg-text" font-size="10.5" font-weight="650">${esc(trunc(label, 17))} · ${w.g.files}</text><title>${esc(`${w.g.label}: ${plural(w.g.files, 'file')}`)}</title></g>`;
  }
  s += '</g></svg>';
  return { markup: s, width: W, height: H };
}

/** The list view: every part, in folders, as buttons in the page's normal tab order. */
export function structureList(st, onPick, selected) {
  const box = h('div.lm-list', { role: 'group', 'aria-label': `List view: ${plural(st.nodes.length, 'file')} with their states` });
  const groups = st.groups;
  for (const [gi, g] of groups.entries()) {
    const members = st.nodes.filter((n) => n.group === g.id);
    if (!members.length) continue;
    const bad = members.filter((n) => n.state.band === 'bad').length;
    box.append(h('details.lm-group', { open: gi < 3 || members.some((n) => selected === n.id) || bad > 0 },
      h('summary', h('b', g.label), ` · ${plural(g.files, 'file')}`, bad ? h('span.badge.bad', `${bad} bad`) : null),
      h('ul.lm-rows', { role: 'list' }, members.map((n) => h('li', h('button.lm-row', { type: 'button', 'data-name': n.id, 'aria-label': spokenNode(n), class: selected === n.id ? 'sel' : '', onclick: () => onPick(n.id) },
        h('span.lm-kind', KIND_LABEL[n.kind]), h('span.lm-name.mono', n.name), h('span', { class: `band ${n.state.band}` }, BAND_LABEL[n.state.band]),
        n.lines != null ? h('span.tiny.faint', `${n.lines} lines`) : null,
        ...(n.badges || []).slice(0, 3).map((b) => h('span.badge.rune', b.text))))))));
  }
  if (st.counts.files > st.nodes.length) box.append(h('p.small.muted', `The list holds ${st.nodes.length} of ${st.counts.files} files: a folder this large is read in part. The counts above are the whole folder's.`));
  return box;
}

// ------------------------------------------------------------------------------------------------ panels --

const sentenceFor = (n, st) => {
  const imports = (n.imports || []).length, by = (n.imported_by || []).length;
  const size = n.lines != null ? `${n.lines} line${n.lines === 1 ? '' : 's'}` : 'a file whose lines are not counted';
  const where = n.group ? `in ${n.group}` : 'at the top of the project';
  if (n.kind === 'module') return `A source file${n.language ? ` in ${n.language}` : ''} of ${size}, ${where}. It imports ${imports ? plural(imports, 'other file') : 'no other file of the project'} and is imported by ${by ? plural(by, 'file') : 'none'}.`;
  if (n.kind === 'test') return `A test file of ${size}, ${where}. It reaches ${(n.reaches || []).length ? plural(n.reaches.length, 'source file') : 'no source file'}, by importing it or by being named for it.`;
  if (n.kind === 'doc') return `A document of ${size}, ${where}. Runesmith reads it to map the project; no test reaches it.`;
  if (n.kind === 'config') return `A configuration file of ${size}, ${where}: how the project is set up, not code that runs on its own.`;
  return `A file of ${size}, ${where}, that is neither code, a document nor configuration.`;
};

/** The panel of one part: What this is, Evidence, Automate. */
export async function nodePanel(n, st, ctx, close) {
  const obj = st.object;
  const el = panel({ eyebrow: `${KIND_LABEL[n.kind]} · ${n.group || 'top of the project'}`, title: n.id, onClose: close, note: ['file', `${obj.name}/${n.id}`, n.id] });
  el.append(h('div.row.mt-8.wrap', h('span', { class: `band ${n.state.band}` }, BAND_LABEL[n.state.band]),
    ...(n.badges || []).map((b) => h('span.badge.rune', { title: b.source }, b.text))));
  el.append(whatSection(sentenceFor(n, st)), evidenceSection(n.evidence));
  const container = { objects: obj.root ? [] : [obj.name], object: obj.name };
  if (n.kind === 'module') {
    el.append(await automateSection(ctx, ['watch_tests', { id: 'fix_tests', ...container }, { id: 'milestone_form', title: `Work on ${n.id}`, done_when: '' }, { id: 'exclude', ...container }]));
  } else if (n.kind === 'test') {
    el.append(await automateSection(ctx, ['watch_tests', { id: 'link', label: 'Open its results in Activity', now: 'Activity keeps what each round found, with times.', effect: 'The page that already lists every round and job.', button: 'Open Activity', go: ['activity'] }]));
  } else if (n.kind === 'doc') {
    el.append(await automateSection(ctx, [{ id: 'link', label: 'Documents a model may read', now: 'You choose which documents a model may read as blueprints.', effect: 'Goals & plan → the brief and its blueprints. Notes you write travel with the work they are about.', button: 'Open Goals & plan', go: ['goals'] }]));
  } else {
    el.append(noAutomation(`Runesmith reads a ${KIND_LABEL[n.kind].toLowerCase()} for the map and does not act on it.`,
      'the never-touch list in Settings keeps Runesmith out of a whole object; automatic apply is limited to the folders you allow in Goals & plan.',
      [{ label: 'Open Settings', go: () => ctx.navigate('settings') }]));
  }
  return el;
}

export async function groupPanel(g, st, ctx, close, onExpand) {
  const members = st.nodes.filter((n) => n.group === g.id);
  const count = (band) => members.filter((n) => n.state.band === band).length;
  const kinds = Object.entries(members.reduce((o, n) => ({ ...o, [n.kind]: (o[n.kind] || 0) + 1 }), {})).map(([k, v]) => `${v} ${KIND_LABEL[k].toLowerCase()}${v === 1 ? '' : 's'}`);
  const el = panel({ eyebrow: 'Folder', title: g.label, onClose: close });
  const disk = `read from disk at ${hhmm(st.built_utc)}`;
  el.append(whatSection(`A folder of ${st.object.name}: ${plural(g.files, 'file')}, drawn together so the picture stays readable.`),
    evidenceSection([
      { label: 'Files', value: `${g.files} (${kinds.join(', ') || 'none'})`, source: disk },
      { label: 'States of its files', value: `${count('bad')} bad · ${count('minimal')} minimal · ${count('optimal')} optimal · ${count('unknown')} unknown`, source: "each file's own state: select one to see why" },
      { label: 'Drawn', value: g.more > 0 ? `${g.drawn} of ${g.files}; ${g.more} more are in the list view` : `all ${g.files}`, source: 'the map keeps about 60 parts drawn' }],
    g.more > 0 ? h('button.btn.sm.mt-8', { onclick: () => onExpand(g.id) }, icon('plus'), g.expanded ? 'Show fewer' : `Show all ${g.files}`) : null));
  el.append(noAutomation('A folder inside a project cannot be kept out on its own: the never-touch list works on whole objects, the top-level folders the map lists.',
    'Settings → Never touch (objects); Goals & plan → Allowed files or folders (where a checked draft may be written automatically).',
    [{ label: 'Open Settings', go: () => ctx.navigate('settings') }, { label: 'Open Goals & plan', go: () => ctx.navigate('goals') }]));
  return el;
}

export function morePanel(g, st, ctx, close, onExpand) {
  const el = panel({ eyebrow: 'More files', title: `+${g.more} in ${g.label}`, onClose: close });
  el.append(whatSection(`${plural(g.more, 'file')} of ${g.label} that are not drawn, so the picture stays readable. They are all in the list view.`),
    evidenceSection([{ label: 'Not drawn', items: (g.more_ids || []).slice(0, 40), source: `read from disk at ${hhmm(st.built_utc)}; the smallest and the untroubled parts of the folder` }],
      h('button.btn.sm.mt-8', { onclick: () => onExpand(g.id) }, icon('plus'), `Show them in the drawing (${g.files} files)`)),
    noAutomation('This is a count of files, not a part of its own.', 'each file has its own panel; the list view reaches every one.'));
  return el;
}

export const hubSentence = (st) => st.sentence;
export { section };
