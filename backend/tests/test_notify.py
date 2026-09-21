"""Benachrichtigungskanaele. Kein Netzwerk - der HTTP-Client wird ersetzt."""
import json

import pytest

from app.notify import Notification, all_channels, get_channel


class FakeAntwort:
    def __init__(self, status=200, text="ok", daten=None):
        self.status_code = status
        self.text = text
        self._daten = daten

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


class FakeClient:
    """Faengt post/put ab und merkt sich, was verschickt wurde."""

    def __init__(self, antwort=None):
        self.antwort = antwort or FakeAntwort()
        self.aufrufe: list[dict] = []

    async def post(self, url, **kw):
        self.aufrufe.append({"methode": "POST", "url": url, **kw})
        return self.antwort

    async def put(self, url, **kw):
        self.aufrufe.append({"methode": "PUT", "url": url, **kw})
        return self.antwort


def FakeHttp(antwort=None):
    """Echter PoliteClient, nur httpx darunter ausgetauscht.

    So laeuft der Code, den die Kanaele wirklich aufrufen (inklusive der
    Timeout-Vorgabe in PoliteClient.post) - ersetzt ist nur das Netz.
    """
    from app.http import PoliteClient

    http = PoliteClient.__new__(PoliteClient)
    http._client = FakeClient(antwort)
    http.aufrufe = http._client.aufrufe
    return http


def note(**kw):
    grund = dict(titel="Sony WH-1000XM5 Kopfhörer", url="https://shop.de/xm5",
                 quelle="mydealz", regel="Kopfhörer", preis=199.0,
                 originalpreis=379.0, rabatt_prozent=47.0, waehrung="EUR",
                 haendler="Amazon", bild="https://shop.de/xm5.jpg",
                 beschreibung="Mit Geräuschunterdrückung.", deal_id=42,
                 urteil="bestpreis", urteil_text="Bestpreis — so günstig war "
                                                 "es noch nie.")
    return Notification(**{**grund, **kw})


async def sende(typ: str, config: dict, meldung=None, antwort=None):
    http = FakeHttp(antwort)
    await get_channel(typ).send(config, meldung or note(), http)
    return http.aufrufe[0]


# --- Alle Kanaele gemeinsam ------------------------------------------------

def test_neun_kanaele_registriert():
    typen = {c.type for c in all_channels()}
    assert typen == {"telegram", "discord", "slack", "matrix", "gotify",
                     "pushover", "ntfy", "smtp", "webhook"}


@pytest.mark.parametrize("kanal", all_channels(), ids=lambda c: c.type)
def test_jeder_kanal_beschreibt_sich(kanal):
    """Ohne Beschreibung und Feldliste kann das UI nichts anzeigen."""
    assert kanal.display_name and kanal.beschreibung
    assert kanal.options_schema
    for feld in kanal.options_schema:
        assert feld.key and feld.label and feld.type


@pytest.mark.parametrize("typ", ["discord", "slack", "matrix", "gotify",
                                 "pushover", "ntfy", "webhook"])
@pytest.mark.asyncio
async def test_leere_konfiguration_wird_klar_abgelehnt(typ):
    """Ein Kanal ohne Zugangsdaten darf nicht still nichts tun."""
    with pytest.raises((ValueError, RuntimeError)):
        await sende(typ, {})


# --- Discord ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_discord_baut_ein_embed():
    aufruf = await sende("discord",
                         {"url": "https://discord.com/api/webhooks/1/abc"})
    embed = aufruf["json"]["embeds"][0]
    assert "Bestpreis" in embed["title"]
    assert embed["url"] == "https://shop.de/xm5"
    assert embed["thumbnail"]["url"].endswith(".jpg")
    felder = {f["name"]: f["value"] for f in embed["fields"]}
    assert "Preis" in felder and "Preisurteil" in felder
    assert "Amazon" in felder["Händler"]


@pytest.mark.asyncio
async def test_discord_faerbt_nach_urteil():
    gratis = await sende("discord", {"url": "https://discord.com/api/webhooks/1/a"},
                         note(ist_gratis=True))
    schlecht = await sende("discord", {"url": "https://discord.com/api/webhooks/1/a"},
                           note(urteil="uvp_fragwuerdig", ist_gratis=False))
    assert gratis["json"]["embeds"][0]["color"] != schlecht["json"]["embeds"][0]["color"]


