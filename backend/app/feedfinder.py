"""Den Feed finden, statt seinen Pfad zu raten.

Der Anlass war eine Fehlermeldung aus dem Betrieb:

    https://www.mydealz.de/gruppe/erotik-rss:
    ValueError: Kein gueltiger Feed (SAXParseException).
    Anfang der Antwort: '<!DOCTYPE html><html class="no-js …

Der Pfad war geraten, und er war falsch. Zwei Sachen sind daran zu lernen.

Die erste: die Antwort war eine **echte Seite**, kein 404 und keine
Cloudflare-Wand. Der Server ist also erreichbar, und er weiss, wo sein
Feed liegt - nur SparBit wusste es nicht. Praktisch jede Seite schreibt
das in ihren Kopf:

    <link rel="alternate" type="application/rss+xml" href="/rss/gruppe/erotik">

Genau danach wird hier gesucht. Kommt statt eines Feeds eine HTML-Seite,
liest SparBit deren Feed-Auszeichnungen aus und probiert sie der Reihe
nach. Damit heilt sich ein falsch geratener Pfad von selbst - und was
gefunden wurde, wird in die Quellen-Einstellungen zurueckgeschrieben, so
dass beim naechsten Lauf gleich die richtige Adresse dransteht.

Die zweite: eine Fehlermeldung muss sagen, was zu tun ist. "SAXParseException"
sagt das nicht. Steht auf der Seite kein Feed, nennt der Fehler jetzt den
Seitentitel und - wenn vorhanden - welche Adressen dort ausgezeichnet sind.
"""
from __future__ import annotations

import html as html_mod
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

log = logging.getLogger(__name__)

# Wie viele ausgezeichnete Adressen hoechstens ausprobiert werden. Mehr
# waere gegenueber der fremden Seite unhoeflich - und wer drei Feeds
# anbietet, von denen keiner geht, hat ein anderes Problem.
MAX_VERSUCHE = 3

FEED_TYPEN = (
    "application/rss+xml", "application/atom+xml", "application/rdf+xml",
    "application/xml", "text/xml",
)

_LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""(\w[\w:-]*)\s*=\s*("([^"]*)"|'([^']*)'|([^\s">]+))""")
_TITEL_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_ANKER_RE = re.compile(r"""<a\b[^>]+href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Adressen, die nach Feed aussehen - zweite Wahl nach den <link>-Tags.
_SIEHT_AUS = re.compile(
    r"(?:^|[/-])(?:rss|feed|atom)(?:\.xml|\.atom|/|$)"
    r"|\.(?:rss|atom)(?:$|\?)"
    r"|[?&](?:rss|feed)=1"
    r"|format=(?:rss|atom)",
    re.IGNORECASE)

# Typische Bot-Abwehr. Kein Feed-Problem, sondern ein Zugangsproblem -
# und das muss anders klingen, sonst sucht man an der falschen Stelle.
_WAND = (
    "just a moment", "checking your browser", "cf-browser-verification",
    "attention required", "enable javascript and cookies",
    "ddos protection by", "请稍候", "access denied",
)


@dataclass
class Feedlink:
    url: str
    titel: str | None = None
    typ: str | None = None
    herkunft: str = "link"          # "link" (ausgezeichnet) | "anker" (geraten)

    def als_dict(self) -> dict:
        return {"url": self.url, "titel": self.titel, "typ": self.typ,
                "herkunft": self.herkunft}


@dataclass
class Fund:
    """Was am Ende herauskam."""
    text: str
    url: str
    entdeckt: bool = False              # war die Adresse eine andere als gefragt?
    kandidaten: list[Feedlink] = field(default_factory=list)


class KeinFeed(ValueError):
    """Antwort war kein Feed - mit einer Begruendung, die weiterhilft."""

    def __init__(self, nachricht: str, *, kandidaten: list[Feedlink] | None = None):
        super().__init__(nachricht)
        self.kandidaten = kandidaten or []


# --- Erkennen --------------------------------------------------------------

def ist_feed(text: str) -> bool:
    """Sieht die Antwort nach RSS/Atom/RDF aus?

    Bewusst nur ein Blick auf den Anfang: ob der Feed *gueltig* ist,
    entscheidet spaeter der Parser. Hier geht es nur um die Frage
    "Feed oder Webseite", und die ist am ersten Tag ablesbar.
    """
    anfang = (text or "").lstrip("﻿ \t\r\n")[:2000].lower()
    if not anfang:
        return False
    if anfang.startswith("<!doctype html") or anfang.startswith("<html"):
        return False
    return any(marke in anfang for marke in
               ("<rss", "<feed", "<rdf:rdf", "<channel"))


def ist_wand(text: str) -> str | None:
    """Bot-Abwehr statt Inhalt? Gibt den erkannten Hinweis zurueck."""
    anfang = (text or "")[:4000].lower()
    for marke in _WAND:
        if marke in anfang:
            return marke
    return None


def seitentitel(html: str) -> str | None:
    treffer = _TITEL_RE.search(html or "")
    if not treffer:
        return None
    roh = re.sub(r"<[^>]+>", "", treffer.group(1))
    titel = re.sub(r"\s+", " ", html_mod.unescape(roh)).strip()
    return titel[:120] or None


def _attribute(tag: str) -> dict[str, str]:
    raus = {}
    for treffer in _ATTR_RE.finditer(tag):
        wert = treffer.group(3) or treffer.group(4) or treffer.group(5) or ""
        raus[treffer.group(1).lower()] = wert
    return raus


