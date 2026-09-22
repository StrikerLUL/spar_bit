"""Web Push: die Meldung landet direkt im Browser.

Der einzige Kanal ohne Konfigurationsfeld - und ohne fremden Dienst in
der Mitte. Wo man bei Telegram ein Konto, einen Bot und eine Chat-ID
braucht, klickt man hier einmal "Benachrichtigungen erlauben".

Der Kanal schickt an alle angemeldeten Geraete. Ein Endpunkt, den der
Push-Dienst mit 404 oder 410 beantwortet, ist erloschen (Browser
deinstalliert, Berechtigung entzogen) und wird gleich entfernt - sonst
sammeln sich Karteileichen, an die jede Meldung vergeblich geht.
"""
from __future__ import annotations

import logging
from typing import Any

from .. import webpush
from ..db import SessionLocal, get_setting
from ..models import PushAbo, utcnow
from .base import Channel, Notification, register

log = logging.getLogger(__name__)


class BrowserPush(Channel):
    type = "browser"
    display_name = "Browser (Web Push)"
    beschreibung = ("Meldungen direkt im Browser - auch auf dem Handy, wenn "
                    "die Seite dort installiert ist. Kein Konto, kein "
                    "fremder Dienst. Geräte meldest du unter Kanäle an.")

    # Bewusst leer: was dieser Kanal braucht, ist kein Feld, sondern eine
    # Erlaubnis im Browser.
    options_schema = []

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        if not webpush.verfuegbar():
            raise ValueError("Web Push braucht das Paket 'cryptography'.")

        with SessionLocal() as db:
            privat = get_setting(db, "vapid_privat")
            oeffentlich = get_setting(db, "vapid_oeffentlich")
            kontakt = str(get_setting(db, "vapid_kontakt") or "")
            abos = [{"id": a.id, "endpunkt": a.endpunkt, "p256dh": a.p256dh,
                     "auth": a.auth} for a in db.query(PushAbo).all()]

        if not (privat and oeffentlich):
            raise ValueError("Noch kein Schlüsselpaar - unter Kanäle einmal "
                             "'Gerät anmelden' drücken.")
        if not abos:
            raise ValueError("Kein Gerät angemeldet.")

        inhalt = webpush.nachricht(note)
        erloschen: list[int] = []
        fehler: list[str] = []
        zugestellt = 0

        for abo in abos:
            try:
                status = await webpush.sende(
                    http, abo, inhalt, privat, oeffentlich, kontakt,
                    dringend=note.prioritaet == "SOFORT")
            except Exception as exc:
                fehler.append(f"{type(exc).__name__}: {exc}")
                continue

            if status in (404, 410):
                # Der Push-Dienst sagt: diesen Empfaenger gibt es nicht mehr.
                erloschen.append(abo["id"])
            elif 200 <= status < 300:
                zugestellt += 1
            else:
                fehler.append(f"HTTP {status}")

        with SessionLocal() as db:
            if erloschen:
                db.query(PushAbo).filter(PushAbo.id.in_(erloschen)).delete(
                    synchronize_session=False)
                log.info("%d erloschene Push-Abos entfernt", len(erloschen))
            if zugestellt:
                db.query(PushAbo).filter(~PushAbo.id.in_(erloschen)).update(
                    {PushAbo.zuletzt_ok: utcnow()}, synchronize_session=False)
            db.commit()

        if not zugestellt:
            grund = fehler[0] if fehler else "alle Geräte erloschen"
            raise ValueError(f"Keine Zustellung: {grund}")


register(BrowserPush())
