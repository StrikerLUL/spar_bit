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

Die zweite schwierige Stelle kam aus dem Betrieb hinterher: **nicht jeder
Betrag in einem Deal-Text ist ein Preis.** In derselben Zeile stehen
regelmaessig Betraege, die etwas voellig anderes bedeuten -

    "Sony XM5 fuer 229 EUR, zzgl. 4,99 EUR Versand"   -> 4,99 ist Porto
    "20 EUR Gutschein ab 100 EUR Bestellwert"          -> beides kein Preis
    "6er-Pack fuer 23,94 EUR (je 3,99 EUR)"            -> 3,99 ist Stueckpreis
    "Netflix 4,99 EUR pro Monat statt 12,99 EUR"       -> Preis, aber je Monat

- und wer die fuer den Artikelpreis haelt, zeigt 4,99 EUR fuer Kopfhoerer an.
Darum bekommt jede Zahl zusaetzlich einen **Zweck** aus ihrem Umfeld:
Versand, Rabatt, Mindestbestellwert, Gebuehr, Stueckpreis, Zeitraum. Was
nachweislich kein Artikelpreis ist, faellt bei der Auswahl raus; ein
Zeitraum faellt nicht raus, sondern wird mitgefuehrt - "4,99 EUR" und
"4,99 EUR/Monat" sind zwei verschiedene Angebote, und nur eines davon ist
guenstig.
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
    # Die Zahl muss am Anfang stehen duerfen: ohne diese Bremse frisst der
    # Tausendertrenner die letzte Ziffer einer Modellnummer mit.
    # "Sony WH-1000XM5 229 EUR" wurde so zu 5.229 EUR - echt gemessen.
    rf"(?<![\w.,])(?P<num>{_NUM})"
    rf"\s*(?P<post>[€$£]|EUR|USD|GBP|CHF|Euro)?",
    re.IGNORECASE,
)

_PCT_RE = re.compile(r"[-−–]?\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*%")

# Signalwoerter, nach denen der ALTE Preis steht ...
_INSTEAD_WORDS = (r"statt|anstatt|instead\s+of|uvp|vorher|war|rrp|msrp|"
                  r"regulär|regulaer|regular|bisher|ehemals|listenpreis|"
                  r"originalpreis|was|wert|worth|value")
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

# --- Wozu gehoert ein Betrag? ---------------------------------------------
#
# Jede Regel ist ein Paar aus "was darf davor stehen" und "was darf danach
# stehen". Geprueft wird nur ein kurzes Fenster um die Zahl herum
# (ZWECK_WEITE) - was zehn Woerter weiter steht, gehoert nicht mehr dazu.

ZWECK_WEITE = 28

# Diese Zwecke sind kein Artikelpreis. Ein Betrag mit so einem Etikett
# kommt fuer "was kostet das Ding" nicht mehr in Frage.
KEIN_PREIS = ("versand", "rabatt", "mbw", "gebuehr")

_V_WORT = r"versand\w*|porto\w*|lieferung|zustellung|shipping|delivery"

# ... aber "versandkostenfrei" ist das Gegenteil von Versandkosten.
#
# Aus dem Betrieb gemessen: "Kopfhoerer 229 EUR versandkostenfrei" verlor
# seinen Preis, weil hinter der Zahl ein Wort mit "versand" stand. Genau
# diese Wendung steht in jedem zweiten deutschen Deal-Titel - und sie sagt,
# dass eben KEIN Porto dazukommt. Wo so eine Verneinung steht, ist der
# Betrag daneben der Artikelpreis und nicht das Porto.
_VERSAND_GRATIS = re.compile(
    r"(?:versand|porto|liefer\w*?|zustell\w*?)(?:kosten)?(?:frei|los)"
    r"|(?:gratis|kostenlos\w*|kostenfrei\w*|frei\w*|inklusive|inkl\.?)"
    r"\s*[-–]?\s*(?:versand\w*|porto\w*|lieferung|zustellung|shipping)"
    r"|(?:versand\w*|porto\w*|lieferung)\s*(?:ist\s+)?(?:gratis|kostenlos|frei|inklusive|inkl\.?)",
    re.IGNORECASE)
_R_WORT = (r"rabatt\w*|gutschein\w*|coupon\w*|cashback|nachlass|ersparnis|"
           r"sparen|spare|bonus|prämie|praemie|guthaben|erstattung|"
           r"willkommensbonus|neukundenbonus")
