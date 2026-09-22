"""Gutschein-Codes: das Nicht-Finden ist die eigentliche Aufgabe.

Ein Muster, das grosszuegig ist, schreibt in jede zweite Meldung einen
erfundenen Code. Das ist schlimmer als gar keiner, weil man ihm glaubt
und damit an der Kasse steht. Die Faelle unten sind darum zur Haelfte
solche, in denen NICHTS herauskommen darf.
"""
import pytest

from app.gutschein import finde


@pytest.mark.parametrize("text,erwartet", [
    ("Nike Sale: 25% mit Code SOMMER25", "SOMMER25"),
    ("Gutscheincode: WELCOME-10 einlösen", "WELCOME-10"),
    ("Rabattcode BLACK_50 im Warenkorb", "BLACK_50"),
    ("Der Code lautet FRUEHLING", "FRUEHLING"),
    ('Mit dem Code "SPAREN20" 20 % sparen', "SPAREN20"),
    ("Voucher code SAVE15 applied at checkout", "SAVE15"),
    ("Promo Code: XMAS2024", "XMAS2024"),
    ("mit dem Code »NEU15«", "NEU15"),
])
def test_codes_werden_gefunden(text, erwartet):
    assert finde(text) == erwartet


@pytest.mark.parametrize("text", [
    # Produktbezeichnungen sehen aus wie Codes - und sind keine.
    "Sony WH-1000XM5 Kopfhörer für 199 €",
    "Samsung 990 PRO 2TB NVMe SSD",
    "LEGO Technic 42143 Ferrari Daytona",
    # Der Hinweis steht da, aber es folgt kein Code.
    "Kein Code nötig, Rabatt im Warenkorb",
    "code: checkout",
    "Der Rabatt wird automatisch abgezogen",
    # Ein Code-Wort ohne Hinweis davor zaehlt nicht.
    "BLACKFRIDAY Angebote bei MediaMarkt",
    # Zu kurz, um ein Code zu sein.
    "Code: XY",
])
def test_was_kein_gutschein_ist_bleibt_ungemeldet(text):
    assert finde(text) is None


def test_eine_lange_ziffernfolge_ist_eine_artikelnummer():
    """13 Ziffern hinter „Code" sind eine EAN, kein Gutschein."""
    assert finde("Artikel mit Code 4006381333931 bestellen") is None


def test_kurze_ziffernfolgen_gelten_als_aktionscode():
    """Viele Shops nutzen fuenfstellige Zahlen - die sind echt."""
    assert finde("Rabattcode 12345 eingeben") == "12345"


def test_der_titel_zaehlt_vor_der_beschreibung():
    """Steht in beiden einer, ist der im Titel fast immer der richtige."""
    assert finde("Deal mit Code TITEL10", "Anderer Code BESCHREIB20") == "TITEL10"


def test_kleinschreibung_wird_nicht_geraten():
    """Ein Code in Kleinbuchstaben ist von einem Wort nicht zu unterscheiden."""
    assert finde("mit dem code sommer") is None


def test_leere_eingaben_sind_kein_fehler():
    assert finde(None, "", None) is None
