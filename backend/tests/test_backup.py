"""Was eine Sicherung koennen muss - vor allem: nichts vergessen.

Die alte Fassung sicherte Regeln, Kanaele, Quellen, Deals und Claims.
Wunschliste, Preisverlauf, Interaktionen, Suchen und Einstellungen
fehlten - also genau das, was nach einem Plattenschaden nicht
nachwaechst. Diese Tests halten fest, dass der Weg hin und zurueck
fuehrt.
"""
import json

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


def fuelle(client):
    """Eine Installation, wie sie nach ein paar Wochen aussieht."""
    from app.db import SessionLocal
    from app.models import (
        Deal,
        Interaction,
        PriceHistory,
        SavedSearch,
        WatchItem,
        WatchPrice,
        utcnow,
    )

    with SessionLocal() as db:
        deal = Deal(url_hash="hash-eins", titel="LEGO Technic",
                    titel_norm="lego technic", url="https://shop/1",
                    preis=79.99, preis_eur=79.99, waehrung="EUR",
                    haendler="amazon", quelle="mydealz", bookmarked=True)
        db.add(deal)
        db.flush()
        db.add(PriceHistory(deal_id=deal.id, preis=99.0, waehrung="EUR"))
        db.add(PriceHistory(deal_id=deal.id, preis=79.99, waehrung="EUR"))
        db.add(Interaction(deal_id=deal.id, art="gemerkt"))
        db.add(Interaction(deal_id=deal.id, art="geoeffnet"))

        wunsch = WatchItem(name="Kopfhoerer", url="https://shop/kopfhoerer",
                           ziel_preis=150.0, letzter_preis=189.0)
        db.add(wunsch)
        db.flush()
        db.add(WatchPrice(watch_id=wunsch.id, preis=199.0))
        db.add(WatchPrice(watch_id=wunsch.id, preis=189.0))

        db.add(SavedSearch(name="Nur Bestpreise", filter={"urteil": "bestpreis"}))
        db.commit()
        assert utcnow() is not None

    client.post("/api/rules", json={"name": "LEGO", "keywords": ["lego"],
                                    "priority": "SOFORT"})


def test_sicherung_enthaelt_was_nicht_nachwaechst(client):
    fuelle(client)
    daten = client.get("/api/system/backup").json()

    assert daten["version"] == 2
    assert len(daten["wunschliste"]) == 1
    assert len(daten["wunschliste"][0]["preise"]) == 2
    assert len(daten["gespeicherte_suchen"]) == 1
    assert daten["benutzer"][0]["username"] == "cillian"

    deal = daten["deals"][0]
    assert len(deal["verlauf"]) == 2
    assert {i["art"] for i in deal["interaktionen"]} == {"gemerkt", "geoeffnet"}


def test_umfang_einstellungen_laesst_die_daten_weg(client):
    fuelle(client)
    daten = client.get("/api/system/backup?umfang=einstellungen").json()
    assert daten["deals"] == []
    assert daten["wunschliste"] == []
    assert len(daten["regeln"]) == 1


def test_hin_und_zurueck_stellt_alles_wieder_her(client, tmp_path, monkeypatch):
    fuelle(client)
    sicherung = client.get("/api/system/backup").json()

    # Zweite, leere Installation - wie nach einem Plattenschaden.
    from conftest import lade_app_neu
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path / "neu"))
    main = lade_app_neu()
    with TestClient(main.app) as neu:
        neu.post("/api/auth/setup",
                 json={"username": "cillian", "password": "einGutesPasswort1"})
        bericht = neu.post("/api/system/restore", json=sicherung).json()
        assert bericht["ok"] is True
        assert bericht["deals"] == 1
        assert bericht["verlauf"] == 2
        assert bericht["interaktionen"] == 2
        assert bericht["wunschliste"] == 1
        assert bericht["wunschpreise"] == 2
        assert bericht["suchen"] == 1
        assert bericht["regeln"] == 1

        kontrolle = neu.get("/api/system/backup").json()
        assert kontrolle["deals"][0]["titel"] == "LEGO Technic"
        assert len(kontrolle["deals"][0]["verlauf"]) == 2
        assert kontrolle["wunschliste"][0]["name"] == "Kopfhoerer"


def test_zweimal_einspielen_verdoppelt_nichts(client):
    fuelle(client)
    sicherung = client.get("/api/system/backup").json()
    client.post("/api/system/restore", json=sicherung)
    zweiter = client.post("/api/system/restore", json=sicherung).json()
    assert zweiter["deals"] == 0
    assert zweiter["verlauf"] == 0
    assert zweiter["interaktionen"] == 0
    assert zweiter["wunschpreise"] == 0


