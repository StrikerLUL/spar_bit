"""„Warum kam dieser Fund nicht an?"

Die Frage, die man abends stellt, wenn ein Deal im Feed steht, aber
nicht auf dem Handy war. Die Antwort muss zwei Dinge koennen: die
richtige Stufe nennen (nicht irgendeine, die zufaellig auch stoppt),
und dabei denselben Weg gehen wie die Zustellung.

Der zweite Punkt ist der Grund fuer die meisten Tests hier: eine
Diagnose, die anders rechnet als die Zustellung, ist schlimmer als
keine - sie schickt einen zum falschen Knopf.
"""
import pytest

from app.diagnose import DURCH, GESTOPPT, diagnose


@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import lade_app_neu

    monkeypatch.setenv("SPARBIT_DATA_DIR", str(tmp_path))
    lade_app_neu()
    # lade_app_neu() importiert nur - die Tabellen legt sonst der
    # Lifespan-Hook an, und den gibt es ohne TestClient nicht.
    from app.db import SessionLocal, init_db
    init_db()
    with SessionLocal() as sitzung:
        yield sitzung


def mach_deal(db, **kw):
    from app.models import Deal, utcnow

    felder = dict(titel="LEGO Technic Bagger", titel_norm="lego technic bagger",
                  url="https://shop.test/1", url_hash="hash1",
                  quelle="mydealz", preis=49.0, preis_eur=49.0,
                  first_seen=utcnow())
    felder.update(kw)
    deal = Deal(**felder)
    db.add(deal)
    db.commit()
    return deal


def mach_regel(db, **kw):
    from app.models import Rule

    felder = dict(name="Lego", keywords=["lego"], enabled=True, channels=[])
    felder.update(kw)
    regel = Rule(**felder)
    db.add(regel)
    db.commit()
    return regel


def mach_kanal(db, **kw):
    from app.models import Channel

    felder = dict(name="Telegram", type="telegram", enabled=True, config={})
    felder.update(kw)
    kanal = Channel(**felder)
    db.add(kanal)
    db.commit()
    return kanal


def stufe(bericht, name):
    return next(s for s in bericht["stufen"] if s["name"] == name)


# --- Regeln ----------------------------------------------------------------

def test_ohne_regel_sagt_es_das_auch_so(db):
    deal = mach_deal(db)
    bericht = diagnose(db, deal)
    assert stufe(bericht, "Regeln")["stand"] == GESTOPPT
    assert "keine regel" in bericht["fazit"].lower()


def test_jede_regel_sagt_warum_sie_nicht_traf(db):
    deal = mach_deal(db)
    mach_regel(db, name="Kaffee", keywords=["kaffee"])
    bericht = diagnose(db, deal)
    details = stufe(bericht, "Regeln")["details"]
    assert details[0]["regel"] == "Kaffee"
    assert details[0]["stand"] == "trifft nicht"
    assert details[0]["text"]                      # eine Begruendung, kein leeres Feld


def test_eine_ausgeschaltete_regel_wird_als_solche_genannt(db):
    """Sonst sucht man den Fehler im Stichwort, und es war der Schalter."""
    deal = mach_deal(db)
    mach_regel(db, enabled=False)
    details = stufe(diagnose(db, deal), "Regeln")["details"]
    assert details[0]["stand"] == "aus"


# --- Kanaele ---------------------------------------------------------------

def test_regel_ohne_kanal_ist_der_haeufigste_fall(db):
    """Ein Treffer ohne Empfaenger - die Regel arbeitet, es kommt nur nichts an."""
    deal = mach_deal(db)
    mach_regel(db)
    bericht = diagnose(db, deal)
    assert stufe(bericht, "Regeln")["stand"] == DURCH
    assert stufe(bericht, "Kanaele")["stand"] == GESTOPPT
    assert "Kanaele" in bericht["fazit"]


def test_ausgeschalteter_kanal_faellt_auf(db):
    deal = mach_deal(db)
    kanal = mach_kanal(db, enabled=False)
    mach_regel(db, channels=[kanal.id])
    kanal_stufe = stufe(diagnose(db, deal), "Kanaele")
    assert kanal_stufe["stand"] == GESTOPPT
    assert kanal_stufe["details"][0]["stand"] == "aus"


def test_mit_regel_und_kanal_ist_alles_offen(db):
    deal = mach_deal(db)
    kanal = mach_kanal(db)
    mach_regel(db, channels=[kanal.id])
    bericht = diagnose(db, deal)
    assert stufe(bericht, "Kanaele")["stand"] == DURCH
    assert "Kein Hindernis" in bericht["fazit"]


# --- Die beiden Wege ------------------------------------------------------

def test_der_preisfehler_weg_blockiert_nicht_wenn_eine_regel_trifft(db):
    """Fruehere Fassung antwortete auf jeden gewoehnlichen Deal mit
    „zu wenig Preisfehler-Punkte" - richtig, aber am Thema vorbei."""
    deal = mach_deal(db)
    kanal = mach_kanal(db)
    mach_regel(db, channels=[kanal.id])
    bericht = diagnose(db, deal)
    preis = stufe(bericht, "Preisfehler-Weg")
    assert preis["stand"] == GESTOPPT           # 0 Punkte, stimmt ja
    assert preis["blockiert"] is False          # aber es ist nicht der Grund
    assert "Preisfehler" not in bericht["fazit"]


