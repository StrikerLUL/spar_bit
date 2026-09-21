"""Preis aus Produktseiten lesen - gegen echte Markup-Formen, ohne Netzwerk."""
import pytest

from app.models import WatchItem
from app.pricewatch import (
    Fund,
    NichtGefunden,
    preis_aus_seite,
    soll_melden,
)

# --- Beispielseiten in den Formen, die Shops wirklich ausliefern -----------

JSONLD_EINFACH = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Sony WH-1000XM5",
 "image":"https://shop.de/xm5.jpg",
 "offers":{"@type":"Offer","price":"249.00","priceCurrency":"EUR",
           "availability":"https://schema.org/InStock"}}
</script></head><body>egal</body></html>
"""

JSONLD_GRAPH = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"Organization","name":"Shop"},
  {"@type":"Product","name":"LEGO Technic",
   "offers":{"@type":"AggregateOffer","lowPrice":"129,99","priceCurrency":"EUR"}}]}
</script></head><body></body></html>
"""

JSONLD_LISTE = """
<script type="application/ld+json">
[{"@type":"BreadcrumbList"},
 {"@type":"Product","name":"Monitor","offers":[
   {"@type":"Offer","price":199.5,"priceCurrency":"EUR"}]}]
</script>
"""

OPENGRAPH = """
<html><head>
<meta property="og:title" content="Samsung SSD 2TB" />
<meta property="og:image" content="https://shop.de/ssd.png" />
<meta property="product:price:amount" content="129.00" />
<meta property="product:price:currency" content="EUR" />
</head></html>
"""

OG_UMGEKEHRT = """
<meta content="89.99" property="product:price:amount">
<meta content="EUR" property="product:price:currency">
"""

MICRODATA = """
<div itemscope itemtype="http://schema.org/Product">
  <meta itemprop="price" content="59.90">
  <meta itemprop="priceCurrency" content="EUR">
</div>
"""

OHNE_DATEN = "<html><body><span class='preis'>249,00 €</span></body></html>"


def test_jsonld_einfach():
    fund = preis_aus_seite(JSONLD_EINFACH)
    assert fund.preis == 249.0 and fund.waehrung == "EUR"
    assert fund.name == "Sony WH-1000XM5"
    assert fund.bild.endswith("xm5.jpg")
    assert fund.verfuegbar is True
    assert fund.quelle == "JSON-LD"


def test_jsonld_im_graph():
    """@graph ist bei grossen Shops die Regel, nicht die Ausnahme."""
    fund = preis_aus_seite(JSONLD_GRAPH)
    assert fund.preis == 129.99


def test_jsonld_als_liste():
    assert preis_aus_seite(JSONLD_LISTE).preis == 199.5


def test_opengraph():
    fund = preis_aus_seite(OPENGRAPH)
    assert fund.preis == 129.0 and fund.quelle == "Open Graph"
    assert fund.name == "Samsung SSD 2TB"


def test_opengraph_mit_vertauschten_attributen():
    """content vor property ist gueltiges HTML und kommt vor."""
    assert preis_aus_seite(OG_UMGEKEHRT).preis == 89.99


def test_microdata():
    fund = preis_aus_seite(MICRODATA)
    assert fund.preis == 59.90 and fund.quelle == "Microdata"


def test_jsonld_hat_vorrang_vor_opengraph():
    seite = JSONLD_EINFACH + OPENGRAPH
    assert preis_aus_seite(seite).quelle == "JSON-LD"


# --- Ehrliches Scheitern ---------------------------------------------------

def test_ohne_strukturierte_daten_wird_klar_gemeldet():
    """Lieber sagen 'kann ich nicht', als einen bruechigen Selektor zu raten -
    ein Waechter, der still den falschen Wert liest, ist schlimmer als keiner."""
    with pytest.raises(NichtGefunden) as info:
        preis_aus_seite(OHNE_DATEN)
    assert "JSON-LD" in str(info.value)


@pytest.mark.parametrize("seite", [
    "", "<html></html>",
    '<script type="application/ld+json">{kaputt</script>',
    '<script type="application/ld+json">{"@type":"Product"}</script>',
    '<meta property="product:price:amount" content="kein preis">',
    '<script type="application/ld+json">{"@type":"Product","offers":{"price":0}}</script>',
])
def test_unbrauchbare_seiten_werfen_sauber(seite):
    with pytest.raises(NichtGefunden):
        preis_aus_seite(seite)


@pytest.mark.parametrize("roh,erwartet", [
    ("1.299,00", 1299.0), ("1,299.00", 1299.0), ("249.00", 249.0),
    ("129,99", 129.99), ("59", 59.0), ("€ 19,90", 19.9),
])
def test_zahlformate(roh, erwartet):
    seite = f'<script type="application/ld+json">{{"@type":"Offer","price":"{roh}","priceCurrency":"EUR"}}</script>'
    assert preis_aus_seite(seite).preis == erwartet


# --- Wann wird gemeldet? ---------------------------------------------------

def eintrag(**kw):
    grund = dict(id=1, name="Test", url="https://shop.de/x", waehrung="EUR",
                 ziel_preis=None, bester_preis=None, zuletzt_gemeldet=None)
    return WatchItem(**{**grund, **kw})


def test_zielpreis_erreicht_wird_gemeldet():
    grund = soll_melden(eintrag(ziel_preis=200.0), Fund(189.0, "EUR"))
    assert grund and "Zielpreis" in grund


def test_ueber_dem_ziel_wird_nicht_gemeldet():
    assert soll_melden(eintrag(ziel_preis=200.0), Fund(219.0, "EUR")) is None


def test_gleiche_meldung_kommt_nicht_zweimal():
    """Sonst meldet sich SparBit bei jedem Lauf erneut, solange der Preis
    unten bleibt."""
    e = eintrag(ziel_preis=200.0, zuletzt_gemeldet=189.0)
    assert soll_melden(e, Fund(189.0, "EUR")) is None


def test_weiter_gefallen_wird_erneut_gemeldet():
    e = eintrag(ziel_preis=200.0, zuletzt_gemeldet=189.0)
    assert soll_melden(e, Fund(149.0, "EUR")) is not None


def test_ohne_ziel_zaehlt_ein_deutlicher_rutsch():
    e = eintrag(bester_preis=200.0)
    assert soll_melden(e, Fund(179.0, "EUR")) is not None      # -10 %
    assert soll_melden(e, Fund(198.0, "EUR")) is None          # -1 %, Rauschen


def test_fremdwaehrung_wird_umgerechnet():
    """200 USD sind unter einem 200-EUR-Ziel - ohne Umrechnung waere das
    ein verpasster Treffer."""
    e = eintrag(ziel_preis=200.0)
    assert soll_melden(e, Fund(200.0, "USD")) is not None
