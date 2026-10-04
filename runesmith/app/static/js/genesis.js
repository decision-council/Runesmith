// Genesis: the opening sequence. It explains Runesmith in seven short scenes, then asks what you will create.
// First boot: it uses the real folder and ends with naming it. Cinema mode (/cinema): demo data, loops, shareable.
import { h, icon, get, post } from './core.js';
import { iconSvg, logoMark, wordmark } from './icons.js';

const NS = 'http://www.w3.org/2000/svg';
const CX = 800, CY = 360;
function S(tag, attrs = {}, parent) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    if (k === 'text') el.textContent = v; else if (k === 'style') el.setAttribute('style', v); else el.setAttribute(k, v);
  }
  if (parent) parent.appendChild(el);
  return el;
}
function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const EMBER = '#ff8a3d', GOLD = '#e8b04a', RUNE = '#f8dc94', STEEL = '#8ea0c4';

const KERNEL_DEMO = ['canon', 'ledger', 'instruments', 'sandbox', 'organ_child', 'oslimits', 'generations', 'loop', 'opportunity', 'objects/code', 'discover',
  'envmap', 'selfmap', 'kaizen/improve', 'kaizen/trial', 'kaizen/attention', 'kaizen/diagnose', 'kaizen/affordances', 'share', 'proposals', 'memory', 'notes',
  'keystore', 'manual', 'report', 'doctor', 'steward', 'config', 'home', 'local'];
const dir = (name, ...kids) => ({ name, type: 'dir', children: kids.map((k) => (k.endsWith('/') ? { name: k.slice(0, -1), type: 'dir' } : { name: k, type: 'file' })) });
const file = (name) => ({ name, type: 'file' });
// The cinema cycles through these: a corner bakery, a freight company, a group of clinics. Any shape and size.
// Each is a real demo folder (the website shows the same folders in the Studio); file counts are theirs.
const DEMOS = [
  { folder: 'moonlight-bakery', path: '~/projects/moonlight-bakery', files: 30, empty: false, who: 'a corner bakery',
    entries: [dir('bakery-api', 'src/', 'tests/', 'pyproject.toml', 'README.md'), dir('shop', 'index.html', 'order.html', 'pickup.html', 'styles.css', 'images/'),
      dir('docs', 'index.md', 'ordering.md', 'pickup.md', 'allergens.md'), dir('recipes', 'sourdough.md', 'rye.md', 'seeded-loaf.md', 'cinnamon-buns.md', 'croissants.md'),
      file('README.md'), file('blueprint.md'), file('menu.csv')],
    objects: [{ name: 'bakery-api', kind: 'python_repository' }, { name: 'shop', kind: 'website' }, { name: 'docs', kind: 'document_collection' }],
    typed: { name: 'Moonlight Bakery', description: 'A little website where our neighbours pre-order bread, and a weekly bake plan for us.', type: 'build',
      sub: 'Mapping its world. Planning the way.' } },
  { folder: 'northwind-freight', path: '~/work/northwind-freight', files: 84, empty: false, who: 'a freight company',
    entries: [dir('services', 'tracking-api/', 'billing/', 'notifications/', 'customs/'), dir('web-portal', 'src/', 'public/', 'tests/', 'package.json'),
      dir('docs', 'runbooks/', 'adr/', 'architecture.md', 'compliance.md'), dir('infra', 'terraform/', 'k8s/', 'docker-compose.yml'),
      dir('data-contracts', 'shipment.schema.json', 'invoice.schema.json', 'container-event.schema.json'),
      { name: 'payroll', type: 'dir', excluded: true }, file('README.md'), file('SECURITY.md'), file('CODEOWNERS'), file('CHANGELOG.md')],
    objects: [{ name: 'services/tracking-api', kind: 'python_repository' }, { name: 'web-portal', kind: 'node_repository' }, { name: 'docs', kind: 'document_collection' }],
    typed: { name: 'Northwind Freight Portal', description: 'Shippers track every container in real time, and compliance can verify every change we make.', type: 'improve',
      sub: 'Four services, one portal, one ledger. Mapping them now.' } },
  { folder: 'helio-clinics', path: '~/work/helio-clinics', files: 38, empty: false, who: 'three clinics',
    entries: [dir('booking-app', 'index.html', 'book.html', 'clinics.html', 'faq.html', 'booking.js'), dir('api', 'src/', 'tests/', 'pyproject.toml', 'README.md'),
      dir('policies', 'privacy.md', 'consent.md', 'complaints.md', 'cookies.md'), dir('staff-handbook', 'rota.md', 'onboarding.md', 'hygiene.md', 'emergencies.md'),
      { name: 'patient-records', type: 'dir', excluded: true }, file('README.md'), file('clinics.csv')],
    objects: [{ name: 'booking-app', kind: 'website' }, { name: 'api', kind: 'python_repository' }, { name: 'policies', kind: 'document_collection' }],
    typed: { name: 'Helio Booking', description: 'Patients book at any of our three clinics, and get a reminder the day before.', type: 'build',
      sub: 'Three clinics, one calendar. Planning the way.' } },
];
const DEMO = DEMOS[0];

