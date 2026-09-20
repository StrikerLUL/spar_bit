"""18+-Quellen.

Diese Quellen erscheinen erst, wenn der Bereich unter *Logs & System*
freigeschaltet ist - vorher listet die API sie nicht und der Scheduler
startet sie nicht. Ihre Funde tragen die 18+-Marke und sind ausschliesslich
auf der eigenen Seite zu sehen.

Verifizierungsstand: UNVERIFIED, wie bei allen anderen Quellen auch. Die
Build-Umgebung kommt an keinen einzigen Deal-Host heran (44 von 44
Endpoints am Proxy gescheitert, siehe ENDPOINTS.md), und daran hat sich
nichts geaendert. Erst recht gilt hier darum: **alle Pfade sind editierbar,
und "Jetzt testen" hat das letzte Wort.**

Warum es nur drei Quellen sind und nicht zwoelf: das Aufnahmekriterium ist
unveraendert - es muss einen Feed oder eine dokumentierte API geben.
Erotik-Shops sind fast durchweg reine HTML-Seiten mit aktivem Bot-Schutz;
ein Scraper dafuer waere genau das, was du nicht wolltest. Die dritte Quelle
hier ist deshalb die wichtigste: eine generische Feed-Quelle, in die du
jeden Shop-Feed eintraegst, den du selbst geprueft hast. Welche Feed-Adressen
sich bei welcher Shop-Software lohnen, steht in ENDPOINTS.md.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .. import feedfinder
from ..priceparse import parse_price_text
from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)
from .pepper import PepperSource
from .reddit import Reddit
from .rssutil import (entry_body, entry_datetime, entry_tags, first_image,
                      parse_feed, strip_html)

KATEGORIE = "erwachsen"


def _markiere(items: list[DealItem]) -> list[DealItem]:
    """Jeden Fund als 18+ kennzeichnen - unabhaengig von seinem Titel.

    Die Einstufung per Stichwort (app/erwachsen.py) greift zusaetzlich, aber
    verlassen darf man sich darauf nicht: "Gutschein 20 EUR" verraet nicht,
    aus welchem Regal es kommt. Die Quelle weiss es.
    """
    return [i.model_copy(update={"kategorie": KATEGORIE}) for i in items]


class MyDealzErotik(PepperSource):
    """Die Erotik-Gruppe von mydealz, getrennt von der normalen Quelle.

    Bewusst eine eigene Quelle und kein weiterer Pfad in der bestehenden:
    so laesst sie sich einzeln abschalten, und ihre Funde sind schon an der
    Quellen-ID als 18+ erkennbar.
    """

    id = "mydealz_erotik"
    display_name = "mydealz.de - Erotik (18+)"
    base_url = "https://www.mydealz.de"
    category = Category.ERWACHSEN
    verification = Verification.UNVERIFIED
    docs_url = "https://www.mydealz.de/gruppe/erotik"
    beschreibung = ("Erotik-Gruppe. Eingetragen ist die Seite, nicht der "
                    "Feed - den sucht SparBit selbst.")
    options_schema = [
        OptionSpec("feeds", "Feed- oder Seiten-Pfade", "list", ["/gruppe/erotik"],
                   help="Die Gruppen-Seite. Kommt HTML statt Feed, liest "
                        "SparBit die ausgezeichnete Feed-Adresse aus der "
                        "Seite und traegt sie hier ein."),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", [],
                   help="Oft ergiebiger als die Gruppe: satisfyer, gleitgel, "
                        "womanizer, dessous, kondome"),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/search?q={term}&rss=1"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0,
                   help="0 = alles uebernehmen."),
    ]

    def parse(self, text: str, min_temp: float = 0.0) -> list[DealItem]:
        return _markiere(super().parse(text, min_temp))


def _pepper_optionen(pfad: str, begriffe: list[str]) -> list[OptionSpec]:
    """Gleiche Felder fuer alle Pepper-Ableger - nur andere Vorbelegung."""
    return [
        OptionSpec("feeds", "Feed- oder Seiten-Pfade", "list", [pfad],
                   help="Die Gruppen-Seite. Findet SparBit dort einen "
                        "ausgezeichneten Feed, traegt es ihn hier ein. "
                        "Der Pfad ist geraten - 'Jetzt testen' sagt dir, "
                        "ob die Gruppe so heisst."),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", begriffe,
                   help="Greift auch dann, wenn es die Gruppe gar nicht gibt."),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/search?q={term}&rss=1"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0),
    ]


class PreisjaegerErotik(PepperSource):
    id = "preisjaeger_erotik"
    display_name = "Preisjaeger.at - Erotik (18+)"
    base_url = "https://www.preisjaeger.at"
    category = Category.ERWACHSEN
    verification = Verification.UNVERIFIED
    beschreibung = "Oesterreichischer Pepper-Ableger, gleiche Plattform wie mydealz."
    options_schema = _pepper_optionen(
        "/gruppe/erotik", ["satisfyer", "gleitgel", "dessous"])

    def parse(self, text: str, min_temp: float = 0.0) -> list[DealItem]:
        return _markiere(super().parse(text, min_temp))


class DealabsErotik(PepperSource):
    id = "dealabs_erotik"
    display_name = "Dealabs (FR) - Erotique (18+)"
    base_url = "https://www.dealabs.com"
    category = Category.ERWACHSEN
    verification = Verification.UNVERIFIED
    beschreibung = ("Franzoesischer Pepper-Ableger. Franzoesische Titel - die "
                    "Stichwort-Einstufung greift hier nicht, die Quelle "
                    "selbst schon.")
    options_schema = _pepper_optionen(
        "/groupe/erotique", ["sextoy", "preservatif", "lingerie"])

    def parse(self, text: str, min_temp: float = 0.0) -> list[DealItem]:
        return _markiere(super().parse(text, min_temp))


class HotUKDealsErwachsen(PepperSource):
    id = "hotukdeals_erwachsen"
    display_name = "HotUKDeals (UK) - Adult (18+)"
    base_url = "https://www.hotukdeals.com"
    category = Category.ERWACHSEN
    verification = Verification.UNVERIFIED
    default_currency = "GBP"
    beschreibung = "UK-Pepper-Ableger. Preise in GBP, werden in EUR umgerechnet."
    options_schema = _pepper_optionen(
        "/tag/adult", ["sex toy", "lovehoney", "durex"])

    def parse(self, text: str, min_temp: float = 0.0) -> list[DealItem]:
        return _markiere(super().parse(text, min_temp))


class RedditErwachsen(Reddit):
    """Subreddits, die 18+-Angebote sammeln.

    Die vorbelegten Namen sind **Vorschlaege, keine geprueften Adressen** -
    ich konnte kein einziges davon aufrufen. Reddit gibt fuer einen
    Subreddit, den es nicht gibt, eine leere bzw. 404-Antwort; die Quelle
    ueberspringt einzelne Ausfaelle und meldet erst, wenn alle scheitern.
    Was nicht liefert, gehoert aus der Liste gestrichen.
    """

    id = "reddit_erwachsen"
    display_name = "Reddit - 18+ (ungeprueft)"
    category = Category.ERWACHSEN
    default_interval = 900
    verification = Verification.UNVERIFIED
    beschreibung = ("Oeffentliche .rss-Feeds. Die vorbelegten Subreddits sind "
                    "ungeprueft - erst testen, dann behalten.")

    options_schema = [
        OptionSpec("subreddits", "Subreddits", "list",
                   ["SexToyDeals", "NSFWdeals", "AdultDeals"],
                   help="Ohne 'r/'. Ungeprueft vorbelegt: was 404 gibt, "
                        "hier loeschen. Einer pro Zeile."),
        OptionSpec("listing", "Sortierung", "select", "new",
                   choices=["new", "hot", "top"]),
        OptionSpec("base", "Basis-Host", "string", "https://www.reddit.com",
                   help="Alternative: https://old.reddit.com"),
    ]

    def parse(self, text: str, sub: str = "") -> list[DealItem]:
        return _markiere(super().parse(text, sub))


class ErotikFeed(Source):
    """Eigene 18+-Feeds - die eigentliche Arbeitsquelle dieses Bereichs.

    Viele Shops liefern einen Feed, ohne damit zu werben. Shopify haengt an
    jede Kollektion ein `.atom` (…/collections/sale.atom), WooCommerce und
    WordPress kennen `/feed`. Genau dafuer ist diese Quelle da: du traegst
    ein, was du selbst im Browser geoeffnet hast, und nichts wird geraten.
    """

    id = "erotik_feed"
    display_name = "Eigene 18+-Quellen (Seite oder Feed)"
    category = Category.ERWACHSEN
    default_interval = 1800
    min_interval = 600
    verification = Verification.UNVERIFIED
    beschreibung = ("Adresse eines Shops eintragen - den Feed sucht SparBit "
                    "selbst. Auch fertige Feed-Adressen sind willkommen.")

    options_schema = [
        OptionSpec("feeds", "Shop- oder Feed-Adressen", "list", [],
                   help="Eine vollstaendige Adresse pro Zeile - die "
                        "Angebotsseite genuegt. Zeichnet die Seite einen "
                        "Feed aus, traegt SparBit ihn hier ein. Mit "
                        "'Feed suchen' vorher nachsehen."),
        OptionSpec("label", "Haendler-Label", "string", "",
                   help="Leer = Hostname der jeweiligen URL."),
        OptionSpec("nur_reduziert", "Nur reduzierte Eintraege", "bool", False,
                   help="Verwirft Eintraege ohne Rabatt und ohne Gratis-Marke."),
        OptionSpec("max_items", "Max. Eintraege pro Feed", "int", 50),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        feeds = [f.strip() for f in (ctx.opt("feeds") or []) if str(f).strip()]
        if not feeds:
            raise ValueError(
                "Keine Adressen eingetragen. Diese Quelle raet nichts - trag "
                "die Angebotsseite eines Shops ein; den Feed sucht SparBit "
                "dann selbst (siehe ENDPOINTS.md)."
            )
        label = ctx.opt("label", "")
        cap = int(ctx.opt("max_items", 50))
        nur_reduziert = bool(ctx.opt("nur_reduziert", False))

        items: list[DealItem] = []
        errors: list[str] = []
        korrigiert: dict[int, str] = {}
        for nummer, url in enumerate(feeds):
            try:
                fund = await feedfinder.hole(ctx.http, url,
                                             cache_key=f"erotik:{url}")
                text = fund.text
                if fund.entdeckt:
                    korrigiert[nummer] = fund.url
                geparst = self.parse(text, label or urlsplit(url).hostname or "")
                items.extend(geparst[:cap])
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}"[:260])

        if korrigiert:
            neu = list(feeds)
            for nummer, url in korrigiert.items():
                neu[nummer] = url
            ctx.merke("feeds", neu)

        if not items and errors:
            raise RuntimeError(" | ".join(errors[:3]))
        if nur_reduziert:
            items = [i for i in items
                     if i.ist_gratis or (i.rabatt_prozent or 0) > 0]
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
                kategorie=KATEGORIE,
            ))
        return out


register(MyDealzErotik())
register(PreisjaegerErotik())
register(DealabsErotik())
register(HotUKDealsErwachsen())
register(RedditErwachsen())
register(ErotikFeed())
