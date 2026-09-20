# SparBit

**Findet Preisfehler, bevor sie korrigiert sind.**

Ein Preisfehler ist kein Rabatt. Es ist ein Versehen des Händlers — eine
verrutschte Kommastelle, eine vergessene Null. Der Fernseher für 899 € steht
plötzlich für 89,90 € drin, und zwanzig Minuten später nicht mehr.

SparBit beobachtet dafür rund um die Uhr 14 Deal-Quellen, vergleicht jeden
Preis mit dem **eigenen beobachteten Verlauf** und mit dem, was andere Quellen
für denselben Artikel verlangen — und weckt dich, wenn etwas nicht
zusammenpasst. Mit Begründung, nicht mit einer Punktzahl.

Nebenbei macht es das, was ein Deal-Monitor sonst so macht: Gratis-Spiele
einsammeln, Wunschlisten überwachen, nach deinen Regeln filtern und über neun
Kanäle melden.

![Lizenz](https://img.shields.io/badge/Lizenz-MIT-blue) ![Python](https://img.shields.io/badge/Python-3.11+-3776ab) ![React](https://img.shields.io/badge/React-18-61dafb) ![Tests](https://img.shields.io/badge/Tests-390-22c55e)

**Auf einem VPS** — ein Befehl, inklusive Docker, HTTPS, Zertifikat und
Update-Knopf im UI:

```bash
curl -fsSL https://raw.githubusercontent.com/StrikerLUL/spar_bit/refs/heads/claude/deal-freebie-zentrale-gpi8dr/install.sh | bash
```

**Auf dem eigenen Rechner** — kein Docker, keine Konfigurationsdatei:

```bash
git clone https://github.com/StrikerLUL/spar_bit.git
cd spar_bit
python run.py
```

---

**Inhalt** · [Preisfehler](#preisfehler) · [Auf einem VPS](#auf-einem-vps)
· [Updates per Knopfdruck](#updates-per-knopfdruck)
· [Auf dem eigenen Rechner](#auf-dem-eigenen-rechner)
· [Die ersten 10 Minuten](#die-ersten-10-minuten)
· [Was SparBit sonst kann](#was-sparbit-sonst-kann)
· [Benachrichtigungen](#benachrichtigungen-einrichten)
· [Kommandozeile](#kommandozeile) · [API-Keys](#api-keys-optional)
· [Server betreiben](#server-betreiben) · [Entwicklung](#entwicklung)
· [Sicherheit](#sicherheit) · [Problemlösung](#problemlösung)
· [Bekannte Lücken](#bekannte-lücken)

> **Vor dem ersten Start: [ENDPOINTS.md](ENDPOINTS.md) lesen.**
> Kein Quellen-Endpoint konnte beim Bauen live geprüft werden — die
> Build-Umgebung hatte keinen Netzzugang zu den Deal-Seiten. Alle Quellen
> starten als *ungeprüft*; ein Befehl bzw. ein Knopf im UI verifiziert sie auf
> deinem Rechner. Das ist Absicht: lieber ehrlich ungeprüft als falsch
> „funktioniert".

---

## Preisfehler

Der naheliegende Ansatz — „melde alles über 90 % Rabatt" — funktioniert nicht.
Er meldet jeden Steam-Sale und jeden aufgeblasenen UVP, und nach einer Woche
hat man den Kanal stummgeschaltet. Deshalb prüft SparBit nicht **eine**
Schwelle, sondern sammelt **Indizien** und addiert sie zu einer Punktzahl von
0 bis 100.

| Indiz | Punkte | Warum es zählt |
|---|--:|---|
| Ausdrücklich als Preisfehler gemeldet | 55 | Das verlässlichste Signal überhaupt — jemand hat den Artikel gesehen |
| „vermutlich Preisfehler" | 30 | Ein Hinweis, keine Feststellung |
| Weit unter dem eigenen Verlauf | 25–45 | Gestuft nach Abstand zum üblichen Preis |
| Noch nie annähernd so günstig | 15 | Unterbietet den bisherigen Tiefstpreis um die Hälfte |
| Andere Quellen verlangen ein Vielfaches | 18–35 | Derselbe Artikel, dreifacher Preis |
| **Verrutschte Kommastelle** | 30 | 899,00 → 89,90 ist Faktor 10 |
| Extremrabatt auf glaubwürdigen UVP | 20 | Nur wenn die UVP nicht schon als fragwürdig erkannt ist |
| Sehr hohe Resonanz | 10 | Stützt nur — trägt nie allein |

**Ab 70 Punkten** („belegt") meldet der Wächter sofort, **ab 45** („Verdacht")
erscheint der Fund nur im Feed und auf der Preisfehler-Seite.

Das stärkste Einzelindiz ist die **verrutschte Kommastelle**, weil es eine
Mechanik beschreibt und nicht bloß „billig" heißt: Händler setzen Rabatte auf
krumme 71 oder 83 Prozent, nie auf exakt 90,0 Prozent. Genau dieser Faktor 10
ist die Signatur eines Tippfehlers.

### Was *nicht* gemeldet wird

Das ist der wichtigere Teil. Ein Wächter, der täglich anschlägt, ist keiner.

* **Gratis-Angebote** — Absicht, kein Versehen.
* **Gutscheine, Sammeldeals, Verträge, Abos, B-Ware, Refurbished** — dort
  gehört ein niedriger Preis zur Bauart des Angebots.
* **Spiele-Shops** (Steam, GOG, Epic, CheapShark, ITAD, GG.deals) werden stark
  gedämpft: 92 % auf ein altes Spiel ist dort der Normalfall. Steht aber
  ausdrücklich „Preisfehler" dabei, sticht das die Dämpfung.
* **Kleinbeträge** — unter 25 € Ersparnis reicht es höchstens für „Verdacht".
  Rechnerisch auffällig, praktisch egal.
* **Alles ohne Vergleichsgröße** — ohne eigenen Verlauf und ohne Fremdpreis
  weiß SparBit nicht, wovon der Preis abweichen soll. Dann sagt es das,
  statt zu raten.
* **Fragwürdige UVP** — hat ein Artikel seine angebliche UVP nie erreicht,
  belegt ein Rabatt darauf gar nichts.

### Der Wächter

Preisfehler sind kurzlebig. Deshalb hat der Wächter einen **eigenen
Meldeweg neben den Regeln**: er braucht keine passend gebaute Regel und hält
sich nicht an Ruhezeiten. Er geht über alle aktiven Kanäle raus, gleich beim
Quellenlauf, und prüft zusätzlich alle 20 Minuten die Deals der letzten Woche
noch einmal — ein Preis fällt ja nicht nur beim ersten Sehen.

Damit derselbe Fund nicht bei jedem Durchlauf erneut das Handy weckt, gilt
eine Sperre von 12 Stunden pro Deal.

Einstellbar unter *Preisfehler* im Browser oder auf der Kommandozeile:

```bash
python cli.py preisfehler liste                  # Funde mit Begründung
python cli.py preisfehler liste --nur-belegt
python cli.py preisfehler waechter --an --schwelle 65
python cli.py preisfehler waechter --aus         # nachts lieber Ruhe
python cli.py preisfehler pruefen                # alles neu bewerten
```

Die Schwelle ist ein Regler, kein Schalter: **30** lässt kaum etwas durch die
Maschen und produziert Fehlalarme, **100** meldet nur noch das Eindeutige.

Für eine Regel, die Preisfehler an einen *bestimmten* Kanal schickt, gibt es
die Bedingung ebenfalls:

```bash
python cli.py regeln hinzufuegen "Preisfehler aufs Handy" \
  --preisfehler 70 --sofort --kanal 1
```

### Ein Fund sieht so aus

```
BELEGT  100/100  89,90 €  statt ~1.499,00 €
        LG OLED evo C4 55 Zoll — statt 1.499,00 € nur 89,90 € (Preisfehler?)
        - Als Preisfehler ausgewiesen.
        - Kostet sonst um 1.474,00 € — das sind 94 % weniger als üblich.
        - Günstigster bisher beobachteter Preis war 1.399,00 €.
        - 94 % unter dem Listenpreis von 1.499,00 €.
        - Sehr hohe Resonanz (1840°).
```

In der Meldung steht nie „Preisfehler (87 Punkte)", sondern **warum**. Nur so
lässt sich in zwei Sekunden entscheiden, ob man dem Fund glaubt.

> Ein Händler darf eine Bestellung zu einem fehlerhaften Preis stornieren.
> Ein Anspruch besteht nicht — SparBit schreibt das unter jeden belegten Fund.

---

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

---

## Auf dem eigenen Rechner

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

**1. Einen Kanal einrichten — zuerst.** Unter *Kanäle* → **Kanal hinzufügen**.
Ohne Kanal meldet sich SparBit nie, auch nicht bei einem Preisfehler; es
sammelt dann nur still vor sich hin. Neun Kanäle stehen zur Wahl, beliebig
viele parallel:

* **Desktop-Meldungen** — einschalten, einmal erlauben, fertig. Kein Bot,
  kein Token. Funktioniert nur, solange der Browser offen ist.
* **Telegram, Discord, Slack, Matrix, Gotify, Pushover, ntfy, E-Mail,
  Webhook** — [siehe unten](#benachrichtigungen-einrichten). Für einen
  Server ist Telegram oder ntfy die naheliegende Wahl.

Danach **Test senden** drücken. Kommt nichts an, stimmt die Konfiguration
nicht — das jetzt zu merken ist besser als beim ersten Preisfehler.

**2. Quellen prüfen und einschalten.** Unter *Quellen* bei jeder interessanten
Quelle **„Jetzt testen"** drücken — der Test ruft den echten Endpoint auf und
zeigt die ersten Treffer. Grün heißt einschalten, rot nennt den Grund. Fang mit
**mydealz**, **Reddit** und **Epic** an, die decken schon viel ab.

Alles auf einmal prüfen:

```bash
cd backend && python -m tools.verify_endpoints
```

**3. Der Preisfehler-Wächter läuft schon.** Er ist ab Werk an und braucht keine
Regel. Auf der Seite *Preisfehler* siehst du, was er gefunden hat, und stellst
die Empfindlichkeit ein. Wer nachts nicht geweckt werden will, schaltet ihn
dort aus — drosseln hilft nicht, es macht ihn nur unzuverlässig.

**4. Erste Regel.** Für alles andere: unter *Regeln* eine **Vorlage** anklicken
(„Alles Gratis", „Preisfehler", „Günstige Technik" …), anpassen, speichern.
Rechts siehst du beim Tippen, wie viele der letzten 500 Deals die Regel
getroffen hätte — samt Beispielen und den Deals, die *knapp* daneben lagen.
Damit tunst du Regeln ohne Rauschen.

> **Geduld beim Urteil.** Preisurteil und Preisfehler-Erkennung brauchen einen
> eigenen Preisverlauf. In den ersten Tagen steht öfter „zu wenig Daten" da —
> das ist Absicht. Ein erfundenes Urteil wäre schlimmer als keines.

---

## Was SparBit sonst kann

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
Preisgrenze, Mindestrabatt, „nur 0 €", Mindest-Temperatur, Preisurteil,
**Preisfehler-Punktzahl** sowie Quellen-, Kategorie- und Händlerfilter. Priorität **SOFORT** (Push in Sekunden)
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

### Preise richtig lesen

Alles oben steht und fällt damit, dass der Preis stimmt. Das Schwierige daran
ist nicht, Zahlen zu finden, sondern zu entscheiden, **welche** davon der
aktuelle Preis ist: ein Deal-Titel nennt fast immer zwei Beträge, und wer den
falschen nimmt, zeigt den durchgestrichenen UVP als Preis an.

SparBit hängt dafür an jede gefundene Zahl ein Etikett aus dem Wort, das
unmittelbar davor steht (`statt`, `UVP` → alt; `nur`, `jetzt`, `für` → neu) —
aber nur, wenn zwischen Wort und Zahl keine *andere* Zahl liegt. Genau diese
Bedingung entscheidet die kniffligen Fälle:

| Titel | Preis | statt |
|---|--:|--:|
| `12,99€ statt 89,90€` | 12,99 € | 89,90 € |
| `statt 59,99 nur 9,99` | 9,99 € | 59,99 € |
| `Sony XM5 statt 379 € jetzt 229 €` | 229 € | 379 € |
| `Nur 9,99 statt 19,99 €` | 9,99 € | 19,99 € |
| `iPhone 15 für 699 statt 949 Euro` | 699 € | 949 € |
| `3 für 2 Aktion: 14,99 €` | 14,99 € | — |
| `16 GB RAM Notebook ab 499 €` | 499 € | — |

Die letzten beiden Zeilen sind die Bremse: eine Zahl ohne Währungszeichen wird
nur dann als Preis akzeptiert, wenn sie ein **Paar** vervollständigt — es gibt
schon einen „alten" Preis und der neue liegt darunter. Ohne diese Regel meldet
`3 für 2` einen Preis von 2 €.

Alle Beträge werden zusätzlich in **Euro umgerechnet**, damit „max. 20 €" auch
bei USD- und GBP-Quellen greift; in der Oberfläche steht der Gegenwert daneben
(`29,99 $ · ≈ 27,59 €`). Preis, Streichpreis, Währung und Rabatt ziehen dabei
immer gemeinsam um: übernimmt eine günstigere Quelle in anderer Währung den
Deal, verschwindet der alte Streichpreis, statt mit dem neuen Währungszeichen
stehen zu bleiben. Und ein Prozentwert wird aus den beiden angezeigten Zahlen
gerechnet, nicht von der Quelle übernommen — sonst steht er neben zwei Preisen,
aus denen er sich nicht ergibt.

### Melden

**Neun Kanäle als Plugins**, beliebig viele parallel, jeder einzeln
abschaltbar und mit *Test senden* sofort prüfbar:

| Kanal | Wofür | Was du brauchst |
|---|---|---|
| **Telegram** | unterwegs, mit Aktions-Knöpfen | Bot-Token + Chat-ID |
| **Discord** | eigener Server, Einbettung mit Farbe und Bild | Webhook-URL |
| **Slack** | Team-Kanal, Block-Kit-Nachricht | Webhook-URL |
| **Matrix** | eigener Homeserver, keine fremde Cloud | Zugangstoken + Raum-ID |
| **Gotify** | selbst gehosteter Push | Server + App-Token |
| **Pushover** | Push auf iOS/Android ohne eigenen Server | App-Token + Benutzerschlüssel |
| **ntfy** | Push ohne Konto, ntfy.sh oder eigene Instanz | Topic |
| **E-Mail** | Archiv, Weiterleitung, Filterregeln im Mailclient | SMTP-Zugang |
| **Webhook** | Home Assistant, n8n, eigene Skripte | URL (bekommt JSON) |
| **Desktop** | derselbe Rechner, kein Konto nötig | ein Klick im Browser |

Jede Meldung trägt **das Preisurteil mit** — ein Bestpreis kommt grün, ein
Preisfehler rot mit seiner Begründung, eine SOFORT-Regel gelb. Discord erwähnt eine Rolle nur
bei SOFORT, Gotify und ntfy heben dann die Priorität an; sonst bleibt es leise.

* Ruhezeiten, die SOFORT-Regeln durchlassen
* Global pausieren — im UI oder per `/pause` in Telegram

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

## Benachrichtigungen einrichten

Im UI: *Benachrichtigungen* → **Kanal hinzufügen** → Typ wählen → Felder
ausfüllen → **Speichern** → **Test senden**. Pflichtfelder sind mit `*`
markiert; ohne sie lässt sich nicht speichern. Auf der Kommandozeile geht
dasselbe mit `python cli.py kanaele` ([siehe unten](#kommandozeile)).

<details>
<summary><strong>Telegram</strong> — mit Knöpfen, funktioniert hinter jedem Heimrouter</summary>

1. In Telegram **@BotFather** anschreiben, `/newbot` senden.
2. Namen vergeben (der Benutzername muss auf `bot` enden). Du bekommst den
   **Token** — sieht aus wie `123456789:AAE...`.
3. **@userinfobot** anschreiben, der nennt dir deine numerische **Chat-ID**.
4. **Deinem eigenen Bot einmal `/start` senden.** Ohne das darf er dir nicht
   schreiben — der häufigste Stolperstein.
5. Token und Chat-ID eintragen, speichern, **Test senden**.

**Befehle im Chat:** `/status`, `/neueste`, `/gratis`, `/pause`, `/weiter`,
`/hilfe`. Der Bot nutzt Long Polling und braucht **keinen offenen Port**.

```bash
python cli.py kanaele hinzufuegen telegram "Handy" \
  --set bot_token=123456789:AAE... --set chat_id=987654321
```
</details>

<details>
<summary><strong>Discord</strong> — eigener Server, Einbettung mit Farbe und Bild</summary>

1. Im Discord-Kanal: *Kanaleinstellungen → Integrationen → Webhooks → Neuer
   Webhook*, **Webhook-URL kopieren**.
2. Im UI eintragen. Optional eine **Rollen-ID** — die wird dann bei
   SOFORT-Meldungen erwähnt, sonst nie. (Rollen-ID: Entwicklermodus in Discord
   einschalten, Rechtsklick auf die Rolle → *ID kopieren*.)

```bash
python cli.py kanaele hinzufuegen discord "Server" \
  --set url=https://discord.com/api/webhooks/... --set rolle=123456789
```
</details>

<details>
<summary><strong>Slack</strong> — Team-Kanal</summary>

1. <https://api.slack.com/apps> → *Create New App* → *From scratch*.
2. *Incoming Webhooks* aktivieren → *Add New Webhook to Workspace* → Kanal
   wählen → **URL kopieren**.

```bash
python cli.py kanaele hinzufuegen slack "Team" \
  --set url=https://hooks.slack.com/services/...
```
</details>

<details>
<summary><strong>Matrix</strong> — eigener Homeserver, nichts verlässt deine Infrastruktur</summary>

1. Einen Bot-Account anlegen und dessen **Zugangstoken** holen (in Element:
   *Einstellungen → Hilfe & Info → Erweitert → Zugangstoken*).
2. Den Bot in den Zielraum einladen und beitreten lassen.
3. **Raum-ID** kopieren (*Raumeinstellungen → Erweitert*) — beginnt mit `!`,
   nicht die `#alias:server`-Form.

```bash
python cli.py kanaele hinzufuegen matrix "Heim-Raum" \
  --set homeserver=https://matrix.example.org \
  --set token=syt_... --set raum='!abc123:example.org'
```
</details>

<details>
<summary><strong>Gotify</strong> — selbst gehosteter Push</summary>

In Gotify eine **Anwendung** anlegen (*Apps → Create Application*) und deren
Token übernehmen. Server-URL ohne abschließenden Schrägstrich.

```bash
python cli.py kanaele hinzufuegen gotify "Push" \
  --set server=https://gotify.example.org --set token=A1b2C3...
```
</details>

<details>
<summary><strong>Pushover</strong> — Push auf iOS/Android, ohne eigenen Server</summary>

Auf <https://pushover.net> anmelden: der **Benutzerschlüssel** steht auf der
Startseite, den **Anwendungs-Token** bekommst du über *Create an
Application/API Token*.

```bash
python cli.py kanaele hinzufuegen pushover "Handy" \
  --set token=aTokenHier --set user=uSchluesselHier
```
</details>

<details>
<summary><strong>ntfy</strong> — Push ohne Konto</summary>

Nur ein **Topic** ausdenken (rate schwer, sonst liest es jemand mit) und die
ntfy-App auf dasselbe Topic abonnieren. Eigene Instanz? Server-URL anpassen.

```bash
python cli.py kanaele hinzufuegen ntfy "Handy" --set topic=sparbit-4f3a9c
```
</details>

<details>
<summary><strong>E-Mail</strong> — Archiv und Mailclient-Filter</summary>

SMTP-Zugang deines Anbieters. Bei Gmail ein **App-Passwort** verwenden, nicht
das Kontopasswort.

```bash
python cli.py kanaele hinzufuegen smtp "Postfach" \
  --set host=smtp.example.com --set port=587 \
  --set username=ich@example.com --set password=geheim \
  --set from_addr=ich@example.com --set to_addr=ich@example.com
```
</details>

<details>
<summary><strong>Webhook</strong> — Home Assistant, n8n, eigene Skripte</summary>

Bekommt den Treffer als JSON: Titel, URL, Preis, Originalpreis, Rabatt,
Händler, Quelle, Regel, Tags, `ist_gratis`, `prioritaet`, `urteil` und
`deal_id`. Eine Discord-URL wird hier weiterhin erkannt — für Discord ist der
eigene Kanal oben aber schöner.

```bash
python cli.py kanaele hinzufuegen webhook "n8n" --set url=https://n8n.local/hook/deal
```
</details>

---

## Kommandozeile

`cli.py` steuert dieselbe Datenbank wie die Oberfläche — **auch wenn der Server
gerade aus ist**. Änderungen an Quellen übernimmt ein laufender Server
innerhalb einer Minute, ohne Neustart.

```bash
python cli.py status                      # Überblick
python cli.py kanaele typen               # alle 9 Kanäle mit ihren Feldern
python cli.py quellen liste
python cli.py regeln liste
python cli.py deals lego --anzahl 10
```

| Bereich | Befehle |
|---|---|
| `kanaele` | `typen`, `liste`, `hinzufuegen <typ> <name> --set k=v`, `aendern <id>`, `loeschen <id>`, `testen [id]` |
| `quellen` | `liste`, `an <quelle>`, `aus <quelle>`, `intervall <quelle> <minuten>`, `testen [quelle]`, `jetzt <quelle>` |
| `regeln` | `liste`, `hinzufuegen <name> [Optionen]`, `an`, `aus`, `loeschen`, `testen <id>` |
| `wunschliste` | `liste`, `hinzufuegen <url> --ziel 199`, `entfernen <id>`, `pruefen [id]` |
| `preisfehler` | `liste [--tage 7] [--nur-belegt]`, `pruefen`, `waechter --an/--aus --schwelle 70` |
| `deals` | `[suchbegriff] --gratis --urteil bestpreis --anzahl 20` |

Ein paar Beispiele:

```bash
# Kanal anlegen und sofort ausprobieren
python cli.py kanaele hinzufuegen ntfy "Handy" --set topic=sparbit-4f3a9c
python cli.py kanaele testen

# Quelle einschalten und einmalig laufen lassen
python cli.py quellen an mydealz
python cli.py quellen intervall mydealz 15
python cli.py quellen jetzt mydealz

# Regel bauen und gegen die letzten Deals gegenprüfen
python cli.py regeln hinzufuegen "Alles Gratis" --gratis --sofort --kanal 1
python cli.py regeln hinzufuegen "Lego" --keyword lego --max-preis 49.99 \
  --min-rabatt 30 --blacklist gebraucht --kanal 1
python cli.py regeln testen 2 --anzahl 500

# Preisfehler ansehen und den Wächter empfindlicher stellen
python cli.py preisfehler liste --nur-belegt
python cli.py preisfehler waechter --an --schwelle 60
```

`regeln testen` zeigt dieselbe Vorschau wie das UI: wie viele der letzten Deals
die Regel getroffen hätte, mit Beispielen und den knapp verfehlten.

Die CLI meckert früh statt spät: fehlende Pflichtfelder, vertippte Feldnamen
(`--set urll=…`), Regeln ohne Bedingung und Stichworte, die zugleich auf der
Blacklist stehen, werden abgelehnt — nicht klaglos gespeichert. Bei einem
Tippfehler im Quellennamen schlägt sie die richtige vor.

Die CLI benutzt automatisch die von `run.py` angelegte `.venv` — `python
cli.py …` genügt, egal mit welchem Python du sie startest.

> Die CLI kennt kein eigenes Passwort. Wer die Datei `data/sparbit.db` lesen
> kann, hat ohnehin Zugriff auf alles — ein zweites Passwort davor wäre nur
> Theater.

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
[`deploy/Caddyfile`](deploy/Caddyfile) sind fertig dabei.

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

---

## Entwicklung

```bash
python run.py --dev              # Backend mit Auto-Neuladen
cd frontend && npm run dev       # Oberfläche separat, mit Hot-Reload
cd backend && pytest tests/ -q   # 390 Tests, ohne Netzwerk
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

---

## Bekannte Lücken

Ehrlich benannt statt verschwiegen:

* **Kein Endpoint ist vorab verifiziert.** Siehe [ENDPOINTS.md](ENDPOINTS.md) —
  der erste Schritt ist `python -m tools.verify_endpoints`.
* **Die Preisfehler-Erkennung ist nicht gegen echte Funde geeicht.** Die
  Gewichte sind begründet, aber am Schreibtisch gewählt und gegen
  konstruierte Fälle getestet — nicht an einem Jahr echter mydealz-Daten
  kalibriert. Rechne in den ersten Wochen mit Fehlalarmen und stell die
  Schwelle nach.
* **Fremdpreise braucht es erst.** Das stärkste Indiz nach der Kommastelle ist
  der Vergleich mit anderen Quellen — den gibt es nur, wenn mehrere Quellen
  denselben Artikel melden. Mit einer eingeschalteten Quelle bleibt der
  Detektor auf den eigenen Verlauf angewiesen.
* **Der Claimer hat keinen Startknopf.** Die Claimer-Seite zeigt den Befehl zum
  Abtippen, statt den Container selbst zu starten.
* **Sechs Quellen fehlen bewusst** — itch.io, Indiegala, Fanatical, Humble,
  Unreal/FAB und Kleinanzeigen hätten HTML-Scraping erfordert. Gründe und
  Alternativen stehen in [ENDPOINTS.md](ENDPOINTS.md).

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
