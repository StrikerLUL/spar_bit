"""Generische JSON-Quelle: ein Endpunkt, ein paar Pfade, fertig.

Sechs Quellen fehlen bewusst - itch.io, Indiegala, Fanatical, Humble,
Unreal/FAB und Kleinanzeigen - weil sie HTML-Scraping erfordert haetten.
Die Begruendung steht in ENDPOINTS.md und gilt weiter: ein CSS-Selektor
haelt bis zum naechsten Redesign, und ein Preiswaechter, der still den
falschen Wert liest, ist schlimmer als einer, der sagt "kann ich nicht".

Viele dieser Seiten haben aber einen JSON-Endpunkt, den ihre eigene
Oberflaeche benutzt. Der ist kein CSS-Selektor - er ist die Schnittstelle,
gegen die die Seite selbst gebaut ist.

Statt sechs geratene Quellen mitzuliefern, gibt es hier den Bauplan:
Adresse eintragen, Pfad zur Liste nennen, Feldnamen zuordnen. Wer den
Endpunkt selbst geprueft hat, bekommt eine Quelle - ohne SparBit zu
aendern und ohne dass irgendjemand etwas raten muss.

    Adresse:        https://api.beispiel.de/v1/deals
    Liste:          data.items
    Titel:          title
    Adresse:        url
    Preis:          price.current
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit

from ..priceparse import parse_price_text
from .base import Category, DealItem, FetchContext, OptionSpec, Source, Verification, register


def pfad_lesen(daten: Any, pfad: str) -> Any:
    """Verschachtelten Wert holen: "data.items", "price.current", "a.0.b".

    Absichtlich winzig gehalten - kein JSONPath, keine Filter. Was sich
    damit nicht ausdruecken laesst, gehoert in ein Plugin (siehe
    SPARBIT_PLUGIN_DIR), nicht in eine Ausdruckssprache, die niemand mehr
    debuggen kann.
    """
    if not pfad:
        return daten
    for teil in pfad.split("."):
        if daten is None:
            return None
        if isinstance(daten, list):
            if not teil.isdigit() or int(teil) >= len(daten):
                return None
            daten = daten[int(teil)]
        elif isinstance(daten, dict):
            daten = daten.get(teil)
        else:
            return None
    return daten


def _als_zahl(wert: Any) -> float | None:
    if wert is None or isinstance(wert, bool):
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    return parse_price_text(str(wert)).preis


class CustomJson(Source):
    id = "custom_json"
    display_name = "Eigene JSON-Schnittstelle"
    category = Category.EXPERIMENTAL
    default_interval = 1800
    min_interval = 600
    experimental = True
    verification = Verification.UNVERIFIED
    beschreibung = ("Ein JSON-Endpunkt, den du selbst geprueft hast. Fuer "
                    "Seiten ohne Feed, die ihrer eigenen Oberflaeche aber "
                    "JSON liefern (itch.io, Indiegala, Fanatical ...).")
    docs_url = "https://github.com/StrikerLUL/spar_bit/blob/main/ENDPOINTS.md"

    options_schema = [
        OptionSpec("url", "Adresse des Endpunkts", "string", "", pflicht=True,
                   help="Vollstaendige URL, die JSON zurueckgibt."),
        OptionSpec("liste", "Pfad zur Liste", "string", "",
                   help="Punkt-Schreibweise, z.B. data.items. Leer, wenn die "
                        "Antwort selbst schon die Liste ist."),
        OptionSpec("feld_titel", "Feld: Titel", "string", "title", pflicht=True),
        OptionSpec("feld_url", "Feld: Adresse", "string", "url", pflicht=True),
        OptionSpec("feld_preis", "Feld: Preis", "string", "price"),
        OptionSpec("feld_originalpreis", "Feld: Streichpreis", "string", ""),
        OptionSpec("feld_bild", "Feld: Bild", "string", ""),
        OptionSpec("feld_beschreibung", "Feld: Beschreibung", "string", ""),
        OptionSpec("waehrung", "Waehrung", "string", "EUR"),
        OptionSpec("haendler", "Haendler-Label", "string", "",
                   help="Leer = Hostname des Endpunkts."),
        OptionSpec("teiler", "Preis teilen durch", "int", 1,
                   help="Fuer Schnittstellen, die in Cent rechnen: 100."),
        OptionSpec("max_items", "Max. Eintraege", "int", 60),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        url = str(ctx.opt("url", "")).strip()
        if not url:
            raise ValueError("Keine Adresse eingetragen.")

        daten = await ctx.http.get_json(url, cache_key=f"custom_json:{url}")
        return self.parse(daten, ctx, url)

    def parse(self, daten: Any, ctx: FetchContext, url: str) -> list[DealItem]:
        roh_liste = pfad_lesen(daten, str(ctx.opt("liste", "") or ""))
        if roh_liste is None:
            raise ValueError(
                f"Unter '{ctx.opt('liste')}' steht nichts. Antwort beginnt mit: "
                f"{str(daten)[:120]}")
        if not isinstance(roh_liste, list):
            raise ValueError(f"Unter '{ctx.opt('liste')}' steht kein Array, "
                             f"sondern {type(roh_liste).__name__}.")

        label = str(ctx.opt("haendler", "") or "") or (urlsplit(url).hostname or "")
        waehrung = str(ctx.opt("waehrung", "EUR") or "EUR").upper()[:8]
        teiler = max(1, int(ctx.opt("teiler", 1) or 1))
        grenze = max(1, int(ctx.opt("max_items", 60) or 60))

        items: list[DealItem] = []
        for eintrag in roh_liste[:grenze]:
            titel = pfad_lesen(eintrag, str(ctx.opt("feld_titel", "title")))
            ziel = pfad_lesen(eintrag, str(ctx.opt("feld_url", "url")))
            if not titel or not ziel:
                continue
            # Relative Adressen gegen den Endpunkt aufloesen - viele
            # Schnittstellen liefern nur "/spiel/xyz".
            ziel = urljoin(url, str(ziel))

            preis = _als_zahl(pfad_lesen(eintrag, str(ctx.opt("feld_preis", "") or "")))
            original = _als_zahl(pfad_lesen(
                eintrag, str(ctx.opt("feld_originalpreis", "") or "")))
            if teiler > 1:
                preis = preis / teiler if preis is not None else None
                original = original / teiler if original is not None else None

            bild = pfad_lesen(eintrag, str(ctx.opt("feld_bild", "") or ""))
            text = pfad_lesen(eintrag, str(ctx.opt("feld_beschreibung", "") or ""))

            items.append(DealItem(
                titel=str(titel)[:500],
                url=ziel,
                quelle=self.id,
                preis=preis,
                originalpreis=original,
                waehrung=waehrung,
                haendler=label or None,
                bild=str(bild) if bild else None,
                beschreibung=str(text)[:2000] if text else None,
            ))
        return items


register(CustomJson())
