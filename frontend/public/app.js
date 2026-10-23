/* =====================================================================================
   MarineEdge — app shell: chart engine, glass sheet, tab pages (Chart, Vessels,
   Alerts, Reports, Profile/Settings), login, report overlay.
   ===================================================================================== */
'use strict';
const $ = s => document.querySelector(s);
const REGIONS = {
  blacksea: { label: 'Black Sea', bounds: [27.2, 40.6, 42.0, 47.4], geo: 'A' },
  hormuz:   { label: 'Hormuz', bounds: [55.3, 25.3, 57.7, 27.5], geo: 'B' },
  iran:     { label: 'Iran', bounds: [48.0, 24.4, 61.8, 31.0], geo: 'B' },
  oman:     { label: 'Oman', bounds: [52.8, 16.0, 62.6, 26.9], geo: 'B' },
  uae:      { label: 'UAE', bounds: [51.3, 23.6, 57.3, 26.6], geo: 'B' },
};
const TYPES = [['all', 'All'], ['tanker', 'Tankers'], ['bulk', 'Bulk'], ['container', 'Container'], ['gas', 'Gas'], ['other', 'Other']];
const PAGES = ['chart', 'vessels', 'alerts', 'reports', 'profile'];
const S = { page: 'chart', mode: 'region', region: 'blacksea', imo: null, voyage: null, vtab: 'voyages', query: '', type: 'all', flaggedOnly: false, focusFlag: null, vseg: 'watch', pview: 'root', loading: true };
const LIVE = []; // analysed fleet
const store = {
  get(k, d) { try { const v = localStorage.getItem('vvt.' + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('vvt.' + k, JSON.stringify(v)); } catch (e) { /* per-viewer convenience only */ } },
  del(k) { try { localStorage.removeItem('vvt.' + k); } catch (e) {} },
};
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
const isMobile = () => matchMedia('(max-width: 899px)').matches;
const SET = Object.assign({ provider: 'mock', apiKey: '', theme: 'system', timeLocal: false, portLabels: true, graticule: true, reduceTransparency: false, notify: { flags: true, sanctions: true, digest: false, gaps: true }, zonesOff: [], baseMap: true }, store.get('settings', {}));
const ICON = {
  chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"><path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20z"/><path d="M9 4v13.5M15 6.5V20"/></svg>',
  vessels: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"><path d="M3 14h18l-2.5 5h-13z"/><path d="M6 14V9h12v5M10 9V5h4v4"/><path d="M2 19.5c2 1.5 4 1.5 6 0 2 1.5 4 1.5 6 0 2 1.5 4 1.5 6 0"/></svg>',
  alerts: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>',
  reports: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h6M10 16h6"/></svg>',
  profile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"><circle cx="12" cy="8.5" r="4"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/></svg>',
  chevR: '<svg viewBox="0 0 8 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 1.5 6.5 7l-5 5.5"/></svg>',
  chevL: '<svg viewBox="0 0 14 22" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2 3 11l8 9"/></svg>',
  check: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5 8.5 15 16 6"/></svg>',
  key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="14" r="4"/><path d="M11 11l9-9M16 6l2 2M13 9l2 2"/></svg>',
  rules: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h10M18 7h2M4 12h4M12 12h8M4 17h12M20 17h0"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="17" r="2"/></svg>',
  zones: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 6 10 4l6 2 4-1.5v13L16 19l-6-2-6 2z" stroke-dasharray="3 2"/></svg>',
  look: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/></svg>',
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
  logo: '<svg viewBox="0 0 26 26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 18c3 2 6 2 9 0s6-2 9 0"/><path d="M7 15 13 4l6 11"/><circle cx="13" cy="12" r="1.6" fill="currentColor" stroke="none"/></svg>',
};

/* ------------------------------------ chart engine ------------------------------------ */
const mY = lat => Math.log(Math.tan(Math.PI / 4 + lat * RAD / 2)) / RAD;
const mLat = y => (2 * Math.atan(Math.exp(y * RAD)) - Math.PI / 2) / RAD;
const LAND = {};
for (const key of ['A', 'B']) LAND[key] = GEO.regions[key].land.map(ring => ({ pts: ring.map(([lon, lat]) => [lon, mY(lat)]), bbox: ring.reduce((b, [lon, lat]) => [Math.min(b[0], lon), Math.min(b[1], lat), Math.max(b[2], lon), Math.max(b[3], lat)], [999, 999, -999, -999]) }));
const LAND_EXTENT = {};   // charted extent per region: the union of its land rings' bounding boxes
for (const key of ['A', 'B']) LAND_EXTENT[key] = LAND[key].reduce((b, r) => [Math.min(b[0], r.bbox[0]), Math.min(b[1], r.bbox[1]), Math.max(b[2], r.bbox[2]), Math.max(b[3], r.bbox[3])], [999, 999, -999, -999]);
const ZONES_M = GEO.zones.map(z => ({ z, pts: z.poly.map(([lon, lat]) => [lon, mY(lat)]), c: z.poly.reduce((a, p) => [a[0] + p[0] / z.poly.length, a[1] + p[1] / z.poly.length], [0, 0]) }));

const Chart = {
  cv: null, ctx: null, w: 0, h: 0, dpr: 1, cx: 35, cy: mY(43.5), scale: 40, anim: null,
  init(canvas) { this.cv = canvas; this.ctx = canvas.getContext('2d'); new ResizeObserver(() => this.resize()).observe(canvas.parentElement); this.resize(); },
  resize() { const r = this.cv.parentElement.getBoundingClientRect(); this.w = Math.max(1, r.width); this.h = Math.max(1, r.height); this.dpr = Math.min(2.5, devicePixelRatio || 1); this.cv.width = Math.round(this.w * this.dpr); this.cv.height = Math.round(this.h * this.dpr); Base.resize(); this.draw(); },
  px(lon, y) { return [(lon - this.cx) * this.scale + this.w / 2, (this.cy - y) * this.scale + this.h / 2]; },
  get base() { return Base.active && this === Chart; },
  project(lon, lat) { return this.base ? Base.project(lon, lat) : this.px(lon, mY(lat)); },
  unproject(x, y) { return this.base ? Base.unproject(x, y) : [this.cx + (x - this.w / 2) / this.scale, mLat(this.cy - (y - this.h / 2) / this.scale)]; },
  bounds() { if (this.base) return Base.bounds(); const a = this.unproject(0, this.h), b = this.unproject(this.w, 0); return [a[0], a[1], b[0], b[1]]; },
  pad() { if (!isMobile()) return { t: 70, r: 470, b: 40, l: 90 }; const sh = Sheet.target ?? $('#sheet').getBoundingClientRect().height; return { t: 118, r: 20, b: Math.min(sh + 64 + 42, this.h * 0.62), l: 20 }; },
  fitBounds(b, animate = true) {
    const p = this.pad();
    if (this.base) { Base.fitBounds(b, p, animate && !reduceMotion.matches); return; }
    const W = Math.max(40, this.w - p.l - p.r), Hh = Math.max(40, this.h - p.t - p.b);
    const y0 = mY(b[1]), y1 = mY(b[3]);
    const scale = Math.min(W / Math.max(0.01, b[2] - b[0]), Hh / Math.max(0.01, y1 - y0));
    const cx = (b[0] + b[2]) / 2 + ((p.r - p.l) / 2) / scale, cy = (y0 + y1) / 2 + ((p.t - p.b) / 2) / scale;
    this.goTo(cx, cy, Math.max(6, Math.min(3000, scale)), animate);
  },
  goTo(cx, cy, scale, animate) {
    if (!animate || reduceMotion.matches) { this.cx = cx; this.cy = cy; this.scale = scale; this.draw(); onMoveEnd(); return; }
    const s0 = { cx: this.cx, cy: this.cy, scale: this.scale }, t0 = performance.now(), dur = 340;
    cancelAnimationFrame(this.anim);
    const step = now => { const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3); this.cx = s0.cx + (cx - s0.cx) * e; this.cy = s0.cy + (cy - s0.cy) * e; this.scale = s0.scale * Math.pow(scale / s0.scale, e); this.draw(); if (k < 1) this.anim = requestAnimationFrame(step); else onMoveEnd(); };
    this.anim = requestAnimationFrame(step);
  },
  zoomAt(x, y, f) { if (this.base) { Base.zoomBy(f, [x, y]); return; } const [lon, lat] = this.unproject(x, y); this.scale = Math.max(6, Math.min(3000, this.scale * f)); const [nx, ny] = this.project(lon, lat); this.cx += (nx - x) / this.scale; this.cy -= (ny - y) / this.scale; this.draw(); },
  theme() { const c = getComputedStyle(document.documentElement); const g = n => c.getPropertyValue(n).trim(); return { water: g('--water'), land: g('--land'), coast: g('--coast'), grid: g('--grid'), label: g('--label'), zone: g('--zone'), zoneLine: g('--zone-line'), fg: g('--fg'), bg: g('--surface'), accent: g('--accent'), high: g('--high'), medium: g('--medium'), info: g('--info'), types: { tanker: g('--t-tanker'), bulk: g('--t-bulk'), container: g('--t-container'), gas: g('--t-gas'), other: g('--t-other') }, v: [0, 1, 2, 3, 4, 5, 6, 7].map(i => g('--v' + i)) }; },
  draw(ctx = this.ctx, view = this) {
    const T = this.theme(); const tiles = view === this && Base.active && Base.ready;
    if (view === this && Base.active) this.scale = Base.pxPerDegLon();
    ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
    if (tiles) ctx.clearRect(0, 0, view.w, view.h); else { ctx.fillStyle = T.water; ctx.fillRect(0, 0, view.w, view.h); }
    if (!tiles) this.drawLand(ctx, view, T);
    if (SET.graticule && !tiles) this.drawGraticule(ctx, view, T, false);
    this.drawZones(ctx, view, T);
    if (S.mode === 'vessel' || S.mode === 'voyage') this.drawVessel(ctx, view, T); else this.drawFleet(ctx, view, T);
    if (ctx === this.ctx) this.updateReadout();
  },
  drawGraticule(ctx, view, T, linesOnly) {
    const b = view.bounds(); const step = view.scale > 400 ? 0.5 : view.scale > 150 ? 1 : view.scale > 50 ? 2 : 5;
    if (linesOnly) {
      ctx.strokeStyle = T.grid; ctx.lineWidth = 1; ctx.beginPath();
      for (let lon = Math.ceil(b[0] / step) * step; lon <= b[2]; lon += step) { const x = view.px(lon, 0)[0]; ctx.moveTo(x, 0); ctx.lineTo(x, view.h); }
      for (let lat = Math.ceil(b[1] / step) * step; lat <= b[3]; lat += step) { const y = view.px(0, mY(lat))[1]; ctx.moveTo(0, y); ctx.lineTo(view.w, y); }
      ctx.stroke(); return;
    }
    ctx.fillStyle = T.label; ctx.font = '10px ui-monospace, "IBM Plex Mono", monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let lon = Math.ceil(b[0] / step) * step; lon <= b[2]; lon += step) { const x = view.px(lon, 0)[0]; if (x > 40 && x < view.w - 40) ctx.fillText(`${Math.abs(lon)}°${lon >= 0 ? 'E' : 'W'}`, x, view.h - 16); }
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (let lat = Math.ceil(b[1] / step) * step; lat <= b[3]; lat += step) { const y = view.px(0, mY(lat))[1]; if (y > 130 && y < view.h - 30) ctx.fillText(`${Math.abs(lat)}°${lat >= 0 ? 'N' : 'S'}`, view.w - 6, y); }
  },
  drawLand(ctx, view, T) {
    const b = view.bounds(); ctx.fillStyle = T.land; ctx.strokeStyle = T.coast; ctx.lineWidth = 1; ctx.lineJoin = 'round';
    // beyond the charted extents the schematic has no coastline data; paint it as land (the regions are ringed by land)
    // and re-open water inside each extent, so zooming out never shows a hard rectangle
    ctx.fillRect(0, 0, view.w, view.h); ctx.fillStyle = T.water;
    for (const key of ['A', 'B']) { const e = LAND_EXTENT[key]; const [x0, y0] = view.px(e[0], mY(e[3])); const [x1, y1] = view.px(e[2], mY(e[1])); ctx.fillRect(x0, y0, x1 - x0, y1 - y0); }
    if (SET.graticule) this.drawGraticule(ctx, view, T, true);
    ctx.fillStyle = T.land;
    for (const key of ['A', 'B']) for (const ring of LAND[key]) {
      if (ring.bbox[2] < b[0] || ring.bbox[0] > b[2] || ring.bbox[3] < b[1] || ring.bbox[1] > b[3]) continue;
      ctx.beginPath(); ring.pts.forEach(([lon, y], i) => { const [x, yy] = view.px(lon, y); i ? ctx.lineTo(x, yy) : ctx.moveTo(x, yy); }); ctx.closePath(); ctx.fill(); ctx.stroke();
    }
    // the outer ring of each region closes along its extent; hide that seam under a land-coloured line
    ctx.strokeStyle = T.land; ctx.lineWidth = 3;
    for (const key of ['A', 'B']) { const e = LAND_EXTENT[key]; const [x0, y0] = view.px(e[0], mY(e[3])); const [x1, y1] = view.px(e[2], mY(e[1])); ctx.strokeRect(x0, y0, x1 - x0, y1 - y0); }
  },
  drawZones(ctx, view, T) {
    ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
    for (const z of ZONES_M) {
      const off = z.z.enabled === false; ctx.fillStyle = off ? 'transparent' : T.zone; ctx.strokeStyle = T.zoneLine; ctx.globalAlpha = off ? 0.35 : 1;
      ctx.beginPath(); z.pts.forEach(([lon, y], i) => { const [x, yy] = view.px(lon, y); i ? ctx.lineTo(x, yy) : ctx.moveTo(x, yy); }); ctx.closePath(); if (!off) ctx.fill(); ctx.stroke();
      if (view.scale > 30) {
        // label at the centre of the zone's visible part, so a zone cut by the screen edge keeps a readable label
        let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9; z.pts.forEach(([lon, yy]) => { const [px, py] = view.px(lon, yy); x0 = Math.min(x0, px); y0 = Math.min(y0, py); x1 = Math.max(x1, px); y1 = Math.max(y1, py); });
        const vx0 = Math.max(x0, 12), vy0 = Math.max(y0, 60), vx1 = Math.min(x1, view.w - 12), vy1 = Math.min(y1, view.h - 12);
        if (vx1 - vx0 > 90 && vy1 - vy0 > 20) {
          const text = z.z.name.toUpperCase() + (off ? ' · OFF' : ''); ctx.font = '600 10px -apple-system, "Instrument Sans", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          const tw = ctx.measureText(text).width; const cx = Math.min(Math.max((vx0 + vx1) / 2, vx0 + tw / 2 + 4), vx1 - tw / 2 - 4);
          ctx.fillStyle = T.zoneLine; ctx.fillText(text, cx, (vy0 + vy1) / 2);
        }
      }
      ctx.globalAlpha = 1;
    }
    ctx.setLineDash([]);
  },
  drawPorts(ctx, view, T, filter) {
    const b = view.bounds();
    for (const key of ['A', 'B']) for (const p of GEO.regions[key].ports) {
      if (p.b[0] < b[0] || p.b[0] > b[2] || p.b[1] < b[1] || p.b[1] > b[3]) continue;
      if (!(filter ? filter(p) : (p.major || view.scale > 60))) continue;
      const [x, y] = view.project(p.b[0], p.b[1]);
      ctx.beginPath(); ctx.arc(x, y, 2.6, 0, Math.PI * 2); ctx.fillStyle = T.fg; ctx.fill(); ctx.strokeStyle = T.bg; ctx.lineWidth = 1; ctx.stroke();
      if (SET.portLabels && (view.scale > 24 || p.major || filter)) { ctx.fillStyle = T.label; ctx.font = '11px -apple-system, "Instrument Sans", sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(p.name, x + 6, y - 1); }
    }
  },
  drawFleet(ctx, view, T) {
    this.drawPorts(ctx, view, T); const hits = []; const b = view.bounds();
    for (const a of LIVE) {
      const p = a.last; if (p.lon < b[0] - 1 || p.lon > b[2] + 1 || p.lat < b[1] - 1 || p.lat > b[3] + 1) continue;
      if (!passFilter(a)) continue;
      const [x, y] = view.project(p.lon, p.lat); const sel = a.v.imo === S.imo; const color = T.types[a.v.type];
      if (a.sev.high) { ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.strokeStyle = T.high; ctx.lineWidth = 2; ctx.stroke(); }
      if (sel) { ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI * 2); ctx.strokeStyle = T.accent; ctx.lineWidth = 2.5; ctx.stroke(); }
      drawShip(ctx, x, y, p.cog, p.sog, color, T.bg);
      if (view.scale > 110 || sel) { ctx.fillStyle = T.fg; ctx.font = '600 11px -apple-system, "Instrument Sans", sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(a.v.name, x + 12, y + 1); }
      hits.push({ x, y, a });
    }
    this.hits = hits;
  },
  drawVessel(ctx, view, T) {
    const a = ANALYSIS.get(S.imo); if (!a) return;
    const selN = S.voyage, voys = a.voyages;
    this.drawPorts(ctx, view, T, p => a.portCalls.some(pc => pc.port.id === p.id));
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'; const segHits = [];
    for (const vg of voys) {
      const faded = selN && vg.n !== selN; const col = T.v[vg.color];
      ctx.globalAlpha = faded ? 0.22 : 1; ctx.lineWidth = selN === vg.n ? 3.2 : 2.2; ctx.strokeStyle = col; ctx.setLineDash(vg.current ? [9, 7] : []);
      ctx.beginPath(); let pen = false, prev = null;
      for (const p of vg.pts) {
        if (p.jump) continue; const [x, y] = view.project(p.lon, p.lat);
        if (prev && p.t - prev.t > RULES.aisGap.minHours * H && prev.sog > RULES.portCall.maxSpeedKn) pen = false;
        if (!pen) { ctx.moveTo(x, y); pen = true; } else ctx.lineTo(x, y);
        if (!faded && prev) segHits.push({ x0: prev._x, y0: prev._y, x1: x, y1: y, vg });
        p._x = x; p._y = y; prev = p;
      }
      ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.globalAlpha = 1;
    for (const f of a.flags) {
      if (f.rule === 'AIS gap' && (!selN || (f.voyage && f.voyage.n === selN))) { const b0 = f.evidence.before[f.evidence.before.length - 1], a0 = f.evidence.after[0]; const [x0, y0] = view.project(b0.lon, b0.lat), [x1, y1] = view.project(a0.lon, a0.lat); ctx.strokeStyle = T.high; ctx.lineWidth = 2; ctx.setLineDash([2, 5]); ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); ctx.setLineDash([]); }
      if (f.rule === 'Position jump' && (!selN || (f.voyage && f.voyage.n === selN))) { const [x, y] = view.project(f.lon, f.lat); ctx.strokeStyle = T.medium; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(x - 4, y - 4); ctx.lineTo(x + 4, y + 4); ctx.moveTo(x + 4, y - 4); ctx.lineTo(x - 4, y + 4); ctx.stroke(); }
    }
    const calls = selN ? a.portCalls.filter(pc => { const vg = voys.find(v => v.n === selN); return vg && (pc === vg.from || pc === vg.to); }) : a.portCalls;
    const seen = new Set();
    for (const pc of calls) { if (seen.has(pc.port.id)) continue; seen.add(pc.port.id); const [x, y] = view.project(pc.port.b[0] ?? pc.lon, pc.port.b[1] ?? pc.lat); ctx.beginPath(); ctx.arc(x, y, 3.2, 0, Math.PI * 2); ctx.fillStyle = T.fg; ctx.fill(); ctx.strokeStyle = T.bg; ctx.lineWidth = 1.2; ctx.stroke(); }
    const hits = [];
    for (const f of a.flags) {
      if (f.vesselLevel || (selN && (!f.voyage || f.voyage.n !== selN))) continue;
      const [x, y] = view.project(f.lon, f.lat); const focus = S.focusFlag === f.id; const col = f.severity === 'high' ? T.high : f.severity === 'medium' ? T.medium : T.info;
      if (focus) { ctx.beginPath(); ctx.arc(x, y, 16, 0, Math.PI * 2); ctx.strokeStyle = T.accent; ctx.lineWidth = 2.5; ctx.stroke(); }
      ctx.beginPath(); ctx.arc(x, y, 8.5, 0, Math.PI * 2); ctx.fillStyle = col; ctx.fill(); ctx.strokeStyle = T.bg; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = T.bg; ctx.font = '700 11px -apple-system, "Instrument Sans", sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', x, y + 0.5);
      hits.push({ x, y, f });
    }
    if (S.focusFlag) { const f = a.flags.find(f => f.id === S.focusFlag); if (f && f.evidence) for (const [arr, hollow] of [[f.evidence.before, true], [f.evidence.after, false]]) for (const p of arr) { const [x, y] = view.project(p.lon, p.lat); ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.lineWidth = 1.5; ctx.strokeStyle = T.accent; ctx.fillStyle = hollow ? T.bg : T.accent; ctx.fill(); ctx.stroke(); } }
    const last = a.last; const [lx, ly] = view.project(last.lon, last.lat);
    ctx.beginPath(); ctx.arc(lx, ly, 13, 0, Math.PI * 2); ctx.fillStyle = T.accent; ctx.globalAlpha = 0.22; ctx.fill(); ctx.globalAlpha = 1;
    drawShip(ctx, lx, ly, last.cog, last.sog, T.accent, T.bg, 1.15);
    ctx.fillStyle = T.fg; ctx.font = '700 11px -apple-system, "Instrument Sans", sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText('Now', lx + 14, ly);
    this.hits = hits; this.segHits = segHits;
  },
  hitTest(x, y) {
    if (S.mode === 'region' || S.mode === 'search') { let best = null, bd = 22; for (const h of this.hits || []) { const d = Math.hypot(h.x - x, h.y - y); if (d < bd) { bd = d; best = h; } } return best ? { type: 'ship', a: best.a } : null; }
    let best = null, bd = 18; for (const h of this.hits || []) { const d = Math.hypot(h.x - x, h.y - y); if (d < bd) { bd = d; best = h; } }
    if (best) return { type: 'flag', f: best.f };
    let bs = null, sd = 14; for (const s of this.segHits || []) { const d = segDist(x, y, s.x0, s.y0, s.x1, s.y1); if (d < sd) { sd = d; bs = s; } }
    return bs ? { type: 'voyage', vg: bs.vg } : null;
  },
  updateReadout() {
    const [lon, lat] = this.unproject(this.w / 2, this.h / 2); $('#coords').textContent = fmtDM(lat, lon);
    const pxPerNm = (this.base ? Base.pxPerDegLon() : this.scale) / 60 / Math.cos(lat * RAD); const nice = [1, 2, 5, 10, 20, 50, 100, 200, 500].find(n => n * pxPerNm >= 60) || 500;
    $('#scalebar').querySelector('i').style.setProperty('--w', (nice * pxPerNm).toFixed(0) + 'px'); $('#scaletxt').textContent = nice + ' nm';
  },
  snapshot(b, w, h) {
    const cv = document.createElement('canvas'); cv.width = w * 2; cv.height = h * 2; const ctx = cv.getContext('2d');
    const view = Object.create(this); view.w = w; view.h = h; view.dpr = 2; view.ctx = ctx;
    const p = { t: 30, r: 60, b: 30, l: 30 }; const y0 = mY(b[1]), y1 = mY(b[3]);
    view.scale = Math.max(6, Math.min(3000, Math.min((w - p.l - p.r) / Math.max(0.01, b[2] - b[0]), (h - p.t - p.b) / Math.max(0.01, y1 - y0))));
    view.cx = (b[0] + b[2]) / 2 + ((p.r - p.l) / 2) / view.scale; view.cy = (y0 + y1) / 2 + ((p.t - p.b) / 2) / view.scale;
    view.px = function (lon, y) { return [(lon - this.cx) * this.scale + this.w / 2, (this.cy - y) * this.scale + this.h / 2]; };
    view.bounds = function () { const a = this.unproject(0, this.h), c = this.unproject(this.w, 0); return [a[0], a[1], c[0], c[1]]; };
    view.unproject = function (x, y) { return [this.cx + (x - this.w / 2) / this.scale, mLat(this.cy - (y - this.h / 2) / this.scale)]; };
    view.project = function (lon, lat) { return this.px(lon, mY(lat)); };
    this.draw(ctx, view); return cv.toDataURL('image/png');
  },
};
function drawShip(ctx, x, y, cog, sog, color, stroke, k = 1) {
  ctx.save(); ctx.translate(x, y); ctx.fillStyle = color; ctx.strokeStyle = stroke; ctx.lineWidth = 1.3;
  if (sog < 0.5) { ctx.beginPath(); ctx.rect(-5 * k, -5 * k, 10 * k, 10 * k); ctx.fill(); ctx.stroke(); }
  else { ctx.rotate(cog * RAD); ctx.beginPath(); ctx.moveTo(0, -8.5 * k); ctx.lineTo(5.5 * k, 6 * k); ctx.lineTo(0, 3 * k); ctx.lineTo(-5.5 * k, 6 * k); ctx.closePath(); ctx.fill(); ctx.stroke(); }
  ctx.restore();
}
function segDist(px, py, x0, y0, x1, y1) { const dx = x1 - x0, dy = y1 - y0, L2 = dx * dx + dy * dy; const t = L2 ? Math.max(0, Math.min(1, ((px - x0) * dx + (py - y0) * dy) / L2)) : 0; return Math.hypot(px - (x0 + t * dx), py - (y0 + t * dy)); }
function boundsOf(pts) { const b = [999, 999, -999, -999]; for (const p of pts) { if (p.jump) continue; if (p.lon < b[0]) b[0] = p.lon; if (p.lat < b[1]) b[1] = p.lat; if (p.lon > b[2]) b[2] = p.lon; if (p.lat > b[3]) b[3] = p.lat; } if (b[2] - b[0] < 0.3) { b[0] -= 0.15; b[2] += 0.15; } if (b[3] - b[1] < 0.2) { b[1] -= 0.1; b[3] += 0.1; } return b; }
function passFilter(a) { if (S.type !== 'all' && a.v.type !== S.type) return false; if (S.flaggedOnly && !a.sev.high) return false; return true; }

