from __future__ import annotations

import asyncio
import json
import platform
import sys
from datetime import datetime, timezone

from fastapi import (APIRouter, Depends, Header, HTTPException, Query,
                     Request)
from pydantic import BaseModel
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..events import broker
from ..logging_setup import recent_logs
from .. import updater
from ..models import (Channel, ClaimEvent, Deal, Match, NotificationLog, Rule,
                      SourceConfig, SourceRun)
from .. import claimer as claimer_mod

router = APIRouter(prefix="/api/system", tags=["system"],
                   dependencies=[Depends(current_user)])

STARTED_AT = datetime.now(timezone.utc)


@router.get("/info")
def info(db: Session = Depends(get_db)) -> dict:
    db_bytes = settings.db_path.stat().st_size if settings.db_path.exists() else 0
    wal = settings.db_path.with_suffix(".db-wal")
    if wal.exists():
        db_bytes += wal.stat().st_size
    return {
        "version": "1.0.0",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "gestartet": STARTED_AT,
        "laufzeit_sekunden": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "db_pfad": str(settings.db_path),
        "db_groesse_bytes": db_bytes,
        "db_groesse_mb": round(db_bytes / 1024 / 1024, 2),
        "sse_clients": broker.subscriber_count,
        "zeilen": {
            "deals": db.scalar(select(func.count()).select_from(Deal)) or 0,
            "matches": db.scalar(select(func.count()).select_from(Match)) or 0,
            "regeln": db.scalar(select(func.count()).select_from(Rule)) or 0,
            "kanaele": db.scalar(select(func.count()).select_from(Channel)) or 0,
            "quellen": db.scalar(select(func.count()).select_from(SourceConfig)) or 0,
            "laeufe": db.scalar(select(func.count()).select_from(SourceRun)) or 0,
            "claims": db.scalar(select(func.count()).select_from(ClaimEvent)) or 0,
        },
    }


@router.get("/logs")
def logs(limit: int = Query(300, le=2000), level: str = "ALL") -> list[dict]:
    return recent_logs(limit, level)


@router.get("/backup")
def backup(db: Session = Depends(get_db)) -> JSONResponse:
    """Vollstaendiger JSON-Export. API-Keys und Kanal-Secrets bleiben drin -
    das ist ein Backup, kein Teilen-Export. Datei entsprechend behandeln."""
    def rows(model, fields):
        return [{f: getattr(r, f) for f in fields} for r in db.scalars(select(model))]

    data = {
        "exportiert_am": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "regeln": rows(Rule, ["id", "name", "enabled", "priority", "keywords",
                              "required_keywords", "blacklist", "max_preis",
                              "min_rabatt_prozent", "nur_gratis", "min_temperatur",
                              "sources", "kategorien", "haendler", "channels"]),
        "kanaele": rows(Channel, ["id", "type", "name", "enabled", "config"]),
        "quellen": rows(SourceConfig, ["id", "enabled", "interval_seconds",
                                       "api_key", "options", "verification"]),
        "deals": rows(Deal, ["id", "titel", "url", "preis", "originalpreis",
                             "rabatt_prozent", "waehrung", "ist_gratis",
                             "haendler", "quelle", "first_seen", "bookmarked"]),
        "claims": rows(ClaimEvent, ["platform", "titel", "status", "seen_at"]),
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return JSONResponse(
        content=json.loads(json.dumps(data, default=str)),
        headers={"Content-Disposition": f'attachment; filename="sparbit-backup-{stamp}.json"'},
    )


# --- Updates ---------------------------------------------------------------

class UpdateAuto(BaseModel):
    auto: bool


@router.get("/update")
def update_status(db: Session = Depends(get_db)) -> dict:
    return updater.status(db)


@router.post("/update")
def update_anfordern(db: Session = Depends(get_db)) -> dict:
    """Bittet den Host-Updater, beim naechsten Lauf zu aktualisieren."""
    try:
        return updater.fordere_an(db)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/update/auto")
def update_auto(body: UpdateAuto, db: Session = Depends(get_db)) -> dict:
    try:
        return updater.setze_auto(db, body.auto)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


# Die beiden folgenden Endpunkte gehoeren dem Host-Skript, nicht dem Browser.
# Sie haengen darum nicht an der Sitzung, sondern am gemeinsamen Token -
# eine Sitzung hat ein systemd-Timer nicht.
host_router = APIRouter(prefix="/api/system/update", tags=["system"])


def _pruefe_token(x_sparbit_update: str = Header(default="")) -> None:
    if not updater.token_stimmt(x_sparbit_update):
        raise HTTPException(403, "Ungültiges Update-Token")


@host_router.get("/auftrag", dependencies=[Depends(_pruefe_token)])
def update_auftrag(db: Session = Depends(get_db)) -> dict:
    return updater.hole_auftrag(db)


@host_router.post("/bericht", dependencies=[Depends(_pruefe_token)])
def update_bericht(bericht: dict, db: Session = Depends(get_db)) -> dict:
    return updater.nimm_bericht(db, bericht)


# --- SSE ------------------------------------------------------------------

sse_router = APIRouter(prefix="/api", tags=["system"])


@sse_router.get("/events")
async def events(request: Request, _user=Depends(current_user)) -> StreamingResponse:
    """Live-Ticker. Ein Heartbeat alle 20s haelt Proxys davon ab, zu kappen."""
    queue = broker.subscribe()

    async def stream():
        try:
            yield "retry: 3000\n\n"
            yield f"event: hello\ndata: {json.dumps({'ok': True})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                event = json.loads(payload)
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], default=str)}\n\n"
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


# --- Claimer --------------------------------------------------------------

claimer_router = APIRouter(prefix="/api/claimer", tags=["claimer"],
                           dependencies=[Depends(current_user)])


@claimer_router.get("/status")
def claimer_status(db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import desc
    events = db.scalars(select(ClaimEvent).order_by(desc(ClaimEvent.seen_at)).limit(50))
    items = [{"platform": e.platform, "titel": e.titel, "status": e.status,
              "seen_at": e.seen_at, "detail": e.detail} for e in events]
    return {**claimer_mod.status(),
            "geclaimt_gesamt": db.scalar(
                select(func.count()).select_from(ClaimEvent)
                .where(ClaimEvent.status == "claimed")) or 0,
            "ereignisse": items}


@claimer_router.get("/log")
def claimer_log(lines: int = Query(300, le=2000)) -> dict:
    return {"log": claimer_mod.read_tail(lines)}


@claimer_router.post("/scan")
def claimer_scan() -> dict:
    return {"neue_ereignisse": claimer_mod.scan_job()}
