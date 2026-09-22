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


def _kurse() -> dict:
    """Wie alt sind die Waehrungskurse?

    Ein veralteter Kurs ist der unangenehmste Fehler in dieser Anlage:
    er meldet sich nie. Eine Regel "max. 20 EUR" greift bei
    USD-Angeboten einfach ein bisschen daneben, jahrelang, und niemand
    merkt es, weil Deals ja weiter ankommen. Darum steht er hier
    neben Datenbank und Scheduler - ein Mangel, keine Stoerung.
    """
    from . import currency

    try:
        with SessionLocal() as db:
            from .db import get_setting
            from .models import User
            stand = get_setting(db, currency.SCHLUESSEL_STAND)
            automatisch = bool(get_setting(db, currency.SCHLUESSEL_AUTO, True))
            # Wie lange steht diese Anlage schon? Der aelteste Benutzer ist
            # der einzige verlaessliche Zeitstempel dafuer - die Datenbank
            # selbst merkt sich ihren Geburtstag nicht.
            seit = db.scalar(select(func.min(User.created_at)))
    except Exception as exc:
        return {"stand": "degraded", "text": f"nicht lesbar: {exc}"[:200]}

    alter = currency.alter_in_tagen(stand)
    befund = {"stand": "ok", "kurs_stand": stand, "alter_tage": alter,
              "automatisch": automatisch}
    if alter is None:
        # Frisch installiert: der Abruf steht noch aus, das ist kein
        # Mangel. Erst wenn die Anlage lange genug laeuft und trotzdem
        # nie ein Kurs ankam, stimmt hier etwas nicht - dann rechnet sie
        # naemlich dauerhaft mit den eingefrorenen Werten aus dem Code.
        jung = seit is not None and (utcnow() - seit) < timedelta(
            days=currency.VERALTET_NACH_TAGEN)
        if jung or seit is None:
            befund["text"] = "noch nicht geholt"
        else:
            befund["stand"] = "degraded"
            befund["text"] = ("noch nie aktualisiert - es gelten die festen "
                              "Vorgabewerte aus dem Code")
    elif currency.ist_veraltet(stand):
        befund["stand"] = "degraded"
        befund["text"] = f"{alter} Tage alt - Preisgrenzen rechnen ungenau"
    else:
        befund["text"] = f"{alter} Tage alt"
    return befund


RANG = {"ok": 0, "degraded": 1, "down": 2}


def bericht() -> dict:
    teile = {
        "datenbank": _datenbank(),
        "scheduler": _scheduler(),
        "quellen": _quellen(),
        "kurse": _kurse(),
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

        # Zustellung. Bewusst als Gauge ueber ein festes Fenster und
        # nicht als Counter: die Protokollzeilen werden nach
        # SPARBIT_LOG_RETENTION_DAYS geloescht, ein Counter wuerde dabei
        # zurueckspringen - und Prometheus liest einen Ruecksprung als
        # Neustart, also als riesigen Zuwachs. Ein Fenster-Gauge sagt,
        # was er sagt.
        from .models import NotificationLog
        seit = jetzt - timedelta(hours=24)
        versand = db.execute(
            select(NotificationLog.channel_type, NotificationLog.ok,
                   func.count(NotificationLog.id))
            .where(NotificationLog.created_at > seit)
            .group_by(NotificationLog.channel_type, NotificationLog.ok)
        ).all()
        gut: dict[str, int] = {}
        schlecht: dict[str, int] = {}
        for kanal, ok, anzahl in versand:
            ziel = gut if ok else schlecht
            ziel[kanal or "?"] = ziel.get(kanal or "?", 0) + int(anzahl or 0)
        kanaele = sorted(set(gut) | set(schlecht))
        bloecke.append(_zeile(
            "meldungen_24h", "Zugestellte Meldungen der letzten 24 Stunden",
            "gauge", [(f'{{kanal="{k}"}}', gut.get(k, 0)) for k in kanaele]))
        bloecke.append(_zeile(
            "meldungen_fehler_24h",
            "Fehlgeschlagene Zustellungen der letzten 24 Stunden", "gauge",
            [(f'{{kanal="{k}"}}', schlecht.get(k, 0)) for k in kanaele]))

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

    # Das Alter der Waehrungskurse gehoert in die Ueberwachung: es ist
    # der eine Fehler, der sich nie von selbst meldet. -1 heisst "noch
    # nie geholt".
    bloecke.append(_zeile(
        "kurse_alter_tage", "Alter der Waehrungskurse in Tagen (-1 = nie)",
        "gauge", [("", stand["teile"].get("kurse", {}).get("alter_tage", -1) or -1)]))

    return "\n".join(bloecke) + "\n"
