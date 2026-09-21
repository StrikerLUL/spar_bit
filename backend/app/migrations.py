"""Schema-Aenderungen, nummeriert und nachvollziehbar.

Vorher stand hier eine Liste von Spalten, die bei jedem Start stur
nachgezogen wurde. Das reichte, solange es nur ums Ergaenzen ging - aber
es konnte nichts anderes: keinen Index nachtragen, keine Daten fuellen,
nichts umbenennen. Und es liess sich nicht ansehen: welchen Stand eine
vorgefundene Datenbank hatte, war nirgends vermerkt.

Jetzt hat jeder Schritt eine Nummer, eine Beschreibung und einen Eintrag
in `schema_migrations`, sobald er gelaufen ist. Was einmal angewendet
wurde, laeuft nicht noch einmal.

Zwei Faelle, absichtlich getrennt:

* **Neue Datenbank** - `create_all` baut den aktuellen Stand, danach
  werden alle Schritte als erledigt vermerkt (gestempelt). Sie muessen
  nicht laufen, ihr Ergebnis steht schon.
* **Vorgefundene Datenbank** - die offenen Schritte laufen der Reihe
  nach, jeder in seiner eigenen Transaktion. Bricht einer ab, bleibt
  alles davor erhalten und beim naechsten Start geht es dort weiter.

Ein neuer Schritt gehoert ans Ende der Liste und bekommt die naechste
Nummer. Nummern werden nie wiederverwendet und bestehende Schritte nie
nachtraeglich geaendert - draussen sind sie laengst gelaufen.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.schema import CreateIndex

log = logging.getLogger(__name__)

TABELLE = "schema_migrations"


@dataclass(frozen=True)
class Schritt:
    nummer: int
    beschreibung: str
    aendert: Callable[[Connection], None]


# --- Werkzeug fuer die Schritte ------------------------------------------

def tabelle_existiert(conn: Connection, name: str) -> bool:
    return name in inspect(conn).get_table_names()


def spalte_existiert(conn: Connection, tabelle: str, spalte: str) -> bool:
    if not tabelle_existiert(conn, tabelle):
        return False
    return any(s["name"] == spalte for s in inspect(conn).get_columns(tabelle))


def spalte_ergaenzen(conn: Connection, tabelle: str, spalte: str, ddl: str) -> bool:
    """ADD COLUMN, wenn es die Spalte noch nicht gibt. Gibt True bei Arbeit."""
    if not tabelle_existiert(conn, tabelle):
        return False            # legt create_all gleich komplett an
    if spalte_existiert(conn, tabelle, spalte):
        return False
    conn.execute(text(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {ddl}"))
    log.info("Migration: Spalte %s.%s ergaenzt", tabelle, spalte)
    return True


def indizes_aus_modellen(conn: Connection, metadata) -> int:
    """Jeden im Modell deklarierten Index anlegen, der noch fehlt.

    Noetig, weil `create_all` bestehende Tabellen ueberspringt - samt
    ihrer Indizes. Ein Index, der nach der ersten Version dazukam, fehlte
    darum auf genau den Installationen, die am laengsten laufen und die
    meisten Daten haben.
    """
    inspector = inspect(conn)
    vorhanden = set(inspector.get_table_names())
    angelegt = 0
    for tabelle in metadata.sorted_tables:
        if tabelle.name not in vorhanden:
            continue
        bekannt = {i["name"] for i in inspector.get_indexes(tabelle.name)}
        spalten = {s["name"] for s in inspector.get_columns(tabelle.name)}
        for index in tabelle.indexes:
            if index.name in bekannt:
                continue
            # Ein Index auf einer Spalte, die es (noch) nicht gibt, waere
            # ein Fehler - der zugehoerige Schritt kommt dann spaeter.
            if not {c.name for c in index.columns} <= spalten:
                continue
            conn.execute(CreateIndex(index, if_not_exists=True))
            log.info("Migration: Index %s angelegt", index.name)
            angelegt += 1
    return angelegt


# --- Die Schritte ---------------------------------------------------------

# Spalten, die zwischen dem ersten Release und der Einfuehrung dieser Datei
# dazugekommen sind. Frueher lief diese Liste bei jedem Start; hier laeuft
# sie genau einmal und wird dann vermerkt.
_SPALTEN_BIS_V1: list[tuple[str, str, str]] = [
    ("deals", "preis_eur", "FLOAT"),
    ("deals", "alarm_preis", "FLOAT"),
    ("deals", "alarm_ausgeloest", "DATETIME"),
    ("deals", "notiz", "TEXT"),
    ("source_configs", "snooze_until", "DATETIME"),
    ("deals", "bild_lokal", "VARCHAR(128)"),
    ("deals", "urteil", "VARCHAR(24)"),
    ("deals", "urteil_text", "TEXT"),
    ("deals", "urteil_am", "DATETIME"),
    ("rules", "min_urteil", "VARCHAR(24)"),
    ("deals", "fehler_score", "INTEGER DEFAULT 0"),
    ("deals", "fehler_stufe", "VARCHAR(16)"),
    ("deals", "fehler_gruende", "JSON"),
    ("deals", "fehler_erwartet_eur", "FLOAT"),
    ("deals", "fehler_am", "DATETIME"),
    ("deals", "fehler_gemeldet_am", "DATETIME"),
    ("rules", "min_fehler_score", "INTEGER"),
    ("deals", "fehler_indizien", "JSON"),
    ("deals", "fehler_urteil_mensch", "VARCHAR(16)"),
    ("deals", "fehler_urteil_am", "DATETIME"),
    ("deals", "erwachsen", "BOOLEAN DEFAULT 0"),
    ("deals", "erwachsen_grund", "TEXT"),
    ("deals", "check_status", "VARCHAR(16)"),
    ("deals", "check_text", "TEXT"),
    ("deals", "check_preis_eur", "FLOAT"),
    ("deals", "check_am", "DATETIME"),
    ("deals", "gratis_hinweis", "VARCHAR(64)"),
    ("rules", "erwachsen", "BOOLEAN DEFAULT 0"),
]


def _schritt_001(conn: Connection) -> None:
    for tabelle, spalte, ddl in _SPALTEN_BIS_V1:
        spalte_ergaenzen(conn, tabelle, spalte, ddl)


def _schritt_002(conn: Connection) -> None:
    from .models import Base
    anzahl = indizes_aus_modellen(conn, Base.metadata)
    if anzahl:
        log.info("Migration: %d fehlende Indizes nachgezogen", anzahl)


SCHRITTE: list[Schritt] = [
    Schritt(1, "Spalten der Releases bis 1.0", _schritt_001),
    Schritt(2, "Fehlende Indizes nachziehen", _schritt_002),
]


# --- Ablauf ---------------------------------------------------------------

def _registry_anlegen(conn: Connection) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TABELLE} (
            nummer INTEGER PRIMARY KEY,
            beschreibung TEXT,
            angewendet_am TEXT NOT NULL
        )
    """))


