"""Preisurteil. Der gemeldete Rabatt taugt nichts - der eigene Verlauf schon."""
from datetime import datetime, timedelta, timezone

import pytest

from app.verdict import (BESTPREIS, GUT, MIN_PUNKTE, NORMAL, SEHR_GUT, TEURER,
                         UNBEKANNT, UVP_FRAGWUERDIG, bewerte, euro, mindestens)


def verlauf(preise: list[float], abstand_tage: int = 3):
    jetzt = datetime.now(timezone.utc)
    return [(p, jetzt - timedelta(days=(len(preise) - i) * abstand_tage))
            for i, p in enumerate(preise)]


HISTORIE = [349.0, 299.0, 299.0, 279.0, 259.0, 249.0]


def test_neuer_tiefstpreis_ist_bestpreis():
    assert bewerte(199.0, verlauf(HISTORIE)).stufe == BESTPREIS


def test_knapp_ueber_dem_tiefstwert_ist_sehr_gut():
    assert bewerte(252.0, verlauf(HISTORIE)).stufe == SEHR_GUT


def test_am_median_ist_normal():
    assert bewerte(285.0, verlauf(HISTORIE)).stufe == NORMAL


def test_deutlich_ueber_dem_median_war_schon_guenstiger():
    urteil = bewerte(320.0, verlauf(HISTORIE))
    assert urteil.stufe == TEURER
    assert "249,00" in urteil.text          # nennt den besseren Preis


def test_gratis_ist_immer_bestpreis():
    assert bewerte(0.0, [], ist_gratis=True).stufe == BESTPREIS


# --- Ehrlichkeit bei duenner Datenlage ------------------------------------

@pytest.mark.parametrize("anzahl", range(MIN_PUNKTE))
def test_zu_wenige_messungen_geben_kein_urteil(anzahl):
    """Bei zwei Punkten ist jeder zweite Preis zwangslaeufig 'der beste'.
    Das waere Zufall, kein Urteil - lieber ehrlich nichts sagen."""
    urteil = bewerte(99.0, verlauf([200.0] * anzahl))
    assert urteil.stufe == UNBEKANNT


def test_ohne_preis_kein_urteil():
    assert bewerte(None, verlauf(HISTORIE)).stufe == UNBEKANNT


def test_ab_genug_messungen_wird_geurteilt():
    urteil = bewerte(99.0, verlauf([200.0] * MIN_PUNKTE))
    assert urteil.stufe != UNBEKANNT


# --- Aufgeblasene UVP -----------------------------------------------------

def test_unglaubwuerdige_uvp_wird_benannt():
    """Ein Artikel, der nie ueber 119 EUR lag, hat keine UVP von 399 EUR -
    ein daran gerechneter Rabatt ist wertlos."""
    urteil = bewerte(99.0, verlauf([119.0, 109.0, 115.0, 105.0, 99.0]),
                     originalpreis_eur=399.0)
    assert urteil.stufe == UVP_FRAGWUERDIG
    assert "399,00" in urteil.text and "119,00" in urteil.text


def test_plausible_uvp_wird_nicht_bemaengelt():
    urteil = bewerte(99.0, verlauf([149.0, 139.0, 145.0, 129.0, 119.0]),
                     originalpreis_eur=159.0)
    assert urteil.stufe != UVP_FRAGWUERDIG


def test_uvp_pruefung_braucht_auch_genug_daten():
    urteil = bewerte(99.0, verlauf([119.0, 109.0]), originalpreis_eur=399.0)
    assert urteil.stufe == UNBEKANNT


# --- Hilfsfunktionen ------------------------------------------------------

@pytest.mark.parametrize("wert,erwartet", [
    (1234.5, "1.234,50 €"), (99.0, "99,00 €"), (0.5, "0,50 €"), (0.0, "0,00 €"),
])
def test_euro_formatierung(wert, erwartet):
    """Der Satzpunkt darf nicht mit dem Dezimaltrenner verwechselt werden."""
    assert euro(wert) == erwartet


def test_mindestens_liefert_die_besseren_stufen():
    assert mindestens(GUT) == [BESTPREIS, SEHR_GUT, GUT]
    assert BESTPREIS in mindestens(NORMAL)
    assert TEURER not in mindestens(GUT)


def test_urteil_nennt_die_zahl_der_messungen():
    urteil = bewerte(199.0, verlauf(HISTORIE))
    assert urteil.punkte == len(HISTORIE)
