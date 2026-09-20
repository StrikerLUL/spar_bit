"""Push-Dienste: Gotify und Pushover.

Gotify laeuft auf dem eigenen Server - passt zum selbstgehosteten Ansatz und
schickt keine Daten an Dritte. Pushover ist ein bezahlter Dienst, dafuer ohne
eigene Infrastruktur.

Verifizierungsstand wie bei den Chat-Kanaelen: dokumentierte Endpunkte, in der
Build-Umgebung nicht live pruefbar. "Test senden" ist die Probe.
"""
from __future__ import annotations

from typing import Any

from ..sources.base import OptionSpec
from .base import Channel, Notification, register


class Gotify(Channel):
    type = "gotify"
    display_name = "Gotify (selbst gehostet)"
    beschreibung = ("Eigener Push-Server. In Gotify eine Anwendung anlegen und "
                    "deren Token hier eintragen.")

    options_schema = [
        OptionSpec("server", "Server", "string", "",
                   help="z. B. https://gotify.example.de", pflicht=True),
        OptionSpec("token", "App-Token", "string", "",
                   help="Der Token der Anwendung, nicht der des Clients.", pflicht=True),
        OptionSpec("prioritaet", "Priorität", "int", 5,
                   help="0–10. Ab 8 klingelt es auf den meisten Geräten."),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        server = (config.get("server") or "").rstrip("/")
        token = (config.get("token") or "").strip()
        if not (server and token):
            raise ValueError("Server und App-Token müssen gesetzt sein.")

        try:
            prio = int(config.get("prioritaet", 5))
        except (TypeError, ValueError):
            prio = 5
        if note.prioritaet == "SOFORT":
            prio = max(prio, 8)

        text = "\n".join([*(f"{name}: {wert}" for name, wert in note.zeilen()),
                          *(["", note.url] if note.url else [])])
        if not text.strip():
            text = note.titel

        resp = await http.post(
            f"{server}/message",
            params={"token": token},
            json={
                "title": note.kopfzeile[:250],
                "message": text,
                "priority": max(0, min(10, prio)),
                # Klickbarer Link und Markdown - beides versteht Gotify ueber extras.
                "extras": {
                    "client::display": {"contentType": "text/markdown"},
                    **({"client::notification": {"click": {"url": note.url}}}
                       if note.url else {}),
                },
            },
            timeout=20.0)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")


class Pushover(Channel):
    type = "pushover"
    display_name = "Pushover"
    beschreibung = ("Push-Dienst für iOS und Android. Benutzerschlüssel und "
                    "einen Anwendungs-Token auf pushover.net anlegen.")

    options_schema = [
        OptionSpec("token", "Anwendungs-Token", "string", "",
                   help="Von pushover.net/apps/build.", pflicht=True),
        OptionSpec("user", "Benutzerschlüssel", "string", "",
                   help="Steht auf der Startseite nach dem Anmelden.", pflicht=True),
        OptionSpec("geraet", "Nur dieses Gerät (optional)", "string", ""),
        OptionSpec("ton", "Ton", "string", "",
                   help="Leer = Standardton des Geräts."),
    ]

    ENDPUNKT = "https://api.pushover.net/1/messages.json"

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        token = (config.get("token") or "").strip()
        user = (config.get("user") or "").strip()
        if not (token and user):
            raise ValueError("Anwendungs-Token und Benutzerschlüssel müssen "
                             "gesetzt sein.")

        daten = {
            "token": token,
            "user": user,
            "title": note.kopfzeile[:250],
            "message": ("\n".join(f"{name}: {wert}" for name, wert in note.zeilen())
                        or note.titel),
            # 1 = hoch (Ton auch im Stillmodus-Zeitplan), 0 = normal.
            "priority": 1 if note.prioritaet == "SOFORT" else 0,
            # Pushover lehnt url_title ohne url ab.
            **({"url": note.url, "url_title": "Zum Deal"} if note.url else {}),
        }
        if config.get("geraet"):
            daten["device"] = str(config["geraet"])[:100]
        if config.get("ton"):
            daten["sound"] = str(config["ton"])[:40]

        resp = await http.post(self.ENDPUNKT, data=daten, timeout=20.0)
        try:
            antwort = resp.json()
        except Exception:
            antwort = {}
        if resp.status_code >= 300 or antwort.get("status") != 1:
            fehler = ", ".join(antwort.get("errors") or []) or resp.text[:200]
            raise RuntimeError(f"Pushover: {fehler}")


register(Gotify())
register(Pushover())
