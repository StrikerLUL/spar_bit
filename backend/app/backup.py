"""Sicherung und Wiederherstellung.

Die erste Fassung sicherte Regeln, Kanaele, Quellen, Deals und Claims.
Das klang vollstaendig, war es aber nicht - und ausgerechnet das
Fehlende waechst nicht nach:

* die **Wunschliste** samt beobachteter Preise,
* der **Preisverlauf**, aus dem jedes Urteil ("Bestpreis") entsteht,
* die **Interaktionen**, aus denen der Feed gelernt hat, was mich
  interessiert,
* gespeicherte **Suchen**, **Einstellungen** und die **Rueckmeldungen**
  zu Preisfehlern, an denen die Eichung haengt.

Wer nach einem Plattenschaden das alte Backup einspielte, bekam seine
Regeln zurueck und fing beim Rest bei null an.

Verwandtschaften stehen hier bewusst **verschachtelt** statt ueber IDs:
der Preisverlauf haengt unter seinem Deal, die Preispunkte unter ihrem
Wunschlisten-Eintrag. Damit muss beim Einspielen keine ID umgerechnet
werden - was fehlt, wird ueber natuerliche Schluessel erkannt
(url_hash beim Deal, URL beim beobachteten Artikel, fingerprint beim
Claim).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ApiToken,
    Channel,
    ClaimEvent,
    Deal,
    DealOffer,
    Interaction,
    PriceHistory,
    Rule,
    SavedSearch,
    Setting,
    SourceConfig,
    User,
    WatchItem,
    WatchPrice,
)

log = logging.getLogger(__name__)

FORMAT_VERSION = 2

# Die Sitzungs-Signatur gehoert zur Installation, nicht zur Sicherung.
# Wuerde sie mitwandern, waeren nach dem Einspielen alle Anmeldungen der
# Zielinstallation ungueltig - ohne dass jemand danach gefragt haette.
NICHT_WIEDERHERSTELLEN = {"secret_key"}


def _zeilen(db: Session, model, felder: list[str], filter_=None) -> list[dict]:
    stmt = select(model)
    if filter_ is not None:
        stmt = stmt.where(filter_)
    return [{f: getattr(r, f) for f in felder} for r in db.scalars(stmt)]


DEAL_FELDER = [
    "url_hash", "titel", "titel_norm", "beschreibung", "url", "bild",
    "preis", "originalpreis", "rabatt_prozent", "waehrung", "preis_eur",
    "ist_gratis", "haendler", "quelle", "kategorie", "temperatur",
    "first_seen", "last_seen", "bookmarked", "notiz",
    "alarm_preis", "alarm_ausgeloest",
    "urteil", "urteil_text", "urteil_am",
    "fehler_score", "fehler_stufe", "fehler_gruende", "fehler_erwartet_eur",
    "fehler_am", "fehler_gemeldet_am", "fehler_indizien",
    "fehler_urteil_mensch", "fehler_urteil_am",
    "erwachsen", "erwachsen_grund",
    "check_status", "check_text", "check_preis_eur", "check_am",
    "gratis_hinweis",
]

WATCH_FELDER = [
    "name", "url", "ziel_preis", "aktiv", "intervall_minuten",
    "letzter_preis", "waehrung", "bester_preis", "bild", "haendler",
    "letzter_lauf", "letzter_erfolg", "zuletzt_gemeldet", "erstellt_am",
]


def erstelle(db: Session, umfang: str = "voll") -> dict[str, Any]:
    """Sicherung als Datenstruktur. `umfang="einstellungen"` laesst die
    gesammelten Daten weg - fuer den Umzug der Konfiguration."""
    from . import migrations
    from .db import engine

    daten: dict[str, Any] = {
        "version": FORMAT_VERSION,
        "sparbit_version": "1.0.0",
        "exportiert_am": datetime.now(UTC).isoformat(),
        "schema_stand": migrations.version(engine),
        "umfang": umfang,
    }

    # --- Konfiguration (immer dabei) --------------------------------------
    daten["benutzer"] = _zeilen(db, User, ["username", "password_hash", "created_at"])
    daten["einstellungen"] = [
        {"key": s.key, "value": s.value}
        for s in db.scalars(select(Setting))
        if s.key not in NICHT_WIEDERHERSTELLEN
    ]
    daten["regeln"] = _zeilen(db, Rule, [
        "name", "enabled", "priority", "keywords", "required_keywords",
        "blacklist", "max_preis", "min_rabatt_prozent", "nur_gratis",
        "min_temperatur", "sources", "kategorien", "haendler", "channels",
        "min_urteil", "min_fehler_score", "erwachsen",
    ])
    daten["kanaele"] = _zeilen(db, Channel, ["type", "name", "enabled", "config"])
    daten["quellen"] = _zeilen(db, SourceConfig, [
        "id", "enabled", "interval_seconds", "api_key", "options", "verification",
    ])
    daten["gespeicherte_suchen"] = _zeilen(db, SavedSearch, ["name", "filter", "created_at"])
    daten["api_tokens"] = _zeilen(db, ApiToken, ["name", "token_hash", "praefix",
                                                 "erstellt_am", "zuletzt_genutzt"])

    if umfang == "einstellungen":
        daten["wunschliste"] = []
        daten["deals"] = []
        daten["claims"] = []
        return daten

    # --- Wunschliste mit ihren Preispunkten -------------------------------
    wunsch: list[dict] = []
    for item in db.scalars(select(WatchItem)):
        eintrag = {f: getattr(item, f) for f in WATCH_FELDER}
        eintrag["preise"] = [
            {"preis": p.preis, "waehrung": p.waehrung, "ts": p.ts}
            for p in db.scalars(select(WatchPrice).where(WatchPrice.watch_id == item.id))
        ]
        wunsch.append(eintrag)
    daten["wunschliste"] = wunsch

    # --- Deals mit Verlauf, Angeboten und Interaktionen -------------------
    # In einem Rutsch einsammeln statt je Deal nachzufragen: bei 50.000
    # Deals waere das sonst eine Viertelmillion Einzelabfragen.
    verlauf: dict[int, list[dict]] = {}
    for h in db.scalars(select(PriceHistory)):
        verlauf.setdefault(h.deal_id, []).append(
            {"preis": h.preis, "waehrung": h.waehrung, "quelle": h.quelle, "ts": h.ts})

    angebote: dict[int, list[dict]] = {}
    for a in db.scalars(select(DealOffer)):
        angebote.setdefault(a.deal_id, []).append({
            "quelle": a.quelle, "url": a.url, "preis": a.preis,
            "waehrung": a.waehrung, "preis_eur": a.preis_eur,
            "originalpreis": a.originalpreis, "rabatt_prozent": a.rabatt_prozent,
            "haendler": a.haendler, "ist_gratis": a.ist_gratis,
            "zuerst_gesehen": a.zuerst_gesehen, "zuletzt_gesehen": a.zuletzt_gesehen,
        })

    interaktionen: dict[int, list[dict]] = {}
    for i in db.scalars(select(Interaction)):
        interaktionen.setdefault(i.deal_id, []).append({"art": i.art, "ts": i.ts})

    deals: list[dict] = []
    for deal in db.scalars(select(Deal)):
        eintrag = {f: getattr(deal, f) for f in DEAL_FELDER}
        eintrag["verlauf"] = verlauf.get(deal.id, [])
        eintrag["angebote"] = angebote.get(deal.id, [])
        eintrag["interaktionen"] = interaktionen.get(deal.id, [])
        deals.append(eintrag)
    daten["deals"] = deals

    daten["claims"] = _zeilen(db, ClaimEvent, ["platform", "titel", "status",
                                               "detail", "seen_at", "fingerprint"])
    return daten


def als_json(daten: dict[str, Any]) -> str:
    return json.dumps(daten, default=str, ensure_ascii=False)


# --- Verschluesselung -----------------------------------------------------
# Eine Sicherung enthaelt Bot-Token, API-Schluessel und Passwort-Hashes.
# Sie liegt danach in einem Downloadordner, einer Cloud oder auf einem
# USB-Stick - genau dort, wo man sie nicht im Klartext haben will.

SCRYPT_N = 2 ** 15          # ~32 MB Speicher, ca. 0,1 s - bremst das Raten
SCRYPT_R = 8
SCRYPT_P = 1


class VerschluesselungFehlt(RuntimeError):
    """Das Paket 'cryptography' ist nicht installiert."""


def verschluesselung_verfuegbar() -> bool:
    try:
        import cryptography.hazmat.primitives.ciphers.aead  # noqa: F401
        return True
    except ImportError:
        return False


def _schluessel(passwort: str, salt: bytes) -> bytes:
    return hashlib.scrypt(passwort.encode("utf-8"), salt=salt,
                          n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32,
                          maxmem=64 * 1024 * 1024)


def verschluessele(klartext: bytes, passwort: str) -> dict[str, Any]:
    if not verschluesselung_verfuegbar():
        raise VerschluesselungFehlt(
            "Verschluesselte Sicherungen brauchen das Paket 'cryptography'. "
            "Ohne es funktioniert alles andere weiter - die Sicherung ist "
            "dann unverschluesselt.")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    geheim = AESGCM(_schluessel(passwort, salt)).encrypt(nonce, klartext, None)
    return {
        "sparbit_backup": "verschluesselt",
        "verfahren": "AES-256-GCM",
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P},
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "inhalt": base64.b64encode(geheim).decode(),
    }


def entschluessele(huelle: dict[str, Any], passwort: str) -> dict[str, Any]:
    if not verschluesselung_verfuegbar():
        raise VerschluesselungFehlt(
            "Diese Sicherung ist verschluesselt - zum Oeffnen wird das Paket "
            "'cryptography' gebraucht.")
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    kdf = huelle.get("kdf") or {}
    salt = base64.b64decode(huelle["salt"])
    nonce = base64.b64decode(huelle["nonce"])
    schluessel = hashlib.scrypt(
        passwort.encode("utf-8"), salt=salt,
        n=int(kdf.get("n", SCRYPT_N)), r=int(kdf.get("r", SCRYPT_R)),
        p=int(kdf.get("p", SCRYPT_P)), dklen=32, maxmem=64 * 1024 * 1024)
    try:
        klartext = AESGCM(schluessel).decrypt(nonce, base64.b64decode(huelle["inhalt"]), None)
    except InvalidTag as exc:
        raise ValueError("Falsches Passwort oder beschaedigte Datei.") from exc
    return json.loads(klartext)


def ist_verschluesselt(daten: dict[str, Any]) -> bool:
    return daten.get("sparbit_backup") == "verschluesselt"


# --- Einspielen -----------------------------------------------------------

def _zeit(wert) -> datetime | None:
    if wert is None or isinstance(wert, datetime):
        return wert
    try:
        gelesen = datetime.fromisoformat(str(wert))
    except ValueError:
        return None
    return gelesen if gelesen.tzinfo else gelesen.replace(tzinfo=UTC)


def _mit_zeiten(zeile: dict, felder: list[str]) -> dict:
    """Zeitstempel aus JSON sind Text - daraus wieder datetime machen."""
    return {k: (_zeit(v) if k.endswith(("_am", "_at", "_seen", "_lauf",
                                        "_erfolg", "ts")) else v)
            for k, v in zeile.items() if k in felder}


def spiele_ein(db: Session, daten: dict[str, Any]) -> dict[str, int]:
    """Sicherung einspielen.

    Konfiguration wird **ersetzt** (Regeln, Kanaele, Suchen), gesammelte
    Daten werden **ergaenzt**: was schon da ist, bleibt; was fehlt, kommt
    dazu. So macht ein Einspielen nichts kaputt, das seit der Sicherung
    dazugekommen ist.
    """
    if not isinstance(daten, dict) or "version" not in daten:
        raise ValueError("Das sieht nicht nach einer SparBit-Sicherung aus.")

    bericht = dict.fromkeys((
        "regeln", "kanaele", "quellen", "suchen", "einstellungen", "benutzer",
        "wunschliste", "wunschpreise", "deals", "verlauf", "angebote",
        "interaktionen", "claims", "tokens"), 0)

    # --- Benutzer: nur, wenn es noch keinen gibt --------------------------
    # Sonst wuerde eine eingespielte Sicherung den Zugang der laufenden
    # Installation ueberschreiben - und im schlimmsten Fall aussperren.
    if daten.get("benutzer") and not db.scalar(select(User).limit(1)):
        for zeile in daten["benutzer"]:
            db.add(User(username=zeile["username"],
                        password_hash=zeile["password_hash"],
                        created_at=_zeit(zeile.get("created_at")) or datetime.now(UTC)))
            bericht["benutzer"] += 1

    for zeile in daten.get("einstellungen") or []:
        key = zeile.get("key")
        if not key or key in NICHT_WIEDERHERSTELLEN:
            continue
        vorhanden = db.get(Setting, key)
        if vorhanden:
            vorhanden.value = zeile.get("value")
        else:
            db.add(Setting(key=key, value=zeile.get("value")))
        bericht["einstellungen"] += 1

    if isinstance(daten.get("regeln"), list):
        db.query(Rule).delete()
        for zeile in daten["regeln"]:
            db.add(Rule(**{k: v for k, v in zeile.items() if k != "id"}))
            bericht["regeln"] += 1

    if isinstance(daten.get("kanaele"), list):
        db.query(Channel).delete()
        for zeile in daten["kanaele"]:
            db.add(Channel(**{k: v for k, v in zeile.items() if k != "id"}))
            bericht["kanaele"] += 1

    if isinstance(daten.get("gespeicherte_suchen"), list):
        db.query(SavedSearch).delete()
        for zeile in daten["gespeicherte_suchen"]:
            db.add(SavedSearch(name=zeile.get("name", "Suche"),
                               filter=zeile.get("filter") or {},
                               created_at=_zeit(zeile.get("created_at")) or datetime.now(UTC)))
            bericht["suchen"] += 1

    for zeile in daten.get("quellen") or []:
        cfg = db.get(SourceConfig, zeile.get("id"))
        if cfg is None:
            continue          # Quelle gibt es in dieser Version nicht mehr
        for key in ("enabled", "interval_seconds", "api_key", "options", "verification"):
            if key in zeile:
                setattr(cfg, key, zeile[key])
        bericht["quellen"] += 1

    for zeile in daten.get("api_tokens") or []:
        if db.scalar(select(ApiToken).where(ApiToken.token_hash == zeile["token_hash"])):
            continue
        db.add(ApiToken(name=zeile.get("name", "Token"),
                        token_hash=zeile["token_hash"],
                        praefix=zeile.get("praefix", ""),
                        erstellt_am=_zeit(zeile.get("erstellt_am")) or datetime.now(UTC),
                        zuletzt_genutzt=_zeit(zeile.get("zuletzt_genutzt"))))
        bericht["tokens"] += 1

    db.flush()

    # --- Wunschliste ------------------------------------------------------
    for zeile in daten.get("wunschliste") or []:
        item = db.scalar(select(WatchItem).where(WatchItem.url == zeile.get("url")))
        if item is None:
            item = WatchItem(**_mit_zeiten(zeile, WATCH_FELDER))
            db.add(item)
            db.flush()
            bericht["wunschliste"] += 1
        bekannt = {p.ts for p in db.scalars(
            select(WatchPrice).where(WatchPrice.watch_id == item.id))}
        for punkt in zeile.get("preise") or []:
            ts = _zeit(punkt.get("ts"))
            if ts is None or ts in bekannt:
                continue
            db.add(WatchPrice(watch_id=item.id, preis=punkt["preis"],
                              waehrung=punkt.get("waehrung", "EUR"), ts=ts))
            bericht["wunschpreise"] += 1

    # --- Deals ------------------------------------------------------------
    for zeile in daten.get("deals") or []:
        url_hash = zeile.get("url_hash")
        if not url_hash:
            continue
        deal = db.scalar(select(Deal).where(Deal.url_hash == url_hash))
        if deal is None:
            felder = _mit_zeiten(zeile, DEAL_FELDER)
            felder.setdefault("titel_norm", (felder.get("titel") or "").lower())
            deal = Deal(url_hash=url_hash, **{k: v for k, v in felder.items()
                                              if k != "url_hash"})
            db.add(deal)
            db.flush()
            bericht["deals"] += 1

        vorhanden = {h.ts for h in db.scalars(
            select(PriceHistory).where(PriceHistory.deal_id == deal.id))}
        for punkt in zeile.get("verlauf") or []:
            ts = _zeit(punkt.get("ts"))
            if ts is None or ts in vorhanden:
                continue
            db.add(PriceHistory(deal_id=deal.id, preis=punkt["preis"],
                                waehrung=punkt.get("waehrung", "EUR"),
                                quelle=punkt.get("quelle"), ts=ts))
            bericht["verlauf"] += 1

        quellen = {a.quelle for a in db.scalars(
            select(DealOffer).where(DealOffer.deal_id == deal.id))}
        for angebot in zeile.get("angebote") or []:
            if angebot.get("quelle") in quellen:
                continue
            db.add(DealOffer(deal_id=deal.id, **_mit_zeiten(angebot, [
                "quelle", "url", "preis", "waehrung", "preis_eur",
                "originalpreis", "rabatt_prozent", "haendler", "ist_gratis",
                "zuerst_gesehen", "zuletzt_gesehen"])))
            bericht["angebote"] += 1

        gesehen = {(i.art, i.ts) for i in db.scalars(
            select(Interaction).where(Interaction.deal_id == deal.id))}
        for spur in zeile.get("interaktionen") or []:
            ts = _zeit(spur.get("ts"))
            if ts is None or (spur.get("art"), ts) in gesehen:
                continue
            db.add(Interaction(deal_id=deal.id, art=spur["art"], ts=ts))
            bericht["interaktionen"] += 1

    for zeile in daten.get("claims") or []:
        finger = zeile.get("fingerprint")
        if not finger or db.scalar(select(ClaimEvent).where(
                ClaimEvent.fingerprint == finger)):
            continue
        db.add(ClaimEvent(platform=zeile.get("platform", "?"),
                          titel=zeile.get("titel", ""),
                          status=zeile.get("status", "claimed"),
                          detail=zeile.get("detail"),
                          seen_at=_zeit(zeile.get("seen_at")) or datetime.now(UTC),
                          fingerprint=finger))
        bericht["claims"] += 1

    db.commit()
    log.info("Sicherung eingespielt: %s", bericht)
    return bericht


# --- Automatische Sicherung ----------------------------------------------

def ordner() -> Path:
    from .config import settings
    return settings.data_dir / "backups"


def schreibe_datei(db: Session, passwort: str = "") -> Path:
    """Sicherung in den Backup-Ordner schreiben. Gibt den Pfad zurueck."""
    ziel = ordner()
    ziel.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    daten = erstelle(db)
    if passwort and verschluesselung_verfuegbar():
        inhalt = json.dumps(verschluessele(als_json(daten).encode("utf-8"), passwort))
        name = f"sparbit-{stempel}.json.enc"
    else:
        if passwort:
            log.warning("Backup-Passwort gesetzt, aber 'cryptography' fehlt - "
                        "die Sicherung wird unverschluesselt geschrieben.")
        inhalt = als_json(daten)
        name = f"sparbit-{stempel}.json"

    pfad = ziel / name
    # Erst vollstaendig danebenlegen, dann umbenennen: ein Absturz mitten
    # im Schreiben darf keine halbe Sicherung hinterlassen, die aussieht
    # wie eine ganze.
    temp = pfad.with_suffix(pfad.suffix + ".teil")
    temp.write_text(inhalt, encoding="utf-8")
    os.replace(temp, pfad)
    return pfad


def raeume_auf(behalten: int) -> int:
    """Alte Sicherungen loeschen, die neuesten `behalten` bleiben."""
    ziel = ordner()
    if not ziel.is_dir() or behalten <= 0:
        return 0
    dateien = sorted(
        [p for p in ziel.glob("sparbit-*.json*") if not p.name.endswith(".teil")],
        key=lambda p: p.name, reverse=True)
    entfernt = 0
    for alt in dateien[behalten:]:
        try:
            alt.unlink()
            entfernt += 1
        except OSError as exc:
            log.warning("Alte Sicherung %s nicht loeschbar: %s", alt.name, exc)
    return entfernt


def vorhandene() -> list[dict[str, Any]]:
    ziel = ordner()
    if not ziel.is_dir():
        return []
    heraus = []
    for pfad in sorted(ziel.glob("sparbit-*.json*"), reverse=True):
        if pfad.name.endswith(".teil"):
            continue
        stat = pfad.stat()
        heraus.append({
            "name": pfad.name,
            "bytes": stat.st_size,
            "erstellt": datetime.fromtimestamp(stat.st_mtime, UTC),
            "verschluesselt": pfad.name.endswith(".enc"),
        })
    return heraus
