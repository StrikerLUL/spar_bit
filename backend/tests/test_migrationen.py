"""Was die alte Spaltenliste nicht konnte - und der Ersatz koennen muss."""
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from app import migrations


@pytest.fixture
def db(tmp_path):
    pfad = tmp_path / "alt.db"
    engine = create_engine(f"sqlite:///{pfad}")
    yield engine
    engine.dispose()


def alte_datenbank(pfad):
    """Eine Datenbank, wie sie vor den Migrationen ausgesehen hat."""
    conn = sqlite3.connect(pfad)
    conn.executescript("""
        CREATE TABLE deals (
            id INTEGER PRIMARY KEY,
            url_hash VARCHAR(32),
            titel TEXT,
            titel_norm TEXT,
            url TEXT,
            preis FLOAT,
            ist_gratis BOOLEAN DEFAULT 0,
            first_seen DATETIME
        );
        CREATE TABLE rules (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE source_configs (id VARCHAR(64) PRIMARY KEY);
        INSERT INTO deals (url_hash, titel, titel_norm, url, preis)
        VALUES ('abc', 'Alter Deal', 'alter deal', 'https://x/1', 9.99);
    """)
    conn.commit()
    conn.close()


def test_frische_datenbank_wird_nur_gestempelt(db):
    """Nichts auszufuehren - create_all hat den Stand schon gebaut."""
    with db.connect() as conn:
        assert migrations.datenbank_ist_leer(conn)

    migrations.stempeln(db)
    assert migrations.version(db) == migrations.neuester_stand()
    # Ein zweiter Lauf findet nichts mehr zu tun.
    assert migrations.migriere(db) == []


def test_alte_datenbank_bekommt_ihre_spalten(tmp_path):
    pfad = tmp_path / "alt.db"
    alte_datenbank(pfad)
    engine = create_engine(f"sqlite:///{pfad}")

    with engine.connect() as conn:
        assert not migrations.datenbank_ist_leer(conn)
        assert not migrations.spalte_existiert(conn, "deals", "preis_eur")

    gelaufen = migrations.migriere(engine)
    assert 1 in gelaufen

    with engine.connect() as conn:
        for spalte in ("preis_eur", "urteil", "fehler_score", "erwachsen"):
            assert migrations.spalte_existiert(conn, "deals", spalte), spalte
        # Bestehende Daten bleiben unangetastet.
        assert conn.execute(text("SELECT titel FROM deals")).scalar() == "Alter Deal"
    engine.dispose()


def test_zweiter_lauf_macht_nichts_mehr(tmp_path):
    pfad = tmp_path / "alt.db"
    alte_datenbank(pfad)
    engine = create_engine(f"sqlite:///{pfad}")
    erste = migrations.migriere(engine)
    zweite = migrations.migriere(engine)
    assert erste and zweite == []
    assert migrations.version(engine) == migrations.neuester_stand()
    engine.dispose()


def test_fehlende_indizes_werden_nachgezogen(tmp_path):
    """Der Fall, den die alte Liste gar nicht kannte.

    create_all ueberspringt bestehende Tabellen samt ihrer Indizes. Ein
    Index, der nach der ersten Version dazukam, fehlte darum genau dort,
    wo die meisten Daten liegen.
    """
    pfad = tmp_path / "alt.db"
    alte_datenbank(pfad)
    engine = create_engine(f"sqlite:///{pfad}")

    from app.models import Base

    with engine.connect() as conn:
        vorher = {i["name"] for i in inspect(conn).get_indexes("deals")}
    assert "ix_deals_gratis_seen" not in vorher

    migrations.migriere(engine)

    with engine.connect() as conn:
        nachher = {i["name"] for i in inspect(conn).get_indexes("deals")}
    assert "ix_deals_gratis_seen" in nachher
    assert "ix_deals_first_seen_desc" in nachher
    # Und die Spalten-Indizes der nachgeruesteten Spalten ebenso.
    assert "ix_deals_preis_eur" in nachher
    assert Base is not None
    engine.dispose()


def test_ein_abbrechender_schritt_laesst_den_rest_stehen(tmp_path, monkeypatch):
    pfad = tmp_path / "alt.db"
    alte_datenbank(pfad)
    engine = create_engine(f"sqlite:///{pfad}")

    def kaputt(conn):
        raise RuntimeError("geht nicht")

    original = list(migrations.SCHRITTE)
    monkeypatch.setattr(migrations, "SCHRITTE", [
        original[0],
        migrations.Schritt(99, "kaputter Schritt", kaputt),
    ])

    with pytest.raises(RuntimeError):
        migrations.migriere(engine)

    # Schritt 1 ist gelaufen UND vermerkt, der kaputte nicht.
    with engine.connect() as conn:
        assert migrations.spalte_existiert(conn, "deals", "preis_eur")
        assert migrations.angewendete(conn) == {1}
    engine.dispose()


def test_neue_schritte_haben_eindeutige_aufsteigende_nummern():
    nummern = [s.nummer for s in migrations.SCHRITTE]
    assert nummern == sorted(nummern), "Schritte muessen in Reihenfolge stehen"
    assert len(nummern) == len(set(nummern)), "Nummern werden nie wiederverwendet"
