"""Fristen: erkennen, erinnern, in den Kalender legen.

Ein Rabatt, den man morgen auch noch mitnimmt, ist ein Rabatt. Ein
Gratis-Spiel, das Donnerstag um 17 Uhr verschwindet, ist ein Termin.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.ablauf import aus_roh, aus_text, bestimme

JETZT = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("text,erwartet", [
    ("Nur bis 31.10. gratis", datetime(2026, 10, 31, 23, 59, tzinfo=UTC)),
    ("Angebot endet am 05.11.2026", datetime(2026, 11, 5, 23, 59, tzinfo=UTC)),
    ("gültig bis 5. November", datetime(2026, 11, 5, 23, 59, tzinfo=UTC)),
    ("Nur noch 6 Stunden!", datetime(2026, 9, 21, 18, 0, tzinfo=UTC)),
    ("noch 3 Tage", datetime(2026, 9, 24, 12, 0, tzinfo=UTC)),
])
def test_frist_aus_dem_text(text, erwartet):
    assert aus_text(text, JETZT) == erwartet


def test_jahreswechsel_wird_mitgedacht():
    """Steht im Dezember 'bis 05.01.', ist der Januar danach gemeint."""
    dezember = datetime(2026, 12, 20, 10, 0, tzinfo=UTC)
    assert aus_text("nur bis 05.01.", dezember).year == 2027


@pytest.mark.parametrize("text", [
    "Bester Deal aller Zeiten",
    "Sony WH-1000XM5 für 249 statt 419",
    "",
    "bis 45.13. gültig",
])
def test_lieber_kein_datum_als_ein_falsches(text):
    """Ein erfundener Countdown waere schlimmer als gar keiner."""
    assert aus_text(text, JETZT) is None


def test_ein_jahr_voraus_ist_ein_lesefehler():
    assert aus_text("bis 01.01.2099", JETZT) is None


def test_rohdaten_schlagen_den_text():
    """Epic schickt endDate seit jeher mit - das ist die sichere Angabe."""
    ende = bestimme("Gratis bis 31.10.", None,
                    {"endDate": "2026-09-25T15:00:00.000Z"}, JETZT)
    assert ende == datetime(2026, 9, 25, 15, 0, tzinfo=UTC)


def test_rohdaten_als_zeitstempel():
    assert aus_roh({"expires": 1790000000}).year == 2026


# --- Erinnerung -----------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    lade_app_neu()
    from app.db import SessionLocal, init_db
    init_db()
    return SessionLocal


def deal(sitzung, **felder):
    from app.models import Deal, utcnow
    standard = dict(url_hash=felder.pop("hash", "h1"), titel="Gratis-Spiel",
                    titel_norm="gratis spiel", url="https://x/1",
                    quelle="test", ist_gratis=True,
                    laeuft_ab=utcnow() + timedelta(hours=4))
    standard.update(felder)
    d = Deal(**standard)
    sitzung.add(d)
    sitzung.commit()
    return d


def test_was_bald_endet_und_mich_angeht(db):
    from app.pipeline import auslaufende

    with db() as sitzung:
        gratis = deal(sitzung, hash="a")
        deal(sitzung, hash="b", titel="Rabatt", ist_gratis=False,
             url="https://x/2", bookmarked=False)
        gemerkt = deal(sitzung, hash="c", titel="Gemerkt", ist_gratis=False,
                       url="https://x/3", bookmarked=True)

        treffer = auslaufende(sitzung)
        ids = {d.id for d in treffer}
        assert gratis.id in ids, "gratis ist immer interessant"
        assert gemerkt.id in ids, "gemerkt sowieso"
        assert len(ids) == 2, "der ungemerkte Rabatt nicht"


def test_was_erst_naechste_woche_endet_kommt_nicht(db):
    from app.models import utcnow
    from app.pipeline import auslaufende

    with db() as sitzung:
        deal(sitzung, laeuft_ab=utcnow() + timedelta(days=7))
        assert auslaufende(sitzung) == []


def test_jede_frist_wird_nur_einmal_gemeldet(db):
    from app.models import utcnow
    from app.pipeline import auslaufende

    with db() as sitzung:
        eintrag = deal(sitzung)
        assert len(auslaufende(sitzung)) == 1
        eintrag.ablauf_gemeldet_am = utcnow()
        sitzung.commit()
        assert auslaufende(sitzung) == []


@pytest.mark.asyncio
async def test_meldung_geht_raus_und_nennt_die_restzeit(db, monkeypatch):
    import app.pipeline.versand as versand
    from app.models import Channel
    from app.pipeline import dispatch_ablauf

    gesendet = []

    class Kanal:
        async def send(self, config, note, http):
            gesendet.append(note)

    monkeypatch.setattr(versand, "get_channel", lambda typ: Kanal())

    with db() as sitzung:
        sitzung.add(Channel(type="telegram", name="Test", enabled=True, config={}))
        sitzung.commit()
        deal(sitzung)

        anzahl = await dispatch_ablauf(sitzung, http=None)
        assert anzahl == 1
        assert "Läuft aus" in gesendet[0].titel
        assert "4 h" in gesendet[0].beschreibung
        assert gesendet[0].prioritaet == "SOFORT"

        # Beim zweiten Lauf ist nichts mehr offen.
        assert await dispatch_ablauf(sitzung, http=None) == 0


@pytest.mark.asyncio
async def test_ohne_kanal_bleibt_die_frist_offen(db):
    """Sonst faellt die Meldung aus, sobald wieder ein Kanal da ist."""
    from app.pipeline import auslaufende, dispatch_ablauf

    with db() as sitzung:
        deal(sitzung)
        assert await dispatch_ablauf(sitzung, http=None) == 0
        assert len(auslaufende(sitzung)) == 1


# --- Kalender -------------------------------------------------------------

def test_kalender_ist_gueltiges_ical(db):
    from app.kalender import feed

    with db() as sitzung:
        deal(sitzung, titel="Gratis: Control")
        text = feed(sitzung)

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip().endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" in text and "END:VEVENT" in text
    assert "SUMMARY:Gratis endet: Gratis: Control" in text
    assert "TRIGGER:-PT6H" in text, "Erinnerung vorher"
    # Jede Zeile endet mit CRLF und ist hoechstens 75 Oktetts lang.
    for zeile in text.split("\r\n"):
        assert len(zeile.encode("utf-8")) <= 75, zeile


def test_sonderzeichen_werden_maskiert(db):
    from app.kalender import feed

    with db() as sitzung:
        deal(sitzung, titel="Spiel, mit Komma; und Semikolon")
        text = feed(sitzung)
    assert r"Komma\; und" in text or r"Komma\," in text
    assert "Komma; und Semikolon" not in text


def test_kalender_braucht_ein_token(db):
    from conftest import lade_app_neu
    from fastapi.testclient import TestClient
    main = lade_app_neu()
    with TestClient(main.app) as client:
        assert client.get("/api/kalender.ics?token=falschesToken").status_code == 401
        assert client.get("/api/kalender.ics").status_code == 422
