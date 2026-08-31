"""Parser jeder Quelle gegen gespeicherte Fixtures - ohne Netzwerk."""
import pytest

from app.sources.cheapshark import CheapShark
from app.sources.epic import EpicFreeGames
from app.sources.itad import IsThereAnyDeal
from app.sources.pepper import MyDealz
from app.sources.reddit import Reddit
from app.sources.steam import Steam
from app.sources.wordpress import Sparhamster


def test_mydealz_parst_preise_und_temperatur(load_text):
    items = MyDealz().parse(load_text("pepper_mydealz.xml"))
    assert len(items) == 4

    xm5 = next(i for i in items if "WH-1000XM5" in i.titel)
    assert xm5.preis == 249.0
    assert xm5.originalpreis == 379.0
    assert round(xm5.rabatt_prozent) == 34
    assert xm5.temperatur == 349
    assert xm5.haendler == "Amazon"
    assert xm5.bild and xm5.bild.endswith("xm5.jpg")
    assert xm5.veroeffentlicht_am is not None
    assert not xm5.ist_gratis

    lego = next(i for i in items if "LEGO" in i.titel)
    assert lego.preis == 12.99 and lego.originalpreis == 349.99
    assert lego.temperatur == 982

    gratis = next(i for i in items if "Nivea" in i.titel)
    assert gratis.ist_gratis and gratis.preis == 0.0


def test_mydealz_temperaturfilter(load_text):
    items = MyDealz().parse(load_text("pepper_mydealz.xml"), min_temp=300)
    assert {round(i.temperatur) for i in items} == {349, 982}


def test_reddit_erkennt_store_und_gratis(load_text):
    items = Reddit().parse(load_text("reddit_gamedeals.xml"), sub="GameDeals")
    assert len(items) == 3

    portal = next(i for i in items if "Portal 2" in i.titel)
    assert portal.ist_gratis and portal.haendler == "Steam"
    assert portal.tags == ["r/GameDeals"]

    witcher = next(i for i in items if "Witcher" in i.titel)
    assert witcher.haendler == "GOG"
    assert witcher.rabatt_prozent == 85.0


def test_epic_laufende_und_kommende(load_json):
    items = EpicFreeGames().parse(load_json("epic_free.json"))
    titel = {i.titel for i in items}
    assert titel == {"Control", "Alan Wake 2"}   # "Nicht im Angebot" faellt raus

    control = next(i for i in items if i.titel == "Control")
    assert control.ist_gratis and control.preis == 0.0
    assert control.originalpreis == 29.99
    assert control.url == "https://store.epicgames.com/de/p/control"
    assert control.bild.endswith("control-wide.jpg")

    upcoming = next(i for i in items if i.titel == "Alan Wake 2")
    assert "demnaechst" in upcoming.tags
    assert not upcoming.ist_gratis        # noch nicht gratis


def test_epic_ohne_kommende(load_json):
    items = EpicFreeGames().parse(load_json("epic_free.json"), include_upcoming=False)
    assert [i.titel for i in items] == ["Control"]


def test_steam_dedupliziert_und_filtert(load_json):
    items = Steam().parse_featured(load_json("steam_featured.json"), min_discount=50)
    # Witcher steht in zwei Buckets, darf aber nur einmal kommen;
    # "Nur 20 Prozent" faellt unter die Schwelle.
    assert [i.titel for i in items] == ["Dota 2 Bundle", "The Witcher 3: Wild Hunt"]

    dota = items[0]
    assert dota.ist_gratis and dota.preis == 0.0 and dota.rabatt_prozent == 100

    witcher = items[1]
    assert witcher.preis == 7.99 and witcher.originalpreis == 39.99
    assert witcher.url == "https://store.steampowered.com/app/292030/"


def test_cheapshark(load_json):
    items = CheapShark().parse(load_json("cheapshark_deals.json"), stores={"1": "Steam"},
                               min_discount=80)
    assert [i.titel for i in items] == ["Portal 2", "Hades"]
    portal = items[0]
    assert portal.ist_gratis and portal.waehrung == "USD"
    assert portal.haendler == "Steam"
    assert portal.url == "https://www.cheapshark.com/redirect?dealID=abc123XYZ"


def test_itad(load_json):
    items = IsThereAnyDeal().parse(load_json("itad_deals.json"), min_discount=80)
    assert [i.titel for i in items] == ["Portal 2", "Hades"]
    assert items[0].ist_gratis
    assert items[1].preis == 4.99 and items[1].haendler == "GOG"


def test_sparhamster(load_text):
    items = Sparhamster().parse(load_text("sparhamster.xml"))
    assert len(items) == 2
    air = items[0]
    assert air.preis == 99.99 and air.originalpreis == 179.99
    assert items[1].ist_gratis


@pytest.mark.parametrize("bad", [
    "<html><body>Just a moment... Cloudflare</body></html>",
    "", "nicht mal ansatzweise xml",
])
def test_html_statt_feed_wirft(bad):
    """Eine Blockseite darf nicht als leerer Feed durchgehen."""
    with pytest.raises(ValueError):
        MyDealz().parse(bad)
