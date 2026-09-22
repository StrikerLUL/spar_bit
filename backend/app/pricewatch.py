"""Eigene Wunschliste: Artikel selbst beobachten statt auf Posts zu warten.

Der Preis wird aus **strukturierten Daten** gelesen, die Shops fuer
Suchmaschinen ohnehin ausliefern: JSON-LD nach schema.org, Open-Graph-Tags
oder Microdata. Das ist der stabile Teil einer Produktseite - CSS-Klassen
aendern sich bei jedem Redesign, `"@type": "Product"` nicht.

Findet sich nichts davon, wird das klar gemeldet, statt einen brüchigen
Selektor zu raten. Ein Preiswaechter, der still den falschen Wert liest, ist
schlimmer als einer, der sagt "kann ich nicht".
"""
from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from .currency import to_eur
from .models import WatchItem, WatchPrice, utcnow

log = logging.getLogger(__name__)

MAX_BYTES = 2_000_000          # Produktseiten sind gross; mehr braucht niemand
MAX_FEHLER = 5                 # danach wird der Eintrag pausiert

# Schluessel in der Settings-Tabelle: Adresse eines Render-Dienstes.
#
# Manche Shops setzen den Preis erst per JavaScript ein. Im rohen HTML
# steht dann nichts, und SparBit sagt ehrlich "kann ich nicht lesen" -
# das bleibt so. Wer es trotzdem braucht, stellt sich einen
# Render-Dienst daneben (browserless, ein eigener Playwright-Container)
# und traegt dessen Adresse hier ein.
#
# Bewusst nicht mitgeliefert: ein Browser im Image waere ein halbes
# Gigabyte und ein eigener Angriffspfad - fuer eine Handvoll Shops, die
# das Auslesen ohnehin nicht wollen. Wer ihn will, weiss, was er tut.
SCHLUESSEL_RENDER = "render_url"

# In der Adresse steht {url} fuer die Zieladresse. Beispiele:
#   http://browserless:3000/content?token=x&url={url}
#   http://renderer:8080/render?url={url}
RENDER_PLATZHALTER = "{url}"


class NichtGefunden(Exception):
    """Auf der Seite stand kein maschinenlesbarer Preis."""


@dataclass
class Fund:
    preis: float
    waehrung: str
    name: str | None = None
    bild: str | None = None
    verfuegbar: bool | None = None
    quelle: str = ""          # welches Verfahren gegriffen hat
    # Versandkosten, wenn der Shop sie maschinenlesbar angibt. None heisst
    # "steht nicht da" und nicht "kostenlos" - der Unterschied ist genau
    # der, an dem zwei Preise unvergleichbar werden: 199 EUR beim einen
    # und 195 EUR plus 9,90 EUR beim anderen.
    versand: float | None = None

    @property
    def gesamt(self) -> float:
        """Was wirklich zu zahlen ist, soweit bekannt."""
        return round(self.preis + (self.versand or 0.0), 2)


# --- JSON-LD ---------------------------------------------------------------

_JSONLD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)


def _flach(knoten) -> list[dict]:
    """JSON-LD verschachtelt beliebig tief (@graph, Listen, itemListElement)."""
    gefunden: list[dict] = []
    if isinstance(knoten, list):
        for eintrag in knoten:
            gefunden.extend(_flach(eintrag))
    elif isinstance(knoten, dict):
        gefunden.append(knoten)
        for schluessel in ("@graph", "itemListElement", "mainEntity", "offers",
                           "hasVariant"):
            if schluessel in knoten:
                gefunden.extend(_flach(knoten[schluessel]))
    return gefunden


def _typ_passt(knoten: dict, gesucht: set[str]) -> bool:
    typ = knoten.get("@type")
    if isinstance(typ, list):
        return any(str(t).lower() in gesucht for t in typ)
    return str(typ or "").lower() in gesucht