def finde_feeds(html: str, basis_url: str = "") -> list[Feedlink]:
    """Alle Feed-Adressen, die eine HTML-Seite nennt.

    Zuerst die ausgezeichneten `<link rel="alternate">` - das ist die
    Stelle, an der eine Seite ihre Feeds offiziell bekanntgibt. Erst
    danach Links im Text, die nach Feed aussehen; die sind Rateschluesse
    und darum als solche markiert.
    """
    gefunden: list[Feedlink] = []
    gesehen: set[str] = set()

    def dazu(href: str, titel: str | None, typ: str | None, herkunft: str) -> None:
        if not href:
            return
        voll = urljoin(basis_url, href.strip()) if basis_url else href.strip()
        if not voll.lower().startswith(("http://", "https://")):
            return
        if voll in gesehen:
            return
        gesehen.add(voll)
        gefunden.append(Feedlink(voll, titel or None, typ or None, herkunft))

    for tag in _LINK_RE.findall(html or ""):
        attr = _attribute(tag)
        rel = attr.get("rel", "").lower()
        typ = attr.get("type", "").lower()
        if "alternate" not in rel and "feed" not in rel:
            continue
        if typ and typ.split(";")[0].strip() not in FEED_TYPEN:
            continue
        if not typ and not _SIEHT_AUS.search(attr.get("href", "")):
            continue
        dazu(attr.get("href", ""), attr.get("title"), typ, "link")

    for href in _ANKER_RE.findall(html or ""):
        if _SIEHT_AUS.search(href):
            dazu(href, None, None, "anker")

    # Ausgezeichnete zuerst, sonst Reihenfolge der Seite.
    gefunden.sort(key=lambda f: 0 if f.herkunft == "link" else 1)
    return gefunden[:12]


# --- Holen -----------------------------------------------------------------

async def hole(http, url: str, *, cache_key: str | None = None) -> Fund:
    """Feed holen - und wenn eine Webseite kommt, den Feed darauf suchen.

    Wirft `KeinFeed` mit einer Begruendung, die sagt, was als Naechstes
    zu tun ist. Netzfehler reicht sie unveraendert durch: ein Timeout ist
    kein Feed-Problem.
    """
    text = await http.get_text(url, cache_key=cache_key)
    if ist_feed(text):
        return Fund(text, url)

    wand = ist_wand(text)
    titel = seitentitel(text)
    kandidaten = finde_feeds(text, url)

    if wand and not kandidaten:
        raise KeinFeed(
            f"Bot-Abwehr statt Inhalt ({wand!r}"
            + (f", Seitentitel {titel!r}" if titel else "") + "). "
            "Die Seite laesst diesen Server nicht durch - ein anderer Pfad "
            "hilft dagegen nicht.")

    for kandidat in kandidaten[:MAX_VERSUCHE]:
        if kandidat.url == url:
            continue
        try:
            versuch = await http.get_text(kandidat.url)
        except Exception as exc:                       # noqa: BLE001
            log.debug("Feed-Kandidat %s nicht erreichbar: %s", kandidat.url, exc)
            continue
        if ist_feed(versuch):
            log.info("Feed gefunden: %s -> %s", url, kandidat.url)
            return Fund(versuch, kandidat.url, entdeckt=True, kandidaten=kandidaten)

    raise KeinFeed(_begruendung(url, titel, kandidaten), kandidaten=kandidaten)


def _begruendung(url: str, titel: str | None, kandidaten: list[Feedlink]) -> str:
    wo = urlsplit(url).netloc or url
    kopf = (f"Der Server hat eine HTML-Seite geliefert, keinen Feed"
            + (f" (Seitentitel: {titel!r})" if titel else "") + ".")
    if not kandidaten:
        return (f"{kopf} Auf der Seite ist auch kein Feed ausgezeichnet - "
                f"unter dieser Adresse gibt es vermutlich keinen. Ruf die "
                f"Seite im Browser auf und such den Feed-Pfad; oder nimm "
                f"'Feed suchen' auf einer Uebersichtsseite von {wo}.")
    liste = ", ".join(k.url for k in kandidaten[:MAX_VERSUCHE])
    return (f"{kopf} Die Seite nennt zwar Feeds ({liste}), aber keiner davon "
            f"lieferte einen. Adresse hier korrigieren.")


async def suche(http, url: str) -> dict:
    """Fuer den Knopf 'Feed suchen': was bietet diese Adresse an?

    Ausdruecklich gutmuetig - sie wird auf alles losgelassen, was jemand
    in die Zwischenablage kopiert hat, und soll darauf eine brauchbare
    Antwort geben statt eines Stacktrace.
    """
    try:
        text = await http.get_text(url)
    except Exception as exc:                           # noqa: BLE001
        return {"ok": False, "url": url,
                "detail": f"Nicht erreichbar: {type(exc).__name__}: {exc}"[:300],
                "feeds": []}

    if ist_feed(text):
        return {"ok": True, "url": url, "ist_selbst_feed": True,
                "detail": "Diese Adresse ist bereits ein Feed.",
                "feeds": [Feedlink(url, seitentitel(text), None, "link").als_dict()]}

    wand = ist_wand(text)
    if wand:
        return {"ok": False, "url": url, "ist_selbst_feed": False,
                "detail": f"Bot-Abwehr statt Inhalt ({wand!r}). "
                          f"Die Seite laesst diesen Server nicht durch.",
                "feeds": []}

    feeds = finde_feeds(text, url)
    titel = seitentitel(text)
    if not feeds:
        return {"ok": False, "url": url, "ist_selbst_feed": False,
                "detail": f"Kein Feed ausgezeichnet"
                          + (f" (Seite: {titel!r})" if titel else "") + ".",
                "feeds": []}
    return {"ok": True, "url": url, "ist_selbst_feed": False,
            "detail": f"{len(feeds)} Feed-Adresse(n) gefunden"
                      + (f" auf {titel!r}" if titel else "") + ".",
            "feeds": [f.als_dict() for f in feeds]}
