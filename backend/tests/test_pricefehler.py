"""Preisfehler-Erkennung.

Die Tests sind in zwei Haelften geteilt, und die zweite ist die wichtigere:
Ein Detektor, der jeden Preisfehler findet, aber bei jedem Steam-Sale
mitschreit, ist schlechter als keiner - er wird nach einer Woche
stummgeschaltet. Darum steht hinter jedem "findet es"-Test ein
"meldet es nicht"-Test.
"""
import pytest

from app.pricefehler import HEISS, KEIN, VERDACHT, bewerte

# --- Was ein Preisfehler ist ----------------------------------------------

def test_ausdrueckliche_nennung_plus_beleg():
    """Der Standardfall auf mydealz: jemand schreibt "Preisfehler" dazu."""
    u = bewerte(
        "Preisfehler? Bosch Waschmaschine für 89,99€",
        89.99,
        verlauf_eur=[649.0, 629.0, 679.0, 599.0, 649.0],
        quelle="mydealz")
    assert u.stufe == HEISS
    assert u.punkte >= 70
    assert any("Preisfehler" in g for g in u.gruende)


def test_verrutschte_kommastelle():
    """899,00 -> 89,90 ist Faktor 10 - die Signatur eines Tippfehlers."""
    u = bewerte("LG OLED 55 Zoll Fernseher", 89.90,
                originalpreis_eur=899.0, rabatt_prozent=90.0,
                verlauf_eur=[899.0, 879.0, 949.0, 899.0],
                quelle="mydealz")
    assert u.stufe == HEISS
    assert any("Komma" in g for g in u.gruende)


def test_andere_quellen_verlangen_ein_vielfaches():
    u = bewerte("Dyson V15 Akkusauger", 59.0,
                fremdpreise_eur=[549.0, 579.0, 529.0],
                verlauf_eur=[549.0, 539.0, 559.0, 549.0],
                quelle="mydealz")
    assert u.stufe == HEISS
    assert u.erwartet_eur and u.erwartet_eur > 500


def test_begruendung_ist_lesbar_und_nennt_zahlen():
    """In der Meldung soll nicht '87 Punkte' stehen, sondern warum."""
    u = bewerte("Kaffeevollautomat", 39.0,
                verlauf_eur=[449.0, 429.0, 469.0, 449.0],
                fremdpreise_eur=[439.0],
                quelle="mydealz")
    assert u.gruende, "ohne Begruendung ist die Meldung wertlos"
    text = u.kurz()
    assert "€" in text
    assert not text.startswith("Preisfehler-Verdacht")   # kein blosses Label


def test_vage_nennung_zaehlt_schwaecher():
    """'vermutlich Preisfehler' ist ein Hinweis, keine Feststellung."""
    stark = bewerte("Preisfehler: Monitor 34 Zoll", 45.0,
                    verlauf_eur=[399.0, 389.0, 409.0, 399.0])
    schwach = bewerte("Vermutlich Preisfehler: Monitor 34 Zoll", 45.0,
                      verlauf_eur=[399.0, 389.0, 409.0, 399.0])
    assert stark.punkte > schwach.punkte


# --- Was keiner ist --------------------------------------------------------

def test_gratis_ist_kein_fehler():
    """Ein Freebie ist Absicht, kein Versehen."""
    u = bewerte("Epic: Control kostenlos", 0.0, ist_gratis=True,
                originalpreis_eur=29.99, rabatt_prozent=100.0)
    assert u.stufe == KEIN
    assert u.punkte == 0


def test_steam_sale_ist_kein_fehler():
    """90 Prozent auf ein altes Spiel ist bei Key-Shops der Normalfall."""
    u = bewerte("Hitman 3 im Sale", 4.99,
                originalpreis_eur=59.99, rabatt_prozent=92.0,
                verlauf_eur=[59.99, 29.99, 59.99, 19.99],
                quelle="steam")
    assert u.stufe != HEISS


def test_gutschein_und_sammeldeal_fallen_raus():
    for titel in ("50€ Gutschein für 5€", "Sammeldeal: diverse Artikel ab 1€",
                  "Handyvertrag 5GB für 4,99€ monatlich",
                  "iPhone 14 refurbished B-Ware 89€"):
        u = bewerte(titel, 4.99, verlauf_eur=[199.0, 189.0, 209.0, 199.0])
        assert u.stufe == KEIN, f"haette nicht anschlagen duerfen: {titel}"


def test_kleinbetrag_meldet_nicht():
    """Rechnerisch ein Zehntel, praktisch drei Euro. Kein Weckruf wert."""
    u = bewerte("Kugelschreiber 4er-Pack", 0.30,
                verlauf_eur=[3.0, 3.2, 2.9, 3.1],
                fremdpreise_eur=[2.99])
    assert u.stufe != HEISS


def test_ohne_referenz_keine_meldung():
    """Ohne Verlauf und ohne Fremdpreis wissen wir nicht, wovon der Preis
    abweicht - eine Punktzahl waere geraten."""
    u = bewerte("Irgendein Artikel", 9.99, quelle="mydealz")
    assert u.stufe == KEIN


def test_fragwuerdige_uvp_belegt_nichts():
    """Wenn die UVP selbst unglaubwuerdig ist, darf der Rabatt darauf kein
    Indiz sein - sonst belegt ein erfundener Listenpreis einen Preisfehler."""
    mit = bewerte("Gartenschlauch 50m", 19.99,
                  originalpreis_eur=199.0, rabatt_prozent=90.0,
                  uvp_fragwuerdig=True)
    ohne = bewerte("Gartenschlauch 50m", 19.99,
                   originalpreis_eur=199.0, rabatt_prozent=90.0,
                   uvp_fragwuerdig=False)
    assert mit.punkte < ohne.punkte
    assert mit.stufe != HEISS


def test_normaler_guter_deal_bleibt_ruhig():
    """30 Prozent unter dem Ueblichen ist ein guter Kauf, kein Fehler."""
    u = bewerte("Sony WH-1000XM5", 249.0,
                originalpreis_eur=379.0, rabatt_prozent=34.0,
                verlauf_eur=[349.0, 329.0, 359.0, 339.0],
                quelle="mydealz")
    assert u.stufe == KEIN


def test_hitze_allein_reicht_nicht():
    """Ein heiss diskutierter Deal ist noch kein Preisfehler."""
    u = bewerte("Beliebter Deal", 199.0, temperatur=1200.0, quelle="mydealz")
    assert u.stufe == KEIN


@pytest.mark.parametrize("preis", [None, 0.0, -1.0])
def test_ohne_preis_kein_urteil(preis):
    assert bewerte("Artikel", preis).stufe == KEIN


# --- Abstufung -------------------------------------------------------------

def test_verdacht_liegt_zwischen_den_stufen():
    """Auffaellig, aber nicht belegt: in den Feed, nicht aufs Handy."""
    u = bewerte("Grafikkarte RTX 4070", 149.0,
                verlauf_eur=[549.0, 529.0, 569.0, 549.0],
                quelle="mydealz")
    assert u.stufe in (VERDACHT, HEISS)
    assert u.punkte >= 45


def test_punkte_bleiben_im_bereich():
    u = bewerte("Preisfehler! Preisfehler! TV", 8.99,
                originalpreis_eur=899.0, rabatt_prozent=99.0,
                verlauf_eur=[899.0, 879.0, 929.0, 899.0],
                fremdpreise_eur=[879.0], temperatur=2000.0)
    assert 0 <= u.punkte <= 100
