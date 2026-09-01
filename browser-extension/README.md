# SparBit Browser-Erweiterung

Setzt Artikel von jeder Shop-Seite aus auf die SparBit-Wunschliste und zeigt
dir, wenn SparBit denselben Artikel schon günstiger kennt.

## Einrichten (2 Minuten)

**1. Zugangsschlüssel holen.** In SparBit unter *Logs & System →
Browser-Erweiterung* auf **Neuen Schlüssel anlegen**. Der Schlüssel wird
genau einmal angezeigt — gleich kopieren.

**2. Erweiterung laden.**

*Chrome, Edge, Brave:*
1. `chrome://extensions` öffnen
2. **Entwicklermodus** oben rechts einschalten
3. **Entpackte Erweiterung laden** → diesen Ordner auswählen

*Firefox:*
1. `about:debugging#/runtime/this-firefox` öffnen
2. **Temporäres Add-on laden** → `manifest.json` in diesem Ordner auswählen
3. Firefox entfernt temporäre Add-ons beim Neustart. Dauerhaft geht es nur
   signiert über addons.mozilla.org.

**3. Verbinden.** Auf das SparBit-Symbol in der Symbolleiste klicken, Adresse
(Vorgabe `http://localhost:8000`) und Schlüssel eintragen, **Verbinden**.

## Benutzen

Auf einer Produktseite auf das Symbol klicken. Die Erweiterung zeigt:

* den **erkannten Preis** und woraus sie ihn gelesen hat
* ob **SparBit den Artikel schon kennt** — und ob er dort günstiger ist
* ein Feld für den **Zielpreis**

Ein Klick auf *Auf die Wunschliste*, fertig. SparBit beobachtet den Artikel
dann selbst und meldet sich, wenn der Preis fällt.

## Wenn kein Preis erkannt wird

Die Erweiterung liest **strukturierte Daten** — JSON-LD nach schema.org, Open
Graph oder Microdata. Das sind dieselben Angaben, die Shops für Suchmaschinen
ausliefern, und der stabile Teil einer Produktseite: CSS-Klassen ändern sich
bei jedem Redesign, `"@type": "Product"` nicht.

Liefert eine Seite davon nichts, sagt die Erweiterung das klar, statt einen
brüchigen Selektor zu raten. Ein Preiswächter, der still den falschen Wert
liest, wäre schlimmer als gar keiner.

## Warum ein eigener Schlüssel?

Die Erweiterung läuft auf fremden Seiten und kann das Sitzungs-Cookie von
SparBit dort nicht mitschicken. Der Schlüssel lässt sich einzeln zurückziehen
— wenn ein Rechner abhandenkommt, musst du nicht dein Passwort ändern.

Alle Aufrufe laufen über den Hintergrundprozess der Erweiterung. Der hat die
Host-Berechtigung und umgeht damit CORS — du musst deine SparBit-Instanz also
nicht nach außen öffnen.

## Andere Adresse als localhost

Läuft SparBit woanders (anderer Rechner im Heimnetz, eigene Domain), musst du
die Adresse in `manifest.json` unter `host_permissions` ergänzen und die
Erweiterung neu laden:

```json
"host_permissions": ["http://localhost/*", "http://127.0.0.1/*",
                     "http://192.168.1.50/*"]
```

## Dateien

| Datei | Zweck |
|---|---|
| `manifest.json` | Manifest V3, Chrome und Firefox |
| `content.js` | liest die Produktdaten aus der Seite |
| `background.js` | spricht mit SparBit (hat die Host-Berechtigung) |
| `popup.html/js/css` | die Oberfläche |
| `lib.js` | Gemeinsames: Einstellungen, API-Aufrufe |