@pytest.mark.asyncio
async def test_discord_erwaehnt_rolle_nur_bei_sofort():
    config = {"url": "https://discord.com/api/webhooks/1/a", "rolle": "999"}
    normal = await sende("discord", config, note(prioritaet="NORMAL"))
    sofort = await sende("discord", config, note(prioritaet="SOFORT"))
    assert "content" not in normal["json"]
    assert normal["json"].get("allowed_mentions") is None
    assert sofort["json"]["content"] == "<@&999>"
    # Ohne allowed_mentions koennte Discord @everyone aufloesen.
    assert sofort["json"]["allowed_mentions"] == {"roles": ["999"]}


@pytest.mark.asyncio
async def test_discord_lehnt_fremde_url_ab():
    """Eine Slack-URL in einem Discord-Kanal wuerde sonst still 404 liefern."""
    with pytest.raises(ValueError):
        await sende("discord", {"url": "https://hooks.slack.com/services/x"})


# --- Slack -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_slack_baut_bloecke_und_rueckfalltext():
    aufruf = await sende("slack", {"url": "https://hooks.slack.com/services/x"})
    payload = aufruf["json"]
    # "text" ist die Anzeige in Push-Benachrichtigung und Suche.
    assert "Sony" in payload["text"]
    kopf = payload["blocks"][0]
    assert kopf["type"] == "section"
    assert "https://shop.de/xm5" in kopf["text"]["text"]
    assert kopf["accessory"]["image_url"].endswith(".jpg")


@pytest.mark.asyncio
async def test_slack_maskiert_sonderzeichen():
    aufruf = await sende("slack", {"url": "https://hooks.slack.com/services/x"},
                         note(titel="Kopfhörer <b> & \"Zubehör\""))
    text = json.dumps(aufruf["json"])
    assert "&lt;b&gt;" in text and "&amp;" in text


# --- Matrix ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_matrix_sendet_per_put_mit_token():
    aufruf = await sende("matrix", {"homeserver": "https://matrix.example.de",
                                    "token": "geheim", "raum": "!abc:example.de"})
    assert aufruf["methode"] == "PUT"
    assert "/rooms/%21abc%3Aexample.de/send/m.room.message/" in aufruf["url"]
    assert aufruf["headers"]["Authorization"] == "Bearer geheim"
    assert aufruf["json"]["format"] == "org.matrix.custom.html"
    assert "Sony" in aufruf["json"]["body"]


@pytest.mark.asyncio
async def test_matrix_weist_auf_falsche_raum_id_hin():
    """#raum:server ist der Anzeigename und funktioniert hier nicht - das
    muss die Fehlermeldung sagen."""
    with pytest.raises(ValueError) as info:
        await sende("matrix", {"homeserver": "https://m.de", "token": "t",
                               "raum": "#allgemein:m.de"})
    assert "!" in str(info.value)


# --- Gotify ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_gotify_schickt_token_als_parameter():
    aufruf = await sende("gotify", {"server": "https://gotify.de/", "token": "abc"})
    assert aufruf["url"] == "https://gotify.de/message"
    assert aufruf["params"]["token"] == "abc"
    assert "Sony" in aufruf["json"]["title"]
    assert aufruf["json"]["extras"]["client::notification"]["click"]["url"]


@pytest.mark.asyncio
async def test_gotify_hebt_prioritaet_bei_sofort():
    normal = await sende("gotify", {"server": "https://g.de", "token": "a",
                                    "prioritaet": 3}, note(prioritaet="NORMAL"))
    sofort = await sende("gotify", {"server": "https://g.de", "token": "a",
                                    "prioritaet": 3}, note(prioritaet="SOFORT"))
    assert normal["json"]["priority"] == 3
    assert sofort["json"]["priority"] >= 8


# --- Pushover --------------------------------------------------------------

