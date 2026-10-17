// Offline copy of the app itself, so it opens even without a connection; the AI on the phone works offline too
// (the model and ONNX Runtime are kept here once loaded). An AI server, if one is set, still needs the network.
// Network first: a change to the app shows at once; the copy is only used when the network fails.
const CACHE = "respirai";
const APP = ["./", "index.html", "style.css", "app.js", "audio.js", "device.js", "fake-bluetooth.js", "manifest.webmanifest",
  "native.js", "native-bluetooth.js", "ai/local.js", "ai/worker.js", "ai/pipeline.js", "mic-test.html", "mic-test.js",
  "i18n/index.js", "i18n/en.js", "i18n/ro.js", "i18n/es.js", "i18n/fr.js", "i18n/de.js",
  "img/logo.png", "img/logo-dark.png", "img/lungs.png", "img/lungs-dark.png", "img/favicon.png", "img/icon-192.png"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(APP)).catch(() => {}));
});
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || /^\/(health|session|log)\b/.test(url.pathname)) return;
  e.respondWith(fetch(e.request).then((res) => {
    if (res.ok) {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
    }
    return res;
  }).catch(() => caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || Response.error())));
});
