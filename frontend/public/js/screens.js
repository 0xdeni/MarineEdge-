/* The map screens: Home (search and the region overview), a ship and its year, its voyages and findings,
   team notes, alerts. Everything on screen comes from the server; nothing here is invented. */
'use strict';

const REGION_NAME = { blacksea: 'Black Sea', hormuz: 'Strait of Hormuz', iran: 'Iran coast', oman: 'Gulf of Oman', uae: 'UAE' };
const TYPE_LABEL = { tanker: 'Tanker', bulk: 'Bulk carrier', container: 'Container ship', gas: 'Gas carrier', other: 'Ship' };
const SEV_LABEL = { high: 'High', medium: 'Medium', info: 'Info' };
const NUM_WORD = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];
const wide = () => window.innerWidth >= 820;
const DAY = 864e5;

function typeOf(v) { return (v && (v.sub || TYPE_LABEL[v.type])) || 'Ship'; }
function titleCase(s) { return String(s || '').toLowerCase().replace(/(^|[\s\-/(])([a-zà-ž])/g, (m, a, b) => a + b.toUpperCase()); }
function dh(ms) {
  if (ms == null || ms < 0) return '—';
  const h = Math.round(ms / 3600e3);
  if (h < 1) return `${Math.max(1, Math.round(ms / 60e3))} min`;
  if (h < 24) return `${h} h`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}
function nmBetween(lat1, lon1, lat2, lon2) {
  const k = Math.cos(((lat1 + lat2) / 2) * Math.PI / 180);
  return 60 * Math.hypot(lat2 - lat1, (lon2 - lon1) * k);
}
function nearestPort(lat, lon, maxNm = 30) {
  let best = null, bd = maxNm;
  for (const p of S.ports || []) { const d = nmBetween(lat, lon, p.lat, p.lon); if (d < bd) { bd = d; best = p; } }
  return best ? { port: best, nm: bd } : null;
}
function navText(r) {
  if (!r || r.lat == null) return '';
  const near = nearestPort(r.lat, r.lon);
  if (r.nav === 5 || (r.sog < 0.5 && near && near.nm < 3)) return `moored${near ? ' at ' + near.port.name : ''}`;
  if (r.nav === 1 || r.sog < 0.5) return `${r.nav === 1 ? 'at anchor' : 'stopped'}${near ? ' off ' + near.port.name : ''}`;
  return `under way at ${Number(r.sog).toFixed(1)} kn${r.destination ? ', bound for ' + titleCase(r.destination) : near ? ' near ' + near.port.name : ''}`;
}
function hl(text, q) {
  const t = String(text || ''); const i = q ? t.toUpperCase().indexOf(q.toUpperCase()) : -1;
  if (i < 0 || !q) return esc(t);
  return `${esc(t.slice(0, i))}<span class="mark">${esc(t.slice(i, i + q.length))}</span>${esc(t.slice(i + q.length))}`;
}
function ruleText(rule) {
  const R = S.rules || {};
  const g = (grp, k, d) => (R[grp] && R[grp][k] != null ? R[grp][k] : d);
  switch (rule) {
    case 'Sanctions hit': return `Flagged when the ship's IMO number is on the ${(g('sanctions', 'lists', ['OFAC SDN', 'EU', 'UK'])).join(', ')} lists. The server downloads them every day.`;
    case 'Call at a sensitive port': return `Flagged when the ship stays ${g('port_call', 'min_hours', 6)} hours or more, slower than ${g('port_call', 'max_speed_kn', 0.5)} kn, at a port or anchorage inside a sensitive zone.`;
    case 'AIS gap': return `Flagged when no position arrives for more than ${g('ais_gap', 'min_hours', 6)} hours at sea. High when it lasts over ${g('ais_gap', 'high_hours', 24)} hours or starts within ${g('ais_gap', 'near_sensitive_nm', 100)} nm of a sensitive zone. Quiet periods where no receiver can hear the ship are not counted.`;
    case 'Draught change at sea': return `Flagged when the reported draught changes by ${Number(g('draught_change', 'min_meters', 1)).toFixed(1)} m or more with no port call in between.`;
    case 'Possible ship-to-ship transfer': return `Flagged when another ship stays within ${g('sts', 'max_dist_m', 500)} m for ${g('sts', 'min_hours', 2)} hours or more, both slower than ${g('sts', 'max_speed_kn', 1)} kn, outside port limits.`;
    case 'Position jump': return `Flagged when two positions in a row imply a speed above ${g('position_jump', 'max_implied_kn', 30)} kn, which a merchant ship can't do.`;
    case 'Identity change': return 'Flagged when the name, flag or MMSI changed in the last 12 months. One change is Info; more than one is Medium.';
    default: return '';
  }
}
const isDraught = f => f && f.rule === 'Draught change at sea';
const DRAUGHT_NOTE = 'Draught is typed in by the crew, so draught-based flags are indicators, not proof.';

const Screens = {
  inited: false, home: null, ship: null, page: null, comp: null,
  homeDetent: 'half', shipDetent: 'half', q: '', searchT: 0, searchSeq: 0, results: null,
  cur: { imo: null }, pageKind: null, pageKey: null, mini: null, homeAt: 0, loading: new Map(),
  expand: { voy: false, info: false }, xc: null, firstHome: true,

  /* ================================================================ setup */
  initOnce() {
    if (this.inited) return;
    this.inited = true;
    const H = () => window.innerHeight;
    const fullOf = el => () => el.offsetHeight;
    const hs = $('#homeSheet'), ss = $('#shipSheet'), ps = $('#pageSheet'), cs = $('#composer');
    this.home = new Sheet(hs, { detents: { peek: () => (wide() ? hs.offsetHeight : 228), half: () => (wide() ? hs.offsetHeight : Math.round(H() * 0.52)), full: fullOf(hs) },
      onChange: (n) => { if (n && S.view === 'home') this.homeDetent = n; this.layoutAttr(); } });
    this.ship = new Sheet(ss, { detents: { peek: () => (wide() ? ss.offsetHeight : 214), half: () => (wide() ? ss.offsetHeight : Math.round(H() * 0.56)), full: fullOf(ss) },
      onChange: (n) => { if (n && S.view === 'ship') this.shipDetent = n; this.layoutAttr(); } });
    this.page = new Sheet(ps, { detents: { peek: () => (wide() ? ps.offsetHeight : 196), half: () => (wide() ? ps.offsetHeight : Math.round(H() * 0.5)), full: fullOf(ps) }, onChange: () => this.layoutAttr() });
    this.comp = new Sheet(cs, { detents: { full: fullOf(cs) } });
    for (const sh of [this.home, this.ship, this.page]) sh.detentAllowed = n => !wide() || n === 'full';
    this.page.dismissible = true; this.page.onDismiss = () => App.back();
    this.comp.dismissible = true; this.comp.onDismiss = () => this.compCancel();

    // Home head: the search capsule (a real input, so a tap opens the keyboard on iPhone)
    $('#homeHead').innerHTML = `<div class="hs-search">
      <label class="search"><span aria-hidden="true">${ICON.search(18)}</span>
        <input id="q" type="search" enterkeyhint="search" placeholder="Name, IMO or MMSI" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false" aria-label="Search ships by name, IMO or MMSI">
        <button class="clear" type="button" data-act="clear-q" hidden aria-label="Clear search">${ICON.x(15)}</button></label>
      <button class="cancel" type="button" data-act="cancel-search">Cancel</button></div>`;
    $('#homeBody').innerHTML = `<div class="home-main" id="homeMain"></div><div class="results" id="results" aria-live="polite"></div>`;
    this.qEl = $('#q'); this.qClear = $('#homeHead .clear');
    this.qEl.addEventListener('focus', () => { if (S.route.name !== 'search') App.go('#/search'); });
    this.qEl.addEventListener('input', () => this.onSearchInput());
    this.qEl.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); this.searchEnter(); } else if (e.key === 'Escape') this.act('cancel-search'); });

    // chrome
    $('#regionBtn').addEventListener('click', () => this.pickRegion());
    $('#regionBtn span[aria-hidden]').innerHTML = ICON.down(12);
    $('#alertsBtn').addEventListener('click', () => App.go('#/alerts'));
    $('#meBtn').addEventListener('click', () => App.go('#/profile'));
    $('#shipBack').innerHTML = ICON.back(21);
    $('#shipBack').addEventListener('click', () => App.back());
    $('#shipMore').innerHTML = ICON.share(20);
    $('#shipMore').addEventListener('click', () => this.more());
    $('#shipWatch').addEventListener('click', () => { if (this.cur.imo) this.toggleWatch(this.cur.imo); });
    $('#dim1').addEventListener('click', () => App.back());
    $('#dim2').addEventListener('click', () => App.back());
    $('#dim3').addEventListener('click', () => this.compCancel());

    // one delegated handler for the sheets
    document.body.addEventListener('click', e => {
      if (e.target.closest('#ob, #pages')) return;
      const g = e.target.closest('[data-go]');
      if (g) { e.preventDefault(); if (this.qEl && document.activeElement === this.qEl) this.qEl.blur(); App.go(g.dataset.go); return; }
      const a = e.target.closest('[data-act]');
      if (a) { e.preventDefault(); this.act(a.dataset.act, a, e); }
    });

    // map taps
    MapView.on('ship', (imo, name) => { if (!imo || imo === '0' || +imo === 0) { toast(`${name || 'This ship'} hasn't broadcast its IMO number yet.`); return; } App.go(`#/ship/${imo}`); });
    MapView.on('flag', key => { if (this.cur.imo) App.go(`#/ship/${this.cur.imo}/finding/${encodeURIComponent(key)}`); });
    MapView.on('voyage', n => { if (this.cur.imo && n != null) App.go(`#/ship/${this.cur.imo}/voyage/${n}`); });
    // Re-frame the region when the screen size settles (the keyboard closing after sign-in, rotation, iOS toolbars),
    // unless the person has moved the map since the last framing.
    if (MapView.map) MapView.map.on('movestart', e => { if (e && e.originalEvent) this.movedAt = Date.now(); });
    const onResize = () => {
      this.layoutAttr();
      clearTimeout(this.refitT);
      this.refitT = setTimeout(() => this.refitHome(), 180);
    };
    window.addEventListener('resize', onResize);
    if (window.visualViewport) window.visualViewport.addEventListener('resize', onResize);
    this.renderRegionName();
    this.loadPorts();
  },

  async loadPorts() { if (S.ports) return; try { S.ports = await API.ports(); } catch (e) { S.ports = []; } },

  reset() {
    if (!this.inited) return;
    this.closeComposer(true);
    for (const sh of [this.page, this.ship, this.home]) sh.hide(false);
    this.dropMini();
    $('#shipSheet').classList.remove('back'); $('#homeSheet').classList.remove('back', 'searching');
    $$('.dim').forEach(d => d.classList.remove('on'));
    this.chrome('none');
    MapView.clearShip(); MapView.setLive([]);
    $('#homeMain').innerHTML = ''; $('#results').innerHTML = ''; $('#shipBody').innerHTML = ''; $('#shipSheet .head').innerHTML = '';
    this.qEl.value = ''; this.q = ''; this.results = null; this.cur = { imo: null }; this.homeAt = 0; this.firstHome = true;
    S.view = null;
  },

  /* ================================================================ layout helpers */
  chrome(mode) {
    $('#homeChrome').classList.toggle('hide', mode !== 'home');
    $('#liveChip').classList.toggle('hide', mode !== 'home');
    $('#shipChrome').classList.toggle('hide', !(mode === 'ship' || mode === 'voyage'));
    $('#shipWatch').hidden = mode !== 'ship'; $('#shipMore').hidden = mode !== 'ship';
    $('#veil').style.opacity = mode === 'none' ? '0' : '1';
  },
  layoutAttr() {
    const a = $('#attr'); if (!a) return;
    if (wide()) { a.style.bottom = '8px'; return; }
    const v = Math.max(this.home ? this.home.visible() : 0, this.ship ? this.ship.visible() : 0, this.page && this.page.shown ? this.page.visible() : 0);
    a.style.bottom = `${v + 6}px`;
    a.style.opacity = v > window.innerHeight * 0.7 ? '0' : '';
  },
  mapPad(sheet) {
    if (wide()) return { top: 90, bottom: 30, left: 450, right: 40 };
    const top = 104;
    const vis = sheet && sheet.shown ? sheet.visible() : 0;
    return { top, bottom: clamp(vis + 18, 30, window.innerHeight - top - 80), left: 24, right: 24 };
  },
  fitRegion(animate) {
    const r = (S.regions || []).find(x => x.id === S.region) || REGION_VIEW[S.region] || REGION_VIEW.blacksea;
    this.fitAt = Date.now();
    MapView.fit(r.bbox, { duration: animate ? 820 : 0, maxZoom: 8.6, padding: this.mapPad(this.home) });
  },
  refitHome() {
    if (S.view === 'home' && !(this.movedAt > this.fitAt)) this.fitRegion(true);
  },
  renderRegionName() { $('#regionName').textContent = (S.regions.find(r => r.id === S.region) || {}).name || REGION_NAME[S.region] || 'Black Sea'; },
  dropMini() { if (this.mini) { try { this.mini.remove(); } catch (e) { /* gone */ } this.mini = null; } },

  /* ================================================================ routing entry points */
  apply(r, prev) {
    if (this.compState && !(r.name === prev.name && r.imo === prev.imo)) this.closeComposer(true);
    switch (r.name) {
      case 'home': return this.showHome(false, prev);
      case 'search': return this.showHome(true, prev);
      case 'ship': return this.showShip(r.imo, prev);
      case 'voyage': return this.showVoyage(r.imo, r.n, prev);
      case 'finding': return this.showFinding(r.imo, decodeURIComponent(r.key), prev);
      case 'alerts': return this.showAlerts(prev);
      case 'list': return this.showList(r.kind, prev);
      default: return this.showHome(false, prev);
    }
  },

  closePage() {
    if (this.page.shown) this.page.hide();
    $('#voyTools').hidden = true; $('#pageSheet').classList.remove('has-tools');
    this.dropMini();
    this.pageKind = null; this.pageKey = null;
    $('#dim2').classList.remove('on');
    $('#shipSheet').classList.remove('back'); $('#homeSheet').classList.remove('back');
  },

  /* ================================================================ Home and search */
  showHome(searching, prev = {}) {
    const fromShip = ['ship', 'voyage', 'finding'].includes(prev.name) || (prev.name === 'list' || prev.name === 'alerts') && this.cur.imo && S.view === 'ship';
    this.closePage();
    if (this.ship.shown) this.ship.hide();
    S.view = searching ? 'search' : 'home';
    this.chrome(searching ? 'search' : 'home');
    const hsEl = $('#homeSheet');
    MapView.clearShip(); MapView.showLive(true);
    this.cur = { imo: null };
    if (searching) {
      hsEl.classList.add('searching');
      $('#dim1').classList.add('on');
      this.home.snap('full');
      this.renderResults();
    } else {
      hsEl.classList.remove('searching');
      $('#dim1').classList.remove('on');
      if (document.activeElement === this.qEl) this.qEl.blur();
      this.home.snap(this.home.pos && this.home.pos !== 'full' && prev.name !== 'search' ? this.home.pos : this.homeDetent === 'full' ? 'half' : this.homeDetent);
    }
    if (!S.overview || !$('#homeMain').innerHTML) this.renderHome();
    if (this.firstHome) {
      this.firstHome = false;
      requestAnimationFrame(() => this.fitRegion(false));
      setTimeout(() => this.refitHome(), 700);          // again once the sign-in keyboard and the welcome fade are gone
    }
    else if (fromShip) this.fitRegion(true);
    this.renderLiveChip();
    this.layoutAttr();
  },

  async refreshHome(force) {
    if (!S.me || !this.inited) return;
    const rid = S.region;
    if (!force && Date.now() - this.homeAt < 50e3) return;
    this.homeAt = Date.now();
    const [ov, w] = await Promise.allSettled([API.overview(rid), API.watching()]);
    if (rid !== S.region) return;
    if (ov.status === 'fulfilled') { S.overview = ov.value; this.homeErr = null; } else this.homeErr = ov.reason;
    if (w.status === 'fulfilled') S.watching = w.value || [];
    if (S.view === 'home' || S.view === 'search' || !S.view) this.renderHome();
    this.renderLiveChip();
    try { const rows = await API.live(rid); if (rid === S.region) { S.live = rows || []; MapView.setLive(S.live); } } catch (e) { /* keep the last rows */ }
  },

  renderLiveChip() {
    const o = S.overview; const el = $('#liveChip');
    if (!o) { el.innerHTML = ''; return; }
    let cls = '', txt;
    if (o.source === 'demo') txt = 'Demo fleet on this machine';
    else if (!o.newest) { cls = 'off'; txt = S.me && S.me.server && !S.me.server.liveKey ? 'Live feed not connected' : 'No live positions yet'; }
    else if (Date.now() - o.newest > 30 * 60e3) { cls = 'stale'; txt = `Last position ${Fmt.ago(o.newest)}`; }
    else txt = `Live, updated ${Fmt.ago(o.newest)}`;
    el.innerHTML = `<span class="chip ${cls}"><span class="dot"></span>${esc(txt)}</span>`;
  },

  renderHome() {
    const box = $('#homeMain'); if (!box) return;
    const o = S.overview; const me = S.me || {}; const admin = me.user && me.user.role === 'admin';
    const first = !box.dataset.done;
    let h = '';
    if (me.server && !me.server.mock && !me.server.liveKey) h += admin ? this.setupCard() : `<div class="setup-card"><h3>The live feed isn't connected yet</h3><p>Ships appear on the map once an admin adds the free aisstream.io key in Profile › Data sources.</p></div>`;
    else if (admin && me.server && (me.server.recorder === 'error' || me.server.recorder === 'stopped')) h += `<div class="setup-card" style="background:var(--red-bg);box-shadow:none"><h3>${me.server.recorder === 'error' ? 'aisstream.io isn’t sending positions' : 'The recorder has stopped'}</h3><p>${me.server.recorder === 'error' ? 'The key may be wrong or expired.' : 'The server process that records the feed isn’t running.'} Details in Profile › Data sources.</p><button class="btn small" style="margin-top:12px" data-go="#/profile/sources">Open Data sources</button></div>`;
    // the three figures
    if (!o) {
      h += this.homeErr ? `<div class="empty"><div class="ei">${ICON.warn(24)}</div><h3>Couldn't load ${esc(REGION_NAME[S.region])}</h3><p>${esc(this.homeErr.message || '')}</p><button class="btn small tinted" style="margin-top:14px" data-act="home-retry">Try again</button></div>`
        : `<div class="tiles" style="margin-top:14px">${'<div class="tile sk"><div class="v"></div><div class="l"></div></div>'.repeat(3)}</div>`;
      box.innerHTML = h; return;
    }
    const c = o.counts;
    h += `<div class="tiles" style="margin-top:14px">
      <button class="tile tap" data-act="see-map"><div class="v">${Fmt.n(c.inRange)}</div><div class="l">${c.inRange === 1 ? 'ship' : 'ships'} in range</div></button>
      <button class="tile tap ${c.high ? 'risk' : ''}" ${c.high ? 'data-go="#/list/high"' : 'data-act="noop"'}><div class="v">${Fmt.n(c.high)}</div><div class="l">high risk</div></button>
      <button class="tile tap ${c.sanctioned ? 'risk' : ''}" ${c.sanctioned ? 'data-go="#/list/sanctioned"' : 'data-act="noop"'}><div class="v">${Fmt.n(c.sanctioned)}</div><div class="l">on sanctions lists</div></button></div>`;
    // watching
    const W = S.watching || [];
    if (W.length) {
      h += `<div class="sec-h"><h2>Watching</h2><span class="act c2">${W.length}</span></div><div class="group">${W.slice(0, 6).map(w => this.watchRow(w)).join('')}</div>`;
      if (W.length > 6) h += `<p class="sec-foot">${W.length - 6} more in Profile › Watching.</p>`;
    }
    // highest risk in range
    if (!c.inRange) {
      h += `<div class="empty"><div class="ei">${ICON.antenna(24)}</div><h3>No ships heard here yet</h3><p>${me.server && !me.server.liveKey && !me.server.mock ? 'Connect the live feed to start recording positions.' : "The free feed hears ships within reach of coastal receivers. Positions show up here within minutes of a ship being heard."}</p></div>`;
    } else if (c.high) {
      h += `<div class="sec-h"><h2>Highest risk in range</h2>${c.high > 3 ? `<button class="act" data-go="#/list/high">See all ${c.high}</button>` : ''}</div>
        <div class="group">${o.highest.slice(0, 3).map(r => this.liveRow(r)).join('')}</div>`;
    } else if (!c.checked) {
      h += `<div class="empty"><div class="ei"><span class="spin" style="color:var(--text-2)"></span></div><h3>Checking the ships in range</h3><p>Every ship heard here gets the full check, a few at a time. The first results appear within minutes.</p></div>`;
    } else {
      h += `<div class="empty"><div class="ei" style="color:var(--green)">${ICON.check(24)}</div><h3>No high-risk ships in range</h3><p>${Fmt.n(c.checked)} of ${Fmt.n(c.inRange)} checked so far.${o.sweep && o.sweep.waiting ? ` ${Fmt.n(o.sweep.waiting)} still waiting.` : ''}</p></div>`;
    }
    if (c.inRange) h += `<p class="sec-foot" style="margin-top:12px">${this.coverageLine(o, c)}</p>`;
    box.innerHTML = `<div class="${first ? 'cascade' : ''}">${h}</div>`;
    box.dataset.done = '1';
  },
  coverageLine(o, c) {
    const rec = o.recorder;
    const since = rec && rec.oldest ? ` since ${Fmt.day(rec.oldest, true)}` : '';
    const chk = c.checked < c.inRange ? ` ${Fmt.n(c.checked)} of ${Fmt.n(c.inRange)} checked so far.` : ' All checked.';
    if (o.source === 'demo') return `Demo fleet generated on this machine.${chk}`;
    return `Ships heard in the last 6 hours by aisstream.io's free feed, recorded on your server${since}. It hears ships near the coast only.${chk}`;
  },
  setupCard() {
    return `<div class="setup-card"><h3>Connect the live feed</h3>
      <p>MarineEdge records ship positions from aisstream.io's free feed. Setting it up takes two minutes:</p>
      <ol><li>Open <a href="https://aisstream.io" target="_blank" rel="noopener">aisstream.io</a> and sign in with GitHub.</li><li>Create an API key and copy it.</li><li>Paste it here.</li></ol>
      <div class="inp" style="background:var(--fill-2)"><span class="ico">${ICON.key(17)}</span><input id="aisKey" placeholder="Paste the API key" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="aisstream.io API key"></div>
      <button class="btn" style="margin-top:12px" data-act="save-ais"><span class="lbl">Start recording</span></button></div>`;
  },
  liveRow(r) {
    const lvl = r.level || 'none';
    const head = r.headline || (r.sanctioned ? 'On a sanctions list' : r.level ? LEVEL_LABEL[r.level] : 'Not checked yet');
    const desc = [typeOf(r), navText(r)].filter(Boolean).join(', ');
    return `<button class="row ship rowtap" data-act="open-ship" data-imo="${r.imo || 0}" data-name="${esc(r.name)}" data-level="${esc(r.level || '')}">
      <span class="ship-ic ${lvl}">${ICON.ship(20)}</span>
      <span class="tx"><div class="t1 b">${esc(r.name)}</div><div class="t2">${esc(head)}</div><div class="t3">${esc(desc)}</div></span><span class="chev">${ICON.chev(14)}</span></button>`;
  },
  watchRow(w) {
    const lvl = w.level || 'none';
    const near = w.last ? nearestPort(w.last.lat, w.last.lon) : null;
    const where = w.last ? `Heard ${Fmt.ago(w.last.t)}${w.last.sog >= 1 ? `, ${Number(w.last.sog).toFixed(1)} kn` : ''}${near ? ` near ${near.port.name}` : ''}` : 'Not heard by the live feed yet';
    return `<button class="row ship rowtap" data-act="open-ship" data-imo="${w.imo}" data-name="${esc(w.name)}" data-level="${esc(w.level || '')}">
      <span class="ship-ic ${lvl}">${ICON.ship(20)}</span>
      <span class="tx"><div class="t1 b">${esc(w.name)}</div><div class="t2">${esc(w.headline || (w.level ? LEVEL_LABEL[w.level] : 'Not checked yet'))}</div><div class="t3">${esc(where)}</div></span><span class="chev">${ICON.chev(14)}</span></button>`;
  },

  onSearchInput() {
    const q = this.qEl.value.trim(); this.q = q;
    this.qClear.hidden = !this.qEl.value;
    clearTimeout(this.searchT);
    if (q.length < 2) { this.searchSeq++; this.results = null; this.renderResults(); return; }
    this.searchT = setTimeout(() => this.runSearch(q), 220);
  },
  async runSearch(q) {
    const seq = ++this.searchSeq;
    if (!this.results || this.results.q !== q) $('#results').classList.add('busy');
    try {
      const items = await API.search(q);
      if (seq !== this.searchSeq) return;
      this.results = { q, items: items || [] };
    } catch (e) { if (seq !== this.searchSeq) return; this.results = { q, error: e.message }; }
    $('#results').classList.remove('busy');
    this.renderResults();
  },
  searchEnter() {
    const q = this.qEl.value.trim();
    clearTimeout(this.searchT);
    const items = this.results && this.results.q === q ? this.results.items || [] : [];
    if (items.length === 1) return this.openShip(items[0].imo, items[0].name, items[0].verdict && items[0].verdict.level);
    if (/^\d{7}$/.test(q)) return this.openShip(+q, null, null);
    if (q.length >= 2) this.runSearch(q);
  },
  renderResults() {
    const box = $('#results'); if (!box) return;
    const q = this.q;
    if (!q || q.length < 2) {
      const rec = store.get('recent', []);
      box.innerHTML = rec.length ? `<div class="sec-h"><h2>Recently checked</h2><button class="act" data-act="recent-clear">Clear</button></div>
        <div class="recent">${rec.slice(0, 10).map(r => `<button class="tap" data-act="open-ship" data-imo="${r.imo}" data-name="${esc(r.name)}">${esc(r.name)}</button>`).join('')}</div>
        <p class="sec-foot" style="margin-top:22px">Search by name, a former name, the 7-digit IMO number or the 9-digit MMSI.</p>`
        : `<div class="empty"><div class="ei">${ICON.search(24)}</div><h3>Find any ship</h3><p>By name, a former name, the 7-digit IMO number or the 9-digit MMSI.</p></div>`;
      return;
    }
    const R = this.results;
    if (!R || R.q !== q) { box.innerHTML = `<div class="empty"><span class="spin" style="margin:0 auto;color:var(--text-2)"></span></div>`; return; }
    if (R.error) { box.innerHTML = `<div class="empty"><div class="ei">${ICON.warn(24)}</div><h3>Search didn't work</h3><p>${esc(R.error)}</p></div>`; return; }
    const items = R.items;
    if (!items.length) {
      const imo = /^\d{7}$/.test(q);
      box.innerHTML = `<div class="empty"><div class="ei">${ICON.search(24)}</div><h3>No ship matches “${esc(q)}”</h3><p>${S.me && S.me.server && S.me.server.mock ? 'The demo fleet has a few dozen ships.' : 'The free feed knows the ships it has heard since your server started recording. Try the IMO or MMSI number.'}</p>
        ${imo ? `<button class="btn small tinted" style="margin-top:14px" data-act="open-ship" data-imo="${q}">Look up IMO ${q}</button>` : ''}</div>`;
      return;
    }
    box.innerHTML = `<p class="sec-cap">${items.length === 1 ? '1 ship matches' : `${items.length} ships match`}</p><div class="group">${items.map(m => {
      const v = m.verdict; const lvl = v ? v.level : 'none';
      const spec = [typeOf(m), m.dwt ? `${Fmt.n(m.dwt)} dwt` : '', m.built ? `built ${m.built}` : ''].filter(Boolean).join(', ');
      const id = [m.flag ? `${m.flag} flag` : '', `IMO ${m.imo}`, v && v.checked ? `checked ${Fmt.day(v.checked)}` : ''].filter(Boolean).join(' · ');
      return `<button class="row ship rowtap" data-act="open-ship" data-imo="${m.imo}" data-name="${esc(m.name)}" data-level="${esc(v ? v.level : '')}">
        <span class="ship-ic ${lvl}">${ICON.ship(20)}</span>
        <span class="tx"><div class="t1 rowline"><span class="nm b">${hl(m.name, q)}</span>${vbadge(v && v.level, v && v.label)}</div>
          ${m.matchedFormer ? `<div class="t3">Formerly <span class="mark">${hl(m.matchedFormer, q)}</span></div>` : ''}
          <div class="t2">${esc(spec)}</div><div class="t3">${esc(id)}</div></span></button>`;
    }).join('')}</div><p class="sec-foot">The IMO number stays with the hull when the name, flag or MMSI change, so it always finds the right ship.</p>`;
  },

  async pickRegion() {
    const regs = S.regions.length ? S.regions : Object.keys(REGION_NAME).map(id => ({ id, name: REGION_NAME[id] }));
    const v = await actionSheet({ title: 'Show ships in', actions: regs.map(r => ({ label: r.name, value: r.id, bold: r.id === S.region })) });
    if (!v || v === S.region) return;
    S.region = v; store.set('region', v);
    API.updateMe({ prefs: { region: v } }).catch(() => {});
    this.renderRegionName();
    S.overview = null; S.live = []; MapView.setLive([]);
    this.renderHome(); this.renderLiveChip();
    this.fitRegion(true);
    this.refreshHome(true);
  },

  /* ================================================================ a ship */
  async load(imo, { refresh = false } = {}) {
    const c = S.analyses.get(imo);
    if (c && !refresh && Date.now() - c.at < 5 * 60e3) return c.a;
    if (!refresh && this.loading.has(imo)) return this.loading.get(imo);
    const p = API.analysis(imo, refresh).then(a => {
      S.analyses.set(imo, { a, at: Date.now() });
      this.loading.delete(imo);
      this.remember(a);
      return a;
    }, e => { this.loading.delete(imo); throw e; });
    this.loading.set(imo, p);
    return p;
  },
  async loadNotes(imo) {
    try { S.notes.set(imo, await API.notes(imo)); } catch (e) { if (!S.notes.has(imo)) S.notes.set(imo, []); }
    return S.notes.get(imo);
  },
  remember(a) {
    const v = a.vessel; const rec = store.get('recent', []).filter(r => r.imo !== v.imo);
    rec.unshift({ imo: v.imo, name: v.name, level: a.verdict && a.verdict.level });
    store.set('recent', rec.slice(0, 12));
  },
  openShip(imo, name) {
    if (!imo || +imo === 0) { toast(`${name || 'This ship'} hasn't broadcast its IMO number yet.`); return; }
    if (document.activeElement === this.qEl) this.qEl.blur();
    this.pendingName = name || null;
    App.go(`#/ship/${imo}`);
  },

  async showShip(imo, prev = {}) {
    const same = this.cur.imo === imo && ['voyage', 'finding'].includes(prev.name) || (this.cur.imo === imo && S.view === 'ship');
    this.closePage();
    if (this.home.shown) this.home.hide();
    $('#homeSheet').classList.remove('searching'); $('#dim1').classList.remove('on');
    if (document.activeElement === this.qEl) this.qEl.blur();
    S.view = 'ship';
    this.chrome('ship');
    MapView.showLive(false);
    this.renderWatch(imo);
    if (same && this.cur.a) {
      if (!this.ship.shown || this.ship.pos == null) this.ship.snap(this.shipDetent);
      MapView.setShip(this.cur.a);
      if (S.focusFlag) this.focusFlag(S.focusFlag);
      else if (prev.name === 'voyage') this.fitShip(true);
      this.layoutAttr();
      return;
    }
    this.cur = { imo, a: null };
    this.expand = { voy: false, info: false }; this.xc = null;
    const cached = S.analyses.get(imo);
    const name = cached ? cached.a.vessel.name : this.pendingName || (S.live.find(r => r.imo === imo) || {}).name || (store.get('recent', []).find(r => r.imo === imo) || {}).name;
    this.pendingName = null;
    if (!cached) this.renderShipLoading(imo, name);
    this.ship.snap(this.shipDetent === 'full' ? 'half' : this.shipDetent);
    this.layoutAttr();
    MapView.clearShip();
    try {
      const [a] = await Promise.all([this.load(imo), this.loadNotes(imo)]);
      if (this.cur.imo !== imo || S.view !== 'ship') return;
      this.cur.a = a;
      this.renderShip(a);
      MapView.setShip(a);
      if (S.focusFlag) this.focusFlag(S.focusFlag); else this.fitShip(true);
    } catch (e) {
      if (this.cur.imo !== imo) return;
      this.renderShipError(imo, name, e);
    }
  },
  fitShip(animate) {
    const a = this.cur.a; if (!a) return;
    const pts = (a.track || []).filter(p => !p.jump);
    const b = boundsOf(pts.length ? pts : a.last ? [a.last] : []);
    if (!b) return;
    MapView.fit(b, { duration: animate ? 820 : 0, maxZoom: 8.5, padding: this.mapPad(this.ship) });
  },
  focusFlag(key) {
    S.focusFlag = null;
    const a = this.cur.a; if (!a) return;
    const f = (a.flags || []).find(x => x.key === key);
    MapView.setShip(a, { flagKey: key, sel: f ? f.voyage : null });
    if (!this.ship.shown) this.ship.snap('peek'); else this.ship.snap('peek');
    if (f && f.lat != null) {
      const pts = [{ lon: f.lon, lat: f.lat }, ...((f.evidence && [...(f.evidence.before || []), ...(f.evidence.after || [])]) || [])];
      const b = boundsOf(pts); const pad = 0.25;
      setTimeout(() => MapView.fit([b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad], { maxZoom: 9, padding: this.mapPad(this.ship) }), 60);
    }
  },
  renderWatch(imo) {
    const on = !!(S.me && S.me.watchlist && S.me.watchlist.includes(imo));
    const b = $('#shipWatch');
    b.innerHTML = on ? `<span style="color:var(--yellow)">${ICON.starFill(21)}</span>` : ICON.star(21);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.setAttribute('aria-label', on ? 'Watching. Tap to stop watching' : 'Watch this ship');
    const w = $('#watchBtn'); if (w) w.innerHTML = on ? `<span style="color:var(--yellow);display:flex">${ICON.starFill(19)}</span>Watching` : `${ICON.star(19)}Watch`;
  },
  shipHead(name, sub) {
    $('#shipSheet .head').innerHTML = `<div class="ship-head"><h1 class="selectable">${esc(name || 'Loading…')}</h1><div class="sub">${sub}</div></div>`;
  },
  renderShipLoading(imo, name) {
    this.shipHead(name || `IMO ${imo}`, `IMO ${imo}`);
    $('#shipBody').innerHTML = `<div class="verdict"><div class="skl" style="height:14px;width:38%"></div><div class="skl" style="height:20px;margin-top:14px"></div><div class="skl" style="height:20px;width:72%;margin-top:7px"></div></div>
      <div class="tiles" style="margin-top:10px">${'<div class="tile sk"><div class="v"></div><div class="l"></div></div>'.repeat(3)}</div>
      <p class="foot-note" style="text-align:center;margin-top:20px">Checking twelve months of positions…</p>`;
  },
  renderShipError(imo, name, e) {
    this.shipHead(name || `IMO ${imo}`, `IMO ${imo}`);
    const unknown = e.status === 404;
    $('#shipBody').innerHTML = `<div class="empty"><div class="ei">${unknown ? ICON.antenna(24) : ICON.warn(24)}</div>
      <h3>${unknown ? 'No data for this IMO yet' : "Couldn't check this ship"}</h3>
      <p>${unknown ? (S.me && S.me.server && S.me.server.mock ? 'It isn’t in the demo fleet.' : "The live feed hasn't heard a ship broadcasting this IMO number. Ships send it every few minutes while a receiver can hear them.") : esc(e.message)}</p>
      <button class="btn small tinted" style="margin-top:16px" data-act="retry-ship">Try again</button></div>`;
  },

  renderShip(a) {
    const v = a.vessel; const imo = v.imo;
    const former = (v.exNames || [])[0];
    this.shipHead(v.name, `${esc(typeOf(v))}${v.flag ? ' · ' + esc(v.flag) : ''} · IMO ${imo}${former ? `<br>Formerly ${esc(former)}` : ''}`);
    const body = $('#shipBody'); const keep = body.scrollTop;
    body.innerHTML = [this.verdictCard(a), this.tilesHtml(a), this.statusHtml(a), this.historyCard(a), this.timeline(a), this.yearBar(a), this.voyagesHtml(a),
      this.identityHtml(a), this.particularsHtml(a), `<div id="notesShip">${this.notesHtml(imo, null)}</div>`, this.crossHtml(), this.actionsHtml(a), this.footHtml(a)].join('');
    body.scrollTop = keep;
    this.renderWatch(imo);
  },
  verdictCard(a) {
    const vd = a.verdict || {}; const lvl = vd.level || 'insufficient';
    return `<div class="verdict ${lvl}"><div class="vh"><span class="lvl">${LEVEL_ICON[lvl] ? LEVEL_ICON[lvl]() : ''}${esc(vd.label || LEVEL_LABEL[lvl])}</span><span class="meta">${esc(vd.meta || '')}</span></div>
      <p class="sentence">${esc(vd.sentence || '')}</p>${vd.detail ? `<p class="detail">${esc(vd.detail)}</p>` : ''}</div>`;
  },
  tilesHtml(a) {
    const t = (a.verdict && a.verdict.tiles) || [];
    if (!t.length) return '';
    return `<div class="tiles" style="margin-top:10px">${t.map(x => `<div class="tile ${x.risk ? 'risk' : ''}"><div class="v">${esc(x.value)}</div><div class="l">${esc(x.label)}</div></div>`).join('')}</div>`;
  },
  statusHtml(a) {
    const st = a.status || {}; const last = a.last;
    if (!last) return `<div class="status"><span class="live off"></span><div><div class="t-body b">No position yet</div></div></div>`;
    const stale = Date.now() - last.t > 6 * 3600e3;
    const dest = st.nextPort ? st.nextPort.name : st.destination ? titleCase(st.destination) : '';
    let l1, l2 = '';
    if (st.state === 'moored') l1 = `Moored${st.port ? ' at ' + st.port.name : ''}${st.since ? ' since ' + Fmt.day(st.since) : ''}`;
    else if (st.state === 'anchored') l1 = `At anchor${st.port ? ' off ' + st.port.name : ''}${st.since ? ' since ' + Fmt.day(st.since) : ''}`;
    else l1 = `Under way${dest ? ' to ' + dest : ''}${last.sog != null ? ` at ${Number(last.sog).toFixed(1)} kn` : ''}`;
    if (st.state === 'underway' && st.eta) l2 = `Due ${Fmt.dayTime(st.eta)}${last.draught ? ` · draught ${last.draught} m, typed by the crew` : ''}`;
    else if (st.state !== 'underway' && dest) l2 = `Next port typed by the crew: ${dest}`;
    if (stale) l2 = `Last heard ${Fmt.ago(last.t)}${l2 ? ' · ' + l2 : ''}`;
    return `<div class="status"><span class="live ${stale ? 'off' : ''}"></span><div><div class="t-body b">${esc(l1)}</div>${l2 ? `<div class="t-sub c2" style="margin-top:2px">${esc(l2)}</div>` : ''}</div></div>`;
  },
  historyCard(a) {
    const h = a.history || {}; const vd = a.verdict || {};
    const admin = S.me && S.me.user && S.me.user.role === 'admin';
    if (h.available && !h.bought) {
      return `<div class="setup-card"><h3>Get the last 12 months</h3><p>Bought once from ${esc(titleCase(h.provider || 'the history provider'))}, open sea included, and kept on your server. ${admin ? 'You confirm before any credits are used.' : 'An admin can buy it for this ship.'}</p>
        ${admin ? `<button class="btn" style="margin-top:14px" data-act="buy-history"><span class="lbl">Get 12 months of history</span></button>` : ''}</div>`;
    }
    if (!h.available && (vd.historyDays || 0) < 300 && a.stats && /aisstream/i.test(a.stats.source || '')) {
      const since = a.stats.historySince ? Fmt.day(a.stats.historySince, true) : null;
      return `<p class="foot-note" style="margin-top:14px">${since ? `Your server has recorded this area since ${since}, so older voyages aren't here yet.` : 'Older voyages aren’t recorded yet.'}${admin ? ' Adding a Datalastic key in Profile › Data sources lets you buy the last 12 months per ship.' : ''}</p>`;
    }
    return '';
  },
  timeline(a) {
    const flags = a.flags || [];
    const main = flags.filter(f => f.severity !== 'info').sort((x, y) => x.t0 - y.t0);
    const info = flags.filter(f => f.severity === 'info').sort((x, y) => x.t0 - y.t0);
    if (!main.length && !info.length) return '';
    const imo = a.vessel.imo; const notes = S.notes.get(imo) || [];
    const item = f => {
      const st = f.story || { title: f.title, text: (f.lines || [])[0] || '' };
      const nn = notes.some(n => n.scope === `flag:${f.key}`);
      return `<button class="tl-item rowtap" data-go="#/ship/${imo}/finding/${encodeURIComponent(f.key)}"><span class="pin ${f.severity}"></span><span class="when">${esc(Fmt.range(f.t0, f.t1))}</span>
        <span class="what">${esc(st.title)}${nn ? `<span class="c2" aria-label="Has a team note">${ICON.note(14)}</span>` : ''}</span><span class="why">${esc(st.text)}</span></button>`;
    };
    let h = `<div class="sec-h"><h2>What happened</h2>${main.length ? `<span class="act c2">${main.length === 1 ? '1 finding' : main.length + ' findings'}</span>` : ''}</div><div class="timeline">`;
    let month = null;
    for (const f of main) { const m = Fmt.month(f.t0); if (m !== month) { h += `<div class="tl-month">${esc(m)}</div>`; month = m; } h += item(f); }
    if (main.length) {
      const lastT = Math.max(...main.map(f => f.t1 || f.t0));
      const months = Math.round((Date.now() - lastT) / (30.4 * DAY));
      if (months >= 2) h += `<div class="tl-end"><span class="ok">${ICON.okc(14)}</span>Nothing found in the ${months <= 12 ? NUM_WORD[months] : months} months since.</div>`;
    }
    if (info.length) {
      if (this.expand.info) { h += `<div class="tl-month">Not counted</div>` + info.map(item).join(''); }
      else h += `<button class="tl-end rowtap" data-act="tl-info" style="width:100%;text-align:left"><span class="ok" style="color:var(--text-3)">${ICON.dashc(14)}</span>${info.length === 1 ? 'One quiet period' : `${NUM_WORD[info.length] || info.length} quiet periods`} outside receiver coverage, not counted. Show</button>`;
    }
    return h + '</div>';
  },
  yearBar(a) {
    const vs = a.voyages || []; const fl = (a.flags || []).filter(f => f.severity !== 'info');
    if (!vs.length && !fl.length) return '';
    const now = Date.now(), t0 = now - 365 * DAY, W = 322;
    const x = t => clamp((t - t0) / (now - t0) * W, 0, W);
    const P = PAL[S.theme] || PAL.dark;
    let s = '';
    const d = new Date(t0); d.setUTCDate(1); d.setUTCHours(0, 0, 0, 0); d.setUTCMonth(d.getUTCMonth() + 1);
    for (; d.getTime() < now; d.setUTCMonth(d.getUTCMonth() + 1)) {
      const xx = x(d.getTime());
      s += `<path d="M${xx.toFixed(1)} 14V32" style="stroke:var(--sep-soft)" stroke-width="1"/>`;
      if (xx < W - 6) s += `<text x="${(xx + 2).toFixed(1)}" y="44" font-size="10" style="fill:var(--text-2)">${'JFMAMJJASOND'[d.getUTCMonth()]}</text>`;
    }
    const from = a.verdict && a.verdict.historyFrom;
    if (from && from > t0 + 7 * DAY) s += `<rect x="0" y="22" width="${x(from).toFixed(1)}" height="2" rx="1" style="fill:var(--fill-2)"/>`;
    for (const v of vs) { const xa = x(v.depart), xb = x(v.arrive || now); s += `<rect x="${xa.toFixed(1)}" y="18" width="${Math.max(1.2, xb - xa).toFixed(1)}" height="10" rx="2" fill="${P.voyages[v.color % 8]}"/>`; }
    for (const f of fl) s += `<circle cx="${x(f.t0).toFixed(1)}" cy="8" r="3.2" fill="${f.severity === 'high' ? P.high : P.medium}"/>`;
    const cap = from && from > t0 + 7 * DAY ? `Recorded from ${Fmt.day(from, true)}. ` : '';
    return `<div class="sec-h"><h2>The year at a glance</h2></div><div class="yearbar"><svg viewBox="0 0 ${W} 48" role="img" aria-label="${vs.length} voyages and ${fl.length} findings over the last 12 months">${s}</svg>
      <p class="cap">${esc(cap)}Each bar is one voyage, the gaps are time in port. Dots are findings.</p></div>`;
  },
  voyName(a, v) {
    const st = a.status || {};
    const from = v.from ? v.from.port.name : 'At sea';
    const to = v.to ? v.to.port.name : v.current ? (st.nextPort ? st.nextPort.name : st.destination ? titleCase(st.destination) : 'at sea') : 'at sea';
    return { from, to };
  },
  voyagesHtml(a) {
    const vs = [...(a.voyages || [])].reverse(); if (!vs.length) return '';
    const byId = Object.fromEntries((a.flags || []).map(f => [f.id, f]));
    const P = PAL[S.theme] || PAL.dark; const imo = a.vessel.imo;
    const show = this.expand.voy ? vs : vs.slice(0, 4);
    const rows = show.map(v => {
      const { from, to } = this.voyName(a, v);
      const fl = (v.flags || []).map(id => byId[id]).filter(f => f && f.severity !== 'info');
      const hi = fl.some(f => f.severity === 'high');
      const cnt = fl.length ? `<span class="cnt ${hi ? '' : 'med'}" aria-label="${fl.length} findings">${fl.length}</span>` : '';
      const span = Fmt.range(v.depart, v.arrive || null);
      return `<button class="row rowtap" data-go="#/ship/${imo}/voyage/${v.n}"><span class="vsw" style="background:${P.voyages[v.color % 8]}"></span>
        <span class="tx"><div class="t1">${esc(from)} → ${esc(to)}</div><div class="t2">${esc(span)}${v.current ? ', now' : ''} · ${Fmt.nm(v.nm)} · ${dh((v.arrive || Date.now()) - v.depart)}</div></span>${cnt}<span class="chev">${ICON.chev(14)}</span></button>`;
    }).join('');
    const more = vs.length > 4 ? `<button class="row accent rowtap" data-act="voy-more"><span class="tx"><div class="t1">${this.expand.voy ? 'Show fewer' : `Show all ${vs.length} voyages`}</div></span></button>` : '';
    return `<div class="sec-h"><h2>Voyages</h2><button class="act" data-act="fit-all">${vs.length > 1 ? `All ${vs.length} on the map` : 'Show on the map'}</button></div><div class="group">${rows}${more}</div>`;
  },
  identityHtml(a) {
    const v = a.vessel; const hist = (v.history || []);
    const last = f => hist.filter(h => h.field === f).sort((x, y) => y.t - x.t)[0];
    const kv = (k, val, sub, cls = '') => `<div class="kv"><span class="k">${k}</span><span class="v ${cls}">${val}${sub ? `<div class="s">${sub}</div>` : ''}</span></div>`;
    const since = (h, fallback) => h ? `Since ${Fmt.day(h.t, true)} · before: ${esc(h.from)}` : fallback || '';
    let sanc;
    const checked = a.sanctionsChecked; const L = a.sanctionsLists || [];
    const short = { 'OFAC SDN': 'OFAC', EU: 'EU', UK: 'UK' };
    const names = [...['OFAC SDN', 'EU', 'UK'].filter(x => L.includes(x)), ...L.filter(x => !short[x])].map(x => short[x] || x);
    const joined = names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names.join('');
    if (v.sanctions && v.sanctions.length) {
      const lists = [...new Set(v.sanctions.map(s => s.list))].join(', ');
      sanc = kv('Sanctions', `<span class="c-red b">Listed</span>`, esc(lists) + (v.sanctions[0].programme ? ' · ' + esc(v.sanctions[0].programme) : ''));
    } else if (names.length) {
      sanc = kv('Sanctions', 'Not listed', `${esc(joined)}${checked ? `, checked ${Date.now() - checked < 90e3 ? 'just now' : esc(Fmt.dayTime(checked))}` : ''}`);
    } else sanc = kv('Sanctions', '<span class="c2">Not checked yet</span>', 'The server hasn’t downloaded the lists yet');
    const ex = (v.exNames || []).filter(n => n !== v.name);
    const rows = [sanc,
      kv('Name', esc(v.name), since(last('name'), ex.length ? 'Formerly ' + esc(ex.join(', ')) : '')),
      v.flag ? kv('Flag', esc(v.flag), since(last('flag'))) : '',
      v.mmsi ? kv('MMSI', `<span class="num selectable">${esc(v.mmsi)}</span>`, since(last('mmsi'))) : '',
      v.callsign ? kv('Call sign', `<span class="selectable">${esc(v.callsign)}</span>`) : ''];
    return `<div class="sec-h"><h2>Identity and sanctions</h2></div><div class="group">${rows.join('')}</div>`;
  },
  particularsHtml(a) {
    const v = a.vessel;
    const facts = [
      v.dwt ? ['Deadweight', `${Fmt.n(v.dwt)} t`] : null,
      v.loa ? ['Length × beam', `${Math.round(v.loa)}${v.beam ? ' × ' + Math.round(v.beam) : ''} m`] : null,
      v.built ? ['Built', `${v.built}${v.builder ? ', ' + v.builder : ''}`] : null,
      v.gt ? ['Gross tonnage', Fmt.n(v.gt)] : null,
    ].filter(Boolean);
    const who = [['Registered owner', v.regOwner], ['Beneficial owner', v.benOwner], ['ISM manager', v.ism], ['Operator', v.operator], ['Class', v.classSoc], ['P&I insurer', v.pi]].filter(x => x[1]);
    let h = `<div class="sec-h"><h2>Ship</h2></div>`;
    h += facts.length ? `<div class="facts">${facts.map(([k, val]) => `<div class="fact"><div class="k">${k}</div><div class="v">${esc(val)}</div></div>`).join('')}</div>`
      : `<p class="sec-foot" style="margin-top:0">Size and build aren't in AIS data. A paid provider adds them.</p>`;
    h += `<div class="group" style="margin-top:8px">${who.length ? who.map(([k, val]) => `<div class="kv"><span class="k">${k}</span><span class="v">${esc(val)}</span></div>`).join('')
      : `<div class="kv"><span class="k">Owner, manager, class, insurer</span><span class="v c2">Not in AIS data</span></div>`}
      <a class="row rowtap accent" href="https://www.equasis.org/" target="_blank" rel="noopener"><span class="tx"><div class="t1">Look up IMO ${a.vessel.imo} in Equasis</div><div class="t3">Free registration. Owners, managers, inspections</div></span><span class="chev">${ICON.ext(15)}</span></a></div>`;
    return h;
  },
  notesHtml(imo, scope) {
    const all = S.notes.get(imo) || [];
    const list = scope ? all.filter(n => n.scope === scope) : all;
    const ctx = n => {
      if (scope || n.scope === 'ship') return '';
      if (n.scope.startsWith('voyage:')) { const a = this.cur.a; const v = a && (a.voyages || []).find(x => `voyage:${x.n}` === n.scope); if (v) { const nm = this.voyName(a, v); return `On the voyage ${nm.from} → ${nm.to}`; } return 'On a voyage'; }
      if (n.scope.startsWith('flag:')) { const a = this.cur.a; const f = a && (a.flags || []).find(x => `flag:${x.key}` === n.scope); return f && f.story ? `On “${f.story.title}”` : 'On a finding'; }
      return '';
    };
    const card = n => `<button class="note rowtap" style="display:block;width:calc(100% - 2 * var(--edge));text-align:left" data-act="note-open" data-id="${n.id}">
      <div class="nh"><span><span class="b" style="color:var(--text)">${esc(n.author)}</span> · ${esc(Fmt.ago(n.updated || n.created))}${n.updated && n.updated - n.created > 60e3 ? ', edited' : ''}</span>${n.canEdit ? `<span class="c3">${ICON.pencil(14)}</span>` : ''}</div>
      <div class="nt">${esc(n.text)}</div>${ctx(n) ? `<span class="ctx">${esc(ctx(n))}</span>` : ''}</button>`;
    const sc = scope || 'ship';
    return `<div class="sec-h"><h2>Team notes</h2><button class="act" data-act="note-add" data-scope="${esc(sc)}">Add note</button></div>
      ${list.length ? list.map(card).join('') : `<p class="sec-foot" style="margin-top:0">${scope ? 'No notes here yet.' : 'No notes yet.'} Your team sees notes, and they're printed in the PDF report.</p>`}`;
  },
  crossResult() {
    const r = this.xc;
    if (!r) return '';
    if (r.loading) return `<p class="sec-foot"><span class="spin" style="display:inline-block;width:12px;height:12px;vertical-align:-1px;margin-right:6px"></span>Asking Global Fishing Watch…</p>`;
    if (!r.ok) return `<p class="sec-foot">${esc(r.error || 'The cross-check failed.')}</p>`;
    const ev = r.events || [];
    return `<div class="group" style="margin-top:8px">${r.matches && r.matches.length ? `<div class="kv"><span class="k">Their record</span><span class="v">${esc(r.matches.map(m => m.name).filter(Boolean).slice(0, 2).join(', ') || 'Found')}<div class="s">${r.matches.length} identity ${r.matches.length === 1 ? 'record' : 'records'}</div></span></div>` : `<div class="kv"><span class="k">Their record</span><span class="v c2">${esc(r.note || 'Not found')}</span></div>`}
      ${ev.slice(0, 12).map(e => `<div class="kv"><span class="k">${esc(e.label)}</span><span class="v">${esc(Fmt.range(e.t0, e.t1))}${e.detail ? `<div class="s">${esc(e.detail)}</div>` : ''}</span></div>`).join('')}
      ${ev.length > 12 ? `<div class="kv"><span class="k c2">And ${ev.length - 12} more</span></div>` : ''}${r.errors && r.errors.length ? `<div class="kv"><span class="k c2">Some lookups failed</span><span class="v c2">${r.errors.length}</span></div>` : ''}</div>
      <p class="sec-foot">${esc(r.licence || 'CC BY-NC 4.0, non-commercial use only')}. A cross-check only: MarineEdge never uses it as a source for findings.</p>`;
  },
  crossHtml() {
    return `<div class="sec-h"><h2>Cross-check</h2></div><div class="group"><button class="row ic rowtap" data-act="xcheck"><span class="itile" style="background:#0E8C9E">${ICON.globe(18)}</span>
      <span class="tx"><div class="t1">Compare with Global Fishing Watch</div><div class="t2">Their own AIS record: gaps, port visits, encounters</div></span><span class="chev">${ICON.chev(14)}</span></button></div><div id="xcBox">${this.crossResult()}</div>`;
  },
  actionsHtml(a) {
    return `<div class="actions2"><button class="btn secondary" id="watchBtn" data-act="watch"></button><button class="btn secondary" data-act="report"><span class="lbl" style="display:flex;align-items:center;gap:8px">${ICON.doc(18)}Report</span></button></div>`;
  },
  footHtml(a) {
    const from = a.verdict && a.verdict.historyFrom;
    const src = (a.stats && a.stats.source) || '';
    const bought = a.history && a.history.bought;
    const srcLine = /aisstream/i.test(src) ? `Positions from your server's recording of aisstream.io's free feed, which hears ships near the coast${bought ? `, plus 12 months bought from ${a.history.provider}` : ''}. Quiet periods where no receiver can hear are not counted as going dark.`
      : /mock/i.test(src) ? 'Demo positions generated on this machine.' : src ? `Positions from ${src}, kept on your server.` : '';
    return `<p class="foot-note" style="margin-top:22px">From ${Fmt.n(a.positions || 0)} positions${from ? `, ${Fmt.day(from, true)} to today` : ''}. ${DRAUGHT_NOTE}</p>${srcLine ? `<p class="foot-note" style="margin-top:8px">${esc(srcLine)}</p>` : ''}`;
  },

  /* ================================================================ voyage page */
  async ensureShipFor(imo) {
    if (this.cur.imo === imo && this.cur.a) return this.cur.a;
    this.cur = { imo, a: null };
    const [a] = await Promise.all([this.load(imo), S.notes.has(imo) ? null : this.loadNotes(imo)]);
    if (this.cur.imo === imo) { this.cur.a = a; this.renderShip(a); }
    return a;
  },
  pageOpen(kind, key, { detent = 'full', modal = true } = {}) {
    this.dropMini();
    this.pageKind = kind; this.pageKey = key;
    $('#voyTools').hidden = kind !== 'voyage';
    $('#pageSheet').classList.toggle('has-tools', kind === 'voyage');
    this.page.detentAllowed = n => (wide() ? n === 'full' : modal ? n === 'full' : true);
    $('#dim2').classList.toggle('on', modal);
    $('#pageSheet').setAttribute('aria-modal', modal ? 'true' : 'false');
    this.page.snap(detent);
    this.layoutAttr();
  },
  pageLoading(title) {
    $('#pageHead').innerHTML = `<div class="nav"><span style="width:32px"></span><div class="ttl">${esc(title || '')}</div><button class="cbtn lg" data-act="close-page" aria-label="Close">${ICON.x(14)}</button></div>`;
    $('#pageBody').innerHTML = `<div class="empty"><span class="spin" style="margin:0 auto;color:var(--text-2)"></span></div>`;
  },
  async showVoyage(imo, n, prev = {}) {
    if (this.home.shown) this.home.hide();
    $('#homeSheet').classList.remove('searching', 'back'); $('#dim1').classList.remove('on');
    $('#shipSheet').classList.remove('back');
    if (this.ship.shown) this.ship.hide();
    S.view = 'voyage';
    this.chrome('voyage');
    MapView.showLive(false);
    const wasVoyage = this.pageKind === 'voyage';
    if (!this.cur.a || this.cur.imo !== imo) this.pageLoading('Voyage');
    this.pageOpen('voyage', n, { detent: wasVoyage && this.page.pos ? this.page.pos : 'half', modal: false });
    let a;
    try { a = await this.ensureShipFor(imo); } catch (e) { this.pageError(e); return; }
    if (S.route.name !== 'voyage' || S.route.imo !== imo) return;
    const v = (a.voyages || []).find(x => x.n === n);
    this.renderVoyage(a, v);
    MapView.setShip(a, { sel: v ? v.n : null });
    if (v) this.fitVoyage(a, v, true);
  },
  fitVoyage(a, v, animate) {
    const pts = (a.track || []).slice(v.i0, v.i1 + 1).filter(p => !p.jump);
    const b = boundsOf(pts); if (!b) return;
    MapView.fit(b, { duration: animate ? 820 : 0, maxZoom: 9, padding: this.mapPad(this.page) });
  },
  renderVoyage(a, v) {
    const imo = a.vessel.imo;
    const vs = a.voyages || [];
    if (!v) {
      $('#pageHead').innerHTML = `<div class="nav"><span style="width:32px"></span><div class="ttl">Voyage</div><button class="cbtn lg" data-act="close-page" aria-label="Close">${ICON.x(14)}</button></div>`;
      $('#pageBody').innerHTML = `<div class="empty"><h3>That voyage isn't in the last 12 months any more</h3><p>Voyages are re-numbered as old ones drop out of the twelve-month window.</p></div>`;
      return;
    }
    const idx = vs.indexOf(v);
    const { from, to } = this.voyName(a, v);
    $('#pageHead').innerHTML = `<div class="nav">
      <button class="cbtn lg" data-act="voy-step" data-d="-1" aria-label="Earlier voyage" ${idx <= 0 ? 'disabled style="opacity:.35"' : ''}><span style="transform:rotate(180deg);display:flex">${ICON.chev(14)}</span></button>
      <div class="ttl">Voyage ${idx + 1} of ${vs.length}</div>
      <button class="cbtn lg" data-act="voy-step" data-d="1" aria-label="Later voyage" ${idx >= vs.length - 1 ? 'disabled style="opacity:.35"' : ''}>${ICON.chev(14)}</button></div>`;
    const renamed = (a.vessel.history || []).filter(h => h.field === 'name' && h.t > v.depart).sort((x, y) => x.t - y.t)[0];
    const byId = Object.fromEntries((a.flags || []).map(f => [f.id, f]));
    const fl = (v.flags || []).map(id => byId[id]).filter(Boolean).sort((x, y) => x.t0 - y.t0);
    const dIn = v.draughtIn, dOut = v.draughtOut;
    const dChanged = dIn && dOut && Math.abs(dIn - dOut) >= 1 && fl.some(isDraught);
    const P = PAL[S.theme] || PAL.dark;
    let h = `${renamed ? `<p class="t-sub c2" style="margin:2px 20px 0">Sailing as ${esc(renamed.from)}, now ${esc(a.vessel.name)}</p>` : ''}
      <h1 class="t-title2 voy-title"><span class="vsw" style="background:${P.voyages[v.color % 8]}"></span>${esc(from)} → ${esc(to)}</h1>
      <div class="route"><div class="ports">
        <div class="port"><div class="d">Departed</div><div class="n">${esc(from)}</div><div class="d">${esc(Fmt.dayTime(v.depart))}</div></div>
        <div class="arrow">${ICON.arrowR(18)}</div>
        <div class="port r"><div class="d">${v.current ? 'Heading for' : 'Arrived'}</div><div class="n">${esc(to)}</div><div class="d">${v.arrive ? esc(Fmt.dayTime(v.arrive)) : 'Under way now'}</div></div></div></div>
      <div class="facts" style="margin-top:8px">
        <div class="fact"><div class="k">${v.current ? 'So far' : 'Took'}</div><div class="v">${dh((v.arrive || Date.now()) - v.depart)}</div></div>
        <div class="fact"><div class="k">Distance</div><div class="v">${Fmt.nm(v.nm)}</div></div>
        <div class="fact"><div class="k">Draught</div><div class="v">${dOut ? `${(+dOut).toFixed(1)} → ${dChanged ? `<span class="c-red">${(+dIn).toFixed(1)}</span>` : dIn ? (+dIn).toFixed(1) : '—'} m` : '—'}</div></div>
        <div class="fact"><div class="k">AIS off</div><div class="v ${v.darkH ? 'c-red' : ''}">${v.darkH ? Fmt.hours(v.darkH) : 'Never'}</div></div></div>
`;
    $('#voyTools').innerHTML = `<button data-act="voy-map">${ICON.map(17)}Show on map</button><button data-act="note-add" data-scope="voyage:${v.n}">${ICON.note(17)}Add note</button><button data-act="report">${ICON.doc(17)}PDF</button>`;
    h += `<div class="sec-h"><h2>On this voyage</h2></div>`;
    h += fl.length ? `<div class="group">${fl.map(f => {
      const st = f.story || { title: f.title, text: '' };
      return `<button class="row rowtap" data-go="#/ship/${imo}/finding/${encodeURIComponent(f.key)}"><span class="sev ${f.severity}"></span><span class="tx"><div class="t1 b">${esc(st.title)}</div><div class="t2">${esc(Fmt.range(f.t0, f.t1))} · ${esc(st.text)}</div></span><span class="chev">${ICON.chev(14)}</span></button>`;
    }).join('')}</div>` : `<div class="group"><div class="row"><span style="color:var(--green)">${ICON.check(18)}</span><span class="tx"><div class="t1">Nothing found on this voyage</div></div></div></div>`;
    const calls = [v.from, v.to].filter(Boolean);
    if (calls.length) {
      h += `<div class="sec-h"><h2>Port calls</h2></div><div class="group">${calls.map(pc => `<div class="kv"><span class="k">${esc(pc.port.name)}${pc.port.c ? `, ${esc(pc.port.c)}` : ''}</span><span class="v">${esc(Fmt.range(pc.arrive, pc.depart))}<div class="s">${pc.anchorage ? 'At anchor' : 'Alongside'} ${esc(dh(pc.depart - pc.arrive))}${pc.draughtIn ? ` · draught ${pc.draughtIn} → ${pc.draughtOut} m` : ''}${pc.port.zone ? ' · sensitive zone' : ''}</div></span></div>`).join('')}</div>`;
    }
    h += `<div id="notesPage">${this.notesHtml(imo, `voyage:${v.n}`)}</div>`;
    if (dIn || dOut) h += `<p class="foot-note">${DRAUGHT_NOTE}</p>`;
    $('#pageBody').innerHTML = h;
    $('#pageBody').scrollTop = 0;
  },

  /* ================================================================ finding page */
  async showFinding(imo, key, prev = {}) {
    if (this.home.shown) this.home.hide();
    $('#homeSheet').classList.remove('searching'); $('#dim1').classList.remove('on');
    const overShip = this.ship.shown && this.cur.imo === imo;
    $('#shipSheet').classList.toggle('back', overShip);
    S.view = 'finding';
    this.chrome('none');
    if (!this.cur.a || this.cur.imo !== imo) this.pageLoading('Finding');
    this.pageOpen('finding', key, { detent: 'full', modal: true });
    let a;
    try { a = await this.ensureShipFor(imo); if (!S.rules) S.rules = (await API.rules().catch(() => ({ rules: {} }))).rules; } catch (e) { this.pageError(e); return; }
    if (S.route.name !== 'finding' || this.pageKey !== key) return;
    const f = (a.flags || []).find(x => x.key === key);
    this.renderFinding(a, f, key);
    MapView.setShip(a, { flagKey: key, sel: f ? f.voyage : null });
  },
  renderFinding(a, f, key) {
    const imo = a.vessel.imo;
    $('#pageHead').innerHTML = `<div class="nav"><button class="btn plain" data-act="note-add" data-scope="flag:${esc(key)}" ${f ? '' : 'hidden'}>Add note</button><div class="ttl"></div><button class="cbtn lg" data-act="close-page" aria-label="Close">${ICON.x(14)}</button></div>`;
    if (!f) {
      $('#pageBody').innerHTML = `<div class="empty"><div class="ei">${ICON.info(24)}</div><h3>This finding is no longer there</h3><p>The latest check of ${esc(a.vessel.name)} doesn't find it any more, for example after a rule threshold or a zone changed.</p><button class="btn small tinted" style="margin-top:14px" data-go="#/ship/${imo}">Open ${esc(a.vessel.name)}</button></div>`;
      return;
    }
    const st = f.story || { title: f.title, text: (f.lines || [])[0] || '' };
    const sevCls = f.severity === 'high' ? 'high' : f.severity === 'medium' ? 'review' : 'none';
    const sevIcon = f.severity === 'high' ? ICON.excl(13) : f.severity === 'medium' ? ICON.tri(13) : ICON.dashc(13);
    const ev = f.evidence || { before: [], after: [] };
    const pts = [...(ev.before || []), ...(ev.after || [])];
    const hasMap = (f.lat != null || pts.length) && typeof maplibregl !== 'undefined';
    let h = `<div style="display:flex;align-items:center;gap:10px;margin:4px 20px 0"><span class="vb ${sevCls}">${sevIcon}${SEV_LABEL[f.severity] || f.severity}${f.severity === 'info' ? ', not counted' : ''}</span><span class="t-foot c2">${esc(f.rule)}</span></div>
      <h1 class="t-title" style="margin:12px 20px 0">${esc(st.title)}</h1>
      <p class="prose">${esc(st.text)}</p>`;
    if (f.voyage != null) {
      const v = (a.voyages || []).find(x => x.n === f.voyage);
      if (v) { const nm = this.voyName(a, v); h += `<div class="group" style="margin-top:14px"><button class="row rowtap" data-go="#/ship/${imo}/voyage/${v.n}"><span class="vsw" style="background:${(PAL[S.theme] || PAL.dark).voyages[v.color % 8]}"></span><span class="tx"><div class="t1">${esc(nm.from)} → ${esc(nm.to)}</div><div class="t2">${esc(Fmt.range(v.depart, v.arrive))} · the voyage it happened on</div></span><span class="chev">${ICON.chev(14)}</span></button></div>`; }
    }
    if (hasMap) h += `<div class="minimap"><div class="mm" id="mm" aria-label="Map of the positions around this finding" role="img"></div><button class="pill-btn go" data-act="finding-map">${ICON.map(16)}Show on map</button></div>`;
    if (pts.length) {
      const mark = new Set();
      const nb = (ev.before || []).length;
      if (f.rule === 'AIS gap' || f.rule === 'Draught change at sea') { if (nb) mark.add(nb - 1); if ((ev.after || []).length) mark.add(nb); }
      else if (f.rule === 'Position jump') { if ((ev.after || []).length) mark.add(nb); }
      const multiDay = pts.length > 1 && Fmt.parts(pts[0].t).d !== Fmt.parts(pts[pts.length - 1].t).d;
      h += `<div class="sec-h"><h2>Positions before and after</h2></div><div class="evtable selectable" role="table">
        <div class="er hd" role="row"><span>${Fmt.utc ? 'UTC' : 'Time'}</span><span>Position</span><span>Speed</span><span>Draught</span></div>
        ${pts.map((p, i) => `<div class="er ${mark.has(i) ? 'mark' : ''}" role="row"><span>${esc(multiDay ? `${Fmt.parts(p.t).d} ${MON[Fmt.parts(p.t).m]} ${Fmt.time(p.t)}` : Fmt.time(p.t))}</span><span>${esc(Fmt.dm(p.lat, p.lon))}</span><span>${p.sog != null ? Number(p.sog).toFixed(1) + ' kn' : '—'}</span><span>${p.draught ? p.draught + ' m' : '—'}</span></div>`).join('')}</div>`;
    }
    if (f.lines && f.lines.length) h += `<div class="sec-h"><h2>The record</h2></div><div class="group">${f.lines.map(l => `<div class="kv"><span class="v selectable" style="text-align:left;font-size:0.882rem">${esc(l)}</span></div>`).join('')}</div>`;
    if (f.partnerImo) h += `<div class="group" style="margin-top:8px"><button class="row ship rowtap" data-go="#/ship/${f.partnerImo}"><span class="ship-ic">${ICON.ship(20)}</span><span class="tx"><div class="t1 b">${esc((f.meta && f.meta.partner) || 'The other ship')}</div><div class="t2">IMO ${f.partnerImo} · open its year</div></span><span class="chev">${ICON.chev(14)}</span></button></div>`;
    const rt = ruleText(f.rule);
    h += `<div class="rulebox"><div class="k">The rule</div>${esc(rt)}${isDraught(f) ? ' ' + DRAUGHT_NOTE : ''}${f.rule === 'AIS gap' && f.severity === 'info' ? ' This one fell outside receiver coverage, so it is shown for completeness and not counted.' : ''}</div>`;
    h += `<div id="notesPage">${this.notesHtml(imo, `flag:${key}`)}</div>`;
    $('#pageBody').innerHTML = h;
    $('#pageBody').scrollTop = 0;
    if (hasMap) {
      const mark = f.lat != null ? [{ lon: f.lon, lat: f.lat, k: 'mark' }] : [];
      const all = [...pts.map(p => ({ lon: p.lon, lat: p.lat, k: 'pos' })), ...mark];
      let b = boundsOf(all); const pad = 0.12;
      if (b) b = [b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad];
      setTimeout(() => {
        if (this.pageKey !== key || !$('#mm')) return;
        this.dropMini();
        try { this.mini = miniMap($('#mm'), { theme: S.theme, detailUrl: S.maps && S.maps.installed ? S.maps.url : null, bounds: b, track: pts, points: all, zones: S.zones }); } catch (e) { $('#mm').parentElement.hidden = true; }
      }, reduceMotion() ? 0 : 380);
    }
  },
  pageError(e) {
    $('#pageBody').innerHTML = `<div class="empty"><div class="ei">${ICON.warn(24)}</div><h3>${e.status === 404 ? 'No data for this ship yet' : "Couldn't open this"}</h3><p>${esc(e.message)}</p><button class="btn small tinted" style="margin-top:14px" data-act="close-page">Close</button></div>`;
  },

  /* ================================================================ alerts and lists */
  async showAlerts(prev = {}) {
    this.modalOverCurrent();
    this.pageOpen('alerts', null, { detent: 'full', modal: true });
    $('#pageHead').innerHTML = `<div class="nav"><span style="width:36px"></span><div class="ttl">Alerts</div><button class="cbtn lg" data-act="close-page" aria-label="Close">${ICON.x(14)}</button></div>`;
    $('#pageBody').innerHTML = `<div class="empty"><span class="spin" style="margin:0 auto;color:var(--text-2)"></span></div>`;
    let d;
    try { d = await API.alerts(30); } catch (e) { this.pageError(e); return; }
    if (this.pageKind !== 'alerts') return;
    this.alertItems = d.items || [];
    const items = this.alertItems;
    let h = '';
    if (!items.length) {
      const pushOn = await Profile.pushState().catch(() => 'off');
      h = `<div class="empty" style="margin-top:50px"><div class="ei">${ICON.bell(24)}</div><h3>No alerts in the last 30 days</h3>
        <p>${d.watching ? `You watch ${Fmt.plural(d.watching, 'ship')}. MarineEdge checks ${d.watching === 1 ? 'it' : 'them'} again every 30 minutes and lists every new red flag here.` : 'Watch a ship (the star on its page) and MarineEdge checks it every 30 minutes. New red flags appear here.'}</p>
        ${pushOn !== 'on' && S.me.push && S.me.push.configured ? `<button class="btn small tinted" style="margin-top:16px" data-go="#/profile/notifications">Get them on this iPhone</button>` : ''}</div>`;
    } else {
      let day = null; h += '<div style="height:6px"></div>';
      const groups = [];
      items.forEach((al, i) => { const dd = Fmt.day(al.created_at, true); if (dd !== day) { groups.push({ dd, rows: [] }); day = dd; } groups[groups.length - 1].rows.push([al, i]); });
      const today = Fmt.day(Date.now(), true), yest = Fmt.day(Date.now() - DAY, true);
      h += groups.map(g => `<p class="sec-cap">${g.dd === today ? 'Today' : g.dd === yest ? 'Yesterday' : esc(g.dd)}</p><div class="group">${g.rows.map(([al, i]) => `<button class="row alert-row rowtap ${al.unread ? 'unread' : ''}" data-act="open-alert" data-i="${i}"><span class="sev ${al.severity}"></span>
        <span class="tx"><div class="t1 b">${esc(al.title)}</div><div class="t2">${esc(al.detail || '')}</div></span><span class="when">${esc(Fmt.time(al.created_at))}</span></button>`).join('')}</div>`).join('');
      h += `<p class="sec-foot" style="margin-top:14px">New red flags on the ships you watch, from the checks every 30 minutes.</p>`;
    }
    $('#pageBody').innerHTML = h;
    if (S.me && S.me.unread) { API.alertsSeen().then(() => { S.me.unread = 0; App.renderBadge(); }).catch(() => {}); }
  },
  modalOverCurrent() {
    // a full-height page over whatever is showing: the sheet underneath steps back
    $('#dim1').classList.remove('on'); $('#homeSheet').classList.remove('searching');
    if (document.activeElement === this.qEl) this.qEl.blur();
    if (this.ship.shown) $('#shipSheet').classList.add('back');
    else { if (!this.home.shown) { MapView.clearShip(); MapView.showLive(true); this.home.snap(this.homeDetent === 'full' ? 'half' : this.homeDetent); if (!$('#homeMain').innerHTML) this.renderHome(); } $('#homeSheet').classList.add('back'); }
    this.chrome('none');
    if (!this.ship.shown) S.view = 'home';
  },
  async showList(kind, prev = {}) {
    this.modalOverCurrent();
    this.pageOpen('list', kind, { detent: 'full', modal: true });
    const title = kind === 'sanctioned' ? 'On sanctions lists' : 'High risk';
    $('#pageHead').innerHTML = `<div class="nav"><span style="width:36px"></span><div class="ttl">${title}</div><button class="cbtn lg" data-act="close-page" aria-label="Close">${ICON.x(14)}</button></div>`;
    if (!S.live.length) $('#pageBody').innerHTML = `<div class="empty"><span class="spin" style="margin:0 auto;color:var(--text-2)"></span></div>`;
    try { S.live = await API.live(S.region); MapView.setLive(S.live); } catch (e) { if (!S.live.length) { this.pageError(e); return; } }
    if (this.pageKind !== 'list') return;
    const rows = S.live.filter(r => kind === 'sanctioned' ? r.sanctioned : r.level === 'high').sort((x, y) => (y.sanctioned - x.sanctioned) || (y.t - x.t));
    $('#pageBody').innerHTML = `<p class="lead" style="padding:0 20px;margin:2px 0 4px;color:var(--text-2);font-size:0.882rem">${Fmt.plural(rows.length, 'ship')} in ${esc(REGION_NAME[S.region])}, heard in the last 6 hours.</p>
      ${rows.length ? `<div class="group" style="margin-top:12px">${rows.map(r => this.liveRow(r)).join('')}</div>` : `<div class="empty"><h3>None right now</h3><p>Ships come and go as receivers hear them.</p></div>`}
      <p class="sec-foot" style="margin-top:14px">${kind === 'sanctioned' ? 'IMO numbers on the OFAC, EU or UK lists the server downloads every day.' : 'High risk: on a sanctions list, or at least one High finding in the last 12 months.'}</p>`;
  },

  /* ================================================================ actions */
  async act(act, el) {
    const a = this.cur.a;
    switch (act) {
      case 'noop': return;
      case 'clear-q': this.qEl.value = ''; this.onSearchInput(); this.qEl.focus(); return;
      case 'cancel-search': this.qEl.value = ''; this.q = ''; this.results = null; this.qClear.hidden = true; this.qEl.blur(); if (S.route.name === 'search') App.back('#/'); return;
      case 'open-ship': return this.openShip(+el.dataset.imo, el.dataset.name);
      case 'recent-clear': store.del('recent'); this.renderResults(); return;
      case 'home-retry': this.homeErr = null; this.renderHome(); return this.refreshHome(true);
      case 'see-map': return this.home.snap('peek');
      case 'save-ais': return this.saveAisKey(el);
      case 'retry-ship': { const imo = this.cur.imo; this.cur = { imo: null }; return this.showShip(imo, {}); }
      case 'fit-all': if (wide()) return this.fitShip(true); this.ship.snap('peek'); setTimeout(() => this.fitShip(true), 80); return;
      case 'voy-more': this.expand.voy = !this.expand.voy; if (a) this.renderShip(a); return;
      case 'tl-info': this.expand.info = true; if (a) { this.renderShip(a); } return;
      case 'watch': if (this.cur.imo) return this.toggleWatch(this.cur.imo); return;
      case 'report': if (a) return this.report(a.vessel.imo, a.vessel.name, el.classList.contains('btn') ? el : null); return;
      case 'xcheck': return this.crossCheck();
      case 'buy-history': return this.buyHistory(el);
      case 'close-page': return App.back();
      case 'voy-map': {
        const v = a && (a.voyages || []).find(x => x.n === this.pageKey); if (!v) return;
        if (!wide()) this.page.snap('peek');
        setTimeout(() => this.fitVoyage(a, v, true), 60); return;
      }
      case 'voy-step': {
        if (!a) return; const vs = a.voyages || []; const i = vs.findIndex(x => x.n === this.pageKey) + (+el.dataset.d);
        if (i >= 0 && i < vs.length) App.go(`#/ship/${a.vessel.imo}/voyage/${vs[i].n}`, { replace: true }); return;
      }
      case 'finding-map': S.focusFlag = this.pageKey; App.go(`#/ship/${this.cur.imo}`, { replace: true }); return;
      case 'open-alert': return this.openAlert(this.alertItems[+el.dataset.i], el);
      case 'note-add': return this.compose({ imo: this.cur.imo, scope: el.dataset.scope || 'ship' });
      case 'note-open': {
        const n = (S.notes.get(this.cur.imo) || []).find(x => String(x.id) === el.dataset.id); if (!n) return;
        if (!n.canEdit && !n.canDelete) { toast(`Only ${n.author} can change this note.`); return; }
        return this.compose({ imo: this.cur.imo, scope: n.scope, note: n });
      }
      case 'comp-cancel': return this.compCancel();
      case 'comp-save': return this.compSave(el);
      case 'comp-delete': return this.compDelete(el);
      default: return;
    }
  },

  async saveAisKey(btn) {
    const k = ($('#aisKey') || {}).value ? $('#aisKey').value.trim() : '';
    if (k.length < 20) { toast('Paste the whole key from aisstream.io first.', 'err'); return; }
    await busy(btn, async () => {
      try {
        await API.setKey('aisstream', k);
        S.me = await API.me(); App.renderBadge();
        toast('Saved. Recording starts within a minute.', 'ok');
        this.renderHome(); this.renderLiveChip();
        setTimeout(() => this.refreshHome(true), 30000);
      } catch (e) { toast(e.message, 'err'); }
    });
  },

  async toggleWatch(imo) {
    const list = (S.me && S.me.watchlist) || [];
    const on = list.includes(imo);
    const next = on ? list.filter(i => i !== imo) : [...list, imo];
    const name = (this.cur.a && this.cur.a.vessel.imo === imo) ? this.cur.a.vessel.name : `IMO ${imo}`;
    S.me.watchlist = next; this.renderWatch(imo);
    try {
      const r = await API.setWatchlist(next); S.me.watchlist = r.watchlist; this.renderWatch(imo);
      S.watching = (S.watching || []).filter(w => w.imo !== imo || !on); this.homeAt = 0;
      if (on) { toast(`Stopped watching ${name}.`); return; }
      const ps = await Profile.pushState().catch(() => 'off');
      if (ps === 'off' && S.me.push && S.me.push.configured && 'Notification' in window && Notification.permission === 'default') {
        const ok = await actionSheet({ title: `Watching ${name}`, message: 'MarineEdge checks it every 30 minutes. Get a notification on this device when it finds a new red flag?', actions: [{ label: 'Turn on notifications', bold: true, value: 'yes' }], cancel: 'Not now' });
        if (ok === 'yes') Profile.enablePush();
      } else toast(`Watching ${name}. New red flags show up in Alerts.`, 'ok');
    } catch (e) { S.me.watchlist = list; this.renderWatch(imo); toast(e.message, 'err'); }
  },

  async more() {
    const a = this.cur.a; if (!a) return;
    const v = await actionSheet({ title: a.vessel.name, message: `IMO ${a.vessel.imo}`, actions: [
      { label: 'PDF report', value: 'report', bold: true }, { label: 'Copy link to this ship', value: 'link' },
      { label: 'Copy IMO number', value: 'imo' }, { label: 'Check again now', value: 'recheck' }] });
    if (v === 'report') this.report(a.vessel.imo, a.vessel.name, null);
    else if (v === 'link') { const ok = await copyText(`${location.origin}${location.pathname}#/ship/${a.vessel.imo}`); toast(ok ? 'Link copied. Teammates open it with their own MarineEdge account.' : "Couldn't copy the link.", ok ? 'ok' : 'err'); }
    else if (v === 'imo') { const ok = await copyText(String(a.vessel.imo)); toast(ok ? 'IMO number copied.' : "Couldn't copy.", ok ? 'ok' : 'err'); }
    else if (v === 'recheck') this.recheck();
  },
  async recheck() {
    const imo = this.cur.imo; if (!imo) return;
    toast('Checking again…');
    try {
      const a = await this.load(imo, { refresh: true }); await this.loadNotes(imo);
      if (this.cur.imo !== imo) return;
      this.cur.a = a; this.renderShip(a); MapView.setShip(a);
      toast('Checked again just now.', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  },

  async report(imo, name, btn) {
    const run = async () => {
      let blob;
      if (!btn) toast('Making the PDF report…');
      try {
        const r = await fetch(API.reportUrl(imo), { credentials: 'same-origin' });
        if (r.status === 401) { if (API.onSignedOut) API.onSignedOut(); return; }
        if (!r.ok) { let msg = `The report couldn't be made (${r.status}).`; try { const j = await r.json(); msg = j.detail || msg; } catch (e) { /* not json */ } throw new Error(msg); }
        blob = await r.blob();
      } catch (e) { toast(e.message && !/fetch/i.test(e.message) ? e.message : 'No connection to the server.', 'err'); return; }
      const fname = `MarineEdge-${String(name || 'ship').replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '')}-${imo}.pdf`;
      let file = null; try { file = new File([blob], fname, { type: 'application/pdf' }); } catch (e) { file = null; }
      const canShare = !!(file && navigator.canShare && navigator.canShare({ files: [file] }));
      const choice = await actionSheet({ title: 'Report ready', message: `${fname} · ${Fmt.bytes(blob.size)}`, actions: [canShare ? { label: 'Share or save…', bold: true, value: 'share' } : { label: 'Download', bold: true, value: 'download' }, { label: 'Open', value: 'open' }] });
      if (choice === 'share') { try { await navigator.share({ files: [file], title: `${name} · MarineEdge report` }); } catch (e) { /* cancelled */ } }
      else if (choice === 'download' || choice === 'open') {
        const url = URL.createObjectURL(blob); const lnk = document.createElement('a'); lnk.href = url; lnk.rel = 'noopener';
        if (choice === 'download') lnk.download = fname; else lnk.target = '_blank';
        document.body.appendChild(lnk); lnk.click(); lnk.remove(); setTimeout(() => URL.revokeObjectURL(url), 120000);
      }
    };
    return btn ? busy(btn, run) : run();
  },

  async crossCheck() {
    const imo = this.cur.imo; if (!imo || (this.xc && this.xc.loading)) return;
    this.xc = { loading: true };
    const show = () => { const box = $('#xcBox'); if (box) box.innerHTML = this.crossResult(); };
    show();
    try { this.xc = await API.crosscheck(imo); } catch (e) { this.xc = { ok: false, error: e.message }; }
    if (this.cur.imo !== imo) return;
    show();
  },

  async buyHistory(btn) {
    const a = this.cur.a; if (!a) return;
    const prov = titleCase((a.history && a.history.provider) || 'the provider');
    const ok = await actionSheet({ title: `Buy 12 months for ${a.vessel.name}?`, message: `${prov} charges credits for the positions it sends. They're bought once, kept on your server, and never fetched twice.`, actions: [{ label: 'Buy 12 months', bold: true, value: 'yes' }] });
    if (ok !== 'yes') return;
    await busy(btn, async () => {
      try {
        const r = await API.buyHistory(a.vessel.imo);
        toast(r.already ? 'Already bought. Nothing was charged.' : `Added ${Fmt.n(r.bought)} positions${r.credits ? ` for ${r.credits} credits` : ''}.`, 'ok');
        const fresh = await this.load(a.vessel.imo, { refresh: true });
        if (this.cur.imo !== a.vessel.imo) return;
        this.cur.a = fresh; this.renderShip(fresh); MapView.setShip(fresh); this.fitShip(true);
      } catch (e) { toast(e.message, 'err'); }
    });
  },

  async openAlert(al, row) {
    if (!al) return;
    await busy(row, async () => {
      try {
        const a = await this.load(al.imo);
        const f = (a.flags || []).find(x => x.rule === al.rule && Math.floor(x.t0 / 3600e3) === Math.floor(al.t0 / 3600e3));
        this.cur = { imo: al.imo, a };
        if (!S.notes.has(al.imo)) await this.loadNotes(al.imo);
        App.go(f ? `#/ship/${al.imo}/finding/${encodeURIComponent(f.key)}` : `#/ship/${al.imo}`);
      } catch (e) { toast(e.message, 'err'); }
    });
  },

  /* ================================================================ note composer */
  compose({ imo, scope, note = null }) {
    if (!imo) return;
    const a = this.cur.a;
    let label = 'On this ship';
    if (scope.startsWith('voyage:') && a) { const v = (a.voyages || []).find(x => `voyage:${x.n}` === scope); if (v) { const nm = this.voyName(a, v); label = `On the voyage ${nm.from} → ${nm.to}`; } }
    if (scope.startsWith('flag:') && a) { const f = (a.flags || []).find(x => `flag:${x.key}` === scope); if (f) label = `On “${(f.story && f.story.title) || f.title}”`; }
    $('#composerHead').innerHTML = `<div class="nav"><button class="btn plain" data-act="comp-cancel">Cancel</button><div class="ttl">${note ? 'Edit note' : 'New note'}</div><button class="btn plain b" data-act="comp-save" ${note && !note.canEdit ? 'hidden' : ''}><span class="lbl">${note ? 'Save' : 'Add'}</span></button></div>`;
    $('#composerBody').innerHTML = `<div style="padding:4px var(--edge) 0"><p class="t-foot c2" style="margin:0 4px 8px">${esc(label)} · ${esc(a ? a.vessel.name : 'IMO ' + imo)}</p>
      <textarea class="ta" id="noteText" maxlength="4000" placeholder="What should your team know?" ${note && !note.canEdit ? 'readonly' : ''}>${esc(note ? note.text : '')}</textarea>
      <p class="t-foot c2" style="margin:8px 4px 0">Your team sees notes with your name, and they're printed in the PDF report.</p>
      ${note && note.canDelete ? `<button class="btn danger" style="margin-top:24px" data-act="comp-delete"><span class="lbl">Delete note</span></button>` : ''}</div>`;
    this.compState = { imo, scope, note, orig: note ? note.text : '' };
    $('#dim3').classList.add('on');
    this.comp.snap('full');
    const ta = $('#noteText'); try { ta.focus({ preventScroll: true }); ta.setSelectionRange(ta.value.length, ta.value.length); } catch (e) { /* older browsers */ }
  },
  closeComposer(quick) {
    if (!this.compState) return;
    this.compState = null;
    $('#dim3').classList.remove('on');
    const ta = $('#noteText'); if (ta) ta.blur();
    this.comp.hide(!quick);
  },
  async compCancel() {
    const st = this.compState; if (!st) return;
    const ta = $('#noteText');
    if (ta && ta.value.trim() && ta.value.trim() !== (st.orig || '').trim()) {
      const v = await actionSheet({ actions: [{ label: 'Discard changes', destructive: true, value: 'discard' }], cancel: 'Keep editing' });
      if (v !== 'discard') { this.comp.snap('full'); return; }
    }
    this.closeComposer();
  },
  async compSave(btn) {
    const st = this.compState; if (!st) return;
    const text = $('#noteText').value.trim();
    if (!text) { toast('Write something first.', 'err'); return; }
    await busy(btn, async () => {
      try {
        const n = st.note ? await API.editNote(st.note.id, text) : await API.addNote(st.imo, st.scope, text);
        const list = (S.notes.get(st.imo) || []).filter(x => x.id !== n.id);
        list.unshift(n); S.notes.set(st.imo, list);
        this.closeComposer();
        this.refreshNotesUI();
        toast(st.note ? 'Note saved.' : 'Note added. Your team can see it.', 'ok');
      } catch (e) { toast(e.message, 'err'); }
    });
  },
  async compDelete(btn) {
    const st = this.compState; if (!st || !st.note) return;
    const v = await actionSheet({ title: 'Delete this note?', message: 'It disappears for the whole team.', actions: [{ label: 'Delete note', destructive: true, value: 'del' }] });
    if (v !== 'del') return;
    await busy(btn, async () => {
      try {
        await API.deleteNote(st.note.id);
        S.notes.set(st.imo, (S.notes.get(st.imo) || []).filter(x => x.id !== st.note.id));
        this.closeComposer(); this.refreshNotesUI(); toast('Note deleted.');
      } catch (e) { toast(e.message, 'err'); }
    });
  },
  refreshNotesUI() {
    const imo = this.cur.imo; if (!imo) return;
    const a = this.cur.a;
    if (a && $('#notesShip')) { this.renderShip(a); }
    const np = $('#notesPage');
    if (np) np.innerHTML = this.notesHtml(imo, this.pageKind === 'voyage' ? `voyage:${this.pageKey}` : this.pageKind === 'finding' ? `flag:${this.pageKey}` : null);
  },

  onTheme() {
    if (S.view === 'ship' && this.cur.a) this.renderShip(this.cur.a);
    if (this.pageKind === 'voyage' && this.cur.a) this.renderVoyage(this.cur.a, (this.cur.a.voyages || []).find(x => x.n === this.pageKey));
  },
};
