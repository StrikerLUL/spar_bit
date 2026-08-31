from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, select
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


def init_db() -> None:
    Base.metadata.create_all(engine)
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
