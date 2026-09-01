"""Volltextsuche: Uebersetzung der Eingabe und echte Treffer gegen SQLite."""
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.dedupe import normalize_title
from app.models import Base, Deal
from app.search import einrichten, match_bedingung, zu_fts_query


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
