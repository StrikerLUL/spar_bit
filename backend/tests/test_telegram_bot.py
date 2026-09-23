"""Der Telegram-Bot - 270 Zeilen, die bisher kein Test angefasst hat.

Er ist der einzige Teil von SparBit, der Befehle von aussen entgegen-
nimmt. Was hier schiefgeht, geht an einer Stelle schief, an der niemand
hinsieht: ein Knopf unter einer Meldung tut nichts, ein /pause
pausiert nicht, oder - der unangenehmste Fall - ein Deal-Titel mit
einem spitzen Klammerzeichen zerlegt die HTML-Nachricht, und Telegram
liefert sie gar nicht erst aus.

Kein Netz: geprueft wird, was der Bot aus der Datenbank macht und was
er zurueckschickt, nicht ob Telegram antwortet.
"""
import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    lade_app_neu()
    from app.db import SessionLocal, init_db
    init_db()
    with SessionLocal() as sitzung:
        yield sitzung


@pytest.fixture
def bot(db):
    # Erst nach lade_app_neu() importieren: der Bot haelt SessionLocal aus
    # dem Modulkopf fest, und ein frueher Import zeigte auf die Datenbank
    # der vorigen Testdatei.
    from app.telegram_bot import TelegramBot
    return TelegramBot()


@pytest.fixture
def snooze_stunden(db):
    from app.telegram_bot import SNOOZE_HOURS
    return SNOOZE_HOURS


def mach_deal(db, **kw):
    from app.models import Deal, utcnow

    nr = kw.pop("nr", 1)
    felder = dict(titel="LEGO Technic Bagger", titel_norm="lego",
                  url=f"https://shop.test/{nr}", url_hash=f"hash{nr}",
                  quelle="mydealz", preis=49.99, waehrung="EUR",
                  first_seen=utcnow())
    felder.update(kw)
    deal = Deal(**felder)
    db.add(deal)
    db.commit()
    return deal


# --- Knoepfe unter der Meldung --------------------------------------------

def test_merken_und_wieder_entmerken(bot, db):
    deal = mach_deal(db)
    assert bot._toggle_bookmark(str(deal.id)) == "Gemerkt"
    db.refresh(deal)
    assert deal.bookmarked is True

    assert bot._toggle_bookmark(str(deal.id)) == "Merkung entfernt"
    db.refresh(deal)
    assert deal.bookmarked is False


def test_ein_geloeschter_deal_laesst_den_knopf_nicht_abstuerzen(bot, db):
    """Deals werden nach 60 Tagen aufgeraeumt - die Nachricht bleibt im Chat."""
    assert bot._toggle_bookmark("999999") == "Deal nicht mehr vorhanden"


def test_muell_als_deal_id_wird_abgefangen(bot, db):
    assert "Ungueltige" in bot._toggle_bookmark("abc")
    assert "Ungueltige" in bot._preisfehler_urteil("", "echt")


def test_quelle_stummschalten_setzt_eine_frist(bot, db, snooze_stunden):
    from datetime import timedelta

    from app.models import SourceConfig, utcnow

    db.add(SourceConfig(id="mydealz", enabled=True))
    db.commit()

    antwort = bot._snooze_source("mydealz")
    assert str(snooze_stunden) in antwort
    cfg = db.get(SourceConfig, "mydealz")
    db.refresh(cfg)
    assert cfg.snooze_until is not None
    # Ungefaehr in SNOOZE_HOURS Stunden - und nicht etwa in der Vergangenheit.
    assert cfg.snooze_until > utcnow() + timedelta(hours=snooze_stunden - 1)


def test_unbekannte_quelle_ist_kein_absturz(bot, db):
    assert bot._snooze_source("gibtsnicht") == "Quelle unbekannt"


def test_preisfehler_rueckmeldung_wird_vermerkt(bot, db):
    deal = mach_deal(db, fehler_score=85, fehler_stufe="heiss")
    antwort = bot._preisfehler_urteil(str(deal.id), "echt")
    assert "echter Preisfehler" in antwort
    db.refresh(deal)
    assert deal.fehler_urteil_mensch is not None


# --- Befehle ---------------------------------------------------------------

def test_status_nennt_die_zahlen(bot, db):
    from app.models import SourceConfig

    db.add(SourceConfig(id="mydealz", enabled=True))
    mach_deal(db)
    db.commit()

    text = bot._cmd_status()
    assert "Quellen aktiv: 1" in text
    assert "Deals gesamt: 1" in text
    assert "laeuft" in text


def test_pause_und_weiter_wirken_wirklich(bot, db):
    from app.db import get_setting

    assert "pausiert" in bot._cmd_pause(True)
    assert get_setting(db, "notifications_paused") is True
    assert "laeuft wieder" in bot._cmd_pause(False)
    assert get_setting(db, "notifications_paused") is False
    # Und der Status sagt danach dasselbe.
    assert "pausiert" not in bot._cmd_status()


def test_neueste_ohne_deals_sagt_das_auch(bot, db):
    assert bot._cmd_deals(nur_gratis=False) == "Noch nichts gefunden."


def test_neueste_zeigt_preis_und_link(bot, db):
    mach_deal(db)
    text = bot._cmd_deals(nur_gratis=False)
    assert "49,99 EUR" in text              # deutsches Komma
    assert "https://shop.test/1" in text


def test_gratis_zeigt_nur_gratis(bot, db):
    mach_deal(db, nr=1)
    mach_deal(db, nr=2, titel="Kostenloses Spiel", ist_gratis=True, preis=0.0)
    text = bot._cmd_deals(nur_gratis=True)
    assert "Kostenloses Spiel" in text
    assert "LEGO" not in text
    assert "gratis" in text


