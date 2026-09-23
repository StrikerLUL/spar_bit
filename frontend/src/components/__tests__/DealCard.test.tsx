/* Die Deal-Karte - das eine Bauteil, das der Benutzer hundertmal am Tag sieht.
 *
 * Geprüft wird, was darauf steht, nicht wie es aussieht. Ein Snapshot über
 * Tailwind-Klassen hielte bis zur nächsten Anpassung und meldete dann
 * "rot", ohne dass etwas kaputt ist.
 *
 * Die Fälle sind die, bei denen die Karte einmal etwas Falsches behauptet
 * hat: ein durchgestrichener Preis unter dem aktuellen, ein Dollarbetrag
 * ohne Umrechnung, ein Gutschein-Code, der nur in der gekürzten
 * Beschreibung stand.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Deal } from "@/lib/api";
import { SpracheProvider } from "@/lib/i18n";
import { DealCard } from "@/components/DealCard";

// jsdom meldet "en-US" als Browsersprache - ohne diese Zeile liefe die
// Karte in jedem Test auf Englisch, und das wäre nicht der Normalfall.
beforeEach(() => {
  window.localStorage.setItem("sparbit-sprache", "de");
});

function deal(ueberschreiben: Partial<Deal> = {}): Deal {
  return {
    id: 1,
    titel: "LEGO Technic Bagger 42121",
    beschreibung: null,
    url: "https://shop.test/lego",
    bild: null,
    preis: 49.99,
    originalpreis: 99.99,
    rabatt_prozent: 50,
    waehrung: "EUR",
    ist_gratis: false,
    haendler: "Amazon",
    kategorie: "community",
    quelle: "mydealz",
    temperatur: 350,
    tags: [],
    veroeffentlicht_am: null,
    first_seen: new Date().toISOString(),
    last_seen: new Date().toISOString(),
    seen_count: 1,
    also_from: [],
    bookmarked: false,
    preis_eur: 49.99,
    bild_lokal: null,
    beste_quelle: "mydealz",
    anzahl_angebote: 1,
    urteil: null,
    urteil_text: null,
    fehler_score: 0,
    fehler_stufe: null,
    fehler_gruende: [],
    fehler_erwartet_eur: null,
    ...ueberschreiben,
  } as Deal;
}

function zeichne(d: Deal, props: Record<string, unknown> = {}) {
  return render(
    <SpracheProvider>
      <DealCard deal={d} {...props} />
    </SpracheProvider>,
  );
}

describe("Preisdarstellung", () => {
  it("zeigt Preis und Streichpreis", () => {
    zeichne(deal());
    expect(screen.getByText(/49,99/)).toBeInTheDocument();
    expect(screen.getByText(/99,99/)).toBeInTheDocument();
  });

  it("verschweigt einen Streichpreis, der unter dem Preis liegt", () => {
    // Ein Datenfehler der Quelle darf den Deal nicht schlechter aussehen
    // lassen, als er ist.
    zeichne(deal({ preis: 49.99, originalpreis: 39.99 }));
    expect(screen.queryByText(/39,99/)).not.toBeInTheDocument();
  });

  it("schreibt „gratis“ statt „0,00 €“", () => {
    zeichne(deal({ preis: 0, ist_gratis: true }));
    expect(screen.getAllByText(/gratis/i).length).toBeGreaterThan(0);
  });

  it("stellt bei Fremdwährung den EUR-Gegenwert daneben", () => {
    // Ohne ihn lässt sich "$ 9.99" mit keinem Preislimit vergleichen.
    zeichne(deal({ preis: 9.99, waehrung: "USD", preis_eur: 9.19 }));
    expect(screen.getByText(/9,19/)).toBeInTheDocument();
  });

  it("sagt einem Screenreader, dass der Streichpreis ein alter Preis ist", () => {
    // Durchgestrichen sieht man - vorgelesen wird es nicht.
    zeichne(deal());
    expect(screen.getByText("statt", { exact: false })).toBeInTheDocument();
  });
});

describe("Abzeichen", () => {
  it("zeigt den Rabatt", () => {
    zeichne(deal());
    expect(screen.getByText("−50%")).toBeInTheDocument();
  });

  it("zeigt das Preisurteil im Klartext, nicht nur farbig", () => {
    zeichne(deal({ urteil: "bestpreis", urteil_text: "So günstig war es noch nie" }));
    expect(screen.getByText("Bestpreis")).toBeInTheDocument();
  });

  it("zeigt kein Urteil, wo keines feststeht", () => {
    zeichne(deal({ urteil: "unbekannt" }));
    expect(screen.queryByText(/kein Urteil/)).not.toBeInTheDocument();
  });
});

describe("Gutschein-Code", () => {
  it("steht auf der Karte, nicht nur im Fließtext", () => {
    zeichne(deal({ gutschein_code: "SOMMER25" }));
    expect(screen.getByText("SOMMER25")).toBeInTheDocument();
  });

  it("fehlt, wo keiner ist", () => {
    zeichne(deal());
    expect(screen.queryByText(/Gutschein/)).not.toBeInTheDocument();
  });
});

describe("Bedienung", () => {
  it("meldet den Merken-Klick mit der Deal-Nummer", async () => {
    const onBookmark = vi.fn();
    zeichne(deal(), { onBookmark });
    await userEvent.click(screen.getByRole("button", { name: /merken/i }));
    expect(onBookmark).toHaveBeenCalledWith(1);
  });

  it("sagt über aria-pressed, ob schon gemerkt ist", () => {
    // Nur die Füllung des Symbols zu ändern, sieht ein Screenreader nicht.
    zeichne(deal({ bookmarked: true }), { onBookmark: vi.fn() });
    expect(screen.getByRole("button", { name: /merken/i }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("öffnet die Detailansicht über den Titel", async () => {
    const onOpen = vi.fn();
    zeichne(deal(), { onOpen });
    await userEvent.click(screen.getByText(/LEGO Technic Bagger/));
    expect(onOpen).toHaveBeenCalledWith(1);
  });

  it("verlinkt ohne Detailansicht direkt zum Shop", () => {
    zeichne(deal());
    const link = screen.getByRole("link", { name: /LEGO Technic Bagger/ });
    expect(link).toHaveAttribute("href", "https://shop.test/lego");
    // Ohne noopener kann die geöffnete Seite auf das Fenster zurückgreifen.
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});

describe("Zweite Sprache", () => {
  it("übersetzt die Karte", () => {
    window.localStorage.setItem("sparbit-sprache", "en");
    zeichne(deal({ urteil: "bestpreis" }));
    expect(screen.getByText("Best price ever")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view deal/i })).toBeInTheDocument();
  });
});
