"""Deal-Communities ausserhalb des deutschsprachigen Raums.

Warum ueberhaupt: SparBit rechnet seit jeher in EUR um (CheapShark
liefert USD, HotUKDeals GBP), und die Preisfehler-Erkennung braucht
Gegenmeinungen aus mehreren Quellen. Beides wird besser, je mehr Maerkte
dieselbe Ware melden — gerade bei Elektronik, wo ein Preisfehler oft
zuerst in einem anderen Land auffaellt.

Beide Quellen liefern klassisches RSS. Sie sind darum kein eigener
Parser, sondern eine Konfiguration des vorhandenen: Adresse rein,
`feedfinder` sucht sie notfalls selbst, `priceparse` liest den Preis aus
dem Titel.

Verifizierungsstand: UNVERIFIED - in der Build-Umgebung nicht live
pruefbar. Beide Adressen stehen als Option offen und lassen sich mit
"Jetzt testen" bzw. `python -m tools.verify_endpoints` pruefen.

Die Waehrung wird **nicht geraten**: Slickdeals ist USD, OzBargain AUD.
Steht im Titel ein Waehrungszeichen, gewinnt das - sonst gilt die
Vorgabe der Quelle. Ohne diese Festlegung liefe ein "$ 199" als EUR
durch jede Preisregel, und "max. 200 EUR" wuerde bei 180 EUR-Aequivalent
mal treffen und mal nicht.
"""
from __future__ import annotations

from .. import feedfinder
from ..priceparse import parse_price_text
from .base import Category, DealItem, FetchContext, OptionSpec, Source, Verification, register
from .rssutil import entry_body, entry_datetime, entry_tags, first_image, parse_feed, strip_html


class InternationalerFeed(Source):
    """Gemeinsamer Rumpf: RSS lesen, Preis aus dem Titel, Waehrung festlegen."""

    category = Category.COMMUNITY
    default_interval = 1200
    min_interval = 600
    verification = Verification.UNVERIFIED
    feed_url: str = ""
    waehrung: str = "EUR"

    @property
    def options_schema(self):  # type: ignore[override]
        return [
            OptionSpec("feed_url", "Feed-URL", "string", self.feed_url,
                       help="Mit 'Jetzt testen' pruefen. Viele dieser Seiten "
                            "bieten auch Feeds je Kategorie an."),
            OptionSpec("waehrung", "Währung der Quelle", "string", self.waehrung,
                       help="Gilt, wenn im Titel kein Währungszeichen steht. "
                            "Der Kurs dazu steht unter „Logs & System“."),
            OptionSpec("max_items", "Max. Einträge pro Lauf", "int", 50),
        ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        url = ctx.opt("feed_url", self.feed_url)
        if not url:
            raise ValueError("Keine Feed-URL konfiguriert.")
        fund = await feedfinder.hole(ctx.http, url, cache_key=f"{self.id}:{url}")
        if fund.entdeckt:
            ctx.merke("feed_url", fund.url)
        waehrung = str(ctx.opt("waehrung", self.waehrung) or self.waehrung).upper()[:8]
        return self.parse(fund.text, waehrung)[: int(ctx.opt("max_items", 50))]

    def parse(self, text: str, waehrung: str | None = None) -> list[DealItem]:
        waehrung = (waehrung or self.waehrung).upper()
        feed = parse_feed(text)
        raus: list[DealItem] = []
        for eintrag in feed.entries:
            titel = strip_html(eintrag.get("title"), 400)
            link = eintrag.get("link")
            if not titel or not link:
                continue
            body_html = entry_body(eintrag)
            body = strip_html(body_html)
            preis = parse_price_text(f"{titel} {body}")
            raus.append(DealItem(
                titel=titel,
                url=link,
                quelle=self.id,
                beschreibung=body or None,
                preis=preis.preis,
                originalpreis=preis.originalpreis,
                rabatt_prozent=preis.rabatt_prozent,
                # Der Parser erkennt die Waehrung nur, wenn ein Zeichen
                # dabeisteht. Sonst die der Quelle - nicht EUR.
                waehrung=preis.waehrung or waehrung,
                bild=first_image(eintrag, body_html),
                veroeffentlicht_am=entry_datetime(eintrag),
                tags=entry_tags(eintrag),
                ist_gratis=preis.ist_gratis,
                kategorie="community",
            ))
        return raus


class Slickdeals(InternationalerFeed):
    id = "slickdeals"
    display_name = "Slickdeals (US)"
    feed_url = "https://feeds.slickdeals.net/slickdeals/frontpage"
    waehrung = "USD"
    beschreibung = ("Die groesste US-Deal-Community. Der Frontpage-Feed zeigt, "
                    "was dort durch die Abstimmung gekommen ist. Preise in USD — "
                    "SparBit rechnet sie fuer Regeln in EUR um.")


class OzBargain(InternationalerFeed):
    id = "ozbargain"
    display_name = "OzBargain (AU)"
    feed_url = "https://www.ozbargain.com.au/deals/feed"
    waehrung = "AUD"
    beschreibung = ("Australische Deal-Community. Wegen der Zeitzone oft die "
                    "erste Quelle, die einen weltweiten Preisfehler meldet.")


register(Slickdeals())
register(OzBargain())
