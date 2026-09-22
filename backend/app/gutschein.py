"""Gutschein-Codes aus dem Deal-Text herausholen.

Der Fall: „Nur mit Code SOMMER25 – 25 % auf alles". Der Code stand
bisher im Fliesstext der Beschreibung, und in der Meldung aufs Handy
wurde die Beschreibung gekuerzt. Wer im Laden stand, musste den Deal
noch einmal aufmachen.

Das Problem an der Aufgabe ist nicht das Finden, sondern das
Nicht-Finden. Ein Deal-Text ist voller Zeichenfolgen, die aussehen wie
ein Code: Artikelnummern, Modellbezeichnungen (`WH-1000XM5`), Groessen
(`XXL`), Abkuerzungen (`DHL`, `PS5`). Ein Muster, das grosszuegig ist,
schreibt in jede zweite Meldung einen erfundenen Gutschein - und das ist
schlimmer als keiner, weil man ihm glaubt und an der Kasse steht.

Darum die umgekehrte Reihenfolge: **erst der Hinweis, dann der Code.**
Gesucht wird nie nach dem Code allein, sondern immer nach einem der
Woerter, die einen Code ankuendigen (`Code`, `Gutschein`, `Voucher`,
`Rabattcode` …) - und der Kandidat muss unmittelbar daneben stehen.
Steht kein Hinweis da, wird nichts gemeldet.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Die Woerter, die einen Code ankuendigen. Deutsch und Englisch, weil
# HotUKDeals und Reddit englisch schreiben.
_HINWEIS = (
    r"(?:gutschein(?:code|nummer)?|rabattcode|aktionscode|coupon(?:code)?|"
    r"voucher(?:\s*code)?|promo(?:tion)?\s*code|discount\s*code|code)"
)

# Der Kandidat selbst: 4 bis 24 Zeichen aus Buchstaben, Ziffern,
# Bindestrich und Unterstrich. Ob die Schreibweise fuer einen Code
# spricht, entscheidet _plausibel - hier wird erst einmal alles
# eingesammelt.
_KANDIDAT = r"([A-Za-z0-9][A-Za-z0-9_-]{3,23})"

# "Code: ABC123", "Code ABC123", "mit dem Code »ABC123«", "Code = ABC123"
#
# Das (?i:...) gilt nur fuer den Hinweis. Fuer den Kandidaten NICHT:
# dort ist die Schreibweise ein Indiz (siehe _plausibel), und ein
# globales re.IGNORECASE haette es zunichte gemacht.
_MUSTER = re.compile(
    rf"(?i:{_HINWEIS})\s*(?i:lautet|ist)?\s*(?::|=|-|–)?\s*"
    rf"[\"'„»«‘’“”\[\(]?\s*{_KANDIDAT}")

# Was trotz Hinweis kein Gutschein ist. Diese Woerter stehen haeufig
# direkt hinter "Code" und sind dann Teil des Satzes, nicht der Code.
_KEIN_CODE = {
    "CODE", "CODES", "GUTSCHEIN", "COUPON", "VOUCHER", "PROMO", "RABATT",
    "NICHT", "KEIN", "KEINE", "OHNE", "IM", "IST", "SIND", "WIRD",
    "EINGEBEN", "EINLOESEN", "EINLÖSEN", "NOETIG", "NÖTIG", "NOTWENDIG",
    "AUTOMATISCH", "ERFORDERLICH", "NEEDED", "REQUIRED", "APPLIED",
    "CHECKOUT", "WARENKORB", "SIEHE", "OBEN", "UNTEN", "DEAL", "LINK",
    "HIER", "THE", "AND", "FOR", "WITH", "YOUR", "THIS", "THAT", "FROM",
    "AUTO", "NONE", "NULL",
}

# Ein Kandidat, der nur aus Ziffern besteht, ist meistens eine
# Artikelnummer oder ein Preis - ausser er ist kurz genug, um ein
# Aktionscode zu sein (viele Shops nutzen fuenfstellige Zahlen).
_MAX_NUR_ZIFFERN = 8


def _plausibel(kandidat: str) -> bool:
    """`kandidat` in Originalschreibweise - die zaehlt hier mit."""
    if kandidat.upper() in _KEIN_CODE:
        return False
    if kandidat.isdigit() and len(kandidat) > _MAX_NUR_ZIFFERN:
        return False
    # Reine Bindestrich-Ketten und aehnlicher Unsinn.
    if not any(z.isalnum() for z in kandidat):
        return False
    # Die Schreibweise als Indiz: Codes stehen praktisch immer in
    # Grossbuchstaben ("SOMMER25") oder enthalten eine Ziffer
    # ("sommer25"). Was weder das eine noch das andere ist, ist
    # wahrscheinlich das naechste Wort im Satz - "mit dem Code sommer"
    # endet sonst als Gutschein "SOMMER", den es nie gab.
    return any(z.isupper() for z in kandidat) or any(z.isdigit() for z in kandidat)


def finde(*texte: str | None) -> str | None:
    """Den ersten plausiblen Gutschein-Code finden, sonst None.

    Mehrere Texte, weil Titel und Beschreibung beide in Frage kommen -
    und der Titel zuerst, weil ein Code dort fast immer der richtige
    ist.
    """
    for text in texte:
        if not text:
            continue
        for treffer in _MUSTER.finditer(text):
            kandidat = treffer.group(1)
            if _plausibel(kandidat):
                # Erst jetzt gross schreiben: die Pruefung oben braucht
                # das Original, der Laden nimmt beides.
                return kandidat.upper()
    return None
