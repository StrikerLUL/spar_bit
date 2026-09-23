/* Startpunkte und Vorgaben fuer den Regel-Editor.
 *
 * Reine Daten, kein Verhalten - darum eine eigene Datei. Sie stehen
 * zugleich an zwei Stellen im Weg: beim Lesen des Editors (dort
 * interessiert sie niemanden) und beim Suchen einer Vorlage (dort
 * sucht man sie zwischen 900 Zeilen Formular).
 */
import type { RuleDraft } from "@/lib/api";

/** Startpunkte statt weisses Blatt. Jede Vorlage ist bewusst eng gefasst -
 *  lieber wenige gute Treffer als ein Kanal, den man nach zwei Tagen
 *  stummschaltet. */
export const VORLAGEN: Array<{ name: string; beschreibung: string; regel: Partial<RuleDraft> }> = [
  {
    name: "Alles Gratis",
    beschreibung: "Jeder 0-€-Fund, sofort. Der Klassiker zum Anfangen.",
    regel: { name: "Alles Gratis", nur_gratis: true, priority: "SOFORT" },
  },
  {
    name: "Gratis-Spiele",
    beschreibung: "Nur Gaming-Quellen, nur kostenlos.",
    regel: {
      name: "Gratis-Spiele", nur_gratis: true, priority: "SOFORT",
      sources: ["epic", "gog", "steam", "cheapshark", "itad", "reddit"],
    },
  },
  {
    name: "Preisfehler",
    beschreibung: "Belegte Preisfehler, sofort. Nutzt die Punktzahl aus dem "
      + "Verlauf statt eines Rabatt-Schwellwerts.",
    regel: {
      name: "Preisfehler", min_fehler_score: 70, priority: "SOFORT",
    },
  },
  {
    name: "Preisfehler-Verdacht",
    beschreibung: "Auch die unsicheren Fälle — mehr Treffer, mehr Fehlalarme.",
    regel: {
      name: "Preisfehler-Verdacht", min_fehler_score: 45, priority: "NORMAL",
    },
  },
  {
    name: "Starke Rabatte",
    beschreibung: "Ab 70 % reduziert, als stündliche Zusammenfassung.",
    regel: { name: "Starke Rabatte", min_rabatt_prozent: 70, priority: "NORMAL" },
  },
  {
    name: "Günstige Technik",
    beschreibung: "Beispiel für Keywords plus Preisgrenze — bitte anpassen.",
    regel: {
      name: "Günstige Technik", priority: "NORMAL", max_preis: 50,
      keywords: ["ssd", "kopfhörer", "monitor", "tastatur", "maus", "festplatte"],
      blacklist: ["gebraucht", "defekt", "b-ware"],
    },
  },
];

/* Die Warengruppen, wie sie backend/app/warengruppe.py kennt.
 * Bewusst von Hand gespiegelt statt ueber einen weiteren Endpunkt
 * geholt: es sind zwoelf feste Werte, die sich mit dem Backend aendern -
 * und ein Ladezustand fuer eine Liste, die nie leer ist, waere Ballast.
 * Weicht sie ab, faellt es sofort auf: die Knoepfe treffen dann nichts. */
export const WARENGRUPPEN: Array<{ id: string; label: string }> = [
  { id: "elektronik", label: "Elektronik" },
  { id: "computer", label: "Computer & Zubehör" },
  { id: "gaming", label: "Gaming" },
  { id: "haushalt", label: "Haushalt & Küche" },
  { id: "werkzeug", label: "Werkzeug & Garten" },
  { id: "kleidung", label: "Kleidung & Schuhe" },
  { id: "drogerie", label: "Drogerie & Gesundheit" },
  { id: "lebensmittel", label: "Lebensmittel & Getränke" },
  { id: "spielzeug", label: "Spielzeug" },
  { id: "medien", label: "Bücher, Filme & Musik" },
  { id: "software", label: "Software & Abos" },
  { id: "reise", label: "Reise & Mobilität" },
];

export const EMPTY_RULE: RuleDraft = {
  name: "",
  enabled: true,
  priority: "NORMAL",
  keywords: [],
  required_keywords: [],
  blacklist: [],
  max_preis: null,
  min_rabatt_prozent: null,
  nur_gratis: false,
  erwachsen: false,
  min_temperatur: null,
  min_urteil: null,
  min_fehler_score: null,
  sources: [],
  kategorien: [],
  warengruppen: [],
  haendler: [],
  channels: [],
};
