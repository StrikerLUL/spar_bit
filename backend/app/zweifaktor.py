"""Zweiter Faktor per Authenticator-App (TOTP, RFC 6238).

Warum ueberhaupt: ein Passwort schuetzt so gut, wie es geheim bleibt.
Steht SparBit unter einer Domain im Netz, reicht ein wiederverwendetes
Passwort aus einem fremden Datenleck - und die Bremse gegen das
Durchprobieren hilft dagegen nicht, weil gar nichts geraten wird.

Bewusst ohne neue Abhaengigkeit: TOTP ist ein HMAC ueber die
Zeitscheibe, und hmac, hashlib und base64 bringt Python mit. Ein
Paket fuer dreissig Zeilen waere hier mehr Wartungslast als Hilfe.

Der Zeitversatz von einer Scheibe nach vorn und hinten ist Absicht:
Handy-Uhren gehen selten exakt, und ein Code, der abgelehnt wird,
obwohl er stimmt, treibt die Leute dazu, die ganze Funktion wieder
abzuschalten.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
from urllib.parse import quote

log = logging.getLogger(__name__)

STELLEN = 6
SCHEIBE = 30          # Sekunden je Code
TOLERANZ = 1          # erlaubte Scheiben vor und nach jetzt


def neues_geheimnis() -> str:
    """160 Bit, base32 - das Format, das jede Authenticator-App versteht."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code(geheimnis: str, zaehler: int) -> str:
    polster = "=" * (-len(geheimnis) % 8)
    schluessel = base64.b32decode(geheimnis.upper() + polster, casefold=True)
    mac = hmac.new(schluessel, struct.pack(">Q", zaehler), hashlib.sha1).digest()
    versatz = mac[-1] & 0x0F
    zahl = struct.unpack(">I", mac[versatz:versatz + 4])[0] & 0x7FFFFFFF
    return str(zahl % (10 ** STELLEN)).zfill(STELLEN)


def aktueller_code(geheimnis: str, jetzt: float | None = None) -> str:
    return _code(geheimnis, int((jetzt or time.time()) // SCHEIBE))


def pruefe(geheimnis: str, eingabe: str, jetzt: float | None = None) -> bool:
    """Code pruefen - mit einer Scheibe Toleranz in beide Richtungen."""
    eingabe = (eingabe or "").strip().replace(" ", "")
    if not eingabe.isdigit() or len(eingabe) != STELLEN:
        return False
    zaehler = int((jetzt or time.time()) // SCHEIBE)
    for versatz in range(-TOLERANZ, TOLERANZ + 1):
        # compare_digest: sonst verraet die Laufzeit, wie viele Stellen
        # schon stimmen.
        if hmac.compare_digest(_code(geheimnis, zaehler + versatz), eingabe):
            return True
    return False


def otpauth_url(geheimnis: str, benutzer: str, ausgeber: str = "SparBit") -> str:
    """Die Adresse hinter dem QR-Code."""
    label = quote(f"{ausgeber}:{benutzer}", safe="")
    return (f"otpauth://totp/{label}?secret={geheimnis}"
            f"&issuer={quote(ausgeber)}&algorithm=SHA1"
            f"&digits={STELLEN}&period={SCHEIBE}")


def ersatzcodes(anzahl: int = 8) -> list[str]:
    """Einmal-Codes fuer den Tag, an dem das Handy weg ist.

    Ohne sie ist ein verlorenes Telefon gleichbedeutend mit einer
    ausgesperrten Installation - und der Ausweg waere, die Datenbank von
    Hand anzufassen.
    """
    return [f"{secrets.randbelow(10**5):05d}-{secrets.randbelow(10**5):05d}"
            for _ in range(anzahl)]


def code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()
