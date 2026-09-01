#!/usr/bin/env python3
"""SparBit auf dem eigenen Rechner starten.

    python run.py

Das Skript kuemmert sich um alles: virtuelle Umgebung anlegen, Abhaengigkeiten
installieren, Weboberflaeche bauen (falls Node da ist), Server starten und den
Browser oeffnen. Kein Docker, kein Server, kein nginx.

Nuetzliche Schalter:
    --port 9000        anderen Port verwenden
    --host 0.0.0.0     auch von anderen Geraeten im Heimnetz erreichbar
    --no-browser       Browser nicht automatisch oeffnen
    --rebuild          Weboberflaeche neu bauen, auch wenn sie schon da ist
    --skip-install     Abhaengigkeiten nicht pruefen (schnellerer Start)
    --dev              Entwicklungsmodus mit automatischem Neuladen
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
MIN_PYTHON = (3, 11)

IS_WINDOWS = platform.system() == "Windows"
BIN = "Scripts" if IS_WINDOWS else "bin"
VENV_PYTHON = VENV / BIN / ("python.exe" if IS_WINDOWS else "python")

# Farbe nur, wenn das Terminal sie auch darstellt.
_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

def info(msg: str) -> None:    print(f"  {msg}")
def step(msg: str) -> None:    print(_c(f"\n▸ {msg}", "1;36"))
def ok(msg: str) -> None:      print(f"  {_c('✓', '32')} {msg}")
def warn(msg: str) -> None:    print(f"  {_c('!', '33')} {msg}")
def fail(msg: str) -> None:    print(f"  {_c('✗', '31')} {msg}")


def die(msg: str, hint: str = "") -> "NoReturn":  # type: ignore[valid-type]
    fail(msg)
    if hint:
        print(f"\n    {hint}\n")
    sys.exit(1)


def run(cmd: list[str], cwd: Path | None = None, quiet: bool = True) -> bool:
    """Befehl ausfuehren. Bei Fehler wird die Ausgabe gezeigt, sonst nicht."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE if quiet else None,
            stderr=subprocess.STDOUT if quiet else None,
            text=True,
        )
    except FileNotFoundError:
        return False
    if result.returncode != 0 and quiet and result.stdout:
        print(result.stdout[-2500:])
    return result.returncode == 0


def have(program: str) -> str | None:
    return shutil.which(program)


# --- Schritte --------------------------------------------------------------

def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        die(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ noetig, "
            f"gefunden {sys.version.split()[0]}.",
            "Aktuelle Version holen: https://www.python.org/downloads/")


def ensure_venv() -> Path:
    """Virtuelle Umgebung anlegen, damit nichts ins System-Python wandert."""
    if VENV_PYTHON.exists():
        return VENV_PYTHON
    step("Virtuelle Umgebung anlegen (einmalig)")
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
    except Exception as exc:
        die(f"Konnte .venv nicht anlegen: {exc}",
            "Unter Debian/Ubuntu fehlt oft das Paket python3-venv:\n"
            "    sudo apt install python3-venv")
    if not VENV_PYTHON.exists():
        die("Virtuelle Umgebung wurde angelegt, aber kein Python darin gefunden.")
    ok(f"{VENV.relative_to(ROOT)} erstellt")
    return VENV_PYTHON


def marker_current(marker: Path, source: Path) -> bool:
    return marker.exists() and source.exists() and \
        marker.stat().st_mtime >= source.stat().st_mtime


def install_deps(python: Path, force: bool = False) -> None:
    req = BACKEND / "requirements.txt"
    marker = VENV / ".sparbit-deps"
    if not force and marker_current(marker, req):
        return
    step("Python-Abhaengigkeiten installieren")
    info("Das dauert beim ersten Mal ein bis zwei Minuten.")
    if not run([str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"]):
        warn("pip konnte nicht aktualisiert werden - weiter mit der vorhandenen Version.")
    if not run([str(python), "-m", "pip", "install", "-r", str(req), "--quiet"],
               quiet=True):
        die("Installation der Abhaengigkeiten fehlgeschlagen.",
            "Siehe Ausgabe oben. Haeufigste Ursache: keine Internetverbindung.")
    marker.write_text("ok")
    ok("Abhaengigkeiten installiert")


def build_frontend(force: bool = False) -> bool:
    """Weboberflaeche bauen. Liefert True, wenn danach ein dist/ existiert."""
    dist_index = FRONTEND / "dist" / "index.html"
    if dist_index.exists() and not force:
        return True

    npm = have("npm")
    if not npm:
        if dist_index.exists():
            return True
        warn("Node.js/npm nicht gefunden - die Weboberflaeche kann nicht gebaut werden.")
        info("Node holen: https://nodejs.org  (LTS reicht)")
        info("Danach nochmal 'python run.py' starten.")
        return False

    step("Weboberflaeche bauen")
    if not (FRONTEND / "node_modules").is_dir() or force:
        info("npm-Pakete installieren (einmalig, ~1 Minute) ...")
        if not run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND):
            fail("npm install fehlgeschlagen.")
            return False
    info("Bauen ...")
    if not run([npm, "run", "build"], cwd=FRONTEND):
        fail("Build fehlgeschlagen.")
        return False
    ok("Weboberflaeche gebaut")
    return True


def open_browser_later(url: str, delay: float = 2.0) -> None:
    def worker() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


def banner(url: str, dev: bool) -> None:
    print()
    print(_c("  ╭─────────────────────────────────────────────╮", "36"))
    print(_c("  │", "36") + "   " + _c("SparBit", "1;32") +
          " — Deal- & Freebie-Zentrale       " + _c("│", "36"))
    print(_c("  ╰─────────────────────────────────────────────╯", "36"))
    print()
    print(f"   Oberflaeche:  {_c(url, '1;36')}")
    if dev:
        print(f"   Modus:        Entwicklung (laedt bei Aenderungen neu)")
    print(f"   Beenden mit:  {_c('Strg+C', '1')}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SparBit lokal starten",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1",
                        help="0.0.0.0 macht SparBit im Heimnetz erreichbar")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()

    check_python()
    python = ensure_venv()
    if not args.skip_install:
        install_deps(python, force=args.rebuild)

    have_ui = build_frontend(force=args.rebuild)
    if not have_ui:
        warn("SparBit startet trotzdem - die API laeuft, nur die Oberflaeche fehlt.")

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env.setdefault("SPARBIT_DATA_DIR", str(data_dir))
    env.setdefault("SPARBIT_HOST", args.host)
    env.setdefault("SPARBIT_PORT", str(args.port))
    env.setdefault("PYTHONUNBUFFERED", "1")

    anzeige_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    url = f"http://{anzeige_host}:{args.port}"

    cmd = [str(python), "-m", "uvicorn", "app.main:app",
           "--host", args.host, "--port", str(args.port)]
    if args.dev:
        cmd += ["--reload", "--reload-dir", str(BACKEND / "app")]

    banner(url, args.dev)
    if not args.no_browser:
        open_browser_later(url)

    try:
        return subprocess.call(cmd, cwd=BACKEND, env=env)
    except KeyboardInterrupt:
        print("\n  SparBit beendet. Deine Daten liegen in ./data\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
