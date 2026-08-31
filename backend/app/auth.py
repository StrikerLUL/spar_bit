"""Single-User-Auth: argon2-Hash + signiertes Session-Cookie.

Kein Default-Passwort. Solange kein User existiert, laeuft nur der
Setup-Assistent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, secret_key
from .models import User

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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung abgelaufen")
    except BadSignature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungueltige Sitzung")

    user = db.get(User, data.get("uid"))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzer existiert nicht")
    return user


def create_user(db: Session, username: str, password: str) -> User:
    if len(password) < 10:
        raise HTTPException(400, "Passwort muss mindestens 10 Zeichen haben.")
    if setup_done(db):
        raise HTTPException(409, "Es existiert bereits ein Benutzer.")
    user = User(username=username.strip(), password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("Benutzer '%s' angelegt", user.username)
    return user


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not user or not verify_password(user.password_hash, password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Benutzername oder Passwort falsch")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return user
