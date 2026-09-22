"""Anmeldung: argon2-Hash + signiertes Session-Cookie.

Kein Default-Passwort. Solange kein Benutzer existiert, laeuft nur der
Setup-Assistent.

Lange war hier genau ein Konto vorgesehen - create_user warf ab dem
zweiten einen Fehler. Fuer einen Haushalt ist das die falsche Zahl: die
Wunschliste des einen hat mit den Regeln des anderen nichts zu tun, und
alles unter einem Konto zu fuehren heisst, dass jeder die Meldungen
aller bekommt.

Drei Rollen, mehr braucht es nicht: **Admin** verwaltet Quellen,
Benutzer und System, **Mitglied** hat eigene Regeln, Kanaele und
Wunschlisten, **Gast** darf zusehen. Der erste Benutzer ist immer
Admin - sonst koennte niemand weitere anlegen.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, secret_key
from .models import ADMIN, GAST, MITGLIED, ROLLEN, User

log = logging.getLogger(__name__)
_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    try:
        _ph.verify(hashed, plain)
        return True
    except (VerifyMismatchError, Exception):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _ph.check_needs_rehash(hashed)
    except Exception:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt="sparbit-session")


def issue_session(response: Response, user: User, secure: bool = False) -> None:
    token = _serializer().dumps({"uid": user.id, "u": user.username})
    response.set_cookie(
        settings.session_cookie, token,
        max_age=settings.session_max_age,
        httponly=True, samesite="lax", secure=secure, path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(settings.session_cookie, path="/")


def setup_done(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(User)) or 0) > 0


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency: wirft 401, wenn nicht eingeloggt."""
    if not setup_done(db):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Setup noch nicht abgeschlossen")
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")
    try:
        data = _serializer().loads(token, max_age=settings.session_max_age)
    except SignatureExpired:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung abgelaufen") from None
    except BadSignature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungueltige Sitzung") from None

    user = db.get(User, data.get("uid"))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzer existiert nicht")
    if not user.aktiv:
        # Abgeschaltet statt geloescht: die Sitzung endet trotzdem sofort.
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Dieses Konto ist abgeschaltet.")
    return user


def create_user(db: Session, username: str, password: str,
                rolle: str | None = None) -> User:
    """Benutzer anlegen. Der erste einer Installation wird Admin."""
    if len(password) < 10:
        raise HTTPException(400, "Passwort muss mindestens 10 Zeichen haben.")
    username = username.strip()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, f"Den Benutzer '{username}' gibt es schon.")

    erster = not setup_done(db)
    if erster:
        rolle = ADMIN
    elif rolle not in ROLLEN:
        rolle = MITGLIED

    user = User(username=username, password_hash=hash_password(password),
                rolle=rolle, aktiv=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("Benutzer '%s' angelegt (%s)", user.username, user.rolle)
    return user


def nur_admin(user: User = Depends(current_user)) -> User:
    """Dependency fuer alles, was die ganze Installation betrifft."""
    if user.rolle != ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Das darf nur ein Administrator.")
    return user


def darf_schreiben(user: User = Depends(current_user)) -> User:
    """Ein Gast darf zusehen - anlegen und aendern darf er nicht."""
    if user.rolle == GAST:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Gäste können nichts ändern.")
    return user


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not user or not verify_password(user.password_hash, password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Benutzername oder Passwort falsch")
    if not user.aktiv:
        # Dieselbe Meldung wie bei falschem Passwort waere hier falsch:
        # das Passwort stimmt ja, und wer es weiss, soll erfahren, warum
        # es trotzdem nicht geht.
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Dieses Konto ist abgeschaltet.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login = datetime.now(UTC)
    db.commit()
    return user
