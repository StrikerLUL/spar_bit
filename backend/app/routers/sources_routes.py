from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import erwachsen as erwachsen_mod
from ..auth import current_user, nur_admin
from ..db import get_db
from ..drosselung import drossel
from ..models import SourceConfig, SourceRun, utcnow
from ..scheduler import build_context, run_source, schedule_source
from ..sources import all_sources, get_source

log = logging.getLogger(__name__)
# Lesen darf jeder Angemeldete, aendern nur ein Admin: eine Quelle
# kostet Anfragen bei einem fremden Server, und wer sie umstellt,
# entscheidet fuer die ganze Anlage - nicht nur fuer sich.
router = APIRouter(prefix="/api/sources", tags=["sources"],
                   dependencies=[Depends(current_user)])
schreib_abhaengig = [Depends(nur_admin)]


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


@router.post(dependencies=[*schreib_abhaengig,
                           # Jede Suche laedt eine fremde Seite und probiert
                           # danach mehrere Pfade durch - ein Knopf, viele Abrufe.
                           Depends(drossel("feed-suche", pro_minute=10, stoss=3))],
             path="/feed-suche")
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


@router.patch(dependencies=schreib_abhaengig, path="/{source_id}")
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


@router.post(dependencies=[*schreib_abhaengig,
                           Depends(drossel("quelle-test", pro_minute=12, stoss=4))],
             path="/{source_id}/test")
async def test_source(source_id: str, db: Session = Depends(get_db)) -> dict:
    """'Jetzt testen' - health_check mit Live-Ergebnis, ohne zu speichern."""
    src = get_source(source_id)
    cfg = db.get(SourceConfig, source_id)
    if src is None or cfg is None:
        raise HTTPException(404, "Quelle unbekannt")
    _pruefe_frei(db, source_id)

    # Wer hier drueckt, will jetzt eine Antwort - nicht die Sperrfrist von
    # vorhin, die verhindert, dass eine tote Adresse alle zehn Minuten
    # durchprobiert wird.
    from .. import feedfinder
    feedfinder.pause_zuruecksetzen()

    ctx = build_context(cfg)
    result = await src.health_check(ctx)

    cfg.verification = "verified" if result.ok else "broken"
    cfg.last_verified = utcnow()
    if not result.ok:
        cfg.last_error = result.detail
    # Was der Test unterwegs gelernt hat, gilt auch fuer den echten Lauf:
    # eine gefundene Feed-Adresse, ein Subreddit, den es nicht gibt. Sonst
    # zeigt der Test etwas anderes als die Quelle danach tut.
    if ctx.notizen:
        cfg.options = {**(cfg.options or {}), **ctx.notizen}
        log.info("%s: Einstellungen beim Test korrigiert (%s)",
                 source_id, ", ".join(sorted(ctx.notizen)))
    db.commit()

    return {
        "ok": result.ok,
        "detail": result.detail,
        "items_found": result.items_found,
        "latency_ms": result.latency_ms,
        "samples": [s.model_dump(mode="json") for s in result.samples],
    }


@router.post(dependencies=schreib_abhaengig, path="/{source_id}/run")
async def run_now(source_id: str, db: Session = Depends(get_db)) -> dict:
    if get_source(source_id) is None:
        raise HTTPException(404, "Quelle unbekannt")
    _pruefe_frei(db, source_id)
    return await run_source(source_id, manual=True)


@router.post(dependencies=schreib_abhaengig, path="/{source_id}/reset")
def reset_breaker(source_id: str, db: Session = Depends(get_db)) -> dict:
    cfg = db.get(SourceConfig, source_id)
    if cfg is None:
        raise HTTPException(404, "Quelle unbekannt")
    cfg.consecutive_failures = 0
    cfg.circuit_open_until = None
    cfg.last_error = None
    db.commit()
    return {"ok": True}


# --- OPML: Feeds mitbringen und mitnehmen ---------------------------------

OPML_QUELLEN = ("custom_feed", "erwachsen_feeds")


@router.get("/opml/export")
def opml_export(db: Session = Depends(get_db)) -> Response:
    """Die eigenen Feeds als OPML.

    Das Format, in dem jeder Feedreader seine Abos hat. Wer SparBit
    umzieht oder seine Liste anderswo weiterpflegen will, soll sie nicht
    abtippen muessen.
    """
    import xml.etree.ElementTree as ET
    from datetime import UTC, datetime

    opml = ET.Element("opml", version="2.0")
    kopf = ET.SubElement(opml, "head")
    ET.SubElement(kopf, "title").text = "SparBit — eigene Feeds"
    ET.SubElement(kopf, "dateCreated").text = datetime.now(UTC).strftime(
        "%a, %d %b %Y %H:%M:%S +0000")
    koerper = ET.SubElement(opml, "body")

    anzahl = 0
    for cfg in db.scalars(select(SourceConfig).where(
            SourceConfig.id.in_(OPML_QUELLEN))):
        for schluessel in ("feeds", "eigene_feeds"):
            for url in (cfg.options or {}).get(schluessel) or []:
                if not str(url).strip():
                    continue
                ET.SubElement(koerper, "outline", type="rss",
                              text=str(url), title=str(url),
                              xmlUrl=str(url))
                anzahl += 1

    roh = ET.tostring(opml, encoding="utf-8", xml_declaration=True)
    return Response(content=roh, media_type="text/x-opml; charset=utf-8",
                    headers={"Content-Disposition":
                             'attachment; filename="sparbit-feeds.opml"',
                             "X-SparBit-Feeds": str(anzahl)})


class OpmlImport(BaseModel):
    inhalt: str = Field(min_length=10, max_length=2_000_000)
    ziel: str = "custom_feed"


@router.post(dependencies=schreib_abhaengig, path="/opml/import")
def opml_import(body: OpmlImport, db: Session = Depends(get_db)) -> dict:
    """OPML aus einem Feedreader einlesen.

    Was schon drinsteht, bleibt unberuehrt - zweimal importieren legt
    keine Dubletten an.
    """
    import xml.etree.ElementTree as ET

    if body.ziel not in OPML_QUELLEN:
        raise HTTPException(400, "Unbekanntes Ziel für den Import.")

    try:
        baum = ET.fromstring(body.inhalt)
    except ET.ParseError as exc:
        raise HTTPException(400, f"Das ist kein gültiges OPML: {exc}") from None

    gefunden: list[str] = []
    for knoten in baum.iter("outline"):
        url = (knoten.get("xmlUrl") or knoten.get("xmlurl") or "").strip()
        if url.lower().startswith(("http://", "https://")) and url not in gefunden:
            gefunden.append(url)

    if not gefunden:
        raise HTTPException(400, "In der Datei steht kein einziger Feed "
                                 "(gesucht wird das Attribut xmlUrl).")

    cfg = db.get(SourceConfig, body.ziel)
    if cfg is None:
        raise HTTPException(404, "Diese Quelle gibt es nicht.")

    optionen = dict(cfg.options or {})
    schluessel = "feeds" if "feeds" in optionen or body.ziel == "custom_feed" \
        else "eigene_feeds"
    bestand = [str(f) for f in optionen.get(schluessel) or []]
    neu = [u for u in gefunden if u not in bestand]
    optionen[schluessel] = bestand + neu
    cfg.options = optionen
    db.commit()

    return {"ok": True, "gefunden": len(gefunden), "neu": len(neu),
            "schon_da": len(gefunden) - len(neu),
            "quelle": body.ziel, "aktiv": bool(cfg.enabled)}
