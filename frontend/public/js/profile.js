/* Profile and settings: pushed pages over the map, iOS Settings style. Routes: #/profile[/page[/id]].
   Everyone: account, password, devices, appearance, times, notifications, start region, watching, about.
   Admins also: team and invites, data sources, sanctions lists, rules, zones, detailed maps, email, server. */
'use strict';

const TILE = {
  blue: '#0A84FF', gray: '#8E8E93', green: '#30D158', indigo: '#5E5CE6', orange: '#FF9F0A', red: '#FF453A', teal: '#30B0C7',
  yellow: '#FFB800', pink: '#FF375F', mint: '#00B39B', purple: '#BF5AF2',
};
const ROLE_LABEL = { admin: 'Admin', analyst: 'Analyst' };

function prow({ icon, color, title, value = '', sub = '', go = '', act = '', data = '', danger = false, accent = false, chev = true, id = '' }) {
  const tag = go || act ? 'button' : 'div';
  const attrs = `${go ? `data-go="${esc(go)}"` : ''} ${act ? `data-act="${esc(act)}"` : ''} ${data} ${id ? `id="${id}"` : ''}`;
  return `<${tag} class="row ${icon ? 'ic' : ''} ${go || act ? 'rowtap' : ''} ${danger ? 'danger' : ''} ${accent ? 'accent' : ''}" ${attrs}>
    ${icon ? `<span class="itile" style="background:${color || TILE.gray}">${icon}</span>` : ''}
    <span class="tx"><div class="t1">${title}</div>${sub ? `<div class="t3">${sub}</div>` : ''}</span>
    ${value !== '' ? `<span class="val">${value}</span>` : ''}${(go || act) && chev ? `<span class="chev">${ICON.chev(14)}</span>` : ''}</${tag}>`;
}
const pgroup = (rows, { head = '', foot = '' } = {}) => `${head ? `<p class="sec-cap">${head}</p>` : '<div style="height:22px"></div>'}<div class="group">${rows.filter(Boolean).join('')}</div>${foot ? `<p class="sec-foot">${foot}</p>` : ''}`;
const pfield = ({ id, label, type = 'text', value = '', ph = '', ac = 'off', hint = '', inputmode = '', meter = false }) =>
  `<div class="fld" data-f="${id}"><label for="p-${id}">${esc(label)}</label><div class="inp"><input id="p-${id}" name="${id}" type="${type}" value="${esc(value)}" placeholder="${esc(ph)}" autocomplete="${ac}" ${inputmode ? `inputmode="${inputmode}"` : ''} autocapitalize="${id === 'name' ? 'words' : 'off'}" spellcheck="false">${type === 'password' ? `<button type="button" class="eye" data-act="eye" aria-label="Show password">${ICON.eye(20)}</button>` : ''}</div>${meter ? '<div class="meter" aria-hidden="true"><i></i><i></i><i></i><i></i></div>' : ''}${hint ? `<p class="hint">${hint}</p>` : ''}<p class="err" hidden></p></div>`;
