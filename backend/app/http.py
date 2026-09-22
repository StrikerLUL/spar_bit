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


class ZuGross(Exception):
    """Die Antwort ueberschreitet das Limit und wurde abgebrochen.

    Einzelne Module hatten ihre eigene Obergrenze (Produktseiten,
    Gratis-Gegenprobe, Bilder), die Feed-Suche keine. Eine Adresse, die
    man selbst eintraegt, kann aber auf eine beliebig grosse Datei
    zeigen - und httpx laedt sie vollstaendig in den Speicher, bevor
    irgendein Modul sie zu Gesicht bekommt. Die Grenze gehoert darum
    hierhin, wo gelesen wird, nicht dorthin, wo ausgewertet wird.
    """

    def __init__(self, gelesen: int, grenze: int):
        super().__init__(f"Antwort groesser als {grenze} Bytes - abgebrochen "
                         f"nach {gelesen}.")
        self.gelesen = gelesen
        self.grenze = grenze


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
        max_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        from .netzschutz import haken as netz_haken

        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.6",
            },
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            # Prueft jede Adresse vor dem Verbindungsaufbau - auch die
            # jeder Weiterleitung, die erst hier drin entsteht.
            event_hooks={"request": [netz_haken]},
        )
        self.per_host_delay = per_host_delay
        self.max_retries = max_retries
        self.max_bytes = max_bytes
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
                resp = await self._lies_begrenzt(url, hdrs, **kwargs)
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

    async def _lies_begrenzt(self, url: str, hdrs: dict[str, str],
                             **kwargs: Any) -> httpx.Response:
        """Antwort stueckweise lesen und bei self.max_bytes abbrechen.

        Erst die angekuendigte Laenge pruefen - steht sie im Header, muss
        gar nichts geladen werden. Fehlt sie oder luegt sie, zaehlt das
        tatsaechlich Gelesene.
        """
        async with self._client.stream("GET", url, headers=hdrs, **kwargs) as antwort:
            angekuendigt = antwort.headers.get("content-length")
            if angekuendigt and angekuendigt.isdigit() and int(angekuendigt) > self.max_bytes:
                raise ZuGross(int(angekuendigt), self.max_bytes)

            if antwort.status_code == 304 or antwort.status_code >= 400:
                # Fehler- und 304-Antworten werden nicht ausgewertet; der
                # Rumpf interessiert nur fuer die Meldung.
                roh = b""
                async for stueck in antwort.aiter_bytes():
                    roh += stueck
                    if len(roh) > 64 * 1024:
                        break
            else:
                roh = b""
                async for stueck in antwort.aiter_bytes():
                    roh += stueck
                    if len(roh) > self.max_bytes:
                        raise ZuGross(len(roh), self.max_bytes)

            # Der Strom liefert bereits entpackte Bytes - genau darum
            # greift die Grenze auch gegen eine Zip-Bombe. Die Kopfzeilen
            # zur Kodierung muessen dann aber weg, sonst wuerde jemand
            # spaeter ein zweites Mal entpacken wollen.
            kopf = [(k, v) for k, v in antwort.headers.multi_items()
                    if k.lower() not in ("content-encoding", "content-length")]
            return httpx.Response(antwort.status_code, headers=kopf,
                                  content=roh, request=antwort.request)

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
        kwargs.setdefault("extensions", {"sparbit_intern": True})
        return await self._client.post(url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Wie post() - Matrix schickt Nachrichten per PUT."""
        kwargs.setdefault("timeout", 20.0)
        kwargs.setdefault("extensions", {"sparbit_intern": True})
        return await self._client.put(url, **kwargs)

    async def get_intern(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET auf einen Dienst im eigenen Netz, den man selbst eingetragen hat.

        Gegenstueck zu post(): dieselbe Ausnahme vom Netzschutz, nur
        lesend. Gebraucht vom Render-Dienst der Wunschliste, der
        ueblicherweise als Nachbarcontainer laeuft und damit auf einer
        Adresse sitzt, die SparBit sonst nicht anfassen wuerde.
        """
        kwargs.setdefault("timeout", 60.0)   # ein Browser braucht laenger
        kwargs.setdefault("extensions", {"sparbit_intern": True})
        antwort = await self._client.get(url, **kwargs)
        antwort.raise_for_status()
        return antwort

    async def get_text(self, url: str, **kwargs: Any) -> str:
        return (await self.get(url, **kwargs)).text

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.get(url, **kwargs)
        ctype = resp.headers.get("content-type", "")
        if "json" not in ctype and resp.text.lstrip()[:1] not in ("{", "["):
            raise ValueError(
                f"Erwartet JSON, bekommen '{ctype or 'unbekannt'}' "
                f"({len(resp.content)} Bytes). Endpoint liefert vermutlich HTML "
                f"(Block-Seite oder Redirect)."
            )
        return resp.json()
