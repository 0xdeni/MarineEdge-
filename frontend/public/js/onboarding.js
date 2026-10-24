/* Before sign-in: the welcome (animated mark), three intro pages, and the account screens —
   sign in, create account (invite or server setup code), forgot password, reset, accept an invite. */
'use strict';

/* The welcome and account screens are always night: the browser's bars (theme-color) follow them, not the app theme. */
function chromeColor(c) { const m = document.querySelector('meta[name=theme-color]'); if (m) m.content = c; }

const Onboarding = {
  el: null, played: false, page: 0, current: null,

  root() {
    if (!this.el) {
      this.el = $('#ob');
      this.el.innerHTML = `<div class="bgmap" style="background-image:url('img/welcome-night.jpg')"></div><div class="shade"></div><div class="scr-host"></div>`;
      const img = new Image(); img.onload = () => this.el.querySelector('.bgmap').classList.add('on'); img.src = 'img/welcome-night.jpg';
      this.el.addEventListener('click', e => this.click(e));
      this.el.addEventListener('submit', e => { e.preventDefault(); this.submit(e.target); });
      this.el.addEventListener('input', e => this.input(e));
    }
    this.el.hidden = false;
    chromeColor('#000000');
    return this.el;
  },

  show(r, prev) {
    this.touring = false;
    const el = this.root();
    el.style.opacity = '';
    const host = el.querySelector('.scr-host');
    const html = this.render(r);
    if (html == null) return;
    const old = host.querySelector('.scr');
    const scr = document.createElement('div');
    scr.className = 'scr';
    scr.style.cssText = 'position:absolute;inset:0;';
    scr.innerHTML = html;
    host.appendChild(scr);
    if (old) {
      old.style.transition = 'opacity 200ms var(--ease)'; old.style.opacity = '0'; old.style.pointerEvents = 'none';
      setTimeout(() => old.remove(), 220);
      if (!reduceMotion()) { scr.animate([{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], { duration: 380, easing: 'cubic-bezier(0.32,0.72,0,1)' }); }
    }
    this.current = r.name;
    el.classList.toggle('dimmed', r.name !== 'welcome');     // the chart stays behind the forms, quietly
    if (r.name === 'welcome') {
      el.classList.remove('play', 'shown');
      void el.offsetWidth;
      el.classList.add(this.played ? 'shown' : 'play');
      this.played = true;
    } else { el.classList.remove('play'); el.classList.add('shown'); }
    if (r.name === 'intro') this.initPager(scr);
    this.after(r, scr);
    const f = scr.querySelector('[autofocus]');
    if (f && !/iPhone|iPad/.test(navigator.userAgent)) setTimeout(() => f.focus(), 350);
  },

  close(fresh) {
    if (!this.el || this.el.hidden) return;
    const el = this.el;
    const a = document.activeElement; if (a && el.contains(a)) a.blur();      // the keyboard goes before the fade, not after
    chromeColor(document.documentElement.dataset.theme === 'light' ? '#F2F2F7' : '#000000');
    if (reduceMotion() || !fresh) { el.hidden = true; el.querySelector('.scr-host').innerHTML = ''; return; }
    el.style.transition = 'opacity 520ms var(--ease)'; el.style.opacity = '0';
    setTimeout(() => { el.hidden = true; el.style.transition = ''; el.style.opacity = ''; el.querySelector('.scr-host').innerHTML = ''; }, 540);
  },

  offline() {
    this.root().querySelector('.scr-host').innerHTML = `<div class="scr" style="position:absolute;inset:0"><div class="stage"><div class="grow"></div>
      ${logoSVG(64, 'off')}<h1 class="t-title" style="margin-top:18px">You're offline</h1><p class="tagline">MarineEdge needs a connection to sign in. Check your signal and try again.</p>
      <div class="cta"><button class="btn tap" data-a="retry">Try again</button></div></div></div>`;
    this.el.classList.add('shown', 'dimmed');
  },

  /* ---------------------------------------------------------------- screens */
  render(r) {
    const st = S.authState || {};
    switch (r.name) {
      case 'welcome': return this.welcome();
      case 'intro': return this.intro();
      case 'signin': return this.signin(st);
      case 'signup': return this.signup(st, null);
      case 'forgot': return this.forgot(st);
      case 'invite': this.loadInvite(r.code); return this.waiting('Opening your invite…');
      case 'reset': this.loadReset(r.token); return this.waiting('Checking your link…');
      default: return this.welcome();
    }
  },
  waiting(msg) {
    return `<div class="stage"><div class="grow"></div><div style="display:flex;align-items:center;gap:12px;justify-content:center;color:rgba(235,235,245,0.7)"><span class="spin"></span>${esc(msg)}</div><div class="grow"></div></div>`;
  },
  welcome() {
    store.set('seenWelcome', true);
    return `<div class="stage">
      <div class="grow"></div>
      <div class="lg-wrap">${logoSVG(84, 'wl')}</div>
      <h1 class="wordmark rise-1" style="margin-top:22px"><span class="lt">Marine</span>Edge</h1>
      <p class="tagline rise-2">Check any ship's last twelve months before you fix it: every voyage, every red flag, with the evidence.</p>
      <div class="cta rise-3">
        <button class="btn tap" data-go="#/intro">Get started</button>
        <button class="btn secondary tap" data-go="#/signin">I have an account</button>
      </div>
      <p class="legal rise-3">For teams screening ships in the Black Sea, the Eastern Mediterranean and the Gulf.</p>
    </div>`;
  },
  /* the intro again, from Profile › About, without signing out */
  tour() {
    this.touring = true;
    const el = this.root(); el.style.opacity = '';
    const host = el.querySelector('.scr-host');
    host.innerHTML = '';
    const scr = document.createElement('div'); scr.className = 'scr'; scr.style.cssText = 'position:absolute;inset:0;';
    scr.innerHTML = this.intro(true);
    host.appendChild(scr);
    el.classList.remove('play'); el.classList.add('shown', 'dimmed');
    if (!reduceMotion()) el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 320, easing: 'ease' });
    this.initPager(scr);
  },
  intro(tour = false) {
    this.page = 0;
    return `<div class="intro-top"><div class="mini">${logoSVG(24, 'in')}MarineEdge</div><button class="btn plain" ${tour ? 'data-a="tour-done"' : 'data-go="#/signin"'} style="color:rgba(235,235,245,0.8)">${tour ? 'Done' : 'Skip'}</button></div>
    <div class="pager" id="pager">
      <section class="pg" aria-label="Every ship, its whole year">
        <div class="art">${this.artVoyages()}</div>
        <h2>Every ship,<br>its whole year.</h2>
        <p>Search by name, IMO or MMSI, even by a name it no longer uses. See twelve months of voyages, port to port, on one map.</p>
      </section>
      <section class="pg" aria-label="Red flags, with the evidence">
        <div class="art">${this.artFlags()}</div>
        <h2>Red flags,<br>with the evidence.</h2>
        <p>Seven checks run on every voyage. Each finding shows when, where and the positions around it, so you can judge it yourself.</p>
      </section>
      <section class="pg" aria-label="Watch ships, hear first">
        <div class="art">${this.artWatch()}</div>
        <h2>Watch ships.<br>Hear first.</h2>
        <p>Star the ships you fix or charter. MarineEdge checks them again every 30 minutes and tells you on your iPhone. A PDF report is one tap away.</p>
      </section>
    </div>
    <div class="intro-bottom">
      <div class="dots" role="tablist" aria-label="Intro pages"><i class="on"></i><i></i><i></i></div>
      <div id="introCta"><button class="btn tap" data-a="next">Continue</button></div>
    </div>`;
  },
  artVoyages() {
    // a real map (Natural Earth, rendered from the app's own style) with two voyages drawn through the water
    return `<div class="art-card"><div class="art-map" style="background-image:url('img/intro-map.jpg')">
      <svg viewBox="0 0 320 210" aria-hidden="true">
        <path class="track-anim" pathLength="1" d="M16.4 165.3 C19.4 162.8, 27.3 156.8, 34.5 150.7 C41.8 144.6, 49.6 135.0, 60.1 128.8 C70.6 122.5, 84.5 117.7, 97.3 113.0 C110.0 108.2, 124.0 105.0, 136.8 100.2 C149.5 95.4, 163.1 89.5, 173.9 84.2 C184.8 78.8, 194.5 72.5, 201.8 68.0 C209.1 63.5, 215.0 59.0, 217.6 57.2" fill="none" stroke="#64D2FF" stroke-width="2.6" stroke-linecap="round"/>
        <path class="track-anim" pathLength="1" style="animation-delay:1000ms" d="M217.6 57.9 C219.6 60.9, 225.0 69.6, 229.7 76.1 C234.4 82.6, 239.8 89.8, 246.0 97.0 C252.2 104.2, 259.7 112.2, 266.9 119.3 C274.0 126.4, 282.4 134.1, 288.9 139.7 C295.5 145.4, 303.5 151.2, 306.4 153.5" fill="none" stroke="#BF5AF2" stroke-width="2.6" stroke-linecap="round"/>
        <circle class="pt-anim" style="animation-delay:150ms" cx="16.4" cy="165.3" r="4.5" fill="#0B1A2A" stroke="#C7CED8" stroke-width="1.6"/>
        <circle class="pt-anim" style="animation-delay:1000ms" cx="217.6" cy="57.2" r="4.5" fill="#0B1A2A" stroke="#C7CED8" stroke-width="1.6"/>
        <circle class="pt-anim" style="animation-delay:2000ms" cx="306.4" cy="153.5" r="6" fill="#0A84FF" stroke="#fff" stroke-width="2"/>
      </svg></div>
      <div class="art-cap"><div class="t">Twelve months, one map</div><div class="s">One colour per voyage, port to port, up to where the ship is now</div></div></div>`;
  },
  artFlags() {
    const card = (bg, fg, icon, t, s) => `<div class="fcard"><div class="ic" style="background:${bg};color:${fg}">${icon}</div><div><div class="t">${t}</div><div class="s">${s}</div></div></div>`;
    return `<div class="flagcards">
      ${card('rgba(255,69,58,0.18)', '#FF6961', ICON.antenna(18), 'Went dark at sea', 'AIS off for hours, near a sensitive zone')}
      ${card('rgba(255,69,58,0.18)', '#FF6961', ICON.pin(18), 'Called at a sanctioned port', 'Crimea, Syria, Iran and other listed zones')}
      ${card('rgba(255,69,58,0.18)', '#FF6961', ICON.ship(18), 'Stopped beside another ship', 'Both under one knot, outside port limits')}
      ${card('rgba(255,159,10,0.18)', '#FFB340', ICON.wave(18), 'Draught changed at sea', 'An indicator, never proof on its own')}
    </div>`;
  },
  artWatch() {
    return `<div class="phone-lock">
      <div class="notif"><div class="app">${logoSVG(38, 'nt')}</div><div style="flex:1;min-width:0"><div class="hd"><span>MARINEEDGE</span><span>now</span></div>
        <div class="t">New red flag on a ship you watch</div><div class="s">Tap to see when, where and the positions around it.</div></div></div>
      <div class="watch-demo"><span class="star">${ICON.starFill(22)}</span><div><div style="font-weight:600;font-size:0.941rem">Watching</div><div style="font-size:0.765rem;color:rgba(235,235,245,0.6)">Checked again every 30 minutes</div></div></div>
    </div>`;
  },
  initPager(scr) {
    const pager = scr.querySelector('#pager'); const dots = $$('.dots i', scr); const pgs = $$('.pg', scr);
    const setPage = i => {
      this.page = i;
      dots.forEach((d, k) => d.classList.toggle('on', k === i));
      pgs.forEach((p, k) => p.classList.toggle('on', k === i));
      scr.querySelector('#introCta').innerHTML = i < 2 ? `<button class="btn tap" data-a="next">Continue</button>`
        : this.touring ? `<button class="btn tap" data-a="tour-done">Done</button>`
          : `<div style="display:grid;gap:12px"><button class="btn tap" data-go="#/signup">Create account</button><button class="btn secondary tap" data-go="#/signin">Sign in</button></div>`;
    };
    requestAnimationFrame(() => setPage(0));
    let t = 0;
    pager.addEventListener('scroll', () => { clearTimeout(t); t = setTimeout(() => { const i = Math.round(pager.scrollLeft / pager.clientWidth); if (i !== this.page) setPage(i); }, 60); }, { passive: true });
    this._setPage = setPage; this._pager = pager;
  },

  field({ id, label, type = 'text', ac = '', value = '', ph = '', icon = '', hint = '', autofocus = false, inputmode = '', meter = false, pattern = '' }) {
    const eye = type === 'password' ? `<button type="button" class="eye" data-a="eye" aria-label="Show password">${ICON.eye(20)}</button>` : '';
    return `<div class="fld" data-f="${id}"><label for="f-${id}">${esc(label)}</label>
      <div class="inp">${icon ? `<span class="ico">${icon}</span>` : ''}<input id="f-${id}" name="${id}" type="${type}" ${ac ? `autocomplete="${ac}"` : ''} ${inputmode ? `inputmode="${inputmode}"` : ''} ${pattern ? `pattern="${pattern}"` : ''}
        value="${esc(value)}" placeholder="${esc(ph)}" ${autofocus ? 'autofocus' : ''} autocapitalize="${type === 'text' && id === 'name' ? 'words' : 'off'}" spellcheck="false">${eye}</div>
      ${meter ? '<div class="meter" aria-hidden="true"><i></i><i></i><i></i><i></i></div>' : ''}
      ${hint ? `<p class="hint">${hint}</p>` : ''}<p class="err" hidden></p></div>`;
  },
  topbar(back = '#/welcome') {
    return `<div class="topbar"><button class="back-btn" data-go="${back}" type="button">${ICON.back(20)}<span>Back</span></button><span></span></div>`;
  },
  signin(st) {
    const banner = st.setup ? `<div class="note-box" style="margin-top:18px">This server has no accounts yet. <button type="button" data-go="#/signup" style="color:#409CFF;font-weight:600">Set up the first one</button>, with the admin password from the server setup.</div>` : '';
    return `<div class="auth">${this.topbar('#/welcome')}<div class="inner">
      ${logoSVG(52, 'si')}
      <h1>Sign in</h1><p class="lead">Welcome back.</p>${banner}
      <form data-form="signin" novalidate>
        ${this.field({ id: 'email', label: 'Email', type: 'email', ac: 'username', inputmode: 'email', icon: ICON.mail(17), ph: 'you@company.com', autofocus: true })}
        ${this.field({ id: 'password', label: 'Password', type: 'password', ac: 'current-password', icon: ICON.lock(17) })}
        <div style="display:flex;justify-content:flex-end;margin-top:6px"><button type="button" class="btn plain" data-go="#/forgot" style="padding-right:4px">Forgot password?</button></div>
        <div class="formerr" hidden></div>
        <div class="sticky"><button class="btn tap" type="submit"><span class="lbl">Sign in</span></button>
        <p class="alt">New here? <button type="button" data-go="#/signup">Create an account</button></p></div>
      </form></div></div>`;
  },
  signup(st, inv) {
    const setup = !!st.setup;
    const title = setup ? 'Set up MarineEdge' : inv ? 'Join your team' : 'Create your account';
    const lead = setup ? "You're the first person on this server, so your account becomes the owner. You'll need the admin password chosen when the server was set up."
      : inv ? `${inv.invitedBy ? esc(inv.invitedBy) + ' invited you' : "You've been invited"}${inv.role === 'admin' ? ' as an admin' : ''}. Choose a password to finish.`
        : 'MarineEdge accounts are by invitation. Paste the invite link or code you received from your admin.';
    return `<div class="auth">${this.topbar(inv ? '#/welcome' : '#/signin')}<div class="inner">
      ${logoSVG(52, 'su')}
      <h1>${title}</h1><p class="lead">${lead}</p>
      <form data-form="signup" novalidate ${inv ? `data-invite="${esc(inv.code)}"` : ''}>
        ${this.field({ id: 'name', label: 'Your name', ac: 'name', icon: ICON.person(17), ph: 'First and last name', autofocus: true })}
        ${this.field({ id: 'email', label: 'Email', type: 'email', ac: 'username', inputmode: 'email', icon: ICON.mail(17), ph: 'you@company.com', value: inv && inv.email ? inv.email : '' })}
        ${this.field({ id: 'password', label: 'Password', type: 'password', ac: 'new-password', icon: ICON.lock(17), meter: true, hint: `At least ${(st.minPassword || 10)} characters. A few unrelated words make a strong one.` })}
        ${setup ? this.field({ id: 'setupCode', label: 'Server admin password', type: 'password', ac: 'off', icon: ICON.key(17), hint: 'The ADMIN_TOKEN from the setup file. You used it to sign in before accounts existed.' }) : ''}
        ${!setup && !inv ? this.field({ id: 'invite', label: 'Invite code', ac: 'off', icon: ICON.link(17), ph: 'Paste the link or code' }) : ''}
        <div class="formerr" hidden></div>
        <div class="sticky"><button class="btn tap" type="submit"><span class="lbl">${setup ? 'Create owner account' : 'Create account'}</span></button>
        <p class="alt">Already have an account? <button type="button" data-go="#/signin">Sign in</button></p></div>
      </form></div></div>`;
  },
  forgot(st, step = 'email', email = '') {
    if (step === 'code') {
      return `<div class="auth">${this.topbar('#/signin')}<div class="inner">
        <h1>Check your email</h1><p class="lead">If <b>${esc(email)}</b> has an account, a 6-digit code is on its way. It works for 30 minutes.</p>
        <form data-form="reset-code" data-email="${esc(email)}" novalidate>
          ${this.field({ id: 'code', label: 'Code', ac: 'one-time-code', inputmode: 'numeric', icon: ICON.key(17), ph: '6 digits', autofocus: true })}
          ${this.field({ id: 'password', label: 'New password', type: 'password', ac: 'new-password', icon: ICON.lock(17), meter: true, hint: `At least ${st.minPassword || 10} characters.` })}
          <div class="formerr" hidden></div>
          <div class="sticky"><button class="btn tap" type="submit"><span class="lbl">Save and sign in</span></button>
          <p class="alt">No email? <button type="button" data-a="resend" data-email="${esc(email)}">Send another code</button></p></div>
        </form></div></div>`;
    }
    if (step === 'nomail') {
      return `<div class="auth">${this.topbar('#/signin')}<div class="inner">
        <h1>Ask your admin</h1><p class="lead">Email isn't set up on this server yet, so it can't send you a code.</p>
        <div class="note-box">An admin can make you a reset link in a few taps: <b>Profile › Team › your name › Send a password reset link</b>. Open the link on this phone to choose a new password.</div>
        <div class="sticky"><button class="btn secondary tap" type="button" data-go="#/signin">Back to sign in</button></div></div></div>`;
    }
    return `<div class="auth">${this.topbar('#/signin')}<div class="inner">
      <h1>Reset your password</h1><p class="lead">Enter your account's email. We'll send a 6-digit code to choose a new password.</p>
      <form data-form="forgot" novalidate>
        ${this.field({ id: 'email', label: 'Email', type: 'email', ac: 'username', inputmode: 'email', icon: ICON.mail(17), ph: 'you@company.com', autofocus: true })}
        <div class="formerr" hidden></div>
        <div class="sticky"><button class="btn tap" type="submit"><span class="lbl">Send code</span></button></div>
      </form></div></div>`;
  },
  resetLink(info, token) {
    if (!info.valid) {
      return `<div class="auth">${this.topbar('#/signin')}<div class="inner"><h1>This link has expired</h1>
        <p class="lead">Reset links work once, for a limited time. Ask for a new code, or ask your admin for a new link.</p>
        <div class="sticky"><button class="btn tap" type="button" data-go="#/forgot">Send me a code</button></div></div></div>`;
    }
    return `<div class="auth">${this.topbar('#/signin')}<div class="inner">
      <h1>Choose a new password</h1><p class="lead">For <b>${esc(info.email)}</b>. You'll be signed out on other devices.</p>
      <form data-form="reset-link" data-token="${esc(token)}" novalidate>
        <input type="email" name="username" autocomplete="username" value="${esc(info.email)}" hidden>
        ${this.field({ id: 'password', label: 'New password', type: 'password', ac: 'new-password', icon: ICON.lock(17), meter: true, autofocus: true, hint: `At least ${(S.authState && S.authState.minPassword) || 10} characters.` })}
        <div class="formerr" hidden></div>
        <div class="sticky"><button class="btn tap" type="submit"><span class="lbl">Save and sign in</span></button></div>
      </form></div></div>`;
  },
  async loadInvite(code) {
    let info = { valid: false };
    try { info = await API.inviteInfo(code); } catch (e) { info = { valid: false, error: e.message }; }
    if (S.route.name !== 'invite') return;
    let html;
    if (S.me) {
      html = `<div class="auth"><div class="inner"><h1>You're already signed in</h1><p class="lead">This invite is for a new account. Sign out first if you want to use it, or carry on as ${esc(S.me.user.email)}.</p>
        <div class="sticky" style="display:grid;gap:12px"><button class="btn tap" data-a="signout-then-invite" data-code="${esc(code)}">Sign out and accept</button><button class="btn secondary tap" data-go="#/">Keep going</button></div></div></div>`;
    } else if (!info.valid) {
      html = `<div class="auth">${this.topbar('#/welcome')}<div class="inner"><h1>This invite has expired</h1><p class="lead">Invites work once, for seven days. Ask your admin for a new one.</p>
        <div class="sticky"><button class="btn secondary tap" data-go="#/signin">I already have an account</button></div></div></div>`;
    } else {
      html = this.signup({ ...(S.authState || {}), setup: false }, { ...info, code });
    }
    this.replace(html);
  },
  async loadReset(token) {
    let info = { valid: false };
    try { info = await API.resetInfo(token); } catch (e) { info = { valid: false }; }
    if (S.route.name !== 'reset') return;
    this.replace(this.resetLink(info, token));
  },
  replace(html) {
    const scr = this.el.querySelector('.scr-host .scr:last-child'); if (!scr) return;
    scr.innerHTML = html;
    scr.animate && !reduceMotion() && scr.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220 });
  },
  after() { /* reserved for per-screen hooks */ },

  /* ---------------------------------------------------------------- events */
  click(e) {
    const g = e.target.closest('[data-go]');
    if (g) { e.preventDefault(); App.go(g.dataset.go, { replace: true }); return; }
    const a = e.target.closest('[data-a]'); if (!a) return;
    const act = a.dataset.a;
    if (act === 'next') { const i = Math.min(2, this.page + 1); this._pager.scrollTo({ left: i * this._pager.clientWidth, behavior: reduceMotion() ? 'auto' : 'smooth' }); this._setPage(i); }
    else if (act === 'eye') { const inp = a.parentElement.querySelector('input'); const show = inp.type === 'password'; inp.type = show ? 'text' : 'password'; a.innerHTML = show ? ICON.eyeOff(20) : ICON.eye(20); a.setAttribute('aria-label', show ? 'Hide password' : 'Show password'); }
    else if (act === 'retry') location.reload();
    else if (act === 'tour-done') { this.touring = false; store.set('seenWelcome', true); this.close(true); }
    else if (act === 'resend') { busy(a, async () => { try { await API.forgot(a.dataset.email); toast('A new code is on its way.', 'ok'); } catch (err) { toast(err.message, 'err'); } }); }
    else if (act === 'signout-then-invite') { busy(a, async () => { try { await API.logout(); } catch (err) { /* already out */ } S.me = null; location.reload(); }); }
  },
  input(e) {
    const t = e.target;
    const fld = t.closest('.fld');
    if (fld) { fld.querySelector('.inp').classList.remove('bad'); const er = fld.querySelector('.err'); if (er) er.hidden = true; }
    const form = t.closest('form'); if (form) { const fe = form.querySelector('.formerr'); if (fe) fe.hidden = true; }
    if (t.name === 'password' && fld && fld.querySelector('.meter')) {
      const m = fld.querySelector('.meter'); const s = strength(t.value);
      m.className = `meter${t.value ? ' s' + s : ''}`;
    }
    if (t.name === 'invite' && /#\/invite\//.test(t.value)) t.value = t.value.split('#/invite/')[1].trim();
  },
  fail(form, err) {
    if (err.field) {
      const map = { invite: 'invite', setupCode: 'setupCode', email: 'email', password: 'password', name: 'name', code: 'code' };
      const fld = form.querySelector(`[data-f="${map[err.field] || err.field}"]`);
      if (fld) { fld.querySelector('.inp').classList.add('bad'); const er = fld.querySelector('.err'); er.textContent = err.message; er.hidden = false; fld.querySelector('input').focus(); return; }
    }
    const fe = form.querySelector('.formerr'); fe.textContent = err.message; fe.hidden = false;
  },
  async submit(form) {
    const kind = form.dataset.form; const btn = form.querySelector('[type=submit]');
    const v = n => { const i = form.querySelector(`[name="${n}"]`); return i ? i.value.trim() : ''; };
    const pw = n => { const i = form.querySelector(`[name="${n}"]`); return i ? i.value : ''; };
    const need = (n, msg) => { if (!v(n)) { this.fail(form, { field: n, message: msg }); throw new Error('stop'); } };
    try {
      await busy(btn, async () => {
        try {
          if (kind === 'signin') {
            need('email', 'Enter your email.'); need('password', 'Enter your password.');
            await API.login(v('email'), pw('password'));
            await this.finish();
          } else if (kind === 'signup') {
            need('name', 'Enter your name.'); need('email', 'Enter your email.'); need('password', 'Choose a password.');
            const body = { name: v('name'), email: v('email'), password: pw('password') };
            if (form.dataset.invite) body.invite = form.dataset.invite;
            if (form.querySelector('[name=invite]')) { need('invite', 'Paste your invite link or code.'); body.invite = v('invite'); }
            if (form.querySelector('[name=setupCode]')) { need('setupCode', 'Enter the server admin password.'); body.setupCode = pw('setupCode'); }
            await API.signup(body);
            store.set('justJoined', true);
            await this.finish();
          } else if (kind === 'forgot') {
            need('email', 'Enter your email.');
            const r = await API.forgot(v('email'));
            this.replace(r.email ? this.forgot(S.authState || {}, 'code', v('email')) : this.forgot(S.authState || {}, 'nomail'));
          } else if (kind === 'reset-code') {
            need('code', 'Enter the code from the email.'); need('password', 'Choose a new password.');
            await API.reset({ email: form.dataset.email, code: v('code'), password: pw('password') });
            toast('Password changed. Other devices were signed out.', 'ok');
            await this.finish();
          } else if (kind === 'reset-link') {
            need('password', 'Choose a new password.');
            await API.reset({ token: form.dataset.token, password: pw('password') });
            toast('Password changed. Other devices were signed out.', 'ok');
            await this.finish();
          }
        } catch (err) { if (err.message !== 'stop') this.fail(form, err); }
      });
    } catch (e) { /* handled */ }
  },
  async finish() {
    const a = document.activeElement; if (a && a.blur) a.blur();
    const me = await API.me();
    await App.signedIn(me, { fresh: true });
  },
};

function strength(p) {
  if (!p) return 0;
  let s = 0;
  if (p.length >= 10) s++;
  if (p.length >= 14) s++;
  if (/[a-z]/.test(p) && /[A-Z]/.test(p) || /\d/.test(p) && /[^A-Za-z0-9]/.test(p) || /\s|-/.test(p) && p.length >= 16) s++;
  if (p.length >= 20 || (p.length >= 12 && new Set(p.toLowerCase()).size >= 10)) s++;
  if (p.length < 10) return 1;
  return Math.max(1, Math.min(4, s));
}
