"""JSON-Adapter und Steam-Import - die beiden Wege, die bisher fehlten."""
import pytest

from app.sources.base import FetchContext
from app.sources.customjson import CustomJson, pfad_lesen


class Http:
    """Ein HTTP-Client, der nur zurueckgibt, was man ihm vorlegt."""

    def __init__(self, antworten=None, texte=None):
        self.antworten = antworten or {}
        self.texte = texte or {}
        self.gefragt = []

    async def get_json(self, url, **kwargs):
        self.gefragt.append(url)
        if url not in self.antworten:
            raise AssertionError(f"unerwartete Adresse: {url}")
        return self.antworten[url]

    async def get_text(self, url, **kwargs):
        self.gefragt.append(url)
        return self.texte[url]


def ctx(http, **optionen):
    return FetchContext(http=http, options=optionen)


# --- Pfade ---------------------------------------------------------------

@pytest.mark.parametrize("pfad,erwartet", [
    ("", {"a": 1}),
    ("a", 1),
    ("b.c", 2),
    ("liste.0.x", 9),
    ("gibtsnicht", None),
    ("a.b", None),
])
def test_pfad_lesen(pfad, erwartet):
    daten = {"a": 1, "b": {"c": 2}, "liste": [{"x": 9}]}
    if pfad == "":
        assert pfad_lesen({"a": 1}, pfad) == erwartet
    else:
        assert pfad_lesen(daten, pfad) == erwartet


# --- JSON-Quelle ---------------------------------------------------------

@pytest.mark.asyncio
async def test_json_quelle_liest_verschachtelte_antwort():
    antwort = {"data": {"items": [
        {"title": "Spiel A", "url": "/spiel/a", "price": {"current": 499, "old": 1999}},
        {"title": "Spiel B", "url": "https://shop.de/b", "price": {"current": 0}},
    ]}}
    http = Http({"https://api.shop.de/deals": antwort})
    quelle = CustomJson()

    items = await quelle.fetch(ctx(
        http, url="https://api.shop.de/deals", liste="data.items",
        feld_titel="title", feld_url="url", feld_preis="price.current",
        feld_originalpreis="price.old", teiler=100, waehrung="EUR"))

    assert len(items) == 2
    assert items[0].titel == "Spiel A"
    assert items[0].preis == 4.99
    assert items[0].originalpreis == 19.99
    # Relative Adresse gegen den Endpunkt aufgeloest.
    assert items[0].url == "https://api.shop.de/spiel/a"
    # 0 heisst gratis - das erkennt DealItem selbst.
    assert items[1].ist_gratis is True


@pytest.mark.asyncio
async def test_falscher_pfad_sagt_was_stattdessen_da_ist():
    """Sonst sucht man den Fehler im Endpunkt statt in der Einstellung."""
    http = Http({"https://api.shop.de/deals": {"ergebnisse": []}})
    with pytest.raises(ValueError, match="steht nichts"):
        await CustomJson().fetch(ctx(http, url="https://api.shop.de/deals",
                                     liste="data.items"))


@pytest.mark.asyncio
async def test_eintraege_ohne_titel_oder_adresse_fallen_raus():
    http = Http({"https://x/d": [{"title": "ok", "url": "https://x/1"},
                                 {"title": "", "url": "https://x/2"},
                                 {"title": "kein Link"}]})
    items = await CustomJson().fetch(ctx(http, url="https://x/d"))
    assert [i.titel for i in items] == ["ok"]


@pytest.mark.asyncio
async def test_ohne_adresse_wird_klar_gemeckert():
    with pytest.raises(ValueError, match="Keine Adresse"):
        await CustomJson().fetch(ctx(Http(), url=""))


# --- Steam-Wunschliste ---------------------------------------------------

@pytest.mark.parametrize("eingabe,erwartet", [
    ("https://store.steampowered.com/wishlist/profiles/76561198000000000/",
     ("id", "76561198000000000")),
    ("https://steamcommunity.com/id/cillian/", ("name", "cillian")),
    ("76561198000000000", ("id", "76561198000000000")),
    ("cillian", ("name", "cillian")),
])
def test_steam_profil_erkennen(eingabe, erwartet):
    from app.steamwunsch import steam_id_aus
    assert steam_id_aus(eingabe) == erwartet


def test_unsinn_wird_erklaert():
    from app.steamwunsch import steam_id_aus
    with pytest.raises(ValueError, match="Steam-Profil"):
        steam_id_aus("https://example.com/kein profil !!")


@pytest.mark.asyncio
async def test_wunschliste_wird_gelesen():
    from app.steamwunsch import hole

    url = ("https://store.steampowered.com/wishlist/profiles/"
           "76561198000000000/wishlistdata/?p=0")
    http = Http({url: {
        "1091500": {"name": "Cyberpunk 2077", "capsule": "https://bild/1.jpg"},
        "570": {"name": "Dota 2", "capsule": None},
    }})
    eintraege = await hole(http, "76561198000000000")
    assert {e.titel for e in eintraege} == {"Cyberpunk 2077", "Dota 2"}
    assert eintraege[0].url == "https://store.steampowered.com/app/1091500/"


@pytest.mark.asyncio
async def test_private_wunschliste_sagt_warum():
    """Steam antwortet mit einem leeren Array statt mit einem Fehler -
    ohne diesen Zweig stuende da nur 'nichts gefunden'."""
    from app.steamwunsch import hole

    url = ("https://store.steampowered.com/wishlist/profiles/"
           "76561198000000000/wishlistdata/?p=0")
    http = Http({url: []})
    with pytest.raises(ValueError, match="privat"):
        await hole(http, "76561198000000000")


@pytest.mark.asyncio
async def test_profilname_wird_aufgeloest():
    from app.steamwunsch import hole

    xml = "<profile><steamID64>76561198000000000</steamID64></profile>"
    wunsch = ("https://store.steampowered.com/wishlist/profiles/"
              "76561198000000000/wishlistdata/?p=0")
    http = Http(antworten={wunsch: {"570": {"name": "Dota 2"}}},
                texte={"https://steamcommunity.com/id/cillian/?xml=1": xml})
    eintraege = await hole(http, "cillian")
    assert eintraege[0].appid == "570"
