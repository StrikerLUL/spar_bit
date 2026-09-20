"""Ein Deal ist eine Nachricht - auch wenn drei Regeln ihn treffen.

Vorher ging je (Regel, Deal)-Paar eine Meldung raus. Wer eine Regel für
"Lego" und eine für "Preisfehler" hatte, bekam denselben Fund zweimal aufs
Handy.
"""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Channel, Deal, Match, NotificationLog, Rule, utcnow
from app.notify.base import _CHANNELS, Channel as KanalBasis
from app.pipeline import buendele, dispatch


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sitzung = sessionmaker(bind=engine)()
    yield sitzung
    sitzung.close()


class Sammler(KanalBasis):
    """Kanal, der nur mitschreibt, was er zugestellt bekommen hat."""

    type = "sammler"
    display_name = "Sammler"
    options_schema = []

    def __init__(self):
        self.gesendet = []

    async def send(self, config, note, http):
        self.gesendet.append(note)


@pytest.fixture
def sammler():
    kanal = Sammler()
    vorher = _CHANNELS.get("sammler")
    _CHANNELS["sammler"] = kanal
    yield kanal
    if vorher is None:
        _CHANNELS.pop("sammler", None)
    else:
        _CHANNELS["sammler"] = vorher


def kanal(db, name="Handy"):
    row = Channel(type="sammler", name=name, enabled=True, config={})
    db.add(row)
    db.commit()
    return row


def deal(db, titel="LEGO Technic Ferrari"):
    row = Deal(titel=titel, url=f"https://shop.test/{titel[:5]}", quelle="mydealz",
               preis=279.0, waehrung="EUR", url_hash=titel, titel_norm=titel.lower(),
               first_seen=utcnow(), last_seen=utcnow())
    db.add(row)
    db.commit()
    return row


def regel(db, name, kanaele, prioritaet="NORMAL"):
    row = Rule(name=name, enabled=True, priority=prioritaet, keywords=[],
               required_keywords=[], blacklist=[], sources=[], kategorien=[],
               haendler=[], channels=kanaele)
    db.add(row)
    db.commit()
    return row


# --- Bündeln ---------------------------------------------------------------

def test_buendeln_fasst_denselben_deal_zusammen(db):
    d = deal(db)
    r1, r2 = regel(db, "Lego", []), regel(db, "Preisfehler", [])
    gebuendelt = buendele([(r1, d), (r2, d)])
    assert len(gebuendelt) == 1
    assert [r.name for r in gebuendelt[0][1]] == ["Lego", "Preisfehler"]


def test_buendeln_haelt_verschiedene_deals_auseinander(db):
    a, b = deal(db, "LEGO Ferrari"), deal(db, "PS5 Slim")
    r = regel(db, "Alles", [])
    assert len(buendele([(r, a), (r, b)])) == 2


def test_buendeln_behaelt_die_reihenfolge(db):
    a, b = deal(db, "Zuerst"), deal(db, "Danach")
    r = regel(db, "Alles", [])
    assert [d.titel for d, _ in buendele([(r, a), (r, b)])] == ["Zuerst", "Danach"]


def test_dieselbe_regel_zweimal_zaehlt_einmal(db):
    d = deal(db)
    r = regel(db, "Lego", [])
    assert len(buendele([(r, d), (r, d)])[0][1]) == 1


# --- Zustellung ------------------------------------------------------------

@pytest.mark.asyncio
async def test_drei_regeln_ein_deal_eine_nachricht(db, sammler):
    k = kanal(db)
    d = deal(db)
    regeln = [regel(db, n, [k.id]) for n in ("Lego", "Technic", "Unter 300")]
    for r in regeln:
        db.add(Match(rule_id=r.id, deal_id=d.id))
    db.commit()

    gesendet = await dispatch(db, [(r, d) for r in regeln], http=None)

    assert gesendet == 1
    assert len(sammler.gesendet) == 1
    assert sammler.gesendet[0].regel == "Lego, Technic, Unter 300"


@pytest.mark.asyncio
async def test_viele_regeln_werden_gekuerzt(db, sammler):
    k = kanal(db)
    d = deal(db)
    regeln = [regel(db, f"R{i}", [k.id]) for i in range(5)]
    await dispatch(db, [(r, d) for r in regeln], http=None)
    assert sammler.gesendet[0].regel == "R0, R1, R2 +2"


@pytest.mark.asyncio
async def test_sofort_gewinnt_gegen_normal(db, sammler):
    """Trifft eine dringende Regel mit, ist der Fund dringend."""
    k = kanal(db)
    d = deal(db)
    ruhig = regel(db, "Lego", [k.id])
    dringend = regel(db, "Preisfehler", [k.id], prioritaet="SOFORT")

    await dispatch(db, [(ruhig, d), (dringend, d)], http=None)
    assert sammler.gesendet[0].prioritaet == "SOFORT"


@pytest.mark.asyncio
async def test_kanaele_werden_vereinigt(db, sammler):
    a, b = kanal(db, "Handy"), kanal(db, "Discord")
    d = deal(db)
    r1 = regel(db, "Lego", [a.id])
    r2 = regel(db, "Technic", [b.id])

    gesendet = await dispatch(db, [(r1, d), (r2, d)], http=None)
    assert gesendet == 2                       # zwei Kanäle
    assert len(sammler.gesendet) == 2          # aber dieselbe Meldung


@pytest.mark.asyncio
async def test_derselbe_kanal_bekommt_nichts_doppelt(db, sammler):
    """Beide Regeln zeigen auf denselben Kanal - eine Zustellung."""
    k = kanal(db)
    d = deal(db)
    r1, r2 = regel(db, "Lego", [k.id]), regel(db, "Technic", [k.id])
    assert await dispatch(db, [(r1, d), (r2, d)], http=None) == 1


@pytest.mark.asyncio
async def test_alle_beteiligten_treffer_gelten_als_zugestellt(db, sammler):
    """Sonst taucht der Deal im nächsten Digest wieder auf."""
    k = kanal(db)
    d = deal(db)
    r1, r2 = regel(db, "Lego", [k.id]), regel(db, "Technic", [k.id])
    db.add_all([Match(rule_id=r1.id, deal_id=d.id),
                Match(rule_id=r2.id, deal_id=d.id)])
    db.commit()

    await dispatch(db, [(r1, d), (r2, d)], http=None)

    offen = [m for m in db.scalars(select(Match)) if m.notified_at is None]
    assert offen == []


@pytest.mark.asyncio
async def test_protokoll_bekommt_alle_regelnamen(db, sammler):
    k = kanal(db)
    d = deal(db)
    r1, r2 = regel(db, "Lego", [k.id]), regel(db, "Technic", [k.id])
    await dispatch(db, [(r1, d), (r2, d)], http=None)

    eintrag = db.scalars(select(NotificationLog)).one()
    assert eintrag.rule_name == "Lego, Technic"
    assert eintrag.ok is True


@pytest.mark.asyncio
async def test_regel_ohne_kanal_blockiert_die_anderen_nicht(db, sammler):
    k = kanal(db)
    d = deal(db)
    ohne = regel(db, "Vergessen", [])
    mit = regel(db, "Lego", [k.id])
    assert await dispatch(db, [(ohne, d), (mit, d)], http=None) == 1