def angewendete(conn: Connection) -> set[int]:
    if not tabelle_existiert(conn, TABELLE):
        return set()
    return {row[0] for row in conn.execute(text(f"SELECT nummer FROM {TABELLE}"))}


def _vermerken(conn: Connection, schritt: Schritt) -> None:
    conn.execute(
        text(f"INSERT OR REPLACE INTO {TABELLE} "
             f"(nummer, beschreibung, angewendet_am) VALUES (:n, :b, :z)"),
        {"n": schritt.nummer, "b": schritt.beschreibung,
         "z": datetime.now(UTC).isoformat()},
    )


def datenbank_ist_leer(conn: Connection) -> bool:
    """Frische Datenbank? Dann baut create_all den aktuellen Stand."""
    return not [t for t in inspect(conn).get_table_names() if t != TABELLE]


def stempeln(engine: Engine) -> None:
    """Alle Schritte als erledigt vermerken, ohne sie auszufuehren."""
    with engine.begin() as conn:
        _registry_anlegen(conn)
        offen = angewendete(conn)
        for schritt in SCHRITTE:
            if schritt.nummer not in offen:
                _vermerken(conn, schritt)
    log.info("Neue Datenbank: Schema-Stand %d", version(engine))


def migriere(engine: Engine) -> list[int]:
    """Offene Schritte ausfuehren. Gibt die Nummern zurueck, die liefen."""
    with engine.begin() as conn:
        _registry_anlegen(conn)
        erledigt = angewendete(conn)

    gelaufen: list[int] = []
    for schritt in SCHRITTE:
        if schritt.nummer in erledigt:
            continue
        # Eigene Transaktion je Schritt: bricht einer ab, bleibt der Rest.
        with engine.begin() as conn:
            log.info("Migration %03d: %s", schritt.nummer, schritt.beschreibung)
            schritt.aendert(conn)
            _vermerken(conn, schritt)
        gelaufen.append(schritt.nummer)
    return gelaufen


def version(engine: Engine) -> int:
    """Hoechste angewendete Nummer - 0 heisst: noch nichts vermerkt."""
    with engine.connect() as conn:
        if not tabelle_existiert(conn, TABELLE):
            return 0
        wert = conn.execute(text(f"SELECT MAX(nummer) FROM {TABELLE}")).scalar()
        return int(wert or 0)


def neuester_stand() -> int:
    return max((s.nummer for s in SCHRITTE), default=0)
