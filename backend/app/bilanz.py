"""Was das Ganze eigentlich gebracht hat.

SparBit sammelt seit dem ersten Tag alles, was fuer diese Frage noetig
ist: Preisverlauf, Urteile, gemerkte Deals, geclaimte Gratis-Spiele.
Beantwortet hat sie nie jemand. Man sah Deals, Regeln und Statistiken
ueber Quellen - aber nicht, was unter dem Strich steht.

Zwei Vorsichtsmassnahmen, damit die Zahl ehrlich bleibt:

* Gerechnet wird gegen den **beobachteten Referenzpreis** (Median des
  eigenen Verlaufs), nicht gegen die UVP. Gegen eine UVP zu rechnen,
  die nie jemand bezahlt hat, waere genau der Taschenspielertrick, den
  SparBit den Haendlern vorwirft.
* Gezaehlt wird nur, was ich **angefasst** habe - gemerkt oder mit einem
  Alarm versehen. Was ungesehen vorbeigezogen ist, hat mir nichts
  gespart, egal wie guenstig es war.

Es bleibt eine Schaetzung, und sie sagt das auch. "Du haettest sparen
koennen" ist keine Kontoauszugszeile.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ClaimEvent, Deal, Interaction, PriceHistory, utcnow

log = logging.getLogger(__name__)

# Ab wie vielen Preispunkten der Median als Referenz taugt. Darunter ist
# es kein Verlauf, sondern eine Momentaufnahme.
MIN_PUNKTE = 3
# Interaktionen, die "ich wollte das" bedeuten.
ZAEHLT = ("gemerkt", "alarm")


def _referenz(punkte: list[float]) -> float | None:
    """Was der Artikel ueblicherweise kostet."""
    if len(punkte) < MIN_PUNKTE:
        return None
    return float(median(punkte))


def berechne(db: Session, tage: int = 365) -> dict:
    seit = utcnow() - timedelta(days=tage)

    # Welche Deals habe ich angefasst?
    gewollt: dict[int, str] = {}
    for spur in db.scalars(select(Interaction).where(Interaction.ts >= seit,
                                                     Interaction.art.in_(ZAEHLT))):
        gewollt[spur.deal_id] = spur.art
    auch_gemerkt = list(db.scalars(select(Deal).where(Deal.bookmarked.is_(True),
                                                      Deal.first_seen >= seit)))
    for deal in auch_gemerkt:
        gewollt.setdefault(deal.id, "gemerkt")

    if not gewollt:
        return _leer(tage)

    deals = {d.id: d for d in db.scalars(select(Deal).where(Deal.id.in_(gewollt)))}

    verlauf: dict[int, list[float]] = defaultdict(list)
    for punkt in db.scalars(select(PriceHistory).where(
            PriceHistory.deal_id.in_(deals))):
        verlauf[punkt.deal_id].append(punkt.preis)

    ersparnis = 0.0
    gezaehlt = 0
    ohne_verlauf = 0
    gratis = 0
    beste: list[tuple[float, Deal]] = []

    for deal_id, deal in deals.items():
        preis = deal.preis_eur if deal.preis_eur is not None else deal.preis
        if deal.ist_gratis or (preis is not None and preis <= 0.009):
            gratis += 1
        if preis is None:
            continue
        referenz = _referenz(verlauf.get(deal_id, []))
        if referenz is None:
            ohne_verlauf += 1
            continue
        differenz = referenz - preis
        if differenz <= 0:
            gezaehlt += 1
            continue
        ersparnis += differenz
        gezaehlt += 1
        beste.append((differenz, deal))

    beste.sort(key=lambda paar: paar[0], reverse=True)

    from sqlalchemy import func

    claim_anzahl = db.scalar(
        select(func.count()).select_from(ClaimEvent)
        .where(ClaimEvent.seen_at >= seit, ClaimEvent.status == "claimed")) or 0

    return {
        "tage": tage,
        "ersparnis_eur": round(ersparnis, 2),
        "beobachtete_deals": len(deals),
        "mit_verlauf": gezaehlt,
        "ohne_verlauf": ohne_verlauf,
        "gratis_mitgenommen": gratis,
        "claims": claim_anzahl,
        "top": [{
            "id": deal.id,
            "titel": deal.titel,
            "url": deal.url,
            "haendler": deal.haendler,
            "preis": deal.preis_eur if deal.preis_eur is not None else deal.preis,
            "gespart": round(differenz, 2),
        } for differenz, deal in beste[:10]],
        # Damit die Zahl im UI eingeordnet werden kann statt als Wahrheit
        # dazustehen.
        "hinweis": ("Geschätzt gegen den beobachteten Referenzpreis (Median "
                    "des eigenen Verlaufs), nicht gegen die UVP. Gezählt wird "
                    "nur, was du gemerkt oder mit einem Alarm versehen hast."),
    }


def _leer(tage: int) -> dict:
    return {
        "tage": tage, "ersparnis_eur": 0.0, "beobachtete_deals": 0,
        "mit_verlauf": 0, "ohne_verlauf": 0, "gratis_mitgenommen": 0,
        "claims": 0, "hat_claims": False, "top": [],
        "hinweis": ("Noch nichts gemerkt - und ohne gemerkte Deals lässt sich "
                    "nicht sagen, was du gespart hast."),
    }