/* ---------------------------------- gestures ---------------------------------- */
function isDark() { const t = document.documentElement.getAttribute('data-theme'); return t === 'dark' || (!t && matchMedia('(prefers-color-scheme: dark)').matches); }
function startBase() {
  const stage = $('#stage'), el = $('#basemap');
  if (!SET.baseMap || !el || (API.cfg && API.cfg.noTiles)) return;   // noTiles: hosts whose sandbox blocks tile fetches (the prototype link)
  const ok = Base.init(el, {
    onReady() { stage.classList.add('tiles'); $('#attrib').hidden = false; Chart.draw(); },
    onFail() { stage.classList.remove('tiles'); $('#attrib').hidden = true; $('#map').style.pointerEvents = ''; wireGestures($('#map')); Chart.fitBounds(REGIONS[S.region].bounds, false); },
    onMove() { Chart.draw(); },
    onMoveEnd() { onMoveEnd(); },
    onTap(x, y) { onTap(x, y); },
    onHover(x, y) { return !!Chart.hitTest(x, y); },
  }, isDark());
  if (ok) stage.classList.add('base');
}

function wireGestures(cv) {
  if (Base.active) { cv.style.pointerEvents = 'none'; return; }
  const ptrs = new Map(); let pinch = null, down = null, moved = false, lastTap = 0;
  cv.addEventListener('pointerdown', e => { cv.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, { x: e.offsetX, y: e.offsetY }); if (ptrs.size === 1) { down = { x: e.offsetX, y: e.offsetY, t: performance.now() }; moved = false; } if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 }; } });
  cv.addEventListener('pointermove', e => {
    if (!ptrs.has(e.pointerId)) return; const prev = ptrs.get(e.pointerId); ptrs.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
    if (ptrs.size === 2 && pinch) { const [a, b] = [...ptrs.values()]; const d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2; Chart.zoomAt(mx, my, d / pinch.d); Chart.cx -= (mx - pinch.mx) / Chart.scale; Chart.cy += (my - pinch.my) / Chart.scale; pinch = { d, mx, my }; Chart.draw(); moved = true; return; }
    if (ptrs.size === 1) { const dx = e.offsetX - prev.x, dy = e.offsetY - prev.y; if (down && Math.hypot(e.offsetX - down.x, e.offsetY - down.y) > 6) moved = true; if (moved) { Chart.cx -= dx / Chart.scale; Chart.cy += dy / Chart.scale; Chart.draw(); } }
  });
  const up = e => { if (!ptrs.has(e.pointerId)) return; ptrs.delete(e.pointerId); if (ptrs.size < 2) pinch = null; if (ptrs.size === 0) { if (!moved && down && performance.now() - down.t < 500) { const now = performance.now(); if (now - lastTap < 320) { Chart.zoomAt(e.offsetX, e.offsetY, 2); lastTap = 0; } else { lastTap = now; onTap(e.offsetX, e.offsetY); } } down = null; if (moved) onMoveEnd(); } };
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('wheel', e => { e.preventDefault(); Chart.zoomAt(e.offsetX, e.offsetY, Math.exp(-e.deltaY * 0.0018)); clearTimeout(Chart._wt); Chart._wt = setTimeout(onMoveEnd, 160); }, { passive: false });
  cv.addEventListener('pointermove', e => { if (ptrs.size) return; const hit = Chart.hitTest(e.offsetX, e.offsetY); cv.style.cursor = hit ? 'pointer' : 'grab'; });
}
let moveT = 0;
function onMoveEnd() { clearTimeout(moveT); moveT = setTimeout(() => { if (S.mode === 'region') renderSheet(); }, 60); }
function onTap(x, y) {
  const hit = Chart.hitTest(x, y); if (!hit) { if (S.mode === 'region' && S.imo) { S.imo = null; Chart.draw(); renderSheet(); } return; }
  if (hit.type === 'ship') openVessel(hit.a.v.imo); else if (hit.type === 'flag') focusFlag(hit.f, false); else if (hit.type === 'voyage') openVoyage(hit.vg.n, false);
}

