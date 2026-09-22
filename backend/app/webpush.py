"""Push-Nachrichten an den Browser - ohne Telegram, ohne fremden Dienst.

Bisher brauchte eine Meldung auf dem Handy einen Umweg: Telegram, ntfy,
Gotify, Pushover. Alle vier funktionieren, alle vier heissen: noch ein
Konto, noch eine App, und bei drei von vier laeuft die Meldung ueber
einen fremden Server.

Der Browser kann das selbst. Web Push ist seit Jahren in Chrome, Edge,
Firefox und (seit iOS 16.4) auch in Safari - und liefert an ein Geraet
aus, auf dem SparBit gar nicht offen ist.

Hier steht die Kryptografie dazu, und die ist der Grund, warum das
Ganze nicht in drei Zeilen geht:

* **VAPID** (RFC 8292) beweist dem Push-Dienst, dass die Nachricht von
  dieser Installation kommt. Ein signiertes Token, kein Konto.
* **aes128gcm** (RFC 8291) verschluesselt den Inhalt so, dass der
  Push-Dienst ihn nicht lesen kann. Google und Mozilla leiten die
  Nachricht weiter - erfahren aber nicht, welcher Deal drinsteht.

Beides ist ohne fremde Bibliothek umgesetzt, auf Basis von
`cryptography`, das ohnehin schon fuer verschluesselte Sicherungen da
ist. Fehlt das Paket, ist die Funktion aus und sagt das - genau wie
Pillow beim Bild-Zwischenspeicher.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

# Wie gross ein Datensatz hoechstens wird. 4096 ist der Wert, den alle
# Push-Dienste sicher annehmen.
RECORD_SIZE = 4096


class PushNichtVerfuegbar(RuntimeError):
    """Das Paket 'cryptography' fehlt - Web Push ist dann aus."""


def verfuegbar() -> bool:
    try:
        import cryptography.hazmat.primitives.asymmetric.ec  # noqa: F401
        return True
    except ImportError:
        return False


def b64(daten: bytes) -> str:
    """base64url ohne Polster - die Form, die Web Push ueberall nutzt."""
    return base64.urlsafe_b64encode(daten).decode("ascii").rstrip("=")


def unb64(text: str) -> bytes:
    text = (text or "").strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- Schluesselpaar -------------------------------------------------------

@dataclass
class Schluesselpaar:
    privat: str          # base64url der 32 Byte
    oeffentlich: str     # base64url des unkomprimierten Punktes (65 Byte)


def neues_paar() -> Schluesselpaar:
    """VAPID-Schluesselpaar erzeugen. Einmal je Installation."""
    if not verfuegbar():
        raise PushNichtVerfuegbar(
            "Web Push braucht das Paket 'cryptography'.")
    from cryptography.hazmat.primitives.asymmetric import ec

    schluessel = ec.generate_private_key(ec.SECP256R1())
    roh = schluessel.private_numbers().private_value.to_bytes(32, "big")
    return Schluesselpaar(privat=b64(roh), oeffentlich=b64(_punkt(schluessel)))


def _punkt(privat) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return privat.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint)


def _lade_privat(privat_b64: str):
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.derive_private_key(
        int.from_bytes(unb64(privat_b64), "big"), ec.SECP256R1())


# --- VAPID (RFC 8292) -----------------------------------------------------

def vapid_kopf(endpunkt: str, privat_b64: str, oeffentlich_b64: str,
               kontakt: str = "", stunden: int = 12) -> dict[str, str]:
    """Authorization-Kopfzeile fuer diesen Push-Dienst.

    Das Token gilt fuer die Herkunft des Endpunkts, nicht fuer die
    einzelne Nachricht - darum die Laufzeit von Stunden statt Sekunden.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    teile = urlsplit(endpunkt)
    aud = f"{teile.scheme}://{teile.netloc}"

    kopf = {"typ": "JWT", "alg": "ES256"}
    inhalt = {
        "aud": aud,
        "exp": int(time.time()) + stunden * 3600,
        "sub": kontakt or "mailto:sparbit@localhost",
    }
    signiert = (b64(json.dumps(kopf, separators=(",", ":")).encode()) + "."
                + b64(json.dumps(inhalt, separators=(",", ":")).encode()))

    unterschrift = _lade_privat(privat_b64).sign(
        signiert.encode(), ec.ECDSA(hashes.SHA256()))
    # Der Standard will r und s roh hintereinander, nicht als DER-Struktur.
    r, s = utils.decode_dss_signature(unterschrift)
    roh = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    return {"Authorization": f"vapid t={signiert}.{b64(roh)}, k={oeffentlich_b64}"}


