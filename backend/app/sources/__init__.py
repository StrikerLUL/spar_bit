"""Quellen-Registry.

Neue Quelle hinzufuegen:
  1. Datei in diesem Ordner anlegen, Source ableiten, register(Instanz()).
  2. Modul hier importieren.
Mehr nicht.
"""
from . import (cheapshark, customfeed, epic, ggdeals, gog, itad,  # noqa: F401
               pepper, reddit, steam, wordpress)
from .base import (Category, DealItem, FetchContext, HealthResult,  # noqa: F401
                   OptionSpec, Source, Verification, all_sources, get_source,
                   register)

__all__ = ["Source", "DealItem", "FetchContext", "HealthResult", "OptionSpec",
           "Category", "Verification", "all_sources", "get_source", "register"]
