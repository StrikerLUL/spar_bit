"""Das optionale lokale Sprachmodell.

Die Regeln, die es sich gefallen lassen muss: aus, bis jemand es
einschaltet; nur eine Auswahl, keine freie Antwort; und jeder Fehler
endet in „keine Antwort", nicht in einem abgebrochenen Quellenlauf.

Kleine Modelle antworten gern mit einem ganzen Satz. Darum wird nicht
verglichen, sondern gesucht - aber nur nach Gruppen, die es gibt.
"""
import pytest

from app.ollama import _auswerten, eingerichtet, warengruppe
from app.warengruppe import GRUPPEN


def test_ohne_adresse_ist_es_aus():
    assert not eingerichtet(None)
    assert not eingerichtet("")
    assert not eingerichtet("   ")
    assert eingerichtet("http://127.0.0.1:11434")


@pytest.mark.parametrize("antwort,erwartet", [
    ("elektronik", "elektronik"),
    ("Elektronik", "elektronik"),
    ("  gaming\n", "gaming"),
    ("Das ist wohl Haushalt.", "haushalt"),
    ("Antwort: werkzeug", "werkzeug"),
])
def test_eine_bekannte_gruppe_wird_herausgeloest(antwort, erwartet):
    assert _auswerten(antwort) == erwartet


@pytest.mark.parametrize("antwort", [
    "", "   ", "keine", "Ich weiss es nicht",
    # Die gefaehrlichste Antwort: eine neue Gruppe, die es nicht gibt.
    "Gartenmoebel", "sonstiges",
])
def test_alles_andere_gilt_als_keine_antwort(antwort):
    assert _auswerten(antwort) is None


def test_jede_gruppe_laesst_sich_zurueckerkennen():
    """Sonst gaebe es Gruppen, die das Modell nie treffen kann."""
    for gruppe in GRUPPEN:
        assert _auswerten(gruppe) == gruppe


class FalscherClient:
    def __init__(self, antwort=None, wirft=None, status=200):
        self.antwort = antwort
        self.wirft = wirft
        self.status = status
        self.gesehen = None

    async def post(self, url, json=None, **kw):
        if self.wirft:
            raise self.wirft
        self.gesehen = (url, json)
        klient = self

        class Antwort:
            status_code = klient.status

            @staticmethod
            def json():
                return {"response": klient.antwort}

        return Antwort()


@pytest.mark.asyncio
async def test_das_modell_wird_gefragt_und_gehoert():
    client = FalscherClient(antwort="computer")
    assert await warengruppe(client, "http://ollama:11434",
                             "Dell UltraSharp U2723QE") == "computer"
    url, nutzlast = client.gesehen
    assert url == "http://ollama:11434/api/generate"
    assert nutzlast["stream"] is False
    # Bei dieser Aufgabe gibt es eine richtige Antwort.
    assert nutzlast["options"]["temperature"] == 0.0
    # Die Liste der erlaubten Gruppen muss mitkommen, sonst raet es frei.
    assert "elektronik" in nutzlast["system"]


@pytest.mark.asyncio
async def test_ein_nicht_erreichbares_modell_haelt_nichts_auf():
    client = FalscherClient(wirft=ConnectionError("kein Ollama da"))
    assert await warengruppe(client, "http://ollama:11434", "Irgendwas") is None


@pytest.mark.asyncio
async def test_ein_fehlerstatus_gilt_als_keine_antwort():
    client = FalscherClient(antwort="elektronik", status=500)
    assert await warengruppe(client, "http://ollama:11434", "Irgendwas") is None


@pytest.mark.asyncio
async def test_ohne_adresse_wird_gar_nicht_erst_gefragt():
    client = FalscherClient(antwort="elektronik")
    assert await warengruppe(client, "", "Irgendwas") is None
    assert client.gesehen is None


@pytest.mark.asyncio
async def test_ohne_titel_wird_nicht_gefragt():
    client = FalscherClient(antwort="elektronik")
    assert await warengruppe(client, "http://ollama:11434", "   ") is None
    assert client.gesehen is None


@pytest.mark.asyncio
async def test_ein_langer_titel_wird_gekuerzt():
    client = FalscherClient(antwort="elektronik")
    await warengruppe(client, "http://ollama:11434", "x" * 5000)
    assert len(client.gesehen[1]["prompt"]) <= 300
