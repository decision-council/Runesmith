// The living map's shared parts: the What this is / Evidence / Automate panel, and the owner controls Automate offers.
//
// Every control here is an existing setting or action, sent through its existing endpoint, with its existing
// confirmation where there is one (docs/MAP_LOGIC.md, "The Automate mapping"). The map adds reach, never authority:
// nothing is sent until the owner presses the control's own button, and Cancel sends nothing.
import { h, icon, get, post, toast, clear, plural, withBusy, confirmDialog, openNotes, $ } from '../core.js';

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const trunc = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));
export const hhmm = (utc) => (utc && String(utc).length >= 16 ? `${String(utc).slice(11, 16)}Z` : 'an unknown time');
export const when = (utc) => (utc ? `${String(utc).slice(0, 10)} ${hhmm(utc)}` : 'an unknown time');

// ------------------------------------------------------------------------------------------------ the panel --

/** A details panel: a header with its close button, then the three sections the caller adds. */
export function panel({ eyebrow, title, onClose, note }) {
  const el = h('div.map-side.lm-panel', { role: 'region', 'aria-label': `Details: ${title}` });
  el.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('.modal-wrap, .drawer, .cmdk')) { e.stopPropagation(); onClose(); } });
  el.append(h('div.row', h('div.grow', h('div.small.faint', eyebrow), h('h3', { tabindex: '-1', style: { margin: '2px 0 0', fontSize: '17px', overflowWrap: 'anywhere' } }, title)),
    h('button.btn.icon.sm.ghost', { onclick: onClose, title: 'Close', 'aria-label': 'Close the details' }, icon('x'))));
  if (note) el.append(h('div.row.mt-8', h('button.btn.sm', { onclick: () => openNotes(...note) }, icon('note'), 'Comment')));
  return el;
}

export const section = (title, ...children) => h('section.lm-sec', { 'aria-label': title }, h('h4.label-text', title), ...children);
export const whatSection = (text) => section('What this is', h('p.small', text));

/** The facts, each with its source (and its time when it has one): [{label, value | items, source, utc}]. */
export function evidenceSection(rows, ...more) {
  return section('Evidence', ...rows.filter(Boolean).map((r) => h('div.lm-fact',
    h('div.small.faint', r.label),
    r.items && r.items.length ? h('ul.small.lm-items', r.items.map((x) => h('li', x))) : h('div.small', { style: { overflowWrap: 'anywhere' } }, r.value == null || r.value === '' ? 'unknown' : String(r.value)),
    h('div.tiny.faint.lm-src', `Source: ${r.source || 'not recorded'}${r.utc ? ` · ${when(r.utc)}` : ''}`))), ...more);
}

/** Where the part's own words go: a comment on it. */
export const focusHeading = (el) => { const head = el.querySelector('h3'); if (head) { head.setAttribute('tabindex', '-1'); head.focus({ preventScroll: true }); } };