/** The demo stories, for pages that show them beside the cinema (name, folder and who it is for). */
export const STORIES = DEMOS.map((d) => ({ name: d.typed.name, folder: d.folder, who: d.who }));

export async function runGenesis(root, { cinema = false, embedded = false, story = 0 } = {}) {
  let info = DEMOS[story % DEMOS.length] || DEMO;
  const real = !cinema || (!embedded && new URLSearchParams(location.search).has('real'));
  if (real) { try { info = await get('/api/genesis'); } catch { info = DEMO; } }
  return new Promise((resolve) => {
    const g = new Genesis(root, info, { cinema: cinema || embedded, embedded, onDone: resolve });
    if (!real) g.loops = story % DEMOS.length;
    // A page can follow the stories (genesis:story, sent on the root) and pick one (genesis:play with {story}).
    root.addEventListener('genesis:play', (e) => g.play(e.detail?.story ?? 0));
    g.start();
  });
}

class Genesis {
  constructor(root, info, { cinema, embedded = false, onDone }) {
    this.info = info; this.cinema = cinema; this.embedded = embedded; this.onDone = onDone; this.index = -1; this.timer = null; this.layers = [];
    this.el = h('div.genesis', { role: 'region', 'aria-label': 'Runesmith introduction' });
    this.loops = 0;
    this.starSvg = S('svg', { class: 'stars', viewBox: '0 0 1600 900', preserveAspectRatio: 'xMidYMid slice', 'aria-hidden': 'true' });
    this.svg = S('svg', { class: 'stage', viewBox: '0 0 1600 900', preserveAspectRatio: 'xMidYMid meet' });
    this.caption = h('div.g-caption', h('div.t'), h('div.s'), h('div.fine'));
    this.dots = h('div.g-dots');
    this.top = h('div.g-top');
    this.el.append(...[this.starSvg, this.svg, h('div.g-brand', h('span.mk', { html: logoMark() }), h('span.wm', { html: wordmark() })), this.top, this.caption, this.dots,
      embedded ? null : h('div.hint', cinema ? 'Space: next · F: full screen' : 'Space or → to skip ahead')].filter(Boolean));   // DOM append would print "null"
    if (embedded) this.el.classList.add('embedded');
    this.root = root;
    root.append(this.el);
    this.defs();
    this.stars();
    this.stage = S('g', {}, this.svg);
    this.frame();
    if ('ResizeObserver' in window) {                         // a resized window or player keeps the scene fitted
      this.resizer = new ResizeObserver(() => { this.frame(); if (this.lastFit && this.lastFit[0].isConnected) this.fit(...this.lastFit); });
      this.resizer.observe(this.svg);
    }
    this.scenes = [this.spark, this.forge, this.world, this.itself, this.guard, this.evidence, this.minds, this.finale].map((f) => f.bind(this));
    for (let i = 0; i < this.scenes.length; i++) this.dots.append(h('i', { onclick: () => this.go(i) }));
    if (cinema) this.top.append(h('button.g-btn', { onclick: () => this.go(0) }, icon('refresh'), 'Restart'),
      h('button.g-btn', { onclick: () => this.fullscreen() }, icon('maximize'), 'Full screen'));
    else this.top.append(h('button.g-btn', { onclick: () => this.go(this.scenes.length - 1) }, 'Skip intro', icon('right')));
    this.onKey = (e) => {
      if (e.target.closest && e.target.closest('input, textarea')) return;
      if (e.key === ' ' || e.key === 'ArrowRight') { e.preventDefault(); if (this.index < this.scenes.length - 1) this.go(this.index + 1); }
      else if (e.key === 'ArrowLeft' && this.index > 0) this.go(this.index - 1);
      else if (e.key === 'Escape' && !this.cinema) this.go(this.scenes.length - 1);
      else if ((e.key === 'f' || e.key === 'F') && this.cinema) this.fullscreen();
    };
    if (!embedded) document.addEventListener('keydown', this.onKey);    // on a web page, keys belong to the page
  }
  fullscreen() { if (!document.fullscreenElement) this.el.requestFullscreen?.().catch(() => {}); else document.exitFullscreen?.(); }
  start() {
    const q = new URLSearchParams(this.embedded ? '' : location.search);
    this.hold = q.has('hold');                         // stills for design review and the website: ?scene=N&hold
    const n = Math.max(0, Math.min(this.scenes.length - 1, parseInt(q.get('scene') || '0', 10) || 0));
    this.announce();
    this.go(n);
  }
  /** Tell the page which story plays now (cinema only; the real first boot has no stories). */
  announce() {
    if (!this.info.typed) return;
    this.root.dispatchEvent(new CustomEvent('genesis:story', { detail: { index: this.loops % DEMOS.length, name: this.info.typed.name, folder: this.info.folder } }));
  }
  /** Jump to a story's own world. */
  play(i) {
    if (!this.info.typed) return;
    this.loops = ((i % DEMOS.length) + DEMOS.length) % DEMOS.length;
    this.info = DEMOS[this.loops];
    this.announce();
    this.go(2);
  }
  defs() {
    const d = S('defs', {}, this.svg);
    const rg = S('radialGradient', { id: 'g-ember', r: '60%' }, d);
    S('stop', { offset: '0', 'stop-color': '#fff3d6' }, rg); S('stop', { offset: '.35', 'stop-color': GOLD }, rg); S('stop', { offset: '.75', 'stop-color': EMBER }, rg); S('stop', { offset: '1', 'stop-color': '#c58a34' }, rg);
    const halo = S('radialGradient', { id: 'g-halo', r: '50%' }, d);
    S('stop', { offset: '0', 'stop-color': EMBER, 'stop-opacity': '.55' }, halo); S('stop', { offset: '1', 'stop-color': EMBER, 'stop-opacity': '0' }, halo);
    const rh = S('radialGradient', { id: 'g-rune-halo', r: '50%' }, d);
    S('stop', { offset: '0', 'stop-color': RUNE, 'stop-opacity': '.4' }, rh); S('stop', { offset: '1', 'stop-color': RUNE, 'stop-opacity': '0' }, rh);
    const f = S('filter', { id: 'g-glow', x: '-50%', y: '-50%', width: '200%', height: '200%' }, d);
    S('feGaussianBlur', { stdDeviation: '5', result: 'b' }, f);
    const m = S('feMerge', {}, f); S('feMergeNode', { in: 'b' }, m); S('feMergeNode', { in: 'SourceGraphic' }, m);
  }
  stars() {
    const r = rng(7), g = S('g', {}, this.starSvg);
    for (let i = 0; i < 110; i++) {
      S('circle', { cx: (r() * 1600).toFixed(1), cy: (r() * 900).toFixed(1), r: (r() * 1.3 + 0.3).toFixed(2), fill: r() < 0.15 ? GOLD : '#c9d4ff', class: 'twinkle',
        style: `animation-delay:${(r() * 3.6).toFixed(2)}s;opacity:.3` }, g);
    }
  }
  say(t, s, fine, cls) {
    const [te, se, fe] = this.caption.children;
    this.caption.classList.remove('on');
    clearTimeout(this.sayTimer);
    this.sayTimer = setTimeout(() => {
      te.textContent = t || ''; se.textContent = s || ''; fe.textContent = fine || '';
      te.className = `t${cls ? ' ' + cls : ''}`;
      void this.caption.offsetWidth;
      if (t || s) this.caption.classList.add('on');
    }, this.index === 0 ? 400 : 480);
  }
  layer() {
    for (const old of this.layers) { old.classList.add('fade-out'); setTimeout(() => old.remove(), 950); }
    const holder = S('g', {}, this.stage);                  // holder: scaled to fit; l: animated (fades, never scaled)
    const l = S('g', { class: 'fade-in' }, holder);
    this.layers = [holder];
    return l;
  }
  /** Give the drawing the stage band's own shape (900 units tall, as wide as the band), so wide scenes use the
   *  whole width of a full screen, a web player or a phone. Scene coordinates stay centred on (800, 450). */
  frame() {
    const r = this.svg.getBoundingClientRect();
    const aspect = r.width > 0 && r.height > 0 ? r.width / r.height : 16 / 9;
    this.VW = Math.max(600, Math.min(3200, 900 * aspect));
    this.svg.setAttribute('viewBox', `${(800 - this.VW / 2).toFixed(1)} 0 ${this.VW.toFixed(1)} 900`);
  }
  /** Scale a scene to fill the stage band: [x0, y0, x1, y1] is the art's extent in scene coordinates. */
  fit(l, box, most = 1.45) {
    this.lastFit = [l, box, most];
    const [x0, y0, x1, y1] = box;
    const s = Math.min((this.VW || 1600) * 0.94 / (x1 - x0), 900 * 0.94 / (y1 - y0), most);
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    l.parentNode.setAttribute('transform', `translate(${(800 - s * cx).toFixed(1)} ${(450 - s * cy).toFixed(1)}) scale(${s.toFixed(3)})`);
  }
  go(i) {
    clearTimeout(this.timer);
    this.finaleToken = null;                                // a typing finale stops the moment the scene changes
    if (i !== this.scenes.length - 1) { this.namePane?.remove(); this.namePane = null; this.el.querySelector('.forged')?.remove(); }
    this.index = i;
    [...this.dots.children].forEach((d, j) => { d.className = j < i ? 'done' : j === i ? 'now' : ''; });
    const dur = this.scenes[i]() || 0;
    const nowDot = this.dots.children[i];
    if (nowDot && dur) nowDot.style.setProperty('--dur', `${dur}ms`);
    if (dur && !this.hold) this.timer = setTimeout(() => this.go(i + 1), reduced() ? Math.min(dur, 2500) : dur);
  }
  sigil(parent, x, y, size, cls = 'pop') {
    const holder = S('g', { transform: `translate(${x - size / 2},${y - size / 2})` }, parent);
    const inner = S('g', { class: cls }, holder);
    const t = document.createElement('template');
    t.innerHTML = logoMark({ forge: true }).replace('<svg ', `<svg width="${size}" height="${size}" `);
    inner.appendChild(document.importNode(t.content.firstChild, true));
    return holder;
  }
  runeGlyph(parent, x, y, size, seed, rot, color) {
    const r = rng(seed), grp = S('g', { transform: `translate(${x},${y}) rotate(${rot})`, stroke: color, 'stroke-width': 1.7, fill: 'none', 'stroke-linecap': 'round' }, parent);
    const hh = size / 2;
    S('path', { d: `M0 ${-hh} L0 ${hh}` }, grp);
    const twigs = 1 + Math.floor(r() * 2.4);
    for (let i = 0; i < twigs; i++) {
      const y0 = -hh + r() * size * 0.55, dir = r() < 0.5 ? -1 : 1, len = size * (0.32 + r() * 0.28);
      S('path', { d: r() < 0.3 ? `M0 ${y0} L${dir * len * 0.7} ${y0 + len * 0.45} L0 ${y0 + len * 0.9}` : `M0 ${y0} L${dir * len * 0.72} ${y0 + len * 0.6}` }, grp);
    }
  }
  iconAt(parent, name, x, y, size, color) {
    const t = document.createElement('template');
    t.innerHTML = iconSvg(name).replace('<svg ', `<svg x="${x - size / 2}" y="${y - size / 2}" width="${size}" height="${size}" `).replace('stroke="currentColor"', `stroke="${color}"`);
    parent.appendChild(document.importNode(t.content.firstChild, true));
  }
  line(parent, x1, y1, x2, y2, color, delay = 0, width = 1.4, extra = {}) {
    const len = Math.hypot(x2 - x1, y2 - y1);
    return S('path', { d: `M${x1} ${y1} L${x2} ${y2}`, stroke: color, 'stroke-width': width, fill: 'none', class: 'draw', style: `--len:${len.toFixed(0)};animation-delay:${delay}ms`, ...extra }, parent);
  }

