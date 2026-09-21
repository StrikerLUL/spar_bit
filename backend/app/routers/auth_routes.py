from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import status as http_status  # 'status' ist hier eine Route
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import zweifaktor
from ..auth import authenticate, clear_session, create_user, current_user, issue_session, setup_done
from ..db import get_db
from ..loginguard import SANFT_AB, LoginGesperrt, client_ip, fehlversuch, pruefen, zuruecksetzen
from ..models import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    # Nur noetig, wenn fuer dieses Konto ein zweiter Faktor eingerichtet ist.
    code: str = Field(default="", max_length=32)


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

    if user.totp_aktiv and user.totp_geheimnis:
        if not body.code:
            # 428 statt 401: das Passwort stimmt, es fehlt nur der zweite
            # Faktor. Die Oberflaeche kann daran das Codefeld einblenden,
            # ohne die Eingabe von vorn zu verlangen.
            raise HTTPException(
                http_status.HTTP_428_PRECONDITION_REQUIRED,
                "Code aus der Authenticator-App noetig.")
        if not zweifaktor_pruefen(db, user, body.code):
            # Ein falscher zweiter Faktor zaehlt wie ein falsches Passwort -
            # sonst waere er unbegrenzt durchprobierbar.
            fehlversuch(db, ip, body.username)
            raise HTTPException(http_status.HTTP_401_UNAUTHORIZED,
                                "Code stimmt nicht.") from None

    zuruecksetzen(db, ip)
    issue_session(response, user, secure=request.url.scheme == "https")
    return {"ok": True, "username": user.username}


def zweifaktor_pruefen(db: Session, user: User, code: str) -> bool:
    """Code der App - oder einen Ersatzcode, der danach verbraucht ist."""
    if zweifaktor.pruefe(user.totp_geheimnis or "", code):
        return True
    gesucht = zweifaktor.code_hash(code)
    ersatz = list(user.totp_ersatz or [])
    if gesucht in ersatz:
        ersatz.remove(gesucht)
        user.totp_ersatz = ersatz
        db.commit()
        log.warning("Anmeldung mit Ersatzcode - noch %d uebrig", len(ersatz))
        return True
    return False


# --- Zweiter Faktor einrichten -------------------------------------------

class CodeBody(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class PasswortBody(BaseModel):
    password: str


@router.get("/zweifaktor")
def zweifaktor_status(user: User = Depends(current_user)) -> dict:
    return {
        "aktiv": bool(user.totp_aktiv),
        "vorbereitet": bool(user.totp_geheimnis and not user.totp_aktiv),
        "ersatzcodes_uebrig": len(user.totp_ersatz or []),
    }


@router.post("/zweifaktor/start")
def zweifaktor_start(db: Session = Depends(get_db),
                     user: User = Depends(current_user)) -> dict:
    """Geheimnis erzeugen und den QR-Text zurueckgeben.

    Scharf ist es erst nach der Bestaetigung mit einem echten Code -
    sonst sperrt sich aus, wessen App das Geheimnis nie bekommen hat.
    """
    if user.totp_aktiv:
        raise HTTPException(409, "Der zweite Faktor ist bereits aktiv.")
    user.totp_geheimnis = zweifaktor.neues_geheimnis()
    db.commit()
    return {
        "geheimnis": user.totp_geheimnis,
        "otpauth": zweifaktor.otpauth_url(user.totp_geheimnis, user.username),
    }


@router.post("/zweifaktor/bestaetigen")
def zweifaktor_bestaetigen(body: CodeBody, db: Session = Depends(get_db),
                           user: User = Depends(current_user)) -> dict:
    if not user.totp_geheimnis:
        raise HTTPException(409, "Erst einrichten, dann bestaetigen.")
    if not zweifaktor.pruefe(user.totp_geheimnis, body.code):
        raise HTTPException(400, "Der Code stimmt nicht. Geht die Uhr des "
                                 "Telefons richtig?")
    codes = zweifaktor.ersatzcodes()
    user.totp_aktiv = True
    user.totp_ersatz = [zweifaktor.code_hash(c) for c in codes]
    db.commit()
    log.info("Zweiter Faktor fuer '%s' eingeschaltet", user.username)
    # Die Klartext-Codes gibt es genau einmal - danach liegen nur Hashes.
    return {"ok": True, "ersatzcodes": codes}


@router.post("/zweifaktor/aus")
def zweifaktor_aus(body: PasswortBody, db: Session = Depends(get_db),
                   user: User = Depends(current_user)) -> dict:
    """Abschalten geht nur mit dem Passwort.

    Ein offener Laptop soll nicht reichen, um den zweiten Faktor
    loszuwerden - sonst schuetzt er genau so lange, wie niemand am
    Rechner sitzt.
    """
    from ..auth import verify_password
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Passwort stimmt nicht.")
    user.totp_aktiv = False
    user.totp_geheimnis = None
    user.totp_ersatz = []
    db.commit()
    log.info("Zweiter Faktor fuer '%s' abgeschaltet", user.username)
    return {"ok": True}


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
