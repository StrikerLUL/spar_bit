"""Was noch gilt - und was nur noch dasteht.

Zwei Beschwerden aus dem Betrieb stecken in dieser Datei:

    "Viele Preise werden falsch angezeigt"
    "wenn man drauf geht, ist das schon längst abgelaufen"

Die erste ist im Parser behoben (tests/test_priceparse.py). Die zweite
lässt sich nicht im Text erkennen - dafür muss jemand auf der Zielseite
nachsehen. Hier steht, wer das wann tut und was der Feed danach zeigt.
"""
import pytest
from fastapi.testclient import TestClient

ABGELAUFEN = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Weg",
 "offers":{"@type":"Offer","price":"19.99","priceCurrency":"EUR",
 "availability":"https://schema.org/OutOfStock"}}</script></head></html>"""


@pytest.fixture
def welt(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    main = lade_app_neu()

    from app.db import SessionLocal, init_db
    init_db()
    with TestClient(main.app) as client:
        client.post("/api/auth/setup",
                    json={"username": "cillian", "password": "einGutesPasswort1"})
        yield client, SessionLocal


def _deal(db, **felder):
    from app.kategorien import fuer_deal
    from app.models import Deal

    vorgabe = dict(titel="Irgendwas", url="https://x.test/1", quelle="test",
                   preis=10.0, preis_eur=10.0)
    vorgabe.update(felder)
    vorgabe.setdefault("titel_norm", vorgabe["titel"].lower())
    vorgabe.setdefault("url_hash", f"{abs(hash(vorgabe['url'])):032x}"[:32])
    deal = Deal(**vorgabe)
    deal.kategorien = fuer_deal(deal).text or ""
    db.add(deal)
    db.commit()
    return deal


# --- Wer wird als Naechstes nachgesehen? ----------------------------------

def test_abgelaufenes_wird_nicht_erneut_geprueft(welt):
    """Das Urteil aendert sich nicht mehr - die Anfrage waere verschenkt."""
    _, SessionLocal = welt
    from app.gratischeck import waehle_nachpruefung

    with SessionLocal() as db:
        _deal(db, url="https://x.test/tot", check_status="abgelaufen")
        _deal(db, url="https://x.test/lebt")
        adressen = [d.url for d in waehle_nachpruefung(db)]
    assert adressen == ["https://x.test/lebt"]


def test_18er_funde_bleiben_unangetastet_solange_der_bereich_zu_ist(welt):
    """Ist der Bereich aus, ruft SparBit auch keine 18+-Zielseite auf."""
    _, SessionLocal = welt
    from app.gratischeck import waehle_nachpruefung

    with SessionLocal() as db:
        _deal(db, url="https://x.test/18", erwachsen=True)
        _deal(db, url="https://x.test/normal")
        zu = [d.url for d in waehle_nachpruefung(db)]
        offen = [d.url for d in waehle_nachpruefung(db, erwachsen_erlaubt=True)]
    assert zu == ["https://x.test/normal"]
    assert len(offen) == 2


def test_wer_zuerst_drankommt(welt):
    """Gemerkt, geschenkt, auffaellig - in dieser Reihenfolge aergert ein
    toter Link am meisten."""
    _, SessionLocal = welt
    from app.gratischeck import waehle_nachpruefung

    with SessionLocal() as db:
        _deal(db, url="https://x.test/egal", preis=99.0, preis_eur=99.0)
        _deal(db, url="https://x.test/billig", preis=0.99, preis_eur=0.99)
        _deal(db, url="https://x.test/gemerkt", preis=50.0, preis_eur=50.0,
              bookmarked=True)
        reihe = [d.url for d in waehle_nachpruefung(db)]
    assert reihe[0] == "https://x.test/gemerkt"
    assert reihe[1] == "https://x.test/billig"


def test_deckel_pro_lauf(welt):
    """Sonst wird aus der Nachschau ein Crawler."""
    _, SessionLocal = welt
    from app.gratischeck import waehle_nachpruefung

    with SessionLocal() as db:
        for i in range(12):
            _deal(db, url=f"https://x.test/{i}")
        assert len(waehle_nachpruefung(db, grenze=5)) == 5


# --- Was der Feed daraus macht --------------------------------------------

def test_abgelaufene_lassen_sich_ausblenden(welt):
    client, SessionLocal = welt
    with SessionLocal() as db:
        _deal(db, titel="Noch zu haben", url="https://x.test/a")
        _deal(db, titel="Vorbei", url="https://x.test/b", check_status="abgelaufen")
        _deal(db, titel="Ungeprüft", url="https://x.test/c")

    alles = client.get("/api/deals").json()
    assert alles["total"] == 3

    gueltig = client.get("/api/deals?nur_gueltig=true").json()
    titel = {d["titel"] for d in gueltig["items"]}
    assert titel == {"Noch zu haben", "Ungeprüft"}, "Ungeprüftes bleibt sichtbar"


def test_filter_nach_kategorie(welt):
    client, SessionLocal = welt
    with SessionLocal() as db:
        _deal(db, titel="Samsung 2TB NVMe SSD", url="https://x.test/ssd")
        _deal(db, titel="Sony Kopfhörer WH-1000XM5", url="https://x.test/audio")
        _deal(db, titel="Netflix Abo 4,99 € pro Monat", url="https://x.test/abo")

    nur_ssd = client.get("/api/deals?kategorie=speicher").json()
    assert [d["titel"] for d in nur_ssd["items"]] == ["Samsung 2TB NVMe SSD"]

    # Mehrere Kategorien sind ODER-verknuepft.
    beides = client.get("/api/deals?kategorie=speicher,audio").json()
    assert beides["total"] == 2

    assert nur_ssd["items"][0]["kategorien"] == ["speicher"]
    assert nur_ssd["items"][0]["kategorien_labels"] == ["Speicher & SSD"]


def test_kategorienliste_zaehlt_mit(welt):
    """Eine Kategorie ohne Treffer ist ein Knopf ins Leere - das UI soll
    das sehen koennen."""
    client, SessionLocal = welt
    with SessionLocal() as db:
        _deal(db, titel="Samsung 2TB NVMe SSD", url="https://x.test/ssd")

    liste = client.get("/api/kategorien").json()
    nach_key = {k["key"]: k for k in liste}
    assert nach_key["speicher"]["anzahl"] == 1
    assert nach_key["audio"]["anzahl"] == 0
    # 18+-Kategorien haben im normalen Bereich nichts zu suchen.
    assert not any(k["key"].endswith("18") for k in liste)


def test_18er_kategorien_nur_mit_freigeschaltetem_bereich(welt):
    client, _ = welt
    assert client.get("/api/kategorien?bereich=erwachsen").status_code == 403


def test_guenstigste_zuerst_rechnet_mit_dem_monatspreis(welt):
    """1 € für drei Monate ist guenstiger als 0,99 € im Monat."""
    client, SessionLocal = welt
    with SessionLocal() as db:
        _deal(db, titel="Abo A", url="https://x.test/a", preis=0.99,
              preis_eur=0.99, preis_monat_eur=0.99, preis_zeitraum="monat")
        _deal(db, titel="Abo B", url="https://x.test/b", preis=1.0,
              preis_eur=1.0, preis_monat_eur=0.33)
        _deal(db, titel="Ohne Preis", url="https://x.test/c", preis=None,
              preis_eur=None)

    items = client.get("/api/deals?sortierung=guenstig").json()["items"]
    assert [d["titel"] for d in items] == ["Abo B", "Abo A", "Ohne Preis"]


def test_hoechstpreis_pro_monat_filtert_auf_abos(welt):
    client, SessionLocal = welt
    with SessionLocal() as db:
        _deal(db, titel="Abo billig", url="https://x.test/a", preis=1.0,
              preis_eur=1.0, preis_monat_eur=0.33)
        _deal(db, titel="Abo teuer", url="https://x.test/b", preis=20.0,
              preis_eur=20.0, preis_monat_eur=20.0, preis_zeitraum="monat")
        _deal(db, titel="Einmaliger Kauf", url="https://x.test/c", preis=0.5,
              preis_eur=0.5)

    items = client.get("/api/deals?max_preis_monat=5").json()["items"]
    assert [d["titel"] for d in items] == ["Abo billig"]


# --- Die Gegenprobe selbst ------------------------------------------------

@pytest.mark.asyncio
async def test_nachschau_markiert_abgelaufen(welt):
    """Von der Zielseite bis zur Marke im Feed."""
    _, SessionLocal = welt
    from app import gratischeck

    class Antwort:
        def __init__(self, text):
            self.text = text
            self.content = text.encode()
            self.status_code = 200
            self.headers = {"content-type": "text/html"}

    class Http:
        async def get(self, url, **kwargs):
            return Antwort(ABGELAUFEN)

    with SessionLocal() as db:
        deal = _deal(db, url="https://x.test/weg", preis=19.99, preis_eur=19.99)
        bilanz = await gratischeck.pruefe_deals(db, Http(), [deal], alle=True)
        assert bilanz["geprueft"] == 1
        assert deal.id in bilanz["gesperrt"]
        assert deal.check_status == "abgelaufen"


@pytest.mark.asyncio
async def test_ohne_alle_bleiben_normale_deals_liegen(welt):
    """Beim Einsammeln wird nur geprueft, was wirklich aergert - sonst
    waere jeder Fund eine Anfrage an den Haendler."""
    _, SessionLocal = welt
    from app import gratischeck

    class Http:
        async def get(self, url, **kwargs):
            raise AssertionError("haette nicht abgerufen werden duerfen")

    with SessionLocal() as db:
        deal = _deal(db, url="https://x.test/teuer", preis=99.0, preis_eur=99.0)
        bilanz = await gratischeck.pruefe_deals(db, Http(), [deal])
        assert bilanz["geprueft"] == 0
