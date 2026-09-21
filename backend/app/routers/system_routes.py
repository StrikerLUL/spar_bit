from __future__ import annotations

import asyncio
import json
import platform
import sys
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import backup as backup_mod
from .. import claimer as claimer_mod
from .. import erwachsen as erwachsen_mod
from .. import gratischeck, updater
from ..auth import current_user
from ..config import settings
from ..db import get_db, get_setting, set_setting
from ..events import broker
from ..logging_setup import recent_logs
from ..models import (
    Channel,
    ClaimEvent,
    Deal,
    Match,
    Rule,
    SourceConfig,
    SourceRun,
)

router = APIRouter(prefix="/api/system", tags=["system"],
                   dependencies=[Depends(current_user)])

STARTED_AT = datetime.now(UTC)


@router.get("/info")
def info(db: Session = Depends(get_db)) -> dict:
    db_bytes = settings.db_path.stat().st_size if settings.db_path.exists() else 0
    wal = settings.db_path.with_suffix(".db-wal")
    if wal.exists():
        db_bytes += wal.stat().st_size
    from .. import migrations
    from ..db import engine

    return {
        "version": "1.0.0",
        "python": sys.version.split()[0],
        # Damit sichtbar ist, auf welchem Stand diese Datenbank steht -
        # vorher liess sich das nur am Vorhandensein einzelner Spalten raten.
        "schema_stand": migrations.version(engine),
        "schema_neuester": migrations.neuester_stand(),
        "platform": platform.platform(),
        "gestartet": STARTED_AT,
        "laufzeit_sekunden": int((datetime.now(UTC) - STARTED_AT).total_seconds()),
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
def backup(umfang: str = Query("voll", pattern="^(voll|einstellungen)$"),
           db: Session = Depends(get_db)) -> JSONResponse:
    """Vollstaendige Sicherung als JSON.

    Enthaelt API-Schluessel, Kanal-Geheimnisse und Passwort-Hashes - das
    ist eine Sicherung, kein Teilen-Export. Wer sie aus der Hand gibt,
    nimmt den Weg ueber POST /api/system/backup mit Passwort.
    """
    daten = backup_mod.erstelle(db, umfang=umfang)
    stempel = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return JSONResponse(
        content=json.loads(backup_mod.als_json(daten)),
        headers={"Content-Disposition":
                 f'attachment; filename="sparbit-backup-{stempel}.json"'},
    )


class BackupWunsch(BaseModel):
    umfang: str = "voll"
    passwort: str = ""


@router.post("/backup")
def backup_verschluesselt(body: BackupWunsch,
                          db: Session = Depends(get_db)) -> JSONResponse:
    """Sicherung mit Passwort. Ohne Passwort dasselbe wie GET."""
    umfang = body.umfang if body.umfang in ("voll", "einstellungen") else "voll"
    daten = backup_mod.erstelle(db, umfang=umfang)
    stempel = datetime.now(UTC).strftime("%Y%m%d-%H%M")

    if not body.passwort:
        return JSONResponse(
            content=json.loads(backup_mod.als_json(daten)),
            headers={"Content-Disposition":
                     f'attachment; filename="sparbit-backup-{stempel}.json"'})

    if len(body.passwort) < 8:
        raise HTTPException(400, "Das Passwort braucht mindestens 8 Zeichen.")
    try:
        huelle = backup_mod.verschluessele(
            backup_mod.als_json(daten).encode("utf-8"), body.passwort)
    except backup_mod.VerschluesselungFehlt as exc:
        raise HTTPException(501, str(exc)) from exc
    return JSONResponse(
        content=huelle,
        headers={"Content-Disposition":
                 f'attachment; filename="sparbit-backup-{stempel}.json.enc"'})


@router.post("/restore")
def restore(payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    """Sicherung einspielen.

    Nimmt die Datei so, wie sie exportiert wurde - offen oder
    verschluesselt. Fuer den verschluesselten Fall kommt das Passwort in
    einer Huelle: {"daten": <Datei>, "passwort": "..."}.
    """
    passwort = ""
    if isinstance(payload, dict) and "daten" in payload:
        passwort = str(payload.get("passwort") or "")
        payload = payload["daten"]

    if backup_mod.ist_verschluesselt(payload):
        if not passwort:
            raise HTTPException(400, "Diese Sicherung ist verschluesselt - "
                                     "bitte das Passwort mitgeben.")
        try:
            payload = backup_mod.entschluessele(payload, passwort)
        except backup_mod.VerschluesselungFehlt as exc:
            raise HTTPException(501, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    try:
        return {"ok": True, **backup_mod.spiele_ein(db, payload)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/backups")
def backups_liste() -> dict:
    """Die automatisch geschriebenen Sicherungen im Datenverzeichnis."""
    return {
        "ordner": str(backup_mod.ordner()),
        "dateien": backup_mod.vorhandene(),
        "verschluesselung_moeglich": backup_mod.verschluesselung_verfuegbar(),
    }


@router.post("/backups")
def backup_jetzt(db: Session = Depends(get_db)) -> dict:
    """Jetzt eine Sicherung in den Ordner schreiben."""
    passwort = str(get_setting(db, "backup_passwort") or "")
    pfad = backup_mod.schreibe_datei(db, passwort)
    entfernt = backup_mod.raeume_auf(int(get_setting(db, "backup_behalten", 7) or 7))
    return {"ok": True, "datei": pfad.name, "bytes": pfad.stat().st_size,
            "alte_entfernt": entfernt}


@router.get("/backups/{name}")
def backup_holen(name: str) -> FileResponse:
    pfad = (backup_mod.ordner() / name).resolve()
    if not pfad.is_relative_to(backup_mod.ordner().resolve()) or not pfad.is_file():
        raise HTTPException(404, "Diese Sicherung gibt es nicht.")
    return FileResponse(pfad, media_type="application/json", filename=pfad.name)


@router.delete("/backups/{name}")
def backup_loeschen(name: str) -> dict:
    pfad = (backup_mod.ordner() / name).resolve()
    if not pfad.is_relative_to(backup_mod.ordner().resolve()) or not pfad.is_file():
        raise HTTPException(404, "Diese Sicherung gibt es nicht.")
    pfad.unlink()
    return {"ok": True}


# --- Selbstueberwachung ----------------------------------------------------

class WatchdogAn(BaseModel):
    an: bool


@router.get("/probleme")
def probleme(db: Session = Depends(get_db)) -> dict:
    """Was gerade nicht laeuft - dieselbe Pruefung wie der Melder."""
    from .. import watchdog

    befunde = watchdog.pruefe(db)
    return {
        "an": bool(get_setting(db, "watchdog_an", True)),
        "probleme": [
            {"art": b.art, "betrifft": b.betrifft, "text": b.text,
             "rat": b.rat, "seit": b.seit}
            for b in befunde
        ],
    }


@router.put("/probleme/melden")
def probleme_melden(body: WatchdogAn, db: Session = Depends(get_db)) -> dict:
    set_setting(db, "watchdog_an", body.an)
    db.commit()
    return {"ok": True, "an": body.an}


# --- 18+-Bereich -----------------------------------------------------------

class ErwachsenSchalter(BaseModel):
    an: bool
    # Ohne dieses Haekchen wird nicht eingeschaltet. Es ist die Stelle, an
    # der man nicht aus Versehen hinklickt.
    bestaetigt: bool = False


class ErwachsenOptionen(BaseModel):
    melden: bool | None = None
    unscharf: bool | None = None


@router.get("/erwachsen")
def erwachsen_status(db: Session = Depends(get_db)) -> dict:
    from ..sources import all_sources

    quellen = [s for s in all_sources() if s.category.value == "erwachsen"]
    zustand = erwachsen_mod.zustand(db)
    zustand["quellen"] = len(quellen)
    zustand["quellen_namen"] = [s.display_name for s in quellen]
    zustand["deals"] = db.scalar(
        select(func.count()).select_from(Deal)
        .where(Deal.erwachsen.is_(True))) or 0
    return zustand


@router.put("/erwachsen")
def erwachsen_schalten(body: ErwachsenSchalter,
                       db: Session = Depends(get_db)) -> dict:
    try:
        zustand = erwachsen_mod.schalte(db, body.an, bestaetigt=body.bestaetigt)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Jobs sofort nachziehen: beim Ausschalten muessen die 18+-Quellen
    # aufhoeren zu laufen, beim Einschalten duerfen sie anfangen.
    from ..scheduler import sync_jobs
    sync_jobs()
    return zustand


@router.put("/erwachsen/optionen")
def erwachsen_optionen(body: ErwachsenOptionen,
                       db: Session = Depends(get_db)) -> dict:
    if body.melden is not None:
        set_setting(db, erwachsen_mod.MELDEN, bool(body.melden))
    if body.unscharf is not None:
        set_setting(db, erwachsen_mod.UNSCHARF, bool(body.unscharf))
    db.commit()
    return erwachsen_mod.zustand(db)


# --- Gratis-Gegenprobe -----------------------------------------------------

class GratisCheck(BaseModel):
    an: bool | None = None
    max_pro_lauf: int | None = None


@router.get("/gratischeck")
def gratischeck_status(db: Session = Depends(get_db)) -> dict:
    from datetime import timedelta

    seit = datetime.now(UTC) - timedelta(days=7)
    zeilen = db.execute(
        select(Deal.check_status, func.count(Deal.id))
        .where(Deal.check_am >= seit).group_by(Deal.check_status)).all()
    return {
        "an": bool(get_setting(db, gratischeck.SETTING_AN, True)),
        "max_pro_lauf": int(get_setting(db, gratischeck.SETTING_MAX,
                                        gratischeck.MAX_PRO_LAUF)),
        "woche": {status: anzahl for status, anzahl in zeilen if status},
        "label": gratischeck.LABEL,
    }


@router.put("/gratischeck")
def gratischeck_setzen(body: GratisCheck, db: Session = Depends(get_db)) -> dict:
    if body.an is not None:
        set_setting(db, gratischeck.SETTING_AN, bool(body.an))
    if body.max_pro_lauf is not None:
        set_setting(db, gratischeck.SETTING_MAX,
                    max(0, min(60, int(body.max_pro_lauf))))
    db.commit()
    return gratischeck_status(db)


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


@host_router.post("/claimer-bericht", dependencies=[Depends(_pruefe_token)])
def claimer_bericht(bericht: dict, db: Session = Depends(get_db)) -> dict:
    return updater.nimm_claimer_bericht(db, bericht)


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
                except TimeoutError:
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


@claimer_router.get("/lauf")
def claimer_lauf_status(db: Session = Depends(get_db)) -> dict:
    return updater.claimer_status(db)


@claimer_router.post("/lauf")
def claimer_lauf_starten(db: Session = Depends(get_db)) -> dict:
    """Den Claimer-Container einmal laufen lassen.

    Der Backend-Container bekommt bewusst keinen Docker-Socket; der
    Auftrag geht denselben Weg wie ein Update - über das Host-Skript.
    """
    try:
        return updater.claimer_anfordern(db)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@claimer_router.post("/scan")
def claimer_scan() -> dict:
    return {"neue_ereignisse": claimer_mod.scan_job()}
