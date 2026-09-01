"""Integrationstest: Quelle -> Dedupe -> DB -> Regel -> Match. Ohne Netzwerk."""
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Deal, DealOffer, Match, PriceHistory, Rule
from app.pipeline import check_price_alarms, ingest, match_rules
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


def angebot_quellen(db, deal_id):
    """Welche Quellen haben ein Angebot fuer diesen Deal."""
    return {a.quelle for a in db.scalars(
        select(DealOffer).where(DealOffer.deal_id == deal_id))}


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


# --- Preishistorie und Alarme ---------------------------------------------

def test_erster_preis_landet_in_der_historie(db):
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=99.0)])
    verlauf = list(db.scalars(select(PriceHistory)))
    assert len(verlauf) == 1 and verlauf[0].preis == 99.0


def test_preissenkung_wird_aufgezeichnet(db):
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=99.0)])
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=79.0)])
    preise = [p.preis for p in db.scalars(select(PriceHistory).order_by(PriceHistory.id))]
    assert preise == [99.0, 79.0]
    assert db.scalar(select(Deal)).preis == 79.0


def test_gleicher_preis_erzeugt_keinen_neuen_eintrag(db):
    for _ in range(3):
        ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=99.0)])
    assert len(list(db.scalars(select(PriceHistory)))) == 1


def test_teurerer_preis_gewinnt_nicht(db):
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=79.0)])
    ingest(db, "reddit", [item(url="https://a.de/1", titel="SSD", preis=99.0,
                               quelle="reddit")])
    assert db.scalar(select(Deal)).preis == 79.0


def test_preis_eur_wird_beim_anlegen_gesetzt(db):
    ingest(db, "cheapshark", [item(url="https://a.de/1", titel="Spiel", preis=10.0,
                                   waehrung="USD")])
    deal_row = db.scalar(select(Deal))
    assert deal_row.waehrung == "USD"
    assert deal_row.preis_eur is not None and deal_row.preis_eur < 10.0


def test_guenstiger_wird_ueber_waehrungen_hinweg_verglichen(db):
    """9 USD (~8,28 EUR) ist guenstiger als 9 EUR - der Vergleich muss in
    einer gemeinsamen Waehrung passieren, nicht auf den nackten Zahlen."""
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="Spiel", preis=9.0,
                                waehrung="EUR")])
    ingest(db, "cheapshark", [item(url="https://a.de/1", titel="Spiel", preis=9.0,
                                   waehrung="USD", quelle="cheapshark")])
    deal_row = db.scalar(select(Deal))
    assert deal_row.waehrung == "USD"


def test_preisalarm_loest_bei_unterschreitung_aus(db):
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=99.0)])
    deal_row = db.scalar(select(Deal))
    deal_row.alarm_preis = 80.0
    db.commit()

    assert check_price_alarms(db) == []          # 99 > 80, noch nichts

    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=75.0)])
    getroffen = check_price_alarms(db)
    assert len(getroffen) == 1 and getroffen[0].id == deal_row.id


def test_preisalarm_loest_nur_einmal_aus(db):
    ingest(db, "mydealz", [item(url="https://a.de/1", titel="SSD", preis=50.0)])
    deal_row = db.scalar(select(Deal))
    deal_row.alarm_preis = 80.0
    db.commit()

    assert len(check_price_alarms(db)) == 1
    assert check_price_alarms(db) == []          # kein Dauerfeuer


# --- Preisvergleich ueber Quellen -----------------------------------------

def angebote(db, deal_id):
    return {a.quelle: a for a in db.scalars(
        select(DealOffer).where(DealOffer.deal_id == deal_id))}


def test_jede_quelle_bekommt_ein_eigenes_angebot(db):
    """Der Deal haelt den besten Preis - fuer den Vergleich braucht es
    zusaetzlich, was jede Quelle verlangt."""
    ingest(db, "mydealz", [item(titel="Sony WH-1000XM5 Kopfhoerer",
                                url="https://mydealz.de/x", preis=279.0)])
    ingest(db, "preisjaeger", [item(titel="Sony WH-1000XM5 Kopfhoerer",
                                    url="https://preisjaeger.at/y", preis=249.0,
                                    quelle="preisjaeger")])
    deal_row = db.scalars(select(Deal)).one()
    alle = angebote(db, deal_row.id)

    assert set(alle) == {"mydealz", "preisjaeger"}
    assert alle["mydealz"].preis == 279.0
    assert alle["preisjaeger"].preis == 249.0
    assert deal_row.preis == 249.0          # der Deal zeigt den besten


def test_angebotsliste_passt_zur_angezeigten_anzahl(db):
    """Die Karte zeigt 1 + len(also_from) Angebote - genauso viele muessen
    in der Detailansicht stehen."""
    for quelle, url in [("mydealz", "https://a.de/1"), ("reddit", "https://b.de/2"),
                        ("preisjaeger", "https://c.de/3")]:
        ingest(db, quelle, [item(titel="Sony WH-1000XM5 Kopfhoerer", url=url,
                                 preis=249.0, quelle=quelle)])
    deal_row = db.scalars(select(Deal)).one()
    angezeigt = 1 + len(deal_row.also_from or [])
    assert angezeigt == len(angebot_quellen(db, deal_row.id)) == 3
    assert angebot_quellen(db, deal_row.id) == {deal_row.quelle, *deal_row.also_from}


def test_angebote_behalten_ihre_eigene_url(db):
    """Sonst landet man beim Klick auf 'guenstigster' beim falschen Shop."""
    ingest(db, "mydealz", [item(titel="SSD 2TB", url="https://mydealz.de/a",
                                preis=99.0)])
    ingest(db, "reddit", [item(titel="SSD 2TB", url="https://reddit.com/b",
                               preis=79.0, quelle="reddit")])
    alle = angebote(db, db.scalars(select(Deal)).one().id)
    assert alle["mydealz"].url == "https://mydealz.de/a"
    assert alle["reddit"].url == "https://reddit.com/b"


def test_erneuter_lauf_aktualisiert_statt_zu_verdoppeln(db):
    for preis in (99.0, 89.0, 89.0):
        ingest(db, "mydealz", [item(titel="SSD", url="https://a.de/1", preis=preis)])
    alle = angebote(db, db.scalars(select(Deal)).one().id)
    assert len(alle) == 1
    assert alle["mydealz"].preis == 89.0


def test_angebot_kennt_seinen_eur_preis(db):
    """Nur so laesst sich USD gegen EUR vergleichen."""
    ingest(db, "cheapshark", [item(titel="Spiel", url="https://cs.de/1",
                                   preis=10.0, waehrung="USD",
                                   quelle="cheapshark")])
    angebot = angebote(db, db.scalars(select(Deal)).one().id)["cheapshark"]
    assert angebot.waehrung == "USD"
    assert angebot.preis_eur is not None and angebot.preis_eur < 10.0


def test_guenstigstes_angebot_ueber_waehrungen(db):
    """9 USD (~8,28 EUR) schlaegt 9 EUR - der Vergleich muss umrechnen."""
    ingest(db, "mydealz", [item(titel="Spiel X", url="https://a.de/1", preis=9.0)])
    ingest(db, "cheapshark", [item(titel="Spiel X", url="https://b.de/2", preis=9.0,
                                   waehrung="USD", quelle="cheapshark")])
    alle = angebote(db, db.scalars(select(Deal)).one().id)
    guenstigstes = min(alle.values(), key=lambda a: a.preis_eur)
    assert guenstigstes.quelle == "cheapshark"
