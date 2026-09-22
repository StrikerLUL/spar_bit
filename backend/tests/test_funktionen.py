"""Sparbilanz, Regeln teilen, OPML, Schwelle uebernehmen, HTML-Mail."""
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


# --- Sparbilanz -----------------------------------------------------------

def test_ohne_gemerktes_sagt_die_bilanz_das(client):
    """Was ungesehen vorbeizog, hat nichts gespart - egal wie guenstig."""
    antwort = client.get("/api/bilanz").json()
    assert antwort["ersparnis_eur"] == 0.0
    assert "Noch nichts gemerkt" in antwort["hinweis"]


def test_bilanz_rechnet_gegen_den_eigenen_verlauf(client):
    from app.db import SessionLocal
    from app.models import Deal, Interaction, PriceHistory

    with SessionLocal() as db:
        deal = Deal(url_hash="b1", titel="Kopfhörer", titel_norm="kopfhoerer",
                    url="https://shop/1", quelle="test", preis=180.0,
                    preis_eur=180.0, bookmarked=True)
        db.add(deal)
        db.flush()
        # Ueblicher Preis laut eigenem Verlauf: 250.
        for preis in (240.0, 250.0, 260.0):
            db.add(PriceHistory(deal_id=deal.id, preis=preis))
        db.add(Interaction(deal_id=deal.id, art="gemerkt"))
        db.commit()

    antwort = client.get("/api/bilanz").json()
    assert antwort["ersparnis_eur"] == 70.0, "250 (Median) minus 180"
    assert antwort["top"][0]["titel"] == "Kopfhörer"
    assert "UVP" in antwort["hinweis"], "die Rechnung muss sich erklären"


def test_zu_wenig_verlauf_wird_nicht_geschaetzt(client):
    """Zwei Preispunkte sind kein Verlauf, sondern eine Momentaufnahme."""
    from app.db import SessionLocal
    from app.models import Deal, Interaction, PriceHistory

    with SessionLocal() as db:
        deal = Deal(url_hash="b2", titel="Maus", titel_norm="maus",
                    url="https://shop/2", quelle="test", preis=10.0, preis_eur=10.0)
        db.add(deal)
        db.flush()
        db.add(PriceHistory(deal_id=deal.id, preis=99.0))
        db.add(Interaction(deal_id=deal.id, art="gemerkt"))
        db.commit()

    antwort = client.get("/api/bilanz").json()
    assert antwort["ersparnis_eur"] == 0.0
    assert antwort["ohne_verlauf"] == 1


# --- Regeln teilen --------------------------------------------------------

def test_regeln_export_laesst_kanaele_weg(client):
    """Eine Regel aus einer fremden Installation darf nicht auf Kanäle
    zeigen, die es hier gar nicht gibt."""
    kanal = client.post("/api/channels", json={
        "type": "webhook", "name": "Test",
        "config": {"url": "https://example.de/hook"}}).json()
    client.post("/api/rules", json={"name": "LEGO", "keywords": ["lego"],
                                    "channels": [kanal["id"]],
                                    "priority": "SOFORT"})
    export = client.get("/api/rules/export").json()
    assert export["format"] == "sparbit-regeln"
    assert export["regeln"][0]["name"] == "LEGO"
    assert "channels" not in export["regeln"][0]
    assert "id" not in export["regeln"][0]
    assert "match_count" not in export["regeln"][0]


def test_import_legt_regeln_ausgeschaltet_an(client):
    """Eine fremde Regel, die sofort losmeldet, ist der schnellste Weg
    zu einem stummgeschalteten Kanal."""
    antwort = client.post("/api/rules/import", json={"regeln": [
        {"name": "Kaffee", "keywords": ["kaffee"], "max_preis": 20.0},
        {"name": "Bücher", "keywords": ["buch"]},
    ]}).json()
    assert antwort["angelegt"] == ["Kaffee", "Bücher"]

    regeln = client.get("/api/rules").json()
    assert {r["name"] for r in regeln} == {"Kaffee", "Bücher"}
    assert all(r["enabled"] is False for r in regeln)
    assert all(r["channels"] == [] for r in regeln)


def test_import_ueberschreibt_nichts_ungefragt(client):
    client.post("/api/rules", json={"name": "Kaffee", "keywords": ["espresso"]})
    antwort = client.post("/api/rules/import", json={"regeln": [
        {"name": "Kaffee", "keywords": ["etwas anderes"]}]}).json()
    assert antwort["uebersprungen"] == ["Kaffee"]
    assert client.get("/api/rules").json()[0]["keywords"] == ["espresso"]


