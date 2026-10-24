/* Service worker. The app shell (code, styles, map fonts, Natural Earth) is cached so MarineEdge opens
   instantly and without signal; API answers are network-first with the last good answer as a fallback,
   so ships you opened before still show offline. The detailed map is never cached here (it's large and
   read with range requests). Bump VERSION on every change to the shell. */
const VERSION = 'marineedge-1.0.0';
const SHELL = [
  './', './index.html', './manifest.webmanifest', './css/app.css',
  './js/theme.js', './js/ui.js', './js/api.js', './js/map.js', './js/pmtiles.js', './js/onboarding.js', './js/screens.js', './js/profile.js', './js/app.js',
  './vendor/maplibre/maplibre-gl-csp.js', './vendor/maplibre/maplibre-gl-csp-worker.js', './vendor/maplibre/maplibre-gl.css',
  './geo/ne.json', './icons/icon.svg', './icons/icon-192.png', './icons/apple-touch-icon.png',
];
const NO_STORE = ['/api/auth/', '/api/admin/', '/api/me/sessions', '/report.pdf', '/report.html'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => !k.startsWith(VERSION)).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/tiles/')) return;                      // range requests straight to the server
  if (url.pathname.startsWith('/api/')) {
    if (NO_STORE.some(p => url.pathname.includes(p))) return;
    e.respondWith(fetch(req).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION + '-api').then(c => c.put(req, copy)); }
      return r;
    }).catch(() => caches.match(req).then(r => r || new Response(JSON.stringify({ error: 'offline' }), { status: 503, headers: { 'Content-Type': 'application/json' } }))));
    return;
  }
  if (url.pathname.startsWith('/fonts/')) {                            // map glyphs: cache as they're used
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(res => { if (res.ok) { const copy = res.clone(); caches.open(VERSION + '-fonts').then(c => c.put(req, copy)); } return res; })));
    return;
  }
  // the shell: cache first, then network; navigations fall back to the cached index
  e.respondWith(caches.match(req, { ignoreSearch: true }).then(r => r || fetch(req).catch(() => req.mode === 'navigate' ? caches.match('./index.html') : Response.error())));
});

self.addEventListener('message', e => {
  if (e.data === 'signed-out') e.waitUntil(caches.delete(VERSION + '-api'));
});

self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { title: 'MarineEdge', body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || 'MarineEdge', {
    body: d.body || '', tag: d.tag, icon: './icons/icon-192.png', badge: './icons/icon-192.png', data: { url: d.url || '#/alerts' },
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const hash = (e.notification.data && e.notification.data.url) || '#/alerts';
  const target = new URL('./' + (hash.startsWith('#') ? hash : '#/alerts'), self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    for (const c of list) { if ('focus' in c) { c.postMessage({ go: hash }); return c.focus(); } }   // the open app routes itself
    return self.clients.openWindow(target);
  }));
});
