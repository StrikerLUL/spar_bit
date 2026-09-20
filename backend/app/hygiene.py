"""Regel-Hygiene: was man eingerichtet und nie wieder angesehen hat.

Regeln werden einmal gebaut und dann vergessen. Die eine liefert 400
Treffer im Monat, von denen man zwei angesehen hat - die schult einen
darauf, Meldungen wegzuwischen. Die andere hat seit acht Wochen nie
getroffen, weil ein Tippfehler im Stichwort steht.

Beides steht in den Daten, die ohnehin anfallen: Match zaehlt die Treffer,
Interaction verraet, was davon angesehen wurde. Hier wird daraus ein Satz
gemacht, den man lesen und entscheiden kann.

Vorgeschlagen wird, nie ausgefuehrt: eine Regel abzuschalten, die jemand
absichtlich weit gefasst hat, waere schlimmer als der Hinweis nuetzt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Deal, Interaction, Match, Rule, SourceConfig, utcnow

log = logging.getLogger(__name__)

# Beobachtungsfenster. Kuerzer waere zu zufaellig, laenger zu traege.
FENSTER_TAGE = 30
# Ab so vielen Treffern lohnt sich das Urteil "zu viel Rauschen".
LAUT_AB = 40
# Unter diesem Anteil angesehener Treffer gilt eine Regel als Rauschen.
BEACHTUNG_MIN = 0.10
# So lange darf eine Regel leerlaufen, bevor es auffaellt.
LEER_TAGE = 45
# Ab so vielen Funden laesst sich ueber eine Quelle etwas sagen.
QUELLE_MIN_FUNDE = 50
# Unter diesem Signalanteil liefert eine Quelle vor allem Fuellmaterial.
SIGNAL_MIN = 0.02

# Die Interaktionen, die "ich habe hingesehen" bedeuten. Blosses Anzeigen
# im Feed zaehlt nicht - danach koennte man jede Regel gutrechnen.
BEACHTET = ("geoeffnet", "geklickt", "gemerkt", "alarm")


@dataclass
class Befund:
    """Ein Hinweis samt konkretem Vorschlag."""

    art: str                     # regel_laut | regel_leer | regel_ohne_kanal
                                 # | quelle_rauschen
    betrifft: str                # Name der Regel bzw. Quelle
    regel_id: int | None = None
    quelle_id: str | None = None
    text: str = ""
    vorschlag: str = ""
    # Was der Knopf tut: {"feld": "enabled", "wert": False} o.ae.
    aktion: dict = field(default_factory=dict)
    zahlen: dict = field(default_factory=dict)


def _beachtet_je_regel(db: Session, seit) -> dict[int, int]:
    """Wie viele Treffer je Regel haben zu einer Reaktion gefuehrt."""
    rows = db.execute(
        select(Match.rule_id, func.count(func.distinct(Match.deal_id)))
        .join(Interaction, Interaction.deal_id == Match.deal_id)
        .where(Match.created_at >= seit, Interaction.art.in_(BEACHTET))
        .group_by(Match.rule_id)
    ).all()
    return {rule_id: anzahl for rule_id, anzahl in rows}


def _treffer_je_regel(db: Session, seit) -> dict[int, int]:
    rows = db.execute(
        select(Match.rule_id, func.count(Match.id))
        .where(Match.created_at >= seit)
        .group_by(Match.rule_id)
    ).all()
    return {rule_id: anzahl for rule_id, anzahl in rows}


def pruefe_regeln(db: Session) -> list[Befund]:
    seit = utcnow() - timedelta(days=FENSTER_TAGE)
    treffer = _treffer_je_regel(db, seit)
    beachtet = _beachtet_je_regel(db, seit)
    raus: list[Befund] = []

    for regel in db.scalars(select(Rule)):
        anzahl = treffer.get(regel.id, 0)
        gesehen = beachtet.get(regel.id, 0)

        # 1. Viel Lärm, wenig Beachtung.
        if anzahl >= LAUT_AB:
            anteil = gesehen / anzahl
            if anteil < BEACHTUNG_MIN:
                raus.append(Befund(
                    art="regel_laut", betrifft=regel.name, regel_id=regel.id,
                    text=(f"„{regel.name}“ hat in {FENSTER_TAGE} Tagen "
                          f"{anzahl} Treffer erzeugt — angesehen hast du "
                          f"{gesehen}."),
                    vorschlag=("Enger fassen: ein Pflichtwort ergänzen, den "
                               "Höchstpreis senken oder ein Preisurteil "
                               "verlangen."),
                    aktion={"art": "oeffnen"},
                    zahlen={"treffer": anzahl, "beachtet": gesehen,
                            "anteil": round(anteil * 100)}))
                continue

        # 2. Läuft leer.
        if regel.enabled:
            nie = regel.last_match is None
            alt = (regel.last_match is not None
                   and regel.last_match < utcnow() - timedelta(days=LEER_TAGE))
            jung = regel.created_at > utcnow() - timedelta(days=LEER_TAGE)
            # Eine frisch gebaute Regel hatte noch keine Gelegenheit.
            if (nie or alt) and not jung:
                wann = ("noch nie" if nie
                        else f"seit {(utcnow() - regel.last_match).days} Tagen nicht")
                raus.append(Befund(
                    art="regel_leer", betrifft=regel.name, regel_id=regel.id,
                    text=f"„{regel.name}“ hat {wann} getroffen.",
                    vorschlag=("Stichwörter prüfen — oft ist es ein Tippfehler "
                               "oder eine zu enge Preisgrenze."),
                    aktion={"art": "oeffnen"},
                    zahlen={"treffer": anzahl}))
                continue

        # 3. Ohne Kanal stellt sie nichts zu.
        if regel.enabled and not (regel.channels or []):
            raus.append(Befund(
                art="regel_ohne_kanal", betrifft=regel.name, regel_id=regel.id,
                text=f"„{regel.name}“ hat keinen Kanal — Treffer landen nur im Feed.",
                vorschlag="Einen Kanal zuordnen, sonst erfährst du nichts davon.",
                aktion={"art": "oeffnen"},
                zahlen={"treffer": anzahl}))

    return raus


def pruefe_quellen(db: Session) -> list[Befund]:
    """Quellen, die viel liefern und selten eine Regel treffen."""
    seit = utcnow() - timedelta(days=FENSTER_TAGE)
    raus: list[Befund] = []

    funde = dict(db.execute(
        select(Deal.quelle, func.count(Deal.id))
        .where(Deal.first_seen >= seit).group_by(Deal.quelle)).all())
    treffer = dict(db.execute(
        select(Deal.quelle, func.count(func.distinct(Match.deal_id)))
        .join(Match, Match.deal_id == Deal.id)
        .where(Deal.first_seen >= seit).group_by(Deal.quelle)).all())

    aktiv = {c.id for c in db.scalars(select(SourceConfig)) if c.enabled}

    for quelle, anzahl in funde.items():
        if quelle not in aktiv or anzahl < QUELLE_MIN_FUNDE:
            continue
        mit_treffer = treffer.get(quelle, 0)
        anteil = mit_treffer / anzahl
        if anteil >= SIGNAL_MIN:
            continue
        raus.append(Befund(
            art="quelle_rauschen", betrifft=quelle, quelle_id=quelle,
            text=(f"„{quelle}“ lieferte {anzahl} Funde, davon trafen "
                  f"{mit_treffer} eine Regel."),
            vorschlag=("Entweder eine passende Regel bauen oder die Quelle "
                       "abschalten — so kostet sie nur Anfragen."),
            aktion={"art": "quelle_aus", "quelle": quelle},
            zahlen={"funde": anzahl, "treffer": mit_treffer,
                    "anteil": round(anteil * 100, 1)}))

    return raus


def pruefe(db: Session) -> list[Befund]:
    return pruefe_regeln(db) + pruefe_quellen(db)


def als_dict(befunde: list[Befund]) -> list[dict]:
    return [{
        "art": b.art, "betrifft": b.betrifft, "regel_id": b.regel_id,
        "quelle_id": b.quelle_id, "text": b.text, "vorschlag": b.vorschlag,
        "aktion": b.aktion, "zahlen": b.zahlen,
    } for b in befunde]
