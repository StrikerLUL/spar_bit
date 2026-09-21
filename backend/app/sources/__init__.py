"""Quellen-Registry.

Neue Quelle hinzufuegen:
  1. Datei in diesem Ordner anlegen, Source ableiten, register(Instanz()).
  2. Modul hier importieren.
Mehr nicht.
"""
from . import (  # noqa: F401
               cheapshark,
               customfeed,
               epic,
               erwachsen,
               ggdeals,
               gog,
               itad,
               pepper,
               reddit,
               steam,
               wordpress,
)
from .base import (
               Category,
               DealItem,
               FetchContext,
               HealthResult,
               OptionSpec,
               Source,
               Verification,
               all_sources,
               get_source,
               register,
)

__all__ = [
               "Category",
               "DealItem",
               "FetchContext",
               "HealthResult",
               "OptionSpec",
               "Source",
               "Verification",
               "all_sources",
               "get_source",
               "register",
]
