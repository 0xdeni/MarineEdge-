/* Shared UI helpers: escaping, formatting, icons, toasts, action sheets, draggable sheets, pages. */
'use strict';

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const reduceMotion = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/* ---------------------------------------------------------------- formatting */
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const Fmt = {
  utc: true,                                 // maritime convention; Profile › Preferences can switch to local time
  parts(t) {
    const d = new Date(t);
    return this.utc ? { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes() }
      : { y: d.getFullYear(), m: d.getMonth(), d: d.getDate(), h: d.getHours(), mi: d.getMinutes() };
  },
  tz() { return this.utc ? 'UTC' : ''; },
  day(t, withYear) { if (t == null) return '—'; const p = this.parts(t); const y = withYear || p.y !== this.parts(Date.now()).y; return `${p.d} ${MON[p.m]}${y ? ' ' + p.y : ''}`; },
  month(t) { const p = this.parts(t); return `${MONTH[p.m]} ${p.y}`; },
  time(t) { const p = this.parts(t); return `${String(p.h).padStart(2, '0')}:${String(p.mi).padStart(2, '0')}`; },
  dayTime(t) { return `${this.day(t)}, ${this.time(t)}${this.utc ? ' UTC' : ''}`; },
  range(t0, t1) {
    if (t1 == null || Math.abs(t1 - t0) < 12 * 3600e3 && this.parts(t0).d === this.parts(t1).d) return this.day(t0);
    const a = this.parts(t0), b = this.parts(t1), now = this.parts(Date.now());
    const yb = b.y !== now.y ? ' ' + b.y : '';
    if (a.y === b.y && a.m === b.m) return `${a.d} – ${b.d} ${MON[b.m]}${yb}`;
    if (a.y === b.y) return `${a.d} ${MON[a.m]} – ${b.d} ${MON[b.m]}${yb}`;
    return `${a.d} ${MON[a.m]} ${a.y} – ${b.d} ${MON[b.m]} ${b.y}`;
  },
  ago(t) {
    if (!t) return 'never';
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 45) return 'just now';
    if (s < 90) return 'a minute ago';
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 5400) return 'an hour ago';
    if (s < 86400) return `${Math.round(s / 3600)} hours ago`;
    if (s < 172800) return 'yesterday';
    if (s < 30 * 86400) return `${Math.round(s / 86400)} days ago`;
    return this.day(t, true);
  },
  hours(h) { if (h == null) return '—'; if (h < 1) return `${Math.round(h * 60)} min`; if (h < 48) return `${Math.round(h)} h`; const d = h / 24; return `${d < 10 ? d.toFixed(1) : Math.round(d)} days`; },
  dur(ms) { return this.hours(ms / 3600e3); },
  n(v) { return v == null ? '—' : Number(v).toLocaleString('en-US'); },
  nm(v) { return v == null ? '—' : `${Number(Math.round(v)).toLocaleString('en-US')} nm`; },
  dm(lat, lon) {
    const f = (v, pos, neg, w) => { const a = Math.abs(v); const d = Math.floor(a); const m = (a - d) * 60; return `${String(d).padStart(w, '0')}°${m.toFixed(1).padStart(4, '0')}′${v >= 0 ? pos : neg}`; };
    return `${f(lat, 'N', 'S', 2)} ${f(lon, 'E', 'W', 3)}`;
  },
  bytes(b) { if (!b) return '0 KB'; if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`; if (b >= 1e6) return `${(b / 1e6).toFixed(b >= 1e7 ? 0 : 1)} MB`; return `${Math.max(1, Math.round(b / 1e3))} KB`; },
  plural(n, one, many) { return `${n} ${n === 1 ? one : (many || one + 's')}`; },
};

/* ---------------------------------------------------------------- icons (SF Symbols–like, 24 grid) */
const I = (d, opts = {}) => `<svg width="${opts.s || 22}" height="${opts.s || 22}" viewBox="0 0 24 24" fill="${opts.fill || 'none'}" stroke="${opts.fill ? 'none' : 'currentColor'}" stroke-width="${opts.w || 1.9}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICON = {
  search: (s = 18) => I('<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>', { s, w: 2.4 }),
  x: (s = 14) => I('<path d="M5 5l14 14M19 5L5 19"/>', { s, w: 2.6 }),
  back: (s = 20) => I('<path d="M15.5 4L7.5 12l8 8"/>', { s, w: 2.6 }),
  chev: (s = 14) => I('<path d="M9 5l7 7-7 7"/>', { s, w: 2.4 }),
  down: (s = 12) => I('<path d="M5 9l7 7 7-7"/>', { s, w: 2.6 }),
  star: (s = 21) => I('<path d="M12 2.8l2.84 5.76 6.36.92-4.6 4.49 1.09 6.33L12 17.3l-5.69 2.99 1.09-6.33-4.6-4.49 6.36-.92z"/>', { s, w: 1.8 }),
  starFill: (s = 21) => I('<path d="M12 2.8l2.84 5.76 6.36.92-4.6 4.49 1.09 6.33L12 17.3l-5.69 2.99 1.09-6.33-4.6-4.49 6.36-.92z"/>', { s, fill: 'currentColor' }),
  share: (s = 20) => I('<path d="M12 3.5v11"/><path d="M8 7.5l4-4 4 4"/><path d="M8.5 10.5H6v10h12v-10h-2.5"/>', { s, w: 1.9 }),
  bell: (s = 20) => I('<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2H4.5z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>', { s }),
  person: (s = 20) => I('<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c1.2-4 4.2-6 7.5-6s6.3 2 7.5 6"/>', { s }),
  gear: (s = 20) => I('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>', { s, w: 1.8 }),
  ship: (s = 22) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M2 14h20l-3.2 5.2a1.6 1.6 0 0 1-1.36.8H6.4a1.6 1.6 0 0 1-1.36-.8z"/><path d="M5 13V9.6c0-.33.27-.6.6-.6h4.8c.33 0 .6.27.6.6V13z"/><rect x="6.4" y="5.5" width="1.6" height="3.5" rx="0.6"/></svg>`,
  warn: (s = 18) => I('<path d="M12 3.5L2.5 20h19z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.3" r="0.6" fill="currentColor"/>', { s, w: 2 }),
  excl: (s = 14) => `<svg width="${s}" height="${s}" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="8.5" fill="currentColor"/><path d="M9 4.6v5.4" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/><circle cx="9" cy="13.2" r="1.3" fill="#fff"/></svg>`,
  tri: (s = 14) => `<svg width="${s}" height="${s * 13 / 14}" viewBox="0 0 14 13" aria-hidden="true"><path d="M7 1L13.2 12H0.8Z" fill="currentColor"/></svg>`,
  okc: (s = 14) => `<svg width="${s}" height="${s}" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="7" fill="currentColor"/><path d="M4 7.2l2 2 4-4.3" fill="none" stroke="var(--sheet-solid)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  dashc: (s = 14) => `<svg width="${s}" height="${s}" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="7.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="2.6 2.2"/></svg>`,
  check: (s = 18) => I('<path d="M4.5 12.5l5 5 10-11"/>', { s, w: 2.4 }),
  lock: (s = 17) => I('<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>', { s, w: 1.9 }),
  mail: (s = 17) => I('<rect x="3" y="5.5" width="18" height="13" rx="2.5"/><path d="M3.5 7l8.5 6 8.5-6"/>', { s, w: 1.9 }),
  eye: (s = 20) => I('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>', { s, w: 1.8 }),
  eyeOff: (s = 20) => I('<path d="M3 3l18 18"/><path d="M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-3.1 4.1M6.6 6.6C3.7 8.5 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>', { s, w: 1.8 }),
  people: (s = 20) => I('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 19.5c.9-3.4 3.4-5 6.5-5s5.6 1.6 6.5 5"/><circle cx="17" cy="9" r="2.6"/><path d="M17 14c2.3 0 4 1.2 4.6 3.6"/>', { s, w: 1.8 }),
  plus: (s = 18) => I('<path d="M12 5v14M5 12h14"/>', { s, w: 2.4 }),
  trash: (s = 18) => I('<path d="M4 7h16"/><path d="M9.5 7V4.5h5V7"/><path d="M6.5 7l1 13h9l1-13"/>', { s, w: 1.9 }),
  pencil: (s = 16) => I('<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/>', { s, w: 2 }),
  doc: (s = 18) => I('<path d="M6 2.5h8l4.5 4.5V21a.5.5 0 0 1-.5.5H6a.5.5 0 0 1-.5-.5V3a.5.5 0 0 1 .5-.5z"/><path d="M14 2.5V7h4.5"/><path d="M8.5 12h7M8.5 15.5h7"/>', { s, w: 1.8 }),
  globe: (s = 18) => I('<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z"/>', { s, w: 1.7 }),
  ext: (s = 15) => I('<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>', { s, w: 2 }),
  sun: (s = 18) => I('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>', { s, w: 1.9 }),
  shield: (s = 18) => I('<path d="M12 2.5l8 3v6c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10v-6z"/>', { s, w: 1.9 }),
  server: (s = 18) => I('<rect x="3.5" y="4" width="17" height="7" rx="2"/><rect x="3.5" y="13" width="17" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>', { s, w: 2 }),
  antenna: (s = 18) => I('<circle cx="12" cy="12" r="2"/><path d="M8 8a5.7 5.7 0 0 0 0 8M16 8a5.7 5.7 0 0 1 0 8M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>', { s, w: 1.9 }),
  sliders: (s = 18) => I('<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>', { s, w: 1.9 }),
  pin: (s = 18) => I('<path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21z"/><circle cx="12" cy="9.8" r="2.3"/>', { s, w: 1.9 }),
  info: (s = 18) => I('<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.6" r="0.6" fill="currentColor"/>', { s, w: 1.9 }),
  logout: (s = 18) => I('<path d="M14 4h4.5a1.5 1.5 0 0 1 1.5 1.5v13a1.5 1.5 0 0 1-1.5 1.5H14"/><path d="M10 8l-4 4 4 4"/><path d="M6 12h10"/>', { s, w: 1.9 }),
  refresh: (s = 18) => I('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>', { s, w: 2 }),
  copy: (s = 18) => I('<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>', { s, w: 1.9 }),
  link: (s = 18) => I('<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>', { s, w: 1.9 }),
  key: (s = 18) => I('<circle cx="8" cy="15" r="4.5"/><path d="M11.2 11.8L20 3M17 6l2.5 2.5M14.5 8.5l2 2"/>', { s, w: 1.9 }),
  clock: (s = 18) => I('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>', { s, w: 1.9 }),
  map: (s = 18) => I('<path d="M3.5 6.5l5.5-2.5 6 2.5 5.5-2.5v13.5l-5.5 2.5-6-2.5-5.5 2.5z"/><path d="M9 4v13.5M15 6.5V20"/>', { s, w: 1.8 }),
  note: (s = 18) => I('<path d="M13.5 4.5H6A1.5 1.5 0 0 0 4.5 6v12A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-7.5"/><path d="M17.8 3.2a1.9 1.9 0 0 1 2.7 2.7L12.5 14l-3.3.6.6-3.3z"/>', { s, w: 1.8 }),
  fit: (s = 18) => I('<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>', { s, w: 2 }),
  arrowR: (s = 16) => I('<path d="M4 12h15M13 6l6 6-6 6"/>', { s, w: 2.2 }),
  download: (s = 18) => I('<path d="M12 3.5v11"/><path d="M7.5 10l4.5 4.5 4.5-4.5"/><path d="M4.5 19.5h15"/>', { s, w: 2 }),
  iphone: (s = 18) => I('<rect x="6.5" y="2.5" width="11" height="19" rx="2.5"/><path d="M10.5 5h3"/>', { s, w: 1.9 }),
  layers: (s = 18) => I('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>', { s, w: 1.9 }),
  wave: (s = 18) => I('<path d="M2 15c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2"/><path d="M2 19c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2"/><path d="M12 3v7M9 6l3-3 3 3"/>', { s, w: 1.8 }),
};
const LEVEL_ICON = { high: () => ICON.excl(13), review: () => ICON.tri(13), clear: () => ICON.okc(13), insufficient: () => ICON.dashc(13) };
const LEVEL_LABEL = { high: 'High risk', review: 'Review', clear: 'No red flags', insufficient: 'Not enough history' };
function vbadge(level, label) {
  if (!level) return `<span class="vb none">${ICON.dashc(13)}Not checked</span>`;
  return `<span class="vb ${esc(level)}">${LEVEL_ICON[level] ? LEVEL_ICON[level]() : ''}${esc(label || LEVEL_LABEL[level] || level)}</span>`;
}

