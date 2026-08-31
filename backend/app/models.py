from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceConfig(Base):
    """Laufzeit-Konfiguration + Health einer Quelle. id == Source.id."""
    __tablename__ = "source_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=900)
    api_key: Mapped[str | None] = mapped_column(String(255))
    options: Mapped[dict] = mapped_column(JSON, default=dict)

    # Health / Circuit Breaker
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_errors: Mapped[int] = mapped_column(Integer, default=0)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    verification: Mapped[str] = mapped_column(String(16), default="unverified")
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # HTTP-Cache
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    items: Mapped[int] = mapped_column(Integer, default=0)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[int] = mapped_column(primary_key=True)
    url_hash: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    titel: Mapped[str] = mapped_column(Text)
    titel_norm: Mapped[str] = mapped_column(Text, index=True)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    bild: Mapped[str | None] = mapped_column(Text)

    preis: Mapped[float | None] = mapped_column(Float)
    originalpreis: Mapped[float | None] = mapped_column(Float)
    rabatt_prozent: Mapped[float | None] = mapped_column(Float)
    waehrung: Mapped[str] = mapped_column(String(8), default="EUR")
    ist_gratis: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    haendler: Mapped[str | None] = mapped_column(String(128), index=True)
    kategorie: Mapped[str | None] = mapped_column(String(64))
    quelle: Mapped[str] = mapped_column(String(64), index=True)
    temperatur: Mapped[float | None] = mapped_column(Float)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    veroeffentlicht_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, index=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    # Wenn dieser Deal ein Duplikat ist: Verweis auf das Original.
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("deals.id"), index=True)
    also_from: Mapped[list] = mapped_column(JSON, default=list)
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    roh: Mapped[dict] = mapped_column(JSON, default=dict)


Index("ix_deals_first_seen_desc", Deal.first_seen.desc())
Index("ix_deals_gratis_seen", Deal.ist_gratis, Deal.first_seen.desc())


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[str] = mapped_column(String(16), default="NORMAL")  # SOFORT|NORMAL

    keywords: Mapped[list] = mapped_column(JSON, default=list)           # ODER
    required_keywords: Mapped[list] = mapped_column(JSON, default=list)  # UND
    blacklist: Mapped[list] = mapped_column(JSON, default=list)

    max_preis: Mapped[float | None] = mapped_column(Float)
    min_rabatt_prozent: Mapped[float | None] = mapped_column(Float)
    nur_gratis: Mapped[bool] = mapped_column(Boolean, default=False)
    min_temperatur: Mapped[float | None] = mapped_column(Float)

    sources: Mapped[list] = mapped_column(JSON, default=list)     # leer = alle
    kategorien: Mapped[list] = mapped_column(JSON, default=list)
    haendler: Mapped[list] = mapped_column(JSON, default=list)

    channels: Mapped[list] = mapped_column(JSON, default=list)    # Channel-IDs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    last_match: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("rule_id", "deal_id", name="uq_rule_deal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"),
                                         index=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"),
                                         index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deal: Mapped["Deal"] = relationship(lazy="joined")


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32))   # telegram|smtp|webhook|ntfy
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_count: Mapped[int] = mapped_column(Integer, default=0)


class NotificationLog(Base):
    __tablename__ = "notification_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, index=True)
    channel_type: Mapped[str] = mapped_column(String(32))
    rule_id: Mapped[int | None] = mapped_column(Integer)
    rule_name: Mapped[str | None] = mapped_column(String(128))
    deal_id: Mapped[int | None] = mapped_column(Integer)
    deal_titel: Mapped[str | None] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, index=True)


class ClaimEvent(Base):
    """Aus den Logs des Claimer-Containers geparst."""
    __tablename__ = "claim_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32))     # epic|prime|gog
    titel: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))       # claimed|already|failed
    detail: Mapped[str | None] = mapped_column(Text)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                              default=utcnow, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)


class LogEntry(Base):
    __tablename__ = "log_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                         index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    logger: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
