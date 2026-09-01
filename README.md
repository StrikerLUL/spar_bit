# SparBit

Deal- und Freebie-Zentrale für zu Hause: sammelt Gratis-Sachen, Preisfehler und
starke Rabatte aus vielen Quellen, filtert sie nach deinen Regeln und meldet
Treffer sofort — per Telegram und als Desktop-Meldung. Konfiguriert wird alles
im Web-Interface.

**Läuft auf deinem eigenen Rechner.** Kein Server, kein Docker, keine
Konfigurationsdateien. Ein Befehl genügt.

![Lizenz](https://img.shields.io/badge/Lizenz-MIT-blue) ![Python](https://img.shields.io/badge/Python-3.11+-3776ab) ![React](https://img.shields.io/badge/React-18-61dafb)

---

## Loslegen

Du brauchst nur **Python 3.11 oder neuer**. Node.js ist optional (wird nur
gebraucht, wenn du die Oberfläche selbst neu bauen willst).

```bash
git clone https://github.com/StrikerLUL/spar_bit.git
cd spar_bit
python run.py
```

Das war's. Beim ersten Mal legt SparBit eine virtuelle Umgebung an, installiert
die Abhängigkeiten, baut die Oberfläche und startet — danach öffnet sich
automatisch <http://localhost:8000>. Dauert etwa eine Minute; jeder weitere
Start ein paar Sekunden.

**Windows:** `start.bat` doppelklicken.
**macOS/Linux:** `./start.sh` oder `python3 run.py`.

Beim ersten Aufruf legst du dein Konto an. Es gibt **kein Standard-Passwort** —
was du setzt, gilt (mindestens 10 Zeichen, mit argon2 gehasht).

### Nützliche Schalter

```bash
python run.py --port 9000      # anderer Port
python run.py --host 0.0.0.0   # auch vom Handy im WLAN erreichbar
python run.py --no-browser     # Browser nicht automatisch öffnen
python run.py --rebuild        # Oberfläche neu bauen
python run.py --dev            # Entwicklungsmodus mit Auto-Neuladen
```

Alle Daten liegen in `./data/sparbit.db`. Ordner mitnehmen = Umzug erledigt.

---

## Die ersten 10 Minuten

**1. Quellen prüfen und einschalten.** Unter *Quellen* bei jeder interessanten
Quelle **„Jetzt testen"** drücken — der Test ruft den echten Endpoint auf und
zeigt die ersten Treffer. Grün heißt einschalten, rot zeigt dir den Grund.
Fang mit **mydealz**, **Reddit** und **Epic** an, die decken schon viel ab.

> Wichtig: Kein Endpoint konnte beim Bauen des Projekts geprüft werden — die
> Build-Umgebung kam nicht ins offene Internet. Alles startet als *ungeprüft*,
> und alle URLs sind im UI änderbar. Details in
> [ENDPOINTS.md](ENDPOINTS.md).

**2. Benachrichtigung einrichten.** Zwei Wege, beide gehen parallel:

* **Desktop-Meldungen** — unter *Benachrichtigungen* einschalten, einmal
  erlauben, fertig. Kein Bot, kein Token. Ideal, wenn SparBit ohnehin läuft.
* **Telegram** — für unterwegs, siehe unten.

**3. Erste Regel.** Unter *Regeln* eine **Vorlage** anklicken („Alles Gratis",
„Gratis-Spiele", „Preisfehler" …), anpassen, speichern. Rechts siehst du beim
Tippen, wie viele der letzten 500 Deals die Regel getroffen hätte — samt
Beispielen und den Deals, die *knapp* daneben lagen. Damit tunst du Regeln
ohne Rauschen, statt zu raten.

---

## Was SparBit kann

### Quellen

14 Quellen als Plugins, jede einzeln schaltbar mit eigenem Intervall:

| Gruppe | Quellen |
|---|---|
| Deal-Communities | mydealz, Preisjäger.at, HotUKDeals, Dealabs |
| Blogs | Sparhamster.at, Schnäppchenfuchs |
| Reddit | GameDeals, FreeGameFindings, freebies, googleplaydeals, AppHookup, Schnaeppchen — Subreddits im UI pflegbar |
| Gaming | Epic Games Store, GOG, Steam, CheapShark, IsThereAnyDeal, GG.deals |
| Eigene | beliebige RSS/Atom-Feeds (z. B. deine Geizhals-Wunschliste) |

Fällt eine Quelle aus, laufen die anderen weiter. Nach fünf Fehlern in Folge
pausiert ein Schutzschalter sie automatisch; im UI steht, warum.

### Filter, die man versteht

* Keywords (ODER), Pflicht-Keywords (UND), Blacklist — mit `lego*` als Präfix
  und `"nintendo switch"` als Phrase
* Preisgrenze, Mindestrabatt, „nur 0 €", Mindest-Temperatur
* Quellen-, Kategorie- und Händlerfilter
* Priorität **SOFORT** (Push in Sekunden) oder **NORMAL** (stündliche
  Zusammenfassung)
* **Live-Vorschau** beim Bauen: Trefferzahl, Beispiele, „knapp verfehlt" und
  eine Begründung je Deal, warum er getroffen oder gescheitert ist

Preise werden robust aus deutschem Text gelesen — `12,99€ statt 89,90€`,
`-95%`, `gratis`, `geschenkt`, `1.299,00 €`. Alles wird in **Euro umgerechnet**,
damit „max. 20 €" auch bei USD- und GBP-Quellen richtig greift.

### Suche

Volltextsuche über SQLite-FTS5 — sie bleibt auch bei 50.000 Deals schnell und
kann Dinge, die eine einfache Suche nicht kann:

| Eingabe | Bedeutung |
|---|---|
| `lego technic` | beide Wörter |
| `"nintendo switch"` | genau diese Wortfolge — trifft *nicht* „Nintendo 3DS und Switch Lite" |
| `ssd -gebraucht` | „gebraucht" ausschließen |
| `kopfhör*` | Präfix, findet auch „Kopfhörern" |

Fehlt FTS5 in deiner SQLite-Version, fällt die Suche automatisch auf die
einfache Variante zurück.

### Preisvergleich über Quellen

Derselbe Deal aus vier Communities kommt **einmal** an (URL-Hash plus
Titelvergleich). Produktvarianten bleiben getrennt: „Hades" und „Hades II",
„990 Pro" und „990 Evo" sind nicht dasselbe.

Was jede Quelle verlangt, wird trotzdem einzeln gespeichert. Die
Detailansicht zeigt daraus eine Tabelle — günstigster zuerst, jede Zeile mit
eigenem Link. Fremdwährungen stehen mit ihrem Euro-Gegenwert daneben, sonst
ließe sich `265,00 $` nicht gegen `249,00 €` vergleichen (in dem Beispiel
gewinnt der Dollarpreis).

### Benachrichtigungen

* **Telegram** mit Bild, Preis, Direktlink und Knöpfen — *gemerkt* und *Quelle
  6 h stumm* funktionieren wirklich
* **Desktop-Meldungen** im Browser
* **E-Mail**, **Discord/Webhook**, **ntfy**
* Ruhezeiten, die SOFORT-Regeln durchlassen
* Global pausieren — im UI oder per `/pause` in Telegram

**Telegram-Befehle:** `/status`, `/neueste`, `/gratis`, `/pause`, `/weiter`,
`/hilfe`. Der Bot nutzt Long Polling und braucht deshalb **keinen offenen
Port** — er funktioniert hinter jedem Heimrouter.

### Preisverlauf und Preisalarme

Jede Preisänderung wird aufgezeichnet. In der Detailansicht siehst du die Kurve,
Tiefst- und Höchstpreis. Und du kannst einen **Preisalarm** setzen: „melde dich,
wenn das unter 20 € fällt". Löst genau einmal aus, nicht bei jedem Durchlauf.

### Statistiken

Welche Quelle liefert Signal, welche nur Rauschen? Die Statistik-Seite zeigt
Verlauf, Ausbeute je Quelle (inklusive **Signalanteil** — wie viel Prozent der
Funde eine Regel getroffen haben) und die häufigsten Händler. Damit weißt du,
welche Quelle du seltener abfragen oder abschalten solltest.

### Bilder bleiben bei dir

Deal-Bilder werden einmal geholt, verkleinert unter `./data/images` abgelegt
und von SparBit selbst ausgeliefert. Ohne das erführe jeder Händler bei jedem
Öffnen des Feeds, welche Deals du dir gerade ansiehst. Abschaltbar, und der
Cache räumt sich mit den Deals zusammen auf.

### Bedienung

* Hell, dunkel oder wie im System
* **Strg/Cmd + K** öffnet den Schnellzugriff
* `/` springt in die Suche, `g` gefolgt von `d`/`f`/`s`/`q`/`r` navigiert
* Gespeicherte Suchen im Feed
* CSV-Export, JSON-Backup und **Backup-Import**
* Als App installierbar (PWA), voll bedienbar auf dem Handy

### Auto-Claimer

Epic, Prime Gaming und GOG holen ihre Gratis-Titel selbst — über
[vogler/free-games-claimer](https://github.com/vogler/free-games-claimer) in
einem eigenen Container. Siehe [Mit Docker](#mit-docker).

---

## Telegram einrichten (3 Minuten)

1. In Telegram **@BotFather** anschreiben, `/newbot` senden.
2. Namen vergeben (der Benutzername muss auf `bot` enden). Du bekommst den
   **Token** — sieht aus wie `123456789:AAE...`.
3. **@userinfobot** anschreiben, der nennt dir deine numerische **Chat-ID**.
4. **Deinem eigenen Bot einmal `/start` senden.** Ohne das darf er dir nicht
   schreiben — das ist der häufigste Stolperstein.
5. Im UI unter *Benachrichtigungen* → **Telegram** → Token und Chat-ID
   eintragen → speichern → **Test senden**.

---

## API-Keys (optional)

Ohne sie bleiben nur diese beiden Quellen aus, alles andere läuft.

| Dienst | Wo | Kosten |
|---|---|---|
| IsThereAnyDeal | <https://isthereanydeal.com/apps/my/> — App registrieren | kostenlos |
| GG.deals | <https://gg.deals/de/api/> — Zugang beantragen | für private Nutzung kostenlos |

Eintragen unter *Quellen → (Quelle) → Einstellungen*. Die Keys landen in der
Datenbank, nicht in einer Datei, und werden bei jeder Rückgabe maskiert.

---

## Mit Docker

Wenn SparBit dauerhaft auf einem Server laufen soll — oder du den Auto-Claimer
willst:

```bash
cp .env.example .env
nano .env                       # Zeitzone, ggf. Claimer-Zugangsdaten
docker compose up -d --build
```

Danach <http://server-ip:8080>. Ohne Claimer:

```bash
docker compose up -d --build backend frontend
```

### Auto-Claimer

Zugangsdaten in die `.env` (`EG_EMAIL`, `PG_EMAIL`, … siehe `.env.example`).
Zeitplan über `CLAIMER_SCHEDULE`, Vorgabe täglich 4 Uhr.

Wegen 2FA und Captchas musst du dich **einmal interaktiv anmelden**. Dafür gibt
es einen VNC-Zugang, der bewusst nur an `127.0.0.1` gebunden ist:

```bash
ssh -L 5900:127.0.0.1:5900 -L 6080:127.0.0.1:6080 user@dein-server
```

Dann `http://localhost:6080` öffnen und durchklicken. Die Session liegt im
Volume `claimer-data` und überlebt Neustarts. Manuell auslösen:
`docker compose run --rm claimer`.

Falls das Image Probleme macht, ist
[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)
der Fallback (nur Epic). Das Log-Parsing kommt mit beiden Formaten zurecht und
zeigt im Zweifel das Rohlog.

### Hinter Caddy oder Traefik

Beim `frontend` die Portfreigabe auf `127.0.0.1:8080:80` ändern und den Proxy
davorhängen.

```caddy
deals.example.com {
    reverse_proxy localhost:8080 {
        flush_interval -1   # ohne das kommt der Live-Ticker nie an
    }
}
```

Zwei Dinge zählen: **kein Puffern auf `/api/events`** (sonst steht der
Live-Ticker), und **HTTPS verwenden** — dann setzt SparBit das Session-Cookie
automatisch mit `Secure`.

---

## Entwicklung

```bash
python run.py --dev              # Backend mit Auto-Neuladen

cd frontend && npm run dev       # Oberfläche separat, mit Hot-Reload
```

Tests laufen ohne Netzwerk gegen gespeicherte Fixtures:

```bash
cd backend && pytest tests/ -q   # 168 Tests
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

### Aufbau

```
Quellen (Plugins) ─► Dedupe ─► SQLite (WAL) ─► Regeln ─► Kanäle
  isoliert,          URL-Hash    Deals,         Keywords,   Telegram
  Schutzschalter   + Fuzzy-Titel Historie,      Preis EUR,  Desktop
  je Quelle                      Regeln,        Rabatt,     E-Mail
                                 Treffer        Temperatur  Discord, ntfy
       │                              │                          │
       └──── APScheduler ─────────────┴──── SSE ──► Web-UI ◄──────┘
```

Backend: Python 3.11+, FastAPI, SQLAlchemy 2, SQLite (WAL), APScheduler, httpx.
Frontend: Vite, React 18, TypeScript, Tailwind. Beim lokalen Start liefert das
Backend die gebaute Oberfläche gleich mit aus — ein Prozess, ein Port.

---

## Sicherheit

* Passwort mit **argon2** gehasht, kein Standard-Passwort im Code
* **Bremse gegen Durchprobieren:** ab 5 Fehlversuchen wachsende Wartezeit, ab
  10 für 15 Minuten gesperrt. Die Zähler liegen in der Datenbank — ein
  Neustart hebt die Sperre nicht auf.
* Session-Cookie signiert, `HttpOnly`, `SameSite=Lax`, `Secure` bei HTTPS
* Deal-Bilder werden lokal zwischengespeichert, statt sie bei jedem Aufruf
  vom Händler zu laden
* Secrets in der Datenbank bzw. `.env`, nichts im Repository
* Lokal lauscht SparBit nur auf `127.0.0.1` — erst `--host 0.0.0.0` macht es
  im Netz sichtbar
* **Der Backup-Export enthält API-Keys und Telegram-Token im Klartext.**
  Behandle die Datei wie ein Passwort.

## Höfliches Crawling

Fremde Server kosten fremdes Geld:

* eigener, sprechender User-Agent
* Mindestabstand zwischen Anfragen an denselben Host (Vorgabe 1 s)
* ETag und Last-Modified werden mitgeführt, 304 spart die Übertragung
* exponentieller Backoff bei 429 und 5xx, `Retry-After` wird respektiert
* Mindestintervall je Quelle, das im UI nicht unterschritten werden kann

Bitte dreh die Intervalle nicht ohne Grund runter. Eine Quelle, die dich
sperrt, nützt dir nichts.

## Problemlösung

| Problem | Ursache und Lösung |
|---|---|
| `python: command not found` | Python installieren: <https://www.python.org/downloads/>. Unter Windows beim Setup „Add Python to PATH" ankreuzen. |
| „Konnte .venv nicht anlegen" | Unter Debian/Ubuntu fehlt `python3-venv`: `sudo apt install python3-venv` |
| Oberfläche fehlt, API läuft | Node.js installieren (<https://nodejs.org>), dann `python run.py --rebuild` |
| Port 8000 belegt | `python run.py --port 9000` |
| Quelle liefert 403 | Manche Seiten stehen hinter Cloudflare. „Jetzt testen" zeigt den Grund; siehe [ENDPOINTS.md](ENDPOINTS.md). |
| Telegram schweigt | Dem Bot einmal selbst `/start` senden. Dann „Test senden" im UI. |
| Live-Ticker steht | Hinter einem Reverse-Proxy: Puffern für `/api/events` abschalten. |
| „Zu viele Fehlversuche" | Die Anmeldebremse greift. Warte die angezeigte Zeit ab — der Knopf zählt herunter. |
| Bilder fehlen | Unter *Logs & System → Bild-Cache* nachsehen. Nicht erreichbare Bilder werden einmal versucht und dann übersprungen. |

## Lizenz

MIT — siehe [LICENSE](LICENSE).
