/* Service Worker: nimmt Push-Meldungen an, auch wenn SparBit zu ist -
 * und zeigt offline wenigstens SparBit statt der Dinosaurier-Seite.
 *
 * Bewusst klein gehalten. Er tut drei Dinge: eine Meldung anzeigen,
 * beim Klick den Deal oeffnen, und die Huelle der Anwendung
 * vorhalten. Dabei faengt er einen Fall ab, den man leicht uebersieht:
 * ist SparBit schon in einem Tab offen, wird dieser Tab benutzt, statt
 * einen zweiten aufzumachen.
 *
 * **Was NICHT gecacht wird: Daten.** Kein Deal, keine Antwort von
 * /api. Ein Deal-Feed von gestern ist keine Hilfe, sondern eine Falle -
 * ein Preisfehler, der laengst korrigiert ist, sieht im Cache genauso
 * aus wie einer, der noch gilt.
 *
 * Gecacht wird nur die Huelle: index.html und die gebauten Dateien.
 * Damit oeffnet die installierte App offline eine SparBit-Seite, die
 * "keine Verbindung" sagt - statt einer Browser-Fehlerseite, die wie
 * ein Defekt aussieht.
 *
 * Der zweite Grund fuer den frueheren Verzicht war "nach dem Update
 * sieht es komisch aus". Dagegen steht hier: **network-first.** Ist das
 * Netz da, gewinnt immer das Netz, und der Cache wird gleich
 * nachgezogen. Der Cache antwortet nur, wenn der Abruf scheitert.
 */

// Mit jedem Release neu, damit alte Huellen verschwinden. Der Wert wird
// beim Bauen nicht ersetzt - er muss von Hand hoch, wenn sich an dieser
// Datei etwas aendert. Das ist Absicht: automatisch waere er bei jedem
// Bau neu, und dann raeumte jeder Bau den Cache aller Benutzer ab.
const HUELLE = "sparbit-huelle-v1";
const VORRAT = ["/", "/index.html", "/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  // Sofort uebernehmen statt auf das Schliessen aller Tabs zu warten.
  self.skipWaiting();
  event.waitUntil(
    caches.open(HUELLE)
      // addAll bricht ab, sobald EINE Datei fehlt - und dann gaebe es
      // gar keinen Cache. Einzeln ist schlechter zu lesen und
      // ueberlebt eine fehlende Datei.
      .then((cache) => Promise.allSettled(VORRAT.map((pfad) => cache.add(pfad))))
      .catch(() => undefined),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((namen) => Promise.all(
        namen.filter((n) => n.startsWith("sparbit-huelle-") && n !== HUELLE)
             .map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const anfrage = event.request;
  if (anfrage.method !== "GET") return;

  const adresse = new URL(anfrage.url);
  if (adresse.origin !== self.location.origin) return;

  // Daten nie aus dem Cache. /api liefert Deals, Preise und Zustaende -
  // alles davon ist morgen falsch. /api/events ist zusaetzlich ein
  // offener Strom; ihn zu cachen hiesse, ihn nie zu beenden.
  if (adresse.pathname.startsWith("/api/")) return;
  // Deal-Bilder liegen schon lokal beim Backend - ein zweiter Cache
  // davor braeuchte nur Platz.
  if (adresse.pathname.startsWith("/bilder/")) return;

  event.respondWith(
    fetch(anfrage)
      .then((antwort) => {
        // Nur vollstaendige, eigene Antworten aufheben. Eine 206 oder
        // eine Fehlerseite im Cache waere schlimmer als kein Cache.
        if (antwort.ok && antwort.type === "basic") {
          const kopie = antwort.clone();
          caches.open(HUELLE).then((cache) => cache.put(anfrage, kopie))
            .catch(() => undefined);
        }
        return antwort;
      })
      .catch(async () => {
        const gefunden = await caches.match(anfrage);
        if (gefunden) return gefunden;
        // Jede Unteradresse der Anwendung fuehrt auf dieselbe Seite -
        // ohne das endet /feed offline in einem 404.
        if (anfrage.mode === "navigate") {
          const huelle = await caches.match("/index.html");
          if (huelle) return huelle;
        }
        return Response.error();
      }),
  );
});

self.addEventListener("push", (event) => {
  let daten = {};
  try {
    daten = event.data ? event.data.json() : {};
  } catch {
    daten = { titel: "SparBit", text: event.data ? event.data.text() : "" };
  }

  const titel = daten.titel || "SparBit";
  const optionen = {
    body: daten.text || "",
    icon: "/icon.svg",
    badge: "/icon.svg",
    // Gleiche Regel = gleiches Tag: zwei Meldungen derselben Regel
    // ersetzen einander, statt sich zu stapeln.
    tag: daten.deal_id ? `deal-${daten.deal_id}` : (daten.regel || "sparbit"),
    data: { url: daten.url || "/" },
    requireInteraction: Boolean(daten.dringend),
    timestamp: Date.now(),
  };
  if (daten.bild) optionen.image = daten.bild;

  event.waitUntil(self.registration.showNotification(titel, optionen));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const ziel = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true })
      .then((fenster) => {
        for (const f of fenster) {
          // Ist SparBit schon offen, dorthin wechseln statt neu oeffnen.
          if (f.url.includes(self.location.origin) && "focus" in f) {
            f.navigate(ziel).catch(() => undefined);
            return f.focus();
          }
        }
        return self.clients.openWindow(ziel);
      }),
  );
});
