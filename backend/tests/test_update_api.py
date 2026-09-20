"""Update-Knopf und der Draht zum Host-Skript.

Der Container fasst den Host nicht an; er legt einen Auftrag ab, den das
Skript abholt. Hier wird beides von beiden Seiten durchgespielt.
"""
import pytest
from fastapi.testclient import TestClient

TOKEN = "geheimes-update-token-fuer-den-test"


def _lade_app(tmp_path, monkeypatch, token):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SPARBIT_UPDATE_TOKEN", token)
    return lade_app_neu()


@pytest.fixture
def client(tmp_path, monkeypatch):
    main = _lade_app(tmp_path, monkeypatch, TOKEN)
    with TestClient(main.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


@pytest.fixture
def client_ohne_token(tmp_path, monkeypatch):
    main = _lade_app(tmp_path, monkeypatch, "")
    with TestClient(main.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


# --- ohne Token: Funktion aus ---------------------------------------------

def test_ohne_token_ist_die_funktion_aus(client_ohne_token):
    antwort = client_ohne_token.get("/api/system/update").json()
    assert antwort["eingerichtet"] is False
    assert "README" in antwort["grund"]


def test_ohne_token_laesst_sich_nichts_anfordern(client_ohne_token):
    assert client_ohne_token.post("/api/system/update").status_code == 409


def test_ohne_token_kommt_das_skript_nicht_rein(client_ohne_token):
    """Sonst koennte ein leeres Token als gueltig durchgehen."""
    antwort = client_ohne_token.get("/api/system/update/auftrag",
                                    headers={"X-SparBit-Update": ""})
    assert antwort.status_code == 403


# --- Browser-Seite ---------------------------------------------------------

def test_status_ist_anfangs_leer(client):
    antwort = client.get("/api/system/update").json()
    assert antwort["eingerichtet"] is True
    assert antwort["angefordert"] is False
    assert antwort["auto"] is False
    assert antwort["commit"] is None


def test_knopf_hinterlegt_einen_auftrag(client):
    assert client.post("/api/system/update").json()["ok"] is True
    assert client.get("/api/system/update").json()["angefordert"] is True


def test_automatik_laesst_sich_schalten(client):
    client.put("/api/system/update/auto", json={"auto": True})
    assert client.get("/api/system/update").json()["auto"] is True
    client.put("/api/system/update/auto", json={"auto": False})
    assert client.get("/api/system/update").json()["auto"] is False


def test_update_braucht_eine_anmeldung(client):
    client.post("/api/auth/logout")
    assert client.get("/api/system/update").status_code == 401
    assert client.post("/api/system/update").status_code == 401


# --- Host-Seite ------------------------------------------------------------

def test_falsches_token_wird_abgewiesen(client):
    antwort = client.get("/api/system/update/auftrag",
                         headers={"X-SparBit-Update": "falsch"})
    assert antwort.status_code == 403


def test_skript_holt_den_auftrag_und_verbraucht_ihn(client):
    client.post("/api/system/update")
    kopf = {"X-SparBit-Update": TOKEN}

    erster = client.get("/api/system/update/auftrag", headers=kopf).json()
    assert erster["jetzt"] is True

    # Zweiter Lauf darf nicht nochmal bauen.
    zweiter = client.get("/api/system/update/auftrag", headers=kopf).json()
    assert zweiter["jetzt"] is False


def test_auto_bleibt_beim_abholen_stehen(client):
    """Die Automatik ist ein Dauerzustand, kein einmaliger Auftrag."""
    client.put("/api/system/update/auto", json={"auto": True})
    kopf = {"X-SparBit-Update": TOKEN}
    for _ in range(3):
        assert client.get("/api/system/update/auftrag", headers=kopf).json()["auto"] is True


def test_bericht_landet_im_status(client):
    kopf = {"X-SparBit-Update": TOKEN}
    client.post("/api/system/update/bericht", headers=kopf, json={
        "laeuft": False, "zweig": "main", "commit": "a" * 40,
        "betreff": "Etwas repariert", "neue_commits": 0,
        "geprueft_am": "2026-09-20T10:00:00Z",
        "letztes_update": {"zeit": "2026-09-20T10:00:00Z", "ok": True,
                           "von": "1234567", "nach": "abcdefg", "fehler": None},
    })
    status = client.get("/api/system/update").json()
    assert status["commit_kurz"] == "aaaaaaa"
    assert status["betreff"] == "Etwas repariert"
    assert status["letztes_update"]["ok"] is True
    assert status["neue_commits"] == 0


def test_teilbericht_loescht_nichts(client):
    """Der Minutenlauf meldet nur den Stand - der letzte Bericht bleibt."""
    kopf = {"X-SparBit-Update": TOKEN}
    client.post("/api/system/update/bericht", headers=kopf, json={
        "letztes_update": {"zeit": "x", "ok": True, "von": "a", "nach": "b",
                           "fehler": None}})
    client.post("/api/system/update/bericht", headers=kopf,
                json={"laeuft": False, "neue_commits": 2})
    status = client.get("/api/system/update").json()
    assert status["letztes_update"]["ok"] is True
    assert status["neue_commits"] == 2


def test_waehrend_eines_laufs_wird_nicht_nochmal_angefordert(client):
    kopf = {"X-SparBit-Update": TOKEN}
    client.post("/api/system/update/bericht", headers=kopf, json={"laeuft": True})
    antwort = client.post("/api/system/update").json()
    assert "läuft bereits" in antwort["hinweis"]
    assert client.get("/api/system/update").json()["angefordert"] is False


def test_langes_protokoll_wird_gekuerzt(client):
    kopf = {"X-SparBit-Update": TOKEN}
    client.post("/api/system/update/bericht", headers=kopf,
                json={"protokoll": "z" * 50000})
    status = client.get("/api/system/update").json()
    assert len(status["protokoll"]) == 20000


# --- Claimer ueber denselben Draht -----------------------------------------

def test_claimer_ohne_token_ist_aus(client_ohne_token):
    antwort = client_ohne_token.get("/api/claimer/lauf").json()
    assert antwort["eingerichtet"] is False
    assert client_ohne_token.post("/api/claimer/lauf").status_code == 409


def test_claimer_knopf_hinterlegt_einen_auftrag(client):
    assert client.post("/api/claimer/lauf").json()["ok"] is True
    assert client.get("/api/claimer/lauf").json()["angefordert"] is True


def test_skript_holt_den_claimer_auftrag_einmal(client):
    client.post("/api/claimer/lauf")
    kopf = {"X-SparBit-Update": TOKEN}

    assert client.get("/api/system/update/auftrag", headers=kopf).json()["claimer"] is True
    # Zweiter Lauf darf den Container nicht nochmal starten.
    assert client.get("/api/system/update/auftrag", headers=kopf).json()["claimer"] is False


def test_update_und_claimer_stoeren_sich_nicht(client):
    client.post("/api/system/update")
    client.post("/api/claimer/lauf")
    auftrag = client.get("/api/system/update/auftrag",
                         headers={"X-SparBit-Update": TOKEN}).json()
    assert auftrag["jetzt"] is True
    assert auftrag["claimer"] is True


def test_claimer_bericht_landet_im_status(client):
    kopf = {"X-SparBit-Update": TOKEN}
    client.post("/api/system/update/claimer-bericht", headers=kopf,
                json={"laeuft": False, "zuletzt": "2026-09-20T13:00:00Z",
                      "ok": True, "ausgabe": "Epic: 2 Spiele geholt"})
    status = client.get("/api/claimer/lauf").json()
    assert status["ok"] is True
    assert "2 Spiele" in status["ausgabe"]


def test_waehrend_eines_laufs_wird_nicht_nochmal_gestartet(client):
    kopf = {"X-SparBit-Update": TOKEN}
    client.post("/api/system/update/claimer-bericht", headers=kopf,
                json={"laeuft": True})
    assert "läuft bereits" in client.post("/api/claimer/lauf").json()["hinweis"]
    assert client.get("/api/claimer/lauf").json()["angefordert"] is False


def test_claimer_bericht_braucht_das_token(client):
    antwort = client.post("/api/system/update/claimer-bericht",
                          headers={"X-SparBit-Update": "falsch"}, json={})
    assert antwort.status_code == 403
