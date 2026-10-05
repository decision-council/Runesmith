// Self: Runesmith's own anatomy: a fixed kernel ring, living organs, its lineage of generations in parent-to-child order
// with their trial states, and the self-knowledge metrics with their samples (docs/MAP_LOGIC.md, section 2).
import { h, icon, get, post, bus, toast, clear, plural, humanize, BAND_LABEL, openNotes, commentable, debounce } from '../core.js';
import { bandPosition, fmtCap } from './home.js';
import { esc, trunc, hhmm, when, panel as lmPanel, section, whatSection, evidenceSection, automateSection, noAutomation, focusHeading,
  panZoom, keyboardNodes, kv } from './map-parts.js';

const CAP = 8;                                             // stations drawn; the older ones are one "+N earlier" part
export const STATE_SHORT = { active: 'active', on_trial: 'on trial', won: 'won its trial', rejected: 'rejected', rolled_back: 'rolled back',
  frozen: 'frozen', superseded: 'replaced', trial_stopped: 'trial stopped', imported: 'imported', unknown: 'not read' };
const ORIGIN_WORDS = { shipped: 'shipped with Runesmith', kaizen: 'written by a self-improvement campaign (a model authored the change)',
  imported: 'imported from the library of proven generations', requalified: 'the same organs, re-checked under a newer kernel' };
const CAP_NAMES = { repair_yield: 'Repair yield', seconds_per_repair: 'Seconds per repair', calls_per_repair: 'Calls per repair', false_promotion_rate: 'False "fixed" rate' };

/** Stations from the ordered lineage, or (when it could not be built) from the old list, with no state claimed. */
function stationsOf(data) {
  const ordered = data.lineage_ordered?.stations;
  if (ordered) return { stations: ordered, ordered: true };
  const active = data.identity.active_generation;
  return { ordered: false, stations: (data.lineage || []).map((g) => ({ id: g.id, name: g.id.replace('gen-', ''), label: g.label, parent: g.parent, depth: 0,
    state: 'unknown', state_words: 'Its state could not be read; it is listed as the manifests were found.', tick: g.id === active, active: g.id === active,
    created_utc: g.frozen_utc, organ_digest: g.organ_digest, origin: 'unknown', source: 'generations/' + g.id + '/MANIFEST.json' })) };
}

export async function generationPanel(g, stations, ctx, onClose) {
  const nameOf = (id) => stations.find((x) => x.id === id)?.name || id;
  const el = lmPanel({ eyebrow: `Generation · ${STATE_SHORT[g.state] || g.state}`, title: g.name, onClose, note: ['generation', g.id, g.id] });
  const t = g.trial;
  const trialRows = !t ? [{ label: 'Trial', value: 'none recorded for this generation', source: 'TRIAL.json and the closed trial records' }] : [
    { label: 'Trial', value: t.state === 'open'
      ? `open against ${nameOf(t.incumbent)}: candidate ${t.counts.candidate[0]}/${t.counts.candidate[1]}, incumbent ${t.counts.incumbent[0]}/${t.counts.incumbent[1]}; ${plural(t.looks, 'look')} done; next look when each arm has ${t.next_look_at}; at most ${t.max_per_arm} per arm; level ${Number(t.level_per_look).toFixed(4)} per look`
      : `closed (${humanize(t.decision)}): candidate ${t.counts.candidate[0]}/${t.counts.candidate[1]}, incumbent ${t.counts.incumbent[0]}/${t.counts.incumbent[1]}, ${plural(t.looks, 'look')}`,
    source: t.source, utc: t.opened_utc }];
  el.append(h('div.row.mt-8.wrap', g.tick ? h('span.badge.good', g.active ? '✓ active' : '✓ won its trial') : h('span.badge', STATE_SHORT[g.state] || g.state)),
    whatSection(`A frozen copy of Runesmith's organs, ${ORIGIN_WORDS[g.origin] || 'of a kind the map could not read'}. A new generation is never an edit of an old one.`),
    evidenceSection([{ label: 'State', value: g.state_words, source: g.source },
      { label: 'Parent', value: g.parent ? `${nameOf(g.parent)} (${g.parent})` : 'none: a root', source: `generations/${g.id}/MANIFEST.json` },
      { label: 'Organ digest', value: (g.organ_digest || '').slice(0, 26) + '…', source: `generations/${g.id}/MANIFEST.json` },
      { label: 'Created', value: when(g.created_utc), source: 'the manifest (frozen time)', utc: g.created_utc },
      { label: 'Author model', value: g.author_model || (g.origin === 'kaizen' ? 'unknown: the campaign record does not name it' : 'not applicable'), source: g.author_model ? `kaizen/${g.campaign}/KAIZEN_RESULT.json` : 'the manifest and the campaign record (no author named)' },
      { label: 'Campaign and target', value: g.campaign ? `${g.campaign}${g.target ? ` · target: ${humanize(g.target)}` : ''}` : 'none', source: 'the manifest and the campaign record' },
      g.validation != null ? { label: 'Validation', value: `${g.validation} repaired, against ${g.incumbent_validation ?? 'unknown'} for the incumbent`, source: 'the manifest (held-out replay at freezing)' } : null,
      ...trialRows,
      g.activated_utc ? { label: 'Made active', value: when(g.activated_utc), source: 'ledger: generation.activated', utc: g.activated_utc } : null].filter(Boolean)),
    await automateSection(ctx, [{ id: 'activate', gid: g.id, name: g.name, active: g.active },
      ...(g.state === 'on_trial' ? [{ id: 'stop_trial', incumbent: t.incumbent, incumbentName: nameOf(t.incumbent), candidateName: g.name }] : [])]));
  return el;
}

