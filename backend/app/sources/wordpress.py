"""Blog-artige Deal-Seiten mit klassischem WordPress-Feed
(Sparhamster.at, Schnaeppchenfuchs).

Verifizierungsstand: UNVERIFIED - in der Build-Session nicht live pruefbar.
Feed-URL ist als Option editierbar.
"""
from __future__ import annotations

from ..priceparse import parse_price_text
from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)
from .rssutil import (entry_body, entry_datetime, entry_tags, first_image,
                      parse_feed, strip_html)


class WordpressDealSource(Source):
    category = Category.COMMUNITY
    default_interval = 900
    min_interval = 600
    verification = Verification.UNVERIFIED
    feed_url: str = ""

    @property
    def options_schema(self):  # type: ignore[override]
        return [
            OptionSpec("feed_url", "Feed-URL", "string", self.feed_url,
                       help="Standard-WordPress-Feed. Mit 'Jetzt testen' pruefen."),
            OptionSpec("max_items", "Max. Eintraege pro Lauf", "int", 60),
        ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        url = ctx.opt("feed_url", self.feed_url)
        if not url:
            raise ValueError("Keine Feed-URL konfiguriert.")
        text = await ctx.http.get_text(url, cache_key=f"{self.id}:{url}")
        return self.parse(text)[: int(ctx.opt("max_items", 60))]

    def parse(self, text: str) -> list[DealItem]:
        feed = parse_feed(text)
        out: list[DealItem] = []
        for entry in feed.entries:
            title = strip_html(entry.get("title"), 400)
            link = entry.get("link")
            if not title or not link:
                continue
            body_html = entry_body(entry)
            body = strip_html(body_html)
            price = parse_price_text(f"{title} {body}")
            out.append(DealItem(
                titel=title,
                url=link,
                quelle=self.id,
                beschreibung=body or None,
                preis=price.preis,
                originalpreis=price.originalpreis,
                rabatt_prozent=price.rabatt_prozent,
                waehrung=price.waehrung or "EUR",
                bild=first_image(entry, body_html),
                veroeffentlicht_am=entry_datetime(entry),
                tags=entry_tags(entry),
                ist_gratis=price.ist_gratis,
                kategorie="community",
            ))
        return out


class Sparhamster(WordpressDealSource):
    id = "sparhamster"
    display_name = "Sparhamster.at"
    feed_url = "https://www.sparhamster.at/feed/"
    beschreibung = "Oesterreichischer Schnaeppchen-Blog."


class Schnaeppchenfuchs(WordpressDealSource):
    id = "schnaeppchenfuchs"
    display_name = "Schnaeppchenfuchs.com"
    feed_url = "https://www.schnaeppchenfuchs.com/feed"
    beschreibung = "Deutscher Schnaeppchen-Blog."


register(Sparhamster())
register(Schnaeppchenfuchs())
