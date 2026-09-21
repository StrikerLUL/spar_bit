"""Schutz gegen das Durchprobieren von Passwoertern.

argon2 ist absichtlich langsam, aber ohne Bremse kann jemand trotzdem
beliebig oft raten - besonders wenn SparBit mit --host 0.0.0.0 im WLAN steht.

Regel:
  bis 4 Fehlversuche   keine Verzoegerung
  ab 5 Fehlversuchen   wachsende Wartezeit (2s, 4s, 8s ... max 60s)
  ab 10 Fehlversuchen  15 Minuten gesperrt

Gezaehlt wird je Absender-IP innerhalb eines gleitenden Fensters. Die
Versuche liegen in der Datenbank, nicht im Speicher: ein Neustart darf die
Sperre nicht aufheben, sonst waere sie wertlos.
"""
from __future__ import annotations

import logging
from datetime import UTC, timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import LoginAttempt, utcnow

log = logging.getLogger(__name__)

FENSTER_MINUTEN = 15        # so weit zurueck wird gezaehlt
SANFT_AB = 5                # ab hier Wartezeit
SPERRE_AB = 10              # ab hier komplett dicht
SPERRE_MINUTEN = 15
MAX_WARTEN = 60.0


class LoginGesperrt(Exception):
    """Zu viele Fehlversuche. `sekunden` sagt, wie lange noch."""

    def __init__(self, sekunden: float, versuche: int):
        super().__init__(f"Gesperrt fuer {sekunden:.0f}s nach {versuche} Fehlversuchen")
        self.sekunden = max(1.0, sekunden)
        self.versuche = versuche


def client_ip(request: Request) -> str:
    """Absender-IP, hinter einem Reverse-Proxy aus X-Forwarded-For.

    Der erste Eintrag ist der urspruengliche Client. Das ist faelschbar, wenn
    SparBit ohne Proxy direkt im Netz steht - dann ist aber auch die
    Verbindungs-IP echt, weil kein Header gesetzt wird.
    """
    weiter = request.headers.get("x-forwarded-for")
    if weiter:
        erste = weiter.split(",")[0].strip()
        if erste:
            return erste[:64]
    return (request.client.host if request.client else "unbekannt")[:64]


def _zaehle(db: Session, ip: str) -> tuple[int, object | None]:
    """Fehlversuche im Fenster und der Zeitpunkt des letzten."""
    seit = utcnow() - timedelta(minutes=FENSTER_MINUTEN)
    anzahl = db.scalar(
        select(func.count()).select_from(LoginAttempt)
        .where(LoginAttempt.ip == ip, LoginAttempt.ts >= seit)) or 0
    letzter = db.scalar(
        select(func.max(LoginAttempt.ts))
        .where(LoginAttempt.ip == ip, LoginAttempt.ts >= seit))
    return anzahl, letzter


def wartezeit(versuche: int) -> float:
    """Wie lange muss nach so vielen Fehlversuchen gewartet werden."""
    if versuche < SANFT_AB:
        return 0.0
    if versuche >= SPERRE_AB:
        return SPERRE_MINUTEN * 60.0
    return min(MAX_WARTEN, 2.0 ** (versuche - SANFT_AB + 1))


def pruefen(db: Session, ip: str) -> None:
    """Vor dem Passwortvergleich aufrufen. Wirft LoginGesperrt."""
    versuche, letzter = _zaehle(db, ip)
    noetig = wartezeit(versuche)
    if noetig <= 0 or letzter is None:
        return

    if letzter.tzinfo is None:
        letzter = letzter.replace(tzinfo=UTC)

    vergangen = (utcnow() - letzter).total_seconds()
    if vergangen < noetig:
        raise LoginGesperrt(noetig - vergangen, versuche)


def fehlversuch(db: Session, ip: str, benutzername: str | None) -> int:
    """Fehlversuch vermerken. Gibt die neue Anzahl im Fenster zurueck."""
    db.add(LoginAttempt(ip=ip, benutzername=(benutzername or "")[:64]))
    db.commit()
    versuche, _ = _zaehle(db, ip)
    log.warning("Fehlgeschlagene Anmeldung von %s als '%s' (%d im Fenster)",
                ip, benutzername, versuche,
                extra={"ip": ip})
    return versuche


def zuruecksetzen(db: Session, ip: str) -> None:
    """Nach erfolgreicher Anmeldung die Zaehler dieser IP leeren."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.ip == ip))
    db.commit()


def aufraeumen(db: Session) -> int:
    """Alte Eintraege wegwerfen - laeuft im Aufraeum-Job mit."""
    alt = utcnow() - timedelta(hours=24)
    ergebnis = db.execute(delete(LoginAttempt).where(LoginAttempt.ts < alt))
    return ergebnis.rowcount or 0
