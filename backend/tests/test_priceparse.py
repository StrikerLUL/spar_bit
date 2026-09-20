"""Preis-Parsing gegen die Formate, die in echten Feeds vorkommen."""
import pytest

from app.priceparse import (detect_currency, is_free_text, parse_number,
                            parse_percent, parse_price_text)


@pytest.mark.parametrize("raw,expected", [
    ("12,99", 12.99), ("1.299,00", 1299.0), ("1,299.00", 1299.0),
    ("99", 99.0), ("0,00", 0.0), ("1.234.567,89", 1234567.89),
    ("1,234", 1234.0), ("9.99", 9.99), ("", None), ("abc", None),
])
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize("text,preis,orig,rabatt,gratis", [
    ("12,99€ statt 89,90€", 12.99, 89.90, 85.6, False),
    ("Nur 1.299,00 € statt 1.899,00 €", 1299.0, 1899.0, 31.6, False),
    ("Deal für 4,99 statt 19,99", 4.99, 19.99, 75.0, False),
    ("$9.99 (was $39.99)", 9.99, 39.99, 75.0, False),
    ("LEGO Set für 0,00 EUR", 0.0, None, None, True),
    ("Gratis abstauben", 0.0, None, None, True),
    ("geschenkt statt 59,99€", 0.0, 59.99, 100.0, True),
    ("Kopfhörer 89,90 €", 89.90, None, None, False),
])
def test_parse_price_text(text, preis, orig, rabatt, gratis):
    p = parse_price_text(text)
    assert p.preis == preis
    assert p.originalpreis == orig
    assert (round(p.rabatt_prozent, 1) if p.rabatt_prozent else None) == rabatt
    assert p.ist_gratis is gratis


@pytest.mark.parametrize("text", [
    "LEGO Bausatz Artikelnummer 42115",
    "Buch mit 320 Seiten",
    "Version 2.50 erschienen",
    "Modell WH-1000XM5",
])
def test_keine_falschen_preise(text):
    """Zahlen ohne Preis-Kontext duerfen nicht als Preis durchgehen."""
    assert parse_price_text(text).preis is None


@pytest.mark.parametrize("text,pct", [
    ("-95%", 95.0), ("bis zu 70 % Rabatt", 70.0), ("50% und 80% im Sale", 80.0),
    ("kein Prozent hier", None), ("120% ungueltig", None),
])
def test_parse_percent(text, pct):
    assert parse_percent(text) == pct


def test_hundert_prozent_ist_gratis():
    p = parse_price_text("Steam: Titel 100% off")
    assert p.ist_gratis and p.preis == 0.0


@pytest.mark.parametrize("text,frei", [
    ("gratis", True), ("kostenlos abgeben", True), ("Zu verschenken", True),
    ("Free to keep", True), ("Freezer 7 Pro", False), ("Freeman Kühlschrank", False),
    ("Gefrierschrank", False),
])
def test_is_free_text(text, frei):
    assert is_free_text(text) is frei


def test_detect_currency():
    assert detect_currency("12,99 €") == "EUR"
    assert detect_currency("$5") == "USD"
    assert detect_currency("nur Text") is None


def test_original_aus_rabatt_hergeleitet():
    p = parse_price_text("Jetzt 10,00 € (-50%)")
    assert p.preis == 10.0
    assert p.originalpreis == 20.0


# --- Richtungs-Regression --------------------------------------------------
# Diese Faelle lieferten frueher den durchgestrichenen UVP als aktuellen
# Preis. Sie stehen hier einzeln, damit ein Rueckfall sofort auffaellt.

@pytest.mark.parametrize("text,preis,orig", [
    # "statt" steht VOR beiden Preisen - der erste danach ist der alte.
    ("statt 59,99 nur 9,99", 9.99, 59.99),
    ("Sony WH-1000XM5 statt 379 € jetzt 229 €", 229.0, 379.0),
    ("LEGO 42115 statt 349,99 € nur 249 €", 249.0, 349.99),
    # Nur einer der beiden Betraege traegt ein Waehrungszeichen.
    ("Nur 9,99 statt 19,99 €", 9.99, 19.99),
    ("iPhone 15 für 699 statt 949 Euro", 699.0, 949.0),
    # Reihenfolge andersherum - muss weiterhin stimmen.
    ("PS5 Slim 349€ statt 549,99€", 349.0, 549.99),
    ("Angebot: 49,99 € (UVP 129,99 €)", 49.99, 129.99),
])
def test_richtung_preis_und_uvp(text, preis, orig):
    p = parse_price_text(text)
    assert p.preis == preis, f"aktueller Preis falsch in: {text}"
    assert p.originalpreis == orig, f"Originalpreis falsch in: {text}"


@pytest.mark.parametrize("text,preis", [
    # "3 für 2" darf nicht als Preis von 2 € durchgehen.
    ("3 für 2 Aktion: 14,99 €", 14.99),
    # Technische Daten sind keine Preise.
    ("Samsung 65 Zoll TV, 4K, 120 Hz - 799 €", 799.0),
    ("16 GB RAM Notebook ab 499 €", 499.0),
    ("Akku 5000 mAh, Laden mit 65 W - 249,00 €", 249.0),
])
def test_keine_zahl_aus_dem_fliesstext(text, preis):
    assert parse_price_text(text).preis == preis


def test_unsinniger_streichpreis_wird_verworfen():
    """Ein 'Originalpreis' unter dem Preis ist ein Parse-Unfall.
    Lieber keinen Streichpreis zeigen als einen falschen."""
    p = parse_price_text("Sonderposten 89,90 € statt 49,90 €")
    assert p.preis is not None
    assert p.originalpreis is None or p.originalpreis > p.preis
