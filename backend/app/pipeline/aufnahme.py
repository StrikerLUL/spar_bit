"""Von der Quelle in die Datenbank: Dedupe, Preis, Angebote.

Der erste Teil des Weges, den ein Deal geht. Was danach kommt - Regeln
und Versand - steht in regeln.py und versand.py.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import erwachsen as erwachsen_mod
from ..currency import to_eur
from ..dedupe import normalize_title, titles_match, url_hash
from ..events import broker
from ..models import Deal, DealOffer, PriceHistory, utcnow
from ..produktid import fuer_deal
from ..sources.base import DealItem
from .gemeinsam import _deal_payload

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

    item = _entwirre_gratis(item)
    uhash = url_hash(item.url)

    # 1) Exaktes URL-Duplikat -> nur "wieder gesehen" vermerken.
    existing = db.scalar(select(Deal).where(Deal.url_hash == uhash))
    if existing:
        existing.last_seen = utcnow()
        existing.seen_count += 1
        erwachsen_mod.markiere(existing, source_id=source_id)
        _merke_angebot(db, existing, item, source_id)
        _apply_price(db, existing, item, source_id)
        if source_id not in (existing.also_from or []) and source_id != existing.quelle:
            existing.also_from = list(existing.also_from or []) + [source_id]
        return None

    titel_norm = normalize_title(item.titel)
    kennung = fuer_deal(item.url, item.roh)

    # 2) Gleiche Produktkennung -> derselbe Artikel, ohne Raten.
    #
    # Steht vor dem Titelvergleich, weil sie ihn schlaegt: "Sony
    # WH-1000XM5 Schwarz" und "Sony Kopfhoerer WH1000XM5, schwarz" sind
    # fuer jeden Schwellenwert ein Grenzfall - fuer dieselbe ASIN nicht.
    # Und sie gilt ohne Zeitfenster: die Kandidatenliste reicht 72 Stunden
    # zurueck, eine Kennung findet den Artikel auch danach noch.
    if kennung:
        treffer = db.scalar(
            select(Deal).where(Deal.produkt_id == kennung,
                               Deal.duplicate_of.is_(None))
            .order_by(Deal.first_seen.desc()).limit(1))
        if treffer is not None:
            treffer.last_seen = utcnow()
            treffer.seen_count += 1
            erwachsen_mod.markiere(treffer, source_id=source_id)
            if source_id not in (treffer.also_from or []) and source_id != treffer.quelle:
                treffer.also_from = list(treffer.also_from or []) + [source_id]
            _merke_angebot(db, treffer, item, source_id)
            _apply_price(db, treffer, item, source_id)
            log.debug("Produktkennung %s: '%s' (%s) gehoert zu '%s'",
                      kennung, item.titel[:50], source_id, treffer.titel[:50])
            return None

    # 3) Fuzzy-Duplikat ueber Quellen hinweg.
    for cand in recent:
        # Zwei verschiedene Kennungen heissen: verschiedene Artikel. Dann
        # braucht der Titel gar nicht erst befragt zu werden - "iPhone 15
        # 128 GB" und "iPhone 15 256 GB" heissen fast gleich.
        if kennung and cand.produkt_id and cand.produkt_id != kennung:
            continue
        if cand.titel_norm and titles_match(item.titel, cand.titel):
            # Gleicher Titel, andere URL -> derselbe Deal aus anderer Quelle.
            cand.last_seen = utcnow()
            cand.seen_count += 1
            erwachsen_mod.markiere(cand, source_id=source_id)
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
        produkt_id=kennung,
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
        gratis_hinweis=(item.roh or {}).get("gratis_hinweis"),
        roh=item.roh or {},
    )
    erwachsen_mod.markiere(deal, source_id=source_id)
    db.add(deal)
    db.flush()
    _merke_angebot(db, deal, item, source_id)
    if deal.preis is not None:
        db.add(PriceHistory(deal_id=deal.id, preis=deal.preis,
                            waehrung=deal.waehrung, quelle=source_id))
    return deal


def _entwirre_gratis(item: DealItem) -> DealItem:
    """Letzte Instanz gegen falsche Gratis-Meldungen.

    `priceparse` faengt den haeufigsten Fall schon im Text ab ("gratis
    Versand"). Hier geht es um den Rest: eine Quelle, die `ist_gratis`
    meldet und im selben Atemzug einen Preis ueber null nennt. Beides kann
    nicht stimmen, und die Zahl ist die konkretere Angabe - ein Flag kann
    aus einer Kategorie ("Freebies") stammen, ein Preis nicht.

    Das greift quellenuebergreifend, auch bei API-Quellen, die ihren
    Gratis-Status nicht aus Text ableiten.
    """
    if not item.ist_gratis or item.preis is None or item.preis <= 0.009:
        return item
    roh = dict(item.roh or {})
    roh["gratis_hinweis"] = "Quelle meldete gratis trotz Preis"
    roh["gratis_laut_quelle"] = True
    return item.model_copy(update={
        "ist_gratis": False,
        "rabatt_prozent": None if (item.rabatt_prozent or 0) >= 99.5
                          else item.rabatt_prozent,
        "roh": roh,
    })


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


