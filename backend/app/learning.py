"""Lernender Feed: was interessiert mich wirklich?

SparBit weiss bereits, was ich mir gemerkt, geoeffnet oder mit einem Alarm
versehen habe - und was monatelang unbeachtet vorbeigezogen ist. Daraus laesst
sich lernen, ohne dass Daten das Haus verlassen: ein Naive-Bayes-Klassifikator
ueber Merkmale wie Titelwoerter, Haendler, Quelle und Preisklasse.

Bewusst kein neuronales Netz und kein externer Dienst. Das Modell muss
erklaerbar bleiben - "warum schlaegst du mir das vor" ist bei einem
Empfehlungssystem die wichtigste Frage, und Naive Bayes kann sie beantworten.

Und es haelt den Mund, solange es zu wenig gesehen hat. Ein Vorschlag aus
drei Beispielen waere geraten, nicht gelernt.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Deal, Interaction, utcnow

log = logging.getLogger(__name__)

# Wie viele positive Beispiele es braucht, bevor ueberhaupt geurteilt wird.
MIN_POSITIV = 12
MIN_NEGATIV = 12
# Interaktionen, die als "gefaellt mir" zaehlen, mit ihrem Gewicht.
POSITIV = {"gemerkt": 3.0, "alarm": 3.0, "geklickt": 1.5, "geoeffnet": 1.0}
NEGATIV = {"verworfen": 2.0}

_WORT = re.compile(r"[a-zäöüß0-9]{3,}", re.IGNORECASE)
_STOPP = {
    "der", "die", "das", "und", "oder", "für", "fuer", "mit", "von", "bei",
    "auf", "aus", "des", "dem", "den", "ein", "eine", "einer", "eines", "im",
    "in", "zu", "zum", "zur", "ist", "sind", "the", "and", "for", "with",
    "you", "your", "off", "deal", "deals", "neu", "jetzt", "nur", "statt",
    "gratis", "kostenlos", "sale", "prozent", "euro",
}


def merkmale(deal) -> list[str]:
    """Ein Deal als Liste von Merkmalen.

    Praefixe halten die Raeume getrennt - "amazon" als Haendler ist etwas
    anderes als "amazon" im Titel.
    """
    raus: list[str] = []
    for wort in _WORT.findall((deal.titel or "").lower()):
        if wort not in _STOPP and not wort.isdigit():
            raus.append(f"w:{wort}")

    if getattr(deal, "haendler", None):
        raus.append(f"h:{str(deal.haendler).lower().strip()[:40]}")
    if getattr(deal, "quelle", None):
        raus.append(f"q:{deal.quelle}")
    if getattr(deal, "kategorie", None):
        raus.append(f"k:{deal.kategorie}")

    preis = getattr(deal, "preis_eur", None) or getattr(deal, "preis", None)
    if getattr(deal, "ist_gratis", False):
        raus.append("p:gratis")
    elif preis is not None:
        for grenze, name in ((5, "0-5"), (20, "5-20"), (50, "20-50"),
                             (150, "50-150"), (500, "150-500")):
            if preis < grenze:
                raus.append(f"p:{name}")
                break
        else:
            raus.append("p:500+")

    rabatt = getattr(deal, "rabatt_prozent", None)
    if rabatt is not None:
        raus.append("r:hoch" if rabatt >= 60 else "r:mittel" if rabatt >= 30
                    else "r:niedrig")

    return list(dict.fromkeys(raus))


@dataclass
class Modell:
    """Naive Bayes mit Laplace-Glaettung."""

    positiv: Counter = field(default_factory=Counter)
    negativ: Counter = field(default_factory=Counter)
    n_positiv: float = 0.0
    n_negativ: float = 0.0
    trainiert: bool = False

    @property
    def bereit(self) -> bool:
        return self.trainiert and self.n_positiv >= MIN_POSITIV \
            and self.n_negativ >= MIN_NEGATIV

    def lerne(self, deal, gewicht: float, mag_ich: bool) -> None:
        ziel = self.positiv if mag_ich else self.negativ
        for merkmal in merkmale(deal):
            ziel[merkmal] += gewicht
        if mag_ich:
            self.n_positiv += gewicht
        else:
            self.n_negativ += gewicht

    def _log_verhaeltnis(self, merkmal: str) -> float:
        """Wie stark spricht dieses Merkmal fuer 'gefaellt mir'?"""
        vokabular = len(set(self.positiv) | set(self.negativ)) or 1
        p = (self.positiv[merkmal] + 1.0) / (self.n_positiv + vokabular)
        n = (self.negativ[merkmal] + 1.0) / (self.n_negativ + vokabular)
        return math.log(p / n)

    def punkte(self, deal) -> float:
        """Wert zwischen 0 und 1. 0,5 heisst 'keine Meinung'."""
        if not self.bereit:
            return 0.5
        summe = sum(self._log_verhaeltnis(m) for m in merkmale(deal))
        return 1.0 / (1.0 + math.exp(-summe / 3.0))      # gedaempft

    def gruende(self, deal, anzahl: int = 3) -> list[str]:
        """Die Merkmale, die am staerksten fuer den Deal sprechen.
        Ohne das waere die Empfehlung eine Blackbox."""
        if not self.bereit:
            return []
        gewichtet = [(m, self._log_verhaeltnis(m)) for m in merkmale(deal)]
        gewichtet.sort(key=lambda paar: paar[1], reverse=True)
        return [_lesbar(m) for m, wert in gewichtet[:anzahl] if wert > 0.15]


def _lesbar(merkmal: str) -> str:
    art, _, wert = merkmal.partition(":")
    return {
        "w": f"„{wert}“", "h": f"Händler {wert}", "q": f"Quelle {wert}",
        "k": f"Kategorie {wert}", "p": f"Preisklasse {wert} €",
        "r": f"{wert}er Rabatt",
    }.get(art, wert)


def _nur(stmt, benutzer_id: int | None):
    """Auf die Spuren eines Benutzers einschraenken.

    Ohne das lernt der Feed aus dem Verhalten aller zusammen - und
    schlaegt dem einen vor, was der andere gemerkt hat. Zwei Geschmaecker
    in einem Modell ergeben keinen Durchschnitt, sondern Rauschen.
    NULL zaehlt mit: so sehen Spuren aus der Zeit vor den Konten aus.
    """
    if benutzer_id is None:
        return stmt
    from sqlalchemy import or_
    return stmt.where(or_(Interaction.benutzer_id == benutzer_id,
                          Interaction.benutzer_id.is_(None)))


def trainiere(db: Session, tage: int = 120, benutzer_id: int | None = None) -> Modell:
    """Modell aus den aufgezeichneten Interaktionen bauen.

    Als negative Beispiele dienen Deals, die im selben Zeitraum durch den
    Feed liefen, aber nie eine Reaktion ausgeloest haben.
    """
    modell = Modell()
    seit = utcnow() - timedelta(days=tage)

    gewichte: dict[int, float] = defaultdict(float)
    verworfen: set[int] = set()
    for eintrag in db.scalars(
            _nur(select(Interaction).where(Interaction.ts >= seit), benutzer_id)):
        if eintrag.art in NEGATIV:
            verworfen.add(eintrag.deal_id)
        elif eintrag.art in POSITIV:
            gewichte[eintrag.deal_id] = max(gewichte[eintrag.deal_id],
                                            POSITIV[eintrag.art])

    beruehrt = set(gewichte) | verworfen
    if not beruehrt:
        return modell

    # 18+ bleibt aus dem Modell heraus: es sortiert den normalen Feed, und
    # ein dort gemerkter Fund wuerde dessen Reihenfolge mitbestimmen.
    for deal in db.scalars(select(Deal).where(Deal.id.in_(beruehrt),
                                              Deal.erwachsen.is_(False))):
        if deal.id in verworfen:
            modell.lerne(deal, NEGATIV["verworfen"], mag_ich=False)
        else:
            modell.lerne(deal, gewichte[deal.id], mag_ich=True)

    # Unberuehrte Deals als Gegenbeispiele - ohne sie kennt das Modell nur,
    # was mir gefaellt, und findet alles gut.
    fehlend = max(0, int(MIN_NEGATIV * 3 - modell.n_negativ))
    if fehlend:
        ungesehen = db.scalars(
            select(Deal).where(Deal.first_seen >= seit,
                               Deal.erwachsen.is_(False),
                               Deal.id.notin_(beruehrt or {0}))
            .order_by(Deal.first_seen.desc()).limit(fehlend * 3))
        for deal in list(ungesehen)[:fehlend]:
            modell.lerne(deal, 1.0, mag_ich=False)

    modell.trainiert = True
    return modell


# --- Regelvorschlaege ------------------------------------------------------

@dataclass
class Vorschlag:
    titel: str
    begruendung: str
    regel: dict
    treffer: int


def vorschlaege(db: Session, tage: int = 120, limit: int = 4,
                benutzer_id: int | None = None) -> list[Vorschlag]:
    """Aus dem Verhalten Regeln ableiten, die man anlegen koennte.

    Vorgeschlagen wird nur, was oft genug vorkam - eine Regel aus zwei
    Beobachtungen waere geraten.
    """
    seit = utcnow() - timedelta(days=tage)
    gemocht = [eintrag.deal_id for eintrag in db.scalars(
        _nur(select(Interaction).where(Interaction.ts >= seit,
                                       Interaction.art.in_(("gemerkt", "alarm"))),
             benutzer_id))]
    if len(set(gemocht)) < MIN_POSITIV:
        return []

    deals = list(db.scalars(select(Deal).where(Deal.id.in_(set(gemocht)),
                                                Deal.erwachsen.is_(False))))
    gesamt = len(deals)
    if not gesamt:
        return []

    zaehler: Counter = Counter()
    for deal in deals:
        zaehler.update(merkmale(deal))

    preise = sorted(d.preis_eur or d.preis for d in deals
                    if (d.preis_eur or d.preis) is not None)

    raus: list[Vorschlag] = []
    for merkmal, anzahl in zaehler.most_common(40):
        anteil = anzahl / gesamt
        # Mindestens ein Drittel der gemerkten Deals und mindestens vier Stueck.
        if anteil < 0.34 or anzahl < 4:
            continue
        art, _, wert = merkmal.partition(":")

        if art == "w":
            regel = {"keywords": [wert]}
            titel = f"Alles zu „{wert}“"
        elif art == "h":
            regel = {"haendler": [wert]}
            titel = f"Nur bei {wert}"
        elif art == "p" and wert == "gratis":
            regel = {"nur_gratis": True}
            titel = "Alles Gratis"
        elif art == "r" and wert == "hoch":
            regel = {"min_rabatt_prozent": 60}
            titel = "Nur starke Rabatte"
        else:
            continue

        # Preisgrenze aus dem eigenen Verhalten: der 80-%-Punkt.
        if preise and art == "w":
            grenze = preise[min(len(preise) - 1, int(len(preise) * 0.8))]
            regel["max_preis"] = round(grenze * 1.1, 2)

        raus.append(Vorschlag(
            titel=titel,
            begruendung=(f"{anzahl} von {gesamt} gemerkten Deals "
                         f"({anteil * 100:.0f} %) passen dazu."),
            regel=regel, treffer=anzahl))
        if len(raus) >= limit:
            break
    return raus


def notiere(db: Session, deal_id: int, art: str,
            benutzer_id: int | None = None) -> None:
    """Eine Interaktion festhalten. Doppelte am selben Tag werden gespart."""
    if art not in POSITIV and art not in NEGATIV:
        return
    heute = utcnow() - timedelta(hours=12)
    schon_da = db.scalar(
        _nur(select(Interaction).where(Interaction.deal_id == deal_id,
                                       Interaction.art == art,
                                       Interaction.ts >= heute), benutzer_id))
    if schon_da:
        return
    db.add(Interaction(deal_id=deal_id, art=art, benutzer_id=benutzer_id))
    db.commit()
