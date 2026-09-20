from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from .. import erwachsen as erwachsen_mod
from ..db import get_db
from ..models import SourceConfig, SourceRun, User, utcnow
from ..scheduler import build_context, run_source, schedule_source
from ..sources import all_sources, get_source

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sources", tags=["sources"],
                   dependencies=[Depends(current_user)])


class FeedSuche(BaseModel):
    url: str


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None
    api_key: str | None = None
    options: dict | None = None


def _serialize(src, cfg: SourceConfig, stats: dict) -> dict:
    return {
        "id": src.id,
        "display_name": src.display_name,
        "category": src.category.value,
        "beschreibung": src.beschreibung,
        "docs_url": src.docs_url,
        "requires_api_key": src.requires_api_key,
        "api_key_url": src.api_key_url,
        "experimental": src.experimental,
        "erwachsen": src.category.value == "erwachsen",
        "default_interval": src.default_interval,
        "min_interval": src.min_interval,
        "options_schema": [asdict(o) for o in src.options_schema],
        # Laufzeit
        "enabled": cfg.enabled,
        "interval_seconds": cfg.interval_seconds,
        "has_api_key": bool(cfg.api_key),
        "options": cfg.options or {},
        "verification": cfg.verification,
        "last_verified": cfg.last_verified,
        "last_run": cfg.last_run,
        "last_success": cfg.last_success,
        "last_error": cfg.last_error,
        "consecutive_failures": cfg.consecutive_failures,
        "circuit_open_until": cfg.circuit_open_until,
        "circuit_open": bool(cfg.circuit_open_until and cfg.circuit_open_until > utcnow()),
        "snooze_until": cfg.snooze_until,
        "total_runs": cfg.total_runs,
        "total_errors": cfg.total_errors,
        "total_items": cfg.total_items,
        "fehlerquote": round(cfg.total_errors / cfg.total_runs * 100, 1) if cfg.total_runs else 0.0,
        **stats,
    }


@router.get("")
def list_sources(db: Session = Depends(get_db)) -> list[dict]:
    cfgs = {c.id: c for c in db.scalars(select(SourceConfig))}
    # Letzte 20 Laeufe je Quelle fuer den Sparkline-Verlauf.
    runs = db.execute(
        select(SourceRun.source_id, func.count(SourceRun.id), func.avg(SourceRun.duration_ms))
        .where(SourceRun.started_at >= utcnow().replace(microsecond=0))
        .group_by(SourceRun.source_id)
    ).all()
    avg_map = {r[0]: int(r[2] or 0) for r in runs}

    # Solange der 18+-Bereich zu ist, gibt es diese Quellen hier nicht -
    # weder sichtbar noch schaltbar. Ihre Config-Zeilen bleiben bestehen,
    # damit Einstellungen ein Aus- und Wiedereinschalten ueberleben.
    frei = erwachsen_mod.ist_aktiv(db)

    out = []
    for src in all_sources():
        if src.category.value == "erwachsen" and not frei:
            continue
        cfg = cfgs.get(src.id)
        if cfg is None:
            cfg = SourceConfig(id=src.id, enabled=False,
                               interval_seconds=src.default_interval,
                               options=dict(src.default_options),
                               verification=src.verification.value)
            db.add(cfg)
            db.commit()
        out.append(_serialize(src, cfg, {"avg_duration_ms": avg_map.get(src.id, 0)}))
    return out


@router.post("/feed-suche")
async def feed_suche(body: FeedSuche) -> dict:
    """Welche Feeds zeichnet diese Adresse aus?

    Der Ausweg aus dem Pfad-Raten: statt zu wissen, wie ein Shop seinen
    Feed nennt, fragt man ihn. Ergebnis sind die Adressen, die die Seite
    selbst angibt - direkt in ein Feed-Feld kopierbar.
    """
    from .. import feedfinder

    url = (body.url or "").strip()
    if not url:
        raise HTTPException(400, "Keine Adresse angegeben.")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return await feedfinder.suche(build_context(
        SourceConfig(id="_suche", options={})).http, url)


def _pruefe_frei(db: Session, source_id: str) -> None:
    """403 fuer 18+-Quellen, solange der Bereich nicht freigeschaltet ist.

    Der Filter in der Liste allein reicht nicht: wer die ID kennt, koennte
    sonst per PATCH an der Sperre vorbei einschalten.
    """
    if erwachsen_mod.quelle_ist_18(source_id) and not erwachsen_mod.ist_aktiv(db):
        raise HTTPException(
            403, "Der 18+-Bereich ist nicht freigeschaltet "
                 "(Logs & System → 18+-Bereich).")


@router.get("/{source_id}/runs")
def source_runs(source_id: str, limit: int = 30,
                db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(SourceRun).where(SourceRun.source_id == source_id)
        .order_by(desc(SourceRun.started_at)).limit(min(limit, 100))
    )
    return [{"started_at": r.started_at, "ok": r.ok, "items": r.items,
             "new_items": r.new_items, "duration_ms": r.duration_ms,
             "error": r.error} for r in rows]


@router.patch("/{source_id}")
def update_source(source_id: str, body: SourceUpdate,
                  db: Session = Depends(get_db)) -> dict:
    src = get_source(source_id)
    cfg = db.get(SourceConfig, source_id)
    if src is None or cfg is None:
        raise HTTPException(404, "Quelle unbekannt")
    _pruefe_frei(db, source_id)

    if body.enabled is not None:
        cfg.enabled = body.enabled
        if body.enabled:
            # Neustart-Chance nach manuellem Einschalten.
            cfg.consecutive_failures = 0
            cfg.circuit_open_until = None
    if body.interval_seconds is not None:
        cfg.interval_seconds = max(int(body.interval_seconds), src.min_interval)
    if body.api_key is not None:
        cfg.api_key = body.api_key.strip() or None
    if body.options is not None:
        cfg.options = {**(cfg.options or {}), **body.options}

    db.commit()
    db.refresh(cfg)
    schedule_source(cfg)
    return _serialize(src, cfg, {})


@router.post("/{source_id}/test")
async def test_source(source_id: str, db: Session = Depends(get_db)) -> dict:
    """'Jetzt testen' - health_check mit Live-Ergebnis, ohne zu speichern."""
    src = get_source(source_id)
    cfg = db.get(SourceConfig, source_id)
    if src is None or cfg is None:
        raise HTTPException(404, "Quelle unbekannt")
    _pruefe_frei(db, source_id)

    result = await src.health_check(build_context(cfg))

    cfg.verification = "verified" if result.ok else "broken"
    cfg.last_verified = utcnow()
    if not result.ok:
        cfg.last_error = result.detail
    db.commit()

    return {
        "ok": result.ok,
        "detail": result.detail,
        "items_found": result.items_found,
        "latency_ms": result.latency_ms,
        "samples": [s.model_dump(mode="json") for s in result.samples],
    }


@router.post("/{source_id}/run")
async def run_now(source_id: str, db: Session = Depends(get_db)) -> dict:
    if get_source(source_id) is None:
        raise HTTPException(404, "Quelle unbekannt")
    _pruefe_frei(db, source_id)
    return await run_source(source_id, manual=True)


@router.post("/{source_id}/reset")
def reset_breaker(source_id: str, db: Session = Depends(get_db)) -> dict:
    cfg = db.get(SourceConfig, source_id)
    if cfg is None:
        raise HTTPException(404, "Quelle unbekannt")
    cfg.consecutive_failures = 0
    cfg.circuit_open_until = None
    cfg.last_error = None
    db.commit()
    return {"ok": True}
