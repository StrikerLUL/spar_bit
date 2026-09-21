"""Der 18+-Bereich - vor allem seine Sperren.

Die eigentliche Frage bei diesem Bereich ist nicht, ob er funktioniert,
sondern ob er dicht ist: aus, bis jemand ausdruecklich Ja sagt, und danach
strikt getrennt vom normalen Feed.
"""
import pytest
from fastapi.testclient import TestClient

from app.erwachsen import einstufen, markiere
from app.filters import RuleSpec, evaluate
from app.models import Deal


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    main = lade_app_neu()
    with TestClient(main.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


def frei(client):
    antwort = client.put("/api/system/erwachsen",
                         json={"an": True, "bestaetigt": True})
    assert antwort.status_code == 200
    return antwort.json()


# --- Einstufung ------------------------------------------------------------

@pytest.mark.parametrize("titel", [
    "Satisfyer Pro 2 für 24,99 €", "Durex Kondome 40er Pack",
    "Amorelie Adventskalender", "Nutaku: Gratis-Spiel der Woche",
    "FSK 18 Horrorfilm Blu-ray", "Lovense Lush 3 reduziert",
])
def test_eindeutiges_stichwort_genuegt(titel):
    assert einstufen(titel).erwachsen is True


@pytest.mark.parametrize("titel", [
    "LEGO Technic Bugatti 249 €", "Sony WH-1000XM5 Kopfhörer",
    "Adult Swim T-Shirt", "Orion Teleskop 114/900",
    "Erwachsenen-Malbuch Mandala", "Damen Nachtwäsche Pyjama",
])
def test_ein_mehrdeutiges_wort_genuegt_nicht(titel):
    """Sonst wandert die halbe Modeabteilung in den 18+-Bereich."""
    assert einstufen(titel).erwachsen is False


def test_zwei_mehrdeutige_stufen_ein():
    assert einstufen("Sexy Dessous Set reduziert").erwachsen is True


def test_quelle_schlaegt_den_titel():
    """"Gutschein 20 €" verraet nicht, aus welchem Regal es kommt."""
    e = einstufen("Gutschein 20 €", quelle_ist_18=True)
    assert e.erwachsen is True and "Quelle" in e.grund


def test_marke_faellt_nie_wieder_weg():
    """Derselbe Artikel kann spaeter ueber eine harmlose Quelle kommen."""
    deal = Deal(titel="Satisfyer Pro 2", erwachsen=True)
    assert markiere(deal, source_id="mydealz") is True
    assert deal.erwachsen is True


# --- Regeln ----------------------------------------------------------------

def test_regel_ohne_haekchen_trifft_nie():
    deal = Deal(titel="Satisfyer Pro 2", preis=5.0, preis_eur=5.0,
                erwachsen=True, tags=[])
    regel = RuleSpec(max_preis=100.0)          # wuerde sonst glatt durchgehen
    ergebnis = evaluate(regel, deal)
    assert ergebnis.matched is False
    assert "18+" in ergebnis.failed[0]


def test_regel_mit_haekchen_trifft():
    deal = Deal(titel="Satisfyer Pro 2", preis=5.0, preis_eur=5.0,
                erwachsen=True, tags=[])
    assert evaluate(RuleSpec(max_preis=100.0, erwachsen=True), deal).matched


def test_haekchen_oeffnet_nicht_den_normalen_feed():
    """Eine 18+-Regel soll zusaetzlich sehen, nicht stattdessen."""
    normal = Deal(titel="LEGO Set", preis=5.0, preis_eur=5.0,
                  erwachsen=False, tags=[])
    assert evaluate(RuleSpec(max_preis=100.0, erwachsen=True), normal).matched


# --- Die Sperren durch die API --------------------------------------------

def test_bereich_ist_nach_der_installation_aus(client):
    zustand = client.get("/api/system/erwachsen").json()
    assert zustand["an"] is False
    assert zustand["melden"] is False


def test_einschalten_ohne_bestaetigung_wird_abgelehnt(client):
    antwort = client.put("/api/system/erwachsen",
                         json={"an": True, "bestaetigt": False})
    assert antwort.status_code == 400
    assert client.get("/api/system/erwachsen").json()["an"] is False


def test_einschalten_mit_bestaetigung(client):
    zustand = frei(client)
    assert zustand["an"] is True and zustand["bestaetigt_am"]


def test_quellen_tauchen_erst_nach_freigabe_auf(client):
    ids = {q["id"] for q in client.get("/api/sources").json()}
    assert "mydealz_erotik" not in ids and "erotik_feed" not in ids

    frei(client)
    nachher = {q["id"] for q in client.get("/api/sources").json()}
    assert {"mydealz_erotik", "reddit_erwachsen", "erotik_feed"} <= nachher


def test_quelle_laesst_sich_nicht_an_der_sperre_vorbei_einschalten(client):
    """Wer die ID kennt, darf trotzdem nicht per PATCH einschalten."""
    for pfad, methode in [("/api/sources/mydealz_erotik", "patch"),
                          ("/api/sources/mydealz_erotik/test", "post"),
                          ("/api/sources/mydealz_erotik/run", "post")]:
        antwort = (client.patch(pfad, json={"enabled": True})
                   if methode == "patch" else client.post(pfad))
        assert antwort.status_code == 403, pfad


def test_feed_zeigt_18plus_nicht(client):
    from app.db import SessionLocal
    from app.models import Deal as D

    with SessionLocal() as db:
        db.add(D(url_hash="a" * 32, titel="Satisfyer Pro 2", titel_norm="satisfyer",
                 url="https://x.test/1", quelle="mydealz_erotik", erwachsen=True))
        db.add(D(url_hash="b" * 32, titel="LEGO Set", titel_norm="lego",
                 url="https://x.test/2", quelle="mydealz", erwachsen=False))
        db.commit()

    titel = [d["titel"] for d in client.get("/api/deals").json()["items"]]
    assert titel == ["LEGO Set"]

    # Auch nicht ueber die Suche.
    treffer = client.get("/api/deals", params={"q": "Satisfyer"}).json()
    assert treffer["items"] == []


def test_18plus_bereich_ist_ohne_freigabe_gesperrt(client):
    antwort = client.get("/api/deals", params={"bereich": "erwachsen"})
    assert antwort.status_code == 403


def test_18plus_bereich_zeigt_nach_freigabe_nur_18plus(client):
    from app.db import SessionLocal
    from app.models import Deal as D

    with SessionLocal() as db:
        db.add(D(url_hash="c" * 32, titel="Satisfyer Pro 2", titel_norm="satisfyer",
                 url="https://x.test/1", quelle="mydealz_erotik", erwachsen=True))
        db.add(D(url_hash="d" * 32, titel="LEGO Set", titel_norm="lego",
                 url="https://x.test/2", quelle="mydealz", erwachsen=False))
        db.commit()

    frei(client)
    items = client.get("/api/deals", params={"bereich": "erwachsen"}).json()["items"]
    assert [d["titel"] for d in items] == ["Satisfyer Pro 2"]
    assert items[0]["erwachsen"] is True


def test_statistik_zaehlt_18plus_nicht_mit(client):
    from app.db import SessionLocal
    from app.models import Deal as D

    with SessionLocal() as db:
        for i in range(3):
            db.add(D(url_hash=f"{i}" * 32, titel="Satisfyer", titel_norm="s",
                     url=f"https://x.test/{i}", quelle="mydealz_erotik",
                     erwachsen=True, ist_gratis=True))
        db.commit()

    frei(client)
    stats = client.get("/api/stats").json()
    assert stats["deals_gesamt"] == 0
    assert stats["gratis_diese_woche"] == 0


def test_ausschalten_nimmt_die_quellen_wieder_weg(client):
    frei(client)
    assert "erotik_feed" in {q["id"] for q in client.get("/api/sources").json()}

    client.put("/api/system/erwachsen", json={"an": False})
    assert "erotik_feed" not in {q["id"] for q in client.get("/api/sources").json()}
    assert client.get("/api/deals", params={"bereich": "erwachsen"}).status_code == 403


def test_melden_ist_ein_zweiter_schalter(client):
    frei(client)
    assert client.get("/api/system/erwachsen").json()["melden"] is False
    client.put("/api/system/erwachsen/optionen", json={"melden": True})
    assert client.get("/api/system/erwachsen").json()["melden"] is True


# --- Zustellung ------------------------------------------------------------

@pytest.mark.asyncio
async def test_zustellung_haelt_18plus_zurueck(tmp_path, monkeypatch):
    """Zweite Sperre: auch eine Regel MIT Haekchen meldet nicht,
    solange der Melde-Schalter aus ist."""
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()

    from app.db import SessionLocal, init_db, set_setting
    init_db()                       # sonst gibt es die Tabellen noch nicht
    from app.erwachsen import AKTIV, MELDEN
    from app.models import Channel, Deal as D, Rule
    from app.pipeline import dispatch

    gesendet = []

    class Kanal:
        async def send(self, config, note, http):
            gesendet.append(note.titel)
            return True

    monkeypatch.setattr("app.pipeline.get_channel", lambda typ: Kanal())

    with SessionLocal() as db:
        set_setting(db, AKTIV, True)
        set_setting(db, MELDEN, False)
        kanal = Channel(type="discord", name="Test", enabled=True, config={})
        db.add(kanal)
        db.flush()
        regel = Rule(name="Alles billige", enabled=True, max_preis=100.0,
                     erwachsen=True, channels=[kanal.id])
        deal = D(url_hash="e" * 32, titel="Satisfyer Pro 2", titel_norm="s",
                 url="https://x.test/9", quelle="mydealz_erotik",
                 erwachsen=True, preis=5.0, preis_eur=5.0)
        db.add_all([regel, deal])
        db.commit()

        assert await dispatch(db, [(regel, deal)], None) == 0
        assert gesendet == []

        set_setting(db, MELDEN, True)
        db.commit()
        await dispatch(db, [(regel, deal)], None)
        assert gesendet == ["Satisfyer Pro 2"]


# --- Abos: laufende Zugaenge statt Ware -----------------------------------
#
# Der Wunsch dahinter: "im 18+ auch Abos anzeigen, die gerade guenstig
# sind - also fuer Internetseiten". Das Schwierige daran ist nicht das
# Einsammeln, sondern der Vergleich: 1 EUR fuer drei Monate ist guenstiger
# als 0,99 EUR im Monat, obwohl die Zahl groesser ist.

ABO_FEED = '''<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Premium-Zugang 3 Monate für 9 € statt 29,97 €</title>
<link>https://a.test/1</link></item>
<item><title>Satisfyer Pro 2 Vibrator für 24,99 €</title>
<link>https://a.test/2</link></item>
<item><title>Mitgliedschaft 14,99 €/Monat</title>
<link>https://a.test/3</link></item>
</channel></rss>'''


class _AboHttp:
    async def get_text(self, url, **kwargs):
        return ABO_FEED


def _abo_kontext(**optionen):
    from app.sources.base import FetchContext
    from app.sources.erwachsen import ErotikAbo

    quelle = ErotikAbo()
    opts = dict(quelle.default_options)
    opts["feeds"] = ["https://a.test/feed"]
    opts.update(optionen)
    return quelle, FetchContext(http=_AboHttp(), options=opts)


@pytest.mark.asyncio
async def test_abo_quelle_nimmt_nur_laufende_angebote():
    """Der Vibrator im selben Feed ist Ware, kein Zugang."""
    quelle, ctx = _abo_kontext()
    titel = [i.titel for i in await quelle.fetch(ctx)]
    assert len(titel) == 2
    assert not any("Vibrator" in t for t in titel)


@pytest.mark.asyncio
async def test_abo_quelle_rechnet_auf_den_monat():
    quelle, ctx = _abo_kontext()
    items = await quelle.fetch(ctx)
    drei_monate = next(i for i in items if "3 Monate" in i.titel)
    assert drei_monate.preis == 9.0 and drei_monate.preis_monat == 3.0
    monatlich = next(i for i in items if "Mitgliedschaft" in i.titel)
    assert monatlich.preis_zeitraum == "monat" and monatlich.preis_monat == 14.99


@pytest.mark.asyncio
async def test_abo_quelle_filtert_auf_den_monatspreis():
    """'Günstig' ist beim Abo nicht am Preisschild abzulesen."""
    quelle, ctx = _abo_kontext(max_preis_monat=5)
    titel = [i.titel for i in await quelle.fetch(ctx)]
    assert titel == ["Premium-Zugang 3 Monate für 9 € statt 29,97 €"]


@pytest.mark.asyncio
async def test_abo_funde_tragen_die_18er_marke():
    """Wie jeder Fund aus einer 18+-Quelle - unabhaengig vom Titel."""
    quelle, ctx = _abo_kontext()
    assert {i.kategorie for i in await quelle.fetch(ctx)} == {"erwachsen"}


@pytest.mark.asyncio
async def test_abo_quelle_laesst_sich_abschalten():
    """Ohne den Filter kommt alles durch, was in den Feeds steht."""
    quelle, ctx = _abo_kontext(nur_abos=False)
    assert len(await quelle.fetch(ctx)) == 3
