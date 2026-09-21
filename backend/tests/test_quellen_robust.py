"""Was Quellen mit einer Absage machen.

Der Anlass sind zwei Meldungen aus dem Betrieb, in denen jede eingeschaltete
18+-Quelle nur noch Fehler produzierte:

    r/SexToyDeals: HTTPStatusError: 404 Not Found
    r/NSFWdeals: RateLimited: HTTP 429, retry after 58s
    https://www.mydealz.de/gruppe/erotik-rss: KeinFeed: HTML statt Feed

Der gemeinsame Nenner war nicht, dass etwas schiefging - das darf es -,
sondern dass beim naechsten Lauf wieder genau dasselbe schiefging. Hier
steht, was stattdessen passieren muss: einen Namen, den es nicht gibt,
streichen; bei einer Drosselung weiterruecken statt anrennen; eine gefundene
Adresse behalten, auch wenn der Lauf insgesamt fehlschlug.
"""
import pytest

# Achtung: hier wird absichtlich NICHTS aus `app` auf Modulebene importiert.
# `conftest.lade_app_neu()` (in den Scheduler-Tests unten und in anderen
# Dateien) wirft das ganze app-Paket weg und importiert es neu. Ein oben
# festgehaltenes `RateLimited` waere danach eine andere Klasse als die, die
# der frisch geladene Quellcode faengt - und ein `except RateLimited` ginge
# ins Leere. Deshalb holt sich jeder Test seine Klassen selbst.


def rate_limited():
    from app.http import RateLimited
    return RateLimited


def kontext_klasse():
    from app.sources.base import FetchContext
    return FetchContext

FEED = ('<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        '<item><title>[Steam] Portal 2 (gratis)</title>'
        '<link>https://example.test/1</link></item></channel></rss>')

SEITE = ('<!DOCTYPE html><html><head><title>Suche nach "satisfyer"</title>'
         '</head><body>keine Auszeichnung</body></html>')


class Antwort:
    def __init__(self, status):
        self.status_code = status


class HttpFehler(Exception):
    def __init__(self, status):
        super().__init__(f"Client error '{status}'")
        self.response = Antwort(status)


class Http:
    """Nur so viel httpx, wie die Quellen anfassen."""

    def __init__(self, seiten=None, status=None, drosselt=()):
        self.seiten = seiten or {}
        self.status = status or {}
        self.drosselt = set(drosselt)
        self.aufrufe = []

    async def get_text(self, url, **kwargs):
        self.aufrufe.append(url)
        if url in self.drosselt:
            raise rate_limited()(58.0, 429)
        if url in self.status:
            raise HttpFehler(self.status[url])
        if url not in self.seiten:
            raise RuntimeError("unerreichbar")
        return self.seiten[url]


def ctx_fuer(quelle, http, **optionen):
    opts = dict(quelle.default_options)
    opts.update(optionen)
    return kontext_klasse()(http=http, options=opts)


@pytest.fixture(autouse=True)
def ohne_sperrfrist():
    from app import feedfinder
    feedfinder.pause_zuruecksetzen()


# --- Subreddit-Namen -------------------------------------------------------

@pytest.mark.parametrize("eingabe,erwartet", [
    (["r/GameDeals"], ["GameDeals"]),
    (["/r/GameDeals/"], ["GameDeals"]),
    (["https://www.reddit.com/r/GameDeals/"], ["GameDeals"]),
    (["GameDeals", "gamedeals"], ["GameDeals"]),          # Dublette
    (["  ", "", "r/"], []),                               # leer
    (["nicht erlaubt!"], []),                             # kein gueltiger Name
])
def test_namen_werden_geputzt(eingabe, erwartet):
    """Was Leute hineinkopieren, soll nicht als 404 zurueckkommen."""
    from app.sources.reddit import _saubere_namen
    assert _saubere_namen(eingabe) == erwartet


# --- Reddit: 404 ist endgueltig -------------------------------------------

