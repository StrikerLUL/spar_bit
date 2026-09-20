"""Telegram - der primaere Kanal. Mit Bild, Preis, Direktlink und Buttons."""
from __future__ import annotations

import html
from typing import Any

from ..sources.base import OptionSpec
from .base import Channel, Notification, Sammelmeldung, register

API = "https://api.telegram.org/bot{token}/{method}"


def _esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)


class Telegram(Channel):
    type = "telegram"
    display_name = "Telegram"
    beschreibung = "Bot via BotFather anlegen, Token + eigene Chat-ID eintragen."
    supports_buttons = True

    options_schema = [
        OptionSpec("bot_token", "Bot-Token", "string", "",
                   help="Von @BotFather. Format 123456:ABC-DEF...", pflicht=True),
        OptionSpec("chat_id", "Chat-ID", "string", "",
                   help="Deine numerische ID (via @userinfobot) oder @kanalname.", pflicht=True),
        OptionSpec("bilder", "Bilder mitschicken", "bool", True),
        OptionSpec("stumm", "Stumm zustellen", "bool", False,
                   help="Wird bei SOFORT-Prioritaet ignoriert."),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        token = (config.get("bot_token") or "").strip()
        chat_id = str(config.get("chat_id") or "").strip()
        if not token or not chat_id:
            raise ValueError("bot_token und chat_id muessen gesetzt sein.")

        text = self.render(note)
        silent = bool(config.get("stumm")) and note.prioritaet != "SOFORT"
        buttons = self._buttons(note)

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "disable_notification": silent,
            "reply_markup": {"inline_keyboard": buttons},
        }

        use_photo = bool(config.get("bilder", True)) and note.bild
        if use_photo:
            method = "sendPhoto"
            payload |= {"photo": note.bild, "caption": text, "parse_mode": "HTML"}
        else:
            method = "sendMessage"
            payload |= {"text": text, "parse_mode": "HTML",
                        "link_preview_options": {"is_disabled": False}}

        resp = await http.post(API.format(token=token, method=method),
                                       json=payload, timeout=20.0)
        data = self._json(resp)
        if not data.get("ok"):
            # Bild kaputt/zu gross -> als Textnachricht nachreichen statt scheitern.
            if use_photo:
                payload.pop("photo", None)
                payload.pop("caption", None)
                payload |= {"text": text, "parse_mode": "HTML"}
                resp = await http.post(
                    API.format(token=token, method="sendMessage"),
                    json=payload, timeout=20.0)
                data = self._json(resp)
                if data.get("ok"):
                    return
            raise RuntimeError(
                f"Telegram API: {data.get('description') or resp.text[:200]}")

    @staticmethod
    def _json(resp) -> dict:
        try:
            return resp.json()
        except Exception:
            return {"ok": False, "description": resp.text[:200]}

    def render(self, note: Notification) -> str:
        head = "🎁 <b>GRATIS</b>" if note.ist_gratis else "🔥 <b>Deal</b>"
        if note.prioritaet == "SOFORT":
            head = "⚡ " + head
        lines = [f"{head}  {_esc(note.titel)}", "", f"💶 <b>{_esc(note.preis_text())}</b>"]
        if note.haendler:
            lines.append(f"🏬 {_esc(note.haendler)}")
        lines.append(f"📡 {_esc(note.quelle)}" + (f" · Regel: {_esc(note.regel)}"
                                                  if note.regel else ""))
        if note.beschreibung:
            snippet = note.beschreibung[:280]
            if len(note.beschreibung) > 280:
                snippet += "…"
            lines += ["", f"<i>{_esc(snippet)}</i>"]
        if note.url:
            lines += ["",
                      f'<a href="{html.escape(note.url, quote=True)}">➡️ Zum Deal</a>']
        return "\n".join(lines)

    async def send_sammel(self, config: dict[str, Any],
                          sammel: Sammelmeldung, http: Any) -> None:
        """Eine Nachricht mit allen Funden statt zwanzig einzelnen."""
        if sammel.anzahl == 1:
            await self.send(config, sammel.meldungen[0], http)
            return

        token = (config.get("bot_token") or "").strip()
        chat_id = str(config.get("chat_id") or "").strip()
        if not token or not chat_id:
            raise ValueError("bot_token und chat_id muessen gesetzt sein.")

        zeilen = [f"<b>{_esc(sammel.titel)}</b>", ""]
        for note in sammel.beste[:20]:
            marke = ("‼️" if note.ist_preisfehler else
                     "🎁" if note.ist_gratis else
                     "🏆" if note.urteil == "bestpreis" else "•")
            name = _esc(note.titel[:90])
            if note.url:
                name = f'<a href="{html.escape(note.url, quote=True)}">{name}</a>'
            zeilen.append(f"{marke} {name}\n   {_esc(note.preis_text())}")
        rest = sammel.anzahl - min(sammel.anzahl, 20)
        if rest:
            zeilen.append(f"\n<i>… und {rest} weitere</i>")

        # Telegram nimmt 4096 Zeichen; lieber kuerzen als scheitern.
        text = "\n".join(zeilen)[:4000]

        resp = await http.post(
            API.format(token=token, method="sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "link_preview_options": {"is_disabled": True},
                  "disable_notification": bool(config.get("stumm"))},
            timeout=20.0)
        data = self._json(resp)
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API: {data.get('description') or resp.text[:200]}")

    @staticmethod
    def _buttons(note: Notification) -> list[list[dict]]:
        # Telegram lehnt einen Knopf ohne URL ab - ein Hinweis ueber SparBit
        # selbst hat keinen Deal, zu dem er fuehren koennte.
        row1 = [{"text": "🔗 Zum Deal", "url": note.url}] if note.url else []
        row2 = []
        if note.deal_id:
            row2.append({"text": "⭐ Gemerkt",
                         "callback_data": f"save:{note.deal_id}"})
        if note.quelle:
            row2.append({"text": "🔇 Quelle stumm",
                         "callback_data": f"mute:{note.quelle}"})

        # Nur bei Preisfehlern: hier ist die Rueckmeldung wertvoll, weil die
        # Gewichte des Waechters sonst nie an der Wirklichkeit geeicht werden.
        row3 = []
        if note.ist_preisfehler and note.deal_id:
            row3 = [{"text": "✅ Echter Fehler",
                     "callback_data": f"echt:{note.deal_id}"},
                    {"text": "🚫 Fehlalarm",
                     "callback_data": f"falsch:{note.deal_id}"}]
        return [r for r in (row1, row2, row3) if r]


register(Telegram())
