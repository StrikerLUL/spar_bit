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
from .. import kategorien
from ..http import RateLimited
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
    beschreibung = ("Erotik-Gruppe. Liegt der Feed woanders, sucht SparBit "
                    "ihn selbst und traegt ihn hier ein.")
    options_schema = [
        OptionSpec("feeds", "Feed- oder Seiten-Pfade", "list",
                   ["/rss/gruppe/erotik"],
                   help="Vorbelegt ist der uebliche Pepper-Pfad fuer einen "
                        "Gruppen-Feed. Liegt er anders, kommt hier HTML statt "
                        "Feed an - dann probiert SparBit die bekannten "
                        "Varianten durch und traegt die ein, die wirklich "
                        "liefert."),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", [],
                   help="Oft ergiebiger als die Gruppe: satisfyer, gleitgel, "
                        "womanizer, dessous, kondome"),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/rss/search?q={term}"),
        OptionSpec("min_temperatur", "Nur ab Temperatur", "int", 0,
                   help="0 = alles uebernehmen."),
    ]

    def parse(self, text: str, min_temp: float = 0.0) -> list[DealItem]:
        return _markiere(super().parse(text, min_temp))


def _pepper_optionen(pfad: str, begriffe: list[str]) -> list[OptionSpec]:
    """Gleiche Felder fuer alle Pepper-Ableger - nur andere Vorbelegung."""
    return [
        OptionSpec("feeds", "Feed- oder Seiten-Pfade", "list", [pfad],
                   help="Der uebliche Pfad fuer einen Gruppen-Feed. Ob die "
                        "Gruppe wirklich so heisst, sagt dir 'Jetzt testen' - "
                        "kommt HTML statt Feed, probiert SparBit die "
                        "bekannten Varianten durch und traegt die "
                        "funktionierende hier ein."),
        OptionSpec("search_terms", "Suchbegriff-Feeds", "list", begriffe,
                   help="Greift auch dann, wenn es die Gruppe gar nicht gibt."),
        OptionSpec("search_path", "Such-Pfad-Vorlage", "string",
                   "/rss/search?q={term}",
                   help="Welcher Weg gilt, ist von Seite zu Seite "
                        "verschieden. Findet SparBit einen Such-Feed unter "
                        "einer anderen Adresse, steht die danach hier."),
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
        "/rss/gruppe/erotik", ["satisfyer", "gleitgel", "dessous"])

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
        "/rss/groupe/erotique", ["sextoy", "preservatif", "lingerie"])

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
        "/rss/tag/adult", ["sex toy", "lovehoney", "durex"])

    def parse(self, text: str, min_temp: float = 0.0) -> list[DealItem]:
        return _markiere(super().parse(text, min_temp))


class RedditErwachsen(Reddit):
    """Subreddits, die 18+-Angebote sammeln.

    Die vorbelegten Namen sind **Vorschlaege, keine geprueften Adressen** -
    ich konnte kein einziges davon aufrufen. Einer davon, r/SexToyDeals,
    ist inzwischen aus dem Betrieb widerlegt:

        r/SexToyDeals: HTTPStatusError: Client error '404 Not Found'

    Er steht darum nicht mehr in der Vorbelegung. Wichtiger als die Liste
    ist aber, was die Quelle mit so einer Antwort macht: einen Namen, den
    Reddit mit 404 beantwortet, streicht sie selbst heraus und legt ihn
    unter "Automatisch entfernt" ab (siehe `sources/reddit.py`). Ein 429
    dagegen ist kein kaputter Name, sondern eine Drosselung - danach macht
    der naechste Lauf dort weiter, wo dieser aufgehoert hat.

    Zwei Namen bleiben trotzdem nur Vorschlaege. Wenn hier nichts kommt,
    ist die ergiebigere Quelle dieses Bereichs ohnehin "Eigene 18+-Quellen".
    """

    id = "reddit_erwachsen"
    display_name = "Reddit - 18+ (ungeprueft)"
    category = Category.ERWACHSEN
    default_interval = 900
    verification = Verification.UNVERIFIED
    beschreibung = ("Oeffentliche .rss-Feeds. Die vorbelegten Subreddits sind "
                    "ungeprueft - was es nicht gibt, streicht SparBit selbst.")

    options_schema = [
        OptionSpec("subreddits", "Subreddits", "list",
                   ["NSFWdeals", "AdultDeals"],
                   help="Ohne 'r/'. Ungeprueft vorbelegt - was Reddit mit "
                        "404 beantwortet, verschwindet von selbst aus dieser "
                        "Liste. Einer pro Zeile."),
        OptionSpec("listing", "Sortierung", "select", "new",
                   choices=["new", "hot", "top"]),
        OptionSpec("base", "Basis-Host", "string", "https://www.reddit.com",
                   help="Alternative: https://old.reddit.com"),
        OptionSpec("max_pro_lauf", "Subreddits pro Lauf", "int", 0,
                   help="0 = alle. Reddit drosselt Server in Rechenzentren "
                        "gern mit 429; dann hilft ein kleiner Wert, weil die "
                        "Liste ueber mehrere Laeufe abgearbeitet wird."),
        OptionSpec("entfernt", "Automatisch entfernt (404)", "list", [],
                   help="Namen, die es laut Reddit nicht gibt. Nur zur "
                        "Ansicht."),
    ]

    def parse(self, text: str, sub: str = "") -> list[DealItem]:
        return _markiere(super().parse(text, sub))


