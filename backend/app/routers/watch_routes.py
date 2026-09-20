"""Wunschliste, Preisurteil, lernender Feed und Token-Verwaltung."""
from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..learning import notiere, trainiere, vorschlaege
from ..models import ApiToken, Deal, WatchItem, WatchPrice, utcnow
from ..pricewatch import NichtGefunden, preis_aus_seite, pruefe as pruefe_eintrag
from ..scheduler import get_http
from ..tokens import erzeuge, pruefe as pruefe_token, token_aus_header
from ..verdict import LABEL, RANGFOLGE, bewerte_deal

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["watch"],
                   dependencies=[Depends(current_user)])


# --- Wunschliste -----------------------------------------------------------

class WatchBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=8, max_length=2000)
    ziel_preis: float | None = Field(None, ge=0)
    intervall_minuten: int = Field(180, ge=30, le=10080)
    aktiv: bool = True


def _watch_dict(eintrag: WatchItem, verlauf: list | None = None) -> dict:
    return {
        "id": eintrag.id, "name": eintrag.name, "url": eintrag.url,
        "ziel_preis": eintrag.ziel_preis, "aktiv": eintrag.aktiv,
        "intervall_minuten": eintrag.intervall_minuten,
        "letzter_preis": eintrag.letzter_preis, "waehrung": eintrag.waehrung,
        "bester_preis": eintrag.bester_preis, "bild": eintrag.bild,
        "haendler": eintrag.haendler, "letzter_lauf": eintrag.letzter_lauf,
        "letzter_erfolg": eintrag.letzter_erfolg,
        "letzter_fehler": eintrag.letzter_fehler,
        "fehler_in_folge": eintrag.fehler_in_folge,
        "erstellt_am": eintrag.erstellt_am,
        "ziel_erreicht": bool(eintrag.ziel_preis is not None
                              and eintrag.letzter_preis is not None
                              and eintrag.letzter_preis <= eintrag.ziel_preis),
        "verlauf": verlauf if verlauf is not None else [],
    }


@router.get("/watch")
def liste(db: Session = Depends(get_db)) -> list[dict]:
    return [_watch_dict(e) for e in db.scalars(
        select(WatchItem).order_by(desc(WatchItem.erstellt_am)))]


@router.get("/watch/{watch_id}")
def einzeln(watch_id: int, db: Session = Depends(get_db)) -> dict:
    eintrag = db.get(WatchItem, watch_id)
    if eintrag is None:
        raise HTTPException(404, "Nicht gefunden")
    verlauf = db.scalars(select(WatchPrice).where(WatchPrice.watch_id == watch_id)
                         .order_by(WatchPrice.ts.asc()).limit(200))
    return _watch_dict(eintrag, [{"ts": p.ts, "preis": p.preis,
                                  "waehrung": p.waehrung} for p in verlauf])


@router.post("/watch")
async def anlegen(body: WatchBody, db: Session = Depends(get_db)) -> dict:
    """Artikel aufnehmen und gleich einmal abfragen.

    Der erste Abruf passiert sofort und synchron: so erfaehrt man auf der
    Stelle, ob die Seite ueberhaupt lesbar ist, statt es erst in drei
    Stunden zu merken.
    """
    eintrag = WatchItem(**body.model_dump())
    db.add(eintrag)
    db.commit()
    db.refresh(eintrag)

    fund = await pruefe_eintrag(db, eintrag, get_http())
    db.refresh(eintrag)
    ergebnis = _watch_dict(eintrag)
    ergebnis["erster_abruf"] = (
        {"ok": True, "preis": fund.preis, "waehrung": fund.waehrung,
         "verfahren": fund.quelle} if fund else
        {"ok": False, "fehler": eintrag.letzter_fehler})
    return ergebnis


class SammelBody(BaseModel):
    urls: str = Field(max_length=20000)
    ziel_preis: float | None = Field(None, ge=0)
    intervall_minuten: int = Field(180, ge=30, le=10080)


# Mehr als das auf einmal hiesse, den Server fuer Minuten zu blockieren -
# jede Seite wird ja einzeln geholt.
SAMMEL_MAX = 25


