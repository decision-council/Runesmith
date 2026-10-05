// The structure graph of one mapped object: its files around the project, grouped by folder, with the links found in the
// code, and a list view that carries the same facts for the keyboard and screen readers (docs/MAP_LOGIC.md, sections 1 and 9).
// Where every part goes is decided in map-layout.js (pure geometry, tested without a browser); this file draws it.
import { h, icon, clear, plural, BAND_LABEL, BAND_COLOR } from '../core.js';
import { esc, hhmm, panel, section, whatSection, evidenceSection, automateSection, noAutomation } from './map-parts.js';
import { structureLayout, radiusOf, sectorPlan, listOrder, WIDE } from './map-layout.js';

export { radiusOf, structureLayout };
export const KIND_LABEL = { module: 'Source file', test: 'Test file', doc: 'Document', config: 'Configuration', data: 'Data or other file' };
const GLYPH = { bad: '✕', optimal: '✓', minimal: '–', unknown: '?', world_class: '★' };

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

const wedgePath = (a0, a1, rIn, rOut) => {
  const steps = Math.max(4, Math.ceil((a1 - a0) / 0.1));
  const outer = [], inner = [];
  for (let i = 0; i <= steps; i++) {
    const t = a0 + ((a1 - a0) * i) / steps;
    outer.push(`${(Math.cos(t) * rOut * WIDE).toFixed(1)} ${(Math.sin(t) * rOut).toFixed(1)}`);
    inner.push(`${(Math.cos(t) * rIn * WIDE).toFixed(1)} ${(Math.sin(t) * rIn).toFixed(1)}`);
  }
  return `M ${outer.join(' L ')} L ${inner.reverse().join(' L ')} Z`;
};

