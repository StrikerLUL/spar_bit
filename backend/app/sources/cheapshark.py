"""CheapShark - Deal-Aggregator ueber ~35 PC-Stores. Kein API-Key noetig.

Verifizierungsstand: UNVERIFIED. Preise sind USD (CheapShark rechnet nicht um).
"""
from __future__ import annotations

from .base import Category, DealItem, FetchContext, OptionSpec, Source, Verification, register

_REDIRECT = "https://www.cheapshark.com/redirect?dealID={id}"


class CheapShark(Source):
    id = "cheapshark"
    display_name = "CheapShark"
    category = Category.GAMING
    default_interval = 1800
    min_interval = 600
    verification = Verification.UNVERIFIED
    docs_url = "https://apidoc.cheapshark.com/"
    beschreibung = "Deals ueber ~35 Stores. Kein Key. Preise in USD."

    options_schema = [
        OptionSpec("endpoint", "Endpoint", "string",
                   "https://www.cheapshark.com/api/1.0/deals"),
        OptionSpec("stores_endpoint", "Stores-Endpoint", "string",
                   "https://www.cheapshark.com/api/1.0/stores"),
        OptionSpec("upper_price", "Max. Preis (USD)", "int", 5,
                   help="0 = nur komplett kostenlose Titel."),
        OptionSpec("min_discount", "Min. Rabatt %", "int", 80),
        OptionSpec("page_size", "Treffer pro Lauf", "int", 60),
        OptionSpec("only_steamworks", "Nur Steam-Keys", "bool", False),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        params = [
            f"upperPrice={int(ctx.opt('upper_price', 5))}",
            f"pageSize={min(int(ctx.opt('page_size', 60)), 60)}",
            "sortBy=Recent",
        ]
        if ctx.opt("only_steamworks"):
            params.append("steamworks=1")
        url = f"{ctx.opt('endpoint')}?{'&'.join(params)}"
        data = await ctx.http.get_json(url, cache_key="cheapshark:deals")

        stores = {}
        try:
            raw_stores = await ctx.http.get_json(ctx.opt("stores_endpoint"),
                                                 cache_key="cheapshark:stores")
            stores = {s["storeID"]: s["storeName"] for s in raw_stores
                      if s.get("storeID") and s.get("storeName")}
        except Exception as exc:
            if ctx.log:
                ctx.log.debug("cheapshark stores: %s", exc)

        return self.parse(data, stores, float(ctx.opt("min_discount", 80) or 0))

    def parse(self, data: list, stores: dict | None = None,
              min_discount: float = 0.0) -> list[DealItem]:
        stores = stores or {}
        out: list[DealItem] = []
        for d in data or []:
            title = (d.get("title") or "").strip()
            deal_id = d.get("dealID")
            if not title or not deal_id:
                continue

            savings = self._f(d.get("savings"))
            if savings is not None and savings < min_discount:
                continue

            sale = self._f(d.get("salePrice"))
            normal = self._f(d.get("normalPrice"))

            out.append(DealItem(
                titel=title,
                url=_REDIRECT.format(id=deal_id),
                quelle=self.id,
                preis=sale,
                originalpreis=normal,
                rabatt_prozent=round(savings, 1) if savings is not None else None,
                waehrung="USD",
                haendler=stores.get(d.get("storeID"), f"Store {d.get('storeID')}"),
                bild=d.get("thumb"),
                temperatur=self._f(d.get("dealRating")),
                tags=["cheapshark", "pc"],
                ist_gratis=sale == 0.0,
                kategorie="gaming",
                roh={"steamAppID": d.get("steamAppID"), "dealID": deal_id},
            ))
        return out

    @staticmethod
    def _f(val) -> float | None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None


register(CheapShark())
