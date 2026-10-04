// Runesmith Studio icons: 24×24, stroked, drawn for this app.
const P = {
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  map: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
  hammer: '<path d="M13.5 4.5l6 6-2.5 2.5-6-6z"/><path d="M11 7l-2-2 3-2 2 2"/><path d="M12.5 11.5L4 20l-1-1 8.5-8.5"/>',
  spark: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  note: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12.5h5"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  right: '<path d="M9 5l7 7-7 7"/>',
  left: '<path d="M15 5l-7 7 7 7"/>',
  down: '<path d="M5 9l7 7 7-7"/>',
  up: '<path d="M5 15l7-7 7 7"/>',
  external: '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
  doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  code: '<path d="M8 4c-2 0-3 1-3 3v3l-2 2 2 2v3c0 2 1 3 3 3M16 4c2 0 3 1 3 3v3l2 2-2 2v3c0 2-1 3-3 3"/>',
  box: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3M18 5l2 2"/>',
  zap: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7a9.8 9.8 0 0 0 4.4-1"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.3" r=".6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.8" r=".6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  branch: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10"/><path d="M18 9a7 7 0 0 1-7 7H8"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  cloud: '<path d="M7 18a5 5 0 0 1-.5-9.97A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z"/>',
  laptop: '<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>',
  chat: '<path d="M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  monitor: '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  flame: '<path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  filter: '<path d="M4 5h16l-6 8v6l-4-2v-4z"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
  send: '<path d="M21 3L10 14M21 3l-7 18-4-7-7-4z"/>',
  command: '<path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  wand: '<path d="M4 20L15 9"/><path d="M14 8l2 2"/><path d="M17 3v3M20 6h-3M19.5 3.5L18 5M12 4v2M20 11h-2"/>',
  anvil: '<path d="M3 7h12c3 0 5 1 6 3-2 1-4 1.5-7 1.5V14h2v4H7v-4h2v-2.5C5.5 11.5 3 10 3 7z"/>',
  rune: '<path d="M12 2l8.5 5v10L12 22l-8.5-5V7z"/><path d="M10 7v10M10 7h3a2.5 2.5 0 0 1 0 5h-3l4.5 5"/>',
  scale: '<path d="M12 4v16M7 20h10M5 7h14"/><path d="M5 7l-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0z"/>',
  gauge: '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-5"/>',
  pencil: '<path d="M4 20l4-1 11-11-3-3L5 16z"/><path d="M14 6l3 3"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/>',
  inbox: '<path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1 2h6l1-2h5"/>',
  filePlus: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M12 11v6M9 14h6"/>',
  power: '<path d="M12 3v8"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  route: '<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h7a3.5 3.5 0 0 0 0-7H9a3.5 3.5 0 0 1 0-7h7"/>',
  beaker: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3"/><path d="M7.5 14h9"/>',
  hourglass: '<path d="M6 3h12M6 21h12M7 3c0 5 5 6 5 9s-5 4-5 9M17 3c0 5-5 6-5 9s5 4 5 9"/>',
  maximize: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  minus: '<path d="M5 12h14"/>',
  crosshair: '<circle cx="12" cy="12" r="8"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h0M10 10h0M14 10h0M18 10h0M7 14h10"/>',
};

