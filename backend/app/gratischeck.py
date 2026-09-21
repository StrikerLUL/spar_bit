"""Nachsehen, ob die Zielseite haelt, was der Deal verspricht.

Der haeufigste Aerger mit einem Deal-Melder ist nicht die verpasste
Gelegenheit, sondern die falsche: es steht "kostenlos" da, man klickt, und
die Seite will 14,99 EUR. Zwei Ursachen hat das.

Die erste ist der Text selbst - "gratis Versand" macht die Ware nicht
gratis. Dagegen hilft `priceparse.pruefe_gratis`, und zwar ohne Netz.

Die zweite Ursache kann kein Parser erkennen: der Deal war echt und ist
abgelaufen, oder die Quelle hat sich schlicht geirrt. Dafuer gibt es dieses
Modul. Es holt die Zielseite und sucht dort nach einer *ausgezeichneten*
Preisangabe - schema.org, OpenGraph, Microdata. Also nach dem, was der
Haendler selbst maschinenlesbar hinschreibt, nicht nach irgendeiner Zahl im
Fliesstext.

Was hier bewusst NICHT passiert: raten. Findet sich keine ausgezeichnete
Angabe, lautet das Ergebnis `unklar` - und dann bleibt alles, wie die Quelle
es gemeldet hat. Ein Waechter, der bei Unsicherheit widerspricht, waere
schlimmer als gar keiner.

Verifizierungsstand: die Extraktion ist gegen Format-Fixtures geprueft
(schema.org/JSON-LD, Microdata, OpenGraph, Cloudflare-Abweisung), nicht
gegen echte Shop-Seiten - die Build-Umgebung kommt an keinen einzigen Host
heran. Wie sich die Seiten deiner Quellen wirklich verhalten, zeigt erst
der Betrieb; die Spalte "Herkunft" im Befund sagt dir jeweils, woher die
Zahl kam.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from .currency import to_eur
from .priceparse import parse_number

log = logging.getLogger(__name__)

# --- Ergebnis-Stufen -------------------------------------------------------

BESTAETIGT = "bestaetigt"      # Seite nennt denselben Preis
WIDERLEGT = "widerlegt"        # Seite nennt einen anderen, hoeheren Preis
ABGELAUFEN = "abgelaufen"      # Seite sagt: gibt es nicht mehr
UNKLAR = "unklar"              # nichts Ausgezeichnetes gefunden
UNERREICHBAR = "unerreichbar"  # Block, Timeout, Fehler

LABEL = {
    BESTAETIGT: "geprüft",
    WIDERLEGT: "stimmt nicht",
    ABGELAUFEN: "abgelaufen",
    UNKLAR: "ungeprüft",
    UNERREICHBAR: "nicht erreichbar",
}

# Nur diese beiden Stufen greifen in den Deal ein. `unklar` und
# `unerreichbar` sind ausdruecklich folgenlos.
WIDERSPRUCH = (WIDERLEGT, ABGELAUFEN)

# Und nur DIESE eine Stufe heisst "gibt es nicht mehr".
#
# Der Unterschied ist wichtiger, als er aussieht: `widerlegt` bedeutet, dass
# der Preis von der Zielseite korrigiert wurde - das Angebot existiert also
# weiterhin, es ist nur teurer als gemeldet. Es aus dem Feed zu werfen waere
# falsch; gemeldet wird es trotzdem nicht mehr (dafuer steht WIDERSPRUCH).
# Der Schalter "Abgelaufene ausblenden" darf sich nur hierauf beziehen,
# sonst versteckt er etwas anderes, als er verspricht.
VORBEI = (ABGELAUFEN,)

# Wie weit der Seitenpreis ueber dem gemeldeten liegen darf, ohne als
# Widerspruch zu gelten. Cent-Differenzen entstehen durch Rundung und
# Waehrungsumrechnung, nicht durch einen falschen Deal.
TOLERANZ_ABSOLUT = 0.51
TOLERANZ_ANTEIL = 0.05

# Groesser laedt sich keine Produktseite, die wir noch auswerten wollen.
MAX_BYTES = 2_000_000


@dataclass
class Befund:
    status: str
    text: str
    preis: float | None = None
    waehrung: str | None = None
    preis_eur: float | None = None
    herkunft: str | None = None          # "json-ld" | "microdata" | "opengraph"
    belege: list[str] = field(default_factory=list)

    @property
    def widerspricht(self) -> bool:
        return self.status in WIDERSPRUCH

    def als_dict(self) -> dict:
        return {"status": self.status, "label": LABEL.get(self.status, self.status),
                "text": self.text, "preis": self.preis, "waehrung": self.waehrung,
                "preis_eur": self.preis_eur, "herkunft": self.herkunft,
                "belege": self.belege}


# --- HTML aufbereiten ------------------------------------------------------

_SKRIPT_RE = re.compile(r"<(script|style|template)\b[^>]*>.*?</\1>",
                        re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_LD_RE = re.compile(
    r"<script[^>]+type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL)


def sichtbarer_text(html: str) -> str:
    """Seitentext ohne Skripte und Formatvorlagen, klein geschrieben.

    Die Skripte fliegen raus, weil in JS-Vorlagen reihenweise Bausteine wie
    "ausverkauft" stehen, die auf der Seite selbst gar nicht vorkommen. Wer
    sie mitliest, erklaert jeden zweiten Shop fuer ausverkauft.
    """
    ohne = _SKRIPT_RE.sub(" ", html or "")
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", ohne)).lower()


def json_ld_bloecke(html: str) -> list[Any]:
    out: list[Any] = []
    for m in _LD_RE.finditer(html or ""):
        roh = m.group(1).strip()
        try:
            out.append(json.loads(roh))
        except (ValueError, TypeError):
            # Manche Shops haengen mehrere Objekte ohne Array aneinander.
            for stueck in re.split(r"}\s*{", roh):
                try:
                    out.append(json.loads("{" + stueck.strip("{} \n") + "}"))
                except (ValueError, TypeError):
                    continue
    return out


def _knoten(daten: Any) -> Iterator[dict]:
    """Jeden Dict-Knoten im JSON-LD-Baum durchlaufen (@graph inklusive)."""
    if isinstance(daten, dict):
        yield daten
        for wert in daten.values():
            if isinstance(wert, (dict, list)):
                yield from _knoten(wert)
    elif isinstance(daten, list):
        for eintrag in daten:
            yield from _knoten(eintrag)


def _zahl(wert: Any) -> float | None:
    if isinstance(wert, (int, float)):
        return float(wert)
    if isinstance(wert, str):
        return parse_number(wert.strip())
    return None


def _waehrung(wert: Any) -> str | None:
    if isinstance(wert, str) and re.fullmatch(r"[A-Za-z]{3}", wert.strip()):
        return wert.strip().upper()
    return None


# --- Die drei Fundstellen --------------------------------------------------

def aus_json_ld(html: str) -> tuple[float | None, str | None, str | None]:
    """(Preis, Waehrung, Verfuegbarkeit) aus schema.org-Angeboten."""
    preis: float | None = None
    waehrung: str | None = None
    verfuegbar: str | None = None

    for block in json_ld_bloecke(html):
        for knoten in _knoten(block):
            typ = str(knoten.get("@type", "")).lower()
            if "offer" not in typ and "price" not in knoten \
                    and "lowPrice" not in knoten:
                continue
            for feld in ("price", "lowPrice"):
                wert = _zahl(knoten.get(feld))
                if wert is not None and (preis is None or wert < preis):
                    preis = wert
                    waehrung = (_waehrung(knoten.get("priceCurrency"))
                                or waehrung)
            spez = knoten.get("priceSpecification")
            if isinstance(spez, dict):
                wert = _zahl(spez.get("price"))
                if wert is not None and (preis is None or wert < preis):
                    preis = wert
                    waehrung = _waehrung(spez.get("priceCurrency")) or waehrung
            roh = knoten.get("availability")
            if isinstance(roh, str):
                verfuegbar = roh.rsplit("/", 1)[-1].lower()
    return preis, waehrung, verfuegbar


_META_PREIS = re.compile(
    r"<meta[^>]+(?:property|name|itemprop)\s*=\s*[\"']"
    r"(?:product:price:amount|og:price:amount|twitter:data1|price)[\"']"
    r"[^>]*\scontent\s*=\s*[\"']([^\"']{1,24})[\"']", re.IGNORECASE)
_META_PREIS_UMGEKEHRT = re.compile(
    r"<meta[^>]+content\s*=\s*[\"']([^\"']{1,24})[\"'][^>]*"
    r"(?:property|name|itemprop)\s*=\s*[\"']"
    r"(?:product:price:amount|og:price:amount|price)[\"']", re.IGNORECASE)
_META_WAEHRUNG = re.compile(
    r"<meta[^>]+(?:property|name|itemprop)\s*=\s*[\"']"
    r"(?:product:price:currency|og:price:currency|priceCurrency)[\"']"
    r"[^>]*\scontent\s*=\s*[\"']([A-Za-z]{3})[\"']", re.IGNORECASE)
_MICRO_PREIS = re.compile(
    r"<[^>]+itemprop\s*=\s*[\"']price[\"'][^>]*\scontent\s*=\s*"
    r"[\"']([^\"']{1,24})[\"']", re.IGNORECASE)
_MICRO_VERFUEGBAR = re.compile(
    r"itemprop\s*=\s*[\"']availability[\"'][^>]*(?:href|content)\s*=\s*"
    r"[\"'][^\"']*?/([A-Za-z]+)[\"']", re.IGNORECASE)


def aus_meta(html: str) -> tuple[float | None, str | None, str | None]:
    """(Preis, Waehrung, Herkunft) aus Microdata bzw. OpenGraph."""
    html = html or ""
    treffer = _MICRO_PREIS.search(html)
    if treffer:
        wert = parse_number(treffer.group(1))
        if wert is not None:
            w = _META_WAEHRUNG.search(html)
            return wert, (w.group(1).upper() if w else None), "microdata"

    for regex in (_META_PREIS, _META_PREIS_UMGEKEHRT):
        treffer = regex.search(html)
        if treffer:
            wert = parse_number(treffer.group(1))
            if wert is not None:
                w = _META_WAEHRUNG.search(html)
                return wert, (w.group(1).upper() if w else None), "opengraph"
    return None, None, None


# --- Verfuegbarkeit --------------------------------------------------------

# schema.org sagt es maschinenlesbar - darauf ist Verlass.
_WEG_SCHEMA = {"outofstock", "soldout", "discontinued", "instoreonly"}

# Und das hier steht im Klartext auf der Seite. Schwaecheres Indiz, darum
# zaehlt es nur, wenn sich gar keine ausgezeichnete Preisangabe findet.
_WEG_TEXT = [
    "nicht mehr verfügbar", "nicht mehr erhältlich", "derzeit nicht verfügbar",
    "aktuell nicht verfügbar", "ausverkauft", "vergriffen", "angebot beendet",
    "aktion beendet", "deal beendet", "abgelaufen", "nicht mehr vorrätig",
    "sold out", "out of stock", "no longer available", "offer expired",
    "this deal has expired", "currently unavailable", "promotion has ended",
]


def weg_laut_text(html: str) -> str | None:
    text = sichtbarer_text(html)
    for marker in _WEG_TEXT:
        if marker in text:
            return marker
    return None


# --- Urteil ----------------------------------------------------------------

def analysiere(html: str, *, status_code: int = 200,
               erwartet_gratis: bool = False,
               erwartet_eur: float | None = None) -> Befund:
    """Aus einer geholten Seite einen Befund machen. Ohne Netz, testbar."""
    if status_code in (404, 410):
        return Befund(ABGELAUFEN, f"Seite gibt HTTP {status_code} zurück.")

    preis, waehrung, verfuegbar = aus_json_ld(html)
    herkunft = "json-ld" if preis is not None else None
    if preis is None:
        preis, waehrung, herkunft = aus_meta(html)
    if verfuegbar is None:
        treffer = _MICRO_VERFUEGBAR.search(html or "")
        if treffer:
            verfuegbar = treffer.group(1).lower()

    belege: list[str] = []
    if herkunft:
        belege.append(f"Preisangabe aus {herkunft}")
    if verfuegbar:
        belege.append(f"Verfügbarkeit laut Seite: {verfuegbar}")

    if verfuegbar and verfuegbar in _WEG_SCHEMA:
        return Befund(ABGELAUFEN, "Die Seite führt den Artikel als nicht "
                                  "mehr verfügbar.", preis, waehrung,
                      to_eur(preis, waehrung or "EUR"), herkunft, belege)

    if preis is None:
        marker = weg_laut_text(html)
        if marker:
            return Befund(ABGELAUFEN,
                          f"Kein Preis ausgezeichnet, und auf der Seite steht "
                          f"„{marker}“.", belege=belege + [f"Textfund: {marker}"])
        return Befund(UNKLAR, "Kein ausgezeichneter Preis auf der Seite - "
                              "die Meldung der Quelle bleibt unangetastet.",
                      belege=belege)

    preis_eur = to_eur(preis, waehrung or "EUR")

    if erwartet_gratis:
        if preis <= 0.009:
            return Befund(BESTAETIGT, "Die Seite führt den Artikel mit 0,00.",
                          preis, waehrung, preis_eur, herkunft, belege)
        betrag = f"{preis:.2f} {waehrung or ''}".strip()
        return Befund(WIDERLEGT, f"Als gratis gemeldet, die Seite verlangt "
                                 f"{betrag}.", preis, waehrung, preis_eur,
                      herkunft, belege)

    if erwartet_eur is None:
        return Befund(UNKLAR, "Kein Vergleichspreis bekannt.", preis, waehrung,
                      preis_eur, herkunft, belege)

    if preis_eur is None:
        return Befund(UNKLAR, f"Seitenpreis in {waehrung or 'unbekannter Währung'} "
                              f"nicht umrechenbar.", preis, waehrung, None,
                      herkunft, belege)

    grenze = max(TOLERANZ_ABSOLUT, erwartet_eur * TOLERANZ_ANTEIL)
    if preis_eur <= erwartet_eur + grenze:
        return Befund(BESTAETIGT, f"Seitenpreis {preis_eur:.2f} € deckt sich "
                                  f"mit der Meldung.", preis, waehrung,
                      preis_eur, herkunft, belege)
    return Befund(WIDERLEGT, f"Gemeldet {erwartet_eur:.2f} €, die Seite "
                             f"verlangt {preis_eur:.2f} €.", preis, waehrung,
                  preis_eur, herkunft, belege)


async def pruefe(http, url: str, *, erwartet_gratis: bool = False,
                 erwartet_eur: float | None = None) -> Befund:
    """Seite holen und auswerten. Wirft nie - ein Fehler ist ein Befund."""
    try:
        resp = await http.get(url, headers={
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        })
    except Exception as exc:                       # noqa: BLE001 - bewusst breit
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return Befund(ABGELAUFEN, f"Seite gibt HTTP {status} zurück.")
        return Befund(UNERREICHBAR,
                      f"Seite nicht erreichbar: {type(exc).__name__}: {exc}"[:200])

    typ = resp.headers.get("content-type", "")
    if "html" not in typ.lower() and "xml" not in typ.lower():
        return Befund(UNKLAR, f"Keine HTML-Seite ({typ or 'ohne Typangabe'}).")
    if len(resp.content) > MAX_BYTES:
        return Befund(UNKLAR, "Seite zu gross zum Auswerten.")

    return analysiere(resp.text, status_code=resp.status_code,
                      erwartet_gratis=erwartet_gratis,
                      erwartet_eur=erwartet_eur)


# --- Anwendung auf echte Deals --------------------------------------------

SETTING_AN = "gratis_pruefen"          # Schalter unter Logs & System
SETTING_MAX = "gratis_pruefen_max"     # Deckel pro Lauf
# Zweiter Schalter: auch normale Deals auf Aktualitaet pruefen, nicht nur
# Gratis-Funde. Getrennt schaltbar, weil es deutlich mehr Anfragen sind.
SETTING_AKTUALITAET = "aktualitaet_pruefen"
SETTING_AKTUALITAET_MAX = "aktualitaet_max"

MAX_PRO_LAUF = 12
# Ab diesem Preis lohnt die Gegenprobe auch ohne Gratis-Marke: ein Fund
# unter zwei Euro ist entweder ein echter Knaller oder ein Irrtum.
BILLIG_AB_EUR = 2.0
# Wie lange ein Befund haelt, bevor erneut nachgesehen wird.
FRISCH_STUNDEN = 12

# --- Aktualitaet ----------------------------------------------------------
#
# Der zweite Aerger nach dem falschen Gratis-Schild ist der abgelaufene
# Deal: die Karte steht noch da, man klickt, und die Aktion ist seit Tagen
# vorbei. Dagegen half die bisherige Pruefung nicht - sie sah sich nur
# Gratis-Funde an. Jetzt wird jeder Deal irgendwann nachgesehen, aber in
# einer Reihenfolge, die sich nach dem Aerger richtet, und mit einem
# Deckel pro Lauf.

MAX_AKTUALITAET_PRO_LAUF = 25
# Aelter als das wird gar nicht mehr nachgesehen. Der Wert orientiert sich
# an der Aufbewahrungsfrist (Vorgabe 60 Tage): waere er wie anfangs bei 21,
# stuenden Deals zwischen 21 und 60 Tagen ungeprueft im Feed, und genau die
# sind am ehesten tot.
AKTUALITAET_TAGE = 50
# Bis hierher wird alles nachgesehen. Was aelter ist, kommt nur noch dran,
# wenn jemand es sich gemerkt hat oder es auffaellig ist - sonst verbraucht
# der Altbestand das Kontingent, das die frischen Deals brauchen.
AKTUALITAET_FRISCH_TAGE = 21
# Ein bestaetigter Deal wird seltener nachgeprueft als ein ungepruefter.
NACHSCHAU_STUNDEN = 24
# Und eine Seite, auf der nichts Auswertbares stand, noch seltener: sie
# wird beim naechsten Mal mit hoher Wahrscheinlichkeit wieder nichts
# hergeben. Das spart genau die Anfragen, die ohnehin "unklar" ergeben.
UNKLAR_FAKTOR = 4


def ist_kandidat(deal) -> bool:
    """Lohnt sich die Gegenprobe fuer diesen Deal *sofort* beim Einsammeln?

    Nicht jeder Deal - das waere ein Request pro Fund und damit ein
    Crawler. Beim Einsammeln nur die Faelle, in denen eine falsche Meldung
    wirklich aergert: alles, was als geschenkt oder fast geschenkt gemeldet
    wurde. Alles Weitere macht in Ruhe der Aktualitaets-Job.
    """
    if not deal.url:
        return False
    if deal.ist_gratis:
        return True
    return deal.preis_eur is not None and deal.preis_eur <= BILLIG_AB_EUR


def _veraltet(deal, jetzt) -> bool:
    from datetime import timedelta
    return (deal.check_am is None
            or deal.check_am < jetzt - timedelta(hours=FRISCH_STUNDEN))


def waehle_nachpruefung(db, *, grenze: int = MAX_AKTUALITAET_PRO_LAUF,
                        erwachsen_erlaubt: bool = False, jetzt=None) -> list:
    """Welche Deals werden als Naechstes auf Aktualitaet nachgesehen?

    Die Reihenfolge ist die ganze Kunst daran. Vorne steht, was noch nie
    geprueft wurde und was am meisten Schaden anrichtet, wenn es falsch
    ist - ein Deal, der jemanden auf eine tote Seite schickt, aergert mehr,
    je frischer und je auffaelliger er ist. Was schon als abgelaufen
    erkannt wurde, kommt gar nicht mehr dran: das Urteil aendert sich nicht
    mehr, und die Karte ist ohnehin ausgeblendet.
    """
    from datetime import timedelta

    from sqlalchemy import and_, or_, select

    from .models import Deal, utcnow

    jetzt = jetzt or utcnow()
    bedingungen = []
    # Ist der 18+-Bereich zu, wird dort auch nichts nachgesehen: solange
    # er aus ist, faesst SparBit diese Funde ueberhaupt nicht an - auch
    # nicht, um ihre Zielseite aufzurufen.
    if not erwachsen_erlaubt:
        bedingungen.append(Deal.erwachsen.is_(False))
    # Aeltere Deals nur noch, wenn sie jemanden interessieren.
    alt_erlaubt = or_(Deal.bookmarked.is_(True), Deal.ist_gratis.is_(True),
                      Deal.fehler_stufe.isnot(None))
    stumpf = (UNKLAR, UNERREICHBAR)
    faellig = or_(
        Deal.check_am.is_(None),
        # Seiten ohne auswertbare Angabe kommen seltener dran.
        and_(Deal.check_status.in_(stumpf),
             Deal.check_am < jetzt - timedelta(
                 hours=NACHSCHAU_STUNDEN * UNKLAR_FAKTOR)),
        and_(or_(Deal.check_status.is_(None), Deal.check_status.notin_(stumpf)),
             Deal.check_am < jetzt - timedelta(hours=NACHSCHAU_STUNDEN)),
    )
    stmt = (
        select(Deal)
        .where(*bedingungen,
               Deal.url.isnot(None),
               Deal.duplicate_of.is_(None),
               Deal.first_seen >= jetzt - timedelta(days=AKTUALITAET_TAGE),
               or_(Deal.first_seen >= jetzt - timedelta(
                   days=AKTUALITAET_FRISCH_TAGE), alt_erlaubt),
               Deal.check_status.notin_(WIDERSPRUCH) | Deal.check_status.is_(None),
               faellig)
        # Noch nie geprueft zuerst, danach das aelteste Urteil; bei
        # Gleichstand der neuere Deal, denn den sieht man oben im Feed.
        .order_by(Deal.check_am.is_(None).desc(), Deal.check_am,
                  Deal.first_seen.desc())
        .limit(max(1, grenze) * 4)
    )
    kandidaten = list(db.scalars(stmt))

    def dringlichkeit(deal) -> tuple:
        gemerkt = bool(deal.bookmarked)
        billig = deal.ist_gratis or (deal.preis_eur is not None
                                     and deal.preis_eur <= BILLIG_AB_EUR)
        auffaellig = bool(deal.fehler_stufe) or (deal.rabatt_prozent or 0) >= 70
        # Kleiner sortiert vor - darum negiert.
        return (not gemerkt, not billig, not auffaellig)

    kandidaten.sort(key=dringlichkeit)
    return kandidaten[:max(1, grenze)]


def uebernehme(deal, befund: Befund) -> bool:
    """Befund in den Deal schreiben. Gibt zurueck, ob sich etwas geaendert hat.

    Eingegriffen wird nur bei `widerlegt`: dann ist auf der Zielseite ein
    Preis ausgezeichnet, und der gilt. `abgelaufen` wird vermerkt und
    sperrt die Meldung, aendert aber keine Zahl - der Deal war ja richtig,
    als er gemeldet wurde.
    """
    from .models import utcnow

    deal.check_status = befund.status
    deal.check_text = befund.text[:500]
    deal.check_preis_eur = befund.preis_eur
    deal.check_am = utcnow()

    if befund.status != WIDERLEGT or befund.preis is None:
        return False

    deal.ist_gratis = False
    deal.preis = befund.preis
    deal.waehrung = befund.waehrung or deal.waehrung or "EUR"
    deal.preis_eur = befund.preis_eur
    if deal.originalpreis and deal.originalpreis > befund.preis:
        deal.rabatt_prozent = round((1 - befund.preis / deal.originalpreis) * 100, 1)
    else:
        deal.originalpreis = None
        deal.rabatt_prozent = None
    deal.gratis_hinweis = "von der Zielseite widerlegt"
    return True


async def pruefe_deals(db, http, deals: list, *, grenze: int | None = None,
                       alle: bool = False) -> dict:
    """Die Gegenprobe fuer eine Liste Deals. Wirft nie.

    Gibt eine kleine Bilanz zurueck sowie die IDs, die nicht mehr gemeldet
    werden sollten - widerlegt oder abgelaufen.
    """
    from .models import utcnow

    jetzt = utcnow()
    # `alle=True` kommt vom Aktualitaets-Job: dort ist die Auswahl schon
    # getroffen (waehle_nachpruefung), und sie soll hier nicht ein zweites
    # Mal auf Gratis-Funde eingedampft werden.
    kandidaten = [d for d in deals
                  if (alle or ist_kandidat(d)) and _veraltet(d, jetzt)]
    if not kandidaten:
        return {"geprueft": 0, "korrigiert": 0, "gesperrt": []}

    deckel = MAX_PRO_LAUF if grenze is None else max(0, int(grenze))
    kandidaten = kandidaten[:deckel]

    korrigiert = 0
    gesperrt: list[int] = []
    for deal in kandidaten:
        try:
            befund = await pruefe(http, deal.url,
                                  erwartet_gratis=bool(deal.ist_gratis),
                                  erwartet_eur=deal.preis_eur)
        except Exception as exc:                   # noqa: BLE001
            log.debug("Gratis-Pruefung fehlgeschlagen (%s): %s", deal.url, exc)
            continue
        if uebernehme(deal, befund):
            korrigiert += 1
            log.info("Gratis-Pruefung korrigiert '%s': %s",
                     deal.titel[:60], befund.text)
        if befund.widerspricht and deal.id is not None:
            gesperrt.append(deal.id)

    db.commit()
    return {"geprueft": len(kandidaten), "korrigiert": korrigiert,
            "gesperrt": gesperrt}
