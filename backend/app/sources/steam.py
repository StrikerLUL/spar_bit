"""Steam Storefront - 100%-Aktionen, Specials und Free Weekends.

Nutzt die offiziellen Storefront-Endpoints (featuredcategories, appdetails).
Verifizierungsstand: UNVERIFIED. Steam drosselt appdetails hart (grob
~200 Requests / 5 Min pro IP), darum wird pro Lauf nur eine begrenzte Zahl
Detail-Abfragen gemacht und zwischen den Aufrufen gewartet.
"""
from __future__ import annotations

import asyncio

from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)

_APP_URL = "https://store.steampowered.com/app/{appid}/"


class Steam(Source):
    id = "steam"
    display_name = "Steam"
    category = Category.GAMING
    default_interval = 3600
    min_interval = 1800
    verification = Verification.UNVERIFIED
    docs_url = "https://store.steampowered.com/"
    beschreibung = "Specials aus featuredcategories, optional mit appdetails angereichert."

    options_schema = [
        OptionSpec("featured_endpoint", "featuredcategories-Endpoint", "string",
                   "https://store.steampowered.com/api/featuredcategories"),
        OptionSpec("appdetails_endpoint", "appdetails-Endpoint", "string",
                   "https://store.steampowered.com/api/appdetails"),
        OptionSpec("cc", "Laendercode", "string", "de"),
        OptionSpec("language", "Sprache", "string", "german"),
        OptionSpec("min_discount", "Nur ab Rabatt %", "int", 50,
                   help="Steam liefert viele Kleinrabatte - hier filtern."),
        OptionSpec("enrich_limit", "Max. appdetails-Abfragen pro Lauf", "int", 15,
                   help="Rate-Limit-Schutz. 0 = keine Detail-Abfragen."),
        OptionSpec("enrich_delay", "Pause zwischen appdetails (Sek.)", "int", 2),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        cc = ctx.opt("cc", "de")
        lang = ctx.opt("language", "german")
        url = f"{ctx.opt('featured_endpoint')}?cc={cc}&l={lang}"
        data = await ctx.http.get_json(url, cache_key="steam:featured")

        min_disc = float(ctx.opt("min_discount", 50) or 0)
        items = self.parse_featured(data, min_disc)

        limit = int(ctx.opt("enrich_limit", 15) or 0)
        if limit:
            await self._enrich(ctx, items[:limit], cc, lang)
        return items

    def parse_featured(self, data: dict, min_discount: float = 0.0) -> list[DealItem]:
        """featuredcategories liefert mehrere Buckets - wir nehmen alle, die
        Items mit Rabatt enthalten."""
        seen: set[int] = set()
        out: list[DealItem] = []

        for bucket_name, bucket in (data or {}).items():
            if not isinstance(bucket, dict):
                continue
            entries = bucket.get("items")
            if not isinstance(entries, list):
                continue
            for it in entries:
                if not isinstance(it, dict):
                    continue
                appid = it.get("id")
                if not appid or appid in seen:
                    continue

                discount = float(it.get("discount_percent") or 0)
                final = it.get("final_price")
                orig = it.get("original_price")
                free_flag = bool(it.get("discounted")) and final == 0

                if discount < min_discount and not free_flag:
                    continue
                seen.add(appid)

                currency = it.get("currency") or "EUR"
                preis = round(final / 100, 2) if isinstance(final, int) else None
                originalpreis = round(orig / 100, 2) if isinstance(orig, int) else None

                out.append(DealItem(
                    titel=(it.get("name") or f"Steam App {appid}").strip(),
                    url=_APP_URL.format(appid=appid),
                    quelle=self.id,
                    preis=preis,
                    originalpreis=originalpreis,
                    rabatt_prozent=discount or None,
                    waehrung=currency,
                    haendler="Steam",
                    bild=it.get("large_capsule_image") or it.get("header_image")
                         or it.get("small_capsule_image"),
                    tags=["steam", bucket_name],
                    ist_gratis=(preis == 0.0) or discount >= 100,
                    kategorie="gaming",
                    roh={"appid": appid, "bucket": bucket_name},
                ))
        out.sort(key=lambda d: d.rabatt_prozent or 0, reverse=True)
        return out

    async def _enrich(self, ctx: FetchContext, items: list[DealItem],
                      cc: str, lang: str) -> None:
        """Beschreibung + Genres nachladen. Fehler hier sind egal."""
        endpoint = ctx.opt("appdetails_endpoint")
        delay = float(ctx.opt("enrich_delay", 2) or 0)
        for item in items:
            appid = item.roh.get("appid")
            if not appid:
                continue
            try:
                url = f"{endpoint}?appids={appid}&cc={cc}&l={lang}"
                data = await ctx.http.get_json(url, cache_key=None)
                node = (data or {}).get(str(appid)) or {}
                if not node.get("success"):
                    continue
                d = node.get("data") or {}
                item.beschreibung = (d.get("short_description") or "")[:800] or None
                genres = [g.get("description") for g in (d.get("genres") or [])
                          if g.get("description")]
                item.tags = list(dict.fromkeys(item.tags + genres[:4]))
                if d.get("is_free"):
                    item.ist_gratis = True
            except Exception as exc:
                if ctx.log:
                    ctx.log.debug("steam appdetails %s: %s", appid, exc)
            if delay:
                await asyncio.sleep(delay)


register(Steam())
