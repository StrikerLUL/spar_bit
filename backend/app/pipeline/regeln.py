"""Welche Regel trifft, was die Ruhezeit sagt, was gebuendelt wird.

Das Stueck zwischen Aufnahme und Versand: hier entscheidet sich, ob aus
einem Deal ueberhaupt eine Meldung wird - und ob sie jetzt raus darf.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import erwachsen as erwachsen_mod
from ..db import get_setting
from ..events import broker
from ..filters import RuleSpec, evaluate
from ..models import Deal, Match, Rule, utcnow
from .gemeinsam import _deal_payload

log = logging.getLogger(__name__)


# --- Regel-Auswertung ------------------------------------------------------

def match_rules(db: Session, deals: list[Deal]) -> list[tuple[Rule, Deal]]:
    """Neue Deals gegen alle aktiven Regeln pruefen."""
    if not deals:
        return []
    rules = list(db.scalars(select(Rule).where(Rule.enabled.is_(True))))
    if not rules:
        return []

    hits: list[tuple[Rule, Deal]] = []
    for rule in rules:
        spec = RuleSpec.from_model(rule)
        for deal in deals:
            if not evaluate(spec, deal).matched:
                continue
            exists = db.scalar(select(Match).where(Match.rule_id == rule.id,
                                                   Match.deal_id == deal.id))
            if exists:
                continue
            db.add(Match(rule_id=rule.id, deal_id=deal.id))
            rule.match_count += 1
            rule.last_match = utcnow()
            hits.append((rule, deal))
            broker.publish("match", {"regel": rule.name, "prioritaet": rule.priority,
                                     **_deal_payload(deal)})
    if hits:
        db.commit()
    return hits


# --- Ruhezeiten ------------------------------------------------------------

def _parse_hhmm(raw: str, fallback: time) -> time:
    try:
        hh, mm = str(raw).split(":")
        return time(int(hh) % 24, int(mm) % 60)
    except (ValueError, AttributeError):
        return fallback


def in_quiet_hours(db: Session, now: datetime | None = None) -> bool:
    cfg = get_setting(db, "quiet_hours") or {}
    if not cfg.get("enabled"):
        return False
    now = (now or datetime.now(UTC)).astimezone(
        timezone(timedelta(hours=float(cfg.get("utc_offset", 2)))))
    start = _parse_hhmm(cfg.get("start", "23:00"), time(23, 0))
    end = _parse_hhmm(cfg.get("end", "07:00"), time(7, 0))
    cur = now.time()
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end     # ueber Mitternacht


def buendele(hits: list[tuple[Rule, Deal]]) -> list[tuple[Deal, list[Rule]]]:
    """Treffer nach Deal zusammenfassen.

    Vorher ging je (Regel, Deal)-Paar eine Nachricht raus. Wer eine Regel
    fuer "Lego" und eine fuer "Preisfehler" hat, bekam denselben Fund
    zweimal aufs Handy - und je mehr Regeln, desto schlimmer. Die
    Reihenfolge der Deals bleibt, damit Aelteres zuerst kommt.
    """
    raus: dict[int, tuple[Deal, list[Rule]]] = {}
    for rule, deal in hits:
        schluessel = deal.id if deal.id is not None else id(deal)
        if schluessel in raus:
            regeln = raus[schluessel][1]
            if all(r.id != rule.id for r in regeln):
                regeln.append(rule)
        else:
            raus[schluessel] = (deal, [rule])
    return list(raus.values())


def _sofort(regeln: list[Rule]) -> bool:
    """SOFORT gewinnt: trifft eine dringende Regel, ist der Fund dringend."""
    return any((r.priority or "NORMAL").upper() == "SOFORT" for r in regeln)


def _regelnamen(regeln: list[Rule]) -> str:
    namen = [r.name for r in regeln]
    if len(namen) <= 3:
        return ", ".join(namen)
    return ", ".join(namen[:3]) + f" +{len(namen) - 3}"


def _ohne_erwachsene(db: Session, paare: list[tuple[Deal, list[Rule]]]
                     ) -> list[tuple[Deal, list[Rule]]]:
    """Zweite Sperre vor dem Versand.

    Die erste sitzt in der Regel-Auswertung: eine Regel ohne 18+-Haekchen
    trifft diese Deals gar nicht. Hier geht es um den globalen Schalter -
    wer den Bereich ansehen, aber nicht aufs Handy bekommen will, stellt
    ihn aus, und dann gilt das fuer jede Regel, auch fuer eine mit Haekchen.
    """
    if not any(d.erwachsen for d, _ in paare):
        return paare
    if erwachsen_mod.melden_erlaubt(db):
        return paare
    behalten = [(d, r) for d, r in paare if not d.erwachsen]
    zurueck = len(paare) - len(behalten)
    if zurueck:
        log.info("18+-Zustellung ist aus - %d Fund(e) nur auf der Seite",
                 zurueck)
    return behalten


def _zielkanaele(regeln: list[Rule]) -> list[int]:
    """Vereinigung der Kanaele aller beteiligten Regeln, Reihenfolge stabil."""
    raus: list[int] = []
    for regel in regeln:
        for cid in regel.channels or []:
            if cid not in raus:
                raus.append(cid)
    return raus


