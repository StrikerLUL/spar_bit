from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, and_, desc, func, or_, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Deal, Match, Rule, SourceConfig, utcnow
from ..learning import trainiere
from ..search import fts_verfuegbar, match_bedingung
from ..verdict import mindestens

router = APIRouter(prefix="/api", tags=["deals"],
                   dependencies=[Depends(current_user)])


def _deal_dict(d: Deal) -> dict:
    return {
        "id": d.id, "titel": d.titel, "beschreibung": d.beschreibung,
        "url": d.url, "bild": d.bild, "preis": d.preis,
        "originalpreis": d.originalpreis, "rabatt_prozent": d.rabatt_prozent,
        "waehrung": d.waehrung, "ist_gratis": d.ist_gratis,
        "haendler": d.haendler, "kategorie": d.kategorie, "quelle": d.quelle,
        "temperatur": d.temperatur, "tags": d.tags or [],
        "veroeffentlicht_am": d.veroeffentlicht_am, "first_seen": d.first_seen,
        "last_seen": d.last_seen, "seen_count": d.seen_count,
        "also_from": d.also_from or [], "bookmarked": d.bookmarked,
        "preis_eur": d.preis_eur, "bild_lokal": d.bild_lokal,
        "beste_quelle": d.quelle,
        "anzahl_angebote": 1 + len(d.also_from or []),
        "urteil": d.urteil, "urteil_text": d.urteil_text,
    }


