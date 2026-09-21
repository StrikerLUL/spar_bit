"""APScheduler-Runner mit isolierter Fehlerbehandlung + Circuit Breaker.

Faellt eine Quelle aus, laufen alle anderen weiter. Nach X Fehlern in Folge
wird die Quelle fuer eine Weile gesperrt und im UI rot markiert.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import delete, desc, select

from . import erwachsen as erwachsen_mod
from . import gratischeck, pricefehler
from .config import settings
from .db import SessionLocal, get_setting, session_scope
from .events import broker
from .http import NotModified, PoliteClient, RateLimited
from .images import aufraeumen as bilder_aufraeumen
from .images import hole_fuer_deals
from .models import Deal, LogEntry, NotificationLog, SourceConfig, SourceRun, utcnow
from .pipeline import (
    check_price_alarms,
    dispatch,
    dispatch_alarms,
    dispatch_preisfehler,
    dispatch_watchdog,
    ingest,
    match_rules,
    send_digest,
)
from .sources import all_sources, get_source
from .sources.base import FetchContext
from .verdict import aktualisiere as urteile_aktualisieren

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")
http: PoliteClient | None = None
_locks: dict[str, asyncio.Lock] = {}


def get_http() -> PoliteClient:
    global http
    if http is None:
        http = PoliteClient(user_agent=settings.user_agent,
                            timeout=settings.http_timeout,
                            per_host_delay=settings.per_host_delay)
    return http


def ensure_source_rows() -> None:
    """Fuer jede registrierte Quelle eine Config-Zeile anlegen (aus)."""
    with session_scope() as db:
        existing = {row.id for row in db.scalars(select(SourceConfig))}
        for src in all_sources():
            if src.id in existing:
                continue
            db.add(SourceConfig(
                id=src.id,
                enabled=False,
                interval_seconds=src.default_interval,
                options=dict(src.default_options),
                verification=src.verification.value,
            ))
            log.info("Quelle '%s' registriert", src.id)


def build_context(cfg: SourceConfig) -> FetchContext:
    return FetchContext(http=get_http(), options=dict(cfg.options or {}),
                        api_key=cfg.api_key, log=log)


async def run_source(source_id: str, manual: bool = False) -> dict:
    """Einen Quellen-Lauf ausfuehren. Faengt alles ab - wirft nie."""
    lock = _locks.setdefault(source_id, asyncio.Lock())
    if lock.locked():
        return {"source_id": source_id, "skipped": "laeuft bereits"}

    async with lock:
        src = get_source(source_id)
        if src is None:
            return {"source_id": source_id, "error": "unbekannte Quelle"}

        with SessionLocal() as db:
            cfg = db.get(SourceConfig, source_id)
            if cfg is None:
                return {"source_id": source_id, "error": "keine Konfiguration"}
            # Auch bei manuellem Start: ist der 18+-Bereich zu, laeuft keine
            # 18+-Quelle. Der Schalter unter Logs & System ist die einzige
            # Stelle, an der das aufgeht - nicht ein vergessener Job, nicht
            # ein Knopf im Quellen-Dialog, nicht die CLI.
            if erwachsen_mod.quelle_ist_18(source_id) \
                    and not erwachsen_mod.ist_aktiv(db):
                return {"source_id": source_id,
                        "skipped": "18+-Bereich nicht freigeschaltet"}
            if not manual and not cfg.enabled:
                return {"source_id": source_id, "skipped": "deaktiviert"}
            if not manual and cfg.circuit_open_until and cfg.circuit_open_until > utcnow():
                return {"source_id": source_id, "skipped": "Circuit Breaker offen"}
            if not manual and cfg.snooze_until and cfg.snooze_until > utcnow():
                return {"source_id": source_id, "skipped": "stummgeschaltet"}
            ctx = build_context(cfg)

        t0 = time.monotonic()
        error: str | None = None
        # Gedrosselt ist nicht kaputt: ein 429 zaehlt zwar als Fehlversuch,
        # macht aber den Schutzschalter nicht zu - sonst schaltet sich eine
        # voellig gesunde Quelle ab, nur weil die Gegenseite gerade knausert.
        # Stattdessen schlaeft sie genau so lange, wie die Gegenseite sagt.
        pause: float = 0.0
        items: list = []

        try:
            items = await src.fetch(ctx)
        except NotModified:
            error = None
            items = []
            log.debug("%s: 304 nicht geaendert", source_id)
        except RateLimited as exc:
            error = f"Rate-Limit: {exc}"
            pause = max(float(getattr(exc, "retry_after", 60.0) or 60.0), 60.0)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:600]

        duration = int((time.monotonic() - t0) * 1000)
        new_count = 0

        with SessionLocal() as db:
            cfg = db.get(SourceConfig, source_id)
            if cfg is None:
                return {"source_id": source_id, "error": "Konfiguration verschwunden"}

            cfg.last_run = utcnow()
            cfg.total_runs += 1

            if error:
                cfg.total_errors += 1
                cfg.last_error = error

                # Auch ein Fehlversuch kann etwas gelernt haben - z.B. dass
                # einer von fuenf Subreddits nicht existiert. Ginge das hier
                # verloren, stellte die Quelle beim naechsten Lauf dieselbe
                # Frage noch einmal, und zwar fuer immer.
                if ctx.notizen:
                    cfg.options = {**(cfg.options or {}), **ctx.notizen}
                    log.info("%s: Einstellungen korrigiert (%s)",
                             source_id, ", ".join(sorted(ctx.notizen)))

                if pause:
                    cfg.snooze_until = utcnow() + timedelta(seconds=pause)
                    log.warning("Quelle '%s' gedrosselt, Pause bis %s: %s",
                                source_id, cfg.snooze_until, error,
                                extra={"source_id": source_id})
                else:
                    cfg.consecutive_failures += 1
                    if cfg.consecutive_failures >= settings.breaker_threshold:
                        cfg.circuit_open_until = utcnow() + timedelta(
                            seconds=settings.breaker_cooldown)
                        log.error("Circuit Breaker fuer '%s' offen bis %s (%d Fehler)",
                                  source_id, cfg.circuit_open_until,
                                  cfg.consecutive_failures,
                                  extra={"source_id": source_id})
                    else:
                        log.warning("Quelle '%s' fehlgeschlagen: %s", source_id, error,
                                    extra={"source_id": source_id})
            else:
                cfg.consecutive_failures = 0
                cfg.circuit_open_until = None
                cfg.last_error = None
                cfg.last_success = utcnow()
                cfg.total_items += len(items)
                if items:
                    cfg.verification = "verified"
                    cfg.last_verified = utcnow()

                # Was die Quelle unterwegs ueber sich gelernt hat, bleibt
                # erhalten - z.B. eine selbst gefundene Feed-Adresse.
                if ctx.notizen:
                    cfg.options = {**(cfg.options or {}), **ctx.notizen}
                    log.info("%s: Einstellungen korrigiert (%s)",
                             source_id, ", ".join(sorted(ctx.notizen)))

                fresh = ingest(db, source_id, items)
                new_count = len(fresh)

                # Bilder einmal holen und lokal ablegen, damit der Feed sie
                # nicht bei jedem Oeffnen beim Haendler nachlaedt.
                if fresh and get_setting(db, "bilder_lokal", True):
                    try:
                        await hole_fuer_deals(db, fresh, get_http())
                    except Exception as exc:
                        log.debug("Bilder holen fehlgeschlagen: %s", exc)

                # Urteil sofort berechnen, damit der Feed nicht erst beim
                # naechsten Lauf einen Wert zeigt.
                if fresh:
                    try:
                        urteile_aktualisieren(db, fresh)
                    except Exception as exc:
                        log.debug("Urteile fehlgeschlagen: %s", exc)

                # Preisfehler vor den Regeln pruefen und sofort melden.
                # Die Reihenfolge ist wichtig: der Waechter braucht das
                # Urteil (eine fragwuerdige UVP darf keinen Fehler belegen),
                # und die Regeln brauchen den Fehler-Score, damit eine Regel
                # "nur Preisfehler" ueberhaupt greifen kann.
                if fresh:
                    try:
                        heiss = pricefehler.aktualisiere(db, fresh)
                        if heiss:
                            await dispatch_preisfehler(db, heiss, get_http())
                    except Exception as exc:
                        log.error("Preisfehler-Pruefung fehlgeschlagen: %s", exc)

                # Preisalarme greifen auch, wenn der Deal nicht neu ist -
                # gerade dann ist er ja im Preis gefallen.
                try:
                    alarme = check_price_alarms(db)
                    if alarme:
                        await dispatch_alarms(db, alarme, get_http())
                except Exception as exc:
                    log.error("Preisalarm fehlgeschlagen: %s", exc)

                # Gegenprobe auf der Zielseite, BEVOR die Regeln laufen:
                # ein Fund, der sich als nicht-gratis herausstellt, soll
                # eine "nur gratis"-Regel gar nicht erst treffen. Genau
                # dieser Fall war der Aerger - Meldung kommt, Seite will
                # Geld.
                gesperrt: set[int] = set()
                if fresh and get_setting(db, gratischeck.SETTING_AN, True):
                    try:
                        bilanz = await gratischeck.pruefe_deals(
                            db, get_http(), fresh,
                            grenze=get_setting(db, gratischeck.SETTING_MAX,
                                               gratischeck.MAX_PRO_LAUF))
                        gesperrt = set(bilanz["gesperrt"])
                        if bilanz["korrigiert"]:
                            log.info("Gratis-Pruefung: %d von %d korrigiert",
                                     bilanz["korrigiert"], bilanz["geprueft"])
                    except Exception as exc:
                        log.error("Gratis-Pruefung fehlgeschlagen: %s", exc)

                hits = []
                # Was die Zielseite als abgelaufen fuehrt, wird nicht
                # gemeldet - der Deal bleibt sichtbar, aber er weckt
                # niemanden mehr.
                fresh = [d for d in fresh if d.id not in gesperrt]
                if fresh:
                    hits = match_rules(db, fresh)
                    if hits:
                        try:
                            await dispatch(db, hits, get_http())
                        except Exception as exc:
                            log.error("Versand fehlgeschlagen: %s", exc)
                    log.info("Quelle '%s': %d Eintraege, %d neu, %d Regeltreffer",
                             source_id, len(items), new_count, len(hits),
                             extra={"source_id": source_id})

            db.add(SourceRun(source_id=source_id, duration_ms=duration,
                             ok=not error, items=len(items), new_items=new_count,
                             error=error))
            db.commit()

            broker.publish("source", {
                "source_id": source_id, "ok": not error, "items": len(items),
                "new_items": new_count, "error": error, "duration_ms": duration,
                "consecutive_failures": cfg.consecutive_failures,
                "circuit_open_until": (cfg.circuit_open_until.isoformat()
                                       if cfg.circuit_open_until else None),
            })

        return {"source_id": source_id, "ok": not error, "items": len(items),
                "new_items": new_count, "error": error, "duration_ms": duration}


def _job_id(source_id: str) -> str:
    return f"src:{source_id}"


def _aktuelles_intervall(job) -> int | None:
    """Sekunden des laufenden Triggers - oder None, wenn kein Intervall."""
    trigger = getattr(job, "trigger", None)
    if isinstance(trigger, IntervalTrigger):
        return int(trigger.interval.total_seconds())
    return None


def schedule_source(cfg: SourceConfig) -> None:
    """Job anlegen/aktualisieren. Respektiert das Mindestintervall der Quelle."""
    src = get_source(cfg.id)
    if src is None:
        return
    job_id = _job_id(cfg.id)
    existing = scheduler.get_job(job_id)

    if not cfg.enabled or (erwachsen_mod.quelle_ist_18(cfg.id)
                           and not _erwachsen_frei()):
        if existing:
            existing.remove()
            log.info("Job fuer '%s' entfernt", cfg.id)
        return

    interval = max(int(cfg.interval_seconds or src.default_interval), src.min_interval)

    if existing:
        # Nur umplanen, wenn sich wirklich etwas geaendert hat. Ein
        # reschedule() setzt die naechste Laufzeit zurueck - beim
        # regelmaessigen Abgleich wuerde eine Quelle mit langem Intervall
        # dadurch nie an die Reihe kommen.
        if _aktuelles_intervall(existing) == interval:
            return
        existing.reschedule(trigger=IntervalTrigger(
            seconds=interval, jitter=min(60, interval // 10)))
        log.info("Job fuer '%s' auf %ds umgestellt", cfg.id, interval)
    else:
        scheduler.add_job(run_source,
                          trigger=IntervalTrigger(seconds=interval,
                                                  jitter=min(60, interval // 10)),
                          args=[cfg.id], id=job_id,
                          max_instances=1, coalesce=True, misfire_grace_time=300,
                          next_run_time=utcnow() + timedelta(seconds=5))
        log.info("Job fuer '%s' alle %ds", cfg.id, interval)


def _erwachsen_frei() -> bool:
    """Ist der 18+-Bereich freigeschaltet? Fehler heissen hier: nein."""
    try:
        with SessionLocal() as db:
            return erwachsen_mod.ist_aktiv(db)
    except Exception:
        return False


def sync_jobs() -> None:
    """Jobs mit der Datenbank abgleichen.

    Laeuft beim Start, nach Aenderungen ueber die API und minuetlich - so
    greifen auch Aenderungen, die die CLI direkt in die Datenbank schreibt,
    ohne dass der Server neu gestartet werden muss.
    """
    try:
        with session_scope() as db:
            bekannt = set()
            for cfg in db.scalars(select(SourceConfig)):
                bekannt.add(_job_id(cfg.id))
                schedule_source(cfg)
        # Quellen, deren Config-Zeile geloescht wurde, nicht weiterlaufen lassen.
        for job in scheduler.get_jobs():
            if job.id.startswith("src:") and job.id not in bekannt:
                job.remove()
                log.info("Job '%s' entfernt - keine Konfiguration mehr", job.id)
    except Exception as exc:
        log.error("Job-Abgleich fehlgeschlagen: %s", exc)


async def watch_job() -> None:
    """Wunschliste abfragen und bei Preisstuerzen melden.

    Laeuft alle 10 Minuten, prueft aber nur, was laut eigenem Intervall
    faellig ist - so bleibt jeder Shop hoeflich bedient.
    """
    from .models import Channel
    from .notify import Notification, get_channel
    from .pricewatch import faellige, pruefe, soll_melden

    try:
        with SessionLocal() as db:
            offen = faellige(db)
            if not offen:
                return
            kanaele = [c for c in db.scalars(select(Channel)) if c.enabled]

            for eintrag in offen:
                fund = await pruefe(db, eintrag, get_http())
                if fund is None:
                    continue
                grund = soll_melden(eintrag, fund)
                if not grund:
                    continue

                log.info("Wunschliste: %s - %s", eintrag.name, grund)
                note = Notification(
                    titel=eintrag.name, url=eintrag.url, quelle="wunschliste",
                    regel="Wunschliste", preis=fund.preis,
                    waehrung=fund.waehrung, haendler=eintrag.haendler,
                    bild=eintrag.bild, beschreibung=grund,
                    prioritaet="SOFORT")
                for kanal in kanaele:
                    impl = get_channel(kanal.type)
                    if impl is None:
                        continue
                    try:
                        await impl.send(kanal.config or {}, note, get_http())
                    except Exception as exc:
                        log.error("Wunschliste-Meldung ueber %s: %s",
                                  kanal.type, exc)

                eintrag.zuletzt_gemeldet = fund.preis
                broker.publish("watch", {
                    "id": eintrag.id, "name": eintrag.name, "grund": grund,
                    "preis": fund.preis, "waehrung": fund.waehrung,
                    "url": eintrag.url, "bild": eintrag.bild})
            db.commit()
    except Exception as exc:
        log.error("Wunschliste fehlgeschlagen: %s", exc)


async def preisfehler_job() -> None:
    """Bestehende Deals erneut auf Preisfehler pruefen.

    Ein Preis faellt nicht nur beim ersten Sehen. Ein Artikel, der seit Tagen
    im Feed steht und heute auf ein Zehntel rutscht, ist derselbe Fund - er
    kaeme ohne diesen Lauf nie zur Sprache, weil er nicht mehr "neu" ist.
    """
    try:
        from datetime import timedelta as _td
        with SessionLocal() as db:
            kandidaten = list(db.scalars(
                select(Deal)
                .where(Deal.first_seen >= utcnow() - _td(days=7),
                       Deal.ist_gratis.is_(False),
                       # Der Waechter weckt das Handy in Sekunden - genau
                       # das soll der 18+-Bereich nicht tun.
                       Deal.erwachsen.is_(False),
                       Deal.preis_eur.isnot(None))
                .order_by(desc(Deal.last_seen)).limit(400)))
            heiss = pricefehler.aktualisiere(db, kandidaten)
            if heiss:
                log.warning("Preisfehler-Nachlauf: %d neue Funde", len(heiss))
                await dispatch_preisfehler(db, heiss, get_http())
    except Exception as exc:
        log.error("Preisfehler-Nachlauf fehlgeschlagen: %s", exc)


def urteile_job() -> None:
    """Urteile der letzten Tage nachziehen - der Verlauf waechst ja weiter."""
    try:
        from datetime import timedelta as _td
        with session_scope() as db:
            frisch = list(db.scalars(
                select(Deal).where(Deal.first_seen >= utcnow() - _td(days=14))
                .order_by(desc(Deal.first_seen)).limit(500)))
            geaendert = urteile_aktualisieren(db, frisch)
            if geaendert:
                log.info("Preisurteile: %d aktualisiert", geaendert)
    except Exception as exc:
        log.error("Urteile fehlgeschlagen: %s", exc)


async def watchdog_job() -> None:
    """Sich selbst pruefen: laufen alle eingeschalteten Quellen und Kanaele?"""
    try:
        with SessionLocal() as db:
            await dispatch_watchdog(db, get_http())
    except Exception as exc:
        log.error("Selbstueberwachung fehlgeschlagen: %s", exc)


async def gratischeck_job() -> None:
    """Gratis-Funde der letzten Tage nachpruefen.

    Der Lauf beim Einsammeln erwischt jeden Fund einmal. Was danach
    passiert - Aktion beendet, Vorrat weg - sieht nur dieser Job. Er
    arbeitet die aeltesten Befunde zuerst ab und ist pro Lauf gedeckelt,
    damit daraus kein Crawler wird.
    """
    try:
        from datetime import timedelta as _td
        with SessionLocal() as db:
            if not get_setting(db, gratischeck.SETTING_AN, True):
                return
            kandidaten = list(db.scalars(
                select(Deal)
                .where(Deal.first_seen >= utcnow() - _td(days=3),
                       Deal.ist_gratis.is_(True))
                .order_by(Deal.check_am.is_(None).desc(), Deal.check_am)
                .limit(60)))
            bilanz = await gratischeck.pruefe_deals(
                db, get_http(), kandidaten,
                grenze=get_setting(db, gratischeck.SETTING_MAX,
                                   gratischeck.MAX_PRO_LAUF))
            if bilanz["geprueft"]:
                log.info("Gratis-Nachpruefung: %d geprueft, %d korrigiert",
                         bilanz["geprueft"], bilanz["korrigiert"])
    except Exception as exc:
        log.error("Gratis-Nachpruefung fehlgeschlagen: %s", exc)


async def digest_job() -> None:
    try:
        with SessionLocal() as db:
            sent = await send_digest(db, get_http())
            if sent:
                log.info("Digest verschickt: %d Nachrichten", sent)
    except Exception as exc:
        log.error("Digest fehlgeschlagen: %s", exc)


def cleanup_job() -> None:
    """Alte Deals/Logs wegwerfen, damit die DB nicht endlos waechst."""
    try:
        with session_scope() as db:
            deal_cut = utcnow() - timedelta(days=settings.deal_retention_days)
            log_cut = utcnow() - timedelta(days=settings.log_retention_days)
            deals = db.execute(delete(Deal).where(Deal.first_seen < deal_cut,
                                                  Deal.bookmarked.is_(False)))
            db.execute(delete(SourceRun).where(SourceRun.started_at < log_cut))
            db.execute(delete(NotificationLog).where(NotificationLog.created_at < log_cut))
            db.execute(delete(LogEntry).where(LogEntry.ts < log_cut))
            from .loginguard import aufraeumen as login_aufraeumen
            login_aufraeumen(db)
            if deals.rowcount:
                log.info("Aufraeumen: %d alte Deals entfernt", deals.rowcount)
            db.flush()
            bilder_aufraeumen(db)
    except Exception as exc:
        log.error("Aufraeumen fehlgeschlagen: %s", exc)


def start() -> None:
    ensure_source_rows()
    sync_jobs()
    scheduler.add_job(digest_job, IntervalTrigger(hours=1), id="digest",
                      max_instances=1, coalesce=True)
    scheduler.add_job(cleanup_job, IntervalTrigger(hours=6), id="cleanup",
                      max_instances=1, coalesce=True)
    scheduler.add_job(watch_job, IntervalTrigger(minutes=10), id="watch",
                      max_instances=1, coalesce=True)
    scheduler.add_job(urteile_job, IntervalTrigger(hours=3), id="urteile",
                      max_instances=1, coalesce=True)
    # Haeufiger als die Urteile: ein Preisfehler ist nach einer Stunde weg.
    scheduler.add_job(preisfehler_job, IntervalTrigger(minutes=20),
                      id="preisfehler", max_instances=1, coalesce=True)
    scheduler.add_job(sync_jobs, IntervalTrigger(seconds=60), id="sync",
                      max_instances=1, coalesce=True)
    scheduler.add_job(gratischeck_job, IntervalTrigger(minutes=30),
                      id="gratischeck", max_instances=1, coalesce=True,
                      next_run_time=utcnow() + timedelta(minutes=3))
    # Erst nach ein paar Minuten anfangen: direkt nach dem Start hat noch
    # keine Quelle laufen koennen, da waere jede Meldung verfrueht.
    scheduler.add_job(watchdog_job, IntervalTrigger(minutes=15), id="watchdog",
                      max_instances=1, coalesce=True,
                      next_run_time=utcnow() + timedelta(minutes=5))
    try:
        from .claimer import scan_job
        scheduler.add_job(scan_job, IntervalTrigger(minutes=10), id="claimer_scan",
                          max_instances=1, coalesce=True)
    except Exception as exc:
        log.debug("Claimer-Scan nicht aktiv: %s", exc)
    scheduler.start()
    log.info("Scheduler gestartet mit %d Jobs", len(scheduler.get_jobs()))


async def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if http is not None:
        await http.aclose()
