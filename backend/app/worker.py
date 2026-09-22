"""Der Scheduler als eigener Dienst.

    python -m app.worker

Normalerweise braucht es das nicht: SparBit ist ein Prozess, und der
Scheduler laeuft in derselben Schleife wie die API. Fuer einen Haushalt
mit fuenfzehn Quellen ist das genau richtig - ein Dienst, ein Neustart,
ein Protokoll.

Es gibt aber einen Fall, in dem das stoert: wenn das Einsammeln so viel
Arbeit macht, dass die Oberflaeche darunter traege wird. Dann laeuft
hier der Scheduler und dort die API, beide auf derselben Datenbank:

    # .env
    SPARBIT_SCHEDULER=aus          # gilt fuer den API-Prozess

    docker compose --profile worker up -d

Was dabei zu wissen ist:

* **Genau einer.** Zwei Worker auf derselben Datenbank fragen jede
  Quelle doppelt ab und verschicken jede Meldung zweimal. Es gibt keine
  Sperre dagegen - sie waere ein verteiltes Schloss fuer einen Fall, den
  es in einem Haushalt nicht gibt.
* **Der Live-Ticker geht weiter.** Der Worker spiegelt seine Ereignisse
  in die Tabelle `event_log`, der API-Prozess liest von dort nach.
* **Der Telegram-Bot laeuft hier**, nicht im API-Prozess: Long Polling
  ist eine Dauerverbindung, und zwei davon wuerden sich die Nachrichten
  gegenseitig wegnehmen.
"""
from __future__ import annotations

import asyncio
import logging
import signal

from .config import settings
from .db import get_setting, init_db, session_scope
from .events import broker
from .logging_setup import setup_logging

log = logging.getLogger("sparbit.worker")


async def laufen() -> None:
    from . import currency, plugins
    from . import scheduler as sched
    from .telegram_bot import bot

    init_db()
    broker.bind_loop(asyncio.get_running_loop())
    # Der API-Prozess sieht die Warteschlange dieses Prozesses nicht -
    # ohne die Spiegelung waere sein Live-Ticker still.
    broker.spiegeln = True

    with session_scope() as db:
        currency.set_rates(get_setting(db, currency.SCHLUESSEL_KURSE),
                           get_setting(db, currency.SCHLUESSEL_STAND))

    plugins.lade()
    sched.start()
    if settings.telegram_polling:
        bot.start()

    log.info("Worker laeuft - Scheduler mit %d Jobs",
             len(sched.scheduler.get_jobs()))

    # Auf SIGTERM/SIGINT warten. Docker schickt SIGTERM beim Stoppen;
    # ohne diese Behandlung liefe der Container in den Kill-Timeout und
    # ein laufender Quellenlauf braeche mitten in der Datenbank ab.
    schluss = asyncio.Event()
    schleife = asyncio.get_running_loop()
    for zeichen in (signal.SIGTERM, signal.SIGINT):
        try:
            schleife.add_signal_handler(zeichen, schluss.set)
        except NotImplementedError:
            pass                    # Windows kennt das nicht
    try:
        await schluss.wait()
    finally:
        log.info("Worker wird beendet")
        await bot.stop()
        await sched.shutdown()


def main() -> None:
    setup_logging()
    if settings.scheduler_hier:
        # Kein Abbruch: wer beides laufen laesst, soll es merken, aber
        # nicht mit einem Dienst dastehen, der sich weigert zu starten.
        log.warning(
            "SPARBIT_SCHEDULER steht auf '%s'. Laeuft daneben ein "
            "API-Prozess, sammelt er zusaetzlich ein - dann kommt jeder "
            "Deal doppelt. Fuer den Worker-Betrieb gehoert dort "
            "SPARBIT_SCHEDULER=aus hin.", settings.scheduler)
    try:
        asyncio.run(laufen())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
