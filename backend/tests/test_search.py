"""Volltextsuche: Uebersetzung der Eingabe und echte Treffer gegen SQLite."""
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.dedupe import normalize_title
from app.models import Base, Deal
from app.search import (
    POSTGRES,
    einrichten,
    match_bedingung,
    motor,
    motor_zuruecksetzen,
    zu_fts_query,
    zu_ts_query,
)


@pytest.mark.parametrize("eingabe,erwartet", [
    ("lego technic", "lego AND technic"),
    ('"nintendo switch"', '"nintendo switch"'),
    ("ssd -gebraucht", "ssd NOT gebraucht"),
    ("kopfhoer*", "kopfhoer*"),
    ('"the witcher 3" -defekt ssd', '"the witcher 3" AND ssd NOT defekt'),
])
def test_uebersetzung(eingabe, erwartet):
    assert zu_fts_query(eingabe) == erwartet


@pytest.mark.parametrize("eingabe", ["", "   ", "((()))", "-nur -ausschluss", '""'])
def test_unbrauchbare_eingabe_gibt_leer(eingabe):
    """Eine leere Abfrage heisst 'nicht suchen' - nicht 'alles finden'.
    Eine reine Ausschlussliste faellt auch darunter: 'alles ausser X' waere
    fuer einen Deal-Feed keine sinnvolle Suche."""
    assert zu_fts_query(eingabe) == ""


def test_ausschluss_neben_suchwort_bleibt_erhalten():
    assert zu_fts_query("-nur negativ") == "negativ NOT nur"


@pytest.mark.parametrize("eingabe", ["a OR b", "NOT", "sony AND philips", "near"])
def test_operatorwoerter_werden_entschaerft(eingabe):
    """'OR' als Suchwort darf keinen Syntaxfehler ausloesen."""
    abfrage = zu_fts_query(eingabe)
    assert abfrage
    for operator in ("OR", "AND", "NOT", "NEAR"):
        # Operatorwoerter aus der Eingabe stehen in Anfuehrungszeichen.
        if operator.lower() in eingabe.lower().split():
            assert f'"{operator}"' in abfrage or f'"{operator.lower()}"' in abfrage


# --- gegen eine echte SQLite-Datenbank -------------------------------------

