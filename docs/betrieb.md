# Betrieb

Auf einem Server, auf dem eigenen Rechner, hinter einem Proxy.

## Auf einem VPS

Ein Befehl. Das Skript prüft die Voraussetzungen, installiert bei Bedarf
Docker, erzeugt den Sitzungsschlüssel, fragt nach einer Domain und richtet
bei Bedarf HTTPS ein:

```bash
curl -fsSL https://raw.githubusercontent.com/StrikerLUL/spar_bit/refs/heads/claude/deal-freebie-zentrale-gpi8dr/install.sh | bash
```

Die **einzige** Frage ist die nach der Domain:

* **Mit Domain** → Caddy holt automatisch ein Let's-Encrypt-Zertifikat und
  erneuert es. Danach `https://deine-domain`. Es gibt nichts zu konfigurieren
  und nichts, was in 90 Tagen abläuft und vergessen wird. Voraussetzung: der
  A-Record zeigt auf diesen Server, Port 80 und 443 sind offen.
* **Ohne Domain** → läuft auf Port 8080. Dann bitte **nicht** offen ins
  Internet hängen, sondern über einen SSH-Tunnel benutzen:
  `ssh -L 8080:127.0.0.1:8080 user@server`.

Danach im Browser Konto anlegen, einen Kanal einrichten, mydealz einschalten —
fertig.

### Betrieb

Alles über ein Skript im Installationsverzeichnis (Vorgabe `/opt/sparbit`):

```bash
./sparbit status        # läuft alles, und geht es ihm gut
./sparbit logs          # mitlesen (Strg+C beendet)
./sparbit update        # holen, neu bauen, alte Images aufräumen
./sparbit sichern       # Datenbank sichern (über die SQLite-Backup-API)
./sparbit wiederherstellen sparbit-20260920.db
./sparbit cli preisfehler liste
```

`sichern` kopiert nicht einfach die Datei: eine laufende SQLite-Datenbank hat
Änderungen im WAL, die eine Dateikopie nicht mitnimmt. Für ein tägliches
Backup reicht ein Cron-Eintrag:

```cron
0 4 * * * cd /opt/sparbit && ./sparbit sichern /var/backups/sparbit-$(date +\%F).db
```

**Systemanforderungen:** 1 GB RAM reichen (der Frontend-Build ist die
anspruchsvollste Stelle — bei weniger vorher Swap anlegen), rund 1 GB Platte.
Ein Einsteiger-VPS für ein paar Euro im Monat genügt.

### Updates per Knopfdruck

`install.sh` richtet einen systemd-Timer ein, der minütlich nachsieht, ob
etwas zu tun ist. Im UI erscheint dann unter **Logs & System → Updates**:

* der Stand des Servers (Commit, Zweig, Betreff)
* **ein Knopf** — spielt neue Commits ein, wirkt binnen einer Minute
* **ein Schalter „Automatisch"** — dann geschieht das nach jedem Push von
  selbst, ohne dass du etwas anklickst
* Ergebnis des letzten Laufs; ging etwas schief, steht die Build-Ausgabe
  direkt daneben

Vor jedem Update wird die Datenbank gesichert, und geholt wird nur
**vorwärts** (`git merge --ff-only`) — lokale Änderungen auf dem Server
werden nie überschrieben, das Update bricht dann lieber ab.

Der Container fasst den Host nicht an: kein Docker-Socket, kein git im
Image. Das UI hinterlegt nur einen Auftrag, den das Skript auf dem Host
(`deploy/sparbit-autoupdate.sh`) abholt. Beide weisen sich mit
`SPARBIT_UPDATE_TOKEN` aus der `.env` aus.

Von Hand einrichten (oder nach einem Update von einer älteren Version):

```bash
cd /opt/sparbit
openssl rand -hex 32                     # in die .env als SPARBIT_UPDATE_TOKEN
./sparbit neustart backend

sudo cp deploy/sparbit-update.service deploy/sparbit-update.timer \
        /etc/systemd/system/
sudo sed -i "s|/opt/sparbit|$PWD|g; s|^User=.*|User=$(stat -c '%U' .)|" \
        /etc/systemd/system/sparbit-update.service
sudo systemctl daemon-reload
sudo systemctl enable --now sparbit-update.timer
```

Nachsehen, ob er läuft: `systemctl list-timers sparbit-update`, Ausgabe des
letzten Laufs mit `journalctl -u sparbit-update -n 50`.

Ohne Timer (oder ohne systemd) bleibt alles wie vorher — `./sparbit update`
macht dasselbe von Hand.

## Auf dem eigenen Rechner

Du brauchst **Python 3.11 oder neuer**. Node.js ist optional: fehlt es, holt
sich `run.py` die fertig gebaute Oberfläche aus dem letzten Release (mit
Prüfsumme). Node brauchst du nur, wenn du sie selbst bauen oder ändern willst.

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

