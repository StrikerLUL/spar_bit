"""Wunschliste: mehrere URLs auf einmal.

Jeden Artikel einzeln über ein Formular einzutragen ist der Grund, warum
Wunschlisten leer bleiben.
"""
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


@pytest.fixture(autouse=True)
def kein_netz(client, monkeypatch):
    """Keine Abrufe - der Import muss auch ohne lesbare Seite funktionieren.

    Haengt bewusst an `client`: der laedt die app-Module neu, ein vorher
    gesetzter Patch waere danach weg und der Test ginge wirklich ins Netz.
    """
    async def nichts(db, eintrag, http):
        # Wie das Original: der Fehler wird festgeschrieben, sonst wirft
        # das db.refresh() im Router ihn wieder weg.
        eintrag.letzter_fehler = "Seite nicht lesbar"
        db.commit()
        return None

    import app.routers.watch_routes as routes
    monkeypatch.setattr(routes, "pruefe_eintrag", nichts)


def sammel(client, urls, **kw):
    return client.post("/api/watch/sammel",
                       json={"urls": urls, **kw})


def test_mehrere_urls_werden_angelegt(client):
    antwort = sammel(client, "https://a.test/eins\nhttps://b.test/zwei\n"
                             "https://c.test/drei")
    assert antwort.status_code == 200
    raus = antwort.json()
    assert raus["zusammenfassung"]["neu"] == 3
    assert len(client.get("/api/watch").json()) == 3


def test_leere_zeilen_und_muell_werden_uebergangen(client):
    antwort = sammel(client, "\n\nhttps://a.test/eins\n   \nkein-link\n"
                             "ftp://b.test/x\nhttps://b.test/zwei\n")
    assert antwort.json()["zusammenfassung"]["gelesen"] == 2


def test_ohne_gueltige_url_gibt_es_einen_fehler(client):
    antwort = sammel(client, "nur text\nkein link")
    assert antwort.status_code == 400
    assert "URL" in antwort.json()["detail"]


def test_doppelte_zeilen_zaehlen_einmal(client):
    antwort = sammel(client, "https://a.test/x\nhttps://a.test/x")
    assert antwort.json()["zusammenfassung"]["neu"] == 1


def test_bereits_vorhandene_werden_uebersprungen(client):
    sammel(client, "https://a.test/x")
    antwort = sammel(client, "https://a.test/x\nhttps://b.test/y")
    raus = antwort.json()
    assert raus["zusammenfassung"]["doppelt"] == 1
    assert raus["zusammenfassung"]["neu"] == 1
    assert "steht schon drin" in raus["uebersprungen"][0]["grund"]


def test_zu_viele_auf_einmal_werden_abgelehnt(client):
    from app.routers.watch_routes import SAMMEL_MAX
    viele = "\n".join(f"https://a.test/{i}" for i in range(SAMMEL_MAX + 1))
    antwort = sammel(client, viele)
    assert antwort.status_code == 400
    assert str(SAMMEL_MAX) in antwort.json()["detail"]


def test_unlesbare_seiten_werden_trotzdem_aufgenommen(client):
    """Oft zickt eine Seite nur beim ersten Mal - der Lauf holt es nach."""
    raus = sammel(client, "https://a.test/x").json()
    assert raus["zusammenfassung"]["ohne_preis"] == 1
    assert raus["fehler"][0]["grund"] == "Seite nicht lesbar"
    assert len(client.get("/api/watch").json()) == 1


def test_zielpreis_und_intervall_gelten_fuer_alle(client):
    sammel(client, "https://a.test/x\nhttps://b.test/y",
           ziel_preis=199.0, intervall_minuten=360)
    for eintrag in client.get("/api/watch").json():
        assert eintrag["ziel_preis"] == 199.0
        assert eintrag["intervall_minuten"] == 360


def test_namen_kommen_aus_der_url(client):
    sammel(client, "https://shop.de/p/lego-technic-42143.html")
    assert client.get("/api/watch").json()[0]["name"] == "lego technic 42143"


def test_eine_kaputte_seite_bricht_den_rest_nicht_ab(client, monkeypatch):
    aufrufe = {"n": 0}

    async def mal_so_mal_so(db, eintrag, http):
        aufrufe["n"] += 1
        if aufrufe["n"] == 2:
            raise RuntimeError("Verbindung abgebrochen")
        eintrag.letzter_fehler = "kein Preis"
        db.commit()
        return None

    import app.routers.watch_routes as routes
    monkeypatch.setattr(routes, "pruefe_eintrag", mal_so_mal_so)

    raus = sammel(client, "https://a.test/1\nhttps://a.test/2\n"
                          "https://a.test/3").json()
    assert raus["zusammenfassung"]["neu"] == 3
    assert len(client.get("/api/watch").json()) == 3


def test_import_braucht_eine_anmeldung(client):
    client.post("/api/auth/logout")
    assert sammel(client, "https://a.test/x").status_code == 401
