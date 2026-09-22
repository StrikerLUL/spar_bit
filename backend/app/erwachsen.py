"""Der 18+-Bereich: standardmaessig aus, und strikt getrennt gefuehrt.

Drei Regeln bestimmen alles, was hier passiert:

1. **Aus, bis jemand ausdruecklich Ja sagt.** Der Schalter sitzt unter
   *Logs & System*, verlangt eine Altersbestaetigung und ist nach einer
   Neuinstallation aus. Ohne ihn gibt es die Quellen nicht, die Seite nicht
   und die Deals nicht - auch nicht ueber die API.
2. **Nie im normalen Feed.** Ein 18+-Fund taucht auf der eigenen Seite auf
   und sonst nirgends: nicht im Feed, nicht in der Uebersicht, nicht in der
   Suche, nicht in den Statistiken, nicht in der Empfehlung.
3. **Nie ungefragt aufs Handy.** Normale Regeln koennen 18+-Deals gar nicht
   treffen. Eine Regel muss das ausdruecklich erlauben - und selbst dann
   entscheidet ein zweiter Schalter, ob ueberhaupt gemeldet wird.

Die Einstufung selbst ist bewusst zweistufig. Ein eindeutiges Wort genuegt
("Vibrator"), ein mehrdeutiges nicht ("adult", "sexy") - davon braucht es
zwei. Sonst wandert die halbe Modeabteilung in den 18+-Bereich, und dort
findet sie niemand wieder.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .db import get_setting, set_setting
from .models import utcnow

# --- Einstellungs-Schluessel ----------------------------------------------

AKTIV = "erwachsen_aktiv"                # Bereich freigeschaltet?
BESTAETIGT_AM = "erwachsen_bestaetigt_am"  # wann das Alter bestaetigt wurde
MELDEN = "erwachsen_melden"              # auch ueber Kanaele zustellen?
UNSCHARF = "erwachsen_unscharf"          # Bilder erst auf Klick zeigen


def ist_aktiv(db: Session) -> bool:
    return bool(get_setting(db, AKTIV, False))


def melden_erlaubt(db: Session) -> bool:
    """Duerfen 18+-Funde ueber Telegram, Discord & Co. raus?"""
    return ist_aktiv(db) and bool(get_setting(db, MELDEN, False))


def zustand(db: Session) -> dict:
    return {
        "an": ist_aktiv(db),
        "bestaetigt_am": get_setting(db, BESTAETIGT_AM),
        "melden": bool(get_setting(db, MELDEN, False)),
        "unscharf": bool(get_setting(db, UNSCHARF, True)),
    }


def schalte(db: Session, an: bool, *, bestaetigt: bool = False) -> dict:
    """Bereich ein- oder ausschalten.

    Einschalten geht nur mit ausdruecklicher Altersbestaetigung. Das ist
    kein Rechtsgutachten, sondern die Stelle, an der man nicht aus Versehen
    hinklickt.
    """
    if an and not bestaetigt:
        raise ValueError("Zum Einschalten fehlt die Altersbestätigung.")
    set_setting(db, AKTIV, bool(an))
    if an:
        set_setting(db, BESTAETIGT_AM, utcnow().isoformat())
    db.commit()
    return zustand(db)


# --- Einstufung ------------------------------------------------------------

# Eindeutig. Ein Treffer genuegt.
EINDEUTIG = [
    # Artikel
    "erotik", "erotikshop", "erotikartikel", "sexspielzeug", "sextoy",
    "sextoys", "sexshop", "vibrator", "vibratoren", "dildo", "dildos",
    "buttplug", "analplug", "analkette", "penisring", "penispumpe",
    "masturbator", "taschenmuschi", "liebeskugeln", "vibrationsei",
    "gleitgel", "gleitmittel", "kondom", "kondome", "sexpuppe", "lovedoll",
    "fesselset", "bondage", "bdsm", "fetisch", "nippelklemmen", "analdusche",
    "vibro-ei", "klitoris", "auflegevibrator", "paarvibrator", "strap-on",
    # Marken, die es nur in diesem Regal gibt
    "satisfyer", "womanizer", "lovense", "fleshlight", "we-vibe", "wevibe",
    "lelo", "durex", "ritex", "billy boy", "amorelie", "beate uhse",
    "eis.de", "orion versand", "pjur", "tenga", "svakom", "arcwave",
    "fun factory", "nexus", "sinful", "lustpunkt",
    # Medien und Plattformen
    "pornhub", "porno", "pornofilm", "erotikfilm", "onlyfans", "fansly",
    "brazzers", "xhamster", "youporn", "stripchat", "chaturbate",
    "hentai", "doujin", "doujinshi", "eroge", "nutaku", "dlsite",
    "mangagamer", "jast usa", "fanza",
    # Kennzeichnungen
    "nsfw", "fsk 18", "fsk18", "usk 18", "ab 18 jahren", "adults only",
    "r18", "18+",
]

# Mehrdeutig. Zwei davon (oder eins plus ein eindeutiges) stufen ein.
MEHRDEUTIG = [
    "adult", "mature", "erwachsenen", "erotisch", "erotische",
    "dessous", "reizwäsche", "reizwaesche", "negligé", "neglige",
    "lingerie", "strapse", "straps", "nachtwäsche", "babydoll",
    "sinnlich", "verführerisch", "verfuehrerisch", "intim", "intimpflege",
    "nackt", "nude", "nudity", "sexy", "lust", "ecchi", "oppai",
    "swinger", "partnertausch", "rollenspiel für erwachsene",
]

SCHWELLE_MEHRDEUTIG = 2


def _regex(woerter: list[str]) -> re.Pattern:
    teile = [re.escape(w).replace(r"\ ", r"\s+").replace(r"\+", r"\+")
             for w in sorted(woerter, key=len, reverse=True)]
    return re.compile(r"(?<![a-z0-9äöüß])(?:" + "|".join(teile) + r")(?![a-zäöüß])",
                      re.IGNORECASE)


_EINDEUTIG_RE = _regex(EINDEUTIG)
_MEHRDEUTIG_RE = _regex(MEHRDEUTIG)


@dataclass
class Einstufung:
    erwachsen: bool
    treffer: list[str] = field(default_factory=list)
    grund: str = ""


def einstufen(titel: str, beschreibung: str | None = None,
              tags: list | None = None, *, quelle_ist_18: bool = False
              ) -> Einstufung:
    """Gehoert dieser Fund in den 18+-Bereich?

    `quelle_ist_18` schlaegt alles: was aus einer 18+-Quelle kommt, bleibt
    dort, auch wenn im Titel nur "Gutschein" steht.
    """
    if quelle_ist_18:
        return Einstufung(True, [], "stammt aus einer 18+-Quelle")

    heu = " ".join(filter(None, [
        titel or "", beschreibung or "",
        " ".join(str(t) for t in (tags or [])),
    ]))
    eindeutig = sorted({m.group(0).lower() for m in _EINDEUTIG_RE.finditer(heu)})
    if eindeutig:
        return Einstufung(True, eindeutig,
                          "eindeutiges Stichwort: " + ", ".join(eindeutig[:3]))

    mehrdeutig = sorted({m.group(0).lower() for m in _MEHRDEUTIG_RE.finditer(heu)})
    if len(mehrdeutig) >= SCHWELLE_MEHRDEUTIG:
        return Einstufung(True, mehrdeutig,
                          "mehrere Hinweise: " + ", ".join(mehrdeutig[:3]))
    return Einstufung(False, mehrdeutig, "")


def quelle_ist_18(source_id: str) -> bool:
    """Gehoert diese Quellen-ID zum 18+-Bereich?"""
    from .sources import Category, get_source  # spaet, wegen Importlage
    src = get_source(source_id)
    return bool(src and src.category is Category.ERWACHSEN)


def markiere(deal, *, source_id: str = "", quelle_ist_18_flag: bool | None = None
             ) -> bool:
    """Einen Deal einstufen und die Marke setzen. Gibt zurueck, ob 18+.

    Einmal gesetzt bleibt die Marke. Derselbe Artikel kann spaeter ueber
    eine harmlose Quelle noch einmal hereinkommen - er darf dadurch nicht in
    den normalen Feed rutschen.
    """
    if getattr(deal, "erwachsen", False):
        return True
    aus_quelle = (quelle_ist_18(source_id) if quelle_ist_18_flag is None
                  else quelle_ist_18_flag)
    urteil = einstufen(deal.titel, deal.beschreibung, deal.tags,
                       quelle_ist_18=aus_quelle)
    if urteil.erwachsen:
        deal.erwachsen = True
        deal.erwachsen_grund = urteil.grund[:500]
    return urteil.erwachsen
