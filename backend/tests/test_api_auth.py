"""Anmeldung durch den echten Endpunkt - inklusive Bremse."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    # Module neu laden, damit sie das frische Datenverzeichnis sehen.
    import importlib, sys
    for name in list(sys.modules):
        if name.startswith("app."):
            del sys.modules[name]
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def test_setup_und_anmeldung(client):
    assert client.get("/api/auth/status").json()["setup_done"] is False

    antwort = client.post("/api/auth/setup",
                          json={"username": "cillian", "password": "einGutesPasswort1"})
    assert antwort.status_code == 200
    assert client.get("/api/auth/status").json()["logged_in"] is True


def test_zu_kurzes_passwort_wird_abgelehnt(client):
    antwort = client.post("/api/auth/setup",
                          json={"username": "cillian", "password": "kurz"})
    assert antwort.status_code == 422


def test_zweiter_benutzer_nicht_moeglich(client):
    client.post("/api/auth/setup",
                json={"username": "cillian", "password": "einGutesPasswort1"})
    antwort = client.post("/api/auth/setup",
                          json={"username": "wer", "password": "einGutesPasswort1"})
    assert antwort.status_code == 409


def test_falsches_passwort_wird_gebremst(client):
    client.post("/api/auth/setup",
                json={"username": "cillian", "password": "einGutesPasswort1"})
    client.post("/api/auth/logout")

    # Die ersten vier Versuche laufen normal durch ...
    for _ in range(4):
        antwort = client.post("/api/auth/login",
                              json={"username": "cillian", "password": "falsch"})
        assert antwort.status_code == 401

    # ... ab dem fuenften wird gebremst.
    client.post("/api/auth/login", json={"username": "cillian", "password": "falsch"})
    antwort = client.post("/api/auth/login",
                          json={"username": "cillian", "password": "falsch"})
    assert antwort.status_code == 429
    assert "Retry-After" in antwort.headers
    assert "warten" in antwort.json()["detail"]


def test_geschuetzte_route_ohne_anmeldung(client):
    client.post("/api/auth/setup",
                json={"username": "cillian", "password": "einGutesPasswort1"})
    client.post("/api/auth/logout")
    assert client.get("/api/deals").status_code == 401


def test_bild_lokal_wird_in_beiden_ansichten_geliefert(client):
    """Fehlt das Feld, faellt das UI still auf die externe Bild-URL zurueck -
    und der ganze Cache waere wirkungslos."""
    client.post("/api/auth/setup",
                json={"username": "cillian", "password": "einGutesPasswort1"})

    import app.db as db_mod
    from app.models import Deal
    with db_mod.SessionLocal() as db:
        db.add(Deal(url_hash="h1", titel="Ein Deal", titel_norm="ein deal",
                    url="https://x.de/1", quelle="mydealz", waehrung="EUR",
                    bild="https://cdn.de/a.png", bild_lokal="abc123.jpg",
                    tags=[], also_from=[], roh={}))
        db.commit()
        deal_id = db.query(Deal).one().id

    liste = client.get("/api/deals").json()["items"][0]
    assert liste["bild_lokal"] == "abc123.jpg"

    detail = client.get(f"/api/deals/{deal_id}/detail").json()
    assert detail["bild_lokal"] == "abc123.jpg"
