// Notes: every comment the owner made, on anything, and whether a model reads it.
import { h, icon, get, post, bus, clear, ago, openNotes, empty, debounce, humanize } from '../core.js';

const FILTERS = [['open', 'Open'], ['resolved', 'Resolved'], ['all', 'All']];
const TYPE_ICON = { workspace: 'home', object: 'grid', objective: 'gauge', rung: 'layers', proposal: 'check', draft: 'filePlus', generation: 'branch',
  goal: 'target', milestone: 'flag', instrument: 'cpu', capability: 'gauge', component: 'rune', self: 'rune', plan: 'route', brief: 'book', session: 'hammer', trial: 'scale' };

export default async function render(root, ctx) {
  const offs = [];
  let filter = 'open';
  const head = h('div.page-head', h('div', h('h2', 'Notes'),
    h('p', 'You can comment on anything in the Studio: a folder, a rung, a fix, a model, Runesmith itself. Press C, or use the speech-bubble button that appears when you hover. Open notes travel to the model that works on that thing, clearly labelled as your guidance.')),
    h('div.actions', h('button.btn.primary', { onclick: () => openNotes('workspace', 'root', 'the whole workspace') }, icon('note'), 'Note on the whole workspace')));
  const seg = h('div.seg');
  const list = h('div.col.gap-16');
  root.append(head, h('div.row.mb-8', seg), list);
  const load = async () => {
    const data = await get('/api/notes');
    clear(seg).append(...FILTERS.map(([k, l]) => h('button', { class: k === filter ? 'on' : '', onclick: () => { filter = k; load(); } }, l)));
    const notes = data.notes.filter((n) => filter === 'all' || (filter === 'open' ? !n.resolved : !!n.resolved));
    clear(list);
    if (!data.read_notes) list.append(h('div.callout.warn', icon('eyeOff'), h('div', 'Models do not read notes at the moment (Settings → Give notes to the model).')));
    if (!notes.length) { list.append(empty('note', filter === 'open' ? 'No open notes' : 'Nothing here', 'Hover over anything and click the speech bubble, or press C and click what you want to talk about.')); return; }
    const groups = new Map();
    for (const n of notes) { const k = `${n.target.type}|${n.target.id}`; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(n); }
    for (const [k, rows] of groups) {
      const t = rows[0].target;
      const card = h('div.card.hoverable', { onclick: () => openNotes(t.type, t.id, t.label || t.id) },
        h('div.card-head', h('div.ico', icon(TYPE_ICON[t.type] || 'note')), h('div.grow', h('h3', t.label || t.id), h('div.small.faint', humanize(t.type))),
          h('span.badge', `${rows.length} note${rows.length > 1 ? 's' : ''}`)),
        h('div.col.gap-6', rows.slice(0, 3).map((n) => h('div', { class: `note${n.resolved ? ' resolved' : ''}` }, h('div.who', icon('user'), 'You', h('span', '·'), ago(n.utc)), h('div.text', n.text)))),
        rows.length > 3 ? h('p.small.faint', `and ${rows.length - 3} more…`) : null);
      list.append(card);
    }
  };
  await load();
  offs.push(bus.on('notes', debounce(load, 250)));
  return () => offs.forEach((f) => f());
}