/* the logo mark, inline (also animates on the welcome screen) */
function logoSVG(size = 76, id = 'lg') {
  return `<svg class="logo" width="${size}" height="${size}" viewBox="0 0 512 512" aria-hidden="true">
  <defs>
    <linearGradient id="${id}Bg" x1="0" y1="0" x2="0.4" y2="1"><stop offset="0" stop-color="#12304F"/><stop offset="0.55" stop-color="#0A1A2E"/><stop offset="1" stop-color="#050C17"/></linearGradient>
    <radialGradient id="${id}Glow" cx="0.28" cy="0.18" r="0.75"><stop offset="0" stop-color="#3D7BC4" stop-opacity="0.35"/><stop offset="1" stop-color="#3D7BC4" stop-opacity="0"/></radialGradient>
    <linearGradient id="${id}Trk" x1="110" y1="0" x2="400" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.38"/><stop offset="0.55" stop-color="#FFFFFF" stop-opacity="0.85"/><stop offset="1" stop-color="#FFFFFF"/></linearGradient>
    <linearGradient id="${id}Dot" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#64D2FF"/><stop offset="1" stop-color="#0A84FF"/></linearGradient>
    <clipPath id="${id}Clip"><rect width="512" height="512" rx="115"/></clipPath>
  </defs>
  <g clip-path="url(#${id}Clip)"><g class="lg-tilebox"><rect width="512" height="512" fill="url(#${id}Bg)"/><rect width="512" height="512" fill="url(#${id}Glow)"/></g></g>
  <path class="lg-track" pathLength="1" d="M112 346 C 138 288, 158 172, 192 172 C 230 172, 228 278, 256 278 C 284 278, 282 172, 320 172 C 354 172, 370 268, 384 318" fill="none" stroke="url(#${id}Trk)" stroke-width="38" stroke-linecap="round" stroke-linejoin="round"/>
  <circle class="lg-ping" cx="392" cy="342" r="34" fill="none" stroke="#64D2FF" stroke-width="6"/>
  <g class="lg-ring"><circle cx="392" cy="342" r="34" fill="#FFFFFF"/><circle cx="392" cy="342" r="19" fill="url(#${id}Dot)"/></g>
</svg>`;
}

