/**
 * Liest Produktdaten aus der Seite — aus denselben strukturierten Angaben,
 * die SparBit serverseitig auswertet (JSON-LD, Open Graph, Microdata).
 *
 * Bewusst keine CSS-Selektoren: die ändern sich bei jedem Redesign,
 * "@type": "Product" nicht.
 */

function zahl(wert) {
  if (wert === null || wert === undefined) return null;
  if (typeof wert === "number") return wert;
  let text = String(wert).trim().replace(/\s/g, "");
  if (text.includes(",") && text.includes(".")) {
    text = text.lastIndexOf(",") > text.lastIndexOf(".")
      ? text.replace(/\./g, "").replace(",", ".")
      : text.replace(/,/g, "");
  } else if (text.includes(",")) {
    text = text.replace(",", ".");
  }
  text = text.replace(/[^\d.]/g, "");
  const ergebnis = Number.parseFloat(text);
  return Number.isFinite(ergebnis) && ergebnis > 0 ? ergebnis : null;
}

function flach(knoten, gesammelt = []) {
  if (Array.isArray(knoten)) {
    knoten.forEach((k) => flach(k, gesammelt));
  } else if (knoten && typeof knoten === "object") {
    gesammelt.push(knoten);
    for (const schluessel of ["@graph", "itemListElement", "mainEntity",
                              "offers", "hasVariant"]) {
      if (knoten[schluessel]) flach(knoten[schluessel], gesammelt);
    }
  }
  return gesammelt;
}

const istTyp = (knoten, typen) => {
  const typ = knoten["@type"];
  const liste = Array.isArray(typ) ? typ : [typ];
  return liste.some((t) => typen.includes(String(t || "").toLowerCase()));
};

function ausJsonLd() {
  for (const skript of document.querySelectorAll(
      'script[type="application/ld+json"]')) {
    let daten;
    try {
      daten = JSON.parse(skript.textContent);
    } catch { continue; }

    const knoten = flach(daten);
    const produkte = knoten.filter((k) => istTyp(k, ["product", "productmodel"]));
    const angebote = knoten.filter((k) => istTyp(k, ["offer", "aggregateoffer"]));

    for (const angebot of angebote) {
      const preis = zahl(angebot.price ?? angebot.lowPrice);
      if (preis === null) continue;
      const produkt = produkte[0] || {};
      let bild = produkt.image;
      if (Array.isArray(bild)) bild = bild[0];
      if (bild && typeof bild === "object") bild = bild.url;
      return {
        preis,
        waehrung: String(angebot.priceCurrency || "EUR").toUpperCase(),
        name: produkt.name ? String(produkt.name) : null,
        bild: bild ? String(bild) : null,
        verfahren: "JSON-LD",
      };
    }
  }
  return null;
}

const meta = (...namen) => {
  for (const name of namen) {
    const knoten = document.querySelector(
      `meta[property="${name}"], meta[name="${name}"], meta[itemprop="${name}"]`);
    if (knoten?.content) return knoten.content;
  }
  return null;
};

function ausOpenGraph() {
  const preis = zahl(meta("product:price:amount", "og:price:amount"));
  if (preis === null) return null;
  return {
    preis,
    waehrung: (meta("product:price:currency", "og:price:currency") || "EUR")
      .toUpperCase(),
    name: meta("og:title"),
    bild: meta("og:image"),
    verfahren: "Open Graph",
  };
}

function ausMicrodata() {
  const knoten = document.querySelector('[itemprop="price"]');
  if (!knoten) return null;
  const preis = zahl(knoten.getAttribute("content") || knoten.textContent);
  if (preis === null) return null;
  const waehrung = document.querySelector('[itemprop="priceCurrency"]');
  return {
    preis,
    waehrung: (waehrung?.getAttribute("content") || "EUR").toUpperCase(),
    name: document.querySelector('[itemprop="name"]')?.textContent?.trim() || null,
    bild: document.querySelector('[itemprop="image"]')?.getAttribute("src") || null,
    verfahren: "Microdata",
  };
}

function lies() {
  for (const verfahren of [ausJsonLd, ausOpenGraph, ausMicrodata]) {
    try {
      const fund = verfahren();
      if (fund) {
        return {
          ...fund,
          name: (fund.name || document.title || "").trim().slice(0, 250),
          url: location.href.split("#")[0],
        };
      }
    } catch { /* nächstes Verfahren */ }
  }
  return {
    preis: null,
    name: (document.title || "").trim().slice(0, 250),
    url: location.href.split("#")[0],
    verfahren: null,
  };
}

chrome.runtime.onMessage.addListener((nachricht, _absender, antworte) => {
  if (nachricht?.typ === "lies-produkt") {
    antworte(lies());
  }
  return true;
});
