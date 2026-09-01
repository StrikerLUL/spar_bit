"""Filter-Engine gegen synthetische Deals - kein Netzwerk, keine DB."""
from types import SimpleNamespace

import pytest

from app.filters import RuleSpec, evaluate, preview


def deal(**kw):
    base = dict(id=1, titel="", beschreibung="", haendler=None, tags=[],
                preis=None, preis_eur=None, originalpreis=None,
                rabatt_prozent=None, ist_gratis=False, temperatur=None,
                quelle="mydealz", kategorie="community",
                url="https://example.com/x", bild=None)
    return SimpleNamespace(**{**base, **kw})


# --- Keywords -------------------------------------------------------------

def test_keyword_oder():
    rule = RuleSpec(keywords=["lego", "playmobil"])
    assert evaluate(rule, deal(titel="LEGO Technic Set")).matched
    assert evaluate(rule, deal(titel="Playmobil Burg")).matched
    assert not evaluate(rule, deal(titel="Duplo Steine")).matched


def test_keyword_ist_wortgenau():
    """'tv' darf nicht in 'Advent' oder 'Motiv' treffen."""
    rule = RuleSpec(keywords=["tv"])
    assert evaluate(rule, deal(titel="Samsung TV 55 Zoll")).matched
    assert not evaluate(rule, deal(titel="Adventskalender")).matched
    assert not evaluate(rule, deal(titel="Motivwagen")).matched


def test_keyword_praefix_stern():
    rule = RuleSpec(keywords=["kopfhoer*"])
    assert evaluate(rule, deal(titel="Kopfhoerer Sony")).matched
    assert evaluate(rule, deal(titel="Kopfhoerern im Angebot")).matched


def test_keyword_phrase():
    rule = RuleSpec(keywords=["nintendo switch"])
    assert evaluate(rule, deal(titel="Nintendo Switch OLED")).matched
    assert not evaluate(rule, deal(titel="Nintendo 3DS und Switch Lite")).matched


def test_pflicht_keywords_sind_und():
    rule = RuleSpec(required_keywords=["ssd", "2tb"])
    assert evaluate(rule, deal(titel="Samsung SSD 2TB")).matched
    res = evaluate(rule, deal(titel="Samsung SSD 1TB"))
    assert not res.matched and any("2tb" in f for f in res.failed)


def test_blacklist_schlaegt_alles():
    rule = RuleSpec(keywords=["lego"], blacklist=["duplo"])
    res = evaluate(rule, deal(titel="LEGO Duplo Starterset"))
    assert not res.matched
    assert "Blacklist" in res.failed[0]


def test_blacklist_prueft_auch_beschreibung():
    rule = RuleSpec(keywords=["ssd"], blacklist=["gebraucht"])
    assert not evaluate(rule, deal(titel="SSD 2TB",
                                   beschreibung="Zustand: gebraucht")).matched


# --- Preis / Rabatt / Gratis ---------------------------------------------

def test_nur_gratis():
    rule = RuleSpec(nur_gratis=True)
    assert evaluate(rule, deal(titel="x", ist_gratis=True)).matched
    assert not evaluate(rule, deal(titel="x", preis=5.0)).matched


def test_max_preis():
    rule = RuleSpec(max_preis=20.0)
    assert evaluate(rule, deal(titel="x", preis=19.99)).matched
    assert not evaluate(rule, deal(titel="x", preis=20.01)).matched


def test_max_preis_ohne_erkannten_preis_faellt_durch():
    """Lieber nichts melden als etwas Teures - kein Preis heisst kein Treffer."""
    res = evaluate(RuleSpec(max_preis=20.0), deal(titel="x", preis=None))
    assert not res.matched and "kein Preis" in res.failed[0]


def test_min_rabatt():
    rule = RuleSpec(min_rabatt_prozent=80)
    assert evaluate(rule, deal(titel="x", rabatt_prozent=85)).matched
    assert not evaluate(rule, deal(titel="x", rabatt_prozent=50)).matched


def test_gratis_zaehlt_als_hundert_prozent():
    rule = RuleSpec(min_rabatt_prozent=90)
    assert evaluate(rule, deal(titel="x", ist_gratis=True,
                               rabatt_prozent=None)).matched


