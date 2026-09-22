/* Zwei Sprachen, ohne Bibliothek.
 *
 * SparBit ist auf Deutsch gebaut - Oberfläche, Code, Kommentare (siehe
 * CONTRIBUTING.md). Das bleibt so. Aber vier der eingebauten Quellen
 * liefern gar kein Deutsch (HotUKDeals, Dealabs, Slickdeals, OzBargain),
 * und wer das Projekt auf GitHub findet, liest die Oberfläche nicht.
 *
 * Darum eine zweite Sprache - und zwar so, dass sie niemanden stört:
 *
 * **Deutsch bleibt die Vorgabe** und ist zugleich der Schlüssel. Ein
 * fehlender englischer Eintrag fällt damit nicht als `missing.key` auf,
 * sondern zeigt den deutschen Text. Das ist der Grund für diese Form:
 * eine Übersetzung, die halb fertig ist, soll aussehen wie Deutsch, nicht
 * wie ein Defekt.
 *
 * **Keine Bibliothek.** i18next wäre 40 KB für das, was hier vierzig
 * Zeilen sind - und es bringt eine Konfiguration mit, die man pflegen
 * muss.
 *
 * Stand: Navigation, Anmeldung, Feed, Deal-Karten, Preisurteile und die
 * gemeinsamen Bedienelemente sind übersetzt. Die Einstellungsseiten
 * (Regeln, Kanäle, Quellen, System) sind es noch nicht - dort steht viel
 * erklärender Fließtext, und eine halbe Übersetzung wäre dort schlimmer
 * als gar keine. `docs/entwicklung.md` sagt, wie man weitermacht.
 */
import * as React from "react";

export type Sprache = "de" | "en";

const KEY = "sparbit-sprache";

/** Was der Browser will - Englisch nur, wenn er ausdrücklich danach fragt. */
function browserSprache(): Sprache {
  const roh = (navigator.languages?.[0] ?? navigator.language ?? "de").toLowerCase();
  return roh.startsWith("en") ? "en" : "de";
}

export function gespeicherteSprache(): Sprache {
  try {
    const gemerkt = localStorage.getItem(KEY);
    if (gemerkt === "de" || gemerkt === "en") return gemerkt;
  } catch {
    /* privater Modus - dann eben der Browser */
  }
  return browserSprache();
}

/* Die Wörterbücher. Schlüssel ist der deutsche Text; nur Englisch steht
 * hier, Deutsch ergibt sich von selbst. */
