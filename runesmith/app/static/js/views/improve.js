// Self-improvement: generations, the online trial, the library of proven generations, campaigns, capabilities.
import { h, icon, get, post, bus, toast, commentable, openNotes, clear, ago, plural, humanize, withBusy, confirmDialog,
  empty, debounce } from '../core.js';
import { bandPosition, fmtCap } from './home.js';

// Runesmith's plan for improving itself: the summary of its map, the owner's share, the scored plan (the top ten), the next item
// and why (and the struggle it is linked to), and the struggles it sees in the work. Nothing here changes Runesmith itself: an item
// without a gate is only planned.
function selfPlanCard(plan, navigate) {
  if (!plan) return null;
  const map = plan.map || {};
  const struggles = plan.struggles || [];
  const next = plan.next || null;
  const turnWords = plan.next_self_turn_in === 1 ? 'the very next work turn' : `${plan.next_self_turn_in} work turns from now`;
  const bandWords = Object.entries(map.bands || {}).map(([k, v]) => `${humanize(k)}: ${v}`).join(' · ');
  const statusClass = (status) => String(status || '').startsWith('campaign') || String(status || '').startsWith('a campaign') ? 'good'
    : String(status || '').startsWith('planned') ? 'violet' : String(status || '').startsWith('waits') ? 'warn' : '';
  const item = (x, i) => h('div.item', { 'data-item': x.id },
    h('div', { class: `ico ${x.kind === 'kaizen_target' ? 'accent' : 'warn'}` }, icon(x.kind === 'kaizen_target' ? 'spark' : 'crosshair')),
    h('div.body', h('div.title', `${i + 1}. ${x.title} `, h('span.badge', { title: `benefit ${x.score.benefit} + recency ${x.score.recency} + gate ${x.score.gate}` }, `score ${x.score.total}`), ' ',
      h('span', { class: `badge ${statusClass(x.status)}` }, x.status || ''), x.priority ? ' ' : null, x.priority ? h('span.badge.warn', 'answers a struggle') : null),
      h('div.small.muted', x.reason), h('div.tiny.faint', x.what)));
  const struggle = (x) => h('div.item', { 'data-struggle': x.id },
    h('div', { class: `ico ${x.current ? 'warn' : ''}` }, icon('alert')),
    h('div.body', h('div.title', `${x.milestone_title ? `“${x.milestone_title}”` : x.scope === 'repairs' ? 'The repair organ' : 'The project'}: ${x.words}`,
      ' ', x.current ? h('span.badge.warn', 'struggling now') : null, x.id === (next && next.struggle) ? h('span.badge.violet', 'the next item answers this') : null),
      h('div.meta', `${plural(x.count, 'time')}${x.since ? ` since ${String(x.since).slice(0, 16).replace('T', ' ')}Z` : ''}`)));
  const rule = plan.rule || {};
  return h('section.card', { 'aria-label': 'Improvement plan', 'data-self-plan': '' },
    h('div.card-head', h('h3', icon('target'), 'Improvement plan'),
      h('div.actions', h('span', { class: `badge ${plan.kaizen_on ? 'good' : ''}` }, plan.kaizen_on ? 'self-improvement on' : 'self-improvement off'),
        h('button.btn.sm', { onclick: () => navigate('settings') }, icon('sliders'), 'Share'))),
    h('p.small', `Its map of itself: ${plural(map.components || 0, 'component')}, ${plural(map.targets || 0, 'repair target')} from its own records, `
      + `${plural(map.struggles || 0, 'struggle')} seen in the work (${map.current_struggles || 0} now).${bandWords ? ` ${bandWords}.` : ''}`),
    h('p.small', { 'data-share': '' }, `Self-improvement share: ${plan.share}%. ${plan.sentence}. The next self-improvement turn is ${turnWords}.`,
      plan.kaizen_on ? null : ' Self-improvement is off in Settings, so none will run.'),
    next ? h('div.callout.mt-8', { 'data-next': '' }, icon('info'), h('div', h('b', next.action === 'none' ? 'Nothing can run at the next self-improvement turn. ' : `Next: ${next.title}. `),
      next.why)) : null,
    (plan.blockers || []).length ? h('p.tiny.faint.mt-8', `A campaign on the repair organ cannot start now: ${plan.blockers.join('; ')}.`) : null,
    h('div.label-text.mt-16', 'The plan, first item first'),
    (plan.items || []).length ? h('div.list', (plan.items || []).map(item)) : h('p.muted', 'No item yet: the plan fills as Runesmith sees where it can do better.'),
    struggles.length ? h('div.label-text.mt-16', 'Where the work struggles') : null,
    struggles.length ? h('div.list', struggles.map(struggle)) : null,
    h('details.mt-16', h('summary', 'How the score is worked out'),
      h('ul.small', ['score', 'benefit', 'recency', 'gate', 'turns', 'priority'].filter((k) => rule[k]).map((k) => h('li', h('b', `${humanize(k)}: `), rule[k]))),
      h('p.small.muted', 'A change to Runesmith is only ever made through a gate: a campaign on the repair organ, held-out replay, and an online trial on your own work. Every other item stays planned: needs a gate.')));
}

