"""Produktkennung: wann zwei Angebote wirklich derselbe Artikel sind."""
import pytest

from app.produktid import aus_strukturierten_daten, aus_url, fuer_deal


@pytest.mark.parametrize("url,erwartet", [
    ("https://www.amazon.de/dp/B07H8MJ2BF", "asin:B07H8MJ2BF"),
    ("https://www.amazon.de/Sony-Kopfhoerer/dp/B07H8MJ2BF/ref=sr_1_3?keywords=x",
     "asin:B07H8MJ2BF"),
    ("https://www.amazon.de/gp/product/B08N5WRWNW?psc=1", "asin:B08N5WRWNW"),
    ("https://store.steampowered.com/app/1091500/Cyberpunk_2077/", "steam:1091500"),
    ("https://www.gog.com/de/game/cyberpunk_2077", "gog:cyberpunk_2077"),
    ("https://store.epicgames.com/de/p/alan-wake-2", "epic:alan-wake-2"),
    ("https://www.mediamarkt.de/de/product/_sony-wh-1000xm5-2845321.html",
     "mms:2845321"),
])
def test_kennung_aus_der_adresse(url, erwartet):
    assert aus_url(url) == erwartet


@pytest.mark.parametrize("url", [
    "https://www.mydealz.de/deals/irgendein-deal-2345678",
    "https://www.reddit.com/r/GameDeals/comments/abc/titel/",
    "",
])
def test_ohne_kennung_bleibt_es_beim_titel(url):
    assert aus_url(url) is None


def test_gtin_wird_auf_dreizehn_stellen_gebracht():
    """Dieselbe Ware traegt je nach Shop 12, 13 oder 14 Stellen."""
    kurz = aus_strukturierten_daten({"gtin12": "012345678905"})
    lang = aus_strukturierten_daten({"gtin14": "00012345678905"})
    assert kurz == lang
    assert kurz.startswith("gtin:")


def test_sku_zaehlt_nicht_als_identitaet():
    """Eine Artikelnummer ist nur innerhalb eines Shops eindeutig."""
    assert aus_strukturierten_daten({"sku": "A-123", "mpn": "XYZ"}) is None


def test_strukturierte_daten_schlagen_die_adresse():
    kennung = fuer_deal("https://www.amazon.de/dp/B07H8MJ2BF",
                        {"gtin13": "4260000000001"})
    assert kennung == "gtin:4260000000001"


# --- Wirkung auf das Zusammenfuehren -------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    lade_app_neu()
    from app.db import SessionLocal, init_db
    init_db()
    return SessionLocal


def item(titel, url, preis=None):
    from app.sources.base import DealItem
    return DealItem(titel=titel, url=url, quelle="test", preis=preis)


def test_gleiche_asin_verschiedene_titel_ist_ein_artikel(db):
    """Der Fall, an dem jeder Schwellenwert scheitert."""
    from app.pipeline import ingest

    with db() as sitzung:
        ingest(sitzung, "mydealz", [
            item("Sony WH-1000XM5 Schwarz", "https://www.amazon.de/dp/B09XS7JWHH", 279.0)])
        neu = ingest(sitzung, "preisjaeger", [
            item("Sony Kopfhoerer WH1000XM5, schwarz, Bluetooth",
                 "https://www.amazon.de/gp/product/B09XS7JWHH?tag=xyz", 269.0)])

        assert neu == [], "zweite Meldung ist kein neuer Deal"
        # ingest committet nur, wenn etwas Neues dabei war - im Betrieb
        # schliesst der Scheduler die Sitzung ab (session_scope).
        sitzung.commit()

        from sqlalchemy import select

        from app.models import Deal, DealOffer
        deals = list(sitzung.scalars(select(Deal)))
        assert len(deals) == 1
        # Und der Preisvergleich hat jetzt zwei Zeilen - genau das, was dem
        # Preisfehler-Waechter bisher fehlte.
        angebote = list(sitzung.scalars(select(DealOffer).where(
            DealOffer.deal_id == deals[0].id)))
        assert {a.quelle for a in angebote} == {"mydealz", "preisjaeger"}


def test_verschiedene_kennung_trennt_aehnliche_titel(db):
    """"iPhone 15 128 GB" und "iPhone 15 256 GB" heissen fast gleich."""
    from sqlalchemy import select

    from app.models import Deal
    from app.pipeline import ingest

    with db() as sitzung:
        ingest(sitzung, "mydealz", [
            item("Apple iPhone 15 128 GB", "https://www.amazon.de/dp/B0CHX1W1XY", 699.0)])
        ingest(sitzung, "mydealz", [
            item("Apple iPhone 15 128 GB", "https://www.amazon.de/dp/B0CHX2A9BB", 749.0)])
        assert len(list(sitzung.scalars(select(Deal)))) == 2


def test_kennung_findet_auch_ausserhalb_des_zeitfensters(db):
    """Die Kandidatenliste reicht 72 Stunden zurueck - eine Kennung weiter."""
    from datetime import timedelta

    from sqlalchemy import select

    from app.models import Deal, utcnow
    from app.pipeline import ingest

    with db() as sitzung:
        ingest(sitzung, "steam", [
            item("Cyberpunk 2077", "https://store.steampowered.com/app/1091500/", 29.99)])
        alt = sitzung.scalar(select(Deal))
        alt.first_seen = utcnow() - timedelta(days=30)
        sitzung.commit()

        neu = ingest(sitzung, "reddit", [
            item("Cyberpunk 2077 im Angebot",
                 "https://store.steampowered.com/app/1091500/Cyberpunk_2077/", 24.99)])
        assert neu == []
        assert len(list(sitzung.scalars(select(Deal)))) == 1