export function iconSvg(name, cls = '') {
  const body = P[name] || P.info;
  return `<svg class="ic${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

// The Runesmith mark: a gold stone block with the rune carved through it, its leg breaking out of the bottom edge.
// Every call returns a self-contained SVG with its own gradient ids, so many copies can share a page whether or
// not the first one is visible. { forge: true } fills the carved rune with the dark slate and the heat of the forge.
const MARK_STONE = 'M38 6L82 6C107.6 6 114 12.4 114 38L114 82C114 107.6 107.6 114 82 114L80.9 114L51.9 85L84.9 52L51.9 19L35 19L35 101.9L49 101.9L61.1 114L38 114C12.4 114 6 107.6 6 82L6 38C6 12.4 12.4 6 38 6ZM49 35.9L65.1 52 49 68.1Z';
const MARK_RUNE = 'M80.9 114 51.9 85 84.9 52 51.9 19 35 19 35 101.9 49 101.9 61.1 114Z';
let markCount = 0;
export function logoMark({ forge = false } = {}) {
  const k = `rsm${++markCount}`;
  return `<svg viewBox="0 0 120 120" aria-hidden="true" focusable="false"><defs>` +
    `<linearGradient id="${k}g" x1="0" y1="0" x2="0.35" y2="1"><stop offset="0" stop-color="#f8dc94"/><stop offset="0.45" stop-color="#e8b04a"/><stop offset="1" stop-color="#c58a34"/></linearGradient>` +
    (forge ? `<linearGradient id="${k}d" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d2230"/><stop offset="1" stop-color="#0b0e14"/></linearGradient>` +
      `<radialGradient id="${k}h" cx="0.55" cy="1" r="0.75"><stop offset="0" stop-color="#ff8a3d" stop-opacity="0.85"/><stop offset="0.45" stop-color="#ff6a1f" stop-opacity="0.25"/><stop offset="1" stop-color="#ff6a1f" stop-opacity="0"/></radialGradient>` : '') +
    `</defs>` +
    (forge ? `<path fill="url(#${k}d)" d="${MARK_RUNE}"/><path fill="url(#${k}h)" d="${MARK_RUNE}"/>` : '') +
    `<path fill="url(#${k}g)" d="${MARK_STONE}"/></svg>`;
}

// The wordmark, cut without curves ("runes were cut"); it takes the text colour of its parent.
let wordCount = 0;
export function wordmark() {
  const k = `rsw${++wordCount}`;
  return `<svg viewBox="0 0 746 100" role="img" aria-label="Runesmith" focusable="false"><g fill="currentColor"><clipPath id="${k}"><rect x="-1" y="0" width="748" height="100"/></clipPath><g clip-path="url(#${k})">` +
    '<path fill-rule="evenodd" d="M0 0L27 0 57 30 27 60 67 100 45.79 100 15 69.21 15 100 0 100ZM15 15L20.79 15 35.79 30 15 50.79Z"/>' +
    '<path d="M91 0L91 83.61 107.39 100 140.61 100 157 83.61 157 0 142 0 142 77.39 134.39 85 113.61 85 106 77.39 106 0Z"/>' +
    '<path d="M181 0L196 0 196 100 181 100Z"/><path d="M232 0L247 0 247 100 232 100Z"/><path d="M181 0L197.72 0 247 100 230.28 100Z"/>' +
    '<path d="M331 0L271 0 271 100 331 100 331 85 286 85 286 15 331 15Z"/><path d="M278.5 42.5L325 42.5 325 57.5 278.5 57.5Z"/>' +
    '<path d="M417 0L369.39 0 355 14.39 355 43.11 369.39 57.5 396.39 57.5 402 63.11 402 79.39 396.39 85 355 85 355 100 402.61 100 417 85.61 417 56.89 402.61 42.5 375.61 42.5 370 36.89 370 20.61 375.61 15 417 15Z"/>' +
    '<path d="M441 0L456 0 456 100 441 100Z"/><path d="M510 0L525 0 525 100 510 100Z"/><path d="M441.59 -9.09L483 89.34 524.41 -9.09 510.59 -14.91 483 50.66 455.41 -14.91Z"/>' +
    '<path d="M549 0L564 0 564 100 549 100Z"/><path d="M588 0L656 0 656 15 588 15Z"/><path d="M614.5 0L629.5 0 629.5 100 614.5 100Z"/>' +
    '<path d="M680 0L695 0 695 100 680 100Z"/><path d="M731 0L746 0 746 100 731 100Z"/><path d="M695 42.5L731 42.5 731 57.5 695 57.5Z"/></g></g></svg>';
}
