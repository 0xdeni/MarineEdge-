/* App state, routing and the transitions between the main views.
   Routes (hash): #/  #/search  #/ship/:imo  #/ship/:imo/voyage/:n  #/ship/:imo/finding/:key  #/alerts  #/list/high
                  #/profile[/...]  #/welcome  #/intro  #/signin  #/signup  #/forgot  #/invite/:code  #/reset/:token */
'use strict';

const S = {
  me: null, authState: null, region: 'blacksea', regions: [], themePref: 'system', theme: 'dark',
  overview: null, live: [], watching: [], zones: null, maps: null,
  analyses: new Map(), notes: new Map(), route: { name: 'boot' }, view: null, depth: 0, pollT: 0, lastRoute: null,
};

const store = {
  get(k, d) { try { const v = localStorage.getItem('me.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('me.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  del(k) { try { localStorage.removeItem('me.' + k); } catch (e) { /* ignore */ } },
};

const App = {
  /* ---------------------------------------------------------------- boot */
  async boot() {
    this.applyTheme(store.get('theme', 'system'), false);
    matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (S.themePref === 'system') this.applyTheme('system', false); });
    API.onSignedOut = () => this.signedOut();
    window.addEventListener('hashchange', () => this.route());
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') return;
      if (S.updateReady && !(typeof Screens !== 'undefined' && Screens.compState)) { location.reload(); return; }
      this.tick(true);
    });
    if ('serviceWorker' in navigator) {
      const hadController = !!navigator.serviceWorker.controller;
      navigator.serviceWorker.register('./sw.js').catch(() => {});
      navigator.serviceWorker.addEventListener('message', e => { const go = e.data && e.data.go; if (typeof go === 'string' && go.startsWith('#/')) this.go(go); });
      // a new version took over: reload when the person next comes back to the app, never mid-task
      navigator.serviceWorker.addEventListener('controllerchange', () => { if (hadController) S.updateReady = true; });
    }

    let me = null;
    try { me = await API.me(); } catch (e) { me = null; if (e.code === 'network' || e.code === 'offline') { this.bootDone(); Onboarding.offline(); return; } }
    if (me) { await this.signedIn(me, { fromBoot: true }); }
    else {
      try { S.authState = await API.authState(); } catch (e) { S.authState = { setup: false, email: false }; }
      this.bootDone();
      this.route();
    }
  },
  bootDone() { const b = $('#boot'); if (b) { b.classList.add('out'); setTimeout(() => b.remove(), 400); } },

  async signedIn(me, { fromBoot = false, fresh = false } = {}) {
    S.me = me;
    const prefs = (me.user && me.user.prefs) || {};
    if (prefs.theme) this.applyTheme(prefs.theme, false);
    Fmt.utc = !prefs.timeLocal;
    S.region = store.get('region', prefs.region || 'blacksea');
    this.renderMeButton();
    await this.ensureMap();
    Screens.initOnce();
    this.bootDone();
    const h = location.hash;
    if (!h || /^#\/?(welcome|intro|signin|signup|forgot|invite|reset)/.test(h)) {
      history.replaceState(null, '', '#/');
    }
    Onboarding.close(fresh);
    this.route();
    this.loadStatic();
    this.tick(true);
    clearInterval(S.pollT);
    S.pollT = setInterval(() => this.tick(false), 60000);
  },

  async signedOut() {
    if (!S.me) return;
    S.me = null; S.analyses.clear(); S.notes.clear(); S.overview = null; S.live = []; S.watching = [];
    clearInterval(S.pollT);
    try { const ks = await caches.keys(); await Promise.all(ks.filter(k => k.includes('-api')).map(k => caches.delete(k))); } catch (e) { /* no caches */ }
    store.del('recent');
    Pages.clear();
    Screens.reset();
    try { S.authState = await API.authState(); } catch (e) { /* keep */ }
    location.hash = '#/signin';
  },

  async ensureMap() {
    if (MapView.map) return;
    let detail = null;
    try { S.maps = await API.maps(); detail = S.maps && S.maps.installed ? S.maps.url : null; } catch (e) { detail = null; }
    const reg = REGION_VIEW[S.region] || REGION_VIEW.blacksea;
    try {
      MapView.init($('#map'), { theme: S.theme, detailUrl: detail, center: reg.center, zoom: reg.zoom });
      await MapView.ready;
    } catch (e) {
      console.warn('map failed', e);
      toast("The map couldn't start on this device. Lists still work.", 'err');
    }
    this.renderAttribution();
  },
  renderAttribution() {
    const a = $('#attr');
    a.innerHTML = `© <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener">Natural Earth</a>${S.maps && S.maps.installed ? ' · © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> · Protomaps' : ''}`;
  },

  async loadStatic() {
    try { S.zones = await API.zones(); MapView.setZones(S.zones); } catch (e) { /* map works without zones */ }
    try { S.regions = await API.regions(); } catch (e) { S.regions = []; }
  },

  /* periodic refresh of what is on screen (Home every minute; alerts badge always) */
  async tick(force) {
    if (!S.me || document.visibilityState === 'hidden') return;
    if (force || S.view === 'home' || S.view === 'search') Screens.refreshHome(force);
    try { const me = await API.me(); S.me = me; this.renderBadge(); } catch (e) { /* offline: keep */ }
  },

  /* ---------------------------------------------------------------- appearance */
  applyTheme(pref, save = true) {
    S.themePref = pref;
    const t = pref === 'system' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : pref;
    S.theme = t;
    document.documentElement.dataset.theme = t;
    const m = document.querySelector('meta[name=theme-color]'); if (m) m.content = t === 'light' ? '#F2F2F7' : '#000000';
    store.set('theme', pref);
    const changed = MapView.theme !== t;
    MapView.setTheme(t);
    if (changed && typeof Screens !== 'undefined' && Screens.inited) Screens.onTheme();
    if (save && S.me) API.updateMe({ prefs: { theme: pref } }).catch(() => {});
  },

  renderMeButton() {
    const u = S.me && S.me.user; if (!u) return;
    $('#meBtn').innerHTML = `<span style="width:30px;height:30px;border-radius:15px;background:${esc(u.color)};color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;letter-spacing:0.02em">${esc(u.initials)}</span>`;
    $('#alertsBtn .bell').innerHTML = ICON.bell(19);
    this.renderBadge();
  },
  renderBadge() {
    const n = (S.me && S.me.unread) || 0; const b = $('#alertsBadge');
    b.hidden = !n; b.textContent = n > 9 ? '9+' : String(n);
    $('#alertsBtn').setAttribute('aria-label', n ? `Alerts, ${n} new` : 'Alerts');
  },

  /* ---------------------------------------------------------------- routing */
  parse(h = location.hash) {
    const p = h.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
    if (!p.length) return { name: 'home' };
    const [a, b, c, d] = p;
    if (a === 'search') return { name: 'search' };
    if (a === 'ship' && /^\d{7}$/.test(b || '')) {
      if (c === 'voyage' && d) return { name: 'voyage', imo: +b, n: +d };
      if (c === 'finding' && d) return { name: 'finding', imo: +b, key: d };
      return { name: 'ship', imo: +b };
    }
    if (a === 'alerts') return { name: 'alerts' };
    if (a === 'list') return { name: 'list', kind: b || 'high' };
    if (a === 'profile') return { name: 'profile', sub: p.slice(1) };
    if (['welcome', 'intro', 'signin', 'signup', 'forgot'].includes(a)) return { name: a };
    if (a === 'invite' && b) return { name: 'invite', code: b };
    if (a === 'reset' && b) return { name: 'reset', token: b };
    return { name: 'home' };
  },
  go(hash, { replace = false } = {}) {
    if (location.hash === hash) { this.route(); return; }
    if (replace) { history.replaceState(null, '', hash); this.route(); }
    else { S.depth++; location.hash = hash; }
  },
  back(fallback) {
    if (S.depth > 0) { S.depth--; history.back(); return; }
    const r = S.route;
    const parent = fallback || (r.name === 'voyage' || r.name === 'finding' ? `#/ship/${r.imo}` : r.name === 'profile' && r.sub && r.sub.length ? '#/profile' + (r.sub.length > 1 ? '/' + r.sub.slice(0, -1).join('/') : '') : '#/');
    history.replaceState(null, '', parent);
    this.route();
  },

  route() {
    const r = this.parse();
    const prev = S.route; S.route = r;
    const authRoutes = ['welcome', 'intro', 'signin', 'signup', 'forgot', 'invite', 'reset'];
    if (!S.me) {
      if (!authRoutes.includes(r.name)) { history.replaceState(null, '', store.get('seenWelcome', false) ? '#/signin' : '#/welcome'); return this.route(); }
      Onboarding.show(r, prev);
      return;
    }
    if (authRoutes.includes(r.name) && r.name !== 'invite' && r.name !== 'reset') { history.replaceState(null, '', '#/'); return this.route(); }
    if (r.name === 'invite' || r.name === 'reset') { Onboarding.show(r, prev); return; }
    // profile pages sit on top of whatever map view is underneath
    if (r.name === 'profile') { Profile.sync(r.sub || []); if (!S.view) Screens.showHome(false); return; }
    if (Pages.stack.length) Profile.sync(null);
    Screens.apply(r, prev);
  },
};

const REGION_VIEW = {     // the server's regions (service.REGIONS), so the first frame needs no request
  blacksea: { center: [34.6, 43.4], zoom: 4.2, bbox: [27.2, 40.6, 42.0, 47.4] },
  hormuz: { center: [56.5, 26.4], zoom: 7.0, bbox: [55.3, 25.3, 57.7, 27.5] },
  iran: { center: [54.9, 27.7], zoom: 5.0, bbox: [48.0, 24.4, 61.8, 31.0] },
  oman: { center: [57.7, 21.5], zoom: 4.8, bbox: [52.8, 16.0, 62.6, 26.9] },
  uae: { center: [54.3, 25.1], zoom: 6.0, bbox: [51.3, 23.6, 57.3, 26.6] },
};

window.addEventListener('DOMContentLoaded', () => App.boot());
