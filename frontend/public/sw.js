// Service worker: hace la app instalable y deja el «esqueleto» (HTML, JS, CSS, iconos) disponible sin conexión.
// NUNCA toca /api: ahí van la sesión, los coches y las fotos de las revisiones (datos privados), que siempre van a la red.
// Subir VERSION al cambiar esta lógica: al activarse, borra las cachés de versiones anteriores.
const VERSION = "v1";
const CACHE = `autos-${VERSION}`;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/", "/manifest.webmanifest", "/icon-192.png"])));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return; // red directa

  if (req.mode === "navigate") {
    // La página: primero la red (así una versión nueva se ve al recargar); sin red, la última guardada.
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copia = res.clone();
          caches.open(CACHE).then((c) => c.put("/", copia));
          return res;
        })
        .catch(() => caches.match("/")),
    );
    return;
  }

  // Archivos con hash en el nombre (/assets/...) e iconos: no cambian, primero la caché.
  e.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ||
        fetch(req).then((res) => {
          if (res.ok) {
            const copia = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copia));
          }
          return res;
        }),
    ),
  );
});