// ------------------------------------------------------------------------------------------ the controls --
// The confirmations are the owner's own, word for word, from the places that already ask (a test keeps them in step).
export const CONFIRM = {
  fix_tests: (files, auto) => ({ title: 'Fix the failing tests?', confirm: 'Fix them', icon: 'hammer',
    text: `Runesmith adds a milestone, “Make the failing tests pass”. Your ${files} test file(s) are frozen as they are now and decide when it is done. ` +
      (auto ? 'When every test passes, the fix is applied to your code automatically; your tests are never changed.' : 'You review the fix and apply it yourself.') }),
  build_apply: (where) => ({ title: 'Apply checked drafts automatically in this folder?',
    text: `Runesmith may then write ${where}. It writes only when a draft passes both its own tests and your acceptance checks for the milestone. You can turn this off here at any time; backups and Undo stay available.`,
    confirm: 'Allow automatic apply' }),
  autopilot: () => ({ title: 'Let Runesmith approve checks itself?',
    text: 'Runesmith then asks for acceptance checks for ready milestones and approves them only when they pass every test: tried on your project, no problems it found itself, and a second model working out the same expected values. Otherwise it turns them down with the reason and asks again, twice at most, then leaves them for you. Checks you approved are never replaced by it. You can read and replace any of its checks.',
    confirm: 'Turn on the check autopilot' }),
  adopt: (name) => ({ title: `Adopt ${name}?`, text: `${name} is checked (digests, allowed imports, a confined smoke test), frozen next to your active generation, and put on trial against it. It becomes active only if it wins on your own work.`, confirm: 'Adopt and start the trial' }),
  activate: (name) => ({ title: `Make ${name} active?`, text: 'This is your choice, recorded as such in the ledger. It skips the trial, so use it to roll back to an earlier generation rather than to promote an untested one. An open trial is closed by it.', confirm: 'Make active' }),
  stop_trial: (incumbent, candidate) => ({ title: 'Stop this trial?', confirm: 'Stop the trial',
    text: `${incumbent} stays active and ${candidate} is not used. The counts so far are kept, and the trial is recorded as closed by your choice.` }),
  // Running the project's own tests executes its code: the words the Settings switch and the Re-map button already carry.
  watch_tests: () => ({ title: 'Run this project’s tests while mapping?', confirm: 'Turn it on and measure',
    text: 'This executes the project’s own code, on a throwaway copy of the folder, so nothing is written into it. Only for projects you trust: the copy is not a security boundary.' }),
};
const INTERVALS = [[5, 'every 5 minutes'], [15, 'every 15 minutes'], [30, 'every 30 minutes'], [60, 'every hour'], [180, 'every 3 hours'], [720, 'twice a day'], [1440, 'once a day']];
const POLICY = new Set(['auto_work', 'probe_tests', 'kaizen']);          // the owner's first-run choices: saved as chosen
const onOff = (v) => (v ? 'on' : 'off');

/** What the controls read: the settings always, and the other records only for the controls that need them. */
export async function loadState(needs = []) {
  const S = { settings: await get('/api/settings') };
  const wanted = new Set(needs);
  const reads = [];
  if (wanted.has('build')) reads.push(get('/api/build').then((v) => { S.build = v; }).catch(() => { S.build = null; }));
  if (wanted.has('fix')) reads.push(get('/api/fix-tests').then((v) => { S.fix = v?.offer || null; }).catch(() => { S.fix = null; }));
  if (wanted.has('improve')) reads.push(get('/api/improve').then((v) => { S.improve = v; }).catch(() => { S.improve = null; }));
  if (wanted.has('env')) reads.push(get('/api/map/environment').then((v) => { S.env = v; }).catch(() => { S.env = null; }));
  await Promise.all(reads);
  return S;
}

const afterSave = (S, ctx, saved) => { Object.assign(S.settings, saved); ctx.refreshState?.(); };

/** A setting that is on or off: its current value, what turning it the other way changes, and the one button. */
function switchSetting(S, ctx, { id, key, label, ifOn, ifOff, confirmOn, extra }) {
  const on = !!S.settings[key];
  return { id, label, now: `${label}: ${onOff(on)}.`, effect: on ? ifOff : ifOn, buttons: [{
    label: on ? 'Turn off' : 'Turn on', run: async () => {
      if (!on && confirmOn && !(await confirmDialog(confirmOn()))) return;
      afterSave(S, ctx, await post('/api/settings', { [key]: !on, ...(POLICY.has(key) ? { policy_chosen: true } : {}) }));
      if (!on && extra) await extra();
      toast(`${label}: ${onOff(!on)}`, 'good', 2200);
    } }] };
}

function choiceSetting(S, ctx, { id, key, label, options, effect, words }) {
  const value = S.settings[key];
  return { id, label, now: `${label}: ${words ? words(value) : value}.`, effect, select: { value, options, onchange: async (v) => {
    afterSave(S, ctx, await post('/api/settings', { [key]: v }));
    toast(`${label} saved`, 'good', 1800);
  } } };
}

