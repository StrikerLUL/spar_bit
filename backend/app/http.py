"""Hoeflicher HTTP-Client: eigener UA, ETag/Last-Modified, Backoff, Ratelimit."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_UA = (
    "SparBit/1.0 (self-hosted deal monitor; "
    "+https://github.com/StrikerLUL/spar_bit)"
)


# Hosts, die mehr Abstand verlangen als der Standard. Reddit drosselt
# Anfragen aus Rechenzentrums-Netzen hart (HTTP 429 mit "retry after 58s"),
# und ein VPS steht praktisch immer in so einem Netz. Drei Sekunden zwischen
# zwei Subreddits kosten nichts - der Scheduler laeuft ohnehin nur alle paar
# Minuten - und sind der Unterschied zwischen "liefert" und "429".
HOST_PAUSEN: dict[str, float] = {
    "reddit.com": 3.0,
}


def host_pause(host: str, standard: float) -> float:
    """Mindestabstand fuer diesen Host - Domain-Suffixe zaehlen mit."""
    host = (host or "").lower().rstrip(".")
    for domain, pause in HOST_PAUSEN.items():
        if host == domain or host.endswith("." + domain):
            return max(standard, pause)
    return standard


class RateLimited(Exception):
    """429 (oder ein 5xx, das nicht aufhoert) - der Host will Ruhe.

    Eigene Klasse, weil sich daran etwas entscheidet: ein Rate-Limit ist
    kein kaputter Endpoint. Der Scheduler legt die Quelle darum schlafen,
    statt sie als fehlerhaft zu zaehlen und irgendwann ganz abzuschalten.
    """

    def __init__(self, retry_after: float, status: int):
        super().__init__(f"HTTP {status}, retry after {retry_after:.0f}s")
        self.retry_after = retry_after
        self.status = status


class NotModified(Exception):
    """304 - nichts Neues, Aufrufer kann abbrechen."""


@dataclass
class _HostState:
    """Pro Host: Mindestabstand zwischen Requests + Ratelimit-Sperre."""
    last_request: float = 0.0
    blocked_until: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class PoliteClient:
    """Ein httpx-Client fuer alle Quellen, mit Manieren.

    - eigener User-Agent
    - min. Abstand pro Host (Default 1s), damit wir niemanden hammern
    - ETag/Last-Modified werden pro Cache-Key gehalten -> 304 spart Traffic
    - exponentieller Backoff mit Jitter bei 429/5xx, respektiert Retry-After
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        timeout: float = 25.0,
        per_host_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.6",
            },
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self.per_host_delay = per_host_delay
        self.max_retries = max_retries
        self._hosts: dict[str, _HostState] = {}
        self._cache: dict[str, tuple[str | None, str | None]] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    def _state(self, host: str) -> _HostState:
        if host not in self._hosts:
            self._hosts[host] = _HostState()
        return self._hosts[host]

    async def _throttle(self, host: str) -> None:
        st = self._state(host)
        async with st.lock:
            now = time.monotonic()
            if st.blocked_until > now:
                raise RateLimited(st.blocked_until - now, 429)
            wait = host_pause(host, self.per_host_delay) - (now - st.last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            st.last_request = time.monotonic()

    async def get(
        self,
        url: str,
        *,
        cache_key: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """GET mit Backoff. Wirft NotModified bei 304, RateLimited bei 429."""
        host = httpx.URL(url).host or url
        hdrs = dict(headers or {})

        if cache_key:
            etag, lastmod = self._cache.get(cache_key, (None, None))
            if etag:
                hdrs["If-None-Match"] = etag
            if lastmod:
                hdrs["If-Modified-Since"] = lastmod

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            await self._throttle(host)
            try:
                resp = await self._client.get(url, headers=hdrs, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(self._backoff(attempt))
                continue

            if resp.status_code == 304:
                raise NotModified()

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = self._retry_after(resp)
                if resp.status_code == 429:
                    # Host fuer die genannte Dauer komplett sperren.
                    self._state(host).blocked_until = time.monotonic() + retry_after
                if attempt >= self.max_retries:
                    raise RateLimited(retry_after, resp.status_code)
                await asyncio.sleep(min(retry_after, self._backoff(attempt)))
                continue

            resp.raise_for_status()

            if cache_key:
                self._cache[cache_key] = (
                    resp.headers.get("etag"),
                    resp.headers.get("last-modified"),
                )
            return resp

        raise last_exc or RuntimeError("unreachable")

    def _backoff(self, attempt: int) -> float:
        return min(30.0, (2 ** attempt) * 1.5) + random.uniform(0, 0.75)

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float:
        raw = resp.headers.get("retry-after")
        if raw:
            try:
                return max(1.0, float(raw))
            except ValueError:
                pass
        return 60.0

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Fuer Benachrichtigungs-Kanaele.

        Ohne Drosselung und ohne Wiederholung: das Ziel ist der eigene Bot
        bzw. Webhook, nicht eine fremde Seite, die man schonen muesste. Wer
        wiederholen will, tut das mit eigener Logik - eine doppelt
        zugestellte Meldung ist schlimmer als eine ausgefallene.
        """
        kwargs.setdefault("timeout", 20.0)
        return await self._client.post(url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Wie post() - Matrix schickt Nachrichten per PUT."""
        kwargs.setdefault("timeout", 20.0)
        return await self._client.put(url, **kwargs)

    async def get_text(self, url: str, **kwargs: Any) -> str:
        return (await self.get(url, **kwargs)).text

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.get(url, **kwargs)
        ctype = resp.headers.get("content-type", "")
        if "json" not in ctype and not resp.text.lstrip()[:1] in ("{", "["):
            raise ValueError(
                f"Erwartet JSON, bekommen '{ctype or 'unbekannt'}' "
                f"({len(resp.content)} Bytes). Endpoint liefert vermutlich HTML "
                f"(Block-Seite oder Redirect)."
            )
        return resp.json()
