"""Der Job-Abgleich darf laufende Quellen nicht ausbremsen.

sync_jobs() laeuft jede Minute, damit Aenderungen aus der CLI im laufenden
Server greifen. Wuerde dabei jedes Mal reschedule() aufgerufen, waere die
naechste Laufzeit jedes Mal zurueckgesetzt - eine Quelle mit 30-Minuten-
Intervall kaeme dann nie an die Reihe.
"""
from dataclasses import dataclass, field

import pytest

from app import scheduler as sched
from app.sources import all_sources


@dataclass
class FakeConfig:
    id: str
    enabled: bool = True
    interval_seconds: int = 1800
    options: dict = field(default_factory=dict)
    api_key: str | None = None


@pytest.fixture
def quelle_id():
    return next(iter(all_sources())).id


@pytest.fixture(autouse=True)
def leerer_scheduler():
    for job in list(sched.scheduler.get_jobs()):
        job.remove()
    yield
    for job in list(sched.scheduler.get_jobs()):
        job.remove()


def test_job_wird_angelegt(quelle_id):
    sched.schedule_source(FakeConfig(quelle_id))
    job = sched.scheduler.get_job(f"src:{quelle_id}")
    assert job is not None
    assert sched._aktuelles_intervall(job) == 1800


def test_wiederholter_abgleich_verschiebt_die_laufzeit_nicht(quelle_id):
    cfg = FakeConfig(quelle_id)
    sched.schedule_source(cfg)
    vorher = sched.scheduler.get_job(f"src:{quelle_id}").next_run_time

    for _ in range(5):
        sched.schedule_source(cfg)

    nachher = sched.scheduler.get_job(f"src:{quelle_id}").next_run_time
    assert nachher == vorher


def test_geaendertes_intervall_greift(quelle_id):
    sched.schedule_source(FakeConfig(quelle_id, interval_seconds=1800))
    sched.schedule_source(FakeConfig(quelle_id, interval_seconds=600))
    job = sched.scheduler.get_job(f"src:{quelle_id}")
    assert sched._aktuelles_intervall(job) == 600


def test_mindestintervall_wird_erzwungen(quelle_id):
    src = sched.get_source(quelle_id)
    sched.schedule_source(FakeConfig(quelle_id, interval_seconds=1))
    job = sched.scheduler.get_job(f"src:{quelle_id}")
    assert sched._aktuelles_intervall(job) == src.min_interval


def test_deaktivieren_entfernt_den_job(quelle_id):
    sched.schedule_source(FakeConfig(quelle_id))
    assert sched.scheduler.get_job(f"src:{quelle_id}") is not None
    sched.schedule_source(FakeConfig(quelle_id, enabled=False))
    assert sched.scheduler.get_job(f"src:{quelle_id}") is None


def test_sync_ist_als_job_registriert():
    """Ohne diesen Job greifen CLI-Aenderungen erst beim Neustart."""
    import inspect
    quelle = inspect.getsource(sched.start)
    assert 'id="sync"' in quelle
    assert "sync_jobs" in quelle


# --- Zeitstempel aus der Datenbank -----------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import lade_app_neu
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    lade_app_neu()
    from app.db import SessionLocal, init_db
    init_db()
    return SessionLocal


def test_zeitstempel_behalten_ihre_zeitzone(db):
    """SQLite gibt sonst naive Zeitstempel zurück.

    Der Schutzschalter verglich circuit_open_until mit utcnow() und starb
    daran, sobald er einmal zugemacht hatte - die Quelle lief nie wieder
    an. Dasselbe traf die Stummschaltung und die Sperrfrist des
    Preisfehler-Wächters.
    """
    from datetime import timedelta
    from app.models import SourceConfig, utcnow

    with db() as sitzung:
        sitzung.add(SourceConfig(id="probe", enabled=True,
                                 circuit_open_until=utcnow() + timedelta(minutes=30),
                                 snooze_until=utcnow() + timedelta(hours=6),
                                 last_success=utcnow()))
        sitzung.commit()

    with db() as sitzung:
        cfg = sitzung.get(SourceConfig, "probe")
        for feld in ("circuit_open_until", "snooze_until", "last_success"):
            wert = getattr(cfg, feld)
            assert wert.tzinfo is not None, f"{feld} kam ohne Zeitzone zurück"
        # Der Vergleich, an dem es gescheitert ist:
        assert cfg.circuit_open_until > utcnow()
        assert cfg.last_success <= utcnow()


@pytest.mark.asyncio
async def test_offener_schutzschalter_ueberspringt_statt_zu_werfen(db, quelle_id):
    from datetime import timedelta
    from app.models import SourceConfig, utcnow
    from app import scheduler as sched_neu

    with db() as sitzung:
        sitzung.add(SourceConfig(id=quelle_id, enabled=True,
                                 consecutive_failures=5,
                                 circuit_open_until=utcnow() + timedelta(minutes=30)))
        sitzung.commit()

    ergebnis = await sched_neu.run_source(quelle_id)
    assert ergebnis.get("skipped") == "Circuit Breaker offen"
