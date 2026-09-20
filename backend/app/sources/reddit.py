"""Reddit ueber die oeffentlichen .rss-Endpunkte.

Subreddits sind im UI pflegbar. Kein API-Key noetig, aber Reddit ist bei
Cloud-/Rechenzentrums-IPs streng: erwarte 403/429, wenn der VPS in einem
bekannten Hosting-Netz steht. Der Circuit Breaker faengt das ab, und der
User-Agent ist bewusst sprechend (das verlangt Reddit ausdruecklich).

Verifizierungsstand: UNVERIFIED - in der Build-Session nicht live pruefbar.
"""
from __future__ import annotations

import re

from .. import feedfinder
from ..priceparse import parse_price_text
from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)
from .rssutil import (entry_body, entry_datetime, first_image, parse_feed,
                      strip_html)

# r/GameDeals-Konvention: "[Steam] Titel (75% off / 4,99€)"
_STORE_RE = re.compile(r"^\s*\[([^\]]{1,40})\]")


class Reddit(Source):
    id = "reddit"
    display_name = "Reddit"
    category = Category.REDDIT
    default_interval = 600
    min_interval = 300
    verification = Verification.UNVERIFIED
    docs_url = "https://www.reddit.com/wiki/api"
    beschreibung = ("Oeffentliche .rss-Feeds mehrerer Subreddits. "
                    "Subreddits hier pflegbar.")

    options_schema = [
        OptionSpec("subreddits", "Subreddits", "list",
                   ["GameDeals", "FreeGameFindings", "freebies",
                    "googleplaydeals", "AppHookup", "Schnaeppchen"],
                   help="Ohne 'r/'. Einer pro Zeile."),
        OptionSpec("listing", "Sortierung", "select", "new",
                   choices=["new", "hot", "top"],
                   help="new = alles sofort, hot = nur was Zulauf hat."),
        OptionSpec("base", "Basis-Host", "string", "https://www.reddit.com",
                   help="Alternative: https://old.reddit.com"),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        subs = ctx.opt("subreddits") or []
        if not subs:
            raise ValueError("Keine Subreddits konfiguriert.")
        listing = ctx.opt("listing", "new")
        base = str(ctx.opt("base", "https://www.reddit.com")).rstrip("/")

        items: list[DealItem] = []
        errors: list[str] = []
        for sub in subs:
            sub = str(sub).strip().lstrip("r/").strip("/")
            if not sub:
                continue
            url = f"{base}/r/{sub}/{listing}/.rss"
            try:
                fund = await feedfinder.hole(
                    ctx.http, url, cache_key=f"{self.id}:{sub}:{listing}")
                items.extend(self.parse(fund.text, sub))
            except Exception as exc:
                errors.append(f"r/{sub}: {type(exc).__name__}: {exc}"[:260])

        if not items and errors:
            raise RuntimeError(" | ".join(errors[:3]))
        if errors and ctx.log:
            ctx.log.warning("%s: %d Subreddits fehlerhaft: %s",
                            self.id, len(errors), errors[0])
        return items

    def parse(self, text: str, sub: str = "") -> list[DealItem]:
        feed = parse_feed(text)
        out: list[DealItem] = []
        for entry in feed.entries:
            title = strip_html(entry.get("title"), 400)
            link = entry.get("link")
            if not title or not link:
                continue
            body_html = entry_body(entry)
            body = strip_html(body_html, 800)
            price = parse_price_text(title)     # Reddit-Titel tragen den Preis
            if price.preis is None:
                price = parse_price_text(f"{title} {body}")

            store = None
            m = _STORE_RE.match(title)
            if m:
                store = m.group(1).strip()

            out.append(DealItem(
                titel=title,
                url=link,
                quelle=self.id,
                beschreibung=body or None,
                preis=price.preis,
                originalpreis=price.originalpreis,
                rabatt_prozent=price.rabatt_prozent,
                waehrung=price.waehrung or "EUR",
                haendler=store,
                bild=first_image(entry, body_html),
                veroeffentlicht_am=entry_datetime(entry),
                tags=[f"r/{sub}"] if sub else [],
                ist_gratis=price.ist_gratis,
                kategorie="reddit",
                roh={"subreddit": sub, "author": entry.get("author")},
            ))
        return out


register(Reddit())
