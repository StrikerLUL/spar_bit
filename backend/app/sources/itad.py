"""IsThereAnyDeal API v2 (API-Key noetig).

Verifizierungsstand: UNVERIFIED. Doku: https://docs.isthereanydeal.com/
Key holen: https://isthereanydeal.com/apps/my/ (App registrieren -> Key).
"""
from __future__ import annotations

from datetime import datetime

from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)


def _dt(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


class IsThereAnyDeal(Source):
    id = "itad"
    display_name = "IsThereAnyDeal"
    category = Category.GAMING
    default_interval = 1800
    min_interval = 900
    requires_api_key = True
    api_key_url = "https://isthereanydeal.com/apps/my/"
    verification = Verification.UNVERIFIED
    docs_url = "https://docs.isthereanydeal.com/"
    beschreibung = "Preisvergleich ueber viele Stores; starke Historie/Tiefstpreise."

    options_schema = [
        OptionSpec("endpoint", "Deals-Endpoint", "string",
                   "https://api.isthereanydeal.com/deals/v2"),
        OptionSpec("country", "Land", "string", "DE"),
        OptionSpec("limit", "Treffer pro Lauf", "int", 50),
        OptionSpec("min_discount", "Min. Rabatt %", "int", 80),
        OptionSpec("nondeals", "Auch Nicht-Deals", "bool", False),
        OptionSpec("mature", "Mature-Inhalte", "bool", False),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        if not ctx.api_key:
            raise ValueError(
                "Kein API-Key hinterlegt. Key unter "
                "https://isthereanydeal.com/apps/my/ anlegen."
            )
        params = [
            f"key={ctx.api_key}",
            f"country={ctx.opt('country', 'DE')}",
            f"limit={int(ctx.opt('limit', 50))}",
            "offset=0",
            "sort=-cut",
            f"nondeals={'true' if ctx.opt('nondeals') else 'false'}",
            f"mature={'true' if ctx.opt('mature') else 'false'}",
        ]
        url = f"{ctx.opt('endpoint')}?{'&'.join(params)}"
        data = await ctx.http.get_json(url, cache_key="itad:deals")
        return self.parse(data, float(ctx.opt("min_discount", 80) or 0))

    def parse(self, data, min_discount: float = 0.0) -> list[DealItem]:
        # v2 liefert {"list": [...]}; aeltere/andere Aufrufe direkt eine Liste.
        rows = data.get("list") if isinstance(data, dict) else data
        out: list[DealItem] = []

        for row in rows or []:
            title = (row.get("title") or "").strip()
            deal = row.get("deal") or {}
            if not title or not deal:
                continue

            cut = deal.get("cut")
            cut = float(cut) if cut is not None else None
            if cut is not None and cut < min_discount:
                continue

            price = (deal.get("price") or {})
            regular = (deal.get("regular") or {})
            amount = price.get("amount")
            reg_amount = regular.get("amount")
            shop = (deal.get("shop") or {}).get("name")

            url = deal.get("url") or row.get("urls", {}).get("game")
            if not url:
                continue

            out.append(DealItem(
                titel=title,
                url=url,
                quelle=self.id,
                preis=float(amount) if amount is not None else None,
                originalpreis=float(reg_amount) if reg_amount is not None else None,
                rabatt_prozent=cut,
                waehrung=price.get("currency") or "EUR",
                haendler=shop,
                bild=(row.get("assets") or {}).get("boxart")
                     or (row.get("assets") or {}).get("banner400"),
                veroeffentlicht_am=_dt(deal.get("timestamp")),
                tags=["itad", "pc"] + ([shop] if shop else []),
                ist_gratis=(amount == 0) or (cut is not None and cut >= 100),
                kategorie="gaming",
                roh={"id": row.get("id"), "slug": row.get("slug")},
            ))
        return out


register(IsThereAnyDeal())
