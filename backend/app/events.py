"""SSE-Broker: Live-Ticker im Dashboard ohne Reload."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

log = logging.getLogger(__name__)


class EventBroker:
    def __init__(self, max_queue: int = 200) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._max_queue = max_queue
        self._loop: asyncio.AbstractEventLoop | None = None

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


broker = EventBroker()
