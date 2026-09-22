"""Eigene Quellen und Kanaele, ohne SparBit zu forken.

Eine neue Quelle brauchte bisher eine Datei im Repository und einen
Eintrag in sources/__init__.py. Fuer den, der eine Seite beobachten
will, die sonst niemanden interessiert, heisst das: Fork pflegen,
bei jedem Update nachziehen - oder es bleiben lassen.

Jede .py-Datei im Plugin-Ordner wird beim Start geladen. Darin steht
dasselbe wie in einer mitgelieferten Quelle:

    from app.sources import Source, DealItem, register

    class MeinShop(Source):
        id = "meinshop"
        ...

    register(MeinShop())

Bewusst ohne Absicherung: was in dem Ordner liegt, laeuft mit allen
Rechten des Prozesses. Das ist kein Versehen - es ist der eigene
Rechner und der eigene Ordner, und eine halbe Sandkiste waere ein
Versprechen, das sie nicht halten kann. Wer den Pfad nicht setzt, laedt
nichts.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)

geladen: list[str] = []
fehler: dict[str, str] = {}


def ordner() -> Path | None:
    return Path(settings.plugin_dir) if settings.plugin_dir else None


def lade() -> list[str]:
    """Alle Plugin-Dateien importieren. Gibt die Namen zurueck, die liefen."""
    geladen.clear()
    fehler.clear()

    ziel = ordner()
    if ziel is None:
        return []
    if not ziel.is_dir():
        log.warning("Plugin-Ordner %s gibt es nicht - nichts geladen", ziel)
        return []

    for datei in sorted(ziel.glob("*.py")):
        if datei.name.startswith("_"):
            continue
        name = f"sparbit_plugin_{datei.stem}"
        try:
            spec = importlib.util.spec_from_file_location(name, datei)
            if spec is None or spec.loader is None:
                raise ImportError("Datei laesst sich nicht als Modul lesen")
            modul = importlib.util.module_from_spec(spec)
            sys.modules[name] = modul
            spec.loader.exec_module(modul)
        except Exception as exc:
            # Ein kaputtes Plugin darf den Start nicht verhindern - sonst
            # steht nach einem Tippfehler die ganze Installation.
            fehler[datei.name] = f"{type(exc).__name__}: {exc}"
            sys.modules.pop(name, None)
            log.error("Plugin %s nicht geladen: %s", datei.name, exc)
            continue
        geladen.append(datei.name)
        log.info("Plugin %s geladen", datei.name)
    return list(geladen)


def stand() -> dict:
    return {
        "ordner": str(ordner()) if ordner() else None,
        "geladen": list(geladen),
        "fehler": dict(fehler),
    }
