"""Home Assistant ueber MQTT - mit Auto-Discovery.

Es gab schon einen Weg nach Home Assistant: den Webhook-Kanal. Der
funktioniert, verlangt aber, dass man drueben von Hand eine Automation
baut, das JSON auseinandernimmt und daraus einen Sensor bastelt. Das ist
eine halbe Stunde Arbeit fuer etwas, das MQTT von sich aus kann.

Hier passiert stattdessen zweierlei:

1. **Discovery.** Beim ersten Senden legt SparBit eine Beschreibung
   seiner selbst auf `homeassistant/sensor/...`. Home Assistant liest
   sie und hat danach einen Sensor „SparBit Letzter Deal" - ohne dass
   drueben irgendetwas konfiguriert wird.

2. **Zustand.** Jede Meldung schreibt den Titel als Zustand und alles
   Weitere (Preis, Haendler, Urteil, Link, Bild) als Attribute. Damit
   laesst sich drueben alles bauen: eine Karte im Dashboard, eine
   Automation „bei Preisfehler das Licht rot", eine Benachrichtigung.

Beides mit `retain`: wer Home Assistant neu startet, sieht sofort
wieder den letzten Fund statt „unbekannt", bis der naechste kommt.

`paho-mqtt` ist optional. Fehlt es, meldet sich der Kanal mit einem
Klartext-Hinweis, statt beim Start alles mitzureissen - genauso wie
Pillow und cryptography an anderer Stelle.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anyio

from ..sources.base import OptionSpec
from .base import Channel, Notification, register

log = logging.getLogger(__name__)

# Eindeutig je Anlage, damit zwei SparBits an einem Broker sich nicht
# gegenseitig die Sensoren ueberschreiben. Faellt ueber die Option
# "kennung" auseinander.
DISCOVERY_VORLAGE = "{praefix}/sensor/{kennung}/deal/config"
ZUSTAND_VORLAGE = "sparbit/{kennung}/deal"

# MQTT erlaubt 268 MB je Nachricht, Home Assistant deutlich weniger
# geduldig. Der Titel ist der Zustand, und ein Zustand darf dort
# hoechstens 255 Zeichen lang sein - laenger, und der Sensor wird
# stillschweigend verworfen.
ZUSTAND_MAX = 255


def _paho():
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:                    # pragma: no cover
        raise RuntimeError(
            "Fuer den Home-Assistant-Kanal fehlt das Paket 'paho-mqtt'. "
            "Nachinstallieren mit: pip install paho-mqtt — im Docker-Image "
            "ist es enthalten.") from exc
    return mqtt


class HomeAssistantChannel(Channel):
    type = "homeassistant"
    display_name = "Home Assistant (MQTT)"
    beschreibung = ("Legt in Home Assistant von selbst einen Sensor an "
                    "(MQTT-Discovery) und schreibt jeden Fund mit Preis, "
                    "Urteil und Link hinein. Kein Basteln drueben.")

    options_schema = [
        OptionSpec("host", "MQTT-Broker", "string", "", pflicht=True,
                   help="Adresse des Brokers, z. B. die IP von Home Assistant."),
        OptionSpec("port", "Port", "int", 1883),
        OptionSpec("username", "Benutzer", "string", ""),
        OptionSpec("password", "Passwort", "string", ""),
        OptionSpec("tls", "TLS", "bool", False),
        OptionSpec("kennung", "Kennung dieser Anlage", "string", "sparbit",
                   help="Nur aendern, wenn zwei SparBits denselben Broker "
                        "nutzen — sonst ueberschreiben sie sich den Sensor."),
        OptionSpec("discovery_praefix", "Discovery-Präfix", "string",
                   "homeassistant",
                   help="Nur aendern, wenn in Home Assistant ein anderer "
                        "Praefix eingestellt ist."),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        # paho ist blockierend - wie smtplib gehoert es in einen Thread.
        await anyio.to_thread.run_sync(self._senden, config, note)

    # --- Nutzlasten ------------------------------------------------------

    @staticmethod
    def _kennung(config: dict) -> str:
        roh = (config.get("kennung") or "sparbit").strip() or "sparbit"
        # MQTT-Topics vertragen kein '/' oder '+' mitten in der Kennung.
        return "".join(z for z in roh if z.isalnum() or z in "-_") or "sparbit"

    @classmethod
    def discovery(cls, config: dict) -> tuple[str, dict]:
        kennung = cls._kennung(config)
        praefix = (config.get("discovery_praefix") or "homeassistant").strip("/")
        thema = DISCOVERY_VORLAGE.format(praefix=praefix, kennung=kennung)
        nutzlast = {
            "name": "Letzter Deal",
            "unique_id": f"{kennung}_letzter_deal",
            "state_topic": ZUSTAND_VORLAGE.format(kennung=kennung),
            "value_template": "{{ value_json.titel }}",
            "json_attributes_topic": ZUSTAND_VORLAGE.format(kennung=kennung),
            "icon": "mdi:tag-search",
            # Damit drueben ein Geraet daraus wird und nicht eine lose
            # Entitaet - so laesst es sich in einem Raum einsortieren.
            "device": {
                "identifiers": [kennung],
                "name": "SparBit",
                "manufacturer": "SparBit",
                "model": "Deal-Monitor",
            },
        }
        return thema, nutzlast

    @classmethod
    def zustand(cls, config: dict, note: Notification) -> tuple[str, dict]:
        thema = ZUSTAND_VORLAGE.format(kennung=cls._kennung(config))
        nutzlast = {
            "titel": (note.titel or "")[:ZUSTAND_MAX],
            "url": note.url,
            "preis": note.preis,
            "preis_eur": note.preis_eur,
            "originalpreis": note.originalpreis,
            "rabatt_prozent": note.rabatt_prozent,
            "waehrung": note.waehrung,
            "preis_text": note.preis_text(),
            "haendler": note.haendler,
            "quelle": note.quelle,
            "regel": note.regel,
            "prioritaet": note.prioritaet,
            "ist_gratis": note.ist_gratis,
            "urteil": note.urteil,
            "urteil_text": note.urteil_text,
            # Die beiden Felder, fuer die man drueben eine Automation
            # baut: "wenn Preisfehler, dann laut".
            "ist_preisfehler": note.ist_preisfehler,
            "fehler_text": note.fehler_text,
            "gutschein_code": note.gutschein_code,
            "bild": note.bild,
            "deal_id": note.deal_id,
            "entity_picture": note.bild,
        }
        return thema, nutzlast

    # --- Verbindung ------------------------------------------------------

    def _senden(self, config: dict[str, Any], note: Notification) -> None:
        mqtt = _paho()
        host = (config.get("host") or "").strip()
        if not host:
            raise ValueError("MQTT-Broker fehlt.")

        # Callback-API v2: v1 ist in paho 2.x abgekuendigt und wuerde
        # beim naechsten Update eine Warnung pro Meldung schreiben.
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:                    # paho 1.x
            client = mqtt.Client()

        if config.get("username"):
            client.username_pw_set(config.get("username"),
                                   config.get("password") or None)
        if config.get("tls"):
            client.tls_set()

        client.connect(host, int(config.get("port") or 1883), keepalive=30)
        client.loop_start()
        try:
            # Discovery bei jeder Meldung, nicht nur beim ersten Mal:
            # sie ist retained und idempotent, und so erscheint der
            # Sensor auch nach einem geloeschten Broker-Zustand wieder,
            # ohne dass jemand "Test senden" druecken muss.
            for thema, nutzlast in (self.discovery(config),
                                    self.zustand(config, note)):
                ergebnis = client.publish(
                    thema, json.dumps(nutzlast, ensure_ascii=False),
                    qos=1, retain=True)
                ergebnis.wait_for_publish(timeout=15)
                if not ergebnis.is_published():
                    raise RuntimeError(f"MQTT hat '{thema}' nicht bestaetigt.")
        finally:
            client.loop_stop()
            try:
                client.disconnect()
            except Exception:
                pass


register(HomeAssistantChannel())
