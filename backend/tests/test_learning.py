"""Lernender Feed. Alles lokal, kein Netzwerk, kein externer Dienst."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.learning import MIN_POSITIV, Modell, merkmale, notiere, trainiere, vorschlaege
from app.models import Base, Deal, Interaction


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def deal(db, titel, preis=None, haendler=None, quelle="mydealz", gratis=False,
         rabatt=None):
    zeile = Deal(url_hash=f"h{titel}{preis}", titel=titel, titel_norm=titel.lower(),
                 url=f"https://x.de/{abs(hash(titel)) % 10000}", quelle=quelle,
                 waehrung="EUR", preis=preis, preis_eur=preis, haendler=haendler,
                 ist_gratis=gratis, rabatt_prozent=rabatt,
                 tags=[], also_from=[], roh={})
    db.add(zeile)
    db.commit()
    return zeile


# --- Merkmale --------------------------------------------------------------

def test_merkmale_trennen_die_raeume():
    """'amazon' als Haendler ist etwas anderes als 'amazon' im Titel."""
    d = Deal(titel="Amazon Echo Dot", haendler="MediaMarkt", quelle="mydealz",
             preis_eur=29.0, ist_gratis=False)
    m = merkmale(d)
    assert "w:amazon" in m and "h:mediamarkt" in m
    assert "q:mydealz" in m and "p:20-50" in m


def test_stoppwoerter_und_zahlen_fliegen_raus():
    d = Deal(titel="Der neue Deal für 2024 mit Rabatt", preis_eur=10.0)
    m = merkmale(d)
    assert "w:der" not in m and "w:deal" not in m and "w:2024" not in m


def test_gratis_bekommt_eigene_preisklasse():
    d = Deal(titel="Spiel", ist_gratis=True)
    assert "p:gratis" in merkmale(d)


# --- Zurueckhaltung bei duenner Datenlage ---------------------------------

def test_ohne_daten_keine_meinung(db):
    modell = trainiere(db)
    assert not modell.bereit
    assert modell.punkte(deal(db, "Irgendwas", 10.0)) == 0.5


def test_wenige_beispiele_reichen_nicht(db):
    """Ein Vorschlag aus drei Beispielen waere geraten, nicht gelernt."""
    for i in range(3):
        d = deal(db, f"LEGO Technic Set {i}", 40.0)
        db.add(Interaction(deal_id=d.id, art="gemerkt"))
    db.commit()
    assert not trainiere(db).bereit


def test_ohne_gegenbeispiele_faellt_kein_urteil(db):
    """Ein Modell, das nur Gemochtes kennt, findet alles gut."""
    modell = Modell()
    for i in range(MIN_POSITIV + 5):
        modell.lerne(Deal(titel=f"LEGO {i}", preis_eur=40.0), 1.0, mag_ich=True)
    modell.trainiert = True
    assert not modell.bereit


# --- Lernen ----------------------------------------------------------------

def _fuettere(db, gemocht: list[str], ignoriert: list[str]):
    for i, titel in enumerate(gemocht):
        d = deal(db, f"{titel} {i}", 40.0)
        db.add(Interaction(deal_id=d.id, art="gemerkt"))
    for i, titel in enumerate(ignoriert):
        deal(db, f"{titel} {i}", 40.0)
    db.commit()


def test_modell_erkennt_das_muster(db):
    _fuettere(db,
              gemocht=["LEGO Technic Bausatz"] * 15,
              ignoriert=["Kaffeemaschine Vollautomat"] * 40)
    modell = trainiere(db)
    assert modell.bereit

    passt = modell.punkte(Deal(titel="LEGO Technic Lamborghini", preis_eur=40.0))
    passt_nicht = modell.punkte(Deal(titel="Kaffeemaschine Milchaufschäumer",
                                     preis_eur=40.0))
    assert passt > 0.5 > passt_nicht


def test_modell_kann_sich_erklaeren(db):
    """Ohne Begruendung waere die Empfehlung eine Blackbox."""
    _fuettere(db, gemocht=["LEGO Technic Bausatz"] * 15,
              ignoriert=["Kaffeemaschine"] * 40)
    gruende = trainiere(db).gruende(Deal(titel="LEGO Technic Set", preis_eur=40.0))
    assert gruende
    assert any("lego" in g.lower() for g in gruende)


def test_verworfene_deals_zaehlen_negativ(db):
    for i in range(15):
        d = deal(db, f"LEGO Set {i}", 40.0)
        db.add(Interaction(deal_id=d.id, art="gemerkt"))
    for i in range(15):
        d = deal(db, f"Kaffee Kapseln {i}", 40.0)
        db.add(Interaction(deal_id=d.id, art="verworfen"))
    db.commit()

    modell = trainiere(db)
    assert modell.punkte(Deal(titel="LEGO Bausatz", preis_eur=40.0)) > \
        modell.punkte(Deal(titel="Kaffee Kapseln XL", preis_eur=40.0))


# --- Regelvorschlaege ------------------------------------------------------

def test_keine_vorschlaege_ohne_genug_daten(db):
    for i in range(4):
        d = deal(db, f"LEGO {i}", 40.0)
        db.add(Interaction(deal_id=d.id, art="gemerkt"))
    db.commit()
    assert vorschlaege(db) == []


def test_haeufiges_stichwort_wird_vorgeschlagen(db):
    for i in range(15):
        d = deal(db, f"LEGO Technic Bausatz {i}", 40.0)
        db.add(Interaction(deal_id=d.id, art="gemerkt"))
    db.commit()

    ergebnis = vorschlaege(db)
    assert ergebnis
    keywords = [v.regel.get("keywords", [None])[0] for v in ergebnis]
    assert "lego" in keywords
    treffer = next(v for v in ergebnis if v.regel.get("keywords") == ["lego"])
    assert "15 von 15" in treffer.begruendung
    assert treffer.regel.get("max_preis")     # Preisgrenze aus dem Verhalten


def test_haendler_wird_vorgeschlagen(db):
    for i in range(15):
        d = deal(db, f"Artikel {i}", 40.0, haendler="Amazon")
        db.add(Interaction(deal_id=d.id, art="gemerkt"))
    db.commit()
    assert any(v.regel.get("haendler") == ["amazon"] for v in vorschlaege(db))


def test_seltenes_merkmal_wird_nicht_vorgeschlagen(db):
    """Aus 1 von 15 laesst sich keine Regel ableiten."""
    for i in range(14):
        d = deal(db, f"Kaffee Kapseln {i}", 40.0)
        db.add(Interaction(deal_id=d.id, art="gemerkt"))
    einzeln = deal(db, "LEGO Ausreisser", 40.0)
    db.add(Interaction(deal_id=einzeln.id, art="gemerkt"))
    db.commit()

    keywords = [v.regel.get("keywords", [None])[0] for v in vorschlaege(db)]
    assert "lego" not in keywords


# --- Aufzeichnung ----------------------------------------------------------

def test_interaktion_wird_festgehalten(db):
    d = deal(db, "Ein Deal", 10.0)
    notiere(db, d.id, "gemerkt")
    assert db.query(Interaction).count() == 1


def test_gleiche_interaktion_wird_nicht_gedoppelt(db):
    """Sonst zaehlt mehrfaches Anschauen wie mehrfaches Interesse."""
    d = deal(db, "Ein Deal", 10.0)
    for _ in range(5):
        notiere(db, d.id, "geoeffnet")
    assert db.query(Interaction).count() == 1


def test_unbekannte_art_wird_ignoriert(db):
    d = deal(db, "Ein Deal", 10.0)
    notiere(db, d.id, "quatsch")
    assert db.query(Interaction).count() == 0


def test_punktzahl_trennt_passend_von_unpassend(db):
    """Ein Artikel ganz unten in der Empfehlung darf nicht 'passt zu dir'
    behaupten - die Route zeigt Gruende erst ab 0,6 Punkten."""
    _fuettere(db, gemocht=["LEGO Technic Bausatz"] * 15,
              ignoriert=["Kaffeekapseln Vorratspack"] * 40)
    modell = trainiere(db)

    passt = Deal(titel="LEGO Technic Lamborghini", preis_eur=40.0)
    passt_nicht = Deal(titel="Kaffeekapseln Espresso", preis_eur=40.0,
                       quelle="mydealz")

    assert modell.punkte(passt) > 0.6
    assert modell.punkte(passt_nicht) < 0.5
    assert modell.gruende(passt)
