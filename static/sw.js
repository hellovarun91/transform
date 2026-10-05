const CACHE = 'transform-v1';
const SHELL = ['/', '/static/styles.css', '/static/app.js', '/static/manifest.json', '/static/icon.svg', '/static/icon-180.png',
  '/static/views/today.js', '/static/views/plan.js', '/static/views/weight.js', '/static/views/history.js', '/static/views/settings.js'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;
  e.respondWith(
    fetch(e.request).then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return res; })
      .catch(() => caches.match(e.request).then((r) => r || caches.match('/')))
  );
});
self.addEventListener('push', (e) => {
  let data = { title: 'Transform', body: '', url: '/#today', tag: 'transform' };
  try { data = { ...data, ...e.data.json() }; } catch {}
  e.waitUntil(self.registration.showNotification(data.title, { body: data.body, tag: data.tag, icon: '/static/icon-180.png', badge: '/static/icon-180.png', data: { url: data.url } }));
});
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/#today';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