class ErotikFeed(Source):
    """Eigene 18+-Feeds - die eigentliche Arbeitsquelle dieses Bereichs.

    Viele Shops liefern einen Feed, ohne damit zu werben. Shopify haengt an
    jede Kollektion ein `.atom` (…/collections/sale.atom), WooCommerce und
    WordPress kennen `/feed`. Genau dafuer ist diese Quelle da: du traegst
    ein, was du selbst im Browser geoeffnet hast.

    Seit dem Umbau des Feed-Finders genuegt dafuer die Adresse der
    Angebotsseite. Zeichnet die Seite ihren Feed aus, wird er uebernommen;
    tut sie es nicht, klappert SparBit genau die Stellen ab, an denen die
    ueblichen Shop-Systeme ihn ablegen. Geraten wird trotzdem nichts:
    eingetragen wird nur eine Adresse, die tatsaechlich einen Feed
    zurueckgegeben hat.
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
                        "Angebotsseite genuegt. SparBit liest die "
                        "Feed-Auszeichnung der Seite und probiert sonst die "
                        "ueblichen Pfade (…/feed, …/rss, bei Shopify "
                        "…/collections/xyz.atom). Was liefert, steht danach "
                        "hier. Mit 'Feed suchen' vorher nachsehen."),
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
        gedrosselt: RateLimited | None = None
        drosselungen = 0
        for nummer, url in enumerate(feeds):
            try:
                fund = await feedfinder.hole(ctx.http, url,
                                             cache_key=f"erotik:{url}")
                text = fund.text
                if fund.entdeckt:
                    korrigiert[nummer] = fund.url
                geparst = self.parse(text, label or urlsplit(url).hostname or "")
                items.extend(geparst[:cap])
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
                preis_zeitraum=price.zeitraum,
                preis_monat=price.preis_pro_monat,
                preis_hinweis=price.preis_hinweis,
                kategorie=KATEGORIE,
            ))
        return out


class ErotikAbo(ErotikFeed):
    """Abos und Zugaenge fuer Seiten - das, was kein Paket verschickt.

    Der Unterschied zu `erotik_feed` ist nicht die Technik, sondern der
    Filter: hier bleibt nur, was ein laufendes Angebot ist. Erkannt wird
    das an zwei Dingen, die beide aus dem Text kommen und keine Raterei
    sind:

    * am Preis - "9,99 EUR/Monat" oder "3 Monate fuer 1 EUR" traegt seinen
      Zeitraum mit sich (siehe `app/priceparse.py`), und
    * an den Kategorien - "Mitgliedschaft", "Premium-Zugang", "Flatrate"
      (siehe `app/kategorien.py`).

    Und weil "guenstig" bei einem Abo nicht am Preisschild abzulesen ist -
    1 EUR fuer drei Monate ist billiger als 0,99 EUR im Monat -, filtert
    die Quelle auf den **Monatspreis**. Das ist die einzige Zahl, mit der
    sich zwei Abos vergleichen lassen.

    Verifizierungsstand wie ueberall hier: UNVERIFIED. Vorbelegt ist nichts,
    weil es fuer diesen Bereich keine Feed-Adresse gibt, die ich haette
    pruefen koennen - die Anbieter, die einen Feed haben, kennst du besser
    als ich. Was du eintraegst, darf die Angebotsseite sein; den Feed sucht
    SparBit selbst (siehe `app/feedfinder.py`).
    """

    id = "erotik_abo"
    display_name = "18+-Abos (Seiten-Zugänge)"
    category = Category.ERWACHSEN
    default_interval = 3600
    min_interval = 900
    verification = Verification.UNVERIFIED
    beschreibung = ("Laufende Zugänge statt Ware: Mitgliedschaften, "
                    "Premium-Zugänge, Flatrates. Gefiltert auf den Preis "
                    "pro Monat.")

    options_schema = [
        OptionSpec("feeds", "Shop- oder Feed-Adressen", "list", [],
                   help="Eine vollständige Adresse pro Zeile - die "
                        "Angebotsseite genügt. Gut geeignet sind die "
                        "Angebots- oder Blog-Seiten der Anbieter und "
                        "Deal-Seiten, die Zugänge listen."),
        OptionSpec("max_preis_monat", "Höchstpreis pro Monat (€)", "float", 0.0,
                   help="0 = kein Limit. Gerechnet wird der Monatspreis: "
                        "'3 Monate für 9 €' sind 3 € im Monat."),
        OptionSpec("nur_abos", "Nur laufende Angebote", "bool", True,
                   help="Aus: auch einmalige Käufe aus denselben Feeds "
                        "übernehmen."),
        OptionSpec("label", "Händler-Label", "string", "",
                   help="Leer = Hostname der jeweiligen URL."),
        OptionSpec("max_items", "Max. Einträge pro Feed", "int", 50),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        # Eine eigene Fehlermeldung, bevor die geerbte greift: diese Quelle
        # kann nichts vorbelegen (es gibt keine Adresse, die ich haette
        # pruefen koennen), also muss wenigstens dastehen, wie man zu einer
        # kommt. "Keine Adressen eingetragen" allein hilft niemandem.
        if not [f for f in (ctx.opt("feeds") or []) if str(f).strip()]:
            raise ValueError(
                "Noch keine Adresse eingetragen - und vorbelegen kann ich "
                "hier nichts, weil ich keine einzige davon pruefen konnte. "
                "So kommst du zu einer: (1) die Angebots-, Deal- oder "
                "Blog-Seite eines Anbieters im Browser oeffnen, (2) die "
                "Adresse hier eintragen - die Seite genuegt, den Feed sucht "
                "SparBit selbst, (3) 'Jetzt testen' druecken. Kommt nichts, "
                "hat die Seite keinen Feed; dann ist der naechste Anbieter "
                "dran. Mit 'Feed suchen' laesst sich das vorher pruefen."
            )
        # Gefiltert wird hier und nicht in parse(): die Quellen sind
        # Einzelstuecke, die sich mehrere Laeufe teilen - Optionen an der
        # Instanz zwischenzulegen waere eine Wette darauf, dass nie zwei
        # gleichzeitig laufen.
        items = await super().fetch(ctx)
        nur_abos = bool(ctx.opt("nur_abos", True))
        grenze = float(ctx.opt("max_preis_monat", 0) or 0)

        raus: list[DealItem] = []
        for item in items:
            if nur_abos and not _ist_abo(item):
                continue
            if grenze > 0 and (item.preis_monat is None
                               or item.preis_monat > grenze):
                continue
            raus.append(item)
        return raus


def _ist_abo(item: DealItem) -> bool:
    """Laeuft dieses Angebot weiter - oder ist es ein einmaliger Kauf?

    Zwei unabhaengige Belege, und einer genuegt: eine Preisangabe mit
    Zeitraum ("9,99 EUR/Monat", "3 Monate fuer 1 EUR") oder ein Text, der
    von Mitgliedschaft, Zugang oder Flatrate spricht.
    """
    if item.preis_zeitraum or item.preis_monat is not None:
        return True
    befund = kategorien.bestimme(item.titel, item.beschreibung,
                                 item.tags, erwachsen=True)
    return bool({"abo", "seiten18"} & set(befund.keys))


register(MyDealzErotik())
register(PreisjaegerErotik())
register(DealabsErotik())
register(HotUKDealsErwachsen())
register(RedditErwachsen())
register(ErotikFeed())
register(ErotikAbo())