const EN: Record<string, string> = {
  // --- Navigation ---
  "Finden": "Find",
  "Einstellen": "Configure",
  "Nachsehen": "Review",
  "Übersicht": "Overview",
  "Preisfehler": "Pricing errors",
  "Feed": "Feed",
  "Wunschliste": "Watchlist",
  "Regeln": "Rules",
  "Kanäle": "Channels",
  "Quellen": "Sources",
  "Statistiken": "Statistics",
  "Claimer": "Claimer",
  "Logs & System": "Logs & system",
  "18+": "18+",

  // --- Anmeldung ---
  "Anmelden": "Sign in",
  "Abmelden": "Sign out",
  "Benutzername": "Username",
  "Passwort": "Password",
  "Einrichten": "Set up",
  "Code aus der App": "Code from your app",
  "Zweiter Faktor": "Two-factor code",
  "Passwort wiederholen": "Repeat password",
  "SparBit einrichten": "Set up SparBit",
  "Willkommen zurück": "Welcome back",
  "Leg dein Konto an. Es gibt kein Standard-Passwort — was du hier setzt, gilt.":
    "Create your account. There is no default password — what you set here is what counts.",
  "Melde dich an, um weiterzumachen.": "Sign in to continue.",
  "Mindestens 10 Zeichen.": "At least 10 characters.",
  "Code aus der Authenticator-App": "Code from your authenticator app",
  "Handy nicht zur Hand? Ein Ersatzcode geht auch.":
    "Phone not at hand? A backup code works too.",
  "Die Passwörter stimmen nicht überein.": "The passwords do not match.",
  "Konto anlegen": "Create account",
  "Gesperrt — noch": "Locked —",
  "Sekunden": "seconds left",

  // --- Gemeinsame Bedienelemente ---
  "Speichern": "Save",
  "Abbrechen": "Cancel",
  "Löschen": "Delete",
  "Schließen": "Close",
  "Suchen": "Search",
  "Filter": "Filters",
  "Alle": "All",
  "Laden …": "Loading…",
  "Mehr laden": "Load more",
  "Nichts gefunden": "Nothing found",
  "Fehler": "Error",
  "Erneut versuchen": "Try again",
  "Hell": "Light",
  "Dunkel": "Dark",
  "Wie im System": "Match system",
  "Sprache": "Language",
  "Deutsch": "German",
  "Englisch": "English",
  "Menü öffnen": "Open menu",
  "Menü schließen": "Close menu",
  "Schnellzugriff öffnen": "Open quick access",
  "Verbunden": "Connected",
  "Keine Verbindung": "Disconnected",

  // --- Deal-Karten ---
  "gratis": "free",
  "statt": "was",
  "gemerkt": "saved",
  "merken": "save",
  "Zum Angebot": "View deal",
  "Details": "Details",
  "Preisalarm": "Price alert",
  "Gutschein-Code": "Coupon code",
  "Versand": "Shipping",
  "Gesamtpreis": "Total",
  "Händler": "Retailer",
  "Quelle": "Source",
  "Regel": "Rule",
  "Umgerechnet mit dem hinterlegten Kurs": "Converted at the stored rate",
  "guter Preis": "good price",
  "kein Urteil": "no verdict",

  // --- Preisurteile ---
  "Bestpreis": "Best price ever",
  "sehr gut": "very good",
  "gut": "good",
  "normal": "typical",
  "war günstiger": "was cheaper before",
  "UVP fragwürdig": "list price doubtful",
  "zu wenig Daten": "not enough data",
  "Preisurteil": "Price verdict",

  // --- Warengruppen ---
  "Elektronik": "Electronics",
  "Computer & Zubehör": "Computers & accessories",
  "Gaming": "Gaming",
  "Haushalt & Küche": "Home & kitchen",
  "Werkzeug & Garten": "Tools & garden",
  "Kleidung & Schuhe": "Clothing & shoes",
  "Drogerie & Gesundheit": "Health & beauty",
  "Lebensmittel & Getränke": "Food & drink",
  "Spielzeug": "Toys",
  "Bücher, Filme & Musik": "Books, films & music",
  "Software & Abos": "Software & subscriptions",
  "Reise & Mobilität": "Travel & mobility",
  "ohne Warengruppe": "no category",

  // --- Zustellungs-Diagnose ---
  "Warum kam das nicht an?": "Why didn't this arrive?",
  "Zugestellt": "Delivered",
  "Nicht zugestellt": "Not delivered",
  "Fazit": "Conclusion",
};

const WOERTERBUECHER: Record<Sprache, Record<string, string>> = { de: {}, en: EN };

/** Übersetzen. Unbekannter Schlüssel = der deutsche Text selbst. */
export function uebersetze(sprache: Sprache, text: string): string {
  return WOERTERBUECHER[sprache][text] ?? text;
}

/** BCP-47-Kennung für Intl. */
export function locale(sprache: Sprache): string {
  return sprache === "en" ? "en-GB" : "de-DE";
}

const Kontext = React.createContext<{
  sprache: Sprache;
  setSprache: (s: Sprache) => void;
  t: (text: string) => string;
}>({ sprache: "de", setSprache: () => {}, t: (text) => text });

export function SpracheProvider({ children }: { children: React.ReactNode }) {
  const [sprache, setzeSprache] = React.useState<Sprache>(gespeicherteSprache);

  const setSprache = React.useCallback((neu: Sprache) => {
    setzeSprache(neu);
    try {
      localStorage.setItem(KEY, neu);
    } catch {
      /* gilt dann nur für diese Sitzung */
    }
    // Ohne lang-Attribut liest ein Screenreader englische Texte mit
    // deutscher Aussprache vor - und die Silbentrennung stimmt auch nicht.
    document.documentElement.lang = neu;
  }, []);

  React.useEffect(() => {
    document.documentElement.lang = sprache;
  }, [sprache]);

  const wert = React.useMemo(
    () => ({ sprache, setSprache, t: (text: string) => uebersetze(sprache, text) }),
    [sprache, setSprache],
  );

  return React.createElement(Kontext.Provider, { value: wert }, children);
}

export function useSprache() {
  return React.useContext(Kontext);
}
