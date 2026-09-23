"""Bremse fuer die Endpunkte, die nach draussen greifen.

Die Anmeldung hat schon eine Bremse (loginguard). Alles dahinter hatte
keine - und dort sitzen die teuren Knoepfe: "Quelle jetzt testen",
"Feed suchen", "Preisfehler nachpruefen", die Sammeleingabe der
Wunschliste. Ein Aufruf hier loest mehrere Abrufe dort aus. Wer den
Knopf in einer Schleife drueckt (oder ein Skript daran haengt), macht
aus SparBit einen Verstaerker: eine Anfrage rein, zwanzig Anfragen an
einen fremden Shop raus. Das faellt nicht auf SparBit zurueck, sondern
auf die IP des VPS - und irgendwann steht sie auf einer Sperrliste.

Gezaehlt wird je Konto, nicht je IP: der Haushalt sitzt hinter derselben
IP, und das Konto ist die Einheit, die auch sonst zaehlt. Ohne Konto
kommt hier ohnehin niemand vorbei.

Die Zaehler liegen im Speicher, anders als bei der Anmeldebremse. Das
ist Absicht: hier geht es um Versehen und Uebermut, nicht um einen
Angreifer, der Passwoerter raet. Ein Neustart, der die Zaehler
zuruecksetzt, kostet nichts - und dafuer kostet jeder Aufruf keine
Schreiboperation in der Datenbank.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status

from .auth import current_user
from .models import User

log = logging.getLogger(__name__)


@dataclass
class _Eimer:
    """Token-Bucket: `fuellung` Marken, die mit `rate` pro Sekunde nachlaufen.

    Ein reiner Zaehler pro Minute waere haerter als noetig - er wuerde
    zehn Klicks in zehn Sekunden erlauben und den elften eine Minute
    lang bestrafen. Der Eimer laesst einen kurzen Schwall zu und danach
    ein gleichmaessiges Tempo, was dem entspricht, wie Menschen Knoepfe
    druecken.
    """
    rate: float
    grenze: float
    fuellung: float = field(default=0.0)
    stand: float = field(default_factory=time.monotonic)

    def nimm(self, jetzt: float) -> float:
        """0.0, wenn die Marke da war - sonst die Wartezeit in Sekunden."""
        self.fuellung = min(self.grenze, self.fuellung + (jetzt - self.stand) * self.rate)
        self.stand = jetzt
        if self.fuellung >= 1.0:
            self.fuellung -= 1.0
            return 0.0
        return (1.0 - self.fuellung) / self.rate


_eimer: dict[tuple[str, int], _Eimer] = {}


def _aufraeumen(jetzt: float) -> None:
    """Volle Eimer sind vergessene Eimer - sie belegen nur Speicher."""
    if len(_eimer) < 512:
        return
    tot = [k for k, e in _eimer.items()
           if e.fuellung + (jetzt - e.stand) * e.rate >= e.grenze]
    for k in tot:
        _eimer.pop(k, None)


def zuruecksetzen() -> None:
    """Nur fuer Tests - zwischen zwei Faellen soll nichts nachhallen."""
    _eimer.clear()


def pruefe(schluessel: str, benutzer_id: int, pro_minute: float,
           stoss: int, jetzt: float | None = None) -> float:
    """Kern ohne FastAPI, damit er sich ohne HTTP testen laesst."""
    jetzt = time.monotonic() if jetzt is None else jetzt
    _aufraeumen(jetzt)
    eimer = _eimer.get((schluessel, benutzer_id))
    if eimer is None:
        # Voll starten: der erste Klick nach dem Anmelden soll nie warten.
        eimer = _Eimer(rate=pro_minute / 60.0, grenze=float(stoss),
                       fuellung=float(stoss), stand=jetzt)
        _eimer[(schluessel, benutzer_id)] = eimer
    return eimer.nimm(jetzt)


def drossel(schluessel: str, pro_minute: float, stoss: int = 5) -> Callable:
    """Dependency-Fabrik. `stoss` ist, wie viele Klicks am Stueck durchgehen.

        @router.post("/teuer", dependencies=[Depends(drossel("teuer", 6))])
    """
    def abhaengigkeit(user: User = Depends(current_user)) -> None:
        warte = pruefe(schluessel, user.id, pro_minute, stoss)
        if warte <= 0:
            return
        log.info("Gedrosselt: %s von Benutzer %s, noch %.0fs",
                 schluessel, user.username, warte)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Zu viele Anfragen hintereinander. In {warte:.0f} Sekunden "
                   f"geht es weiter — die Bremse schuetzt die fremden Server, "
                   f"die SparBit hier abfragt.",
            # Damit ein Skript nicht raten muss und die Oberflaeche den
            # Knopf so lange ausgrauen kann.
            headers={"Retry-After": str(max(1, int(warte) + 1))},
        )

    return abhaengigkeit