_M_WORT = (r"mbw|mindestbestellwert|bestellwert|einkaufswert|warenkorbwert|"
           r"mindestumsatz")
_G_WORT = (r"gebühr\w*|gebuehr\w*|anschlusspreis|bereitstellungspreis|"
           r"servicepauschale|grundgebühr|grundgebuehr|pfand|kaution")
_S_WORT = (r"stückpreis|stueckpreis|je\s+stück|pro\s+stück|je\s+einheit|"
           r"pro\s+einheit|je\s+packung|pro\s+packung|pro\s+dose|"
           r"pro\s+flasche|pro\s+kapsel|pro\s+liter|pro\s+100\s*g")

# (Schluessel, Klartext, was DAVOR stehen darf, was DANACH stehen darf)
_ZWECKE: list[tuple[str, str, str | None, str | None]] = [
    ("versand", "Versandkosten",
     rf"(?:{_V_WORT})\s*(?:kostet|von|ab|:)?\s*$"
     r"|(?:zzgl\.?|zuzüglich|plus|\+)\s*$",
     rf"\s*(?:€|eur|euro)?\s*(?:{_V_WORT})"),
    ("rabatt", "Rabatt- oder Gutscheinbetrag",
     rf"(?:{_R_WORT})\s*(?:in\s+höhe\s+von|im\s+wert\s+von|über|ueber|von|:)?\s*$",
     rf"\s*(?:€|eur|euro)?\s*(?:{_R_WORT})"),
    ("mbw", "Mindestbestellwert",
     rf"(?:{_M_WORT})\s*(?:von|ab|:)?\s*$",
     rf"\s*(?:€|eur|euro)?\s*(?:{_M_WORT})"),
    ("gebuehr", "Gebühr, nicht der Artikelpreis",
     rf"(?:{_G_WORT})\s*(?:von|:)?\s*$",
     rf"\s*(?:€|eur|euro)?\s*(?:{_G_WORT})"),
    ("stueck", "Stückpreis",
     rf"(?:{_S_WORT})\s*(?:von|:|=)?\s*$|\b(?:je|à)\s*$",
     rf"\s*(?:€|eur|euro)?\s*(?:{_S_WORT})|\s*(?:€|eur|euro)?\s*/\s*stück"),
]

_ZWECK_TEXT = {k: t for k, t, _, _ in _ZWECKE}
_ZWECK_RE = [(k,
              re.compile(d, re.IGNORECASE) if d else None,
              re.compile(n, re.IGNORECASE) if n else None)
             for k, _, d, n in _ZWECKE]

# Zeitraeume. Kein Ausschluss, sondern eine Eigenschaft des Preises: was
# 4,99 im Monat kostet, kostet im Jahr 59,88 - und steht auf der Karte
# deshalb mit "/Monat" dran.
_ZEITRAUM = [
    ("monat", r"(?:/|pro|je|im|p\.?\s*m\.?)?\s*(?:monat\w*|mtl\.?)",
     r"(?:monatlich|mtl\.?|pro\s+monat|im\s+monat|je\s+monat|monatsabo|"
     r"monatspaket)\s*(?:nur|ab|für|fuer|schon|:)?\s*$"),
    ("jahr", r"(?:/|pro|je|im|p\.?\s*a\.?)?\s*(?:jahr\w*|jährlich|jaehrlich)",
     r"(?:jährlich|jaehrlich|pro\s+jahr|im\s+jahr|jahresabo|jahrespaket|"
     r"jahreslizenz)\s*(?:nur|ab|für|fuer|:)?\s*$"),
    ("woche", r"(?:/|pro|je|die)?\s*(?:woche|wöchentlich|woechentlich)",
     r"(?:wöchentlich|woechentlich|pro\s+woche)\s*(?:nur|ab|für)?\s*$"),
]
# Vor der Zeitangabe darf Satzzeichen stehen: "59,88 € (jährlich)" ist
# dieselbe Aussage wie "59,88 € jährlich", nur in Klammern.
_ZEITRAUM_RE = [(k, re.compile(r"^[\s(\[,;–-]*" + n, re.IGNORECASE),
                 re.compile(d, re.IGNORECASE))
                for k, n, d in _ZEITRAUM]

_ZEITRAUM_LABEL = {"monat": "Monat", "jahr": "Jahr", "woche": "Woche"}
_MONATE_JE = {"monat": 1, "jahr": 12, "woche": 0.25}

