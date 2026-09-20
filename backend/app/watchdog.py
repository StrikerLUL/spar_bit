"""Selbstueberwachung: melden, wenn SparBit selbst nichts mehr liefert.

Der gefaehrlichste Ausfall eines Waechters ist der stille. Faellt eine
Quelle aus, macht der Schutzschalter nach ein paar Fehlern zu - und von
aussen sieht das aus wie "heute keine Deals", nicht wie "ich bin kaputt".
Dasselbe bei Kanaelen: wird ein Bot-Token ungueltig, laeuft der
Fehlerzaehler hoch und niemand erfaehrt es.

Darum prueft dieses Modul regelmaessig sich selbst und meldet Befunde
ueber dieselben Kanaele wie Deals - aber entschieden gedrosselt. Ein
Waechter, der taeglich ueber sich selbst klagt, wird stummgeschaltet und
nuetzt dann gar nichts mehr:

  * je Problem hoechstens eine Meldung am Tag
  * Entwarnung genau einmal, wenn es sich erholt hat
  * waehrend der Ruhezeit wird nichts verschickt, sondern beim naechsten
    Lauf danach - die Pruefung laeuft ohnehin alle 15 Minuten
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_setting, set_setting
from .models import Channel, NotificationLog, SourceConfig, utcnow

log = logging.getLogger(__name__)

# Wie lange eine eingeschaltete Quelle schweigen darf, bevor es auffaellt.
# Grosszuegig: manche Quellen liefern nachts schlicht nichts Neues.
STILL_STUNDEN = 24
# So viele Fehlversuche in Folge, bevor ein Kanal als kaputt gilt.
KANAL_FEHLER = 3
# Abstand zwischen zwei Meldungen zum selben Problem.
WIEDERHOLUNG_STUNDEN = 24

SCHLUESSEL = "watchdog_gemeldet"


@dataclass
class Befund:
    """Ein Problem, das der Benutzer wissen sollte."""

    art: str                    # quelle_gesperrt | quelle_still | kanal_fehler
    betrifft: str               # Quellen-ID bzw. Kanalname
    text: str                   # was los ist, in einem Satz
    rat: str = ""               # was man dagegen tut
    seit: datetime | None = None

    @property
    def schluessel(self) -> str:
        return f"{self.art}:{self.betrifft}"


@dataclass
class Lage:
    probleme: list[Befund] = field(default_factory=list)
    entwarnungen: list[str] = field(default_factory=list)


# --- Pruefungen ------------------------------------------------------------

def _quellen(db: Session, jetzt: datetime) -> list[Befund]:
    raus: list[Befund] = []
    still_ab = jetzt - timedelta(hours=STILL_STUNDEN)

    for cfg in db.scalars(select(SourceConfig)):
        if not cfg.enabled:
            continue

        if cfg.circuit_open_until and cfg.circuit_open_until > jetzt:
            raus.append(Befund(
                art="quelle_gesperrt", betrifft=cfg.id,
                text=f"Quelle „{cfg.id}“ ist nach {cfg.consecutive_failures} "
                     f"Fehlversuchen gesperrt.",
                rat=(cfg.last_error or "").strip()[:200]
                    or "Unter Quellen „Jetzt testen“ drücken.",
                seit=cfg.circuit_open_until))
            continue

        # Nie erfolgreich gewesen ist etwas anderes als "liefert nicht mehr":
        # eine frisch eingeschaltete Quelle hatte noch keine Gelegenheit.
        if cfg.last_success is None:
            if cfg.total_runs >= 3 and cfg.total_errors >= cfg.total_runs:
                raus.append(Befund(
                    art="quelle_still", betrifft=cfg.id,
                    text=f"Quelle „{cfg.id}“ hat noch nie etwas geliefert.",
                    rat=(cfg.last_error or "").strip()[:200]
                        or "Unter Quellen „Jetzt testen“ drücken."))
            continue

        if cfg.last_success < still_ab:
            stunden = int((jetzt - cfg.last_success).total_seconds() // 3600)
            raus.append(Befund(
                art="quelle_still", betrifft=cfg.id,
                text=f"Quelle „{cfg.id}“ liefert seit {stunden} Stunden nichts mehr.",
                rat=(cfg.last_error or "").strip()[:200]
                    or "Endpoint prüfen: Quellen → Jetzt testen.",
                seit=cfg.last_success))

    return raus


def _kanaele(db: Session) -> list[Befund]:
    """Kanaele, deren letzte Zustellversuche alle fehlgeschlagen sind.

    Der reine Fehlerzaehler taugt nicht: er wird nie zurueckgesetzt, ein
    Kanal mit einem Ausrutscher vor Monaten stuende sonst ewig auf Rot.
    """
    raus: list[Befund] = []

    for kanal in db.scalars(select(Channel)):
        if not kanal.enabled:
            continue
        letzte = list(db.scalars(
            select(NotificationLog)
            .where(NotificationLog.channel_id == kanal.id)
            .order_by(NotificationLog.created_at.desc())
            .limit(KANAL_FEHLER)))
        if len(letzte) < KANAL_FEHLER or any(e.ok for e in letzte):
            continue
        grund = (letzte[0].error or "").strip()[:200]
        raus.append(Befund(
            art="kanal_fehler", betrifft=kanal.name,
            text=f"Kanal „{kanal.name}“ ({kanal.type}) hat die letzten "
                 f"{KANAL_FEHLER} Zustellungen nicht geschafft.",
            rat=grund or "Unter Benachrichtigungen „Test senden“ drücken.",
            seit=letzte[0].created_at))

    return raus


def pruefe(db: Session, jetzt: datetime | None = None) -> list[Befund]:
    """Alle Pruefungen - ohne Nebenwirkung, auch fuer das UI."""
    jetzt = jetzt or utcnow()
    return _quellen(db, jetzt) + _kanaele(db)


# --- Was davon ist meldenswert? -------------------------------------------

def _gemeldet(db: Session) -> dict:
    roh = get_setting(db, SCHLUESSEL) or {}
    return roh if isinstance(roh, dict) else {}


def faellig(db: Session, befunde: list[Befund],
            jetzt: datetime | None = None) -> Lage:
    """Neue Probleme und behobene Alte - der Rest bleibt still.

    Aendert nichts; erst melde() schreibt den Stand fort. So kann das UI
    dieselbe Funktion benutzen, ohne die Drosselung zu verbrauchen.
    """
    jetzt = jetzt or utcnow()
    bekannt = _gemeldet(db)
    offen = {b.schluessel: b for b in befunde}

    frisch = utcnow() - timedelta(hours=WIEDERHOLUNG_STUNDEN)
    zu_melden = []
    for schluessel, befund in offen.items():
        zuletzt = bekannt.get(schluessel)
        if zuletzt:
            try:
                if datetime.fromisoformat(zuletzt) > frisch:
                    continue
            except (TypeError, ValueError):
                pass
        zu_melden.append(befund)

    entwarnt = [s for s in bekannt if s not in offen]
    return Lage(probleme=zu_melden, entwarnungen=entwarnt)


def merke(db: Session, lage: Lage, jetzt: datetime | None = None) -> None:
    """Den Meldestand fortschreiben - nach erfolgreichem Versand."""
    jetzt = (jetzt or utcnow()).isoformat()
    bekannt = _gemeldet(db)
    for befund in lage.probleme:
        bekannt[befund.schluessel] = jetzt
    for schluessel in lage.entwarnungen:
        bekannt.pop(schluessel, None)
    set_setting(db, SCHLUESSEL, bekannt)
    db.commit()


def text_fuer_entwarnung(schluessel: str) -> str:
    art, _, betrifft = schluessel.partition(":")
    if art == "kanal_fehler":
        return f"Kanal „{betrifft}“ stellt wieder zu."
    return f"Quelle „{betrifft}“ läuft wieder."
