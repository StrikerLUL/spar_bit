# Mitarbeiten

SparBit ist eine selbstgehostete Anwendung für einen Haushalt, keine
Bibliothek für tausend Projekte. Das prägt, was hier zählt.

## Was diesem Projekt wichtig ist

**Ehrlichkeit vor Politur.** Eine Quelle, die als *ungeprüft* dasteht, ist
besser als eine, die „funktioniert" behauptet. Ein Preiswächter, der sagt
„kann ich nicht lesen", ist besser als einer, der still den falschen Wert
nimmt. Wo etwas geraten wird, muss es dranstehen.

**Der Grund gehört in den Code.** Kommentare beantworten *warum*, nicht
*was*. Die interessanten Stellen hier sind alle so entstanden: weil
irgendwo etwas schiefging, und die nächste Person soll nicht denselben Weg
noch einmal gehen.

**Deutsch im Code.** Modulnamen, Funktionsnamen, Kommentare, Meldungen. Das
ist Absicht: die Oberfläche ist deutsch, und ein Wechsel zwischen
`schwellen_vorschlag` und `threshold_suggestion` in derselben Datei macht
niemandem das Lesen leichter.

## Bevor du einen Pull Request aufmachst

```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/pip install ruff pytest-cov

.venv/bin/ruff check .          # Linter
.venv/bin/python -m pytest -q   # Tests (dauert ~2 Minuten)

cd frontend && npm ci && npm run lint && npm run typecheck && npm run build
```

Dasselbe läuft in der CI, auf Python 3.11 bis 3.13.

**Nicht benutzt wird `ruff format`.** Der Code ist von Hand gesetzt — Tabellen
in Dicts, ausgerichtete Kommentare, bewusste Zeilenumbrüche. Eine
automatische Formatierung würde das einebnen.

## Tests

Jede Änderung am Verhalten braucht einen Test, und der Testname sagt, worum
es geht — nicht `test_parse_3`, sondern
`test_lieber_kein_datum_als_ein_falsches`. Die Docstrings der Testdateien
erklären, welcher Fehler hier in Zukunft verhindert wird.

Besonders wichtig bei:

* **Preis-Parsing** — jeder Fall, der einmal falsch lag, bleibt als Test da.
* **Sicherheitsgrenzen** — SSRF-Schutz, Besitzverhältnisse zwischen Konten,
  Entpacken von Archiven. Diese Tests beschreiben Angriffe, keine Features.
* **Migrationen** — eine alte Datenbank muss nach dem Update funktionieren,
  und das lässt sich nur mit einer alten Datenbank prüfen.

## Eine neue Quelle

Der Weg steht in [docs/entwicklung.md](docs/entwicklung.md). Drei Regeln:

1. **Strukturierte Daten vor CSS-Selektoren.** JSON-Endpunkte, RSS,
   schema.org. Ein Selektor hält bis zum nächsten Redesign.
2. **Die Quelle startet als `UNVERIFIED`.** Nichts hier behauptet, geprüft
   zu sein, bevor es jemand auf einem echten Rechner geprüft hat.
3. **Fehler werfen ist richtig.** Der Runner fängt sie isoliert ab; eine
   Quelle, die einen Fehler verschluckt und `[]` zurückgibt, sieht aus wie
   „heute nichts dabei".

Geht es nur um deine eigene Seite? Dann brauchst du keinen Fork: ein Modul
in `SPARBIT_PLUGIN_DIR` wird beim Start geladen (siehe
[docs/entwicklung.md](docs/entwicklung.md)).

## Datenbank ändern

Neue Spalte, neuer Index, Daten nachtragen: ein nummerierter Schritt in
`backend/app/migrations.py`, ans Ende der Liste. Nummern werden nie
wiederverwendet und bestehende Schritte nie nachträglich geändert — draußen
sind sie längst gelaufen.

Ein Schritt darf nie voraussetzen, dass eine Spalte existiert, nur weil das
Modell sie kennt: eine Datenbank von vor drei Releases sieht anders aus.
`spalte_existiert()` beantwortet das.

## Commits

Die Überschrift sagt, was sich für den Benutzer ändert, nicht welche Datei
angefasst wurde. Der Text darunter erklärt das Problem, das dahinter stand —
so lässt sich später nachvollziehen, warum etwas so ist, wie es ist.

## Sicherheitslücken

Nicht als Issue. Siehe [SECURITY.md](SECURITY.md).
