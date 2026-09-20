"""Der ganze Weg: Quelle meldet „gratis", Zielseite verlangt Geld.

Das ist der Test zur eigentlichen Beschwerde. Die Einzelteile sind anderswo
geprueft; hier geht es darum, dass sie in der richtigen Reihenfolge
zusammenspielen - die Gegenprobe muss VOR der Regel-Auswertung laufen,
sonst hat die „nur gratis"-Regel schon zugeschlagen, wenn die Korrektur
kommt.
"""
import pytest

SEITE = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Bundle",
 "offers":{"@type":"Offer","price":"14.99","priceCurrency":"EUR",
 "availability":"https://schema.org/InStock"}}</script></head><body>x</body></html>"""

ECHT_FREI = SEITE.replace('"14.99"', '"0.00"')


class _Antwort:
    def __init__(self, text):
        self.text = text
        self.content = text.encode()
        self.status_code = 200
        self.headers = {"content-type": "text/html"}


class _Http:
    def __init__(self, seiten):
        self.seiten = seiten
        self.abgerufen = []

    async def get(self, url, **kwargs):
        self.abgerufen.append(url)
        if url not in self.seiten:
            raise RuntimeError("nicht erreichbar")
        return _Antwort(self.seiten[url])

    async def get_text(self, url, **kwargs):
        return (await self.get(url)).text


@pytest.fixture
def welt(tmp_path, monkeypatch):
    """Frische App mit einer Testquelle, die zwei Gratis-Funde meldet."""
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()

    from app.db import SessionLocal, init_db
    from app.sources.base import (Category, DealItem, Source, Verification,
                                  register)

    init_db()

    class Testquelle(Source):
        id = "testquelle"
        display_name = "Testquelle"
        category = Category.EXPERIMENTAL
        verification = Verification.UNVERIFIED
        options_schema = []

        async def fetch(self, ctx):
            return [
                DealItem(titel="Bundle angeblich geschenkt",
                         url="https://shop.test/falsch", quelle=self.id,
                         preis=0.0, ist_gratis=True),
                DealItem(titel="Spiel wirklich geschenkt",
                         url="https://shop.test/echt", quelle=self.id,
                         preis=0.0, ist_gratis=True),
            ]

    register(Testquelle())

    http = _Http({"https://shop.test/falsch": SEITE,
                  "https://shop.test/echt": ECHT_FREI})
    monkeypatch.setattr("app.scheduler.get_http", lambda: http)

    from app import scheduler
    scheduler.ensure_source_rows()
    with SessionLocal() as db:
        from app.models import SourceConfig
        cfg = db.get(SourceConfig, "testquelle")
        cfg.enabled = True
        db.commit()
    return SessionLocal, http


@pytest.mark.asyncio
async def test_falsches_gratis_wird_vor_der_regel_korrigiert(welt):
    SessionLocal, http = welt
    from app.models import Channel, Deal, Match, Rule
    from app.scheduler import run_source

    gesendet = []

    class Kanal:
        async def send(self, config, note, http_):
            gesendet.append(note.titel)
            return True

    import app.pipeline as pipeline
    pipeline.get_channel = lambda typ: Kanal()

    with SessionLocal() as db:
        kanal = Channel(type="discord", name="Test", enabled=True, config={})
        db.add(kanal)
        db.flush()
        db.add(Rule(name="Alles Gratis", enabled=True, nur_gratis=True,
                    priority="SOFORT", channels=[kanal.id]))
        db.commit()

    ergebnis = await run_source("testquelle")
    assert ergebnis["new_items"] == 2

    with SessionLocal() as db:
        from sqlalchemy import select
        deals = {d.titel: d for d in db.scalars(select(Deal))}

        falsch = deals["Bundle angeblich geschenkt"]
        assert falsch.ist_gratis is False, "Die Seite verlangt 14,99 - nicht gratis"
        assert falsch.preis == 14.99
        assert falsch.check_status == "widerlegt"

        echt = deals["Spiel wirklich geschenkt"]
        assert echt.ist_gratis is True
        assert echt.check_status == "bestaetigt"

        # Und das Entscheidende: die Regel hat nur den echten getroffen.
        treffer = [m.deal.titel for m in db.scalars(select(Match))]
        assert treffer == ["Spiel wirklich geschenkt"]

    assert gesendet == ["Spiel wirklich geschenkt"]


@pytest.mark.asyncio
async def test_ohne_gegenprobe_geht_die_falsche_meldung_wieder_raus(welt):
    """Gegenprobe: ausgeschaltet verhaelt sich SparBit wie vorher.

    Ohne diesen Test koennte der obige auch dann gruen sein, wenn die
    Korrektur in Wahrheit von etwas anderem kaeme.
    """
    SessionLocal, http = welt
    from app.db import set_setting
    from app.gratischeck import SETTING_AN
    from app.models import Channel, Deal, Rule
    from app.scheduler import run_source

    class Kanal:
        async def send(self, config, note, http_):
            return True

    import app.pipeline as pipeline
    pipeline.get_channel = lambda typ: Kanal()

    with SessionLocal() as db:
        set_setting(db, SETTING_AN, False)
        kanal = Channel(type="discord", name="Test", enabled=True, config={})
        db.add(kanal)
        db.flush()
        db.add(Rule(name="Alles Gratis", enabled=True, nur_gratis=True,
                    channels=[kanal.id]))
        db.commit()

    await run_source("testquelle")

    with SessionLocal() as db:
        from sqlalchemy import select
        falsch = db.scalar(select(Deal).where(
            Deal.titel == "Bundle angeblich geschenkt"))
        assert falsch.ist_gratis is True        # unkorrigiert, wie frueher
        assert falsch.check_status is None
    assert http.abgerufen == []                 # keine einzige Seite geholt
