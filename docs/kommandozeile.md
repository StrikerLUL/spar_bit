# Kommandozeile und API

Alles, was die Oberflaeche kann, geht auch ohne sie.

## Kommandozeile

`cli.py` steuert dieselbe Datenbank wie die Oberfläche — **auch wenn der Server
gerade aus ist**. Änderungen an Quellen übernimmt ein laufender Server
innerhalb einer Minute, ohne Neustart.

```bash
python cli.py status                      # Überblick
python cli.py kanaele typen               # alle 12 Kanäle mit ihren Feldern
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
| `feed-suche` | `<adresse>` — welche Feeds gibt diese Seite an? |
| `gratischeck` | `--an/--aus`, `--max-pro-lauf 12` |
| `18plus` | `--an --ich-bin-volljaehrig`, `--aus`, `--melden an/aus` |
| `deals` | `[suchbegriff] --gratis --urteil bestpreis --anzahl 20` |
| `diagnose` | `<nr>` — warum kam dieser Fund nicht an? |
| `warengruppen` | `[--tage 30]` — was hier anfällt, nach Ware sortiert |
| `kurse` | `[--jetzt] [--automatisch an/aus]` — Wechselkurse ansehen und holen |

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

# Gratis-Gegenprobe: Stand ansehen, enger stellen, abschalten
python cli.py gratischeck
python cli.py gratischeck --max-pro-lauf 6
python cli.py gratischeck --aus

# 18+-Bereich freischalten (ohne die Bestätigung passiert nichts)
python cli.py 18plus                       # Stand, ohne etwas zu ändern
python cli.py 18plus --an --ich-bin-volljaehrig
python cli.py quellen testen mydealz_erotik
python cli.py quellen an mydealz_erotik
python cli.py 18plus --melden an           # auch über die Kanäle
python cli.py 18plus --aus                 # Quellen stoppen, Funde ausblenden
```

`18plus --an` ohne `--ich-bin-volljaehrig` bricht ab, und
`quellen an mydealz_erotik` lehnt ab, solange der Bereich zu ist — die CLI
ist ausdrücklich keine Hintertür am Schalter vorbei. Bei ausgeschaltetem
Bereich taucht in `quellen liste` keine 18+-Quelle auf.

`regeln testen` zeigt dieselbe Vorschau wie das UI: wie viele der letzten Deals
die Regel getroffen hätte, mit Beispielen und den knapp verfehlten.

### Die drei neuen Befehle

```bash
# "Warum kam das nicht an?" - dieselbe Stufenliste wie im UI, nur auch dann
# zu haben, wenn der Server aus ist und man gerade herausfinden will, warum.
python cli.py deals lego --anzahl 5        # die Nummer heraussuchen
python cli.py diagnose 1234

# Was fällt hier eigentlich an - nach Ware, nicht nach Quelle?
python cli.py warengruppen --tage 90

# Wechselkurse: ansehen, holen, Automatik umstellen
python cli.py kurse                        # mit Datum und Alter
python cli.py kurse --jetzt                # sofort bei der EZB holen
python cli.py kurse --automatisch aus      # dann gilt, was im UI steht
```

`diagnose` gibt je Stufe ein Zeichen aus: ✓ durchgelassen, ✗ hier war Schluss,
und ein graues `·` für eine Stufe, die zwar stoppt, aber auf dem Weg dieses
Fundes gar nicht liegt. Bei einem gewöhnlichen Deal steht der Preisfehler-Weg
so da — richtig wäre ein Kreuz, nur führt es am Thema vorbei.

`kurse` färbt den Stand rot, sobald er älter als 90 Tage ist. Das ist der
einzige Fehler in SparBit, der sich sonst nie von selbst meldet: eine Regel
„max. 20 €" greift bei Fremdwährungen einfach ein bisschen daneben.

Die CLI meckert früh statt spät: fehlende Pflichtfelder, vertippte Feldnamen
(`--set urll=…`), Regeln ohne Bedingung und Stichworte, die zugleich auf der
Blacklist stehen, werden abgelehnt — nicht klaglos gespeichert. Bei einem
Tippfehler im Quellennamen schlägt sie die richtige vor.

Die CLI benutzt automatisch die von `run.py` angelegte `.venv` — `python
cli.py …` genügt, egal mit welchem Python du sie startest.

> Die CLI kennt kein eigenes Passwort. Wer die Datei `data/sparbit.db` lesen
> kann, hat ohnehin Zugriff auf alles — ein zweites Passwort davor wäre nur
> Theater.

## API-Keys (optional)

Ohne sie bleiben nur diese beiden Quellen aus, alles andere läuft.

| Dienst | Wo | Kosten |
|---|---|---|
| IsThereAnyDeal | <https://isthereanydeal.com/apps/my/> — App registrieren | kostenlos |
| GG.deals | <https://gg.deals/de/api/> — Zugang beantragen | für private Nutzung kostenlos |

Eintragen unter *Quellen → (Quelle) → Einstellungen*. Die Keys landen in der
Datenbank, nicht in einer Datei, und werden bei jeder Rückgabe maskiert.

---

[← Zurück zur Übersicht](../README.md)
