# SparBit

Selbstgehostete Deal- und Freebie-Zentrale: sammelt Gratis-Sachen, Preisfehler
und extreme Rabatte aus vielen Quellen, filtert sie nach deinen Regeln und
schickt dir die Treffer sofort per Telegram. Konfiguriert wird alles im
Web-UI — im Alltag musst du keine Datei mehr anfassen.

![Lizenz](https://img.shields.io/badge/Lizenz-MIT-blue) ![Python](https://img.shields.io/badge/Python-3.12-3776ab) ![React](https://img.shields.io/badge/React-18-61dafb)

> **Vor dem ersten Start bitte [ENDPOINTS.md](ENDPOINTS.md) lesen.**
> Kein Quellen-Endpoint konnte beim Bauen live geprüft werden (die
> Build-Umgebung hatte keinen Netzzugang zu den Deal-Seiten). Alle Quellen
> starten als *ungeprüft*; ein Befehl bzw. ein Knopf im UI verifiziert sie auf
> deinem Server. Das ist Absicht — lieber ehrlich ungeprüft als falsch
> „funktioniert".

## Was drin ist

* **14 Quellen** als Plugins — Deal-Communities (mydealz, Preisjäger,
  HotUKDeals, Dealabs), Blogs (Sparhamster, Schnäppchenfuchs), Reddit, Epic,
  GOG, Steam, CheapShark, IsThereAnyDeal, GG.deals, plus beliebige eigene Feeds.
* **Regel-Editor mit Live-Vorschau** — beim Bauen einer Regel siehst du sofort,
  wie viele der letzten 500 Deals sie getroffen hätte, mit Beispielen *und* mit
  „knapp verfehlt", damit du Rauschen wegtunen kannst, ohne zu raten.
* **Dedupe über Quellen hinweg** — derselbe Deal aus vier Communities kommt
  einmal an. Produktvarianten („Hades" vs. „Hades II", „990 Pro" vs.
  „990 Evo") bleiben getrennt.
* **Benachrichtigungen** — Telegram (mit Bild, Preis, Direktlink und
  Inline-Buttons), E-Mail, Discord/Webhook, ntfy. Ruhezeiten mit Override für
  SOFORT-Regeln.
* **Auto-Claimer** — Epic, Prime Gaming und GOG holen ihre Gratis-Titel selbst;
  Status und geclaimte Spiele im UI.
* **Isolierte Quellen** — fällt eine aus, laufen die anderen weiter. Circuit
  Breaker nach 5 Fehlern, Status als Ampel im UI.

## Setup in unter 15 Minuten

### Voraussetzungen

Ubuntu-VPS mit Docker und Docker Compose. 16 GB RAM sind reichlich — SparBit
selbst braucht unter 1 GB, der Claimer bis zu 2 GB (er startet einen Browser).

### 1. Holen und konfigurieren (2 Min.)

```bash
git clone https://github.com/StrikerLUL/spar_bit.git
cd spar_bit
cp .env.example .env
nano .env
```

Fürs Erste reicht es, `TZ` zu prüfen und `SPARBIT_WEB_PORT` zu setzen.
Alles andere kann leer bleiben — Telegram und API-Keys trägst du später
bequem im Web-UI ein.

### 2. Starten (3–5 Min., meist Build-Zeit)

```bash
docker compose up -d --build
docker compose ps          # alle Dienste "healthy"?
```

Nur SparBit ohne Auto-Claimer:

```bash
docker compose up -d --build backend frontend
```

### 3. Konto anlegen (1 Min.)

`http://<server-ip>:8080` öffnen. Beim ersten Aufruf erscheint der
Setup-Assistent. **Es gibt kein Standard-Passwort** — was du hier setzt, gilt
(mindestens 10 Zeichen, gehasht mit argon2).

### 4. Quellen prüfen und einschalten (3 Min.)

Unter **Quellen** bei jeder interessanten Quelle **„Jetzt testen"** drücken.
Der Test ruft den echten Endpoint auf und zeigt dir die ersten Treffer.

* grün → einschalten
* rot → Fehlermeldung lesen; meist reicht es, unter *Einstellungen* eine URL
  zu korrigieren

Alles auf einmal prüfen:

```bash
docker compose exec backend python -m tools.verify_endpoints
```

Empfehlung für den Anfang: **mydealz**, **Reddit** und **Epic**. Die decken
zusammen schon sehr viel ab.

### 5. Telegram einrichten (3 Min.)

1. In Telegram **@BotFather** anschreiben, `/newbot` senden.
2. Namen und Benutzernamen vergeben (der muss auf `bot` enden).
   BotFather antwortet mit dem **Token** — sieht aus wie
   `123456789:AAE...`.
3. **@userinfobot** anschreiben, der nennt dir deine numerische **Chat-ID**.
4. **Deinem eigenen Bot einmal `/start` senden.** Ohne das darf er dir nicht
   schreiben — das ist der häufigste Stolperstein.
5. Im UI unter *Benachrichtigungen* → **Telegram** → Token und Chat-ID
   eintragen → speichern → **Test senden**.

### 6. Erste Regel (1 Min.)

Unter **Regeln** → „Erste Regel anlegen":

* Name: `Alles Gratis`
* *Nur gratis* an
* Priorität **SOFORT**
* Kanal: dein Telegram

Rechts siehst du sofort, wie viele der bisher gesammelten Deals die Regel
getroffen hätte. Speichern — fertig.

## Wo du API-Keys herbekommst

Beide sind optional; ohne sie bleiben nur diese zwei Quellen aus.

| Dienst | Wo | Kosten |
|---|---|---|
| IsThereAnyDeal | <https://isthereanydeal.com/apps/my/> — App registrieren | kostenlos |
| GG.deals | <https://gg.deals/de/api/> — Zugang beantragen | für private Nutzung kostenlos |

Eintragen im UI unter *Quellen → (Quelle) → Einstellungen → API-Key*. Die
Keys landen in der Datenbank, nicht in einer Datei, und werden bei jeder
Rückgabe maskiert.

## Auto-Claimer

Der Claimer ist [vogler/free-games-claimer](https://github.com/vogler/free-games-claimer)
als eigener Container. Er holt automatisch die Gratis-Spiele von Epic, Prime
Gaming und GOG.

**Zugangsdaten** in die `.env` (`EG_EMAIL`, `PG_EMAIL`, … — siehe
`.env.example`). Der Zeitplan steht in `CLAIMER_SCHEDULE`, Vorgabe ist täglich
4 Uhr.

**Erste Anmeldung.** Wegen 2FA und Captchas musst du dich einmal interaktiv
anmelden. Der Container bringt dafür einen VNC-Zugang mit, der bewusst nur an
`127.0.0.1` gebunden ist:

```bash
# SSH-Tunnel von deinem Rechner aus
ssh -L 5900:127.0.0.1:5900 -L 6080:127.0.0.1:6080 user@dein-server
```

Dann im Browser `http://localhost:6080` öffnen (oder einen VNC-Client auf
`localhost:5900`) und die Anmeldung durchklicken. Die Session liegt im Volume
`claimer-data` und überlebt Neustarts.

Manuell laufen lassen:

```bash
docker compose run --rm claimer
```

Status, geclaimte Titel und das Rohlog stehen im UI unter **Claimer**. SparBit
liest die Logdateien des Claimers nur — es schreibt dort nichts hinein.

**Falls das Image Probleme macht**, ist
[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)
der Fallback (nur Epic). In `docker-compose.yml` den `claimer`-Dienst ersetzen
und weiter ins Volume `claimer-data` schreiben lassen — das Log-Parsing kommt
mit beiden Formaten zurecht und zeigt im Zweifel das Rohlog.

## Betrieb hinter einem Reverse-Proxy

SparBit macht selbst kein TLS. Für den Betrieb hinter Caddy oder Traefik in
`docker-compose.yml` beim `frontend` die Portfreigabe entfernen (oder auf
`127.0.0.1:8080:80` ändern) und den Proxy davorhängen.

**Caddy** (`Caddyfile`):

```caddy
deals.example.com {
    reverse_proxy localhost:8080 {
        # Der Live-Ticker ist ein SSE-Stream und darf nicht gepuffert werden.
        flush_interval -1
    }
}
```

**Traefik** (Labels am `frontend`-Dienst):

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.sparbit.rule=Host(`deals.example.com`)"
  - "traefik.http.routers.sparbit.entrypoints=websecure"
  - "traefik.http.routers.sparbit.tls.certresolver=le"
  - "traefik.http.services.sparbit.loadbalancer.server.port=80"
```

Zwei Dinge sind wichtig:

* **Kein Puffern auf `/api/events`** — sonst kommt der Live-Ticker nie an. Das
  mitgelieferte nginx ist schon richtig eingestellt; der äußere Proxy muss
  mitspielen (bei Caddy `flush_interval -1`).
* **HTTPS verwenden.** Das Session-Cookie wird bei HTTPS automatisch mit
  `Secure` gesetzt.

## Entwicklung

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
SPARBIT_DATA_DIR=./data uvicorn app.main:app --reload

# Frontend (proxyt /api automatisch auf :8000)
cd frontend
npm install
npm run dev
```

Tests laufen ohne Netzwerk gegen gespeicherte Fixtures:

```bash
cd backend
pytest tests/ -q          # 93 Tests
```

### Eine neue Quelle hinzufügen

Zwei Schritte, mehr nicht:

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
automatisch im UI, inklusive Optionsfeldern, Intervall-Regler und Testknopf —
`health_check()` erbst du.

## Architektur

```
Quellen (Plugins)  ──►  Dedupe  ──►  SQLite (WAL)  ──►  Regel-Engine  ──►  Kanäle
   isoliert,             URL-Hash        Deals,           Keywords,        Telegram
   Circuit Breaker    + Fuzzy-Titel      Regeln,          Preis, Rabatt,   E-Mail
   pro Quelle                            Treffer          Quelle, Temp.    Discord, ntfy
        │                                     │                                 │
        └──────────── APScheduler ────────────┴────── SSE ──► Web-UI ◄──────────┘
```

* **Backend** — Python 3.12, FastAPI, SQLAlchemy 2, SQLite im WAL-Modus,
  APScheduler, httpx.
* **Frontend** — Vite, React 18, TypeScript, Tailwind, Dark Mode als Vorgabe.
* **Deployment** — docker-compose mit Healthchecks, Speicherlimits und
  `restart: unless-stopped`.

## Sicherheit und Datenschutz

* Alle Secrets in `.env` bzw. in der Datenbank, nichts im Repository. `.env`
  steht in `.gitignore`.
* Passwort mit **argon2** gehasht, kein Standard-Passwort im Code.
* Session-Cookie signiert, `HttpOnly`, `SameSite=Lax`, `Secure` bei HTTPS.
* Container laufen als unprivilegierter Benutzer, der Claimer-Mount ist
  schreibgeschützt.
* **Der Backup-Export enthält deine API-Keys und Telegram-Token im Klartext.**
  Behandle die Datei wie ein Passwort.

## Höfliches Crawling

Fremde Server kosten fremdes Geld — SparBit verhält sich entsprechend:

* Eigener, sprechender User-Agent (in `.env` anpassbar).
* Mindestabstand zwischen zwei Anfragen an denselben Host (Vorgabe 1 s).
* ETag und Last-Modified werden mitgeführt; 304 spart die Übertragung.
* Exponentieller Backoff mit Jitter bei 429 und 5xx, `Retry-After` wird
  respektiert.
* Pro Quelle ein Mindestintervall, das im UI nicht unterschritten werden kann.

Bitte dreh die Intervalle nicht ohne Grund runter. Eine Quelle, die dich
sperrt, nützt dir nichts.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