const checkRow = (label, sub, on, act, data = '') => `<button class="row rowtap" data-act="${act}" ${data} role="menuitemradio" aria-checked="${on}"><span class="tx"><div class="t1">${label}</div>${sub ? `<div class="t3">${sub}</div>` : ''}</span><span style="color:var(--accent-text);visibility:${on ? 'visible' : 'hidden'}">${ICON.check(18)}</span></button>`;
const switchRow = (label, sub, on, act, data = '', disabled = false) => `<div class="row"><span class="tx"><div class="t1">${label}</div>${sub ? `<div class="t3">${sub}</div>` : ''}</span><button class="switch" role="switch" aria-checked="${on}" aria-label="${esc(label)}" data-act="${act}" ${data} ${disabled ? 'disabled' : ''}></button></div>`;
function b64ToU8(b64) { const pad = '='.repeat((4 - b64.length % 4) % 4); const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(raw, c => c.charCodeAt(0)); }
const isAdmin = () => !!(S.me && S.me.user && S.me.user.role === 'admin');
const standalone = () => (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

const Profile = {
  wired: false, cfg: null, team: null, lastInvite: null, lastReset: null, testResult: null, pullResult: null, sanc: null, emailTest: null,

  wire() {
    if (this.wired) return; this.wired = true;
    const root = $('#pages');
    root.addEventListener('click', e => {
      const g = e.target.closest('[data-go]'); if (g) { e.preventDefault(); App.go(g.dataset.go); return; }
      const a = e.target.closest('[data-act]'); if (a) { e.preventDefault(); this.act(a.dataset.act, a, e); }
    });
    root.addEventListener('input', e => {
      const t = e.target; const fld = t.closest('.fld');
      if (fld) { const inp = fld.querySelector('.inp'); if (inp) inp.classList.remove('bad'); const er = fld.querySelector('.err'); if (er) er.hidden = true; }
      if (t.type === 'password' && fld && fld.querySelector('.meter')) { const m = fld.querySelector('.meter'); m.className = `meter${t.value ? ' s' + strength(t.value) : ''}`; }
      if (t.id === 'p-email' && $('#emailPw')) $('#emailPw').hidden = t.value.trim().toLowerCase() === (S.me.user.email || '').toLowerCase();
    });
    root.addEventListener('submit', e => e.preventDefault());
  },

  /* keep the page stack in step with the route */
  sync(sub) {
    this.wire();
    if (sub === null) { if (Pages.stack.length) Pages.clear(); return; }
    const want = ['root'];
    for (let i = 0; i < sub.length; i++) want.push(sub.slice(0, i + 1).join('/'));
    let k = 0;
    while (k < Pages.stack.length && k < want.length && Pages.stack[k].id === want[k]) k++;
    while (Pages.stack.length > k) Pages.pop();
    for (let i = k; i < want.length; i++) {
      const def = this.page(want[i]);
      if (!def) { history.replaceState(null, '', '#/profile' + (i > 1 ? '/' + want[i - 1] : '')); break; }
      Pages.push(def);
    }
    if (k === want.length && Pages.top()) Pages.refresh(Pages.top());
  },
  refresh() { if (Pages.top()) Pages.refresh(Pages.top()); },
  fail(form, err) {
    if (err.field) {
      const f = form.querySelector(`[data-f="${err.field}"]`) || form.querySelector(`[data-f="${err.field === 'current' ? 'current' : err.field}"]`);
      if (f) { f.querySelector('.inp').classList.add('bad'); const er = f.querySelector('.err'); er.textContent = err.message; er.hidden = false; return; }
    }
    toast(err.message, 'err');
  },

  page(id) {
    const [base, arg] = id.split('/');
    const adminOnly = ['team', 'invite', 'sources', 'sanctions', 'rules', 'zones', 'maps', 'email', 'server'];
    if (adminOnly.includes(base) && !isAdmin()) return { id, title: 'Admins only', render: pc => { pc.innerHTML = `<div class="empty"><h3>Only admins can change this</h3><p>Ask an admin on your team.</p></div>`; } };
    const P = {
      root: { title: 'Profile', render: pc => this.pRoot(pc) },
      account: { title: 'Name and email', render: pc => this.pAccount(pc) },
      password: { title: 'Password', render: pc => this.pPassword(pc) },
      devices: { title: 'Signed-in devices', render: pc => this.pDevices(pc) },
      appearance: { title: 'Appearance', render: pc => this.pAppearance(pc) },
      times: { title: 'Times', render: pc => this.pTimes(pc) },
      notifications: { title: 'Notifications', render: pc => this.pNotifications(pc) },
      region: { title: 'Start region', render: pc => this.pRegion(pc) },
      watching: { title: 'Watching', render: pc => this.pWatching(pc) },
      team: { title: 'Team', render: pc => this.pTeam(pc) },
      invite: { title: 'Invite someone', render: pc => this.pInvite(pc) },
      sources: { title: 'Data sources', render: pc => this.pSources(pc) },
      sanctions: { title: 'Sanctions lists', render: pc => this.pSanctions(pc) },
      rules: { title: 'Red-flag rules', render: pc => this.pRules(pc) },
      zones: { title: 'Sensitive zones', render: pc => this.pZones(pc) },
      maps: { title: 'Detailed maps', render: pc => this.pMaps(pc) },
      email: { title: 'Email', render: pc => this.pEmail(pc) },
      server: { title: 'Server', render: pc => this.pServer(pc) },
      about: { title: 'About MarineEdge', render: pc => this.pAbout(pc) },
    };
    if (base === 'team' && arg) return { id, title: 'Member', render: pc => this.pMember(pc, +arg) };
    if (base === 'invite' && arg) return null;
    const d = P[base]; if (!d || (arg && base !== 'team')) return null;
    return { id, ...d };
  },

  /* ================================================================ everyone */
  async pRoot(pc) {
    const u = S.me.user; const admin = isAdmin();
    const ps = await this.pushState().catch(() => 'off');
    const theme = { system: 'System', dark: 'Dark', light: 'Light' }[S.themePref] || 'System';
    const regionName = (S.regions.find(r => r.id === ((u.prefs && u.prefs.region) || 'blacksea')) || {}).name || REGION_NAME[(u.prefs && u.prefs.region) || 'blacksea'];
    pc.innerHTML = `<button class="pcard rowtap" data-go="#/profile/account"><span class="avatar" style="background:${esc(u.color)}">${esc(u.initials)}</span>
        <span class="tx"><div class="t-title3">${esc(u.name)}</div><div class="t-sub c2">${esc(u.email)}</div><div class="t-foot c2" style="margin-top:3px">${esc(ROLE_LABEL[u.role] || u.role)}</div></span><span class="chev">${ICON.chev(14)}</span></button>
      ${pgroup([prow({ icon: ICON.lock(17), color: TILE.gray, title: 'Password', go: '#/profile/password' }),
        prow({ icon: ICON.iphone(17), color: TILE.green, title: 'Signed-in devices', go: '#/profile/devices' })])}
      ${pgroup([prow({ icon: ICON.sun(17), color: TILE.indigo, title: 'Appearance', value: theme, go: '#/profile/appearance' }),
        prow({ icon: ICON.clock(17), color: TILE.orange, title: 'Times', value: Fmt.utc ? 'UTC' : 'This phone', go: '#/profile/times' }),
        prow({ icon: ICON.bell(17), color: TILE.red, title: 'Notifications', value: ps === 'on' ? 'On' : ps === 'unsupported' ? 'Not available' : 'Off', go: '#/profile/notifications' }),
        prow({ icon: ICON.pin(17), color: TILE.teal, title: 'Start region', value: esc(regionName), go: '#/profile/region' })], { head: 'Preferences' })}
      ${pgroup([prow({ icon: ICON.starFill(17), color: TILE.yellow, title: 'Watching', value: String((S.me.watchlist || []).length), go: '#/profile/watching' })], { head: 'Ships' })}
      ${admin ? pgroup([prow({ icon: ICON.people(17), color: TILE.indigo, title: 'Team', go: '#/profile/team' }),
        prow({ icon: ICON.antenna(17), color: TILE.blue, title: 'Data sources', go: '#/profile/sources' }),
        prow({ icon: ICON.shield(17), color: TILE.red, title: 'Sanctions lists', go: '#/profile/sanctions' }),
        prow({ icon: ICON.sliders(17), color: TILE.orange, title: 'Red-flag rules', go: '#/profile/rules' }),
        prow({ icon: ICON.map(17), color: TILE.pink, title: 'Sensitive zones', go: '#/profile/zones' }),
        prow({ icon: ICON.layers(17), color: TILE.green, title: 'Detailed maps', go: '#/profile/maps' }),
        prow({ icon: ICON.mail(17), color: TILE.blue, title: 'Email', go: '#/profile/email' }),
        prow({ icon: ICON.server(17), color: TILE.gray, title: 'Server', go: '#/profile/server' })], { head: 'Team and server' }) : ''}
      ${pgroup([prow({ icon: ICON.info(17), color: TILE.gray, title: 'About MarineEdge', go: '#/profile/about' })])}
      ${pgroup([prow({ title: 'Sign out', act: 'signout', danger: true, chev: false })])}
      <p class="sec-foot" style="text-align:center;margin-top:18px">MarineEdge ${esc(S.me.server.version)}</p>`;
  },

  pAccount(pc) {
    const u = S.me.user;
    pc.innerHTML = `<form class="pform" data-form="account" novalidate>
      ${pfield({ id: 'name', label: 'Name', value: u.name, ac: 'name' })}
      ${pfield({ id: 'email', label: 'Email', type: 'email', value: u.email, ac: 'username', inputmode: 'email', hint: 'You sign in with it, and password reset codes go there.' })}
      <div id="emailPw" hidden>${pfield({ id: 'currentPassword', label: 'Current password', type: 'password', ac: 'current-password', hint: 'Needed to change your email.' })}</div>
      <button class="btn" style="margin-top:22px" data-act="save-account"><span class="lbl">Save</span></button></form>
      ${pgroup([`<div class="kv"><span class="k">Role</span><span class="v">${esc(ROLE_LABEL[u.role] || u.role)}</span></div>`,
        `<div class="kv"><span class="k">Member since</span><span class="v">${esc(Fmt.day(u.created, true))}</span></div>`],
        { foot: u.role === 'admin' ? 'Admins invite people and change the server settings.' : 'An admin can change your role in Profile › Team.' })}`;
  },
  pPassword(pc) {
    pc.innerHTML = `<form class="pform" data-form="password" novalidate>
      <input type="email" name="username" autocomplete="username" value="${esc(S.me.user.email)}" hidden>
      ${pfield({ id: 'current', label: 'Current password', type: 'password', ac: 'current-password' })}
      ${pfield({ id: 'password', label: 'New password', type: 'password', ac: 'new-password', meter: true, hint: 'At least 10 characters. A few unrelated words make a strong one.' })}
      <button class="btn" style="margin-top:22px" data-act="save-password"><span class="lbl">Change password</span></button>
      <p class="sec-foot" style="margin:14px 4px 0">Your other devices are signed out when the password changes.</p></form>`;
  },
  async pDevices(pc) {
    const list = await API.sessions();
    const others = list.filter(s => !s.current);
    pc.innerHTML = pgroup(list.map(s => prow({ icon: ICON.iphone(17), color: s.current ? TILE.green : TILE.gray, title: esc(s.device) + (s.current ? ' · this device' : ''),
      sub: `Signed in ${esc(Fmt.day(s.created, true))} · active ${esc(Fmt.ago(s.lastSeen))}`, act: s.current ? '' : 'end-session', data: `data-id="${s.id}" data-name="${esc(s.device)}"` })),
      { foot: 'Sessions last 90 days from the last use.' })
      + (others.length ? pgroup([prow({ title: `Sign out ${others.length === 1 ? 'the other device' : `all ${others.length} other devices`}`, act: 'end-others', danger: true, chev: false })]) : '');
  },
  pAppearance(pc) {
    const p = S.themePref;
    pc.innerHTML = pgroup([checkRow('System', 'Follows the iPhone: dark at night, light by day', p === 'system', 'theme', 'data-v="system"'),
      checkRow('Dark', 'The night chart. Easiest on the eyes on the bridge or at night', p === 'dark', 'theme', 'data-v="dark"'),
      checkRow('Light', 'Brighter, for sunlight', p === 'light', 'theme', 'data-v="light"')]);
  },
  pTimes(pc) {
    pc.innerHTML = pgroup([checkRow('UTC', 'The maritime standard. Reports always use UTC', Fmt.utc, 'times', 'data-v="utc"'),
      checkRow("This phone's time zone", Intl.DateTimeFormat().resolvedOptions().timeZone || '', !Fmt.utc, 'times', 'data-v="local"')]);
  },
  async pushState() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return 'unsupported';
    if (Notification.permission === 'denied') return 'denied';
    try { const reg = await navigator.serviceWorker.getRegistration(); const sub = reg && await reg.pushManager.getSubscription(); return sub ? 'on' : 'off'; } catch (e) { return 'off'; }
  },
  async pNotifications(pc) {
    const st = await this.pushState(); const cfg = S.me.push || {};
    const prefs = S.me.user.prefs || {}; const min = prefs.pushMin || 'high';
    let h = '';
    if (st === 'unsupported') {
      h = `<div class="empty"><div class="ei">${ICON.bell(24)}</div><h3>${isIOS() && !standalone() ? 'Add MarineEdge to your Home Screen first' : "This browser can't show notifications"}</h3>
        <p>${isIOS() && !standalone() ? 'On iPhone, notifications work for apps on the Home Screen: tap Share, then Add to Home Screen, and open MarineEdge from there.' : 'Open MarineEdge in Safari on iPhone (from the Home Screen), or in Chrome, Edge or Firefox.'}</p></div>`;
    } else if (!cfg.configured) {
      h = `<div class="empty"><div class="ei">${ICON.bell(24)}</div><h3>Notifications aren't set up on this server</h3><p>The server has no push keys yet. Re-running the installer creates them. Alerts still appear in the app.</p></div>`;
    } else {
      h = pgroup([switchRow('On this device', st === 'denied' ? 'Blocked in Settings › Notifications › MarineEdge' : 'New red flags on the ships you watch', st === 'on', 'push-toggle', '', st === 'denied')],
        { foot: 'MarineEdge checks your watched ships every 30 minutes, also while your phone is locked.' });
      h += pgroup([checkRow('High findings only', 'Sanctions, sensitive ports, long dark periods, ship-to-ship stops', min !== 'medium', 'push-min', 'data-v="high"'),
        checkRow('High and Medium', 'Also draught changes at sea and repeated identity changes', min === 'medium', 'push-min', 'data-v="medium"')], { head: 'Notify me about' });
      if (st === 'on') h += pgroup([prow({ title: 'Send a test notification', act: 'push-test', accent: true, chev: false })]);
    }
    pc.innerHTML = h;
  },
  async enablePush() {
    try {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) { toast(isIOS() && !standalone() ? 'Add MarineEdge to your Home Screen first, then try again.' : "This browser can't show notifications.", 'err'); return false; }
      if (!S.me.push || !S.me.push.publicKey) { toast("Notifications aren't set up on this server.", 'err'); return false; }
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') { toast('Notifications were not allowed. You can allow them in Settings.', 'err'); return false; }
      const reg = await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(S.me.push.publicKey) });
      await API.pushSubscribe(sub.toJSON());
      toast('Notifications are on for this device.', 'ok');
      return true;
    } catch (e) { toast(`Couldn't turn on notifications: ${e.message}`, 'err'); return false; }
  },
  async disablePush() {
    try {
      const reg = await navigator.serviceWorker.getRegistration(); const sub = reg && await reg.pushManager.getSubscription();
      if (sub) { await API.pushUnsubscribe({ endpoint: sub.endpoint }).catch(() => {}); await sub.unsubscribe(); }
      toast('Notifications are off for this device.');
    } catch (e) { toast(e.message, 'err'); }
  },
  pRegion(pc) {
    const cur = (S.me.user.prefs && S.me.user.prefs.region) || S.region;
    const regs = S.regions.length ? S.regions : Object.keys(REGION_NAME).map(id => ({ id, name: REGION_NAME[id] }));
    pc.innerHTML = pgroup(regs.map(r => checkRow(esc(r.name), '', r.id === cur, 'region', `data-v="${r.id}"`)), { foot: 'The map opens here. Change it any time with the region button on the map.' });
  },
  async pWatching(pc) {
    const list = await API.watching();
    if (!list.length) { pc.innerHTML = `<div class="empty"><div class="ei">${ICON.star(24)}</div><h3>No ships yet</h3><p>Open a ship and tap the star. MarineEdge checks it every 30 minutes and tells you about new red flags.</p></div>`; return; }
    pc.innerHTML = pgroup(list.map(w => `<div class="row ship"><button class="tx rowtap" style="text-align:left;display:flex;gap:12px;align-items:center" data-go="#/ship/${w.imo}"><span class="ship-ic ${w.level || 'none'}">${ICON.ship(20)}</span>
        <span style="min-width:0"><div class="t1 b">${esc(w.name)}</div><div class="t2">${esc(w.headline || (w.level ? LEVEL_LABEL[w.level] : 'Not checked yet'))}</div><div class="t3">IMO ${w.imo}${w.last ? ` · heard ${esc(Fmt.ago(w.last.t))}` : ''}</div></span></button>
        <button class="cbtn lg" data-act="unwatch" data-imo="${w.imo}" data-name="${esc(w.name)}" aria-label="Stop watching ${esc(w.name)}" style="color:var(--yellow)">${ICON.starFill(17)}</button></div>`),
      { foot: 'Checked every 30 minutes. New red flags show in Alerts and as notifications.' });
  },
  pAbout(pc) {
    pc.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;padding:12px 20px 4px">${logoSVG(72, 'ab')}<div class="t-title2" style="margin-top:12px">MarineEdge</div><div class="t-sub c2">Version ${esc(S.me.server.version)}</div></div>
      ${pgroup([`<div class="kv"><span class="k">Live positions</span><span class="v">aisstream.io<div class="s">Free feed, recorded on your server</div></span></div>`,
        `<div class="kv"><span class="k">History</span><span class="v">Datalastic<div class="s">Only when an admin adds a key</div></span></div>`,
        `<div class="kv"><span class="k">Sanctions</span><span class="v">OFAC, EU, UK<div class="s">Official lists, refreshed daily</div></span></div>`,
        `<div class="kv"><span class="k">Cross-check</span><span class="v">Global Fishing Watch<div class="s">CC BY-NC 4.0, never a source</div></span></div>`,
        `<div class="kv"><span class="k">Maps</span><span class="v">Natural Earth, OpenStreetMap<div class="s">Public domain; © OpenStreetMap contributors, ODbL</div></span></div>`,
        `<div class="kv"><span class="k">Map engine</span><span class="v">MapLibre GL JS<div class="s">BSD-3-Clause</div></span></div>`], { head: 'Where the data comes from' })}
      ${pgroup([prow({ title: 'Show the introduction again', act: 'intro', accent: true, chev: false })], { foot: `${DRAUGHT_NOTE} Findings are rule-based indicators for your own judgement, not legal conclusions.` })}`;
  },

  /* ================================================================ admin: team */
  async pTeam(pc) {
    const t = await API.team(); this.team = t;
    const me = S.me.user.id;
    pc.innerHTML = `<div style="padding:16px var(--edge) 0"><button class="btn" data-go="#/profile/invite">${ICON.plus(18)}<span class="lbl">Invite someone</span></button></div>
      ${pgroup(t.users.map(u => `<button class="row rowtap" data-go="#/profile/team/${u.id}"><span class="avatar sm" style="background:${esc(u.color)}">${esc(u.initials)}</span>
        <span class="tx"><div class="t1">${esc(u.name)}${u.id === me ? ' <span class="c2">(you)</span>' : ''}</div><div class="t3">${esc(u.email)}${u.status === 'disabled' ? ' · turned off' : u.lastSeen ? ' · active ' + esc(Fmt.ago(u.lastSeen)) : ''}</div></span>
        <span class="val">${esc(ROLE_LABEL[u.role] || u.role)}</span><span class="chev">${ICON.chev(14)}</span></button>`), { head: `${t.users.length} ${t.users.length === 1 ? 'person' : 'people'}` })}
      ${t.invites.length ? pgroup(t.invites.map(i => prow({ icon: ICON.mail(17), color: TILE.gray, title: esc(i.email || 'Invite link'), sub: `${esc(ROLE_LABEL[i.role] || i.role)} · works until ${esc(Fmt.day(i.expires, true))}`, act: 'revoke-invite', data: `data-id="${i.id}"`, chev: false, value: '<span class="c-red" style="font-size:0.882rem">Cancel</span>' })), { head: 'Waiting to join' }) : ''}
      <p class="sec-foot" style="margin-top:14px">Analysts check ships, watch them and write notes. Admins also manage the team and the server.</p>`;
  },
  async pMember(pc, uid) {
    if (!this.team) this.team = await API.team();
    const u = this.team.users.find(x => x.id === uid);
    if (!u) { pc.innerHTML = `<div class="empty"><h3>This person isn't on the team any more</h3></div>`; return; }
    const self = u.id === S.me.user.id;
    const reset = this.lastReset && this.lastReset.uid === uid ? this.lastReset : null;
    pc.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;padding:8px 20px 0;text-align:center"><span class="avatar lg" style="background:${esc(u.color)}">${esc(u.initials)}</span>
        <div class="t-title3" style="margin-top:10px">${esc(u.name)}</div><div class="t-sub c2">${esc(u.email)}</div>
        <div class="t-foot c2" style="margin-top:4px">Joined ${esc(Fmt.day(u.created, true))}${u.lastSeen ? ` · active ${esc(Fmt.ago(u.lastSeen))}` : ''}</div></div>
      <p class="sec-cap">Role</p><div style="margin:0 var(--edge)"><div class="seg" role="group" aria-label="Role">${['analyst', 'admin'].map(r => `<button data-act="set-role" data-uid="${uid}" data-v="${r}" aria-pressed="${u.role === r}">${ROLE_LABEL[r]}</button>`).join('')}</div></div>
      ${pgroup([switchRow('Account on', u.status === 'disabled' ? 'Turned off: they can’t sign in' : 'They can sign in', u.status !== 'disabled', 'set-status', `data-uid="${uid}"`, self)])}
      ${!self ? pgroup([prow({ title: 'Make a password reset link', act: 'reset-link', data: `data-uid="${uid}"`, accent: true, chev: false, sub: 'For when email isn’t set up. Works once, for 24 hours.' })]) : ''}
      ${reset ? `<div class="linkbox"><div class="t-foot c2">Send this to ${esc(u.name)}. It works once, until ${esc(Fmt.dayTime(reset.expires))}.</div><div class="lk selectable">${esc(reset.url)}</div>
        <div class="btnrow two"><button class="btn secondary small" data-act="share-link" data-url="${esc(reset.url)}" data-title="Reset your MarineEdge password">${ICON.share(16)}Share</button><button class="btn secondary small" data-act="copy-link" data-url="${esc(reset.url)}">${ICON.copy(16)}Copy</button></div></div>` : ''}
      ${!self ? pgroup([prow({ title: 'Remove from team', act: 'remove-member', data: `data-uid="${uid}" data-name="${esc(u.name)}"`, danger: true, chev: false })], { foot: 'Their notes stay, marked as from a former member.' }) : `<p class="sec-foot" style="margin-top:18px">You can't change your own access. Ask another admin.</p>`}`;
  },
  pInvite(pc) {
    const inv = this.lastInvite;
    if (inv) {
      const url = inv.url;
      pc.innerHTML = `<div class="empty" style="margin-top:20px"><div class="ei" style="color:var(--green)">${ICON.check(26)}</div><h3>Invite ready</h3>
          <p>${inv.emailed ? `Sent to ${esc(inv.email)}. You can also share the link yourself.` : `${inv.email ? `Email isn't set up, so send it to ${esc(inv.email)} yourself.` : 'Send it to the person you want to invite.'} It works once, for seven days.`}</p></div>
        <div class="linkbox"><div class="lk selectable">${esc(url)}</div><div class="btnrow two"><button class="btn small" data-act="share-link" data-url="${esc(url)}" data-title="Join MarineEdge">${ICON.share(16)}Share</button><button class="btn secondary small" data-act="copy-link" data-url="${esc(url)}">${ICON.copy(16)}Copy</button></div></div>
        ${pgroup([prow({ title: 'Invite someone else', act: 'invite-again', accent: true, chev: false })], { foot: `They join as ${ROLE_LABEL[inv.role] || inv.role}. Pending invites are listed in Team, where you can cancel them.` })}`;
      return;
    }
    pc.innerHTML = `<form class="pform" data-form="invite" novalidate>
      ${pfield({ id: 'email', label: 'Their email (optional)', type: 'email', ph: 'name@company.com', inputmode: 'email', hint: S.cfgEmail ? 'They get the invite by email.' : 'Leave it empty to just make a link to share.' })}
      <p class="sec-cap" style="margin-left:4px;margin-right:4px">Role</p><div class="seg" role="group" aria-label="Role"><button type="button" data-act="inv-role" data-v="analyst" aria-pressed="true">Analyst</button><button type="button" data-act="inv-role" data-v="admin" aria-pressed="false">Admin</button></div>
      <button class="btn" style="margin-top:22px" data-act="create-invite"><span class="lbl">Create invite</span></button></form>`;
    API.email().then(e => { S.cfgEmail = e.configured; const h = pc.querySelector('[data-f="email"] .hint'); if (h) h.textContent = e.configured ? 'They get the invite by email, and you can share the link too.' : "Email isn't set up, so you'll share the link yourself."; }).catch(() => {});
  },

  /* ================================================================ admin: data sources */
  async pSources(pc) {
    const c = await API.config(); this.cfg = c;
    const k = c.keys || {}; const live = c.live || {};
    const rs = c.recorder || {};
    let rec = live.newest ? `Recording since ${Fmt.day(live.oldest, true)} · ${Fmt.n(live.mmsi)} ships seen · last position ${Fmt.ago(live.newest)}` : k.aisstream ? 'Key saved. Waiting for the first positions' : 'No key yet';
    if (k.aisstream && rs.state === 'error') rec = `<span class="c-red">Not recording: ${esc(rs.error || 'the connection failed')}</span>`;
    else if (k.aisstream && rs.state === 'stopped') rec = `<span class="c-red">The recorder isn't running (last seen ${esc(Fmt.ago(rs.updated))})</span>`;
    else if (k.aisstream && rs.state === 'connecting' && !live.newest) rec = 'Connecting to aisstream.io…';
    else rec = esc(rec);
    const keyForm = (name, ph) => `<div class="keyform"><div class="inp"><span class="ico">${ICON.key(17)}</span><input id="key-${name}" placeholder="${esc(ph)}" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="${esc(ph)}"></div>
      <div class="btnrow two"><button class="btn small" data-act="save-key" data-name="${name}"><span class="lbl">Save</span></button>${k[name] ? `<button class="btn secondary small" data-act="clear-key" data-name="${name}">Remove</button>` : '<span></span>'}</div></div>`;
    const paidPrimary = /^(datalastic|kpler)$/.test(c.provider);
    let h = '';
    if (c.mock) h += `<div class="setup-card" style="margin-top:18px"><h3>Demo fleet</h3><p>This development machine shows generated ships. A server never does.</p></div>`;
    if (paidPrimary) h += `<div class="setup-card" style="margin-top:18px"><h3>Every check buys positions</h3><p>${esc(titleCase(c.provider))} is the main source, so each new check costs credits. The free feed plus 12 months bought per ship is cheaper.</p><button class="btn" style="margin-top:12px" data-act="use-free"><span class="lbl">Use the free feed as the main source</span></button></div>`;
    h += pgroup([prow({ icon: ICON.antenna(17), color: TILE.blue, title: 'aisstream.io', sub: rec, value: k.aisstream ? esc(k.aisstream) : '' })], { head: 'Live positions (free)' }) + keyForm('aisstream', k.aisstream ? 'Paste a new key to replace it' : 'Paste the aisstream.io API key')
      + `<p class="sec-foot">Free. Hears ships near the coast only, and nothing from before your server started recording. Get a key at <a href="https://aisstream.io" target="_blank" rel="noopener">aisstream.io</a> (sign in with GitHub).</p>`;
    h += pgroup([prow({ icon: ICON.clock(17), color: TILE.indigo, title: 'Datalastic', sub: k.datalastic ? 'Each ship page offers to buy its last 12 months' : 'Add a key to buy 12 months of history per ship', value: k.datalastic ? esc(k.datalastic) : '' })], { head: 'Past 12 months (paid)' }) + keyForm('datalastic', k.datalastic ? 'Paste a new key to replace it' : 'Paste the Datalastic API key')
      + `<p class="sec-foot">Bought once per ship, open sea included, kept on your server and never fetched twice. Nothing is bought without an admin confirming.</p>`;
    if (k.datalastic) {
      h += pgroup([`<div class="row" style="display:block"><div class="t1" style="margin-bottom:8px">Buy history for several ships</div><textarea class="ta" id="pullImos" style="min-height:76px" placeholder="IMO numbers, up to 10">${esc((this.pullResult && this.pullResult.input) || '')}</textarea>
        <button class="btn small" style="margin-top:10px" data-act="first-pull"><span class="lbl">Buy 12 months for these</span></button>${this.pullResult && this.pullResult.rows ? `<div class="t-foot c2" style="margin-top:10px">${this.pullResult.rows.map(r => esc(`${r.imo}: ${r.ok === false ? r.error : `${r.name || ''} ${r.positions != null ? r.positions + ' positions' : ''}`}`)).join('<br>')}</div>` : ''}</div>`]);
    }
    h += pgroup([prow({ icon: ICON.globe(17), color: TILE.teal, title: 'Global Fishing Watch', sub: k.gfw ? 'Cross-check on every ship page' : 'Not set up', value: k.gfw ? esc(k.gfw) : '' })], { head: 'Cross-check' }) + keyForm('gfw', k.gfw ? 'Paste a new token to replace it' : 'Paste the GFW API token')
      + `<p class="sec-foot">Free for non-commercial use only (CC BY-NC 4.0). Global Fishing Watch says a business's internal use needs their licence, so ask them before adding the token. Used only to compare, never as a source for findings. <a href="https://globalfishingwatch.org/faqs/can-i-use-global-fishing-watch-apis-for-commercial-purposes/" target="_blank" rel="noopener">Their licence terms</a>.</p>`;
    h += pgroup([prow({ title: 'Test the main source', act: 'test-provider', accent: true, chev: false, sub: this.testResult ? esc(this.testResult) : `Now: ${esc(titleCase(c.active || c.provider))}` })]);
    pc.innerHTML = h;
  },

  async pSanctions(pc) {
    const c = await API.config(); this.cfg = c;
    const s = c.sanctions || {};
    const r = this.sanc;
    pc.innerHTML = pgroup([`<div class="kv"><span class="k">Listed IMO numbers</span><span class="v">${s.rows != null ? Fmt.n(s.rows) : '—'}</span></div>`,
      `<div class="kv"><span class="k">Last download</span><span class="v">${s.refreshed ? esc(Fmt.dayTime(s.refreshed)) : 'Never'}</span></div>`,
      ...(s.lists ? Object.entries(s.lists).map(([n, v]) => `<div class="kv"><span class="k">${esc(n)}</span><span class="v">${Fmt.n(v)}</span></div>`) : [])],
      { foot: 'Downloaded every day at 04:30 UTC from the official sources: the OFAC SDN list (US Treasury), the EU consolidated list and the UK Sanctions List (FCDO). Ships are matched by IMO number.' })
      + pgroup([prow({ title: r && r.running ? 'Downloading…' : 'Download the lists now', act: 'sanctions-now', accent: true, chev: false, sub: r && r.result ? esc(r.result) : '' })]);
  },

  async pRules(pc) {
    const d = await API.rules(); const R = d.rules; const over = d.overrides || {};
    const F = [
      ['port_call', 'Port calls', [['min_hours', 'Stopped for at least', 'h'], ['max_speed_kn', 'Slower than', 'kn'], ['port_radius_nm', 'Within', 'nm of the berth']]],
      ['ais_gap', 'AIS gaps', [['min_hours', 'Longer than', 'h'], ['high_hours', 'High when longer than', 'h'], ['near_sensitive_nm', 'High when within', 'nm of a zone'], ['coverage_max_hours', 'Not counted outside coverage up to', 'h']]],
      ['draught_change', 'Draught change at sea', [['min_meters', 'At least', 'm'], ['after_stop_or_dark_only', 'Only after a stop at sea or AIS off', 'Changes typed in while under way show as Info']]],
      ['sts', 'Ship-to-ship stops', [['max_dist_m', 'Within', 'm'], ['alongside_max_dist_m', 'At anchor or moored, within', 'm'], ['max_speed_kn', 'Both slower than', 'kn'], ['min_hours', 'For at least', 'h'],
        ['partner_needs_imo', 'Only ships with an IMO number', 'Leaves out tugs, pilot boats and harbour craft']]],
      ['position_jump', 'Position jumps', [['max_implied_kn', 'Implied speed above', 'kn']]],
    ];
    const changed = Object.keys(over).length > 0;
    const field = (g, name, [k, label, unit]) => typeof R[g][k] === 'boolean'
      ? switchRow(label, unit, R[g][k], 'rule-switch', `data-g="${g}" data-k="${k}"`)
      : `<label class="row numrow"><span class="tx"><div class="t1">${label}</div></span>
        <input class="num ${over[g] && over[g][k] != null ? 'changed' : ''}" type="number" inputmode="decimal" step="any" min="0" data-g="${g}" data-k="${k}" value="${R[g][k]}" aria-label="${esc(name + ': ' + label)}"><span class="unit">${unit}</span></label>`;
    pc.innerHTML = F.map(([g, name, keys]) => pgroup(keys.filter(([k]) => R[g] && R[g][k] != null).map(f => field(g, name, f)), { head: name })).join('')
      + `<div style="padding:22px var(--edge) 0;display:grid;gap:10px"><button class="btn" data-act="save-rules"><span class="lbl">Save and re-check</span></button>${changed ? '<button class="btn secondary" data-act="reset-rules">Back to the defaults</button>' : ''}</div>
      <p class="sec-foot">Changes apply to every check from now on. Ships are re-checked the next time they're opened or swept.</p>`;
  },

  async pZones(pc) {
    const c = await API.config(); this.cfg = c;
    pc.innerHTML = pgroup((c.zones || []).map(z => switchRow(esc(z.name), esc(z.basis || ''), z.enabled, 'zone', `data-id="${esc(z.id)}"`)),
      { foot: 'A port call or an AIS gap inside or near an enabled zone becomes a red flag. Zones are drawn hatched on the map.' });
  },

  async pMaps(pc) {
    const st = await API.mapsStatus();
    const dl = st.state === 'downloading';
    let h = '';
    if (st.installed) h += pgroup([`<div class="kv"><span class="k">Installed</span><span class="v">${esc(Fmt.bytes(st.bytes))}<div class="s">${st.build ? 'Build ' + esc(st.build) : ''}${st.maxzoom ? ` · street level to zoom ${st.maxzoom}` : ''}</div></span></div>`],
      { head: 'OpenStreetMap detail', foot: 'Coastlines, harbours, roads and towns in close-up, served from your own server. Natural Earth covers the rest.' });
    else h += `<div class="empty" style="margin-top:28px"><div class="ei">${ICON.layers(24)}</div><h3>Close-up maps</h3><p>The app ships with Natural Earth maps of the whole world. Download OpenStreetMap detail for the Black Sea, the Mediterranean and the Gulf to see harbours and coastlines up close.</p></div>`;
    if (dl) h += pgroup([`<div class="row"><span class="spin" style="color:var(--text-2)"></span><span class="tx"><div class="t1">Downloading…</div><div class="t3">${st.progressBytes ? esc(Fmt.bytes(st.progressBytes)) + ' so far' : 'Starting'} · this page updates by itself</div></span></div>`]);
    else {
      if (st.state === 'failed') h += `<p class="sec-foot c-red" style="margin-top:14px">The last download failed: ${esc(st.error || 'unknown error')}.</p>`;
      h += pgroup((st.zooms || [11, 12, 13, 14]).map(z => checkRow(`Detail to zoom ${z}`, { 11: 'Coastlines and ports. About 0.5 GB', 12: 'Harbour basins. About 1 GB', 13: 'Quays and terminals. About 2 GB', 14: 'Every pier. About 4 GB' }[z] || '', (this.mapZoom || st.maxzoom || st.defaultZoom) === z, 'map-zoom', `data-v="${z}"`)), { head: st.installed ? 'Download again' : 'How much detail' })
        + `<div style="padding:16px var(--edge) 0"><button class="btn" data-act="map-download"><span class="lbl">${st.installed ? 'Replace the map' : 'Download'}</span></button></div>
        <p class="sec-foot">Takes 5–30 minutes on the server. The app keeps working meanwhile.</p>`;
      if (st.installed) h += pgroup([prow({ title: 'Remove the detailed map', act: 'map-remove', danger: true, chev: false })]);
    }
    pc.innerHTML = h;
    clearTimeout(this.mapPoll);
    if (dl) this.mapPoll = setTimeout(() => { if (Pages.top() && Pages.top().id === 'maps') this.refresh(); }, 4000);
    else if (st.installed && !(S.maps && S.maps.installed)) { S.maps = { installed: true, url: st.url }; MapView.setDetail(st.url); App.renderAttribution(); }
  },

  async pEmail(pc) {
    const e = await API.email();
    const t = this.emailTest;
    pc.innerHTML = `${e.configured ? '' : `<div class="setup-card" style="margin-top:18px"><h3>Why set up email</h3><p>Password reset codes and invites go out by email. Without it, admins make reset links by hand in Team.</p></div>`}
      <form class="pform" data-form="email" novalidate>
      ${pfield({ id: 'host', label: 'SMTP server', value: e.host, ph: 'smtp.gmail.com' })}
      <div class="two-col">${pfield({ id: 'port', label: 'Port', value: String(e.port || 587), inputmode: 'numeric' })}
        <div class="fld"><label>Security</label><div class="seg" role="group" aria-label="Security" style="margin-top:2px">${['starttls', 'ssl', 'none'].map(s => `<button type="button" data-act="smtp-sec" data-v="${s}" aria-pressed="${(e.security || 'starttls') === s}">${{ starttls: 'STARTTLS', ssl: 'SSL', none: 'None' }[s]}</button>`).join('')}</div></div></div>
      ${pfield({ id: 'username', label: 'Username', value: e.username, ph: 'Often your email address' })}
      ${pfield({ id: 'password', label: 'Password', type: 'password', ph: e.password ? 'Saved. Leave empty to keep it' : 'App password', ac: 'new-password' })}
      ${pfield({ id: 'fromEmail', label: 'From address', type: 'email', value: e.fromEmail, ph: 'marineedge@company.com', inputmode: 'email' })}
      ${pfield({ id: 'fromName', label: 'From name', value: e.fromName || 'MarineEdge' })}
      <button class="btn" style="margin-top:22px" data-act="save-email"><span class="lbl">Save</span></button></form>
      ${e.configured ? pgroup([prow({ title: 'Send a test email to me', act: 'test-email', accent: true, chev: false, sub: t ? esc(t) : esc(S.me.user.email) }), prow({ title: 'Remove email settings', act: 'clear-email', danger: true, chev: false })]) : ''}
      <p class="sec-foot">Gmail and Microsoft 365 need an app password. The password is stored on your server only.</p>`;
    this.smtpSec = e.security || 'starttls';
  },

  async pServer(pc) {
    const c = await API.config(); this.cfg = c;
    const up = c.update; const disk = c.disk; const sw = c.sweep || {};
    const upLine = !up ? ['Not set up', 'The server updates itself when auto-update is on'] : up.result === 'ok' ? ['Up to date', `Version ${up.commit} · tests passed before it switched · ${up.checked_at ? Fmt.ago(Date.parse(up.checked_at)) : ''}`]
      : [`<span class="c-red">Held back</span>`, `${up.result.replace('_', ' ')} on ${up.commit}: still running ${up.previous}. ${up.detail ? up.detail.slice(0, 160) : ''}`];
    pc.innerHTML = pgroup([`<div class="kv"><span class="k">Updates</span><span class="v">${upLine[0]}<div class="s">${esc(upLine[1])}</div></span></div>`,
      `<div class="kv"><span class="k">Storage</span><span class="v">${disk ? `${disk.free_gb} GB free` : '—'}<div class="s">${c.db_gb != null ? `Database ${c.db_gb} GB · ` : ''}recording pauses below 3 GB</div></span></div>`,
      `<div class="kv"><span class="k">Accounts</span><span class="v">${Fmt.n(c.users)}</span></div>`,
      `<div class="kv"><span class="k">Notifications</span><span class="v">${c.push ? 'Set up' : '<span class="c2">No push keys</span>'}</span></div>`,
      `<div class="kv"><span class="k">Email</span><span class="v">${c.email && c.email.configured ? 'Set up' : '<span class="c2">Not set up</span>'}</span></div>`,
      `<div class="kv"><span class="k">Background checks</span><span class="v">${sw.running ? 'Running now' : sw.last ? Fmt.ago(sw.last) : 'Not yet'}<div class="s">${sw.analysed != null ? `${sw.analysed} ships last time${sw.waiting ? `, ${sw.waiting} waiting` : ''}` : 'Every ship in range is checked, a few at a time'}</div></span></div>`],
      { head: `MarineEdge ${esc(c.version)}` })
      + pgroup([prow({ title: 'Check ships in range now', act: 'job-sweep', accent: true, chev: false, sub: 'Up to 30 seconds of checks on the recorded feed. Free' }),
        prow({ title: 'Re-check watched ships now', act: 'job-refresh', accent: true, chev: false, sub: 'The same as the 30-minute job: new findings become alerts' })], { head: 'Run now' })
      + `<p class="sec-foot">Backups run every night at 03:00 UTC and stay on this server.</p>`;
  },

  /* ================================================================ actions */
  async act(act, el) {
    const form = el.closest('form');
    const val = n => { const i = form && form.querySelector(`[name="${n}"]`); return i ? i.value.trim() : ''; };
    const raw = n => { const i = form && form.querySelector(`[name="${n}"]`); return i ? i.value : ''; };
    switch (act) {
      case 'eye': { const inp = el.parentElement.querySelector('input'); const show = inp.type === 'password'; inp.type = show ? 'text' : 'password'; el.innerHTML = show ? ICON.eyeOff(20) : ICON.eye(20); return; }
      case 'signout': {
        const v = await actionSheet({ title: 'Sign out of MarineEdge?', message: 'Your watched ships and notes stay on the server.', actions: [{ label: 'Sign out', destructive: true, value: 'out' }] });
        if (v !== 'out') return;
        try { const reg = await navigator.serviceWorker.getRegistration(); const sub = reg && await reg.pushManager.getSubscription(); if (sub) { await API.pushUnsubscribe({ endpoint: sub.endpoint }).catch(() => {}); await sub.unsubscribe(); } } catch (e) { /* no push */ }
        try { await API.logout(); } catch (e) { /* signed out anyway */ }
        await App.signedOut(); return;
      }
      case 'save-account': return busy(el, async () => {
        const body = { name: val('name'), email: val('email') };
        if (!body.name) return this.fail(form, { field: 'name', message: 'Enter your name.' });
        if (body.email.toLowerCase() !== S.me.user.email.toLowerCase()) body.currentPassword = raw('currentPassword');
        try { const r = await API.updateMe(body); S.me.user = r.user; App.renderMeButton(); toast('Saved.', 'ok'); App.back(); } catch (e) { this.fail(form, e); }
      });
      case 'save-password': return busy(el, async () => {
        if (!raw('current')) return this.fail(form, { field: 'current', message: 'Enter your current password.' });
        if (!raw('password')) return this.fail(form, { field: 'password', message: 'Choose a new password.' });
        try { await API.changePassword(raw('current'), raw('password')); toast('Password changed. Your other devices were signed out.', 'ok'); App.back(); } catch (e) { this.fail(form, e.field === 'current' || e.field === 'password' ? e : { ...e, field: e.code === 'bad_password' ? 'current' : e.field }); }
      });
      case 'end-session': {
        const v = await actionSheet({ title: el.dataset.name, actions: [{ label: 'Sign out this device', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { await API.endSession(+el.dataset.id); toast('Signed out.', 'ok'); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'end-others': {
        const v = await actionSheet({ title: 'Sign out everywhere else?', message: 'This device stays signed in.', actions: [{ label: 'Sign out other devices', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { const r = await API.endOtherSessions(); toast(`Signed out ${Fmt.plural(r.signedOut, 'device')}.`, 'ok'); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'theme': App.applyTheme(el.dataset.v, true); return this.refresh();
      case 'times': {
        const local = el.dataset.v === 'local'; Fmt.utc = !local;
        S.me.user.prefs = { ...(S.me.user.prefs || {}), timeLocal: local };
        API.updateMe({ prefs: { timeLocal: local } }).catch(e => toast(e.message, 'err'));
        Screens.onTheme(); return this.refresh();
      }
      case 'push-toggle': {
        if (el.disabled) return;
        const on = el.getAttribute('aria-checked') === 'true';
        await busy(el, async () => { if (on) await this.disablePush(); else await this.enablePush(); });
        return this.refresh();
      }
      case 'push-min': {
        const v = el.dataset.v; S.me.user.prefs = { ...(S.me.user.prefs || {}), pushMin: v };
        try { await API.updateMe({ prefs: { pushMin: v } }); } catch (e) { toast(e.message, 'err'); }
        return this.refresh();
      }
      case 'push-test': return busy(el, async () => { try { const r = await API.pushTest(); toast(r.sent ? 'Sent. It should arrive in a few seconds.' : 'The push service didn’t accept it. Turn notifications off and on again.', r.sent ? 'ok' : 'err'); } catch (e) { toast(e.message, 'err'); } });
      case 'region': {
        const v = el.dataset.v; S.me.user.prefs = { ...(S.me.user.prefs || {}), region: v };
        try { await API.updateMe({ prefs: { region: v } }); } catch (e) { toast(e.message, 'err'); }
        if (S.region !== v) { S.region = v; store.set('region', v); Screens.renderRegionName(); S.overview = null; S.live = []; MapView.setLive([]); Screens.homeAt = 0; Screens.fitRegion(false); Screens.refreshHome(true); }
        return this.refresh();
      }
      case 'unwatch': {
        const imo = +el.dataset.imo;
        const v = await actionSheet({ title: `Stop watching ${el.dataset.name}?`, actions: [{ label: 'Stop watching', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { const r = await API.setWatchlist((S.me.watchlist || []).filter(i => i !== imo)); S.me.watchlist = r.watchlist; S.watching = (S.watching || []).filter(w => w.imo !== imo); Screens.homeAt = 0; this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'intro': Pages.clear(); store.del('seenWelcome'); Onboarding.tour(); return;

      // team
      case 'inv-role': $$('[data-act="inv-role"]', form).forEach(b => b.setAttribute('aria-pressed', b === el ? 'true' : 'false')); return;
      case 'create-invite': return busy(el, async () => {
        const role = (form.querySelector('[data-act="inv-role"][aria-pressed="true"]') || {}).dataset.v || 'analyst';
        try { const r = await API.invite(val('email'), role); this.lastInvite = { ...r, url: location.origin + location.pathname + r.link.slice(r.link.indexOf('#')) }; this.team = null; this.refresh(); } catch (e) { this.fail(form, e); }
      });
      case 'invite-again': this.lastInvite = null; return this.refresh();
      case 'revoke-invite': {
        const v = await actionSheet({ title: 'Cancel this invite?', message: 'The link stops working.', actions: [{ label: 'Cancel invite', destructive: true, value: 'x' }], cancel: 'Keep it' });
        if (v !== 'x') return;
        try { await API.revokeInvite(+el.dataset.id); toast('Invite cancelled.'); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'set-role': {
        if (el.getAttribute('aria-pressed') === 'true') return;
        try { const u = await API.setMember(+el.dataset.uid, { role: el.dataset.v }); this.patchMember(u); toast(`${u.name} is now ${ROLE_LABEL[u.role] === 'Admin' ? 'an admin' : 'an analyst'}.`, 'ok'); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'set-status': {
        if (el.disabled) return;
        const on = el.getAttribute('aria-checked') === 'true';
        if (on) { const v = await actionSheet({ title: 'Turn off this account?', message: 'They are signed out everywhere and can’t sign in until you turn it back on.', actions: [{ label: 'Turn off', destructive: true, value: 'x' }] }); if (v !== 'x') return; }
        try { const u = await API.setMember(+el.dataset.uid, { status: on ? 'disabled' : 'active' }); this.patchMember(u); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'reset-link': return busy(el, async () => {
        try { const r = await API.resetLink(+el.dataset.uid); this.lastReset = { uid: +el.dataset.uid, url: location.origin + location.pathname + r.link.slice(r.link.indexOf('#')), expires: r.expires }; this.refresh(); } catch (e) { toast(e.message, 'err'); }
      });
      case 'share-link': { const r = await shareOrCopy({ title: el.dataset.title || 'MarineEdge', url: el.dataset.url }); if (r === 'copied') toast('Link copied.', 'ok'); else if (r === 'failed') toast("Couldn't copy the link.", 'err'); return; }
      case 'copy-link': { const ok = await copyText(el.dataset.url); toast(ok ? 'Link copied.' : "Couldn't copy the link.", ok ? 'ok' : 'err'); return; }
      case 'remove-member': {
        const v = await actionSheet({ title: `Remove ${el.dataset.name}?`, message: 'They lose access at once. Their notes stay.', actions: [{ label: 'Remove from team', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { await API.removeMember(+el.dataset.uid); this.team = null; toast(`${el.dataset.name} was removed.`); App.back(); } catch (e) { toast(e.message, 'err'); }
        return;
      }

      // data sources
      case 'save-key': return busy(el, async () => {
        const name = el.dataset.name; const v = ($(`#key-${name}`) || {}).value; const key = (v || '').trim();
        if (key.length < 8) { toast('Paste the whole key first.', 'err'); return; }
        try { await API.setKey(name, key); toast({ aisstream: 'Saved. Recording starts within a minute.', datalastic: 'Saved. Ship pages now offer 12 months of history.', gfw: 'Saved. Cross-check works on every ship page.' }[name] || 'Saved.', 'ok'); S.me = await API.me(); this.refresh(); } catch (e) { toast(e.message, 'err'); }
      });
      case 'clear-key': {
        const name = el.dataset.name;
        const v = await actionSheet({ title: `Remove the ${titleCase(name)} key?`, message: name === 'aisstream' ? 'Recording stops until a new key is saved.' : '', actions: [{ label: 'Remove key', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { await API.setKey(name, null); S.me = await API.me(); toast('Key removed.'); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'use-free': return busy(el, async () => { try { await API.setProvider('aisstream'); toast('The free feed is the main source now.', 'ok'); S.analyses.clear(); this.refresh(); } catch (e) { toast(e.message, 'err'); } });
      case 'test-provider': return busy(el, async () => {
        try { const r = await API.testProvider(); this.testResult = r.ok ? `Works · ${titleCase(r.provider)} answered in ${r.ms} ms${r.matches != null ? ` · ${r.matches} matches for a test search` : ''}` : `Failed: ${r.error}`; } catch (e) { this.testResult = `Failed: ${e.message}`; }
        this.refresh();
      });
      case 'first-pull': return busy(el, async () => {
        const txt = ($('#pullImos') || {}).value || ''; const imos = (txt.match(/\b\d{7}\b/g) || []).slice(0, 10).map(Number);
        if (!imos.length) { toast('Type at least one 7-digit IMO number.', 'err'); return; }
        const v = await actionSheet({ title: `Buy 12 months for ${Fmt.plural(imos.length, 'ship')}?`, message: 'Each ship uses Datalastic credits once.', actions: [{ label: 'Buy', bold: true, value: 'y' }] });
        if (v !== 'y') return;
        try { const rows = await API.firstPull(imos); this.pullResult = { input: txt, rows }; } catch (e) { toast(e.message, 'err'); }
        this.refresh();
      });
      case 'sanctions-now': {
        if (this.sanc && this.sanc.running) return;
        this.sanc = { running: true }; this.refresh();
        try { const r = await API.jobSanctions(); this.sanc = { result: Object.entries(r).filter(([k]) => k !== 'rows_written').map(([k, v]) => `${k}: ${typeof v === 'number' ? Fmt.n(v) : v}`).join(' · ') }; toast('Sanctions lists downloaded.', 'ok'); }
        catch (e) { this.sanc = { result: `Failed: ${e.message}` }; }
        return this.refresh();
      }
      case 'save-rules': return busy(el, async () => {
        const over = {}; let bad = null;
        $$('#pages input.num').forEach(i => { const v = parseFloat(i.value); if (!isFinite(v) || v < 0) { bad = i; return; } (over[i.dataset.g] = over[i.dataset.g] || {})[i.dataset.k] = v; });
        $$('#pages [data-act="rule-switch"]').forEach(b => { (over[b.dataset.g] = over[b.dataset.g] || {})[b.dataset.k] = b.getAttribute('aria-checked') === 'true'; });
        if (bad) { bad.focus(); toast('Every value must be a number of zero or more.', 'err'); return; }
        try { const r = await API.saveRules(over); S.rules = r.rules; S.analyses.clear(); toast('Saved. Ships are re-checked with the new rules.', 'ok'); this.refresh(); } catch (e) { toast(e.message, 'err'); }
      });
      case 'reset-rules': {
        const v = await actionSheet({ title: 'Back to the default rules?', actions: [{ label: 'Use the defaults', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { const r = await API.resetRules(); S.rules = r.rules; S.analyses.clear(); toast('Default rules restored.', 'ok'); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'rule-switch': el.setAttribute('aria-checked', String(el.getAttribute('aria-checked') !== 'true')); return;   // saved with "Save and re-check"
      case 'zone': {
        const on = el.getAttribute('aria-checked') === 'true';
        el.setAttribute('aria-checked', String(!on));
        try { await API.setZone(el.dataset.id, !on); S.analyses.clear(); try { S.zones = await API.zones(); MapView.setZones(S.zones); } catch (e) { /* map keeps the old zones */ } }
        catch (e) { el.setAttribute('aria-checked', String(on)); toast(e.message, 'err'); }
        return;
      }
      case 'map-zoom': this.mapZoom = +el.dataset.v; $$('[data-act="map-zoom"]').forEach(b => { const on = b === el; b.setAttribute('aria-checked', on); b.lastElementChild.style.visibility = on ? 'visible' : 'hidden'; }); return;
      case 'map-download': return busy(el, async () => { try { await API.mapsDownload(this.mapZoom || null); toast('Download started on the server.', 'ok'); this.refresh(); } catch (e) { toast(e.message, 'err'); } });
      case 'map-remove': {
        const v = await actionSheet({ title: 'Remove the detailed map?', message: 'The Natural Earth map stays.', actions: [{ label: 'Remove', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { await API.mapsRemove(); S.maps = { installed: false, url: null }; MapView.setDetail(null); App.renderAttribution(); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'smtp-sec': this.smtpSec = el.dataset.v; $$('[data-act="smtp-sec"]').forEach(b => b.setAttribute('aria-pressed', b === el ? 'true' : 'false')); if (form && el.dataset.v === 'ssl' && val('port') === '587') form.querySelector('[name=port]').value = '465'; if (form && el.dataset.v === 'starttls' && val('port') === '465') form.querySelector('[name=port]').value = '587'; return;
      case 'save-email': return busy(el, async () => {
        const body = { host: val('host'), port: parseInt(val('port'), 10) || 587, security: this.smtpSec || 'starttls', username: val('username'), password: raw('password'), fromEmail: val('fromEmail'), fromName: val('fromName') };
        if (!body.host) return this.fail(form, { field: 'host', message: 'Enter the SMTP server.' });
        if (!body.fromEmail) return this.fail(form, { field: 'fromEmail', message: 'Enter the address emails come from.' });
        try { await API.saveEmail(body); toast('Saved. Send yourself a test.', 'ok'); this.emailTest = null; this.refresh(); } catch (e) { this.fail(form, e); }
      });
      case 'test-email': return busy(el, async () => {
        try { const r = await API.testEmail(S.me.user.email); this.emailTest = r.ok ? `Sent to ${r.to}. Check the inbox (and spam).` : `Failed: ${r.error}`; } catch (e) { this.emailTest = `Failed: ${e.message}`; }
        this.refresh();
      });
      case 'clear-email': {
        const v = await actionSheet({ title: 'Remove the email settings?', message: 'Reset codes and invites stop going out by email.', actions: [{ label: 'Remove', destructive: true, value: 'x' }] });
        if (v !== 'x') return;
        try { await API.saveEmail({ clear: true }); this.refresh(); } catch (e) { toast(e.message, 'err'); }
        return;
      }
      case 'job-sweep': return busy(el, async () => { try { const r = await API.jobSweep(30); toast(r.skipped ? 'A check is already running.' : `Checked ${Fmt.plural(r.analysed, 'ship')}${r.candidates > r.analysed ? `, ${r.candidates - r.analysed} still waiting` : ''}.`, 'ok'); Screens.homeAt = 0; this.refresh(); } catch (e) { toast(e.message, 'err'); } });
      case 'job-refresh': return busy(el, async () => { try { const r = await API.jobRefresh(); toast(`Re-checked ${Fmt.plural(r.vessels, 'ship')}: ${Fmt.plural(r.new_alerts, 'new alert')}${r.pushed ? `, ${r.pushed} pushed` : ''}.`, 'ok'); } catch (e) { toast(e.message, 'err'); } });
      default: return;
    }
  },
  patchMember(u) { if (this.team) { const i = this.team.users.findIndex(x => x.id === u.id); if (i >= 0) this.team.users[i] = u; } },
};
