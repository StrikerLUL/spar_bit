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
