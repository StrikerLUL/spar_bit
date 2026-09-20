"""Selbstüberwachung: erkennt sie echte Ausfälle, und hält sie den Mund?

Beide Hälften zählen. Ein Wächter, der Ausfälle übersieht, ist nutzlos -
einer, der täglich klagt, wird stummgeschaltet und ist dann genauso nutzlos.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import watchdog
from app.db import get_setting
from app.models import Channel, NotificationLog, SourceConfig, utcnow


@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import lade_app_neu
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    lade_app_neu()
    from app.db import SessionLocal, init_db
    init_db()
    with SessionLocal() as sitzung:
        yield sitzung


def quelle(db, **kw):
    grund = dict(id="mydealz", enabled=True, interval_seconds=900,
                 total_runs=10, total_errors=0, last_success=utcnow())
    cfg = SourceConfig(**{**grund, **kw})
    db.add(cfg)
    db.commit()
    return cfg


# --- Quellen ---------------------------------------------------------------

def test_gesunde_quelle_meldet_nichts(db):
    quelle(db)
    assert watchdog.pruefe(db) == []


def test_ausgeschaltete_quelle_ist_kein_problem(db):
    """Wer sie abgeschaltet hat, weiß Bescheid."""
    quelle(db, enabled=False, last_success=utcnow() - timedelta(days=30))
    assert watchdog.pruefe(db) == []


def test_gesperrte_quelle_wird_gemeldet(db):
    quelle(db, consecutive_failures=5, last_error="HTTP 403: Forbidden",
           circuit_open_until=utcnow() + timedelta(minutes=20))
    befunde = watchdog.pruefe(db)
    assert len(befunde) == 1
    assert befunde[0].art == "quelle_gesperrt"
    assert "mydealz" in befunde[0].text
    assert "403" in befunde[0].rat


def test_stille_quelle_wird_gemeldet(db):
    quelle(db, last_success=utcnow() - timedelta(hours=30))
    befunde = watchdog.pruefe(db)
    assert len(befunde) == 1
    assert befunde[0].art == "quelle_still"
    assert "30 Stunden" in befunde[0].text


def test_frisch_eingeschaltete_quelle_bekommt_zeit(db):
    """Noch nie gelaufen ist kein Ausfall - nur noch keine Gelegenheit."""
    quelle(db, last_success=None, total_runs=0, total_errors=0)
    assert watchdog.pruefe(db) == []


def test_quelle_die_nur_scheitert_wird_gemeldet(db):
    quelle(db, last_success=None, total_runs=5, total_errors=5,
           last_error="Timeout")
    befunde = watchdog.pruefe(db)
    assert len(befunde) == 1
    assert "noch nie" in befunde[0].text


def test_kurze_stille_reicht_nicht(db):
    quelle(db, last_success=utcnow() - timedelta(hours=6))
    assert watchdog.pruefe(db) == []


# --- Kanaele ---------------------------------------------------------------

def kanal(db, **kw):
    grund = dict(type="telegram", name="Handy", enabled=True, config={})
    row = Channel(**{**grund, **kw})
    db.add(row)
    db.commit()
    return row


def protokoll(db, kanal_id, *erfolge, fehler="HTTP 401: Unauthorized"):
    for i, ok in enumerate(erfolge):
        db.add(NotificationLog(
            channel_id=kanal_id, channel_type="telegram", ok=ok,
            error=None if ok else fehler,
            created_at=utcnow() - timedelta(minutes=10 - i)))
    db.commit()


def test_kanal_mit_lauter_fehlern_wird_gemeldet(db):
    k = kanal(db)
    protokoll(db, k.id, False, False, False)
    befunde = watchdog.pruefe(db)
    assert len(befunde) == 1
    assert befunde[0].art == "kanal_fehler"
    assert "401" in befunde[0].rat


def test_ein_ausrutscher_reicht_nicht(db):
    """Sonst stuende ein Kanal nach einem einzelnen Netzfehler auf Rot."""
    k = kanal(db)
    protokoll(db, k.id, False, True, True)
    assert watchdog.pruefe(db) == []


def test_alter_fehler_ohne_neue_versuche_zaehlt_nicht(db):
    """error_count wird nie zurueckgesetzt - danach darf nicht geurteilt werden."""
    k = kanal(db, error_count=99)
    protokoll(db, k.id, True, True, True)
    assert watchdog.pruefe(db) == []


def test_kanal_ohne_verlauf_wird_nicht_beurteilt(db):
    kanal(db)
    assert watchdog.pruefe(db) == []


# --- Drosselung ------------------------------------------------------------

def test_dasselbe_problem_wird_nicht_taeglich_wiederholt(db):
    quelle(db, last_success=utcnow() - timedelta(hours=30))
    befunde = watchdog.pruefe(db)

    erste = watchdog.faellig(db, befunde)
    assert len(erste.probleme) == 1
    watchdog.merke(db, erste)

    zweite = watchdog.faellig(db, befunde)
    assert zweite.probleme == []


def test_nach_einem_tag_wird_erinnert(db):
    quelle(db, last_success=utcnow() - timedelta(hours=30))
    befunde = watchdog.pruefe(db)
    watchdog.merke(db, watchdog.faellig(db, befunde),
                   jetzt=utcnow() - timedelta(hours=25))
    assert len(watchdog.faellig(db, befunde).probleme) == 1


def test_behobenes_problem_gibt_entwarnung_genau_einmal(db):
    cfg = quelle(db, last_success=utcnow() - timedelta(hours=30))
    watchdog.merke(db, watchdog.faellig(db, watchdog.pruefe(db)))

    cfg.last_success = utcnow()
    db.commit()

    lage = watchdog.faellig(db, watchdog.pruefe(db))
    assert lage.entwarnungen == ["quelle_still:mydealz"]
    assert "läuft wieder" in watchdog.text_fuer_entwarnung(lage.entwarnungen[0])
    watchdog.merke(db, lage)

    assert watchdog.faellig(db, watchdog.pruefe(db)).entwarnungen == []


def test_pruefen_veraendert_nichts(db):
    """Das UI ruft dieselbe Funktion - sie darf die Drosselung nicht verbrauchen."""
    quelle(db, last_success=utcnow() - timedelta(hours=30))
    watchdog.pruefe(db)
    watchdog.faellig(db, watchdog.pruefe(db))
    assert get_setting(db, watchdog.SCHLUESSEL) in (None, {})
