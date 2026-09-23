"""Slickdeals und OzBargain - und die Frage der Waehrung.

Der Grund, warum diese beiden Quellen eine eigene Klasse haben und nicht
einfach „noch ein RSS-Feed" sind: sie rechnen in USD und AUD. Ohne
festgelegte Vorgabe liefe ein „$ 199" als EUR durch jede Preisregel, und
„max. 200 EUR" wuerde bei einem Deal von umgerechnet 180 EUR mal greifen
und mal nicht - je nachdem, ob im Titel ein Waehrungszeichen stand.
"""
import pytest

from app.sources import get_source

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Anker USB-C Charger $19.99 (was $39.99)</title>
    <link>https://slickdeals.net/f/1</link>
    <description>Guter Preis</description>
  </item>
  <item>
    <title>Kindle Paperwhite 16GB</title>
    <link>https://slickdeals.net/f/2</link>
    <description>Ohne Preis im Titel</description>
  </item>
</channel></rss>"""


@pytest.mark.parametrize("quelle_id,waehrung", [("slickdeals", "USD"),
                                                ("ozbargain", "AUD")])
def test_beide_quellen_sind_registriert(quelle_id, waehrung):
    quelle = get_source(quelle_id)
    assert quelle is not None
    assert quelle.waehrung == waehrung
    assert quelle.display_name and quelle.beschreibung
    # Ungeprueft, bis es jemand auf einem echten Rechner geprueft hat.
    assert quelle.verification.value == "unverified"


def test_die_waehrung_der_quelle_gilt_wenn_der_titel_schweigt():
    """Der Preisparser erkennt die Waehrung nur am Zeichen. Fehlt es,
    darf nicht EUR angenommen werden."""
    posten = get_source("ozbargain").parse(FEED, "AUD")
    ohne_preis = [p for p in posten if p.preis is None]
    assert ohne_preis and ohne_preis[0].waehrung == "AUD"


def test_ein_waehrungszeichen_im_titel_gewinnt():
    posten = get_source("slickdeals").parse(FEED, "USD")
    assert posten[0].preis == 19.99
    assert posten[0].waehrung == "USD"
    assert posten[0].originalpreis == 39.99


def test_die_eigene_id_steht_in_jedem_posten():
    """Sonst liessen sich die Funde im Feed nicht nach Quelle filtern."""
    for posten in get_source("slickdeals").parse(FEED, "USD"):
        assert posten.quelle == "slickdeals"


def test_eintraege_ohne_link_werden_uebergangen():
    kaputt = FEED.replace("<link>https://slickdeals.net/f/1</link>", "")
    assert len(get_source("slickdeals").parse(kaputt, "USD")) == 1


def test_die_feed_adresse_ist_im_ui_aenderbar():
    """Viele dieser Seiten bieten Feeds je Kategorie - und eine Adresse,
    die nur im Code steht, kann niemand umstellen."""
    schluessel = {f.key for f in get_source("slickdeals").options_schema}
    assert {"feed_url", "waehrung", "max_items"} <= schluessel