def _zahl(wert) -> float | None:
    if wert is None:
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    text = str(wert).strip().replace(" ", "")
    # "1.299,00" (deutsch) vs "1,299.00" (englisch)
    if "," in text and "." in text:
        text = (text.replace(".", "").replace(",", ".")
                if text.rfind(",") > text.rfind(".")
                else text.replace(",", ""))
    elif "," in text:
        text = text.replace(",", ".")
    text = re.sub(r"[^\d.]", "", text)
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _versand(angebot: dict) -> float | None:
    """Versandkosten aus `shippingDetails`, wenn der Shop sie auszeichnet.

    schema.org erlaubt mehrere Lieferoptionen. Genommen wird die
    guenstigste: sie entspricht dem, was in einem Preisvergleich zaehlt,
    und wer Express will, rechnet ohnehin selbst.

    Eine ausdrueckliche 0 ist ein Wert, kein fehlender Eintrag - "gratis
    Versand" ist eine Information, die im UI stehen soll.
    """
    roh = angebot.get("shippingDetails")
    if roh is None:
        return None
    kandidaten = roh if isinstance(roh, list) else [roh]

    preise: list[float] = []
    for eintrag in kandidaten:
        if not isinstance(eintrag, dict):
            continue
        rate = eintrag.get("shippingRate")
        for zeile in (rate if isinstance(rate, list) else [rate]):
            if not isinstance(zeile, dict):
                continue
            wert = _zahl(zeile.get("value"))
            if wert is not None and wert >= 0:
                preise.append(wert)
    return min(preise) if preise else None


def aus_jsonld(quelltext: str) -> Fund | None:
    for block in _JSONLD.findall(quelltext):
        try:
            daten = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue

        knoten = _flach(daten)
        produkte = [k for k in knoten if _typ_passt(k, {"product", "productmodel",
                                                        "individualproduct"})]
        angebote = [k for k in knoten
                    if _typ_passt(k, {"offer", "aggregateoffer", "unitpricespecification"})]

        for angebot in angebote:
            preis = _zahl(angebot.get("price") or angebot.get("lowPrice"))
            if preis is None or preis <= 0:
                continue
            waehrung = str(angebot.get("priceCurrency") or "EUR").upper()[:8]
            produkt = produkte[0] if produkte else {}
            bild = produkt.get("image")
            if isinstance(bild, list):
                bild = bild[0] if bild else None
            if isinstance(bild, dict):
                bild = bild.get("url")
            verfuegbar = None
            zustand = str(angebot.get("availability") or "").lower()
            if zustand:
                verfuegbar = "instock" in zustand or "preorder" in zustand
            return Fund(preis, waehrung,
                        name=str(produkt.get("name")) if produkt.get("name") else None,
                        bild=str(bild) if bild else None,
                        verfuegbar=verfuegbar, quelle="JSON-LD",
                        versand=_versand(angebot))
    return None


# --- Open Graph / Meta -----------------------------------------------------

def _meta(quelltext: str, *namen: str) -> str | None:
    for name in namen:
        muster = re.compile(
            rf'<meta[^>]+(?:property|name|itemprop)=["\']{re.escape(name)}["\']'
            rf'[^>]*content=["\']([^"\']+)["\']', re.IGNORECASE)
        treffer = muster.search(quelltext)
        if treffer:
            return html.unescape(treffer.group(1))
        # Reihenfolge der Attribute kann umgekehrt sein
        muster2 = re.compile(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*'
            rf'(?:property|name|itemprop)=["\']{re.escape(name)}["\']', re.IGNORECASE)
        treffer = muster2.search(quelltext)
        if treffer:
            return html.unescape(treffer.group(1))
    return None


