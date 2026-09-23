from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import currency, gesundheit
from .auth import current_user
from .config import settings
from .currency import set_rates
from .db import get_db, get_setting, init_db, session_scope
from .events import broker
from .logging_setup import setup_logging
from .routers import (
    auth_routes,
    deals_routes,
    extras_routes,
    notify_routes,
    rules_routes,
    sources_routes,
    system_routes,
    watch_routes,
)
from .sicherheitsheader import SicherheitsHeader
from .tokens import pruefe as pruefe_token

setup_logging()
log = logging.getLogger("sparbit")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    broker.bind_loop(asyncio.get_running_loop())

    # Waehrungskurse aus den Einstellungen laden, damit Preisregeln
    # quellenuebergreifend in EUR rechnen. Der Stand kommt mit: das UI
    # soll sagen koennen, wie alt die Zahlen sind, statt sie einfach
    # anzuzeigen, als waeren sie von heute.
    with session_scope() as db:
        set_rates(get_setting(db, currency.SCHLUESSEL_KURSE),
                  get_setting(db, currency.SCHLUESSEL_STAND))

    # Erst die Erweiterungen laden, dann den Scheduler starten: er legt
    # beim Start fuer jede registrierte Quelle eine Zeile an.
    from . import plugins
    plugins.lade()

    from . import scheduler as sched
    from .telegram_bot import bot

    hier = settings.scheduler_hier
    nachlese_task: asyncio.Task | None = None

    if hier:
        sched.start()
        if settings.telegram_polling:
            bot.start()
    else:
        # Der Scheduler laeuft als eigener Dienst (python -m app.worker).
        # Dann holt dieser Prozess dessen Ereignisse aus der Datenbank,
        # sonst bliebe der Live-Ticker stumm und saehe kaputt aus.
        sched.ensure_source_rows()
        nachlese_task = asyncio.create_task(_nachlese_schleife())
        log.info("Scheduler laeuft nicht hier (SPARBIT_SCHEDULER=%s) - "
                 "es muss ein Worker laufen, sonst wird nichts eingesammelt.",
                 settings.scheduler)

    log.info("SparBit laeuft auf http://%s:%s", settings.host, settings.port)
    try:
        yield
    finally:
        if nachlese_task is not None:
            nachlese_task.cancel()
        if hier:
            await bot.stop()
            await sched.shutdown()
        log.info("SparBit beendet")


# Wie oft der API-Prozess im Worker-Betrieb nach neuen Ereignissen sieht.
# Zwei Sekunden: schnell genug, dass der Ticker lebendig wirkt, selten
# genug, dass es im Leerlauf nicht auffaellt.
NACHLESE_TAKT = 2.0


async def _nachlese_schleife() -> None:
    """Ereignisse des Workers an die eigenen SSE-Verbindungen weiterreichen."""
    from .events import nachlese

    marke: int | None = None
    while True:
        try:
            await asyncio.sleep(NACHLESE_TAKT)
            # Niemand sieht zu? Dann auch nichts holen - das spart im
            # Normalfall jede Abfrage, weil das Dashboard meistens zu ist.
            if broker.subscriber_count == 0:
                marke = None       # beim naechsten Zusehen frisch aufsetzen
                continue
            marke, nutzlasten = await asyncio.to_thread(nachlese, marke)
            for nutzlast in nutzlasten:
                broker.einspeisen(nutzlast)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("Nachlese-Schleife: %s", exc)


