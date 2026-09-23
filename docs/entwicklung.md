# Entwicklung

Aufbau, eigene Quellen, eigene Kanaele, Tests.

## Entwicklung

```bash
python run.py --dev              # Backend mit Auto-Neuladen
cd frontend && npm run dev       # Oberfläche separat, mit Hot-Reload

python -m pytest -q              # 1068 Tests im Backend, ohne Netzwerk
npm --prefix frontend test       # 61 Tests der Oberfläche (Vitest)
npm --prefix frontend run test:e2e   # Durchstich im echten Browser
```

Wer nicht erst Python-Versionen sortieren will: `.devcontainer/` richtet beides
in einem Schritt ein (VS Code Dev Containers oder GitHub Codespaces). Und
`.pre-commit-config.yaml` sagt in zwei Sekunden, was die CI in vier Minuten
sagen würde:

```bash
.venv/bin/pip install pre-commit && .venv/bin/pre-commit install
```

### Eine neue Quelle hinzufügen

Datei anlegen, registrieren, fertig:

```python
# backend/app/sources/meinshop.py
from .base import Category, DealItem, FetchContext, OptionSpec, Source, register

class MeinShop(Source):
    id = "meinshop"
    display_name = "Mein Shop"
    category = Category.COMMUNITY
    default_interval = 900
    options_schema = [OptionSpec("feed_url", "Feed-URL", "string", "https://…")]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        text = await ctx.http.get_text(ctx.opt("feed_url"))
        return [DealItem(titel="…", url="…", quelle=self.id, preis=9.99)]

register(MeinShop())
```

Dann in `backend/app/sources/__init__.py` importieren. Die Quelle erscheint
automatisch im UI — mit Optionsfeldern, Intervall-Regler und Testknopf.

### Einen neuen Kanal hinzufügen

Kanäle sind genauso Plugins. `options_schema` beschreibt die Felder — daraus
baut das UI das Formular und die CLI ihre `--set`-Schlüssel, ganz ohne
zusätzlichen Code:

```python
# backend/app/notify/meinkanal.py
from ..sources.base import OptionSpec
from .base import Channel, Notification, register

class MeinKanal(Channel):
    type = "meinkanal"
    display_name = "Mein Kanal"
    beschreibung = "Wo bekommt man die Zugangsdaten?"
    options_schema = [
        OptionSpec("url", "Server-URL", "string", "", pflicht=True),
        OptionSpec("bilder", "Bild mitschicken", "bool", True),
    ]

    async def send(self, config, note: Notification, http) -> None:
        # note.kopfzeile, note.zeilen(), note.farbe und note.preis_text()
        # liefern die fertige Aufbereitung — auch das Preisurteil.
        resp = await http.post(config["url"], json={
            "text": note.kopfzeile,
            "felder": dict(note.zeilen()),
        })
        if resp.status_code >= 300:          # werfen; der Aufrufer protokolliert
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

register(MeinKanal())
```

In `backend/app/notify/__init__.py` importieren — fertig. Der Kanal steht
danach in der Auswahl im UI, in `python cli.py kanaele typen` und beim
Test-Versand. `pflicht=True` markiert Pflichtfelder; UI und CLI verweigern das
Speichern, solange sie leer sind.

### Aufbau

```
Quellen (Plugins) ─┐                                       Kanäle (Plugins)
Wunschliste ───────┼─► Dedupe ─► SQLite (WAL) ─► Regeln ─► Telegram, Discord,
Erweiterung ───────┘   URL-Hash    Deals,        Keywords,  Slack, Matrix,
  isoliert,          + Zahlen-     Historie,     Preis EUR, Gotify, Pushover,
  Schutzschalter     + Titel-      Angebote,     Rabatt,    ntfy, E-Mail,
  je Quelle            vergleich   Urteile       Urteil     Webhook, Desktop
       │                   │           │             │           ▲
       │            Preisurteil    Lernmodell        │           │
       │            (Verlauf)      (lokal)           │           │
       │                   │                         │           │
       │            Preisfehler ────────────────────────────────►┤
       │            (Indizien)   eigener Meldeweg: ohne Regel,   │
       │                   │     ohne Ruhezeit, sofort           │
       └──── APScheduler ──┴──────── SSE ──► Web-UI ◄────────────┘
                    │                         CLI ◄──────────────┘
```

