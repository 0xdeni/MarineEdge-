/* The map: MapLibre GL with a style of our own.
   Base layers: Natural Earth (public domain, ships with the app: land, depths, rivers, borders, places) and,
   when the server holds it, the detailed OpenStreetMap basemap from Protomaps (pmtiles://, range requests).
   Overlays: live ships, sensitive zones, a ship's voyages, AIS gaps, findings and its position now. */
'use strict';

const PAL = {
  dark: {
    depth: ['#112A41', '#0D233A', '#0B1E33', '#09192C', '#081626', '#071321'],
    land: '#1B1E24', coast: '#323B47', border: '#3E4753', river: '#15304A', road: '#2A3038', urban: '#20242B',
    country: '#6B7685', city: '#9AA5B3', cityDot: '#C7CED8', sea: '#5B83AA', halo: '#0D1117',
    zone: '#FF453A', high: '#FF453A', medium: '#FF9F0A', info: '#8E8E93', accent: '#0A84FF', ship: '#C9D3DF', shipHalo: '#05080D',
    voyages: ['#64D2FF', '#5E5CE6', '#BF5AF2', '#40C8E0', '#0A84FF', '#66D4CF', '#9F8CFF', '#5AC8FA'], dim: '#8EA2B8', label: '#FFFFFF',
  },
  light: {
    depth: ['#CFE5F5', '#BEDBF1', '#B0D2EC', '#A4CAE8', '#9AC3E5', '#92BDE2'],
    land: '#F4F2EC', coast: '#B7C4D0', border: '#CFC9BE', river: '#C6DDF0', road: '#E4DED2', urban: '#ECE8E0',
    country: '#8B9099', city: '#4F555E', cityDot: '#4F555E', sea: '#4F7FAD', halo: '#FFFFFF',
    zone: '#E0281E', high: '#FF3B30', medium: '#FF9500', info: '#8E8E93', accent: '#0066CC', ship: '#3C4652', shipHalo: '#FFFFFF',
    voyages: ['#0071E3', '#5856D6', '#AF52DE', '#0098B3', '#3A5BD9', '#008E8E', '#7A5AF8', '#2E86C9'], dim: '#7F93A8', label: '#000000',
  },
};
const cubic = (x1, y1, x2, y2) => t => {          // CSS cubic-bezier as an easing function for MapLibre cameras
  let lo = 0, hi = 1, m = t;
  for (let i = 0; i < 30; i++) { m = (lo + hi) / 2; const x = 3 * (1 - m) * (1 - m) * m * x1 + 3 * (1 - m) * m * m * x2 + m * m * m; if (x < t) lo = m; else hi = m; }
  return 3 * (1 - m) * (1 - m) * m * y1 + 3 * (1 - m) * m * m * y2 + m * m * m;
};
const CAMERA = cubic(0.65, 0, 0.35, 1);
const abs = p => new URL(p, document.baseURI).href;
const PLACE_TIERS = [[0, 2, 0], [3, 4, 4.3], [5, 7, 5.8]];      // Natural Earth scalerank → first zoom a town is named

