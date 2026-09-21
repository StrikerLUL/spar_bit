"""Den Feed finden, statt seinen Pfad zu raten.

Der Anlass war eine Fehlermeldung aus dem Betrieb:

    https://www.mydealz.de/gruppe/erotik-rss:
    ValueError: Kein gueltiger Feed (SAXParseException).
    Anfang der Antwort: '<!DOCTYPE html><html class="no-js …

Der Pfad war geraten, und er war falsch. Drei Sachen sind daran zu lernen.

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

Die dritte kam aus dem zweiten Betriebsbericht und ist der Grund fuer den
zweiten Teil dieser Datei: **eine Seite muss ihren Feed nicht auszeichnen.**
Genau das macht mydealz auf seinen Gruppen-Seiten nicht, und dann half auch
das Auslesen nichts:

    KeinFeed: Der Server hat eine HTML-Seite geliefert, keinen Feed
    (Seitentitel: 'Erotik Angebote ⇒ Dessous, Sextoys günstig kaufen').
    Auf der Seite ist auch kein Feed ausgezeichnet.

Nur: unbekannt ist die Adresse deshalb nicht. Jede Shop- und
Community-Software legt ihre Feeds an derselben Handvoll Stellen ab -
Pepper (mydealz, Preisjaeger, Dealabs, HotUKDeals) unter `/rss/gruppe/…`,
WordPress unter `…/feed`, Shopify haengt `.atom` an jede Kollektion. Diese
Muster stehen jetzt in `muster()`, werden der Reihe nach durchprobiert, und
das Ergebnis wandert wieder in die Einstellungen. Geraten wird dabei nichts:
uebernommen wird nur, was tatsaechlich einen Feed zurueckgibt.

Damit das hoeflich bleibt, gilt eine harte Obergrenze (`MAX_MUSTER`) und
eine Sperrfrist: eine Adresse, bei der alle Muster durchgefallen sind, wird
eine Stunde lang nicht noch einmal durchprobiert. Der Feed-Pfad aendert sich
nicht im Minutentakt, die Quelle laeuft aber alle zehn.
"""
from __future__ import annotations

import html as html_mod
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import (parse_qsl, urlencode, urljoin, urlsplit, urlunsplit)

log = logging.getLogger(__name__)

# Wie viele ausgezeichnete Adressen hoechstens ausprobiert werden. Mehr
# waere gegenueber der fremden Seite unhoeflich - und wer drei Feeds
# anbietet, von denen keiner geht, hat ein anderes Problem.
MAX_VERSUCHE = 3

# Wie viele geratene Muster-Adressen hoechstens ausprobiert werden. Kleiner
# als man denkt, und mit Absicht: das hier laeuft bei jedem Fehlschlag
# wieder, und vier Zusatz-Anfragen alle zehn Minuten sind die Grenze dessen,
# was man einer fremden Seite zumuten darf.
MAX_MUSTER = 4

# So lange wird eine Adresse nach einem kompletten Fehlschlag nicht noch
# einmal mit Mustern durchprobiert. Der Erstabruf laeuft weiter - nur das
# Durchprobieren pausiert.
MUSTER_PAUSE = 3600.0

# Manche Server liefern unter derselben Adresse HTML oder Feed, je nachdem
# wonach gefragt wird. Fragen kostet nichts.
FEED_ACCEPT = ("application/rss+xml, application/atom+xml, application/xml;q=0.9, "
               "text/xml;q=0.9, text/html;q=0.5, */*;q=0.1")

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

# Gruppen-, Tag- und Kategorie-Seiten der Pepper-Plattform in allen vier
# Sprachvarianten, die SparBit anfaesst. Ein fuehrendes /rss gehoert dazu:
# auch wenn die eingetragene Adresse schon die Feed-Variante ist, sollen
# bei einem Fehlschlag die anderen Varianten drankommen.
_PEPPER_RE = re.compile(
    r"^(?:/rss)?/(gruppe|groupe|group|grupo|tag|tags|kategorie)/([^/?#]+)/?$",
    re.IGNORECASE)

# "…-rss" ist das Suffix, das frueher geraten wurde. Es bleibt hier stehen,
# weil es als *Kandidat* weiterhin sinnvoll ist - nur nicht mehr als Wahrheit.
_RSS_SUFFIX = re.compile(r"-(?:rss|feed|atom)$", re.IGNORECASE)

# Dateiendungen, hinter denen ein Verzeichnis-Muster keinen Sinn ergibt.
_SEITENDATEI = re.compile(r"\.(?:html?|php|aspx?|jsp)$", re.IGNORECASE)

