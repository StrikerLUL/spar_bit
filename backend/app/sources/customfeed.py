"""Generische Feed-Quelle: beliebige RSS/Atom-URLs ohne Code-Aenderung.

Dafuer gedacht, Luecken zu schliessen, die diese Session nicht sauber
verifizieren konnte - z.B. eine Geizhals-Wunschliste als RSS, den Feed eines
Shops oder eine Gratis-Spiele-Seite. Du traegst nur URLs ein, die du selbst
geprueft hast; es wird nichts geraten.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .. import feedfinder
from ..http import RateLimited
from ..priceparse import parse_price_text
from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)
from .rssutil import (entry_body, entry_datetime, entry_tags, first_image,
                      parse_feed, strip_html)


class CustomFeed(Source):
    id = "custom_feed"
    display_name = "Eigene Feeds (RSS/Atom)"
    category = Category.EXPERIMENTAL
    default_interval = 900
    min_interval = 300
    experimental = True
    verification = Verification.UNVERIFIED
    beschreibung = ("Beliebige RSS/Atom-URLs. Gut fuer Geizhals-Wunschlisten "
                    "oder Shop-Feeds, die du selbst geprueft hast.")

    options_schema = [
        OptionSpec("feeds", "Feed-URLs", "list", [],
                   help="Eine vollstaendige URL pro Zeile."),
        OptionSpec("label", "Haendler-Label", "string", "",
                   help="Leer = Hostname der jeweiligen URL."),
        OptionSpec("max_items", "Max. Eintraege pro Feed", "int", 50),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        feeds = [f.strip() for f in (ctx.opt("feeds") or []) if str(f).strip()]
        if not feeds:
            raise ValueError("Keine Feed-URLs eingetragen.")
        label = ctx.opt("label", "")
        cap = int(ctx.opt("max_items", 50))

        items: list[DealItem] = []
        errors: list[str] = []
        korrigiert: dict[int, str] = {}
        gedrosselt: RateLimited | None = None
        drosselungen = 0
        for nummer, url in enumerate(feeds):
            try:
                fund = await feedfinder.hole(ctx.http, url,
                                             cache_key=f"custom:{url}")
                text = fund.text
                if fund.entdeckt:
                    korrigiert[nummer] = fund.url
                items.extend(self.parse(text, label or urlsplit(url).hostname or "")[:cap])
            except RateLimited as exc:
                # Wer drosselt, drosselt fuer alle Adressen dieses Hosts -
                # aber andere Hosts in der Liste koennen weiterlaufen.
                gedrosselt = exc
                drosselungen += 1
                errors.append(f"{url}: gedrosselt ({exc})")
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}"[:260])

        if korrigiert:
            neu = list(feeds)
            for nummer, url in korrigiert.items():
                neu[nummer] = url
            ctx.merke("feeds", neu)

        if not items and errors:
            if gedrosselt is not None and drosselungen == len(errors):
                # Nur gedrosselt, nichts kaputt: als RateLimited
                # weiterreichen, damit der Scheduler eine Pause macht statt
                # die Quelle als defekt zu zaehlen. Steht daneben ein echter
                # Fehler, gilt der - der waere sonst nicht zu sehen.
                raise gedrosselt
            text = " | ".join(errors[:3])
            if len(errors) > 3:
                text += f" | (+{len(errors) - 3} weitere)"
            raise RuntimeError(text)
        return items

    def parse(self, text: str, label: str = "") -> list[DealItem]:
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
                haendler=label or None,
                bild=first_image(entry, body_html),
                veroeffentlicht_am=entry_datetime(entry),
                tags=entry_tags(entry),
                ist_gratis=price.ist_gratis,
                kategorie="custom",
            ))
        return out


register(CustomFeed())
