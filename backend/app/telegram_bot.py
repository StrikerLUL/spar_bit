"""Telegram-Bot: Knopfdruck und Befehle entgegennehmen.

Die Nachrichten tragen Inline-Buttons ("gemerkt", "Quelle stummschalten") -
ohne Gegenstelle passiert beim Druck darauf nichts. Dieser Worker holt die
Ereignisse per Long Polling ab. Long Polling statt Webhook, weil SparBit dann
keinen von aussen erreichbaren Port braucht: laeuft genauso auf dem Laptop
hinter einem Router wie auf einem VPS.

Befehle:
  /status     Kurzueberblick: Quellen, Treffer, Datenbank
  /neueste    die letzten 5 Deals
  /gratis     die letzten 5 Gratis-Funde
  /pause      alle Benachrichtigungen anhalten
  /weiter     wieder zustellen
  /hilfe      diese Liste
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import desc, func, select

from .db import SessionLocal, get_setting, set_setting
from .models import Channel, Deal, Match, SourceConfig, utcnow

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
SNOOZE_HOURS = 6


class TelegramBot:
    """Ein Worker je Bot-Token. Faellt er aus, laeuft SparBit normal weiter."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._offset = 0

    # --- Lebenszyklus ----------------------------------------------------

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="telegram-bot")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    # --- Hauptschleife ---------------------------------------------------

    def _token(self) -> str | None:
        """Token des ersten aktiven Telegram-Kanals."""
        with SessionLocal() as db:
            row = db.scalar(
                select(Channel).where(Channel.type == "telegram",
                                      Channel.enabled.is_(True)).limit(1))
            if not row:
                return None
            return (row.config or {}).get("bot_token") or None

    async def _run(self) -> None:
        backoff = 5
        async with httpx.AsyncClient(timeout=40.0) as client:
            while not self._stop.is_set():
                token = self._token()
                if not token:
                    # Noch kein Kanal eingerichtet - spaeter nochmal schauen.
                    await self._sleep(30)
                    continue
                try:
                    updates = await self._poll(client, token)
                    backoff = 5
                except Exception as exc:
                    log.warning("Telegram-Polling: %s", exc)
                    await self._sleep(backoff)
                    backoff = min(backoff * 2, 300)
                    continue

                for update in updates:
                    try:
                        await self._handle(client, token, update)
                    except Exception:
                        log.exception("Telegram-Update konnte nicht verarbeitet werden")

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _poll(self, client: httpx.AsyncClient, token: str) -> list[dict]:
        resp = await client.get(
            API.format(token=token, method="getUpdates"),
            params={"offset": self._offset, "timeout": 25,
                    "allowed_updates": '["message","callback_query"]'},
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description") or resp.text[:200])
        updates = data.get("result") or []
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    # --- Verarbeitung ----------------------------------------------------

    async def _handle(self, client: httpx.AsyncClient, token: str,
                      update: dict) -> None:
        if "callback_query" in update:
            await self._on_button(client, token, update["callback_query"])
        elif "message" in update:
            await self._on_message(client, token, update["message"])

    async def _on_button(self, client: httpx.AsyncClient, token: str,
                         query: dict) -> None:
        data = str(query.get("data") or "")
        antwort = "Unbekannte Aktion"

        if data.startswith("save:"):
            antwort = self._toggle_bookmark(data[5:])
        elif data.startswith("mute:"):
            antwort = self._snooze_source(data[5:])

        await client.post(API.format(token=token, method="answerCallbackQuery"),
                          json={"callback_query_id": query["id"], "text": antwort})

    def _toggle_bookmark(self, raw_id: str) -> str:
        try:
            deal_id = int(raw_id)
        except ValueError:
            return "Ungueltige Deal-ID"
        with SessionLocal() as db:
            deal = db.get(Deal, deal_id)
            if not deal:
                return "Deal nicht mehr vorhanden"
            deal.bookmarked = not deal.bookmarked
            db.commit()
            return "Gemerkt" if deal.bookmarked else "Merkung entfernt"

    def _snooze_source(self, source_id: str) -> str:
        with SessionLocal() as db:
            cfg = db.get(SourceConfig, source_id)
            if not cfg:
                return "Quelle unbekannt"
            cfg.snooze_until = utcnow() + timedelta(hours=SNOOZE_HOURS)
            db.commit()
            log.info("Quelle '%s' per Telegram fuer %dh stummgeschaltet",
                     source_id, SNOOZE_HOURS)
            return f"{source_id} fuer {SNOOZE_HOURS}h stumm"

    async def _on_message(self, client: httpx.AsyncClient, token: str,
                          message: dict) -> None:
        text = str(message.get("text") or "").strip().lower()
        chat_id = message.get("chat", {}).get("id")
        if not text.startswith("/") or chat_id is None:
            return
        command = text.split()[0].split("@")[0]

        handlers = {
            "/status": self._cmd_status,
            "/neueste": lambda: self._cmd_deals(nur_gratis=False),
            "/gratis": lambda: self._cmd_deals(nur_gratis=True),
            "/pause": lambda: self._cmd_pause(True),
            "/weiter": lambda: self._cmd_pause(False),
            "/hilfe": self._cmd_help,
            "/start": self._cmd_help,
        }
        handler = handlers.get(command)
        antwort = handler() if handler else (
            "Unbekannter Befehl. /hilfe zeigt, was ich kann.")

        await client.post(API.format(token=token, method="sendMessage"),
                          json={"chat_id": chat_id, "text": antwort,
                                "parse_mode": "HTML",
                                "link_preview_options": {"is_disabled": True}})

    # --- Befehle ---------------------------------------------------------

    def _cmd_status(self) -> str:
        with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            heute = now - timedelta(hours=24)
            cfgs = list(db.scalars(select(SourceConfig)))
            aktiv = sum(1 for c in cfgs if c.enabled)
            kaputt = sum(1 for c in cfgs
                         if c.enabled and c.circuit_open_until
                         and c.circuit_open_until > now)
            deals = db.scalar(select(func.count()).select_from(Deal)) or 0
            treffer = db.scalar(select(func.count()).select_from(Match)
                                .where(Match.created_at >= heute)) or 0
            pausiert = bool(get_setting(db, "notifications_paused"))

        return (f"<b>SparBit</b>\n"
                f"Quellen aktiv: {aktiv} ({kaputt} gesperrt)\n"
                f"Deals gesamt: {deals}\n"
                f"Treffer heute: {treffer}\n"
                f"Zustellung: {'pausiert' if pausiert else 'laeuft'}")

    def _cmd_deals(self, nur_gratis: bool) -> str:
        with SessionLocal() as db:
            stmt = select(Deal).order_by(desc(Deal.first_seen)).limit(5)
            if nur_gratis:
                stmt = stmt.where(Deal.ist_gratis.is_(True))
            rows = list(db.scalars(stmt))

        if not rows:
            return "Noch nichts gefunden."
        kopf = "<b>Neueste Gratis-Funde</b>" if nur_gratis else "<b>Neueste Deals</b>"
        zeilen = []
        for deal in rows:
            preis = "gratis" if deal.ist_gratis else (
                f"{deal.preis:.2f} {deal.waehrung}".replace(".", ",")
                if deal.preis is not None else "Preis unbekannt")
            titel = deal.titel[:70].replace("<", "&lt;").replace(">", "&gt;")
            zeilen.append(f'• <a href="{deal.url}">{titel}</a> — {preis}')
        return kopf + "\n" + "\n".join(zeilen)

    def _cmd_pause(self, pausieren: bool) -> str:
        with SessionLocal() as db:
            set_setting(db, "notifications_paused", pausieren)
            db.commit()
        log.info("Benachrichtigungen per Telegram %s",
                 "pausiert" if pausieren else "fortgesetzt")
        return ("Zustellung pausiert. /weiter hebt das wieder auf."
                if pausieren else "Zustellung laeuft wieder.")

    def _cmd_help(self) -> str:
        return ("<b>SparBit</b>\n"
                "/status — Quellen, Treffer, Datenbank\n"
                "/neueste — die letzten 5 Deals\n"
                "/gratis — die letzten 5 Gratis-Funde\n"
                "/pause — Zustellung anhalten\n"
                "/weiter — Zustellung fortsetzen\n"
                "/hilfe — diese Liste\n\n"
                "Unter jeder Meldung kannst du sie merken oder die Quelle "
                f"fuer {SNOOZE_HOURS} Stunden stummschalten.")


bot = TelegramBot()
