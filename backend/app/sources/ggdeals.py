"""GG.deals API (API-Key; fuer private Nutzung kostenlos).

Verifizierungsstand: UNVERIFIED - und hier besonders wichtig: der Zugang wird
bei GG.deals einzeln freigeschaltet (Formular), und die genaue Response-Form
haengt vom freigeschalteten Plan ab. Endpoint und Feldnamen sind darum
konfigurierbar. Bitte unbedingt erst 'Jetzt testen' druecken.
Key/Zugang: https://gg.deals/de/api/
"""
from __future__ import annotations

from .base import Category, DealItem, FetchContext, OptionSpec, Source, Verification, register


class GGDeals(Source):
    id = "ggdeals"
    display_name = "GG.deals"
    category = Category.GAMING
    default_interval = 3600
    min_interval = 1800
    requires_api_key = True
    api_key_url = "https://gg.deals/de/api/"
    verification = Verification.UNVERIFIED
    docs_url = "https://gg.deals/de/api/"
    beschreibung = ("Preisvergleich inkl. Key-Shops. Zugang muss bei GG.deals "
                    "beantragt werden.")

    options_schema = [
        OptionSpec("endpoint", "Deals-Endpoint", "string",
                   "https://api.gg.deals/v1/deals/list/",
                   help="Exakten Pfad aus deiner GG.deals-Freischaltung eintragen."),
        OptionSpec("region", "Region", "string", "de"),
        OptionSpec("limit", "Treffer pro Lauf", "int", 50),
        OptionSpec("min_discount", "Min. Rabatt %", "int", 80),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        if not ctx.api_key:
            raise ValueError(
                "Kein API-Key hinterlegt. Zugang unter https://gg.deals/de/api/ "
                "beantragen."
            )
        url = (f"{ctx.opt('endpoint')}?key={ctx.api_key}"
               f"&region={ctx.opt('region', 'de')}"
               f"&limit={int(ctx.opt('limit', 50))}")
        data = await ctx.http.get_json(url, cache_key="ggdeals:list")
        return self.parse(data, float(ctx.opt("min_discount", 80) or 0))

    def parse(self, data, min_discount: float = 0.0) -> list[DealItem]:
        if isinstance(data, dict):
            if data.get("success") is False:
                raise ValueError(f"GG.deals meldet Fehler: {data.get('message') or data}")
            rows = data.get("data") or data.get("deals") or data.get("list") or []
        else:
            rows = data or []
        if isinstance(rows, dict):
            rows = rows.get("deals") or list(rows.values())

        out: list[DealItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = (row.get("title") or row.get("name") or "").strip()
            url = row.get("url") or row.get("dealUrl") or row.get("link")
            if not title or not url:
                continue

            preis = self._f(row.get("price") or row.get("currentRetail")
                            or row.get("salePrice"))
            orig = self._f(row.get("regularPrice") or row.get("retail")
                           or row.get("originalPrice"))
            disc = self._f(row.get("discount") or row.get("cut"))
            if disc is None and preis is not None and orig:
                disc = round((1 - preis / orig) * 100, 1)
            if disc is not None and disc < min_discount:
                continue

            shop = row.get("shop") or row.get("store") or row.get("shopName")
            if isinstance(shop, dict):
                shop = shop.get("name")

            out.append(DealItem(
                titel=title,
                url=url,
                quelle=self.id,
                preis=preis,
                originalpreis=orig,
                rabatt_prozent=disc,
                waehrung=row.get("currency") or "EUR",
                haendler=shop,
                bild=row.get("image") or row.get("boxart"),
                tags=["ggdeals", "pc"],
                ist_gratis=preis == 0.0 or (disc is not None and disc >= 100),
                kategorie="gaming",
            ))
        return out

    @staticmethod
    def _f(val):
        if val is None:
            return None
        try:
            return float(str(val).replace(",", ".").replace("€", "").replace("$", "").strip())
        except ValueError:
            return None


register(GGDeals())