Backend: Python 3.11+, FastAPI, SQLAlchemy 2, SQLite (WAL), APScheduler, httpx.
Frontend: Vite, React 18, TypeScript, Tailwind. Beim lokalen Start liefert das
Backend die gebaute Oberfläche gleich mit aus — ein Prozess, ein Port.


### Die Oberfläche übersetzen

Zwei Sprachen, ohne Bibliothek — `frontend/src/lib/i18n.ts`. Der Kniff:
**Deutsch ist zugleich Vorgabe und Schlüssel.**

```tsx
const { t } = useSprache();
<Button>{t("Speichern")}</Button>
```

Steht `"Speichern"` nicht im englischen Wörterbuch, erscheint „Speichern" —
nicht `missing.key`. Eine halb fertige Übersetzung soll aussehen wie Deutsch,
nicht wie ein Defekt. Das ist auch der Grund, warum man Seite für Seite
weitermachen kann, ohne dass zwischendurch etwas kaputt ist.

Stand: Navigation, Anmeldung, Feed, Deal-Karten, Preisurteile und die
gemeinsamen Bedienelemente sind übersetzt. Die Einstellungsseiten (Regeln,
Kanäle, Quellen, System) sind es nicht — dort steht viel erklärender
Fließtext, und ein halb übersetzter Absatz ist schlimmer als ein deutscher.

Weitermachen heißt: im Bauteil `useSprache()` holen, die sichtbaren Texte in
`t("…")` einpacken und die englischen Entsprechungen in `EN` nachtragen. Was
dabei **nicht** durch `t()` gehört: Fehlermeldungen vom Backend (die kommen
schon fertig) und Daten aus der Datenbank (Regelnamen, Händler, Deal-Titel).

Zahlen, Daten und Dauern gehen über `formatAmount`, `timeAgo` und
`formatDuration` in `lib/utils.ts` — die lesen die Sprache selbst und brauchen
keinen Hook. Wer `new Intl.…("de-DE")` schreibt, umgeht das; dafür gibt es
dort `intl()`.

### Was die Oberfläche gegen das Backend hält

`api.ts` ist handgeschrieben — 950 Zeilen Typen, die das Backend nicht kennt.
Wird dort ein Feld umbenannt, fällt das sonst erst im Browser auf, und zwar
als `undefined`: also als fehlender Wert, nicht als Fehler.

Nach jeder Änderung an einem API-Körper:

```bash
python backend/tools/openapi_export.py frontend/openapi.json
npm --prefix frontend run api:types
```

Das erzeugt `src/lib/api-typen.ts` (eingecheckt), `api-vertrag.ts` behauptet
auf Typ-Ebene, dass der handgeschriebene Client dazu passt, und `tsc` prüft
das mit. Die CI erzeugt beides neu und vergleicht — weicht etwas ab, ist die
Antwort ein roter Lauf statt eines leeren Feldes.

### Der Scheduler als eigener Dienst

Normalerweise nicht nötig: SparBit ist ein Prozess. Wenn das Einsammeln die
Oberfläche träge macht, geht auch getrennt:

```bash
# .env
SPARBIT_SCHEDULER=aus            # gilt für den API-Prozess

docker compose --profile worker up -d
# oder ohne Docker:
cd backend && python -m app.worker
```

**Genau einer.** Zwei Worker auf derselben Datenbank fragen jede Quelle
doppelt ab und verschicken jede Meldung zweimal; eine Sperre dagegen wäre ein
verteiltes Schloss für einen Fall, den es in einem Haushalt nicht gibt.

Der Live-Ticker läuft weiter: der Worker spiegelt seine Ereignisse in die
Tabelle `event_log`, der API-Prozess liest alle zwei Sekunden nach — aber nur,
solange jemand zusieht. Der Telegram-Bot läuft dann im Worker, nicht im
API-Prozess: Long Polling ist eine Dauerverbindung, und zwei davon würden sich
die Nachrichten gegenseitig wegnehmen.

## Eigene Quellen ohne Fork

Eine Quelle, die nur dich interessiert, braucht keinen Fork. Setze
`SPARBIT_PLUGIN_DIR` auf einen Ordner; jede `.py`-Datei darin wird beim Start
geladen:

```python
# /data/plugins/meinshop.py
from app.sources import Category, DealItem, Source, Verification, register


class MeinShop(Source):
    id = "meinshop"
    display_name = "Mein Shop"
    category = Category.EXPERIMENTAL
    verification = Verification.UNVERIFIED

    async def fetch(self, ctx):
        daten = await ctx.http.get_json("https://meinshop.de/api/deals")
        return [DealItem(titel=d["name"], url=d["url"], quelle=self.id,
                         preis=d["price"]) for d in daten]


register(MeinShop())
```

