"""Die Gegenprobe auf der Zielseite.

Geprueft wird hier das Auswerten einer Seite, nicht das Netz - die
Build-Umgebung kommt an keinen Shop heran. Die HTML-Schnipsel bilden die
Formen ab, in denen Shops ihre Preise auszeichnen: schema.org als JSON-LD,
Microdata, OpenGraph. Und die Faelle, in denen SparBit ausdruecklich NICHT
urteilen soll.
"""
import pytest

from app.gratischeck import (ABGELAUFEN, BESTAETIGT, UNERREICHBAR, UNKLAR,
                             WIDERLEGT, analysiere, ist_kandidat, pruefe,
                             pruefe_deals, uebernehme)
from app.models import Deal

JSONLD = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Kopfhörer",
 "offers":{"@type":"Offer","price":"%s","priceCurrency":"EUR",
 "availability":"https://schema.org/%s"}}</script></head><body>x</body></html>"""

OPENGRAPH = """<html><head>
<meta property="product:price:amount" content="19,99">
<meta property="product:price:currency" content="EUR">
</head><body>Produkt</body></html>"""

MICRODATA = """<html><body><div itemprop="offers">
<meta itemprop="price" content="0.00">
<link itemprop="availability" href="https://schema.org/InStock">
</div></body></html>"""


def test_seite_verlangt_geld_obwohl_gratis_gemeldet():
    b = analysiere(JSONLD % ("14.99", "InStock"), erwartet_gratis=True)
    assert b.status == WIDERLEGT and b.preis == 14.99
    assert b.herkunft == "json-ld" and b.widerspricht


def test_seite_bestaetigt_null():
    b = analysiere(JSONLD % ("0.00", "InStock"), erwartet_gratis=True)
    assert b.status == BESTAETIGT and not b.widerspricht


@pytest.mark.parametrize("zustand", ["OutOfStock", "SoldOut", "Discontinued"])
def test_schema_verfuegbarkeit_schlaegt_durch(zustand):
    b = analysiere(JSONLD % ("0.00", zustand), erwartet_gratis=True)
    assert b.status == ABGELAUFEN and b.widerspricht


def test_opengraph_wird_gelesen():
    assert analysiere(OPENGRAPH, erwartet_eur=19.99).status == BESTAETIGT
    assert analysiere(OPENGRAPH, erwartet_eur=4.99).status == WIDERLEGT


def test_microdata_wird_gelesen():
    b = analysiere(MICRODATA, erwartet_gratis=True)
    assert b.status == BESTAETIGT and b.herkunft == "microdata"


def test_cent_abweichung_ist_kein_widerspruch():
    """Rundung und Waehrungsumrechnung duerfen keinen Alarm ausloesen."""
    assert analysiere(OPENGRAPH, erwartet_eur=19.60).status == BESTAETIGT


@pytest.mark.parametrize("code", [404, 410])
def test_verschwundene_seite(code):
    assert analysiere("<html></html>", status_code=code).status == ABGELAUFEN


def test_ohne_ausgezeichneten_preis_wird_nicht_geraten():
    """Der wichtigste Test: bei Unsicherheit bleibt die Quelle im Recht."""
    b = analysiere("<html><body><p>Toller Deal, nur heute!</p></body></html>",
                   erwartet_gratis=True)
    assert b.status == UNKLAR and not b.widerspricht


def test_cloudflare_abweisung_urteilt_nicht():
    cf = ("<html><head><title>Just a moment...</title></head>"
          "<body>Checking your browser before accessing</body></html>")
    assert analysiere(cf, erwartet_gratis=True).status == UNKLAR


def test_marker_im_skript_zaehlt_nicht():
    """JS-Vorlagen enthalten reihenweise 'ausverkauft'-Bausteine.

    Wer die mitliest, erklaert jeden zweiten Shop fuer ausverkauft.
    """
    seite = ('<html><body><h1>Super Deal</h1></body>'
             '<script>var t = {leer: "ausverkauft", weg: "abgelaufen"};</script>'
             '</html>')
    assert analysiere(seite, erwartet_gratis=True).status == UNKLAR


def test_klartext_marker_zaehlt_ohne_preisangabe():
    seite = "<html><body><p>Dieses Angebot ist leider abgelaufen.</p></body></html>"
    assert analysiere(seite, erwartet_gratis=True).status == ABGELAUFEN


# --- Uebernahme in den Deal ------------------------------------------------

def test_widerlegt_korrigiert_den_deal():
    deal = Deal(titel="Spiel", url="https://x.test/a", ist_gratis=True,
                preis=0.0, preis_eur=0.0, originalpreis=29.99,
                rabatt_prozent=100.0)
    befund = analysiere(JSONLD % ("14.99", "InStock"), erwartet_gratis=True)
    assert uebernehme(deal, befund) is True
    assert deal.ist_gratis is False
    assert deal.preis == 14.99 and deal.preis_eur == 14.99
    assert deal.rabatt_prozent == 50.0          # gegen die 29,99 gerechnet
    assert deal.check_status == WIDERLEGT and deal.check_am is not None


def test_abgelaufen_aendert_keine_zahl():
    """Der Deal war richtig, als er gemeldet wurde - nur vorbei ist er."""
    deal = Deal(titel="Spiel", url="https://x.test/a", ist_gratis=True,
                preis=0.0, preis_eur=0.0)
    befund = analysiere(JSONLD % ("0.00", "OutOfStock"), erwartet_gratis=True)
    assert uebernehme(deal, befund) is False
    assert deal.ist_gratis is True and deal.preis == 0.0
    assert deal.check_status == ABGELAUFEN


def test_unklar_laesst_alles_wie_es_war():
    deal = Deal(titel="Spiel", url="https://x.test/a", ist_gratis=True, preis=0.0)
    uebernehme(deal, analysiere("<html></html>", erwartet_gratis=True))
    assert deal.ist_gratis is True
    assert deal.check_status == UNKLAR


# --- Auswahl und Lauf ------------------------------------------------------

@pytest.mark.parametrize("gratis,preis_eur,erwartet", [
    (True, 0.0, True),          # als geschenkt gemeldet
    (False, 0.99, True),        # verdaechtig billig
    (False, 49.0, False),       # normaler Deal - kein Grund nachzusehen
])
def test_kandidatenauswahl(gratis, preis_eur, erwartet):
    deal = Deal(titel="x", url="https://x.test/a", ist_gratis=gratis,
                preis_eur=preis_eur)
    assert ist_kandidat(deal) is erwartet


def test_ohne_url_kein_kandidat():
    assert ist_kandidat(Deal(titel="x", url="", ist_gratis=True)) is False


class _Antwort:
    def __init__(self, text, status=200, typ="text/html; charset=utf-8"):
        self.text = text
        self.content = text.encode()
        self.status_code = status
        self.headers = {"content-type": typ}


class _Http:
    """Minimaler Ersatz fuer den PoliteClient."""

    def __init__(self, seiten):
        self.seiten = seiten
        self.abgerufen = []

    async def get(self, url, **kwargs):
        self.abgerufen.append(url)
        if url not in self.seiten:
            raise RuntimeError("nicht erreichbar")
        return _Antwort(self.seiten[url])


class _DB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_lauf_korrigiert_und_sperrt():
    frei = Deal(titel="echt gratis", url="https://a.test/1", ist_gratis=True,
                preis=0.0, preis_eur=0.0)
    frei.id = 1
    falsch = Deal(titel="angeblich gratis", url="https://a.test/2",
                  ist_gratis=True, preis=0.0, preis_eur=0.0)
    falsch.id = 2
    teuer = Deal(titel="normal", url="https://a.test/3", ist_gratis=False,
                 preis=49.0, preis_eur=49.0)
    teuer.id = 3

    http = _Http({
        "https://a.test/1": JSONLD % ("0.00", "InStock"),
        "https://a.test/2": JSONLD % ("14.99", "InStock"),
        "https://a.test/3": JSONLD % ("49.00", "InStock"),
    })
    bilanz = await pruefe_deals(_DB(), http, [frei, falsch, teuer])

    assert bilanz["geprueft"] == 2          # der teure war gar kein Kandidat
    assert bilanz["korrigiert"] == 1
    assert bilanz["gesperrt"] == [2]
    assert "https://a.test/3" not in http.abgerufen
    assert falsch.ist_gratis is False and frei.ist_gratis is True


@pytest.mark.asyncio
async def test_deckel_wird_eingehalten():
    """Sonst wird aus der Gegenprobe ein Crawler."""
    deals = []
    for i in range(10):
        d = Deal(titel=f"d{i}", url=f"https://a.test/{i}", ist_gratis=True,
                 preis=0.0, preis_eur=0.0)
        d.id = i
        deals.append(d)
    http = _Http({f"https://a.test/{i}": JSONLD % ("0.00", "InStock")
                  for i in range(10)})
    bilanz = await pruefe_deals(_DB(), http, deals, grenze=3)
    assert bilanz["geprueft"] == 3 and len(http.abgerufen) == 3


@pytest.mark.asyncio
async def test_netzfehler_ist_kein_urteil():
    deal = Deal(titel="x", url="https://tot.test/1", ist_gratis=True,
                preis=0.0, preis_eur=0.0)
    deal.id = 7
    bilanz = await pruefe_deals(_DB(), _Http({}), [deal])
    assert bilanz["korrigiert"] == 0 and bilanz["gesperrt"] == []
    assert deal.ist_gratis is True


@pytest.mark.asyncio
async def test_nicht_html_wird_nicht_ausgewertet():
    class NurJson(_Http):
        async def get(self, url, **kwargs):
            return _Antwort('{"preis": 14.99}', typ="application/json")

    befund = await pruefe(NurJson({}), "https://a.test/x", erwartet_gratis=True)
    assert befund.status == UNKLAR and not befund.widerspricht
