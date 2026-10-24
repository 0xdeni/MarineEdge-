/* The server API. Same origin, HttpOnly session cookie; every state-changing request carries the
   X-MarineEdge header the server requires (a cross-site page can't send it). */
'use strict';

class ApiError extends Error {
  constructor(message, status, code, field) { super(message); this.status = status; this.code = code; this.field = field; }
}

const API = {
  onSignedOut: null,
  async req(method, path, body, { quiet401 = false, timeout = 45000 } = {}) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeout);
    let r;
    try {
      r = await fetch(path, {
        method, credentials: 'same-origin', signal: ctl.signal,
        headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' ? { 'X-MarineEdge': '1' } : {}) },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw new ApiError(e.name === 'AbortError' ? 'The server took too long to answer.' : 'No connection to the server. Check your signal and try again.', 0, 'network');
    } finally { clearTimeout(timer); }
    if (r.status === 204) return null;
    let data = null;
    const ct = r.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) { try { data = await r.json(); } catch (e) { data = null; } }
    if (r.status === 503 && data && data.error === 'offline') throw new ApiError("You're offline. This needs a connection.", 0, 'offline');
    if (!r.ok) {
      if (r.status === 401 && !quiet401 && this.onSignedOut) this.onSignedOut();
      const msg = (data && (data.detail || data.error)) || `The server answered ${r.status}.`;
      throw new ApiError(msg, r.status, data && data.code, data && data.field);
    }
    return data;
  },
  get(p, o) { return this.req('GET', p, undefined, o); },
  post(p, b = {}, o) { return this.req('POST', p, b, o); },
  put(p, b = {}, o) { return this.req('PUT', p, b, o); },
  patch(p, b = {}, o) { return this.req('PATCH', p, b, o); },
  del(p, b, o) { return this.req('DELETE', p, b, o); },

  // auth
  authState() { return this.get('/api/auth/state', { quiet401: true }); },
  login(email, password) { return this.post('/api/auth/login', { email, password }, { quiet401: true }); },
  signup(body) { return this.post('/api/auth/signup', body, { quiet401: true }); },
  logout() { return this.post('/api/auth/logout', {}, { quiet401: true }); },
  forgot(email) { return this.post('/api/auth/forgot', { email }, { quiet401: true }); },
  reset(body) { return this.post('/api/auth/reset', body, { quiet401: true }); },
  inviteInfo(code) { return this.get(`/api/auth/invite/${encodeURIComponent(code)}`, { quiet401: true }); },
  resetInfo(token) { return this.get(`/api/auth/reset/${encodeURIComponent(token)}`, { quiet401: true }); },
  // me
  me() { return this.get('/api/me', { quiet401: true }); },
  updateMe(body) { return this.patch('/api/me', body); },
  changePassword(current, password) { return this.post('/api/me/password', { current, password }); },
  sessions() { return this.get('/api/me/sessions'); },
  endSession(id) { return this.del(`/api/me/sessions/${id}`); },
  endOtherSessions() { return this.post('/api/me/sessions/revoke-others', {}); },
  setWatchlist(imos) { return this.put('/api/me/watchlist', { imos }); },
  watching() { return this.get('/api/me/watching'); },
  // data
  regions() { return this.get('/api/regions'); },
  overview(rid) { return this.get(`/api/regions/${rid}/overview`); },
  live(rid) { return this.get(`/api/regions/${rid}/vessels`); },
  search(q) { return this.get('/api/vessels/search?q=' + encodeURIComponent(q)); },
  analysis(imo, refresh) { return this.get(`/api/vessels/${imo}/analysis${refresh ? '?refresh=1' : ''}`, { timeout: 90000 }); },
  buyHistory(imo) { return this.post(`/api/vessels/${imo}/history`, {}, { timeout: 120000 }); },
  crosscheck(imo) { return this.get(`/api/vessels/${imo}/crosscheck`, { timeout: 60000 }); },
  notes(imo) { return this.get(`/api/vessels/${imo}/notes`); },
  addNote(imo, scope, text) { return this.post(`/api/vessels/${imo}/notes`, { scope, text }); },
  editNote(id, text) { return this.patch(`/api/notes/${id}`, { text }); },
  deleteNote(id) { return this.del(`/api/notes/${id}`); },
  alerts(days = 30) { return this.get(`/api/alerts?days=${days}`); },
  alertsSeen() { return this.post('/api/alerts/seen', {}); },
  zones() { return this.get('/api/geo/zones'); },
  ports() { return this.get('/api/geo/ports'); },
  maps() { return this.get('/api/maps'); },
  rules() { return this.get('/api/rules'); },
  pushSubscribe(sub) { return this.post('/api/push/subscribe', sub); },
  pushUnsubscribe(sub) { return this.del('/api/push/subscribe', sub); },
  pushTest() { return this.post('/api/push/test', {}); },
  reportUrl(imo) { return `/api/vessels/${imo}/report.pdf`; },
  // admin
  config() { return this.get('/api/admin/config'); },
  setProvider(provider, api_key) { return this.post('/api/admin/provider', { provider, api_key: api_key || null }); },
  setKey(name, api_key) { return this.post('/api/admin/key', { name, api_key: api_key || null }); },
  testProvider() { return this.post('/api/admin/test', {}, { timeout: 60000 }); },
  firstPull(imos) { return this.post('/api/admin/first-pull', { imos }, { timeout: 300000 }); },
  team() { return this.get('/api/admin/team'); },
  invite(email, role) { return this.post('/api/admin/invites', { email, role }); },
  revokeInvite(id) { return this.del(`/api/admin/invites/${id}`); },
  setMember(id, body) { return this.patch(`/api/admin/users/${id}`, body); },
  removeMember(id) { return this.del(`/api/admin/users/${id}`); },
  resetLink(id) { return this.post(`/api/admin/users/${id}/reset-link`, {}); },
  email() { return this.get('/api/admin/email'); },
  saveEmail(body) { return this.put('/api/admin/email', body); },
  testEmail(to) { return this.post('/api/admin/email/test', { to }, { timeout: 60000 }); },
  saveRules(overrides) { return this.put('/api/admin/rules', { overrides }); },
  resetRules() { return this.del('/api/admin/rules'); },
  setZone(id, enabled) { return this.post(`/api/admin/zones/${id}`, { enabled }); },
  mapsStatus() { return this.get('/api/admin/maps'); },
  mapsDownload(maxzoom) { return this.post('/api/admin/maps/download', { maxzoom }); },
  mapsRemove() { return this.del('/api/admin/maps'); },
  jobSanctions() { return this.post('/api/jobs/sanctions', {}, { timeout: 300000 }); },
  jobRefresh() { return this.post('/api/jobs/refresh', {}, { timeout: 300000 }); },
  jobSweep(seconds = 30) { return this.post('/api/jobs/sweep', { seconds }, { timeout: 120000 }); },
};
