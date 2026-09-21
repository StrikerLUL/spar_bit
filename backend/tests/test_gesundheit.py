"""Was /api/health sagt, wenn etwas nicht stimmt.

Vorher gab der Endpunkt immer {"status": "ok"} zurueck - er bewies nur,
dass ein Webserver antwortet. Genau das weiss aber schon, wer ihn
erreicht. Der gefaehrliche Ausfall ist der stille: Scheduler tot,
Quellen gesperrt, und von aussen sieht es aus wie "heute keine Deals".
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    main = lade_app_neu()
    with TestClient(main.app) as c:
        yield c


def test_gesund_ist_gesund(client):
    antwort = client.get("/api/health")
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["status"] == "ok"
    assert daten["teile"]["datenbank"]["stand"] == "ok"
    assert daten["teile"]["scheduler"]["stand"] == "ok"


def test_health_braucht_keine_anmeldung(client):
    """Ein Wachhund hat kein Sitzungs-Cookie."""
    client.cookies.clear()
    assert client.get("/api/health").status_code == 200


def test_kaputte_datenbank_ergibt_503(client, monkeypatch):
    from app import gesundheit

    monkeypatch.setattr(gesundheit, "_datenbank",
                        lambda: {"stand": "down", "text": "Platte voll"})
    antwort = client.get("/api/health")
    assert antwort.status_code == 503
    assert antwort.json()["status"] == "down"


def test_mangel_bleibt_200(client, monkeypatch):
    """Sonst startet ein Orchestrator den Dienst neu, obwohl er arbeitet."""
    from app import gesundheit

    monkeypatch.setattr(gesundheit, "_scheduler",
                        lambda: {"stand": "degraded", "text": "ohne Jobs"})
    antwort = client.get("/api/health")
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "degraded"


def test_alle_quellen_gesperrt_ist_ein_mangel(client):
    """Der Fall, der von aussen wie 'keine Deals' aussieht."""
    from app.db import SessionLocal
    from app.gesundheit import _quellen
    from app.models import SourceConfig, utcnow

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "epic")
        cfg.enabled = True
        cfg.circuit_open_until = utcnow() + timedelta(hours=1)
        db.commit()

    befund = _quellen()
    assert befund["stand"] == "degraded"
    assert "gesperrt" in befund["text"]
    assert befund["gesperrt"] == ["epic"]


def test_lange_kein_erfolg_ist_ein_mangel(client):
    from app.db import SessionLocal
    from app.gesundheit import _quellen
    from app.models import SourceConfig, utcnow

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "epic")
        cfg.enabled = True
        cfg.last_success = utcnow() - timedelta(hours=30)
        db.commit()

    befund = _quellen()
    assert befund["stand"] == "degraded"
    assert "30 h" in befund["text"]


# --- Metriken -------------------------------------------------------------

def test_metriken_sind_prometheus_lesbar(client):
    from app.db import SessionLocal
    from app.models import SourceConfig

    client.post("/api/auth/setup",
                json={"username": "cillian", "password": "einGutesPasswort1"})
    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "epic")
        cfg.enabled = True
        cfg.total_runs = 42
        cfg.total_errors = 3
        db.commit()

    text = client.get("/api/metrics").text
    assert "# TYPE sparbit_quelle_laeufe_gesamt counter" in text
    assert 'sparbit_quelle_laeufe_gesamt{quelle="epic"} 42' in text
    assert 'sparbit_quelle_fehler_gesamt{quelle="epic"} 3' in text
    assert 'sparbit_quelle_eingeschaltet{quelle="epic"} 1' in text
    assert "sparbit_deals_gesamt 0" in text
    assert 'sparbit_gesund{teil="datenbank"} 1' in text

    # Jede Zeile ist entweder Kommentar oder "name wert".
    for zeile in text.strip().splitlines():
        if zeile.startswith("#"):
            continue
        assert len(zeile.rsplit(" ", 1)) == 2, zeile
        float(zeile.rsplit(" ", 1)[1])


def test_schema_stand_steht_in_der_systeminfo(client):
    """Vorher liess sich nur am Vorhandensein einzelner Spalten raten,
    auf welchem Stand eine Datenbank ist."""
    client.post("/api/auth/setup",
                json={"username": "cillian", "password": "einGutesPasswort1"})
    info = client.get("/api/system/info").json()
    assert info["schema_stand"] == info["schema_neuester"]
    assert info["schema_stand"] > 0
