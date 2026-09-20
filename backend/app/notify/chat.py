"""Chat-Kanaele: Discord, Slack, Matrix.

Discord gab es vorher nur versteckt im generischen Webhook-Kanal. Als
eigener Typ kann er zeigen, was er kann - Embed mit Bild, farbigem Rand
je nach Preisurteil und sauberen Feldern.

Verifizierungsstand: die Endpunkte sind langjaehrig dokumentiert, konnten in
der Build-Umgebung aber nicht live geprueft werden (Egress-Policy). Der Knopf
"Test senden" im UI bzw. `sparbit kanaele testen` ist die Probe.
"""
from __future__ import annotations

import html
import time
from typing import Any
from urllib.parse import quote

from ..sources.base import OptionSpec
from .base import Channel, Notification, register


class Discord(Channel):
    type = "discord"
    display_name = "Discord"
    beschreibung = ("Webhook-URL im Discord-Kanal anlegen: Kanaleinstellungen → "
                    "Integrationen → Webhooks.")

    options_schema = [
        OptionSpec("url", "Webhook-URL", "string", "",
                   help="https://discord.com/api/webhooks/…", pflicht=True),
        OptionSpec("username", "Absendername in Discord", "string", "SparBit"),
        OptionSpec("rolle", "Rolle erwähnen (optional)", "string", "",
                   help="Rollen-ID für @-Erwähnung bei SOFORT-Meldungen."),
        OptionSpec("bilder", "Bild mitschicken", "bool", True),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        url = (config.get("url") or "").strip()
        if not url:
            raise ValueError("Webhook-URL fehlt.")
        if "discord" not in url:
            raise ValueError("Das sieht nicht nach einer Discord-Webhook-URL aus.")

        embed: dict[str, Any] = {
            "title": note.kopfzeile[:250],
            "color": note.farbe,
            "fields": [{"name": name, "value": wert[:1000], "inline": name != "Preisurteil"}
                       for name, wert in note.zeilen()],
        }
        # Eine leere URL lehnt Discord ab - Hinweise haben keinen Deal-Link.
        if note.url:
            embed["url"] = note.url
        if note.beschreibung:
            embed["description"] = note.beschreibung[:400]
        if note.bild and config.get("bilder", True):
            embed["thumbnail"] = {"url": note.bild}
        if note.tags:
            embed["footer"] = {"text": " · ".join(note.tags[:5])[:200]}

        payload: dict[str, Any] = {
            "username": config.get("username") or "SparBit",
            "embeds": [embed],
        }
        # Erwaehnung nur bei SOFORT - sonst pingt jeder Fund den ganzen Server.
        rolle = str(config.get("rolle") or "").strip()
        if rolle and note.prioritaet == "SOFORT":
            payload["content"] = f"<@&{rolle}>"
            payload["allowed_mentions"] = {"roles": [rolle]}

        resp = await http.post(url, json=payload, timeout=20.0)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")


class Slack(Channel):
    type = "slack"
    display_name = "Slack"
    beschreibung = ("Incoming Webhook in Slack anlegen: api.slack.com/apps → "
                    "Incoming Webhooks.")

    options_schema = [
        OptionSpec("url", "Webhook-URL", "string", "",
                   help="https://hooks.slack.com/services/…", pflicht=True),
        OptionSpec("bilder", "Bild mitschicken", "bool", True),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        url = (config.get("url") or "").strip()
        if not url:
            raise ValueError("Webhook-URL fehlt.")

        # Ein Hinweis ueber SparBit selbst hat weder Link noch Preis.
        if note.url:
            titelzeile = f"*<{note.url}|{_slack_esc(note.kopfzeile)}>*"
        else:
            titelzeile = f"*{_slack_esc(note.kopfzeile)}*"
        unterzeile = ("" if note.ist_hinweis
                      else "\n" + _slack_esc(note.preis_text()))

        kopf: dict[str, Any] = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": titelzeile + unterzeile},
        }
        if note.bild and config.get("bilder", True):
            kopf["accessory"] = {"type": "image", "image_url": note.bild,
                                 "alt_text": "Produktbild"}

        kontext = " · ".join(f"{name}: {wert}" for name, wert in note.zeilen()[1:])
        bloecke: list[dict[str, Any]] = [kopf]
        if kontext:
            bloecke.append({"type": "context", "elements": [
                {"type": "mrkdwn", "text": _slack_esc(kontext)[:2000]}]})

        # text ist die Rueckfallanzeige in Benachrichtigungen und Suchergebnissen.
        payload = {"text": f"{note.kopfzeile} — {note.preis_text()}",
                   "blocks": bloecke}

        resp = await http.post(url, json=payload, timeout=20.0)
        if resp.status_code >= 300 or resp.text.strip() not in ("ok", ""):
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")


def _slack_esc(text: str) -> str:
    """Slack erwartet nur diese drei Zeichen maskiert."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Matrix(Channel):
    type = "matrix"
    display_name = "Matrix"
    beschreibung = ("Für eigene Matrix-Server. Zugangstoken über einen "
                    "Bot-Account, Raum-ID beginnt mit !.")

    options_schema = [
        OptionSpec("homeserver", "Homeserver", "string", "https://matrix.org",
                   help="z. B. https://matrix.example.de"),
        OptionSpec("token", "Zugangstoken", "string", "",
                   help="Access-Token des Bot-Accounts.", pflicht=True),
        OptionSpec("raum", "Raum-ID", "string", "",
                   help="!abcdef:matrix.org — nicht der Anzeigename.", pflicht=True),
        OptionSpec("bilder", "Bild verlinken", "bool", True),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        server = (config.get("homeserver") or "").rstrip("/")
        token = (config.get("token") or "").strip()
        raum = (config.get("raum") or "").strip()
        if not (server and token and raum):
            raise ValueError("Homeserver, Token und Raum-ID müssen gesetzt sein.")
        if not raum.startswith("!"):
            raise ValueError("Die Raum-ID beginnt mit '!' — der Anzeigename "
                             "(#raum:server) funktioniert hier nicht.")

        klartext = "\n".join([note.kopfzeile,
                              *(f"{name}: {wert}" for name, wert in note.zeilen()),
                              *([note.url] if note.url else [])])
        zeilen = "<br>".join(f"<b>{html.escape(name)}:</b> {html.escape(wert)}"
                             for name, wert in note.zeilen())
        # Ohne Deal-Link (Hinweis ueber SparBit selbst) kein leeres <a>.
        kopf_html = f"<b>{html.escape(note.kopfzeile)}</b>"
        if note.url:
            kopf_html = (f'<a href="{html.escape(note.url, quote=True)}">'
                         f'{kopf_html}</a>')
        formatiert = kopf_html + (f"<br>{zeilen}" if zeilen else "")
        if note.bild and config.get("bilder", True):
            formatiert += (f'<br><a href="{html.escape(note.bild, quote=True)}">'
                           f'Bild</a>')

        # Die Transaktions-ID macht den Versand wiederholbar, ohne zu doppeln.
        txn = f"sparbit{int(time.time() * 1000)}"
        url = (f"{server}/_matrix/client/v3/rooms/{quote(raum)}"
               f"/send/m.room.message/{txn}")

        resp = await http.put(
            url,
            json={"msgtype": "m.text", "body": klartext,
                  "format": "org.matrix.custom.html", "formatted_body": formatiert},
            headers={"Authorization": f"Bearer {token}"}, timeout=20.0)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")


register(Discord())
register(Slack())
register(Matrix())