@router.post("/watch/sammel")
async def sammel_anlegen(body: SammelBody,
                         db: Session = Depends(get_db)) -> dict:
    """Mehrere Artikel auf einmal aufnehmen - eine URL je Zeile.

    Namen und Preise werden gleich geholt, damit man sofort sieht, was
    gelesen werden konnte. Was scheitert, wird trotzdem aufgenommen und
    beim naechsten Lauf erneut versucht - haeufig ist es nur eine Seite,
    die beim ersten Mal zickt.
    """
    roh = [z.strip() for z in body.urls.splitlines()]
    kandidaten: list[str] = []
    for zeile in roh:
        if not zeile or not zeile.lower().startswith(("http://", "https://")):
            continue
        if zeile not in kandidaten:
            kandidaten.append(zeile)

    if not kandidaten:
        raise HTTPException(400, "Keine gültige URL gefunden — eine pro Zeile, "
                                 "beginnend mit http:// oder https://")
    if len(kandidaten) > SAMMEL_MAX:
        raise HTTPException(400, f"Höchstens {SAMMEL_MAX} auf einmal — "
                                 f"{len(kandidaten)} waren es.")

    vorhanden = {e.url for e in db.scalars(select(WatchItem))}
    http = get_http()
    angelegt, uebersprungen, fehler = [], [], []

    for url in kandidaten:
        if url in vorhanden:
            uebersprungen.append({"url": url, "grund": "steht schon drin"})
            continue

        # Vorlaeufiger Name aus der URL - der erste Abruf ersetzt ihn, wenn
        # die Seite einen hergibt.
        eintrag = WatchItem(name=_name_aus_url(url), url=url,
                            ziel_preis=body.ziel_preis,
                            intervall_minuten=body.intervall_minuten, aktiv=True)
        db.add(eintrag)
        db.commit()
        db.refresh(eintrag)
        vorhanden.add(url)

        try:
            fund = await pruefe_eintrag(db, eintrag, http)
        except Exception as exc:                      # eine Seite darf nicht alles abbrechen
            log.warning("Sammelimport: %s: %s", url, exc)
            fund = None
        db.refresh(eintrag)

        if fund:
            angelegt.append(_watch_dict(eintrag))
        else:
            fehler.append({"url": url, "id": eintrag.id,
                           "name": eintrag.name,
                           "grund": eintrag.letzter_fehler or "kein Preis gefunden"})

    return {"angelegt": angelegt, "uebersprungen": uebersprungen,
            "fehler": fehler,
            "zusammenfassung": {
                "gelesen": len(kandidaten), "neu": len(angelegt) + len(fehler),
                "mit_preis": len(angelegt), "ohne_preis": len(fehler),
                "doppelt": len(uebersprungen)}}


def _name_aus_url(url: str) -> str:
    """Ein brauchbarer Platzhalter, bis die Seite einen echten Namen liefert."""
    from urllib.parse import unquote, urlparse

    pfad = urlparse(url).path.rstrip("/")
    letzter = unquote(pfad.rsplit("/", 1)[-1]) if pfad else ""
    # Endung und Trennzeichen weg: "lego-technic-42143.html" -> "lego technic 42143"
    letzter = letzter.rsplit(".", 1)[0] if "." in letzter[-6:] else letzter
    lesbar = " ".join(w for w in letzter.replace("-", " ").replace("_", " ").split()
                      if w)
    if len(lesbar) >= 3:
        return lesbar[:255]
    return (urlparse(url).netloc or url)[:255]


@router.put("/watch/{watch_id}")
def aendern(watch_id: int, body: WatchBody, db: Session = Depends(get_db)) -> dict:
    eintrag = db.get(WatchItem, watch_id)
    if eintrag is None:
        raise HTTPException(404, "Nicht gefunden")
    for schluessel, wert in body.model_dump().items():
        setattr(eintrag, schluessel, wert)
    if eintrag.aktiv:
        eintrag.fehler_in_folge = 0
    db.commit()
    return _watch_dict(eintrag)


