"""Waehrungsumrechnung - ohne sie greifen Preisregeln quellenabhaengig falsch."""
import pytest

from app.currency import DEFAULT_RATES, get_rates, set_rates, to_eur


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
