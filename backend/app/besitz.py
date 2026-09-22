"""Wem gehoert was - die eine Stelle, die das beantwortet.

Mit mehreren Benutzern zerfaellt die Datenbank in zwei Arten von Zeilen:
gemeinsame (Deals, Quellen, Systemeinstellungen) und persoenliche
(Regeln, Kanaele, Wunschlisten, gelernte Vorlieben). Fuer die zweite
Sorte muss an jeder Abfrage dieselbe Frage beantwortet werden - und
genau deshalb steht sie hier und nicht acht Mal verteilt im Code.

Zwei Regeln, mehr nicht:

* **NULL gehoert allen.** So sehen Zeilen aus, die es vor den
  Benutzerkonten schon gab. Die Migration ordnet sie dem Erstbenutzer
  zu; was danach noch NULL ist, bleibt fuer alle sichtbar.
* **Ein Admin sieht seine eigenen Sachen.** Nicht die der anderen -
  Administrator heisst "darf die Anlage verwalten", nicht "liest mit".
  Wer die Regeln eines anderen braucht, bekommt sie ueber den Export.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.sql import Select

from .models import User


def nur_meine(stmt: Select, modell, user: User) -> Select:
    """Abfrage auf das einschraenken, was diesem Benutzer gehoert."""
    return stmt.where(or_(modell.benutzer_id == user.id,
                          modell.benutzer_id.is_(None)))


def gehoert_mir(zeile, user: User) -> bool:
    if zeile is None:
        return False
    besitzer = getattr(zeile, "benutzer_id", None)
    return besitzer is None or besitzer == user.id
