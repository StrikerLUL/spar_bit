"""SparBit ruft Adressen ab, die man ihm nennt - aber nicht ins eigene Netz.

Der gefaehrliche Fall ist nicht der Tippfehler, sondern die Absicht:
ein Feed, der brav antwortet und dann per 302 auf 127.0.0.1 zeigt, oder
ein Wunschlisten-Eintrag auf 169.254.169.254, wo bei jedem Cloud-Anbieter
die Zugangsdaten der Maschine liegen.
"""
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

# Bewusst erst in den Tests importiert: andere Testdateien laden das Paket
# "app" neu, und ein Modul-Import hier oben zeigte danach auf die alte
# Fassung - samt ihrer eigenen Einstellungen.


def netzschutz():
    from app import netzschutz as modul
    return modul


@pytest.mark.parametrize("url,teil", [
    ("http://127.0.0.1:8000/admin", "localhost"),
    ("http://localhost:9000/", "localhost"),
    ("http://169.254.169.254/latest/meta-data/", "Link-Local"),
    ("http://192.168.1.1/", "privates Netz"),
    ("http://10.0.0.5:8080/feed", "privates Netz"),
    ("http://172.16.0.1/", "privates Netz"),
    ("http://[::1]/", "localhost"),
])
def test_eigenes_netz_ist_tabu(url, teil):
    modul = netzschutz()
    with pytest.raises(modul.ZielVerboten) as fehler:
        modul.pruefe_sync(url)
    assert teil in str(fehler.value)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://beispiel.de/",
    "ftp://beispiel.de/datei",
])
def test_andere_schemata_gehen_nicht(url):
    modul = netzschutz()
    with pytest.raises(modul.ZielVerboten, match="http"):
        modul.pruefe_sync(url)


def test_ohne_rechnernamen_kein_abruf():
    modul = netzschutz()
    with pytest.raises(modul.ZielVerboten, match="Rechnername"):
        modul.pruefe_sync("http:///nur-ein-pfad")


def test_schalter_erlaubt_das_eigene_netz(monkeypatch):
    """Wer bewusst einen Feed im Heimnetz liest, soll das duerfen."""
    modul = netzschutz()
    monkeypatch.setattr(modul.settings, "erlaube_private_ziele", True)
    modul.pruefe_sync("http://192.168.1.50:8080/feed.xml")     # wirft nicht


# --- Der Weg ueber eine Weiterleitung ------------------------------------

class Umleiter(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
        self.end_headers()

    def log_message(self, *_):
        pass


@pytest.fixture
def umleitender_server(monkeypatch):
    """Ein Server, der erst antwortet und dann ins Metadaten-Netz zeigt."""
    monkeypatch.setattr(netzschutz().settings, "erlaube_private_ziele", False)
    srv = HTTPServer(("127.0.0.1", 0), Umleiter)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/start"
    srv.shutdown()


def test_weiterleitung_ins_eigene_netz_wird_gestoppt(umleitender_server, monkeypatch):
    """Der entscheidende Fall: die Weiterleitung entsteht erst im Client.

    Eine Pruefung an der Aufrufstelle sieht sie nie. Damit der Test das
    zweite Glied der Kette prueft und nicht schon am ersten haengen
    bleibt, gilt der Testserver hier als oeffentlich erreichbar - das
    Weiterleitungsziel 169.254.169.254 bleibt, was es ist.
    """
    from app.http import PoliteClient

    modul = netzschutz()
    echt = modul._adressen

    def aufloesen(host, port):
        if host == "127.0.0.1":
            return ["93.184.216.34"]        # tut so, als waere es draussen
        return echt(host, port)

    monkeypatch.setattr(modul, "_adressen", aufloesen)

    async def lauf():
        client = PoliteClient(per_host_delay=0)
        try:
            with pytest.raises(modul.ZielVerboten) as fehler:
                await client.get(umleitender_server)
            assert "Link-Local" in str(fehler.value)
        finally:
            await client.aclose()

    asyncio.run(lauf())


def test_kanaele_duerfen_ins_heimnetz(monkeypatch):
    """Ein Gotify unter 192.168.x.x ist der Normalfall, kein Angriff."""
    import httpx

    from app.http import PoliteClient

    gesehen = {}

    async def lauf():
        client = PoliteClient(per_host_delay=0)

        async def fake_post(url, **kwargs):
            gesehen["extensions"] = kwargs.get("extensions")
            return httpx.Response(200, request=httpx.Request("POST", url))

        client._client.post = fake_post
        await client.post("http://192.168.1.20:8080/message", json={"x": 1})
        await client.aclose()

    asyncio.run(lauf())
    assert gesehen["extensions"] == {"sparbit_intern": True}
