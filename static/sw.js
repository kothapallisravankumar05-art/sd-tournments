const CACHE_NAME = 'sd-v3-fix';

self.addEventListener('install', event => {
  self.skipWaiting();
});

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

// TABS FIX + NOTIFICATION CLICK
self.addEventListener('fetch', event => {
  const request = event.request;
  
  // 1. NEVER cache HTML navigation - Always network (Fixes Tabs)
  if (request.mode === 'navigate' || request.headers.get('accept').includes('text/html')) {
    event.respondWith(
      fetch(request).catch(() => caches.match('/'))
    );
    return;
  }

  // 2. For images/css/js - try cache first
  event.respondWith(
    caches.match(request).then(response => {
      return response || fetch(request);
    })
  );
});

// 🔔 NOTIFICATION CLICK - NEW
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow('/')
  );
});

self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {title:'SD TOURNAMENTS', body:'🔥 New Match Live!'};
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icon.png',
      badge: '/static/icon.png',
      vibrate: [200,100,200]
    })
  );
});
