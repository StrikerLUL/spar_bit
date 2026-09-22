# Werkzeuge

Skripte, die nicht im Betrieb laufen, sondern bei der Arbeit am Projekt.

| Datei | Wofür |
|---|---|
| `verify_endpoints.py` | Quellen gegen die echten Endpunkte prüfen und Fixtures aufzeichnen |
| `demodaten.py` | Eine Installation mit glaubwürdigen Beispieldaten füllen |
| `screenshots.py` | Die Bilder in `docs/bilder/` neu aufnehmen |

## Screenshots erneuern

Nach einer Änderung an der Oberfläche:

```bash
# 1. Demo-Installation anlegen (gibt den Datenordner aus)
.venv/bin/python backend/tools/demodaten.py

# 2. Damit starten
cd backend && SPARBIT_DATA_DIR=<ordner> SPARBIT_TELEGRAM_POLLING=false \
  ../.venv/bin/python -m uvicorn app.main:app --port 8811

# 3. Aufnehmen (braucht playwright)
.venv/bin/python backend/tools/screenshots.py
```

Die Bilder werden anschließend auf einfache Auflösung verkleinert — 2x sieht
im Browser gleich aus, kostet im Repository aber das Doppelte.

Die Demo-Daten sind ausgedacht, aber nicht zufällig: echte Produktnamen,
plausible Preise und ein Preisfehler, der wie einer aussieht. Ein Screenshot
mit `Testartikel 1` erklärt niemandem, was das Programm tut.
