"""Deal-Communities des Pepper-Netzwerks (mydealz, Preisjaeger, Dealabs,
HotUKDeals) - alle laufen auf derselben Plattform, also ein Parser.

WICHTIG - Verifizierungsstand: Diese Feed-Pfade konnten in der Build-Session
nicht live geprueft werden (Egress-Policy). Alle Pfade sind darum als Option
im UI editierbar. `Jetzt testen` im UI bzw. tools/verify_endpoints.py sagt
dir, welche wirklich liefern. Pepper-Seiten stehen zudem hinter Cloudflare -
gut moeglich, dass ein Teil der Feeds ohne Browser-Header blockt.

Weil die Pfade eben nicht geprueft sind, ist der wichtigste Teil dieser
Datei nicht die Vorbelegung, sondern was passiert, wenn sie danebenliegt.
Aus dem Betrieb kamen zwei Meldungen dieser Art:

    /gruppe/erotik-rss: KeinFeed: Der Server hat eine HTML-Seite geliefert
    /search?q=satisfyer&rss=1: KeinFeed: Der Server hat eine HTML-Seite …

Beides faengt jetzt `app/feedfinder.py` ab: es liest die Feed-Auszeichnung
der gelieferten Seite und probiert danach die bekannten Pepper-Muster
(`/rss/gruppe/<slug>`, `/rss/search?q=…`). Was wirklich einen Feed liefert,
schreibt die Quelle in ihre Einstellungen zurueck - bei Suchbegriffen nicht
nur die eine Adresse, sondern gleich die Vorlage fuer alle Begriffe.
"""
from __future__ import annotations

import re

from .. import feedfinder
from ..http import RateLimited
from ..priceparse import parse_price_text
from .base import Category, DealItem, FetchContext, OptionSpec, Source, Verification, register
from .rssutil import entry_body, entry_datetime, entry_tags, first_image, parse_feed, strip_html

# mydealz nennt die Deal-Temperatur im Titel oder Body als "123°".
_TEMP_RE = re.compile(r"(-?\d{1,4})\s*°")
_MERCHANT_RE = re.compile(r"\[(.*?)\]")

# In eckigen Klammern steht mal der Haendler ("[Amazon]"), mal eine Rubrik
# ("[Preisfehler]"). Rubriken als Haendler zu fuehren macht die
# Haendler-Statistik und Haendler-Filter unbrauchbar - deshalb aussortieren.
_KEINE_HAENDLER = {
    "preisfehler", "gratis", "kostenlos", "freebie", "deal", "hot", "sammeldeal",
    "angebot", "schnäppchen", "schnaeppchen", "info", "update", "abgelaufen",
    "lokal", "bundesweit", "neu", "tipp", "sparabo", "prime", "blitzangebot",
    "vorbestellung", "vorbestellbar", "ausverkauft", "nur heute", "letzte chance",
}


