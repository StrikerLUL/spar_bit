"""Der Scheduler als eigener Dienst.

Die eine Sache, die dabei wirklich schiefgehen kann, ist unsichtbar:
laeuft der Scheduler im Worker UND im API-Prozess, wird jede Quelle
doppelt abgefragt und jede Meldung doppelt verschickt. Das faellt
niemandem als Fehler auf - es sieht aus, als waere der Feed voll.

Darum prueft dieser Test vor allem, dass die Entscheidung „laeuft er
hier?" eindeutig ist und dass ein falsch gesetzter Schalter eine
Warnung erzeugt.
"""
import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    return lade_app_neu()


@pytest.mark.parametrize("wert,laeuft_hier", [
    ("auto", True), ("", True), ("an", True), ("irgendwas", True),
    ("aus", False), ("AUS", False), ("off", False), ("0", False),
    ("false", False),
])
def test_der_schalter_wird_eindeutig_gelesen(app, wert, laeuft_hier):
    """Ein Tippfehler darf nicht dazu fuehren, dass gar nichts einsammelt.
    Im Zweifel laeuft der Scheduler - das ist der Normalfall."""
    from app.config import Settings

    assert Settings(scheduler=wert).scheduler_hier is laeuft_hier


def starte_ohne_schleife(monkeypatch, scheduler: str) -> list[str]:
    """main() ausfuehren, ohne die Ereignisschleife wirklich zu starten.

    Gibt die Warnungen zurueck. Nicht ueber caplog: setup_logging() raeumt
    die Wurzel-Handler ab (Absicht - der Worker soll sein eigenes Format
    schreiben) und nimmt caplogs Handler mit. Der Ringpuffer, den das UI
    ohnehin liest, ist der ehrlichere Ort zum Nachsehen.
    """
    import app.worker as worker
    from app.logging_setup import recent_logs

    vorher = len(recent_logs(limit=1000))
    gelaufen = []
    monkeypatch.setattr(worker.asyncio, "run", lambda ko: gelaufen.append(ko))
    monkeypatch.setattr(worker.settings, "scheduler", scheduler)

    worker.main()

    assert gelaufen, "main() hat die Schleife gar nicht erst gestartet"
    gelaufen[0].close()          # sonst: "coroutine was never awaited"

    neu = recent_logs(limit=1000)[:max(0, len(recent_logs(limit=1000)) - vorher)]
    return [e["message"] for e in neu if e["level"] == "WARNING"]


def test_der_worker_warnt_wenn_daneben_auch_gesammelt_wird(app, monkeypatch):
    """Beide an heisst: jeder Deal kommt doppelt. Der Worker startet
    trotzdem - er soll es nur sagen."""
    warnungen = starte_ohne_schleife(monkeypatch, "auto")
    assert any("SPARBIT_SCHEDULER" in w for w in warnungen), warnungen


def test_bei_richtiger_einstellung_warnt_er_nicht(app, monkeypatch):
    warnungen = starte_ohne_schleife(monkeypatch, "aus")
    assert not [w for w in warnungen if "SPARBIT_SCHEDULER" in w]


def test_strg_c_ist_kein_fehler(app, monkeypatch):
    """Ein Dienst, der sich beim Beenden mit einem Stacktrace verabschiedet,
    sieht in jedem Protokoll wie ein Absturz aus."""
    import app.worker as worker

    def bricht_ab(ko):
        ko.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.asyncio, "run", bricht_ab)
    monkeypatch.setattr(worker.settings, "scheduler", "aus")
    worker.main()                                    # wirft nicht
