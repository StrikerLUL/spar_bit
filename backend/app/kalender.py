"""Was endet, gehoert in den Kalender - nicht in eine Liste.

Ein Gratis-Spiel mit Frist ist ein Termin. Bisher stand es in einer
Liste, die man aufmachen muss, um zu sehen, dass man etwas verpasst
hat. Ein Kalender sagt es von sich aus - auf dem Handy, im Sperrbild-
schirm, ohne dass SparBit ueberhaupt offen ist.

Ausgegeben wird iCalendar (RFC 5545), das jeder Kalender abonnieren
kann. Zwei Termine je Deal: das Ende selbst, und eine Erinnerung
vorher - bei etwas, das nichts kostet, ist der Hinweis "laeuft heute
aus" mehr wert als der Eintrag "ist abgelaufen".
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Deal, Match, utcnow

log = logging.getLogger(__name__)

# Wie weit voraus der Kalender blickt. Weiter waere Ballast: was in drei
# Monaten endet, interessiert heute niemanden.
VORSCHAU_TAGE = 60
# Wie lange abgelaufene Termine stehen bleiben, damit man noch sieht,
# was man verpasst hat.
RUECKSCHAU_TAGE = 3


def _escape(text: str) -> str:
    """iCalendar-Feldwerte: Komma, Semikolon, Backslash und Zeilenumbruch."""
    return (str(text or "")
            .replace("\\", "\\\\").replace(";", r"\;")
            .replace(",", r"\,").replace("\n", r"\n").replace("\r", ""))


def _falten(zeile: str) -> str:
    """Zeilen ueber 75 Oktetts umbrechen - so will es RFC 5545.

    Ohne das verwerfen manche Kalender den ganzen Eintrag, statt nur die
    lange Zeile zu kuerzen.
    """
    roh = zeile.encode("utf-8")
    if len(roh) <= 75:
        return zeile
    teile, rest = [], roh
    teile.append(rest[:73])
    rest = rest[73:]
    while rest:
        teile.append(b" " + rest[:72])
        rest = rest[72:]
    return "\r\n".join(t.decode("utf-8", "ignore") for t in teile)


def _zeit(wert: datetime) -> str:
    return wert.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _termin(deal: Deal, jetzt: datetime) -> list[str]:
    ende = deal.laeuft_ab
    beginn = ende - timedelta(minutes=30)
    kennung = hashlib.sha256(f"sparbit-deal-{deal.id}".encode()).hexdigest()[:32]

    was = "Gratis" if deal.ist_gratis else "Angebot"
    titel = f"{was} endet: {deal.titel[:120]}"

    beschreibung = [deal.url or ""]
    if deal.preis is not None and not deal.ist_gratis:
        beschreibung.append(f"{deal.preis:.2f} {deal.waehrung}")
    if deal.haendler:
        beschreibung.append(f"bei {deal.haendler}")
    if deal.urteil_text:
        beschreibung.append(deal.urteil_text)

    zeilen = [
        "BEGIN:VEVENT",
        f"UID:{kennung}@sparbit",
        f"DTSTAMP:{_zeit(jetzt)}",
        f"DTSTART:{_zeit(beginn)}",
        f"DTEND:{_zeit(ende)}",
        f"SUMMARY:{_escape(titel)}",
        f"DESCRIPTION:{_escape(' - '.join(b for b in beschreibung if b))}",
        f"URL:{_escape(deal.url)}",
        "TRANSP:TRANSPARENT",
        # Erinnerung sechs Stunden vorher: frueh genug, um noch zu
        # reagieren, spaet genug, um nicht vergessen zu werden.
        "BEGIN:VALARM",
        "TRIGGER:-PT6H",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_escape(titel)}",
        "END:VALARM",
        "END:VEVENT",
    ]
    return zeilen


def auswahl(db: Session, nur_gratis: bool = False) -> list[Deal]:
    """Welche Deals in den Kalender gehoeren.

    Nicht alles mit Datum: nur, was mit mir zu tun hat - gemerkt, von
    einer Regel getroffen oder gratis. Sonst waere der Kalender nach
    einer Woche unbenutzbar.
    """
    jetzt = utcnow()
    bedingungen = [
        Deal.laeuft_ab.is_not(None),
        Deal.laeuft_ab > jetzt - timedelta(days=RUECKSCHAU_TAGE),
        Deal.laeuft_ab < jetzt + timedelta(days=VORSCHAU_TAGE),
        Deal.duplicate_of.is_(None),
        Deal.erwachsen.is_(False),
    ]
    if nur_gratis:
        bedingungen.append(Deal.ist_gratis.is_(True))

    stmt = (select(Deal).where(*bedingungen)
            .where(or_(Deal.bookmarked.is_(True), Deal.ist_gratis.is_(True),
                       Deal.id.in_(select(Match.deal_id))))
            .order_by(Deal.laeuft_ab.asc()).limit(200))
    return list(db.scalars(stmt))


def feed(db: Session, nur_gratis: bool = False) -> str:
    jetzt = datetime.now(UTC)
    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SparBit//Deal-Fristen//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SparBit",
        "X-WR-CALDESC:Angebote und Gratis-Sachen mit Frist",
        # Wie oft der Kalender nachsehen soll. Ohne die Angabe fragen
        # manche Clients einmal am Tag - zu selten fuer ein Angebot,
        # das heute Abend endet.
        "REFRESH-INTERVAL;VALUE=DURATION:PT2H",
        "X-PUBLISHED-TTL:PT2H",
    ]
    for deal in auswahl(db, nur_gratis):
        zeilen.extend(_termin(deal, jetzt))
    zeilen.append("END:VCALENDAR")
    return "\r\n".join(_falten(z) for z in zeilen) + "\r\n"
