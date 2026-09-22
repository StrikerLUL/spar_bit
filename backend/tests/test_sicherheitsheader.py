"""Kopfzeilen, die es auf dem lokalen Weg bisher gar nicht gab.

Die Docker-Variante setzte drei davon in nginx. Startet man SparBit
lokal, liefert das Backend die Oberflaeche selbst aus - dort kam nichts
an. Eine Content-Security-Policy fehlte auf beiden Wegen.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    main = lade_app_neu()
    with TestClient(main.app) as c:
        yield c


def test_grundschutz_steht_auf_jeder_antwort(client):
    kopf = client.get("/api/health").headers
    assert kopf["X-Content-Type-Options"] == "nosniff"
    assert kopf["X-Frame-Options"] == "DENY"
    assert kopf["Referrer-Policy"] == "same-origin"
    assert "geolocation=()" in kopf["Permissions-Policy"]


def test_policy_erlaubt_nur_eigene_skripte(client):
    csp = client.get("/api/health").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # Bilder duerfen vom Haendler kommen, solange der Zwischenspeicher aus ist.
    assert "img-src 'self' https: data:" in csp
    assert "'unsafe-eval'" not in csp


def test_die_api_dokumentation_bleibt_benutzbar(client):
    """Swagger laedt von einem CDN - eine Policy, die es verbietet,
    haette nur eine kaputte Seite ergeben."""
    antwort = client.get("/api/docs")
    assert "Content-Security-Policy" not in antwort.headers
    assert antwort.headers["X-Content-Type-Options"] == "nosniff"


def test_hsts_nur_wenn_wirklich_https(client):
    assert "Strict-Transport-Security" not in client.get("/api/health").headers
    mit_proxy = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert mit_proxy.headers["Strict-Transport-Security"].startswith("max-age=")