# --- Inhalt verschluesseln (RFC 8291) -------------------------------------

def _hkdf(salz: bytes, ikm: bytes, info: bytes, laenge: int) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=laenge, salt=salz,
                info=info).derive(ikm)


def verschluessele(inhalt: bytes, p256dh_b64: str, auth_b64: str,
                   salz: bytes | None = None,
                   server_privat=None) -> bytes:
    """Nachricht nach RFC 8291 verpacken.

    Die beiden letzten Parameter gibt es nur, damit sich das Ergebnis
    gegen den Testvektor des Standards pruefen laesst - im Betrieb sind
    Salz und Serverschluessel jedes Mal neu.
    """
    if not verfuegbar():
        raise PushNichtVerfuegbar("Web Push braucht das Paket 'cryptography'.")
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    empfaenger_roh = unb64(p256dh_b64)
    geheim = unb64(auth_b64)
    salz = salz or os.urandom(16)

    empfaenger = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), empfaenger_roh)
    server_privat = server_privat or ec.generate_private_key(ec.SECP256R1())
    server_roh = _punkt(server_privat)

    gemeinsam = server_privat.exchange(ec.ECDH(), empfaenger)

    # Erst aus dem gemeinsamen Geheimnis und dem Client-Geheimnis einen
    # Schluessel ableiten, der beide Seiten bindet ...
    prk = _hkdf(geheim, gemeinsam,
                b"WebPush: info\x00" + empfaenger_roh + server_roh, 32)
    # ... daraus dann Schluessel und Nonce fuer diesen einen Datensatz.
    cek = _hkdf(salz, prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salz, prk, b"Content-Encoding: nonce\x00", 12)

    # 0x02 schliesst den Inhalt ab (RFC 8188): es ist der letzte Datensatz.
    verschluesselt = AESGCM(cek).encrypt(nonce, inhalt + b"\x02", None)

    return (salz + struct.pack(">I", RECORD_SIZE)
            + bytes([len(server_roh)]) + server_roh + verschluesselt)


# --- Versand --------------------------------------------------------------

def nachricht(note) -> bytes:
    """Was im Browser ankommt. Klein halten - 4 KB sind die Grenze."""
    text = []
    if note.preis is not None:
        text.append(f"{note.preis:.2f} {note.waehrung}")
    if note.haendler:
        text.append(f"bei {note.haendler}")
    if note.urteil_text:
        text.append(note.urteil_text)

    return json.dumps({
        "titel": ("Gratis: " if note.ist_gratis else "") + (note.titel or "")[:120],
        "text": " · ".join(text)[:200] or (note.beschreibung or "")[:200],
        "url": note.url or "/",
        "bild": note.bild,
        "regel": note.regel,
        "deal_id": note.deal_id,
        "dringend": note.prioritaet == "SOFORT",
    }, ensure_ascii=False).encode("utf-8")


async def sende(http, abo: dict, inhalt: bytes, privat: str, oeffentlich: str,
                kontakt: str = "", dringend: bool = False) -> int:
    """An einen Endpunkt zustellen. Gibt den HTTP-Status zurueck."""
    endpunkt = abo["endpunkt"]
    koerper = verschluessele(inhalt, abo["p256dh"], abo["auth"])

    kopf = vapid_kopf(endpunkt, privat, oeffentlich, kontakt)
    kopf.update({
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        # Wie lange der Dienst die Nachricht aufhebt, wenn das Geraet aus
        # ist. Ein Deal von vorgestern hilft niemandem.
        "TTL": "86400" if not dringend else "3600",
        "Urgency": "high" if dringend else "normal",
    })
    antwort = await http.post(endpunkt, content=koerper, headers=kopf,
                              timeout=20.0)
    return antwort.status_code