export default async function selfLens(body, ctx) {
  const offs = [];
  const data = await get('/api/map/self');
  const wrap = h('div.map-wrap');
  let selected = null, current = null, token = 0;
  let mode = window.matchMedia?.('(max-width: 560px)').matches ? 'list' : 'graph';
  const kernel = data.kernel, organs = data.active_organs;
  const { stations, ordered } = stationsOf(data);
  const shown = stations.length > CAP ? stations.slice(stations.length - CAP) : stations;
  const hidden = stations.length - shown.length;
  const problem = (data.living_problems || []).find((p) => p.startsWith('the lineage')) || (ordered ? null : 'the lineage of generations could not be ordered');
  const nameOf = (id) => stations.find((x) => x.id === id)?.name || id;

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
    s += `<g class="node${selected === '__self' ? ' sel' : ''}" data-kind="self" data-name="__self"><circle r="118" fill="var(--bg-1)" stroke="var(--line-2)"/><title>Runesmith itself: its self-knowledge</title></g>`;
    const m = organs.length || 1;
    organs.forEach((o, i) => {
      const a = (i / m) * Math.PI * 2 - Math.PI / 2;
      const x = Math.cos(a) * 64, y = Math.sin(a) * 64;
      s += `<g class="node${selected === o.path ? ' sel' : ''}" data-kind="organ" data-name="${esc(o.path)}" data-note="organ|${esc(o.path)}" data-note-label="organ ${esc(o.path)}" transform="translate(${m === 1 ? 0 : x},${m === 1 ? -20 : y})"><circle r="${m === 1 ? 46 : 30}" fill="url(#core)"/><text text-anchor="middle" y="4" font-size="12" font-weight="700" fill="#0b0e14">${esc(o.path.replace('.py', ''))}</text><title>organ ${esc(o.path)} · ${o.lines} lines</title></g>`;
    });
    const gen = data.identity.active_generation || '';
    s += `<text text-anchor="middle" y="${m === 1 ? 50 : 104}" class="svg-muted" font-size="11.5">active generation</text><text text-anchor="middle" y="${m === 1 ? 68 : 120}" class="svg-text" font-size="13" font-weight="700">${esc(nameOf(gen))}</text>`;
    s += `<text x="0" y="${-R2 - 44}" text-anchor="middle" class="svg-faint" font-size="12" letter-spacing="3">KERNEL · FIXED · ${N} MODULES</text>`;
    s += `<text x="0" y="${R2 + 58}" text-anchor="middle" class="svg-faint" font-size="12" letter-spacing="3">ORGANS · LIVING · REWRITTEN ONLY WITH EVIDENCE</text>`;
    // the lineage along the left, parent before child: a child sits one step in from its parent
    const pos = new Map();
    shown.forEach((g, i) => { pos.set(g.id, { x: -500 + Math.min(3, g.depth) * 18, y: -190 + i * 58 + (hidden ? 38 : 0) }); });
    if (hidden) s += `<g class="node${selected === '__earlier' ? ' sel' : ''}" data-kind="earlier" data-name="__earlier" transform="translate(-500,-190)" tabindex="0" role="button" aria-label="${esc(`${hidden} earlier generations, not drawn`)}"><rect x="-16" y="-16" width="130" height="32" fill="transparent"/><circle r="12" fill="var(--bg-2)" stroke="var(--line-2)" stroke-dasharray="3 3"/><text x="24" y="4" class="svg-muted" font-size="11.5">+${hidden} earlier</text><title>${esc(`${hidden} earlier generations`)}</title></g>`;
    shown.forEach((g) => {
      const p = pos.get(g.id), parent = pos.get(g.parent);
      if (parent) s += `<path d="M${parent.x} ${parent.y + 14} C ${parent.x} ${p.y - 24} ${p.x} ${parent.y + 24} ${p.x} ${p.y - 14}" fill="none" stroke="var(--line-2)" stroke-width="2"/>`;
    });
    shown.forEach((g) => {
      const p = pos.get(g.id);
      const fill = g.active ? '#ff8a3d' : g.state === 'on_trial' ? 'var(--bg-3)' : 'var(--bg-3)';
      const stroke = g.active ? '#f8dc94' : g.state === 'on_trial' ? 'var(--violet)' : g.state === 'rejected' || g.state === 'rolled_back' ? 'var(--bad)' : g.tick ? 'var(--good)' : 'var(--line-2)';
      const glyph = g.state === 'rejected' ? '✕' : g.state === 'rolled_back' ? '↩' : g.state === 'on_trial' ? '…' : g.state === 'imported' ? '↓' : '';
      const trial = g.trial && g.trial.state === 'open' ? ` · ${g.trial.counts.candidate[0]}/${g.trial.counts.candidate[1]} vs ${g.trial.counts.incumbent[0]}/${g.trial.counts.incumbent[1]}` : '';
      s += `<g class="node lm-station${selected === g.id ? ' sel' : ''}" data-kind="generation" data-name="${esc(g.id)}" data-note="generation|${esc(g.id)}" data-note-label="${esc(g.id)}" transform="translate(${p.x},${p.y})"
        aria-label="${esc(`${g.name}: ${STATE_SHORT[g.state] || g.state}. ${g.state_words}`)}"><rect x="-18" y="-20" width="230" height="40" fill="transparent"/>${g.state === 'on_trial' ? '<circle class="lm-pulse" r="19" fill="none" stroke="var(--violet)" stroke-width="4"/>' : ''}
        <circle r="14" fill="${fill}" stroke="${stroke}" stroke-width="2.4" ${g.state === 'frozen' || g.state === 'superseded' || g.state === 'trial_stopped' ? 'stroke-dasharray="3 3"' : ''}/>
        ${g.tick ? '<path class="lm-tick" d="M-5 0 L-1.5 3.5 L5 -3.5" stroke-width="2.4" fill="none" stroke-linecap="round"/>' : `<text text-anchor="middle" y="4" class="svg-text" font-size="12">${glyph}</text>`}
        <text x="26" y="-3" class="svg-text" font-size="12" font-weight="650">${esc(trunc(g.name, 22))}</text>
        <text x="26" y="12" class="lm-gen-state" font-size="10.5">${esc(trunc((STATE_SHORT[g.state] || g.state) + trial, 34))}</text><title>${esc(`${g.name}: ${g.state_words}`)}</title></g>`;
    });
    s += `<text x="-514" y="-224" class="svg-faint" font-size="11" letter-spacing="2">LINEAGE · PARENT TO CHILD</text>`;
    s += `</g></svg>`;
    const holder = h('div', { html: s });
    const svg = holder.firstChild;
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', `Runesmith's anatomy: ${N} kernel modules, ${organs.length} organ${organs.length === 1 ? '' : 's'} and ${stations.length} generation${stations.length === 1 ? '' : 's'}. Tab to a part and press Enter for its details, or use the list view.`);
    const pz = panZoom(svg, svg.querySelector('.pz'));
    svg.addEventListener('click', (e) => { const n = e.target.closest('.node'); if (n) open(n.dataset.kind, n.dataset.name, false); });
    keyboardNodes(svg, (n) => open(n.dataset.kind, n.dataset.name, true));
    const toggle = h('div.seg.lm-mode', { role: 'group', 'aria-label': 'How to show the parts' }, [['graph', 'Graph', 'branch'], ['list', 'List', 'menu']].map(([id, label, ic]) => h('button', { class: mode === id ? 'on' : '',
      'aria-pressed': String(mode === id), onclick: () => { mode = id; draw(); } }, icon(ic), label)));
    wrap.append(...[h('div.map-tools.lm-tools', ...[mode === 'graph' ? h('button.btn.sm.icon', { 'aria-label': 'Zoom in', title: 'Zoom in', onclick: () => pz.zoom(1.2) }, icon('plus')) : null,
      mode === 'graph' ? h('button.btn.sm.icon', { 'aria-label': 'Zoom out', title: 'Zoom out', onclick: () => pz.zoom(1 / 1.2) }, icon('minus')) : null,
      mode === 'graph' ? h('button.btn.sm.icon', { 'aria-label': 'Reset the view', title: 'Reset view', onclick: () => pz.reset() }, icon('crosshair')) : null,
      toggle, h('span.badge.rune', `Runesmith ${data.identity.version}`)].filter(Boolean)), mode === 'graph' ? svg : listView(),
      h('div.map-legend.lm-legend', h('span', h('b', { style: { color: 'var(--rune)' } }, '■'), ' kernel module (fixed)'), h('span', h('b', { style: { color: 'var(--ember)' } }, '●'), ' organ (can be improved)'),
        h('span.faint', '✓ only on the active generation or one that won its trial · click any part')),
      problem ? h('div.lm-notice.small', { role: 'status' }, icon('info'), `${problem}: the generations are listed as found, with no state claimed.`) : null, current].filter(Boolean));
  };
  // the same parts as a list, for the keyboard, a screen reader and a phone
  const listView = () => {
    const row = (kind, name, ...cells) => h('li', h('button.lm-row', { type: 'button', 'data-name': name, 'data-kind': kind, class: selected === name ? 'sel' : '', onclick: () => open(kind, name, true) }, ...cells));
    const metricsRows = Object.entries(CAP_NAMES).map(([k, label]) => {
      const c = data.capabilities[k] || { band: 'unknown', value: null }, m = metrics?.metrics?.[k];
      return row('metric', k, h('span.lm-name', label), h('span', { class: `band ${c.band}` }, c.value == null ? 'unknown' : fmtCap(k, c.value)), h('span.tiny.faint', m ? `${m.n} judged session${m.n === 1 ? '' : 's'}${m.few ? ' · few sessions' : ''}` : 'sample unknown'));
    });
    return h('div.lm-listbox', { role: 'group', 'aria-label': 'List view: the generations, organs, metrics and kernel modules' },
      h('details.lm-group', { open: true }, h('summary', h('b', 'Generations'), ` · ${plural(stations.length, 'generation')}, parent to child`),
        h('ul.lm-rows', { role: 'list' }, stations.map((g) => row('generation', g.id, h('span.lm-kind', g.tick ? '✓ ' + (STATE_SHORT[g.state] || g.state) : STATE_SHORT[g.state] || g.state),
          h('span.lm-name', { style: { paddingLeft: `${Math.min(3, g.depth) * 14}px` } }, g.name), h('span.tiny.faint', g.state_words.slice(0, 90)))))),
      h('details.lm-group', { open: true }, h('summary', h('b', 'Organs'), ` · ${plural(organs.length, 'organ')}, improvable only with evidence`),
        h('ul.lm-rows', { role: 'list' }, organs.map((o) => row('organ', o.path, h('span.lm-name.mono', o.path), h('span.tiny.faint', `${o.lines} lines`))))),
      h('details.lm-group', { open: true }, h('summary', h('b', 'Self-knowledge'), ' · what Runesmith knows about its own repairs'), h('ul.lm-rows', { role: 'list' }, metricsRows)),
      h('details.lm-group', h('summary', h('b', 'Kernel'), ` · ${plural(kernel.length, 'fixed module')}`),
        h('ul.lm-rows', { role: 'list' }, kernel.map((c) => row('kernel', c.path, h('span.lm-name.mono', c.path), h('span.tiny.faint', `${c.lines || '?'} lines`))))));
  };

  const close = () => { selected = null; token++; defaultPanel().then((el) => { current = el; draw(); }); };
  const open = async (kind, name, focus) => {
    const mine = ++token;
    selected = name;
    let el;
    try { el = await build(kind, name); } catch (error) { toast(error.message || String(error), 'warn'); return; }
    if (mine !== token) return;
    current = el;
    draw();
    if (focus) focusHeading(current);
  };

  // ---- the panels
  const build = async (kind, name) => {
    if (kind === 'kernel') return kernelPanel(kernel.find((k) => k.path === name) || { path: name });
    if (kind === 'organ') return organPanel(organs.find((o) => o.path === name) || { path: name }, data.organs.find((o) => o.path === name || o.path.endsWith(name)) || {});
    if (kind === 'generation') return generationPanelHere(stations.find((g) => g.id === name));
    if (kind === 'earlier') return earlierPanel();
    if (kind === 'metric') return metricPanel(name);
    return defaultPanel();
  };
  const sourceTree = 'the Runesmith source this Studio is running';
  const kernelPanel = async (c) => {
    const el = lmPanel({ eyebrow: 'Kernel module · fixed', title: c.path, onClose: close, note: ['component', c.path, c.path] });
    el.append(whatSection(`${c.purpose || 'A fixed module of the kernel.'} The kernel is the fixed part that owns identity, budgets, the ledger and promotion.`),
      evidenceSection([{ label: 'Module', value: c.path, source: sourceTree },
        { label: 'Lines', value: c.lines, source: sourceTree },
        { label: 'Public parts', items: (c.public_symbols || []).slice(0, 30), value: (c.public_symbols || []).length ? null : 'none listed', source: sourceTree + ', by reading the module' },
        { label: 'Kernel digest of the running build', value: (data.identity.kernel_digest || '').slice(0, 26) + '…', source: `Runesmith ${data.identity.version}, computed from its own files` }]),
      noAutomation('The kernel is not self-modifiable; it changes only with a Runesmith release, so no improvement loop can rewrite its own judge.',
        'updates: a new release of Runesmith. Nothing on this map, and no setting, changes a kernel module.'));
    return el;
  };
  const organPanel = async (o, full) => {
    const el = lmPanel({ eyebrow: 'Organ · improvable', title: o.path, onClose: close, note: ['organ', o.path, `organ ${o.path}`] });
    const active = stations.find((g) => g.active);
    el.append(whatSection(`${full.purpose || 'A part of Runesmith that can be rewritten.'} An organ changes only with evidence: a self-improvement campaign, a held-out replay and a trial on your work.`),
      evidenceSection([{ label: 'Organ file', value: `${o.path}, ${o.lines} lines`, source: `the active generation's organs/ folder${active ? ` (${active.name})` : ''}` },
        { label: 'Active generation', value: active ? `${active.name} (${active.id})` : data.identity.active_generation || 'unknown', source: 'the ACTIVE pointer and its manifest' },
        { label: 'Public parts', items: (full.public_symbols || []).slice(0, 30), value: (full.public_symbols || []).length ? null : 'none listed', source: sourceTree },
        { label: 'Unused kernel affordances', value: (data.improvement_options?.[o.path.replace('.py', '')]?.unused_affordances || []).join(', ') || 'none found', source: 'a static read of the organ' }]),
      await automateSection(ctx, ['kaizen', 'self_improvement_share', 'kaizen_every', 'min_experience', 'adopt']));
    return el;
  };
  const generationPanelHere = async (g) => (g ? generationPanel(g, stations, ctx, close) : defaultPanel());
  const earlierPanel = async () => {
    const el = lmPanel({ eyebrow: 'Lineage', title: `${hidden} earlier generations`, onClose: close });
    el.append(whatSection('Older generations, parent before child, that are not drawn so the lineage stays readable.'),
      evidenceSection(stations.slice(0, hidden).map((g) => ({ label: g.name, value: `${STATE_SHORT[g.state] || g.state}: ${g.state_words}`, source: g.source }))));
    for (const g of stations.slice(0, hidden)) el.append(h('button.btn.sm.mt-8', { onclick: () => open('generation', g.id, true) }, g.name));
    el.append(noAutomation('This is a count of generations, not a part of its own.', 'each generation has its own panel above.'));
    return el;
  };
  const metrics = data.metrics;
  const metricPanel = async (key) => {
    const mrow = metrics?.metrics?.[key];
    const c = data.capabilities[key] || { band: 'unknown', value: null };
    const el = lmPanel({ eyebrow: 'Self-knowledge metric', title: CAP_NAMES[key] || key, onClose: close, note: ['capability', key, CAP_NAMES[key] || key] });
    el.append(whatSection(mrow ? `${CAP_NAMES[key]}: ${mrow.definition}.` : `${CAP_NAMES[key] || key}: a measure of Runesmith's own repairs.`),
      evidenceSection([
        { label: 'Value', value: c.value == null ? 'unknown' : `${fmtCap(key, c.value)} (${BAND_LABEL[c.band]})`, source: 'Runesmith\'s own session records, read by the self map' },
        mrow ? { label: 'Sample', value: `${mrow.n} judged session${mrow.n === 1 ? '' : 's'}${mrow.since ? ` since ${when(mrow.since)}` : ''}${mrow.few ? ' — few sessions: read it with care' : ''}`, source: mrow.source } : { label: 'Sample', value: 'unknown: the sample could not be read', source: 'sessions/' },
        ...(mrow?.arms ? Object.entries(mrow.arms).map(([arm, a]) => ({ label: `During the trial: ${arm}`, value: `${a.n} judged session${a.n === 1 ? '' : 's'}${a.few ? ' (few sessions)' : ''}; value ${a.value == null ? 'unknown' : fmtCap(key, a.value)}`, source: 'sessions marked with the trial arm, since the trial opened' })) : [])]),
      await automateSection(ctx, ['self_improvement_share', 'kaizen']));
    return el;
  };
  const defaultPanel = async () => {
    const el = h('div.map-side.lm-panel', { role: 'region', 'aria-label': 'Details: Runesmith itself' });
    el.append(h('div.row', h('div.grow', h('div.small.faint', 'Runesmith itself'), h('h3', { style: { margin: '2px 0 0' }, tabindex: '-1' }, 'Self-knowledge')),
      h('button.btn.sm', { onclick: () => openNotes('self', 'runesmith', 'Runesmith itself') }, icon('note'), 'Comment')),
      whatSection('What Runesmith knows about itself: how its own repairs have gone, with how many sessions that rests on. Nothing here is assumed; a number without evidence says unknown.'));
    const ev = section('Evidence');
    for (const [k, label] of Object.entries(CAP_NAMES)) {
      const c = data.capabilities[k] || { band: 'unknown', value: null };
      const mrow = metrics?.metrics?.[k];
      const row = h('div.gauge-row', { onclick: () => open('metric', k, true), 'aria-label': `${label}: ${c.value == null ? 'unknown' : fmtCap(k, c.value)}. Open its evidence.` }, h('span.small', label),
        h('div', { class: `bandbar${c.value == null ? ' unknown' : ''}` }, c.value != null ? h('span.mark', { style: { left: `${bandPosition(c)}%` } }) : null),
        h('span', { class: `band ${c.band}` }, c.value == null ? '?' : fmtCap(k, c.value)));
      commentable(row, 'capability', k, label);
      ev.append(row, h('div.tiny.faint.lm-src', mrow ? `${mrow.n} judged session${mrow.n === 1 ? '' : 's'}${mrow.since ? ` since ${hhmm(mrow.since)}` : ''}${mrow.few ? ' · few sessions' : ''}` : 'sample size unknown'));
    }
    ev.append(h('div.tiny.faint.lm-src.mt-8', `Source: ${metrics?.window || 'Runesmith\'s own session records'}; Runesmith ${data.identity.version}.`),
      h('div.divider'), h('div.label-text', 'What an organ may ask of the kernel'),
      h('div.col.gap-6.mt-8', Object.entries(data.affordances).map(([k, v]) => h('div.small', h('b.mono', k), h('span.muted', ` — ${v}`)))),
      h('div.divider'), h('div.label-text', 'Envelope per attempt'), kv(Object.entries(data.envelope).map(([k, v]) => [humanize(k), v])));
    if (data.open_targets?.length) ev.append(h('div.divider'), h('div.label-text', 'Where it struggles most (Kaizen targets)'),
      h('div.col.gap-6.mt-8', data.open_targets.map((t) => h('div.small', h('b', humanize(t.family || t.stage || t.kind || 'target')), h('span.muted', ` · share ${Math.round((t.share || 0) * 100)}%`)))));
    ev.append(h('div.divider'), h('div.label-text', 'Unknown'), h('ul.small.muted', { style: { paddingLeft: '18px' } }, data.unknowns.map((u) => h('li', u))));
    el.append(ev, await automateSection(ctx, ['kaizen', 'self_improvement_share']));
    return el;
  };
  body.append(wrap);
  current = await defaultPanel();
  draw();
  return () => offs.forEach((f) => f());
}
