"""Volltextsuche - SQLite-FTS5 oder PostgreSQL, dieselbe Syntax.

Vorher lief die Suche als LIKE '%wort%' ueber drei Spalten - das kann keinen
Index nutzen und liest bei jeder Anfrage die ganze Tabelle. Bei ein paar
tausend Deals faellt das nicht auf, bei 50.000 schon.

Drei Motoren, in dieser Reihenfolge:

**FTS5** - der Normalfall. In den meisten SQLite-Builds enthalten, aber
nicht in allen.

**PostgreSQL** - fuer alle, die SPARBIT_DB_URL_OVERRIDE gesetzt haben.
Lange fiel die Suche dort stillschweigend auf LIKE zurueck: die
dokumentierte Syntax stand im README, funktionierte aber genau dann
nicht, wenn jemand die ebenfalls dokumentierte Postgres-Option nutzte.
Jetzt uebersetzt derselbe Parser in `tsquery` statt in eine FTS5-Abfrage,
und ein Ausdrucksindex (GIN) macht es schnell.

**LIKE** - wenn beides nicht geht. Lieber langsam als kaputt.

Suchsyntax (ueberall gleich):
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

FTS5 = "fts5"
POSTGRES = "postgres"
LIKE = "like"

# Welche Sprache Postgres beim Zerlegen annimmt. Deutsch, weil die
# Deal-Titel deutsch sind: "Kopfhoerer" und "Kopfhoerern" sollen
# denselben Treffer ergeben.
PG_SPRACHE = "german"

# Der Ausdruck, ueber den in Postgres gesucht wird. Steht hier genau
# einmal, weil Index und Abfrage *zeichengleich* sein muessen - weicht
# eines ab, wird der Index still nicht benutzt und die Suche ist wieder
# ein Tabellendurchlauf.
PG_VEKTOR = ("to_tsvector('" + PG_SPRACHE + "', "
             "coalesce(titel,'') || ' ' || coalesce(beschreibung,'') || "
             "' ' || coalesce(haendler,''))")

_motor: str | None = None


def motor(engine: Engine | None = None) -> str:
    """Welcher Volltextmotor gilt - einmal ermittelt, dann gemerkt."""
    global _motor
    if _motor is not None:
        return _motor
    if engine is None:
        return LIKE                 # ohne Engine wird nichts festgelegt

    if engine.dialect.name.startswith("postgres"):
        _motor = POSTGRES
        return _motor

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS "
                              "_fts_probe USING fts5(x)"))
            conn.execute(text("DROP TABLE IF EXISTS _fts_probe"))
            conn.commit()
        _motor = FTS5
    except Exception as exc:
        log.warning("FTS5 nicht verfuegbar (%s) - Suche laeuft ueber LIKE", exc)
        _motor = LIKE
    return _motor


def motor_zuruecksetzen() -> None:
    """Nur fuer Tests: der naechste Aufruf ermittelt wieder neu."""
    global _motor
    _motor = None


def fts_verfuegbar(engine: Engine) -> bool:
    """Gibt es ueberhaupt einen Volltextindex? (Name aus Bestandsgruenden.)"""
    return motor(engine) != LIKE


def einrichten(conn: Connection) -> None:
    """Index anlegen. Idempotent, laeuft bei jedem Start."""
    if conn.dialect.name.startswith("postgres"):
        _einrichten_postgres(conn)
        return
    _einrichten_fts5(conn)


def _einrichten_postgres(conn: Connection) -> None:
    """Ein GIN-Index auf den Suchausdruck - keine zweite Tabelle noetig.

    Ein Ausdrucksindex statt einer eigenen tsvector-Spalte: der braucht
    weder eine Migration noch Trigger, die ihn synchron halten. Postgres
    pflegt ihn beim Schreiben selbst, und damit kann kein Codepfad
    vergessen, den Index nachzuziehen - derselbe Grund, aus dem es bei
    FTS5 Trigger gibt.
    """
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS ix_deals_volltext ON deals USING GIN ({PG_VEKTOR})"))
    log.info("Volltextindex (PostgreSQL/GIN) steht bereit")


def _einrichten_fts5(conn: Connection) -> None:
    """Index und Trigger fuer SQLite anlegen."""
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
    """Index verwerfen und neu fuellen. Bei Postgres nicht noetig."""
    if conn.dialect.name.startswith("postgres"):
        return          # ein Ausdrucksindex ist nie aus dem Tritt
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


def zu_ts_query(eingabe: str) -> str:
    """Dieselbe Eingabe, uebersetzt in eine PostgreSQL-`tsquery`.

    Bewusst ein zweiter Uebersetzer statt einer gemeinsamen Zwischenform:
    die beiden Sprachen sehen sich aehnlich und unterscheiden sich genau
    dort, wo es weh tut (`*` gegen `:*`, `AND` gegen `&`, Phrasen in
    Anfuehrungszeichen gegen den `<->`-Operator). Eine gemeinsame Form
    haette an jeder dieser Stellen ein `if` gebraucht - und Fehler dort
    sehen aus wie "findet nichts", nicht wie ein Fehler.

    `websearch_to_tsquery` waere kuerzer, kann aber keine Praefixe -
    und `kopfhoer*` ist genau das, wofuer die Suchzeile da ist.
    """
    roh = _ERLAUBT.sub(" ", eingabe or "").strip()
    if not roh:
        return ""

    positiv: list[str] = []
    negativ: list[str] = []

    # Phrasen: aufeinanderfolgende Woerter, mit <-> verkettet.
    for phrase in re.findall(r'"([^"]+)"', roh):
        woerter = phrase.split()
        if woerter:
            positiv.append("(" + " <-> ".join(woerter) + ")")
    rest = re.sub(r'"[^"]*"', " ", roh)

    for wort in rest.split():
        ausschluss = wort.startswith("-")
        praefix = wort.endswith("*")
        kern = wort.lstrip("-").rstrip("*")
        if not kern:
            continue
        (negativ if ausschluss else positiv).append(f"{kern}:*" if praefix else kern)

    if not positiv:
        return ""

    abfrage = " & ".join(positiv)
    for begriff in negativ:
        abfrage += f" & !{begriff}"
    return abfrage


def match_bedingung(eingabe: str):
    """SQL-Bedingung fuer die Volltextsuche, oder None.

    Bewusst eine Unterabfrage statt einer Liste von IDs: eine Liste muesste
    begrenzt werden, und dann waere die angezeigte Trefferzahl falsch
    (5000 statt der echten 23.000). So zaehlt und paginiert die Datenbank.
    """
    from sqlalchemy import column, select, table, text

    if motor() == POSTGRES:
        abfrage = zu_ts_query(eingabe)
        if not abfrage:
            return None
        deals = table("deals", column("id"))
        return select(deals.c.id).where(
            text(f"{PG_VEKTOR} @@ to_tsquery('{PG_SPRACHE}', :fts_q)")
            .bindparams(fts_q=abfrage))

    abfrage = zu_fts_query(eingabe)
    if not abfrage:
        return None
    fts = table(TABELLE, column("rowid"))
    return select(fts.c.rowid).where(
        text(f"{TABELLE} MATCH :fts_q").bindparams(fts_q=abfrage))


def treffer_ids(db: Session, eingabe: str, limit: int = 5000) -> list[int] | None:
    """IDs der passenden Deals, beste zuerst. None = Suche nicht moeglich.

    Nur fuer Faelle, in denen die Rangfolge von FTS gebraucht wird; die
    normale Feed-Suche nutzt match_bedingung().
    """
    if motor() == POSTGRES:
        abfrage = zu_ts_query(eingabe)
        if not abfrage:
            return None
        satz = (f"SELECT id FROM deals "
                f"WHERE {PG_VEKTOR} @@ to_tsquery('{PG_SPRACHE}', :q) "
                f"ORDER BY ts_rank({PG_VEKTOR}, to_tsquery('{PG_SPRACHE}', :q)) DESC "
                f"LIMIT :limit")
    else:
        abfrage = zu_fts_query(eingabe)
        if not abfrage:
            return None
        satz = (f"SELECT rowid FROM {TABELLE} WHERE {TABELLE} MATCH :q "
                f"ORDER BY rank LIMIT :limit")

    try:
        zeilen = db.execute(text(satz), {"q": abfrage, "limit": limit}).all()
    except Exception as exc:
        log.warning("Volltextsuche fehlgeschlagen (%s) - weiche auf LIKE aus", exc)
        return None
    return [zeile[0] for zeile in zeilen]
