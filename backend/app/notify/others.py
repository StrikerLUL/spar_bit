"""Weitere Kanaele: SMTP, Webhook/Discord, ntfy."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

import anyio

from ..sources.base import OptionSpec
from .base import Channel, Notification, register


class SMTPChannel(Channel):
    type = "smtp"
    display_name = "E-Mail (SMTP)"
    beschreibung = "Klassische Mail. Bei Gmail App-Passwort verwenden."

    options_schema = [
        OptionSpec("host", "SMTP-Host", "string", ""),
        OptionSpec("port", "Port", "int", 587),
        OptionSpec("username", "Benutzer", "string", ""),
        OptionSpec("password", "Passwort", "string", ""),
        OptionSpec("from_addr", "Absender", "string", ""),
        OptionSpec("to_addr", "Empfaenger", "string", ""),
        OptionSpec("tls", "STARTTLS", "bool", True),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        # smtplib ist blockierend -> in einen Worker-Thread.
        await anyio.to_thread.run_sync(self._send_sync, config, note)

    def _send_sync(self, config: dict[str, Any], note: Notification) -> None:
        host = (config.get("host") or "").strip()
        if not host:
            raise ValueError("SMTP-Host fehlt.")
        to_addr = (config.get("to_addr") or "").strip()
        from_addr = (config.get("from_addr") or config.get("username") or "").strip()
        if not to_addr or not from_addr:
            raise ValueError("Absender und Empfaenger muessen gesetzt sein.")

        msg = EmailMessage()
        prefix = "[GRATIS] " if note.ist_gratis else "[Deal] "
        msg["Subject"] = (prefix + note.titel)[:200]
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(
            f"{note.titel}\n\n{note.preis_text()}\n"
            f"Haendler: {note.haendler or '-'}\n"
            f"Quelle: {note.quelle}\nRegel: {note.regel}\n\n"
            f"{note.beschreibung or ''}\n\n{note.url}\n"
        )

        port = int(config.get("port") or 587)
        password = config.get("password") or ""
        username = config.get("username") or ""

        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=25,
                                  context=ssl.create_default_context()) as srv:
                if username:
                    srv.login(username, password)
                srv.send_message(msg)
            return

        with smtplib.SMTP(host, port, timeout=25) as srv:
            if config.get("tls", True):
                srv.starttls(context=ssl.create_default_context())
            if username:
                srv.login(username, password)
            srv.send_message(msg)


class WebhookChannel(Channel):
    type = "webhook"
    display_name = "Webhook / Discord"
    beschreibung = ("Discord-Webhook-URL erkennt SparBit automatisch und schickt "
                    "ein Embed. Andere URLs bekommen generisches JSON.")

    options_schema = [
        OptionSpec("url", "Webhook-URL", "string", ""),
        OptionSpec("username", "Anzeigename (Discord)", "string", "SparBit"),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        url = (config.get("url") or "").strip()
        if not url:
            raise ValueError("Webhook-URL fehlt.")

        if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
            payload = self._discord(config, note)
        else:
            payload = {
                "titel": note.titel, "url": note.url, "preis": note.preis,
                "originalpreis": note.originalpreis,
                "rabatt_prozent": note.rabatt_prozent, "waehrung": note.waehrung,
                "haendler": note.haendler, "quelle": note.quelle,
                "regel": note.regel, "ist_gratis": note.ist_gratis,
                "bild": note.bild, "prioritaet": note.prioritaet,
            }

        resp = await http._client.post(url, json=payload, timeout=20.0)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    @staticmethod
    def _discord(config: dict, note: Notification) -> dict:
        embed = {
            "title": note.titel[:250],
            "url": note.url,
            "color": 0x22C55E if note.ist_gratis else 0xF59E0B,
            "fields": [
                {"name": "Preis", "value": note.preis_text(), "inline": True},
                {"name": "Quelle", "value": note.quelle, "inline": True},
            ],
        }
        if note.haendler:
            embed["fields"].append({"name": "Haendler", "value": note.haendler[:100],
                                    "inline": True})
        if note.beschreibung:
            embed["description"] = note.beschreibung[:400]
        if note.bild:
            embed["thumbnail"] = {"url": note.bild}
        if note.regel:
            embed["footer"] = {"text": f"Regel: {note.regel}"}
        return {"username": config.get("username") or "SparBit", "embeds": [embed]}


class NtfyChannel(Channel):
    type = "ntfy"
    display_name = "ntfy"
    beschreibung = "Push ohne eigenen Bot. ntfy.sh oder eigene Instanz."

    options_schema = [
        OptionSpec("server", "Server", "string", "https://ntfy.sh"),
        OptionSpec("topic", "Topic", "string", ""),
        OptionSpec("token", "Access-Token (optional)", "string", ""),
        OptionSpec("prioritaet", "ntfy-Prioritaet", "select", "default",
                   choices=["min", "low", "default", "high", "urgent"]),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        topic = (config.get("topic") or "").strip()
        if not topic:
            raise ValueError("ntfy-Topic fehlt.")
        server = (config.get("server") or "https://ntfy.sh").rstrip("/")

        prio = config.get("prioritaet") or "default"
        if note.prioritaet == "SOFORT" and prio in ("min", "low", "default"):
            prio = "high"

        headers = {
            "Title": self._ascii(("GRATIS: " if note.ist_gratis else "Deal: ")
                                 + note.titel)[:180],
            "Priority": prio,
            "Tags": "gift" if note.ist_gratis else "fire",
            "Actions": f"view, Zum Deal, {note.url}",
            "Markdown": "yes",
        }
        if config.get("token"):
            headers["Authorization"] = f"Bearer {config['token']}"
        if note.bild:
            headers["Attach"] = note.bild

        body = (f"**{note.preis_text()}**\n\n"
                f"{note.haendler or ''} · {note.quelle}\n\n{note.url}")

        resp = await http._client.post(f"{server}/{topic}", content=body.encode("utf-8"),
                                       headers=headers, timeout=20.0)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    @staticmethod
    def _ascii(text: str) -> str:
        # ntfy-Header muessen latin-1-safe sein.
        return text.encode("latin-1", "replace").decode("latin-1")


register(SMTPChannel())
register(WebhookChannel())
register(NtfyChannel())
