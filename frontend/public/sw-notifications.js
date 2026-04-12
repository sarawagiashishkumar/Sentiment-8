/* Service Worker for Push Notifications */
/* eslint-disable no-restricted-globals */

self.addEventListener("install", () => { self.skipWaiting(); });
self.addEventListener("activate", (event) => { event.waitUntil(self.clients.claim()); });

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "PUSH_NOTIFICATION") {
    const { title, body, tag, icon } = event.data;
    self.registration.showNotification(title || "Trading Alert", {
      body: body || "",
      tag: tag || "trading-alert",
      icon: icon || "/favicon.ico",
      badge: "/favicon.ico",
      vibrate: [200, 100, 200],
      requireInteraction: true,
      actions: [{ action: "open", title: "Open Dashboard" }, { action: "dismiss", title: "Dismiss" }],
    });
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  if (event.action === "dismiss") return;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          return client.focus();
        }
      }
      return self.clients.openWindow("/");
    })
  );
});
