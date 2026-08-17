// Web Push service worker. Deliberately has NO fetch/caching logic -- this
// app makes live API calls (focus timer polling, task board, etc.) that
// must never be intercepted/cached by a stale SW; this file only exists to
// receive push events and handle notification clicks.

self.addEventListener("push", (event) => {
  let payload = { title: "Winslow", body: "" };
  try {
    payload = event.data.json();
  } catch (e) {
    payload.body = event.data ? event.data.text() : "";
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || "Winslow", {
      body: payload.body || "",
      icon: "/icons/icon-192.png",
      tag: payload.tag || undefined,
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("/focus");
    })
  );
});
