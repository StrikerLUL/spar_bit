"""Robustes Preis-Parsing fuer deutsche (und englische) Deal-Texte.

Zielformate u.a.:
  "12,99€ statt 89,90€"              -> 12.99 / 89.90
  "statt 59,99 nur 9,99"             -> 9.99 / 59.99
  "Sony XM5 statt 379 € jetzt 229 €" -> 229 / 379
  "iPhone 15 für 699 statt 949 Euro" -> 699 / 949
  "-95%"                             -> rabatt 95
  "gratis", "geschenkt", "kostenlos", "umsonst", "for free"
  "1.299,00 € statt 1.899,00 €"      (Tausenderpunkt!)

Die schwierige Stelle ist nicht, Zahlen zu finden, sondern zu entscheiden,
WELCHE davon der aktuelle Preis ist. Ein Deal-Titel nennt fast immer zwei
Betraege, und wer den falschen nimmt, zeigt den durchgestrichenen UVP als
Preis an.

Darum bekommt hier jede gefundene Zahl ein Etikett - "davor stand statt" oder
"davor stand nur" - und erst diese Etiketten entscheiden. Der frueher benutzte
Positionsvergleich (was vor "statt" steht, ist der aktuelle Preis) liegt bei
jedem Titel daneben, der mit "statt" anfaengt.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

FREE_WORDS = {
    "gratis", "kostenlos", "geschenkt", "umsonst", "freebie", "for free",
    "free", "0 euro", "null euro", "geschenk", "kostenfrei", "gratisartikel",
    "free to keep", "free game", "gratis-spiel", "verschenken", "zu verschenken",
}

_CURRENCY = {
    "€": "EUR", "eur": "EUR", "euro": "EUR",
    "$": "USD", "usd": "USD",
    "£": "GBP", "gbp": "GBP",
    "chf": "CHF", "fr.": "CHF",
    "zł": "PLN", "pln": "PLN",
}

# Zahl mit optionalem Tausendertrenner und Dezimalteil.
_NUM = r"\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"

_PRICE_RE = re.compile(
    rf"(?P<pre>[€$£]|EUR|USD|GBP|CHF)?\s*"
    rf"(?P<num>{_NUM})"
    rf"\s*(?P<post>[€$£]|EUR|USD|GBP|CHF|Euro)?",
    re.IGNORECASE,
)

_PCT_RE = re.compile(r"[-−–]?\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*%")

# Signalwoerter, nach denen der ALTE Preis steht ...
_INSTEAD_WORDS = (r"statt|anstatt|instead\s+of|uvp|vorher|war|rrp|msrp|"
                  r"regulär|regulaer|regular|bisher|ehemals|listenpreis|"
                  r"originalpreis|was")
# ... und solche, nach denen der NEUE Preis steht.
_NOW_WORDS = (r"nur\s+noch|nur|jetzt|now|for|für|fuer|ab|aktuell|"
              r"zum\s+preis\s+von|reduziert\s+auf|dealpreis|angebotspreis")

_INSTEAD = re.compile(rf"\b(?:{_INSTEAD_WORDS})\b", re.IGNORECASE)
_NOW = re.compile(rf"\b(?:{_NOW_WORDS})\b", re.IGNORECASE)
_ANY_MARKER = re.compile(rf"\b(?P<wort>{_INSTEAD_WORDS}|{_NOW_WORDS})\b",
                         re.IGNORECASE)

# Blanke Dezimalzahl ("4,99") - nur in eindeutigem Preis-Kontext verwertbar.
_BARE_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.\s]\d{3})*[.,]\d{2})(?![\w.,])")

# Eine Zahl direkt hinter einem Signalwort: "statt 949", "für 699".
_MARKED_BARE_RE = re.compile(
    rf"\b(?P<wort>{_INSTEAD_WORDS}|{_NOW_WORDS})\b\s*(?P<num>{_NUM})",
    re.IGNORECASE)

# Was hinter einer Zahl stehen kann, wenn sie kein Preis ist: "16 GB", "3 Stück".
_EINHEIT = re.compile(
    r"^\s*(stk|stück|stueck|st\.|x|jahre?|monate?|tage?|wochen?|"
    r"gb|tb|mb|kb|ghz|mhz|zoll|cm|mm|km|kg|ml|w|kw|wh|mah|ah|v|"
    r"seiten|teile|teilig|pack|packungen?|liter|gramm|prozent|"
    r"mbit|gbit|fps|hz|bit|cores?|kerne?)\b", re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_number(raw: str) -> float | None:
    """'1.299,00' -> 1299.0 ; '12,99' -> 12.99 ; '1,299.00' -> 1299.0 ; '99' -> 99.0"""
    s = (raw or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        # Der letzte Trenner ist der Dezimaltrenner.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")      # deutsch
        else:
            s = s.replace(",", "")                         # englisch
    elif has_comma:
        # Komma ist Dezimaltrenner, ausser es sieht nach Tausendern aus (1,234)
        if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif has_dot:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def detect_currency(text: str) -> str | None:
    low = normalize_text(text).lower()
    for token, code in _CURRENCY.items():
        if token in low:
            return code
    return None


def is_free_text(text: str) -> bool:
    low = normalize_text(text).lower()
    # Wortgrenzen, damit "freeze" oder "Freeman" nicht triggert.
    for w in FREE_WORDS:
        if re.search(rf"(?<![a-z0-9äöüß]){re.escape(w)}(?![a-z0-9äöüß])", low):
            return True
    return False


def parse_percent(text: str) -> float | None:
    """Groesster Prozentwert im Text (Deals nennen oft mehrere)."""
    vals = []
    for m in _PCT_RE.finditer(normalize_text(text)):
        v = parse_number(m.group(1))
        if v is not None and 0 < v <= 100:
            vals.append(v)
    return max(vals) if vals else None


# --- Fundstellen -----------------------------------------------------------

@dataclass
class Fund:
    """Ein Geldbetrag im Text, mitsamt dem, was davor stand."""
    wert: float
    pos: int
    waehrung: str | None = None
    marker: str | None = None      # "alt" | "neu" | None
    sicher: bool = True            # trug ein Waehrungszeichen


# Wie weit ein Signalwort hoechstens vor der Zahl stehen darf, um noch
# dazuzugehoeren. "statt 59,99" ja, "statt dem Vorgaengermodell nun 59,99"
# nein - dazwischen steht zu viel, als dass die Zuordnung sicher waere.
MARKER_ABSTAND = 14


def _marker_fuer(norm: str, pos: int, andere: list[int]) -> str | None:
    """Welches Signalwort gehoert zu der Zahl an `pos`?

    Es zaehlt das letzte Signalwort davor - aber nur, wenn zwischen ihm und
    der Zahl keine andere Zahl liegt. Sonst faerbt in "statt 59,99 nur 9,99"
    das "statt" auch noch auf die 9,99 ab.
    """
    treffer = None
    for m in _ANY_MARKER.finditer(norm):
        if m.end() > pos:
            break
        if any(m.end() <= p < pos for p in andere):
            continue                          # eine andere Zahl liegt dazwischen
        if pos - m.end() > MARKER_ABSTAND:
            continue
        treffer = m.group("wort")
    if treffer is None:
        return None
    return "alt" if _INSTEAD.fullmatch(treffer) else "neu"


def _plausibel(norm: str, ende: int) -> bool:
    """Steht hinter der Zahl eine Einheit, ist es kein Preis ('16 GB')."""
    return not _EINHEIT.match(norm[ende:ende + 14])


def finde(text: str) -> list[Fund]:
    """Alle Geldbetraege im Text, nach Position sortiert.

    Drei Stufen, absteigend nach Verlaesslichkeit:

    1. Betraege mit Waehrungszeichen - das sind immer Preise.
    2. Nur wenn Stufe 1 leer bleibt: blanke Dezimalzahlen, und auch die nur,
       wenn der Text sich klar als Preisangabe zu erkennen gibt.
    3. Zahlen ohne Waehrungszeichen direkt hinter einem Signalwort
       ("statt 949"). Die kommen nur dazu, wenn sie ein Paar
       vervollstaendigen - sonst wuerde "3 für 2 Aktion: 14,99 €" als
       Preis 2 € melden.
    """
    norm = normalize_text(text)
    funde: list[Fund] = []
    belegt: list[tuple[int, int]] = []

    for m in _PRICE_RE.finditer(norm):
        zeichen = m.group("pre") or m.group("post")
        if not zeichen:
            continue
        wert = parse_number(m.group("num"))
        if wert is None or wert > 1_000_000:
            continue
        funde.append(Fund(wert, m.start("num"),
                          _CURRENCY.get(zeichen.lower().strip())))
        belegt.append((m.start(), m.end()))

    if not funde and (_INSTEAD.search(norm) or _NOW.search(norm)
                      or detect_currency(norm)):
        for m in _BARE_RE.finditer(norm):
            wert = parse_number(m.group(1))
            if wert is None or wert > 1_000_000 or not _plausibel(norm, m.end()):
                continue
            funde.append(Fund(wert, m.start(), None, sicher=False))
            belegt.append((m.start(), m.end()))

    # Marker zuordnen, bevor Stufe 3 neue Zahlen einstreut.
    positionen = [f.pos for f in funde]
    for f in funde:
        f.marker = _marker_fuer(norm, f.pos, [p for p in positionen if p != f.pos])

    funde.extend(_ergaenze_paar(norm, funde, belegt))
    funde.sort(key=lambda f: f.pos)
    return funde


def _ergaenze_paar(norm: str, funde: list[Fund],
                   belegt: list[tuple[int, int]]) -> list[Fund]:
    """Stufe 3: die fehlende Haelfte eines statt/nur-Paares nachtragen."""
    vorhanden = {f.marker for f in funde if f.marker}
    if not vorhanden or vorhanden == {"alt", "neu"}:
        return []                     # nichts zu ergaenzen oder schon vollstaendig
    gesucht = "neu" if vorhanden == {"alt"} else "alt"

    for m in _MARKED_BARE_RE.finditer(norm):
        start, ende = m.start("num"), m.end("num")
        if any(a <= start < b for a, b in belegt):
            continue                  # diese Zahl steckt schon in einem Treffer
        art = "alt" if _INSTEAD.fullmatch(m.group("wort")) else "neu"
        if art != gesucht:
            continue
        wert = parse_number(m.group("num"))
        if wert is None or wert <= 0 or wert > 1_000_000 or not _plausibel(norm, ende):
            continue
        # Nur ein sinnvolles Paar zaehlt: neu muss unter alt liegen.
        partner = [f.wert for f in funde if f.marker and f.marker != art]
        if art == "neu" and not any(wert < p for p in partner):
            continue
        if art == "alt" and not any(wert > p for p in partner):
            continue
        return [Fund(wert, start, None, marker=art, sicher=False)]
    return []


def find_prices(text: str) -> list[tuple[float, int, str | None]]:
    """Alte Sicht auf `finde` - (wert, position, waehrung)."""
    return [(f.wert, f.pos, f.waehrung) for f in finde(text)]


# --- Ergebnis --------------------------------------------------------------

class ParsedPrice:
    __slots__ = ("preis", "originalpreis", "rabatt_prozent", "waehrung", "ist_gratis")

    def __init__(self, preis=None, originalpreis=None, rabatt_prozent=None,
                 waehrung=None, ist_gratis=False):
        self.preis = preis
        self.originalpreis = originalpreis
        self.rabatt_prozent = rabatt_prozent
        self.waehrung = waehrung
        self.ist_gratis = ist_gratis

    def __repr__(self) -> str:
        return (f"ParsedPrice(preis={self.preis}, originalpreis={self.originalpreis}, "
                f"rabatt={self.rabatt_prozent}, {self.waehrung}, gratis={self.ist_gratis})")

    def as_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def _waehle(funde: list[Fund]) -> tuple[float | None, float | None]:
    """Aus allen Fundstellen aktuellen Preis und Originalpreis waehlen."""
    if not funde:
        return None, None

    alt = [f.wert for f in funde if f.marker == "alt"]
    neu = [f.wert for f in funde if f.marker == "neu"]
    ohne = [f.wert for f in funde if f.marker is None]

    # Bester Fall: beide Seiten sind ausgeschildert.
    if alt and neu:
        return min(neu), max(alt)

    # Nur "statt/UVP" markiert - der Rest ist der aktuelle Preis.
    if alt and ohne:
        return min(ohne), max(alt)
    if alt:
        # Nur "statt"-Werte, sonst nichts. Bei mehreren ist der kleinste
        # der Preis; bei einem einzigen kennen wir nur den UVP.
        return (min(alt), max(alt)) if len(alt) > 1 else (None, alt[0])

    # Nur "nur/jetzt" markiert - ein groesserer unmarkierter Wert ist der UVP.
    if neu:
        preis = min(neu)
        groesser = [w for w in ohne if w > preis]
        return preis, (max(groesser) if groesser else None)

    # Gar keine Marker: kleinster Betrag = Preis, groesster = UVP.
    if len(ohne) >= 2:
        lo, hi = min(ohne), max(ohne)
        return (lo, hi) if hi > lo else (lo, None)
    return ohne[0], None


def parse_price_text(text: str) -> ParsedPrice:
    """Hauptfunktion: aus freiem Text Preis/Originalpreis/Rabatt ziehen."""
    norm = normalize_text(text)
    if not norm:
        return ParsedPrice()

    waehrung = detect_currency(norm)
    pct = parse_percent(norm)
    funde = finde(norm)
    gratis = is_free_text(norm)

    preis, orig = _waehle(funde)
    if waehrung is None:
        waehrung = next((f.waehrung for f in funde if f.waehrung), None)

    # "geschenkt statt 59,99 EUR" heisst: jetzt 0, vorher 59,99. Der einzige
    # gefundene Betrag ist dann der Originalpreis, nicht der aktuelle.
    if gratis and preis is not None and preis > 0 and orig is None:
        if any(f.marker == "alt" for f in funde):
            orig, preis = preis, 0.0
    if gratis and (preis is None or preis == 0):
        preis = 0.0
    if preis is not None and preis <= 0.009:
        gratis = True
    if pct is not None and pct >= 99.5:
        gratis = True
        if preis is None:
            preis = 0.0

    # Ein "Originalpreis", der unter dem Preis liegt, ist ein Parse-Unfall.
    # Lieber gar keinen Streichpreis zeigen als einen falschen.
    if orig is not None and preis is not None and orig <= preis:
        orig = None

    if pct is None and preis is not None and orig and orig > 0 and preis <= orig:
        pct = round((1 - preis / orig) * 100, 1)
    if orig is None and preis is not None and pct and 0 < pct < 100:
        hergeleitet = preis / (1 - pct / 100)
        if hergeleitet > preis:
            orig = round(hergeleitet, 2)

    return ParsedPrice(preis, orig, pct, waehrung, gratis)
