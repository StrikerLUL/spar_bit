from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index,
                        Integer, String, Text, TypeDecorator, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Zeitstempel, die auch nach dem Laden noch eine Zeitzone haben.

    SQLite kennt keinen Datentyp fuer Datum; SQLAlchemy legt den Text ab und
    gibt beim Lesen ein naives datetime zurueck - auch bei
    DateTime(timezone=True). Jeder Vergleich mit utcnow() wirft dann
    "can't compare offset-naive and offset-aware datetimes".

    Das war kein theoretisches Problem: der Schutzschalter verglich
    circuit_open_until mit utcnow() und starb daran, sobald er einmal
    zugemacht hatte - die Quelle lief nie wieder an, und im Log stand ein
    TypeError statt "gesperrt". Dasselbe traf die Stummschaltung per
    Telegram und die Sperrfrist des Preisfehler-Waechters.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(UTCDateTime)


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
    circuit_open_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Manuell stummgeschaltet (z.B. per Telegram-Knopf), laeuft von selbst ab.
    snooze_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_run: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_errors: Mapped[int] = mapped_column(Integer, default=0)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    verification: Mapped[str] = mapped_column(String(16), default="unverified")
    last_verified: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # HTTP-Cache
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
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
    # Preis in EUR umgerechnet - CheapShark liefert USD, HotUKDeals GBP.
    # Regeln rechnen hiermit, damit "max 20 EUR" quellenuebergreifend stimmt.
    preis_eur: Mapped[float | None] = mapped_column(Float, index=True)
    # Gilt der Preis je Zeitraum ("monat", "jahr", "woche")? Ohne diese
    # Angabe steht ein Abo fuer 4,99 im Monat neben einem Kopfhoerer fuer
    # 4,99, als waere es dasselbe Angebot.
    preis_zeitraum: Mapped[str | None] = mapped_column(String(8), index=True)
    # Was das Angebot pro Monat kostet - der einzige Wert, mit dem sich
    # Abos untereinander vergleichen lassen.
    preis_monat_eur: Mapped[float | None] = mapped_column(Float, index=True)
    preis_hinweis: Mapped[str | None] = mapped_column(String(48))
    ist_gratis: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    haendler: Mapped[str | None] = mapped_column(String(128), index=True)
    kategorie: Mapped[str | None] = mapped_column(String(64))
    # Worum es inhaltlich geht - siehe app/kategorien.py. Gespeichert als
    # "|speicher|computer|", damit ein LIKE '%|ssd|%' nicht versehentlich
    # in einem laengeren Schluessel landet. Mehrfach, weil ein
    # Gaming-Notebook mit SSD zu Recht unter drei Marken auftaucht.
    kategorien: Mapped[str | None] = mapped_column(Text, index=True)
    quelle: Mapped[str] = mapped_column(String(64), index=True)
    temperatur: Mapped[float | None] = mapped_column(Float)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    veroeffentlicht_am: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime,
                                                 default=utcnow, index=True)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    # Wenn dieser Deal ein Duplikat ist: Verweis auf das Original.
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("deals.id"), index=True)
    also_from: Mapped[list] = mapped_column(JSON, default=list)
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Dateiname im lokalen Bild-Cache, falls das Bild geholt werden konnte.
    bild_lokal: Mapped[str | None] = mapped_column(String(128))
    # Preisurteil aus der eigenen Historie - siehe app/verdict.py.
    urteil: Mapped[str | None] = mapped_column(String(24), index=True)
    urteil_text: Mapped[str | None] = mapped_column(Text)
    urteil_am: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Preisfehler-Verdacht - siehe app/pricefehler.py. Getrennt vom Urteil,
    # weil es eine andere Frage beantwortet: nicht "ist der Preis gut", sondern
    # "hat sich hier jemand vertippt".
    fehler_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    fehler_stufe: Mapped[str | None] = mapped_column(String(16), index=True)
    fehler_gruende: Mapped[list] = mapped_column(JSON, default=list)
    # Stabile Schluessel der Indizien, die zugeschlagen haben - Grundlage
    # fuer die Auswertung "welches Indiz lag bei echten Funden wie oft
    # richtig". Die Gruende darueber sind freier Text und taugen dafuer nicht.
    fehler_indizien: Mapped[list] = mapped_column(JSON, default=list)
    # Rueckmeldung des Benutzers: "echt", "fehlalarm" oder None.
    fehler_urteil_mensch: Mapped[str | None] = mapped_column(String(16), index=True)
    fehler_urteil_am: Mapped[datetime | None] = mapped_column(UTCDateTime)
    fehler_erwartet_eur: Mapped[float | None] = mapped_column(Float)
    fehler_am: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Wann zuletzt wegen dieses Preisfehlers gemeldet wurde - verhindert,
    # dass derselbe Fund bei jedem Quellenlauf erneut das Handy weckt.
    fehler_gemeldet_am: Mapped[datetime | None] = mapped_column(
        UTCDateTime)

    # Preisalarm: melden, sobald der Preis unter diese Schwelle faellt.
    alarm_preis: Mapped[float | None] = mapped_column(Float)
    alarm_ausgeloest: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notiz: Mapped[str | None] = mapped_column(Text)

    # 18+ - siehe app/erwachsen.py. Deals mit dieser Marke erscheinen
    # ausschliesslich auf der eigenen Seite; jede andere Abfrage klammert
    # sie aus. Die Marke faellt nie wieder weg: was einmal als 18+ erkannt
    # wurde, rutscht auch dann nicht in den normalen Feed, wenn es spaeter
    # aus einer harmlosen Quelle noch einmal hereinkommt.
    erwachsen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    erwachsen_grund: Mapped[str | None] = mapped_column(Text)

    # Gegenprobe auf der Zielseite - siehe app/gratischeck.py.
    check_status: Mapped[str | None] = mapped_column(String(16), index=True)
    check_text: Mapped[str | None] = mapped_column(Text)
    check_preis_eur: Mapped[float | None] = mapped_column(Float)
    check_am: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Stand im Titel ein Gratis-Wort, das sich auf etwas anderes bezog?
    # ("gilt nur für den Versand") - erklaert, warum hier kein Gratis-Schild
    # haengt, obwohl "gratis" im Text steht.
    gratis_hinweis: Mapped[str | None] = mapped_column(String(64))

    roh: Mapped[dict] = mapped_column(JSON, default=dict)


