/* Die Funktionen, durch die jede Zahl auf jeder Karte läuft.
 *
 * Jeder Fall hier stand einmal falsch auf dem Bildschirm. "1299,00 €" ohne
 * Tausenderpunkt liest sich als ein Zehntel von dem, was es ist; ein
 * durchgestrichener Preis, der unter dem aktuellen liegt, lässt einen Deal
 * schlechter aussehen als er ist; und 0 € bei "gespart" heißt null
 * Ersparnis, nicht "gratis".
 */
import { beforeEach, describe, expect, it } from "vitest";
import {
  cn,
  currencySymbol,
  eurHinweis,
  formatAmount,
  formatBytes,
  formatDuration,
  formatNumber,
  formatPrice,
  linesToList,
  listToLines,
  timeAgo,
  zeigeStreichpreis,
} from "@/lib/utils";

/* Zwischen Zahl und Waehrungszeichen steht ein geschuetztes Leerzeichen
 * (siehe eslint.config.js): "12,99 EUR" darf nicht umbrechen. Im Test
 * muss es genauso dastehen - sonst vergleicht man zwei Strings, die
 * gleich aussehen und es nicht sind. Genau diese Stelle kostet sonst
 * eine Viertelstunde. */
const NB = "\u00A0";

beforeEach(() => {
  // Die Formatierung liest die Sprache aus dem Speicher - ohne diese Zeile
  // hinge das Ergebnis an der Spracheinstellung des Testrechners.
  window.localStorage.setItem("sparbit-sprache", "de");
});

describe("formatAmount", () => {
  it("setzt den Tausenderpunkt", () => {
    // Der Fall, für den Intl überhaupt benutzt wird.
    expect(formatAmount(1299)).toBe(`1.299,00${NB}€`);
  });

  it("zeigt immer zwei Nachkommastellen", () => {
    expect(formatAmount(9.5)).toBe(`9,50${NB}€`);
    expect(formatAmount(9)).toBe(`9,00${NB}€`);
  });

  it("behandelt 0 als Betrag, nicht als gratis", () => {
    expect(formatAmount(0)).toBe(`0,00${NB}€`);
  });

  it("gibt bei fehlendem Wert einen Gedankenstrich", () => {
    expect(formatAmount(null)).toBe("—");
    expect(formatAmount(undefined)).toBe("—");
    expect(formatAmount(Number.NaN)).toBe("—");
  });

  it("folgt der Sprache", () => {
    window.localStorage.setItem("sparbit-sprache", "en");
    expect(formatAmount(1299)).toBe(`1,299.00${NB}€`);
  });
});

describe("formatPrice", () => {
  it("nennt 0 beim Namen", () => {
    expect(formatPrice(0)).toBe("gratis");
    // Auch Rundungsreste aus der Umrechnung.
    expect(formatPrice(0.004)).toBe("gratis");
  });

  it("rechnet nicht selbst um", () => {
    expect(formatPrice(9.99, "USD")).toBe(`9,99${NB}$`);
  });
});

describe("currencySymbol", () => {
  it("kennt die Währungen der eingebauten Quellen", () => {
    expect(currencySymbol("EUR")).toBe("€");
    expect(currencySymbol("usd")).toBe("$");
    expect(currencySymbol("GBP")).toBe("£");
  });

  it("gibt Unbekanntes unverändert zurück statt zu raten", () => {
    expect(currencySymbol("AUD")).toBe("AUD");
  });
});

describe("eurHinweis", () => {
  it("steht nur bei Fremdwährung", () => {
    expect(eurHinweis(9.19, "USD")).toBe(`≈ 9,19${NB}€`);
    expect(eurHinweis(9.19, "EUR")).toBeNull();
  });

  it("entfällt, wo es nichts zu vergleichen gibt", () => {
    expect(eurHinweis(null, "USD")).toBeNull();
    expect(eurHinweis(0, "USD")).toBeNull();
  });
});

