from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import current_user, darf_schreiben
from ..besitz import gehoert_mir, nur_meine
from ..db import get_db, get_setting, set_setting
from ..drosselung import drossel
from ..models import Channel as ChannelRow
from ..models import NotificationLog, PushAbo, User
from ..notify import all_channels, get_channel
from ..scheduler import get_http

router = APIRouter(prefix="/api/channels", tags=["notify"],
                   dependencies=[Depends(current_user)])

# Felder, die nie im Klartext zurueckgehen.
# Was nie im Klartext zurueckgegeben wird. "topic" gehoert dazu: wer ein
# ntfy-Topic kennt, liest alle Meldungen mit. "user" ist der Pushover-Schluessel.
SECRET_KEYS = {"bot_token", "password", "token", "url", "user", "topic"}


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
             "supports_buttons": c.supports_buttons,
             "options_schema": [asdict(o) for o in c.options_schema]}
            for c in all_channels()]


@router.get("")
def list_channels(db: Session = Depends(get_db),
                  user: User = Depends(current_user)) -> list[dict]:
    stmt = nur_meine(select(ChannelRow), ChannelRow, user).order_by(ChannelRow.id)
    return [_channel_dict(c) for c in db.scalars(stmt)]


def _mein_kanal(channel_id: int, db: Session, user: User) -> ChannelRow:
    row = db.get(ChannelRow, channel_id)
    if row is None or not gehoert_mir(row, user):
        raise HTTPException(404, "Kanal nicht gefunden")
    return row


@router.post("")
def create_channel(body: ChannelBody, db: Session = Depends(get_db),
                   user: User = Depends(darf_schreiben)) -> dict:
    if get_channel(body.type) is None:
        raise HTTPException(400, f"Unbekannter Kanaltyp '{body.type}'")
    row = ChannelRow(type=body.type, name=body.name, enabled=body.enabled,
                     config=body.config, benutzer_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _channel_dict(row)


@router.put("/{channel_id}")
def update_channel(channel_id: int, body: ChannelBody,
                   db: Session = Depends(get_db),
                   user: User = Depends(darf_schreiben)) -> dict:
    row = _mein_kanal(channel_id, db, user)
    if row.benutzer_id is None:
        row.benutzer_id = user.id
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
def delete_channel(channel_id: int, db: Session = Depends(get_db),
                   user: User = Depends(darf_schreiben)) -> dict:
    row = _mein_kanal(channel_id, db, user)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{channel_id}/test",
             # Jeder Test verschickt wirklich etwas. Eine Schleife hier
             # bringt nicht SparBit an die Grenze, sondern das Konto beim
             # Dienst dahinter.
             dependencies=[Depends(drossel("kanal-test", pro_minute=10, stoss=4))])
async def test_channel(channel_id: int, db: Session = Depends(get_db),
                       user: User = Depends(current_user)) -> dict:
    row = _mein_kanal(channel_id, db, user)
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


# --- Web Push: Geraete an- und abmelden -----------------------------------

push_router = APIRouter(prefix="/api/push", tags=["push"],
                        dependencies=[Depends(current_user)])


class AboBody(BaseModel):
    endpunkt: str = Field(min_length=10, max_length=2000)
    p256dh: str = Field(min_length=10, max_length=255)
    auth: str = Field(min_length=8, max_length=64)
    geraet: str = Field(default="", max_length=255)


@push_router.get("/schluessel")
def push_schluessel(db: Session = Depends(get_db)) -> dict:
    """Den oeffentlichen VAPID-Schluessel holen - der Browser braucht ihn
    beim Anmelden.

    Erzeugt wird das Paar beim ersten Aufruf. Einmal je Installation:
    waere es je Geraet, muessten sich alle anderen neu anmelden, sobald
    eines dazukommt.
    """
    from .. import webpush

    if not webpush.verfuegbar():
        return {"verfuegbar": False, "schluessel": None,
                "grund": "Das Paket 'cryptography' fehlt."}

    oeffentlich = get_setting(db, "vapid_oeffentlich")
    if not oeffentlich:
        paar = webpush.neues_paar()
        set_setting(db, "vapid_privat", paar.privat)
        set_setting(db, "vapid_oeffentlich", paar.oeffentlich)
        db.commit()
        oeffentlich = paar.oeffentlich
    return {"verfuegbar": True, "schluessel": oeffentlich,
            "geraete": db.query(PushAbo).count()}


@push_router.post("/abo")
def push_anmelden(body: AboBody, db: Session = Depends(get_db),
                  user: User = Depends(current_user)) -> dict:
    """Dieses Geraet anmelden. Derselbe Endpunkt zweimal ist kein Fehler -
    der Browser erneuert ihn von sich aus."""
    vorhanden = db.scalar(select(PushAbo).where(PushAbo.endpunkt == body.endpunkt))
    if vorhanden is not None and not gehoert_mir(vorhanden, user):
        # Derselbe Browser, anderes Konto: das Abo wechselt den Besitzer,
        # statt beim alten zu bleiben - sonst bekaeme der Vorgaenger
        # weiter die Meldungen auf dieses Geraet.
        vorhanden.benutzer_id = user.id
    if vorhanden:
        vorhanden.p256dh = body.p256dh
        vorhanden.auth = body.auth
        vorhanden.geraet = body.geraet[:255] or vorhanden.geraet
        vorhanden.fehler_in_folge = 0
        db.commit()
        return {"ok": True, "neu": False, "id": vorhanden.id}

    abo = PushAbo(endpunkt=body.endpunkt, p256dh=body.p256dh, auth=body.auth,
                  geraet=body.geraet[:255] or None, benutzer_id=user.id)
    db.add(abo)
    db.commit()
    db.refresh(abo)
    return {"ok": True, "neu": True, "id": abo.id}


@push_router.get("/abos")
def push_liste(db: Session = Depends(get_db),
               user: User = Depends(current_user)) -> list[dict]:
    return [{"id": a.id, "geraet": a.geraet or "unbekanntes Gerät",
             "erstellt_am": a.erstellt_am, "zuletzt_ok": a.zuletzt_ok,
             "host": a.endpunkt.split("/")[2] if "/" in a.endpunkt else ""}
            for a in db.scalars(nur_meine(select(PushAbo), PushAbo, user)
                                .order_by(desc(PushAbo.erstellt_am)))]


@push_router.delete("/abo/{abo_id}")
def push_abmelden(abo_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)) -> dict:
    abo = db.get(PushAbo, abo_id)
    if abo is None or not gehoert_mir(abo, user):
        raise HTTPException(404, "Nicht gefunden")
    db.delete(abo)
    db.commit()
    return {"ok": True}
