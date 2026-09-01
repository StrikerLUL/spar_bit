/**
 * Hintergrundprozess: alle Aufrufe an SparBit laufen hier.
 *
 * Grund: nur der Service Worker hat die Host-Berechtigung und darf damit
 * ohne CORS auf localhost zugreifen. Das Popup ruft ihn per Nachricht auf.
 */
import { api } from "./lib.js";

chrome.runtime.onMessage.addListener((nachricht, _absender, antworte) => {
  if (nachricht?.typ !== "api") return false;

  api(nachricht.pfad, { methode: nachricht.methode, daten: nachricht.daten })
    .then((ergebnis) => antworte({ ok: true, ergebnis }))
    .catch((fehler) => antworte({ ok: false, fehler: String(fehler.message) }));

  return true;   // asynchrone Antwort
});
