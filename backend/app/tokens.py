"""Zugangstoken fuer die Browser-Erweiterung.

Die Erweiterung laeuft auf fremden Seiten und kann das Sitzungs-Cookie nicht
mitschicken. Sie bekommt darum einen eigenen Schluessel - einzeln
zurueckziehbar, damit man nicht das Passwort aendern muss, wenn ein Rechner
abhandenkommt.

Gespeichert wird nur der Hash. Der Klartext ist genau einmal zu sehen,
direkt nach dem Anlegen.
"""
from __future__ import annotations

import hashlib
import logging
import secrets

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ApiToken, utcnow

log = logging.getLogger(__name__)

PRAEFIX = "sparbit_"


def erzeuge(db: Session, name: str) -> tuple[ApiToken, str]:
    """Neues Token anlegen. Gibt (Datensatz, Klartext) zurueck."""
    klartext = PRAEFIX + secrets.token_urlsafe(32)
    zeile = ApiToken(name=name.strip()[:128] or "Browser-Erweiterung",
                     token_hash=_hash(klartext),
                     praefix=klartext[:12])
    db.add(zeile)
    db.commit()
    db.refresh(zeile)
    log.info("API-Token '%s' angelegt", zeile.name)
    return zeile, klartext


def _hash(klartext: str) -> str:
    return hashlib.sha256(klartext.encode("utf-8")).hexdigest()


def pruefe(db: Session, klartext: str) -> ApiToken | None:
    if not klartext or not klartext.startswith(PRAEFIX):
        return None
    zeile = db.scalar(select(ApiToken).where(ApiToken.token_hash == _hash(klartext)))
    if zeile is not None:
        zeile.zuletzt_genutzt = utcnow()
        db.commit()
    return zeile


def token_aus_header(authorization: str | None = Header(default=None)) -> str:
    """Bearer-Token aus dem Authorization-Header ziehen."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Kein Token. Erwartet: Authorization: Bearer <token>")
    return authorization.split(" ", 1)[1].strip()