/* ---------------------------------------------------------------- toasts */
function toast(msg, kind = '') {
  const box = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.setAttribute('role', kind === 'err' ? 'alert' : 'status');
  el.innerHTML = (kind === 'ok' ? ICON.check(16) : kind === 'err' ? ICON.warn(16) : '') + `<span>${esc(msg)}</span>`;
  box.appendChild(el);
  const life = Math.min(6000, 2200 + msg.length * 35);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, life);
}

/* ---------------------------------------------------------------- action sheet (confirmations, choices) */
function actionSheet({ title = '', message = '', actions = [], cancel = 'Cancel' }) {
  return new Promise(resolve => {
    const scrim = document.createElement('div'); scrim.className = 'scrim';
    const sh = document.createElement('div'); sh.className = 'asheet'; sh.setAttribute('role', 'dialog'); sh.setAttribute('aria-modal', 'true');
    sh.innerHTML = `<div class="ag">${title || message ? `<div class="ah">${title ? `<div class="t">${esc(title)}</div>` : ''}${message ? `<div class="m">${esc(message)}</div>` : ''}</div>` : ''}
      ${actions.map((a, i) => `<button class="ab ${a.destructive ? 'destructive' : ''} ${a.bold ? 'b' : ''}" data-i="${i}">${esc(a.label)}</button>`).join('')}</div>
      <div class="cancel ag"><button class="ab" data-i="-1">${esc(cancel)}</button></div>`;
    document.body.append(scrim, sh);
    requestAnimationFrame(() => { scrim.classList.add('on'); sh.classList.add('on'); });
    const close = v => { scrim.classList.remove('on'); sh.classList.remove('on'); setTimeout(() => { scrim.remove(); sh.remove(); }, 420); resolve(v); };
    scrim.addEventListener('click', () => close(null));
    sh.addEventListener('click', e => { const b = e.target.closest('[data-i]'); if (!b) return; const i = +b.dataset.i; close(i < 0 ? null : (actions[i].value !== undefined ? actions[i].value : i)); });
    const first = sh.querySelector('.ab'); if (first) first.focus({ preventScroll: true });
  });
}