  // ------------------------------------------------------------------ scenes --
  spark() {
    const l = this.layer();
    S('circle', { cx: CX, cy: CY, r: 150, fill: 'url(#g-halo)', class: 'breathe' }, l);
    S('circle', { cx: CX, cy: CY, r: 9, fill: 'url(#g-ember)', class: 'glow breathe' }, l);
    const r = rng(3);
    for (let i = 0; i < 18; i++) {
      const a = (i / 18) * Math.PI * 2 + r() * 0.2, r0 = 20 + r() * 10, r1 = 60 + r() * 70;
      this.line(l, CX + Math.cos(a) * r0, CY + Math.sin(a) * r0, CX + Math.cos(a) * r1, CY + Math.sin(a) * r1, i % 3 ? GOLD : EMBER, 300 + r() * 1400, 1.2, { 'stroke-opacity': 0.7 });
    }
    this.fit(l, [CX - 190, CY - 190, CX + 190, CY + 190], 1.25);
    this.say('Every creation begins with a spark.', this.cinema ? '' : 'Welcome. This takes about half a minute, and you can skip it.');
    return 3800;
  }
  forge() {
    const l = this.layer();
    S('circle', { cx: CX, cy: CY, r: 300, fill: 'url(#g-halo)', opacity: 0.55 }, l);
    S('circle', { cx: CX, cy: CY, r: 150, fill: 'none', stroke: EMBER, 'stroke-width': 1.5, 'stroke-dasharray': '2 10', class: 'spin', opacity: 0.8 }, l);
    S('circle', { cx: CX, cy: CY, r: 208, fill: 'none', stroke: RUNE, 'stroke-width': 1.2, 'stroke-dasharray': '46 14 4 14', class: 'spin-rev', opacity: 0.7 }, l);
    const ring = S('g', { class: 'spin' }, l);
    for (let i = 0; i < 40; i++) {
      const a = (i / 40) * Math.PI * 2, rr = 268;
      this.runeGlyph(ring, CX + Math.cos(a) * rr, CY + Math.sin(a) * rr, 18, i * 31 + 5, (a * 180) / Math.PI + 90, i % 5 ? 'rgba(255,190,120,.55)' : GOLD);
    }
    S('circle', { cx: CX, cy: CY, r: 268, fill: 'none', stroke: 'rgba(255,255,255,.06)', 'stroke-width': 30 }, l);
    this.sigil(l, CX, CY, 150);
    this.fit(l, [CX - 300, CY - 300, CX + 300, CY + 300], 1.3);
    this.say('RUNESMITH', 'A runtime that learns its craft, and proves it.', '', 'g-title');
    return 5200;
  }
  world() {
    const l = this.layer();
    const info = this.info;
    const entries = (info.entries || []).slice(0, 18);
    this.sigil(l, CX, CY, 96, 'fade-in');
    if (!entries.length) {
      S('ellipse', { cx: CX, cy: CY, rx: 430, ry: 230, fill: 'none', stroke: 'rgba(255,255,255,.18)', 'stroke-dasharray': '5 12' }, l);
      S('text', { x: CX, y: CY + 110, 'text-anchor': 'middle', fill: '#8a95b0', 'font-size': 20, text: 'an empty folder' }, l);
      this.fit(l, [CX - 450, CY - 250, CX + 450, CY + 250]);
      this.say('It maps your world.', 'An empty folder is a blank canvas. Tell Runesmith what to build, and it plans the way there.');
      return 5200;
    }
    const n = entries.length;
    const RX = n <= 6 ? 330 : 440, RY = n <= 6 ? 150 : 185;
    const short = (s, k) => (s.length > k ? s.slice(0, k - 1) + '…' : s);
    entries.forEach((e, i) => {
      const a = -Math.PI / 2 + (i / n) * Math.PI * 2 + (n % 2 ? 0 : Math.PI / (2 * n));
      const x = CX + Math.cos(a) * RX, y = CY + Math.sin(a) * RY;
      const delay = 250 + i * 150;
      const isDir = e.type === 'dir';
      const tone = e.excluded ? '#6f7a95' : isDir ? RUNE : GOLD;
      this.line(l, CX + Math.cos(a) * 64, CY + Math.sin(a) * 40, x - Math.cos(a) * 30, y - Math.sin(a) * 18,
        e.excluded ? 'rgba(111,122,149,.4)' : isDir ? 'rgba(34,211,197,.5)' : 'rgba(255,181,71,.45)', delay, 1.3, e.excluded ? { 'stroke-dasharray': '4 6' } : {});
      const g = S('g', { class: 'pop', style: `animation-delay:${delay + 450}ms` }, l);
      S('circle', { cx: x, cy: y, r: 24, fill: '#101626', stroke: tone, 'stroke-width': 1.6, 'stroke-dasharray': e.excluded ? '4 4' : null }, g);
      this.iconAt(g, e.excluded ? 'lock' : isDir ? 'folder' : 'file', x, y, 22, tone);
      S('text', { x, y: y + (Math.sin(a) < -0.3 ? -34 : 44), 'text-anchor': 'middle', fill: e.excluded ? '#8a95b0' : '#dfe5f2', 'font-size': 15, 'font-weight': 650,
        text: e.excluded ? `${short(e.name, 16)} · never read` : short(e.name, 18) }, g);
      const kids = (e.children || []).slice(0, 5);
      kids.forEach((k, j) => {
        const b = a + (j - (kids.length - 1) / 2) * (n <= 6 ? 0.2 : 0.13);
        const kx = CX + Math.cos(b) * RX * 1.5, ky = CY + Math.sin(b) * RY * 1.55;
        const kd = delay + 900 + j * 90;
        this.line(l, x + Math.cos(b) * 26, y + Math.sin(b) * 18, kx - Math.cos(b) * 12, ky - Math.sin(b) * 8, 'rgba(255,255,255,.14)', kd, 1);
        const kg = S('g', { class: 'pop', style: `animation-delay:${kd + 300}ms` }, l);
        S('circle', { cx: kx, cy: ky, r: 9, fill: '#101626', stroke: k.type === 'dir' ? 'rgba(34,211,197,.7)' : 'rgba(255,181,71,.7)', 'stroke-width': 1.2 }, kg);
        const right = Math.cos(b) >= 0;
        S('text', { x: kx + (right ? 15 : -15), y: ky + 4, 'text-anchor': right ? 'start' : 'end', fill: '#8a95b0', 'font-size': 12, text: short(k.name, 16) }, kg);
      });
    });
    const kidsX = entries.some((e) => (e.children || []).length) ? 1.5 * RX + 130 : RX + 110;
    const kidsY = entries.some((e) => (e.children || []).length) ? 1.55 * RY + 30 : RY + 60;
    this.fit(l, [CX - kidsX, CY - kidsY, CX + kidsX, CY + kidsY]);
    const folder = info.folder || info.name || 'this folder';
    const files = info.files != null ? `${info.files} file${info.files === 1 ? '' : 's'}` : `${n} things`;
    this.say('It maps your world.', `${files} in “${folder}”, read in seconds: every folder, how healthy each part is, and the next rung on each ladder.`);
    return 5800;
  }
  itself() {
    const l = this.layer();
    const kernel = (this.info.self && this.info.self.kernel && this.info.self.kernel.length ? this.info.self.kernel : KERNEL_DEMO).slice(0, 40);
    const N = kernel.length, R1 = 150, R2 = 205;
    S('circle', { cx: CX, cy: CY, r: 280, fill: 'url(#g-rune-halo)', opacity: 0.6 }, l);
    kernel.forEach((k, i) => {
      const a0 = (i / N) * Math.PI * 2 - Math.PI / 2 + 0.02, a1 = ((i + 1) / N) * Math.PI * 2 - Math.PI / 2 - 0.02;
      const p = (r, a) => `${(CX + Math.cos(a) * r).toFixed(1)} ${(CY + Math.sin(a) * r).toFixed(1)}`;
      S('path', { d: `M ${p(R2, a0)} A ${R2} ${R2} 0 0 1 ${p(R2, a1)} L ${p(R1, a1)} A ${R1} ${R1} 0 0 0 ${p(R1, a0)} Z`, fill: RUNE, 'fill-opacity': (0.25 + (i % 4) * 0.12).toFixed(2),
        stroke: '#0a0d16', 'stroke-width': 2, class: 'fade-in', style: `animation-delay:${200 + i * 55}ms` }, l);
      const am = (a0 + a1) / 2;
      if (i % 3 === 0 && !(Math.sin(am) < -0.9)) {                 // keep the top clear for the ring's title
        const tx = CX + Math.cos(am) * 245, ty = CY + Math.sin(am) * 245;
        S('text', { x: tx, y: ty, 'text-anchor': Math.cos(am) > 0.2 ? 'start' : Math.cos(am) < -0.2 ? 'end' : 'middle', 'dominant-baseline': 'middle', fill: '#7f8aa6', 'font-size': 12.5,
          class: 'fade-in', style: `animation-delay:${600 + i * 55}ms`, text: k }, l);
      }
    });
    S('circle', { cx: CX, cy: CY, r: 118, fill: '#0b0f19', stroke: 'rgba(255,255,255,.08)' }, l);
    S('circle', { cx: CX, cy: CY, r: 70, fill: 'url(#g-ember)', class: 'breathe', style: 'animation-delay:1.2s' }, l);
    S('text', { x: CX, y: CY + 6, 'text-anchor': 'middle', fill: '#0b0e14', 'font-size': 17, 'font-weight': 800, text: 'organs' }, l);
    S('text', { x: CX, y: CY - 262, 'text-anchor': 'middle', fill: RUNE, 'font-size': 13, 'letter-spacing': 4, text: `KERNEL · ${N} MODULES · FIXED`, class: 'fade-in' }, l);
    this.fit(l, [CX - 330, CY - 280, CX + 330, CY + 270], 1.4);
    this.say('…and it maps itself.', 'A fixed kernel keeps the rules: budgets, judges, a tamper-evident ledger. Living organs do the work, and only they may change. Every capability is measured, or marked unknown.');
    return 6000;
  }
  guard() {
    const l = this.layer();
    const stations = [['map', 'Map'], ['search', 'Find work'], ['hammer', 'Repair'], ['scale', 'Judge'], ['inbox', 'Propose'], ['user', 'You decide']];
    const R = 205;
    S('circle', { cx: CX, cy: CY, r: R, fill: 'none', stroke: 'rgba(255,255,255,.12)', 'stroke-width': 2, 'stroke-dasharray': '3 9' }, l);
    const path = S('path', { id: 'g-loop', d: `M ${CX} ${CY - R} A ${R} ${R} 0 1 1 ${CX - 0.01} ${CY - R}`, fill: 'none', stroke: 'none' }, l);
    stations.forEach(([ic, label], i) => {
      const a = -Math.PI / 2 + (i / stations.length) * Math.PI * 2, x = CX + Math.cos(a) * R, y = CY + Math.sin(a) * R;
      const you = i === stations.length - 1;
      const g = S('g', { class: 'pop', style: `animation-delay:${200 + i * 260}ms` }, l);
      S('circle', { cx: x, cy: y, r: 40, fill: '#101626', stroke: you ? EMBER : RUNE, 'stroke-width': you ? 3 : 1.6 }, g);
      if (you) S('circle', { cx: x, cy: y, r: 52, fill: 'none', stroke: EMBER, 'stroke-opacity': 0.35, 'stroke-width': 6, class: 'breathe' }, g);
      this.iconAt(g, ic, x, y, 30, you ? GOLD : RUNE);
      S('text', { x, y: y + (Math.sin(a) > 0.3 ? 66 : -54), 'text-anchor': 'middle', fill: you ? '#ffd9b8' : '#c9d1e3', 'font-size': 16, 'font-weight': 650, text: label }, g);
    });
    const dot = S('circle', { r: 8, fill: GOLD, class: 'glow' }, l);
    const motion = S('animateMotion', { dur: '4.2s', repeatCount: 'indefinite', rotate: 'auto' }, dot);
    S('mpath', { href: '#g-loop' }, motion);
    this.shield = S('g', { class: 'pop', style: 'animation-delay:1.8s' }, l);
    this.iconAt(this.shield, 'shield', CX, CY - 10, 70, RUNE);
    S('text', { x: CX, y: CY + 52, 'text-anchor': 'middle', fill: '#8a95b0', 'font-size': 14, text: 'your files stay yours' }, this.shield);
    this.fit(l, [CX - 300, CY - R - 80, CX + 300, CY + R + 80], 1.4);
    this.say('It works under guard.', 'Tests run on throwaway copies. A held-out judge checks every fix. Nothing touches your files until you say yes, and every yes can be undone.');
    return 6400;
  }
  evidence() {
    const l = this.layer();
    const root = [380, CY];
    S('circle', { cx: root[0], cy: root[1], r: 30, fill: '#101626', stroke: STEEL, 'stroke-width': 2 }, l);
    S('text', { x: root[0], y: root[1] + 6, 'text-anchor': 'middle', fill: '#dfe5f2', 'font-size': 16, 'font-weight': 750, text: 'B' }, l);
    S('text', { x: root[0], y: root[1] + 58, 'text-anchor': 'middle', fill: '#7f8aa6', 'font-size': 13, text: 'the incumbent' }, l);
    const kids = [[640, CY - 170, false], [660, CY - 60, false], [640, CY + 60, true], [660, CY + 170, false]];
    kids.forEach(([x, y, win], i) => {
      const d = 300 + i * 320;
      S('path', { d: `M${root[0] + 30} ${root[1]} C ${root[0] + 150} ${root[1]}, ${x - 150} ${y}, ${x - 26} ${y}`, stroke: win ? EMBER : 'rgba(255,255,255,.25)', 'stroke-width': win ? 2.4 : 1.4, fill: 'none', class: 'draw', style: `--len:420;animation-delay:${d}ms` }, l);
      const g = S('g', { class: 'pop', style: `animation-delay:${d + 700}ms` }, l);
      S('circle', { cx: x, cy: y, r: 24, fill: win ? 'url(#g-ember)' : '#101626', stroke: win ? GOLD : 'rgba(255,255,255,.3)', 'stroke-width': 1.6 }, g);
      S('text', { x, y: y + 5, 'text-anchor': 'middle', fill: win ? '#0b0e14' : '#8a95b0', 'font-size': 13, 'font-weight': 800, text: win ? 'C7' : `c${i + 1}` }, g);
      if (!win) {
        const x2 = S('g', { class: 'pop', style: `animation-delay:${d + 1500}ms` }, l);
        S('path', { d: `M${x + 30} ${y - 8} l16 16 M${x + 46} ${y - 8} l-16 16`, stroke: '#ff5a4f', 'stroke-width': 2.4, 'stroke-linecap': 'round' }, x2);
      }
    });
    // the sealed test: two bars
    const bx = 860, by = CY - 70, W = 520;
    const bar = (y, frac, color, label, value, delay) => {
      S('text', { x: bx, y: y - 14, fill: '#c9d1e3', 'font-size': 15, 'font-weight': 650, text: label, class: 'fade-in', style: `animation-delay:${delay}ms` }, l);
      S('rect', { x: bx, y, width: W, height: 26, rx: 13, fill: 'rgba(255,255,255,.07)' }, l);
      const r = S('rect', { x: bx, y, width: 0, height: 26, rx: 13, fill: color }, l);
      const t = S('text', { x: bx + W + 16, y: y + 19, fill: '#fff', 'font-size': 20, 'font-weight': 800, text: '0' }, l);
      setTimeout(() => {
        const t0 = performance.now(), dur = 1500;
        // a frame's timestamp can precede t0: clamp, or the count runs negative for a moment
        const step = (now) => { const k = Math.max(0, Math.min(1, (now - t0) / dur)), e = 1 - Math.pow(1 - k, 3);
          r.setAttribute('width', (W * frac * e).toFixed(1)); t.textContent = `${Math.round(value * e)}`;
          if (k < 1 && this.index === 5) requestAnimationFrame(step); };
        requestAnimationFrame(step);
      }, delay);
    };
    bar(by, 57 / 162, EMBER, 'C7, written by Runesmith for itself', 57, 1900);
    bar(by + 92, 35 / 162, STEEL, 'B, its predecessor', 35, 2100);
    S('text', { x: bx, y: by + 170, fill: '#7f8aa6', 'font-size': 13.5, text: 'repairs out of 162 attempts at 54 unseen tasks, same cheap model', class: 'fade-in', style: 'animation-delay:2.6s' }, l);
    this.fit(l, [340, CY - 210, 1420, CY + 210], 1.35);
    this.say('It improves itself, only with evidence.',
      'Candidates are tested on work their author never saw. In a sealed, preregistered test, a generation Runesmith wrote for itself succeeded on 57 of 162 attempts at 54 unseen tasks. Its predecessor managed 35.',
      'SR7 · 2026 · synthetic single-line bugs · one cheap model · p = 0.00085 · a new generation must still win a live trial on your work');
    return 7600;
  }
  minds() {
    const l = this.layer();
    this.sigil(l, CX, CY, 120, 'fade-in');
    const orbit = S('g', { class: 'spin', style: 'animation-duration:48s' }, l);
    const minds = [['laptop', 'on your computer'], ['key', 'an API key'], ['chat', 'a chat window'], ['cloud', 'any provider'], ['eye', 'none: map & watch']];
    minds.forEach(([ic, label], i) => {
      const a = -Math.PI / 2 + (i / minds.length) * Math.PI * 2, x = CX + Math.cos(a) * 300, y = CY + Math.sin(a) * 210;
      this.line(orbit, CX + Math.cos(a) * 78, CY + Math.sin(a) * 56, x - Math.cos(a) * 44, y - Math.sin(a) * 32, 'rgba(255,181,71,.35)', 200 + i * 200);
      const g = S('g', { class: 'pop', style: `animation-delay:${300 + i * 220}ms` }, orbit);
      const counter = S('g', { style: `transform-origin:${x}px ${y}px;animation:g-spin 48s linear infinite reverse;transform-box:view-box` }, g);
      S('circle', { cx: x, cy: y, r: 38, fill: '#101626', stroke: i === 4 ? 'rgba(255,255,255,.3)' : GOLD, 'stroke-width': 1.6 }, counter);
      this.iconAt(counter, ic, x, y, 28, i === 4 ? '#a8b2c8' : GOLD);
      S('text', { x, y: y + 62, 'text-anchor': 'middle', fill: '#c9d1e3', 'font-size': 15, 'font-weight': 600, text: label }, counter);
    });
    this.fit(l, [CX - 390, CY - 270, CX + 390, CY + 290], 1.35);
    this.say('Any mind can wear the suit.', 'A model on your computer, an API key, a chat window you copy and paste into, or none at all. Weak or strong, the suit keeps the rules.');
    return 5800;
  }
  finale() {
    clearTimeout(this.timer);
    if (!this.cinema) this.top.replaceChildren();          // the intro is over: nothing left to skip
    const l = this.layer();
    S('circle', { cx: CX, cy: 300, r: 420, fill: 'url(#g-halo)', opacity: 0.35 }, l);
    this.say('', '');
    [...this.dots.children].forEach((d) => { d.className = 'done'; });
    const info = this.info;
    const guess = info.empty ? 'build' : (info.objects || []).some((o) => o.kind === 'python_repository' || o.kind === 'node_repository') ? 'improve'
      : (info.objects || []).some((o) => o.kind === 'data_reports') ? 'numbers'
      : (info.objects || []).some((o) => o.kind === 'document_collection') ? 'docs' : 'build';
    let type = guess;
    const name = h('input.big', { placeholder: 'Name your creation', maxlength: 80, value: this.cinema ? '' : (info.onboarded ? info.name : ''), 'aria-label': 'Name' });
    const desc = h('textarea', { placeholder: 'What should it do? Who is it for? (optional: you can say more later)', maxlength: 4000, 'aria-label': 'Description' });
    const types = h('div.types', [['build', 'Build something new', 'wand'], ['improve', 'Improve my code', 'hammer'], ['docs', 'Tend my documents', 'doc'], ['numbers', 'Keep an eye on my numbers', 'gauge'], ['explore', 'Just explore', 'compass']]
      .map(([k, label, ic]) => h('button', { type: 'button', class: k === type ? 'on' : '', 'aria-pressed': String(k === type), dataset: { t: k }, onclick: (e) => { type = k; for (const b of types.children) { b.classList.toggle('on', b.dataset.t === k); b.setAttribute('aria-pressed', String(b.dataset.t === k)); } } }, icon(ic), label)));
    // Space skips ahead in the intro; pressed once too often it must not type leading spaces into the name (J3-F3).
    name.addEventListener('keydown', (e) => { if (e.key === ' ' && !name.value.trim()) { e.preventDefault(); name.value = ''; } });
    const go = h('button.go', { type: 'submit' }, icon('flame'), 'Forge it');
    const form = h('form', h('div.sigil', { html: logoMark({ forge: true }) }), h('h2', 'What will you create?'), h('p.lead', 'Give it a name. Describe it if you like, or leave that for later.'), name, desc, types, go,
      this.cinema ? null : h('button.skip', { type: 'button', onclick: () => this.complete('', '', type, true) }, 'Skip for now'),
      h('div.where', this.cinema ? 'runesmith · open source · any model · evidence first' : `in ${info.path}`));
    const pane = h('div.g-name', form);
    this.el.append(pane);
    this.namePane = pane;
    form.addEventListener('submit', (e) => { e.preventDefault(); if (this.cinema) return; this.complete(name.value.trim(), desc.value.trim(), type, false); });
    if (this.cinema) this.demoType(name, desc, types);
    else setTimeout(() => name.focus(), 300);
    return 0;
  }
  async demoType(name, desc, types) {
    const story = this.info.typed || DEMOS[0].typed;
    const token = this.finaleToken = {};
    const live = () => token === this.finaleToken && document.body.contains(this.el);
    const typeInto = async (el, text, speed) => { el.classList.add('typer'); for (const ch of text) { if (!live()) return; el.value += ch; await sleep(speed + Math.random() * speed); } el.classList.remove('typer'); };
    await sleep(900); if (!live()) return; await typeInto(name, story.name, 70);
    await sleep(400); if (!live()) return; await typeInto(desc, story.description, 26);
    await sleep(500); if (!live()) return; for (const b of types.children) b.classList.toggle('on', b.dataset.t === story.type);
    await sleep(900); if (!live()) return; this.forgeWord(story.name, story.sub);
    await sleep(5200);
    if (live() && this.index === this.scenes.length - 1) {
      this.loops += 1;
      if (this.info.typed) this.info = DEMOS[this.loops % DEMOS.length];     // the next story: another shape and size
      this.announce();
      this.go(0);
    }
  }
  forgeWord(word, sub) {
    this.namePane?.remove();
    const wordEl = h('div.word', [...(word || 'Your creation')].map((ch, i) => h('span', { style: { animationDelay: `${i * 55}ms` } }, ch === ' ' ? ' ' : ch)));
    const box = h('div.forged', h('div', wordEl, h('div.sub', sub)));
    this.el.append(box);
    const l = this.layers[0];
    const r = rng(11);
    for (let i = 0; i < 26; i++) {
      const a = r() * Math.PI * 2, d = 120 + r() * 220;
      this.line(l, CX, CY, CX + Math.cos(a) * d, CY + Math.sin(a) * d * 0.6, i % 2 ? GOLD : EMBER, r() * 500, 1.3, { 'stroke-opacity': 0.6 });
    }
  }
  async complete(name, description, type, skipped) {
    try { await post('/api/genesis', { name, description, use_type: type }); }
    catch (e) { /* the Studio still opens; settings can be set there */ }
    if (!skipped) { this.forgeWord(name || this.info.folder || 'Your creation', 'Mapping its world…'); await sleep(2600); }
    this.el.classList.add('leaving');
    await sleep(1000);
    document.removeEventListener('keydown', this.onKey);
    clearTimeout(this.timer);
    this.resizer?.disconnect();
    this.el.remove();
    this.onDone();
  }
}