const MapView = {
  map: null, theme: 'dark', detailUrl: null, ready: null, handlers: {}, nowMarker: null, _imgs: false, _padding: { top: 0, bottom: 0, left: 0, right: 0 },

  available() { return typeof window.maplibregl !== 'undefined'; },

  init(el, { theme = 'dark', detailUrl = null, center = [36.5, 43.4], zoom = 4.6 } = {}) {
    this.theme = theme; this.detailUrl = detailUrl;
    if (!this.available()) { this.ready = Promise.reject(new Error('Map library failed to load')); return this.ready; }
    try {
      maplibregl.setWorkerUrl(abs('vendor/maplibre/maplibre-gl-csp-worker.js'));
      maplibregl.addProtocol('pmtiles', window.PMTiles.protocol);
    } catch (e) { /* already set */ }
    const m = new maplibregl.Map({
      container: el, style: this.style(theme, detailUrl), center, zoom, minZoom: 2.5, maxZoom: detailUrl ? 15 : 10, attributionControl: false,
      dragRotate: false, pitchWithRotate: false, touchPitch: false, maxPitch: 0, renderWorldCopies: false, fadeDuration: 180,
      maxBounds: [[9, 6], [75, 57]], cooperativeGestures: false,    // inside the Natural Earth extract (scripts/ne_extract.py)
    });
    m.touchZoomRotate.disableRotation();
    m.keyboard.disableRotation();
    this.map = m;
    this.ready = new Promise((res, rej) => {
      m.once('load', () => { this._images(); this._overlays(); res(m); });
      m.once('error', e => { if (!m.loaded()) rej(e && e.error || e); });
    });
    m.on('styleimagemissing', e => this._image(e.id));
    m.on('click', e => this._click(e));
    m.on('mousemove', e => { const f = this._hit(e.point); m.getCanvas().style.cursor = f ? 'pointer' : ''; });
    return this.ready;
  },

  /* ---------------------------------------------------------------- the base style */
  style(theme, detailUrl) {
    const P = PAL[theme];
    const fonts = abs('fonts/') + '{fontstack}/{range}.pbf';
    const sources = { ne: { type: 'geojson', data: abs('geo/ne.json'), attribution: 'Natural Earth', tolerance: 0.6, buffer: 64 } };
    const layers = [
      { id: 'bg', type: 'background', paint: { 'background-color': P.depth[0] } },
      { id: 'ne-depth', type: 'fill', source: 'ne', filter: ['==', ['get', 'l'], 'depth'],
        paint: { 'fill-color': ['match', ['get', 'd'], 200, P.depth[1], 1000, P.depth[2], 2000, P.depth[3], 3000, P.depth[4], 4000, P.depth[5], P.depth[1]], 'fill-antialias': false } },
      { id: 'ne-land', type: 'fill', source: 'ne', filter: ['==', ['get', 'l'], 'land'],
        paint: { 'fill-color': P.land, 'fill-opacity': detailUrl ? ['interpolate', ['linear'], ['zoom'], 6, 1, 6.6, 0] : 1 } },
    ];
    if (detailUrl) {
      sources.osm = { type: 'vector', url: 'pmtiles://' + abs(detailUrl), attribution: '© OpenStreetMap contributors · Protomaps' };
      layers.push(
        { id: 'osm-earth', type: 'fill', source: 'osm', 'source-layer': 'earth', minzoom: 5.5, filter: ['==', '$type', 'Polygon'],
          paint: { 'fill-color': P.land, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 5.5, 0, 6.2, 1] } },
        { id: 'osm-urban', type: 'fill', source: 'osm', 'source-layer': 'landuse', minzoom: 9, filter: ['in', 'kind', 'residential', 'industrial', 'commercial', 'port', 'retail'],
          paint: { 'fill-color': P.urban, 'fill-opacity': 0.8 } },
        { id: 'osm-water', type: 'fill', source: 'osm', 'source-layer': 'water', minzoom: 5.5, filter: ['all', ['==', '$type', 'Polygon'], ['!=', 'kind', 'ocean']],
          paint: { 'fill-color': P.depth[0] } },
        { id: 'osm-river', type: 'line', source: 'osm', 'source-layer': 'water', minzoom: 9, filter: ['in', 'kind', 'river', 'canal'],
          paint: { 'line-color': P.depth[0], 'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 9, 0.6, 14, 4] } },
        { id: 'osm-road-major', type: 'line', source: 'osm', 'source-layer': 'roads', minzoom: 8, filter: ['in', 'kind', 'highway', 'major_road'],
          layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': P.road, 'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 8, 0.4, 14, 3] } },
        { id: 'osm-road-minor', type: 'line', source: 'osm', 'source-layer': 'roads', minzoom: 12, filter: ['in', 'kind', 'minor_road'],
          layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': P.road, 'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 12, 0.4, 15, 2] } },
        { id: 'osm-boundary', type: 'line', source: 'osm', 'source-layer': 'boundaries', minzoom: 6, filter: ['<=', 'kind_detail', 2],
          paint: { 'line-color': P.border, 'line-width': 0.8, 'line-dasharray': [3, 2] } },
      );
    }
    layers.push(
      { id: 'ne-lake', type: 'fill', source: 'ne', filter: ['==', ['get', 'l'], 'lake'], maxzoom: detailUrl ? 6.6 : 24, paint: { 'fill-color': P.depth[0] } },
      { id: 'ne-coast', type: 'line', source: 'ne', filter: ['==', ['get', 'l'], 'land'], maxzoom: detailUrl ? 6.6 : 24,
        paint: { 'line-color': P.coast, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.4, 8, 1] } },
      { id: 'ne-river', type: 'line', source: 'ne', filter: ['==', ['get', 'l'], 'river'], maxzoom: detailUrl ? 9 : 24,
        layout: { 'line-cap': 'round' }, paint: { 'line-color': P.river, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.5, 8, 1.4] } },
      { id: 'ne-border', type: 'line', source: 'ne', filter: ['==', ['get', 'l'], 'border'], maxzoom: detailUrl ? 6.2 : 24,
        paint: { 'line-color': P.border, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.5, 8, 1], 'line-dasharray': [3, 2] } },
      { id: 'ne-sea', type: 'symbol', source: 'ne', filter: ['==', ['get', 'l'], 'sea'], maxzoom: 9,
        layout: { 'text-field': ['get', 'n'], 'text-font': ['Noto Sans Italic'], 'text-size': ['interpolate', ['linear'], ['zoom'], 3, 10, 7, 14], 'text-letter-spacing': 0.18, 'text-max-width': 8 },
        paint: { 'text-color': P.sea, 'text-halo-color': P.depth[0], 'text-halo-width': 0.6, 'text-opacity': 0.85 } },
      { id: 'ne-country', type: 'symbol', source: 'ne', filter: ['==', ['get', 'l'], 'country'], minzoom: 3.5, maxzoom: 7,
        layout: { 'text-field': ['upcase', ['get', 'n']], 'text-font': ['Noto Sans Medium'], 'text-size': ['interpolate', ['linear'], ['zoom'], 3.5, 9, 7, 12], 'text-letter-spacing': 0.22, 'text-max-width': 7 },
        paint: { 'text-color': P.country, 'text-halo-color': P.halo, 'text-halo-width': 0.5, 'text-opacity': 0.85 } },
      ...PLACE_TIERS.map(([lo, hi, minz], i) => ({ id: `ne-place-${i}`, type: 'symbol', source: 'ne', minzoom: minz, maxzoom: detailUrl ? 7 : 24,
        filter: ['all', ['==', ['get', 'l'], 'place'], ['>=', ['get', 'r'], lo], ['<=', ['get', 'r'], hi]],
        layout: { 'text-field': ['get', 'n'], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 3, 10.5, 8, 13], 'text-anchor': 'left', 'text-offset': [0.6, 0],
          'text-max-width': 9, 'symbol-sort-key': ['get', 'r'], 'text-padding': 4, 'icon-image': 'place-dot', 'icon-size': 1, 'text-optional': false },
        paint: { 'text-color': P.city, 'text-halo-color': P.halo, 'text-halo-width': 1.1, 'text-halo-blur': 0.4, 'icon-color': P.cityDot, 'icon-opacity': 0.9 } })),
    );
    if (detailUrl) {
      layers.push({ id: 'osm-place', type: 'symbol', source: 'osm', 'source-layer': 'places', minzoom: 7, filter: ['in', 'kind', 'locality'],
        layout: { 'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 7, 11, 13, 15],
          'text-max-width': 9, 'symbol-sort-key': ['coalesce', ['get', 'sort_key'], ['get', 'min_zoom']], 'text-padding': 6 },
        paint: { 'text-color': P.city, 'text-halo-color': P.halo, 'text-halo-width': 1.2 } });
    }
    return { version: 8, glyphs: fonts, sources, layers };
  },

  /* paint values that change with the theme, for every layer we own */
  themed() {
    const P = PAL[this.theme];
    return [
      ['bg', 'background-color', P.depth[0]],
      ['ne-depth', 'fill-color', ['match', ['get', 'd'], 200, P.depth[1], 1000, P.depth[2], 2000, P.depth[3], 3000, P.depth[4], 4000, P.depth[5], P.depth[1]]],
      ['ne-land', 'fill-color', P.land], ['osm-earth', 'fill-color', P.land], ['osm-urban', 'fill-color', P.urban], ['osm-water', 'fill-color', P.depth[0]], ['osm-river', 'line-color', P.depth[0]],
      ['osm-road-major', 'line-color', P.road], ['osm-road-minor', 'line-color', P.road], ['osm-boundary', 'line-color', P.border],
      ['ne-lake', 'fill-color', P.depth[0]], ['ne-coast', 'line-color', P.coast], ['ne-river', 'line-color', P.river], ['ne-border', 'line-color', P.border],
      ['ne-sea', 'text-color', P.sea], ['ne-sea', 'text-halo-color', P.depth[0]], ['ne-country', 'text-color', P.country], ['ne-country', 'text-halo-color', P.halo],
      ...PLACE_TIERS.flatMap((_, i) => [[`ne-place-${i}`, 'text-color', P.city], [`ne-place-${i}`, 'text-halo-color', P.halo], [`ne-place-${i}`, 'icon-color', P.cityDot]]),
      ['osm-place', 'text-color', P.city], ['osm-place', 'text-halo-color', P.halo],
      ['zone-line', 'line-color', P.zone], ['live-ship', 'icon-halo-color', P.shipHalo], ['live-label', 'text-color', P.label], ['live-label', 'text-halo-color', P.halo],
      ['live-ship', 'icon-color', ['match', ['get', 'level'], 'high', P.high, 'review', P.medium, P.ship]],
      ['voy-line', 'line-color', this._voyColor()], ['voy-current', 'line-color', this._voyColor()], ['gap-line', 'line-color', P.high], ['gap-info', 'line-color', P.info],
      ['flag-dot', 'circle-color', ['match', ['get', 'severity'], 'high', P.high, 'medium', P.medium, P.info]], ['flag-cluster', 'circle-color', P.high],
      ['call-dot', 'circle-color', this.theme === 'dark' ? '#0B1A2A' : '#FFFFFF'], ['call-label', 'text-color', P.city], ['call-label', 'text-halo-color', P.halo],
      ['sel-halo', 'line-color', this.theme === 'dark' ? '#000000' : '#FFFFFF'],
    ];
  },
  _voyColor() {
    const P = PAL[this.theme];
    return ['case', ['==', ['get', 'dim'], true], P.dim, ['match', ['get', 'c'], 0, P.voyages[0], 1, P.voyages[1], 2, P.voyages[2], 3, P.voyages[3], 4, P.voyages[4], 5, P.voyages[5], 6, P.voyages[6], P.voyages[7]]];
  },
  setTheme(theme) {
    if (!this.map || theme === this.theme) { this.theme = theme; return; }
    this.theme = theme;
    const m = this.map;
    for (const [id, prop, val] of this.themed()) { if (m.getLayer(id)) { try { m.setPaintProperty(id, prop, val); } catch (e) { /* layer type mismatch */ } } }
    this._hatch(true);
  },
  setDetail(url) {
    if (!this.map || url === this.detailUrl) return;
    this.detailUrl = url;
    const keep = this.map.getStyle();
    const next = this.style(this.theme, url);
    // carry our overlays across the style change
    next.sources = { ...next.sources, ...Object.fromEntries(Object.entries(keep.sources).filter(([k]) => !['ne', 'osm'].includes(k))) };
    next.layers = [...next.layers, ...keep.layers.filter(l => l.source && !['ne', 'osm'].includes(l.source))];
    this.map.setMaxZoom(url ? 15 : 10);
    this.map.setStyle(next, { diff: false });
    this.map.once('style.load', () => { this._imgs = false; this._images(); });
  },

  /* ---------------------------------------------------------------- images: ship arrow, dot, zone hatch */
  _images() {
    if (this._imgs) return; this._imgs = true;
    for (const id of ['ship-arrow', 'ship-dot', 'place-dot']) this._image(id);
    this._hatch();
  },
  _image(id, m = this.map) {
    if (!m || m.hasImage(id)) return;
    const mk = (w, h, draw) => { const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); draw(g); return g.getImageData(0, 0, w, h); };
    if (id === 'ship-arrow') m.addImage(id, mk(40, 40, g => { g.fillStyle = '#fff'; g.beginPath(); g.moveTo(20, 4); g.lineTo(31, 34); g.lineTo(20, 28); g.lineTo(9, 34); g.closePath(); g.fill(); }), { sdf: true, pixelRatio: 2 });
    else if (id === 'ship-dot') m.addImage(id, mk(40, 40, g => { g.fillStyle = '#fff'; g.beginPath(); g.arc(20, 20, 9, 0, Math.PI * 2); g.fill(); }), { sdf: true, pixelRatio: 2 });
    else if (id === 'place-dot') m.addImage(id, mk(12, 12, g => { g.fillStyle = '#fff'; g.beginPath(); g.arc(6, 6, 3.2, 0, Math.PI * 2); g.fill(); }), { sdf: true, pixelRatio: 2 });
    else if (id === 'hatch') this._hatch();
  },
  _hatch(replace) {
    const m = this.map; const P = PAL[this.theme];
    const c = document.createElement('canvas'); c.width = 24; c.height = 24; const g = c.getContext('2d');
    g.strokeStyle = P.zone; g.globalAlpha = this.theme === 'dark' ? 0.45 : 0.4; g.lineWidth = 2;
    for (let i = -24; i < 48; i += 8) { g.beginPath(); g.moveTo(i, 24); g.lineTo(i + 24, 0); g.stroke(); }
    const img = g.getImageData(0, 0, 24, 24);
    if (m.hasImage('hatch')) { if (replace) m.updateImage('hatch', img); } else m.addImage('hatch', img, { pixelRatio: 2 });
  },

  /* ---------------------------------------------------------------- overlays */
  _overlays() {
    const m = this.map; const P = PAL[this.theme];
    const empty = { type: 'FeatureCollection', features: [] };
    const add = (id, src) => { if (!m.getSource(id)) m.addSource(id, src); };
    add('zones', { type: 'geojson', data: empty });
    add('live', { type: 'geojson', data: empty });
    add('voy', { type: 'geojson', data: empty, lineMetrics: false });
    add('gaps', { type: 'geojson', data: empty });
    add('calls', { type: 'geojson', data: empty });
    add('flags', { type: 'geojson', data: empty, cluster: true, clusterRadius: 26, clusterMaxZoom: 9 });
    const L = (spec) => { if (!m.getLayer(spec.id)) m.addLayer(spec); };
    L({ id: 'zone-fill', type: 'fill', source: 'zones', filter: ['==', ['get', 'enabled'], true], paint: { 'fill-pattern': 'hatch', 'fill-opacity': 0.9 } });
    L({ id: 'zone-line', type: 'line', source: 'zones', filter: ['==', ['get', 'enabled'], true], paint: { 'line-color': P.zone, 'line-opacity': 0.55, 'line-width': 1.2, 'line-dasharray': [4, 3] } });
    L({ id: 'live-ship', type: 'symbol', source: 'live',
      layout: { 'icon-image': ['case', ['>=', ['get', 'sog'], 0.8], 'ship-arrow', 'ship-dot'], 'icon-rotate': ['case', ['>=', ['get', 'sog'], 0.8], ['get', 'cog'], 0],
        'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true,
        'icon-size': ['interpolate', ['linear'], ['zoom'], 3, ['case', ['==', ['get', 'level'], 'high'], 0.62, 0.38], 8, ['case', ['==', ['get', 'level'], 'high'], 0.95, 0.66]],
        'symbol-sort-key': ['match', ['get', 'level'], 'high', 3, 'review', 2, 1] },
      paint: { 'icon-color': ['match', ['get', 'level'], 'high', P.high, 'review', P.medium, P.ship], 'icon-halo-color': P.shipHalo, 'icon-halo-width': 1.1,
        'icon-opacity': ['interpolate', ['linear'], ['zoom'], 3, ['case', ['==', ['get', 'level'], 'high'], 1, 0.6], 8, ['case', ['==', ['get', 'level'], 'high'], 1, 0.85]] } });
    L({ id: 'live-label', type: 'symbol', source: 'live', minzoom: 5.2, filter: ['==', ['get', 'level'], 'high'],
      layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-offset': [0, 1.15], 'text-anchor': 'top', 'text-max-width': 10, 'text-optional': true },
      paint: { 'text-color': P.label, 'text-halo-color': P.halo, 'text-halo-width': 1.4 } });
    L({ id: 'sel-halo', type: 'line', source: 'voy', filter: ['==', ['get', 'sel'], true], layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': this.theme === 'dark' ? '#000000' : '#FFFFFF', 'line-width': 7, 'line-opacity': 0.55 } });
    L({ id: 'voy-line', type: 'line', source: 'voy', filter: ['!=', ['get', 'current'], true], layout: { 'line-cap': 'round', 'line-join': 'round', 'line-sort-key': ['case', ['==', ['get', 'sel'], true], 2, 1] },
      paint: { 'line-color': this._voyColor(), 'line-width': ['case', ['==', ['get', 'sel'], true], 3.4, ['==', ['get', 'dim'], true], 1.1, 2],
        'line-opacity': ['case', ['==', ['get', 'dim'], true], 0.32, 0.95] } });
    L({ id: 'voy-current', type: 'line', source: 'voy', filter: ['==', ['get', 'current'], true], layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': this._voyColor(), 'line-width': ['case', ['==', ['get', 'sel'], true], 3.4, 2.2], 'line-dasharray': [1.6, 1.4], 'line-opacity': ['case', ['==', ['get', 'dim'], true], 0.35, 1] } });
    L({ id: 'gap-line', type: 'line', source: 'gaps', filter: ['!=', ['get', 'severity'], 'info'], layout: { 'line-cap': 'round' },
      paint: { 'line-color': P.high, 'line-width': 2.6, 'line-dasharray': [0.1, 2.2], 'line-opacity': ['case', ['==', ['get', 'dim'], true], 0.35, 1] } });
    L({ id: 'gap-info', type: 'line', source: 'gaps', filter: ['==', ['get', 'severity'], 'info'], layout: { 'line-cap': 'round' },
      paint: { 'line-color': P.info, 'line-width': 2, 'line-dasharray': [0.1, 2.4], 'line-opacity': 0.7 } });
    L({ id: 'call-dot', type: 'circle', source: 'calls', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 2.6, 10, 4.5], 'circle-color': this.theme === 'dark' ? '#0B1A2A' : '#FFFFFF',
      'circle-stroke-color': ['case', ['==', ['get', 'zone'], true], P.zone, P.city], 'circle-stroke-width': 1.5 } });
    L({ id: 'call-label', type: 'symbol', source: 'calls', minzoom: 5.5,
      layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-anchor': 'left', 'text-offset': [0.7, 0], 'text-optional': true, 'text-max-width': 9 },
      paint: { 'text-color': P.city, 'text-halo-color': P.halo, 'text-halo-width': 1.3 } });
    L({ id: 'flag-cluster', type: 'circle', source: 'flags', filter: ['has', 'point_count'],
      paint: { 'circle-radius': 10, 'circle-color': P.high, 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 1.6 } });
    L({ id: 'flag-count', type: 'symbol', source: 'flags', filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-allow-overlap': true }, paint: { 'text-color': '#FFFFFF' } });
    L({ id: 'flag-dot', type: 'circle', source: 'flags', filter: ['!', ['has', 'point_count']],
      paint: { 'circle-radius': ['case', ['==', ['get', 'sel'], true], 8.5, 6], 'circle-color': ['match', ['get', 'severity'], 'high', P.high, 'medium', P.medium, P.info],
        'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': ['case', ['==', ['get', 'sel'], true], 2.5, 1.6],
        'circle-opacity': ['case', ['==', ['get', 'dim'], true], 0.3, 1], 'circle-stroke-opacity': ['case', ['==', ['get', 'dim'], true], 0.3, 1] } });
  },

  _hit(point) {
    const m = this.map; if (!m) return null;
    const layers = ['flag-dot', 'flag-cluster', 'live-ship', 'voy-line', 'voy-current'].filter(id => m.getLayer(id) && m.getLayoutProperty(id, 'visibility') !== 'none');
    const box = [[point.x - 12, point.y - 12], [point.x + 12, point.y + 12]];
    const fs = m.queryRenderedFeatures(box, { layers });
    return fs[0] || null;
  },
  _click(e) {
    const f = this._hit(e.point); if (!f) return;
    const id = f.layer.id;
    if (id === 'flag-cluster') {
      this.map.getSource('flags').getClusterExpansionZoom(f.properties.cluster_id).then(z => this.map.easeTo({ center: f.geometry.coordinates, zoom: z + 0.3, duration: reduceMotion() ? 0 : 500 }));
      return;
    }
    if (id === 'flag-dot' && this.handlers.flag) this.handlers.flag(f.properties.key);
    else if (id === 'live-ship' && this.handlers.ship) this.handlers.ship(f.properties.imo, f.properties.name);
    else if ((id === 'voy-line' || id === 'voy-current') && this.handlers.voyage) this.handlers.voyage(f.properties.n);
  },
  on(name, fn) { this.handlers[name] = fn; },

  vis(ids, on) { if (!this.map) return; for (const id of ids) if (this.map.getLayer(id)) this.map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'); },
  data(src, fc) { const s = this.map && this.map.getSource(src); if (s) s.setData(fc); },

  setZones(fc) { this.data('zones', fc); },
  setLive(rows) {
    this.data('live', { type: 'FeatureCollection', features: (rows || []).filter(r => r.lat != null).map(r => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [r.lon, r.lat] },
      properties: { imo: r.imo, name: r.name, level: r.level || 'none', sog: r.sog || 0, cog: r.cog || 0 } })) });
  },
  showLive(on) { this.vis(['live-ship', 'live-label'], on); },

  /* a ship's year: voyages, gaps, port calls, findings, and its position now */
  setShip(a, { sel = null, flagKey = null } = {}) {
    const track = a.track || [];
    const feats = [];
    for (const v of a.voyages || []) {
      const pts = track.slice(v.i0, v.i1 + 1).filter(p => !p.jump).map(p => [p.lon, p.lat]);
      if (pts.length < 2) continue;
      feats.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: pts }, properties: { n: v.n, c: v.color, current: !!v.current, sel: sel === v.n, dim: sel != null && sel !== v.n } });
    }
    this.data('voy', { type: 'FeatureCollection', features: feats });
    const gaps = [];
    for (const f of a.flags || []) {
      if (f.rule !== 'AIS gap') continue;
      const b = f.evidence && f.evidence.before && f.evidence.before[f.evidence.before.length - 1];
      const c = f.evidence && f.evidence.after && f.evidence.after[0];
      if (!b || !c) continue;
      gaps.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[b.lon, b.lat], [c.lon, c.lat]] }, properties: { severity: f.severity, dim: sel != null && f.voyage !== sel } });
    }
    this.data('gaps', { type: 'FeatureCollection', features: gaps });
    const seen = new Set(); const calls = [];
    for (const pc of a.portCalls || []) {
      const k = pc.port.id || pc.port.name; if (seen.has(k)) continue; seen.add(k);
      calls.push({ type: 'Feature', geometry: { type: 'Point', coordinates: pc.port.b || [pc.lon, pc.lat] }, properties: { name: pc.port.name, zone: !!pc.port.zone } });
    }
    this.data('calls', { type: 'FeatureCollection', features: calls });
    this.data('flags', { type: 'FeatureCollection', features: (a.flags || []).filter(f => !f.vesselLevel && f.lat != null && f.severity !== 'info')
      .map(f => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [f.lon, f.lat] }, properties: { key: f.key, severity: f.severity, sel: f.key === flagKey, dim: sel != null && f.voyage !== sel } })) });
    this.vis(['voy-line', 'voy-current', 'sel-halo', 'gap-line', 'gap-info', 'call-dot', 'call-label', 'flag-cluster', 'flag-count', 'flag-dot'], true);
    const last = a.last || track[track.length - 1];
    if (last) this.setNow([last.lon, last.lat]); else this.setNow(null);
  },
  clearShip() {
    const empty = { type: 'FeatureCollection', features: [] };
    for (const s of ['voy', 'gaps', 'calls', 'flags']) this.data(s, empty);
    this.setNow(null);
  },
  setNow(ll) {
    if (!this.map) return;
    if (!ll) { if (this.nowMarker) { this.nowMarker.remove(); this.nowMarker = null; } return; }
    if (!this.nowMarker) { const el = document.createElement('div'); el.className = 'now-mk'; this.nowMarker = new maplibregl.Marker({ element: el }).setLngLat(ll).addTo(this.map); }
    else this.nowMarker.setLngLat(ll);
  },

  /* ---------------------------------------------------------------- camera */
  setPadding(p) { this._padding = { ...this._padding, ...p }; if (this.map) this.map.setPadding(this._padding); },
  fit(bounds, { duration = 820, maxZoom = 9.5, padding = null } = {}) {
    if (!this.map || !bounds) return;
    const [w, s, e, n] = bounds;
    const pad = padding || { top: 70, bottom: 30, left: 30, right: 30 };
    try {
      this.map.fitBounds([[w, s], [Math.max(e, w + 0.02), Math.max(n, s + 0.02)]], { padding: pad, maxZoom, duration: reduceMotion() ? 0 : duration, easing: CAMERA, essential: true });
    } catch (err) { /* bounds outside maxBounds */ }
  },
  flyTo(center, zoom, duration = 820) { if (this.map) this.map.flyTo({ center, zoom, duration: reduceMotion() ? 0 : duration, curve: 1.3, easing: CAMERA, essential: true }); },
  resize() { if (this.map) this.map.resize(); },
};

