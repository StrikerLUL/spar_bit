"""Wann ein Angebot endet - und warum das bei Gratis-Sachen alles ist.

Ein Rabatt, den man morgen auch noch mitnimmt, ist ein Rabatt. Ein
Gratis-Spiel, das Donnerstag um 17 Uhr verschwindet, ist ein Termin.
SparBit wusste das bisher nicht: es gab kein Feld dafuer, obwohl die
Quellen es teilweise mitliefern - Epic schickt seit jeher endDate mit,
es landete unbenutzt im Rohdatenfeld.

Zwei Wege hierher:

* **Aus den Rohdaten**, wo die Quelle es sauber angibt. Verlaesslich.
* **Aus dem Text**, wo es jemand hingeschrieben hat ("nur bis 31.10.",
  "noch 3 Tage"). Bewusst zurueckhaltend: lieber kein Datum als ein
  falsches. Ein erfundener Countdown waere schlimmer als gar keiner -
  wer wegen "laeuft in 2 h aus" hetzt und es stimmt nicht, glaubt der
  naechsten Meldung nicht mehr.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

# Felder, unter denen Quellen ein Ende angeben.
ROH_FELDER = ("endDate", "end_date", "expires", "expiry", "valid_until",
              "gueltig_bis", "endet_am")

_MONATE = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "maerz": 3, "märz": 3,
    "mar": 3, "mrz": 3, "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6,
    "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
    "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

# "bis 31.10.", "nur bis 31.10.2026", "endet am 05.11.2026"
_DATUM = re.compile(
    r"\b(?:nur\s+)?(?:noch\s+)?(?:bis|endet\s+am|gueltig\s+bis|gültig\s+bis|läuft\s+bis)"
    r"\s+(?:zum\s+)?(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})?", re.IGNORECASE)
# "bis 5. November", "endet am 12. Dez"
_DATUM_WORT = re.compile(
    r"\b(?:nur\s+)?(?:bis|endet\s+am|gueltig\s+bis|gültig\s+bis)\s+(?:zum\s+)?"
    r"(\d{1,2})\.?\s+([a-zäöü]{3,9})", re.IGNORECASE)
# "noch 3 Tage", "nur noch 6 Stunden"
_DAUER = re.compile(
    r"\bnoch\s+(\d{1,3})\s*(stunden?|std|h|tage?|tg|minuten?|min)\b", re.IGNORECASE)


def _mit_zeitzone(wert: datetime) -> datetime:
    return wert if wert.tzinfo else wert.replace(tzinfo=UTC)


def aus_roh(roh: dict | None) -> datetime | None:
    """Ende aus den Rohdaten der Quelle - der verlaessliche Weg."""
    if not isinstance(roh, dict):
        return None
    for feld in ROH_FELDER:
        wert = roh.get(feld)
        if not wert:
            continue
        if isinstance(wert, datetime):
            return _mit_zeitzone(wert)
        try:
            # Steam und Epic haengen ein Z an, das fromisoformat vor
            # Python 3.11 nicht mochte - und manche Quellen Millisekunden.
            return _mit_zeitzone(datetime.fromisoformat(
                str(wert).replace("Z", "+00:00")))
        except ValueError:
            try:
                return _mit_zeitzone(datetime.fromtimestamp(float(wert), UTC))
            except (ValueError, OSError, OverflowError):
                continue
    return None


def aus_text(text: str, jetzt: datetime | None = None) -> datetime | None:
    """Ende aus freiem Text - nur, wenn es eindeutig dasteht."""
    if not text:
        return None
    jetzt = jetzt or datetime.now(UTC)

    treffer = _DAUER.search(text)
    if treffer:
        menge = int(treffer.group(1))
        einheit = treffer.group(2).lower()
        if einheit.startswith(("stunde", "std", "h")):
            return jetzt + timedelta(hours=menge)
        if einheit.startswith(("tag", "tg")):
            return jetzt + timedelta(days=menge)
        if einheit.startswith("min"):
            return jetzt + timedelta(minutes=menge)

    treffer = _DATUM.search(text)
    if treffer:
        tag, monat, jahr = treffer.groups()
        return _datum(int(tag), int(monat), jahr, jetzt)

    treffer = _DATUM_WORT.search(text)
    if treffer:
        tag, monatswort = treffer.groups()
        monat = _MONATE.get(monatswort.lower())
        if monat:
            return _datum(int(tag), monat, None, jetzt)
    return None


def _datum(tag: int, monat: int, jahr: str | None, jetzt: datetime) -> datetime | None:
    if not (1 <= tag <= 31 and 1 <= monat <= 12):
        return None
    if jahr:
        zahl = int(jahr)
        zahl = zahl + 2000 if zahl < 100 else zahl
    else:
        # Ohne Jahresangabe das naechste Vorkommen nehmen: steht im Dezember
        # "bis 05.01.", ist der Januar danach gemeint, nicht der vergangene.
        zahl = jetzt.year
    try:
        # Ende des Tages, nicht Anfang: "bis 31.10." heisst ueblicherweise
        # einschliesslich des 31.
        ziel = datetime(zahl, monat, tag, 23, 59, tzinfo=UTC)
    except ValueError:
        return None
    if not jahr and ziel < jetzt - timedelta(days=1):
        try:
            ziel = ziel.replace(year=zahl + 1)
        except ValueError:
            return None
    # Mehr als ein Jahr voraus ist bei einem Angebot kein Ende, sondern
    # ein Lesefehler.
    if ziel > jetzt + timedelta(days=400):
        return None
    return ziel


def bestimme(titel: str, beschreibung: str | None, roh: dict | None,
             jetzt: datetime | None = None) -> datetime | None:
    """Der beste Wert, den es fuer diesen Deal gibt."""
    sicher = aus_roh(roh)
    if sicher:
        return sicher
    text = " ".join(t for t in (titel or "", beschreibung or "") if t)
    return aus_text(text, jetzt)
