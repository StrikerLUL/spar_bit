"""Zusatzfunktionen: Statistiken, Deal-Detail, Preisalarme, Export/Import."""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth import current_user, darf_schreiben
from ..besitz import gehoert_mir, nur_meine
from ..currency import DEFAULT_RATES, get_rates, set_rates, to_eur
from ..db import get_db, get_setting, set_setting
from ..gratischeck import LABEL as GRATIS_LABEL
from ..images import aufraeumen as bilder_aufraeumen
from ..images import bild_verzeichnis
from ..images import statistik as bild_statistik
from ..models import (
    Deal,
    DealOffer,
    Match,
    PriceHistory,
    Rule,
    SavedSearch,
    SourceConfig,
    User,
    utcnow,
)
from ..pricefehler import HEISS as PF_HEISS
from ..pricefehler import SCHWELLE_HEISS, bewerte_deal
from ..pricefehler import VERDACHT as PF_VERDACHT

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["extras"],
                   dependencies=[Depends(current_user)])


# --- Bilder ----------------------------------------------------------------
# Eigener Router ohne Login-Pflicht: das <img>-Tag im Browser schickt zwar das
# Cookie mit, aber ein 401 auf ein Bild waere nur ein kaputtes Bild ohne
# erkennbaren Grund. Ausgeliefert werden ausschliesslich Dateien aus dem
# eigenen Cache-Verzeichnis, benannt nach einem Hash - erraten kann man die
# nicht, und Deal-Bilder sind ohnehin oeffentliche Produktfotos.

bilder_router = APIRouter(prefix="/api/bilder", tags=["bilder"])


@bilder_router.get("/{datei}")
def bild_ausliefern(datei: str):
    from fastapi.responses import FileResponse, Response

    verzeichnis = bild_verzeichnis().resolve()
    ziel = (verzeichnis / datei).resolve()
    # Kein Ausbrechen aus dem Verzeichnis ueber ".." im Dateinamen.
    if not ziel.is_relative_to(verzeichnis) or not ziel.is_file():
        # 1x1-Platzhalter statt 404: eine kaputte Karte sieht schlimmer aus
        # als ein leeres Bild, und das Frontend blendet es ohnehin aus.
        return Response(status_code=404)
    return FileResponse(ziel, headers={"Cache-Control": "public, max-age=604800"})


# --- Statistiken -----------------------------------------------------------

@router.get("/stats/timeline")
def timeline(tage: int = Query(30, ge=7, le=180),
             db: Session = Depends(get_db)) -> dict:
    """Deals, Gratis-Funde und Treffer je Tag - fuer die Diagramme."""
    seit = utcnow() - timedelta(days=tage)

    deals = db.execute(
        select(func.date(Deal.first_seen), func.count(Deal.id),
               func.sum(func.cast(Deal.ist_gratis, func.count(Deal.id).type)))
        .where(Deal.first_seen >= seit).group_by(func.date(Deal.first_seen))
    ).all()

    treffer = db.execute(
        select(func.date(Match.created_at), func.count(Match.id))
        .where(Match.created_at >= seit).group_by(func.date(Match.created_at))
    ).all()
    treffer_map = {str(row[0]): row[1] for row in treffer}

    ersparnis = db.execute(
        select(func.date(Deal.first_seen),
               func.sum(Deal.originalpreis - Deal.preis))
        .where(Deal.first_seen >= seit, Deal.originalpreis.isnot(None),
               Deal.preis.isnot(None), Deal.originalpreis > Deal.preis)
        .group_by(func.date(Deal.first_seen))
    ).all()
    ersparnis_map = {str(row[0]): float(row[1] or 0) for row in ersparnis}

    deal_map = {str(row[0]): (row[1], int(row[2] or 0)) for row in deals}

    # Luecken auffuellen, damit die Kurve keine Spruenge macht.
    heute = date.today()
    punkte = []
    for offset in range(tage - 1, -1, -1):
        tag = str(heute - timedelta(days=offset))
        anzahl, gratis = deal_map.get(tag, (0, 0))
        punkte.append({
            "tag": tag,
            "deals": anzahl,
            "gratis": gratis,
            "treffer": treffer_map.get(tag, 0),
            "ersparnis": round(ersparnis_map.get(tag, 0.0), 2),
        })
    return {"tage": tage, "punkte": punkte}