# "3 Monate fuer 1 EUR", "12 Monate ab 49 EUR" - der Betrag gilt fuer die
# ganze Laufzeit, nicht je Monat. Fuer den Vergleich zaehlt, was er pro
# Monat macht.
_LAUFZEIT_RE = re.compile(
    r"(\d{1,3})\s*(monate?n?|jahre?n?)\s*(?:lang\s*)?"
    r"(?:für|fuer|zu|um|ab|nur|zum\s+preis\s+von|:)?\s*$",
    re.IGNORECASE)


def _zweck_fuer(norm: str, start: int, ende: int) -> str | None:
    """Wofuer steht dieser Betrag - Ware, Porto, Gutschein?"""
    davor = norm[max(0, start - ZWECK_WEITE):start].lower()
    danach = norm[ende:ende + ZWECK_WEITE].lower()
    for key, dre, nre in _ZWECK_RE:
        if dre is not None and dre.search(davor):
            # Steht das Versandwort VOR der Zahl, ist sie in beiden
            # Lesarten kein Artikelpreis: "Versand 3,95 EUR" ist das Porto,
            # "gratis Versand ab 20 EUR" die Schwelle dafuer.
            return key
        if nre is not None and nre.match(danach):
            # Dahinter dagegen entscheidet die Verneinung: "229 EUR
            # versandkostenfrei" nennt keine Versandkosten, sondern sagt,
            # dass keine anfallen. Der Betrag bleibt der Artikelpreis.
            if key == "versand" and _VERSAND_GRATIS.search(danach):
                continue
            return key
    return None


def _zeitraum_fuer(norm: str, start: int, ende: int) -> str | None:
    """Gilt der Betrag je Monat, je Jahr, je Woche?"""
    davor = norm[max(0, start - ZWECK_WEITE):start]
    danach = norm[ende:ende + ZWECK_WEITE]
    for key, nre, dre in _ZEITRAUM_RE:
        if nre.match(danach) or dre.search(davor):
            return key
    return None


def _laufzeit_fuer(norm: str, start: int) -> float | None:
    """'3 Monate fuer 1 EUR' - wie viele Monate deckt dieser Betrag ab?"""
    treffer = _LAUFZEIT_RE.search(norm[max(0, start - 40):start])
    if not treffer:
        return None
    try:
        anzahl = int(treffer.group(1))
    except ValueError:
        return None
    if anzahl <= 0 or anzahl > 120:
        return None
    return float(anzahl * (12 if treffer.group(2).lower().startswith("jahr") else 1))


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


# --- Worauf sich "gratis" bezieht -----------------------------------------
#
# Der haeufigste Grund fuer eine falsche Gratis-Meldung ist nicht ein
# kaputter Parser, sondern ein Wort, das sich auf etwas anderes bezieht als
# auf die Ware: "Sony XM5 fuer 229 EUR inkl. gratis Versand" ist kein
# Geschenk, "3 Monate gratis, danach 10,99 EUR" auch nicht. Frueher reichte
# das blosse Vorkommen von "gratis" irgendwo im Text - und weil jede zweite
# Deal-Beschreibung irgendwo "kostenloser Versand" stehen hat, landete
# reihenweise Bezahlware im Gratis-Filter.
#
# Darum wird hier nicht nur gefragt OB, sondern WORAUF.

# Woerter, die sich in einem Kompositum selbst erklaeren.
_GEKLEBT: dict[str, str] = {
    "versandkostenfrei": "versand", "versandkostenlos": "versand",
    "portofrei": "versand", "gratisversand": "versand",
    "lieferkostenfrei": "versand",
    "gratismonat": "probe", "probemonat": "probe", "gratismonate": "probe",
    "gratiszugabe": "zugabe", "gratisbeigabe": "zugabe",
    "gebuehrenfrei": "service", "gebührenfrei": "service",
    "kontofuehrungsfrei": "service",
}

# Adjektive, die gebeugt auftreten ("kostenlose Lieferung",
# "gebuehrenfreier Kontofuehrung").
_BEUGBAR = ({"kostenlos", "kostenfrei"}
            | {w for w in _GEKLEBT if w.endswith(("frei", "los"))})


def _alternative(wort: str) -> str:
    esc = re.escape(wort).replace(r"\ ", r"\s+")
    return esc + r"(?:e[mnrs]?)?" if wort in _BEUGBAR else esc


