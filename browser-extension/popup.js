import { STANDARD_ADRESSE, einstellungen, euro, speichern } from "./lib.js";

const $ = (id) => document.getElementById(id);
const zeigen = (id, an = true) => { $(id).hidden = !an; };

function status(feldId, text, art = "") {
  const knoten = $(feldId);
  knoten.textContent = text;
  knoten.className = `status ${art}`;
}

/** Ruft SparBit über den Hintergrundprozess auf (dort greift die
 *  Host-Berechtigung, sonst blockt CORS). */
function api(pfad, methode = "GET", daten = null) {
  return new Promise((loesen, ablehnen) => {
    chrome.runtime.sendMessage({ typ: "api", pfad, methode, daten }, (antwort) => {
      if (chrome.runtime.lastError) {
        ablehnen(new Error(chrome.runtime.lastError.message));
      } else if (!antwort?.ok) {
        ablehnen(new Error(antwort?.fehler || "Unbekannter Fehler"));
      } else {
        loesen(antwort.ergebnis);
      }
    });
  });
}

/** Produktdaten aus dem aktiven Tab lesen. */
async function produktLesen() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https?:/.test(tab.url || "")) return null;

  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch {
    // Auf manchen Seiten (Store-Seiten des Browsers, PDF-Ansicht) geht das nicht.
    return null;
  }

  return new Promise((loesen) => {
    chrome.tabs.sendMessage(tab.id, { typ: "lies-produkt" }, (antwort) => {
      loesen(chrome.runtime.lastError ? null : antwort);
    });
  });
}

let produkt = null;

async function start() {
  const { adresse, token } = await einstellungen();
  $("adresse").value = adresse;
  $("oeffnen").href = adresse;

  if (!token) {
    zeigen("einrichtung");
    return;
  }
  zeigen("inhalt");
  await inhaltFuellen();
}

async function inhaltFuellen() {
  produkt = await produktLesen();

  if (!produkt) {
    $("titel").textContent = "Diese Seite lässt sich nicht auslesen.";
    $("beobachten").disabled = true;
    status("status", "Öffne eine Produktseite in einem Shop.", "warn");
    return;
  }

  $("titel").textContent = produkt.name || "Ohne Titel";
  if (produkt.bild) {
    $("bild").src = produkt.bild;
    zeigen("bild");
  }

  if (produkt.preis === null) {
    $("preis").textContent = "Kein Preis erkennbar";
    $("verfahren").textContent =
      "Diese Seite liefert keine strukturierten Preisdaten — SparBit könnte sie "
      + "nicht zuverlässig beobachten.";
    $("beobachten").disabled = true;
    return;
  }

  $("preis").textContent = euro(produkt.preis, produkt.waehrung);
  $("verfahren").textContent = `gelesen aus ${produkt.verfahren}`;

  // Kennt SparBit den Artikel schon — und günstiger?
  try {
    const bekannt = await api(
      `/kennt?url=${encodeURIComponent(produkt.url)}`
      + `&titel=${encodeURIComponent(produkt.name || "")}`);
    bekanntZeigen(bekannt);
  } catch (fehler) {
    status("status", fehler.message, "fehler");
  }
}

function bekanntZeigen(bekannt) {
  const karte = $("bekannt");

  if (bekannt.beobachtet) {
    karte.className = "karte";
    karte.innerHTML = "Steht bereits auf deiner Wunschliste.";
    zeigen("bekannt");
    $("beobachten").textContent = "Zielpreis aktualisieren";
  }

  if (!bekannt.bekannt) return;

  const dort = bekannt.preis_eur ?? bekannt.preis;
  const hier = produkt.preis;
  const teile = [];

  if (dort !== null && dort !== undefined && hier !== null) {
    if (dort < hier * 0.99) {
      karte.className = "karte guenstiger";
      const ersparnis = hier - dort;
      teile.push(`SparBit kennt das für <b>${euro(dort)}</b> bei `
        + `${bekannt.quelle} — ${euro(ersparnis)} günstiger.`);
    } else {
      teile.push(`SparBit kennt das für ${euro(dort)} bei ${bekannt.quelle}.`);
    }
  }
  if (bekannt.urteil_text) teile.push(`<span class="klein">${bekannt.urteil_text}</span>`);

  if (teile.length) {
    karte.innerHTML = (karte.hidden ? "" : karte.innerHTML + "<br>") + teile.join("<br>");
    zeigen("bekannt");
  }
}

// --- Aktionen --------------------------------------------------------------

$("verbinden").addEventListener("click", async () => {
  const adresse = $("adresse").value.trim() || STANDARD_ADRESSE;
  const token = $("token").value.trim();
  if (!token) {
    status("einrichtung-status", "Bitte den Zugangsschlüssel einfügen.", "warn");
    return;
  }

  status("einrichtung-status", "Prüfe Verbindung …");
  await speichern(adresse, token);
  try {
    await api("/ping");
  } catch (fehler) {
    status("einrichtung-status", fehler.message, "fehler");
    return;
  }
  status("einrichtung-status", "Verbunden.", "ok");
  zeigen("einrichtung", false);
  zeigen("inhalt");
  $("oeffnen").href = adresse;
  await inhaltFuellen();
});

$("zahnrad").addEventListener("click", () => {
  const zeigt = !$("einrichtung").hidden;
  zeigen("einrichtung", !zeigt);
  zeigen("inhalt", zeigt);
});

$("beobachten").addEventListener("click", async () => {
  if (!produkt) return;
  const knopf = $("beobachten");
  knopf.disabled = true;
  status("status", "Wird gespeichert …");

  const rohZiel = $("ziel").value.trim().replace(",", ".");
  const ziel = rohZiel ? Number.parseFloat(rohZiel) : null;

  try {
    const ergebnis = await api("/watch", "POST", {
      name: produkt.name || produkt.url,
      url: produkt.url,
      ziel_preis: Number.isFinite(ziel) ? ziel : null,
      bild: produkt.bild || null,
    });
    if (ergebnis.bereits_vorhanden) {
      status("status", "Stand schon auf der Wunschliste.", "ok");
    } else if (ergebnis.fehler) {
      status("status", `Aufgenommen, aber: ${ergebnis.fehler}`, "warn");
    } else {
      status("status",
        `Aufgenommen — beobachtet ab ${euro(ergebnis.preis, produkt.waehrung)}.`,
        "ok");
    }
  } catch (fehler) {
    status("status", fehler.message, "fehler");
  } finally {
    knopf.disabled = false;
  }
});

start();