@router.get("/stats/quellen")
def quellen_stats(tage: int = Query(30, ge=1, le=180),
                  db: Session = Depends(get_db)) -> list[dict]:
    """Je Quelle: wie viel kommt rein, wie viel davon ist wirklich relevant."""
    seit = utcnow() - timedelta(days=tage)

    gesamt = dict(db.execute(
        select(Deal.quelle, func.count(Deal.id))
        .where(Deal.first_seen >= seit).group_by(Deal.quelle)).all())
    gratis = dict(db.execute(
        select(Deal.quelle, func.count(Deal.id))
        .where(Deal.first_seen >= seit, Deal.ist_gratis.is_(True))
        .group_by(Deal.quelle)).all())
    getroffen = dict(db.execute(
        select(Deal.quelle, func.count(func.distinct(Match.deal_id)))
        .join(Match, Match.deal_id == Deal.id)
        .where(Match.created_at >= seit).group_by(Deal.quelle)).all())

    out = []
    for quelle, anzahl in sorted(gesamt.items(), key=lambda kv: -kv[1]):
        treffer = getroffen.get(quelle, 0)
        out.append({
            "quelle": quelle,
            "deals": anzahl,
            "gratis": gratis.get(quelle, 0),
            "treffer": treffer,
            # Signalanteil: wie viel Prozent des Rauschens war brauchbar.
            "signalquote": round(treffer / anzahl * 100, 1) if anzahl else 0.0,
        })
    return out


@router.get("/stats/haendler")
def haendler_stats(limit: int = Query(12, le=50),
                   db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Deal.haendler, func.count(Deal.id),
               func.avg(Deal.rabatt_prozent))
        .where(Deal.haendler.isnot(None), Deal.haendler != "")
        .group_by(Deal.haendler).order_by(desc(func.count(Deal.id))).limit(limit)
    ).all()
    return [{"haendler": r[0], "anzahl": r[1],
             "schnitt_rabatt": round(float(r[2] or 0), 1)} for r in rows]


# --- Deal-Detail und Preisverlauf -----------------------------------------

