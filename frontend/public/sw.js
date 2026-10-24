/* Service worker: app shell cached for offline use, API responses network-first with a cache fallback,
   so the last analysed vessels still open on a phone with no signal. Bump VERSION on every deploy. */
const VERSION = 'marineedge-v0.7.0';
const SHELL = ['./', './index.html', './styles.css', './geo.js', './base.js', './core.js', './api.js', './app.js', './manifest.webmanifest', './icons/icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.pathname.includes('/api/')) {
    e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(VERSION + '-api').then(c => c.put(e.request, copy)); return r; })
      .catch(() => caches.match(e.request).then(r => r || new Response(JSON.stringify({ error: 'offline' }), { status: 503, headers: { 'Content-Type': 'application/json' } }))));
    return;
  }
  if (url.hostname.includes('openfreemap.org')) return;  // tiles: network only, never cached by us
  if (url.hostname.includes('fonts.g') || url.hostname.includes('jsdelivr')) { e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(res => { const copy = res.clone(); caches.open(VERSION + '-fonts').then(c => c.put(e.request, copy)); return res; }).catch(() => new Response('', { status: 204 })))); return; }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});

self.addEventListener('push', e => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch (err) { d = { title: 'MarineEdge', body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || 'MarineEdge', { body: d.body || '', tag: d.tag, icon: './icons/icon-192.png', badge: './icons/icon-192.png', data: { url: d.url || './' } }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const target = new URL((e.notification.data && e.notification.data.url) || './', self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => { for (const c of list) { if ('focus' in c) { c.navigate(target); return c.focus(); } } return self.clients.openWindow(target); }));
});
