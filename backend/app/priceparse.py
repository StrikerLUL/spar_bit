"""Robustes Preis-Parsing fuer deutsche (und englische) Deal-Texte.

Zielformate u.a.:
  "12,99€ statt 89,90€"      -> 12.99 / 89.90
  "-95%"                      -> rabatt 95
  "gratis", "geschenkt", "kostenlos", "umsonst", "for free"
  "0,00 €", "0€", "EUR 0.00"
  "1.299,00 € statt 1.899,00 €"  (Tausenderpunkt!)
  "statt 59,99 nur 9,99"
"""
from __future__ import annotations

import re
import unicodedata

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

# "statt", "instead of", "UVP", "war", "vorher", "RRP"
_INSTEAD = re.compile(
    r"\b(statt|anstatt|instead\s+of|uvp|vorher|war|rrp|msrp|regulaer|regular)\b",
    re.IGNORECASE,
)
# "nur", "jetzt", "for", "ab"
_NOW = re.compile(r"\b(nur|jetzt|now|for|ab|aktuell)\b", re.IGNORECASE)


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


# Bare Dezimalzahl ("4,99"), nur als Fallback in eindeutigem Preis-Kontext.
_BARE_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.\s]\d{3})*[.,]\d{2})(?![\w.,])")


def find_prices(text: str) -> list[tuple[float, int, str | None]]:
    """Alle Geldbetraege als (wert, position, waehrung).

    Primaer zaehlt nur, was ein Waehrungszeichen traegt. Faellt das aus, aber
    der Text sagt eindeutig Preis ("4,99 statt 19,99"), greift ein Fallback
    auf blanke Dezimalzahlen - sonst verlieren wir halbe Deal-Titel.
    """
    out: list[tuple[float, int, str | None]] = []
    norm = normalize_text(text)
    for m in _PRICE_RE.finditer(norm):
        marker = m.group("pre") or m.group("post")
        if not marker:
            continue
        val = parse_number(m.group("num"))
        if val is None or val > 1_000_000:
            continue
        cur = _CURRENCY.get(marker.lower().strip())
        out.append((val, m.start(), cur))

    if out:
        return out

    # Fallback nur, wenn der Text sich klar als Preisangabe zu erkennen gibt.
    if not (_INSTEAD.search(norm) or _NOW.search(norm) or detect_currency(norm)):
        return out
    for m in _BARE_RE.finditer(norm):
        val = parse_number(m.group(1))
        if val is None or val > 1_000_000:
            continue
        out.append((val, m.start(), None))
    return out


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


def parse_price_text(text: str) -> ParsedPrice:
    """Hauptfunktion: aus freiem Text Preis/Originalpreis/Rabatt ziehen."""
    norm = normalize_text(text)
    if not norm:
        return ParsedPrice()

    currency = detect_currency(norm)
    pct = parse_percent(norm)
    prices = find_prices(norm)
    free = is_free_text(norm)

    preis = orig = None

    if prices:
        # Falls "statt/UVP" vorkommt: Preis davor = aktuell, danach = Original.
        m_instead = _INSTEAD.search(norm)
        if m_instead and len(prices) >= 2:
            before = [p for p in prices if p[1] < m_instead.start()]
            after = [p for p in prices if p[1] > m_instead.start()]
            if before and after:
                preis, orig = before[-1][0], after[0][0]
            elif after and len(after) >= 2:
                preis, orig = after[0][0], after[1][0]
        if preis is None:
            vals = [p[0] for p in prices]
            if len(vals) >= 2:
                # Ohne Marker: kleinster = aktuell, groesster = Original.
                lo, hi = min(vals), max(vals)
                if hi > lo:
                    preis, orig = lo, hi
                else:
                    preis = lo
            else:
                preis = vals[0]
        if currency is None:
            currency = next((p[2] for p in prices if p[2]), None)

    # Gratis-Signale. "geschenkt statt 59,99 EUR" heisst: 0 jetzt, 59,99 vorher -
    # der einzige gefundene Preis ist dann der Originalpreis, nicht der aktuelle.
    if free and preis is not None and preis > 0 and orig is None:
        m_instead = _INSTEAD.search(norm)
        if m_instead and any(p[1] > m_instead.start() for p in prices):
            orig, preis = preis, 0.0
    if free and (preis is None or preis == 0):
        preis, free = 0.0, True
    if preis is not None and preis <= 0.009:
        free = True
    if pct is not None and pct >= 99.5:
        free = True
        if preis is None:
            preis = 0.0

    # Rabatt herleiten
    if pct is None and preis is not None and orig and orig > 0 and preis <= orig:
        pct = round((1 - preis / orig) * 100, 1)
    # Original herleiten
    if orig is None and preis is not None and pct and 0 < pct < 100:
        derived = preis / (1 - pct / 100)
        if derived > preis:
            orig = round(derived, 2)

    return ParsedPrice(preis, orig, pct, currency, free)