## Server betreiben

Für den normalen Fall gibt es [den Installer](#auf-einem-vps). Was hier steht,
brauchst du nur, wenn du es von Hand machen oder etwas abweichend aufsetzen
willst.

```bash
cp .env.example .env
nano .env                       # Zeitzone, ggf. Claimer-Zugangsdaten
docker compose up -d --build
```

Danach <http://server-ip:8080>. Ohne Claimer:

```bash
docker compose up -d --build backend frontend
```

Mit HTTPS (`SPARBIT_DOMAIN` muss in der `.env` stehen):

```bash
docker compose --profile https up -d --build
```

Dann sollte der Frontend-Port nicht mehr nach außen zeigen — dafür
`SPARBIT_WEB_BIND=127.0.0.1` in die `.env`.

> **Läuft auf dem Server schon etwas auf Port 80/443?** Dann ist das
> `https`-Profil der falsche Weg — der mitgelieferte Caddy will genau diese
> Ports. SparBit gehört dann auf eine Subdomain hinter den vorhandenen Proxy:
> [siehe unten](#auf-einer-subdomain-neben-anderen-seiten).

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

### Auf einer Subdomain, neben anderen Seiten

Steht auf dem Server noch nichts, nimm das `https`-Profil oben — Caddy und
[`deploy/Caddyfile`](../deploy/Caddyfile) sind fertig dabei.

Läuft dort aber schon ein Webserver oder Reverse-Proxy, sind Port 80 und 443
belegt. SparBit bekommt dann **keinen eigenen Port nach außen**, sondern einen
Eintrag im vorhandenen Proxy.

**1. Port nur lokal öffnen** — in der `.env`:

```bash
SPARBIT_WEB_BIND=127.0.0.1      # nicht mehr aus dem Internet erreichbar
SPARBIT_WEB_PORT=8080           # frei wählbar, falls 8080 schon belegt ist
```

```bash
docker compose up -d
ss -ltnp | grep 8080            # muss 127.0.0.1:8080 zeigen, nicht 0.0.0.0
```

**2. Im Proxy eintragen.** Drei Dinge zählen, egal welcher Proxy:

* **kein Puffern auf `/api/events`** — sonst steht der Live-Ticker
* **`X-Forwarded-Proto` durchreichen** — daran erkennt SparBit HTTPS und setzt
  das Session-Cookie mit `Secure`
* **lange Lesezeit** für den SSE-Stream, sonst bricht er im Minutentakt ab

<details>
<summary><strong>Caddy</strong></summary>

```caddy
spar-bit.example.de {
    reverse_proxy 127.0.0.1:8080 {
        flush_interval -1        # ohne das kommt der Live-Ticker nie an
    }
}
```

Caddy setzt `X-Forwarded-Proto` von selbst und holt das Zertifikat automatisch.
</details>

<details>
<summary><strong>nginx auf dem Host</strong></summary>

Die fertige Datei liegt im Repo — nur die Domain eintragen:

```bash
sudo cp deploy/nginx-sparbit.conf /etc/nginx/sites-available/sparbit
sudo sed -i 's/DEINE-DOMAIN/spar-bit.example.de/' /etc/nginx/sites-available/sparbit
sudo ln -s /etc/nginx/sites-available/sparbit /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d spar-bit.example.de
```

`certbot --nginx` baut den Block selbst auf HTTPS um und richtet die
Umleitung von Port 80 ein — deshalb steht in der Vorlage noch kein `ssl`.
Sie bringt schon mit, was leicht vergessen wird: eigene Location für den
SSE-Stream ohne Puffer, `X-Forwarded-Proto` für das `Secure`-Cookie und
8 MB Upload-Grenze für den Backup-Import.
</details>

<details>
<summary><strong>Traefik</strong> (Labels statt Portfreigabe)</summary>

Beim `frontend` in der `docker-compose.yml` den `ports`-Block streichen und
stattdessen Labels setzen — Traefik spricht dann direkt mit dem Container:

```yaml
    networks: [default, proxy]           # das Netz deines Traefik
    labels:
      traefik.enable: "true"
      traefik.docker.network: proxy
      traefik.http.routers.sparbit.rule: Host(`spar-bit.example.de`)
      traefik.http.routers.sparbit.entrypoints: websecure
      traefik.http.routers.sparbit.tls.certresolver: le
      traefik.http.services.sparbit.loadbalancer.server.port: "80"
```

und unten im `networks`-Block:

```yaml
networks:
  proxy:
    external: true
```

Traefik setzt `X-Forwarded-Proto` selbst; SSE läuft ohne Zusatzoption.
</details>

<details>
<summary><strong>Nginx Proxy Manager</strong> (die Weboberfläche)</summary>

*Hosts → Proxy Hosts → Add Proxy Host*

| Feld | Wert |
|---|---|
| Domain Names | `spar-bit.example.de` |
| Scheme | `http` |
| Forward Hostname / IP | die Docker-Host-IP, meist `172.17.0.1` |
| Forward Port | `8080` |
| Websockets Support | **an** |
| Block Common Exploits | an |

Reiter *SSL*: Zertifikat anfordern, **Force SSL** an. Dann unter *Advanced*:

```nginx
location /api/events {
    proxy_pass http://172.17.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection        "";
    proxy_buffering off;
    proxy_read_timeout 24h;
}
```
</details>

**3. Prüfen.** Anmelden, dann im Browser unter *Logs & System* nachsehen, ob
der Live-Ticker „verbunden" zeigt. In den Entwicklertools muss das Cookie
`sparbit_session` das Häkchen bei **Secure** haben — fehlt es, kommt
`X-Forwarded-Proto` nicht durch.


## Umgebungsvariablen, die später dazukamen

| Variable | Standard | Wofür |
|---|---|---|
| `SPARBIT_ERLAUBE_PRIVATE_ZIELE` | `false` | Feeds und Shops im eigenen Netz abrufen dürfen |
| `SPARBIT_PLUGIN_DIR` | – | Ordner mit eigenen Quellen-Modulen |
| `SPARBIT_DB_URL_OVERRIDE` | – | Andere Datenbank statt SQLite, z. B. Postgres |
| `SPARBIT_BEZUG` | `auto` | `auto` = fertiges Image ziehen, wenn es zum Commit eines gibt; `build` = immer selbst bauen |
| `SPARBIT_TAG` | `main` | Welche Marke `docker compose up` von Hand zieht. Der Updater setzt sie selbst auf `sha-<commit>` |
| `SPARBIT_IMAGE_BACKEND` / `_FRONTEND` | ghcr.io/strikerlul/… | Eigene Registry, z. B. im Firmennetz |
| `SPARBIT_SCHEDULER` | `auto` | `aus` = der API-Prozess sammelt nicht ein; dann muss ein Worker laufen |

Die vollständige Liste mit Erklärungen steht in
[.env.example](../.env.example).

### Andere Datenbank

SQLite bleibt der Normalfall und das, wofür SparBit gebaut ist — eine Datei,
die man mitnehmen kann. Wer schon ein Postgres betreibt:

```bash
SPARBIT_DB_URL_OVERRIDE=postgresql+psycopg://sparbit:geheim@db/sparbit
```

**Die Suchsyntax bleibt dieselbe.** Bis vor Kurzem fiel die Suche auf
Postgres stillschweigend auf `LIKE` zurück — die dokumentierte Syntax
funktionierte also genau dann nicht, wenn jemand die ebenfalls dokumentierte
Postgres-Option nutzte. Jetzt übersetzt derselbe Parser in `tsquery`:
`lego technic` wird zu `lego & technic`, `kopfhör*` zu `kopfhör:*`,
`"nintendo switch"` zu `nintendo <-> switch`. Ein GIN-Index auf dem
Suchausdruck entsteht beim Start.

### Den Scheduler getrennt betreiben

Für einen Haushalt nicht nötig: SparBit ist ein Prozess, ein Neustart, ein
Protokoll. Wenn das Einsammeln die Oberfläche träge macht, geht auch getrennt:

```bash
# .env
SPARBIT_SCHEDULER=aus            # gilt für den API-Prozess

docker compose --profile worker up -d
```

**Genau einer.** Zwei Worker auf derselben Datenbank fragen jede Quelle
doppelt ab und verschicken jede Meldung zweimal — und das fällt niemandem als
Fehler auf, es sieht aus, als wäre der Feed gut gefüllt. Eine Sperre dagegen
wäre ein verteiltes Schloss für einen Fall, den es hier nicht gibt.

Der Live-Ticker läuft weiter: der Worker spiegelt seine Ereignisse in die
Datenbank, der API-Prozess liest nach — aber nur, solange jemand zusieht. Der
Telegram-Bot wandert mit in den Worker; Long Polling ist eine
Dauerverbindung, und zwei davon würden sich die Nachrichten wegnehmen.

## Automatische Sicherung

Ein täglicher Lauf schreibt nach `data/backups` und hält die letzten sieben
(einstellbar). Mit gesetztem Passwort wird die Datei verschlüsselt.

```bash
ls -la data/backups/
```

Beim Umzug genügt der Ordner `data/` — oder eine Sicherung plus
*Einspielen* auf der neuen Installation.

---

[← Zurück zur Übersicht](../README.md)
