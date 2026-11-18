/*
 * RetailIQ service worker
 *
 * Strategy
 *  - App shell (index, offline page, icons) is pre-cached on install.
 *  - Hashed build assets (/assets/*) are cache-first: their file names change on every build.
 *  - Page navigations are network-first; when offline we serve the cached app shell,
 *    and if even that is missing, the offline fallback page.
 *  - API calls (/api/*) are NEVER cached: business data must always be fresh and
 *    private data must not be left in the cache.
 */
const VERSION = "retailiq-v1";
const SHELL = ["/", "/index.html", "/offline.html", "/manifest.webmanifest", "/favicon.svg",
  "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // always network

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put("/index.html", copy));
          return res;
        })
        .catch(async () => (await caches.match("/index.html")) || caches.match("/offline.html")),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/") || url.pathname.endsWith(".woff2")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return res;
      })),
    );
  }
});