/* ---------------------------------- glass sheet ---------------------------------- */
const Sheet = {
  el: null, target: null, pos: 'half',
  init() {
    this.el = $('#sheet'); const grab = $('#grab'); let start = null;
    grab.addEventListener('pointerdown', e => { grab.setPointerCapture(e.pointerId); start = { y: e.clientY, h: this.el.getBoundingClientRect().height }; this.el.classList.add('dragging'); });
    grab.addEventListener('pointermove', e => { if (!start) return; const h = Math.max(110, Math.min(this.max() - 16, start.h + (start.y - e.clientY))); this.el.style.setProperty('--sheet-h', h + 'px'); });
    const end = e => { if (!start) return; const moved = Math.abs(e.clientY - start.y); this.el.classList.remove('dragging'); const h = this.el.getBoundingClientRect().height; if (moved < 6) this.snap(this.pos === 'peek' ? 'half' : this.pos === 'half' ? 'full' : 'peek'); else this.snap(h < this.max() * 0.3 ? 'peek' : h < this.max() * 0.7 ? 'half' : 'full'); start = null; };
    grab.addEventListener('pointerup', end); grab.addEventListener('pointercancel', end);
  },
  max() { return $('#page-chart').getBoundingClientRect().height; },
  snap(pos) {
    if (!isMobile()) { this.target = null; this.el.classList.remove('full'); return; }
    this.pos = pos; const M = this.max(); const h = pos === 'peek' ? 150 : pos === 'full' ? M - 16 : M * 0.46;
    this.target = pos === 'full' ? M * 0.46 : h; this.el.style.setProperty('--sheet-h', h + 'px'); this.el.classList.toggle('full', pos === 'full');
    $('#tabbar').classList.toggle('hide', pos === 'full');
  },
};

/* ------------------------------------- shared bits ------------------------------------- */
function typeDot(t) { return `<span class="dot" style="--c:var(--t-${t})"></span>`; }
function sevBadge(a) { if (!a.flags.length) return `<span class="badge">0</span>`; return `<span class="badge ${a.sev.high ? 'high' : 'medium'}">${a.flags.length}${a.sev.high ? ' · ' + a.sev.high + 'H' : ''}</span>`; }
function watchlist() { return store.get('watch', []); }
function watched(imo) { return watchlist().includes(imo); }
function ago(t) { const m = Math.round((NOW - t) / 60e3); return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 48 * 60 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; }
function statusLine(a) {
  const st = a.static, p = a.last;
  if (st.state === 'underway') return `Underway ${p.sog} kn · ${String(p.cog).padStart(3, '0')}° → ${esc(st.destination)} · ETA ${fmtDT(st.eta)} ${TZ()}`;
  if (st.state === 'anchored') return `At anchor off ${esc(st.port.name)} since ${fmtDT(st.since)} ${TZ()}`;
  return `Moored at ${esc(st.port.name)} since ${fmtDT(st.since)} ${TZ()}${st.nextPort ? ' · next ' + esc(st.nextPort.name) : ''}`;
}
function vesselRow(a, extra = '') {
  return `<li><button class="row" data-act="open" data-imo="${a.v.imo}" aria-pressed="${a.v.imo === S.imo}">${typeDot(a.v.type)}<div class="rmain"><div class="nm"><span>${esc(a.v.name)}</span>${watched(a.v.imo) ? '<span class="star">★</span>' : ''}</div><div class="sub2">${TYPE_LABEL[a.v.type]} · ${esc(a.v.flag)} · IMO ${a.v.imo}${extra}</div></div><div class="side"><span class="mono">${a.last.sog < 0.5 ? (a.static.state === 'anchored' ? 'At anchor' : 'Moored') : a.last.sog + ' kn · ' + String(a.last.cog).padStart(3, '0') + '°'}</span><span>${a.static.state === 'underway' ? '→ ' + esc(a.static.destination) : esc((a.static.port || a.static.lastPort).name)}</span>${sevBadge(a)}</div></button></li>`;
}
function toast(msg) { const t = document.createElement('div'); t.className = 'toast glass'; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 1900); }
function sw(key, on) { return `<button class="switch" role="switch" aria-checked="${on}" data-act="switch" data-key="${key}" aria-label="${key}"></button>`; }
function grow(label, value, act = '', sub = '', ico = '') { const tag = act ? 'button' : 'div'; return `<${tag} class="grow" ${act ? `data-act="${act}"` : ''}>${ico}<div class="lbl"><b>${label}</b>${sub ? `<span>${sub}</span>` : ''}</div>${value !== undefined && value !== '' ? `<span class="val">${value}</span>` : ''}${act ? `<span class="chev">${ICON.chevR}</span>` : ''}</${tag}>`; }
function ico(svg, color) { return `<span class="ico" style="background:${color}">${svg}</span>`; }

