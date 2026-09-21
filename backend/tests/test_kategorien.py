"""Worum es in einem Deal geht - Elektronik, SSD, Abo, Dessous.

Die Einstufung ist eine Wortliste, und Wortlisten gehen auf zwei Arten
kaputt: sie treffen zu wenig (der Filter bleibt leer) oder zu viel (jeder
Deal traegt jede Marke). Beide Richtungen stehen hier.
"""
import pytest

from app.kategorien import (MAX_PRO_DEAL, als_text, alle, aus_text, bestimme,
                            label)


# --- Treffen, was gemeint ist ---------------------------------------------

@pytest.mark.parametrize("titel,erwartet", [
    ("Samsung 990 Pro 2TB NVMe SSD für 129 €", "speicher"),
    ("Sony WH-1000XM5 Kopfhörer 249 €", "audio"),
    ("LEGO Technic Bugatti für 249 €", "kinder"),
    ("Netflix Standard 4,99 € pro Monat", "abo"),
    ("Allnet-Flat 20 GB LTE für 9,99 €", "mobilfunk"),
    ("Saugroboter Roborock S8 reduziert", "haushalt"),
    ("Winterreifen 205/55 R16 im Set", "auto"),
    ("Kindle E-Book Sale: Romane für 0,99 €", "medien"),
])
def test_offensichtliche_faelle(titel, erwartet):
    assert erwartet in bestimme(titel).keys


def test_zusammensetzungen_werden_gefunden():
    """Deutsch klebt Woerter aneinander - daran scheitern naive Wortlisten."""
    assert "speicher" in bestimme("Externe SSD-Festplatte 1TB").keys
    assert "gaming" in bestimme("Gaming-Headset mit Mikrofon").keys
    assert "abo" in bestimme("Monatsabo jederzeit kündbar").keys


def test_mehrere_marken_statt_einer_schublade():
    """Ein Gaming-Notebook mit SSD gehoert in alle drei Filter."""
    keys = bestimme("Gaming-Notebook mit 1 TB SSD und RTX 4070").keys
    assert {"speicher", "computer", "gaming"} == set(keys)


def test_hoechstens_drei():
    """Sonst wird die Karte zur Wortwolke."""
    lang = ("Gaming-Notebook mit SSD, Kopfhörer, Monitor, Tastatur, Maus, "
            "Drucker, Fernseher und Kaffeemaschine")
    assert len(bestimme(lang).keys) <= MAX_PRO_DEAL


def test_titel_zaehlt_mehr_als_die_beschreibung():
    """In der Beschreibung steht der halbe Shop - im Titel steht die Ware."""
    befund = bestimme("Sony Kopfhörer WH-1000XM5",
                      "Versand gratis. Siehe auch unsere SSD-Angebote und "
                      "Notebooks im Sale.")
    assert befund.keys[0] == "audio"


# --- Nicht treffen, was nicht gemeint ist ---------------------------------

@pytest.mark.parametrize("titel", [
    "See above for details",          # "abo" steckt in "above"
    "Vodafone Gutschein",             # "vod" steckt in "Vodafone"
    "Bewertung mit 5 Sternen",
])
def test_kurze_begriffe_stolpern_nicht(titel):
    befund = bestimme(titel, erwachsen=True)
    assert "abo" not in befund.keys
    assert "seiten18" not in befund.keys


def test_ohne_treffer_bleibt_es_leer():
    assert bestimme("Irgendein namenloses Angebot").keys == []


# --- 18+ bleibt getrennt --------------------------------------------------

def test_18er_marken_nur_fuer_18er_funde():
    """Sonst steht 'Dessous' als Filter im normalen Feed."""
    normal = bestimme("Satisfyer Pro 2 Vibrator 24,99 €")
    assert not any(k.endswith("18") for k in normal.keys)

    erwachsen = bestimme("Satisfyer Pro 2 Vibrator 24,99 €", erwachsen=True)
    assert "toys18" in erwachsen.keys


def test_abo_wird_auch_im_18er_bereich_erkannt():
    """Der eigentliche Anlass: guenstige Zugaenge fuer Internetseiten."""
    keys = bestimme("Premium-Mitgliedschaft 3 Monate Zugang", erwachsen=True).keys
    assert "seiten18" in keys or "abo" in keys


def test_auswahl_je_bereich():
    normal = {k.key for k in alle()}
    erwachsen = {k.key for k in alle(erwachsen=True)}
    assert not normal & erwachsen
    assert "speicher" in normal and "toys18" in erwachsen


# --- Speicherform ---------------------------------------------------------

def test_text_und_zurueck():
    assert als_text(["speicher", "computer"]) == "|speicher|computer|"
    assert aus_text("|speicher|computer|") == ["speicher", "computer"]
    assert aus_text("") == [] and aus_text(None) == []


def test_unbekannte_schluessel_fliegen_raus():
    """Sonst steht in der Datenbank ein Filter, den es nicht mehr gibt."""
    assert als_text(["speicher", "erfunden"]) == "|speicher|"
    assert aus_text("|speicher|erfunden|") == ["speicher"]


