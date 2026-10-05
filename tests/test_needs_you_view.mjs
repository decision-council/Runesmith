// No server or resident Studio: exercise the Overview's "Needs you" card with a tiny DOM stand-in.
// A stuck milestone nothing more is tried for by itself is shown with what is stuck, why, and the owner's choices.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../runesmith/app/static/js/views/home.js', import.meta.url), 'utf8');
const view = source.slice(source.indexOf('function needsYouCard('), source.indexOf('function numbersCard('));
assert(view.startsWith('function needsYouCard('));

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

const same = (a, b) => assert.equal(JSON.stringify(a), JSON.stringify(b));      // objects from the vm realm differ in prototype
const calls = [], toasts = [], navigations = [];
let redrawn = 0, confirmed = true;
const context = vm.createContext({
  h, icon: () => '', plural: (n, one, many) => `${n} ${n === 1 ? one : many || one + 's'}`,
  withBusy: async (button, fn) => fn(),
  post: async (path, body) => { calls.push([path, body]); return {}; },
  toast: (message, kind) => toasts.push([message, kind]),
  confirmDialog: async () => confirmed,
});
vm.runInContext(view, context);

const row = {
  milestone: 'm1', title: 'One engine for every page', utc: '2026-10-04T20:20:00Z', kind: 'spent', code: 'refused',
  what: '“One engine for every page” cannot go on by itself: its three tries and its one more try are used up on the files as they are now. Runesmith asked a model for smaller steps by your setting, but its answer could not be used (a breakdown needs 2-4 steps).',
  choices: [{ id: 'breakdown', label: 'Ask for smaller steps again', detail: 'One request to a model.' },
            { id: 'edit', label: 'Edit the milestone', detail: 'New wording gives it fresh tries.' },
            { id: 'set_aside', label: 'Set it aside', detail: 'The plan goes on without it.' }],
};

assert.equal(context.needsYouCard({ needs_you: [] }, () => {}, () => {}), null);          // nothing stuck: no card
assert.equal(context.needsYouCard({}, () => {}, () => {}), null);

const card = context.needsYouCard({ needs_you: [row] }, (to) => navigations.push(to), () => { redrawn += 1; });
const rendered = text(card);
for (const expected of ['Needs you', '1 milestone', 'One engine for every page', 'its one more try are used up',
  'could not be used', 'Ask for smaller steps again', 'Edit the milestone', 'Set it aside']) assert(rendered.includes(expected), expected);
assert(!/null|undefined/.test(rendered));
const buttons = find(card, (n) => n.props && n.props['data-choice']);
same(buttons.map((b) => b.props['data-choice']), ['breakdown', 'edit', 'set_aside']);
assert(buttons[0].tag.includes('primary'), 'the first choice is the suggested one');
const click = (id) => buttons.find((b) => b.props['data-choice'] === id).props.onclick({ currentTarget: {} });

await click('breakdown');
same(calls.at(-1), ['/api/worker/run', { job: 'breakdown', params: { milestone: 'm1' } }]);
await click('edit');
same(navigations, ['goals']);
await click('set_aside');                                                    // confirmed: dropped, and the page is redrawn
same(calls.at(-1), ['/api/plan/milestones/m1', { status: 'dropped' }]);
assert.equal(redrawn, 1);
confirmed = false;
const before = calls.length;
await click('set_aside');                                                    // not confirmed: nothing is sent
assert.equal(calls.length, before);

// Several stuck milestones, one card; the one more try is offered as a choice of its own.
const two = context.needsYouCard({ needs_you: [row, { ...row, milestone: 'm2', title: 'Second',
  choices: [{ id: 'escalate', label: 'Try once more with another model' }, { id: 'edit', label: 'Edit the milestone' }] }] },
  () => {}, () => {});
assert(text(two).includes('2 milestones'));
const retry = find(two, (n) => n.props && n.props['data-choice'] === 'escalate')[0];
await retry.props.onclick({ currentTarget: {} });
same(calls.at(-1), ['/api/worker/run', { job: 'escalate' }]);

// A one more try that was interrupted and that Runesmith could not settle: plain words and a one-click "Close the interrupted call".
const interrupted = { milestone: 'm3', title: 'Styles for the page', utc: '2026-10-05T00:27:00Z', kind: 'interrupted', code: 'interrupted',
  receipt: 'e355ea61a7ec2',
  what: '“Styles for the page” cannot go on by itself: its one more try, with another model, was interrupted (the Studio was closed or stopped while it worked), and what is saved does not say how it ended.',
  choices: [{ id: 'close_interrupted', label: 'Close the interrupted call', detail: 'Counts its one more try as used and sends nothing.' },
            { id: 'edit', label: 'Edit the milestone', detail: 'New wording gives it fresh tries.' },
            { id: 'set_aside', label: 'Set it aside', detail: 'The plan goes on without it.' }] };
const cut = context.needsYouCard({ needs_you: [interrupted] }, () => {}, () => { redrawn += 1; });
for (const expected of ['Styles for the page', 'was interrupted', 'Close the interrupted call']) assert(text(cut).includes(expected), expected);
assert(!/null|undefined/.test(text(cut)));
const redrawnBefore = redrawn;
await find(cut, (n) => n.props && n.props['data-choice'] === 'close_interrupted')[0].props.onclick({ currentTarget: {} });
same(calls.at(-1), ['/api/build/escalations/e355ea61a7ec2/close', {}]);
assert.equal(redrawn, redrawnBefore + 1, 'the card is redrawn once the call is closed');
console.log('needs-you view: ok');
