"""Was im Backend steht und in der Oberflaeche noch einmal - gespiegelt,
nicht geholt.

An ein paar Stellen kennt die Oberflaeche eine Liste, die eigentlich dem
Backend gehoert: die Warengruppen zum Beispiel. Das ist Absicht - zwoelf
feste Werte ueber einen eigenen Endpunkt zu holen hiesse, fuer eine Liste
einen Ladezustand zu bauen, die nie leer ist.

Der Preis dafuer ist genau dieser Test. Ohne ihn faellt eine neue Gruppe
im Backend niemandem auf: die Knoepfe im Regel-Editor treffen dann
einfach nichts, und das sieht aus wie "die Regel findet nichts".
"""
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
UI_QUELLEN = WURZEL / "frontend" / "src"


def _ids_aus_ui(konstante: str) -> list[str]:
    """Die `id`-Werte einer Konstanten irgendwo in der Oberflaeche lesen.

    Gesucht wird im ganzen Baum statt an einem festen Pfad: Dateien
    werden umbenannt und aufgeteilt, und ein Test, der danach
    "Datei nicht gefunden" sagt, wird abgeschaltet statt repariert.
    """
    import re

    muster = re.compile(rf"const {konstante}[^=]*=\s*\[(.*?)\n\];", re.DOTALL)
    for datei in sorted(UI_QUELLEN.rglob("*.tsx")):
        treffer = muster.search(datei.read_text(encoding="utf-8"))
        if treffer:
            return re.findall(r'id:\s*"([^"]+)"', treffer.group(1))
    raise AssertionError(
        f"Die Konstante {konstante} steht nirgends in frontend/src. "
        f"Wurde sie umbenannt? Dann gehoert dieser Test nachgezogen.")


@pytest.mark.skipif(not UI_QUELLEN.exists(),
                    reason="Ohne Oberflaeche im Baum gibt es nichts abzugleichen.")
def test_die_warengruppen_stimmen_ueberein():
    from app.warengruppe import GRUPPEN

    im_ui = _ids_aus_ui("WARENGRUPPEN")
    assert im_ui, "Im Regel-Editor steht keine einzige Warengruppe."

    fehlen = [g for g in GRUPPEN if g not in im_ui]
    zu_viel = [g for g in im_ui if g not in GRUPPEN]
    assert not fehlen, (
        f"Diese Warengruppen fehlen im Regel-Editor: {fehlen}. "
        f"Nachtragen bei der Konstanten WARENGRUPPEN in frontend/src.")
    assert not zu_viel, (
        f"Diese Knoepfe im Regel-Editor treffen nichts mehr: {zu_viel}.")


@pytest.mark.skipif(not UI_QUELLEN.exists(), reason="keine Oberflaeche im Baum")
def test_die_reihenfolge_stimmt_auch():
    """Nicht Pedanterie: die Reihenfolge im Backend ist die, in der
    entschieden wird (spezifisch vor allgemein). Wer sie im UI anders
    sieht, baut Regeln mit falschen Erwartungen."""
    from app.warengruppe import GRUPPEN

    assert _ids_aus_ui("WARENGRUPPEN") == list(GRUPPEN)