function numberSetting(S, ctx, { id, key, label, min, max, effect }) {
  return { id, label, now: `${label}: ${S.settings[key]}.`, effect, number: { value: S.settings[key], min, max, onchange: async (v) => {
    afterSave(S, ctx, await post('/api/settings', { [key]: v }));
    toast(`${label} saved`, 'good', 1800);
  } } };
}

/** The four build keys travel together, as Goals & plan sends them, so a change here is the same request as there. */
async function saveBuild(S, ctx, change) {
  const next = { build_steps: !!S.settings.build_steps, build_apply: !!(S.build ? S.build.apply : S.settings.build_apply),
    build_paths: S.settings.build_paths || [], checks_autopilot: !!S.settings.checks_autopilot, ...change };
  const saved = await post('/api/settings', next);
  afterSave(S, ctx, saved);
  if (S.build) S.build.apply = !!saved.build_apply;
  toast('Build settings saved for this folder.', 'good');
}

const REG = {
  // ---- how the loop runs
  auto_work: (S, ctx) => switchSetting(S, ctx, { id: 'auto_work', key: 'auto_work', label: 'Scheduled rounds',
    ifOn: `Turning on runs a round ${S.settings.full_speed ? `as soon as one ends (waiting at most ${S.settings.interval_minutes} min)` : `every ${S.settings.interval_minutes} min`} while the Studio is open; each round can spend model calls.`,
    ifOff: 'Turning off stops scheduled rounds. You can still run one by hand.' }),
  interval_minutes: (S, ctx) => choiceSetting(S, ctx, { id: 'interval_minutes', key: 'interval_minutes', label: 'How often a round runs',
    options: INTERVALS.concat(INTERVALS.some(([v]) => v === Number(S.settings.interval_minutes)) ? [] : [[Number(S.settings.interval_minutes), `every ${S.settings.interval_minutes} minutes`]]),
    words: (v) => (INTERVALS.find(([n]) => n === Number(v)) || [0, `every ${v} minutes`])[1],
    effect: 'A round maps, finds work, works on what is new and reports. With full speed on, this is the longest wait.' }),
  full_speed: (S, ctx) => switchSetting(S, ctx, { id: 'full_speed', key: 'full_speed', label: 'Full speed',
    ifOn: 'Turning on starts the next step as soon as one ends, while the models answer; it uses the free allowances faster.',
    ifOff: 'Turning off goes back to one round per interval.' }),
  autonomy: (S, ctx) => choiceSetting(S, ctx, { id: 'autonomy', key: 'autonomy', label: 'How Runesmith may act',
    options: [['observe', 'Observe: just look'], ['propose', 'Propose: also work and propose fixes']],
    words: (v) => (v === 'propose' ? 'Propose' : 'Observe'),
    effect: 'Observe maps and reports and asks no model. Propose also plans, drafts and brings you changes to review. Your files change only when you approve, or when you allow automatic apply for checked builds.' }),
  probe_tests: (S, ctx) => switchSetting(S, ctx, { id: 'probe_tests', key: 'probe_tests', label: 'Run this project’s tests while mapping',
    ifOn: 'Turning on executes the project’s own code on a throwaway copy of the folder each time it is mapped. Only for projects you trust.',
    ifOff: 'Turning off stops the test runs while mapping; recorded results stay.', confirmOn: CONFIRM.watch_tests }),
  max_objects: (S, ctx) => numberSetting(S, ctx, { id: 'max_objects', key: 'max_objects', label: 'Most objects to map', min: 1, max: 500,
    effect: 'For very large folders: only this many directories are mapped, and the map says how many were left out.' }),
  read_notes: (S, ctx) => switchSetting(S, ctx, { id: 'read_notes', key: 'read_notes', label: 'Give notes to the model',
    ifOn: 'Turning on lets your open notes travel with the work they are about, labelled as your guidance.',
    ifOff: 'Turning off keeps your notes from every model request.' }),
  remap: (S, ctx) => ({ id: 'remap', label: 'Re-map & measure', now: 'Maps the folder again.',
    effect: 'Runs each object’s tests on throwaway copies while it maps, whatever the switch above says. The map updates when it is done.',
    buttons: [{ label: 'Re-map & measure', run: async () => {
      await post('/api/worker/run', { job: 'map', params: { probe: true } });
      toast('Mapping and measuring… the map updates when done.', 'good');
    } }] }),
  watch_tests: (S, ctx) => ({ id: 'watch_tests', label: 'Watch its tests', needs: ['settings'],
    now: `Running this project’s tests while mapping: ${onOff(S.settings.probe_tests)}.`,
    effect: 'Turns the switch on and maps again, running the project’s own tests on a throwaway copy of the folder. Only for projects you trust.',
    buttons: [{ label: S.settings.probe_tests ? 'Measure its tests now' : 'Turn on and measure', run: async () => {
      if (!(await confirmDialog(CONFIRM.watch_tests()))) return;
      if (!S.settings.probe_tests) afterSave(S, ctx, await post('/api/settings', { probe_tests: true, policy_chosen: true }));
      await post('/api/worker/run', { job: 'map', params: { probe: true } });
      toast('Measuring: the tests run on throwaway copies.', 'good');
    } }] }),
  exclude: (S, ctx, extra) => ({ id: 'exclude', label: 'Keep Runesmith out of an object', needs: ['env'],
    now: (S.settings.exclude || []).length ? `Never touched: ${S.settings.exclude.join(', ')}.` : 'Nothing is on the never-touch list.',
    effect: 'An object on the list is listed on the map but never read, probed or worked on. It takes effect when the folder is mapped again, which this starts.',
    chips: { items: (extra?.objects || []).map((name) => ({ name, on: (S.settings.exclude || []).includes(name) })), toggle: async (name) => {
      const fresh = await get('/api/settings');                 // the list as it is now: another tab or Settings may have changed it
      const ex = new Set(fresh.exclude || []);
      ex.has(name) ? ex.delete(name) : ex.add(name);
      afterSave(S, ctx, await post('/api/settings', { exclude: [...ex] }));
      await post('/api/worker/run', { job: 'map' });
      toast(ex.has(name) ? `${name} will never be touched` : `${name} is included again`, 'good');
    } } }),
  fix_tests: (S, ctx, extra) => {
    const offer = S.fix && (!extra?.object || S.fix.object === extra.object) ? S.fix : null;
    return { id: 'fix_tests', label: 'Fix the failing tests (the whole project)',
      now: offer ? `${offer.object}: ${offer.tests_green == null ? 'some tests fail' : `${Math.round(offer.tests_green * 100)}% of its tests pass`}.` : 'Not offered now: the Overview offers it once a measurement (Re-map & measure, or a measuring round) shows failing tests.',
      effect: 'Adds a milestone whose acceptance is the project’s own test files, frozen as they are now, and builds it. It works on the whole project, not on this part alone; it changes code, never tests; you review and apply the fix yourself.',
      buttons: [{ label: 'Fix the failing tests', disabled: !offer, run: async () => {
        if (!(await confirmDialog(CONFIRM.fix_tests(offer.test_files, false)))) return;
        await post('/api/fix-tests', { allow_apply: false });
        await post('/api/worker/run', { job: 'build' });
        toast('Fixing the failing tests: follow it in Goals & plan and Activity.', 'good', 6000);
        ctx.navigate('goals');
      } }] };
  },
  // ---- the plan and the build
  milestone_form: (S, ctx, extra) => ({ id: 'milestone_form', label: 'Make a milestone for this file',
    now: 'Nothing is saved until you press Save.', effect: 'Adds one open milestone to the plan; no model is asked and no file is written.',
    form: { title: extra?.title || '', done_when: extra?.done_when || '', save: async (v) => {
      await post('/api/plan/milestones', { title: v.title, detail: v.detail || '', track: v.track || '', done_when: v.done_when });
      ctx.refreshState?.();
      toast('Milestone added. Find it in Goals & plan.', 'good');
    } } }),
  checks_autopilot: (S, ctx) => ({ id: 'checks_autopilot', label: 'Check autopilot', needs: ['build'],
    now: `Check autopilot: ${onOff(!!S.settings.checks_autopilot)}.`,
    effect: S.settings.checks_autopilot ? 'Turning off leaves proposed acceptance checks for you to approve.' : 'Turning on lets Runesmith approve proposed acceptance checks that pass every gate; otherwise it turns them down with the reason and leaves them for you.',
    buttons: [{ label: S.settings.checks_autopilot ? 'Turn off' : 'Turn on', run: async () => {
      if (!S.settings.checks_autopilot && !(await confirmDialog(CONFIRM.autopilot()))) return;
      await saveBuild(S, ctx, { checks_autopilot: !S.settings.checks_autopilot });
    } }] }),
  build_steps: (S, ctx) => ({ id: 'build_steps', label: 'Check drafts by running their tests', needs: ['build'],
    now: `Check drafts by running their tests: ${onOff(!!S.settings.build_steps)}.`,
    effect: 'Runs the project’s code and your acceptance checks in a throwaway working copy before a draft is written.',
    buttons: [{ label: S.settings.build_steps ? 'Turn off' : 'Turn on', run: async () => { await saveBuild(S, ctx, { build_steps: !S.settings.build_steps }); } }] }),
  build_apply: (S, ctx) => {
    const on = !!(S.build ? S.build.apply : S.settings.build_apply);
    const paths = S.settings.build_paths || [];
    return { id: 'build_apply', label: 'Apply checked drafts automatically', needs: ['build'],
      now: `Apply checked drafts automatically: ${onOff(on)}${paths.length ? `; allowed: ${paths.join(', ')}` : '; no allowed folders named'}.`,
      effect: on ? 'Turning off puts every draft back in your hands.' : 'Turning on lets Runesmith write a draft that passes both its own tests and your acceptance checks, only in the allowed files or folders. Backups and Undo stay available. It needs allowed folders: set them in Goals & plan.',
      buttons: [{ label: on ? 'Turn off' : 'Turn on', run: async () => {
        if (!on) {
          if (!paths.length) { toast('Name the files or folders Runesmith may write first, for example: src, tests. A . means the whole folder. Do it in Goals & plan → Build continuation.', 'warn', 8000); return; }
          const where = paths.some((p) => p === '.' || p === './') ? 'anywhere in this folder (never in Runesmith’s own records or .git)' : `only in: ${paths.join(', ')}`;
          if (!(await confirmDialog(CONFIRM.build_apply(where)))) return;
        }
        await saveBuild(S, ctx, { build_apply: !on });
      } }] };
  },
  stuck_policy: (S, ctx) => choiceSetting(S, ctx, { id: 'stuck_policy', key: 'stuck_policy', label: 'When a milestone’s tries are used up',
    options: [['wait', 'Wait for me'], ['retry', 'One more try'], ['retry_split', 'One more try, then break it down']],
    words: (v) => ({ wait: 'wait for you', retry: 'one more try', retry_split: 'one more try, then break it down' }[v] || v),
    effect: 'Three tries, and then it waits for you. “One more try” gives it one extra try with another model; “then break it down” also asks for smaller steps and adopts them, once.' }),
  recheck_policy: (S, ctx) => choiceSetting(S, ctx, { id: 'recheck_policy', key: 'recheck_policy', label: 'When a draft’s checks did not finish',
    options: [['wait', 'Wait for me'], ['recheck', 'Recheck once']], words: (v) => (v === 'recheck' ? 'recheck once' : 'wait for you'),
    effect: 'Checks that run out of time wait for your button. “Recheck once” lets Runesmith run them once more itself, with a longer limit and no model call.' }),
  recovery_policy: (S, ctx) => choiceSetting(S, ctx, { id: 'recovery_policy', key: 'recovery_policy', label: 'After an interrupted job',
    options: [['wait', 'Wait for me'], ['keep', 'Keep and continue']], words: (v) => (v === 'keep' ? 'keep and continue' : 'wait for you'),
    effect: 'If the Studio is restarted while a job runs, you review what was left before anything continues. “Keep and continue” lets Runesmith keep the waiting work and go on by itself; the interrupted job is never run again.' }),
  propose_checks: (S, ctx, extra) => ({ id: 'propose_checks', label: 'Propose acceptance checks',
    now: extra?.hasChecks ? 'This milestone has approved checks.' : 'No approved checks yet.',
    effect: 'Asks the Checker model for plain-words checks; they wait for you to read and approve them (unless the autopilot is on). It spends one model call.',
    buttons: [{ label: extra?.hasChecks ? 'Ask for new checks' : 'Propose acceptance checks', disabled: !extra?.ready, run: async () => {
      await post('/api/worker/run', { job: 'propose_acceptance', params: { milestone: extra.mid } });
      toast('Proposing acceptance checks for this milestone. They appear in Goals & plan for you to read and approve.', 'good', 6000);
    } }] }),
  // ---- Runesmith itself
  kaizen: (S, ctx) => switchSetting(S, ctx, { id: 'kaizen', key: 'kaizen', label: 'Let Runesmith improve itself',
    ifOn: 'Turning on lets self-improvement campaigns rewrite its repair organ from its own experience. A candidate becomes active only by winning a trial on your work.',
    ifOff: 'Turning off stops new campaigns. A trial that is already open goes on.' }),
  self_improvement_share: (S, ctx) => choiceSetting(S, ctx, { id: 'self_improvement_share', key: 'self_improvement_share', label: 'Self-improvement share',
    options: [10, 20, 30, 40, 50, 60, 70, 80, 90].map((v) => [v, `${v}%`]), words: (v) => `${v}% (${v / 10} of every 10 work turns)`,
    effect: 'How many of every 10 work turns go to improving Runesmith itself. A change is only made through its gate: a campaign, held-out replay and an online trial.' }),
  kaizen_every: (S, ctx) => numberSetting(S, ctx, { id: 'kaizen_every', key: 'kaizen_every', label: 'New attempts between campaigns', min: 1, max: 10000,
    effect: 'So every campaign works from fresh evidence.' }),
  min_experience: (S, ctx) => numberSetting(S, ctx, { id: 'min_experience', key: 'min_experience', label: 'Experience before the first campaign', min: 2, max: 10000,
    effect: 'Stored repair attempts needed before a campaign may start.' }),
  adopt: (S, ctx, extra) => {
    const library = S.improve?.library || [], trial = S.improve?.trial;
    return { id: 'adopt', label: 'Adopt a proven generation', needs: ['improve'],
      now: trial ? 'A trial is already open.' : `${plural(library.filter((e) => !e.imported_as).length, 'proven generation')} to adopt.`,
      effect: 'A library generation is checked, frozen next to the active one and put on trial against it. It becomes active only if it wins on your own work.',
      buttons: library.map((e) => ({ label: e.imported_as ? `${e.name}: adopted` : `Adopt ${e.name}: start a trial`, disabled: !!e.imported_as || !!trial, run: async () => {
        if (!(await confirmDialog(CONFIRM.adopt(e.name)))) return;
        const r = await post(`/api/improve/adopt/${e.id}`, {});
        r.ok ? toast(`${e.name} adopted as ${r.id}; the trial is open.`, 'good', 7000) : toast(r.detail, 'warn', 8000);
        ctx.refreshLens?.();
      } })) };
  },
  activate: (S, ctx, extra) => ({ id: 'activate', label: 'Make this generation active (roll back)',
    now: extra.active ? 'It is the active generation.' : 'It is not active.',
    effect: 'Your own choice, recorded as such in the ledger. It skips the trial, so use it to roll back to an earlier generation. An open trial is closed by it.',
    buttons: [{ label: 'Make active', disabled: !!extra.active, run: async () => {
      if (!(await confirmDialog(CONFIRM.activate(extra.name)))) return;
      const r = await post(`/api/improve/activate/${extra.gid}`, {});
      r.ok ? toast(`${extra.name} is active.${r.trial_closed ? ' The open trial was closed.' : ''}`, 'good', 6000) : toast(r.detail, 'warn', 8000);
      ctx.refreshLens?.();
    } }] }),
  stop_trial: (S, ctx, extra) => ({ id: 'stop_trial', label: 'Stop this trial',
    now: 'The candidate is being compared with the incumbent on new repairs.',
    effect: 'The incumbent stays active and the candidate is not used. The counts so far are kept, and the trial is recorded as closed by your choice.',
    buttons: [{ label: 'Stop this trial', run: async () => {
      if (!(await confirmDialog(CONFIRM.stop_trial(extra.incumbentName, extra.candidateName)))) return;
      const r = await post(`/api/improve/activate/${extra.incumbent}`, {});
      r.ok ? toast('Trial stopped; what runs is unchanged.', 'good') : toast(r.detail || 'The trial could not be stopped.', 'warn');
      ctx.refreshLens?.();
    } }] }),
  // ---- links to the page that already owns the control
  link: (S, ctx, extra) => ({ id: extra.id, label: extra.label, now: extra.now || '', effect: extra.effect || '', buttons: [{ label: extra.button, run: async () => { ctx.navigate(...extra.go); } }] }),
  none: (S, ctx, extra) => ({ id: extra.id || 'none', label: extra.label || 'Not automatable', now: extra.now, effect: extra.effect || '', none: true }),
};
const NEEDS = { build_steps: ['build'], build_apply: ['build'], checks_autopilot: ['build'], fix_tests: ['fix'], adopt: ['improve'], exclude: ['env'] };