/* ------------------------------------- chart sheet ------------------------------------- */
function renderSheet() {
  const body = $('#sheetBody'); $('#sheetHead').hidden = S.mode === 'vessel' || S.mode === 'voyage';
  if (S.mode === 'search') body.innerHTML = renderSearch(); else if (S.mode === 'vessel') body.innerHTML = renderVessel(); else if (S.mode === 'voyage') body.innerHTML = renderVoyage(); else body.innerHTML = renderRegion();
}
function renderRegion() {
  const b = Chart.bounds(); const inView = LIVE.filter(a => a.last.lon >= b[0] && a.last.lon <= b[2] && a.last.lat >= b[1] && a.last.lat <= b[3]);
  const shown = inView.filter(passFilter).sort((x, y) => (y.sev.high - x.sev.high) || (y.flags.length - x.flags.length) || x.v.name.localeCompare(y.v.name));
  const flagged = inView.filter(a => a.sev.high).length;
  return `<div class="sh"><div class="sh-title"><h2>${esc(REGIONS[S.region].label)}</h2><span class="count">${inView.length} in view · ${flagged} with high flags${S.loading ? ' · loading ' + LIVE.length + '/' + FLEET.length : ''}</span></div>
  <div class="filters">${TYPES.map(([k, l]) => `<button class="fchip" data-act="type" data-type="${k}" aria-pressed="${S.type === k}">${k !== 'all' ? `<span class="dot" style="--c:var(--t-${k})"></span>` : ''}${l}</button>`).join('')}<button class="fchip" data-act="flagged" aria-pressed="${S.flaggedOnly}">⚑ High flags only</button></div></div>
  <ul class="rows">${shown.map(a => vesselRow(a)).join('') || '<li class="empty">No vessels in view. Pan the chart or pick another region.</li>'}</ul>
  <p class="hint">Sample fleet of ${FLEET.length} fictional vessels with generated 12-month tracks. Tap a ship on the chart or in the list to open its voyages, red flags and identity. Positions refresh from the AIS provider in the production build.</p>`;
}
function renderSearch() {
  const res = API.server ? LIVE.filter(a => { const q = S.query.toUpperCase(); return a.v.name.includes(q) || String(a.v.imo).startsWith(q) || (a.v.mmsi || '').startsWith(q); }).map(a => a.v) : Provider.searchVessel(S.query); const dup = new Set(res.map(v => v.name).filter((n, i, arr) => arr.indexOf(n) !== i));
  const rows = res.map(v => { const a = ANALYSIS.get(v.imo); return `<li><button class="row" data-act="open" data-imo="${v.imo}">${typeDot(v.type)}<div class="rmain"><div class="nm"><span>${esc(v.name)}</span>${dup.has(v.name) ? '<span class="badge">same name</span>' : ''}</div><div class="sub2">IMO ${v.imo} · MMSI ${v.mmsi} · ${esc(v.flag)} · ${esc(v.sub)} · ${fmtN(v.dwt)} dwt${v.exNames.length ? ' · ex ' + esc(v.exNames.join(', ')) : ''}</div></div><div class="side">${a ? sevBadge(a) : '<span class="badge">…</span>'}</div></button></li>`; }).join('');
  return `<div class="sh"><div class="sh-title"><h2>Search</h2><span class="count">${res.length} match${res.length === 1 ? '' : 'es'}</span></div>${dup.size ? '<div class="hint">Several ships share a name. Check IMO, flag and size before you pick one.</div>' : ''}</div><ul class="rows">${rows || `<li class="empty">No vessel matches “${esc(S.query)}”. Try an IMO or MMSI number.</li>`}</ul>`;
}
function vesselHeader(a) {
  const v = a.v, st = a.static, cur = a.voyages.find(x => x.current);
  const flagHist = v.history.filter(h => h.field === 'flag' && h.t >= NOW - YEAR).sort((x, y) => y.t - x.t)[0];
  const sanc = a.flags.find(f => f.rule === 'Sanctions hit'); const dark = a.voyages.reduce((s, x) => s + x.darkH, 0);
  return `<div class="backrow"><button class="ibtn" data-act="back">${ICON.chevL}${S.query ? 'Search' : esc(REGIONS[S.region].label)}</button><span class="mono muted" style="font-size:11px">fix ${ago(a.last.t)} · ${a.last.src === 'S' ? 'satellite' : 'terrestrial'}</span></div>
  <div class="vname"><h2>${esc(v.name)}${watched(v.imo) ? '<span class="star" title="Watching">★</span>' : ''}</h2><span class="ids">IMO ${v.imo} · MMSI ${v.mmsi} · ${v.callsign}</span></div>
  <div class="vsub">${esc(v.sub)} · ${esc(v.flag)} flag${flagHist ? ` (${esc(flagHist.from)} until ${fmtMon(flagHist.t)})` : ''} · ${fmtN(v.dwt)} dwt · built ${v.built}</div>
  <div class="status"><span class="led ${st.state}"></span><span>${statusLine(a)}${cur ? ` · draught ${a.last.draught} m` : ''}</span></div>
  <div class="kpis"><div class="kpi"><b>${a.voyages.length}</b><span>Voyages</span></div><div class="kpi ${a.sev.high ? 'high' : ''}"><b>${a.flags.length}</b><span>${a.sev.high ? a.sev.high + ' high' : 'Flags'}</span></div><div class="kpi ${sanc ? 'high' : 'ok'}"><b>${sanc ? 'Listed' : 'Clear'}</b><span>Sanctions</span></div><div class="kpi ${dark > 24 ? 'high' : ''}"><b>${Math.round(dark)} h</b><span>Time dark</span></div></div>
  <div class="actions"><button class="cap primary sm" data-act="report">Vessel report</button><button class="cap tint sm" data-act="watch" aria-pressed="${watched(v.imo)}">${watched(v.imo) ? '★ Watching' : '☆ Watch'}</button><button class="cap sm" data-act="fit">Fit voyages</button></div>`;
}
function renderVessel() {
  const a = ANALYSIS.get(S.imo), v = a.v;
  const tabs = [['voyages', 'Voyages'], ['flags', `Flags (${a.flags.length})`], ['identity', 'Identity'], ['particulars', 'Particulars']];
  let body = '';
  if (S.vtab === 'voyages') {
    body = `<ul class="rows">${a.voyages.slice().reverse().map(vg => { const fl = vg.flags.length; const when = vg.current ? `Left ${fmtD(vg.depart)} · ${fl ? fl + ' flag' + (fl > 1 ? 's' : '') : 'no flags yet'}` : `${fmtRange(vg.depart, vg.arrive)} · ${fl ? fl + ' flag' + (fl > 1 ? 's' : '') : 'no flags'}`;
      return `<li><button class="vrow" data-act="voyage" data-n="${vg.n}" aria-current="${S.voyage === vg.n}"><span class="vline" style="--c:var(--v${vg.color});--ls:${vg.current ? 'dashed' : 'solid'}"></span><div><b>V${vg.n}${vg.current ? ' · underway' : ''}</b><span class="route">${vg.from ? esc(vg.from.port.name) : 'History start'} → ${vg.to ? esc(vg.to.port.name) : esc(a.static.destination || '…')}</span><span class="meta ${fl ? 'fl' : ''}">${when}</span></div><span class="side">${fmtN(vg.nm)} nm<br>${vg.arrive ? fmtDur(vg.arrive - vg.depart) : fmtDur(NOW - vg.depart)}</span></button></li>`; }).join('')}</ul>`;
  } else if (S.vtab === 'flags') {
    const rank = { high: 0, medium: 1, info: 2 };
    const fl = a.flags.slice().sort((x, y) => ((rank[x.severity] ?? 3) - (rank[y.severity] ?? 3)) || ((y.vesselLevel ? 1 : 0) - (x.vesselLevel ? 1 : 0)) || (y.t0 - x.t0)); body = fl.length ? fl.map(f => flagCard(f)).join('') : `<div class="empty">No red flags in the last 12 months.</div>`;
    if (API.server) body += crossCheckPanel(v.imo);
  } else if (S.vtab === 'identity') {
    const hist = v.history.slice().sort((x, y) => y.t - x.t); const label = { name: 'Name', flag: 'Flag', mmsi: 'MMSI' };
    const lists = RULES.sanctions.lists.map(l => { const s = v.sanctions.find(s => s.list === l); return `<tr><th>${l}</th><td>${s ? `<span class="pill high">LISTED</span> ${fmtDY(s.t)} · ${esc(s.programme)}` : '<span class="pill ok">CLEAR</span>'}</td></tr>`; }).join('');
    body = `<div class="sec"><h3>Identity history (keyed on IMO ${v.imo})</h3>${hist.length ? `<ul class="tl">${hist.map(h => `<li><span class="d">${fmtDY(h.t)}</span><span>${label[h.field]} ${esc(h.from)} → <b>${esc(h.to)}</b></span></li>`).join('')}</ul>` : '<p class="muted" style="margin:0">No name, flag or MMSI change recorded in the last 12 months.</p>'}${v.exNames.length ? `<p class="muted" style="margin:4px 0 0">Former names: ${esc(v.exNames.join(', '))}</p>` : ''}</div>
    <div class="sec"><h3>Sanctions screening</h3><table class="kv">${lists}<tr><th>Screened</th><td>${fmtDT(NOW)} ${TZ()} · lists refreshed daily in production</td></tr></table></div>
    <div class="sec"><h3>Ownership and management</h3><table class="kv"><tr><th>Registered owner</th><td>${esc(v.regOwner)}</td></tr><tr><th>Beneficial owner</th><td>${esc(v.benOwner)}</td></tr><tr><th>ISM manager</th><td>${esc(v.ism)}</td></tr><tr><th>Commercial operator</th><td>${esc(v.operator)}</td></tr><tr><th>Class</th><td>${esc(v.classSoc)}</td></tr><tr><th>P&amp;I</th><td>${esc(v.pi)}</td></tr></table></div>`;
  } else {
    body = `<table class="kv"><tr><th>Type</th><td>${esc(v.sub)}</td></tr><tr><th>Flag</th><td>${esc(v.flag)}</td></tr><tr><th>IMO</th><td class="mono">${v.imo}</td></tr><tr><th>MMSI</th><td class="mono">${v.mmsi}</td></tr><tr><th>Call sign</th><td class="mono">${v.callsign}</td></tr><tr><th>DWT / GT</th><td class="mono">${fmtN(v.dwt)} t / ${fmtN(v.gt)}</td></tr><tr><th>LOA × beam</th><td class="mono">${v.loa} m × ${v.beam} m</td></tr><tr><th>Draught loaded / ballast</th><td class="mono">${v.draughtLoaded} m / ${v.draughtBallast} m</td></tr><tr><th>Built</th><td>${v.built} · ${esc(v.builder)}</td></tr><tr><th>Service speed</th><td class="mono">${v.speed.toFixed(1)} kn</td></tr><tr><th>AIS destination</th><td class="mono">${esc(a.static.destination || '—')}</td></tr><tr><th>ETA (AIS)</th><td class="mono">${a.static.eta ? fmtDT(a.static.eta) + ' ' + TZ() : '—'}</td></tr><tr><th>Nav status</th><td>${a.last.nav === 0 ? 'Under way using engine' : a.last.nav === 1 ? 'At anchor' : 'Moored'}</td></tr><tr><th>Last position</th><td class="mono">${fmtDM(a.last.lat, a.last.lon)}<br>${fmtDT(a.last.t)} ${TZ()} · ${a.last.src === 'S' ? 'satellite' : 'terrestrial'}</td></tr><tr><th>Draught (AIS)</th><td class="mono">${a.last.draught} m</td></tr><tr><th>Region</th><td>${v.region === 'A' ? 'Black Sea / Eastern Mediterranean' : 'Gulf / Hormuz / Arabian Sea'}</td></tr></table>`;
  }
  const s = a.stats;
  return `<div class="vh">${vesselHeader(a)}<div class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-act="vtab" data-tab="${k}" aria-selected="${S.vtab === k}">${l}</button>`).join('')}</div><div class="tab-body">${body}</div>
  <div class="pipeline">${esc(providerLabel())} · ${fmtN(s.raw)} raw positions → ${fmtN(s.clean)} clean (${s.dup} duplicates, ${s.bad} bad fixes dropped) → ${s.portCalls} port calls → ${s.voyages} voyages → ${s.flags} flags · ${s.ms} ms · thresholds from Settings › Rules</div></div>`;
}
const XCHECK = new Map();   // imo -> {loading} | result of /crosscheck
function crossCheckPanel(imo) {
  const x = XCHECK.get(imo);
  let inner;
  if (!x) inner = `<p class="muted" style="margin:0 0 8px">Independent events computed by Global Fishing Watch from satellite AIS — a second opinion beside our own rules, useful where the free coastal feed sees nothing.</p><button class="cap tint sm" data-act="xcheck">Cross-check with Global Fishing Watch</button>`;
  else if (x.loading) inner = `<p class="muted" style="margin:0">Asking Global Fishing Watch…</p>`;
  else if (!x.ok) inner = `<p class="muted" style="margin:0">${esc(x.error || 'failed')}</p>`;
  else if (!x.events.length) inner = `<p class="muted" style="margin:0">${esc(x.note || 'No GFW events for this IMO in the last 12 months.')}${x.errors && x.errors.length ? ' · ' + esc(x.errors.join(' · ')) : ''}</p>`;
  else inner = `<ul class="tl">${x.events.map(e => `<li><span class="d">${e.t0 ? fmtDY(e.t0) : '—'}</span><span><b>${esc(e.label)}</b>${e.t1 && e.t0 ? ' · ' + fmtDur(e.t1 - e.t0) : ''}${e.detail ? ' · ' + esc(e.detail) : ''}${e.lat != null ? ` <button class="lnk" data-act="xcheck-go" data-lat="${e.lat}" data-lon="${e.lon}">show →</button>` : ''}</span></li>`).join('')}</ul><p class="gf" style="margin:8px 0 0">${x.events.length} events · ${esc(x.licence || '')}${x.errors && x.errors.length ? ' · unavailable: ' + esc(x.errors.map(s => s.split(':')[0]).join(', ')) : ''}</p>`;
  return `<div class="sec" id="xcheck"><h3>Cross-check · Global Fishing Watch</h3>${inner}</div>`;
}
function flagCard(f, showVoyage = true) {
  const ev = f.evidence ? `<div class="evid">${f.evidence.before.map(p => `<span><b>${fmtDT(p.t)}</b> ${fmtDM(p.lat, p.lon)} · ${p.sog} kn · ${p.draught} m</span>`).join('')}<span>— ${esc(f.rule.toLowerCase())} —</span>${f.evidence.after.map(p => `<span><b>${fmtDT(p.t)}</b> ${fmtDM(p.lat, p.lon)} · ${p.sog} kn · ${p.draught} m</span>`).join('')}</div>` : '';
  return `<div class="flag ${f.severity} ${S.focusFlag === f.id ? 'focus' : ''}" id="flag-${f.id}"><div class="fh"><span class="pill ${f.severity}">${f.severity.toUpperCase()}</span><span class="ft">${esc(f.title)}</span>${showVoyage && f.voyage ? `<span class="badge">V${f.voyage.n}</span>` : ''}</div><ul class="fl">${f.lines.map(l => `<li>${esc(l)}</li>`).join('')}</ul>${f.vesselLevel ? '' : `<div class="fa"><button data-act="flag" data-id="${f.id}">Show on chart →</button>${f.voyage && showVoyage ? `<button data-act="voyage" data-n="${f.voyage.n}">Open voyage</button>` : ''}</div>${S.focusFlag === f.id ? ev : ''}`}</div>`;
}
function renderVoyage() {
  const a = ANALYSIS.get(S.imo), vg = a.voyages.find(x => x.n === S.voyage); if (!vg) return renderVessel();
  const note = store.get('notes', {})[a.v.imo + '-' + vg.n] || '';
  const facts = [[vg.from ? 'Departed' : 'From', vg.from ? `${esc(vg.from.port.name)}, ${fmtD(vg.depart)}` : `History start, ${fmtD(vg.depart)}`], [vg.to ? 'Arrived' : 'Destination', vg.to ? `${esc(vg.to.port.name)}, ${fmtD(vg.arrive)}` : `${esc(a.static.destination || '—')}${a.static.eta ? ', ETA ' + fmtD(a.static.eta) : ''}`], ['Duration', vg.arrive ? fmtDur(vg.arrive - vg.depart) : fmtDur(NOW - vg.depart) + ' so far'], ['Distance', `${fmtN(vg.nm)} nm`], ['Draught out / in', `${vg.draughtOut} m / ${vg.draughtIn} m`], ['Time dark', vg.darkH ? `<span style="color:var(--high);font-weight:700">${Math.round(vg.darkH)} hours</span>` : '0 hours'], ['Avg speed', `${(vg.nm / Math.max(1, ((vg.arrive || NOW) - vg.depart) / H)).toFixed(1)} kn`], [vg.to ? 'Anchorage wait' : 'Positions', vg.to ? (vg.to.anchHours ? `${Math.round(vg.to.anchHours)} h off ${esc(vg.to.port.name)}` : 'none') : `${fmtN(vg.pts.length)} fixes`]];
  return `<div class="vh"><div class="backrow"><button class="ibtn" data-act="vessel">${ICON.chevL}${esc(a.v.name)}</button><span class="mono muted" style="font-size:11px">IMO ${a.v.imo}</span></div>
  <div class="vname"><h2 style="font-size:21px"><span class="vline" style="width:26px;--c:var(--v${vg.color});--ls:${vg.current ? 'dashed' : 'solid'}"></span>V${vg.n} · ${vg.from ? esc(vg.from.port.name) : 'History start'} → ${vg.to ? esc(vg.to.port.name) : esc(a.static.destination || '…')}</h2><span class="ids">${vg.current ? 'Underway' : 'Completed'} · ${fmtDY(vg.depart)} – ${vg.arrive ? fmtDY(vg.arrive) : 'now'}</span></div>
  <div class="vfacts">${facts.map(([k, v]) => `<div class="kpi"><b>${v}</b><span>${k}</span></div>`).join('')}</div>
  <div class="actions"><button class="cap primary sm" data-act="fitvoyage">Show on chart</button><button class="cap sm" data-act="report">Export report</button></div>
  <div class="sec"><h3>Red flags on this voyage (${vg.flags.length})</h3>${vg.flags.length ? vg.flags.map(f => flagCard(f, false)).join('') : '<p class="muted" style="margin:0">No flags on this voyage.</p>'}</div>
  <div class="sec"><h3>Analyst note</h3><textarea class="notebox" id="note" placeholder="Add a note for the report (saved on this device only)">${esc(note)}</textarea></div></div>`;
}

/* ------------------------------------- actions ------------------------------------- */
function showPage(p) {
  S.page = p; for (const k of PAGES) $('#page-' + k).hidden = k !== p;
  document.querySelectorAll('#tabbar .tab').forEach(t => t.setAttribute('aria-selected', t.dataset.page === p));
  $('#tabbar').classList.toggle('hide', p === 'chart' && Sheet.pos === 'full' && isMobile());
  if (p === 'chart') { Chart.resize(); } else renderPage(p);
  if (p === 'alerts') { store.set('alertsSeen', NOW); updateBadge(); if (API.server) API.alerts().then(list => { S.serverAlerts = list; renderPage('alerts'); }).catch(() => {}); }
  try { history.replaceState(null, '', '#' + (p === 'chart' && S.imo && S.mode !== 'region' ? 'imo' + S.imo : p === 'chart' ? S.region : p)); } catch (e) {}
}
function openVessel(imo) {
  if (API.server && !(ANALYSIS.get(imo) || {}).track?.length) {
    toast('Loading track…');
    API.analysis(imo).then(j => { const a = API.hydrate(j); ANALYSIS.set(imo, a); const k = LIVE.findIndex(x => x.v.imo === imo); if (k >= 0) LIVE[k] = a; else LIVE.push(a); BY_IMO[imo] = a.v; openVessel(imo); }).catch(err => toast('Could not load vessel: ' + err.message));
    return;
  }
  if (!ANALYSIS.has(imo)) analyze(BY_IMO[imo]);
  S.mode = 'vessel'; S.imo = imo; S.voyage = null; S.focusFlag = null; S.vtab = 'voyages';
  const a = ANALYSIS.get(imo); S.region = a.v.region === 'A' ? 'blacksea' : (S.region === 'blacksea' ? 'uae' : S.region); syncRegions();
  if (S.page !== 'chart') showPage('chart');
  renderSheet(); Sheet.snap('half'); $('#sheetBody').scrollTop = 0;
  Chart.fitBounds(boundsOf(a.track)); try { history.replaceState(null, '', '#imo' + imo); } catch (e) {}
}
function openVoyage(n, scroll = true) { S.mode = 'voyage'; S.voyage = n; S.focusFlag = null; if (API.server) API.notes(S.imo).then(ns => { const all = store.get('notes', {}); for (const [k, t] of Object.entries(ns)) all[S.imo + '-' + k] = t; store.set('notes', all); const el = document.getElementById('note'); if (el && ns[String(n)] !== undefined && !el.value) el.value = ns[String(n)]; }).catch(() => {}); renderSheet(); if (scroll) $('#sheetBody').scrollTop = 0; Sheet.snap('half'); const a = ANALYSIS.get(S.imo), vg = a.voyages.find(x => x.n === n); if (vg) Chart.fitBounds(boundsOf(vg.pts)); else Chart.draw(); }
function focusFlag(f, scroll = true, snapTo = 'half') {
  if (S.imo !== f.vessel.imo) { S.imo = f.vessel.imo; S.mode = 'vessel'; S.voyage = null; S.vtab = 'flags'; }
  S.focusFlag = f.id; if (f.voyage && S.mode === 'voyage') S.voyage = f.voyage.n;
  if (S.page !== 'chart') showPage('chart');
  renderSheet(); Sheet.snap(snapTo); const pts = f.evidence ? [...f.evidence.before, ...f.evidence.after, f] : [f, f];
  Chart.fitBounds(boundsOf(pts.map(p => ({ lat: p.lat, lon: p.lon }))));
  if (scroll) { const el = document.getElementById('flag-' + f.id); if (el) el.scrollIntoView({ block: 'center', behavior: reduceMotion.matches ? 'auto' : 'smooth' }); }
}
function backToRegion() { S.mode = S.query ? 'search' : 'region'; S.voyage = null; S.focusFlag = null; renderSheet(); Chart.fitBounds(REGIONS[S.region].bounds); try { history.replaceState(null, '', '#' + S.region); } catch (e) {} }
function setRegion(key) { S.region = key; syncRegions(); if (S.mode === 'vessel' || S.mode === 'voyage') { S.mode = 'region'; S.voyage = null; } S.query = ''; $('#q').value = ''; $('#qclear').hidden = true; if (S.mode === 'search') S.mode = 'region'; Chart.fitBounds(REGIONS[key].bounds); renderSheet(); try { history.replaceState(null, '', '#' + key); } catch (e) {} }
function syncRegions() { document.querySelectorAll('#regions .rchip').forEach(c => c.setAttribute('aria-pressed', c.dataset.region === S.region)); }
function toggleWatch(imo) { const w = watchlist(); const i = w.indexOf(imo); if (i >= 0) w.splice(i, 1); else w.push(imo); store.set('watch', w); toast(i >= 0 ? 'Removed from watchlist' : 'Added to watchlist'); if (API.server) API.putWatchlist(w).catch(() => toast('Watchlist not saved on the server')); }
function providerLabel() { if (API.server) return 'Server · ' + (API.cfg.providerName || 'configured provider'); return { mock: 'Mock AIS provider (generated tracks)', kpler: 'Kpler / MarineTraffic API', spire: 'Kpler / Spire Maritime', datalastic: 'Datalastic', vesselfinder: 'VesselFinder API' }[SET.provider] || 'Mock AIS provider'; }
function saveSettings() { store.set('settings', SET); }
function applyAppearance() {
  const root = document.documentElement; if (SET.theme === 'system') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', SET.theme);
  $('#app').classList.toggle('rt', !!SET.reduceTransparency); TIME_LOCAL = !!SET.timeLocal;
  GEO.zones.forEach(z => { z.enabled = !SET.zonesOff.includes(z.id); });
}
function rerun(msg) {
  ANALYSIS.clear(); LIVE.length = 0; S.loading = true; $('#loading').hidden = false;
  if (API.server) { fetch(API.cfg.apiBase + '/api/rules/reload', { method: 'POST' }).catch(() => {}); }
  loadFleet(() => { if (S.page === 'chart') { renderSheet(); Chart.draw(); } else renderPage(S.page); updateBadge(); if (msg) toast(msg); });
}

/* ------------------------------------- pages ------------------------------------- */
function topbar(title, left = '', right = '') { return `<div class="topbar glass" data-tb><div class="side">${left}</div><div class="ttl">${title}</div><div class="side r">${right}</div></div>`; }
function renderPage(p) {
  const el = $('#page-' + p); if (!el) return;
  if (p === 'vessels') el.innerHTML = renderVesselsPage(); else if (p === 'alerts') el.innerHTML = renderAlertsPage(); else if (p === 'reports') el.innerHTML = renderReportsPage(); else if (p === 'profile') el.innerHTML = renderProfilePage();
  el.scrollTop = 0;
}
function renderVesselsPage() {
  const segs = [['watch', `Watchlist (${watchlist().length})`], ['fleet', 'Fleet'], ['flagged', 'High flags']];
  let list = LIVE.slice(); if (S.vseg === 'watch') list = list.filter(a => watched(a.v.imo)); if (S.vseg === 'flagged') list = list.filter(a => a.sev.high);
  list.sort((x, y) => (y.sev.high - x.sev.high) || (y.flags.length - x.flags.length) || x.v.name.localeCompare(y.v.name));
  const empty = S.vseg === 'watch' ? 'Your watchlist is empty. Open a vessel and tap Watch; its new flags will show under Alerts.<br><button class="cta" data-act="vseg" data-seg="fleet">Browse the fleet →</button>' : 'Nothing here yet.';
  return `${topbar('Vessels')}<div class="content"><h1 class="largetitle">Vessels</h1><p class="sub">${LIVE.length} vessels in the sample fleet · ${LIVE.filter(a => a.sev.high).length} with high flags</p>
  <div class="seg">${segs.map(([k, l]) => `<button data-act="vseg" data-seg="${k}" aria-pressed="${S.vseg === k}">${l}</button>`).join('')}</div>
  <div class="group"><ul class="rows">${list.map(a => vesselRow(a, ` · ${a.v.region === 'A' ? 'Black Sea' : 'Gulf'}`)).join('') || `<li class="empty">${empty}</li>`}</ul></div></div>`;
}
function alertsList() {
  const out = [];
  if (API.server && S.serverAlerts) for (const al of S.serverAlerts) { const a = ANALYSIS.get(al.imo); const f = a && a.flags.find(f => f.rule === al.rule && Math.abs(f.t0 - al.t0) < 3600e3); out.push({ t: al.created_at, sev: al.severity, title: al.title, sub: `${al.rule} · refresh job`, f, a }); }
  for (const a of LIVE) for (const f of a.flags) { const t = f.t1 || f.t0; if (t >= NOW - 14 * D) out.push({ t, sev: f.severity, title: f.title, sub: `${a.v.name} · ${f.rule}${watched(a.v.imo) ? ' · watched' : ''}`, f, a }); }
  for (const a of LIVE) for (const s of a.v.sanctions) if (s.t >= NOW - 240 * D) out.push({ t: s.t, sev: 'high', title: `${a.v.name} added to ${s.list}`, sub: `${s.programme} · list refresh`, f: a.flags.find(f => f.rule === 'Sanctions hit'), a });
  out.push({ t: NOW - 2 * H, sev: 'sys', title: 'Sanctions lists refreshed', sub: 'OFAC SDN, EU and UK consolidated lists · no new fleet matches', sys: true });
  out.push({ t: NOW - 26 * H, sev: 'sys', title: 'Position cache rebuilt', sub: `${fmtN(LIVE.reduce((s, a) => s + a.stats.clean, 0))} positions stored · ${providerLabel()}`, sys: true });
  return out.sort((x, y) => y.t - x.t);
}
function updateBadge() { const seen = store.get('alertsSeen', 0); const n = alertsList().filter(x => x.t > seen && x.sev !== 'sys').length; const b = $('#tabbar .tab[data-page="alerts"] .bdg'); if (b) { b.textContent = n > 99 ? '99+' : n; b.hidden = !n; } }
function renderAlertsPage() {
  const items = alertsList(), seen = store.get('alertsSeen', 0); const groups = new Map();
  for (const it of items) { const k = fmtDY(it.t); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(it); }
  const dayLabel = k => k === fmtDY(NOW) ? 'Today' : k === fmtDY(NOW - D) ? 'Yesterday' : k;
  return `${topbar('Alerts')}<div class="content"><h1 class="largetitle">Alerts</h1><p class="sub">Flags raised in the last 14 days across the fleet, sanctions list changes and system events. Watched vessels first in the production feed.</p>
  ${[...groups].map(([k, arr]) => `<div class="gh">${dayLabel(k)}</div><div class="group">${arr.map(it => `<button class="alert ${it.t > seen && !it.sys ? 'unread' : ''}" ${it.f ? `data-act="alert" data-imo="${it.a.v.imo}" data-id="${it.f.id}"` : ''}><span class="sd ${it.sev}"></span><div><b>${esc(it.title)}</b><span>${esc(it.sub)}</span></div><span class="when">${fmtDT(it.t)}</span></button>`).join('')}</div>`).join('')}
  <p class="gf">Push notifications for watched vessels arrive with the production build (see Profile › Notifications).</p></div>`;
}
function renderReportsPage() {
  const reps = store.get('reports', []).slice().reverse();
  return `${topbar('Reports')}<div class="content"><h1 class="largetitle">Reports</h1><p class="sub">Vessel reports generated on this device. Each one carries identity, sanctions screening, the chart, the voyage table and every flag with its evidence.</p>
  <div class="group">${reps.length ? reps.map(r => { const v = BY_IMO[r.imo]; if (!v) return ''; const a = ANALYSIS.get(r.imo); return `<button class="grow" data-act="openreport" data-imo="${r.imo}">${ico(ICON.reports, 'var(--accent)')}<div class="lbl"><b>${esc(v.name)}</b><span>IMO ${v.imo} · ${a ? a.flags.length + ' flags · ' + a.voyages.length + ' voyages' : ''} · generated ${fmtDT(r.t)} ${TZ()}</span></div><span class="chev">${ICON.chevR}</span></button>`; }).join('') : '<div class="empty">No reports yet. Open a vessel on the chart and tap “Vessel report”.</div>'}</div>
  <div class="gh">Scheduled</div><div class="group">${grow('Daily fleet digest', 'Off', 'digest', 'Watchlist summary at 07:00 ' + TZ() + ' · production build', ico(ICON.bell, 'var(--orange)'))}</div>
  ${reps.length ? `<div class="group" style="margin-top:14px"><button class="grow red" data-act="clearreports">Clear report history</button></div>` : ''}</div>`;
}
function renderProfilePage() {
  const u = store.get('user', { email: 'analyst@example.com', name: 'Analyst' }); const initials = u.name.split(/\s+/).map(s => s[0]).join('').slice(0, 2).toUpperCase();
  const pv = S.pview;
  if (pv === 'root') return `${topbar('Profile')}<div class="content"><h1 class="largetitle">Profile</h1>
    <div class="pcard"><div class="avatar">${esc(initials)}</div><div><b>${esc(u.name)}</b><span>${esc(u.email)}</span><span>${esc(u.org || 'Your organisation')} · ${esc(u.role || 'Analyst')}</span></div></div>
    <div class="gh">Account</div><div class="group">${grow('Name', esc(u.name), 'edit-name')}${grow('Organisation', esc(u.org || 'Set'), 'edit-org')}${grow('Role', esc(u.role || 'Analyst'), 'edit-role')}</div>
    <div class="gh">Settings</div><div class="group">${grow('AIS provider', API.server ? esc(((S.me && S.me.provider) || 'server').split(' (')[0]) : ({ mock: 'Mock', kpler: 'Kpler', spire: 'Spire', datalastic: 'Datalastic', vesselfinder: 'VesselFinder' }[SET.provider] || 'Mock'), 'pv-provider', '', ico(ICON.key, 'var(--accent)'))}${grow('Rules & thresholds', '', 'pv-rules', 'Every threshold the engine uses', ico(ICON.rules, 'var(--orange)'))}${grow('Sensitive zones', `${GEO.zones.filter(z => z.enabled !== false).length} on`, 'pv-zones', '', ico(ICON.zones, 'var(--red)'))}${grow('Appearance & chart', SET.theme === 'system' ? 'System' : SET.theme === 'dark' ? 'Dark' : 'Light', 'pv-look', '', ico(ICON.look, '#5856D6'))}${grow('Notifications', Object.values(SET.notify).filter(Boolean).length + ' on', 'pv-notify', '', ico(ICON.bell, 'var(--green)'))}${grow('About & data sources', '', 'pv-about', '', ico(ICON.info, 'var(--fg3)'))}</div>
    <div class="gh">On this device</div><div class="group">${grow('Watchlist', watchlist().length + ' vessels', 'go-vessels')}${grow('Analyst notes', Object.values(store.get('notes', {})).filter(t => t && t.trim()).length + ' notes')}${grow('Reports', store.get('reports', []).length)}<button class="grow red" data-act="cleardata">Clear local data</button></div>
    <div class="group" style="margin-top:14px"><button class="grow red" data-act="signout">Sign out</button></div>
    <p class="gf">Signed in as ${esc(u.email)} · demo session kept on this device only.</p></div>`;
  const back = `<button class="ibtn" data-act="pv-root">${ICON.chevL}Profile</button>`;
  if (pv === 'provider' && API.server) return renderAdminProvider(back);
  if (pv === 'provider') {
    const provs = [['mock', 'Mock provider', 'Generated tracks, sample fleet'], ['kpler', 'Kpler / MarineTraffic', 'Global coastal + satellite · paid credits'], ['spire', 'Kpler / Spire Maritime', 'Global, strong satellite · paid contract'], ['datalastic', 'Datalastic', 'Global · monthly credit plans'], ['vesselfinder', 'VesselFinder API', 'Global · limited history · paid credits']];
    const cached = LIVE.reduce((s, a) => s + a.stats.clean, 0);
    return `${topbar('AIS provider', back)}<div class="content"><h1 class="largetitle">AIS provider</h1><p class="sub">One adapter interface. Switching provider never touches the rules or the screens.</p>
    <div class="gh">Provider</div><div class="group">${provs.map(([k, l, s]) => `<button class="grow" data-act="provider" data-id="${k}"><div class="lbl"><b>${l}</b><span>${s}</span></div>${SET.provider === k ? `<span class="check">${ICON.check}</span>` : ''}</button>`).join('')}</div>
    <div class="gh">API key</div><div class="group"><div class="grow"><div class="lbl"><b>Key</b></div><input type="password" id="apikey" value="${esc(SET.apiKey)}" placeholder="Paste key" autocomplete="off"></div><button class="grow" data-act="testkey"><div class="lbl"><b style="color:var(--accent)">Test connection</b></div></button></div><p class="gf">Stored on this device only and never committed. In production the key lives in <span class="mono">.env</span> on the server.</p>
    <div class="gh">Cache</div><div class="group">${grow('Positions stored', fmtN(cached))}${grow('Vessels with history', LIVE.length)}${grow('Credits used this month', SET.provider === 'mock' ? '0' : '—', '', 'Only the fetch step costs money')}</div></div>`;
  }
  if (pv === 'rules') {
    const num = (path, label, unit, step = 1) => { const [g, k] = path.split('.'); return `<div class="grow"><div class="lbl"><b>${label}</b></div><input type="number" data-rule="${path}" value="${RULES[g][k]}" step="${step}" min="0" aria-label="${label}"><span class="val">${unit}</span></div>`; };
    return `${topbar('Rules', back)}<div class="content"><h1 class="largetitle">Rules &amp; thresholds</h1><p class="sub">Edit a value and the engine re-runs on the whole fleet. These are the starting thresholds from the brief.</p>
    <div class="gh">Port call</div><div class="group">${num('portCall.maxSpeedKn', 'Speed under', 'kn', 0.1)}${num('portCall.minHours', 'For at least', 'h')}${num('portCall.portRadiusNm', 'Within', 'nm of a port')}</div>
    <div class="gh">AIS gap</div><div class="group">${num('aisGap.minHours', 'No position for more than', 'h')}${num('aisGap.highHours', 'High if longer than', 'h')}${num('aisGap.nearSensitiveNm', 'High if within', 'nm of a zone')}</div>
    <div class="gh">Draught change at sea</div><div class="group">${num('draughtChange.minMeters', 'Change of at least', 'm', 0.1)}</div>
    <div class="gh">Ship-to-ship transfer</div><div class="group">${num('sts.maxDistM', 'Other vessel within', 'm', 50)}${num('sts.maxSpeedKn', 'Both under', 'kn', 0.1)}${num('sts.minHours', 'For at least', 'h', 0.5)}</div>
    <div class="gh">Position jump</div><div class="group">${num('positionJump.maxImpliedKn', 'Implied speed above', 'kn')}</div>
    <div class="gh">Identity change</div><div class="group">${num('identity.mediumIfMoreThan', 'Medium if more than', 'changes')}</div>
    <div class="gh">Sanctions</div><div class="group">${num('sanctions.lookbackMonths', 'Listed now or in the past', 'months')}${grow('Lists', RULES.sanctions.lists.join(', '))}</div>
    <div class="group" style="margin-top:14px"><button class="grow" data-act="resetrules"><div class="lbl"><b style="color:var(--accent)">Reset to brief defaults</b></div></button></div></div>`;
  }
  if (pv === 'zones') return `${topbar('Zones', back)}<div class="content"><h1 class="largetitle">Sensitive zones</h1><p class="sub">A port call or anchorage inside a zone is a High flag; an AIS gap within ${RULES.aisGap.nearSensitiveNm} nm of one is raised to High.</p>
    <div class="group">${GEO.zones.map(z => `<div class="grow"><div class="lbl"><b>${esc(z.name)}</b><span>${esc(z.basis)} · ${z.poly.length} vertices</span></div>${sw('zone:' + z.id, z.enabled !== false)}</div>`).join('')}</div>
    <p class="gf">North Korea is on the list in the brief but outside the regions this build charts. In production you draw or import zones as GeoJSON (<span class="mono">config/zones.geojson</span>).</p></div>`;
  if (pv === 'look') return `${topbar('Appearance', back)}<div class="content"><h1 class="largetitle">Appearance &amp; chart</h1>
    <div class="gh">Theme</div><div class="seg">${[['system', 'System'], ['light', 'Light'], ['dark', 'Dark']].map(([k, l]) => `<button data-act="theme" data-id="${k}" aria-pressed="${SET.theme === k}">${l}</button>`).join('')}</div>
    <div class="gh">Chart</div><div class="group"><div class="grow"><div class="lbl"><b>Map tiles</b><span>OpenFreeMap base map · off = schematic coastlines, works offline</span></div>${sw('baseMap', SET.baseMap)}</div><div class="grow"><div class="lbl"><b>Port labels</b></div>${sw('portLabels', SET.portLabels)}</div><div class="grow"><div class="lbl"><b>Graticule</b><span>Latitude and longitude grid</span></div>${sw('graticule', SET.graticule)}</div></div>
    <div class="gh">Time</div><div class="group"><div class="grow"><div class="lbl"><b>Show times in local time</b><span>Default is UTC, as on the bridge</span></div>${sw('timeLocal', SET.timeLocal)}</div></div>
    <div class="gh">Accessibility</div><div class="group"><div class="grow"><div class="lbl"><b>Reduce transparency</b><span>Solid panels instead of glass</span></div>${sw('reduceTransparency', SET.reduceTransparency)}</div></div></div>`;
  if (pv === 'notify') return `${topbar('Notifications', back)}<div class="content"><h1 class="largetitle">Notifications</h1><p class="sub">What should reach your phone. Push delivery is part of the production build.</p>
    ${API.server ? `<div class="gh">This device</div><div class="group"><button class="grow" data-act="push"><div class="lbl"><b style="color:var(--accent)">${S.pushOn ? 'Push notifications on · tap to turn off' : 'Enable push notifications on this device'}</b><span>${(S.push && S.push.configured) ? 'High flags on watched vessels, sent by the refresh job' : 'Server has no VAPID keys yet (see docs/DEPLOY.md)'}</span></div></button></div>` : ''}
    <div class="group"><div class="grow"><div class="lbl"><b>New flags on watched vessels</b></div>${sw('notify.flags', SET.notify.flags)}</div><div class="grow"><div class="lbl"><b>Sanctions list changes</b><span>OFAC, EU, UK · daily refresh</span></div>${sw('notify.sanctions', SET.notify.sanctions)}</div><div class="grow"><div class="lbl"><b>AIS gaps over ${RULES.aisGap.highHours} h</b></div>${sw('notify.gaps', SET.notify.gaps)}</div><div class="grow"><div class="lbl"><b>Daily digest</b><span>07:00 ${TZ()}</span></div>${sw('notify.digest', SET.notify.digest)}</div></div></div>`;
  if (pv === 'about') return `${topbar('About', back)}<div class="content"><h1 class="largetitle">About</h1>
    <div class="group">${grow('Version', 'Prototype 0.2 · sample data')}${grow('Fleet', FLEET.length + ' fictional vessels')}${grow('Chart', 'Schematic coastlines (MapLibre tiles in production)')}${grow('Rules', '7 rules · ' + RULE_LIST.map(r => r.name).join(', '))}</div>
    <div class="gh">Data sources (production)</div><div class="group">${grow('AIS positions', 'Kpler · Spire · Datalastic · VesselFinder')}${grow('Sanctions', 'OFAC SDN · EU · UK · OpenSanctions')}${grow('Ports', 'World Port Index (NGA)')}${grow('Cross-checks', 'Global Fishing Watch events · GPSJam')}</div>
    <p class="gf">Every vessel is keyed on its IMO number. Every paid position is cached once. No scraping of provider websites. Draught-based flags are indicators, not proof.</p></div>`;
  return '';
}

/* ------------------------------------- admin (server mode) ------------------------------------- */
const PROVS = [['mock', 'Mock provider', 'Generated tracks, sample fleet, no credits'], ['aisstream', 'aisstream.io (free)', 'Live coastal AIS recorded by your own server from the day you start · no past history, no open-sea coverage · free key from aisstream.io (GitHub sign-in)'], ['datalastic', 'Datalastic', 'Global · 12 months of history per ship · monthly credit plans · key from datalastic.com'], ['kpler', 'Kpler / MarineTraffic', 'Global coastal + satellite · contract · adapter pending their answers']];
const fmtAgo = ms => { if (!ms) return '—'; const m = Math.max(0, Math.round((Date.now() - ms) / 60000)); return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.round(m / 60) + ' h ago' : Math.round(m / 1440) + ' d ago'; };
function renderAdminProvider(back) {
  const cfg = S.admin || {}; const isAdmin = (S.me && S.me.role) === 'admin';
  if (!S.admin) API.adminConfig().then(c => { S.admin = c; if (S.page === 'profile' && S.pview === 'provider') renderPage('profile'); }).catch(e => { S.admin = { error: e.message }; renderPage('profile'); });
  const fp = S.firstPull || {};
  return `${topbar('AIS provider', back)}<div class="content"><h1 class="largetitle">AIS provider</h1><p class="sub">${isAdmin ? 'Everything here runs on the server. Paste the key once; it is stored on the server, never on this phone.' : 'Only an admin token can change the provider. Ask your administrator.'}</p>
    ${cfg.error ? `<div class="hint">${esc(cfg.error)}</div>` : ''}
    <div class="gh">Active</div><div class="group">${grow('Provider', esc((cfg.active || (S.me && S.me.provider) || '…').split(' (')[0]))}${grow('Credits used since restart', cfg.credits_used ?? '—')}${grow('Track fetches since restart', cfg.fetches_this_run ?? '—', '', cfg.active && (cfg.active.startsWith('Mock') || cfg.active.startsWith('Recorded')) ? 'free on this provider' : 'each one is paid')}${grow('Database', cfg.database === undefined ? '—' : cfg.database ? 'PostGIS' : 'in-memory (dev)')}</div>
    <div class="gh">Server updates (the server is the CI)</div><div class="group">${cfg.update ? grow('Last update', `${cfg.update.result === 'ok' ? '✅ deployed' : '⛔ ' + esc(cfg.update.result.replace('_', ' '))} · ${esc((cfg.update.commit || '').slice(0, 7))}`, '', `${esc(cfg.update.tests || '')}${cfg.update.checked_at ? ' · ' + fmtAgo(Date.parse(cfg.update.checked_at)) : ''}`) + (cfg.update.result !== 'ok' && cfg.update.detail ? `<div class="grow"><div class="lbl"><span style="color:var(--high);white-space:pre-wrap">${esc(cfg.update.detail)}</span></div></div>` : '') : grow('Last update', 'no auto-update yet', '', 'the server checks GitHub every 10 minutes, tests the new build, and switches only when green')}</div>
    <div class="gh">Recorded AIS (free feed)</div><div class="group">${cfg.live ? grow('Positions stored', fmtN(cfg.live.positions || 0), '', cfg.live.newest ? 'latest ' + fmtAgo(cfg.live.newest) : 'recorder not running yet') + grow('Ships seen', `${fmtN(cfg.live.mmsi || 0)} · ${fmtN(cfg.live.with_imo || 0)} with IMO`) + grow('Recording since', cfg.live.oldest ? fmtD(cfg.live.oldest) : '—', '', 'history starts here; buy older months per ship only when needed') : grow('Recorder', 'no live table yet', '', 'runs after migration 003 on the database')}</div>
    ${isAdmin ? `<div class="gh">Switch provider</div><div class="group">${PROVS.map(([k, l, d]) => `<button class="grow" data-act="adm-provider" data-id="${k}"><div class="lbl"><b>${l}</b><span>${d}${cfg.keys && cfg.keys[k] ? ' · key ' + esc(cfg.keys[k]) : ''}</span></div>${cfg.provider === k ? `<span class="check">${ICON.check}</span>` : ''}</button>`).join('')}</div>
    <div class="gh">API key for ${esc((PROVS.find(p => p[0] === (S.admKey || cfg.provider)) || PROVS[1])[1])}</div><div class="group"><div class="grow"><div class="lbl"><b>Key</b></div><input type="password" id="admkey" placeholder="${cfg.keys && cfg.keys[S.admKey || cfg.provider] ? 'stored: ' + esc(cfg.keys[S.admKey || cfg.provider]) : 'paste key'}" autocomplete="off" autocapitalize="off" spellcheck="false"></div><button class="grow" data-act="adm-savekey"><div class="lbl"><b style="color:var(--accent)">Save key and switch</b></div></button><button class="grow" data-act="adm-test"><div class="lbl"><b style="color:var(--accent)">Test connection</b><span>One cheap search call; shows credits used</span></div></button></div>
    <div class="gh">Cross-check token · Global Fishing Watch (free, non-commercial licence)</div><div class="group"><div class="grow"><div class="lbl"><b>Token</b></div><input type="password" id="gfwkey" placeholder="${cfg.keys && cfg.keys.gfw ? 'stored: ' + esc(cfg.keys.gfw) : 'paste API token'}" autocomplete="off" autocapitalize="off" spellcheck="false"></div><button class="grow" data-act="adm-gfwkey"><div class="lbl"><b style="color:var(--accent)">Save cross-check token</b><span>Adds a “Cross-check” button on every vessel: GFW port visits, loitering, encounters and AIS-off events from satellite AIS</span></div></button></div>
    ${S.admTest ? `<div class="hint">${esc(S.admTest)}</div>` : ''}
    <div class="gh">First pull (acceptance check)</div><div class="group"><div class="grow"><div class="lbl"><b>IMO numbers</b><span>Up to 10, separated by spaces or commas</span></div></div><div style="padding:0 16px 12px"><textarea class="notebox" id="fpimos" placeholder="9000036 9000014" style="min-height:56px">${esc(fp.input || '')}</textarea></div><button class="grow" data-act="adm-firstpull"><div class="lbl"><b style="color:var(--accent)">${fp.running ? 'Running…' : 'Run first pull'}</b><span>Fetches 12 months per ship (paid on a real provider), then checks positions, draught, port calls, voyages, cache</span></div></button></div>
    ${fp.results ? fp.results.map(r => `<div class="flag ${r.ok ? 'info' : 'medium'}"><div class="fh"><span class="pill ${r.ok ? 'ok' : 'medium'}">${r.ok ? 'OK' : 'CHECK'}</span><span class="ft">${r.imo}${r.name ? ' · ' + esc(r.name) : ''}</span></div>${r.error ? `<ul class="fl"><li>${esc(r.error)}</li></ul>` : `<ul class="fl">${Object.entries(r.checks).map(([k, v]) => `<li>${v ? '✓' : '✗'} ${esc(k)}</li>`).join('')}<li class="mono" style="font-size:11px">${r.stats.clean} clean of ${r.stats.raw} raw · ${r.stats.port_calls} calls · ${r.stats.voyages} voyages · ${r.stats.flags} flags (${r.sev.high} high) · ${esc(r.status)}</li></ul>`}</div>`).join('') : ''}
    <div class="gh">Jobs</div><div class="group"><button class="grow" data-act="adm-refresh"><div class="lbl"><b style="color:var(--accent)">Refresh watched vessels now</b><span>Same as the 30-minute job: new tail of positions, new flags become alerts</span></div></button><button class="grow" data-act="adm-sanctions"><div class="lbl"><b style="color:var(--accent)">Refresh sanctions lists now</b><span>OFAC, EU, UK (needs the database)</span></div></button></div>` : ''}
    <p class="gf">Switching provider keeps every position already stored; only new fetches use the new source.</p></div>`;
}
async function adminAction(act, b) {
  const key = () => ($('#admkey') ? $('#admkey').value.trim() : '');
  try {
    if (act === 'adm-provider') { S.admKey = b.dataset.id; if (b.dataset.id === 'mock' || (S.admin && S.admin.keys && S.admin.keys[b.dataset.id])) { await API.adminProvider(b.dataset.id, key() || null); toast('Provider switched'); S.admin = null; } renderPage('profile'); }
    else if (act === 'adm-savekey') { const p = S.admKey || (S.admin && S.admin.provider) || 'datalastic'; if (p !== 'mock' && !key()) { toast('Paste the key first'); return; } await API.adminProvider(p, key() || null); toast('Key saved on the server'); S.admin = null; renderPage('profile'); }
    else if (act === 'adm-gfwkey') { const t = $('#gfwkey') ? $('#gfwkey').value.trim() : ''; if (!t) { toast('Paste the token first'); return; } await API.adminKey('gfw', t); toast('Cross-check token saved'); S.admin = null; renderPage('profile'); }
    else if (act === 'adm-test') { S.admTest = 'Testing…'; renderPage('profile'); const r = await API.adminTest(); S.admTest = r.ok ? `OK · ${r.provider} · ${r.matches} matches for “MAERSK” (${(r.sample || []).join(', ') || 'none'}) · ${r.credits_used} credits used · ${r.ms} ms` : `Failed: ${r.error}`; S.admin = null; renderPage('profile'); }
    else if (act === 'adm-firstpull') { const txt = ($('#fpimos') ? $('#fpimos').value : ''); const imos = (txt.match(/\d{7}/g) || []).slice(0, 10).map(Number); if (!imos.length) { toast('Type at least one 7-digit IMO'); return; } S.firstPull = { input: txt, running: true }; renderPage('profile'); const res = await API.adminFirstPull(imos); S.firstPull = { input: txt, results: res }; S.admin = null; renderPage('profile'); }
    else if (act === 'adm-refresh') { toast('Refreshing…'); const r = await API.jobsRefresh(); toast(`${r.vessels} vessels · ${r.new_alerts} new alerts · ${r.fetches} fetches`); }
    else if (act === 'adm-sanctions') { toast('Refreshing lists…'); const r = await API.jobsSanctions(); toast('Sanctions: ' + JSON.stringify(r).slice(0, 120)); }
  } catch (e) { toast('Failed: ' + e.message); if (S.firstPull) S.firstPull.running = false; renderPage('profile'); }
}

/* ------------------------------------- web push ------------------------------------- */
function b64ToU8(b64) { const pad = '='.repeat((4 - b64.length % 4) % 4); const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(raw, c => c.charCodeAt(0)); }
async function togglePush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) { toast('Push is not available in this browser'); return; }
  const reg = await navigator.serviceWorker.ready;
  const cur = await reg.pushManager.getSubscription();
  if (cur) { await API.pushUnsubscribe(cur.toJSON()).catch(() => {}); await cur.unsubscribe(); S.pushOn = false; toast('Push notifications off'); renderPage('profile'); return; }
  if (!(S.push && S.push.publicKey)) { toast('Server has no push keys yet'); return; }
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') { toast('Notifications were not allowed'); return; }
  try {
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(S.push.publicKey) });
    await API.pushSubscribe(sub.toJSON()); S.pushOn = true; toast('Push notifications on'); renderPage('profile');
  } catch (e) { toast('Could not subscribe: ' + e.message); }
}
async function checkPush() { try { if (!('serviceWorker' in navigator) || !('PushManager' in window)) return; const reg = await navigator.serviceWorker.ready; S.pushOn = !!(await reg.pushManager.getSubscription()); } catch (e) { /* no push */ } }

/* ------------------------------------- login ------------------------------------- */
function renderLogin() {
  const el = $('#login'); el.hidden = false;
  el.innerHTML = `<form class="lcard glass" id="loginForm"><div class="wm"><span class="wmark">${ICON.logo}</span><div><h1>MarineEdge</h1><p>Vessel due diligence · Black Sea &amp; Gulf</p></div></div>
  <div class="field"><label for="lemail">Work email</label><input id="lemail" type="email" autocomplete="username" placeholder="you@company.com" required value="${esc(store.get('lastEmail', ''))}"></div>
  <div class="field"><label for="lpass">${API.server ? 'API token' : 'Password'}</label><input id="lpass" type="password" autocomplete="current-password" placeholder="••••••••" required></div>
  <button class="cap primary" type="submit">Sign in</button><button class="cap tint" type="button" data-act="passkey">Continue with a passkey</button>
  <div class="linkrow"><button type="button" data-act="forgot">Forgot password</button><button type="button" data-act="sso">Company SSO</button></div>
  <p style="font-size:12px">${API.server ? 'Enter the API token from your administrator. SSO replaces this on the company deployment.' : 'Demo sign-in: any email and password work. Production uses your identity provider; sessions never leave your server.'}</p></form>`;
  el.querySelector('#loginForm').addEventListener('submit', e => { e.preventDefault(); const email = $('#lemail').value.trim() || 'analyst@example.com'; if (API.server) store.set('token', $('#lpass').value.trim()); signIn(email); if (API.server && !LIVE.length && !S.loading) loadFleet(() => { updateBadge(); renderSheet(); }); });
  el.addEventListener('click', e => { const b = e.target.closest('[data-act]'); if (!b) return; if (b.dataset.act === 'passkey') signIn($('#lemail').value.trim() || 'analyst@example.com'); if (b.dataset.act === 'forgot') toast('Reset link would be emailed in production'); if (b.dataset.act === 'sso') toast('SSO redirect happens in production'); });
}
function signIn(email) {
  const name = email.split('@')[0].split(/[._-]/).map(s => s ? s[0].toUpperCase() + s.slice(1) : '').join(' ') || 'Analyst';
  const prev = store.get('user', {});
  const u = Object.assign({ org: email.split('@')[1] ? email.split('@')[1].split('.')[0].replace(/^\w/, c => c.toUpperCase()) : 'Your organisation', role: 'Analyst' }, prev, { email, name: prev.name || name });
  store.set('user', u); store.set('auth', { t: NOW }); store.set('lastEmail', email); $('#login').hidden = true; toast(`Signed in as ${u.name}`); if (S.page === 'profile') renderPage('profile');
}
function signOut() { store.del('auth'); store.del('token'); S.pview = 'root'; renderLogin(); }

/* ------------------------------------- report ------------------------------------- */
function reportText(a) {
  const v = a.v, L = [];
  L.push(`VESSEL REPORT — ${v.name} (IMO ${v.imo})`, `Generated ${fmtISO(NOW)} · MarineEdge · sample data, fictional vessel`, '');
  L.push('IDENTITY', `Name ${v.name}${v.exNames.length ? ' (ex ' + v.exNames.join(', ') + ')' : ''}`, `IMO ${v.imo} · MMSI ${v.mmsi} · call sign ${v.callsign}`, `Flag ${v.flag} · ${v.sub} · ${fmtN(v.dwt)} dwt · built ${v.built}, ${v.builder}`, `Registered owner ${v.regOwner} · beneficial owner ${v.benOwner} · ISM ${v.ism} · class ${v.classSoc} · P&I ${v.pi}`, `Status: ${statusLine(a).replace(/&amp;/g, '&')}`, '');
  L.push('SANCTIONS SCREENING', ...RULES.sanctions.lists.map(l => { const s = v.sanctions.find(s => s.list === l); return `${l}: ${s ? 'LISTED ' + fmtDY(s.t) + ' · ' + s.programme : 'clear'}`; }), '');
  L.push(`VOYAGES, LAST 12 MONTHS (${a.voyages.length})`);
  for (const vg of a.voyages.slice().reverse()) L.push(`V${vg.n}  ${vg.from ? vg.from.port.name : 'history start'} → ${vg.to ? vg.to.port.name : a.static.destination || '…'}  ${fmtDY(vg.depart)} – ${vg.arrive ? fmtDY(vg.arrive) : 'underway'}  ${vg.nm} nm  draught ${vg.draughtOut}/${vg.draughtIn} m  dark ${Math.round(vg.darkH)} h  flags ${vg.flags.length}`);
  L.push('', `RED FLAGS (${a.flags.length}: ${a.sev.high} high, ${a.sev.medium} medium, ${a.sev.info} info)`);
  for (const f of a.flags) { L.push(`[${f.severity.toUpperCase()}] ${f.title}${f.voyage ? ' (V' + f.voyage.n + ')' : ''}`); f.lines.forEach(l => L.push('   ' + l)); if (f.evidence) { f.evidence.before.forEach(p => L.push(`   before ${fmtDT(p.t)} ${fmtDM(p.lat, p.lon)} ${p.sog} kn ${p.draught} m`)); f.evidence.after.forEach(p => L.push(`   after  ${fmtDT(p.t)} ${fmtDM(p.lat, p.lon)} ${p.sog} kn ${p.draught} m`)); } }
  const notes = store.get('notes', {}); const mine = Object.entries(notes).filter(([k, t]) => k.startsWith(v.imo + '-') && t.trim());
  if (mine.length) { L.push('', 'ANALYST NOTES'); mine.forEach(([k, t]) => L.push(`V${k.split('-')[1]}: ${t}`)); }
  L.push('', `Rules: port call < ${RULES.portCall.maxSpeedKn} kn for ${RULES.portCall.minHours} h within ${RULES.portCall.portRadiusNm} nm · AIS gap > ${RULES.aisGap.minHours} h (high > ${RULES.aisGap.highHours} h or within ${RULES.aisGap.nearSensitiveNm} nm of a sensitive zone) · draught change ≥ ${RULES.draughtChange.minMeters} m at sea · STS within ${RULES.sts.maxDistM} m, both < ${RULES.sts.maxSpeedKn} kn, ≥ ${RULES.sts.minHours} h · jump > ${RULES.positionJump.maxImpliedKn} kn · identity changes · sanctions lists.`);
  return L.join('\n');
}
function openReport(imo = S.imo, record = true) {
  if (!ANALYSIS.has(imo)) analyze(BY_IMO[imo]);
  const a = ANALYSIS.get(imo), v = a.v; S.imo = imo; const img = Chart.snapshot(boundsOf(a.track), 720, 440); const notes = store.get('notes', {});
  if (record) { const reps = store.get('reports', []).filter(r => r.imo !== imo); reps.push({ imo, t: NOW }); store.set('reports', reps); }
  const el = $('#report');
  el.innerHTML = `<div class="report-in"><div class="report-bar glass"><button class="ibtn" data-act="closereport">${ICON.chevL}Back</button><button class="cap tint sm" data-act="copyreport">Copy as text</button></div>
  <div class="rp"><h1>${esc(v.name)}</h1><div class="mono muted" style="font-size:12px;margin-top:4px">IMO ${v.imo} · MMSI ${v.mmsi} · ${v.callsign} · report generated ${fmtISO(NOW)}</div><p class="muted" style="font-size:12px;margin:8px 0 0">MarineEdge · sample data, fictional vessel and generated track. The production build prints this page to PDF with Playwright; here you can copy it as text.</p></div>
  <div class="rp"><h2>Identity</h2><table class="kv"><tr><th>Name</th><td>${esc(v.name)}${v.exNames.length ? ` <span class="muted">(ex ${esc(v.exNames.join(', '))})</span>` : ''}</td></tr><tr><th>Flag</th><td>${esc(v.flag)}</td></tr><tr><th>Type</th><td>${esc(v.sub)} · ${fmtN(v.dwt)} dwt · ${v.loa} m × ${v.beam} m</td></tr><tr><th>Built</th><td>${v.built} · ${esc(v.builder)}</td></tr><tr><th>Owner / manager</th><td>${esc(v.regOwner)} · ${esc(v.ism)}</td></tr><tr><th>Beneficial owner</th><td>${esc(v.benOwner)}</td></tr><tr><th>Class / P&amp;I</th><td>${esc(v.classSoc)} · ${esc(v.pi)}</td></tr><tr><th>Status</th><td>${statusLine(a)}</td></tr><tr><th>Sanctions</th><td>${RULES.sanctions.lists.map(l => { const s = v.sanctions.find(s => s.list === l); return `${l}: ${s ? `<span class="pill high">LISTED</span> ${fmtDY(s.t)}` : '<span class="pill ok">CLEAR</span>'}`; }).join(' · ')}</td></tr>${v.history.length ? `<tr><th>Identity changes</th><td>${v.history.slice().sort((x, y) => y.t - x.t).map(h => `${fmtDY(h.t)}: ${h.field} ${esc(h.from)} → ${esc(h.to)}`).join('<br>')}</td></tr>` : ''}</table></div>
  <div class="rp"><h2>Chart · 12 months, one colour per voyage</h2><img src="${img}" alt="Chart of the vessel's voyages over the last 12 months" width="720" height="440"></div>
  <div class="rp"><h2>Voyages (${a.voyages.length})</h2><div class="rtab-wrap"><table class="rtab"><thead><tr><th>#</th><th>From → to</th><th>Departed</th><th>Arrived</th><th>nm</th><th>Draught out/in</th><th>Dark</th><th>Flags</th></tr></thead><tbody>${a.voyages.slice().reverse().map(vg => `<tr><td class="mono">V${vg.n}</td><td>${vg.from ? esc(vg.from.port.name) : 'History start'} → ${vg.to ? esc(vg.to.port.name) : esc(a.static.destination || '…')}</td><td class="mono">${fmtD(vg.depart)}</td><td class="mono">${vg.arrive ? fmtD(vg.arrive) : 'underway'}</td><td class="mono">${fmtN(vg.nm)}</td><td class="mono">${vg.draughtOut} / ${vg.draughtIn}</td><td class="mono">${vg.darkH ? Math.round(vg.darkH) + ' h' : '—'}</td><td class="mono">${vg.flags.length ? `<span style="color:var(--high);font-weight:600">${vg.flags.length}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div></div>
  <div class="rp"><h2>Red flags (${a.flags.length})</h2>${a.flags.length ? a.flags.map(f => `<div class="flag ${f.severity}"><div class="fh"><span class="pill ${f.severity}">${f.severity.toUpperCase()}</span><span class="ft">${esc(f.title)}</span>${f.voyage ? `<span class="badge">V${f.voyage.n}</span>` : ''}</div><ul class="fl">${f.lines.map(l => `<li>${esc(l)}</li>`).join('')}</ul>${f.evidence ? `<div class="evid">${f.evidence.before.map(p => `<span><b>${fmtDT(p.t)}</b> ${fmtDM(p.lat, p.lon)} · ${p.sog} kn · ${p.draught} m</span>`).join('')}<span>— ${esc(f.rule.toLowerCase())} —</span>${f.evidence.after.map(p => `<span><b>${fmtDT(p.t)}</b> ${fmtDM(p.lat, p.lon)} · ${p.sog} kn · ${p.draught} m</span>`).join('')}</div>` : ''}</div>`).join('') : '<p class="muted">No red flags in the last 12 months.</p>'}</div>
  ${Object.entries(notes).some(([k, t]) => k.startsWith(v.imo + '-') && t.trim()) ? `<div class="rp"><h2>Analyst notes</h2>${Object.entries(notes).filter(([k, t]) => k.startsWith(v.imo + '-') && t.trim()).map(([k, t]) => `<p><b>V${k.split('-')[1]}</b> · ${esc(t)}</p>`).join('')}</div>` : ''}
  <p class="muted" style="font-size:11px">Thresholds: port call under ${RULES.portCall.maxSpeedKn} kn for ${RULES.portCall.minHours} h within ${RULES.portCall.portRadiusNm} nm of a port or inside an anchorage · AIS gap over ${RULES.aisGap.minHours} h at sea, High over ${RULES.aisGap.highHours} h or within ${RULES.aisGap.nearSensitiveNm} nm of a sensitive zone · draught change ≥ ${RULES.draughtChange.minMeters} m with no port call between · STS: another vessel within ${RULES.sts.maxDistM} m, both under ${RULES.sts.maxSpeedKn} kn for ${RULES.sts.minHours} h+, outside port limits · position jump above ${RULES.positionJump.maxImpliedKn} kn implied · identity change Info, Medium if more than ${RULES.identity.mediumIfMoreThan} · sanctions: IMO on OFAC, EU or UK lists now or in the past ${RULES.sanctions.lookbackMonths} months.</p></div>`;
  el.hidden = false; el.scrollTop = 0;
}
async function copyReport() {
  const text = reportText(ANALYSIS.get(S.imo));
  try { await navigator.clipboard.writeText(text); toast('Report copied'); }
  catch (e) { const ta = document.createElement('textarea'); ta.value = text; ta.style.cssText = 'position:fixed;left:5%;top:10%;width:90%;height:50%;z-index:40'; document.body.appendChild(ta); ta.select(); toast('Select and copy the text'); ta.addEventListener('blur', () => ta.remove(), { once: true }); }
}

/* ------------------------------------- boot ------------------------------------- */
function wireUI() {
  $('#regions').innerHTML = Object.entries(REGIONS).map(([k, r]) => `<button class="rchip" role="tab" data-region="${k}" aria-pressed="${k === S.region}">${esc(r.label)}</button>`).join('');
  $('#regions').addEventListener('click', e => { const c = e.target.closest('.rchip'); if (c) setRegion(c.dataset.region); });
  $('#tabbar').innerHTML = [['chart', 'Chart'], ['vessels', 'Vessels'], ['alerts', 'Alerts'], ['reports', 'Reports'], ['profile', 'Profile']].map(([k, l]) => `<button class="tab" role="tab" data-page="${k}" aria-selected="${k === S.page}" aria-label="${l}">${ICON[k]}<span>${l}</span>${k === 'alerts' ? '<span class="bdg" hidden></span>' : ''}</button>`).join('');
  $('#tabbar').addEventListener('click', e => { const t = e.target.closest('.tab'); if (t) showPage(t.dataset.page); });
  const q = $('#q');
  q.addEventListener('input', () => { S.query = q.value.trim(); $('#qclear').hidden = !S.query; if (S.query.length >= 2) { S.mode = 'search'; renderSheet(); Sheet.snap('half'); } else if (S.mode === 'search') { S.mode = 'region'; renderSheet(); } });
  q.addEventListener('focus', () => { if (isMobile() && Sheet.pos === 'peek') Sheet.snap('half'); });
  q.addEventListener('keydown', e => { if (e.key === 'Enter') { const r = Provider.searchVessel(S.query); if (r.length === 1) openVessel(r[0].imo); q.blur(); } });
  $('#qclear').addEventListener('click', () => { q.value = ''; S.query = ''; $('#qclear').hidden = true; if (S.mode === 'search') { S.mode = 'region'; renderSheet(); } q.focus(); });
  $('#sheetBody').addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (!b) return; const act = b.dataset.act;
    if (act === 'open') openVessel(+b.dataset.imo);
    else if (act === 'type') { S.type = b.dataset.type; renderSheet(); Chart.draw(); }
    else if (act === 'flagged') { S.flaggedOnly = !S.flaggedOnly; renderSheet(); Chart.draw(); }
    else if (act === 'back') backToRegion();
    else if (act === 'vessel') { S.mode = 'vessel'; S.voyage = null; S.focusFlag = null; renderSheet(); $('#sheetBody').scrollTop = 0; Chart.fitBounds(boundsOf(ANALYSIS.get(S.imo).track)); }
    else if (act === 'vtab') { S.vtab = b.dataset.tab; S.focusFlag = null; renderSheet(); Chart.draw(); }
    else if (act === 'voyage') openVoyage(+b.dataset.n);
    else if (act === 'fitvoyage') { const a = ANALYSIS.get(S.imo), vg = a.voyages.find(x => x.n === S.voyage); if (vg) { Sheet.snap('peek'); Chart.fitBounds(boundsOf(vg.pts)); } }
    else if (act === 'flag') { const f = ANALYSIS.get(S.imo).flags.find(f => f.id === b.dataset.id); if (f) focusFlag(f, false, 'peek'); }
    else if (act === 'fit') { Sheet.snap('peek'); Chart.fitBounds(boundsOf(ANALYSIS.get(S.imo).track)); }
    else if (act === 'watch') { toggleWatch(S.imo); renderSheet(); updateBadge(); }
    else if (act === 'xcheck') { XCHECK.set(S.imo, { loading: true }); renderSheet(); API.crosscheck(S.imo).then(r => { XCHECK.set(S.imo, r); renderSheet(); }).catch(e => { XCHECK.set(S.imo, { ok: false, error: e.message }); renderSheet(); }); }
    else if (act === 'xcheck-go') { const lo = parseFloat(b.dataset.lon), la = parseFloat(b.dataset.lat); Sheet.snap('peek'); Chart.fitBounds([lo - 1.5, la - 1, lo + 1.5, la + 1]); }
    else if (act === 'report') { if (API.server) { toast('Generating PDF…'); fetch(API.reportUrl(S.imo), { method: 'POST', headers: API.headers() }).then(r => { if (!r.ok) throw new Error(r.status); return r.blob(); }).then(b => { const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `marineedge-${S.imo}.pdf`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 10000); }).catch(err => toast('Report failed: ' + err.message)); } else openReport(); }
  });
  let noteT = 0;
  $('#sheetBody').addEventListener('input', e => { if (e.target.id === 'note') { const n = store.get('notes', {}); n[S.imo + '-' + S.voyage] = e.target.value; store.set('notes', n); if (API.server) { clearTimeout(noteT); const imo = S.imo, vn = S.voyage, text = e.target.value; noteT = setTimeout(() => API.putNote(imo, vn, text).catch(() => toast('Note not saved on the server')), 800); } } });
  $('#report').addEventListener('click', e => { const b = e.target.closest('[data-act]'); if (!b) return; if (b.dataset.act === 'closereport') { $('#report').hidden = true; if (S.page === 'reports') renderPage('reports'); } if (b.dataset.act === 'copyreport') copyReport(); });
  for (const p of ['vessels', 'alerts', 'reports', 'profile']) {
    const el = $('#page-' + p);
    el.addEventListener('scroll', () => { const tb = el.querySelector('[data-tb]'); if (tb) tb.classList.toggle('on', el.scrollTop > 36); }, { passive: true });
    el.addEventListener('click', e => { const b = e.target.closest('[data-act]'); if (!b) return; pageAction(b.dataset.act, b); });
    el.addEventListener('change', e => { const t = e.target; if (t.dataset.rule) { const [g, k] = t.dataset.rule.split('.'); const v = parseFloat(t.value); if (Number.isFinite(v)) { RULES[g][k] = v; store.set('rules', RULES); rerun('Rules re-run on ' + FLEET.length + ' vessels'); } } if (t.id === 'apikey') { SET.apiKey = t.value; saveSettings(); } });
  }
  $('#zin').addEventListener('click', () => { Chart.zoomAt(Chart.w / 2, Chart.h / 2, 1.6); if (!Base.active) onMoveEnd(); });
  $('#zout').addEventListener('click', () => { Chart.zoomAt(Chart.w / 2, Chart.h / 2, 1 / 1.6); if (!Base.active) onMoveEnd(); });
  $('#zfit').addEventListener('click', () => { if (S.mode === 'vessel' || S.mode === 'voyage') { const a = ANALYSIS.get(S.imo); const vg = S.mode === 'voyage' && a.voyages.find(x => x.n === S.voyage); Chart.fitBounds(boundsOf(vg ? vg.pts : a.track)); } else Chart.fitBounds(REGIONS[S.region].bounds); });
  const redraw = () => Chart.draw();
  const retheme = () => { Base.setTheme(isDark()); Chart.draw(); };
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', retheme);
  new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(redraw);
  window.addEventListener('resize', () => { if (isMobile()) Sheet.snap(Sheet.pos); else Sheet.snap('half'); });
}
function pageAction(act, b) {
  if (act === 'open') openVessel(+b.dataset.imo);
  else if (act === 'vseg') { S.vseg = b.dataset.seg; renderPage('vessels'); }
  else if (act === 'alert') { const a = ANALYSIS.get(+b.dataset.imo); const f = a && a.flags.find(f => f.id === b.dataset.id); if (f && !f.vesselLevel) focusFlag(f, true); else openVessel(+b.dataset.imo); }
  else if (act === 'openreport') openReport(+b.dataset.imo, false);
  else if (act === 'clearreports') { store.set('reports', []); renderPage('reports'); }
  else if (act === 'digest') toast('Scheduled digests ship with the production build');
  else if (act.startsWith('pv-')) { S.pview = act.slice(3); renderPage('profile'); }
  else if (act === 'go-vessels') { S.vseg = 'watch'; showPage('vessels'); }
  else if (act === 'edit-name' || act === 'edit-org' || act === 'edit-role') { const u = store.get('user', {}); const key = act.slice(5); const cur = u[key] || ''; const el = b.querySelector('.val') || b.querySelector('.lbl'); el.innerHTML = `<input type="text" id="edit" value="${esc(cur)}" style="text-align:right;border:0;background:var(--fill);border-radius:8px;padding:4px 8px;width:160px;color:var(--fg)">`; const inp = el.querySelector('input'); inp.focus(); const done = () => { u[key] = inp.value.trim() || cur; store.set('user', u); renderPage('profile'); }; inp.addEventListener('blur', done, { once: true }); inp.addEventListener('keydown', e => { if (e.key === 'Enter') inp.blur(); }); }
  else if (act === 'cleardata') { ['watch', 'notes', 'reports', 'alertsSeen'].forEach(k => store.del(k)); toast('Local data cleared'); renderPage('profile'); updateBadge(); }
  else if (act.startsWith('adm-')) adminAction(act, b);
  else if (act === 'push') togglePush();
  else if (act === 'signout') signOut();
  else if (act === 'provider') { SET.provider = b.dataset.id; saveSettings(); renderPage('profile'); toast(SET.provider === 'mock' ? 'Mock provider active' : providerLabel() + ' selected · needs a key and hosting'); }
  else if (act === 'testkey') toast(SET.provider === 'mock' ? 'Mock provider: OK · 0 credits used' : SET.apiKey ? 'This preview cannot reach outside APIs; test from the hosted build' : 'Paste an API key first');
  else if (act === 'resetrules') { Object.assign(RULES, { portCall: { maxSpeedKn: 0.5, minHours: 6, portRadiusNm: 5, mergeWithinHours: 36 }, sanctions: { lookbackMonths: 12, lists: ['OFAC SDN', 'EU', 'UK'] }, aisGap: { minHours: 6, highHours: 24, nearSensitiveNm: 100 }, draughtChange: { minMeters: 1.0 }, sts: { maxDistM: 500, maxSpeedKn: 1.0, minHours: 2 }, positionJump: { maxImpliedKn: 30 }, identity: { mediumIfMoreThan: 1 } }); store.del('rules'); renderPage('profile'); rerun('Defaults restored'); }
  else if (act === 'theme') { SET.theme = b.dataset.id; saveSettings(); applyAppearance(); renderPage('profile'); }
  else if (act === 'switch') {
    const key = b.dataset.key; const on = b.getAttribute('aria-checked') !== 'true'; b.setAttribute('aria-checked', on);
    if (key.startsWith('zone:')) { const id = key.slice(5); SET.zonesOff = on ? SET.zonesOff.filter(z => z !== id) : [...SET.zonesOff, id]; saveSettings(); applyAppearance(); rerun(`${on ? 'Zone on' : 'Zone off'} · rules re-run`); return; }
    if (key.startsWith('notify.')) { SET.notify[key.slice(7)] = on; saveSettings(); return; }
    SET[key] = on; saveSettings(); applyAppearance();
    if (key === 'baseMap') { toast(on ? 'Map tiles on after reload' : 'Schematic chart after reload'); return; }
    if (key === 'timeLocal') rerun(on ? 'Times shown in local time' : 'Times shown in UTC'); else Chart.draw();
  }
}
function loadFleet(done) {
  let i = 0; const loading = $('#loading');
  if (API.server) {
    loading.hidden = false; loading.textContent = 'Loading fleet from server…';
    API.me().then(me => { S.me = me; if (Array.isArray(me.watchlist)) store.set('watch', me.watchlist); S.push = me.push || {}; }).catch(() => {});
    API.fleet().then(list => { for (const j of list) { const a = API.hydrate(j); ANALYSIS.set(a.v.imo, a); BY_IMO[a.v.imo] = a.v; const k = LIVE.findIndex(x => x.v.imo === a.v.imo); if (k >= 0) LIVE[k] = a; else LIVE.push(a); } loading.hidden = true; S.loading = false; if (S.page === 'chart') { Chart.draw(); renderSheet(); } done(); })
      .catch(err => { loading.textContent = 'Server unavailable: ' + err.message; console.error(err); });
    return;
  }
  const step = () => {
    const t0 = performance.now();
    while (i < FLEET.length && performance.now() - t0 < 40) { LIVE.push(analyze(FLEET[i])); i++; }
    loading.textContent = `Loading sample fleet… ${i}/${FLEET.length}`;
    if (S.page === 'chart') { Chart.draw(); if (S.mode === 'region') renderSheet(); }
    if (i < FLEET.length) setTimeout(step, 0); else { loading.hidden = true; S.loading = false; done(); }
  };
  setTimeout(step, 0);
}
function boot() {
  const savedRules = store.get('rules', null); if (savedRules) for (const k of Object.keys(savedRules)) if (RULES[k]) Object.assign(RULES[k], savedRules[k]);
  applyAppearance();
  startBase(); Chart.init($('#map')); wireGestures($('#map')); Sheet.init(); wireUI();
  const hash = (location.hash || '').slice(1); const m = hash.match(/^imo(\d{7})$/);
  if (REGIONS[hash]) S.region = hash; syncRegions();
  Chart.fitBounds(REGIONS[S.region].bounds, false); Sheet.snap('half'); renderSheet();
  if (!store.get('auth', null)) renderLogin();
  checkPush();
  loadFleet(() => { updateBadge(); if (m && BY_IMO[+m[1]]) openVessel(+m[1]); else if (PAGES.includes(hash) && hash !== 'chart') showPage(hash); else renderSheet(); });
}
boot();