def test_trennzeichen_verhindert_teiltreffer():
    """'|abo|' darf nicht in '|abonnement_neu|' hineinpassen."""
    text = als_text(["abo"])
    assert "|abo|" in text
    assert "|ab|" not in text


def test_label_faellt_auf_den_schluessel_zurueck():
    assert label("speicher") == "Speicher & SSD"
    assert label("gibtsnicht") == "gibtsnicht"


# --- Nachtrag fuer den Altbestand -----------------------------------------

def test_nachtrag_fuellt_leere_felder(tmp_path, monkeypatch):
    """Ohne Nachtrag waeren die Filter fuer alles Aeltere leer."""
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()

    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.kategorien import nachtragen
    from app.models import Deal

    init_db()
    with SessionLocal() as db:
        db.add(Deal(url_hash="a" * 32, titel="Samsung 2TB NVMe SSD",
                    titel_norm="samsung 2tb nvme ssd", url="https://x.test/1",
                    quelle="test"))
        db.add(Deal(url_hash="b" * 32, titel="Namenloses Angebot",
                    titel_norm="namenloses angebot", url="https://x.test/2",
                    quelle="test"))
        db.commit()

        assert nachtragen(db) == 2
        # Zweiter Lauf fasst nichts mehr an - sonst laeuft er ewig im Kreis.
        assert nachtragen(db) == 0

        deals = {d.titel: d for d in db.scalars(select(Deal))}
        assert "speicher" in aus_text(deals["Samsung 2TB NVMe SSD"].kategorien)
        assert deals["Namenloses Angebot"].kategorien == ""


# --- Nach einer Listenaenderung neu einstufen ------------------------------

def test_neue_wortliste_erreicht_auch_den_bestand(tmp_path, monkeypatch):
    """Der Fehler, der erst in drei Wochen auffaellt.

    Ohne diesen Durchlauf waere jede Verbesserung an der Wortliste fuer
    alles wirkungslos, was schon in der Datenbank liegt - der Filter bliebe
    fuer den halben Bestand leer, und niemand wuesste, warum.
    """
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()

    from sqlalchemy import select

    from app import kategorien as kat
    from app.db import SessionLocal, get_setting, init_db, set_setting
    from app.models import Deal

    init_db()
    with SessionLocal() as db:
        db.add(Deal(url_hash="c" * 32, titel="Roborock S8 Pro Ultra",
                    titel_norm="roborock s8 pro ultra", url="https://x.test/9",
                    quelle="test", kategorien=""))      # nach alter Liste leer
        # Stand einer aelteren Wortliste - genau die Lage nach einem Update.
        set_setting(db, kat.SCHLUESSEL_STAND,
                    {"version": kat.VERSION - 1, "cursor": 0})
        db.commit()

        assert kat.nachtragen(db, grenze=500) == 1

        deal = db.scalar(select(Deal))
        assert "haushalt" in kat.aus_text(deal.kategorien)
        stand = get_setting(db, kat.SCHLUESSEL_STAND)
        assert stand["version"] == kat.VERSION

        # Und danach fasst er nichts mehr an.
        assert kat.nachtragen(db, grenze=500) == 0


def test_neu_einstufen_laeuft_in_haeppchen(tmp_path, monkeypatch):
    """Ein Start mit 50.000 Deals darf nicht minutenlang haengen."""
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()

    from app import kategorien as kat
    from app.db import SessionLocal, get_setting, init_db, set_setting
    from app.models import Deal

    init_db()
    with SessionLocal() as db:
        for i in range(5):
            db.add(Deal(url_hash=f"{i:032d}", titel="Samsung 2TB NVMe SSD",
                        titel_norm="samsung 2tb nvme ssd",
                        url=f"https://x.test/{i}", quelle="test", kategorien=""))
        set_setting(db, kat.SCHLUESSEL_STAND,
                    {"version": kat.VERSION - 1, "cursor": 0})
        db.commit()

        assert kat.nachtragen(db, grenze=2) == 2
        stand = get_setting(db, kat.SCHLUESSEL_STAND)
        assert stand["version"] != kat.VERSION and stand["cursor"] > 0

        assert kat.nachtragen(db, grenze=2) == 2
        assert kat.nachtragen(db, grenze=2) == 1        # Rest, damit fertig
        assert get_setting(db, kat.SCHLUESSEL_STAND)["version"] == kat.VERSION


def test_18er_marken_folgen_der_einstufung(tmp_path, monkeypatch):
    """Wird ein Deal erst spaeter als 18+ erkannt, passen seine Marken nicht
    mehr - die 18er-Kategorien gibt es nur fuer 18er-Funde."""
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()

    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.kategorien import aus_text
    from app.models import Deal
    from app.pipeline import ingest
    from app.sources.base import DealItem

    init_db()
    titel = "Satisfyer Pro 2 Vibrator"
    with SessionLocal() as db:
        # Erst ueber eine normale Quelle - die Stichwortpruefung stuft ein.
        ingest(db, "custom_feed", [DealItem(titel=titel, url="https://x.test/1",
                                            quelle="custom_feed", preis=24.99)])
        deal = db.scalar(select(Deal))
        assert deal.erwachsen is True
        assert "toys18" in aus_text(deal.kategorien)
