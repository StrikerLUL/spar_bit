"""Volltextsuche ueber SQLite-FTS5.

Vorher lief die Suche als LIKE '%wort%' ueber drei Spalten - das kann keinen
Index nutzen und liest bei jeder Anfrage die ganze Tabelle. Bei ein paar
tausend Deals faellt das nicht auf, bei 50.000 schon.

FTS5 ist in den meisten SQLite-Builds enthalten, aber nicht in allen. Fehlt
es, faellt die Suche automatisch auf LIKE zurueck - lieber langsam als kaputt.

Suchsyntax:
    lego technic      beide Woerter (UND)
    "nintendo switch" genau diese Wortfolge
    ssd -gebraucht    "gebraucht" ausschliessen
    kopfhoer*         Praefix
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

TABELLE = "deals_fts"
_verfuegbar: bool | None = None


def fts_verfuegbar(engine: Engine) -> bool:
    """Einmal pruefen, ob diese SQLite-Version FTS5 kann."""
    global _verfuegbar
    if _verfuegbar is not None:
        return _verfuegbar
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS "
                              "_fts_probe USING fts5(x)"))
            conn.execute(text("DROP TABLE IF EXISTS _fts_probe"))
            conn.commit()
        _verfuegbar = True
    except Exception as exc:
        log.warning("FTS5 nicht verfuegbar (%s) - Suche laeuft ueber LIKE", exc)
        _verfuegbar = False
    return _verfuegbar


def einrichten(conn: Connection) -> None:
    """Index und Trigger anlegen. Idempotent, laeuft bei jedem Start."""
    conn.execute(text(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {TABELLE} USING fts5(
            titel, beschreibung, haendler,
            content='deals', content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """))

    # Trigger halten den Index automatisch synchron - so kann kein Codepfad
    # vergessen, ihn zu pflegen.
    conn.execute(text(f"""
        CREATE TRIGGER IF NOT EXISTS deals_fts_ai AFTER INSERT ON deals BEGIN
            INSERT INTO {TABELLE}(rowid, titel, beschreibung, haendler)
            VALUES (new.id, new.titel, new.beschreibung, new.haendler);
        END
    """))
    conn.execute(text(f"""
        CREATE TRIGGER IF NOT EXISTS deals_fts_ad AFTER DELETE ON deals BEGIN
            INSERT INTO {TABELLE}({TABELLE}, rowid, titel, beschreibung, haendler)
            VALUES ('delete', old.id, old.titel, old.beschreibung, old.haendler);
        END
    """))
    conn.execute(text(f"""
        CREATE TRIGGER IF NOT EXISTS deals_fts_au AFTER UPDATE ON deals BEGIN
            INSERT INTO {TABELLE}({TABELLE}, rowid, titel, beschreibung, haendler)
            VALUES ('delete', old.id, old.titel, old.beschreibung, old.haendler);
            INSERT INTO {TABELLE}(rowid, titel, beschreibung, haendler)
            VALUES (new.id, new.titel, new.beschreibung, new.haendler);
        END
    """))

    # Bestehende Deals einmalig nachtragen.
    leer = conn.execute(text(f"SELECT 1 FROM {TABELLE} LIMIT 1")).first() is None
    hat_deals = conn.execute(text("SELECT 1 FROM deals LIMIT 1")).first() is not None
    if leer and hat_deals:
        conn.execute(text(f"INSERT INTO {TABELLE}({TABELLE}) VALUES('rebuild')"))
        log.info("Volltextindex fuer bestehende Deals aufgebaut")


def neu_aufbauen(conn: Connection) -> None:
    conn.execute(text(f"INSERT INTO {TABELLE}({TABELLE}) VALUES('rebuild')"))


# FTS5 hat eigene Sonderzeichen. Alles, was wir nicht bewusst unterstuetzen,
# wird entfernt, damit eine Nutzereingabe nie einen Syntaxfehler ausloest.
_ERLAUBT = re.compile(r'[^\w\s"*\-äöüßÄÖÜ]', re.UNICODE)


# Woerter, die FTS5 als Operator liest. Als Suchbegriff muessen sie in
# Anfuehrungszeichen, sonst gibt es einen Syntaxfehler.
_OPERATOREN = {"and", "or", "not", "near"}


def _begriff(wort: str, praefix: bool) -> str:
    if wort.lower() in _OPERATOREN:
        return f'"{wort}"'          # als Wort suchen, nicht als Operator
    return f"{wort}*" if praefix else wort


def zu_fts_query(eingabe: str) -> str:
    """Nutzereingabe in eine FTS5-Abfrage uebersetzen.

    Bewusst konservativ: FTS5 wirft bei ungueltiger Syntax eine Ausnahme,
    und ein Tippfehler in der Suchzeile darf keine Fehlermeldung erzeugen.
    Positive Begriffe werden mit AND verknuepft, ausgeschlossene haengen als
    NOT hinten dran - so bleibt die Reihenfolge immer gueltig.
    """
    roh = _ERLAUBT.sub(" ", eingabe or "").strip()
    if not roh:
        return ""

    positiv: list[str] = []
    negativ: list[str] = []

    # Phrasen in Anfuehrungszeichen zuerst herausloesen.
    for phrase in re.findall(r'"([^"]+)"', roh):
        sauber = phrase.strip()
        if sauber:
            positiv.append(f'"{sauber}"')
    rest = re.sub(r'"[^"]*"', " ", roh)

    for wort in rest.split():
        ausschluss = wort.startswith("-")
        praefix = wort.endswith("*")
        kern = wort.lstrip("-").rstrip("*")
        if not kern:
            continue
        (negativ if ausschluss else positiv).append(_begriff(kern, praefix))

    # Eine reine Ausschlussliste ergibt keine sinnvolle Treffermenge.
    if not positiv:
        return ""

    abfrage = " AND ".join(positiv)
    for begriff in negativ:
        abfrage += f" NOT {begriff}"
    return abfrage


def match_bedingung(eingabe: str):
    """SQL-Bedingung fuer die Volltextsuche, oder None.

    Bewusst eine Unterabfrage statt einer Liste von IDs: eine Liste muesste
    begrenzt werden, und dann waere die angezeigte Trefferzahl falsch
    (5000 statt der echten 23.000). So zaehlt und paginiert die Datenbank.
    """
    abfrage = zu_fts_query(eingabe)
    if not abfrage:
        return None
    from sqlalchemy import column, select, table, text

    fts = table(TABELLE, column("rowid"))
    return select(fts.c.rowid).where(
        text(f"{TABELLE} MATCH :fts_q").bindparams(fts_q=abfrage))


def treffer_ids(db: Session, eingabe: str, limit: int = 5000) -> list[int] | None:
    """IDs der passenden Deals, beste zuerst. None = Suche nicht moeglich.

    Nur fuer Faelle, in denen die Rangfolge von FTS gebraucht wird; die
    normale Feed-Suche nutzt match_bedingung().
    """
    abfrage = zu_fts_query(eingabe)
    if not abfrage:
        return None
    try:
        zeilen = db.execute(
            text(f"SELECT rowid FROM {TABELLE} WHERE {TABELLE} MATCH :q "
                 f"ORDER BY rank LIMIT :limit"),
            {"q": abfrage, "limit": limit},
        ).all()
    except Exception as exc:
        log.warning("Volltextsuche fehlgeschlagen (%s) - weiche auf LIKE aus", exc)
        return None
    return [zeile[0] for zeile in zeilen]
