/* Service Worker: nimmt Push-Meldungen an, auch wenn SparBit zu ist.
 *
 * Bewusst klein gehalten. Er tut genau zwei Dinge - eine Meldung
 * anzeigen und beim Klick den Deal oeffnen - und faengt dabei einen
 * Fall ab, den man leicht uebersieht: ist SparBit schon in einem Tab
 * offen, wird dieser Tab benutzt, statt einen zweiten aufzumachen.
 *
 * Kein Offline-Cache. Ein Deal-Feed von gestern ist keine Hilfe,
 * sondern eine Falle - und ein Cache, der die Oberflaeche einfriert,
 * waere der haeufigste Grund fuer "nach dem Update sieht es komisch
 * aus".
 */

self.addEventListener("install", () => {
  // Sofort uebernehmen statt auf das Schliessen aller Tabs zu warten.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
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
