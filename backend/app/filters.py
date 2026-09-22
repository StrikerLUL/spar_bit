"""Filter-Engine.

Eine Regel ist ein Datensatz, kein Code. Sie wird im UI gebaut und hier
ausgewertet. Wichtig fuers UI: `evaluate` liefert nicht nur ja/nein, sondern
auch WARUM - damit der Regel-Editor zeigen kann, woran ein Deal gescheitert
ist.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# Ein "Deal-aehnliches" Objekt: DB-Model oder DealItem. Beides hat diese Felder.


@dataclass
class RuleSpec:
    """Regel-Definition, entkoppelt vom DB-Model (damit testbar ohne DB)."""

    keywords: list[str] = field(default_factory=list)
    required_keywords: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)
    max_preis: float | None = None
    min_rabatt_prozent: float | None = None
    nur_gratis: bool = False
    min_temperatur: float | None = None
    min_urteil: str | None = None
    min_fehler_score: int | None = None
    sources: list[str] = field(default_factory=list)
    kategorien: list[str] = field(default_factory=list)
    warengruppen: list[str] = field(default_factory=list)
    haendler: list[str] = field(default_factory=list)
    # Darf die Regel 18+-Funde sehen? Ohne dieses Haekchen nie - eine
    # Regel wie "alles unter 5 Euro" wuerde den ganzen Bereich melden.
    erwachsen: bool = False

    @classmethod
    def from_model(cls, rule: Any) -> RuleSpec:
        return cls(
            keywords=list(rule.keywords or []),
            required_keywords=list(rule.required_keywords or []),
            blacklist=list(rule.blacklist or []),
            max_preis=rule.max_preis,
            min_rabatt_prozent=rule.min_rabatt_prozent,
            nur_gratis=bool(rule.nur_gratis),
            min_temperatur=rule.min_temperatur,
            min_urteil=getattr(rule, "min_urteil", None),
            min_fehler_score=getattr(rule, "min_fehler_score", None),
            sources=list(rule.sources or []),
            kategorien=list(rule.kategorien or []),
            warengruppen=list(getattr(rule, "warengruppen", None) or []),
            haendler=list(rule.haendler or []),
            erwachsen=bool(getattr(rule, "erwachsen", False)),
        )


@dataclass
class MatchResult:
    matched: bool
    reasons: list[str] = field(default_factory=list)   # was hat gepasst
    failed: list[str] = field(default_factory=list)    # woran es scheiterte

    def __bool__(self) -> bool:
        return self.matched


def _haystack(deal: Any) -> str:
    parts = [
        getattr(deal, "titel", "") or "",
        getattr(deal, "beschreibung", "") or "",
        getattr(deal, "haendler", "") or "",
        " ".join(getattr(deal, "tags", None) or []),
    ]
    return " ".join(parts).lower()


def _term_matches(term: str, haystack: str) -> bool:
    """Keyword-Match.

    - "foo bar"   -> Phrase, muss so vorkommen
    - "foo*"      -> Praefix
    - sonst       -> ganzes Wort (damit "tv" nicht in "advent" trifft)
    """
    term = (term or "").strip().lower()
    if not term:
        return False
    if term.endswith("*"):
        stem = re.escape(term[:-1])
        return re.search(rf"(?<![\w]){stem}[\w]*", haystack) is not None
    if " " in term:
        return term in haystack
    return re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", haystack) is not None


def _norm_set(values: Iterable[str]) -> set[str]:
    return {str(v).strip().lower() for v in values if str(v).strip()}


def evaluate(rule: RuleSpec, deal: Any) -> MatchResult:
    """Prueft einen Deal gegen eine Regel. Alle Bedingungen sind UND-verknuepft;
    nur die `keywords`-Liste selbst ist ODER."""
    reasons: list[str] = []
    failed: list[str] = []
    hay = _haystack(deal)

    # --- 18+: schlaegt alles, noch vor der Blacklist ---
    # Nicht "eine Bedingung mehr", sondern eine Tuer. Eine Regel ohne das
    # Haekchen sieht diese Deals gar nicht - unabhaengig davon, wie gut
    # alles andere passt.
    if getattr(deal, "erwachsen", False) and not rule.erwachsen:
        return MatchResult(False, [], ["18+-Fund, Regel nicht dafür freigegeben"])

    # --- Blacklist: schlaegt alles ---
    for term in rule.blacklist:
        if _term_matches(term, hay):
            return MatchResult(False, [], [f"Blacklist-Treffer: '{term}'"])

    # --- Pflicht-Keywords (UND) ---
    for term in rule.required_keywords:
        if not _term_matches(term, hay):
            failed.append(f"Pflicht-Keyword fehlt: '{term}'")
    if rule.required_keywords and not failed:
        reasons.append(f"alle Pflicht-Keywords vorhanden ({len(rule.required_keywords)})")

    # --- Keywords (ODER) ---
    if rule.keywords:
        hits = [t for t in rule.keywords if _term_matches(t, hay)]
        if hits:
            reasons.append("Keyword: " + ", ".join(f"'{h}'" for h in hits[:3]))
        else:
            failed.append("kein Keyword getroffen")

    # --- Quellen ---
    if rule.sources:
        quelle = (getattr(deal, "quelle", "") or "").lower()
        if quelle not in _norm_set(rule.sources):
            failed.append(f"Quelle '{quelle}' nicht in Auswahl")
        else:
            reasons.append(f"Quelle '{quelle}'")

    # --- Gratis / Preis / Rabatt ---
    # Fuer Preisschwellen zaehlt der EUR-Betrag: CheapShark liefert USD,
    # HotUKDeals GBP - sonst wuerde "max. 20 EUR" quellenabhaengig anders
    # greifen. Faellt preis_eur aus (unbekannte Waehrung), nutzen wir den
    # Rohpreis, statt den Deal stillschweigend fallen zu lassen.
    preis = getattr(deal, "preis_eur", None)
    if preis is None:
        preis = getattr(deal, "preis", None)
    ist_gratis = bool(getattr(deal, "ist_gratis", False))

    if rule.nur_gratis:
        if ist_gratis:
            reasons.append("ist gratis")
        else:
            failed.append("nicht gratis")

    if rule.max_preis is not None:
        if preis is None:
            failed.append("kein Preis erkannt (max_preis gesetzt)")
        elif preis > rule.max_preis:
            failed.append(f"Preis {preis:.2f} > max {rule.max_preis:.2f}")
        else:
            reasons.append(f"Preis {preis:.2f} <= {rule.max_preis:.2f}")

    if rule.min_rabatt_prozent is not None:
        rabatt = getattr(deal, "rabatt_prozent", None)
        # Gratis zaehlt implizit als 100 %.
        if rabatt is None and ist_gratis:
            rabatt = 100.0
        if rabatt is None:
            failed.append("kein Rabatt erkannt (min_rabatt gesetzt)")
        elif rabatt < rule.min_rabatt_prozent:
            failed.append(f"Rabatt {rabatt:.0f}% < {rule.min_rabatt_prozent:.0f}%")
        else:
            reasons.append(f"Rabatt {rabatt:.0f}%")

    # --- Temperatur ---
    if rule.min_temperatur is not None:
        temp = getattr(deal, "temperatur", None)
        if temp is None:
            failed.append("keine Temperatur (Quelle liefert keine)")
        elif temp < rule.min_temperatur:
            failed.append(f"Temperatur {temp:.0f} < {rule.min_temperatur:.0f}")
        else:
            reasons.append(f"Temperatur {temp:.0f}")

    # --- Preisurteil ---
    if rule.min_urteil:
        from .verdict import LABEL, mindestens
        urteil = getattr(deal, "urteil", None)
        erlaubt = mindestens(rule.min_urteil)
        if urteil is None:
            failed.append("noch kein Preisurteil (zu wenig Verlauf)")
        elif urteil not in erlaubt:
            failed.append(f"Urteil '{LABEL.get(urteil, urteil)}' "
                          f"schlechter als '{LABEL.get(rule.min_urteil)}'")
        else:
            reasons.append(f"Urteil: {LABEL.get(urteil, urteil)}")

    # --- Preisfehler ---
    if rule.min_fehler_score:
        from .pricefehler import LABEL as FEHLER_LABEL
        score = int(getattr(deal, "fehler_score", 0) or 0)
        if score < rule.min_fehler_score:
            stufe = getattr(deal, "fehler_stufe", None)
            failed.append(f"Preisfehler-Punkte {score} < {rule.min_fehler_score}"
                          + (f" ({FEHLER_LABEL.get(stufe)})" if stufe else ""))
        else:
            reasons.append(f"Preisfehler-Punkte {score}")

    # --- Kategorie / Haendler ---
    if rule.kategorien:
        kat = (getattr(deal, "kategorie", "") or "").lower()
        if kat not in _norm_set(rule.kategorien):
            failed.append(f"Kategorie '{kat or '-'}' nicht in Auswahl")
        else:
            reasons.append(f"Kategorie '{kat}'")

    if rule.warengruppen:
        from .warengruppe import GRUPPEN
        gruppe = (getattr(deal, "warengruppe", "") or "").lower()
        if gruppe not in _norm_set(rule.warengruppen):
            # Der Anzeigename statt der ID: "nicht in Auswahl" hilft
            # nur, wenn dabeisteht, was der Deal denn ist.
            name = GRUPPEN.get(gruppe) or "ohne Warengruppe"
            failed.append(f"Warengruppe: {name}")
        else:
            reasons.append(f"Warengruppe '{GRUPPEN.get(gruppe, gruppe)}'")

    if rule.haendler:
        h = (getattr(deal, "haendler", "") or "").lower()
        wanted = _norm_set(rule.haendler)
        # Teilstring, damit "amazon" auch "Amazon.de" trifft.
        if not any(w in h for w in wanted):
            failed.append(f"Haendler '{h or '-'}' nicht in Auswahl")
        else:
            reasons.append(f"Haendler '{h}'")

    # Eine Regel ohne jede Bedingung soll nicht alles durchwinken.
    if not any([rule.keywords, rule.required_keywords, rule.nur_gratis,
                rule.max_preis is not None, rule.min_rabatt_prozent is not None,
                rule.min_temperatur is not None, rule.min_urteil, rule.sources,
                rule.min_fehler_score, rule.kategorien, rule.haendler,
                rule.warengruppen]):
        return MatchResult(False, [], ["Regel hat keine Bedingungen"])

    return MatchResult(not failed, reasons, failed)


def preview(rule: RuleSpec, deals: list[Any], sample_size: int = 8) -> dict:
    """Fuer den Regel-Editor: wie viele der letzten N Deals haette die Regel
    getroffen, und welche?"""
    hits, near_misses = [], []
    for deal in deals:
        res = evaluate(rule, deal)
        if res.matched:
            hits.append((deal, res))
        elif len(res.failed) == 1 and not res.failed[0].startswith("Blacklist"):
            near_misses.append((deal, res))

    total = len(deals)
    return {
        "geprueft": total,
        "treffer": len(hits),
        "trefferquote": round(len(hits) / total * 100, 1) if total else 0.0,
        "beispiele": [_sample(d, r) for d, r in hits[:sample_size]],
        "knapp_verfehlt": [_sample(d, r) for d, r in near_misses[:sample_size]],
    }


def _sample(deal: Any, res: MatchResult) -> dict:
    return {
        "id": getattr(deal, "id", None),
        "titel": getattr(deal, "titel", ""),
        "preis": getattr(deal, "preis", None),
        "originalpreis": getattr(deal, "originalpreis", None),
        "rabatt_prozent": getattr(deal, "rabatt_prozent", None),
        "ist_gratis": bool(getattr(deal, "ist_gratis", False)),
        "erwachsen": bool(getattr(deal, "erwachsen", False)),
        "quelle": getattr(deal, "quelle", ""),
        "fehler_score": getattr(deal, "fehler_score", 0),
        "fehler_stufe": getattr(deal, "fehler_stufe", None),
        "url": getattr(deal, "url", ""),
        "bild": getattr(deal, "bild", None),
        "gruende": res.reasons,
        "verfehlt": res.failed,
    }