@pytest.mark.asyncio
async def test_toter_subreddit_wird_gestrichen():
    """Der Fall r/SexToyDeals: 404 heisst, den gibt es nicht."""
    http = Http({"https://www.reddit.com/r/GameDeals/new/.rss": FEED},
                status={"https://www.reddit.com/r/GibtsNicht/new/.rss": 404})
    from app.sources.reddit import Reddit
    quelle = Reddit()
    ctx = ctx_fuer(quelle, http, subreddits=["GibtsNicht", "GameDeals"])

    items = await quelle.fetch(ctx)

    assert len(items) == 1                       # GameDeals liefert weiter
    assert ctx.notizen["subreddits"] == ["GameDeals"]
    assert ctx.notizen["entfernt"] == ["GibtsNicht"]


@pytest.mark.asyncio
async def test_gestrichener_subreddit_kostet_nichts_mehr():
    """Zweiter Lauf mit der korrigierten Liste: kein Anklopfen mehr."""
    http = Http({"https://www.reddit.com/r/GameDeals/new/.rss": FEED},
                status={"https://www.reddit.com/r/GibtsNicht/new/.rss": 404})
    from app.sources.reddit import Reddit
    quelle = Reddit()
    ctx = ctx_fuer(quelle, http, subreddits=["GibtsNicht", "GameDeals"])
    await quelle.fetch(ctx)

    zweiter = ctx_fuer(quelle, http, **{**ctx.options, **ctx.notizen})
    http.aufrufe.clear()
    await quelle.fetch(zweiter)
    assert http.aufrufe == ["https://www.reddit.com/r/GameDeals/new/.rss"]


@pytest.mark.asyncio
async def test_privater_subreddit_wird_nicht_gestrichen():
    """403 heisst 'nicht fuer dich', nicht 'gibt es nicht' - Finger weg."""
    http = Http(status={"https://www.reddit.com/r/Privat/new/.rss": 403})
    from app.sources.reddit import Reddit
    quelle = Reddit()
    ctx = ctx_fuer(quelle, http, subreddits=["Privat"])

    with pytest.raises(RuntimeError) as fehler:
        await quelle.fetch(ctx)

    assert "403" in str(fehler.value)
    assert "subreddits" not in ctx.notizen


# --- Reddit: 429 ist eine Pause, kein Defekt ------------------------------

@pytest.mark.asyncio
async def test_drosselung_bricht_ab_statt_anzurennen():
    """Ist der Host gesperrt, bekommen die restlichen Namen dieselbe Absage.

    Frueher liefen alle drei Subreddits in ihr eigenes 429 - drei
    Fehlermeldungen fuer ein einziges Problem.
    """
    http = Http(drosselt={"https://www.reddit.com/r/Eins/new/.rss"})
    from app.sources.reddit import Reddit
    quelle = Reddit()
    ctx = ctx_fuer(quelle, http, subreddits=["Eins", "Zwei", "Drei"])

    with pytest.raises(rate_limited()):
        await quelle.fetch(ctx)

    assert http.aufrufe == ["https://www.reddit.com/r/Eins/new/.rss"]


@pytest.mark.asyncio
async def test_nach_der_drosselung_geht_es_dort_weiter():
    """Sonst verbrauchen immer dieselben ersten Namen das Kontingent."""
    from app.sources.reddit import Reddit
    from app.sources.reddit import Reddit
    quelle = Reddit()
    erste = "https://www.reddit.com/r/Eins/new/.rss"
    zweite = "https://www.reddit.com/r/Zwei/new/.rss"

    http = Http(drosselt={erste})
    ctx = ctx_fuer(quelle, http, subreddits=["Eins", "Zwei"])
    with pytest.raises(rate_limited()):
        await quelle.fetch(ctx)
    assert ctx.notizen.get("_offset") == 0        # Eins ist noch offen

    # Naechster Lauf, Drosselung trifft jetzt den zweiten Namen.
    http2 = Http({erste: FEED}, drosselt={zweite})
    ctx2 = ctx_fuer(quelle, http2, **{**ctx.options, **ctx.notizen})
    items = await quelle.fetch(ctx2)
    assert len(items) == 1
    assert http2.aufrufe == [erste, zweite]
    assert ctx2.notizen.get("_offset") == 1       # Zwei kommt zuerst dran