# Typische Bot-Abwehr. Kein Feed-Problem, sondern ein Zugangsproblem -
# und das muss anders klingen, sonst sucht man an der falschen Stelle.
_WAND = (
    "just a moment", "checking your browser", "cf-browser-verification",
    "attention required", "enable javascript and cookies",
    "ddos protection by", "请稍候", "access denied",
)

# HTTP-Antworten, bei denen ein anderer Pfad helfen kann. 404 heisst "hier
# nicht", nicht "nirgends"; 403/406 kommt oefter von einer Weiche, die HTML
# erwartet hat. Bei 429 oder 5xx waere Weiterprobieren nur unhoeflich.
_PFADFEHLER = (400, 401, 403, 404, 406, 410, 415)


@dataclass
class Feedlink:
    url: str
    titel: str | None = None
    typ: str | None = None
    herkunft: str = "link"          # "link" (ausgezeichnet) | "anker" (geraten)
                                    # | "muster" (bekanntes Software-Muster)

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


# --- Raten, aber mit System ------------------------------------------------

def muster(url: str) -> list[str]:
    """Adressen, unter denen bei dieser Software erfahrungsgemaess ein Feed liegt.

    Das ist die Antwort auf den Fall, den `finde_feeds` nicht loesen kann:
    eine Seite, die ihren Feed nicht auszeichnet. Statt zu kapitulieren
    werden die Stellen abgeklappert, an denen die jeweilige Software ihren
    Feed ueblicherweise ablegt.

    Wichtig fuer das Verstaendnis: das hier ist eine **Kandidatenliste**,
    keine Behauptung. Uebernommen wird nur, was beim Abruf tatsaechlich
    einen Feed liefert - und die Liste ist absichtlich kurz.
    """
    teile = urlsplit(url)
    if not teile.scheme.lower().startswith("http") or not teile.netloc:
        return []

    pfad = teile.path or "/"
    raus: list[str] = []

    def dazu(neuer_pfad: str, query: str = "") -> None:
        neu = urlunsplit((teile.scheme, teile.netloc, neuer_pfad or "/", query, ""))
        if neu != url and neu not in raus:
            raus.append(neu)

    # 1. Pepper-Gruppen: /gruppe/erotik -> /rss/gruppe/erotik
    #    Ein evtl. schon angehaengtes "-rss" kommt vorher weg, sonst wuerde
    #    aus einem falschen Pfad ein doppelt falscher.
    treffer = _PEPPER_RE.match(pfad)
    if treffer:
        art, slug = treffer.group(1).lower(), _RSS_SUFFIX.sub("", treffer.group(2))
        # Die eingetragene Adresse faellt in `dazu` von selbst raus - uebrig
        # bleiben genau die Varianten, die noch nicht probiert wurden.
        dazu(f"/rss/{art}/{slug}")
        dazu(f"/{art}/{slug}-rss")
        dazu(f"/{art}/{slug}", "rss=1")
        dazu(f"/rss/{slug}")
        return raus[:MAX_MUSTER]

    # 2. Suchergebnisse als Feed. Welcher der drei Wege gilt, ist von
    #    Pepper-Seite zu Pepper-Seite verschieden - darum alle drei.
    query_paare = parse_qsl(teile.query, keep_blank_values=True)
    stamm = pfad.rstrip("/")
    if query_paare and stamm.lower().endswith(("/search", "/suche", "/recherche")):
        rest = [(k, v) for k, v in query_paare
                if k.lower() not in ("rss", "feed", "format")]
        sauber = urlencode(rest)
        # Ein schon vorhandenes /rss-Praefix abziehen, sonst entstuende
        # /rss/rss/search - eine Adresse, die es nirgends gibt.
        nackt = stamm[4:] if stamm.lower().startswith("/rss/") else stamm
        dazu("/rss" + nackt, sauber)
        dazu(nackt, sauber + ("&" if sauber else "") + "rss=1")
        dazu(nackt + "/rss", sauber)
        dazu(nackt + ".rss", sauber)
        return raus[:MAX_MUSTER]

    # 3. Alles andere: die ueblichen Stellen einer Shop- oder Blog-Software.
    if _SEITENDATEI.search(stamm):
        stamm = stamm.rsplit("/", 1)[0]

    # Shopify haengt an jede Kollektion ein .atom - das ist der zuverlaessigste
    # Feed im ganzen Shop-Umfeld und kommt darum zuerst.
    if re.match(r"^/collections/[^/]+$", stamm, re.IGNORECASE):
        dazu(stamm + ".atom")
    elif not stamm:
        dazu("/collections/all.atom")

    for endung in ("/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml"):
        dazu(stamm + endung)
    return raus[:MAX_MUSTER]


