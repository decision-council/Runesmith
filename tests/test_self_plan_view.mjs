// No server or resident Studio: exercise the Self-improvement page's plan card with a tiny DOM stand-in.
// The card shows the map's summary, the owner's share, the scored plan (the top ten), the next item and why (with the
// struggle it is linked to), the struggles, and how the score is worked out.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../runesmith/app/static/js/views/improve.js', import.meta.url), 'utf8');
const view = source.slice(source.indexOf('function selfPlanCard('), source.indexOf('export default async function render('));
assert(view.startsWith('function selfPlanCard('));

function h(tag, ...rest) {
  let props = {};
  if (rest[0] && typeof rest[0] === 'object' && !Array.isArray(rest[0]) && !('children' in rest[0])) props = rest.shift();
  return { tag, props, children: rest.flat(Infinity).filter((x) => x != null) };
}
const text = (node) => node == null ? '' : typeof node !== 'object' ? String(node) : (node.children || []).map(text).join(' ');
const find = (node, test, out = []) => {
  if (node && typeof node === 'object') { if (test(node)) out.push(node); (node.children || []).forEach((c) => find(c, test, out)); }
  return out;
};

const navigations = [];
const context = vm.createContext({
  h, icon: () => '', plural: (n, one, many) => `${n} ${n === 1 ? one : many || one + 's'}`,
  humanize: (s) => String(s || '').replace(/_/g, ' '),
});
vm.runInContext(view, context);

const struggle = { id: 'mf5efcd|no_author_allowance', scope: 'milestone', milestone: 'mf5efcd',
  milestone_title: 'Convert motion.mjs to module-compatible engine', signature: 'no_author_allowance',
  words: 'no author try is left to fund the next attempt', count: 24, since: '2026-10-04T20:22:00Z', current: true };
const plan = {
  kaizen_on: true, share: 20, sentence: '2 of every 10 work turns go to improving Runesmith itself', turns: 3, next_self_turn_in: 2,
  map: { version: '0.9.0', generation: 'gen-1', components: 90, bands: { repair_yield: 'minimal' }, targets: 2, struggles: 3,
    current_struggles: 2, unknowns: 2 },
  struggles: [struggle, { ...struggle, id: 'project|answer_truncated', scope: 'project', milestone: null, milestone_title: null,
    signature: 'answer_truncated', words: 'the author’s answers are cut off', count: 4, current: false }],
  items: [
    { id: 'fresh_try_after_one_more_try', title: 'A fresh ordinary try after the one more try fails', kind: 'struggle',
      what: 'Fund a new ordinary attempt.', score: { total: 80, benefit: 60, recency: 20, gate: 0 },
      reason: 'No author try is left on “Convert motion.mjs”: 24 time(s). No trial gate exists for this kind of change yet, so it stays a plan.',
      gate: null, struggles: [struggle.id], priority: true, status: 'planned: needs a gate' },
    { id: 'kaizen:yield:budget_exhausted', title: 'Repair organ: fewer “budget exhausted” failures', kind: 'kaizen_target',
      what: 'A Kaizen campaign.', score: { total: 60, benefit: 40, recency: 0, gate: 20 }, rank: 1,
      reason: '40% of the repairs it could not make ended as “budget exhausted”.', gate: 'online trial of the repair organ',
      struggles: [], status: 'waits: no Improver model is set up' },
  ],
  next: { action: 'plan', item: 'fresh_try_after_one_more_try', title: 'A fresh ordinary try after the one more try fails',
    mode: 'struggle', struggle: struggle.id,
    why: '“Convert motion.mjs to module-compatible engine” is struggling now, so the best-scored improvement linked to it comes first.' },
  blockers: ['no Improver model is set up'],
  rule: { score: 'benefit + recency + gate; whole numbers; ties by id', benefit: 'by count', recency: 'by age', gate: '20 when a gate exists',
    turns: 'the owner’s share of every 10 work turns', priority: 'a struggle comes first' },
  history: [],
};

assert.equal(context.selfPlanCard(null, () => {}), null);                      // no plan yet: no card

const card = context.selfPlanCard(plan, (to) => navigations.push(to));
const rendered = text(card);
for (const expected of ['Improvement plan', 'self-improvement on', '90 components', '3 struggles seen in the work (2 now)',
  'repair yield: minimal', 'Self-improvement share: 20%', '2 of every 10 work turns go to improving Runesmith itself',
  '2 work turns from now', 'Next: A fresh ordinary try after the one more try fails', 'is struggling now',
  'the next item answers this',
  'A campaign on the repair organ cannot start now: no Improver model is set up', 'The plan, first item first',
  '1. A fresh ordinary try after the one more try fails', 'score 80', 'planned: needs a gate',
  '2. Repair organ: fewer “budget exhausted” failures', 'score 60', 'waits: no Improver model is set up',
  'answers a struggle', 'Where the work struggles', '24 times since 2026-10-04 20:22Z', 'struggling now', 'The project: the author’s answers are cut off',
  'How the score is worked out', 'benefit + recency + gate', 'a struggle comes first', 'needs a gate']) {
  assert(rendered.includes(expected), expected);
}
assert(!/null|undefined/.test(rendered));
const rows = find(card, (n) => n.props && n.props['data-item']);
assert.deepEqual(rows.map((r) => r.props['data-item']), ['fresh_try_after_one_more_try', 'kaizen:yield:budget_exhausted']);
assert.equal(find(card, (n) => n.props && n.props['data-struggle']).length, 2);
const scoreBadge = find(card, (n) => n.props && String(n.props.title || '').startsWith('benefit 60'));
assert.equal(scoreBadge.length, 1);                                              // the breakdown is there for whoever hovers
find(card, (n) => n.tag === 'button.btn.sm')[0].props.onclick();
assert.deepEqual(navigations, ['settings']);                                     // the share is one click away

// Self-improvement off, nothing yet, nothing that can run: the card still says what is true.
const off = context.selfPlanCard({ ...plan, kaizen_on: false, items: [], struggles: [], blockers: [],
  next: { action: 'none', item: null, title: null, why: 'Nothing can run now.', struggle: null }, next_self_turn_in: 1 }, () => {});
const offText = text(off);
for (const expected of ['self-improvement off', 'Self-improvement is off in Settings, so none will run.', 'the very next work turn',
  'Nothing can run at the next self-improvement turn.', 'No item yet']) assert(offText.includes(expected), expected);
assert(!offText.includes('Where the work struggles') && !/null|undefined/.test(offText));
console.log('self-improvement view: ok');
