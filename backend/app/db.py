from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base, Setting

log = logging.getLogger(__name__)

settings.data_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")       # gleichzeitig lesen + schreiben
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Spalten, die nach dem ersten Release dazugekommen sind. SQLite kann
# ADD COLUMN, also reicht das statt eines Migrations-Frameworks - fuer eine
# Single-User-App waere Alembic hier mehr Ballast als Nutzen.
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
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


def _migrate(conn) -> None:
    """Fehlende Spalten nachziehen. Idempotent - laeuft bei jedem Start."""
    for table, column, ddl in _ADDED_COLUMNS:
        exists = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        if not exists:
            continue                      # Tabelle legt create_all gleich neu an
        if any(row[1] == column for row in exists):
            continue
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        log.info("Migration: Spalte %s.%s ergaenzt", table, column)


def init_db() -> None:
    with engine.begin() as conn:
        _migrate(conn)
    Base.metadata.create_all(engine)

    # Volltextindex nach create_all, damit die deals-Tabelle sicher existiert.
    from .search import einrichten, fts_verfuegbar
    if fts_verfuegbar(engine):
        with engine.begin() as conn:
            einrichten(conn)
    with SessionLocal() as db:
        if not get_setting(db, "secret_key"):
            set_setting(db, "secret_key", secrets.token_urlsafe(48))
            db.commit()
            log.info("Neuer secret_key erzeugt und in der DB abgelegt")


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Key/Value-Settings ---------------------------------------------------

def get_setting(db: Session, key: str, default=None):
    row = db.scalar(select(Setting).where(Setting.key == key))
    return row.value if row else default


def set_setting(db: Session, key: str, value) -> None:
    row = db.scalar(select(Setting).where(Setting.key == key))
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def secret_key() -> str:
    if settings.secret_key:
        return settings.secret_key
    with SessionLocal() as db:
        key = get_setting(db, "secret_key")
        if not key:
            key = secrets.token_urlsafe(48)
            set_setting(db, "secret_key", key)
            db.commit()
        return key
