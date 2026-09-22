"""API-Token der Browser-Erweiterung.

Die Erweiterung laeuft auf fremden Shop-Seiten und kann das
Sitzungs-Cookie nicht mitschicken. Sie bekommt darum einen eigenen
Schluessel - und der ist genau so viel wert wie ein Passwort.

Zwei Zusagen stehen im Modul, und beide werden hier geprueft: in der
Datenbank liegt nur der Hash, und der Klartext ist genau einmal zu
sehen.
"""
import pytest
from fastapi import HTTPException

from app.tokens import PRAEFIX, erzeuge, pruefe, token_aus_header


@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    lade_app_neu()
    from app.db import SessionLocal, init_db
    init_db()
    with SessionLocal() as sitzung:
        yield sitzung


def test_der_klartext_steht_nicht_in_der_datenbank(db):
    zeile, klartext = erzeuge(db, "Laptop")
    assert klartext.startswith(PRAEFIX)
    assert zeile.token_hash != klartext
    assert klartext not in zeile.token_hash
    # Auch nicht in Teilen: der Praefix zum Wiedererkennen ist kurz genug,
    # um nicht zu erraten.
    assert len(zeile.praefix) <= 12


def test_ein_gueltiges_token_wird_erkannt(db):
    zeile, klartext = erzeuge(db, "Laptop")
    gefunden = pruefe(db, klartext)
    assert gefunden is not None
    assert gefunden.id == zeile.id


def test_die_nutzung_wird_vermerkt(db):
    """Damit sich im UI sehen laesst, welches Geraet noch zugreift - und
    welches man gefahrlos zurueckziehen kann."""
    _, klartext = erzeuge(db, "Laptop")
    zeile = pruefe(db, klartext)
    assert zeile.zuletzt_genutzt is not None


@pytest.mark.parametrize("versuch", [
    "", None, "irgendwas", "Bearer abc",
    # Richtiger Praefix, falscher Rest - der haeufigste Tippfehler.
    PRAEFIX + "falsch",
])
def test_was_nicht_stimmt_kommt_nicht_durch(db, versuch):
    erzeuge(db, "Laptop")
    assert pruefe(db, versuch) is None


def test_zwei_token_sind_verschieden(db):
    _, eins = erzeuge(db, "Laptop")
    _, zwei = erzeuge(db, "Handy")
    assert eins != zwei
    assert pruefe(db, eins).name == "Laptop"
    assert pruefe(db, zwei).name == "Handy"


def test_ein_leerer_name_bekommt_einen(db):
    """Ein Token ohne Namen laesst sich im UI nicht zuordnen - und was man
    nicht zuordnen kann, zieht man nie zurueck."""
    zeile, _ = erzeuge(db, "   ")
    assert zeile.name == "Browser-Erweiterung"


def test_ein_langer_name_wird_gekuerzt(db):
    zeile, _ = erzeuge(db, "x" * 500)
    assert len(zeile.name) <= 128


# --- Der Authorization-Header ---------------------------------------------

def test_bearer_wird_gelesen():
    assert token_aus_header("Bearer sparbit_abc") == "sparbit_abc"
    # Gross-/Kleinschreibung ist im Header nicht festgelegt.
    assert token_aus_header("bearer sparbit_abc") == "sparbit_abc"


@pytest.mark.parametrize("kopf", [None, "", "sparbit_abc", "Basic abc"])
def test_ohne_bearer_gibt_es_401(kopf):
    with pytest.raises(HTTPException) as fehler:
        token_aus_header(kopf)
    assert fehler.value.status_code == 401
    # Die Meldung sagt, was erwartet wird - sonst probiert man dreimal.
    assert "Bearer" in fehler.value.detail
