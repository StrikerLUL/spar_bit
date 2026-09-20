"""Den Feed finden, statt seinen Pfad zu raten.

Anlass war eine Meldung aus dem Betrieb: /gruppe/erotik-rss lieferte eine
HTML-Seite, und SparBit warf eine SAXParseException. Der Pfad war geraten.
Hier wird geprueft, dass aus so einer Antwort jetzt entweder der richtige
Feed oder wenigstens eine brauchbare Auskunft wird.
"""
import pytest

from app import feedfinder
from app.feedfinder import (KeinFeed, finde_feeds, hole, ist_feed, ist_wand,
                            seitentitel, suche)

# Nachgebaut nach der echten Fehlermeldung: dieselbe DOCTYPE-Zeile, dieselben
# Klassennamen der Pepper-Oberflaeche.
MYDEALZ = '''<!DOCTYPE html><html class="no-js flex--expand-v color--bg-BaseSecondary" lang="de">
<head><title>Erotik Angebote &amp; Schnäppchen | mydealz</title>
<link rel="stylesheet" href="/assets/app.css">
<link rel="alternate icon" type="image/png" href="/favicon.png">
<link rel="alternate" type="application/rss+xml" title="Erotik" href="/rss/gruppe/erotik">
</head><body><main>Deals</main></body></html>'''

FEED = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        '<title>Erotik</title><link>https://www.mydealz.de/gruppe/erotik</link>'
        '<item><title>Satisfyer Pro 2 fuer 24,99</title>'
        '<link>https://www.mydealz.de/deals/1</link></item></channel></rss>')

NACKTE_SEITE = ('<!DOCTYPE html><html><head><title>Shop</title></head>'
                '<body><p>Willkommen</p></body></html>')

CLOUDFLARE = ('<html><head><title>Just a moment...</title></head>'
              '<body>Checking your browser before accessing</body></html>')


class Http:
    def __init__(self, seiten):
        self.seiten = seiten
        self.aufrufe = []

    async def get_text(self, url, **kwargs):
        self.aufrufe.append(url)
        if url not in self.seiten:
            raise RuntimeError("HTTP 404")
        return self.seiten[url]


# --- Erkennen --------------------------------------------------------------

@pytest.mark.parametrize("text,erwartet", [
    (FEED, True),
    ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>', True),
    ('<rdf:RDF xmlns="http://purl.org/rss/1.0/"></rdf:RDF>', True),
    ("﻿<?xml version='1.0'?><rss></rss>", True),        # mit BOM
    (MYDEALZ, False),
    (NACKTE_SEITE, False),
    ("", False),
])
def test_feed_oder_seite(text, erwartet):
    assert ist_feed(text) is erwartet


def test_titel_wird_entschluesselt():
    assert seitentitel(MYDEALZ) == "Erotik Angebote & Schnäppchen | mydealz"


def test_bot_abwehr_wird_erkannt():
    assert ist_wand(CLOUDFLARE)
    assert ist_wand(MYDEALZ) is None


# --- Finden ----------------------------------------------------------------

def test_ausgezeichneter_feed_wird_gefunden():
    feeds = finde_feeds(MYDEALZ, "https://www.mydealz.de/gruppe/erotik-rss")
    assert [f.url for f in feeds] == ["https://www.mydealz.de/rss/gruppe/erotik"]
    assert feeds[0].herkunft == "link" and feeds[0].titel == "Erotik"


def test_favicon_ist_kein_feed():
    """`rel="alternate icon"` steht in jeder zweiten Seite - echt gemessen
    bei GitHub. Wer darauf hereinfaellt, holt sich ein PNG als Feed."""
    seite = ('<html><head><link rel="alternate icon" type="image/png" '
             'href="/favicon.png"></head><body></body></html>')
    assert finde_feeds(seite, "https://x.test/") == []


def test_relative_adressen_werden_absolut():
    seite = ('<html><head><link rel="alternate" type="application/rss+xml" '
             'href="../rss/alle"></head></html>')
    feeds = finde_feeds(seite, "https://x.test/gruppe/erotik")
    assert feeds[0].url == "https://x.test/rss/alle"


def test_links_im_text_sind_zweite_wahl():
    seite = ('<html><head><link rel="alternate" type="application/rss+xml" '
             'href="/echt.xml"></head><body>'
             '<a href="/gruppe/erotik-rss">RSS</a>'
             '<a href="/impressum">Impressum</a></body></html>')
    feeds = finde_feeds(seite, "https://x.test/")
    assert [f.herkunft for f in feeds] == ["link", "anker"]
    assert "impressum" not in " ".join(f.url for f in feeds)


# --- Holen -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_geratener_pfad_heilt_sich_selbst():
    """Der Fall aus dem Betrieb, Ende zu Ende."""
    http = Http({"https://www.mydealz.de/gruppe/erotik-rss": MYDEALZ,
                 "https://www.mydealz.de/rss/gruppe/erotik": FEED})
    fund = await hole(http, "https://www.mydealz.de/gruppe/erotik-rss")
    assert fund.entdeckt is True
    assert fund.url == "https://www.mydealz.de/rss/gruppe/erotik"
    assert fund.text == FEED


