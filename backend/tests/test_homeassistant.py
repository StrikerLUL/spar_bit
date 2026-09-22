"""Home Assistant ueber MQTT.

Das Versprechen des Kanals ist „kein Basteln drueben": ein Sensor
erscheint von selbst. Das haengt an genau zwei Nutzlasten - der
Discovery-Beschreibung und dem Zustand -, und wenn eine davon nicht
stimmt, erscheint drueben nichts und niemand sieht warum.

Geprueft wird darum, was auf die Leitung geht, ohne dass ein Broker
laeuft.
"""
import json

import pytest

from app.notify import Notification, get_channel


@pytest.fixture
def kanal():
    return get_channel("homeassistant")


@pytest.fixture
def note():
    return Notification(
        titel="LEGO Technic Bagger", url="https://shop.test/1",
        quelle="mydealz", regel="Lego", preis=49.99, originalpreis=99.99,
        waehrung="EUR", preis_eur=49.99, haendler="Amazon",
        urteil="bestpreis", urteil_text="So günstig war es noch nie",
        fehler_stufe="heiss", fehler_text="Kommastelle verrutscht",
        gutschein_code="SOMMER25", prioritaet="SOFORT")


def test_der_kanal_ist_registriert(kanal):
    assert kanal is not None
    assert kanal.display_name and kanal.beschreibung
    assert {f.key for f in kanal.options_schema} >= {"host", "port", "kennung"}


def test_discovery_beschreibt_einen_sensor(kanal):
    thema, nutzlast = kanal.discovery({"kennung": "sparbit"})
    assert thema == "homeassistant/sensor/sparbit/deal/config"
    # Ohne unique_id legt Home Assistant keine Entitaet an, die man
    # umbenennen oder einem Raum zuordnen kann.
    assert nutzlast["unique_id"] == "sparbit_letzter_deal"
    assert nutzlast["state_topic"] == "sparbit/sparbit/deal"
    assert nutzlast["json_attributes_topic"] == nutzlast["state_topic"]
    assert nutzlast["device"]["identifiers"] == ["sparbit"]


def test_ein_eigener_praefix_wird_beachtet(kanal):
    thema, _ = kanal.discovery({"kennung": "keller",
                                "discovery_praefix": "ha/"})
    assert thema == "ha/sensor/keller/deal/config"


def test_die_kennung_wird_entschaerft(kanal):
    """Ein '/' in der Kennung wuerde das Thema aufspalten und den Sensor
    an einer Stelle anlegen, die niemand sucht."""
    thema, _ = kanal.discovery({"kennung": "haus/keller"})
    assert thema == "homeassistant/sensor/hauskeller/deal/config"


def test_leere_kennung_faellt_auf_die_vorgabe_zurueck(kanal):
    thema, _ = kanal.discovery({"kennung": "   "})
    assert "/sparbit/" in thema


def test_der_zustand_traegt_alles_mit_was_man_drueben_braucht(kanal, note):
    _, nutzlast = kanal.zustand({}, note)
    assert nutzlast["titel"] == "LEGO Technic Bagger"
    assert nutzlast["preis"] == 49.99
    assert nutzlast["url"] == "https://shop.test/1"
    assert nutzlast["urteil"] == "bestpreis"
    assert nutzlast["gutschein_code"] == "SOMMER25"
    # Die beiden Felder, fuer die man drueben eine Automation baut.
    assert nutzlast["ist_preisfehler"] is True
    assert nutzlast["prioritaet"] == "SOFORT"


def test_der_zustand_bleibt_unter_der_grenze_von_home_assistant(kanal):
    """Ueber 255 Zeichen verwirft Home Assistant den Zustand stillschweigend."""
    lang = Notification(titel="x" * 900, url="https://shop.test/1",
                        quelle="mydealz")
    _, nutzlast = kanal.zustand({}, lang)
    assert len(nutzlast["titel"]) <= 255


def test_beide_nutzlasten_sind_gueltiges_json(kanal, note):
    for thema, nutzlast in (kanal.discovery({}), kanal.zustand({}, note)):
        assert thema
        json.dumps(nutzlast, ensure_ascii=False)      # wirft, wenn nicht


def test_ohne_broker_gibt_es_eine_klare_meldung(kanal, note):
    import anyio

    async def lauf():
        await kanal.send({"host": ""}, note, None)

    with pytest.raises(ValueError, match="MQTT-Broker"):
        anyio.run(lauf)
