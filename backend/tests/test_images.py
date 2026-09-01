"""Bild-Cache. Ohne Netzwerk - der HTTP-Client wird ersetzt."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import images
from app.models import Base, CachedImage, Deal

# Kleinstes gueltiges PNG (1x1, transparent).
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100fdff03fa0000000049454e44ae426082")


class FakeAntwort:
    def __init__(self, content: bytes, content_type: str = "image/png"):
        self.content = content
        self.headers = {"content-type": content_type}


class FakeHttp:
    """Ersetzt PoliteClient: liefert vorgegebene Antworten, zaehlt Aufrufe."""

    def __init__(self, antworten: dict):
        self.antworten = antworten
        self.aufrufe: list[str] = []

    async def get(self, url: str, **kwargs):
        self.aufrufe.append(url)
        antwort = self.antworten.get(url)
        if antwort is None:
            raise RuntimeError("404")
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(images.settings, "data_dir", tmp_path)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.mark.asyncio
async def test_bild_wird_lokal_abgelegt(db):
    http = FakeHttp({"https://cdn.de/a.png": FakeAntwort(PNG)})
    datei = await images.hole_bild(db, "https://cdn.de/a.png", http)

    assert datei is not None
    assert (images.bild_verzeichnis() / datei).is_file()
    assert db.scalar(select(CachedImage)).ok is True


@pytest.mark.asyncio
async def test_zweiter_aufruf_holt_nicht_erneut(db):
    """Sonst laedt jeder Lauf dasselbe Bild neu - genau das wollen wir
    dem Bildserver ersparen."""
    http = FakeHttp({"https://cdn.de/a.png": FakeAntwort(PNG)})
    await images.hole_bild(db, "https://cdn.de/a.png", http)
    await images.hole_bild(db, "https://cdn.de/a.png", http)
    assert len(http.aufrufe) == 1


@pytest.mark.asyncio
async def test_fehlschlag_wird_gemerkt_und_nicht_wiederholt(db):
    http = FakeHttp({})
    assert await images.hole_bild(db, "https://cdn.de/weg.png", http) is None
    assert await images.hole_bild(db, "https://cdn.de/weg.png", http) is None
    assert len(http.aufrufe) == 1
    assert db.scalar(select(CachedImage)).ok is False


@pytest.mark.asyncio
async def test_html_statt_bild_wird_abgelehnt(db):
    """Manche Server antworten mit einer Fehlerseite und Status 200."""
    http = FakeHttp({"https://cdn.de/a.png":
                     FakeAntwort(b"<html>nope</html>", "text/html")})
    assert await images.hole_bild(db, "https://cdn.de/a.png", http) is None


@pytest.mark.asyncio
async def test_zu_grosses_bild_wird_abgelehnt(db):
    riesig = b"x" * (images.MAX_BYTES + 1)
    http = FakeHttp({"https://cdn.de/gross.png": FakeAntwort(riesig)})
    assert await images.hole_bild(db, "https://cdn.de/gross.png", http) is None


@pytest.mark.asyncio
async def test_unsinnige_url_wird_uebersprungen(db):
    http = FakeHttp({})
    assert await images.hole_bild(db, "javascript:alert(1)", http) is None
    assert await images.hole_bild(db, "", http) is None
    assert http.aufrufe == []


@pytest.mark.asyncio
async def test_deals_bekommen_ihr_lokales_bild(db):
    deal = Deal(url_hash="h1", titel="Ein Deal", titel_norm="ein deal",
                url="https://x.de/1", quelle="mydealz", waehrung="EUR",
                bild="https://cdn.de/a.png", tags=[], also_from=[], roh={})
    db.add(deal)
    db.commit()

    http = FakeHttp({"https://cdn.de/a.png": FakeAntwort(PNG)})
    assert await images.hole_fuer_deals(db, [deal], http) == 1
    assert deal.bild_lokal is not None


@pytest.mark.asyncio
async def test_aufraeumen_entfernt_verwaiste_bilder(db):
    http = FakeHttp({"https://cdn.de/a.png": FakeAntwort(PNG)})
    datei = await images.hole_bild(db, "https://cdn.de/a.png", http)
    assert (images.bild_verzeichnis() / datei).exists()

    # Kein Deal zeigt darauf -> beim Aufraeumen weg.
    assert images.aufraeumen(db) == 1
    assert not (images.bild_verzeichnis() / datei).exists()


@pytest.mark.asyncio
async def test_benutzte_bilder_bleiben(db):
    http = FakeHttp({"https://cdn.de/a.png": FakeAntwort(PNG)})
    datei = await images.hole_bild(db, "https://cdn.de/a.png", http)
    db.add(Deal(url_hash="h1", titel="x", titel_norm="x", url="https://x.de/1",
                quelle="mydealz", waehrung="EUR", bild_lokal=datei,
                tags=[], also_from=[], roh={}))
    db.commit()

    assert images.aufraeumen(db) == 0
    assert (images.bild_verzeichnis() / datei).exists()