def aus_opengraph(quelltext: str) -> Fund | None:
    # Bewusst nur echte og:/product:-Namen. Ein blankes name="price" waere
    # Microdata (dafuer gibt es aus_microdata), und "twitter:data1" traegt
    # mal einen Preis und mal die Lieferzeit - ein falsch gelesener Preis
    # ist schlimmer als gar keiner.
    roh = _meta(quelltext, "product:price:amount", "og:price:amount",
                "product:price", "og:price")
    preis = _zahl(roh)
    if preis is None or preis <= 0:
        return None
    waehrung = (_meta(quelltext, "product:price:currency", "og:price:currency")
                or "EUR").upper()[:8]
    return Fund(preis, waehrung,
                name=_meta(quelltext, "og:title"),
                bild=_meta(quelltext, "og:image"), quelle="Open Graph")


# --- Microdata -------------------------------------------------------------

def aus_microdata(quelltext: str) -> Fund | None:
    roh = _meta(quelltext, "price")
    if roh is None:
        treffer = re.search(
            r'itemprop=["\']price["\'][^>]*content=["\']([^"\']+)["\']',
            quelltext, re.IGNORECASE)
        roh = treffer.group(1) if treffer else None
    preis = _zahl(roh)
    if preis is None or preis <= 0:
        return None
    waehrung_treffer = re.search(
        r'itemprop=["\']priceCurrency["\'][^>]*content=["\']([^"\']+)["\']',
        quelltext, re.IGNORECASE)
    return Fund(preis, (waehrung_treffer.group(1) if waehrung_treffer else "EUR")
                .upper()[:8], quelle="Microdata")


VERFAHREN = (aus_jsonld, aus_opengraph, aus_microdata)


def preis_aus_seite(quelltext: str) -> Fund:
    """Preis aus einer Produktseite lesen. Wirft NichtGefunden."""
    for verfahren in VERFAHREN:
        try:
            fund = verfahren(quelltext)
        except Exception as exc:      # kaputtes Markup soll nichts umwerfen
            log.debug("%s fehlgeschlagen: %s", verfahren.__name__, exc)
            continue
        if fund is not None:
            return fund
    raise NichtGefunden(
        "Kein maschinenlesbarer Preis gefunden (weder JSON-LD noch Open Graph "
        "noch Microdata). Diese Seite lässt sich nicht zuverlässig beobachten.")


# --- Abruf -----------------------------------------------------------------

def render_adresse(vorlage: str | None, ziel: str) -> str | None:
    """Die Abrufadresse fuer den Render-Dienst, oder None.

    Ohne {url} in der Vorlage gibt es keine Adresse - lieber gar nicht
    abrufen als den Dienst auf seine eigene Startseite schicken und den
    leeren Inhalt fuer eine Antwort halten.
    """
    vorlage = (vorlage or "").strip()
    if not vorlage or RENDER_PLATZHALTER not in vorlage:
        return None
    from urllib.parse import quote
    return vorlage.replace(RENDER_PLATZHALTER, quote(ziel, safe=""))


async def hole_seite(http, eintrag: WatchItem, render_vorlage: str | None) -> str:
    """Quelltext der Produktseite - direkt oder ueber den Render-Dienst."""
    ueber = (render_adresse(render_vorlage, eintrag.url)
             if getattr(eintrag, "rendern", False) else None)
    if ueber:
        # post() statt get(): der Dienst steht ueblicherweise im eigenen
        # Netz, und get() wuerde am Netzschutz haengenbleiben. Dieselbe
        # Ausnahme wie bei einem Gotify im Heimnetz - die Adresse hat man
        # selbst eingetragen.
        antwort = await http.get_intern(ueber)
    else:
        antwort = await http.get(eintrag.url)
    quelltext = antwort.text
    return quelltext[:MAX_BYTES] if len(quelltext) > MAX_BYTES else quelltext