def test_min_temperatur():
    rule = RuleSpec(min_temperatur=200)
    assert evaluate(rule, deal(titel="x", temperatur=350)).matched
    assert not evaluate(rule, deal(titel="x", temperatur=100)).matched


# --- Quellen / Haendler ---------------------------------------------------

def test_quellenauswahl():
    rule = RuleSpec(keywords=["deal"], sources=["mydealz", "reddit"])
    assert evaluate(rule, deal(titel="deal", quelle="mydealz")).matched
    assert not evaluate(rule, deal(titel="deal", quelle="steam")).matched


def test_haendler_teilstring():
    rule = RuleSpec(haendler=["amazon"])
    assert evaluate(rule, deal(titel="x", haendler="Amazon.de")).matched
    assert not evaluate(rule, deal(titel="x", haendler="MediaMarkt")).matched


# --- Kombination ----------------------------------------------------------

def test_alle_bedingungen_sind_und_verknuepft():
    rule = RuleSpec(keywords=["ssd"], max_preis=100, min_rabatt_prozent=50)
    assert evaluate(rule, deal(titel="SSD", preis=80, rabatt_prozent=60)).matched
    assert not evaluate(rule, deal(titel="SSD", preis=120, rabatt_prozent=60)).matched
    assert not evaluate(rule, deal(titel="SSD", preis=80, rabatt_prozent=10)).matched


def test_leere_regel_trifft_nichts():
    """Sonst wuerde eine halbfertige Regel im Editor alles durchwinken."""
    res = evaluate(RuleSpec(), deal(titel="irgendwas"))
    assert not res.matched
    assert "keine Bedingungen" in res.failed[0]


def test_gruende_werden_erklaert():
    rule = RuleSpec(keywords=["lego"], max_preis=50)
    res = evaluate(rule, deal(titel="LEGO Set", preis=30))
    assert res.matched
    assert any("lego" in r.lower() for r in res.reasons)
    assert any("30" in r for r in res.reasons)


# --- Preview (Kernfunktion des Regel-Editors) ----------------------------

def test_preview_zaehlt_und_zeigt_beispiele():
    deals = ([deal(id=i, titel="LEGO Technic", preis=20.0) for i in range(5)]
             + [deal(id=100 + i, titel="Kaffeemaschine", preis=99.0) for i in range(15)])
    result = preview(RuleSpec(keywords=["lego"]), deals)
    assert result["geprueft"] == 20
    assert result["treffer"] == 5
    assert result["trefferquote"] == 25.0
    assert len(result["beispiele"]) == 5
    assert all("LEGO" in b["titel"] for b in result["beispiele"])


def test_preview_zeigt_knapp_verfehlte():
    """Genau eine verfehlte Bedingung -> als 'knapp verfehlt' anbieten,
    damit man beim Tunen sieht, was man gerade ausschliesst."""
    deals = [deal(id=1, titel="LEGO Technic", preis=60.0)]
    result = preview(RuleSpec(keywords=["lego"], max_preis=50), deals)
    assert result["treffer"] == 0
    assert len(result["knapp_verfehlt"]) == 1
    assert "60" in result["knapp_verfehlt"][0]["verfehlt"][0]


def test_preview_ohne_deals():
    result = preview(RuleSpec(keywords=["lego"]), [])
    assert result == {"geprueft": 0, "treffer": 0, "trefferquote": 0.0,
                      "beispiele": [], "knapp_verfehlt": []}


# --- Waehrung -------------------------------------------------------------

def test_preisgrenze_rechnet_in_euro():
    """Ein 25-USD-Deal (~23 EUR) muss eine 'max. 24 EUR'-Regel treffen -
    und ein 25-EUR-Deal darf es nicht."""
    rule = RuleSpec(max_preis=24.0)
    usd = deal(titel="x", preis=25.0, preis_eur=23.0)
    eur = deal(titel="x", preis=25.0, preis_eur=25.0)
    assert evaluate(rule, usd).matched
    assert not evaluate(rule, eur).matched


def test_ohne_eur_preis_zaehlt_der_rohpreis():
    """Faellt die Umrechnung aus, soll der Deal nicht stillschweigend
    verschwinden."""
    rule = RuleSpec(max_preis=20.0)
    assert evaluate(rule, deal(titel="x", preis=15.0, preis_eur=None)).matched