@router.get("/deals")
def list_deals(
    q: str | None = None,
    quelle: str | None = None,
    nur_gratis: bool = False,
    min_rabatt: float | None = None,
    max_preis: float | None = None,
    bookmarked: bool = False,
    urteil: str | None = None,
    sortierung: str = "neu",
    limit: int = Query(60, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Deal)
    conditions = []

    if q:
        # Volltextindex bevorzugen; er kennt Phrasen und Ausschluss und
        # muss nicht die ganze Tabelle lesen. Faellt er aus (kein FTS5 in
        # dieser SQLite-Version, kaputte Eingabe), greift LIKE.
        treffer = match_bedingung(q) if fts_verfuegbar(db.get_bind()) else None
        if treffer is not None:
            conditions.append(Deal.id.in_(treffer))
        else:
            like = f"%{q.strip()}%"
            conditions.append(or_(Deal.titel.ilike(like),
                                  Deal.beschreibung.ilike(like),
                                  Deal.haendler.ilike(like)))
    if quelle:
        conditions.append(Deal.quelle == quelle)
    if nur_gratis:
        conditions.append(Deal.ist_gratis.is_(True))
    if min_rabatt is not None:
        conditions.append(Deal.rabatt_prozent >= min_rabatt)
    if max_preis is not None:
        conditions.append(and_(Deal.preis.isnot(None), Deal.preis <= max_preis))
    if bookmarked:
        conditions.append(Deal.bookmarked.is_(True))
    if urteil:
        # "mindestens gut" heisst: gut, sehr gut oder Bestpreis.
        conditions.append(Deal.urteil.in_(mindestens(urteil)))

    if conditions:
        stmt = stmt.where(*conditions)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if sortierung == "fuer_mich":
        return _fuer_mich(db, stmt, total, limit, offset)

    rows = db.scalars(stmt.order_by(desc(Deal.first_seen)).limit(limit).offset(offset))
    return {"total": total, "items": [_deal_dict(d) for d in rows]}


# Wie viele Deals der Empfehlung zur Auswahl stehen. Das Modell rechnet in
# Python, darum wird die Menge begrenzt - es soll die Seite nicht bremsen.
EMPFEHLUNG_POOL = 600
# Ab welcher Punktzahl eine Begruendung gezeigt wird. 0,5 heisst "keine
# Meinung" - darueber muss es deutlich liegen, sonst ist es keine Empfehlung.
PASST_AB = 0.6


def _fuer_mich(db: Session, stmt, total: int, limit: int, offset: int) -> dict:
    """Nach gelerntem Interesse sortieren.

    Faellt zurueck auf "neu zuerst", solange zu wenig gelernt wurde - eine
    Reihenfolge aus drei Beispielen waere geraten, nicht empfohlen.
    """
    modell = trainiere(db)
    kandidaten = list(db.scalars(
        stmt.order_by(desc(Deal.first_seen)).limit(EMPFEHLUNG_POOL)))

    if not modell.bereit:
        seite = kandidaten[offset:offset + limit]
        return {"total": total, "items": [_deal_dict(d) for d in seite],
                "empfehlung_aktiv": False,
                "hinweis": ("Noch zu wenig gelernt — sortiert nach Datum. "
                            "Merk dir ein paar Deals, dann wird daraus eine "
                            "Empfehlung.")}

    bewertet = sorted(((modell.punkte(d), d) for d in kandidaten),
                      key=lambda paar: paar[0], reverse=True)
    seite = bewertet[offset:offset + limit]
    items = []
    for wert, deal in seite:
        eintrag = _deal_dict(deal)
        eintrag["passt_zu_mir"] = round(wert, 3)
        # Begruendung nur, wenn der Deal wirklich passt. Ein Artikel mit
        # 0,04 Punkten steht ganz unten in der Liste - "passt zu dir" waere
        # dort schlicht gelogen, auch wenn einzelne Merkmale dafuer sprechen.
        eintrag["passt_weil"] = modell.gruende(deal) if wert > PASST_AB else []
        items.append(eintrag)
    return {"total": min(total, len(kandidaten)), "items": items,
            "empfehlung_aktiv": True}


@router.post("/deals/{deal_id}/bookmark")
def toggle_bookmark(deal_id: int, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")
    deal.bookmarked = not deal.bookmarked
    db.commit()
    return {"id": deal.id, "bookmarked": deal.bookmarked}


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    now = utcnow()
    today = now - timedelta(hours=24)
    week = now - timedelta(days=7)

    treffer_heute = db.scalar(
        select(func.count()).select_from(Match).where(Match.created_at >= today)) or 0
    deals_heute = db.scalar(
        select(func.count()).select_from(Deal).where(Deal.first_seen >= today)) or 0
    gratis_woche = db.scalar(
        select(func.count()).select_from(Deal)
        .where(Deal.ist_gratis.is_(True), Deal.first_seen >= week)) or 0

    # Gesparter Betrag: nur ueber Deals, die eine Regel getroffen haben -
    # sonst zaehlt man sich an Deals reich, die man nie wollte.
    gespart = db.scalar(
        select(func.coalesce(func.sum(Deal.originalpreis - Deal.preis), 0.0))
        .select_from(Match).join(Deal, Deal.id == Match.deal_id)
        .where(Match.created_at >= week, Deal.originalpreis.isnot(None),
               Deal.preis.isnot(None), Deal.originalpreis > Deal.preis)
    ) or 0.0

    cfgs = list(db.scalars(select(SourceConfig)))
    ampel = {"gruen": 0, "gelb": 0, "rot": 0, "aus": 0}
    for c in cfgs:
        if not c.enabled:
            ampel["aus"] += 1
        elif c.circuit_open_until and c.circuit_open_until > now:
            ampel["rot"] += 1
        elif c.consecutive_failures > 0:
            ampel["gelb"] += 1
        else:
            ampel["gruen"] += 1

    top_quellen = db.execute(
        select(Deal.quelle, func.count(Deal.id)).where(Deal.first_seen >= week)
        .group_by(Deal.quelle).order_by(desc(func.count(Deal.id))).limit(8)
    ).all()

    return {
        "treffer_heute": treffer_heute,
        "deals_heute": deals_heute,
        "gratis_diese_woche": gratis_woche,
        "gesparter_betrag": round(float(gespart), 2),
        "deals_gesamt": db.scalar(select(func.count()).select_from(Deal)) or 0,
        "quellen_ampel": ampel,
        "aktive_regeln": db.scalar(
            select(func.count()).select_from(Rule).where(Rule.enabled.is_(True))) or 0,
        "top_quellen": [{"quelle": q, "anzahl": n} for q, n in top_quellen],
    }


@router.get("/matches")
def list_matches(limit: int = Query(50, le=200), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Match, Rule.name).join(Rule, Rule.id == Match.rule_id)
        .order_by(desc(Match.created_at)).limit(limit)
    ).all()
    out = []
    for match, rule_name in rows:
        if match.deal is None:
            continue
        out.append({"regel": rule_name, "created_at": match.created_at,
                    "notified_at": match.notified_at, **_deal_dict(match.deal)})
    return out
