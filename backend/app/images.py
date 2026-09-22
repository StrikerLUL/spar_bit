"""Lokaler Bild-Cache.

Ohne ihn laedt jede Deal-Karte das Bild direkt bei Amazon, mydealz und Co. -
die sehen dann bei jedem Oeffnen des Feeds deine IP und wissen, welche Deals
du dir ansiehst. Ausserdem bleiben tote Bild-URLs dauerhaft tot.

SparBit holt Bilder darum einmal beim Einsammeln, legt sie unter
<data>/images ab und liefert sie selbst aus. Ist Pillow installiert, werden
sie vorher verkleinert; sonst werden sie unveraendert gespeichert - das
Verhalten bleibt gleich, nur die Datei ist groesser.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import CachedImage, Deal, utcnow

log = logging.getLogger(__name__)

MAX_BYTES = 3 * 1024 * 1024          # groesser holen wir gar nicht erst
MAX_KANTE = 640                      # Karten zeigen hoechstens ~400px breit
ERLAUBTE_TYPEN = {"image/jpeg", "image/png", "image/webp", "image/gif"}
GLEICHZEITIG = 4                     # Hoeflichkeit gegenueber den Bildservern

try:
    from PIL import Image  # type: ignore
    PILLOW = True
except ImportError:                  # pragma: no cover - haengt von der Umgebung ab
    PILLOW = False


def bild_verzeichnis() -> Path:
    pfad = settings.data_dir / "images"
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def url_schluessel(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _endung(content_type: str | None) -> str:
    return {"image/jpeg": ".jpg", "image/png": ".png",
            "image/webp": ".webp", "image/gif": ".gif"}.get(content_type or "", ".img")


def _verkleinern(rohdaten: bytes, ziel: Path) -> tuple[bool, int]:
    """Bild verkleinern und speichern. Gibt (verkleinert, bytes) zurueck."""
    if not PILLOW:
        ziel.write_bytes(rohdaten)
        return False, len(rohdaten)
    try:
        import io
        with Image.open(io.BytesIO(rohdaten)) as bild:
            bild.load()
            if max(bild.size) <= MAX_KANTE and bild.format in ("JPEG", "WEBP"):
                ziel.write_bytes(rohdaten)      # schon klein genug
                return False, len(rohdaten)
            bild.thumbnail((MAX_KANTE, MAX_KANTE))
            if bild.mode in ("P", "RGBA", "LA"):
                hintergrund = Image.new("RGB", bild.size, (17, 19, 24))
                hintergrund.paste(bild, mask=bild.split()[-1]
                                  if bild.mode in ("RGBA", "LA") else None)
                bild = hintergrund
            elif bild.mode != "RGB":
                bild = bild.convert("RGB")
            bild.save(ziel, "JPEG", quality=82, optimize=True)
        return True, ziel.stat().st_size
    except Exception as exc:
        # Kaputtes oder exotisches Bild - lieber im Original behalten.
        log.debug("Bild konnte nicht verkleinert werden (%s), speichere original", exc)
        ziel.write_bytes(rohdaten)
        return False, len(rohdaten)


async def hole_bild(db: Session, url: str, http) -> str | None:
    """Ein Bild holen und ablegen. Gibt den Dateinamen zurueck, oder None.

    Fehler sind hier bewusst harmlos: ein fehlendes Bild darf niemals einen
    Deal verhindern.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None

    schluessel = url_schluessel(url)
    bekannt = db.scalar(select(CachedImage).where(CachedImage.url_hash == schluessel))
    if bekannt is not None:
        # Auch ein frueherer Fehlschlag zaehlt: nicht bei jedem Lauf erneut versuchen.
        if bekannt.ok and bekannt.datei and (bild_verzeichnis() / bekannt.datei).exists():
            return bekannt.datei
        if not bekannt.ok:
            return None

    eintrag = bekannt or CachedImage(url_hash=schluessel, quell_url=url[:2000])
    try:
        antwort = await http.get(url)
        content_type = (antwort.headers.get("content-type") or "").split(";")[0].strip()
        rohdaten = antwort.content

        if content_type not in ERLAUBTE_TYPEN:
            raise ValueError(f"unerwarteter Typ '{content_type or 'unbekannt'}'")
        if len(rohdaten) > MAX_BYTES:
            raise ValueError(f"{len(rohdaten) // 1024} KB ueberschreiten das Limit")

        datei = schluessel + (".jpg" if PILLOW else _endung(content_type))
        _, groesse = _verkleinern(rohdaten, bild_verzeichnis() / datei)

        eintrag.datei = datei
        eintrag.content_type = "image/jpeg" if PILLOW else content_type
        eintrag.bytes = groesse
        eintrag.ok = True
        eintrag.fehler = None
    except Exception as exc:
        eintrag.ok = False
        eintrag.datei = None
        eintrag.fehler = f"{type(exc).__name__}: {exc}"[:300]
        log.debug("Bild %s nicht geholt: %s", url[:80], eintrag.fehler)

    eintrag.geholt_am = utcnow()
    if bekannt is None:
        db.add(eintrag)
    db.commit()
    return eintrag.datei if eintrag.ok else None


async def hole_fuer_deals(db: Session, deals: list[Deal], http) -> int:
    """Bilder frisch eingesammelter Deals nachladen - mehrere parallel,
    aber gedeckelt, damit wir keinen Bildserver ueberrennen."""
    offen = [d for d in deals if d.bild and not d.bild_lokal]
    if not offen:
        return 0

    semaphor = asyncio.Semaphore(GLEICHZEITIG)

    async def einer(deal: Deal) -> tuple[int, str | None]:
        async with semaphor:
            return deal.id, await hole_bild(db, deal.bild, http)

    ergebnisse = await asyncio.gather(*(einer(d) for d in offen),
                                      return_exceptions=True)
    geholt = 0
    for ergebnis in ergebnisse:
        if isinstance(ergebnis, BaseException):
            continue
        deal_id, datei = ergebnis
        if datei:
            deal = db.get(Deal, deal_id)
            if deal is not None:
                deal.bild_lokal = datei
                geholt += 1
    if geholt:
        db.commit()
    return geholt


def aufraeumen(db: Session) -> int:
    """Bilder wegwerfen, auf die kein Deal mehr zeigt."""
    verzeichnis = bild_verzeichnis()
    benutzt = {row[0] for row in db.execute(
        select(Deal.bild_lokal).where(Deal.bild_lokal.isnot(None))).all()}

    entfernt = 0
    for datei in verzeichnis.iterdir():
        if datei.is_file() and datei.name not in benutzt:
            try:
                datei.unlink()
                entfernt += 1
            except OSError:
                pass

    verwaist = db.execute(
        delete(CachedImage).where(CachedImage.datei.isnot(None),
                                  CachedImage.datei.notin_(benutzt or [""])))
    if entfernt or verwaist.rowcount:
        log.info("Bild-Cache aufgeraeumt: %d Dateien entfernt", entfernt)
    return entfernt


def statistik(db: Session) -> dict:
    verzeichnis = bild_verzeichnis()
    bytes_gesamt = sum(f.stat().st_size for f in verzeichnis.iterdir() if f.is_file())
    return {
        "aktiv": True,
        "pillow": PILLOW,
        "dateien": db.scalar(select(func.count()).select_from(CachedImage)
                             .where(CachedImage.ok.is_(True))) or 0,
        "fehlgeschlagen": db.scalar(select(func.count()).select_from(CachedImage)
                                    .where(CachedImage.ok.is_(False))) or 0,
        "bytes": bytes_gesamt,
        "verzeichnis": str(verzeichnis),
    }
