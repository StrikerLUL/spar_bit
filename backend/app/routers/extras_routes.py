"""Zusatzfunktionen: Statistiken, Deal-Detail, Preisalarme, Export/Import."""
from __future__ import annotations

import csv
import io
import json
import logging
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..images import aufraeumen as bilder_aufraeumen
from ..images import bild_verzeichnis, statistik as bild_statistik
from ..currency import DEFAULT_RATES, get_rates, set_rates, to_eur
from ..db import get_db, get_setting, set_setting
from ..models import (Channel, Deal, DealOffer, Match, PriceHistory, Rule,
                      SavedSearch, SourceConfig, utcnow)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["extras"],
                   dependencies=[Depends(current_user)])


# --- Bilder ----------------------------------------------------------------
# Eigener Router ohne Login-Pflicht: das <img>-Tag im Browser schickt zwar das
# Cookie mit, aber ein 401 auf ein Bild waere nur ein kaputtes Bild ohne
# erkennbaren Grund. Ausgeliefert werden ausschliesslich Dateien aus dem
# eigenen Cache-Verzeichnis, benannt nach einem Hash - erraten kann man die
# nicht, und Deal-Bilder sind ohnehin oeffentliche Produktfotos.

bilder_router = APIRouter(prefix="/api/bilder", tags=["bilder"])


@bilder_router.get("/{datei}")
def bild_ausliefern(datei: str):
    from fastapi.responses import FileResponse, Response

    verzeichnis = bild_verzeichnis().resolve()
    ziel = (verzeichnis / datei).resolve()
    # Kein Ausbrechen aus dem Verzeichnis ueber ".." im Dateinamen.
    if not ziel.is_relative_to(verzeichnis) or not ziel.is_file():
        # 1x1-Platzhalter statt 404: eine kaputte Karte sieht schlimmer aus
        # als ein leeres Bild, und das Frontend blendet es ohnehin aus.
        return Response(status_code=404)
    return FileResponse(ziel, headers={"Cache-Control": "public, max-age=604800"})


# --- Statistiken -----------------------------------------------------------

@router.get("/stats/timeline")
def timeline(tage: int = Query(30, ge=7, le=180),
             db: Session = Depends(get_db)) -> dict:
    """Deals, Gratis-Funde und Treffer je Tag - fuer die Diagramme."""
    seit = utcnow() - timedelta(days=tage)

    deals = db.execute(
        select(func.date(Deal.first_seen), func.count(Deal.id),
               func.sum(func.cast(Deal.ist_gratis, func.count(Deal.id).type)))
        .where(Deal.first_seen >= seit).group_by(func.date(Deal.first_seen))
    ).all()

    treffer = db.execute(
        select(func.date(Match.created_at), func.count(Match.id))
        .where(Match.created_at >= seit).group_by(func.date(Match.created_at))
    ).all()
    treffer_map = {str(row[0]): row[1] for row in treffer}

    ersparnis = db.execute(
        select(func.date(Deal.first_seen),
               func.sum(Deal.originalpreis - Deal.preis))
        .where(Deal.first_seen >= seit, Deal.originalpreis.isnot(None),
               Deal.preis.isnot(None), Deal.originalpreis > Deal.preis)
        .group_by(func.date(Deal.first_seen))
    ).all()
    ersparnis_map = {str(row[0]): float(row[1] or 0) for row in ersparnis}

    deal_map = {str(row[0]): (row[1], int(row[2] or 0)) for row in deals}

    # Luecken auffuellen, damit die Kurve keine Spruenge macht.
    heute = date.today()
    punkte = []
    for offset in range(tage - 1, -1, -1):
        tag = str(heute - timedelta(days=offset))
        anzahl, gratis = deal_map.get(tag, (0, 0))
        punkte.append({
            "tag": tag,
            "deals": anzahl,
            "gratis": gratis,
            "treffer": treffer_map.get(tag, 0),
            "ersparnis": round(ersparnis_map.get(tag, 0.0), 2),
        })
    return {"tage": tage, "punkte": punkte}