class PepperSource(Source):
    """Basis fuer alle Pepper-Seiten. Unterklassen setzen nur Host + Defaults."""

    base_url: str = ""
    category = Category.COMMUNITY
    default_interval = 600
    min_interval = 300
    verification = Verification.UNVERIFIED

    options_schema = [
        OptionSpec("feeds", "Feed-Pfade", "list", [],
                   help="Pfade relativ zur Domain, z.B. /rss/alle. Einer pro Zeile."),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", [],
                   help="Eigene Suchbegriffe; je Begriff wird ein Such-Feed abgefragt."),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/rss/search?q={term}",
                   help="{term} wird ersetzt. Welcher Weg gilt, ist von "
                        "Pepper-Seite zu Pepper-Seite verschieden - liefert "
                        "diese Vorlage HTML statt Feed, probiert SparBit die "
                        "anderen durch und traegt die passende hier ein."),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0,
                   help="0 = alles uebernehmen."),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        pfade = [str(p) for p in (ctx.opt("feeds") or [])]
        # Index mitfuehren, damit ein selbst gefundener Feed genau den
        # Pfad ersetzt, der daneben lag - und nicht irgendeinen. Der
        # Suchbegriff kommt mit, weil sich aus einer geheilten Such-Adresse
        # die Vorlage fuer alle weiteren Begriffe ableiten laesst.
        urls: list[tuple[int | None, str, str]] = [
            (i, self._abs(p), "") for i, p in enumerate(pfade)]

        tmpl = str(ctx.opt("search_path", "/rss/search?q={term}"))
        for term in (ctx.opt("search_terms") or []):
            begriff = str(term).strip()
            if not begriff:
                continue
            urls.append((None, self._abs(tmpl.format(term=begriff.replace(" ", "+"))),
                         begriff))

        if not urls:
            raise ValueError(
                "Keine Feeds konfiguriert. Trag unter 'Feed-Pfade' mindestens "
                "einen Pfad ein (z.B. /rss/alle)."
            )

        min_temp = float(ctx.opt("min_temperatur", 0) or 0)
        items: list[DealItem] = []
        errors: list[str] = []
        korrigiert: dict[int, str] = {}
        neue_vorlage: str | None = None
        gedrosselt: RateLimited | None = None

        for index, url, begriff in urls:
            try:
                fund = await feedfinder.hole(ctx.http, url,
                                             cache_key=f"{self.id}:{url}")
            except RateLimited as exc:
                # Der Host ist jetzt gesperrt; die restlichen Feeds wuerden
                # nur dieselbe Absage bekommen.
                gedrosselt = exc
                break
            except Exception as exc:  # eine kaputte Sub-Feed-URL kippt nicht alles
                errors.append(f"{url}: {type(exc).__name__}: {exc}"[:260])
                continue
            if fund.entdeckt:
                if index is not None:
                    korrigiert[index] = fund.url
                elif neue_vorlage is None and begriff:
                    neue_vorlage = self._vorlage(fund.url, begriff)
            items.extend(self.parse(fund.text, min_temp))

        if korrigiert:
            neu = list(pfade)
            for index, url in korrigiert.items():
                neu[index] = url
            ctx.merke("feeds", neu)
        # Eine Such-Adresse, die wirklich einen Feed geliefert hat, gilt ab
        # jetzt fuer alle Begriffe - sonst heilt sich jeder Begriff einzeln
        # und jeder kostet dabei jedes Mal dieselben Zusatz-Anfragen.
        if neue_vorlage and neue_vorlage != tmpl:
            ctx.merke("search_path", neue_vorlage)
            if ctx.log:
                ctx.log.info("%s: Such-Vorlage korrigiert: %s -> %s",
                             self.id, tmpl, neue_vorlage)

        if items:
            if errors and ctx.log:
                ctx.log.warning("%s: %d/%d Feeds fehlerhaft: %s",
                                self.id, len(errors), len(urls), errors[0])
            return items

        if gedrosselt is not None:
            raise gedrosselt
        if errors:
            text = " | ".join(errors[:3])
            if len(errors) > 3:
                text += f" | (+{len(errors) - 3} weitere)"
            raise RuntimeError(text)
        return items

    def _vorlage(self, gefunden: str, begriff: str) -> str | None:
        """Aus einer geheilten Such-Adresse die Vorlage zurueckrechnen.

        Beispiel: der Begriff war "satisfyer", gefunden wurde
        `https://www.mydealz.de/rss/search?q=satisfyer` - dann heisst die
        Vorlage `/rss/search?q={term}`.
        """
        kodiert = begriff.replace(" ", "+")
        if not kodiert or kodiert not in gefunden:
            return None
        stamm = self.base_url.rstrip("/")
        rel = gefunden[len(stamm):] if stamm and gefunden.startswith(stamm) else gefunden
        return (rel or "/").replace(kodiert, "{term}")

    def _abs(self, path: str) -> str:
        path = path.strip()
        if path.startswith("http"):
            return path
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def parse(self, text: str, min_temp: float = 0.0) -> list[DealItem]:
        feed = parse_feed(text)
        out: list[DealItem] = []
        for entry in feed.entries:
            title = strip_html(entry.get("title"), 400)
            link = entry.get("link")
            if not title or not link:
                continue

            body_html = entry_body(entry)
            body = strip_html(body_html)
            blob = f"{title} {body}"

            temp = None
            m = _TEMP_RE.search(blob)
            if m:
                try:
                    temp = float(m.group(1))
                except ValueError:
                    temp = None
            if min_temp and (temp is None or temp < min_temp):
                continue

            price = parse_price_text(blob)

            merchant = None
            mm = _MERCHANT_RE.search(title)
            if mm:
                kandidat = mm.group(1).strip()
                if kandidat and len(kandidat) <= 40 \
                        and kandidat.lower() not in _KEINE_HAENDLER:
                    merchant = kandidat

            out.append(DealItem(
                titel=title,
                url=link,
                quelle=self.id,
                beschreibung=body or None,
                preis=price.preis,
                originalpreis=price.originalpreis,
                rabatt_prozent=price.rabatt_prozent,
                waehrung=price.waehrung or self.default_currency,
                haendler=merchant,
                bild=first_image(entry, body_html),
                veroeffentlicht_am=entry_datetime(entry),
                temperatur=temp,
                tags=entry_tags(entry),
                ist_gratis=price.ist_gratis,
                kategorie="community",
                roh={"author": entry.get("author")},
            ))
        return out

    default_currency = "EUR"


