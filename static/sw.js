const CACHE_NAME = 'judgment-search-shell-v2';
const SHELL_ASSETS = [
  './static/manifest.json',
  './static/favicon.png'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => {})
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // API 請求一律走網路，不快取
  if (url.pathname.includes('/api/')) return;

  // 網路優先，離線時才退回快取
  event.respondWith(
    fetch(req).catch(() => caches.match(req))
  );
});
