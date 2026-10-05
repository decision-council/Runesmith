// Helper of tests/test_map_layout.py (not a test on its own): runs the Living map's pure layout (map-layout.js) on the structure and
// plan answers the Python builders made, and prints plain numbers as JSON, so the geometry can be checked without a browser.
//
//   node tests/map_layout_dump.mjs OUT.json IN.json
//
// IN.json is {name: {structure: <GET /api/map/structure answer>} | {plan: <plan graph>}}. Each entry is laid out twice: as given,
// and with its lists shuffled (a fixed shuffle), so the test can check that no position depends on the order of a list.
import { readFileSync, writeFileSync } from 'node:fs';
import * as L from '../runesmith/app/static/js/views/map-layout.js';

const [out, input] = process.argv.slice(2);
const cases = JSON.parse(readFileSync(input, 'utf8'));

const shuffle = (list) => {                                  // a fixed pseudo-random shuffle: the same every run
  const a = [...list];
  let seed = 12345;
  for (let i = a.length - 1; i > 0; i--) { seed = (seed * 1103515245 + 12345) % 2147483648; const j = seed % (i + 1); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
};
const round = (x) => Math.round(x * 1000) / 1000;
const rounded = (value) => JSON.parse(JSON.stringify(value, (k, v) => (typeof v === 'number' ? round(v) : v)));

function dumpStructure(st) {
  const lay = L.structureLayout(st);
  return rounded({
    order: lay.order,
    sectors: lay.sectors.map((s) => ({ id: s.id, cat: s.cat, home: s.home, a0: s.a0, a1: s.a1, rIn: s.rIn, rOut: s.rOut, regions: s.regions })),
    points: [...lay.points].map(([id, p]) => ({ id, ...p })),
    boxes: lay.boxes,
    labels: lay.labels.map((l) => ({ gid: l.gid, text: l.text, sub: l.sub, anchor: l.anchor, size: l.size, box: l.box, radius: l.radius })),
    edges: lay.edges.map((e) => ({ from: e.from, to: e.to, type: e.type, bad: e.bad, d: e.d, samples: L.samplePath(e.d, 48) })),
    bounds: lay.bounds, ring: lay.ring, hub: { x: L.HUB_X, y: L.HUB_Y },
    radii: Object.fromEntries([0, 1, 2, 9, 10, 99, 100, 999, 1000, 2999, 3000, 3162, 10000, 1e6].map((n) => [n, L.radiusOf(n)])),
  });
}

// the path of a plan link is lines and quadratic or cubic curves: sample it into points
function planSamples(d) {
  const points = [];
  let x = 0, y = 0;
  for (const m of d.matchAll(/([MHVQCL])([^MHVQCL]*)/g)) {
    const n = (m[2].match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
    const seg = (fn) => { for (let i = 1; i <= 16; i++) points.push(fn(i / 16)); };
    if (m[1] === 'M') { [x, y] = n; points.push({ x, y }); }
    else if (m[1] === 'H') { const x0 = x; x = n[0]; seg((t) => ({ x: x0 + (x - x0) * t, y })); }
    else if (m[1] === 'V') { const y0 = y; y = n[0]; seg((t) => ({ x, y: y0 + (y - y0) * t })); }
    else if (m[1] === 'L') { const [x0, y0] = [x, y]; [x, y] = n; seg((t) => ({ x: x0 + (x - x0) * t, y: y0 + (y - y0) * t })); }
    else if (m[1] === 'Q') { const [x0, y0] = [x, y]; seg((t) => { const u = 1 - t; return { x: u * u * x0 + 2 * u * t * n[0] + t * t * n[2], y: u * u * y0 + 2 * u * t * n[1] + t * t * n[3] }; }); [x, y] = [n[2], n[3]]; }
    else if (m[1] === 'C') { const [x0, y0] = [x, y]; seg((t) => { const u = 1 - t; return { x: u ** 3 * x0 + 3 * u * u * t * n[0] + 3 * u * t * t * n[2] + t ** 3 * n[4], y: u ** 3 * y0 + 3 * u * u * t * n[1] + 3 * u * t * t * n[3] + t ** 3 * n[5] }; }); [x, y] = [n[4], n[5]]; }
  }
  return points;
}

function dumpPlan(graph) {
  const shown = new Set(graph.nodes.filter((n) => n.drawn).map((n) => n.id));
  const lay = L.planLayout(graph, shown, new Set());
  return rounded({
    columns: lay.columns, W: lay.W, H: lay.H, box: { w: L.PLAN.BOX_W, h: L.PLAN.BOX_H, col: L.PLAN.COL, pad: L.PLAN.PAD },
    nodes: [...lay.pos].map(([id, p]) => ({ id, x: p.x, y: p.y, row: p.row, col: p.col, track: graph.nodes.find((n) => n.id === id).track, state: graph.nodes.find((n) => n.id === id).state })),
    lanes: lay.lanes.map((l) => ({ track: l.t.name, y: l.y, hgt: l.hgt, rows: l.rows })),
    edges: lay.edges.map((e) => ({ from: e.from, to: e.to, route: e.route, d: e.d, samples: planSamples(e.d) })),
  });
}

const result = {};
for (const [name, entry] of Object.entries(cases)) {
  if (entry.structure) {
    const st = entry.structure;
    const shuffled = { ...st, nodes: shuffle(st.nodes), groups: shuffle(st.groups), edges: shuffle(st.edges) };
    result[name] = { kind: 'structure', layout: dumpStructure(st), again: dumpStructure(JSON.parse(JSON.stringify(st))), shuffled: dumpStructure(shuffled) };
  } else {
    const g = entry.plan;
    const shuffled = { ...g, edges: shuffle(g.edges) };                 // the plan's own order is meaningful (it breaks ties); its edge list is not
    result[name] = { kind: 'plan', layout: dumpPlan(g), again: dumpPlan(JSON.parse(JSON.stringify(g))), shuffled: dumpPlan(shuffled) };
  }
}
writeFileSync(out, JSON.stringify(result));
