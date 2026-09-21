"""Steam-Wunschliste als Vorlage fuer die eigene Wunschliste.

Wer Spiele beobachtet, hat sie meistens schon irgendwo stehen - naemlich
in der Steam-Wunschliste. Sie von Hand in SparBit zu uebertragen, heisst
bei dreissig Eintraegen dreissig Mal kopieren und einfuegen; die meisten
lassen es dann.

Steam liefert eine oeffentliche Wunschliste als JSON aus, ohne
Anmeldung und ohne API-Schluessel. Gelesen wird nur, was ohnehin
oeffentlich ist - wer seine Wunschliste privat gestellt hat, bekommt
eine klare Meldung statt eines leeren Ergebnisses.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Beide Schreibweisen, die man kopiert bekommt:
#   steamcommunity.com/profiles/<64-Bit-ID>/ bzw. /id/<Vanity-Name>/
#   store.steampowered.com/wishlist/profiles/<64-Bit-ID>/
_PROFIL = re.compile(
    r"(?:steamcommunity\.com|steampowered\.com/wishlist)/(profiles|id)/([^/?#]+)")
_NUR_ID = re.compile(r"^\d{17}$")

WUNSCH_URL = "https://store.steampowered.com/wishlist/profiles/{id}/wishlistdata/?p={seite}"
SPIEL_URL = "https://store.steampowered.com/app/{appid}/"
VANITY_URL = "https://steamcommunity.com/id/{name}/?xml=1"


@dataclass
class Eintrag:
    appid: str
    titel: str
    bild: str | None
    url: str


def steam_id_aus(eingabe: str) -> tuple[str, str]:
    """Aus Adresse, Vanity-Name oder ID die Form machen, die Steam kennt.

    Gibt (art, wert) zurueck: ("id", "7656119...") oder ("name", "cillian").
    """
    eingabe = (eingabe or "").strip()
    if not eingabe:
        raise ValueError("Keine Steam-Adresse angegeben.")

    treffer = _PROFIL.search(eingabe)
    if treffer:
        return ("id" if treffer.group(1) == "profiles" else "name",
                treffer.group(2))
    if _NUR_ID.match(eingabe):
        return "id", eingabe
    if re.fullmatch(r"[A-Za-z0-9_-]{2,64}", eingabe):
        return "name", eingabe
    raise ValueError("Das sieht nicht nach einem Steam-Profil aus. Erwartet "
                     "wird die Adresse der Wunschliste, der Profilname oder "
                     "die 17-stellige Steam-ID.")


async def _zu_id(http, art: str, wert: str) -> str:
    if art == "id":
        return wert
    # Der Vanity-Name loest sich ueber die oeffentliche XML-Ansicht auf -
    # ohne API-Schluessel, den sonst jeder erst beantragen muesste.
    text = await http.get_text(VANITY_URL.format(name=wert))
    treffer = re.search(r"<steamID64>(\d{17})</steamID64>", text)
    if not treffer:
        raise ValueError(f"Zu '{wert}' gibt es kein oeffentliches Steam-Profil.")
    return treffer.group(1)


async def hole(http, eingabe: str, max_seiten: int = 5) -> list[Eintrag]:
    """Wunschliste lesen. Wirft ValueError mit einem Satz, der weiterhilft."""
    art, wert = steam_id_aus(eingabe)
    steam_id = await _zu_id(http, art, wert)

    eintraege: list[Eintrag] = []
    for seite in range(max_seiten):
        daten = await http.get_json(WUNSCH_URL.format(id=steam_id, seite=seite))

        # Steam antwortet auf eine private Liste mit einem leeren Array
        # statt mit einem Fehler - ohne diesen Zweig sagte SparBit nur
        # "nichts gefunden" und niemand wuesste, woran es liegt.
        if isinstance(daten, list):
            if seite == 0:
                raise ValueError(
                    "Steam gibt nichts heraus. Die Wunschliste ist privat - "
                    "unter Profil - Privatsphaere steht 'Spieledetails', und "
                    "die muss auf 'oeffentlich' stehen.")
            break
        if not isinstance(daten, dict) or not daten:
            break

        for appid, spiel in daten.items():
            if not str(appid).isdigit() or not isinstance(spiel, dict):
                continue
            eintraege.append(Eintrag(
                appid=str(appid),
                titel=str(spiel.get("name") or f"Steam-App {appid}")[:255],
                bild=spiel.get("capsule") or None,
                url=SPIEL_URL.format(appid=appid),
            ))
        if len(daten) < 100:
            break            # letzte Seite
    return eintraege
