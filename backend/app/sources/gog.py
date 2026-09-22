"""GOG - Katalog-Suche nach 0-EUR-Titeln + Giveaway-Erkennung.

Verifizierungsstand: UNVERIFIED. Der Giveaway-Endpoint ist erfahrungsgemaess
sprunghaft (existiert nur, wenn gerade ein Giveaway laeuft) - er wird darum
weich behandelt: faellt er aus, liefert die Quelle trotzdem den Katalog.
"""
from __future__ import annotations

from .base import Category, DealItem, FetchContext, OptionSpec, Source, Verification, register


class GOG(Source):
    id = "gog"
    display_name = "GOG.com"
    category = Category.GAMING
    default_interval = 3600
    min_interval = 900
    verification = Verification.UNVERIFIED
    docs_url = "https://www.gog.com/"
    beschreibung = "Gratis-Titel im Katalog (0 EUR) und laufende Giveaways."

    options_schema = [
        OptionSpec("catalog_endpoint", "Katalog-Endpoint", "string",
                   "https://catalog.gog.com/v1/catalog"),
        OptionSpec("giveaway_endpoint", "Giveaway-Endpoint", "string",
                   "https://www.gog.com/giveaway/api/status",
                   help="Leer lassen, um die Giveaway-Pruefung abzuschalten."),
        OptionSpec("country", "Land", "string", "DE"),
        OptionSpec("locale", "Locale", "string", "de-DE"),
        OptionSpec("currency", "Waehrung", "string", "EUR"),
        OptionSpec("limit", "Max. Katalog-Treffer", "int", 48),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        items: list[DealItem] = []
        errors: list[str] = []

        try:
            url = (
                f"{ctx.opt('catalog_endpoint')}"
                f"?limit={int(ctx.opt('limit', 48))}"
                f"&price=between:0,0"
                f"&order=desc:trending"
                f"&productType=in:game,pack,dlc,extras"
                f"&page=1"
                f"&countryCode={ctx.opt('country', 'DE')}"
                f"&locale={ctx.opt('locale', 'de-DE')}"
                f"&currencyCode={ctx.opt('currency', 'EUR')}"
            )
            items.extend(self.parse_catalog(await ctx.http.get_json(url, cache_key="gog:catalog")))
        except Exception as exc:
            errors.append(f"Katalog: {type(exc).__name__}: {exc}"[:200])

        giveaway_url = ctx.opt("giveaway_endpoint")
        if giveaway_url:
            try:
                items.extend(self.parse_giveaway(
                    await ctx.http.get_json(giveaway_url, cache_key="gog:giveaway")))
            except Exception as exc:
                # Kein laufendes Giveaway -> 404 ist der Normalfall, kein Fehler.
                if ctx.log:
                    ctx.log.debug("gog giveaway: %s", exc)

        if not items and errors:
            raise RuntimeError(" | ".join(errors))
        return items

    def parse_catalog(self, data: dict) -> list[DealItem]:
        out: list[DealItem] = []
        for prod in data.get("products") or []:
            title = (prod.get("title") or "").strip()
            url = prod.get("storeLink") or prod.get("url")
            if not title or not url:
                continue
            if url.startswith("/"):
                url = "https://www.gog.com" + url

            price = prod.get("price") or {}
            final = self._money(price.get("final") or price.get("finalMoney", {}).get("amount"))
            base = self._money(price.get("base") or price.get("baseMoney", {}).get("amount"))

            out.append(DealItem(
                titel=title,
                url=url,
                quelle=self.id,
                preis=final if final is not None else 0.0,
                originalpreis=base,
                waehrung="EUR",
                haendler="GOG.com",
                bild=self._image(prod),
                tags=["gog", "gratis"] + [g for g in (prod.get("genres") or [])[:4]
                                          if isinstance(g, str)],
                ist_gratis=True,
                kategorie="gaming",
                roh={"productType": prod.get("productType")},
            ))
        return out

    def parse_giveaway(self, data: dict) -> list[DealItem]:
        if not isinstance(data, dict):
            return []
        # Struktur variiert; wir nehmen nur, was eindeutig ein laufendes
        # Giveaway beschreibt.
        giveaway = data.get("giveaway") or data
        title = giveaway.get("gameTitle") or giveaway.get("title")
        if not title or not giveaway.get("isActive", True):
            return []
        slug = giveaway.get("gameSlug") or giveaway.get("slug") or ""
        url = f"https://www.gog.com/game/{slug}" if slug else "https://www.gog.com/#giveaway"
        return [DealItem(
            titel=f"[GOG Giveaway] {title}",
            url=url,
            quelle=self.id,
            preis=0.0,
            waehrung="EUR",
            haendler="GOG.com",
            tags=["gog", "giveaway", "gratis"],
            ist_gratis=True,
            kategorie="gaming",
        )]

    @staticmethod
    def _money(val) -> float | None:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return round(float(val) / 100, 2) if float(val) > 1000 else float(val)
        try:
            return float(str(val).replace(",", ".").replace("€", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _image(prod: dict) -> str | None:
        for key in ("coverHorizontal", "coverVertical", "image", "boxArtImage"):
            val = prod.get(key)
            if isinstance(val, str) and val:
                return val if val.startswith("http") else f"https:{val}"
        return None


register(GOG())
