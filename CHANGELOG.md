# Änderungen

Was sich für dich ändert, nicht welche Datei angefasst wurde. Neues steht
oben.

Das Format folgt lose [Keep a Changelog](https://keepachangelog.com/de/1.1.0/);
die Versionen folgen [SemVer](https://semver.org/lang/de/). Wer mit dem
Update-Knopf im UI arbeitet, liest hier, was der nächste Klick bringt.

## Unveröffentlicht

### Behoben

* **Wechselkurse alterten still.** Sie standen als feste Werte im Code. Eine
  Regel „max. 20 €" greift bei USD-, GBP- oder AUD-Angeboten damit von Jahr
  zu Jahr weiter daneben, ohne dass irgendwo etwas rot wird — der einzige
  Fehler in dieser Anwendung, der sich nie von selbst meldet. Sie kommen
  jetzt täglich von der EZB (eine Datei, kein Schlüssel, abschaltbar), und
  ihr Alter steht im UI, in `/api/health` und in den Metriken.
* **`PUT /api/settings` hing am Router statt an einer Rolle.** Damit konnte
  ein **Gast**, der laut Beschreibung nur zusehen darf, die Währungskurse der
  ganzen Anlage ändern, die Preisfehler-Schwelle verstellen und das Passwort
  der Sicherungen setzen. Dasselbe galt für Bilder-Aufräumen, Quellen-Snooze
  und die Schwellenübernahme. Alle vier sind jetzt Admin-Sache; Preisalarm
  und Preisfehler-Rückmeldung verlangen mindestens ein Mitglied.
* **Die Volltextsuche fiel auf PostgreSQL stillschweigend auf `LIKE` zurück.**
  Die dokumentierte Suchsyntax funktionierte genau dann nicht, wenn jemand die
  ebenfalls dokumentierte Postgres-Option nutzte. Derselbe Parser übersetzt
  jetzt in `tsquery`, mit GIN-Index.
* **`timeAgo` bildete die Mehrzahl selbst.** Über `Intl.RelativeTimeFormat`
  stimmt sie jetzt auch in der zweiten Sprache — und sagt „vorgestern" statt
  „vor 2 Tagen".

### Neu

* **„Warum kam das nicht an?"** — die Gegenrichtung zur Live-Vorschau im
  Regel-Editor. In der Detailansicht jedes Deals läuft derselbe Weg ab, den
  die Zustellung nimmt: 18+-Sperre, Regeln, Preisfehler-Weg, Pause, Ruhezeit,
  Kanäle, Versandverlauf. Jede Stufe sagt, ob sie durchlässt, und wenn nicht:
  warum und was dagegen zu tun wäre. Auch auf der Kommandozeile:
  `sparbit diagnose <nr>`.
* **Zweite Sprache (Englisch).** Navigation, Anmeldung, Deal-Karten,
  Preisurteile und die gemeinsamen Bedienelemente. Zahlen, Daten und Dauern
  folgen der Sprache — vorher hing alles fest auf `de-DE`, und „1.299,00"
  liest sich englisch als ein Tausendstel. Umschalten unten links.
  Die Einstellungsseiten sind noch deutsch; `docs/entwicklung.md` sagt, wie
  man weitermacht.
* **Warengruppen.** Was ein Fund *ist* (Elektronik, Haushalt, Werkzeug …),
  nicht nur, aus welcher Art Quelle er kam. Aus Stichwörtern, also
  nachvollziehbar: im UI steht das Wort, das die Einteilung ausgelöst hat.
  Neuer Filter im Regel-Editor, neuer Block in den Statistiken, neuer Befehl
  `sparbit warengruppen`. Optional darf ein **lokales Ollama** die Reste
  einteilen, die kein Stichwort erwischt — aus, bis du es einschaltest.
* **Gutschein-Codes** aus dem Deal-Text, auf der Karte und in der Meldung.
  Vorher standen sie im Fließtext, und der wird gekürzt — ausgerechnet das
  Stück, das man an der Kasse braucht.
* **Versandkosten** in der Wunschliste, aus den strukturierten Daten des
  Shops. 195 € plus 9,90 € sind teurer als 199 € versandkostenfrei. „Keine
  Angabe" und „kostenlos" bleiben dabei zwei verschiedene Dinge.
* **Home Assistant über MQTT**, mit Auto-Discovery: der Sensor erscheint
  drüben von selbst, mit Preis, Urteil, Link und Bild als Attribute. Kein
  Basteln mit dem Webhook-JSON mehr.
* **Zwei neue Quellen:** Slickdeals (US) und OzBargain (AU). Beide rechnen in
  ihrer eigenen Währung; OzBargain ist wegen der Zeitzone oft die erste
  Quelle, die einen weltweiten Preisfehler meldet.
* **Zweiter Faktor als Pflicht für Administratoren** (abschaltbar, Vorgabe
  aus). Gesperrt werden nur die Admin-Funktionen — anmelden und den zweiten
  Faktor einrichten geht weiter, sonst wäre es eine Aussperrung statt einer
  Hürde.
* **Bremse für die Endpunkte, die nach draußen greifen** („Quelle testen",
  Feed-Suche, Sammeleingabe, Kanal-Test). Ein Aufruf hier löst mehrere Abrufe
  bei einem fremden Shop aus; ohne Bremse wird SparBit zum Verstärker, und
  gesperrt wird am Ende die IP deines Servers.
* **Render-Dienst für die Wunschliste** (optional): Shops, die ihren Preis
  erst per JavaScript einsetzen, lassen sich über browserless oder einen
  eigenen Playwright-Container lesen. Kein Browser im Image — wer ihn will,
  stellt ihn daneben.
* **Worker-Betrieb:** der Scheduler kann als eigener Dienst laufen
  (`SPARBIT_SCHEDULER=aus` plus `--profile worker`). Der Live-Ticker geht
  dabei weiter; der Worker spiegelt seine Ereignisse über die Datenbank.
* **Grafana-Dashboard** unter `deploy/grafana/`, mit den Alarmen, die sich
  lohnen. Neue Metriken: Zustellung je Kanal und das Alter der Kurse.

### Betrieb

* **Fertige Images in der GitHub-Registry.** Bisher baute jeder VPS bei jedem
  Update beide Images selbst — Minuten, RAM und Build-Werkzeug auf einer
  Maschine, die eigentlich nur Deals einsammeln soll. Der Auto-Updater zieht
  jetzt das Image zu genau dem Commit, den er ausgecheckt hat, und baut nur,
  wenn es keines gibt (eigener Commit, eigener Fork). Für `amd64` und
  `arm64`, signiert, mit Stückliste und Herkunftsnachweis.
* **Neue Migrationen 9–12:** Versandkosten, Gutschein-Codes, Warengruppen
  (rückwirkend eingeteilt), Warengruppen-Filter, Render-Schalter.
* **Neue Einstellungen:** `SPARBIT_BEZUG`, `SPARBIT_TAG`, `SPARBIT_SCHEDULER`
  — alle mit Vorgaben, die den bisherigen Betrieb unverändert lassen.
* **Die Install-Zeile im README zeigte auf einen Branch, den es nicht gibt**
  (`refs/heads/main`) — ein 404, und `curl | bash` tut dann einfach nichts.
  Jetzt `HEAD`: immer der Standard-Branch, auch nach einer Umbenennung.
  Dieselbe Falle steckte in den Workflows für Images und CodeQL: ein fest
  eingetragenes `main` ließ sie stillschweigend nie laufen. Sie prüfen den
  Standard-Branch jetzt zur Laufzeit.

### Für Mitwirkende

* **1068 Backend-Tests** (vorher 849), Abdeckung 75 % → 80 %, Schwelle auf 78.
  Neu getestet: Telegram-Bot (vorher null Tests), API-Token,
  Berechtigungsmatrix über alle anlagenweiten Endpunkte.
* **61 Tests für die Oberfläche** (vorher null) plus ein Durchstich im echten
  Browser (Playwright, echtes Backend, Wegwerf-Datenbank).
* **Der API-Client wird gemessen.** Das OpenAPI-Schema erzeugt Typen,
  `api-vertrag.ts` behauptet auf Typ-Ebene, dass der handgeschriebene Client
  dazu passt, und die CI prüft, dass die Typen aktuell sind.
* **System.tsx (1355 Zeilen) und Rules.tsx (981) sind aufgeteilt** — dieselben
  Bauteile, nur auffindbar.
* CodeQL, Dependabot, `pip-audit`, `npm audit`, Diff-Coverage, Dev-Container,
  Commit-Haken, Issue- und PR-Vorlagen.

---

## 1.0.0

Der Stand, mit dem SparBit öffentlich wurde: 15 Quellen, Preisfehler-Wächter
mit acht Indizien, Regeln mit Live-Vorschau, elf Meldekanäle, Wunschliste mit
eigener Preisbeobachtung, Mehrbenutzer, 18+-Bereich, Ein-Befehl-Installer.

Siehe [README.md](README.md) für den vollen Umfang.
