from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import status as http_status  # 'status' ist hier eine Route
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import (authenticate, clear_session, create_user, current_user,
                    issue_session, setup_done)
from ..db import get_db
from ..loginguard import (SANFT_AB, LoginGesperrt, client_ip, fehlversuch,
                          pruefen, zuruecksetzen)
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SetupBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)) -> dict:
    done = setup_done(db)
    logged_in = False
    username = None
    if done:
        try:
            user = current_user(request, db)
            logged_in, username = True, user.username
        except HTTPException:
            pass
    return {"setup_done": done, "logged_in": logged_in, "username": username}


@router.post("/setup")
def setup(body: SetupBody, request: Request, response: Response,
          db: Session = Depends(get_db)) -> dict:
    user = create_user(db, body.username, body.password)
    issue_session(response, user, secure=request.url.scheme == "https")
    return {"ok": True, "username": user.username}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response,
          db: Session = Depends(get_db)) -> dict:
    ip = client_ip(request)
    try:
        pruefen(db, ip)
    except LoginGesperrt as gesperrt:
        # 429 mit Retry-After: das UI kann daraus einen Countdown bauen.
        raise HTTPException(
            http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(f"Zu viele Fehlversuche. Bitte "
                    f"{_dauer(gesperrt.sekunden)} warten."),
            headers={"Retry-After": str(int(gesperrt.sekunden))},
        ) from None

    try:
        user = authenticate(db, body.username, body.password)
    except HTTPException:
        versuche = fehlversuch(db, ip, body.username)
        rest = SANFT_AB - versuche
        hinweis = ("Benutzername oder Passwort falsch."
                   + (f" Noch {rest} Versuche, dann wird gebremst."
                      if 0 < rest <= 2 else ""))
        raise HTTPException(http_status.HTTP_401_UNAUTHORIZED, hinweis) from None

    zuruecksetzen(db, ip)
    issue_session(response, user, secure=request.url.scheme == "https")
    return {"ok": True, "username": user.username}


def _dauer(sekunden: float) -> str:
    if sekunden < 60:
        return f"{int(sekunden)} Sekunden"
    minuten = int(sekunden // 60)
    return f"{minuten} Minute{'n' if minuten != 1 else ''}"


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session(response)
    return {"ok": True}


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=10, max_length=256)


@router.post("/password")
def change_password(body: PasswordChange, db: Session = Depends(get_db),
                    user: User = Depends(current_user)) -> dict:
    from ..auth import hash_password, verify_password
    if not verify_password(user.password_hash, body.old_password):
        raise HTTPException(401, "Aktuelles Passwort ist falsch.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