@router.get("/deals/{deal_id}/detail")
def deal_detail(deal_id: int, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")

    verlauf = db.scalars(
        select(PriceHistory).where(PriceHistory.deal_id == deal_id)
        .order_by(PriceHistory.ts.asc()).limit(200))
    # Der Verlauf kann Waehrungen mischen (erst EUR von mydealz, dann USD von
    # CheapShark). Fuer Kurve und Tiefst-/Hoechstwert zaehlt darum der
    # Euro-Betrag - sonst entsteht beim Waehrungswechsel ein Sprung, den es
    # nie gegeben hat, und die Beschriftung waere schlicht falsch.
    punkte = [{"ts": p.ts, "preis": p.preis, "waehrung": p.waehrung,
               "preis_eur": to_eur(p.preis, p.waehrung), "quelle": p.quelle}
              for p in verlauf]

    regeln = db.execute(
        select(Rule.name, Match.created_at).join(Match, Match.rule_id == Rule.id)
        .where(Match.deal_id == deal_id)).all()

    angebote = sorted(
        db.scalars(select(DealOffer).where(DealOffer.deal_id == deal_id)),
        # Guenstigster zuerst; Angebote ohne erkannten Preis ans Ende.
        key=lambda a: (a.preis_eur if a.preis_eur is not None
                       else (a.preis if a.preis is not None else float("inf"))),
    )

    preise_eur = [p["preis_eur"] for p in punkte if p["preis_eur"] is not None]
    return {
        "id": deal.id, "titel": deal.titel, "beschreibung": deal.beschreibung,
        "url": deal.url, "bild": deal.bild, "bild_lokal": deal.bild_lokal,
        "preis": deal.preis,
        "preis_eur": deal.preis_eur, "originalpreis": deal.originalpreis,
        "rabatt_prozent": deal.rabatt_prozent, "waehrung": deal.waehrung,
        "ist_gratis": deal.ist_gratis, "haendler": deal.haendler,
        "quelle": deal.quelle, "also_from": deal.also_from or [],
        "temperatur": deal.temperatur, "tags": deal.tags or [],
        "first_seen": deal.first_seen, "last_seen": deal.last_seen,
        "seen_count": deal.seen_count, "bookmarked": deal.bookmarked,
        "alarm_preis": deal.alarm_preis, "alarm_ausgeloest": deal.alarm_ausgeloest,
        "notiz": deal.notiz,
        "fehler_score": deal.fehler_score or 0, "fehler_stufe": deal.fehler_stufe,
        "fehler_gruende": deal.fehler_gruende or [],
        "fehler_erwartet_eur": deal.fehler_erwartet_eur,
        "erwachsen": bool(deal.erwachsen),
        # Gegenprobe auf der Zielseite - siehe app/gratischeck.py.
        "check_status": deal.check_status,
        "check_label": GRATIS_LABEL.get(deal.check_status or "") or None,
        "check_text": deal.check_text, "check_preis_eur": deal.check_preis_eur,
        "check_am": deal.check_am,
        "gratis_hinweis": deal.gratis_hinweis,
        "verlauf": punkte,
        "tiefstpreis": min(preise_eur) if preise_eur else None,
        "hoechstpreis": max(preise_eur) if preise_eur else None,
        # Bestes Angebot: darauf bezieht sich der grosse Preis oben.
        "beste_quelle": angebote[0].quelle if angebote else deal.quelle,
        "beste_url": angebote[0].url if angebote else deal.url,
        "regeltreffer": [{"regel": r[0], "wann": r[1]} for r in regeln],
        "angebote": [{
            "quelle": a.quelle, "url": a.url, "preis": a.preis,
            "waehrung": a.waehrung, "preis_eur": a.preis_eur,
            "originalpreis": a.originalpreis, "rabatt_prozent": a.rabatt_prozent,
            "haendler": a.haendler, "ist_gratis": a.ist_gratis,
            "zuletzt_gesehen": a.zuletzt_gesehen,
        } for a in angebote],
    }


class AlarmBody(BaseModel):
    ziel_preis: float | None = Field(None, ge=0)
    notiz: str | None = None


@router.put("/deals/{deal_id}/alarm")
def set_alarm(deal_id: int, body: AlarmBody, db: Session = Depends(get_db)) -> dict:
    """Preisalarm setzen oder (mit ziel_preis=null) wieder entfernen."""
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")
    deal.alarm_preis = body.ziel_preis
    deal.alarm_ausgeloest = None      # neuer Alarm darf wieder ausloesen
    if body.notiz is not None:
        deal.notiz = body.notiz or None
    db.commit()
    return {"id": deal.id, "alarm_preis": deal.alarm_preis, "notiz": deal.notiz}


# --- Export / Import -------------------------------------------------------

@router.get("/deals/export.csv")
def export_csv(nur_gratis: bool = False, nur_gemerkt: bool = False,
               limit: int = Query(5000, le=50000),
               db: Session = Depends(get_db)) -> StreamingResponse:
    # 18+ bleibt auch aus dem Export draussen - eine CSV wird weitergereicht.
    stmt = (select(Deal).where(Deal.erwachsen.is_(False))
            .order_by(desc(Deal.first_seen)).limit(limit))
    if nur_gratis:
        stmt = stmt.where(Deal.ist_gratis.is_(True))
    if nur_gemerkt:
        stmt = stmt.where(Deal.bookmarked.is_(True))

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")     # Semikolon: Excel-DE-freundlich
    writer.writerow(["Titel", "Preis", "Waehrung", "Preis EUR", "Originalpreis",
                     "Rabatt %", "Gratis", "Haendler", "Quelle", "Temperatur",
                     "Gefunden am", "URL"])
    for deal in db.scalars(stmt):
        writer.writerow([
            deal.titel, deal.preis if deal.preis is not None else "", deal.waehrung,
            deal.preis_eur if deal.preis_eur is not None else "",
            deal.originalpreis if deal.originalpreis is not None else "",
            round(deal.rabatt_prozent) if deal.rabatt_prozent else "",
            "ja" if deal.ist_gratis else "nein", deal.haendler or "", deal.quelle,
            round(deal.temperatur) if deal.temperatur else "",
            deal.first_seen.strftime("%Y-%m-%d %H:%M") if deal.first_seen else "",
            deal.url,
        ])
    buffer.seek(0)
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8-sig")]),   # BOM fuer Excel
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sparbit-{stamp}.csv"'},
    )


# --- Sparbilanz ------------------------------------------------------------

@router.get("/bilanz")
def bilanz(tage: int = Query(365, ge=7, le=3650),
           db: Session = Depends(get_db)) -> dict:
    """Was das Ganze gebracht hat.

    Die Daten dafuer liegen seit dem ersten Tag da - beantwortet hat die
    Frage nur nie jemand.
    """
    from ..bilanz import berechne
    return berechne(db, tage)


# --- Kalender --------------------------------------------------------------

kalender_router = APIRouter(prefix="/api", tags=["kalender"])


