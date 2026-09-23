"""Warum kam *dieser* Deal nicht an?

Der Regel-Editor beantwortet die Frage in die eine Richtung: zu einer
Regel zeigt er, welche der letzten 500 Deals sie getroffen haetten. Die
Gegenrichtung fehlte - und das ist die, die man abends stellt, wenn ein
Fund im Feed steht, aber nicht auf dem Handy war.

Bisher hiess die Antwort darauf: Regeln durchlesen, Ruhezeit nachsehen,
Kanaele pruefen, im Versandverlauf suchen. Vier Orte, und am Ende weiss
man immer noch nicht, ob die Regel nicht traf oder der Kanal nicht
zustellte.

Hier laeuft derselbe Weg, den die Zustellung nimmt, noch einmal ab -
Stufe fuer Stufe, mit demselben Code, der auch wirklich entscheidet
(`filters.evaluate`, `regeln.in_quiet_hours`). Jede Stufe sagt, ob sie
durchlaesst, und wenn nicht: warum, und was dagegen zu tun waere.

Ausdruecklich keine zweite Wahrheit: wo es geht, wird nicht
nachgebildet, sondern aufgerufen. Eine Diagnose, die anders rechnet als
die Zustellung, ist schlimmer als keine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import erwachsen as erwachsen_mod
from .db import get_setting
from .filters import RuleSpec, evaluate
from .models import Channel, Deal, Match, NotificationLog, Rule, utcnow
from .pipeline.regeln import in_quiet_hours
from .pricefehler import SCHWELLE_HEISS

log = logging.getLogger(__name__)

# Wie eine Stufe ausgehen kann.
DURCH = "durch"          # weitergereicht
GESTOPPT = "gestoppt"    # hier war Schluss
HINWEIS = "hinweis"      # durchgelassen, aber erwaehnenswert


@dataclass
class Stufe:
    name: str
    stand: str
    text: str
    rat: str = ""                       # was man dagegen tun kann
    details: list[dict] = field(default_factory=list)
    # Liegt diese Stufe auf dem Weg, den dieser Fund wirklich genommen
    # haette? Es gibt zwei Wege - Regeln und Preisfehler-Waechter -, und
    # eine Stufe des einen sagt nichts ueber den anderen. Ohne diese
    # Unterscheidung lautete die Antwort auf "warum kam nichts an?"
    # bei jedem gewoehnlichen Deal "zu wenig Preisfehler-Punkte", was
    # zwar stimmt, aber am Thema vorbeigeht.
    blockiert: bool = True

    def as_dict(self) -> dict:
        raus = {"name": self.name, "stand": self.stand, "text": self.text,
                "blockiert": self.blockiert}
        if self.rat:
            raus["rat"] = self.rat
        if self.details:
            raus["details"] = self.details
        return raus


def _stufe_erwachsen(db: Session, deal: Deal) -> Stufe:
    if not deal.erwachsen:
        return Stufe("18+-Sperre", DURCH, "kein 18+-Fund")
    if not erwachsen_mod.melden_erlaubt(db):
        return Stufe("18+-Sperre", GESTOPPT,
                     "Dieser Fund ist als 18+ eingestuft, und die Zustellung "
                     "von 18+-Funden ist global ausgeschaltet.",
                     "Unter „18+“ die Zustellung einschalten — oder so lassen, "
                     "wenn der Bereich absichtlich nur zum Ansehen ist.")
    return Stufe("18+-Sperre", HINWEIS,
                 "18+-Fund, Zustellung ist erlaubt. Es greifen nur Regeln "
                 "mit ausdruecklichem 18+-Haekchen.")


def _stufe_regeln(db: Session, deal: Deal) -> tuple[Stufe, list[Rule]]:
    """Welche Regel trifft - und bei welcher woran es scheiterte."""
    alle = list(db.scalars(select(Rule).order_by(Rule.id)))
    if not alle:
        return Stufe("Regeln", GESTOPPT, "Es gibt noch keine Regel.",
                     "Ohne Regel wird nichts gemeldet. Der Regel-Editor "
                     "schlaegt aus deinem Verhalten welche vor."), []

    treffer: list[Rule] = []
    details: list[dict] = []
    for regel in alle:
        if not regel.enabled:
            details.append({"regel": regel.name, "id": regel.id,
                            "stand": "aus",
                            "text": "Diese Regel ist ausgeschaltet."})
            continue
        ergebnis = evaluate(RuleSpec.from_model(regel), deal)
        if ergebnis.matched:
            treffer.append(regel)
            details.append({"regel": regel.name, "id": regel.id,
                            "stand": "trifft",
                            "text": ", ".join(ergebnis.reasons) or "alle Bedingungen erfuellt",
                            "prioritaet": (regel.priority or "NORMAL").upper()})
        else:
            details.append({"regel": regel.name, "id": regel.id,
                            "stand": "trifft nicht",
                            "text": ", ".join(ergebnis.failed) or "Bedingung nicht erfuellt"})

    if treffer:
        namen = ", ".join(r.name for r in treffer)
        return Stufe("Regeln", DURCH, f"getroffen von: {namen}",
                     details=details), treffer

    return Stufe("Regeln", GESTOPPT, "Keine aktive Regel trifft diesen Fund.",
                 "Die Liste unten sagt je Regel, woran es lag — meistens ist "
                 "es ein Stichwort, das anders geschrieben ist.",
                 details=details), []


def _stufe_preisfehler(db: Session, deal: Deal) -> Stufe:
    """Der Weg neben den Regeln: ein Preisfehler meldet ohne Regel."""
    waechter = bool(get_setting(db, "preisfehler_waechter", True))
    schwelle = int(get_setting(db, "preisfehler_schwelle", SCHWELLE_HEISS))
    punkte = int(deal.fehler_score or 0)

    if not waechter:
        return Stufe("Preisfehler-Weg", GESTOPPT,
                     "Der Preisfehler-Waechter ist ausgeschaltet.",
                     "Unter „Preisfehler“ wieder einschalten.")
    if punkte < schwelle:
        return Stufe("Preisfehler-Weg", GESTOPPT,
                     f"{punkte} von {schwelle} Punkten — zu wenig fuer eine "
                     f"eigene Meldung.")
    if deal.fehler_gemeldet_am and utcnow() - deal.fehler_gemeldet_am < timedelta(hours=12):
        return Stufe("Preisfehler-Weg", GESTOPPT,
                     "Schon gemeldet — dieselbe Fundstelle weckt hoechstens "
                     "alle 12 Stunden.")
    return Stufe("Preisfehler-Weg", DURCH,
                 f"{punkte} Punkte, ab {schwelle} geht er ohne Regel raus.")


def _stufe_pause(db: Session, regeln: list[Rule]) -> Stufe:
    if get_setting(db, "notifications_paused"):
        return Stufe("Pause", GESTOPPT,
                     "Die Zustellung ist global angehalten.",
                     "Im UI fortsetzen oder in Telegram /weiter schicken. "
                     "Zurueckgehaltenes kommt als Sammelmeldung nach.")
    return Stufe("Pause", DURCH, "nicht pausiert")


def _stufe_ruhezeit(db: Session, regeln: list[Rule]) -> Stufe:
    if not in_quiet_hours(db):
        return Stufe("Ruhezeit", DURCH, "keine Ruhezeit")
    sofort = [r for r in regeln if (r.priority or "NORMAL").upper() == "SOFORT"]
    if sofort:
        return Stufe("Ruhezeit", DURCH,
                     f"Ruhezeit, aber „{sofort[0].name}“ hat Prioritaet SOFORT.")
    return Stufe("Ruhezeit", GESTOPPT,
                 "Ruhezeit — der Fund kommt mit der naechsten Sammelmeldung.",
                 "Wer solche Funde auch nachts will, stellt die Regel auf "
                 "SOFORT; die Ruhezeit laesst SOFORT immer durch.")


def _stufe_kanaele(db: Session, regeln: list[Rule]) -> Stufe:
    ziel_ids: list[int] = []
    for regel in regeln:
        for cid in regel.channels or []:
            if cid not in ziel_ids:
                ziel_ids.append(cid)

    if not ziel_ids:
        return Stufe("Kanaele", GESTOPPT,
                     "Keine der treffenden Regeln hat einen Kanal zugeordnet.",
                     "In der Regel unten einen Kanal ankreuzen — sonst gibt es "
                     "einen Treffer, aber keinen Empfaenger.")

    details = []
    offen = 0
    for cid in ziel_ids:
        kanal = db.get(Channel, cid)
        if kanal is None:
            details.append({"kanal": f"#{cid}", "stand": "weg",
                            "text": "Dieser Kanal existiert nicht mehr."})
            continue
        if not kanal.enabled:
            details.append({"kanal": kanal.name, "stand": "aus",
                            "text": "Der Kanal ist ausgeschaltet."})
            continue
        offen += 1
        details.append({"kanal": kanal.name, "stand": "bereit",
                        "text": f"{kanal.type}, zuletzt benutzt: "
                                f"{kanal.last_used or 'nie'}"})

    if not offen:
        return Stufe("Kanaele", GESTOPPT,
                     "Alle zugeordneten Kanaele sind aus oder geloescht.",
                     "Kanal einschalten oder der Regel einen anderen geben.",
                     details=details)
    return Stufe("Kanaele", DURCH, f"{offen} Kanal/Kanaele bereit",
                 details=details)


def _stufe_kanaele_alle(db: Session) -> Stufe:
    """Der Preisfehler-Weg kennt keine Regel - er nimmt alle aktiven Kanaele."""
    kanaele = list(db.scalars(select(Channel)))
    aktiv = [k for k in kanaele if k.enabled]
    details = [{"kanal": k.name, "stand": "bereit" if k.enabled else "aus",
                "text": k.type} for k in kanaele]
    if not aktiv:
        return Stufe("Kanaele", GESTOPPT,
                     "Es ist kein Kanal eingeschaltet.",
                     "Unter „Benachrichtigungen“ einen Kanal anlegen und "
                     "einschalten — „Test senden“ zeigt sofort, ob er geht.",
                     details=details)
    return Stufe("Kanaele", DURCH,
                 f"{len(aktiv)} aktive(r) Kanal/Kanaele — der "
                 f"Preisfehler-Weg nimmt alle.", details=details)


def _stufe_versand(db: Session, deal: Deal) -> Stufe:
    """Was wirklich passiert ist - der Versandverlauf zu diesem Deal."""
    zeilen = list(db.scalars(
        select(NotificationLog).where(NotificationLog.deal_id == deal.id)
        .order_by(desc(NotificationLog.created_at)).limit(20)))

    if not zeilen:
        # Kein Eintrag heisst: es wurde nie versucht. Das ist die Folge
        # einer frueheren Stufe, nicht die Ursache - sonst stuende hier
        # bei jedem nicht zugestellten Fund dieselbe leere Antwort.
        return Stufe("Versand", HINWEIS,
                     "Zu diesem Fund wurde nie ein Zustellversuch "
                     "unternommen.", blockiert=False)

    details = [{"kanal": z.channel_type, "regel": z.rule_name,
                "stand": "ok" if z.ok else "fehler",
                "text": z.error or "zugestellt",
                "zeit": z.created_at} for z in zeilen]
    gut = sum(1 for z in zeilen if z.ok)
    if gut:
        return Stufe("Versand", DURCH,
                     f"{gut} von {len(zeilen)} Versuchen erfolgreich",
                     details=details)
    return Stufe("Versand", GESTOPPT,
                 "Alle Zustellversuche sind fehlgeschlagen — der Grund steht "
                 "unten im Klartext.",
                 "Meistens ein abgelaufenes Token oder ein Webhook, den es "
                 "nicht mehr gibt. „Test senden“ beim Kanal zeigt es sofort.",
                 details=details)


def diagnose(db: Session, deal: Deal) -> dict:
    """Den ganzen Weg ablaufen und als Liste von Stufen zurueckgeben.

    Es gibt zwei Wege zu einer Meldung: ueber eine Regel, und - ohne
    Regel, ohne Ruhezeit - ueber den Preisfehler-Waechter. Welcher
    gegolten haette, entscheidet sich an der Regel-Stufe; die Stufen des
    jeweils anderen Wegs bleiben sichtbar, zaehlen aber nicht als Grund.
    """
    stufen: list[Stufe] = []

    stufen.append(_stufe_erwachsen(db, deal))
    regel_stufe, treffer = _stufe_regeln(db, deal)
    preis_stufe = _stufe_preisfehler(db, deal)

    ueber_regel = bool(treffer)
    ueber_preisfehler = preis_stufe.stand == DURCH

    # Trifft eine Regel, ist der Preisfehler-Weg nur eine Nebenbemerkung -
    # und umgekehrt.
    preis_stufe.blockiert = not ueber_regel
    regel_stufe.blockiert = not ueber_preisfehler or ueber_regel

    stufen.append(regel_stufe)
    stufen.append(preis_stufe)
    stufen.append(_stufe_pause(db, treffer))
    stufen.append(_stufe_ruhezeit(db, treffer) if ueber_regel
                  else Stufe("Ruhezeit", DURCH,
                             "Der Preisfehler-Weg kennt keine Ruhezeit."
                             if ueber_preisfehler else "keine Ruhezeit",
                             blockiert=False))
    if ueber_regel:
        stufen.append(_stufe_kanaele(db, treffer))
    elif ueber_preisfehler:
        stufen.append(_stufe_kanaele_alle(db))
    stufen.append(_stufe_versand(db, deal))

    zugestellt = bool(db.scalar(
        select(Match).where(Match.deal_id == deal.id,
                            Match.notified_at.is_not(None)).limit(1)))

    # Die erste Stufe, die auf dem gegangenen Weg stoppt, ist die Antwort -
    # und zwar die erste in der Reihenfolge der Zustellung. Ein 18+-Fund
    # bei abgeschalteter 18+-Zustellung wird nicht zugestellt, egal wie
    # die Regeln stehen; das gehoert dann auch ins Fazit und nicht die
    # Regel-Stufe, die zufaellig auch stoppt.
    erste_sperre = next((s for s in stufen
                         if s.stand == GESTOPPT and s.blockiert), None)
    if zugestellt:
        fazit = "Dieser Fund wurde zugestellt."
    elif erste_sperre is None:
        fazit = ("Kein Hindernis gefunden — der Fund duerfte unterwegs sein "
                 "oder in der naechsten Sammelmeldung stecken.")
    elif erste_sperre is regel_stufe and not ueber_preisfehler:
        # Beide Wege zu, und der Grund steht in der Regel-Stufe.
        fazit = (f"Weder eine Regel noch der Preisfehler-Waechter greift. "
                 f"{regel_stufe.text}")
    else:
        fazit = f"{erste_sperre.name}: {erste_sperre.text}"

    return {
        "deal_id": deal.id,
        "titel": deal.titel,
        "zugestellt": zugestellt,
        "weg": "regel" if ueber_regel else ("preisfehler" if ueber_preisfehler else "keiner"),
        "fazit": fazit,
        "stufen": [s.as_dict() for s in stufen],
    }
