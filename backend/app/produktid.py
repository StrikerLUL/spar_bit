"""Wann sind zwei Angebote wirklich derselbe Artikel?

Bisher entschied das der Titel: normalisieren, Zahlen vergleichen,
Aehnlichkeit messen. Das ist erstaunlich gut geworden - aber es bleibt
Raten. "Sony WH-1000XM5 Schwarz" und "Sony Kopfhoerer WH1000XM5, schwarz"
sind derselbe Artikel, und kein Schwellenwert trifft beide Faelle
zugleich, ohne irgendwo danebenzuliegen.

Viele Adressen tragen die Antwort aber mit sich herum: in einer
Amazon-URL steht die ASIN, in einer Steam-Adresse die AppID, in den
ausgezeichneten Daten einer Produktseite die EAN. Wo so eine Kennung da
ist, muss nichts geraten werden.

Das hilft doppelt. Das Zusammenfuehren wird exakt statt aehnlich - und
der Preisfehler-Waechter bekommt endlich das, was ihm bisher fehlte:
Fremdpreise. Sein staerkstes Indiz nach der Kommastelle ist der
Vergleich mit anderen Quellen, und den gibt es nur, wenn mehrere
Quellen erkennbar denselben Artikel melden.

Die Kennung wird mit ihrer Herkunft gespeichert ("asin:B07H8MJ2BF"),
damit eine Steam-AppID nie versehentlich auf eine EAN trifft.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

# Amazon: /dp/<ASIN>, /gp/product/<ASIN>, auch mitten im Pfad.
_AMAZON = re.compile(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})(?:[/?]|$)")
# Steam: /app/<id>/Slug/
_STEAM = re.compile(r"store\.steampowered\.com/app/(\d+)")
# GOG und Epic haben keine Zahl, aber einen stabilen Slug im Pfad.
_GOG = re.compile(r"gog\.com/(?:[a-z]{2}/)?game/([a-z0-9_]+)")
_EPIC = re.compile(r"epicgames\.com/(?:store/)?(?:[a-z-]+/)?p/([a-z0-9-]+)")
# Media Markt und Saturn haengen die Artikelnummer hinten an.
_MM_SATURN = re.compile(r"(?:mediamarkt|saturn)\.de/.*?-(\d{6,9})(?:\.html|$)")

# 8, 12, 13 oder 14 Stellen - EAN, UPC, GTIN sind dieselbe Familie.
_GTIN = re.compile(r"^\d{8}$|^\d{12,14}$")


def aus_url(url: str) -> str | None:
    """Produktkennung aus der Adresse lesen, wenn eine drinsteht."""
    if not url:
        return None

    treffer = _AMAZON.search(url)
    if treffer:
        return f"asin:{treffer.group(1)}"

    treffer = _STEAM.search(url)
    if treffer:
        return f"steam:{treffer.group(1)}"

    treffer = _GOG.search(url)
    if treffer:
        return f"gog:{treffer.group(1)}"

    treffer = _EPIC.search(url)
    if treffer:
        return f"epic:{treffer.group(1)}"

    treffer = _MM_SATURN.search(url)
    if treffer:
        return f"mms:{treffer.group(1)}"

    # Manche Shops haengen die Artikelnummer als Parameter an.
    try:
        felder = parse_qs(urlsplit(url).query)
    except ValueError:
        return None
    for schluessel in ("ean", "gtin", "gtin13", "asin"):
        werte = felder.get(schluessel) or []
        if werte:
            return normalisiere(schluessel, werte[0])
    return None


def normalisiere(art: str, wert: str) -> str | None:
    """Eine gefundene Kennung in die Form <art>:<wert> bringen."""
    wert = (wert or "").strip().replace("-", "").replace(" ", "")
    if not wert:
        return None
    art = art.lower()
    if art in ("ean", "gtin", "gtin8", "gtin12", "gtin13", "gtin14", "upc"):
        if not _GTIN.match(wert):
            return None
        # Alle auf 13 Stellen bringen: dieselbe Ware traegt je nach Land
        # und Shop 12, 13 oder 14 Stellen, und fuehrende Nullen sind
        # bedeutungslos. Ohne das faende "0012345678905" nie die "12345678905".
        return f"gtin:{wert.lstrip('0').zfill(13)}"
    if art == "asin":
        return f"asin:{wert.upper()}" if len(wert) == 10 else None
    return f"{art}:{wert}"


def aus_strukturierten_daten(daten: dict) -> str | None:
    """Kennung aus schema.org-Feldern lesen (JSON-LD, Microdata).

    Genau die Felder, die Shops fuer Suchmaschinen ohnehin ausliefern -
    derselbe stabile Teil der Seite, aus dem die Wunschliste schon ihren
    Preis liest.
    """
    if not isinstance(daten, dict):
        return None
    for feld in ("gtin13", "gtin14", "gtin12", "gtin8", "gtin", "ean", "upc"):
        wert = daten.get(feld)
        if wert:
            kennung = normalisiere(feld, str(wert))
            if kennung:
                return kennung
    # mpn und sku sind nur innerhalb eines Shops eindeutig - als
    # quellenuebergreifende Identitaet taugen sie darum nicht.
    return None


def fuer_deal(url: str, roh: dict | None = None) -> str | None:
    """Was sich ueber diesen Deal sagen laesst: erst Daten, dann Adresse."""
    aus_daten = aus_strukturierten_daten(roh or {})
    return aus_daten or aus_url(url)
