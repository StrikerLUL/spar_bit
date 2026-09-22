"""SSE-Broker: Live-Ticker im Dashboard ohne Reload.

Zwei Betriebsarten. Im Normalfall laufen Scheduler und API im selben
Prozess: ein Fund wird gefunden, der Broker reicht ihn an die offenen
SSE-Verbindungen weiter, fertig.

Laeuft der Scheduler als eigener Dienst, teilen sich die beiden keine
Warteschlange mehr. Dann spiegelt der Worker jedes Ereignis in die
Tabelle `event_log`, und der API-Prozess liest von dort nach (siehe
`nachlese`). Das ist ein Umweg, aber einer ohne zusaetzliche Software -
und ohne ihn waere der Live-Ticker im Worker-Betrieb still, was wie ein
Defekt aussaehe.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# Wie viele Ereignisse eine Nachlese hoechstens auf einmal holt. Wer
# lange nicht hingesehen hat, soll nicht eine Minute Verlauf auf einmal
# ins Gesicht bekommen.
NACHLESE_MAX = 50


class EventBroker:
    def __init__(self, max_queue: int = 200) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._max_queue = max_queue
        self._loop: asyncio.AbstractEventLoop | None = None
        # Schreibt dieser Prozess seine Ereignisse zusaetzlich in die
        # Datenbank? Nur der Worker tut das - im Normalbetrieb waere es
        # eine Schreiboperation je Fund, fuer niemanden.
        self.spiegeln = False

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: str, data: Any) -> None:
        """Threadsicher: darf auch aus Scheduler-Threads aufgerufen werden."""
        if self.spiegeln:
            # Zweite Absicherung neben der in _in_die_db: der Ticker ist
            # Beiwerk, das Einsammeln ist die Arbeit. Ein Fehler auf dem
            # Weg in die Datenbank darf einen Quellenlauf nie anhalten -
            # auch dann nicht, wenn er entsteht, bevor das try dort greift.
            try:
                self._in_die_db(event, data)
            except Exception as exc:
                log.debug("Ereignis nicht gespiegelt: %s", exc)
        payload = json.dumps({"event": event, "data": data}, default=str,
                             ensure_ascii=False)
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._fanout, payload)
                return
            except RuntimeError:
                pass
        self._fanout(payload)

    def _fanout(self, payload: str) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Langsamer Client: aeltestes Event verwerfen, neues rein.
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    def einspeisen(self, nutzlast: str) -> None:
        """Eine fertige SSE-Nutzlast weiterreichen, ohne sie neu zu bauen.

        Fuer die Nachlese aus der Datenbank: dort steht die Nutzlast
        schon fertig, und ein zweites json.dumps wuerde sie nur noch
        einmal verpacken.
        """
        self._fanout(nutzlast)

    @staticmethod
    def _in_die_db(event: str, data: Any) -> None:
        """Ereignis fuer den anderen Prozess ablegen.

        Ein Fehler hier darf den Lauf nicht anhalten: der Live-Ticker ist
        Beiwerk, das Einsammeln ist die Arbeit.
        """
        try:
            from .db import SessionLocal
            from .models import EventLog

            # json.dumps/loads, damit auch datetime-Werte in der
            # JSON-Spalte landen - dieselbe Umwandlung wie im Fanout.
            sauber = json.loads(json.dumps(data, default=str, ensure_ascii=False))
            with SessionLocal() as db:
                db.add(EventLog(event=event, daten=sauber))
                db.commit()
        except Exception as exc:
            log.debug("Ereignis nicht gespiegelt: %s", exc)


broker = EventBroker()


def nachlese(ab_id: int | None) -> tuple[int, list[str]]:
    """Ereignisse, die ein anderer Prozess geschrieben hat.

    Gibt die neue Marke und die fertigen SSE-Nutzlasten zurueck.

    `ab_id=None` heisst "ich sehe gerade erst zu": dann wird nur die
    Marke gesetzt und nichts geliefert - die letzte Stunde Verlauf
    nachzureichen hilft niemandem.

    Bewusst None und nicht 0: bei einer leeren Tabelle ist 0 die echte
    Marke, und mit 0 als Sonderwert haette der erste Schwung Ereignisse
    einer frischen Anlage die Nachlese nur erneut zurueckgesetzt statt
    angekommen zu sein.
    """
    from sqlalchemy import func, select

    from .db import SessionLocal
    from .models import EventLog

    try:
        with SessionLocal() as db:
            if ab_id is None:
                return int(db.scalar(select(func.max(EventLog.id))) or 0), []
            zeilen = list(db.scalars(
                select(EventLog).where(EventLog.id > ab_id)
                .order_by(EventLog.id).limit(NACHLESE_MAX)))
    except Exception as exc:
        log.debug("Nachlese fehlgeschlagen: %s", exc)
        return ab_id or 0, []

    if not zeilen:
        return ab_id, []
    nutzlast = [json.dumps({"event": z.event, "data": z.daten},
                           default=str, ensure_ascii=False) for z in zeilen]
    return zeilen[-1].id, nutzlast
