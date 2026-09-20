"""Der stündliche Digest muss einer sein.

Vorher reichte send_digest() die aufgestauten Treffer einfach an dispatch()
weiter - also zwanzig Einzelnachrichten um sieben Uhr statt einer
Zusammenfassung.
"""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import (Base, Channel, Deal, Match, NotificationLog, Rule,
                        Setting, utcnow)
from app.notify.base import _CHANNELS, Channel as KanalBasis, Sammelmeldung
from app.notify import Notification
from app.pipeline import send_digest


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sitzung = sessionmaker(bind=engine)()
    yield sitzung
    sitzung.close()


class Sammler(KanalBasis):
    type = "sammler"
    display_name = "Sammler"
    options_schema = []

    def __init__(self):
        self.einzeln = []
        self.sammel = []

    async def send(self, config, note, http):
        self.einzeln.append(note)

    async def send_sammel(self, config, sammel, http):
        self.sammel.append(sammel)


class Schlicht(KanalBasis):
    """Kanal ohne eigene Sammel-Fassung - muss den Rückfall benutzen."""

    type = "schlicht"
    display_name = "Schlicht"
    options_schema = []

    def __init__(self):
        self.einzeln = []

    async def send(self, config, note, http):
        self.einzeln.append(note)


@pytest.fixture
def kanaele():
    sammler, schlicht = Sammler(), Schlicht()
    _CHANNELS["sammler"], _CHANNELS["schlicht"] = sammler, schlicht
    yield sammler, schlicht
    _CHANNELS.pop("sammler", None)
    _CHANNELS.pop("schlicht", None)


def kanal(db, typ="sammler", name="Handy"):
    row = Channel(type=typ, name=name, enabled=True, config={})
    db.add(row)
    db.commit()
    return row


def deal(db, titel, **kw):
    grund = dict(titel=titel, url=f"https://shop.test/{titel[:8]}", quelle="mydealz",
                 preis=99.0, waehrung="EUR", url_hash=titel,
                 titel_norm=titel.lower(), first_seen=utcnow(), last_seen=utcnow())
    row = Deal(**{**grund, **kw})
    db.add(row)
    db.commit()
    return row


def regel(db, name, kanaele_ids):
    row = Rule(name=name, enabled=True, priority="NORMAL", keywords=[],
               required_keywords=[], blacklist=[], sources=[], kategorien=[],
               haendler=[], channels=kanaele_ids)
    db.add(row)
    db.commit()
    return row


def stau(db, regel_row, *deals):
    for d in deals:
        db.add(Match(rule_id=regel_row.id, deal_id=d.id, created_at=utcnow()))
    db.commit()


# --- Zusammenfassen --------------------------------------------------------

@pytest.mark.asyncio
async def test_zwanzig_treffer_ergeben_eine_nachricht(db, kanaele):
    sammler, _ = kanaele
    k = kanal(db)
    r = regel(db, "Alles", [k.id])
    stau(db, r, *[deal(db, f"Deal {i}") for i in range(20)])

    assert await send_digest(db, http=None) == 1
    assert len(sammler.sammel) == 1
    assert sammler.sammel[0].anzahl == 20
    assert sammler.einzeln == []


@pytest.mark.asyncio
async def test_ohne_stau_passiert_nichts(db, kanaele):
    kanal(db)
    assert await send_digest(db, http=None) == 0


@pytest.mark.asyncio
async def test_treffer_gelten_danach_als_zugestellt(db, kanaele):
    k = kanal(db)
    r = regel(db, "Alles", [k.id])
    stau(db, r, deal(db, "Kaffee"), deal(db, "Tee"))

    await send_digest(db, http=None)
    assert all(m.notified_at for m in db.scalars(select(Match)))


