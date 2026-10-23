/* =====================================================================================
   Data source switch. `mock` runs the whole pipeline in the browser (no backend, no credits);
   `server` asks the FastAPI backend, which returns the same JSON shapes the browser builds itself.
   Open the app with ?source=server (or set window.VVT_CONFIG.source) to use the backend.
   ===================================================================================== */
'use strict';
const API = {
  cfg: window.VVT_CONFIG || { source: 'mock', apiBase: '' },
  get server() { return this.cfg.source === 'server'; },
  token() { try { return JSON.parse(localStorage.getItem('vvt.token') || 'null') || ''; } catch (e) { return ''; } },
  headers() { const h = { Accept: 'application/json' }; const t = this.token(); if (t) h.Authorization = 'Bearer ' + t; return h; },
  async get(path) {
    const r = await fetch(this.cfg.apiBase + path, { headers: this.headers() });
    if (r.status === 401) { try { localStorage.removeItem('vvt.auth'); } catch (e) {} if (typeof renderLogin === 'function') renderLogin(); throw new Error('Sign in with your API token'); }
    if (!r.ok) { let d = ''; try { d = (await r.json()).detail || ''; } catch (e) {} throw new Error(`${r.status} ${path} ${d}`); }
    return r.json();
  },
  async send(method, path, body) {
    const r = await fetch(this.cfg.apiBase + path, { method, headers: { ...this.headers(), 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.status === 204 ? null : r.json();
  },
  me() { return this.get('/api/me'); },
  putWatchlist(imos) { return this.send('PUT', '/api/me/watchlist', { imos }); },
  notes(imo) { return this.get(`/api/me/notes/${imo}`); },
  putNote(imo, n, text) { return this.send('PUT', `/api/me/notes/${imo}/${n}`, { text }); },
  alerts(days = 14) { return this.get(`/api/alerts?days=${days}`); },
  pushSubscribe(sub) { return this.send('POST', '/api/push/subscribe', sub); },
  pushUnsubscribe(sub) { return this.send('DELETE', '/api/push/subscribe', sub); },
  search(q) { return this.get('/api/vessels/search?q=' + encodeURIComponent(q)); },
  analysis(imo) { return this.get(`/api/vessels/${imo}/analysis`); },
  fleet() { return this.get('/api/fleet'); },
  region(id) { return this.get(`/api/regions/${id}/vessels`); },
  rules() { return this.get('/api/rules'); },
  reportUrl(imo) { return `${this.cfg.apiBase}/api/vessels/${imo}/report`; },

  /* Rehydrate a server analysis into the object shape core.js produces, so every screen works unchanged. */
  hydrate(j) {
    const v = j.vessel; v.history = v.history || []; v.sanctions = v.sanctions || []; v.exNames = v.exNames || [];
    const track = j.track || [];
    const calls = (j.portCalls || []).map(pc => ({ ...pc, port: { ...pc.port, b: pc.port.b } }));
    const voyages = (j.voyages || []).map(vg => ({ ...vg, from: vg.from ? calls.find(c => c.arrive === vg.from.arrive) || vg.from : null, to: vg.to ? calls.find(c => c.arrive === vg.to.arrive) || vg.to : null, pts: track.slice(vg.i0, vg.i1 + 1), flags: [] }));
    const flags = (j.flags || []).map(f => { const fl = { ...f, vessel: v, vesselLevel: f.vesselLevel, voyage: f.voyage ? voyages.find(x => x.n === f.voyage) : null }; if (fl.voyage) fl.voyage.flags.push(fl); if (f.partnerImo) fl.partner = { name: (f.lines[1] || '').split(' · ')[0], imo: f.partnerImo }; return fl; });
    const st = j.status || { state: 'moored' };
    return { v, track, portCalls: calls, voyages, flags, sev: j.sev || { high: 0, medium: 0, info: 0 }, last: j.last || track[track.length - 1], stats: j.stats || {},
      static: { state: st.state, destination: st.destination, eta: st.eta, since: st.since, port: st.port, lastPort: st.lastPort, nextPort: st.nextPort } };
  },
};