/** The Automate section: each named control, current value first, what changes second, the button last. `extras` holds
 *  what a control needs from its part (the object's name, a generation's id). */
export async function automateSection(ctx, wanted, extras = {}) {
  const needs = wanted.flatMap((w) => NEEDS[typeof w === 'string' ? w : w.id] || []);
  let S;
  try { S = await loadState(needs); } catch (error) { return section('Automate', h('p.small.muted', `The controls could not be read: ${error.message || error}`)); }
  const box = section('Automate', h('p.tiny.faint', 'These are the owner controls that already exist, sent through their usual requests. Nothing changes until you press a button.'));
  for (const w of wanted) {
    const id = typeof w === 'string' ? w : w.id;
    const extra = typeof w === 'string' ? (extras[w] || {}) : w;
    const make = REG[id];
    if (!make) continue;
    const row = h('div.lm-ctl', { 'data-control': id });
    const draw = () => {
      const spec = make(S, ctx, extra);
      clear(row);
      row.append(...[h('div.row', h('b.small', spec.label)), spec.now ? h('div.small', spec.now) : null, spec.effect ? h('div.tiny.muted', spec.effect) : null].filter(Boolean));
      if (spec.buttons) row.append(h('div.row.wrap.mt-8', spec.buttons.map((b) => h('button.btn.sm', { disabled: b.disabled || null, onclick: (e) => withBusy(e.currentTarget, async () => { await b.run(); draw(); }) }, b.label))));
      if (spec.select) {
        const sel = h('select.select', { 'aria-label': spec.label, style: { width: 'auto', maxWidth: '100%' }, onchange: () => withBusy(sel, async () => { await spec.select.onchange(isNaN(Number(sel.value)) || sel.value === '' ? sel.value : Number(sel.value)); draw(); }) },
          spec.select.options.map(([v, l]) => h('option', { value: v, selected: String(v) === String(spec.select.value) }, l)));
        row.append(h('div.row.mt-8', sel));
      }
      if (spec.number) {
        const input = h('input.input', { type: 'number', min: spec.number.min, max: spec.number.max, value: spec.number.value, 'aria-label': spec.label, style: { width: '110px' } });
        input.addEventListener('change', () => withBusy(input, async () => { await spec.number.onchange(Number(input.value)); draw(); }));
        row.append(h('div.row.mt-8', input));
      }
      if (spec.chips) row.append(spec.chips.items.length ? h('div.pillbox.mt-8', spec.chips.items.map((c) => h('button', { class: `chip${c.on ? ' on' : ''}`, 'aria-pressed': String(c.on),
        onclick: (e) => withBusy(e.currentTarget, async () => { await spec.chips.toggle(c.name); draw(); }) }, c.on ? icon('lock') : null, c.name)))
        : h('div.tiny.faint.mt-8', 'No object to keep out: only the folders the map lists as objects can be excluded.'));
      if (spec.form) {
        const title = h('input.input', { value: spec.form.title, 'aria-label': 'Milestone title', placeholder: 'What should be true' });
        const done = h('input.input', { value: spec.form.done_when, 'aria-label': 'Done when', placeholder: 'Done when…' });
        row.append(h('div.col.gap-6.mt-8', title, done, h('div.row', h('button.btn.sm.primary', { onclick: (e) => withBusy(e.currentTarget, async () => {
          if (!title.value.trim()) { toast('A milestone needs a title.', 'warn'); return; }
          await spec.form.save({ title: title.value.trim(), done_when: done.value.trim() });
          title.value = '';
        }) }, icon('plus'), 'Save the milestone'))));
      }
    };
    draw();
    box.append(row);
  }
  return box;
}

