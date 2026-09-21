"""Mehrere Konten - und die Frage, ob die Trennung wirklich haelt.

Der gefaehrliche Fehler bei Mehrbenutzer ist nicht die fehlende
Funktion, sondern die undichte: eine Regel, die auf das Telefon eines
anderen meldet, oder eine Wunschliste, die jeder sieht.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    return lade_app_neu()


@pytest.fixture
def admin(app):
    with TestClient(app.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


def zweiter(app, admin_client, name="mitbewohner", rolle="mitglied"):
    """Zweites Konto anlegen und dafuer einen eigenen Client zurueckgeben."""
    antwort = admin_client.post("/api/auth/benutzer", json={
        "username": name, "password": "nochEinPasswort1", "rolle": rolle})
    assert antwort.status_code == 200, antwort.text
    client = TestClient(app.app)
    client.post("/api/auth/login",
                json={"username": name, "password": "nochEinPasswort1"})
    return client


# --- Konten ---------------------------------------------------------------

def test_der_erste_ist_admin(admin):
    liste = admin.get("/api/auth/benutzer").json()
    assert len(liste) == 1
    assert liste[0]["rolle"] == "admin"
    assert liste[0]["ich"] is True


def test_setup_macht_zu_sobald_es_einen_benutzer_gibt(admin):
    """Sonst waere der offene Endpunkt ein Weg, sich ohne Anmeldung ein
    Konto anzulegen."""
    antwort = admin.post("/api/auth/setup",
                         json={"username": "fremd", "password": "einGutesPasswort1"})
    assert antwort.status_code == 409


def test_nur_ein_admin_legt_benutzer_an(app, admin):
    mitglied = zweiter(app, admin)
    antwort = mitglied.post("/api/auth/benutzer", json={
        "username": "dritter", "password": "nochEinPasswort1"})
    assert antwort.status_code == 403


def test_der_letzte_admin_bleibt_admin(admin):
    ich = admin.get("/api/auth/benutzer").json()[0]
    antwort = admin.patch(f"/api/auth/benutzer/{ich['id']}",
                          json={"rolle": "mitglied"})
    assert antwort.status_code == 409
    assert "letzte Administrator" in antwort.json()["detail"]


def test_abgeschaltetes_konto_kommt_nicht_rein(app, admin):
    mitglied = zweiter(app, admin)
    ziel = next(u for u in admin.get("/api/auth/benutzer").json()
                if u["username"] == "mitbewohner")
    admin.patch(f"/api/auth/benutzer/{ziel['id']}", json={"aktiv": False})

    # Laufende Sitzung endet sofort ...
    assert mitglied.get("/api/rules").status_code == 403
    # ... und eine neue Anmeldung sagt, warum.
    frisch = TestClient(app.app)
    antwort = frisch.post("/api/auth/login",
                          json={"username": "mitbewohner", "password": "nochEinPasswort1"})
    assert antwort.status_code == 403
    assert "abgeschaltet" in antwort.json()["detail"]


def test_admin_kann_passwort_zuruecksetzen(app, admin):
    """Ein vergessenes Passwort darf nicht das Ende des Kontos sein."""
    zweiter(app, admin)
    ziel = next(u for u in admin.get("/api/auth/benutzer").json()
                if u["username"] == "mitbewohner")
    admin.patch(f"/api/auth/benutzer/{ziel['id']}",
                json={"neues_passwort": "ganzNeuesPasswort1"})

    frisch = TestClient(app.app)
    assert frisch.post("/api/auth/login", json={
        "username": "mitbewohner", "password": "ganzNeuesPasswort1"}).status_code == 200


# --- Trennung -------------------------------------------------------------

def test_regeln_bleiben_beim_eigenen_konto(app, admin):
    admin.post("/api/rules", json={"name": "LEGO", "keywords": ["lego"]})
    mitglied = zweiter(app, admin)
    mitglied.post("/api/rules", json={"name": "Kaffee", "keywords": ["kaffee"]})

    assert [r["name"] for r in admin.get("/api/rules").json()] == ["LEGO"]
    assert [r["name"] for r in mitglied.get("/api/rules").json()] == ["Kaffee"]


def test_fremde_regel_ist_nicht_zu_finden(app, admin):
    regel = admin.post("/api/rules", json={"name": "Privat",
                                           "keywords": ["x"]}).json()
    mitglied = zweiter(app, admin)
    # 404 statt 403: dass es sie gibt, geht niemanden etwas an.
    assert mitglied.put(f"/api/rules/{regel['id']}",
                        json={"name": "Geklaut", "keywords": ["y"]}).status_code == 404
    assert mitglied.delete(f"/api/rules/{regel['id']}").status_code == 404


def test_regel_darf_nicht_auf_fremde_kanaele_zeigen(app, admin):
    """Sonst schickt die eigene Regel Meldungen auf ein fremdes Telefon."""
    kanal = admin.post("/api/channels", json={
        "type": "webhook", "name": "Meins",
        "config": {"url": "https://example.de/hook"}}).json()
    mitglied = zweiter(app, admin)

    antwort = mitglied.post("/api/rules", json={
        "name": "Übergriffig", "keywords": ["x"], "channels": [kanal["id"]]})
    assert antwort.status_code == 400
    assert "gehören jemand anderem" in antwort.json()["detail"]


def test_kanaele_bleiben_getrennt(app, admin):
    admin.post("/api/channels", json={"type": "webhook", "name": "Meiner",
                                      "config": {"url": "https://example.de/a"}})
    mitglied = zweiter(app, admin)
    assert mitglied.get("/api/channels").json() == []


def test_wunschliste_und_listen_bleiben_getrennt(app, admin):
    from app.db import SessionLocal
    from app.models import WatchItem

    admin.post("/api/listen", json={"name": "Weihnachten"})
    mitglied = zweiter(app, admin)

    with SessionLocal() as db:
        # Direkt anlegen - der API-Weg wuerde die Seite abrufen.
        db.add(WatchItem(name="Geschenk", url="https://shop/1", benutzer_id=1))
        db.commit()

    assert len(admin.get("/api/watch").json()) == 1
    assert mitglied.get("/api/watch").json() == []
    assert len(admin.get("/api/listen").json()) == 1
    assert mitglied.get("/api/listen").json() == []


def test_gelernte_vorlieben_vermischen_sich_nicht(app, admin):
    """Zwei Geschmaecker in einem Modell ergeben Rauschen, keinen
    Durchschnitt."""
    from app.db import SessionLocal
    from app.models import Deal

    with SessionLocal() as db:
        db.add(Deal(url_hash="m1", titel="LEGO Technic", titel_norm="lego technic",
                    url="https://shop/1", quelle="test"))
        db.commit()

    admin.post("/api/deals/1/interaktion", json={"art": "gemerkt"})
    mitglied = zweiter(app, admin)

    assert admin.get("/api/empfehlungen/status").json()["positiv"] > 0
    assert mitglied.get("/api/empfehlungen/status").json()["positiv"] == 0


def test_gast_darf_zusehen_aber_nichts_anlegen(app, admin):
    gast = zweiter(app, admin, name="besuch", rolle="gast")
    assert gast.get("/api/rules").status_code == 200
    antwort = gast.post("/api/rules", json={"name": "Nö", "keywords": ["x"]})
    assert antwort.status_code == 403
    assert "Gäste" in antwort.json()["detail"]


def test_quellen_bleiben_gemeinsam(app, admin):
    """Quellen kosten Anfragen bei fremden Servern - sie gehoeren der
    Anlage, nicht einer Person."""
    mitglied = zweiter(app, admin)
    quellen_admin = {q["id"] for q in admin.get("/api/sources").json()}
    quellen_mitglied = {q["id"] for q in mitglied.get("/api/sources").json()}
    assert quellen_admin == quellen_mitglied


def test_deals_bleiben_gemeinsam(app, admin):
    """Der Deal-Pool ist die gemeinsame Arbeit aller Quellen."""
    from app.db import SessionLocal
    from app.models import Deal

    with SessionLocal() as db:
        db.add(Deal(url_hash="g1", titel="Gemeinsam", titel_norm="gemeinsam",
                    url="https://shop/2", quelle="test"))
        db.commit()

    mitglied = zweiter(app, admin)
    assert admin.get("/api/deals").json()["total"] == 1
    assert mitglied.get("/api/deals").json()["total"] == 1


# --- Altbestand -----------------------------------------------------------

def test_was_vorher_da_war_gehoert_dem_erstbenutzer(tmp_path, monkeypatch):
    """Eine Installation, die bisher einem gehoerte, darf nach dem Update
    nicht dastehen, als gehoerte nichts mehr jemandem."""
    import sqlite3

    from sqlalchemy import create_engine, text

    from app import migrations

    pfad = tmp_path / "alt.db"
    conn = sqlite3.connect(pfad)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT,
                            password_hash TEXT);
        CREATE TABLE rules (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE channels (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO users (username, password_hash) VALUES ('cillian', 'x');
        INSERT INTO rules (name) VALUES ('Alte Regel');
        INSERT INTO channels (name) VALUES ('Alter Kanal');
    """)
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{pfad}")
    migrations.migriere(engine)

    with engine.connect() as verbindung:
        assert verbindung.execute(text("SELECT benutzer_id FROM rules")).scalar() == 1
        assert verbindung.execute(text("SELECT benutzer_id FROM channels")).scalar() == 1
        assert verbindung.execute(text("SELECT rolle FROM users")).scalar() == "admin"
    engine.dispose()
