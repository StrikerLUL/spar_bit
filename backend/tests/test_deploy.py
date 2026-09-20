"""Die mitgelieferten Proxy-Vorlagen muessen gueltig sein.

Ein Tippfehler darin faellt sonst erst auf dem Server auf - und dort haelt
ein kaputtes Snippet den ganzen nginx an, nicht nur SparBit.
"""
import pathlib
import tempfile

import pytest

crossplane = pytest.importorskip("crossplane", reason="crossplane nicht installiert")

WURZEL = pathlib.Path(__file__).resolve().parents[2]
VORLAGE = WURZEL / "deploy" / "nginx-sparbit.conf"


@pytest.fixture(scope="module")
def baum():
    """Die Vorlage so einbetten, wie nginx sie auf dem Server sieht."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "sparbit.conf").write_text(
        VORLAGE.read_text().replace("DEINE-DOMAIN", "spar-bit.example.de"))
    (tmp / "nginx.conf").write_text(
        "events { worker_connections 1024; }\n"
        f"http {{\n  include {tmp / 'sparbit.conf'};\n}}\n")
    ergebnis = crossplane.parse(str(tmp / "nginx.conf"), catch_errors=True)
    assert ergebnis["status"] == "ok", ergebnis.get("errors")
    return ergebnis


def _alle(bloecke):
    for d in bloecke:
        yield d
        if d.get("block"):
            yield from _alle(d["block"])


def direktiven(baum):
    raus = []
    for datei in baum["config"]:
        raus.extend(_alle(datei["parsed"]))
    return raus


def test_nur_echte_direktiven(baum):
    from crossplane.analyzer import DIRECTIVES
    unbekannt = [d["directive"] for d in direktiven(baum)
                 if d.get("directive") and d["directive"] not in DIRECTIVES]
    assert not unbekannt, f"keine nginx-Direktiven: {unbekannt}"


def test_sse_wird_nicht_gepuffert(baum):
    """Ohne das steht der Live-Ticker - der haeufigste Proxy-Fehler."""
    events = [d for d in direktiven(baum)
              if d.get("directive") == "location" and d["args"] == ["/api/events"]]
    assert events, "Die Vorlage hat keine eigene Location fuer /api/events"
    innen = {d["directive"]: d["args"] for d in events[0]["block"]}
    assert innen.get("proxy_buffering") == ["off"]
    assert innen.get("proxy_cache") == ["off"]
    # 60 s Vorgabe wuerde den Stream im Minutentakt abreissen lassen.
    assert innen.get("proxy_read_timeout") == ["24h"]


def test_forwarded_proto_wird_gesetzt(baum):
    """Fehlt der Header, bleibt das Session-Cookie ohne Secure."""
    orte = [d for d in direktiven(baum) if d.get("directive") == "location"]
    assert orte
    for ort in orte:
        header = [d["args"] for d in ort["block"]
                  if d.get("directive") == "proxy_set_header"]
        assert ["X-Forwarded-Proto", "$scheme"] in header, ort["args"]


def test_zielt_auf_localhost():
    """Die Vorlage darf nicht versehentlich nach aussen zeigen."""
    text = VORLAGE.read_text()
    assert "127.0.0.1:8080" in text
    assert "0.0.0.0" not in text


# --- docker-compose.yml ----------------------------------------------------

COMPOSE = WURZEL / "docker-compose.yml"


def test_keine_pflichtvariablen_in_compose():
    """${VAR:?...} macht die ganze Datei unbrauchbar, nicht nur den Dienst.

    Compose loest die Datei vollstaendig auf, bevor Profile ueberhaupt
    betrachtet werden. Eine Pflichtvariable im caddy-Dienst liess damit auch
    'docker compose up backend frontend' scheitern - bei jedem, der ohne
    eigene Domain startet.
    """
    import re
    treffer = re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?", COMPOSE.read_text())
    assert not treffer, (
        f"Pflichtvariablen in docker-compose.yml: {treffer}. "
        "Stattdessen ${VAR:-} nehmen und im Dienst selbst pruefen.")


def test_caddy_meldet_die_fehlende_domain_selbst():
    """Der Ersatz fuer die Pflichtvariable muss auch wirklich greifen."""
    import yaml
    caddy = yaml.safe_load(COMPOSE.read_text())["services"]["caddy"]
    assert caddy["profiles"] == ["https"]
    skript = caddy["command"][0]
    # $$ ist die Compose-Schreibweise fuer ein literales $ - ohne das
    # ersetzte Compose die Variable selbst und die Pruefung liefe ins Leere.
    assert '[ -z "$$SPARBIT_DOMAIN" ]' in skript
    assert "exit 1" in skript
    assert "exec caddy run" in skript


def test_compose_loest_ohne_domain_auf(tmp_path):
    """Die Gegenprobe mit dem echten Compose - der Fall, der gescheitert ist."""
    import shutil
    import subprocess
    if shutil.which("docker") is None:
        pytest.skip("docker nicht verfuegbar")

    umgebung = tmp_path / "env"
    umgebung.write_text("SPARBIT_DOMAIN=\nSPARBIT_WEB_PORT=8080\n")
    ergebnis = subprocess.run(
        ["docker", "compose", "--env-file", str(umgebung), "config", "--services"],
        capture_output=True, text=True, cwd=str(WURZEL), timeout=120)
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "frontend" in ergebnis.stdout


# --- Auto-Updater ----------------------------------------------------------

SKRIPT = WURZEL / "deploy" / "sparbit-autoupdate.sh"
UNIT = WURZEL / "deploy" / "sparbit-update.service"
TIMER = WURZEL / "deploy" / "sparbit-update.timer"


def test_updater_skript_ist_gueltige_shell():
    import shutil
    import subprocess
    if shutil.which("bash") is None:
        pytest.skip("bash fehlt")
    lauf = subprocess.run(["bash", "-n", str(SKRIPT)], capture_output=True, text=True)
    assert lauf.returncode == 0, lauf.stderr


def test_updater_ist_ausfuehrbar():
    import os
    assert os.access(SKRIPT, os.X_OK), "systemd startet nur ein ausführbares Skript"


def test_updater_faellt_ohne_token_weich_aus():
    """Ohne Token darf das Skript nicht blind loslaufen."""
    text = SKRIPT.read_text()
    assert 'if [ -z "$TOKEN" ]' in text
    assert "exit 0" in text


def test_updater_unterscheidet_403_von_server_aus():
    """Sonst sucht man bei einem Tippfehler im Token am falschen Ende."""
    text = SKRIPT.read_text()
    assert "403)" in text
    assert "000|" in text          # curl meldet 000, wenn nichts zustande kam


def test_updater_zieht_nur_vorwaerts():
    """Ein Merge oder Reset wuerde lokale Stände auf dem Server zerstören."""
    text = SKRIPT.read_text()
    assert "merge --ff-only" in text
    assert "reset --hard" not in text
    assert "checkout -f" not in text


def test_updater_sichert_vor_dem_einspielen():
    assert "sparbit sichern" in SKRIPT.read_text()


def test_updater_laeuft_nur_einmal_gleichzeitig():
    text = SKRIPT.read_text()
    assert 'mkdir "$SPERRE"' in text
    assert "trap" in text


def test_systemd_units_sind_lesbar():
    import configparser
    for pfad in (UNIT, TIMER):
        c = configparser.ConfigParser(strict=False)
        c.optionxform = str
        c.read(pfad)
        assert c.sections(), pfad.name

    c = configparser.ConfigParser(strict=False)
    c.optionxform = str
    c.read(TIMER)
    # Minuetlich, damit der Knopf im UI zuegig wirkt.
    assert c["Timer"]["OnUnitActiveSec"] == "1min"
    assert c["Timer"]["Unit"] == "sparbit-update.service"

    c = configparser.ConfigParser(strict=False)
    c.optionxform = str
    c.read(UNIT)
    assert c["Service"]["Type"] == "oneshot"
    # Ein haengender Build darf den Timer nicht dauerhaft blockieren.
    assert "TimeoutStartSec" in c["Service"]


def test_installer_legt_ein_token_an():
    text = (WURZEL / "install.sh").read_text()
    assert "setze SPARBIT_UPDATE_TOKEN" in text
    assert "openssl rand -hex 32" in text
    # Der Timer darf nicht als root laufen - sonst gehoeren die von git
    # angelegten Dateien danach root und "./sparbit update" scheitert.
    assert "User=$besitzer" in text


def test_manuelles_update_nutzt_dieselbe_sperre():
    """Zwei gleichzeitige Builds am selben Compose-Projekt gehen schief."""
    text = (WURZEL / "sparbit").read_text()
    assert "mkdir .update/sperre" in text
    assert "trap 'rmdir .update/sperre" in text


def test_watchdog_laeuft_als_job():
    """Ohne den Job prüft sich SparBit nie selbst."""
    import inspect
    from app import scheduler
    quelle = inspect.getsource(scheduler.start)
    assert 'id="watchdog"' in quelle
    assert "watchdog_job" in quelle
