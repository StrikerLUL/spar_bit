"""Web Push: die Rechnung muss auf das Byte stimmen.

Anders als bei einem Webhook gibt es hier keine Fehlermeldung, die
weiterhilft: ein Push-Dienst nimmt die Nachricht an und liefert sie aus -
und der Browser verwirft sie stumm, wenn die Verschluesselung nicht
stimmt. Darum wird gegen den Testvektor des Standards geprueft.
"""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from app import webpush


def unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- RFC 8291, Abschnitt 5 ------------------------------------------------

def test_verschluesselung_entspricht_dem_standard():
    """Der vollstaendige Testvektor aus RFC 8291.

    Stimmt hier ein Byte nicht, kommt im Browser nie etwas an - ohne
    dass irgendwo ein Fehler auftaucht.
    """
    from cryptography.hazmat.primitives.asymmetric import ec

    klartext = b"When I grow up, I want to be a watermelon"
    ua_public = ("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4"
                 "bjyPjs7Vd8pZGH6SRpkNtoIAiw4")
    ua_auth = "BTBZMqHH6r4Tts7J_aSIgg"
    as_privat = ec.derive_private_key(
        int.from_bytes(unb64("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
        ec.SECP256R1())
    salz = unb64("DGv6ra1nlYgDCS1FRnbzlw")

    erwartet = unb64(
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
        "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
        "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")

    assert webpush.verschluessele(klartext, ua_public, ua_auth,
                                  salz=salz, server_privat=as_privat) == erwartet


def test_zwei_nachrichten_sind_nie_gleich():
    """Salz und Serverschluessel muessen jedes Mal neu sein."""
    paar = webpush.neues_paar()
    empfaenger = webpush.neues_paar()
    eins = webpush.verschluessele(b"hallo", empfaenger.oeffentlich, webpush.b64(b"0" * 16))
    zwei = webpush.verschluessele(b"hallo", empfaenger.oeffentlich, webpush.b64(b"0" * 16))
    assert eins != zwei
    assert paar.privat != paar.oeffentlich


# --- VAPID ----------------------------------------------------------------

def test_vapid_kopf_ist_pruefbar_signiert():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    paar = webpush.neues_paar()
    kopf = webpush.vapid_kopf("https://fcm.googleapis.com/fcm/send/abc",
                              paar.privat, paar.oeffentlich,
                              "mailto:ich@example.de")
    wert = kopf["Authorization"]
    assert wert.startswith("vapid t=")
    token = wert.split("t=")[1].split(",")[0]
    kopfteil, inhaltteil, signatur = token.split(".")

    inhalt = json.loads(unb64(inhaltteil))
    # Das Token gilt fuer die Herkunft des Dienstes, nicht fuer die URL.
    assert inhalt["aud"] == "https://fcm.googleapis.com"
    assert inhalt["sub"] == "mailto:ich@example.de"
    assert json.loads(unb64(kopfteil))["alg"] == "ES256"

    # Und die Unterschrift muss gegen den oeffentlichen Schluessel passen.
    roh = unb64(signatur)
    der = utils.encode_dss_signature(int.from_bytes(roh[:32], "big"),
                                     int.from_bytes(roh[32:], "big"))
    oeffentlich = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), unb64(paar.oeffentlich))
    oeffentlich.verify(der, f"{kopfteil}.{inhaltteil}".encode(),
                       ec.ECDSA(hashes.SHA256()))


def test_nachricht_passt_in_die_grenze():
    """4 KB sind das Maximum, das Push-Dienste sicher annehmen."""
    from app.notify.base import Notification

    note = Notification(titel="X" * 400, url="https://shop/" + "y" * 400,
                        quelle="test", beschreibung="Z" * 2000,
                        preis=9.99, haendler="H" * 200, regel="R" * 200)
    assert len(webpush.nachricht(note)) < 4096


# --- Der Weg durch die API ------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    main = lade_app_neu()
    with TestClient(main.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


def _echtes_abo(endpunkt="https://fcm.googleapis.com/fcm/send/geraet-eins"):
    """Ein Abo mit echtem Schluessel - ein ausgedachter Punkt liegt nicht
    auf der Kurve, und die Verschluesselung lehnt ihn zu Recht ab."""
    paar = webpush.neues_paar()
    return {"endpunkt": endpunkt, "p256dh": paar.oeffentlich,
            "auth": webpush.b64(b"b" * 16), "geraet": "Firefox auf Linux"}


ABO = _echtes_abo()


def test_schluessel_entsteht_beim_ersten_abruf(client):
    erste = client.get("/api/push/schluessel").json()
    assert erste["verfuegbar"] is True
    assert erste["schluessel"]
    # Und bleibt danach derselbe - sonst muesste sich jedes Geraet neu
    # anmelden, sobald eines dazukommt.
    assert client.get("/api/push/schluessel").json()["schluessel"] == erste["schluessel"]


def test_geraet_anmelden_und_wieder_weg(client):
    client.get("/api/push/schluessel")
    antwort = client.post("/api/push/abo", json=ABO).json()
    assert antwort["neu"] is True

    liste = client.get("/api/push/abos").json()
    assert len(liste) == 1
    assert liste[0]["geraet"] == "Firefox auf Linux"
    assert liste[0]["host"] == "fcm.googleapis.com"

    assert client.delete(f"/api/push/abo/{antwort['id']}").json()["ok"] is True
    assert client.get("/api/push/abos").json() == []


def test_dasselbe_geraet_zweimal_ist_kein_fehler(client):
    """Der Browser erneuert seinen Endpunkt von sich aus."""
    client.get("/api/push/schluessel")
    client.post("/api/push/abo", json=ABO)
    zweite = client.post("/api/push/abo", json={**ABO, "auth": webpush.b64(b"c" * 16)})
    assert zweite.json()["neu"] is False
    assert len(client.get("/api/push/abos").json()) == 1


def test_abos_sind_nicht_oeffentlich(client):
    client.cookies.clear()
    assert client.get("/api/push/abos").status_code == 401
    assert client.post("/api/push/abo", json=ABO).status_code == 401


@pytest.mark.asyncio
async def test_erloschene_geraete_fliegen_raus(client):
    """410 heisst: diesen Empfaenger gibt es nicht mehr. Ohne das sammeln
    sich Karteileichen, an die jede Meldung vergeblich geht."""
    from app.db import SessionLocal
    from app.models import PushAbo
    from app.notify.base import Notification
    from app.notify.browser import BrowserPush

    client.get("/api/push/schluessel")
    client.post("/api/push/abo", json=ABO)
    client.post("/api/push/abo", json=_echtes_abo(ABO["endpunkt"] + "-zwei"))

    class Http:
        async def post(self, url, **kwargs):
            class Antwort:
                status_code = 410 if url.endswith("-zwei") else 201
            return Antwort()

    await BrowserPush().send({}, Notification(titel="Test", url="https://x",
                                              quelle="test"), Http())

    with SessionLocal() as db:
        uebrig = [a.endpunkt for a in db.query(PushAbo).all()]
    assert uebrig == [ABO["endpunkt"]]
