"""Eine Installation mit glaubwuerdigen Beispieldaten fuer Screenshots."""
import os
import random
import sys
import tempfile
from datetime import timedelta

ordner = tempfile.mkdtemp(prefix="sparbit-demo-")
os.environ["SPARBIT_DATA_DIR"] = ordner
os.environ["SPARBIT_LOG_JSON"] = "false"
os.environ["SPARBIT_TELEGRAM_POLLING"] = "false"
sys.path.insert(0, "backend")

from app.auth import create_user
from app.db import SessionLocal, init_db
from app.models import (
    Channel,
    Deal,
    DealOffer,
    Interaction,
    Match,
    PriceHistory,
    Rule,
    WatchItem,
    WatchListe,
    WatchPrice,
    utcnow,
)

init_db()

DEALS = [
    ("LEGO Technic Ferrari Daytona SP3", 249.99, 449.99, "amazon", "mydealz", "bestpreis", 96),
    ("Samsung 990 Pro 2TB NVMe SSD", 88.90, 189.00, "mediamarkt", "preisjaeger", "sehr gut", 0),
    ("Sony WH-1000XM5 Kopfhörer, schwarz", 229.00, 419.00, "amazon", "mydealz", "gut", 0),
    ("Philips Hue Starter Set E27", 89.95, 139.99, "saturn", "sparhamster", "normal", 0),
    ("Cyberpunk 2077 Ultimate Edition", 24.99, 79.99, "steam", "steam", "bestpreis", 0),
    ("Anker PowerBank 20000mAh", 8.99, 59.99, "amazon", "preisjaeger", "bestpreis", 88),
    ("iRobot Roomba j7+ Saugroboter", 399.00, 999.00, "otto", "mydealz", "sehr gut", 0),
    ("Kindle Paperwhite 16GB", 109.99, 159.99, "amazon", "mydealz", "gut", 0),
    ("Nintendo Switch OLED weiß", 279.00, 349.99, "mediamarkt", "preisjaeger", "gut", 0),
    ("Logitech MX Master 3S", 69.99, 119.00, "amazon", "schnaeppchenfuchs", "sehr gut", 0),
]

GRATIS = [
    ("Control Ultimate Edition", "epic", 39.99),
    ("Fall Guys Season Pass", "epic", 9.99),
    ("Ghostrunner", "gog", 29.99),
]

