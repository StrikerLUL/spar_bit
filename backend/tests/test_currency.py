"""Waehrungsumrechnung - ohne sie greifen Preisregeln quellenabhaengig falsch."""
import pytest

from app.currency import (
    DEFAULT_RATES,
    KeinKurs,
    alter_in_tagen,
    aus_ezb_xml,
    get_rates,
    ist_veraltet,
    set_rates,
    to_eur,
)


@pytest.fixture(autouse=True)
def reset_rates():
    set_rates(None)
    yield
    set_rates(None)


def test_eur_bleibt_unveraendert():
    assert to_eur(19.99, "EUR") == 19.99


def test_usd_wird_umgerechnet():
    assert to_eur(10.0, "USD") == round(10.0 * DEFAULT_RATES["USD"], 2)


def test_gbp_ist_mehr_wert_als_eur():
    assert to_eur(10.0, "GBP") > 10.0


def test_fehlender_betrag():
    assert to_eur(None, "USD") is None


def test_unbekannte_waehrung_gibt_none():
    """Lieber kein Wert als ein falscher - sonst rutscht ein teurer Deal
    durch eine 'max. 20 EUR'-Regel."""
    assert to_eur(10.0, "XYZ") is None


def test_kurse_koennen_gesetzt_werden():
    set_rates({"USD": 0.5})
    assert to_eur(10.0, "USD") == 5.0


def test_unsinnige_kurse_werden_verworfen():
    set_rates({"USD": -1, "GBP": 0, "CHF": "keine Zahl", "PLN": 99999})
    kurse = get_rates()
    assert kurse["USD"] == DEFAULT_RATES["USD"]
    assert kurse["GBP"] == DEFAULT_RATES["GBP"]
    assert kurse["CHF"] == DEFAULT_RATES["CHF"]
    assert kurse["PLN"] == DEFAULT_RATES["PLN"]


def test_eur_kurs_bleibt_immer_eins():
    set_rates({"EUR": 42.0})
    assert to_eur(5.0, "EUR") == 5.0


def test_kleinschreibung_wird_erkannt():
    assert to_eur(10.0, "usd") == to_eur(10.0, "USD")


# --- EZB-Kurse -------------------------------------------------------------
#
# Die Umkehrung ist der ganze Trick, und sie ist die Stelle, an der ein
# Fehler jahrelang unbemerkt bliebe: 0,92 und 1,09 sehen beide plausibel
# aus. Darum wird hier mit einer Zahl geprueft, bei der die Richtung
# eindeutig ist.

EZB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2026-09-21">
      <Cube currency="USD" rate="1.0870"/>
      <Cube currency="GBP" rate="0.8340"/>
      <Cube currency="CHF" rate="0.9350"/>
      <Cube currency="PLN" rate="4.2700"/>
      <Cube currency="AUD" rate="1.6200"/>
      <Cube currency="JPY" rate="160.5000"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


def test_die_kurse_werden_umgedreht():
    """Die EZB sagt „1 EUR = 1,087 USD". SparBit braucht die Gegenrichtung."""
    kurse, _ = aus_ezb_xml(EZB_XML)
    assert kurse["USD"] == pytest.approx(1 / 1.0870, abs=1e-5)
    # Ein Dollar ist weniger wert als ein Euro - und ein Pfund mehr.
    assert kurse["USD"] < 1.0
    assert kurse["GBP"] > 1.0


def test_der_stand_kommt_mit():
    """Ein Kurs ohne Datum sieht aus wie einer von heute."""
    _, stand = aus_ezb_xml(EZB_XML)
    assert stand == "2026-09-21"


def test_nur_was_sparbit_kennt():
    """Die EZB liefert 30 Waehrungen. Der Rest waere nur Ballast."""
    kurse, _ = aus_ezb_xml(EZB_XML)
    assert "JPY" not in kurse
    assert kurse["EUR"] == 1.0


def test_muell_wird_nicht_zu_kursen():
    with pytest.raises(KeinKurs):
        aus_ezb_xml("<html>Wartungsarbeiten</html>")
    with pytest.raises(KeinKurs):
        aus_ezb_xml("kein xml")


def test_eine_antwort_ohne_datum_gilt_nicht():
    ohne_zeit = EZB_XML.replace(' time="2026-09-21"', "")
    with pytest.raises(KeinKurs):
        aus_ezb_xml(ohne_zeit)


def test_ein_kurs_von_null_wird_uebergangen():
    """Sonst gaebe es eine Division durch null - und einen Preis von unendlich."""
    kaputt = EZB_XML.replace('rate="1.0870"', 'rate="0"')
    kurse, _ = aus_ezb_xml(kaputt)
    assert "USD" not in kurse
    assert "GBP" in kurse           # der Rest bleibt brauchbar


def test_alter_und_veraltung():
    from datetime import UTC, datetime, timedelta

    heute = datetime.now(UTC).date().isoformat()
    assert alter_in_tagen(heute) == 0
    assert not ist_veraltet(heute)

    alt = (datetime.now(UTC).date() - timedelta(days=200)).isoformat()
    assert alter_in_tagen(alt) == 200
    assert ist_veraltet(alt)

    # Nie geholt zaehlt als veraltet: die Vorgabewerte im Code sind
    # eingefroren und werden mit jedem Monat schlechter.
    assert alter_in_tagen(None) is None
    assert ist_veraltet(None)
    assert alter_in_tagen("kein datum") is None