/** The structure drawing as SVG markup, plus the facts the page needs about it. */
export function structureSvg(st, { selected, centre }) {
  const lay = structureLayout(st);
  const { points, sectors, labels, edges, bounds } = lay;
  const pad = 28, W = bounds.maxX - bounds.minX + 2 * pad, H = bounds.maxY - bounds.minY + 2 * pad;
  const byId = new Map(st.nodes.map((n) => [n.id, n]));
  const groupOf = new Map(st.groups.map((g) => [g.id, g]));
  const hot = selected && !selected.startsWith('group:') && !selected.startsWith('more:') && byId.has(selected) ? selected : null;
  let s = `<svg class="map lm-structure" viewBox="${(bounds.minX - pad).toFixed(1)} ${(bounds.minY - pad).toFixed(1)} ${W.toFixed(1)} ${H.toFixed(1)}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="group"
    aria-label="${esc(`Structure of ${centre.name}: ${st.counts.drawn} of ${st.counts.files} files drawn around the project, ${st.counts.edges} links between them. Tab to a part and press Enter for its details, or use the list view.`)}"><defs><radialGradient id="hubg" cx="50%" cy="40%" r="70%"><stop offset="0" stop-color="#f8dc94"/><stop offset=".6" stop-color="#e8b04a"/><stop offset="1" stop-color="#c58a34"/></radialGradient></defs><g class="pz">`;
  sectors.forEach((w, i) => {                                   // a folder's sector, and the folders inside it
    s += `<path class="lm-wedge${i % 2 ? ' alt' : ''}" d="${wedgePath(w.a0, w.a1, w.rIn, w.rOut)}"/>`;
    for (const rg of w.regions.slice(1)) s += `<path class="lm-subwedge" d="${wedgePath(rg.a0, rg.a1, w.rIn + 4, rg.rOut)}"/>`;
  });
  // links first, so the parts sit on top of them: thin, faint, and brighter only for the part in hand
  for (const e of edges) {
    const on = hot && (e.from === hot || e.to === hot);
    s += `<path class="lm-edge ${e.type}${e.bad ? ' bad' : ''}${on ? ' hot' : hot ? ' dim' : ''}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" d="${e.d}"><title>${esc(`${e.type === 'tests' ? 'a test reaches' : 'imports'}: ${e.from} → ${e.to} (${e.how.join('; ')})${e.bad ? ' - the test is failing' : ''}`)}</title></path>`;
  }
  s += `<g class="node lm-centre${selected === centre.id ? ' sel' : ''}" data-name="${esc(centre.id)}" data-kind="centre" data-note="${esc(centre.note)}" data-note-label="${esc(centre.name)}"
    tabindex="0" role="button" aria-label="${esc(centre.spoken)}"><path class="halo" d="M-56 -86 L56 -86 L86 -56 L86 56 L56 86 L-56 86 L-86 56 L-86 -56 Z" fill="none" stroke="#e8b04a" stroke-opacity=".35" stroke-width="8"/>
    <path d="M-42 -66 L42 -66 L66 -42 L66 42 L42 66 L-42 66 L-66 42 L-66 -42 Z" fill="url(#hubg)"/>
    <path d="M-37.9 -56 L37.9 -56 L56 -37.9 L56 37.9 L37.9 56 L-37.9 56 L-56 37.9 L-56 -37.9 Z" fill="var(--bg-1)"/>${centre.markup}</g>`;
  for (const [id, p] of points) {
    const at = `translate(${p.x.toFixed(1)},${p.y.toFixed(1)})`;
    if (id.startsWith('more:')) {
      const gid = id.slice(5), g = groupOf.get(gid);
      s += `<g class="node lm-more${selected === id ? ' sel' : ''}" data-name="${esc(id)}" data-kind="more" transform="${at}" tabindex="0" role="button"
        aria-label="${esc(`${g.more} more files in ${g.label}, not drawn. Enter to see them.`)}"><rect x="-24" y="-18" width="48" height="52" fill="transparent"/><circle r="15" fill="var(--bg-2)" stroke="var(--line-2)" stroke-width="1.6" stroke-dasharray="3 3"/>
        <text text-anchor="middle" y="4" class="svg-text" font-size="11" font-weight="700">+${g.more}</text><text text-anchor="middle" y="30" class="svg-faint" font-size="9.5">more</text><title>${esc(`+${g.more} more files in ${g.label}`)}</title></g>`;
      continue;
    }
    const n = byId.get(id);
    const dots = (n.badges || []).filter((b) => BADGE_DOT[b.kind]).slice(0, 3).map((b, i) => `<circle cx="${p.r * 0.85 + 2}" cy="${-p.r * 0.85 + i * 8}" r="3.4" fill="${BADGE_DOT[b.kind]}"><title>${esc(b.text)}</title></circle>`).join('');
    s += `<g class="node lm-part lm-b-${n.state.band}${selected === id ? ' sel' : ''}" data-name="${esc(id)}" data-kind="part" data-note="file|${esc(centre.name)}/${esc(id)}" data-note-label="${esc(id)}"
      transform="${at}" tabindex="0" role="button" aria-label="${esc(spokenNode(n))}">
      <rect x="-42" y="${-p.r - 8}" width="84" height="${2 * p.r + 30}" fill="transparent"/>
      <rect class="halo" x="${-p.r - 7}" y="${-p.r - 7}" width="${2 * p.r + 14}" height="${2 * p.r + 14}" rx="${p.r + 7}" fill="none" stroke="${BAND_COLOR[n.state.band]}" stroke-opacity=".4" stroke-width="5"/>
      <g class="lm-shape">${shape(n, p.r)}</g>
      <text text-anchor="middle" y="4" class="lm-glyph" font-size="${Math.max(9, Math.min(13, p.r * 0.7))}">${GLYPH[n.state.band]}</text>${dots}
      <text text-anchor="middle" y="${p.r + 13}" class="svg-muted lm-name-text" font-size="10">${esc(p.label)}</text>
      <title>${esc(`${n.id} — ${KIND_LABEL[n.kind]} — ${BAND_LABEL[n.state.band]}`)}</title></g>`;
  }
  for (const lb of labels) {                                    // a folder's name and size, outside its outermost ring
    const g = groupOf.get(lb.gid), rx = lb.anchor === 'end' ? -lb.w : lb.anchor === 'middle' ? -lb.w / 2 : 0;
    if (lb.leader) {
      const w = sectors.find((x) => x.regions.some((r) => r.id === lb.gid)), rg = w.regions.find((r) => r.id === lb.gid);
      s += `<path class="lm-leader" d="M${(Math.cos(lb.t) * rg.rOut * WIDE).toFixed(1)} ${(Math.sin(lb.t) * rg.rOut).toFixed(1)} L${lb.x.toFixed(1)} ${lb.y.toFixed(1)}"/>`;
    }
    s += `<g class="node lm-group-label${lb.sub ? ' sub' : ''}${selected === `group:${lb.gid}` ? ' sel' : ''}" data-name="group:${esc(lb.gid)}" data-kind="group" transform="translate(${lb.x.toFixed(1)},${lb.y.toFixed(1)})" tabindex="0" role="button"
      aria-label="${esc(`Folder ${g.label}: ${plural(g.files, 'file')}`)}"><rect x="${rx.toFixed(1)}" y="-11" width="${lb.w}" height="22" rx="8" fill="var(--bg-2)" fill-opacity=".92" stroke="var(--line-2)"/>
      <text x="${(rx + lb.w / 2).toFixed(1)}" y="3.5" text-anchor="middle" class="svg-text lm-group-text" font-size="${lb.size}" font-weight="650">${esc(lb.text)}</text><title>${esc(`${g.label}: ${plural(g.files, 'file')}`)}</title></g>`;
  }
  s += '</g></svg>';
  return { markup: s, width: W, height: H, layout: lay };
}