@router.get("/stats/quellen")
def quellen_stats(tage: int = Query(30, ge=1, le=180),
                  db: Session = Depends(get_db)) -> list[dict]:
    """Je Quelle: wie viel kommt rein, wie viel davon ist wirklich relevant."""
    seit = utcnow() - timedelta(days=tage)

    gesamt = dict(db.execute(
        select(Deal.quelle, func.count(Deal.id))
        .where(Deal.first_seen >= seit).group_by(Deal.quelle)).all())
    gratis = dict(db.execute(
        select(Deal.quelle, func.count(Deal.id))
        .where(Deal.first_seen >= seit, Deal.ist_gratis.is_(True))
        .group_by(Deal.quelle)).all())
    getroffen = dict(db.execute(
        select(Deal.quelle, func.count(func.distinct(Match.deal_id)))
        .join(Match, Match.deal_id == Deal.id)
        .where(Match.created_at >= seit).group_by(Deal.quelle)).all())

    out = []
    for quelle, anzahl in sorted(gesamt.items(), key=lambda kv: -kv[1]):
        treffer = getroffen.get(quelle, 0)
        out.append({
            "quelle": quelle,
            "deals": anzahl,
            "gratis": gratis.get(quelle, 0),
            "treffer": treffer,
            # Signalanteil: wie viel Prozent des Rauschens war brauchbar.
            "signalquote": round(treffer / anzahl * 100, 1) if anzahl else 0.0,
        })
    return out


@router.get("/stats/haendler")
def haendler_stats(limit: int = Query(12, le=50),
                   db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Deal.haendler, func.count(Deal.id),
               func.avg(Deal.rabatt_prozent))
        .where(Deal.haendler.isnot(None), Deal.haendler != "")
        .group_by(Deal.haendler).order_by(desc(func.count(Deal.id))).limit(limit)
    ).all()
    return [{"haendler": r[0], "anzahl": r[1],
             "schnitt_rabatt": round(float(r[2] or 0), 1)} for r in rows]


# --- Deal-Detail und Preisverlauf -----------------------------------------

