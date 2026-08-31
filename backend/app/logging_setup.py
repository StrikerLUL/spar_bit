"""Strukturiertes Logging: JSON auf stdout + Ringpuffer in der DB fuers UI."""
from __future__ import annotations

import json
import logging
import sys
from collections import deque
from datetime import datetime, timezone
from typing import Any

from .config import settings

_RING: deque[dict[str, Any]] = deque(maxlen=settings.max_log_lines)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("source_id", "rule_id", "deal_id", "channel"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)[-1500:]
        return json.dumps(payload, ensure_ascii=False, default=str)


class RingHandler(logging.Handler):
    """Haelt die letzten N Zeilen fuer die Logs-Seite im UI vor."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()[:2000],
            }
            if record.exc_info:
                entry["exc"] = self.format(record)[-1200:]
            _RING.append(entry)
            from .events import broker
            if record.levelno >= logging.INFO:
                broker.publish("log", entry)
        except Exception:
            pass


def recent_logs(limit: int = 300, level: str | None = None) -> list[dict]:
    items = list(_RING)
    if level and level.upper() != "ALL":
        wanted = logging.getLevelName(level.upper())
        items = [e for e in items
                 if logging.getLevelName(e["level"]) >= wanted]
    return items[-limit:][::-1]


def setup_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter() if settings.log_json
                        else logging.Formatter(
                            "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"))
    root.addHandler(stream)
    root.addHandler(RingHandler())

    for noisy in ("httpx", "httpcore", "apscheduler.executors.default",
                  "apscheduler.scheduler", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
