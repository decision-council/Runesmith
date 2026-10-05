// The Living map's geometry, with no DOM and nothing random or measured (docs/MAP_LOGIC.md, "Layout"): where every part of the
// structure drawing and of the plan graph sits, and why. The same structure always gives the same drawing, whatever order the
// answer listed its parts in. Text widths are estimated (a generous per-letter width), so a drawing never depends on a font.

export const WIDE = 1.5;                    // the drawing is an ellipse, wider than tall, like the canvas
export const SECTOR_GAP = 0.05;             // radians between two sectors
export const SUB_GAP = 0.02;                // radians between two folders inside one sector
export const HUB_X = 94, HUB_Y = 94;        // links keep out of this box around the hub (the hub is 66 across, its halo 86)
export const OTHER = '(other folders)';
export const NODE_LABEL_CHARS = 16;
export const SIZE_NOTE = 'size: lines of code, on a log scale, clamped (the largest from about 3,000 lines)';

const CAT_OF = { module: 'source', test: 'tests', doc: 'docs', config: 'config', data: 'data' };
const CAT_ORDER = ['source', 'tests', 'docs', 'config', 'data'];
const KIND_RANK = { module: 0, test: 1, doc: 2, config: 3, data: 4, more: 5 };
const MORE_R = 15;
const HUB_BOX = { x0: -88, x1: 88, y0: -88, y1: 88 };
const TAU = Math.PI * 2;

const byId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

/** Radius of a part: it grows with its lines, on a log scale, clamped to 8 to 24. */
export const radiusOf = (lines) => (lines == null ? 10 : Math.max(8, Math.min(24, 8 + 4.6 * Math.log10(1 + Math.max(0, lines)))));

/** A generous estimate of a text's width in pixels, from the kind of each letter (capitals and "m w _" are wide, "i l . t" narrow)
 *  and a margin for the font the system picks: measured in a browser, real text is 5 to 15 per cent narrower than this. */