Was dort liegt, läuft mit allen Rechten des Prozesses — das ist kein
Versehen, sondern die ehrliche Variante. Ein Plugin mit Tippfehler wird
gemeldet und übersprungen, statt den Start zu verhindern.

Für einfache JSON-Endpunkte braucht es gar kein Modul: die mitgelieferte
Quelle **Eigene JSON-Schnittstelle** nimmt Adresse und Feldnamen entgegen
(`data.items`, `price.current`) und macht daraus Deals.

## Datenbank ändern

`backend/app/migrations.py` hält nummerierte Schritte. Neuer Schritt ans
Ende, Nummer nie wiederverwenden, bestehende Schritte nie ändern:

```python
def _schritt_009(conn: Connection) -> None:
    """Was dieser Schritt tut und warum."""
    spalte_ergaenzen(conn, "deals", "neue_spalte", "VARCHAR(64)")
    # Daten nachtragen ist ausdrücklich erlaubt - genau dafür gibt es
    # nummerierte Schritte statt einer Spaltenliste.
```

Eine neue Datenbank wird **gestempelt** statt migriert: `create_all` hat den
Stand schon gebaut. Eine vorgefundene arbeitet die offenen Schritte ab, jeder
in eigener Transaktion.

Der Schema-Stand steht unter *Logs & System* und in `/api/system/info`.

## Was die CI prüft

Bei jedem Push:

| Lauf | Was er sagt |
|---|---|
| `ruff check` | Linter, ohne Formatierungsstreit |
| Testsuite auf 3.11/3.12/3.13 | mit Gesamtschwelle (78 %) |
| **Abdeckung der geänderten Zeilen** | nur bei PRs, 80 %. Die Gesamtschwelle trägt den Bestand und sagt nichts darüber, ob *neuer* Code getestet ist — ein ungetestetes Modul fällt in einer großen Codebasis nicht auf |
| `eslint`, `tsc`, Vitest, Build | die Oberfläche |
| **Oberfläche gegen OpenAPI** | erzeugt die API-Typen neu und vergleicht sie mit den eingecheckten |
| **Durchstich im Browser** | Playwright gegen ein echtes Backend |
| **CodeQL** | statische Analyse, wöchentlich auch ohne neuen Code |
| `pip-audit`, `npm audit` | bekannte Lücken in Abhängigkeiten — als Warnung, nicht blockierend: ein Fund ohne verfügbares Update soll sichtbar sein, aber nicht alle offenen PRs rot färben |
| Docker-Images, `docker compose config` | auch der HTTPS-Pfad mit Caddy |

Bei einem Push auf den **Standard-Branch** und bei einem Tag `v*` baut ein
zweiter Workflow beide Images für `amd64` und `arm64`, signiert sie
schlüssellos über sigstore und lädt sie nach `ghcr.io` — unter anderem mit
den Marken `latest` und `sha-<commit>`. Genau die zweite zieht der
Auto-Updater auf dem VPS: das Image zum ausgecheckten Commit, und wenn es
keines gibt (eigener Fork), baut er wie zuvor selbst.

Der Branch steht dabei **nicht** im Workflow. Er wird zur Laufzeit gegen
`github.event.repository.default_branch` geprüft. Ein fest eingetragenes
`main` wäre in diesem Repository still wirkungslos gewesen — der
Standard-Branch heißt anders, und ein Workflow, der nie läuft, meldet sich
nicht: kein roter Lauf, keine Fehlermeldung, nur keine Images.

Bei einem Tag baut ein dritter Workflow außerdem die Oberfläche und hängt sie
als `frontend-dist.tar.gz` samt Prüfsumme, Stückliste und Herkunftsnachweis
ans Release — das Archiv, das `run.py` holt, wenn kein Node installiert ist.

## Überwachung

`/api/health` prüft Datenbank, Scheduler und Quellen und antwortet mit 503,
wenn etwas wirklich kaputt ist (ein Mangel bleibt 200 — sonst startet ein
Orchestrator den Dienst neu, obwohl er arbeitet). `/api/metrics` liefert das
Prometheus-Textformat; es braucht eine Anmeldung oder ein API-Token, das
Prometheus per `bearer_token_file` mitschicken kann.

---

[← Zurück zur Übersicht](../README.md)
