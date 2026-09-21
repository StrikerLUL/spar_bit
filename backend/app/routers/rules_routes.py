from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import current_user, darf_schreiben
from ..besitz import gehoert_mir, nur_meine
from ..db import get_db
from ..filters import RuleSpec, evaluate, preview
from ..models import Channel as ChannelRow
from ..models import Deal, Match, Rule, User

router = APIRouter(prefix="/api/rules", tags=["rules"],
                   dependencies=[Depends(current_user)])


class RuleBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    priority: str = "NORMAL"
    keywords: list[str] = []
    required_keywords: list[str] = []
    blacklist: list[str] = []
    max_preis: float | None = None
    min_rabatt_prozent: float | None = None
    nur_gratis: bool = False
    min_temperatur: float | None = None
    min_urteil: str | None = None
    min_fehler_score: int | None = None
    sources: list[str] = []
    kategorien: list[str] = []
    haendler: list[str] = []
    channels: list[int] = []
    # Ohne dieses Haekchen sieht die Regel 18+-Funde gar nicht.
    erwachsen: bool = False


def _rule_dict(r: Rule) -> dict:
    return {
        "id": r.id, "name": r.name, "enabled": r.enabled, "priority": r.priority,
        "keywords": r.keywords or [], "required_keywords": r.required_keywords or [],
        "blacklist": r.blacklist or [], "max_preis": r.max_preis,
        "min_rabatt_prozent": r.min_rabatt_prozent, "nur_gratis": r.nur_gratis,
        "min_temperatur": r.min_temperatur, "min_urteil": r.min_urteil,
        "min_fehler_score": r.min_fehler_score,
        "sources": r.sources or [],
        "kategorien": r.kategorien or [], "haendler": r.haendler or [],
        "erwachsen": bool(getattr(r, "erwachsen", False)),
        "channels": r.channels or [], "created_at": r.created_at,
        "match_count": r.match_count, "last_match": r.last_match,
    }


@router.get("")
def list_rules(db: Session = Depends(get_db),
               user: User = Depends(current_user)) -> list[dict]:
    stmt = nur_meine(select(Rule), Rule, user).order_by(Rule.id)
    return [_rule_dict(r) for r in db.scalars(stmt)]


def _meine_regel(rule_id: int, db: Session, user: User) -> Rule:
    rule = db.get(Rule, rule_id)
    # 404 statt 403, wenn sie jemand anderem gehoert: dass es sie gibt,
    # geht niemanden etwas an.
    if rule is None or not gehoert_mir(rule, user):
        raise HTTPException(404, "Regel nicht gefunden")
    return rule


def _pruefe_kanaele(body: RuleBody, db: Session, user: User) -> None:
    """Eine Regel darf nur auf eigene Kanaele zeigen.

    Ohne diese Pruefung koennte man - mit einer per Hand gebauten
    Anfrage - die Meldungen seiner Regel auf das Telefon eines anderen
    schicken.
    """
    if not body.channels:
        return
    erlaubt = {c.id for c in db.scalars(
        nur_meine(select(ChannelRow), ChannelRow, user))}
    fremd = [cid for cid in body.channels if cid not in erlaubt]
    if fremd:
        raise HTTPException(400, "Diese Kanäle gibt es nicht oder sie gehören "
                                 "jemand anderem.")


@router.post("")
def create_rule(body: RuleBody, db: Session = Depends(get_db),
                user: User = Depends(darf_schreiben)) -> dict:
    _pruefe_kanaele(body, db, user)
    rule = Rule(**body.model_dump(), benutzer_id=user.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, db: Session = Depends(get_db),
                user: User = Depends(darf_schreiben)) -> dict:
    rule = _meine_regel(rule_id, db, user)
    _pruefe_kanaele(body, db, user)
    for key, value in body.model_dump().items():
        setattr(rule, key, value)
    # Eine Regel aus der Zeit vor den Konten bekommt beim ersten Bearbeiten
    # einen Besitzer - den, der sie bearbeitet.
    if rule.benutzer_id is None:
        rule.benutzer_id = user.id
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db),
                user: User = Depends(darf_schreiben)) -> dict:
    rule = _meine_regel(rule_id, db, user)
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/preview")
def preview_rule(body: RuleBody, sample: int = Query(500, le=2000),
                 db: Session = Depends(get_db)) -> dict:
    """Kernfunktion des Regel-Editors: wie viele der letzten N Deals haette
    diese Regel getroffen - inklusive Beispielen und knappen Verfehlern."""
    # Die Vorschau zeigt denselben Ausschnitt, den die Regel spaeter sieht:
    # ohne das 18+-Haekchen kommen diese Deals gar nicht erst in die Stichprobe.
    stmt = select(Deal)
    if not body.erwachsen:
        stmt = stmt.where(Deal.erwachsen.is_(False))
    deals = list(db.scalars(
        stmt.order_by(desc(Deal.first_seen)).limit(sample)))
    spec = RuleSpec(
        keywords=body.keywords, required_keywords=body.required_keywords,
        blacklist=body.blacklist, max_preis=body.max_preis,
        min_rabatt_prozent=body.min_rabatt_prozent, nur_gratis=body.nur_gratis,
        min_temperatur=body.min_temperatur, min_urteil=body.min_urteil,
        min_fehler_score=body.min_fehler_score, sources=body.sources,
        kategorien=body.kategorien, haendler=body.haendler,
        erwachsen=body.erwachsen,
    )
    return preview(spec, deals)