app = FastAPI(title="SparBit", version="1.0.0",
              description="Selbstgehostete Deal- & Freebie-Zentrale",
              lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(SicherheitsHeader)

if settings.cors_origins:
    _herkuenfte = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

    # "*" zusammen mit Cookies ist die Stelle, an der der CSRF-Schutz des
    # Cookies (SameSite=Lax) nichts mehr nuetzt: Starlette spiegelt dann
    # jede Herkunft zurueck, und eine beliebige fremde Seite darf
    # angemeldete Anfragen an SparBit schicken. Die Sternchen-Schreibweise
    # sieht harmlos aus ("ich will es nur schnell testen") und ist es
    # genau hier nicht.
    if "*" in _herkuenfte:
        log.warning(
            "SPARBIT_CORS_ORIGINS enthaelt '*'. Damit duerfte jede fremde "
            "Seite angemeldete Anfragen stellen. Cookies werden fuer "
            "fremde Herkuenfte deshalb NICHT freigegeben - trage die "
            "erlaubten Adressen einzeln ein, z. B. "
            "SPARBIT_CORS_ORIGINS=https://sparbit.example.de")

    _mit_cookies = "*" not in _herkuenfte
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_herkuenfte,
        allow_credentials=_mit_cookies,
        allow_methods=["*"], allow_headers=["*"],
    )
    log.info("CORS offen fuer: %s (Cookies: %s)", ", ".join(_herkuenfte),
             "ja" if _mit_cookies else "nein")

app.include_router(auth_routes.router)
app.include_router(sources_routes.router)
app.include_router(deals_routes.router)
app.include_router(rules_routes.router)
app.include_router(notify_routes.router)
app.include_router(notify_routes.quiet_router)
app.include_router(notify_routes.push_router)
app.include_router(system_routes.router)
app.include_router(system_routes.host_router)
app.include_router(system_routes.sse_router)
app.include_router(system_routes.claimer_router)
app.include_router(extras_routes.router)
app.include_router(extras_routes.bilder_router)
app.include_router(extras_routes.kalender_router)
app.include_router(watch_routes.router)
app.include_router(watch_routes.extern_router)


@app.get("/api/health")
def health(response: Response) -> dict:
    """Tiefencheck - ohne Anmeldung, damit ein Wachhund ihn abfragen kann.

    Herausgegeben werden nur Zustaende, keine Daten: welcher Teil in
    Ordnung ist und seit wann nichts mehr laeuft. 503 gibt es erst,
    wenn wirklich etwas kaputt ist - ein Mangel (degraded) bleibt 200,
    sonst startet ein Container-Orchestrator den Dienst neu, obwohl er
    seine Arbeit tut.
    """
    stand = gesundheit.bericht()
    if stand["status"] == "down":
        response.status_code = 503
    return stand


@app.get("/api/metrics", response_class=PlainTextResponse)
def metrics(request: Request, db: Session = Depends(get_db)) -> str:
    """Prometheus-Format. Die Zahlen liegen ohnehin schon in der Datenbank.

    Anders als /api/health nicht offen: die Zahlen verraten, welche
    Quellen laufen und wie viele Deals hier liegen. Zugang hat, wer
    angemeldet ist - oder ein API-Token schickt, wie es Prometheus mit
    bearer_token_file ohnehin kann.
    """
    try:
        current_user(request, db)
        return gesundheit.metriken()
    except HTTPException:
        pass

    kopf = request.headers.get("authorization", "")
    if kopf.lower().startswith("bearer ") and pruefe_token(db, kopf.split(" ", 1)[1].strip()):
        return gesundheit.metriken()
    raise HTTPException(401, "Anmeldung oder API-Token noetig.")


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unbehandelter Fehler bei %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "Interner Fehler - siehe Logs."})


# --- Web-Oberflaeche ------------------------------------------------------
# Liegt ein gebautes Frontend daneben, liefert das Backend es gleich mit aus.
# Dann genuegt ein Prozess und ein Port - genau das, was man auf dem eigenen
# Rechner will. Im Docker-Setup uebernimmt stattdessen nginx.

DIST = settings.frontend_dist

if (DIST / "index.html").exists():
    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Single-Page-App: jeder unbekannte Pfad bekommt index.html, damit
        Deep-Links wie /regeln direkt funktionieren."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Unbekannter API-Pfad")
        # Echte Dateien (Manifest, Icons, robots.txt) direkt ausliefern.
        candidate = (DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(DIST.resolve()):
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
else:
    log.warning("Kein gebautes Frontend unter %s - starte es separat mit "
                "'npm run dev' oder baue es mit 'npm run build'.", DIST)