Index("ix_deals_first_seen_desc", Deal.first_seen.desc())
# Jede Feed-Abfrage filtert auf erwachsen=0 und sortiert nach Datum.
Index("ix_deals_erwachsen_seen", Deal.erwachsen, Deal.first_seen.desc())
Index("ix_deals_gratis_seen", Deal.ist_gratis, Deal.first_seen.desc())
# Die Preisfehler-Seite fragt genau danach - und zwar oft.
Index("ix_deals_fehler", Deal.fehler_stufe, Deal.first_seen.desc())


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
    # Nur Deals ab dieser Urteilsstufe (siehe app/verdict.py).
    min_urteil: Mapped[str | None] = mapped_column(String(24))
    # Nur Deals mit mindestens so vielen Preisfehler-Punkten
    # (siehe app/pricefehler.py). 0 / None = egal.
    min_fehler_score: Mapped[int | None] = mapped_column(Integer)
    # Darf diese Regel 18+-Funde sehen? Ohne dieses Haekchen niemals -
    # sonst wuerde eine harmlose Regel wie "alles unter 5 Euro" den
    # ganzen 18+-Bereich aufs Handy schicken.
    erwachsen: Mapped[bool] = mapped_column(Boolean, default=False)

    sources: Mapped[list] = mapped_column(JSON, default=list)     # leer = alle
    kategorien: Mapped[list] = mapped_column(JSON, default=list)
    haendler: Mapped[list] = mapped_column(JSON, default=list)

    channels: Mapped[list] = mapped_column(JSON, default=list)    # Channel-IDs
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    last_match: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("rule_id", "deal_id", name="uq_rule_deal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"),
                                         index=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"),
                                         index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime,
                                                 default=utcnow, index=True)
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deal: Mapped["Deal"] = relationship(lazy="joined")


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32))   # telegram|smtp|webhook|ntfy
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used: Mapped[datetime | None] = mapped_column(UTCDateTime)
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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime,
                                                 default=utcnow, index=True)


class ClaimEvent(Base):
    """Aus den Logs des Claimer-Containers geparst."""
    __tablename__ = "claim_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32))     # epic|prime|gog
    titel: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))       # claimed|already|failed
    detail: Mapped[str | None] = mapped_column(Text)
    seen_at: Mapped[datetime] = mapped_column(UTCDateTime,
                                              default=utcnow, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)


class LogEntry(Base):
    __tablename__ = "log_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow,
                                         index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    logger: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class PriceHistory(Base):
    """Ein Eintrag je beobachteter Preisaenderung - Grundlage der Sparkline."""
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"),
                                         index=True)
    preis: Mapped[float] = mapped_column(Float)
    waehrung: Mapped[str] = mapped_column(String(8), default="EUR")
    quelle: Mapped[str | None] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow,
                                         index=True)


