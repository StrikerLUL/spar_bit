"""Gemeinsame RSS/Atom-Helfer fuer alle Feed-Quellen."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

import feedparser

_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def strip_html(raw: str | None, limit: int = 1200) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def first_image(entry: Any, raw_html: str | None = None) -> str | None:
    """Bild aus media:content, enclosure oder <img> im Body."""
    for key in ("media_content", "media_thumbnail"):
        vals = getattr(entry, key, None) or entry.get(key) if hasattr(entry, "get") else None
        if vals:
            url = vals[0].get("url")
            if url:
                return url
    for enc in (entry.get("enclosures") or []):
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    if raw_html:
        m = _IMG_RE.search(raw_html)
        if m:
            return html.unescape(m.group(1))
    return None


def entry_datetime(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        tm = entry.get(key)
        if tm:
            try:
                return datetime(*tm[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def entry_body(entry: Any) -> str:
    """Rohes HTML des Eintrags (content bevorzugt, sonst summary)."""
    content = entry.get("content")
    if content and isinstance(content, list) and content[0].get("value"):
        return content[0]["value"]
    return entry.get("summary") or entry.get("description") or ""


def parse_feed(text: str) -> Any:
    """feedparser mit Sanity-Check.

    feedparser gibt fuer HTML-Blockseiten oder leere Antworten klaglos ein
    Objekt mit 0 Eintraegen zurueck. Das darf nicht als "Feed ohne neue Deals"
    durchgehen - sonst sieht eine Cloudflare-Wand im UI aus wie eine gesunde
    Quelle. Ohne Eintraege verlangen wir darum den Nachweis, dass ueberhaupt
    ein Feed geparst wurde (version/Feed-Titel).
    """
    parsed = feedparser.parse(text or "")
    if parsed.entries:
        return parsed

    exc = getattr(parsed, "bozo_exception", None)
    looks_like_feed = bool(getattr(parsed, "version", "")) and bool(
        (parsed.feed or {}).get("title") or (parsed.feed or {}).get("link"))
    if looks_like_feed and not parsed.bozo:
        return parsed          # echter, aber gerade leerer Feed

    head = (text or "").lstrip()[:160].replace("\n", " ")
    raise ValueError(
        f"Kein gueltiger Feed ({type(exc).__name__ if exc else 'keine Eintraege'}). "
        f"Anfang der Antwort: {head!r}"
    )


def entry_tags(entry: Any) -> list[str]:
    out = []
    for t in (entry.get("tags") or []):
        term = (t.get("term") or "").strip()
        if term:
            out.append(term)
    return out[:12]
