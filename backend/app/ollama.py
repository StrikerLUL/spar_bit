"""Ein lokales Sprachmodell darf mitreden - wenn du es einschaltest.

SparBit kommt ohne aus und bleibt dabei: die Warengruppe entsteht aus
Stichwoertern (`warengruppe.py`), und die sind nachvollziehbar. Ein
Restbestand bleibt trotzdem uebrig - Titel wie „Philips HD9200/90" oder
„Tefal E43806", bei denen kein Wort verraet, worum es geht.

Fuer genau diesen Rest kann ein lokales Modell einspringen. Die Regeln:

* **Aus, bis jemand es einschaltet.** Keine Vorgabe-Adresse, kein
  stiller Versuch auf localhost.
* **Nur lokal gedacht.** Der Abruf laeuft ueber `PoliteClient.post` -
  denselben Weg wie ein Gotify im Heimnetz, also ohne die
  Netzschutz-Sperre fuer private Adressen. Das ist richtig fuer eine
  Adresse, die man selbst eintraegt, und es heisst zugleich: wer hier
  eine fremde Cloud eintraegt, schickt ihr jeden unerkannten Deal-Titel.
  Das waere ein Widerspruch zum Rest dieser Anwendung - SparBit haelt
  niemanden davon ab, aber es steht hier.
* **Nur der Rest.** Das Modell sieht nur, was die Regeln nicht erkannt
  haben. Das sind je nach Feed ein paar Prozent.
* **Nur eine Auswahl.** Gefragt wird nicht "was ist das?", sondern
  "welche dieser zwoelf Gruppen passt?". Antwortet es etwas anderes,
  wird die Antwort verworfen.
* **Erkennbar.** Was vom Modell kommt, wird als solches vermerkt
  (`warengruppe_quelle = "modell"`), damit man es spaeter auseinander
  halten kann.

Kein neues Paket: Ollama spricht HTTP, und einen HTTP-Client gibt es
hier schon.
"""
from __future__ import annotations

import logging

from .warengruppe import GRUPPEN

log = logging.getLogger(__name__)

# Schluessel in der Settings-Tabelle.
SCHLUESSEL_URL = "ollama_url"          # z. B. http://127.0.0.1:11434
SCHLUESSEL_MODELL = "ollama_modell"    # z. B. llama3.2:3b
VORGABE_MODELL = "llama3.2:3b"

# Mehr Zeit als fuer eine Quelle: ein kleines Modell auf einer CPU
# braucht fuer diese Aufgabe gut und gern zwei Sekunden.
TIMEOUT = 20.0

_ANWEISUNG = (
    "Du ordnest Produkte einer Warengruppe zu. Antworte mit GENAU EINEM "
    "Wort aus dieser Liste und sonst nichts:\n{gruppen}\n"
    "Passt keine Gruppe, antworte: keine"
)


def eingerichtet(url: str | None) -> bool:
    return bool((url or "").strip())


async def warengruppe(http, url: str, titel: str,
                      modell: str | None = None) -> str | None:
    """Das Modell fragen. Gibt eine Gruppen-ID zurueck oder None.

    Jeder Fehler endet in None: ein Modell, das nicht laeuft, darf den
    Quellenlauf nicht anhalten. Die Warengruppe ist eine Zugabe, kein
    Teil des Fundes.
    """
    ziel = (url or "").strip().rstrip("/")
    if not ziel or not (titel or "").strip():
        return None

    nutzlast = {
        "model": (modell or VORGABE_MODELL).strip(),
        "system": _ANWEISUNG.format(gruppen=", ".join(sorted(GRUPPEN))),
        "prompt": titel[:300],
        "stream": False,
        "options": {
            # Bei dieser Aufgabe gibt es eine richtige Antwort - Kreativitaet
            # waere hier nur eine Fehlerquelle.
            "temperature": 0.0,
            "num_predict": 8,
        },
    }

    try:
        antwort = await http.post(f"{ziel}/api/generate", json=nutzlast,
                                  timeout=TIMEOUT)
        if antwort.status_code >= 300:
            log.debug("Ollama antwortete %s", antwort.status_code)
            return None
        roh = str(antwort.json().get("response") or "")
    except Exception as exc:
        log.debug("Ollama nicht erreichbar: %s", exc)
        return None

    return _auswerten(roh)


def _auswerten(roh: str) -> str | None:
    """Die Antwort auf eine bekannte Gruppe eindampfen.

    Kleine Modelle antworten gern mit einem ganzen Satz ("Das ist wohl
    Elektronik."). Darum wird nicht verglichen, sondern gesucht - aber
    nur nach den Gruppen, die es gibt. Alles andere gilt als "keine
    Antwort", nicht als neue Gruppe.
    """
    text = roh.strip().lower()
    if not text:
        return None
    for gruppe in GRUPPEN:
        if gruppe in text:
            return gruppe
    return None
