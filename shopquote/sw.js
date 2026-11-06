const CACHE_NAME = 'shopquote-shell-v1';
const APP_ROOT = new URL('./', self.registration.scope);
const SHELL_FILES = ['./', './index.html', './styles.css', './app.js', './manifest.webmanifest', './shopquote-icon.svg'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_FILES.map(path => new URL(path, APP_ROOT)))));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('shopquote-shell-') && key !== CACHE_NAME).map(key => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  const appPath = new URL(self.registration.scope).pathname;
  if (request.method !== 'GET' || url.origin !== self.location.origin || !url.pathname.startsWith(appPath) || url.pathname.includes('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) await (await caches.open(CACHE_NAME)).put(new URL('./index.html', APP_ROOT), response.clone());
        return response;
      } catch {
        return (await caches.match(new URL('./index.html', APP_ROOT))) || Response.error();
      }
    })());
    return;
  }

  event.respondWith((async () => {
    try {
      const response = await fetch(request);
      if (response.ok) await (await caches.open(CACHE_NAME)).put(request, response.clone());
      return response;
    } catch {
      return (await caches.match(request)) || Response.error();
    }
  })());
});