BEISPIELE = [
    ("LEGO Technic 42115 Lamborghini", "Bausatz mit 3696 Teilen", "Amazon"),
    ("LEGO Duplo Starterset gebraucht", "Zustand gebraucht", "eBay"),
    ("Nintendo Switch OLED", "Konsole mit OLED-Bildschirm", "MediaMarkt"),
    ("Nintendo 3DS und Switch Lite", "zwei Konsolen", "Otto"),
    ("Samsung 990 Pro 2TB SSD", "schnelle NVMe", "Amazon"),
    ("Kingston SSD 1TB gebraucht", "guenstig gebraucht", "eBay"),
    ("Sony Kopfhoerer WH-1000XM5", "Bluetooth", "Saturn"),
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        einrichten(conn)
    session = sessionmaker(bind=engine)()
    for i, (titel, beschreibung, haendler) in enumerate(BEISPIELE):
        session.add(Deal(url_hash=f"h{i}", titel=titel, titel_norm=normalize_title(titel),
                         beschreibung=beschreibung, haendler=haendler,
                         url=f"https://x.de/{i}", quelle="mydealz", waehrung="EUR",
                         tags=[], also_from=[], roh={}))
    session.commit()
    yield session
    session.close()


def suche(db, eingabe: str) -> set[str]:
    bedingung = match_bedingung(eingabe)
    if bedingung is None:
        return set()
    return {d.titel for d in db.scalars(select(Deal).where(Deal.id.in_(bedingung)))}


def test_einzelnes_wort(db):
    assert len(suche(db, "lego")) == 2


def test_zwei_woerter_sind_und_verknuepft(db):
    treffer = suche(db, "lego technic")
    assert treffer == {"LEGO Technic 42115 Lamborghini"}


def test_phrase_beachtet_die_reihenfolge(db):
    """'nintendo switch' als Phrase darf 'Nintendo 3DS und Switch Lite'
    nicht treffen - genau das kann LIKE nicht."""
    assert suche(db, '"nintendo switch"') == {"Nintendo Switch OLED"}


def test_ausschluss(db):
    treffer = suche(db, "ssd -gebraucht")
    assert treffer == {"Samsung 990 Pro 2TB SSD"}


def test_ausschluss_greift_auch_in_der_beschreibung(db):
    assert "LEGO Duplo Starterset gebraucht" not in suche(db, "lego -gebraucht")


def test_praefix(db):
    assert suche(db, "kopfhoer*") == {"Sony Kopfhoerer WH-1000XM5"}


def test_haendler_ist_durchsuchbar(db):
    assert len(suche(db, "amazon")) == 2


def test_ohne_treffer(db):
    assert suche(db, "gibtsdefinitivnicht") == set()


def test_index_folgt_aenderungen(db):
    """Die Trigger muessen den Index synchron halten - sonst findet die Suche
    geloeschte Deals und verpasst neue."""
    neu = Deal(url_hash="neu", titel="Playmobil Ritterburg", titel_norm="playmobil",
               url="https://x.de/neu", quelle="mydealz", waehrung="EUR",
               tags=[], also_from=[], roh={})
    db.add(neu)
    db.commit()
    assert suche(db, "playmobil") == {"Playmobil Ritterburg"}

    neu.titel = "Playmobil Piratenschiff"
    db.commit()
    assert suche(db, "piratenschiff") == {"Playmobil Piratenschiff"}

    db.delete(neu)
    db.commit()
    assert suche(db, "playmobil") == set()


def test_zaehlung_stimmt_mit_der_ergebnisliste(db):
    """Die angezeigte Trefferzahl muss zur Liste passen."""
    bedingung = match_bedingung("lego")
    anzahl = db.scalar(select(func.count()).select_from(Deal).where(Deal.id.in_(bedingung)))
    assert anzahl == len(suche(db, "lego"))


# --- PostgreSQL ------------------------------------------------------------
#
# Die Postgres-Option stand im README, die Suchsyntax daneben - und genau
# dann, wenn jemand beides nutzte, fiel die Suche stillschweigend auf
# LIKE zurueck. Hier wird geprueft, dass derselbe Parser dort dieselbe
# Syntax erzeugt: `&` statt `AND`, `:*` statt `*`, `<->` statt
# Anfuehrungszeichen.


class FalscherMotor:
    """Ein Engine-Doppel, das nur seinen Dialekt kennt."""

    class dialect:
        name = "postgresql"


def test_postgres_wird_am_dialekt_erkannt():
    motor_zuruecksetzen()
    try:
        assert motor(FalscherMotor()) == POSTGRES
    finally:
        motor_zuruecksetzen()


def test_mehrere_woerter_werden_verundet():
    assert zu_ts_query("lego technic") == "lego & technic"


def test_praefix_wird_uebersetzt():
    """`websearch_to_tsquery` koennte das nicht - darum der eigene Parser."""
    assert zu_ts_query("kopfhoer*") == "kopfhoer:*"


def test_ausschluss_haengt_hinten():
    assert zu_ts_query("ssd -gebraucht") == "ssd & !gebraucht"


def test_eine_phrase_wird_zur_wortfolge():
    """In tsquery ist eine Phrase kein Anfuehrungszeichen, sondern <->."""
    assert zu_ts_query('"nintendo switch"') == "(nintendo <-> switch)"


def test_phrase_und_wort_zusammen():
    abfrage = zu_ts_query('"nintendo switch" spiel -gebraucht')
    assert abfrage == "(nintendo <-> switch) & spiel & !gebraucht"


def test_reiner_ausschluss_ergibt_keine_abfrage():
    """Sonst waere das Ergebnis „alles ausser X" - also fast alles."""
    assert zu_ts_query("-gebraucht") == ""


def test_leere_und_unsinnige_eingaben():
    assert zu_ts_query("") == ""
    assert zu_ts_query("   ") == ""
    assert zu_ts_query("!!!") == ""


def test_sonderzeichen_koennen_keine_abfrage_zerlegen():
    """Eine Nutzereingabe darf nie einen Syntaxfehler in der Datenbank
    ausloesen - dasselbe Versprechen wie bei FTS5."""
    for eingabe in ("lego & technic", "a | b", "x:*", "'; DROP TABLE deals; --"):
        abfrage = zu_ts_query(eingabe)
        # Uebrig bleiben duerfen nur unsere eigenen Operatoren.
        for zeichen in ("|", ";", "'", "("):
            if zeichen == "(":
                continue          # Phrasen stehen in Klammern
            assert zeichen not in abfrage, (eingabe, abfrage)