# Adressen, bei denen zuletzt kein Muster gegriffen hat: monotone Uhr ->
# Zeitpunkt. Verhindert, dass eine tote Adresse alle zehn Minuten vier
# zusaetzliche Anfragen erzeugt.
_muster_pause: dict[str, float] = {}


def _pausiert(url: str) -> bool:
    bis = _muster_pause.get(url)
    if bis is None:
        return False
    if bis > time.monotonic():
        return True
    _muster_pause.pop(url, None)
    return False


def _pausieren(url: str) -> None:
    _muster_pause[url] = time.monotonic() + MUSTER_PAUSE
    # Die Tabelle darf nicht unbegrenzt wachsen; abgelaufene raus.
    if len(_muster_pause) > 512:
        jetzt = time.monotonic()
        for schluessel in [k for k, v in _muster_pause.items() if v <= jetzt]:
            _muster_pause.pop(schluessel, None)


def pause_zuruecksetzen(praefix: str | None = None) -> None:
    """Sperrfristen vergessen - fuer 'Jetzt testen' und fuer Tests.

    Wer im UI auf den Knopf drueckt, will jetzt eine Antwort und nicht die
    von vor einer Stunde. Mit `praefix` gilt das nur fuer die Adressen
    einer Seite: eine Quelle zu testen ist kein Grund, die Schonfrist aller
    anderen Hosts aufzuheben - die haben davon nichts als zusaetzliche
    Anfragen.
    """
    if not praefix:
        _muster_pause.clear()
        return
    for schluessel in [k for k in _muster_pause if k.startswith(praefix)]:
        _muster_pause.pop(schluessel, None)


def _status(exc: Exception) -> int | None:
    """HTTP-Status einer Fehler-Ausnahme, falls sie einen traegt."""
    antwort = getattr(exc, "response", None)
    code = getattr(antwort, "status_code", None)
    return int(code) if isinstance(code, int) else None


def _ist_pfadfehler(exc: Exception) -> bool:
    code = _status(exc)
    return code in _PFADFEHLER if code is not None else False


# --- Holen -----------------------------------------------------------------

async def _probiere(http, kandidaten: list[Feedlink], original: str,
                    gefunden: list[Feedlink] | None = None) -> Fund | None:
    """Kandidaten der Reihe nach abrufen, bis einer einen Feed liefert."""
    for kandidat in kandidaten:
        if kandidat.url == original:
            continue
        try:
            versuch = await http.get_text(kandidat.url,
                                          headers={"Accept": FEED_ACCEPT})
        except Exception as exc:                       # noqa: BLE001
            log.debug("Feed-Kandidat %s nicht erreichbar: %s", kandidat.url, exc)
            continue
        if ist_feed(versuch):
            log.info("Feed gefunden (%s): %s -> %s",
                     kandidat.herkunft, original, kandidat.url)
            return Fund(versuch, kandidat.url, entdeckt=True,
                        kandidaten=gefunden or kandidaten)
    return None


async def _muster_probieren(http, url: str,
                            gefunden: list[Feedlink] | None = None) -> Fund | None:
    """Die bekannten Software-Muster durchgehen - hoechstens `MAX_MUSTER`."""
    kandidaten = [Feedlink(m, None, None, "muster") for m in muster(url)]
    if not kandidaten:
        return None
    return await _probiere(http, kandidaten, url, gefunden)


async def hole(http, url: str, *, cache_key: str | None = None,
               mit_mustern: bool = True) -> Fund:
    """Feed holen - und wenn eine Webseite kommt, den Feed darauf suchen.

    Drei Stufen, in dieser Reihenfolge:

    1. Die Adresse selbst. Liefert sie einen Feed, ist alles gut.
    2. Was die gelieferte Seite an Feeds auszeichnet (`<link rel=alternate>`).
    3. Die bekannten Muster der jeweiligen Software (`muster()`).

    Wirft `KeinFeed` mit einer Begruendung, die sagt, was als Naechstes
    zu tun ist. Netzfehler reicht sie unveraendert durch: ein Timeout ist
    kein Feed-Problem. `mit_mustern=False` schaltet Stufe 3 ab - sinnvoll
    ueberall dort, wo die Adresse nachweislich stimmt und ein 404 wirklich
    "gibt es nicht" heisst (Reddit-Subreddits zum Beispiel).
    """
    try:
        text = await http.get_text(url, cache_key=cache_key,
                                   headers={"Accept": FEED_ACCEPT})
    except Exception as exc:                           # noqa: BLE001
        # 404 auf einem geratenen Pfad heisst "hier nicht", nicht "nirgends".
        if mit_mustern and _ist_pfadfehler(exc) and not _pausiert(url):
            fund = await _muster_probieren(http, url)
            if fund is not None:
                return fund
            _pausieren(url)
        raise

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

    fund = await _probiere(http, kandidaten[:MAX_VERSUCHE], url, kandidaten)
    if fund is not None:
        return fund

    # Die Seite zeichnet nichts aus (oder das Ausgezeichnete ging nicht) -
    # jetzt die Stellen abklappern, an denen diese Software ihren Feed hat.
    probiert: list[str] = []
    if mit_mustern and not wand and not _pausiert(url):
        probiert = muster(url)
        fund = await _muster_probieren(http, url, kandidaten)
        if fund is not None:
            return fund
        _pausieren(url)

    raise KeinFeed(_begruendung(url, titel, kandidaten, probiert),
                   kandidaten=kandidaten)


