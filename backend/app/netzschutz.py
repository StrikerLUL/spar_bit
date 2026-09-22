"""Wohin SparBit von sich aus Verbindungen aufbaut - und wohin nicht.

SparBit holt Adressen, die man ihm nennt: Feeds, Produktseiten der
Wunschliste, die Seite hinter einem Gratis-Angebot, Kandidaten der
Feed-Suche. Aus Sicht des Servers ist das eine Anfrage, die jemand von
aussen ausloest - und die im eigenen Netz landen kann.

Auf einem VPS ist das der Unterschied zwischen einer Produktseite und
`http://169.254.169.254/latest/meta-data/iam/security-credentials/`:
dieselbe Mechanik, nur dass am Ende die Zugangsdaten des Servers stehen.
Zu Hause sind es der Router unter 192.168.1.1 oder der Dienst, der auf
localhost lauscht und keine Anmeldung kennt, weil "da kommt ja niemand
hin".

Darum wird jede Adresse vor dem Verbindungsaufbau aufgeloest und die
IP geprueft - auch bei jeder Weiterleitung. Ein Server, der erst
brav antwortet und dann per 302 auf 127.0.0.1 zeigt, kommt damit
genauso wenig durch wie eine direkte Eingabe.

Zwei Ausnahmen, beide mit Absicht:

* **Benachrichtigungs-Kanaele** duerfen ins eigene Netz. Ein Gotify
  oder ntfy im Heimnetz ist der Normalfall, kein Angriff - und die
  Adresse hat man selbst eingetragen, sie kommt nicht von einer
  fremden Seite.
* **SPARBIT_ERLAUBE_PRIVATE_ZIELE=true** schaltet die Pruefung ganz ab,
  fuer den, der bewusst einen Feed aus dem eigenen Netz liest.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlsplit

import httpx

from .config import settings

log = logging.getLogger(__name__)

# Nur diese beiden Schemata. file:// und gopher:// haben hier nichts zu
# suchen, und httpx wuerde sie ohnehin nicht sprechen - aber eine
# Fehlermeldung ist besser als ein Stacktrace.
ERLAUBTE_SCHEMATA = {"http", "https"}


class ZielVerboten(ValueError):
    """Die Adresse zeigt ins eigene Netz (oder ist keine Web-Adresse)."""


def _ist_heikel(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Gibt den Grund zurueck, wenn diese IP nicht angefasst werden soll."""
    if ip.is_loopback:
        return "localhost"
    if ip.is_link_local:
        # 169.254.169.254 ist bei AWS, GCP, Azure und Hetzner der Weg zu
        # den Zugangsdaten der Maschine.
        return "Link-Local (Cloud-Metadaten)"
    if ip.is_private:
        return "privates Netz"
    if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return "reservierter Bereich"
    # IPv6-Adressen, die eine IPv4 einpacken, zaehlen wie die IPv4 darin.
    entpackt = getattr(ip, "ipv4_mapped", None) or getattr(ip, "sixtofour", None)
    if entpackt is not None:
        return _ist_heikel(entpackt)
    return None


def _adressen(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def pruefe_sync(url: str) -> None:
    """Adresse pruefen. Wirft ZielVerboten, wenn sie ins eigene Netz zeigt."""
    if settings.erlaube_private_ziele:
        return

    teile = urlsplit(url)
    if teile.scheme.lower() not in ERLAUBTE_SCHEMATA:
        raise ZielVerboten(
            f"Nur http und https - '{teile.scheme or 'ohne Schema'}' nicht.")
    if not teile.hostname:
        raise ZielVerboten("In der Adresse steht kein Rechnername.")

    port = teile.port or (443 if teile.scheme.lower() == "https" else 80)
    try:
        adressen = _adressen(teile.hostname, port)
    except socket.gaierror as exc:
        raise ZielVerboten(f"Rechnername '{teile.hostname}' nicht aufloesbar.") from exc

    for roh in adressen:
        try:
            ip = ipaddress.ip_address(roh.split("%")[0])   # %eth0 abschneiden
        except ValueError:
            continue
        grund = _ist_heikel(ip)
        if grund:
            # Alle Adressen pruefen, nicht nur die erste: welche das
            # Betriebssystem nimmt, entscheidet es selbst.
            raise ZielVerboten(
                f"'{teile.hostname}' zeigt auf {ip} - {grund}. SparBit ruft "
                f"von sich aus nichts im eigenen Netz ab. (Bewusst gewollt? "
                f"SPARBIT_ERLAUBE_PRIVATE_ZIELE=true)")


async def pruefe(url: str) -> None:
    """Wie pruefe_sync, aber ohne den Ereignis-Schleifen-Thread zu blockieren."""
    await asyncio.to_thread(pruefe_sync, url)


async def haken(request: httpx.Request) -> None:
    """httpx-Haken: laeuft vor jeder Anfrage - auch vor jeder Weiterleitung.

    Genau darum haengt die Pruefung hier und nicht an den Aufrufstellen:
    eine Weiterleitung entsteht erst im Client, und keine Aufrufstelle
    sieht sie je.
    """
    if request.extensions.get("sparbit_intern"):
        return                      # eigener Kanal, Adresse selbst eingetragen
    await pruefe(str(request.url))
