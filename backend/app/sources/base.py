"""Quellen-Plugin-System.

Eine neue Quelle hinzufuegen = eine Datei in sources/ anlegen + in
sources/__init__.py registrieren. Sonst nichts.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Category(str, enum.Enum):
    COMMUNITY = "community"      # mydealz, Preisjaeger, ...
    REDDIT = "reddit"
    GAMING = "gaming"
    EXPERIMENTAL = "experimental"
    # 18+. Quellen dieser Kategorie sind unsichtbar und unstartbar, solange
    # der Bereich unter "Logs & System" nicht freigeschaltet ist, und ihre
    # Funde landen ausschliesslich auf der eigenen Seite.
    ERWACHSEN = "erwachsen"


class Verification(str, enum.Enum):
    """Wurde der Endpoint gegen den echten Dienst geprueft?

    Diese Session konnte KEINE Quelle live pruefen (Egress-Policy blockt alle
    Deal-Hosts). Darum startet alles auf UNVERIFIED und wird erst durch
    `python -m tools.verify_endpoints` bzw. den "Jetzt testen"-Button im UI
    auf VERIFIED/BROKEN gesetzt. Nichts hier behauptet, geprueft zu sein.
    """
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    BROKEN = "broken"


class DealItem(BaseModel):
    """Normalisiertes Deal-Objekt. Jede Quelle liefert genau das."""

    titel: str
    url: str
    quelle: str

    beschreibung: str | None = None
    preis: float | None = None
    originalpreis: float | None = None
    rabatt_prozent: float | None = None
    waehrung: str = "EUR"
    haendler: str | None = None
    bild: str | None = None
    veroeffentlicht_am: datetime | None = None
    temperatur: float | None = None
    tags: list[str] = Field(default_factory=list)
    ist_gratis: bool = False
    kategorie: str | None = None
    # Gilt der Preis je Zeitraum? "monat" | "jahr" | "woche". Ein Abo fuer
    # 4,99 im Monat und ein Kopfhoerer fuer 4,99 sind zwei sehr
    # verschiedene Angebote - ohne dieses Feld sehen sie gleich aus.
    preis_zeitraum: str | None = None
    # Was das Angebot pro Monat kostet. Erst das macht Abos vergleichbar:
    # "1 EUR" fuer drei Monate ist guenstiger als "0,99 EUR" im Monat.
    preis_monat: float | None = None
    # Klartext fuer die Karte: "pro Monat", "für 3 Monate", "Stückpreis".
    preis_hinweis: str | None = None
    roh: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # Gratis-Erkennung vereinheitlichen: 0.00 zaehlt als gratis,
        # 100% Rabatt ebenso.
        if self.preis is not None and self.preis <= 0.009:
            object.__setattr__(self, "ist_gratis", True)
        if self.rabatt_prozent is not None and self.rabatt_prozent >= 99.5:
            object.__setattr__(self, "ist_gratis", True)
        if self.veroeffentlicht_am is not None and self.veroeffentlicht_am.tzinfo is None:
            object.__setattr__(
                self, "veroeffentlicht_am",
                self.veroeffentlicht_am.replace(tzinfo=timezone.utc),
            )
        # Rabatt aus Preisen ableiten, wenn die Quelle ihn nicht liefert.
        if (self.rabatt_prozent is None and self.preis is not None
                and self.originalpreis and self.originalpreis > 0
                and self.preis <= self.originalpreis):
            pct = (1 - self.preis / self.originalpreis) * 100
            object.__setattr__(self, "rabatt_prozent", round(pct, 1))


@dataclass
class OptionSpec:
    """Beschreibt ein im Web-UI editierbares Feld einer Quelle."""

    key: str
    label: str
    type: str  # "string" | "int" | "bool" | "list" | "select"
    default: Any = None
    help: str = ""
    choices: list[str] = field(default_factory=list)
    # Ohne diesen Wert funktioniert die Quelle bzw. der Kanal nicht. Ein
    # leerer Default heisst nicht automatisch Pflicht - viele Felder sind
    # schlicht optional.
    pflicht: bool = False


@dataclass
class HealthResult:
    ok: bool
    detail: str
    items_found: int = 0
    latency_ms: int = 0
    samples: list[DealItem] = field(default_factory=list)


@dataclass
class FetchContext:
    """Alles, was eine Quelle zur Laufzeit braucht."""

    http: Any                 # app.http.PoliteClient
    options: dict[str, Any]
    api_key: str | None = None
    log: Any = None
    # Was die Quelle waehrend des Laufs ueber sich selbst gelernt hat.
    # Nach einem erfolgreichen Lauf schreibt der Runner das in die
    # Konfiguration zurueck - so steht eine selbst gefundene Feed-Adresse
    # beim naechsten Mal schon richtig da und ist im UI sichtbar.
    notizen: dict[str, Any] = field(default_factory=dict)

    def opt(self, key: str, default: Any = None) -> Any:
        val = self.options.get(key, default)
        return default if val in (None, "") else val

    def merke(self, key: str, wert: Any) -> None:
        """Eine korrigierte Einstellung fuer den naechsten Lauf hinterlegen."""
        if self.options.get(key) != wert:
            self.notizen[key] = wert


class Source(ABC):
    """Basisklasse aller Quellen."""

    id: str
    display_name: str
    category: Category
    default_interval: int = 900          # Sekunden
    requires_api_key: bool = False
    api_key_url: str | None = None
    experimental: bool = False
    verification: Verification = Verification.UNVERIFIED
    docs_url: str | None = None
    beschreibung: str = ""
    min_interval: int = 300              # hoefliches Crawling: Untergrenze
    options_schema: list[OptionSpec] = []

    @property
    def default_options(self) -> dict[str, Any]:
        return {o.key: o.default for o in self.options_schema}

    @abstractmethod
    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        """Deals holen. Darf werfen - der Runner faengt isoliert ab."""

    async def health_check(self, ctx: FetchContext) -> HealthResult:
        """Default: einmal fetchen und schauen ob etwas Sinnvolles kommt."""
        import time
        t0 = time.monotonic()
        try:
            items = await self.fetch(ctx)
        except Exception as exc:  # noqa: BLE001 - bewusst breit
            return HealthResult(
                ok=False,
                detail=f"{type(exc).__name__}: {exc}"[:400],
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        ms = int((time.monotonic() - t0) * 1000)
        if not items:
            return HealthResult(
                ok=False,
                detail="Erreichbar, aber 0 Eintraege geparst - Format vermutlich geaendert.",
                latency_ms=ms,
            )
        return HealthResult(
            ok=True,
            detail=f"{len(items)} Eintraege geparst.",
            items_found=len(items),
            latency_ms=ms,
            samples=items[:5],
        )


# --- Registry -------------------------------------------------------------

_REGISTRY: dict[str, Source] = {}


def register(source: Source) -> Source:
    if source.id in _REGISTRY:
        raise ValueError(f"Quelle '{source.id}' ist bereits registriert")
    _REGISTRY[source.id] = source
    return source


def get_source(source_id: str) -> Source | None:
    return _REGISTRY.get(source_id)


def all_sources() -> list[Source]:
    return sorted(_REGISTRY.values(), key=lambda s: (s.category.value, s.display_name))
