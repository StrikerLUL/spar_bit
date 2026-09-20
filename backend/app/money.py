"""Geldbetraege einheitlich darstellen.

Es gab an vier Stellen im Projekt eine eigene Variante, Preise zu formatieren -
und damit vier Gelegenheiten, es unterschiedlich falsch zu machen. Hier steht
die eine Wahrheit; alles andere ruft hier an.

Regeln:
  * Deutsche Schreibweise: 1.299,00 €
  * Waehrungszeichen hinter dem Betrag, mit schmalem Leerzeichen
  * 0,00 ist nicht automatisch "gratis" - das entscheidet der Aufrufer,
    denn eine Ersparnis von 0 € ist kein Geschenk.
"""
from __future__ import annotations

SYMBOL = {"EUR": "\u20ac", "USD": "$", "GBP": "\u00a3", "CHF": "CHF", "PLN": "z\u0142"}


def symbol(waehrung: str | None) -> str:
    code = (waehrung or "EUR").upper()
    return SYMBOL.get(code, code)


def betrag(wert: float | None, waehrung: str | None = "EUR") -> str:
    """Nackter Betrag mit Waehrung: 1.299,00 EUR -> '1.299,00 €'.

    Die Umformung geht ueber einen Platzhalter, weil ein naives
    .replace(".", ",") auf dem fertigen String auch die Tausenderpunkte
    trifft, die Pythons Formatierung gerade erst gesetzt hat.
    """
    if wert is None:
        return "\u2014"
    roh = f"{wert:,.2f}".replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return f"{roh}\u00a0{symbol(waehrung)}"


def preis(wert: float | None, waehrung: str | None = "EUR",
          gratis: bool = False) -> str:
    """Betrag als Preis - 0,00 heisst hier tatsaechlich 'gratis'."""
    if gratis or (wert is not None and wert <= 0.009):
        return "gratis"
    if wert is None:
        return "Preis unbekannt"
    return betrag(wert, waehrung)


def preiszeile(wert: float | None, waehrung: str | None = "EUR",
               gratis: bool = False, original: float | None = None,
               eur: float | None = None) -> str:
    """Vollstaendige Preisangabe inklusive Streichpreis und EUR-Hinweis.

    Der EUR-Hinweis erscheint nur bei Fremdwaehrung: '$9.99 (≈ 9,19 €)'.
    Ohne ihn steht in einer Meldung eine Zahl, die man nicht mit dem
    eigenen Preislimit vergleichen kann.
    """
    teile = [preis(wert, waehrung, gratis)]
    code = (waehrung or "EUR").upper()
    if code != "EUR" and eur is not None and not gratis and wert is not None:
        teile.append(f"(\u2248 {betrag(eur, 'EUR')})")
    if original is not None and wert is not None and original > wert:
        teile.append(f"statt {betrag(original, waehrung)}")
    return " ".join(teile)


def rabatt_text(prozent: float | None) -> str:
    if prozent is None:
        return ""
    return f"\u2212{prozent:.0f}\u00a0%"
