"""Die Bremse fuer Endpunkte, die nach draussen greifen.

Der Fall, gegen den sie steht: ein Knopf im UI loest mehrere Abrufe bei
einem fremden Shop aus. Wer ihn in einer Schleife drueckt, macht aus
SparBit einen Verstaerker - und der Shop sperrt nicht SparBit, sondern
die IP des Servers.

Geprueft wird darum nicht "irgendwann kommt ein 429", sondern die drei
Eigenschaften, auf die es ankommt: ein Schwall geht durch, danach wird
gewartet, und Konten stehen sich nicht gegenseitig im Weg.
"""
import pytest
from fastapi.testclient import TestClient

from app import drosselung


@pytest.fixture(autouse=True)
def leerer_eimer():
    drosselung.zuruecksetzen()
    yield
    drosselung.zuruecksetzen()


# --- Der Kern, ohne HTTP ---------------------------------------------------

def test_der_erste_klick_wartet_nie():
    """Wer sich gerade angemeldet hat, soll nicht in eine Bremse laufen."""
    assert drosselung.pruefe("x", 1, pro_minute=1, stoss=1, jetzt=0.0) == 0.0


def test_ein_schwall_geht_durch_und_dann_ist_schluss():
    for _ in range(4):
        assert drosselung.pruefe("x", 1, pro_minute=6, stoss=4, jetzt=0.0) == 0.0
    warte = drosselung.pruefe("x", 1, pro_minute=6, stoss=4, jetzt=0.0)
    assert warte > 0


def test_nach_der_wartezeit_geht_es_weiter():
    for _ in range(3):
        drosselung.pruefe("x", 1, pro_minute=60, stoss=3, jetzt=0.0)
    assert drosselung.pruefe("x", 1, pro_minute=60, stoss=3, jetzt=0.0) > 0
    # 60 pro Minute = eine Marke je Sekunde.
    assert drosselung.pruefe("x", 1, pro_minute=60, stoss=3, jetzt=1.5) == 0.0


def test_der_eimer_laeuft_nicht_ueber():
    """Eine Stunde Pause darf keine Stunde Vollgas erlauben."""
    drosselung.pruefe("x", 1, pro_minute=60, stoss=3, jetzt=0.0)
    for _ in range(3):
        assert drosselung.pruefe("x", 1, pro_minute=60, stoss=3, jetzt=3600.0) == 0.0
    assert drosselung.pruefe("x", 1, pro_minute=60, stoss=3, jetzt=3600.0) > 0


def test_konten_bremsen_sich_nicht_gegenseitig():
    for _ in range(3):
        drosselung.pruefe("x", 1, pro_minute=6, stoss=3, jetzt=0.0)
    assert drosselung.pruefe("x", 1, pro_minute=6, stoss=3, jetzt=0.0) > 0
    # Der Mitbewohner hat damit nichts zu tun.
    assert drosselung.pruefe("x", 2, pro_minute=6, stoss=3, jetzt=0.0) == 0.0


def test_verschiedene_knoepfe_haben_eigene_eimer():
    for _ in range(2):
        drosselung.pruefe("test", 1, pro_minute=6, stoss=2, jetzt=0.0)
    assert drosselung.pruefe("test", 1, pro_minute=6, stoss=2, jetzt=0.0) > 0
    assert drosselung.pruefe("suche", 1, pro_minute=6, stoss=2, jetzt=0.0) == 0.0


# --- Am echten Endpunkt ----------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    main = lade_app_neu()
    with TestClient(main.app) as c:
        c.post("/api/auth/setup",
               json={"username": "cillian", "password": "einGutesPasswort1"})
        yield c


def test_die_feed_suche_wird_irgendwann_gebremst(client, monkeypatch):
    """Ein Aufruf hier laedt eine fremde Seite und probiert Pfade durch."""
    async def keine_suche(http, url, **kw):
        return {"feeds": [], "hinweis": "Test"}

    import app.feedfinder as ff
    monkeypatch.setattr(ff, "suche", keine_suche)

    codes = [client.post("/api/sources/feed-suche",
                         json={"url": "https://beispiel.test"}).status_code
             for _ in range(8)]
    assert 429 in codes, codes
    # Und zwar nicht sofort: ein paar Versuche am Stueck sind in Ordnung.
    assert codes[0] != 429


def test_die_absage_sagt_wie_lange(client, monkeypatch):
    async def keine_suche(http, url, **kw):
        return {"feeds": []}

    import app.feedfinder as ff
    monkeypatch.setattr(ff, "suche", keine_suche)

    antwort = None
    for _ in range(10):
        antwort = client.post("/api/sources/feed-suche",
                              json={"url": "https://beispiel.test"})
        if antwort.status_code == 429:
            break
    assert antwort.status_code == 429
    # Ohne Retry-After muesste ein Skript raten - und raet zu kurz.
    assert int(antwort.headers["retry-after"]) >= 1
    assert "Sekunden" in antwort.json()["detail"]