_GRATIS_RE = re.compile(
    r"(?<![a-z0-9äöüß])(?:"
    + "|".join(_alternative(w) for w in
               sorted(set(FREE_WORDS) | set(_GEKLEBT), key=len, reverse=True))
    + r")(?![a-z0-9äöüß])",
    re.IGNORECASE,
)

# Wie weit um das Wort herum nach seinem Bezug gesucht wird.
BEZUG_WEITE = 34

_VERSAND = r"versand\w*|lieferung\w*|liefer\w*|zustellung|porto|shipping|delivery"
_RUECK = (r"rückversand|rueckversand|rücksendung|ruecksendung|retoure\w*|"
          r"rückgabe|rueckgabe|umtausch|storno\w*|returns?")
_DIENST = (r"hotline|beratung|support|kontoführung|kontofuehrung|girokonto|"
           r"überweisung|ueberweisung|abhebung|bargeldabhebung|servicepauschale")
_ZEIT = r"\d+\s*(?:tag|tage|tagen|woche|wochen|monat|monate|monaten|jahr|jahre)"

# (Schluessel, Klartext, was DAVOR stehen darf, was DANACH stehen darf)
_BEZUEGE: list[tuple[str, str, str | None, str | None]] = [
    ("versand", "gilt nur für den Versand",
     rf"(?:{_VERSAND})\s+(?:ist\s+|sind\s+)?$",
     rf"[\s\-]*(?:{_VERSAND})"),
    ("rueckgabe", "gilt nur für die Rücksendung",
     rf"(?:{_RUECK})\s+(?:ist\s+|sind\s+)?$",
     rf"[\s\-]*(?:{_RUECK})"),
    ("probe", "gilt nur für einen Testzeitraum",
     rf"(?:{_ZEIT})\s*(?:lang\s*)?$",
     r"[\s\-]*(?:testen|ausprobieren|probieren|trial|testphase|probeabo)"
     r"|.{0,24}?\b(?:danach|anschließend|anschliessend|im\s+anschluss|"
     r"monatlich\s+kündbar|danach\s+kostenpflichtig)\b"),
    ("zugabe", "ist eine Zugabe, nicht der Artikel",
     r"\b(?:dazu|obendrauf|zusätzlich|zusaetzlich|extra|als\s+zugabe)\s*$",
     r"[^,;.!?|•]{0,30}?\b(?:dazu|obendrauf|mit\s+dabei|als\s+zugabe|"
     r"als\s+beigabe|zum\s+kauf)\b"),
    ("bedingung", "gilt nur ab einem Mindestbestellwert",
     r"\b(?:ab\s+\d[\d.,]*\s*(?:€|eur|euro)?\s*|beim\s+kauf\s+von\s+)$",
     r".{0,30}?\b(?:ab\s+\d|ab\s+einem|beim\s+kauf|bei\s+kauf|mit\s+kauf|"
     r"mindestbestellwert|einkaufswert)\b"),
    ("service", "gilt für eine Nebenleistung",
     rf"(?:{_DIENST})\s+(?:ist\s+|sind\s+)?$",
     rf"[\s\-]*(?:{_DIENST})"),
]

_BEZUG_TEXT = {k: t for k, t, _, _ in _BEZUEGE}
_BEZUG_RE = [(k, re.compile(d, re.IGNORECASE) if d else None,
              re.compile(n, re.IGNORECASE) if n else None)
             for k, _, d, n in _BEZUEGE]


@dataclass
class GratisBefund:
    """Steht hier wirklich 'geschenkt' - und wenn nicht, worauf bezog es sich?"""

    gratis: bool
    bezug: str | None = None            # stabiler Schluessel, z.B. "versand"
    einschraenkung: str | None = None   # Klartext fuer die Oberflaeche


def _bezug_fuer(low: str, start: int, end: int) -> str | None:
    """Der Bezug eines Gratis-Wortes, oder None wenn es fuer sich steht."""
    wort = low[start:end].replace("-", "").replace(" ", "")
    if wort in _GEKLEBT:
        return _GEKLEBT[wort]
    # Gebeugte Form auf den Stamm zurueckfuehren: "gebuehrenfreier" -> ...
    stamm = re.sub(r"e[mnrs]?$", "", wort)
    if stamm in _GEKLEBT:
        return _GEKLEBT[stamm]
    davor = low[max(0, start - BEZUG_WEITE):start]
    danach = low[end:end + BEZUG_WEITE]
    for key, dre, nre in _BEZUG_RE:
        if dre is not None and dre.search(davor):
            return key
        if nre is not None and nre.match(danach):
            return key
    return None