@kalender_router.get("/kalender.ics")
def kalender(token: str = Query(..., min_length=10),
             nur_gratis: bool = False,
             db: Session = Depends(get_db)) -> Response:
    """Fristen als abonnierbarer Kalender.

    Das Token steht in der Adresse und nicht im Header, weil eine
    Kalender-App keinen mitschicken kann - sie holt die Datei stumpf per
    GET. Darum ein API-Token, das sich einzeln zurueckziehen laesst,
    statt des Sitzungs-Cookies.
    """
    from ..kalender import feed
    from ..tokens import pruefe as pruefe_token

    if pruefe_token(db, token) is None:
        raise HTTPException(401, "Token ungültig oder zurückgezogen")
    return Response(content=feed(db, nur_gratis),
                    media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition":
                             'inline; filename="sparbit.ics"'})


# --- Gespeicherte Suchen ---------------------------------------------------

class SavedSearchBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    filter: dict = {}


@router.get("/searches")
def list_searches(db: Session = Depends(get_db),
                  user: User = Depends(current_user)) -> list[dict]:
    stmt = nur_meine(select(SavedSearch), SavedSearch, user).order_by(SavedSearch.id)
    return [{"id": s.id, "name": s.name, "filter": s.filter}
            for s in db.scalars(stmt)]


@router.post("/searches")
def create_search(body: SavedSearchBody, db: Session = Depends(get_db),
                  user: User = Depends(darf_schreiben)) -> dict:
    row = SavedSearch(name=body.name, filter=body.filter, benutzer_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "filter": row.filter}


@router.delete("/searches/{search_id}")
def delete_search(search_id: int, db: Session = Depends(get_db),
                  user: User = Depends(darf_schreiben)) -> dict:
    row = db.get(SavedSearch, search_id)
    if row is None or not gehoert_mir(row, user):
        raise HTTPException(404, "Suche nicht gefunden")
    db.delete(row)
    db.commit()
    return {"ok": True}


# --- Allgemeine Einstellungen ---------------------------------------------

class GeneralSettings(BaseModel):
    """Alle Felder optional - was nicht mitkommt, bleibt stehen.

    Vorher hatte jedes Feld einen Default, und PUT schrieb sie alle. Wer
    im Kanal-Bereich einen Waehrungskurs speicherte, setzte damit
    unbemerkt die Preisfehler-Schwelle auf 70 zurueck: die Seite schickte
    nur zwei Felder, der Rest kam aus den Defaults. Ein Teil-Update kann
    das nicht passieren.
    """
    waehrungskurse: dict[str, float] | None = None
    benachrichtigungen_pausiert: bool | None = None
    # Der Preisfehler-Waechter meldet unabhaengig von Regeln und Ruhezeit.
    # Abschaltbar, weil "weckt dich nachts" eine Entscheidung ist, die man
    # selbst treffen sollte.
    preisfehler_waechter: bool | None = None
    preisfehler_schwelle: int | None = None
    # Taegliche Sicherung ins Datenverzeichnis. Ein Passwort verschluesselt
    # sie - sie enthaelt Bot-Token und Passwort-Hashes.
    backup_taeglich: bool | None = None
    backup_behalten: int | None = None
    backup_passwort: str | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict:
    return {
        "waehrungskurse": get_setting(db, "currency_rates") or DEFAULT_RATES,
        "aktive_kurse": get_rates(),
        "benachrichtigungen_pausiert": bool(get_setting(db, "notifications_paused")),
        "preisfehler_waechter": bool(get_setting(db, "preisfehler_waechter", True)),
        "preisfehler_schwelle": int(get_setting(db, "preisfehler_schwelle",
                                                SCHWELLE_HEISS)),
        "backup_taeglich": bool(get_setting(db, "backup_taeglich", True)),
        "backup_behalten": int(get_setting(db, "backup_behalten", 7) or 7),
        # Das Passwort selbst geht nie wieder raus - nur ob eines gesetzt ist.
        "backup_passwort_gesetzt": bool(get_setting(db, "backup_passwort")),
    }