/* ---------------------------------------------------------------- share / copy */
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; } ta.remove(); return ok;
  }
}
async function shareOrCopy({ title, text, url }) {
  if (navigator.share) {
    try { await navigator.share({ title, text, url }); return 'shared'; } catch (e) { if (e && e.name === 'AbortError') return 'cancelled'; }
  }
  return (await copyText(url || text)) ? 'copied' : 'failed';
}

/* ---------------------------------------------------------------- busy buttons */
async function busy(btn, fn) {
  if (!btn) return fn();
  if (btn.classList.contains('loading')) return undefined;
  btn.classList.add('loading'); btn.setAttribute('aria-busy', 'true');
  let sp = btn.querySelector(':scope > .spin');
  const added = !sp;
  if (added) { sp = document.createElement('span'); sp.className = 'spin'; sp.setAttribute('aria-hidden', 'true'); if (btn.classList.contains('row')) btn.append(sp); else btn.prepend(sp); }
  try { return await fn(); } finally {
    btn.classList.remove('loading'); btn.removeAttribute('aria-busy');
    if (added && !btn.classList.contains('btn')) sp.remove();     // buttons keep a hidden spinner; rows and links don't
  }
}

/* ---------------------------------------------------------------- draggable bottom sheet with detents */
class Sheet {
  /* detents: { name: visibleHeightPx | fn() }; the sheet's top sits at (viewport height - visible) */
  constructor(el, { detents, initial = null, onChange = null, onDrag = null }) {
    this.el = el; this.detents = detents; this.onChange = onChange; this.onDrag = onDrag; this.pos = null; this.shown = false;
    this.handle = el.querySelector('.grab'); this.head = el.querySelector('.head'); this.body = el.querySelector('.body');
    this._wire();
    if (initial) this.snap(initial, false);
    window.addEventListener('resize', () => { if (this.pos) this.snap(this.pos, false); });
  }
  vh() { return this.el.offsetHeight; }
  vis(name) { const d = this.detents[name]; return typeof d === 'function' ? d() : d; }
  yFor(name) { return Math.max(0, this.vh() - this.vis(name)); }
  current() { return this.pos; }
  visible() { return this.shown ? this.vh() - this._y : 0; }
  snap(name, animate = true) {
    if (!(name in this.detents)) return;
    const y = this.yFor(name);
    this._y = y; this.pos = name; this.shown = true;
    this.el.style.setProperty('--y', `${y}px`);
    if (!animate) { this.el.style.transition = 'none'; }
    if (reduceMotion() && animate && this.el.dataset.rmFade !== '0') {
      this.el.style.transform = `translateY(${y}px)`;
    } else {
      this.el.style.transform = `translateY(${y}px)`;
    }
    this.el.style.opacity = '';
    if (!animate) { void this.el.offsetHeight; this.el.style.transition = ''; }
    if (this.body) {
      const locked = name !== 'full' && name !== this.scrollDetent;
      this.body.classList.toggle('locked', locked);
      if (locked && this.body.scrollTop) this.body.scrollTo({ top: 0, behavior: animate && !reduceMotion() ? 'smooth' : 'auto' });   // collapsed: show the top again
    }
    this.onChange && this.onChange(name, this.vh() - y);
  }
  hide(animate = true) {
    this.shown = false; this.pos = null;
    if (!animate) this.el.style.transition = 'none';
    if (reduceMotion() && animate) { this.el.style.opacity = '0'; setTimeout(() => { if (!this.shown) this.el.style.transform = 'translateY(calc(100% + 60px))'; }, 240); }
    else this.el.style.transform = 'translateY(calc(100% + 60px))';
    if (!animate) { void this.el.offsetHeight; this.el.style.transition = ''; }
    this.onChange && this.onChange(null, 0);
  }
  _wire() {
    let startY = 0, y0 = 0, lastY = 0, lastT = 0, vel = 0, tracking = false, moved = false, pid = null;
    // a drag can start on the grabber, the header, or the content while the content can't scroll (below the top detent)
    const canDrag = e => {
      if (!this.shown || e.button > 0) return false;
      if (e.target.closest('input, textarea, select, .noDrag, .maplibregl-map')) return false;
      if (this.body && this.body.contains(e.target) && !this.body.classList.contains('locked')) return false;
      return true;
    };
    const down = e => {
      if (!canDrag(e)) return;
      tracking = true; moved = false; pid = e.pointerId; startY = lastY = e.clientY; lastT = performance.now(); y0 = this._y; vel = 0;
    };
    const move = e => {
      if (!tracking || e.pointerId !== pid) return;
      const dy = e.clientY - startY;
      if (!moved && Math.abs(dy) < 8) return;
      if (!moved) { moved = true; this.el.classList.add('dragging'); try { this.el.setPointerCapture(pid); } catch (err) { /* already released */ } }
      const minY = this.yFor(this._maxDetent());
      let y = y0 + dy;
      if (y < minY) y = minY - Math.pow(minY - y, 0.7);        // rubber band above the top detent
      const now = performance.now(); vel = (e.clientY - lastY) / Math.max(1, now - lastT); lastY = e.clientY; lastT = now;
      this._y = y; this.el.style.transform = `translateY(${y}px)`;
      this.onDrag && this.onDrag(this.vh() - y);
    };
    const up = e => {
      if (!tracking || (e && e.pointerId !== pid)) return;
      tracking = false;
      if (!moved) return;
      this.el.classList.remove('dragging');
      this._noClick = true; setTimeout(() => { this._noClick = false; }, 350);   // the drag was not a tap on whatever it started on
      const names = Object.keys(this.detents).filter(n => this.detentAllowed ? this.detentAllowed(n) : true);
      const proj = this._y + vel * 180;                         // where the flick would carry it
      let best = names[0], bd = Infinity;
      for (const n of names) { const d = Math.abs(this.yFor(n) - proj); if (d < bd) { bd = d; best = n; } }
      if (this.dismissible && proj > this.vh() - this.vis(names.reduce((a, b) => this.vis(a) < this.vis(b) ? a : b)) + 80) { this.hide(); this.onDismiss && this.onDismiss(); return; }
      this.snap(best);
    };
    this.el.addEventListener('pointerdown', down);
    this.el.addEventListener('pointermove', move);
    this.el.addEventListener('pointerup', up);
    this.el.addEventListener('pointercancel', up);
    this.el.addEventListener('click', e => { if (this._noClick) { e.stopPropagation(); e.preventDefault(); this._noClick = false; } }, true);
    // pulling down from the top of the scrolled content collapses the sheet, like iOS
    if (this.body) {
      let ty = null;
      this.body.addEventListener('touchstart', e => { ty = this.body.scrollTop <= 0 ? e.touches[0].clientY : null; }, { passive: true });
      this.body.addEventListener('touchmove', e => {
        if (ty == null || this.pos !== 'full') return;
        if (e.touches[0].clientY - ty > 70 && this.body.scrollTop <= 0) {
          ty = null; const lower = this._lowerDetent();
          if (lower) this.snap(lower); else if (this.dismissible) { this.hide(); this.onDismiss && this.onDismiss(); }
        }
      }, { passive: true });
    }
  }
  _maxDetent() { return Object.keys(this.detents).reduce((a, b) => this.vis(a) > this.vis(b) ? a : b); }
  _lowerDetent() {
    const names = Object.keys(this.detents).filter(n => !this.detentAllowed || this.detentAllowed(n)).sort((a, b) => this.vis(b) - this.vis(a));
    const i = names.indexOf(this.pos); return i >= 0 ? names[i + 1] || null : null;
  }
}

