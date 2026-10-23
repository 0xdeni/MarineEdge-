/* =====================================================================================
   Base map adapter. When MapLibre GL is loaded and OpenFreeMap tiles answer, the map owns the
   view (pan, pinch, zoom) and the canvas chart draws voyages, flags and ships on top of it.
   When MapLibre is missing (offline, blocked, or switched off in Settings) the canvas keeps
   drawing its schematic coastlines and handles gestures itself. Nothing else in the app knows which.
   Tiles: OpenFreeMap (free, no key). Attribution: © OpenFreeMap © OpenMapTiles, data from OpenStreetMap.
   ===================================================================================== */
'use strict';
const BASE_STYLES = { light: 'https://tiles.openfreemap.org/styles/positron', dark: 'https://tiles.openfreemap.org/styles/dark' };
const Base = {
  map: null, ready: false, failed: false, hooks: null,
  available() { return typeof window.maplibregl !== 'undefined'; },
  init(container, hooks, dark) {
    this.hooks = hooks;
    if (!this.available()) { this.failed = true; return false; }
    try {
      const m = new window.maplibregl.Map({
        container, style: dark ? BASE_STYLES.dark : BASE_STYLES.light, center: [35, 43.5], zoom: 5, minZoom: 2, maxZoom: 14,
        attributionControl: false, dragRotate: false, pitchWithRotate: false, touchPitch: false, maxPitch: 0, fadeDuration: 0, renderWorldCopies: false,
      });
      m.touchZoomRotate.disableRotation();
      m.keyboard.disableRotation();
      m.on('load', () => { this.ready = true; hooks.onReady && hooks.onReady(); });
      m.on('error', e => { if (!this.ready) { console.warn('Base map unavailable, using schematic coastlines', e && e.error); this.destroy(); this.failed = true; hooks.onFail && hooks.onFail(); } });
      m.on('move', () => hooks.onMove && hooks.onMove());
      m.on('moveend', () => hooks.onMoveEnd && hooks.onMoveEnd());
      m.on('click', e => hooks.onTap && hooks.onTap(e.point.x, e.point.y));
      m.on('mousemove', e => { if (hooks.onHover) m.getCanvas().style.cursor = hooks.onHover(e.point.x, e.point.y) ? 'pointer' : ''; });
      this.map = m;
      return true;
    } catch (e) { console.warn('Base map failed to start', e); this.failed = true; this.map = null; return false; }
  },
  destroy() { try { if (this.map) this.map.remove(); } catch (e) { /* already gone */ } this.map = null; this.ready = false; },
  get active() { return !!this.map; },
  project(lon, lat) { const p = this.map.project([lon, lat]); return [p.x, p.y]; },
  unproject(x, y) { const l = this.map.unproject([x, y]); return [l.lng, l.lat]; },
  bounds() { const b = this.map.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; },
  pxPerDegLon() { return 512 * Math.pow(2, this.map.getZoom()) / 360; },
  fitBounds(b, pad, animate) {
    const lonSpan = Math.max(0.05, b[2] - b[0]), latSpan = Math.max(0.05, b[3] - b[1]);
    this.map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: { top: pad.t, right: pad.r, bottom: pad.b, left: pad.l }, duration: animate ? 340 : 0, maxZoom: 13, linear: false });
    void lonSpan; void latSpan;
  },
  zoomBy(f, point) { this.map.zoomTo(this.map.getZoom() + Math.log2(f), { around: point ? this.map.unproject(point) : undefined, duration: 200 }); },
  setTheme(dark) { if (this.map) { this.ready = false; this.map.once('style.load', () => { this.ready = true; }); this.map.setStyle(dark ? BASE_STYLES.dark : BASE_STYLES.light); } },
  resize() { if (this.map) this.map.resize(); },
};
