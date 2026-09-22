"""Der Live-Ticker, wenn Scheduler und API in zwei Prozessen laufen.

Zwei Prozesse teilen keine Warteschlange. Ohne Umweg ueber die Datenbank
waere der Ticker im Worker-Betrieb still - und ein stiller Ticker sieht
aus wie ein Defekt, nicht wie eine Betriebsart.

Der Umweg darf zweierlei nicht: den Quellenlauf aufhalten, wenn er
scheitert, und dem Zuschauer beim Aufmachen eine Stunde Vergangenheit
ins Gesicht schuetten.
"""
import json

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    main = lade_app_neu()
    from app.db import init_db
    init_db()
    return main


@pytest.fixture
def broker(app):
    from app.events import broker as b

    b.spiegeln = False
    yield b
    b.spiegeln = False


def test_im_normalbetrieb_wird_nichts_geschrieben(broker, app):
    """Eine Schreiboperation je Fund, fuer niemanden - das waere der Preis
    einer Spiegelung, die immer an ist."""
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import EventLog

    broker.publish("deal", {"titel": "Test"})
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EventLog)) == 0


def test_der_worker_spiegelt(broker, app):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import EventLog

    broker.spiegeln = True
    broker.publish("deal", {"titel": "LEGO", "preis": 49.99})

    with SessionLocal() as db:
        zeile = db.scalars(select(EventLog)).first()
    assert zeile.event == "deal"
    assert zeile.daten["titel"] == "LEGO"


def test_datumswerte_ueberstehen_den_umweg(broker, app):
    """JSON kennt kein datetime. Ohne Umwandlung waere die Spalte leer -
    und der Ticker zeigte einen Fund ohne Zeit."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import EventLog

    broker.spiegeln = True
    broker.publish("deal", {"zeit": datetime(2026, 1, 1, tzinfo=UTC)})
    with SessionLocal() as db:
        zeile = db.scalars(select(EventLog)).first()
    assert "2026-01-01" in zeile.daten["zeit"]


def test_ein_fehler_beim_spiegeln_haelt_den_lauf_nicht_auf(broker, app, monkeypatch):
    """Der Ticker ist Beiwerk, das Einsammeln ist die Arbeit."""
    def kaputt(*a, **kw):
        raise RuntimeError("Datenbank weg")

    import app.events as ev
    monkeypatch.setattr(ev.EventBroker, "_in_die_db", staticmethod(kaputt))
    broker.spiegeln = True
    broker.publish("deal", {"titel": "Test"})      # wirft nicht


def test_die_erste_nachlese_liefert_keine_vergangenheit(broker, app):
    """Wer gerade erst zusieht, will nicht die letzte Stunde nachgereicht
    bekommen - nur die Marke, ab der es weitergeht."""
    from app.events import nachlese

    broker.spiegeln = True
    for i in range(3):
        broker.publish("deal", {"nr": i})

    marke, nutzlasten = nachlese(None)
    assert nutzlasten == []
    assert marke == 3


def test_die_nachlese_holt_genau_das_neue(broker, app):
    from app.events import nachlese

    broker.spiegeln = True
    broker.publish("deal", {"nr": 1})
    marke, _ = nachlese(None)

    broker.publish("deal", {"nr": 2})
    broker.publish("match", {"regel": "Lego"})

    marke, nutzlasten = nachlese(marke)
    assert len(nutzlasten) == 2
    ereignisse = [json.loads(n) for n in nutzlasten]
    assert ereignisse[0]["data"]["nr"] == 2
    assert ereignisse[1]["event"] == "match"

    # Zweimal lesen liefert nicht zweimal dasselbe.
    _, nochmal = nachlese(marke)
    assert nochmal == []


def test_die_nachlese_ist_gedeckelt(broker, app):
    """Wer lange nicht hingesehen hat, bekommt nicht alles auf einmal."""
    from app.events import NACHLESE_MAX, nachlese

    broker.spiegeln = True
    marke, _ = nachlese(None)
    for i in range(NACHLESE_MAX + 10):
        broker.publish("deal", {"nr": i})

    _, nutzlasten = nachlese(marke)
    assert len(nutzlasten) == NACHLESE_MAX


def test_die_nutzlast_sieht_aus_wie_die_direkte(broker, app):
    """Der Ticker im Browser darf nicht merken, welchen Weg ein Ereignis
    genommen hat."""
    from app.events import nachlese

    broker.spiegeln = True
    marke, _ = nachlese(None)
    broker.publish("deal", {"titel": "LEGO"})
    _, nutzlasten = nachlese(marke)

    gelesen = json.loads(nutzlasten[0])
    assert set(gelesen) == {"event", "data"}
    assert gelesen["event"] == "deal"
    assert gelesen["data"]["titel"] == "LEGO"


def test_null_ist_eine_gueltige_marke_und_kein_sonderfall(broker, app):
    """Bei leerer Tabelle ist 0 die echte Marke. Waere 0 zugleich das
    Zeichen fuer „noch nichts gesehen", gingen die allerersten Ereignisse
    einer frischen Anlage verloren."""
    from app.events import nachlese

    broker.spiegeln = True
    marke, _ = nachlese(None)
    assert marke == 0

    broker.publish("deal", {"nr": 1})
    marke, nutzlasten = nachlese(marke)
    assert len(nutzlasten) == 1
