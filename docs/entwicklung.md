# Entwicklung

Aufbau, eigene Quellen, eigene Kanaele, Tests.

## Entwicklung

```bash
python run.py --dev              # Backend mit Auto-Neuladen
cd frontend && npm run dev       # Oberfläche separat, mit Hot-Reload
cd backend && pytest tests/ -q   # 622 Tests, ohne Netzwerk
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

Bei jedem Push: `ruff check`, die Testsuite auf Python 3.11/3.12/3.13 mit
Abdeckungsschwelle, `eslint`, `tsc`, der Frontend-Build, beide Docker-Images
und ein Probelauf von `docker compose config`.

Bei einem Tag `v*` baut ein zweiter Workflow die Oberfläche und hängt sie als
`frontend-dist.tar.gz` samt Prüfsumme ans Release — das Archiv, das `run.py`
holt, wenn kein Node installiert ist.

## Überwachung

`/api/health` prüft Datenbank, Scheduler und Quellen und antwortet mit 503,
wenn etwas wirklich kaputt ist (ein Mangel bleibt 200 — sonst startet ein
Orchestrator den Dienst neu, obwohl er arbeitet). `/api/metrics` liefert das
Prometheus-Textformat; es braucht eine Anmeldung oder ein API-Token, das
Prometheus per `bearer_token_file` mitschicken kann.

---

[← Zurück zur Übersicht](../README.md)
