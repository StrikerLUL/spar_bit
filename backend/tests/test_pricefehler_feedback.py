"""Rückmeldung zum Preisfehler: wird daraus etwas Brauchbares?

Die Gewichte des Wächters sind am Schreibtisch gewählt. Erst wenn der
Benutzer sagt "war echt" oder "war Quatsch", lässt sich etwas belegen -
und auch dann nur vorsichtig.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Deal, Setting, utcnow
from app.pricefehler import (ECHT, FEHLALARM, MIN_RUECKMELDUNGEN,
                             SCHWELLE_HEISS, bewerte, bewerte_rueckmeldungen,
                             notiere_rueckmeldung)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sitzung = sessionmaker(bind=engine)()
    yield sitzung
    sitzung.close()


def fund(db, punkte, indizien, urteil=None, titel=None):
    d = Deal(titel=titel or f"Fund {punkte}", url=f"https://s.test/{punkte}-{len(indizien)}",
             quelle="mydealz", preis=9.99, waehrung="EUR",
             url_hash=f"{punkte}-{indizien}-{titel}", titel_norm="x",
             first_seen=utcnow(), last_seen=utcnow(),
             fehler_score=punkte, fehler_stufe="heiss",
             fehler_indizien=indizien, fehler_urteil_mensch=urteil)
    db.add(d)
    db.commit()
    return d


# --- Indizien mitschreiben -------------------------------------------------

def test_bewerten_merkt_sich_stabile_schluessel():
    urteil = bewerte("Fernseher Preisfehler", 89.0, originalpreis_eur=899.0,
                     rabatt_prozent=90.0, verlauf_eur=[899, 879, 890, 885])
    assert "ausgewiesen" in urteil.indizien
    assert "kommastelle" in urteil.indizien
    # Die Gruende sind freier Text und taugen nicht zum Auswerten.
    assert urteil.gruende and urteil.gruende != urteil.indizien


def test_ohne_punkte_keine_indizien():
    urteil = bewerte("Normaler Kaffee", 9.99)
    assert urteil.indizien == []


# --- Rueckmeldung speichern ------------------------------------------------

def test_rueckmeldung_wird_vermerkt(db):
    d = fund(db, 80, ["kommastelle"])
    notiere_rueckmeldung(db, d.id, ECHT)
    assert d.fehler_urteil_mensch == ECHT
    assert d.fehler_urteil_am is not None


def test_nochmal_druecken_nimmt_zurueck(db):
    d = fund(db, 80, ["kommastelle"])
    notiere_rueckmeldung(db, d.id, ECHT)
    notiere_rueckmeldung(db, d.id, ECHT)
    assert d.fehler_urteil_mensch is None


def test_umentscheiden_geht(db):
    d = fund(db, 80, ["kommastelle"])
    notiere_rueckmeldung(db, d.id, ECHT)
    notiere_rueckmeldung(db, d.id, FEHLALARM)
    assert d.fehler_urteil_mensch == FEHLALARM


def test_unbekanntes_urteil_wird_abgelehnt(db):
    d = fund(db, 80, ["kommastelle"])
    with pytest.raises(ValueError):
        notiere_rueckmeldung(db, d.id, "vielleicht")


def test_fehlender_deal_gibt_none(db):
    assert notiere_rueckmeldung(db, 9999, ECHT) is None


# --- Auswertung ------------------------------------------------------------

def test_ohne_rueckmeldungen_wird_nichts_behauptet(db):
    fund(db, 80, ["kommastelle"])
    raus = bewerte_rueckmeldungen(db)
    assert raus["beurteilt"] == 0
    assert raus["indizien"] == []
    assert raus["vorschlag"] is None


def test_treffsicherheit_je_indiz(db):
    for i in range(3):
        fund(db, 90, ["kommastelle"], ECHT, titel=f"echt {i}")
    fund(db, 60, ["hohe_resonanz"], ECHT, titel="echt resonanz")
    for i in range(3):
        fund(db, 60, ["hohe_resonanz"], FEHLALARM, titel=f"falsch {i}")

    raus = bewerte_rueckmeldungen(db)
    nach_schluessel = {i["schluessel"]: i for i in raus["indizien"]}
    assert nach_schluessel["kommastelle"]["treffsicherheit"] == 100
    assert nach_schluessel["hohe_resonanz"]["treffsicherheit"] == 25
    # Das beste Indiz steht oben.
    assert raus["indizien"][0]["schluessel"] == "kommastelle"


def test_indiz_ohne_rueckmeldung_taucht_nicht_auf(db):
    fund(db, 90, ["kommastelle"], ECHT)
    raus = bewerte_rueckmeldungen(db)
    assert [i["schluessel"] for i in raus["indizien"]] == ["kommastelle"]


# --- Schwellenvorschlag ----------------------------------------------------

def test_bei_wenigen_rueckmeldungen_kein_vorschlag(db):
    for i in range(MIN_RUECKMELDUNGEN - 1):
        fund(db, 90, ["kommastelle"], ECHT, titel=f"e{i}")
    raus = bewerte_rueckmeldungen(db)
    assert raus["vorschlag"] is None
    assert str(MIN_RUECKMELDUNGEN) in raus["vorschlag_grund"]


def test_schwelle_ueber_dem_hoechsten_fehlalarm(db):
    for i in range(8):
        fund(db, 90, ["kommastelle"], ECHT, titel=f"e{i}")
    fund(db, 72, ["hohe_resonanz"], FEHLALARM, titel="f1")
    fund(db, 78, ["hohe_resonanz"], FEHLALARM, titel="f2")

    raus = bewerte_rueckmeldungen(db)
    assert raus["vorschlag"] == 79
    assert "78" in raus["vorschlag_grund"]


def test_ohne_fehlalarme_darf_die_schwelle_sinken(db):
    """Schwelle 90, echte Funde ab 85 - so rutscht Richtiges durch."""
    db.add(Setting(key="preisfehler_schwelle", value=90))
    db.commit()
    for i in range(12):
        fund(db, 85, ["kommastelle"], ECHT, titel=f"e{i}")
    raus = bewerte_rueckmeldungen(db)
    assert raus["vorschlag"] == 85
    assert "Fehlalarm" in raus["vorschlag_grund"]


def test_passende_schwelle_bleibt_auch_ohne_fehlalarme(db):
    """Fängt die Schwelle schon alles, gibt es nichts zu ändern."""
    for i in range(12):
        fund(db, 85, ["kommastelle"], ECHT, titel=f"e{i}")
    assert bewerte_rueckmeldungen(db)["vorschlag"] is None


def test_die_schwelle_faellt_nie_unter_den_verdacht(db):
    """Sonst würde jeder halbwegs auffällige Preis gemeldet."""
    from app.pricefehler import SCHWELLE_VERDACHT
    db.add(Setting(key="preisfehler_schwelle", value=90))
    db.commit()
    for i in range(12):
        fund(db, 10, ["hohe_resonanz"], ECHT, titel=f"e{i}")
    assert bewerte_rueckmeldungen(db)["vorschlag"] == SCHWELLE_VERDACHT


def test_passende_schwelle_wird_nicht_veraendert(db):
    db.add(Setting(key="preisfehler_schwelle", value=80))
    db.commit()
    for i in range(10):
        fund(db, 95, ["kommastelle"], ECHT, titel=f"e{i}")
    fund(db, 79, ["hohe_resonanz"], FEHLALARM, titel="f1")

    raus = bewerte_rueckmeldungen(db)
    assert raus["vorschlag"] is None
    assert raus["aktuelle_schwelle"] == 80


def test_der_vorschlag_verstellt_nichts_von_selbst(db):
    db.add(Setting(key="preisfehler_schwelle", value=70))
    db.commit()
    for i in range(10):
        fund(db, 95, ["kommastelle"], ECHT, titel=f"e{i}")
    fund(db, 85, ["hohe_resonanz"], FEHLALARM, titel="f1")

    bewerte_rueckmeldungen(db)
    from app.db import get_setting
    assert get_setting(db, "preisfehler_schwelle") == 70
