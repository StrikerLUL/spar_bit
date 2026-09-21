"""Was rausgeht: Regeltreffer, Sammelmeldung, Preisalarm, Waechter.

Vier Absender, eine Meldungsform (siehe gemeinsam._note) - damit
ueberall dieselben Zahlen stehen.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..db import get_setting
from ..events import broker
from ..models import Channel, Deal, Match, NotificationLog, Rule, utcnow
from ..notify import Notification, Sammelmeldung, get_channel
from .gemeinsam import _deal_payload, _note
from .regeln import _ohne_erwachsene, _regelnamen, _sofort, _zielkanaele, buendele, in_quiet_hours

log = logging.getLogger(__name__)


async def dispatch(db: Session, hits: list[tuple[Rule, Deal]], http) -> int:
    """Treffer an die Kanaele geben - ein Deal, eine Nachricht.

    SOFORT umgeht Ruhezeiten. Treffen mehrere Regeln denselben Deal, zaehlt
    die dringendste Prioritaet und es gehen alle ihre Kanaele an.
    """
    if not hits:
        return 0

    # Per Telegram (/pause) global angehalten? Treffer bleiben gespeichert,
    # nur die Zustellung ruht - /weiter holt sie als Digest nach.
    if get_setting(db, "notifications_paused"):
        log.info("Zustellung pausiert - %d Treffer zurueckgehalten", len(hits))
        return 0

    quiet = in_quiet_hours(db)
    channels = {c.id: c for c in db.scalars(select(Channel))}
    sent = 0

    for deal, regeln in _ohne_erwachsene(db, buendele(hits)):
        sofort = _sofort(regeln)
        if quiet and not sofort:
            log.info("Ruhezeit: '%s' zurueckgehalten (%s)",
                     deal.titel[:60], _regelnamen(regeln))
            continue

        target_ids = _zielkanaele(regeln)
        if not target_ids:
            log.warning("Keine der Regeln %s hat einen Kanal konfiguriert",
                        _regelnamen(regeln))
            continue

        note = _note(deal, regel=_regelnamen(regeln),
                     prioritaet="SOFORT" if sofort else "NORMAL")

        # Fuer das Protokoll die Regel, die den Fund erklaert: die
        # dringendste, sonst die erste.
        protokoll_regel = next(
            (r for r in regeln if (r.priority or "NORMAL").upper() == "SOFORT"),
            regeln[0])

        for cid in target_ids:
            chan_row = channels.get(cid)
            if not chan_row or not chan_row.enabled:
                continue
            impl = get_channel(chan_row.type)
            if impl is None:
                log.error("Unbekannter Kanaltyp '%s'", chan_row.type)
                continue
            try:
                await impl.send(chan_row.config or {}, note, http)
                chan_row.last_used = utcnow()
                sent += 1
                db.add(NotificationLog(
                    channel_id=cid, channel_type=chan_row.type,
                    rule_id=protokoll_regel.id, rule_name=_regelnamen(regeln),
                    deal_id=deal.id, deal_titel=deal.titel[:500], ok=True))
            except Exception as exc:
                chan_row.error_count += 1
                log.error("Kanal %s (%s) fehlgeschlagen: %s",
                          chan_row.name, chan_row.type, exc,
                          extra={"channel": chan_row.type})
                db.add(NotificationLog(
                    channel_id=cid, channel_type=chan_row.type,
                    rule_id=protokoll_regel.id, rule_name=_regelnamen(regeln),
                    deal_id=deal.id, deal_titel=deal.titel[:500], ok=False,
                    error=f"{type(exc).__name__}: {exc}"[:500]))

        # Alle beteiligten Regeln gelten als zugestellt - sonst kaeme der
        # Deal im naechsten Digest nochmal.
        for regel in regeln:
            match = db.scalar(select(Match).where(Match.rule_id == regel.id,
                                                  Match.deal_id == deal.id))
            if match:
                match.notified_at = utcnow()

    db.commit()
    return sent


def _zeitraum(seit: datetime | None) -> str:
    """„seit 07:12“ bzw. „über Nacht“ - was der Digest im Titel nennt."""
    if seit is None:
        return ""
    stunden = (utcnow() - seit).total_seconds() / 3600
    if stunden >= 6:
        return "über Nacht" if stunden >= 10 else "in den letzten Stunden"
    return f"seit {seit.astimezone(UTC).strftime('%H:%M')} UTC"


async def send_digest(db: Session, http) -> int:
    """Eine Sammelnachricht fuer alles, was liegen geblieben ist.

    Bis hierher wurden aufgestaute Treffer einfach an dispatch()
    weitergereicht - also zwanzig Einzelnachrichten um sieben Uhr statt
    einer Zusammenfassung. Jetzt geht je Kanal genau eine Meldung raus,
    mit den interessantesten Funden zuerst.
    """
    if get_setting(db, "notifications_paused"):
        return 0
    if in_quiet_hours(db):
        return 0

    pending = list(db.scalars(
        select(Match).where(Match.notified_at.is_(None))
        .order_by(Match.created_at.asc()).limit(200)
    ))
    if not pending:
        return 0

    rules = {r.id: r for r in db.scalars(select(Rule))}
    hits = [(rules[m.rule_id], m.deal) for m in pending
            if m.rule_id in rules and m.deal is not None]
    if not hits:
        return 0

    channels = {c.id: c for c in db.scalars(select(Channel))}

    # Je Kanal sammeln, was dort hingehoert: ein Deal kann ueber mehrere
    # Regeln in mehreren Kanaelen landen, soll aber je Kanal einmal
    # vorkommen.
    pro_kanal: dict[int, list[Notification]] = {}
    for deal, regeln in _ohne_erwachsene(db, buendele(hits)):
        note = _note(deal, regel=_regelnamen(regeln),
                     prioritaet="SOFORT" if _sofort(regeln) else "NORMAL")
        for cid in _zielkanaele(regeln):
            pro_kanal.setdefault(cid, []).append(note)

    aeltester = min((m.created_at for m in pending if m.created_at), default=None)
    zeitraum = _zeitraum(aeltester)
    gesendet = 0

    for cid, meldungen in pro_kanal.items():
        chan_row = channels.get(cid)
        if not chan_row or not chan_row.enabled:
            continue
        impl = get_channel(chan_row.type)
        if impl is None:
            log.error("Unbekannter Kanaltyp '%s'", chan_row.type)
            continue

        sammel = Sammelmeldung(meldungen=meldungen, zeitraum=zeitraum)
        try:
            await impl.send_sammel(chan_row.config or {}, sammel, http)
            chan_row.last_used = utcnow()
            gesendet += 1
            db.add(NotificationLog(
                channel_id=cid, channel_type=chan_row.type,
                rule_name="Zusammenfassung",
                deal_titel=f"{sammel.anzahl} Funde"[:500], ok=True))
        except Exception as exc:
            chan_row.error_count += 1
            log.error("Digest über %s fehlgeschlagen: %s", chan_row.type, exc)
            db.add(NotificationLog(
                channel_id=cid, channel_type=chan_row.type,
                rule_name="Zusammenfassung",
                deal_titel=f"{sammel.anzahl} Funde"[:500], ok=False,
                error=f"{type(exc).__name__}: {exc}"[:500]))

    # Nur als zugestellt markieren, wenn wenigstens ein Kanal es genommen
    # hat - sonst waeren die Treffer weg, ohne je angekommen zu sein.
    if gesendet:
        for match in pending:
            match.notified_at = utcnow()

    db.commit()
    if gesendet:
        log.info("Digest: %d Funde an %d Kanäle", len(hits), gesendet)
    return gesendet


def check_price_alarms(db: Session) -> list[Deal]:
    """Deals finden, deren Preis unter die gesetzte Alarmschwelle gefallen ist.

    Ein Alarm loest genau einmal aus - sonst meldet sich SparBit bei jedem
    Lauf erneut, solange der Preis unten bleibt.
    """
    kandidaten = list(db.scalars(
        select(Deal).where(Deal.alarm_preis.isnot(None),
                           Deal.alarm_ausgeloest.is_(None))
    ))
    getroffen: list[Deal] = []
    for deal in kandidaten:
        preis = deal.preis_eur if deal.preis_eur is not None else deal.preis
        if preis is None:
            continue
        if preis <= deal.alarm_preis:
            deal.alarm_ausgeloest = utcnow()
            getroffen.append(deal)
            log.info("Preisalarm: '%s' bei %.2f (Schwelle %.2f)",
                     deal.titel[:60], preis, deal.alarm_preis)
    if getroffen:
        db.commit()
        for deal in getroffen:
            broker.publish("alarm", _deal_payload(deal))
    return getroffen


async def dispatch_alarms(db: Session, deals: list[Deal], http) -> int:
    """Preisalarme ueber alle aktiven Kanaele melden - unabhaengig von Regeln.
    Ein Alarm ist immer gewollt, sonst haette man ihn nicht gesetzt."""
    if not deals:
        return 0
    channels = [c for c in db.scalars(select(Channel)) if c.enabled]
    if not channels:
        return 0

    sent = 0
    for deal in deals:
        note = _note(deal, regel="Preisalarm", prioritaet="SOFORT",
                     titel=f"Preisalarm: {deal.titel}",
                     beschreibung=("Dein Zielpreis war "
                                   f"{money.betrag(deal.alarm_preis)}."))
        for row in channels:
            impl = get_channel(row.type)
            if impl is None:
                continue
            try:
                await impl.send(row.config or {}, note, http)
                sent += 1
                db.add(NotificationLog(channel_id=row.id, channel_type=row.type,
                                       rule_name="Preisalarm", deal_id=deal.id,
                                       deal_titel=deal.titel[:500], ok=True))
            except Exception as exc:
                log.error("Preisalarm ueber %s fehlgeschlagen: %s", row.type, exc)
                db.add(NotificationLog(channel_id=row.id, channel_type=row.type,
                                       rule_name="Preisalarm", deal_id=deal.id,
                                       deal_titel=deal.titel[:500], ok=False,
                                       error=f"{type(exc).__name__}: {exc}"[:500]))
    db.commit()
    return sent


# --- Preisfehler-Waechter --------------------------------------------------
#
# Ein eigener Zustellweg neben den Regeln, und das mit Absicht: ein
# Preisfehler ist nach zwanzig Minuten korrigiert. Er darf nicht davon
# abhaengen, ob jemand vorher eine passende Regel gebaut hat, und er darf
# nicht in der Ruhezeit liegen bleiben. Wer um drei Uhr nachts nicht geweckt
# werden will, schaltet den Waechter ab - aber gedrosselt ist er nicht
# nuetzlich, sondern nur noch unzuverlaessig.

# Wie lange derselbe Deal nicht erneut gemeldet wird. Ohne diese Sperre
# meldet sich SparBit bei jedem Quellenlauf aufs Neue, solange der falsche
# Preis online steht.
FEHLER_SPERRE_STUNDEN = 12


async def dispatch_watchdog(db: Session, http) -> int:
    """Befunde der Selbstueberwachung melden.

    Eigener Weg, weil es hier keinen Deal und keine Regel gibt - und weil
    diese Meldung auch dann rausmuss, wenn gerade keine Regel greift. Die
    Ruhezeit wird respektiert: ein kaputter Kanal um drei Uhr nachts ist
    kein Grund, jemanden zu wecken; die Pruefung laeuft ohnehin alle
    15 Minuten wieder.
    """
    from . import watchdog

    if get_setting(db, "notifications_paused"):
        return 0
    if in_quiet_hours(db):
        return 0
    if not get_setting(db, "watchdog_an", True):
        return 0

    lage = watchdog.faellig(db, watchdog.pruefe(db))
    if not lage.probleme and not lage.entwarnungen:
        return 0

    kanaele = [c for c in db.scalars(select(Channel)) if c.enabled]
    if not kanaele:
        # Ohne Kanal laesst sich nichts melden - aber ins Log gehoert es.
        for befund in lage.probleme:
            log.warning("Selbstueberwachung: %s", befund.text)
        watchdog.merke(db, lage)
        return 0

    meldungen: list[Notification] = []
    for befund in lage.probleme:
        meldungen.append(Notification(
            titel=befund.text,
            url="", quelle="system", regel="Selbstüberwachung",
            beschreibung=befund.rat or None,
            prioritaet="NORMAL", ist_hinweis=True))
    for schluessel in lage.entwarnungen:
        meldungen.append(Notification(
            titel=watchdog.text_fuer_entwarnung(schluessel),
            url="", quelle="system", regel="Selbstüberwachung",
            prioritaet="NORMAL", ist_hinweis=True, ist_entwarnung=True))

    gesendet = 0
    for note in meldungen:
        for kanal in kanaele:
            impl = get_channel(kanal.type)
            if impl is None:
                continue
            try:
                await impl.send(kanal.config or {}, note, http)
                kanal.last_used = utcnow()
                gesendet += 1
            except Exception as exc:
                # Nicht in den Fehlerzaehler: sonst meldet ein kaputter
                # Kanal sich selbst kaputt und treibt den Zaehler hoch.
                log.error("Selbstueberwachung über %s fehlgeschlagen: %s",
                          kanal.type, exc)

    watchdog.merke(db, lage)
    log.info("Selbstueberwachung: %d Probleme, %d Entwarnungen gemeldet",
             len(lage.probleme), len(lage.entwarnungen))
    return gesendet


def waechter_aktiv(db: Session) -> bool:
    return bool(get_setting(db, "preisfehler_waechter", True))


async def dispatch_preisfehler(db: Session, deals: list[Deal], http) -> int:
    """Preisfehler ueber alle aktiven Kanaele melden - sofort, ohne Regel."""
    if not deals or not waechter_aktiv(db):
        return 0

    kanaele = [c for c in db.scalars(select(Channel)) if c.enabled]
    if not kanaele:
        log.warning("Preisfehler gefunden, aber kein Kanal eingerichtet: %s",
                    ", ".join(d.titel[:40] for d in deals[:3]))
        return 0

    sperre = utcnow() - timedelta(hours=FEHLER_SPERRE_STUNDEN)
    gesendet = 0

    for deal in deals:
        if deal.fehler_gemeldet_am and deal.fehler_gemeldet_am > sperre:
            continue

        gruende = deal.fehler_gruende or []
        note = _note(
            deal, regel="Preisfehler-Wächter", prioritaet="SOFORT",
            titel=deal.titel,
            beschreibung=" ".join(gruende) or "Auffällig niedriger Preis.")

        for kanal in kanaele:
            impl = get_channel(kanal.type)
            if impl is None:
                continue
            try:
                await impl.send(kanal.config or {}, note, http)
                kanal.last_used = utcnow()
                gesendet += 1
                db.add(NotificationLog(
                    channel_id=kanal.id, channel_type=kanal.type,
                    rule_name="Preisfehler", deal_id=deal.id,
                    deal_titel=deal.titel[:500], ok=True))
            except Exception as exc:
                kanal.error_count += 1
                log.error("Preisfehler-Meldung über %s fehlgeschlagen: %s",
                          kanal.type, exc)
                db.add(NotificationLog(
                    channel_id=kanal.id, channel_type=kanal.type,
                    rule_name="Preisfehler", deal_id=deal.id,
                    deal_titel=deal.titel[:500], ok=False,
                    error=f"{type(exc).__name__}: {exc}"[:500]))

        deal.fehler_gemeldet_am = utcnow()
        broker.publish("preisfehler", {**_deal_payload(deal),
                                       "gruende": gruende})

    db.commit()
    return gesendet
