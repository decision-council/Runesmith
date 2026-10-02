// Recovery is a review of retained intentions, never a generic retry button.
import {h, icon, clear, post, get, withBusy, toast} from './core.js';

// What the owner was doing, in their words (journey J4-F11: the detail below is exact but written for engineers).
const DOING = {propose_acceptance: 'proposing acceptance checks', plan: 'drafting a plan', goalposts: 'proposing goalposts',
  draft: 'drafting files', build: 'building the next step', revise: 'revising a draft', correct: 'correcting a draft',
  escalate: 'asking a stronger model', supplement: 'asking for missing files', breakdown: 'proposing smaller steps',
  map: 'mapping the folder', round: 'running a round', measure: 'taking a measurement', review_current: 'checking the current files'};
// Jobs that never write into the owner's folder: only for these may the summary say that nothing there changed.
const NO_FOLDER_WRITES = new Set(['propose_acceptance', 'plan', 'goalposts', 'draft', 'breakdown', 'split', 'map', 'measure', 'review_current']);

export function plainSummary(recovery) {
  const kind = recovery.interrupted;
  const doing = kind ? (DOING[kind] || kind.replace(/_/g, ' ')) : 'working';
  const waiting = recovery.relay_set_aside ? ', waiting for your chat window' : '';
  const files = kind && NO_FOLDER_WRITES.has(kind) ? ' It changes no file in your folder, so nothing there was touched.'
    : kind ? ' If it was writing a checked draft, Work & proposals shows what was written, with Undo.' : '';
  const request = recovery.relay_set_aside ? ' The request it waited on was set aside; ask again when you are ready.' : '';
  return `In short: Runesmith was restarted while ${doing}${waiting}. Nothing was repeated or sent twice.${files}${request} ` +
    'To carry on, tick the box below, choose “Keep waiting jobs”, then Resume.';
}

export function recoveryPanel(onState) {
  const root = h('section.card.hidden', {'aria-label': 'Restart recovery', style:{marginBottom:'16px'}});
  let signature = '', saving = false;
  function update(worker) {
    const recovery = worker.recovery;
    if (!recovery) { clear(root); root.classList.add('hidden'); signature = ''; return; }
    const next = JSON.stringify([recovery, worker.queue]);
    if (next === signature) return;
    signature = next;
    clear(root); root.classList.remove('hidden');
    root.append(h('div.card-head', h('h3', icon('shield'), 'Restart recovery'), h('span.badge.warn', 'Held · nothing replayed')),
      h('p', plainSummary(recovery)),
      h('p.small', 'Review saved outcomes in Jobs and Work & proposals before continuing. An interrupted author call may already have been processed; retrieve its saved response instead of submitting it again. Spent check allocations remain spent.'),
      h('ul.small.muted', (recovery.reasons || []).map(reason => h('li', reason))),
      h('p.small', `${(worker.queue || []).length} waiting intention(s) retained. Interrupted jobs are recorded in history, never restored to this queue.`));
    for (const job of worker.queue || []) {
      root.append(h('details', h('summary.small', `${job.kind} · ${job.id}`),
        h('pre.small', {style:{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}, JSON.stringify(job.params || {}, null, 2))));
    }
    if (recovery.blocked) {
      root.append(h('p.callout.warn.small', recovery.error || 'Control records need repair before review can be recorded.'),
        h('p.small.muted', 'The original records are preserved. Resume and recovery acknowledgement are unavailable; repair or reconcile the records and reopen Studio.'));
      return;
    }
    const checked = h('input', {type:'checkbox', style:{flexShrink:'0',marginTop:'3px'}});
    const keep = h('button.btn.sm', {disabled:true}, 'Keep waiting jobs · stay paused');
    const park = h('button.btn.sm', {disabled:true}, 'Set aside waiting jobs · stay paused');
    const enable = () => { keep.disabled = park.disabled = saving || !checked.checked; };
    checked.addEventListener('change', enable);
    root.append(h('label.small', {style:{display:'flex',alignItems:'flex-start',gap:'10px',marginTop:'8px'}}, checked,
        h('span', 'I have reviewed the saved outcomes and the waiting intentions.')),
      h('p.small.faint', 'Review is not proof of completion. Both choices keep the queue paused; Resume can start queued or scheduled work. Set-aside intentions remain in a receipt. Remote calls and spent allocations are unchanged.'),
      h('div', {style:{display:'flex',flexWrap:'wrap',gap:'8px'}}, keep, park));
    const save = async (button, decision) => {
      if (saving || !checked.checked) return;
      saving = true; enable();
      try {
        await withBusy(button, async () => {
          const state = await post('/api/worker/recovery', {revision:recovery.revision, decision, reviewed:true});
          onState(state);
          toast('Review recorded. The queue is still paused; no work was run.', 'good');
        });
      } finally { saving = false; enable(); }
    };
    keep.addEventListener('click', () => save(keep, 'keep'));
    park.addEventListener('click', () => save(park, 'park'));
    const refresh = h('button.btn.sm', 'Refresh recovery status');
    refresh.addEventListener('click', () => withBusy(refresh, async () => onState(await get('/api/worker'))));
    root.append(h('div.mt-8', refresh));
  }
  return {root, update};
}