class MyDealz(PepperSource):
    id = "mydealz"
    display_name = "mydealz.de"
    base_url = "https://www.mydealz.de"
    beschreibung = "Groesste deutsche Deal-Community. Gesamt-Feed, Gruppen und eigene Suchbegriffe."
    docs_url = "https://www.mydealz.de/"
    options_schema = [
        OptionSpec("feeds", "Feed-Pfade", "list",
                   ["/rss/alle", "/rss/hot",
                    "/gruppe/preisfehler", "/gruppe/gratis", "/gruppe/gaming"],
                   help="Feed-Adresse oder Seiten-Adresse - bei einer Seite "
                        "sucht SparBit den Feed selbst und traegt ihn hier "
                        "ein. Die Gruppen-Pfade sind darum die der Seite."),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", [],
                   help="z.B. lego, ssd, kopfhoerer"),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/rss/search?q={term}"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0),
    ]


class Preisjaeger(PepperSource):
    id = "preisjaeger"
    display_name = "Preisjaeger.at"
    base_url = "https://www.preisjaeger.at"
    beschreibung = "Oesterreichischer Pepper-Ableger."
    options_schema = [
        OptionSpec("feeds", "Feed-Pfade", "list", ["/rss/alle", "/rss/hot"]),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", []),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/rss/search?q={term}"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0),
    ]


class HotUKDeals(PepperSource):
    id = "hotukdeals"
    display_name = "HotUKDeals (UK)"
    base_url = "https://www.hotukdeals.com"
    beschreibung = "UK-Community - gut fuer internationale Preisfehler."
    default_currency = "GBP"
    options_schema = [
        OptionSpec("feeds", "Feed-Pfade", "list", ["/rss/all", "/rss/hot"]),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", []),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/rss/search?q={term}"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0),
    ]


class Dealabs(PepperSource):
    id = "dealabs"
    display_name = "Dealabs (FR)"
    base_url = "https://www.dealabs.com"
    beschreibung = "Franzoesische Community - internationale Preisfehler."
    options_schema = [
        OptionSpec("feeds", "Feed-Pfade", "list", ["/rss/alle", "/rss/hot"]),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", []),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/rss/search?q={term}"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0),
    ]


register(MyDealz())
register(Preisjaeger())
register(HotUKDeals())
register(Dealabs())
