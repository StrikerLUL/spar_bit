from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db, get_setting, set_setting
from ..models import Channel as ChannelRow
from ..models import NotificationLog
from ..notify import all_channels, get_channel
from ..scheduler import get_http

router = APIRouter(prefix="/api/channels", tags=["notify"],
                   dependencies=[Depends(current_user)])

# Felder, die nie im Klartext zurueckgehen.
SECRET_KEYS = {"bot_token", "password", "token", "url"}


class ChannelBody(BaseModel):
    type: str
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    config: dict = {}


def _mask(cfg: dict) -> dict:
    out = {}
    for key, val in (cfg or {}).items():
        if key in SECRET_KEYS and isinstance(val, str) and val:
            out[key] = val[:4] + "…" + val[-3:] if len(val) > 10 else "…"
            out[f"{key}__set"] = True
        else:
            out[key] = val
    return out


def _channel_dict(c: ChannelRow) -> dict:
    return {"id": c.id, "type": c.type, "name": c.name, "enabled": c.enabled,
            "config": _mask(c.config or {}), "created_at": c.created_at,
            "last_used": c.last_used, "error_count": c.error_count}


@router.get("/types")
def channel_types() -> list[dict]:
    return [{"type": c.type, "display_name": c.display_name,
             "beschreibung": c.beschreibung,
             "options_schema": [asdict(o) for o in c.options_schema]}
            for c in all_channels()]


@router.get("")
def list_channels(db: Session = Depends(get_db)) -> list[dict]:
    return [_channel_dict(c) for c in db.scalars(select(ChannelRow).order_by(ChannelRow.id))]


@router.post("")
def create_channel(body: ChannelBody, db: Session = Depends(get_db)) -> dict:
    if get_channel(body.type) is None:
        raise HTTPException(400, f"Unbekannter Kanaltyp '{body.type}'")
    row = ChannelRow(type=body.type, name=body.name, enabled=body.enabled,
                     config=body.config)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _channel_dict(row)


@router.put("/{channel_id}")
def update_channel(channel_id: int, body: ChannelBody,
                   db: Session = Depends(get_db)) -> dict:
    row = db.get(ChannelRow, channel_id)
    if row is None:
        raise HTTPException(404, "Kanal nicht gefunden")
    row.name, row.enabled = body.name, body.enabled
    # Maskierte Werte nicht ueberschreiben: leere/maskierte Felder behalten.
    merged = dict(row.config or {})
    for key, val in (body.config or {}).items():
        if key.endswith("__set"):
            continue
        if key in SECRET_KEYS and isinstance(val, str) and ("…" in val or val == ""):
            continue
        merged[key] = val
    row.config = merged
    db.commit()
    db.refresh(row)
    return _channel_dict(row)


@router.delete("/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ChannelRow, channel_id)
    if row is None:
        raise HTTPException(404, "Kanal nicht gefunden")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{channel_id}/test")
async def test_channel(channel_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ChannelRow, channel_id)
    if row is None:
        raise HTTPException(404, "Kanal nicht gefunden")
    impl = get_channel(row.type)
    if impl is None:
        raise HTTPException(400, f"Unbekannter Kanaltyp '{row.type}'")
    try:
        await impl.send_test(row.config or {}, get_http())
    except Exception as exc:
        row.error_count += 1
        db.add(NotificationLog(channel_id=row.id, channel_type=row.type,
                               deal_titel="Testnachricht", ok=False,
                               error=f"{type(exc).__name__}: {exc}"[:500]))
        db.commit()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
    db.add(NotificationLog(channel_id=row.id, channel_type=row.type,
                           deal_titel="Testnachricht", ok=True))
    db.commit()
    return {"ok": True}


@router.get("/log")
def notification_log(limit: int = Query(80, le=300),
                     db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(NotificationLog)
                      .order_by(desc(NotificationLog.created_at)).limit(limit))
    return [{"id": r.id, "channel_type": r.channel_type, "rule_name": r.rule_name,
             "deal_titel": r.deal_titel, "ok": r.ok, "error": r.error,
             "created_at": r.created_at} for r in rows]


# --- Ruhezeiten -----------------------------------------------------------

quiet_router = APIRouter(prefix="/api/quiet-hours", tags=["notify"],
                         dependencies=[Depends(current_user)])


class QuietHours(BaseModel):
    enabled: bool = False
    start: str = "23:00"
    end: str = "07:00"
    utc_offset: float = 2.0


@quiet_router.get("")
def get_quiet(db: Session = Depends(get_db)) -> dict:
    return get_setting(db, "quiet_hours") or QuietHours().model_dump()


@quiet_router.put("")
def put_quiet(body: QuietHours, db: Session = Depends(get_db)) -> dict:
    set_setting(db, "quiet_hours", body.model_dump())
    db.commit()
    return body.model_dump()
