"""Preisurteil aus der eigenen Beobachtung.

Der von der Quelle gemeldete Rabatt taugt wenig: Haendler rechnen gegen eine
UVP, die nie jemand bezahlt hat. "-70%" sagt darum nichts darueber, ob der
Preis gerade gut ist.

Was etwas sagt, ist der eigene Verlauf: Was hat dieser Artikel in den letzten
Wochen wirklich gekostet? Genau darauf antwortet dieses Modul - und es sagt
ehrlich "weiss ich nicht", wenn die Datenlage zu duenn ist. Ein erfundenes
Urteil waere schlimmer als keines.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .currency import to_eur
from .models import Deal, PriceHistory, utcnow

log = logging.getLogger(__name__)

# Urteilsstufen, von gut nach schlecht. Die Reihenfolge ist auch die
# Rangfolge fuer Regeln ("mindestens GUT").
BESTPREIS = "bestpreis"
SEHR_GUT = "sehr_gut"
GUT = "gut"
NORMAL = "normal"
TEURER = "teurer"
UVP_FRAGWUERDIG = "uvp_fragwuerdig"
UNBEKANNT = "unbekannt"

RANGFOLGE = [BESTPREIS, SEHR_GUT, GUT, NORMAL, TEURER, UVP_FRAGWUERDIG, UNBEKANNT]

LABEL = {
    BESTPREIS: "Bestpreis",
    SEHR_GUT: "sehr guter Preis",
    GUT: "guter Preis",
    NORMAL: "normaler Preis",
    TEURER: "war schon günstiger",
    UVP_FRAGWUERDIG: "UVP unglaubwürdig",
    UNBEKANNT: "zu wenig Daten",
}

# Ab wie vielen Messpunkten ueberhaupt geurteilt wird. Bei zwei Punkten ist
# jeder zweite Preis zwangslaeufig "der beste" - das waere Zufall, kein Urteil.
MIN_PUNKTE = 4
FENSTER_TAGE = 180
# Wie weit der Preis unter dem Ueblichen liegen muss.
SEHR_GUT_PERZENTIL = 0.10
GUT_PERZENTIL = 0.25
# Ab hier gilt die UVP als aufgeblasen: nie auch nur in ihre Naehe gekommen.
UVP_FAKTOR = 0.65


def euro(wert: float) -> str:
    """Betrag in deutscher Schreibweise. Als eigener Helfer, weil ein
    .replace(".", ",") ueber den fertigen Satz auch den Satzpunkt trifft."""
    return f"{wert:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".") + " €"


@dataclass
class Urteil:
    stufe: str
    text: str
    punkte: int
    tiefst: float | None = None
    median: float | None = None

    @property
    def label(self) -> str:
        return LABEL.get(self.stufe, self.stufe)


def _perzentil(werte: list[float], anteil: float) -> float:
    """Einfaches Perzentil ohne numpy - die Datenmengen sind winzig."""
    if not werte:
        raise ValueError("leere Liste")
    sortiert = sorted(werte)
    if len(sortiert) == 1:
        return sortiert[0]
    pos = anteil * (len(sortiert) - 1)
    unten = int(pos)
    oben = min(unten + 1, len(sortiert) - 1)
    rest = pos - unten
    return sortiert[unten] * (1 - rest) + sortiert[oben] * rest


def _tage_her(punkte: list[tuple[float, object]], preis: float) -> int | None:
    """Wann war es zuletzt guenstiger als jetzt?"""
    jetzt = utcnow()
    for wert, ts in reversed(punkte):
        if wert < preis * 0.995:
            if ts is None:
                return None
            zeit = ts if ts.tzinfo else ts.replace(tzinfo=jetzt.tzinfo)
            return max(0, (jetzt - zeit).days)
    return None


def bewerte(preis_eur: float | None,
            verlauf: list[tuple[float, object]],
            originalpreis_eur: float | None = None,
            ist_gratis: bool = False) -> Urteil:
    """Kern der Bewertung - ohne Datenbank, damit gut testbar.

    `verlauf` ist eine nach Zeit aufsteigend sortierte Liste von
    (preis_in_eur, zeitstempel).
    """
    if ist_gratis:
        return Urteil(BESTPREIS, "Gratis — günstiger geht nicht.", len(verlauf), 0.0)

    if preis_eur is None:
        return Urteil(UNBEKANNT, "Kein Preis erkannt.", len(verlauf))

    werte = [w for w, _ in verlauf if w is not None and w > 0]

    # UVP-Pruefung geht auch ohne Historie: wenn ein Artikel nie in die Naehe
    # seiner angeblichen UVP kam, ist der Rabatt daran gerechnet wertlos.
    if originalpreis_eur and werte and len(werte) >= MIN_PUNKTE:
        hoechster = max(werte)
        if hoechster < originalpreis_eur * UVP_FAKTOR:
            return Urteil(
                UVP_FRAGWUERDIG,
                f"Die UVP von {euro(originalpreis_eur)} ist unglaubwürdig — "
                f"beobachtet wurden höchstens {euro(hoechster)}.",
                len(werte), min(werte), _perzentil(werte, 0.5))

    if len(werte) < MIN_PUNKTE:
        return Urteil(
            UNBEKANNT,
            f"Erst {len(werte)} Messung{'en' if len(werte) != 1 else ''} — "
            f"für ein Urteil zu wenig.",
            len(werte), min(werte) if werte else None)

    tiefst = min(werte)
    median = _perzentil(werte, 0.5)
    p10 = _perzentil(werte, SEHR_GUT_PERZENTIL)
    p25 = _perzentil(werte, GUT_PERZENTIL)

    if preis_eur <= tiefst * 1.005:
        return Urteil(BESTPREIS,
                      f"Bestpreis — so günstig war es in {len(werte)} Messungen "
                      f"noch nie.", len(werte), tiefst, median)

    tage = _tage_her(verlauf, preis_eur)
    if preis_eur > median * 1.02:
        wann = f"vor {tage} Tagen" if tage else "schon einmal"
        return Urteil(TEURER,
                      f"Üblich sind {euro(median)} — {wann} lag es bei "
                      f"{euro(tiefst)}.", len(werte), tiefst, median)

    if preis_eur <= p10:
        return Urteil(SEHR_GUT,
                      f"Sehr guter Preis — nur {euro(tiefst)} war je günstiger.",
                      len(werte), tiefst, median)
    if preis_eur <= p25:
        return Urteil(GUT, f"Guter Preis — üblich sind {euro(median)}.",
                      len(werte), tiefst, median)

    return Urteil(NORMAL, f"Normaler Preis — üblich sind {euro(median)}.",
                  len(werte), tiefst, median)


def bewerte_deal(db: Session, deal: Deal) -> Urteil:
    """Urteil fuer einen Deal aus seiner gespeicherten Historie."""
    seit = utcnow() - timedelta(days=FENSTER_TAGE)
    zeilen = db.scalars(
        select(PriceHistory)
        .where(PriceHistory.deal_id == deal.id, PriceHistory.ts >= seit)
        .order_by(PriceHistory.ts.asc())).all()

    verlauf = [(to_eur(z.preis, z.waehrung), z.ts) for z in zeilen]
    verlauf = [(w, ts) for w, ts in verlauf if w is not None]

    preis_eur = deal.preis_eur if deal.preis_eur is not None else to_eur(
        deal.preis, deal.waehrung)
    original_eur = to_eur(deal.originalpreis, deal.waehrung)

    return bewerte(preis_eur, verlauf, original_eur, deal.ist_gratis)


def aktualisiere(db: Session, deals: list[Deal]) -> int:
    """Urteile neu berechnen und am Deal speichern."""
    geaendert = 0
    for deal in deals:
        urteil = bewerte_deal(db, deal)
        if deal.urteil != urteil.stufe or deal.urteil_text != urteil.text:
            deal.urteil = urteil.stufe
            deal.urteil_text = urteil.text
            geaendert += 1
        deal.urteil_am = utcnow()
    if geaendert:
        db.commit()
    return geaendert


def mindestens(stufe: str) -> list[str]:
    """Alle Stufen, die mindestens so gut sind wie die genannte."""
    if stufe not in RANGFOLGE:
        return []
    return RANGFOLGE[:RANGFOLGE.index(stufe) + 1]