async def pruefe(db: Session, eintrag: WatchItem, http,
                 render_vorlage: str | None = None) -> Fund | None:
    """Einen Eintrag abfragen und den Preis festhalten.

    Fehler landen am Eintrag statt zu fliegen - ein kaputter Shop darf die
    anderen nicht mitreissen.
    """
    eintrag.letzter_lauf = utcnow()
    try:
        quelltext = await hole_seite(http, eintrag, render_vorlage)
        fund = preis_aus_seite(quelltext)
    except Exception as exc:
        eintrag.fehler_in_folge += 1
        eintrag.letzter_fehler = f"{type(exc).__name__}: {exc}"[:400]
        if eintrag.fehler_in_folge >= MAX_FEHLER:
            eintrag.aktiv = False
            log.warning("Wunschliste: '%s' nach %d Fehlern pausiert",
                        eintrag.name, eintrag.fehler_in_folge)
        db.commit()
        return None

    eintrag.fehler_in_folge = 0
    eintrag.letzter_fehler = None
    eintrag.letzter_erfolg = utcnow()
    eintrag.letzter_preis = fund.preis
    eintrag.waehrung = fund.waehrung
    eintrag.versandkosten = fund.versand
    if fund.bild and not eintrag.bild:
        eintrag.bild = fund.bild
    if not eintrag.haendler:
        eintrag.haendler = (urlsplit(eintrag.url).hostname or "").removeprefix("www.")
    if eintrag.bester_preis is None or fund.preis < eintrag.bester_preis:
        eintrag.bester_preis = fund.preis

    # Nur echte Aenderungen aufzeichnen - sonst waechst die Historie mit
    # jedem Lauf, ohne etwas auszusagen.
    letzter = db.scalars(
        select(WatchPrice).where(WatchPrice.watch_id == eintrag.id)
        .order_by(WatchPrice.ts.desc()).limit(1)).first()
    # Auch eine reine Versandaenderung ist eine Aenderung: 195 + 9,90
    # wird 195 + 0, und der Verlauf saehe sonst wie Stillstand aus.
    versand_anders = (letzter is not None
                      and abs((letzter.versand or 0.0) - (fund.versand or 0.0)) > 0.004)
    if letzter is None or abs(letzter.preis - fund.preis) > 0.004 or versand_anders:
        db.add(WatchPrice(watch_id=eintrag.id, preis=fund.preis,
                          waehrung=fund.waehrung, versand=fund.versand))
    db.commit()
    return fund


def soll_melden(eintrag: WatchItem, fund: Fund) -> str | None:
    """Ist dieser Preis eine Meldung wert? Gibt den Grund zurueck.

    Zweimal dieselbe Meldung waere Laerm - darum merkt sich der Eintrag,
    zu welchem Preis er zuletzt gemeldet hat.
    """
    preis_eur = to_eur(fund.preis, fund.waehrung) or fund.preis
    ziel = eintrag.ziel_preis

    if ziel is not None and preis_eur <= ziel:
        if eintrag.zuletzt_gemeldet is None or preis_eur < eintrag.zuletzt_gemeldet - 0.004:
            return f"Zielpreis erreicht: {preis_eur:.2f} € (Ziel {ziel:.2f} €)"
        return None

    # Ohne Zielpreis: deutlicher Rutsch gegenueber dem bisher Besten.
    if ziel is None and eintrag.bester_preis is not None:
        vorher = eintrag.zuletzt_gemeldet or eintrag.bester_preis
        if preis_eur < vorher * 0.95:
            return f"Preis gefallen auf {preis_eur:.2f} €"
    return None


def faellige(db: Session) -> list[WatchItem]:
    """Eintraege, deren Intervall abgelaufen ist."""
    jetzt = utcnow()
    faellig = []
    for eintrag in db.scalars(select(WatchItem).where(WatchItem.aktiv.is_(True))):
        if eintrag.letzter_lauf is None:
            faellig.append(eintrag)
            continue
        letzter = eintrag.letzter_lauf
        if letzter.tzinfo is None:
            letzter = letzter.replace(tzinfo=jetzt.tzinfo)
        if jetzt - letzter >= timedelta(minutes=max(30, eintrag.intervall_minuten)):
            faellig.append(eintrag)
    return faellig