class SavedSearch(Base):
    """Gespeicherter Filter im Feed - ein Klick statt jedes Mal neu einstellen."""
    __tablename__ = "saved_searches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    filter: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DealOffer(Base):
    """Ein Angebot fuer denselben Artikel aus einer bestimmten Quelle.

    Derselbe Deal kommt aus mydealz, Reddit und CheapShark - oft zu
    verschiedenen Preisen und mit verschiedenen Links. Der Deal-Datensatz
    haelt den besten Preis; hier steht, welche Quelle was verlangt.
    """
    __tablename__ = "deal_offers"
    __table_args__ = (UniqueConstraint("deal_id", "quelle", name="uq_deal_quelle"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"),
                                         index=True)
    quelle: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    preis: Mapped[float | None] = mapped_column(Float)
    waehrung: Mapped[str] = mapped_column(String(8), default="EUR")
    preis_eur: Mapped[float | None] = mapped_column(Float)
    originalpreis: Mapped[float | None] = mapped_column(Float)
    rabatt_prozent: Mapped[float | None] = mapped_column(Float)
    haendler: Mapped[str | None] = mapped_column(String(128))
    ist_gratis: Mapped[bool] = mapped_column(Boolean, default=False)
    zuerst_gesehen: Mapped[datetime] = mapped_column(UTCDateTime,
                                                     default=utcnow)
    zuletzt_gesehen: Mapped[datetime] = mapped_column(UTCDateTime,
                                                      default=utcnow)


class LoginAttempt(Base):
    """Fehlversuche bei der Anmeldung, je Absender-IP.

    Liegt in der Datenbank und nicht im Speicher: sonst haette ein Neustart
    die Sperre aufgehoben, und genau darauf wuerde ein Angreifer setzen.
    """
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    benutzername: Mapped[str | None] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow,
                                         index=True)


class CachedImage(Base):
    """Lokal abgelegtes Deal-Bild.

    Ohne das laedt jede Deal-Karte direkt beim Haendler - der sieht dann bei
    jedem Oeffnen des Feeds deine IP.
    """
    __tablename__ = "cached_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    url_hash: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    quell_url: Mapped[str] = mapped_column(Text)
    datei: Mapped[str | None] = mapped_column(String(128))
    content_type: Mapped[str | None] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    fehler: Mapped[str | None] = mapped_column(Text)
    geholt_am: Mapped[datetime] = mapped_column(UTCDateTime,
                                                default=utcnow, index=True)


class WatchItem(Base):
    """Ein selbst beobachteter Artikel.

    Der Unterschied zum Rest von SparBit: hier wartet man nicht darauf, dass
    jemand einen Deal postet, sondern schaut selbst regelmaessig nach.
    """
    __tablename__ = "watch_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    ziel_preis: Mapped[float | None] = mapped_column(Float)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    intervall_minuten: Mapped[int] = mapped_column(Integer, default=180)

    letzter_preis: Mapped[float | None] = mapped_column(Float)
    waehrung: Mapped[str] = mapped_column(String(8), default="EUR")
    bester_preis: Mapped[float | None] = mapped_column(Float)
    bild: Mapped[str | None] = mapped_column(Text)
    haendler: Mapped[str | None] = mapped_column(String(128))

    letzter_lauf: Mapped[datetime | None] = mapped_column(UTCDateTime)
    letzter_erfolg: Mapped[datetime | None] = mapped_column(UTCDateTime)
    letzter_fehler: Mapped[str | None] = mapped_column(Text)
    fehler_in_folge: Mapped[int] = mapped_column(Integer, default=0)
    zuletzt_gemeldet: Mapped[float | None] = mapped_column(Float)
    erstellt_am: Mapped[datetime] = mapped_column(UTCDateTime,
                                                  default=utcnow)


class WatchPrice(Base):
    """Preispunkt eines beobachteten Artikels."""
    __tablename__ = "watch_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watch_items.id",
                                                     ondelete="CASCADE"), index=True)
    preis: Mapped[float] = mapped_column(Float)
    waehrung: Mapped[str] = mapped_column(String(8), default="EUR")
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow,
                                         index=True)


class Interaction(Base):
    """Was ich mit einem Deal gemacht habe - Grundlage des lernenden Feeds.

    Ohne diese Spuren kann SparBit nur raten, was mich interessiert.
    """
    __tablename__ = "interactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"),
                                         index=True)
    # angesehen | geoeffnet | geklickt | gemerkt | alarm | verworfen
    art: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow,
                                         index=True)


class ApiToken(Base):
    """Zugangstoken fuer die Browser-Erweiterung.

    Die Erweiterung laeuft auf einer fremden Seite und kann das
    Sitzungs-Cookie nicht nutzen - sie braucht einen eigenen Schluessel,
    der sich einzeln zurueckziehen laesst.
    """
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    praefix: Mapped[str] = mapped_column(String(12))
    erstellt_am: Mapped[datetime] = mapped_column(UTCDateTime,
                                                  default=utcnow)
    zuletzt_genutzt: Mapped[datetime | None] = mapped_column(UTCDateTime)
