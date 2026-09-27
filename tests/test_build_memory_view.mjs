// No server or resident Studio: exercise the actual view renderer with a tiny DOM stand-in.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../runesmith/app/static/js/views/work.js', import.meta.url), 'utf8');
const view = source.slice(source.indexOf('function drawMemory('), source.indexOf('async function applyDraft('));
assert(view.startsWith('function drawMemory('));
function element(tag, ...children) {
  return { tag, children: children.flat(Infinity), append(...more) { this.children.push(...more.flat(Infinity)); } };
}
function text(node) {
  if (node == null) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  return (node.children || []).map(text).join('\n');
}
const context = vm.createContext({ h: element, icon: () => '', humanize: s => s.replaceAll('_', ' '),
  ago: s => s, empty: (...children) => element('empty', ...children) });
vm.runInContext(view, context);
const example = { id: 'mem-123', kind: 'episode', text: 'Public historical feedback only',
  source: { outcome: 'acceptance_passed', draft: 'draft-1', observed_utc: '2026-09-26T20:00:00Z' },
  selection: { reason: 'same_milestone', earlier_distinct_observations: 2 } };
let body = element('body');
context.drawMemory(body, { build_memory: { total: 1, items: [example], working_set: {
  milestone: { title: 'CLI exporter' }, items: [example], limit: 3, preview_only: true } } });
let rendered = text(body);
for (const expected of ['Next author memory preview', 'CLI exporter', '1 / 3 context slots',
  'same milestone', '2 earlier distinct', 'Read-only preview', 'latest verification receipt',
  'Public historical feedback only', 'not the current project verdict']) assert(rendered.includes(expected), expected);
assert(body.children.some(node => node?.tag === 'div.card.mt-16'));

body = element('body');
context.drawMemory(body, { build_memory: { total: 0, items: [], working_set: {
  milestone: null, items: [], limit: 3, preview_only: true } } });
rendered = text(body);
assert(rendered.includes('No ready milestone'));
assert(rendered.includes('No build observations yet'));

body = element('body');
context.drawMemory(body, { build_memory: { total: 0, items: [], working_set: {
  milestone: { title: 'Empty context' }, items: [], limit: 3, preview_only: true } } });
assert(text(body).includes('No matching build observations'));
console.log('Build memory actual-renderer smoke: 3 cases passed (no browser or Studio).');
