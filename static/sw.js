const CACHE_NAME = 'sd-v3-fix';
const ICON_192 = '/static/icon-192.png';
const ICON_512 = '/static/icon-512.png';

// Install - Skip waiting
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll([
        '/',
        '/static/manifest.json',
        ICON_192,
        ICON_512
      ]).catch(() => console.log('Pre-cache failed but ok'));
    })
  );
});

// Activate - Clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// TABS FIX + OFFLINE FIX - MAIN LOGIC
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  
  // Skip chrome extensions and non-GET
  if (request.method !== 'GET' || url.protocol.startsWith('chrome-extension')) {
    return;
  }
  
  // 1. NEVER cache HTML navigation - Always network (Fixes Tabs Issue)
  if (request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then(res => {
          // Clone and cache HTML for offline fallback only
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          return res;
        })
        .catch(() => caches.match('/') || caches.match(request))
    );
    return;
  }

  // 2. For static assets - Cache first, network fallback
  if (url.pathname.startsWith('/static/') || request.destination === 'image' || request.destination === 'style' || request.destination === 'script') {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          // Cache new static files
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          return res;
        }).catch(() => cached);
      })
    );
    return;
  }

  // 3. For API calls - Network only, no cache
  event.respondWith(fetch(request).catch(() => caches.match(request)));
});

// 🔔 NOTIFICATION CLICK - FIXED
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  const targetUrl = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      // If window already open, focus it
      for (let client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Else open new window
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

// 🔔 PUSH NOTIFICATION - FIXED
self.addEventListener('push', event => {
  let data = { title: 'SD TOURNAMENTS', body: '🔥 New Match Live! Join Now', url: '/' };
  
  try {
    if (event.data) {
      const json = event.data.json();
      data = { ...data, ...json };
    }
  } catch (e) {
    if (event.data) data.body = event.data.text();
  }
  
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: ICON_192,
      badge: ICON_192,
      image: ICON_512,
      vibrate: [200, 100, 200],
      data: { url: data.url || '/' },
      actions: [
        { action: 'open', title: '🎮 Join Now' },
        { action: 'close', title: '❌ Close' }
      ],
      requireInteraction: false,
      tag: 'sd-tour-notif'
    })
  );
});

self.addEventListener('notificationclose', event => {
  console.log('Notification closed');
});