def test_ohne_regel_traegt_der_preisfehler_weg(db):
    from app.db import set_setting

    deal = mach_deal(db, fehler_score=85, fehler_stufe="heiss")
    mach_kanal(db)
    set_setting(db, "preisfehler_waechter", True)
    db.commit()
    bericht = diagnose(db, deal)
    assert bericht["weg"] == "preisfehler"
    assert stufe(bericht, "Preisfehler-Weg")["stand"] == DURCH
    # Der Preisfehler-Weg kennt keine Ruhezeit - das soll auch dastehen.
    assert stufe(bericht, "Ruhezeit")["blockiert"] is False


def test_ohne_jeden_weg_sagt_das_fazit_beides(db):
    deal = mach_deal(db)
    mach_regel(db, name="Kaffee", keywords=["kaffee"])
    bericht = diagnose(db, deal)
    assert bericht["weg"] == "keiner"
    assert "Preisfehler" in bericht["fazit"]


# --- Pause und Ruhezeit ---------------------------------------------------

def test_globale_pause_steht_vor_allem_anderen(db):
    from app.db import set_setting

    deal = mach_deal(db)
    kanal = mach_kanal(db)
    mach_regel(db, channels=[kanal.id])
    set_setting(db, "notifications_paused", True)
    db.commit()
    bericht = diagnose(db, deal)
    assert stufe(bericht, "Pause")["stand"] == GESTOPPT
    assert bericht["fazit"].startswith("Pause")


def test_sofort_kommt_durch_die_ruhezeit(db):
    from app.db import set_setting

    deal = mach_deal(db)
    kanal = mach_kanal(db)
    mach_regel(db, channels=[kanal.id], priority="SOFORT")
    # Ruhezeit rund um die Uhr - so braucht der Test keine Uhrzeit.
    set_setting(db, "quiet_hours",
                {"enabled": True, "start": "00:00", "end": "23:59",
                 "utc_offset": 0})
    db.commit()
    ruhe = stufe(diagnose(db, deal), "Ruhezeit")
    assert ruhe["stand"] == DURCH
    assert "SOFORT" in ruhe["text"]


def test_normal_bleibt_in_der_ruhezeit_liegen(db):
    from app.db import set_setting

    deal = mach_deal(db)
    kanal = mach_kanal(db)
    mach_regel(db, channels=[kanal.id], priority="NORMAL")
    set_setting(db, "quiet_hours",
                {"enabled": True, "start": "00:00", "end": "23:59",
                 "utc_offset": 0})
    db.commit()
    bericht = diagnose(db, deal)
    assert stufe(bericht, "Ruhezeit")["stand"] == GESTOPPT
    assert "Sammelmeldung" in stufe(bericht, "Ruhezeit")["text"]


# --- 18+ -------------------------------------------------------------------

def test_18plus_wird_als_erstes_geprueft(db):
    deal = mach_deal(db, erwachsen=True)
    kanal = mach_kanal(db)
    mach_regel(db, channels=[kanal.id])
    bericht = diagnose(db, deal)
    assert stufe(bericht, "18+-Sperre")["stand"] == GESTOPPT
    assert bericht["fazit"].startswith("18+")


# --- Versandverlauf --------------------------------------------------------

def test_ein_fehlgeschlagener_versand_steht_im_klartext(db):
    from app.models import NotificationLog

    deal = mach_deal(db)
    kanal = mach_kanal(db)
    regel = mach_regel(db, channels=[kanal.id])
    db.add(NotificationLog(channel_id=kanal.id, channel_type="telegram",
                           rule_id=regel.id, rule_name="Lego",
                           deal_id=deal.id, deal_titel=deal.titel,
                           ok=False, error="401 Unauthorized"))
    db.commit()
    versand = stufe(diagnose(db, deal), "Versand")
    assert versand["stand"] == GESTOPPT
    assert versand["details"][0]["text"] == "401 Unauthorized"


def test_ohne_versuch_ist_der_versand_keine_ursache(db):
    """Ein leerer Versandverlauf ist die Folge einer frueheren Stufe."""
    deal = mach_deal(db)
    versand = stufe(diagnose(db, deal), "Versand")
    assert versand["blockiert"] is False


def test_zugestellt_wird_als_zugestellt_erkannt(db):
    from app.models import Match, utcnow

    deal = mach_deal(db)
    kanal = mach_kanal(db)
    regel = mach_regel(db, channels=[kanal.id])
    db.add(Match(rule_id=regel.id, deal_id=deal.id, notified_at=utcnow()))
    db.commit()
    bericht = diagnose(db, deal)
    assert bericht["zugestellt"] is True
    assert "zugestellt" in bericht["fazit"]