@pytest.mark.asyncio
async def test_max_pro_lauf_teilt_die_liste_auf():
    http = Http({f"https://www.reddit.com/r/S{i}/new/.rss": FEED
                 for i in range(4)})
    from app.sources.reddit import Reddit
    quelle = Reddit()
    ctx = ctx_fuer(quelle, http, subreddits=[f"S{i}" for i in range(4)],
                   max_pro_lauf=2)

    await quelle.fetch(ctx)
    assert len(http.aufrufe) == 2
    assert ctx.notizen["_offset"] == 2

    ctx2 = ctx_fuer(quelle, http, **{**ctx.options, **ctx.notizen})
    http.aufrufe.clear()
    await quelle.fetch(ctx2)
    assert http.aufrufe == ["https://www.reddit.com/r/S2/new/.rss",
                            "https://www.reddit.com/r/S3/new/.rss"]


# --- Pepper: eine geheilte Suche gilt fuer alle Begriffe ------------------

@pytest.mark.asyncio
async def test_such_vorlage_wird_einmal_gelernt():
    """Der Fall preisjaeger: /search?q=…&rss=1 liefert HTML.

    Findet SparBit den Such-Feed woanders, muss die *Vorlage* mitwandern -
    sonst sucht jeder weitere Begriff dieselbe Adresse noch einmal ab.
    """
    http = Http({
        "https://www.mydealz.de/search?q=satisfyer&rss=1": SEITE,
        "https://www.mydealz.de/rss/search?q=satisfyer": FEED,
        "https://www.mydealz.de/rss/search?q=gleitgel": FEED,
    })
    from app.sources.pepper import MyDealz
    quelle = MyDealz()
    ctx = ctx_fuer(quelle, http, feeds=[],
                   search_terms=["satisfyer"],
                   search_path="/search?q={term}&rss=1")

    items = await quelle.fetch(ctx)

    assert items
    assert ctx.notizen["search_path"] == "/rss/search?q={term}"


@pytest.mark.asyncio
async def test_gruppen_seite_heilt_sich_ueber_das_muster():
    """Die Gruppen-Seite zeichnet nichts aus - trotzdem kommt ein Feed."""
    http = Http({"https://www.mydealz.de/gruppe/erotik": SEITE,
                 "https://www.mydealz.de/rss/gruppe/erotik": FEED})
    from app.sources.pepper import MyDealz
    quelle = MyDealz()
    ctx = ctx_fuer(quelle, http, feeds=["/gruppe/erotik"], search_terms=[])

    items = await quelle.fetch(ctx)

    assert items
    assert ctx.notizen["feeds"] == ["https://www.mydealz.de/rss/gruppe/erotik"]


@pytest.mark.asyncio
async def test_ein_kaputter_feed_kippt_nicht_die_quelle():
    http = Http({"https://www.mydealz.de/rss/alle": FEED},
                status={"https://www.mydealz.de/rss/kaputt": 500})
    from app.sources.pepper import MyDealz
    quelle = MyDealz()
    ctx = ctx_fuer(quelle, http, feeds=["/rss/alle", "/rss/kaputt"],
                   search_terms=[])
    assert len(await quelle.fetch(ctx)) == 1


@pytest.mark.asyncio
async def test_fehlermeldung_bleibt_lesbar():
    """Sechs Fehler ergeben keine sechs Absaetze im Quellen-Dialog."""
    from app.sources.pepper import MyDealz
    quelle = MyDealz()
    ctx = ctx_fuer(quelle, Http(), feeds=[f"/rss/f{i}" for i in range(6)],
                   search_terms=[])
    with pytest.raises(RuntimeError) as fehler:
        await quelle.fetch(ctx)
    assert "+3 weitere" in str(fehler.value)


# --- Eigene 18+-Quellen ----------------------------------------------------

@pytest.mark.asyncio
async def test_shop_adresse_genuegt():
    """Die Arbeitsquelle des 18+-Bereichs: Shop eintragen, Feed findet sich.

    Der Shop zeichnet nichts aus - Shopify legt seinen Feed aber immer an
    dieselbe Stelle.
    """
    from app.sources.erwachsen import ErotikFeed

    http = Http({"https://shop.test/collections/sale": SEITE,
                 "https://shop.test/collections/sale.atom": FEED})
    quelle = ErotikFeed()
    ctx = ctx_fuer(quelle, http, feeds=["https://shop.test/collections/sale"])

    items = await quelle.fetch(ctx)

    assert [i.kategorie for i in items] == ["erwachsen"]
    assert ctx.notizen["feeds"] == ["https://shop.test/collections/sale.atom"]


