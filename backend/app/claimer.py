"""Auto-Claimer-Anbindung (vogler/free-games-claimer).

Der Claimer laeuft als eigener Container und schreibt in ein gemeinsames
Volume. Wir lesen dort nur mit: Logdateien parsen -> geclaimte Titel ins UI.

Bewusst tolerant: das Logformat des Projekts ist nicht stabil versioniert,
darum mehrere Muster und ein Fallback. Findet der Parser nichts, zeigt das UI
das Rohlog - es geht nie etwas verloren.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .db import session_scope
from .models import ClaimEvent

log = logging.getLogger(__name__)

# free-games-claimer loggt z.B.:
#   "claimed <Titel>"  /  "already claimed <Titel>"  /  "Failed to claim <Titel>"
# Reihenfolge zaehlt: "already claimed" und "failed to claim" enthalten beide
# das Wort claim - die spezifischeren Muster muessen zuerst greifen.
_PATTERNS = [
    (re.compile(r"\balready\s+(?:claimed|owned)\b[:\s]+[\"']?(?P<titel>[^\"'\n]{2,120})", re.I), "already"),
    (re.compile(r"\b(?:failed|error)\b[^\n]{0,20}\bclaim\w*\b[:\s]+[\"']?(?P<titel>[^\"'\n]{2,120})", re.I), "failed"),
    (re.compile(r"\bclaimed\b[:\s]+[\"']?(?P<titel>[^\"'\n]{2,120})", re.I), "claimed"),
    (re.compile(r"^\s*(?P<titel>[^\n]{2,120})\s+-\s+claimed\s*$", re.I | re.M), "claimed"),
]

# Anhaengsel wie "(button not found)" gehoeren in detail, nicht in den Titel.
_TRAILING_NOTE = re.compile(r"\s*\([^)]*\)\s*$")

_PLATFORM_HINTS = {
    "epic": ("epic-games", "epic_games", "epicgames", "epic"),
    "prime": ("prime-gaming", "prime_gaming", "primegaming", "prime", "amazon"),
    "gog": ("gog",),
}

_ANSI = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _platform_for(text: str, filename: str = "") -> str:
    blob = f"{filename} {text}".lower()
    for platform, hints in _PLATFORM_HINTS.items():
        if any(h in blob for h in hints):
            return platform
    return "unbekannt"


def log_files() -> list[Path]:
    base = settings.claimer_log_dir
    if not base.exists():
        return []
    files: list[Path] = []
    for pattern in ("*.log", "*.txt", "**/*.log"):
        files.extend(p for p in base.glob(pattern) if p.is_file())
    return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)[:10]


def read_tail(limit_lines: int = 400) -> str:
    """Rohlog fuers UI - neueste Datei, letzte N Zeilen."""
    files = log_files()
    if not files:
        return ""
    try:
        text = files[0].read_text("utf-8", errors="replace")
    except OSError as exc:
        return f"Log nicht lesbar: {exc}"
    lines = _ANSI.sub("", text).splitlines()
    return "\n".join(lines[-limit_lines:])


def parse_events(text: str, filename: str = "") -> list[dict]:
    text = _ANSI.sub("", text or "")
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 500:
            continue
        for pattern, status in _PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            titel = _TRAILING_NOTE.sub("", m.group("titel")).strip(" -:\t\"'")
            # Offensichtlichen Log-Rauschtext aussortieren.
            if len(titel) < 2 or titel.lower() in ("game", "games", "null", "undefined"):
                continue
            key = (titel.lower(), status)
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "titel": titel[:300],
                "status": status,
                "platform": _platform_for(line, filename),
                "detail": line[:400],
            })
            break
    return found


def scan_job() -> int:
    """Logs einlesen und neue Claim-Events speichern. Idempotent."""
    files = log_files()
    if not files:
        return 0

    new = 0
    with session_scope() as db:
        for path in files:
            try:
                text = path.read_text("utf-8", errors="replace")
            except OSError as exc:
                log.debug("Claimer-Log %s nicht lesbar: %s", path, exc)
                continue

            mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            for ev in parse_events(text, path.name):
                fp = hashlib.sha256(
                    f"{ev['platform']}|{ev['titel'].lower()}|{ev['status']}"
                    f"|{mtime.date()}".encode()
                ).hexdigest()[:64]
                if db.scalar(select(ClaimEvent).where(ClaimEvent.fingerprint == fp)):
                    continue
                db.add(ClaimEvent(platform=ev["platform"], titel=ev["titel"],
                                  status=ev["status"], detail=ev["detail"],
                                  seen_at=mtime, fingerprint=fp))
                new += 1

    if new:
        log.info("Claimer: %d neue Ereignisse aus den Logs", new)
    return new


def status() -> dict:
    files = log_files()
    newest = files[0] if files else None
    return {
        "log_dir": str(settings.claimer_log_dir),
        "log_vorhanden": bool(files),
        "dateien": [f.name for f in files],
        "letzte_aenderung": (
            datetime.fromtimestamp(newest.stat().st_mtime, UTC).isoformat()
            if newest else None
        ),
    }