@pytest.mark.asyncio
async def test_pushover_sendet_formulardaten():
    aufruf = await sende("pushover", {"token": "t", "user": "u"},
                         antwort=FakeAntwort(daten={"status": 1}))
    assert aufruf["data"]["token"] == "t" and aufruf["data"]["user"] == "u"
    assert aufruf["data"]["url"] == "https://shop.de/xm5"
    assert aufruf["data"]["priority"] == 0


@pytest.mark.asyncio
async def test_pushover_meldet_fehler_aus_der_antwort():
    """Pushover antwortet mit HTTP 200 und status=0 - das muss auffallen."""
    with pytest.raises(RuntimeError) as info:
        await sende("pushover", {"token": "t", "user": "u"},
                    antwort=FakeAntwort(daten={"status": 0,
                                               "errors": ["user key is invalid"]}))
    assert "user key is invalid" in str(info.value)


# --- Webhook ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_liefert_das_urteil_mit():
    aufruf = await sende("webhook", {"url": "https://eigenes-system.de/hook"})
    assert aufruf["json"]["urteil"] == "bestpreis"
    assert aufruf["json"]["deal_id"] == 42


@pytest.mark.asyncio
async def test_webhook_erkennt_discord_weiterhin():
    """Bestehende Konfigurationen sollen nach dem Umbau weiterlaufen."""
    aufruf = await sende("webhook",
                         {"url": "https://discord.com/api/webhooks/1/abc"})
    assert "embeds" in aufruf["json"]


# --- Fehlerbehandlung ------------------------------------------------------

@pytest.mark.parametrize("typ,config", [
    ("discord", {"url": "https://discord.com/api/webhooks/1/a"}),
    ("slack", {"url": "https://hooks.slack.com/services/x"}),
    ("matrix", {"homeserver": "https://m.de", "token": "t", "raum": "!a:m.de"}),
    ("gotify", {"server": "https://g.de", "token": "a"}),
])
@pytest.mark.asyncio
async def test_fehlerstatus_wird_gemeldet(typ, config):
    with pytest.raises(RuntimeError):
        await sende(typ, config, antwort=FakeAntwort(status=500, text="kaputt"))


def test_kanaele_nutzen_die_oeffentliche_client_api():
    """Kein Griff in PoliteClient._client - sonst bricht jede Umstellung dort."""
    import pathlib
    ordner = pathlib.Path(__file__).resolve().parents[1] / "app" / "notify"
    schuldige = [p.name for p in ordner.glob("*.py") if "_client" in p.read_text("utf-8")]
    assert not schuldige, f"greifen auf _client zu: {schuldige}"


@pytest.mark.asyncio
async def test_post_setzt_ein_zeitlimit():
    """Ohne Timeout haengt ein toter Webhook den ganzen Versand auf."""
    http = FakeHttp()
    await http.post("https://beispiel.test/hook", json={})
    assert http.aufrufe[0]["timeout"] > 0


# --- Hinweise der Selbstueberwachung ---------------------------------------

def hinweis(**kw):
    """Meldung ueber SparBit selbst: kein Deal, kein Preis, kein Link."""
    grund = dict(titel="Quelle „mydealz“ liefert seit 30 Stunden nichts mehr.",
                 url="", quelle="system", regel="Selbstüberwachung",
                 beschreibung="Endpoint prüfen: Quellen → Jetzt testen.",
                 ist_hinweis=True)
    return Notification(**{**grund, **kw})


def test_hinweis_hat_keine_preiszeile():
    assert hinweis().zeilen() == [("Hinweis", "Endpoint prüfen: Quellen → Jetzt testen.")]


def test_hinweis_und_entwarnung_unterscheiden_sich():
    warnung = hinweis()
    entwarnung = hinweis(titel="Quelle „mydealz“ läuft wieder.",
                         beschreibung=None, ist_entwarnung=True)
    assert warnung.farbe != entwarnung.farbe
    assert "meldet sich" in warnung.kopfzeile
    assert "meldet sich" not in entwarnung.kopfzeile