@router.delete("/watch/{watch_id}")
def loeschen(watch_id: int, db: Session = Depends(get_db)) -> dict:
    eintrag = db.get(WatchItem, watch_id)
    if eintrag is None:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(eintrag)
    db.commit()
    return {"ok": True}


@router.post("/watch/{watch_id}/pruefen")
async def jetzt_pruefen(watch_id: int, db: Session = Depends(get_db)) -> dict:
    eintrag = db.get(WatchItem, watch_id)
    if eintrag is None:
        raise HTTPException(404, "Nicht gefunden")
    fund = await pruefe_eintrag(db, eintrag, get_http())
    db.refresh(eintrag)
    if fund is None:
        return {"ok": False, "fehler": eintrag.letzter_fehler}
    return {"ok": True, "preis": fund.preis, "waehrung": fund.waehrung,
            "verfahren": fund.quelle, "name": fund.name}


class PruefBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@router.post("/watch-test")
async def testen(body: PruefBody) -> dict:
    """URL pruefen, ohne sie aufzunehmen - fuer das Anlege-Formular."""
    try:
        antwort = await get_http().get(body.url)
        fund = preis_aus_seite(antwort.text)
    except NichtGefunden as exc:
        return {"ok": False, "fehler": str(exc)}
    except Exception as exc:
        return {"ok": False, "fehler": f"{type(exc).__name__}: {exc}"[:300]}
    return {"ok": True, "preis": fund.preis, "waehrung": fund.waehrung,
            "name": fund.name, "bild": fund.bild, "verfahren": fund.quelle}


# --- Preisurteil -----------------------------------------------------------

@router.get("/urteile")
def urteil_stufen() -> list[dict]:
    return [{"stufe": stufe, "label": LABEL[stufe]} for stufe in RANGFOLGE]


@router.post("/deals/{deal_id}/urteil")
def urteil_neu(deal_id: int, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, "Deal nicht gefunden")
    urteil = bewerte_deal(db, deal)
    deal.urteil, deal.urteil_text, deal.urteil_am = (
        urteil.stufe, urteil.text, utcnow())
    db.commit()
    return {"stufe": urteil.stufe, "label": urteil.label, "text": urteil.text,
            "punkte": urteil.punkte, "tiefst": urteil.tiefst,
            "median": urteil.median}


# --- Lernender Feed --------------------------------------------------------

class InteraktionBody(BaseModel):
    art: str


@router.post("/deals/{deal_id}/interaktion")
def interaktion(deal_id: int, body: InteraktionBody,
                db: Session = Depends(get_db)) -> dict:
    notiere(db, deal_id, body.art)
    return {"ok": True}


@router.get("/empfehlungen/status")
def lern_status(db: Session = Depends(get_db)) -> dict:
    modell = trainiere(db)
    return {
        "bereit": modell.bereit,
        "positiv": round(modell.n_positiv, 1),
        "negativ": round(modell.n_negativ, 1),
        "hinweis": ("Genug gelernt — der Feed kann nach Interesse sortieren."
                    if modell.bereit else
                    "Noch zu wenig Signal. Merk dir ein paar Deals oder setz "
                    "Preisalarme, dann lernt SparBit daraus."),
    }


@router.get("/empfehlungen/regeln")
def regel_vorschlaege(db: Session = Depends(get_db)) -> list[dict]:
    return [asdict(v) for v in vorschlaege(db)]


# --- Token fuer die Erweiterung -------------------------------------------

class TokenBody(BaseModel):
    name: str = Field("Browser-Erweiterung", max_length=128)


@router.get("/tokens")
def token_liste(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": t.id, "name": t.name, "praefix": t.praefix,
             "erstellt_am": t.erstellt_am, "zuletzt_genutzt": t.zuletzt_genutzt}
            for t in db.scalars(select(ApiToken).order_by(ApiToken.id))]


@router.post("/tokens")
def token_anlegen(body: TokenBody, db: Session = Depends(get_db)) -> dict:
    zeile, klartext = erzeuge(db, body.name)
    # Der Klartext ist genau hier einmal zu sehen - danach nur noch der Hash.
    return {"id": zeile.id, "name": zeile.name, "token": klartext,
            "hinweis": "Jetzt kopieren — dieser Schlüssel wird nie wieder angezeigt."}


