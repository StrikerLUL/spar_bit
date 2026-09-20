from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..filters import RuleSpec, evaluate, preview
from ..models import Deal, Match, Rule

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
        "channels": r.channels or [], "created_at": r.created_at,
        "match_count": r.match_count, "last_match": r.last_match,
    }


@router.get("")
def list_rules(db: Session = Depends(get_db)) -> list[dict]:
    return [_rule_dict(r) for r in db.scalars(select(Rule).order_by(Rule.id))]


@router.post("")
def create_rule(body: RuleBody, db: Session = Depends(get_db)) -> dict:
    rule = Rule(**body.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, db: Session = Depends(get_db)) -> dict:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, "Regel nicht gefunden")
    for key, value in body.model_dump().items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> dict:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, "Regel nicht gefunden")
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/preview")
def preview_rule(body: RuleBody, sample: int = Query(500, le=2000),
                 db: Session = Depends(get_db)) -> dict:
    """Kernfunktion des Regel-Editors: wie viele der letzten N Deals haette
    diese Regel getroffen - inklusive Beispielen und knappen Verfehlern."""
    deals = list(db.scalars(
        select(Deal).order_by(desc(Deal.first_seen)).limit(sample)))
    spec = RuleSpec(
        keywords=body.keywords, required_keywords=body.required_keywords,
        blacklist=body.blacklist, max_preis=body.max_preis,
        min_rabatt_prozent=body.min_rabatt_prozent, nur_gratis=body.nur_gratis,
        min_temperatur=body.min_temperatur, min_urteil=body.min_urteil,
        min_fehler_score=body.min_fehler_score, sources=body.sources,
        kategorien=body.kategorien, haendler=body.haendler,
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
def explain(rule_id: int, deal_id: int, db: Session = Depends(get_db)) -> dict:
    """Warum hat (oder hat nicht) diese Regel diesen Deal getroffen?"""
    rule, deal = db.get(Rule, rule_id), db.get(Deal, deal_id)
    if rule is None or deal is None:
        raise HTTPException(404, "Regel oder Deal nicht gefunden")
    res = evaluate(RuleSpec.from_model(rule), deal)
    return {"matched": res.matched, "gruende": res.reasons, "verfehlt": res.failed}
