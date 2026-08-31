"""Benachrichtigungs-Kanaele als Plugins."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..sources.base import OptionSpec


@dataclass
class Notification:
    titel: str
    url: str
    quelle: str
    regel: str = ""
    preis: float | None = None
    originalpreis: float | None = None
    rabatt_prozent: float | None = None
    waehrung: str = "EUR"
    haendler: str | None = None
    bild: str | None = None
    ist_gratis: bool = False
    beschreibung: str | None = None
    deal_id: int | None = None
    prioritaet: str = "NORMAL"
    tags: list[str] = field(default_factory=list)

    def preis_text(self) -> str:
        sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(self.waehrung, self.waehrung)
        if self.ist_gratis or (self.preis is not None and self.preis <= 0.009):
            base = "GRATIS"
        elif self.preis is not None:
            base = f"{self.preis:.2f} {sym}".replace(".", ",")
        else:
            base = "Preis unbekannt"
        if self.originalpreis and self.preis is not None and self.originalpreis > self.preis:
            was = f"{self.originalpreis:.2f} {sym}".replace(".", ",")
            base += f"  (statt {was})"
        if self.rabatt_prozent:
            base += f"  -{self.rabatt_prozent:.0f}%"
        return base


class Channel(ABC):
    type: str
    display_name: str
    beschreibung: str = ""
    options_schema: list[OptionSpec] = []
    supports_buttons: bool = False

    @abstractmethod
    async def send(self, config: dict[str, Any], note: Notification,
                   http: Any) -> None:
        """Sendet. Wirft bei Fehler - der Aufrufer loggt."""

    async def send_test(self, config: dict[str, Any], http: Any) -> None:
        await self.send(config, Notification(
            titel="SparBit Testnachricht",
            url="https://github.com/StrikerLUL/spar_bit",
            quelle="system",
            regel="Test",
            preis=0.0,
            originalpreis=49.99,
            rabatt_prozent=100.0,
            ist_gratis=True,
            haendler="SparBit",
            beschreibung="Wenn du das liest, funktioniert der Kanal.",
        ), http)


_CHANNELS: dict[str, Channel] = {}


def register(channel: Channel) -> Channel:
    _CHANNELS[channel.type] = channel
    return channel


def get_channel(ctype: str) -> Channel | None:
    return _CHANNELS.get(ctype)


def all_channels() -> list[Channel]:
    return sorted(_CHANNELS.values(), key=lambda c: c.display_name)