describe("zeigeStreichpreis", () => {
  it("zeigt einen echten Streichpreis", () => {
    expect(zeigeStreichpreis({ preis: 49, originalpreis: 99 })).toBe(true);
  });

  it("verschweigt einen, der den Deal schlechter aussehen ließe", () => {
    // Ein "Originalpreis" unter dem aktuellen ist immer ein Datenfehler.
    expect(zeigeStreichpreis({ preis: 49, originalpreis: 39 })).toBe(false);
    expect(zeigeStreichpreis({ preis: 49, originalpreis: 49 })).toBe(false);
  });

  it("zeigt bei Gratis-Funden, was es sonst gekostet hätte", () => {
    expect(zeigeStreichpreis({ preis: 0, ist_gratis: true, originalpreis: 19.99 }))
      .toBe(true);
    expect(zeigeStreichpreis({ preis: 0, ist_gratis: true, originalpreis: 0 }))
      .toBe(false);
  });

  it("zeigt nichts, wo nichts steht", () => {
    expect(zeigeStreichpreis({ preis: 49 })).toBe(false);
    expect(zeigeStreichpreis({ originalpreis: 99 })).toBe(false);
  });
});

describe("timeAgo", () => {
  it("sagt bei frischen Funden „jetzt“", () => {
    expect(timeAgo(new Date().toISOString())).toMatch(/jetzt/i);
  });

  it("rechnet in die nächstgrößere Einheit hoch", () => {
    const vor90Minuten = new Date(Date.now() - 90 * 60_000).toISOString();
    expect(timeAgo(vor90Minuten)).toMatch(/Stunde/i);
  });

  it("spricht in beiden Sprachen natürlich", () => {
    // Über Intl.RelativeTimeFormat statt eigener Wortlisten: das trifft
    // die Mehrzahl und die Sonderformen ("vorgestern") ohne eigene Regeln.
    const vor2Tagen = new Date(Date.now() - 2 * 86_400_000).toISOString();
    expect(timeAgo(vor2Tagen)).toBe("vorgestern");
    window.localStorage.setItem("sparbit-sprache", "en");
    expect(timeAgo(vor2Tagen)).toBe("2 days ago");
  });

  it("nennt bei älteren Funden das Datum", () => {
    const vorEinemJahr = new Date(Date.now() - 400 * 86_400_000).toISOString();
    expect(timeAgo(vorEinemJahr)).toMatch(/\d{4}/);
  });

  it("fällt bei Unsinn nicht um", () => {
    expect(timeAgo(null)).toBe("—");
    expect(timeAgo("kein datum")).toBe("—");
  });
});

describe("formatDuration", () => {
  it("wählt die passende Einheit", () => {
    expect(formatDuration(30)).toMatch(/30/);
    expect(formatDuration(600)).toMatch(/10/);
    expect(formatDuration(7200)).toMatch(/2/);
  });

  it("nennt bei Stunden auch die Minuten", () => {
    // 4 Std. 20 Min. - "4 Std." allein wäre 20 Minuten daneben.
    const text = formatDuration(4 * 3600 + 20 * 60);
    expect(text).toMatch(/4/);
    expect(text).toMatch(/20/);
  });
});

describe("formatNumber und formatBytes", () => {
  it("gruppiert große Zahlen", () => {
    expect(formatNumber(50000)).toBe("50.000");
  });

  it("rechnet Bytes in lesbare Einheiten", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 ** 2)).toBe("5.0 MB");
  });
});

describe("Listen und Zeilen", () => {
  it("wirft leere Zeilen und Leerraum weg", () => {
    expect(linesToList("lego\n\n  technic  \n")).toEqual(["lego", "technic"]);
  });

  it("ist umkehrbar", () => {
    expect(linesToList(listToLines(["a", "b"]))).toEqual(["a", "b"]);
    expect(listToLines(undefined)).toBe("");
  });
});

describe("cn", () => {
  it("lässt die spätere Tailwind-Klasse gewinnen", () => {
    // Ohne twMerge stünden beide im class-Attribut und die Reihenfolge
    // im Stylesheet entschiede - also der Zufall.
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("übergeht falsche Bedingungen", () => {
    // So steht es im Code: eine Klasse haengt an einer Bedingung.
    const aktiv = false;
    expect(cn("a", aktiv && "b", undefined, "c")).toBe("a c");
  });
});
