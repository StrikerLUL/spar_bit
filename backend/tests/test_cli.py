"""Die CLI gegen eine echte, temporaere Datenbank fahren.

Als Unterprozess, weil genau das der Benutzer tut - inklusive Exit-Codes,
Datenbank-Anlage und Ausgabe. Ohne Netz: alles, was hier geprueft wird,
arbeitet nur auf der lokalen Datei.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
CLI = WURZEL / "cli.py"


@pytest.fixture(scope="module")
def datendir(tmp_path_factory):
    return tmp_path_factory.mktemp("cli-daten")


def rufe(datendir, *args):
    umgebung = {**os.environ, "SPARBIT_DATA_DIR": str(datendir), "NO_COLOR": "1"}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True,
                          text=True, env=umgebung, cwd=str(WURZEL), timeout=120)


# --- Grundlagen ------------------------------------------------------------

def test_hilfe_ohne_datenbank(tmp_path):
    e = rufe(tmp_path / "leer", "--help")
    assert e.returncode == 0
    for bereich in ("kanaele", "quellen", "regeln", "wunschliste", "deals"):
        assert bereich in e.stdout


def test_status_auf_frischer_datenbank(datendir):
    e = rufe(datendir, "status")
    assert e.returncode == 0, e.stderr
    assert "Deals gesamt" in e.stdout


def test_quellen_gibt_es_ohne_serverstart(datendir):
    """ensure_source_rows() muss die CLI selbst erledigen."""
    e = rufe(datendir, "quellen", "liste")
    assert e.returncode == 0, e.stderr
    assert "mydealz" in e.stdout


# --- Kanaele ---------------------------------------------------------------

def test_alle_typen_werden_gelistet(datendir):
    e = rufe(datendir, "kanaele", "typen")
    assert e.returncode == 0
    for typ in ("discord", "slack", "matrix", "gotify", "pushover",
                "telegram", "ntfy", "smtp", "webhook"):
        assert typ in e.stdout, typ


def test_pflichtfeld_fehlt(datendir):
    e = rufe(datendir, "kanaele", "hinzufuegen", "discord", "Test")
    assert e.returncode == 1
    assert "url" in e.stdout


def test_unbekanntes_feld_wird_abgelehnt(datendir):
    e = rufe(datendir, "kanaele", "hinzufuegen", "discord", "Test",
             "--set", "urll=https://discord.com/api/webhooks/1/x")
    assert e.returncode == 1
    assert "urll" in e.stdout


def test_unbekannter_typ(datendir):
    e = rufe(datendir, "kanaele", "hinzufuegen", "signal", "Test")
    assert e.returncode == 1
    assert "signal" in e.stdout


def test_kanal_anlegen_aendern_loeschen(datendir):
    e = rufe(datendir, "kanaele", "hinzufuegen", "slack", "Team",
             "--set", "url=https://hooks.slack.com/services/A/B/C")
    assert e.returncode == 0, e.stdout + e.stderr

    liste = rufe(datendir, "kanaele", "liste")
    assert "Team" in liste.stdout and "slack" in liste.stdout

    kid = _letzte_kanal_id(datendir)
    assert rufe(datendir, "kanaele", "aendern", str(kid), "--aus").returncode == 0
    assert "nein" in rufe(datendir, "kanaele", "liste").stdout

    assert rufe(datendir, "kanaele", "aendern", str(kid),
                "--set", "quatsch=1").returncode == 1
    assert rufe(datendir, "kanaele", "loeschen", str(kid)).returncode == 0
    assert "Team" not in rufe(datendir, "kanaele", "liste").stdout


def _letzte_kanal_id(datendir) -> int:
    code = (
        "import sys;sys.path.insert(0,'backend');"
        "from sqlalchemy import select;"
        "from app.db import SessionLocal;from app.models import Channel;"
        "db=SessionLocal();"
        "print(max(c.id for c in db.scalars(select(Channel))))"
    )
    e = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(WURZEL),
                       env={**os.environ, "SPARBIT_DATA_DIR": str(datendir)})
    return int(e.stdout.strip())


# --- Quellen ---------------------------------------------------------------

def test_quelle_an_und_aus(datendir):
    assert rufe(datendir, "quellen", "an", "epic").returncode == 0
    assert "an" in rufe(datendir, "quellen", "liste").stdout
    assert rufe(datendir, "quellen", "aus", "epic").returncode == 0


def test_tippfehler_schlaegt_die_richtige_quelle_vor(datendir):
    e = rufe(datendir, "quellen", "an", "epic_free")
    assert e.returncode == 1
    assert "Meintest du epic" in e.stdout


def test_mindestintervall_wird_nicht_unterschritten(datendir):
    e = rufe(datendir, "quellen", "intervall", "epic", "1")
    assert e.returncode == 0
    assert "Mindestintervall" in e.stdout


# --- Regeln ----------------------------------------------------------------

def test_regel_ohne_bedingung_wird_abgelehnt(datendir):
    e = rufe(datendir, "regeln", "hinzufuegen", "Leer")
    assert e.returncode == 1
    assert "Bedingung" in e.stdout


def test_widerspruechliche_regel_wird_abgelehnt(datendir):
    e = rufe(datendir, "regeln", "hinzufuegen", "Widerspruch",
             "--keyword", "lego", "--blacklist", "LEGO")
    assert e.returncode == 1
    assert "Blacklist" in e.stdout


def test_regel_zeigt_oder_und_und(datendir):
    assert rufe(datendir, "regeln", "hinzufuegen", "Konsolen",
                "--keyword", "ps5", "--keyword", "xbox",
                "--pflicht", "bundle", "--blacklist", "gebraucht",
                "--max-preis", "399").returncode == 0
    aus = rufe(datendir, "regeln", "liste").stdout
    assert "ps5 oder xbox" in aus
    assert "bundle" in aus
    assert "ohne gebraucht" in aus
    assert "≤399€" in aus


def test_regel_pausieren(datendir):
    rid = _letzte_regel_id(datendir)
    assert rufe(datendir, "regeln", "aus", str(rid)).returncode == 0
    assert rufe(datendir, "regeln", "an", str(rid)).returncode == 0
    assert rufe(datendir, "regeln", "loeschen", str(rid)).returncode == 0


def _letzte_regel_id(datendir) -> int:
    code = (
        "import sys;sys.path.insert(0,'backend');"
        "from sqlalchemy import select;"
        "from app.db import SessionLocal;from app.models import Rule;"
        "db=SessionLocal();"
        "print(max(r.id for r in db.scalars(select(Rule))))"
    )
    e = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(WURZEL),
                       env={**os.environ, "SPARBIT_DATA_DIR": str(datendir)})
    return int(e.stdout.strip())


# --- Deals -----------------------------------------------------------------

def test_deals_leer(datendir):
    e = rufe(datendir, "deals")
    assert e.returncode == 0
    assert "nichts vorhanden" in e.stdout


# --- reine Hilfsfunktionen -------------------------------------------------

def lade_cli(name="sparbit_cli"):
    """cli.py als Modul laden.

    SPARBIT_CLI_REEXEC verhindert, dass _in_die_venv() beim Import den
    laufenden pytest-Prozess per execv durch die .venv ersetzt.
    """
    import importlib.util
    vorher = os.environ.get("SPARBIT_CLI_REEXEC")
    os.environ["SPARBIT_CLI_REEXEC"] = "1"
    try:
        spec = importlib.util.spec_from_file_location(name, CLI)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return modul
    finally:
        if vorher is None:
            os.environ.pop("SPARBIT_CLI_REEXEC", None)
        else:
            os.environ["SPARBIT_CLI_REEXEC"] = vorher


@pytest.fixture(scope="module")
def cli_modul():
    return lade_cli()


def test_paare_erkennt_typen(cli_modul):
    raus = cli_modul.paare(["port=587", "tls=ja", "stumm=nein", "topic=meins"])
    assert raus == {"port": 587, "tls": True, "stumm": False, "topic": "meins"}


def test_paare_verlangt_gleichheitszeichen(cli_modul):
    with pytest.raises(SystemExit):
        cli_modul.paare(["kaputt"])


def test_paare_laesst_url_heil(cli_modul):
    """Ein '=' im Wert (Query-Parameter) darf nicht zerteilt werden."""
    raus = cli_modul.paare(["url=https://x.de/hook?a=1&b=2"])
    assert raus["url"] == "https://x.de/hook?a=1&b=2"


def test_kuerzen_zeigt_den_rest_an(cli_modul):
    assert cli_modul.kuerze(["a", "b", "c", "d", "e"], "/") == "a/b/c +2"
    assert cli_modul.kuerze(["a", "b"], " oder ") == "a oder b"


def test_beschnitten_markiert(cli_modul):
    assert cli_modul.beschnitten("kurz", 10) == "kurz"
    assert cli_modul.beschnitten("viel zu langer Text", 10).endswith("…")
    assert len(cli_modul.beschnitten("viel zu langer Text", 10)) == 10


def test_wechselt_in_die_venv(monkeypatch, tmp_path):
    """run.py installiert nach ./.venv - die CLI muss dort landen.

    Ohne diesen Sprung scheitert 'python cli.py' auf einem frischen Rechner
    an einem ImportError, obwohl alles laengst installiert ist.
    """
    wurzel = tmp_path / "spar_bit"
    binordner = wurzel / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    binordner.mkdir(parents=True)
    venv_python = binordner / ("python.exe" if os.name == "nt" else "python")
    venv_python.write_text("")

    modul = lade_cli("cli_fuer_venv_test")

    gerufen = []
    monkeypatch.setattr(modul, "ROOT", wurzel)
    monkeypatch.setattr(modul.os, "execv",
                        lambda pfad, argv: gerufen.append((pfad, argv)))
    monkeypatch.delenv("SPARBIT_CLI_REEXEC", raising=False)
    monkeypatch.setattr(modul.sys, "argv", ["cli.py", "status"])

    modul._in_die_venv()

    assert gerufen, "ohne Sprung fehlen der CLI ihre Abhaengigkeiten"
    pfad, argv = gerufen[0]
    assert pfad == str(venv_python)
    assert argv[-1] == "status"


def test_springt_nicht_zweimal(monkeypatch, tmp_path):
    """Sonst startet sich die CLI endlos selbst."""
    modul = lade_cli("cli_kein_zweiter_sprung")

    gerufen = []
    monkeypatch.setenv("SPARBIT_CLI_REEXEC", "1")
    monkeypatch.setattr(modul.os, "execv",
                        lambda pfad, argv: gerufen.append(pfad))
    modul._in_die_venv()
    assert not gerufen


def test_ohne_venv_laeuft_die_cli_trotzdem(monkeypatch, tmp_path):
    """Wer die Abhaengigkeiten global hat, braucht keine .venv."""
    modul = lade_cli("cli_ohne_venv")

    gerufen = []
    monkeypatch.setattr(modul, "ROOT", tmp_path)      # kein .venv darin
    monkeypatch.setattr(modul.os, "execv",
                        lambda pfad, argv: gerufen.append(pfad))
    monkeypatch.delenv("SPARBIT_CLI_REEXEC", raising=False)
    modul._in_die_venv()
    assert not gerufen