@pytest.mark.asyncio
async def test_richtiger_pfad_holt_nur_einmal():
    http = Http({"https://x.test/rss": FEED})
    fund = await hole(http, "https://x.test/rss")
    assert fund.entdeckt is False and http.aufrufe == ["https://x.test/rss"]


@pytest.mark.asyncio
async def test_seite_ohne_feed_erklaert_sich():
    http = Http({"https://x.test/a": NACKTE_SEITE})
    with pytest.raises(KeinFeed) as fehler:
        await hole(http, "https://x.test/a")
    text = str(fehler.value)
    assert "HTML-Seite" in text and "'Shop'" in text
    assert "kein Feed ausgezeichnet" in text
    assert "SAXParse" not in text            # das war die alte, nutzlose Meldung


@pytest.mark.asyncio
async def test_bot_abwehr_klingt_anders_als_ein_falscher_pfad():
    """Sonst sucht man am falschen Ende - ein anderer Pfad hilft da nicht."""
    http = Http({"https://x.test/cf": CLOUDFLARE})
    with pytest.raises(KeinFeed) as fehler:
        await hole(http, "https://x.test/cf")
    assert "Bot-Abwehr" in str(fehler.value)


@pytest.mark.asyncio
async def test_ausgezeichneter_feed_der_auch_nicht_geht():
    http = Http({"https://x.test/a": MYDEALZ})       # der Feed selbst fehlt
    with pytest.raises(KeinFeed) as fehler:
        await hole(http, "https://x.test/a")
    assert "nennt zwar Feeds" in str(fehler.value)


@pytest.mark.asyncio
async def test_hoechstens_drei_kandidaten():
    """Sonst klappert SparBit die Seite einer fremden Domain durch."""
    viele = "".join(
        f'<link rel="alternate" type="application/rss+xml" href="/f{i}.xml">'
        for i in range(8))
    http = Http({"https://x.test/a": f"<html><head>{viele}</head></html>"})
    with pytest.raises(KeinFeed):
        await hole(http, "https://x.test/a")
    assert len(http.aufrufe) == 1 + feedfinder.MAX_VERSUCHE


@pytest.mark.asyncio
async def test_netzfehler_bleibt_netzfehler():
    """Ein Timeout ist kein Feed-Problem und darf nicht so aussehen."""
    http = Http({})
    with pytest.raises(RuntimeError) as fehler:
        await hole(http, "https://x.test/weg")
    assert not isinstance(fehler.value, KeinFeed)


# --- Feed suchen -----------------------------------------------------------

@pytest.mark.asyncio
async def test_suche_nennt_die_adressen():
    http = Http({"https://www.mydealz.de/gruppe/erotik": MYDEALZ})
    ergebnis = await suche(http, "https://www.mydealz.de/gruppe/erotik")
    assert ergebnis["ok"] is True
    assert ergebnis["feeds"][0]["url"] == "https://www.mydealz.de/rss/gruppe/erotik"


@pytest.mark.asyncio
async def test_suche_erkennt_einen_fertigen_feed():
    http = Http({"https://x.test/rss": FEED})
    ergebnis = await suche(http, "https://x.test/rss")
    assert ergebnis["ist_selbst_feed"] is True


@pytest.mark.asyncio
async def test_suche_wirft_nicht():
    """Sie wird auf alles losgelassen, was in der Zwischenablage war."""
    ergebnis = await suche(Http({}), "https://gibtsnicht.test/")
    assert ergebnis["ok"] is False and "Nicht erreichbar" in ergebnis["detail"]


# --- Selbstheilung durch den Runner ---------------------------------------

@pytest.mark.asyncio
async def test_gefundene_adresse_wird_zurueckgeschrieben(tmp_path, monkeypatch):
    """Einmal suchen genuegt: beim naechsten Lauf steht die richtige da.

    Genau der Fall aus dem Betrieb - mydealz_erotik zeigte auf
    /gruppe/erotik-rss, dort kam HTML. Nach einem Lauf muss in der
    Konfiguration die Adresse stehen, die die Seite selbst nennt.
    """
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()

    from app.db import SessionLocal, init_db, set_setting
    from app.erwachsen import AKTIV
    from app.models import SourceConfig
    from app import scheduler

    init_db()
    scheduler.ensure_source_rows()

    http = Http({"https://www.mydealz.de/gruppe/erotik-rss": MYDEALZ,
                 "https://www.mydealz.de/rss/gruppe/erotik": FEED})
    monkeypatch.setattr(scheduler, "get_http", lambda: http)

    with SessionLocal() as db:
        set_setting(db, AKTIV, True)              # 18+-Bereich freischalten
        cfg = db.get(SourceConfig, "mydealz_erotik")
        cfg.enabled = True
        cfg.options = {**(cfg.options or {}), "feeds": ["/gruppe/erotik-rss"]}
        db.commit()

    ergebnis = await scheduler.run_source("mydealz_erotik")
    assert ergebnis["items"] == 1, ergebnis

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "mydealz_erotik")
        assert cfg.options["feeds"] == ["https://www.mydealz.de/rss/gruppe/erotik"]
        assert cfg.last_error is None

    # Zweiter Lauf: die Seite wird gar nicht mehr angefasst.
    http.aufrufe.clear()
    await scheduler.run_source("mydealz_erotik")
    assert http.aufrufe == ["https://www.mydealz.de/rss/gruppe/erotik"]