const WIDE_LETTER = /[A-Z0-9@#%&mwMW_]/, NARROW_LETTER = /[ilj.,:;'!|ft1 \-]/;
export const textWidth = (s, size = 10, bold = false) => {
  let units = 0;
  for (const ch of String(s)) units += WIDE_LETTER.test(ch) ? 0.68 : NARROW_LETTER.test(ch) ? 0.38 : 0.56;
  return Math.ceil(units * size * (bold ? 1.1 : 1) * 1.04) + 3;
};

/** A name cut in the middle, so both its beginning and its end (the extension) stay: ``test_app_en…long_name.py``. */
export function midTrunc(s, max) {
  const text = String(s ?? '');
  if (text.length <= max) return text;
  if (max < 5) return text.slice(0, max - 1) + '…';
  const tail = Math.min(10, Math.floor((max - 1) / 2)), head = max - 1 - tail;
  return text.slice(0, head) + '…' + text.slice(text.length - tail);
}

/** A folder path cut in the middle but keeping its last folder. */
export function pathTrunc(path, max) {
  if (path.length <= max) return path;
  const parts = path.split('/');
  const last = parts[parts.length - 1];
  if (parts.length > 1 && last.length + 2 <= max) return `${midTrunc(parts.slice(0, -1).join('/'), max - last.length - 1)}/${last}`;
  return midTrunc(path, max);
}

// ------------------------------------------------------------------------------------------------ the sectors --

const centrality = (n) => n.imported_by_count ?? (n.imported_by || []).length;

/** The main module a test file reaches: the one it is named for, then the one found by most reasons, then the first by path.
 *  Only modules that are drawn count. null when it reaches none. */
export function mainTargets(st, drawnIds) {
  const best = new Map();
  for (const e of [...st.edges].sort((a, b) => cmp(a.type + a.from + a.to, b.type + b.from + b.to))) {
    if (e.type !== 'tests' || !drawnIds.has(e.to)) continue;
    const named = (e.how || []).some((h) => String(h).startsWith('named for it')) ? 1 : 0;
    const key = [named, (e.how || []).length];
    const old = best.get(e.from);
    if (!old || key[0] > old.key[0] || (key[0] === old.key[0] && key[1] > old.key[1]) || (key[0] === old.key[0] && key[1] === old.key[1] && e.to < old.to)) best.set(e.from, { to: e.to, key });
  }
  return new Map([...best].map(([from, v]) => [from, v.to]));
}

/** The sectors in the fixed order, clockwise from 12 o'clock: source folders (the largest first), each followed by the tests
 *  folders that reach it most, then documents, configuration, data and other; "(other folders)" last. A folder inside a
 *  folder that is itself drawn is a sub-folder of that folder's sector (one level: deeper ones join the topmost). */
export function sectorPlan(st) {
  const nodes = [...st.nodes].sort(byId), groups = [...st.groups].sort(byId);
  const byGroup = new Map(groups.map((g) => [g.id, []]));
  for (const n of nodes) byGroup.get(n.group)?.push(n);
  const real = groups.filter((g) => g.id !== '' && g.id !== OTHER);
  const topOf = (g) => {
    if (g.id === '' || g.id === OTHER) return null;
    let best = null;
    for (const p of real) if (p.id !== g.id && g.id.startsWith(p.id + '/') && (!best || p.id.length < best.id.length)) best = p;
    return best;
  };
  const sectors = [];
  const sectorOfGroup = new Map();
  for (const g of groups) {
    if (topOf(g)) continue;
    const s = { id: g.id, own: g, subs: [], cat: 'data', files: g.files };
    sectors.push(s);
    sectorOfGroup.set(g.id, s);
  }
  for (const g of groups) {
    const top = topOf(g);
    if (top) { const s = sectorOfGroup.get(top.id); s.subs.push(g); sectorOfGroup.set(g.id, s); s.files += g.files; }
  }
  for (const s of sectors) {
    const counts = new Map();
    for (const g of [s.own, ...s.subs]) for (const n of byGroup.get(g.id) || []) counts.set(CAT_OF[n.kind] || 'data', (counts.get(CAT_OF[n.kind] || 'data') || 0) + 1);
    s.cat = CAT_ORDER.reduce((best, c) => ((counts.get(c) || 0) > (counts.get(best) || 0) ? c : best), 'data');
    if (!counts.size) s.cat = 'data';
    s.subs.sort(byId);
  }
  const drawn = new Set(nodes.filter((n) => n.drawn).map((n) => n.id));
  const main = mainTargets(st, drawn);
  const sectorOfNode = (id) => { const n = nodes.find((x) => x.id === id); return n ? sectorOfGroup.get(n.group) : null; };
  const size = (a, b) => b.files - a.files || cmp(a.id, b.id);
  const other = sectors.find((s) => s.id === OTHER) || null;
  const rest = sectors.filter((s) => s !== other);
  const kinds = (c) => rest.filter((s) => s.cat === c).sort(size);
  const sources = kinds('source'), tests = kinds('tests');
  const mainSeq = [...sources, ...kinds('docs'), ...kinds('config'), ...kinds('data')];
  const NONE = '\u0000none';
  const attached = new Map();
  for (const t of tests) {
    const votes = new Map();
    for (const n of nodes) {
      if (n.kind !== 'test' || sectorOfGroup.get(n.group) !== t || !main.has(n.id)) continue;
      const home = sectorOfNode(main.get(n.id));
      if (home && home !== t && mainSeq.includes(home)) votes.set(home.id, (votes.get(home.id) || 0) + 1);
    }
    const home = [...votes].sort((a, b) => b[1] - a[1] || size(sectors.find((s) => s.id === a[0]), sectors.find((s) => s.id === b[0])))[0];
    const key = home ? home[0] : NONE;
    if (!attached.has(key)) attached.set(key, []);
    attached.get(key).push(t);
    t.home = home ? home[0] : null;
  }
  const seq = [];
  const push = (s) => { seq.push(s); seq.push(...(attached.get(s.id) || [])); };
  sources.forEach(push);
  seq.push(...(attached.get(NONE) || []));
  [...kinds('docs'), ...kinds('config'), ...kinds('data')].forEach(push);
  if (other) seq.push(other);
  seq.forEach((s, i) => { s.index = i; });
  return { sectors: seq, byGroup, sectorOfGroup, main, drawn };
}

/** Every file of a folder in the order the list shows it: source files by how often they are imported, then the rest by name. */
export function listOrder(members) {
  return [...members].sort((a, b) => (KIND_RANK[a.kind] ?? 9) - (KIND_RANK[b.kind] ?? 9)
    || (a.kind === 'module' && b.kind === 'module' ? centrality(b) - centrality(a) : 0) || cmp(a.id, b.id));
}

// -------------------------------------------------------------------------------------------- the rings and slots --

/** The least angle between two parts on a ring of radius r at angle t so that their boxes (w wide, h tall) do not touch. */
const stepAt = (t, r, w, h) => Math.min(w / (r * WIDE * Math.max(Math.abs(Math.sin(t)), 0.1)), h / (r * Math.max(Math.abs(Math.cos(t)), 0.1)));

/** How many parts fit on the ring between a0 and a1, and their angles (spread evenly over the room there is). */
function ringSlots(r, a0, a1, w, h, want) {
  const fit = [];
  let t = a0 + stepAt(a0, r, w, h) / 2;
  while (t <= a1 - stepAt(t, r, w, h) / 2 + 1e-9) { fit.push(t); t += stepAt(t, r, w, h); }
  const capacity = Math.max(1, fit.length);
  const count = Math.min(capacity, want);
  if (count === 1) return { capacity, angles: [(a0 + a1) / 2] };
  if (count === capacity && fit.length) {
    const room = a1 - (fit[fit.length - 1] + stepAt(fit[fit.length - 1], r, w, h) / 2);
    return { capacity, angles: fit.map((x, j) => x + (room * (j + 0.5)) / count) };
  }
  return { capacity, angles: Array.from({ length: count }, (_, j) => a0 + ((j + 0.5) * (a1 - a0)) / count) };
}

/** The slots a region of ``n`` parts takes: ring by ring from the hub outwards, each ring as full as it fits. */
function regionSlots(n, a0, a1, w, h, ringR) {
  const slots = [];
  for (let k = 0; slots.length < n; k++) {
    const { angles } = ringSlots(ringR(k), a0, a1, w, h, n - slots.length);
    angles.forEach((t) => slots.push({ ring: k, t }));
  }
  return slots;
}

const boxOf = (p, label, size = 10, bold = false) => {
  const w = Math.max(2 * p.r, textWidth(label, size, bold)) + 8;
  return { x0: p.x - w / 2, x1: p.x + w / 2, y0: p.y - p.r - 2, y1: p.y + p.r + 16 };
};
const hit = (a, b, gap = 2) => a.x0 < b.x1 + gap && b.x0 < a.x1 + gap && a.y0 < b.y1 + gap && b.y0 < a.y1 + gap;

// ----------------------------------------------------------------------------------------------- the structure --

/** Places every drawn part of a structure, its folders (sectors and sub-folders), their names and the links between parts.
 *  Returns plain numbers only: ``{ order, sectors, points, labels, edges, bounds, ring }``. */
export function structureLayout(st) {
  const plan = sectorPlan(st);
  const nodes = [...st.nodes].sort(byId);
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const drawnNodes = nodes.filter((n) => n.drawn);
  const rmax = Math.max(MORE_R, ...drawnNodes.map((n) => radiusOf(n.lines)));
  const widest = Math.max(...drawnNodes.map((n) => Math.max(2 * radiusOf(n.lines), textWidth(midTrunc(n.name, NODE_LABEL_CHARS))) + 8), 40);
  const R0 = 100 + rmax + 16, pitch = Math.max(2 * rmax + 26, Math.ceil(widest / WIDE) + 2);   // rings far enough apart for both a tall and a wide part
  const ringR = (k) => R0 + k * pitch;
  const rIn = R0 - rmax - 24;
  const itemsOf = (g) => {
    const items = (plan.byGroup.get(g.id) || []).filter((n) => n.drawn).map((n) => ({ id: n.id, kind: n.kind, n, r: radiusOf(n.lines), label: midTrunc(n.name, NODE_LABEL_CHARS) }));
    if (g.more > 0) items.push({ id: `more:${g.id}`, kind: 'more', g, r: MORE_R, label: 'more' });
    return items;
  };
  const live = plan.sectors.filter((s) => [s.own, ...s.subs].some((g) => itemsOf(g).length));
  const total = live.reduce((a, s) => a + [s.own, ...s.subs].reduce((b, g) => b + itemsOf(g).length, 0), 0) || 1;
  const usable = TAU - SECTOR_GAP * live.length;
  const points = new Map();
  const sectors = [];
  let a0 = -Math.PI / 2;
  for (const s of live) {
    const regions = [s.own, ...s.subs].map((g) => ({ g, items: itemsOf(g) })).filter((r) => r.items.length);
    const count = regions.reduce((a, r) => a + r.items.length, 0);
    const span = usable * (0.6 * (count / total) + 0.4 / live.length);
    const sub = regions.length > 1 ? SUB_GAP : 0, inner = span - sub * (regions.length - 1);
    const weight = regions.reduce((a, r) => a + r.items.length + 1, 0);
    let t0 = a0;
    for (const r of regions) {
      r.a0 = t0;
      r.a1 = t0 + (inner * (r.items.length + 1)) / weight;
      t0 = r.a1 + sub;
    }
    sectors.push({ s, regions, a0, a1: a0 + span });
    a0 += span + SECTOR_GAP;
  }
  const place = (it, ring, t, region, sector) => {
    points.set(it.id, { x: Math.cos(t) * ringR(ring) * WIDE, y: Math.sin(t) * ringR(ring), r: it.r, ring, angle: t, group: region.g.id, sector: sector.s.id, label: it.label });
    region.rings = Math.max(region.rings || 0, ring + 1);
  };
  const pureTests = (r) => r.items.every((i) => i.kind === 'test' || i.kind === 'more') && r.items.some((i) => i.kind === 'test');
  const geometry = (r) => ({ w: Math.max(...r.items.map((i) => textWidth(i.label))) + 12, h: 2 * Math.max(...r.items.map((i) => i.r)) + 22 });
  // 1. every folder that is not only tests: source files by how central they are (the most imported nearest the hub), the rest
  //    by name, ring after ring; inside a ring in name order.
  for (const sec of sectors) {
    for (const r of sec.regions.filter((x) => !pureTests(x))) {
      const { w, h } = geometry(r);
      const ordered = [...r.items].sort((a, b) => (KIND_RANK[a.kind] - KIND_RANK[b.kind])
        || (a.kind === 'module' ? centrality(b.n) - centrality(a.n) : 0) || cmp(a.id, b.id));
      let next = 0;
      for (let k = 0; next < ordered.length; k++) {
        const { angles } = ringSlots(ringR(k), r.a0, r.a1, w, h, ordered.length - next);
        const ring = ordered.slice(next, next + angles.length).sort((a, b) => (a.kind === 'more') - (b.kind === 'more') || cmp(a.id, b.id));
        ring.forEach((it, j) => place(it, k, angles[j], r, sec));
        next += angles.length;
      }
    }
  }
  // 2. folders of tests: a sector of tests shares an edge with the source sector it reaches most, and its files keep the order of the
  //    modules they reach most, counted from that edge (mirrored across it: the module nearest the edge gives the first place), so
  //    the dashed links nest instead of crossing in order; a file that reaches nothing comes last, by name. A folder of tests inside a
  //    source folder counts from its own start instead (the module's angle, in the same sector).
  for (const sec of sectors) {
    for (const r of sec.regions.filter(pureTests)) {
      const { w, h } = geometry(r);
      const key = (it) => {
        if (it.kind === 'more') return [2, 0];
        const target = plan.main.get(it.id), p = target && points.get(target);
        if (!p) return [1, 0];
        const inside = plan.sectorOfGroup.get(nodeById.get(target)?.group) === sec.s;
        return [0, inside ? (((p.angle - sec.a0) % TAU) + TAU) % TAU : (((sec.a0 - p.angle) % TAU) + TAU) % TAU];
      };
      const ordered = [...r.items].sort((a, b) => { const ka = key(a), kb = key(b); return ka[0] - kb[0] || ka[1] - kb[1] || cmp(a.id, b.id); });
      const slots = regionSlots(ordered.length, r.a0, r.a1, w, h, ringR).sort((a, b) => a.t - b.t || a.ring - b.ring);
      ordered.forEach((it, j) => place(it, slots[j].ring, slots[j].t, r, sec));
    }
  }
  // the guarantee: no two parts (a part is its shape and its name) ever overlap. A part that still touches another after the
  // rings are filled (a wide name beside a wide name) moves outwards along its own line until it is clear.
  const ids = [...points.keys()];
  for (let pass = 0; pass < 24; pass++) {
    let moved = false;
    for (const id of ids) {                                     // nothing sits on the hub (its halo ends at 86)
      const p = points.get(id);
      if (!hit(boxOf(p, p.label), HUB_BOX, 2)) continue;
      const f = (Math.hypot(p.x / WIDE, p.y) + 8) / Math.hypot(p.x / WIDE, p.y);
      p.x *= f; p.y *= f; p.pushed = true; moved = true;
    }
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = points.get(ids[i]), b = points.get(ids[j]);
        if (!hit(boxOf(a, a.label), boxOf(b, b.label), 2)) continue;
        const rad = Math.hypot(b.x / WIDE, b.y) + 8;
        const f = rad / Math.hypot(b.x / WIDE, b.y);
        b.x *= f; b.y *= f; b.pushed = true; moved = true;
      }
    }
    if (!moved) break;
  }
  const sequence = [];                                         // the order the drawing lists its parts in, which is the Tab order too: folder by folder, ring by ring
  for (const sec of sectors) {
    for (const r of sec.regions) {
      const here = [...r.items].sort((a, b) => points.get(a.id).ring - points.get(b.id).ring || points.get(a.id).angle - points.get(b.id).angle || cmp(a.id, b.id));
      for (const it of here) sequence.push([it.id, points.get(it.id)]);
    }
  }
  points.clear();
  for (const [id, p] of sequence) points.set(id, p);
  const boxes = [];
  for (const [id, p] of points) boxes.push({ id, kind: 'part', ...boxOf(p, p.label) });
  const wedges = [];
  const reach = (ids2) => Math.max(0, ...ids2.map((id) => { const p = points.get(id); return Math.hypot(p.x / WIDE, p.y) + p.r + 22; }));
  for (const sec of sectors) {
    const regionsOut = sec.regions.map((r) => ({ ...r, rOut: reach(r.items.map((i) => i.id)) }));
    wedges.push({ id: sec.s.id, cat: sec.s.cat, home: sec.s.home || null, a0: sec.a0, a1: sec.a1, rIn, rOut: Math.max(...regionsOut.map((r) => r.rOut)),
      regions: regionsOut.map((r) => ({ id: r.g.id, a0: r.a0, a1: r.a1, rOut: r.rOut, rings: r.rings || 1 })) });
  }
  const labels = [];
  let order = 0;
  for (const wd of wedges) {
    const sec = sectors.find((x) => x.s.id === wd.id);
    wd.regions.forEach((rg, i) => {
      const g = sec.regions[i].g, isSub = g.id !== sec.s.id;
      const base = isSub ? g.id.slice(sec.s.id.length + 1) : g.id;
      const name = g.id === '' ? 'top level' : g.id === OTHER ? 'other folders' : pathTrunc(isSub ? base : g.id, isSub ? 20 : 24);
      const text = `${name} · ${g.files} file${g.files === 1 ? '' : 's'}`;
      const size = isSub ? 9.5 : 10.5, w = textWidth(text, size, true) + 16;
      const t = (rg.a0 + rg.a1) / 2;
      labels.push({ gid: g.id, text, size, w, h: 22, t, sub: isSub, order: order++, base: rg.rOut + (isSub ? 12 : 16), anchorR: rg.rOut, a0: rg.a0, a1: rg.a1 });
    });
  }
  const placed = [];
  for (const lb of labels) {
    const ca = Math.cos(lb.t), anchor = Math.abs(ca) < 0.3 ? 'middle' : ca > 0 ? 'start' : 'end';
    let r = lb.base, tries = 0, box;
    const at = (rad) => {
      const x = Math.cos(lb.t) * rad * WIDE, y = Math.sin(lb.t) * rad;
      const x0 = anchor === 'end' ? x - lb.w : anchor === 'middle' ? x - lb.w / 2 : x;
      return { x, y, box: { x0, x1: x0 + lb.w, y0: y - lb.h / 2, y1: y + lb.h / 2 } };
    };
    let p = at(r);
    while (tries < 80 && (boxes.some((b) => b.kind === 'part' && hit(p.box, b, 3)) || placed.some((q) => hit(p.box, q.box, 3)))) { r += 10; p = at(r); tries++; }
    lb.x = p.x; lb.y = p.y; lb.anchor = anchor; lb.box = p.box; lb.radius = r; lb.leader = r - lb.base > 24;
    placed.push(lb);
  }
  // the links: thin curves that never cross the hub
  const edges = [];
  const band = new Map(nodes.map((n) => [n.id, n.state?.band]));
  for (const e of [...st.edges].sort((a, b) => cmp(a.type + a.from + a.to, b.type + b.from + b.to))) {
    const a = points.get(e.from), b = points.get(e.to);
    if (!a || !b) continue;
    edges.push({ from: e.from, to: e.to, type: e.type, bad: e.type === 'tests' && band.get(e.from) === 'bad', how: e.how || [], d: linkPath(a, b) });
  }
  const xs = [-HUB_X, HUB_X], ys = [-HUB_Y, HUB_Y];
  for (const b of boxes) { xs.push(b.x0, b.x1); ys.push(b.y0, b.y1); }
  for (const lb of labels) { xs.push(lb.box.x0, lb.box.x1); ys.push(lb.box.y0, lb.box.y1); }
  for (const wd of wedges) for (const rg of wd.regions) for (const t of [wd.a0, wd.a1]) { xs.push(Math.cos(t) * rg.rOut * WIDE); ys.push(Math.sin(t) * rg.rOut); }
  const bounds = { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
  return { order: plan.sectors.map((s) => s.id), sectors: wedges, points, boxes, labels, edges, bounds, rIn, ring: { R0, pitch, rmax } };
}

