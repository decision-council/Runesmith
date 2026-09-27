// Recovery is a review of retained intentions, never a generic retry button.
import {h, icon, clear, post, get, withBusy, toast} from './core.js';

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
