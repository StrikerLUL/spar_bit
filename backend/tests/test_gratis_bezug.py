"""Worauf sich ein "gratis" im Deal-Text bezieht.

Das ist der Test zu der Beschwerde, die das ausgeloest hat: es steht
kostenlos da, man klickt, und die Seite will Geld. In den allermeisten
Faellen liegt das nicht an einem kaputten Parser, sondern daran, dass sich
das Wort auf den Versand, eine Zugabe oder einen Probemonat bezog.
"""
import pytest

from app.priceparse import is_free_text, parse_price_text, pruefe_gratis


@pytest.mark.parametrize("text,bezug", [
    ("Sony XM5 für 229 € statt 379 € inkl. gratis Versand", "versand"),
    ("Anker Powerbank 19,99 € - kostenloser Versand", "versand"),
    ("Portofrei bestellen: Buch 9,99 €", "versand"),
    ("Shirt 14,99 €, versandkostenfrei ab 20 €", "versand"),
    ("Buch 12,99 € - kostenlose Rücksendung", "rueckgabe"),
    ("3 Monate Spotify Premium gratis, danach 10,99 €/Monat", "probe"),
    ("Streaming 30 Tage kostenlos testen", "probe"),
    ("Nike Schuhe 49,99 € + gratis Socken dazu", "zugabe"),
    ("Girokonto mit gebührenfreier Kontoführung", "service"),
])
def test_gratis_wort_mit_bezug_zaehlt_nicht(text, bezug):
    befund = pruefe_gratis(text)
    assert befund.gratis is False, f"faelschlich als gratis erkannt: {text}"
    assert befund.bezug == bezug
    assert befund.einschraenkung


@pytest.mark.parametrize("text", [
    "Epic: Control gratis",
    "Gratis abstauben",
    "Zu verschenken: Sofa",
    "Free to keep",
    "kostenlos abgeben",
    "Gratis-Skin im Wert von 9,99 €",
    "Kostenlose App statt 4,99 €",
])
def test_echtes_gratis_bleibt_gratis(text):
    assert pruefe_gratis(text).gratis is True
    assert is_free_text(text) is True


def test_nullpreis_ist_gratis_ohne_gratis_wort():
    """Kein Gratis-Wort noetig - der Preis selbst genuegt."""
    assert pruefe_gratis("LEGO Set für 0,00 EUR").gratis is False
    assert parse_price_text("LEGO Set für 0,00 EUR").ist_gratis is True


@pytest.mark.parametrize("text", [
    "Freezer 7 Pro", "Freeman Kühlschrank", "Gefrierschrank",
])
def test_keine_wortteile(text):
    """'Freezer' ist kein 'free' - die alte Wortgrenzen-Regel bleibt."""
    assert pruefe_gratis(text).gratis is False


def test_ein_unbedingtes_gratis_schlaegt_ein_bedingtes():
    """Steht beides im Text, gewinnt das unbedingte.

    "Spiel geschenkt, dazu kostenloser Versand" ist geschenkt - es waere
    falsch, das an der zweiten Haelfte scheitern zu lassen.
    """
    befund = pruefe_gratis("Spiel geschenkt, dazu kostenloser Versand")
    assert befund.gratis is True


def test_versandhinweis_zerstoert_den_preis_nicht():
    p = parse_price_text("Sony XM5 statt 379 € jetzt 229 € inkl. gratis Versand")
    assert p.preis == 229.0 and p.originalpreis == 379.0
    assert p.ist_gratis is False
    assert p.gratis_einschraenkung == "gilt nur für den Versand"


def test_ausgezeichneter_aktueller_preis_schlaegt_das_gratis_wort():
    """Letzte Reissleine: "jetzt 9,99" und "geschenkt" koennen nicht beide
    stimmen. Die Zahl mit Signalwort davor ist die konkretere Angabe."""
    p = parse_price_text("Freebie-Aktion: jetzt 9,99 € für das Bundle")
    assert p.preis == 9.99
    p2 = parse_price_text("Gratis-Aktion - jetzt nur 4,99 €")
    assert p2.ist_gratis is False and p2.preis == 4.99


def test_wert_gilt_als_alter_preis():
    """Sonst wuerde der Gegenwert eines Geschenks zum Kaufpreis."""
    p = parse_price_text("Gratis-Skin im Wert von 9,99 €")
    assert p.ist_gratis is True
    assert p.preis == 0.0 and p.originalpreis == 9.99


# --- Beim Einsammeln -------------------------------------------------------

def test_quelle_meldet_gratis_und_nennt_trotzdem_einen_preis():
    """Letzte Reissleine im Pipeline-Eingang.

    Greift auch bei API-Quellen, deren Gratis-Status gar nicht aus Text
    stammt - z.B. wenn eine Kategorie "Freebies" heisst, der Artikel darin
    aber 4,99 kostet. Beides kann nicht stimmen; die Zahl ist konkreter.
    """
    from app.pipeline import _entwirre_gratis
    from app.sources.base import DealItem

    item = DealItem(titel="Bundle", url="https://x.test/1", quelle="test",
                    preis=4.99, ist_gratis=True, rabatt_prozent=100.0)
    sauber = _entwirre_gratis(item)
    assert sauber.ist_gratis is False
    assert sauber.preis == 4.99
    assert sauber.rabatt_prozent is None
    assert sauber.roh["gratis_hinweis"]


def test_echter_nullpreis_bleibt_unangetastet():
    from app.pipeline import _entwirre_gratis
    from app.sources.base import DealItem

    item = DealItem(titel="Control", url="https://x.test/2", quelle="epic",
                    preis=0.0, ist_gratis=True)
    assert _entwirre_gratis(item) is item