@pytest.mark.asyncio
async def test_nur_gedrosselt_ist_kein_defekt():
    """Ein einziger Host, der bremst, darf nicht als Defekt gezaehlt werden."""
    from app.sources.erwachsen import ErotikFeed

    http = Http(drosselt={"https://shop.test/feed"})
    quelle = ErotikFeed()
    ctx = ctx_fuer(quelle, http, feeds=["https://shop.test/feed"])

    with pytest.raises(rate_limited()):
        await quelle.fetch(ctx)


@pytest.mark.asyncio
async def test_neben_der_drosselung_zaehlt_der_echte_fehler():
    """Sonst verschwindet ein kaputter Feed hinter einer Pause."""
    from app.sources.erwachsen import ErotikFeed

    http = Http(status={"https://kaputt.test/feed": 500},
                drosselt={"https://shop.test/feed"})
    quelle = ErotikFeed()
    ctx = ctx_fuer(quelle, http, feeds=["https://shop.test/feed",
                                        "https://kaputt.test/feed"])

    with pytest.raises(RuntimeError) as fehler:
        await quelle.fetch(ctx)
    assert "kaputt.test" in str(fehler.value)


# --- Was der Scheduler daraus macht ---------------------------------------
#
# Achtung beim Lesen: `lade_app_neu()` importiert das ganze app-Paket neu.
# Die Klassen oben in dieser Datei sind danach nicht mehr dieselben Objekte
# wie die im frisch geladenen Code - deshalb werden RateLimited & Co. in
# diesen beiden Tests innerhalb der Funktion geholt.

def _frischer_server(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    from conftest import lade_app_neu
    lade_app_neu()
    from app import scheduler
    from app.db import init_db
    init_db()
    scheduler.ensure_source_rows()
    return scheduler


@pytest.mark.asyncio
async def test_gelerntes_ueberlebt_einen_fehlschlag(tmp_path, monkeypatch):
    """Ein Lauf, der nichts liefert, kann trotzdem etwas gelernt haben.

    Frueher wurde `ctx.notizen` nur nach einem erfolgreichen Lauf
    gespeichert. Eine Liste aus lauter toten Subreddits blieb damit fuer
    immer eine Liste aus lauter toten Subreddits - jeden Lauf aufs Neue.
    """
    scheduler = _frischer_server(tmp_path, monkeypatch)
    from app.db import SessionLocal
    from app.models import SourceConfig

    http = Http(status={"https://www.reddit.com/r/GibtsNicht/new/.rss": 404})
    monkeypatch.setattr(scheduler, "get_http", lambda: http)

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "reddit")
        cfg.enabled = True
        cfg.options = {**(cfg.options or {}), "subreddits": ["GibtsNicht"]}
        db.commit()

    ergebnis = await scheduler.run_source("reddit")
    assert "error" in ergebnis

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "reddit")
        assert cfg.options["subreddits"] == []
        assert cfg.options["entfernt"] == ["GibtsNicht"]
        assert "404" in (cfg.last_error or "")


@pytest.mark.asyncio
async def test_drosselung_sperrt_die_quelle_nicht_aus(tmp_path, monkeypatch):
    """Gedrosselt ist nicht kaputt.

    Bei drei Rate-Limits in Folge machte der Schutzschalter zu und die
    Quelle lief eine halbe Stunde gar nicht mehr - obwohl mit ihr alles in
    Ordnung ist und die Gegenseite sogar gesagt hat, wie lange sie Ruhe will.
    """
    scheduler = _frischer_server(tmp_path, monkeypatch)
    from app.db import SessionLocal
    from app.http import RateLimited as Frisch
    from app.models import SourceConfig

    class Gedrosselt:
        async def get_text(self, url, **kwargs):
            raise Frisch(58.0, 429)

    monkeypatch.setattr(scheduler, "get_http", lambda: Gedrosselt())

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "reddit")
        cfg.enabled = True
        cfg.options = {**(cfg.options or {}), "subreddits": ["GameDeals"]}
        db.commit()

    for _ in range(3):
        await scheduler.run_source("reddit", manual=True)

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, "reddit")
        assert cfg.consecutive_failures == 0        # kein Schritt Richtung Sperre
        assert cfg.circuit_open_until is None
        assert cfg.snooze_until is not None          # stattdessen: Pause
        assert "Rate-Limit" in (cfg.last_error or "")
