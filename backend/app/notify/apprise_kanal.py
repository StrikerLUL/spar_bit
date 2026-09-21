"""Apprise als Sammelanschluss: ein Kanal, hundert Dienste.

SparBit bringt neun Kanaele mit, und jeder einzelne war Arbeit: Format
lesen, Felder definieren, Fehler uebersetzen. Fuer Signal, Matrix-Bruecken,
Home Assistant, Mastodon, Teams, Zulip, SMS-Anbieter und den Rest waere
das jeweils dasselbe nochmal.

Apprise loest genau dieses Problem und kennt ueber hundert Dienste ueber
eine Adresszeile: `signal://`, `mqtt://`, `tgram://`, `mailto://`. Wer
den Dienst betreibt, kennt die Adresse ohnehin aus dessen Doku.

Bewusst **optional**: Apprise ist kein Teil der Abhaengigkeiten. Fehlt
das Paket, ist der Kanal sichtbar, sagt aber klar, was zu tun ist -
statt in der Liste zu fehlen und Raetsel aufzugeben.

    pip install apprise

Der Aufruf laeuft in einem Worker-Thread: Apprise ist synchron, und ein
blockierender Versand haette den ganzen Scheduler angehalten.
"""
from __future__ import annotations

import logging
from typing import Any

import anyio

from ..sources.base import OptionSpec
from .base import Channel, Notification, register

log = logging.getLogger(__name__)

HINWEIS = ("Das Paket 'apprise' ist nicht installiert. "
           "Im Container: pip install apprise, dann neu starten.")


def verfuegbar() -> bool:
    try:
        import apprise  # noqa: F401
        return True
    except ImportError:
        return False


class AppriseChannel(Channel):
    type = "apprise"
    display_name = "Apprise (über 100 Dienste)"
    beschreibung = ("Ein Kanal für alles, was Apprise kennt: Signal, Matrix, "
                    "Home Assistant, Mastodon, Teams, SMS und mehr. Adresse "
                    "aus der Apprise-Doku eintragen, z. B. "
                    "signal://…, mqtt://…, tgram://…")
    docs_url = "https://github.com/caronc/apprise/wiki"

    options_schema = [
        OptionSpec("urls", "Apprise-Adressen", "list", [], pflicht=True,
                   help="Eine Adresse pro Zeile. Mehrere gehen gleichzeitig raus."),
        OptionSpec("tag", "Nur diese Tags", "string", "",
                   help="Leer = alle Adressen. Sonst Apprise-Tags, kommagetrennt."),
    ]

    async def send(self, config: dict[str, Any], note: Notification, http: Any) -> None:
        titel = ("GRATIS: " if note.ist_gratis else "") + note.titel
        koerper = "\n".join(t for t in [
            note.preis_text(),
            f"Händler: {note.haendler}" if note.haendler else "",
            note.urteil_text or "",
            f"Regel: {note.regel}" if note.regel else "",
            note.url or "",
        ] if t)
        await anyio.to_thread.run_sync(self._sende_sync, config, titel, koerper,
                                       note.bild)

    async def send_sammel(self, config: dict[str, Any], sammel, http: Any) -> None:
        if sammel.anzahl == 1:
            await self.send(config, sammel.meldungen[0], http)
            return
        await anyio.to_thread.run_sync(
            self._sende_sync, config, sammel.titel,
            "\n".join(sammel.kurzzeilen(15)), None)

    def _sende_sync(self, config: dict[str, Any], titel: str, koerper: str,
                    bild: str | None) -> None:
        if not verfuegbar():
            raise ValueError(HINWEIS)
        import apprise

        adressen = [str(u).strip() for u in (config.get("urls") or []) if str(u).strip()]
        if not adressen:
            raise ValueError("Keine Apprise-Adresse eingetragen.")

        ziel = apprise.Apprise()
        abgelehnt = [a for a in adressen if not ziel.add(a)]
        if abgelehnt:
            # Apprise sagt nur True/False - welche Adresse es war, muss
            # hier stehen, sonst sucht man in fuenf Zeilen die falsche.
            raise ValueError("Apprise versteht diese Adresse nicht: "
                             + ", ".join(a.split("://")[0] + "://…" for a in abgelehnt))

        tags = [t.strip() for t in str(config.get("tag") or "").split(",") if t.strip()]
        ok = ziel.notify(body=koerper, title=titel,
                         tag=tags or apprise.common.MATCH_ALL_TAG,
                         attach=bild if bild and bild.startswith("http") else None)
        if not ok:
            raise ValueError("Apprise konnte nicht zustellen - Adresse und "
                             "Zugangsdaten prüfen.")


register(AppriseChannel())