/** Where a part cannot be automated, and what governs it instead, in plain words. */
export function noAutomation(why, governedBy, links = []) {
  return section('Automate', h('div.callout', icon('lock'), h('div', h('b', 'Not automatable, by design. '), why,
    governedBy ? h('div.small.mt-8', h('b', 'What governs it instead: '), governedBy) : null)),
  ...(links.length ? [h('div.row.wrap.mt-8', links.map((l) => h('button.btn.sm', { onclick: l.go }, l.label)))] : []));
}

// ---------------------------------------------------------------------------- shared drawing helpers --
/** Every `.node` of a lens drawing takes the keyboard: a Tab stop, announced by its tooltip, picked by Enter or Space. */
export function keyboardNodes(svg, pick) {
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


// ------------------------------------------------------------ pan and zoom --
export function panZoom(svg, g, fit) {
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


export function kv(rows) {
  return h('table.table.small', { style: { marginTop: '6px' } }, rows.map(([k, v]) => h('tr', h('td.faint', { style: { padding: '5px 8px 5px 0', width: '44%' } }, k), h('td', { style: { padding: '5px 0', wordBreak: 'break-word' } }, v == null || v === '' ? '—' : String(v)))));
}



// ------------------------------------------------------------------------------------------ the ladders --
// Old maps stay on disk until the owner re-maps. Render their retained probe with
// current evidence semantics, without starting tests or rewriting the receipt.
export function scopedObject(obj) {
  if (obj._overlaid) return obj;
  const probe = obj.probe || {}, unavailable = !!(probe.unavailable || probe.error);
  if (probe.runner !== 'unittest' && !unavailable) return obj;
  const objectives = (obj.objectives || []).map(row => ['test_pass_rate', 'test_suite_seconds'].includes(row.metric)
    ? {...row, value: null, band: 'unknown', evidence: 'unknown'} : row);
  const ladder = (obj.ladder || []).map(row => ['tests_collect', 'tests_pass', 'fast_suite'].includes(row.rung)
    ? {...row, status: row.rung === 'tests_pass' && !unavailable && probe.exit_code != null && probe.exit_code !== 0
      ? 'not_achieved' : 'unknown'} : row);
  return {...obj, objectives, ladder, next_rung: ladder.find(row => row.status !== 'achieved')?.rung || null};
}
// The test rungs of a code object's ladder from the latest recorded test run, whatever ran it (the server names the run and
// its time on each rung). Without them (an older answer, or no run recorded) the map's own scoped ladder stays.
export function withOverlay(obj, ladders) {
  const scoped = scopedObject(obj), overlay = ladders && ladders[obj.name];
  if (!overlay) return scoped;
  const ladder = (scoped.ladder || []).map((r) => (overlay[r.rung] ? { ...r, status: overlay[r.rung].status, evidence: overlay[r.rung] } : r));
  return { ...scoped, ladder, next_rung: ladder.find((r) => r.status !== 'achieved')?.rung || null, _overlaid: true };
}