@router.put("/settings")
def put_settings(body: GeneralSettings, db: Session = Depends(get_db)) -> dict:
    if body.waehrungskurse is not None:
        set_setting(db, "currency_rates", body.waehrungskurse)
        set_rates(body.waehrungskurse)
    if body.benachrichtigungen_pausiert is not None:
        set_setting(db, "notifications_paused", body.benachrichtigungen_pausiert)
    if body.preisfehler_waechter is not None:
        set_setting(db, "preisfehler_waechter", body.preisfehler_waechter)
    if body.preisfehler_schwelle is not None:
        set_setting(db, "preisfehler_schwelle",
                    max(30, min(100, int(body.preisfehler_schwelle))))
    if body.backup_taeglich is not None:
        set_setting(db, "backup_taeglich", body.backup_taeglich)
    if body.backup_behalten is not None:
        set_setting(db, "backup_behalten", max(1, min(90, int(body.backup_behalten))))
    # "-" loescht das Passwort, leer laesst es stehen: sonst wuerde jedes
    # Speichern anderer Einstellungen die Verschluesselung abschalten.
    if body.backup_passwort:
        set_setting(db, "backup_passwort",
                    "" if body.backup_passwort == "-" else body.backup_passwort)
    db.commit()
    return get_settings(db)


@router.get("/bilder-status")
def bilder_status(db: Session = Depends(get_db)) -> dict:
    return {**bild_statistik(db),
            "aktiv": get_setting(db, "bilder_lokal", True)}


@router.post("/bilder-aufraeumen")
def bilder_putzen(db: Session = Depends(get_db)) -> dict:
    return {"entfernt": bilder_aufraeumen(db)}


@router.post("/sources/{source_id}/snooze")
def snooze_source(source_id: str, stunden: float = Query(6, ge=0, le=168),
                  db: Session = Depends(get_db)) -> dict:
    cfg = db.get(SourceConfig, source_id)
    if cfg is None:
        raise HTTPException(404, "Quelle unbekannt")
    cfg.snooze_until = (utcnow() + timedelta(hours=stunden)) if stunden else None
    db.commit()
    return {"id": source_id, "snooze_until": cfg.snooze_until}


# --- Preisfehler -----------------------------------------------------------

@router.get("/preisfehler")
def preisfehler_liste(tage: int = Query(7, ge=1, le=90),
                      nur_heiss: bool = False,
                      limit: int = Query(60, le=200),
                      db: Session = Depends(get_db)) -> dict:
    """Die aktuellen Preisfehler-Funde, nach Punktzahl sortiert.

    Nicht nach Datum: bei Preisfehlern ist die Ueberzeugungskraft
    interessanter als das Alter. Ein Fund von gestern mit 95 Punkten gehoert
    ueber einen von heute Morgen mit 48.
    """
    stufen = [PF_HEISS] if nur_heiss else [PF_HEISS, PF_VERDACHT]
    seit = utcnow() - timedelta(days=tage)
    rows = list(db.scalars(
        select(Deal)
        .where(Deal.fehler_stufe.in_(stufen), Deal.last_seen >= seit,
               Deal.erwachsen.is_(False))
        .order_by(desc(Deal.fehler_score), desc(Deal.first_seen))
        .limit(limit)))

    return {
        "schwelle": int(get_setting(db, "preisfehler_schwelle", SCHWELLE_HEISS)),
        "waechter_aktiv": bool(get_setting(db, "preisfehler_waechter", True)),
        "items": [{
            "id": d.id, "titel": d.titel, "url": d.url, "bild": d.bild,
            "bild_lokal": d.bild_lokal, "preis": d.preis,
            "preis_eur": d.preis_eur, "originalpreis": d.originalpreis,
            "rabatt_prozent": d.rabatt_prozent, "waehrung": d.waehrung,
            "ist_gratis": d.ist_gratis, "haendler": d.haendler,
            "quelle": d.quelle, "temperatur": d.temperatur,
            "first_seen": d.first_seen, "last_seen": d.last_seen,
            "bookmarked": d.bookmarked, "tags": d.tags or [],
            "also_from": d.also_from or [],
            "anzahl_angebote": 1 + len(d.also_from or []),
            "urteil": d.urteil, "urteil_text": d.urteil_text,
            "fehler_score": d.fehler_score or 0,
            "fehler_stufe": d.fehler_stufe,
            "fehler_gruende": d.fehler_gruende or [],
            "fehler_erwartet_eur": d.fehler_erwartet_eur,
            "fehler_gemeldet_am": d.fehler_gemeldet_am,
            "fehler_indizien": d.fehler_indizien or [],
            "urteil_mensch": d.fehler_urteil_mensch,
        } for d in rows],
    }


class Rueckmeldung(BaseModel):
    urteil: str          # "echt" | "fehlalarm"


