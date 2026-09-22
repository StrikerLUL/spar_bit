"""Antwortet auf die Frage, die /api/health bisher nicht beantwortete.

Der alte Endpunkt gab {"status": "ok"} zurueck - immer. Er sagte nur,
dass ein Webserver laeuft. Genau das weiss man aber schon, wenn man ihn
erreicht. Ob die Datenbank antwortet, ob der Scheduler noch Jobs hat, ob
seit Stunden eine Quelle durchgelaufen ist: alles unsichtbar.

Und das ist der Ausfall, auf den es ankommt. Faellt der Scheduler
stillschweigend aus, sieht das von aussen aus wie "heute keine Deals" -
nicht wie "ich bin kaputt". Ein Wachhund, der nur prueft, ob der Port
offen ist, meldet das nie.

Darum drei echte Pruefungen, jede mit einem Befund statt eines
Haekchens. Der Gesamtstand ist der schlechteste Einzelstand:
ok -> 200, degraded -> 200 (laeuft, aber mit Mangel), down -> 503.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select, text

from .db import SessionLocal, engine
from .models import Deal, SourceConfig, utcnow

log = logging.getLogger(__name__)

# Ab wann gilt "es kommt nichts mehr" als Mangel. Grosszuegig: die
# laengsten Intervalle liegen bei mehreren Stunden, und eine Nacht ohne
# neue Deals ist normal.
OHNE_LAUF_STUNDEN = 6


def _datenbank() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"stand": "ok", "text": "antwortet"}
    except Exception as exc:
        return {"stand": "down", "text": f"{type(exc).__name__}: {exc}"[:200]}


def _scheduler() -> dict:
    try:
        from .scheduler import scheduler
    except Exception as exc:
        return {"stand": "down", "text": f"nicht ladbar: {exc}"[:200]}

    if not scheduler.running:
        return {"stand": "down", "text": "laeuft nicht"}
    jobs = scheduler.get_jobs()
    if not jobs:
        return {"stand": "degraded", "text": "laeuft, aber ohne Jobs"}
    return {"stand": "ok", "text": f"{len(jobs)} Jobs", "jobs": len(jobs)}


def _quellen() -> dict:
    """Laeuft ueberhaupt noch etwas - und wenn nicht, warum?"""
    try:
        with SessionLocal() as db:
            configs = list(db.scalars(select(SourceConfig).where(
                SourceConfig.enabled.is_(True))))
            if not configs:
                return {"stand": "ok", "text": "keine Quelle eingeschaltet",
                        "eingeschaltet": 0}

            jetzt = utcnow()
            gesperrt = [c.id for c in configs
                        if c.circuit_open_until and c.circuit_open_until > jetzt]
            letzter = max((c.last_success for c in configs if c.last_success),
                          default=None)

            befund = {
                "stand": "ok",
                "eingeschaltet": len(configs),
                "gesperrt": gesperrt,
                "letzter_erfolg": letzter,
            }
            if len(gesperrt) == len(configs):
                befund["stand"] = "degraded"
                befund["text"] = "alle eingeschalteten Quellen sind gesperrt"
            elif letzter is None:
                befund["stand"] = "degraded"
                befund["text"] = "noch kein erfolgreicher Lauf"
            elif jetzt - letzter > timedelta(hours=OHNE_LAUF_STUNDEN):
                befund["stand"] = "degraded"
                stunden = int((jetzt - letzter).total_seconds() // 3600)
                befund["text"] = f"seit {stunden} h kein erfolgreicher Lauf"
            else:
                befund["text"] = f"{len(configs) - len(gesperrt)} laufen"
            return befund
    except Exception as exc:
        return {"stand": "down", "text": f"{type(exc).__name__}: {exc}"[:200]}


RANG = {"ok": 0, "degraded": 1, "down": 2}


def bericht() -> dict:
    teile = {
        "datenbank": _datenbank(),
        "scheduler": _scheduler(),
        "quellen": _quellen(),
    }
    gesamt = max(teile.values(), key=lambda t: RANG.get(t["stand"], 0))["stand"]
    return {"status": gesamt, "teile": teile}


# --- Metriken -------------------------------------------------------------

def _zeile(name: str, hilfe: str, typ: str, werte: list[tuple[str, float]]) -> str:
    kopf = [f"# HELP sparbit_{name} {hilfe}", f"# TYPE sparbit_{name} {typ}"]
    return "\n".join(kopf + [f"sparbit_{name}{marke} {wert}"
                             for marke, wert in werte])


def metriken() -> str:
    """Zahlen im Prometheus-Textformat.

    Die Daten liegen ohnehin schon in der Datenbank - SourceRun zaehlt
    Laeufe, Fehler und Treffer seit jeher mit. Bisher waren sie nur im
    UI zu sehen, also genau dort, wo man nicht hinschaut, wenn etwas
    ausfaellt.
    """
    bloecke: list[str] = []
    with SessionLocal() as db:
        configs = list(db.scalars(select(SourceConfig)))
        jetzt = utcnow()

        bloecke.append(_zeile(
            "quelle_laeufe_gesamt", "Laeufe je Quelle seit Beginn", "counter",
            [(f'{{quelle="{c.id}"}}', c.total_runs or 0) for c in configs]))
        bloecke.append(_zeile(
            "quelle_fehler_gesamt", "Fehlgeschlagene Laeufe je Quelle", "counter",
            [(f'{{quelle="{c.id}"}}', c.total_errors or 0) for c in configs]))
        bloecke.append(_zeile(
            "quelle_eintraege_gesamt", "Gelieferte Eintraege je Quelle", "counter",
            [(f'{{quelle="{c.id}"}}', c.total_items or 0) for c in configs]))
        bloecke.append(_zeile(
            "quelle_eingeschaltet", "1 wenn die Quelle laeuft", "gauge",
            [(f'{{quelle="{c.id}"}}', 1 if c.enabled else 0) for c in configs]))
        bloecke.append(_zeile(
            "quelle_gesperrt", "1 wenn der Schutzschalter zu ist", "gauge",
            [(f'{{quelle="{c.id}"}}',
              1 if (c.circuit_open_until and c.circuit_open_until > jetzt) else 0)
             for c in configs]))
        bloecke.append(_zeile(
            "quelle_sekunden_seit_erfolg",
            "Sekunden seit dem letzten erfolgreichen Lauf", "gauge",
            [(f'{{quelle="{c.id}"}}',
              int((jetzt - c.last_success).total_seconds()) if c.last_success else -1)
             for c in configs]))

        deals_gesamt = db.scalar(select(func.count()).select_from(Deal)) or 0
        deals_24h = db.scalar(select(func.count()).select_from(Deal).where(
            Deal.first_seen > jetzt - timedelta(hours=24))) or 0
        bloecke.append(_zeile("deals_gesamt", "Gespeicherte Deals", "gauge",
                              [("", deals_gesamt)]))
        bloecke.append(_zeile("deals_24h", "Neue Deals der letzten 24 Stunden",
                              "gauge", [("", deals_24h)]))

    stand = bericht()
    bloecke.append(_zeile(
        "gesund", "1 wenn der Teil in Ordnung ist", "gauge",
        [(f'{{teil="{name}"}}', 1 if teil["stand"] == "ok" else 0)
         for name, teil in stand["teile"].items()]))

    return "\n".join(bloecke) + "\n"
