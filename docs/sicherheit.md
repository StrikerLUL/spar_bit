# Sicherheit und Problemloesung

Was geschuetzt ist, was nicht, und was zu tun ist, wenn etwas klemmt.

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
* **Der Backup-Export enthält API-Keys und Kanal-Zugangsdaten im Klartext**
  (Bot-Token, Webhook-URLs, SMTP-Passwort). Behandle die Datei wie ein
  Passwort.
* Kanal-Geheimnisse liegen in der Datenbank, nicht in Dateien, und kommen aus
  der API nur maskiert zurück — beim Bearbeiten leer lassen heißt „behalten".

### Höfliches Crawling

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
| Quelle liefert 403 | Manche Seiten stehen hinter Cloudflare. „Jetzt testen" zeigt den Grund; siehe [ENDPOINTS.md](../ENDPOINTS.md). |
| `KeinFeed: HTML-Seite geliefert, keinen Feed` | Der eingetragene Pfad ist kein Feed. SparBit probiert die üblichen Adressen selbst durch (siehe [Den Feed finden](#den-feed-finden-statt-ihn-zu-raten)); bleibt die Meldung, nennt sie, was probiert wurde — dann im Browser nachsehen und die Adresse eintragen. |
| `r/…: HTTPStatusError: 404 Not Found` | Den Subreddit gibt es nicht. SparBit streicht ihn beim nächsten Lauf selbst und legt ihn unter *Automatisch entfernt* ab. |
| `RateLimited: HTTP 429, retry after 58s` | Reddit drosselt diesen Server — typisch für VPS in Rechenzentrums-Netzen. Die Quelle macht eine Pause und beim nächsten Lauf dort weiter, wo sie stand. Bleibt es dabei: Intervall hochsetzen und *Subreddits pro Lauf* auf 1–2 stellen. |
| Quelle steht auf „gedrosselt bis …" | Kein Defekt und keine Stummschaltung, sondern die Pause, um die die Gegenseite gebeten hat. Danach läuft sie von selbst weiter. |
| Telegram schweigt | Dem Bot einmal selbst `/start` senden. Dann „Test senden" im UI. |
| Kanal schweigt, Test schlägt fehl | Der Verlauf unter *Benachrichtigungen* nennt den Fehler im Klartext. Auf der Konsole: `python cli.py kanaele testen`. |
| Discord: „sieht nicht nach einer Discord-Webhook-URL aus" | Es ist die Kanal- statt der Webhook-URL. Die richtige beginnt mit `https://discord.com/api/webhooks/`. |
| Matrix: 403 oder „Raum-ID beginnt mit !" | Die `#alias:server`-Form geht nicht; die interne ID steht unter *Raumeinstellungen → Erweitert*. Und der Bot muss dem Raum beigetreten sein. |
| Pushover meldet „application token is invalid" | Token und Benutzerschlüssel vertauscht. Der Benutzerschlüssel steht auf der Pushover-Startseite. |
| Kein Bereich „Updates" unter *Logs & System* | `SPARBIT_UPDATE_TOKEN` fehlt in der `.env`. Setzen, dann `./sparbit neustart backend`. |
| Update-Knopf tut nichts | Der Timer läuft nicht: `systemctl list-timers sparbit-update`. Fehler im letzten Lauf: `journalctl -u sparbit-update -n 50`. |
| „Token abgelehnt" im Journal | Die `.env` wurde nach dem Containerstart geändert — `./sparbit neustart backend`. |
| Update bricht mit „Not possible to fast-forward" ab | Auf dem Server liegen eigene Commits. Absicht von SparBit: es überschreibt nichts. `git -C /opt/sparbit status` zeigt, was dort liegt. |
| CLI: „Quelle gibt es nicht" | `python cli.py quellen liste` zeigt die gültigen IDs — bei Tippfehlern schlägt die CLI die richtige vor. |
| Live-Ticker steht | Hinter einem Reverse-Proxy: Puffern für `/api/events` abschalten. |
| „Zu viele Fehlversuche" | Die Anmeldebremse greift. Warte die angezeigte Zeit ab — der Knopf zählt herunter. |
| „zu wenig Daten" statt Urteil | SparBit braucht mindestens vier Preismessungen. Nach ein paar Tagen füllt sich das von selbst. |
| „Für dich" sortiert nach Datum | Noch zu wenig gelernt. Merk dir ein Dutzend Deals, dann greift die Empfehlung. |
| Wunschliste: „kein Preis gefunden" | Die Seite liefert keine strukturierten Daten. Oft hilft die Detailseite statt der Übersicht. |
| Erweiterung verbindet nicht | Schlüssel zurückgezogen? Neuen anlegen. Läuft SparBit nicht auf localhost, muss die Adresse in `manifest.json` unter `host_permissions` stehen. |
| Bilder fehlen | Unter *Logs & System → Bild-Cache* nachsehen. Nicht erreichbare Bilder werden einmal versucht und dann übersprungen. |

## Bekannte Lücken

Ehrlich benannt statt verschwiegen:

* **Kein Endpoint ist vorab verifiziert.** Siehe [ENDPOINTS.md](../ENDPOINTS.md) —
  der erste Schritt ist `python -m tools.verify_endpoints`.
* **Die Preisfehler-Erkennung startet ungeeicht.** Die Gewichte sind
  begründet, aber am Schreibtisch gewählt. SparBit lernt jetzt dazu: klick
  bei einem Fund auf „Echter Fehler" oder „Fehlalarm" (geht auch per
  Telegram-Knopf), und unter *Preisfehler → einstellen → Eichung* steht,
  welches Indiz bei dir wie oft richtig lag — samt Vorschlag für die
  Schwelle. Verstellt wird nichts von selbst.
* **Fremdpreise braucht es erst.** Das stärkste Indiz nach der Kommastelle ist
  der Vergleich mit anderen Quellen — den gibt es nur, wenn mehrere Quellen
  denselben Artikel melden. Mit einer eingeschalteten Quelle bleibt der
  Detektor auf den eigenen Verlauf angewiesen.
* **Sechs Quellen fehlen bewusst** — itch.io, Indiegala, Fanatical, Humble,
  Unreal/FAB und Kleinanzeigen hätten HTML-Scraping erfordert. Gründe und
  Alternativen stehen in [ENDPOINTS.md](../ENDPOINTS.md).
* **Die Gratis-Gegenprobe ist nur so gut wie die Zielseite.** Sie liest
  ausschließlich ausgezeichnete Preisangaben (schema.org, Microdata,
  OpenGraph). Shops, die ihren Preis erst per JavaScript nachladen, und
  Community-Posts, die gar keinen nennen, ergeben `ungeprüft` — und dann
  bleibt alles, wie die Quelle es gemeldet hat. Das ist so gewollt, heißt
  aber: sie fängt nicht jeden Fall.
* **Die 18+-Quellen sind ungeprüft wie alle anderen** — die vorbelegten
  Gruppen-Pfade und Subreddit-Namen sind geraten. Ein falscher Pfad heilt
  sich inzwischen selbst: erst über die Feed-Auszeichnung der Seite, und
  wenn die fehlt, über die bekannten Muster der Shop-Software. Was Reddit
  mit 404 beantwortet, verschwindet von selbst aus der Liste. Erst testen,
  dann behalten; Kandidaten und Feed-Konventionen stehen in
  [ENDPOINTS.md](../ENDPOINTS.md#18-bereich).
* **Auch die Muster-Suche hat eine Grenze.** Sie kennt Pepper, Shopify,
  WordPress und die üblichen `/feed`-Varianten — eine Seite, die ihren Feed
  weder auszeichnet noch an einer dieser Stellen hat, bleibt Handarbeit.
  Die Tabelle der üblichen Adressen je Shop-System steht in ENDPOINTS.md.
* **Ob es die vorbelegten Subreddits gibt, weiß ich weiterhin nicht.**
  `r/SexToyDeals` ist aus dem Betrieb widerlegt und draußen; `r/NSFWdeals`
  und `r/AdultDeals` sind in deinen Läufen nie bis zu einer Antwort
  gekommen, weil vorher das Rate-Limit griff. Bleiben sie leer, ist
  *Eigene 18+-Quellen* der Weg, der nichts rät.


## Dazugekommen

Der aktuelle Stand steht in [../SECURITY.md](../SECURITY.md). Kurz:

* **Zweiter Faktor** (TOTP) mit acht Ersatzcodes — gegen ein
  wiederverwendetes Passwort aus einem fremden Datenleck hilft keine
  Anmeldebremse, weil nichts geraten wird.
* **Netzschutz vor jedem ausgehenden Abruf**: keine Adresse im eigenen Netz,
  auch nicht über eine Weiterleitung. Abschaltbar mit
  `SPARBIT_ERLAUBE_PRIVATE_ZIELE=true`.
* **Obergrenze beim Lesen**, gezählt auf entpackte Bytes — greift damit auch
  gegen ein Archiv, das aus wenigen Kilobyte 50 MB macht.
* **Content-Security-Policy** auf beiden Auslieferungswegen (nginx und
  Backend). Vorher hatte der lokale Start gar keine Kopfzeilen.
* **Verschlüsselte Sicherungen** (AES-256-GCM, Schlüssel per scrypt).
* **Zweiter Faktor als Pflicht für Administratoren**, abschaltbar, Vorgabe
  aus. Ein Admin-Konto kann Quellen umstellen, Updates einspielen und
  Sicherungen herunterladen — und in denen stehen die Geheimnisse aller
  Konten. Gesperrt werden nur die Admin-Funktionen: anmelden und den zweiten
  Faktor einrichten geht weiter, sonst wäre die Pflicht eine Aussperrung
  statt einer Hürde. Einschalten darf sie nur, wer selbst schon einen hat —
  sonst sperrt sich der einzige Administrator im selben Klick aus, und die
  Einstellung zum Zurücknehmen ist genau eine der gesperrten.
* **Anlagenweite Einstellungen sind Admin-Sache.** `PUT /api/settings` hing
  am Router statt an einer Rolle; damit konnte ein **Gast**, der laut
  Beschreibung nur zusehen darf, die Währungskurse der ganzen Anlage ändern,
  die Preisfehler-Schwelle verstellen und das Passwort der Sicherungen
  setzen. Dasselbe galt für Bilder-Aufräumen, Quellen-Snooze und die
  Schwellenübernahme. Eine eigene Testdatei zählt die anlagenweiten
  Endpunkte jetzt auf, damit der nächste nicht wieder durchrutscht.
* **Bremse für die Endpunkte, die nach draußen greifen** — „Quelle testen",
  Feed-Suche, Sammeleingabe der Wunschliste, Kanal-Test. Ein Aufruf hier löst
  mehrere Abrufe bei einem fremden Shop aus. Wer den Knopf in einer Schleife
  drückt (oder ein Skript daran hängt), macht aus SparBit einen Verstärker:
  eine Anfrage rein, zwanzig Anfragen an einen fremden Server raus. Das fällt
  nicht auf SparBit zurück, sondern auf die IP des VPS. Gezählt wird je
  Konto, die Absage nennt die Wartezeit in `Retry-After`.
* **CORS mit `*` gibt keine Cookies mehr frei.** Die Sternchen-Schreibweise
  sieht harmlos aus („ich will es nur schnell testen") und ist genau dort
  nicht harmlos: Starlette spiegelt dann jede Herkunft zurück, und eine
  beliebige fremde Seite dürfte angemeldete Anfragen stellen — der
  `SameSite=Lax`-Schutz des Cookies nützt dabei nichts mehr. SparBit warnt
  im Protokoll und lässt Cookies für fremde Herkünfte weg.
* **Veraltete Wechselkurse sind jetzt sichtbar.** Kein Angriff, aber ein
  stiller Fehler: eine Regel „max. 20 €" greift bei Fremdwährungen von Jahr
  zu Jahr weiter daneben, ohne dass irgendwo etwas rot wird. Das Alter steht
  im UI, in `/api/health` und in den Metriken.

## Wenn etwas klemmt

| Symptom | Erster Blick |
|---|---|
| „heute keine Deals" | `/api/health` — steht dort `degraded`, sagt der Befund, warum |
| Meldungen kommen nicht an | *Kanäle → Kanal testen*, danach das Protokoll darunter |
| Web Push kommt nicht an | Gerät unter *Push aufs Gerät* noch gelistet? Kanal vom Typ *Browser* aktiv? |
| Datenbank nach Update komisch | Schema-Stand unter *Logs & System* gegen `neuester` prüfen |
| Quelle liefert nichts | *Jetzt testen* — der Befund nennt Endpunkt und Fehler |

---

[← Zurück zur Übersicht](../README.md)
