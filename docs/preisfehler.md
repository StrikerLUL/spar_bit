# Preisfehler

Der Teil, der am meisten bringt und am leichtesten danebenliegt.

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

![Der Wächter nennt seine Indizien — jedes einzeln nachvollziehbar](bilder/preisfehler.png)

*Der Wächter nennt seine Indizien — jedes einzeln nachvollziehbar.*


---

[← Zurück zur Übersicht](../README.md)