@router.post("/preisfehler/{deal_id}/rueckmeldung")
def preisfehler_rueckmeldung(deal_id: int, body: Rueckmeldung,
                             db: Session = Depends(get_db)) -> dict:
    """War das wirklich ein Preisfehler? Nochmal drücken nimmt es zurück."""
    from ..pricefehler import notiere_rueckmeldung

    try:
        deal = notiere_rueckmeldung(db, deal_id, body.urteil)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")
    return {"ok": True, "urteil_mensch": deal.fehler_urteil_mensch}


@router.get("/hygiene")
def hygiene(db: Session = Depends(get_db)) -> dict:
    """Regeln und Quellen, die Aufmerksamkeit verdienen.

    Vorgeschlagen, nie ausgeführt: eine Regel abzuschalten, die jemand
    absichtlich weit gefasst hat, wäre schlimmer als der Hinweis nützt.
    """
    from .. import hygiene as modul

    befunde = modul.pruefe(db)
    return {"fenster_tage": modul.FENSTER_TAGE,
            "befunde": modul.als_dict(befunde)}


@router.get("/preisfehler/auswertung")
def preisfehler_auswertung(db: Session = Depends(get_db)) -> dict:
    """Welches Indiz lag wie oft richtig - und was folgt daraus.

    Die Gewichte des Wächters sind begründet, aber am Schreibtisch
    gewählt. Erst die Rückmeldungen sagen, welche Indizien mit diesen
    Quellen tatsächlich taugen.
    """
    from ..pricefehler import bewerte_rueckmeldungen

    return bewerte_rueckmeldungen(db)


@router.post("/preisfehler/schwelle-uebernehmen")
def schwelle_uebernehmen(db: Session = Depends(get_db)) -> dict:
    """Den Vorschlag der Eichung uebernehmen.

    Die Auswertung schlug bisher vor und blieb dabei - verstellen musste
    man selbst, an einer anderen Stelle, mit dem Wert im Kopf. Ein Knopf
    daneben ist dasselbe in einem Schritt, und weil er den alten Wert
    zurueckgibt, bleibt der Weg zurueck offen.
    """
    from ..pricefehler import bewerte_rueckmeldungen

    auswertung = bewerte_rueckmeldungen(db)
    vorschlag = auswertung.get("vorschlag")
    if not vorschlag:
        raise HTTPException(409, auswertung.get("vorschlag_grund")
                            or "Es gibt gerade nichts zu übernehmen.")

    vorher = int(get_setting(db, "preisfehler_schwelle", SCHWELLE_HEISS)
                 or SCHWELLE_HEISS)
    set_setting(db, "preisfehler_schwelle", int(vorschlag))
    db.commit()
    log.info("Preisfehler-Schwelle von %d auf %d gesetzt (Eichung)",
             vorher, vorschlag)
    return {"ok": True, "vorher": vorher, "jetzt": int(vorschlag),
            "grund": auswertung.get("vorschlag_grund")}


@router.post("/preisfehler/{deal_id}/pruefen")
def preisfehler_neu_pruefen(deal_id: int, db: Session = Depends(get_db)) -> dict:
    """Einen Deal von Hand neu bewerten.

    Nuetzlich nach dem Nachtragen von Waehrungskursen oder wenn seit dem
    letzten Lauf weitere Quellen denselben Artikel gemeldet haben.
    """
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")
    urteil = bewerte_deal(db, deal)
    deal.fehler_score = urteil.punkte
    deal.fehler_stufe = urteil.stufe
    deal.fehler_gruende = urteil.gruende
    deal.fehler_erwartet_eur = urteil.erwartet_eur
    deal.fehler_am = utcnow()
    db.commit()
    return urteil.as_dict()


@router.post("/preisfehler/{deal_id}/verwerfen")
def preisfehler_verwerfen(deal_id: int, db: Session = Depends(get_db)) -> dict:
    """Fehlalarm wegklicken.

    Setzt die Meldesperre, statt die Punktzahl zu loeschen: die Begruendung
    bleibt nachvollziehbar, aber es kommt keine zweite Nachricht. Zaehlt
    zugleich als Rueckmeldung - wer hier klickt, hat das Urteil ja gefaellt,
    und daraus soll der Waechter lernen.
    """
    from ..pricefehler import FEHLALARM

    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")
    deal.fehler_stufe = "kein"
    deal.fehler_gemeldet_am = utcnow()
    if deal.fehler_urteil_mensch is None:
        deal.fehler_urteil_mensch = FEHLALARM
        deal.fehler_urteil_am = utcnow()
    db.commit()
    return {"ok": True, "id": deal.id}
