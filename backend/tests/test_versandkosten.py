"""Versandkosten: zwei Preise sind erst vergleichbar, wenn beide dasselbe meinen.

195 EUR plus 9,90 EUR Versand sind teurer als 199 EUR versandkostenfrei.
Ohne diese Zahl meldet die Wunschliste einen erreichten Zielpreis, der
an der Kasse nicht stimmt.

Der wichtigste Fall ist auch hier der leere: **kein Eintrag heisst nicht
kostenlos.** Wer das verwechselt, rechnet fuer jeden Shop ohne Angabe mit
0 EUR Versand - und das ist eine erfundene Zahl.
"""
from app.pricewatch import aus_jsonld, preis_aus_seite, render_adresse


def seite(jsonld: str) -> str:
    return f'<html><script type="application/ld+json">{jsonld}</script></html>'


def test_versandkosten_werden_gelesen():
    fund = aus_jsonld(seite('''{
      "@type": "Product", "name": "Kopfhörer",
      "offers": {"@type": "Offer", "price": "195.00", "priceCurrency": "EUR",
                 "shippingDetails": {"@type": "OfferShippingDetails",
                   "shippingRate": {"@type": "MonetaryAmount",
                                    "value": "9.90", "currency": "EUR"}}}
    }'''))
    assert fund.preis == 195.0
    assert fund.versand == 9.90
    assert fund.gesamt == 204.90


def test_ohne_angabe_bleibt_es_unbekannt():
    """None heisst „steht nicht da" - nicht „kostenlos"."""
    fund = aus_jsonld(seite('''{
      "@type": "Product", "name": "Kopfhörer",
      "offers": {"@type": "Offer", "price": "195.00", "priceCurrency": "EUR"}
    }'''))
    assert fund.versand is None
    # Der Gesamtpreis ist dann der Artikelpreis - mit derselben
    # Unsicherheit wie vorher, nicht mit einer zusaetzlichen.
    assert fund.gesamt == 195.0


def test_gratis_versand_ist_eine_information():
    """Eine ausdrueckliche 0 unterscheidet sich von „keine Angabe"."""
    fund = aus_jsonld(seite('''{
      "@type": "Product", "name": "Buch",
      "offers": {"@type": "Offer", "price": "19.99", "priceCurrency": "EUR",
                 "shippingDetails": {"shippingRate": {"value": 0, "currency": "EUR"}}}
    }'''))
    assert fund.versand == 0.0
    assert fund.gesamt == 19.99


def test_bei_mehreren_optionen_zaehlt_die_guenstigste():
    """Wer Express will, rechnet selbst - im Vergleich zaehlt der Normalversand."""
    fund = aus_jsonld(seite('''{
      "@type": "Product", "name": "Monitor",
      "offers": {"@type": "Offer", "price": "299.00", "priceCurrency": "EUR",
                 "shippingDetails": [
                   {"shippingRate": {"value": "14.99"}},
                   {"shippingRate": {"value": "4.99"}}]}
    }'''))
    assert fund.versand == 4.99


def test_unsinn_im_versandfeld_wird_uebergangen():
    """Lieber keine Versandkosten als geratene."""
    fund = aus_jsonld(seite('''{
      "@type": "Product", "name": "Ding",
      "offers": {"@type": "Offer", "price": "10.00", "priceCurrency": "EUR",
                 "shippingDetails": "auf Anfrage"}
    }'''))
    assert fund.preis == 10.0
    assert fund.versand is None


def test_der_preis_geht_vor():
    """Ein kaputtes Versandfeld darf den Fund nicht mitreissen."""
    fund = preis_aus_seite(seite('''{
      "@type": "Product", "name": "Ding",
      "offers": {"@type": "Offer", "price": "10.00", "priceCurrency": "EUR",
                 "shippingDetails": {"shippingRate": {"value": "keine Zahl"}}}
    }'''))
    assert fund.preis == 10.0
    assert fund.versand is None


# --- Render-Dienst ---------------------------------------------------------

def test_render_adresse_setzt_die_zielseite_ein():
    adresse = render_adresse("http://browserless:3000/content?url={url}",
                             "https://shop.test/artikel?id=1")
    assert "https%3A%2F%2Fshop.test%2Fartikel%3Fid%3D1" in adresse


def test_ohne_platzhalter_gibt_es_keine_adresse():
    """Sonst landete jeder Abruf auf der Startseite des Dienstes - und die
    leere Antwort saehe aus wie „Shop liefert keinen Preis"."""
    assert render_adresse("http://browserless:3000/content", "https://x.test") is None
    assert render_adresse("", "https://x.test") is None
    assert render_adresse(None, "https://x.test") is None
