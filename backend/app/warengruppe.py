"""Was ist das ueberhaupt fuer ein Ding?

Das Feld `kategorie` am Deal heisst so, meint aber etwas anderes: dort
steht, aus welcher Art Quelle der Fund kam ("community", "gaming",
"reddit"). Der Kategorie-Filter in den Regeln war damit ein zweiter
Quellenfilter - nuetzlich, aber nicht das, was der Name verspricht.

Hier geht es um die Ware: Elektronik, Haushalt, Spielzeug, Lebensmittel.
Das ist die Einteilung, nach der man sucht ("zeig mir Werkzeug unter
50 Euro") und nach der eine Statistik interessant wird ("zwei Drittel
deiner Ersparnis war Elektronik").

**Regeln statt Modell, und zwar aus einem Grund:** die Einteilung muss
erklaerbar sein. Wenn ein Deal in "Drogerie" landet, soll danebenstehen,
welches Wort das ausgeloest hat. Ein Modell, das "Elektronik" sagt und
nicht warum, ist in einer Anwendung, die sonst jede Zahl begruendet, ein
Fremdkoerper.

Ein Modell darf trotzdem mitreden - siehe `ollama.py`. Es kommt aber
erst dran, wenn die Regeln nichts finden, und sein Ergebnis wird als
solches gekennzeichnet. Vorgabe ist: aus.

Wo nichts passt, steht nichts. "Sonstiges" waere eine Antwort, die so
aussieht, als haette jemand hingesehen.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Die Gruppen mit ihrem Anzeigenamen. Bewusst kurz gehalten: zwanzig
# Gruppen trifft keiner mehr, und eine Regel wie "nur Haushalt" wird
# unbrauchbar, wenn die Haelfte in "Haushalt & Garten & Werkzeug" landet.
GRUPPEN: dict[str, str] = {
    "elektronik": "Elektronik",
    "computer": "Computer & Zubehör",
    "gaming": "Gaming",
    "haushalt": "Haushalt & Küche",
    "werkzeug": "Werkzeug & Garten",
    "kleidung": "Kleidung & Schuhe",
    "drogerie": "Drogerie & Gesundheit",
    "lebensmittel": "Lebensmittel & Getränke",
    "spielzeug": "Spielzeug",
    "medien": "Bücher, Filme & Musik",
    "software": "Software & Abos",
    "reise": "Reise & Mobilität",
}

# Die Stichwoerter je Gruppe. Reihenfolge zaehlt: die erste Gruppe mit
# einem Treffer gewinnt, und spezifische Gruppen stehen darum vor
# allgemeinen ("computer" vor "elektronik", sonst faengt "Monitor" in
# der falschen Gruppe an).
#
# Jeder Eintrag ist ein Wortstamm. Drei Schreibweisen, drei Bedeutungen
# (siehe `_wortmuster`):
#
#   "monitor"     Wortanfang - trifft auch "Monitorhalterung"
#   "reis "       mit Leerzeichen: nur das ganze Wort. Ohne diese
#                 Moeglichkeit faende "reis" auch "Reise", und ein
#                 Kurzurlaub landete unter Lebensmitteln.
#   "vollautomat" ab acht Zeichen zusaetzlich am Wortende - deutsche
#                 Komposita setzen das Hauptwort hinten an, und
#                 "Kaffeevollautomat" ist sonst nicht zu fassen.
#                 Kuerzere bleiben vorn verankert, sonst faende
#                 "roller" jeden "Controller".
#
# Umlaute stehen in beiden Schreibweisen, weil Deal-Titel beides
# benutzen.
_STICHWORTE: list[tuple[str, tuple[str, ...]]] = [
    ("computer", (
        "laptop", "notebook", "ultrabook", "macbook", "thinkpad", "chromebook",
        "monitor", "grafikkarte", "geforce", "radeon", "rtx", "ryzen",
        "prozessor", "cpu", "mainboard", "arbeitsspeicher", "ddr4", "ddr5",
        "ssd", "festplatte", "nvme", "netzteil", "gehaeuse", "gehäuse",
        "tastatur", "keyboard", "maus", "mousepad", "drucker", "scanner",
        "router", "wlan", "wifi", "switch-port", "nas", "usb-stick",
        "dockingstation", "webcam", "pc ", "desktop-pc",
    )),
    ("gaming", (
        "playstation", "ps5", "ps4", "xbox", "nintendo", "switch-spiel",
        "steam", "gog", "epic games", "gamepad", "controller", "konsole",
        "spielesammlung", "gaming-stuhl", "vr-brille", "oculus", "quest 3",
    )),
    ("elektronik", (
        "fernseher", "tv ", "oled", "qled", "soundbar", "kopfhoer",
        "kopfhör", "earbuds", "airpods", "lautsprecher", "bluetooth-box",
        "smartphone", "handy", "iphone", "galaxy", "pixel ", "tablet",
        "ipad", "smartwatch", "fitnesstracker", "kamera", "objektiv",
        "drohne", "beamer", "projektor", "powerbank", "ladegeraet",
        "ladegerät", "saugroboter", "e-reader", "kindle", "receiver",
        "hifi", "plattenspieler", "mikrofon",
    )),
    ("haushalt", (
        "kaffeemaschine", "vollautomat", "siebtraeger", "siebträger",
        "wasserkocher", "toaster", "mixer", "kuechenmaschine",
        "küchenmaschine", "pfanne", "topfset", "messer-set", "geschirr",
        "staubsauger", "waschmaschine", "trockner", "geschirrspueler",
        "geschirrspüler", "kuehlschrank", "kühlschrank", "gefrierschrank",
        "backofen", "mikrowelle", "heissluftfritteuse", "heißluftfritteuse",
        "airfryer", "matratze", "bettwaesche", "bettwäsche", "handtuch",
        "regal", "sofa", "schrank", "lampe", "leuchte", "luftreiniger",
    )),
    ("werkzeug", (
        "akkuschrauber", "bohrmaschine", "schlagbohr", "stichsaege",
        "stichsäge", "kreissaege", "kreissäge", "winkelschleifer",
        "werkzeugkoffer", "schraubendreher", "zange", "rasenmaeher",
        "rasenmäher", "heckenschere", "hochdruckreiniger", "leiter",
        "grill", "gartenschlauch", "kettensaege", "kettensäge", "bosch prof",
    )),
    ("kleidung", (
        "t-shirt", "hoodie", "pullover", "jacke", "mantel", "hose", "jeans",
        "sneaker", "schuhe", "stiefel", "sandalen", "socken", "unterwaesche",
        "unterwäsche", "kleid", "rock ", "anzug", "guertel", "gürtel",
        "muetze", "mütze", "handschuhe", "rucksack", "laufschuh",
    )),
    ("drogerie", (
        "shampoo", "duschgel", "zahnpasta", "zahnbuerste", "zahnbürste",
        "rasierer", "rasierklingen", "deo", "parfum", "creme", "sonnencreme",
        "windeln", "waschmittel", "spuelmittel", "spülmittel", "toilettenpapier",
        "vitamin", "nahrungsergaenzung", "nahrungsergänzung", "proteinpulver",
    )),
    ("lebensmittel", (
        "kaffeebohnen", "kaffeepads", "kapseln", "schokolade", "suessigkeit",
        "süßigkeit", "gummibaer", "gummibär", "chips", "nudeln", "reis ",
        "olivenoel", "olivenöl", "bier", "wein", "whisky", "gin ", "rum ",
        "energy drink", "limonade", "mineralwasser", "tee ", "muesli",
        "müsli", "tiefkuehl", "tiefkühl",
    )),
    ("spielzeug", (
        "lego", "playmobil", "puppe", "brettspiel", "kartenspiel", "puzzle",
        "modellbau", "carrera", "bobby-car", "kuscheltier", "bausatz",
        "spielzeugauto", "schleich", "ravensburger",
    )),
    ("medien", (
        "blu-ray", "bluray", "dvd", "hoerbuch", "hörbuch", "taschenbuch",
        "gebundene ausgabe", "comic", "manga", "vinyl", "schallplatte",
        "zeitschrift", "abo-zeitschrift", "roman",
    )),
    ("software", (
        "lizenz", "office 365", "microsoft 365", "windows 11", "antivirus",
        "vpn-abo", "nordvpn", "surfshark", "adobe", "photoshop",
        "streaming-abo", "netflix", "spotify", "disney+", "cloud-speicher",
    )),
    ("reise", (
        "hotel", "uebernachtung", "übernachtung", "flug ", "fluege", "flüge",
        "mietwagen", "bahncard", "deutschlandticket", "kreuzfahrt",
        "pauschalreise", "ferienwohnung", "kurzurlaub", "tankgutschein",
        "e-bike", "fahrrad", "roller", "reifen",
    )),
]

# Ab dieser Laenge darf ein Stichwort auch am Wortende stehen.
# Acht Zeichen sind lang genug, dass ein zufaelliges Zusammentreffen
# unwahrscheinlich wird, und kurz genug fuer "kopfhoer" und "waschmasch".
_KOMPOSITUM_AB = 8


def _wortmuster(wort: str) -> str:
    kern = re.escape(wort.strip())
    if wort.endswith(" "):
        return rf"(?<![\w]){kern}(?![\w])"          # nur das ganze Wort
    if len(wort.strip()) >= _KOMPOSITUM_AB:
        return rf"(?:(?<![\w]){kern}|{kern}(?![\w]))"
    return rf"(?<![\w]){kern}"


# Vorgefertigte Ausdruecke: einmal bauen statt bei jedem Deal.
_MUSTER: list[tuple[str, re.Pattern[str]]] = [
    (gruppe, re.compile("|".join(_wortmuster(wort) for wort in woerter),
                        re.IGNORECASE))
    for gruppe, woerter in _STICHWORTE
]


def _text(titel: str | None, beschreibung: str | None = None,
          tags: list[str] | None = None) -> str:
    teile = [titel or "", beschreibung or "", " ".join(tags or [])]
    return " ".join(teile).lower()


def bestimme(titel: str | None, beschreibung: str | None = None,
             tags: list[str] | None = None) -> tuple[str | None, str | None]:
    """Warengruppe und das Wort, das sie ausgeloest hat.

    Gibt (None, None) zurueck, wenn nichts passt. Das ist ein gueltiges
    Ergebnis und keine Luecke: "Sammeldeal: 20 Artikel reduziert" hat
    keine Warengruppe, und eine erfundene waere schlimmer als keine.

    Der Titel wiegt schwerer als die Beschreibung - in ihr steht oft ein
    Zubehoerteil ("inkl. USB-Kabel"), das den ganzen Deal in die falsche
    Gruppe zoege. Darum erst der Titel allein, dann alles zusammen.
    """
    for haystack in (_text(titel), _text(titel, beschreibung, tags)):
        if not haystack.strip():
            continue
        for gruppe, muster in _MUSTER:
            treffer = muster.search(haystack)
            if treffer:
                return gruppe, treffer.group(0).strip()
    return None, None


def label(gruppe: str | None) -> str | None:
    """Anzeigename einer Gruppe, oder None."""
    return GRUPPEN.get(gruppe or "")
