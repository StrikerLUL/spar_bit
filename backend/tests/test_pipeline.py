"""Integrationstest: Quelle -> Dedupe -> DB -> Regel -> Match. Ohne Netzwerk."""
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Deal, Match, Rule
from app.pipeline import ingest, match_rules
from app.sources.base import DealItem


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def item(**kw):
    base = dict(titel="Test", url="https://example.com/a", quelle="mydealz")
    return DealItem(**{**base, **kw})


def test_neue_deals_landen_in_der_db(db):
    fresh = ingest(db, "mydealz", [
        item(titel="LEGO Technic 42115", url="https://shop.de/lego", preis=12.99),
        item(titel="Sony Kopfhoerer", url="https://shop.de/sony", preis=249.0),
    ])
    assert len(fresh) == 2
    assert db.scalar(select(Deal).where(Deal.titel == "LEGO Technic 42115")) is not None


def test_gleiche_url_wird_nicht_doppelt_gespeichert(db):
    ingest(db, "mydealz", [item(url="https://shop.de/x", titel="Ein Deal")])
    fresh = ingest(db, "mydealz", [item(url="https://shop.de/x", titel="Ein Deal")])
    assert fresh == []
    deal = db.scalar(select(Deal))
    assert deal.seen_count == 2


def test_tracking_parameter_gelten_als_gleiche_url(db):
    ingest(db, "mydealz", [item(url="https://shop.de/x?utm_source=rss", titel="Deal")])
    fresh = ingest(db, "reddit", [item(url="https://shop.de/x", titel="Deal",
                                       quelle="reddit")])
    assert fresh == []
    assert db.scalar(select(Deal)).seen_count == 2


def test_gleicher_deal_aus_vier_quellen_kommt_einmal_an(db):
    """Der Kernfall: derselbe Deal aus mehreren Communities."""
    quellen = [
        ("mydealz", "[Amazon] Sony WH-1000XM5 für 249,00€ statt 379,00€",
         "https://mydealz.de/deals/sony-1"),
        ("preisjaeger", "Sony WH-1000XM5 Kopfhoerer um 249€",
         "https://preisjaeger.at/deals/sony-2"),
        ("reddit", "Sony WH-1000XM5 - 249 EUR bei Amazon",
         "https://reddit.com/r/x/sony3"),
        ("sparhamster", "Sony WH-1000XM5 um 249,00 €",
         "https://sparhamster.at/sony-4"),
    ]
    total_fresh = 0
    for quelle, titel, url in quellen:
        total_fresh += len(ingest(db, quelle, [item(titel=titel, url=url,
                                                    quelle=quelle, preis=249.0)]))

    assert total_fresh == 1, "Deal haette nur einmal neu sein duerfen"
    assert db.scalar(select(Deal).where(Deal.duplicate_of.is_(None))) is not None
    deal = db.scalars(select(Deal)).one()
    assert set(deal.also_from) == {"preisjaeger", "reddit", "sparhamster"}
    assert deal.seen_count == 4


def test_verschiedene_deals_werden_nicht_zusammengelegt(db):
    fresh = ingest(db, "mydealz", [
        item(titel="Sony WH-1000XM5 Kopfhoerer", url="https://a.de/1"),
        item(titel="Samsung 990 Pro 2TB SSD", url="https://a.de/2"),
        item(titel="LEGO Technic 42115", url="https://a.de/3"),
    ])
    assert len(fresh) == 3


def test_guenstigerer_preis_gewinnt(db):
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD 2TB", preis=99.0)])
    ingest(db, "reddit", [item(url="https://a.de/1", titel="SSD 2TB", preis=79.0,
                               quelle="reddit")])
    assert db.scalar(select(Deal)).preis == 79.0


def test_regel_trifft_und_erzeugt_match(db):
    db.add(Rule(name="Nur Gratis", enabled=True, nur_gratis=True,
                priority="SOFORT", channels=[1]))
    db.commit()

    fresh = ingest(db, "epic", [
        item(titel="Control", url="https://epic.com/control", preis=0.0, quelle="epic"),
        item(titel="Teures Spiel", url="https://epic.com/teuer", preis=49.99,
             quelle="epic"),
    ])
    hits = match_rules(db, fresh)

    assert len(hits) == 1
    assert hits[0][1].titel == "Control"
    assert db.scalar(select(Rule)).match_count == 1
    assert db.scalar(select(Match)) is not None


def test_deaktivierte_regel_trifft_nicht(db):
    db.add(Rule(name="Aus", enabled=False, nur_gratis=True, channels=[1]))
    db.commit()
    fresh = ingest(db, "epic", [item(titel="Gratis", url="https://e.de/1", preis=0.0)])
    assert match_rules(db, fresh) == []


def test_derselbe_deal_loest_regel_nur_einmal_aus(db):
    db.add(Rule(name="Gratis", enabled=True, nur_gratis=True, channels=[1]))
    db.commit()
    fresh = ingest(db, "epic", [item(titel="Control", url="https://e.de/c", preis=0.0)])
    assert len(match_rules(db, fresh)) == 1
    assert match_rules(db, fresh) == []      # zweiter Durchlauf: kein neuer Match


def test_ungueltige_items_werden_uebersprungen(db):
    fresh = ingest(db, "mydealz", [
        item(titel="Gut", url="https://a.de/gut"),
        DealItem(titel="", url="https://a.de/leer", quelle="mydealz"),
        DealItem(titel="Ohne URL", url="", quelle="mydealz"),
    ])
    assert len(fresh) == 1