# Was jeder Kanal antworten muss, damit er den Versand als gelungen ansieht.
GLUECKLICH = {
    "pushover": FakeAntwort(daten={"status": 1}),
    "telegram": FakeAntwort(daten={"ok": True, "result": {}}),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("typ,config", [
    ("discord", {"url": "https://discord.com/api/webhooks/1/x"}),
    ("slack", {"url": "https://hooks.slack.com/services/A/B/C"}),
    ("matrix", {"homeserver": "https://m.example.org", "token": "t",
                "raum": "!r:example.org"}),
    ("gotify", {"server": "https://gotify.example.org", "token": "t"}),
    ("pushover", {"token": "t", "user": "u"}),
    ("telegram", {"bot_token": "1:abc", "chat_id": "42"}),
    ("ntfy", {"topic": "meins"}),
    ("webhook", {"url": "https://n8n.local/hook"}),
])
async def test_jeder_kanal_vertraegt_einen_hinweis(typ, config):
    """Ohne Deal-URL bauen mehrere Dienste sonst ungültige Anfragen."""
    aufruf = await sende(typ, config, hinweis(), antwort=GLUECKLICH.get(typ))
    alles = (json.dumps(aufruf.get("json") or {}, ensure_ascii=False)
             + str(aufruf.get("data") or "") + str(aufruf.get("headers") or "")
             + str(aufruf.get("content") or ""))
    assert "mydealz" in alles


@pytest.mark.asyncio
async def test_discord_laesst_die_leere_embed_url_weg():
    """Discord weist ein Embed mit leerem url-Feld zurueck."""
    aufruf = await sende("discord", {"url": "https://discord.com/api/webhooks/1/x"},
                         hinweis())
    assert "url" not in aufruf["json"]["embeds"][0]


@pytest.mark.asyncio
async def test_telegram_baut_keinen_knopf_ohne_ziel():
    """Ein Inline-Knopf ohne url laesst Telegram die Nachricht ablehnen."""
    aufruf = await sende("telegram", {"bot_token": "1:abc", "chat_id": "42"},
                         hinweis(), antwort=GLUECKLICH["telegram"])
    knoepfe = aufruf["json"].get("reply_markup", {}).get("inline_keyboard", [])
    for reihe in knoepfe:
        for knopf in reihe:
            assert knopf.get("url") != ""


@pytest.mark.asyncio
async def test_ntfy_setzt_keine_aktion_ohne_ziel():
    """ntfy verwirft die Nachricht, wenn Actions kein Ziel hat."""
    aufruf = await sende("ntfy", {"topic": "meins"}, hinweis())
    assert "Actions" not in aufruf["headers"]
    assert aufruf["headers"]["Tags"] == "warning"


@pytest.mark.asyncio
async def test_pushover_setzt_keinen_url_titel_ohne_url(monkeypatch):
    """url_title ohne url quittiert Pushover mit einem Fehler."""
    aufruf = await sende("pushover", {"token": "t", "user": "u"}, hinweis(),
                         antwort=GLUECKLICH["pushover"])
    assert "url_title" not in aufruf["data"]
    assert "url" not in aufruf["data"]


def test_smtp_baut_auch_ohne_deal_eine_mail(monkeypatch):
    gesendet = {}

    class FakeSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, *a, **kw): pass
        def login(self, *a): pass
        def send_message(self, msg): gesendet["msg"] = msg

    import asyncio
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    asyncio.run(get_channel("smtp").send(
        {"host": "smtp.x.de", "username": "u", "password": "p",
         "from_addr": "a@x.de", "to_addr": "b@x.de"}, hinweis(), FakeHttp()))
    assert "mydealz" in str(gesendet["msg"])


# --- Sammelmeldungen -------------------------------------------------------

def sammel(anzahl=5, zeitraum="seit 07:00"):
    """Eine Sammelmeldung mit genau `anzahl` Funden."""
    from app.notify.base import Sammelmeldung

    besonders = [
        Notification(titel="Fernseher für 89 statt 899", url="https://s.test/tv",
                     quelle="mydealz", preis=89.0, fehler_stufe="heiss"),
        Notification(titel="Gratis-Spiel bei Epic", url="https://s.test/epic",
                     quelle="epic", preis=0.0, ist_gratis=True),
    ][:anzahl]
    fuellung = [Notification(titel=f"Deal {i}", url=f"https://s.test/{i}",
                             quelle="mydealz", preis=9.99 + i)
                for i in range(max(0, anzahl - len(besonders)))]
    return Sammelmeldung(meldungen=besonders + fuellung, zeitraum=zeitraum)


