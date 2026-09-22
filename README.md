# SparBit

**Findet Preisfehler, bevor sie korrigiert sind.**

Ein Preisfehler ist kein Rabatt. Es ist ein Versehen des Händlers — eine
verrutschte Kommastelle, eine vergessene Null. Der Fernseher für 899 € steht
plötzlich für 89,90 € drin, und zwanzig Minuten später nicht mehr.

SparBit beobachtet dafür rund um die Uhr 15 Deal-Quellen, vergleicht jeden
Preis mit dem **eigenen beobachteten Verlauf** und mit dem, was andere Quellen
für denselben Artikel verlangen — und weckt dich, wenn etwas nicht
zusammenpasst. Mit Begründung, nicht mit einer Punktzahl.

Nebenbei macht es das, was ein Deal-Monitor sonst so macht: Gratis-Spiele
einsammeln, Wunschlisten überwachen, nach deinen Regeln filtern und über elf
Kanäle melden — bis hin zu Push direkt in den Browser.

![Lizenz](https://img.shields.io/badge/Lizenz-MIT-blue) ![Python](https://img.shields.io/badge/Python-3.11+-3776ab) ![React](https://img.shields.io/badge/React-18-61dafb) ![Tests](https://img.shields.io/badge/Tests-848-22c55e)

**Auf einem VPS** — ein Befehl, inklusive Docker, HTTPS, Zertifikat und
Update-Knopf im UI:

```bash
curl -fsSL https://raw.githubusercontent.com/StrikerLUL/spar_bit/refs/heads/main/install.sh | bash
```

**Auf dem eigenen Rechner** — kein Docker, keine Konfigurationsdatei:

```bash
git clone https://github.com/StrikerLUL/spar_bit.git
cd spar_bit
python run.py
```

Python 3.11 genügt. Node.js ist optional: fehlt es, holt sich `run.py` die
fertig gebaute Oberfläche aus dem letzten Release (mit Prüfsumme).

---

## So sieht es aus

| | |
|---|---|
| ![Feed](docs/bilder/feed.png) | ![Preisfehler](docs/bilder/preisfehler.png) |
| **Feed** — jeder Deal mit Urteil aus dem eigenen Verlauf, Gratis-Funde mit Gegenprobe | **Preisfehler** — mit Begründung, nicht mit einer Punktzahl |
| ![Regeln](docs/bilder/regeln.png) | ![Statistiken](docs/bilder/statistiken.png) |
| **Regeln** — die Live-Vorschau sagt beim Bauen, wie viele der letzten 500 Deals getroffen worden wären | **Bilanz** — was das Ganze gebracht hat, gerechnet gegen den eigenen Verlauf statt gegen die UVP |

---

## Dokumentation

Dieses README ist der Einstieg. Alles Weitere steht daneben — sortiert nach
dem, was man gerade sucht:

| Seite | Worum es geht |
|---|---|
| **[Preisfehler](docs/preisfehler.md)** | Wie die Erkennung urteilt, was sie *nicht* meldet, und wie du sie eichst |
| **[Was SparBit kann](docs/funktionen.md)** | Quellen, Urteile, Regeln, Wunschliste, Gratis-Gegenprobe, 18+-Bereich |
| **[Betrieb](docs/betrieb.md)** | VPS, eigener Rechner, Reverse-Proxy, Updates, Auto-Claimer |
| **[Benachrichtigungen](docs/benachrichtigungen.md)** | Telegram, Discord, Matrix, ntfy, Web Push, Apprise und der Rest |
| **[Kommandozeile & API](docs/kommandozeile.md)** | Alles, was die Oberfläche kann, geht auch ohne sie |
| **[Entwicklung](docs/entwicklung.md)** | Aufbau, eigene Quellen, eigene Kanäle, Tests |
| **[Sicherheit & Problemlösung](docs/sicherheit.md)** | Was geschützt ist, was nicht, und was zu tun ist, wenn es klemmt |
| **[ENDPOINTS.md](ENDPOINTS.md)** | Welche Quelle welchen Endpunkt nutzt — und welche ungeprüft ist |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Wie hier gearbeitet wird |

> **Vor dem ersten Start: [ENDPOINTS.md](ENDPOINTS.md) lesen.**
> Kein Quellen-Endpoint konnte beim Bauen live geprüft werden — die
> Build-Umgebung hatte keinen Netzzugang zu den Deal-Seiten. Alle Quellen
> starten als *ungeprüft*; ein Befehl bzw. ein Knopf im UI verifiziert sie auf
> deinem Rechner. Das ist Absicht: lieber ehrlich ungeprüft als falsch
> „funktioniert".

---

## In Kürze

**Finden** — 15 Quellen als Plugins (Deal-Communities, Reddit, Gaming-Stores,
eigene RSS-Feeds, eigene JSON-Schnittstellen), dazu eine Wunschliste, die
Artikel selbst beobachtet, statt auf Posts zu warten. Steam-Wunschlisten lassen
sich übernehmen, Feedreader-Listen per OPML einlesen.

**Zusammenführen** — derselbe Artikel aus vier Quellen kommt einmal an. Wo eine
Produktkennung in der Adresse steht (ASIN, Steam-AppID, GTIN), wird nicht mehr
geraten, sondern gewusst.

**Beurteilen** — der Rabatt der Quelle sagt wenig, weil er gegen eine UVP
rechnet, die nie jemand bezahlt hat. SparBit urteilt aus dem eigenen
Preisverlauf: *Bestpreis*, *sehr gut*, *war günstiger*, *UVP fragwürdig* — und
sagt „zu wenig Daten", statt zu raten.

**Filtern** — Regeln aus Keywords, Preisgrenzen, Mindestrabatt, Preisurteil und
Preisfehler-Punktzahl, mit Live-Vorschau und Begründung je Deal. Der Feed lernt
mit, lokal und erklärbar. Regeln lassen sich exportieren und weitergeben.

**Melden** — elf Kanäle: Telegram, Discord, Slack, Matrix, ntfy, Gotify,
Pushover, E-Mail (auch als HTML), Webhook, **Web Push direkt in den Browser**
und **Apprise** für alles Weitere (Signal, Home Assistant, Mastodon …). Dazu
Ruhezeiten, Sammelmeldungen und eine Erinnerung, bevor ein Angebot ausläuft.

**Nicht verpassen** — Angebote mit Frist landen auf Wunsch als
abonnierbarer Kalender im Handy, mit Erinnerung sechs Stunden vorher.

**Im Haushalt** — mehrere Konten mit eigenen Regeln, Kanälen und
Wunschlisten. Quellen und gesammelte Deals bleiben gemeinsam.

**Für dich behalten** — alles läuft auf deinem Rechner. Kein Konto, keine
Telemetrie, keine Cloud. Deal-Bilder werden lokal zwischengespeichert, damit
der Händler beim Blättern nicht deine IP sieht.

---

## Die ersten 10 Minuten

**1. Einen Kanal einrichten — zuerst.** Unter *Kanäle* → **Kanal hinzufügen**.
Ohne Kanal meldet sich SparBit nie, auch nicht bei einem Preisfehler; es
sammelt dann nur still vor sich hin. Neun Kanäle stehen zur Wahl, beliebig
viele parallel:

* **Desktop-Meldungen** — einschalten, einmal erlauben, fertig. Kein Bot,
  kein Token. Funktioniert nur, solange der Browser offen ist.
* **Telegram, Discord, Slack, Matrix, Gotify, Pushover, ntfy, E-Mail,
  Webhook** — [siehe unten](docs/benachrichtigungen.md). Für einen
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

---

## Sicherung

SparBit schreibt täglich eine Sicherung nach `data/backups` und hält die
letzten sieben. Sie enthält alles, was nicht nachwächst: Regeln, Kanäle,
Quellen-Einstellungen, Wunschlisten, Preisverlauf, gelernte Vorlieben und
gespeicherte Suchen. Mit einem Passwort wird sie verschlüsselt (AES-256) —
sie enthält Bot-Token und Passwort-Hashes.

Einspielen ersetzt die Konfiguration und **ergänzt** die Daten: was seit der
Sicherung dazugekommen ist, bleibt stehen.

---

## Bekannte Lücken

Ehrlich benannt statt verschwiegen — die vollständige Liste steht in
[docs/sicherheit.md](docs/sicherheit.md#bekannte-lücken). Die wichtigsten:

* **Kein Endpoint ist vorab verifiziert.** Erster Schritt:
  `python -m tools.verify_endpoints`.
* **Die Preisfehler-Erkennung startet ungeeicht.** Sie lernt aus deinen
  Rückmeldungen und schlägt eine Schwelle vor; übernommen wird sie erst auf
  Knopfdruck.
* **Die Gratis-Gegenprobe ist nur so gut wie die Zielseite.** Shops, die ihren
  Preis per JavaScript nachladen, ergeben `ungeprüft` — und dann bleibt alles,
  wie die Quelle es gemeldet hat.
* **Die 18+-Quellen sind ungeprüft wie alle anderen.** Ein falscher Pfad heilt
  sich inzwischen selbst, aber die vorbelegten Namen sind geraten.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
