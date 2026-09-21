"""Zweiter Faktor: die Rechnung stimmt, und man sperrt sich nicht aus."""
import base64
import time

import pytest
from fastapi.testclient import TestClient

from app import zweifaktor as z

# Der Schluessel aus RFC 6238, Anhang B.
RFC_GEHEIMNIS = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


@pytest.mark.parametrize("zeitpunkt,erwartet", [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
])
def test_rechnung_stimmt_mit_dem_standard(zeitpunkt, erwartet):
    """Gegen die Testvektoren aus RFC 6238 - sonst passt keine App dazu."""
    assert z.aktueller_code(RFC_GEHEIMNIS, zeitpunkt) == erwartet


def test_eine_scheibe_versatz_wird_verziehen():
    """Handy-Uhren gehen selten exakt."""
    code = z.aktueller_code(RFC_GEHEIMNIS, 1000)
    assert z.pruefe(RFC_GEHEIMNIS, code, 1000 + 29)
    assert z.pruefe(RFC_GEHEIMNIS, code, 1000 - 29)


def test_zwei_minuten_alt_gilt_nicht_mehr():
    code = z.aktueller_code(RFC_GEHEIMNIS, 1000)
    assert not z.pruefe(RFC_GEHEIMNIS, code, 1000 + 120)


@pytest.mark.parametrize("murks", ["", "abcdef", "12345", "1234567", "  "])
def test_unsinn_wird_abgewiesen(murks):
    assert not z.pruefe(RFC_GEHEIMNIS, murks)


def test_otpauth_url_enthaelt_alles_was_die_app_braucht():
    url = z.otpauth_url("ABCDEFGH", "cillian")
    assert url.startswith("otpauth://totp/SparBit%3Acillian?")
    assert "secret=ABCDEFGH" in url
    assert "issuer=SparBit" in url


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


def einrichten(client) -> tuple[str, list[str]]:
    start = client.post("/api/auth/zweifaktor/start").json()
    code = z.aktueller_code(start["geheimnis"])
    antwort = client.post("/api/auth/zweifaktor/bestaetigen", json={"code": code})
    assert antwort.status_code == 200
    return start["geheimnis"], antwort.json()["ersatzcodes"]


def test_anfangs_ist_nichts_eingerichtet(client):
    assert client.get("/api/auth/zweifaktor").json() == {
        "aktiv": False, "vorbereitet": False, "ersatzcodes_uebrig": 0}


def test_falscher_code_schaltet_nicht_scharf(client):
    client.post("/api/auth/zweifaktor/start")
    antwort = client.post("/api/auth/zweifaktor/bestaetigen", json={"code": "000000"})
    assert antwort.status_code == 400
    assert client.get("/api/auth/zweifaktor").json()["aktiv"] is False


def test_einrichten_liefert_ersatzcodes_genau_einmal(client):
    _, codes = einrichten(client)
    assert len(codes) == 8
    stand = client.get("/api/auth/zweifaktor").json()
    assert stand["aktiv"] is True
    assert stand["ersatzcodes_uebrig"] == 8
    # Ein zweiter Start ist gesperrt, solange der Faktor aktiv ist.
    assert client.post("/api/auth/zweifaktor/start").status_code == 409


def test_anmeldung_verlangt_den_code(client):
    geheimnis, _ = einrichten(client)
    client.post("/api/auth/logout")

    ohne = client.post("/api/auth/login",
                       json={"username": "cillian", "password": "einGutesPasswort1"})
    assert ohne.status_code == 428, "428 sagt: Passwort stimmt, Code fehlt"

    falsch = client.post("/api/auth/login",
                         json={"username": "cillian", "password": "einGutesPasswort1",
                               "code": "000000"})
    assert falsch.status_code == 401

    richtig = client.post("/api/auth/login",
                          json={"username": "cillian", "password": "einGutesPasswort1",
                                "code": z.aktueller_code(geheimnis)})
    assert richtig.status_code == 200


def test_falsches_passwort_verraet_nicht_dass_ein_code_fehlt(client):
    """Sonst waere 428 ein Orakel fuer gueltige Passwoerter."""
    einrichten(client)
    client.post("/api/auth/logout")
    antwort = client.post("/api/auth/login",
                          json={"username": "cillian", "password": "falschfalsch"})
    assert antwort.status_code == 401


def test_ersatzcode_funktioniert_genau_einmal(client):
    """Der Tag, an dem das Handy weg ist - und der Tag danach."""
    _, codes = einrichten(client)
    client.post("/api/auth/logout")

    erste = client.post("/api/auth/login",
                        json={"username": "cillian", "password": "einGutesPasswort1",
                              "code": codes[0]})
    assert erste.status_code == 200
    assert client.get("/api/auth/zweifaktor").json()["ersatzcodes_uebrig"] == 7

    client.post("/api/auth/logout")
    zweite = client.post("/api/auth/login",
                         json={"username": "cillian", "password": "einGutesPasswort1",
                               "code": codes[0]})
    assert zweite.status_code == 401, "verbraucht ist verbraucht"


def test_abschalten_braucht_das_passwort(client):
    einrichten(client)
    assert client.post("/api/auth/zweifaktor/aus",
                       json={"password": "falsch"}).status_code == 401
    assert client.get("/api/auth/zweifaktor").json()["aktiv"] is True

    assert client.post("/api/auth/zweifaktor/aus",
                       json={"password": "einGutesPasswort1"}).status_code == 200
    assert client.get("/api/auth/zweifaktor").json()["aktiv"] is False

    # Danach geht die Anmeldung wieder ohne Code.
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "cillian",
                             "password": "einGutesPasswort1"}).status_code == 200


def test_falscher_code_zaehlt_als_fehlversuch(client):
    """Sonst liesse sich der zweite Faktor unbegrenzt durchprobieren."""
    from app.db import SessionLocal
    from app.models import LoginAttempt

    einrichten(client)
    client.post("/api/auth/logout")
    for _ in range(3):
        client.post("/api/auth/login",
                    json={"username": "cillian", "password": "einGutesPasswort1",
                          "code": "000000"})
    with SessionLocal() as db:
        assert db.query(LoginAttempt).count() >= 3
    assert time.time() > 0
