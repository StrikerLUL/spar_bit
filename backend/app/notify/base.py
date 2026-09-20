"""Benachrichtigungs-Kanaele als Plugins."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .. import money
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
    # Preis in EUR, falls die Quelle in Fremdwaehrung liefert. Steht in der
    # Meldung als Hinweis dabei, damit der Betrag vergleichbar bleibt.
    preis_eur: float | None = None
    haendler: str | None = None
    bild: str | None = None
    ist_gratis: bool = False
    beschreibung: str | None = None
    deal_id: int | None = None
    prioritaet: str = "NORMAL"
    tags: list[str] = field(default_factory=list)
    # Preisurteil aus dem eigenen Verlauf - das Interessanteste an der
    # Meldung, darum tragen es alle Kanaele mit.
    urteil: str | None = None
    urteil_text: str | None = None
    # Preisfehler-Verdacht (siehe app/pricefehler.py). Steht ganz oben in der
    # Meldung, weil er das Einzige ist, worauf man sofort reagieren muss.
    fehler_stufe: str | None = None
    fehler_text: str | None = None

    @property
    def ist_preisfehler(self) -> bool:
        return self.fehler_stufe == "heiss"

    @property
    def kopfzeile(self) -> str:
        """Eine Zeile, die sagt worum es geht - fuer Kanaele ohne Formatierung."""
        if self.ist_preisfehler:
            return f"PREISFEHLER: {self.titel}"
        if self.ist_gratis:
            return f"GRATIS: {self.titel}"
        if self.urteil == "bestpreis":
            return f"Bestpreis: {self.titel}"
        return self.titel

    @property
    def farbe(self) -> int:
        """Akzentfarbe als 24-Bit-Zahl, fuer Discord und Slack."""
        if self.ist_preisfehler:
            return 0xD64545          # rot - hier zaehlt jede Minute
        if self.ist_gratis or self.urteil == "bestpreis":
            return 0x22C55E          # gruen
        if self.urteil == "uvp_fragwuerdig":
            return 0xEF4444
        if self.prioritaet == "SOFORT":
            return 0xF59E0B          # gelb
        return 0x3987E5              # blau

    def zeilen(self) -> list[tuple[str, str]]:
        """Die Eckdaten als Feld/Wert-Paare - jeder Kanal formatiert sie selbst."""
        raus = []
        if self.fehler_text:
            raus.append(("Preisfehler", self.fehler_text))
        raus.append(("Preis", self.preis_text()))
        if self.haendler:
            raus.append(("Händler", self.haendler))
        raus.append(("Quelle", self.quelle))
        if self.regel:
            raus.append(("Regel", self.regel))
        if self.urteil_text:
            raus.append(("Preisurteil", self.urteil_text))
        return raus

    def preis_text(self) -> str:
        """Die Preiszeile einer Meldung.

        Geht ueber app.money, damit eine Telegram-Nachricht denselben Betrag
        zeigt wie die Deal-Karte im Browser. Bei Fremdwaehrung steht der
        EUR-Gegenwert dabei - ohne ihn kann man "$ 9.99" nicht mit dem
        eigenen Preislimit vergleichen.
        """
        if self.ist_gratis or (self.preis is not None and self.preis <= 0.009):
            base = "GRATIS"
        else:
            base = money.preiszeile(self.preis, self.waehrung, eur=self.preis_eur)
        if (self.originalpreis and self.preis is not None
                and self.originalpreis > self.preis and not self.ist_gratis):
            base += f"  (statt {money.betrag(self.originalpreis, self.waehrung)})"
        elif self.ist_gratis and self.originalpreis:
            base += f"  (statt {money.betrag(self.originalpreis, self.waehrung)})"
        if self.rabatt_prozent and not self.ist_gratis:
            base += f"  {money.rabatt_text(self.rabatt_prozent)}"
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
