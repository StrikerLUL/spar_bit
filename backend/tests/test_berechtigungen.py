"""Wer darf was - und zwar an jedem schreibenden Endpunkt, nicht nur an
denen, an die man beim Bauen gedacht hat.

Bisher wurde die Trennung zwischen Konten dort geprueft, wo sie gebaut
wurde: Regeln, Kanaele, Wunschlisten. Der Fehler, der dabei durchrutschte,
war ein anderer: `PUT /api/settings` haengt am Router und nicht an einer
Rolle - damit konnte ein **Gast**, der laut Beschreibung nur zusehen darf,
die Waehrungskurse der ganzen Anlage aendern, die Preisfehler-Schwelle
verstellen und das Passwort der Sicherungen setzen.

Solche Luecken findet man nicht, indem man Endpunkte einzeln prueft,
sondern indem man sie aufzaehlt. Darum steht hier eine Liste, und jede
neue anlagenweite Einstellung muss in ihr auftauchen.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    return lade_app_neu()


@pytest.fixture
def admin(app):
    with TestClient(app.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


def konto(app, admin_client, name, rolle):
    antwort = admin_client.post("/api/auth/benutzer", json={
        "username": name, "password": "nochEinPasswort1", "rolle": rolle})
    assert antwort.status_code == 200, antwort.text
    client = TestClient(app.app)
    client.post("/api/auth/login",
                json={"username": name, "password": "nochEinPasswort1"})
    return client


@pytest.fixture
def gast(app, admin):
    return konto(app, admin, "zuschauer", "gast")


@pytest.fixture
def mitglied(app, admin):
    return konto(app, admin, "mitbewohner", "mitglied")


# Was die ganze Anlage betrifft: nur ein Admin.
#
# Die Liste ist der eigentliche Test. Ein neuer anlagenweiter Endpunkt,
# der hier fehlt, faellt niemandem auf - deshalb gehoert er beim Anlegen
# hier hinein.
NUR_ADMIN = [
    ("PUT", "/api/settings", {"waehrungskurse": {"USD": 0.5}}),
    ("PUT", "/api/settings", {"preisfehler_schwelle": 30}),
    ("PUT", "/api/settings", {"backup_passwort": "geheim"}),
    ("PUT", "/api/settings", {"zweifaktor_pflicht": True}),
    ("POST", "/api/bilder-aufraeumen", None),
    ("POST", "/api/sources/mydealz/snooze", None),
    ("POST", "/api/preisfehler/schwelle-uebernehmen", None),
    ("PATCH", "/api/sources/mydealz", {"enabled": True}),
]

# Was jeder darf, der kein Gast ist.
NICHT_FUER_GAESTE = [
    ("POST", "/api/rules", {"name": "Test", "keywords": ["x"]}),
    ("POST", "/api/channels", {"name": "T", "type": "ntfy",
                               "config": {"topic": "x"}}),
    ("POST", "/api/watch", {"name": "X", "url": "https://shop.test/1"}),
]


def ruf(client, methode, pfad, koerper):
    return client.request(methode, pfad,
                          json=koerper if koerper is not None else None)


@pytest.mark.parametrize("methode,pfad,koerper", NUR_ADMIN,
                         ids=lambda v: str(v)[:40])
def test_anlagenweites_bleibt_dem_admin(gast, mitglied, methode, pfad, koerper):
    """Weder Gast noch Mitglied darf hier durchkommen."""
    assert ruf(gast, methode, pfad, koerper).status_code == 403
    assert ruf(mitglied, methode, pfad, koerper).status_code == 403


@pytest.mark.parametrize("methode,pfad,koerper", NUR_ADMIN,
                         ids=lambda v: str(v)[:40])
def test_der_admin_kommt_durch(admin, methode, pfad, koerper):
    """Die Gegenprobe: sonst wuerde ein zugemauerter Endpunkt als „sicher"
    durchgehen."""
    antwort = ruf(admin, methode, pfad, koerper)
    assert antwort.status_code != 403, antwort.text


@pytest.mark.parametrize("methode,pfad,koerper", NICHT_FUER_GAESTE,
                         ids=lambda v: str(v)[:40])
def test_gaeste_schauen_zu(gast, methode, pfad, koerper):
    assert ruf(gast, methode, pfad, koerper).status_code == 403


@pytest.mark.parametrize("methode,pfad,koerper", NICHT_FUER_GAESTE,
                         ids=lambda v: str(v)[:40])
def test_mitglieder_duerfen_ihr_eigenes(mitglied, methode, pfad, koerper):
    antwort = ruf(mitglied, methode, pfad, koerper)
    assert antwort.status_code != 403, antwort.text


def test_gast_darf_lesen(gast):
    """Zusehen ist ausdruecklich erlaubt - sonst waere die Rolle sinnlos."""
    for pfad in ("/api/deals", "/api/settings", "/api/rules", "/api/sources"):
        assert gast.get(pfad).status_code == 200, pfad


def test_ein_gast_kann_keinen_deal_merken(gast):
    """Der Feed gehoert allen, aber verstellt wird er nicht von einem Gast."""
    assert gast.put("/api/deals/1/alarm",
                    json={"ziel_preis": 10}).status_code == 403


# --- Zweiter Faktor fuer Administratoren ----------------------------------

def test_die_pflicht_laesst_sich_nicht_blind_einschalten(admin):
    """Sonst sperrt sich der einzige Administrator im selben Klick aus -
    und die Einstellung, mit der er es zuruecknehmen koennte, ist genau
    eine der gesperrten."""
    antwort = admin.put("/api/settings", json={"zweifaktor_pflicht": True})
    assert antwort.status_code == 409
    assert "zweiten Faktor" in antwort.json()["detail"]


def zweiten_faktor_einrichten(client):
    import app.zweifaktor as z

    start = client.post("/api/auth/zweifaktor/start").json()
    code = z.aktueller_code(start["geheimnis"])
    assert client.post("/api/auth/zweifaktor/bestaetigen",
                       json={"code": code}).status_code == 200


def test_mit_zweitem_faktor_geht_die_pflicht(admin):
    zweiten_faktor_einrichten(admin)
    assert admin.put("/api/settings",
                     json={"zweifaktor_pflicht": True}).status_code == 200
    assert admin.get("/api/settings").json()["zweifaktor_pflicht"] is True


def test_ein_admin_ohne_zweiten_faktor_verliert_die_admin_rechte(app, admin):
    """Die Huerde wirkt auch fuer die anderen Administratoren - aber sie
    sperrt niemanden aus der Anmeldung aus."""
    zweiten_faktor_einrichten(admin)
    admin.put("/api/settings", json={"zweifaktor_pflicht": True})

    zweiter = konto(app, admin, "zweiter_admin", "admin")
    # Lesen geht weiter, und der zweite Faktor laesst sich einrichten.
    assert zweiter.get("/api/deals").status_code == 200
    assert zweiter.post("/api/auth/zweifaktor/start").status_code == 200
    # Admin-Funktionen nicht.
    antwort = zweiter.post("/api/bilder-aufraeumen")
    assert antwort.status_code == 403
    assert "zweiten Faktor" in antwort.json()["detail"]

    # Und mit eingerichtetem Faktor stehen sie wieder offen.
    zweiten_faktor_einrichten(zweiter)
    assert zweiter.post("/api/bilder-aufraeumen").status_code == 200


def test_die_pflicht_laesst_sich_nicht_per_abschalten_umgehen(admin):
    zweiten_faktor_einrichten(admin)
    admin.put("/api/settings", json={"zweifaktor_pflicht": True})
    antwort = admin.post("/api/auth/zweifaktor/aus",
                         json={"password": "einGutesPasswort1"})
    assert antwort.status_code == 409


def test_das_ui_erfaehrt_von_der_pflicht_vor_dem_ersten_403(app, admin):
    zweiten_faktor_einrichten(admin)
    admin.put("/api/settings", json={"zweifaktor_pflicht": True})
    zweiter = konto(app, admin, "dritter_admin", "admin")
    stand = zweiter.get("/api/auth/zweifaktor").json()
    assert stand["pflicht_fuer_admins"] is True
    assert stand["faellig"] is True
