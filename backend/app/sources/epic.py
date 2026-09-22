"""Epic Games Store - freeGamesPromotions.

Verifizierungsstand: UNVERIFIED (Egress-Policy in der Build-Session).
Host + Query sind als Option editierbar, falls Epic den Endpoint verschiebt.
"""
from __future__ import annotations

from datetime import UTC, datetime

from .base import Category, DealItem, FetchContext, OptionSpec, Source, Verification, register

_STORE_BASE = "https://store.epicgames.com/de/p/"


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class EpicFreeGames(Source):
    id = "epic"
    display_name = "Epic Games Store"
    category = Category.GAMING
    default_interval = 3600
    min_interval = 900
    verification = Verification.UNVERIFIED
    docs_url = "https://store.epicgames.com/de/free-games"
    beschreibung = "Woechentliche Gratis-Spiele + aktuelle Promo-Aktionen."

    options_schema = [
        OptionSpec("endpoint", "Endpoint", "string",
                   "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"),
        OptionSpec("locale", "Locale", "string", "de-DE"),
        OptionSpec("country", "Land", "string", "DE"),
        OptionSpec("include_upcoming", "Kommende Gratis-Spiele mitnehmen", "bool", True),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        base = ctx.opt("endpoint")
        locale = ctx.opt("locale", "de-DE")
        country = ctx.opt("country", "DE")
        url = f"{base}?locale={locale}&country={country}&allowCountries={country}"
        data = await ctx.http.get_json(url, cache_key="epic:free")
        return self.parse(data, bool(ctx.opt("include_upcoming", True)))

    def parse(self, data: dict, include_upcoming: bool = True) -> list[DealItem]:
        elements = (
            data.get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
        )
        now = datetime.now(UTC)
        out: list[DealItem] = []

        for el in elements:
            title = (el.get("title") or "").strip()
            if not title or title.lower() == "mystery game":
                continue

            promos = el.get("promotions") or {}
            current = promos.get("promotionalOffers") or []
            upcoming = promos.get("upcomingPromotionalOffers") or []

            offer, is_upcoming = self._pick_offer(current, now), False
            if offer is None and include_upcoming:
                offer, is_upcoming = self._pick_offer(upcoming, now, future=True), True
            if offer is None:
                continue

            discount_pct = offer.get("discountSetting", {}).get("discountPercentage")
            # Epic: 0 == 100 % Rabatt (Preis wird auf 0 gesetzt).
            free = discount_pct == 0

            price_info = (el.get("price") or {}).get("totalPrice") or {}
            decimals = (price_info.get("currencyCode") and price_info.get("decimals", 2)) or 2
            orig_cents = price_info.get("originalPrice")
            disc_cents = price_info.get("discountPrice")
            factor = 10 ** (decimals or 2)
            originalpreis = round(orig_cents / factor, 2) if orig_cents is not None else None
            preis = round(disc_cents / factor, 2) if disc_cents is not None else None
            # Nur eine LAUFENDE Aktion setzt den Preis auf 0. Ein Titel, der
            # erst naechste Woche gratis wird, darf keine Gratis-Regel
            # ausloesen - sonst kommt die Meldung sieben Tage zu frueh.
            if free and not is_upcoming:
                preis = 0.0

            tags = ["epic"]
            if is_upcoming:
                tags.append("demnaechst")
            else:
                tags.append("gratis" if free else "rabatt")

            out.append(DealItem(
                titel=title,
                url=self._store_url(el),
                quelle=self.id,
                beschreibung=(el.get("description") or "").strip()[:800] or None,
                preis=preis,
                originalpreis=originalpreis,
                rabatt_prozent=100.0 if (free and not is_upcoming) else None,
                waehrung=price_info.get("currencyCode") or "EUR",
                haendler="Epic Games Store",
                bild=self._image(el),
                veroeffentlicht_am=_parse_dt(offer.get("startDate")) or None,
                tags=tags,
                ist_gratis=free and not is_upcoming,
                kategorie="gaming",
                roh={"startDate": offer.get("startDate"),
                     "endDate": offer.get("endDate"),
                     "upcoming": is_upcoming},
            ))
        return out

    @staticmethod
    def _pick_offer(groups: list, now: datetime, future: bool = False) -> dict | None:
        for group in groups or []:
            for offer in group.get("promotionalOffers") or []:
                start = _parse_dt(offer.get("startDate"))
                end = _parse_dt(offer.get("endDate"))
                if future:
                    if start and start > now:
                        return offer
                elif (not start or start <= now) and (not end or end > now):
                    return offer
        return None

    @staticmethod
    def _store_url(el: dict) -> str:
        slug = el.get("productSlug") or el.get("urlSlug")
        for mapping in el.get("catalogNs", {}).get("mappings") or []:
            if mapping.get("pageSlug"):
                slug = mapping["pageSlug"]
                break
        if not slug:
            for attr in el.get("customAttributes") or []:
                if attr.get("key") == "com.epicgames.app.productSlug":
                    slug = attr.get("value")
        slug = (slug or "").split("/")[0]
        return _STORE_BASE + slug if slug else "https://store.epicgames.com/de/free-games"

    @staticmethod
    def _image(el: dict) -> str | None:
        prefer = ("OfferImageWide", "OfferImageTall", "Thumbnail", "DieselStoreFrontWide")
        images = {i.get("type"): i.get("url") for i in (el.get("keyImages") or [])}
        for key in prefer:
            if images.get(key):
                return images[key]
        return next((v for v in images.values() if v), None)


register(EpicFreeGames())
