"""Wunschlisten: trennen, was getrennt gehoert - und das Budget im Blick."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    main = lade_app_neu()
    with TestClient(main.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


def artikel(client, liste_id=None, preis=None, ziel=None, name="Ding",
            url="https://shop/1"):
    """Direkt in die Datenbank - der API-Weg wuerde die Seite abrufen."""
    from app.db import SessionLocal
    from app.models import WatchItem

    with SessionLocal() as db:
        eintrag = WatchItem(name=name, url=url, liste_id=liste_id,
                            ziel_preis=ziel, letzter_preis=preis)
        db.add(eintrag)
        db.commit()
        return eintrag.id


def test_liste_anlegen_und_wiederfinden(client):
    liste = client.post("/api/listen", json={
        "name": "Weihnachten", "budget": 300.0,
        "beschreibung": "Geschenke 2026"}).json()
    assert liste["name"] == "Weihnachten"
    assert liste["anzahl"] == 0
    assert liste["budget_rest"] == 300.0

    alle = client.get("/api/listen").json()
    assert [x["name"] for x in alle] == ["Weihnachten"]


def test_budget_sagt_ob_es_noch_reicht(client):
    """Die Frage, die bei Geschenken zuerst kommt."""
    liste = client.post("/api/listen", json={"name": "Umzug", "budget": 500.0}).json()
    artikel(client, liste["id"], preis=180.0, name="Regal")
    artikel(client, liste["id"], preis=240.0, name="Lampe", url="https://shop/2")

    jetzt = client.get("/api/listen").json()[0]
    assert jetzt["anzahl"] == 2
    assert jetzt["summe_aktuell"] == 420.0
    assert jetzt["budget_rest"] == 80.0


def test_ueberzogenes_budget_wird_negativ(client):
    liste = client.post("/api/listen", json={"name": "Klein", "budget": 50.0}).json()
    artikel(client, liste["id"], preis=80.0)
    assert client.get("/api/listen").json()[0]["budget_rest"] == -30.0


def test_artikel_ohne_preis_werden_gezaehlt_nicht_geschaetzt(client):
    liste = client.post("/api/listen", json={"name": "Offen", "budget": 100.0}).json()
    artikel(client, liste["id"], preis=None)
    jetzt = client.get("/api/listen").json()[0]
    assert jetzt["ohne_preis"] == 1
    assert jetzt["summe_aktuell"] == 0


def test_erreichte_ziele_stehen_dabei(client):
    liste = client.post("/api/listen", json={"name": "Technik"}).json()
    artikel(client, liste["id"], preis=90.0, ziel=100.0, name="erreicht")
    artikel(client, liste["id"], preis=150.0, ziel=100.0, name="noch nicht",
            url="https://shop/2")
    assert client.get("/api/listen").json()[0]["ziel_erreicht"] == 1


def test_liste_loeschen_behaelt_die_artikel(client):
    """Loeschen loest eine Ordnung auf, es vernichtet keine Arbeit."""
    liste = client.post("/api/listen", json={"name": "Temporär"}).json()
    artikel(client, liste["id"], preis=10.0)

    bericht = client.delete(f"/api/listen/{liste['id']}").json()
    assert bericht["artikel_behalten"] == 1
    assert client.get("/api/listen").json() == []
    assert len(client.get("/api/watch").json()) == 1


def test_liste_aendern(client):
    liste = client.post("/api/listen", json={"name": "Alt", "budget": 100.0}).json()
    neu = client.patch(f"/api/listen/{liste['id']}",
                       json={"name": "Neu", "budget": 250.0}).json()
    assert neu["name"] == "Neu"
    assert neu["budget"] == 250.0


def test_artikel_ohne_liste_bleiben_wo_sie_waren(client):
    """Wer keine Listen anlegt, merkt von der Funktion nichts."""
    artikel(client, None, preis=20.0)
    assert client.get("/api/listen").json() == []
    assert client.get("/api/watch").json()[0]["liste_id"] is None


def test_listen_kommen_mit_in_die_sicherung(client):
    liste = client.post("/api/listen", json={"name": "Weihnachten",
                                             "budget": 300.0}).json()
    artikel(client, liste["id"], preis=99.0, name="Geschenk")

    sicherung = client.get("/api/system/backup").json()
    assert sicherung["listen"][0]["name"] == "Weihnachten"
    # Verknuepft ueber den Namen, nicht ueber die ID - in einer anderen
    # Installation waere die ID bedeutungslos.
    assert sicherung["wunschliste"][0]["liste"] == "Weihnachten"

    bericht = client.post("/api/system/restore", json=sicherung).json()
    assert bericht["ok"] is True