/* ---------------------------------------------------------------- pushed pages (profile and settings) */
const Pages = {
  stack: [],
  root() { return $('#pages'); },
  push({ id, title, render, modal = false, large = true, right = '' }) {
    const el = document.createElement('section');
    el.className = `page${modal ? ' modal' : ''}`;
    el.dataset.id = id;
    el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', title);
    const backLabel = this.stack.length ? (this.stack[this.stack.length - 1].title || 'Back') : 'Map';
    el.innerHTML = `<header class="navbar"><div class="bar">${modal ? `<button class="back" data-nav="close">${'Close'}</button>` : `<button class="back" data-nav="back" aria-label="Back to ${esc(backLabel)}">${ICON.back(20)}<span>${esc(backLabel.length > 12 ? 'Back' : backLabel)}</span></button>`}
      <div class="mid">${esc(title)}</div><div class="right">${right}</div></div></header>
      <div class="scroll">${large ? `<h1 class="t-large ltitle">${esc(title)}</h1>` : ''}<div class="pc"></div></div>`;
    this.root().appendChild(el);
    const entry = { id, title, el, render };
    const prev = this.stack[this.stack.length - 1];
    this.stack.push(entry);
    const sc = el.querySelector('.scroll'), nb = el.querySelector('.navbar');
    sc.addEventListener('scroll', () => nb.classList.toggle('solid', sc.scrollTop > (large ? 38 : 2)), { passive: true });
    if (!large) nb.classList.add('solid');
    el.addEventListener('click', e => { const b = e.target.closest('[data-nav]'); if (b) { e.preventDefault(); App.back(); } });
    this.refresh(entry);
    requestAnimationFrame(() => requestAnimationFrame(() => { el.classList.add('in'); if (prev) prev.el.classList.add('under'); }));
    return entry;
  },
  async refresh(entry = this.stack[this.stack.length - 1]) {
    if (!entry) return;
    try { await entry.render(entry.el.querySelector('.pc'), entry); } catch (e) { console.error(e); entry.el.querySelector('.pc').innerHTML = `<div class="empty"><h3>Couldn't load this page</h3><p>${esc(e.message || e)}</p></div>`; }
  },
  pop() {
    const top = this.stack.pop(); if (!top) return false;
    top.el.classList.remove('in');
    const prev = this.stack[this.stack.length - 1]; if (prev) { prev.el.classList.remove('under'); }
    setTimeout(() => top.el.remove(), 500);
    return true;
  },
  clear() { while (this.stack.length) { const p = this.stack.pop(); p.el.classList.remove('in'); const el = p.el; setTimeout(() => el.remove(), 500); } },
  top() { return this.stack[this.stack.length - 1]; },
};
