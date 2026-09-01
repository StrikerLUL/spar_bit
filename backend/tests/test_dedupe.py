import pytest

from app.dedupe import canonical_url, normalize_title, titles_match, url_hash


def test_tracking_parameter_werden_entfernt():
    a = "https://www.amazon.de/dp/B08XYZ?utm_source=rss&tag=partner-21&th=1"
    b = "https://amazon.de/dp/B08XYZ/"
    assert canonical_url(a) == canonical_url(b)
    assert url_hash(a) == url_hash(b)


def test_echte_parameter_bleiben():
    a = canonical_url("https://shop.de/p?id=1")
    b = canonical_url("https://shop.de/p?id=2")
    assert a != b


def test_query_reihenfolge_egal():
    assert (canonical_url("https://s.de/p?b=2&a=1")
            == canonical_url("https://s.de/p?a=1&b=2"))


def test_titel_normalisierung():
    norm = normalize_title("[Amazon] Sony WH-1000XM5 für 249,00€ statt 379,00€ (349°)")
    assert "sony" in norm and "wh" in norm
    assert "249" not in norm and "amazon" not in norm


def test_gleicher_deal_aus_zwei_quellen():
    a = "[Amazon] Sony WH-1000XM5 Kopfhörer für 249,00€ statt 379,00€"
    b = "Sony WH-1000XM5 Kopfhörer - 249€ (Bestpreis) bei Amazon"
    assert titles_match(a, b)


def test_verschiedene_deals_nicht_gleich():
    assert not titles_match("Sony WH-1000XM5 Kopfhörer",
                            "Samsung 990 Pro 2TB SSD")


def test_kurze_titel_sind_streng():
    """Kurze Titel duerfen nicht vorschnell als Duplikat gelten."""
    assert not titles_match("Hades", "Hades II")


def test_produktvarianten_bleiben_getrennt():
    """Ausgaben, Nummern und Modellvarianten sind verschiedene Artikel."""
    assert not titles_match("iPhone 15 Pro 256GB", "iPhone 15 256GB")
    assert not titles_match("Samsung 990 Pro 2TB SSD", "Samsung 990 Evo 2TB SSD")
    assert not titles_match("The Witcher 3 GOTY", "The Witcher 3")


def test_zusatzwoerter_stoeren_nicht():
    assert titles_match("Portal 2 gratis auf Steam", "[Steam] Portal 2 (Free to keep)")
    assert titles_match("LEGO Technic 42115 Lamborghini",
                        "LEGO Technic 42115 Lamborghini Sian")


def test_lange_titel_mit_anderer_nummer_bleiben_getrennt():
    """Bei langen, sonst gleichen Titeln lag der Aehnlichkeitswert frueher
    ueber der Schwelle - zwei verschiedene Artikel fielen zusammen."""
    assert not titles_match("Kaffeekapseln Vorratspack 12",
                            "Kaffeekapseln Vorratspack 13")
    assert not titles_match("LEGO Technic Bausatz 1", "LEGO Technic Bausatz 2")


@pytest.mark.parametrize("a,b", [
    ("iPhone 15", "iPhone 16"),
    ("iPhone 15 Pro 256GB", "iPhone 16 Pro 256GB"),
    ("Samsung Galaxy S24", "Samsung Galaxy S25"),
    ("PlayStation 5 Slim", "PlayStation 4 Slim"),
    ("Die Siedler 7", "Die Siedler 8"),
])
def test_nachfolger_sind_nicht_derselbe_artikel(a, b):
    assert not titles_match(a, b)


def test_schreibweise_der_gleichen_zahl_stoert_nicht():
    """'2TB' und '2 TB' sind derselbe Artikel - die Zahl zaehlt, nicht wie
    sie im Text klebt."""
    assert titles_match("Samsung SSD 2TB", "Samsung SSD 2 TB")


def test_beide_nennen_etwas_eigenes_heisst_verschieden():
    """token_set_ratio wertet Teilmengen als Volltreffer - bei langem
    gemeinsamem Text fielen dadurch verschiedene Artikel zusammen."""
    assert not titles_match("Kaffeekapseln Lungo Vorratspack",
                            "Kaffeekapseln Espresso Vorratspack")
    assert not titles_match("LEGO Technic Bausatz", "LEGO City Bausatz")


def test_einseitiger_zusatz_ist_nur_beiwerk():
    """Nur eine Seite nennt etwas zusaetzlich - das ist Herkunft, kein
    anderer Artikel."""
    assert titles_match("Portal 2 gratis auf Steam", "[Steam] Portal 2")
    assert titles_match("Sony WH-1000XM5 Kopfhörer",
                        "Sony WH-1000XM5 Kopfhörer bei Amazon")
