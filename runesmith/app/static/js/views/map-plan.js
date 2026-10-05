// Development: your goals, the plan as a dependency graph, each object's ladder (from the latest recorded test run, with its
// source and time) and Runesmith's own generations in lineage order (docs/MAP_LOGIC.md, section 3).
import { h, icon, get, toast, commentable, clear, humanize, KIND, plural } from '../core.js';
import { esc, trunc, hhmm, when, panel as lmPanel, section, whatSection, evidenceSection, automateSection, noAutomation, focusHeading, keyboardNodes,
  withOverlay } from './map-parts.js';
import { generationPanel, STATE_SHORT } from './map-self.js';

const BOX_W = 172, BOX_H = 46, COL = 232, ROW = 62, LANE_HEAD = 30;
const STATE_LABEL = { done: 'done', ready: 'ready', waiting: 'waiting', doing: 'in progress', needs_you: 'needs you', dropped: 'dropped' };
const RUNG_WORDS = {
  source_present: 'The folder holds source files.', tests_present: 'The project has test files.', tests_collect: 'The test runner finds and counts the project’s tests.',
  tests_pass: 'Every test passes.', fast_suite: 'The whole test suite runs in 60 seconds or less.', coverage_measured: 'How much code the tests run has been measured (Runesmith does not measure this yet).',
  mutation_tested: 'The tests have been checked by changing the code (Runesmith does not do this yet).', package_manifest: 'A package.json describes the project.',
  test_script_declared: 'The package declares a test script.', lockfile_present: 'A lockfile pins the packages.', typecheck_declared: 'The package declares a type check.',
  documents_present: 'The folder holds documents.', index_present: 'There is an index page to start from.', links_resolve: 'Every internal link points at a file that exists.',
  pages_present: 'The site has pages.', styles_present: 'The site has stylesheets.', mobile_ready: 'Every page says it fits a phone.', titles_present: 'Every page has a title.',
  contents_present: 'The folder holds files.', readme_present: 'A readme says what the folder is.', version_control: 'The folder is under version control.', reports_present: 'The folder holds report files.',
};
const TEST_RUNGS = new Set(['tests_collect', 'tests_pass', 'fast_suite']);