/** A part in hand brightens its own links and dims the rest; leaving it restores the selected part's. Classes only: the
 *  drawing is never redrawn for a hover, so the focus and the pointer stay where they are. */
export function wireLinks(svg, selected) {
  const links = [...svg.querySelectorAll('.lm-edge')];
  const base = selected && !selected.startsWith('group:') && !selected.startsWith('more:') && svg.querySelector(`.lm-part[data-name="${CSS.escape(selected)}"]`) ? selected : null;
  const show = (id) => {
    for (const e of links) { const on = !!id && (e.dataset.from === id || e.dataset.to === id); e.classList.toggle('hot', on); e.classList.toggle('dim', !!id && !on); }
  };
  const part = (e) => e.target.closest?.('.node.lm-part');
  const left = (e) => { const n = part(e); return n && !(e.relatedTarget && n.contains(e.relatedTarget)); };
  svg.addEventListener('pointerover', (e) => { const n = part(e); if (n) show(n.dataset.name); });
  svg.addEventListener('pointerout', (e) => { if (left(e)) show(base); });
  svg.addEventListener('focusin', (e) => { const n = part(e); if (n) show(n.dataset.name); });
  svg.addEventListener('focusout', (e) => { if (left(e)) show(base); });
}

/** The list view: every part, in the folders of the drawing in the order the drawing places them (a folder inside a folder under
 *  its parent), as buttons in the page's normal tab order. */
export function structureList(st, onPick, selected) {
  const box = h('div.lm-list', { role: 'group', 'aria-label': `List view: ${plural(st.nodes.length, 'file')} with their states` });
  const plan = sectorPlan(st);
  const folder = (g, subs, index) => {
    const members = listOrder(plan.byGroup.get(g.id) || []);
    const bad = members.filter((n) => n.state.band === 'bad').length;
    const inside = subs.flatMap((x) => plan.byGroup.get(x.id) || []);
    const open = index < 3 || [...members, ...inside].some((n) => selected === n.id) || bad > 0;
    return h('details.lm-group', { open, class: index < 0 ? 'lm-subgroup' : '' },
      h('summary', h('b', g.label), ` · ${plural(g.files, 'file')}`, bad ? h('span.badge.bad', `${bad} bad`) : null),
      h('ul.lm-rows', { role: 'list' }, members.map((n) => h('li', h('button.lm-row', { type: 'button', 'data-name': n.id, 'aria-label': spokenNode(n), class: selected === n.id ? 'sel' : '', onclick: () => onPick(n.id) },
        h('span.lm-kind', KIND_LABEL[n.kind]), h('span.lm-name.mono', n.name), h('span', { class: `band ${n.state.band}` }, BAND_LABEL[n.state.band]),
        n.lines != null ? h('span.tiny.faint', `${n.lines} lines`) : null,
        ...(n.badges || []).slice(0, 3).map((b) => h('span.badge.rune', b.text)))))),
      ...subs.map((x) => folder(x, [], -1)));
  };
  plan.sectors.forEach((sec, i) => { if ((plan.byGroup.get(sec.own.id) || []).length || sec.subs.length) box.append(folder(sec.own, sec.subs, i)); });
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
