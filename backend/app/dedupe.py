"""Dedupe: URL-Hash (exakt) + Fuzzy-Titelvergleich (quellenuebergreifend).

Derselbe Deal kommt gern aus mydealz, Reddit, CheapShark und Preisjaeger
gleichzeitig - er soll genau einmal ankommen.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

# Tracking-Parameter, die denselben Deal unterschiedlich aussehen lassen.
_JUNK_PARAMS = re.compile(
    r"^(utm_|gclid|fbclid|msclkid|mc_[ce]id|ref|referrer|affiliate|aff|tag|"
    r"campaign|partner|source|cmp|icn|icid|ascsubtag|linkCode|creative"
    r"|creativeASIN|psc|th|smid|pf_rd_|pd_rd_|_encoding|deal_id_hash)",
    re.IGNORECASE,
)

_TITLE_JUNK = re.compile(
    r"\b(deal|angebot|sale|rabatt|gratis|kostenlos|free|nur|jetzt|statt|"
    r"bestpreis|tiefstpreis|preisfehler|neu|aktion|prime|blitzangebot|"
    r"sparen|reduziert|giveaway|100%|bis\s+zu)\b",
    re.IGNORECASE,
)


def canonical_url(url: str) -> str:
    """URL auf ihren Kern reduzieren: kein Tracking, kein Fragment, kein /."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"

    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
             if not _JUNK_PARAMS.match(k)]
    query.sort()

    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:32]


# Fuellwoerter, die ueber den Artikel nichts aussagen.
_STOPWORDS = {
    "für", "fuer", "bei", "auf", "mit", "von", "der", "die", "das", "den",
    "dem", "und", "im", "in", "zu", "ab", "je", "inkl", "the", "at",
    "on", "for", "with", "and", "to", "of", "a", "an", "is", "keep", "off",
    # "pro" fehlt hier bewusst: das ist eine Produktvariante (990 Pro,
    # iPhone Pro), kein Fuellwort - siehe _EDITION.
}


def normalize_title(title: str) -> str:
    """Titel fuer den Fuzzy-Vergleich entrauschen."""
    t = (title or "").lower()
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t)       # [PS5] (Steam) weg
    t = re.sub(r"[\d]+[,.]\d{2}\s*(?:€|eur|\$|usd|£)", " ", t)  # 12,99€ weg
    t = re.sub(r"[\d]+\s*(?:€|eur|\$|usd|£)(?![\w])", " ", t)     # 249€ weg
    t = re.sub(r"[-−–]?\s*\d{1,3}\s*%", " ", t)        # Prozente weg
    t = _TITLE_JUNK.sub(" ", t)
    t = re.sub(r"[^\w\säöüß]", " ", t)
    tokens = [w for w in t.split() if w not in _STOPWORDS]
    return " ".join(tokens).strip()


# Tokens, die eine Ausgabe/Fortsetzung unterscheiden. Wenn sich zwei Titel
# genau hierin unterscheiden, sind es NICHT dieselben Artikel.
_ROMAN = re.compile(r"^(?:i{1,3}|iv|v|vi{1,3}|ix|x{1,3})$")
_EDITION = {
    "remastered", "remaster", "definitive", "goty", "deluxe", "ultimate",
    "premium", "collectors", "collector", "anniversary", "enhanced", "complete",
    "gold", "platinum", "legacy", "redux", "reloaded", "director", "cut",
    "season", "pass", "dlc", "bundle", "edition", "pro", "max", "plus", "mini",
    "lite", "xl", "xxl", "set",
}


def _distinguishing(token: str) -> bool:
    """Unterscheidet dieses Token eine Ausgabe von einer anderen?

    Zahlen sind hier bewusst NICHT dabei - die werden ueber `_zahlen`
    verglichen, weil "2TB" und "2 TB" derselbe Artikel sind, "15" und "16"
    aber nicht.
    """
    return bool(_ROMAN.match(token)) or token in _EDITION


def _zahlen(titel: str) -> list[str]:
    """Alle Zahlen im Titel, sortiert.

    Der verlaesslichste Unterschied zwischen zwei Produktvarianten ist die
    Zahl darin: iPhone 15 / 16, Galaxy S24 / S25, WH-1000XM5 / XM4. Ob sie
    an einem Wort klebt ("2TB") oder getrennt steht ("2 TB"), ist egal -
    darum wird ueber den ganzen Titel gesucht, nicht ueber Tokens.
    """
    return sorted(re.findall(r"\d+", titel))


def titles_match(a: str, b: str, threshold: int = 88) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True

    # Verschiedene Zahlen heissen verschiedene Artikel. Das gilt ohne
    # Ausnahme - fruehere Versionen liessen hier einen Aehnlichkeitswert
    # entscheiden, und bei langen Titeln ("Kaffeekapseln Vorratspack 12"
    # gegen "... 13") lag der so hoch, dass zwei verschiedene Artikel
    # zusammenfielen.
    if _zahlen(na) != _zahlen(nb):
        return False

    ta, tb = set(na.split()), set(nb.split())

    # Nennt JEDE Seite etwas, das die andere nicht nennt, sind es verschiedene
    # Artikel ("Kaffeekapseln Lungo ..." gegen "Kaffeekapseln Espresso ...").
    # Nennt nur eine Seite etwas zusaetzlich, ist das meist Beiwerk
    # ("... bei Amazon", "... auf Steam") und stoert nicht.
    #
    # Das ist noetig, weil token_set_ratio eine Teilmenge als perfekten
    # Treffer wertet: je laenger der gemeinsame Text, desto leichter fielen
    # sonst zwei verschiedene Artikel zusammen.
    nur_a = "".join(sorted(ta - tb))
    nur_b = "".join(sorted(tb - ta))
    # Verglichen wird der Buchstabenbestand, damit "2TB" und "2 TB" gleich
    # bleiben - da unterscheidet sich nur die Schreibweise, nicht der Artikel.
    if nur_a and nur_b and nur_a != nur_b:
        return False

    # Ausgaben und Varianten ("Hades" vs "Hades II", "990 Pro" vs "990 Evo").
    if any(_distinguishing(t) for t in ta ^ tb):
        return False

    if max(len(na), len(nb)) < 12:
        threshold = 95   # kurze Titel kollidieren sonst zu leicht

    # token_set_ratio wertet Teilmengen als perfekten Treffer - das ist hier
    # erwuenscht ("Portal 2" == "Portal 2 auf Steam"), weil die Pruefungen
    # oben bereits ausgeschlossen haben, dass es verschiedene Artikel sind.
    return fuzz.token_set_ratio(na, nb) >= threshold


def similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(normalize_title(a), normalize_title(b))