function boundsOf(points) {
  let w = 180, s = 90, e = -180, n = -90;
  for (const p of points) { const lon = p.lon != null ? p.lon : p[0], lat = p.lat != null ? p.lat : p[1]; if (lon < w) w = lon; if (lon > e) e = lon; if (lat < s) s = lat; if (lat > n) n = lat; }
  return w <= e ? [w, s, e, n] : null;
}

/* A small, still map for a finding's evidence (one extra WebGL context while the finding is open). */
function miniMap(el, { theme, detailUrl, bounds, track = [], points = [], zones = null }) {
  if (typeof maplibregl === 'undefined') return null;
  const style = MapView.style(theme, detailUrl);
  const P = PAL[theme];
  style.sources.trk = { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: track.map(p => [p.lon, p.lat]) }, properties: {} } };
  style.sources.pts = { type: 'geojson', data: { type: 'FeatureCollection', features: points.map(p => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [p.lon, p.lat] }, properties: { k: p.k || 'pos' } })) } };
  if (zones) style.sources.zn = { type: 'geojson', data: zones };
  if (zones) style.layers.push({ id: 'zn', type: 'line', source: 'zn', filter: ['==', ['get', 'enabled'], true], paint: { 'line-color': P.zone, 'line-opacity': 0.6, 'line-width': 1.2, 'line-dasharray': [4, 3] } });
  style.layers.push({ id: 'trk', type: 'line', source: 'trk', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': P.voyages[0], 'line-width': 2 } });
  style.layers.push({ id: 'pts', type: 'circle', source: 'pts', paint: { 'circle-radius': ['match', ['get', 'k'], 'mark', 7, 4], 'circle-color': ['match', ['get', 'k'], 'mark', P.high, P.voyages[0]], 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': ['match', ['get', 'k'], 'mark', 2, 1] } });
  const m = new maplibregl.Map({ container: el, style, interactive: false, attributionControl: false, fadeDuration: 0, bounds: [[bounds[0], bounds[1]], [bounds[2], bounds[3]]],
    fitBoundsOptions: { padding: 28, maxZoom: 9 }, maxZoom: detailUrl ? 14 : 10 });
  m.on('styleimagemissing', e => MapView._image(e.id, m));
  return m;
}
