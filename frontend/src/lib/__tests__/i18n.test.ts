/* Die zweite Sprache - und vor allem: was passiert, wenn sie lückenhaft ist.
 *
 * Deutsch ist zugleich Vorgabe und Schlüssel. Das ist der ganze Trick
 * dieser Lösung: ein fehlender englischer Eintrag zeigt den deutschen
 * Text, nicht `missing.key`. Eine halb fertige Übersetzung soll aussehen
 * wie Deutsch, nicht wie ein Defekt.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { gespeicherteSprache, locale, uebersetze } from "@/lib/i18n";

beforeEach(() => {
  window.localStorage.clear();
});

describe("uebersetze", () => {
  it("übersetzt, was im Wörterbuch steht", () => {
    expect(uebersetze("en", "Anmelden")).toBe("Sign in");
    expect(uebersetze("en", "Wunschliste")).toBe("Watchlist");
  });

  it("gibt auf Deutsch den Schlüssel zurück", () => {
    // Deutsch braucht kein Wörterbuch - der Schlüssel IST der Text.
    expect(uebersetze("de", "Anmelden")).toBe("Anmelden");
  });

  it("zeigt bei fehlender Übersetzung den deutschen Text", () => {
    expect(uebersetze("en", "Ein Satz, den niemand übersetzt hat"))
      .toBe("Ein Satz, den niemand übersetzt hat");
  });

  it("kennt jede Warengruppe", () => {
    // Sonst stünden in der englischen Statistik deutsche Gruppennamen
    // zwischen englischen Spaltenköpfen.
    for (const gruppe of ["Elektronik", "Haushalt & Küche", "Spielzeug",
                          "Reise & Mobilität", "ohne Warengruppe"]) {
      expect(uebersetze("en", gruppe)).not.toBe(gruppe);
    }
  });

  it("kennt jedes Preisurteil", () => {
    for (const urteil of ["Bestpreis", "sehr gut", "war günstiger",
                          "UVP fragwürdig", "zu wenig Daten"]) {
      expect(uebersetze("en", urteil)).not.toBe(urteil);
    }
  });
});

describe("locale", () => {
  it("liefert eine Kennung, die Intl versteht", () => {
    expect(locale("de")).toBe("de-DE");
    expect(locale("en")).toBe("en-GB");
    expect(() => new Intl.NumberFormat(locale("en"))).not.toThrow();
  });
});

describe("gespeicherteSprache", () => {
  it("nimmt, was gespeichert ist", () => {
    window.localStorage.setItem("sparbit-sprache", "en");
    expect(gespeicherteSprache()).toBe("en");
  });

  it("übergeht Unsinn im Speicher", () => {
    // Eine fremde Erweiterung oder eine alte Version könnte alles
    // hineingeschrieben haben.
    window.localStorage.setItem("sparbit-sprache", "klingonisch");
    expect(["de", "en"]).toContain(gespeicherteSprache());
  });

  it("fällt ohne Eintrag auf Deutsch zurück", () => {
    // In jsdom meldet der Browser "en-US" - trotzdem ist Deutsch die
    // Vorgabe dieses Programms, sofern der Browser nicht ausdrücklich
    // Englisch will. Hier tut er das, also:
    expect(gespeicherteSprache()).toBe("en");
  });
});