def test_18plus_bleibt_auch_im_chat_draussen(bot, db):
    """Der 18+-Bereich erscheint nirgendwo sonst - auch nicht hier."""
    mach_deal(db, nr=3, titel="Nicht fuer den Chat", erwachsen=True)
    assert "Nicht fuer den Chat" not in bot._cmd_deals(nur_gratis=False)


def test_spitze_klammern_im_titel_zerlegen_die_nachricht_nicht(bot, db):
    """Telegram liest die Nachricht als HTML. Ein ungeschuetztes '<' macht
    aus der ganzen Meldung einen Fehler - und zugestellt wird nichts."""
    mach_deal(db, nr=4, titel="Monitor <27 Zoll> & mehr")
    text = bot._cmd_deals(nur_gratis=False)
    assert "&lt;27 Zoll&gt;" in text
    assert "<27" not in text


def test_deal_ohne_preis_sagt_das_statt_zu_raten(bot, db):
    mach_deal(db, nr=5, preis=None)
    assert "Preis unbekannt" in bot._cmd_deals(nur_gratis=False)


def test_hilfe_nennt_jeden_befehl(bot, db):
    text = bot._cmd_help()
    for befehl in ("/status", "/neueste", "/gratis", "/pause", "/weiter", "/hilfe"):
        assert befehl in text


# --- Der Weg vom Update zur Antwort ---------------------------------------

class FalscherClient:
    """Faengt ab, was der Bot an Telegram schicken wuerde."""

    def __init__(self):
        self.gesendet = []

    async def post(self, url, json=None, **kw):
        self.beobachte = None
        self.gesendet.append((url, json))

        class Antwort:
            status_code = 200

            @staticmethod
            def json():
                return {"ok": True}

        return Antwort()


@pytest.mark.asyncio
async def test_ein_befehl_wird_beantwortet(bot, db):
    client = FalscherClient()
    await bot._handle(client, "TOKEN",
                      {"message": {"chat": {"id": 42}, "text": "/hilfe"}})
    (url, nutzlast), = client.gesendet
    assert url.endswith("/sendMessage")
    assert nutzlast["chat_id"] == 42
    assert "/status" in nutzlast["text"]


@pytest.mark.asyncio
async def test_ein_unbekannter_befehl_bekommt_einen_hinweis(bot, db):
    client = FalscherClient()
    await bot._handle(client, "TOKEN",
                      {"message": {"chat": {"id": 42}, "text": "/tanzen"}})
    assert "/hilfe" in client.gesendet[0][1]["text"]


@pytest.mark.asyncio
async def test_normaler_text_wird_ignoriert(bot, db):
    """Ein Bot in einer Gruppe soll nicht auf jedes Wort antworten."""
    client = FalscherClient()
    await bot._handle(client, "TOKEN",
                      {"message": {"chat": {"id": 42}, "text": "guten morgen"}})
    assert client.gesendet == []


@pytest.mark.asyncio
async def test_befehl_mit_bot_namen_wird_erkannt(bot, db):
    """In Gruppen schreibt Telegram /status@sparbit_bot."""
    client = FalscherClient()
    await bot._handle(client, "TOKEN",
                      {"message": {"chat": {"id": 1},
                                   "text": "/status@mein_sparbit_bot"}})
    assert "SparBit" in client.gesendet[0][1]["text"]


@pytest.mark.asyncio
async def test_ein_knopfdruck_wird_quittiert(bot, db):
    """Ohne answerCallbackQuery dreht sich in Telegram ewig ein Raedchen."""
    deal = mach_deal(db)
    client = FalscherClient()
    await bot._handle(client, "TOKEN", {
        "callback_query": {"id": "abc", "data": f"save:{deal.id}"}})
    url, nutzlast = client.gesendet[0]
    assert url.endswith("/answerCallbackQuery")
    assert nutzlast["callback_query_id"] == "abc"
    assert nutzlast["text"] == "Gemerkt"


@pytest.mark.asyncio
async def test_eine_unbekannte_aktion_wird_trotzdem_quittiert(bot, db):
    client = FalscherClient()
    await bot._handle(client, "TOKEN",
                      {"callback_query": {"id": "abc", "data": "tanzen:1"}})
    assert client.gesendet[0][1]["text"] == "Unbekannte Aktion"


# --- Long Polling ----------------------------------------------------------

class PollClient:
    def __init__(self, antwort):
        self.antwort = antwort
        self.params = None

    async def get(self, url, params=None, **kw):
        self.params = params

        class Antwort:
            status_code = 200
            text = ""

            def json(_):
                return self.antwort

        return Antwort()


@pytest.mark.asyncio
async def test_der_offset_wandert_weiter(bot, db):
    """Ohne wandernden Offset liefert Telegram dieselben Updates wieder -
    und jeder Knopfdruck wirkte endlos."""
    client = PollClient({"ok": True, "result": [
        {"update_id": 10, "message": {}}, {"update_id": 11, "message": {}}]})
    updates = await bot._poll(client, "TOKEN")
    assert len(updates) == 2
    assert bot._offset == 12

    leer = PollClient({"ok": True, "result": []})
    await bot._poll(bot and leer, "TOKEN")
    assert leer.params["offset"] == 12
    assert bot._offset == 12               # ohne Updates bleibt er stehen


@pytest.mark.asyncio
async def test_ein_abgelehntes_token_wird_zum_fehler(bot, db):
    """Sonst liefe die Schleife still weiter und niemand erfuehre, dass das
    Token nicht mehr gilt."""
    client = PollClient({"ok": False, "description": "Unauthorized"})
    with pytest.raises(RuntimeError, match="Unauthorized"):
        await bot._poll(client, "TOKEN")
