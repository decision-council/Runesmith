// Operations: the work loop as it runs: stages with defined counters, who thinks what, attention, the trial and the schedule,
// each opening what it is, its evidence and the controls that govern it (docs/MAP_LOGIC.md, section 4).
import { h, icon, get, bus, clear, ago, humanize, clock, debounce, plural } from '../core.js';
import { when, panel as lmPanel, whatSection, evidenceSection, automateSection, noAutomation, focusHeading, kv } from './map-parts.js';

const STAGE_UI = { map: ['Map', 'map'], discover: ['Discover', 'search'], repair: ['Repair', 'hammer'], judge: ['Judge', 'scale'], propose: ['Propose', 'inbox'], apply: ['Apply', 'user'] };
const STAGE_CONTROLS = {
  map: ['probe_tests', 'max_objects', 'remap'],
  discover: ['auto_work', 'interval_minutes', 'full_speed', 'autonomy'],
  repair: ['auto_work', 'interval_minutes', 'full_speed', 'autonomy'],
  judge: ['checks_autopilot', { id: 'link', label: 'Read and approve checks yourself', now: 'Checks you approve are never replaced by the autopilot.', effect: 'Goals & plan shows each milestone’s proposed checks.', button: 'Open Goals & plan', go: ['goals'] }],
  propose: ['build_apply', 'autonomy', { id: 'link', label: 'Allowed folders for automatic apply', now: 'Set together with the switch, in Build continuation.', effect: 'Goals & plan names the files or folders a checked draft may be written in.', button: 'Open Goals & plan', go: ['goals'] }],
  apply: ['build_apply', 'autonomy', { id: 'link', label: 'Review what waits for you', now: 'Every fix and draft waits in Work & proposals until you apply it, unless automatic apply is on.', effect: 'The page that holds Apply, Undo and Reject.', button: 'Open Work & proposals', go: ['work'] }],
};
const MODE_TEXT = { HEALTHY: 'Healthy: most attention goes to your work', SUSPECTED_BLOCKAGE: 'A failure keeps recurring: the repairs may be struggling',
  SUBJECT_BLOCKED: 'Blocked by a recurring failure: the improvement plan treats it as a struggle', RECOVERING: 'Recovering after an improvement',
  CAPACITY_CONSTRAINED: 'Models are short of capacity: work waits, nothing is scored' };

