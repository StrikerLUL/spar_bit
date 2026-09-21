"""Der Weg eines Deals: Quelle -> Dedupe -> DB -> Regeln -> Kanaele.

Fruehe eine Datei mit 795 Zeilen, in der Aufnahme, Regelpruefung,
Ruhezeiten, Versand, Sammelmeldung, Preisalarm und Preisfehler-Waechter
nebeneinander standen - sieben Gruende, dieselbe Datei anzufassen.

Jetzt drei Module entlang des Wegs. Nach aussen bleibt alles, wie es
war: wer `from .pipeline import ingest, dispatch` schreibt, merkt vom
Schnitt nichts.
"""
from .aufnahme import (  # noqa: F401
                       DEDUPE_CANDIDATES,
                       DEDUPE_WINDOW_HOURS,
                       _apply_price,
                       _entwirre_gratis,
                       _ingest_one,
                       _merke_angebot,
                       _rabatt,
                       ingest,
)
from .gemeinsam import _deal_payload, _note  # noqa: F401
from .regeln import (  # noqa: F401
                       _ohne_erwachsene,
                       _parse_hhmm,
                       _regelnamen,
                       _sofort,
                       _zielkanaele,
                       buendele,
                       in_quiet_hours,
                       match_rules,
)
from .versand import (  # noqa: F401
                       _zeitraum,
                       check_price_alarms,
                       dispatch,
                       dispatch_alarms,
                       dispatch_preisfehler,
                       dispatch_watchdog,
                       send_digest,
                       waechter_aktiv,
)

__all__ = [
                       "buendele",
                       "check_price_alarms",
                       "dispatch",
                       "dispatch_alarms",
                       "dispatch_preisfehler",
                       "dispatch_watchdog",
                       "in_quiet_hours",
                       "ingest",
                       "match_rules",
                       "send_digest",
                       "waechter_aktiv",
]
