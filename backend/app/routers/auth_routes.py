from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import status as http_status  # 'status' ist hier eine Route
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import zweifaktor
from ..auth import (
    authenticate,
    clear_session,
    create_user,
    current_user,
    hash_password,
    issue_session,
    nur_admin,
    setup_done,
)
from ..db import get_db
from ..loginguard import SANFT_AB, LoginGesperrt, client_ip, fehlversuch, pruefen, zuruecksetzen
from ..models import ADMIN, ROLLEN, User

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
    rolle = None
    if done:
        try:
            user = current_user(request, db)
            logged_in, username, rolle = True, user.username, user.rolle
        except HTTPException:
            pass
    return {"setup_done": done, "logged_in": logged_in, "username": username,
            "rolle": rolle}


@router.post("/setup")
def setup(body: SetupBody, request: Request, response: Response,
          db: Session = Depends(get_db)) -> dict:
    """Das erste Konto anlegen - und nur das.

    Der Endpunkt ist offen, weil es vor dem ersten Benutzer niemanden
    gibt, der sich anmelden koennte. Genau darum muss er zumachen,
    sobald es einen gibt: sonst waere er ein Weg, sich ohne Anmeldung
    ein Konto anzulegen. Weitere Benutzer legt ein Admin an.
    """
    if setup_done(db):
        raise HTTPException(409, "Die Einrichtung ist abgeschlossen. Weitere "
                                 "Benutzer legt ein Administrator an.")
    user = create_user(db, body.username, body.password)
    issue_session(response, user, secure=request.url.scheme == "https")
    return {"ok": True, "username": user.username, "rolle": user.rolle}


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
    except HTTPException as fehler:
        if fehler.status_code != http_status.HTTP_401_UNAUTHORIZED:
            # Ein abgeschaltetes Konto ist kein Rateversuch: das Passwort
            # stimmt ja. Diese Meldung darf nicht unter "falsch" landen,
            # sonst sucht der Betroffene an der falschen Stelle.
            raise
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
def zweifaktor_status(db: Session = Depends(get_db),
                      user: User = Depends(current_user)) -> dict:
    from ..auth import ADMIN as _ADMIN
    from ..auth import zweifaktor_pflicht
    pflicht = zweifaktor_pflicht(db)
    return {
        "aktiv": bool(user.totp_aktiv),
        "vorbereitet": bool(user.totp_geheimnis and not user.totp_aktiv),
        "ersatzcodes_uebrig": len(user.totp_ersatz or []),
        "pflicht_fuer_admins": pflicht,
        # Damit die Oberflaeche den Hinweis zeigen kann, *bevor* der
        # naechste Admin-Klick in einem 403 endet.
        "faellig": bool(pflicht and user.rolle == _ADMIN and not user.totp_aktiv),
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
    from ..auth import ADMIN as _ADMIN
    from ..auth import verify_password, zweifaktor_pflicht
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Passwort stimmt nicht.")
    # Sonst waere die Pflicht ein Vorschlag: einschalten, abschalten,
    # weiter wie vorher. Wer sie loswerden will, nimmt sie in den
    # Einstellungen zurueck - und das ist eine bewusste Entscheidung
    # fuer die ganze Anlage, keine nebenbei.
    if user.rolle == _ADMIN and zweifaktor_pflicht(db):
        raise HTTPException(
            409, "Diese Anlage verlangt von Administratoren einen zweiten "
                 "Faktor. Erst die Pflicht unter „Logs & System → Sicherheit“ "
                 "abschalten, dann hier.")
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


# --- Benutzer verwalten ---------------------------------------------------

class NeuerBenutzer(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    rolle: str = "mitglied"


class BenutzerAenderung(BaseModel):
    rolle: str | None = None
    aktiv: bool | None = None
    neues_passwort: str | None = Field(default=None, min_length=10, max_length=256)


def _benutzer_dict(u: User, ich: int) -> dict:
    return {"id": u.id, "username": u.username, "rolle": u.rolle,
            "aktiv": bool(u.aktiv), "erstellt": u.created_at,
            "zuletzt_angemeldet": u.last_login,
            "zweifaktor": bool(u.totp_aktiv), "ich": u.id == ich}


@router.get("/benutzer")
def benutzer_liste(db: Session = Depends(get_db),
                   user: User = Depends(current_user)) -> list[dict]:
    """Wer hier Konten hat. Sichtbar fuer alle - wer im selben Haushalt
    wohnt, weiss ohnehin, wer mitliest."""
    from sqlalchemy import select as sel
    return [_benutzer_dict(u, user.id)
            for u in db.scalars(sel(User).order_by(User.id))]


@router.post("/benutzer")
def benutzer_anlegen(body: NeuerBenutzer, db: Session = Depends(get_db),
                     _: User = Depends(nur_admin)) -> dict:
    neu = create_user(db, body.username, body.password, body.rolle)
    return _benutzer_dict(neu, 0)


@router.patch("/benutzer/{benutzer_id}")
def benutzer_aendern(benutzer_id: int, body: BenutzerAenderung,
                     db: Session = Depends(get_db),
                     admin: User = Depends(nur_admin)) -> dict:
    ziel = db.get(User, benutzer_id)
    if ziel is None:
        raise HTTPException(404, "Benutzer nicht gefunden")

    if body.rolle is not None:
        if body.rolle not in ROLLEN:
            raise HTTPException(400, f"Unbekannte Rolle '{body.rolle}'.")
        # Der letzte Admin darf sich nicht selbst entmachten - danach
        # koennte niemand mehr Quellen umstellen oder Benutzer anlegen.
        if ziel.rolle == ADMIN and body.rolle != ADMIN and _admins(db) <= 1:
            raise HTTPException(409, "Das ist der letzte Administrator.")
        ziel.rolle = body.rolle

    if body.aktiv is not None:
        if not body.aktiv and ziel.id == admin.id:
            raise HTTPException(409, "Sich selbst abschalten geht nicht.")
        if not body.aktiv and ziel.rolle == ADMIN and _admins(db) <= 1:
            raise HTTPException(409, "Das ist der letzte Administrator.")
        ziel.aktiv = body.aktiv

    if body.neues_passwort:
        # Ein Admin darf zuruecksetzen, ohne das alte zu kennen - sonst
        # waere ein vergessenes Passwort das Ende des Kontos.
        ziel.password_hash = hash_password(body.neues_passwort)
        log.info("Passwort von '%s' durch Admin zurueckgesetzt", ziel.username)

    db.commit()
    return _benutzer_dict(ziel, admin.id)


@router.delete("/benutzer/{benutzer_id}")
def benutzer_loeschen(benutzer_id: int, db: Session = Depends(get_db),
                      admin: User = Depends(nur_admin)) -> dict:
    """Konto samt allem, was daran haengt.

    Loeschen nimmt Regeln, Kanaele und Wunschliste mit - wer das nicht
    will, schaltet das Konto ab, statt es zu loeschen.
    """
    ziel = db.get(User, benutzer_id)
    if ziel is None:
        raise HTTPException(404, "Benutzer nicht gefunden")
    if ziel.id == admin.id:
        raise HTTPException(409, "Sich selbst löschen geht nicht.")
    if ziel.rolle == ADMIN and _admins(db) <= 1:
        raise HTTPException(409, "Das ist der letzte Administrator.")

    name = ziel.username
    db.delete(ziel)
    db.commit()
    log.info("Benutzer '%s' geloescht", name)
    return {"ok": True, "geloescht": name}


def _admins(db: Session) -> int:
    from sqlalchemy import func
    from sqlalchemy import select as sel
    return db.scalar(sel(func.count()).select_from(User)
                     .where(User.rolle == ADMIN, User.aktiv.is_(True))) or 0
