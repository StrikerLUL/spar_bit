"""Kanal-Endpunkte durch die echte API - vor allem die Maskierung.

Geheimnisse duerfen nie im Klartext zurueckkommen, und ein Speichern mit
leerem Feld darf sie nicht loeschen. Beides ist leicht zu brechen und faellt
sonst erst auf, wenn ein Kanal still nicht mehr zustellt.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    import importlib, sys
    for name in list(sys.modules):
        if name.startswith("app."):
            del sys.modules[name]
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


def test_alle_neun_typen_werden_angeboten(client):
    typen = client.get("/api/channels/types").json()
    assert {t["type"] for t in typen} == {
        "discord", "slack", "matrix", "gotify", "pushover",
        "telegram", "ntfy", "smtp", "webhook"}


def test_jeder_typ_beschreibt_sich(client):
    for typ in client.get("/api/channels/types").json():
        assert typ["display_name"] and typ["beschreibung"], typ["type"]
        assert typ["options_schema"], typ["type"]
        # Ohne Pflichtfeld koennte man einen leeren Kanal speichern.
        assert any(o["pflicht"] for o in typ["options_schema"]), typ["type"]
        assert isinstance(typ["supports_buttons"], bool)


def test_telegram_token_kommt_maskiert_zurueck(client):
    antwort = client.post("/api/channels", json={
        "type": "telegram", "name": "Handy",
        "config": {"bot_token": "123456789:AAEgeheimesToken", "chat_id": "42"}})
    assert antwort.status_code == 200
    cfg = antwort.json()["config"]
    assert "geheimesToken" not in str(cfg)
    assert cfg["bot_token__set"] is True
    assert cfg["chat_id"] == "42"


@pytest.mark.parametrize("typ,schluessel,wert,rest", [
    ("telegram", "bot_token", "123456789:AAEgeheim", {"chat_id": "42"}),
    ("discord", "url", "https://discord.com/api/webhooks/1/geheim", {}),
    ("ntfy", "topic", "meinGeheimesTopic", {}),
    ("pushover", "user", "uGeheimerSchluessel", {"token": "aToken"}),
    ("smtp", "password", "geheimesPasswort", {"host": "smtp.x.de"}),
])
def test_geheimnisse_verlassen_den_server_nicht(client, typ, schluessel, wert, rest):
    antwort = client.post("/api/channels",
                          json={"type": typ, "name": typ, "config": {schluessel: wert, **rest}})
    assert wert not in str(antwort.json())
    assert wert not in str(client.get("/api/channels").json())


def test_leeres_feld_behaelt_das_gespeicherte_geheimnis(client):
    angelegt = client.post("/api/channels", json={
        "type": "telegram", "name": "Handy",
        "config": {"bot_token": "123456789:AAEgeheim", "chat_id": "42"}}).json()

    # So schickt es die Oberflaeche zurueck: maskierter Wert, unveraenderter Rest.
    client.put(f"/api/channels/{angelegt['id']}", json={
        "type": "telegram", "name": "Handy neu", "enabled": True,
        "config": {**angelegt["config"], "chat_id": "43"}})

    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Channel
    with SessionLocal() as db:
        row = db.scalars(select(Channel)).one()
    assert row.config["bot_token"] == "123456789:AAEgeheim"
    assert row.config["chat_id"] == "43"
    assert row.name == "Handy neu"


def test_unbekannter_typ_wird_abgelehnt(client):
    antwort = client.post("/api/channels",
                          json={"type": "signal", "name": "X", "config": {}})
    assert antwort.status_code == 400


def test_kanal_laesst_sich_loeschen(client):
    angelegt = client.post("/api/channels", json={
        "type": "ntfy", "name": "Handy", "config": {"topic": "abc"}}).json()
    assert client.delete(f"/api/channels/{angelegt['id']}").status_code == 200
    assert client.get("/api/channels").json() == []
