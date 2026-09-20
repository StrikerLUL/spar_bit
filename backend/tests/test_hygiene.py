"""Regel-Hygiene: sagt sie Nützliches, und hält sie sich zurück?

Beide Hälften zählen. Ein Ratgeber, der jede Regel bemängelt, wird
weggeklickt - einer, der nie etwas sagt, ist überflüssig.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import hygiene
from app.models import (Base, Deal, Interaction, Match, Rule, SourceConfig,
                        utcnow)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sitzung = sessionmaker(bind=engine)()
    yield sitzung
    sitzung.close()


def regel(db, name="Lego", **kw):
    grund = dict(name=name, enabled=True, priority="NORMAL", keywords=["lego"],
                 required_keywords=[], blacklist=[], sources=[], kategorien=[],
                 haendler=[], channels=[1],
                 created_at=utcnow() - timedelta(days=90))
    row = Rule(**{**grund, **kw})
    db.add(row)
    db.commit()
    return row


def deal(db, nr, quelle="mydealz", alter_tage=1):
    row = Deal(titel=f"Deal {nr}", url=f"https://s.test/{quelle}/{nr}", quelle=quelle,
               preis=9.99, waehrung="EUR", url_hash=f"{quelle}{nr}",
               titel_norm=f"deal {nr}",
               first_seen=utcnow() - timedelta(days=alter_tage),
               last_seen=utcnow())
    db.add(row)
    db.commit()
    return row


def treffer(db, regel_row, deals, beachtet=0):
    for i, d in enumerate(deals):
        db.add(Match(rule_id=regel_row.id, deal_id=d.id,
                     created_at=utcnow() - timedelta(days=1)))
        if i < beachtet:
            db.add(Interaction(deal_id=d.id, art="geoeffnet"))
    regel_row.match_count = len(deals)
    regel_row.last_match = utcnow()
    db.commit()


# --- Rauschende Regeln -----------------------------------------------------

def test_viele_treffer_ohne_beachtung_werden_gemeldet(db):
    r = regel(db)
    treffer(db, r, [deal(db, i) for i in range(50)], beachtet=1)
    befunde = [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_laut"]
    assert len(befunde) == 1
    assert "50 Treffer" in befunde[0].text
    assert befunde[0].zahlen["beachtet"] == 1


def test_beachtete_regel_bleibt_unbehelligt(db):
    r = regel(db)
    treffer(db, r, [deal(db, i) for i in range(50)], beachtet=20)
    assert [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_laut"] == []


def test_wenige_treffer_sind_kein_rauschen(db):
    """Unter der Schwelle ist die Stichprobe zu klein für ein Urteil."""
    r = regel(db)
    treffer(db, r, [deal(db, i) for i in range(10)], beachtet=0)
    assert [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_laut"] == []


def test_nur_angesehen_zaehlt_nicht_als_beachtung(db):
    """Sonst könnte man jede Regel durch bloßes Scrollen gutrechnen."""
    r = regel(db)
    deals = [deal(db, i) for i in range(50)]
    treffer(db, r, deals)
    for d in deals:
        db.add(Interaction(deal_id=d.id, art="angesehen"))
    db.commit()
    assert len([b for b in hygiene.pruefe_regeln(db) if b.art == "regel_laut"]) == 1


# --- Leerlaufende Regeln ---------------------------------------------------

def test_regel_ohne_treffer_wird_gemeldet(db):
    regel(db, "Tippfehler-Regel", last_match=None)
    befunde = [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_leer"]
    assert len(befunde) == 1
    assert "noch nie" in befunde[0].text


def test_lange_stille_wird_gemeldet(db):
    regel(db, "Alt", last_match=utcnow() - timedelta(days=60))
    befunde = [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_leer"]
    assert len(befunde) == 1
    assert "60 Tagen" in befunde[0].text


def test_frische_regel_bekommt_zeit(db):
    """Eine gestern gebaute Regel hatte noch keine Gelegenheit."""
    regel(db, "Neu", last_match=None, created_at=utcnow() - timedelta(days=2))
    assert [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_leer"] == []


def test_ausgeschaltete_regel_wird_nicht_bemaengelt(db):
    regel(db, "Pausiert", enabled=False, last_match=None)
    assert hygiene.pruefe_regeln(db) == []


def test_kuerzlich_getroffene_regel_ist_in_ordnung(db):
    r = regel(db)
    treffer(db, r, [deal(db, 1)])
    assert [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_leer"] == []


# --- Regel ohne Kanal ------------------------------------------------------

def test_regel_ohne_kanal_wird_gemeldet(db):
    r = regel(db, "Stumm", channels=[])
    treffer(db, r, [deal(db, 1)])
    befunde = [b for b in hygiene.pruefe_regeln(db) if b.art == "regel_ohne_kanal"]
    assert len(befunde) == 1
    assert "nur im Feed" in befunde[0].text


# --- Quellen ---------------------------------------------------------------

def quelle(db, id_, aktiv=True):
    db.add(SourceConfig(id=id_, enabled=aktiv, interval_seconds=900))
    db.commit()


def test_quelle_ohne_signal_wird_gemeldet(db):
    quelle(db, "rauschen")
    for i in range(80):
        deal(db, i, quelle="rauschen")
    befunde = hygiene.pruefe_quellen(db)
    assert len(befunde) == 1
    assert befunde[0].betrifft == "rauschen"
    assert befunde[0].zahlen["funde"] == 80


def test_quelle_mit_treffern_bleibt_unbehelligt(db):
    quelle(db, "gut")
    r = regel(db)
    deals = [deal(db, i, quelle="gut") for i in range(80)]
    treffer(db, r, deals[:10])
    assert hygiene.pruefe_quellen(db) == []


def test_kleine_quelle_wird_nicht_beurteilt(db):
    """Bei zehn Funden sagt der Signalanteil nichts."""
    quelle(db, "klein")
    for i in range(10):
        deal(db, i, quelle="klein")
    assert hygiene.pruefe_quellen(db) == []


def test_ausgeschaltete_quelle_wird_nicht_beurteilt(db):
    quelle(db, "aus", aktiv=False)
    for i in range(80):
        deal(db, i, quelle="aus")
    assert hygiene.pruefe_quellen(db) == []


# --- Gesamt ----------------------------------------------------------------

def test_saubere_einrichtung_erzeugt_keine_befunde(db):
    quelle(db, "mydealz")
    r = regel(db)
    treffer(db, r, [deal(db, i) for i in range(20)], beachtet=8)
    assert hygiene.pruefe(db) == []


def test_jeder_befund_hat_einen_vorschlag(db):
    quelle(db, "rauschen")
    for i in range(80):
        deal(db, i, quelle="rauschen")
    regel(db, "Leer", last_match=None)
    laut = regel(db, "Laut")
    treffer(db, laut, [deal(db, 100 + i) for i in range(50)])

    befunde = hygiene.pruefe(db)
    assert len(befunde) >= 3
    for b in befunde:
        assert b.text and b.vorschlag, b.art
