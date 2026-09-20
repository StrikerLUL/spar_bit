"""Deal-Communities des Pepper-Netzwerks (mydealz, Preisjaeger, Dealabs,
HotUKDeals) - alle laufen auf derselben Plattform, also ein Parser.

WICHTIG - Verifizierungsstand: Diese Feed-Pfade konnten in der Build-Session
nicht live geprueft werden (Egress-Policy). Alle Pfade sind darum als Option
im UI editierbar. `Jetzt testen` im UI bzw. tools/verify_endpoints.py sagt
dir, welche wirklich liefern. Pepper-Seiten stehen zudem hinter Cloudflare -
gut moeglich, dass ein Teil der Feeds ohne Browser-Header blockt.
"""
from __future__ import annotations

import re

from .. import feedfinder
from ..priceparse import parse_price_text
from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)
from .rssutil import (entry_body, entry_datetime, entry_tags, first_image,
                      parse_feed, strip_html)

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
                   "/search?q={term}&rss=1",
                   help="{term} wird ersetzt. Anpassen falls die Seite es anders macht."),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0,
                   help="0 = alles uebernehmen."),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        pfade = [str(p) for p in (ctx.opt("feeds") or [])]
        # Index mitfuehren, damit ein selbst gefundener Feed genau den
        # Pfad ersetzt, der daneben lag - und nicht irgendeinen.
        urls: list[tuple[int | None, str]] = [
            (i, self._abs(p)) for i, p in enumerate(pfade)]

        tmpl = ctx.opt("search_path", "/search?q={term}&rss=1")
        for term in (ctx.opt("search_terms") or []):
            urls.append((None,
                         self._abs(tmpl.format(term=term.strip().replace(" ", "+")))))

        if not urls:
            raise ValueError(
                "Keine Feeds konfiguriert. Trag unter 'Feed-Pfade' mindestens "
                "einen Pfad ein (z.B. /rss/alle)."
            )

        min_temp = float(ctx.opt("min_temperatur", 0) or 0)
        items: list[DealItem] = []
        errors: list[str] = []
        korrigiert: dict[int, str] = {}

        for index, url in urls:
            try:
                fund = await feedfinder.hole(ctx.http, url,
                                             cache_key=f"{self.id}:{url}")
            except Exception as exc:  # eine kaputte Sub-Feed-URL kippt nicht alles
                errors.append(f"{url}: {type(exc).__name__}: {exc}"[:260])
                continue
            if fund.entdeckt and index is not None:
                korrigiert[index] = fund.url
            items.extend(self.parse(fund.text, min_temp))

        if korrigiert:
            neu = list(pfade)
            for index, url in korrigiert.items():
                neu[index] = url
            ctx.merke("feeds", neu)

        if not items and errors:
            raise RuntimeError(" | ".join(errors[:3]))
        if errors and ctx.log:
            ctx.log.warning("%s: %d/%d Feeds fehlerhaft: %s",
                            self.id, len(errors), len(urls), errors[0])
        return items

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
                   "/search?q={term}&rss=1"),
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
                   "/search?q={term}&rss=1"),
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
                   "/search?q={term}&rss=1"),
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
                   "/search?q={term}&rss=1"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0),
    ]


register(MyDealz())
register(Preisjaeger())
register(HotUKDeals())
register(Dealabs())