@router.delete("/tokens/{token_id}")
def token_loeschen(token_id: int, db: Session = Depends(get_db)) -> dict:
    zeile = db.get(ApiToken, token_id)
    if zeile is None:
        raise HTTPException(404, "Token nicht gefunden")
    db.delete(zeile)
    db.commit()
    return {"ok": True}


# --- Schnittstelle fuer die Erweiterung -----------------------------------
# Eigener Router ohne Sitzungs-Cookie: die Erweiterung laeuft auf fremden
# Seiten und weist sich per Bearer-Token aus.

extern_router = APIRouter(prefix="/api/extern", tags=["extern"])


def token_benutzer(db: Session = Depends(get_db),
                   token: str = Depends(token_aus_header)) -> ApiToken:
    zeile = pruefe_token(db, token)
    if zeile is None:
        raise HTTPException(401, "Token ungültig oder zurückgezogen")
    return zeile


class ExternWatchBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=8, max_length=2000)
    ziel_preis: float | None = Field(None, ge=0)
    bild: str | None = None


@extern_router.get("/ping")
def ping(_: ApiToken = Depends(token_benutzer)) -> dict:
    return {"ok": True, "app": "SparBit"}


@extern_router.post("/watch")
async def extern_aufnehmen(body: ExternWatchBody,
                           db: Session = Depends(get_db),
                           _: ApiToken = Depends(token_benutzer)) -> dict:
    """Artikel aus der Browser-Erweiterung aufnehmen."""
    vorhanden = db.scalar(select(WatchItem).where(WatchItem.url == body.url))
    if vorhanden is not None:
        return {"ok": True, "bereits_vorhanden": True, "id": vorhanden.id,
                "letzter_preis": vorhanden.letzter_preis}

    eintrag = WatchItem(name=body.name, url=body.url, ziel_preis=body.ziel_preis,
                        bild=body.bild)
    db.add(eintrag)
    db.commit()
    db.refresh(eintrag)
    fund = await pruefe_eintrag(db, eintrag, get_http())
    db.refresh(eintrag)
    return {"ok": True, "id": eintrag.id, "bereits_vorhanden": False,
            "preis": fund.preis if fund else None,
            "fehler": eintrag.letzter_fehler}


@extern_router.get("/kennt")
async def kennt_sparbit(url: str = Query(..., max_length=2000),
                        titel: str = Query("", max_length=300),
                        db: Session = Depends(get_db),
                        _: ApiToken = Depends(token_benutzer)) -> dict:
    """Kennt SparBit diesen Artikel schon - und günstiger?

    Damit kann die Erweiterung auf der Shop-Seite anzeigen, dass es den
    Artikel woanders billiger gibt.
    """
    from ..dedupe import titles_match, url_hash

    treffer = db.scalar(select(Deal).where(Deal.url_hash == url_hash(url)))
    if treffer is None and titel:
        # Die Titelsuche bleibt im normalen Bestand: eine Wunschliste ist
        # kein Eingang fuer den 18+-Bereich. Der exakte URL-Treffer oben
        # bleibt davon unberuehrt - den hat man selbst eingetragen.
        for kandidat in db.scalars(select(Deal)
                                   .where(Deal.erwachsen.is_(False))
                                   .order_by(desc(Deal.first_seen))
                                   .limit(400)):
            if titles_match(titel, kandidat.titel):
                treffer = kandidat
                break

    beobachtet = db.scalar(select(WatchItem).where(WatchItem.url == url))
    if treffer is None:
        return {"bekannt": False, "beobachtet": beobachtet is not None,
                "watch_id": beobachtet.id if beobachtet else None}

    return {
        "bekannt": True, "deal_id": treffer.id, "titel": treffer.titel,
        "preis": treffer.preis, "waehrung": treffer.waehrung,
        "preis_eur": treffer.preis_eur, "quelle": treffer.quelle,
        "urteil": treffer.urteil, "urteil_text": treffer.urteil_text,
        "beobachtet": beobachtet is not None,
        "watch_id": beobachtet.id if beobachtet else None,
    }
