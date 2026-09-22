"""Waehrungsumrechnung auf EUR.

CheapShark liefert USD, HotUKDeals GBP. Ohne Umrechnung wuerde eine Regel
"max. 20 EUR" bei USD-Deals falsch greifen.

Frueher standen hier ausschliesslich feste Kurse. Das war bequem und
falsch: ein Kurs altert still. Niemand bekommt eine Fehlermeldung, wenn
"max. 20 EUR" seit einem Jahr bei 21,40 EUR zuschlaegt - die Regel greift
einfach ein bisschen daneben, und das faellt erst auf, wenn man es
nachrechnet.

Darum holt SparBit die EZB-Referenzkurse - einmal am Tag, eine Datei,
kein Schluessel, kein Konto, keine Cookies. Das ist der eine ausgehende
Abruf, den SparBit von sich aus macht; abschalten laesst er sich mit
einem Schalter, und dann gilt wieder, was in den Einstellungen steht.
Ohne Netz oder mit abgeschalteter Automatik bleibt der zuletzt bekannte
Stand stehen, und das UI sagt, wie alt er ist.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

log = logging.getLogger(__name__)

# Die taegliche Referenztabelle der Europaeischen Zentralbank. Rund 3 KB,
# aktualisiert an Bankarbeitstagen gegen 16:00 MEZ.
EZB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

# Wie viel EUR ist eine Einheit der Waehrung wert. Rueckfallebene, falls
# nie ein Abruf gelungen ist - grob, aber besser als gar kein Kurs.
DEFAULT_RATES: dict[str, float] = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.17,
    "CHF": 1.05,
    "PLN": 0.23,
    # OzBargain rechnet in AUD. Ohne Kurs liefe jeder Fund von dort
    # ohne EUR-Gegenwert durch - und damit an jeder Preisgrenze vorbei.
    "AUD": 0.60,
}

# Ab wann das UI warnt. Drei Monate Drift sind bei den ueblichen Paaren
# einige Prozent - genug, dass eine Preisgrenze daneben greift.
VERALTET_NACH_TAGEN = 90

# Schluessel in der Settings-Tabelle.
SCHLUESSEL_KURSE = "currency_rates"
SCHLUESSEL_STAND = "currency_rates_stand"      # ISO-Datum des EZB-Stands
SCHLUESSEL_AUTO = "currency_auto"              # bool, Vorgabe an

_rates: dict[str, float] = dict(DEFAULT_RATES)
_stand: str | None = None


class KeinKurs(Exception):
    """Der Abruf kam durch, aber es stand nichts Brauchbares darin."""


def set_rates(rates: dict[str, float] | None, stand: str | None = None) -> None:
    """Kurse aus den Einstellungen uebernehmen. Unsinnige Werte werden verworfen."""
    merged = dict(DEFAULT_RATES)
    for code, value in (rates or {}).items():
        try:
            rate = float(value)
        except (TypeError, ValueError):
            continue
        if 0 < rate < 1000:
            merged[str(code).upper()] = rate
    merged["EUR"] = 1.0
    global _rates, _stand
    _rates = merged
    if stand is not None:
        _stand = stand


def get_rates() -> dict[str, float]:
    return dict(_rates)


def get_stand() -> str | None:
    """ISO-Datum des zuletzt uebernommenen EZB-Stands, sonst None."""
    return _stand


def alter_in_tagen(stand: str | None = None) -> int | None:
    """Wie alt der Kursstand ist. None, wenn nie einer geholt wurde."""
    roh = stand if stand is not None else _stand
    if not roh:
        return None
    try:
        gestellt = date.fromisoformat(str(roh)[:10])
    except ValueError:
        return None
    return max(0, (datetime.now(UTC).date() - gestellt).days)


def ist_veraltet(stand: str | None = None) -> bool:
    alter = alter_in_tagen(stand)
    # Nie geholt zaehlt als veraltet: die Vorgabewerte im Code sind
    # eingefroren und werden mit jedem Monat schlechter.
    return alter is None or alter > VERALTET_NACH_TAGEN


def aus_ezb_xml(xml: str | bytes, nur: set[str] | None = None) -> tuple[dict[str, float], str]:
    """EZB-XML in unsere Richtung drehen: wie viel EUR kostet eine Einheit.

    Die EZB schreibt den Kehrwert von dem, was hier gebraucht wird
    (`rate="1.0856"` heisst: 1 EUR = 1,0856 USD). Die Umkehrung ist der
    ganze Trick - und die Stelle, an der ein Vorzeichenfehler jahrelang
    unbemerkt bliebe, weil 0,92 und 1,09 beide plausibel aussehen.

    `nur` beschraenkt auf die Waehrungen, die SparBit wirklich sieht;
    die EZB liefert 30.
    """
    try:
        wurzel = ET.fromstring(xml if isinstance(xml, str) else xml.decode("utf-8"))
    except (ET.ParseError, UnicodeDecodeError) as exc:
        raise KeinKurs(f"XML nicht lesbar: {exc}") from exc

    gefragt = {c.upper() for c in (nur or DEFAULT_RATES)} - {"EUR"}
    kurse: dict[str, float] = {"EUR": 1.0}
    stand = ""

    # Der Namensraum der EZB steht in der Datei; hart kodiert waere er die
    # naechste Quelle fuer "ging jahrelang, geht ploetzlich nicht mehr".
    for knoten in wurzel.iter():
        marke = knoten.tag.rsplit("}", 1)[-1]
        if marke != "Cube":
            continue
        if knoten.get("time"):
            stand = knoten.get("time", "")
        code = (knoten.get("currency") or "").upper()
        roh = knoten.get("rate")
        if not code or not roh:
            continue
        if gefragt and code not in gefragt:
            continue
        try:
            je_euro = float(roh)
        except ValueError:
            continue
        if je_euro <= 0:
            continue
        kurse[code] = round(1.0 / je_euro, 6)

    if len(kurse) < 2 or not stand:
        raise KeinKurs("Keine verwertbaren Kurse in der Antwort.")
    return kurse, stand


async def hole(client) -> tuple[dict[str, float], str]:
    """Kurse bei der EZB abholen. Wirft, wenn nichts Brauchbares kommt.

    `client` ist der PoliteClient des Schedulers - damit gelten hier
    dieselben Regeln wie fuer jede Quelle: eigener User-Agent, Abstand,
    Groessengrenze, und der Netzschutz sieht die Adresse vorher an.
    """
    antwort = await client.get(EZB_URL, cache_key="ezb-kurse")
    return aus_ezb_xml(antwort.content, nur=set(DEFAULT_RATES))


def to_eur(amount: float | None, currency: str | None) -> float | None:
    """Betrag in EUR. Unbekannte Waehrung -> None, damit nichts Falsches
    in eine Preis-Regel rutscht."""
    if amount is None:
        return None
    code = (currency or "EUR").upper()
    rate = _rates.get(code)
    if rate is None:
        log.debug("Kein Kurs fuer %s hinterlegt", code)
        return None
    return round(amount * rate, 2)