def test_hin_und_zurueck(client):
    client.post("/api/rules", json={"name": "Technik", "keywords": ["ssd", "nvme"],
                                    "max_preis": 99.5, "nur_gratis": False,
                                    "min_urteil": "gut"})
    export = client.get("/api/rules/export").json()
    client.delete(f"/api/rules/{client.get('/api/rules').json()[0]['id']}")
    client.post("/api/rules/import", json={"regeln": export["regeln"], "aktiv": True})

    wieder = client.get("/api/rules").json()[0]
    assert wieder["keywords"] == ["ssd", "nvme"]
    assert wieder["max_preis"] == 99.5
    assert wieder["min_urteil"] == "gut"
    assert wieder["enabled"] is True


def test_leere_datei_wird_abgewiesen(client):
    assert client.post("/api/rules/import", json={"regeln": []}).status_code == 400


# --- OPML -----------------------------------------------------------------

OPML = """<?xml version="1.0"?>
<opml version="2.0"><head><title>Meine Feeds</title></head><body>
  <outline text="Sparhamster" type="rss" xmlUrl="https://sparhamster.at/feed/"/>
  <outline text="Ordner"><outline type="rss" xmlUrl="https://example.de/feed"/></outline>
  <outline text="kein Feed"/>
</body></opml>"""


def test_opml_import_findet_verschachtelte_feeds(client):
    antwort = client.post("/api/sources/opml/import", json={"inhalt": OPML}).json()
    assert antwort["gefunden"] == 2
    assert antwort["neu"] == 2

    quellen = client.get("/api/sources").json()
    eigene = next(q for q in quellen if q["id"] == "custom_feed")
    assert "https://sparhamster.at/feed/" in eigene["options"]["feeds"]


def test_zweimal_importieren_legt_keine_dubletten_an(client):
    client.post("/api/sources/opml/import", json={"inhalt": OPML})
    zweite = client.post("/api/sources/opml/import", json={"inhalt": OPML}).json()
    assert zweite["neu"] == 0
    assert zweite["schon_da"] == 2


def test_kaputte_datei_sagt_was_los_ist(client):
    antwort = client.post("/api/sources/opml/import", json={"inhalt": "<opml kaputt"})
    assert antwort.status_code == 400
    assert "OPML" in antwort.json()["detail"]


def test_datei_ohne_feeds_wird_erklaert(client):
    antwort = client.post("/api/sources/opml/import",
                          json={"inhalt": "<opml><body/></opml>"})
    assert antwort.status_code == 400
    assert "xmlUrl" in antwort.json()["detail"]


def test_opml_export_liefert_was_eingelesen_wurde(client):
    client.post("/api/sources/opml/import", json={"inhalt": OPML})
    antwort = client.get("/api/sources/opml/export")
    assert antwort.status_code == 200
    assert antwort.headers["X-SparBit-Feeds"] == "2"
    assert "sparhamster.at/feed/" in antwort.text
    assert antwort.text.startswith("<?xml")


# --- Preisfehler-Schwelle -------------------------------------------------

def test_ohne_rueckmeldungen_gibt_es_nichts_zu_uebernehmen(client):
    antwort = client.post("/api/preisfehler/schwelle-uebernehmen")
    assert antwort.status_code == 409
    assert "Rückmeldungen" in antwort.json()["detail"]


def test_schwelle_uebernehmen_nennt_den_weg_zurueck(client, monkeypatch):
    import app.pricefehler as pricefehler
    from app.routers import extras_routes  # noqa: F401

    monkeypatch.setattr(pricefehler, "bewerte_rueckmeldungen",
                        lambda db: {"vorschlag": 85, "aktuelle_schwelle": 70,
                                    "vorschlag_grund": "Über 84 kein Fehlalarm."})
    antwort = client.post("/api/preisfehler/schwelle-uebernehmen").json()
    assert antwort["vorher"] == 70
    assert antwort["jetzt"] == 85
    assert client.get("/api/settings").json()["preisfehler_schwelle"] == 85


# --- HTML-Mail ------------------------------------------------------------

def test_html_mail_zeigt_das_wichtige_zuerst():
    from app.mailhtml import einzeln, sammel
    from app.notify.base import Notification, Sammelmeldung

    note = Notification(titel="LEGO Technic", url="https://shop/1", quelle="mydealz",
                        preis=79.99, originalpreis=119.99, rabatt_prozent=33,
                        haendler="amazon", urteil="bestpreis",
                        urteil_text="So günstig war es noch nie", regel="LEGO")
    html = einzeln(note)
    assert "LEGO Technic" in html
    assert "Bestpreis" in html
    assert "119,99" in html or "119.99" in html
    assert "<style" not in html, "Mail-Programme werfen style-Blöcke weg"

    viele = Sammelmeldung(meldungen=[note] * 3, zeitraum="seit 07:00")
    assert "3" in sammel(viele)


def test_sonderzeichen_werden_maskiert():
    from app.mailhtml import einzeln
    from app.notify.base import Notification

    note = Notification(titel='<script>alert("x")</script>', url="https://x",
                        quelle="test")
    html = einzeln(note)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