export default async function operationsLens(body, ctx) {
  const offs = [];
  const box = h('div');
  body.append(box);
  let selected = null, current = null, token = 0, last = null;

  const select = async (kind, key, focus) => {
    selected = `${kind}:${key}`;
    const mine = ++token;
    let el;
    try { el = await panelFor(kind, key, last); } catch (error) { el = lmPanel({ eyebrow: 'Operations', title: 'Could not be read', onClose: closeDetail }); el.append(h('p.small.muted', error.message || String(error))); }
    if (mine !== token) return;
    current = el;
    paintDetail();
    if (focus) { focusHeading(current); current.scrollIntoView?.({ block: 'nearest' }); }
  };
  const closeDetail = () => { selected = null; current = null; token++; paintDetail(); };
  const detail = h('div.lm-detail');
  const paintDetail = () => {
    clear(detail);
    detail.append(current || h('p.small.faint', 'Select a stage, a model role, attention, the trial or the schedule to see what it means, the facts behind it and the controls that govern it.'));
    for (const el of box.querySelectorAll('.lm-pressable')) el.classList.toggle('sel', el.dataset.key === selected);
  };

  const panelFor = async (kind, key, d) => {
    if (kind === 'stage') {
      const s = (d.stages || []).find((x) => x.id === key) || legacyStage(d, key);
      const el = lmPanel({ eyebrow: 'Work-loop stage', title: `${STAGE_UI[key]?.[0] || key} · ${s.unit}`, onClose: closeDetail });
      el.append(whatSection(`${STAGE_UI[key]?.[0] || key}: ${s.definition}.`),
        evidenceSection([{ label: 'Count', value: `${s.count} (${s.unit})`, source: s.source, utc: s.utc },
          { label: 'What is counted', value: s.definition, source: 'docs/MAP_LOGIC.md, section 4' },
          { label: 'Since when', value: s.window, source: s.source },
          s.extra ? { label: 'Also', value: s.extra, source: s.source } : null].filter(Boolean)),
        await automateSection(ctx, STAGE_CONTROLS[key] || []));
      return el;
    }
    if (kind === 'role') {
      const names = d.roles[key] || [];
      const el = lmPanel({ eyebrow: 'Who thinks what', title: d.role_labels[key] || key, onClose: closeDetail });
      const rows = names.map((n) => {
        const e = d.roles_evidence?.[n], st = d.stats[n];
        const calls = e ? e.calls : st?.calls ?? 0, errors = e ? e.errors : st?.errors ?? 0;
        return { label: n, value: `${calls} calls, ${errors} errors${st ? `, about ${(st.latency_s / Math.max(1, st.calls)).toFixed(1)} s each` : ''}${e?.failing_every_call ? ` — failing every call (${errors} of ${calls})` : ''}${e?.last_error ? `; last error: ${e.last_error}` : ''}`,
          source: e ? e.source : 'OPERATIONS.json', utc: e?.last_utc };
      });
      el.append(whatSection(`${d.role_labels[key]}. The first model in the chain is asked; the next ones take over when it cannot answer.`),
        evidenceSection(rows.length ? rows : [{ label: 'Chain', value: key === 'plan' && d.ready.plan ? `borrows the ${d.ready.plan_source} role's model` : key === 'acceptance' && d.ready.acceptance ? 'uses the Planner’s model' : 'no model yet', source: 'the role assignments in runesmith.json' }]),
        await automateSection(ctx, [{ id: 'link', label: 'Choose the models for this role', now: 'Thinking power holds the role assignments and the free-key chain.', effect: 'Add a model, order the fallbacks, or remove one.', button: 'Open Thinking power', go: ['inference'] }]));
      return el;
    }
    if (kind === 'attention') {
      const a = d.attention;
      const el = lmPanel({ eyebrow: 'Attention', title: 'Self-improvement share', onClose: closeDetail });
      el.append(whatSection('Your share of work turns that go to improving Runesmith itself. The line beside it is only a health signal: it shows when the same failure keeps recurring, and it does not change the share.'),
        evidenceSection(a ? [{ label: 'Share', value: `${Math.round(a.share * 100)}% (${Math.round(a.share * 10)} of every 10 work turns)`, source: 'your setting self_improvement_share' },
          { label: 'Health signal', value: MODE_TEXT[a.mode] || a.mode, source: 'ATTENTION.json: it watches outcomes of recent attempts' },
          { label: 'What the automatic share would have been', value: `${Math.round((a.automatic_share ?? 0) * 100)}%`, source: 'ATTENTION.json (shown for comparison only)' }] : [{ label: 'Attention', value: 'starts once Runesmith has worked on something', source: 'ATTENTION.json (not written yet)' }]),
        await automateSection(ctx, ['self_improvement_share', 'kaizen']));
      return el;
    }
    if (kind === 'trial') {
      const t = d.trial;
      const station = d.lineage_ordered?.stations?.find((g) => g.trial && g.trial.state === 'open');
      const el = lmPanel({ eyebrow: 'Online trial', title: t ? 'A candidate is on trial' : 'No trial open', onClose: closeDetail });
      const nameOf = (id) => d.lineage_ordered?.stations?.find((g) => g.id === id)?.name || id;
      if (!t) {
        el.append(whatSection('A candidate generation must win a trial on your own work before it can become active. None is open now.'),
          evidenceSection([{ label: 'Trial', value: 'none open', source: 'TRIAL.json (absent)' }]),
          await automateSection(ctx, ['adopt', { id: 'link', label: 'Self-improvement', now: 'Generations, campaigns and the library.', effect: 'Where a trial is opened, read and ended.', button: 'Open Self-improvement', go: ['improve'] }]));
        return el;
      }
      const tr = station?.trial;
      el.append(whatSection(`${nameOf(t.candidate)} challenges ${nameOf(t.incumbent)}. New work is split between them by a seeded coin; the result decides activation.`),
        evidenceSection([{ label: 'Incumbent', value: `repaired ${t.counts.incumbent[0]} of ${t.counts.incumbent[1]}`, source: 'TRIAL.json', utc: tr?.opened_utc },
          { label: 'Candidate', value: `repaired ${t.counts.candidate[0]} of ${t.counts.candidate[1]}`, source: 'TRIAL.json' },
          { label: 'Rule', value: tr ? `a one-sided Fisher test at level ${Number(tr.level_per_look).toFixed(4)} per look (alpha ${tr.alpha}); at most ${tr.max_per_arm} tasks per arm` : `at most ${t.max_per_arm} tasks per arm`, source: 'TRIAL.json' },
          { label: 'Looks', value: tr ? `${tr.looks} done; the next comes when each arm has ${tr.next_look_at} finished` : 'not read', source: 'TRIAL.json' }]),
        await automateSection(ctx, [{ id: 'stop_trial', incumbent: t.incumbent, incumbentName: nameOf(t.incumbent), candidateName: nameOf(t.candidate) },
          { id: 'link', label: 'Self-improvement', now: 'Generations, campaigns and the library.', effect: 'Where a trial is opened, read and ended.', button: 'Open Self-improvement', go: ['improve'] }]));
      return el;
    }
    // the schedule
    const w = d.worker, s = d.settings;
    const el = lmPanel({ eyebrow: 'Schedule', title: 'When rounds run', onClose: closeDetail });
    el.append(whatSection('How Runesmith decides when to work: its autonomy, whether rounds run on a schedule, and when the next one is due.'),
      evidenceSection([{ label: 'Autonomy', value: s.autonomy === 'propose' ? 'Propose: works, then asks you' : 'Observe: maps and watches', source: 'your setting autonomy' },
        { label: 'Scheduled rounds', value: s.auto_work ? (s.full_speed ? `full speed (waits at most ${s.interval_minutes} min)` : `every ${s.interval_minutes} min`) : 'off', source: 'your settings auto_work, interval_minutes, full_speed' },
        { label: 'Next round', value: w.next_round_utc ? `${clock(w.next_round_utc)} (${ago(w.next_round_utc)})` : 'none due', source: 'computed from the settings and the last round' },
        { label: 'Last round', value: d.round_utc ? `${ago(d.round_utc)}: ${humanize(d.last_round?.outcome)}` : 'never', source: 'WORK.json', utc: d.round_utc }]));
    if (w.recovery) el.append(h('div.callout.warn.mt-8', icon('alert'), h('div', h('b', 'A restart hold waits for you. '), `The Studio was restarted while a job ran; ${plural(w.recovery.waiting || 0, 'job')} wait until you review them in Activity.`)));
    el.append(await automateSection(ctx, ['autonomy', 'auto_work', 'interval_minutes', 'full_speed', 'recovery_policy',
      ...(w.recovery ? [{ id: 'link', label: 'Review the held jobs and Resume', now: 'The review needs your decision on the current revision.', effect: 'Activity shows the review and the Resume button, with their usual confirmations.', button: 'Open Activity', go: ['activity'] }] : [])]));
    return el;
  };
  const legacyStage = (d, key) => {
    const p = d.pipeline, label = STAGE_UI[key]?.[0] || key;
    const n = { map: p.objects, discover: p.code_objects, repair: p.attempts, judge: p.accepted, propose: p.waiting, apply: p.applied }[key] ?? 0;
    return { id: key, label, count: n, unit: { map: 'objects', discover: 'code objects', repair: 'attempts', judge: 'accepted', propose: 'waiting', apply: 'applied' }[key], definition: 'its counter could not be read in full, so only the older count is shown', window: 'unknown', source: 'the older counters' };
  };

  const load = async () => {
    const d = await get('/api/map/operations');
    last = d;
    clear(box);
    const w = d.worker;
    const liveStage = { mapping: 0, discovering: 1, working: 2, planning: -1, drafting: -1 }[w.status];
    const stages = d.stages || Object.keys(STAGE_UI).map((k) => legacyStage(d, k));
    const pipe = h('div.card', h('div.card-head', h('h3', icon('activity'), 'The work loop'),
      h('span', { class: `badge ${w.current ? 'rune' : w.paused ? 'warn' : ''}` }, w.current ? (w.detail || w.status) : w.paused ? 'paused' : 'idle')),
      h('div.pipeline', stages.map((s, i) => h('div', { class: `stage lm-stage lm-pressable${i === liveStage ? ' live' : ''}`, 'data-key': `stage:${s.id}`, title: `${s.definition} (${s.window})`,
        'aria-label': `${STAGE_UI[s.id]?.[0] || s.id}: ${s.count} ${s.unit}. ${s.window}. Open its definition, evidence and controls.`, onclick: () => select('stage', s.id, true) },
        h('div.orb', icon(STAGE_UI[s.id]?.[1] || 'activity')), h('b', String(s.count ?? 0)), h('span', `${STAGE_UI[s.id]?.[0] || s.id} · ${s.unit}`), h('div.tiny.faint', s.window)))),
      h('p.tiny.faint', 'Runesmith never writes to your files on its own: every fix waits in Work & proposals until you apply it.'),
      d.living_problems?.length ? h('p.tiny.faint', `Could not read in full: ${d.living_problems.join('; ')}.`) : null);
    const roles = h('div.card', h('div.card-head', h('h3', icon('cpu'), 'Who thinks what'), h('div.actions', h('button.btn.sm', { onclick: () => ctx.navigate('inference') }, 'Thinking power', icon('right')))));
    for (const [role, label] of Object.entries(d.role_labels)) {
      const names = d.roles[role] || [];
      const meta = names.length ? names.map((n) => {
        const st = d.stats[n], e = d.roles_evidence?.[n];
        return `${n}${st ? ` (${st.calls} calls, ${st.errors} errors, ~${(st.latency_s / Math.max(1, st.calls)).toFixed(1)} s)` : ''}${e?.failing_every_call ? ` — failing every call (${e.errors} of ${e.calls})` : ''}`;
      }).join(' → ') : role === 'plan' && d.ready.plan ? `borrows the ${d.ready.plan_source} role's model` : role === 'acceptance' && d.ready.acceptance ? 'uses the Planner’s model' : 'no model yet';
      const failing = names.some((n) => d.roles_evidence?.[n]?.failing_every_call);
      roles.append(h('div.item.lm-pressable', { 'data-key': `role:${role}`, 'aria-label': `${label}: ${meta}. Open its evidence and controls.`, onclick: () => select('role', role, true) },
        h('div', { class: `ico ${failing ? 'bad' : names.length ? 'rune' : 'warn'}` }, icon(role === 'repair' ? 'hammer' : role === 'kaizen' ? 'spark' : role === 'acceptance' ? 'check' : 'wand')),
        h('div.body', h('div.title', label), h('div.meta', meta))));
    }
    const att = d.attention;
    const attention = h('div.card', h('div.card-head', h('h3', icon('gauge'), 'Attention'), h('div.actions', h('button.btn.sm', { 'data-key': 'attention:share', onclick: () => select('attention', 'share', true) }, 'What this means'))),
      att ? h('div', h('div.kpi', h('div.v', `${Math.round(att.share * 100)}%`, h('small', 'self')), h('div.k', MODE_TEXT[att.mode] || att.mode)),
        h('div.bar.rune.mt-8', h('i', { style: { width: `${att.share * 100}%` } })), h('p.tiny.faint.mt-8', 'Your share of work turns that go to improving Runesmith itself (Settings, Self-improvement). The line above is only a health signal: it shows when the same failure keeps recurring, and it no longer changes the share.'))
        : h('p.muted', 'Attention starts once Runesmith has worked on something.'));
    const t = d.trial;
    const trial = h('div.card', h('div.card-head', h('h3', icon('scale'), 'Trial'), h('div.actions', h('button.btn.sm', { 'data-key': 'trial:open', onclick: () => select('trial', 'open', true) }, 'What this means'))),
      t ? h('div', h('p.small', `${t.candidate} challenges ${t.incumbent}. New work is split between them by a seeded coin; the result decides activation.`),
        h('div.grid.two', ['incumbent', 'candidate'].map((arm) => h('div.kpi', h('div.k', arm), h('div.v', `${t.counts[arm][0]}`, h('small', `/ ${t.counts[arm][1]}`)), h('div.bar.mt-8', h('i', { style: { width: `${Math.min(100, t.counts[arm][1] / t.max_per_arm * 100)}%` } })))))) : h('p.muted', 'No trial open. A candidate generation must win one before it can become active.'));
    const sched = h('div.card', h('div.card-head', h('h3', icon('clock'), 'Schedule'), h('div.actions', h('button.btn.sm', { 'data-key': 'schedule:rounds', onclick: () => select('schedule', 'rounds', true) }, 'What this means'))),
      kv([['Autonomy', d.settings.autonomy === 'propose' ? 'Propose: works, then asks you' : 'Observe: maps and watches'], ['Scheduled rounds', d.settings.auto_work ? (d.settings.full_speed ? `full speed (waits at most ${d.settings.interval_minutes} min)` : `every ${d.settings.interval_minutes} min`) : 'off'],
        ['Next round', w.next_round_utc ? `${clock(w.next_round_utc)} (${ago(w.next_round_utc)})` : '—'], ['Last round', d.round_utc ? `${ago(d.round_utc)}: ${humanize(d.last_round?.outcome)}` : 'never']]),
      w.recovery ? h('div.callout.warn.mt-8', icon('alert'), h('div', h('b', 'A restart hold waits for you. '), 'Review it in Activity before Resume.')) : null,
      h('div.row.mt-8', h('button.btn.sm', { onclick: () => ctx.navigate('settings') }, icon('sliders'), 'Change')));
    const consoleBox = h('div.console');
    (w.lines || []).slice(-60).forEach((l) => consoleBox.append(h('div', { class: `l ${l.level || ''}` }, h('time', clock(l.utc)), l.text)));
    const live = h('div.card', h('div.card-head', h('h3', icon('activity'), 'Live log')), consoleBox);
    box.append(pipe, detail, h('div.grid.two.mt-16', roles, attention), h('div.grid.two.mt-16', trial, sched), h('div.mt-16'), live);
    paintDetail();
    setTimeout(() => { consoleBox.scrollTop = 1e9; }, 0);
  };
  await load();
  const later = debounce(async () => { const keep = selected; await load(); if (keep) { const [k, key] = keep.split(':'); select(k, key, false); } }, 800);
  // while a panel is open, the busy streams (the worker's lines, model calls) do not redraw it under the owner's hand
  for (const k of ['worker', 'round', 'call', 'improve', 'settings']) offs.push(bus.on(k, (...a) => { if (selected && (k === 'worker' || k === 'call')) return; later(...a); }));
  return () => offs.forEach((f) => f());
}
