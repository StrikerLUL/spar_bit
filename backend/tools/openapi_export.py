"""Das OpenAPI-Schema in eine Datei schreiben - ohne den Server zu starten.

Der API-Client der Oberflaeche war lange handgeschrieben: 950 Zeilen
Typen, die niemand mit dem Backend abgeglichen hat. Wird dort ein Feld
umbenannt, faellt das erst im Browser auf, und zwar als `undefined` -
also als fehlender Wert, nicht als Fehler.

Dieses Skript schreibt das Schema, `openapi-typescript` macht Typen
daraus, und die CI vergleicht sie mit den eingecheckten. Weicht etwas
ab, ist die Antwort ein roter Lauf statt eines leeren Felds.

    python backend/tools/openapi_export.py frontend/openapi.json
    npm --prefix frontend run api:types

Die erzeugten Typen ersetzen den handgeschriebenen Client nicht - sie
stehen daneben (`api-typen.ts`) und sind die Wahrheit, an der er
gemessen wird. Ein Umbau in einem Rutsch waere ein Risiko ohne
sichtbaren Gewinn; Schritt fuer Schritt umzuziehen geht so auch.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WURZEL / "backend"))


def schema() -> dict:
    # In ein Wegwerf-Verzeichnis, damit der Import keine echte Datenbank
    # anlegt - das Schema haengt nicht an den Daten.
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.setdefault("SPARBIT_DATA_DIR", tmp)
        os.environ.setdefault("SPARBIT_LOG_LEVEL", "ERROR")
        from app.main import app

        return app.openapi()


def main() -> int:
    ziel = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/openapi.json")
    if not ziel.is_absolute():
        ziel = WURZEL / ziel
    ziel.parent.mkdir(parents=True, exist_ok=True)

    # sort_keys, damit der Vergleich in der CI nicht an der Reihenfolge
    # haengt, die FastAPI je nach Import-Reihenfolge anders waehlt.
    ziel.write_text(
        json.dumps(schema(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"Schema geschrieben: {ziel.relative_to(WURZEL)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