with SessionLocal() as db:
    create_user(db, "cillian", "einGutesPasswort1")

    db.add(Channel(type="telegram", name="Handy", enabled=True,
                   config={"bot_token": "1", "chat_id": "1"}, benutzer_id=1))
    db.add(Channel(type="browser", name="Browser", enabled=True, config={}, benutzer_id=1))
    db.flush()

    regeln = [
        Rule(name="LEGO & Technik", keywords=["lego", "ssd", "nvme"], priority="SOFORT",
             max_preis=300, enabled=True, channels=[1], benutzer_id=1, match_count=14),
        Rule(name="Alles Gratis", nur_gratis=True, priority="SOFORT", enabled=True,
             channels=[1, 2], benutzer_id=1, match_count=37),
        Rule(name="Nur echte Bestpreise", min_urteil="bestpreis", priority="NORMAL",
             enabled=True, channels=[1], benutzer_id=1, match_count=8),
    ]
    for r in regeln:
        db.add(r)
    db.flush()

    jetzt = utcnow()
    for n, (titel, preis, original, haendler, quelle, urteil, fehler) in enumerate(DEALS):
        deal = Deal(url_hash=f"demo{n}", titel=titel, titel_norm=titel.lower(),
                    url=f"https://{haendler}.de/artikel/{n}", preis=preis,
                    preis_eur=preis, originalpreis=original,
                    rabatt_prozent=round((1 - preis / original) * 100, 1),
                    haendler=haendler, quelle=quelle, urteil=urteil,
                    urteil_text={"bestpreis": "So günstig war es noch nie beobachtet",
                                 "sehr gut": "Im unteren Viertel des bisher Gesehenen",
                                 "gut": "Guenstiger als üblich",
                                 "normal": "Üblicher Preis"}[urteil],
                    temperatur=random.randint(120, 890),
                    first_seen=jetzt - timedelta(hours=n * 3 + 1),
                    last_seen=jetzt, seen_count=random.randint(1, 5),
                    bookmarked=n in (0, 1, 6))
        if fehler:
            deal.fehler_score = fehler
            deal.fehler_stufe = "heiss" if fehler >= 90 else "verdacht"
            deal.fehler_gruende = ["Preis liegt 78 % unter dem eigenen Verlauf",
                                   "Kommastelle verrutscht (249,99 statt 24,99)",
                                   "Zwei andere Quellen nennen 249,00 EUR"]
            deal.fehler_erwartet_eur = original * 0.8
            deal.fehler_am = jetzt
        db.add(deal)
        db.flush()
        basis = original * 0.85
        for t in range(12):
            db.add(PriceHistory(deal_id=deal.id,
                                preis=round(basis * random.uniform(0.9, 1.1), 2),
                                ts=jetzt - timedelta(days=12 - t)))
        db.add(PriceHistory(deal_id=deal.id, preis=preis, ts=jetzt))
        for q in {quelle, "cheapshark", "ggdeals"}:
            db.add(DealOffer(deal_id=deal.id, quelle=q, url=deal.url,
                             preis=round(preis * random.uniform(1.0, 1.25), 2),
                             preis_eur=round(preis * random.uniform(1.0, 1.25), 2),
                             haendler=haendler))
        if n < 6:
            db.add(Match(rule_id=regeln[n % 3].id, deal_id=deal.id))
        if n in (0, 1, 2, 6):
            db.add(Interaction(deal_id=deal.id, art="gemerkt", benutzer_id=1))

    for n, (titel, quelle, wert) in enumerate(GRATIS):
        deal = Deal(url_hash=f"gratis{n}", titel=titel, titel_norm=titel.lower(),
                    url=f"https://{quelle}.com/p/{n}", preis=0.0, preis_eur=0.0,
                    originalpreis=wert, ist_gratis=True, rabatt_prozent=100,
                    haendler=quelle, quelle=quelle, urteil="bestpreis",
                    urteil_text="Gratis - günstiger geht nicht",
                    check_status="bestaetigt", check_text="Preis 0,00 EUR bestätigt",
                    first_seen=jetzt - timedelta(hours=n + 1), last_seen=jetzt,
                    laeuft_ab=jetzt + timedelta(hours=[5, 30, 70][n]))
        db.add(deal)
        db.flush()
        db.add(Match(rule_id=regeln[1].id, deal_id=deal.id))

    liste = WatchListe(name="Weihnachten", budget=400.0, benutzer_id=1)
    db.add(liste)
    db.flush()
    wunsch = [("Dyson V15 Detect", "https://shop.de/dyson", 499.0, 649.0, liste.id),
              ("Kaffeevollautomat DeLonghi", "https://shop.de/delonghi", 399.0, 429.0, liste.id),
              ("Bosch Akkuschrauber Set", "https://shop.de/bosch", 89.0, 119.0, None)]
    for name, url, ziel, aktuell, lid in wunsch:
        w = WatchItem(name=name, url=url, ziel_preis=ziel, letzter_preis=aktuell,
                      bester_preis=aktuell * 0.95, liste_id=lid, benutzer_id=1,
                      letzter_erfolg=jetzt, haendler="shop.de")
        db.add(w)
        db.flush()
        for t in range(8):
            db.add(WatchPrice(watch_id=w.id, preis=round(aktuell * random.uniform(0.95, 1.15), 2),
                              ts=jetzt - timedelta(days=8 - t)))
    db.commit()

print(ordner)