export default async function render(root, ctx) {
  const offs = [];
  const head = h('div.page-head', h('div', h('h2', 'Self-improvement'),
    h('p', 'Runesmith rewrites its own repair organ only with evidence. Eligible experience is split in two: the Improver model sees one half, and every candidate is tested on the other. Support-report-assisted repairs stay available for local review but are excluded from learning and trial scoring. A candidate that wins is frozen, not switched on. It becomes active only by winning a trial on eligible fresh work, or by your explicit choice. Rolling back is one click.')));
  const body = h('div');
  root.append(head, body);
  const load = async () => {
    const d = await get('/api/improve');
    const settings = ctx.app.state?.settings || {};
    clear(body);
    // ---- active + lineage
    const activeName = (d.lineage.find((g) => g.active) || {}).name || d.active;
    const lineage = h('div.card', h('div.card-head', h('h3', icon('branch'), 'Generations'), h('span.badge.rune', `active: ${activeName}`)));
    const list = h('div.list');
    for (const g of d.lineage.slice().reverse()) {
      const val = g.validation ? `validation ${g.validation.strict_successes} vs ${g.incumbent_validation?.strict_successes ?? '?'}` : '';
      const item = h('div.item', h('div', { class: `ico ${g.active ? 'accent' : ''}` }, icon(g.origin === 'imported' ? 'download' : g.origin === 'kaizen' ? 'spark' : 'rune')),
        h('div.body', h('div.title', g.name || g.id, ' ', h('span.small.faint.mono', g.id), ' ', g.active ? h('span.badge.accent', 'active') : null, ' ', h('span.badge', g.origin), g.same_kernel ? null : h('span.badge.warn', 'older kernel')),
          h('div.meta', [g.label, val, g.frozen_utc ? `frozen ${ago(g.frozen_utc)}` : ''].filter(Boolean).join(' · '))),
        !g.active ? h('button.btn.sm', { onclick: (e) => activate(e.currentTarget, g, load) }, icon('undo'), 'Make active') : null);
      commentable(item, 'generation', g.id, g.id);
      item.querySelector('.note-btn').style.right = g.active ? '8px' : '120px';
      list.append(item);
    }
    lineage.append(list);
    if (d.requalification?.requalified) lineage.append(h('div.callout.mt-8', icon('info'), h('div', `Runesmith was updated, so the active organs were re-checked and re-qualified under the new kernel (same bytes): ${d.requalification.from} → ${d.requalification.id}.`)));
    // ---- trial
    const t = d.trial;
    const nameOf = (id) => { const g = d.lineage.find((x) => x.id === id); return g ? `${g.name} · ${id.replace('gen-', '')}` : id; };
    const trial = h('div.card', { class: t ? 'glow' : '' }, h('div.card-head', h('h3', icon('scale'), 'Online trial'), t ? h('span.badge.violet', 'running') : h('span.badge', 'none open')));
    if (t) {
      const bar = (arm) => { const [s, n] = t.counts[arm]; return h('div', h('div.row.small', h('b', arm === 'candidate' ? `Candidate ${nameOf(t.candidate)}` : `Incumbent ${nameOf(t.incumbent)}`), h('span.spacer'), h('span', `${s} repaired of ${n}`)),
        h('div', { class: `bar mt-8${arm === 'incumbent' ? ' rune' : ''}` }, h('i', { style: { width: `${Math.min(100, (n / t.max_per_arm) * 100)}%` } }))); };
      trial.append(h('p.small.muted', `Eligible new work is split between the two by a seeded coin. Support-report-assisted work is excluded before assignment. At every ${t.look_every} finished tasks per arm (from ${t.min_per_arm}), a one-sided Fisher test compares them at level ${t.level_per_look.toFixed(4)} per look. The candidate is activated only if it is clearly better; otherwise the incumbent stays. At most ${t.max_per_arm} tasks per arm.`),
        h('div.col.gap-16.mt-8', bar('incumbent'), bar('candidate')),
        t.looks_detail?.length ? h('table.table.small.mt-16', h('tr', ['Look', 'Incumbent', 'Candidate', 'p (better)', 'p (worse)'].map((x) => h('th', x))),
          t.looks_detail.map((l) => h('tr', h('td', String(l.look)), h('td', `${l.incumbent[0]}/${l.incumbent[1]}`), h('td', `${l.candidate[0]}/${l.candidate[1]}`), h('td', String(l.p_candidate_better)), h('td', String(l.p_candidate_worse))))) : h('p.tiny.faint.mt-8', 'No look yet: the first comes after enough tasks on both arms.'));
      // Journey J6-F5: turning self-improvement off stops new campaigns, not the trial the owner opened; and the
      // only way to stop a trial was to switch generations. Say so, and offer a plain stop that keeps what runs.
      trial.append(...[settings.kaizen ? null : h('p.small.mt-8', 'Self-improvement is off, so no new campaigns start. This trial keeps comparing the two on new repairs, and the candidate becomes active only if it clearly wins.'),
        h('div.row.mt-8', h('button.btn.sm', { onclick: (e) => withBusy(e.currentTarget, async () => {
          if (!(await confirmDialog({ title: 'Stop this trial?', confirm: 'Stop the trial',
            text: `${nameOf(t.incumbent)} stays active and ${nameOf(t.candidate)} is not used. The counts so far are kept, and the trial is recorded as closed by your choice.` }))) return;
          const r = await post(`/api/improve/activate/${t.incumbent}`, {});
          r.ok ? toast('Trial stopped; what runs is unchanged.', 'good') : toast(r.detail || 'The trial could not be stopped.', 'warn');
          load();
        }) }, icon('x'), 'Stop this trial'))].filter(Boolean));
      commentable(trial, 'trial', t.candidate, `trial of ${t.candidate}`);
    } else trial.append(h('p.muted', 'A trial opens when a candidate is frozen by a Kaizen campaign or adopted from the library.'));
    const OUTCOME = { activate: ['good', 'check', 'won: activated'], reject: ['', 'x', 'did not win: rejected'], closed_by_owner: ['warn', 'user', 'closed by your choice'] };
    if (d.closed_trials?.length) trial.append(h('div.label-text.mt-16', 'Closed trials'), h('div.list', d.closed_trials.map((c) => {
      const [cls, ic, words] = OUTCOME[c.decision] || ['', 'info', c.decision];
      return h('div.item', h('div', { class: `ico ${cls}` }, icon(ic)),
        h('div.body', h('div.title', `${nameOf(c.candidate)}: ${words}`), h('div.meta', `incumbent ${c.counts.incumbent[0]}/${c.counts.incumbent[1]} · candidate ${c.counts.candidate[0]}/${c.counts.candidate[1]} · ${c.looks} look(s)`)));
    })));
    // ---- library
    const lib = h('div.card', h('div.card-head', h('h3', icon('book'), 'Library of proven generations'), h('span.badge', 'ships with Runesmith')));
    if (!d.library.length) lib.append(h('p.muted', 'Empty.'));
    for (const e of d.library) {
      const adoptedWords = e.imported_as ? (t && t.candidate === e.imported_as ? 'Adopted: on trial now' : e.imported_as === d.active ? 'Adopted: active' : 'Adopted') : null;
      const adopt = h('button.btn.primary', { disabled: !!e.imported_as || !!t, title: e.imported_as || '' }, icon('download'), adoptedWords || (t ? 'A trial is already open' : 'Adopt: start a trial'));
      adopt.addEventListener('click', () => withBusy(adopt, async () => {
        if (!(await confirmDialog({ title: `Adopt ${e.name}?`, text: `${e.name} is checked (digests, allowed imports, a confined smoke test), frozen next to your active generation, and put on trial against it. It becomes active only if it wins on your own work.`, confirm: 'Adopt and start the trial' }))) return;
        const r = await post(`/api/improve/adopt/${e.id}`, {});
        r.ok ? toast(`${e.name} adopted as ${r.id}; the trial is open.`, 'good', 7000) : toast(r.detail, 'warn', 8000);
        load();
      }));
      const card = h('div.card.flat.mt-8', h('div.row', h('div.monogram', { style: { background: 'linear-gradient(135deg,#f8dc94,#c58a34)', color: '#0b0e14' } }, e.name), h('div.grow', h('b', e.title), h('div.small.muted', e.id))),
        h('p', e.summary), h('div.evidence', h('b', 'Evidence. '), e.evidence), h('p.small.muted.mt-8', h('b', 'Caveat. '), e.caveat), h('p.tiny.faint', `Authored by ${e.authored_by}.`), h('div.row', adopt));
      commentable(card, 'generation', e.id, `${e.name} (${e.id})`);
      lib.append(card);
    }
    // ---- capabilities & campaigns
    const caps = h('div.card', h('div.card-head', h('h3', icon('gauge'), 'Capabilities on your work'), h('span.badge', 'from its own records')));
    const names = { repair_yield: 'Repair yield', seconds_per_repair: 'Seconds per repair', calls_per_repair: 'Calls per repair', false_promotion_rate: 'False "fixed" rate' };
    for (const [k, label] of Object.entries(names)) {
      const c = d.self.capabilities[k] || { band: 'unknown', value: null };
      const row = h('div.gauge-row', h('span', label), h('div', { class: `bandbar${c.value == null ? ' unknown' : ''}` }, c.value != null ? h('span.mark', { style: { left: `${bandPosition(c)}%` } }) : null),
        h('span', { class: `band ${c.band}` }, c.value == null ? 'unknown' : fmtCap(k, c.value)));
      commentable(row, 'capability', k, label);
      caps.append(row);
    }
    if (d.self.open_targets?.length) caps.append(h('div.label-text.mt-16', 'Where it struggles (the next Kaizen target)'), h('div.list', d.self.open_targets.map((x) => h('div.item', h('div.ico.warn', icon('crosshair')), h('div.body', h('div.title', humanize(x.family || x.stage || x.kind || 'target')), h('div.meta', `share of failures: ${Math.round((x.share || 0) * 100)}%`))))));
    const camp = h('div.card', h('div.card-head', h('h3', icon('beaker'), 'Kaizen campaigns'),
      h('div.actions', h('span', { class: `badge ${settings.kaizen ? 'good' : ''}` }, settings.kaizen ? 'on' : 'off'), h('button.btn.sm', { onclick: () => ctx.navigate('settings') }, icon('sliders'), 'Settings'))),
      d.campaigns.length ? h('div.list', d.campaigns.slice().reverse().map((c) => h('div.item', h('div', { class: `ico ${c.decision === 'candidate' ? 'good' : ''}` }, icon('beaker')),
        h('div.body', h('div.title', `${humanize(c.decision)} · ${humanize(c.target || '')}`), h('div.meta', `${c.campaign} · best ${c.best ?? '—'} vs baseline ${c.baseline ?? '—'}`),
          c.attempts.length ? h('div.pillbox.mt-8', c.attempts.map((a) => h('span', { class: `badge ${a.accepted ? 'good' : ''}`, title: a.mechanism || '' }, `#${a.iteration} ${humanize(a.stage || '')}`))) : null))))
        : h('p.muted', `No campaign yet. One starts when Runesmith has at least ${settings.min_experience || 8} eligible stored attempts and enough new ones since the last campaign, and only while no trial is open.`),
      h('button.btn.sm.mt-8', { onclick: () => openNotes('self', 'runesmith', 'Runesmith itself') }, icon('note'), 'Tell the Improver something'));
    body.append(...[selfPlanCard(d.plan, ctx.navigate), h('div.grid.two.mt-24', h('div.col.gap-16', lineage, trial), h('div.col.gap-16', lib, caps, camp))].filter(Boolean));
  };
  await load();
  offs.push(bus.on('improve', debounce(load, 300)), bus.on('round', debounce(load, 500)));
  return () => offs.forEach((f) => f());
}

async function activate(btn, g, reload) {
  const ok = await confirmDialog({ title: `Make ${g.name || g.id} active?`, text: 'This is your choice, recorded as such in the ledger. It skips the trial, so use it to roll back to an earlier generation rather than to promote an untested one. An open trial is closed by it.', confirm: 'Make active' });
  if (!ok) return;
  await withBusy(btn, async () => {
    const r = await post(`/api/improve/activate/${g.id}`, {});
    if (r.ok) toast(`${g.name || g.id} is active.${r.trial_closed ? ' The open trial was closed.' : ''}`, 'good', 6000); else toast(r.detail, 'warn', 8000);
    reload();
  });
}