@router.get("/deals/{deal_id}/detail")
def deal_detail(deal_id: int, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")

    verlauf = db.scalars(
        select(PriceHistory).where(PriceHistory.deal_id == deal_id)
        .order_by(PriceHistory.ts.asc()).limit(200))
    # Der Verlauf kann Waehrungen mischen (erst EUR von mydealz, dann USD von
    # CheapShark). Fuer Kurve und Tiefst-/Hoechstwert zaehlt darum der
    # Euro-Betrag - sonst entsteht beim Waehrungswechsel ein Sprung, den es
    # nie gegeben hat, und die Beschriftung waere schlicht falsch.
    punkte = [{"ts": p.ts, "preis": p.preis, "waehrung": p.waehrung,
               "preis_eur": to_eur(p.preis, p.waehrung), "quelle": p.quelle}
              for p in verlauf]

    regeln = db.execute(
        select(Rule.name, Match.created_at).join(Match, Match.rule_id == Rule.id)
        .where(Match.deal_id == deal_id)).all()

    angebote = sorted(
        db.scalars(select(DealOffer).where(DealOffer.deal_id == deal_id)),
        # Guenstigster zuerst; Angebote ohne erkannten Preis ans Ende.
        key=lambda a: (a.preis_eur if a.preis_eur is not None
                       else (a.preis if a.preis is not None else float("inf"))),
    )

    preise_eur = [p["preis_eur"] for p in punkte if p["preis_eur"] is not None]
    return {
        "id": deal.id, "titel": deal.titel, "beschreibung": deal.beschreibung,
        "url": deal.url, "bild": deal.bild, "bild_lokal": deal.bild_lokal,
        "preis": deal.preis,
        "preis_eur": deal.preis_eur, "originalpreis": deal.originalpreis,
        "rabatt_prozent": deal.rabatt_prozent, "waehrung": deal.waehrung,
        "ist_gratis": deal.ist_gratis, "haendler": deal.haendler,
        "quelle": deal.quelle, "also_from": deal.also_from or [],
        "temperatur": deal.temperatur, "tags": deal.tags or [],
        "first_seen": deal.first_seen, "last_seen": deal.last_seen,
        "seen_count": deal.seen_count, "bookmarked": deal.bookmarked,
        "alarm_preis": deal.alarm_preis, "alarm_ausgeloest": deal.alarm_ausgeloest,
        "notiz": deal.notiz,
        "verlauf": punkte,
        "tiefstpreis": min(preise_eur) if preise_eur else None,
        "hoechstpreis": max(preise_eur) if preise_eur else None,
        # Bestes Angebot: darauf bezieht sich der grosse Preis oben.
        "beste_quelle": angebote[0].quelle if angebote else deal.quelle,
        "beste_url": angebote[0].url if angebote else deal.url,
        "regeltreffer": [{"regel": r[0], "wann": r[1]} for r in regeln],
        "angebote": [{
            "quelle": a.quelle, "url": a.url, "preis": a.preis,
            "waehrung": a.waehrung, "preis_eur": a.preis_eur,
            "originalpreis": a.originalpreis, "rabatt_prozent": a.rabatt_prozent,
            "haendler": a.haendler, "ist_gratis": a.ist_gratis,
            "zuletzt_gesehen": a.zuletzt_gesehen,
        } for a in angebote],
    }


class AlarmBody(BaseModel):
    ziel_preis: float | None = Field(None, ge=0)
    notiz: str | None = None


@router.put("/deals/{deal_id}/alarm")
def set_alarm(deal_id: int, body: AlarmBody, db: Session = Depends(get_db)) -> dict:
    """Preisalarm setzen oder (mit ziel_preis=null) wieder entfernen."""
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")
    deal.alarm_preis = body.ziel_preis
    deal.alarm_ausgeloest = None      # neuer Alarm darf wieder ausloesen
    if body.notiz is not None:
        deal.notiz = body.notiz or None
    db.commit()
    return {"id": deal.id, "alarm_preis": deal.alarm_preis, "notiz": deal.notiz}


# --- Export / Import -------------------------------------------------------

@router.get("/deals/export.csv")
def export_csv(nur_gratis: bool = False, nur_gemerkt: bool = False,
               limit: int = Query(5000, le=50000),
               db: Session = Depends(get_db)) -> StreamingResponse:
    stmt = select(Deal).order_by(desc(Deal.first_seen)).limit(limit)
    if nur_gratis:
        stmt = stmt.where(Deal.ist_gratis.is_(True))
    if nur_gemerkt:
        stmt = stmt.where(Deal.bookmarked.is_(True))

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")     # Semikolon: Excel-DE-freundlich
    writer.writerow(["Titel", "Preis", "Waehrung", "Preis EUR", "Originalpreis",
                     "Rabatt %", "Gratis", "Haendler", "Quelle", "Temperatur",
                     "Gefunden am", "URL"])
    for deal in db.scalars(stmt):
        writer.writerow([
            deal.titel, deal.preis if deal.preis is not None else "", deal.waehrung,
            deal.preis_eur if deal.preis_eur is not None else "",
            deal.originalpreis if deal.originalpreis is not None else "",
            round(deal.rabatt_prozent) if deal.rabatt_prozent else "",
            "ja" if deal.ist_gratis else "nein", deal.haendler or "", deal.quelle,
            round(deal.temperatur) if deal.temperatur else "",
            deal.first_seen.strftime("%Y-%m-%d %H:%M") if deal.first_seen else "",
            deal.url,
        ])
    buffer.seek(0)
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8-sig")]),   # BOM fuer Excel
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sparbit-{stamp}.csv"'},
    )


