/** Gemeinsames zwischen Popup und Hintergrundprozess. */

export const STANDARD_ADRESSE = "http://localhost:8000";

export async function einstellungen() {
  const { adresse, token } = await chrome.storage.local.get(["adresse", "token"]);
  return { adresse: adresse || STANDARD_ADRESSE, token: token || "" };
}

export async function speichern(adresse, token) {
  await chrome.storage.local.set({ adresse: adresse.replace(/\/+$/, ""), token });
}

/**
 * Ruft SparBit auf.
 *
 * Läuft bewusst im Hintergrundprozess: der hat die Host-Berechtigung und
 * umgeht damit CORS. Ein Aufruf aus dem Content-Script der Shop-Seite würde
 * daran scheitern — und niemand soll CORS für seine SparBit-Instanz öffnen
 * müssen, nur damit eine Erweiterung funktioniert.
 */
export async function api(pfad, { methode = "GET", daten = null } = {}) {
  const { adresse, token } = await einstellungen();
  if (!token) throw new Error("Kein Zugangsschlüssel hinterlegt.");

  let antwort;
  try {
    antwort = await fetch(`${adresse}/api/extern${pfad}`, {
      method: methode,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(daten ? { "Content-Type": "application/json" } : {}),
      },
      body: daten ? JSON.stringify(daten) : undefined,
    });
  } catch {
    throw new Error(`SparBit unter ${adresse} nicht erreichbar. Läuft es?`);
  }

  if (antwort.status === 401) {
    throw new Error("Zugangsschlüssel ungültig oder zurückgezogen.");
  }
  if (!antwort.ok) {
    let text = `HTTP ${antwort.status}`;
    try {
      const koerper = await antwort.json();
      if (koerper?.detail) text = koerper.detail;
    } catch { /* keine JSON-Antwort */ }
    throw new Error(text);
  }
  return antwort.json();
}

export function euro(wert, waehrung = "EUR") {
  if (wert === null || wert === undefined) return "—";
  const zeichen = { EUR: "€", USD: "$", GBP: "£" }[waehrung] || waehrung;
  return `${wert.toFixed(2).replace(".", ",")} ${zeichen}`;
}
