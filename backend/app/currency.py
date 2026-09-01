"""Waehrungsumrechnung auf EUR.

CheapShark liefert USD, HotUKDeals GBP. Ohne Umrechnung wuerde eine Regel
"max. 20 EUR" bei USD-Deals falsch greifen. Die Kurse stehen in den
Einstellungen und sind im UI pflegbar - bewusst statisch, damit SparBit
keinen weiteren externen Dienst braucht, den man pflegen und der ausfallen
kann. Fuer Deal-Schwellen reicht ein grober Kurs voellig.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Wie viel EUR ist eine Einheit der Waehrung wert.
DEFAULT_RATES: dict[str, float] = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.17,
    "CHF": 1.05,
    "PLN": 0.23,
}

_rates: dict[str, float] = dict(DEFAULT_RATES)


def set_rates(rates: dict[str, float] | None) -> None:
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
    global _rates
    _rates = merged


def get_rates() -> dict[str, float]:
    return dict(_rates)


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