@router.post("/system/restore")
def restore(payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    """Backup einspielen. Regeln, Kanaele und Quellen-Konfiguration werden
    ersetzt; gesammelte Deals bleiben unangetastet - die kommen ohnehin
    wieder rein."""
    if not isinstance(payload, dict) or "version" not in payload:
        raise HTTPException(400, "Das sieht nicht nach einem SparBit-Backup aus.")

    bericht = {"regeln": 0, "kanaele": 0, "quellen": 0}

    if isinstance(payload.get("regeln"), list):
        db.query(Rule).delete()
        for row in payload["regeln"]:
            row = {k: v for k, v in row.items() if k != "id"}
            db.add(Rule(**row))
            bericht["regeln"] += 1

    if isinstance(payload.get("kanaele"), list):
        db.query(Channel).delete()
        for row in payload["kanaele"]:
            row = {k: v for k, v in row.items() if k != "id"}
            db.add(Channel(**row))
            bericht["kanaele"] += 1

    if isinstance(payload.get("quellen"), list):
        for row in payload["quellen"]:
            cfg = db.get(SourceConfig, row.get("id"))
            if cfg is None:
                continue      # Quelle gibt es in dieser Version nicht mehr
            for key in ("enabled", "interval_seconds", "api_key", "options",
                        "verification"):
                if key in row:
                    setattr(cfg, key, row[key])
            bericht["quellen"] += 1

    db.commit()
    log.info("Backup eingespielt: %s", bericht)
    return {"ok": True, **bericht}


# --- Gespeicherte Suchen ---------------------------------------------------

class SavedSearchBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    filter: dict = {}


@router.get("/searches")
def list_searches(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": s.id, "name": s.name, "filter": s.filter}
            for s in db.scalars(select(SavedSearch).order_by(SavedSearch.id))]


@router.post("/searches")
def create_search(body: SavedSearchBody, db: Session = Depends(get_db)) -> dict:
    row = SavedSearch(name=body.name, filter=body.filter)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "filter": row.filter}


@router.delete("/searches/{search_id}")
def delete_search(search_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(SavedSearch, search_id)
    if row is None:
        raise HTTPException(404, "Suche nicht gefunden")
    db.delete(row)
    db.commit()
    return {"ok": True}


# --- Allgemeine Einstellungen ---------------------------------------------

class GeneralSettings(BaseModel):
    waehrungskurse: dict[str, float] = {}
    benachrichtigungen_pausiert: bool = False


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict:
    return {
        "waehrungskurse": get_setting(db, "currency_rates") or DEFAULT_RATES,
        "aktive_kurse": get_rates(),
        "benachrichtigungen_pausiert": bool(get_setting(db, "notifications_paused")),
    }


@router.put("/settings")
def put_settings(body: GeneralSettings, db: Session = Depends(get_db)) -> dict:
    set_setting(db, "currency_rates", body.waehrungskurse)
    set_setting(db, "notifications_paused", body.benachrichtigungen_pausiert)
    db.commit()
    set_rates(body.waehrungskurse)
    return get_settings(db)


@router.get("/bilder-status")
def bilder_status(db: Session = Depends(get_db)) -> dict:
    return {**bild_statistik(db),
            "aktiv": get_setting(db, "bilder_lokal", True)}


@router.post("/bilder-aufraeumen")
def bilder_putzen(db: Session = Depends(get_db)) -> dict:
    return {"entfernt": bilder_aufraeumen(db)}


@router.post("/sources/{source_id}/snooze")
def snooze_source(source_id: str, stunden: float = Query(6, ge=0, le=168),
                  db: Session = Depends(get_db)) -> dict:
    cfg = db.get(SourceConfig, source_id)
    if cfg is None:
        raise HTTPException(404, "Quelle unbekannt")
    cfg.snooze_until = (utcnow() + timedelta(hours=stunden)) if stunden else None
    db.commit()
    return {"id": source_id, "snooze_until": cfg.snooze_until}