def pruefe_gratis(text: str) -> GratisBefund:
    """Gratis ja/nein - und bei nein der Grund.

    Ein einziges unbedingtes Gratis-Wort genuegt. Erst wenn sich JEDER
    Fund auf etwas anderes bezieht, ist der Artikel nicht geschenkt.
    """
    low = normalize_text(text).lower()
    treffer = list(_GRATIS_RE.finditer(low))
    if not treffer:
        return GratisBefund(False)

    bezuege: list[str] = []
    for m in treffer:
        bezug = _bezug_fuer(low, m.start(), m.end())
        if bezug is None:
            return GratisBefund(True)
        bezuege.append(bezug)
    erster = bezuege[0]
    return GratisBefund(False, erster, _BEZUG_TEXT[erster])


def is_free_text(text: str) -> bool:
    """Alte Sicht auf `pruefe_gratis` - nur das Ja/Nein."""
    return pruefe_gratis(text).gratis


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
    # Wofuer der Betrag steht: None = Ware, sonst "versand", "rabatt",
    # "mbw", "gebuehr", "stueck".
    zweck: str | None = None
    zeitraum: str | None = None    # "monat" | "jahr" | "woche"
    laufzeit: float | None = None  # Monate, die dieser Betrag abdeckt

    @property
    def ist_preis(self) -> bool:
        """Kommt dieser Betrag als Artikelpreis ueberhaupt in Frage?"""
        return self.zweck not in KEIN_PREIS


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

    # Zweck und Zeitraum stehen im Umfeld der Zahl, nicht in ihr. Beides
    # wird erst hier bestimmt, damit auch die in Stufe 3 nachgetragenen
    # Betraege ihr Etikett bekommen.
    for f in funde:
        ende = _wortende(norm, f.pos)
        f.zweck = _zweck_fuer(norm, f.pos, ende)
        f.zeitraum = _zeitraum_fuer(norm, f.pos, ende)
        f.laufzeit = _laufzeit_fuer(norm, f.pos)
    return funde


_ZAHLENDE_RE = re.compile(rf"\s*(?:{_NUM})\s*(?:€|\$|£|eur|usd|gbp|chf|euro)?",
                          re.IGNORECASE)


def _wortende(norm: str, start: int) -> int:
    """Wo hoert die Zahl auf, die an `start` beginnt (samt Waehrungszeichen)?

    Fuer den Blick nach rechts ist das die entscheidende Stelle: "4,99 €
    Versand" darf nicht am Euro-Zeichen haengenbleiben, sonst steht im
    Fenster nur noch "Versan".
    """
    m = _ZAHLENDE_RE.match(norm, start)
    return m.end() if m else start


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
    __slots__ = ("preis", "originalpreis", "rabatt_prozent", "waehrung",
                 "ist_gratis", "gratis_einschraenkung", "zeitraum",
                 "laufzeit_monate", "preis_hinweis")

    def __init__(self, preis=None, originalpreis=None, rabatt_prozent=None,
                 waehrung=None, ist_gratis=False, gratis_einschraenkung=None,
                 zeitraum=None, laufzeit_monate=None, preis_hinweis=None):
        self.preis = preis
        self.originalpreis = originalpreis
        self.rabatt_prozent = rabatt_prozent
        self.waehrung = waehrung
        self.ist_gratis = ist_gratis
        # Gesetzt, wenn im Text zwar ein Gratis-Wort stand, es sich aber auf
        # etwas anderes bezog - Klartext fuer die Oberflaeche.
        self.gratis_einschraenkung = gratis_einschraenkung
        # "monat" | "jahr" | "woche": der Preis gilt je Zeitraum, nicht einmalig.
        self.zeitraum = zeitraum
        # Wie viele Monate ein einmaliger Betrag abdeckt ("3 Monate fuer 1 EUR").
        self.laufzeit_monate = laufzeit_monate
        # Klartext fuer die Karte: "pro Monat", "für 3 Monate", "Stückpreis".
        self.preis_hinweis = preis_hinweis

    @property
    def preis_pro_monat(self) -> float | None:
        """Was das Angebot im Monat kostet - oder None, wenn es kein Abo ist.

        Der Punkt daran ist der Vergleich: "1 EUR" und "49 EUR" sagen
        nichts, solange nicht dabeisteht, ob fuer einen Monat oder fuer
        zwoelf. Erst diese Zahl macht aus zwei Abo-Angeboten eine Rangfolge.
        """
        if self.preis is None:
            return None
        if self.zeitraum:
            je = _MONATE_JE.get(self.zeitraum)
            return round(self.preis / je, 2) if je else None
        if self.laufzeit_monate:
            return round(self.preis / self.laufzeit_monate, 2)
        return None

    def __repr__(self) -> str:
        return (f"ParsedPrice(preis={self.preis}, originalpreis={self.originalpreis}, "
                f"rabatt={self.rabatt_prozent}, {self.waehrung}, gratis={self.ist_gratis})")

    def as_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def _brauchbar(funde: list[Fund]) -> list[Fund]:
    """Die Betraege, die als Artikelpreis ueberhaupt in Frage kommen.

    Versand, Gutschein, Mindestbestellwert und Gebuehren fliegen immer
    raus. Der Stueckpreis nur dann, wenn daneben ein Gesamtpreis steht -
    bei "6er-Pack 23,94 EUR (je 3,99 EUR)" ist 23,94 der Preis, bei
    "Kapseln je 0,29 EUR" ist 0,29 alles, was es gibt.
    """
    echte = [f for f in funde if f.ist_preis]
    ohne_stueck = [f for f in echte if f.zweck != "stueck"]
    return ohne_stueck or echte


