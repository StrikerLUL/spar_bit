"""Der Weg eines Deals: Quelle -> Dedupe -> DB -> Regeln -> Kanaele."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import money
from .currency import to_eur
from .db import get_setting
from .dedupe import canonical_url, normalize_title, titles_match, url_hash
from .events import broker
from .filters import RuleSpec, evaluate
from .models import (Channel, Deal, DealOffer, Match, NotificationLog,
                     PriceHistory, Rule, SourceConfig, utcnow)
from .notify import Notification, get_channel
from .sources.base import DealItem

log = logging.getLogger(__name__)

# Wie weit zurueck wird auf Fuzzy-Duplikate geprueft.
DEDUPE_WINDOW_HOURS = 72
DEDUPE_CANDIDATES = 400


def ingest(db: Session, source_id: str, items: list[DealItem]) -> list[Deal]:
    """Neue Deals speichern. Gibt die tatsaechlich NEUEN zurueck."""
    if not items:
        return []

    since = utcnow() - timedelta(hours=DEDUPE_WINDOW_HOURS)
    recent = list(db.scalars(
        select(Deal).where(Deal.first_seen >= since, Deal.duplicate_of.is_(None))
        .order_by(Deal.first_seen.desc()).limit(DEDUPE_CANDIDATES)
    ))
    # Titel-Index nur ueber die Kandidaten, damit der Fuzzy-Vergleich billig bleibt.
    fresh: list[Deal] = []

    for item in items:
        try:
            deal = _ingest_one(db, source_id, item, recent)
        except Exception as exc:
            log.warning("Deal verworfen (%s): %s", source_id, exc,
                        extra={"source_id": source_id})
            continue
        if deal is not None:
            fresh.append(deal)
            recent.insert(0, deal)

    if fresh:
        db.commit()
        for deal in fresh:
            broker.publish("deal", _deal_payload(deal))
    return fresh


def _ingest_one(db: Session, source_id: str, item: DealItem,
                recent: list[Deal]) -> Deal | None:
    if not item.url or not item.titel:
        return None

    uhash = url_hash(item.url)

    # 1) Exaktes URL-Duplikat -> nur "wieder gesehen" vermerken.
    existing = db.scalar(select(Deal).where(Deal.url_hash == uhash))
    if existing:
        existing.last_seen = utcnow()
        existing.seen_count += 1
        _merke_angebot(db, existing, item, source_id)
        _apply_price(db, existing, item, source_id)
        if source_id not in (existing.also_from or []) and source_id != existing.quelle:
            existing.also_from = list(existing.also_from or []) + [source_id]
        return None

    titel_norm = normalize_title(item.titel)

    # 2) Fuzzy-Duplikat ueber Quellen hinweg.
    for cand in recent:
        if cand.titel_norm and titles_match(item.titel, cand.titel):
            # Gleicher Titel, andere URL -> derselbe Deal aus anderer Quelle.
            cand.last_seen = utcnow()
            cand.seen_count += 1
            if source_id not in (cand.also_from or []) and source_id != cand.quelle:
                cand.also_from = list(cand.also_from or []) + [source_id]
            _merke_angebot(db, cand, item, source_id)
            _apply_price(db, cand, item, source_id)
            log.debug("Duplikat: '%s' (%s) == '%s' (%s)",
                      item.titel[:60], source_id, cand.titel[:60], cand.quelle)
            return None

    # Streichpreis nur uebernehmen, wenn er ueber dem Preis liegt, und den
    # Rabatt daraus rechnen. Sonst steht auf der Karte ein Prozentwert, der
    # sich aus den beiden danebenstehenden Zahlen nicht ergibt.
    original = item.originalpreis
    if original is not None and item.preis is not None and original <= item.preis:
        original = None

    deal = Deal(
        url_hash=uhash,
        titel=item.titel[:1000],
        titel_norm=titel_norm,
        beschreibung=item.beschreibung,
        url=item.url,
        bild=item.bild,
        preis=item.preis,
        originalpreis=original,
        rabatt_prozent=_rabatt(item.preis, original, item.rabatt_prozent,
                               item.ist_gratis),
        waehrung=item.waehrung,
        preis_eur=to_eur(item.preis, item.waehrung),
        ist_gratis=item.ist_gratis,
        haendler=(item.haendler or None) and item.haendler[:128],
        kategorie=item.kategorie,
        quelle=item.quelle or source_id,
        temperatur=item.temperatur,
        tags=item.tags or [],
        veroeffentlicht_am=item.veroeffentlicht_am,
        also_from=[],
        roh=item.roh or {},
    )
    db.add(deal)
    db.flush()
    _merke_angebot(db, deal, item, source_id)
    if deal.preis is not None:
        db.add(PriceHistory(deal_id=deal.id, preis=deal.preis,
                            waehrung=deal.waehrung, quelle=source_id))
    return deal


def _merke_angebot(db: Session, deal: Deal, item: DealItem, source_id: str) -> None:
    """Was diese Quelle fuer diesen Artikel verlangt.

    Der Deal-Datensatz haelt nur den besten Preis. Fuer den Vergleich
    ("wo ist es wie teuer") braucht es das Angebot je Quelle - sonst weiss
    man am Ende nur, dass es irgendwo guenstiger war.
    """
    # Schluessel ist die laufende Quelle, nicht item.quelle: also_from wird
    # ebenfalls damit gefuehrt, und die beiden muessen zusammenpassen, sonst
    # zeigt die Karte "3 Angebote" und die Detailansicht nur zwei.
    quelle = source_id or item.quelle
    angebot = db.scalar(select(DealOffer).where(DealOffer.deal_id == deal.id,
                                                DealOffer.quelle == quelle))
    preis_eur = to_eur(item.preis, item.waehrung)

    if angebot is None:
        db.add(DealOffer(
            deal_id=deal.id, quelle=quelle, url=item.url,
            preis=item.preis, waehrung=item.waehrung, preis_eur=preis_eur,
            originalpreis=item.originalpreis, rabatt_prozent=item.rabatt_prozent,
            haendler=(item.haendler or None) and item.haendler[:128],
            ist_gratis=item.ist_gratis,
        ))
        return

    angebot.zuletzt_gesehen = utcnow()
    angebot.url = item.url
    angebot.preis = item.preis
    angebot.waehrung = item.waehrung
    angebot.preis_eur = preis_eur
    angebot.originalpreis = item.originalpreis
    angebot.rabatt_prozent = item.rabatt_prozent
    angebot.ist_gratis = item.ist_gratis
    if item.haendler:
        angebot.haendler = item.haendler[:128]


def _apply_price(db: Session, deal: Deal, item: DealItem, source_id: str) -> None:
    """Preis eines schon bekannten Deals aktualisieren.

    Es gewinnt der guenstigere Preis - derselbe Artikel taucht bei mehreren
    Quellen zu verschiedenen Preisen auf, und interessant ist der beste.
    Jede echte Aenderung landet in der Historie.

    Wichtig ist, dass Preis, Waehrung, Streichpreis und Rabatt gemeinsam
    umziehen. Frueher wurden nur Preis und Waehrung ersetzt - der alte
    Streichpreis blieb stehen und wurde dann mit dem neuen Waehrungszeichen
    angezeigt: ein EUR-Betrag mit Dollarzeichen davor, und ein Rabatt, der
    zu keinem der beiden Preise mehr passte.
    """
    if item.preis is None:
        return
    neu_eur = to_eur(item.preis, item.waehrung)
    alt_eur = deal.preis_eur if deal.preis_eur is not None else to_eur(deal.preis,
                                                                      deal.waehrung)

    guenstiger = (
        deal.preis is None
        or (neu_eur is not None and alt_eur is not None and neu_eur < alt_eur)
        or (neu_eur is None and item.preis < deal.preis)
    )
    if not guenstiger:
        return

    geaendert = deal.preis != item.preis
    waehrung_wechselt = (deal.waehrung or "EUR") != (item.waehrung or "EUR")

    deal.preis = item.preis
    deal.waehrung = item.waehrung
    deal.preis_eur = neu_eur
    deal.ist_gratis = deal.ist_gratis or item.ist_gratis

    # Streichpreis: der der neuen Quelle, sonst der alte - aber nur, solange
    # die Waehrung dieselbe bleibt und er ueber dem neuen Preis liegt.
    if item.originalpreis is not None and item.originalpreis > item.preis:
        deal.originalpreis = item.originalpreis
    elif waehrung_wechselt or (deal.originalpreis is not None
                               and deal.originalpreis <= item.preis):
        deal.originalpreis = None

    deal.rabatt_prozent = _rabatt(deal.preis, deal.originalpreis,
                                  item.rabatt_prozent, deal.ist_gratis)

    if geaendert:
        db.add(PriceHistory(deal_id=deal.id, preis=item.preis,
                            waehrung=item.waehrung, quelle=source_id))


def _rabatt(preis: float | None, original: float | None,
            gemeldet: float | None, gratis: bool = False) -> float | None:
    """Rabatt, der zu den angezeigten Zahlen passt.

    Wenn ein Streichpreis dasteht, wird der Prozentwert daraus gerechnet -
    ein von der Quelle gemeldeter Rabatt, der gegen eine andere UVP gerechnet
    wurde, waere sonst neben zwei Preisen zu sehen, aus denen er sich nicht
    ergibt. Der gemeldete Wert greift nur, wenn es keinen Streichpreis gibt.
    """
    if gratis:
        return 100.0
    if preis is not None and original and original > preis > 0:
        return round((1 - preis / original) * 100, 1)
    if preis == 0 and original:
        return 100.0
    if original is None and gemeldet is not None and 0 < gemeldet <= 100:
        return round(float(gemeldet), 1)
    return None


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
    )


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
    now = (now or datetime.now(timezone.utc)).astimezone(
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


def _zielkanaele(regeln: list[Rule]) -> list[int]:
    """Vereinigung der Kanaele aller beteiligten Regeln, Reihenfolge stabil."""
    raus: list[int] = []
    for regel in regeln:
        for cid in regel.channels or []:
            if cid not in raus:
                raus.append(cid)
    return raus


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

    for deal, regeln in buendele(hits):
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


async def send_digest(db: Session, http) -> int:
    """Stuendlicher Digest fuer NORMAL-Regeln, deren Treffer wegen Ruhezeit
    oder Prioritaet liegen geblieben sind."""
    pending = list(db.scalars(
        select(Match).where(Match.notified_at.is_(None))
        .order_by(Match.created_at.asc()).limit(200)
    ))
    if not pending:
        return 0
    if in_quiet_hours(db):
        return 0

    rules = {r.id: r for r in db.scalars(select(Rule))}
    hits = [(rules[m.rule_id], m.deal) for m in pending
            if m.rule_id in rules and m.deal is not None]
    return await dispatch(db, hits, http)


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