@router.get("/{rule_id}/matches")
def rule_matches(rule_id: int, limit: int = Query(50, le=200),
                 db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Match).where(Match.rule_id == rule_id)
        .order_by(desc(Match.created_at)).limit(limit))
    out = []
    for m in rows:
        if m.deal is None:
            continue
        out.append({"created_at": m.created_at, "notified_at": m.notified_at,
                    "titel": m.deal.titel, "url": m.deal.url,
                    "preis": m.deal.preis, "quelle": m.deal.quelle,
                    "bild": m.deal.bild, "ist_gratis": m.deal.ist_gratis})
    return out


@router.post("/{rule_id}/explain/{deal_id}")
def explain(rule_id: int, deal_id: int, db: Session = Depends(get_db),
            user: User = Depends(current_user)) -> dict:
    """Warum hat (oder hat nicht) diese Regel diesen Deal getroffen?"""
    rule, deal = db.get(Rule, rule_id), db.get(Deal, deal_id)
    if rule is not None and not gehoert_mir(rule, user):
        rule = None
    if rule is None or deal is None:
        raise HTTPException(404, "Regel oder Deal nicht gefunden")
    res = evaluate(RuleSpec.from_model(rule), deal)
    return {"matched": res.matched, "gruende": res.reasons, "verfehlt": res.failed}


# --- Regeln teilen ---------------------------------------------------------

# Was eine Regel ausmacht. Bewusst ohne id, Trefferzahl und Kanal-IDs:
# eine Regel aus einer fremden Installation soll sich einsetzen lassen,
# ohne dort auf Kanaele zu zeigen, die es hier gar nicht gibt.
TEILBAR = ("name", "priority", "keywords", "required_keywords", "blacklist",
           "max_preis", "min_rabatt_prozent", "nur_gratis", "min_temperatur",
           "min_urteil", "min_fehler_score", "sources", "kategorien",
           "haendler", "erwachsen")


@router.get("/export")
def regeln_export(db: Session = Depends(get_db),
                  user: User = Depends(current_user)) -> dict:
    """Regeln als JSON zum Weitergeben.

    Eine gute Regel ist Arbeit - und bisher blieb sie in der
    Installation, in der sie gebaut wurde. Der Export enthaelt keine
    Kanal-Zuordnung und keine Trefferzahlen: was hier rausgeht, soll
    woanders funktionieren.
    """
    regeln = []
    for r in db.scalars(nur_meine(select(Rule), Rule, user).order_by(Rule.name)):
        regeln.append({f: getattr(r, f) for f in TEILBAR})
    return {"format": "sparbit-regeln", "version": 1, "regeln": regeln}


class RegelImport(BaseModel):
    regeln: list[dict]
    # Standard: dazulegen statt ersetzen. Wer seine Regeln loswerden
    # will, sagt das ausdruecklich.
    ersetzen: bool = False
    aktiv: bool = False


@router.post("/import")
def regeln_import(body: RegelImport, db: Session = Depends(get_db),
                  user: User = Depends(darf_schreiben)) -> dict:
    """Regeln einsetzen.

    Neue Regeln kommen **ausgeschaltet** an. Eine fremde Regel, die
    sofort losmeldet, ist der schnellste Weg zu einem stummgeschalteten
    Kanal - erst ansehen, dann einschalten.
    """
    if not isinstance(body.regeln, list) or not body.regeln:
        raise HTTPException(400, "Keine Regeln in der Datei.")

    if body.ersetzen:
        # Nur die eigenen - fremde Regeln sind nicht meine, sie zu loeschen.
        for eigene in db.scalars(nur_meine(select(Rule), Rule, user)):
            db.delete(eigene)
        db.flush()

    vorhanden = {r.name for r in db.scalars(nur_meine(select(Rule), Rule, user))}
    angelegt, uebersprungen = [], []

    for roh in body.regeln:
        if not isinstance(roh, dict) or not roh.get("name"):
            continue
        name = str(roh["name"])[:128]
        if name in vorhanden:
            uebersprungen.append(name)
            continue
        felder = {f: roh[f] for f in TEILBAR if f in roh}
        felder["name"] = name
        regel = Rule(**felder, enabled=bool(body.aktiv), channels=[],
                     benutzer_id=user.id)
        db.add(regel)
        vorhanden.add(name)
        angelegt.append(name)

    db.commit()
    return {"ok": True, "angelegt": angelegt, "uebersprungen": uebersprungen,
            "hinweis": ("Neue Regeln sind ausgeschaltet und ohne Kanal - "
                        "erst ansehen, dann einschalten."
                        if angelegt and not body.aktiv else "")}