def _waehle(funde: list[Fund]) -> tuple[float | None, float | None]:
    """Aus allen Fundstellen aktuellen Preis und Originalpreis waehlen."""
    funde = _brauchbar(funde)
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
    befund = pruefe_gratis(norm)
    gratis = befund.gratis
    einschraenkung = befund.einschraenkung

    preis, orig = _waehle(funde)
    if waehrung is None:
        waehrung = next((f.waehrung for f in funde if f.waehrung), None)

    # "geschenkt statt 59,99 EUR" heisst: jetzt 0, vorher 59,99. Der einzige
    # gefundene Betrag ist dann der Originalpreis, nicht der aktuelle.
    if gratis and preis is not None and preis > 0 and orig is None:
        if any(f.marker == "alt" for f in funde):
            orig, preis = preis, 0.0
    # Widerspruch: ein ausdruecklich als aktuell ausgezeichneter Preis ueber
    # null schlaegt das Gratis-Wort. "Jetzt 229 EUR" und "geschenkt" koennen
    # nicht beide stimmen - und die Zahl mit Signalwort davor ist die
    # verlaesslichere Angabe. Nur markierte Preise zaehlen hier: eine blosse
    # Zahl im Text ("Gratis-Skin, 9,99 EUR Wert") darf das nicht kippen.
    if gratis and preis is not None and preis > 0.009 \
            and any(f.marker == "neu" for f in funde):
        gratis = False
        einschraenkung = einschraenkung or "ein aktueller Preis ist genannt"

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

    zeitraum, laufzeit, hinweis = _zeitangabe(funde, preis)
    return ParsedPrice(preis, orig, pct, waehrung, gratis, einschraenkung,
                       zeitraum, laufzeit, hinweis)


def _zeitangabe(funde: list[Fund], preis: float | None
                ) -> tuple[str | None, float | None, str | None]:
    """Gilt der gewaehlte Preis je Monat - oder fuer eine ganze Laufzeit?

    Gesucht wird die Fundstelle, aus der der Preis stammt; nur deren
    Zeitangabe zaehlt. Sonst faerbt das "/Monat" eines danebenstehenden
    Streichpreises auf den Artikelpreis ab.
    """
    if preis is None:
        return None, None, None
    passend = [f for f in _brauchbar(funde) if abs(f.wert - preis) < 0.005]
    if not passend:
        return None, None, None

    zeitraum = next((f.zeitraum for f in passend if f.zeitraum), None)
    if zeitraum:
        return zeitraum, None, f"pro {_ZEITRAUM_LABEL.get(zeitraum, zeitraum)}"

    laufzeit = next((f.laufzeit for f in passend if f.laufzeit), None)
    if laufzeit:
        monate = int(laufzeit) if float(laufzeit).is_integer() else laufzeit
        return None, float(laufzeit), f"für {monate} Monate"

    if all(f.zweck == "stueck" for f in passend):
        return None, None, _ZWECK_TEXT["stueck"]
    return None, None, None
