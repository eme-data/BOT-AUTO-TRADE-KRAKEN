/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope;

import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';

// Precache static assets (injected by VitePWA build)
precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Push notification handler
self.addEventListener('push', (event) => {
  if (!event.data) return;

  try {
    const data = event.data.json();
    const title = data.title || 'Altior Trading';
    const options: NotificationOptions = {
      body: data.body || '',
      icon: '/favicon.svg',
      badge: '/favicon.svg',
      tag: data.tag || 'default',
      data: { url: data.url || '/' },
      requireInteraction: false,
    };
    event.waitUntil(self.registration.showNotification(title, options));
  } catch {
    const text = event.data?.text() || 'Nouvelle notification';
    event.waitUntil(
      self.registration.showNotification('Altior Trading', { body: text })
    );
  }
});

// Notification click – open/focus the app
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