async def sende_sammel(typ, config, inhalt=None, antwort=None):
    http = FakeHttp(antwort)
    await get_channel(typ).send_sammel(config, inhalt or sammel(), http)
    return http.aufrufe


@pytest.mark.asyncio
async def test_discord_baut_ein_embed_mit_einem_feld_je_fund():
    aufrufe = await sende_sammel(
        "discord", {"url": "https://discord.com/api/webhooks/1/x"})
    embed = aufrufe[0]["json"]["embeds"][0]
    assert embed["title"] == "5 Funde seit 07:00"
    assert len(embed["fields"]) == 5
    # Der Preisfehler steht oben.
    assert embed["fields"][0]["name"].startswith("‼")


@pytest.mark.asyncio
async def test_discord_kuerzt_lange_listen_und_sagt_es():
    aufrufe = await sende_sammel(
        "discord", {"url": "https://discord.com/api/webhooks/1/x"},
        sammel(anzahl=30))
    embed = aufrufe[0]["json"]["embeds"][0]
    assert len(embed["fields"]) == 20
    assert "10 weitere" in embed["footer"]["text"]


@pytest.mark.asyncio
async def test_telegram_schickt_genau_eine_nachricht():
    aufrufe = await sende_sammel("telegram", {"bot_token": "1:abc", "chat_id": "42"},
                                 antwort=FakeAntwort(daten={"ok": True}))
    assert len(aufrufe) == 1
    text = aufrufe[0]["json"]["text"]
    assert "5 Funde" in text
    assert "Gratis-Spiel bei Epic" in text
    # Linkvorschau aus: sonst haengt Telegram ein zufaelliges Bild an.
    assert aufrufe[0]["json"]["link_preview_options"]["is_disabled"] is True


@pytest.mark.asyncio
async def test_telegram_bleibt_unter_der_laengengrenze():
    aufrufe = await sende_sammel(
        "telegram", {"bot_token": "1:abc", "chat_id": "42"},
        sammel(anzahl=60), antwort=FakeAntwort(daten={"ok": True}))
    assert len(aufrufe[0]["json"]["text"]) <= 4000


@pytest.mark.asyncio
async def test_slack_baut_kopf_und_liste():
    aufrufe = await sende_sammel("slack",
                                 {"url": "https://hooks.slack.com/services/A/B/C"})
    bloecke = aufrufe[0]["json"]["blocks"]
    assert bloecke[0]["type"] == "header"
    assert "5 Funde" in bloecke[0]["text"]["text"]
    assert "Gratis-Spiel bei Epic" in bloecke[1]["text"]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("typ,config", [
    ("gotify", {"server": "https://gotify.example.org", "token": "t"}),
    ("ntfy", {"topic": "meins"}),
    ("webhook", {"url": "https://n8n.local/hook"}),
    ("matrix", {"homeserver": "https://m.example.org", "token": "t",
                "raum": "!r:example.org"}),
    ("pushover", {"token": "t", "user": "u"}),
])
async def test_kanaele_ohne_eigene_fassung_nutzen_den_rueckfall(typ, config):
    """Auch ohne send_sammel darf es nur eine Nachricht werden."""
    aufrufe = await sende_sammel(typ, config, antwort=GLUECKLICH.get(typ))
    assert len(aufrufe) == 1
    alles = (json.dumps(aufrufe[0].get("json") or {}, ensure_ascii=False)
             + str(aufrufe[0].get("data") or "") + str(aufrufe[0].get("headers") or "")
             + str(aufrufe[0].get("content") or ""))
    assert "5 Funde" in alles


@pytest.mark.asyncio
async def test_ein_einzelner_fund_geht_als_normale_meldung_raus():
    """Eine „Zusammenfassung“ mit einem Eintrag wäre albern."""
    aufrufe = await sende_sammel(
        "discord", {"url": "https://discord.com/api/webhooks/1/x"}, sammel(anzahl=1))
    embed = aufrufe[0]["json"]["embeds"][0]
    assert "Funde" not in embed["title"]
    assert embed["title"].startswith("PREISFEHLER")
