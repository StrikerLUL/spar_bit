# Sicherheit

## Eine Lücke melden

**Bitte kein öffentliches Issue.** Melde sie über *Security → Report a
vulnerability* im GitHub-Repository oder per Mail an die im Profil
hinterlegte Adresse.

Sinnvoll in der Meldung: was passiert, was passieren sollte, und wie es sich
nachstellen lässt. Ein Proof of Concept hilft mehr als eine Einschätzung des
Schweregrads.

## Was SparBit annimmt

SparBit ist für den Betrieb hinter einer Anmeldung gebaut — auf dem eigenen
Rechner oder auf einem VPS mit HTTPS davor. Die Annahmen:

* **Wer angemeldet ist, darf seine eigenen Daten verwalten.** Trennung
  zwischen Konten gibt es (Regeln, Kanäle, Wunschlisten, gelernte
  Vorlieben); sie ist gegen Versehen gebaut, nicht gegen einen Angreifer im
  selben Haushalt.
* **Ein Administrator darf die Anlage verwalten.** Quellen, Konten,
  Sicherungen, Updates. Ein Admin kann Sicherungen herunterladen, und die
  enthalten die Geheimnisse aller Konten.
* **Der Server ist nicht öffentlich.** Es gibt keine Registrierung, keine
  Passwort-vergessen-Mail und keine Mandantentrennung im Sinne eines
  Mehrmandanten-Dienstes.

## Was eingebaut ist

| Schutz | Wogegen |
|---|---|
| argon2 für Passwörter | Ausgelesene Datenbank |
| Anmeldebremse, in der Datenbank | Durchprobieren, auch über Neustarts hinweg |
| Zweiter Faktor (TOTP, RFC 6238) | Wiederverwendete Passwörter aus fremden Datenlecks |
| Signiertes Session-Cookie, `httponly`, `samesite=lax` | Diebstahl per JavaScript, einfache CSRF |
| Netzschutz vor jedem ausgehenden Abruf | SSRF — auch über Weiterleitungen (siehe unten) |
| Obergrenze beim Lesen, auf entpackte Bytes | Zip-Bomben, endlose Antworten |
| Content-Security-Policy und Kopfzeilen | Eingeschleuste Skripte, Framing |
| Prüfung beim Entpacken des Release-Archivs | Präparierte Archive (`../`, Symlinks) |
| Verschlüsselte Sicherungen (AES-256-GCM, scrypt) | Sicherungsdatei in fremden Händen |
| API-Token einzeln zurückziehbar | Verlorenes Gerät |

### Netzschutz im Detail

SparBit ruft Adressen ab, die man ihm nennt: Feeds, Produktseiten,
Kandidaten der Feed-Suche. Jede wird vor dem Verbindungsaufbau aufgelöst und
geprüft; Ziele in `127.0.0.0/8`, privaten Netzen, Link-Local
(`169.254.169.254` — Cloud-Metadaten) und reservierten Bereichen werden
abgelehnt. Die Prüfung hängt am HTTP-Client und greift darum **auch bei
jeder Weiterleitung**, die erst dort entsteht.

Zwei Ausnahmen mit Absicht: Benachrichtigungs-Kanäle dürfen ins eigene Netz
(ein Gotify unter `192.168.x.x` ist der Normalfall, und die Adresse hat man
selbst eingetragen), und `SPARBIT_ERLAUBE_PRIVATE_ZIELE=true` schaltet die
Prüfung ganz ab.

## Was nicht geschützt ist

Ehrlich benannt:

* **Kein CSRF-Token.** Der Schutz ist `samesite=lax` plus die Tatsache, dass
  alle schreibenden Aufrufe JSON-Bodies mit `Content-Type: application/json`
  verwenden. Für einen öffentlich erreichbaren Mehrbenutzer-Dienst wäre das
  zu wenig.
* **Plugins laufen mit allen Rechten.** Was in `SPARBIT_PLUGIN_DIR` liegt,
  ist Code, der beim Start ausgeführt wird. Das ist kein Versehen — eine
  halbe Sandkiste wäre ein Versprechen, das sie nicht halten kann.
* **Sicherungen enthalten Geheimnisse.** API-Schlüssel, Bot-Token,
  Passwort-Hashes. Ohne Passwort liegen sie im Klartext in der Datei.
* **Die 18+-Trennung ist eine Ablage, kein Jugendschutz.** Sie verhindert,
  dass solche Funde zwischen den normalen Karten auftauchen — mehr nicht.

## Abhängigkeiten

Untergrenzen in `backend/requirements.txt` sind die getesteten Versionen,
Obergrenzen die nächste Hauptversion. Zwei Pakete sind optional und werden
zur Laufzeit geprüft: `Pillow` (verkleinert zwischengespeicherte Bilder),
`cryptography` (verschlüsselte Sicherungen, Web Push). Fehlt eines, läuft
SparBit weiter und sagt, was dadurch aus ist.
