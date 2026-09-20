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
