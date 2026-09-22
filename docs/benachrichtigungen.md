# Benachrichtigungen

Welche Kanaele es gibt und wie man sie einrichtet.

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


## Push direkt in den Browser

Der Kanal ohne Konto und ohne fremden Dienst in der Mitte. Unter *Kanäle →
Push aufs Gerät* einmal „Dieses Gerät anmelden" drücken, dann einen Kanal vom
Typ **Browser (Web Push)** anlegen — fertig.

Die Meldung kommt an, auch wenn SparBit gar nicht offen ist. Auf dem iPhone
muss die Seite dafür zum Home-Bildschirm hinzugefügt sein; das ist eine
Vorgabe von Apple, keine von SparBit.

Der Inhalt ist verschlüsselt (aes128gcm nach RFC 8291), die Herkunft
signiert (VAPID nach RFC 8292). Google und Mozilla leiten die Nachricht
weiter, erfahren aber nicht, welcher Deal drinsteht. Das Schlüsselpaar
entsteht beim ersten Anmelden und gehört der Installation.

Ein Gerät, das der Push-Dienst mit 404 oder 410 beantwortet (Browser
deinstalliert, Berechtigung entzogen), wird gleich entfernt — sonst sammeln
sich Karteileichen, an die jede Meldung vergeblich geht.

## Apprise: über hundert weitere Dienste

Signal, Matrix-Brücken, Home Assistant, Mastodon, Teams, Zulip, SMS-Anbieter:
[Apprise](https://github.com/caronc/apprise/wiki) kennt sie alle über eine
Adresszeile. Der Kanal nimmt eine Adresse pro Zeile, so wie sie in der
Apprise-Doku steht:

```
signal://apphost:port/+4915112345678
mqtt://user:pass@broker:1883/sparbit/deals
mastodon://token@mastodon.social
```

Das Paket ist **nicht** Teil der Abhängigkeiten — im Container
`pip install apprise`, dann neu starten. Fehlt es, ist der Kanal sichtbar und
sagt das, statt in der Liste zu fehlen.

## E-Mail als HTML

Der SMTP-Kanal verschickt seit jeher Text. Bei einem einzelnen Fund geht das
in Ordnung; bei einer Sammelmeldung mit zwanzig Deals ist es eine Wand, in
der der Bestpreis genauso aussieht wie der Rest.

Mit dem Häkchen *Als HTML gestalten* kommt eine Tabelle mit Bildern und
hervorgehobenem Urteil — und der Textteil bleibt als Alternative erhalten.
Wer kein HTML anzeigt (oder nicht will), bekommt weiter genau das von vorher.

## Bevor etwas ausläuft

Angebote mit Frist melden sich noch einmal, etwa sechs Stunden vor Schluss —
aber nur, wenn sie dich etwas angehen: gemerkt, von einer Regel getroffen,
mit Preisalarm versehen oder gratis. Eine Erinnerung an jeden auslaufenden
Rabatt wäre in einer Woche stummgeschaltet.

Die Ruhezeit gilt auch hier: ein Angebot, das in sechs Stunden endet,
rechtfertigt keinen Weckruf um drei Uhr nachts.

## Fristen im Kalender

Unter *Logs & System → Fristen im Kalender* gibt es eine Adresse, die jeder
Kalender abonnieren kann (Apple, Google, Thunderbird). Jeder Termin bringt
eine Erinnerung sechs Stunden vorher mit.

Das Token steht in der Adresse, weil eine Kalender-App keinen
Authorization-Header mitschicken kann. Es ist ein eigenes, einzeln
zurückziehbares Token — wer die Adresse hat, sieht deine Fristen.

---

[← Zurück zur Übersicht](../README.md)
