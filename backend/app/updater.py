"""Updates anfordern und ihren Stand anzeigen.

Der Container darf den Host nicht anfassen - kein Docker-Socket, kein git im
Image. Die Arbeit macht deploy/sparbit-autoupdate.sh auf dem Host, gestartet
von einem systemd-Timer. Beide reden ueber die ohnehin vorhandene API:

    Skript holt sich den Auftrag   GET  /api/system/update/auftrag
    Skript meldet das Ergebnis     POST /api/system/update/bericht

Beides mit dem Token aus SPARBIT_UPDATE_TOKEN im Kopf X-SparBit-Update.
Der Umweg ueber HTTP statt ueber ein gemeinsames Verzeichnis spart den
Streit um Dateirechte: im Container schreibt uid 10001, auf dem Host ein
ganz anderer Benutzer.

Ohne Token ist die Funktion aus - das UI sagt das dann auch.
"""
from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import settings
from .db import get_setting, set_setting

log = logging.getLogger(__name__)

# Schluessel in der Settings-Tabelle.
JETZT = "update_angefordert"        # ISO-Zeit der Anforderung, sonst None
AUTO = "update_automatisch"         # bool
STATUS = "update_status"            # Bericht des Host-Skripts


def eingerichtet() -> bool:
    return bool(settings.update_token)


def token_stimmt(mitgeschickt: str | None) -> bool:
    """Zeitunabhaengiger Vergleich - ein Token ist ein Passwort."""
    if not eingerichtet() or not mitgeschickt:
        return False
    return hmac.compare_digest(mitgeschickt, settings.update_token)


def status(db: Session) -> dict:
    if not eingerichtet():
        return {
            "eingerichtet": False,
            "grund": "Der Auto-Updater ist nicht eingerichtet. Siehe README, "
                     "Abschnitt „Updates per Knopfdruck“.",
        }

    bericht = get_setting(db, STATUS) or {}
    commit = bericht.get("commit") or ""
    return {
        "eingerichtet": True,
        "auto": bool(get_setting(db, AUTO, False)),
        "angefordert": bool(get_setting(db, JETZT)),
        "laeuft": bool(bericht.get("laeuft")),
        "zweig": bericht.get("zweig"),
        "commit": commit or None,
        "commit_kurz": commit[:7] or None,
        "betreff": bericht.get("betreff"),
        "commit_datum": bericht.get("commit_datum"),
        "neue_commits": bericht.get("neue_commits"),
        "geprueft_am": bericht.get("geprueft_am"),
        "letztes_update": bericht.get("letztes_update"),
        "protokoll": bericht.get("protokoll"),
    }


def fordere_an(db: Session) -> dict:
    if not eingerichtet():
        raise RuntimeError("Der Auto-Updater ist auf diesem System nicht eingerichtet.")
    bericht = get_setting(db, STATUS) or {}
    if bericht.get("laeuft"):
        return {"ok": True, "hinweis": "Ein Update läuft bereits."}
    set_setting(db, JETZT, datetime.now(timezone.utc).isoformat())
    db.commit()
    log.info("Update angefordert")
    return {"ok": True, "hinweis": "Das Update startet innerhalb einer Minute."}


def setze_auto(db: Session, an: bool) -> dict:
    if not eingerichtet():
        raise RuntimeError("Der Auto-Updater ist auf diesem System nicht eingerichtet.")
    set_setting(db, AUTO, bool(an))
    db.commit()
    log.info("Automatische Updates: %s", "an" if an else "aus")
    return {"ok": True, "auto": bool(an)}


def hole_auftrag(db: Session) -> dict:
    """Was das Host-Skript tun soll. Die Anforderung gilt danach als abgeholt."""
    jetzt = bool(get_setting(db, JETZT))
    if jetzt:
        set_setting(db, JETZT, None)
        db.commit()
    return {"jetzt": jetzt, "auto": bool(get_setting(db, AUTO, False))}


def nimm_bericht(db: Session, bericht: dict) -> dict:
    """Stand vom Host uebernehmen. Was nicht mitkommt, bleibt stehen."""
    alt = dict(get_setting(db, STATUS) or {})
    for schluessel in ("laeuft", "zweig", "commit", "betreff", "commit_datum",
                       "neue_commits", "geprueft_am", "letztes_update",
                       "protokoll"):
        if schluessel in bericht:
            alt[schluessel] = bericht[schluessel]
    # Ein Protokoll voller Build-Ausgabe muss nicht unbegrenzt in der
    # Datenbank liegen; fuer die Fehlersuche reicht das Ende.
    if isinstance(alt.get("protokoll"), str):
        alt["protokoll"] = alt["protokoll"][-20000:]
    set_setting(db, STATUS, alt)
    db.commit()
    return {"ok": True}
