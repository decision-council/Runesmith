// No server or resident Studio: the Overview's free-key card, the hero's latest failure and the model row's words, with a tiny
// DOM stand-in. One free Google key: which model answers, how much of its day is used, who waits for its midnight.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const home = readFileSync(new URL('../runesmith/app/static/js/views/home.js', import.meta.url), 'utf8');
const inference = readFileSync(new URL('../runesmith/app/static/js/views/inference.js', import.meta.url), 'utf8');
const slice = (source, from, to) => {
  const start = source.indexOf(from), end = source.indexOf(to, start);
  assert(start >= 0 && end > start, from);
  return source.slice(start, end);
};
const view = [slice(home, 'const MODEL_JOBS', '// A long error cut for the Overview'),
  slice(home, 'function pacingCard(', 'function drawFix('), slice(inference, 'function removeWords(', '// What the last test said')].join('\n');

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
const navigations = [], emitted = [];
const context = vm.createContext({ h, icon: () => '', navigate: null, bus: { emit: (...a) => emitted.push(a) }, setTimeout: (f) => f() });
vm.runInContext(view, context);

// ---- the hero: the latest job that asked a model, not the latest build (a plan, checks, a build), and its plain words
const raw = "role 'plan': no response after 3 attempts; last: http_503 \"[{'error': {'code': 503, 'message': 'This model is currently experiencing high demand.";
const history = [
  { kind: 'propose_acceptance', result: 'failed', finished: '2026-10-05T09:08:02Z', outcome: { error: 'no acceptance checks: Google Gemini (gemini-3.8-flash) has used up its free allowance for today.' } },
  { kind: 'round', result: 'done', finished: '2026-10-05T09:07:00Z', outcome: {} },
  { kind: 'propose_acceptance', result: 'failed', finished: '2026-10-05T09:04:42Z', outcome: { error: 'no acceptance checks: the model is busy' } },
  { kind: 'build', result: 'failed', finished: '2026-10-05T07:10:22Z', outcome: { error: raw } },
];
assert.equal(context.latestModelJob(history).finished, '2026-10-05T09:08:02Z');                // not the build from hours ago
assert.equal(context.latestModelJob([{ kind: 'round', result: 'done' }, { kind: 'plan', result: 'skipped' }]), undefined);
assert.equal(context.latestModelJob([{ kind: 'build', result: 'done', finished: 'newer' }, history[3]]).finished, 'newer');   // a later success is the latest
const plain = context.plainFailure(history[3].outcome.error);                                  // an old raw text is told plainly here too
assert(/busy/.test(plain) && !/http_|\{|attempts/.test(plain), plain);
assert(/free limit/.test(context.plainFailure('http_429 {"error": "quota"}')));
assert.equal(context.plainFailure('the model is busy: try again'), 'the model is busy: try again');
assert.equal(context.plainFailure(undefined), 'see Activity');

// ---- the card: three free Gemini models on one key, the first used up
const used = (n, cap = 20) => ({ count: n, cap, learned: true, words: `about ${n} of ${cap} used today` });
const pacing = {
  limited: [{ name: 'gemini', label: 'Google Gemini (gemini-3.8-flash)', until_clock: '02:00', daily: true, said: 'Quota exceeded ... limit: 20',
    words: 'Google Gemini (gemini-3.8-flash) has used up its free allowance for today (about 20 of 20 used today). Runesmith will not ask it again before about 02:00 (about 15 hours from now), so no more of the allowance is spent.' }],
  limited_summary: 'Google Gemini (gemini-3.8-flash) has used up its free allowance for today (about 20 of 20 used today). Runesmith will not ask it again before about 02:00 (about 15 hours from now), so no more of the allowance is spent.',
  waiting: false, only_provider_limited: false,
  answering: { plan: { name: 'gemini-3.7-flash', label: 'Google Gemini (gemini-3.7-flash)', model: 'gemini-3.7-flash' } },
  free_keys: [
    { name: 'gemini', label: 'Google Gemini (gemini-3.8-flash)', model: 'gemini-3.8-flash', answering: [], held: true, until_clock: '02:00', used: used(20) },
    { name: 'gemini-3.7-flash', label: 'Google Gemini (gemini-3.7-flash)', model: 'gemini-3.7-flash', answering: ['repair', 'plan', 'acceptance'], held: false, used: used(3) },
    { name: 'gemini-3.5-flash-lite', label: 'Google Gemini (gemini-3.5-flash-lite)', model: 'gemini-3.5-flash-lite', answering: [], held: false, used: used(0) }],
  guide_words: 'Chapter 4 of the guide', guide_url: '',
};
const card = context.pacingCard({ pacing }, (to) => navigations.push(to));
const shown = text(card);
for (const expected of ['Free thinking power today', 'answering now: gemini-3.7-flash', 'has used up its free allowance for today',
  'Work goes on with Google Gemini (gemini-3.7-flash)', 'used up for today: asked again after about 02:00', 'about 20 of 20 used today',
  'answering now · about 3 of 20 used today', 'next in line · about 0 of 20 used today']) assert(shown.includes(expected), expected);
assert(!/Waiting for a free limit|null|undefined/.test(shown), shown);
assert.equal(find(card, (n) => n.props && 'data-free-key' in n.props).length, 3);
assert.equal(find(card, (n) => n.tag === 'button.btn.primary').length, 0, 'a second provider is not pushed while a model answers');

// every model held back, one provider: the card waits, and says what to do
const waiting = context.pacingCard({ pacing: { ...pacing, waiting: true, only_provider_limited: true, answering: {},
  free_keys: pacing.free_keys.map((k) => ({ ...k, held: true, answering: [] })) } }, (to) => navigations.push(to));
const waits = text(waiting);
for (const expected of ['Waiting for a free limit', 'no calls are made meanwhile', 'You have one provider', 'Groq', 'Add a second free provider',
  'Chapter 4 of the guide']) assert(waits.includes(expected), expected);
await find(waiting, (n) => n.tag === 'button.btn.primary')[0].props.onclick();
assert.deepEqual(navigations, ['inference']);
assert.equal(emitted[0][0], 'ui:add-model');

// nothing to say: no card (a key never used and nothing held)
assert.equal(context.pacingCard({ pacing: { limited: [], free_keys: [{ ...pacing.free_keys[2] }], waiting: false } }, () => {}), null);
assert.equal(context.pacingCard({}, () => {}), null);

// ---- the model row: removing one model of a chain keeps the key for the others
assert(context.removeWords({ shares_key_with: ['gemini-3.7-flash', 'gemini-3.5-flash-lite'] }).includes('The saved key stays'));
assert(context.removeWords({ shares_key_with: ['gemini'] }).includes('still uses it'));
assert.equal(context.removeWords({ shares_key_with: [] }), 'Its saved key is deleted too.');
console.log('free quota view: ok');