def _begruendung(url: str, titel: str | None, kandidaten: list[Feedlink],
                 probiert: list[str] | None = None) -> str:
    wo = urlsplit(url).netloc or url
    kopf = (f"Der Server hat eine HTML-Seite geliefert, keinen Feed"
            + (f" (Seitentitel: {titel!r})" if titel else "") + ".")
    if kandidaten:
        liste = ", ".join(k.url for k in kandidaten[:MAX_VERSUCHE])
        return (f"{kopf} Die Seite nennt zwar Feeds ({liste}), aber keiner davon "
                f"lieferte einen. Adresse hier korrigieren.")
    schwanz = (f"Ruf die Seite im Browser auf und such den Feed-Pfad; oder nimm "
               f"'Feed suchen' auf einer Uebersichtsseite von {wo}.")
    if probiert:
        return (f"{kopf} Auf der Seite ist auch kein Feed ausgezeichnet, und die "
                f"ueblichen Adressen ({', '.join(probiert)}) lieferten ebenfalls "
                f"keinen. {schwanz}")
    return (f"{kopf} Auf der Seite ist auch kein Feed ausgezeichnet - "
            f"unter dieser Adresse gibt es vermutlich keinen. {schwanz}")


async def suche(http, url: str) -> dict:
    """Fuer den Knopf 'Feed suchen': was bietet diese Adresse an?

    Ausdruecklich gutmuetig - sie wird auf alles losgelassen, was jemand
    in die Zwischenablage kopiert hat, und soll darauf eine brauchbare
    Antwort geben statt eines Stacktrace. Zeichnet die Seite nichts aus,
    werden - wie beim Abruf - die bekannten Muster durchprobiert; was davon
    wirklich einen Feed liefert, steht danach zum Uebernehmen bereit.
    """
    try:
        text = await http.get_text(url, headers={"Accept": FEED_ACCEPT})
    except Exception as exc:                           # noqa: BLE001
        if _ist_pfadfehler(exc):
            fund = await _muster_probieren(http, url)
            if fund is not None:
                return {"ok": True, "url": url, "ist_selbst_feed": False,
                        "detail": f"Unter der Adresse selbst kam "
                                  f"{_status(exc) or 'ein Fehler'} - der Feed "
                                  f"liegt unter {fund.url}.",
                        "feeds": [Feedlink(fund.url, seitentitel(fund.text),
                                           None, "muster").als_dict()]}
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
    if feeds:
        return {"ok": True, "url": url, "ist_selbst_feed": False,
                "detail": f"{len(feeds)} Feed-Adresse(n) gefunden"
                          + (f" auf {titel!r}" if titel else "") + ".",
                "feeds": [f.als_dict() for f in feeds]}

    # Nichts ausgezeichnet: die ueblichen Stellen abklappern. Was antwortet,
    # ist eine gepruefte Adresse - nicht geraten.
    fund = await _muster_probieren(http, url)
    if fund is not None:
        return {"ok": True, "url": url, "ist_selbst_feed": False,
                "detail": f"Kein Feed ausgezeichnet"
                          + (f" (Seite: {titel!r})" if titel else "")
                          + f" - aber unter {fund.url} liegt einer.",
                "feeds": [Feedlink(fund.url, seitentitel(fund.text), None,
                                   "muster").als_dict()]}

    versucht = muster(url)
    return {"ok": False, "url": url, "ist_selbst_feed": False,
            "detail": (f"Kein Feed ausgezeichnet"
                       + (f" (Seite: {titel!r})" if titel else "") + "."
                       + (f" Auch die ueblichen Adressen ({', '.join(versucht)}) "
                          f"lieferten keinen." if versucht else "")),
            "feeds": []}