/** A quadratic curve between two parts that keeps out of the box around the hub: it bows away from the hub as far as it must
 *  (the other way round, when the parts are opposite each other). Returns the SVG path. */
export function linkPath(a, b) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  let nx = -(b.y - a.y) / len, ny = (b.x - a.x) / len;        // the chord's normal, turned to the side away from the hub
  if (nx * mx + ny * my < -1e-6) { nx = -nx; ny = -ny; }
  let bow = Math.min(22, len * 0.08), c;
  for (let i = 0; i < 80; i++, bow += 10) {
    c = { x: mx + nx * bow * 2, y: my + ny * bow * 2 };
    if (curveClear(a, c, b)) break;
  }
  return `M${a.x.toFixed(1)} ${a.y.toFixed(1)} Q ${c.x.toFixed(1)} ${c.y.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
}

/** Whether the quadratic curve a, c, b stays out of the hub's box. */
export function curveClear(a, c, b) {
  for (let i = 0; i <= 32; i++) {
    const t = i / 32, u = 1 - t;
    const x = u * u * a.x + 2 * u * t * c.x + t * t * b.x, y = u * u * a.y + 2 * u * t * c.y + t * t * b.y;
    if (Math.abs(x) < HUB_X && Math.abs(y) < HUB_Y) return false;
  }
  return true;
}

/** The points of a path written by ``linkPath`` (a quadratic curve), sampled, for checks. */
export function samplePath(d, steps = 32) {
  const n = String(d).match(/-?\d+(?:\.\d+)?/g).map(Number);
  const [x0, y0, cx, cy, x1, y1] = n;
  return Array.from({ length: steps + 1 }, (_, i) => { const t = i / steps, u = 1 - t; return { x: u * u * x0 + 2 * u * t * cx + t * t * x1, y: u * u * y0 + 2 * u * t * cy + t * t * y1 }; });
}

// ---------------------------------------------------------------------------------------------------- the plan --

export const PLAN = { BOX_W: 172, BOX_H: 46, COL: 232, ROW: 62, HEAD: 30, PAD: 24, GAP_Y: 10 };

/** Places the plan graph: one lane per track; inside a lane, a column per prerequisite depth that holds a milestone (the depths
 *  are numbered by the plan, and only the ones in use take a column, so the spacing is even); a milestone sits to the right of
 *  everything it needs, and the order inside a column follows where what it needs was placed (the plan's order breaks ties), so
 *  links cross as little as the order allows. A link between neighbouring columns is a curve; one that skips a column runs along
 *  the space between two rows, so it never passes behind a milestone. */
export function planLayout(graph, shownIds, openTracks = new Set()) {
  const { BOX_W, BOX_H, COL, ROW, HEAD, PAD, GAP_Y } = PLAN;
  const order = new Map(graph.nodes.map((n, i) => [n.id, i]));
  const shown = graph.nodes.filter((n) => shownIds.has(n.id));
  const tracks = graph.tracks.filter((t) => shown.some((n) => n.track === t.name) || t.more);
  const levels = [...new Set(shown.map((n) => n.level))].sort((a, b) => a - b);
  const column = new Map(levels.map((l, i) => [l, i]));
  const lanes = [];
  let y = 0;
  for (const t of tracks) {
    const members = shown.filter((n) => n.track === t.name);
    const cells = new Map();
    for (const n of members) { const c = column.get(n.level); if (!cells.has(c)) cells.set(c, []); cells.get(c).push(n); }
    const rows = Math.max(1, ...[...cells.values()].map((c) => c.length));
    const more = t.more && !openTracks.has(t.name);
    const hgt = HEAD + rows * ROW + (more ? 26 : 8);
    lanes.push({ t, y, hgt, rows, members, cells, more });
    y += hgt + GAP_Y;
  }
  const pos = new Map();
  const centreY = (id) => pos.get(id).y + BOX_H / 2;
  const maxCol = Math.max(0, levels.length - 1);
  for (let c = 0; c <= maxCol; c++) {
    for (const lane of lanes) {
      const cell = lane.cells.get(c) || [];
      const keyed = cell.map((n) => {
        const ys = (n.depends_on || []).filter((k) => pos.has(k)).map(centreY);
        return { n, key: ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : lane.y + HEAD + order.get(n.id) * 0.001 };
      });
      keyed.sort((a, b) => a.key - b.key || order.get(a.n.id) - order.get(b.n.id));
      keyed.forEach(({ n }, row) => pos.set(n.id, { x: PAD + c * COL, y: lane.y + HEAD + row * ROW, row, col: c, lane }));
    }
  }
  const W = PAD + (maxCol + 1) * COL + 40, H = y + 10;
  const edges = [];
  const channelOf = (from, to) => {                    // the gap between two rows of the source's lane that leans towards the target
    const lane = from.lane, down = centreY0(to) > centreY0(from);
    const i = down ? from.row + 1 : from.row;
    return lane.y + HEAD + i * ROW - (ROW - BOX_H) / 2 + (i === 0 ? 4 : 0);
  };
  const centreY0 = (p) => p.y + BOX_H / 2;
  for (const e of graph.edges) {
    const a = pos.get(e.from), b = pos.get(e.to);
    if (!a || !b) continue;
    const x1 = a.x + BOX_W, y1 = a.y + BOX_H / 2, x2 = b.x, y2 = b.y + BOX_H / 2;
    let d, route = 'curve';
    if (b.col - a.col <= 1) {
      const mx = (x1 + x2) / 2;
      d = `M${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2 - 2} ${y2}`;
    } else {
      route = 'channel';
      const yc = channelOf(a, b), r = 8, xa = x1 + 16, xb = x2 - 16;
      const s1 = yc > y1 ? 1 : -1, s2 = y2 > yc ? 1 : -1;
      d = `M${x1} ${y1} H ${xa - r} Q ${xa} ${y1} ${xa} ${y1 + s1 * r} V ${yc - s1 * r} Q ${xa} ${yc} ${xa + r} ${yc} H ${xb - r} Q ${xb} ${yc} ${xb} ${yc + s2 * r} V ${y2 - s2 * r} Q ${xb} ${y2} ${xb + r} ${y2} H ${x2 - 2}`;
    }
    edges.push({ ...e, d, route });
  }
  return { lanes, pos, edges, columns: levels.length, W, H, tracks };
}