export default async function developmentLens(body, ctx) {
  const offs = [];
  const data = await get('/api/map/development');
  const goals = (data.goals || []).filter((g) => g.status !== 'removed');
  const graph = data.graph && data.graph.nodes?.length ? data.graph : null;
  const problems = data.living_problems || [];
  const lineage = data.lineage_ordered?.stations || null;
  const planNote = !data.graph && problems.find((p) => p.startsWith('the plan graph'));
  const genNote = !lineage && problems.find((p) => p.startsWith('the lineage'));
  const nameOfGen = (id) => lineage?.find((g) => g.id === id)?.name || id;

  // ---------------------------------------------------------------------------- goals
  const goalsCard = h('div.card', h('div.card-head', h('h3', icon('target'), 'Operating toward'), h('div.actions', h('button.btn.sm', { onclick: () => ctx.navigate('goals') }, icon('plus'), 'Goals & plan'))),
    goals.length ? h('div.pillbox', goals.map((g) => { const c = h('span', { class: `chip${g.status === 'done' ? ' on' : ''}` }, icon(g.status === 'done' ? 'check' : 'target'), g.text); commentable(c, 'goal', g.id, g.text); c.querySelector('.note-btn').style.top = '-10px'; return c; }))
      : h('p.muted', 'No goals yet. Goals tell the planner and the map what matters to you.'));

  // ---------------------------------------------------------------------------- the plan graph
  const planCard = h('div.card', h('div.card-head', h('h3', icon('flag'), 'The plan'), graph ? h('span.badge', `${graph.counts.total} milestone${graph.counts.total === 1 ? '' : 's'}`) : null));
  let planSel = null, planMode = window.matchMedia?.('(max-width: 560px)').matches ? 'list' : 'graph', planPanel = null, planToken = 0;
  const openTracks = new Set();
  const planHost = h('div.lm-host');
  const drawPlan = () => {
    clear(planHost);
    if (!graph) {
      planHost.append(h('p.muted', planNote ? `${planNote}. The milestones are in Goals & plan.` : 'No plan yet. Draft one under Goals & plan, or add a milestone: its prerequisites become the edges of this graph.'));
      return;
    }
    const by = new Map(graph.nodes.map((n) => [n.id, n]));
    const shownIds = new Set(graph.nodes.filter((n) => n.drawn || openTracks.has(n.track)).map((n) => n.id));
    const tracks = graph.tracks.filter((t) => graph.nodes.some((n) => n.track === t.name && shownIds.has(n.id)) || t.more);
    const counts = Object.fromEntries(Object.keys(STATE_LABEL).map((k) => [k, graph.counts[k] || 0]));
    const summary = h('div.row.wrap.small', Object.entries(STATE_LABEL).filter(([k]) => counts[k]).map(([k, label]) => h('span', { class: `lm-state ${k}` }, h('i'), `${counts[k]} ${label}`)));
    const pick = (id) => { planSel = id; openPlanPanel(true); drawPlan(); };
    let content;
    if (planMode === 'graph') {
      // lanes: one per track; columns by how many prerequisites deep; the stack inside a cell follows the plan's order
      const lanes = []; let y = 0;
      const pos = new Map();
      for (const t of tracks) {
        const members = graph.nodes.filter((n) => n.track === t.name && shownIds.has(n.id));
        const stack = new Map();
        for (const n of members) { const k = n.level; stack.set(k, (stack.get(k) || 0) + 1); pos.set(n.id, { x: 24 + n.level * COL, row: stack.get(k) - 1 }); }
        const rows = Math.max(1, ...stack.values());
        const hgt = LANE_HEAD + rows * ROW + (t.more && !openTracks.has(t.name) ? 26 : 8);
        for (const n of members) { const p = pos.get(n.id); p.y = y + LANE_HEAD + p.row * ROW; }
        lanes.push({ t, y, hgt, members });
        y += hgt + 10;
      }
      const maxLevel = Math.max(0, ...[...shownIds].map((id) => by.get(id).level));
      const W = 24 + (maxLevel + 1) * COL + 40, H = y + 10;
      let s = `<svg class="lm-plan" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg" role="group"
        aria-label="${esc(`The plan: ${graph.counts.total} milestones in ${tracks.length} tracks, with their prerequisites as links. Tab to a milestone and press Enter for its details, or use the list view.`)}">
        <defs><marker id="lm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="var(--line-2)"/></marker></defs>`;
      for (const l of lanes) {
        s += `<rect class="lm-lane" x="6" y="${l.y}" width="${W - 12}" height="${l.hgt}" rx="12"/><text x="22" y="${l.y + 19}" class="svg-text" font-size="13" font-weight="680">${esc(trunc(l.t.name, 40))}</text>
          <text x="${22 + Math.min(300, 8 + l.t.name.length * 7.6)}" y="${l.y + 19}" class="svg-faint" font-size="11">${esc(plural(l.t.total, 'milestone'))}</text>`;
      }
      for (const e of graph.edges) {
        const a = pos.get(e.from), b = pos.get(e.to);
        if (!a || !b) continue;
        const x1 = a.x + BOX_W, y1 = a.y + BOX_H / 2, x2 = b.x, y2 = b.y + BOX_H / 2, mx = (x1 + x2) / 2;
        s += `<path class="lm-pedge${e.met ? '' : ' unmet'}" marker-end="url(#lm-arrow)" d="M${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2 - 2} ${y2}"><title>${esc(`${by.get(e.to).title} needs ${by.get(e.from).title} first (${e.met ? 'it is settled' : 'still open'})`)}</title></path>`;
      }
      for (const l of lanes) {
        for (const n of l.members) {
          const p = pos.get(n.id);
          const mark = n.state === 'done' ? '✓ ' : n.state === 'needs_you' ? '! ' : '';
          const sub = n.state === 'waiting' ? `waiting for ${plural(n.unmet.length, 'prerequisite')}` : n.state === 'needs_you' ? (n.needs[0]?.text || 'needs you') : STATE_LABEL[n.state];
          s += `<g class="node kb lm-ms ${n.state}${planSel === n.id ? ' sel' : ''}" data-name="${esc(n.id)}" data-note="milestone|${esc(n.id)}" data-note-label="${esc(n.title)}" transform="translate(${p.x},${p.y})" tabindex="0" role="button"
            aria-label="${esc(`${n.title}: ${STATE_LABEL[n.state]}${n.state === 'waiting' ? `, waiting for ${plural(n.unmet.length, 'prerequisite')}` : ''}${n.needs.length ? `. ${n.needs.map((x) => x.text).join('; ')}` : ''}`)}">
            <rect class="lm-box" width="${BOX_W}" height="${BOX_H}" rx="10"/>
            <text class="lm-title" x="10" y="19">${esc(mark + trunc(n.title, 24))}</text><text class="lm-sub" x="10" y="35">${esc(trunc(sub, 30))}</text>
            <title>${esc(`${n.title} — ${n.state_words}`)}</title></g>`;
        }
        const t = l.t;
        if (t.more && !openTracks.has(t.name)) s += `<g class="node kb lm-ms" data-name="more:${esc(t.name)}" transform="translate(24,${l.y + l.hgt - 24})" tabindex="0" role="button" aria-label="${esc(`${t.more} more milestones in ${t.name}, not drawn. Enter to show them.`)}"><rect x="-6" y="-4" width="180" height="22" fill="transparent"/><text class="lm-track-more" y="12">+${t.more} more (finished and later ones)</text></g>`;
      }
      s += '</svg>';
      const holder = h('div.lm-scroll', { html: s });
      const svg = holder.firstChild;
      svg.addEventListener('click', (e) => { const n = e.target.closest('.node'); if (!n) return; const name = n.dataset.name; if (name.startsWith('more:')) { openTracks.add(name.slice(5)); drawPlan(); } else pick(name); });
      keyboardNodes(svg, (n) => { const name = n.dataset.name; if (name.startsWith('more:')) { openTracks.add(name.slice(5)); drawPlan(); } else pick(name); });
      content = holder;
    } else {
      const list = h('div.lm-list', { role: 'group', 'aria-label': 'List view: every milestone with its state and what it needs' });
      for (const t of graph.tracks) {
        const members = graph.nodes.filter((n) => n.track === t.name);
        list.append(h('details.lm-group', { open: members.some((n) => n.state !== 'done' && n.state !== 'dropped') || planSel && members.some((n) => n.id === planSel) },
          h('summary', h('b', t.name), ` · ${plural(t.total, 'milestone')}`),
          h('ul.lm-rows', { role: 'list' }, members.map((n) => h('li', h('button.lm-row', { type: 'button', 'data-name': n.id, class: planSel === n.id ? 'sel' : '', onclick: () => pick(n.id),
            'aria-label': `${n.title}: ${STATE_LABEL[n.state]}${n.needs.length ? `. ${n.needs.map((x) => x.text).join('; ')}` : ''}` },
            h('span', { class: `lm-state ${n.state}` }, h('i'), STATE_LABEL[n.state]), h('span.lm-name', n.title),
            n.unmet.length ? h('span.tiny.faint', `needs ${n.unmet.map((k) => by.get(k)?.title || k).join(', ')}`) : null))))));
      }
      content = list;
    }
    const toggle = h('div.seg.lm-mode', { role: 'group', 'aria-label': 'How to show the plan' }, [['graph', 'Graph', 'branch'], ['list', 'List', 'menu']].map(([id, label, ic]) => h('button', { class: planMode === id ? 'on' : '',
      'aria-pressed': String(planMode === id), onclick: () => { planMode = id; drawPlan(); } }, icon(ic), label)));
    planHost.append(h('div.row.wrap.mt-8', toggle, summary), h('div.mt-8', content),
      h('p.tiny.faint.mt-8', `Plan version ${graph.plan.version ?? '?'}${graph.plan.drafted_by ? `, drafted by ${graph.plan.drafted_by}` : ''}, saved ${when(graph.plan.utc)}. An arrow means “needs this first”; dashed is still open.`),
      ...(graph.notes?.length ? [h('p.tiny.faint', `Could not read: ${graph.notes.join('; ')}. Those facts are shown as unknown.`)] : []));
    if (planPanel) planHost.append(planPanel);
  };
  const closePlan = () => { planSel = null; planPanel = null; planToken++; drawPlan(); };
  const openPlanPanel = async (focus) => {
    const mine = ++planToken;
    const n = graph.nodes.find((x) => x.id === planSel);
    if (!n) return;
    try {
      const el = await milestonePanel(n);
      if (mine !== planToken) return;
      planPanel = el; drawPlan();
      if (focus) focusHeading(planPanel);
    } catch (error) { toast(error.message || String(error), 'warn'); }
  };
  const milestonePanel = async (n) => {
    const el = lmPanel({ eyebrow: `Milestone · ${n.track}`, title: n.title, onClose: closePlan, note: ['milestone', n.id, n.title] });
    const tries = h('div.lm-fact', h('div.small.faint', 'Tries'), h('div.small', 'Reading the tries against the files as they are now…'), h('div.tiny.faint.lm-src', 'Source: the build attempts’ own records'));
    el.append(h('div.row.mt-8.wrap', h('span', { class: `lm-state ${n.state}` }, h('i'), n.state_words)),
      whatSection(`One step of the plan. It counts as done when: ${n.done_when || 'nothing is written yet'}.`));
    const ev = evidenceSection(n.evidence);
    if (n.status === 'open' || n.status === 'doing') ev.append(tries);
    el.append(ev);
    const open = n.status === 'open' || n.status === 'doing';
    if (open) {
      el.append(await automateSection(ctx, [{ id: 'propose_checks', mid: n.id, hasChecks: n.checks.approved, ready: true }, 'checks_autopilot', 'stuck_policy', 'recheck_policy', 'build_steps', 'build_apply',
        { id: 'link', label: 'Edit or review it in Goals & plan', now: 'Wording, prerequisites, drafts and checks live there.', effect: 'The page that already holds the milestone’s own controls.', button: 'Open Goals & plan', go: ['goals'] }]));
      get(`/api/map/milestone/${encodeURIComponent(n.id)}`).then((t) => {
        const row = tries.querySelector('.small:not(.faint)');
        row.textContent = t.known ? `${t.used} of ${t.limit} used${t.one_more_try_used ? ', and its one more try' : ''}; ${t.remaining} left, counted against the files as they are now` : `unknown: ${t.reason}`;
      }).catch((error) => { tries.querySelector('.small:not(.faint)').textContent = `unknown: ${error.message || error}`; });
    } else {
      el.append(noAutomation(`A ${n.state === 'done' ? 'finished' : 'dropped'} milestone is recorded history: its checks, drafts and ledger entries are not changed from here.`,
        'the plan in Goals & plan, where you can reopen it.', [{ label: 'Open Goals & plan', go: () => ctx.navigate('goals') }]));
    }
    return el;
  };
  planCard.append(planHost);

  // ---------------------------------------------------------------------------- the tracks
  const lanes = [];
  if (!graph && data.plan?.milestones?.length) {                  // the plan graph could not be built: the plan as flat tracks, as before
    const byTrack = new Map();
    for (const m of data.plan.milestones) { const t = m.track || 'Plan'; if (!byTrack.has(t)) byTrack.set(t, []); byTrack.get(t).push(m); }
    for (const [t, ms] of byTrack) lanes.push({ kind: 'plan', label: t, sub: 'plan track', stations: ms.map((m) => ({ id: m.id, label: m.title, status: m.status === 'done' ? 'achieved' : m.status === 'doing' ? 'doing' : m.status === 'dropped' ? 'dropped' : 'open', note: ['milestone', m.id, m.title] })) });
  }
  for (const raw of data.objects || []) {
    const o = withOverlay(raw, data.ladders);
    if (!o.ladder?.length) continue;
    lanes.push({ kind: 'object', label: o.name, sub: KIND[o.kind]?.label || o.kind, object: o, stations: o.ladder.map((r) => ({ id: r.rung, label: humanize(r.rung), status: r.status, next: o.next_rung === r.rung,
      note: ['rung', `${o.name}/${r.rung}`, `${o.name}: ${humanize(r.rung)}`], rung: r, sub: r.evidence?.utc ? `${hhmm(r.evidence.utc)} · ${r.evidence.source === 'probe' ? 'map probe' : r.evidence.source === 'measure' ? 'measuring round' : 'repair round'}` : '',
      title: r.evidence?.note || null })) });
  }
  if (lineage?.length) lanes.push({ kind: 'self', label: 'Runesmith itself', sub: 'generations, parent to child', stations: lineage.map((g) => ({ id: g.id, label: g.name, status: g.state, tick: g.tick, sub: STATE_SHORT[g.state] || g.state,
    note: ['generation', g.id, g.id], title: g.state_words, gen: g })) });
  else if (data.lineage?.length) lanes.push({ kind: 'self', label: 'Runesmith itself', sub: 'generations (order not read)', stations: data.lineage.map((g) => ({ id: g.id, label: g.id.replace('gen-', ''), status: 'unknown', tick: !!g.active, sub: 'state not read',
    note: ['generation', g.id, g.id], title: g.label })) });
  const laneW = 210, stepW = 158, rowH = 100;
  const maxStations = Math.max(3, ...lanes.map((l) => l.stations.length));
  const W = laneW + maxStations * stepW + 60, H = Math.max(1, lanes.length) * rowH + 30;
  let trackSel = null, trackPanel = null, trackToken = 0;
  const trackHost = h('div.lm-host');
  const drawTracks = () => {
    clear(trackHost);
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg" style="display:block">`;
    lanes.forEach((lane, i) => {
      const y = 30 + i * rowH + 26;
      const color = lane.kind === 'self' ? 'var(--rune)' : lane.kind === 'plan' ? 'var(--violet)' : 'var(--ember)';
      s += `<rect x="8" y="${y - 32}" width="${W - 16}" height="${rowH - 12}" rx="14" fill="var(--bg-1)" stroke="var(--line)"/>`;
      s += `<text x="26" y="${y - 4}" class="svg-text" font-size="14" font-weight="680">${esc(trunc(lane.label, 22))}</text><text x="26" y="${y + 14}" class="svg-faint" font-size="11">${esc(trunc(lane.sub, 28))}</text>`;
      const x0 = laneW, x1 = laneW + (lane.stations.length - 1) * stepW;
      s += `<path d="M${x0} ${y} L${x1} ${y}" stroke="var(--line-2)" stroke-width="4" stroke-linecap="round"/>`;
      if (lane.kind !== 'self') {
        const lastDone = lane.stations.reduce((m, st, j) => (st.status === 'achieved' ? j : m), -1);
        if (lastDone > 0) s += `<path d="M${x0} ${y} L${laneW + lastDone * stepW} ${y}" stroke="${color}" stroke-width="4" stroke-linecap="round"/>`;
      }
      lane.stations.forEach((st, j) => {
        const x = laneW + j * stepW;
        const on = st.status === 'achieved' || st.tick;
        const fill = st.tick && st.gen?.active ? '#ff8a3d' : on ? color : 'var(--bg-2)';
        const stroke = st.status === 'unknown' ? 'var(--text-3)' : st.status === 'not_achieved' ? '#e8b04a' : st.status === 'dropped' ? 'var(--line-2)' : st.status === 'on_trial' ? 'var(--violet)'
          : st.status === 'rejected' || st.status === 'rolled_back' ? 'var(--bad)' : color;
        const pulse = st.next || st.status === 'doing' || st.status === 'on_trial';
        s += `<g class="node lm-station${trackSel === `${i}:${j}` ? ' sel' : ''}" data-lane="${i}" data-st="${j}" data-name="${i}:${j}" transform="translate(${x},${y})" aria-label="${esc(`${lane.label}: ${st.label}, ${st.status === 'achieved' ? 'achieved' : humanize(st.status)}${st.sub ? `. ${st.sub}` : ''}`)}">
          <rect x="-28" y="-26" width="${stepW - 20}" height="${68}" fill="transparent"/>
          ${pulse ? `<circle class="lm-pulse" r="17" fill="none" stroke="${color}" stroke-width="4"/>` : ''}
          <circle r="10" fill="${fill}" stroke="${stroke}" stroke-width="2.5" ${st.status === 'unknown' || st.status === 'frozen' || st.status === 'superseded' ? 'stroke-dasharray="3 3"' : ''}/>
          ${on ? '<path class="lm-tick" d="M-4 0 L-1 3 L4 -3" stroke-width="2" fill="none" stroke-linecap="round"/>' : ''}
          <text y="28" text-anchor="middle" class="${st.status === 'dropped' ? 'svg-faint' : 'svg-muted'}" font-size="11" ${st.status === 'dropped' ? 'text-decoration="line-through"' : ''}>${esc(trunc(st.label, 22))}</text>
          ${st.sub ? `<text y="41" text-anchor="middle" class="lm-gen-state" font-size="9.5">${esc(trunc(st.sub, 26))}</text>` : ''}
          <title>${esc(`${st.label} — ${st.status === 'achieved' ? 'achieved' : humanize(st.status)}${st.title ? ` — ${st.title}` : ''}`)}</title></g>`;
      });
    });
    if (!lanes.length) s += `<text x="${W / 2}" y="60" text-anchor="middle" class="svg-muted" font-size="14">No tracks yet: map the folder, set goals, or draft a plan.</text>`;
    s += '</svg>';
    const holder = h('div.lm-scroll', { html: s });
    const station = (n) => lanes[+n.dataset.lane].stations[+n.dataset.st];
    const pick = (n, focus) => { trackSel = n.dataset.name; openTrackPanel(lanes[+n.dataset.lane], station(n), focus); };
    if (holder.firstChild) {
      holder.firstChild.setAttribute('role', 'group');
      holder.firstChild.setAttribute('aria-label', `${lanes.length} development track${lanes.length === 1 ? '' : 's'}. Tab to a station and press Enter for its details.`);
      holder.firstChild.addEventListener('click', (e) => { const n = e.target.closest('.node'); if (n) pick(n, false); });
      keyboardNodes(holder.firstChild, (n) => pick(n, true));
    }
    trackHost.append(holder);
    if (trackPanel) trackHost.append(trackPanel);
  };
  const closeTrack = () => { trackSel = null; trackPanel = null; trackToken++; drawTracks(); };
  const openTrackPanel = async (lane, st, focus) => {
    const mine = ++trackToken;
    let el;
    try {
      if (st.gen) el = await generationPanel(st.gen, lineage, ctx, closeTrack);
      else if (lane.kind === 'object') el = await rungPanel(lane, st);
      else el = await legacyStationPanel(lane, st);
    } catch (error) { toast(error.message || String(error), 'warn'); return; }
    if (mine !== trackToken) return;
    trackPanel = el; drawTracks();
    if (focus) focusHeading(trackPanel);
  };
  const legacyStationPanel = async (lane, st) => {
    const el = lmPanel({ eyebrow: lane.sub, title: st.label, onClose: closeTrack, note: st.note });
    el.append(whatSection(`${lane.label}: ${st.label}.`), evidenceSection([{ label: 'Status', value: humanize(st.status), source: 'the map, as read now' }]),
      noAutomation('This part could not be read in full, so nothing is offered for it here.', 'Goals & plan, where the plan itself is kept.', [{ label: 'Open Goals & plan', go: () => ctx.navigate('goals') }]));
    return el;
  };
  const rungPanel = async (lane, st) => {
    const o = lane.object, r = st.rung;
    const el = lmPanel({ eyebrow: `${lane.sub} · ${lane.label}`, title: humanize(r.rung), onClose: closeTrack, note: st.note });
    const ev = r.evidence;
    const rows = [{ label: 'Status', value: r.status === 'achieved' ? 'achieved' : r.status === 'not_achieved' ? 'not achieved yet' : 'unknown', source: ev ? ev.source_words : 'the map of this folder' , utc: ev?.utc }];
    if (ev) rows.push({ label: 'Why', value: ev.note, source: ev.source_words, utc: ev.utc });
    else rows.push({ label: 'Why', value: TEST_RUNGS.has(r.rung) ? 'No test run is recorded that settles this rung, so it stays as the map found it.' : 'Read from the files on disk when the folder was mapped.', source: data.mapped_utc ? `the map written ${when(data.mapped_utc)}` : 'the map of this folder' });
    if (o.measured_utc && TEST_RUNGS.has(r.rung)) rows.push({ label: 'The map’s own probe', value: `measured ${when(o.measured_utc)}`, source: 'ENVIRONMENT.json', utc: o.measured_utc });
    el.append(h('div.row.mt-8.wrap', h('span', { class: `rung ${r.status}` }, h('span.pip'), humanize(r.status === 'achieved' ? 'achieved' : r.status))), whatSection(RUNG_WORDS[r.rung] || `A step on the ${lane.sub.toLowerCase()} ladder.`), evidenceSection(rows));
    if (TEST_RUNGS.has(r.rung)) el.append(await automateSection(ctx, ['watch_tests', { id: 'fix_tests', object: o.name }, 'remap']));
    else el.append(noAutomation('This rung is read from the files on disk (or is not measured yet), so there is nothing to switch on for it.', 'the folder itself: change the files and map again.',
      [{ label: 'Open the Environment', go: () => ctx.navigate('map', 'environment') }]));
    return el;
  };
  const tracks = h('div.card', h('div.card-head', h('h3', icon('route'), 'Development tracks'), h('span.badge', 'click a station for its evidence')), trackHost,
    h('div.row.mt-8.small.faint.wrap', h('span', { class: 'band optimal' }, 'achieved'), h('span', { class: 'band minimal' }, 'not yet'), h('span', { class: 'band unknown' }, 'unknown'),
      h('span', '· a ring marks what is next, or a trial in progress · a tick only where a rung is achieved, or a generation is active or won its trial')),
    genNote ? h('p.tiny.faint.mt-8', `${genNote}: the generations are listed as found, with no state claimed.`) : null);
  drawPlan();
  drawTracks();

  const camp = h('div.card', h('div.card-head', h('h3', icon('spark'), 'Self-improvement campaigns')),
    data.campaigns.length ? h('div.list', data.campaigns.slice().reverse().map((c) => h('div.item', h('div', { class: `ico ${c.decision === 'candidate' ? 'good' : ''}` }, icon('beaker')),
      h('div.body', h('div.title', `${humanize(c.decision)} · target: ${humanize(c.target || '?')}`), h('div.meta', `${c.campaign} · ${c.attempts.length} attempt(s) · validation ${c.best ?? '—'} vs baseline ${c.baseline ?? '—'}`)))))
      : h('p.muted', 'None yet. Runesmith starts one when it has enough of its own experience (Settings → Self-improvement).'));
  body.append(goalsCard, h('div.mt-16'), planCard, h('div.mt-16'), tracks, h('div.mt-16'), camp);
  return () => offs.forEach((f) => f());
}