def test_einspielen_sperrt_niemanden_aus(client):
    """Der Benutzer der laufenden Installation bleibt, wie er ist."""
    sicherung = client.get("/api/system/backup").json()
    sicherung["benutzer"] = [{"username": "fremd", "password_hash": "x",
                              "created_at": "2020-01-01T00:00:00+00:00"}]
    bericht = client.post("/api/system/restore", json=sicherung).json()
    assert bericht["benutzer"] == 0
    assert client.get("/api/system/backup").json()["benutzer"][0]["username"] == "cillian"


def test_fremde_datei_wird_abgewiesen(client):
    antwort = client.post("/api/system/restore", json={"irgendwas": 1})
    assert antwort.status_code == 400


# --- Verschluesselung -----------------------------------------------------

def test_verschluesselte_sicherung_und_zurueck(client):
    fuelle(client)
    antwort = client.post("/api/system/backup",
                          json={"passwort": "einLangesPasswort"})
    assert antwort.status_code == 200
    huelle = antwort.json()
    assert huelle["sparbit_backup"] == "verschluesselt"
    assert "LEGO" not in json.dumps(huelle)          # nichts im Klartext

    bericht = client.post("/api/system/restore",
                          json={"daten": huelle, "passwort": "einLangesPasswort"})
    assert bericht.status_code == 200
    assert bericht.json()["ok"] is True


def test_falsches_passwort_wird_erkannt(client):
    huelle = client.post("/api/system/backup",
                         json={"passwort": "einLangesPasswort"}).json()
    antwort = client.post("/api/system/restore",
                          json={"daten": huelle, "passwort": "falsch123"})
    assert antwort.status_code == 400
    assert "Passwort" in antwort.json()["detail"]


def test_verschluesselte_datei_ohne_passwort_sagt_das(client):
    huelle = client.post("/api/system/backup",
                         json={"passwort": "einLangesPasswort"}).json()
    antwort = client.post("/api/system/restore", json=huelle)
    assert antwort.status_code == 400
    assert "verschluesselt" in antwort.json()["detail"]


def test_kurzes_passwort_wird_abgelehnt(client):
    assert client.post("/api/system/backup", json={"passwort": "kurz"}).status_code == 400


# --- Automatische Sicherung ----------------------------------------------

def test_sicherung_auf_knopfdruck_und_rotation(client, tmp_path):
    from app import backup as backup_mod
    from app.db import SessionLocal, set_setting

    fuelle(client)
    with SessionLocal() as db:
        set_setting(db, "backup_behalten", 3)
        db.commit()

    for _ in range(5):
        antwort = client.post("/api/system/backups").json()
        assert antwort["ok"] is True

    dateien = client.get("/api/system/backups").json()["dateien"]
    assert len(dateien) <= 3, "Rotation haelt den Ordner klein"
    assert backup_mod.ordner().is_dir()


def test_heruntergeladene_sicherung_ist_die_geschriebene(client):
    fuelle(client)
    name = client.post("/api/system/backups").json()["datei"]
    inhalt = client.get(f"/api/system/backups/{name}")
    assert inhalt.status_code == 200
    assert inhalt.json()["deals"][0]["titel"] == "LEGO Technic"


def test_kein_ausbruch_aus_dem_backup_ordner(client):
    antwort = client.get("/api/system/backups/..%2F..%2Fsparbit.db")
    assert antwort.status_code in (400, 404)


# --- Teil-Update der Einstellungen ---------------------------------------

def test_speichern_einer_einstellung_laesst_die_anderen_stehen(client):
    """Vorher setzte jedes PUT alle Felder auf ihre Defaults zurueck.

    Wer im Kanal-Bereich einen Waehrungskurs speicherte, stellte damit
    unbemerkt die Preisfehler-Schwelle von 85 zurueck auf 70.
    """
    client.put("/api/settings", json={"preisfehler_schwelle": 85,
                                      "preisfehler_waechter": False})
    client.put("/api/settings", json={"waehrungskurse": {"USD": 0.9}})

    jetzt = client.get("/api/settings").json()
    assert jetzt["preisfehler_schwelle"] == 85
    assert jetzt["preisfehler_waechter"] is False
    assert jetzt["waehrungskurse"]["USD"] == 0.9


def test_backup_passwort_geht_nie_wieder_heraus(client):
    client.put("/api/settings", json={"backup_passwort": "meinGeheimnis"})
    antwort = client.get("/api/settings").json()
    assert antwort["backup_passwort_gesetzt"] is True
    assert "meinGeheimnis" not in str(antwort)


def test_passwort_laesst_sich_wieder_loeschen(client):
    client.put("/api/settings", json={"backup_passwort": "meinGeheimnis"})
    client.put("/api/settings", json={"backup_passwort": "-"})
    assert client.get("/api/settings").json()["backup_passwort_gesetzt"] is False