@pytest.mark.asyncio
async def test_fehlgeschlagener_versand_haelt_die_treffer_fest(db, kanaele):
    """Sonst wären sie weg, ohne je angekommen zu sein."""
    sammler, _ = kanaele

    async def kaputt(config, sammel, http):
        raise RuntimeError("HTTP 401")

    sammler.send_sammel = kaputt
    k = kanal(db)
    r = regel(db, "Alles", [k.id])
    stau(db, r, deal(db, "Kaffee"))

    assert await send_digest(db, http=None) == 0
    assert all(m.notified_at is None for m in db.scalars(select(Match)))
    eintrag = db.scalars(select(NotificationLog)).one()
    assert eintrag.ok is False


# --- Reihenfolge -----------------------------------------------------------

def test_die_besten_funde_stehen_oben():
    def n(titel, **kw):
        return Notification(titel=titel, url="u", quelle="mydealz", **kw)

    sammel = Sammelmeldung(meldungen=[
        n("Normal", preis=50.0),
        n("Bestpreis", preis=50.0, urteil="bestpreis"),
        n("Preisfehler", preis=5.0, fehler_stufe="heiss"),
        n("Gratis", preis=0.0, ist_gratis=True),
    ])
    assert [m.titel for m in sammel.beste] == [
        "Preisfehler", "Gratis", "Bestpreis", "Normal"]


def test_kurzzeilen_kuerzen_und_sagen_es():
    def n(i):
        return Notification(titel=f"Deal {i}", url="u", quelle="q", preis=9.99)

    sammel = Sammelmeldung(meldungen=[n(i) for i in range(12)])
    zeilen = sammel.kurzzeilen(hoechstens=5)
    assert len(zeilen) == 6
    assert zeilen[-1] == "… und 7 weitere"


# --- Je Kanal --------------------------------------------------------------

@pytest.mark.asyncio
async def test_jeder_kanal_bekommt_seinen_eigenen_stand(db, kanaele):
    """Zwei Regeln mit verschiedenen Kanälen - jeder sieht nur seins."""
    sammler, schlicht = kanaele
    a = kanal(db, "sammler", "Handy")
    b = kanal(db, "schlicht", "Mail")
    r1 = regel(db, "Lego", [a.id])
    r2 = regel(db, "Kaffee", [b.id])
    stau(db, r1, deal(db, "LEGO Technic"))
    stau(db, r2, deal(db, "Kaffeekapseln"), deal(db, "Kaffeemühle"))

    assert await send_digest(db, http=None) == 2
    assert sammler.sammel[0].anzahl == 1
    # Der schlichte Kanal hat keine eigene Sammel-Fassung -> Rückfall.
    assert len(schlicht.einzeln) == 1
    assert "Kaffeekapseln" in (schlicht.einzeln[0].beschreibung or "")


@pytest.mark.asyncio
async def test_ein_einzelner_fund_bleibt_eine_normale_meldung(db, kanaele):
    """Eine „Zusammenfassung“ mit einem Eintrag wäre albern."""
    sammler, _ = kanaele
    k = kanal(db)
    r = regel(db, "Alles", [k.id])
    stau(db, r, deal(db, "Kaffee"))

    await send_digest(db, http=None)
    assert sammler.sammel[0].anzahl == 1


@pytest.mark.asyncio
async def test_derselbe_deal_kommt_je_kanal_einmal(db, kanaele):
    """Zwei Regeln, ein Deal, derselbe Kanal."""
    sammler, _ = kanaele
    k = kanal(db)
    d = deal(db, "LEGO Technic")
    r1, r2 = regel(db, "Lego", [k.id]), regel(db, "Technic", [k.id])
    stau(db, r1, d)
    stau(db, r2, d)

    await send_digest(db, http=None)
    assert sammler.sammel[0].anzahl == 1
    assert sammler.sammel[0].meldungen[0].regel == "Lego, Technic"


# --- Ruhezeit und Pause ----------------------------------------------------

@pytest.mark.asyncio
async def test_pausiert_wird_nichts_verschickt(db, kanaele):
    k = kanal(db)
    r = regel(db, "Alles", [k.id])
    stau(db, r, deal(db, "Kaffee"))
    db.add(Setting(key="notifications_paused", value=True))
    db.commit()

    assert await send_digest(db, http=None) == 0
    assert all(m.notified_at is None for m in db.scalars(select(Match)))
