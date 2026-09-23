"""Bausteine, die Aufnahme und Versand beide brauchen.

Sie stehen hier und nicht in einem der beiden Module, damit keines vom
anderen importieren muss - sonst haette der Split nur die Schleife
verlagert, die er aufloesen sollte.
"""
from __future__ import annotations

import logging

from ..models import Deal
from ..notify import Notification

log = logging.getLogger(__name__)


def _deal_payload(deal: Deal) -> dict:
    return {
        "id": deal.id, "titel": deal.titel, "url": deal.url, "bild": deal.bild,
        "preis": deal.preis, "originalpreis": deal.originalpreis,
        "rabatt_prozent": deal.rabatt_prozent, "waehrung": deal.waehrung,
        "preis_eur": deal.preis_eur,
        "ist_gratis": deal.ist_gratis, "haendler": deal.haendler,
        "quelle": deal.quelle, "temperatur": deal.temperatur,
        "fehler_stufe": deal.fehler_stufe, "fehler_score": deal.fehler_score,
        "first_seen": deal.first_seen.isoformat() if deal.first_seen else None,
    }


def _note(deal: Deal, *, regel: str, prioritaet: str = "NORMAL",
          titel: str | None = None, beschreibung: str | None = None) -> Notification:
    """Eine Meldung aus einem Deal bauen.

    An einer Stelle, weil es drei Absender gibt (Regeltreffer, Preisalarm,
    Preisfehler-Waechter) und eine Meldung ueberall dieselben Zahlen zeigen
    soll. Frueher stand der Aufbau dreimal im Code, mit drei verschiedenen
    Feldlisten - eine davon vergass den EUR-Gegenwert.
    """
    fehler = (deal.fehler_gruende or [])
    return Notification(
        titel=titel or deal.titel,
        url=deal.url, quelle=deal.quelle, regel=regel,
        preis=deal.preis, originalpreis=deal.originalpreis,
        rabatt_prozent=deal.rabatt_prozent, waehrung=deal.waehrung,
        preis_eur=deal.preis_eur,
        haendler=deal.haendler, bild=deal.bild, ist_gratis=deal.ist_gratis,
        beschreibung=beschreibung if beschreibung is not None else deal.beschreibung,
        deal_id=deal.id, prioritaet=prioritaet, tags=deal.tags or [],
        urteil=deal.urteil, urteil_text=deal.urteil_text,
        fehler_stufe=deal.fehler_stufe,
        fehler_text=" ".join(fehler[:2]) if fehler else None,
        gutschein_code=deal.gutschein_code,
    )


