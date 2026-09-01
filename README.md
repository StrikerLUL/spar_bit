# SparBit

Deal- und Freebie-Zentrale für zu Hause: sammelt Gratis-Sachen, Preisfehler und
starke Rabatte aus vielen Quellen, **beurteilt sie am eigenen Preisverlauf**,
filtert nach deinen Regeln und meldet Treffer sofort per Telegram oder als
Desktop-Meldung.

**Läuft auf deinem eigenen Rechner.** Kein Server, kein Docker, keine
Konfigurationsdateien. Ein Befehl genügt.

![Lizenz](https://img.shields.io/badge/Lizenz-MIT-blue) ![Python](https://img.shields.io/badge/Python-3.11+-3776ab) ![React](https://img.shields.io/badge/React-18-61dafb) ![Tests](https://img.shields.io/badge/Tests-244-22c55e)

```bash
git clone https://github.com/StrikerLUL/spar_bit.git
cd spar_bit
python run.py
```

---

**Inhalt** · [Loslegen](#loslegen) · [Die ersten 10 Minuten](#die-ersten-10-minuten)
· [Was SparBit kann](#was-sparbit-kann) · [Telegram](#telegram-einrichten)
· [API-Keys](#api-keys-optional) · [Mit Docker](#mit-docker)
· [Entwicklung](#entwicklung) · [Sicherheit](#sicherheit)
· [Problemlösung](#problemlösung) · [Bekannte Lücken](#bekannte-lücken)

> **Vor dem ersten Start: [ENDPOINTS.md](ENDPOINTS.md) lesen.**
> Kein Quellen-Endpoint konnte beim Bauen live geprüft werden — die
> Build-Umgebung hatte keinen Netzzugang zu den Deal-Seiten. Alle Quellen
> starten als *ungeprüft*; ein Befehl bzw. ein Knopf im UI verifiziert sie auf
> deinem Rechner. Das ist Absicht: lieber ehrlich ungeprüft als falsch
> „funktioniert".

---

## Loslegen

Du brauchst **Python 3.11 oder neuer**. Node.js ist optional — nur nötig, wenn
du die Oberfläche selbst neu bauen willst.

**Windows:** `start.bat` doppelklicken.
**macOS/Linux:** `./start.sh` oder `python3 run.py`.

Beim ersten Mal legt SparBit eine virtuelle Umgebung an, installiert die
Abhängigkeiten und startet — danach öffnet sich <http://localhost:8000>.
Dauert etwa eine Minute; jeder weitere Start ein paar Sekunden.

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

Alle Daten liegen in `./data/`. Ordner mitnehmen = Umzug erledigt.

---

## Die ersten 10 Minuten

**1. Quellen prüfen und einschalten.** Unter *Quellen* bei jeder interessanten
Quelle **„Jetzt testen"** drücken — der Test ruft den echten Endpoint auf und
zeigt die ersten Treffer. Grün heißt einschalten, rot nennt den Grund. Fang mit
**mydealz**, **Reddit** und **Epic** an, die decken schon viel ab.

Alles auf einmal prüfen:

```bash
cd backend && python -m tools.verify_endpoints
```

**2. Benachrichtigung einrichten.** Zwei Wege, beide gehen parallel:

* **Desktop-Meldungen** — unter *Benachrichtigungen* einschalten, einmal
  erlauben, fertig. Kein Bot, kein Token.
* **Telegram** — für unterwegs, [siehe unten](#telegram-einrichten).

**3. Erste Regel.** Unter *Regeln* eine **Vorlage** anklicken („Alles Gratis",
„Preisfehler" …), anpassen, speichern. Rechts siehst du beim Tippen, wie viele
der letzten 500 Deals die Regel getroffen hätte — samt Beispielen und den
Deals, die *knapp* daneben lagen. Damit tunst du Regeln ohne Rauschen.

---

## Was SparBit kann

### Finden

**14 Quellen als Plugins**, jede einzeln schaltbar mit eigenem Intervall:

| Gruppe | Quellen |
|---|---|
| Deal-Communities | mydealz, Preisjäger.at, HotUKDeals, Dealabs |
| Blogs | Sparhamster.at, Schnäppchenfuchs |
| Reddit | GameDeals, FreeGameFindings, freebies, googleplaydeals, AppHookup, Schnaeppchen — im UI pflegbar |
| Gaming | Epic Games Store, GOG, Steam, CheapShark, IsThereAnyDeal, GG.deals |
| Eigene | beliebige RSS/Atom-Feeds (z. B. deine Geizhals-Wunschliste) |

Fällt eine Quelle aus, laufen die anderen weiter. Nach fünf Fehlern in Folge
pausiert ein Schutzschalter sie automatisch; im UI steht, warum.

**Wunschliste** — Artikel, die SparBit *selbst* beobachtet, unabhängig davon,
ob sie jemand als Deal postet. Du trägst Shop-URL und Zielpreis ein, SparBit
fragt regelmäßig nach und meldet den Preissturz.

Der Preis kommt aus **strukturierten Daten** (JSON-LD, Open Graph, Microdata) —
denselben, die Shops für Suchmaschinen ausliefern, und dem stabilen Teil einer
Produktseite: CSS-Klassen ändern sich bei jedem Redesign, `"@type": "Product"`
nicht. Liefert eine Seite davon nichts, sagt SparBit das klar, statt einen
brüchigen Selektor zu raten.

**[Browser-Erweiterung](browser-extension/)** für Chrome, Edge, Brave und
Firefox — setzt Artikel in einem Klick von jeder Shop-Seite auf die
Wunschliste und zeigt direkt dort, wenn SparBit ihn woanders günstiger kennt.

### Beurteilen

Der von der Quelle gemeldete Rabatt sagt wenig: Händler rechnen gegen eine UVP,
die nie jemand bezahlt hat. SparBit urteilt aus dem **eigenen Preisverlauf**:

| Urteil | Bedeutung |
|---|---|
| **Bestpreis** | so günstig war es noch nie beobachtet |
| **sehr gut / gut** | im unteren Viertel des bisher Gesehenen |
| **normal** | üblicher Preis |
| **war günstiger** | nennt dir, wann es billiger war |
| **UVP fragwürdig** | kam nie in die Nähe seiner angeblichen UVP |

Bei zu wenig Verlauf sagt SparBit **„zu wenig Daten"** statt zu raten. Regeln
können darauf filtern — „nur echte Bestpreise" ist ein Klick.

**Preisvergleich über Quellen.** Derselbe Deal aus vier Communities kommt
einmal an, aber was jede Quelle verlangt, wird einzeln gespeichert. Die
Detailansicht zeigt daraus eine Tabelle, günstigster zuerst, jede Zeile mit
eigenem Link. Fremdwährungen stehen mit ihrem Euro-Gegenwert daneben — sonst
ließe sich `265,00 $` nicht gegen `249,00 €` vergleichen (dort gewinnt der
Dollarpreis).

**Preisverlauf und Preisalarme.** Jede Preisänderung wird aufgezeichnet; in der
Detailansicht siehst du die Kurve mit Tiefst- und Höchstpreis. Ein Preisalarm
löst genau einmal aus, nicht bei jedem Durchlauf.

Produktvarianten bleiben getrennt: „Hades" und „Hades II", „iPhone 15" und
„iPhone 16", „990 Pro" und „990 Evo" sind nicht dasselbe.

### Filtern

Regeln aus Keywords (ODER), Pflicht-Keywords (UND) und Blacklist, dazu
Preisgrenze, Mindestrabatt, „nur 0 €", Mindest-Temperatur, Preisurteil sowie
Quellen-, Kategorie- und Händlerfilter. Priorität **SOFORT** (Push in Sekunden)
oder **NORMAL** (Sammelmeldung).

Die **Live-Vorschau** beim Bauen zeigt Trefferzahl, Beispiele, „knapp verfehlt"
und je Deal eine Begründung, warum er getroffen oder gescheitert ist.

**Der Feed lernt mit.** Was du dir merkst, öffnest oder mit einem Alarm
versiehst, wertet SparBit aus — **lokal, ohne externen Dienst**. Der Feed lässt
sich nach *Für dich* sortieren, und jede Empfehlung sagt, warum sie dasteht
(„passt zu dir: „lego", Händler amazon"). Aus demselben Verhalten schlägt
SparBit fertige Regeln vor: *„16 von 16 gemerkten Deals passen zu ‚lego'"*.
Solange zu wenig Signal da ist, hält es den Mund.

**Suche** über SQLite-FTS5 — schnell auch bei 50.000 Deals, und mit Dingen, die
eine einfache Suche nicht kann:

| Eingabe | Bedeutung |
|---|---|
| `lego technic` | beide Wörter |
| `"nintendo switch"` | genau diese Wortfolge — trifft *nicht* „Nintendo 3DS und Switch Lite" |
| `ssd -gebraucht` | „gebraucht" ausschließen |
| `kopfhör*` | Präfix, findet auch „Kopfhörern" |

Preise werden robust aus deutschem Text gelesen — `12,99€ statt 89,90€`, `-95%`,
`gratis`, `1.299,00 €` — und in **Euro umgerechnet**, damit „max. 20 €" auch bei
USD- und GBP-Quellen richtig greift.

### Melden

* **Telegram** mit Bild, Preis, Direktlink und Knöpfen — *gemerkt* und
  *Quelle 6 h stumm* funktionieren wirklich
* **Desktop-Meldungen** im Browser
* **E-Mail**, **Discord/Webhook**, **ntfy**
* Ruhezeiten, die SOFORT-Regeln durchlassen
* Global pausieren — im UI oder per `/pause` in Telegram

**Telegram-Befehle:** `/status`, `/neueste`, `/gratis`, `/pause`, `/weiter`,
`/hilfe`. Der Bot nutzt Long Polling und braucht **keinen offenen Port** — er
funktioniert hinter jedem Heimrouter.

### Drumherum

**Statistiken** — Verlauf, Ausbeute je Quelle inklusive *Signalanteil* (wie viel
Prozent der Funde eine Regel getroffen haben) und häufigste Händler. Damit
siehst du, welche Quelle nur Rauschen liefert.

**Bilder bleiben bei dir** — Deal-Bilder werden einmal geholt, verkleinert unter
`./data/images` abgelegt und von SparBit ausgeliefert. Ohne das erführe jeder
Händler bei jedem Öffnen des Feeds, welche Deals du dir ansiehst.

**Bedienung** — hell/dunkel/wie im System, **Strg/Cmd + K** für den
Schnellzugriff, `/` springt in die Suche, `g` gefolgt von
`d`/`f`/`s`/`w`/`q`/`r` navigiert. Gespeicherte Suchen, CSV-Export,
JSON-Backup und -Import. Als App installierbar (PWA), voll bedienbar auf dem
Handy.

**Auto-Claimer** — Epic, Prime Gaming und GOG holen ihre Gratis-Titel selbst,
über [vogler/free-games-claimer](https://github.com/vogler/free-games-claimer)
in einem eigenen Container. Einrichtung [unter Docker](#auto-claimer-einrichten).

---

## Telegram einrichten

1. In Telegram **@BotFather** anschreiben, `/newbot` senden.
2. Namen vergeben (der Benutzername muss auf `bot` enden). Du bekommst den
   **Token** — sieht aus wie `123456789:AAE...`.
3. **@userinfobot** anschreiben, der nennt dir deine numerische **Chat-ID**.
4. **Deinem eigenen Bot einmal `/start` senden.** Ohne das darf er dir nicht
   schreiben — der häufigste Stolperstein.
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

### Auto-Claimer einrichten

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
der Fallback (nur Epic). Das Log-Parsing kommt mit beiden Formaten zurecht.

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
cd backend && pytest tests/ -q   # 244 Tests, ohne Netzwerk
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
Quellen (Plugins) ─┐
Wunschliste ───────┼─► Dedupe ─► SQLite (WAL) ─► Regeln ─► Kanäle
Erweiterung ───────┘   URL-Hash    Deals,         Keywords,   Telegram
  isoliert,          + Zahlen-     Historie,      Preis EUR,  Desktop
  Schutzschalter     + Titel-      Angebote,      Rabatt,     E-Mail
  je Quelle            vergleich   Urteile        Urteil      Discord, ntfy
       │                   │            │             │           │
       │              Preisurteil   Lernmodell        │           │
       │              (Verlauf)     (lokal)           │           │
       └──── APScheduler ───────────┴──── SSE ──► Web-UI ◄────────┘
```

Backend: Python 3.11+, FastAPI, SQLAlchemy 2, SQLite (WAL), APScheduler, httpx.
Frontend: Vite, React 18, TypeScript, Tailwind. Beim lokalen Start liefert das
Backend die gebaute Oberfläche gleich mit aus — ein Prozess, ein Port.

---

## Sicherheit

* Passwort mit **argon2** gehasht, kein Standard-Passwort im Code
* **Bremse gegen Durchprobieren:** ab 5 Fehlversuchen wachsende Wartezeit, ab
  10 für 15 Minuten gesperrt. Die Zähler liegen in der Datenbank — ein Neustart
  hebt die Sperre nicht auf.
* Session-Cookie signiert, `HttpOnly`, `SameSite=Lax`, `Secure` bei HTTPS
* Die Browser-Erweiterung nutzt ein eigenes Token, das sich einzeln
  zurückziehen lässt
* Deal-Bilder werden lokal zwischengespeichert statt bei jedem Aufruf vom
  Händler geladen
* Lokal lauscht SparBit nur auf `127.0.0.1` — erst `--host 0.0.0.0` macht es im
  Netz sichtbar
* **Der Backup-Export enthält API-Keys und Telegram-Token im Klartext.**
  Behandle die Datei wie ein Passwort.

### Höfliches Crawling

Fremde Server kosten fremdes Geld:

* eigener, sprechender User-Agent
* Mindestabstand zwischen Anfragen an denselben Host (Vorgabe 1 s)
* ETag und Last-Modified werden mitgeführt, 304 spart die Übertragung
* exponentieller Backoff bei 429 und 5xx, `Retry-After` wird respektiert
* Mindestintervall je Quelle, das im UI nicht unterschritten werden kann

Bitte dreh die Intervalle nicht ohne Grund runter. Eine Quelle, die dich
sperrt, nützt dir nichts.

---

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
| „zu wenig Daten" statt Urteil | SparBit braucht mindestens vier Preismessungen. Nach ein paar Tagen füllt sich das von selbst. |
| „Für dich" sortiert nach Datum | Noch zu wenig gelernt. Merk dir ein Dutzend Deals, dann greift die Empfehlung. |
| Wunschliste: „kein Preis gefunden" | Die Seite liefert keine strukturierten Daten. Oft hilft die Detailseite statt der Übersicht. |
| Erweiterung verbindet nicht | Schlüssel zurückgezogen? Neuen anlegen. Läuft SparBit nicht auf localhost, muss die Adresse in `manifest.json` unter `host_permissions` stehen. |
| Bilder fehlen | Unter *Logs & System → Bild-Cache* nachsehen. Nicht erreichbare Bilder werden einmal versucht und dann übersprungen. |

---

## Bekannte Lücken

Ehrlich benannt statt verschwiegen:

* **Kein Endpoint ist vorab verifiziert.** Siehe [ENDPOINTS.md](ENDPOINTS.md) —
  der erste Schritt ist `python -m tools.verify_endpoints`.
* **Der stündliche Digest ist keiner.** NORMAL-Regeln verschicken aufgestaute
  Treffer weiterhin als Einzelnachrichten statt als eine Sammelmeldung.
* **Der Claimer hat keinen Startknopf.** Die Claimer-Seite zeigt den Befehl zum
  Abtippen, statt den Container selbst zu starten.
* **Sechs Quellen fehlen bewusst** — itch.io, Indiegala, Fanatical, Humble,
  Unreal/FAB und Kleinanzeigen hätten HTML-Scraping erfordert. Gründe und
  Alternativen stehen in [ENDPOINTS.md](ENDPOINTS.md).

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
