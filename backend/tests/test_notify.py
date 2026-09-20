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
